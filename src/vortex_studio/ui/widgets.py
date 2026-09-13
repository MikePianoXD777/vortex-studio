"""Piezas de interfaz que se repiten en los paneles."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.ui import theme


class FlowLayout(QLayout):
    """Acomoda los widgets en fila y brinca a la siguiente cuando no caben.

    Ocho pestañas no caben en un panel de 330 px; con flechas de scroll la
    mitad quedaría escondida, y aquí todas se ven siempre.
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 4) -> None:
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, alto_fila = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x, y = area.x(), y + alto_fila + self.spacing()
                alto_fila = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            alto_fila = max(alto_fila, hint.height())
        return y + alto_fila - rect.y() + m.bottom()


class PillTabs(QWidget):
    """Pestañas en píldora que mandan sobre un QTabWidget sin barra.

    El QTabWidget sigue siendo el que sabe qué página está activa y cuál está
    apagada; las píldoras solo lo reflejan. Así el resto del programa sigue
    hablándole a las pestañas como siempre.
    """

    def __init__(self, tabs: QTabWidget) -> None:
        super().__init__()
        self._tabs = tabs
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.setStyleSheet(theme.PILL_STYLE)
        self._flow = FlowLayout(self, spacing=2)
        self._flow.setContentsMargins(10, 10, 10, 8)

        tabs.tabBar().hide()
        for i in range(tabs.count()):
            self._add(i)
        self._group.idClicked.connect(tabs.setCurrentIndex)
        tabs.currentChanged.connect(self.sync)
        self.sync()

    def _add(self, index: int) -> None:
        boton = QToolButton()
        boton.setText(self._tabs.tabText(index))
        boton.setCheckable(True)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setFocusPolicy(Qt.NoFocus)
        self._group.addButton(boton, index)
        self._flow.addWidget(boton)

    def button(self, index: int) -> QToolButton | None:
        return self._group.button(index)

    def sync(self, *_args) -> None:
        for boton in self._group.buttons():
            indice = self._group.id(boton)
            boton.setEnabled(self._tabs.isTabEnabled(indice))
            boton.setChecked(indice == self._tabs.currentIndex())

SLIDER_STYLE = theme.SLIDER_STYLE

# El número se ve como texto, en monoespaciada y sin caja; al hacerle clic
# se sigue pudiendo escribir.
SPIN_STYLE = f"""
QSpinBox {{
    background: transparent; color: {theme.TENUE}; border: 1px solid transparent;
    border-radius: 6px; padding: 1px 2px; font-family: {theme.MONO}; font-size: 11px;
    min-width: 44px; max-width: 58px;
}}
QSpinBox:hover {{ border-color: {theme.BORDE}; }}
QSpinBox:focus {{ border-color: {theme.BORDE_FUERTE}; color: {theme.TEXTO};
    background: {theme.CAMPO}; }}
QSpinBox:disabled {{ color: {theme.APAGADO}; }}
"""


class _ValueSpin(QSpinBox):
    """Guarda enteros pero muestra el valor real: 12 décimas se ven «1.2»."""

    def __init__(self, scale: int = 1, decimals: int = 0, suffix: str = "") -> None:
        super().__init__()
        self._scale, self._decimals, self._sufijo = scale, decimals, suffix

    def textFromValue(self, value: int) -> str:
        if self._scale == 1 and not self._decimals:
            return f"{value}{self._sufijo}"
        return f"{value / self._scale:.{self._decimals}f}{self._sufijo}"

    def valueFromText(self, text: str) -> int:
        limpio = text.replace(self._sufijo, "").replace(",", ".").strip() if self._sufijo \
            else text.replace(",", ".").strip()
        try:
            return int(round(float(limpio) * self._scale))
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        from PySide6.QtGui import QValidator
        limpio = text.replace(self._sufijo, "").strip() if self._sufijo else text.strip()
        if limpio in ("", "-", ".", "-."):
            return QValidator.Intermediate, text, pos
        try:
            float(limpio.replace(",", "."))
        except ValueError:
            return QValidator.Invalid, text, pos
        return QValidator.Acceptable, text, pos


class Card(QFrame):
    """Una zona de la ventana: tarjeta redondeada con borde tenue."""

    def __init__(self, parent: QWidget | None = None, padding=(0, 0, 0, 0)) -> None:
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(theme.CARD_STYLE)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(0)


