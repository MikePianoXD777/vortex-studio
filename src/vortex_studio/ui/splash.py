"""Pantalla de carga.

Cubre lo que de verdad tarda al arrancar: importar PyAV (que jala FFmpeg
entero) y construir los widgets. Por eso `app.py` difiere esos imports
hasta después de mostrar esta ventana.

El gráfico se dibuja con QPainter en vez de cargar un PNG: así no hay que
empacar archivos sueltos en el ejecutable ni preocuparse por rutas.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen, QWidget

WIDTH, HEIGHT = 520, 300

BG_TOP = QColor("#202329")
BG_BOTTOM = QColor("#141619")
BORDER = QColor("#31363d")
ACCENT = QColor("#e0574a")
TITLE = QColor("#f0f3f6")
SUBTITLE = QColor("#878d96")
STATUS = QColor("#9aa1aa")


class SplashScreen(QSplashScreen):
    """Splash con mensajes de estado y un tiempo mínimo en pantalla."""

    def __init__(self, version: str = "") -> None:
        self._version = version
        ratio = QApplication.primaryScreen().devicePixelRatio()

        super().__init__(self._render(ratio))
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self._shown_at = time.monotonic()

    # --- dibujo -----------------------------------------------------------

    def _render(self, ratio: float) -> QPixmap:
        """Dibuja el splash a la resolución real de la pantalla."""
        pixmap = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        card = QRectF(0, 0, WIDTH, HEIGHT).adjusted(0.5, 0.5, -0.5, -0.5)

        gradient = QLinearGradient(0, 0, 0, HEIGHT)
        gradient.setColorAt(0.0, BG_TOP)
        gradient.setColorAt(1.0, BG_BOTTOM)
        painter.setBrush(gradient)
        painter.setPen(QPen(BORDER, 1))
        painter.drawRoundedRect(card, 10, 10)

        # Barra de acento: el mismo rojo del playhead del timeline.
        painter.setPen(Qt.NoPen)
        painter.setBrush(ACCENT)
        painter.drawRoundedRect(QRectF(44, 112, 52, 3), 1.5, 1.5)

        title = QFont()
        title.setPointSize(27)
        title.setWeight(QFont.DemiBold)
        title.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        painter.setFont(title)
        painter.setPen(TITLE)
        painter.drawText(QRectF(44, 58, WIDTH - 88, 46),
                         Qt.AlignLeft | Qt.AlignVCenter, "VORTEX STUDIO")

        subtitle = QFont()
        subtitle.setPointSize(9)
        subtitle.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        painter.setFont(subtitle)
        painter.setPen(SUBTITLE)
        painter.drawText(QRectF(44, 126, WIDTH - 88, 22),
                         Qt.AlignLeft | Qt.AlignVCenter, "Editor de video no lineal")

        if self._version:
            painter.setPen(QColor("#5c626b"))
            painter.drawText(QRectF(0, HEIGHT - 44, WIDTH - 44, 20),
                             Qt.AlignRight | Qt.AlignVCenter, f"v{self._version}")

        painter.end()
        return pixmap

    def drawContents(self, painter: QPainter) -> None:
        """Qt centra el mensaje por default; aquí lo queremos abajo a la izquierda."""
        painter.setPen(STATUS)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(44, HEIGHT - 44, WIDTH - 88, 20),
                         Qt.AlignLeft | Qt.AlignVCenter, self.message())

    # --- estado -----------------------------------------------------------

    def ensure_painted(self, timeout: float = 0.4) -> None:
        """Espera a que el compositor de verdad dibuje el splash.

        Bajo Wayland `show()` no pinta nada: solo pide al compositor que
        mapee la superficie, y eso tarda un par de ciclos de eventos. Si
        arrancamos la carga pesada de inmediato, el hilo se bloquea antes
        del primer cuadro y el splash aparece apenas un destello al final,
        o de plano no aparece.
        """
        deadline = time.monotonic() + timeout
        handle = self.windowHandle()
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if handle is not None and handle.isExposed():
                QApplication.processEvents()
                return
            time.sleep(0.01)

    def status(self, text: str) -> None:
        """Actualiza el mensaje y repinta de inmediato.

        Hay que forzar el repintado: durante la carga nadie está corriendo
        el ciclo de eventos, así que el splash se quedaría congelado.
        """
        self.showMessage(text)
        QApplication.processEvents()

    def hold(self, minimum: float = 1.4) -> None:
        """Mantiene el splash en pantalla hasta cumplir `minimum` segundos.

        Se llama ANTES de mostrar la ventana principal, no después. Si se
        llamara después, el editor ya está en pantalla tapando el splash y
        toda la espera se desperdicia.

        Tampoco sirve confiar en `WindowStaysOnTopHint`: bajo Wayland el
        compositor decide el orden de las ventanas y esa bandera no hace
        nada. La única forma de garantizar que se vea es no tener todavía
        otra ventana abierta.
        """
        remaining = minimum - (time.monotonic() - self._shown_at)
        while remaining > 0:
            QApplication.processEvents()
            time.sleep(min(0.02, remaining))
            remaining = minimum - (time.monotonic() - self._shown_at)
