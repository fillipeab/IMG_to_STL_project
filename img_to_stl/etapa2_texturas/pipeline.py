"""Etapa 2 completa: PlanarMap + texturas escolhidas -> relevo -> STL (+ prévia e relatório)."""
from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from ..comum.arquivos import ensure
from ..etapa1_reconhecimento.modelos import PlanarMap
from .atribuicao import TextureAssigner, TextureAssignment
from .biblioteca import TextureLibrary
from .config import Etapa2Config
from .relevo import HeightField, ReliefBuilder
from .saida import report_text
from .stl import HeightfieldMesher, Mesh
from .texturas_arquivo import load_texture_file, save_texture_file, signature

TEXTURE_FILE = "texturas.json"


class Etapa2:
    """Uso típico:

        e2 = Etapa2(cfg, log=print)
        e2.prepare_textures(pmap, out_dir)          # sugere e grava texturas.json (ou lê o existente)
        # ... a pessoa edita texturas.json (ou o CLI interativo muda as linhas) ...
        e2.run(pmap, out_dir)                       # relevo -> modelo.stl
    """

    def __init__(self, config: Optional[Etapa2Config] = None, log: Optional[Callable[[str], None]] = None):
        self.config = config or Etapa2Config()
        self.log = log or (lambda msg: None)
        self.warnings: List[str] = []

    # ---- texturas.json ---- #
    def prepare_textures(self, pmap: PlanarMap, out_dir: str,
                         textures_file: Optional[str] = None) -> Tuple[str, Dict[int, TextureAssignment]]:
        """Garante o arquivo de texturas. Existe e combina com a etapa 1 -> lê. Senão -> sugere e grava.
        Retorna (caminho, atribuição manual lida/sugerida por região)."""
        cfg = self.config
        ensure(out_dir)
        if cfg.texture_dir:
            TextureLibrary.load_directory(cfg.texture_dir)
        path = textures_file or os.path.join(out_dir, TEXTURE_FILE)
        if os.path.exists(path):
            manual, warns = load_texture_file(path, pmap, cfg.texture_amplitude_mm)
            if not any("outro resultado" in w for w in warns):
                for w in warns:
                    self.log(f"[aviso] {w}")
                full = TextureAssigner(cfg).assign(pmap, manual)
                return path, full
            self.log(f"[aviso] {TEXTURE_FILE} era de outro resultado da etapa 1: gerando nova sugestão "
                     f"(o antigo foi guardado como {os.path.basename(path)}.antigo)")
            os.replace(path, path + ".antigo")
        assigner = TextureAssigner(cfg)
        suggestion = assigner.assign(pmap)
        for w in assigner.warnings:
            self.log(f"[aviso] {w}")
        save_texture_file(path, pmap, suggestion, cfg.texture_amplitude_mm)
        self.log(f"[etapa 2] sugestão de texturas gravada em {path}")
        return path, suggestion

    # ---- geração ---- #
    def build_heightfield(self, pmap: PlanarMap, assignments: Dict[int, TextureAssignment]) -> HeightField:
        t0 = time.time()
        builder = ReliefBuilder(pmap, self.config, assignments)
        for w in builder.warnings:
            self.log(f"[aviso] {w}")
        self.warnings = list(builder.warnings)
        hf = builder.build()
        w, h = hf.size_mm
        self.log(f"[etapa 2] campo de alturas {hf.z.shape[1]}x{hf.z.shape[0]} nós, {w:.1f} x {h:.1f} mm, "
                 f"altura máx {hf.z.max():.2f} mm  ({time.time() - t0:.1f}s)")
        self.assignments = builder.assignments
        return hf

    def export(self, hf: HeightField, stl_path: str) -> Tuple[Mesh, Dict[str, float]]:
        t0 = time.time()
        mesh = HeightfieldMesher().build(hf)
        info = mesh.validate()
        if not info["estanque"]:
            raise RuntimeError("A malha gerada não é estanque (bug); STL não salvo.")
        mesh.save_stl(stl_path)
        self.log(f"[etapa 2] {info['triangulos']:,} triângulos, volume {info['volume_mm3']:.0f} mm³, "
                 f"{os.path.getsize(stl_path) / 1e6:.1f} MB -> {stl_path}  ({time.time() - t0:.1f}s)")
        return mesh, info

    def run(self, pmap: PlanarMap, out_dir: str, stl_path: Optional[str] = None,
            textures_file: Optional[str] = None) -> Mesh:
        """`stl_path`: onde gravar o STL (padrão: <out_dir>/modelo.stl)."""
        ensure(out_dir)
        stl_path = stl_path or os.path.join(out_dir, "modelo.stl")
        ensure(os.path.dirname(os.path.abspath(stl_path)))
        _, manual = self.prepare_textures(pmap, out_dir, textures_file)
        self.config.to_json(os.path.join(out_dir, "parametros.json"))
        hf = self.build_heightfield(pmap, manual)
        hf.save_shaded_preview(os.path.join(out_dir, "previa_relevo.png"))
        mesh, info = self.export(hf, stl_path)
        with open(os.path.join(out_dir, "relatorio.txt"), "w", encoding="utf-8") as f:
            f.write(report_text(pmap, self.config, self.assignments, info, self.warnings, hf.size_mm, os.path.abspath(stl_path)))
        return mesh
