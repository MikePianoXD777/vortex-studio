"""La barra de arriba: marca, menús, datos de la secuencia y Exportar.

Sustituye a la barra de menús de siempre. Exportar va a la vista, en blanco,
porque es el final de todo trabajo y antes había que buscarlo en Archivo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenuBar, QPushButton, QWidget

from vortex_studio.ui import theme


class _Logo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(20, 20)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACENTO))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)
        p.end()


class TopBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("barraSuperior")

        self.logo = _Logo()
        self.name = QLabel("Vortex Studio")
        self.name.setStyleSheet(f"color:{theme.TEXTO}; font-size:13px; font-weight:600;")

        self.menu = QMenuBar()
        self.menu.setNativeMenuBar(False)

        self.info = QLabel("")
        self.info.setStyleSheet(
            f"color:{theme.MUY_TENUE}; font-family:{theme.MONO}; font-size:11px;")

        self.export_button = QPushButton("Exportar")
        self.export_button.setObjectName("primario")
        self.export_button.setCursor(Qt.PointingHandCursor)
        self.export_button.setFocusPolicy(Qt.NoFocus)
        self.export_button.setToolTip("Exportar video  ·  Ctrl+E")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 8)
        layout.setSpacing(10)
        layout.addWidget(self.logo)
        layout.addWidget(self.name)
        layout.addSpacing(8)
        layout.addWidget(self.menu)
        layout.addStretch(1)
        layout.addWidget(self.info)
        layout.addSpacing(8)
        layout.addWidget(self.export_button)
