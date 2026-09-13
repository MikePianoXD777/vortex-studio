"""La fila de herramientas sobre el timeline.

En la 0.6 las herramientas solo vivían en el menú Editar y en el teclado: no
había nada a la vista que dijera "esto es un editor". El diseño de la beta
las pone como píldoras arriba del timeline —Selección, Cortar y Dividir—, y
aquí se suman con el mismo estilo Deslizar, Imán y Enlace.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QToolButton, QWidget

from vortex_studio.ui import theme
from vortex_studio.ui.timeline import TOOL_RAZOR, TOOL_SELECT, TOOL_SLIP
from vortex_studio.ui.widgets import make_icon

TOOLS = (
    (TOOL_SELECT, "Selección", "seleccion", "Seleccionar y mover  ·  V"),
    (TOOL_RAZOR, "Cortar", "navaja", "Navaja: el clic corta el clip ahí  ·  C"),
)


class TimelineTools(QWidget):
    tool_chosen = Signal(str)
    split_requested = Signal()
    snap_toggled = Signal(bool)
    link_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(theme.PILL_STYLE)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.tool_buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(2)

        for tool, texto, icono, tip in TOOLS:
            layout.addWidget(self._tool(tool, texto, icono, tip))

        self.split_button = self._pill("Dividir", "dividir",
                                       "Dividir lo seleccionado en el playhead  ·  S")
        self.split_button.clicked.connect(self.split_requested.emit)
        layout.addWidget(self.split_button)

        layout.addWidget(self._tool(TOOL_SLIP, "Deslizar", "deslizar",
                                    "Deslizar (slip): mueve el contenido sin mover el clip  ·  Y"))

        separador = QWidget()
        separador.setFixedSize(1, 16)
        separador.setStyleSheet(f"background:{theme.BORDE_FUERTE};")
        layout.addSpacing(6)
        layout.addWidget(separador)
        layout.addSpacing(6)

        self.snap_button = self._pill("Imán", "iman", "Imán: pegar a cortes, marcas y playhead")
        self.snap_button.setCheckable(True)
        self.snap_button.setChecked(True)
        self.snap_button.toggled.connect(self.snap_toggled.emit)
        layout.addWidget(self.snap_button)

        self.link_button = self._pill("Enlace", "enlace",
                                      "Selección enlazada: video y su audio se mueven juntos")
        self.link_button.setCheckable(True)
        self.link_button.setChecked(True)
        self.link_button.toggled.connect(self.link_toggled.emit)
        layout.addWidget(self.link_button)

        layout.addStretch(1)
        self.count = QLabel("")
        self.count.setStyleSheet(
            f"color:{theme.MUY_TENUE}; font-family:{theme.MONO}; font-size:11px;")
        layout.addWidget(self.count)

        self._group.idClicked.connect(self._chosen)
        self.set_tool(TOOL_SELECT)

    def _pill(self, texto: str, icono: str, tip: str) -> QToolButton:
        boton = QToolButton()
        boton.setText(texto)
        boton.setIcon(make_icon(icono, theme.TENUE, 14))
        boton.setIconSize(QSize(14, 14))
        boton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        boton.setToolTip(tip)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setFocusPolicy(Qt.NoFocus)
        return boton

    def _tool(self, tool: str, texto: str, icono: str, tip: str) -> QToolButton:
        boton = self._pill(texto, icono, tip)
        boton.setCheckable(True)
        self._group.addButton(boton, len(self.tool_buttons))
        self.tool_buttons[tool] = boton
        return boton

    def _chosen(self, indice: int) -> None:
        self.tool_chosen.emit(list(self.tool_buttons)[indice])

    def set_tool(self, tool: str) -> None:
        boton = self.tool_buttons.get(tool)
        if boton is not None and not boton.isChecked():
            boton.setChecked(True)

    def set_count(self, piezas: int) -> None:
        self.count.setText(f"{piezas} elemento{'s' if piezas != 1 else ''}")
