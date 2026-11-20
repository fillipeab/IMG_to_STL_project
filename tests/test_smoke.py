"""Testes de fumaça. Rode:  python tests/test_smoke.py   (ou pytest)"""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from img_to_stl import (Etapa1Config, Etapa2Config, ImageReader, ImageToStl, PipelineConfig,  # noqa: E402
                        PlanarMap, TextureLibrary, TextureTransform, TransformedTexture)
from img_to_stl.etapa2_texturas.relevo import HeightField  # noqa: E402
from img_to_stl.etapa2_texturas.stl import HeightfieldMesher  # noqa: E402
import make_demo_image  # noqa: E402


def _demo(d, name="demo.png"):
    img = os.path.join(d, name)
    make_demo_image.make(img)
    return img


def _fast_cfg(res=0.3, d=None):
    cfg = PipelineConfig()
    cfg.etapa2.resolution_mm = res
    if d:
        cfg.base_dir = os.path.join(d, "repositorio")
        cfg.stl_dir = os.path.join(d, "saidas")
    return cfg


# ----------------------------- biblioteca de texturas ----------------------------- #
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


def test_transform_scale_stretch_rotation():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 30, 5000), rng.uniform(0, 30, 5000)
    base = TextureLibrary.create(3)
    assert np.allclose(TransformedTexture(base, TextureTransform()).height(x, y), base.height(x, y))
    big = TransformedTexture(base, TextureTransform(scale=2.0))
    assert np.allclose(big.height(x, y), base.height(x / 2.0, y / 2.0))
    rot = TransformedTexture(base, TextureTransform(rotation_deg=90))
    assert np.allclose(rot.height(x, y), base.height(y, -x))
    st = TextureTransform(stretch=2.0, stretch_angle_deg=0.0)
    assert np.allclose(st.apply(x, y)[0], x / 2.0) and np.allclose(st.apply(x, y)[1], y)
    assert TransformedTexture(TextureLibrary.create(1), TextureTransform(scale=0.4)).min_feature_mm < 0.4


def test_cad_roundtrip_stl_and_png():
    from img_to_stl.etapa2_texturas.biblioteca import TileTexture, export_texture_templates
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


def test_catalogo_e_texturas_novas():
    cat = TextureLibrary.catalog()
    assert [c[0] for c in cat][:13] == list(range(13)) and all(desc for _, _, desc in cat)
    assert cat[0][1] == "lisa"                                    # a textura lisa existe (id 0)
    assert TextureLibrary.resolve("zigue-zague") == 9 and TextureLibrary.resolve("aneis") == 10
    assert not np.any(TextureLibrary.create(0).height(np.zeros(5), np.zeros(5)))
    for tid in range(6, 13):                                      # cada nova tem relevo de verdade
        h = TextureLibrary.create(tid).tile(10.0, 0.1)
        assert h.max() - h.min() > 0.5, tid


# ----------------------------- especificação "nome/numero(distorções)" ----------------------------- #
def test_especificacao_de_textura():
    from img_to_stl.etapa2_texturas.especificacao import format_spec, parse_spec
    a = parse_spec("ondas/3(1.5, 2, 30)", 0.6)
    assert a.texture_id == 3 and a.transform.scale == 1.5 and a.transform.stretch == 2 \
        and a.transform.stretch_angle_deg == 30 and a.amplitude_mm == 0.6
    b = parse_spec("escamas(escala=0.8, amp=0.9, desloc_x=2)", 0.6)
    assert b.texture_id == 4 and b.amplitude_mm == 0.9 and b.transform.offset_mm == (2.0, 0.0)
    assert parse_spec("lisa/0", 0.6).texture_id == 0 and parse_spec("5", 0.6).texture_id == 5
    assert parse_spec("Xs/2", 0.6).texture_id == 2 and parse_spec("X's", 0.6).texture_id == 2
    for bad in ("ondas/3(foo=1)", "inexistente", "ondas/3(a)", "3(1,2,3,4,5,6,7,8,9,10)"):
        try:
            parse_spec(bad, 0.6)
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError(f"deveria rejeitar: {bad}")
    for spec in ("ondas/3", "escamas/4(escala=1.5, alongar=2, angulo=30, amp=0.8)"):
        assert parse_spec(format_spec(parse_spec(spec, 0.6), 0.6), 0.6) == parse_spec(spec, 0.6)


