"""Filtros de un clic y «Mejorar con un clic».

Un filtro es un conjunto de ajustes (los mismos del panel) con nombre. Así
cada filtro se puede afinar a mano después, la intensidad se aplica
escalando los ajustes hacia cero —lo que es exacto y no cuesta una segunda
imagen— y no hay una segunda ruta de código que mantener.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np

from ._util import luma
from .adjust import _puntos_curva, apply_adjustments, pchip
from .document import Adjustments, Filter


@dataclass
class FilterPreset:
    id: str
    name: str
    adjustments: Adjustments


def _p(id_: str, nombre: str, **kw) -> tuple[str, FilterPreset]:
    return id_, FilterPreset(id_, nombre, Adjustments(**kw))


# Curvas de apoyo
_S_SUAVE = [(0.0, 0.0), (0.25, 0.21), (0.75, 0.80), (1.0, 1.0)]
_MATE = [(0.0, 0.08), (0.25, 0.27), (0.75, 0.78), (1.0, 0.94)]
_DESVANECIDO = [(0.0, 0.14), (0.3, 0.34), (0.7, 0.72), (1.0, 0.96)]
_PELICULA = [(0.0, 0.03), (0.2, 0.17), (0.5, 0.52), (0.85, 0.89), (1.0, 0.98)]

FILTERS: dict[str, FilterPreset] = dict([
    _p("natural", "Natural", contrast=8, vibrance=12, clarity=8),
    _p("vivido", "Vívido", contrast=18, saturation=28, vibrance=20, clarity=10),
    _p("calido", "Cálido", temperature=32, tint=6, contrast=6, saturation=6),
    _p("frio", "Frío", temperature=-32, tint=-4, contrast=6, saturation=4),
    _p("bn", "Blanco y negro", saturation=-100, contrast=14, clarity=10),
    _p("noir", "Noir", saturation=-100, contrast=42, blacks=-28, highlights=-10,
       vignette=45, grain=18),
    _p("sepia", "Sepia", saturation=-100, temperature=58, tint=14, contrast=8,
       blacks=8, vignette=15),
    _p("vintage", "Vintage", temperature=18, tint=8, saturation=-22, contrast=-8,
       curve=_DESVANECIDO, vignette=28, grain=18),
    _p("pelicula", "Película", contrast=10, saturation=-8, tint=-6, temperature=6,
       curve=_PELICULA, grain=32),
    _p("atardecer", "Atardecer", temperature=44, tint=10, exposure=6, saturation=14,
       highlights=-12, vibrance=16,
       hsl={"orange": (0, 20, 8), "yellow": (-10, 10, 0), "blue": (0, -20, -10)}),
    _p("pastel", "Pastel", saturation=-18, vibrance=10, exposure=10, contrast=-22,
       shadows=30, blacks=22),
    _p("dramatico", "Dramático", contrast=46, clarity=45, shadows=-12, highlights=-26,
       saturation=-14, vignette=30),
    _p("matte", "Matte", contrast=-12, saturation=-10, curve=_MATE, shadows=12),
    _p("cian_naranja", "Cian y naranja", contrast=14, temperature=8, saturation=6,
       hsl={"orange": (0, 28, 6), "red": (0, 10, 0), "aqua": (-8, 24, -6),
            "blue": (-6, 22, -12), "green": (0, -40, 0)}),
    _p("retro70", "Retro 70", temperature=26, tint=14, saturation=-12, contrast=-6,
       exposure=6, curve=_DESVANECIDO, grain=22,
       hsl={"green": (-20, -20, 0), "blue": (10, -30, 0)}),
    _p("desvanecido", "Desvanecido", contrast=-30, saturation=-26, exposure=8,
       curve=_DESVANECIDO),
    _p("nitido", "Nítido", sharpen=65, clarity=32, contrast=10),
    _p("suave", "Suave", clarity=-45, blur=9, exposure=6, contrast=-8, saturation=-4),
    _p("neon", "Neón", saturation=48, vibrance=30, contrast=26, blacks=-24,
       tint=22, temperature=-14, vignette=28,
       hsl={"purple": (0, 25, 8), "magenta": (0, 25, 8), "aqua": (0, 20, 6)}),
    _p("invierno", "Invierno", temperature=-26, saturation=-18, exposure=8, contrast=10,
       highlights=8, hsl={"blue": (0, 10, 4)}),
    _p("verano", "Verano", temperature=22, saturation=22, vibrance=18, exposure=6,
       contrast=8, hsl={"green": (6, 14, 0), "yellow": (0, 16, 4)}),
    _p("otono", "Otoño", temperature=30, tint=8, saturation=8, contrast=12,
       hsl={"green": (-36, -10, -6), "yellow": (-10, 18, 0), "orange": (0, 24, 0)}),
])


def filter_ids() -> list[str]:
    return list(FILTERS)


def find_preset(name: str) -> FilterPreset | None:
    """El preset por id o por nombre visible (sin importar mayúsculas)."""
    if not name:
        return None
    if name in FILTERS:
        return FILTERS[name]
    bajo = name.strip().lower()
    for p in FILTERS.values():
        if p.id == bajo or p.name.lower() == bajo:
            return p
    return None


def scale_adjustments(adj: Adjustments, t: float) -> Adjustments:
    """Los ajustes mezclados con «ninguno» en la proporción t (0…1)."""
    t = min(1.0, max(0.0, float(t)))
    if t >= 1.0:
        return adj
    kw = {}
    for f in fields(Adjustments):
        v = getattr(adj, f.name)
        if f.name == "curve":
            if v:
                xs, ys = _puntos_curva(v)
                gx = np.linspace(0, 1, 9)
                gy = pchip(xs, ys, gx)
                kw["curve"] = [(float(x), float(x + (y - x) * t)) for x, y in zip(gx, gy)]
            else:
                kw["curve"] = []
        elif f.name == "hsl":
            kw["hsl"] = {k: tuple(c * t for c in tup) for k, tup in v.items()}
        else:
            kw[f.name] = v * t
    return replace(adj, **kw)


def filter_adjustments(flt: Filter) -> Adjustments | None:
    """Los ajustes que equivalen a un filtro con su intensidad (o None)."""
    if flt.is_off():
        return None
    preset = find_preset(flt.name)
    if preset is None:
        return None
    return scale_adjustments(preset.adjustments, flt.intensity / 100.0)


def apply_filter(pixels: np.ndarray, flt: Filter, scale: float = 1.0) -> np.ndarray:
    adj = filter_adjustments(flt)
    if adj is None:
        return pixels
    return apply_adjustments(pixels, adj, scale)


def auto_enhance(pixels: np.ndarray) -> Adjustments:
    """«Mejorar con un clic»: mira el histograma y propone correcciones
    moderadas (nunca extremas) para que la foto se vea mejor sin que parezca
    editada. Una foto ya buena sale casi neutra."""
    h, w = pixels.shape[:2]
    paso = max(1, int(max(h, w) / 256))
    muestra = pixels[::paso, ::paso]
    opaco = muestra[..., 3] > 16
    if not opaco.any():
        return Adjustments()
    l = luma(muestra[opaco][:, :3].astype(np.float32) / 255.0)
    p1, p10, p50, p90, p99 = np.percentile(l, [1, 10, 50, 90, 99])
    media = float(l.mean())
    adj = Adjustments()
    clip = lambda v, lo, hi: float(min(hi, max(lo, v)))

    # Exposición: llevar la mediana hacia ~0,45 (en luz lineal, como una cámara).
    if p50 > 0.01:
        ev = np.log2(max(0.45, 1e-3) ** 2.2 / max(p50, 1e-3) ** 2.2)
        adj.exposure = round(clip(ev * 100 * 0.6, -45, 55), 1)
        if abs(adj.exposure) < 4:
            adj.exposure = 0.0
    else:
        adj.exposure = 55.0
    # Contraste: si el histograma no llena el rango, estirarlo un poco.
    rango = p99 - p1
    if rango < 0.85:
        adj.contrast = round(clip((0.85 - rango) * 55, 0, 28), 1)
    # Sombras y altas luces: abrir lo hundido y recuperar lo quemado.
    if p10 < 0.12:
        adj.shadows = round(clip((0.12 - p10) * 320, 0, 38), 1)
    if p90 > 0.9:
        adj.highlights = round(-clip((p90 - 0.9) * 380, 0, 38), 1)
    if p99 > 0.985 and p90 <= 0.9:
        adj.highlights = -10.0
    if p1 > 0.06:
        adj.blacks = round(-clip((p1 - 0.06) * 160, 0, 25), 1)
    if p99 < 0.9:
        adj.whites = round(clip((0.9 - p99) * 120, 0, 22), 1)
    # Color: un empujón suave, mayor si la foto está apagada.
    mx = muestra[opaco][:, :3].max(axis=1).astype(np.float32)
    mn = muestra[opaco][:, :3].min(axis=1).astype(np.float32)
    sat_media = float(np.mean((mx - mn) / np.maximum(mx, 1.0)))
    adj.vibrance = round(clip((0.45 - sat_media) * 60, 6, 28), 1)
    adj.saturation = 4.0 if sat_media < 0.5 else 0.0
    adj.clarity = 8.0
    if media >= 0.0:      # siempre un poco de nitidez
        adj.sharpen = 14.0
    return adj