class Switch(QAbstractButton):
    """Interruptor de encendido, en vez de una casilla o una lista de dos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(30, 17)

    def sizeHint(self) -> QSize:
        return QSize(30, 17)

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        encendido = self.isChecked()
        activo = self.isEnabled()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TENUE if encendido and activo else theme.PILDORA))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        lado = r.height() - 4
        x = r.right() - lado - 2 if encendido else r.left() + 2
        p.setBrush(QColor(theme.ACENTO if activo else theme.APAGADO))
        p.drawEllipse(QRect(int(x), r.top() + 2, lado, lado))
        p.end()


class SwitchRow(QWidget):
    """Fila con nombre a la izquierda e interruptor a la derecha, en su cajita."""

    toggled = Signal(bool)

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("filaInterruptor")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#filaInterruptor {{ background: {theme.CAMPO}; border: 1px solid {theme.BORDE};"
            f" border-radius: 8px; }}"
        )
        self._label = QLabel(label)
        self._label.setStyleSheet(f"color:{theme.TEXTO}; font-size:12px;")
        self.switch = Switch()
        self.switch.toggled.connect(self.toggled.emit)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self._label, 1)
        layout.addWidget(self.switch)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, on: bool) -> None:
        self.switch.setChecked(on)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if not hasattr(self, "_label") or event.type() != QEvent.EnabledChange:
            return
        self._label.setStyleSheet(
            f"color:{theme.TEXTO if self.isEnabled() else theme.APAGADO}; font-size:12px;")

    def mousePressEvent(self, event) -> None:
        if self.isEnabled():
            self.switch.click()


ICONOS = ("inicio", "fin", "play", "pausa", "anterior", "siguiente", "repetir",
          "volumen", "silencio", "flotar", "cerrar", "seleccion", "navaja", "dividir",
          "deslizar", "iman", "enlace", "buscar", "mas")


def draw_icon(painter, nombre: str, rect, color) -> None:
    """Íconos de línea dibujados a mano: se ven igual en Windows y en Linux.

    Los caracteres como ⏮ o 🔊 dependen de las fuentes del sistema y en cada
    máquina salían de otro tamaño, o como cuadritos.
    """
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QPainterPath, QPen

    c = QRectF(rect).center()
    s = min(rect.width(), rect.height()) / 16.0
    pen = QPen(color, 1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def P(x, y):
        return QPointF(c.x() + x * s, c.y() + y * s)

    def triangulo(puntos):
        camino = QPainterPath()
        camino.moveTo(P(*puntos[0]))
        for punto in puntos[1:]:
            camino.lineTo(P(*punto))
        camino.closeSubpath()
        painter.setBrush(color)
        painter.drawPath(camino)
        painter.setBrush(Qt.NoBrush)

    if nombre == "play":
        triangulo([(-3, -5), (5, 0), (-3, 5)])
    elif nombre == "pausa":
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(P(-4, -5), P(-1, 5)), 0.8, 0.8)
        painter.drawRoundedRect(QRectF(P(1, -5), P(4, 5)), 0.8, 0.8)
    elif nombre == "inicio":
        triangulo([(4, -5), (-2, 0), (4, 5)])
        painter.drawLine(P(-4.5, -5), P(-4.5, 5))
    elif nombre == "fin":
        triangulo([(-4, -5), (2, 0), (-4, 5)])
        painter.drawLine(P(4.5, -5), P(4.5, 5))
    elif nombre == "anterior":
        painter.drawPolyline([P(2, -4), P(-2, 0), P(2, 4)])
    elif nombre == "siguiente":
        painter.drawPolyline([P(-2, -4), P(2, 0), P(-2, 4)])
    elif nombre == "repetir":
        camino = QPainterPath()
        camino.arcMoveTo(QRectF(P(-5, -5), P(5, 5)), 60)
        camino.arcTo(QRectF(P(-5, -5), P(5, 5)), 60, 300)
        painter.drawPath(camino)
        painter.drawPolyline([P(0.5, -7), P(3, -4.5), P(0.5, -2)])
    elif nombre in ("volumen", "silencio"):
        triangulo([(-6, -2), (-3, -2), (1, -5.5), (1, 5.5), (-3, 2), (-6, 2)])
        if nombre == "volumen":
            camino = QPainterPath()
            camino.arcMoveTo(QRectF(P(-1, -4), P(5, 4)), -50)
            camino.arcTo(QRectF(P(-1, -4), P(5, 4)), -50, 100)
            painter.drawPath(camino)
        else:
            painter.drawLine(P(3, -2.5), P(7, 2.5))
            painter.drawLine(P(7, -2.5), P(3, 2.5))
    elif nombre == "flotar":
        painter.drawRoundedRect(QRectF(P(-5, -3), P(3, 5)), 1.5, 1.5)
        painter.drawPolyline([P(-1, -6), P(6, -6), P(6, 1)])
    elif nombre == "cerrar":
        painter.drawLine(P(-4, -4), P(4, 4))
        painter.drawLine(P(4, -4), P(-4, 4))
    elif nombre == "seleccion":
        triangulo([(-4, -6), (4, 1), (0, 1.5), (-1.5, 6)])
    elif nombre == "navaja":
        painter.drawEllipse(P(-3, 3.5), 2.2 * s, 2.2 * s)
        painter.drawEllipse(P(3, 3.5), 2.2 * s, 2.2 * s)
        painter.drawLine(P(-1.8, 1.8), P(4, -6))
        painter.drawLine(P(1.8, 1.8), P(-4, -6))
    elif nombre == "dividir":
        painter.drawLine(P(0, -6), P(0, 6))
        painter.drawRoundedRect(QRectF(P(-6.5, -3), P(-2, 3)), 1, 1)
        painter.drawRoundedRect(QRectF(P(2, -3), P(6.5, 3)), 1, 1)
    elif nombre == "deslizar":
        painter.drawRoundedRect(QRectF(P(-3, -4), P(3, 4)), 1, 1)
        painter.drawPolyline([P(-5, -2), P(-7, 0), P(-5, 2)])
        painter.drawPolyline([P(5, -2), P(7, 0), P(5, 2)])
    elif nombre == "iman":
        camino = QPainterPath()
        camino.moveTo(P(-5, -5))
        camino.lineTo(P(-5, 1))
        camino.arcTo(QRectF(P(-5, -4), P(5, 6)), 180, 180)
        camino.lineTo(P(5, -5))
        painter.drawPath(camino)
        painter.drawLine(P(-6.5, -3), P(-3.5, -3))
        painter.drawLine(P(3.5, -3), P(6.5, -3))
    elif nombre == "enlace":
        painter.drawRoundedRect(QRectF(P(-7, -2.5), P(0.5, 2.5)), 2.5 * s, 2.5 * s)
        painter.drawRoundedRect(QRectF(P(-0.5, -2.5), P(7, 2.5)), 2.5 * s, 2.5 * s)
    elif nombre == "buscar":
        painter.drawEllipse(P(-1, -1), 4 * s, 4 * s)
        painter.drawLine(P(2, 2), P(5.5, 5.5))
    elif nombre == "mas":
        painter.drawLine(P(0, -5), P(0, 5))
        painter.drawLine(P(-5, 0), P(5, 0))


def make_icon(nombre: str, color: str = theme.TENUE, size: int = 16):
    """Un QIcon con el ícono dibujado, a doble resolución para pantallas HiDPI."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(2.0)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    draw_icon(p, nombre, QRectF(0, 0, size, size), QColor(color))
    p.end()
    return QIcon(pixmap)


