"""Texturas internas 6–12. Todas periódicas num período que divide 10 mm (o tile de 10 mm fecha sem emenda).

6 pontos · 7 xadrez · 8 grade · 9 zigue-zague · 10 aneis · 11 tijolos · 12 colinas
Cada uma tem parâmetros próprios, ajustáveis em `texture_params` (ex.: {"6": {"pitch": 5.0}}).
"""
from __future__ import annotations

import numpy as np

from .base import Texture
from .registro import TextureLibrary


def _wrap(t, period):
    """Resto centrado: valor em [-period/2, period/2)."""
    return np.mod(t + period / 2.0, period) - period / 2.0


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class DotsTexture(Texture):
    """Textura 6: pontos (cúpulas) numa grade quadrada.

    pitch: distância entre centros (mm; deve dividir 10). diameter: diâmetro da base da cúpula."""

    texture_id = 6
    name = "pontos"
    description = "cúpulas pequenas em grade"

    def __init__(self, pitch: float = 2.5, diameter: float = 1.6, profile=None):
        super().__init__(profile)
        self.pitch, self.diameter = pitch, diameter
        self.period_mm = pitch
        self.min_feature_mm = diameter

    def height(self, x, y):
        r = np.hypot(_wrap(x, self.pitch), _wrap(y, self.pitch))
        return self.profile(r, self.diameter)


class CheckerTexture(Texture):
    """Textura 7: xadrez em relevo (quadrados altos e baixos, com rampa suave entre eles).

    cell: lado do quadrado (mm; 2*cell deve dividir 10: 1.25, 2.5, 5). bevel: largura da rampa (mm)."""

    texture_id = 7
    name = "xadrez"
    description = "quadrados altos e baixos alternados"

    def __init__(self, cell: float = 2.5, bevel: float = 0.4, profile=None):
        super().__init__(profile)
        self.cell, self.bevel = cell, max(bevel, 1e-6)
        self.period_mm = 2 * cell
        self.min_feature_mm = cell

    def height(self, x, y):
        c = self.cell
        iu, iv = np.floor(x / c), np.floor(y / c)
        high = np.mod(iu + iv, 2) == 0
        u, v = np.mod(x, c), np.mod(y, c)
        d = np.minimum(np.minimum(u, c - u), np.minimum(v, c - v))      # distância à borda do quadrado
        ramp = 0.5 * _smooth(d / self.bevel)
        return np.where(high, 0.5 + ramp, 0.5 - ramp)


class GridTexture(Texture):
    """Textura 8: grade (traços horizontais e verticais cruzados).

    pitch: espaçamento (mm; divide 10). width: largura da base do traço."""

    texture_id = 8
    name = "grade"
    description = "traços cruzados na horizontal e vertical"

    def __init__(self, pitch: float = 2.5, width: float = 0.8, profile=None):
        super().__init__(profile)
        self.pitch, self.width = pitch, width
        self.period_mm = pitch
        self.min_feature_mm = width

    def height(self, x, y):
        a = self.profile(np.abs(_wrap(x, self.pitch)), self.width)
        b = self.profile(np.abs(_wrap(y, self.pitch)), self.width)
        return np.maximum(a, b)


class ZigzagTexture(Texture):
    """Textura 9: traços em zigue-zague (espinha), na horizontal.

    pitch: espaçamento entre traços (mm; divide 10). amp: amplitude do zigue-zague (mm).
    period: comprimento de cada "V" em x (mm; divide 10). width: largura da base do traço."""

    texture_id = 9
    name = "zigue-zague"
    description = "traços em V, como espinha de peixe"

    def __init__(self, pitch: float = 2.5, amp: float = 1.25, period: float = 5.0, width: float = 0.8, profile=None):
        super().__init__(profile)
        self.pitch, self.amp, self.period, self.width = pitch, amp, period, width
        self.period_mm = max(pitch, period)
        self.min_feature_mm = width

    def height(self, x, y):
        t = _wrap(x, self.period)
        tri = self.amp * (4.0 * np.abs(t) / self.period - 1.0)           # onda triangular em [-amp, amp]
        slope = 4.0 * self.amp / self.period
        d = np.abs(_wrap(y - tri, self.pitch)) / np.sqrt(1.0 + slope ** 2)   # distância ao traço (perpendicular)
        return self.profile(d, self.width)


class RingsTexture(Texture):
    """Textura 10: anéis concêntricos com um ponto no centro ("alvo"), um por célula.

    cell: lado da célula (mm; divide 10). radius: raio do anel (mm). width: largura do traço."""

    texture_id = 10
    name = "aneis"
    description = "anéis concêntricos com ponto central"

    def __init__(self, cell: float = 5.0, radius: float = 1.4, width: float = 0.8, profile=None):
        super().__init__(profile)
        self.cell, self.radius, self.width = cell, radius, width
        self.period_mm = cell
        self.min_feature_mm = width

    def height(self, x, y):
        r = np.hypot(_wrap(x, self.cell), _wrap(y, self.cell))
        ring = self.profile(np.abs(r - self.radius), self.width)
        dot = self.profile(r, self.width)
        return np.maximum(ring, dot)


class BricksTexture(Texture):
    """Textura 11: tijolos (blocos altos com argamassa rebaixada), fileiras desencontradas.

    brick_w x brick_h: tamanho do tijolo (mm; brick_w divide 10 e 2*brick_h divide 10).
    mortar: largura da argamassa. bevel: rampa entre argamassa e tijolo."""

    texture_id = 11
    name = "tijolos"
    description = "tijolos em fileiras desencontradas"

    def __init__(self, brick_w: float = 5.0, brick_h: float = 2.5, mortar: float = 0.8, bevel: float = 0.3, profile=None):
        super().__init__(profile)
        self.bw, self.bh, self.mortar, self.bevel = brick_w, brick_h, mortar, max(bevel, 1e-6)
        self.period_mm = max(brick_w, 2 * brick_h)
        self.min_feature_mm = mortar

    def height(self, x, y):
        row = np.floor(y / self.bh)
        xs = x + np.mod(row, 2) * (self.bw / 2.0)
        u, v = np.mod(xs, self.bw), np.mod(y, self.bh)
        d = np.minimum(np.minimum(u, self.bw - u), np.minimum(v, self.bh - v))
        return _smooth((d - self.mortar / 2.0) / self.bevel)


class HillsTexture(Texture):
    """Textura 12: colinas suaves (ondulado cruzado, "caixa de ovos"). Sem arestas vivas.

    period: distância entre cristas (mm; divide 10)."""

    texture_id = 12
    name = "colinas"
    description = "ondulado suave nos dois sentidos"

    def __init__(self, period: float = 5.0, profile=None):
        super().__init__(profile)
        self.period = period
        self.period_mm = period

    def height(self, x, y):
        k = 2.0 * np.pi / self.period
        return (np.cos(k * x) + np.cos(k * y) + 2.0) / 4.0


for _k in (DotsTexture, CheckerTexture, GridTexture, ZigzagTexture, RingsTexture, BricksTexture, HillsTexture):
    TextureLibrary.register(_k)
