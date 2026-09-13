"""El monitor: muestra el cuadro compuesto, con letterbox."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QWidget

from vortex_studio.media import Frame
from vortex_studio.model import ImageOverlay, Title
from vortex_studio.ui import theme
from vortex_studio.ui.compositor import compose, draw_layers, draw_overlay, draw_title

# Dentro del editor el monitor es parte de su tarjeta: alrededor del cuadro va
# el color de la tarjeta y el cuadro lleva esquinas redondeadas. En pantalla
# completa todo es negro.
BG = QColor(theme.TARJETA)
LETTERBOX = QColor("#000000")
HINT = QColor(theme.MUY_TENUE)
RADIO = 10


class PreviewWidget(QWidget):
    """Dibuja el cuadro respetando su relación de aspecto."""

    fullscreen_toggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layers: list[tuple] = []
        self._overlays: list[tuple[ImageOverlay, QImage]] = []
        self._titles: list[Title] = []
        # El lienzo lo define la secuencia, no el archivo de origen: un
        # video horizontal metido en una secuencia vertical se acomoda
        # dentro, y el cuadro exportado debe salir vertical.
        self._canvas = (1920, 1080)
        self._time: float | None = None
        self._alpha = 1.0
        # Lo que hay que hacer antes de sacar el cuadro en limpio. La ventana
        # lo usa para esperar al cuadro exacto: pintar la pantalla nunca
        # espera, pero exportar un cuadro no puede salir con el anterior.
        self._before_grab = None
        self._message = "Importa un video para empezar  ·  Ctrl+I"

        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)

    # --- qué mostrar ------------------------------------------------------

    def set_layers(self, layers: list[tuple]) -> None:
        """Las capas de video, de abajo hacia arriba.

        Cada capa es (cuadro, opacidad) y opcionalmente su transformación.
        """
        # Una capa de color liso (fundido a negro) no trae cuadro y sí cuenta.
        self._layers = [capa for capa in layers
                        if capa[0] is not None or (len(capa) > 5 and capa[5] is not None)
                        or (len(capa) > 7 and capa[7] is not None)]
        self.update()

    def set_frame(self, frame: Frame | None, alpha: float = 1.0) -> None:
        self.set_layers([(frame, alpha)] if frame is not None else [])

    @property
    def _frame(self) -> Frame | None:
        return self._layers[0][0] if self._layers else None

    def set_time(self, t: float) -> None:
        """El instante que se está viendo, para que cada fundido se aplique."""
        self._time = t

    def set_overlays(self, overlays: list[tuple[ImageOverlay, QImage]]) -> None:
        self._overlays = overlays
        self.update()

    def set_titles(self, titles: list[Title]) -> None:
        self._titles = titles
        self.update()

    def set_canvas(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self._canvas = (width, height)
            self.update()

    @property
    def _aspect(self) -> float:
        return self._canvas[0] / self._canvas[1]

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    @property
    def is_empty(self) -> bool:
        return not self._layers and not self._overlays and not self._titles

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        fondo = LETTERBOX if self.isWindow() else BG
        painter.fillRect(self.rect(), fondo)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self.is_empty:
            painter.setPen(HINT)
            painter.drawText(self.rect(), Qt.AlignCenter, self._message)
            painter.end()
            return

        if self._layers:
            target = self._fit(self._aspect)
            painter.fillRect(target, LETTERBOX)
            if any(len(c) > 7 and c[7] is not None for c in self._layers):
                # Una capa de ajuste corrige lo ya pintado, y eso solo se puede
                # sobre una imagen: se compone al tamaño en pantalla y se pinta.
                imagen = compose(max(1, int(target.width())), max(1, int(target.height())),
                                 self._layers, [], [], None)
                painter.drawImage(target, imagen)
            else:
                draw_layers(painter, target, self._layers)
        else:
            # Sin video de fondo el lienzo es negro, pero el texto y las
            # imágenes se siguen viendo: así se puede armar una portada.
            target = self._fit(self._aspect)
            painter.fillRect(target, QColor("#000000"))

        t = self._time
        for overlay, image in self._overlays:
            draw_overlay(painter, target, overlay, image,
                         overlay.fade_at(t) if t is not None else 1.0, t)
        for title in self._titles:
            draw_title(painter, target, title,
                       title.fade_at(t) if t is not None else 1.0, t)

        if not self.isWindow():
            # Las esquinas se tapan después de pintar todo: recortar antes
            # chocaría con los recortes que ya usa el compositor.
            esquinas = QPainterPath()
            esquinas.addRect(target)
            redondo = QPainterPath()
            redondo.addRoundedRect(target, RADIO, RADIO)
            painter.fillPath(esquinas.subtracted(redondo), fondo)

        painter.end()

    def _fit(self, aspect: float) -> QRectF:
        """El rectángulo más grande con esa relación de aspecto que cabe."""
        w, h = self.width(), max(1, self.height())
        if w / h > aspect:
            fit_w, fit_h = h * aspect, float(h)
        else:
            fit_w, fit_h = float(w), w / aspect
        return QRectF((w - fit_w) / 2, (h - fit_h) / 2, fit_w, fit_h)

    def set_grab_hook(self, hook) -> None:
        self._before_grab = hook

    def current_image(self) -> QImage | None:
        """El cuadro a resolución completa, para exportarlo."""
        if self._before_grab is not None:
            self._before_grab()
        if self.is_empty:
            return None

        width, height = self._canvas
        return compose(width, height, self._layers, self._overlays,
                       self._titles, self._time)

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
