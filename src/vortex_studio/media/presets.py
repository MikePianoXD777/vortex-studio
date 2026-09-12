"""Presets de exportación: los que se usan, no un panel de cuarenta opciones.

Premiere abre la exportación con decenas de parámetros, y casi todos se
dejan como vienen. Aquí hay cuatro, y cada uno dice para qué sirve:

- **Tamaño de la secuencia**: sale igual que lo que ves;
- **H.264 1080p** y **H.264 4K**: los dos tamaños que piden redes y
  pantallas;
- **Solo audio**: el sonido en AAC, para un podcast o para mandarle la
  mezcla a alguien.

"1080p" quiere decir **el lado corto** mide 1080. Así un video vertical de
TikTok sale de 1080 × 1920 y no de 608 × 1080, que es lo que daría leerlo
como "1080 de alto".

Python puro: la cuenta de tamaños se prueba sin codificar nada.
"""

from __future__ import annotations

from dataclasses import dataclass

VIDEO = "video"
AUDIO = "audio"


@dataclass(frozen=True)
class ExportPreset:
    name: str
    kind: str = VIDEO
    short_side: int | None = None       # None: el tamaño de la secuencia
    extension: str = ".mp4"
    description: str = ""


PRESETS = (
    ExportPreset("Tamaño de la secuencia", VIDEO, None, ".mp4",
                 "Igual que el formato de la secuencia."),
    ExportPreset("H.264 1080p", VIDEO, 1080, ".mp4",
                 "Para redes y la mayoría de las pantallas."),
    ExportPreset("H.264 4K", VIDEO, 2160, ".mp4",
                 "Para pantallas grandes o para guardar. Tarda bastante más."),
    ExportPreset("Solo audio (AAC)", AUDIO, None, ".m4a",
                 "Nada más el sonido, con todas las pistas mezcladas."),
)

DEFAULT = PRESETS[0]


def by_name(name: str) -> ExportPreset:
    """El preset con ese nombre; el de siempre si no existe."""
    return next((p for p in PRESETS if p.name == name), DEFAULT)


def output_size(preset: ExportPreset, width: int, height: int) -> tuple[int, int]:
    """El tamaño del archivo para una secuencia de `width` × `height`.

    Se escala manteniendo la proporción, y los dos lados quedan pares: H.264
    no acepta lados impares y el codificador truena.
    """
    if preset.kind == AUDIO:
        return 0, 0

    if preset.short_side is None or min(width, height) <= 0:
        ancho, alto = width, height
    else:
        factor = preset.short_side / min(width, height)
        ancho, alto = round(width * factor), round(height * factor)

    return max(2, ancho - ancho % 2), max(2, alto - alto % 2)
