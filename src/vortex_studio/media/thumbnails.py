"""Miniaturas del panel de medios.

Una miniatura es un cuadro chico del archivo, sacado cerca del inicio pero
no en el cuadro cero: el primer cuadro de muchos videos es negro o un
fundido, y un panel lleno de cuadros negros no ayuda a encontrar nada.

Se guardan en la caché del sistema, con la misma firma que la onda —ruta,
tamaño y fecha del archivo—, para que volver a abrir un proyecto no tenga
que decodificar nada. Este módulo no sabe de Qt: entrega un `Frame` y la
interfaz lo guarda como PNG.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from vortex_studio.media.decoder import HAS_PYAV, Frame
from vortex_studio.media.waveform import cache_dir as _waves_dir

try:
    import av
except ImportError:  # pragma: no cover - depende del entorno
    av = None

VERSION = 1
WIDTH = 192


def thumbnails_dir() -> Path:
    return _waves_dir().parent / "miniaturas"


def thumbnail_path(path: str | Path, width: int = WIDTH) -> Path | None:
    """Dónde va la miniatura de ese archivo. `None` si el archivo no existe."""
    fuente = Path(path)
    try:
        stat = fuente.stat()
    except OSError:
        return None
    firma = (f"{fuente.resolve().as_posix()}|{stat.st_size}|{stat.st_mtime_ns}"
             f"|{width}|{VERSION}")
    return thumbnails_dir() / f"{hashlib.sha1(firma.encode()).hexdigest()}.png"


def pick_time(duration: float) -> float:
    """El instante de la miniatura: al 10 % del video, y nunca después del segundo 2."""
    if duration <= 0:
        return 0.0
    return min(2.0, duration * 0.10)


def extract(path: str | Path, width: int = WIDTH) -> Frame | None:
    """Un cuadro chico del video, o `None` si no se puede leer."""
    if not HAS_PYAV:
        return None
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                return None
            stream = container.streams.video[0]
            duracion = float(container.duration / av.time_base) if container.duration else 0.0
            momento = pick_time(duracion)
            if momento > 0:
                container.seek(int(momento / stream.time_base), stream=stream, backward=True)

            elegido = None
            for frame in container.decode(stream):
                elegido = frame
                cuando = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
                if cuando + 1e-3 >= momento:
                    break
            if elegido is None:
                return None

            alto = max(2, round(width * elegido.height / max(1, elegido.width)))
            alto -= alto % 2
            chico = elegido.reformat(width=width, height=alto, format="rgb24")
            plano = chico.planes[0]
            return Frame(bytes(plano), chico.width, chico.height, plano.line_size)
    except Exception:
        return None
