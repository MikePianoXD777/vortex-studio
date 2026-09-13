"""Decodificación en un hilo aparte, con búfer de cuadros.

La regla dura: **nunca decodificar en el hilo de la interfaz.** Antes, cada
vez que se movía el playhead la ventana misma abría el archivo, buscaba el
keyframe y decodificaba hasta el cuadro pedido. Con 1080p eso son unos
milisegundos y no se nota; con 4K son decenas, y la ventana entera se
traba mientras tanto — el timeline no responde, el cursor se congela.

Aquí la interfaz **pide** cuadros y **recoge** los que ya estén. Un hilo
aparte decodifica, con su propio juego de decodificadores, y avisa cuando
tiene algo nuevo. PyAV suelta el candado de Python mientras decodifica, así
que el hilo corre de verdad en paralelo.

Tres reglas del servidor:

- **gana el pedido más nuevo**: arrastrar el playhead encarga un cuadro por
  cada posición, y solo importa la última; lo que quedó atrás se descarta
  sin decodificar;
- **un cuadro que falló se recuerda**: si no, la interfaz lo volvería a
  pedir en cada repintado, para siempre;
- **el último cuadro de cada clip se guarda aparte**, para mostrarlo mientras
  llega el nuevo: al arrastrar se ve el cuadro anterior, no un negro.

Este módulo no sabe nada de Qt. Avisa con una función, y quien lo usa decide
cómo llevar el aviso al hilo de la interfaz.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from vortex_studio.media.pool import SourcePool

CACHE_BYTES = 384 * 1024 * 1024     # unos 60 cuadros de 1080p
READ_AHEAD = 8                      # cuadros que se adelantan al reproducir


@dataclass(frozen=True)
class FrameJob:
    """Un cuadro por decodificar: de qué clip, de qué archivo, cuándo y con qué color.

    El ajuste de color se **copia** al crear el trabajo. El hilo decodifica
    mientras el usuario sigue moviendo deslizadores en la interfaz; si
    compartieran el mismo objeto, el hilo podría aplicar la mitad de un
    cambio.
    """

    key: int
    path: Path
    time: float
    adjust: object = field(default=None, compare=False, hash=False)
    signature: tuple = ()
    chroma: object = field(default=None, compare=False, hash=False)

    @classmethod
    def make(cls, key: int, path, time: float, adjust=None, chroma=None) -> "FrameJob":
        copia = adjust.copy() if adjust is not None else None
        llave = chroma.copy() if chroma is not None and chroma.is_on else None
        firma = ((copia.signature if copia is not None else ())
                 + ((llave.signature,) if llave is not None else ()))
        return cls(key, Path(path), round(float(time), 4), copia, firma, llave)

    @property
    def cache_key(self) -> tuple:
        return (self.key, str(self.path), self.time, self.signature)


class FrameServer:
    """Decodifica en su propio hilo y guarda lo decodificado."""

    def __init__(self, on_ready: Callable[[], None] | None = None,
                 cache_bytes: int = CACHE_BYTES, pool_limit: int = 8) -> None:
        self._on_ready = on_ready
        self._limit = cache_bytes

        self._cond = threading.Condition()
        self._queue: list[FrameJob] = []
        self._cache: OrderedDict[tuple, object] = OrderedDict()
        self._bytes = 0
        self._failed: set[tuple] = set()
        self._latest: dict[int, object] = {}
        self._stop = False
        self._reset = False

        # Los decodificadores son solo del hilo: nadie más los toca.
        self._pool = SourcePool(pool_limit)

        self.decoded = 0                    # intentos de decodificación
        self.threads: set[int] = set()      # en qué hilos se decodificó

        self._thread = threading.Thread(target=self._run, name="vortex-decodificador",
                                        daemon=True)
        self._thread.start()

    # --- lo que usa la interfaz -------------------------------------------

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def cached_count(self) -> int:
        with self._cond:
            return len(self._cache)

    def request(self, jobs: Iterable[FrameJob], ahead: Iterable[FrameJob] = ()) -> None:
        """Encarga cuadros. Reemplaza lo que estuviera pendiente.

        Primero los de ahora y luego los adelantados. Lo que ya está en el
        búfer, o ya falló, no se vuelve a encargar.
        """
        jobs, ahead = list(jobs), list(ahead)
        with self._cond:
            vistos: set[tuple] = set()
            pedidos: list[FrameJob] = []
            for job in jobs + ahead:
                clave = job.cache_key
                if clave in vistos or clave in self._cache or clave in self._failed:
                    continue
                vistos.add(clave)
                pedidos.append(job)
            self._queue = pedidos

            # El cuadro de reserva solo hace falta de los clips que se están
            # mostrando: los demás son de clips que ya ni existen.
            vivos = {job.key for job in jobs}
            self._latest = {k: v for k, v in self._latest.items() if k in vivos}

            if pedidos:
                self._cond.notify_all()

    def get(self, job: FrameJob):
        """El cuadro exacto, si ya está decodificado."""
        with self._cond:
            frame = self._cache.get(job.cache_key)
            if frame is not None:
                self._cache.move_to_end(job.cache_key)
            return frame

    def latest(self, key: int):
        """El último cuadro que se decodificó de ese clip, sea del tiempo que sea."""
        with self._cond:
            return self._latest.get(key)

    def failed(self, job: FrameJob) -> bool:
        with self._cond:
            return job.cache_key in self._failed

    def settled(self, jobs: Iterable[FrameJob]) -> bool:
        """¿Ya hay respuesta —cuadro o falla— para todos esos trabajos?"""
        with self._cond:
            return self._settled(list(jobs))

    def wait_for(self, jobs: Iterable[FrameJob], timeout: float = 10.0) -> bool:
        """Espera a que esos cuadros estén. Los pone al frente de la fila.

        Es para sacar un cuadro en limpio, no para pintar: el preview nunca
        espera.
        """
        jobs = list(jobs)
        with self._cond:
            faltan = [j for j in jobs
                      if j.cache_key not in self._cache and j.cache_key not in self._failed]
            if faltan:
                claves = {j.cache_key for j in faltan}
                self._queue = faltan + [j for j in self._queue if j.cache_key not in claves]
                self._cond.notify_all()
            return self._cond.wait_for(lambda: self._stop or self._settled(jobs), timeout)

    def reset(self) -> None:
        """Tira todo: el proyecto cambió. Los decodificadores se cierran en su hilo."""
        with self._cond:
            self._queue = []
            self._cache.clear()
            self._bytes = 0
            self._failed.clear()
            self._latest.clear()
            self._reset = True
            self._cond.notify_all()

    def close(self, timeout: float = 5.0) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout)

    # --- el hilo ----------------------------------------------------------

    def _settled(self, jobs: list[FrameJob]) -> bool:
        return all(j.cache_key in self._cache or j.cache_key in self._failed for j in jobs)

    def _run(self) -> None:
        try:
            while True:
                with self._cond:
                    self._cond.wait_for(lambda: self._stop or self._reset or self._queue)
                    if self._stop:
                        return
                    if self._reset:
                        self._reset = False
                        job = None
                    else:
                        job = self._queue.pop(0)
                        if job.cache_key in self._cache or job.cache_key in self._failed:
                            continue

                if job is None:
                    self._pool.close_all()
                    continue

                frame = None
                try:
                    fuente = self._pool.get(job.key, job.path)
                    # La llave solo se pasa si hay: así cualquier fuente con la
                    # firma de siempre —incluidas las falsas de las pruebas—
                    # sigue sirviendo.
                    if job.chroma is None:
                        frame = fuente.frame_at(job.time, job.adjust)
                    else:
                        frame = fuente.frame_at(job.time, job.adjust, job.chroma)
                except Exception:
                    frame = None

                with self._cond:
                    self.decoded += 1
                    self.threads.add(threading.get_ident())
                    if self._reset:
                        # El proyecto cambió mientras decodificaba: el cuadro
                        # ya no corresponde a nada.
                        self._cond.notify_all()
                        continue
                    if frame is None:
                        self._failed.add(job.cache_key)
                    else:
                        self._store(job.cache_key, frame)
                        self._latest[job.key] = frame
                    self._cond.notify_all()

                if self._on_ready is not None:
                    try:
                        self._on_ready()
                    except Exception:
                        pass
        finally:
            self._pool.close_all()

    def _store(self, clave: tuple, frame) -> None:
        """Guarda el cuadro y tira los más viejos si se pasa del límite."""
        self._cache[clave] = frame
        self._cache.move_to_end(clave)
        self._bytes += len(frame.data)
        while self._bytes > self._limit and len(self._cache) > 1:
            _, viejo = self._cache.popitem(last=False)
            self._bytes -= len(viejo.data)
