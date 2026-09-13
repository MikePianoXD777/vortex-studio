"""Análisis en segundo plano: uno detrás de otro, sin trabar la ventana.

Estabilizar pide recorrer el video completo una vez. Eso son segundos con
material largo, así que va en su propio hilo, igual que los proxies: se
sigue editando y, en cuanto el análisis termina, el clip se corrige solo.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from vortex_studio.media.encoder import Cancelled


class BackgroundAnalyzer(QObject):
    progress = Signal(object, float)     # archivo, avance de 0 a 1
    ready = Signal(object)
    failed = Signal(object, str)

    def __init__(self, work: Callable, done: Callable[[Path], bool],
                 parent: QObject | None = None) -> None:
        """`work(ruta, progreso)` hace el trabajo; `done(ruta)` dice si ya estaba hecho."""
        super().__init__(parent)
        self._work = work
        self._done = done
        self._pending: list[Path] = []
        self._current: Path | None = None
        self._cond = threading.Condition()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        with self._cond:
            return bool(self._pending) or self._current is not None

    def request(self, paths) -> int:
        nuevos = 0
        with self._cond:
            for path in paths:
                path = Path(path)
                if self._done(path) or path == self._current or path in self._pending:
                    continue
                self._pending.append(path)
                nuevos += 1
            if nuevos and (self._thread is None or not self._thread.is_alive()):
                self._cancel.clear()
                self._thread = threading.Thread(target=self._run, name="vortex-analisis",
                                                daemon=True)
                self._thread.start()
            self._cond.notify_all()
        return nuevos

    def wait(self, timeout: float = 120.0) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: not self._pending and self._current is None,
                                       timeout)

    def shutdown(self, timeout: float = 5.0) -> None:
        with self._cond:
            self._pending.clear()
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            with self._cond:
                if not self._pending:
                    self._current = None
                    self._cond.notify_all()
                    return
                self._current = actual = self._pending.pop(0)

            def avance(hecho: int, total: int, p=actual) -> bool:
                try:
                    self.progress.emit(p, hecho / max(1, total))
                except RuntimeError:
                    pass
                return not self._cancel.is_set()

            try:
                self._work(actual, avance)
                self.ready.emit(actual)
            except Cancelled:
                pass
            except RuntimeError:
                pass            # la ventana se cerró mientras analizaba
            except Exception as error:
                try:
                    self.failed.emit(actual, str(error) or type(error).__name__)
                except RuntimeError:
                    pass
            finally:
                with self._cond:
                    self._current = None
                    self._cond.notify_all()
