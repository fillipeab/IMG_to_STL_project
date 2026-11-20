"""Texturas internas 0–5: lisa, linhas diagonais, X's, ondas, escamas e losangos (as novas estão em padroes_extra.py)."""
from __future__ import annotations

from typing import Optional

import numpy as np

from .base import SQRT2, RidgeProfile, Texture, dist_to_segment
from .registro import TextureLibrary


class FlatTexture(Texture):
    """Textura 0: nenhuma."""

    texture_id = 0
    name = "lisa"
    description = "sem relevo: superfície lisa"

    def height(self, x, y):
        return np.zeros_like(x, dtype=float)


class DiagonalLinesTexture(Texture):
    """Textura 1: linhas diagonais a 45°.

    pitch: espaçamento medido ao longo de x (ou y). O espaçamento perpendicular é pitch/√2.
           Precisa dividir 10 mm para o tile fechar (2, 2.5, 5, 10...).
    width: largura da base do traço.
    direction: +1 => "\\", -1 => "/".
    """

    texture_id = 1
    name = "linhas diagonais"
    description = "linhas diagonais a 45°"

    def __init__(self, pitch: float = 2.5, width: float = 0.8, direction: int = -1, profile=None):
        super().__init__(profile)
        self.pitch, self.width, self.direction = pitch, width, 1 if direction >= 0 else -1
        self.period_mm = pitch
        self.min_feature_mm = width

    def height(self, x, y):
        u = (x + self.direction * y) / SQRT2
        period = self.pitch / SQRT2
        t = np.mod(u + period / 2.0, period) - period / 2.0
        return self.profile(np.abs(t), self.width)


class XPatternTexture(Texture):
    """Textura 2: X grande no centro de cada célula `cell` x `cell` + mini-X entre eles.

    - X grande: duas diagonais até as quinas. As pontas são cones triangulares que descem até a
      altura `corner_height` (fração 0..1) exatamente na quina, onde 4 X's se encontram
      (0 = chegam à base; 1 = sem rebaixo, malha de losangos fundida).
      `corner_gap` (mm), se dado, troca isso por um vão livre entre pontas opostas.
    - Mini-X: no ponto médio entre dois centros de X grandes, com pernas paralelas às do grande.
      Ocupa `mini_ratio` do vão livre entre duas pernas paralelas (sobra (1-ratio)/2 de cada lado).
    """

    texture_id = 2
    name = "X's"
    description = "X grande em cada célula, com mini-X entre eles"

    def __init__(self, cell: float = 5.0, w_big: float = 0.8, w_mini: float = 0.6,
                 mini_ratio: float = 6 / 8, corner_height: float = 0.0,
                 corner_gap: Optional[float] = None, profile=None):
        super().__init__(profile)
        self.cell, self.w_big, self.w_mini = cell, w_big, w_mini
        self.mini_ratio, self.corner_height, self.corner_gap = mini_ratio, corner_height, corner_gap
        self.period_mm = cell
        self.min_feature_mm = min(w_big, w_mini)
        self._inset = self._compute_inset()

    def _compute_inset(self) -> float:
        """Recuo (mm, ao longo da diagonal) entre a quina e o fim do eixo da perna grande."""
        if self.corner_gap is not None:
            return self.corner_gap / 2.0 + self.w_big / 2.0
        if self.corner_height >= 1.0:
            return 0.0
        r = self.w_big / 2.0
        d = np.linspace(0.0, r, 4001)
        h = self.profile(d, self.w_big)  # decrescente em d
        return float(np.interp(self.corner_height, h[::-1], d[::-1]))

    def info(self) -> Dict[str, float]:
        clear = self.cell / SQRT2 - self.w_big
        leg = self.mini_ratio * clear
        return {
            "vao_livre_mm": clear,
            "perna_mini_mm": leg,
            "folga_mini_cada_lado_mm": (clear - leg) / 2.0,
            "recuo_eixo_ate_quina_mm": self._inset,
        }

    def height(self, x, y):
        cell, prof = self.cell, self.profile
        xm, ym = np.mod(x, cell), np.mod(y, cell)
        h = np.zeros_like(xm, dtype=float)

        a0 = self._inset / SQRT2
        b0 = cell - a0
        for ox in (-cell, 0.0, cell):
            for oy in (-cell, 0.0, cell):
                for (ax, ay, bx, by) in ((a0, a0, b0, b0), (a0, b0, b0, a0)):
                    d = dist_to_segment(xm - ox, ym - oy, ax, ay, bx, by)
                    h = np.maximum(h, prof(d, self.w_big))

        clear = cell / SQRT2 - self.w_big
        leg_total = self.mini_ratio * clear
        a = max(leg_total / 2.0 - self.w_mini / 2.0, 0.0)
        u = a / SQRT2
        centers = [(cell, cell / 2), (cell / 2, cell), (0.0, cell / 2), (cell / 2, 0.0)]
        for (cx, cy) in centers:
            for (dx, dy) in ((u, u), (u, -u)):
                d = dist_to_segment(xm, ym, cx - dx, cy - dy, cx + dx, cy + dy)
                h = np.maximum(h, prof(d, self.w_mini))
        return h


