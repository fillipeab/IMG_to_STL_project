"""Biblioteca de texturas procedurais (campos de altura normalizados 0..1).

Cada textura é uma classe com `height(x, y)` (x, y em mm, arrays numpy) e é periódica com período
que divide 10 mm, então o tile de 10x10 mm repete sem emenda. As texturas são avaliadas em
coordenadas globais, então o padrão é contínuo entre regiões vizinhas.

Ids: 0 lisa | 1 linhas diagonais | 2 X's | 3 ondas | 4 escamas | 5 losangos | 6 pontos | 7 xadrez | 8 grade |
9 zigue-zague | 10 aneis | 11 tijolos | 12 colinas.
Para criar uma nova: herde de `Texture`, implemente `height` e use `TextureLibrary.register`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

SQRT2 = float(np.sqrt(2.0))


class RidgeProfile:
    """Altura normalizada (0..1) em função da distância `d` ao eixo do traço.

    - "triangular": flancos retos, ápice arredondado numa faixa de ±apex_round (parábola tangente).
    - "round": semicírculo.
    Como depende só da distância, as pontas dos traços viram cones com o mesmo perfil.
    """

    def __init__(self, kind: str = "triangular", apex_round: float = 0.1):
        if kind not in ("triangular", "round"):
            raise ValueError("kind deve ser 'triangular' ou 'round'")
        self.kind = kind
        self.apex_round = float(apex_round)

    def __call__(self, d, width: float):
        d = np.asarray(d, dtype=float)
        r = width / 2.0
        if self.kind == "round":
            return np.sqrt(np.clip(1.0 - (d / r) ** 2, 0.0, 1.0))
        e = max(min(self.apex_round, r), 1e-9)
        g = np.where(d >= e, d, d * d / (2.0 * e) + e / 2.0)
        h = (1.0 - g / r) / (1.0 - e / (2.0 * r))
        return np.clip(h, 0.0, 1.0)


def dist_to_segment(px, py, ax, ay, bx, by):
    """Distância de pontos (px, py) ao segmento A-B."""
    abx, aby = bx - ax, by - ay
    t = ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)
    t = np.clip(t, 0.0, 1.0)
    return np.hypot(px - (ax + t * abx), py - (ay + t * aby))


class Texture(ABC):
    texture_id: int = -1
    name: str = "textura"
    description: str = ""                   # uma linha, para a lista de texturas
    period_mm: float = 10.0  # o tile de 10 mm é periódico se este valor divide 10
    min_feature_mm: Optional[float] = None  # menor traço da textura (para avisar se ficar fino demais)

    def __init__(self, profile: Optional[RidgeProfile] = None):
        self.profile = profile or RidgeProfile()

    @abstractmethod
    def height(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Altura normalizada 0..1 nos pontos (x, y) em mm."""

    def __call__(self, x, y):
        return self.height(np.asarray(x, dtype=float), np.asarray(y, dtype=float))

    def tile(self, size: float = 10.0, res: float = 0.05) -> np.ndarray:
        """Rasteriza um tile `size` x `size` mm (para preview/edição)."""
        n = int(round(size / res))
        xs = (np.arange(n) + 0.5) * res
        X, Y = np.meshgrid(xs, xs)
        return self.height(X, Y)
