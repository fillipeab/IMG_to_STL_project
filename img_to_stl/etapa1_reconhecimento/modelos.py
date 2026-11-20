"""Modelos de dados do resultado da etapa 1: regiões, famílias, fronteiras, pontos e o `PlanarMap`.

Coordenadas em mm: x para a direita, y para cima, origem no canto inferior esquerdo da peça.
Fronteira com `region_a == -1` é a moldura externa.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

CLASSE_TRIPLICE = "triplice"      # 3 regiões se encontram
CLASSE_MULTIPLO = "multiplo"      # 4 ou mais regiões se encontram


@dataclass
class Region:
    id: int
    area_mm2: float
    color_rgb: Tuple[int, int, int]
    centroid_mm: Tuple[float, float]
    name: str = ""                 # "03_verde_2": número + cor (+ ordinal entre regiões da mesma cor)
    color_name: str = ""           # "verde"
    family: int = 0                # id da família ("regiões irmãs")
    touches_frame: bool = False
    ignored: bool = False          # região "de fundo": lisa na etapa 2 e fora da base "silhueta"


@dataclass
class Family:
    """Conjunto de regiões de cor parecida (irmãs), vizinhas ou não."""
    id: int
    name: str                      # "familia_01_verde"
    region_ids: List[int]
    color_rgb: Tuple[int, int, int]


@dataclass
class Border:
    id: int
    region_a: int                  # -1 = fora da peça (moldura)
    region_b: int
    points_mm: np.ndarray          # (N, 2)
    closed: bool = False
    outer: bool = False            # fronteira com o exterior (moldura da peça)
    name: str = ""

    @property
    def length_mm(self) -> float:
        d = np.diff(self.points_mm, axis=0)
        return float(np.hypot(d[:, 0], d[:, 1]).sum())


@dataclass
class InterestPoint:
    """Ponto marcado no mapa. `classe`: "triplice", "multiplo" ou a classe dada pelo usuário
    ("capital", "cidade"...). `regions`: nos pontos tríplices, as regiões que se encontram ali."""
    id: int
    xy_mm: Tuple[float, float]
    classe: str = "ponto"
    nome: Optional[str] = None
    regions: Tuple[int, ...] = ()
    shape: Optional[str] = None    # força uma forma ("circle", "square", "triangle"); None = pela classe (etapa 2)

    @property
    def is_junction(self) -> bool:
        return self.classe in (CLASSE_TRIPLICE, CLASSE_MULTIPLO)


@dataclass
class PlanarMap:
    """Resultado da etapa 1."""
    labels: np.ndarray                         # (H, W) int32: id da região de cada pixel
    mm_per_px: float
    regions: List[Region] = field(default_factory=list)
    families: List[Family] = field(default_factory=list)
    borders: List[Border] = field(default_factory=list)
    points: List[InterestPoint] = field(default_factory=list)
    outer_frame: bool = True

    @property
    def size_mm(self) -> Tuple[float, float]:
        h, w = self.labels.shape
        return w * self.mm_per_px, h * self.mm_per_px

    def label_at(self, x_mm, y_mm) -> np.ndarray:
        """Id da região em coordenadas do modelo (fora da imagem usa o pixel mais próximo)."""
        h, w = self.labels.shape
        ix = np.clip((np.asarray(x_mm) / self.mm_per_px).astype(int), 0, w - 1)
        iy = np.clip(((h * self.mm_per_px - np.asarray(y_mm)) / self.mm_per_px).astype(int), 0, h - 1)
        return self.labels[iy, ix]

    def region(self, region_id: int) -> Region:
        return self.regions[region_id]

    def points_of(self, classe: str) -> List[InterestPoint]:
        return [p for p in self.points if p.classe == classe]

    def classes(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for p in self.points:
            out[p.classe] = out.get(p.classe, 0) + 1
        return out

    # ---- resumo ---- #
    def summary(self) -> str:
        w, h = self.size_mm
        cls = ", ".join(f"{n} {c}" for c, n in self.classes().items()) or "nenhum"
        return (f"{len(self.regions)} regiões em {len(self.families)} famílias, {len(self.borders)} fronteiras "
                f"({sum(b.length_mm for b in self.borders):.0f} mm no total), pontos: {cls}; "
                f"peça {w:.1f} x {h:.1f} mm")

    # ---- persistência (resultado.json + rotulos.png) ---- #
    def to_dict(self, include_geometry: bool = True) -> dict:
        out = {
            "size_mm": [round(v, 3) for v in self.size_mm],
            "mm_per_px": self.mm_per_px,
            "outer_frame": self.outer_frame,
            "regioes": [
                {"id": r.id, "nome": r.name, "cor": r.color_name, "rgb": list(r.color_rgb), "familia": r.family,
                 "area_mm2": round(r.area_mm2, 2), "centroide_mm": [round(c, 2) for c in r.centroid_mm],
                 "toca_moldura": r.touches_frame, "fundo": r.ignored}
                for r in self.regions],
            "familias": [{"id": f.id, "nome": f.name, "regioes": f.region_ids, "rgb": list(f.color_rgb)}
                         for f in self.families],
            "fronteiras": [],
            "pontos": [{"id": p.id, "classe": p.classe, "nome": p.nome,
                        "xy_mm": [round(c, 3) for c in p.xy_mm], "regioes": list(p.regions), "forma": p.shape}
                       for p in self.points],
        }
        for b in self.borders:
            item = {"id": b.id, "nome": b.name, "regioes": [b.region_a, b.region_b],
                    "comprimento_mm": round(b.length_mm, 2), "fechada": b.closed, "externa": b.outer}
            if include_geometry:
                item["pontos_mm"] = np.round(b.points_mm, 3).tolist()
            out["fronteiras"].append(item)
        return out

    def save(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "resultado.json"), "w", encoding="utf-8") as f:
            json.dump(self.to_dict(True), f, indent=1, ensure_ascii=False)
        cv2.imwrite(os.path.join(directory, "rotulos.png"), self.labels.astype(np.uint16))

    @classmethod
    def load(cls, directory: str) -> "PlanarMap":
        """Recarrega o resultado gravado por `save` (permite rodar a etapa 2 sem refazer a 1)."""
        with open(os.path.join(directory, "resultado.json"), encoding="utf-8") as f:
            d = json.load(f)
        labels = cv2.imread(os.path.join(directory, "rotulos.png"), cv2.IMREAD_UNCHANGED).astype(np.int32)
        pm = cls(labels=labels, mm_per_px=float(d["mm_per_px"]), outer_frame=bool(d.get("outer_frame", True)))
        pm.regions = [Region(id=r["id"], area_mm2=r["area_mm2"], color_rgb=tuple(r["rgb"]),
                             centroid_mm=tuple(r["centroide_mm"]), name=r["nome"], color_name=r["cor"],
                             family=r["familia"], touches_frame=r["toca_moldura"], ignored=r["fundo"])
                      for r in d["regioes"]]
        pm.families = [Family(f["id"], f["nome"], list(f["regioes"]), tuple(f["rgb"])) for f in d["familias"]]
        pm.borders = [Border(id=b["id"], region_a=b["regioes"][0], region_b=b["regioes"][1],
                             points_mm=np.array(b["pontos_mm"], dtype=float), closed=b["fechada"],
                             outer=b["externa"], name=b["nome"]) for b in d["fronteiras"]]
        pm.points = [InterestPoint(id=p["id"], xy_mm=tuple(p["xy_mm"]), classe=p["classe"], nome=p["nome"],
                                   regions=tuple(p["regioes"]), shape=p["forma"]) for p in d["pontos"]]
        return pm
