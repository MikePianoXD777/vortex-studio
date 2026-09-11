"""El monitor: muestra el cuadro compuesto, con letterbox."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from vortex_studio.media import Frame
from vortex_studio.model import ImageOverlay, Title
from vortex_studio.ui.compositor import compose, draw_overlay, draw_title, frame_to_image

BG = QColor("#101113")
LETTERBOX = QColor("#000000")
HINT = QColor("#6c727b")


class PreviewWidget(QWidget):
    """Dibuja el cuadro respetando su relación de aspecto."""

    fullscreen_toggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame: Frame | None = None
        self._overlays: list[tuple[ImageOverlay, QImage]] = []
        self._titles: list[Title] = []
        self._aspect = 16 / 9
        self._message = "Importa un video para empezar  ·  Ctrl+I"

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

    @property
    def is_empty(self) -> bool:
        return self._frame is None and not self._overlays and not self._titles

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BG)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self.is_empty:
            painter.setPen(HINT)
            painter.drawText(self.rect(), Qt.AlignCenter, self._message)
            painter.end()
            return

        if self._frame is not None:
            target = self._fit(self._frame.width / self._frame.height)
            painter.fillRect(self.rect(), LETTERBOX)
            painter.drawImage(target, frame_to_image(self._frame))
        else:
            # Sin video de fondo el lienzo es negro, pero el texto y las
            # imágenes se siguen viendo: así se puede armar una portada.
            target = self._fit(self._aspect)
            painter.fillRect(self.rect(), LETTERBOX)
            painter.fillRect(target, QColor("#000000"))

        for overlay, image in self._overlays:
            draw_overlay(painter, target, overlay, image)
        for title in self._titles:
            draw_title(painter, target, title)

        painter.end()

    def _fit(self, aspect: float) -> QRectF:
        """El rectángulo más grande con esa relación de aspecto que cabe."""
        w, h = self.width(), self.height()
        if w / h > aspect:
            fit_w, fit_h = h * aspect, float(h)
        else:
            fit_w, fit_h = float(w), w / aspect
        return QRectF((w - fit_w) / 2, (h - fit_h) / 2, fit_w, fit_h)

    def current_image(self) -> QImage | None:
        """El cuadro a resolución completa, para exportarlo."""
        if self.is_empty:
            return None

        if self._frame is not None:
            width, height = self._frame.width, self._frame.height
        else:
            height = 1080
            width = int(height * self._aspect)

        return compose(width, height, self._frame, self._overlays, self._titles)

    # --- pantalla completa ------------------------------------------------

    def mouseDoubleClickEvent(self, event) -> None:
        self.fullscreen_toggled.emit()

    def keyPressEvent(self, event) -> None:
        # Solo actúa cuando el preview es su propia ventana; si está dentro
        # del editor, la ventana principal ya maneja estas teclas.
        if self.isWindow() and event.key() in (Qt.Key_Escape, Qt.Key_F):
            self.fullscreen_toggled.emit()
        else:
            super().keyPressEvent(event)
