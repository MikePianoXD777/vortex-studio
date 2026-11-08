"""PROVISIONAL: formas con QPainter."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen

from vortex_studio.photo.document import Layer


def _path(shape: str, w: float, h: float, radius: float) -> QPainterPath:
    p = QPainterPath()
    r = QRectF(0, 0, w, h)
    if shape == "ellipse":
        p.addEllipse(r)
    elif shape == "triangle":
        p.moveTo(w / 2, 0); p.lineTo(w, h); p.lineTo(0, h); p.closeSubpath()
    elif shape == "star":
        c = QPointF(w / 2, h / 2)
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            k = 0.5 if i % 2 == 0 else 0.22
            pt = QPointF(c.x() + math.cos(ang) * w * k, c.y() + math.sin(ang) * h * k)
            p.moveTo(pt) if i == 0 else p.lineTo(pt)
        p.closeSubpath()
    elif shape == "heart":
        p.moveTo(w / 2, h)
        p.cubicTo(-w * 0.2, h * 0.4, w * 0.2, -h * 0.2, w / 2, h * 0.3)
        p.cubicTo(w * 0.8, -h * 0.2, w * 1.2, h * 0.4, w / 2, h)
    elif shape in ("line", "arrow"):
        p.moveTo(0, h / 2); p.lineTo(w, h / 2)
    elif radius > 0:
        p.addRoundedRect(r, radius, radius)
    else:
        p.addRect(r)
    return p


def render_shape(layer: Layer, scale: float) -> np.ndarray:
    from vortex_studio.photo.render import from_qimage
    w = max(1, round(layer.transform.width * scale))
    h = max(1, round(layer.transform.height * scale))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    fill = layer.fill if layer.shape not in ("line", "arrow") else None
    stroke = layer.stroke or (layer.fill if layer.shape in ("line", "arrow") else None)
    p.setBrush(QBrush(QColor(fill)) if fill else Qt.NoBrush)
    sw = layer.stroke_width or (6 if layer.shape in ("line", "arrow") else 0)
    p.setPen(QPen(QColor(stroke), sw) if stroke and sw else Qt.NoPen)
    p.drawPath(_path(layer.shape, layer.transform.width, layer.transform.height,
                     layer.corner_radius))
    p.end()
    return from_qimage(img)
