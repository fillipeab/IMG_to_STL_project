"""Orquestra as partes 1 e 2: imagem -> PlanarMap -> campo de alturas -> STL."""
from __future__ import annotations

import os
import time
from typing import Optional

from .config import PipelineConfig
from .relief import HeightField, ReliefBuilder
from .stl_export import HeightfieldMesher, Mesh
from .vision import ImageReader, PlanarMap


class ImageToReliefPipeline:
    """Uso típico:

        pipe = ImageToReliefPipeline(PipelineConfig())
        pmap = pipe.read("imagem.png", out_dir="saida")      # parte 1 (+ preview com os ids das regiões)
        pipe.run("imagem.png", "saida/peca.stl")             # tudo
    """

    def __init__(self, config: Optional[PipelineConfig] = None, verbose: bool = True):
        self.config = config or PipelineConfig()
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ---- etapas ---- #
    def read(self, image_path: str, out_dir: Optional[str] = None) -> PlanarMap:
        t0 = time.time()
        pmap = ImageReader(self.config.vision).read(image_path)
        self._log(f"[parte 1] {pmap.summary()}  ({time.time() - t0:.1f}s)")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            pmap.render_preview(os.path.join(out_dir, "regioes_preview.png"))
            pmap.save_json(os.path.join(out_dir, "mapa.json"), include_geometry=True)
        return pmap

    def build_heightfield(self, pmap: PlanarMap) -> HeightField:
        t0 = time.time()
        builder = ReliefBuilder(pmap, self.config.relief)
        for w in builder.warnings:
            self._log(f"[aviso] {w}")
        hf = builder.build()
        w, h = hf.size_mm
        self._log(f"[parte 2] campo de alturas {hf.z.shape[1]}x{hf.z.shape[0]} nós, peça {w:.1f} x {h:.1f} mm, "
                  f"altura máx {hf.z.max():.2f} mm  ({time.time() - t0:.1f}s)")
        return hf

    def export(self, hf: HeightField, stl_path: str) -> Mesh:
        t0 = time.time()
        mesh = HeightfieldMesher().build(hf)
        info = mesh.validate()
        if not info["estanque"]:
            raise RuntimeError("A malha gerada não é estanque (bug); STL não salvo.")
        mesh.save_stl(stl_path)
        size_mb = os.path.getsize(stl_path) / 1e6
        self._log(f"[stl] {info['triangulos']:,} triângulos, volume {info['volume_mm3']:.0f} mm³, "
                  f"{size_mb:.1f} MB -> {stl_path}  ({time.time() - t0:.1f}s)")
        return mesh

    def run(self, image_path: str, stl_path: str, out_dir: Optional[str] = None) -> Mesh:
        out_dir = out_dir or os.path.dirname(os.path.abspath(stl_path))
        pmap = self.read(image_path, out_dir)
        hf = self.build_heightfield(pmap)
        hf.save_shaded_preview(os.path.join(out_dir, "relevo_preview.png"))
        return self.export(hf, stl_path)
