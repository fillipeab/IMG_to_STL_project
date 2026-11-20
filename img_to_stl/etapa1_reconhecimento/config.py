"""Configuração da etapa 1 (dataclass serializável em JSON)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..comum.config_io import dataclass_from_dict, read_json, to_json_file
from . import parametros as P


@dataclass
class Etapa1Config:
    # --- escala ---
    # Largura final da peça em mm; a altura segue a proporção da imagem. [parametros.py]
    width_mm: float = P.LARGURA_PECA_MM
    # Lado maior (px) da imagem usada nos cálculos. Imagens maiores são reduzidas.
    work_max_px: int = 1200

    # --- pré-processamento (filtro bilateral: suaviza cores sem borrar bordas) ---
    denoise_iterations: int = 2
    denoise_sigma_color: float = 25.0
    denoise_sigma_space: float = 7.0

    # --- regiões ---
    # Cores iniciais do k-means (Lab); depois são fundidas. Deve ser >= max_regions.
    n_color_clusters: int = 16
    color_tolerance: float = P.TOLERANCIA_COR
    max_regions: int = P.MAX_REGIOES
    min_region_area_mm2: float = P.AREA_MIN_REGIAO_MM2
    min_region_thickness_mm: float = P.ESPESSURA_MIN_REGIAO_MM
    # Cor RGB do "fundo" (ex.: (255, 255, 255)): a região dessa cor fica lisa na etapa 2 e,
    # com base "silhueta", fica fora da peça. None = nenhuma.
    ignore_color: Optional[Tuple[int, int, int]] = None
    ignore_tolerance: float = 15.0

    # Fusões pedidas pelo usuário, aplicadas em ordem sobre o resultado já existente. Cada item é uma
    # lista de números de região ([3, 7]) ou um critério: "familia", "menores=50", "cor=verde,lilas".
    merge_regions: List[Any] = field(default_factory=list)

    # --- famílias ("regiões irmãs") ---
    family_tolerance: float = P.FAMILIA_TOLERANCIA_COR

    # --- fronteiras ---
    min_border_length_mm: float = P.COMPRIMENTO_MIN_FRONTEIRA_MM
    smooth_sigma_mm: float = P.SUAVIZACAO_CURVAS_MM
    simplify_tol_mm: float = 0.12
    outer_frame: bool = P.MOLDURA_EXTERNA

    # --- pontos tríplices ---
    triple_min_regions: int = P.TRIPLICE_MIN_REGIOES
    triple_merge_dist_mm: float = P.TRIPLICE_DIST_FUSAO_MM

    # --- pontos de interesse ---
    # Lista de {"classe": ..., "cor": [r,g,b], "tolerancia": ΔE}. Ver parametros.py.
    point_markers: List[Dict[str, Any]] = field(default_factory=lambda: list(P.MARCADORES_PONTOS))
    points_file: Optional[str] = P.ARQUIVO_PONTOS
    marker_max_area_mm2: float = P.MARCADOR_AREA_MAX_MM2

    # --- negativos ---
    negatives_px_per_mm: float = P.NEGATIVOS_PX_POR_MM
    negatives_line_mm: float = P.NEGATIVOS_LINHA_MM
    negatives_point_radius_mm: float = P.NEGATIVOS_PONTO_RAIO_MM

    random_seed: int = 0

    # ---- JSON ---- #
    def to_json(self, path: str, comments: bool = False) -> None:
        to_json_file(self, path, AJUDA if comments else None)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Etapa1Config":
        return dataclass_from_dict(cls, data, tuple_fields=("ignore_color",))

    @classmethod
    def from_json(cls, path: str) -> "Etapa1Config":
        return cls.from_dict(read_json(path))


AJUDA: Dict[str, str] = {
    "width_mm": "Largura final da peça em mm; a altura segue a proporção da imagem.",
    "work_max_px": "Lado maior (pixels) da imagem usada nos cálculos. Maior = contornos mais finos, mais lento.",
    "denoise_iterations": "Passadas do filtro bilateral que suaviza cores sem borrar bordas. 0 desliga.",
    "denoise_sigma_color": "Quanto dois tons podem diferir e ainda serem misturados pelo filtro.",
    "denoise_sigma_space": "Tamanho (pixels) da vizinhança do filtro.",
    "n_color_clusters": "Cores iniciais do k-means, antes das fusões. Mantenha >= max_regions.",
    "color_tolerance": "Grau de semelhança (delta E, Lab): vizinhas mais parecidas que isso viram uma região.",
    "max_regions": "Teto de regiões; se houver mais, funde as mais parecidas até caber.",
    "min_region_area_mm2": "Regiões menores (mm2) são absorvidas pela vizinha de cor mais próxima.",
    "min_region_thickness_mm": "Traços/regiões mais finos que isso (mm) são apagados e preenchidos pela vizinhança. 0 = desligado.",
    "merge_regions": "Fusões pedidas por você, em ordem. Cada item: lista de números de região ([3, 7]) ou critério: \"familia\" (irmãs que se tocam), \"menores=50\" (regiões < 50 mm² vão para a vizinha mais parecida), \"cor=verde,lilas\" (regiões de mesma cor viram uma). Números valem para o resultado do momento: se mudar outros parâmetros, confira.",
    "ignore_color": "Cor RGB de fundo, ex.: [255, 255, 255]. null = nenhuma.",
    "ignore_tolerance": "Quão próxima (delta E) uma região precisa ser de ignore_color para contar como fundo.",
    "family_tolerance": "Regiões com delta E menor que isso (vizinhas ou não) são 'irmãs' (mesma família). 0 = sem famílias.",
    "min_border_length_mm": "Fronteira mais curta que isso (mm) é encolhida: as duas junções viram uma só.",
    "smooth_sigma_mm": "Suavização das curvas (mm). Maior = mais redondo.",
    "simplify_tol_mm": "Simplificação Douglas-Peucker (mm). Maior = menos pontos na curva.",
    "outer_frame": "true = fronteira também em volta de toda a peça.",
    "triple_min_regions": "Nº mínimo de regiões que se encontram num ponto tríplice (3 = junção em Y).",
    "triple_merge_dist_mm": "Junções mais próximas que isso (mm) viram um ponto só.",
    "point_markers": "Marcadores de pontos de interesse na imagem: [{\"classe\": \"capital\", \"cor\": [255,0,0], \"tolerancia\": 30}].",
    "points_file": "Arquivo .json/.csv com pontos de interesse (classe, nome, x_px, y_px ou x_mm, y_mm). null = nenhum.",
    "marker_max_area_mm2": "Manchas de cor maiores que isso (mm2) não são tratadas como marcador.",
    "negatives_px_per_mm": "Resolução dos negativos (pixels por mm).",
    "negatives_line_mm": "Espessura (mm) da linha nas imagens de fronteiras.",
    "negatives_point_radius_mm": "Raio (mm) da marca de cada ponto nas imagens de pontos.",
    "random_seed": "Semente do k-means: o mesmo valor repete o mesmo resultado.",
}
