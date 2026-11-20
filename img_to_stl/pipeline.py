"""Orquestra as duas etapas e organiza o repositório e a pasta de STL.

repositorio/<nome>/                  um projeto por imagem
    identificacao.txt                identificação geral
    imagem_original.<ext>            cópia da imagem de entrada
    etapa1_reconhecimento/           parâmetros, resultados, previa.png, negativos/ ...
    etapa2_texturas/                 parametros.json, texturas.json, previa_relevo.png, relatorio.txt
saidas/<nome>.stl                    só os STL prontos para imprimir
"""
from __future__ import annotations

import datetime
import glob
import os
import shutil
from typing import Callable, Dict, List, Optional

from . import __version__
from .comum.arquivos import ensure, image_stem, slug
from .config import PipelineConfig
from .etapa1_reconhecimento import Etapa1, Etapa1Config, PlanarMap
from .etapa1_reconhecimento.leitor import ImageReader
from .etapa1_reconhecimento.saida import save_stage1
from .etapa2_texturas import Etapa2, Etapa2Config
from .etapa2_texturas.stl import Mesh
from .etapa2_texturas.texturas_arquivo import set_entry

PASTA_ETAPA1 = "etapa1_reconhecimento"
PASTA_ETAPA2 = "etapa2_texturas"


