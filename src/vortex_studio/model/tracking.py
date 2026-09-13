"""Lo que se hace con un seguimiento: que algo siga al objeto.

El seguimiento (`media/tracking.py`) dice dónde está el objeto en el
**material**. La máscara y los textos se colocan sobre el **cuadro de
salida**. Entre los dos está el encuadre del clip —ajustar, rellenar o
estirar— y su transformación. Aquí se hace esa cuenta de ida y de vuelta,
y el resultado se escribe como **keyframes**, uno por cuadro de la
secuencia.

Keyframes y no un enlace vivo al seguimiento, como en After Effects: así el
resultado se ve en el editor de curvas, se corrige a mano el cuadro donde se
perdió, y se guarda y se deshace como cualquier otra animación.

Python puro.
"""

from __future__ import annotations

import math

import numpy as np

from vortex_studio.model import keyframes as kf
from vortex_studio.model.transform import FILL, STRETCH


def _rect(src_w: float, src_h: float, seq_w: float, seq_h: float, fit: str):
    """(izquierda, arriba, ancho, alto) del material en el cuadro, en pixeles de la secuencia.

    La misma cuenta que `fit_rect` del compositor, sin Qt.
    """
    if fit == STRETCH or src_w <= 0 or src_h <= 0 or seq_h <= 0:
        return 0.0, 0.0, float(seq_w), float(seq_h)
    material, cuadro = src_w / src_h, seq_w / seq_h
    if abs(material - cuadro) < 1e-6:
        return 0.0, 0.0, float(seq_w), float(seq_h)
    if (material > cuadro) != (fit == FILL):
        ancho, alto = seq_w, seq_w / material
    else:
        ancho, alto = seq_h * material, seq_h
    return (seq_w - ancho) / 2, (seq_h - alto) / 2, ancho, alto


def source_to_frame(sx: float, sy: float, src_size, seq_size, transform, local: float = 0.0):
    """Un punto del material —fracciones— en fracciones del cuadro de salida."""
    seq_w, seq_h = seq_size
    izq, arriba, ancho, alto = _rect(src_size[0], src_size[1], seq_w, seq_h, transform.fit)
    px, py = izq + sx * ancho, arriba + sy * alto
    v = transform.values_at(local)
    pivote_x = seq_w * (0.5 + transform.anchor_x)
    pivote_y = seq_h * (0.5 + transform.anchor_y)
    dx, dy = (px - pivote_x) * v["scale"], (py - pivote_y) * v["scale"]
    giro = math.radians(v["rotation"])
    rx = dx * math.cos(giro) - dy * math.sin(giro)
    ry = dx * math.sin(giro) + dy * math.cos(giro)
    return ((pivote_x + rx) / seq_w + v["x"], (pivote_y + ry) / seq_h + v["y"])


def frame_to_source(fx: float, fy: float, src_size, seq_size, transform, local: float = 0.0):
    """Lo contrario: un punto del cuadro de salida en fracciones del material."""
    seq_w, seq_h = seq_size
    v = transform.values_at(local)
    pivote_x = seq_w * (0.5 + transform.anchor_x)
    pivote_y = seq_h * (0.5 + transform.anchor_y)
    rx = (fx - v["x"]) * seq_w - pivote_x
    ry = (fy - v["y"]) * seq_h - pivote_y
    giro = -math.radians(v["rotation"])
    escala = max(1e-6, v["scale"])
    dx = (rx * math.cos(giro) - ry * math.sin(giro)) / escala
    dy = (rx * math.sin(giro) + ry * math.cos(giro)) / escala
    izq, arriba, ancho, alto = _rect(src_size[0], src_size[1], seq_w, seq_h, transform.fit)
    return ((pivote_x + dx - izq) / max(1e-6, ancho), (pivote_y + dy - arriba) / max(1e-6, alto))


def samples(clip, rows: np.ndarray, local_from: float, fps: float, src_size, seq_size):
    """`[(local, x, y)]` del cuadro de salida, un cuadro de la secuencia a la vez.

    Cada instante del clip pide su tiempo de archivo con `source_time`, así
    que la velocidad y el remapeo cuentan solos. Fuera de lo seguido no se
    inventa nada: se para.
    """
    if len(rows) == 0:
        return []
    salida = []
    paso = 1.0 / (fps if fps > 0 else 30.0)
    local = max(0.0, local_from)
    while local <= clip.duration + 1e-9:
        fuente = clip.source_time(clip.start + local)
        if fuente < rows[0, 0] - paso or fuente > rows[-1, 0] + paso:
            break
        sx = float(np.interp(fuente, rows[:, 0], rows[:, 1]))
        sy = float(np.interp(fuente, rows[:, 0], rows[:, 2]))
        fx, fy = source_to_frame(sx, sy, src_size, seq_size, clip.transform, local)
        salida.append((round(local, 4), fx, fy))
        local += paso
    return salida


def _merge(anteriores: list, nuevos: list, desde: float) -> list:
    """Los keyframes de antes de `desde` se quedan; de ahí en adelante mandan los nuevos."""
    quedan = [list(k) for k in anteriores if kf.time_of(k) < desde - kf.TIME_TOLERANCE]
    return kf.clean(quedan + nuevos)


def apply_to_mask(clip, puntos: list) -> int:
    """La máscara del clip sigue al objeto. Devuelve cuántos keyframes puso."""
    if not puntos:
        return 0
    desde = puntos[0][0]
    for ruta, indice in (("mask.x", 1), ("mask.y", 2)):
        nuevos = [[p[0], float(p[indice]), kf.LINEAR] for p in puntos]
        clip.anim[ruta] = _merge(clip.anim.get(ruta, []), nuevos, desde)
    return len(puntos)


def apply_to_item(item, clip, puntos: list) -> int:
    """Un texto o una imagen sigue al objeto, con la distancia que tenía al empezar.

    El texto se mueve lo mismo que el objeto, no se pega a su centro: uno lo
    pone al lado de la cara y así debe seguir.
    """
    if not puntos:
        return 0
    desde_clip = puntos[0][0]
    # El elemento tiene su propio tiempo local.
    corrimiento = clip.start - item.start
    from vortex_studio.model import animate

    local0 = desde_clip + corrimiento
    base_x = animate.value_at(item, "x", local0)
    base_y = animate.value_at(item, "y", local0)
    x0, y0 = puntos[0][1], puntos[0][2]
    filas_x, filas_y = [], []
    for local, x, y in puntos:
        propio = round(local + corrimiento, 4)
        if propio < 0 or propio > item.duration + 1e-9:
            continue
        filas_x.append([propio, base_x + (x - x0), kf.LINEAR])
        filas_y.append([propio, base_y + (y - y0), kf.LINEAR])
    if not filas_x:
        return 0
    item.anim["x"] = _merge(item.anim.get("x", []), filas_x, filas_x[0][0])
    item.anim["y"] = _merge(item.anim.get("y", []), filas_y, filas_y[0][0])
    return len(filas_x)
