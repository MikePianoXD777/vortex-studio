"""El panel de propiedades: una sola ventana con pestañas.

Varias ventanas acopladas apiladas —que es como estaba— dejan la mitad de
la pantalla en controles que casi nunca se tocan a la vez, y es justo lo que
hace ver pesado a After Effects. Aquí las páginas viven en un panel con
pestañas: se ve solo la del trabajo de este momento, y la pestaña se cambia
sola según lo que selecciones.

Lo que se usa a diario va a la vista; lo que se usa de vez en cuando —la
curva de color, por ejemplo— va en un grupo que arranca cerrado. Es la
misma idea aplicada adentro de cada página.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QColorDialog,
    QComboBox,
    QFontComboBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
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
    AUDIO_MODES,
    BLENDS,
    CURVE_LOOKS,
    FIT_MODES,
    SPEED_MAX,
    SPEED_MIN,
    TRANSITIONS,
    IN_ANIMS,
    OUT_ANIMS,
    PROPS,
    RANGES,
    SHAPES,
    ColorAdjust,
    ImageOverlay,
    Mask,
    Title,
)
from vortex_studio.model.animation import DEFAULT_TIME
from vortex_studio.model.color import (
    BRIGHTNESS,
    CHANNELS,
    CONTRAST,
    CURVE_POINT,
    EXPOSURE,
    GAIN,
    GAMMA,
    GAMMA_CH,
    LIFT,
    LOOKS,
    LUT_INTENSITY,
    SATURATION,
    TEMPERATURE,
    TINT,
    VIGNETTE,
)
from vortex_studio.model import timeremap
from vortex_studio.model.mask import NONE as MASK_NONE
from vortex_studio.model.project import SAMPLE_NEAREST, SAMPLINGS
from vortex_studio.model.transform import CORNERS, TILT
from vortex_studio.ui.widgets import (
    Collapsible,
    CurveView,
    SliderRow,
    column,
    section,
)

PANEL_STYLE = """
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


class Page(QWidget):
    """Base de las páginas del panel de propiedades.

    Antes cada una era su propia ventana acoplable y quedaban cinco apiladas
    a la derecha, todas abiertas a la vez. Con el contenido separado de la
    ventana, las cinco caben en un solo panel con pestañas y solo se ve la
    que importa.
    """

    TITULO = ""

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def _set_content(self, widget: QWidget) -> None:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setWidget(widget)
        self._layout.addWidget(area)


