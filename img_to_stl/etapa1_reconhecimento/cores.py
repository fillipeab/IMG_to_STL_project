"""Nomes de cor (paleta em Lab) e agrupamento em famílias ("regiões irmãs")."""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np

# Paleta simples em português. O nome de uma região é a cor mais próxima (em Lab) da sua cor média.
PALETA: Dict[str, Tuple[int, int, int]] = {
    "preto": (20, 20, 20), "cinza_escuro": (85, 85, 85), "cinza": (140, 140, 140),
    "cinza_claro": (200, 200, 200), "branco": (250, 250, 250),
    "vermelho": (220, 30, 30), "vinho": (120, 20, 40), "laranja": (245, 130, 20),
    "marrom": (120, 75, 35), "bege": (225, 200, 160), "amarelo": (250, 225, 30),
    "verde_claro": (150, 220, 110), "verde": (40, 160, 60), "verde_escuro": (20, 90, 40),
    "oliva": (125, 130, 40), "turquesa": (30, 190, 190), "azul_claro": (130, 190, 240),
    "azul": (30, 90, 220), "azul_marinho": (20, 35, 100), "roxo": (110, 50, 160),
    "lilas": (190, 160, 220), "rosa": (245, 150, 190), "magenta": (210, 30, 140),
}


def rgb_to_lab(rgb: Sequence[float]) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    return cv2.cvtColor(arr, cv2.COLOR_RGB2Lab).reshape(3)


_LAB = {n: rgb_to_lab(c) for n, c in PALETA.items()}


def color_name(rgb: Sequence[float]) -> str:
    lab = rgb_to_lab(rgb)
    return min(_LAB, key=lambda n: float(np.linalg.norm(_LAB[n] - lab)))


def group_families(colors_rgb: List[Tuple[int, int, int]], areas: List[float], tolerance: float) -> List[List[int]]:
    """Agrupa índices de regiões cujas cores diferem menos que `tolerance` (ΔE, Lab), em cadeia
    (união-busca). Retorna grupos ordenados pela área total decrescente."""
    n = len(colors_rgb)
    if tolerance <= 0 or n == 0:
        groups = [[i] for i in range(n)]
    else:
        lab = np.array([rgb_to_lab(c) for c in colors_rgb])
        parent = list(range(n))

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for i in range(n):
            for j in range(i + 1, n):
                if float(np.linalg.norm(lab[i] - lab[j])) < tolerance:
                    parent[find(i)] = find(j)
        buckets: Dict[int, List[int]] = {}
        for i in range(n):
            buckets.setdefault(find(i), []).append(i)
        groups = list(buckets.values())
    groups.sort(key=lambda g: -sum(areas[i] for i in g))
    return groups
