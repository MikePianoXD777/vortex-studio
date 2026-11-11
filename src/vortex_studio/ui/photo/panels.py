"""Los paneles de la barra izquierda: Diseño, Subir, Texto, Elementos y Dibujar."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo import templates
from vortex_studio.photo.document import KIND_SHAPE, Layer, Transform
from vortex_studio.photo.render import to_qimage
from vortex_studio.photo.shapes import render_shape
from vortex_studio.ui import theme
from vortex_studio.ui.photo.controls import (
    MORADO,
    PALETA,
    ColorButton,
    IconBtn,
    PSlider,
    heading,
    muted,
)
from vortex_studio.ui.photo.session import SHAPE_NAMES, PhotoSession


def scrolled(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setWidget(inner)
    return sa


def _page(*widgets, margins=(14, 14, 14, 14)) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(8)
    for x in widgets:
        if x is None:
            lay.addStretch(1)
        elif isinstance(x, QWidget):
            lay.addWidget(x)
        else:
            lay.addLayout(x)
    return w


def _subtitle(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setStyleSheet(f"color:{theme.MUY_TENUE}; font-size:10px; font-weight:600; "
                      "letter-spacing:1.5px; padding-top:8px;")
    return lab


class DesignPanel(QWidget):
    """Tamaños y color de fondo."""

    custom_size_requested = Signal()

    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        self.info = muted("")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        cuerpo = QWidget()
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(6)
        v.addWidget(heading("Diseño"))
        v.addWidget(self.info)

        v.addWidget(_subtitle("Color de fondo"))
        grid = QGridLayout()
        grid.setSpacing(5)
        self.bg_swatches: dict[str, QToolButton] = {}
        for i, hexa in enumerate(PALETA):
            b = QToolButton()
            b.setFixedSize(30, 30)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(hexa)
            b.setStyleSheet(f"QToolButton {{ background:{hexa}; border:2px solid {theme.BORDE_FUERTE}; "
                            "border-radius:15px; }")
            b.clicked.connect(lambda _=False, h=hexa: self.s.set_background(h))
            self.bg_swatches[hexa] = b
            grid.addWidget(b, i // 6, i % 6)
        v.addLayout(grid)
        fila = QHBoxLayout()
        self.bg_custom = ColorButton(self.s.doc.background, "Otro color de fondo")
        self.bg_custom.changed.connect(self.s.set_background)
        self.btn_transparent = QPushButton("Transparente")
        self.btn_transparent.clicked.connect(lambda: self.s.set_background(None))
        fila.addWidget(self.bg_custom)
        fila.addWidget(self.btn_transparent, 1)
        v.addLayout(fila)

        v.addWidget(_subtitle("Tamaño"))
        self.size_buttons: list[tuple[QPushButton, int, int]] = []
        grupo = None
        for g, nombre, w, h in templates.SIZES:
            if g != grupo:
                grupo = g
                lab = QLabel(g)
                lab.setStyleSheet(f"color:{theme.TENUE}; font-size:12px; padding-top:6px;")
                v.addWidget(lab)
            b = QPushButton(f"{nombre}    {w} × {h}")
            b.setStyleSheet("text-align:left; padding:8px 12px;")
            b.setToolTip(b.text())
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)   # nombres largos no ensanchan el panel
            b.clicked.connect(lambda _=False, a=w, c=h: self.s.resize_document(a, c))
            v.addWidget(b)
            self.size_buttons.append((b, w, h))
        custom = QPushButton("Tamaño personalizado…")
        custom.clicked.connect(self.custom_size_requested)
        v.addSpacing(6)
        v.addWidget(custom)
        v.addStretch(1)
        lay.addWidget(scrolled(cuerpo))
        session.committed.connect(lambda _l: self.refresh())
        session.document_replaced.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        d = self.s.doc
        self.info.setText(f"Ahora: {d.width} × {d.height} px")
        self.bg_custom.set_color(d.background)
        for b, w, h in self.size_buttons:
            b.setChecked(False)


class UploadPanel(QWidget):
    pick_requested = Signal()

    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Subir"))
        self.btn = QPushButton("Subir imágenes")
        self.btn.setObjectName("primario")
        self.btn.clicked.connect(self.pick_requested)
        lay.addWidget(self.btn)
        lay.addWidget(muted("También puedes arrastrar archivos hasta el lienzo o pegar con Ctrl+V."))
        lay.addWidget(_subtitle("Subidas en esta sesión"))
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        lay.addWidget(self.grid_host)
        lay.addStretch(1)
        self.thumb_buttons: list[QToolButton] = []
        session.committed.connect(lambda _l: self.refresh())
        session.document_replaced.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
                it.widget().deleteLater()
        self.thumb_buttons = []
        for i, (name, mini, asset) in enumerate(self.s.uploads):
            if not self.s.store.has(asset):
                continue
            b = QToolButton()
            b.setFixedSize(84, 84)
            b.setIcon(QIcon(QPixmap.fromImage(to_qimage(mini))))
            b.setIconSize(QSize(76, 76))
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QToolButton {{ background:{theme.CAMPO}; border:1px solid {theme.BORDE}; "
                            f"border-radius:8px; }} QToolButton:hover {{ border-color:{MORADO}; }}")
            b.clicked.connect(lambda _=False, a=asset, n=name: self._again(a, n))
            self.grid.addWidget(b, len(self.thumb_buttons) // 3, len(self.thumb_buttons) % 3)
            self.thumb_buttons.append(b)

    def _again(self, asset: str, name: str) -> None:
        if self.s.store.has(asset):
            self.s.add_image(self.s.store.get(asset))


class TextPanel(QWidget):
    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Texto"))
        self.buttons: list[QPushButton] = []
        tams = (22, 16, 13)
        for i, (nombre, _capa) in enumerate(templates.text_presets()):
            b = QPushButton(nombre)
            b.setMinimumHeight(54 if i == 0 else 46)
            f = QFont()
            f.setPixelSize(tams[min(i, 2)])
            f.setBold(i < 2)
            b.setFont(f)
            b.setStyleSheet("text-align:left; padding:8px 14px;")
            b.clicked.connect(lambda _=False, k=i: self.s.add_text(k))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addWidget(muted("Doble clic en un texto del lienzo para escribir. "
                            "Arrástralo por las esquinas para cambiar su tamaño."))
        lay.addStretch(1)


class ElementsPanel(QWidget):
    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Elementos"))
        lay.addWidget(_subtitle("Formas"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.buttons: dict[str, QToolButton] = {}
        for i, (kind, nombre) in enumerate(SHAPE_NAMES.items()):
            b = QToolButton()
            b.setFixedSize(84, 84)
            b.setToolTip(nombre)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(QIcon(self._preview(kind)))
            b.setIconSize(QSize(56, 56))
            b.setStyleSheet(f"QToolButton {{ background:{theme.CAMPO}; border:1px solid {theme.BORDE}; "
                            f"border-radius:10px; }} QToolButton:hover {{ border-color:{MORADO}; }}")
            b.clicked.connect(lambda _=False, k=kind: self.s.add_shape(k))
            grid.addWidget(b, i // 3, i % 3)
            self.buttons[kind] = b
        lay.addLayout(grid)
        lay.addStretch(1)

    @staticmethod
    def _preview(kind: str) -> QPixmap:
        """La forma pequeña, dibujada por el mismo motor que la dibuja en el lienzo."""
        t = Transform(0, 0, 56, 56)
        capa = Layer(kind=KIND_SHAPE, shape=kind, fill="#b9a6ff", transform=t)
        if kind in ("line", "arrow"):
            capa.transform = Transform(0, 0, 56, 20)
            capa.fill, capa.stroke, capa.stroke_width = None, "#b9a6ff", 5
        try:
            return QPixmap.fromImage(to_qimage(render_shape(capa, 1.0)))
        except Exception:
            return QPixmap()


class DrawPanel(QWidget):
    def __init__(self, session: PhotoSession) -> None:
        super().__init__()
        self.s = session
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(heading("Dibujar"))
        fila = QHBoxLayout()
        self.btn_brush = IconBtn("pincel", "Pincel (B)", 40, checkable=True)
        self.btn_erase = IconBtn("borrador", "Borrador (E)", 40, checkable=True)
        self.btn_brush.clicked.connect(lambda: self._toggle("brush"))
        self.btn_erase.clicked.connect(lambda: self._toggle("erase"))
        fila.addWidget(self.btn_brush)
        fila.addWidget(self.btn_erase)
        fila.addStretch(1)
        lay.addLayout(fila)
        b = session.brush
        self.size = PSlider("Tamaño", 1, 300, b.size)
        self.hard = PSlider("Dureza", 0, 100, round(b.hardness * 100), suffix="%")
        self.opac = PSlider("Opacidad", 1, 100, round(b.opacity * 100), suffix="%")
        self.size.live.connect(lambda v: setattr(self.s.brush, "size", float(v)))
        self.hard.live.connect(lambda v: setattr(self.s.brush, "hardness", v / 100))
        self.opac.live.connect(lambda v: setattr(self.s.brush, "opacity", v / 100))
        for w in (self.size, self.hard, self.opac):
            lay.addWidget(w)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Color"))
        self.color = ColorButton(b.color, "Color del pincel")
        self.color.changed.connect(lambda c: setattr(self.s.brush, "color", c or "#000000"))
        fila.addWidget(self.color)
        fila.addStretch(1)
        lay.addLayout(fila)
        lay.addWidget(muted("Pinta sobre una capa de dibujo que se crea sola, encima de tu foto. "
                            "El borrador borra sobre la foto o dibujo que tengas seleccionado. "
                            "Esc para volver a mover."))
        lay.addStretch(1)
        session.tool_changed.connect(self._sync)
        self._sync(session.tool)

    def _toggle(self, tool: str) -> None:
        self.s.set_tool("move" if self.s.tool == tool else tool)
        self._sync(self.s.tool)

    def _sync(self, tool: str) -> None:
        self.btn_brush.setChecked(tool == "brush")
        self.btn_erase.setChecked(tool == "erase")
