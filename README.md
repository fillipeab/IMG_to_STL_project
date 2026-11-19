# img_to_stl

Imagem → **regiões, fronteiras e pontos** → relevo 2.5D texturizado → **STL** para impressão 3D.

## Instalação
```
pip install -r requirements.txt     # numpy, scipy, opencv-python, Pillow
```

## Uso (2 passos)
```
# 1) lê a imagem e gera saida/regioes_preview.png (com o id de cada região) e saida/mapa.json
python -m img2stl imagem.png --read-only -o saida --width-mm 120 --max-regions 8 --tolerance 12

# 2) escolhe as texturas por região e gera o STL
python -m img2stl imagem.png -o saida/peca.stl --width-mm 120 --max-regions 8 --tolerance 12 \
       --textures 0=1,1=2,2=3,3=4
```
Sem `--textures`, as regiões recebem as texturas 1→2→3→4 em ciclo. Para controle total (rotação,
deslocamento, amplitude por região, parâmetros das texturas), use um JSON:
`--config config.json` (veja `config_exemplo.json`; `--save-config` grava a configuração usada).

Pelo Python:
```python
from img2stl import PipelineConfig, ImageToReliefPipeline
cfg = PipelineConfig()
cfg.vision.width_mm = 120
cfg.relief.region_textures = {0: 1, 1: {"texture": 2, "rotation_deg": 15}}
ImageToReliefPipeline(cfg).run("imagem.png", "saida/peca.stl")
```

## Texturas (ids)
`0` lisa · `1` linhas diagonais · `2` X's (grandes + mini) · `3` ondas · `4` escamas · `5` losangos (pirâmides).
Todas periódicas em tile de 10 mm, em coordenadas globais (contínuas entre regiões).
Parâmetros por textura em `relief.texture_params`, ex.: `{"2": {"mini_ratio": 0.625, "corner_height": 0.3}}`.

## Parâmetros: onde mudar
Três níveis, do mais simples ao mais pontual (o de baixo vence o de cima):
1. **`img2stl/parametros.py`** — padrões principais, comentados um a um. Edite e rode de novo.
2. **`--config arquivo.json`** — um conjunto de valores por projeto. `config_exemplo.json` mostra o formato; o significado de cada parâmetro está no **Anexo** no fim deste arquivo.
3. **Linha de comando** — `--width-mm`, `--max-regions`, `--tolerance`, `--resolution`, etc., só naquela execução.

Parâmetros avançados (filtro de ruído, k-means, perfil dos traços, textura por região) ficam em
`img2stl/config.py`, também comentados.

## Distorção de texturas (`transforms.py`)
Camada intermediária que transforma as coordenadas antes de avaliar a textura (vale para qualquer
textura, inclusive as de CAD). Por região, em `relief.region_textures`:
```json
{"0": {"texture": 2, "scale": 1.5, "stretch": 2.0, "stretch_angle_deg": 30,
       "shear": 0.0, "rotation_deg": 0, "offset_mm": [0, 0],
       "warp_amplitude_mm": 0.0, "warp_wavelength_mm": 20, "amplitude_mm": 0.6}}
```
- `scale`: amplia (>1) ou reduz (<1). `stretch`: alonga ao longo de `stretch_angle_deg`. `shear`: inclina.
- `warp_*`: ondula o padrão. `rotation_deg` / `offset_mm`: giram/deslocam.
- Na linha de comando: `--textures 0=2:1.5:2:30` (textura 2, escala 1.5, esticar 2x a 30°).
- A distorção é geométrica: a largura dos traços muda junto. Para manter a largura e mudar só o
  espaçamento, ajuste `texture_params` (pitch, cell, diag_x...). O código avisa se algum traço ficar
  menor que `min_feature_warn_mm` (0,4 mm).

## Texturas no CAD (FreeCAD ↔ Python)
- **Exportar modelos:** `python -m img2stl --export-textures texturas_modelo` grava, para cada textura
  interna, um tile 10×10 mm em STL (sólido fechado), PNG e JSON — já incluídos em `texturas_modelo/`.
- **Editar:** abra o STL no FreeCAD (como referência) e modele o seu tile, ou pinte o PNG em
  GIMP/Krita (preto = baixo, branco = alto; use "tornar contínuo/seamless").
- **Trazer de volta:** no FreeCAD, selecione o corpo → *Arquivo → Exportar → STL (mesh)* e salve em
  `texturas/100_meu_padrao.stl` (id ≥ 100). Use: `--texture-dir texturas --textures 0=100`.
