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
from vortex_studio.model.overlays import ImageOverlay, Title
from vortex_studio.model.project import Clip, Project, Sequence, Track

FORMAT_VERSION = 1
EXTENSION = ".vortex"


def item_to_dict(item: Any) -> dict:
    data = asdict(item)
    if isinstance(item, Clip):
        data["tipo"] = "clip"
        data["source"] = str(item.source)
    elif isinstance(item, ImageOverlay):
        data["tipo"] = "imagen"
        data["source"] = str(item.source)
    elif isinstance(item, Title):
        data["tipo"] = "texto"
    else:  # pragma: no cover - no debería pasar
        raise TypeError(f"No sé guardar {type(item).__name__}")
    return data


def item_from_dict(data: dict) -> Any:
    data = dict(data)
    kind = data.pop("tipo")

    if kind == "clip":
        color = data.pop("color", None)
        clip = Clip(**data)
        if color:
            clip.color = ColorAdjust(**color)
        return clip
    if kind == "imagen":
        return ImageOverlay(**data)
    if kind == "texto":
        return Title(**data)
    raise ValueError(f"Tipo desconocido en el proyecto: {kind}")


def sequence_to_dict(sequence: Sequence) -> dict:
    return {
        "name": sequence.name,
        "fps": sequence.fps,
        "width": sequence.width,
        "height": sequence.height,
        "tracks": [
            {
                "name": track.name,
                "kind": track.kind,
                "clips": [item_to_dict(c) for c in track.clips],
            }
            for track in sequence.tracks
        ],
    }


def sequence_from_dict(data: dict) -> Sequence:
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
            clips=[item_from_dict(c) for c in track.get("clips", [])],
        )
        for track in data.get("tracks", [])
    ]
    return sequence


def project_to_dict(project: Project) -> dict:
    return {
        "formato": FORMAT_VERSION,
        "name": project.name,
        "sequences": [sequence_to_dict(s) for s in project.sequences],
    }


def project_from_dict(data: dict) -> Project:
    version = data.get("formato", 0)
    if version > FORMAT_VERSION:
        raise ValueError(
            f"El proyecto es de una versión más nueva (formato {version}). "
            f"Esta versión de Vortex Studio entiende hasta la {FORMAT_VERSION}."
        )

    project = Project(name=data.get("name", "Sin título"))
    sequences = [sequence_from_dict(s) for s in data.get("sequences", [])]
    project.sequences = sequences or [Sequence.default()]
    return project


def save_project(project: Project, path: str | Path) -> Path:
    path = Path(path).with_suffix(EXTENSION)
    path.write_text(
        json.dumps(project_to_dict(project), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_project(path: str | Path) -> Project:
    return project_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
