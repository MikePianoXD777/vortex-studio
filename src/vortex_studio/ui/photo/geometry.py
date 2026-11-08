"""Geometría del lienzo: cajas giradas, asas, escalado, giro e imán.

Todo son funciones puras sobre `Transform` y números (sin Qt) para poder
probarlas sin ventana. Coordenadas del lienzo: origen arriba a la izquierda,
y hacia abajo; un giro positivo va a favor del reloj, como en `document.py`.
"""

from __future__ import annotations

import math
from dataclasses import replace

from vortex_studio.photo.document import Transform

# Las 8 asas y hacia dónde apuntan: (-1, -1) = esquina de arriba a la izquierda.
HANDLES = {
    "nw": (-1, -1), "n": (0, -1), "ne": (1, -1), "e": (1, 0),
    "se": (1, 1), "s": (0, 1), "sw": (-1, 1), "w": (-1, 0),
}
CORNERS = ("nw", "ne", "se", "sw")
MIN_SIZE = 8.0


def rot(x: float, y: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def to_local(t: Transform, x: float, y: float) -> tuple[float, float]:
    """Un punto del lienzo, en el marco de la caja (origen en su centro, sin girar)."""
    return rot(x - t.cx, y - t.cy, -t.rotation)


def to_canvas(t: Transform, lx: float, ly: float) -> tuple[float, float]:
    rx, ry = rot(lx, ly, t.rotation)
    return t.cx + rx, t.cy + ry


def corners(t: Transform) -> list[tuple[float, float]]:
    w, h = t.width / 2, t.height / 2
    return [to_canvas(t, x, y) for x, y in ((-w, -h), (w, -h), (w, h), (-w, h))]


def contains(t: Transform, x: float, y: float, pad: float = 0.0) -> bool:
    lx, ly = to_local(t, x, y)
    return abs(lx) <= t.width / 2 + pad and abs(ly) <= t.height / 2 + pad


def bbox(transforms) -> tuple[float, float, float, float] | None:
    """Caja alineada a los ejes que envuelve a todas (con sus giros)."""
    pts = [p for t in transforms for p in corners(t)]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def box_transform(b: tuple[float, float, float, float]) -> Transform:
    x0, y0, x1, y1 = b
    return Transform((x0 + x1) / 2, (y0 + y1) / 2, max(1.0, x1 - x0), max(1.0, y1 - y0))


def selection_box(transforms) -> Transform | None:
    """La caja con asas: la de la capa si es una sola (girada), o el envolvente."""
    ts = list(transforms)
    if not ts:
        return None
    if len(ts) == 1:
        return replace(ts[0])
    return box_transform(bbox(ts))


def handle_points(t: Transform) -> dict[str, tuple[float, float]]:
    return {n: to_canvas(t, hx * t.width / 2, hy * t.height / 2)
            for n, (hx, hy) in HANDLES.items()}


def rotate_handle_point(t: Transform, offset: float) -> tuple[float, float]:
    """El asa de giro: sobre el borde de arriba, `offset` unidades del lienzo."""
    return to_canvas(t, 0, -t.height / 2 - offset)


def resize_transform(t: Transform, handle: str, px: float, py: float,
                     proportional: bool, min_size: float = MIN_SIZE) -> Transform:
    """La caja `t` con el asa `handle` llevada al punto (px, py) del lienzo.

    El lado opuesto queda fijo. No se deja pasar al otro lado (no voltea): se
    detiene en `min_size`.
    """
    hx, hy = HANDLES[handle]
    lx, ly = to_local(t, px, py)
    w, h = t.width, t.height
    ax, ay = -hx * w / 2, -hy * h / 2
    nw, nh = w, h
    if hx:
        nw = max(min_size, hx * (lx - ax))
    if hy:
        nh = max(min_size, hy * (ly - ay))
    if proportional and hx and hy:
        k = max(nw / w, nh / h, min_size / min(w, h))
        nw, nh = w * k, h * k
    ncx = ax + hx * nw / 2 if hx else 0.0
    ncy = ay + hy * nh / 2 if hy else 0.0
    cx, cy = to_canvas(t, ncx, ncy)
    return replace(t, cx=cx, cy=cy, width=nw, height=nh)


def angle_to(cx: float, cy: float, px: float, py: float) -> float:
    return math.degrees(math.atan2(py - cy, px - cx))


def normalize_angle(a: float) -> float:
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def snap_angle(a: float, step: float = 15.0) -> float:
    return round(a / step) * step


def rotate_point(x: float, y: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
    rx, ry = rot(x - cx, y - cy, deg)
    return cx + rx, cy + ry


# --- imán y guías ----------------------------------------------------------

def compute_snap(box: tuple[float, float, float, float],
                 others: list[tuple[float, float, float, float]],
                 doc_w: float, doc_h: float, threshold: float):
    """Cuánto correr `box` para que su centro o un borde caiga en una guía.

    Devuelve `(dx, dy, guias)`; cada guía es `(eje, posicion, desde, hasta,
    tipo)` con eje "v" (línea vertical) o "h", y tipo "lienzo" o "capa".
    """
    x0, y0, x1, y1 = box
    ax = [x0, (x0 + x1) / 2, x1]
    ay = [y0, (y0 + y1) / 2, y1]
    tx = [(0.0, "lienzo", None), (doc_w / 2, "lienzo", None), (doc_w, "lienzo", None)]
    ty = [(0.0, "lienzo", None), (doc_h / 2, "lienzo", None), (doc_h, "lienzo", None)]
    for o in others:
        ox0, oy0, ox1, oy1 = o
        tx += [(ox0, "capa", o), ((ox0 + ox1) / 2, "capa", o), (ox1, "capa", o)]
        ty += [(oy0, "capa", o), ((oy0 + oy1) / 2, "capa", o), (oy1, "capa", o)]

    def mejor(anclas, objetivos):
        best = None
        for a in anclas:
            for t, _, _ in objetivos:
                d = t - a
                if abs(d) <= threshold and (best is None or abs(d) < abs(best)):
                    best = d
        return best

    dx = mejor(ax, tx)
    dy = mejor(ay, ty)
    sx = dx or 0.0
    sy = dy or 0.0
    guias = []
    nx0, ny0, nx1, ny1 = x0 + sx, y0 + sy, x1 + sx, y1 + sy
    if dx is not None:
        for a in (nx0, (nx0 + nx1) / 2, nx1):
            for t, tipo, o in tx:
                if abs(t - a) < 0.5:
                    if tipo == "lienzo":
                        guias.append(("v", t, 0.0, doc_h, tipo))
                    else:
                        guias.append(("v", t, min(ny0, o[1]), max(ny1, o[3]), tipo))
    if dy is not None:
        for a in (ny0, (ny0 + ny1) / 2, ny1):
            for t, tipo, o in ty:
                if abs(t - a) < 0.5:
                    if tipo == "lienzo":
                        guias.append(("h", t, 0.0, doc_w, tipo))
                    else:
                        guias.append(("h", t, min(nx0, o[0]), max(nx1, o[2]), tipo))
    return sx, sy, guias
