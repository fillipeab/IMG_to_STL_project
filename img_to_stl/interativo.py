"""Interface interativa no terminal, em passos curtos: uma pergunta por vez.

Todas as perguntas passam por `ask` (padrão: input) e as mensagens por `out` (padrão: print),
o que permite testar com respostas prontas.
"""
from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, fields
from typing import Any, Callable, Dict, List, Optional, Tuple

from .comum.arquivos import slug
from .config import PipelineConfig
from .etapa1_reconhecimento.config import AJUDA as AJUDA1
from .etapa2_texturas.biblioteca import TextureLibrary
from .etapa2_texturas.config import AJUDA as AJUDA2
from .etapa2_texturas.texturas_arquivo import set_entry
from .pipeline import PASTA_ETAPA1, PASTA_ETAPA2, ImageToStl

# Parâmetros agrupados por assunto (o grupo "Avançado" recebe todos os que sobram)
GRUPOS1: List[Tuple[str, List[str]]] = [
    ("Tamanho e regiões", ["width_mm", "max_regions", "color_tolerance", "min_region_area_mm2", "min_region_thickness_mm"]),
    ("Famílias e fundo", ["family_tolerance", "ignore_color", "ignore_tolerance"]),
    ("Fronteiras", ["min_border_length_mm", "smooth_sigma_mm", "outer_frame"]),
    ("Pontos de interesse", ["point_markers", "points_file"]),
]
GRUPOS2: List[Tuple[str, List[str]]] = [
    ("Base e resolução", ["resolution_mm", "base_thickness_mm", "base_mode", "base_regions", "frame_cord"]),
    ("Texturas", ["texture_amplitude_mm", "smooth_region", "default_textures", "texture_dir", "exclusion_texture_scale"]),
    ("Cordão das fronteiras", ["border_width_mm", "border_height_mm", "border_exclusion_mm"]),
    ("Pontos", ["point_shape", "point_size_mm", "point_height_mm", "model_triple_points", "model_multiple_points"]),
]
ROTULOS = {
    "width_mm": "Largura da peça (mm)", "max_regions": "Máximo de regiões", "color_tolerance": "Tolerância de cor (ΔE)",
    "min_region_area_mm2": "Área mínima de região (mm²)", "min_region_thickness_mm": "Espessura mínima de região (mm)",
    "family_tolerance": "Tolerância de cor das famílias", "ignore_color": "Cor de fundo (RGB)",
    "ignore_tolerance": "Tolerância da cor de fundo", "min_border_length_mm": "Fronteira mínima (mm)",
    "smooth_sigma_mm": "Suavização das curvas (mm)", "outer_frame": "Moldura externa",
    "point_markers": "Marcadores de pontos (cores)", "points_file": "Arquivo de pontos",
    "resolution_mm": "Resolução da grade (mm)", "base_thickness_mm": "Espessura da base (mm)",
    "base_mode": "Formato da base", "base_regions": "Regiões da base (silhueta)", "frame_cord": "Cordão da moldura",
    "texture_amplitude_mm": "Altura das texturas (mm)", "default_textures": "Texturas sugeridas", "smooth_region": "Região lisa (externa/maior/nenhuma)",
    "merge_regions": "Fusões de regiões",
    "texture_dir": "Pasta de texturas próprias", "exclusion_texture_scale": "Escala da textura nas bordas",
    "border_width_mm": "Largura do cordão (mm)", "border_height_mm": "Altura do cordão (mm)",
    "border_exclusion_mm": "Faixa livre junto ao cordão (mm)", "point_shape": "Forma dos pontos",
    "point_size_mm": "Tamanho dos pontos (mm)", "point_height_mm": "Altura dos pontos (mm)",
    "model_triple_points": "Modelar pontos tríplices", "model_multiple_points": "Modelar pontos múltiplos",
}
LARGURA = 60