class IconButton(QToolButton):
    """Botón plano con un ícono de `draw_icon`; claro al pasar o encendido."""

    def __init__(self, icon: str, tip: str = "", size: int = 28, circle: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon
        self._circle = circle
        self.setToolTip(tip)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self._hover = False

    def set_icon(self, icon: str) -> None:
        self.icon_name = icon
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._circle:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACENTO if self.isEnabled() else theme.APAGADO))
            p.drawEllipse(r)
            color = QColor(theme.SOBRE_ACENTO)
            caja = r.adjusted(r.width() * 0.2, r.height() * 0.2,
                              -r.width() * 0.2, -r.height() * 0.2)
            if self.icon_name == "play":
                caja.translate(r.width() * 0.03, 0)
        else:
            if self.isChecked() or (self._hover and self.isEnabled()):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.PILDORA if self.isChecked() else theme.PILDORA_HOVER))
                p.drawRoundedRect(r, 7, 7)
            if not self.isEnabled():
                color = QColor(theme.APAGADO)
            elif self.isChecked() or self._hover:
                color = QColor(theme.TEXTO)
            else:
                color = QColor(theme.TENUE)
            lado = min(r.width(), r.height()) * 0.62
            caja = QRectF(r.center().x() - lado / 2, r.center().y() - lado / 2, lado, lado)
        draw_icon(p, self.icon_name, caja, color)
        p.end()


