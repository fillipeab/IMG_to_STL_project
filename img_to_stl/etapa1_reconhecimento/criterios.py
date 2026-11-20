"""Fusão de regiões por critério (em vez de números): família, tamanho, cor.

Uma "fusão" é um item de `merge_regions`: lista de números de região ([3, 7]) ou texto de critério:
    "familia"            funde as regiões irmãs (mesma família) que se tocam
    "familia=2"          idem, só da família de número 2 (ou pelo nome)
    "menores=50"         cada região com menos de 50 mm² vai para a vizinha de cor mais parecida
    "cor=verde,lilas"    todas as regiões de cada cor viram uma só ("cor=verde+lilas" = verde e lilás numa só)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from ..comum.arquivos import slug
from .cores import rgb_to_lab
from .modelos import PlanarMap

Fusao = Union[List[int], str]
CRITERIOS = ("familia", "menores", "cor")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()


def parse_fusion(text: str, pmap: Optional[PlanarMap] = None) -> Fusao:
    """Texto digitado -> item de fusão. '3 7' / '3,7' / nomes de região -> [3, 7];
    'familia', 'menores 50', 'menores=50', 'cor verde lilas' -> critério normalizado."""
    t = _norm(text)
    if not t:
        raise ValueError("fusão vazia")
    m = re.match(r"^(familia|menores|cor)\b[\s=]*(.*)$", t)
    if m:
        kind, arg = m.group(1), m.group(2).strip()
        if kind == "familia":
            return "familia" + (f"={arg}" if arg else "")
        if not arg:
            raise ValueError(f"informe o valor: '{kind}=...'")
        if kind == "menores":
            float(arg.replace(",", "."))                          # valida o número
            return f"menores={arg.replace(',', '.')}"
        return "cor=" + ",".join(arg.replace(",", " ").split())
    by_name = {_norm(r.name): r.id for r in pmap.regions} if pmap else {}
    ids: List[int] = []
    for tok in t.replace(",", " ").split():
        if tok.isdigit():
            ids.append(int(tok))
        elif tok in by_name:
            ids.append(by_name[tok])
        else:
            raise ValueError(f"'{tok}' não é número, nome de região nem critério (familia, menores=N, cor=...)")
    return ids


def _components(members: Sequence[int], adj: Dict[int, set]) -> List[List[int]]:
    """Grupos de `members` ligados entre si por vizinhança."""
    left, out = set(members), []
    while left:
        stack, comp = [left.pop()], []
        while stack:
            r = stack.pop()
            comp.append(r)
            for n in adj[r] & left:
                left.discard(n)
                stack.append(n)
        out.append(sorted(comp))
    return out


def resolve_fusion(pmap: PlanarMap, entry: Fusao) -> List[List[int]]:
    """Item de fusão -> grupos de regiões a fundir (cada grupo com 2+). Levanta ValueError se não houver nada."""
    if not isinstance(entry, str):
        ids = list(dict.fromkeys(int(i) for i in entry))
        bad = [i for i in ids if not 0 <= i < len(pmap.regions)]
        if bad:
            raise ValueError(f"região inexistente: {bad} (há {len(pmap.regions)} regiões, de 0 a {len(pmap.regions) - 1})")
        if len(ids) < 2:
            raise ValueError("informe pelo menos 2 regiões diferentes para fundir")
        return [ids]
    kind, _, arg = entry.partition("=")
    kind, arg = _norm(kind), arg.strip()
    regions, adj = pmap.regions, pmap.adjacency()
    groups: List[List[int]] = []

    if kind == "familia":
        for fam in pmap.families:
            if arg and arg not in (str(fam.id), fam.name):
                continue
            groups += [c for c in _components(fam.region_ids, adj) if len(c) > 1]
        if not groups:
            raise ValueError("nenhuma família com regiões vizinhas para fundir"
                             + (" (família não encontrada?)" if arg else ""))

    elif kind == "menores":
        limit = float(arg.replace(",", "."))
        area = {r.id: r.area_mm2 for r in regions}
        lab = {r.id: rgb_to_lab(r.color_rgb) for r in regions}
        nb = {k: set(v) for k, v in adj.items()}
        parent = {r.id: r.id for r in regions}
        ignored = {r.id: r.ignored for r in regions}
        while True:
            small = [i for i in nb if area[i] < limit and nb[i]]
            if not small:
                break
            a = min(small, key=lambda i: area[i])
            same = [n for n in nb[a] if ignored[n] == ignored[a]] or list(nb[a])   # evita engolir o fundo
            b = min(same, key=lambda n: float(np.linalg.norm(lab[a] - lab[n])))
            tot = area[a] + area[b]                                  # b absorve a
            lab[b] = (lab[a] * area[a] + lab[b] * area[b]) / tot
            area[b] = tot
            nb[b] |= nb[a] - {b}
            for n in nb[a]:
                nb[n].discard(a)
                if n != b:
                    nb[n].add(b)
            del nb[a]
            parent[a] = b
        comp: Dict[int, List[int]] = {}
        for i in parent:
            r = i
            while parent[r] != r:
                r = parent[r]
            comp.setdefault(r, []).append(i)
        groups = [sorted(v) for v in comp.values() if len(v) > 1]
        if not groups:
            raise ValueError(f"nenhuma região com menos de {limit:g} mm² (e com vizinha) para fundir")

    elif kind == "cor":
        if not arg:
            raise ValueError("informe a cor: cor=verde (ou cor=verde,lilas / cor=verde+lilas)")
        for item in arg.split(","):
            toks = [slug(t) for t in item.split("+") if t.strip()]
            ids = [r.id for r in regions
                   if any(slug(r.color_name) == t or slug(r.color_name).startswith(t + "_") for t in toks)]
            if len(ids) > 1:
                groups.append(ids)
        if not groups:
            raise ValueError(f"nenhuma cor com 2+ regiões para fundir em '{arg}'")
    else:
        raise ValueError(f"critério desconhecido: '{entry}' (use familia, menores=N ou cor=...)")
    return groups
