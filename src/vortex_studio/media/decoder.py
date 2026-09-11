"""Decodificación de video con PyAV (FFmpeg).

PyAV es opcional: si no está instalado, `HAS_PYAV` queda en False y la app
arranca igual, solo que sin imagen. Nunca revienta al importar.

Esta capa no sabe nada de Qt: entrega pixeles crudos en RGB y que la UI
arme la imagen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vortex_studio.media.color import ColorProcessor
from vortex_studio.model.color import ColorAdjust

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False


@dataclass(frozen=True)
class Frame:
    """Un frame decodificado, en RGB de 8 bits.

    `stride` son los bytes por renglón. FFmpeg alinea los renglones, así que
    puede ser mayor que `width * 3`: hay que respetarlo o la imagen sale
    inclinada.
    """

    data: bytes
    width: int
    height: int
    stride: int


class VideoSource:
    """Lee frames de un archivo de video por tiempo, no por orden.

    Mantiene abierto el contenedor y hace seek al keyframe anterior al tiempo
    pedido, avanzando hasta el frame correcto. Guarda el último frame servido
    para que arrastrar el playhead hacia adelante no vuelva a hacer seek.
    """

    def __init__(self, path: str | Path) -> None:
        if not HAS_PYAV:
            raise RuntimeError("PyAV no está instalado: no se puede decodificar video")

        self.path = Path(path)
        self._container = av.open(str(self.path))
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"

        self.width = self._stream.codec_context.width
        self.height = self._stream.codec_context.height
        self.fps = float(self._stream.average_rate or 30)
        self.duration = float(self._container.duration / av.time_base) if self._container.duration else 0.0

        self._last_time = -1.0
        self._cached: Frame | None = None
        self._color = ColorProcessor()
        self._applied: tuple | None = None

    def frame_at(self, t: float, adjust: ColorAdjust | None = None) -> Frame | None:
        """Devuelve el frame que se ve en el segundo `t`, ya corregido."""
        t = max(0.0, t)
        settings = self._settings(adjust)

        # Si el cuadro es el mismo y el color no cambió, no hay que decodificar
        # nada: esto es lo que hace que mover un deslizador de color se sienta
        # inmediato con el video pausado.
        if self._cached is not None and settings != self._applied and abs(t - self._last_time) < 1e-6:
            return self._recolor(adjust)

        # Solo hacemos seek si vamos hacia atrás o saltamos lejos; avanzar
        # poco a poco es mucho más barato decodificando en orden.
        if self._cached is None or t < self._last_time or t - self._last_time > 1.0:
            self._seek(t)

        for frame in self._container.decode(self._stream):
            when = float(frame.pts * self._stream.time_base) if frame.pts is not None else t
            if when + 1e-6 >= t:
                self._last_time = when
                self._raw = frame
                self._applied = settings
                self._cached = self._to_rgb(self._color.apply(frame, adjust) if adjust else frame)
                return self._cached

        return self._cached  # se acabó el archivo: nos quedamos con el último

    def _recolor(self, adjust: ColorAdjust | None) -> Frame | None:
        """Vuelve a filtrar el último cuadro decodificado, sin volver a leerlo."""
        raw = getattr(self, "_raw", None)
        if raw is None:
            return self._cached
        self._applied = self._settings(adjust)
        self._cached = self._to_rgb(self._color.apply(raw, adjust) if adjust else raw)
        return self._cached

    @staticmethod
    def _settings(adjust: ColorAdjust | None) -> tuple:
        if adjust is None:
            return ()
        return (adjust.brightness, adjust.contrast, adjust.saturation, adjust.gamma)

    def _seek(self, t: float) -> None:
        offset = int(t / self._stream.time_base)
        self._container.seek(offset, stream=self._stream, backward=True, any_frame=False)
        self._last_time = t

    @staticmethod
    def _to_rgb(frame) -> Frame:
        """Convierte a RGB leyendo el plano directo, sin pasar por numpy."""
        rgb = frame.reformat(format="rgb24")
        plane = rgb.planes[0]
        return Frame(bytes(plane), rgb.width, rgb.height, plane.line_size)

    def close(self) -> None:
        self._container.close()

    def __enter__(self) -> VideoSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def probe(path: str | Path) -> dict:
    """Datos básicos del archivo, sin decodificar nada."""
    if not HAS_PYAV:
        return {}

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return {
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "fps": float(stream.average_rate or 30),
            "duration": float(container.duration / av.time_base) if container.duration else 0.0,
        }
