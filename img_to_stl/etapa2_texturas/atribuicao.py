"""Quem recebe qual textura: sugestão automática (vizinhas nunca repetem) e escolhas manuais."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..etapa1_reconhecimento.modelos import PlanarMap
from .biblioteca import TextureTransform
from .config import Etapa2Config


@dataclass
class TextureAssignment:
    texture_id: int
    amplitude_mm: float = 0.6
    transform: TextureTransform = field(default_factory=TextureTransform)


class TextureAssigner:
    """Decide a textura de cada região.

    Prioridade: escolha manual > fundo ignorado (lisa) > região lisa automática (`smooth_region`) > automática.
    Automática: regiões vizinhas NUNCA recebem a mesma textura e, enquanto houver textura livre,
    nenhuma textura se repete. Só repete quando há mais regiões que texturas em `default_textures`
    (e, mesmo assim, nunca entre vizinhas, se possível). Repetições manuais são respeitadas sem aviso.
    """

    def __init__(self, cfg: Etapa2Config):
        self.cfg = cfg
        self.warnings: List[str] = []

    @staticmethod
    def adjacency(pmap: PlanarMap) -> Dict[int, set]:
        """Regiões que se tocam (pixels vizinhos com rótulos diferentes)."""
        return pmap.adjacency()

    def smooth_region_id(self, pmap: PlanarMap, candidates: List[int], has_smooth: bool) -> Optional[int]:
        """Região que fica lisa na sugestão (ver `smooth_region`); None = nenhuma."""
        mode = str(self.cfg.smooth_region).strip()
        key = mode.lower()
        regions = {r.id: r for r in pmap.regions}
        if key in ("nenhuma", "nenhum", "none"):
            return None
        if key not in ("externa", "maior"):                       # nome ou número da região
            for r in pmap.regions:
                if mode == r.name or mode == str(r.id):
                    return r.id if r.id in candidates else None
            self.warnings.append(f"smooth_region '{mode}' não é nome/número de região: ignorado")
            return None
        if has_smooth or len(candidates) < 2:                     # já há lisa (fundo/manual) ou só uma região
            return None
        pool = [i for i in candidates if regions[i].touches_frame] if key == "externa" else []
        pool = pool or candidates
        return max(pool, key=lambda i: regions[i].area_mm2)

    def assign(self, pmap: PlanarMap, manual: Optional[Dict[int, TextureAssignment]] = None) -> Dict[int, TextureAssignment]:
        """Atribuição final: `manual` (id da região -> TextureAssignment) vale; o resto é sugerido."""
        cfg = self.cfg
        manual = manual or {}
        self.warnings = []
        out: Dict[int, TextureAssignment] = {}
        auto: List[int] = []
        for r in pmap.regions:
            if r.id in manual:
                out[r.id] = manual[r.id]
            elif r.ignored:
                out[r.id] = TextureAssignment(0, amplitude_mm=cfg.texture_amplitude_mm)
            else:
                auto.append(r.id)
        has_smooth = any(a.texture_id == 0 for a in out.values())
        smooth = self.smooth_region_id(pmap, auto, has_smooth)
        if smooth is not None:
            out[smooth] = TextureAssignment(0, amplitude_mm=cfg.texture_amplitude_mm)
            auto.remove(smooth)
        if not auto:
            return dict(sorted(out.items()))

        pool = [t for t in cfg.default_textures if t != 0] or [0]
        adj = self.adjacency(pmap)
        usage = Counter(a.texture_id for a in out.values() if a.texture_id != 0)
        chosen: Dict[int, int] = {}
        pending = set(auto)
        names = {r.id: r.name for r in pmap.regions}

        def neighbour_textures(rid: int) -> set:
            ts = {out[n].texture_id for n in adj[rid] if n in out}
            ts |= {chosen[n] for n in adj[rid] if n in chosen}
            ts.discard(0)
            return ts

        while pending:
            # a mais "apertada" primeiro: mais texturas já usadas por vizinhas, depois mais vizinhas
            rid = max(sorted(pending), key=lambda i: (len(neighbour_textures(i)), len(adj[i])))
            forbidden = neighbour_textures(rid)
            free = [t for t in pool if t not in forbidden]
            if free:
                tex = min(free, key=lambda t: (usage[t], pool.index(t)))
            else:
                tex = min(pool, key=lambda t: (sum(1 for n in adj[rid] if (chosen.get(n) or (out[n].texture_id if n in out else None)) == t),
                                               usage[t], pool.index(t)))
                self.warnings.append(
                    f"região {names[rid]}: todas as texturas sugeridas já são usadas por vizinhas; "
                    f"repetiu a textura {tex} (acrescente texturas em default_textures ou escolha à mão)")
            chosen[rid] = tex
            usage[tex] += 1
            pending.discard(rid)
        for rid, tex in chosen.items():
            out[rid] = TextureAssignment(tex, amplitude_mm=cfg.texture_amplitude_mm)
        if len(auto) > len(pool):
            self.warnings.append(
                f"{len(auto)} regiões e só {len(pool)} texturas sugeridas: algumas se repetem "
                f"(nunca entre vizinhas, quando possível).")
        return dict(sorted(out.items()))

    def neighbour_conflicts(self, pmap: PlanarMap, assignments: Dict[int, TextureAssignment]) -> List[str]:
        """Avisos para vizinhas com a mesma textura (permitido se for escolha manual, mas vale avisar)."""
        adj = self.adjacency(pmap)
        names = {r.id: r.name for r in pmap.regions}
        out = []
        for a, ns in adj.items():
            for b in ns:
                if a < b and assignments[a].texture_id == assignments[b].texture_id != 0 \
                        and assignments[a].transform == assignments[b].transform:
                    out.append(f"regiões vizinhas {names[a]} e {names[b]} com a mesma textura ({assignments[a].texture_id})")
        return out
