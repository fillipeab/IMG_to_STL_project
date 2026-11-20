"""Etapa 1 completa: imagem -> PlanarMap (+ pasta de saída)."""
from __future__ import annotations

import time
from typing import Callable, Optional

from .config import Etapa1Config
from .leitor import ImageReader
from .modelos import PlanarMap
from .saida import save_stage1


class Etapa1:
    """Uso:  pmap = Etapa1(cfg).run("imagem.png", out_dir="repositorio/imagem/etapa1_reconhecimento")"""

    def __init__(self, config: Optional[Etapa1Config] = None, log: Optional[Callable[[str], None]] = None):
        self.config = config or Etapa1Config()
        self.log = log or (lambda msg: None)
        self.warnings = []

    def run(self, image_path: str, out_dir: Optional[str] = None, negatives: bool = True) -> PlanarMap:
        t0 = time.time()
        reader = ImageReader(self.config)
        pmap = reader.read(image_path)
        self.warnings = reader.warnings
        self.log(f"[etapa 1] {pmap.summary()}  ({time.time() - t0:.1f}s)")
        for w in self.warnings:
            self.log(f"[aviso] {w}")
        if out_dir:
            t1 = time.time()
            save_stage1(pmap, self.config, out_dir, self.warnings, negatives)
            self.log(f"[etapa 1] resultados gravados em {out_dir}  ({time.time() - t1:.1f}s)")
        return pmap
