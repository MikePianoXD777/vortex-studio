"""Estabilización: quitar el temblor de una toma a mano.

Se hace en dos pasos, y el primero se guarda:

1. **Análisis**, una sola vez por archivo: cuánto se movió la imagen de cada
   cuadro al siguiente. Se mide con **correlación de fase** sobre cuadros
   reducidos a 160 pixeles en gris: la FFT de dos cuadros seguidos, su
   producto normalizado y de regreso; el pico dice el desplazamiento. Es
   NumPy puro y cuesta menos de un milisegundo por cuadro. Se acumula en una
   trayectoria y se guarda en la caché, como la onda.
2. **Corrección**, en cada cuadro que se pinta: la trayectoria se suaviza
   con un promedio móvil y la diferencia entre la suave y la real es lo que
   hay que mover la imagen. Un poco de zoom tapa las orillas que quedan
   descubiertas.

Hacerlo así —y no con el filtro `deshake` de FFmpeg, que sí viene— es lo que
permite saltar a cualquier cuadro: `deshake` depende de los cuadros
anteriores, así que el preview después de un salto y la exportación en orden
darían imágenes distintas. Con la trayectoria guardada, el cuadro 300 se
corrige igual llegues como llegues.
"""

from __future__ import annotations

import hashlib
import os
import threading
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
WIDTH = 160
MAX_ZOOM = 1.25


def analysis_dir() -> Path:
    return _waves_dir().parent / "estabilizacion"


def analysis_path(path: str | Path) -> Path | None:
    fuente = Path(path)
    try:
        stat = fuente.stat()
    except OSError:
        return None
    firma = f"{fuente.resolve().as_posix()}|{stat.st_size}|{stat.st_mtime_ns}|{WIDTH}|{VERSION}"
    return analysis_dir() / f"{hashlib.sha1(firma.encode()).hexdigest()}.npy"


# --- medir -------------------------------------------------------------------

