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
        assert len(pmap.points) == 4
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok:", name)
