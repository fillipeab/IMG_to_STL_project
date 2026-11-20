"""Relatório da etapa 2: parâmetros usados, texturas aplicadas e dados do modelo."""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List

from ..etapa1_reconhecimento.modelos import PlanarMap
from .atribuicao import TextureAssignment
from .biblioteca import TextureLibrary
from .config import AJUDA, Etapa2Config
from .especificacao import format_spec


def report_text(pmap: PlanarMap, cfg: Etapa2Config, assignments: Dict[int, TextureAssignment],
                info: Dict[str, float], warnings: List[str], size_mm, stl_path: str) -> str:
    L = ["ETAPA 2 — APLICAÇÃO DE TEXTURA E GERAÇÃO DO STL", "=" * 50, "", "PARÂMETROS UTILIZADOS", "-" * 40]
    for k, v in asdict(cfg).items():
        L.append(f"{k} = {v}")
        if k in AJUDA:
            L.append(f"    # {AJUDA[k]}")
    L += ["", "TEXTURAS APLICADAS  (região -> textura)  [edite em texturas.json]", "-" * 40]
    names = TextureLibrary.describe()
    for r in pmap.regions:
        a = assignments[r.id]
        L.append(f"  {r.name}: {format_spec(a, cfg.texture_amplitude_mm)}   ({names.get(a.texture_id, '?')})")
    L += ["", "MODELO OBTIDO", "-" * 40,
          f"arquivo STL: {stl_path}",
          f"dimensões (X x Y): {size_mm[0]:.1f} x {size_mm[1]:.1f} mm",
          f"base: {cfg.base_mode}, espessura {cfg.base_thickness_mm} mm",
          f"triângulos: {int(info['triangulos']):,}", f"volume: {info['volume_mm3']:.0f} mm³",
          f"malha estanque: {'sim' if info['estanque'] else 'NÃO'}"]
    if warnings:
        L += ["", "AVISOS"] + [f"  {w}" for w in warnings]
    return "\n".join(L) + "\n"
