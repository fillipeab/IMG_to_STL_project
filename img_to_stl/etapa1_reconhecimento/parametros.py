"""ETAPA 1 — RECONHECIMENTO DA IMAGEM: parâmetros-padrão (edite aqui).

Estes valores são usados quando você não escolhe outros. Para uma imagem específica, use
`etapa1_reconhecimento/parametros.json` (gravado na pasta de saída) ou o CLI interativo.
Medidas em mm. Parâmetros avançados (filtro, k-means) ficam em etapa1_reconhecimento/config.py.
"""

# ======================= PEÇA ======================= #
# Largura final da peça. A altura segue a proporção da imagem.
LARGURA_PECA_MM = 100.0

# ======================= REGIÕES ======================= #
# Máximo de regiões. Se a imagem gerar mais, as mais parecidas são fundidas até caber.
MAX_REGIOES = 12
# "Grau de semelhança" entre cores (ΔE em Lab). Vizinhas mais parecidas que isso viram uma região.
# ~2 quase imperceptível · ~10 mesma família de tons · 20+ funde cores bem distintas.
TOLERANCIA_COR = 10.0
# Regiões menores que isso (mm²) são absorvidas pela vizinha de cor mais próxima (limpa "sujeira").
AREA_MIN_REGIAO_MM2 = 15.0
# Traços e regiões mais finos que isso (mm) são apagados e preenchidos pela vizinhança: some o
# contorno preto de mapas, o serrilhado entre cores e texto fino. 0 = desligado.
ESPESSURA_MIN_REGIAO_MM = 1.0

# ======================= FAMÍLIAS ("regiões irmãs") ======================= #
# Regiões de cor parecida, vizinhas ou não, entram na mesma FAMÍLIA (ex.: todos os "verdes").
# Duas regiões são irmãs se a diferença de cor (ΔE, Lab) for menor que isso. 0 = cada região
# é uma família. Não altera as regiões: só as agrupa no resultado (resultado.json).
FAMILIA_TOLERANCIA_COR = 25.0

# ======================= FRONTEIRAS ======================= #
# Fronteira mais curta que isso (mm) é encolhida: as duas junções viram uma só (a rede de cordões
# continua sem fresta). Não apaga fronteiras, para não deixar buracos.
COMPRIMENTO_MIN_FRONTEIRA_MM = 4.0
# Suavização das curvas (mm): tira o serrilhado dos pixels. Maior = mais redondo, cantos amaciados.
SUAVIZACAO_CURVAS_MM = 0.5
# True = há fronteira também em volta de toda a peça (moldura externa).
MOLDURA_EXTERNA = True

# ======================= PONTOS ======================= #
# Pontos TRÍPLICES (e múltiplos): onde 3 ou mais regiões se encontram. Sempre são calculados e
# listados no resultado; se viram relevo ou não é decidido na etapa 2.
TRIPLICE_MIN_REGIOES = 3
# Junções mais próximas que isso (mm) viram um ponto só.
TRIPLICE_DIST_FUSAO_MM = 1.5

# Pontos de INTERESSE (capitais etc.), por classe. Duas formas de informar (podem ser usadas juntas):
#  1) MARCADORES: bolinhas coloridas desenhadas na imagem. Cada item:
#       {"classe": "capital", "cor": [255, 0, 0], "tolerancia": 30}
#     O programa acha as bolinhas dessa cor, grava o centro de cada uma e as apaga da imagem
#     (para não virarem regiões).
#  2) ARQUIVO de pontos (.json ou .csv): colunas/chaves  classe, nome, x_px, y_px  (pixels da
#     imagem original, origem no canto superior esquerdo)  ou  x_mm, y_mm (mm da peça, origem no
#     canto inferior esquerdo).
MARCADORES_PONTOS = []
ARQUIVO_PONTOS = None
# Tamanho máximo (mm²) de uma bolinha-marcador; manchas maiores são ignoradas (não são marcadores).
MARCADOR_AREA_MAX_MM2 = 80.0

# ======================= SAÍDA ======================= #
# REPOSITÓRIO: uma pasta por imagem/objeto (original, etapa 1, etapa 2): repositorio/<nome_da_imagem>/
PASTA_REPOSITORIO = "repositorio"
# SAÍDAS: só os STL prontos para imprimir: saidas/<nome_da_imagem>.stl
PASTA_STL = "saidas"
# Resolução das imagens de negativos (pixels por mm; limitada a ~4000 px no lado maior).
NEGATIVOS_PX_POR_MM = 10.0
# Espessura da linha nas imagens de fronteiras (mm).
NEGATIVOS_LINHA_MM = 0.5
# Raio da marca de cada ponto nas imagens de pontos (mm).
NEGATIVOS_PONTO_RAIO_MM = 1.2
