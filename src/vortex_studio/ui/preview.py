"""El monitor: compone el cuadro final.

El orden de pintado es el de cualquier editor — video de fondo, luego las
imágenes de las pistas superiores, y el texto hasta arriba.

Las imágenes y el texto se componen aquí con QPainter en vez de mandarlos al
grafo de FFmpeg: son pocos elementos y así se pueden mover en vivo sin
reconstruir nada.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from vortex_studio.media import Frame
from vortex_studio.model import ImageOverlay, Title

BG = QColor("#101113")
LETTERBOX = QColor("#000000")
HINT = QColor("#6c727b")
OUTLINE = QColor(0, 0, 0, 235)
CAPTION_BOX = QColor(0, 0, 0, 150)

ALIGN_FLAGS = {
    "izquierda": Qt.AlignLeft,
    "centro": Qt.AlignHCenter,
    "derecha": Qt.AlignRight,
}


class PreviewWidget(QWidget):
    """Dibuja el cuadro respetando su relación de aspecto (letterbox)."""

    fullscreen_toggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame: Frame | None = None
        self._overlays: list[tuple[ImageOverlay, QImage]] = []
        self._titles: list[Title] = []
        self._aspect = 16 / 9
        self._message = "Abre un video para empezar  ·  Ctrl+O"

        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)

    # --- qué mostrar ------------------------------------------------------

    def set_frame(self, frame: Frame | None) -> None:
        self._frame = frame
        self.update()

    def set_overlays(self, overlays: list[tuple[ImageOverlay, QImage]]) -> None:
        self._overlays = overlays
        self.update()

    def set_titles(self, titles: list[Title]) -> None:
        self._titles = titles
        self.update()

    def set_aspect(self, aspect: float) -> None:
        self._aspect = aspect or (16 / 9)
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BG)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        empty = self._frame is None and not self._overlays and not self._titles
        if empty:
            painter.setPen(HINT)
            painter.drawText(self.rect(), Qt.AlignCenter, self._message)
            painter.end()
            return

        if self._frame is not None:
            frame = self._frame
            target = self._fit(frame.width / frame.height)
            image = QImage(frame.data, frame.width, frame.height,
                           frame.stride, QImage.Format_RGB888)
            painter.fillRect(self.rect(), LETTERBOX)
            painter.drawImage(target, image)
        else:
            # Sin video de fondo el lienzo es negro, pero el texto y las
            # imágenes se siguen viendo: así se puede armar una portada.
            target = self._fit(self._aspect)
            painter.fillRect(self.rect(), LETTERBOX)
            painter.fillRect(target, QColor("#000000"))

        for overlay, image in self._overlays:
            self._draw_overlay(painter, target, overlay, image)

        for title in self._titles:
            self._draw_title(painter, target, title)

        painter.end()

    def _draw_overlay(self, painter: QPainter, target: QRectF,
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

    def _draw_title(self, painter: QPainter, target: QRectF, title: Title) -> None:
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

        if title.align == "izquierda":
            left = anchor_x
        elif title.align == "derecha":
            left = anchor_x - widest
        else:
            left = anchor_x - widest / 2

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
            self._draw_line(painter, row, line, font, metrics, title)

    def _draw_line(self, painter: QPainter, row: QRectF, line: str,
                   font: QFont, metrics: QFontMetricsF, title: Title) -> None:
        """El contorno se dibuja como trazo de un path, no como texto repetido.

        Repetir el texto desplazado deja bordes sucios en las diagonales; el
        trazo sobre el contorno real queda parejo en todas las direcciones.
        """
        flags = ALIGN_FLAGS.get(title.align, Qt.AlignHCenter)
        if flags == Qt.AlignLeft:
            x = row.left()
        elif flags == Qt.AlignRight:
            x = row.right() - metrics.horizontalAdvance(line)
        else:
            x = row.center().x() - metrics.horizontalAdvance(line) / 2
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

    def _fit(self, aspect: float) -> QRectF:
        """El rectángulo más grande con esa relación de aspecto que cabe."""
        w, h = self.width(), self.height()
        if w / h > aspect:
            fit_w, fit_h = h * aspect, float(h)
        else:
            fit_w, fit_h = float(w), w / aspect
        return QRectF((w - fit_w) / 2, (h - fit_h) / 2, fit_w, fit_h)

    # --- imagen y pantalla completa ---------------------------------------

    def current_image(self) -> QImage | None:
        """Lo que se ve, con imágenes y texto incluidos, listo para guardar."""
        if self._frame is None and not self._overlays and not self._titles:
            return None

        if self._frame is not None:
            width, height = self._frame.width, self._frame.height
        else:
            height = 1080
            width = int(height * self._aspect)

        canvas = QImage(width, height, QImage.Format_RGB888)
        canvas.fill(Qt.black)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        target = QRectF(0, 0, width, height)

        if self._frame is not None:
            frame = self._frame
            painter.drawImage(target, QImage(frame.data, frame.width, frame.height,
                                             frame.stride, QImage.Format_RGB888))
        for overlay, image in self._overlays:
            self._draw_overlay(painter, target, overlay, image)
        for title in self._titles:
            self._draw_title(painter, target, title)
        painter.end()

        return canvas

    def mouseDoubleClickEvent(self, event) -> None:
        self.fullscreen_toggled.emit()

    def keyPressEvent(self, event) -> None:
        # Solo actúa cuando el preview es su propia ventana; si está dentro
        # del editor, la ventana principal ya maneja estas teclas.
        if self.isWindow() and event.key() in (Qt.Key_Escape, Qt.Key_F):
            self.fullscreen_toggled.emit()
        else:
            super().keyPressEvent(event)
