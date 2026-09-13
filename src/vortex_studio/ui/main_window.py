"""La ventana principal: amarra preview, timeline, transporte y paneles."""

from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.media import HAS_PYAV, probe_media
from vortex_studio.model.media import AUDIO, IMAGE, lookup
from vortex_studio.media.frameserver import READ_AHEAD, FrameJob, FrameServer
from vortex_studio.media.pool import SourcePool

from vortex_studio.media.mixer import AudioMixer
from vortex_studio.media.encoder import QUALITY, Cancelled, export_audio, export_video
from vortex_studio.media.presets import AUDIO as AUDIO_PRESET
from vortex_studio.media.presets import DEFAULT as DEFAULT_PRESET
from vortex_studio.media.presets import (
    PRESETS,
    all_presets,
    by_name,
    delete_user_preset,
    output_size,
    save_user_preset,
)
from vortex_studio.model import (
    ANCHORS,
    AUDIO_MODES,
    BLENDS,
    FIT_MODES,
    PROPS,
    SHAPES,
    Clip,
    Delete,
    Fill,
    ImageOverlay,
    Link,
    Paste,
    PasteAttributes,
    Project,
    Sequence,
    SetSpeed,
    Split,
    Title,
    Unlink,
    timecode,
)
from vortex_studio.model.commands import copy_items, new_link, overwrite
from vortex_studio.model.project import DIP_BLACK, DIP_WHITE, CROSS, Marker
from vortex_studio.model.transform import FILL
from vortex_studio.model.autosave import (
    AUTOSAVE_SECONDS,
    discard,
    list_recoverable,
    load_recovery,
    write_autosave,
)
from vortex_studio.model.history import History
from vortex_studio.model.serialize import EXTENSION, load_project, save_project
from vortex_studio.ui.audio_player import AudioPlayer
from vortex_studio.ui.compositor import Layer, clear_mask_cache, compose
from vortex_studio.ui.dialogs import MarkerDialog, PasteAttributesDialog
from vortex_studio.ui.panels import PropertiesPanel
from vortex_studio.model.overlays import AdjustmentLayer
from vortex_studio.model.project import NestedClip
from vortex_studio.model.nesting import would_cycle
from vortex_studio.model import render_zones
from vortex_studio.ui import render_cache
from vortex_studio.ui.renderer import (
    SequenceRenderer,
    adjustment_layer,
    fill_layer,
    inside,
    layer_for,
    local_in,
    overlays_at,
    titles_at,
)
from vortex_studio.ui.keyframe_editor import KeyframeEditor
from vortex_studio.ui.scopes import ScopesDock
from vortex_studio.model import subtitles
from vortex_studio.model.project import Track
from vortex_studio.model import animate
from vortex_studio.ui.preview import PreviewWidget
from vortex_studio.ui.shortcuts import DEFAULTS, ShortcutsDialog, load_shortcuts
from vortex_studio.model.commands import RippleDelete, Slip, split_item
from vortex_studio.model.serialize import item_from_dict, sequence_to_dict
from vortex_studio.media.proxy import existing_proxy, needs_proxy
from vortex_studio.model.media import VIDEO
from vortex_studio.ui.media_bin import MediaBin
from vortex_studio.ui.proxies import ProxyManager
from vortex_studio.ui.render_queue import (
    CANCELLED,
    DONE,
    FAILED,
    RenderJob,
    RenderQueue,
    RenderQueuePanel,
)
from vortex_studio.ui.settings import load_settings, save_settings
from vortex_studio.ui.timeline import TOOL_RAZOR, TOOL_SELECT, TOOL_SLIP, TimelineWidget
from vortex_studio.ui.transport import SPEEDS, TransportBar

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}

MEDIA_FILTER = (
    "Medios (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.png *.jpg *.jpeg *.webp *.bmp "
    "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;"
    "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;"
    "Audio (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;"
    "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;"
    "Todos los archivos (*)"
)
PROJECT_FILTER = f"Proyecto de Vortex Studio (*{EXTENSION});;Todos los archivos (*)"
EXPORT_FILTER = "PNG (*.png);;JPEG (*.jpg)"
VIDEO_OUT_FILTER = "Video MP4 (*.mp4)"
AUDIO_OUT_FILTER = "Audio M4A (*.m4a)"

HEAVY_MODIFIERS = Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier

NAV_KEYS = {Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
            Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown}

# Widgets donde el usuario escribe: ahí los atajos de tecla suelta se apagan.
TYPING_WIDGETS = (QPlainTextEdit, QLineEdit, QAbstractSpinBox, QComboBox, QKeySequenceEdit)

# Atajos que un cuadro de texto necesita para sí: copiar y pegar el texto de
# un subtítulo no puede pegar un clip en el timeline.
TEXT_KEYS = {"editar.copiar", "editar.cortar_copia", "editar.pegar", "editar.pegar_atributos"}

TRACK_FLAG_LABELS = {
    ("enabled", True): "Mostrar {}", ("enabled", False): "Ocultar {}",
    ("locked", True): "Bloquear {}", ("locked", False): "Desbloquear {}",
    ("muted", True): "Silenciar {}", ("muted", False): "Quitar silencio a {}",
    ("solo", True): "Solo en {}", ("solo", False): "Quitar solo a {}",
}


def _is_nav_key(sequence: QKeySequence) -> bool:
    """¿El atajo usa flechas, Inicio, Fin o Re Pág / Av Pág?"""
    return not sequence.isEmpty() and sequence[0].key() in NAV_KEYS


def _is_plain_key(sequence: QKeySequence) -> bool:
    """¿El atajo le estorba a quien está escribiendo?

    Una tecla suelta, sin Ctrl ni Alt, sí: teclear una "c" activaría la
    navaja. Y las de navegación también, **aunque lleven Ctrl**: `Ctrl+←`
    salta una palabra dentro de un cuadro de texto, y como atajo del editor
    se la robaría a quien está corrigiendo un subtítulo.
    """
    if sequence.isEmpty():
        return False
    if _is_nav_key(sequence):
        return True
    return not bool(sequence[0].keyboardModifiers() & HEAVY_MODIFIERS)


class _FrameSignal(QObject):
    """Lleva el aviso del hilo de decodificación al hilo de la interfaz.

    El servidor de cuadros no sabe de Qt: avisa llamando a una función desde
    su hilo. Emitir una señal desde ahí la encola hacia el hilo de la
    ventana, que es el único que puede tocar los widgets.
    """

    ready = Signal()


