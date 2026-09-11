"""Lectura de audio: forma de onda para el timeline y mezcla para exportar.

La forma de onda se calcula bajando el audio a mono 8 kHz y sacando el pico
de cada cubo. Se saca el pico y no el promedio a propósito: promediar aplana
los golpes, que es justo lo que uno busca cuando mira una onda para cortar.
"""

from __future__ import annotations

import array
from fractions import Fraction
from pathlib import Path
from typing import Iterator

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
    if not HAS_PYAV:
        return []

    try:
        container = av.open(str(path))
        stream = container.streams.audio[0]
    except Exception:
        return []

    resampler = AudioResampler(format="s16", layout="mono", rate=PEAK_RATE)
    samples = array.array("h")

    try:
        for frame in container.decode(stream):
            for chunk in resampler.resample(frame):
                # El plano viene con relleno al final: hay que cortarlo a las
                # muestras reales o la onda se llena de ceros fantasma.
                data = bytes(chunk.planes[0])[: chunk.samples * 2]
                block = array.array("h")
                block.frombytes(data)
                samples.extend(block)
    except Exception:
        pass
    finally:
        container.close()

    if not samples:
        return []

    bucket = max(1, PEAK_RATE // max(1, per_second))
    out: list[float] = []
    for index in range(0, len(samples), bucket):
        chunk = samples[index:index + bucket]
        out.append(max(max(chunk), -min(chunk)) / 32768.0)
    return out


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
            yield from self._from_clip(clip, desde, hasta - cursor)
            cursor = hasta

        if cursor < end:
            yield from self._silence(end - cursor)

    # --- piezas -----------------------------------------------------------

    def _silence(self, seconds: float) -> Iterator:
        pendientes = int(round(seconds * self.rate))
        while pendientes > 0:
            bloque = min(pendientes, self.rate)
            frame = av.AudioFrame(format=self.format, layout=self.layout, samples=bloque)
            frame.sample_rate = self.rate
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            yield frame
            pendientes -= bloque

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

            while faltan > 0:
                salida = fifo.read(min(self.rate, faltan))
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
