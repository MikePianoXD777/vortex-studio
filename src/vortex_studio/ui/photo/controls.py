"""Controles propios de Vortex Photo: botones de ícono, deslizador con «soltar», color.

El deslizador distingue lo que se **arrastra** (`live`, muchas veces, solo para
re-dibujar) de lo que se **suelta** (`committed`, una vez, para el historial):
así arrastrar «Brillo» de 0 a 40 deja un único paso en «Deshacer».
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.ui import theme
from vortex_studio.ui.photo.icons import draw_icon, draw_letter
from vortex_studio.ui.widgets import SLIDER_STYLE, SPIN_STYLE

MORADO = "#8b5cf6"           # acento de Vortex Photo: selección, guías, asas
ROSA = "#ff5ca8"             # guías del lienzo

PALETA = [
    "#000000", "#545454", "#737373", "#a6a6a6", "#d9d9d9", "#ffffff",
    "#ff3131", "#ff5757", "#ff66c4", "#cb6ce6", "#8c52ff", "#5e17eb",
    "#0097b2", "#0cc0df", "#5ce1e6", "#38b6ff", "#5271ff", "#004aad",
    "#00bf63", "#7ed957", "#c1ff72", "#ffde59", "#ffbd59", "#ff914d",
]


class IconBtn(QToolButton):
    """Botón plano con un ícono de `icons.draw_icon` (o una letra, o texto)."""

    def __init__(self, icon: str = "", tip: str = "", size: int = 32, *, checkable: bool = False,
                 text: str = "", letter: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon
        self._letter = letter
        self.setToolTip(tip)
        self.setAccessibleName(tip or text or icon)
        self.setCheckable(checkable)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self._text = text
        self._hover = False
        if text:
            self.setFixedHeight(size)
            self.setMinimumWidth(size)
        else:
            self.setFixedSize(size, size)

    def set_icon(self, name: str) -> None:
        self.icon_name = name
        self.update()

    def sizeHint(self) -> QSize:
        if self._text:
            ancho = self.fontMetrics().horizontalAdvance(self._text) + (38 if self.icon_name else 24)
            return QSize(max(ancho, self.minimumWidth()), self.height())
        return super().sizeHint()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isChecked() or (self._hover and self.isEnabled()):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.PILDORA if self.isChecked() else theme.PILDORA_HOVER))
            p.drawRoundedRect(r, 8, 8)
        if not self.isEnabled():
            color = QColor(theme.APAGADO)
        elif self.isChecked() or self._hover:
            color = QColor(theme.TEXTO)
        else:
            color = QColor(theme.TENUE)
        if self._text:
            x = 8.0
            if self.icon_name:
                draw_icon(p, self.icon_name, QRectF(r.left() + 6, r.center().y() - 9, 18, 18), color)
                x = 28.0
            p.setPen(color)
            p.drawText(QRectF(r.left() + x, r.top(), r.width() - x - 6, r.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self._text)
        else:
            lado = min(r.width(), r.height()) * 0.62
            caja = QRectF(r.center().x() - lado / 2, r.center().y() - lado / 2, lado, lado)
            if self._letter:
                draw_letter(p, self.icon_name, caja, color, **self._letter)
            else:
                draw_icon(p, self.icon_name, caja, color)
        p.end()


class PSlider(QWidget):
    """Etiqueta, deslizador y número. `live` mientras se arrastra, `committed` al soltar."""

    live = Signal(float)
    committed = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float, neutral: float = 0.0,
                 div: float = 1.0, suffix: str = "") -> None:
        super().__init__()
        self.neutral = neutral
        self.div = div
        self._dragging = False
        self._label = QLabel(label)
        self._label.setStyleSheet(f"color:{theme.TENUE}; font-size:12px;")
        self._label.setToolTip("Doble clic para volver al valor original")
        self._label.setMinimumWidth(78)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(int(round(minimum * div)), int(round(maximum * div)))
        self._slider.setValue(int(round(neutral * div)))
        self._slider.setStyleSheet(SLIDER_STYLE)
        self._slider.setFocusPolicy(Qt.ClickFocus)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setDecimals(0 if div == 1 else 1)
        self._spin.setSingleStep(1 if div == 1 else 0.1)
        self._spin.setSuffix(suffix)
        self._spin.setValue(neutral)
        self._spin.setKeyboardTracking(False)
        self._spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self._spin.setAlignment(Qt.AlignRight)
        self._spin.setFixedWidth(58)
        self._spin.setStyleSheet(SPIN_STYLE)

        self._slider.sliderPressed.connect(self._pressed)
        self._slider.sliderReleased.connect(self._released)
        self._slider.valueChanged.connect(self._from_slider)
        self._spin.valueChanged.connect(self._from_spin)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(8)
        lay.addWidget(self._label)
        lay.addWidget(self._slider, 1)
        lay.addWidget(self._spin)

    # El valor sale siempre en unidades reales (no multiplicadas por `div`).
    def value(self) -> float:
        return self._slider.value() / self.div

    def set_value(self, value: float) -> None:
        """Refleja un valor externo sin disparar señales."""
        for w, v in ((self._slider, int(round(value * self.div))), (self._spin, value)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

    def _pressed(self) -> None:
        self._dragging = True

    def _released(self) -> None:
        self._dragging = False
        self.committed.emit(self.value())

    def _from_slider(self, raw: int) -> None:
        v = raw / self.div
        self._spin.blockSignals(True)
        self._spin.setValue(v)
        self._spin.blockSignals(False)
        self.live.emit(v)
        if not self._dragging:
            self.committed.emit(v)

    def _from_spin(self, v: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(round(v * self.div)))
        self._slider.blockSignals(False)
        self.live.emit(v)
        self.committed.emit(v)

    def setEnabled(self, on: bool) -> None:
        super().setEnabled(on)

    def mouseDoubleClickEvent(self, e) -> None:
        if self.value() != self.neutral:
            self.set_value(self.neutral)
            self.live.emit(self.neutral)
            self.committed.emit(self.neutral)


class ColorPopup(QFrame):
    """Paleta de colores que sale bajo un `ColorButton`."""

    picked = Signal(object)

    def __init__(self, current: str | None, allow_none: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Popup)
        self.setObjectName("colorpopup")
        self.setStyleSheet(
            f"#colorpopup {{ background:{theme.CAMPO}; border:1px solid {theme.BORDE_FUERTE}; "
            "border-radius:10px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        grid = QGridLayout()
        grid.setSpacing(5)
        self.swatches: dict[str, QToolButton] = {}
        for i, hexa in enumerate(PALETA):
            b = QToolButton()
            b.setFixedSize(24, 24)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(hexa)
            borde = MORADO if (current or "").lower() == hexa else theme.BORDE_FUERTE
            b.setStyleSheet(f"QToolButton {{ background:{hexa}; border:2px solid {borde}; "
                            "border-radius:12px; }")
            b.clicked.connect(lambda _=False, h=hexa: self._pick(h))
            self.swatches[hexa] = b
            grid.addWidget(b, i // 6, i % 6)
        lay.addLayout(grid)
        fila = QHBoxLayout()
        self.hex = QLineEdit(current or "")
        self.hex.setPlaceholderText("#rrggbb")
        self.hex.setMaxLength(9)
        self.hex.returnPressed.connect(self._from_hex)
        fila.addWidget(self.hex, 1)
        otro = QPushButton("Otro…")
        otro.clicked.connect(self._other)
        fila.addWidget(otro)
        lay.addLayout(fila)
        if allow_none:
            nada = QPushButton("Sin color")
            nada.clicked.connect(lambda: self._pick(None))
            lay.addWidget(nada)
        self._current = current

    def _pick(self, color) -> None:
        self.picked.emit(color)
        self.close()

    def _from_hex(self) -> None:
        c = QColor(self.hex.text().strip())
        if c.isValid():
            self._pick(c.name())

    def _other(self) -> None:
        c = QColorDialog.getColor(QColor(self._current or "#ffffff"), self, "Elige un color")
        if c.isValid():
            self._pick(c.name())


class ColorButton(QToolButton):
    """Un círculo con el color actual; al pulsarlo se abre la paleta."""

    changed = Signal(object)        # "#rrggbb" o None

    def __init__(self, color: str | None = "#000000", tip: str = "Color", *,
                 allow_none: bool = False, size: int = 28) -> None:
        super().__init__()
        self._color = color
        self.allow_none = allow_none
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(self.open_popup)
        self.popup: ColorPopup | None = None

    def color(self) -> str | None:
        return self._color

    def set_color(self, color: str | None) -> None:
        """Pone el color sin avisar (para reflejar el estado de la capa)."""
        self._color = color
        self.update()

    def open_popup(self) -> None:
        self.popup = ColorPopup(self._color, self.allow_none, self)
        self.popup.picked.connect(self._picked)
        self.popup.adjustSize()
        self.popup.move(self.mapToGlobal(QPoint(0, self.height() + 4)))
        self.popup.show()

    def _picked(self, color) -> None:
        self._color = color
        self.update()
        self.changed.emit(color)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(theme.BORDE_FUERTE), 1.5))
        if self._color:
            p.setBrush(QColor(self._color))
            p.drawEllipse(r)
        else:
            p.setBrush(QColor(theme.CAMPO))
            p.drawEllipse(r)
            p.setPen(QPen(QColor(theme.PLAYHEAD), 1.5))
            p.drawLine(QPointF(r.left() + r.width() * 0.15, r.bottom() - r.height() * 0.15),
                       QPointF(r.right() - r.width() * 0.15, r.top() + r.height() * 0.15))
        p.end()


class Segmented(QWidget):
    """Una fila de botones de los que solo uno está encendido."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[object, str]], value=None) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.buttons: dict[object, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_value(k, emit=True))
            lay.addWidget(b)
            self.buttons[key] = b
        self._value = None
        self.set_value(value if value is not None else options[0][0])

    def value(self):
        return self._value

    def set_value(self, key, emit: bool = False) -> None:
        self._value = key
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        if emit:
            self.changed.emit(key)


def heading(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{theme.TEXTO}; font-size:14px; font-weight:600;")
    return lab


def muted(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color:{theme.MUY_TENUE}; font-size:11px;")
    return lab


def separator(vertical: bool = True) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
    f.setStyleSheet(f"color:{theme.BORDE}; background:{theme.BORDE};")
    if vertical:
        f.setFixedWidth(1)
    else:
        f.setFixedHeight(1)
    return f
