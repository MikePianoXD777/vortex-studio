"""Autoguardado: una copia del proyecto por si el programa se cierra de golpe.

La copia **nunca** se escribe encima del proyecto del usuario. Vive en la
carpeta de datos del sistema, y el `.vortex` que él guardó solo cambia
cuando él dice "Guardar". Autoguardar encima es la manera clásica de perder
trabajo: el usuario prueba algo, no le gusta, cierra sin guardar… y el
autoguardado ya lo había escrito.

El ciclo de vida:

- se escribe cada tanto, solo si hay cambios sin guardar;
- se borra al guardar, al abrir otro proyecto y al cerrar normalmente;
- si el programa truena, la copia se queda, y al arrancar se ofrece.

Una copia más vieja que el proyecto guardado no se ofrece: si el usuario
guardó después, la copia ya no tiene nada que salvar.

Guarda rutas **absolutas**. El proyecto normal usa relativas para poder
mover la carpeta, pero la copia vive en otro lado: con relativas, los clips
apuntarían a la carpeta de autoguardado.

Python puro: todo se prueba sin ventana.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from vortex_studio.model.project import Project
from vortex_studio.model.serialize import EXTENSION, project_from_dict, project_to_dict

AUTOSAVE_SECONDS = 30
META = "autoguardado"


def data_dir() -> Path:
    """La carpeta de datos del sistema, o `VORTEX_DATA_DIR`.

    La variable existe para las pruebas: sin ella, el banco dejaría
    autoguardados de mentira que luego se le ofrecerían al usuario real.
    """
    propia = os.environ.get("VORTEX_DATA_DIR")
    if propia:
        return Path(propia)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "VortexStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VortexStudio"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "vortex-studio"


def autosave_dir() -> Path:
    return data_dir() / "autoguardado"


def autosave_path(original: Path | None, session: str) -> Path:
    """Dónde va la copia de este proyecto.

    Un proyecto guardado tiene una sola copia, se abra las veces que se
    abra: el nombre sale de su ruta. Uno sin guardar no tiene ruta, así que
    se distingue por la sesión — dos ventanas con proyectos nuevos no se
    pisan la copia.
    """
    if original is not None:
        ruta = Path(original).expanduser().resolve()
        clave = hashlib.sha1(ruta.as_posix().encode("utf-8")).hexdigest()[:12]
        return autosave_dir() / f"{ruta.stem}-{clave}{EXTENSION}"
    return autosave_dir() / f"sin-titulo-{session}{EXTENSION}"


def write_autosave(project: Project, original: Path | None, session: str) -> Path:
    """Escribe la copia. Primero a un temporal y luego se renombra.

    Si el programa truena justo mientras escribe —que es cuando más falta
    hace la copia— queda la anterior entera en vez de una a medias.
    """
    destino = autosave_path(original, session)
    destino.parent.mkdir(parents=True, exist_ok=True)

    datos = project_to_dict(project, None)          # rutas absolutas, a propósito
    datos[META] = {
        "original": str(Path(original).resolve()) if original is not None else None,
        "fecha": time.time(),
    }

    temporal = destino.with_name(destino.name + ".tmp")
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, destino)
    return destino


@dataclass
class Recovery:
    """Una copia que se puede ofrecer al arrancar."""

    path: Path
    original: Path | None
    saved_at: float
    name: str


def list_recoverable() -> list[Recovery]:
    """Las copias que valen la pena ofrecer, de la más nueva a la más vieja.

    Las que ya no sirven se borran de paso: una copia dañada, o una más vieja
    que su proyecto guardado.
    """
    carpeta = autosave_dir()
    if not carpeta.is_dir():
        return []

    salida: list[Recovery] = []
    for archivo in carpeta.glob(f"*{EXTENSION}"):
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            meta = datos.get(META) or {}
            original = Path(meta["original"]) if meta.get("original") else None
            fecha = float(meta.get("fecha") or archivo.stat().st_mtime)
            nombre = datos.get("name") or archivo.stem
        except (OSError, ValueError, TypeError, AttributeError):
            continue        # dañada: no se ofrece, pero tampoco se borra sin saber

        if original is not None:
            try:
                if original.stat().st_mtime >= fecha:
                    discard(archivo)        # el usuario guardó después
                    continue
            except OSError:
                pass        # el original desapareció: la copia es lo único que queda

        salida.append(Recovery(archivo, original, fecha, nombre))

    salida.sort(key=lambda r: r.saved_at, reverse=True)
    return salida


def load_recovery(recovery: Recovery) -> Project:
    datos = json.loads(recovery.path.read_text(encoding="utf-8"))
    datos.pop(META, None)
    return project_from_dict(datos, None)


def discard(path: Path | None) -> None:
    if path is None:
        return
    try:
        Path(path).unlink()
    except OSError:
        pass
