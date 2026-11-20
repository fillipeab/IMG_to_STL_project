"""Linha de comando por objeto: escolha o projeto e diga o que fazer nele.

    python -m img_to_stl projetos                              lista os projetos do repositório
    python -m img_to_stl projeto NOME ver                      estado, resumo e texturas
    python -m img_to_stl projeto NOME regioes                  regiões numeradas (nome, família, área)
    python -m img_to_stl projeto NOME fundir ESPEC [ESPEC...]  funde regiões: 3,7 | familia | parecidas=8 | menores=50 | cor=verde,lilas
    python -m img_to_stl projeto NOME fundo REGIAO...           região(ões) de fundo (lisas): números/nomes | nenhuma | auto
    python -m img_to_stl projeto NOME textura REGIAO=ESPEC...  muda texturas (ex.: 3=ondas/3(1.5) 0=lisa)
    python -m img_to_stl projeto NOME reconhecer               refaz a etapa 1
    python -m img_to_stl projeto NOME gerar                    etapa 2: gera o STL
    python -m img_to_stl projeto NOME abrir [--interface auxiliar]   abre no modo interativo
Opções (depois da ação): -o PASTA_DO_REPOSITORIO · --saidas PASTA · --resolution MM · --amplitude MM · --smooth-region X
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from .config import PipelineConfig
from .etapa1_reconhecimento.criterios import parse_fusion, resolve_fusion
from .etapa2_texturas.pipeline import apply_background
from .etapa2_texturas.texturas_arquivo import set_entry
from .pipeline import PASTA_ETAPA1, PASTA_ETAPA2, ImageToStl

ACOES = ("ver", "regioes", "fundir", "fundo", "textura", "reconhecer", "gerar", "abrir")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="img_to_stl projeto", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nome", help="nome do projeto no repositório (ou caminho da pasta)")
    p.add_argument("acao", choices=ACOES, help="o que fazer")
    p.add_argument("args", nargs="*", help="argumentos da ação (ex.: as regiões a fundir)")
    p.add_argument("-o", "--output", help="pasta do repositório (padrão: repositorio)")
    p.add_argument("--saidas", help="pasta dos STL (padrão: saidas)")
    p.add_argument("--resolution", type=float, help="resolução da grade (mm)")
    p.add_argument("--amplitude", type=float, help="altura das texturas (mm)")
    p.add_argument("--smooth-region", dest="smooth_region", help="região lisa: externa, maior, nenhuma ou nome/número")
    p.add_argument("--sim", action="store_true", help="fundir sem perguntar (por padrão, num terminal, mostra o plano e pergunta)")
    p.add_argument("--interface", choices=["principal", "auxiliar"], default="principal", help="só para 'abrir'")
    return p


def listar(app: ImageToStl, out=print) -> int:
    projs = app.list_projects()
    if not projs:
        out(f"Repositório vazio ({app.config.base_dir}/). Importe uma imagem: python -m img_to_stl imagem.png")
        return 0
    for n in projs:
        st = app.status(os.path.join(app.config.base_dir, n))
        mark = lambda ok: "✓" if ok else "—"
        out(f"{n:<24} etapa 1 {mark(st['etapa1'])}  etapa 2 {mark(st['etapa2'])}  STL {mark(st['stl'])}")
    return 0


def _regioes(pmap, out) -> None:
    for r in pmap.regions:
        out(f"{r.id:3d}  {r.name:<22} família {r.family:<3}{r.area_mm2:8.0f} mm²" + ("  [fundo]" if r.ignored else ""))


def _texturas(app: ImageToStl, proj: str, pmap, out) -> str:
    """Garante o texturas.json e o lista."""
    e2 = app.etapa2()
    path, _ = e2.prepare_textures(pmap, os.path.join(proj, PASTA_ETAPA2))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name, spec in data["regioes"].items():
        out(f"  {name:<22}{spec}")
    return path


def executar(app: ImageToStl, args: argparse.Namespace, out=print) -> int:
    try:
        proj = app.resolve_project(args.nome)
    except FileNotFoundError as e:
        out(f"Erro: {e}")
        return 2
    app.load_params(proj)
    e2 = app.config.etapa2
    for attr, val in (("resolution_mm", args.resolution), ("texture_amplitude_mm", args.amplitude),
                      ("smooth_region", args.smooth_region)):
        if val is not None:
            setattr(e2, attr, val)
    name = os.path.basename(os.path.normpath(proj))
    st = app.status(proj)
    acao, extra = args.acao, args.args

    try:
        if acao == "reconhecer":
            pmap = app.run_etapa1(app.original_image(proj), proj)
            out(f"✓ {pmap.summary()}")
            return 0
        if not st["etapa1"]:
            out(f"Erro: '{name}' ainda não tem a etapa 1. Rode: python -m img_to_stl projeto {name} reconhecer")
            return 2
        pmap = app.load_etapa1(proj)

        if acao == "ver":
            out(f"{name}: etapa 1 {'✓' if st['etapa1'] else '—'} · etapa 2 {'✓' if st['etapa2'] else '—'} · "
                f"STL {'✓ ' + app.stl_path(proj) if st['stl'] else '—'}")
            out(pmap.summary())
            if e2.smooth_region:
                out(f"Região lisa da sugestão: {e2.smooth_region}")
            out("Texturas:")
            _texturas(app, proj, pmap, out)
        elif acao == "regioes":
            _regioes(pmap, out)
        elif acao == "fundir":
            if not extra:
                out("Erro: diga o que fundir. Ex.: fundir 3,7 · fundir familia · fundir menores=50 · fundir cor=verde,lilas")
                return 2
            for text in extra:
                entry = parse_fusion(text, pmap)
                if isinstance(entry, str) and not args.sim and sys.stdin.isatty():
                    from .interativo import confirm_fusion       # mostra quantas regiões e deixa mudar o limite
                    entry = confirm_fusion(pmap, entry, input, out)
                    if entry is None:
                        out("Cancelado.")
                        return 0
                groups = resolve_fusion(pmap, entry)
                names = "; ".join(" + ".join(pmap.regions[i].name for i in g) for g in groups)
                new = app.fundir_regioes(proj, pmap, entry)
                out(f"✓ {names}  →  {len(pmap.regions)} → {len(new.regions)} regiões")
                pmap = new
            out("Obs.: as texturas foram refeitas (a sugestão antiga ficou em texturas.json.antigo, se existia).")
        elif acao == "fundo":
            apply_background(pmap, e2)
            if not extra:
                atual = [r.name for r in pmap.regions if r.ignored]
                out(f"Fundo atual: {', '.join(atual) or 'nenhum'}  (para mudar: fundo 3 | fundo nenhuma | fundo auto)")
                return 0
            refs = None if extra == ["auto"] else [] if extra[0].lower() in ("nenhuma", "nenhum") else extra
            fundo = app.etapa2().set_background(pmap, os.path.join(proj, PASTA_ETAPA2), refs)
            out(f"✓ Fundo: {', '.join(pmap.regions[i].name for i in fundo) or 'nenhum'} "
                f"(lisa; fora da base silhueta). Para refazer o STL: projeto {name} gerar")
        elif acao == "textura":
            if not extra:
                out("Texturas atuais (para mudar: textura REGIAO=ESPEC, ex.: 3=ondas/3(1.5)):")
                _texturas(app, proj, pmap, out)
                return 0
            path = _texturas(app, proj, pmap, lambda *_: None)
            for item in extra:
                key, _, spec = item.partition("=")
                set_entry(path, key.strip(), spec.strip(), pmap, e2.texture_amplitude_mm)
            out("✓ texturas gravadas:")
            _texturas(app, proj, pmap, out)
        elif acao == "gerar":
            app.log = out
            app.run_etapa2(proj, pmap)
            out(f"✓ STL: {os.path.abspath(app.stl_path(proj))}")
        elif acao == "abrir":
            from . import cli_auxiliar
            from .interativo import interactive_session, params_principal
            step = cli_auxiliar.params_abas if args.interface == "auxiliar" else params_principal
            interactive_session(None, app, proj=proj, start_stage=1 if not extra else 2, params_step=step)
    except (ValueError, KeyError) as e:
        out(f"Erro: {e}")
        return 2
    return 0


def main(argv: Optional[List[str]] = None, out=print) -> int:
    """argv[0] é 'projeto' ou 'projetos'."""
    argv = list(argv or [])
    cfg = PipelineConfig()
    if argv and argv[0] == "projetos":
        rest = argv[1:]
        if "-o" in rest:
            cfg.base_dir = rest[rest.index("-o") + 1]
        return listar(ImageToStl(cfg), out)
    args = build_parser().parse_args(argv[1:])
    if args.output:
        cfg.base_dir = args.output
    if args.saidas:
        cfg.stl_dir = args.saidas
    return executar(ImageToStl(cfg), args, out)
