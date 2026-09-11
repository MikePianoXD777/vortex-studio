"""Piezas de interfaz que se repiten en los paneles."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
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
