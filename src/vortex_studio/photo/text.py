"""PROVISIONAL: texto con QTextDocument."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument)

from vortex_studio.photo.document import Layer

_ALIGN = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight}


def _document(layer: Layer, scale: float = 1.0) -> QTextDocument:
    doc = QTextDocument()
    font = QFont(layer.font_family)
    font.setPixelSize(max(1, int(round(layer.font_size))))
    font.setBold(layer.bold)
    font.setItalic(layer.italic)
    font.setUnderline(layer.underline)
    font.setLetterSpacing(QFont.AbsoluteSpacing, layer.letter_spacing)
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0)
    doc.setTextWidth(max(1.0, layer.transform.width))
    doc.setPlainText(layer.text.upper() if layer.uppercase else layer.text)
    cur = QTextCursor(doc)
    cur.select(QTextCursor.Document)
    char = QTextCharFormat()
    char.setForeground(QColor(layer.color))
    cur.mergeCharFormat(char)
    block = QTextBlockFormat()
    block.setAlignment(_ALIGN.get(layer.align, Qt.AlignHCenter))
    block.setLineHeight(layer.line_height * 100, 1)   # proporcional
    cur.mergeBlockFormat(block)
    return doc


def text_height(layer: Layer) -> float:
    return float(_document(layer).size().height())


def render_text(layer: Layer, scale: float) -> np.ndarray:
    from vortex_studio.photo.render import from_qimage
    w = max(1, round(layer.transform.width * scale))
    h = max(1, round(layer.transform.height * scale))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.scale(scale, scale)
    _document(layer).drawContents(p)
    p.end()
    return from_qimage(img)
