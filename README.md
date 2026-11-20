# img_to_stl

Imagem → **etapa 1: reconhecimento** (regiões, famílias, fronteiras e pontos) → **etapa 2: textura** (relevo 2.5D) → **STL** para impressão 3D.

## Instalação
```
pip install -r requirements.txt     # numpy, scipy, opencv-python, Pillow
```

## Uso
```
python run.py                       # menu: 1) importar nova imagem  2) operar em uma imagem já existente
python -m img_to_stl imagem.png     # importa a imagem e segue o fluxo interativo
python -m img_to_stl imagem.png --auto            # sem perguntas: etapa 1 + etapa 2 com os padrões
python -m img_to_stl imagem.png --etapa 1         # só o reconhecimento
python -m img_to_stl --projeto imagem --etapa 2 --auto   # só a etapa 2 (depois de editar texturas.json)
```
**Menu:** `1) Importar nova imagem` copia a imagem para o repositório (se o nome já existe: sobrescrever, novo nome ou cancelar).
`2) Operar em uma imagem já existente` lista o repositório com o estado de cada uma (etapa 1 ✓/—, etapa 2 ✓/—, STL ✓/—) e
oferece *refazer a etapa 1* ou *ajustar texturas e gerar o STL* (etapa 2), já com os parâmetros que o projeto usou.

**No terminal, um passo de cada vez** (interface principal):
1. *Parâmetros:* cada etapa abre mostrando só os principais (etapa 1: largura, máximo de regiões, tolerância de cor, cor de fundo; etapa 2: resolução, base, altura das texturas, região lisa).
   `número` altera, `?<número>` explica (valor atual e padrão), `p` lista **todos** os parâmetros divididos por grupo (e permite alterá-los), `Enter` continua.
2. *Etapa 1:* processa e mostra só o resumo. `v` lista as regiões, `f` funde regiões, `r` refaz, `Enter` segue.
3. *Etapa 2:* parâmetros → **texturas das regiões** (escolha o número da região e a lista de texturas aparece; `l` mostra a lista a qualquer momento) → gerar o STL.

**Interface auxiliar (versão 2):** o mesmo fluxo, mas os parâmetros ficam em abas: `Enter` usa os atuais, `a` abre os grupos um a um.
Escolha com `python -m img_to_stl --interface auxiliar` ou, no menu inicial, `3) Trocar de interface`.

**Por objeto, sem menu:** escolha o projeto e diga o que fazer (`python -m img_to_stl projeto -h`):
```
python -m img_to_stl projetos                              # lista os projetos
python -m img_to_stl projeto demo ver                      # estado, resumo e texturas
python -m img_to_stl projeto demo regioes                  # regiões numeradas
python -m img_to_stl projeto demo fundo 3                  # região 3 vira o fundo (lisa, fora da base silhueta)
python -m img_to_stl projeto demo fundir menores=50        # funde (ver abaixo)
python -m img_to_stl projeto demo textura 3=ondas/3(1.5)   # muda a textura de uma região
python -m img_to_stl projeto demo gerar --resolution 0.3   # etapa 2: gera o STL
python -m img_to_stl projeto demo reconhecer               # refaz a etapa 1
python -m img_to_stl projeto demo abrir                    # abre no modo interativo (--interface auxiliar)
```

## Região de fundo (etapa 2)
- Fundo = região **lisa** e **fora da base "silhueta"**. A etapa 1 reconhece o fundo pela cor (`ignore_color`); na etapa 2 você pode escolher outra.
- Modo interativo: no início da etapa 2, `Região de fundo: ...` → `f` escolhe (número ou nome), `n` nenhuma, `a` volta à reconhecida na etapa 1.
- Linha de comando: `projeto NOME fundo 3` · `fundo nenhuma` · `fundo auto` ou `--background-regions 3,5`. Parâmetro: `background_regions`.
- A região escolhida passa a `lisa/0` no `texturas.json`.

## Editar `texturas.json` e regerar o STL
1. Edite `repositorio/<nome>/etapa2_texturas/texturas.json` (região por nome ou número, `"ondas/3(escala=1.5)"`).
2. Regere só a etapa 2: `python -m img_to_stl projeto NOME gerar` (ou `--projeto NOME --etapa 2 --auto`, ou menu → 2 → etapa 2).
- Erro de digitação: o programa diz qual região/linha está errada e **não** mexe no STL anterior.
- Se a etapa 1 for refeita (ou regiões fundidas), o arquivo antigo vira `texturas.json.antigo` e sai uma nova sugestão.

