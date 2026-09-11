"""Cálculo de la forma de onda en segundo plano.

Sacar los picos exige decodificar el audio completo. Hacerlo dentro del
repintado congelaba la ventana la primera vez que aparecía un clip de
audio — con un archivo largo, varios segundos tieso.

Aquí se calcula en un hilo aparte: el timeline pide la onda, se le entrega
una lista vacía de momento, y cuando el hilo termina avisa para repintar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from vortex_studio.media.audio import peaks


class _Aviso(QObject):
    listo = Signal(object, list)


class _Tarea(QRunnable):
    def __init__(self, source: Path, per_second: int, aviso: _Aviso) -> None:
        super().__init__()
        self.source = source
        self.per_second = per_second
        self.aviso = aviso

    @Slot()
    def run(self) -> None:
        try:
            datos = peaks(self.source, self.per_second)
        except Exception:
            datos = []      # un archivo ilegible simplemente no tiene onda
        self.aviso.listo.emit(self.source, datos)


class WaveformCache(QObject):
    """Guarda las ondas ya calculadas y encarga las que falten."""

    ready = Signal()

    def __init__(self, per_second: int = 60, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.per_second = per_second
        self._done: dict[Path, list[float]] = {}
        self._working: set[Path] = set()

        self._aviso = _Aviso()
        self._aviso.listo.connect(self._store)
        self._pool = QThreadPool.globalInstance()

    def get(self, source: Path) -> list[float]:
        """La onda del archivo, o una lista vacía mientras se calcula."""
        source = Path(source)
        if source in self._done:
            return self._done[source]

        if source not in self._working:
            self._working.add(source)
            self._pool.start(_Tarea(source, self.per_second, self._aviso))
        return []

    def _store(self, source: Path, datos: list[float]) -> None:
        self._done[Path(source)] = datos
        self._working.discard(Path(source))
        self.ready.emit()

    def wait(self, timeout_ms: int = 30000) -> bool:
        """Espera a que no quede nada pendiente. Solo para las pruebas."""
        return self._pool.waitForDone(timeout_ms)
