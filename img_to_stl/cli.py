"""Linha de comando.

Fluxo recomendado (2 passos):
  1) python -m img_to_stl imagem.png --read-only          # saida/imagem/regioes_preview.png com os ids
  2) python -m img_to_stl imagem.png --textures 0=1,1=2,2=3,3=4   # saida/imagem/imagem.stl + negativos/
"""
from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):   # rodado como arquivo (python img_to_stl/cli.py): sem pacote pai
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "img_to_stl"

from .config import PipelineConfig  # noqa: E402
from .pipeline import ImageToReliefPipeline, resolve_outputs  # noqa: E402
from .textures import TextureLibrary  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="img_to_stl", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", nargs="?", help="imagem de entrada (png, jpg...)")
    p.add_argument("--export-textures", metavar="PASTA",
                   help="grava um tile (STL+PNG+JSON) de cada textura interna para editar no CAD e sai")
    p.add_argument("-o", "--output", default=None,
                   help="pasta-base (padrão: 'saida'); cada imagem ganha a subpasta <pasta>/<nome_da_imagem>/. "
                        "Se terminar em .stl, usa esse caminho exato para o STL")
    p.add_argument("--no-negatives", action="store_true", help="não grava a pasta negativos/")
    p.add_argument("--config", help="JSON de configuração (valores do arquivo são a base)")
    p.add_argument("--save-config", help="salva a configuração final neste JSON")
    p.add_argument("--read-only", action="store_true", help="só a parte 1: gera previews e mapa.json")

    g = p.add_argument_group("parte 1 — imagem")
    g.add_argument("--width-mm", type=float, help="largura final da peça")
    g.add_argument("--max-regions", type=int, help="máximo de regiões")
    g.add_argument("--tolerance", type=float, help="ΔE (Lab) para fundir regiões parecidas")
    g.add_argument("--min-region-area", type=float, help="área mínima de região (mm²)")
    g.add_argument("--min-border", type=float, help="comprimento mínimo de fronteira (mm)")
    g.add_argument("--clusters", type=int, help="cores iniciais do k-means")
    g.add_argument("--junction-points", action="store_true",
                   help="liga os pontos de intersecção (encontros de 3+ regiões); desligado por padrão")

    g = p.add_argument_group("parte 2 — relevo")
    g.add_argument("--resolution", type=float, help="resolução da grade (mm); menor = mais detalhe")
    g.add_argument("--base", type=float, help="espessura da base (mm)")
    g.add_argument("--amplitude", type=float, help="altura das texturas (mm)")
    g.add_argument("--textures", help="região=textura[:escala[:esticar[:ângulo]]] separados por vírgula, "
                                      "ex.: 0=1,1=2:1.5,2=3:1:2:30 "
                                      f"(texturas: {TextureLibrary.describe()})")
    g.add_argument("--texture-dir", help="pasta com texturas de CAD/PNG: arquivos <id>_<nome>.stl|png")
    return p


def apply_overrides(cfg: PipelineConfig, a: argparse.Namespace) -> None:
    v, r = cfg.vision, cfg.relief
    for attr, val in (("width_mm", a.width_mm), ("max_regions", a.max_regions),
                      ("color_tolerance", a.tolerance), ("min_region_area_mm2", a.min_region_area),
                      ("min_border_length_mm", a.min_border), ("n_color_clusters", a.clusters)):
        if val is not None:
            setattr(v, attr, val)
    for attr, val in (("resolution_mm", a.resolution), ("base_thickness_mm", a.base),
                      ("texture_amplitude_mm", a.amplitude)):
        if val is not None:
            setattr(r, attr, val)
    if a.texture_dir:
        r.texture_dir = a.texture_dir
    if a.textures:
        for item in a.textures.split(","):
            rid, spec = item.split("=")
            tid, *extra = spec.split(":")
            if extra:
                keys = ("scale", "stretch", "stretch_angle_deg")
                r.region_textures[int(rid)] = {"texture": int(tid), **{k: float(v) for k, v in zip(keys, extra)}}
            else:
                r.region_textures[int(rid)] = int(tid)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.export_textures:
        from .tiles import export_texture_templates
        files = export_texture_templates(args.export_textures)
        print(f"{len(files)} modelos gravados em {args.export_textures}/ (STL + PNG + JSON por textura)")
        return 0
    if not args.image:
        build_parser().error("informe a imagem (ou use --export-textures PASTA)")
    cfg = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    apply_overrides(cfg, args)
    if args.junction_points:
        cfg.vision.junction_points = True
    if args.no_negatives:
        cfg.output.negatives = False
    if args.save_config:
        cfg.to_json(args.save_config)

    pipe = ImageToReliefPipeline(cfg)
    out_dir, stl_path = resolve_outputs(args.image, args.output, cfg.output.base_dir)
    if args.read_only:
        pipe.read(args.image, out_dir=out_dir)
        print(f"Previews em {out_dir}/ — veja regioes_preview.png e escolha as texturas com --textures")
        return 0
    pipe.run(args.image, stl_path, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