def rule(out: Callable[[str], None], title: str) -> None:
    """Cabeçalho de passo, para separar bem as etapas na tela."""
    out("")
    out(f"── {title} " + "─" * max(3, LARGURA - len(title) - 4))


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "sim" if value else "não"
    if value is None:
        return "nenhum"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple, dict)):
        txt = json.dumps(value, ensure_ascii=False)
        return txt if len(txt) <= 36 else txt[:33] + "..."
    return str(value)


# --------------------------------------------------------------------------- #
# Parâmetros
# --------------------------------------------------------------------------- #
def parse_value(text: str, current: Any) -> Any:
    """Converte o que a pessoa digitou para o tipo do valor atual."""
    t = text.strip()
    if t.lower() in ("nenhum", "nenhuma", "none", "null", "-"):
        return None
    if isinstance(current, bool):
        if t.lower() in ("s", "sim", "true", "1", "ligado", "on"):
            return True
        if t.lower() in ("n", "nao", "não", "false", "0", "desligado", "off"):
            return False
        raise ValueError("responda sim ou não")
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        number = float(t.replace(",", "."))
        return int(number) if isinstance(current, int) else number
    try:
        return json.loads(t)                      # listas, dicionários, números
    except json.JSONDecodeError:
        return t                                  # texto puro (ex.: retangular, circle)


def _explain(cfg, key: str, notes: Dict[str, str], out: Callable[[str], None]) -> None:
    default = getattr(type(cfg)(), key)
    out(f"  {ROTULOS.get(key, key)}  [{key}]")
    out(f"    {notes.get(key, '(sem descrição)')}")
    out(f"    valor atual: {fmt(getattr(cfg, key))}  ·  padrão: {fmt(default)}")


def edit_params(cfg, keys: List[str], notes: Dict[str, str], ask: Callable[[str], str],
                out: Callable[[str], None]) -> None:
    """Lista curta de parâmetros (um grupo). Número altera, ?número explica, Enter volta."""
    while True:
        out("")
        for i, k in enumerate(keys, 1):
            out(f"  {i}) {ROTULOS.get(k, k):<34}{fmt(getattr(cfg, k))}")
        out("")
        resp = ask("Número = alterar · ?número = explicação · Enter = voltar: ").strip()
        if not resp:
            return
        explain = resp.startswith("?")
        num = resp[1:].strip() if explain else resp
        if not num.isdigit() or not (1 <= int(num) <= len(keys)):
            out(f"  Comando não reconhecido: '{resp}'. Use um número de 1 a {len(keys)}, ?número ou Enter.")
            continue
        key = keys[int(num) - 1]
        out("")
        _explain(cfg, key, notes, out)
        if explain:
            continue
        raw = ask("  Novo valor (Enter = manter · 'nenhum' = vazio): ")
        if not raw.strip():
            continue
        old = getattr(cfg, key)
        try:
            setattr(cfg, key, parse_value(raw, old))
            if hasattr(cfg, "validate"):
                cfg.validate()
        except (ValueError, TypeError) as e:
            setattr(cfg, key, old)
            out(f"  Valor inválido: {e}")


def choose_params(cfg, groups: List[Tuple[str, List[str]]], notes: Dict[str, str], ask, out) -> None:
    """Passo "Parâmetros": usar os atuais (Enter) ou ajustar por grupo."""
    r = ask("Parâmetros: [Enter] usar os valores atuais · [a] ajustar: ").strip().lower()
    if r != "a":
        return
    used = {k for _, ks in groups for k in ks}
    rest = [f.name for f in fields(cfg) if f.name not in used]
    groups = groups + ([("Avançado", rest)] if rest else [])
    while True:
        rule(out, "Grupos de parâmetros")
        for i, (title, _) in enumerate(groups, 1):
            out(f"  {i}) {title}")
        out("")
        g = ask("Grupo (número) · Enter = pronto: ").strip()
        if not g:
            return
        if not g.isdigit() or not (1 <= int(g) <= len(groups)):
            out(f"  Escolha de 1 a {len(groups)}, ou Enter.")
            continue
        title, keys = groups[int(g) - 1]
        rule(out, title)
        edit_params(cfg, keys, notes, ask, out)


