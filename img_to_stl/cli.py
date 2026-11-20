"""Linha de comando.

Interativo (padrão num terminal):
    python -m img_to_stl                 # menu: 1) importar nova imagem  2) operar em imagem existente
    python -m img_to_stl imagem.png      # importa a imagem e segue o fluxo interativo
Automático (sem perguntas):
    python -m img_to_stl imagem.png --auto
    python -m img_to_stl imagem.png --etapa 1                      # só o reconhecimento
    python -m img_to_stl --projeto imagem --etapa 2 --auto         # só a etapa 2 (depois de editar texturas.json)
Por objeto (escolhe o projeto e diz o que fazer; veja `python -m img_to_stl projeto -h`):
    python -m img_to_stl projetos
    python -m img_to_stl projeto demo fundir menores=50
    python -m img_to_stl projeto demo textura 3=ondas/3          (uma ação por comando; depois: projeto demo gerar)
Repositório: repositorio/<nome>/ (um projeto por imagem) · STL prontos: saidas/<nome>.stl
"""
from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):   # rodado como arquivo (python img_to_stl/cli.py): sem pacote pai
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "img_to_stl"

from .config import PipelineConfig  # noqa: E402
from .etapa1_reconhecimento.criterios import parse_fusion  # noqa: E402
from .etapa2_texturas.biblioteca import TextureLibrary  # noqa: E402
from .pipeline import ImageToStl  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="img_to_stl", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", nargs="?", help="imagem de entrada (png, jpg...)")
    p.add_argument("--projeto", metavar="NOME", help="projeto já existente no repositório (nome ou caminho da pasta)")
    p.add_argument("--etapa", choices=["1", "2", "tudo"], default="tudo", help="o que executar (padrão: tudo)")
    p.add_argument("--auto", action="store_true", help="sem perguntas (padrão quando não há terminal)")
    p.add_argument("-i", "--interativo", action="store_true", help="força o modo interativo")
    p.add_argument("-o", "--output", default=None, help="pasta do repositório (padrão: 'repositorio'); cria <pasta>/<nome_da_imagem>/")
    p.add_argument("--saidas", default=None, help="pasta dos STL prontos (padrão: 'saidas')")
    p.add_argument("--interface", choices=["principal", "auxiliar"], default="principal",
                   help="interface interativa: principal (parâmetros principais + lista completa) ou auxiliar (versão 2, parâmetros em abas)")
    p.add_argument("--no-negatives", action="store_true", help="não grava os negativos")
    p.add_argument("--config", help="JSON de configuração completo (etapa1 + etapa2)")
    p.add_argument("--save-config", help="salva a configuração final neste JSON")
    p.add_argument("--list-textures", action="store_true", help="lista as texturas disponíveis e sai")
    p.add_argument("--export-textures", metavar="PASTA",
                   help="grava um tile (STL+PNG+JSON) de cada textura interna para editar no CAD e sai")

    g = p.add_argument_group("etapa 1 — reconhecimento")
    g.add_argument("--width-mm", type=float, help="largura final da peça")
    g.add_argument("--max-regions", type=int, help="máximo de regiões")
    g.add_argument("--tolerance", type=float, help="ΔE (Lab) para fundir regiões parecidas")
    g.add_argument("--family-tolerance", type=float, help="ΔE (Lab) para agrupar regiões irmãs (famílias)")
    g.add_argument("--min-region-area", type=float, help="área mínima de região (mm²)")
    g.add_argument("--min-border", type=float, help="comprimento mínimo de fronteira (mm)")
    g.add_argument("--clusters", type=int, help="cores iniciais do k-means")
    g.add_argument("--ignore-color", metavar="R,G,B", help="cor de fundo (região lisa; fora da base 'silhueta')")
    g.add_argument("--fundir", action="append", metavar="ESPEC",
                   help="funde regiões (repetível, em ordem). ESPEC: números (3,7) ou critério: familia | menores=50 | cor=verde,lilas")
    g.add_argument("--marker", action="append", metavar="CLASSE=R,G,B[,TOL]",
                   help="marcador de pontos de interesse: bolinhas dessa cor viram pontos da classe (repetível)")
    g.add_argument("--points-file", help="arquivo .json/.csv de pontos de interesse (classe, nome, x_px, y_px)")

    g = p.add_argument_group("etapa 2 — texturas e STL")
    g.add_argument("--resolution", type=float, help="resolução da grade (mm); menor = mais detalhe")
    g.add_argument("--base", type=float, help="espessura da base (mm)")
    g.add_argument("--base-mode", choices=["retangular", "silhueta"], help="formato da base")
    g.add_argument("--base-regions", help="ids das regiões da base 'silhueta', ex.: 0,1,3")
    g.add_argument("--smooth-region", dest="smooth_region",
                   help="região lisa da sugestão: externa (padrão), maior, nenhuma, ou nome/número da região")
    g.add_argument("--amplitude", type=float, help="altura das texturas (mm)")
    g.add_argument("--textura", action="append", metavar="REGIAO=ESPEC",
                   help=f"textura de uma região (número ou nome), ex.: 3=ondas/3(1.5,2,30) (repetível). "
                        f"Texturas: {TextureLibrary.describe()}")
    g.add_argument("--textures-file", help="arquivo texturas.json a usar (padrão: o da pasta etapa2_texturas)")
    g.add_argument("--texture-dir", help="pasta com texturas de CAD/PNG: arquivos <id>_<nome>.stl|png")
    g.add_argument("--model-triple-points", action="store_true", help="pontos tríplices viram relevo")
    return p


