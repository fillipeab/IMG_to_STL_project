"""Configuração completa: etapa 1 + etapa 2 + saída (um único JSON com as três seções)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from .comum.config_io import read_json, with_notes
from .etapa1_reconhecimento import parametros as P1
from .etapa1_reconhecimento.config import AJUDA as AJUDA1, Etapa1Config
from .etapa2_texturas.config import AJUDA as AJUDA2, Etapa2Config


@dataclass
class PipelineConfig:
    etapa1: Etapa1Config = field(default_factory=Etapa1Config)
    etapa2: Etapa2Config = field(default_factory=Etapa2Config)
    # Repositório: cada imagem ganha a subpasta "<base_dir>/<nome_da_imagem>/" (original, etapa 1, etapa 2).
    base_dir: str = P1.PASTA_REPOSITORIO
    # Pasta só com os STL prontos: "<stl_dir>/<nome_da_imagem>.stl".
    stl_dir: str = P1.PASTA_STL
    # True = grava os negativos (regiões, famílias, fronteiras e pontos) na pasta da etapa 1.
    negatives: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: str, comments: bool = False) -> None:
        data = self.to_dict()
        if comments:
            data = {"etapa1": with_notes(data["etapa1"], AJUDA1), "etapa2": with_notes(data["etapa2"], AJUDA2),
                    "base_dir": data["base_dir"], "stl_dir": data["stl_dir"], "negatives": data["negatives"]}
            data = {"_leia_me": "Chaves que começam com '_' são notas e são ignoradas. Edite só os valores. "
                                "Medidas em mm.", **data}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        return cls(etapa1=Etapa1Config.from_dict(data.get("etapa1", {})),
                   etapa2=Etapa2Config.from_dict(data.get("etapa2", {})),
                   base_dir=data.get("base_dir", P1.PASTA_REPOSITORIO),
                   stl_dir=data.get("stl_dir", P1.PASTA_STL), negatives=bool(data.get("negatives", True)))

    @classmethod
    def from_json(cls, path: str) -> "PipelineConfig":
        return cls.from_dict(read_json(path))
