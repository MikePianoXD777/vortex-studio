"""Barra de transporte: una sola línea bajo el monitor.

Antes era una botonera de reproductor —diez botones con repetir y volumen
en cajitas— y era lo que más hacía ver al editor como OBS. Con el diseño de
la beta queda lo mínimo a la vista: el código de tiempo a la izquierda, ir al
inicio, play y final al centro, y velocidad y volumen a la derecha. Saltar
diez segundos sigue en el teclado y en el menú Reproducción.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSlider, QWidget

from vortex_studio.ui import theme
from vortex_studio.ui.widgets import IconButton

SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0]

COMBO_STYLE = f"""
QComboBox {{
    background: transparent; border: none; color: {theme.TENUE};
    font-family: {theme.MONO}; font-size: 11px; padding: 2px 4px; min-width: 30px;
}}
QComboBox:hover {{ color: {theme.TEXTO}; }}
QComboBox::drop-down {{ width: 0; border: none; }}
QComboBox::down-arrow {{ image: none; border: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background: {theme.CAMPO}; color: {theme.TEXTO}; border: 1px solid {theme.BORDE_FUERTE};
    selection-background-color: {theme.PILDORA}; outline: none;
}}
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
    volume_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(52)

        self._current = QLabel("00:00:00:00")
        self._current.setStyleSheet(
            f"color:{theme.TEXTO}; font-family:{theme.MONO}; font-size:13px;")
        self._total = QLabel("/ 00:00:00:00")
        self._total.setStyleSheet(
            f"color:{theme.MUY_TENUE}; font-family:{theme.MONO}; font-size:13px;")

        start = IconButton("inicio", "Ir al inicio  ·  Inicio", 30)
        start.clicked.connect(self.go_start.emit)
        back = IconButton("anterior", "Cuadro anterior  ·  ←", 26)
        back.clicked.connect(lambda: self.step.emit(-1))
        self._play = IconButton("play", "Reproducir / pausar  ·  Espacio", 38, circle=True)
        self._play.clicked.connect(self.play_pause.emit)
        forward = IconButton("siguiente", "Cuadro siguiente  ·  →", 26)
        forward.clicked.connect(lambda: self.step.emit(1))
        end = IconButton("fin", "Ir al final  ·  Fin", 30)
        end.clicked.connect(self.go_end.emit)

        self._loop = IconButton("repetir", "Repetir  ·  L", 26)
        self._loop.setCheckable(True)
        self._loop.toggled.connect(self.loop_toggled.emit)

        self._speed = QComboBox()
        self._speed.setStyleSheet(COMBO_STYLE)
        self._speed.setToolTip("Velocidad  ·  J más lento, K normal, Shift+L más rápido")
        self._speed.setFocusPolicy(Qt.NoFocus)
        self._speed.setCursor(Qt.PointingHandCursor)
        for value in SPEEDS:
            self._speed.addItem(f"{value:g}×", value)
        self._speed.setCurrentIndex(SPEEDS.index(1.0))
        self._speed.currentIndexChanged.connect(
            lambda i: self.speed_changed.emit(SPEEDS[i]))

        self._mute = IconButton("volumen", "Silenciar", 26)
        self._mute.setCheckable(True)
        self._mute.toggled.connect(self._toggle_mute)

        self._volume = QSlider(Qt.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(80)
        self._volume.setFixedWidth(76)
        self._volume.setToolTip("Volumen")
        self._volume.setStyleSheet(theme.SLIDER_STYLE)
        self._volume.valueChanged.connect(
            lambda v: self.volume_changed.emit(v / 100.0))

        # Tres columnas del mismo ancho: así el play queda al centro exacto
        # aunque el código de tiempo y los controles de la derecha midan
        # distinto.
        izquierda = QWidget()
        caja = QHBoxLayout(izquierda)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(6)
        caja.addWidget(self._current)
        caja.addWidget(self._total)
        caja.addStretch(1)

        centro = QWidget()
        caja = QHBoxLayout(centro)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(6)
        for widget in (back, start, self._play, end, forward):
            caja.addWidget(widget)

        derecha = QWidget()
        caja = QHBoxLayout(derecha)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(4)
        caja.addStretch(1)
        caja.addWidget(self._loop)
        caja.addWidget(self._speed)
        caja.addWidget(self._mute)
        caja.addWidget(self._volume)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 2)
        layout.setSpacing(8)
        layout.addWidget(izquierda, 1)
        layout.addWidget(centro, 0)
        layout.addWidget(derecha, 1)

    # --- estado que refleja, no controla ----------------------------------

    def set_timecode(self, current: str, total: str = "") -> None:
        self._current.setText(current)
        if total:
            self._total.setText(f"/ {total}")

    def set_playing(self, playing: bool) -> None:
        self._play.set_icon("pausa" if playing else "play")

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

    def _toggle_mute(self, silenciado: bool) -> None:
        self._mute.set_icon("silencio" if silenciado else "volumen")
        self._volume.setEnabled(not silenciado)
        self.volume_changed.emit(0.0 if silenciado else self._volume.value() / 100.0)

    def volume(self) -> float:
        return 0.0 if self._mute.isChecked() else self._volume.value() / 100.0
