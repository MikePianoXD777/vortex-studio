"""Proxies: copias livianas de 540p para editar material pesado.

Un 4K en H.265 no se reproduce fluido en una laptop, por más hilo aparte
que tenga el decodificador. La salida de siempre —la de Premiere y Resolve—
es editar sobre una copia chica y exportar desde el original. Aquí:

- la copia mide **540 del lado corto** y guarda la proporción;
- se codifica en H.264 con un keyframe **cada 15 cuadros**: saltar a
  cualquier punto cuesta decodificar a lo mucho 14 cuadros, y es eso —no
  la resolución— lo que hace que arrastrar el playhead se sienta inmediato;
- conserva las marcas de tiempo del original, así el segundo 3.2 del proxy
  es el segundo 3.2 del video;
- solo imagen: el audio sale siempre del original.

Se escribe primero a un archivo temporal y se renombra al terminar. Un
proxy a medias con el nombre bueno se usaría como si estuviera completo.
Viven en la caché: borrarlos no pierde nada, se vuelven a crear.
"""

from __future__ import annotations

import hashlib
import os
from fractions import Fraction
from pathlib import Path
from typing import Callable

from vortex_studio.media.decoder import rotation_of
from vortex_studio.media.encoder import Cancelled
from vortex_studio.media.waveform import cache_dir as _waves_dir

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

VERSION = 1
SHORT_SIDE = 540
GOP = 15


def proxies_dir() -> Path:
    return _waves_dir().parent / "proxies"


def proxy_path(path: str | Path) -> Path | None:
    """Dónde va el proxy de ese archivo. `None` si el original no existe.

    La firma lleva tamaño y fecha: si alguien reemplaza el video por otro
    con el mismo nombre, el proxy viejo deja de valer solo.
    """
    fuente = Path(path)
    try:
        stat = fuente.stat()
    except OSError:
        return None
    firma = (f"{fuente.resolve().as_posix()}|{stat.st_size}|{stat.st_mtime_ns}"
             f"|{SHORT_SIDE}|{VERSION}")
    return proxies_dir() / f"{hashlib.sha1(firma.encode()).hexdigest()}.mp4"


def existing_proxy(path: str | Path) -> Path | None:
    destino = proxy_path(path)
    return destino if destino is not None and destino.exists() else None


def proxy_size(width: int, height: int, short_side: int = SHORT_SIDE) -> tuple[int, int]:
    """El tamaño del proxy: 540 del lado corto, pares, y nunca más grande que el original."""
    if width <= 0 or height <= 0:
        return 0, 0
    factor = min(1.0, short_side / min(width, height))
    ancho, alto = round(width * factor), round(height * factor)
    return max(2, ancho - ancho % 2), max(2, alto - alto % 2)


def needs_proxy(width: int, height: int, short_side: int = SHORT_SIDE) -> bool:
    """Un video que ya es chico no gana nada con un proxy."""
    return min(width, height) > short_side


def make_proxy(path: str | Path,
               progress: Callable[[int, int], bool] | None = None) -> Path:
    """Crea el proxy y devuelve su ruta. Si ya existía, no hace nada.

    `progress` recibe milisegundos (hechos, total) y devuelve False para
    cancelar; al cancelar no queda ningún archivo.
    """
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado: no se pueden crear proxies")

    destino = proxy_path(path)
    if destino is None:
        raise FileNotFoundError(str(path))
    if destino.exists():
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.stem + f".{os.getpid()}.parte.mp4")

    try:
        with av.open(str(path)) as entrada:
            if not entrada.streams.video:
                raise ValueError("El archivo no tiene video")
            origen = entrada.streams.video[0]
            origen.thread_type = "AUTO"
            ancho, alto = proxy_size(origen.codec_context.width, origen.codec_context.height)
            # Un vertical de celular viene acostado con una marca de giro. El
            # proxy se hace igual de acostado, así que hay que copiarle la
            # marca: sin ella el proxy se vería de lado y el original derecho.
            giro = rotation_of(entrada, origen)
            total = max(1, int((entrada.duration or 0) / av.time_base * 1000))
            base = origen.time_base or Fraction(1, 1000)

            with av.open(str(temporal), mode="w") as salida:
                flujo = salida.add_stream("libx264", rate=origen.average_rate or 30)
                flujo.width, flujo.height = ancho, alto
                flujo.pix_fmt = "yuv420p"
                flujo.time_base = base
                flujo.codec_context.time_base = base
                flujo.options = {"preset": "veryfast", "crf": "23", "g": str(GOP),
                                 "bf": "0"}
                if giro:
                    flujo.set_display_rotation(giro)

                ultimo = -1
                for frame in entrada.decode(origen):
                    if frame.pts is None or frame.pts <= ultimo:
                        continue    # marcas repetidas: el muxer las rechaza
                    ultimo = frame.pts
                    chico = frame.reformat(width=ancho, height=alto, format="yuv420p")
                    chico.pts, chico.time_base = frame.pts, base
                    for paquete in flujo.encode(chico):
                        salida.mux(paquete)
                    if progress is not None:
                        hecho = int(frame.pts * base * 1000)
                        if not progress(min(hecho, total), total):
                            raise Cancelled()
                for paquete in flujo.encode():
                    salida.mux(paquete)
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return destino
