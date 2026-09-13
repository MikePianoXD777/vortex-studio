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

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from pathlib import Path

from vortex_studio.model import Clip, ImageOverlay, Sequence, Title, accepts, timecode
from vortex_studio.model import animate
from vortex_studio.model.commands import link_offset, overwrite
from vortex_studio.model.commands import slip as slip_clip
from vortex_studio.model.project import DIP_BLACK, DIP_WHITE
from vortex_studio.ui.waveforms import WaveformCache

MEDIA_MIME = "application/x-vortex-media"

HEADER_WIDTH = 116
BUTTON = 17            # lado de los botones de la cabecera de pista
RULER_HEIGHT = 26
TRACK_HEIGHT = 40
TRACK_GAP = 2
EDGE_GRAB = 7          # pixeles de cada extremo que sirven para recortar
SNAP_PIXELS = 9        # qué tan cerca hay que estar para que imante

TOOL_SELECT = "seleccion"
TOOL_RAZOR = "navaja"
TOOL_SLIP = "deslizar"

BG = QColor("#1b1d21")
RULER_BG = QColor("#232629")
TRACK_BG = QColor("#212429")
TRACK_BG_TARGET = QColor("#262b32")
CLIP_VIDEO = QColor("#3d6fa8")
CLIP_AUDIO = QColor("#3f7d5c")
CLIP_TEXT = QColor("#a8763d")
CLIP_IMAGE = QColor("#7a5aa8")
CLIP_ADJUST = QColor("#7f8a3a")
CLIP_NESTED = QColor("#357f82")
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
DIP_FILLS = {DIP_BLACK: QColor(10, 10, 12, 190), DIP_WHITE: QColor(240, 242, 245, 170)}
MARKER_TEXT = QColor("#1b1d21")
LINKED_SELECTED = QColor("#b9c6d6")
OFFSET_TAG = QColor("#ff6b5e")
LOCKED_HATCH = QColor(0, 0, 0, 90)
BUTTON_BG = QColor("#2b2f34")
BUTTON_ON = {"enabled": QColor("#5f9bd8"), "muted": QColor("#e8904a"),
             "solo": QColor("#e8c15a"), "locked": QColor("#e0574a")}

PEAKS_PER_SECOND = 60

# Qué tipo de cosa acepta cada clase de pista. Vive en el modelo
# (`accepts`); esto queda para quien ya lo usaba.
ACCEPTS = {
    "video": (Clip, ImageOverlay),
    "texto": (Title,),
    "audio": (Clip,),
}

# Los botones de cada clase de pista, de izquierda a derecha.
TRACK_BUTTONS = {
    "video": ("enabled", "locked"),
    "texto": ("enabled", "locked"),
    "audio": ("muted", "solo", "locked"),
}
BUTTON_TIPS = {
    "enabled": "Mostrar u ocultar la pista",
    "locked": "Bloquear la pista: nada se mueve ni se borra",
    "muted": "Silenciar la pista",
    "solo": "Solo: oír nada más esta pista (y las otras en solo)",
}


def _color_for(track, clip) -> QColor:
    """El color dice qué es cada bloque sin tener que leer su nombre."""
    if isinstance(clip, Title):
        return CLIP_TEXT
    if isinstance(clip, ImageOverlay):
        return CLIP_IMAGE
    if type(clip).__name__ == "AdjustmentLayer":
        return CLIP_ADJUST
    if type(clip).__name__ == "NestedClip":
        return CLIP_NESTED
    return CLIP_AUDIO if track.kind == "audio" else CLIP_VIDEO


