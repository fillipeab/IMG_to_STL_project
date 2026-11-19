"""img2stl — imagem -> regiões/fronteiras/pontos -> relevo 2.5D texturizado -> STL."""
from .config import PipelineConfig, ReliefConfig, VisionConfig
from .pipeline import ImageToReliefPipeline
from .relief import HeightField, ReliefBuilder
from .stl_export import HeightfieldMesher, Mesh
from .textures import Texture, TextureLibrary
from .tiles import TileTexture, export_texture_templates
from .transforms import TextureTransform, TransformedTexture
from .vision import ImageReader, PlanarMap

__all__ = [
    "TextureTransform", "TransformedTexture", "TileTexture", "export_texture_templates",
    "PipelineConfig", "VisionConfig", "ReliefConfig", "ImageToReliefPipeline",
    "ImageReader", "PlanarMap", "ReliefBuilder", "HeightField", "HeightfieldMesher", "Mesh",
    "Texture", "TextureLibrary",
]
