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
    def params_of(cls, texture_id: int) -> List[str]:
        """Parâmetros próprios da textura ("nome=padrão"), para `texture_params`."""
        import inspect
        try:
            sig = inspect.signature(cls._registry[texture_id])
        except (TypeError, ValueError, KeyError):
            return []
        return [f"{n}={p.default:g}" if isinstance(p.default, (int, float)) and not isinstance(p.default, bool)
                else f"{n}={p.default}"
                for n, p in sig.parameters.items()
                if n != "profile" and p.default is not inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]

    @classmethod
    def catalog_text(cls) -> str:
        """Texto do arquivo `texturas_disponiveis.txt`: lista, parâmetros e como usar."""
        L = ["TEXTURAS DISPONÍVEIS — img_to_stl",
             "(gerado por: python -m img_to_stl --list-textures)", "",
             "Como usar: no texturas.json, \"REGIAO\": \"nome/id(distorções)\" — pelo nome ou pelo número.",
             "  Ex.: \"ondas/3\"   \"3\"   \"ondas/3(escala=1.5, alongar=2, angulo=30)\"   \"lisa/0\"",
             "Distorções: escala, alongar, angulo, cisalhar, rotacao, desloc_x, desloc_y, onda_amp, onda_comp, amp (altura, mm).",
             "Parâmetros próprios de cada textura vão em texture_params (parametros.json da etapa 2), ex.: {\"6\": {\"pitch\": 5.0}}.",
             "Todas as internas repetem num tile de 10 mm: pitch/célula devem dividir 10.", "",
             " id  nome              descrição"]
        for tid, name, desc in cls.catalog():
            L.append(f"{tid:>3}  {name:<16}  {desc}")
            params = cls.params_of(tid)
            if params:
                L.append(f"{'':>21}parâmetros: " + ", ".join(params))
        L += ["", "0 é a textura lisa (sem relevo). Ids >= 100: suas texturas de CAD/PNG (pasta texture_dir, arquivos <id>_<nome>.stl|png);",
              "elas aparecem aqui quando a lista é gerada com --texture-dir PASTA."]
        return "\n".join(L) + "\n"

    @classmethod
    def write_catalog(cls, path: str = "texturas_disponiveis.txt") -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(cls.catalog_text())
        return path

    @classmethod
    def describe(cls) -> Dict[int, str]:
        return dict(sorted(cls._names.items()))

    @classmethod
    def load_directory(cls, directory: str) -> list:
        """Registra as texturas de arquivo (`<id>_<nome>.stl|png`) de uma pasta; retorna os ids."""
        from .tiles import load_directory
        return load_directory(directory)
