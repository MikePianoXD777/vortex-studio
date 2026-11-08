"""Ventanitas de Vortex Photo: exportar, nuevo diseño, cambiar tamaño, editar en lote."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.photo import io as photo_io
from vortex_studio.photo import templates
from vortex_studio.photo.document import Adjustments, Filter
from vortex_studio.photo.filters import FILTERS
from vortex_studio.ui import theme
from vortex_studio.ui.photo.controls import BAR_SPIN_STYLE, PSlider, Segmented, heading, muted
from vortex_studio.ui.photo.session import PhotoSession


class ExportPopup(QFrame):
    """El panel de «Exportar»: formato, calidad, tamaño y fondo transparente."""

    requested = Signal(dict)

    def __init__(self, session: PhotoSession, parent=None) -> None:
        super().__init__(parent, Qt.Popup)
        self.s = session
        self.setObjectName("expopup")
        self.setStyleSheet(f"#expopup {{ background:{theme.CAMPO}; border:1px solid {theme.BORDE_FUERTE}; "
                           "border-radius:12px; }")
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(heading("Exportar"))
        lay.addWidget(muted("Formato"))
        self.fmt = Segmented([(f, f) for f in photo_io.EXPORT_FORMATS], "PNG")
        self.fmt.changed.connect(self._sync)
        lay.addWidget(self.fmt)
        self.quality = PSlider("Calidad", 10, 100, 92, suffix="%")
        self.quality.live.connect(lambda _v: self._sync())
        lay.addWidget(self.quality)
        lay.addWidget(muted("Tamaño"))
        self.size = Segmented([(0.5, "×0,5"), (1.0, "×1"), (2.0, "×2")], 1.0)
        self.size.changed.connect(self._sync)
        lay.addWidget(self.size)
        self.dims = muted("")
        lay.addWidget(self.dims)
        self.transparent = QCheckBox("Fondo transparente")
        self.transparent.toggled.connect(self._sync)
        lay.addWidget(self.transparent)
        self.btn = QPushButton("Exportar")
        self.btn.setObjectName("primario")
        self.btn.clicked.connect(self._go)
        lay.addWidget(self.btn)
        self._sync()

    def options(self) -> dict:
        fmt = self.fmt.value()
        return {"fmt": fmt, "quality": int(self.quality.value()), "scale": float(self.size.value()),
                "transparent": bool(self.transparent.isChecked() and fmt != "JPG")}

    def _sync(self, *_a) -> None:
        fmt = self.fmt.value()
        self.quality.setEnabled(fmt != "PNG")
        self.transparent.setEnabled(fmt != "JPG")
        if fmt == "JPG":
            self.transparent.setChecked(False)
        d, k = self.s.doc, float(self.size.value())
        self.dims.setText(f"{max(1, round(d.width * k))} × {max(1, round(d.height * k))} px")

    def show_at(self, anchor: QWidget) -> None:
        self._sync()
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(anchor.width() - self.width(), anchor.height() + 6))
        self.move(pos)
        self.show()

    def _go(self) -> None:
        self.hide()
        self.requested.emit(self.options())


class _Worker(QThread):
    """Corre una tarea larga (exportar) fuera del hilo de la interfaz."""

    done = Signal(object)       # None si salió bien, o el error
    step = Signal(int, int)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            self.fn(self.step.emit)
            self.done.emit(None)
        except Exception as error:      # el aviso lo muestra la ventana
            self.done.emit(error)


class SizePicker(QWidget):
    """Ancho × alto, con candado de proporción."""

    changed = Signal(int, int)

    def __init__(self, w: int, h: int) -> None:
        super().__init__()
        self._ratio = w / h
        self._busy = False
        self.w = QSpinBox()
        self.h = QSpinBox()
        for s, v in ((self.w, w), (self.h, h)):
            s.setRange(1, 16000)
            s.setValue(v)
            s.setSuffix(" px")
            s.setKeyboardTracking(False)
            s.setButtonSymbols(QSpinBox.NoButtons)
            s.setStyleSheet(BAR_SPIN_STYLE)
            s.setAlignment(Qt.AlignCenter)
            s.setFixedHeight(32)
        self.lock = QCheckBox("Mantener proporción")
        self.lock.setChecked(True)
        self.w.valueChanged.connect(self._w)
        self.h.valueChanged.connect(self._h)
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(QLabel("Ancho"))
        fila.addWidget(self.w, 1)
        fila.addWidget(QLabel("Alto"))
        fila.addWidget(self.h, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(fila)
        lay.addWidget(self.lock)

    def set_size(self, w: int, h: int) -> None:
        self._busy = True
        self.w.setValue(w)
        self.h.setValue(h)
        self._ratio = w / max(1, h)
        self._busy = False

    def _w(self, v: int) -> None:
        if self._busy:
            return
        if self.lock.isChecked():
            self._busy = True
            self.h.setValue(max(1, round(v / self._ratio)))
            self._busy = False
        else:
            self._ratio = v / max(1, self.h.value())
        self.changed.emit(self.w.value(), self.h.value())

    def _h(self, v: int) -> None:
        if self._busy:
            return
        if self.lock.isChecked():
            self._busy = True
            self.w.setValue(max(1, round(v * self._ratio)))
            self._busy = False
        else:
            self._ratio = self.w.value() / max(1, v)
        self.changed.emit(self.w.value(), self.h.value())

    def values(self) -> tuple[int, int]:
        return self.w.value(), self.h.value()


class NewDesignDialog(QDialog):
    """Elegir un tamaño de la lista o escribir uno propio."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo diseño")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(heading("Nuevo diseño"))
        self.name = QLineEdit("Diseño sin título")
        lay.addWidget(self.name)
        self.list = QListWidget()
        self.list.setMinimumHeight(190)
        for g, nombre, w, h in templates.SIZES:
            it = QListWidgetItem(f"{nombre}    {w} × {h} px    ·    {g}")
            it.setData(Qt.UserRole, (w, h))
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.list.currentItemChanged.connect(self._from_list)
        lay.addWidget(self.list)
        lay.addWidget(muted("O un tamaño personalizado"))
        self.custom = SizePicker(*self.list.item(0).data(Qt.UserRole))
        self.custom.lock.setChecked(False)
        lay.addWidget(self.custom)
        fila = QHBoxLayout()
        fila.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Crear diseño")
        ok.setObjectName("primario")
        ok.clicked.connect(self.accept)
        fila.addWidget(cancel)
        fila.addWidget(ok)
        lay.addLayout(fila)

    def _from_list(self, cur, _prev) -> None:
        if cur is not None:
            self.custom.set_size(*cur.data(Qt.UserRole))

    def values(self) -> tuple[int, int, str]:
        w, h = self.custom.values()
        return w, h, self.name.text().strip() or "Diseño sin título"


class ResizeDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cambiar tamaño")
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(heading("Cambiar tamaño"))
        self.picker = SizePicker(width, height)
        lay.addWidget(self.picker)
        self.adapt = QCheckBox("Adaptar el contenido al nuevo tamaño")
        self.adapt.setChecked(True)
        lay.addWidget(self.adapt)
        fila = QHBoxLayout()
        fila.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Cambiar tamaño")
        ok.setObjectName("primario")
        ok.clicked.connect(self.accept)
        fila.addWidget(cancel)
        fila.addWidget(ok)
        lay.addLayout(fila)

    def values(self) -> tuple[int, int, bool]:
        w, h = self.picker.values()
        return w, h, self.adapt.isChecked()


class BatchDialog(QDialog):
    """Editar en lote: las mismas correcciones a muchas fotos."""

    def __init__(self, session: PhotoSession, parent=None) -> None:
        super().__init__(parent)
        self.s = session
        self.paths: list[str] = []
        self.out_dir = ""
        self.worker: _Worker | None = None
        self.setWindowTitle("Editar en lote")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(heading("Editar en lote"))
        lay.addWidget(muted("Aplica los mismos ajustes a varias fotos y las guarda en una carpeta, "
                            "sin tocar las originales."))
        self.files = QListWidget()
        self.files.setMinimumHeight(120)
        lay.addWidget(self.files)
        self.btn_add = QPushButton("Agregar fotos…")
        lay.addWidget(self.btn_add)
        self.use_current = QCheckBox("Usar los ajustes y el filtro de la foto seleccionada")
        capa = session.single()
        self.use_current.setEnabled(capa is not None and capa.kind == "image")
        self.use_current.setChecked(self.use_current.isEnabled())
        self.use_current.toggled.connect(self._sync)
        lay.addWidget(self.use_current)
        self.filter = QComboBox()
        self.filter.addItem("Sin filtro", "")
        for f in FILTERS.values():
            self.filter.addItem(f.name, f.id)
        self.exposure = PSlider("Exposición", -3, 3, 0, div=100)
        self.contrast = PSlider("Contraste", -100, 100, 0)
        self.saturation = PSlider("Saturación", -100, 100, 0)
        for w in (self.filter, self.exposure, self.contrast, self.saturation):
            lay.addWidget(w)
        self.fmt = Segmented([("JPG", "JPG"), ("PNG", "PNG"), ("WEBP", "WEBP")], "JPG")
        lay.addWidget(self.fmt)
        self.quality = PSlider("Calidad", 10, 100, 92, suffix="%")
        lay.addWidget(self.quality)
        self.btn_dir = QPushButton("Carpeta de salida…")
        self.dir_label = muted("Sin elegir")
        lay.addWidget(self.btn_dir)
        lay.addWidget(self.dir_label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        fila = QHBoxLayout()
        fila.addStretch(1)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.reject)
        self.btn_run = QPushButton("Procesar")
        self.btn_run.setObjectName("primario")
        self.btn_run.clicked.connect(self.run)
        fila.addWidget(self.btn_close)
        fila.addWidget(self.btn_run)
        lay.addLayout(fila)
        self.result: list[Path] = []
        self.error: Exception | None = None
        self._sync()

    def _sync(self, *_a) -> None:
        manual = not self.use_current.isChecked()
        for w in (self.filter, self.exposure, self.contrast, self.saturation):
            w.setEnabled(manual)

    def add_paths(self, paths: list[str]) -> None:
        for p in paths:
            if p not in self.paths:
                self.paths.append(p)
                self.files.addItem(Path(p).name)

    def set_out_dir(self, d: str) -> None:
        self.out_dir = d
        self.dir_label.setText(d or "Sin elegir")

    def settings(self) -> tuple[Adjustments, Filter]:
        capa = self.s.single()
        if self.use_current.isChecked() and capa is not None:
            return capa.adjustments, capa.filter
        adj = Adjustments(exposure=self.exposure.value() * 100, contrast=self.contrast.value(),
                          saturation=self.saturation.value())
        fid = self.filter.currentData() or ""
        return adj, Filter(fid, 100.0) if fid else Filter()

    def can_run(self) -> bool:
        return bool(self.paths) and bool(self.out_dir) and self.worker is None

    def run(self) -> bool:
        if not self.can_run():
            return False
        adj, flt = self.settings()
        paths, out, fmt, q = list(self.paths), self.out_dir, self.fmt.value(), int(self.quality.value())
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)

        def tarea(avance):
            self.result = photo_io.export_batch(paths, adj, flt, out, fmt, q, progress=avance)

        self.worker = _Worker(tarea, self)
        self.worker.step.connect(lambda i, n: self.progress.setValue(i))
        self.worker.done.connect(self._finished)
        self.worker.start()
        return True

    def _finished(self, error) -> None:
        self.error = error
        self.worker = None
        self.btn_run.setEnabled(True)
        self.progress.setVisible(False)
        if error is None:
            self.dir_label.setText(f"Listo: {len(self.result)} fotos en {self.out_dir}")
        else:
            self.dir_label.setText(f"No se pudo terminar: {error}")