## Fundir regiões
- **Por critério** (sem precisar saber os números):
  - `familia` junta as regiões irmãs (cor parecida) que se tocam; `familia=2` só a família 2.
  - `parecidas=8` junta vizinhas cuja cor difere menos que 8 (ΔE), as mais parecidas primeiro.
  - `menores=50` manda cada região com menos de 50 mm² para a vizinha de cor mais parecida.
  - `cor=verde,lilas` junta as regiões de cada cor numa só; `cor=verde+lilas` junta as duas cores numa região só.
- **Limite ajustável:** nos critérios `parecidas` e `menores`, o terminal mostra quantas regiões serão fundidas (ex.: 7 → 6) e a lista dos grupos;
  `Enter` continua, `l` muda o limite (e recalcula o plano) e `c` cancela. Em `projeto NOME fundir`, a pergunta aparece quando há terminal (`--sim` fundir direto).
- **Por número ou nome:** `3,7` ou `3 7` (também `03_verde 07_azul`).
- Onde usar: `f` na etapa 1 do modo interativo (mostra o plano e pede confirmação nos critérios), `--fundir ESPEC` (repetível),
  ou `python -m img_to_stl projeto NOME fundir ESPEC [ESPEC...]`.
- A região fundida soma as áreas e usa a cor média; nomes, famílias, fronteiras e pontos tríplices são refeitos (pontos de interesse ficam).
- A fusão é guardada em `merge_regions` (`parametros.json`): refazer a etapa 1 com os mesmos parâmetros repete a fusão (se algo deixar de valer, vira aviso, não erro).
  Números valem para o resultado do momento; critérios se adaptam. Para desfazer, deixe `merge_regions` vazio e refaça a etapa 1.
- O `texturas.json` anterior é guardado como `.antigo` e uma nova sugestão é feita (as regiões mudaram).

## As duas etapas
**Etapa 1 — reconhecimento** (`img_to_stl/etapa1_reconhecimento/`). Métodos clássicos de visão computacional (sem rede neural):
filtro bilateral → k-means em Lab → componentes conexos → remoção de traços finos → fusão por cor/área → fronteiras traçadas
entre pixels (suavizadas, contínuas, sem pontas soltas) → pontos.
- **Regiões**: setores de cor homogênea. Cada uma tem número, **nome** (`03_verde_2` = número + cor + ordinal) e **família**.
- **Famílias ("regiões irmãs")**: regiões de cor parecida (ΔE < `family_tolerance`), vizinhas ou não. Servem para tratar "todos os verdes" juntos.
- **Fronteiras**: linhas entre regiões (`F03_r01_r04`); a moldura externa é `F00_moldura_rNN`.
- **Pontos**, cada um com uma **classe**: `triplice` (3 regiões se encontram) e `multiplo` (4+) — sempre calculados e listados;
  e **pontos de interesse** (`capital`, `cidade`... a classe é sua) informados de duas formas:
  1. **marcadores** na imagem: bolinhas de uma cor combinada (`--marker capital=255,0,0,30`); são localizadas e apagadas da imagem;
  2. **arquivo** `.json`/`.csv` (`--points-file`) com `classe, nome, x_px, y_px` (pixels da imagem original) ou `x_mm, y_mm`.

**Etapa 2 — textura e STL** (`img_to_stl/etapa2_texturas/`):
- **Base**: `base_mode = "retangular"` (placa inteira) ou `"silhueta"` (a base segue o contorno das regiões escolhidas em `base_regions`,
  ou de todas que não são fundo — defina o fundo com `--ignore-color`). O cordão da fronteira com o fundo cabe inteiro na base.
- **Texturas**: o programa **sugere** (vizinhas nunca repetem; nenhuma repete enquanto houver textura livre; uma região fica lisa, ver `smooth_region`) e grava `texturas.json`; você edita.
  A lisa automática não age se já houver fundo (`--ignore-color`) ou lisa escolhida à mão.
- Cordões de fronteira, pontos de interesse com forma por classe (`point_shape_by_class`), exclusão com textura reduzida.
  Pontos tríplices/múltiplos só viram relevo se ligados (`model_triple_points`, `model_multiple_points`).

