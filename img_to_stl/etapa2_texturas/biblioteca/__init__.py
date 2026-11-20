"""Biblioteca de texturas: procedurais, distorção e arquivos de CAD (STL/PNG)."""
from . import padroes, padroes_extra  # noqa: F401  (registra as texturas internas)
from .base import RidgeProfile, Texture
from .atualizar import update_textures
from .registro import TextureLibrary
from .tiles import TileTexture, export_texture_templates, load_directory
from .transformacoes import TextureTransform, TransformedTexture

__all__ = ["RidgeProfile", "Texture", "TextureLibrary", "TileTexture", "export_texture_templates",
           "load_directory", "update_textures", "TextureTransform", "TransformedTexture"]
