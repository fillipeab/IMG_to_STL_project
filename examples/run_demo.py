"""Demo: gera uma imagem sintética e roda as duas etapas.  python examples/run_demo.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from img_to_stl import ImageToStl, PipelineConfig  # noqa: E402
import make_demo_image  # noqa: E402

here = os.path.dirname(os.path.abspath(__file__))
img = os.path.join(here, "demo.png")
make_demo_image.make(img)

cfg = PipelineConfig()
cfg.base_dir = os.path.join(here, "repositorio")
cfg.stl_dir = os.path.join(here, "saidas")
cfg.etapa1.width_mm = 100.0
cfg.etapa2.resolution_mm = 0.15           # 0.1 para a versão final (arquivo maior)

app = ImageToStl(cfg, log=print)
pmap = app.run_etapa1(img)                # repositorio/demo/etapa1_reconhecimento/...
# Aqui você pode abrir repositorio/demo/etapa2_texturas/texturas.json depois da 1ª execução e editar as texturas.
app.run_etapa2(os.path.join(cfg.base_dir, "demo"), pmap)