def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Cuántos pixeles hay que mover `a` para que caiga sobre `b`, en (x, y).

    Con ajuste parabólico alrededor del pico, para tener fracciones de
    pixel: a 160 de ancho, un pixel entero son casi 12 de un video de 1080p.
    """
    alto, ancho = a.shape
    ventana = np.outer(np.hanning(alto), np.hanning(ancho))
    fa = np.fft.fft2((a - a.mean()) * ventana)
    fb = np.fft.fft2((b - b.mean()) * ventana)
    cruzado = fb * np.conj(fa)
    cruzado /= np.maximum(np.abs(cruzado), 1e-9)
    correlacion = np.real(np.fft.ifft2(cruzado))
    py, px = np.unravel_index(int(np.argmax(correlacion)), correlacion.shape)

    def fino(c_menos, c_centro, c_mas):
        denominador = c_menos - 2 * c_centro + c_mas
        return 0.0 if abs(denominador) < 1e-12 else 0.5 * (c_menos - c_mas) / denominador

    dx = px + fino(correlacion[py, (px - 1) % ancho], correlacion[py, px],
                   correlacion[py, (px + 1) % ancho])
    dy = py + fino(correlacion[(py - 1) % alto, px], correlacion[py, px],
                   correlacion[(py + 1) % alto, px])
    if dx > ancho / 2:
        dx -= ancho
    if dy > alto / 2:
        dy -= alto
    return float(dx), float(dy)


def analyze(path: str | Path,
            progress: Callable[[int, int], bool] | None = None) -> np.ndarray:
    """La trayectoria del archivo: filas `[tiempo, x, y]`, en fracciones del cuadro.

    `progress(hecho, total)` en milisegundos; devuelve False para cancelar.
    """
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado")
    filas: list[tuple[float, float, float]] = []
    anterior = None
    x = y = 0.0
    with av.open(str(path)) as contenedor:
        if not contenedor.streams.video:
            raise ValueError("El archivo no tiene video que estabilizar.")
        flujo = contenedor.streams.video[0]
        flujo.thread_type = "AUTO"
        total = max(1, int((contenedor.duration or 0) / av.time_base * 1000))
        for frame in contenedor.decode(flujo):
            alto = max(2, round(WIDTH * frame.height / max(1, frame.width)))
            gris = frame.reformat(width=WIDTH, height=alto, format="gray").to_ndarray()
            gris = gris[:, :WIDTH].astype(np.float32)
            cuando = float(frame.pts * flujo.time_base) if frame.pts is not None else len(filas) / 30
            if anterior is not None:
                dx, dy = phase_shift(anterior, gris)
                x += dx / gris.shape[1]
                y += dy / gris.shape[0]
            filas.append((cuando, x, y))
            anterior = gris
            if progress is not None and not progress(min(total, int(cuando * 1000)), total):
                from vortex_studio.media.encoder import Cancelled
                raise Cancelled()
    return np.array(filas, dtype=np.float64).reshape(-1, 3)


def load_or_analyze(path: str | Path, progress=None) -> np.ndarray:
    destino = analysis_path(path)
    if destino is not None and destino.exists():
        try:
            return np.load(destino)
        except (OSError, ValueError):
            pass
    datos = analyze(path, progress)
    if destino is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_name(destino.stem + f".{os.getpid()}.parte.npy")
        np.save(temporal, datos)
        os.replace(temporal, destino)
    return datos


# --- corregir ------------------------------------------------------------------

def smoothed(trayectoria: np.ndarray, radio: int) -> np.ndarray:
    """Promedio móvil de x e y, con las orillas extendidas."""
    if radio < 1 or len(trayectoria) < 3:
        return trayectoria[:, 1:3].copy()
    salida = np.empty((len(trayectoria), 2))
    nucleo = np.ones(2 * radio + 1) / (2 * radio + 1)
    for columna in (1, 2):
        extendida = np.pad(trayectoria[:, columna], radio, mode="edge")
        salida[:, columna - 1] = np.convolve(extendida, nucleo, mode="valid")
    return salida


def radius_for(strength: float, fps: float = 30.0) -> int:
    """Fuerza 100 = un segundo de promedio: quita el pulso sin quitar el paneo."""
    return max(1, int(round(max(0.0, min(100.0, strength)) / 100.0 * fps)))


def corrections(trayectoria: np.ndarray, strength: float, fps: float = 30.0) -> np.ndarray:
    """Por cuadro, cuánto mover la imagen `(dx, dy)` para dejarla quieta."""
    if strength <= 0 or len(trayectoria) == 0:
        return np.zeros((len(trayectoria), 2))
    return smoothed(trayectoria, radius_for(strength, fps)) - trayectoria[:, 1:3]


def zoom_for(correcciones: np.ndarray) -> float:
    """El zoom que tapa las orillas: el doble del mayor movimiento, con tope."""
    if len(correcciones) == 0:
        return 1.0
    return float(min(MAX_ZOOM, 1.0 + 2.0 * np.abs(correcciones).max()))


class Stabilizer:
    """Guarda las trayectorias ya leídas y responde la corrección de un instante.

    No analiza: si todavía no hay análisis del archivo responde None y el
    clip se pinta sin corregir. Analizar lo encarga la ventana en otro hilo.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._datos: dict[tuple, tuple[np.ndarray, np.ndarray, float]] = {}

    def forget(self) -> None:
        with self._lock:
            self._datos.clear()

    def has_analysis(self, path) -> bool:
        destino = analysis_path(path)
        return destino is not None and destino.exists()

    def offset(self, path, source_time: float, strength: float, fps: float = 30.0):
        """(dx, dy, zoom) para ese instante del archivo, o None."""
        if strength <= 0:
            return None
        destino = analysis_path(path)
        if destino is None or not destino.exists():
            return None
        clave = (str(destino), round(float(strength), 2))
        with self._lock:
            listo = self._datos.get(clave)
        if listo is None:
            try:
                trayectoria = np.load(destino)
            except (OSError, ValueError):
                return None
            corr = corrections(trayectoria, strength, fps)
            listo = (trayectoria[:, 0], corr, zoom_for(corr))
            with self._lock:
                self._datos[clave] = listo
        tiempos, corr, zoom = listo
        if len(tiempos) == 0:
            return None
        indice = int(np.clip(np.searchsorted(tiempos, source_time + 1e-6) - 1, 0, len(tiempos) - 1))
        return float(corr[indice, 0]), float(corr[indice, 1]), zoom


STABILIZER = Stabilizer()
