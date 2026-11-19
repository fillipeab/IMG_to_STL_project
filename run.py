"""Atalho para rodar sem instalar.

  python run.py                      -> pergunta o endereço da imagem e gera saida/peca.stl
  python run.py imagem.png -o x.stl  -> igual a `python -m img2stl imagem.png -o x.stl`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from img_to_stl.cli import main  # noqa: E402


def pedir_imagem() -> str:
    """Pergunta o endereço da imagem até receber um arquivo que exista."""
    while True:
        caminho = input("Endereço da imagem (pode arrastar o arquivo para cá): ").strip().strip("\"'")
        caminho = os.path.expanduser(caminho)
        if os.path.isfile(caminho):
            return caminho
        print(f"  Arquivo não encontrado: {caminho!r}. Tente de novo.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        imagem = pedir_imagem()
        args = [imagem, "-o", os.path.join("saida", "peca.stl")]
    sys.exit(main(args))
