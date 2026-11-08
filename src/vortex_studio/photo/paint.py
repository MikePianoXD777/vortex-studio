"""PROVISIONAL: pincel simple con QPainter; varita y fondo devuelven máscara vacía."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from vortex_studio.photo.render import from_qimage, to_qimage


@dataclass
class Brush:
    size: float = 30
    hardness: float = 0.8
    opacity: float = 1.0
    color: str = "#000000"
    mode: str = "paint"


def _dibujar(arr: np.ndarray, points, brush: Brush, color: QColor, erase: bool) -> np.ndarray:
    img = to_qimage(arr)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    if erase:
        p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    color.setAlphaF(brush.opacity)
    p.setPen(QPen(color, brush.size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    pts = [QPointF(x, y) for x, y, _ in points]
    if len(pts) == 1:
        p.drawPoint(pts[0])
    elif pts:
        p.drawPolyline(pts)
    p.end()
    return from_qimage(img)


def stroke(pixels, points, brush: Brush) -> np.ndarray:
    return _dibujar(pixels, points, brush, QColor(brush.color), brush.mode == "erase")


def stroke_mask(mask, points, brush: Brush) -> np.ndarray:
    rgba = np.zeros(mask.shape + (4,), np.uint8)
    rgba[..., :3] = mask[..., None]
    rgba[..., 3] = 255
    gris = "#ffffff" if brush.mode == "paint" else "#000000"
    out = _dibujar(rgba, points, Brush(brush.size, brush.hardness, 1.0, gris), QColor(gris), False)
    return out[..., 0].copy()


def clone(pixels, points, brush: Brush, offset) -> np.ndarray:
    return pixels.copy()


def magic_wand(pixels, x: int, y: int, tolerance: float = 32, contiguous: bool = True) -> np.ndarray:
    return np.zeros(pixels.shape[:2], np.uint8)


def remove_background(pixels) -> np.ndarray:
    return np.full(pixels.shape[:2], 255, np.uint8)
