"""Interface interativa no terminal, em passos curtos: uma pergunta por vez.

Principal (esta): cada etapa abre mostrando só os parâmetros principais; `p` mostra/altera todos, por grupo.
Auxiliar (cli_auxiliar.py, "versão 2"): os parâmetros ficam em abas (grupos) que se abrem uma a uma.
As duas dividem o resto do fluxo (menu, fusão, texturas, STL); muda só o passo "parâmetros".

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
from .etapa1_reconhecimento.criterios import LIMITES, limit_of, parse_fusion, resolve_fusion, with_limit
from .config import PipelineConfig
from .etapa1_reconhecimento.config import AJUDA as AJUDA1
from .etapa2_texturas.biblioteca import TextureLibrary
from .etapa2_texturas.config import AJUDA as AJUDA2
from .etapa2_texturas.texturas_arquivo import set_entry
from .etapa2_texturas.pipeline import apply_background
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
# Os poucos parâmetros que aparecem logo ao abrir cada etapa
PRINCIPAIS1 = ["width_mm", "max_regions", "color_tolerance", "ignore_color"]
PRINCIPAIS2 = ["resolution_mm", "base_thickness_mm", "base_mode", "texture_amplitude_mm", "smooth_region"]
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
    # avançados (etapa 1)
    "work_max_px": "Resolução de trabalho (px)", "denoise_iterations": "Passadas do filtro de ruído",
    "denoise_sigma_color": "Filtro: tolerância de cor", "denoise_sigma_space": "Filtro: vizinhança (px)",
    "n_color_clusters": "Cores iniciais (k-means)", "simplify_tol_mm": "Simplificação das curvas (mm)",
    "triple_min_regions": "Regiões mínimas num ponto tríplice", "triple_merge_dist_mm": "Distância p/ unir tríplices (mm)",
    "marker_max_area_mm2": "Área máxima de um marcador (mm²)", "negatives_px_per_mm": "Negativos: pixels por mm",
    "negatives_line_mm": "Negativos: espessura da linha (mm)", "negatives_point_radius_mm": "Negativos: raio dos pontos (mm)",
    "random_seed": "Semente aleatória",
    # avançados (etapa 2)
    "ridge_profile": "Perfil dos traços", "apex_round_mm": "Arredondamento da ponta (mm)",
    "min_feature_warn_mm": "Aviso de traço mínimo (mm)", "texture_params": "Parâmetros próprios das texturas",
    "border_semicircle": "Cordão semicircular", "exclusion_fade_mm": "Rampa da faixa livre (mm)",
    "exclusion_texture_height_factor": "Altura da textura na faixa livre", "point_flank_mm": "Rampa dos pontos (mm)",
    "point_exclusion_mm": "Faixa livre em volta do ponto (mm)", "point_shape_by_class": "Forma dos pontos por classe",
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
                out: Callable[[str], None], headers: Optional[Dict[int, str]] = None,
                extras: Optional[Dict[str, Tuple[str, Callable[[], None]]]] = None,
                exit_label: str = "voltar", reprint: bool = True) -> None:
    """Lista numerada de parâmetros. Número altera, ?<número> explica, Enter sai.
    `headers`: {posição: título do grupo}; `extras`: {letra: (texto, função)}; `reprint=False` só relista com 'l'."""
    headers, extras = headers or {}, extras or {}

    def show() -> None:
        out("")
        for i, k in enumerate(keys, 1):
            if i - 1 in headers:
                out(f"  ── {headers[i - 1]}")
            out(f"  {i:2d}) {ROTULOS.get(k, k):<36}{fmt(getattr(cfg, k))}")

    show()
    while True:
        out("")
        parts = ["número = alterar", "?<número> = explicar"] + [f"{k} = {d}" for k, (d, _) in extras.items()]
        if not reprint:
            parts.append("l = listar de novo")
        resp = ask(" · ".join(parts) + f" · Enter = {exit_label}: ").strip()
        if not resp:
            return
        if resp.lower() in extras:
            extras[resp.lower()][1]()
            if reprint:
                show()
            continue
        if resp.lower() == "l" and not reprint:
            show()
            continue
        explain = resp.startswith("?")
        num = resp[1:].strip().strip("<>") if explain else resp
        if not num.isdigit() or not (1 <= int(num) <= len(keys)):
            out(f"  Comando não reconhecido: '{resp}'. Use um número de 1 a {len(keys)}, ?<número> ou Enter.")
            continue
        key = keys[int(num) - 1]
        out("")
        _explain(cfg, key, notes, out)
        if explain:
            continue
        raw = ask("  Novo valor (Enter = manter · 'nenhum' = vazio): ")
        if raw.strip():
            old = getattr(cfg, key)
            try:
                setattr(cfg, key, parse_value(raw, old))
                if hasattr(cfg, "validate"):
                    cfg.validate()
                out(f"  ✓ {ROTULOS.get(key, key)} = {fmt(getattr(cfg, key))}")
            except (ValueError, TypeError) as e:
                setattr(cfg, key, old)
                out(f"  Valor inválido: {e}")
        if reprint:
            show()


def all_groups(cfg, groups: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[str]]]:
    """Os grupos + "Avançado" com tudo o que não coube neles."""
    used = {k for _, ks in groups for k in ks}
    rest = [f.name for f in fields(cfg) if f.name not in used]
    return groups + ([("Avançado", rest)] if rest else [])


def params_principal(cfg, groups, principais, notes, ask, out) -> None:
    """Passo "parâmetros" da interface principal: só os principais; `p` abre a lista completa por grupo."""
    def full() -> None:
        keys, headers = [], {}
        for title, ks in all_groups(cfg, groups):
            headers[len(keys)] = title
            keys += ks
        rule(out, "Todos os parâmetros")
        edit_params(cfg, keys, notes, ask, out, headers=headers, exit_label="voltar", reprint=False)
        rule(out, "Parâmetros principais")

    out("  Parâmetros principais")
    edit_params(cfg, principais, notes, ask, out, extras={"p": ("ver/alterar todos", full)},
                exit_label="continuar")


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


def confirm_fusion(pmap, entry, ask, out):
    """Mostra quantas regiões o critério funde e deixa continuar, mudar o limite ou cancelar.
    Retorna o item de fusão final (talvez com outro limite) ou None se cancelar."""
    n = len(pmap.regions)
    while True:
        lim = limit_of(entry)
        try:
            groups = resolve_fusion(pmap, entry)
        except ValueError as e:
            groups = []
            out(f"  {e}")
        if groups:
            merged = sum(len(g) - 1 for g in groups)
            out(f"  Vai fundir {merged} região(ões) em {len(groups)} grupo(s): {n} → {n - merged} regiões")
            for g in groups[:8]:
                out("    " + " + ".join(pmap.regions[i].name for i in g))
            if len(groups) > 8:
                out(f"    ... e mais {len(groups) - 8} grupo(s)")
        opts = (["[Enter] continuar"] if groups else []) \
            + ([f"[l] mudar o {LIMITES[lim[0]][0]} (atual: {lim[1]:g} {LIMITES[lim[0]][1]})"] if lim else []) \
            + ["[c] cancelar"]
        r = ask(" · ".join(opts) + ": ").strip().lower()
        if r == "c" or (not r and not groups):
            return None
        if not r:
            return entry
        if r == "l" and lim:
            raw = ask(f"  Novo {LIMITES[lim[0]][0]} ({LIMITES[lim[0]][1]}): ").strip().replace(",", ".")
            try:
                entry = with_limit(entry, float(raw))
            except ValueError:
                out(f"  '{raw}' não é um número.")


def merge_dialog(app: ImageToStl, proj: str, pmap, ask, out):
    """Fundir regiões a pedido (números/nomes ou critério). Retorna o novo mapa (ou o mesmo, se cancelar)."""
    rule(out, "Fundir regiões")
    show_regions(pmap, out)
    out("")
    out("  Escolha: números ou nomes (ex.: 3 7) · ou um critério:")
    out("    parecidas 8 = junta vizinhas com cor parecida (ΔE < 8) · menores 50 = junta as < 50 mm² na vizinha parecida")
    out("    familia = junta irmãs que se tocam · cor verde = junta as regiões dessa cor")
    resp = ask("Fundir (Enter = cancelar): ").strip()
    if not resp:
        return pmap
    try:
        entry = parse_fusion(resp, pmap)
        if isinstance(entry, str):                       # critério: mostra o plano e deixa ajustar o limite
            entry = confirm_fusion(pmap, entry, ask, out)
            if entry is None:
                return pmap
        new = app.fundir_regioes(proj, pmap, entry)
    except ValueError as e:
        out(f"  Não foi possível fundir: {e}")
        return pmap
    out(f"  ✓ {len(pmap.regions)} → {len(new.regions)} regiões")
    return new


def background_step(e2, pmap, out_dir: str, ask, out) -> None:
    """Passo opcional da etapa 2: escolher qual região é o FUNDO (lisa e fora da base silhueta)."""
    apply_background(pmap, e2.config)
    atual = [r.name for r in pmap.regions if r.ignored]
    out("")
    out(f"  Região de fundo: {', '.join(atual) or 'nenhuma'}")
    if ask("[Enter] manter · [f] escolher a região de fundo: ").strip().lower() != "f":
        return
    show_regions(pmap, out)
    while True:
        out("")
        resp = ask("Região de fundo (número ou nome) · [n] nenhuma · [a] a reconhecida na etapa 1 · Enter = manter: ").strip()
        if not resp:
            return
        try:
            refs = None if resp.lower() == "a" else [] if resp.lower() == "n" else resp.replace(",", " ").split()
            fundo = e2.set_background(pmap, out_dir, refs)
        except ValueError as e:
            out(f"  Não aceito: {e}")
            continue
        out(f"  ✓ Fundo: {', '.join(pmap.regions[i].name for i in fundo) or 'nenhuma'}")
        return


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


def interface_name(params_step) -> str:
    return "principal" if params_step is params_principal else "auxiliar (versão 2)"


def main_menu(app: ImageToStl, ask: Callable[[str], str] = input, out: Callable[[str], None] = print,
              params_step=None) -> bool:
    """Menu inicial. Cada escolha roda uma sessão e volta ao menu. Retorna False ao sair."""
    from . import cli_auxiliar                          # import tardio (cli_auxiliar importa este módulo)
    step = params_step or params_principal
    while True:
        rule(out, "img_to_stl")
        out(f"  repositório: {app.config.base_dir}/    STL: {app.config.stl_dir}/")
        out("")
        out("  1) Importar nova imagem")
        out("  2) Operar em uma imagem já existente")
        out(f"  3) Trocar de interface (atual: {interface_name(step)})")
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
            interactive_session(image, app, proj=app.project_dir(name), ask=ask, out=out, params_step=step)
        elif r == "2":
            _open_existing(app, ask, out, step)
        elif r == "3":
            step = cli_auxiliar.params_abas if step is params_principal else params_principal
            out(f"\n  Interface: {interface_name(step)}")


def _open_existing(app: ImageToStl, ask, out, params_step=None) -> None:
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
        interactive_session(app.original_image(proj), app, proj=proj, ask=ask, out=out, params_step=params_step)
    elif a == "2" and st["etapa1"]:
        app.load_params(proj)
        interactive_session(None, app, proj=proj, ask=ask, out=out, start_stage=2, params_step=params_step)


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
                        start_stage: int = 1, params_step=None) -> Optional[str]:
    """Etapa 1 -> (ajustes) -> etapa 2 -> (ajustes) -> STL. Retorna o caminho do STL (ou None se parou antes)."""
    cfg: PipelineConfig = app.config
    step = params_step or params_principal
    proj = proj or app.project_dir(image_path)
    name = os.path.basename(os.path.normpath(proj))

    if start_stage == 1:
        rule(out, f"Etapa 1 · reconhecimento · {name}")
        while True:
            step(cfg.etapa1, GRUPOS1, PRINCIPAIS1, AJUDA1, ask, out)
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
    step(cfg.etapa2, GRUPOS2, PRINCIPAIS2, AJUDA2, ask, out)

    e2 = app.etapa2()
    out_dir = os.path.join(proj, PASTA_ETAPA2)
    background_step(e2, pmap, out_dir, ask, out)
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
