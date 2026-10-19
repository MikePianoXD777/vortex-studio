"""Medidor de audio junto al timeline.

Antes no había ninguno: la mezcla podía pasarse de 1.0 y recortar sin que
nada lo avisara. Ahora hay un limitador (`media/limiter.py`) y este medidor
dice cuándo tuvo que actuar.

Es un medidor de picos estéreo en dB, como el de Premiere:

- sube al instante y baja a 24 dB por segundo, para que se pueda leer;
- retiene el pico más alto 1.5 s con una rayita;
- la luz «LIM» de arriba se queda prendida si el limitador bajó el volumen:
  la mezcla está demasiado fuerte. Un clic la apaga.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from vortex_studio.ui import theme

FLOOR_DB = -60.0
FALL_DB_PER_S = 24.0
HOLD_S = 1.5
TICKS = (0, -6, -12, -18, -24, -36, -48)

VERDE = QColor("#4fb866")
AMARILLO = QColor("#e0b43c")
ROJO = QColor("#e0574a")
APAGADO = QColor(theme.CAMPO)
LUZ_APAGADA = QColor(theme.BORDE_FUERTE)


def to_db(pico: float) -> float:
    return FLOOR_DB if pico <= 1e-6 else max(FLOOR_DB, 20.0 * math.log10(pico))


class AudioMeter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(46)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setMinimumHeight(80)
        self.setToolTip("Nivel de la mezcla (dB). La luz LIM se prende si el limitador "
                        "tuvo que bajar el volumen; un clic la apaga.")
        self.setCursor(Qt.PointingHandCursor)
        self.shown = [FLOOR_DB, FLOOR_DB]     # lo que se dibuja
        self._target = [FLOOR_DB, FLOOR_DB]   # lo último que llegó
        self.hold = [FLOOR_DB, FLOOR_DB]
        self._hold_at = [0.0, 0.0]
        self.limited = False
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._animate)

    # --- lo que llega -------------------------------------------------------

    def set_levels(self, left: float, right: float, limited: bool = False) -> None:
        ahora = time.monotonic()
        for i, pico in enumerate((left, right)):
            db = to_db(pico)
            self._target[i] = db
            if db >= self.shown[i]:
                self.shown[i] = db              # el ataque es instantáneo
            if db >= self.hold[i]:
                self.hold[i], self._hold_at[i] = db, ahora
        if limited:
            self.limited = True
        if not self._timer.isActive():
            self._last = ahora
            self._timer.start()
        self.update()

    def reset(self) -> None:
        """Al pausar: la barra baja sola, sin brincar a cero."""
        self._target = [FLOOR_DB, FLOOR_DB]
        if not self._timer.isActive():
            self._last = time.monotonic()
            self._timer.start()

    def clear_limit(self) -> None:
        self.limited = False
        self.update()

    def _animate(self) -> None:
        ahora = time.monotonic()
        paso = (ahora - self._last) * FALL_DB_PER_S
        self._last = ahora
        quieto = True
        for i in range(2):
            self.shown[i] = max(self._target[i], self.shown[i] - paso)
            if ahora - self._hold_at[i] > HOLD_S:
                self.hold[i] = max(self.shown[i], self.hold[i] - paso)
            if self.shown[i] > FLOOR_DB or self.hold[i] > FLOOR_DB:
                quieto = False
        if quieto:
            self._timer.stop()
        self.update()

    def mousePressEvent(self, event) -> None:
        self.clear_limit()

    # --- dibujo -------------------------------------------------------------

    def _y_for(self, db: float, area: QRectF) -> float:
        fraccion = (db - FLOOR_DB) / -FLOOR_DB
        return area.bottom() - max(0.0, min(1.0, fraccion)) * area.height()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        luz = QRectF(self.width() - 30, 2, 26, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(ROJO if self.limited else LUZ_APAGADA)
        p.drawRoundedRect(luz, 3, 3)
        fuente = QFont()
        fuente.setPixelSize(8)
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor("#ffffff") if self.limited else QColor(theme.MUY_TENUE))
        p.drawText(luz, Qt.AlignCenter, "LIM")

        area = QRectF(self.width() - 26, 20, 22, self.height() - 26)
        ancho = 9.0
        for i in range(2):
            barra = QRectF(area.left() + i * (ancho + 4), area.top(), ancho, area.height())
            p.setPen(Qt.NoPen)
            p.setBrush(APAGADO)
            p.drawRoundedRect(barra, 2, 2)
            tope = self._y_for(self.shown[i], area)
            # Tres zonas, como en cualquier medidor: verde, amarillo desde −18
            # y rojo desde −6.
            for desde, hasta, color in ((FLOOR_DB, -18, VERDE), (-18, -6, AMARILLO), (-6, 0, ROJO)):
                y0, y1 = self._y_for(hasta, area), self._y_for(desde, area)
                y0 = max(y0, tope)
                if y1 > y0:
                    p.fillRect(QRectF(barra.left(), y0, ancho, y1 - y0), color)
            if self.hold[i] > FLOOR_DB:
                y = self._y_for(self.hold[i], area)
                p.fillRect(QRectF(barra.left(), y - 1, ancho, 2), QColor(theme.TEXTO))

        fuente.setBold(False)
        fuente.setPixelSize(8)
        p.setFont(fuente)
        p.setPen(QColor(theme.MUY_TENUE))
        for db in TICKS:
            y = self._y_for(db, area)
            if y < area.top() + 3:
                y = area.top() + 3
            p.drawText(QRectF(0, y - 6, self.width() - 30, 12),
                       Qt.AlignRight | Qt.AlignVCenter, str(db))
        p.end()
