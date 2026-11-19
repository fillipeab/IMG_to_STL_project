"""Parte 2 — monta o relevo 2.5D (campo de alturas) a partir do `PlanarMap`.

Camadas combinadas por máximo, sobre uma placa de espessura `base_thickness_mm`:
  1. regiões: textura repetida em coordenadas globais, com zonas de exclusão ao redor de
     fronteiras e pontos (a textura é zerada e volta com uma transição suave)
  2. fronteiras: cordão semi-elíptico centrado na curva
  3. pontos: formas (círculo, quadrado, triângulo) com flancos inclinados, por valência
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .config import ReliefConfig
from .textures import RidgeProfile, Texture, TextureLibrary
from .transforms import TextureTransform, TransformedTexture
from .vision import PlanarMap

SQRT3 = float(np.sqrt(3.0))


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------- #
# Formas dos pontos
# --------------------------------------------------------------------------- #
class PointShape(ABC):
    name = "forma"

    def __init__(self, size: float):
        self.size = float(size)

    @property
    @abstractmethod
    def extent(self) -> float:
        """Maior distância do centro até a borda da forma (mm)."""

    @abstractmethod
    def sdf(self, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
        """Distância com sinal à forma (negativa dentro)."""


class CirclePoint(PointShape):
    name = "circle"
    extent = property(lambda self: self.size / 2.0)

    def sdf(self, dx, dy):
        return np.hypot(dx, dy) - self.size / 2.0


class SquarePoint(PointShape):
    name = "square"
    extent = property(lambda self: self.size / np.sqrt(2.0))

    def sdf(self, dx, dy):
        qx, qy = np.abs(dx) - self.size / 2.0, np.abs(dy) - self.size / 2.0
        return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0)


class TrianglePoint(PointShape):
    """Triângulo equilátero de lado `size`, ápice para +y, centrado no baricentro."""

    name = "triangle"
    extent = property(lambda self: self.size / SQRT3)

    def sdf(self, dx, dy):
        r = self.size / 2.0
        px, py = np.abs(dx) - r, dy + r / SQRT3
        m = px + SQRT3 * py > 0.0
        px, py = np.where(m, (px - SQRT3 * py) / 2.0, px), np.where(m, (-SQRT3 * px - py) / 2.0, py)
        px = px - np.clip(px, -2.0 * r, 0.0)
        return -np.hypot(px, py) * np.sign(py)


class PointShapeFactory:
    _shapes = {c.name: c for c in (CirclePoint, SquarePoint, TrianglePoint)}

    @classmethod
    def create(cls, name: str, size: float) -> PointShape:
        if name not in cls._shapes:
            raise KeyError(f"Forma '{name}' desconhecida. Use: {sorted(cls._shapes)}")
        return cls._shapes[name](size)


# --------------------------------------------------------------------------- #
# Atribuição de texturas às regiões
# --------------------------------------------------------------------------- #
@dataclass
class TextureAssignment:
    texture_id: int
    amplitude_mm: float = 0.6
    transform: TextureTransform = field(default_factory=TextureTransform)


class TextureAssigner:
    """Decide a textura de cada região.

    Prioridade: escolha manual (config) > fundo ignorado (lisa) > automática.
    Automática: regiões vizinhas NUNCA recebem a mesma textura e, enquanto houver textura
    livre, nenhuma textura se repete na imagem. Só repete quando há mais regiões do que
    texturas em `default_textures` (e, mesmo assim, nunca entre vizinhas, se for possível).
    Repetições pedidas manualmente pela usuária são respeitadas sem aviso.
    """

    def __init__(self, cfg: ReliefConfig):
        self.cfg = cfg
        self.warnings: List[str] = []

    @staticmethod
    def adjacency(pmap: PlanarMap) -> Dict[int, set]:
        """Regiões que se tocam (pixels vizinhos com rótulos diferentes)."""
        lab = pmap.labels
        pairs = set()
        for a, b in ((lab[:, :-1], lab[:, 1:]), (lab[:-1, :], lab[1:, :])):
            m = a != b
            lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
            pairs.update(zip(lo.tolist(), hi.tolist()))
        adj: Dict[int, set] = {r.id: set() for r in pmap.regions}
        for x, y in pairs:
            adj[x].add(y)
            adj[y].add(x)
        return adj

    def assign(self, pmap: PlanarMap) -> Dict[int, TextureAssignment]:
        cfg = self.cfg
        out: Dict[int, TextureAssignment] = {}
        auto: List[int] = []
        for r in pmap.regions:
            if r.id in cfg.region_textures:
                out[r.id] = self._parse(cfg.region_textures[r.id])
            elif r.ignored:
                out[r.id] = TextureAssignment(0, amplitude_mm=cfg.texture_amplitude_mm)
            else:
                auto.append(r.id)
        if not auto:
            return out

        pool = [t for t in cfg.default_textures if t != 0] or [0]
        adj = self.adjacency(pmap)
        usage = Counter(a.texture_id for a in out.values() if a.texture_id != 0)
        chosen: Dict[int, int] = {}
        pending = set(auto)

        def neighbour_textures(rid: int) -> set:
            ts = {out[n].texture_id for n in adj[rid] if n in out}
            ts |= {chosen[n] for n in adj[rid] if n in chosen}
            ts.discard(0)
            return ts

        while pending:
            # a mais "apertada" primeiro: mais texturas já usadas por vizinhas, depois mais vizinhas
            rid = max(sorted(pending), key=lambda i: (len(neighbour_textures(i)), len(adj[i])))
            forbidden = neighbour_textures(rid)
            free = [t for t in pool if t not in forbidden]
            if free:
                tex = min(free, key=lambda t: (usage[t], pool.index(t)))
            else:
                tex = min(pool, key=lambda t: (sum(1 for n in adj[rid] if (chosen.get(n) or (out[n].texture_id if n in out else None)) == t),
                                               usage[t], pool.index(t)))
                self.warnings.append(
                    f"região {rid}: todas as texturas de default_textures já são usadas por regiões vizinhas; "
                    f"repetiu a textura {tex} (acrescente texturas em default_textures ou escolha à mão)")
            chosen[rid] = tex
            usage[tex] += 1
            pending.discard(rid)
        for rid, tex in chosen.items():
            out[rid] = TextureAssignment(tex, amplitude_mm=cfg.texture_amplitude_mm)
        if len(auto) > len(pool):
            self.warnings.append(
                f"{len(auto)} regiões e só {len(pool)} texturas em default_textures: algumas se repetem "
                f"(nunca entre vizinhas, quando possível). Acrescente texturas para evitar repetições.")
        return dict(sorted(out.items()))

    def _parse(self, spec) -> TextureAssignment:
        amp = self.cfg.texture_amplitude_mm
        if isinstance(spec, dict):
            return TextureAssignment(
                texture_id=int(spec["texture"]),
                amplitude_mm=float(spec.get("amplitude_mm", amp)),
                transform=TextureTransform.from_spec(spec))
        return TextureAssignment(int(spec), amplitude_mm=amp)


# --------------------------------------------------------------------------- #
# Campo de alturas
# --------------------------------------------------------------------------- #
@dataclass
class HeightField:
    z: np.ndarray        # (ny, nx) altura em mm, origem no canto inferior esquerdo da peça
    dx: float            # espaçamento da grade (mm)
    dy: float

    @property
    def size_mm(self) -> Tuple[float, float]:
        ny, nx = self.z.shape
        return (nx - 1) * self.dx, (ny - 1) * self.dy

    def estimate_triangles(self) -> int:
        ny, nx = self.z.shape
        return 2 * (nx - 1) * (ny - 1) + 4 * (nx + ny - 2) + 2 * (nx + ny - 2)

    def save_shaded_preview(self, path: str, max_side: int = 1600) -> None:
        """PNG de relevo sombreado (luz a noroeste) para conferir o resultado."""
        z = self.z
        step = max(1, int(np.ceil(max(z.shape) / max_side)))
        z = z[::step, ::step]
        gy, gx = np.gradient(z, self.dy * step, self.dx * step)
        lx, ly, lz = -0.6, 0.6, 0.5
        nx_, ny_, nz_ = -gx, -gy, np.ones_like(z)
        s = (nx_ * lx + ny_ * ly + nz_ * lz) / np.sqrt(nx_ ** 2 + ny_ ** 2 + nz_ ** 2) / np.sqrt(lx ** 2 + ly ** 2 + lz ** 2)
        img = (255 * np.clip(s, 0, 1)).astype(np.uint8)[::-1]  # y para cima -> imagem
        cv2.imwrite(path, img)


# --------------------------------------------------------------------------- #
# Construtor do relevo
# --------------------------------------------------------------------------- #
class ReliefBuilder:
    def __init__(self, pmap: PlanarMap, config: ReliefConfig):
        config.validate()
        self.pmap, self.cfg = pmap, config
        self.profile = RidgeProfile(config.ridge_profile, config.apex_round_mm)
        if config.texture_dir:
            TextureLibrary.load_directory(config.texture_dir)
        assigner = TextureAssigner(config)
        self.assignments = assigner.assign(pmap)
        self._texture_cache: Dict[int, Texture] = {}
        self.warnings: List[str] = list(assigner.warnings)
        self._region_textures: Dict[int, Texture] = {}
        self._reduced_textures: Dict[int, Texture] = {}   # versão em escala menor p/ a zona de exclusão
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
                        f"região {rid}: na zona de exclusão a textura reduzida ({config.exclusion_texture_scale:g}x) "
                        f"tem traço mínimo de {small.min_feature_mm:.2f} mm (< {config.min_feature_warn_mm} mm)")
            if tex.min_feature_mm is not None and tex.min_feature_mm < config.min_feature_warn_mm:
                self.warnings.append(
                    f"região {rid}: textura '{tex.name}' com traço mínimo de {tex.min_feature_mm:.2f} mm "
                    f"(< {config.min_feature_warn_mm} mm) — pode não imprimir bem")

    # ---- API ---- #
    def build(self) -> HeightField:
        cfg, pm = self.cfg, self.pmap
        W, H = pm.size_mm
        has_frame = pm.outer_frame and any(b.outer for b in pm.borders)
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

        # f = 1 fora das zonas de exclusão, 0 no miolo delas (cordão/ponto + margem).
        f = f_border * f_points
        tex = self._texture_layer(X, Y, labels)
        if cfg.exclusion_texture_scale > 0:
            # suavização: na zona de exclusão entra a textura reduzida (escala e altura menores)
            small = self._texture_layer(X, Y, labels, reduced=True, only=f < 0.999)
            tex = f * tex + (1.0 - f) * small
        else:
            tex = tex * f

        relief = np.maximum(np.maximum(tex, cord), pts)
        z = (cfg.base_thickness_mm + relief).astype(np.float32)
        return HeightField(z=z, dx=float(dx), dy=float(dy))

    # ---- texturas ---- #
    def _texture(self, texture_id: int) -> Texture:
        if texture_id not in self._texture_cache:
            params = self.cfg.texture_params.get(texture_id, {})
            self._texture_cache[texture_id] = TextureLibrary.create(texture_id, profile=self.profile, **params)
        return self._texture_cache[texture_id]

    def _texture_layer(self, X, Y, labels, reduced: bool = False, only=None) -> np.ndarray:
        """Altura (mm) da textura de cada região. reduced=True usa a versão em escala menor
        (e altura menor); `only` (máscara) limita onde calcular, para poupar tempo."""
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
        lines = [b.points_mm for b in self.pmap.borders if len(b.points_mm) >= 2]
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
        for p in self.pmap.points:
            shape = PointShapeFactory.create(p.shape or cfg.point_shapes.get(p.valence, cfg.point_shape),
                                             cfg.point_size_mm)
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
