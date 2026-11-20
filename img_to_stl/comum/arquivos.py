"""Nomes e pastas de saída."""
from __future__ import annotations

import os
import re
import unicodedata


def slug(text: str) -> str:
    """'Azul claro' -> 'azul_claro' (sem acentos, minúsculas, só letras/números/_)."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "x"


def image_stem(image_path: str) -> str:
    return os.path.splitext(os.path.basename(image_path))[0]


def project_dir(image_path: str, base_dir: str) -> str:
    """Pasta do projeto: <base_dir>/<nome_da_imagem>/"""
    return os.path.join(base_dir, image_stem(image_path))


def ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
