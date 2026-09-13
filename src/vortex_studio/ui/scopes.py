"""El panel de scopes: histograma, forma de onda y vectorscopio.

Se actualiza cuando cambia el cuadro, con freno: arrastrar el playhead
pediría uno por pixel y el panel viviría recalculando. Mientras está
cerrado no calcula nada.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QDockWidget, QVBoxLayout, QWidget

from vortex_studio.media import scopes

HISTOGRAM = "Histograma"
WAVEFORM = "Forma de onda"
VECTORSCOPE = "Vectorscopio"
MODES = (HISTOGRAM, WAVEFORM, VECTORSCOPE)
WIDTH = 320


def image_to_array(image: QImage, width: int = WIDTH) -> np.ndarray:
    """La imagen como arreglo RGB, reducida a `width` de ancho."""
    if image.width() > width:
        image = image.scaledToWidth(width, Qt.FastTransformation)
    image = image.convertToFormat(QImage.Format_RGB888)
    alto, ancho, paso = image.height(), image.width(), image.bytesPerLine()
    datos = np.frombuffer(image.constBits(), dtype=np.uint8, count=alto * paso)
    return datos.reshape(alto, paso)[:, :ancho * 3].reshape(alto, ancho, 3).copy()


class ScopeView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.mode = WAVEFORM
        self.data: np.ndarray | None = None
        self.setMinimumSize(220, 160)

    def set_data(self, mode: str, data: np.ndarray | None) -> None:
        self.mode, self.data = mode, data
        self.update()

    @staticmethod
    def _intensity(conteos: np.ndarray) -> np.ndarray:
        """Escala logarítmica: si no, un fondo liso tapa todo lo demás."""
        valores = np.log1p(conteos.astype(np.float32))
        tope = float(valores.max()) or 1.0
        return (valores / tope * 255).astype(np.uint8)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f1113"))
        caja = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#2a2f36"), 1))
        for i in range(1, 4):
            y = caja.top() + caja.height() * i / 4
            painter.drawLine(QPointF(caja.left(), y), QPointF(caja.right(), y))

        if self.data is None:
            painter.setPen(QColor("#6f757e"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin cuadro")
            painter.end()
            return

        if self.mode == HISTOGRAM:
            self._paint_histogram(painter, caja)
        else:
            niveles = self._intensity(self.data)
            if self.mode == VECTORSCOPE:
                lado = min(caja.width(), caja.height())
                caja = QRectF(caja.center().x() - lado / 2, caja.center().y() - lado / 2,
                              lado, lado)
            rgba = np.zeros((*niveles.shape, 4), dtype=np.uint8)
            rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = niveles
            rgba[..., 1] = np.minimum(255, niveles.astype(np.int32) + 20)
            rgba[..., 3] = np.where(niveles > 0, 255, 0)
            imagen = QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.shape[1] * 4,
                            QImage.Format_RGBA8888)
            painter.drawImage(caja, imagen)
            if self.mode == VECTORSCOPE:
                painter.setPen(QPen(QColor("#e0574a"), 1))
                for nombre, (x, y) in scopes.targets(256).items():
                    punto = QPointF(caja.left() + caja.width() * x / 255,
                                    caja.top() + caja.height() * y / 255)
                    painter.drawRect(QRectF(punto.x() - 4, punto.y() - 4, 8, 8))
                    painter.drawText(punto + QPointF(6, -4), nombre)
        painter.end()

    def _paint_histogram(self, painter: QPainter, caja: QRectF) -> None:
        colores = [QColor(230, 80, 80, 150), QColor(80, 220, 110, 150),
                   QColor(90, 140, 240, 150), QColor(230, 230, 230, 200)]
        tope = float(np.log1p(self.data[:3]).max()) or 1.0
        for canal in (0, 1, 2, 3):
            valores = np.log1p(self.data[canal]) / tope
            painter.setPen(QPen(colores[canal], 1.2))
            anterior = None
            for i, v in enumerate(valores):
                punto = QPointF(caja.left() + caja.width() * i / (len(valores) - 1),
                                caja.bottom() - caja.height() * float(v))
                if anterior is not None:
                    painter.drawLine(anterior, punto)
                anterior = punto


class ScopesDock(QDockWidget):
    def __init__(self) -> None:
        super().__init__("Scopes")
        self.setObjectName("scopes")
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.setCurrentText(WAVEFORM)
        self.mode.currentTextChanged.connect(lambda _: self._recalculate())
        self.view = ScopeView()
        self._image: QImage | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._recalculate)

        cuerpo = QWidget()
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.mode)
        layout.addWidget(self.view, 1)
        self.setWidget(cuerpo)

    def submit(self, image: QImage | None) -> None:
        """Un cuadro nuevo. Se calcula al rato, y solo si el panel se ve."""
        self._image = image
        if not self.isHidden():
            self._timer.start()

    def calculate(self, image: QImage | None = None) -> np.ndarray | None:
        """Calcula ya, sin esperar. Devuelve los conteos del modo elegido."""
        if image is not None:
            self._image = image
        self._recalculate()
        return self.view.data

    def _recalculate(self) -> None:
        if self._image is None or self._image.isNull():
            self.view.set_data(self.mode.currentText(), None)
            return
        arreglo = image_to_array(self._image)
        modo = self.mode.currentText()
        datos = {HISTOGRAM: scopes.histogram, WAVEFORM: scopes.waveform,
                 VECTORSCOPE: scopes.vectorscope}[modo](arreglo)
        self.view.set_data(modo, datos)
