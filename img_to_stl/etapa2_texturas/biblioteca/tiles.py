"""Ida e volta com CAD: texturas a partir de arquivos (STL do FreeCAD ou PNG em tons de cinza).

Convenção de um tile em STL (feito no FreeCAD, Inventor, Blender...):
  - sólido com fundo plano e a superfície de cima sendo um relevo (sem sobreposições/cavidades);
  - eixos: XY = plano do tile, Z para cima, unidades em mm;
  - o tamanho do tile é a caixa XY do STL (ex.: 10 x 10 mm) e o padrão repete a cada tile.
A altura 0 é o ponto mais baixo da superfície de cima e 1 o mais alto; a amplitude real vem da
configuração (`texture_amplitude_mm`), então o mesmo tile serve com relevos diferentes.

PNG: tons de cinza, preto = baixo, branco = alto; tamanho do tile 10 mm (ou em <arquivo>.json).

Pasta de texturas personalizadas: arquivos `<id>_<nome>.stl|png` (ex.: `100_losango_duplo.stl`);
o id é o número usado em `--textures`. Use ids >= 100 (ids menores substituem as texturas internas).
"""
from __future__ import annotations

import json
import os
import re
import warnings
from functools import partial
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage

from .base import RidgeProfile, Texture
from .registro import TextureLibrary

SUFFIXES = (".stl", ".png", ".jpg", ".jpeg", ".bmp")


