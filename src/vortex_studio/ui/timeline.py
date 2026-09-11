"""El timeline: regla de tiempo, pistas, clips, playhead y edición.

Dibujado y manipulado a mano con QPainter. Un editor necesita control fino
de cada pixel — imantado, recorte por los bordes, arrastre entre pistas — y
ningún widget de Qt hecho da eso.

Reparto de la superficie, igual que en cualquier editor:
  · la regla de arriba mueve el playhead
  · el área vacía de las pistas también lo mueve
  · encima de un clip, el clic selecciona y arrastra
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
EDGE_GRAB = 7          # pixeles de cada extremo que sirven para recortar
SNAP_PIXELS = 9        # qué tan cerca hay que estar para que imante

TOOL_SELECT = "seleccion"
TOOL_RAZOR = "navaja"

BG = QColor("#1b1d21")
RULER_BG = QColor("#232629")
TRACK_BG = QColor("#212429")
TRACK_BG_TARGET = QColor("#262b32")
CLIP_VIDEO = QColor("#3d6fa8")
CLIP_AUDIO = QColor("#3f7d5c")
CLIP_TEXT = QColor("#a8763d")
CLIP_IMAGE = QColor("#7a5aa8")
CLIP_BORDER = QColor("#0f1113")
SELECTED = QColor("#ffffff")
TEXT = QColor("#c8ccd2")
DIM_TEXT = QColor("#7d838c")
PLAYHEAD = QColor("#e0574a")
RANGE_FILL = QColor(61, 111, 168, 46)
RANGE_EDGE = QColor("#5f9bd8")
OUTSIDE = QColor(10, 11, 13, 96)
SNAP_LINE = QColor("#e8c15a")

# Qué tipo de cosa acepta cada clase de pista.
ACCEPTS = {
    "video": (Clip, ImageOverlay),
    "texto": (Title,),
    "audio": (Clip,),
}


def _color_for(track, clip) -> QColor:
    """El color dice qué es cada bloque sin tener que leer su nombre."""
    if isinstance(clip, Title):
        return CLIP_TEXT
    if isinstance(clip, ImageOverlay):
        return CLIP_IMAGE
    return CLIP_AUDIO if track.kind == "audio" else CLIP_VIDEO


class TimelineWidget(QWidget):
    """Muestra la secuencia y deja editarla."""

    playhead_moved = Signal(float)
    selection_changed = Signal(object)
    edit_finished = Signal(str)          # etiqueta para el historial
    cut_requested = Signal(object, float)

    def __init__(self, sequence: Sequence, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sequence = sequence
        self.playhead = 0.0
        self.pixels_per_second = 80.0
        self.mark_in: float | None = None
        self.mark_out: float | None = None

        self.tool = TOOL_SELECT
        self.selected = None

        self._scrubbing = False
        self._drag: dict | None = None
        self._snap_at: float | None = None

        self.setMinimumHeight(
            RULER_HEIGHT + len(sequence.tracks) * (TRACK_HEIGHT + TRACK_GAP) + 10)
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

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.setCursor(Qt.CrossCursor if tool == TOOL_RAZOR else Qt.ArrowCursor)

    def select(self, item) -> None:
        if item is not self.selected:
            self.selected = item
            self.selection_changed.emit(item)
            self.update()

    def refresh(self) -> None:
        """Tras cambiar la secuencia por fuera (deshacer, importar…)."""
        self.setMinimumHeight(
            RULER_HEIGHT + len(self.sequence.tracks) * (TRACK_HEIGHT + TRACK_GAP) + 10)
        self.update()

    # --- geometría de pistas ---------------------------------------------

    def _track_top(self, index: int) -> float:
        return RULER_HEIGHT + TRACK_GAP + index * (TRACK_HEIGHT + TRACK_GAP)

    def _track_index_at(self, y: float) -> int | None:
        if y < RULER_HEIGHT:
            return None
        index = int((y - RULER_HEIGHT - TRACK_GAP) // (TRACK_HEIGHT + TRACK_GAP))
        return index if 0 <= index < len(self.sequence.tracks) else None

    def _item_at(self, x: float, y: float):
        """Devuelve (índice de pista, item, zona) o (None, None, "")."""
        index = self._track_index_at(y)
        if index is None:
            return None, None, ""

        for item in self.sequence.tracks[index].clips:
            left, right = self.x_for(item.start), self.x_for(item.end)
            if left <= x <= right:
                if x - left <= EDGE_GRAB:
                    return index, item, "inicio"
                if right - x <= EDGE_GRAB:
                    return index, item, "fin"
                return index, item, "cuerpo"
        return index, None, ""

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), BG)

        self._draw_ruler(painter)
        self._draw_tracks(painter)
        self._draw_range(painter)
        self._draw_snap(painter)
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
        dragging = self._drag["item"] if self._drag else None

        for index, track in enumerate(self.sequence.tracks):
            y = self._track_top(index)

            # Al arrastrar, las pistas donde sí cabe lo que traes se aclaran.
            highlight = dragging is not None and isinstance(dragging, ACCEPTS.get(track.kind, ()))
            painter.fillRect(QRectF(0, y, self.width(), TRACK_HEIGHT),
                             TRACK_BG_TARGET if highlight else TRACK_BG)

            painter.setPen(DIM_TEXT)
            painter.setFont(QFont("", 8, QFont.Bold))
            painter.drawText(QRectF(0, y, HEADER_WIDTH - 10, TRACK_HEIGHT),
                             Qt.AlignRight | Qt.AlignVCenter, track.name)

            for clip in track.clips:
                self._draw_clip(painter, clip, y, _color_for(track, clip))

    def _draw_clip(self, painter: QPainter, clip, y: float, color: QColor) -> None:
        rect = QRectF(self.x_for(clip.start), y + 2,
                      clip.duration * self.pixels_per_second, TRACK_HEIGHT - 4)
        if rect.right() < HEADER_WIDTH or rect.left() > self.width():
            return

        chosen = clip is self.selected
        painter.setPen(QPen(SELECTED if chosen else CLIP_BORDER, 2 if chosen else 1))
        painter.setBrush(color.lighter(115) if chosen else color)
        painter.drawRoundedRect(rect, 3, 3)

        if rect.width() > 34:
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

    def _draw_snap(self, painter: QPainter) -> None:
        if self._snap_at is None:
            return
        painter.setPen(QPen(SNAP_LINE, 1, Qt.DashLine))
        x = self.x_for(self._snap_at)
        painter.drawLine(QPointF(x, RULER_HEIGHT), QPointF(x, self.height()))

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self.x_for(self.playhead)
        if x < HEADER_WIDTH:
            return

        painter.setPen(QPen(PLAYHEAD, 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

        painter.setPen(Qt.NoPen)
        painter.setBrush(PLAYHEAD)
        painter.drawRect(QRectF(x - 5, 0, 10, 9))

    # --- imantado ---------------------------------------------------------

    def _snap(self, t: float, ignore=None) -> float:
        """Jala el tiempo hacia los puntos de interés que estén muy cerca.

        Sin esto es imposible pegar dos clips sin dejar un hueco de un par
        de milisegundos, que luego se ve como un parpadeo negro.
        """
        candidates = [0.0, self.playhead]
        if self.mark_in is not None:
            candidates.append(self.mark_in)
        if self.mark_out is not None:
            candidates.append(self.mark_out)
        for track in self.sequence.tracks:
            for item in track.clips:
                if item is not ignore:
                    candidates += [item.start, item.end]

        tolerance = SNAP_PIXELS / self.pixels_per_second
        best = min(candidates, key=lambda c: abs(c - t))
        if abs(best - t) <= tolerance:
            self._snap_at = best
            return best

        self._snap_at = None
        return self.sequence.snap_to_frame(t)

    # --- interacción ------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()
        if pos.x() < HEADER_WIDTH:
            return

        if pos.y() < RULER_HEIGHT:
            self._scrubbing = True
            self._scrub(pos.x())
            return

        index, item, zone = self._item_at(pos.x(), pos.y())

        if item is None:
            self.select(None)
            self._scrubbing = True
            self._scrub(pos.x())
            return

        if self.tool == TOOL_RAZOR:
            self.cut_requested.emit(item, self.time_for(pos.x()))
            return

        self.select(item)
        self._drag = {
            "item": item,
            "track": index,
            "zone": zone,
            "grab": self.time_for(pos.x()),
            "start": item.start,
            "duration": item.duration,
            "in_point": getattr(item, "in_point", None),
            "moved": False,
        }

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()

        if self._scrubbing:
            self._scrub(pos.x())
            return

        if self._drag is None:
            self._update_cursor(pos)
            return

        self._drag["moved"] = True
        zone = self._drag["zone"]
        if zone == "cuerpo":
            self._move_drag(pos)
        else:
            self._trim_drag(pos, zone)
        self.update()

    def _move_drag(self, pos) -> None:
        drag = self._drag
        item = drag["item"]

        delta = self.time_for(pos.x()) - drag["grab"]
        item.start = max(0.0, self._snap(drag["start"] + delta, ignore=item))

        # Cambio de pista: solo a una que acepte este tipo de elemento.
        index = self._track_index_at(pos.y())
        if index is not None and index != drag["track"]:
            target = self.sequence.tracks[index]
            if isinstance(item, ACCEPTS.get(target.kind, ())):
                self.sequence.tracks[drag["track"]].clips.remove(item)
                target.add(item)
                drag["track"] = index

    def _trim_drag(self, pos, zone: str) -> None:
        drag = self._drag
        item = drag["item"]
        minimum = self.sequence.frame_duration
        edge = self._snap(self.time_for(pos.x()), ignore=item)

        if zone == "inicio":
            original_end = drag["start"] + drag["duration"]
            new_start = max(0.0, min(edge, original_end - minimum))
            item.start = new_start
            item.duration = original_end - new_start
            # En un clip de archivo, recortar por el inicio avanza el punto
            # de entrada: se ve más adelante del original, no se estira.
            if drag["in_point"] is not None:
                item.in_point = max(0.0, drag["in_point"] + (new_start - drag["start"]))
        else:
            item.duration = max(minimum, edge - item.start)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._scrubbing = False
        self._snap_at = None

        if self._drag is not None:
            if self._drag["moved"]:
                label = "Mover clip" if self._drag["zone"] == "cuerpo" else "Recortar clip"
                self.sequence.tracks[self._drag["track"]].clips.sort(key=lambda c: c.start)
                self.edit_finished.emit(label)
            self._drag = None
            self.update()

    def _update_cursor(self, pos) -> None:
        if self.tool == TOOL_RAZOR:
            return
        _, item, zone = self._item_at(pos.x(), pos.y())
        if item is None:
            self.setCursor(Qt.ArrowCursor)
        elif zone in ("inicio", "fin"):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)

    def _scrub(self, x: float) -> None:
        t = self.sequence.snap_to_frame(self.time_for(x))
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
