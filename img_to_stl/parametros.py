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
# Traços e regiões mais finos que isso (mm) são apagados e preenchidos pela vizinhança: some o
# contorno preto de mapas, o serrilhado entre cores e texto fino; a fronteira passa pelo meio do traço.
# 0 = desligado. Aumente se ainda sobrarem "regiões" que são só linhas.
ESPESSURA_MIN_REGIAO_MM = 1.0
# Fronteira mais curta que isso (mm) é encolhida: as duas junções viram uma só (a rede de cordões
# continua sem fresta). Não apaga fronteiras, para não deixar buracos.
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
# Texturas que o programa pode usar nas regiões sem escolha manual (0 lisa, 1 linhas, 2 X, 3 ondas,
# 4 escamas, 5 losangos). Regiões vizinhas NUNCA repetem a textura e, enquanto houver textura livre,
# nenhuma se repete na imagem. Só se repetem se houver mais regiões do que texturas (aí, nunca entre
# vizinhas, quando possível). Escolhas manuais (--textures / region_textures) podem repetir.
TEXTURAS_PADRAO = [1, 2, 3, 4, 5]
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

# ======================= PONTOS DE INTERESSE ======================= #
# Marcas pontuais no mapa (capitais etc.). Ainda NÃO são detectadas na imagem: estes valores só
# definem como cada ponto será modelado quando ele existir.
# Altura do ponto acima da base.
PONTO_ALTURA_MM = 1.4
# Diâmetro (círculo) ou lado (quadrado/triângulo).
PONTO_TAMANHO_MM = 1.2
# Largura da rampa inclinada em volta da forma (evita parede vertical).
PONTO_FLANCO_MM = 0.4
# Raio sem textura em volta do CENTRO do ponto. Aumenta sozinho se a forma for maior que isso.
PONTO_EXCLUSAO_MM = 1.0
# Forma padrão: "circle", "square" ou "triangle" (cada ponto pode ter a sua).
PONTO_FORMA = "circle"

# ---- Pontos de INTERSECÇÃO (opcional, desligado) ---- #
# Marca com um ponto cada encontro de 3 ou mais regiões. Desligado por padrão; pode servir no futuro.
PONTOS_DE_INTERSECCAO = False
# Nº mínimo de regiões que se encontram para marcar um ponto (3 = junção em "Y").
INTERSECCAO_MIN_REGIOES = 3
# Junções mais próximas que isso (mm) viram um ponto só.
INTERSECCAO_DIST_FUSAO_MM = 1.5
# Se definido, mantém só os N pontos de intersecção de maior valência (None = todos).
INTERSECCAO_MAX_PONTOS = None
# Forma pelo nº de regiões que se encontram (usada nos pontos de intersecção).
INTERSECCAO_FORMAS = {3: "triangle", 4: "square"}

# ======================= SAÍDA ======================= #
# Pasta-base das saídas. Cada imagem ganha uma subpasta própria: saida/<nome_da_imagem>/
PASTA_SAIDA = "saida"
# True = além do STL, grava a subpasta negativos/ (regiões, fronteiras e pontos em preto e branco).
GERAR_NEGATIVOS = True
# Resolução dos negativos (pixels por mm). 10 = 0,1 mm por pixel (limitado a ~4000 px no lado maior).
NEGATIVOS_PX_POR_MM = 10.0