- Regras do STL: XY = plano do tile (a caixa XY do STL é o tamanho do tile), Z para cima, mm; fundo plano;
  a superfície de cima é um relevo sem cavidades/sobreposições; bordas esquerda/direita e
  topo/base se encaixam. O código usa o z-buffer das faces voltadas para cima, normaliza 0..1
  (menor→maior altura) e repete o tile; a amplitude vem de `texture_amplitude_mm`.
  Dá para combinar com distorção (ex.: o mesmo tile reduzido e girado em outra região).

## Estrutura
| Arquivo | Classes principais |
|---|---|
| `config.py` | `VisionConfig`, `ReliefConfig`, `PipelineConfig` (JSON) |
| `vision.py` | `ImageReader`, `RegionGraph`, `BorderTracer`, `PlanarMap`, `Region`, `Border`, `JunctionPoint` |
| `textures.py` | `Texture` (base), `FlatTexture`, `DiagonalLinesTexture`, `XPatternTexture`, `WavesTexture`, `ScalesTexture`, `RidgeProfile`, `TextureLibrary` |
| `parametros.py` | parâmetros principais editáveis (fronteira, pontos, exclusões...) |
| `transforms.py` | `TextureTransform`, `TransformedTexture` (distorção) |
| `tiles.py` | `TileTexture`, `read_stl`, `rasterize_top`, `export_texture_templates` (ida e volta com CAD) |
| `relief.py` | `ReliefBuilder`, `TextureAssigner`, `PointShape` (`CirclePoint`, `SquarePoint`, `TrianglePoint`), `HeightField` |
| `stl_export.py` | `HeightfieldMesher`, `Mesh` (valida malha estanque e grava STL binário) |
| `pipeline.py` | `ImageToReliefPipeline` |

Nova textura: herde de `Texture`, implemente `height(x, y)` (0..1, x/y em mm), defina `texture_id` e
registre com `TextureLibrary.register`.

## Limites conhecidos
- A grade é regular: áreas lisas também geram triângulos (sem decimação).
- Regiões com a mesma cor, mas não vizinhas, são regiões separadas (cada uma recebe seu id).
- Pensado para imagens de áreas de cor definidas (mapas, ilustrações). Fotos precisam de `max_regions` baixo.

Testes: `python -m pytest tests` ou `python tests/test_smoke.py`

## Anexo — Referência de parâmetros
Medidas em mm. "Padrão" = valor em `parametros.py` (ou `config.py` quando não está lá).

### Peça e resolução
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `width_mm` | 100 | Largura final; a altura segue a proporção da imagem. |
| `resolution_mm` | 0,1 | Passo da grade. Menor = mais detalhe e STL maior (100×100 mm ≈ 200 MB a 0,1; use 0,2–0,3 para testar). |
| `base_thickness_mm` | 1,0 | Espessura da placa lisa sob o relevo. |
| `work_max_px` | 1200 | Lado maior da imagem usada nos cálculos (reduz se for maior). Maior = contornos mais finos, mais lento. |

### Regiões (Parte 1)
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `color_tolerance` | 10 | Grau de semelhança (ΔE em Lab). Vizinhas mais parecidas que isso viram uma região. ~2 quase imperceptível · ~10 mesma família de tons · 20+ funde cores distintas. Aumente se uma região de cor variável saiu dividida. |
| `max_regions` | 12 | Teto de regiões; se houver mais, funde as mais parecidas até caber. |
| `min_region_area_mm2` | 15 | Regiões menores são absorvidas pela vizinha de cor mais próxima (limpa "sujeira"). |
| `n_color_clusters` | 16 | Cores iniciais do k-means, antes das fusões. Mantenha ≥ `max_regions`. |
| `ignore_color` / `ignore_tolerance` | `None` / 15 | Cor RGB de fundo, ex.: `[255,255,255]`. A região dessa cor fica lisa. A tolerância diz quão próxima precisa ser. |
| `denoise_iterations` | 2 | Passadas do filtro bilateral que suaviza cores sem borrar bordas (0 desliga). |
| `denoise_sigma_color` / `denoise_sigma_space` | 25 / 7 | Força do filtro: quanto tons podem diferir / tamanho da vizinhança. Maior = borra mais. |
| `random_seed` | 0 | Semente do k-means; o mesmo valor repete o mesmo resultado. |

