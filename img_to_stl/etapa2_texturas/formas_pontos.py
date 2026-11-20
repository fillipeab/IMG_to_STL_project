"""Formas dos pontos (círculo, quadrado, triângulo) como campos de distância com sinal (SDF)."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

SQRT3 = float(np.sqrt(3.0))


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
