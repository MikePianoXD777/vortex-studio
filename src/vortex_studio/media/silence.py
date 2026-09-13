"""Detectar silencios: los tramos donde no se oye nada.

Sale de la onda que ya está en caché (`media/waveform.py`) a 100 cubos por
segundo, o sea de 10 en 10 ms: el pico de cada cubo contra un umbral en dB.
No se vuelve a decodificar nada, así que en un archivo ya abierto sale al
instante.

Pico y no RMS: una respiración o un "eh" tienen poca energía promedio pero
sí se oyen, y cortarlos a la mitad se nota más que dejarlos.

Cada silencio se recorta un poco por los lados que dan a sonido (`padding`):
sin ese margen el corte cae justo en la primera sílaba y se come la
consonante, que es lo que delata un corte automático.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vortex_studio.media.waveform import load_or_compute

PER_SECOND = 100


def silent_ranges(path: str | Path, threshold_db: float = -40.0,
                  min_duration: float = 0.5, padding: float = 0.12) -> list[tuple[float, float]]:
    """Los silencios del archivo, en segundos de archivo: `[(inicio, fin)]`."""
    datos = load_or_compute(path, PER_SECOND)
    if datos.shape[1] == 0:
        return []
    pico = np.maximum(np.abs(datos[0]), np.abs(datos[1]))
    callado = (pico < 10 ** (threshold_db / 20.0)).astype(np.int8)
    bordes = np.diff(np.concatenate([[0], callado, [0]]))
    inicios = np.where(bordes == 1)[0]
    fines = np.where(bordes == -1)[0]
    total = len(pico) / PER_SECOND

    salida = []
    for a, b in zip(inicios, fines):
        inicio, fin = a / PER_SECOND, b / PER_SECOND
        if fin - inicio < min_duration:
            continue
        if inicio > 1e-9:
            inicio += padding
        if fin < total - 1e-9:
            fin -= padding
        if fin - inicio > 0.02:
            salida.append((round(inicio, 3), round(fin, 3)))
    return salida
