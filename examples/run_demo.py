"""Demo: gera uma imagem sintética e roda o pipeline completo.  python examples/run_demo.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from img_to_stl import ImageToReliefPipeline, PipelineConfig  # noqa: E402
import make_demo_image  # noqa: E402

here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "saida")
os.makedirs(out, exist_ok=True)
img = os.path.join(here, "demo.png")
make_demo_image.make(img)

cfg = PipelineConfig()
cfg.vision.width_mm = 100.0
cfg.relief.resolution_mm = 0.15           # 0.1 para a versão final (arquivo maior)
cfg.relief.region_textures = {0: 1, 1: 2, 2: 3, 3: 4}   # id da região -> id da textura
cfg.to_json(os.path.join(out, "config_usada.json"))

ImageToReliefPipeline(cfg).run(img, os.path.join(out, "peca.stl"), out_dir=out)
