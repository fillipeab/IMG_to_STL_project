"""Atualizar texturas: relê a pasta de texturas próprias, confere cada arquivo e regrava a lista."""
from __future__ import annotations

import os
import re
from typing import Callable, List, Optional, Tuple

from .registro import TextureLibrary
from .tiles import SUFFIXES, load_directory

ARQUIVO_LISTA = "texturas_disponiveis.txt"


def update_textures(folder: Optional[str], out: Callable[[str], None] = print,
                    catalog_path: str = ARQUIVO_LISTA) -> Tuple[List[int], List[str]]:
    """Relê `folder` (arquivos `<id>_<nome>.stl|png`, id >= 100), valida cada um e regrava `catalog_path`.
    Retorna (ids carregados, problemas). `folder` None/inexistente: só regrava a lista das internas."""
    TextureLibrary.clear_custom()                       # o que saiu da pasta deixa de existir
    ids: List[int] = []
    problems: List[str] = []
    if folder and os.path.isdir(folder):
        for fname in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(fname)
            if ext.lower() in SUFFIXES and not re.match(r"^\d+_.+$", stem):
                problems.append(f"{fname}: nome fora do padrão <id>_<nome> (ex.: 100_domos.stl): ignorado")
        loaded = load_directory(folder)
        for tid in loaded:
            try:
                TextureLibrary.create(tid)              # abre o arquivo de verdade: pega STL/PNG inválido
                ids.append(tid)
                out(f"  ✓ {tid:>3}  {TextureLibrary.describe()[tid]}")
            except Exception as e:                      # noqa: BLE001 - qualquer falha de leitura vira aviso
                problems.append(f"{tid} ({TextureLibrary.describe()[tid]}): {e}")
                for d in (TextureLibrary._registry, TextureLibrary._names, TextureLibrary._descriptions):
                    d.pop(tid, None)
        out(f"  Pasta '{folder}': {len(ids)} textura(s) própria(s) carregada(s)")
    elif folder:
        problems.append(f"pasta '{folder}' não encontrada: lista só com as texturas internas")
    for pr in problems:
        out(f"  ⚠ {pr}")
    path = TextureLibrary.write_catalog(catalog_path)
    out(f"  Lista gravada em {path}")
    return ids, problems
