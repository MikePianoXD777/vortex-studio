"""Capas de texto.

El texto se acomoda (líneas, ajuste al ancho de la caja) **siempre a escala
1**, en unidades del lienzo, y solo se dibuja escalado. Así el corte de líneas
es idéntico en la vista previa, en la exportación y en `text_height`, sin
importar el zoom: si no, un texto podría saltar de renglón al exportarlo.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextLayout, QTextOption

from ._util import ensure_qt, from_qimage, parse_color
from .document import Layer

_FALLBACK = "Sans Serif"


def _font(layer: Layer) -> QFont:
    f = QFont()
    f.setFamilies([layer.font_family or _FALLBACK, _FALLBACK])     # si no existe, la del sistema
    f.setPixelSize(max(1, int(round(layer.font_size))))
    # Sin hinting las medidas no cambian con el zoom.
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setBold(bool(layer.bold))
    f.setItalic(bool(layer.italic))
    f.setUnderline(bool(layer.underline))
    if layer.letter_spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(layer.letter_spacing))
    return f


def _lines(layer: Layer):
    """Acomoda el texto: lista de (QTextLayout, [(línea, x, y)]) por párrafo y
    el alto total. Devuelve `(layouts, alto)`."""
    ensure_qt()
    texto = layer.text.upper() if layer.uppercase else layer.text
    fuente = _font(layer)
    ancho = max(1.0, float(layer.transform.width))
    paso = max(1.0, float(layer.font_size) * float(layer.line_height))
    opcion = QTextOption()
    opcion.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layouts, y, n = [], 0.0, 0
    for parrafo in texto.split("\n"):
        lay = QTextLayout(parrafo, fuente)
        lay.setTextOption(opcion)
        lay.beginLayout()
        lineas = []
        while True:
            linea = lay.createLine()
            if not linea.isValid():
                break
            linea.setLineWidth(ancho)
            lineas.append(linea)
        if not lineas and parrafo == "":
            pass
        lay.endLayout()
        puestas = []
        for linea in lineas:
            nat = linea.naturalTextWidth()
            if layer.align == "center":
                x = (ancho - nat) / 2
            elif layer.align == "right":
                x = ancho - nat
            else:
                x = 0.0
            # Se centra el renglón dentro de su interlineado.
            ly = y + (paso - linea.height()) / 2
            linea.setPosition(QPointF(x, ly))
            puestas.append(linea)
            y += paso
            n += 1
        if not lineas:                       # renglón vacío (Enter doble)
            y += paso
            n += 1
        layouts.append(lay)
    return layouts, max(y, paso)


def text_height(layer: Layer) -> float:
    """Alto que necesita el texto con el ancho de la caja de la capa."""
    return float(_lines(layer)[1])


def render_text(layer: Layer, scale: float) -> np.ndarray:
    ensure_qt()
    w = max(1, int(round(layer.transform.width * scale)))
    h = max(1, int(round(layer.transform.height * scale)))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    if layer.text:
        layouts, _ = _lines(layer)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(scale, scale)
        r, g, b, a = parse_color(layer.color, (255, 255, 255, 255))
        p.setPen(QColor(r, g, b, a))
        for lay in layouts:
            lay.draw(p, QPointF(0, 0))
        p.end()
    return from_qimage(img)
