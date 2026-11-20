"""Registro de texturas: id e nome -> fábrica. Aceita o id (3) ou o nome ("ondas")."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple, Type

from .base import RidgeProfile, Texture


def _norm(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return "_".join(t.replace("'", "").replace("-", " ").split())


class TextureLibrary:
    """Registro id -> fábrica de textura (classe `Texture` ou função, ex.: arquivos de CAD)."""

    _registry: Dict[int, Callable[..., Texture]] = {}
    _names: Dict[int, str] = {}
    _descriptions: Dict[int, str] = {}

    @classmethod
    def register(cls, klass: Type[Texture]) -> Type[Texture]:
        cls.register_factory(klass.texture_id, klass.name, klass, klass.description)
        return klass

    @classmethod
    def register_factory(cls, texture_id: int, name: str, factory: Callable[..., Texture],
                         description: str = "") -> None:
        cls._registry[texture_id] = factory
        cls._names[texture_id] = name
        cls._descriptions[texture_id] = description

    @classmethod
    def create(cls, texture_id: int, profile: Optional[RidgeProfile] = None, **params) -> Texture:
        if texture_id not in cls._registry:
            raise KeyError(f"Textura {texture_id} não existe. Disponíveis: {cls.describe()}")
        return cls._registry[texture_id](profile=profile, **params)

    @classmethod
    def resolve(cls, ref) -> int:
        """Aceita o id (3 ou "3") ou o nome ("ondas", "linhas_diagonais"; sem acento nem maiúsculas)."""
        if isinstance(ref, int):
            return ref
        txt = str(ref).strip()
        if txt.lstrip("-").isdigit():
            return int(txt)
        key = _norm(txt)
        for tid, name in cls._names.items():
            if _norm(name) == key:
                return tid
        raise KeyError(f"Textura '{ref}' não existe. Disponíveis: "
                       + ", ".join(f"{i}={n}" for i, n in cls.describe().items()))

    @classmethod
    def catalog(cls) -> List[Tuple[int, str, str]]:
        """Lista (id, nome, descrição) de todas as texturas disponíveis, em ordem de id."""
        return [(i, cls._names[i], cls._descriptions.get(i, "")) for i in sorted(cls._names)]

    @classmethod
    def describe(cls) -> Dict[int, str]:
        return dict(sorted(cls._names.items()))

    @classmethod
    def load_directory(cls, directory: str) -> list:
        """Registra as texturas de arquivo (`<id>_<nome>.stl|png`) de uma pasta; retorna os ids."""
        from .tiles import load_directory
        return load_directory(directory)
