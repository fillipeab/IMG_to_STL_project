"""Orquestra as partes 1 e 2: imagem -> PlanarMap -> campo de alturas -> STL."""
from __future__ import annotations

import os
import time
from typing import Optional, Tuple

from .config import PipelineConfig
from .relief import HeightField, ReliefBuilder
from .stl_export import HeightfieldMesher, Mesh
from .negatives import NegativeRenderer
from .vision import ImageReader, PlanarMap


def resolve_outputs(image_path: str, output: Optional[str] = None, base_dir: str = "saida") -> Tuple[str, str]:
    """Define (pasta de saída, caminho do STL) para uma imagem.

    - output None            -> <base_dir>/<nome_da_imagem>/<nome_da_imagem>.stl
    - output termina em .stl -> esse caminho exato; o resto vai na mesma pasta
    - output = pasta         -> <pasta>/<nome_da_imagem>/<nome_da_imagem>.stl
    """
    stem = os.path.splitext(os.path.basename(image_path))[0]
    if output and output.lower().endswith(".stl"):
        return os.path.dirname(os.path.abspath(output)), output
    out_dir = os.path.join(output or base_dir, stem)
    return out_dir, os.path.join(out_dir, stem + ".stl")


class ImageToReliefPipeline:
    """Uso típico:

        pipe = ImageToReliefPipeline(PipelineConfig())
        pmap = pipe.read("imagem.png", out_dir="saida")      # parte 1 (+ preview com os ids das regiões)
        pipe.run("imagem.png")                               # tudo, em saida/imagem/ (STL + previews + negativos)
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
            if self.config.output.negatives:
                t1 = time.time()
                NegativeRenderer(pmap, self.config.relief, self.config.output).save(os.path.join(out_dir, "negativos"))
                self._log(f"[negativos] regioes, fronteiras, pontos e composto em {out_dir}/negativos  "
                          f"({time.time() - t1:.1f}s)")
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

    def run(self, image_path: str, stl_path: Optional[str] = None, out_dir: Optional[str] = None) -> Mesh:
        if stl_path is None:
            auto_dir, stl_path = resolve_outputs(image_path, None, self.config.output.base_dir)
            out_dir = out_dir or auto_dir
        out_dir = out_dir or os.path.dirname(os.path.abspath(stl_path))
        os.makedirs(out_dir, exist_ok=True)
        pmap = self.read(image_path, out_dir)
        hf = self.build_heightfield(pmap)
        hf.save_shaded_preview(os.path.join(out_dir, "relevo_preview.png"))
        mesh = self.export(hf, stl_path)
        self._log(f"[saída] tudo em: {os.path.abspath(out_dir)}")
        return mesh
