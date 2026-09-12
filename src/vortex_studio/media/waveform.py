"""Forma de onda: mínimo y máximo por cubo, calculados una vez y guardados.

Para dibujar la onda hay que decodificar el audio completo, y con un archivo
de una hora eso son varios segundos. Antes se hacía cada vez que se abría el
proyecto, y se guardaba solo el pico absoluto de cada cubo.

Ahora se guardan dos cosas por cubo, **el mínimo y el máximo**, en un
archivo `.npy` en la carpeta de caché del sistema. Con los dos se dibuja la
onda con su forma real —una voz no es simétrica arriba y abajo— y en vez de
decodificar otra vez se carga el arreglo del disco en milisegundos.

El nombre del archivo de caché sale de la ruta, el tamaño, la fecha y la
resolución de la onda: si el audio cambia, la onda vieja simplemente deja de
encontrarse y se calcula una nueva.

NumPy aquí y no bucles de Python: una hora de audio a 8 kHz son 28 millones
de muestras, y sacar mínimo y máximo por bloque en Python tardaría más que
decodificarlas.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np

try:
    import av
    from av.audio.resampler import AudioResampler

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

RATE = 8000       # frecuencia a la que se mide la onda
VERSION = 1       # sube si cambia la manera de calcular: invalida las ondas viejas


def empty() -> np.ndarray:
    return np.zeros((2, 0), dtype=np.float32)


def cache_dir() -> Path:
    """La carpeta de caché del sistema, o la que diga `VORTEX_CACHE_DIR`.

    La variable existe para las pruebas: sin ella, correr el banco llenaría
    la caché real del usuario de ondas de videos de prueba.
    """
    propia = os.environ.get("VORTEX_CACHE_DIR")
    if propia:
        base = Path(propia)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) \
            / "VortexStudio" / "cache"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "VortexStudio"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "vortex-studio"
    return base / "ondas"


def cache_path(path: str | Path, per_second: int) -> Path | None:
    """Dónde va la onda de ese archivo. `None` si el archivo no existe."""
    source = Path(path)
    try:
        stat = source.stat()
    except OSError:
        return None
    firma = (f"{source.resolve().as_posix()}|{stat.st_size}|{stat.st_mtime_ns}"
             f"|{per_second}|{VERSION}")
    return cache_dir() / (hashlib.sha1(firma.encode("utf-8")).hexdigest() + ".npy")


def compute(path: str | Path, per_second: int = 60) -> np.ndarray:
    """Decodifica el audio y saca mínimo y máximo por cubo.

    Devuelve un arreglo de 2 × n en float32, normalizado de -1 a 1: la fila
    0 son los mínimos y la 1 los máximos. Sin audio, o si el archivo no se
    puede leer, un arreglo vacío — un clip sin onda no es un error.
    """
    if not HAS_PYAV:
        return empty()

    try:
        container = av.open(str(path))
        stream = container.streams.audio[0]
    except Exception:
        return empty()

    resampler = AudioResampler(format="s16", layout="mono", rate=RATE)
    trozos: list[np.ndarray] = []

    def guardar(chunks) -> None:
        for chunk in chunks:
            # El plano puede traer relleno al final: se corta a las muestras
            # reales, o la onda se llena de ceros fantasma.
            trozos.append(chunk.to_ndarray().reshape(-1)[: chunk.samples])

    try:
        for frame in container.decode(stream):
            guardar(resampler.resample(frame))
        guardar(resampler.resample(None))      # lo que quedó en el resampler
    except Exception:
        pass        # un archivo truncado da la onda de lo que sí se pudo leer
    finally:
        container.close()

    if not trozos:
        return empty()

    muestras = np.concatenate(trozos).astype(np.float32) / 32768.0
    cubo = max(1, RATE // max(1, per_second))
    cubos = -(-len(muestras) // cubo)                   # redondeo hacia arriba
    muestras = np.pad(muestras, (0, cubos * cubo - len(muestras)))
    bloques = muestras.reshape(cubos, cubo)
    return np.stack([bloques.min(axis=1), bloques.max(axis=1)]).astype(np.float32)


def load_or_compute(path: str | Path, per_second: int = 60) -> np.ndarray:
    """La onda del disco si ya estaba; si no, se calcula y se guarda.

    Se escribe primero a un temporal y luego se renombra: si dos hilos
    calculan la misma onda a la vez, o se va la luz a medio guardar, nunca
    queda un `.npy` a medias que luego truene al cargarlo.
    """
    destino = cache_path(path, per_second)

    if destino is not None and destino.exists():
        try:
            datos = np.load(destino, allow_pickle=False)
            if datos.ndim == 2 and datos.shape[0] == 2:
                return datos
        except Exception:
            pass    # caché corrupto: se recalcula y se sobreescribe

    datos = compute(path, per_second)

    if destino is not None and datos.shape[1] > 0:
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporal = destino.with_name(f"{destino.stem}.{os.getpid()}.tmp.npy")
            np.save(temporal, datos, allow_pickle=False)
            os.replace(temporal, destino)
        except OSError:
            pass    # sin caché en disco se sigue viendo, solo más lento

    return datos
