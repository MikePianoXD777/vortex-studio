"""Cálculo de la forma de onda en segundo plano.

Sacar la onda exige decodificar el audio completo. Hacerlo dentro del
repintado congelaba la ventana la primera vez que aparecía un clip de
audio — con un archivo largo, varios segundos tieso.

Aquí se calcula en un hilo aparte: el timeline pide la onda, se le entrega
un arreglo vacío de momento, y cuando el hilo termina avisa para repintar.
El hilo primero busca la onda en el disco (`media/waveform.py`), así que al
volver a abrir un proyecto casi siempre llega al instante.

Se pide al importar, no al dibujar: para cuando el clip aparece en pantalla
la onda ya viene en camino.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from vortex_studio.media.waveform import empty, load_or_compute


class _Aviso(QObject):
    listo = Signal(object, object)


class _Tarea(QRunnable):
    def __init__(self, source: Path, per_second: int, aviso: _Aviso) -> None:
        super().__init__()
        self.source = source
        self.per_second = per_second
        self.aviso = aviso

    @Slot()
    def run(self) -> None:
        try:
            datos = load_or_compute(self.source, self.per_second)
        except Exception:
            datos = empty()     # un archivo ilegible simplemente no tiene onda
        try:
            self.aviso.listo.emit(self.source, datos)
        except RuntimeError:
            # La ventana se cerró mientras se calculaba: ya no hay a quién
            # avisar, y la onda quedó guardada en disco para la próxima.
            pass


class WaveformCache(QObject):
    """Guarda las ondas ya calculadas y encarga las que falten."""

    ready = Signal()

    def __init__(self, per_second: int = 60, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.per_second = per_second
        self._done: dict[Path, np.ndarray] = {}
        self._working: set[Path] = set()

        self._aviso = _Aviso()
        self._aviso.listo.connect(self._store)
        self._pool = QThreadPool.globalInstance()

    def get(self, source: Path) -> np.ndarray:
        """La onda del archivo (2 × n: mínimos y máximos), o vacía mientras se calcula."""
        source = Path(source)
        if source in self._done:
            return self._done[source]

        if source not in self._working:
            self._working.add(source)
            self._pool.start(_Tarea(source, self.per_second, self._aviso))
        return empty()

    def _store(self, source: Path, datos) -> None:
        self._done[Path(source)] = datos
        self._working.discard(Path(source))
        self.ready.emit()

    def wait(self, timeout_ms: int = 30000) -> bool:
        """Espera a que no quede nada pendiente. Solo para las pruebas."""
        return self._pool.waitForDone(timeout_ms)
