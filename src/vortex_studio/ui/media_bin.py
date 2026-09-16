"""El panel de medios: lo importado, con miniatura, y un buscador.

Hasta la 0.3 importar un archivo lo ponía directo en el timeline y ahí se
acababa: no había dónde ver qué se había traído, ni forma de poner otra vez
el mismo video sin volver a buscarlo en el disco. Aquí vive todo lo que el
proyecto conoce —el caché de sondeos del proyecto—, con su miniatura, y de
aquí se arrastra al timeline o se agrega con doble clic en el playhead.

Con el diseño de la beta se ve como biblioteca: pestañas Medios, Audio y
Texto, tarjetas con la duración encima de la miniatura y una tarjeta punteada
para importar al final de la cuadrícula.

Las miniaturas se sacan en hilos del pool de Qt y se guardan en disco: el
panel nunca decodifica.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from PySide6.QtCore import (
    QMimeData,
    QObject,
    QRect,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.media.thumbnails import extract, thumbnail_path
from vortex_studio.model.media import AUDIO, IMAGE, VIDEO
from vortex_studio.ui import theme
from vortex_studio.ui.compositor import frame_to_image
from vortex_studio.ui.timeline import MEDIA_MIME
from vortex_studio.ui.imagenes import load_image
from vortex_studio.ui.widgets import FlowLayout, draw_icon, make_icon, style_dock

ICON = QSize(128, 72)
CARD = QSize(90, 54)           # la miniatura; dos por fila en un panel de 250 px
GRID = QSize(CARD.width() + 8, CARD.height() + 30)
KINDS = {"Todo": None, "Video": VIDEO, "Audio": AUDIO, "Imágenes": IMAGE}
PATH_ROLE = Qt.UserRole
KIND_ROLE = Qt.UserRole + 1
DURATION_ROLE = Qt.UserRole + 2
THUMB_ROLE = Qt.UserRole + 3

# Las pestañas del diseño y el filtro de tipo que ponen.
TAB_MEDIA, TAB_AUDIO, TAB_TEXT = 0, 1, 2
TEXT_CARDS = ("Subtítulo", "Centro", "Arriba centro")    # posiciones de `ANCHORS`

BIN_STYLE = f"""
QLineEdit {{
    background: {theme.CAMPO}; color: {theme.TEXTO}; border: 1px solid {theme.BORDE};
    border-radius: 8px; padding: 6px 8px; font-size: 12px;
}}
QLineEdit:focus {{ border-color: {theme.BORDE_FUERTE}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QPushButton {{
    background: transparent; color: {theme.TENUE}; border: 1px solid {theme.BORDE};
    border-radius: 7px; padding: 3px 10px; font-size: 11px;
}}
QPushButton:hover {{ color: {theme.TEXTO}; background: {theme.PILDORA_HOVER}; }}
QPushButton:disabled {{ color: {theme.APAGADO}; }}
"""

TEXT_CARD_STYLE = f"""
QToolButton {{
    background: {theme.CAMPO}; color: {theme.TENUE}; border: 1px solid {theme.BORDE};
    border-radius: 8px; font-size: 11px; padding: 6px;
}}
QToolButton:hover {{ color: {theme.TEXTO}; border-color: {theme.BORDE_FUERTE}; }}
"""


def _plain(texto: str) -> str:
    """Sin acentos y en minúsculas: buscar «cancion» encuentra «Canción»."""
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _duration(segundos: float) -> str:
    segundos = max(0, int(round(segundos)))
    return f"{segundos // 60}:{segundos % 60:02d}"


def _mono(pixels: int) -> QFont:
    fuente = QFont()
    fuente.setFamilies(theme.MONO_FAMILIAS)
    fuente.setPixelSize(pixels)
    return fuente


def placeholder(kind: str) -> QPixmap:
    """El cuadro que se ve mientras llega la miniatura, o siempre en un audio."""
    pixmap = QPixmap(ICON)
    pixmap.fill(QColor(theme.CAMPO))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#6f9b84" if kind == AUDIO else theme.MUY_TENUE))
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
                imagen = load_image(guardada)
            elif self.kind == IMAGE:
                imagen = load_image(self.path).scaledToWidth(192, Qt.SmoothTransformation)
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


class _CardDelegate(QStyledItemDelegate):
    """Dibuja cada medio como tarjeta: miniatura redondeada, duración y nombre."""

    def sizeHint(self, option, index) -> QSize:
        return GRID

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        celda = option.rect
        miniatura = QRectF(celda.x() + (celda.width() - CARD.width()) / 2, celda.y() + 4,
                           CARD.width(), CARD.height())
        forma = QPainterPath()
        forma.addRoundedRect(miniatura, 8, 8)
        painter.fillPath(forma, QColor(theme.CAMPO))

        kind = index.data(KIND_ROLE)
        icono = index.data(Qt.DecorationRole)
        if index.data(THUMB_ROLE) and isinstance(icono, QIcon):
            pixmap = icono.pixmap(ICON)
            escalado = pixmap.scaled(miniatura.size().toSize(), Qt.KeepAspectRatioByExpanding,
                                     Qt.SmoothTransformation)
            origen = QRectF((escalado.width() - miniatura.width()) / 2,
                            (escalado.height() - miniatura.height()) / 2,
                            miniatura.width(), miniatura.height())
            painter.setClipPath(forma)
            painter.drawPixmap(miniatura, escalado, origen)
            painter.setClipping(False)
        else:
            lado = 16
            caja = QRectF(miniatura.center().x() - lado / 2, miniatura.center().y() - lado / 2,
                          lado, lado)
            draw_icon(painter, "volumen" if kind == AUDIO else "play", caja,
                      QColor("#6f9b84" if kind == AUDIO else theme.TEXTO))

        seleccionado = bool(option.state & QStyle.State_Selected)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(theme.ACENTO if seleccionado else theme.BORDE),
                            1.5 if seleccionado else 1))
        painter.drawPath(forma)

        duracion = index.data(DURATION_ROLE)
        if duracion:
            painter.setFont(_mono(9))
            texto = _duration(duracion)
            ancho = painter.fontMetrics().horizontalAdvance(texto) + 8
            etiqueta = QRectF(miniatura.right() - ancho - 4, miniatura.bottom() - 17, ancho, 13)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(etiqueta, 4, 4)
            painter.setPen(QColor(theme.TEXTO))
            painter.drawText(etiqueta, Qt.AlignCenter, texto)

        fuente = QFont()
        fuente.setPixelSize(11)
        painter.setFont(fuente)
        nombre = QRectF(miniatura.left(), miniatura.bottom() + 4, miniatura.width(), 16)
        texto = painter.fontMetrics().elidedText(index.data(Qt.DisplayRole) or "",
                                                 Qt.ElideMiddle, int(nombre.width()))
        painter.setPen(QColor(theme.TEXTO if seleccionado else theme.TENUE))
        painter.drawText(nombre, Qt.AlignLeft | Qt.AlignVCenter, texto)
        painter.restore()


class _BinList(QListWidget):
    """La lista de medios. Arrastrar lleva las rutas al timeline.

    La tarjeta de importar no es un elemento de la lista: se dibuja en la
    celda que sigue al último medio visible. Así `count()` sigue contando
    solo lo importado, y buscar o filtrar no la esconde.
    """

    import_clicked = Signal()

    def mimeData(self, items):
        datos = QMimeData()
        rutas = "\n".join(str(i.data(PATH_ROLE)) for i in items)
        datos.setData(MEDIA_MIME, rutas.encode("utf-8"))
        datos.setText(rutas)
        return datos

    def mimeTypes(self):
        return [MEDIA_MIME]

    def import_rect(self) -> QRect:
        """Dónde va la tarjeta punteada, en coordenadas del viewport."""
        visibles = [self.visualItemRect(self.item(i)) for i in range(self.count())
                    if not self.item(i).isHidden()]
        paso = self.gridSize()
        if not visibles:
            celda = QRect(0, 0, paso.width(), paso.height())
        else:
            ultima = visibles[-1]
            celda = QRect(ultima.x() + paso.width(), ultima.y(), paso.width(), paso.height())
            if celda.right() > self.viewport().width():
                celda = QRect(visibles[0].x(), ultima.y() + paso.height(),
                              paso.width(), paso.height())
        return QRect(celda.x() + (celda.width() - CARD.width()) // 2, celda.y() + 4,
                     CARD.width(), CARD.height())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        caja = QRectF(self.import_rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(theme.BORDE_FUERTE), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(caja, 8, 8)
        lado = 14
        draw_icon(painter, "mas", QRectF(caja.center().x() - lado / 2,
                                         caja.center().y() - lado / 2, lado, lado),
                  QColor(theme.TENUE))
        fuente = QFont()
        fuente.setPixelSize(11)
        painter.setFont(fuente)
        painter.setPen(QColor(theme.MUY_TENUE))
        painter.drawText(QRectF(caja.left(), caja.bottom() + 4, caja.width(), 16),
                         Qt.AlignLeft | Qt.AlignVCenter, "Importar")
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and \
                self.import_rect().contains(event.position().toPoint()):
            self.import_clicked.emit()
            return
        super().mousePressEvent(event)


class MediaBin(QDockWidget):
    import_requested = Signal()
    insert_requested = Signal(object)       # ruta
    title_requested = Signal(str)           # posición del texto
    subtitles_requested = Signal()

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

        # --- pestañas ---
        self.tabs = QWidget()
        self.tabs.setStyleSheet(theme.PILL_STYLE)
        fila = QHBoxLayout(self.tabs)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(2)
        self._tab_group = QButtonGroup(self)
        for indice, texto in ((TAB_MEDIA, "Medios"), (TAB_AUDIO, "Audio"), (TAB_TEXT, "Texto")):
            boton = QToolButton()
            boton.setText(texto)
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setFocusPolicy(Qt.NoFocus)
            self._tab_group.addButton(boton, indice)
            fila.addWidget(boton)
        fila.addStretch(1)
        self._tab_group.button(TAB_MEDIA).setChecked(True)
        self._tab_group.idClicked.connect(self._tab_chosen)

        # --- medios ---
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(make_icon("buscar", theme.MUY_TENUE, 14),
                              QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._apply_filter)

        # El filtro por tipo sigue existiendo, escondido: las pestañas lo
        # mueven, y Video e Imágenes se pueden seguir pidiendo por código.
        self.kind = QComboBox()
        self.kind.addItems(KINDS)
        self.kind.currentTextChanged.connect(self._apply_filter)
        self.kind.currentTextChanged.connect(self._sync_tabs)
        self.kind.hide()

        self.list = _BinList()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(ICON)
        self.list.setGridSize(GRID)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QListWidget.DragOnly)
        self.list.setItemDelegate(_CardDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.itemDoubleClicked.connect(
            lambda item: self.insert_requested.emit(Path(item.data(PATH_ROLE))))
        self.list.import_clicked.connect(self.import_requested.emit)

        pagina_medios = QWidget()
        caja = QVBoxLayout(pagina_medios)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)
        caja.addWidget(self.search)
        caja.addWidget(self.kind)
        caja.addWidget(self.list, 1)

        # --- texto ---
        pagina_texto = QWidget()
        flujo = FlowLayout(pagina_texto, spacing=8)
        flujo.setContentsMargins(0, 0, 0, 0)
        self.text_cards: dict[str, QToolButton] = {}
        for posicion in TEXT_CARDS:
            tarjeta = self._text_card("Aa", posicion)
            tarjeta.clicked.connect(lambda _=False, p=posicion: self.title_requested.emit(p))
            self.text_cards[posicion] = tarjeta
            flujo.addWidget(tarjeta)
        subtitulos = self._text_card("SRT", "Subtítulos…")
        subtitulos.setToolTip("Importar subtítulos SRT o VTT")
        subtitulos.clicked.connect(self.subtitles_requested.emit)
        self.text_cards["subtitulos"] = subtitulos
        flujo.addWidget(subtitulos)

        self.pages = QStackedWidget()
        self.pages.addWidget(pagina_medios)
        self.pages.addWidget(pagina_texto)

        # --- pie ---
        self._count = QLabel()
        self._count.setStyleSheet(
            f"color:{theme.MUY_TENUE}; font-family:{theme.MONO}; font-size:11px;")
        self._count.setWordWrap(True)
        self.insert_button = QPushButton("Agregar")
        self.insert_button.setToolTip("Agregar lo seleccionado en el playhead. "
                                      "También puedes arrastrarlo.")
        self.insert_button.setCursor(Qt.PointingHandCursor)
        self.insert_button.clicked.connect(self._insert_selected)
        # Sin esto el botón quedaba prendido sin nada seleccionado y no hacía nada.
        self.list.itemSelectionChanged.connect(
            lambda: self.insert_button.setEnabled(bool(self.list.selectedItems())))
        self.insert_button.setEnabled(False)

        pie = QHBoxLayout()
        pie.setSpacing(6)
        pie.addWidget(self._count, 1)
        pie.addWidget(self.insert_button)

        cuerpo = QWidget()
        cuerpo.setStyleSheet(BIN_STYLE)
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(14, 4, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self.tabs)
        layout.addWidget(self.pages, 1)
        layout.addLayout(pie)
        self.setWidget(cuerpo)
        style_dock(self)
        self._update_count()

    def _text_card(self, muestra: str, nombre: str) -> QToolButton:
        tarjeta = QToolButton()
        tarjeta.setText(f"{muestra}\n{nombre}")
        tarjeta.setFixedSize(CARD.width(), CARD.height() + 10)
        tarjeta.setStyleSheet(TEXT_CARD_STYLE)
        tarjeta.setCursor(Qt.PointingHandCursor)
        tarjeta.setFocusPolicy(Qt.NoFocus)
        tarjeta.setToolTip(f"Agregar un texto ({nombre.lower()}) en el playhead")
        return tarjeta

    # --- pestañas -----------------------------------------------------------

    def _tab_chosen(self, indice: int) -> None:
        if indice == TAB_TEXT:
            self.pages.setCurrentIndex(1)
        else:
            self.pages.setCurrentIndex(0)
            self.kind.setCurrentText("Audio" if indice == TAB_AUDIO else "Todo")
        self._update_count()

    def _sync_tabs(self, texto: str) -> None:
        if self.pages.currentIndex() == 1:
            return
        indice = {"Todo": TAB_MEDIA, "Audio": TAB_AUDIO}.get(texto)
        self._tab_group.setExclusive(False)
        for boton in self._tab_group.buttons():
            boton.setChecked(self._tab_group.id(boton) == indice)
        self._tab_group.setExclusive(True)

    def tab_button(self, indice: int) -> QToolButton:
        return self._tab_group.button(indice)

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
        if info.kind != IMAGE:
            item.setData(DURATION_ROLE, float(getattr(info, "duration", 0.0) or 0.0))
        item.setToolTip(self._describe(info))
        item.setSizeHint(self.list.gridSize())
        imagen = self._thumbs.get(path)
        item.setIcon(QIcon(QPixmap.fromImage(imagen)) if imagen is not None
                     else QIcon(placeholder(info.kind)))
        item.setData(THUMB_ROLE, imagen is not None)
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
                item.setData(THUMB_ROLE, True)

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
        self.list.viewport().update()

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
        self.insert_button.setEnabled(bool(self.list.selectedItems()))
        self.insert_button.setVisible(total > 0 and self.pages.currentIndex() == 0)

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
