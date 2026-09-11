"""La ventana principal: amarra preview, timeline, transporte y paneles."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
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

from vortex_studio.media import HAS_PYAV, VideoSource, probe
from vortex_studio.media.audio import AudioRenderer, has_audio
from vortex_studio.media.encoder import QUALITY, Cancelled, export_video
from vortex_studio.model import (
    ANCHORS,
    Clip,
    ImageOverlay,
    Project,
    Sequence,
    Title,
    timecode,
)
from vortex_studio.model.history import History
from vortex_studio.model.serialize import EXTENSION, load_project, save_project
from vortex_studio.ui.compositor import compose
from vortex_studio.ui.panels import ColorPanel, ImagePanel, TextPanel
from vortex_studio.ui.preview import PreviewWidget
from vortex_studio.ui.timeline import TOOL_RAZOR, TOOL_SELECT, TimelineWidget
from vortex_studio.ui.transport import SPEEDS, TransportBar

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

MEDIA_FILTER = (
    "Video e imágenes (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.png *.jpg *.jpeg *.webp *.bmp);;"
    "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;"
    "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;"
    "Todos los archivos (*)"
)
PROJECT_FILTER = f"Proyecto de Vortex Studio (*{EXTENSION});;Todos los archivos (*)"
EXPORT_FILTER = "PNG (*.png);;JPEG (*.jpg)"
VIDEO_OUT_FILTER = "Video MP4 (*.mp4)"

HEAVY_MODIFIERS = Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier


def _is_plain_key(sequence: QKeySequence) -> bool:
    """¿El atajo es una tecla suelta, sin Ctrl ni Alt?"""
    if sequence.isEmpty():
        return False
    return not bool(sequence[0].keyboardModifiers() & HEAVY_MODIFIERS)


DEFAULT_TITLE_SECONDS = 3.0
DEFAULT_IMAGE_SECONDS = 4.0


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.sequence = self.project.active
        self.history = History()
        self.history.reset(self.sequence)

        self._sources: dict[Path, VideoSource] = {}
        self._images: dict[Path, QImage] = {}
        self._title: Title | None = None
        self._path: Path | None = None
        self._dirty = False

        # Atajos de una sola tecla (Espacio, C, L, Supr…). Hay que apagarlos
        # mientras se escribe: si no, teclear un subtítulo activa la navaja,
        # el bucle y borra el clip seleccionado, y las letras ni siquiera
        # llegan al cuadro de texto porque el atajo se las come antes.
        self._plain_actions: list[QAction] = []

        self._playing = False
        self._speed = 1.0
        self._loop = False
        self._fullscreen = False

        self.resize(1440, 820)

        self.preview = PreviewWidget()
        self.preview.set_aspect(self.sequence.width / self.sequence.height)
        self.timeline = TimelineWidget(self.sequence)
        self.transport = TransportBar()
        self.color_panel = ColorPanel()
        self.text_panel = TextPanel()
        self.image_panel = ImagePanel()

        self._build_layout()
        self._build_menu()
        self._connect()
        self._update_title()
        self._update_status()

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

        self.addDockWidget(Qt.RightDockWidgetArea, self.text_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.image_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.color_panel)
        self.resizeDocks([self.text_panel, self.image_panel, self.color_panel],
                         [360, 250, 240], Qt.Vertical)

    def _build_menu(self) -> None:
        archivo = self.menuBar().addMenu("&Archivo")
        self._action(archivo, "&Nuevo proyecto", QKeySequence.New, self.new_project)
        self._action(archivo, "&Abrir proyecto…", QKeySequence.Open, self.open_project)
        archivo.addSeparator()
        self._action(archivo, "&Guardar", QKeySequence.Save, self.save)
        self._action(archivo, "Guardar &como…", "Ctrl+Shift+S", self.save_as)
        archivo.addSeparator()
        self._action(archivo, "&Importar…", "Ctrl+I", self.import_media)
        self._action(archivo, "Exportar &video…", "Ctrl+E", self.export_video)
        self._action(archivo, "Exportar &cuadro…", "Ctrl+Shift+E", self.export_frame)
        archivo.addSeparator()
        self._action(archivo, "&Salir", QKeySequence.Quit, self.close)

        editar = self.menuBar().addMenu("&Editar")
        self._undo_action = self._action(editar, "&Deshacer", QKeySequence.Undo, self.undo)
        self._redo_action = self._action(editar, "&Rehacer", "Ctrl+Shift+Z", self.redo)
        editar.addSeparator()
        self._action(editar, "&Cortar en el playhead", "Ctrl+K", self.cut_at_playhead)
        self._action(editar, "&Duplicar", "Ctrl+D", self.duplicate_selected)
        self._action(editar, "&Eliminar", "Delete", self.delete_selected)
        self._action(editar, "Eliminar y &cerrar hueco", "Shift+Delete", self.ripple_delete)
        editar.addSeparator()

        herramientas = QActionGroup(self)
        for label, shortcut, tool in (("Selección", "V", TOOL_SELECT),
                                      ("Navaja", "C", TOOL_RAZOR)):
            action = self._action(editar, f"Herramienta: {label}", shortcut,
                                  lambda _=False, t=tool: self.set_tool(t))
            action.setCheckable(True)
            action.setChecked(tool == TOOL_SELECT)
            herramientas.addAction(action)

        # Nada de atajos con Ctrl+Alt: en Windows, con teclado latinoamericano,
        # AltGr manda Ctrl+Alt, así que escribir @ o \ los dispararía.
        clip_menu = self.menuBar().addMenu("&Clip")
        self._action(clip_menu, "&Fundir entrada y salida", "Ctrl+Shift+D",
                     lambda: self.set_fade(entrada=1.0, salida=1.0))
        self._action(clip_menu, "Fundido de &entrada (1 s)", None,
                     lambda: self.set_fade(entrada=1.0))
        self._action(clip_menu, "Fundido de &salida (1 s)", None,
                     lambda: self.set_fade(salida=1.0))
        self._action(clip_menu, "&Quitar fundidos", None,
                     lambda: self.set_fade(entrada=0.0, salida=0.0))
        clip_menu.addSeparator()
        for etiqueta, valor in (("Cámara lenta 0.5×", 0.5), ("Velocidad normal", 1.0),
                                ("Cámara rápida 2×", 2.0), ("Cámara rápida 4×", 4.0)):
            self._action(clip_menu, etiqueta, None,
                         lambda _=False, v=valor: self.set_clip_speed(v))
        clip_menu.addSeparator()
        self._action(clip_menu, "&Congelar cuadro", "Ctrl+Shift+F", self.freeze_frame)

        insertar = self.menuBar().addMenu("&Insertar")
        self._action(insertar, "&Texto", "Ctrl+T", self.add_title)
        self._action(insertar, "&Subtítulo aquí", "Ctrl+Shift+T",
                     lambda: self.add_title(anchor="Subtítulo"))
        self._action(insertar, "&Imagen…", "Ctrl+Shift+I", self.import_image)

        reproducir = self.menuBar().addMenu("&Reproducción")
        self._action(reproducir, "Reproducir / pausar", "Space", self.toggle_play)
        reproducir.addSeparator()
        self._action(reproducir, "Más lento", "J", lambda: self._shift_speed(-1))
        self._action(reproducir, "Velocidad normal", "K", lambda: self.set_speed(1.0))
        self._action(reproducir, "Más rápido", "Shift+L", lambda: self._shift_speed(1))
        reproducir.addSeparator()
        self._loop_action = self._action(reproducir, "Repetir", "L", self.toggle_loop)
        self._loop_action.setCheckable(True)

        marcar = self.menuBar().addMenu("&Marcar")
        self._action(marcar, "Marcar &entrada", "I", self.mark_in)
        self._action(marcar, "Marcar &salida", "O", self.mark_out)
        self._action(marcar, "&Quitar marcas", "Ctrl+Shift+X", self.clear_marks)
        marcar.addSeparator()
        self._action(marcar, "Poner &marcador", "M", self.add_marker)
        self._action(marcar, "Marcador con &nombre…", "Shift+M", self.add_named_marker)
        self._action(marcar, "Marcador &siguiente", "Shift+Down", self.next_marker)
        self._action(marcar, "Marcador &anterior", "Shift+Up", self.previous_marker)
        self._action(marcar, "&Borrar marcadores", "Ctrl+Shift+M", self.clear_markers)
        marcar.addSeparator()
        self._action(marcar, "Ir a la entrada", "Shift+I",
                     lambda: self._scrubbed(self.timeline.mark_in or 0.0))
        self._action(marcar, "Ir a la salida", "Shift+O",
                     lambda: self._scrubbed(self.timeline.mark_out or self.sequence.duration))

        ver = self.menuBar().addMenu("&Ver")
        self._action(ver, "Pantalla &completa", "F", self.toggle_fullscreen)
        self._action(ver, "&Ajustar timeline", "Shift+Z", self._fit_zoom)
        ver.addSeparator()
        ver.addAction(self.text_panel.toggleViewAction())
        ver.addAction(self.image_panel.toggleViewAction())
        ver.addAction(self.color_panel.toggleViewAction())

        self._update_history_actions()
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def _action(self, menu, text: str, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
            if _is_plain_key(action.shortcut()):
                self._plain_actions.append(action)
        action.triggered.connect(slot)
        # Los atajos deben responder aunque el foco esté en el timeline.
        action.setShortcutContext(Qt.ApplicationShortcut)
        menu.addAction(action)
        return action

    def _focus_changed(self, old, new) -> None:
        typing = isinstance(new, (QPlainTextEdit, QLineEdit, QAbstractSpinBox, QComboBox))
        for action in self._plain_actions:
            action.setEnabled(not typing)

    def _connect(self) -> None:
        self.timeline.playhead_moved.connect(self._scrubbed)
        self.timeline.selection_changed.connect(self._selected)
        self.timeline.edit_finished.connect(self._commit)
        self.timeline.cut_requested.connect(self._cut)

        self.transport.play_pause.connect(self.toggle_play)
        self.transport.step.connect(self._step)
        self.transport.skip.connect(self._skip)
        self.transport.go_start.connect(lambda: self._scrubbed(0.0))
        self.transport.go_end.connect(lambda: self._scrubbed(self.sequence.duration))
        self.transport.loop_toggled.connect(self.set_loop)
        self.transport.speed_changed.connect(self.set_speed)

        self.preview.fullscreen_toggled.connect(self.toggle_fullscreen)
        self.color_panel.changed.connect(self._color_changed)
        self.image_panel.changed.connect(self._image_changed)
        self.text_panel.changed.connect(self._text_changed)
        self.text_panel.add_requested.connect(self.add_title)
        self.text_panel.delete_requested.connect(self.delete_title)

    # --- proyecto ---------------------------------------------------------

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
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
        herramienta = "Navaja" if self.timeline.tool == TOOL_RAZOR else "Selección"
        marcas = ""
        if self.timeline.mark_in is not None or self.timeline.mark_out is not None:
            inicio, fin = self._range()
            marcas = f"   ·   Marcas {timecode(inicio, seq.fps)} → {timecode(fin, seq.fps)}"

        self.statusBar().showMessage(
            f"{seq.width}×{seq.height}   ·   {seq.fps:g} fps   ·   "
            f"{timecode(seq.duration, seq.fps)}   ·   "
            f"{piezas} elemento{'s' if piezas != 1 else ''}   ·   "
            f"{herramienta}{marcadores}{marcas}"
        )

    # --- historial --------------------------------------------------------

    def _schedule(self, label: str) -> None:
        """Apunta un cambio para registrarlo cuando el usuario deje de teclear."""
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
        self._commit_timer.stop()
        self._pending = None
        self.history.push(self.sequence, label)
        self._dirty = True
        self._update_title()
        self._update_history_actions()
        self._refresh()
        self._update_status()

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
        self.project.sequences[0] = sequence
        self._adopt(sequence, reset_history=False)
        self._dirty = True
        self._update_title()

    def _adopt(self, sequence: Sequence, reset_history: bool) -> None:
        """Pone una secuencia nueva en circulación por toda la interfaz."""
        self.sequence = sequence
        self.timeline.sequence = sequence
        self.timeline.selected = None
        self.timeline.refresh()
        self._title = None
        self.preview.set_aspect(sequence.width / sequence.height)

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

    def _place_video(self, path: Path) -> None:
        if not HAS_PYAV:
            QMessageBox.warning(
                self, "Falta PyAV",
                "Instala las dependencias para poder leer video:\n\n"
                "./.venv/bin/pip install -r requirements.txt")
            return

        try:
            info = probe(path)
        except Exception as error:  # el archivo puede estar roto o no ser video
            QMessageBox.critical(self, "No se pudo abrir", f"{path.name}\n\n{error}")
            return

        track = self.sequence.video_tracks()[-1]   # V1, la de hasta abajo
        first = not track.clips
        duration = info.get("duration") or 0.0
        clip = track.append(path, duration)

        # El audio del archivo entra como su propio clip en A1, alineado con
        # el video. Van sueltos a propósito: así se puede mover o borrar el
        # sonido sin tocar la imagen.
        if has_audio(path):
            audio = self.sequence.audio_tracks()[0]
            audio.add(Clip(source=path, start=clip.start, duration=duration))

        if first:
            self.sequence.fps = info.get("fps") or self.sequence.fps
            self.sequence.width = info.get("width") or self.sequence.width
            self.sequence.height = info.get("height") or self.sequence.height
            self.preview.set_aspect(self.sequence.width / self.sequence.height)

        self._fit_zoom()
        self.timeline.select(clip)
        self._commit("Importar video")
        self._seek(clip.start)

    def _place_image(self, path: Path) -> None:
        """Las imágenes entran a V2, la pista de arriba: van sobre el video."""
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.critical(self, "No se pudo abrir", path.name)
            return

        self._images[path] = image
        overlay = ImageOverlay(start=self.timeline.playhead,
                               duration=DEFAULT_IMAGE_SECONDS, source=path)
        self.sequence.video_tracks()[0].add(overlay)
        self.timeline.select(overlay)
        self.image_panel.set_target(overlay)
        self._commit("Insertar imagen")
        self.image_panel.show()
        self.image_panel.raise_()

    def export_frame(self) -> None:
        image = self.preview.current_image()
        if image is None:
            QMessageBox.information(self, "Sin imagen", "No hay ningún cuadro en pantalla.")
            return

        stamp = timecode(self.timeline.playhead, self.sequence.fps).replace(":", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar cuadro", f"cuadro_{stamp}.png", EXPORT_FILTER)
        if path and not image.save(path):
            QMessageBox.critical(self, "No se pudo guardar", path)

    # --- exportar video ---------------------------------------------------

    def export_video(self) -> None:
        if self.sequence.duration <= 0:
            QMessageBox.information(self, "Nada que exportar",
                                    "La secuencia está vacía.")
            return
        if not HAS_PYAV:
            QMessageBox.warning(self, "Falta PyAV",
                                "Sin PyAV no se puede codificar video.")
            return

        start, end = self._range()
        options = ExportDialog(self, start, end, self.sequence)
        if options.exec() != QDialog.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar video", f"{self._path.stem if self._path else 'video'}.mp4",
            VIDEO_OUT_FILTER)
        if not path:
            return

        self._pause()
        self._run_export(Path(path), start, end, options.quality(),
                         options.with_audio())

    def _audio_clips(self) -> list:
        return [c for track in self.sequence.audio_tracks() for c in track.clips]

    def _run_export(self, path: Path, start: float, end: float,
                    quality: str, with_audio: bool) -> None:
        fps = self.sequence.fps
        total = max(1, int(round((end - start) * fps)))

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
                self._frames(start, end, fps),
                total,
                self.sequence.width,
                self.sequence.height,
                fps,
                quality,
                report,
                AudioRenderer(self._audio_clips()).stream(start, end)
                if with_audio and self._audio_clips() else None,
            )
        except Cancelled:
            dialog.close()
            return
        except Exception as error:
            dialog.close()
            QMessageBox.critical(self, "Falló la exportación", str(error))
            return
        finally:
            self._seek(self.timeline.playhead)

        dialog.close()
        sonido = "con audio" if with_audio and self._audio_clips() else "sin audio"
        QMessageBox.information(
            self, "Exportado",
            f"{path.name}\n\n{total} cuadros · {(end - start):.1f} s · {sonido}")

    def _frames(self, start: float, end: float, fps: float):
        """Va entregando el cuadro compuesto de cada instante.

        Es un generador para que la codificación avance mientras se dibuja,
        en vez de armar todos los cuadros en memoria primero — una secuencia
        de un minuto en 1080p serían varios gigabytes.
        """
        count = max(1, int(round((end - start) * fps)))
        for index in range(count):
            t = start + index / fps
            clip = self.sequence.top_clip_at(t)
            yield compose(
                self.sequence.width, self.sequence.height,
                self._frame_at(t),
                [(o, self._image_for(o.source)) for o in self.sequence.overlays_at(t)],
                self.sequence.titles_at(t),
                t,
                clip.fade_at(t) if clip else 1.0,
            )

    def _frame_at(self, t: float):
        """El cuadro de video de fondo en ese instante, ya corregido."""
        clip = self.sequence.top_clip_at(t)
        if clip is None or not HAS_PYAV:
            return None
        try:
            return self._source_for(clip.source).frame_at(clip.source_time(t), clip.color)
        except Exception:
            return None

    # --- edición ----------------------------------------------------------

    def _track_of(self, item):
        return next((t for t in self.sequence.tracks if item in t.clips), None)

    def set_tool(self, tool: str) -> None:
        self.timeline.set_tool(tool)
        self._update_status()

    def cut_at_playhead(self) -> None:
        """Corta lo que esté seleccionado, o todo lo que cruce el playhead."""
        t = self.timeline.playhead
        targets = ([self.timeline.selected] if self.timeline.selected
                   else [c for track in self.sequence.tracks for c in track.items_at(t)])
        if any(self._cut(item, t, commit=False) for item in targets if item):
            self._commit("Cortar")

    def _cut(self, item, t: float, commit: bool = True) -> bool:
        """Parte un elemento en dos por el tiempo `t`."""
        track = self._track_of(item)
        if track is None or not (item.start < t < item.end):
            return False

        left = t - item.start
        right = item.duration - left

        second = copy.deepcopy(item)
        second.start = t
        second.duration = right
        if hasattr(second, "in_point"):
            # La segunda mitad arranca más adelante del archivo original.
            second.in_point = item.in_point + left

        item.duration = left
        track.add(second)

        if commit:
            self.timeline.select(second)
            self._commit("Cortar")
        return True

    def duplicate_selected(self) -> None:
        """Pega una copia justo después de lo seleccionado, sin dejar hueco."""
        item = self.timeline.selected
        track = self._track_of(item) if item else None
        if track is None:
            return

        copia = copy.deepcopy(item)
        copia.start = item.end
        track.add(copia)
        self.timeline.select(copia)
        self._commit("Duplicar")

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
        if not isinstance(item, Clip):
            return

        item.retime(speed)
        self._fit_zoom()
        self._commit(f"Velocidad {speed:g}×")

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

        if self._cut(clip, t, commit=False):
            track = self._track_of(clip)
            congelado = next((c for c in track.clips if abs(c.start - t) < 1e-6), None)
            if congelado is not None:
                congelado.speed = 0.0       # el tiempo del archivo deja de avanzar
                congelado.duration = 2.0
                self.timeline.select(congelado)
        self._commit("Congelar cuadro")

    def delete_selected(self) -> None:
        item = self.timeline.selected
        track = self._track_of(item) if item else None
        if track is None:
            return
        track.clips.remove(item)
        self.timeline.select(None)
        self._commit("Eliminar")

    def ripple_delete(self) -> None:
        """Borra y recorre lo que sigue en esa pista, para no dejar hueco."""
        item = self.timeline.selected
        track = self._track_of(item) if item else None
        if track is None:
            return

        gap, start = item.duration, item.start
        track.clips.remove(item)
        for other in track.clips:
            if other.start >= start:
                other.start -= gap

        self.timeline.select(None)
        self._commit("Eliminar y cerrar hueco")

    def _selected(self, item) -> None:
        """Al seleccionar en el timeline, los paneles siguen la selección."""
        if isinstance(item, Title):
            self._title = item
            self.text_panel.set_titles(self._titles_in_track(), item)
            self.text_panel.raise_()
        elif isinstance(item, ImageOverlay):
            self.image_panel.set_target(item)
            self.image_panel.raise_()
        elif isinstance(item, Clip):
            self.color_panel.set_target(item.color, item.name)
            self.color_panel.raise_()

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
        self.text_panel.show()
        self.text_panel.raise_()

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
        clip = self.sequence.top_clip_at(t)
        self.color_panel.set_target(clip.color if clip else None,
                                    clip.name if clip else "")

        titles = self.sequence.titles_at(t)
        if self._title not in titles:
            self._title = titles[0] if titles else None
        self.text_panel.set_titles(titles, self._title)

        overlays = self.sequence.overlays_at(t)
        selected = self.timeline.selected
        self.image_panel.set_target(
            selected if isinstance(selected, ImageOverlay) and selected in overlays
            else (overlays[-1] if overlays else None))

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

    def _render(self, t: float) -> None:
        clip = self.sequence.top_clip_at(t)
        self.preview.set_time(t)
        self.preview.set_frame(self._frame_at(t), clip.fade_at(t) if clip else 1.0)
        self.preview.set_overlays([
            (overlay, self._image_for(overlay.source))
            for overlay in self.sequence.overlays_at(t)
        ])
        self.preview.set_titles(self.sequence.titles_at(t))

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

    def _source_for(self, path: Path) -> VideoSource:
        if path not in self._sources:
            self._sources[path] = VideoSource(path)
        return self._sources[path]

    def _close_sources(self) -> None:
        for source in self._sources.values():
            source.close()
        self._sources.clear()
        self._images.clear()

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
        actual = self.sequence.marker_near(self.timeline.playhead)
        nombre, listo = QInputDialog.getText(
            self, "Marcador", "Nombre:", text=actual.name if actual else "")
        if listo:
            self.add_marker(nombre.strip())

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
        self._clock.start(self._interval())
        self.transport.set_playing(True)

    def _pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._clock.stop()
        self.transport.set_playing(False)

    def _interval(self) -> int:
        """Cada cuánto revisar. Más seguido que el cuadro, para no perder ninguno."""
        return max(4, int(1000 / (self.sequence.fps * max(self._speed, 0.25))))

    def _tick(self) -> None:
        start, end = self._range()
        t = self._origin + (self._elapsed.elapsed() / 1000.0) * self._speed

        if t >= end:
            if self._loop:
                self._origin = start
                self._elapsed.restart()
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
        key = event.key()
        shift = event.modifiers() & Qt.ShiftModifier
        ctrl = event.modifiers() & Qt.ControlModifier

        if key == Qt.Key_Left:
            self._skip(-10.0) if ctrl else (self._skip(-1.0) if shift else self._step(-1))
        elif key == Qt.Key_Right:
            self._skip(10.0) if ctrl else (self._skip(1.0) if shift else self._step(1))
        elif key == Qt.Key_Home:
            self._scrubbed(0.0)
        elif key == Qt.Key_End:
            self._scrubbed(self.sequence.duration)
        elif key == Qt.Key_Escape:
            self.timeline.select(None)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._flush()
        if not self._confirm_discard():
            event.ignore()
            return

        self._clock.stop()
        if self._fullscreen:
            self.preview.close()
        self._close_sources()
        super().closeEvent(event)


class ExportDialog(QDialog):
    """Qué se va a exportar y con qué calidad, antes de pedir el archivo."""

    def __init__(self, parent, start: float, end: float, sequence) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar video")
        self.setMinimumWidth(340)

        marked = (start, end) != (0.0, sequence.duration)
        rango = (f"{timecode(start, sequence.fps)} → {timecode(end, sequence.fps)}"
                 f"{'   (entre las marcas)' if marked else ''}")

        self._quality = QComboBox()
        self._quality.addItems(QUALITY.keys())
        self._quality.setCurrentText("Normal")

        pistas = sum(len(t.clips) for t in sequence.audio_tracks())
        self._audio = QCheckBox(f"Incluir audio ({pistas} clip{'s' if pistas != 1 else ''})")
        self._audio.setChecked(pistas > 0)
        self._audio.setEnabled(pistas > 0)

        form = QFormLayout()
        form.addRow("Tramo:", QLabel(rango))
        form.addRow("Duración:", QLabel(f"{end - start:.2f} s"))
        form.addRow("Tamaño:", QLabel(f"{sequence.width} × {sequence.height}"))
        form.addRow("Cuadros por segundo:", QLabel(f"{sequence.fps:g}"))
        form.addRow("Calidad:", self._quality)

        aviso = QLabel("El audio se exporta al archivo, pero todavía no suena "
                       "durante la edición: no hay motor de reproducción de sonido.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#a8763d; font-size:10px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Exportar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._audio)
        layout.addWidget(aviso)
        layout.addWidget(buttons)

    def quality(self) -> str:
        return self._quality.currentText()

    def with_audio(self) -> bool:
        return self._audio.isChecked()
