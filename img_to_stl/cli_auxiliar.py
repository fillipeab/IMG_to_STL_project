"""Interface AUXILIAR ("versão 2"): os parâmetros ficam em abas (grupos) que se abrem uma a uma.

O resto do fluxo (menu, fusão, texturas, STL) é o mesmo da interface principal (interativo.py);
muda só o passo "parâmetros":  [Enter] usar os atuais · [a] ajustar -> escolher o grupo -> editar.

Uso:  python -m img_to_stl --interface auxiliar      (ou, no menu inicial, 3 = trocar de interface)
"""
from __future__ import annotations

from typing import Callable

from .interativo import all_groups, edit_params, main_menu as _main_menu, rule


def params_abas(cfg, groups, principais, notes, ask, out) -> None:
    """Passo "parâmetros" em abas: usar os atuais (Enter) ou ajustar por grupo."""
    r = ask("Parâmetros: [Enter] usar os valores atuais · [a] ajustar: ").strip().lower()
    if r != "a":
        return
    groups = all_groups(cfg, groups)
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


def main_menu(app, ask: Callable[[str], str] = input, out: Callable[[str], None] = print) -> bool:
    """Menu inicial já na interface auxiliar."""
    return _main_menu(app, ask, out, params_step=params_abas)
