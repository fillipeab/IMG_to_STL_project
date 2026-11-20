"""ETAPA 2 — monta o relevo 2.5D (campo de alturas) a partir do `PlanarMap` e das texturas escolhidas.

Camadas combinadas por máximo, sobre uma placa de espessura `base_thickness_mm`:
  1. regiões: textura repetida em coordenadas globais, com zonas de exclusão ao redor de
     fronteiras e pontos (ali entra a textura reduzida, com transição suave)
  2. fronteiras: cordão semi-elíptico centrado na curva
  3. pontos: formas (círculo, quadrado, triângulo) com flancos inclinados, por classe
Base "silhueta": só as células sobre as regiões escolhidas (mais a metade do cordão) existem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from ..comum.geometria import smoothstep
from ..etapa1_reconhecimento.modelos import InterestPoint, PlanarMap
from .atribuicao import TextureAssigner, TextureAssignment
from .biblioteca import RidgeProfile, Texture, TextureLibrary, TextureTransform, TransformedTexture
from .config import Etapa2Config
from .formas_pontos import PointShapeFactory


@dataclass
class HeightField:
    z: np.ndarray                         # (ny, nx) altura em mm, origem no canto inferior esquerdo da peça
    dx: float                             # espaçamento da grade (mm)
    dy: float
    cells: Optional[np.ndarray] = None    # (ny-1, nx-1) bool: células que existem (None = todas, base retangular)

    @property
    def size_mm(self) -> Tuple[float, float]:
        ny, nx = self.z.shape
        return (nx - 1) * self.dx, (ny - 1) * self.dy

    def estimate_triangles(self) -> int:
        ny, nx = self.z.shape
        if self.cells is None:
            return 2 * (nx - 1) * (ny - 1) + 4 * (nx + ny - 2) + 2 * (nx + ny - 2)
        c = np.pad(self.cells, 1)
        walls = int((c[1:-1, 1:-1] & ~c[:-2, 1:-1]).sum() + (c[1:-1, 1:-1] & ~c[2:, 1:-1]).sum()
                    + (c[1:-1, 1:-1] & ~c[1:-1, :-2]).sum() + (c[1:-1, 1:-1] & ~c[1:-1, 2:]).sum())
        return 4 * int(self.cells.sum()) + 2 * walls

    def save_shaded_preview(self, path: str, max_side: int = 1600) -> None:
        """PNG de relevo sombreado (luz a noroeste) para conferir o resultado."""
        z = self.z
        step = max(1, int(np.ceil(max(z.shape) / max_side)))
        zs = z[::step, ::step]
        gy, gx = np.gradient(zs, self.dy * step, self.dx * step)
        lx, ly, lz = -0.6, 0.6, 0.5
        nx_, ny_, nz_ = -gx, -gy, np.ones_like(zs)
        s = (nx_ * lx + ny_ * ly + nz_ * lz) / np.sqrt(nx_ ** 2 + ny_ ** 2 + nz_ ** 2) / np.sqrt(lx ** 2 + ly ** 2 + lz ** 2)
        img = (255 * np.clip(s, 0, 1)).astype(np.uint8)
        if self.cells is not None:
            node = np.zeros(z.shape, bool)
            node[:-1, :-1] |= self.cells; node[1:, :-1] |= self.cells
            node[:-1, 1:] |= self.cells; node[1:, 1:] |= self.cells
            img[~node[::step, ::step]] = 25                 # fora da base: quase preto
        cv2.imwrite(path, img[::-1])                        # y para cima -> imagem


class ReliefBuilder:
    def __init__(self, pmap: PlanarMap, config: Etapa2Config,
                 manual: Optional[Dict[int, TextureAssignment]] = None):
        config.validate()
        self.pmap, self.cfg = pmap, config
        self.profile = RidgeProfile(config.ridge_profile, config.apex_round_mm)
        if config.texture_dir:
            TextureLibrary.load_directory(config.texture_dir)
        assigner = TextureAssigner(config)
        self.assignments = assigner.assign(pmap, manual)
        self.warnings: List[str] = list(assigner.warnings)
        if manual:
            self.warnings += assigner.neighbour_conflicts(pmap, self.assignments)
        self._texture_cache: Dict[int, Texture] = {}
        self._region_textures: Dict[int, Texture] = {}
        self._reduced_textures: Dict[int, Texture] = {}
        names = {r.id: r.name for r in pmap.regions}
        for rid, asg in self.assignments.items():
            if asg.texture_id == 0:
                continue
            tex = self._texture(asg.texture_id)
            if not asg.transform.is_identity():
                tex = TransformedTexture(tex, asg.transform)
            self._region_textures[rid] = tex
            if config.exclusion_texture_scale > 0:
                small = TransformedTexture(tex, TextureTransform(scale=config.exclusion_texture_scale))
                self._reduced_textures[rid] = small
                if small.min_feature_mm is not None and small.min_feature_mm < config.min_feature_warn_mm:
                    self.warnings.append(
                        f"região {names[rid]}: na zona de exclusão a textura reduzida ({config.exclusion_texture_scale:g}x) "
                        f"tem traço mínimo de {small.min_feature_mm:.2f} mm (< {config.min_feature_warn_mm} mm)")
            if tex.min_feature_mm is not None and tex.min_feature_mm < config.min_feature_warn_mm:
                self.warnings.append(
                    f"região {names[rid]}: textura '{tex.name}' com traço mínimo de {tex.min_feature_mm:.2f} mm "
                    f"(< {config.min_feature_warn_mm} mm) — pode não imprimir bem")
        self.points = [p for p in pmap.points if self._models(p)]
        self.cord_borders = [b for b in pmap.borders if len(b.points_mm) >= 2 and (config.frame_cord or not b.outer)]

    def _models(self, p: InterestPoint) -> bool:
        if p.classe == "triplice":
            return self.cfg.model_triple_points
        if p.classe == "multiplo":
            return self.cfg.model_multiple_points
        return True

    def _shape_name(self, p: InterestPoint) -> str:
        return p.shape or self.cfg.point_shape_by_class.get(p.classe, self.cfg.point_shape)

    # ---- API ---- #
    def build(self) -> HeightField:
        cfg, pm = self.cfg, self.pmap
        W, H = pm.size_mm
        has_frame = cfg.frame_cord and pm.outer_frame and any(b.outer for b in pm.borders)
        margin = cfg.border_width_mm / 2.0 if has_frame else 0.0   # o cordão da moldura cabe inteiro
        nx = int(round((W + 2 * margin) / cfg.resolution_mm)) + 1
        ny = int(round((H + 2 * margin) / cfg.resolution_mm)) + 1
        xs = np.linspace(-margin, W + margin, nx)
        ys = np.linspace(-margin, H + margin, ny)
        dx, dy = xs[1] - xs[0], ys[1] - ys[0]
        X, Y = np.meshgrid(xs.astype(np.float32), ys.astype(np.float32))

        labels = pm.label_at(X, Y)
        half = cfg.border_width_mm / 2.0
        fade = max(cfg.exclusion_fade_mm, 1e-6)

        d_border = self._border_distance(X, Y, half + cfg.border_exclusion_mm + fade + cfg.resolution_mm)
        f_border = smoothstep((d_border - half - cfg.border_exclusion_mm) / fade)   # inf -> 1

        cord = self._cord_layer(d_border, half)
        pts, f_points = self._point_layers(X, Y, xs[0], ys[0], dx, dy, fade)

        f = f_border * f_points          # 1 fora das zonas de exclusão, 0 no miolo delas
        tex = self._texture_layer(X, Y, labels)
        if cfg.exclusion_texture_scale > 0:
            small = self._texture_layer(X, Y, labels, reduced=True, only=f < 0.999)
            tex = f * tex + (1.0 - f) * small
        else:
            tex = tex * f

        relief = np.maximum(np.maximum(tex, cord), pts)
        z = (cfg.base_thickness_mm + relief).astype(np.float32)
        return HeightField(z=z, dx=float(dx), dy=float(dy), cells=self._base_cells(labels, half, dx))

    # ---- base ---- #
    def _base_region_ids(self) -> List[int]:
        if self.cfg.base_regions is not None:
            return [int(i) for i in self.cfg.base_regions]
        return [r.id for r in self.pmap.regions if not r.ignored]

    def _base_cells(self, labels: np.ndarray, half: float, step_mm: float) -> Optional[np.ndarray]:
        """Base "silhueta": células cujos 4 cantos estão a menos de meia largura de cordão (+1 passo)
        das regiões escolhidas. None = base retangular."""
        if self.cfg.base_mode != "silhueta":
            return None
        inc = np.isin(labels, self._base_region_ids())
        if not inc.any():
            raise ValueError("base 'silhueta' sem nenhuma região: confira base_regions e a cor de fundo (ignore_color).")
        near = ndimage.distance_transform_edt(~inc) * step_mm <= half + step_mm
        return near[:-1, :-1] & near[:-1, 1:] & near[1:, :-1] & near[1:, 1:]

    # ---- texturas ---- #
    def _texture(self, texture_id: int) -> Texture:
        if texture_id not in self._texture_cache:
            params = self.cfg.texture_params.get(texture_id, {})
            self._texture_cache[texture_id] = TextureLibrary.create(texture_id, profile=self.profile, **params)
        return self._texture_cache[texture_id]

    def _texture_layer(self, X, Y, labels, reduced: bool = False, only=None) -> np.ndarray:
        """Altura (mm) da textura de cada região. reduced=True usa a versão em escala menor (e altura
        menor); `only` (máscara) limita onde calcular, para poupar tempo."""
        cfg = self.cfg
        tex = np.zeros(X.shape, dtype=np.float32)
        textures = self._reduced_textures if reduced else self._region_textures
        for rid, asg in self.assignments.items():
            if asg.texture_id == 0:
                continue
            mask = labels == rid
            if only is not None:
                mask &= only
            if not mask.any():
                continue
            amp = asg.amplitude_mm * (cfg.exclusion_texture_height_factor if reduced else 1.0)
            x, y = X[mask].astype(np.float64), Y[mask].astype(np.float64)
            tex[mask] = (textures[rid].height(x, y) * amp).astype(np.float32)
        return tex

    # ---- fronteiras ---- #
    def _border_distance(self, X, Y, max_dist: float) -> np.ndarray:
        """Distância (mm) de cada nó da grade ao eixo da fronteira mais próxima (inf se > max_dist)."""
        lines = [b.points_mm for b in self.cord_borders]
        if not lines:
            return np.full(X.shape, np.inf, dtype=np.float32)
        samples = self._densify(lines, step=min(self.cfg.resolution_mm / 2.0, 0.05))
        query = np.column_stack([X.ravel(), Y.ravel()])
        d, _ = cKDTree(samples).query(query, distance_upper_bound=max_dist, workers=-1)
        return d.reshape(X.shape).astype(np.float32)

    @staticmethod
    def _densify(polylines: List[np.ndarray], step: float) -> np.ndarray:
        out = []
        for p in polylines:
            seg = np.hypot(*np.diff(p, axis=0).T)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            if cum[-1] <= 0:
                continue
            s = np.linspace(0.0, cum[-1], max(2, int(np.ceil(cum[-1] / step)) + 1))
            out.append(np.column_stack([np.interp(s, cum, p[:, 0]), np.interp(s, cum, p[:, 1])]))
        return np.vstack(out)

    def _cord_layer(self, d_border: np.ndarray, half: float) -> np.ndarray:
        cfg = self.cfg
        height = half if cfg.border_semicircle else cfg.border_height_mm
        inside = d_border < half
        cord = np.zeros(d_border.shape, dtype=np.float32)
        cord[inside] = height * np.sqrt(1.0 - (d_border[inside] / half) ** 2)
        return cord

    # ---- pontos ---- #
    def _point_layers(self, X, Y, x0, y0, dx, dy, fade) -> Tuple[np.ndarray, np.ndarray]:
        cfg = self.cfg
        pts = np.zeros(X.shape, dtype=np.float32)
        factor = np.ones(X.shape, dtype=np.float32)
        ny, nx = X.shape
        for p in self.points:
            shape = PointShapeFactory.create(self._shape_name(p), cfg.point_size_mm)
            excl = max(cfg.point_exclusion_mm, shape.extent + cfg.point_flank_mm)
            reach = excl + fade
            i0, i1 = max(0, int((p.xy_mm[1] - reach - y0) / dy)), min(ny, int((p.xy_mm[1] + reach - y0) / dy) + 2)
            j0, j1 = max(0, int((p.xy_mm[0] - reach - x0) / dx)), min(nx, int((p.xy_mm[0] + reach - x0) / dx) + 2)
            if i0 >= i1 or j0 >= j1:
                continue
            ddx = X[i0:i1, j0:j1] - p.xy_mm[0]
            ddy = Y[i0:i1, j0:j1] - p.xy_mm[1]
            r = np.hypot(ddx, ddy)
            factor[i0:i1, j0:j1] = np.minimum(factor[i0:i1, j0:j1], smoothstep((r - excl) / fade))
            h = cfg.point_height_mm * np.clip(1.0 - np.maximum(shape.sdf(ddx, ddy), 0.0) / cfg.point_flank_mm, 0.0, 1.0)
            pts[i0:i1, j0:j1] = np.maximum(pts[i0:i1, j0:j1], h)
        return pts, factor
