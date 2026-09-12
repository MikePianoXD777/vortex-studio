"""Guardar y abrir proyectos, y sacar copias del estado.

El mismo código sirve para dos cosas: escribir el archivo .vortex y tomar
las instantáneas del historial de deshacer. Son el mismo problema —
convertir la secuencia a datos planos y de regreso— y tener una sola
implementación evita que el archivo guarde algo que deshacer no restaura.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.curves import Curves
from vortex_studio.model.mask import Mask
from vortex_studio.model.media import MediaInfo, library_key
from vortex_studio.model.overlays import ImageOverlay, Title
from vortex_studio.model.project import Clip, Marker, Project, Sequence, Track
from vortex_studio.model.transform import Transform

# 2: máscaras, modos de fusión, curva de color, viñeta y animación de texto.
# 3: el sondeo de los medios guardado en el proyecto.
# Se sube el número para que una versión vieja diga "esto es más nuevo que
# yo" en vez de abrir el proyecto a medias y perder esos ajustes al guardar.
FORMAT_VERSION = 3
EXTENSION = ".vortex"


def _write_path(path: Path, base: Path | None) -> str:
    """Cómo se guarda la ruta de un archivo dentro del proyecto.

    Si el material está junto al proyecto o debajo de él, se guarda relativo
    y con barras normales. Así el proyecto se puede mover de carpeta, pasar
    de Linux a Windows o mandarse junto con sus videos y sigue abriendo.
    Solo se guarda absoluta cuando el archivo vive en otro lado.
    """
    path = Path(path)
    if base is not None:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return path.as_posix()


def _read_path(texto: str, base: Path | None) -> Path:
    path = Path(texto)
    if not path.is_absolute() and base is not None:
        return (base / path).resolve()
    return path


def item_to_dict(item: Any, base: Path | None = None) -> dict:
    data = asdict(item)
    if isinstance(item, Clip):
        data["tipo"] = "clip"
        data["source"] = _write_path(item.source, base)
    elif isinstance(item, ImageOverlay):
        data["tipo"] = "imagen"
        data["source"] = _write_path(item.source, base)
    elif isinstance(item, Title):
        data["tipo"] = "texto"
    else:  # pragma: no cover - no debería pasar
        raise TypeError(f"No sé guardar {type(item).__name__}")
    return data


def _color(raw: dict | None) -> ColorAdjust | None:
    """Reconstruye el color, con su curva adentro.

    `asdict` aplana los dataclasses anidados a diccionarios, así que al
    volver hay que armarlos de nuevo uno por uno. Sin esto, `clip.color`
    quedaba siendo un `dict` y todo lo que le pedía un atributo tronaba —
    pero hasta varios pasos después, que es lo que lo vuelve difícil de
    encontrar.
    """
    if not raw:
        return None
    raw = dict(raw)
    curva = raw.pop("curves", None)
    adjust = ColorAdjust(**raw)
    if curva:
        adjust.curves = Curves(**curva)
    return adjust


def item_from_dict(data: dict, base: Path | None = None) -> Any:
    data = dict(data)
    kind = data.pop("tipo")

    # `transform` y `mask` se sacan para todos porque solo los tienen los
    # que los tienen. `color` NO: en un `Title` ese campo es el color de la
    # letra, una cadena como "#ffcc00", y sacarlo de ahí borraba el color
    # del texto al abrir el proyecto.
    transform = data.pop("transform", None)
    mask = data.pop("mask", None)

    if kind == "clip":
        color = _color(data.pop("color", None))
        data["source"] = _read_path(data["source"], base)
        item = Clip(**data)
        if color:
            item.color = color
    elif kind == "imagen":
        data["source"] = _read_path(data["source"], base)
        item = ImageOverlay(**data)
    elif kind == "texto":
        item = Title(**data)
    else:
        raise ValueError(f"Tipo desconocido en el proyecto: {kind}")

    if transform and hasattr(item, "transform"):
        item.transform = Transform(**transform)
    if mask and hasattr(item, "mask"):
        item.mask = Mask(**mask)
    return item


def sequence_to_dict(sequence: Sequence, base: Path | None = None) -> dict:
    return {
        "name": sequence.name,
        "fps": sequence.fps,
        "width": sequence.width,
        "height": sequence.height,
        "tracks": [
            {
                "name": track.name,
                "kind": track.kind,
                "clips": [item_to_dict(c, base) for c in track.clips],
            }
            for track in sequence.tracks
        ],
        "markers": [asdict(m) for m in sequence.markers],
    }


def sequence_from_dict(data: dict, base: Path | None = None) -> Sequence:
    sequence = Sequence(
        name=data.get("name", "Secuencia 1"),
        fps=data.get("fps", 30.0),
        width=data.get("width", 1920),
        height=data.get("height", 1080),
    )
    sequence.tracks = [
        Track(
            name=track["name"],
            kind=track.get("kind", "video"),
            clips=[item_from_dict(c, base) for c in track.get("clips", [])],
        )
        for track in data.get("tracks", [])
    ]
    sequence.markers = [Marker(**m) for m in data.get("markers", [])]
    return sequence


# --- migraciones ------------------------------------------------------------
#
# Cada función lleva un proyecto de una versión del formato a la siguiente.
# Se aplican en cadena: uno del formato 1 pasa por 1→2 y luego por 2→3.
#
# Así, cada vez que cambie el formato basta con escribir UNA función nueva, y
# los proyectos de cualquier versión anterior siguen abriendo. Sin la cadena,
# cada cambio obligaría a pensar en todas las combinaciones posibles.

def _de_1_a_2(data: dict) -> dict:
    """Máscaras, fusión, curva, viñeta y animación de texto.

    Todos son campos nuevos con valor por omisión, así que no hay nada que
    reescribir: el dataclass los llena solo al cargar.
    """
    return data


def _de_2_a_3(data: dict) -> dict:
    """El caché de sondeos de medios."""
    data.setdefault("media", [])
    return data


MIGRATIONS = {1: _de_1_a_2, 2: _de_2_a_3}


def migrate(data: dict) -> dict:
    """Lleva un proyecto de cualquier formato anterior al actual.

    Un proyecto sin número de formato es anterior a que existiera el número,
    así que cuenta como el 1.
    """
    data = dict(data)
    version = max(1, int(data.get("formato", 1) or 1))

    if version > FORMAT_VERSION:
        raise ValueError(
            f"El proyecto es de una versión más nueva (formato {version}). "
            f"Esta versión de Vortex Studio entiende hasta la {FORMAT_VERSION}."
        )

    while version < FORMAT_VERSION:
        paso = MIGRATIONS.get(version)
        if paso is None:  # pragma: no cover - lo vigila una prueba
            raise ValueError(f"No hay migración del formato {version} al {version + 1}")
        data = paso(data)
        version += 1

    data["formato"] = FORMAT_VERSION
    return data


# --- el proyecto completo ---------------------------------------------------

def media_to_list(library: dict[str, MediaInfo], base: Path | None = None) -> list:
    salida = []
    for info in library.values():
        fila = asdict(info)
        fila["path"] = _write_path(info.path, base)
        salida.append(fila)
    return salida


def media_from_list(rows: list, base: Path | None = None) -> dict[str, MediaInfo]:
    library: dict[str, MediaInfo] = {}
    for fila in rows or []:
        fila = dict(fila)
        fila["path"] = _read_path(fila["path"], base)
        info = MediaInfo(**fila)
        library[library_key(info.path)] = info
    return library


def project_to_dict(project: Project, base: Path | None = None) -> dict:
    return {
        "formato": FORMAT_VERSION,
        "name": project.name,
        "sequences": [sequence_to_dict(s, base) for s in project.sequences],
        "media": media_to_list(project.media, base),
    }


def project_from_dict(data: dict, base: Path | None = None) -> Project:
    data = migrate(data)

    project = Project(name=data.get("name", "Sin título"))
    sequences = [sequence_from_dict(s, base) for s in data.get("sequences", [])]
    project.sequences = sequences or [Sequence.default()]
    project.media = media_from_list(data.get("media", []), base)
    return project


def save_project(project: Project, path: str | Path) -> Path:
    path = Path(path).with_suffix(EXTENSION)
    # `encoding="utf-8"` explícito: en Windows el valor por omisión suele ser
    # cp1252 y los acentos de los nombres se escribirían mal.
    path.write_text(
        json.dumps(project_to_dict(project, path.parent), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_project(path: str | Path) -> Project:
    path = Path(path)
    datos = json.loads(path.read_text(encoding="utf-8"))
    return project_from_dict(datos, path.parent)
