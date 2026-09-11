"""El launcher: elegir con qué se va a trabajar antes de abrir el editor.

Vortex Studio va a ser dos editores en uno. Por ahora el de video funciona
y el de fotos todavía no, así que su tarjeta se dibuja apagada y no
responde al clic — se ve que existe, pero no se puede entrar.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

VIDEO = "video"
FOTOS = "fotos"

CARD_W, CARD_H = 226, 252

BG = QColor("#16181c")
CARD_BG = QColor("#212429")
CARD_BG_HOVER = QColor("#282d34")
CARD_BG_OFF = QColor("#1c1e22")
CARD_BORDER = QColor("#31363d")
CARD_BORDER_HOVER = QColor("#566070")
ACCENT = QColor("#e0574a")
TITLE = QColor("#eef1f4")
TITLE_OFF = QColor("#6a707a")
SUB = QColor("#878d96")
SUB_OFF = QColor("#565c65")
ICON = QColor("#c3c9d1")
ICON_OFF = QColor("#4d535b")


class ModeCard(QWidget):
    """Una tarjeta del launcher. Se dibuja completa a mano.

    Se dibuja en vez de componerla con widgets porque los tres estados
    —normal, encima, apagada— cambian color de fondo, borde, texto e icono
    a la vez, y con hojas de estilo eso queda repartido en varios lados.
    """

    clicked = Signal(str)

    def __init__(self, mode: str, title: str, subtitle: str,
                 enabled: bool = True, note: str = "") -> None:
        super().__init__()
        self.mode = mode
        self.title = title
        self.subtitle = subtitle
        self.note = note
        self._enabled = enabled
        self._hover = False

        self.setFixedSize(CARD_W, CARD_H)
        self.setAttribute(Qt.WA_Hover, True)
        if enabled:
            self.setCursor(Qt.PointingHandCursor)
            self.setFocusPolicy(Qt.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(CARD_W, CARD_H)

    # --- dibujo -----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        active = self._enabled and (self._hover or self.hasFocus())
        card = QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1)

        if not self._enabled:
            background, border = CARD_BG_OFF, CARD_BORDER
        elif active:
            background, border = CARD_BG_HOVER, CARD_BORDER_HOVER
        else:
            background, border = CARD_BG, CARD_BORDER

        painter.setBrush(background)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(card, 10, 10)

        if active:
            # Filo de acento arriba, para marcar cuál está seleccionada.
            painter.setPen(Qt.NoPen)
            painter.setBrush(ACCENT)
            painter.drawRoundedRect(QRectF(CARD_W / 2 - 26, 0, 52, 3), 1.5, 1.5)

        self._draw_icon(painter)

        font = QFont()
        font.setPointSize(14)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(TITLE if self._enabled else TITLE_OFF)
        painter.drawText(QRectF(0, 150, CARD_W, 26),
                         Qt.AlignHCenter | Qt.AlignVCenter, self.title)

        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(SUB if self._enabled else SUB_OFF)
        painter.drawText(QRectF(18, 176, CARD_W - 36, 34),
                         Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.subtitle)

        if self.note:
            self._draw_badge(painter, self.note)

        painter.end()

    def _draw_badge(self, painter: QPainter, text: str) -> None:
        font = QFont()
        font.setPointSize(8)
        font.setWeight(QFont.DemiBold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        painter.setFont(font)

        width = painter.fontMetrics().horizontalAdvance(text) + 22
        pill = QRectF((CARD_W - width) / 2, CARD_H - 44, width, 21)

        painter.setPen(QPen(QColor("#3d434b"), 1))
        painter.setBrush(QColor("#24282e"))
        painter.drawRoundedRect(pill, 10.5, 10.5)

        painter.setPen(QColor("#8b929b"))
        painter.drawText(pill, Qt.AlignCenter, text)

    def _draw_icon(self, painter: QPainter) -> None:
        """Iconos dibujados con trazos: no dependen de tener un tema instalado."""
        color = ICON if self._enabled else ICON_OFF
        painter.save()
        painter.translate(CARD_W / 2, 92)
        painter.setPen(QPen(color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)

        if self.mode == VIDEO:
            # Tira de película: marco con perforaciones a los lados.
            painter.drawRoundedRect(QRectF(-32, -24, 64, 48), 4, 4)
            painter.drawLine(-20, -24, -20, 24)
            painter.drawLine(20, -24, 20, 24)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            for y in (-16, -3, 10):
                painter.drawRoundedRect(QRectF(-29, y, 6, 6), 1.5, 1.5)
                painter.drawRoundedRect(QRectF(23, y, 6, 6), 1.5, 1.5)
            # Triángulo de play al centro.
            play = QPainterPath()
            play.moveTo(-6, -9)
            play.lineTo(9, 0)
            play.lineTo(-6, 9)
            play.closeSubpath()
            painter.drawPath(play)
        else:
            # Foto: marco, sol y montaña.
            painter.drawRoundedRect(QRectF(-32, -24, 64, 48), 4, 4)
            painter.drawEllipse(QRectF(6, -16, 11, 11))
            ridge = QPainterPath()
            ridge.moveTo(-27, 18)
            ridge.lineTo(-9, -4)
            ridge.lineTo(3, 10)
            ridge.lineTo(11, 2)
            ridge.lineTo(27, 18)
            painter.drawPath(ridge)

        painter.restore()

    # --- interacción ------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def focusInEvent(self, event) -> None:
        self.update()

    def focusOutEvent(self, event) -> None:
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._enabled and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.mode)

    def keyPressEvent(self, event) -> None:
        if self._enabled and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.mode)
        else:
            super().keyPressEvent(event)


class Launcher(QDialog):
    """Ventana de arranque. `choice` queda en VIDEO o en None si se cancela."""

    def __init__(self, version: str = "") -> None:
        super().__init__()
        self.choice: str | None = None

        self.setWindowTitle("Vortex Studio")
        self.setFixedSize(560, 470)
        self.setStyleSheet(f"QDialog {{ background: {BG.name()}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 26)
        layout.setSpacing(0)
        layout.addWidget(self._header())
        layout.addSpacing(26)
        layout.addLayout(self._cards())
        layout.addStretch(1)
        layout.addWidget(self._footer(version))

    def _header(self) -> QWidget:
        box = QWidget()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(6)

        title = QLabel("VORTEX STUDIO")
        font = QFont()
        font.setPointSize(21)
        font.setWeight(QFont.DemiBold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        title.setFont(font)
        title.setStyleSheet(f"color: {TITLE.name()};")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("¿Qué vas a editar?")
        subtitle.setStyleSheet(f"color: {SUB.name()}; font-size: 11px;")
        subtitle.setAlignment(Qt.AlignCenter)

        inner.addWidget(title)
        inner.addWidget(subtitle)
        return box

    def _cards(self) -> QHBoxLayout:
        video = ModeCard(VIDEO, "Video", "Editor de video no lineal")
        fotos = ModeCard(FOTOS, "Fotos", "Editor de fotos",
                         enabled=False, note="PRÓXIMAMENTE")

        video.clicked.connect(self._pick)
        video.setFocus()

        row = QHBoxLayout()
        row.setSpacing(18)
        row.addStretch(1)
        row.addWidget(video)
        row.addWidget(fotos)
        row.addStretch(1)
        return row

    def _footer(self, version: str) -> QWidget:
        label = QLabel(f"v{version}" if version else "")
        label.setStyleSheet("color: #4f555d; font-size: 10px;")
        label.setAlignment(Qt.AlignCenter)
        return label

    def _pick(self, mode: str) -> None:
        self.choice = mode
        self.accept()
