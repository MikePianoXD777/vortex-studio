"""Las cuentas del modo recortar.

Recortar es mover el rectángulo de `Layer.crop` (en píxeles de la imagen
original) y, a la vez, acomodar la caja de la capa para que lo que se ve
no cambie de tamaño. Todo se hace en el marco local de la capa (origen en
el centro de su caja, sin girar), donde el rectángulo de recorte siempre
queda derecho aunque la capa esté girada o volteada.
"""

from __future__ import annotations

from vortex_studio.photo.document import Layer
from vortex_studio.ui.photo import geometry as geo

RATIOS = {"Libre": None, "1:1": 1.0, "4:5": 4 / 5, "9:16": 9 / 16, "16:9": 16 / 9}


class CropMath:
    def __init__(self, layer: Layer, image_size: tuple[int, int]) -> None:
        self.layer = layer
        self.iw, self.ih = image_size
        c = layer.crop or (0.0, 0.0, float(self.iw), float(self.ih))
        self.cx0, self.cy0, self.cw, self.ch = c
        t = layer.transform
        self.kx = t.width / max(1e-6, self.cw)       # unidades del lienzo por píxel de imagen
        self.ky = t.height / max(1e-6, self.ch)
        self.sx = -1.0 if t.flip_h else 1.0
        self.sy = -1.0 if t.flip_v else 1.0
        self._ccx = self.cx0 + self.cw / 2
        self._ccy = self.cy0 + self.ch / 2

    def u_to_local(self, u: float) -> float:
        return self.sx * (u - self._ccx) * self.kx

    def v_to_local(self, v: float) -> float:
        return self.sy * (v - self._ccy) * self.ky

    def local_to_u(self, lx: float) -> float:
        return self._ccx + self.sx * lx / self.kx

    def local_to_v(self, ly: float) -> float:
        return self._ccy + self.sy * ly / self.ky

    def full_rect(self) -> tuple[float, float, float, float]:
        xs = sorted((self.u_to_local(0), self.u_to_local(self.iw)))
        ys = sorted((self.v_to_local(0), self.v_to_local(self.ih)))
        return xs[0], ys[0], xs[1], ys[1]

    def current_rect(self) -> tuple[float, float, float, float]:
        t = self.layer.transform
        return -t.width / 2, -t.height / 2, t.width / 2, t.height / 2

    def result(self, rect: tuple[float, float, float, float]):
        """`(crop, Transform)` que deja a la capa mostrando justo `rect`."""
        x0, y0, x1, y1 = rect
        us = sorted((self.local_to_u(x0), self.local_to_u(x1)))
        vs = sorted((self.local_to_v(y0), self.local_to_v(y1)))
        us = (max(0.0, us[0]), min(float(self.iw), us[1]))
        vs = (max(0.0, vs[0]), min(float(self.ih), vs[1]))
        crop = (us[0], vs[0], max(1.0, us[1] - us[0]), max(1.0, vs[1] - vs[0]))
        t = self.layer.transform
        ncx, ncy = geo.to_canvas(t, (x0 + x1) / 2, (y0 + y1) / 2)
        from dataclasses import replace
        return crop, replace(t, cx=ncx, cy=ncy, width=max(1.0, x1 - x0), height=max(1.0, y1 - y0))


def clamp_rect(rect, bounds, min_size: float = 8.0):
    """Mete el rectángulo dentro de `bounds` sin cambiar su tamaño si cabe."""
    x0, y0, x1, y1 = rect
    bx0, by0, bx1, by1 = bounds
    w = min(max(min_size, x1 - x0), bx1 - bx0)
    h = min(max(min_size, y1 - y0), by1 - by0)
    x0 = min(max(bx0, x0), bx1 - w)
    y0 = min(max(by0, y0), by1 - h)
    return x0, y0, x0 + w, y0 + h


def fit_ratio(rect, ratio: float):
    """El rectángulo más grande de esa proporción dentro de `rect`, centrado."""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    if w / h > ratio:
        w = h * ratio
    else:
        h = w / ratio
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def drag_handle(rect, handle: str, px: float, py: float, bounds, ratio: float | None,
                min_size: float = 8.0):
    """El rectángulo con el asa llevada a (px, py), sin salirse de `bounds`.

    El lado (o la esquina) opuesto al asa queda fijo. Con `ratio` conserva la
    proporción: el rectángulo crece hasta donde lo dejan la imagen y el puntero.
    """
    hx, hy = geo.HANDLES[handle]
    x0, y0, x1, y1 = rect
    bx0, by0, bx1, by1 = bounds
    px = min(max(px, bx0), bx1)
    py = min(max(py, by0), by1)
    ax = x0 if hx > 0 else x1 if hx < 0 else (x0 + x1) / 2
    ay = y0 if hy > 0 else y1 if hy < 0 else (y0 + y1) / 2
    w = abs(px - ax) if hx else x1 - x0
    h = abs(py - ay) if hy else y1 - y0
    if ratio:
        if hx and hy:
            w = max(w, h * ratio)
        elif hx:
            pass
        else:
            w = h * ratio
        h = w / ratio
        wmax = (bx1 - ax) if hx > 0 else (ax - bx0) if hx < 0 else 2 * min(ax - bx0, bx1 - ax)
        hmax = (by1 - ay) if hy > 0 else (ay - by0) if hy < 0 else 2 * min(ay - by0, by1 - ay)
        k = min(1.0, wmax / max(w, 1e-6), hmax / max(h, 1e-6))
        w, h = w * k, h * k
        if w < min_size or h < min_size:
            k = max(min_size / w, min_size / h)
            w, h = w * k, h * k
    w, h = max(w, min_size), max(h, min_size)
    nx0 = ax if hx > 0 else ax - w if hx < 0 else ax - w / 2
    ny0 = ay if hy > 0 else ay - h if hy < 0 else ay - h / 2
    return clamp_rect((nx0, ny0, nx0 + w, ny0 + h), bounds, min_size)
