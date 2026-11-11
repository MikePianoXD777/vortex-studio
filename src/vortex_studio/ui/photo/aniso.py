"""Pincel redondo en el lienzo aunque la capa esté estirada.

Los trazos del motor miden el pincel en píxeles de la imagen, con el mismo
tamaño en x e y. Si la capa se estiró (por ejemplo ×2,4 a lo ancho y ×0,6 a lo
alto) el pincel saldría elíptico en el lienzo. Aquí se calcula la cobertura del
trazo en un espacio auxiliar donde un píxel es cuadrado en el lienzo y se
devuelve a la rejilla de la imagen; después se aplica igual que en el motor.
"""

from __future__ import annotations

import math

import numpy as np

from vortex_studio.photo import paint
from vortex_studio.photo._util import parse_color, resize_gray

TOL = 0.03          # por debajo de esta diferencia entre ejes se usa el motor tal cual


def es_estirada(ax: float, ay: float) -> bool:
    return abs(ax / max(ay, 1e-9) - 1.0) > TOL


def cobertura(shape: tuple[int, int], pts, size_units: float, hardness: float, opacity: float,
              ax: float, ay: float):
    """`(y0, y1, x0, x1, cob)` en píxeles de la imagen, con el trazo redondo en el lienzo.

    `ax`, `ay`: píxeles de imagen por unidad del lienzo en cada eje.
    """
    h, w = shape
    q = max(ax, ay)
    fx, fy = q / ax, q / ay                        # >= 1: la imagen auxiliar es más grande
    sshape = (max(1, int(round(h * fy))), max(1, int(round(w * fx))))
    spts = [(u * fx, v * fy, p) for u, v, p in pts]
    brush = paint.Brush(size_units * q, hardness, opacity)
    cob = paint.coverage(sshape, spts, brush)
    if cob is None:
        return None
    y0, y1, x0, x1, c = cob
    ix0, ix1 = max(0, int(math.floor(x0 / fx))), min(w, int(math.ceil(x1 / fx)))
    iy0, iy1 = max(0, int(math.floor(y0 / fy))), min(h, int(math.ceil(y1 / fy)))
    if ix1 <= ix0 or iy1 <= iy0:
        return None
    # La zona de la imagen, vista en el espacio auxiliar, y dónde cae la cobertura calculada.
    sx0, sx1 = int(round(ix0 * fx)), max(int(round(ix1 * fx)), int(round(ix0 * fx)) + 1)
    sy0, sy1 = int(round(iy0 * fy)), max(int(round(iy1 * fy)), int(round(iy0 * fy)) + 1)
    base = np.zeros((sy1 - sy0, sx1 - sx0), np.float32)
    ax0, ax1 = max(sx0, x0), min(sx1, x1)
    ay0, ay1 = max(sy0, y0), min(sy1, y1)
    if ax1 > ax0 and ay1 > ay0:
        base[ay0 - sy0: ay1 - sy0, ax0 - sx0: ax1 - sx0] = c[ay0 - y0: ay1 - y0, ax0 - x0: ax1 - x0]
    g = np.clip(base * 255.0 + 0.5, 0, 255).astype(np.uint8)
    g = resize_gray(g, ix1 - ix0, iy1 - iy0)
    return iy0, iy1, ix0, ix1, g.astype(np.float32) / 255.0


def pintar(pixels: np.ndarray, cob, color: str, erase: bool) -> np.ndarray:
    """Aplica una cobertura como `paint.stroke`. Devuelve una copia."""
    out = pixels.copy()
    if cob is None:
        return out
    y0, y1, x0, x1, a = cob
    reg = out[y0:y1, x0:x1]
    if erase:
        reg[..., 3] = np.clip(reg[..., 3].astype(np.float32) * (1.0 - a) + 0.5, 0, 255).astype(np.uint8)
        return out
    r, g, b, ca = parse_color(color, (0, 0, 0, 255))
    a = a * (ca / 255.0)
    ab = reg[..., 3].astype(np.float32) * np.float32(1 / 255.0)
    ar = a + ab * (1.0 - a)
    col = np.array([r, g, b], np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.where(ar > 0, a / np.where(ar > 0, ar, 1.0), 0.0)[..., None]
    nuevo = reg[..., :3].astype(np.float32) * (1.0 - k) + col * k
    reg[..., :3] = np.clip(nuevo + 0.5, 0, 255).astype(np.uint8)
    reg[..., 3] = np.clip(ar * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out


def pintar_mascara(mask: np.ndarray, cob, erase: bool) -> np.ndarray:
    out = mask.copy()
    if cob is None:
        return out
    y0, y1, x0, x1, a = cob
    reg = out[y0:y1, x0:x1].astype(np.float32)
    destino = 0.0 if erase else 255.0
    out[y0:y1, x0:x1] = np.clip(reg + (destino - reg) * a + 0.5, 0, 255).astype(np.uint8)
    return out
