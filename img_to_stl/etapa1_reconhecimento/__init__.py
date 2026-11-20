"""ETAPA 1 — reconhecimento da imagem: regiões, famílias, fronteiras e pontos."""
from .config import Etapa1Config
from .leitor import ImageReader
from .modelos import Border, Family, InterestPoint, PlanarMap, Region
from .pipeline import Etapa1

__all__ = ["Etapa1", "Etapa1Config", "ImageReader", "PlanarMap", "Region", "Family", "Border", "InterestPoint"]
