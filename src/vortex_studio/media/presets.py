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

import json
from dataclasses import asdict, dataclass
from pathlib import Path

VIDEO = "video"
AUDIO = "audio"


@dataclass(frozen=True)
class ExportPreset:
    name: str
    kind: str = VIDEO
    short_side: int | None = None       # None: el tamaño de la secuencia
    extension: str = ".mp4"
    description: str = ""
    quality: str | None = None      # None: la que se elija en el diálogo
    fps: float | None = None        # None: la de la secuencia
    user: bool = False              # lo guardó el usuario: se puede borrar


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


# --- presets del usuario --------------------------------------------------------
#
# Los cuatro de fábrica cubren lo común, pero cada quien tiene los suyos: el
# vertical a 60 fps para TikTok, el borrador para mandar a revisión. Se guardan
# en `presets.json`, junto a los atajos, y aparecen en la misma lista.

def presets_path() -> Path:
    from vortex_studio.ui.shortcuts import config_dir
    return config_dir() / "presets.json"


def user_presets() -> list[ExportPreset]:
    try:
        filas = json.loads(presets_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    salida = []
    nombres_fabrica = {p.name for p in PRESETS}
    for fila in filas if isinstance(filas, list) else []:
        try:
            preset = ExportPreset(**{**fila, "user": True})
        except TypeError:
            continue            # un preset de una versión futura con campos raros
        if preset.name not in nombres_fabrica:
            salida.append(preset)
    return salida


def all_presets() -> list[ExportPreset]:
    return list(PRESETS) + user_presets()


def save_user_preset(preset: ExportPreset) -> ExportPreset:
    """Guarda o reemplaza un preset propio. Los de fábrica no se pisan."""
    nombre = preset.name.strip()
    if not nombre:
        raise ValueError("El preset necesita nombre.")
    if nombre in {p.name for p in PRESETS}:
        raise ValueError(f"«{nombre}» es un preset de fábrica; ponle otro nombre.")
    nuevo = ExportPreset(**{**asdict(preset), "name": nombre, "user": True})
    lista = [p for p in user_presets() if p.name != nombre] + [nuevo]
    _write(lista)
    return nuevo


def delete_user_preset(name: str) -> bool:
    lista = user_presets()
    quedan = [p for p in lista if p.name != name]
    if len(quedan) == len(lista):
        return False
    _write(quedan)
    return True


def _write(lista: list[ExportPreset]) -> None:
    ruta = presets_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    filas = [{k: v for k, v in asdict(p).items() if k != "user"} for p in lista]
    ruta.write_text(json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8")


def by_name(name: str) -> ExportPreset:
    """El preset con ese nombre, de fábrica o propio; el de siempre si no existe."""
    return next((p for p in all_presets() if p.name == name), DEFAULT)


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
