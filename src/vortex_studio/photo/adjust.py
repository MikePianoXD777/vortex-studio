"""Ajustes de foto: exposición, tonos, color, detalle y viñeta.

Diseño para que sea rápido:
- Todo lo que depende solo del valor de cada canal (exposición, contraste,
  altas luces, sombras, blancos, negros, curva) se junta en **una** tabla de
  256 entradas. Como la entrada es `uint8`, la tabla es exacta y aplicarla es
  un solo recorrido.
- El color (intensidad, saturación, HSL, temperatura) y lo espacial (claridad,
  enfoque, desenfoque, viñeta, grano) trabajan en `float32` solo si hacen
  falta.
- Con todo en cero se devuelve la misma imagen, bit a bit.
- `scale` es la escala del lienzo a la que se está viendo: los radios se dan
  en píxeles del lienzo y se multiplican por ella, así la vista previa y la
  exportación se ven igual.
"""

from __future__ import annotations

import numpy as np

from ._util import gaussian_blur, luma, smoothstep
from .document import HSL_BANDS, Adjustments

# --- tonos ---------------------------------------------------------------------

_X256 = np.arange(256, dtype=np.float32) / 255.0


def _srgb_a_lineal(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _lineal_a_srgb(x):
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def pchip(xs, ys, x):
    """Interpolación cúbica monótona (Fritsch–Carlson): pasa por los puntos y
    nunca se sobretira entre ellos, a diferencia de un spline normal."""
    xs = np.asarray(xs, np.float64)
    ys = np.asarray(ys, np.float64)
    h = np.diff(xs)
    delta = np.diff(ys) / h
    n = len(xs)
    m = np.zeros(n)
    if n == 2:
        m[:] = delta[0]
    else:
        m[1:-1] = (delta[:-1] + delta[1:]) / 2
        m[0] = delta[0]
        m[-1] = delta[-1]
        for i in range(n - 1):
            if delta[i] == 0:
                m[i] = m[i + 1] = 0
            else:
                a, b = m[i] / delta[i], m[i + 1] / delta[i]
                s = a * a + b * b
                if s > 9:
                    t = 3 / np.sqrt(s)
                    m[i], m[i + 1] = t * a * delta[i], t * b * delta[i]
    x = np.asarray(x, np.float64)
    i = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, n - 2)
    t = (x - xs[i]) / h[i]
    t2, t3 = t * t, t * t * t
    r = ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
         + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return np.clip(r, 0.0, 1.0)


def _puntos_curva(curve):
    """Limpia los puntos: dentro de 0…1, ordenados, sin x repetidas, con los
    extremos (0,0) y (1,1) si faltan."""
    pts = {}
    for p in curve or []:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        pts[min(1.0, max(0.0, x))] = min(1.0, max(0.0, y))
    pts.setdefault(0.0, 0.0)
    pts.setdefault(1.0, 1.0)
    xs = sorted(pts)
    return xs, [pts[x] for x in xs]


def curve_is_identity(curve) -> bool:
    xs, ys = _puntos_curva(curve)
    return all(abs(x - y) < 1e-9 for x, y in zip(xs, ys))


def curve_lut(curve, n: int = 256) -> np.ndarray:
    """Tabla de la curva maestra evaluada en n puntos de 0 a 1."""
    xs, ys = _puntos_curva(curve)
    return pchip(xs, ys, np.linspace(0.0, 1.0, n)).astype(np.float32)


def _contraste(v, c):
    a = c / 100.0
    if a > 0:
        s = v * v * (3 - 2 * v)
        s2 = s * s * (3 - 2 * s)
        return v + a * (s2 - v)
    return 0.5 + (v - 0.5) * (1 + 0.8 * a)


def tone_lut(adj: Adjustments) -> np.ndarray | None:
    """La tabla de 256 entradas (float32, 0…1) de todos los ajustes de tono,
    o None si ninguno actúa."""
    v = _X256.astype(np.float64)
    activo = False
    if adj.exposure:
        v = _lineal_a_srgb(_srgb_a_lineal(v) * 2.0 ** (adj.exposure / 100.0))
        activo = True
    if adj.blacks:
        v = v + 0.25 * (adj.blacks / 100.0) * (1 - v) ** 3
        activo = True
    if adj.whites:
        v = v * (1 + 0.3 * adj.whites / 100.0)
        activo = True
    v = np.clip(v, 0, 1)
    if adj.shadows:
        w = 1 - smoothstep(v / 0.6)
        v = v + 0.35 * (adj.shadows / 100.0) * w
        activo = True
    if adj.highlights:
        w = smoothstep((v - 0.4) / 0.6)
        v = v + 0.35 * (adj.highlights / 100.0) * w
        activo = True
    v = np.clip(v, 0, 1)
    if adj.contrast:
        v = _contraste(v, adj.contrast)
        activo = True
    if adj.curve and not curve_is_identity(adj.curve):
        xs, ys = _puntos_curva(adj.curve)
        v = pchip(xs, ys, np.clip(v, 0, 1))
        activo = True
    if not activo:
        return None
    return np.clip(v, 0, 1).astype(np.float32)


