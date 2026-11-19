"""Configuração do projeto: dataclasses serializáveis em JSON.

Toda a "regra de negócio" ajustável fica aqui. Valores em mm, exceto onde indicado.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from . import parametros as P


# --------------------------------------------------------------------------- #
# Parte 1 — leitura da imagem (visão computacional)
# Os valores-padrão marcados com "parametros.py" vêm de img2stl/parametros.py.
# --------------------------------------------------------------------------- #
@dataclass
class VisionConfig:
    # --- escala ---
    # Largura final da peça em mm; a altura segue a proporção da imagem. [parametros.py]
    width_mm: float = P.LARGURA_PECA_MM
    # Lado maior (em pixels) da imagem usada nos cálculos. Imagens maiores são reduzidas.
    # Maior = contornos mais finos, porém mais lento.
    work_max_px: int = 1200

    # --- pré-processamento (limpa ruído/textura da foto antes de separar as cores) ---
    # Quantas vezes passa o filtro bilateral (suaviza cores sem borrar as bordas). 0 desliga.
    denoise_iterations: int = 2
    # Quanto dois tons podem diferir e ainda serem "misturados" pelo filtro. Maior = borra mais.
    denoise_sigma_color: float = 25.0
    # Tamanho (em pixels) da vizinhança do filtro. Maior = suaviza áreas maiores.
    denoise_sigma_space: float = 7.0

    # --- segmentação / regiões ---
    # Quantas cores o k-means cria de partida (em espaço Lab). Depois elas são fundidas
    # pelos critérios abaixo. Deve ser >= max_regions; maior = mais fiel, porém mais lento.
    n_color_clusters: int = 16
    # "Grau de semelhança": regiões vizinhas com diferença de cor (ΔE, Lab) menor que isso viram
    # uma só. ~2 = quase imperceptível, ~10 = tons da mesma família, 20+ = funde cores distintas.
    # Aumente se uma região de cor variável saiu dividida. [parametros.py]
    color_tolerance: float = P.TOLERANCIA_COR
    # Teto de regiões: se sobrar mais, funde as mais parecidas até caber. [parametros.py]
    max_regions: int = P.MAX_REGIOES
    # Regiões menores que isso (mm²) são absorvidas pela vizinha de cor mais próxima. [parametros.py]
    min_region_area_mm2: float = P.AREA_MIN_REGIAO_MM2
    # Cor RGB do "fundo" (ex.: (255, 255, 255)). A região dessa cor fica lisa, sem textura.
    # None = nenhuma região é tratada como fundo.
    ignore_color: Optional[Tuple[int, int, int]] = None
    # Quão próxima (ΔE) a região precisa ser de ignore_color para contar como fundo.
    ignore_tolerance: float = 15.0

    # --- fronteiras ---
    # Fronteiras mais curtas que isso (mm) não ganham cordão. [parametros.py]
    min_border_length_mm: float = P.COMPRIMENTO_MIN_FRONTEIRA_MM
    # Suavização das curvas (desvio-padrão, mm): remove a "escada" dos pixels. Maior = mais redondo,
    # mas cantos reais ficam arredondados. [parametros.py]
    smooth_sigma_mm: float = P.SUAVIZACAO_CURVAS_MM
    # Tolerância (mm) de simplificação Douglas-Peucker: remove pontos que desviam menos que isso da
    # reta. Maior = curvas com menos pontos (arquivo menor, perfil mais "facetado").
    simplify_tol_mm: float = 0.12
    # True = cordão também em volta de toda a peça (moldura). [parametros.py]
    outer_frame: bool = P.MOLDURA_EXTERNA

    # --- pontos (encontros de 3+ regiões) ---
    # Número mínimo de regiões que se encontram para marcar um ponto (3 = junção "em Y").
    min_regions_at_point: int = 3
    # Junções mais próximas que isso (mm) viram um ponto só. [parametros.py]
    point_merge_dist_mm: float = P.PONTO_DIST_FUSAO_MM
    # Se definido, mantém só os N pontos de maior valência (mais regiões). None = todos.
    max_points: Optional[int] = None

    # Semente do k-means: o mesmo valor reproduz exatamente o mesmo resultado.
    random_seed: int = 0


# --------------------------------------------------------------------------- #
# Parte 2 — relevo 2.5D (todas as medidas em mm)
# --------------------------------------------------------------------------- #
@dataclass
class ReliefConfig:
    # Espaçamento da grade de alturas. Menor = mais detalhe e STL maior (0,1 mm ≈ 200 MB para
    # 100x100 mm; use 0,2–0,3 para testar). [parametros.py]
    resolution_mm: float = P.RESOLUCAO_MM
    # Espessura da placa sob todo o relevo (deve ser > 0). [parametros.py]
    base_thickness_mm: float = P.ESPESSURA_BASE_MM

    # --- texturas das regiões ---
    # Altura (mm) dos relevos de textura acima da base. [parametros.py]
    texture_amplitude_mm: float = P.AMPLITUDE_TEXTURA_MM
    # Perfil da seção dos traços: "triangular" (ponta arredondada) ou "round" (arredondado).
    ridge_profile: str = "triangular"
    # Raio (mm) do arredondamento da ponta dos traços triangulares. 0 = ponta viva. [parametros.py]
    apex_round_mm: float = P.RAIO_APICE_MM
    # Texturas usadas em ciclo nas regiões sem atribuição manual (0 = lisa). [parametros.py]
    default_textures: List[int] = field(default_factory=lambda: list(P.TEXTURAS_PADRAO))
    # Atribuição manual: id da região -> id da textura, ou dict com distorções opcionais:
    # {"texture": 2, "amplitude_mm": 0.6,            # textura e altura própria da região
    #  "scale": 1.5,                                  # >1 amplia, <1 reduz o padrão
    #  "stretch": 2.0, "stretch_angle_deg": 30,       # alonga 2x na direção de 30°
    #  "shear": 0.0,                                  # inclina o padrão
    #  "rotation_deg": 0, "offset_mm": [0, 0],        # gira / desloca
    #  "warp_amplitude_mm": 0.0, "warp_wavelength_mm": 20}   # ondula o padrão (tortinho)
    region_textures: Dict[int, Any] = field(default_factory=dict)
    # Pasta com texturas de CAD/PNG nomeadas "<id>_<nome>.stl|png" (use id >= 100).
    texture_dir: Optional[str] = None
    # Avisa se o menor traço, depois da distorção, ficar menor que isso (bico de 0,4 mm não imprime). [parametros.py]
    min_feature_warn_mm: float = P.AVISO_TRACO_MIN_MM
    # Parâmetros próprios de cada textura: id -> argumentos da classe, ex.: {2: {"mini_ratio": 0.625}}.
    # Veja a tabela de parâmetros por textura no README.
    texture_params: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    # --- fronteiras (cordão semi-elíptico) ---
    # Largura do cordão (mm). [parametros.py]
    border_width_mm: float = P.FRONTEIRA_LARGURA_MM
    # Altura do cordão acima da base (mm). Ignorada se border_semicircle=True. [parametros.py]
    border_height_mm: float = P.FRONTEIRA_ALTURA_MM
    # True = semicírculo perfeito (altura = largura/2). [parametros.py]
    border_semicircle: bool = P.FRONTEIRA_SEMICIRCULAR
    # Faixa sem textura de cada lado, medida a partir da BORDA do cordão (não do centro).
    # Faixa livre total = largura do cordão + 2 x este valor. [parametros.py]
    border_exclusion_mm: float = P.FRONTEIRA_EXCLUSAO_MM
    # Rampa suave na saída da exclusão, para a textura não "nascer" num degrau. 0 = degrau. [parametros.py]
    exclusion_fade_mm: float = P.EXCLUSAO_TRANSICAO_MM

    # --- pontos ---
    # Altura do ponto acima da base (mm). [parametros.py]
    point_height_mm: float = P.PONTO_ALTURA_MM
    # Diâmetro (círculo) ou lado (quadrado/triângulo), em mm. [parametros.py]
    point_size_mm: float = P.PONTO_TAMANHO_MM
    # Largura (mm) da rampa inclinada em volta da forma, para não ter parede vertical. [parametros.py]
    point_flank_mm: float = P.PONTO_FLANCO_MM
    # Raio sem textura em volta do CENTRO do ponto (mm). Aumenta sozinho se a forma for maior. [parametros.py]
    point_exclusion_mm: float = P.PONTO_EXCLUSAO_MM
    # Forma por valência (nº de regiões no ponto): "circle", "square" ou "triangle". [parametros.py]
    point_shapes: Dict[int, str] = field(default_factory=lambda: dict(P.PONTO_FORMAS))
    # Forma das valências que não aparecem em point_shapes. [parametros.py]
    default_point_shape: str = P.PONTO_FORMA_PADRAO

    def validate(self) -> None:
        if self.base_thickness_mm <= 0:
            raise ValueError("base_thickness_mm deve ser > 0 (placa sob o relevo).")
        if self.resolution_mm <= 0:
            raise ValueError("resolution_mm deve ser > 0.")
        if self.border_width_mm <= 0 or self.point_size_mm <= 0:
            raise ValueError("border_width_mm e point_size_mm devem ser > 0.")



# --------------------------------------------------------------------------- #
# Textos de ajuda gravados no JSON (JSON não aceita comentários; chaves que começam com "_"
# são "notas" e são ignoradas ao ler).
# --------------------------------------------------------------------------- #
AJUDA: Dict[str, Dict[str, str]] = {
    "vision": {
        "width_mm": "Largura final da peça em mm; a altura segue a proporção da imagem.",
        "work_max_px": "Lado maior (pixels) da imagem usada nos cálculos. Maior = contornos mais finos, mais lento.",
        "denoise_iterations": "Passadas do filtro bilateral que suaviza cores sem borrar bordas. 0 desliga.",
        "denoise_sigma_color": "Quanto dois tons podem diferir e ainda serem misturados pelo filtro. Maior = borra mais.",
        "denoise_sigma_space": "Tamanho (pixels) da vizinhança do filtro. Maior = suaviza áreas maiores.",
        "n_color_clusters": "Cores iniciais do k-means, antes das fusões. Mantenha >= max_regions.",
        "color_tolerance": "Grau de semelhança (delta E, Lab): vizinhas mais parecidas que isso viram uma região. ~2 quase imperceptível, ~10 mesma família de tons, 20+ funde cores distintas.",
        "max_regions": "Teto de regiões; se houver mais, funde as mais parecidas até caber.",
        "min_region_area_mm2": "Regiões menores (mm2) são absorvidas pela vizinha de cor mais próxima.",
        "ignore_color": "Cor RGB de fundo, ex.: [255, 255, 255]. A região dessa cor fica lisa. null = nenhuma.",
        "ignore_tolerance": "Quão próxima (delta E) uma região precisa ser de ignore_color para contar como fundo.",
        "min_border_length_mm": "Fronteiras mais curtas que isso (mm) não ganham cordão.",
        "smooth_sigma_mm": "Suavização das curvas (mm): tira o serrilhado dos pixels. Maior = mais redondo, cantos amaciados.",
        "simplify_tol_mm": "Simplificação Douglas-Peucker (mm). Maior = menos pontos na curva, perfil mais facetado.",
        "outer_frame": "true = cordão também em volta de toda a peça.",
        "min_regions_at_point": "Nº mínimo de regiões que se encontram para marcar um ponto (3 = junção em Y).",
        "point_merge_dist_mm": "Junções mais próximas que isso (mm) viram um ponto só.",
        "max_points": "Mantém só os N pontos de maior valência. null = todos.",
        "random_seed": "Semente do k-means: o mesmo valor repete o mesmo resultado.",
    },
    "relief": {
        "resolution_mm": "Passo da grade (mm). Menor = mais detalhe e STL maior (100x100 mm a 0,1 = ~200 MB; teste com 0,2-0,3).",
        "base_thickness_mm": "Espessura (mm) da placa lisa sob todo o relevo. Deve ser > 0.",
        "texture_amplitude_mm": "Altura (mm) dos relevos de textura acima da base.",
        "ridge_profile": "Seção dos traços: 'triangular' (ponta arredondada) ou 'round'.",
        "apex_round_mm": "Raio (mm) do arredondamento da ponta triangular. 0 = ponta viva.",
        "default_textures": "Ids de textura usados em ciclo nas regiões sem escolha manual (0 lisa, 1 linhas, 2 X, 3 ondas, 4 escamas, 5 losangos).",
        "region_textures": "Escolha manual: {\"id_regiao\": id_textura} ou {\"id_regiao\": {\"texture\": 2, \"amplitude_mm\": 0.6, \"scale\": 1.5 (>1 amplia), \"stretch\": 2.0 e \"stretch_angle_deg\": 30 (alonga nessa direção), \"shear\": 0.0 (inclina), \"rotation_deg\": 0, \"offset_mm\": [0, 0], \"warp_amplitude_mm\": 0.0 e \"warp_wavelength_mm\": 20 (ondula)}}.",
        "texture_dir": "Pasta com texturas de CAD/PNG '<id>_<nome>.stl|png' (id >= 100). null = nenhuma.",
        "min_feature_warn_mm": "Avisa se o menor traço, após distorção, ficar menor que isso (mm).",
        "texture_params": "Parâmetros próprios por textura, ex.: {\"2\": {\"mini_ratio\": 0.625}}. Nomes por textura no README.",
        "border_width_mm": "Largura (mm) do cordão da fronteira.",
        "border_height_mm": "Altura (mm) do cordão (semi-elipse). Ignorada se border_semicircle = true.",
        "border_semicircle": "true = semicírculo perfeito (altura = largura/2).",
        "border_exclusion_mm": "Faixa sem textura de cada lado, contada a partir da BORDA do cordão. Faixa livre total = largura + 2 x valor.",
        "exclusion_fade_mm": "Rampa suave (mm) na saída da exclusão. 0 = degrau.",
        "point_height_mm": "Altura (mm) do ponto acima da base.",
        "point_size_mm": "Diâmetro (círculo) ou lado (quadrado/triângulo), em mm.",
        "point_flank_mm": "Largura (mm) da rampa inclinada em volta da forma do ponto.",
        "point_exclusion_mm": "Raio (mm) sem textura a partir do CENTRO do ponto (cresce sozinho se a forma for maior).",
        "point_shapes": "Forma por nº de regiões no ponto: {\"3\": \"triangle\", \"4\": \"square\"} (também 'circle').",
        "default_point_shape": "Forma das valências não listadas em point_shapes.",
    },
}

@dataclass
class PipelineConfig:
    vision: VisionConfig = field(default_factory=VisionConfig)
    relief: ReliefConfig = field(default_factory=ReliefConfig)

    # ---- JSON ---- #
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, path: str, comments: bool = True) -> None:
        """Grava o JSON. Com comments=True, cada parâmetro vem precedido de uma nota "_nome"."""
        data = self.to_dict()
        if comments:
            data = {sec: _with_notes(vals, AJUDA.get(sec, {})) for sec, vals in data.items()}
            data = {"_leia_me": "Chaves que começam com '_' são notas e são ignoradas. "
                                "Edite só os valores. Medidas em mm.", **data}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        return cls(
            vision=_dataclass_from_dict(VisionConfig, data.get("vision", {})),
            relief=_dataclass_from_dict(ReliefConfig, data.get("relief", {})),
        )

    @classmethod
    def from_json(cls, path: str) -> "PipelineConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


_INT_KEY_FIELDS = {"region_textures", "texture_params", "point_shapes"}


def _with_notes(values: Dict[str, Any], notes: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in values.items():
        if k in notes:
            out["_" + k] = notes[k]
        out[k] = v
    return out


def _dataclass_from_dict(klass, data: Dict[str, Any]):
    """Cria o dataclass ignorando notas ("_...") e rejeitando chaves desconhecidas;
    converte chaves '3' -> 3 onde faz sentido."""
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    valid = {f.name for f in fields(klass)}
    unknown = set(data) - valid
    if unknown:
        raise ValueError(f"Parâmetros desconhecidos em {klass.__name__}: {sorted(unknown)}")
    kwargs = {}
    for name, value in data.items():
        if name in _INT_KEY_FIELDS and isinstance(value, dict):
            value = {int(k): v for k, v in value.items()}
        if name == "ignore_color" and value is not None:
            value = tuple(int(c) for c in value)
        kwargs[name] = value
    return klass(**kwargs)
