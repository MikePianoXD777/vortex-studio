"""Scopes: histograma, forma de onda y vectorscopio.

Lo que usan los coloristas para no corregir a ojo: el monitor miente según
la pantalla y la luz del cuarto, los scopes no. Se calculan con NumPy sobre
el cuadro compuesto —lo mismo que se exporta—, reducido a unos 320 pixeles
de ancho: para leer la distribución de la luz no hace falta más, y así cuesta
un par de milisegundos.

Sin Qt: entra un arreglo `alto × ancho × 3` en RGB de 8 bits y salen
conteos. La interfaz decide cómo pintarlos.
"""

from __future__ import annotations

import numpy as np

# Rec. 709, la de video HD: cuánto aporta cada canal a la luminancia.
LUMA = np.array([0.2126, 0.7152, 0.0722])


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., :3].astype(np.float32) @ LUMA.astype(np.float32)


def histogram(rgb: np.ndarray, bins: int = 256) -> np.ndarray:
    """(4, bins): conteos de rojo, verde, azul y luminancia."""
    salida = np.zeros((4, bins), dtype=np.int64)
    escala = bins / 256.0
    for canal in range(3):
        salida[canal] = np.bincount((rgb[..., canal].ravel() * escala).astype(np.int64),
                                    minlength=bins)[:bins]
    y = np.clip(luma(rgb), 0, 255)
    salida[3] = np.bincount((y.ravel() * escala).astype(np.int64), minlength=bins)[:bins]
    return salida


def waveform(rgb: np.ndarray, columns: int = 256, levels: int = 256) -> np.ndarray:
    """(levels, columns): cuántos pixeles de cada columna tienen cada luminancia.

    Fila 0 es la luz máxima, para dibujarla tal cual: arriba lo brillante.
    """
    alto, ancho = rgb.shape[:2]
    y = np.clip(luma(rgb), 0, 255)
    columna = np.broadcast_to((np.arange(ancho) * columns // max(1, ancho))[None, :], (alto, ancho))
    nivel = (levels - 1) - (y * (levels - 1) / 255.0).astype(np.int64)
    indices = nivel.ravel() * columns + columna.ravel()
    return np.bincount(indices, minlength=levels * columns).reshape(levels, columns)


def chroma(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cb y Cr de Rec. 709, centrados en cero, de -0.5 a 0.5."""
    x = rgb[..., :3].astype(np.float32) / 255.0
    y = x @ LUMA.astype(np.float32)
    cb = (x[..., 2] - y) / 1.8556
    cr = (x[..., 0] - y) / 1.5748
    return cb, cr


def vectorscope(rgb: np.ndarray, size: int = 256) -> np.ndarray:
    """(size, size): dónde cae el color de cada pixel. Centro = sin color.

    El eje horizontal es Cb (azul a la derecha) y el vertical Cr (rojo
    arriba), como en cualquier vectorscopio. Qué tan lejos del centro es la
    saturación; hacia dónde, el tono.
    """
    cb, cr = chroma(rgb)
    x = np.clip(((cb + 0.5) * (size - 1)).round().astype(np.int64), 0, size - 1)
    y = np.clip(((0.5 - cr) * (size - 1)).round().astype(np.int64), 0, size - 1)
    return np.bincount((y * size + x).ravel(), minlength=size * size).reshape(size, size)


def targets(size: int = 256) -> dict[str, tuple[float, float]]:
    """Dónde caen los seis colores puros al 75 %: las casillas del vectorscopio."""
    puros = {"R": (191, 0, 0), "Mg": (191, 0, 191), "B": (0, 0, 191),
             "Cy": (0, 191, 191), "G": (0, 191, 0), "Yl": (191, 191, 0)}
    salida = {}
    for nombre, rgb in puros.items():
        cb, cr = chroma(np.array([[rgb]], dtype=np.uint8))
        salida[nombre] = ((float(cb[0, 0]) + 0.5) * (size - 1), (0.5 - float(cr[0, 0])) * (size - 1))
    return salida