## Texturas disponíveis
A lista completa, com os parâmetros de cada uma, fica em **`texturas_disponiveis.txt`** (pasta principal). **Atualizar texturas** (releitura da pasta de texturas próprias, conferência de cada arquivo e regravação da lista): no menu inicial, `3) Texturas` (mostra a lista e tem a opção `a` = atualizar),
ou `python -m img_to_stl --atualizar-texturas [PASTA]` (padrão: a pasta `texturas/`). Arquivos fora do padrão `<id>_<nome>.stl|png` ou ilegíveis viram aviso.
A pasta usada fica em `texture_dir` e vale nas próximas execuções. `--list-textures` só mostra a lista no terminal.
Todas periódicas em tile de 10 mm (continuam sem emenda entre regiões). `0` (lisa) é sugerida para **uma** região (parâmetro `smooth_region`: `externa` = a maior que toca a borda, `maior`, `nenhuma` ou o nome/número de uma região); em qualquer região você pode escolher `lisa/0`.
| id | nome | descrição |
|---|---|---|
| `0` | lisa | sem relevo: superfície lisa |
| `1` | linhas diagonais | linhas diagonais a 45° |
| `2` | X's | X grande em cada célula, com mini-X entre eles |
| `3` | ondas | ondas tortinhas, em fileiras |
| `4` | escamas | escamas sobrepostas (arcos) |
| `5` | losangos | losangos em pirâmide |
| `6` | pontos | cúpulas pequenas em grade |
| `7` | xadrez | quadrados altos e baixos alternados |
| `8` | grade | traços cruzados na horizontal e vertical |
| `9` | zigue-zague | traços em V, como espinha de peixe |
| `10` | aneis | anéis concêntricos com ponto central |
| `11` | tijolos | tijolos em fileiras desencontradas |
| `12` | colinas | ondulado suave nos dois sentidos |

Parâmetros próprios de cada uma em `texture_params` (ex.: `{"6": {"pitch": 5.0, "diameter": 2.4}}`): 2 `mini_ratio`, `corner_height` · 6 `pitch`, `diameter` ·
7 `cell`, `bevel` · 8 `pitch`, `width` · 9 `pitch`, `amp`, `period`, `width` · 10 `cell`, `radius`, `width` · 11 `brick_w`, `brick_h`, `mortar`, `bevel` · 12 `period`.
Valores de passo/célula devem dividir 10 mm para o tile fechar. Prévia de todas: `examples/texturas_preview.png`.

### Especificação de textura: `nome/numero(distorções)`
Como uma função: textura e distorções entre parênteses, em ordem ou por nome.
```
ondas/3                          textura 3, sem distorção          (também vale só "3" ou só "ondas")
ondas/3(1.5)                     escala 1,5
ondas/3(1.5, 2, 30)              escala 1,5 · alongada 2x na direção de 30°
escamas/4(escala=0.8, amp=0.9)   por nome, ordem livre; amp = altura própria (mm)
lisa/0                           sem textura
```
Ordem posicional: `escala, alongar, angulo, cisalhar, rotacao, desloc_x, desloc_y, onda_amp, onda_comp`; mais `amp` (só por nome).
Texturas: veja a tabela abaixo (ou `python -m img_to_stl --list-textures`); `>= 100` = as suas (pasta `--texture-dir`).

### `texturas.json` (arquivo de geração)
```json
{"regioes":  {"00_azul": "ondas/3", "01_verde_1": "escamas/4(escala=1.5)"},
  "familias": {"familia_01_verde": "linhas_diagonais/1"}}
```
`familias` vale para as regiões irmãs sem linha própria em `regioes`. Erros dizem qual linha está errada.
Depois de editar: opção 2 do menu, ou `python -m img_to_stl --projeto imagem --etapa 2 --auto`.
Na linha de comando: `--textura 3=ondas/3(1.5,2,30)` (repetível).

