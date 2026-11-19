"""PARÂMETROS PRINCIPAIS — edite aqui. Tudo em mm, salvo indicação.

Estes são os valores-padrão do programa. Um --config JSON ou argumentos de linha de comando
ainda sobrescrevem cada um deles numa execução específica.
Parâmetros avançados (suavização do filtro, k-means, perfil dos traços...) ficam em config.py.
"""

# ======================= PEÇA / RESOLUÇÃO ======================= #
# Largura final da peça. A altura segue a proporção da imagem.
LARGURA_PECA_MM = 100.0
# Passo da grade de alturas. Menor = mais detalhe e arquivo maior.
# 0,1 mm em 100x100 mm ≈ 200 MB; para testes use 0,2–0,3.
RESOLUCAO_MM = 0.1
# Espessura da placa lisa sob todo o relevo (as texturas e cordões ficam acima dela).
ESPESSURA_BASE_MM = 1.0

# ======================= REGIÕES (visão) ======================= #
# Máximo de regiões. Se a imagem gerar mais, as mais parecidas são fundidas até caber.
MAX_REGIOES = 12
# "Grau de semelhança" entre cores (ΔE em Lab). Vizinhas mais parecidas que isso viram uma região.
# ~2 quase imperceptível · ~10 mesma família de tons · 20+ funde cores bem distintas.
TOLERANCIA_COR = 10.0
# Regiões menores que isso (mm²) são absorvidas pela vizinha de cor mais próxima (limpa "sujeira").
AREA_MIN_REGIAO_MM2 = 15.0
# Fronteiras mais curtas que isso (mm) não ganham cordão.
COMPRIMENTO_MIN_FRONTEIRA_MM = 4.0
# Suavização das curvas (mm): tira o serrilhado dos pixels. Maior = mais redondo, cantos amaciados.
SUAVIZACAO_CURVAS_MM = 0.5
# True = cordão também em volta de toda a peça (moldura externa).
MOLDURA_EXTERNA = True

# ======================= TEXTURAS ======================= #
# Altura dos relevos das texturas acima da base.
AMPLITUDE_TEXTURA_MM = 0.6
# Raio de arredondamento da ponta dos traços triangulares. 0 = ponta viva.
RAIO_APICE_MM = 0.1
# Texturas usadas em ciclo nas regiões sem escolha manual (0 lisa, 1 linhas, 2 X, 3 ondas,
# 4 escamas, 5 losangos). Ex.: [1, 3] alterna só linhas e ondas.
TEXTURAS_PADRAO = [1, 2, 3, 4]
# Aviso se o menor traço (após distorção) ficar menor que isso. Bico de 0,4 mm não imprime abaixo.
AVISO_TRACO_MIN_MM = 0.4

# ======================= FRONTEIRAS (cordão) ======================= #
# Largura do cordão na base.
FRONTEIRA_LARGURA_MM = 1.0
# Altura do cordão acima da base (seção semi-elíptica). Ignorada se FRONTEIRA_SEMICIRCULAR = True.
FRONTEIRA_ALTURA_MM = 1.2
# True = semicírculo perfeito (altura = largura / 2).
FRONTEIRA_SEMICIRCULAR = False
# Faixa sem textura de cada lado, medida a partir da BORDA do cordão (não do centro).
# Faixa livre total = FRONTEIRA_LARGURA_MM + 2 x este valor. Sugestão: 0,5–0,7.
FRONTEIRA_EXCLUSAO_MM = 1.0
# Rampa suave na saída da exclusão, para a textura não nascer num degrau. 0 = degrau.
EXCLUSAO_TRANSICAO_MM = 0.3

# ======================= SUAVIZAÇÃO DA ZONA DE EXCLUSÃO ======================= #
# Em vez de deixar a faixa de exclusão (em volta de cordões e pontos) lisa, coloca ali uma versão
# REDUZIDA da textura da região, para a transição ficar mais suave.
# Escala do padrão reduzido: 0,5 = metade do tamanho (traços mais finos e mais juntos).
# 0 = desligado (zona de exclusão lisa). Cuidado: traços ficam mais finos; abaixo de ~0,5 o
# código avisa se o traço ficar menor que AVISO_TRACO_MIN_MM.
EXCLUSAO_ESCALA_TEXTURA = 0.5
# Altura da textura reduzida em relação à normal (0,6 = 60% de TEXTURA_AMPLITUDE). Traços mais
# finos ficam mais frágeis/íngremes se mantiverem a altura cheia.
EXCLUSAO_ALTURA_FATOR = 0.6

# ======================= PONTOS (junções) ======================= #
# Altura do ponto acima da base.
PONTO_ALTURA_MM = 1.4
# Diâmetro (círculo) ou lado (quadrado/triângulo).
PONTO_TAMANHO_MM = 1.2
# Largura da rampa inclinada em volta da forma (evita parede vertical).
PONTO_FLANCO_MM = 0.4
# Raio sem textura em volta do CENTRO do ponto. Aumenta sozinho se a forma for maior que isso.
PONTO_EXCLUSAO_MM = 1.0
# Forma conforme o nº de regiões que se encontram no ponto: "circle", "square" ou "triangle".
PONTO_FORMAS = {3: "triangle", 4: "square"}
# Forma para as demais valências (5, 6...).
PONTO_FORMA_PADRAO = "circle"
# Junções mais próximas que isso viram um único ponto.
PONTO_DIST_FUSAO_MM = 1.5

# ======================= SAÍDA ======================= #
# Pasta-base das saídas. Cada imagem ganha uma subpasta própria: saida/<nome_da_imagem>/
PASTA_SAIDA = "saida"
# True = além do STL, grava a subpasta negativos/ (regiões, fronteiras e pontos em preto e branco).
GERAR_NEGATIVOS = True
# Resolução dos negativos (pixels por mm). 10 = 0,1 mm por pixel (limitado a ~4000 px no lado maior).
NEGATIVOS_PX_POR_MM = 10.0
