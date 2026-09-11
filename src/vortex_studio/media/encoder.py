"""Escribe la secuencia a un archivo de video.

La parte fina es el paso de pixeles: Qt alinea cada renglón de una QImage a
4 bytes y FFmpeg alinea los suyos a su propio `line_size`. Casi nunca
coinciden, así que hay que copiar renglón por renglón. Copiar el buffer
completo de un jalón produce la imagen inclinada clásica.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterator

try:
    import av
    from av.audio.fifo import AudioFifo

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

# Perfiles de calidad, del más liviano al más pesado.
QUALITY = {
    "Borrador": 28,
    "Normal": 23,
    "Alta": 19,
    "Máxima": 15,
}
DEFAULT_QUALITY = "Normal"


def image_to_frame(image, width: int, height: int):
    """Convierte una QImage RGB888 en un cuadro de FFmpeg."""
    frame = av.VideoFrame(width, height, "rgb24")
    plane = frame.planes[0]

    source_stride = image.bytesPerLine()
    target_stride = plane.line_size
    source = image.constBits()

    if source_stride == target_stride:
        plane.update(bytes(source)[: target_stride * height])
        return frame

    # Rellenamos hasta el ancho de renglón que pide FFmpeg; lo que sobra de
    # cada renglón es relleno que nadie lee.
    row_bytes = width * 3
    buffer = bytearray(target_stride * height)
    view = memoryview(source)
    for y in range(height):
        start = y * source_stride
        buffer[y * target_stride: y * target_stride + row_bytes] = \
            view[start: start + row_bytes]
    plane.update(bytes(buffer))
    return frame


def export_video(
    path: str | Path,
    frames: Iterator,
    total: int,
    width: int,
    height: int,
    fps: float,
    quality: str = DEFAULT_QUALITY,
    progress: Callable[[int, int], bool] | None = None,
    audio: Iterator | None = None,
    audio_rate: int = 48000,
    audio_layout: str = "stereo",
) -> Path:
    """Codifica los cuadros que entregue `frames` a H.264.

    `progress` recibe (hechos, total) y devuelve False para cancelar. Si se
    cancela, el archivo a medias se borra: un video truncado que parece
    terminado es peor que no tener archivo.
    """
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado: no se puede exportar")

    path = Path(path)
    # H.264 necesita dimensiones pares; si son impares, el codificador falla.
    width -= width % 2
    height -= height % 2

    container = av.open(str(path), mode="w")
    closed = False
    try:
        stream = container.add_stream("libx264", rate=round(fps))
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {
            "crf": str(QUALITY.get(quality, QUALITY[DEFAULT_QUALITY])),
            "preset": "medium",
        }

        sound = _AudioWriter(container, audio, audio_rate, audio_layout) if audio else None

        for index, image in enumerate(frames):
            frame = image_to_frame(image, width, height)
            for packet in stream.encode(frame):
                container.mux(packet)

            # El audio se va escribiendo al parejo del video en vez de al
            # final: así el muxer no tiene que retener en memoria todos los
            # paquetes de imagen esperando a que llegue el sonido.
            if sound is not None:
                sound.advance((index + 1) / fps)

            if progress is not None and not progress(index + 1, total):
                container.close()
                closed = True
                path.unlink(missing_ok=True)
                raise Cancelled()

        if sound is not None:
            sound.finish()
        for packet in stream.encode():   # vaciar lo que quede en el buffer
            container.mux(packet)
    finally:
        if not closed:
            container.close()

    return path


class Cancelled(Exception):
    """La exportación se detuvo a petición del usuario."""


class _AudioWriter:
    """Escribe la pista de audio en paralelo con la de video.

    El codificador de AAC pide bloques de un tamaño fijo, que casi nunca
    coincide con el de los cuadros que entrega el decodificador. Un FIFO en
    medio absorbe la diferencia; sin él, el codificador rechaza los bloques
    o mete silencios entre uno y otro.
    """

    def __init__(self, container, source: Iterator, rate: int, layout: str) -> None:
        self.container = container
        self.source = source
        self.rate = rate

        self.stream = container.add_stream("aac", rate=rate)
        self.stream.layout = layout

        self._fifo = AudioFifo()
        self._written = 0          # muestras ya codificadas
        self._pulled = 0.0         # segundos ya sacados de la fuente
        self._done = False

    def advance(self, until: float) -> None:
        """Asegura que haya audio escrito hasta el segundo `until`."""
        while not self._done and self._pulled < until:
            frame = next(self.source, None)
            if frame is None:
                self._done = True
                break
            self._pulled += frame.samples / float(frame.sample_rate or self.rate)
            frame.pts = None       # el FIFO reasigna las marcas de tiempo
            self._fifo.write(frame)

        self._drain(self.stream.codec_context.frame_size or 1024)

    def _drain(self, size: int) -> None:
        while True:
            chunk = self._fifo.read(size)
            if chunk is None:
                break
            self._emit(chunk)

    def _emit(self, chunk) -> None:
        chunk.pts = self._written
        chunk.time_base = Fraction(1, self.rate)
        self._written += chunk.samples
        for packet in self.stream.encode(chunk):
            self.container.mux(packet)

    def finish(self) -> None:
        for frame in self.source:      # lo que quedara pendiente
            frame.pts = None
            self._fifo.write(frame)

        self._drain(self.stream.codec_context.frame_size or 1024)
        resto = self._fifo.read()
        if resto is not None:
            self._emit(resto)
        for packet in self.stream.encode():
            self.container.mux(packet)