## Pastas: repositório e saídas
```
repositorio/<nome_da_imagem>/        um projeto por imagem (tudo sobre ela)
  identificacao.txt                  identificação geral
  imagem_original.<ext>              cópia da imagem de entrada
  etapa1_reconhecimento/
    parametros.json                  parâmetros usados
    parametros_e_resultados.txt      parâmetros + resultados (nº de regiões, famílias, tríplices, pontos de interesse, tabelas)
    resultado.json  rotulos.png      resultado completo (a etapa 2 recarrega daqui)
    previa.png                       regiões coloridas com número, fronteiras e pontos por classe
    negativos/
      regioes/regiao_03_verde_2.png  uma máscara por região (nomeada/numerada)
      regioes_niveis_de_cinza.png
      familias/familia_01_verde.png  uma máscara por família
      fronteiras/fronteiras.png  fronteiras_numeradas.png
      pontos/pontos_marcados.png (legenda por classe)  pontos_<classe>.png
  etapa2_texturas/
    parametros.json                  parâmetros usados (editável)
    texturas.json                    texturas por região (editável)
    previa_relevo.png                relevo sombreado
    relatorio.txt                    parâmetros, texturas aplicadas, triângulos, volume, avisos

saidas/<nome_da_imagem>.stl          só os STL prontos para imprimir (sem cópia dentro do projeto: um STL fino pode ter 100–200 MB)
```
Mudar de pasta: `-o PASTA` (repositório) e `--saidas PASTA`, ou `base_dir` / `stl_dir` no JSON. Gerar de novo sobrescreve o STL de mesmo nome.

## Parâmetros: onde mudar (o de baixo vence o de cima)
1. `etapa1_reconhecimento/parametros.py` e `etapa2_texturas/parametros.py` — padrões, comentados um a um.
2. `--config arquivo.json` (ver `config_exemplo.json`) ou os `parametros.json` / `texturas.json` da pasta do projeto.
3. Linha de comando (`--width-mm`, `--max-regions`, `--resolution`...) ou o modo interativo.
Avançados (filtro, k-means, perfil dos traços): `etapa1_reconhecimento/config.py` e `etapa2_texturas/config.py`.

## Texturas no CAD (FreeCAD ↔ Python)
- **Exportar modelos:** `python -m img_to_stl --export-textures texturas_modelo` (tile 10×10 mm em STL, PNG e JSON; já em `texturas_modelo/`).
- **Editar:** abra o STL no FreeCAD ou pinte o PNG (preto = baixo, branco = alto; tornar contínuo/seamless).
- **Trazer de volta:** exporte STL (mesh) para `texturas/100_meu_padrao.stl` (id ≥ 100) e use `--texture-dir texturas` e `"100_meu_padrao/100"` (ou `100`) no `texturas.json`.
- Regras do STL: XY = plano do tile; Z para cima, mm; fundo plano; topo sem cavidades; bordas que se encaixam.

## Estrutura do código
| Pasta / arquivo | Conteúdo |
|---|---|
| `etapa1_reconhecimento/` | `parametros.py`, `config.py` (`Etapa1Config`), `leitor.py` (`ImageReader`), `fusao.py`, `fronteiras.py`, `cores.py` (nomes e famílias), `pontos.py`, `modelos.py` (`PlanarMap`, `Region`, `Family`, `Border`, `InterestPoint`), `negativos.py`, `saida.py`, `pipeline.py` (`Etapa1`) |
| `etapa2_texturas/` | `parametros.py`, `config.py` (`Etapa2Config`), `especificacao.py` (`nome/numero(...)`), `texturas_arquivo.py` (`texturas.json`), `atribuicao.py`, `relevo.py` (`ReliefBuilder`, `HeightField`), `formas_pontos.py`, `stl.py` (`HeightfieldMesher`, `Mesh`), `saida.py`, `pipeline.py` (`Etapa2`), `biblioteca/` (texturas: `base`, `padroes` (0–5), `padroes_extra` (6–12), `transformacoes`, `tiles`, `registro`) |
| `comum/` | geometria, leitura/escrita de configuração, nomes de arquivos |
| `config.py`, `pipeline.py` | `PipelineConfig`, `ImageToStl` (orquestra as duas etapas, o repositório e a pasta de STL) |
| `cli.py`, `cli_projeto.py`, `interativo.py`, `cli_auxiliar.py` | linha de comando, comando por objeto (`projeto NOME ação`), menu e sessão interativa (principal) e interface auxiliar (abas) |

Nova textura: herde de `Texture`, implemente `height(x, y)` (0..1, x/y em mm), defina `texture_id`, `name` e `description` e registre com `TextureLibrary.register` (ela aparece sozinha na lista).

## Limites conhecidos
- A grade é regular: áreas lisas também geram triângulos. A base "silhueta" gera ~2x mais triângulos por célula (topo + fundo); aumente `resolution_mm` se o arquivo ficar grande.
- Regiões de mesma cor não vizinhas são regiões separadas (mas ficam na mesma família).
- Pensado para imagens de áreas de cor definidas (mapas, ilustrações). Fotos precisam de `max_regions` baixo.

Testes: `python -m pytest tests` ou `python tests/test_smoke.py`

