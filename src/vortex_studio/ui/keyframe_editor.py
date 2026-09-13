"""El editor de keyframes: una gráfica por parámetro, con sus curvas.

La capacidad es la del editor de gráficas de After Effects; la interfaz se
queda en lo que se usa. Se escoge el parámetro de una lista —los animados
llevan un rombo—, se ve su valor a lo largo del clip, y cada keyframe se
arrastra en tiempo y en valor. La interpolación del tramo se elige de una
lista: lineal, suave, sostenida o bezier. Con bezier aparecen las dos
manijas del tramo y también se arrastran.

Doble clic en la gráfica pone un keyframe ahí; `Supr` borra el elegido.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.model import animate
from vortex_studio.model import keyframes as kf

MARGIN = 14
KEY_RADIUS = 5
HANDLE_RADIUS = 4

BG = QColor("#15171a")
GRID = QColor("#262a30")
CURVE = QColor("#5f9de0")
KEY = QColor("#e8c15a")
KEY_SELECTED = QColor("#ffffff")
HANDLE = QColor("#e0574a")
PLAYHEAD = QColor("#e0574a")
TEXT = QColor("#7d838c")


class CurveGraph(QWidget):
    """La gráfica: tiempo del clip en horizontal, valor en vertical."""

    edited = Signal()            # a medio arrastre
    released = Signal(str)       # al soltar, con la etiqueta del historial
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.item = None
        self.path = ""
        self.local = 0.0
        self.selected: float | None = None     # tiempo del keyframe elegido
        self._drag: dict | None = None
        self.setMinimumHeight(150)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)

    # --- datos ------------------------------------------------------------

    def set_data(self, item, path: str, local: float) -> None:
        cambio = item is not self.item or path != self.path
        self.item, self.path, self.local = item, path, local
        if cambio:
            self.selected = None
        self.update()

    @property
    def points(self) -> list:
        return animate.keys_for(self.item, self.path) if self.item and self.path else []

    @property
    def duration(self) -> float:
        return max(0.04, getattr(self.item, "duration", 1.0)) if self.item else 1.0

    def value_range(self) -> tuple[float, float]:
        """El rango visible: el de los keyframes con aire, dentro del parámetro."""
        param = animate.PARAMS.get(self.path)
        valores = [kf.value_of(k) for k in self.points]
        if self.item is not None and self.path:
            valores.append(animate.value_at(self.item, self.path, self.local))
        if not valores:
            return (param.minimum, param.maximum) if param else (0.0, 1.0)
        bajo, alto = min(valores), max(valores)
        aire = max((alto - bajo) * 0.25, (param.maximum - param.minimum) * 0.05 if param else 0.1)
        return bajo - aire, alto + aire

    # --- geometría --------------------------------------------------------

    def _box(self) -> QRectF:
        return QRectF(MARGIN, MARGIN, max(10, self.width() - 2 * MARGIN),
                      max(10, self.height() - 2 * MARGIN))

    def to_screen(self, local: float, value: float) -> QPointF:
        caja = self._box()
        bajo, alto = self.value_range()
        x = caja.left() + caja.width() * (local / self.duration)
        y = caja.bottom() - caja.height() * ((value - bajo) / max(1e-9, alto - bajo))
        return QPointF(x, y)

    def from_screen(self, pos: QPointF) -> tuple[float, float]:
        caja = self._box()
        bajo, alto = self.value_range()
        local = (pos.x() - caja.left()) / caja.width() * self.duration
        valor = bajo + (caja.bottom() - pos.y()) / caja.height() * (alto - bajo)
        return max(0.0, min(self.duration, local)), valor

    def _segment_handles(self, key, siguiente) -> tuple[QPointF, QPointF]:
        """Dónde se dibujan las dos manijas de un tramo bezier."""
        x1, y1, x2, y2 = kf.handles_of(key)
        t0, t1 = kf.time_of(key), kf.time_of(siguiente)
        v0, v1 = kf.value_of(key), kf.value_of(siguiente)
        return (self.to_screen(t0 + (t1 - t0) * x1, v0 + (v1 - v0) * y1),
                self.to_screen(t0 + (t1 - t0) * x2, v0 + (v1 - v0) * y2))

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), BG)
        caja = self._box()

        painter.setPen(QPen(GRID, 1))
        for i in range(1, 4):
            y = caja.top() + caja.height() * i / 4
            painter.drawLine(QPointF(caja.left(), y), QPointF(caja.right(), y))

        if self.item is None or not self.path:
            painter.setPen(TEXT)
            painter.drawText(self.rect(), Qt.AlignCenter, "Selecciona un clip para ver sus keyframes")
            painter.end()
            return

        bajo, alto = self.value_range()
        painter.setPen(TEXT)
        painter.drawText(QPointF(4, MARGIN - 3), f"{alto:.3g}")
        painter.drawText(QPointF(4, self.height() - 3), f"{bajo:.3g}")

        trazo = QPainterPath()
        pasos = max(40, int(caja.width() / 3))
        for i in range(pasos + 1):
            local = self.duration * i / pasos
            punto = self.to_screen(local, animate.value_at(self.item, self.path, local))
            trazo.moveTo(punto) if i == 0 else trazo.lineTo(punto)
        painter.setPen(QPen(CURVE, 1.8))
        painter.drawPath(trazo)

        puntos = self.points
        for key, siguiente in zip(puntos, puntos[1:]):
            if kf.interp_of(key) == kf.BEZIER:
                a, b = self._segment_handles(key, siguiente)
                painter.setPen(QPen(HANDLE, 1, Qt.DashLine))
                painter.drawLine(self.to_screen(kf.time_of(key), kf.value_of(key)), a)
                painter.drawLine(self.to_screen(kf.time_of(siguiente), kf.value_of(siguiente)), b)
                painter.setPen(Qt.NoPen)
                painter.setBrush(HANDLE)
                painter.drawEllipse(a, HANDLE_RADIUS, HANDLE_RADIUS)
                painter.drawEllipse(b, HANDLE_RADIUS, HANDLE_RADIUS)

        for key in puntos:
            centro = self.to_screen(kf.time_of(key), kf.value_of(key))
            elegido = self.selected is not None and abs(kf.time_of(key) - self.selected) < 1e-4
            rombo = QPainterPath()
            rombo.moveTo(centro.x(), centro.y() - KEY_RADIUS)
            rombo.lineTo(centro.x() + KEY_RADIUS, centro.y())
            rombo.lineTo(centro.x(), centro.y() + KEY_RADIUS)
            rombo.lineTo(centro.x() - KEY_RADIUS, centro.y())
            rombo.closeSubpath()
            painter.setPen(QPen(KEY_SELECTED if elegido else Qt.black, 1.2))
            painter.setBrush(KEY)
            painter.drawPath(rombo)

        x = caja.left() + caja.width() * (self.local / self.duration)
        painter.setPen(QPen(PLAYHEAD, 1))
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.end()

    # --- edición ----------------------------------------------------------

    def _hit(self, pos: QPointF):
        """("key", t) · ("handle", t_del_tramo, 1|2) · None"""
        puntos = self.points
        for key, siguiente in zip(puntos, puntos[1:]):
            if kf.interp_of(key) == kf.BEZIER:
                a, b = self._segment_handles(key, siguiente)
                if (a - pos).manhattanLength() <= HANDLE_RADIUS * 2:
                    return ("handle", kf.time_of(key), 1)
                if (b - pos).manhattanLength() <= HANDLE_RADIUS * 2:
                    return ("handle", kf.time_of(key), 2)
        for key in puntos:
            if (self.to_screen(kf.time_of(key), kf.value_of(key)) - pos).manhattanLength() \
                    <= KEY_RADIUS * 2:
                return ("key", kf.time_of(key))
        return None

    def mousePressEvent(self, event) -> None:
        if self.item is None or event.button() != Qt.LeftButton:
            return
        golpe = self._hit(event.position())
        if golpe is None:
            self.selected = None
            self.selection_changed.emit()
            self.update()
            return
        if golpe[0] == "key":
            self.selected = golpe[1]
            self._drag = {"kind": "key", "time": golpe[1], "moved": False}
        else:
            self._drag = {"kind": "handle", "time": golpe[1], "which": golpe[2], "moved": False}
        self.selection_changed.emit()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None:
            return
        local, valor = self.from_screen(event.position())
        if self._drag["kind"] == "key":
            self._drag["time"] = self.move_key(self._drag["time"], local, valor)
        else:
            self.move_handle(self._drag["time"], self._drag["which"], local, valor)
        self._drag["moved"] = True
        self.edited.emit()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None and self._drag["moved"]:
            self.released.emit("Mover keyframe" if self._drag["kind"] == "key"
                               else "Curva del keyframe")
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:
        if self.item is None or not self.path:
            return
        local, _ = self.from_screen(event.position())
        self.add_key(local)
        self.released.emit("Keyframe")

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected is not None:
            self.remove_selected()
            self.released.emit("Quitar keyframe")
        else:
            super().keyPressEvent(event)

    # --- operaciones, separadas del mouse para poder probarlas -------------

    def add_key(self, local: float) -> None:
        animate.add_key(self.item, self.path, round(local, 4))
        self.selected = round(local, 4)
        self.update()

    def remove_selected(self) -> bool:
        if self.selected is None:
            return False
        hecho = animate.remove_key(self.item, self.path, self.selected, tolerance=1e-3)
        self.selected = None
        self.update()
        return hecho

    def move_key(self, time: float, new_local: float, new_value: float) -> float:
        """Mueve el keyframe de `time`. No lo deja cruzar a sus vecinos."""
        puntos = self.points
        tiempos = [kf.time_of(k) for k in puntos]
        indice = min(range(len(tiempos)), key=lambda i: abs(tiempos[i] - time))
        antes = tiempos[indice - 1] + 1e-3 if indice > 0 else 0.0
        despues = tiempos[indice + 1] - 1e-3 if indice + 1 < len(tiempos) else self.duration
        nuevo = round(max(antes, min(despues, new_local)), 4)
        param = animate.PARAMS.get(self.path)
        if param is not None:
            new_value = max(param.minimum, min(param.maximum, new_value))
        animate.set_keys_for(self.item, self.path,
                             kf.move_key(puntos, tiempos[indice], nuevo, new_value, 1e-3))
        self.selected = nuevo
        self.update()
        return nuevo

    def move_handle(self, time: float, which: int, local: float, value: float) -> None:
        puntos = self.points
        indice = next((i for i, k in enumerate(puntos) if abs(kf.time_of(k) - time) < 1e-3), None)
        if indice is None or indice + 1 >= len(puntos):
            return
        key, siguiente = puntos[indice], puntos[indice + 1]
        t0, t1 = kf.time_of(key), kf.time_of(siguiente)
        v0, v1 = kf.value_of(key), kf.value_of(siguiente)
        x = (local - t0) / max(1e-9, t1 - t0)
        y = (value - v0) / (v1 - v0) if abs(v1 - v0) > 1e-9 else 0.0
        x1, y1, x2, y2 = kf.handles_of(key)
        if which == 1:
            x1, y1 = max(0.0, min(1.0, x)), y
        else:
            x2, y2 = max(0.0, min(1.0, x)), y
        animate.set_keys_for(self.item, self.path, kf.set_interpolation(
            puntos, t0, kf.BEZIER, [x1, y1, x2, y2], tolerance=1e-3))
        self.update()

    def set_interpolation(self, interp: str) -> bool:
        if self.selected is None:
            return False
        animate.set_keys_for(self.item, self.path, kf.set_interpolation(
            self.points, self.selected, interp, tolerance=1e-3))
        self.update()
        return True


class KeyframeEditor(QDockWidget):
    changed = Signal()
    committed = Signal(str)

    def __init__(self) -> None:
        super().__init__("Keyframes")
        self.setObjectName("editor_de_keyframes")
        self.item = None
        self.local = 0.0

        self.param = QComboBox()
        self.param.setToolTip("El parámetro que se ve en la gráfica. ◆ = animado")
        self.param.currentIndexChanged.connect(self._param_changed)

        self.graph = CurveGraph()
        self.graph.edited.connect(self.changed.emit)
        self.graph.released.connect(self.committed.emit)
        self.graph.selection_changed.connect(self._selection_changed)

        self.interp = QComboBox()
        self.interp.addItems(kf.INTERPOLATIONS)
        self.interp.setToolTip("Cómo avanza el valor desde el keyframe elegido hasta el siguiente")
        self.interp.activated.connect(self._interp_chosen)

        self.add_button = QPushButton("◆ Keyframe aquí")
        self.add_button.setToolTip("Pone un keyframe en el playhead con el valor de ahora")
        self.add_button.clicked.connect(self.add_key_here)
        self.remove_button = QPushButton("Quitar")
        self.remove_button.clicked.connect(self._remove)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#6f757e; font-size:10px;")

        arriba = QHBoxLayout()
        arriba.addWidget(self.param, 1)
        arriba.addWidget(QLabel("Interpolación"))
        arriba.addWidget(self.interp)
        arriba.addWidget(self.add_button)
        arriba.addWidget(self.remove_button)

        cuerpo = QWidget()
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(arriba)
        layout.addWidget(self.graph, 1)
        layout.addWidget(self._hint)
        self.setWidget(cuerpo)
        self.set_target(None, 0.0)

    def set_target(self, item, local: float) -> None:
        anterior = self.param.currentData()
        cambio = item is not self.item
        self.item, self.local = item, local
        if cambio or self.param.count() == 0:
            self._fill_params(anterior)
        else:
            self._mark_animated()
        self.graph.set_data(item, self.param.currentData() or "", local)
        activo = item is not None and self.param.count() > 0
        for widget in (self.param, self.interp, self.add_button, self.remove_button):
            widget.setEnabled(activo)
        self._selection_changed()

    def _fill_params(self, preferido: str | None) -> None:
        self.param.blockSignals(True)
        self.param.clear()
        if self.item is not None:
            animados = set(animate.animated_paths(self.item))
            for p in animate.params_for(self.item):
                marca = "◆ " if p.path in animados else "    "
                self.param.addItem(f"{marca}{p.group} · {p.label}", p.path)
            primero_animado = next((i for i in range(self.param.count())
                                    if self.param.itemData(i) in animados), 0)
            indice = self.param.findData(preferido) if preferido else -1
            self.param.setCurrentIndex(indice if indice >= 0 else primero_animado)
        self.param.blockSignals(False)

    def _mark_animated(self) -> None:
        animados = set(animate.animated_paths(self.item))
        for i in range(self.param.count()):
            ruta = self.param.itemData(i)
            p = animate.PARAMS[ruta]
            self.param.setItemText(i, f"{'◆ ' if ruta in animados else '    '}{p.group} · {p.label}")

    def select_param(self, path: str) -> bool:
        indice = self.param.findData(path)
        if indice < 0:
            return False
        self.param.setCurrentIndex(indice)
        return True

    def _param_changed(self, _indice: int) -> None:
        self.graph.set_data(self.item, self.param.currentData() or "", self.local)
        self._selection_changed()

    def _selection_changed(self) -> None:
        elegido = self.graph.selected
        puntos = self.graph.points
        key = kf.key_near(puntos, elegido, 1e-3) if elegido is not None else None
        self.interp.setEnabled(key is not None)
        self.remove_button.setEnabled(key is not None)
        if key is not None:
            self.interp.setCurrentText(kf.interp_of(key))
        if self.item is None:
            self._hint.setText("")
        elif not puntos:
            self._hint.setText("Sin animación. «◆ Keyframe aquí» o doble clic en la gráfica.")
        else:
            self._hint.setText(f"{len(puntos)} keyframe{'s' if len(puntos) != 1 else ''}. "
                               "Arrastra para mover; Supr borra el elegido.")

    def add_key_here(self) -> None:
        if self.item is None or not self.param.currentData():
            return
        self.graph.add_key(max(0.0, min(self.graph.duration, self.local)))
        self._mark_animated()
        self._selection_changed()
        self.committed.emit("Keyframe")

    def _remove(self) -> None:
        if self.graph.remove_selected():
            self._mark_animated()
            self._selection_changed()
            self.committed.emit("Quitar keyframe")

    def _interp_chosen(self, _indice: int) -> None:
        if self.graph.set_interpolation(self.interp.currentText()):
            self.committed.emit(f"Interpolación {self.interp.currentText().lower()}")
