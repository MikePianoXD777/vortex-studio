"""Crea proxies en segundo plano, uno detrás de otro.

Crear un proxy es codificar un video completo: minutos con material largo.
Va en su propio hilo para que se pueda seguir editando —con el original—
mientras tanto, y en cuanto un proxy termina el preview lo empieza a usar.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from vortex_studio.media.encoder import Cancelled
from vortex_studio.media.proxy import existing_proxy, make_proxy


class ProxyManager(QObject):
    progress = Signal(object, float)     # original, avance de 0 a 1
    ready = Signal(object, object)       # original, proxy
    failed = Signal(object, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: list[Path] = []
        self._current: Path | None = None
        self._cond = threading.Condition()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        with self._cond:
            return bool(self._pending) or self._current is not None

    @property
    def pending(self) -> list[Path]:
        with self._cond:
            return ([self._current] if self._current else []) + list(self._pending)

    def request(self, paths) -> int:
        """Encarga los proxies que falten. Devuelve cuántos quedaron en fila."""
        nuevos = 0
        with self._cond:
            for path in paths:
                path = Path(path)
                if existing_proxy(path) is not None:
                    continue
                if path == self._current or path in self._pending:
                    continue
                self._pending.append(path)
                nuevos += 1
            if nuevos and (self._thread is None or not self._thread.is_alive()):
                self._cancel.clear()
                self._thread = threading.Thread(target=self._run, name="vortex-proxies",
                                                daemon=True)
                self._thread.start()
            self._cond.notify_all()
        return nuevos

    def cancel_all(self) -> None:
        with self._cond:
            self._pending.clear()
        self._cancel.set()

    def wait(self, timeout: float = 120.0) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: not self._pending and self._current is None,
                                       timeout)

    def shutdown(self, timeout: float = 5.0) -> None:
        self.cancel_all()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            with self._cond:
                if not self._pending:
                    self._current = None
                    self._cond.notify_all()
                    return
                self._current = self._pending.pop(0)
                actual = self._current
                self._cancel.clear()

            def avance(hecho: int, total: int, p=actual) -> bool:
                self.progress.emit(p, hecho / max(1, total))
                return not self._cancel.is_set()

            try:
                proxy = make_proxy(actual, avance)
                self.ready.emit(actual, proxy)
            except Cancelled:
                pass
            except Exception as error:
                self.failed.emit(actual, str(error) or type(error).__name__)
            finally:
                with self._cond:
                    self._current = None
                    self._cond.notify_all()
