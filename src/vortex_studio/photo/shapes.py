"""Formas vectoriales: se dibujan con `QPainter` y antialias en la caja de la
capa, así que quedan nítidas a cualquier escala."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from ._util import ensure_qt, from_qimage, parse_color
from .document import Layer


def _color(texto, por_omision=None):
    if not texto:
        return None
    r, g, b, a = parse_color(texto, por_omision or (0, 0, 0, 255))
    return QColor(r, g, b, a)


def _estrella(rect: QRectF, puntas: int = 5, interior: float = 0.4) -> QPolygonF:
    cx, cy = rect.center().x(), rect.center().y()
    rx, ry = rect.width() / 2, rect.height() / 2
    pts = []
    for i in range(puntas * 2):
        ang = -math.pi / 2 + i * math.pi / puntas
        k = 1.0 if i % 2 == 0 else interior
        pts.append(QPointF(cx + math.cos(ang) * rx * k, cy + math.sin(ang) * ry * k))
    return QPolygonF(pts)


def _corazon(rect: QRectF) -> QPainterPath:
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p = QPainterPath()
    p.moveTo(x + w * 0.5, y + h * 0.95)
    p.cubicTo(x + w * 0.05, y + h * 0.62, x - w * 0.02, y + h * 0.18, x + w * 0.27, y + h * 0.06)
    p.cubicTo(x + w * 0.42, y + h * 0.0, x + w * 0.5, y + h * 0.16, x + w * 0.5, y + h * 0.25)
    p.cubicTo(x + w * 0.5, y + h * 0.16, x + w * 0.58, y + h * 0.0, x + w * 0.73, y + h * 0.06)
    p.cubicTo(x + w * 1.02, y + h * 0.18, x + w * 0.95, y + h * 0.62, x + w * 0.5, y + h * 0.95)
    p.closeSubpath()
    return p


def render_shape(layer: Layer, scale: float) -> np.ndarray:
    ensure_qt()
    w = max(1, int(round(layer.transform.width * scale)))
    h = max(1, int(round(layer.transform.height * scale)))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    relleno = _color(layer.fill)
    borde = _color(layer.stroke)
    grosor = max(0.0, float(layer.stroke_width)) * scale
    forma = layer.shape
    es_linea = forma in ("line", "arrow")

    if es_linea:
        # Las líneas no tienen relleno: usan el borde (o el relleno) como tinta.
        tinta = borde or relleno or QColor(0, 0, 0)
        g = grosor if grosor > 0 else max(2.0, 4.0 * scale)
        p.setPen(QPen(tinta, g, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        m = g / 2
        y = h / 2
        x0, x1 = m, w - m
        if x1 <= x0:
            x0, x1 = 0.0, float(w)
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        if forma == "arrow":
            largo = min(max(g * 3.5, 6.0), max(w * 0.5, 1.0))
            ab = min(largo * 0.7, h / 2 - m if h / 2 > m else largo * 0.7)
            p.drawLine(QPointF(x1, y), QPointF(x1 - largo, y - ab))
            p.drawLine(QPointF(x1, y), QPointF(x1 - largo, y + ab))
        p.end()
        return from_qimage(img)

    pluma = QPen(borde, grosor, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                 Qt.PenJoinStyle.MiterJoin if forma in ("triangle", "star") else Qt.PenJoinStyle.RoundJoin) \
        if borde is not None and grosor > 0 else QPen(Qt.PenStyle.NoPen)
    p.setPen(pluma)
    p.setBrush(QBrush(relleno) if relleno is not None else QBrush(Qt.BrushStyle.NoBrush))
    m = grosor / 2 if borde is not None and grosor > 0 else 0.0     # el borde queda dentro de la caja
    r = QRectF(m, m, max(0.0, w - 2 * m), max(0.0, h - 2 * m))
    if forma == "ellipse":
        p.drawEllipse(r)
    elif forma == "triangle":
        p.drawPolygon(QPolygonF([QPointF(r.center().x(), r.top()), QPointF(r.right(), r.bottom()),
                                 QPointF(r.left(), r.bottom())]))
    elif forma == "star":
        p.drawPolygon(_estrella(r))
    elif forma == "heart":
        p.drawPath(_corazon(r))
    else:                                    # rect
        radio = min(max(0.0, float(layer.corner_radius)) * scale, r.width() / 2, r.height() / 2)
        if radio > 0:
            p.drawRoundedRect(r, radio, radio)
        else:
            p.drawRect(r)
    p.end()
    return from_qimage(img)
