"""Reproducción de sonido durante la edición.

Funciona en modo empuje: se le pide a Qt el canal de escritura y se le van
metiendo bloques desde un temporizador. La alternativa —heredar de QIODevice
y dejar que Qt jale— exige acertarle a `bytesAvailable` y a los tamaños
exactos, y cualquier error ahí se oye como chasquidos.

La posición se lee del propio dispositivo, no del reloj de la interfaz: el
audio no se puede acelerar ni saltar sin que se note, así que mandarlo él y
que la imagen lo siga es lo que mantiene la sincronía.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from vortex_studio.media.audio import LAYOUT, RATE, AudioRenderer

CHUNK_MS = 120          # cuánto audio se adelanta en cada empujón
BYTES_PER_FRAME = 4     # estéreo, 16 bits


class AudioPlayer(QObject):
    """Reproduce la mezcla de las pistas de audio mientras corre el playhead."""

    unavailable = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sink: QAudioSink | None = None
        self._io = None
        self._frames = None
        self._pending = b""
        self._volume = 1.0

        self._pump = QTimer(self)
        self._pump.setInterval(CHUNK_MS // 2)
        self._pump.timeout.connect(self._push)

        self._format = QAudioFormat()
        self._format.setSampleRate(RATE)
        self._format.setChannelCount(2)
        self._format.setSampleFormat(QAudioFormat.Int16)

    # --- disponibilidad ---------------------------------------------------

    @property
    def available(self) -> bool:
        """Puede no haber tarjeta de sonido: la app tiene que correr igual."""
        device = QMediaDevices.defaultAudioOutput()
        return not device.isNull() and device.isFormatSupported(self._format)

    @property
    def playing(self) -> bool:
        return self._sink is not None

    # --- control ----------------------------------------------------------

    def start(self, clips: list, desde: float, hasta: float) -> bool:
        self.stop()
        if not clips or not self.available or hasta <= desde:
            return False

        try:
            renderer = AudioRenderer(clips, rate=RATE, layout=LAYOUT, fmt="s16")
            self._frames = renderer.stream(desde, hasta)
            self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), self._format)
            self._sink.setVolume(self._volume)
            self._io = self._sink.start()
        except Exception as error:      # sin permiso, sin servidor de sonido…
            self._sink = None
            self.unavailable.emit(str(error))
            return False

        self._pending = b""
        self._push()                    # llenar antes de arrancar el reloj
        self._pump.start()
        return True

    def stop(self) -> None:
        self._pump.stop()
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        self._io = None
        self._frames = None
        self._pending = b""

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    def position(self) -> float:
        """Segundos de audio ya entregados a la tarjeta."""
        if self._sink is None:
            return 0.0
        return self._sink.processedUSecs() / 1_000_000.0

    # --- alimentación -----------------------------------------------------

    def _push(self) -> None:
        if self._sink is None or self._io is None:
            return

        libre = self._sink.bytesFree()
        while libre > 0:
            if not self._pending:
                bloque = self._next_block()
                if bloque is None:
                    return              # se acabó la mezcla
                self._pending = bloque

            trozo = self._pending[:libre]
            escritos = self._io.write(trozo)
            if escritos <= 0:
                return
            self._pending = self._pending[escritos:]
            libre -= escritos

    def _next_block(self) -> bytes | None:
        frame = next(self._frames, None)
        if frame is None:
            return None
        # Con formato `s16` el plano ya viene entrelazado; hay que recortar
        # el relleno del final o se cuelan muestras basura entre bloques.
        return bytes(frame.planes[0])[: frame.samples * BYTES_PER_FRAME]
