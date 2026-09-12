"""Lectura de audio: picos para el timeline y el audio de cada clip.

La onda completa, con mínimo y máximo y caché en disco, vive en
`media/waveform.py`. Aquí queda `peaks()`, que la resume en picos de 0 a 1.
Se saca el pico y no el promedio a propósito: promediar aplana los golpes,
que es justo lo que uno busca cuando mira una onda para cortar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np

from vortex_studio.media.waveform import compute as compute_waveform

try:
    import av
    from av.audio.fifo import AudioFifo
    from av.audio.resampler import AudioResampler

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

PEAK_RATE = 8000          # frecuencia a la que se mide la onda
RATE = 48000              # frecuencia de salida al exportar
LAYOUT = "stereo"
FORMAT = "fltp"


def silence(seconds: float, rate: int = RATE,
            layout: str = LAYOUT, fmt: str = FORMAT) -> Iterator:
    """Bloques de silencio que suman `seconds`.

    Vive suelta y no dentro de `AudioRenderer` porque el mezclador también
    la necesita: cuando no hay ninguna pista con sonido, la salida sigue
    teniendo que durar lo mismo que la imagen.
    """
    pendientes = int(round(seconds * rate))
    while pendientes > 0:
        bloque = min(pendientes, rate)
        frame = av.AudioFrame(format=fmt, layout=layout, samples=bloque)
        frame.sample_rate = rate
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        yield frame
        pendientes -= bloque


def has_audio(path: str | Path) -> bool:
    if not HAS_PYAV:
        return False
    try:
        with av.open(str(path)) as container:
            return bool(container.streams.audio)
    except Exception:
        return False


def peaks(path: str | Path, per_second: int = 60) -> list[float]:
    """Picos normalizados de 0 a 1, `per_second` por cada segundo de audio."""
    datos = compute_waveform(path, per_second)
    if datos.shape[1] == 0:
        return []
    return np.maximum(np.abs(datos[0]), np.abs(datos[1])).clip(0.0, 1.0).tolist()


def fade_envelope(clip, tiempos: np.ndarray) -> np.ndarray:
    """La opacidad de los fundidos, muestra por muestra.

    Es la misma cuenta que `fade_at` del modelo, pero sobre un arreglo de
    tiempos en vez de un solo instante: si los dos fundidos no caben en el
    clip se reparten a prorrata, y cada uno es una rampa lineal.
    """
    alfa = np.ones_like(tiempos, dtype=np.float64)
    entrada = float(getattr(clip, "fade_in", 0.0))
    salida = float(getattr(clip, "fade_out", 0.0))
    if entrada <= 0 and salida <= 0:
        return alfa

    duracion = float(clip.duration)
    total = entrada + salida
    if total > duracion > 0:
        factor = duracion / total
        entrada, salida = entrada * factor, salida * factor

    dentro = tiempos - clip.start
    if entrada > 0:
        alfa = np.minimum(alfa, np.clip(dentro / entrada, 0.0, 1.0))
    if salida > 0:
        alfa = np.minimum(alfa, np.clip((duracion - dentro) / salida, 0.0, 1.0))
    return alfa


class AudioRenderer:
    """Arma la pista de audio de salida recorriendo los clips en orden.

    Va hacia adelante y nunca regresa, que es como avanza una exportación.
    Eso permite ir decodificando en corrido en vez de hacer un seek por cada
    cuadro, que sería inservible.

    Los huecos entre clips se rellenan con silencio: sin eso, el audio se
    recorrería y perdería la sincronía con la imagen a partir del hueco.
    """

    def __init__(self, clips: list, rate: int = RATE,
                 layout: str = LAYOUT, fmt: str = FORMAT) -> None:
        self.clips = sorted(clips, key=lambda c: c.start)
        self.rate = rate
        self.layout = layout
        self.format = fmt

    def stream(self, start: float, end: float) -> Iterator:
        """Entrega cuadros de audio que cubren exactamente [start, end)."""
        if not HAS_PYAV:
            return

        cursor = start
        for clip in self.clips:
            if clip.end <= cursor or clip.start >= end:
                continue

            if clip.start > cursor:
                yield from self._silence(clip.start - cursor)
                cursor = clip.start

            desde = clip.in_point + (cursor - clip.start)
            hasta = min(clip.end, end)
            for frame in self._from_clip(clip, desde, hasta - cursor):
                yield self._apply_level(frame, clip, cursor)
                cursor += frame.samples / self.rate
            cursor = hasta

        if cursor < end:
            yield from self._silence(end - cursor)

    # --- volumen y fundidos -----------------------------------------------

    def _apply_level(self, frame, clip, cuando: float):
        """Aplica volumen y fundidos del clip a un bloque de audio.

        Con una rampa **muestra por muestra**, multiplicando con NumPy.

        Antes el nivel se calculaba una sola vez al centro de cada bloque y
        se aplicaba con el filtro `volume` de FFmpeg. Con bloques de un
        segundo, un fundido de tres segundos eran tres escalones de volumen:
        yo había escrito que el oído no distinguía la escalera de la rampa,
        y en una voz sí se oye, como tres saltos. Con NumPy la multiplicación
        corre en C igual que el filtro, pero con un nivel por muestra.
        """
        n = frame.samples
        tiempos = cuando + np.arange(n, dtype=np.float64) / self.rate
        nivel = max(0.0, float(getattr(clip, "gain", 1.0))) * fade_envelope(clip, tiempos)

        if np.all(np.abs(nivel - 1.0) < 1e-4):
            return frame            # nada que hacer: ni se copia el bloque

        datos = frame.to_ndarray()
        if frame.format.is_planar:
            datos = datos * nivel[np.newaxis, :]
        else:
            canales = len(frame.layout.channels)
            datos = datos * np.repeat(nivel, canales)[np.newaxis, :]

        original = frame.to_ndarray().dtype
        if np.issubdtype(original, np.integer):
            limites = np.iinfo(original)
            datos = np.clip(np.rint(datos), limites.min, limites.max)
        salida = av.AudioFrame.from_ndarray(
            np.ascontiguousarray(datos.astype(original)),
            format=frame.format.name, layout=frame.layout.name)
        salida.sample_rate = self.rate
        salida.pts = None
        return salida

    def _silence(self, seconds: float) -> Iterator:
        yield from silence(seconds, self.rate, self.layout, self.format)

    def _from_clip(self, clip, source_start: float, seconds: float) -> Iterator:
        """Saca `seconds` de audio del archivo, desde `source_start`."""
        faltan = int(round(seconds * self.rate))
        if faltan <= 0:
            return

        try:
            container = av.open(str(clip.source))
            stream = container.streams.audio[0]
        except Exception:
            # Un clip sin audio no es un error: aporta silencio y ya.
            yield from self._silence(seconds)
            return

        resampler = AudioResampler(format=self.format, layout=self.layout, rate=self.rate)
        fifo = AudioFifo()

        try:
            if source_start > 0:
                container.seek(int(source_start / stream.time_base),
                               stream=stream, backward=True)

            for frame in container.decode(stream):
                cuando = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
                if cuando + frame.samples / max(1, frame.sample_rate) < source_start:
                    continue    # todavía vamos antes del punto de entrada

                for chunk in resampler.resample(frame):
                    chunk.pts = None
                    fifo.write(chunk)

                while fifo.samples >= self.rate and faltan > 0:
                    salida = fifo.read(min(self.rate, faltan))
                    if salida is None:
                        break
                    faltan -= salida.samples
                    yield salida

                if faltan <= 0:
                    break

            # Al terminar el archivo: lo que quedó adentro del resampler, y
            # luego el FIFO hasta vaciarlo.
            #
            # Antes se pedía `fifo.read(1 segundo)` también aquí, y `read`
            # devuelve None si no hay tantas muestras. El pedazo final —hasta
            # un segundo— nunca se leía y se cambiaba por silencio: un clip
            # que llegaba al final de su archivo perdía el cierre de su audio,
            # en el play y en la exportación. Lo destapó una prueba de otra
            # cosa que medía el nivel justo en ese segundo.
            if faltan > 0:
                try:
                    for chunk in resampler.resample(None):
                        chunk.pts = None
                        fifo.write(chunk)
                except Exception:
                    pass

            while faltan > 0 and fifo.samples > 0:
                salida = fifo.read(min(self.rate, faltan, fifo.samples))
                if salida is None:
                    break
                faltan -= salida.samples
                yield salida
        finally:
            container.close()

        if faltan > 0:   # el archivo se acabó antes de tiempo
            yield from self._silence(faltan / self.rate)


def frame_seconds(frame) -> float:
    return frame.samples / float(frame.sample_rate or RATE)