class ColorPanel(Page):
    TITULO = "Color"

    """Corrección de color del clip que está bajo el playhead."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()

        self._adjust: ColorAdjust | None = None

        self._target = QLabel("Ningún clip bajo el playhead")
        self._target.setWordWrap(True)
        self._target.setStyleSheet("color:#7d838c; font-size:10px;")

        self._brightness = SliderRow("Brillo", *BRIGHTNESS)
        self._contrast = SliderRow("Contraste", *CONTRAST)
        self._saturation = SliderRow("Saturación", *SATURATION)
        self._gamma = SliderRow("Gamma", *GAMMA)
        self._temperature = SliderRow("Temperatura", *TEMPERATURE)
        self._vignette = SliderRow("Viñeta", *VIGNETTE)
        self._exposure = SliderRow("Exposición", *EXPOSURE)
        self._tint = SliderRow("Tinte", *TINT)

        # Lift / gamma / gain: las ruedas de DaVinci como deslizadores. Un
        # grupo cerrado: son de corrección fina, no de todos los días.
        rangos = {"lift": LIFT, "gamma": GAMMA_CH, "gain": GAIN}
        nombres = {"r": "rojo", "g": "verde", "b": "azul"}
        self._lgg = {f"{g}_{c}": SliderRow(f"{g.capitalize()} {nombres[c]}", *rangos[g])
                     for g in ("lift", "gamma", "gain") for c in CHANNELS}

        self._lut_name = QLabel("Sin LUT")
        self._lut_name.setWordWrap(True)
        self._lut_name.setStyleSheet("color:#9aa1aa; font-size:11px;")
        self._lut_load = QPushButton("Cargar .cube…")
        self._lut_load.clicked.connect(self._pick_lut)
        self._lut_clear = QPushButton("Quitar LUT")
        self._lut_clear.clicked.connect(lambda: self.set_lut(""))
        self._lut_intensity = SliderRow("Intensidad", *LUT_INTENSITY)

        self._look = QComboBox()
        self._look.addItems(LOOKS.keys())
        self._look.setToolTip("Combinaciones listas; luego puedes seguir ajustando")
        self._look.currentTextChanged.connect(self._apply_look)

        # La curva: cinco deslizadores y la gráfica que dice qué están
        # haciendo. Sin gráfica, "sombras" y "luces" son dos números que no
        # le dicen nada a nadie; con ella no hace falta arrastrar puntos.
        self._graph = CurveView()
        self._curve_rows = {
            "blacks": SliderRow("Negros", *CURVE_POINT),
            "shadows": SliderRow("Sombras", *CURVE_POINT),
            "mids": SliderRow("Medios", *CURVE_POINT),
            "highs": SliderRow("Luces", *CURVE_POINT),
            "whites": SliderRow("Blancos", *CURVE_POINT),
        }
        self._curve_look = QComboBox()
        self._curve_look.addItems(CURVE_LOOKS.keys())
        self._curve_look.setToolTip("Curvas listas; se pueden seguir ajustando")
        self._curve_look.currentTextChanged.connect(self._apply_curve_look)

        for row in self._rows():
            row.changed.connect(self._push)

        reset = QPushButton("Restablecer todo")
        reset.clicked.connect(self._reset)

        self._curve_group = Collapsible(
            "Curva", self._graph, self._curve_look,
            *self._curve_rows.values())
        self._lgg_group = Collapsible("Lift · Gamma · Gain", *self._lgg.values())
        botones_lut = QHBoxLayout()
        botones_lut.addWidget(self._lut_load)
        botones_lut.addWidget(self._lut_clear)
        self._lut_group = Collapsible("LUT", self._lut_name, botones_lut, self._lut_intensity)

        self._set_content(column(
            self._target,
            section("Look"), self._look,
            section("Ajustes"),
            self._exposure, self._brightness, self._contrast, self._saturation,
            self._gamma, self._temperature, self._tint,
            self._curve_group,
            self._lgg_group,
            self._lut_group,
            section("Viñeta"), self._vignette,
            reset,
            None,
        ))
        self.set_target(None, "")

    def _rows(self) -> list[SliderRow]:
        return [self._brightness, self._contrast, self._saturation,
                self._gamma, self._temperature, self._vignette,
                *self._curve_rows.values(), self._exposure, self._tint,
                *self._lgg.values(), self._lut_intensity]

    def set_target(self, adjust: ColorAdjust | None, name: str) -> None:
        """Apunta el panel a un clip. Sin clip, los controles se apagan."""
        self._adjust = adjust
        self._target.setText(f"Clip: {name}" if adjust else "Ningún clip bajo el playhead")

        for row in self._rows():
            row.setEnabled(adjust is not None)
        self._look.setEnabled(adjust is not None)

        self._curve_look.setEnabled(adjust is not None)
        self._lut_load.setEnabled(adjust is not None)
        self._lut_clear.setEnabled(adjust is not None and bool(adjust and adjust.lut))

        if adjust is not None:
            self._brightness.set_value(adjust.brightness)
            self._contrast.set_value(adjust.contrast)
            self._saturation.set_value(adjust.saturation)
            self._gamma.set_value(adjust.gamma)
            self._temperature.set_value(adjust.temperature)
            self._vignette.set_value(adjust.vignette)
            for prop, row in self._curve_rows.items():
                row.set_value(getattr(adjust.curves, prop))
            self._exposure.set_value(int(round(adjust.exposure)))
            self._tint.set_value(int(round(adjust.tint)))
            for campo, row in self._lgg.items():
                row.set_value(int(round(getattr(adjust, campo))))
            self._lut_intensity.set_value(int(round(adjust.lut_intensity)))
            self._lut_name.setText(Path(adjust.lut).name if adjust.lut else "Sin LUT")
            if not adjust.lgg_is_neutral:
                self._lgg_group.abrir()
            if adjust.lut:
                self._lut_group.abrir()
            # El grupo se abre solo si el clip ya traía curva: así un look
            # de cine no deja escondido lo que le está haciendo a la imagen.
            if not adjust.curves.is_neutral:
                self._curve_group.abrir()

        self._graph.set_curves(adjust.curves if adjust else None)

    def _push(self) -> None:
        if self._adjust is None:
            return
        self._adjust.brightness = self._brightness.value()
        self._adjust.contrast = self._contrast.value()
        self._adjust.saturation = self._saturation.value()
        self._adjust.gamma = self._gamma.value()
        self._adjust.temperature = self._temperature.value()
        self._adjust.vignette = self._vignette.value()
        for prop, row in self._curve_rows.items():
            setattr(self._adjust.curves, prop, row.value())
        self._adjust.exposure = self._exposure.value()
        self._adjust.tint = self._tint.value()
        for campo, row in self._lgg.items():
            setattr(self._adjust, campo, row.value())
        self._adjust.lut_intensity = self._lut_intensity.value()
        self._graph.set_curves(self._adjust.curves)
        self.changed.emit()

    def _pick_lut(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        ruta, _ = QFileDialog.getOpenFileName(self, "Cargar LUT", "", "LUT (*.cube)")
        if ruta:
            self.set_lut(ruta)

    def set_lut(self, ruta: str) -> str:
        """Pone o quita el LUT. Devuelve el error, o cadena vacía si quedó."""
        if self._adjust is None:
            return "sin clip"
        if ruta:
            from vortex_studio.model.lut import read_cube
            try:
                read_cube(ruta)
            except (OSError, ValueError) as error:
                self._lut_name.setText(f"No se pudo leer: {error}")
                return str(error)
        self._adjust.lut = str(ruta)
        self._lut_name.setText(Path(ruta).name if ruta else "Sin LUT")
        self._lut_clear.setEnabled(bool(ruta))
        if ruta:
            self._lut_group.abrir()
        self.changed.emit()
        return ""

    def _apply_curve_look(self, nombre: str) -> None:
        if self._adjust is None or nombre not in CURVE_LOOKS:
            return
        self._adjust.curves.apply(CURVE_LOOKS[nombre])
        for prop, row in self._curve_rows.items():
            row.set_value(getattr(self._adjust.curves, prop))
        self._graph.set_curves(self._adjust.curves)
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
        for combo, neutro in ((self._look, "Ninguno"),
                              (self._curve_look, "Ninguna")):
            combo.blockSignals(True)
            combo.setCurrentText(neutro)
            combo.blockSignals(False)
        self.set_target(self._adjust, self._target.text().removeprefix("Clip: "))
        self.changed.emit()


class TextPanel(Page):
    TITULO = "Texto"

    """Lista de textos y edición del que esté seleccionado."""

    changed = Signal()
    add_requested = Signal()
    delete_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()

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

        self._font = QFontComboBox()
        self._font.setToolTip("Tipografía del texto")
        self._font.currentFontChanged.connect(self._font_changed)

        # Contorno y sombra: lo que hace legible un subtítulo sobre cualquier
        # fondo. Van en un grupo cerrado; lo de todos los días es el texto.
        self._outline_color = QPushButton("Color del contorno")
        self._outline_color.clicked.connect(lambda: self._pick("outline_color", "Color del contorno"))
        self._outline_width = SliderRow("Grosor", 1, 20, 6)      # % del alto de la letra
        self._shadow = QCheckBox("Sombra")
        self._shadow_color = QPushButton("Color de la sombra")
        self._shadow_color.clicked.connect(lambda: self._pick("shadow_color", "Color de la sombra"))
        self._shadow_distance = SliderRow("Distancia", 0, 30, 6)
        self._shadow_blur = SliderRow("Desenfoque", 0, 30, 0)
        self._shadow_opacity = SliderRow("Opacidad", 0, 100, 75)
        for row in (self._outline_width, self._shadow_distance, self._shadow_blur,
                    self._shadow_opacity):
            row.changed.connect(self._push)
        self._shadow.toggled.connect(self._push)

        self._duration = QDoubleSpinBox()
        self._duration.setRange(0.2, 600.0)
        self._duration.setSingleStep(0.5)
        self._duration.setValue(3.0)
        self._duration.setSuffix(" s")
        self._duration.valueChanged.connect(self._push)

        # "Duración del texto" y no "Duración": en el mismo panel hay otra
        # duración, la de la animación, y dos campos con el mismo nombre a
        # la vista no se distinguen.
        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("Duración del texto"))
        duration_row.addWidget(self._duration, 1)

        self._bold = QCheckBox("Negrita")
        self._bold.setChecked(True)
        self._italic = QCheckBox("Cursiva")
        self._outline = QCheckBox("Contorno")
        self._outline.setChecked(True)
        self._background = QCheckBox("Caja de subtítulo")
        self._style_group = Collapsible(
            "Contorno y sombra",
            self._outline_color, self._outline_width,
            self._shadow, self._shadow_color, self._shadow_distance,
            self._shadow_blur, self._shadow_opacity)
        for box in (self._bold, self._italic, self._outline, self._background):
            box.toggled.connect(self._push)

        styles = QHBoxLayout()
        styles.addWidget(self._bold)
        styles.addWidget(self._italic)
        styles.addStretch(1)

        # Animación. Dos listas y un tiempo: es todo lo que hace falta para
        # el efecto que en After Effects son cuatro keyframes por propiedad.
        self._anim_in = QComboBox()
        self._anim_in.addItems(IN_ANIMS)
        self._anim_in.setToolTip("Cómo entra el texto")
        self._anim_out = QComboBox()
        self._anim_out.addItems(OUT_ANIMS)
        self._anim_out.setToolTip("Cómo sale el texto")
        for combo in (self._anim_in, self._anim_out):
            combo.currentTextChanged.connect(self._push)

        self._anim_time = QDoubleSpinBox()
        self._anim_time.setRange(0.05, 5.0)
        self._anim_time.setSingleStep(0.05)
        self._anim_time.setDecimals(2)
        self._anim_time.setValue(DEFAULT_TIME)
        self._anim_time.setSuffix(" s")
        self._anim_time.setToolTip("Lo que tarda la entrada, y lo que tarda la salida")
        self._anim_time.valueChanged.connect(self._push)

        anim_in_row = self._labelled("Entrada", self._anim_in)
        anim_out_row = self._labelled("Salida", self._anim_out)
        anim_time_row = self._labelled("Duración", self._anim_time)

        self._set_content(column(
            self._list,
            buttons,
            section("Contenido"),
            self._text,
            section("Animación"),
            anim_in_row, anim_out_row, anim_time_row,
            section("Posición"),
            self._anchor, self._align, self._size,
            section("Estilo"),
            self._font, self._color_button, styles, self._outline, self._background,
            self._style_group,
            section("Tiempo"),
            duration_row,
            None,
        ))
        self.set_titles([], None)

    @staticmethod
    def _labelled(texto: str, widget: QWidget) -> QHBoxLayout:
        etiqueta = QLabel(texto)
        etiqueta.setStyleSheet("color:#9aa1aa; font-size:11px;")
        etiqueta.setMinimumWidth(74)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(etiqueta)
        fila.addWidget(widget, 1)
        return fila

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
                       self._italic, self._outline, self._background,
                       self._anim_in, self._anim_out, self._anim_time,
                       self._delete, self._font, self._outline_color,
                       self._outline_width, self._shadow, self._shadow_color,
                       self._shadow_distance, self._shadow_blur, self._shadow_opacity):
            widget.setEnabled(enabled)

        if title is not None:
            self._anim_in.setCurrentText(
                title.anim_in if title.anim_in in IN_ANIMS else "Ninguna")
            self._anim_out.setCurrentText(
                title.anim_out if title.anim_out in OUT_ANIMS else "Ninguna")
            self._anim_time.setValue(max(0.05, min(5.0, title.anim_time)))
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
            self._font.setCurrentFont(QFont(title.font) if title.font
                                      else QApplication.font())
            self._outline_width.set_value(max(1, round(title.outline_width * 100)))
            self._shadow.setChecked(title.shadow)
            self._shadow_distance.set_value(round(title.shadow_distance * 100))
            self._shadow_blur.set_value(round(title.shadow_blur * 100))
            self._shadow_opacity.set_value(round(title.shadow_opacity * 100))
            self._paint(self._outline_color, title.outline_color)
            self._paint(self._shadow_color, title.shadow_color)
            if title.shadow:
                self._style_group.abrir()

        self._loading = False

    @staticmethod
    def _anchor_name(title: Title) -> str:
        """Qué preset corresponde a la posición actual, si es que alguno."""
        for name, (x, y) in ANCHORS.items():
            if abs(x - title.x) < 1e-6 and abs(y - title.y) < 1e-6:
                return name
        return "Centro"

    def _paint_color_button(self, color: str) -> None:
        self._paint(self._color_button, color)

    @staticmethod
    def _paint(button: QPushButton, color: str) -> None:
        contrast = "#101113" if QColor(color).lightness() > 140 else "#f0f3f6"
        button.setStyleSheet(
            f"QPushButton {{ background:{color}; color:{contrast};"
            f" border:1px solid #3a3f46; border-radius:4px; padding:5px 10px; }}"
        )

    def _font_changed(self, font: QFont) -> None:
        if self._title is None or self._loading:
            return
        self._title.font = font.family()
        self.changed.emit()

    def _pick(self, campo: str, titulo: str) -> None:
        if self._title is None:
            return
        color = QColorDialog.getColor(QColor(getattr(self._title, campo)), self, titulo)
        if color.isValid():
            self.set_style_color(campo, color.name())

    def set_style_color(self, campo: str, color: str) -> None:
        """Pone un color de contorno o de sombra. Separado del diálogo para
        poder probarlo sin abrir una ventana modal."""
        if self._title is None:
            return
        setattr(self._title, campo, color)
        self._paint(self._outline_color if campo == "outline_color" else self._shadow_color,
                    color)
        self.changed.emit()

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
        self._title.anim_in = self._anim_in.currentText()
        self._title.anim_out = self._anim_out.currentText()
        self._title.anim_time = self._anim_time.value()
        self._title.outline_width = self._outline_width.value() / 100.0
        self._title.shadow = self._shadow.isChecked()
        self._title.shadow_distance = self._shadow_distance.value() / 100.0
        self._title.shadow_blur = self._shadow_blur.value() / 100.0
        self._title.shadow_opacity = self._shadow_opacity.value() / 100.0

        self.changed.emit()


class ImagePanel(Page):
    TITULO = "Imagen"

    """Acomoda la imagen seleccionada sobre el video."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()

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

        self._set_content(column(
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


class ClipPanel(Page):
    TITULO = "Clip"

    """Todo lo que se le puede hacer al clip seleccionado, con deslizadores.

    Lo mismo que hay en el menú Clip, pero se puede tantear moviendo: para
    ajustar un fundido o una transición uno quiere ver el resultado mientras
    lo mueve, no elegir un número de una lista.
    """

    changed = Signal()
    committed = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self._item = None
        self._loading = False

        self._name = QLabel("Nada seleccionado")
        self._name.setWordWrap(True)
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        self._fade_in = SliderRow("Entrada", 0, 300, 0)      # décimas de segundo
        self._fade_out = SliderRow("Salida", 0, 300, 0)
        self._dissolve = SliderRow("Transición", 0, 300, 0)
        self._speed = SliderRow("Velocidad", int(SPEED_MIN * 100), int(SPEED_MAX * 100),
                                100)   # porcentaje
        self._gain = SliderRow("Volumen", 0, 400, 100)

        for row in (self._fade_in, self._fade_out, self._dissolve,
                    self._speed, self._gain):
            row.changed.connect(self._push)
        for row in (self._speed, self._dissolve):
            # Velocidad y transición cambian la duración o piden decodificar
            # de nuevo: se aplican al soltar, no en cada pixel del arrastre.
            row._slider.sliderReleased.connect(self._commit_heavy)

        self._transition = QComboBox()
        self._transition.addItems(TRANSITIONS)
        self._transition.setToolTip("Cruzada mezcla los dos clips; a negro o a blanco "
                                    "pasan por ese color")
        self._transition.currentTextChanged.connect(self._transition_changed)

        self._audio_mode = QComboBox()
        self._audio_mode.addItems(AUDIO_MODES)
        self._audio_mode.setToolTip("Qué pasa con el sonido cuando el clip no va a 100 %")
        self._audio_mode.currentTextChanged.connect(self._audio_mode_changed)

        self._interp = QComboBox()
        self._interp.addItems(SAMPLINGS)
        self._interp.setToolTip("En cámara lenta: repetir el cuadro, mezclar los dos vecinos "
                                "o inventar el de en medio siguiendo el movimiento (lento: "
                                "renderiza la zona con Enter)")
        self._interp.currentTextChanged.connect(self._interp_changed)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color:#6f757e; font-size:10px;")

        self._set_content(column(
            self._name,
            section("Fundidos (segundos)"), self._fade_in, self._fade_out,
            section("Transición con el anterior"), self._transition, self._dissolve,
            section("Tiempo"), self._speed, self._audio_mode, self._interp,
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
        self._transition.setEnabled(es_clip and not es_audio)
        self._speed.setEnabled(es_clip)
        self._audio_mode.setEnabled(es_clip)
        self._interp.setEnabled(es_clip and not es_audio)
        self._gain.setEnabled(es_clip and es_audio)

        if tiene:
            self._fade_in.set_value(int(round(item.fade_in * 10)))
            self._fade_out.set_value(int(round(item.fade_out * 10)))
            if es_clip:
                self._dissolve.set_value(int(round(item.dissolve * 10)))
                self._speed.set_value(int(round(item.speed * 100)))
                self._gain.set_value(int(round(item.gain * 100)))
                self._transition.setCurrentText(item.transition if item.transition
                                                in TRANSITIONS else TRANSITIONS[0])
                self._audio_mode.setCurrentText(item.audio_mode if item.audio_mode
                                                in AUDIO_MODES else AUDIO_MODES[0])
                self._interp.setCurrentText(getattr(item, "interpolation", SAMPLE_NEAREST))
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
        if timeremap.is_remapped(item):
            partes.append("con remapeo de tiempo (Clip → Remapeo de tiempo)")
        self._info.setText("  ·  ".join(partes))

    def _interp_changed(self, nombre: str) -> None:
        if self._loading or self._item is None or not hasattr(self._item, "interpolation"):
            return
        self._item.interpolation = nombre
        self.committed.emit(f"Cuadros intermedios: {nombre.lower()}")

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

    def _transition_changed(self, nombre: str) -> None:
        if self._loading or self._item is None or not hasattr(self._item, "transition"):
            return
        self._item.transition = nombre
        self.committed.emit(f"Transición {nombre.lower()}")

    def _audio_mode_changed(self, nombre: str) -> None:
        if self._loading or self._item is None or not hasattr(self._item, "audio_mode"):
            return
        self._item.audio_mode = nombre
        self.committed.emit(f"Audio: {nombre.lower()}")

    def _commit_heavy(self) -> None:
        """Velocidad y transición, al soltar el deslizador."""
        if self._item is None or not hasattr(self._item, "speed"):
            return

        velocidad = self._speed.value() / 100.0
        if abs(velocidad - self._item.speed) > 1e-6:
            # La velocidad pasa por la ventana y no se aplica aquí: el audio
            # enlazado tiene que cambiar junto con el video.
            self.committed.emit(f"__speed__{velocidad}")

        cruce = self._dissolve.value() / 10.0
        if abs(cruce - self._item.dissolve) > 1e-6:
            self.committed.emit(f"__dissolve__{cruce}")

        self._describe()


ANCHOR_PRESETS = {
    "Centro": (0.0, 0.0),
    "Arriba izquierda": (-0.5, -0.5),
    "Arriba": (0.0, -0.5),
    "Arriba derecha": (0.5, -0.5),
    "Izquierda": (-0.5, 0.0),
    "Derecha": (0.5, 0.0),
    "Abajo izquierda": (-0.5, 0.5),
    "Abajo": (0.0, 0.5),
    "Abajo derecha": (0.5, 0.5),
}


class TransformPanel(Page):
    TITULO = "Transformar"

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
        "tilt_x": "Inclinar atrás", "tilt_y": "Girar de lado",
        "pin_tl_x": "Sup. izq. X", "pin_tl_y": "Sup. izq. Y",
        "pin_tr_x": "Sup. der. X", "pin_tr_y": "Sup. der. Y",
        "pin_br_x": "Inf. der. X", "pin_br_y": "Inf. der. Y",
        "pin_bl_x": "Inf. izq. X", "pin_bl_y": "Inf. izq. Y",
    }
    ESCALAS = {"x": 100.0, "y": 100.0, "scale": 100.0, "rotation": 1.0, "opacity": 100.0,
               "tilt_x": 1.0, "tilt_y": 1.0, **{p: 100.0 for p in CORNERS}}

    def __init__(self) -> None:
        super().__init__()

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

        # Encuadre: cómo cae el material en el cuadro, cuánto se recorta y
        # desde dónde crece y gira. Cerrado por omisión: casi siempre el
        # material ya tiene la proporción de la secuencia.
        self._fit = QComboBox()
        self._fit.addItems(FIT_MODES)
        self._fit.setToolTip("Ajustar: entero con franjas · Rellenar: llena y recorta "
                             "lo que sobra (para pasar de horizontal a vertical) · "
                             "Estirar: llena deformando")
        self._fit.currentTextChanged.connect(self._fit_changed)

        self._crop = {
            "crop_left": SliderRow("Izquierda", 0, 49, 0),
            "crop_right": SliderRow("Derecha", 0, 49, 0),
            "crop_top": SliderRow("Arriba", 0, 49, 0),
            "crop_bottom": SliderRow("Abajo", 0, 49, 0),
        }
        self._anchor = {
            "anchor_x": SliderRow("Ancla X", -50, 50, 0),
            "anchor_y": SliderRow("Ancla Y", -50, 50, 0),
        }
        for campo, fila in (*self._crop.items(), *self._anchor.items()):
            fila.changed.connect(lambda _=0, c=campo: self._push_framing(c))

        self._anchor_preset = QComboBox()
        self._anchor_preset.addItems(list(ANCHOR_PRESETS))
        self._anchor_preset.setToolTip("Desde dónde crece y gira la imagen")
        self._anchor_preset.activated.connect(self._apply_anchor_preset)

        self._framing_group = Collapsible(
            "Encuadre y recorte",
            self._labelled("Encuadre", self._fit),
            *self._crop.values(),
            self._labelled("Ancla", self._anchor_preset),
            *self._anchor.values())

        # Perspectiva y corner pin: cerrado por omisión, como el encuadre.
        # Sin rombos; se animan desde el editor de keyframes (Shift+K).
        perspectiva = []
        for prop in TILT + CORNERS:
            fila = SliderRow(self.ETIQUETAS[prop], *RANGES[prop])
            fila.changed.connect(lambda _=0, p=prop: self._push(p))
            self._rows[prop] = fila
            perspectiva.append(fila)
        quitar_perspectiva = QPushButton("Quitar perspectiva")
        quitar_perspectiva.clicked.connect(self._reset_perspective)
        self._perspective_group = Collapsible("3D y esquinas", *perspectiva, quitar_perspectiva)

        centrar = QPushButton("Restablecer")
        centrar.clicked.connect(self._reset)
        limpiar = QPushButton("Quitar animación")
        limpiar.clicked.connect(self._clear_keys)

        botones = QHBoxLayout()
        botones.setSpacing(6)
        botones.addWidget(centrar)
        botones.addWidget(limpiar)

        self._set_content(column(
            self._name,
            section("Transformación"), *filas,
            self._framing_group,
            self._perspective_group,
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

        for widget in (self._fit, self._anchor_preset, *self._crop.values(),
                       *self._anchor.values()):
            widget.setEnabled(tiene)
        if tiene:
            tr = clip.transform
            self._fit.setCurrentText(tr.fit if tr.fit in FIT_MODES else FIT_MODES[0])
            for campo, fila in self._crop.items():
                fila.set_value(round(getattr(tr, campo) * 100))
            for campo, fila in self._anchor.items():
                fila.set_value(round(getattr(tr, campo) * 100))
            if tr.has_crop or tr.fit != FIT_MODES[0] or tr.anchor_x or tr.anchor_y:
                self._framing_group.abrir()
            if tr.has_perspective:
                self._perspective_group.abrir()

        for prop in self._rows:
            self._rows[prop].setEnabled(tiene)
            if prop in self._keys:
                self._keys[prop].setEnabled(tiene)
            if not tiene:
                continue

            valor = clip.transform.at(prop, local)
            self._rows[prop].set_value(int(round(valor * self.ESCALAS[prop])))
            if prop in self._keys:
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

        animadas = [self.ETIQUETAS[p] for p in self._rows if self._clip.transform.animated(p)]
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
            if prop in self._keys:
                self._keys[prop].blockSignals(True)
                self._keys[prop].setChecked(True)
                self._keys[prop].blockSignals(False)
        else:
            setattr(transform, prop, valor)

        self.changed.emit()

    def _reset_perspective(self) -> None:
        if self._clip is None or not hasattr(self._clip, "transform"):
            return
        self._clip.transform.reset_perspective()
        self.set_target(self._clip, self._local)
        self.committed.emit("Quitar perspectiva")

    @staticmethod
    def _labelled(texto: str, widget: QWidget) -> QHBoxLayout:
        return TextPanel._labelled(texto, widget)

    def _fit_changed(self, nombre: str) -> None:
        if self._loading or self._clip is None or not hasattr(self._clip, "transform"):
            return
        self._clip.transform.fit = nombre
        self.committed.emit(f"Encuadre: {nombre.lower()}")

    def _push_framing(self, campo: str) -> None:
        if self._loading or self._clip is None or not hasattr(self._clip, "transform"):
            return
        filas = {**self._crop, **self._anchor}
        setattr(self._clip.transform, campo, filas[campo].value() / 100.0)
        self.changed.emit()

    def _apply_anchor_preset(self, indice: int) -> None:
        if self._clip is None or not hasattr(self._clip, "transform"):
            return
        ax, ay = ANCHOR_PRESETS[self._anchor_preset.itemText(indice)]
        self._clip.transform.anchor_x, self._clip.transform.anchor_y = ax, ay
        self.set_target(self._clip, self._local)
        self.committed.emit("Punto de anclaje")

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


class MaskPanel(Page):
    TITULO = "Máscara"

    """Máscara y modo de fusión del clip o la imagen seleccionada.

    Las dos cosas van juntas porque se usan juntas: la máscara dice *qué
    parte* de la capa se ve y la fusión dice *cómo* se mezcla con lo de
    abajo. En CapCut viven en el mismo lugar por la misma razón.

    La máscara se mide sobre el cuadro de salida, como en CapCut, no sobre
    la capa como en After Effects: uno la coloca mirando el preview, y si
    el clip se anima la máscara se queda donde la pusiste.
    """

    changed = Signal()
    committed = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self._item = None
        self._loading = False

        self._target = QLabel("Nada seleccionado")
        self._target.setWordWrap(True)
        self._target.setStyleSheet("color:#7d838c; font-size:10px;")

        self._blend = QComboBox()
        self._blend.addItems(BLENDS)
        self._blend.setToolTip("Cómo se mezcla esta capa con la pista de abajo")
        self._blend.currentTextChanged.connect(self._push)

        self._shape = QComboBox()
        self._shape.addItems(SHAPES)
        self._shape.setToolTip("La forma de lo que se deja ver")
        self._shape.currentTextChanged.connect(self._shape_changed)

        self._rows = {
            "x": SliderRow("Posición X", 0, 100, 50),
            "y": SliderRow("Posición Y", 0, 100, 50),
            "width": SliderRow("Ancho", 1, 200, 60),
            "height": SliderRow("Alto", 1, 200, 60),
            "rotation": SliderRow("Giro", -180, 180, 0),
            "feather": SliderRow("Suavizado", 0, 50, 3),
        }
        for row in self._rows.values():
            row.changed.connect(self._push)

        self._invert = QCheckBox("Invertir: tapar lo de dentro")
        self._invert.toggled.connect(self._push)

        self._clear = QPushButton("Quitar máscara")
        self._clear.clicked.connect(self._reset)

        self._hint = QLabel(
            "Un corte recto: la posición dice por dónde pasa y el giro "
            "hacia dónde apunta.")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#6f757e; font-size:10px;")
        self._hint.setVisible(False)

        self._set_content(column(
            self._target,
            section("Fusión"), self._blend,
            section("Máscara"), self._shape, self._hint,
            *self._rows.values(),
            self._invert,
            self._clear,
            None,
        ))
        self.set_target(None)

    # --- estado -----------------------------------------------------------

    @property
    def target(self):
        """La capa que el panel está editando, o `None` si no aplica."""
        return self._item

    def set_target(self, item) -> None:
        """Apunta el panel a un clip o a una imagen. `None` lo apaga."""
        self._item = item
        self._loading = True

        activo = item is not None and hasattr(item, "mask")
        self._target.setText(
            f"Capa: {item.name}" if activo else "Nada seleccionado")
        for widget in (self._blend, self._shape, self._invert, self._clear):
            widget.setEnabled(activo)

        if activo:
            mask = item.mask
            self._blend.setCurrentText(
                item.blend if item.blend in BLENDS else "Normal")
            self._shape.setCurrentText(
                mask.shape if mask.shape in SHAPES else MASK_NONE)
            self._rows["x"].set_value(round(mask.x * 100))
            self._rows["y"].set_value(round(mask.y * 100))
            self._rows["width"].set_value(round(mask.width * 100))
            self._rows["height"].set_value(round(mask.height * 100))
            self._rows["rotation"].set_value(round(mask.rotation))
            self._rows["feather"].set_value(round(mask.feather * 100))
            self._invert.setChecked(mask.invert)

        self._loading = False
        self._describe()

    def _describe(self) -> None:
        """Apaga los controles que no aplican a la forma escogida.

        Dejarlos encendidos y muertos es peor que apagarlos: uno mueve el
        ancho de una máscara lineal, no pasa nada, y se queda pensando que
        el programa está roto.
        """
        mask = getattr(self._item, "mask", None)
        viva = mask is not None and not mask.is_off

        for nombre, row in self._rows.items():
            aplica = viva
            if nombre in ("width", "height"):
                aplica = viva and mask.uses_size
            row.setEnabled(aplica)

        self._invert.setEnabled(viva)
        self._clear.setEnabled(viva)
        self._hint.setVisible(viva and mask.shape == "Lineal")

    # --- edición ----------------------------------------------------------

    def _push(self) -> None:
        if self._item is None or self._loading:
            return

        self._item.blend = self._blend.currentText()
        mask = self._item.mask
        mask.shape = self._shape.currentText()
        mask.x = self._rows["x"].value() / 100.0
        mask.y = self._rows["y"].value() / 100.0
        mask.width = self._rows["width"].value() / 100.0
        mask.height = self._rows["height"].value() / 100.0
        mask.rotation = float(self._rows["rotation"].value())
        mask.feather = self._rows["feather"].value() / 100.0
        mask.invert = self._invert.isChecked()

        self.changed.emit()

    def _shape_changed(self, nombre: str) -> None:
        """Cambiar de forma reajusta los controles y entra al historial.

        Va por `committed` y no por `changed` porque no es un arrastre: es
        una decisión, y merece su propio paso de deshacer.
        """
        self._push()
        self._describe()
        if not self._loading:
            self.committed.emit(f"Máscara: {nombre.lower()}")

    def _reset(self) -> None:
        if self._item is None:
            return
        self._item.mask.reset()
        self.set_target(self._item)
        self.committed.emit("Quitar máscara")


class AudioPanel(Page):
    TITULO = "Audio"

    """Ecualizador, compresor, normalización y ducking del clip de audio.

    Lo de todos los días va arriba: tres bandas y normalizar. El compresor
    arranca apagado y cerrado. El papel de la pista —voz o música que se
    agacha— está aquí porque se decide mirando el clip, aunque sea de la
    pista.
    """

    changed = Signal()
    committed = Signal(str)
    normalize_requested = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        from vortex_studio.model.audio_fx import LOUDNESS_TARGETS, ROLES

        self._clip = None
        self._track = None
        self._sequence = None
        self._loading = False

        self._name = QLabel("Selecciona un clip de audio")
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        # En décimas de dB, para que el deslizador tenga pasos finos.
        self.low = SliderRow("Graves", -120, 120, 0)
        self.mid = SliderRow("Medios", -120, 120, 0)
        self.high = SliderRow("Agudos", -120, 120, 0)

        self.compressor = QCheckBox("Compresor")
        self.threshold = SliderRow("Umbral dB", -60, 0, -18)
        self.ratio = SliderRow("Relación ×10", 10, 200, 30)
        self.attack = SliderRow("Ataque ms", 1, 200, 10)
        self.release = SliderRow("Soltar ms", 10, 1000, 150)
        self.makeup = SliderRow("Ganancia ×10", 0, 240, 0)
        for row in (self.low, self.mid, self.high, self.threshold, self.ratio,
                    self.attack, self.release, self.makeup):
            row.changed.connect(self._push)
        self.compressor.toggled.connect(self._compressor_toggled)
        self._comp_group = Collapsible("Compresor", self.compressor, self.threshold, self.ratio,
                                       self.attack, self.release, self.makeup)

        self.target = QComboBox()
        for nombre, valor in LOUDNESS_TARGETS.items():
            self.target.addItem(nombre, valor)
        self.normalize = QPushButton("Normalizar")
        self.normalize.setToolTip("Mide la sonoridad y ajusta el volumen para llegar a la meta")
        self.normalize.clicked.connect(
            lambda: self.normalize_requested.emit(float(self.target.currentData())))
        fila = QHBoxLayout()
        fila.addWidget(self.target, 1)
        fila.addWidget(self.normalize)

        self.role = QComboBox()
        self.role.addItems(ROLES)
        self.role.setToolTip("Voz: manda. Música: baja sola cuando suena una pista de voz")
        self.role.currentTextChanged.connect(self._role_changed)
        self.depth = SliderRow("Cuánto baja dB", 0, 30, 12)
        self.depth.changed.connect(self._depth_changed)

        self._set_content(column(
            self._name,
            section("Ecualizador (dB × 10)"), self.low, self.mid, self.high,
            section("Sonoridad"), fila,
            section("Ducking de la pista"), self.role, self.depth,
            self._comp_group,
            None,
        ))
        self.set_target(None, None, None)

    def set_target(self, clip, track, sequence) -> None:
        self._clip, self._track, self._sequence = clip, track, sequence
        self._loading = True
        tiene = clip is not None and hasattr(clip, "audio_fx")
        self._name.setText(f"Clip: {clip.name}" if tiene else "Selecciona un clip de audio")
        for widget in (self.low, self.mid, self.high, self.compressor, self.target,
                       self.normalize, self.role, self.depth):
            widget.setEnabled(tiene)
        if tiene:
            fx = clip.audio_fx
            self.low.set_value(round(fx.low * 10))
            self.mid.set_value(round(fx.mid * 10))
            self.high.set_value(round(fx.high * 10))
            self.compressor.setChecked(fx.compressor)
            self.threshold.set_value(round(fx.threshold))
            self.ratio.set_value(round(fx.ratio * 10))
            self.attack.set_value(round(fx.attack))
            self.release.set_value(round(fx.release))
            self.makeup.set_value(round(fx.makeup * 10))
            if track is not None:
                self.role.setCurrentText(track.role)
            if sequence is not None:
                self.depth.set_value(round(sequence.duck_depth))
            if fx.compressor:
                self._comp_group.abrir()
        self._loading = False
        self._describe()

    def _describe(self) -> None:
        prendido = self._clip is not None and self._clip.audio_fx.compressor
        for row in (self.threshold, self.ratio, self.attack, self.release, self.makeup):
            row.setEnabled(bool(prendido))

    def _push(self, *_):
        if self._loading or self._clip is None:
            return
        fx = self._clip.audio_fx
        fx.low, fx.mid, fx.high = (self.low.value() / 10, self.mid.value() / 10,
                                   self.high.value() / 10)
        fx.threshold = float(self.threshold.value())
        fx.ratio = self.ratio.value() / 10
        fx.attack = float(self.attack.value())
        fx.release = float(self.release.value())
        fx.makeup = self.makeup.value() / 10
        self.changed.emit()

    def _compressor_toggled(self, prendido: bool) -> None:
        if self._loading or self._clip is None:
            return
        self._clip.audio_fx.compressor = prendido
        self._describe()
        self.committed.emit("Compresor" if prendido else "Quitar compresor")

    def _role_changed(self, rol: str) -> None:
        if self._loading or self._track is None:
            return
        self._track.role = rol
        self.committed.emit(f"{self._track.name}: {rol.split(':')[0].lower()}")

    def _depth_changed(self, valor: int) -> None:
        if self._loading or self._sequence is None:
            return
        self._sequence.duck_depth = float(valor)
        self.changed.emit()


class EffectsPanel(Page):
    TITULO = "Efectos"

    """Llave de croma y estabilización del clip seleccionado.

    Van juntas porque las dos arreglan la toma antes de editarla: quitar el
    fondo verde y quitar el temblor. Cada una en su grupo, apagada hasta que
    se prende.
    """

    changed = Signal()
    committed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        from vortex_studio.model.chroma import PRESETS, SIMILARITY, SMOOTHNESS, SPILL

        self._clip = None
        self._loading = False

        self._name = QLabel("Nada seleccionado")
        self._name.setStyleSheet("color:#7d838c; font-size:10px;")

        self.key_enabled = QCheckBox("Quitar el fondo (llave de croma)")
        self.key_enabled.toggled.connect(self._key_toggled)
        self.key_preset = QComboBox()
        self.key_preset.addItems(list(PRESETS))
        self.key_preset.setToolTip("El color de la pantalla")
        self.key_preset.activated.connect(self._preset_chosen)
        self.key_color = QPushButton("Color de la llave")
        self.key_color.clicked.connect(self._pick_key_color)
        self.similarity = SliderRow("Similitud", *SIMILARITY)
        self.smoothness = SliderRow("Suavidad", *SMOOTHNESS)
        self.spill = SliderRow("Derrame", *SPILL)
        for row in (self.similarity, self.smoothness, self.spill):
            row.changed.connect(self._push)
        self._key_hint = QLabel("Similitud: cuánto fondo se va. Derrame: quita el "
                                "reflejo verde de la piel y la ropa.")
        self._key_hint.setWordWrap(True)
        self._key_hint.setStyleSheet("color:#6f757e; font-size:10px;")

        self.stabilize = QCheckBox("Estabilizar")
        self.stabilize.setToolTip("Quita el temblor de una toma a mano. La primera vez "
                                  "analiza el video en segundo plano.")
        self.stabilize.toggled.connect(self._stabilize_toggled)
        self.strength = SliderRow("Fuerza", 1, 100, 50)
        self.strength.changed.connect(self._strength_changed)
        self.stabilize_status = QLabel("")
        self.stabilize_status.setWordWrap(True)
        self.stabilize_status.setStyleSheet("color:#6f757e; font-size:10px;")

        self._set_content(column(
            self._name,
            section("Llave de croma"),
            self.key_enabled, self.key_preset, self.key_color,
            self.similarity, self.smoothness, self.spill, self._key_hint,
            section("Estabilización"),
            self.stabilize, self.strength, self.stabilize_status,
            None,
        ))
        self.set_target(None)

    def set_target(self, clip) -> None:
        self._clip = clip
        self._loading = True
        tiene = clip is not None and hasattr(clip, "chroma")
        self._name.setText(f"Clip: {clip.name}" if tiene else "Nada seleccionado")
        self.key_enabled.setEnabled(tiene)
        if tiene:
            self.key_enabled.setChecked(clip.chroma.enabled)
            self.similarity.set_value(int(round(clip.chroma.similarity)))
            self.smoothness.set_value(int(round(clip.chroma.smoothness)))
            self.spill.set_value(int(round(clip.chroma.spill)))
            TextPanel._paint(self.key_color, clip.chroma.color)
            self.stabilize.setChecked(clip.stabilize > 0)
            if clip.stabilize > 0:
                self.strength.set_value(int(clip.stabilize))
        self.stabilize.setEnabled(tiene)
        self._loading = False
        self._describe()

    def _describe(self) -> None:
        viva = self._clip is not None and hasattr(self._clip, "chroma") and self._clip.chroma.enabled
        for widget in (self.key_preset, self.key_color, self.similarity, self.smoothness,
                       self.spill):
            widget.setEnabled(viva)
        estable = self._clip is not None and getattr(self._clip, "stabilize", 0) > 0
        self.strength.setEnabled(bool(estable))

    def _key_toggled(self, prendida: bool) -> None:
        if self._loading or self._clip is None:
            return
        self._clip.chroma.enabled = prendida
        self._describe()
        self.committed.emit("Llave de croma" if prendida else "Quitar llave de croma")

    def _stabilize_toggled(self, prendida: bool) -> None:
        if self._loading or self._clip is None:
            return
        self._clip.stabilize = self.strength.value() if prendida else 0
        self._describe()
        self.committed.emit("Estabilizar" if prendida else "Quitar estabilización")

    def _strength_changed(self, valor: int) -> None:
        if self._loading or self._clip is None or self._clip.stabilize <= 0:
            return
        self._clip.stabilize = valor
        self.changed.emit()

    def set_stabilize_status(self, texto: str) -> None:
        self.stabilize_status.setText(texto)

    def _preset_chosen(self, indice: int) -> None:
        from vortex_studio.model.chroma import PRESETS
        self.set_key_color(PRESETS[self.key_preset.itemText(indice)])

    def _pick_key_color(self) -> None:
        if self._clip is None:
            return
        color = QColorDialog.getColor(QColor(self._clip.chroma.color), self, "Color de la llave")
        if color.isValid():
            self.set_key_color(color.name())

    def set_key_color(self, color: str) -> None:
        if self._clip is None:
            return
        self._clip.chroma.color = color
        TextPanel._paint(self.key_color, color)
        self.committed.emit("Color de la llave")

    def _push(self, *_):
        if self._loading or self._clip is None:
            return
        self._clip.chroma.similarity = self.similarity.value()
        self._clip.chroma.smoothness = self.smoothness.value()
        self._clip.chroma.spill = self.spill.value()
        self.changed.emit()


TAB_STYLE = """
QTabWidget::pane { border: none; background: #1b1d21; }
QTabBar { background: #16181c; qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent; color: #808790; padding: 9px 14px 7px 14px;
    border: none; border-bottom: 2px solid transparent;
    font-size: 11px; min-width: 42px;
}
QTabBar::tab:hover { color: #c3c9d1; }
QTabBar::tab:selected { color: #f0f3f6; border-bottom: 2px solid #e0574a; }
QTabBar::tab:disabled { color: #464b52; }
QScrollArea { border: none; background: #1b1d21; }
QScrollBar:vertical {
    background: transparent; width: 9px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #3a3f46; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4a5058; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class PropertiesPanel(QDockWidget):
    """Un solo panel con pestañas, en vez de cinco ventanas apiladas.

    Las pestañas se encienden y apagan según lo que haya seleccionado: si no
    hay texto, la de Texto se ve apagada. Y al seleccionar algo el panel se
    cambia solo a su pestaña, para no tener que buscarla.
    """

    def __init__(self) -> None:
        super().__init__("Propiedades")
        self.setStyleSheet(PANEL_STYLE)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        self.transform = TransformPanel()
        self.color = ColorPanel()
        self.mask = MaskPanel()
        self.clip = ClipPanel()
        self.effects = EffectsPanel()
        self.audio = AudioPanel()
        self.text = TextPanel()
        self.image = ImagePanel()

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(TAB_STYLE)
        self._tabs.setDocumentMode(True)
        self._tabs.setUsesScrollButtons(False)

        iconos = {"Transformar": "⤢", "Color": "◐", "Máscara": "⬭", "Efectos": "✦",
                  "Clip": "▮", "Audio": "♪", "Texto": "T", "Imagen": "▣"}
        for pagina in (self.transform, self.color, self.mask, self.effects, self.clip,
                       self.audio, self.text, self.image):
            self._tabs.addTab(pagina, f"{iconos.get(pagina.TITULO, '')}  {pagina.TITULO}")

        self.setWidget(self._tabs)

    def show_page(self, pagina: QWidget) -> None:
        indice = self._tabs.indexOf(pagina)
        if indice >= 0:
            self._tabs.setCurrentIndex(indice)

    def current_is(self, *paginas) -> bool:
        return self._tabs.currentWidget() in paginas

    def set_enabled(self, pagina: QWidget, activa: bool) -> None:
        """Apaga la pestaña de lo que no aplica, en vez de esconderla.

        Esconderla haría bailar las pestañas de lugar cada vez que cambia la
        selección, y uno acaba buscando dónde quedó la que quería.
        """
        indice = self._tabs.indexOf(pagina)
        if indice >= 0:
            self._tabs.setTabEnabled(indice, activa)
