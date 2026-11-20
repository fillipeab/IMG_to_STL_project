"""Especificação de textura como "função": nome/numero(distorcao_1, distorcao_2, ...).

Exemplos:
    ondas/3                         textura 3 (ondas), sem distorção
    3                               idem (só o número)        ondas   idem (só o nome)
    ondas/3(1.5)                    escala 1,5
    ondas/3(1.5, 2, 30)             escala 1,5; alongada 2x na direção de 30°
    ondas/3(escala=1.5, amp=0.8)    por nome (ordem livre); amp = altura própria (mm)
    lisa/0                          sem textura

Ordem dos argumentos POSICIONAIS (use nome=valor para pular algum):
    1 escala · 2 alongar · 3 angulo (do alongamento, °) · 4 cisalhar · 5 rotacao (°) ·
    6 desloc_x (mm) · 7 desloc_y (mm) · 8 onda_amp (mm) · 9 onda_comp (mm)
Nomes aceitos também em inglês (scale, stretch, stretch_angle_deg, shear, rotation_deg,
offset_x, offset_y, warp_amplitude_mm, warp_wavelength_mm, amplitude_mm).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .atribuicao import TextureAssignment
from .biblioteca import TextureLibrary, TextureTransform

_ORDEM = ["escala", "alongar", "angulo", "cisalhar", "rotacao", "desloc_x", "desloc_y", "onda_amp", "onda_comp"]
_ALIAS = {
    "escala": "escala", "scale": "escala", "alongar": "alongar", "stretch": "alongar",
    "angulo": "angulo", "stretch_angle_deg": "angulo", "cisalhar": "cisalhar", "shear": "cisalhar",
    "rotacao": "rotacao", "rotation_deg": "rotacao", "desloc_x": "desloc_x", "offset_x": "desloc_x",
    "desloc_y": "desloc_y", "offset_y": "desloc_y", "onda_amp": "onda_amp", "warp_amplitude_mm": "onda_amp",
    "onda_comp": "onda_comp", "warp_wavelength_mm": "onda_comp",
    "amp": "amp", "amplitude": "amp", "amplitude_mm": "amp",
}
_PATTERN = re.compile(r"^\s*([^()]*?)\s*(?:\((.*)\))?\s*$")


def parse_spec(text: str, default_amplitude_mm: float) -> TextureAssignment:
    """'ondas/3(1.5, 2, 30)' -> TextureAssignment. Levanta ValueError com mensagem clara se inválido."""
    m = _PATTERN.match(str(text))
    if not m:
        raise ValueError(f"especificação inválida: '{text}'")
    head, args = m.group(1), m.group(2)
    texture_id = _resolve_head(head)

    values: Dict[str, float] = {}
    if args and args.strip():
        for i, raw in enumerate(a.strip() for a in args.split(",")):
            if not raw:
                continue
            if "=" in raw:
                key, val = (s.strip() for s in raw.split("=", 1))
                if key.lower() not in _ALIAS:
                    raise ValueError(f"distorção desconhecida '{key}' em '{text}'. Válidas: {', '.join(_ORDEM)}, amp")
                values[_ALIAS[key.lower()]] = _num(val, text)
            else:
                if i >= len(_ORDEM):
                    raise ValueError(f"argumentos demais em '{text}' (máx. {len(_ORDEM)} posicionais)")
                values[_ORDEM[i]] = _num(raw, text)

    transform = TextureTransform(
        scale=values.get("escala", 1.0), stretch=values.get("alongar", 1.0),
        stretch_angle_deg=values.get("angulo", 0.0), shear=values.get("cisalhar", 0.0),
        rotation_deg=values.get("rotacao", 0.0),
        offset_mm=(values.get("desloc_x", 0.0), values.get("desloc_y", 0.0)),
        warp_amplitude_mm=values.get("onda_amp", 0.0), warp_wavelength_mm=values.get("onda_comp", 20.0))
    return TextureAssignment(texture_id, amplitude_mm=values.get("amp", default_amplitude_mm), transform=transform)


def _num(val: str, text: str) -> float:
    try:
        return float(val.replace(",", "."))
    except ValueError:
        raise ValueError(f"valor não numérico '{val}' em '{text}'")


def _resolve_head(head: str) -> int:
    """'ondas/3', '3' ou 'ondas' -> id. Se nome e número divergirem, vale o número."""
    if not head:
        raise ValueError("falta a textura (nome e/ou número)")
    if "/" in head:
        name, num = (s.strip() for s in head.rsplit("/", 1))
        return TextureLibrary.resolve(num)
    return TextureLibrary.resolve(head)


def format_spec(a: TextureAssignment, default_amplitude_mm: float) -> str:
    """TextureAssignment -> 'ondas/3(escala=1.5, amp=0.8)' (só o que difere do padrão)."""
    name = TextureLibrary.describe().get(a.texture_id, "textura").replace(" ", "_").replace("'", "")
    t = a.transform
    parts: List[str] = []
    for key, val, dflt in (("escala", t.scale, 1.0), ("alongar", t.stretch, 1.0), ("angulo", t.stretch_angle_deg, 0.0),
                           ("cisalhar", t.shear, 0.0), ("rotacao", t.rotation_deg, 0.0),
                           ("desloc_x", t.offset_mm[0], 0.0), ("desloc_y", t.offset_mm[1], 0.0),
                           ("onda_amp", t.warp_amplitude_mm, 0.0)):
        if val != dflt:
            parts.append(f"{key}={val:g}")
    if t.warp_amplitude_mm and t.warp_wavelength_mm != 20.0:
        parts.append(f"onda_comp={t.warp_wavelength_mm:g}")
    if abs(a.amplitude_mm - default_amplitude_mm) > 1e-9:
        parts.append(f"amp={a.amplitude_mm:g}")
    return f"{name}/{a.texture_id}" + (f"({', '.join(parts)})" if parts else "")
