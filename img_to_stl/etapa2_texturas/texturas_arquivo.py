"""Arquivo de geração de texturas (texturas.json): o que cada região recebe, editável à mão.

Formato:
{
  "regioes":  {"00_azul": "ondas/3", "01_verde_1": "escamas/4(escala=1.5)", ...},
  "familias": {"familia_01_verde": "linhas_diagonais/1"}      <- opcional: vale para as regiões
}                                                                  da família sem linha própria em "regioes"
Cada valor é uma especificação "nome/numero(distorções)" — ver especificacao.py.
A chave da região pode ser o nome completo ("03_verde_2") ou só o número (3).
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Tuple

from ..etapa1_reconhecimento.modelos import PlanarMap
from .atribuicao import TextureAssignment
from .especificacao import format_spec, parse_spec

LEIA_ME = ("Escolha a textura de cada região: \"nome/numero(distorcoes)\", ex.: \"ondas/3(escala=1.5, alongar=2, angulo=30)\". "
           "0 = lisa, 1 linhas diagonais, 2 X's, 3 ondas, 4 escamas, 5 losangos; >=100 = texturas da pasta texture_dir. "
           "Distorções: escala, alongar, angulo, cisalhar, rotacao, desloc_x, desloc_y, onda_amp, onda_comp, amp (altura em mm). "
           "Em \"familias\", uma linha vale para todas as regiões irmãs que não têm linha própria em \"regioes\".")


def signature(pmap: PlanarMap) -> str:
    """Identifica o conjunto de regiões (muda se a etapa 1 for refeita com outro resultado)."""
    return hashlib.sha1("|".join(r.name for r in pmap.regions).encode()).hexdigest()[:10]


def save_texture_file(path: str, pmap: PlanarMap, assignments: Dict[int, TextureAssignment],
                      default_amplitude_mm: float) -> None:
    data = {"_leia_me": LEIA_ME, "_assinatura": signature(pmap),
            "regioes": {r.name: format_spec(assignments[r.id], default_amplitude_mm) for r in pmap.regions},
            "familias": {}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_texture_file(path: str, pmap: PlanarMap, default_amplitude_mm: float) -> Tuple[Dict[int, TextureAssignment], List[str]]:
    """Lê o arquivo -> ({id da região: TextureAssignment}, avisos). Erros de sintaxe levantam ValueError
    dizendo qual linha está errada."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    warnings: List[str] = []
    sig = data.get("_assinatura")
    if sig and sig != signature(pmap):
        warnings.append("texturas.json foi gerado para outro resultado da etapa 1 (regiões diferentes); "
                        "confira os nomes das regiões")
        return {}, warnings                                   # não adianta ler: quem chama gera nova sugestão
    by_name = {r.name: r.id for r in pmap.regions}
    by_family = {f.name: f.region_ids for f in pmap.families}
    out: Dict[int, TextureAssignment] = {}

    def region_id(key: str) -> int:
        if key in by_name:
            return by_name[key]
        head = key.split("_")[0]
        if head.isdigit() and int(head) < len(pmap.regions):
            return int(head)
        raise ValueError(f"região '{key}' não existe. Regiões: {', '.join(by_name)}")

    for key, spec in data.get("regioes", {}).items():
        try:
            out[region_id(key)] = parse_spec(spec, default_amplitude_mm)
        except (ValueError, KeyError) as e:
            raise ValueError(f"texturas.json, região '{key}': {e}") from None
    for key, spec in data.get("familias", {}).items():
        if key not in by_family:
            raise ValueError(f"texturas.json: família '{key}' não existe. Famílias: {', '.join(by_family)}")
        try:
            asg = parse_spec(spec, default_amplitude_mm)
        except (ValueError, KeyError) as e:
            raise ValueError(f"texturas.json, família '{key}': {e}") from None
        for rid in by_family[key]:
            out.setdefault(rid, asg)
    return out, warnings


def set_entry(path: str, key: str, spec: str, pmap: PlanarMap, default_amplitude_mm: float) -> None:
    """Muda UMA linha do texturas.json (região por nome ou número). Valida antes de gravar."""
    parse_spec(spec, default_amplitude_mm)                       # levanta ValueError se inválida
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    names = [r.name for r in pmap.regions]
    if key in names:
        name = key
    elif key.isdigit() and int(key) < len(names):
        name = names[int(key)]
    elif key in {f.name for f in pmap.families}:
        data.setdefault("familias", {})[key] = spec
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return
    else:
        raise ValueError(f"região '{key}' não existe. Regiões: {', '.join(names)}")
    data.setdefault("regioes", {})[name] = spec
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
