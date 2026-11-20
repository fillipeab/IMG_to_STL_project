"""Pontos: tríplices (encontro de 3+ regiões) e de interesse por classe (marcadores na imagem ou arquivo)."""
from __future__ import annotations

import csv
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .cores import rgb_to_lab
from .fronteiras import Chain
from .modelos import CLASSE_MULTIPLO, CLASSE_TRIPLICE, InterestPoint


# --------------------------------------------------------------------------- #
# Pontos tríplices / múltiplos
# --------------------------------------------------------------------------- #
def junction_points(chains: List[Chain], to_mm, min_regions: int, merge_dist_mm: float) -> List[Tuple[float, float, Tuple[int, ...]]]:
    """Vértices da rede de fronteiras onde se encontram >= min_regions regiões (a moldura externa
    não conta como região). Junções muito próximas viram uma só. Retorna (x_mm, y_mm, regiões)."""
    verts: Dict[Tuple[float, float], set] = {}
    for c in chains:
        if c.closed:
            continue
        for end in (0, -1):
            k = (round(float(c.pts_px[end][0]), 3), round(float(c.pts_px[end][1]), 3))
            verts.setdefault(k, set()).update(r for r in (c.label_a, c.label_b) if r >= 0)
    cand = [(k, r) for k, r in verts.items() if len(r) >= min_regions]
    if not cand:
        return []
    xy = to_mm(np.array([k for k, _ in cand], dtype=float))
    regs = [tuple(sorted(r)) for _, r in cand]

    parent = list(range(len(xy)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in cKDTree(xy).query_pairs(merge_dist_mm):
        parent[find(a)] = find(b)
    groups: Dict[int, List[int]] = {}
    for i in range(len(xy)):
        groups.setdefault(find(i), []).append(i)

    out = []
    for members in groups.values():
        c = xy[members].mean(axis=0)
        rset = tuple(sorted(set(r for m in members for r in regs[m])))
        out.append((float(c[0]), float(c[1]), rset))
    out.sort(key=lambda t: (-len(t[2]), t[1], t[0]))
    return out


def junction_class(n_regions: int) -> str:
    return CLASSE_TRIPLICE if n_regions == 3 else CLASSE_MULTIPLO


# --------------------------------------------------------------------------- #
# Pontos de interesse: marcadores coloridos na imagem
# --------------------------------------------------------------------------- #
def detect_markers(rgb: np.ndarray, markers: Sequence[Dict[str, Any]], mm_per_px: float,
                   max_area_mm2: float) -> Tuple[List[Tuple[str, float, float]], np.ndarray]:
    """Acha bolinhas da cor de cada marcador. Retorna ([(classe, x_px, y_px)], máscara a apagar).
    `rgb` é a imagem de trabalho (altura x largura x 3, uint8); x_px,y_px no centro do marcador."""
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)
    erase = np.zeros(rgb.shape[:2], np.uint8)
    found: List[Tuple[str, float, float]] = []
    max_px = max_area_mm2 / mm_per_px ** 2
    for m in markers:
        target = rgb_to_lab(m["cor"])
        tol = float(m.get("tolerancia", 30.0))
        mask = (np.linalg.norm(lab - target, axis=2) < tol).astype(np.uint8)
        n, comp, stats, cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if 2 <= area <= max_px:
                found.append((str(m.get("classe", "ponto")), float(cent[i][0]), float(cent[i][1])))
                erase[comp == i] = 255
    if erase.any():
        erase = cv2.dilate(erase, np.ones((5, 5), np.uint8))
    return found, erase


def inpaint(rgb: np.ndarray, erase: np.ndarray) -> np.ndarray:
    """Apaga os marcadores preenchendo com a vizinhança (para não virarem regiões)."""
    if not erase.any():
        return rgb
    return cv2.inpaint(rgb, erase, 3, cv2.INPAINT_TELEA)


# --------------------------------------------------------------------------- #
# Pontos de interesse: arquivo .json / .csv
# --------------------------------------------------------------------------- #
def load_points_file(path: str, size_mm: Tuple[float, float],
                     image_size_px: Tuple[int, int]) -> List[Tuple[str, Optional[str], float, float]]:
    """Lê (classe, nome, x_mm, y_mm). Aceita x_px/y_px (pixels da imagem ORIGINAL, origem no canto
    superior esquerdo) ou x_mm/y_mm (mm da peça, origem no canto inferior esquerdo)."""
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data["pontos"] if isinstance(data, dict) else data
    W, H = size_mm
    w0, h0 = image_size_px
    out = []
    for r in rows:
        classe = str(r.get("classe") or "ponto")
        nome = r.get("nome") or None
        if r.get("x_mm") not in (None, "") and r.get("y_mm") not in (None, ""):
            x, y = float(r["x_mm"]), float(r["y_mm"])
        elif r.get("x_px") not in (None, "") and r.get("y_px") not in (None, ""):
            x, y = float(r["x_px"]) / w0 * W, H - float(r["y_px"]) / h0 * H
        else:
            raise ValueError(f"Ponto sem coordenadas em {path}: {r}")
        out.append((classe, nome, x, y))
    return out
