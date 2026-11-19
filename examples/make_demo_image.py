"""Gera uma imagem de teste: células tipo vitral, uma com gradiente de tom, ruído, uma ilha e um ponto minúsculo."""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def make(path: str, w: int = 800, h: int = 600, seed: int = 1) -> None:
    rng = np.random.default_rng(seed)
    seeds = np.array([[150, 140], [430, 90], [700, 170], [120, 460], [400, 380], [690, 470]], float)
    colors = np.array([
        [236, 120, 160],   # rosa (com gradiente)
        [90, 150, 220],    # azul
        [110, 190, 110],   # verde
        [245, 205, 80],    # amarelo
        [240, 140, 60],    # laranja
        [170, 130, 210],   # lilás
    ], float)

    yy, xx = np.mgrid[0:h, 0:w]
    d = (xx[..., None] - seeds[:, 0]) ** 2 + (yy[..., None] - seeds[:, 1]) ** 2
    cell = d.argmin(-1)
    img = colors[cell]

    # gradiente de tom na célula rosa (a "região rosa que varia um pouco")
    pink = cell == 0
    shift = (xx / w) * 40 - 15
    img[pink] += np.stack([shift[pink] * 0.4, shift[pink] * 0.8, shift[pink] * 0.4], 1)

    img += rng.normal(0, 5, img.shape)                      # ruído
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

    draw = ImageDraw.Draw(pil)
    draw.ellipse([380, 340, 450, 410], fill=(190, 40, 60))   # ilha dentro da célula laranja
    draw.ellipse([250, 250, 256, 256], fill=(30, 30, 30))    # ponto minúsculo (deve sumir)
    pil = pil.filter(ImageFilter.GaussianBlur(0.8))          # anti-aliasing
    pil.save(path)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "demo.png")
