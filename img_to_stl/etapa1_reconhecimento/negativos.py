"""Negativos da etapa 1: regiões (nomeadas/numeradas), famílias, fronteiras e pontos por classe.

Branco sobre preto, todos com o mesmo enquadramento (a peça exata) e a mesma escala.
Servem para conferir a leitura e como máscaras em CAD/editores de imagem.
"""
from __future__ import annotations

import os
from typing import Dict, Tuple

import cv2
import numpy as np

from ..comum.arquivos import ensure, slug
from .config import Etapa1Config
from .modelos import PlanarMap

MAX_SIDE_PX = 4000
# cor (BGR) de cada classe nas imagens coloridas; classes novas ganham cores do ciclo
_CORES_CLASSE = {"triplice": (0, 200, 255), "multiplo": (255, 0, 200), "capital": (0, 0, 255),
                 "cidade": (255, 120, 0), "ponto": (0, 160, 0)}
_CICLO = [(0, 0, 255), (255, 120, 0), (0, 160, 0), (200, 0, 160), (0, 190, 220), (120, 60, 220)]


def class_color(classe: str, _cache: Dict[str, Tuple[int, int, int]] = {}) -> Tuple[int, int, int]:
    if classe in _CORES_CLASSE:
        return _CORES_CLASSE[classe]
    if classe not in _cache:
        _cache[classe] = _CICLO[len(_cache) % len(_CICLO)]
    return _cache[classe]


class NegativeRenderer:
    def __init__(self, pmap: PlanarMap, cfg: Etapa1Config):
        self.pmap, self.cfg = pmap, cfg
        self.W, self.H = pmap.size_mm
        self.ppm = min(float(cfg.negatives_px_per_mm), MAX_SIDE_PX / max(self.W, self.H))
        self.nx, self.ny = max(1, int(round(self.W * self.ppm))), max(1, int(round(self.H * self.ppm)))

    def _px(self, pts_mm) -> np.ndarray:
        p = np.asarray(pts_mm, dtype=float).reshape(-1, 2)
        return np.stack([p[:, 0] * self.ppm, (self.H - p[:, 1]) * self.ppm], axis=1)

    def label_image(self) -> np.ndarray:
        cols = (np.arange(self.nx) + 0.5) / self.ppm
        rows = self.H - (np.arange(self.ny) + 0.5) / self.ppm
        X, Y = np.meshgrid(cols, rows)
        return self.pmap.label_at(X, Y).astype(np.int32)

    def borders_layer(self) -> np.ndarray:
        img = np.zeros((self.ny, self.nx), np.uint8)
        thick = max(1, int(round(self.cfg.negatives_line_mm * self.ppm)))
        for b in self.pmap.borders:
            if len(b.points_mm) >= 2:
                p = np.round(self._px(b.points_mm)).astype(np.int32).reshape(-1, 1, 2)
                cv2.polylines(img, [p], b.closed, 255, thick, cv2.LINE_8)
        return img

    def points_layer(self, points) -> np.ndarray:
        img = np.zeros((self.ny, self.nx), np.uint8)
        r = max(2, int(round(self.cfg.negatives_point_radius_mm * self.ppm)))
        for p in points:
            c = self._px(p.xy_mm)[0]
            cv2.circle(img, (int(round(c[0])), int(round(c[1]))), r, 255, -1, cv2.LINE_8)
        return img

    # ---- imagens com marcação (numeração) ---- #
    def _label_text(self, img, text, xy, color=(255, 255, 255), scale=None):
        scale = scale or max(0.4, 0.5 * self.ppm / 10.0 * 1.0)
        thick = max(1, int(round(scale * 2)))
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        org = (int(xy[0] - tw / 2), int(xy[1] + th / 2))
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)

    def borders_numbered(self, borders_img: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor((borders_img // 3).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        thick = max(1, int(round(self.cfg.negatives_line_mm * self.ppm)))
        for b in self.pmap.borders:
            if len(b.points_mm) >= 2:
                p = np.round(self._px(b.points_mm)).astype(np.int32).reshape(-1, 1, 2)
                cv2.polylines(img, [p], b.closed, (255, 255, 255), thick, cv2.LINE_8)
        for b in self.pmap.borders:
            if b.outer or len(b.points_mm) < 2:
                continue
            mid = self._px(b.points_mm[len(b.points_mm) // 2])[0]
            self._label_text(img, f"F{b.id}", mid, (0, 220, 255))
        return img

    def points_marked(self, base_gray: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(base_gray, cv2.COLOR_GRAY2BGR)
        r = max(3, int(round(self.cfg.negatives_point_radius_mm * self.ppm)))
        for p in self.pmap.points:
            c = self._px(p.xy_mm)[0]
            col = class_color(p.classe)
            cv2.circle(img, (int(round(c[0])), int(round(c[1]))), r, col, -1, cv2.LINE_AA)
            cv2.circle(img, (int(round(c[0])), int(round(c[1]))), r, (255, 255, 255), 1, cv2.LINE_AA)
            if p.nome:
                self._label_text(img, p.nome, (c[0], c[1] - 2 * r), col)
        # legenda
        y = 20
        for classe, n in self.pmap.classes().items():
            cv2.circle(img, (14, y), 7, class_color(classe), -1, cv2.LINE_AA)
            cv2.putText(img, f"{classe} ({n})", (28, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            y += 22
        return img

    # ---- saída ---- #
    def save(self, out_dir: str) -> str:
        ensure(out_dir)
        pm = self.pmap
        lab = self.label_image()
        n = max(1, len(pm.regions))
        lut = np.linspace(70, 255, n).astype(np.uint8) if n > 1 else np.array([200], np.uint8)
        gray = lut[lab]
        cv2.imwrite(os.path.join(out_dir, "regioes_niveis_de_cinza.png"), gray)

        d = ensure(os.path.join(out_dir, "regioes"))
        for r in pm.regions:
            cv2.imwrite(os.path.join(d, f"regiao_{r.name}.png"), ((lab == r.id) * 255).astype(np.uint8))
        d = ensure(os.path.join(out_dir, "familias"))
        for f in pm.families:
            cv2.imwrite(os.path.join(d, f"{f.name}.png"), (np.isin(lab, f.region_ids) * 255).astype(np.uint8))

        d = ensure(os.path.join(out_dir, "fronteiras"))
        borders = self.borders_layer()
        cv2.imwrite(os.path.join(d, "fronteiras.png"), borders)
        cv2.imwrite(os.path.join(d, "fronteiras_numeradas.png"), self.borders_numbered(borders))

        d = ensure(os.path.join(out_dir, "pontos"))
        cv2.imwrite(os.path.join(d, "pontos_marcados.png"), self.points_marked(gray // 2))
        for classe in pm.classes():
            cv2.imwrite(os.path.join(d, f"pontos_{slug(classe)}.png"), self.points_layer(pm.points_of(classe)))
        return out_dir