# --------------------------------------------------------------------------- #
# STL -> mapa de alturas
# --------------------------------------------------------------------------- #
def read_stl(path: str) -> np.ndarray:
    """Lê STL binário ou ASCII. Retorna triângulos (M, 3, 3)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(84)
        if len(head) == 84:
            n = int(np.frombuffer(head[80:84], dtype="<u4")[0])
            if size == 84 + 50 * n:
                dtype = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
                return np.frombuffer(f.read(), dtype=dtype, count=n)["v"].astype(np.float64)
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    verts = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    if not verts or len(verts) % 3:
        raise ValueError(f"STL inválido ou vazio: {path}")
    return np.array(verts, dtype=np.float64).reshape(-1, 3, 3)


def rasterize_top(tris: np.ndarray, res: float):
    """Z-buffer da superfície de cima: altura máxima das faces voltadas para +z em cada célula.

    Retorna (altura (ny, nx) com y crescendo com a linha, tamanho XY em mm, (z mínimo, z máximo)
    dos vértices da superfície de cima — extremos exatos, sem erro de amostragem).
    """
    pts = tris.reshape(-1, 3)
    ox, oy = pts[:, 0].min(), pts[:, 1].min()
    width, depth = pts[:, 0].max() - ox, pts[:, 1].max() - oy
    nx, ny = max(1, int(round(width / res))), max(1, int(round(depth / res)))
    zbuf = np.full((ny, nx), -np.inf)

    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    normal = np.cross(v1 - v0, v2 - v0)
    up = normal[:, 2] > 1e-6 * np.maximum(np.linalg.norm(normal, axis=1), 1e-30)
    eps = 1e-9
    for a, b, c in zip(v0[up], v1[up], v2[up]):
        j0 = max(0, int(np.floor((min(a[0], b[0], c[0]) - ox) / res - 0.5)))
        j1 = min(nx - 1, int(np.ceil((max(a[0], b[0], c[0]) - ox) / res - 0.5)))
        i0 = max(0, int(np.floor((min(a[1], b[1], c[1]) - oy) / res - 0.5)))
        i1 = min(ny - 1, int(np.ceil((max(a[1], b[1], c[1]) - oy) / res - 0.5)))
        if j1 < j0 or i1 < i0:
            continue
        gx, gy = np.meshgrid(ox + (np.arange(j0, j1 + 1) + 0.5) * res, oy + (np.arange(i0, i1 + 1) + 0.5) * res)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        l3 = 1.0 - l1 - l2
        inside = (l1 >= -eps) & (l2 >= -eps) & (l3 >= -eps)
        z = np.where(inside, l1 * a[2] + l2 * b[2] + l3 * c[2], -np.inf)
        sub = zbuf[i0:i1 + 1, j0:j1 + 1]
        np.maximum(sub, z, out=sub)

    holes = ~np.isfinite(zbuf)
    if holes.all():
        raise ValueError("Nenhuma face voltada para cima (+z) no STL.")
    if holes.any():   # triângulos mais finos que uma célula: preenche com o vizinho mais próximo
        idx = ndimage.distance_transform_edt(holes, return_indices=True)[1]
        zbuf = zbuf[tuple(idx)]
    top_z = tris[up][:, :, 2]
    return zbuf, (float(width), float(depth)), (float(top_z.min()), float(top_z.max()))


# --------------------------------------------------------------------------- #
# Textura a partir de mapa de alturas
# --------------------------------------------------------------------------- #
class TileTexture(Texture):
    """Mapa de alturas normalizado (0..1) que repete a cada `tile_mm` (interpolação bilinear, periódica)."""

    texture_id = -1
    name = "personalizada"

    def __init__(self, heightmap: np.ndarray, tile_mm: Tuple[float, float],
                 native_amplitude_mm: Optional[float] = None, name: str = "personalizada",
                 profile: Optional[RidgeProfile] = None):
        super().__init__(profile)
        self.h = np.clip(np.asarray(heightmap, dtype=np.float64), 0.0, 1.0)
        self.tile_mm = (float(tile_mm[0]), float(tile_mm[1]))
        self.native_amplitude_mm = native_amplitude_mm
        self.name = name
        ny, nx = self.h.shape
        self.dx, self.dy = self.tile_mm[0] / nx, self.tile_mm[1] / ny
        self.period_mm = max(self.tile_mm)

    def height(self, x, y):
        u = np.mod(x, self.tile_mm[0]) / self.dx - 0.5
        v = np.mod(y, self.tile_mm[1]) / self.dy - 0.5
        out = ndimage.map_coordinates(self.h, np.vstack([v.ravel(), u.ravel()]), order=1, mode="grid-wrap")
        return np.clip(out.reshape(np.shape(x)), 0.0, 1.0)

    def seam_ratio(self) -> float:
        """Salto na emenda / salto típico entre células vizinhas (≈1 se o tile é contínuo)."""
        def ratio(a, axis):
            seam = np.abs(np.take(a, 0, axis=axis) - np.take(a, -1, axis=axis)).mean()
            inner = np.abs(np.diff(a, axis=axis)).mean()
            return (seam + 1e-9) / (inner + 1e-9)
        return float(max(ratio(self.h, 1), ratio(self.h, 0)))

    # ---- carga ---- #
    @classmethod
    def from_file(cls, path: str, tile_mm: Optional[Tuple[float, float]] = None, res: float = 0.05,
                  name: Optional[str] = None) -> "TileTexture":
        name = name or os.path.splitext(os.path.basename(path))[0]
        sidecar = os.path.splitext(path)[0] + ".json"
        meta = {}
        if os.path.exists(sidecar):
            with open(sidecar, encoding="utf-8") as fh:
                meta = json.load(fh)
        declared = tuple(tile_mm or meta.get("tile_mm") or (10.0, 10.0))

        if path.lower().endswith(".stl"):
            zbuf, size, (lo, hi) = rasterize_top(read_stl(path), res)
            if tile_mm or "tile_mm" in meta:
                if abs(size[0] - declared[0]) > 0.01 * declared[0] or abs(size[1] - declared[1]) > 0.01 * declared[1]:
                    warnings.warn(f"{name}: caixa XY do STL é {size[0]:.2f} x {size[1]:.2f} mm, "
                                  f"mas o tile declarado é {declared[0]} x {declared[1]} mm (usando o STL).")
            native = hi - lo
            heights = (zbuf - lo) / native if native > 1e-9 else np.zeros_like(zbuf)
            tex = cls(heights, size, native, name)
        else:
            img = np.asarray(Image.open(path).convert("L"), dtype=np.float64) / 255.0
            tex = cls(img[::-1], declared, None, name)   # linha 0 da imagem = topo -> y máximo

        if tex.seam_ratio() > 4.0:
            warnings.warn(f"{name}: o tile não parece contínuo nas bordas (emenda visível ao repetir).")
        return tex


# --------------------------------------------------------------------------- #
# Pasta de texturas e exportação de modelos
# --------------------------------------------------------------------------- #
def load_directory(directory: str, res: float = 0.05) -> List[int]:
    """Registra no TextureLibrary os arquivos `<id>_<nome>.(stl|png...)` da pasta. Retorna os ids."""
    ids = []
    for fname in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(fname)
        m = re.match(r"^(\d+)_(.+)$", stem)
        if ext.lower() not in SUFFIXES or not m:
            continue
        tid, name = int(m.group(1)), m.group(2)
        if tid in TextureLibrary.describe() and tid < 100:
            warnings.warn(f"{fname}: id {tid} substitui a textura interna '{TextureLibrary.describe()[tid]}'.")
        path = os.path.join(directory, fname)

        def factory(path=path, name=name, profile=None, **params):
            return TileTexture.from_file(path, res=params.pop("res", res), name=name)

        TextureLibrary.register_factory(tid, name, factory, f"sua textura (arquivo {fname})")
        ids.append(tid)
    return ids


def export_texture_templates(directory: str, res: float = 0.1, amplitude_mm: float = 0.6,
                             plate_mm: float = 0.6, tile_mm: float = 10.0) -> List[str]:
    """Grava um tile de cada textura interna (STL fechado + PNG + JSON) para abrir/editar no CAD.

    O STL tem uma placa de `plate_mm` sob o relevo de `amplitude_mm`, tile de tile_mm x tile_mm.
    """
    from ..relevo import HeightField
    from ..stl import HeightfieldMesher

    os.makedirs(directory, exist_ok=True)
    written = []
    n = int(round(tile_mm / res))
    coords = np.arange(n + 1) * res
    X, Y = np.meshgrid(coords, coords)
    for tid, name in TextureLibrary.describe().items():
        if tid >= 100:
            continue
        tex = TextureLibrary.create(tid)
        h = tex.height(X, Y)
        base = os.path.join(directory, f"{tid:02d}_{name.replace(' ', '_').replace(chr(39), '')}")
        z = (plate_mm + amplitude_mm * h).astype(np.float32)
        HeightfieldMesher().build(HeightField(z=z, dx=res, dy=res)).save_stl(base + ".stl")
        Image.fromarray((255 * h[:-1, :-1][::-1]).round().astype(np.uint8)).save(base + ".png")
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump({"tile_mm": [tile_mm, tile_mm], "amplitude_mm": amplitude_mm, "plate_mm": plate_mm,
                       "origem": f"textura interna {tid} ({name})"}, fh, indent=2, ensure_ascii=False)
        written.append(base + ".stl")
    return written
