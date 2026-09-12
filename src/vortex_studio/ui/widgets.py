"""Piezas de interfaz que se repiten en los paneles."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 4px; background: #2c3037; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #3d6fa8; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; height: 12px; margin: -5px 0;
    background: #d6dae0; border-radius: 6px;
}
QSlider::handle:horizontal:hover { background: #ffffff; }
"""

SPIN_STYLE = """
QSpinBox {
    background: #24282d; color: #d6dae0; border: 1px solid #363b42;
    border-radius: 3px; padding: 1px 4px; max-width: 56px;
}
"""


class SliderRow(QWidget):
    """Etiqueta, deslizador y número, los tres amarrados entre sí.

    Doble clic en la etiqueta regresa el valor a su neutro, que es el gesto
    que todo mundo ya espera de un control de color.
    """

    changed = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, neutral: int) -> None:
        super().__init__()
        self.neutral = neutral

        self._label = QLabel(label)
        self._label.setStyleSheet("color:#9aa1aa; font-size:11px;")
        self._label.setToolTip("Doble clic para regresar al valor neutro")
        self._label.setMinimumWidth(74)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setValue(neutral)
        self._slider.setStyleSheet(SLIDER_STYLE)

        self._spin = QSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(neutral)
        self._spin.setStyleSheet(SPIN_STYLE)
        self._spin.setButtonSymbols(QSpinBox.NoButtons)
        self._spin.setAlignment(Qt.AlignRight)

        self._slider.valueChanged.connect(self._from_slider)
        self._spin.valueChanged.connect(self._from_spin)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)
        layout.addWidget(self._label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._spin)

    def _from_slider(self, value: int) -> None:
        if self._spin.value() != value:
            self._spin.blockSignals(True)
            self._spin.setValue(value)
            self._spin.blockSignals(False)
        self.changed.emit(value)

    def _from_spin(self, value: int) -> None:
        if self._slider.value() != value:
            self._slider.blockSignals(True)
            self._slider.setValue(value)
            self._slider.blockSignals(False)
        self.changed.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        """Pone el valor sin disparar `changed`, para reflejar estado externo."""
        for widget in (self._slider, self._spin):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

    def mouseDoubleClickEvent(self, event) -> None:
        self._slider.setValue(self.neutral)


def section(title: str) -> QLabel:
    """Encabezado de grupo dentro de un panel."""
    label = QLabel(title.upper())
    label.setStyleSheet(
        "color:#6f757e; font-size:9px; font-weight:600; "
        "letter-spacing:1px; padding:10px 0 3px 0;"
    )
    return label


def column(*widgets, spacing: int = 4, margins: tuple = (10, 8, 10, 10)) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    return box


class Collapsible(QWidget):
    """Un grupo que se abre y se cierra con un clic en su título.

    Sin esto, el panel de Color con la curva y la viñeta adentro se vuelve
    una lista de once deslizadores, y ahí se acabó el "fácil de usar": lo
    que se usa todos los días queda enterrado entre lo que se usa una vez
    al mes. Cerrado por omisión, se abre quien lo necesite.
    """

    def __init__(self, title: str, *widgets, abierto: bool = False) -> None:
        super().__init__()

        self._title = title
        self._button = QToolButton()
        self._button.setCheckable(True)
        self._button.setChecked(abierto)
        self._button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._button.setStyleSheet(
            "QToolButton { border: none; background: transparent; "
            "color:#6f757e; font-size:9px; font-weight:600; letter-spacing:1px; "
            "padding:10px 0 3px 0; text-align:left; }"
            "QToolButton:hover { color:#b6bcc4; }"
        )
        self._button.clicked.connect(self._toggle)

        self._body = QWidget()
        cuerpo = QVBoxLayout(self._body)
        cuerpo.setContentsMargins(0, 0, 0, 4)
        cuerpo.setSpacing(4)
        for widget in widgets:
            if isinstance(widget, QWidget):
                cuerpo.addWidget(widget)
            elif widget is not None:
                cuerpo.addLayout(widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._button)
        layout.addWidget(self._body)

        self._refresh()

    def _toggle(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        abierto = self._button.isChecked()
        self._body.setVisible(abierto)
        self._button.setText(f"{'▾' if abierto else '▸'}  {self._title.upper()}")

    @property
    def abierto(self) -> bool:
        return self._button.isChecked()

    def abrir(self, si: bool = True) -> None:
        self._button.setChecked(si)
        self._refresh()


class CurveView(QWidget):
    """La gráfica de la curva de color. Solo se mira, no se arrastra.

    Es la mitad de la idea de tener una curva sin editor de bezier: los
    cinco deslizadores dicen qué hacer y esta gráfica dice qué está pasando.
    Sin el dibujo, cinco números llamados "sombras" y "luces" no le dicen
    nada a nadie.

    Dibuja la misma curva que se le manda a FFmpeg —ver `model/curves.py`—
    así que lo que se ve aquí es lo que se le hace a la imagen.
    """

    def __init__(self) -> None:
        super().__init__()
        self._curves = None
        self.setMinimumHeight(92)
        self.setToolTip("La curva que se le está aplicando al clip")

    def set_curves(self, curves) -> None:
        self._curves = curves
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        marco = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#15171a"))
        painter.drawRoundedRect(marco, 3, 3)

        # La curva se dibuja adentro con un margen: sin él, los puntos de
        # los extremos quedan cortados a la mitad contra el borde.
        caja = marco.adjusted(4, 4, -4, -4)

        rejilla = QPen(QColor("#282c32"), 1)
        painter.setPen(rejilla)
        for i in (1, 2, 3):
            x = caja.left() + caja.width() * i / 4
            y = caja.top() + caja.height() * i / 4
            painter.drawLine(int(x), caja.top(), int(x), caja.bottom())
            painter.drawLine(caja.left(), int(y), caja.right(), int(y))

        # La diagonal es el "no hacer nada": tenerla al lado hace obvio de
        # un vistazo hacia dónde se movió la curva.
        painter.setPen(QPen(QColor("#3a3f46"), 1, Qt.DashLine))
        painter.drawLine(caja.left(), caja.bottom(), caja.right(), caja.top())

        if self._curves is None:
            painter.end()
            return

        def punto(x: float, y: float) -> tuple[float, float]:
            return (caja.left() + caja.width() * x,
                    caja.bottom() - caja.height() * y)

        trazo = QPainterPath()
        pasos = 48
        for i in range(pasos + 1):
            x = i / pasos
            px, py = punto(x, self._curves.at(x))
            if i == 0:
                trazo.moveTo(px, py)
            else:
                trazo.lineTo(px, py)

        painter.setPen(QPen(QColor("#5f9de0"), 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(trazo)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#d6dae0"))
        for x, y in self._curves.points():
            px, py = punto(x, y)
            painter.drawEllipse(QPointF(px, py), 2.6, 2.6)

        painter.end()