# ----------------------------- malha ----------------------------- #
def test_mesh_is_watertight_and_volume_matches():
    z = np.random.default_rng(0).uniform(1, 2, (30, 40)).astype(np.float32)
    info = HeightfieldMesher().build(HeightField(z=z, dx=0.5, dy=0.5)).validate()
    assert info["estanque"]
    cell = (z[:-1, :-1] + z[:-1, 1:] + z[1:, :-1] + z[1:, 1:]) / 4.0 * 0.25
    assert abs(info["volume_mm3"] - cell.sum()) / cell.sum() < 0.02


def test_mesh_silhueta_estanque():
    z = np.random.default_rng(0).uniform(1, 2, (30, 40)).astype(np.float32)
    cells = np.zeros((29, 39), bool)
    cells[3:20, 5:30] = True
    cells[8:12, 10:15] = False                       # buraco no meio
    cells[22:27, 32:37] = True                       # ilha separada
    mesh = HeightfieldMesher().build(HeightField(z=z, dx=0.5, dy=0.5, cells=cells))
    info = mesh.validate()
    assert info["estanque"] and info["volume_mm3"] > 0


# ----------------------------- etapa 1 ----------------------------- #
def test_etapa1_regioes_nomes_familias_e_pontos_triplices():
    with tempfile.TemporaryDirectory() as d:
        pm = ImageReader(Etapa1Config()).read(_demo(d))
        assert len(pm.regions) == 7, "esperado: 6 células + 1 ilha (o ponto minúsculo deve sumir)"
        assert any(b.outer for b in pm.borders)
        assert len({r.name for r in pm.regions}) == 7 and all(r.name[:2].isdigit() for r in pm.regions)
        assert sorted(i for f in pm.families for i in f.region_ids) == list(range(7))
        assert pm.classes() == {"triplice": 4}              # sempre calculados e reportados
        assert all(len(p.regions) >= 3 for p in pm.points)


def test_familias_agrupam_cores_parecidas():
    cfg = Etapa1Config()
    cfg.family_tolerance = 0
    with tempfile.TemporaryDirectory() as d:
        img = _demo(d)
        assert len(ImageReader(cfg).read(img).families) == 7
        cfg.family_tolerance = 200                          # tudo parecido
        assert len(ImageReader(cfg).read(img).families) == 1


def _dangling_ends(pmap):
    import collections
    cnt = collections.Counter()
    for b in pmap.borders:
        if not b.closed:
            for q in (b.points_mm[0], b.points_mm[-1]):
                cnt[(round(q[0], 3), round(q[1], 3))] += 1
    return [k for k, v in cnt.items() if v == 1]


