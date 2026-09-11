"""Los paneles laterales: color y texto."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from vortex_studio.model import (
    ANCHORS,
    PROPS,
    RANGES,
    ColorAdjust,
    ImageOverlay,
    Title,
)
from vortex_studio.model.color import (
    BRIGHTNESS,
    CONTRAST,
    GAMMA,
    LOOKS,
    SATURATION,
    TEMPERATURE,
)
from vortex_studio.ui.widgets import SliderRow, column, section

PANEL_STYLE = """
QDockWidget { color: #9aa1aa; font-size: 11px; }
QDockWidget::title {
    background: #212429; padding: 6px 10px; border-bottom: 1px solid #2e3238;
}
QWidget { background: #1b1d21; color: #d6dae0; }
QPushButton {
    background: #2b2f34; border: 1px solid #3a3f46; border-radius: 4px;
    padding: 5px 10px; color: #d6dae0;
}
QPushButton:hover { background: #353a41; }
QPushButton:disabled { color: #5a6068; background: #232629; }
QComboBox, QPlainTextEdit, QDoubleSpinBox, QListWidget {
    background: #24282d; border: 1px solid #363b42; border-radius: 4px;
    padding: 4px; color: #d6dae0;
}
QComboBox QAbstractItemView {
    background: #24282d; selection-background-color: #3d6fa8; border: 1px solid #363b42;
}
QListWidget::item:selected { background: #3d6fa8; color: #ffffff; }
QCheckBox { color: #b6bcc4; font-size: 11px; spacing: 6px; }
"""


class ColorPanel(QDockWidget):
    """Corrección de color del clip que está bajo el playhead."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__("Color")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._adjust: ColorAdjust | None = None

        self._target = QLabel("Ningún clip bajo el playhead")
        self._target.setWordWrap(True)
        self._target.setStyleSheet("color:#7d838c; font-size:10px;")

        self._brightness = SliderRow("Brillo", *BRIGHTNESS)
        self._contrast = SliderRow("Contraste", *CONTRAST)
        self._saturation = SliderRow("Saturación", *SATURATION)
        self._gamma = SliderRow("Gamma", *GAMMA)
        self._temperature = SliderRow("Temperatura", *TEMPERATURE)

        self._look = QComboBox()
        self._look.addItems(LOOKS.keys())
        self._look.setToolTip("Combinaciones listas; luego puedes seguir ajustando")
        self._look.currentTextChanged.connect(self._apply_look)

        for row in self._rows():
            row.changed.connect(self._push)

        reset = QPushButton("Restablecer")
        reset.clicked.connect(self._reset)

        self.setWidget(column(
            self._target,
            section("Look"), self._look,
            section("Ajustes"),
            self._brightness, self._contrast, self._saturation,
            self._gamma, self._temperature,
            reset,
            None,
        ))
        self.set_target(None, "")

    def _rows(self) -> list[SliderRow]:
        return [self._brightness, self._contrast, self._saturation,
                self._gamma, self._temperature]

    def set_target(self, adjust: ColorAdjust | None, name: str) -> None:
        """Apunta el panel a un clip. Sin clip, los controles se apagan."""
        self._adjust = adjust
        self._target.setText(f"Clip: {name}" if adjust else "Ningún clip bajo el playhead")

        for row in self._rows():
            row.setEnabled(adjust is not None)
        self._look.setEnabled(adjust is not None)

        if adjust is not None:
            self._brightness.set_value(adjust.brightness)
            self._contrast.set_value(adjust.contrast)
            self._saturation.set_value(adjust.saturation)
            self._gamma.set_value(adjust.gamma)
            self._temperature.set_value(adjust.temperature)

    def _push(self) -> None:
        if self._adjust is None:
            return
        self._adjust.brightness = self._brightness.value()
        self._adjust.contrast = self._contrast.value()
        self._adjust.saturation = self._saturation.value()
        self._adjust.gamma = self._gamma.value()
        self._adjust.temperature = self._temperature.value()
        self.changed.emit()

    def _apply_look(self, nombre: str) -> None:
        """Un look es un punto de partida, no una capa aparte.

        Escribe en los mismos controles, así que después se puede seguir
        ajustando a mano sin tener que deshacerlo primero.
        """
        if self._adjust is None or nombre not in LOOKS:
            return

        self._adjust.apply(LOOKS[nombre])
        nombre_actual = self._target.text().removeprefix("Clip: ")
        self.set_target(self._adjust, nombre_actual)
        self._look.blockSignals(True)
        self._look.setCurrentText(nombre)
        self._look.blockSignals(False)
        self.changed.emit()

    def _reset(self) -> None:
        if self._adjust is None:
            return
        self._adjust.reset()
        self._look.blockSignals(True)
        self._look.setCurrentText("Ninguno")
        self._look.blockSignals(False)
        self.set_target(self._adjust, self._target.text().removeprefix("Clip: "))
        self.changed.emit()


class TextPanel(QDockWidget):
    """Lista de textos y edición del que esté seleccionado."""

    changed = Signal()
    add_requested = Signal()
    delete_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__("Texto")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._title: Title | None = None
        self._loading = False

        self._list = QListWidget()
        self._list.setMaximumHeight(108)
        self._list.currentRowChanged.connect(self._select_row)

        add = QPushButton("Agregar texto")
        add.setToolTip("Ctrl+T")
        add.clicked.connect(self.add_requested.emit)
        self._delete = QPushButton("Eliminar")
        self._delete.clicked.connect(lambda: self.delete_requested.emit(self._title))

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(add)
        buttons.addWidget(self._delete)

        self._text = QPlainTextEdit()
        self._text.setPlaceholderText("Escribe aquí…")
        self._text.setMaximumHeight(74)
        self._text.textChanged.connect(self._push)

        self._anchor = QComboBox()
        self._anchor.addItems(ANCHORS.keys())
        self._anchor.setCurrentText("Subtítulo")
        self._anchor.currentTextChanged.connect(self._push)

        self._align = QComboBox()
        self._align.addItems(["izquierda", "centro", "derecha"])
        self._align.setCurrentText("centro")
        self._align.currentTextChanged.connect(self._push)

        self._size = SliderRow("Tamaño", 2, 25, 8)
        self._size.changed.connect(self._push)

        self._color_button = QPushButton("Color del texto")
        self._color_button.clicked.connect(self._pick_color)

        self._duration = QDoubleSpinBox()
        self._duration.setRange(0.2, 600.0)
        self._duration.setSingleStep(0.5)
        self._duration.setValue(3.0)
        self._duration.setSuffix(" s")
        self._duration.valueChanged.connect(self._push)

        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("Duración"))
        duration_row.addWidget(self._duration, 1)

        self._bold = QCheckBox("Negrita")
        self._bold.setChecked(True)
        self._italic = QCheckBox("Cursiva")
        self._outline = QCheckBox("Contorno")
        self._outline.setChecked(True)
        self._background = QCheckBox("Caja de subtítulo")
        for box in (self._bold, self._italic, self._outline, self._background):
            box.toggled.connect(self._push)

        styles = QHBoxLayout()
        styles.addWidget(self._bold)
        styles.addWidget(self._italic)
        styles.addStretch(1)

        self.setWidget(column(
            self._list,
            buttons,
            section("Contenido"),
            self._text,
            section("Posición"),
            self._anchor, self._align, self._size,
            section("Estilo"),
            self._color_button, styles, self._outline, self._background,
            section("Tiempo"),
            duration_row,
            None,
        ))
        self.set_titles([], None)

    # --- lista ------------------------------------------------------------

    def set_titles(self, titles: list[Title], current: Title | None) -> None:
        self._titles = titles

        self._list.blockSignals(True)
        self._list.clear()
        for title in titles:
            item = QListWidgetItem(f"{title.start:6.2f}s   {title.name}")
            self._list.addItem(item)
        if current in titles:
            self._list.setCurrentRow(titles.index(current))
        self._list.blockSignals(False)

        self.edit(current)

    def _select_row(self, row: int) -> None:
        if 0 <= row < len(self._titles):
            self.edit(self._titles[row])
            self.changed.emit()

    # --- edición ----------------------------------------------------------

    def edit(self, title: Title | None) -> None:
        """Carga un texto en los controles.

        `_loading` evita el rebote: al poblar los controles se disparan sus
        señales, y sin la bandera cada carga se escribiría de vuelta encima
        del objeto que apenas se está mostrando.
        """
        self._title = title
        self._loading = True

        enabled = title is not None
        for widget in (self._text, self._anchor, self._align, self._size,
                       self._color_button, self._duration, self._bold,
                       self._italic, self._outline, self._background, self._delete):
            widget.setEnabled(enabled)

        if title is not None:
            self._text.setPlainText(title.text)
            self._align.setCurrentText(title.align)
            self._size.set_value(int(round(title.size * 100)))
            self._duration.setValue(title.duration)
            self._bold.setChecked(title.bold)
            self._italic.setChecked(title.italic)
            self._outline.setChecked(title.outline)
            self._background.setChecked(title.background)
            self._anchor.setCurrentText(self._anchor_name(title))
            self._paint_color_button(title.color)

        self._loading = False

    @staticmethod
    def _anchor_name(title: Title) -> str:
        """Qué preset corresponde a la posición actual, si es que alguno."""
        for name, (x, y) in ANCHORS.items():
            if abs(x - title.x) < 1e-6 and abs(y - title.y) < 1e-6:
                return name
        return "Centro"

    def _paint_color_button(self, color: str) -> None:
        contrast = "#101113" if QColor(color).lightness() > 140 else "#f0f3f6"
        self._color_button.setStyleSheet(
            f"QPushButton {{ background:{color}; color:{contrast};"
            f" border:1px solid #3a3f46; border-radius:4px; padding:5px 10px; }}"
        )

    def _pick_color(self) -> None:
        if self._title is None:
            return
        color = QColorDialog.getColor(QColor(self._title.color), self, "Color del texto")
        if color.isValid():
            self._title.color = color.name()
            self._paint_color_button(color.name())
            self.changed.emit()

    def _push(self) -> None:
        if self._title is None or self._loading:
            return

        self._title.text = self._text.toPlainText()
        self._title.align = self._align.currentText()
        self._title.size = self._size.value() / 100.0
        self._title.duration = self._duration.value()
        self._title.bold = self._bold.isChecked()
        self._title.italic = self._italic.isChecked()
        self._title.outline = self._outline.isChecked()
        self._title.background = self._background.isChecked()
        self._title.x, self._title.y = ANCHORS[self._anchor.currentText()]

        self.changed.emit()


class ImagePanel(QDockWidget):
    """Acomoda la imagen seleccionada sobre el video."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__("Imagen")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._overlay: ImageOverlay | None = None
        self._loading = False

        self._name = QLabel("Ninguna imagen seleccionada")
        self._name.setWordWrap(True)
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        self._x = SliderRow("Horizontal", 0, 100, 50)
        self._y = SliderRow("Vertical", 0, 100, 50)
        self._scale = SliderRow("Tamaño", 2, 200, 35)
        self._opacity = SliderRow("Opacidad", 0, 100, 100)
        for row in (self._x, self._y, self._scale, self._opacity):
            row.changed.connect(self._push)

        self._duration = QDoubleSpinBox()
        self._duration.setRange(0.2, 600.0)
        self._duration.setSingleStep(0.5)
        self._duration.setValue(4.0)
        self._duration.setSuffix(" s")
        self._duration.valueChanged.connect(self._push)

        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("Duración"))
        duration_row.addWidget(self._duration, 1)

        center = QPushButton("Centrar")
        center.clicked.connect(self._center)
        cover = QPushButton("Llenar el cuadro")
        cover.clicked.connect(self._cover)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(center)
        buttons.addWidget(cover)

        self.setWidget(column(
            self._name,
            section("Posición"), self._x, self._y,
            section("Aspecto"), self._scale, self._opacity,
            section("Tiempo"), duration_row,
            buttons,
            None,
        ))
        self.set_target(None)

    def set_target(self, overlay: ImageOverlay | None) -> None:
        self._overlay = overlay
        self._loading = True

        self._name.setText(f"Imagen: {overlay.name}" if overlay
                           else "Ninguna imagen seleccionada")
        for widget in (self._x, self._y, self._scale, self._opacity, self._duration):
            widget.setEnabled(overlay is not None)

        if overlay is not None:
            self._x.set_value(int(round(overlay.x * 100)))
            self._y.set_value(int(round(overlay.y * 100)))
            self._scale.set_value(max(2, int(round(overlay.scale * 100))))
            self._opacity.set_value(int(round(overlay.opacity * 100)))
            self._duration.setValue(overlay.duration)

        self._loading = False

    def _push(self) -> None:
        if self._overlay is None or self._loading:
            return
        self._overlay.x = self._x.value() / 100.0
        self._overlay.y = self._y.value() / 100.0
        self._overlay.scale = self._scale.value() / 100.0
        self._overlay.opacity = self._opacity.value() / 100.0
        self._overlay.duration = self._duration.value()
        self.changed.emit()

    def _center(self) -> None:
        if self._overlay is None:
            return
        self._x.set_value(50)
        self._y.set_value(50)
        self._push()

    def _cover(self) -> None:
        """Centrada y al ancho completo: el caso de una portada o un fondo."""
        if self._overlay is None:
            return
        self._x.set_value(50)
        self._y.set_value(50)
        self._scale.set_value(100)
        self._push()


class ClipPanel(QDockWidget):
    """Todo lo que se le puede hacer al clip seleccionado, con deslizadores.

    Lo mismo que hay en el menú Clip, pero se puede tantear moviendo: para
    ajustar un fundido o una transición uno quiere ver el resultado mientras
    lo mueve, no elegir un número de una lista.
    """

    changed = Signal()
    committed = Signal(str)

    def __init__(self) -> None:
        super().__init__("Clip")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._item = None
        self._loading = False

        self._name = QLabel("Nada seleccionado")
        self._name.setWordWrap(True)
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        self._fade_in = SliderRow("Entrada", 0, 300, 0)      # décimas de segundo
        self._fade_out = SliderRow("Salida", 0, 300, 0)
        self._dissolve = SliderRow("Transición", 0, 300, 0)
        self._speed = SliderRow("Velocidad", 10, 400, 100)   # porcentaje
        self._gain = SliderRow("Volumen", 0, 200, 100)

        for row in (self._fade_in, self._fade_out, self._dissolve,
                    self._speed, self._gain):
            row.changed.connect(self._push)
        for row in (self._speed, self._dissolve):
            # Velocidad y transición cambian la duración o piden decodificar
            # de nuevo: se aplican al soltar, no en cada pixel del arrastre.
            row._slider.sliderReleased.connect(self._commit_heavy)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color:#6f757e; font-size:10px;")

        self.setWidget(column(
            self._name,
            section("Fundidos (segundos)"), self._fade_in, self._fade_out,
            section("Transición con el anterior"), self._dissolve,
            section("Tiempo"), self._speed,
            section("Audio"), self._gain,
            self._info,
            None,
        ))
        self.set_target(None, False)

    # --- estado -----------------------------------------------------------

    def set_target(self, item, es_audio: bool) -> None:
        self._item = item
        self._loading = True

        tiene = item is not None
        self._name.setText(f"Clip: {item.name}" if tiene else "Nada seleccionado")

        es_clip = tiene and hasattr(item, "speed")
        self._fade_in.setEnabled(tiene)
        self._fade_out.setEnabled(tiene)
        self._dissolve.setEnabled(es_clip and not es_audio)
        self._speed.setEnabled(es_clip)
        self._gain.setEnabled(es_clip and es_audio)

        if tiene:
            self._fade_in.set_value(int(round(item.fade_in * 10)))
            self._fade_out.set_value(int(round(item.fade_out * 10)))
            if es_clip:
                self._dissolve.set_value(int(round(item.dissolve * 10)))
                self._speed.set_value(int(round(item.speed * 100)))
                self._gain.set_value(int(round(item.gain * 100)))
            self._describe()
        else:
            self._info.setText("")

        self._loading = False

    def _describe(self) -> None:
        item = self._item
        partes = [f"{item.duration:.2f} s en la pista"]
        if hasattr(item, "speed") and item.speed not in (0, 1.0):
            partes.append(f"{item.duration * item.speed:.2f} s de material")
        if getattr(item, "speed", 1.0) == 0:
            partes.append("cuadro congelado")
        self._info.setText("  ·  ".join(partes))

    def _push(self) -> None:
        if self._item is None or self._loading:
            return

        item = self._item
        item.fade_in = self._fade_in.value() / 10.0
        item.fade_out = self._fade_out.value() / 10.0
        if hasattr(item, "gain"):
            item.gain = self._gain.value() / 100.0

        self._describe()
        self.changed.emit()

    def _commit_heavy(self) -> None:
        """Velocidad y transición, al soltar el deslizador."""
        if self._item is None or not hasattr(self._item, "speed"):
            return

        velocidad = self._speed.value() / 100.0
        if abs(velocidad - self._item.speed) > 1e-6:
            self._item.retime(velocidad)
            self.committed.emit("Velocidad")

        cruce = self._dissolve.value() / 10.0
        if abs(cruce - self._item.dissolve) > 1e-6:
            self.committed.emit(f"__dissolve__{cruce}")

        self._describe()


class TransformPanel(QDockWidget):
    """Posición, tamaño, giro y opacidad, con animación por keyframes.

    La capacidad es la de After Effects; la interfaz, no. Cada propiedad
    tiene su deslizador y un rombo al lado: apagado significa valor fijo,
    encendido significa que hay keyframe justo donde está el playhead. Se
    anima poniendo un rombo, moviendo el playhead y moviendo el deslizador.
    No hay gráfica de curvas que aprender.
    """

    changed = Signal()
    committed = Signal(str)

    ETIQUETAS = {
        "x": "Horizontal", "y": "Vertical", "scale": "Tamaño",
        "rotation": "Giro", "opacity": "Opacidad",
    }
    ESCALAS = {"x": 100.0, "y": 100.0, "scale": 100.0, "rotation": 1.0, "opacity": 100.0}

    def __init__(self) -> None:
        super().__init__("Transformar")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._clip = None
        self._local = 0.0
        self._loading = False

        self._name = QLabel("Nada seleccionado")
        self._name.setWordWrap(True)
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        self._rows: dict[str, SliderRow] = {}
        self._keys: dict[str, QPushButton] = {}
        filas = []

        for prop in PROPS:
            fila = SliderRow(self.ETIQUETAS[prop], *RANGES[prop])
            fila.changed.connect(lambda _=0, p=prop: self._push(p))
            self._rows[prop] = fila

            rombo = QPushButton("◆")
            rombo.setCheckable(True)
            rombo.setFixedWidth(26)
            rombo.setFocusPolicy(Qt.NoFocus)
            rombo.setToolTip("Poner o quitar keyframe aquí")
            rombo.setStyleSheet(
                "QPushButton { background:#24282d; border:1px solid #363b42;"
                " border-radius:3px; color:#5d636b; padding:2px; }"
                "QPushButton:checked { color:#e8c15a; border-color:#6a5c34; }")
            rombo.clicked.connect(lambda _=False, p=prop: self._toggle_key(p))
            self._keys[prop] = rombo

            linea = QHBoxLayout()
            linea.setContentsMargins(0, 0, 0, 0)
            linea.setSpacing(5)
            linea.addWidget(fila, 1)
            linea.addWidget(rombo)
            filas.append(linea)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color:#6f757e; font-size:10px;")

        centrar = QPushButton("Restablecer")
        centrar.clicked.connect(self._reset)
        limpiar = QPushButton("Quitar animación")
        limpiar.clicked.connect(self._clear_keys)

        botones = QHBoxLayout()
        botones.setSpacing(6)
        botones.addWidget(centrar)
        botones.addWidget(limpiar)

        self.setWidget(column(
            self._name,
            section("Transformación"), *filas,
            self._info, botones,
            None,
        ))
        self.set_target(None, 0.0)

    # --- estado -----------------------------------------------------------

    def set_target(self, clip, local: float) -> None:
        self._clip = clip
        self._local = local
        self._loading = True

        tiene = clip is not None and hasattr(clip, "transform")
        self._name.setText(f"Clip: {clip.name}" if tiene else "Nada seleccionado")

        for prop in PROPS:
            self._rows[prop].setEnabled(tiene)
            self._keys[prop].setEnabled(tiene)
            if not tiene:
                continue

            valor = clip.transform.at(prop, local)
            self._rows[prop].set_value(int(round(valor * self.ESCALAS[prop])))
            self._keys[prop].blockSignals(True)
            self._keys[prop].setChecked(
                clip.transform.key_near(prop, local) is not None)
            self._keys[prop].blockSignals(False)

        self._describe()
        self._loading = False

    def _describe(self) -> None:
        if self._clip is None or not hasattr(self._clip, "transform"):
            self._info.setText("")
            return

        animadas = [self.ETIQUETAS[p] for p in PROPS if self._clip.transform.animated(p)]
        self._info.setText(
            f"Animando: {', '.join(animadas)}" if animadas
            else "Sin animación. Prende un rombo para empezar.")

    # --- edición ----------------------------------------------------------

    def _push(self, prop: str) -> None:
        if self._clip is None or self._loading:
            return

        transform = self._clip.transform
        valor = self._rows[prop].value() / self.ESCALAS[prop]

        if transform.animated(prop):
            # Con la propiedad animada, mover el deslizador escribe el
            # keyframe de aquí: es lo que uno espera y evita que el cambio
            # se pierda al mover el playhead.
            transform.set_key(prop, self._local, valor)
            self._keys[prop].blockSignals(True)
            self._keys[prop].setChecked(True)
            self._keys[prop].blockSignals(False)
        else:
            setattr(transform, prop, valor)

        self.changed.emit()

    def _toggle_key(self, prop: str) -> None:
        if self._clip is None:
            return

        transform = self._clip.transform
        if transform.key_near(prop, self._local) is not None:
            transform.remove_key(prop, self._local)
        else:
            transform.set_key(prop, self._local,
                              self._rows[prop].value() / self.ESCALAS[prop])

        self.set_target(self._clip, self._local)
        self.committed.emit("Keyframe")

    def _reset(self) -> None:
        if self._clip is None:
            return
        self._clip.transform.reset()
        self.set_target(self._clip, self._local)
        self.committed.emit("Restablecer transformación")

    def _clear_keys(self) -> None:
        if self._clip is None:
            return
        self._clip.transform.clear_keys()
        self.set_target(self._clip, self._local)
        self.committed.emit("Quitar animación")