# --- color ---------------------------------------------------------------------

_CENTROS_HSL = np.array([0, 30, 60, 120, 180, 240, 270, 310], dtype=np.float64)
_RES_HUE = 720          # entradas de la tabla de tono (0,5° por paso)


def _tabla_hsl(hsl: dict) -> np.ndarray | None:
    """(720, 3): por cada tono, cuánto mover (tono, saturación, luminosidad),
    mezclando las dos franjas vecinas con una transición suave."""
    vals = np.zeros((8, 3))
    activo = False
    for i, b in enumerate(HSL_BANDS):
        t = hsl.get(b)
        if t is not None and any(t):
            vals[i] = np.clip(np.asarray(t, np.float64)[:3], -100, 100) / 100.0
            activo = True
    if not activo:
        return None
    hue = (np.arange(_RES_HUE) + 0.5) * (360.0 / _RES_HUE)
    c = np.concatenate([_CENTROS_HSL, [360.0]])
    v = np.concatenate([vals, vals[:1]])
    i = np.clip(np.searchsorted(c, hue, side="right") - 1, 0, 7)
    t = (hue - c[i]) / (c[i + 1] - c[i])
    s = (t * t * (3 - 2 * t))[:, None]
    return v[i] * (1 - s) + v[i + 1] * s


def _hsv(rgb):
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    d = mx - mn
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(d > 0, d, 1.0)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        h = np.where(mx == r, ((g - b) / dd) % 6.0,
                     np.where(mx == g, (b - r) / dd + 2.0, (r - g) / dd + 4.0))
        h = np.where(d > 0, h * 60.0, 0.0)
        s = np.where(mx > 0, d / np.where(mx > 0, mx, 1.0), 0.0)
    return h.astype(np.float32), s.astype(np.float32), mx


def _de_hsv(h, s, v):
    k = (np.array([5.0, 3.0, 1.0], np.float32) + (h / 60.0)[..., None]) % 6.0
    f = np.clip(np.minimum(k, 4.0 - k), 0.0, 1.0)
    return v[..., None] - (v * s)[..., None] * f


def _aplicar_hsl(rgb, tabla):
    h, s, v = _hsv(rgb)
    idx = np.minimum((h * (_RES_HUE / 360.0)).astype(np.int32), _RES_HUE - 1)
    t = tabla[idx].astype(np.float32)
    peso = np.clip(s * 3.0, 0.0, 1.0)            # el gris no tiene tono que mover
    h2 = (h + t[..., 0] * 30.0 * peso) % 360.0
    s2 = np.clip(s * (1.0 + t[..., 1]), 0.0, 1.0)
    out = _de_hsv(h2, s2, v)
    dl = (t[..., 2] * peso)[..., None]
    pos, neg = np.clip(dl, 0, 1), np.clip(-dl, 0, 1)
    out = out + (1.0 - out) * 0.5 * pos - out * 0.5 * neg
    return out


# --- detalle ---------------------------------------------------------------------

_SEMILLA_GRANO = 20241107
_LADO_GRANO = 1024
_grano_tile = None


def _tile_grano() -> np.ndarray:
    """Una loseta de ruido gaussiano fija (semilla constante): la vista previa
    y la exportación ven siempre el mismo grano."""
    global _grano_tile
    if _grano_tile is None:
        rng = np.random.default_rng(_SEMILLA_GRANO)
        _grano_tile = rng.standard_normal((_LADO_GRANO, _LADO_GRANO)).astype(np.float32)
    return _grano_tile


def _grano(h, w):
    t = _tile_grano()
    iy = np.arange(h) % _LADO_GRANO
    ix = np.arange(w) % _LADO_GRANO
    return t[iy[:, None], ix[None, :]]


def _vineta(h, w, cantidad):
    ys = (np.arange(h, dtype=np.float32) + 0.5) / h * 2 - 1
    xs = (np.arange(w, dtype=np.float32) + 0.5) / w * 2 - 1
    d = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) / np.sqrt(2.0)
    return 1.0 - cantidad * 0.85 * smoothstep((d - 0.3) / 0.7)


