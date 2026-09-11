"""Barra de transporte: reproducción, velocidad, loop y lectura de tiempo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0]

BUTTON_STYLE = """
QPushButton {
    background: #2b2f34; color: #d6dae0; border: 1px solid #3a3f46;
    border-radius: 4px; padding: 4px 10px; min-width: 34px;
}
QPushButton:hover { background: #353a41; }
QPushButton:pressed { background: #23272b; }
QPushButton:checked { background: #3d6fa8; border-color: #4d82bf; color: #ffffff; }
QPushButton:disabled { color: #5a6068; border-color: #2e3238; background: #232629; }
"""

COMBO_STYLE = """
QComboBox {
    background: #2b2f34; color: #d6dae0; border: 1px solid #3a3f46;
    border-radius: 4px; padding: 3px 8px; min-width: 62px;
}
QComboBox:hover { background: #353a41; }
QComboBox QAbstractItemView {
    background: #24282d; color: #d6dae0;
    selection-background-color: #3d6fa8; border: 1px solid #3a3f46;
}
"""


class TransportBar(QWidget):
    """Los controles no reproducen nada: solo avisan qué se pidió."""

    play_pause = Signal()
    step = Signal(int)          # frames, con signo
    skip = Signal(float)        # segundos, con signo
    go_start = Signal()
    go_end = Signal()
    loop_toggled = Signal(bool)
    speed_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("QWidget { background: #1b1d21; }")

        self._current = QLabel("00:00:00:00")
        self._current.setStyleSheet(
            "color:#e6e9ed; font-family:monospace; font-size:15px;"
        )
        self._total = QLabel("/ 00:00:00:00")
        self._total.setStyleSheet(
            "color:#767c85; font-family:monospace; font-size:15px;"
        )

        start = self._button("⏮", "Ir al inicio  ·  Inicio")
        start.clicked.connect(self.go_start.emit)

        back10 = self._button("◀◀", "Atrás 10 s  ·  Ctrl+←")
        back10.clicked.connect(lambda: self.skip.emit(-10.0))

        back = self._button("◀|", "Frame anterior  ·  ←")
        back.clicked.connect(lambda: self.step.emit(-1))

        self._play = self._button("▶", "Reproducir / pausar  ·  Espacio")
        self._play.clicked.connect(self.play_pause.emit)

        forward = self._button("|▶", "Frame siguiente  ·  →")
        forward.clicked.connect(lambda: self.step.emit(1))

        fwd10 = self._button("▶▶", "Adelante 10 s  ·  Ctrl+→")
        fwd10.clicked.connect(lambda: self.skip.emit(10.0))

        end = self._button("⏭", "Ir al final  ·  Fin")
        end.clicked.connect(self.go_end.emit)

        self._loop = self._button("⟲", "Repetir  ·  L")
        self._loop.setCheckable(True)
        self._loop.toggled.connect(self.loop_toggled.emit)

        self._speed = QComboBox()
        self._speed.setStyleSheet(COMBO_STYLE)
        self._speed.setToolTip("Velocidad  ·  J más lento, K normal, Shift+L más rápido")
        self._speed.setFocusPolicy(Qt.NoFocus)
        for value in SPEEDS:
            self._speed.addItem(f"{value:g}×", value)
        self._speed.setCurrentIndex(SPEEDS.index(1.0))
        self._speed.currentIndexChanged.connect(
            lambda i: self.speed_changed.emit(SPEEDS[i])
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)
        layout.addWidget(self._current)
        layout.addWidget(self._total)
        layout.addStretch(1)
        for widget in (start, back10, back, self._play, forward, fwd10, end):
            layout.addWidget(widget)
        layout.addStretch(1)
        layout.addWidget(self._loop)
        layout.addWidget(self._speed)

    def _button(self, text: str, tip: str) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tip)
        button.setStyleSheet(BUTTON_STYLE)
        button.setFocusPolicy(Qt.NoFocus)
        return button

    # --- estado que refleja, no controla ----------------------------------

    def set_timecode(self, current: str, total: str = "") -> None:
        self._current.setText(current)
        if total:
            self._total.setText(f"/ {total}")

    def set_playing(self, playing: bool) -> None:
        self._play.setText("❚❚" if playing else "▶")

    def set_speed(self, speed: float) -> None:
        """Para cuando la velocidad cambia por teclado y hay que reflejarla."""
        if speed in SPEEDS:
            self._speed.blockSignals(True)
            self._speed.setCurrentIndex(SPEEDS.index(speed))
            self._speed.blockSignals(False)

    def set_loop(self, enabled: bool) -> None:
        self._loop.blockSignals(True)
        self._loop.setChecked(enabled)
        self._loop.blockSignals(False)
