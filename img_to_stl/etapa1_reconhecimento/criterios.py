"""Fusão de regiões por critério (em vez de números): família, tamanho, cor.

Uma "fusão" é um item de `merge_regions`: lista de números de região ([3, 7]) ou texto de critério:
    "familia"            funde as regiões irmãs (mesma família) que se tocam
    "familia=2"          idem, só da família de número 2 (ou pelo nome)
    "menores=50"         cada região com menos de 50 mm² vai para a vizinha de cor mais parecida
    "parecidas=8"        vizinhas com diferença de cor (ΔE) menor que 8 viram uma só (as mais parecidas primeiro)
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
CRITERIOS = ("familia", "menores", "cor", "parecidas")
# critérios com "limite aceitável" que o usuário pode ajustar: nome -> (descrição, unidade)
LIMITES = {"menores": ("limite de área", "mm²"), "parecidas": ("limite de diferença de cor", "ΔE")}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().strip()


def parse_fusion(text: str, pmap: Optional[PlanarMap] = None) -> Fusao:
    """Texto digitado -> item de fusão. '3 7' / '3,7' / nomes de região -> [3, 7];
    'familia', 'menores 50', 'menores=50', 'cor verde lilas' -> critério normalizado."""
    t = _norm(text)
    if not t:
        raise ValueError("fusão vazia")
    t = re.sub(r"^(semelhantes|similares)\b", "parecidas", t)
    m = re.match(r"^(familia|menores|cor|parecidas)\b[\s=]*(.*)$", t)
    if m:
        kind, arg = m.group(1), m.group(2).strip()
        if kind == "familia":
            return "familia" + (f"={arg}" if arg else "")
        if not arg:
            raise ValueError(f"informe o valor: '{kind}=...'")
        if kind in LIMITES:
            float(arg.replace(",", "."))                          # valida o número
            return f"{kind}={arg.replace(',', '.')}"
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


class _Sim:
    """Simula fusões de vizinhas (área e cor ponderadas) para os critérios com limite."""

    def __init__(self, regions, adj):
        self.area = {r.id: r.area_mm2 for r in regions}
        self.lab = {r.id: rgb_to_lab(r.color_rgb) for r in regions}
        self.ignored = {r.id: r.ignored for r in regions}
        self.nb = {k: set(v) for k, v in adj.items()}
        self.parent = {r.id: r.id for r in regions}

    def delta(self, a: int, b: int) -> float:
        return float(np.linalg.norm(self.lab[a] - self.lab[b]))

    def absorb(self, a: int, b: int) -> None:
        """`b` absorve `a`."""
        tot = self.area[a] + self.area[b]
        self.lab[b] = (self.lab[a] * self.area[a] + self.lab[b] * self.area[b]) / tot
        self.area[b] = tot
        self.nb[b] |= self.nb[a] - {b}
        for n in self.nb[a]:
            self.nb[n].discard(a)
            if n != b:
                self.nb[n].add(b)
        del self.nb[a]
        self.parent[a] = b

    def groups(self) -> List[List[int]]:
        comp: Dict[int, List[int]] = {}
        for i in self.parent:
            r = i
            while self.parent[r] != r:
                r = self.parent[r]
            comp.setdefault(r, []).append(i)
        return [sorted(v) for v in comp.values() if len(v) > 1]


def limit_of(entry: Fusao):
    """(tipo, valor) se o critério tem limite ajustável; senão None."""
    if isinstance(entry, str):
        kind, _, arg = entry.partition("=")
        if kind in LIMITES and arg:
            return kind, float(arg)
    return None


def with_limit(entry: str, value: float) -> str:
    return f"{entry.partition('=')[0]}={value:g}"


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

    elif kind in LIMITES:
        limit = float(arg.replace(",", "."))
        sim = _Sim(regions, adj)
        if kind == "menores":
            while True:
                small = [i for i in sim.nb if sim.area[i] < limit and sim.nb[i]]
                if not small:
                    break
                a = min(small, key=lambda i: sim.area[i])
                same = [n for n in sim.nb[a] if sim.ignored[n] == sim.ignored[a]] or list(sim.nb[a])  # evita engolir o fundo
                sim.absorb(a, min(same, key=lambda n: sim.delta(a, n)))
        else:
            while True:
                pairs = [(sim.delta(a, b), a, b) for a in sim.nb for b in sim.nb[a]
                         if a < b and sim.ignored[a] == sim.ignored[b]]
                best = min((p for p in pairs if p[0] < limit), default=None)
                if best is None:
                    break
                sim.absorb(best[1], best[2])
        groups = sim.groups()
        if not groups:
            what = f"menos de {limit:g} mm²" if kind == "menores" else f"diferença de cor (ΔE) menor que {limit:g}"
            raise ValueError(f"nenhuma região com {what} (e com vizinha) para fundir")

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
