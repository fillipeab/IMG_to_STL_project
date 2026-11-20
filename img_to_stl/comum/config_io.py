"""Leitura/escrita de configurações em JSON a partir de dataclasses.

JSON não aceita comentários: notas ficam em chaves que começam com "_" (ignoradas ao ler).
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Dict, Iterable, Optional


def with_notes(values: Dict[str, Any], notes: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in values.items():
        if k in notes:
            out["_" + k] = notes[k]
        out[k] = v
    return out


def to_json_file(obj, path: str, notes: Optional[Dict[str, str]] = None) -> None:
    """Grava um dataclass em JSON; com `notes`, cada parâmetro vem precedido de uma nota "_nome"."""
    data = asdict(obj) if is_dataclass(obj) else dict(obj)
    if notes:
        data = {"_leia_me": "Chaves que começam com '_' são notas e são ignoradas. "
                            "Edite só os valores. Medidas em mm.", **with_notes(data, notes)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def dataclass_from_dict(klass, data: Dict[str, Any], int_key_fields: Iterable[str] = (),
                        tuple_fields: Iterable[str] = ()):
    """Cria o dataclass ignorando notas ("_...") e rejeitando chaves desconhecidas;
    converte chaves '3' -> 3 nos campos listados e listas em tuplas nos campos de `tuple_fields`."""
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    valid = {f.name for f in fields(klass)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"Parâmetros desconhecidos em {klass.__name__}: {sorted(unknown)}")
    kwargs = {}
    for name, value in data.items():
        if name in int_key_fields and isinstance(value, dict):
            value = {int(k): v for k, v in value.items()}
        if name in tuple_fields and value is not None:
            value = tuple(int(c) for c in value)
        kwargs[name] = value
    return klass(**kwargs)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
