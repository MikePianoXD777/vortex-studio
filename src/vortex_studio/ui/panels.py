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

from vortex_studio.model import ANCHORS, ColorAdjust, Title
from vortex_studio.model.color import BRIGHTNESS, CONTRAST, GAMMA, SATURATION
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

        for row in self._rows():
            row.changed.connect(self._push)

        reset = QPushButton("Restablecer")
        reset.clicked.connect(self._reset)

        self.setWidget(column(
            self._target,
            section("Ajustes"),
            self._brightness, self._contrast, self._saturation, self._gamma,
            reset,
            None,
        ))
        self.set_target(None, "")

    def _rows(self) -> list[SliderRow]:
        return [self._brightness, self._contrast, self._saturation, self._gamma]

    def set_target(self, adjust: ColorAdjust | None, name: str) -> None:
        """Apunta el panel a un clip. Sin clip, los controles se apagan."""
        self._adjust = adjust
        self._target.setText(f"Clip: {name}" if adjust else "Ningún clip bajo el playhead")

        for row in self._rows():
            row.setEnabled(adjust is not None)

        if adjust is not None:
            self._brightness.set_value(adjust.brightness)
            self._contrast.set_value(adjust.contrast)
            self._saturation.set_value(adjust.saturation)
            self._gamma.set_value(adjust.gamma)

    def _push(self) -> None:
        if self._adjust is None:
            return
        self._adjust.brightness = self._brightness.value()
        self._adjust.contrast = self._contrast.value()
        self._adjust.saturation = self._saturation.value()
        self._adjust.gamma = self._gamma.value()
        self.changed.emit()

    def _reset(self) -> None:
        if self._adjust is None:
            return
        self._adjust.reset()
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