# --------------------------------------------------------------------------- #
# Resultados e texturas
# --------------------------------------------------------------------------- #
def show_stage1(pmap, proj: str, out: Callable[[str], None]) -> None:
    cls = pmap.classes()
    out("")
    out(f"  ✓ {len(pmap.regions)} regiões · {len(pmap.families)} famílias · {len(pmap.borders)} fronteiras")
    out("  Pontos: " + (", ".join(f"{n} {c}" for c, n in cls.items()) if cls else "nenhum"))
    out(f"  Prévia: {os.path.join(proj, PASTA_ETAPA1, 'previa.png')}")


def show_regions(pmap, out: Callable[[str], None]) -> None:
    out("")
    for r in pmap.regions:
        out(f"  {r.id:2d}) {r.name:<20} família {r.family:<3}{r.area_mm2:7.0f} mm²" + ("   [fundo]" if r.ignored else ""))


def parse_regions(text: str, pmap) -> List[int]:
    """'3 7', '3,7' ou nomes ('03_verde 07_azul') -> ids das regiões."""
    by_name = {r.name: r.id for r in pmap.regions}
    ids = []
    for tok in text.replace(",", " ").split():
        if tok.isdigit():
            ids.append(int(tok))
        elif tok in by_name:
            ids.append(by_name[tok])
        else:
            raise ValueError(f"'{tok}' não é número nem nome de região")
    return ids


def merge_dialog(app: ImageToStl, proj: str, pmap, ask, out):
    """Fundir regiões a pedido. Retorna o novo mapa (ou o mesmo, se cancelar/errar)."""
    rule(out, "Fundir regiões")
    show_regions(pmap, out)
    out("")
    resp = ask("Regiões a fundir (números ou nomes, ex.: 3 7) · Enter = cancelar: ").strip()
    if not resp:
        return pmap
    try:
        group = parse_regions(resp, pmap)
        new = app.fundir_regioes(proj, pmap, group)
    except ValueError as e:
        out(f"  Não foi possível fundir: {e}")
        return pmap
    out(f"  ✓ fundidas: {' + '.join(pmap.regions[i].name for i in dict.fromkeys(group))}")
    return new


def show_catalog(out: Callable[[str], None]) -> None:
    """Lista as texturas existentes (as internas e as de CAD/PNG já carregadas)."""
    out("")
    out("  Texturas disponíveis:")
    for tid, name, desc in TextureLibrary.catalog():
        out(f"    {tid:>3}  {name:<18}{desc}")
    out("  Com distorção: ondas/3(1.5, 2, 30) = escala 1,5 · alongada 2x · a 30°")