class DockTitle(QWidget):
    """Barra de título de un panel acoplable, con el estilo de las tarjetas.

    El diseño no trae títulos: las tarjetas empiezan directo con su contenido.
    Aquí queda una franja delgada para agarrar el panel y despegarlo, con sus
    botones de flotar y cerrar, que es lo que Mike pidió: "despegables pero
    con estilo".
    """

    def __init__(self, dock, show_title: bool = False) -> None:
        super().__init__(dock)
        self._dock = dock
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(f"{dock.windowTitle()}: arrastra para mover o despegar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 6, 0)
        layout.setSpacing(2)
        self._title = QLabel(dock.windowTitle().upper() if show_title else "")
        self._title.setStyleSheet(
            f"color:{theme.MUY_TENUE}; font-size:10px; font-weight:600; letter-spacing:1px;")
        layout.addWidget(self._title, 1)
        self.float_button = IconButton("flotar", "Despegar o volver a acoplar", 20)
        self.float_button.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        layout.addWidget(self.float_button)
        self.close_button = IconButton("cerrar", "Cerrar (se vuelve a abrir en Ver)", 20)
        self.close_button.clicked.connect(dock.close)
        layout.addWidget(self.close_button)
        from PySide6.QtWidgets import QDockWidget
        self.close_button.setVisible(
            bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable))
        self.setFixedHeight(24)

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TARJETA))
        r = self.rect()
        radio = theme.RADIO_TARJETA
        p.drawRoundedRect(r.adjusted(0, 0, 0, radio), radio, radio)
        # Tres puntitos al centro: la agarradera.
        p.setBrush(QColor(theme.APAGADO))
        cx = r.center().x()
        for dx in (-6, 0, 6):
            p.drawEllipse(QRect(cx + dx - 1, r.center().y(), 3, 3))
        p.end()


def style_dock(dock, show_title: bool = False) -> None:
    """Pone la barra de título propia y el aspecto de tarjeta a un panel."""
    dock.setTitleBarWidget(DockTitle(dock, show_title))
    contenido = dock.widget()
    if contenido is not None:
        contenido.setObjectName("cuerpoDock")
        contenido.setAttribute(Qt.WA_StyledBackground, True)
        contenido.setStyleSheet(
            contenido.styleSheet() +
            f"\n#cuerpoDock {{ background: {theme.TARJETA}; "
            f"border-bottom-left-radius: {theme.RADIO_TARJETA}px; "
            f"border-bottom-right-radius: {theme.RADIO_TARJETA}px; }}")


class SliderRow(QWidget):
    """Etiqueta, deslizador y número, los tres amarrados entre sí.

    Doble clic en la etiqueta regresa el valor a su neutro, que es el gesto
    que todo mundo ya espera de un control de color.
    """

    changed = Signal(int)

    def __init__(self, label: str, minimum: int, maximum: int, neutral: int,
                 scale: int = 1, decimals: int = 0, suffix: str = "") -> None:
        super().__init__()
        self.neutral = neutral

        self._label = QLabel(label)
        self._label.setStyleSheet(f"color:{theme.TENUE}; font-size:12px;")
        self._label.setToolTip("Doble clic para regresar al valor neutro")
        self._label.setMinimumWidth(66)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setValue(neutral)
        self._slider.setStyleSheet(SLIDER_STYLE)

        self._spin = _ValueSpin(scale, decimals, suffix)
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(neutral)
        self._spin.setStyleSheet(SPIN_STYLE)
        self._spin.setButtonSymbols(QSpinBox.NoButtons)
        self._spin.setAlignment(Qt.AlignRight)

        self._slider.valueChanged.connect(self._from_slider)
        self._spin.valueChanged.connect(self._from_spin)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)
        layout.addWidget(self._label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._spin)

    def _from_slider(self, value: int) -> None:
        if self._spin.value() != value:
            self._spin.blockSignals(True)
            self._spin.setValue(value)
            self._spin.blockSignals(False)
        self.changed.emit(value)

    def _from_spin(self, value: int) -> None:
        if self._slider.value() != value:
            self._slider.blockSignals(True)
            self._slider.setValue(value)
            self._slider.blockSignals(False)
        self.changed.emit(value)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, value: int) -> None:
        """Pone el valor sin disparar `changed`, para reflejar estado externo."""
        for widget in (self._slider, self._spin):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

    def mouseDoubleClickEvent(self, event) -> None:
        self._slider.setValue(self.neutral)


def section(title: str) -> QLabel:
    """Encabezado de grupo dentro de un panel."""
    label = QLabel(title.upper())
    label.setStyleSheet(
        f"color:{theme.MUY_TENUE}; font-size:10px; font-weight:600; "
        "letter-spacing:1.5px; padding:14px 0 4px 0;"
    )
    return label


