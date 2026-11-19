"""Parte 1 — visão computacional: imagem -> regiões, fronteiras e pontos.

Fluxo (classe `ImageReader`):
  1. carrega e reduz a imagem; filtro bilateral (suaviza ruído, preserva bordas)
  2. k-means em Lab (quantização de cor) + componentes conexos = regiões iniciais
  3. fusão: regiões pequenas -> vizinha mais parecida; vizinhas com ΔE < tolerância; e até caber
     em `max_regions` (sempre fundindo as mais parecidas)
  4. fronteiras: traçadas nas "frestas" entre pixels (topologia exata: regiões vizinhas dividem a
     MESMA curva), suavizadas e simplificadas
  5. pontos: de interesse (capitais etc.: ainda sem detecção; entram pela lista `PlanarMap.points`)
     e, opcionalmente (junction_points), de intersecção, onde 3+ regiões se encontram

Coordenadas do resultado: mm, x para a direita, y para cima, origem no canto inferior esquerdo.
"""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from scipy.spatial import cKDTree

from .config import VisionConfig


# --------------------------------------------------------------------------- #
# Modelos de dados
# --------------------------------------------------------------------------- #
@dataclass
class Region:
    id: int
    area_mm2: float
    color_rgb: Tuple[int, int, int]
    centroid_mm: Tuple[float, float]
    touches_frame: bool = False
    ignored: bool = False  # região "de fundo": fica sem textura


@dataclass
class Border:
    id: int
    region_a: int            # -1 = fora da peça (moldura)
    region_b: int
    points_mm: np.ndarray    # (N, 2)
    closed: bool = False
    outer: bool = False      # fronteira com o exterior (moldura da peça)

    @property
    def length_mm(self) -> float:
        d = np.diff(self.points_mm, axis=0)
        return float(np.hypot(d[:, 0], d[:, 1]).sum())


@dataclass
class InterestPoint:
    """Ponto de interesse marcado no mapa (ex.: capital). Ainda não é detectado na imagem:
    quem monta o `PlanarMap` preenche `points` (coordenadas em mm, y para cima, origem no canto
    inferior esquerdo, como em mapa.json)."""
    id: int
    xy_mm: Tuple[float, float]
    shape: Optional[str] = None   # "circle", "square" ou "triangle"; None = forma padrão da configuração
    name: Optional[str] = None
    regions: Tuple[int, ...] = ()  # só nos pontos de intersecção: regiões que se encontram ali

    @property
    def valence(self) -> int:
        """Nº de regiões que se encontram (0 para pontos de interesse comuns)."""
        return len(self.regions)


