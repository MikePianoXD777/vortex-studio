"""Diálogos chicos: marcador y pegar atributos.

Cada uno expone sus valores como métodos para que la ventana —y las
pruebas— los usen sin tener que abrirlos: un diálogo modal en una prueba se
queda esperando un clic que nunca llega.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from vortex_studio.model import ATTRIBUTES, MARKER_COLORS, Clip


def _swatch(color: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class MarkerDialog(QDialog):
    """Nombre, nota y color de un marcador, como el de Premiere pero corto."""

    DELETE = 2          # código de salida de "Borrar marcador"

    def __init__(self, parent, marker, owner_name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Marcador del clip" if owner_name else "Marcador")
        self.setMinimumWidth(340)

        self._name = QLineEdit(marker.name)
        self._name.setPlaceholderText("Por ejemplo: corte, entra música…")
        self._note = QPlainTextEdit(marker.note)
        self._note.setPlaceholderText("Una nota para después")
        self._note.setMaximumHeight(90)

        self._color = QComboBox()
        for nombre, valor in MARKER_COLORS.items():
            self._color.addItem(_swatch(valor), nombre, valor)
        indice = self._color.findData(marker.color)
        if indice < 0:
            self._color.addItem(_swatch(marker.color), marker.color, marker.color)
            indice = self._color.count() - 1
        self._color.setCurrentIndex(indice)

        form = QFormLayout()
        if owner_name:
            form.addRow("Clip:", QLabel(owner_name))
        form.addRow("Nombre:", self._name)
        form.addRow("Nota:", self._note)
        form.addRow("Color:", self._color)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        borrar = QPushButton("Borrar marcador")
        borrar.clicked.connect(lambda: self.done(self.DELETE))
        botones.addButton(borrar, QDialogButtonBox.DestructiveRole)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(botones)
        self._name.setFocus()

    def set_values(self, name: str | None = None, note: str | None = None,
                   color: str | None = None) -> None:
        if name is not None:
            self._name.setText(name)
        if note is not None:
            self._note.setPlainText(note)
        if color is not None:
            indice = self._color.findData(color)
            if indice < 0:
                indice = self._color.findText(color)
            if indice >= 0:
                self._color.setCurrentIndex(indice)

    def values(self) -> dict:
        return {"name": self._name.text().strip(),
                "note": self._note.toPlainText().strip(),
                "color": self._color.currentData()}


class PasteAttributesDialog(QDialog):
    """Qué ajustes llevarse del clip copiado. Lo que no aplica se apaga."""

    def __init__(self, parent, source) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pegar atributos")
        self.setMinimumWidth(300)

        self._boxes: dict[str, QCheckBox] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Del clip «{source.name}»:"))
        for nombre in ATTRIBUTES:
            caja = QCheckBox(nombre)
            aplica = self.applies(source, nombre)
            caja.setEnabled(aplica)
            caja.setChecked(aplica and nombre != "Velocidad")
            layout.addWidget(caja)
            self._boxes[nombre] = caja

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Pegar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    @staticmethod
    def applies(source, nombre: str) -> bool:
        if nombre == "Transformación":
            return hasattr(source, "transform")
        if nombre in ("Color", "Velocidad", "Volumen", "Efectos"):
            return isinstance(source, Clip)
        if nombre == "Máscara y fusión":
            return hasattr(source, "mask")
        return hasattr(source, "fade_in")

    def set_checked(self, nombre: str, valor: bool) -> None:
        self._boxes[nombre].setChecked(valor)

    def groups(self) -> tuple[str, ...]:
        return tuple(n for n, c in self._boxes.items() if c.isChecked() and c.isEnabled())
