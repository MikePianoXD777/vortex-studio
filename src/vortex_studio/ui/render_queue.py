"""Cola de render: exportar en segundo plano mientras se sigue editando.

Antes exportar abría una barra de progreso modal y la ventana entera se
quedaba esperando. Aquí cada exportación es un **trabajo** con su propia
copia congelada de la secuencia: se agrega a la cola, un hilo aparte la
codifica, y el usuario sigue cortando. Lo que edite después ya no cambia
lo que se está exportando, que es lo que uno espera al darle Exportar.

Un trabajo a la vez. Dos codificaciones de H.264 en paralelo no terminan
antes que una tras otra —se pelean los mismos núcleos— y sí se comen el
doble de memoria.

Qt pinta en imágenes desde cualquier hilo, así que el hilo usa el mismo
compositor que el preview. Los avisos al panel van por señales, que Qt
lleva solas al hilo de la interfaz.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from vortex_studio.media.encoder import Cancelled, export_audio, export_video
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.media.presets import AUDIO as AUDIO_PRESET
from vortex_studio.media.presets import output_size

WAITING = "En cola"
RUNNING = "Exportando"
DONE = "Listo"
CANCELLED = "Cancelado"
FAILED = "Falló"
FINISHED = (DONE, CANCELLED, FAILED)

_ids = itertools.count(1)


@dataclass(eq=False)
class RenderJob:
    """Una exportación: qué, a dónde, y cómo va."""

    path: Path
    sequence: dict                  # la secuencia congelada, en datos planos
    media: dict                     # copia del caché de sondeos
    start: float
    end: float
    preset: object
    quality: str = "Normal"
    with_audio: bool = True

    id: int = field(default_factory=lambda: next(_ids))
    status: str = WAITING
    done: int = 0
    total: int = 1
    error: str = ""
    elapsed: float = 0.0
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def fraction(self) -> float:
        return max(0.0, min(1.0, self.done / max(1, self.total)))

    @property
    def is_audio(self) -> bool:
        return getattr(self.preset, "kind", "") == AUDIO_PRESET

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()


class RenderQueue(QObject):
    """La fila de trabajos y el hilo que los va sacando."""

    changed = Signal(object)        # un trabajo avanzó o cambió de estado
    finished = Signal(object)       # un trabajo terminó, bien o mal

    # Cada cuánto avisar del progreso: sin freno serían treinta avisos por
    # segundo de video, y el panel se la pasaría repintando.
    NOTIFY_SECONDS = 0.1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: list[RenderJob] = []
        self._lock = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = False

    # --- lo que usa la interfaz -------------------------------------------

    @property
    def jobs(self) -> list[RenderJob]:
        with self._lock:
            return list(self._jobs)

    @property
    def busy(self) -> bool:
        with self._lock:
            return any(j.status in (WAITING, RUNNING) for j in self._jobs)

    def add(self, job: RenderJob) -> RenderJob:
        with self._lock:
            self._jobs.append(job)
            if self._thread is None or not self._thread.is_alive():
                self._stop = False
                self._thread = threading.Thread(target=self._run, name="vortex-render",
                                                daemon=True)
                self._thread.start()
            self._lock.notify_all()
        self.changed.emit(job)
        return job

    def cancel(self, job: RenderJob) -> None:
        """Cancela. Si todavía no empezaba, sale de la fila sin tocar nada."""
        job._cancel.set()
        with self._lock:
            if job.status == WAITING:
                job.status = CANCELLED
                self._lock.notify_all()
                cancelado_en_fila = True
            else:
                cancelado_en_fila = False
        if cancelado_en_fila:
            self.changed.emit(job)
            self.finished.emit(job)

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = [j for j in self._jobs if j.status not in FINISHED]
        self.changed.emit(None)

    def wait(self, timeout: float = 60.0) -> bool:
        """Espera a que no quede nada pendiente. Para las pruebas y al salir."""
        limite = time.monotonic() + timeout
        with self._lock:
            while any(j.status in (WAITING, RUNNING) for j in self._jobs):
                resta = limite - time.monotonic()
                if resta <= 0:
                    return False
                self._lock.wait(resta)
        return True

    def shutdown(self, timeout: float = 10.0) -> None:
        """Cancela todo y espera al hilo. Un archivo a medias se borra solo."""
        for job in self.jobs:
            if job.status in (WAITING, RUNNING):
                job._cancel.set()
                if job.status == WAITING:
                    job.status = CANCELLED
        with self._lock:
            self._stop = True
            self._lock.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)

    # --- el hilo ----------------------------------------------------------

    def _next(self) -> RenderJob | None:
        with self._lock:
            while not self._stop:
                job = next((j for j in self._jobs if j.status == WAITING), None)
                if job is not None:
                    job.status = RUNNING
                    return job
                return None
            return None

    def _run(self) -> None:
        while True:
            job = self._next()
            if job is None:
                return
            self.changed.emit(job)
            inicio = time.monotonic()
            try:
                self._render(job)
                estado, error = DONE, ""
            except Cancelled:
                estado, error = CANCELLED, ""
            except Exception as falla:          # el archivo, el códec, el disco…
                estado, error = FAILED, str(falla) or type(falla).__name__
            with self._lock:
                job.status, job.error = estado, error
                job.elapsed = time.monotonic() - inicio
                if estado == DONE:
                    job.done = job.total
                self._lock.notify_all()
            self.changed.emit(job)
            self.finished.emit(job)

    def _render(self, job: RenderJob) -> None:
        # Importado aquí para que la cola se pueda probar sin compositor.
        from vortex_studio.model.serialize import sequence_from_dict
        from vortex_studio.ui.renderer import SequenceRenderer

        secuencia = sequence_from_dict(job.sequence)
        ultimo = [0.0]

        def avance(hecho: int, total: int) -> bool:
            job.done, job.total = hecho, total
            ahora = time.monotonic()
            if ahora - ultimo[0] >= self.NOTIFY_SECONDS:
                ultimo[0] = ahora
                self.changed.emit(job)
            return not job._cancel.is_set()

        if job._cancel.is_set():
            raise Cancelled()

        clips = secuencia.audio_clips()
        if job.is_audio:
            if not clips:
                raise RuntimeError("La secuencia no tiene audio que exportar.")
            job.total = max(1, int(round((job.end - job.start) * 1000)))
            export_audio(job.path, AudioMixer(clips).stream(job.start, job.end),
                         job.end - job.start, avance)
            return

        fps = secuencia.fps
        job.total = max(1, int(round((job.end - job.start) * fps)))
        ancho, alto = output_size(job.preset, secuencia.width, secuencia.height)
        renderer = SequenceRenderer(secuencia, dict(job.media))
        try:
            export_video(
                job.path,
                renderer.frames(job.start, job.end, fps, (ancho, alto)),
                job.total, ancho, alto, fps, job.quality, avance,
                AudioMixer(clips).stream(job.start, job.end)
                if job.with_audio and clips else None,
            )
        finally:
            renderer.close()


class _JobRow(QWidget):
    def __init__(self, job: RenderJob, queue: RenderQueue) -> None:
        super().__init__()
        self.job = job
        self._name = QLabel(job.name)
        self._name.setStyleSheet("color:#d6dae0; font-size:11px;")
        self._state = QLabel()
        self._state.setStyleSheet("color:#7d838c; font-size:10px;")
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(lambda: queue.cancel(job))

        arriba = QHBoxLayout()
        arriba.addWidget(self._name, 1)
        arriba.addWidget(self.cancel_button)
        caja = QVBoxLayout(self)
        caja.setContentsMargins(8, 6, 8, 6)
        caja.setSpacing(3)
        caja.addLayout(arriba)
        caja.addWidget(self._bar)
        caja.addWidget(self._state)
        self.refresh()

    def refresh(self) -> None:
        job = self.job
        self._bar.setValue(int(job.fraction * 1000))
        detalle = {
            WAITING: "En cola",
            RUNNING: f"Exportando  ·  {job.fraction * 100:.0f} %",
            DONE: f"Listo  ·  {job.elapsed:.1f} s",
            CANCELLED: "Cancelado",
            FAILED: f"Falló: {job.error}",
        }[job.status]
        self._state.setText(detalle)
        self.cancel_button.setEnabled(job.status in (WAITING, RUNNING))


class RenderQueuePanel(QDockWidget):
    """El panel de la cola: una fila por exportación, con su barra y su botón."""

    def __init__(self, queue: RenderQueue) -> None:
        super().__init__("Cola de render")
        self.setObjectName("cola_de_render")
        self.queue = queue
        self._rows: dict[int, _JobRow] = {}

        self._empty = QLabel("Nada exportándose. Exportar agrega el video aquí "
                             "y puedes seguir editando.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet("color:#6f757e; font-size:10px; padding:10px;")

        self._list = QVBoxLayout()
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(2)
        contenido = QWidget()
        caja = QVBoxLayout(contenido)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(self._empty)
        caja.addLayout(self._list)
        caja.addStretch(1)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(contenido)

        self.clear_button = QPushButton("Quitar terminados")
        self.clear_button.clicked.connect(queue.clear_finished)

        cuerpo = QWidget()
        layout = QVBoxLayout(cuerpo)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(area, 1)
        layout.addWidget(self.clear_button, 0, Qt.AlignRight)
        self.setWidget(cuerpo)

        queue.changed.connect(self._changed)

    def row_for(self, job: RenderJob) -> _JobRow | None:
        return self._rows.get(job.id)

    def _changed(self, job) -> None:
        vivos = {j.id: j for j in self.queue.jobs}
        for ident in [i for i in self._rows if i not in vivos]:
            fila = self._rows.pop(ident)
            self._list.removeWidget(fila)
            fila.deleteLater()
        for ident, trabajo in vivos.items():
            if ident not in self._rows:
                self._rows[ident] = _JobRow(trabajo, self.queue)
                self._list.addWidget(self._rows[ident])
            self._rows[ident].refresh()
        self._empty.setVisible(not self._rows)
