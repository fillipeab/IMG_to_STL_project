"""Configuração da etapa 2 (dataclass serializável em JSON)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..comum.config_io import dataclass_from_dict, read_json, to_json_file
from . import parametros as P


@dataclass
class Etapa2Config:
    # --- peça / base ---
    resolution_mm: float = P.RESOLUCAO_MM
    base_thickness_mm: float = P.ESPESSURA_BASE_MM
    base_mode: str = P.BASE_MODO                       # "retangular" | "silhueta"
    base_regions: Optional[List[int]] = P.BASE_REGIOES
    frame_cord: bool = P.CORDAO_MOLDURA

    # --- texturas ---
    texture_amplitude_mm: float = P.AMPLITUDE_TEXTURA_MM
    ridge_profile: str = "triangular"
    apex_round_mm: float = P.RAIO_APICE_MM
    default_textures: List[int] = field(default_factory=lambda: list(P.TEXTURAS_PADRAO))
    smooth_region: str = P.REGIAO_LISA                 # "externa" | "maior" | "nenhuma" | nome/número da região
    texture_dir: Optional[str] = None
    min_feature_warn_mm: float = P.AVISO_TRACO_MIN_MM
    texture_params: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    # --- fronteiras ---
    border_width_mm: float = P.FRONTEIRA_LARGURA_MM
    border_height_mm: float = P.FRONTEIRA_ALTURA_MM
    border_semicircle: bool = P.FRONTEIRA_SEMICIRCULAR
    border_exclusion_mm: float = P.FRONTEIRA_EXCLUSAO_MM
    exclusion_fade_mm: float = P.EXCLUSAO_TRANSICAO_MM

    # --- suavização da zona de exclusão ---
    exclusion_texture_scale: float = P.EXCLUSAO_ESCALA_TEXTURA
    exclusion_texture_height_factor: float = P.EXCLUSAO_ALTURA_FATOR

    # --- pontos ---
    point_height_mm: float = P.PONTO_ALTURA_MM
    point_size_mm: float = P.PONTO_TAMANHO_MM
    point_flank_mm: float = P.PONTO_FLANCO_MM
    point_exclusion_mm: float = P.PONTO_EXCLUSAO_MM
    point_shape: str = P.PONTO_FORMA
    point_shape_by_class: Dict[str, str] = field(default_factory=lambda: dict(P.PONTO_FORMA_POR_CLASSE))
    model_triple_points: bool = P.MODELAR_TRIPLICES
    model_multiple_points: bool = P.MODELAR_MULTIPLOS

    def validate(self) -> None:
        if self.base_thickness_mm <= 0:
            raise ValueError("base_thickness_mm deve ser > 0 (placa sob o relevo).")
        if self.resolution_mm <= 0:
            raise ValueError("resolution_mm deve ser > 0.")
        if self.border_width_mm <= 0 or self.point_size_mm <= 0:
            raise ValueError("border_width_mm e point_size_mm devem ser > 0.")
        if self.exclusion_texture_scale < 0 or self.exclusion_texture_height_factor < 0:
            raise ValueError("exclusion_texture_scale e exclusion_texture_height_factor devem ser >= 0.")
        if not str(self.smooth_region).strip():
            raise ValueError("smooth_region deve ser 'externa', 'maior', 'nenhuma' ou o nome/número de uma região.")
        if self.base_mode not in ("retangular", "silhueta"):
            raise ValueError("base_mode deve ser 'retangular' ou 'silhueta'.")

    # ---- JSON ---- #
    def to_json(self, path: str, comments: bool = False) -> None:
        to_json_file(self, path, AJUDA if comments else None)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Etapa2Config":
        return dataclass_from_dict(cls, data, int_key_fields=("texture_params",))

    @classmethod
    def from_json(cls, path: str) -> "Etapa2Config":
        return cls.from_dict(read_json(path))


AJUDA: Dict[str, str] = {
    "resolution_mm": "Passo da grade (mm). Menor = mais detalhe e STL maior (100x100 mm a 0,1 = ~200 MB; teste com 0,2-0,3).",
    "base_thickness_mm": "Espessura (mm) da placa lisa sob todo o relevo. Deve ser > 0.",
    "base_mode": "'retangular' = placa inteira; 'silhueta' = a base segue o contorno das regiões escolhidas (o resto fica de fora).",
    "base_regions": "Modo silhueta: ids das regiões que formam a base. null = todas as que não são fundo.",
    "frame_cord": "true = cordão também em volta de toda a peça (moldura).",
    "texture_amplitude_mm": "Altura (mm) dos relevos de textura acima da base.",
    "ridge_profile": "Seção dos traços: 'triangular' (ponta arredondada) ou 'round'.",
    "apex_round_mm": "Raio (mm) do arredondamento da ponta triangular. 0 = ponta viva.",
    "default_textures": "Texturas usadas na SUGESTÃO inicial (texturas.json). Lista completa: python -m img_to_stl --list-textures. A lisa (0) não entra aqui: veja smooth_region.",
    "smooth_region": "Região que fica LISA na sugestão: 'externa' = a maior que toca a borda; 'maior' = a maior de todas; 'nenhuma'; ou nome/número de uma região. Não age se já houver fundo (ignore_color) ou lisa escolhida à mão.",
    "texture_dir": "Pasta com texturas de CAD/PNG '<id>_<nome>.stl|png' (id >= 100). null = nenhuma.",
    "min_feature_warn_mm": "Avisa se o menor traço, após distorção, ficar menor que isso (mm).",
    "texture_params": "Parâmetros próprios por textura, ex.: {\"2\": {\"mini_ratio\": 0.625}}. Nomes por textura no README.",
    "border_width_mm": "Largura (mm) do cordão da fronteira.",
    "border_height_mm": "Altura (mm) do cordão (semi-elipse). Ignorada se border_semicircle = true.",
    "border_semicircle": "true = semicírculo perfeito (altura = largura/2).",
    "border_exclusion_mm": "Faixa sem textura de cada lado, contada a partir da BORDA do cordão.",
    "exclusion_fade_mm": "Rampa suave (mm) na saída da exclusão. 0 = degrau.",
    "exclusion_texture_scale": "Escala da textura reduzida na zona de exclusão (0,5 = metade). 0 = faixa lisa.",
    "exclusion_texture_height_factor": "Altura da textura reduzida relativa à normal (0,6 = 60%).",
    "point_height_mm": "Altura (mm) do ponto acima da base.",
    "point_size_mm": "Diâmetro (círculo) ou lado (quadrado/triângulo), em mm.",
    "point_flank_mm": "Largura (mm) da rampa inclinada em volta da forma do ponto.",
    "point_exclusion_mm": "Raio (mm) sem textura a partir do CENTRO do ponto.",
    "point_shape": "Forma padrão dos pontos: circle, square ou triangle.",
    "point_shape_by_class": "Forma por classe de ponto, ex.: {\"capital\": \"circle\", \"triplice\": \"triangle\"}.",
    "model_triple_points": "true = pontos tríplices viram relevo (desligado por padrão).",
    "model_multiple_points": "true = pontos de 4+ regiões viram relevo (desligado por padrão).",
}
