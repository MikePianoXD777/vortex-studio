"""Subtítulos SRT y WebVTT: leer y escribir.

Los dos formatos son casi el mismo: bloques con un tiempo de entrada, uno de
salida y el texto. Cambian en detalles que rompen un importador ingenuo, y
aquí se cuidan:

- SRT separa los milisegundos con **coma** y VTT con **punto**;
- VTT empieza con `WEBVTT` y permite omitir las horas (`01:02.500`);
- los dos permiten un identificador opcional antes del tiempo, y VTT trae
  ajustes después (`align:start line:90%`) que no son parte del tiempo;
- el texto puede traer etiquetas `<i>`, `<b>` o `{\\an8}`, que se quitan;
- archivos de Windows con `\\r\\n` y con BOM al inicio.

Python puro: entra texto, sale una lista de `Cue`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TIEMPO = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_LINEA_TIEMPO = re.compile(
    r"^\s*(" + _TIEMPO.pattern + r")\s*-->\s*(" + _TIEMPO.pattern + r")")
_ETIQUETAS = re.compile(r"<[^>]+>|\{\\[^}]*\}")


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_time(texto: str) -> float:
    m = _TIEMPO.search(texto)
    if not m:
        raise ValueError(f"tiempo inválido: {texto!r}")
    horas, minutos, segundos, fraccion = m.groups()
    return (int(horas or 0) * 3600 + int(minutos) * 60 + int(segundos)
            + int(fraccion.ljust(3, "0")) / 1000.0)


def format_time(segundos: float, separador: str = ",") -> str:
    total = max(0, int(round(segundos * 1000)))
    horas, resto = divmod(total, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    seg, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{seg:02d}{separador}{ms:03d}"


def parse(texto: str) -> list[Cue]:
    """Lee SRT o VTT: se reconoce solo por el contenido."""
    texto = texto.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for bloque in re.split(r"\n\s*\n", texto):
        lineas = [l for l in bloque.split("\n")]
        indice = next((i for i, l in enumerate(lineas) if "-->" in l), None)
        if indice is None:
            continue            # encabezado WEBVTT, NOTE, STYLE o un número suelto
        m = _LINEA_TIEMPO.match(lineas[indice])
        if not m:
            continue
        partes = lineas[indice].split("-->")
        inicio = parse_time(partes[0])
        fin = parse_time(partes[1])
        cuerpo = "\n".join(_ETIQUETAS.sub("", l).strip() for l in lineas[indice + 1:])
        cuerpo = cuerpo.strip()
        if cuerpo and fin > inicio:
            cues.append(Cue(inicio, fin, cuerpo))
    cues.sort(key=lambda c: c.start)
    return cues


def to_srt(cues: list[Cue]) -> str:
    bloques = []
    for numero, cue in enumerate(sorted(cues, key=lambda c: c.start), start=1):
        bloques.append(f"{numero}\n{format_time(cue.start)} --> {format_time(cue.end)}\n"
                       f"{cue.text.strip()}\n")
    return "\n".join(bloques)


def to_vtt(cues: list[Cue]) -> str:
    bloques = ["WEBVTT\n"]
    for cue in sorted(cues, key=lambda c: c.start):
        bloques.append(f"{format_time(cue.start, '.')} --> {format_time(cue.end, '.')}\n"
                       f"{cue.text.strip()}\n")
    return "\n".join(bloques)


def read_file(path: str | Path) -> list[Cue]:
    return parse(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def write_file(path: str | Path, cues: list[Cue]) -> Path:
    ruta = Path(path)
    texto = to_vtt(cues) if ruta.suffix.lower() == ".vtt" else to_srt(cues)
    ruta.write_text(texto, encoding="utf-8")
    return ruta
