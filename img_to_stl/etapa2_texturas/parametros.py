"""ETAPA 2 — APLICAÇÃO DE TEXTURA E GERAÇÃO DO STL: parâmetros-padrão (edite aqui).

Estes valores são usados quando você não escolhe outros. Para uma imagem específica, use
`etapa2_texturas/parametros.json` e `etapa2_texturas/texturas.json` (gravados na pasta de saída)
ou o CLI interativo. Medidas em mm.
"""

# ======================= PEÇA / BASE ======================= #
# Passo da grade de alturas. Menor = mais detalhe e arquivo maior.
# 0,1 mm em 100x100 mm ≈ 200 MB; para testes use 0,2–0,3.
RESOLUCAO_MM = 0.1
# Espessura da placa lisa sob todo o relevo (as texturas e cordões ficam acima dela).
ESPESSURA_BASE_MM = 1.0
# Formato da base (camada de suporte):
#   "retangular": placa retangular inteira (a imagem toda);
#   "silhueta":   a base segue o contorno das regiões escolhidas — as demais (ex.: o mar, o fundo)
#                 ficam de fora. Por padrão entram todas as regiões que NÃO são "fundo"
#                 (defina a cor de fundo na etapa 1: ignore_color) ou use BASE_REGIOES.
BASE_MODO = "retangular"
# Regiões (ids) que formam a base no modo "silhueta". None = todas as que não são fundo.
BASE_REGIOES = None
# True = cordão em volta de toda a peça (moldura externa), se a etapa 1 gerou a moldura.
CORDAO_MOLDURA = True

# ======================= TEXTURAS ======================= #
# Altura dos relevos das texturas acima da base.
AMPLITUDE_TEXTURA_MM = 0.6
# Raio de arredondamento da ponta dos traços triangulares. 0 = ponta viva.
RAIO_APICE_MM = 0.1
# Texturas que o programa usa na SUGESTÃO inicial (a lista completa: python -m img_to_stl --list-textures;
# 0 = lisa, nunca é sugerida mas pode ser escolhida). Regiões vizinhas NUNCA repetem a textura e,
# enquanto houver textura livre, nenhuma se repete. Quem decide é o arquivo texturas.json: edite lá
# (ou no CLI interativo).
TEXTURAS_PADRAO = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
# Região que fica LISA (textura 0) na sugestão automática, para descansar o olhar e poupar material:
#   "externa": a maior região que toca a borda da imagem;  "maior": a maior região de todas;
#   "nenhuma": nenhuma região lisa;  ou o NOME/número de uma região (ex.: "00_azul" ou "0").
# Não se aplica quando já existe região de fundo (ignore_color, já lisa) ou lisa escolhida à mão.
REGIAO_LISA = "externa"
# Regiões de FUNDO decididas na etapa 2 (lisas e fora da base "silhueta"). None = as que a etapa 1 reconheceu
# (cor de fundo). Lista de nomes ou números de região = só estas; [] = nenhuma.
REGIOES_FUNDO = None
# Aviso se o menor traço (após distorção) ficar menor que isso. Bico de 0,4 mm não imprime abaixo.
AVISO_TRACO_MIN_MM = 0.4

# ======================= FRONTEIRAS (cordão) ======================= #
FRONTEIRA_LARGURA_MM = 1.0
# Altura do cordão acima da base (seção semi-elíptica). Ignorada se FRONTEIRA_SEMICIRCULAR = True.
FRONTEIRA_ALTURA_MM = 1.2
FRONTEIRA_SEMICIRCULAR = False
# Faixa sem textura de cada lado, medida a partir da BORDA do cordão. Sugestão: 0,5–1,0.
FRONTEIRA_EXCLUSAO_MM = 1.0
# Rampa suave na saída da exclusão, para a textura não nascer num degrau. 0 = degrau.
EXCLUSAO_TRANSICAO_MM = 0.3

# ======================= SUAVIZAÇÃO DA ZONA DE EXCLUSÃO ======================= #
# Na faixa de exclusão (cordões e pontos) entra uma versão REDUZIDA da textura da região.
# Escala 0,5 = metade do tamanho; 0 = desligado (faixa lisa).
EXCLUSAO_ESCALA_TEXTURA = 0.5
# Altura da textura reduzida em relação à normal (0,6 = 60%).
EXCLUSAO_ALTURA_FATOR = 0.6

# ======================= PONTOS ======================= #
PONTO_ALTURA_MM = 1.4
# Diâmetro (círculo) ou lado (quadrado/triângulo).
PONTO_TAMANHO_MM = 1.2
# Largura da rampa inclinada em volta da forma (evita parede vertical).
PONTO_FLANCO_MM = 0.4
# Raio sem textura em volta do CENTRO do ponto. Aumenta sozinho se a forma for maior.
PONTO_EXCLUSAO_MM = 1.0
# Forma padrão: "circle", "square" ou "triangle".
PONTO_FORMA = "circle"
# Forma por CLASSE de ponto (chave = classe da etapa 1; as não listadas usam PONTO_FORMA).
PONTO_FORMA_POR_CLASSE = {"triplice": "triangle", "multiplo": "square"}
# Classes de ponto que viram relevo. Pontos de interesse (capital, cidade...) sempre viram.
# Tríplices e múltiplos só se ligados aqui (desligados por padrão: servem à modelagem futura).
MODELAR_TRIPLICES = False
MODELAR_MULTIPLOS = False
