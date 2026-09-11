"""El timeline: regla de tiempo, pistas, clips y playhead.

Dibujado a mano con QPainter. Un editor necesita control fino de cada pixel
(snapping, zoom, arrastre), y ningún widget de Qt hecho da eso.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from vortex_studio.model import Clip, ImageOverlay, Sequence, Title, timecode

HEADER_WIDTH = 72
RULER_HEIGHT = 26
TRACK_HEIGHT = 40
TRACK_GAP = 2

BG = QColor("#1b1d21")
RULER_BG = QColor("#232629")
TRACK_BG = QColor("#212429")
CLIP_VIDEO = QColor("#3d6fa8")
CLIP_AUDIO = QColor("#3f7d5c")
CLIP_TEXT = QColor("#a8763d")
CLIP_IMAGE = QColor("#7a5aa8")
CLIP_BORDER = QColor("#0f1113")
TEXT = QColor("#c8ccd2")
DIM_TEXT = QColor("#7d838c")
PLAYHEAD = QColor("#e0574a")
RANGE_FILL = QColor(61, 111, 168, 46)
RANGE_EDGE = QColor("#5f9bd8")
OUTSIDE = QColor(10, 11, 13, 96)


def _color_for(track, clip) -> QColor:
    """El color dice qué es cada bloque sin tener que leer su nombre."""
    if isinstance(clip, Title):
        return CLIP_TEXT
    if isinstance(clip, ImageOverlay):
        return CLIP_IMAGE
    return CLIP_AUDIO if track.kind == "audio" else CLIP_VIDEO


class TimelineWidget(QWidget):
    """Muestra la secuencia y deja mover el playhead arrastrando."""

    playhead_moved = Signal(float)

    def __init__(self, sequence: Sequence, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sequence = sequence
        self.playhead = 0.0
        self.pixels_per_second = 80.0
        self.mark_in: float | None = None
        self.mark_out: float | None = None

        self._dragging = False
        self.setMinimumHeight(RULER_HEIGHT + len(sequence.tracks) * (TRACK_HEIGHT + TRACK_GAP) + 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # --- conversión tiempo <-> pixel -------------------------------------

    def x_for(self, t: float) -> float:
        return HEADER_WIDTH + t * self.pixels_per_second

    def time_for(self, x: float) -> float:
        return max(0.0, (x - HEADER_WIDTH) / self.pixels_per_second)

    def set_playhead(self, t: float) -> None:
        t = max(0.0, t)
        if abs(t - self.playhead) > 1e-9:
            self.playhead = t
            self.update()

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), BG)

        self._draw_ruler(painter)
        self._draw_tracks(painter)
        self._draw_range(painter)
        self._draw_playhead(painter)
        painter.end()

    def _draw_ruler(self, painter: QPainter) -> None:
        painter.fillRect(0, 0, self.width(), RULER_HEIGHT, RULER_BG)
        painter.setFont(QFont("", 7))

        step = self._ruler_step()
        t = 0.0
        while self.x_for(t) < self.width():
            x = self.x_for(t)
            painter.setPen(QPen(DIM_TEXT, 1))
            painter.drawLine(QPointF(x, RULER_HEIGHT - 7), QPointF(x, RULER_HEIGHT))
            painter.setPen(TEXT)
            painter.drawText(QPointF(x + 3, RULER_HEIGHT - 9), timecode(t, self.sequence.fps))
            t += step

    def _ruler_step(self) -> float:
        """Separación entre marcas, para que no se encimen al alejar el zoom."""
        for step in (0.5, 1, 2, 5, 10, 30, 60, 300):
            if step * self.pixels_per_second >= 72:
                return float(step)
        return 600.0

    def _draw_tracks(self, painter: QPainter) -> None:
        y = RULER_HEIGHT + TRACK_GAP
        for track in self.sequence.tracks:
            painter.fillRect(QRectF(0, y, self.width(), TRACK_HEIGHT), TRACK_BG)

            painter.setPen(DIM_TEXT)
            painter.setFont(QFont("", 8, QFont.Bold))
            painter.drawText(QRectF(0, y, HEADER_WIDTH - 10, TRACK_HEIGHT),
                             Qt.AlignRight | Qt.AlignVCenter, track.name)

            for clip in track.clips:
                self._draw_clip(painter, clip, y, _color_for(track, clip))

            y += TRACK_HEIGHT + TRACK_GAP

    def _draw_clip(self, painter: QPainter, clip, y: float, color: QColor) -> None:
        rect = QRectF(self.x_for(clip.start), y + 3,
                      clip.duration * self.pixels_per_second, TRACK_HEIGHT - 6)
        if rect.right() < HEADER_WIDTH or rect.left() > self.width():
            return

        painter.setPen(QPen(CLIP_BORDER, 1))
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 3, 3)

        painter.setPen(QColor("#eef1f4"))
        painter.setFont(QFont("", 8))
        painter.drawText(rect.adjusted(6, 0, -6, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, clip.name)

    def _draw_range(self, painter: QPainter) -> None:
        """Marcas de entrada y salida: oscurece lo de fuera, resalta lo de dentro."""
        if self.mark_in is None and self.mark_out is None:
            return

        start = self.mark_in if self.mark_in is not None else 0.0
        end = self.mark_out if self.mark_out is not None else self.sequence.duration
        x0, x1 = self.x_for(start), self.x_for(end)
        body = QRectF(0, RULER_HEIGHT, self.width(), self.height() - RULER_HEIGHT)

        painter.setPen(Qt.NoPen)
        painter.setBrush(OUTSIDE)
        if self.mark_in is not None:
            painter.drawRect(QRectF(HEADER_WIDTH, body.top(),
                                    max(0.0, x0 - HEADER_WIDTH), body.height()))
        if self.mark_out is not None:
            painter.drawRect(QRectF(x1, body.top(),
                                    max(0.0, self.width() - x1), body.height()))

        painter.setBrush(RANGE_FILL)
        painter.drawRect(QRectF(x0, 0, max(0.0, x1 - x0), RULER_HEIGHT))

        painter.setPen(QPen(RANGE_EDGE, 1))
        for x, mark in ((x0, self.mark_in), (x1, self.mark_out)):
            if mark is not None:
                painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self.x_for(self.playhead)
        if x < HEADER_WIDTH:
            return

        painter.setPen(QPen(PLAYHEAD, 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

        painter.setPen(Qt.NoPen)
        painter.setBrush(PLAYHEAD)
        painter.drawRect(QRectF(x - 5, 0, 10, 9))

    # --- interacción ------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and event.position().x() >= HEADER_WIDTH:
            self._dragging = True
            self._scrub(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._scrub(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False

    def _scrub(self, event: QMouseEvent) -> None:
        t = self.sequence.snap_to_frame(self.time_for(event.position().x()))
        self.set_playhead(t)
        self.playhead_moved.emit(t)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ctrl + rueda hace zoom manteniendo fijo el tiempo bajo el cursor."""
        if not (event.modifiers() & Qt.ControlModifier):
            super().wheelEvent(event)
            return

        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.pixels_per_second = max(4.0, min(2000.0, self.pixels_per_second * factor))
        self.update()