## Anexo — Referência de parâmetros
Medidas em mm. Os mesmos nomes valem nos JSON (`parametros.json`, `--config`).

### Etapa 1 (`Etapa1Config`)
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `width_mm` | `100.0` | Largura final da peça em mm; a altura segue a proporção da imagem. |
| `work_max_px` | `1200` | Lado maior (pixels) da imagem usada nos cálculos. Maior = contornos mais finos, mais lento. |
| `denoise_iterations` | `2` | Passadas do filtro bilateral que suaviza cores sem borrar bordas. 0 desliga. |
| `denoise_sigma_color` | `25.0` | Quanto dois tons podem diferir e ainda serem misturados pelo filtro. |
| `denoise_sigma_space` | `7.0` | Tamanho (pixels) da vizinhança do filtro. |
| `n_color_clusters` | `16` | Cores iniciais do k-means, antes das fusões. Mantenha >= max_regions. |
| `color_tolerance` | `10.0` | Grau de semelhança (delta E, Lab): vizinhas mais parecidas que isso viram uma região. |
| `max_regions` | `12` | Teto de regiões; se houver mais, funde as mais parecidas até caber. |
| `min_region_area_mm2` | `15.0` | Regiões menores (mm2) são absorvidas pela vizinha de cor mais próxima. |
| `min_region_thickness_mm` | `1.0` | Traços/regiões mais finos que isso (mm) são apagados e preenchidos pela vizinhança. 0 = desligado. |
| `ignore_color` | `null` | Cor RGB de fundo, ex.: [255, 255, 255]. null = nenhuma. |
| `ignore_tolerance` | `15.0` | Quão próxima (delta E) uma região precisa ser de ignore_color para contar como fundo. |
| `merge_regions` | `[]` | Fusões pedidas por você, em ordem. Cada item: lista de números de região ([3, 7]) ou critério: "familia" (irmãs que se tocam), "menores=50" (regiões < 50 mm² vão para a vizinha mais parecida), "cor=verde,lilas" (regiões de mesma cor viram uma). Números valem para o resultado do momento: se mudar outros parâmetros, confira. |
| `family_tolerance` | `25.0` | Regiões com delta E menor que isso (vizinhas ou não) são 'irmãs' (mesma família). 0 = sem famílias. |
| `min_border_length_mm` | `4.0` | Fronteira mais curta que isso (mm) é encolhida: as duas junções viram uma só. |
| `smooth_sigma_mm` | `0.5` | Suavização das curvas (mm). Maior = mais redondo. |
| `simplify_tol_mm` | `0.12` | Simplificação Douglas-Peucker (mm). Maior = menos pontos na curva. |
| `outer_frame` | `true` | true = fronteira também em volta de toda a peça. |
| `triple_min_regions` | `3` | Nº mínimo de regiões que se encontram num ponto tríplice (3 = junção em Y). |
| `triple_merge_dist_mm` | `1.5` | Junções mais próximas que isso (mm) viram um ponto só. |
| `point_markers` | `[]` | Marcadores de pontos de interesse na imagem: [{"classe": "capital", "cor": [255,0,0], "tolerancia": 30}]. |
| `points_file` | `null` | Arquivo .json/.csv com pontos de interesse (classe, nome, x_px, y_px ou x_mm, y_mm). null = nenhum. |
| `marker_max_area_mm2` | `80.0` | Manchas de cor maiores que isso (mm2) não são tratadas como marcador. |
| `negatives_px_per_mm` | `10.0` | Resolução dos negativos (pixels por mm). |
| `negatives_line_mm` | `0.5` | Espessura (mm) da linha nas imagens de fronteiras. |
| `negatives_point_radius_mm` | `1.2` | Raio (mm) da marca de cada ponto nas imagens de pontos. |
| `random_seed` | `0` | Semente do k-means: o mesmo valor repete o mesmo resultado. |

