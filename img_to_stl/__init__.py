"""img_to_stl — imagem -> regiões/fronteiras/pontos (etapa 1) -> relevo texturizado em STL (etapa 2)."""
__version__ = "0.3.0"

from .config import PipelineConfig
from .etapa1_reconhecimento import Etapa1, Etapa1Config, ImageReader, PlanarMap
from .etapa2_texturas import Etapa2, Etapa2Config, TextureLibrary, TextureTransform, TransformedTexture
from .pipeline import ImageToStl

__all__ = ["ImageToStl", "PipelineConfig", "Etapa1", "Etapa1Config", "Etapa2", "Etapa2Config", "ImageReader",
           "PlanarMap", "TextureLibrary", "TextureTransform", "TransformedTexture"]
