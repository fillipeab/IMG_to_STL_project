"""Camada intermediária de distorção: transforma as COORDENADAS antes de avaliar a textura.

    altura(x, y) = textura( T⁻¹ (x - offset, y - offset) )

Funciona com qualquer textura (procedural ou importada do CAD), pois só mexe nas coordenadas.

Ordem da transformação visual (o que você vê no resultado):
  cisalhar -> esticar ao longo de um ângulo -> ampliar/reduzir -> girar -> (ondulação opcional)
Como a transformação é geométrica, a largura dos traços também muda (esticar 2x numa direção
engrossa os traços 2x nessa direção). Para manter a largura do traço e mudar só o espaçamento,
ajuste os parâmetros da própria textura (pitch, cell, diag_x...) em `texture_params`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .base import Texture


def _rot(deg: float) -> np.ndarray:
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s], [s, c]])


@dataclass
class TextureTransform:
    scale: float = 1.0                       # >1 amplia, <1 reduz
    stretch: float = 1.0                     # fator de esticamento ao longo de stretch_angle_deg (>1 alonga)
    stretch_angle_deg: float = 0.0           # direção do esticamento (0 = eixo x)
    shear: float = 0.0                       # cisalhamento: x += shear * y
    rotation_deg: float = 0.0                # gira o padrão (anti-horário)
    offset_mm: Tuple[float, float] = (0.0, 0.0)
    warp_amplitude_mm: float = 0.0           # ondulação do padrão (0 = desligada)
    warp_wavelength_mm: float = 20.0

    _KEYS = ("scale", "stretch", "stretch_angle_deg", "shear", "rotation_deg", "offset_mm",
             "warp_amplitude_mm", "warp_wavelength_mm")

    def __post_init__(self):
        if self.scale <= 0 or self.stretch <= 0 or self.warp_wavelength_mm <= 0:
            raise ValueError("scale, stretch e warp_wavelength_mm devem ser > 0")
        self.offset_mm = tuple(float(v) for v in self.offset_mm)

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> "TextureTransform":
        return cls(**{k: spec[k] for k in cls._KEYS if k in spec})

    def visual_matrix(self) -> np.ndarray:
        stretch = _rot(self.stretch_angle_deg) @ np.diag([self.stretch, 1.0]) @ _rot(-self.stretch_angle_deg)
        shear = np.array([[1.0, self.shear], [0.0, 1.0]])
        return _rot(self.rotation_deg) @ (self.scale * stretch @ shear)

    def is_identity(self) -> bool:
        return self == TextureTransform()

    def min_magnification(self) -> float:
        """Menor ampliação em qualquer direção (para checar se os detalhes ficam finos demais)."""
        return float(np.linalg.svd(self.visual_matrix(), compute_uv=False).min())

    def apply(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Coordenadas do mundo (mm) -> coordenadas da textura."""
        px, py = x - self.offset_mm[0], y - self.offset_mm[1]
        if self.warp_amplitude_mm:
            k = 2.0 * np.pi / self.warp_wavelength_mm
            px, py = (px + self.warp_amplitude_mm * np.sin(k * py),
                      py + self.warp_amplitude_mm * np.sin(k * px))
        inv = np.linalg.inv(self.visual_matrix())
        return inv[0, 0] * px + inv[0, 1] * py, inv[1, 0] * px + inv[1, 1] * py


class TransformedTexture(Texture):
    """Envolve qualquer `Texture` aplicando uma `TextureTransform` às coordenadas."""

    def __init__(self, base: Texture, transform: TextureTransform):
        super().__init__(base.profile)
        self.base, self.transform = base, transform
        self.texture_id, self.name = base.texture_id, base.name
        self.period_mm = base.period_mm
        mf = base.min_feature_mm
        self.min_feature_mm: Optional[float] = None if mf is None else mf * transform.min_magnification()

    def height(self, x, y):
        qx, qy = self.transform.apply(x, y)
        return self.base.height(qx, qy)
