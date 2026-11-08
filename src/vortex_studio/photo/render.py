"""PROVISIONAL: render con QPainter, sin ajustes ni filtros ni efectos."""

from __future__ import annotations

from collections.abc import Collection

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (KIND_ADJUST, KIND_IMAGE, KIND_SHAPE,
                                          KIND_TEXT, Document, Layer)

_MODES = {
    "Multiplicar": QPainter.CompositionMode_Multiply,
    "Oscurecer": QPainter.CompositionMode_Darken,
    "Aclarar": QPainter.CompositionMode_Lighten,
    "Superponer": QPainter.CompositionMode_Overlay,
    "Luz suave": QPainter.CompositionMode_SoftLight,
    "Luz fuerte": QPainter.CompositionMode_HardLight,
    "Diferencia": QPainter.CompositionMode_Difference,
    "Exclusión": QPainter.CompositionMode_Exclusion,
    "Trama": QPainter.CompositionMode_Screen,
}


def to_qimage(pixels: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(pixels, dtype=np.uint8)
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888).copy()


def from_qimage(image: QImage) -> np.ndarray:
    img = image.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=img.bytesPerLine() * h)
    return buf.reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4).copy()


class Renderer:
    def __init__(self, store: AssetStore) -> None:
        self.store = store

    def invalidate(self, layer_id: str | None = None) -> None:
        pass

    def _layer_pixels(self, layer: Layer, scale: float) -> np.ndarray | None:
        from vortex_studio.photo.shapes import render_shape
        from vortex_studio.photo.text import render_text
        if layer.kind == KIND_TEXT:
            return render_text(layer, scale)
        if layer.kind == KIND_SHAPE:
            return render_shape(layer, scale)
        if layer.kind == KIND_IMAGE and layer.asset and self.store.has(layer.asset):
            px = self.store.get(layer.asset)
            if layer.crop:
                x, y, w, h = (int(round(v)) for v in layer.crop)
                px = px[max(0, y): y + max(1, h), max(0, x): x + max(1, w)]
            img = to_qimage(px).scaled(
                max(1, round(layer.transform.width * scale)),
                max(1, round(layer.transform.height * scale)),
                Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            return from_qimage(img)
        return None

    def render_layer(self, doc: Document, layer: Layer, scale: float = 1.0) -> np.ndarray:
        px = self._layer_pixels(layer, scale)
        if px is None:
            return np.zeros((max(1, round(layer.transform.height * scale)),
                             max(1, round(layer.transform.width * scale)), 4), np.uint8)
        return px

    def render(self, doc: Document, scale: float = 1.0, *, hide: Collection[str] = (),
               original: bool = False) -> np.ndarray:
        w, h = max(1, round(doc.width * scale)), max(1, round(doc.height * scale))
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(doc.background) if doc.background else Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for layer in doc.layers:
            if not layer.visible or layer.id in hide or layer.kind == KIND_ADJUST:
                continue
            px = self._layer_pixels(layer, scale)
            if px is None:
                continue
            t = layer.transform
            p.save()
            p.translate(t.cx * scale, t.cy * scale)
            p.rotate(t.rotation)
            p.scale(-1 if t.flip_h else 1, -1 if t.flip_v else 1)
            p.setOpacity(layer.opacity)
            p.setCompositionMode(_MODES.get(layer.blend, QPainter.CompositionMode_SourceOver))
            qi = to_qimage(px)
            p.drawImage(QRectF(-qi.width() / 2, -qi.height() / 2, qi.width(), qi.height()), qi)
            p.restore()
        p.end()
        return from_qimage(img)

    def thumbnail(self, doc: Document, max_side: int) -> np.ndarray:
        return self.render(doc, max_side / max(doc.width, doc.height))
