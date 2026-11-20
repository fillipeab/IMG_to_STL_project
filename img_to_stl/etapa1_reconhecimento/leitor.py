"""ETAPA 1 — leitor de imagem: imagem -> `PlanarMap` (regiões, famílias, fronteiras e pontos).

Métodos (todos clássicos, sem rede neural; só numpy, scipy, OpenCV e Pillow):
  1. carga (EXIF, transparência -> branco), redução e filtro bilateral (tira ruído, preserva bordas)
  2. marcadores de pontos de interesse: bolinhas de cor combinada são localizadas e apagadas (inpaint)
  3. k-means em Lab (quantização de cor) + componentes conexos (4-conexo) = regiões iniciais
  4. remoção de estruturas finas (contornos pretos, serrilhado) via transformada de distância
  5. fusão: regiões pequenas -> vizinha mais parecida; vizinhas com ΔE < tolerância; até caber em max_regions
  6. nomes (cor + ordinal) e famílias (cores parecidas, vizinhas ou não)
  7. fronteiras: traçado nas frestas entre pixels, suavização, Douglas-Peucker, contração das curtas
  8. pontos: tríplices (vértices da rede de fronteiras) + de interesse (marcadores / arquivo)
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from scipy.spatial import cKDTree

from ..comum.arquivos import slug
from .config import Etapa1Config
from .criterios import resolve_fusion
from .cores import color_name, group_families, rgb_to_lab
from .fronteiras import BorderTracer, Chain, contract_short
from .fusao import RegionGraph
from .modelos import Border, Family, InterestPoint, PlanarMap, Region
from . import pontos as pts


class ImageReader:
    def __init__(self, config: Optional[Etapa1Config] = None):
        self.cfg = config or Etapa1Config()
        self.warnings: List[str] = []

    # ---- API ---- #
    def read(self, image_path: str) -> PlanarMap:
        self.warnings = []
        rgb, (w0, h0) = self._load(image_path)
        h, w = rgb.shape[:2]
        mm_per_px = self.cfg.width_mm / w

        markers: List[Tuple[str, float, float]] = []
        if self.cfg.point_markers:
            markers, erase = pts.detect_markers(rgb, self.cfg.point_markers, mm_per_px, self.cfg.marker_max_area_mm2)
            rgb = pts.inpaint(rgb, erase)

        rgb = self._denoise(rgb)
        lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)
        labels = self._initial_segmentation(lab)
        labels = self._remove_thin(labels, mm_per_px)
        labels = self._merge_regions(labels, lab, mm_per_px)

        pmap = PlanarMap(labels=labels, mm_per_px=mm_per_px, outer_frame=self.cfg.outer_frame)
        pmap.regions = self._build_regions(labels, rgb, mm_per_px)
        self._name_regions(pmap.regions)
        pmap.families = self._build_families(pmap.regions)
        chains = self._build_borders(pmap)
        self._name_borders(pmap)
        pmap.points = self._build_points(pmap, chains, markers, (w0, h0), (w, h))
        for entry in self.cfg.merge_regions:                    # fusões pedidas (em ordem)
            try:
                pmap = self.apply_fusion(pmap, entry)
            except ValueError as e:                             # parâmetros mudaram: não derruba a etapa 1
                self.warnings.append(f"fusão {entry!r} ignorada: {e}")
        return pmap

    # ---- fusão escolhida pelo usuário ---- #
    def apply_fusion(self, pmap: PlanarMap, entry) -> PlanarMap:
        """`entry`: lista de números de região ou critério ("familia", "menores=50", "cor=verde")."""
        return self.merge_groups(pmap, resolve_fusion(pmap, entry))

    def merge(self, pmap: PlanarMap, group: List[int]) -> PlanarMap:
        return self.merge_groups(pmap, [group])

    def merge_groups(self, pmap: PlanarMap, groups: List[List[int]]) -> PlanarMap:
        """Funde cada grupo de regiões (ids) numa só e refaz nomes, famílias, fronteiras e pontos tríplices.
        Pontos de interesse (marcadores/arquivo) são mantidos. Retorna um novo PlanarMap."""
        n = len(pmap.regions)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for group in groups:
            ids = list(dict.fromkeys(int(i) for i in group))
            bad = [i for i in ids if not 0 <= i < n]
            if bad:
                raise ValueError(f"região inexistente: {bad} (há {n} regiões, de 0 a {n - 1})")
            if len(ids) < 2:
                raise ValueError("informe pelo menos 2 regiões diferentes para fundir")
            for i in ids[1:]:
                parent[find(i)] = find(ids[0])
        comps: dict = {}
        for i in range(n):
            comps.setdefault(find(i), []).append(i)

        old = pmap.regions
        area = np.array([r.area_mm2 for r in old])
        items = []                                              # (menor id do grupo, Region nova)
        for members in comps.values():
            if len(members) == 1:
                items.append((members[0], old[members[0]]))
                continue
            if ndimage.label(np.isin(pmap.labels, members))[1] > 1:
                self.warnings.append(f"fusão {members}: as regiões não se tocam; a região fundida terá partes separadas")
            m = np.array(members)
            w = area[m] / area[m].sum()
            merged = Region(
                id=-1, area_mm2=float(area[m].sum()),
                color_rgb=tuple(int(round(c)) for c in (np.array([old[i].color_rgb for i in members]) * w[:, None]).sum(0)),
                centroid_mm=tuple(float(c) for c in (np.array([old[i].centroid_mm for i in members]) * w[:, None]).sum(0)),
                touches_frame=any(old[i].touches_frame for i in members),
                ignored=old[members[int(np.argmax(area[m]))]].ignored)
            merged.color_name = color_name(merged.color_rgb)
            items.append((members[0], merged))
        order = sorted(items, key=lambda t: -t[1].area_mm2)     # região 0 = a maior (empate: id menor)
        newid = np.zeros(n, dtype=np.int32)
        regions = []
        for k, (first, r) in enumerate(order):
            r.id = k
            regions.append(r)
            for i in comps[find(first)]:
                newid[i] = k
        out = PlanarMap(labels=newid[pmap.labels], mm_per_px=pmap.mm_per_px, outer_frame=pmap.outer_frame)
        out.regions = regions
        self._name_regions(out.regions)
        out.families = self._build_families(out.regions)
        chains = self._build_borders(out)
        self._name_borders(out)
        h = out.labels.shape[0]
        mpp = out.mm_per_px
        for p in (q for q in pmap.points if not q.is_junction):
            p.id = len(out.points)
            out.points.append(p)
        for x, y, regs in pts.junction_points(chains, lambda q: self._to_mm(q, mpp, h),
                                              self.cfg.triple_min_regions, self.cfg.triple_merge_dist_mm):
            out.points.append(InterestPoint(id=len(out.points), xy_mm=(float(x), float(y)),
                                            classe=pts.junction_class(len(regs)), regions=tuple(regs)))
        return out

    # ---- 1. carga e filtro ---- #
    def _load(self, path: str) -> Tuple[np.ndarray, Tuple[int, int]]:
        img = ImageOps.exif_transpose(Image.open(path))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, img)
        rgb = np.asarray(img.convert("RGB"))
        original = (rgb.shape[1], rgb.shape[0])
        scale = min(1.0, self.cfg.work_max_px / max(rgb.shape[:2]))
        if scale < 1.0:
            rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return rgb, original

    def _denoise(self, rgb: np.ndarray) -> np.ndarray:
        for _ in range(self.cfg.denoise_iterations):
            rgb = cv2.bilateralFilter(rgb, 9, self.cfg.denoise_sigma_color, self.cfg.denoise_sigma_space)
        return rgb

    # ---- 3. regiões iniciais ---- #
    def _initial_segmentation(self, lab: np.ndarray) -> np.ndarray:
        h, w = lab.shape[:2]
        pixels = lab.reshape(-1, 3).astype(np.float32)
        rng = np.random.default_rng(self.cfg.random_seed)
        sample = pixels[rng.choice(len(pixels), size=min(len(pixels), 150_000), replace=False)]
        k = max(1, min(self.cfg.n_color_clusters, len(sample)))
        cv2.setRNGSeed(self.cfg.random_seed)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5)
        _, _, centers = cv2.kmeans(sample, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
        cluster = cKDTree(centers).query(pixels)[1].reshape(h, w)

        labels = np.zeros((h, w), dtype=np.int32)
        offset = 0
        for c in range(k):
            cc, n = ndimage.label(cluster == c)       # conectividade 4
            if n:
                labels[cc > 0] = cc[cc > 0] + offset - 1
                offset += n
        return labels

    # ---- 4. estruturas finas (contornos pretos, serrilhado, texto) ---- #
    def _remove_thin(self, labels: np.ndarray, mm_per_px: float) -> np.ndarray:
        """Apaga componentes mais finos que `min_region_thickness_mm` e preenche o espaço com o
        rótulo vizinho mais próximo; a fronteira passa pelo meio do traço e fica contínua."""
        t_mm = self.cfg.min_region_thickness_mm
        if t_mm <= 0:
            return labels
        p = np.pad(labels, 1, mode="edge")
        c = p[1:-1, 1:-1]
        boundary = (c != p[:-2, 1:-1]) | (c != p[2:, 1:-1]) | (c != p[1:-1, :-2]) | (c != p[1:-1, 2:])
        dt = cv2.distanceTransform((~boundary).astype(np.uint8), cv2.DIST_L2, 3)
        n = int(labels.max()) + 1
        max_dt = np.asarray(ndimage.maximum(dt, labels, index=np.arange(n)), dtype=float)
        thickness_mm = (2.0 * max_dt + 1.0) * mm_per_px
        thin = thickness_mm < t_mm
        if not thin.any() or thin.all():
            return labels
        thin_px = thin[labels]
        idx = ndimage.distance_transform_edt(thin_px, return_distances=False, return_indices=True)
        out = labels[idx[0], idx[1]]
        _, inv = np.unique(out, return_inverse=True)
        return inv.reshape(out.shape).astype(np.int32)

    # ---- 5. fusão ---- #
    def _merge_regions(self, labels: np.ndarray, lab: np.ndarray, mm_per_px: float) -> np.ndarray:
        graph = RegionGraph(labels, lab)
        graph.merge_small(self.cfg.min_region_area_mm2 / mm_per_px ** 2)
        graph.merge_similar(self.cfg.color_tolerance, self.cfg.max_regions)
        roots = graph.roots()[labels]
        ids, counts = np.unique(roots, return_counts=True)
        order = ids[np.argsort(-counts, kind="stable")]     # região 0 = a maior
        remap = np.zeros(roots.max() + 1, dtype=np.int32)
        remap[order] = np.arange(len(order), dtype=np.int32)
        return remap[roots]

    # ---- 6. regiões, nomes e famílias ---- #
    def _build_regions(self, labels, rgb, mm_per_px) -> List[Region]:
        n = int(labels.max()) + 1
        flat = labels.ravel()
        area = np.bincount(flat, minlength=n).astype(float)
        h, w = labels.shape
        ys, xs = np.divmod(np.arange(h * w), w)
        cx = np.bincount(flat, weights=xs + 0.5, minlength=n) / area
        cy = np.bincount(flat, weights=ys + 0.5, minlength=n) / area
        mean_rgb = np.stack([np.bincount(flat, weights=rgb[..., c].ravel(), minlength=n) / area
                             for c in range(3)], axis=1)
        frame = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])).tolist())

        ignore_lab = rgb_to_lab(self.cfg.ignore_color) if self.cfg.ignore_color is not None else None
        regions = []
        for i in range(n):
            rgb_i = tuple(int(round(c)) for c in mean_rgb[i])
            ignored = ignore_lab is not None and \
                float(np.linalg.norm(rgb_to_lab(rgb_i) - ignore_lab)) < self.cfg.ignore_tolerance
            regions.append(Region(
                id=i, area_mm2=float(area[i] * mm_per_px ** 2), color_rgb=rgb_i,
                centroid_mm=(float(cx[i] * mm_per_px), float((h - cy[i]) * mm_per_px)),
                color_name=color_name(rgb_i), touches_frame=i in frame, ignored=ignored))
        return regions

    @staticmethod
    def _name_regions(regions: List[Region]) -> None:
        """Nome = número + cor ("03_verde"); com mais de uma região da mesma cor, ganha ordinal ("03_verde_2")."""
        count = {}
        for r in regions:
            count[r.color_name] = count.get(r.color_name, 0) + 1
        seen = {}
        for r in regions:
            seen[r.color_name] = seen.get(r.color_name, 0) + 1
            suffix = f"_{seen[r.color_name]}" if count[r.color_name] > 1 else ""
            r.name = f"{r.id:02d}_{slug(r.color_name)}{suffix}"

    def _build_families(self, regions: List[Region]) -> List[Family]:
        groups = group_families([r.color_rgb for r in regions], [r.area_mm2 for r in regions],
                                self.cfg.family_tolerance)
        families = []
        for fid, members in enumerate(groups):
            members.sort()
            big = max(members, key=lambda i: regions[i].area_mm2)
            fam = Family(id=fid, name=f"familia_{fid:02d}_{slug(regions[big].color_name)}",
                         region_ids=members, color_rgb=regions[big].color_rgb)
            families.append(fam)
            for i in members:
                regions[i].family = fid
        return families

    # ---- 7. fronteiras ---- #
    def _build_borders(self, pmap: PlanarMap) -> List[Chain]:
        cfg, mpp = self.cfg, pmap.mm_per_px
        h = pmap.labels.shape[0]
        chains = BorderTracer(pmap.labels, cfg.smooth_sigma_mm / mpp, cfg.simplify_tol_mm / mpp).trace()
        chains = contract_short(chains, mpp, cfg.min_border_length_mm)
        for ch in chains:
            outer = ch.label_a == -1
            if outer and not cfg.outer_frame:
                continue
            pmap.borders.append(Border(id=len(pmap.borders), region_a=ch.label_a, region_b=ch.label_b,
                                       points_mm=self._to_mm(ch.pts_px, mpp, h), closed=ch.closed, outer=outer))
        return chains

    @staticmethod
    def _to_mm(p: np.ndarray, mpp: float, h_px: int) -> np.ndarray:
        return np.stack([p[:, 0] * mpp, (h_px - p[:, 1]) * mpp], axis=1)

    @staticmethod
    def _name_borders(pmap: PlanarMap) -> None:
        for b in pmap.borders:
            b.name = f"F{b.id:02d}_" + ("moldura_r%02d" % b.region_b if b.outer else "r%02d_r%02d" % (b.region_a, b.region_b))

    # ---- 8. pontos ---- #
    def _build_points(self, pmap, chains, markers, original_px, work_px) -> List[InterestPoint]:
        cfg, mpp = self.cfg, pmap.mm_per_px
        W, H = pmap.size_mm
        h = pmap.labels.shape[0]
        out: List[InterestPoint] = []

        def add(classe, x, y, nome=None, regions=()):
            out.append(InterestPoint(id=len(out), xy_mm=(float(x), float(y)), classe=classe, nome=nome,
                                     regions=tuple(regions)))

        for classe, x_px, y_px in markers:                      # marcadores: pixels de trabalho
            add(classe, x_px * mpp, (h - y_px) * mpp)
        if cfg.points_file:
            for classe, nome, x, y in pts.load_points_file(cfg.points_file, (W, H), original_px):
                if 0 <= x <= W and 0 <= y <= H:
                    add(classe, x, y, nome)
                else:
                    self.warnings.append(f"ponto '{nome or classe}' fora da peça ({x:.1f}, {y:.1f} mm): ignorado")
        for x, y, regs in pts.junction_points(chains, lambda p: self._to_mm(p, mpp, h),
                                              cfg.triple_min_regions, cfg.triple_merge_dist_mm):
            add(pts.junction_class(len(regs)), x, y, regions=regs)
        return out
