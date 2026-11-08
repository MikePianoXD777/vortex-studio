"""Piezas compartidas del motor: colores, desenfoque, remuestreo y Qt.

Todo vectorizado con numpy. Lo único de Qt que se usa es `QtGui` (imágenes,
fuentes y pintura), sin widgets.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QColor, QGuiApplication, QImage

_app = None


def ensure_qt() -> None:
    """Las fuentes de Qt piden una `QGuiApplication`; si la interfaz aún no
    creó la suya (pruebas, scripts, exportación por lotes), se crea una."""
    global _app
    if QGuiApplication.instance() is None and _app is None:
        _app = QGuiApplication(["vortex-photo"])


def parse_color(texto: str | None, por_omision=(0, 0, 0, 255)) -> tuple[int, int, int, int]:
    """'#rrggbb', '#rgb', '#aarrggbb' o un nombre → (r, g, b, a) en 0…255."""
    if not texto:
        return por_omision
    c = QColor(str(texto))
    if not c.isValid():
        return por_omision
    return c.red(), c.green(), c.blue(), c.alpha()


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


# --- Qt ↔ numpy ---------------------------------------------------------------

def to_qimage(pixels: np.ndarray) -> QImage:
    """RGBA uint8 (alto, ancho, 4) → QImage RGBA8888 (copia)."""
    px = np.ascontiguousarray(pixels, dtype=np.uint8)
    h, w = px.shape[:2]
    return QImage(px.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def from_qimage(image: QImage) -> np.ndarray:
    """QImage → RGBA uint8 sin premultiplicar (copia)."""
    if image.format() != QImage.Format.Format_RGBA8888:
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, paso = image.width(), image.height(), image.bytesPerLine()
    if w == 0 or h == 0:
        return np.zeros((h, w, 4), np.uint8)
    buf = np.frombuffer(image.constBits(), np.uint8, count=paso * h)
    return buf.reshape(h, paso)[:, :w * 4].reshape(h, w, 4).copy()


def resize_rgba(pixels: np.ndarray, w: int, h: int) -> np.ndarray:
    """Remuestrea con el escalado suave de Qt (promedio de área al reducir,
    bilineal al ampliar). Si hay transparencia se hace en premultiplicado
    para que los bordes no se oscurezcan."""
    w, h = max(1, int(w)), max(1, int(h))
    if pixels.shape[1] == w and pixels.shape[0] == h:
        return pixels
    from PySide6.QtCore import Qt
    opaca = pixels[..., 3].min() == 255
    img = to_qimage(pixels)
    if not opaca:
        img = img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    img = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    return from_qimage(img)


def resize_gray(mask: np.ndarray, w: int, h: int) -> np.ndarray:
    """Igual que `resize_rgba` pero para máscaras (alto, ancho) uint8."""
    w, h = max(1, int(w)), max(1, int(h))
    if mask.shape[1] == w and mask.shape[0] == h:
        return mask
    rgba = np.empty(mask.shape + (4,), np.uint8)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = mask
    rgba[..., 3] = 255
    return np.ascontiguousarray(resize_rgba(rgba, w, h)[..., 0])


# --- desenfoque -----------------------------------------------------------------

def _box_axis(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    """Promedio móvil de radio r a lo largo de `axis` con sumas acumuladas
    (costo constante sin importar r). Bordes replicados. Se hace por tandas
    para no duplicar en float64 una imagen entera."""
    movido = np.moveaxis(a, axis, -1)
    salida = np.empty_like(movido)
    n = movido.shape[-1]
    lote = max(1, 2_000_000 // max(1, n * int(np.prod(movido.shape[1:-1], dtype=np.int64) or 1)))
    k = 2 * r + 1
    for i in range(0, movido.shape[0], lote):
        sub = movido[i:i + lote]
        pad = [(0, 0)] * (sub.ndim - 1) + [(r + 1, r)]
        p = np.pad(sub, pad, mode="edge")
        p[..., 0] = 0                       # el cero inicial de la suma acumulada
        c = np.cumsum(p, axis=-1, dtype=np.float64)
        salida[i:i + lote] = ((c[..., k:k + n] - c[..., :n]) / k)
    return np.moveaxis(salida, -1, axis)


def box_sizes(sigma: float, n: int = 3) -> list[int]:
    """Radios de n cajas sucesivas que aproximan una gaussiana de `sigma`."""
    ideal = (12.0 * sigma * sigma / n + 1.0) ** 0.5
    wl = int(ideal)
    if wl % 2 == 0:
        wl -= 1
    wl = max(1, wl)
    wu = wl + 2
    m = round((12.0 * sigma * sigma - n * wl * wl - 4 * n * wl - 3 * n) / (-4.0 * wl - 4.0))
    return [((wl if i < m else wu) - 1) // 2 for i in range(n)]


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Desenfoque gaussiano separable (3 cajas) sobre float32 (alto, ancho[, c]).
    Devuelve un arreglo nuevo, float32."""
    a = np.asarray(a, dtype=np.float32)
    if sigma < 0.35:
        return a.copy()
    out = a
    for r in box_sizes(float(sigma)):
        if r < 1:
            continue
        out = _box_axis(out, r, 0)
        out = _box_axis(out, r, 1)
    return out.astype(np.float32, copy=False) if out is not a else a.copy()


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
