"""Versiones guardadas del proyecto, y el candado de quién lo tiene abierto.

**Versiones.** "Guardar versión" deja una copia con nombre en una carpeta
junto al proyecto (`proyecto.versiones/`). Sirve para volver a como estaba
antes de un cambio grande, y es lo que hace posible fusionar: cada copia
recuerda de qué versión salió (`version_base`), y dos copias que salieron de
la misma se pueden juntar a tres vías (ver `model/merge.py`).

Las versiones van en una carpeta junto al proyecto y no dentro del archivo:
el `.vortex` sigue pesando lo mismo, y la carpeta se puede mandar o no.

**Candado.** Al abrir un proyecto se deja un archivo `.proyecto.vortex.lock`
con quién lo tiene abierto, desde qué equipo y cuándo. Si otra persona lo
abre en una carpeta compartida, se le avisa en vez de dejar que los dos
guarden encima del otro. El candado es un aviso, no una cerradura: un
equipo que se apagó de golpe deja el suyo, y uno viejo del mismo equipo cuyo
proceso ya no existe se toma como abandonado.

Python puro, sin Qt.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

STALE_SECONDS = 24 * 3600


@dataclass
class Version:
    id: str
    label: str
    saved_at: float
    author: str
    path: Path


def versions_dir(project_path: str | Path) -> Path:
    ruta = Path(project_path)
    return ruta.with_name(ruta.stem + ".versiones")


def user_name() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "alguien"


def host_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "otro equipo"


def save_version(project, project_path: str | Path, label: str = "") -> Version:
    """Guarda una copia con nombre y deja al proyecto apuntando a ella como su base."""
    from vortex_studio.model.serialize import project_to_dict

    ruta = Path(project_path)
    carpeta = versions_dir(ruta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex[:12]
    ahora = time.time()
    project.version_base = ident
    datos = project_to_dict(project, ruta.parent)
    datos["version"] = {"id": ident, "label": label or time.strftime("%d/%m %H:%M"),
                        "fecha": ahora, "autor": user_name()}
    destino = carpeta / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ahora))}-{ident}.vortex"
    temporal = destino.with_name(destino.name + ".tmp")
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, destino)
    return Version(ident, datos["version"]["label"], ahora, datos["version"]["autor"], destino)


def list_versions(project_path: str | Path) -> list[Version]:
    """Las versiones guardadas, de la más nueva a la más vieja. Las dañadas no salen."""
    carpeta = versions_dir(project_path)
    salida = []
    for archivo in carpeta.glob("*.vortex") if carpeta.is_dir() else []:
        try:
            meta = json.loads(archivo.read_text(encoding="utf-8"))["version"]
            salida.append(Version(str(meta["id"]), str(meta.get("label", "")),
                                  float(meta.get("fecha", 0.0)), str(meta.get("autor", "")),
                                  archivo))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    salida.sort(key=lambda v: v.saved_at, reverse=True)
    return salida


def find_version(project_path: str | Path, ident: str) -> Version | None:
    return next((v for v in list_versions(project_path) if v.id == ident), None) if ident else None


def version_data(version: Version, project_path: str | Path) -> dict:
    """Los datos de la versión, con las rutas como si estuviera junto al proyecto."""
    datos = json.loads(version.path.read_text(encoding="utf-8"))
    datos.pop("version", None)
    return datos


def load_version(version: Version, project_path: str | Path):
    from vortex_studio.model.serialize import project_from_dict

    return project_from_dict(version_data(version, project_path), Path(project_path).parent)


# --- candado ------------------------------------------------------------------------

def lock_path(project_path: str | Path) -> Path:
    ruta = Path(project_path)
    return ruta.with_name(f".{ruta.name}.lock")


@dataclass
class LockInfo:
    user: str
    host: str
    pid: int
    session: str
    since: float

    @property
    def description(self) -> str:
        return (f"{self.user} en {self.host} desde las "
                f"{time.strftime('%H:%M del %d/%m', time.localtime(self.since))}")


def read_lock(project_path: str | Path) -> LockInfo | None:
    try:
        datos = json.loads(lock_path(project_path).read_text(encoding="utf-8"))
        return LockInfo(str(datos["usuario"]), str(datos["equipo"]), int(datos["pid"]),
                        str(datos["sesion"]), float(datos["desde"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def is_stale(info: LockInfo, now: float | None = None) -> bool:
    """¿Abandonado? Muy viejo, o del mismo equipo con un proceso que ya no existe."""
    ahora = time.time() if now is None else now
    if ahora - info.since > STALE_SECONDS:
        return True
    return info.host == host_name() and not _alive(info.pid)


def acquire(project_path: str | Path, session: str) -> LockInfo | None:
    """Toma el candado. Devuelve quién lo tiene si es de otro y sigue vigente."""
    actual = read_lock(project_path)
    if actual is not None and actual.session != session and not is_stale(actual):
        return actual
    datos = {"usuario": user_name(), "equipo": host_name(), "pid": os.getpid(),
             "sesion": session, "desde": time.time()}
    try:
        lock_path(project_path).write_text(json.dumps(datos), encoding="utf-8")
    except OSError:
        pass            # una carpeta de solo lectura: se trabaja sin candado
    return None


def release(project_path: str | Path | None, session: str) -> bool:
    """Suelta el candado si es de esta sesión."""
    if project_path is None:
        return False
    actual = read_lock(project_path)
    if actual is None or actual.session != session:
        return False
    try:
        lock_path(project_path).unlink()
    except OSError:
        return False
    return True