class TimelineWidget(QWidget):
    """Muestra la secuencia y deja editarla."""

    playhead_moved = Signal(float)
    selection_changed = Signal(object)
    edit_finished = Signal(str)          # etiqueta para el historial
    cut_requested = Signal(object, float)
    live_edit = Signal()                 # algo cambió a medio arrastre
    track_toggled = Signal(object, str)  # pista, interruptor
    marker_activated = Signal(object, object)   # marcador, dueño (None = secuencia)
    media_dropped = Signal(object, float, int)  # ruta, tiempo, pista
    clip_activated = Signal(object)             # doble clic sobre un elemento

    def __init__(self, sequence: Sequence, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sequence = sequence
        self.playhead = 0.0
        self.pixels_per_second = 80.0
        self.mark_in: float | None = None
        self.mark_out: float | None = None

        self.tool = TOOL_SELECT
        self.selected = None
        # Lo que se sumó a la selección con Ctrl+clic. `selected` sigue
        # siendo el principal: el que siguen los paneles.
        self.extra: list = []
        # Alt+clic selecciona un lado del enlace sin el otro, como en
        # Premiere: para mover el audio suelto sin desenlazar.
        self.ignore_link = False

        self._scrubbing = False
        self._drag: dict | None = None
        self._snap_at: float | None = None

        # Cuánto dura el archivo de un clip. Lo pone la ventana, que es quien
        # tiene el caché de sondeos; sin él, el slip solo se detiene en cero.
        self.source_duration = None

        # La onda se calcula en un hilo aparte y se guarda: decodificar el
        # audio entero dentro del repintado congelaba la ventana.
        self.waves = WaveformCache(PEAKS_PER_SECOND, self)
        self.waves.ready.connect(self.update)

        self.setMinimumHeight(
            RULER_HEIGHT + len(sequence.tracks) * (TRACK_HEIGHT + TRACK_GAP) + 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        # Zonas de render: [(inicio, fin, estado)] con estado "listo", 2 (pesada)
        # o 1 (ligera). La pone la ventana; ver `model/render_zones.py`.
        self.render_bar: list = []

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
        cursores = {TOOL_RAZOR: Qt.CrossCursor, TOOL_SLIP: Qt.SplitHCursor}
        self.setCursor(cursores.get(tool, Qt.ArrowCursor))

    def select(self, item, keep_extra: bool = False) -> None:
        if not keep_extra:
            self.extra = []
            self.ignore_link = False
        if item is not self.selected:
            self.selected = item
            self.selection_changed.emit(item)
        self.update()

    def toggle_extra(self, item) -> None:
        """Ctrl+clic: suma o quita un elemento de la selección."""
        if item is self.selected:
            siguiente = self.extra.pop(0) if self.extra else None
            self.selected = siguiente
            self.selection_changed.emit(siguiente)
        elif any(item is x for x in self.extra):
            self.extra = [x for x in self.extra if x is not item]
        elif self.selected is None:
            self.selected = item
            self.selection_changed.emit(item)
        else:
            self.extra.append(item)
        self.update()

    def selected_items(self, with_links: bool = True) -> list:
        """Todo lo seleccionado; con sus enlazados salvo que fue Alt+clic."""
        base = [x for x in [self.selected, *self.extra] if x is not None]
        if with_links and not self.ignore_link:
            return self.sequence.with_linked(base)
        return base

    def _is_selected(self, item) -> tuple[bool, bool]:
        """(seleccionado directo, seleccionado por enlace)."""
        directo = item is self.selected or any(item is x for x in self.extra)
        if directo or self.ignore_link:
            return directo, False
        return False, any(item is x for x in self.selected_items())

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

        for item in reversed(self.sequence.tracks[index].clips):
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
        self._draw_marker_labels(painter)
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
        self._draw_render_bar(painter)

    def _draw_render_bar(self, painter: QPainter) -> None:
        """La barra de Premiere: verde renderizado, rojo pesado, amarillo ligero."""
        colores = {"listo": QColor("#4fb866"), 2: QColor("#d9534f"), 1: QColor("#e0b43c")}
        for inicio, fin, estado in self.render_bar:
            color = colores.get(estado)
            if color is None:
                continue
            x0, x1 = max(HEADER_WIDTH, self.x_for(inicio)), min(self.width(), self.x_for(fin))
            if x1 > x0:
                painter.fillRect(QRectF(x0, RULER_HEIGHT - 3, x1 - x0, 3), color)

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

    def _draw_marker_labels(self, painter: QPainter) -> None:
        """El nombre de cada marcador, en una etiqueta encima de las pistas.

        Va después de pintar las pistas y no junto con la banderita: antes se
        dibujaba primero y el fondo de la primera pista lo tapaba, así que el
        nombre nunca se veía.
        """
        painter.setFont(QFont("", 7))
        metricas = painter.fontMetrics()
        for marker in self.sequence.markers:
            x = self.x_for(marker.time)
            if not marker.name or x < HEADER_WIDTH or x > self.width():
                continue
            etiqueta = marker.name[:22] + (" ✎" if marker.note else "")
            caja = QRectF(x + 3, RULER_HEIGHT + 1, metricas.horizontalAdvance(etiqueta) + 8, 13)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(marker.color))
            painter.drawRoundedRect(caja, 3, 3)
            painter.setPen(MARKER_TEXT)
            painter.drawText(caja, Qt.AlignCenter, etiqueta)

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

            self._draw_header(painter, index, track, y)

            painter.save()
            painter.setClipRect(QRectF(HEADER_WIDTH, y, self.width() - HEADER_WIDTH,
                                       TRACK_HEIGHT))
            apagada = not track.enabled or (track.kind == "audio" and (
                track.muted or (any(t.solo for t in self.sequence.audio_tracks())
                                and not track.solo)))
            if apagada:
                painter.setOpacity(0.45)
            for clip in track.clips:
                self._draw_clip(painter, clip, y, _color_for(track, clip), track.kind)
            if track.kind == "video":
                self._draw_dissolves(painter, track, y)
            painter.setOpacity(1.0)
            if track.locked:
                painter.setPen(QPen(LOCKED_HATCH, 1))
                x = HEADER_WIDTH - (y % 12)
                while x < self.width():
                    painter.drawLine(QPointF(x, y + TRACK_HEIGHT), QPointF(x + TRACK_HEIGHT, y))
                    x += 12
            painter.restore()

    # --- cabecera de pista --------------------------------------------------

    def header_buttons(self, index: int) -> list[tuple[str, QRectF]]:
        """(interruptor, rectángulo) de cada botón de la cabecera de la pista."""
        track = self.sequence.tracks[index]
        y = self._track_top(index) + (TRACK_HEIGHT - BUTTON) / 2
        nombres = TRACK_BUTTONS.get(track.kind, ())
        x = HEADER_WIDTH - 6 - len(nombres) * (BUTTON + 3)
        salida = []
        for nombre in nombres:
            salida.append((nombre, QRectF(x, y, BUTTON, BUTTON)))
            x += BUTTON + 3
        return salida

    def _draw_header(self, painter: QPainter, index: int, track, y: float) -> None:
        painter.setPen(DIM_TEXT if track.enabled else QColor("#4d535b"))
        painter.setFont(QFont("", 8, QFont.Bold))
        painter.drawText(QRectF(6, y, 34, TRACK_HEIGHT),
                         Qt.AlignLeft | Qt.AlignVCenter, track.name)

        for nombre, rect in self.header_buttons(index):
            valor = getattr(track, nombre)
            # "enabled" se prende al revés que los demás: encendido es lo normal.
            resaltado = (not valor) if nombre == "enabled" else valor
            painter.setPen(QPen(QColor("#3a3f46"), 1))
            painter.setBrush(BUTTON_ON[nombre].darker(160) if resaltado else BUTTON_BG)
            painter.drawRoundedRect(rect, 3, 3)
            color = BUTTON_ON[nombre] if resaltado else QColor("#8a9099")
            self._draw_button_icon(painter, nombre, rect, color, valor)

    @staticmethod
    def _draw_button_icon(painter: QPainter, nombre: str, rect: QRectF,
                          color: QColor, valor: bool) -> None:
        c = rect.center()
        painter.setPen(QPen(color, 1.3))
        painter.setBrush(Qt.NoBrush)
        if nombre == "enabled":
            ojo = QPainterPath()
            ojo.moveTo(c.x() - 6, c.y())
            ojo.quadTo(c.x(), c.y() - 6, c.x() + 6, c.y())
            ojo.quadTo(c.x(), c.y() + 6, c.x() - 6, c.y())
            painter.drawPath(ojo)
            painter.setBrush(color)
            painter.drawEllipse(c, 1.8, 1.8)
            if not valor:
                painter.drawLine(QPointF(c.x() - 6, c.y() + 5), QPointF(c.x() + 6, c.y() - 5))
        elif nombre == "locked":
            painter.drawRect(QRectF(c.x() - 4, c.y() - 1, 8, 6))
            arco = QPainterPath()
            arco.moveTo(c.x() - 2.5, c.y() - 1)
            arco.lineTo(c.x() - 2.5, c.y() - 3.5)
            arco.arcTo(QRectF(c.x() - 2.5, c.y() - 6, 5, 5), 180, -180)
            arco.lineTo(c.x() + 2.5, c.y() - (1 if valor else 3))
            painter.drawPath(arco)
        else:
            painter.setFont(QFont("", 7, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, "M" if nombre == "muted" else "S")

    def _draw_clip(self, painter: QPainter, clip, y: float, color: QColor,
                   track_kind: str = "video") -> None:
        rect = QRectF(self.x_for(clip.start), y + 2,
                      clip.duration * self.pixels_per_second, TRACK_HEIGHT - 4)
        if rect.right() < HEADER_WIDTH or rect.left() > self.width():
            return

        chosen, por_enlace = self._is_selected(clip)
        borde = SELECTED if chosen else (LINKED_SELECTED if por_enlace else CLIP_BORDER)
        painter.setPen(QPen(borde, 2 if chosen or por_enlace else 1))
        painter.setBrush(color.lighter(115) if chosen or por_enlace else color)
        painter.drawRoundedRect(rect, 3, 3)

        if track_kind == "audio" and rect.width() > 8:
            self._draw_wave(painter, clip, rect)

        self._draw_fades(painter, clip, rect)
        self._draw_keyframes(painter, clip, rect)

        self._draw_clip_markers(painter, clip, rect)

        if rect.width() > 34:
            painter.setPen(QColor("#eef1f4"))
            fuente = QFont("", 8)
            # Enlazado se ve subrayado, como en Premiere: se nota sin ocupar
            # lugar y sin un ícono más.
            fuente.setUnderline(bool(getattr(clip, "link", "")))
            painter.setFont(fuente)
            painter.drawText(rect.adjusted(6, 0, -6, 0),
                             Qt.AlignLeft | Qt.AlignVCenter, clip.name)

        desfase = link_offset(self.sequence, clip)
        if abs(desfase) > 1e-6 and rect.width() > 40:
            cuadros = round(desfase * self.sequence.fps)
            painter.setPen(OFFSET_TAG)
            painter.setFont(QFont("", 7, QFont.Bold))
            painter.drawText(rect.adjusted(6, 1, -6, 0), Qt.AlignLeft | Qt.AlignTop,
                             f"{cuadros:+d}")

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
            painter.setBrush(DIP_FILLS.get(getattr(clip, "transition", ""), DISSOLVE))
            painter.drawRect(rect)

            # El moño: dos diagonales cruzadas, como en cualquier editor.
            painter.setPen(QPen(DISSOLVE_EDGE, 1))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())

    def _draw_clip_markers(self, painter: QPainter, clip, rect: QRectF) -> None:
        """Los marcadores del clip: una muesca de color en la orilla de arriba."""
        for marker in getattr(clip, "markers", ()) or ():
            x = self.x_for(clip.start + marker.time)
            if x < max(HEADER_WIDTH, rect.left()) or x > min(self.width(), rect.right()):
                continue
            muesca = QPainterPath()
            muesca.moveTo(x - 4, rect.top())
            muesca.lineTo(x + 4, rect.top())
            muesca.lineTo(x, rect.top() + 6)
            muesca.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(marker.color))
            painter.drawPath(muesca)

    def markers_near(self, x: float, y: float):
        """(marcador, dueño) bajo el cursor: en la regla o dentro de un clip."""
        tolerancia = 5 / self.pixels_per_second
        t = self.time_for(x)
        if y < RULER_HEIGHT + 12:
            marcador = next((m for m in self.sequence.markers
                             if abs(m.time - t) <= tolerancia), None)
            if marcador is not None:
                return marcador, None
        _, item, _ = self._item_at(x, y)
        if item is not None:
            marcador = next((m for m in getattr(item, "markers", ()) or ()
                             if abs(item.start + m.time - t) <= tolerancia), None)
            if marcador is not None:
                return marcador, item
        return None, None

    def event(self, event) -> bool:
        """El nombre y la nota del marcador, al pasar el cursor encima."""
        if event.type() == QEvent.ToolTip:
            pos = event.position() if hasattr(event, "position") else event.pos()
            if pos.x() < HEADER_WIDTH:
                indice = self._track_index_at(pos.y())
                for nombre, rect in (self.header_buttons(indice) if indice is not None else ()):
                    if rect.contains(pos):
                        QToolTip.showText(event.globalPos(), BUTTON_TIPS[nombre], self)
                        return True
            marcador, _ = self.markers_near(pos.x(), pos.y())
            if marcador is not None and (marcador.name or marcador.note):
                texto = marcador.name or "Marcador"
                if marcador.note:
                    texto += "\n" + marcador.note
                QToolTip.showText(event.globalPos(), texto, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def _draw_keyframes(self, painter: QPainter, clip, rect: QRectF) -> None:
        """Rombos en la orilla de abajo, uno por instante animado.

        Van dentro del clip y no en una pista aparte: así se ve de un vistazo
        qué clips están animados sin tener que desplegar nada.
        """
        tiempos = animate.all_key_times(clip)
        if not tiempos:
            return

        y = rect.bottom() - 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(MARKER)
        for local in tiempos:
            x = self.x_for(clip.start + local)
            if x < max(HEADER_WIDTH, rect.left()) or x > min(self.width(), rect.right()):
                continue
            rombo = QPainterPath()
            rombo.moveTo(x, y - 4)
            rombo.lineTo(x + 4, y)
            rombo.lineTo(x, y + 4)
            rombo.lineTo(x - 4, y)
            rombo.closeSubpath()
            painter.drawPath(rombo)

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

        Cada columna de pixeles toma el mínimo y el máximo de **todos** los
        cubos que le tocan. Con el zoom muy afuera un pixel cubre muchos
        cubos, y tomar solo uno —como antes— se saltaba los golpes que
        cayeran entre columna y columna.

        La onda ya está calculada: hacer zoom solo cambia qué pedazo del
        arreglo se lee, nunca se vuelve a decodificar.
        """
        data = self._wave_for(clip.source)
        if data is None or data.ndim != 2 or data.shape[1] == 0:
            return

        visible = rect.intersected(QRectF(HEADER_WIDTH, rect.top(),
                                          self.width() - HEADER_WIDTH, rect.height()))
        if visible.width() < 2:
            return

        middle = rect.center().y()
        half = rect.height() / 2 - 3
        velocidad = getattr(clip, "speed", 1.0) or 1.0
        entrada = getattr(clip, "in_point", 0.0)
        cubos_por_pixel = velocidad * PEAKS_PER_SECOND / self.pixels_per_second
        total = data.shape[1]

        painter.setPen(QPen(WAVE, 1))
        for x in range(int(visible.left()), int(visible.right())):
            # De pixel a tiempo del clip, y de ahí a tiempo del archivo.
            dentro = (x - rect.left()) / self.pixels_per_second
            desde = int((entrada + dentro * velocidad) * PEAKS_PER_SECOND)
            hasta = max(desde + 1, int(desde + cubos_por_pixel))
            if desde >= total or hasta <= 0:
                continue
            desde, hasta = max(0, desde), min(total, hasta)
            bajo = float(data[0, desde:hasta].min())
            alto = float(data[1, desde:hasta].max())
            painter.drawLine(QPointF(x, middle - alto * half),
                             QPointF(x, middle - bajo * half))

    def _wave_for(self, source):
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
        ignorados = ignore if isinstance(ignore, list) else [ignore]
        return self._snap_many(t, ignorados)

    def _snap_many(self, t: float, ignorados: list) -> float:
        """Jala el tiempo hacia los puntos de interés que estén muy cerca.

        Sin esto es imposible pegar dos clips sin dejar un hueco de un par
        de milisegundos, que luego se ve como un parpadeo negro.
        """
        candidates = [0.0, self.playhead]
        candidates += [m.time for m in self.sequence.markers]
        for track in self.sequence.tracks:
            for item in track.clips:
                candidates += [item.start + m.time for m in getattr(item, "markers", ()) or ()]
        if self.mark_in is not None:
            candidates.append(self.mark_in)
        if self.mark_out is not None:
            candidates.append(self.mark_out)
        for track in self.sequence.tracks:
            for item in track.clips:
                if not any(item is x for x in ignorados):
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
            self._press_header(pos)
            return

        if pos.y() < RULER_HEIGHT:
            self._scrubbing = True
            self._scrub(pos.x())
            return

        index, item, zone = self._item_at(pos.x(), pos.y())

        # Lo de una pista bloqueada ni se selecciona: el clic mueve el
        # playhead, igual que en un hueco.
        if item is None or self.sequence.tracks[index].locked:
            if not (event.modifiers() & Qt.ControlModifier):
                self.select(None)
            self._scrubbing = True
            self._scrub(pos.x())
            return

        if self.tool == TOOL_RAZOR:
            self.cut_requested.emit(item, self.time_for(pos.x()))
            return

        if event.modifiers() & Qt.ControlModifier:
            self.toggle_extra(item)
            return

        ya_estaba = item is self.selected or any(item is x for x in self.extra)
        if not ya_estaba:
            self.select(item)
        elif item is not self.selected:
            # Clic sobre uno de los que ya estaban: pasa a ser el principal
            # sin perder la selección múltiple, para poder arrastrar todos.
            resto = [x for x in [self.selected, *self.extra] if x is not item]
            self.selected, self.extra = item, resto
            self.selection_changed.emit(item)
        self.ignore_link = bool(event.modifiers() & Qt.AltModifier)
        self.update()

        if self.tool == TOOL_SLIP:
            if isinstance(item, Clip):
                self._drag = {
                    "item": item,
                    "track": index,
                    "zone": "slip",
                    "grab": self.time_for(pos.x()),
                    "in_point": item.in_point,
                    "partners": [(p, p.in_point) for p in self._partners(item)
                                 if isinstance(p, Clip)],
                    "moved": False,
                }
            return

        self._drag = {
            "item": item,
            "track": index,
            "zone": zone,
            "grab": self.time_for(pos.x()),
            "start": item.start,
            "duration": item.duration,
            "in_point": getattr(item, "in_point", None),
            "partners": [(p, p.start, p.duration, getattr(p, "in_point", None))
                         for p in self._partners(item)],
            "moved": False,
        }
        if zone == "inicio":
            # Recortar la cabeza se recalcula desde el estado de antes en cada
            # movimiento del mouse: los keyframes se recorren, y recorrerlos
            # sobre lo ya recorrido los iría arrastrando.
            from vortex_studio.model.commands import head_state
            self._drag["heads"] = {id(x): head_state(x)
                                   for x in [item, *self._partners(item)]}

    def _partners(self, item) -> list:
        """Lo que se arrastra junto con `item`: el resto de la selección y
        sus enlazados, menos lo que esté en pistas bloqueadas."""
        grupo = self.selected_items()
        if not any(item is x for x in grupo):
            grupo = [item]
        salida = []
        for otro in grupo:
            if otro is item:
                continue
            pista = self.sequence.track_of(otro)
            if pista is not None and not pista.locked:
                salida.append(otro)
        return salida

    def _press_header(self, pos) -> None:
        index = self._track_index_at(pos.y())
        if index is None:
            return
        for nombre, rect in self.header_buttons(index):
            if rect.adjusted(-2, -2, 2, 2).contains(pos):
                track = self.sequence.tracks[index]
                setattr(track, nombre, not getattr(track, nombre))
                self.update()
                self.track_toggled.emit(track, nombre)
                return

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
        if zone == "slip":
            self._slip_drag(pos)
            self.live_edit.emit()       # el preview tiene que seguir al arrastre
        elif zone == "cuerpo":
            self._move_drag(pos)
        else:
            self._trim_drag(pos, zone)
        self.update()

    def _slip_drag(self, pos) -> None:
        """Arrastrar a la derecha mueve el contenido a la derecha.

        Es decir, se ve material de **antes**: el punto de entrada baja.
        Así funciona en Premiere, y se siente como agarrar la película por
        dentro del clip y correrla.
        """
        drag = self._drag
        clip = drag["item"]
        corrido = self.time_for(pos.x()) - drag["grab"]
        clip.in_point = drag["in_point"]
        duracion = self.source_duration(clip) if self.source_duration else None
        aplicado = slip_clip(clip, -corrido * max(clip.speed, 0.0), duracion)
        for otro, entrada in drag.get("partners", ()):
            otro.in_point = entrada
            slip_clip(otro, aplicado, duracion)

    def _move_drag(self, pos) -> None:
        drag = self._drag
        item = drag["item"]

        delta = self.time_for(pos.x()) - drag["grab"]
        socios = drag.get("partners", ())
        ignorados = [item, *(p[0] for p in socios)]
        item.start = max(0.0, self._snap_many(drag["start"] + delta, ignorados))

        # Los compañeros se mueven lo mismo que el principal, y nadie pasa
        # de cero: si uno toparía, se frena el grupo entero.
        corrido = item.start - drag["start"]
        if socios:
            corrido = max(corrido, -min(inicio for _, inicio, _, _ in socios))
            item.start = drag["start"] + corrido
            for otro, inicio, _, _ in socios:
                otro.start = inicio + corrido

        # Cambio de pista: solo a una que acepte este tipo de elemento.
        index = self._track_index_at(pos.y())
        if index is not None and index != drag["track"]:
            target = self.sequence.tracks[index]
            if accepts(target, item) and not target.locked:
                self.sequence.tracks[drag["track"]].clips.remove(item)
                target.add(item)
                drag["track"] = index

    def _trim_drag(self, pos, zone: str) -> None:
        drag = self._drag
        item = drag["item"]
        minimum = self.sequence.frame_duration
        edge = self._snap(self.time_for(pos.x()), ignore=item)

        if zone == "inicio":
            from vortex_studio.model.commands import restore_head, trim_head

            original_end = drag["start"] + drag["duration"]
            new_start = max(0.0, min(edge, original_end - minimum))
            corrido = new_start - drag["start"]
            # En un clip de archivo, recortar por el inicio avanza el punto
            # de entrada: se ve más adelante del original, no se estira. En
            # tiempo de archivo, así que cuenta la velocidad —o el remapeo—,
            # y la animación se recorre para seguir pegada a la imagen.
            restore_head(item, drag["heads"][id(item)])
            trim_head(item, corrido)
            for otro, inicio, duracion, entrada in drag.get("partners", ()):
                # Solo se recorta junto el compañero que empezaba en el mismo
                # lugar: recortar la cabeza de un audio más largo que su video
                # le comería material que nadie pidió quitar.
                if abs(inicio - drag["start"]) > 1e-6:
                    continue
                restore_head(otro, drag["heads"][id(otro)])
                trim_head(otro, min(corrido, duracion - minimum))
        else:
            item.duration = max(minimum, edge - item.start)
            fin_original = drag["start"] + drag["duration"]
            for otro, inicio, duracion, _ in drag.get("partners", ()):
                if abs(inicio + duracion - fin_original) > 1e-6:
                    continue
                otro.duration = max(minimum, item.end - otro.start)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._scrubbing = False
        self._snap_at = None

        if self._drag is not None:
            if self._drag["moved"]:
                track = self.sequence.tracks[self._drag["track"]]
                self._resolve_overlap(track, self._drag["item"])
                track.clips.sort(key=lambda c: c.start)
                if self._drag["zone"] == "cuerpo":
                    for otro, *_ in self._drag.get("partners", ()):
                        pista = self.sequence.track_of(otro)
                        if pista is not None:
                            self._resolve_overlap(pista, otro)
                label = {"cuerpo": "Mover clip", "slip": "Deslizar contenido"}.get(
                    self._drag["zone"], "Recortar clip")
                self.edit_finished.emit(label)
            self._drag = None
            self.update()

    @staticmethod
    def _resolve_overlap(track, item) -> None:
        """Lo que se suelta encima tapa a lo que ya estaba. Ver `overwrite`."""
        overwrite(track, item)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Doble clic en un marcador lo abre para ponerle nombre, nota y color."""
        pos = event.position()
        marcador, dueno = self.markers_near(pos.x(), pos.y())
        if marcador is not None:
            self._drag = None
            self.marker_activated.emit(marcador, dueno)
            return
        _, item, _ = self._item_at(pos.x(), pos.y())
        if item is not None:
            self._drag = None
            self.clip_activated.emit(item)
            return
        super().mouseDoubleClickEvent(event)

    # --- soltar medios desde el panel ----------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MEDIA_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MEDIA_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        datos = event.mimeData()
        if not datos.hasFormat(MEDIA_MIME):
            event.ignore()
            return
        pos = event.position()
        indice = self._track_index_at(pos.y())
        tiempo = self._snap(self.time_for(pos.x()))
        self._snap_at = None
        for linea in bytes(datos.data(MEDIA_MIME)).decode("utf-8").splitlines():
            if linea.strip():
                self.media_dropped.emit(Path(linea.strip()), tiempo,
                                        -1 if indice is None else indice)
        event.acceptProposedAction()

    def _update_cursor(self, pos) -> None:
        if self.tool in (TOOL_RAZOR, TOOL_SLIP):
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