@dataclass
class PlanarMap:
    """Resultado da parte 1: as 3 coleções (regiões, fronteiras, pontos) + imagem de rótulos."""

    labels: np.ndarray                 # (H, W) int32, id da região de cada pixel
    mm_per_px: float
    regions: List[Region] = field(default_factory=list)
    borders: List[Border] = field(default_factory=list)
    points: List[InterestPoint] = field(default_factory=list)   # pontos de interesse (ver InterestPoint)
    outer_frame: bool = True

    @property
    def size_mm(self) -> Tuple[float, float]:
        h, w = self.labels.shape
        return w * self.mm_per_px, h * self.mm_per_px

    def label_at(self, x_mm, y_mm) -> np.ndarray:
        """Id da região em coordenadas do modelo (fora da imagem usa o pixel mais próximo)."""
        h, w = self.labels.shape
        ix = np.clip((np.asarray(x_mm) / self.mm_per_px).astype(int), 0, w - 1)
        iy = np.clip(((h * self.mm_per_px - np.asarray(y_mm)) / self.mm_per_px).astype(int), 0, h - 1)
        return self.labels[iy, ix]

    def region(self, region_id: int) -> Region:
        return self.regions[region_id]

    # ---- saída ---- #
    def summary(self) -> str:
        w, h = self.size_mm
        return (f"{len(self.regions)} regiões, {len(self.borders)} fronteiras "
                f"({sum(b.length_mm for b in self.borders):.0f} mm no total), "
                f"{len(self.points)} pontos; peça {w:.1f} x {h:.1f} mm")

    def to_dict(self, include_geometry: bool = False) -> dict:
        out = {
            "size_mm": list(self.size_mm),
            "mm_per_px": self.mm_per_px,
            "regions": [
                {"id": r.id, "area_mm2": round(r.area_mm2, 2), "color_rgb": list(r.color_rgb),
                 "centroid_mm": [round(c, 2) for c in r.centroid_mm],
                 "touches_frame": r.touches_frame, "ignored": r.ignored}
                for r in self.regions
            ],
            "borders": [],
            "points": [{"id": p.id, "xy_mm": [round(c, 3) for c in p.xy_mm],
                        "shape": p.shape, "name": p.name, "regions": list(p.regions)} for p in self.points],
        }
        for b in self.borders:
            item = {"id": b.id, "regions": [b.region_a, b.region_b], "length_mm": round(b.length_mm, 2),
                    "closed": b.closed, "outer": b.outer, "n_points": len(b.points_mm)}
            if include_geometry:
                item["points_mm"] = np.round(b.points_mm, 3).tolist()
            out["borders"].append(item)
        return out

    def save_json(self, path: str, include_geometry: bool = False) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(include_geometry), f, indent=2, ensure_ascii=False)

    def render_preview(self, path: str, max_side: int = 1400) -> None:
        """PNG com regiões coloridas (cor média), fronteiras, pontos e o id de cada região."""
        h, w = self.labels.shape
        lut = np.array([r.color_rgb for r in self.regions], dtype=np.uint8)
        img = lut[self.labels]
        scale = max(1.0, max_side / max(h, w))
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        img = np.ascontiguousarray(img[:, :, ::-1])  # RGB -> BGR p/ OpenCV

        def to_px(pts):
            pts = np.asarray(pts, dtype=float)
            return np.stack([pts[:, 0] / self.mm_per_px, h - pts[:, 1] / self.mm_per_px], 1) * scale

        for b in self.borders:
            p = np.round(to_px(b.points_mm)).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [p], b.closed, (20, 20, 20), max(1, int(round(scale))), cv2.LINE_AA)
        for pt in self.points:
            c = np.round(to_px([pt.xy_mm])[0]).astype(int)
            cv2.circle(img, tuple(int(v) for v in c), max(3, int(4 * scale)), (0, 0, 255), -1, cv2.LINE_AA)
        font_scale = max(0.5, 0.6 * scale * min(h, w) / 600)
        for r in self.regions:
            cx = int(r.centroid_mm[0] / self.mm_per_px * scale)
            cy = int((h - r.centroid_mm[1] / self.mm_per_px) * scale)
            txt = str(r.id)
            lum = 0.299 * r.color_rgb[0] + 0.587 * r.color_rgb[1] + 0.114 * r.color_rgb[2]
            col = (255, 255, 255) if lum < 128 else (0, 0, 0)
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            cv2.putText(img, txt, (cx - tw // 2, cy + th // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, col, 2, cv2.LINE_AA)
        cv2.imwrite(path, img)


# --------------------------------------------------------------------------- #
# Grafo de regiões (fusão)
# --------------------------------------------------------------------------- #
class RegionGraph:
    """Regiões + adjacência com fusão incremental (união de vizinhas)."""

    def __init__(self, labels: np.ndarray, lab: np.ndarray):
        n = int(labels.max()) + 1
        flat = labels.ravel()
        self.area = np.bincount(flat, minlength=n).astype(float)
        self.sum = np.stack(
            [np.bincount(flat, weights=lab[..., c].ravel(), minlength=n) for c in range(3)], axis=1)
        self.alive = np.ones(n, dtype=bool)
        self.version = np.zeros(n, dtype=np.int64)
        self.parent = np.arange(n)
        self.n_alive = n
        self.adj: List[Dict[int, int]] = [dict() for _ in range(n)]

        pairs = []
        for a, b in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
            m = a != b
            lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
            pairs.append(lo.astype(np.int64) * n + hi)
        if pairs:
            keys, counts = np.unique(np.concatenate(pairs), return_counts=True)
            for k, c in zip(keys.tolist(), counts.tolist()):
                a, b = divmod(k, n)
                self.adj[a][b] = c
                self.adj[b][a] = c

    def mean(self, i: int) -> np.ndarray:
        return self.sum[i] / self.area[i]

    def delta(self, i: int, j: int) -> float:
        return float(np.linalg.norm(self.mean(i) - self.mean(j)))

    def merge(self, a: int, b: int) -> None:
        """Funde a região `a` dentro de `b`."""
        for nb, cnt in self.adj[a].items():
            if nb == b:
                continue
            self.adj[nb].pop(a, None)
            self.adj[nb][b] = self.adj[nb].get(b, 0) + cnt
            self.adj[b][nb] = self.adj[b].get(nb, 0) + cnt
        self.adj[b].pop(a, None)
        self.adj[a] = {}
        self.alive[a] = False
        self.parent[a] = b
        self.area[b] += self.area[a]
        self.sum[b] += self.sum[a]
        self.version[b] += 1
        self.n_alive -= 1

    def merge_small(self, min_area_px: float) -> None:
        """Absorve regiões menores que min_area_px na vizinha de cor mais próxima."""
        heap = [(self.area[i], i) for i in range(len(self.area)) if self.alive[i]]
        heapq.heapify(heap)
        while heap:
            area, i = heapq.heappop(heap)
            if not self.alive[i] or area != self.area[i]:
                continue
            if area >= min_area_px:
                break
            if not self.adj[i]:
                continue
            best = min(self.adj[i], key=lambda j: (self.delta(i, j), -self.adj[i][j]))
            self.merge(i, best)
            heapq.heappush(heap, (self.area[best], best))

    def merge_similar(self, tolerance: float, max_regions: int) -> None:
        """Funde as vizinhas mais parecidas enquanto ΔE < tolerância OU houver regiões demais."""
        heap = []

        def push(a, b):
            heapq.heappush(heap, (self.delta(a, b), a, b, self.version[a], self.version[b]))

        for a in range(len(self.adj)):
            if self.alive[a]:
                for b in self.adj[a]:
                    if a < b:
                        push(a, b)
        while heap:
            d, a, b, va, vb = heapq.heappop(heap)
            if not (self.alive[a] and self.alive[b]) or self.version[a] != va or self.version[b] != vb:
                continue
            if d >= tolerance and self.n_alive <= max_regions:
                break
            small, big = (a, b) if self.area[a] <= self.area[b] else (b, a)
            self.merge(small, big)
            for nb in self.adj[big]:
                push(min(big, nb), max(big, nb))

    def roots(self) -> np.ndarray:
        """Para cada id original, o id da região em que foi fundida."""
        root = self.parent.copy()
        for i in range(len(root)):
            r = i
            while root[r] != r:
                r = root[r]
            j = i
            while root[j] != r:
                root[j], j = r, root[j]
        return root


# --------------------------------------------------------------------------- #
# Traçado das fronteiras
# --------------------------------------------------------------------------- #
@dataclass
class Chain:
    label_a: int
    label_b: int
    pts_px: np.ndarray  # (N, 2) em px da imagem (x, y com y para baixo)
    closed: bool


class BorderTracer:
    """Extrai fronteiras como cadeias de "frestas" entre pixels.

    Cada fresta separa dois pixels de rótulos diferentes; os vértices são cantos de pixel.
    Vértices de grau 2 pertencem ao meio de uma cadeia; grau 3+ são junções da rede de fronteiras.
    Como duas regiões vizinhas usam a mesma cadeia, não há frestas nem sobreposições.
    """

    def __init__(self, labels: np.ndarray, smooth_sigma_px: float, simplify_tol_px: float):
        self.labels = labels
        self.sigma = smooth_sigma_px
        self.tol = simplify_tol_px

    def trace(self) -> List[Chain]:
        """Retorna as cadeias de fronteira (entre vértices de grau != 2)."""
        P = np.pad(self.labels, 1, constant_values=-1)
        Hp, Wp = P.shape
        Wv = Wp + 1

        ks, js = np.nonzero(P[1:, :] != P[:-1, :])            # fresta horizontal entre linhas k e k+1
        hu, hv = (ks + 1) * Wv + js, (ks + 1) * Wv + js + 1
        ha, hb = P[ks, js], P[ks + 1, js]
        is_, ks2 = np.nonzero(P[:, 1:] != P[:, :-1])          # fresta vertical entre colunas k e k+1
        vu, vv = is_ * Wv + ks2 + 1, (is_ + 1) * Wv + ks2 + 1
        va, vb = P[is_, ks2], P[is_, ks2 + 1]

        u = np.concatenate([hu, vu])
        v = np.concatenate([hv, vv])
        lo = np.minimum(np.concatenate([ha, va]), np.concatenate([hb, vb]))
        hi = np.maximum(np.concatenate([ha, va]), np.concatenate([hb, vb]))
        n_edges = len(u)
        n_vert = (Hp + 1) * Wv
        if n_edges == 0:
            return []

        ends = np.concatenate([u, v])
        eids = np.concatenate([np.arange(n_edges), np.arange(n_edges)])
        order = np.argsort(ends, kind="stable")
        seid = eids[order]
        deg = np.bincount(ends, minlength=n_vert)
        ptr = np.zeros(n_vert + 1, dtype=np.int64)
        ptr[1:] = np.cumsum(deg)

        # --- cadeias ---
        ul, vl, lol, hil = u.tolist(), v.tolist(), lo.tolist(), hi.tolist()
        degl, ptrl, seidl = deg.tolist(), ptr.tolist(), seid.tolist()
        visited = bytearray(n_edges)
        chains: List[Chain] = []

        def walk(start: int, e: int) -> None:
            ids = [start]
            cur, first = start, e
            while True:
                visited[e] = 1
                nxt = vl[e] if ul[e] == cur else ul[e]
                ids.append(nxt)
                if degl[nxt] != 2 or nxt == start:
                    break
                a = ptrl[nxt]
                e1, e2 = seidl[a], seidl[a + 1]
                e = e2 if e1 == e else e1
                if visited[e]:
                    break
                cur = nxt
            arr = np.asarray(ids)
            pts = np.stack([(arr % Wv) - 1, (arr // Wv) - 1], axis=1).astype(float)
            # laço que começa numa junção (grau >= 3) NÃO é um laço livre: as pontas precisam ficar
            # fixas na junção, senão a suavização abre uma fresta no cordão
            closed = ids[0] == ids[-1] and degl[start] == 2
            chains.append(self._refine(Chain(lol[first], hil[first], pts, closed)))

        for x in np.nonzero((deg != 2) & (deg > 0))[0].tolist():
            for k in range(ptrl[x], ptrl[x + 1]):
                if not visited[seidl[k]]:
                    walk(x, seidl[k])
        for e in range(n_edges):          # laços fechados sem junção (ilhas)
            if not visited[e]:
                walk(ul[e], e)
        return chains

    def _refine(self, ch: Chain) -> Chain:
        """Suaviza (remove a 'escada') mantendo as pontas fixas e simplifica (Douglas-Peucker)."""
        pts = ch.pts_px
        sigma = 0.0 if ch.label_a == -1 else self.sigma   # moldura externa: mantém cantos retos
        if ch.closed:
            core = pts[:-1]
            if len(core) >= 8 and sigma > 0:
                core = np.stack([ndimage.gaussian_filter1d(core[:, c], sigma, mode="wrap")
                                 for c in range(2)], axis=1)
            simp = cv2.approxPolyDP(core.astype(np.float32).reshape(-1, 1, 2), self.tol, True)
            simp = simp.reshape(-1, 2).astype(float)
            simp = np.vstack([simp, simp[:1]])
        else:
            core = pts
            if len(core) >= 6 and sigma > 0:
                sm = np.stack([ndimage.gaussian_filter1d(core[:, c], sigma, mode="nearest")
                               for c in range(2)], axis=1)
                sm[0], sm[-1] = core[0], core[-1]
                core = sm
            simp = cv2.approxPolyDP(core.astype(np.float32).reshape(-1, 1, 2), self.tol, False)
            simp = simp.reshape(-1, 2).astype(float)
        return Chain(ch.label_a, ch.label_b, simp, ch.closed)


# --------------------------------------------------------------------------- #
# Leitor
# --------------------------------------------------------------------------- #
class ImageReader:
    """Converte uma imagem em `PlanarMap` (regiões, fronteiras e pontos)."""

    def __init__(self, config: Optional[VisionConfig] = None):
        self.cfg = config or VisionConfig()

    # ---- API ---- #
    def read(self, image_path: str) -> PlanarMap:
        rgb = self._load(image_path)
        h, w = rgb.shape[:2]
        mm_per_px = self.cfg.width_mm / w
        rgb = self._denoise(rgb)
        lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)

        labels = self._initial_segmentation(lab)
        labels = self._remove_thin(labels, mm_per_px)
        labels = self._merge_regions(labels, lab, mm_per_px)
        pmap = PlanarMap(labels=labels, mm_per_px=mm_per_px, outer_frame=self.cfg.outer_frame)
        pmap.regions = self._build_regions(labels, rgb, lab, mm_per_px)
        self._build_borders_and_points(pmap)
        return pmap

    # ---- 1. carga e filtro ---- #
    def _load(self, path: str) -> np.ndarray:
        img = ImageOps.exif_transpose(Image.open(path))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, img)
        rgb = np.asarray(img.convert("RGB"))
        scale = min(1.0, self.cfg.work_max_px / max(rgb.shape[:2]))
        if scale < 1.0:
            rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return rgb

    def _denoise(self, rgb: np.ndarray) -> np.ndarray:
        for _ in range(self.cfg.denoise_iterations):
            rgb = cv2.bilateralFilter(rgb, 9, self.cfg.denoise_sigma_color, self.cfg.denoise_sigma_space)
        return rgb

    # ---- 2. regiões iniciais ---- #
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
                labels[cc > 0] = cc[cc > 0] + offset - 1 + 0
                offset += n
        return labels

    # ---- 2b. estruturas finas (contornos pretos, serrilhado, texto) ---- #
    def _remove_thin(self, labels: np.ndarray, mm_per_px: float) -> np.ndarray:
        """Apaga componentes mais finos que `min_region_thickness_mm` e preenche o espaço com o
        rótulo vizinho mais próximo. Traços de contorno (ex.: linhas pretas de um mapa) e o
        serrilhado entre duas cores deixam de virar "regiões" próprias; a fronteira passa pelo
        meio do traço e fica contínua."""
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
        _, inv = np.unique(out, return_inverse=True)           # ids contínuos 0..n-1
        return inv.reshape(out.shape).astype(np.int32)

    # ---- 3. fusão ---- #
    def _merge_regions(self, labels: np.ndarray, lab: np.ndarray, mm_per_px: float) -> np.ndarray:
        graph = RegionGraph(labels, lab)
        graph.merge_small(self.cfg.min_region_area_mm2 / mm_per_px ** 2)
        graph.merge_similar(self.cfg.color_tolerance, self.cfg.max_regions)
        roots = graph.roots()[labels]
        # reindexa 0..R-1 por área decrescente (a maior região é a 0)
        ids, counts = np.unique(roots, return_counts=True)
        order = ids[np.argsort(-counts, kind="stable")]
        remap = np.zeros(roots.max() + 1, dtype=np.int32)
        remap[order] = np.arange(len(order), dtype=np.int32)
        return remap[roots]

    def _build_regions(self, labels, rgb, lab, mm_per_px) -> List[Region]:
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

        ignore_lab = None
        if self.cfg.ignore_color is not None:
            ic = np.array(self.cfg.ignore_color, dtype=np.float32).reshape(1, 1, 3) / 255.0
            ignore_lab = cv2.cvtColor(ic, cv2.COLOR_RGB2Lab).reshape(3)
        regions = []
        for i in range(n):
            rgb_i = tuple(int(round(c)) for c in mean_rgb[i])
            ignored = False
            if ignore_lab is not None:
                lab_i = cv2.cvtColor(np.array(rgb_i, np.float32).reshape(1, 1, 3) / 255.0, cv2.COLOR_RGB2Lab).reshape(3)
                ignored = float(np.linalg.norm(lab_i - ignore_lab)) < self.cfg.ignore_tolerance
            regions.append(Region(
                id=i, area_mm2=float(area[i] * mm_per_px ** 2), color_rgb=rgb_i,
                centroid_mm=(float(cx[i] * mm_per_px), float((h - cy[i]) * mm_per_px)),
                touches_frame=i in frame, ignored=ignored))
        return regions

    # ---- 4/5. fronteiras e pontos ---- #
    def _build_borders_and_points(self, pmap: PlanarMap) -> None:
        cfg, mpp = self.cfg, pmap.mm_per_px
        h = pmap.labels.shape[0]
        tracer = BorderTracer(pmap.labels, cfg.smooth_sigma_mm / mpp, cfg.simplify_tol_mm / mpp)
        chains = tracer.trace()
        chains = self._contract_short(chains, mpp)

        def to_mm(p):
            return np.stack([p[:, 0] * mpp, (h - p[:, 1]) * mpp], axis=1)

        for ch in chains:
            outer = ch.label_a == -1
            if outer and not cfg.outer_frame:
                continue
            pmap.borders.append(Border(id=len(pmap.borders), region_a=ch.label_a, region_b=ch.label_b,
                                       points_mm=to_mm(ch.pts_px), closed=ch.closed, outer=outer))
        if cfg.junction_points:
            pmap.points = self._build_points(chains, to_mm)

    def _contract_short(self, chains: List[Chain], mpp: float) -> List[Chain]:
        """Garante fronteiras contínuas. Uma fronteira curta entre duas junções NÃO é apagada (abriria
        uma fresta na rede): ela é "encolhida" — as duas junções viram uma só, no meio, e as demais
        fronteiras passam a terminar ali. Só somem laços livres curtos (ilhotas) e laços curtos presos
        a uma única junção."""
        min_px = self.cfg.min_border_length_mm / mpp
        if min_px <= 0:
            return chains

        def length(c: Chain) -> float:
            d = np.diff(c.pts_px, axis=0)
            return float(np.hypot(d[:, 0], d[:, 1]).sum())

        def key(p) -> Tuple[int, int]:
            return int(round(p[0])), int(round(p[1]))

        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        members: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}

        def find(a):
            parent.setdefault(a, a)
            members.setdefault(a, [a])
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def extent(vs) -> float:
            xy = np.array(vs, dtype=float)
            return float(np.hypot(*(xy.max(axis=0) - xy.min(axis=0))))

        drop = set()
        short = sorted((i for i, c in enumerate(chains) if c.label_a != -1 and length(c) < min_px),
                       key=lambda i: length(chains[i]))
        for i in short:
            c = chains[i]
            if c.closed or key(c.pts_px[0]) == key(c.pts_px[-1]):
                drop.add(i)                                   # ilhota / laço curto preso a uma junção
                continue
            ra, rb = find(key(c.pts_px[0])), find(key(c.pts_px[-1]))
            if ra == rb:
                drop.add(i)
                continue
            if extent(members[ra] + members[rb]) <= min_px:   # evita colapsar uma curva longa
                parent[rb] = ra
                members[ra] += members.pop(rb)
                drop.add(i)

        centre = {r: np.mean(np.array(v, dtype=float), axis=0) for r, v in members.items() if len(v) > 1}
        out = []
        for i, c in enumerate(chains):
            if i in drop:
                continue
            if not c.closed:
                pts = c.pts_px.copy()
                for end in (0, -1):
                    r = find(key(pts[end])) if key(pts[end]) in parent else None
                    if r is not None and r in centre:
                        pts[end] = centre[r]
                c = Chain(c.label_a, c.label_b, pts, c.closed)
            out.append(c)
        return out

    def _build_points(self, chains: List[Chain], to_mm) -> List[InterestPoint]:
        """Pontos de intersecção = vértices da rede de fronteiras onde se encontram
        >= min_regions_at_point regiões (a moldura externa não conta como região)."""
        cfg = self.cfg
        verts: Dict[Tuple[float, float], set] = {}
        for c in chains:
            if c.closed:
                continue
            for end in (0, -1):
                k = (round(float(c.pts_px[end][0]), 3), round(float(c.pts_px[end][1]), 3))
                verts.setdefault(k, set()).update(r for r in (c.label_a, c.label_b) if r >= 0)
        cand = [(k, r) for k, r in verts.items() if len(r) >= cfg.min_regions_at_point]
        if not cand:
            return []
        xy = to_mm(np.array([k for k, _ in cand], dtype=float))
        regs = [tuple(sorted(r)) for _, r in cand]

        # agrupa junções muito próximas (ex.: 4 regiões que se encontram quase no mesmo lugar)
        parent = list(range(len(xy)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for a, b in cKDTree(xy).query_pairs(cfg.point_merge_dist_mm):
            parent[find(a)] = find(b)
        groups: Dict[int, List[int]] = {}
        for i in range(len(xy)):
            groups.setdefault(find(i), []).append(i)

        points = []
        for members in groups.values():
            c = xy[members].mean(axis=0)
            rset = tuple(sorted(set(r for m in members for r in regs[m])))
            points.append((len(rset), float(c[0]), float(c[1]), rset))
        points.sort(key=lambda t: (-t[0], t[2], t[1]))
        if cfg.max_points is not None:
            points = points[: cfg.max_points]
        return [InterestPoint(id=i, xy_mm=(p[1], p[2]), regions=p[3]) for i, p in enumerate(points)]