### Etapa 2 (`Etapa2Config`)
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `resolution_mm` | `0.1` | Passo da grade (mm). Menor = mais detalhe e STL maior (100x100 mm a 0,1 = ~200 MB; teste com 0,2-0,3). |
| `base_thickness_mm` | `1.0` | Espessura (mm) da placa lisa sob todo o relevo. Deve ser > 0. |
| `base_mode` | `retangular` | 'retangular' = placa inteira; 'silhueta' = a base segue o contorno das regiões escolhidas (o resto fica de fora). |
| `base_regions` | `null` | Modo silhueta: ids das regiões que formam a base. null = todas as que não são fundo. |
| `frame_cord` | `true` | true = cordão também em volta de toda a peça (moldura). |
| `background_regions` | `null` | Regiões de FUNDO (lisas; fora da base 'silhueta'). null = as reconhecidas na etapa 1 (cor de fundo); lista de nomes ou números = só estas; [] = nenhuma. |
| `texture_amplitude_mm` | `0.6` | Altura (mm) dos relevos de textura acima da base. |
| `ridge_profile` | `triangular` | Seção dos traços: 'triangular' (ponta arredondada) ou 'round'. |
| `apex_round_mm` | `0.1` | Raio (mm) do arredondamento da ponta triangular. 0 = ponta viva. |
| `default_textures` | `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]` | Texturas usadas na SUGESTÃO inicial (texturas.json). Lista completa: python -m img_to_stl --list-textures. A lisa (0) não entra aqui: veja smooth_region. |
| `smooth_region` | `externa` | Região que fica LISA na sugestão: 'externa' = a maior que toca a borda; 'maior' = a maior de todas; 'nenhuma'; ou nome/número de uma região. Não age se já houver fundo (ignore_color) ou lisa escolhida à mão. |
| `texture_dir` | `null` | Pasta com texturas de CAD/PNG '<id>_<nome>.stl|png' (id >= 100). null = nenhuma. |
| `min_feature_warn_mm` | `0.4` | Avisa se o menor traço, após distorção, ficar menor que isso (mm). |
| `texture_params` | `{}` | Parâmetros próprios por textura, ex.: {"2": {"mini_ratio": 0.625}}. Nomes por textura no README. |
| `border_width_mm` | `1.0` | Largura (mm) do cordão da fronteira. |
| `border_height_mm` | `1.2` | Altura (mm) do cordão (semi-elipse). Ignorada se border_semicircle = true. |
| `border_semicircle` | `false` | true = semicírculo perfeito (altura = largura/2). |
| `border_exclusion_mm` | `1.0` | Faixa sem textura de cada lado, contada a partir da BORDA do cordão. |
| `exclusion_fade_mm` | `0.3` | Rampa suave (mm) na saída da exclusão. 0 = degrau. |
| `exclusion_texture_scale` | `0.5` | Escala da textura reduzida na zona de exclusão (0,5 = metade). 0 = faixa lisa. |
| `exclusion_texture_height_factor` | `0.6` | Altura da textura reduzida relativa à normal (0,6 = 60%). |
| `point_height_mm` | `1.4` | Altura (mm) do ponto acima da base. |
| `point_size_mm` | `1.2` | Diâmetro (círculo) ou lado (quadrado/triângulo), em mm. |
| `point_flank_mm` | `0.4` | Largura (mm) da rampa inclinada em volta da forma do ponto. |
| `point_exclusion_mm` | `1.0` | Raio (mm) sem textura a partir do CENTRO do ponto. |
| `point_shape` | `circle` | Forma padrão dos pontos: circle, square ou triangle. |
| `point_shape_by_class` | `{"triplice": "triangle", "multiplo": "square"}` | Forma por classe de ponto, ex.: {"capital": "circle", "triplice": "triangle"}. |
| `model_triple_points` | `false` | true = pontos tríplices viram relevo (desligado por padrão). |
| `model_multiple_points` | `false` | true = pontos de 4+ regiões viram relevo (desligado por padrão). |

### Distorções de textura (em `texturas.json`)
| Nome (posição) | Padrão | Efeito |
|---|---|---|
| `escala` (1) | 1 | >1 amplia, <1 reduz o padrão |
| `alongar` (2) | 1 | alonga ao longo de `angulo` |
| `angulo` (3) | 0 | direção do alongamento (°) |
| `cisalhar` (4) | 0 | inclina o padrão |
| `rotacao` (5) | 0 | gira (°, anti-horário) |
| `desloc_x`, `desloc_y` (6, 7) | 0 | desloca o padrão (mm) |
| `onda_amp`, `onda_comp` (8, 9) | 0 / 20 | ondula o padrão: amplitude e comprimento de onda (mm) |
| `amp` (só por nome) | `texture_amplitude_mm` | altura própria da região (mm) |

A distorção é geométrica: a largura dos traços muda junto. Para manter a largura e mudar só o espaçamento use `texture_params`
(ex.: `{"2": {"mini_ratio": 0.625}}`). O código avisa se algum traço ficar menor que `min_feature_warn_mm`.
