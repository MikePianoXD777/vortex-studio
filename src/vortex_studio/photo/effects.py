"""Efectos de capa: sombra paralela, contorno y brillo exterior.

Se calculan sobre el alfa de la capa: se agranda el lienzo lo que haga falta
(`apply_effects` dice cuánto), se dibujan los efectos detrás y el original
encima. Todo con desenfoques de caja y máximos deslizantes, vectorizado.
"""

from __future__ import annotations

import math

import numpy as np

from ._util import gaussian_blur, parse_color
from .document import Effects


def _max_axis(a: np.ndarray, k: int, axis: int) -> np.ndarray:
    """Máximo móvil de ventana k (impar) por duplicación: O(log k) pasadas.
    El borde cuenta como 0 (el alfa de afuera)."""
    if k <= 1:
        return a
    h = k // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (h, h)
    p = np.pad(a, pad)
    n = p.shape[axis]
    m, ventana = p, 1
    sl = lambda ini, fin: tuple(slice(ini, fin) if i == axis else slice(None) for i in range(a.ndim))
    while ventana * 2 <= k:
        m = np.maximum(m[sl(0, m.shape[axis] - ventana)], m[sl(ventana, None)])
        ventana *= 2
    largo = n - k + 1
    resto = k - ventana
    return np.maximum(m[sl(0, largo)], m[sl(resto, resto + largo)])


def dilate(alpha: np.ndarray, r: float) -> np.ndarray:
    """Dilatación con un disco de radio r (float32 0…1). El disco se arma con
    unos pocos rectángulos inscritos (escalera), con bordes suavizados."""
    if r <= 0:
        return alpha
    if r < 1:
        # Menos de un píxel: media dilatación proporcional.
        d = dilate(alpha, 1.0)
        return np.maximum(alpha, d * r)
    cuantos = min(int(math.ceil(r)), 8)
    out = alpha.copy()
    for i in range(cuantos + 1):
        # Rectángulo de medio alto y_i y medio ancho x_i que cabe en el disco.
        y = r * i / cuantos
        x = math.sqrt(max(r * r - y * y, 0.0))
        kx, ky = 2 * int(round(x)) + 1, 2 * int(round(y)) + 1
        out = np.maximum(out, _max_axis(_max_axis(alpha, kx, 1), ky, 0))
    return gaussian_blur(out, 0.6)


def _margenes(effects: Effects, scale: float) -> tuple[int, int, int, int]:
    izq = arr = der = aba = 0
    if effects.shadow.enabled:
        sh = effects.shadow
        ext = int(math.ceil(max(sh.blur, 0.0) * scale * 1.5)) + 2
        izq = max(izq, ext - int(math.floor(sh.dx * scale)))
        der = max(der, ext + int(math.ceil(sh.dx * scale)))
        arr = max(arr, ext - int(math.floor(sh.dy * scale)))
        aba = max(aba, ext + int(math.ceil(sh.dy * scale)))
    if effects.outline.enabled:
        e = int(math.ceil(max(effects.outline.width, 0.0) * scale)) + 2
        izq, der, arr, aba = max(izq, e), max(der, e), max(arr, e), max(aba, e)
    if effects.glow.enabled:
        e = int(math.ceil(max(effects.glow.radius, 0.0) * scale * 1.5)) + 2
        izq, der, arr, aba = max(izq, e), max(der, e), max(arr, e), max(aba, e)
    return max(izq, 0), max(arr, 0), max(der, 0), max(aba, 0)


def apply_effects(pixels: np.ndarray, effects: Effects, scale: float) -> tuple[np.ndarray, int, int]:
    """Devuelve (imagen con margen, cuánto creció a la izquierda, cuánto arriba).
    Sin efectos activos devuelve la misma imagen y (0, 0)."""
    if effects is None or effects.is_off():
        return pixels, 0, 0
    scale = max(float(scale), 1e-4)
    izq, arr, der, aba = _margenes(effects, scale)
    h, w = pixels.shape[:2]
    H, W = h + arr + aba, w + izq + der
    alfa = np.zeros((H, W), np.float32)
    alfa[arr:arr + h, izq:izq + w] = pixels[..., 3].astype(np.float32) * np.float32(1 / 255.0)

    # Capas de atrás hacia adelante, en premultiplicado: rgb·a (3) y a.
    acum = np.zeros((H, W, 4), np.float32)

    def poner(cobertura: np.ndarray, color_hex: str, opacidad: float) -> None:
        r, g, b, a = parse_color(color_hex, (0, 0, 0, 255))
        a_ = cobertura * np.float32(opacidad * a / 255.0)
        col = np.array([r, g, b], np.float32) / 255.0
        # acum = capa sobre acum (over, premultiplicado)
        acum[..., :3] = col * a_[..., None] + acum[..., :3] * (1 - a_[..., None])
        acum[..., 3] = a_ + acum[..., 3] * (1 - a_)

    if effects.glow.enabled:
        g = effects.glow
        sigma = max(g.radius * scale / 2.0, 0.5)
        cob = np.clip(gaussian_blur(alfa, sigma) * 1.8, 0.0, 1.0)
        poner(cob, g.color, g.opacity)
    if effects.shadow.enabled:
        s = effects.shadow
        dx, dy = int(round(s.dx * scale)), int(round(s.dy * scale))
        movida = np.roll(np.roll(alfa, dy, axis=0), dx, axis=1)   # el margen asegura que no se envuelva
        sigma = s.blur * scale / 2.0
        cob = gaussian_blur(movida, sigma) if sigma >= 0.35 else movida
        poner(cob, s.color, s.opacity)
    if effects.outline.enabled:
        o = effects.outline
        poner(dilate(alfa, o.width * scale), o.color, 1.0)

    # El original encima.
    src = np.zeros((H, W, 4), np.float32)
    a0 = alfa
    src[arr:arr + h, izq:izq + w, :3] = pixels[..., :3].astype(np.float32) * np.float32(1 / 255.0)
    src[..., :3] *= a0[..., None]
    src[..., 3] = a0
    acum[..., :3] = src[..., :3] + acum[..., :3] * (1 - a0[..., None])
    acum[..., 3] = a0 + acum[..., 3] * (1 - a0)

    out = np.zeros((H, W, 4), np.uint8)
    a = acum[..., 3:4]
    with np.errstate(divide="ignore", invalid="ignore"):
        rgb = np.where(a > 0, acum[..., :3] / np.where(a > 0, a, 1.0), 0.0)
    out[..., :3] = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(a[..., 0] * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out, izq, arr