class ImageToStl:
    """Uso típico:

        app = ImageToStl(PipelineConfig(), log=print)
        pmap = app.run_etapa1("brasil.png")           # repositorio/brasil/etapa1_reconhecimento/...
        app.run_etapa2("repositorio/brasil")          # saidas/brasil.stl
        app.run("brasil.png")                         # as duas, em sequência
    """

    def __init__(self, config: Optional[PipelineConfig] = None, log: Optional[Callable[[str], None]] = None):
        self.config = config or PipelineConfig()
        self.log = log or (lambda msg: None)

    # ---- repositório ---- #
    def project_dir(self, name_or_image: str) -> str:
        """Pasta do projeto a partir do nome (ou do caminho da imagem)."""
        stem = image_stem(name_or_image) if os.path.splitext(name_or_image)[1] else name_or_image
        return os.path.join(self.config.base_dir, stem)

    def resolve_project(self, ref: str) -> str:
        """Aceita o nome do projeto ('brasil') ou o caminho da pasta."""
        if os.path.isdir(ref) and os.path.isdir(os.path.join(ref, PASTA_ETAPA1)):
            return ref
        cand = os.path.join(self.config.base_dir, ref)
        if os.path.isdir(cand):
            return cand
        raise FileNotFoundError(f"Projeto '{ref}' não encontrado em {self.config.base_dir}/ "
                                f"(existentes: {', '.join(self.list_projects()) or 'nenhum'})")

    def list_projects(self) -> List[str]:
        base = self.config.base_dir
        if not os.path.isdir(base):
            return []
        return sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))

    def exists(self, name: str) -> bool:
        return os.path.isdir(os.path.join(self.config.base_dir, name))

    def unique_name(self, stem: str) -> str:
        base = slug(stem) if stem else "imagem"
        name, i = base, 2
        while self.exists(name):
            name, i = f"{base}_{i}", i + 1
        return name

    def stl_path(self, proj: str) -> str:
        return os.path.join(self.config.stl_dir, os.path.basename(os.path.normpath(proj)) + ".stl")

    def status(self, proj: str) -> Dict[str, bool]:
        return {"etapa1": os.path.isfile(os.path.join(proj, PASTA_ETAPA1, "resultado.json")),
                "etapa2": os.path.isfile(os.path.join(proj, PASTA_ETAPA2, "texturas.json")),
                "stl": os.path.isfile(self.stl_path(proj))}

    @staticmethod
    def original_image(proj: str) -> str:
        found = glob.glob(os.path.join(proj, "imagem_original.*"))
        if not found:
            raise FileNotFoundError(f"Sem imagem_original em {proj}")
        return found[0]

    def load_params(self, proj: str) -> None:
        """Volta os parâmetros ao que foi usado neste projeto (se gravados)."""
        p1 = os.path.join(proj, PASTA_ETAPA1, "parametros.json")
        p2 = os.path.join(proj, PASTA_ETAPA2, "parametros.json")
        if os.path.isfile(p1):
            self.config.etapa1 = Etapa1Config.from_json(p1)
        if os.path.isfile(p2):
            self.config.etapa2 = Etapa2Config.from_json(p2)

    # ---- etapa 1 ---- #
    def run_etapa1(self, image_path: str, proj: Optional[str] = None) -> PlanarMap:
        proj = proj or self.project_dir(image_path)
        ensure(proj)
        ext = os.path.splitext(image_path)[1] or ".png"
        dest = os.path.join(proj, "imagem_original" + ext)
        if not (os.path.exists(dest) and os.path.samefile(image_path, dest)):
            for old in glob.glob(os.path.join(proj, "imagem_original.*")):
                os.remove(old)
            shutil.copyfile(image_path, dest)
        pmap = Etapa1(self.config.etapa1, self.log).run(
            image_path, os.path.join(proj, PASTA_ETAPA1), negatives=self.config.negatives)
        self._write_identification(proj, image_path, pmap)
        return pmap

    def fundir_regioes(self, proj: str, pmap: PlanarMap, group: List[int]) -> PlanarMap:
        """Funde as regiões `group` do resultado atual, regrava a etapa 1 e guarda a fusão em `merge_regions`
        (assim refazer a etapa 1 com os mesmos parâmetros repete a fusão)."""
        cfg1 = self.config.etapa1
        reader = ImageReader(cfg1)
        new = reader.merge(pmap, list(group))
        cfg1.merge_regions.append([int(i) for i in group])
        save_stage1(new, cfg1, os.path.join(proj, PASTA_ETAPA1), reader.warnings, self.config.negatives)
        return new

    # ---- etapa 2 ---- #
    def load_etapa1(self, proj: str) -> PlanarMap:
        return PlanarMap.load(os.path.join(proj, PASTA_ETAPA1))

    def etapa2(self) -> Etapa2:
        return Etapa2(self.config.etapa2, self.log)

    def run_etapa2(self, proj: str, pmap: Optional[PlanarMap] = None, textures_file: Optional[str] = None,
                   texture_edits: Optional[List[str]] = None) -> Mesh:
        """`texture_edits`: linhas 'REGIAO=ESPEC' aplicadas ao texturas.json antes de gerar."""
        pmap = pmap or self.load_etapa1(proj)
        e2, out_dir = self.etapa2(), os.path.join(proj, PASTA_ETAPA2)
        if texture_edits:
            path, _ = e2.prepare_textures(pmap, out_dir, textures_file)
            for item in texture_edits:
                key, _, spec = item.partition("=")
                set_entry(path, key.strip(), spec.strip(), pmap, self.config.etapa2.texture_amplitude_mm)
        return e2.run(pmap, out_dir, self.stl_path(proj), textures_file)

    # ---- tudo ---- #
    def run(self, image_path: str, proj: Optional[str] = None) -> Mesh:
        proj = proj or self.project_dir(image_path)
        pmap = self.run_etapa1(image_path, proj)
        mesh = self.run_etapa2(proj, pmap)
        self.log(f"[saída] projeto: {os.path.abspath(proj)}  ·  STL: {os.path.abspath(self.stl_path(proj))}")
        return mesh

    # ---- identificação ---- #
    def _write_identification(self, proj: str, image_path: str, pmap: PlanarMap) -> None:
        W, H = pmap.size_mm
        name = os.path.basename(os.path.normpath(proj))
        lines = [f"img_to_stl {__version__} — identificação do projeto", "",
                 f"projeto: {name}",
                 f"data: {datetime.datetime.now():%Y-%m-%d %H:%M}",
                 f"imagem de entrada: {os.path.abspath(image_path)}",
                 f"cópia da imagem: imagem_original{os.path.splitext(image_path)[1]}",
                 f"peça: {W:.1f} x {H:.1f} mm", "",
                 "Conteúdo da pasta:",
                 f"  {PASTA_ETAPA1}/  parâmetros e resultados do reconhecimento (regiões, famílias, fronteiras, pontos),",
                 "                   prévia e negativos numerados/nomeados",
                 f"  {PASTA_ETAPA2}/    parâmetros, texturas.json (editável), prévia do relevo e relatório",
                 f"O STL fica em {self.config.stl_dir}/{name}.stl (pasta só de STL).", "",
                 "Para refazer só a etapa 2 (ex.: depois de editar texturas.json):",
                 f"  python -m img_to_stl --projeto {name} --etapa 2 --auto"]
        with open(os.path.join(proj, "identificacao.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
