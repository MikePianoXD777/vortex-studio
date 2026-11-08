"""Modos de fusión y composición de capas.

Las fórmulas son las del estándar W3C «Compositing and Blending» (las mismas
que Photoshop para estos 16 modos). Los colores se manejan sin premultiplicar
y la mezcla con el alfa del fondo y de la capa va aparte, como manda la
especificación; así no aparecen halos oscuros en los bordes translúcidos.
"""

from __future__ import annotations

import numpy as np

from .document import BLENDS, NORMAL


# --- modos separables: operan canal por canal, cb = fondo, cs = capa -----------

def _multiply(cb, cs):
    return cb * cs


def _screen(cb, cs):
    return cb + cs - cb * cs


def _hard_light(cb, cs):
    return np.where(cs <= 0.5, _multiply(cb, 2 * cs), _screen(cb, 2 * cs - 1))


def _overlay(cb, cs):
    return _hard_light(cs, cb)


def _soft_light(cb, cs):
    d = np.where(cb <= 0.25, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(cb))
    return np.where(cs <= 0.5, cb - (1 - 2 * cs) * cb * (1 - cb), cb + (2 * cs - 1) * (d - cb))


def _color_dodge(cb, cs):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.minimum(1.0, cb / (1.0 - cs))
    r = np.where(cs >= 1.0, 1.0, r)
    return np.where(cb <= 0.0, 0.0, r)


def _color_burn(cb, cs):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 1.0 - np.minimum(1.0, (1.0 - cb) / cs)
    r = np.where(cs <= 0.0, 0.0, r)
    return np.where(cb >= 1.0, 1.0, r)


_SEPARABLES = {
    "Multiplicar": _multiply,
    "Oscurecer": np.minimum,
    "Subexponer color": _color_burn,
    "Trama": _screen,
    "Aclarar": np.maximum,
    "Sobreexponer color": _color_dodge,
    "Superponer": _overlay,
    "Luz suave": _soft_light,
    "Luz fuerte": _hard_light,
    "Diferencia": lambda cb, cs: np.abs(cb - cs),
    "Exclusión": lambda cb, cs: cb + cs - 2 * cb * cs,
}


# --- modos no separables (tono, saturación, color, luminosidad) ----------------

def _lum(c):
    return (0.3 * c[..., 0] + 0.59 * c[..., 1] + 0.11 * c[..., 2])[..., None]


def _clip_color(c):
    l = _lum(c)
    n = c.min(axis=-1, keepdims=True)
    x = c.max(axis=-1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(n < 0, l + (c - l) * l / (l - n), c)
        c = np.where(x > 1, l + (c - l) * (1 - l) / (x - l), c)
    return np.nan_to_num(c)


def _set_lum(c, l):
    return _clip_color(c + (l - _lum(c)))


def _sat(c):
    return c.max(axis=-1, keepdims=True) - c.min(axis=-1, keepdims=True)


def _set_sat(c, s):
    mn = c.min(axis=-1, keepdims=True)
    mx = c.max(axis=-1, keepdims=True)
    rango = mx - mn
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (c - mn) * s / rango
    return np.where(rango > 0, r, 0.0)


def _hue(cb, cs):
    return _set_lum(_set_sat(cs, _sat(cb)), _lum(cb))


def _saturation(cb, cs):
    return _set_lum(_set_sat(cb, _sat(cs)), _lum(cb))


def _color(cb, cs):
    return _set_lum(cs, _lum(cb))


def _luminosity(cb, cs):
    return _set_lum(cb, _lum(cs))


_NO_SEPARABLES = {"Tono": _hue, "Saturación": _saturation, "Color": _color, "Luminosidad": _luminosity}


def blend_colors(cb: np.ndarray, cs: np.ndarray, mode: str) -> np.ndarray:
    """B(cb, cs): el color de mezcla de un modo, con colores en 0…1 (…, 3).
    Es la función que se prueba contra el cálculo de referencia."""
    if mode in _SEPARABLES:
        return _SEPARABLES[mode](cb, cs)
    if mode in _NO_SEPARABLES:
        return _NO_SEPARABLES[mode](cb, cs)
    return cs


def composite(dst: np.ndarray, src: np.ndarray, mode: str, opacity: float,
              x: int, y: int) -> None:
    """Pone `src` (RGBA uint8) sobre `dst` (RGBA uint8) con su esquina
    superior izquierda en (x, y), en su lugar. `src` puede salirse del borde."""
    opacity = float(opacity)
    if opacity <= 0.0 or src.size == 0 or dst.size == 0:
        return
    opacity = min(opacity, 1.0)
    dh, dw = dst.shape[:2]
    sh, sw = src.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + sw), min(dh, y + sh)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    sa8 = s[..., 3]
    if sa8.max() == 0:
        return
    if mode not in BLENDS:
        mode = NORMAL

    # Camino rápido: capa opaca, modo normal, opacidad plena = copiar.
    if mode == NORMAL and opacity >= 1.0 and sa8.min() == 255:
        d[...] = s
        return

    as_ = sa8.astype(np.float32)[..., None] * np.float32(opacity / 255.0)    # αs'
    cs = s[..., :3].astype(np.float32) * np.float32(1 / 255.0)
    da = d[..., 3]
    if da.min() == 255:
        # Fondo opaco (lo normal): αr = 1 y Cr = Cb + αs'·(B − Cb).
        cb = d[..., :3].astype(np.float32) * np.float32(1 / 255.0)
        b = cs if mode == NORMAL else blend_colors(cb, cs, mode)
        r = cb + as_ * (b - cb)
        d[..., :3] = np.clip(r * 255.0 + 0.5, 0, 255).astype(np.uint8)
        return

    # Caso general (fondo con transparencia).
    ab = da.astype(np.float32)[..., None] * np.float32(1 / 255.0)
    cb = d[..., :3].astype(np.float32) * np.float32(1 / 255.0)
    ar = as_ + ab * (1.0 - as_)
    b = cs if mode == NORMAL else blend_colors(cb, cs, mode)
    # Cr·αr = (1−αs)·αb·Cb + αs·((1−αb)·Cs + αb·B)
    num = (1.0 - as_) * ab * cb + as_ * ((1.0 - ab) * cs + ab * b)
    with np.errstate(divide="ignore", invalid="ignore"):
        cr = np.where(ar > 0, num / ar, 0.0)
    d[..., :3] = np.clip(cr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    d[..., 3] = np.clip(ar[..., 0] * 255.0 + 0.5, 0, 255).astype(np.uint8)
