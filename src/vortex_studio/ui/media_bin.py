"""El panel de medios: lo importado, con miniatura, y un buscador.

Hasta la 0.3 importar un archivo lo ponía directo en el timeline y ahí se
acababa: no había dónde ver qué se había traído, ni forma de poner otra vez
el mismo video sin volver a buscarlo en el disco. Aquí vive todo lo que el
proyecto conoce —el caché de sondeos del proyecto—, con su miniatura, y de
aquí se arrastra al timeline o se agrega con doble clic en el playhead.

Las miniaturas se sacan en hilos del pool de Qt y se guardan en disco: el
panel nunca decodifica.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QRunnable, QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.media.thumbnails import extract, thumbnail_path
from vortex_studio.model.media import AUDIO, IMAGE, VIDEO
from vortex_studio.ui.compositor import frame_to_image
from vortex_studio.ui.timeline import MEDIA_MIME

ICON = QSize(128, 72)
KINDS = {"Todo": None, "Video": VIDEO, "Audio": AUDIO, "Imágenes": IMAGE}
PATH_ROLE = Qt.UserRole
KIND_ROLE = Qt.UserRole + 1


def _plain(texto: str) -> str:
    """Sin acentos y en minúsculas: buscar «cancion» encuentra «Canción»."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _duration(segundos: float) -> str:
    segundos = max(0, int(round(segundos)))
    return f"{segundos // 60}:{segundos % 60:02d}"


