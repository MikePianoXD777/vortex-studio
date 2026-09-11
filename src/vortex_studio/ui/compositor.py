"""Compone el cuadro final: video de fondo, imágenes encima, texto hasta arriba.

Vive aparte porque lo usan dos cosas con necesidades distintas: el preview,
que dibuja sobre el widget al tamaño que tenga la ventana, y la exportación,
que dibuja sobre un lienzo del tamaño real de la secuencia.

Tener una sola implementación es lo que garantiza que lo exportado se vea
igual que lo que viste al editar. Si fueran dos, tarde o temprano un
subtítulo saldría en otro lugar en el archivo final.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen

from vortex_studio.media import Frame
from vortex_studio.model import ImageOverlay, Title

OUTLINE = QColor(0, 0, 0, 235)
CAPTION_BOX = QColor(0, 0, 0, 150)

ALIGN_OFFSET = {
    "izquierda": 0.0,
    "centro": 0.5,
    "derecha": 1.0,
}


def frame_to_image(frame: Frame) -> QImage:
    """Envuelve los bytes del cuadro sin copiarlos."""
    return QImage(frame.data, frame.width, frame.height,
                  frame.stride, QImage.Format_RGB888)


def draw_overlay(painter: QPainter, target: QRectF,
                 overlay: ImageOverlay, image: QImage) -> None:
    if image.isNull():
        return

    width = target.width() * overlay.scale
    height = width * (image.height() / image.width())
    rect = QRectF(target.left() + target.width() * overlay.x - width / 2,
                  target.top() + target.height() * overlay.y - height / 2,
                  width, height)

    painter.save()
    painter.setOpacity(max(0.0, min(1.0, overlay.opacity)))
    painter.drawImage(rect, image)
    painter.restore()


def draw_title(painter: QPainter, target: QRectF, title: Title) -> None:
    if not title.text.strip():
        return

    font = QFont()
    font.setPixelSize(max(8, int(target.height() * title.size)))
    font.setBold(title.bold)
    font.setItalic(title.italic)

    metrics = QFontMetricsF(font)
    lines = title.text.splitlines() or [""]
    line_height = metrics.height()
    block_height = line_height * len(lines)
    widest = max(metrics.horizontalAdvance(line) for line in lines)

    anchor_x = target.left() + target.width() * title.x
    anchor_y = target.top() + target.height() * title.y
    left = anchor_x - widest * ALIGN_OFFSET.get(title.align, 0.5)
    block = QRectF(left, anchor_y - block_height / 2, widest, block_height)

    if title.background:
        pad = line_height * 0.22
        painter.setPen(Qt.NoPen)
        painter.setBrush(CAPTION_BOX)
        painter.drawRoundedRect(block.adjusted(-pad, -pad / 2, pad, pad / 2), 4, 4)

    painter.setFont(font)
    for index, line in enumerate(lines):
        row = QRectF(block.left(), block.top() + index * line_height,
                     block.width(), line_height)
        _draw_line(painter, row, line, font, metrics, title)


def _draw_line(painter: QPainter, row: QRectF, line: str, font: QFont,
               metrics: QFontMetricsF, title: Title) -> None:
    """El contorno se traza sobre el contorno real de la letra.

    Repetir el texto desplazado en ocho direcciones deja bordes sucios en
    las diagonales; trazar el path queda parejo en todas.
    """
    x = row.left() + (row.width() - metrics.horizontalAdvance(line)) * \
        ALIGN_OFFSET.get(title.align, 0.5)
    baseline = row.top() + metrics.ascent()

    if title.outline:
        path = QPainterPath()
        path.addText(QPointF(x, baseline), font, line)
        width = max(1.5, font.pixelSize() * 0.055)
        painter.setPen(QPen(OUTLINE, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    painter.setPen(QColor(title.color))
    painter.drawText(QPointF(x, baseline), line)


def compose(width: int, height: int, frame: Frame | None,
            overlays: list[tuple[ImageOverlay, QImage]],
            titles: list[Title]) -> QImage:
    """Dibuja el cuadro completo sobre un lienzo nuevo del tamaño pedido."""
    canvas = QImage(width, height, QImage.Format_RGB888)
    canvas.fill(Qt.black)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    target = QRectF(0, 0, width, height)

    if frame is not None:
        painter.drawImage(target, frame_to_image(frame))
    for overlay, image in overlays:
        draw_overlay(painter, target, overlay, image)
    for title in titles:
        draw_title(painter, target, title)
    painter.end()

    return canvas