def apply_overrides(cfg: PipelineConfig, a: argparse.Namespace) -> None:
    e1, e2 = cfg.etapa1, cfg.etapa2
    for attr, val in (("width_mm", a.width_mm), ("max_regions", a.max_regions), ("color_tolerance", a.tolerance),
                      ("family_tolerance", a.family_tolerance), ("min_region_area_mm2", a.min_region_area),
                      ("min_border_length_mm", a.min_border), ("n_color_clusters", a.clusters),
                      ("points_file", a.points_file)):
        if val is not None:
            setattr(e1, attr, val)
    if a.ignore_color:
        e1.ignore_color = tuple(int(c) for c in a.ignore_color.split(","))
    for grp in a.fundir or []:
        entry = parse_fusion(grp)
        if entry not in e1.merge_regions:                  # apply_overrides pode rodar duas vezes
            e1.merge_regions.append(entry)
    for m in a.marker or []:
        classe, _, rest = m.partition("=")
        nums = [float(v) for v in rest.split(",")]
        item = {"classe": classe, "cor": [int(v) for v in nums[:3]]}
        if len(nums) > 3:
            item["tolerancia"] = nums[3]
        e1.point_markers.append(item)
    for attr, val in (("resolution_mm", a.resolution), ("base_thickness_mm", a.base),
                      ("base_mode", a.base_mode), ("texture_amplitude_mm", a.amplitude),
                      ("texture_dir", a.texture_dir), ("smooth_region", a.smooth_region)):
        if val is not None:
            setattr(e2, attr, val)
    if a.base_regions:
        e2.base_regions = [int(v) for v in a.base_regions.split(",")]
    if a.model_triple_points:
        e2.model_triple_points = True
    if a.no_negatives:
        cfg.negatives = False
    if a.output:
        cfg.base_dir = a.output
    if a.saidas:
        cfg.stl_dir = a.saidas


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("projeto", "projetos"):
        from .cli_projeto import main as projeto_main
        return projeto_main(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_textures:
        if args.texture_dir:
            TextureLibrary.load_directory(args.texture_dir)
        for tid, name, desc in TextureLibrary.catalog():
            print(f"{tid:>3}  {name:<18}{desc}")
        return 0
    if args.export_textures:
        from .etapa2_texturas.biblioteca import export_texture_templates
        files = export_texture_templates(args.export_textures)
        print(f"{len(files)} modelos gravados em {args.export_textures}/ (STL + PNG + JSON por textura)")
        return 0
    cfg = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    apply_overrides(cfg, args)
    if args.save_config:
        cfg.to_json(args.save_config)
    app = ImageToStl(cfg, log=print)
    interactive = args.interativo or (not args.auto and sys.stdin.isatty())
    from . import cli_auxiliar
    from .interativo import main_menu, params_principal
    step = cli_auxiliar.params_abas if args.interface == "auxiliar" else params_principal

    if not args.image and not args.projeto:
        if not interactive:
            parser.error("informe a imagem (ou --projeto NOME, ou --export-textures PASTA)")
        main_menu(app, params_step=step)
        return 0

    stage = args.etapa
    if args.projeto:
        try:
            proj = app.resolve_project(args.projeto)
        except FileNotFoundError as e:
            parser.error(str(e))
        if not args.config:
            app.load_params(proj)
        apply_overrides(cfg, args)                         # flags da linha de comando vencem o que foi gravado
        image = app.original_image(proj) if stage in ("1", "tudo") else None
    else:
        image = args.image
        if interactive:
            from .interativo import choose_project_name
            name = choose_project_name(app, image, input, print)
            if name is None:
                return 0
            proj = app.project_dir(name)
        else:
            proj = app.project_dir(image)

    if interactive:
        from .interativo import interactive_session
        interactive_session(image, app, proj=proj, start_stage=2 if stage == "2" else 1, params_step=step)
        return 0

    pmap = None
    if stage in ("1", "tudo"):
        pmap = app.run_etapa1(image, proj)
    if stage in ("2", "tudo"):
        app.run_etapa2(proj, pmap, args.textures_file, args.textura)
    print(f"[saída] projeto: {os.path.abspath(proj)}  ·  STL: {os.path.abspath(app.stl_path(proj))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
