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

import traceback
from collections import deque

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from vortex_studio.media.audio import LAYOUT, RATE, silence
from vortex_studio.media.mixer import AudioMixer

CHUNK_MS = 120          # cuánto audio se adelanta en cada empujón
BYTES_PER_FRAME = 4     # estéreo, 16 bits
METER_WINDOW = RATE // 50   # el medidor mide de 20 en 20 ms


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
        self._mix: AudioMixer | None = None
        # Para el medidor: (muestra donde empieza la ventana, pico izq, pico der)
        # de lo que ya se mandó a la tarjeta, en orden.
        self._levels: deque = deque(maxlen=50 * 20)
        self._queued = 0            # muestras mandadas desde el arranque
        self._reported = -1         # hasta qué muestra ya se le contó al medidor
        self._total = 0             # muestras que dura el tramo que se está tocando

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

    def start(self, clips: list, desde: float, hasta: float, options: dict | None = None) -> bool:
        self.stop()
        if not clips or not self.available or hasta <= desde:
            return False

        try:
            # Mezclador y no un solo `AudioRenderer`: si la voz y la música
            # están encimadas, al editar se tiene que oír lo mismo que va a
            # salir en el archivo final.
            mezcla = AudioMixer(clips, rate=RATE, layout=LAYOUT, fmt="s16", **(options or {}))
            self._frames = mezcla.stream(desde, hasta)
            self._mix = mezcla
            self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), self._format)
            self._sink.setVolume(self._volume)
            self._io = self._sink.start()
        except Exception as error:      # sin permiso, sin servidor de sonido…
            self._sink = None
            self.unavailable.emit(str(error))
            return False

        self._pending = b""
        self._levels.clear()
        self._queued = 0
        self._reported = -1
        self._total = int(round((hasta - desde) * RATE))
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
        self._mix = None
        self._pending = b""
        self._levels.clear()
        self._queued = 0
        self._reported = -1

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    def position(self) -> float:
        """Segundos de audio ya entregados a la tarjeta."""
        if self._sink is None:
            return 0.0
        return self._sink.processedUSecs() / 1_000_000.0

    def levels(self) -> tuple[float, float, bool]:
        """(pico izquierdo, pico derecho, ¿el limitador actuó?) de lo que suena ahora.

        Los picos van de 0 a 1 y son de la mezcla, antes del volumen del
        monitor: lo que mide un medidor es lo que va a salir en el archivo,
        no cuánto le subiste a tus bocinas.

        Es el más alto de **todo lo que sonó desde la lectura anterior**, no
        solo de la ventana donde cae la posición. Antes era esa ventana y ya:
        la tarjeta avanza a saltos de 21.3 ms —más que los 20 ms de una
        ventana— y la interfaz a veces tarda más entre lectura y lectura, así
        que un golpe corto en una ventana que quedaba en medio nunca llegaba a
        la barra ni a la rayita del pico. Lo mismo para la luz del limitador.
        """
        if self._sink is None or not self._levels:
            return 0.0, 0.0, False
        ahora = int(self.position() * RATE)
        # Lo que sonó en (previo, ahora]. Si no se avanzó, al menos la muestra
        # de ahora: sin eso la barra se caería a cero entre salto y salto.
        previo = min(self._reported, ahora - 1)
        self._reported = ahora
        izquierdo = derecho = 0.0
        actual = True
        for inicio, izq, der in reversed(self._levels):
            if inicio > ahora:
                continue        # ya se mandó a la tarjeta, pero todavía no suena
            if inicio <= previo and not actual:
                break           # esta ya se contó en la lectura anterior
            izquierdo, derecho = max(izquierdo, izq), max(derecho, der)
            actual = False
        limitado = False
        if self._mix is not None:
            limitado = any(desde <= ahora and desde + largo > previo + 1
                           for desde, largo, _ in self._mix.reductions)
        return izquierdo, derecho, limitado

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
        try:
            frame = next(self._frames, None)
        except Exception:
            frame = self._mute_rest()
        if frame is None:
            return None
        # Con formato `s16` el plano ya viene entrelazado; hay que recortar
        # el relleno del final o se cuelan muestras basura entre bloques.
        datos = bytes(frame.planes[0])[: frame.samples * BYTES_PER_FRAME]
        self._measure(datos)
        return datos

    def _mute_rest(self):
        """La mezcla tronó a medio play: lo que falta del tramo va en silencio.

        El error se escapaba por aquí hacia el temporizador o hacia `start()`,
        y de ahí a `MainWindow._play`, que ya había puesto `_playing` y nunca
        arrancaba su reloj: el playhead se quedaba quieto y la barra
        espaciadora solo «pausaba». Cerrar la tarjeta tampoco sirve: la
        ventana sigue tomando la posición de ella, y sin tarjeta el playhead
        regresaría al principio. Con silencio la tarjeta sigue corriendo y el
        play termina donde debía. El error se apunta igual, para saber qué fue.
        """
        traceback.print_exc()
        faltan = max(0, self._total - self._queued)
        self._frames = silence(faltan / RATE, RATE, LAYOUT, "s16")
        return next(self._frames, None)

    def _measure(self, datos: bytes) -> None:
        """Picos por ventana de 20 ms, para el medidor."""
        muestras = np.frombuffer(datos, dtype=np.int16).reshape(-1, 2)
        for inicio in range(0, len(muestras), METER_WINDOW):
            trozo = np.abs(muestras[inicio:inicio + METER_WINDOW].astype(np.int32))
            if len(trozo):
                picos = trozo.max(axis=0) / 32768.0
                self._levels.append((self._queued + inicio, float(picos[0]), float(picos[1])))
        self._queued += len(muestras)
