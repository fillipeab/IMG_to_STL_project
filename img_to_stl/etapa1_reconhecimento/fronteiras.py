"""Fronteiras: traçado nas "frestas" entre pixels (topologia exata: regiões vizinhas dividem a MESMA
curva), suavização, simplificação e contração de fronteiras curtas (a rede nunca fica com fresta)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import cv2
import numpy as np
from scipy import ndimage


@dataclass
class Chain:
    label_a: int
    label_b: int
    pts_px: np.ndarray  # (N, 2) em px da imagem (x, y com y para baixo)
    closed: bool


class BorderTracer:
    """Extrai fronteiras como cadeias de "frestas" entre pixels.

    Cada fresta separa dois pixels de rótulos diferentes; os vértices são cantos de pixel.
    Vértices de grau 2 pertencem ao meio de uma cadeia; grau 3+ são junções da rede de fronteiras.
    Como duas regiões vizinhas usam a mesma cadeia, não há frestas nem sobreposições.
    """

    def __init__(self, labels: np.ndarray, smooth_sigma_px: float, simplify_tol_px: float):
        self.labels = labels
        self.sigma = smooth_sigma_px
        self.tol = simplify_tol_px

    def trace(self) -> List[Chain]:
        """Retorna as cadeias de fronteira (entre vértices de grau != 2)."""
        P = np.pad(self.labels, 1, constant_values=-1)
        Hp, Wp = P.shape
        Wv = Wp + 1

        ks, js = np.nonzero(P[1:, :] != P[:-1, :])            # fresta horizontal entre linhas k e k+1
        hu, hv = (ks + 1) * Wv + js, (ks + 1) * Wv + js + 1
        ha, hb = P[ks, js], P[ks + 1, js]
        is_, ks2 = np.nonzero(P[:, 1:] != P[:, :-1])          # fresta vertical entre colunas k e k+1
        vu, vv = is_ * Wv + ks2 + 1, (is_ + 1) * Wv + ks2 + 1
        va, vb = P[is_, ks2], P[is_, ks2 + 1]

        u = np.concatenate([hu, vu])
        v = np.concatenate([hv, vv])
        lo = np.minimum(np.concatenate([ha, va]), np.concatenate([hb, vb]))
        hi = np.maximum(np.concatenate([ha, va]), np.concatenate([hb, vb]))
        n_edges = len(u)
        n_vert = (Hp + 1) * Wv
        if n_edges == 0:
            return []

        ends = np.concatenate([u, v])
        eids = np.concatenate([np.arange(n_edges), np.arange(n_edges)])
        order = np.argsort(ends, kind="stable")
        seid = eids[order]
        deg = np.bincount(ends, minlength=n_vert)
        ptr = np.zeros(n_vert + 1, dtype=np.int64)
        ptr[1:] = np.cumsum(deg)

        # --- cadeias ---
        ul, vl, lol, hil = u.tolist(), v.tolist(), lo.tolist(), hi.tolist()
        degl, ptrl, seidl = deg.tolist(), ptr.tolist(), seid.tolist()
        visited = bytearray(n_edges)
        chains: List[Chain] = []

        def walk(start: int, e: int) -> None:
            ids = [start]
            cur, first = start, e
            while True:
                visited[e] = 1
                nxt = vl[e] if ul[e] == cur else ul[e]
                ids.append(nxt)
                if degl[nxt] != 2 or nxt == start:
                    break
                a = ptrl[nxt]
                e1, e2 = seidl[a], seidl[a + 1]
                e = e2 if e1 == e else e1
                if visited[e]:
                    break
                cur = nxt
            arr = np.asarray(ids)
            pts = np.stack([(arr % Wv) - 1, (arr // Wv) - 1], axis=1).astype(float)
            # laço que começa numa junção (grau >= 3) NÃO é um laço livre: as pontas precisam ficar
            # fixas na junção, senão a suavização abre uma fresta no cordão
            closed = ids[0] == ids[-1] and degl[start] == 2
            chains.append(self._refine(Chain(lol[first], hil[first], pts, closed)))

        for x in np.nonzero((deg != 2) & (deg > 0))[0].tolist():
            for k in range(ptrl[x], ptrl[x + 1]):
                if not visited[seidl[k]]:
                    walk(x, seidl[k])
        for e in range(n_edges):          # laços fechados sem junção (ilhas)
            if not visited[e]:
                walk(ul[e], e)
        return chains

    def _refine(self, ch: Chain) -> Chain:
        """Suaviza (remove a 'escada') mantendo as pontas fixas e simplifica (Douglas-Peucker)."""
        pts = ch.pts_px
        sigma = 0.0 if ch.label_a == -1 else self.sigma   # moldura externa: mantém cantos retos
        if ch.closed:
            core = pts[:-1]
            if len(core) >= 8 and sigma > 0:
                core = np.stack([ndimage.gaussian_filter1d(core[:, c], sigma, mode="wrap")
                                 for c in range(2)], axis=1)
            simp = cv2.approxPolyDP(core.astype(np.float32).reshape(-1, 1, 2), self.tol, True)
            simp = simp.reshape(-1, 2).astype(float)
            simp = np.vstack([simp, simp[:1]])
        else:
            core = pts
            if len(core) >= 6 and sigma > 0:
                sm = np.stack([ndimage.gaussian_filter1d(core[:, c], sigma, mode="nearest")
                               for c in range(2)], axis=1)
                sm[0], sm[-1] = core[0], core[-1]
                core = sm
            simp = cv2.approxPolyDP(core.astype(np.float32).reshape(-1, 1, 2), self.tol, False)
            simp = simp.reshape(-1, 2).astype(float)
        return Chain(ch.label_a, ch.label_b, simp, ch.closed)


def contract_short(chains: List[Chain], mpp: float, min_border_length_mm: float) -> List[Chain]:
    """Garante fronteiras contínuas. Uma fronteira curta entre duas junções NÃO é apagada (abriria
    uma fresta na rede): ela é "encolhida" — as duas junções viram uma só, no meio, e as demais
    fronteiras passam a terminar ali. Só somem laços livres curtos (ilhotas) e laços curtos presos
    a uma única junção."""
    min_px = min_border_length_mm / mpp
    if min_px <= 0:
        return chains

    def length(c: Chain) -> float:
        d = np.diff(c.pts_px, axis=0)
        return float(np.hypot(d[:, 0], d[:, 1]).sum())

    def key(p) -> Tuple[int, int]:
        return int(round(p[0])), int(round(p[1]))

    parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
    members: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}

    def find(a):
        parent.setdefault(a, a)
        members.setdefault(a, [a])
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def extent(vs) -> float:
        xy = np.array(vs, dtype=float)
        return float(np.hypot(*(xy.max(axis=0) - xy.min(axis=0))))

    drop = set()
    short = sorted((i for i, c in enumerate(chains) if c.label_a != -1 and length(c) < min_px),
                   key=lambda i: length(chains[i]))
    for i in short:
        c = chains[i]
        if c.closed or key(c.pts_px[0]) == key(c.pts_px[-1]):
            drop.add(i)                                   # ilhota / laço curto preso a uma junção
            continue
        ra, rb = find(key(c.pts_px[0])), find(key(c.pts_px[-1]))
        if ra == rb:
            drop.add(i)
            continue
        if extent(members[ra] + members[rb]) <= min_px:   # evita colapsar uma curva longa
            parent[rb] = ra
            members[ra] += members.pop(rb)
            drop.add(i)

    centre = {r: np.mean(np.array(v, dtype=float), axis=0) for r, v in members.items() if len(v) > 1}
    out = []
    for i, c in enumerate(chains):
        if i in drop:
            continue
        if not c.closed:
            pts = c.pts_px.copy()
            for end in (0, -1):
                r = find(key(pts[end])) if key(pts[end]) in parent else None
                if r is not None and r in centre:
                    pts[end] = centre[r]
            c = Chain(c.label_a, c.label_b, pts, c.closed)
        out.append(c)
    return out