DEFAULT_TITLE_SECONDS = 3.0
DEFAULT_IMAGE_SECONDS = 4.0


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.sequence = self.project.active
        self.history = History()
        self.history.reset(self.sequence)

        # Un decodificador por clip. Compartirlo por archivo hacía que una
        # transición entre dos mitades del mismo video saltara adelante y
        # atrás en cada cuadro, y la reproducción se caía a segundos por
        # cuadro.
        self._sources = SourcePool()        # solo para exportar, en orden

        # El preview decodifica en su propio hilo. Ver `media/frameserver.py`.
        self._frame_signal = _FrameSignal()
        self._frame_signal.ready.connect(self._frames_ready)
        self.frames = FrameServer(on_ready=self._frame_signal.ready.emit,
                                  nested=self._nested_frame_job)
        # Cada edición sube este número: es lo que invalida los cuadros de
        # las secuencias anidadas cuando cambia la hija.
        self._edit_serial = 0
        self._snapshot_memo = None
        self._nested_workers: dict = {}     # solo lo toca el hilo del decodificador
        self.cache_worker = render_cache.RenderCacheWorker(self)
        self.use_render_cache = True
        self._zones: list = []
        self._zones_serial = -1
        self._ready_scheduled = False
        self._images: dict[Path, QImage] = {}
        self._clipboard: list[dict] = []
        self._title: Title | None = None
        self._path: Path | None = None
        self._dirty = False

        # Atajos de una sola tecla (Espacio, C, L, Supr…). Hay que apagarlos
        # mientras se escribe: si no, teclear un subtítulo activa la navaja,
        # el bucle y borra el clip seleccionado, y las letras ni siquiera
        # llegan al cuadro de texto porque el atajo se las come antes.
        self._plain_actions: list[QAction] = []
        self._nav_actions: list[QAction] = []
        self._actions: dict[str, QAction] = {}      # clave del mapa -> acción
        self.shortcuts, self.shortcut_problems = load_shortcuts()

        self._playing = False
        self._speed = 1.0
        self._loop = False
        self._fullscreen = False

        self.resize(1440, 820)

        # El sonido manda cuando está activo: no se puede acelerar ni saltar
        # sin que se oiga, así que la imagen lo sigue a él. Se crea antes que
        # los widgets porque `_connect` ya lo necesita.
        self.audio = AudioPlayer(self)
        self._audio_on = False

        self.preview = PreviewWidget()
        self.preview.set_canvas(self.sequence.width, self.sequence.height)
        self.preview.set_grab_hook(self._settle_preview)
        self.timeline = TimelineWidget(self.sequence)
        self.transport = TransportBar()
        # Un solo panel con pestañas. Los nombres de siempre apuntan a cada
        # página, así que el resto del código no se entera del cambio.
        self.panel = PropertiesPanel()
        self.color_panel = self.panel.color
        self.text_panel = self.panel.text
        self.image_panel = self.panel.image
        self.clip_panel = self.panel.clip
        self.transform_panel = self.panel.transform
        self.mask_panel = self.panel.mask
        self.effects_panel = self.panel.effects
        self.audio_panel = self.panel.audio

        # Lo importado, a la izquierda como en Premiere; la cola de render
        # se asoma sola cuando hay algo exportándose.
        self.media_bin = MediaBin()
        self.render_queue = RenderQueue(self)
        self.queue_panel = RenderQueuePanel(self.render_queue)
        self.keyframe_editor = KeyframeEditor()
        self.scopes = ScopesDock()

        # Proxies: interruptor global, recordado entre sesiones.
        self.proxies = ProxyManager(self)
        from vortex_studio.media.stabilize import STABILIZER, load_or_analyze
        from vortex_studio.ui.analysis import BackgroundAnalyzer
        self.stabilizer = BackgroundAnalyzer(load_or_analyze, STABILIZER.has_analysis, self)
        self._proxy_paths: dict[Path, Path] = {}
        self.use_proxies = bool(load_settings().get("proxies", False))

        self._build_layout()
        self._build_menu()
        self._connect()
        self._update_title()
        self._update_status()
        self._announce_shortcut_problems()

        # Reproducción guiada por reloj real, no por conteo de ticks.
        # `_origin` es el punto de la secuencia donde se dio play y `_elapsed`
        # cuánto ha pasado desde entonces: la posición se calcula, no se
        # acumula. Así, si un cuadro tarda de más, se salta en vez de irse
        # quedando atrás — que es lo que desfasa a un reproductor.
        # Los paneles disparan un cambio por cada tecla y por cada pixel que
        # se mueve un deslizador. Agruparlos en una sola entrada del historial
        # es lo que hace que Ctrl+Z deshaga "escribir el subtítulo" y no la
        # última letra.
        self._pending: str | None = None
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(700)
        self._commit_timer.timeout.connect(self._flush)

        # Autoguardado. Ver `model/autosave.py`: la copia va a la carpeta de
        # datos del sistema, nunca encima del proyecto del usuario.
        self._session = uuid.uuid4().hex[:8]
        self._autosave_path: Path | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_SECONDS * 1000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()

        self._elapsed = QElapsedTimer()
        self._origin = 0.0
        self._clock = QTimer(self)
        self._clock.setTimerType(Qt.PreciseTimer)
        self._clock.timeout.connect(self._tick)

        if not HAS_PYAV:
            self.preview.set_message(
                "PyAV no está instalado — la app corre, pero sin imagen.\n"
                "pip install -r requirements.txt"
            )

    # --- armado -----------------------------------------------------------

    def _build_layout(self) -> None:
        self._top = QWidget()
        self._top_layout = QVBoxLayout(self._top)
        self._top_layout.setContentsMargins(0, 0, 0, 0)
        self._top_layout.setSpacing(0)
        self._top_layout.addWidget(self.preview, 1)
        self._top_layout.addWidget(self.transport)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._top)
        splitter.addWidget(self.timeline)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        self.addDockWidget(Qt.RightDockWidgetArea, self.panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.media_bin)
        self.addDockWidget(Qt.RightDockWidgetArea, self.queue_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.keyframe_editor)
        self.keyframe_editor.hide()
        self.addDockWidget(Qt.RightDockWidgetArea, self.scopes)
        self.scopes.hide()
        self.scopes.visibilityChanged.connect(
            lambda visible: visible and self.scopes.submit(self.scope_image()))
        self.queue_panel.hide()
        self.resizeDocks([self.panel, self.media_bin], [330, 250], Qt.Horizontal)

    def _build_menu(self) -> None:
        # Cada atajo se pide por su clave, no por su tecla: la tecla sale del
        # mapa de atajos (`ui/shortcuts.py`), que el usuario puede cambiar.
        archivo = self.menuBar().addMenu("&Archivo")
        self._action(archivo, "&Nuevo proyecto", "archivo.nuevo", self.new_project)
        self._action(archivo, "&Abrir proyecto…", "archivo.abrir", self.open_project)
        archivo.addSeparator()
        self._action(archivo, "&Guardar", "archivo.guardar", self.save)
        self._action(archivo, "Guardar &como…", "archivo.guardar_como", self.save_as)
        archivo.addSeparator()
        self._action(archivo, "&Importar…", "archivo.importar", self.import_media)
        self._action(archivo, "Importar al &panel de medios…", None,
                     lambda: self.import_to_bin())
        self._action(archivo, "Exportar &video…", "archivo.exportar_video", self.export_video)
        self._action(archivo, "Exportar &cuadro…", "archivo.exportar_cuadro", self.export_frame)
        self._action(archivo, "Exportar por &marcadores…", None, self.export_by_markers)
        archivo.addSeparator()
        self._action(archivo, "Importar &subtítulos (SRT, VTT)…", None,
                     lambda: self.import_subtitles())
        self._action(archivo, "Exportar s&ubtítulos…", None, lambda: self.export_subtitles())
        archivo.addSeparator()
        self._action(archivo, "&Salir", "archivo.salir", self.close)

        editar = self.menuBar().addMenu("&Editar")
        self._undo_action = self._action(editar, "&Deshacer", "editar.deshacer", self.undo)
        self._redo_action = self._action(editar, "&Rehacer", "editar.rehacer", self.redo)
        editar.addSeparator()
        self._action(editar, "&Cortar en el playhead", "editar.cortar", self.cut_at_playhead)
        self._action(editar, "Di&vidir en el playhead", "editar.dividir", self.cut_at_playhead)
        self._action(editar, "&Duplicar", "editar.duplicar", self.duplicate_selected)
        self._action(editar, "&Eliminar", "editar.eliminar", self.delete_selected)
        self._action(editar, "Eliminar y &cerrar hueco", "editar.eliminar_hueco",
                     self.ripple_delete)
        editar.addSeparator()
        self._action(editar, "C&opiar", "editar.copiar", self.copy_selected)
        self._action(editar, "Cortar al &portapapeles", "editar.cortar_copia",
                     self.cut_to_clipboard)
        self._action(editar, "&Pegar", "editar.pegar", self.paste)
        self._action(editar, "Pegar a&tributos…", "editar.pegar_atributos",
                     self.paste_attributes)
        editar.addSeparator()
        self._action(editar, "En&lazar o desenlazar", "editar.enlazar", self.toggle_link)
        editar.addSeparator()

        herramientas = QActionGroup(self)
        self._tool_actions = {}
        for label, clave, tool in (("Selección", "herramienta.seleccion", TOOL_SELECT),
                                   ("Navaja", "herramienta.navaja", TOOL_RAZOR),
                                   ("Deslizar (slip)", "herramienta.slip", TOOL_SLIP)):
            action = self._action(editar, f"Herramienta: {label}", clave,
                                  lambda _=False, t=tool: self.set_tool(t))
            action.setCheckable(True)
            action.setChecked(tool == TOOL_SELECT)
            herramientas.addAction(action)
            self._tool_actions[tool] = action
        editar.addSeparator()
        self._action(editar, "Deslizar contenido un cuadro &atrás", "editar.slip_atras",
                     lambda: self.slip_selected(-1))
        self._action(editar, "Deslizar contenido un cuadro a&delante", "editar.slip_adelante",
                     lambda: self.slip_selected(1))
        editar.addSeparator()
        self._action(editar, "Atajos de &teclado…", "editar.atajos", self.open_shortcuts)

        # Nada de atajos con Ctrl+Alt: en Windows, con teclado latinoamericano,
        # AltGr manda Ctrl+Alt, así que escribir @ o \ los dispararía. El mapa
        # de atajos lo valida; ver `ui/shortcuts.py`.
        clip_menu = self.menuBar().addMenu("&Clip")
        self._action(clip_menu, "&Fundir entrada y salida", "clip.fundir",
                     lambda: self.set_fade(entrada=1.0, salida=1.0))
        self._action(clip_menu, "Fundido de &entrada (1 s)", None,
                     lambda: self.set_fade(entrada=1.0))
        self._action(clip_menu, "Fundido de &salida (1 s)", None,
                     lambda: self.set_fade(salida=1.0))
        self._action(clip_menu, "&Quitar fundidos", None,
                     lambda: self.set_fade(entrada=0.0, salida=0.0))
        clip_menu.addSeparator()
        for etiqueta, valor in (("Cámara lenta 0.25×", 0.25), ("Cámara lenta 0.5×", 0.5),
                                ("Velocidad normal", 1.0),
                                ("Cámara rápida 2×", 2.0), ("Cámara rápida 4×", 4.0)):
            self._action(clip_menu, etiqueta, None,
                         lambda _=False, v=valor: self.set_clip_speed(v))
        sonido = clip_menu.addMenu("&Audio a otra velocidad")
        for modo in AUDIO_MODES:
            self._action(sonido, modo, None, lambda _=False, m=modo: self.set_audio_mode(m))
        clip_menu.addSeparator()
        self._action(clip_menu, "&Transición cruzada (1 s)", "clip.transicion",
                     lambda: self.set_dissolve(1.0, CROSS))
        self._action(clip_menu, "Fundido a &negro (1 s)", "clip.fundido_negro",
                     lambda: self.set_dissolve(1.0, DIP_BLACK))
        self._action(clip_menu, "Fundido a &blanco (1 s)", None,
                     lambda: self.set_dissolve(1.0, DIP_WHITE))
        self._action(clip_menu, "Quitar &transición", None, lambda: self.set_dissolve(0.0))
        clip_menu.addSeparator()
        self._action(clip_menu, "&Congelar cuadro", "clip.congelar", self.freeze_frame)
        clip_menu.addSeparator()
        self._action(clip_menu, "Poner &keyframe de todo", "clip.keyframe",
                     self.key_all_transform)
        self._action(clip_menu, "Quitar a&nimación", None, self.clear_transform_keys)
        self._action(clip_menu, "&Editor de keyframes", "clip.keyframes",
                     lambda: self.open_keyframe_editor())

        capa = self.menuBar().addMenu("Ca&pa")
        fusion = capa.addMenu("Modo de &fusión")
        for nombre in BLENDS:
            self._action(fusion, nombre, None,
                         lambda _=False, n=nombre: self.set_blend(n))
        mascara = capa.addMenu("&Máscara")
        for nombre in SHAPES:
            etiqueta = "Quitar máscara" if nombre == "Ninguna" else nombre
            self._action(mascara, etiqueta, None,
                         lambda _=False, n=nombre: self.set_mask_shape(n))
        mascara.addSeparator()
        self._action(mascara, "&Invertir la máscara", None, self.invert_mask)
        encuadre = capa.addMenu("&Encuadre")
        for modo in FIT_MODES:
            self._action(encuadre, modo, None, lambda _=False, m=modo: self.set_fit(m))
        capa.addSeparator()
        self._action(capa, "&Cuadro dentro de cuadro", "capa.pip", self.picture_in_picture)
        self._action(capa, "&Llenar el cuadro", None, self.fill_frame)

        insertar = self.menuBar().addMenu("&Insertar")
        self._action(insertar, "&Texto", "insertar.texto", self.add_title)
        self._action(insertar, "&Subtítulo aquí", "insertar.subtitulo",
                     lambda: self.add_title(anchor="Subtítulo"))
        self._action(insertar, "&Imagen…", "insertar.imagen", self.import_image)
        self._action(insertar, "Capa de &ajuste", None, lambda: self.add_adjustment_layer())

        reproducir = self.menuBar().addMenu("&Reproducción")
        self._action(reproducir, "Reproducir / pausar", "reproducir.play", self.toggle_play)
        reproducir.addSeparator()
        self._action(reproducir, "Más lento", "reproducir.lento", lambda: self._shift_speed(-1))
        self._action(reproducir, "Velocidad normal", "reproducir.normal",
                     lambda: self.set_speed(1.0))
        self._action(reproducir, "Más rápido", "reproducir.rapido", lambda: self._shift_speed(1))
        reproducir.addSeparator()
        self._loop_action = self._action(reproducir, "Repetir", "reproducir.repetir",
                                         self.toggle_loop)
        self._loop_action.setCheckable(True)
        reproducir.addSeparator()

        # Las flechas, Inicio y Fin eran teclas escritas dentro de
        # `keyPressEvent`, fuera de cualquier mapa. Como acciones se pueden
        # cambiar, aparecen en el menú, y se apagan solas al escribir.
        navegar = reproducir.addMenu("&Navegar")
        for texto, clave, slot in (
            ("Cuadro anterior", "navegar.cuadro_atras", lambda: self._step(-1)),
            ("Cuadro siguiente", "navegar.cuadro_adelante", lambda: self._step(1)),
            ("Un segundo atrás", "navegar.segundo_atras", lambda: self._skip(-1.0)),
            ("Un segundo adelante", "navegar.segundo_adelante", lambda: self._skip(1.0)),
            ("Diez segundos atrás", "navegar.diez_atras", lambda: self._skip(-10.0)),
            ("Diez segundos adelante", "navegar.diez_adelante", lambda: self._skip(10.0)),
            ("Ir al inicio", "navegar.inicio", lambda: self._scrubbed(0.0)),
            ("Ir al final", "navegar.final", lambda: self._scrubbed(self.sequence.duration)),
        ):
            self._action(navegar, texto, clave, slot)

        marcar = self.menuBar().addMenu("&Marcar")
        self._action(marcar, "Marcar &entrada", "marcar.entrada", self.mark_in)
        self._action(marcar, "Marcar &salida", "marcar.salida", self.mark_out)
        self._action(marcar, "&Quitar marcas", "marcar.quitar", self.clear_marks)
        marcar.addSeparator()
        self._action(marcar, "Poner &marcador", "marcar.marcador", self.add_marker)
        self._action(marcar, "&Editar marcador…", "marcar.marcador_nombre",
                     self.add_named_marker)
        self._action(marcar, "Marcador en el &clip", "marcar.marcador_clip",
                     self.add_marker_to_clip)
        self._action(marcar, "Marcador &siguiente", "marcar.siguiente", self.next_marker)
        self._action(marcar, "Marcador &anterior", "marcar.anterior", self.previous_marker)
        self._action(marcar, "&Borrar marcadores", "marcar.borrar", self.clear_markers)
        marcar.addSeparator()
        self._action(marcar, "Ir a la entrada", "marcar.ir_entrada",
                     lambda: self._scrubbed(self.timeline.mark_in or 0.0))
        self._action(marcar, "Ir a la salida", "marcar.ir_salida",
                     lambda: self._scrubbed(self.timeline.mark_out or self.sequence.duration))

        formato = self.menuBar().addMenu("&Secuencia")
        for etiqueta, ancho, alto in (
            ("Horizontal 16:9  ·  1920 × 1080", 1920, 1080),
            ("Vertical 9:16  ·  1080 × 1920", 1080, 1920),
            ("Cuadrado 1:1  ·  1080 × 1080", 1080, 1080),
            ("Vertical 4:5  ·  1080 × 1350", 1080, 1350),
            ("Cine 21:9  ·  2560 × 1080", 2560, 1080),
        ):
            self._action(formato, etiqueta, None,
                         lambda _=False, a=ancho, b=alto: self.set_format(a, b))
        formato.addSeparator()
        self._action(formato, "Ajustar al primer clip", None, self.format_from_clip)
        self._action(formato, "Rellenar el cuadro con todos los clips", None,
                     lambda: self.reframe_all(FILL))
        formato.addSeparator()
        self._action(formato, "&Renderizar zona (entre marcas o todo)", "reproducir.renderizar",
                     lambda: self.render_zones())
        self._action(formato, "&Borrar la caché de render", None, self.clear_render_cache)
        formato.addSeparator()
        self._action(formato, "&Nueva secuencia", None, lambda: self.new_sequence())
        self._action(formato, "&Anidar la selección", "editar.anidar", lambda: self.nest_selection())
        self._switch_menu = formato.addMenu("&Cambiar a")
        self._switch_menu.aboutToShow.connect(self._fill_switch_menu)
        self._insert_menu = formato.addMenu("&Insertar secuencia")
        self._insert_menu.aboutToShow.connect(self._fill_insert_menu)

        ver = self.menuBar().addMenu("&Ver")
        self._action(ver, "Pantalla &completa", "ver.pantalla_completa", self.toggle_fullscreen)
        self._action(ver, "&Ajustar timeline", "ver.ajustar", self._fit_zoom)
        ver.addSeparator()
        self._proxy_action = self._action(ver, "Usar &proxies (540p)", None,
                                          lambda on: self.set_use_proxies(on))
        self._proxy_action.setCheckable(True)
        self._proxy_action.setChecked(self.use_proxies)
        self._action(ver, "&Crear proxies de los videos", None, lambda: self.create_proxies())
        ver.addSeparator()
        ver.addAction(self.panel.toggleViewAction())
        ver.addAction(self.media_bin.toggleViewAction())
        ver.addAction(self.queue_panel.toggleViewAction())
        ver.addAction(self.keyframe_editor.toggleViewAction())
        ver.addAction(self.scopes.toggleViewAction())

        self._classify_actions()
        self._update_history_actions()
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def _action(self, menu, text: str, shortcut, slot) -> QAction:
        """Crea una acción del menú. `shortcut` es la clave del mapa de atajos.

        Una tecla escrita directo aquí truena a propósito: si se pudiera, el
        atajo nuevo no aparecería en el editor de atajos ni se podría
        cambiar, que es justo lo que se quitó.
        """
        action = QAction(text, self)
        if shortcut:
            if shortcut not in DEFAULTS:
                raise KeyError(f"«{shortcut}» no está en el mapa de atajos (ui/shortcuts.py)")
            action.setData(shortcut)
            action.setShortcut(QKeySequence(self.shortcuts.get(shortcut, ""),
                                            QKeySequence.PortableText))
            self._actions[shortcut] = action
        action.triggered.connect(slot)
        # Los atajos deben responder aunque el foco esté en el timeline.
        action.setShortcutContext(Qt.ApplicationShortcut)
        menu.addAction(action)
        return action

    def _classify_actions(self) -> None:
        """Qué atajos se apagan al escribir, y cuáles solo en un deslizador."""
        self._plain_actions = [a for a in self._actions.values() if _is_plain_key(a.shortcut())]
        self._nav_actions = [a for a in self._plain_actions if _is_nav_key(a.shortcut())]

    def _focus_changed(self, old, new) -> None:
        """Apaga los atajos que le robarían la tecla al widget con el foco.

        Escribiendo, se apagan todos los de tecla suelta y los de navegación.
        En un deslizador solo los de navegación: las flechas mueven el
        deslizador, pero `Espacio` tiene que seguir reproduciendo.
        """
        typing = isinstance(new, TYPING_WIDGETS)
        slider = isinstance(new, QAbstractSlider)
        for action in self._plain_actions:
            action.setEnabled(not typing and not (slider and action in self._nav_actions))
        for clave in TEXT_KEYS:
            if clave in self._actions:
                self._actions[clave].setEnabled(not typing)

    def apply_shortcuts(self, mapping: dict[str, str]) -> None:
        """Cambia las teclas en vivo, sin reiniciar la ventana."""
        self.shortcuts = dict(mapping)
        for clave, action in self._actions.items():
            action.setShortcut(QKeySequence(mapping.get(clave, ""), QKeySequence.PortableText))
        self._classify_actions()
        self._focus_changed(None, QApplication.focusWidget())

    def open_shortcuts(self) -> None:
        dialogo = ShortcutsDialog(self, self.shortcuts)
        if dialogo.exec() == QDialog.Accepted:
            self.apply_shortcuts(dialogo.mapping)
            self.statusBar().showMessage("Atajos guardados.", 4000)

    def _announce_shortcut_problems(self) -> None:
        if self.shortcut_problems:
            primero = self.shortcut_problems[0]
            resto = len(self.shortcut_problems) - 1
            self.statusBar().showMessage(
                f"Atajos: {primero}" + (f"  (y {resto} más)" if resto else ""), 15000)

    def _connect(self) -> None:
        self.timeline.playhead_moved.connect(self._scrubbed)
        self.timeline.selection_changed.connect(self._selected)
        self.timeline.edit_finished.connect(self._commit)
        self.timeline.cut_requested.connect(self._cut)
        self.timeline.live_edit.connect(self._refresh)
        self.timeline.track_toggled.connect(self._track_toggled)
        self.timeline.marker_activated.connect(self.edit_marker)
        self.timeline.media_dropped.connect(self.place_media)
        self.timeline.clip_activated.connect(
            lambda item: self.open_nested(item) if isinstance(item, NestedClip) else None)
        self.timeline.source_duration = self._source_duration

        self.transport.play_pause.connect(self.toggle_play)
        self.transport.step.connect(self._step)
        self.transport.skip.connect(self._skip)
        self.transport.go_start.connect(lambda: self._scrubbed(0.0))
        self.transport.go_end.connect(lambda: self._scrubbed(self.sequence.duration))
        self.transport.loop_toggled.connect(self.set_loop)
        self.transport.speed_changed.connect(self.set_speed)
        self.transport.volume_changed.connect(self.audio.set_volume)

        self.preview.fullscreen_toggled.connect(self.toggle_fullscreen)
        self.media_bin.import_requested.connect(lambda: self.import_to_bin())
        self.media_bin.insert_requested.connect(
            lambda path: self.place_media(path, at=self.timeline.playhead))
        self.render_queue.finished.connect(self._render_finished)
        self.keyframe_editor.changed.connect(self._keyframes_edited)
        self.keyframe_editor.committed.connect(self._keyframes_committed)
        self.proxies.ready.connect(self._proxy_ready)
        self.stabilizer.ready.connect(self._stabilize_ready)
        self.cache_worker.zone_ready.connect(lambda _firma: self._refresh_render_bar())
        self.cache_worker.finished.connect(self._cache_finished)
        self.cache_worker.failed.connect(
            lambda error: self.statusBar().showMessage(f"No se pudo renderizar: {error}", 8000))
        self.stabilizer.progress.connect(
            lambda path, avance: self.effects_panel.set_stabilize_status(
                f"Analizando {Path(path).name}: {avance * 100:.0f} %"))
        self.stabilizer.failed.connect(
            lambda path, error: self.effects_panel.set_stabilize_status(
                f"No se pudo analizar: {error}"))
        self.proxies.progress.connect(self._proxy_progress)
        self.proxies.failed.connect(
            lambda path, error: self.statusBar().showMessage(
                f"No se pudo crear el proxy de {Path(path).name}: {error}", 8000))
        self.color_panel.changed.connect(self._color_changed)
        self.image_panel.changed.connect(self._image_changed)
        self.clip_panel.changed.connect(lambda: self._schedule("Ajustar clip"))
        self.clip_panel.committed.connect(self._clip_committed)
        self.transform_panel.changed.connect(lambda: self._schedule("Transformar"))
        self.transform_panel.committed.connect(self._commit)
        self.mask_panel.changed.connect(lambda: self._schedule("Máscara"))
        self.effects_panel.changed.connect(lambda: self._schedule("Efectos"))
        self.effects_panel.committed.connect(self._effects_committed)
        self.audio_panel.changed.connect(lambda: self._schedule("Efectos de audio"))
        self.audio_panel.committed.connect(self._effects_committed)
        self.audio_panel.normalize_requested.connect(lambda meta: self.normalize_loudness(meta))
        self.mask_panel.committed.connect(self._commit)
        self.text_panel.changed.connect(self._text_changed)
        self.text_panel.add_requested.connect(self.add_title)
        self.text_panel.delete_requested.connect(self.delete_title)

    # --- proyecto ---------------------------------------------------------

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._clear_autosave()
        self._close_sources()
        self.project = Project()
        self._path = None
        self._adopt(self.project.active, reset_history=True)
        self._dirty = False
        self._update_title()

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", "", PROJECT_FILTER)
        if not path:
            return

        try:
            project = load_project(path)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo abrir", f"{Path(path).name}\n\n{error}")
            return

        self._clear_autosave()
        self._close_sources()
        self.project = project
        self._path = Path(path)
        self._adopt(project.active, reset_history=True)
        self._dirty = False
        self._update_title()

    def save(self) -> bool:
        self._flush()
        if self._path is None:
            return self.save_as()
        try:
            save_project(self.project, self._path)
        except OSError as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return False
        self._dirty = False
        self._clear_autosave()      # lo guardado ya está a salvo
        self._update_title()
        return True

    def save_as(self) -> bool:
        suggested = str(self._path or Path.home() / f"proyecto{EXTENSION}")
        path, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", suggested, PROJECT_FILTER)
        if not path:
            return False
        self._path = Path(path)
        self.project.name = self._path.stem
        return self.save()

    # --- autoguardado -----------------------------------------------------

    def autosave(self) -> Path | None:
        """Escribe la copia de seguridad si hay algo que salvar.

        Sin cambios no escribe nada: autoguardar un proyecto recién guardado
        solo gasta disco y deja una copia que luego habría que explicar.
        """
        self._flush()        # lo que se está tecleando también cuenta
        if not self._dirty:
            return None
        try:
            destino = write_autosave(self.project, self._path, self._session)
        except OSError as error:
            self.statusBar().showMessage(f"No se pudo autoguardar: {error}", 8000)
            return None

        # Si el proyecto cambió de nombre (Guardar como), la copia vieja ya
        # no corresponde a nada.
        if self._autosave_path is not None and self._autosave_path != destino:
            discard(self._autosave_path)
        self._autosave_path = destino
        return destino

    def _clear_autosave(self) -> None:
        discard(self._autosave_path)
        self._autosave_path = None

    def offer_recovery(self) -> bool:
        """Al arrancar: si quedó una copia de un cierre de golpe, ofrecerla.

        Aquí sí va un diálogo: recuperar o tirar trabajo es una decisión que
        el usuario tiene que ver, no un aviso que se pierda en la barra.
        """
        copias = list_recoverable()
        if not copias:
            return False

        copia = copias[0]
        cuando = time.strftime("%d/%m %H:%M", time.localtime(copia.saved_at))
        donde = f"\n\nProyecto: {copia.original}" if copia.original else ""
        respuesta = QMessageBox.question(
            self, "Recuperar trabajo",
            f"Vortex Studio se cerró sin guardar «{copia.name}».\n"
            f"Hay una copia automática de las {cuando}.{donde}\n\n"
            f"¿Recuperarla?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

        if respuesta != QMessageBox.Yes:
            discard(copia.path)
            return False
        return self.recover(copia)

    def recover(self, copia) -> bool:
        try:
            project = load_recovery(copia)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo recuperar", str(error))
            return False

        self._close_sources()
        self.project = project
        self._path = copia.original
        self._adopt(project.active, reset_history=True)
        # Queda como "sin guardar" a propósito: lo recuperado todavía no
        # está en el .vortex del usuario hasta que él lo guarde.
        self._dirty = True
        self._autosave_path = copia.path
        self._update_title()
        self.statusBar().showMessage(
            f"Recuperado de la copia automática de las "
            f"{time.strftime('%H:%M', time.localtime(copia.saved_at))}. "
            f"Guarda para no perderlo.", 10000)
        return True

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "Hay cambios sin guardar",
            "¿Guardar el proyecto antes de continuar?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save()
        return True

    def _update_title(self) -> None:
        name = self._path.stem if self._path else "Sin título"
        self.setWindowTitle(f"{'*' if self._dirty else ''}{name} — Vortex Studio")

    def _update_status(self) -> None:
        """Lo que hay que saber de un vistazo sin abrir ningún menú."""
        seq = self.sequence
        piezas = sum(len(track.clips) for track in seq.tracks)
        marcadores = (f"   ·   {len(seq.markers)} marcador"
                      f"{'es' if len(seq.markers) != 1 else ''}" if seq.markers else "")
        herramienta = {TOOL_RAZOR: "Navaja", TOOL_SLIP: "Deslizar"}.get(
            self.timeline.tool, "Selección")
        marcas = ""
        if self.timeline.mark_in is not None or self.timeline.mark_out is not None:
            inicio, fin = self._range()
            marcas = f"   ·   Marcas {timecode(inicio, seq.fps)} → {timecode(fin, seq.fps)}"

        proxies = "   ·   Proxies" if getattr(self, "use_proxies", False) else ""
        if len(self.project.sequences) > 1:
            marcadores = marcadores + f"   ·   Secuencia «{seq.name}»"
        self.statusBar().showMessage(
            f"{seq.width}×{seq.height}   ·   {seq.fps:g} fps   ·   "
            f"{timecode(seq.duration, seq.fps)}   ·   "
            f"{piezas} elemento{'s' if piezas != 1 else ''}   ·   "
            f"{herramienta}{marcadores}{marcas}{proxies}"
        )

    # --- historial --------------------------------------------------------

    def _schedule(self, label: str) -> None:
        """Apunta un cambio para registrarlo cuando el usuario deje de teclear."""
        self._absorb_animation()
        self._edit_serial += 1
        self._pending = label
        self._commit_timer.start()
        self._dirty = True
        self._update_title()
        self._refresh()

    def _flush(self) -> None:
        if self._pending is None:
            return
        self.history.push(self.sequence, self._pending)
        self._pending = None
        self._update_history_actions()

    def _commit(self, label: str) -> None:
        """Registra un cambio ya aplicado y refresca lo que dependa de él."""
        self._edit_serial += 1
        self._commit_timer.stop()
        self._pending = None
        self.history.push(self.sequence, label)
        self._dirty = True
        self._update_title()
        self._update_history_actions()
        self._refresh()
        self._update_status()
        self._refresh_render_bar()

    def undo(self) -> None:
        self._flush()
        self._restore(self.history.undo())

    def redo(self) -> None:
        self._flush()
        self._restore(self.history.redo())

    def _restore(self, sequence: Sequence | None) -> None:
        if sequence is None:
            return
        self._pause()
        self.project.sequences[self.project.active_index()] = sequence
        self._adopt(sequence, reset_history=False)
        self._dirty = True
        self._update_title()

    def _adopt(self, sequence: Sequence, reset_history: bool) -> None:
        """Pone una secuencia nueva en circulación por toda la interfaz."""
        self._edit_serial += 1
        self.sequence = sequence
        if any(s is sequence for s in self.project.sequences):
            self.project.active_id = sequence.id
        self.timeline.sequence = sequence
        self.timeline.selected = None
        self.timeline.refresh()
        self._title = None
        self.preview.set_canvas(sequence.width, sequence.height)
        if reset_history:
            self._refresh_bin()
            if self.use_proxies:
                self._scan_proxies()

        if reset_history:
            self.history.reset(sequence)
        self._update_history_actions()

        self._fit_zoom()
        self._seek(min(self.timeline.playhead, sequence.duration))
        self._update_status()

    def _update_history_actions(self) -> None:
        self._undo_action.setEnabled(self.history.can_undo)
        self._redo_action.setEnabled(self.history.can_redo)
        self._undo_action.setText(
            f"&Deshacer {self.history.undo_label}".rstrip() if self.history.can_undo
            else "&Deshacer")
        self._redo_action.setText(
            f"&Rehacer {self.history.redo_label}".rstrip() if self.history.can_redo
            else "&Rehacer")

    # --- importar ---------------------------------------------------------

    def import_media(self) -> None:
        """Un solo diálogo: decide por la extensión a qué pista va."""
        path, _ = QFileDialog.getOpenFileName(self, "Importar", "", MEDIA_FILTER)
        if not path:
            return

        suffix = Path(path).suffix.lower()
        if suffix in IMAGE_EXT:
            self._place_image(Path(path))
        elif suffix in VIDEO_EXT:
            self._place_video(Path(path))
        elif suffix in AUDIO_EXT:
            self._place_audio(Path(path))
        else:
            QMessageBox.warning(self, "Formato no reconocido",
                                f"No sé qué hacer con «{suffix}».")

    def import_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar video", "", MEDIA_FILTER)
        if path:
            self._place_video(Path(path))

    def import_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar imagen", "", MEDIA_FILTER)
        if path:
            self._place_image(Path(path))

    def place_media(self, path: Path, at: float | None = None, track_index: int = -1) -> None:
        """Pone un archivo en el timeline según lo que dijo el sondeo.

        `at` y `track_index` vienen de soltarlo con el mouse; sin ellos, cada
        clase de archivo va a su lugar de siempre.
        """
        path = Path(path)
        try:
            info = self._media_info(path)
        except Exception as error:
            self.statusBar().showMessage(f"No se pudo abrir {path.name}: {error}", 6000)
            return
        if info.kind == AUDIO:
            self._place_audio(path, at, track_index)
        elif info.kind == IMAGE:
            self._place_image(path, at, track_index)
        else:
            self._place_video(path, at, track_index)

    def _target_track(self, index: int, kind: str):
        """La pista donde se soltó, si es de la clase correcta y no está bloqueada."""
        if 0 <= index < len(self.sequence.tracks):
            pista = self.sequence.tracks[index]
            if pista.kind == kind and not pista.locked:
                return pista
        return None

    def _place_video(self, path: Path, at: float | None = None, track_index: int = -1) -> None:
        if not HAS_PYAV:
            QMessageBox.warning(
                self, "Falta PyAV",
                "Instala las dependencias para poder leer video:\n\n"
                "./.venv/bin/pip install -r requirements.txt")
            return

        try:
            info = self._media_info(path)
        except Exception as error:  # el archivo puede estar roto o no ser video
            QMessageBox.critical(self, "No se pudo abrir", f"{path.name}\n\n{error}")
            return

        # La extensión no manda: un .mp4 puede traer solo audio, y un .mkv
        # puede ser una foto. Decide lo que dijo el sondeo.
        if info.kind == AUDIO:
            self._place_audio(path)
            return
        if info.kind == IMAGE:
            self._place_image(path)
            return

        track = (self._target_track(track_index, "video")
                 or self.sequence.video_tracks()[-1])   # V1, la de hasta abajo
        first = not self.sequence.video_tracks()[-1].clips
        duration = info.duration or 0.0
        if at is None:
            clip = track.append(path, duration)
        else:
            clip = Clip(path, max(0.0, at), duration)
            overwrite(track, clip)
            track.add(clip)

        # El audio del archivo entra como su propio clip en una pista de
        # audio, alineado y **enlazado** con el video: se mueven, recortan,
        # cortan y borran juntos. Alt+clic agarra un solo lado, y Ctrl+L los
        # desenlaza.
        if info.has_audio:
            clip.link = new_link()
            audio = self._free_audio_track(clip.start, clip.end) if at is not None \
                else self.sequence.audio_tracks()[0]
            sonido = Clip(source=path, start=clip.start, duration=duration, link=clip.link)
            overwrite(audio, sonido)
            audio.add(sonido)
            self.timeline.waves.get(path)   # la onda empieza a calcularse ya

        if first:
            self.sequence.fps = info.fps or self.sequence.fps
            self.sequence.width = info.width or self.sequence.width
            self.sequence.height = info.height or self.sequence.height
            self.preview.set_canvas(self.sequence.width, self.sequence.height)

        self._fit_zoom()
        self.timeline.select(clip)
        self._commit("Importar video")
        self._seek(clip.start)

    def _media_info(self, path: Path):
        """El sondeo del archivo, del caché del proyecto si sigue vigente."""
        antes = len(self.project.media)
        info = lookup(self.project.media, path, probe_media)
        if len(self.project.media) != antes:
            self._refresh_bin()
        return info

    # --- panel de medios --------------------------------------------------

    def _refresh_bin(self) -> None:
        self.media_bin.set_proxies(self._proxy_paths)
        self.media_bin.set_library(self.project.media)

    def import_to_bin(self, paths=None) -> int:
        """Trae archivos al panel de medios sin ponerlos en el timeline."""
        if paths is None:
            paths, _ = QFileDialog.getOpenFileNames(self, "Importar al panel", "",
                                                    MEDIA_FILTER)
        agregados, fallas = 0, []
        for path in paths or []:
            try:
                self._media_info(Path(path))
                agregados += 1
            except Exception:
                fallas.append(Path(path).name)
        if agregados or fallas:
            self._dirty = self._dirty or bool(agregados)
            self._update_title()
            self._refresh_bin()
            self.media_bin.show()
            aviso = f"{agregados} archivo{'s' if agregados != 1 else ''} en el panel de medios"
            if fallas:
                aviso += f"  ·  no se pudo leer: {', '.join(fallas)}"
            self.statusBar().showMessage(aviso, 6000)
        return agregados

    # --- proxies ----------------------------------------------------------

    def set_use_proxies(self, on: bool) -> None:
        """El interruptor global: el preview lee de los proxies que existan.

        Exportar sigue leyendo siempre de los originales. Al prenderlo se
        encargan los proxies que falten de los videos pesados.
        """
        self.use_proxies = bool(on)
        save_settings({"proxies": self.use_proxies})
        if self._proxy_action.isChecked() != self.use_proxies:
            self._proxy_action.setChecked(self.use_proxies)
        if self.use_proxies:
            self._scan_proxies()
            self.create_proxies()
        self._refresh()
        self._update_status()

    def _video_sources(self) -> list[Path]:
        vistos: list[Path] = []
        for track in self.sequence.video_tracks():
            for clip in track.clips:
                if isinstance(clip, Clip) and not isinstance(clip, NestedClip) \
                        and Path(clip.source) not in vistos:
                    vistos.append(Path(clip.source))
        return vistos

    def _scan_proxies(self) -> None:
        for fuente in self._video_sources():
            proxy = existing_proxy(fuente)
            if proxy is not None:
                self._proxy_paths[fuente] = proxy

    def create_proxies(self, only_heavy: bool = True) -> int:
        """Encarga los proxies que falten. Un video de 540p o menos no lo necesita."""
        fuentes = []
        for fuente in self._video_sources():
            try:
                info = self._media_info(fuente)
            except Exception:
                continue
            if info.kind == VIDEO and (not only_heavy or needs_proxy(info.width, info.height)):
                fuentes.append(fuente)
        nuevos = self.proxies.request(fuentes)
        if nuevos:
            self.statusBar().showMessage(
                f"Creando {nuevos} prox{'ies' if nuevos != 1 else 'y'} en segundo plano…", 5000)
        elif fuentes or only_heavy:
            self._scan_proxies()
        return nuevos

    def _proxy_ready(self, original, proxy) -> None:
        self._proxy_paths[Path(original)] = Path(proxy)
        self._refresh_bin()
        if self.use_proxies:
            self._refresh()
        if not self.proxies.busy:
            self.statusBar().showMessage("Proxies listos.", 4000)

    def _proxy_progress(self, original, avance: float) -> None:
        self.statusBar().showMessage(
            f"Proxy de {Path(original).name}: {avance * 100:.0f} %", 2000)

    def _free_audio_track(self, start: float, end: float):
        """La primera pista de audio libre en ese tramo, o A1 si no hay."""
        pistas = [p for p in self.sequence.audio_tracks() if not p.locked] \
            or self.sequence.audio_tracks()
        return next(
            (p for p in pistas
             if all(c.end <= start + 1e-9 or c.start >= end - 1e-9 for c in p.clips)),
            pistas[0])

    def _place_audio(self, path: Path, at: float | None = None, track_index: int = -1) -> None:
        """Un archivo de solo audio entra en la primera pista de audio libre.

        Libre en el tramo que va a ocupar, empezando en el playhead: así una
        música puesta encima de la voz cae sola en A2 en vez de pisar A1.
        Si todas están ocupadas ahí, se pega al final de A1.
        """
        if not HAS_PYAV:
            return
        try:
            info = self._media_info(path)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo abrir", f"{path.name}\n\n{error}")
            return
        if not info.has_audio:
            self.statusBar().showMessage(f"{path.name} no trae audio.", 5000)
            return

        start = self.timeline.playhead if at is None else max(0.0, at)
        end = start + info.duration
        destino = self._target_track(track_index, "audio")
        if destino is None:
            pistas = [p for p in self.sequence.audio_tracks() if not p.locked]
            destino = next(
                (p for p in pistas
                 if all(c.end <= start + 1e-9 or c.start >= end - 1e-9 for c in p.clips)),
                None)
            if destino is None:
                destino = pistas[0] if pistas else self.sequence.audio_tracks()[0]
                if at is None:
                    start = destino.duration

        clip = Clip(source=path, start=start, duration=info.duration)
        overwrite(destino, clip)
        destino.add(clip)
        self.timeline.waves.get(path)       # la onda empieza a calcularse ya
        self._fit_zoom()
        self.timeline.select(clip)
        self._commit("Importar audio")
        self.statusBar().showMessage(f"{path.name} → {destino.name}", 4000)

    def _place_image(self, path: Path, at: float | None = None, track_index: int = -1) -> None:
        """Las imágenes entran a V2, la pista de arriba: van sobre el video."""
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.critical(self, "No se pudo abrir", path.name)
            return

        self._images[path] = image
        overlay = ImageOverlay(start=self.timeline.playhead if at is None else max(0.0, at),
                               duration=DEFAULT_IMAGE_SECONDS, source=path)
        pista = self._target_track(track_index, "video") or self.sequence.video_tracks()[0]
        overwrite(pista, overlay)
        pista.add(overlay)
        self.timeline.select(overlay)
        self.image_panel.set_target(overlay)
        self._commit("Insertar imagen")
        self.panel.show()
        self.panel.show_page(self.image_panel)

    def export_frame(self) -> None:
        if self.preview.is_empty and self.sequence.duration <= 0:
            self.statusBar().showMessage("No hay ningún cuadro en pantalla.", 4000)
            return
        # Del original y a tamaño completo, aunque el preview use proxies.
        image = self._renderer().compose(self.timeline.playhead,
                                         self.sequence.width, self.sequence.height)

        stamp = timecode(self.timeline.playhead, self.sequence.fps).replace(":", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar cuadro", f"cuadro_{stamp}.png", EXPORT_FILTER)
        if path and not image.save(path):
            QMessageBox.critical(self, "No se pudo guardar", path)

    # --- exportar video ---------------------------------------------------

    def export_video(self) -> None:
        if self.sequence.duration <= 0:
            self.statusBar().showMessage("La secuencia está vacía: nada que exportar.", 4000)
            return
        if not HAS_PYAV:
            QMessageBox.warning(self, "Falta PyAV",
                                "Sin PyAV no se puede codificar video.")
            return

        start, end = self._range()
        options = ExportDialog(self, start, end, self.sequence)
        if options.exec() != QDialog.Accepted:
            return

        preset = options.export_preset()
        solo_audio = preset.kind == AUDIO_PRESET
        if solo_audio and not self._audio_clips():
            self.statusBar().showMessage("No hay audio que exportar.", 5000)
            return

        nombre = self._path.stem if self._path else ("audio" if solo_audio else "video")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar audio" if solo_audio else "Exportar video",
            f"{nombre}{preset.extension}",
            AUDIO_OUT_FILTER if solo_audio else VIDEO_OUT_FILTER)
        if not path:
            return

        self.queue_export(Path(path).with_suffix(preset.extension), start, end,
                          options.quality(), options.with_audio(), preset)

    def queue_export(self, path: Path, start: float, end: float, quality: str = "Normal",
                     with_audio: bool = True, preset=DEFAULT_PRESET) -> RenderJob:
        """Manda la exportación a la cola y deja seguir editando.

        Se lleva una copia congelada de la secuencia: lo que se edite después
        de darle Exportar ya no cambia el archivo.
        """
        self._flush()
        job = RenderJob(path=Path(path), sequence=sequence_to_dict(self.sequence),
                        nested={s.id: sequence_to_dict(s) for s in self.project.sequences
                                if s is not self.sequence},
                        media=dict(self.project.media), start=start, end=end,
                        preset=preset, quality=quality, with_audio=with_audio)
        self.render_queue.add(job)
        self.queue_panel.show()
        self.statusBar().showMessage(
            f"Exportando {job.name} en segundo plano. Puedes seguir editando.", 6000)
        return job

    def export_by_markers(self) -> None:
        """Un archivo por tramo entre marcadores, todos a la cola."""
        from vortex_studio.model.ranges import marker_ranges

        inicio, fin = self._range()
        if not marker_ranges(self.sequence, inicio, fin):
            self.statusBar().showMessage("Pon marcadores (M) donde empieza cada parte.", 5000)
            return
        opciones = ExportDialog(self, inicio, fin, self.sequence)
        if opciones.exec() != QDialog.Accepted:
            return
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta para los tramos")
        if carpeta:
            self.queue_marker_exports(Path(carpeta), opciones.export_preset(),
                                      opciones.quality(), opciones.with_audio())

    def queue_marker_exports(self, folder: Path, preset=DEFAULT_PRESET, quality: str = "Normal",
                             with_audio: bool = True) -> list:
        from vortex_studio.model.ranges import marker_ranges, numbered_names

        inicio, fin = self._range()
        tramos = marker_ranges(self.sequence, inicio, fin)
        if not tramos:
            self.statusBar().showMessage("No hay marcadores en el tramo.", 5000)
            return []
        trabajos = [self.queue_export(Path(folder) / f"{nombre}{preset.extension}",
                                      tramo.start, tramo.end, quality, with_audio, preset)
                    for tramo, nombre in zip(tramos, numbered_names(tramos))]
        self.statusBar().showMessage(f"{len(trabajos)} tramos en la cola de render.", 6000)
        return trabajos

    def _render_finished(self, job) -> None:
        if job.status == DONE:
            self.statusBar().showMessage(
                f"Exportado: {job.name}  ·  {job.end - job.start:.1f} s  ·  "
                f"{job.elapsed:.1f} s de render", 10000)
        elif job.status == FAILED:
            self.statusBar().showMessage(f"Falló la exportación de {job.name}: {job.error}",
                                         15000)
        elif job.status == CANCELLED:
            self.statusBar().showMessage(f"Exportación cancelada: {job.name}", 5000)

    def _audio_clips(self) -> list:
        """Lo que suena: respeta silencio y solo por pista, y el modo Silenciar."""
        return self.sequence.audio_clips(self.project.sequence_by_id)

    def _renderer(self) -> SequenceRenderer:
        """El armador de cuadros de la secuencia actual, con los
        decodificadores e imágenes de la ventana."""
        return SequenceRenderer(self.sequence, self.project.media, self._sources, self._images,
                                resolve=self.project.sequence_by_id)

    def _aspect_of(self, clip) -> float | None:
        return self._renderer().aspect_of(clip)

    def _run_export(self, path: Path, start: float, end: float,
                    quality: str, with_audio: bool, preset=DEFAULT_PRESET) -> bool:
        """Exporta con el preset elegido. Devuelve si el archivo quedó hecho."""
        if preset.kind == AUDIO_PRESET:
            return self._run_audio_export(path, start, end)

        fps = self.sequence.fps
        total = max(1, int(round((end - start) * fps)))
        ancho, alto = output_size(preset, self.sequence.width, self.sequence.height)

        dialog = QProgressDialog("Exportando…", "Cancelar", 0, total, self)
        dialog.setWindowTitle("Exportar video")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)

        def report(done: int, of: int) -> bool:
            dialog.setValue(done)
            dialog.setLabelText(
                f"Cuadro {done} de {of}   ·   {timecode(start + done / fps, fps)}")
            return not dialog.wasCanceled()

        try:
            export_video(
                path,
                self._frames(start, end, fps, (ancho, alto)),
                total,
                ancho,
                alto,
                fps,
                quality,
                report,
                AudioMixer(self._audio_clips(), **self.sequence.audio_mix_options())
                .stream(start, end)
                if with_audio and self._audio_clips() else None,
            )
        except Cancelled:
            dialog.close()
            return False
        except Exception as error:
            dialog.close()
            QMessageBox.critical(self, "Falló la exportación", str(error))
            return False
        finally:
            self._seek(self.timeline.playhead)

        dialog.close()
        # A la barra de estado y no a un diálogo: terminar de exportar no
        # amerita detener al usuario con un clic de "Aceptar".
        sonido = "con audio" if with_audio and self._audio_clips() else "sin audio"
        self.statusBar().showMessage(
            f"Exportado: {path.name}  ·  {ancho}×{alto}  ·  {total} cuadros  ·  "
            f"{(end - start):.1f} s  ·  {sonido}", 10000)
        return True

    def _run_audio_export(self, path: Path, start: float, end: float) -> bool:
        if not self._audio_clips():
            self.statusBar().showMessage("No hay audio que exportar.", 5000)
            return False

        total = max(1, int(round((end - start) * 1000)))
        dialog = QProgressDialog("Exportando audio…", "Cancelar", 0, total, self)
        dialog.setWindowTitle("Exportar audio")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)

        def report(done: int, of: int) -> bool:
            dialog.setValue(done)
            dialog.setLabelText(f"{done / 1000:.1f} de {of / 1000:.1f} s")
            return not dialog.wasCanceled()

        try:
            export_audio(path, AudioMixer(self._audio_clips(), **self.sequence.audio_mix_options())
                         .stream(start, end),
                         end - start, report)
        except Cancelled:
            dialog.close()
            return False
        except Exception as error:
            dialog.close()
            QMessageBox.critical(self, "Falló la exportación", str(error))
            return False

        dialog.close()
        self.statusBar().showMessage(
            f"Exportado: {path.name}  ·  solo audio  ·  {(end - start):.1f} s", 10000)
        return True

    def _frames(self, start: float, end: float, fps: float, size=None):
        """Va entregando el cuadro compuesto de cada instante. Ver `ui/renderer.py`."""
        yield from self._renderer().frames(start, end, fps, size)

    def _preview_path(self, clip) -> Path:
        """De qué archivo lee el preview: el proxy si está prendido y existe."""
        if self.use_proxies:
            proxy = self._proxy_paths.get(Path(clip.source))
            if proxy is not None:
                return proxy
        return clip.source

    def _jobs_at(self, t: float) -> list[tuple]:
        """(clip, trabajo de decodificación, peso) de cada capa en ese instante.

        Una capa de color liso no tiene trabajo: va con `None`.
        """
        plan = []
        for clip, peso in self.sequence.video_stack_at(t, self._aspect_of):
            if isinstance(clip, (Fill, AdjustmentLayer)):
                plan.append((clip, None, peso))
                continue
            if isinstance(clip, NestedClip):
                datos, firma, medios = self._project_snapshot()
                vista = animate.view(clip, local_in(clip, t))
                trabajo = FrameJob.make(
                    id(clip), Path(f"secuencia-{clip.sequence_id}-{firma}"),
                    clip.source_time(inside(clip, t)), vista.color, None,
                    nested=(datos, firma, clip.sequence_id, medios))
                plan.append((clip, trabajo, peso))
                continue
            vista = animate.view(clip, local_in(clip, t))
            trabajo = FrameJob.make(id(clip), self._preview_path(clip),
                                    clip.source_time(inside(clip, t)), vista.color,
                                    vista.chroma)
            plan.append((clip, trabajo, peso))
        return plan

    def _layers_at(self, t: float, sync: bool = False) -> list[Layer]:
        """Las capas de video del instante, de abajo hacia arriba.

        Quién va en la pila lo decide la secuencia: una capa por pista de
        video con material, más una extra por cada transición viva.

        Para el preview (`sync=False`) **nunca se decodifica aquí**: se toma
        el cuadro del servidor si ya está, o el último que hubo de ese clip
        mientras llega el nuevo, y se encarga lo que falte. Para exportar
        (`sync=True`) sí se decodifica en orden, porque el archivo final no
        puede llevar cuadros atrasados.
        """
        if sync:
            return self._renderer().layers(t)

        capas = []
        trabajos = []
        for clip, trabajo, peso in self._jobs_at(t):
            if trabajo is None:
                capas.append(adjustment_layer(clip, t, peso) if isinstance(clip, AdjustmentLayer)
                             else fill_layer(clip, peso))
                continue
            frame = self.frames.get(trabajo) or self.frames.latest(trabajo.key)
            trabajos.append(trabajo)
            capas.append(layer_for(clip, frame, t, peso, self.sequence.fps))

        if trabajos and HAS_PYAV:
            self.frames.request(trabajos, self._ahead(t))
        return capas

    def _ahead(self, t: float) -> list:
        """Los cuadros que vienen, para que al reproducir ya estén listos."""
        if not self._playing:
            return []
        paso = self.sequence.frame_duration * max(self._speed, 0.25)
        adelante = []
        for i in range(1, READ_AHEAD + 1):
            adelante += [trabajo for _, trabajo, _ in self._jobs_at(t + i * paso)
                         if trabajo is not None]
        return adelante

    def _frames_ready(self) -> None:
        """Llegaron cuadros nuevos. Se repinta una vez, aunque lleguen varios.

        El hilo avisa por cada cuadro; sin juntar los avisos, una lectura
        adelantada de ocho cuadros serían ocho repintados seguidos.
        """
        if self._ready_scheduled:
            return
        self._ready_scheduled = True
        QTimer.singleShot(0, self._apply_ready)

    def _apply_ready(self) -> None:
        self._ready_scheduled = False
        self._render(self.timeline.playhead)

    def _settle_preview(self) -> None:
        """Antes de sacar el cuadro en limpio, espera al cuadro exacto.

        Pintar la pantalla nunca espera: se ve el cuadro anterior mientras
        llega el nuevo. Pero exportar un cuadro, o una prueba que mide
        pixeles, no puede llevarse el anterior.
        """
        if not HAS_PYAV:
            return
        t = self.timeline.playhead
        trabajos = [trabajo for _, trabajo, _ in self._jobs_at(t) if trabajo is not None]
        if trabajos:
            self.frames.wait_for(trabajos, timeout=10.0)
        self._render(t)

    def _frame_of(self, clip, t: float):
        """El cuadro de ese clip en ese instante, ya corregido de color.

        El tiempo se puede salir del clip durante una transición: se recorta
        a su material para no pedirle al archivo algo que no tiene.
        """
        return self._renderer().frame_of(clip, t)

    def _frame_at(self, t: float):
        """El cuadro de fondo suelto, sin transición. Lo usa la exportación."""
        clip = self.sequence.top_clip_at(t)
        return self._frame_of(clip, t)

    # --- edición ----------------------------------------------------------

    def set_format(self, ancho: int, alto: int) -> None:
        """Cambia el tamaño del cuadro: vertical para redes, ancho para cine.

        El material no se recorta: se acomoda dentro del cuadro nuevo y lo
        que sobra queda negro. Desde ahí se encuadra con el panel
        Transformar, que es donde el usuario decide qué se ve.
        """
        self.sequence.width, self.sequence.height = ancho, alto
        self.preview.set_canvas(ancho, alto)
        self._commit(f"Formato {ancho}×{alto}")
        self.statusBar().showMessage(
            f"Formato {ancho}×{alto}. Para llenarlo sin franjas: Secuencia › "
            f"Rellenar el cuadro con todos los clips.", 6000)

    def format_from_clip(self) -> None:
        clip = next((c for track in self.sequence.video_tracks()
                     for c in track.clips if isinstance(c, Clip)), None)
        if clip is None:
            return
        try:
            info = self._media_info(clip.source)
        except Exception:
            return
        if info.width:
            self.set_format(info.width, info.height)

    def _track_of(self, item):
        return self.sequence.track_of(item)

    def set_tool(self, tool: str) -> None:
        self.timeline.set_tool(tool)
        accion = getattr(self, "_tool_actions", {}).get(tool)
        if accion is not None and not accion.isChecked():
            accion.setChecked(True)
        self._update_status()

    def cut_at_playhead(self) -> None:
        """Corta lo que esté seleccionado, o todo lo que cruce el playhead."""
        t = self.timeline.playhead
        seleccion = self.timeline.selected_items(with_links=False)
        # Sin selección se corta todo lo que cruce el playhead, en todas las
        # pistas: antes solo se cortaba la de hasta arriba y el video quedaba
        # partido y su audio no.
        targets = seleccion or [c for track in self.sequence.tracks
                                for c in track.items_at(t)]
        self._run(Split(items=targets, time=t, name="Cortar",
                        with_links=not self.timeline.ignore_link))

    def _cut(self, item, t: float, commit: bool = True) -> bool:
        """Parte un elemento —y su enlazado— en dos por el tiempo `t`.

        La lógica vive en `model/commands.py`, donde se prueba sin ventana;
        ahí está por qué cada mitad se lleva solo lo que le toca.
        """
        comando = Split(items=[item], time=t, name="Cortar")
        if not comando.apply(self.sequence):
            return False

        if commit:
            segunda = next((c for c in comando.created
                            if self._track_of(c) is self._track_of(item)), comando.created[0])
            self.timeline.select(segunda)
            self._commit("Cortar")
        return True

    def duplicate_selected(self) -> None:
        """Pega una copia justo después de lo seleccionado, sin dejar hueco."""
        items = self.timeline.selected_items(with_links=False)
        if not items:
            return
        entradas = copy_items(self.sequence, items, with_links=not self.timeline.ignore_link)
        fin = max(i.end for i in self.sequence.with_linked(items))
        comando = Paste(entries=entradas, time=fin, name="Duplicar")
        if self._run(comando):
            self._select_many(comando.created)

    def set_fade(self, entrada: float | None = None, salida: float | None = None) -> None:
        """Fundidos del elemento seleccionado, o del que esté bajo el playhead."""
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        if item is None:
            return

        if entrada is not None:
            item.fade_in = min(entrada, item.duration)
        if salida is not None:
            item.fade_out = min(salida, item.duration)
        self._commit("Fundido")

    def set_clip_speed(self, speed: float) -> None:
        """Cámara lenta o rápida. Solo aplica a clips de archivo."""
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        self._apply_speed(item, speed)

    def _apply_speed(self, item, speed: float) -> None:
        """La velocidad cambia junto en el video y en su audio enlazado."""
        if not isinstance(item, Clip):
            return
        if self._run(SetSpeed(clip=item, speed=speed, name=f"Velocidad {speed:g}×")):
            self._fit_zoom()
            self._sync_panels(self.timeline.playhead)

    def set_audio_mode(self, modo: str) -> None:
        """Qué hace el sonido a otra velocidad, en el clip y su enlazado."""
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        if not isinstance(item, Clip) or modo not in AUDIO_MODES:
            return
        for clip in self.sequence.with_linked([item]):
            if isinstance(clip, Clip):
                clip.audio_mode = modo
        self._commit(f"Audio: {modo.lower()}")
        self._sync_panels(self.timeline.playhead)

    def set_dissolve(self, seconds: float, kind: str | None = None) -> None:
        """Pone una transición con el clip de la izquierda: cruzada, o
        pasando por negro o por blanco."""
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        if not isinstance(item, Clip):
            return

        track = self._track_of(item)
        anterior = track.before(item) if track else None
        if anterior is None:
            # Aviso en la barra, no en un diálogo: un modal para esto
            # interrumpe el trabajo por algo que se corrige solo moviendo
            # el clip, y además vuelve la función imposible de probar.
            if seconds > 0:
                self.statusBar().showMessage(
                    "La transición necesita otro clip pegado a la izquierda.", 4000)
            return

        # No puede durar más que la mitad de ninguno de los dos, o el cruce
        # se saldría del material disponible.
        tope = min(item.duration, anterior.duration)
        item.dissolve = min(seconds, tope)
        if kind is not None:
            item.transition = kind
        nombres = {CROSS: "Transición", DIP_BLACK: "Fundido a negro",
                   DIP_WHITE: "Fundido a blanco"}
        self._commit("Quitar transición" if seconds <= 0
                     else nombres.get(item.transition, "Transición"))

    def key_all_transform(self) -> None:
        """Clava un keyframe de las cinco propiedades donde está el playhead.

        Es el gesto que más se repite al animar: fijar el estado de partida
        antes de mover el playhead y cambiar algo.
        """
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        if not isinstance(item, Clip):
            return

        local = item.local(self.timeline.playhead)
        for prop in PROPS:
            item.transform.set_key(prop, local, item.transform.at(prop, local))

        self._commit("Keyframe de todo")
        self._sync_panels(self.timeline.playhead)

    def clear_transform_keys(self) -> None:
        item = self.timeline.selected or self.sequence.top_clip_at(self.timeline.playhead)
        if not isinstance(item, Clip) or not item.transform.keys:
            return
        item.transform.clear_keys()
        self._commit("Quitar animación")
        self._sync_panels(self.timeline.playhead)

    def freeze_frame(self) -> None:
        """Convierte el cuadro actual en una imagen fija de 2 segundos.

        Se hace partiendo el clip en el playhead y dejando la mitad derecha
        con velocidad cero — es la manera más simple de congelar sin tener
        que escribir un archivo intermedio.
        """
        t = self.timeline.playhead
        clip = self.sequence.top_clip_at(t)
        if clip is None:
            return

        # Sin enlace a propósito: el cuadro congelado es solo imagen, y el
        # audio sigue su curso en su pista.
        congelado = split_item(self.sequence, clip, t)
        if congelado is not None:
            congelado.speed = 0.0       # el tiempo del archivo deja de avanzar
            congelado.duration = 2.0
            congelado.link = ""
            self.timeline.select(congelado)
        self._commit("Congelar cuadro")

    # --- capa: fusión, máscara y cuadro dentro de cuadro --------------------

    def _layer_target(self):
        """La capa sobre la que actúan los comandos de Capa.

        Lo seleccionado si se puede pintar, y si no el video que esté bajo
        el playhead. Un clip de una pista de audio no cuenta: no hay nada
        que tapar ni con qué fusionar.
        """
        item = self.timeline.selected
        if isinstance(item, ImageOverlay):
            return item
        if isinstance(item, Clip):
            pista = self._track_of(item)
            if pista is not None and pista.kind == "audio":
                return None
            return item
        return self.sequence.top_clip_at(self.timeline.playhead)

    def set_blend(self, nombre: str) -> None:
        item = self._layer_target()
        if item is None or nombre not in BLENDS:
            return
        item.blend = nombre
        self._commit(f"Fusión: {nombre.lower()}")
        self._sync_panels(self.timeline.playhead)

        if nombre != "Normal" and len(self.sequence.video_stack_at(
                self.timeline.playhead)) < 2:
            self.statusBar().showMessage(
                "Un modo de fusión mezcla con la pista de abajo, y ahí no "
                "hay nada todavía.", 6000)

    def set_mask_shape(self, nombre: str) -> None:
        item = self._layer_target()
        if item is None or nombre not in SHAPES:
            return
        item.mask.shape = nombre
        self._commit("Quitar máscara" if nombre == "Ninguna"
                     else f"Máscara: {nombre.lower()}")
        self._sync_panels(self.timeline.playhead)
        self.panel.show_page(self.mask_panel)

    def invert_mask(self) -> None:
        item = self._layer_target()
        if item is None or item.mask.is_off:
            return
        item.mask.invert = not item.mask.invert
        self._commit("Invertir máscara")
        self._sync_panels(self.timeline.playhead)

    def picture_in_picture(self) -> None:
        """Encoge la capa y la manda a la esquina de arriba a la derecha.

        Con el apilado de pistas esto ya se podía armar a mano en el panel
        Transformar, pero nadie lo iba a descubrir. Un comando que lo deja
        hecho es lo que vuelve visible que V1 y V2 ahora se ven las dos.
        """
        item = self._layer_target()
        if not isinstance(item, Clip):
            return

        item.transform.clear_keys()
        item.transform.scale = 0.34
        item.transform.x, item.transform.y = 0.30, -0.30
        self._commit("Cuadro dentro de cuadro")
        self._sync_panels(self.timeline.playhead)
        self._render(self.timeline.playhead)

        if len(self.sequence.video_stack_at(self.timeline.playhead)) < 2:
            self.statusBar().showMessage(
                "Listo. Pon el video de fondo en la pista de abajo para que "
                "se vea detrás.", 6000)

    def set_fit(self, modo: str) -> None:
        """Cómo cae el material en el cuadro: ajustar, rellenar o estirar."""
        item = self._layer_target()
        if not isinstance(item, Clip) or modo not in FIT_MODES:
            return
        item.transform.fit = modo
        self._commit(f"Encuadre: {modo.lower()}")
        self._sync_panels(self.timeline.playhead)

    def reframe_all(self, modo: str = FILL) -> None:
        """Todos los clips de video con el mismo encuadre.

        Es el gesto de pasar un horizontal a vertical: se cambia el formato
        de la secuencia y se rellena el cuadro con todo, sin clip por clip.
        """
        clips = [c for t in self.sequence.video_tracks() if not t.locked
                 for c in t.clips if isinstance(c, Clip)]
        cambiados = [c for c in clips if c.transform.fit != modo]
        for clip in cambiados:
            clip.transform.fit = modo
        if cambiados:
            self._commit(f"Encuadre de todo: {modo.lower()}")
            self._sync_panels(self.timeline.playhead)

    def fill_frame(self) -> None:
        """Regresa la capa a llenar el cuadro. El deshacer del anterior."""
        item = self._layer_target()
        if not isinstance(item, Clip):
            return
        item.transform.reset()
        self._commit("Llenar el cuadro")
        self._sync_panels(self.timeline.playhead)
        self._render(self.timeline.playhead)

    def delete_selected(self) -> None:
        items = self.timeline.selected_items(with_links=False)
        if not items:
            return
        if self._run(Delete(items=items, with_links=not self.timeline.ignore_link)):
            self.timeline.select(None)
        else:
            self.statusBar().showMessage("Está en una pista bloqueada.", 4000)

    def ripple_delete(self) -> None:
        """Borra y recorre lo que sigue en esa pista, para no dejar hueco."""
        item = self.timeline.selected
        if item is None:
            return
        if self._run(RippleDelete(item=item, with_links=not self.timeline.ignore_link)):
            self.timeline.select(None)

    # --- portapapeles y enlace --------------------------------------------

    def _select_many(self, items: list) -> None:
        if not items:
            return
        self.timeline.select(items[0])
        self.timeline.extra = list(items[1:])
        self.timeline.update()

    def copy_selected(self) -> int:
        """Copia lo seleccionado —con su enlazado— para pegarlo después."""
        items = self.timeline.selected_items(with_links=False)
        if not items:
            self.statusBar().showMessage("Selecciona algo para copiar.", 3000)
            return 0
        self._clipboard = copy_items(self.sequence, items,
                                     with_links=not self.timeline.ignore_link)
        n = len(self._clipboard)
        self.statusBar().showMessage(f"Copiado: {n} elemento{'s' if n != 1 else ''}.", 3000)
        return n

    def cut_to_clipboard(self) -> None:
        if not self.copy_selected():
            return
        items = self.timeline.selected_items(with_links=False)
        if self._run(Delete(items=items, with_links=not self.timeline.ignore_link,
                            name="Cortar")):
            self.timeline.select(None)

    def paste(self) -> None:
        """Pega en el playhead, cada cosa en su pista, y deja el playhead al final.

        Así, pegar varias veces seguidas pone las copias una detrás de otra,
        que es lo que hace Premiere.
        """
        if not self._clipboard:
            self.statusBar().showMessage("No hay nada copiado.", 3000)
            return
        comando = Paste(entries=self._clipboard, time=self.timeline.playhead)
        if not self._run(comando):
            self.statusBar().showMessage("No hay una pista libre donde pegarlo.", 4000)
            return
        self._select_many(comando.created)
        self._fit_zoom()
        self._scrubbed(max(c.end for c in comando.created))

    def clipboard_source(self):
        """El elemento principal de lo copiado, reconstruido."""
        if not self._clipboard:
            return None
        return item_from_dict(self._clipboard[0]["data"])

    def paste_attributes(self) -> None:
        source = self.clipboard_source()
        if source is None:
            self.statusBar().showMessage("Primero copia el clip del que quieres los ajustes.",
                                         4000)
            return
        dialogo = PasteAttributesDialog(self, source)
        if dialogo.exec() == QDialog.Accepted:
            self.paste_attributes_with(dialogo.groups())

    def paste_attributes_with(self, groups) -> bool:
        source = self.clipboard_source()
        targets = self.timeline.selected_items(with_links=False)
        if not targets:
            debajo = self.sequence.top_clip_at(self.timeline.playhead)
            targets = [debajo] if debajo else []
        if source is None or not targets or not groups:
            return False
        hecho = self._run(PasteAttributes(source=source, targets=targets, groups=tuple(groups)))
        if hecho:
            self._fit_zoom()
            self._sync_panels(self.timeline.playhead)
        return hecho

    def toggle_link(self) -> None:
        """Ctrl+L: desenlaza si algo está enlazado; si no, enlaza lo seleccionado."""
        items = self.timeline.selected_items(with_links=False)
        if not items:
            return
        if any(getattr(i, "link", "") for i in items):
            self._run(Unlink(items=items))
        elif not self._run(Link(items=items)):
            self.statusBar().showMessage(
                "Para enlazar, selecciona con Ctrl+clic un video y un audio.", 5000)

    # --- pistas -----------------------------------------------------------

    def set_track_flag(self, track, nombre: str, valor: bool) -> None:
        if getattr(track, nombre) == valor:
            return
        setattr(track, nombre, valor)
        self._track_toggled(track, nombre)

    def _track_toggled(self, track, nombre: str) -> None:
        """Un interruptor de pista cambió. Entra al historial y se oye al momento."""
        etiqueta = TRACK_FLAG_LABELS.get((nombre, getattr(track, nombre)), "Pista {}")
        if track.locked and self.timeline.selected is not None and \
                self._track_of(self.timeline.selected) is track:
            self.timeline.select(None)
        self._commit(etiqueta.format(track.name))
        if self._playing and track.kind == "audio":
            # La mezcla se arma al dar play: hay que rearmarla para que el
            # silencio o el solo se oigan sin detener la reproducción.
            origen = self.timeline.playhead
            self._pause()
            self._seek(origen)
            self._play()

    def _run(self, command) -> bool:
        """Aplica un comando de `model/commands.py` y lo registra con su nombre."""
        if not command.apply(self.sequence):
            return False
        self._commit(command.name)
        return True

    def _source_duration(self, clip) -> float | None:
        """Cuánto dura el archivo del clip, del caché de sondeos."""
        try:
            return self._media_info(clip.source).duration or None
        except Exception:
            return None

    def slip_selected(self, frames: int) -> None:
        """Desliza el contenido del clip seleccionado, de cuadro en cuadro.

        Un cuadro de la secuencia, contado en tiempo de archivo: en un clip a
        2× cada paso recorre dos cuadros del original, igual que al verlo.
        """
        clip = self.timeline.selected
        if not isinstance(clip, Clip):
            self.statusBar().showMessage("Selecciona un clip de video o de audio.", 4000)
            return

        delta = frames * self.sequence.frame_duration * max(clip.speed, 0.0)
        comando = Slip(clip=clip, delta=delta, source_duration=self._source_duration(clip))
        if self._run(comando):
            self.statusBar().showMessage(
                f"Entrada en {timecode(clip.in_point, self.sequence.fps)}", 3000)
        else:
            lado = "antes" if frames < 0 else "después"
            self.statusBar().showMessage(f"No hay más material {lado}.", 4000)

    # --- marcadores de clip ------------------------------------------------

    def add_marker_to_clip(self, name: str = "") -> Marker | None:
        """Marcador dentro del clip seleccionado, donde está el playhead.

        Viaja con el clip: si lo mueves, el marcador va con él.
        """
        t = self.timeline.playhead
        item = self.timeline.selected or self.sequence.top_clip_at(t)
        if item is None or not hasattr(item, "markers") or not item.contains(t):
            self.statusBar().showMessage(
                "El playhead tiene que estar sobre el clip seleccionado.", 4000)
            return None
        local = round(t - item.start, 6)
        medio = self.sequence.frame_duration / 2
        item.markers = [m for m in item.markers if abs(m.time - local) > medio]
        marcador = Marker(time=local, name=name)
        item.markers.append(marcador)
        item.markers.sort(key=lambda m: m.time)
        self._commit("Marcador en el clip")
        return marcador

    def edit_marker(self, marker, owner=None) -> None:
        """Abre el marcador para ponerle nombre, nota y color."""
        dialogo = MarkerDialog(self, marker, owner.name if owner is not None else "")
        resultado = dialogo.exec()
        if resultado == MarkerDialog.DELETE:
            self.delete_marker(marker, owner)
        elif resultado == QDialog.Accepted:
            self.update_marker(marker, owner, **dialogo.values())

    def update_marker(self, marker, owner=None, name: str = "", note: str = "",
                      color: str | None = None) -> None:
        marker.name, marker.note = name, note
        if color:
            marker.color = color
        self._commit("Editar marcador")

    def delete_marker(self, marker, owner=None) -> None:
        lista = owner.markers if owner is not None else self.sequence.markers
        quedan = [m for m in lista if m is not marker]
        if len(quedan) == len(lista):
            return
        if owner is not None:
            owner.markers = quedan
        else:
            self.sequence.markers = quedan
        self._commit("Borrar marcador")

    def _selected(self, item) -> None:
        """Al seleccionar en el timeline, los paneles siguen la selección."""
        self._follow_selection(item)

        # La pestaña de Máscara se apaga si lo seleccionado no se pinta. Se
        # hace aquí y no solo al mover el playhead porque si no, seleccionar
        # un clip de audio dejaba la pestaña encendida con el panel vacío —
        # y una pestaña encendida que no hace nada parece un programa roto.
        self.panel.set_enabled(self.mask_panel,
                               self.mask_panel.target is not None)

    def _follow_selection(self, item) -> None:
        if isinstance(item, AdjustmentLayer):
            self.color_panel.set_target(item.color, item.name)
            self.mask_panel.set_target(item)
            self.panel.set_enabled(self.color_panel, True)
            if not self.panel.current_is(self.color_panel, self.mask_panel):
                self.panel.show_page(self.color_panel)
            return
        if isinstance(item, Title):
            self._title = item
            self.text_panel.set_titles(self._titles_in_track(), item)
            self.panel.show_page(self.text_panel)
        elif isinstance(item, ImageOverlay):
            self.image_panel.set_target(item)
            self.mask_panel.set_target(item)
            if not self.panel.current_is(self.mask_panel):
                self.panel.show_page(self.image_panel)
        elif isinstance(item, Clip):
            track = self._track_of(item)
            es_audio = bool(track and track.kind == "audio")
            self.clip_panel.set_target(item, es_audio)
            self.transform_panel.set_target(None if es_audio else item,
                                            item.local(self.timeline.playhead))
            self.color_panel.set_target(item.color, item.name)
            self.mask_panel.set_target(None if es_audio else item)
            self.effects_panel.set_target(None if es_audio else item)
            self.audio_panel.set_target(item if es_audio else None,
                                        track if es_audio else None, self.sequence)
            self.panel.set_enabled(self.audio_panel, es_audio)
            self.panel.set_enabled(self.transform_panel, not es_audio)
            self.panel.set_enabled(self.effects_panel, not es_audio)

            # Solo se cambia de pestaña si la de ahora no aplica al clip. Si
            # el usuario ya estaba en Color o en Transformar, se respeta:
            # arrancarle la pestaña de abajo cada vez que selecciona algo es
            # de las cosas que más estorban de un editor.
            aplica = [self.clip_panel] + ([self.audio_panel] if es_audio else [])
            if not es_audio:
                aplica += [self.transform_panel, self.color_panel, self.mask_panel,
                           self.effects_panel]
            if not self.panel.current_is(*aplica):
                self.panel.show_page(self.clip_panel if es_audio
                                     else self.transform_panel)

    def _titles_in_track(self) -> list[Title]:
        return [c for track in self.sequence.text_tracks() for c in track.clips]

    # --- texto ------------------------------------------------------------

    def add_title(self, anchor: str = "Subtítulo") -> None:
        track = self.sequence.text_tracks()[0]     # T1
        x, y = ANCHORS.get(anchor, ANCHORS["Subtítulo"])

        title = Title(start=self.timeline.playhead, duration=DEFAULT_TITLE_SECONDS,
                      text="Texto nuevo", x=x, y=y)
        track.add(title)
        self._title = title

        self.timeline.select(title)
        self._commit("Insertar texto")
        self._sync_panels(self.timeline.playhead)
        self.panel.show()
        self.panel.show_page(self.text_panel)

    # --- scopes -------------------------------------------------------------

    def scope_image(self, width: int = 320):
        """El cuadro de ahora, chico, para los scopes. Nunca espera al decodificador:
        usa lo que el preview ya tiene."""
        from vortex_studio.ui.compositor import compose

        if self.preview.is_empty:
            return None
        alto = max(2, round(width * self.sequence.height / max(1, self.sequence.width)))
        return compose(width, alto, self.preview._layers, self.preview._overlays,
                       self.preview._titles, self.preview._time)

    def show_scopes(self) -> None:
        self.scopes.show()
        self.scopes.raise_()
        self.scopes.submit(self.scope_image())

    # --- subtítulos ---------------------------------------------------------

    def import_subtitles(self, path=None) -> int:
        """Cada subtítulo del archivo entra como un texto en la posición de subtítulo.

        Van a la primera pista de texto que esté libre en todo el tramo; si
        ninguna lo está, se crea otra arriba. Así importar nunca pisa los
        títulos que ya estaban.
        """
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Importar subtítulos", "",
                                                  "Subtítulos (*.srt *.vtt)")
            if not path:
                return 0
        try:
            cues = subtitles.read_file(path)
        except OSError as error:
            self.statusBar().showMessage(f"No se pudo leer {Path(path).name}: {error}", 6000)
            return 0
        if not cues:
            self.statusBar().showMessage(f"{Path(path).name} no trae subtítulos válidos.", 6000)
            return 0

        inicio, fin = cues[0].start, max(c.end for c in cues)
        pista = next((p for p in self.sequence.text_tracks() if not p.locked and
                      all(c.end <= inicio + 1e-9 or c.start >= fin - 1e-9 for c in p.clips)),
                     None)
        if pista is None:
            pista = Track(f"T{len(self.sequence.text_tracks()) + 1}", kind="texto")
            self.sequence.tracks.insert(0, pista)
            self.timeline.refresh()

        x, y = ANCHORS["Subtítulo"]
        for cue in cues:
            pista.add(Title(start=cue.start, duration=cue.end - cue.start, text=cue.text,
                            x=x, y=y, size=0.06, bold=False))
        self._fit_zoom()
        self._commit("Importar subtítulos")
        self.statusBar().showMessage(f"{len(cues)} subtítulos en {pista.name}.", 5000)
        return len(cues)

    def export_subtitles(self, path=None):
        """Escribe los textos de las pistas visibles como SRT o VTT."""
        textos = sorted((t for p in self.sequence.text_tracks() if p.enabled
                         for t in p.clips if isinstance(t, Title) and t.text.strip()),
                        key=lambda t: t.start)
        if not textos:
            self.statusBar().showMessage("No hay ningún texto que exportar.", 5000)
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Exportar subtítulos", "subtitulos.srt",
                                                  "SRT (*.srt);;WebVTT (*.vtt)")
            if not path:
                return None
        ruta = subtitles.write_file(path, [subtitles.Cue(t.start, t.end, t.text) for t in textos])
        self.statusBar().showMessage(f"{len(textos)} subtítulos en {ruta.name}.", 5000)
        return ruta

    # --- secuencias anidadas ---------------------------------------------------

    def _project_snapshot(self):
        """Todas las secuencias en datos planos, con su firma. Una vez por edición.

        Es lo que se le manda al hilo del decodificador para componer una
        anidada: datos congelados, nunca los objetos que se están editando.
        """
        if self._snapshot_memo is not None and self._snapshot_memo[0] == self._edit_serial:
            return self._snapshot_memo[1:]
        import hashlib
        import json

        datos = {s.id: sequence_to_dict(s) for s in self.project.sequences}
        firma = hashlib.sha1(json.dumps(datos, sort_keys=True, default=str)
                             .encode("utf-8")).hexdigest()[:12]
        self._snapshot_memo = (self._edit_serial, datos, firma, dict(self.project.media))
        return datos, firma, self._snapshot_memo[3]

    def _nested_frame_job(self, job):
        """Compone un cuadro de secuencia anidada. Corre en el hilo del decodificador."""
        from vortex_studio.model.serialize import sequence_from_dict
        from vortex_studio.media.color import ColorProcessor
        from vortex_studio.ui.renderer import color_frame, image_to_rgb_frame

        datos, firma, ident, medios = job.nested
        entrada = self._nested_workers.get(firma)
        if entrada is None:
            for vieja in self._nested_workers.values():
                for render in vieja[1].values():
                    render.close()
            self._nested_workers.clear()
            secuencias = {i: sequence_from_dict(d) for i, d in datos.items()}
            entrada = self._nested_workers[firma] = (secuencias, {}, ColorProcessor())
        secuencias, renders, procesador = entrada
        hija = secuencias.get(ident)
        if hija is None:
            return None
        render = renders.get(ident)
        if render is None:
            render = renders[ident] = SequenceRenderer(hija, dict(medios), resolve=secuencias.get)
        imagen = render.compose(job.time, hija.width, hija.height)
        return color_frame(image_to_rgb_frame(imagen), job.adjust, procesador)

    def new_sequence(self):
        nueva = Sequence.default()
        nueva.name = f"Secuencia {len(self.project.sequences) + 1}"
        nueva.width, nueva.height, nueva.fps = (self.sequence.width, self.sequence.height,
                                                self.sequence.fps)
        self.project.sequences.append(nueva)
        self._dirty = True
        self.switch_sequence(nueva.id)
        return nueva

    def switch_sequence(self, ident: str) -> bool:
        """Edita otra secuencia del proyecto. El historial arranca de nuevo."""
        destino = self.project.sequence_by_id(ident)
        if destino is None or destino is self.sequence:
            return False
        self._flush()
        self._pause()
        self.project.active_id = ident
        self._adopt(destino, reset_history=True)
        self._update_title()
        self.statusBar().showMessage(f"Editando «{destino.name}».", 4000)
        return True

    def open_nested(self, clip) -> bool:
        return isinstance(clip, NestedClip) and self.switch_sequence(clip.sequence_id)

    def insert_sequence(self, ident: str):
        """Mete otra secuencia como clip en el playhead, si no hace ciclo."""
        hija = self.project.sequence_by_id(ident)
        if hija is None:
            return None
        if would_cycle(self.project, self.sequence.id, ident):
            self.statusBar().showMessage(
                f"No se puede: meter «{hija.name}» aquí haría un ciclo.", 6000)
            return None
        if hija.duration <= 0:
            self.statusBar().showMessage(f"«{hija.name}» está vacía.", 4000)
            return None
        pista = next((p for p in reversed(self.sequence.video_tracks()) if not p.locked), None)
        if pista is None:
            return None
        anidada = NestedClip(source=Path(""), start=self.timeline.playhead,
                             duration=hija.duration, sequence_id=ident, name=hija.name)
        overwrite(pista, anidada)
        pista.add(anidada)
        self.timeline.select(anidada)
        self._fit_zoom()
        self._commit("Insertar secuencia")
        return anidada

    def nest_selection(self):
        """Mete lo seleccionado en una secuencia nueva y deja un clip en su lugar.

        Cada elemento conserva su pista y su distancia; la anidada cae en la
        pista de video más alta que tenía la selección.
        """
        items = self.timeline.selected_items(with_links=not self.timeline.ignore_link)
        items = [i for i in items if self._track_of(i) is not None
                 and not self._track_of(i).locked]
        if not items:
            self.statusBar().showMessage("Selecciona lo que quieres anidar.", 4000)
            return None

        madre = self.sequence
        inicio = min(i.start for i in items)
        fin = max(i.end for i in items)
        hija = Sequence.default()
        hija.name = f"Anidada {len(self.project.sequences)}"
        hija.width, hija.height, hija.fps = madre.width, madre.height, madre.fps
        por_nombre = {t.name: t for t in hija.tracks}

        destino = None
        for item in items:
            pista = self._track_of(item)
            copia_pista = por_nombre.get(pista.name)
            if copia_pista is None or copia_pista.kind != pista.kind:
                copia_pista = Track(pista.name, kind=pista.kind)
                hija.tracks.append(copia_pista)
                por_nombre[pista.name] = copia_pista
            copia = copy.deepcopy(item)
            copia.start -= inicio
            copia_pista.add(copia)
            if pista.kind == "video" and (destino is None or madre.tracks.index(pista)
                                          < madre.tracks.index(destino)):
                destino = pista

        for item in items:
            pista = self._track_of(item)
            pista.clips = [c for c in pista.clips if c is not item]
        destino = destino or madre.video_tracks()[-1]

        self.project.sequences.append(hija)
        anidada = NestedClip(source=Path(""), start=inicio, duration=fin - inicio,
                             sequence_id=hija.id, name=hija.name)
        overwrite(destino, anidada)
        destino.add(anidada)
        self.timeline.select(anidada)
        self._commit("Anidar")
        return anidada

    def _fill_switch_menu(self) -> None:
        self._switch_menu.clear()
        for secuencia in self.project.sequences:
            accion = self._switch_menu.addAction(secuencia.name)
            accion.setCheckable(True)
            accion.setChecked(secuencia is self.sequence)
            accion.triggered.connect(lambda _=False, i=secuencia.id: self.switch_sequence(i))

    def _fill_insert_menu(self) -> None:
        self._insert_menu.clear()
        for secuencia in self.project.sequences:
            accion = self._insert_menu.addAction(secuencia.name)
            accion.setEnabled(not would_cycle(self.project, self.sequence.id, secuencia.id))
            accion.triggered.connect(lambda _=False, i=secuencia.id: self.insert_sequence(i))

    def add_adjustment_layer(self, seconds: float = 5.0) -> AdjustmentLayer | None:
        """Una capa de ajuste en V2, en el playhead, encima del material."""
        pista = next((p for p in self.sequence.video_tracks() if not p.locked), None)
        if pista is None:
            self.statusBar().showMessage("Todas las pistas de video están bloqueadas.", 4000)
            return None
        capa = AdjustmentLayer(start=self.timeline.playhead, duration=seconds)
        overwrite(pista, capa)
        pista.add(capa)
        self.timeline.select(capa)
        self._commit("Capa de ajuste")
        self._sync_panels(self.timeline.playhead)
        return capa

    def delete_title(self, title: Title | None) -> None:
        if title is None:
            return
        for track in self.sequence.text_tracks():
            if title in track.clips:
                track.clips.remove(title)
        self._title = None
        self._commit("Eliminar texto")
        self._sync_panels(self.timeline.playhead)

    def _text_changed(self) -> None:
        self._title = self.text_panel._title
        for track in self.sequence.text_tracks():
            track.clips.sort(key=lambda c: c.start)
        self._schedule("Editar texto")

    def _color_changed(self) -> None:
        self._schedule("Corregir color")

    def _clip_committed(self, etiqueta: str) -> None:
        """Los cambios pesados del panel de clip: velocidad y transición."""
        if etiqueta.startswith("__dissolve__"):
            self.set_dissolve(float(etiqueta.removeprefix("__dissolve__")))
            return
        if etiqueta.startswith("__speed__"):
            self._apply_speed(self.clip_panel._item,
                              float(etiqueta.removeprefix("__speed__")))
            return
        self._fit_zoom()
        self._commit(etiqueta)

    def _image_changed(self) -> None:
        for track in self.sequence.video_tracks():
            track.clips.sort(key=lambda c: c.start)
        self._schedule("Ajustar imagen")
        self._update_status()

    # --- navegación -------------------------------------------------------

    def _seek(self, t: float) -> None:
        t = min(max(0.0, t), self.sequence.duration)
        self.timeline.set_playhead(t)
        self.transport.set_timecode(
            timecode(t, self.sequence.fps),
            timecode(self.sequence.duration, self.sequence.fps),
        )
        self._render(t)
        self._sync_panels(t)

    def _sync_panels(self, t: float) -> None:
        """Los paneles muestran lo que hay bajo el playhead.

        Sin esto habría que seleccionar el clip a mano antes de corregirlo,
        y el orden natural es al revés: te paras donde se ve mal y ajustas.
        """
        # Lo animado se muestra con su valor de este instante. Ver `bake`.
        for track in self.sequence.tracks:
            for item in track.items_at(t):
                animate.bake(item, local_in(item, t))

        clip = self.sequence.top_clip_at(t)
        if isinstance(self.timeline.selected, AdjustmentLayer):
            self.color_panel.set_target(self.timeline.selected.color, "Capa de ajuste")
        else:
            self.color_panel.set_target(clip.color if clip else None,
                                        clip.name if clip else "")

        seleccion = self.timeline.selected
        objetivo = seleccion if isinstance(seleccion, Clip) else clip
        pista = self._track_of(objetivo) if objetivo else None
        es_audio = bool(pista and pista.kind == "audio")
        self.clip_panel.set_target(objetivo, es_audio)
        # Un clip de una pista de audio no tiene imagen que transformar: la
        # pestaña se apaga en vez de quedar prendida sin hacer nada.
        self.transform_panel.set_target(
            None if es_audio else objetivo, objetivo.local(t) if objetivo else 0.0)

        # La máscara y la fusión aplican a lo que se pinta: un clip de video
        # o una imagen encima. En una pista de audio no hay nada que tapar.
        capa = seleccion if isinstance(seleccion, (ImageOverlay, AdjustmentLayer)) else (
            None if es_audio else objetivo)
        self.mask_panel.set_target(capa)


        titles = self.sequence.titles_at(t)
        if self._title not in titles:
            self._title = titles[0] if titles else None
        self.text_panel.set_titles(titles, self._title)

        overlays = self.sequence.overlays_at(t)
        selected = self.timeline.selected
        self.image_panel.set_target(
            selected if isinstance(selected, ImageOverlay) and selected in overlays
            else (overlays[-1] if overlays else None))

        # Las pestañas que no aplican se apagan, no se esconden: esconderlas
        # las haría bailar de lugar cada vez que cambia la selección.
        self.panel.set_enabled(self.text_panel, bool(titles))
        self.panel.set_enabled(self.image_panel, bool(overlays))
        self.panel.set_enabled(self.clip_panel, objetivo is not None)
        self.panel.set_enabled(self.transform_panel, objetivo is not None and not es_audio)
        self.panel.set_enabled(self.color_panel, clip is not None
                               or isinstance(seleccion, AdjustmentLayer))
        self.panel.set_enabled(self.mask_panel, capa is not None)
        efectos = None if es_audio or not isinstance(objetivo, Clip) else objetivo
        self.effects_panel.set_target(efectos)
        self.panel.set_enabled(self.effects_panel, efectos is not None)
        sonido = objetivo if es_audio and isinstance(objetivo, Clip) else None
        self.audio_panel.set_target(sonido, pista if sonido is not None else None, self.sequence)
        self.panel.set_enabled(self.audio_panel, sonido is not None)

        destino = seleccion if seleccion is not None else clip
        self.keyframe_editor.set_target(
            destino, local_in(destino, t) if destino is not None else 0.0)

    def normalize_loudness(self, target: float = -14.0, clips=None) -> dict:
        """Lleva cada clip de audio a `target` LUFS ajustando su volumen.

        Se mide cada clip por separado, con sus efectos pero sin su volumen
        ni sus fundidos: lo que se quiere igualar es el material. Devuelve
        lo que midió cada uno, en LUFS.
        """
        from vortex_studio.media.audio import AudioRenderer
        from vortex_studio.media.loudness import gain_for, integrated

        if clips is None:
            seleccion = [c for c in self.timeline.selected_items(with_links=False)
                         if isinstance(c, Clip)
                         and getattr(self._track_of(c), "kind", "") == "audio"]
            clips = seleccion or [c for t in self.sequence.audio_tracks() for c in t.clips]
        medidas = {}
        for clip in clips:
            prueba = copy.copy(clip)
            prueba.gain, prueba.fade_in, prueba.fade_out = 1.0, 0.0, 0.0
            prueba.anim = {k: v for k, v in (clip.anim or {}).items() if k != "gain"}
            try:
                lufs = integrated(AudioRenderer([prueba]).stream(clip.start, clip.end))
            except Exception:
                continue
            medidas[id(clip)] = lufs
            clip.anim.pop("gain", None)
            clip.gain = gain_for(lufs, target)
        if medidas:
            self._commit(f"Normalizar a {target:g} LUFS")
            self._sync_panels(self.timeline.playhead)
            self.statusBar().showMessage(
                f"{len(medidas)} clip{'s' if len(medidas) != 1 else ''} a {target:g} LUFS.", 5000)
        else:
            self.statusBar().showMessage("No hay audio que normalizar.", 4000)
        return medidas

    def _effects_committed(self, label: str) -> None:
        self._request_stabilization()
        self._commit(label)
        self._sync_panels(self.timeline.playhead)

    def _request_stabilization(self) -> None:
        """Encarga el análisis de los clips que piden estabilizar y no lo tienen."""
        fuentes = {Path(c.source) for t in self.sequence.video_tracks() for c in t.clips
                   if isinstance(c, Clip) and not isinstance(c, NestedClip)
                   and getattr(c, "stabilize", 0) > 0}
        if self.stabilizer.request(fuentes):
            self.effects_panel.set_stabilize_status("Analizando el movimiento…")

    def _stabilize_ready(self, path) -> None:
        self.effects_panel.set_stabilize_status("Listo: la toma ya se corrige.")
        self._refresh()

    def _animation_targets(self) -> list:
        t = self.timeline.playhead
        candidatos = [self.sequence.top_clip_at(t), self.clip_panel._item,
                      self.mask_panel.target, self.image_panel._overlay,
                      self.text_panel._title, self.timeline.selected]
        salida = []
        for item in candidatos:
            if item is not None and not any(item is x for x in salida):
                salida.append(item)
        return salida

    def _absorb_animation(self) -> None:
        """Lo que se movió en un panel sobre un valor animado se vuelve keyframe."""
        t = self.timeline.playhead
        for item in self._animation_targets():
            animate.absorb(item, local_in(item, t))

    def _keyframes_edited(self) -> None:
        self._dirty = True
        self._update_title()
        self._refresh()

    def _keyframes_committed(self, label: str) -> None:
        self._commit(label)
        self._sync_panels(self.timeline.playhead)

    def open_keyframe_editor(self, path: str | None = None) -> None:
        self.keyframe_editor.show()
        self.keyframe_editor.raise_()
        self._sync_panels(self.timeline.playhead)
        if path:
            self.keyframe_editor.select_param(path)

    def _scrubbed(self, t: float) -> None:
        """Arrastrar el playhead reubica el origen del reloj sin cortar el play."""
        self._origin = t
        self._elapsed.restart()
        self._seek(t)

    def _step(self, frames: int) -> None:
        self._pause()
        self._scrubbed(self.timeline.playhead + frames * self.sequence.frame_duration)

    def _skip(self, seconds: float) -> None:
        self._scrubbed(self.timeline.playhead + seconds)

    # --- caché de render ------------------------------------------------------

    def zones(self) -> list:
        """Las zonas de la secuencia, calculadas una vez por edición."""
        if self._zones_serial != self._edit_serial:
            _, firma, _ = self._project_snapshot()
            hay_anidadas = any(isinstance(c, NestedClip) for t in self.sequence.tracks
                               for c in t.clips)
            self._zones = render_zones.zones(self.sequence, firma if hay_anidadas else None)
            self._zones_serial = self._edit_serial
        return self._zones

    def _refresh_render_bar(self) -> None:
        self.timeline.render_bar = [
            (z.start, z.end, "listo" if render_cache.is_cached(z.signature) else z.level)
            for z in self.zones() if z.level > render_zones.NONE
            or render_cache.is_cached(z.signature)]
        self.timeline.update()

    def render_zones(self, start: float | None = None, end: float | None = None,
                     include_light: bool = False) -> int:
        """Renderiza las zonas pesadas del tramo que no estén en caché."""
        if start is None or end is None:
            start, end = self._range()
        pendientes = [z for z in self.zones() if z.end > start + 1e-6 and z.start < end - 1e-6
                      and (z.level == render_zones.HEAVY
                           or (include_light and z.level == render_zones.LIGHT))
                      and not render_cache.is_cached(z.signature)]
        if not pendientes:
            self.statusBar().showMessage("No hay zonas pesadas por renderizar.", 4000)
            return 0
        if not HAS_PYAV:
            return 0
        self._flush()
        otras = {s.id: sequence_to_dict(s) for s in self.project.sequences
                 if s is not self.sequence}
        if self.cache_worker.start(sequence_to_dict(self.sequence), otras,
                                   dict(self.project.media), pendientes):
            self.statusBar().showMessage(
                f"Renderizando {len(pendientes)} zona{'s' if len(pendientes) != 1 else ''}…", 5000)
            return len(pendientes)
        return 0

    def _cache_finished(self, hechas: int) -> None:
        self._refresh_render_bar()
        self._refresh()
        if hechas:
            self.statusBar().showMessage(
                f"{hechas} zona{'s' if hechas != 1 else ''} renderizada{'s' if hechas != 1 else ''}.",
                5000)

    def clear_render_cache(self) -> int:
        cuantos = render_cache.clear_cache()
        self._refresh_render_bar()
        self._refresh()
        self.statusBar().showMessage(f"Caché de render borrada ({cuantos} archivos).", 4000)
        return cuantos

    def _cached_zone_at(self, t: float):
        if not self.use_render_cache or not HAS_PYAV:
            return None
        zona = render_zones.zone_at(self.zones(), t)
        if zona is None or not render_cache.is_cached(zona.signature):
            return None
        return zona

    def _render(self, t: float) -> None:
        zona = self._cached_zone_at(t)
        if zona is not None:
            # La zona ya está renderizada con todo quemado: se lee del archivo
            # como un video más, sin textos ni imágenes encima (ya van dentro).
            trabajo = FrameJob.make(hash(zona.signature), render_cache.cached_file(zona.signature),
                                    max(0.0, t - zona.start))
            frame = self.frames.get(trabajo) or self.frames.latest(trabajo.key)
            self.frames.request([trabajo])
            self.preview.set_time(t)
            self.preview.set_layers([Layer(frame)] if frame is not None else [])
            self.preview.set_overlays([])
            self.preview.set_titles([])
            self._showing_cache = zona.signature
            return
        self._showing_cache = None
        self.preview.set_time(t)
        self.preview.set_layers(self._layers_at(t))
        self.preview.set_overlays(overlays_at(self.sequence, t, self._image_for))
        self.preview.set_titles(titles_at(self.sequence, t))
        if not self.scopes.isHidden():
            self.scopes.submit(self.scope_image())

    def _refresh(self) -> None:
        """Vuelve a componer el cuadro actual sin mover el playhead."""
        self._render(self.timeline.playhead)
        self.timeline.update()

    def _image_for(self, path: Path) -> QImage:
        """Las imágenes se cargan una vez y se guardan: el preview redibuja
        muchas veces por segundo y no puede volver a leer del disco."""
        if path not in self._images:
            self._images[path] = QImage(str(path))
        return self._images[path]

    def _close_sources(self) -> None:
        self.frames.reset()
        self._sources.close_all()
        self._images.clear()
        clear_mask_cache()

    def _fit_zoom(self) -> None:
        """Ajusta el zoom para que quepa toda la secuencia."""
        duration = self.sequence.duration
        if duration > 0:
            usable = max(200, self.timeline.width() - 90)
            self.timeline.pixels_per_second = usable / duration
            self.timeline.update()

    # --- marcas de entrada y salida ---------------------------------------

    def mark_in(self) -> None:
        t = self.timeline.playhead
        if self.timeline.mark_out is not None and t >= self.timeline.mark_out:
            self.timeline.mark_out = None
        self.timeline.mark_in = t
        self.timeline.update()
        self._update_status()

    def mark_out(self) -> None:
        t = self.timeline.playhead
        if self.timeline.mark_in is not None and t <= self.timeline.mark_in:
            self.timeline.mark_in = None
        self.timeline.mark_out = t
        self.timeline.update()
        self._update_status()

    def clear_marks(self) -> None:
        self.timeline.mark_in = self.timeline.mark_out = None
        self.timeline.update()
        self._update_status()

    # --- marcadores -------------------------------------------------------

    def add_marker(self, name: str = "") -> None:
        self.sequence.add_marker(self.timeline.playhead, name)
        self._commit("Poner marcador")

    def add_named_marker(self) -> None:
        """Shift+M: abre el marcador del playhead, poniéndolo si no hay."""
        t = self.timeline.playhead
        marcador = self.sequence.marker_near(t)
        if marcador is None:
            self.add_marker()
            marcador = self.sequence.marker_near(t)
        self.edit_marker(marcador)

    def next_marker(self) -> None:
        marcador = self.sequence.next_marker(self.timeline.playhead)
        if marcador is not None:
            self._scrubbed(marcador.time)

    def previous_marker(self) -> None:
        marcador = self.sequence.previous_marker(self.timeline.playhead)
        if marcador is not None:
            self._scrubbed(marcador.time)

    def clear_markers(self) -> None:
        if self.sequence.markers:
            self.sequence.markers.clear()
            self._commit("Borrar marcadores")

    def _range(self) -> tuple[float, float]:
        """El tramo que se reproduce: el marcado, o todo si no hay marcas."""
        start = self.timeline.mark_in if self.timeline.mark_in is not None else 0.0
        end = (self.timeline.mark_out if self.timeline.mark_out is not None
               else self.sequence.duration)
        return start, end

    # --- reproducción -----------------------------------------------------

    def toggle_play(self) -> None:
        self._pause() if self._playing else self._play()

    def _play(self) -> None:
        if self.sequence.duration <= 0:
            return

        start, end = self._range()
        if self.timeline.playhead >= end - 1e-6:
            self._seek(start)

        self._playing = True
        self._origin = self.timeline.playhead
        self._elapsed.start()

        # El audio solo acompaña a velocidad normal. A otras velocidades se
        # oiría con el tono cambiado, que es peor que no oírlo.
        self._audio_on = (
            self._speed == 1.0
            and self.audio.start(self._audio_clips(), self._origin, end,
                                 self.sequence.audio_mix_options())
        )

        self._clock.start(self._interval())
        self.transport.set_playing(True)

    def _pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._clock.stop()
        self.audio.stop()
        self._audio_on = False
        self.transport.set_playing(False)

    def _interval(self) -> int:
        """Cada cuánto revisar. Más seguido que el cuadro, para no perder ninguno."""
        return max(4, int(1000 / (self.sequence.fps * max(self._speed, 0.25))))

    def _tick(self) -> None:
        start, end = self._range()

        # Con sonido, la referencia es lo que ya salió por la tarjeta; sin
        # él, el reloj de la interfaz.
        if self._audio_on:
            t = self._origin + self.audio.position()
        else:
            t = self._origin + (self._elapsed.elapsed() / 1000.0) * self._speed

        if t >= end:
            if self._loop:
                self._origin = start
                self._elapsed.restart()
                if self._audio_on:
                    self._audio_on = self.audio.start(self._audio_clips(), start, end,
                                                      self.sequence.audio_mix_options())
                self._seek(start)
                return
            self._pause()
            self._seek(end)
            return

        self._seek(t)

    def set_speed(self, speed: float) -> None:
        # Reanclar el reloj: sin esto, cambiar de velocidad reinterpreta
        # el tiempo ya transcurrido y el playhead pega un salto.
        self._origin = self.timeline.playhead
        self._elapsed.restart()

        self._speed = speed
        self.transport.set_speed(speed)
        if self._playing:
            self._clock.start(self._interval())

    def _shift_speed(self, direction: int) -> None:
        index = SPEEDS.index(self._speed) if self._speed in SPEEDS else SPEEDS.index(1.0)
        self.set_speed(SPEEDS[max(0, min(len(SPEEDS) - 1, index + direction))])

    def set_loop(self, enabled: bool) -> None:
        self._loop = enabled
        self.transport.set_loop(enabled)
        self._loop_action.setChecked(enabled)

    def toggle_loop(self) -> None:
        self.set_loop(not self._loop)

    # --- pantalla completa ------------------------------------------------

    def toggle_fullscreen(self) -> None:
        """Saca el preview a su propia ventana y lo regresa a su lugar.

        Se reparenta el widget en vez de duplicarlo: así sigue siendo el
        mismo destino de los cuadros y la reproducción no se interrumpe.
        """
        if self._fullscreen:
            self.preview.setWindowFlags(Qt.Widget)
            self._top_layout.insertWidget(0, self.preview, 1)
            self.preview.show()
            self._fullscreen = False
            self.activateWindow()
        else:
            self._top_layout.removeWidget(self.preview)
            self.preview.setParent(None)
            self.preview.setWindowFlags(Qt.Window)
            self.preview.setWindowTitle("Vortex Studio — pantalla completa")
            self.preview.showFullScreen()
            self.preview.setFocus()
            self._fullscreen = True

    # --- teclado ----------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # Las flechas, Inicio y Fin ya son acciones del mapa de atajos. Aquí
        # solo queda Escape, que no se deja cambiar: en todo el sistema es la
        # tecla de "suelta lo que estoy haciendo", y un editor que la usara
        # para otra cosa sorprendería.
        if event.key() == Qt.Key_Escape:
            self.timeline.select(None)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._flush()
        if not self._confirm_discard():
            event.ignore()
            return
        if self.render_queue.busy:
            respuesta = QMessageBox.question(
                self, "Hay exportaciones en curso",
                "Si sales ahora se cancelan y los archivos a medias se borran.\n\n"
                "¿Salir de todos modos?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                event.ignore()
                return
        self.render_queue.shutdown()
        self.cache_worker.shutdown()
        self.proxies.shutdown()
        self.stabilizer.shutdown()

        self._clock.stop()
        self._autosave_timer.stop()
        self.audio.stop()
        if self._fullscreen:
            self.preview.close()
        # Cierre normal: el usuario ya decidió guardar o descartar, así que
        # la copia de emergencia sobra. Si el programa truena, esto nunca
        # corre y la copia se queda para la próxima.
        self._clear_autosave()
        self._close_sources()
        self.frames.close()
        super().closeEvent(event)


class ExportDialog(QDialog):
    """Qué se va a exportar, con qué preset y qué calidad, antes de pedir el archivo."""

    FPS_CHOICES = (None, 24.0, 25.0, 30.0, 50.0, 60.0)

    def __init__(self, parent, start: float, end: float, sequence) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar")
        self.setMinimumWidth(400)
        self._sequence = sequence

        marked = (start, end) != (0.0, sequence.duration)
        rango = (f"{timecode(start, sequence.fps)} → {timecode(end, sequence.fps)}"
                 f"{'   (entre las marcas)' if marked else ''}")

        self._preset = QComboBox()
        self._fill_presets(DEFAULT_PRESET.name)

        self._descripcion = QLabel()
        self._descripcion.setWordWrap(True)
        self._descripcion.setStyleSheet("color:#7d838c; font-size:11px;")

        self._size = QLabel()

        self._quality = QComboBox()
        self._quality.addItems(QUALITY.keys())
        self._quality.setCurrentText("Normal")

        self._fps = QComboBox()
        for valor in self.FPS_CHOICES:
            self._fps.addItem(f"Los de la secuencia ({sequence.fps:g})" if valor is None
                              else f"{valor:g}", valor)

        pistas = sum(len(t.clips) for t in sequence.audio_tracks())
        self._hay_audio = pistas > 0
        self._audio = QCheckBox(f"Incluir audio ({pistas} clip{'s' if pistas != 1 else ''})")
        self._audio.setChecked(self._hay_audio)
        self._audio.setEnabled(self._hay_audio)

        self._preset_name = QLineEdit()
        self._preset_name.setPlaceholderText("Nombre para guardar estos ajustes")
        self._save_preset = QPushButton("Guardar preset")
        self._save_preset.clicked.connect(lambda: self.save_current_as(self._preset_name.text()))
        self._delete_preset = QPushButton("Borrar")
        self._delete_preset.clicked.connect(self.delete_current)
        self._preset_msg = QLabel("")
        self._preset_msg.setStyleSheet("color:#7d838c; font-size:10px;")
        fila = QHBoxLayout()
        fila.addWidget(self._preset_name, 1)
        fila.addWidget(self._save_preset)
        fila.addWidget(self._delete_preset)

        form = QFormLayout()
        form.addRow("Preset:", self._preset)
        form.addRow("", self._descripcion)
        form.addRow("Tramo:", QLabel(rango))
        form.addRow("Duración:", QLabel(f"{end - start:.2f} s"))
        form.addRow("Tamaño:", self._size)
        form.addRow("Cuadros por segundo:", self._fps)
        form.addRow("Calidad:", self._quality)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Exportar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.Ok)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._audio)
        layout.addLayout(fila)
        layout.addWidget(self._preset_msg)
        layout.addWidget(buttons)

        self._preset.currentTextChanged.connect(self._preset_changed)
        self._preset_changed(self._preset.currentText())

    def _fill_presets(self, elegido: str) -> None:
        self._preset.blockSignals(True)
        self._preset.clear()
        self._preset.addItems([p.name for p in all_presets()])
        self._preset.setCurrentText(elegido)
        self._preset.blockSignals(False)

    def _preset_changed(self, nombre: str) -> None:
        """Lo que no aplica al preset se apaga, en vez de ignorarse en silencio."""
        preset = by_name(nombre)
        self._descripcion.setText(preset.description)
        self._delete_preset.setEnabled(preset.user)
        if preset.quality:
            self._quality.setCurrentText(preset.quality)
        indice = self._fps.findData(preset.fps)
        self._fps.setCurrentIndex(indice if indice >= 0 else 0)

        if preset.kind == AUDIO_PRESET:
            self._size.setText("solo audio")
            self._quality.setEnabled(False)
            self._fps.setEnabled(False)
            self._audio.setChecked(self._hay_audio)
            self._audio.setEnabled(False)
            self._ok.setEnabled(self._hay_audio)
            if not self._hay_audio:
                self._descripcion.setText("La secuencia no tiene audio que exportar.")
        else:
            ancho, alto = output_size(preset, self._sequence.width, self._sequence.height)
            self._size.setText(f"{ancho} × {alto}")
            self._quality.setEnabled(True)
            self._fps.setEnabled(True)
            self._audio.setEnabled(self._hay_audio)
            self._ok.setEnabled(True)

    def save_current_as(self, nombre: str):
        """Guarda preset, calidad y cuadros por segundo con ese nombre."""
        from dataclasses import replace

        base = by_name(self._preset.currentText())
        try:
            nuevo = save_user_preset(replace(base, name=nombre.strip(), quality=self.quality(),
                                             fps=self.fps(), description="Preset propio."))
        except ValueError as error:
            self._preset_msg.setText(str(error))
            return None
        self._fill_presets(nuevo.name)
        self._preset_changed(nuevo.name)
        self._preset_msg.setText(f"Guardado «{nuevo.name}».")
        return nuevo

    def delete_current(self) -> bool:
        nombre = self._preset.currentText()
        if not delete_user_preset(nombre):
            return False
        self._fill_presets(DEFAULT_PRESET.name)
        self._preset_changed(DEFAULT_PRESET.name)
        self._preset_msg.setText(f"Borrado «{nombre}».")
        return True

    def preset(self):
        """El preset elegido, tal cual está guardado."""
        return by_name(self._preset.currentText())

    def export_preset(self):
        """El preset con los cuadros por segundo y la calidad que quedaron en el diálogo."""
        from dataclasses import replace

        elegido = self.preset()
        if elegido.kind == AUDIO_PRESET:
            return elegido
        return replace(elegido, fps=self.fps(), quality=self.quality())

    def quality(self) -> str:
        return self._quality.currentText()

    def fps(self) -> float | None:
        return self._fps.currentData()

    def with_audio(self) -> bool:
        return self._audio.isChecked()