class WavesTexture(Texture):
    """Textura 3: linhas onduladas (cristas que serpenteiam).

    wavelength: comprimento de onda em x (divisor de 10 mm).
    wave_amplitude: amplitude lateral da onda (mm).
    pitch: espaçamento vertical entre cristas (divisor de 10 mm).
    width: largura da base da crista.
    """

    texture_id = 3
    name = "ondas"
    description = "ondas tortinhas, em fileiras"

    def __init__(self, wavelength: float = 5.0, wave_amplitude: float = 1.0, pitch: float = 2.5,
                 width: float = 0.8, profile=None):
        super().__init__(profile)
        self.wavelength, self.wave_amplitude = wavelength, wave_amplitude
        self.pitch, self.width = pitch, width
        self.period_mm = max(wavelength, pitch)
        self.min_feature_mm = width

    def height(self, x, y):
        k = 2.0 * np.pi / self.wavelength
        yy = y - self.wave_amplitude * np.sin(k * x)
        slope = self.wave_amplitude * k * np.cos(k * x)
        t = np.mod(yy + self.pitch / 2.0, self.pitch) - self.pitch / 2.0
        d = np.abs(t) / np.sqrt(1.0 + slope ** 2)  # distância perpendicular (1ª ordem)
        return self.profile(d, self.width)


class ScalesTexture(Texture):
    """Textura 4: escamas de peixe.

    Fileiras de arcos (semicírculos) de largura `scale_width`, fileiras deslocadas de meia escama
    e espaçadas de scale_width/2. scale_width deve dividir 10 mm (ex.: 5).
    """

    texture_id = 4
    name = "escamas"
    description = "escamas sobrepostas (arcos)"

    def __init__(self, scale_width: float = 5.0, width: float = 0.8, profile=None):
        super().__init__(profile)
        self.scale_width, self.width = scale_width, width
        self.period_mm = scale_width
        self.min_feature_mm = width

    def height(self, x, y):
        w = self.scale_width
        r = w / 2.0
        j0 = np.floor(y / r).astype(int)
        best = np.full_like(x, np.inf, dtype=float)
        for dj in (-1, 0, 1):
            j = j0 + dj
            cy = j * r
            off = 0.5 * (j % 2) * w
            i0 = np.round((x - off) / w)
            for di in (-1, 0, 1):
                cx = (i0 + di) * w + off
                dx, dy = x - cx, y - cy
                rho = np.hypot(dx, dy)
                d_arc = np.where(dy >= 0.0, np.abs(rho - r), np.hypot(np.abs(dx) - r, dy))
                best = np.minimum(best, d_arc)
        return self.profile(best, self.width)


class DiamondsTexture(Texture):
    """Textura 5: losangos em pirâmide ("papel dobrado com o meio levantado").

    Cada losango é uma pirâmide de base losangular: o centro é o ponto mais alto (1) e a altura
    desce linearmente até 0 nas bordas. As dobras (arestas) vão das quinas do losango até o centro.
    Losangos vizinhos se encontram em vales em V na altura 0.

    diag_x, diag_y: diagonais horizontal e vertical do losango (mm); devem dividir 10 mm
                    (ex.: 5x5 = quadrados a 45°; 5x10 = losangos alongados).
    apex_round: arredonda o topo (fração 0..1 da meia-diagonal); 0 = ponta viva.
    """

    texture_id = 5
    name = "losangos"
    description = "losangos em pirâmide"

    def __init__(self, diag_x: float = 5.0, diag_y: float = 5.0, apex_round: float = 0.0, profile=None):
        super().__init__(profile)
        self.diag_x, self.diag_y, self.apex_round = diag_x, diag_y, apex_round
        self.period_mm = max(diag_x, diag_y)

    def height(self, x, y):
        a, b = self.diag_x, self.diag_y

        def wrap(t, p):
            return np.mod(t + p / 2.0, p) - p / 2.0

        # "distância" (norma L1 escalada): 1 na borda do losango, 0 no centro. Duas subgrades de centros:
        # (i*a, j*b) e (i*a + a/2, j*b + b/2) -> os losangos preenchem o plano.
        s1 = np.abs(wrap(x, a)) / (a / 2.0) + np.abs(wrap(y, b)) / (b / 2.0)
        s2 = np.abs(wrap(x - a / 2.0, a)) / (a / 2.0) + np.abs(wrap(y - b / 2.0, b)) / (b / 2.0)
        s = np.minimum(s1, s2)
        e = self.apex_round
        if e > 0:
            g = np.where(s >= e, s, s * s / (2.0 * e) + e / 2.0)
            h = (1.0 - g) / (1.0 - e / 2.0)
        else:
            h = 1.0 - s
        return np.clip(h, 0.0, 1.0)


for _k in (FlatTexture, DiagonalLinesTexture, XPatternTexture, WavesTexture, ScalesTexture, DiamondsTexture):
    TextureLibrary.register(_k)
