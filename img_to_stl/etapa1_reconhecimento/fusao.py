"""Fusão de regiões: grafo de adjacência com união incremental (áreas pequenas e cores parecidas)."""
from __future__ import annotations

import heapq
from typing import Dict, List

import numpy as np


class RegionGraph:
    """Regiões + adjacência com fusão incremental (união de vizinhas)."""

    def __init__(self, labels: np.ndarray, lab: np.ndarray):
        n = int(labels.max()) + 1
        flat = labels.ravel()
        self.area = np.bincount(flat, minlength=n).astype(float)
        self.sum = np.stack(
            [np.bincount(flat, weights=lab[..., c].ravel(), minlength=n) for c in range(3)], axis=1)
        self.alive = np.ones(n, dtype=bool)
        self.version = np.zeros(n, dtype=np.int64)
        self.parent = np.arange(n)
        self.n_alive = n
        self.adj: List[Dict[int, int]] = [dict() for _ in range(n)]

        pairs = []
        for a, b in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
            m = a != b
            lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
            pairs.append(lo.astype(np.int64) * n + hi)
        if pairs:
            keys, counts = np.unique(np.concatenate(pairs), return_counts=True)
            for k, c in zip(keys.tolist(), counts.tolist()):
                a, b = divmod(k, n)
                self.adj[a][b] = c
                self.adj[b][a] = c

    def mean(self, i: int) -> np.ndarray:
        return self.sum[i] / self.area[i]

    def delta(self, i: int, j: int) -> float:
        return float(np.linalg.norm(self.mean(i) - self.mean(j)))

    def merge(self, a: int, b: int) -> None:
        """Funde a região `a` dentro de `b`."""
        for nb, cnt in self.adj[a].items():
            if nb == b:
                continue
            self.adj[nb].pop(a, None)
            self.adj[nb][b] = self.adj[nb].get(b, 0) + cnt
            self.adj[b][nb] = self.adj[b].get(nb, 0) + cnt
        self.adj[b].pop(a, None)
        self.adj[a] = {}
        self.alive[a] = False
        self.parent[a] = b
        self.area[b] += self.area[a]
        self.sum[b] += self.sum[a]
        self.version[b] += 1
        self.n_alive -= 1

    def merge_small(self, min_area_px: float) -> None:
        """Absorve regiões menores que min_area_px na vizinha de cor mais próxima."""
        heap = [(self.area[i], i) for i in range(len(self.area)) if self.alive[i]]
        heapq.heapify(heap)
        while heap:
            area, i = heapq.heappop(heap)
            if not self.alive[i] or area != self.area[i]:
                continue
            if area >= min_area_px:
                break
            if not self.adj[i]:
                continue
            best = min(self.adj[i], key=lambda j: (self.delta(i, j), -self.adj[i][j]))
            self.merge(i, best)
            heapq.heappush(heap, (self.area[best], best))

    def merge_similar(self, tolerance: float, max_regions: int) -> None:
        """Funde as vizinhas mais parecidas enquanto ΔE < tolerância OU houver regiões demais."""
        heap = []

        def push(a, b):
            heapq.heappush(heap, (self.delta(a, b), a, b, self.version[a], self.version[b]))

        for a in range(len(self.adj)):
            if self.alive[a]:
                for b in self.adj[a]:
                    if a < b:
                        push(a, b)
        while heap:
            d, a, b, va, vb = heapq.heappop(heap)
            if not (self.alive[a] and self.alive[b]) or self.version[a] != va or self.version[b] != vb:
                continue
            if d >= tolerance and self.n_alive <= max_regions:
                break
            small, big = (a, b) if self.area[a] <= self.area[b] else (b, a)
            self.merge(small, big)
            for nb in self.adj[big]:
                push(min(big, nb), max(big, nb))

    def roots(self) -> np.ndarray:
        """Para cada id original, o id da região em que foi fundida."""
        root = self.parent.copy()
        for i in range(len(root)):
            r = i
            while root[r] != r:
                r = root[r]
            j = i
            while root[j] != r:
                root[j], j = r, root[j]
        return root
