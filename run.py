"""Atalho para rodar sem instalar (serve também para o botão "Run" de uma IDE).

  python run.py                    -> menu: 1) importar nova imagem  2) operar em uma imagem já existente
  python run.py imagem.png         -> importa a imagem e segue o fluxo interativo
  python run.py imagem.png --auto  -> igual a `python -m img_to_stl imagem.png --auto` (sem perguntas)

Pastas: repositorio/<nome>/ (um projeto por imagem) e saidas/<nome>.stl (só os STL prontos).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from img_to_stl.cli import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--auto" not in args and "--interativo" not in args and "-i" not in args:
        args.append("--interativo")      # IDEs nem sempre se declaram terminal: força o modo interativo
    sys.exit(main(args))