def placeholder(kind: str) -> QPixmap:
    """El cuadro que se ve mientras llega la miniatura, o siempre en un audio."""
    pixmap = QPixmap(ICON)
    pixmap.fill(QColor("#24282d"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#6f9b84" if kind == AUDIO else "#5d636b"))
    painter.setFont(QFont("", 22))
    painter.drawText(pixmap.rect(), Qt.AlignCenter,
                     {AUDIO: "♪", IMAGE: "▣"}.get(kind, "▶"))
    painter.end()
    return pixmap


class _Aviso(QObject):
    listo = Signal(object, object)       # ruta, QImage


class _Miniatura(QRunnable):
    def __init__(self, path: Path, kind: str, aviso: _Aviso) -> None:
        super().__init__()
        self.path, self.kind, self.aviso = path, kind, aviso

    @Slot()
    def run(self) -> None:
        imagen = None
        guardada = thumbnail_path(self.path)
        try:
            if guardada is not None and guardada.exists():
                imagen = QImage(str(guardada))
            elif self.kind == IMAGE:
                imagen = QImage(str(self.path)).scaledToWidth(192, Qt.SmoothTransformation)
            else:
                frame = extract(self.path)
                if frame is not None:
                    imagen = frame_to_image(frame).copy()     # dueña de sus bytes
            if imagen is not None and not imagen.isNull() and guardada is not None \
                    and not guardada.exists():
                guardada.parent.mkdir(parents=True, exist_ok=True)
                imagen.save(str(guardada))
        except Exception:
            imagen = None
        try:
            self.aviso.listo.emit(self.path, imagen)
        except RuntimeError:
            pass        # el panel ya se cerró


class _BinList(QListWidget):
    """La lista de medios. Arrastrar lleva las rutas al timeline."""

    def mimeData(self, items):
        datos = QMimeData()
        rutas = "\n".join(str(i.data(PATH_ROLE)) for i in items)
        datos.setData(MEDIA_MIME, rutas.encode("utf-8"))
        datos.setText(rutas)
        return datos

    def mimeTypes(self):
        return [MEDIA_MIME]


class MediaBin(QDockWidget):
    import_requested = Signal()
    insert_requested = Signal(object)       # ruta

    def __init__(self) -> None:
        super().__init__("Medios")
        self.setObjectName("panel_de_medios")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                         | QDockWidget.DockWidgetClosable)

        self._thumbs: dict[Path, QImage] = {}
        self._working: set[Path] = set()
        self._aviso = _Aviso()
        self._aviso.listo.connect(self._thumbnail_ready)
        self._pool = QThreadPool.globalInstance()
        self._proxies: set[Path] = set()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)

        self.kind = QComboBox()
        self.kind.addItems(KINDS)
        self.kind.currentTextChanged.connect(self._apply_filter)

        self.list = _BinList()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(ICON)
        self.list.setGridSize(QSize(ICON.width() + 16, ICON.height() + 40))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QListWidget.DragOnly)
        self.list.itemDoubleClicked.connect(
            lambda item: self.insert_requested.emit(Path(item.data(PATH_ROLE))))

        self._count = QLabel()
        self._count.setStyleSheet("color:#6f757e; font-size:10px;")

        importar = QPushButton("Importar…")
        importar.clicked.connect(self.import_requested.emit)
        self.insert_button = QPushButton("Agregar al timeline")
        self.insert_button.setToolTip("En el playhead. También puedes arrastrarlo.")
        self.insert_button.clicked.connect(self._insert_selected)

        filtros = QHBoxLayout()
        filtros.addWidget(self.search, 1)
        filtros.addWidget(self.kind)
        botones = QHBoxLayout()
        botones.addWidget(importar)
        botones.addWidget(self.insert_button)

        cuerpo = QWidget()
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)
        layout.addLayout(filtros)
        layout.addWidget(self.list, 1)
        layout.addWidget(self._count)
        layout.addLayout(botones)
        self.setWidget(cuerpo)
        self._update_count()

    # --- contenido --------------------------------------------------------

    def set_library(self, library: dict) -> None:
        """Muestra lo que conoce el proyecto, en orden de nombre."""
        elegidas = {self.path_of(i) for i in self.list.selectedItems()}
        self.list.clear()
        for info in sorted(library.values(), key=lambda i: Path(i.path).name.lower()):
            self._add(info, Path(info.path) in elegidas)
        self._apply_filter()

    def _add(self, info, selected: bool) -> None:
        path = Path(info.path)
        item = QListWidgetItem(path.name)
        item.setData(PATH_ROLE, str(path))
        item.setData(KIND_ROLE, info.kind)
        item.setToolTip(self._describe(info))
        item.setSizeHint(self.list.gridSize())
        imagen = self._thumbs.get(path)
        item.setIcon(QIcon(QPixmap.fromImage(imagen)) if imagen is not None
                     else QIcon(placeholder(info.kind)))
        self.list.addItem(item)
        item.setSelected(selected)
        if imagen is None and info.kind != AUDIO and path not in self._working \
                and path.exists():
            self._working.add(path)
            self._pool.start(_Miniatura(path, info.kind, self._aviso))

    def _describe(self, info) -> str:
        partes = [Path(info.path).name]
        if info.kind == VIDEO:
            partes.append(f"{info.width}×{info.height}  ·  {info.fps:g} fps  ·  "
                          f"{_duration(info.duration)}")
            partes.append(f"{info.video_codec}" + (f" + {info.audio_codec}"
                                                    if info.audio_codec else "  ·  sin audio"))
        elif info.kind == AUDIO:
            partes.append(f"{_duration(info.duration)}  ·  {info.audio_codec}  ·  "
                          f"{info.channels} canal{'es' if info.channels != 1 else ''}")
        else:
            partes.append(f"{info.width}×{info.height}")
        if Path(info.path) in self._proxies:
            partes.append("Con proxy de 540p")
        if not Path(info.path).exists():
            partes.append("⚠ El archivo no está en su lugar")
        return "\n".join(partes)

    def set_proxies(self, originales) -> None:
        self._proxies = {Path(p) for p in originales}

    def _thumbnail_ready(self, path, imagen) -> None:
        path = Path(path)
        self._working.discard(path)
        if imagen is None or imagen.isNull():
            return
        self._thumbs[path] = imagen
        for i in range(self.list.count()):
            item = self.list.item(i)
            if Path(item.data(PATH_ROLE)) == path:
                item.setIcon(QIcon(QPixmap.fromImage(imagen)))

    def wait_thumbnails(self, timeout_ms: int = 30000) -> bool:
        """Solo para las pruebas."""
        return self._pool.waitForDone(timeout_ms)

    # --- buscar -----------------------------------------------------------

    def _apply_filter(self, *_):
        texto = _plain(self.search.text().strip())
        clase = KINDS.get(self.kind.currentText())
        for i in range(self.list.count()):
            item = self.list.item(i)
            coincide = (not texto or texto in _plain(item.text())) and \
                (clase is None or item.data(KIND_ROLE) == clase)
            item.setHidden(not coincide)
        self._update_count()

    def visible_paths(self) -> list[Path]:
        return [Path(self.list.item(i).data(PATH_ROLE)) for i in range(self.list.count())
                if not self.list.item(i).isHidden()]

    def _update_count(self) -> None:
        total = self.list.count()
        visibles = len(self.visible_paths())
        if total == 0:
            self._count.setText("Importa videos, audios o imágenes para empezar.")
        elif visibles == total:
            self._count.setText(f"{total} archivo{'s' if total != 1 else ''}")
        else:
            self._count.setText(f"{visibles} de {total}")
        self.insert_button.setEnabled(visibles > 0)

    @staticmethod
    def path_of(item) -> Path:
        return Path(item.data(PATH_ROLE))

    def _insert_selected(self) -> None:
        for item in self.list.selectedItems():
            if not item.isHidden():
                self.insert_requested.emit(self.path_of(item))

    def mime_for(self, paths) -> QMimeData:
        """Los datos que lleva un arrastre. Separado para poder probarlo."""
        items = [self.list.item(i) for i in range(self.list.count())
                 if Path(self.list.item(i).data(PATH_ROLE)) in {Path(p) for p in paths}]
        return self.list.mimeData(items)
