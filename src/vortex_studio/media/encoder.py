"""Escribe la secuencia a un archivo de video.

La parte fina es el paso de pixeles: Qt alinea cada renglón de una QImage a
4 bytes y FFmpeg alinea los suyos a su propio `line_size`. Casi nunca
coinciden, así que hay que copiar renglón por renglón. Copiar el buffer
completo de un jalón produce la imagen inclinada clásica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

try:
    import av

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

        for index, image in enumerate(frames):
            frame = image_to_frame(image, width, height)
            for packet in stream.encode(frame):
                container.mux(packet)

            if progress is not None and not progress(index + 1, total):
                container.close()
                closed = True
                path.unlink(missing_ok=True)
                raise Cancelled()

        for packet in stream.encode():   # vaciar lo que quede en el buffer
            container.mux(packet)
    finally:
        if not closed:
            container.close()

    return path


class Cancelled(Exception):
    """La exportación se detuvo a petición del usuario."""