### Fronteiras
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `min_border_length_mm` | 4 | Fronteiras mais curtas não ganham cordão. |
| `smooth_sigma_mm` | 0,5 | Suavização das curvas (tira o serrilhado). Maior = mais redondo, cantos amaciados. |
| `simplify_tol_mm` | 0,12 | Simplificação Douglas-Peucker. Maior = menos pontos na curva, perfil mais facetado. |
| `outer_frame` | `True` | Cordão também em volta de toda a peça. |
| `border_width_mm` | 1,0 | Largura do cordão. |
| `border_height_mm` | 1,2 | Altura do cordão (semi-elipse). Ignorada com `border_semicircle`. |
| `border_semicircle` | `False` | `True` = semicírculo perfeito (altura = largura/2). |
| `border_exclusion_mm` | 1,0 | Faixa sem textura de cada lado, contada a partir da **borda** do cordão. Faixa livre total = largura + 2×valor. Sugestão: 0,5–0,7. |
| `exclusion_fade_mm` | 0,3 | Rampa suave na saída da exclusão (0 = degrau). |

### Pontos (encontros de 3+ regiões)
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `min_regions_at_point` | 3 | Nº mínimo de regiões que se encontram para marcar um ponto. |
| `point_merge_dist_mm` | 1,5 | Junções mais próximas que isso viram um ponto só. |
| `max_points` | `None` | Mantém só os N pontos de maior valência (`None` = todos). |
| `point_shapes` | `{3: triangle, 4: square}` | Forma por nº de regiões no ponto (`circle`, `square`, `triangle`). |
| `default_point_shape` | `circle` | Forma das valências não listadas acima. |
| `point_size_mm` | 1,2 | Diâmetro (círculo) ou lado (quadrado/triângulo). |
| `point_height_mm` | 1,4 | Altura do ponto acima da base. |
| `point_flank_mm` | 0,4 | Largura da rampa inclinada em volta da forma. |
| `point_exclusion_mm` | 1,0 | Raio sem textura a partir do **centro** (cresce sozinho se a forma for maior). |

### Texturas
| Parâmetro | Padrão | O que faz |
|---|---|---|
| `texture_amplitude_mm` | 0,6 | Altura dos relevos de textura acima da base. |
| `ridge_profile` | `triangular` | Seção dos traços: `triangular` (ponta arredondada) ou `round`. |
| `apex_round_mm` | 0,1 | Raio do arredondamento da ponta triangular (0 = ponta viva). |
| `default_textures` | `[1,2,3,4]` | Texturas usadas em ciclo nas regiões sem escolha manual. |
| `region_textures` | `{}` | Escolha manual: `{id_região: id_textura}` ou dict com distorção (veja abaixo). |
| `texture_dir` | `None` | Pasta com texturas de CAD/PNG (`<id>_<nome>.stl|png`, id ≥ 100). |
| `texture_params` | `{}` | Parâmetros próprios por textura (tabela abaixo). |
| `min_feature_warn_mm` | 0,4 | Aviso se o menor traço, após distorção, ficar menor que isso. |

**Parâmetros por textura** (`texture_params`, ex.: `{"2": {"mini_ratio": 0.625}}`):
| Textura | Parâmetros (padrão) |
|---|---|
| 1 linhas diagonais | `pitch` 2,5 (distância entre linhas) · `width` 0,8 (largura da linha) · `direction` −1/+1 (sentido da diagonal) |
| 2 X's | `cell` 5 (lado do mini-tile) · `w_big` 0,8 / `w_mini` 0,6 (largura dos traços do X grande / mini) · `mini_ratio` 0,75 (fração do espaço entre pernas ocupada pelo mini-X) · `corner_height` 0 (altura onde as pontas dos X grandes se encontram; 0 = rebaixa até a base) · `corner_gap` (folga extra nas pontas) |
| 3 ondas | `wavelength` 5 (comprimento de onda) · `wave_amplitude` 1,0 (quanto a linha ondula, mm) · `pitch` 2,5 · `width` 0,8 |
| 4 escamas | `scale_width` 5 (largura de cada escama) · `width` 0,8 (largura do traço) |
| 5 losangos | `diag_x` 5 / `diag_y` 5 (diagonais do losango) · `apex_round` 0 (arredonda o topo) |

### Distorção por região (`region_textures`)
| Chave | O que faz |
|---|---|
| `texture` | Id da textura. |
| `amplitude_mm` | Altura própria desta região (senão usa `texture_amplitude_mm`). |
| `scale` | >1 amplia o padrão, <1 reduz. |
| `stretch`, `stretch_angle_deg` | Alonga o padrão `stretch`× na direção do ângulo. |
| `shear` | Inclina o padrão. |
| `rotation_deg`, `offset_mm` | Giram e deslocam `[x, y]` o padrão. |
| `warp_amplitude_mm`, `warp_wavelength_mm` | Ondulam o padrão ("tortinho"): quanto desloca e a cada quantos mm. |

- Fronteiras são traçadas entre pixels: regiões vizinhas **compartilham exatamente a mesma curva**.
