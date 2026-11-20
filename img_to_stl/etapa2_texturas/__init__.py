"""ETAPA 2 — aplicação de textura e geração do STL (relevo 2.5D)."""
from .biblioteca import TextureLibrary, TextureTransform, TransformedTexture
from .config import Etapa2Config
from .pipeline import Etapa2

__all__ = ["Etapa2", "Etapa2Config", "TextureLibrary", "TextureTransform", "TransformedTexture"]
