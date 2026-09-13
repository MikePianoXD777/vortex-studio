"""Tramos para exportar: entre marcadores.

"Exportar por marcadores" es cortar el video en capítulos sin tener que
marcar entrada y salida a mano cada vez: cada marcador empieza un tramo que
llega hasta el siguiente, y el último hasta el final. Si el primer marcador
no está en el inicio, lo de antes también sale, como "Inicio".

Python puro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ExportRange:
    name: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def marker_ranges(sequence, start: float = 0.0, end: float | None = None,
                  minimum: float = 0.05) -> list[ExportRange]:
    """Los tramos entre marcadores dentro de `[start, end)`."""
    fin = sequence.duration if end is None else end
    marcadores = sorted((m for m in sequence.markers if start - 1e-6 <= m.time < fin - 1e-6),
                        key=lambda m: m.time)
    if not marcadores:
        return []
    tramos: list[ExportRange] = []
    if marcadores[0].time - start > minimum:
        tramos.append(ExportRange("Inicio", start, marcadores[0].time))
    for numero, (marcador, siguiente) in enumerate(zip(marcadores, marcadores[1:] + [None]), 1):
        hasta = siguiente.time if siguiente is not None else fin
        if hasta - marcador.time > minimum:
            tramos.append(ExportRange(marcador.name or f"Marcador {numero}", marcador.time, hasta))
    return tramos


def safe_filename(texto: str, limite: int = 60) -> str:
    """Un nombre de archivo que sirve en Linux y en Windows."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip().strip(".")
    return (limpio or "tramo")[:limite]


def numbered_names(tramos: list[ExportRange]) -> list[str]:
    ancho = max(2, len(str(len(tramos))))
    return [f"{i:0{ancho}d} - {safe_filename(t.name)}" for i, t in enumerate(tramos, 1)]