def test_contornos_finos_e_fronteiras_continuas():
    from PIL import Image, ImageDraw
    with tempfile.TemporaryDirectory() as d:
        base = _demo(d, "base.png")
        ref = ImageReader(Etapa1Config()).read(base)
        im = Image.open(base).convert("RGB")
        dr = ImageDraw.Draw(im)
        w, h = im.size
        dr.line([(0, h // 2), (w, h // 2)], fill=(0, 0, 0), width=2)
        dr.line([(w // 5, h // 5), (w // 5, h // 3)], fill=(20, 20, 20), width=2)
        lined = os.path.join(d, "linhas.png")
        im.save(lined)
        pm = ImageReader(Etapa1Config()).read(lined)
        assert len(pm.regions) <= len(ref.regions) + 1
        assert _dangling_ends(pm) == []
        assert pm.classes().get("triplice", 0) <= 8          # nenhum ponto falso em massa


def test_pontos_de_interesse_marcadores_e_arquivo():
    from PIL import Image, ImageDraw
    with tempfile.TemporaryDirectory() as d:
        base = _demo(d, "base.png")
        im = Image.open(base).convert("RGB")
        w, h = im.size
        dr = ImageDraw.Draw(im)
        for cx, cy in ((w * 0.25, h * 0.3), (w * 0.7, h * 0.6)):
            dr.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(1, 255, 2))      # marcadores verde-limão
        marked = os.path.join(d, "marcada.png")
        im.save(marked)
        ref = ImageReader(Etapa1Config()).read(base)
        cfg = Etapa1Config(point_markers=[{"classe": "capital", "cor": [1, 255, 2], "tolerancia": 25}])
        pm = ImageReader(cfg).read(marked)
        caps = pm.points_of("capital")
        assert len(caps) == 2 and len(pm.regions) == len(ref.regions)         # marcador não vira região
        W, H = pm.size_mm
        assert abs(caps[0].xy_mm[0] - W * 0.25) < 1.5 and abs(caps[0].xy_mm[1] - H * 0.7) < 1.5
        # arquivo de pontos (px da imagem original e mm)
        pts = os.path.join(d, "pontos.json")
        json.dump([{"classe": "cidade", "nome": "A", "x_px": w * 0.5, "y_px": h * 0.5},
                   {"classe": "cidade", "nome": "B", "x_mm": 10, "y_mm": 10}], open(pts, "w"))
        pm = ImageReader(Etapa1Config(points_file=pts)).read(base)
        a, b = pm.points_of("cidade")
        assert abs(a.xy_mm[0] - W / 2) < 0.1 and abs(a.xy_mm[1] - H / 2) < 0.1 and b.xy_mm == (10.0, 10.0)
        csv_path = os.path.join(d, "pontos.csv")
        open(csv_path, "w").write("classe,nome,x_px,y_px\ncapital,X,10,20\n")
        assert len(ImageReader(Etapa1Config(points_file=csv_path)).read(base).points_of("capital")) == 1


def test_pasta_de_saida_completa_e_recarga_da_etapa1():
    import cv2
    with tempfile.TemporaryDirectory() as d:
        img = _demo(d, "minha_imagem.png")
        cfg = _fast_cfg(0.4, d)
        app = ImageToStl(cfg)
        pm = app.run_etapa1(img)
        proj = os.path.join(d, "repositorio", "minha_imagem")
        e1 = os.path.join(proj, "etapa1_reconhecimento")
        for f in ("identificacao.txt", "imagem_original.png"):
            assert os.path.isfile(os.path.join(proj, f)), f
        for f in ("parametros.json", "resultado.json", "rotulos.png", "parametros_e_resultados.txt", "previa.png"):
            assert os.path.isfile(os.path.join(e1, f)), f
        txt = open(os.path.join(e1, "parametros_e_resultados.txt"), encoding="utf-8").read()
        assert "número de regiões: 7" in txt and "pontos tríplices: 4" in txt
        neg = os.path.join(e1, "negativos")
        for r in pm.regions:                                           # negativos nomeados/numerados
            assert cv2.imread(os.path.join(neg, "regioes", f"regiao_{r.name}.png"), 0) is not None
        for f in ("fronteiras/fronteiras.png", "fronteiras/fronteiras_numeradas.png",
                  "pontos/pontos_triplice.png", "pontos/pontos_marcados.png"):
            assert os.path.isfile(os.path.join(neg, f)), f
        # recarrega e confere
        pm2 = PlanarMap.load(e1)
        assert np.array_equal(pm.labels, pm2.labels) and [r.name for r in pm2.regions] == [r.name for r in pm.regions]
        assert len(pm2.borders) == len(pm.borders) and pm2.classes() == pm.classes()
        assert np.allclose(pm2.borders[0].points_mm, pm.borders[0].points_mm, atol=1e-3)


# ----------------------------- etapa 2 ----------------------------- #
def test_pipeline_completo_e_texturas_json():
    with tempfile.TemporaryDirectory() as d:
        img = _demo(d, "peca.png")
        cfg = _fast_cfg(0.3, d)
        app = ImageToStl(cfg)
        mesh = app.run(img)
        e2 = os.path.join(d, "repositorio", "peca", "etapa2_texturas")
        stl = os.path.join(d, "saidas", "peca.stl")
        for f in ("parametros.json", "texturas.json", "previa_relevo.png", "relatorio.txt"):
            assert os.path.isfile(os.path.join(e2, f)), f
        assert os.listdir(os.path.join(d, "saidas")) == ["peca.stl"]          # a pasta de saídas só tem STL
        assert not any(f.endswith(".stl") for f in os.listdir(e2))            # sem cópia dentro do projeto
        assert os.path.getsize(stl) == 84 + 50 * len(mesh.faces)
        # editar texturas.json muda o resultado (refazendo só a etapa 2)
        path = os.path.join(e2, "texturas.json")
        data = json.load(open(path, encoding="utf-8"))
        first = next(iter(data["regioes"]))
        data["regioes"][first] = "ondas/3(escala=2, amp=0.9)"
        json.dump(data, open(path, "w", encoding="utf-8"))
        before = os.path.getsize(stl)
        app2 = ImageToStl(cfg)
        proj = os.path.join(d, "repositorio", "peca")
        app2.run_etapa2(proj)
        rel = open(os.path.join(e2, "relatorio.txt"), encoding="utf-8").read()
        assert f"{first}: ondas/3(escala=2, amp=0.9)" in rel
        assert os.path.getsize(stl) > 0 and before > 0
        # entrada inválida dá mensagem clara
        data["regioes"][first] = "ondas/3(foo=1)"
        json.dump(data, open(path, "w", encoding="utf-8"))
        try:
            app2.run_etapa2(proj)
        except ValueError as e:
            assert first in str(e)
        else:
            raise AssertionError("deveria rejeitar distorção desconhecida")


def test_texturas_sugeridas_vizinhas_distintas():
    from img_to_stl.etapa2_texturas.atribuicao import TextureAssigner
    with tempfile.TemporaryDirectory() as d:
        pm = ImageReader(Etapa1Config()).read(_demo(d))
        cfg = Etapa2Config()
        adj = TextureAssigner.adjacency(pm)
        asg = TextureAssigner(cfg).assign(pm)
        for a, vizinhas in adj.items():
            for b in vizinhas:
                assert asg[a].texture_id != asg[b].texture_id
        ids = [a.texture_id for a in asg.values()]
        assert len(set(ids)) == min(len(ids), len(cfg.default_textures))
        # escolha manual pode repetir entre vizinhas, sem alteração
        from img_to_stl.etapa2_texturas.atribuicao import TextureAssignment
        a, b = next((a, b) for a, v in adj.items() for b in v)
        asg = TextureAssigner(cfg).assign(pm, {a: TextureAssignment(3), b: TextureAssignment(3)})
        assert asg[a].texture_id == asg[b].texture_id == 3


def test_regiao_lisa_automatica():
    from img_to_stl.etapa2_texturas.atribuicao import TextureAssigner, TextureAssignment
    with tempfile.TemporaryDirectory() as d:
        pm = ImageReader(Etapa1Config()).read(_demo(d))
        cfg = Etapa2Config()
        asg = TextureAssigner(cfg).assign(pm)
        lisas = [i for i, a in asg.items() if a.texture_id == 0]
        outer = max((r for r in pm.regions if r.touches_frame), key=lambda r: r.area_mm2)
        assert lisas == [outer.id]                                   # uma só: a maior que toca a borda
        cfg.smooth_region = "nenhuma"
        assert all(a.texture_id != 0 for a in TextureAssigner(cfg).assign(pm).values())
        cfg.smooth_region = pm.regions[3].name                       # por nome
        assert [i for i, a in TextureAssigner(cfg).assign(pm).items() if a.texture_id == 0] == [3]
        cfg.smooth_region = "externa"
        manual = {2: TextureAssignment(0)}                           # lisa à mão: não cria outra
        assert [i for i, a in TextureAssigner(cfg).assign(pm, manual).items() if a.texture_id == 0] == [2]
        pm.regions[0].ignored = True                                 # fundo já é lisa: não cria outra
        assert [i for i, a in TextureAssigner(cfg).assign(pm).items() if a.texture_id == 0] == [0]


def test_fundir_regioes():
    with tempfile.TemporaryDirectory() as d:
        cfg = _fast_cfg(d=d)
        app = ImageToStl(cfg)
        proj = app.project_dir("demo")
        pm = app.run_etapa1(_demo(d), proj)
        n, area = len(pm.regions), pm.regions[1].area_mm2 + pm.regions[2].area_mm2
        new = app.fundir_regioes(proj, pm, [1, 2])
        assert len(new.regions) == n - 1 and abs(max(r.area_mm2 for r in new.regions) - max(area, pm.regions[0].area_mm2)) < 1e-6
        assert new.labels.max() == n - 2 and cfg.etapa1.merge_regions == [[1, 2]]
        assert app.load_etapa1(proj).summary() == new.summary()       # regravado em disco
        assert app.run_etapa1(_demo(d), proj).summary() == new.summary()   # refazer repete a fusão
        for bad in ([1], [1, 1], [1, 99]):
            try:
                app.fundir_regioes(proj, new, bad)
            except ValueError:
                continue
            raise AssertionError(bad)
        from img_to_stl.etapa1_reconhecimento.criterios import parse_fusion
        assert parse_fusion("1, 2 " + new.regions[3].name, new) == [1, 2, 3]


def test_fusao_por_criterio():
    from img_to_stl.etapa1_reconhecimento.criterios import parse_fusion, resolve_fusion
    with tempfile.TemporaryDirectory() as d:
        pm = ImageReader(Etapa1Config()).read(_demo(d))
        assert parse_fusion("menores 100") == "menores=100" and parse_fusion("cor verde lilas") == "cor=verde,lilas"
        assert parse_fusion("familia") == "familia" and parse_fusion("3,7") == [3, 7]
        small = [r.id for r in pm.regions if r.area_mm2 < 100]
        groups = resolve_fusion(pm, "menores=100")
        assert small and all(set(small) <= set(g) or not set(small) & set(g) for g in groups)
        assert sum(len(g) - 1 for g in groups) == len(small)        # cada pequena some numa vizinha
        assert len(ImageReader(Etapa1Config()).apply_fusion(pm, "menores=100").regions) == len(pm.regions) - len(small)
        # cor: usa o nome da cor das regiões
        a, b = pm.regions[0], pm.regions[1]
        assert resolve_fusion(pm, f"cor={a.color_name.split()[0]}+{b.color_name.split()[0]}")[0][:2] == [0, 1]
        for bad in ("familia=zzz", "cor=azulbebe", "menores=0.001", "xyz"):
            try:
                resolve_fusion(pm, bad)
            except ValueError:
                continue
            raise AssertionError(bad)
        # repetição fiel pela configuração: criterio guardado em merge_regions
        cfg = Etapa1Config(merge_regions=["menores=100", [0, 1]])
        n = len(ImageReader(cfg).read(_demo(d)).regions)
        assert n == len(pm.regions) - len(small) - 1


def test_cli_por_objeto_e_interface_auxiliar():
    from img_to_stl.cli import main as cli_main
    from img_to_stl.cli_projeto import main as projeto_main
    from img_to_stl.cli_auxiliar import main_menu as menu_aux
    with tempfile.TemporaryDirectory() as d:
        repo, saidas = os.path.join(d, "repositorio"), os.path.join(d, "saidas")
        img = _demo(d, "obj.png")
        assert cli_main([img, "--etapa", "1", "--auto", "-o", repo, "--saidas", saidas, "--no-negatives"]) == 0
        log = []
        run = lambda *a: projeto_main(["projeto", "obj", *a, "-o", repo, "--saidas", saidas, "--resolution", "0.5"], out=log.append)
        assert projeto_main(["projetos", "-o", repo], out=log.append) == 0 and "obj" in log[-1]
        assert run("regioes") == 0 and "00_" in log[-1] or "06_" in "\n".join(log)
        assert run("fundir", "menores=100", "cor=laranja+rosa") == 0 and any("✓" in m for m in log)
        assert run("fundir", "9,10") == 2 and "inexistente" in log[-1]       # erro claro, sem quebrar
        assert run("textura", "1=ondas/3(1.5)") == 0
        assert run("gerar") == 0 and os.path.isfile(os.path.join(saidas, "obj.stl"))
        assert projeto_main(["projeto", "nada", "ver", "-o", repo], out=log.append) == 2
        # interface auxiliar: parâmetros em abas
        cfg = _fast_cfg(0.5, d)
        cfg.base_dir, cfg.stl_dir = repo, saidas
        app = ImageToStl(cfg)
        respostas = iter(["2", "1", "2",                  # operar em existente > #1 > etapa 2
                          "a", "1", "2", "1.5", "", "",   # ajustar > grupo 1 > base_thickness_mm = 1.5 > voltar > pronto
                          "", "", "0"])                   # texturas, gerar, sair
        log = []
        menu_aux(app, ask=lambda m: next(respostas), out=log.append)
        assert cfg.etapa2.base_thickness_mm == 1.5 and "Grupos de parâmetros" in "\n".join(log)


def test_pontos_triplices_so_viram_relevo_se_ligados():
    from img_to_stl.etapa2_texturas.relevo import ReliefBuilder
    with tempfile.TemporaryDirectory() as d:
        pm = ImageReader(Etapa1Config()).read(_demo(d))
        cfg = Etapa2Config(resolution_mm=0.2)
        base = ReliefBuilder(pm, cfg).build().z
        assert ReliefBuilder(pm, cfg).points == []
        cfg.model_triple_points = True
        on = ReliefBuilder(pm, cfg)
        assert len(on.points) == 4 and not np.allclose(base, on.build().z)
        # ponto de interesse sempre vira relevo, com a forma da classe
        from img_to_stl.etapa1_reconhecimento.modelos import InterestPoint
        cfg2 = Etapa2Config(resolution_mm=0.1, point_shape_by_class={"capital": "square"})
        pm.points = [InterestPoint(0, (30.0, 40.0), "capital", "Capital A")]
        hf = ReliefBuilder(pm, cfg2).build()
        assert hf.z.max() >= cfg2.base_thickness_mm + cfg2.point_height_mm - 1e-3


def test_base_silhueta_exclui_fundo():
    from PIL import Image, ImageDraw
    with tempfile.TemporaryDirectory() as d:
        im = Image.new("RGB", (200, 150), (255, 255, 255))          # fundo branco
        dr = ImageDraw.Draw(im)
        dr.ellipse([40, 30, 160, 120], fill=(200, 40, 40))           # ilha vermelha
        path = os.path.join(d, "ilha.png")
        im.save(path)
        cfg = _fast_cfg(0.3, d)
        cfg.etapa1.ignore_color = (255, 255, 255)
        cfg.etapa2.base_mode = "silhueta"
        app = ImageToStl(cfg)
        pm = app.run_etapa1(path)
        assert any(r.ignored for r in pm.regions)
        cfg.etapa2.base_mode = "retangular"
        rect = app.run_etapa2(os.path.join(d, "repositorio", "ilha")).validate()
        cfg.etapa2.base_mode = "silhueta"
        sil = ImageToStl(cfg).run_etapa2(os.path.join(d, "repositorio", "ilha")).validate()
        assert sil["estanque"] and rect["estanque"]
        assert sil["volume_mm3"] < 0.75 * rect["volume_mm3"]         # o fundo saiu da base


# ----------------------------- CLI ----------------------------- #
def test_cli_automatico_menu_e_repositorio():
    from img_to_stl.cli import main
    from img_to_stl.interativo import edit_params, main_menu
    with tempfile.TemporaryDirectory() as d:
        repo, saidas = os.path.join(d, "repositorio"), os.path.join(d, "saidas")
        flags = ["-o", repo, "--saidas", saidas, "--resolution", "0.4"]
        img = _demo(d, "cli.png")
        assert main([img, "--auto", "--textura", "0=ondas/3(1.5)"] + flags) == 0
        tj = os.path.join(repo, "cli", "etapa2_texturas", "texturas.json")
        assert next(iter(json.load(open(tj, encoding="utf-8"))["regioes"].values())) == "ondas/3(1.5)"
        assert os.listdir(saidas) == ["cli.stl"]
        # só a etapa 2 em projeto existente (por nome), parâmetros recarregados do projeto
        os.remove(os.path.join(saidas, "cli.stl"))
        assert main(["--projeto", "cli", "--etapa", "2", "--auto", "-o", repo, "--saidas", saidas]) == 0
        assert os.path.isfile(os.path.join(saidas, "cli.stl"))

        # explicação ?<número> e comandos inválidos
        saida = []
        cfg = _fast_cfg(0.5, d)
        respostas = iter(["?3", "abc", "99", ""])
        edit_params(cfg.etapa1, ["width_mm", "max_regions", "color_tolerance"], {"color_tolerance": "Grau de semelhança"},
                    lambda m: next(respostas), saida.append)
        txt = "\n".join(saida)
        assert "Grau de semelhança" in txt and "padrão: 10" in txt and "não reconhecido" in txt

        # menu: 1) importar (com conflito de nome) e 2) operar em existente
        app = ImageToStl(cfg)
        cfg.base_dir, cfg.stl_dir = repo, saidas
        novo = _demo(d, "outra.png")
        respostas = iter([
            "1", novo,                              # importar nova imagem
            "2", "8", "",                           # etapa 1: parâmetro 2 (max_regions) = 8 > continuar
            "",                                     # seguir para a etapa 2
            "",                                     # parâmetros da etapa 2: continuar
            "1", "escamas/4", "",                   # região 1 > textura > aceitar
            "",                                     # gerar agora
            "1", novo, "n", "outra_v2",             # importa de novo: conflito -> novo nome
            "", "", "", "", "",                     # tudo com padrões
            "2", "2", "2",                          # operar em existente: lista, escolhe #2 (outra) -> etapa 2
            "", "", "",                             # parâmetros, texturas, gerar
            "3", "0",                               # troca de interface e sai
        ])
        log = []
        main_menu(app, ask=lambda m: next(respostas), out=log.append)
        txt = "\n".join(log)
        assert "Importar nova imagem" in txt and "Operar em uma imagem já existente" in txt
        assert "Texturas disponíveis" in txt and "zigue-zague" in txt and "  0  lisa" in txt   # lista ao escolher a textura
        assert {"cli", "outra", "outra_v2"} <= set(app.list_projects())
        assert os.path.isfile(os.path.join(saidas, "outra.stl"))
        assert cfg.etapa1.max_regions == 8
        assert "Parâmetros principais" in txt
        assert "Interface: auxiliar (versão 2)" in txt


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception:
                failed += 1
                print("FALHOU", name)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
