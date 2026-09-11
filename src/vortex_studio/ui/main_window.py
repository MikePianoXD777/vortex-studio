"""La ventana principal: amarra preview, timeline y transporte."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.media import HAS_PYAV, VideoSource, probe
from vortex_studio.model import ANCHORS, ImageOverlay, Project, Title, timecode
from vortex_studio.ui.panels import ColorPanel, TextPanel
from vortex_studio.ui.preview import PreviewWidget
from vortex_studio.ui.timeline import TimelineWidget
from vortex_studio.ui.transport import SPEEDS, TransportBar

VIDEO_FILTER = "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;Todos los archivos (*)"
IMAGE_FILTER = "PNG (*.png);;JPEG (*.jpg)"
IMPORT_IMAGE_FILTER = (
    "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Todos los archivos (*)"
)
DEFAULT_TITLE_SECONDS = 3.0
DEFAULT_IMAGE_SECONDS = 4.0


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.sequence = self.project.active
        self._sources: dict[Path, VideoSource] = {}

        self._playing = False
        self._speed = 1.0
        self._loop = False
        self._fullscreen = False

        self.setWindowTitle("Vortex Studio")
        self.resize(1280, 760)

        self._images: dict[Path, QImage] = {}
        self._title: Title | None = None

        self.preview = PreviewWidget()
        self.preview.set_aspect(self.sequence.width / self.sequence.height)
        self.timeline = TimelineWidget(self.sequence)
        self.transport = TransportBar()
        self.color_panel = ColorPanel()
        self.text_panel = TextPanel()

        self._build_layout()
        self._build_menu()
        self._connect()

        # Reproducción guiada por reloj real, no por conteo de ticks.
        # `_origin` es el punto de la secuencia donde se dio play y `_elapsed`
        # cuánto ha pasado desde entonces: la posición se calcula, no se
        # acumula. Así, si un frame tarda de más, se salta en vez de irse
        # quedando atrás — que es lo que hace que un reproductor se desfase.
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
        self.addDockWidget(Qt.RightDockWidgetArea, self.color_panel)
        self.resizeDocks([self.text_panel, self.color_panel], [420, 260], Qt.Vertical)

    def _build_menu(self) -> None:
        archivo = self.menuBar().addMenu("&Archivo")
        self._action(archivo, "Importar &video…", QKeySequence.Open, self.import_video)
        self._action(archivo, "Importar &imagen…", "Ctrl+I", self.import_image)
        archivo.addSeparator()
        self._action(archivo, "&Guardar frame actual…", "Ctrl+Shift+S", self.save_frame)
        archivo.addSeparator()
        self._action(archivo, "&Salir", QKeySequence.Quit, self.close)

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
        self._action(marcar, "Ir a la entrada", "Shift+I",
                     lambda: self._seek(self.timeline.mark_in or 0.0))
        self._action(marcar, "Ir a la salida", "Shift+O",
                     lambda: self._seek(self.timeline.mark_out or self.sequence.duration))

        insertar = self.menuBar().addMenu("&Insertar")
        self._action(insertar, "&Texto", "Ctrl+T", self.add_title)
        self._action(insertar, "&Subtítulo aquí", "Ctrl+Shift+T",
                     lambda: self.add_title(anchor="Subtítulo"))
        self._action(insertar, "&Imagen…", "Ctrl+I", self.import_image)

        ver = self.menuBar().addMenu("&Ver")
        self._action(ver, "Pantalla &completa", "F", self.toggle_fullscreen)
        self._action(ver, "&Ajustar timeline", "Shift+Z", self._fit_zoom)
        ver.addSeparator()
        ver.addAction(self.text_panel.toggleViewAction())
        ver.addAction(self.color_panel.toggleViewAction())

    def _action(self, menu, text: str, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        # Los atajos deben responder aunque el foco esté en el timeline.
        action.setShortcutContext(Qt.ApplicationShortcut)
        menu.addAction(action)
        return action

    def _connect(self) -> None:
        self.timeline.playhead_moved.connect(self._scrubbed)
        self.transport.play_pause.connect(self.toggle_play)
        self.transport.step.connect(self._step)
        self.transport.skip.connect(self._skip)
        self.transport.go_start.connect(lambda: self._seek(0.0))
        self.transport.go_end.connect(lambda: self._seek(self.sequence.duration))
        self.transport.loop_toggled.connect(self.set_loop)
        self.transport.speed_changed.connect(self.set_speed)
        self.preview.fullscreen_toggled.connect(self.toggle_fullscreen)
        self.color_panel.changed.connect(self._refresh)
        self.text_panel.changed.connect(self._refresh_titles)
        self.text_panel.add_requested.connect(self.add_title)
        self.text_panel.delete_requested.connect(self.delete_title)

    # --- importar ---------------------------------------------------------

    def import_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar video", "", VIDEO_FILTER)
        if not path:
            return

        if not HAS_PYAV:
            QMessageBox.warning(
                self, "Falta PyAV",
                "Instala las dependencias para poder leer video:\n\n"
                "./.venv/bin/pip install -r requirements.txt",
            )
            return

        try:
            info = probe(path)
        except Exception as error:  # el archivo puede estar roto o no ser video
            QMessageBox.critical(self, "No se pudo abrir", f"{Path(path).name}\n\n{error}")
            return

        track = self.sequence.video_tracks()[-1]  # V1, la de hasta abajo
        clip = track.append(Path(path), info.get("duration") or 0.0)

        if len(track.clips) == 1:
            self.sequence.fps = info.get("fps") or self.sequence.fps
            self.sequence.width = info.get("width") or self.sequence.width
            self.sequence.height = info.get("height") or self.sequence.height
            self.preview.set_aspect(self.sequence.width / self.sequence.height)
            self.setWindowTitle(f"{Path(path).name} — Vortex Studio")

        self._fit_zoom()
        self._seek(clip.start)

    def import_image(self) -> None:
        """Las imágenes entran a V2, la pista de arriba: van sobre el video."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar imagen", "", IMPORT_IMAGE_FILTER)
        if not path:
            return

        image = QImage(path)
        if image.isNull():
            QMessageBox.critical(self, "No se pudo abrir", Path(path).name)
            return

        self._images[Path(path)] = image
        track = self.sequence.video_tracks()[0]   # V2
        track.add(ImageOverlay(start=self.timeline.playhead,
                               duration=DEFAULT_IMAGE_SECONDS,
                               source=Path(path)))
        self._refresh()

    # --- texto ------------------------------------------------------------

    def add_title(self, anchor: str = "Subtítulo") -> None:
        track = self.sequence.text_tracks()[0]    # T1
        x, y = ANCHORS.get(anchor, ANCHORS["Subtítulo"])

        title = Title(start=self.timeline.playhead,
                      duration=DEFAULT_TITLE_SECONDS,
                      text="Texto nuevo", x=x, y=y)
        track.add(title)
        self._title = title

        self._refresh()
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
        self._refresh()
        self._sync_panels(self.timeline.playhead)

    def _refresh_titles(self) -> None:
        """Al editar un texto puede cambiar su duración, y con ella la secuencia."""
        self._title = self.text_panel._title
        for track in self.sequence.text_tracks():
            track.clips.sort(key=lambda c: c.start)
        self._refresh()

    def save_frame(self) -> None:
        image = self.preview.current_image()
        if image is None:
            QMessageBox.information(self, "Sin imagen", "No hay ningún frame en pantalla.")
            return

        suggested = f"frame_{timecode(self.timeline.playhead, self.sequence.fps).replace(':', '-')}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar frame", suggested, IMAGE_FILTER)
        if path and not image.save(path):
            QMessageBox.critical(self, "No se pudo guardar", path)

    def _fit_zoom(self) -> None:
        """Ajusta el zoom para que quepa toda la secuencia."""
        duration = self.sequence.duration
        if duration > 0:
            usable = max(200, self.timeline.width() - 90)
            self.timeline.pixels_per_second = usable / duration
            self.timeline.update()

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
        """Los paneles siempre muestran lo que hay bajo el playhead.

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

        if clip is None or not HAS_PYAV:
            self.preview.set_frame(None)
        else:
            try:
                source = self._source_for(clip.source)
                self.preview.set_frame(source.frame_at(clip.source_time(t), clip.color))
            except Exception:
                # Un frame que no se pudo decodificar no debe tumbar la ventana.
                self.preview.set_frame(None)

        self.preview.set_overlays([
            (overlay, self._image_for(overlay.source))
            for overlay in self.sequence.overlays_at(t)
        ])
        self.preview.set_titles(self.sequence.titles_at(t))

    def _image_for(self, path: Path) -> QImage:
        """Las imágenes se cargan una vez y se guardan: el preview redibuja
        muchas veces por segundo y no puede volver a leer del disco."""
        if path not in self._images:
            self._images[path] = QImage(str(path))
        return self._images[path]

    def _refresh(self) -> None:
        """Vuelve a componer el cuadro actual sin mover el playhead."""
        self._render(self.timeline.playhead)
        self.timeline.update()

    def _source_for(self, path: Path) -> VideoSource:
        if path not in self._sources:
            self._sources[path] = VideoSource(path)
        return self._sources[path]

    # --- marcas de entrada y salida ---------------------------------------

    def mark_in(self) -> None:
        t = self.timeline.playhead
        if self.timeline.mark_out is not None and t >= self.timeline.mark_out:
            self.timeline.mark_out = None
        self.timeline.mark_in = t
        self.timeline.update()

    def mark_out(self) -> None:
        t = self.timeline.playhead
        if self.timeline.mark_in is not None and t <= self.timeline.mark_in:
            self.timeline.mark_in = None
        self.timeline.mark_out = t
        self.timeline.update()

    def clear_marks(self) -> None:
        self.timeline.mark_in = self.timeline.mark_out = None
        self.timeline.update()

    def _range(self) -> tuple[float, float]:
        """El tramo que se reproduce: el marcado, o todo si no hay marcas."""
        start = self.timeline.mark_in if self.timeline.mark_in is not None else 0.0
        end = self.timeline.mark_out if self.timeline.mark_out is not None else self.sequence.duration
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
        """Cada cuánto revisar. Más rápido que el cuadro, para no perder ninguno."""
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
        mismo destino de los frames y la reproducción no se interrumpe.
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
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._clock.stop()
        if self._fullscreen:
            self.preview.close()
        for source in self._sources.values():
            source.close()
        super().closeEvent(event)
