"""Gravação da pasta da etapa 1: parâmetros, resultados (JSON + texto), prévia e negativos."""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import List

import cv2
import numpy as np

from ..comum.arquivos import ensure
from .config import AJUDA, Etapa1Config
from .modelos import PlanarMap
from .negativos import NegativeRenderer, class_color


def render_preview(pmap: PlanarMap, path: str, max_side: int = 1400) -> None:
    """PNG com regiões coloridas (cor média), fronteiras, pontos (por classe) e o número de cada região."""
    h, w = pmap.labels.shape
    lut = np.array([r.color_rgb for r in pmap.regions], dtype=np.uint8)
    img = lut[pmap.labels]
    scale = max(1.0, max_side / max(h, w))
    if scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    img = np.ascontiguousarray(img[:, :, ::-1])

    def to_px(pts):
        pts = np.asarray(pts, dtype=float)
        return np.stack([pts[:, 0] / pmap.mm_per_px, h - pts[:, 1] / pmap.mm_per_px], 1) * scale

    for b in pmap.borders:
        p = np.round(to_px(b.points_mm)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [p], b.closed, (20, 20, 20), max(1, int(round(scale))), cv2.LINE_AA)
    for pt in pmap.points:
        c = np.round(to_px([pt.xy_mm])[0]).astype(int)
        cv2.circle(img, tuple(int(v) for v in c), max(3, int(4 * scale)), class_color(pt.classe), -1, cv2.LINE_AA)
    font_scale = max(0.5, 0.6 * scale * min(h, w) / 600)
    for r in pmap.regions:
        cx = int(r.centroid_mm[0] / pmap.mm_per_px * scale)
        cy = int((h - r.centroid_mm[1] / pmap.mm_per_px) * scale)
        txt = str(r.id)
        lum = 0.299 * r.color_rgb[0] + 0.587 * r.color_rgb[1] + 0.114 * r.color_rgb[2]
        col = (255, 255, 255) if lum < 128 else (0, 0, 0)
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
        cv2.putText(img, txt, (cx - tw // 2, cy + th // 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, col, 2, cv2.LINE_AA)
    cv2.imwrite(path, img)


def report_text(pmap: PlanarMap, cfg: Etapa1Config, warnings: List[str]) -> str:
    """Texto com os parâmetros usados e os resultados obtidos."""
    L: List[str] = ["ETAPA 1 — RECONHECIMENTO DA IMAGEM", "=" * 40, "", "PARÂMETROS UTILIZADOS", "-" * 40]
    for k, v in asdict(cfg).items():
        L.append(f"{k} = {v}")
        if k in AJUDA:
            L.append(f"    # {AJUDA[k]}")
    W, H = pmap.size_mm
    cls = pmap.classes()
    L += ["", "RESULTADOS OBTIDOS", "-" * 40,
          f"peça: {W:.1f} x {H:.1f} mm",
          f"número de regiões: {len(pmap.regions)}",
          f"número de famílias (regiões irmãs): {len(pmap.families)}",
          f"número de fronteiras: {len(pmap.borders)} ({sum(b.length_mm for b in pmap.borders):.0f} mm no total)",
          f"pontos tríplices: {cls.get('triplice', 0)}",
          f"pontos múltiplos (4+ regiões): {cls.get('multiplo', 0)}"]
    others = {c: n for c, n in cls.items() if c not in ("triplice", "multiplo")}
    L.append("pontos de interesse: " + (", ".join(f"{c}: {n}" for c, n in others.items()) if others else "nenhum"))
    L += ["", "REGIÕES  (nome | família | cor | rgb | área mm² | fundo)"]
    fam = {f.id: f for f in pmap.families}
    for r in pmap.regions:
        L.append(f"  {r.name} | {fam[r.family].name} | {r.color_name} | {r.color_rgb} | {r.area_mm2:.1f} | "
                 f"{'sim' if r.ignored else 'não'}")
    L += ["", "FAMÍLIAS  (regiões irmãs: cor parecida, vizinhas ou não)"]
    for f in pmap.families:
        L.append(f"  {f.name}: " + ", ".join(pmap.regions[i].name for i in f.region_ids))
    L += ["", "FRONTEIRAS  (nome | comprimento mm)"]
    for b in pmap.borders:
        L.append(f"  {b.name} | {b.length_mm:.1f}")
    if pmap.points:
        L += ["", "PONTOS  (id | classe | nome | x,y mm | regiões)"]
        for p in pmap.points:
            L.append(f"  {p.id} | {p.classe} | {p.nome or '-'} | {p.xy_mm[0]:.1f}, {p.xy_mm[1]:.1f} | "
                     f"{','.join(map(str, p.regions)) or '-'}")
    if warnings:
        L += ["", "AVISOS"] + [f"  {w}" for w in warnings]
    return "\n".join(L) + "\n"


def save_stage1(pmap: PlanarMap, cfg: Etapa1Config, out_dir: str, warnings: List[str], negatives: bool = True) -> str:
    """Grava: parametros.json, resultado.json, rotulos.png, parametros_e_resultados.txt, previa.png, negativos/."""
    ensure(out_dir)
    cfg.to_json(os.path.join(out_dir, "parametros.json"))
    pmap.save(out_dir)
    with open(os.path.join(out_dir, "parametros_e_resultados.txt"), "w", encoding="utf-8") as f:
        f.write(report_text(pmap, cfg, warnings))
    render_preview(pmap, os.path.join(out_dir, "previa.png"))
    if negatives:
        NegativeRenderer(pmap, cfg).save(os.path.join(out_dir, "negativos"))
    return out_dir