def show_textures(path: str, pmap, out: Callable[[str], None]) -> Dict[int, str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out("")
    rows = {}
    for i, r in enumerate(pmap.regions, 1):
        rows[i] = r.name
        out(f"  {i:2d}) {r.name:<20}{data['regioes'].get(r.name, '?')}")
    return rows


def edit_textures(path: str, pmap, app: ImageToStl, ask, out) -> None:
    amp = app.config.etapa2.texture_amplitude_mm
    while True:
        rows = show_textures(path, pmap, out)
        out("")
        resp = ask("Região a alterar (número) · l = lista de texturas · Enter = aceitar: ").strip()
        if not resp:
            return
        if resp.lower() == "l":
            show_catalog(out)
            continue
        if not resp.isdigit() or int(resp) not in rows:
            out(f"  Escolha um número de 1 a {len(rows)}.")
            continue
        name = rows[int(resp)]
        rule(out, f"Textura para {name}")
        show_catalog(out)
        while True:
            out("")
            spec = ask("Textura (número ou nome) · ? = lista · Enter = manter: ").strip()
            if not spec:
                break
            if spec == "?":
                show_catalog(out)
                continue
            try:
                set_entry(path, name, spec, pmap, amp)
                break
            except (ValueError, KeyError) as e:
                out(f"  Não aceito: {e}")
        rule(out, "Texturas")


# --------------------------------------------------------------------------- #
# Menu principal: importar nova imagem / operar em imagem existente
# --------------------------------------------------------------------------- #
def ask_image_path(ask: Callable[[str], str], out: Callable[[str], None]) -> Optional[str]:
    """Pergunta o endereço da imagem até existir (Enter vazio = voltar)."""
    while True:
        path = os.path.expanduser(ask("Endereço da imagem (pode arrastar o arquivo) · Enter = voltar: ").strip().strip("\"'"))
        if not path:
            return None
        if os.path.isfile(path):
            return path
        out(f"  Arquivo não encontrado: {path!r}.")


def choose_project_name(app: ImageToStl, image_path: str, ask, out) -> Optional[str]:
    """Nome do projeto no repositório. Se já existir: sobrescrever, novo nome ou cancelar."""
    stem = os.path.splitext(os.path.basename(image_path))[0]
    name = slug(stem)
    if not app.exists(name):
        return name
    out(f"\n  '{name}' já existe no repositório.")
    while True:
        r = ask("[s] sobrescrever · [n] novo nome · [c] cancelar: ").strip().lower()
        if r == "s":
            return name
        if r == "c":
            return None
        if r == "n":
            suggestion = app.unique_name(stem)
            new = slug(ask(f"Novo nome (Enter = {suggestion}): ").strip() or suggestion)
            if app.exists(new):
                out(f"  '{new}' também já existe.")
                continue
            return new


def _status_text(st: Dict[str, bool]) -> str:
    mark = lambda ok: "✓" if ok else "—"
    return f"etapa 1 {mark(st['etapa1'])}   etapa 2 {mark(st['etapa2'])}   STL {mark(st['stl'])}"


def main_menu(app: ImageToStl, ask: Callable[[str], str] = input, out: Callable[[str], None] = print) -> bool:
    """Menu inicial. Cada escolha roda uma sessão e volta ao menu. Retorna False ao sair."""
    while True:
        rule(out, "img_to_stl")
        out(f"  repositório: {app.config.base_dir}/    STL: {app.config.stl_dir}/")
        out("")
        out("  1) Importar nova imagem")
        out("  2) Operar em uma imagem já existente")
        out("  0) Sair")
        out("")
        r = ask("Escolha: ").strip()
        if r in ("0", "", "q"):
            return False
        if r == "1":
            image = ask_image_path(ask, out)
            if not image:
                continue
            name = choose_project_name(app, image, ask, out)
            if name is None:
                continue
            interactive_session(image, app, proj=app.project_dir(name), ask=ask, out=out)
        elif r == "2":
            _open_existing(app, ask, out)


def _open_existing(app: ImageToStl, ask, out) -> None:
    projects = app.list_projects()
    if not projects:
        out("\n  O repositório está vazio. Importe uma imagem primeiro (opção 1).")
        return
    rule(out, "Imagens no repositório")
    for i, n in enumerate(projects, 1):
        out(f"  {i:2d}) {n:<22}{_status_text(app.status(os.path.join(app.config.base_dir, n)))}")
    out("")
    sel = ask("Número da imagem · Enter = voltar: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(projects)):
        return
    name = projects[int(sel) - 1]
    proj = os.path.join(app.config.base_dir, name)
    st = app.status(proj)
    rule(out, name)
    out("  1) Refazer a etapa 1 (reconhecimento)")
    out("  2) Etapa 2: ajustar texturas e gerar o STL" + ("" if st["etapa1"] else "   [falta a etapa 1]"))
    out("  3) Voltar")
    out("")
    a = ask("Escolha: ").strip()
    if a == "1":
        app.load_params(proj)
        interactive_session(app.original_image(proj), app, proj=proj, ask=ask, out=out)
    elif a == "2" and st["etapa1"]:
        app.load_params(proj)
        interactive_session(None, app, proj=proj, ask=ask, out=out, start_stage=2)


# --------------------------------------------------------------------------- #
# Sessão: etapa 1 -> etapa 2
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def _quiet(app: ImageToStl):
    """Guarda as mensagens de andamento (o terminal mostra só um resumo)."""
    saved, captured = app.log, []
    app.log = captured.append
    try:
        yield captured
    finally:
        app.log = saved


def _warnings_line(captured: List[str], where: str, out: Callable[[str], None]) -> None:
    n = sum(1 for m in captured if m.startswith("[aviso]"))
    if n:
        out(f"  ⚠ {n} aviso(s) — detalhes em {where}")


def interactive_session(image_path: Optional[str], app: ImageToStl, proj: Optional[str] = None,
                        ask: Callable[[str], str] = input, out: Callable[[str], None] = print,
                        start_stage: int = 1) -> Optional[str]:
    """Etapa 1 -> (ajustes) -> etapa 2 -> (ajustes) -> STL. Retorna o caminho do STL (ou None se parou antes)."""
    cfg: PipelineConfig = app.config
    proj = proj or app.project_dir(image_path)
    name = os.path.basename(os.path.normpath(proj))

    if start_stage == 1:
        rule(out, f"Etapa 1 · reconhecimento · {name}")
        while True:
            choose_params(cfg.etapa1, GRUPOS1, AJUDA1, ask, out)
            out("\n  Processando a imagem...")
            with _quiet(app) as captured:
                pmap = app.run_etapa1(image_path, proj)
            show_stage1(pmap, proj, out)
            _warnings_line(captured, os.path.join(proj, PASTA_ETAPA1, "parametros_e_resultados.txt"), out)
            while True:
                out("")
                r = ask("[Enter] etapa 2 · [v] ver regiões · [f] fundir regiões · [r] refazer · [s] parar: ").strip().lower()
                if r == "v":
                    show_regions(pmap, out)
                    continue
                if r == "f":
                    pmap = merge_dialog(app, proj, pmap, ask, out)
                    show_stage1(pmap, proj, out)
                    continue
                break
            if r == "r":
                rule(out, f"Etapa 1 · reconhecimento · {name}")
                continue
            if r == "s":
                return None
            break
    else:
        pmap = app.load_etapa1(proj)

    rule(out, f"Etapa 2 · textura e STL · {name}")
    choose_params(cfg.etapa2, GRUPOS2, AJUDA2, ask, out)

    e2 = app.etapa2()
    out_dir = os.path.join(proj, PASTA_ETAPA2)
    with _quiet(app):
        e2.log = lambda m: None
        path, _ = e2.prepare_textures(pmap, out_dir)
    while True:
        rule(out, "Texturas das regiões")
        edit_textures(path, pmap, app, ask, out)
        rule(out, "Gerar o STL")
        r = ask("[Enter] gerar agora · [t] voltar às texturas · [s] sair sem gerar: ").strip().lower()
        if r == "t":
            continue
        if r == "s":
            return None
        break

    stl_path = app.stl_path(proj)
    out("\n  Gerando o STL...")
    e2 = app.etapa2()
    with _quiet(app) as captured:
        e2.log = captured.append
        e2.run(pmap, out_dir, stl_path)
    out(f"\n  ✓ STL pronto: {stl_path}")
    _warnings_line(captured, os.path.join(out_dir, "relatorio.txt"), out)
    out(f"  Para mudar as texturas depois: menu → opção 2 (ou edite {os.path.join(out_dir, 'texturas.json')}).")
    return stl_path
