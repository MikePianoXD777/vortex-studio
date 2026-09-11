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
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from pathlib import Path

from vortex_studio.model import Clip, ImageOverlay, Sequence, Title, timecode
from vortex_studio.ui.waveforms import WaveformCache

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
WAVE = QColor(190, 235, 210, 190)
FADE = QColor(12, 14, 16, 170)
FADE_EDGE = QColor(235, 238, 242, 130)
SPEED_TAG = QColor("#f0d68a")
MARKER = QColor("#e8c15a")
DISSOLVE = QColor(120, 170, 230, 120)
DISSOLVE_EDGE = QColor("#8fb6e0")
MARKER_TEXT = QColor("#1b1d21")

PEAKS_PER_SECOND = 60

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

        # La onda se calcula en un hilo aparte y se guarda: decodificar el
        # audio entero dentro del repintado congelaba la ventana.
        self.waves = WaveformCache(PEAKS_PER_SECOND, self)
        self.waves.ready.connect(self.update)

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
        self._draw_markers(painter)
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

    def _draw_markers(self, painter: QPainter) -> None:
        """Los marcadores van clavados en la regla, con su línea hacia abajo."""
        for marker in self.sequence.markers:
            x = self.x_for(marker.time)
            if x < HEADER_WIDTH or x > self.width():
                continue

            painter.setPen(QPen(QColor(marker.color), 1, Qt.DotLine))
            painter.drawLine(QPointF(x, RULER_HEIGHT), QPointF(x, self.height()))

            banderita = QPainterPath()
            banderita.moveTo(x, RULER_HEIGHT)
            banderita.lineTo(x - 5, RULER_HEIGHT - 8)
            banderita.lineTo(x + 5, RULER_HEIGHT - 8)
            banderita.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(marker.color))
            painter.drawPath(banderita)

            if marker.name:
                painter.setPen(QColor(marker.color))
                painter.setFont(QFont("", 7))
                painter.drawText(QPointF(x + 8, RULER_HEIGHT + 11), marker.name[:22])

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
                self._draw_clip(painter, clip, y, _color_for(track, clip), track.kind)
            if track.kind == "video":
                self._draw_dissolves(painter, track, y)

    def _draw_clip(self, painter: QPainter, clip, y: float, color: QColor,
                   track_kind: str = "video") -> None:
        rect = QRectF(self.x_for(clip.start), y + 2,
                      clip.duration * self.pixels_per_second, TRACK_HEIGHT - 4)
        if rect.right() < HEADER_WIDTH or rect.left() > self.width():
            return

        chosen = clip is self.selected
        painter.setPen(QPen(SELECTED if chosen else CLIP_BORDER, 2 if chosen else 1))
        painter.setBrush(color.lighter(115) if chosen else color)
        painter.drawRoundedRect(rect, 3, 3)

        if track_kind == "audio" and rect.width() > 8:
            self._draw_wave(painter, clip, rect)

        self._draw_fades(painter, clip, rect)

        if rect.width() > 34:
            painter.setPen(QColor("#eef1f4"))
            painter.setFont(QFont("", 8))
            painter.drawText(rect.adjusted(6, 0, -6, 0),
                             Qt.AlignLeft | Qt.AlignVCenter, clip.name)

        velocidad = getattr(clip, "speed", 1.0)
        if velocidad != 1.0 and rect.width() > 60:
            painter.setPen(SPEED_TAG)
            painter.setFont(QFont("", 7, QFont.Bold))
            etiqueta = "❄" if velocidad == 0 else f"{velocidad:g}×"
            painter.drawText(rect.adjusted(0, 0, -6, 0),
                             Qt.AlignRight | Qt.AlignVCenter, etiqueta)

    def _draw_dissolves(self, painter: QPainter, track, y: float) -> None:
        """La transición se dibuja a caballo sobre el corte, con su moño.

        Se pinta después de los clips y no dentro de cada uno porque
        pertenece a los dos: cruza el corte por igual hacia ambos lados.
        """
        for clip in track.clips:
            cruce = getattr(clip, "dissolve", 0.0)
            if cruce <= 0 or track.before(clip) is None:
                continue

            ancho = cruce * self.pixels_per_second
            rect = QRectF(self.x_for(clip.start) - ancho / 2, y + 2,
                          ancho, TRACK_HEIGHT - 4)
            if rect.right() < HEADER_WIDTH or rect.left() > self.width():
                continue

            painter.setPen(QPen(DISSOLVE_EDGE, 1))
            painter.setBrush(DISSOLVE)
            painter.drawRect(rect)

            # El moño: dos diagonales cruzadas, como en cualquier editor.
            painter.setPen(QPen(DISSOLVE_EDGE, 1))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())

    def _draw_fades(self, painter: QPainter, clip, rect: QRectF) -> None:
        """Los fundidos se dibujan como cuñas oscuras en las puntas.

        Es la forma en que se leen de un vistazo en cualquier editor: la
        cuña muestra hacia dónde baja la opacidad sin tener que abrir nada.
        """
        entrada = getattr(clip, "fade_in", 0.0)
        salida = getattr(clip, "fade_out", 0.0)
        if entrada <= 0 and salida <= 0:
            return

        painter.save()
        painter.setClipRect(rect)
        painter.setPen(QPen(FADE_EDGE, 1))
        painter.setBrush(FADE)

        if entrada > 0:
            ancho = min(entrada, clip.duration) * self.pixels_per_second
            cuna = QPainterPath()
            cuna.moveTo(rect.left(), rect.top())
            cuna.lineTo(rect.left() + ancho, rect.top())
            cuna.lineTo(rect.left(), rect.bottom())
            cuna.closeSubpath()
            painter.drawPath(cuna)

        if salida > 0:
            ancho = min(salida, clip.duration) * self.pixels_per_second
            cuna = QPainterPath()
            cuna.moveTo(rect.right(), rect.top())
            cuna.lineTo(rect.right() - ancho, rect.top())
            cuna.lineTo(rect.right(), rect.bottom())
            cuna.closeSubpath()
            painter.drawPath(cuna)

        painter.restore()

    def _draw_wave(self, painter: QPainter, clip, rect: QRectF) -> None:
        """Dibuja la onda del clip, recortada a la parte que se ve.

        Solo se calculan las columnas visibles: con el zoom muy afuera un
        clip largo cabe en pocos pixeles, y no tiene caso mirar cada pico.
        """
        data = self._wave_for(clip.source)
        if not data:
            return

        visible = rect.intersected(QRectF(HEADER_WIDTH, rect.top(),
                                          self.width() - HEADER_WIDTH, rect.height()))
        if visible.width() < 2:
            return

        middle = rect.center().y()
        half = rect.height() / 2 - 3

        painter.setPen(QPen(WAVE, 1))
        for x in range(int(visible.left()), int(visible.right())):
            # De pixel a tiempo del clip, y de ahí a tiempo del archivo.
            dentro = (x - rect.left()) / self.pixels_per_second
            indice = int((getattr(clip, "in_point", 0.0) + dentro) * PEAKS_PER_SECOND)
            if not (0 <= indice < len(data)):
                continue
            alto = data[indice] * half
            painter.drawLine(QPointF(x, middle - alto), QPointF(x, middle + alto))

    def _wave_for(self, source) -> list[float]:
        return self.waves.get(source)

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
                track = self.sequence.tracks[self._drag["track"]]
                self._resolve_overlap(track, self._drag["item"])
                track.clips.sort(key=lambda c: c.start)
                label = "Mover clip" if self._drag["zone"] == "cuerpo" else "Recortar clip"
                self.edit_finished.emit(label)
            self._drag = None
            self.update()

    @staticmethod
    def _resolve_overlap(track, item) -> None:
        """Lo que se suelta encima tapa a lo que ya estaba.

        Es como funciona el arrastre por defecto en un editor: mandas algo
        sobre otra cosa y la pisa. Antes se permitía el traslape en silencio
        y lo que veías era el primero de la lista, que no siempre es el de
        arriba — parecía que el clip se había perdido.
        """
        for other in list(track.clips):
            if other is item or other.end <= item.start or other.start >= item.end:
                continue

            if other.start >= item.start and other.end <= item.end:
                track.clips.remove(other)          # queda tapado por completo
            elif other.start < item.start:
                other.duration = item.start - other.start   # se le corta la cola
            else:
                recorte = item.end - other.start             # se le corta la cabeza
                other.start = item.end
                other.duration -= recorte
                if hasattr(other, "in_point"):
                    other.in_point += recorte

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
