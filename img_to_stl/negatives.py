"""Imagens "negativas": regiões, fronteiras e pontos em preto e branco (fundo preto).

Servem para conferir a leitura da imagem e como máscaras em CAD/editores de imagem.
Todas têm o mesmo enquadramento e escala (a mesma área do relevo, incluindo a moldura).
"""
from __future__ import annotations

import os
from typing import Tuple

import cv2
import numpy as np

from .config import OutputConfig, ReliefConfig
from .relief import PointShapeFactory
from .vision import PlanarMap

MAX_SIDE_PX = 4000


class NegativeRenderer:
    """Gera, numa pasta:  regioes.png, fronteiras.png, pontos.png, composto.png e regioes/regiao_NN.png."""

    def __init__(self, pmap: PlanarMap, relief: ReliefConfig, output: OutputConfig):
        self.pmap, self.relief, self.output = pmap, relief, output
        W, H = pmap.size_mm
        has_frame = pmap.outer_frame and any(b.outer for b in pmap.borders)
        self.margin = relief.border_width_mm / 2.0 if has_frame else 0.0
        self.W, self.H = W, H
        total_w, total_h = W + 2 * self.margin, H + 2 * self.margin
        self.ppm = min(float(output.negatives_px_per_mm), MAX_SIDE_PX / max(total_w, total_h))
        self.nx = max(1, int(round(total_w * self.ppm)))
        self.ny = max(1, int(round(total_h * self.ppm)))

    # ---- conversões ---- #
    def _px(self, pts_mm) -> np.ndarray:
        pts = np.asarray(pts_mm, dtype=float).reshape(-1, 2)
        x = (pts[:, 0] + self.margin) * self.ppm
        y = (self.H + self.margin - pts[:, 1]) * self.ppm      # y do modelo sobe; o da imagem desce
        return np.stack([x, y], axis=1)

    # ---- camadas ---- #
    def regions_layers(self) -> Tuple[np.ndarray, np.ndarray]:
        """(cinzas por região, id por pixel com -1 fora da peça)."""
        cols = (np.arange(self.nx) + 0.5) / self.ppm - self.margin
        rows = self.H + self.margin - (np.arange(self.ny) + 0.5) / self.ppm
        X, Y = np.meshgrid(cols, rows)
        lab = self.pmap.label_at(X, Y).astype(np.int32)
        outside = (X < 0) | (X > self.W) | (Y < 0) | (Y > self.H)
        lab[outside] = -1
        n = max(1, len(self.pmap.regions))
        lut = np.linspace(70, 255, n).astype(np.uint8) if n > 1 else np.array([200], np.uint8)
        gray = np.zeros(lab.shape, np.uint8)
        gray[lab >= 0] = lut[lab[lab >= 0]]
        return gray, lab

    def borders_layer(self) -> np.ndarray:
        img = np.zeros((self.ny, self.nx), np.uint8)
        thick = max(1, int(round(self.relief.border_width_mm * self.ppm)))
        for b in self.pmap.borders:
            if len(b.points_mm) < 2:
                continue
            p = np.round(self._px(b.points_mm)).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [p], b.closed, 255, thick, cv2.LINE_8)
        return img

    def points_layer(self) -> np.ndarray:
        img = np.zeros((self.ny, self.nx), np.uint8)
        cfg = self.relief
        for pt in self.pmap.points:
            shape = PointShapeFactory.create(pt.shape or cfg.point_shapes.get(pt.valence, cfg.point_shape),
                                             cfg.point_size_mm)
            r = shape.extent + 1.0 / self.ppm
            cx, cy = self._px(pt.xy_mm)[0]
            j0, j1 = max(0, int(cx - r * self.ppm) - 1), min(self.nx, int(cx + r * self.ppm) + 2)
            i0, i1 = max(0, int(cy - r * self.ppm) - 1), min(self.ny, int(cy + r * self.ppm) + 2)
            if i0 >= i1 or j0 >= j1:
                continue
            jj, ii = np.meshgrid(np.arange(j0, j1) + 0.5, np.arange(i0, i1) + 0.5)
            dxm = (jj - cx) / self.ppm
            dym = -(ii - cy) / self.ppm                         # volta ao sentido y-para-cima
            inside = shape.sdf(dxm, dym) <= 0
            img[i0:i1, j0:j1][inside] = 255
        return img

    # ---- saída ---- #
    def save(self, out_dir: str) -> str:
        os.makedirs(os.path.join(out_dir, "regioes"), exist_ok=True)
        regions, lab = self.regions_layers()
        borders, points = self.borders_layer(), self.points_layer()
        cv2.imwrite(os.path.join(out_dir, "regioes.png"), regions)
        cv2.imwrite(os.path.join(out_dir, "fronteiras.png"), borders)
        cv2.imwrite(os.path.join(out_dir, "pontos.png"), points)
        for r in self.pmap.regions:
            cv2.imwrite(os.path.join(out_dir, "regioes", f"regiao_{r.id:02d}.png"),
                        ((lab == r.id) * 255).astype(np.uint8))
        comp = np.stack([regions // 3] * 3, axis=2)              # BGR: regiões em cinza escuro
        comp[borders > 0] = (255, 255, 255)
        comp[points > 0] = (60, 60, 255)                         # pontos em vermelho
        cv2.imwrite(os.path.join(out_dir, "composto.png"), comp)
        return out_dir
