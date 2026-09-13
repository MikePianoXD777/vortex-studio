"""Seguimiento de movimiento: saber dónde está un objeto en cada cuadro.

Se marca una caja sobre el objeto en un cuadro y se busca esa misma imagen
en los siguientes, cerca de donde estaba. La búsqueda es **correlación
cruzada normalizada** (ZNCC) sobre cuadros reducidos a 320 pixeles en gris:
el numerador sale de una FFT y la varianza de cada ventana de imágenes
integrales, así que cada cuadro cuesta unos milisegundos en NumPy, sin
bucles de Python por pixel.

Normalizada y no correlación de fase —la de la estabilización— porque aquí
se busca una parte chica dentro de un pedazo más grande, y porque la
normalización la hace indiferente a que el objeto se aclare u oscurezca un
poco, que es lo que pasa cuando cruza una sombra.

El molde se actualiza despacio (15 % por cuadro, y solo si el parecido es
bueno): el objeto gira y cambia de tamaño, y un molde fijo se pierde a los
pocos segundos; uno que se reemplaza entero se va corriendo del objeto.

El resultado son filas `[tiempo del archivo, x, y, parecido]` con el centro
de la caja en fracciones del cuadro del material. Qué se hace con eso —que
una máscara o un texto lo sigan— es del modelo: ver `model/tracking.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

WIDTH = 320
LOST = 0.35          # debajo de este parecido el objeto se da por perdido en ese cuadro


def _gray(frame, ancho: int = WIDTH) -> np.ndarray:
    alto = max(2, round(ancho * frame.height / max(1, frame.width)))
    return frame.reformat(width=ancho, height=alto, format="gray").to_ndarray()[:, :ancho] \
        .astype(np.float64)


def match(template: np.ndarray, search: np.ndarray):
    """Dónde cae el molde dentro de la búsqueda: `(x, y, parecido)` o None.

    `x`, `y` son la esquina superior izquierda, con fracciones de pixel por
    ajuste parabólico alrededor del pico. El parecido va de -1 a 1.
    """
    th, tw = template.shape
    sh, sw = search.shape
    if sh < th or sw < tw:
        return None
    t = template - template.mean()
    norma = float(np.sqrt((t * t).sum()))
    if norma < 1e-6:
        return None                     # un molde parejo no se puede buscar

    # Numerador: la correlación de la búsqueda con el molde sin su promedio.
    # Como el molde suma cero, restarle el promedio a cada ventana no cambia
    # nada: basta con la búsqueda cruda.
    numerador = np.real(np.fft.ifft2(np.fft.fft2(search) *
                                     np.conj(np.fft.fft2(t, s=search.shape))))
    alto, ancho = sh - th + 1, sw - tw + 1
    numerador = numerador[:alto, :ancho]

    # Denominador: la desviación de cada ventana, con imágenes integrales.
    n = th * tw
    uno = np.pad(search.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    dos = np.pad((search * search).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def ventanas(ii):
        return ii[th:th + alto, tw:tw + ancho] - ii[:alto, tw:tw + ancho] \
            - ii[th:th + alto, :ancho] + ii[:alto, :ancho]

    suma = ventanas(uno)
    varianza = np.maximum(ventanas(dos) - suma * suma / n, 1e-6)
    ncc = numerador / (np.sqrt(varianza) * norma)

    py, px = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
    parecido = float(ncc[py, px])

    def fino(menos, centro, mas):
        den = menos - 2 * centro + mas
        return 0.0 if abs(den) < 1e-12 else max(-0.5, min(0.5, 0.5 * (menos - mas) / den))

    dx = fino(ncc[py, px - 1], ncc[py, px], ncc[py, px + 1]) if 0 < px < ancho - 1 else 0.0
    dy = fino(ncc[py - 1, px], ncc[py, px], ncc[py + 1, px]) if 0 < py < alto - 1 else 0.0
    return px + dx, py + dy, parecido


def track(path: str | Path, start: float, end: float,
          box: tuple[float, float, float, float],
          progress: Callable[[int, int], bool] | None = None) -> np.ndarray:
    """Sigue la caja `(centro x, centro y, ancho, alto)` —fracciones del material—
    desde el segundo `start` hasta `end` del archivo.

    `progress(hecho, total)` en milisegundos; devuelve False para cancelar.
    """
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado")
    filas: list[tuple[float, float, float, float]] = []
    molde = None
    pos = (0.0, 0.0)
    with av.open(str(path)) as contenedor:
        if not contenedor.streams.video:
            raise ValueError("El archivo no tiene video que seguir.")
        flujo = contenedor.streams.video[0]
        flujo.thread_type = "AUTO"
        if start > 0:
            contenedor.seek(int(max(0.0, start - 0.5) / flujo.time_base), stream=flujo,
                            backward=True)
        total = max(1, int((end - start) * 1000))
        for frame in contenedor.decode(flujo):
            cuando = float(frame.pts * flujo.time_base) if frame.pts is not None else start
            if cuando + 1e-6 < start:
                continue
            if cuando > end + 1e-6:
                break
            gris = _gray(frame)
            alto, ancho = gris.shape
            if molde is None:
                tw = int(max(8, min(ancho, round(box[2] * ancho))))
                th = int(max(8, min(alto, round(box[3] * alto))))
                x0 = min(max(0, round(box[0] * ancho - tw / 2)), ancho - tw)
                y0 = min(max(0, round(box[1] * alto - th / 2)), alto - th)
                molde = gris[y0:y0 + th, x0:x0 + tw].copy()
                pos = (float(x0), float(y0))
                filas.append((cuando, (x0 + tw / 2) / ancho, (y0 + th / 2) / alto, 1.0))
                continue

            # Se busca en un margen del tamaño de la caja alrededor de donde estaba.
            margen = max(tw, th)
            sx0 = int(max(0, min(ancho - tw, round(pos[0]) - margen)))
            sy0 = int(max(0, min(alto - th, round(pos[1]) - margen)))
            sx1 = int(min(ancho, round(pos[0]) + tw + margen))
            sy1 = int(min(alto, round(pos[1]) + th + margen))
            hallado = match(molde, gris[sy0:sy1, sx0:sx1])
            parecido = 0.0
            if hallado is not None:
                parecido = hallado[2]
                if parecido >= LOST:
                    pos = (sx0 + hallado[0], sy0 + hallado[1])
                    if parecido > 0.6:
                        xi, yi = int(round(pos[0])), int(round(pos[1]))
                        xi = min(max(0, xi), ancho - tw)
                        yi = min(max(0, yi), alto - th)
                        molde = 0.85 * molde + 0.15 * gris[yi:yi + th, xi:xi + tw]
            filas.append((cuando, (pos[0] + tw / 2) / ancho, (pos[1] + th / 2) / alto, parecido))
            if progress is not None and not progress(int((cuando - start) * 1000), total):
                from vortex_studio.media.encoder import Cancelled
                raise Cancelled()
    return np.array(filas, dtype=np.float64).reshape(-1, 4)
