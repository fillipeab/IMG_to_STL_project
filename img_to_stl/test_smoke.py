"""Testes de fumaça. Rode:  python tests/test_smoke.py   (ou pytest)"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from img2stl import ImageToReliefPipeline, PipelineConfig, TextureLibrary  # noqa: E402
from img2stl.stl_export import HeightfieldMesher  # noqa: E402
from img2stl.relief import HeightField  # noqa: E402
import make_demo_image  # noqa: E402


def test_textures_periodic_and_normalized():
    res = 0.05
    xs = (np.arange(400) + 0.5) * res
    X, Y = np.meshgrid(xs, xs)
    for tid in TextureLibrary.describe():
        tex = TextureLibrary.create(tid)
        full = tex.height(X, Y)
        tiled = np.tile(tex.tile(10.0, res), (2, 2))
        assert np.abs(full - tiled).max() < 1e-9, f"textura {tid} não é periódica em 10 mm"
        assert full.min() >= 0.0 and full.max() <= 1.0


def test_mesh_is_watertight_and_volume_matches():
    z = np.random.default_rng(0).uniform(1, 2, (30, 40)).astype(np.float32)
    mesh = HeightfieldMesher().build(HeightField(z=z, dx=0.5, dy=0.5))
    info = mesh.validate()
    assert info["estanque"]
    # volume por trapézios nas células vs. malha (a diagonal muda pouco o volume)
    cell = (z[:-1, :-1] + z[:-1, 1:] + z[1:, :-1] + z[1:, 1:]) / 4.0 * 0.25
    assert abs(info["volume_mm3"] - cell.sum()) / cell.sum() < 0.02


def test_pipeline_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "demo.png")
        make_demo_image.make(img)
        cfg = PipelineConfig()
        cfg.relief.resolution_mm = 0.25
        pipe = ImageToReliefPipeline(cfg, verbose=False)
        pmap = pipe.read(img, out_dir=d)
        assert len(pmap.regions) == 7, "esperado: 6 células + 1 ilha (o ponto minúsculo deve sumir)"
        assert len(pmap.points) == 0          # pontos de interesse ainda não são detectados
        assert any(b.outer for b in pmap.borders), "moldura externa deveria existir"
        stl = os.path.join(d, "peca.stl")
        mesh = pipe.run(img, stl)
        assert os.path.getsize(stl) == 84 + 50 * len(mesh.faces)


def test_transform_scale_stretch_rotation():
    from img2stl import TextureTransform, TransformedTexture
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 30, 5000), rng.uniform(0, 30, 5000)
    base = TextureLibrary.create(3)
    ident = TransformedTexture(base, TextureTransform())
    assert np.allclose(ident.height(x, y), base.height(x, y))
    big = TransformedTexture(base, TextureTransform(scale=2.0))
    assert np.allclose(big.height(x, y), base.height(x / 2.0, y / 2.0))          # ampliar 2x
    rot = TransformedTexture(base, TextureTransform(rotation_deg=90))
    assert np.allclose(rot.height(x, y), base.height(y, -x))                     # girar 90° anti-horário
    st = TextureTransform(stretch=2.0, stretch_angle_deg=0.0)
    assert np.allclose(st.apply(x, y)[0], x / 2.0) and np.allclose(st.apply(x, y)[1], y)  # esticar em x
    # aviso de traço fino: textura 1 (traço 0.8) com scale 0.4 -> 0.32 mm
    assert TransformedTexture(TextureLibrary.create(1), TextureTransform(scale=0.4)).min_feature_mm < 0.4


def test_cad_roundtrip_stl_and_png():
    from img2stl import TileTexture, export_texture_templates
    with tempfile.TemporaryDirectory() as d:
        export_texture_templates(d)
        rng = np.random.default_rng(1)
        x, y = rng.uniform(0, 40, 5000), rng.uniform(0, 40, 5000)
        for tid, fname in ((2, "02_Xs"), (5, "05_losangos")):
            ref = TextureLibrary.create(tid).height(x, y)
            stl = TileTexture.from_file(os.path.join(d, fname + ".stl"))
            assert abs(stl.native_amplitude_mm - 0.6) < 1e-3 and stl.tile_mm == (10.0, 10.0)
            assert np.abs(stl.height(x, y) - ref).mean() < 0.02
            png = TileTexture.from_file(os.path.join(d, fname + ".png"))
            assert np.abs(png.height(x, y) - ref).mean() < 0.08

def test_negativos_pastas_e_suavizacao():
    """Saída em subpasta por imagem, negativos gerados e textura reduzida na zona de exclusão."""
    import cv2
    from img2stl.pipeline import resolve_outputs
    import make_demo_image
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "minha_imagem.png")
        make_demo_image.make(img)
        out_dir, stl = resolve_outputs(img, d)
        assert out_dir == os.path.join(d, "minha_imagem") and stl.endswith("minha_imagem.stl")
        cfg = PipelineConfig()
        cfg.relief.resolution_mm = 0.4
        pipe = ImageToReliefPipeline(cfg, verbose=False)
        pipe.run(img, stl, out_dir)
        neg = os.path.join(out_dir, "negativos")
        for f in ("regioes.png", "fronteiras.png", "pontos.png", "composto.png"):
            assert (cv2.imread(os.path.join(neg, f), cv2.IMREAD_UNCHANGED) is not None), f
        pts = cv2.imread(os.path.join(neg, "pontos.png"), 0)
        assert (pts > 0).sum() == 0            # sem pontos de interesse detectados, a máscara fica vazia
        # suavização: com a textura reduzida a zona de exclusão deixa de ser lisa
        pm = pipe.read(img)
        zs = []
        for sc in (0.0, 0.5):
            c = PipelineConfig(); c.relief.resolution_mm = 0.2; c.relief.exclusion_texture_scale = sc
            zs.append(ImageToReliefPipeline(c, verbose=False).build_heightfield(pm).z)
        assert not np.allclose(zs[0], zs[1])
        assert zs[1].max() <= zs[0].max() + 1e-6          # a reduzida nunca passa a textura normal


def _dangling_ends(pmap):
    import collections
    cnt = collections.Counter()
    for b in pmap.borders:
        if not b.closed:
            for q in (b.points_mm[0], b.points_mm[-1]):
                cnt[(round(q[0], 3), round(q[1], 3))] += 1
    return [k for k, v in cnt.items() if v == 1]


def test_contornos_finos_e_fronteiras_continuas():
    """Linhas pretas finas (como contornos de mapa) não viram regiões nem pontos falsos e a rede
    de fronteiras não tem pontas soltas."""
    from PIL import Image, ImageDraw
    from img2stl.vision import ImageReader
    import make_demo_image
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "base.png")
        make_demo_image.make(base)
        ref = ImageReader(PipelineConfig().vision).read(base)
        im = Image.open(base).convert("RGB")
        dr = ImageDraw.Draw(im)
        w, h = im.size
        dr.line([(0, h // 2), (w, h // 2)], fill=(0, 0, 0), width=2)           # linha preta fina atravessando
        dr.line([(w // 5, h // 5), (w // 5, h // 3)], fill=(20, 20, 20), width=2)   # traço solto (beco sem saída)
        lined = os.path.join(d, "linhas.png")
        im.save(lined)
        pm = ImageReader(PipelineConfig().vision).read(lined)
        assert len(pm.regions) <= len(ref.regions) + 1
        assert _dangling_ends(pm) == []
        assert pm.points == []


def test_pontos_de_interesse_manuais():
    """Os pontos de interesse (lista em PlanarMap.points) viram relevo e aparecem nos negativos."""
    import cv2
    from img2stl.vision import ImageReader, InterestPoint
    from img2stl.negatives import NegativeRenderer
    import make_demo_image
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "x.png")
        make_demo_image.make(img)
        cfg = PipelineConfig()
        cfg.relief.resolution_mm = 0.1
        pm = ImageReader(cfg.vision).read(img)
        base = ImageToReliefPipeline(cfg, verbose=False).build_heightfield(pm).z.copy()
        pm.points = [InterestPoint(0, (30.0, 40.0), "triangle", "Capital A"), InterestPoint(1, (70.0, 20.0))]
        hf = ImageToReliefPipeline(cfg, verbose=False).build_heightfield(pm)
        assert hf.z.max() >= cfg.relief.base_thickness_mm + cfg.relief.point_height_mm - 1e-3
        assert not np.allclose(base, hf.z)
        NegativeRenderer(pm, cfg.relief, cfg.output).save(d)
        assert (cv2.imread(os.path.join(d, "pontos.png"), 0) > 0).sum() > 0
        assert pm.to_dict()["points"][0]["name"] == "Capital A"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok:", name)