def apply_adjustments(pixels: np.ndarray, adj: Adjustments, scale: float = 1.0) -> np.ndarray:
    """Aplica los ajustes a una imagen RGBA uint8 y devuelve otra del mismo
    tamaño (el alfa no se toca). Con ajustes neutros devuelve `pixels` mismo,
    sin copiar: quien reciba el resultado no debe modificarlo."""
    scale = max(float(scale), 1e-4)
    lut = tone_lut(adj)
    hsl_tab = _tabla_hsl(adj.hsl) if adj.hsl else None
    quiere = {
        "vib": bool(adj.vibrance), "sat": bool(adj.saturation), "hsl": hsl_tab is not None,
        "temp": bool(adj.temperature), "tint": bool(adj.tint),
        "blur": adj.blur > 0, "clar": bool(adj.clarity), "sharp": adj.sharpen > 0,
        "vig": adj.vignette > 0, "grain": adj.grain > 0,
    }
    if lut is None and not any(quiere.values()):
        return pixels
    h, w = pixels.shape[:2]
    alfa = pixels[..., 3]

    # Solo tonos: una sola pasada con la tabla de bytes, sin pasar por float.
    if not any(quiere.values()):
        t8 = np.clip(lut * 255.0 + 0.5, 0, 255).astype(np.uint8)
        out = np.empty_like(pixels)
        out[..., :3] = t8[pixels[..., :3]]
        out[..., 3] = alfa
        return out

    rgb = lut[pixels[..., :3]] if lut is not None else pixels[..., :3].astype(np.float32) * np.float32(1 / 255.0)

    # Color
    if quiere["vib"] or quiere["sat"]:
        l = luma(rgb)[..., None]
        if quiere["vib"]:
            mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
            sat = np.where(mx > 0, (mx - mn) / np.where(mx > 0, mx, 1), 0).astype(np.float32)
            v = adj.vibrance / 100.0
            k = (v * (1.0 - sat) if v > 0 else v + 0 * sat)[..., None]
            rgb = l + (rgb - l) * (1.0 + k)
            l = luma(rgb)[..., None]
        if quiere["sat"]:
            rgb = l + (rgb - l) * np.float32(1.0 + adj.saturation / 100.0)
        rgb = np.clip(rgb, 0.0, 1.0)
    if quiere["hsl"]:
        rgb = np.clip(_aplicar_hsl(rgb, hsl_tab), 0.0, 1.0)
    if quiere["temp"] or quiere["tint"]:
        t, ti = adj.temperature / 100.0, adj.tint / 100.0
        mult = np.array([1 + 0.25 * t, 1 - 0.20 * ti, 1 - 0.25 * t], np.float32)
        # Con la temperatura y el tinte subir un canal baja otro, para que no
        # cambie el brillo general.
        mult[1] *= 1 + 0.04 * abs(t)
        rgb = np.clip(rgb * mult, 0.0, 1.0)

    # Detalle
    if quiere["blur"]:
        sigma = adj.blur / 100.0 * 24.0 * scale
        if sigma >= 0.35:
            rgb = gaussian_blur(rgb, sigma)
    if quiere["clar"]:
        base = gaussian_blur(luma(rgb), max(1.0, 18.0 * scale))
        l = luma(rgb)
        medios = (1.0 - (2.0 * l - 1.0) ** 2) * 0.8 + 0.2
        rgb = np.clip(rgb + ((l - base) * medios * np.float32(adj.clarity / 100.0 * 1.2))[..., None], 0.0, 1.0)
    if quiere["sharp"]:
        sigma = max(0.5, 1.0 * scale)
        fino = gaussian_blur(rgb, sigma)
        rgb = np.clip(rgb + (rgb - fino) * np.float32(adj.sharpen / 100.0 * 2.0), 0.0, 1.0)
    if quiere["vig"]:
        rgb = rgb * _vineta(h, w, adj.vignette / 100.0)[..., None]
    if quiere["grain"]:
        l = luma(rgb)
        peso = (1.0 - (2.0 * l - 1.0) ** 2) * 0.7 + 0.3      # más en los medios tonos
        rgb = np.clip(rgb + (_grano(h, w) * peso * np.float32(adj.grain / 100.0 * 0.12))[..., None], 0.0, 1.0)

    out = np.empty_like(pixels)
    out[..., :3] = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = alfa
    return out
