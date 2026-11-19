"""Ponto de entrada: python -m img_to_stl ...  (também funciona rodando este arquivo direto)."""
import os
import sys

if __package__ in (None, ""):
    # Rodado como arquivo (python img_to_stl/__main__.py ou botão "Run" de uma IDE): não há pacote
    # pai, então os imports relativos falhariam. Põe a pasta do projeto no caminho e usa imports absolutos.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from img_to_stl.cli import main
else:
    from .cli import main

sys.exit(main())
