"""Malha estanque a partir do campo de alturas e escrita de STL binário (sem dependências extras)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from .relief import HeightField


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float32, mm
    faces: np.ndarray     # (M, 3) int32, anti-horário visto de fora (normais para fora)

    # ---- validação ---- #
    def validate(self) -> Dict[str, float]:
        """Checa se a malha é estanque (cada aresta usada 2x, em sentidos opostos) e calcula o volume."""
        f = self.faces.astype(np.int64)
        n = len(self.vertices)
        directed = np.concatenate([f[:, 0] * n + f[:, 1], f[:, 1] * n + f[:, 2], f[:, 2] * n + f[:, 0]])
        reverse = np.concatenate([f[:, 1] * n + f[:, 0], f[:, 2] * n + f[:, 1], f[:, 0] * n + f[:, 2]])
        directed.sort()
        reverse.sort()
        unique_directed = bool(np.all(np.diff(directed) != 0))          # nenhuma aresta repetida no mesmo sentido
        closed = bool(np.array_equal(directed, reverse))               # toda aresta tem a oposta
        v = self.vertices.astype(np.float64)
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
        return {"estanque": unique_directed and closed, "volume_mm3": volume,
                "vertices": n, "triangulos": len(f)}

    # ---- escrita ---- #
    def save_stl(self, path: str, name: str = "img2stl") -> None:
        tris = self.vertices[self.faces]                    # (M, 3, 3)
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 0)
        dtype = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        data = np.empty(len(tris), dtype=dtype)
        data["n"], data["v"], data["attr"] = normals, tris, 0
        with open(path, "wb") as fh:
            fh.write(name.encode("ascii", "ignore")[:79].ljust(80, b" "))
            fh.write(np.uint32(len(tris)).tobytes())
            fh.write(data.tobytes())


class HeightfieldMesher:
    """Sólido fechado: superfície de cima (a partir do campo de alturas), 4 paredes e fundo plano."""

    def build(self, hf: HeightField) -> Mesh:
        z = hf.z.astype(np.float32)
        ny, nx = z.shape
        xs = np.arange(nx, dtype=np.float32) * hf.dx
        ys = np.arange(ny, dtype=np.float32) * hf.dy
        X, Y = np.meshgrid(xs, ys)
        top = np.stack([X.ravel(), Y.ravel(), z.ravel()], axis=1)
        idx = np.arange(nx * ny, dtype=np.int64).reshape(ny, nx)

        # --- superfície de cima: 2 triângulos por célula; diagonal escolhida pela menor variação
        #     de altura (segue cristas diagonais sem serrilhar) ---
        p00, p10, p01, p11 = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
        z00, z10, z01, z11 = z[:-1, :-1], z[:-1, 1:], z[1:, :-1], z[1:, 1:]
        use_main = np.abs(z00 - z11) <= np.abs(z10 - z01)
        t1 = np.where(use_main[..., None], np.stack([p00, p10, p11], -1), np.stack([p00, p10, p01], -1))
        t2 = np.where(use_main[..., None], np.stack([p00, p11, p01], -1), np.stack([p10, p11, p01], -1))
        faces = [t1.reshape(-1, 3), t2.reshape(-1, 3)]

        # --- anel de borda (anti-horário visto de cima) ---
        ring = np.concatenate([idx[0, :-1], idx[:-1, -1], idx[-1, :0:-1], idx[:0:-1, 0]])
        n_ring = len(ring)
        base = nx * ny
        bottom_ring = base + np.arange(n_ring, dtype=np.int64)
        center = base + n_ring
        ring_xyz = top[ring].copy()
        ring_xyz[:, 2] = 0.0
        center_xyz = np.array([[(nx - 1) * hf.dx / 2.0, (ny - 1) * hf.dy / 2.0, 0.0]], dtype=np.float32)

        a, b = ring, np.roll(ring, -1)
        a_b, b_b = bottom_ring, np.roll(bottom_ring, -1)
        faces.append(np.stack([a_b, b_b, b], 1))          # paredes (2 triângulos por segmento)
        faces.append(np.stack([a_b, b, a], 1))
        faces.append(np.stack([np.full(n_ring, center), b_b, a_b], 1))  # fundo: leque a partir do centro

        vertices = np.vstack([top, ring_xyz, center_xyz]).astype(np.float32)
        return Mesh(vertices=vertices, faces=np.vstack(faces).astype(np.int32))