def column(*widgets, spacing: int = 4, margins: tuple = (10, 8, 10, 10)) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    return box


class Collapsible(QWidget):
    """Un grupo que se abre y se cierra con un clic en su título.

    Sin esto, el panel de Color con la curva y la viñeta adentro se vuelve
    una lista de once deslizadores, y ahí se acabó el "fácil de usar": lo
    que se usa todos los días queda enterrado entre lo que se usa una vez
    al mes. Cerrado por omisión, se abre quien lo necesite.
    """

    def __init__(self, title: str, *widgets, abierto: bool = False) -> None:
        super().__init__()

        self._title = title
        self._button = QToolButton()
        self._button.setCheckable(True)
        self._button.setChecked(abierto)
        self._button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._button.setStyleSheet(
            "QToolButton { border: none; background: transparent; "
            f"color:{theme.MUY_TENUE}; font-size:10px; font-weight:600; letter-spacing:1.5px; "
            "padding:14px 0 4px 0; text-align:left; }"
            f"QToolButton:hover {{ color:{theme.TEXTO}; }}"
        )
        self._button.clicked.connect(self._toggle)

        self._body = QWidget()
        cuerpo = QVBoxLayout(self._body)
        cuerpo.setContentsMargins(0, 0, 0, 4)
        cuerpo.setSpacing(4)
        for widget in widgets:
            if isinstance(widget, QWidget):
                cuerpo.addWidget(widget)
            elif widget is not None:
                cuerpo.addLayout(widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._button)
        layout.addWidget(self._body)

        self._refresh()

    def _toggle(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        abierto = self._button.isChecked()
        self._body.setVisible(abierto)
        self._button.setText(f"{'▾' if abierto else '▸'}  {self._title.upper()}")

    @property
    def abierto(self) -> bool:
        return self._button.isChecked()

    def abrir(self, si: bool = True) -> None:
        self._button.setChecked(si)
        self._refresh()


class CurveView(QWidget):
    """La gráfica de la curva de color. Solo se mira, no se arrastra.

    Es la mitad de la idea de tener una curva sin editor de bezier: los
    cinco deslizadores dicen qué hacer y esta gráfica dice qué está pasando.
    Sin el dibujo, cinco números llamados "sombras" y "luces" no le dicen
    nada a nadie.

    Dibuja la misma curva que se le manda a FFmpeg —ver `model/curves.py`—
    así que lo que se ve aquí es lo que se le hace a la imagen.
    """

    def __init__(self) -> None:
        super().__init__()
        self._curves = None
        self.setMinimumHeight(92)
        self.setToolTip("La curva que se le está aplicando al clip")

    def set_curves(self, curves) -> None:
        self._curves = curves
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        marco = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#15171a"))
        painter.drawRoundedRect(marco, 3, 3)

        # La curva se dibuja adentro con un margen: sin él, los puntos de
        # los extremos quedan cortados a la mitad contra el borde.
        caja = marco.adjusted(4, 4, -4, -4)

        rejilla = QPen(QColor("#282c32"), 1)
        painter.setPen(rejilla)
        for i in (1, 2, 3):
            x = caja.left() + caja.width() * i / 4
            y = caja.top() + caja.height() * i / 4
            painter.drawLine(int(x), caja.top(), int(x), caja.bottom())
            painter.drawLine(caja.left(), int(y), caja.right(), int(y))

        # La diagonal es el "no hacer nada": tenerla al lado hace obvio de
        # un vistazo hacia dónde se movió la curva.
        painter.setPen(QPen(QColor("#3a3f46"), 1, Qt.DashLine))
        painter.drawLine(caja.left(), caja.bottom(), caja.right(), caja.top())

        if self._curves is None:
            painter.end()
            return

        def punto(x: float, y: float) -> tuple[float, float]:
            return (caja.left() + caja.width() * x,
                    caja.bottom() - caja.height() * y)

        trazo = QPainterPath()
        pasos = 48
        for i in range(pasos + 1):
            x = i / pasos
            px, py = punto(x, self._curves.at(x))
            if i == 0:
                trazo.moveTo(px, py)
            else:
                trazo.lineTo(px, py)

        painter.setPen(QPen(QColor("#5f9de0"), 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(trazo)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#d6dae0"))
        for x, y in self._curves.points():
            px, py = punto(x, y)
            painter.drawEllipse(QPointF(px, py), 2.6, 2.6)

        painter.end()
