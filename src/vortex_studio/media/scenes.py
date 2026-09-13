"""Detectar cambios de escena: dónde hay un corte dentro de un archivo.

Sirve para el material que ya viene editado —un video descargado, un
render viejo— y se quiere volver a cortar por tomas.

Cada cuadro se reduce a 64 pixeles en gris y se compara con el anterior de
dos maneras: la diferencia promedio pixel a pixel, y la de sus histogramas.
La primera se dispara con un paneo rápido; la segunda no, porque mover la
cámara no cambia los tonos de la escena. Un corte cambia las dos. El
puntaje es el menor de los dos, así que un paneo no cuenta como corte.

Y el umbral es relativo: un corte tiene que destacar contra los cuadros de
alrededor (tres veces la mediana de su vecindad). Con un umbral fijo, una
escena con mucho movimiento se llenaba de cortes falsos y una de tonos
parecidos no daba ninguno.

NumPy puro; no se usa `scdet` de FFmpeg para poder guardar los puntajes y
cambiar la sensibilidad sin volver a leer el archivo.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

import numpy as np

from vortex_studio.media.waveform import cache_dir as _waves_dir

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

VERSION = 1
WIDTH = 64
BINS = 32


def _cache_path(path) -> Path | None:
    fuente = Path(path)
    try:
        stat = fuente.stat()
    except OSError:
        return None
    firma = f"{fuente.resolve().as_posix()}|{stat.st_size}|{stat.st_mtime_ns}|{WIDTH}|{VERSION}"
    return _waves_dir().parent / "escenas" / f"{hashlib.sha1(firma.encode()).hexdigest()}.npy"


def scores(path: str | Path, progress: Callable[[int, int], bool] | None = None) -> np.ndarray:
    """Filas `[tiempo, puntaje]` por cuadro, del segundo en adelante. Guardado en caché."""
    destino = _cache_path(path)
    if destino is not None and destino.exists():
        try:
            return np.load(destino)
        except (OSError, ValueError):
            pass
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado")

    filas = []
    anterior = None
    hist_anterior = None
    with av.open(str(path)) as contenedor:
        if not contenedor.streams.video:
            raise ValueError("El archivo no tiene video.")
        flujo = contenedor.streams.video[0]
        flujo.thread_type = "AUTO"
        total = max(1, int((contenedor.duration or 0) / av.time_base * 1000))
        for frame in contenedor.decode(flujo):
            alto = max(2, round(WIDTH * frame.height / max(1, frame.width)))
            gris = frame.reformat(width=WIDTH, height=alto, format="gray").to_ndarray()[:, :WIDTH]
            gris = gris.astype(np.float32)
            hist = np.histogram(gris, bins=BINS, range=(0, 256))[0] / gris.size
            cuando = float(frame.pts * flujo.time_base) if frame.pts is not None else 0.0
            if anterior is not None:
                pixeles = float(np.abs(gris - anterior).mean() / 255.0)
                tonos = float(np.abs(hist - hist_anterior).sum() / 2.0)
                filas.append((cuando, min(pixeles * 4.0, tonos)))
            anterior, hist_anterior = gris, hist
            if progress is not None and not progress(min(total, int(cuando * 1000)), total):
                from vortex_studio.media.encoder import Cancelled
                raise Cancelled()

    datos = np.array(filas, dtype=np.float64).reshape(-1, 2)
    if destino is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(destino.stem + f".{os.getpid()}.parte.npy")
        np.save(temporal, datos)
        os.replace(temporal, destino)
    return datos


def cuts(datos: np.ndarray, sensitivity: float = 50.0, min_gap: float = 0.5) -> list[float]:
    """Los instantes de corte. `sensitivity` de 0 a 100: más alto, más cortes."""
    if len(datos) == 0:
        return []
    puntaje = datos[:, 1]
    umbral = 0.45 - 0.35 * max(0.0, min(100.0, sensitivity)) / 100.0
    radio = 15
    relleno = np.pad(puntaje, radio, mode="edge")
    vecindad = np.lib.stride_tricks.sliding_window_view(relleno, 2 * radio + 1)
    mediana = np.median(vecindad, axis=1)

    salida: list[float] = []
    for indice in np.where((puntaje > umbral) & (puntaje > 3.0 * mediana))[0]:
        cuando = float(datos[indice, 0])
        if salida and cuando - salida[-1] < min_gap:
            continue
        salida.append(round(cuando, 4))
    return salida
