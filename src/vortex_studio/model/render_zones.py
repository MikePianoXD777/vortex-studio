"""Zonas de render: la barra verde, amarilla y roja de Premiere.

La línea de tiempo se parte en **zonas** por cada punto donde algo empieza o
termina. Dentro de una zona no cambia qué se pinta, así que se puede decir
de una vez qué tan pesada es y, si ya se renderizó, reproducirla desde el
archivo en vez de componerla cuadro por cuadro.

- **Sin color**: un solo clip limpio. Se decodifica y ya.
- **Amarillo**: textos, imágenes, transformación, velocidad. Se compone,
  pero es barato.
- **Rojo**: corrección de color, LUT, llave, estabilización, capa de ajuste,
  secuencia anidada, máscara, fusión o varias capas encimadas. Es lo que
  conviene renderizar.
- **Verde**: ya renderizada, y la firma de la zona no cambió.

La **firma** es lo que hace que la caché nunca mienta: un hash de todo lo que
vive en la zona, con el tamaño y la fecha de cada archivo que usa. Cambias
un deslizador y la firma cambia; la zona vuelve a rojo sola.

Python puro.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

NONE, LIGHT, HEAVY = 0, 1, 2


@dataclass
class Zone:
    start: float
    end: float
    level: int
    signature: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end


def cut_points(sequence) -> list[float]:
    puntos = {0.0, round(sequence.duration, 6)}
    for track in sequence.tracks:
        if track.kind == "audio":
            continue
        for item in track.clips:
            puntos.add(round(item.start, 6))
            puntos.add(round(item.end, 6))
            cruce = getattr(item, "dissolve", 0.0)
            if cruce > 0:
                puntos.add(round(item.start - cruce / 2, 6))
                puntos.add(round(item.start + cruce / 2, 6))
    return sorted(p for p in puntos if 0.0 <= p <= sequence.duration + 1e-9)


def _items_in(sequence, start: float, end: float) -> list:
    salida = []
    for track in sequence.tracks:
        if track.kind == "audio" or not track.enabled:
            continue
        for item in track.clips:
            margen = getattr(item, "dissolve", 0.0) / 2
            if item.start - margen < end - 1e-9 and item.end + margen > start + 1e-9:
                salida.append((track, item))
    return salida


def level_of(sequence, start: float, end: float) -> int:
    from vortex_studio.model.overlays import AdjustmentLayer, ImageOverlay, Title
    from vortex_studio.model.project import Clip

    elementos = _items_in(sequence, start, end)
    videos = [i for _, i in elementos if isinstance(i, (Clip, AdjustmentLayer))]
    nivel = NONE
    if len(videos) > 1:
        return HEAVY
    for _, item in elementos:
        if isinstance(item, AdjustmentLayer) or getattr(item, "sequence_id", ""):
            return HEAVY
        if isinstance(item, (Title, ImageOverlay)):
            nivel = max(nivel, LIGHT)
            if isinstance(item, ImageOverlay) and (not item.mask.is_off or item.blend != "Normal"):
                return HEAVY
            continue
        if isinstance(item, Clip):
            if not item.color.is_neutral or item.chroma.is_on or getattr(item, "stabilize", 0) > 0:
                return HEAVY
            if not item.mask.is_off or item.blend != "Normal" or item.dissolve > 0:
                return HEAVY
            if item.anim:
                return HEAVY
            # Cuadros intermedios en cámara lenta: dos decodificaciones por
            # cuadro, o flujo óptico, que tarda más de un segundo cada uno.
            if getattr(item, "interpolation", "Cuadro más cercano") != "Cuadro más cercano" \
                    and 0 < item.speed < 1.0:
                return HEAVY
            if not item.transform.is_neutral or item.speed != 1.0 or item.fade_in or item.fade_out:
                nivel = max(nivel, LIGHT)
    return nivel


def _file_stamp(path) -> list:
    try:
        stat = Path(path).stat()
        return [str(path), stat.st_size, stat.st_mtime_ns]
    except OSError:
        return [str(path), 0, 0]


def signature_of(sequence, start: float, end: float, extra=None) -> str:
    from vortex_studio.model.serialize import item_to_dict

    cuerpo = {
        "formato": [sequence.width, sequence.height, sequence.fps],
        "tramo": [round(start, 6), round(end, 6)],
        "elementos": [],
        "extra": extra,
    }
    for track, item in _items_in(sequence, start, end):
        datos = item_to_dict(item)
        archivos = [_file_stamp(item.source)] if getattr(item, "source", None) and \
            str(item.source) not in ("", ".") else []
        cuerpo["elementos"].append([sequence.tracks.index(track), datos, archivos])
    texto = json.dumps(cuerpo, sort_keys=True, default=str)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def zones(sequence, extra=None) -> list[Zone]:
    puntos = cut_points(sequence)
    salida = []
    for a, b in zip(puntos, puntos[1:]):
        if b - a < 1e-6:
            continue
        salida.append(Zone(a, b, level_of(sequence, a, b), signature_of(sequence, a, b, extra)))
    return salida


def zone_at(lista: list[Zone], t: float) -> Zone | None:
    return next((z for z in lista if z.contains(t)), None)
