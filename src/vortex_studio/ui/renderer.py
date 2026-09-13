"""Arma el cuadro completo de un instante, decodificando en orden.

Es lo que usa la exportación. Vive fuera de la ventana para que la cola de
render pueda armar cuadros en otro hilo con **su propia copia** de la
secuencia, sus propios decodificadores y sus propias imágenes: el usuario
sigue editando mientras tanto, y nada de lo que toque puede cambiar un
cuadro a medio exportar.

El preview no pasa por aquí para decodificar —él pide cuadros al servidor
en segundo plano y nunca espera—, pero arma sus capas con las mismas dos
funciones de abajo, `layer_for` y `fill_layer`. Así una capa se ve igual
en el preview que en el archivo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from PySide6.QtGui import QImage

from vortex_studio.media import HAS_PYAV, probe_media
from vortex_studio.media.pool import SourcePool
from vortex_studio.model import animate
from vortex_studio.model.media import lookup
from vortex_studio.model.overlays import AdjustmentLayer
from vortex_studio.model.project import Fill, NestedClip
from vortex_studio.ui.compositor import Layer, compose, framing_of


def image_to_rgb_frame(image: QImage):
    """Una QImage como `Frame` RGB, con sus bytes propios."""
    from vortex_studio.media import Frame

    imagen = image.convertToFormat(QImage.Format_RGB888)
    paso, alto = imagen.bytesPerLine(), imagen.height()
    return Frame(bytes(imagen.constBits())[:paso * alto], imagen.width(), alto, paso)


def color_frame(frame, adjust, processor):
    """Corrige el color de un `Frame` RGB ya compuesto (el de una anidada)."""
    if adjust is None or adjust.is_neutral or not HAS_PYAV:
        return frame
    import av
    import numpy as np

    from vortex_studio.media import Frame

    crudo = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.stride)
    arreglo = crudo[:, :frame.width * 3].reshape(frame.height, frame.width, 3)
    salida = processor.apply(av.VideoFrame.from_ndarray(np.ascontiguousarray(arreglo),
                                                        format="rgb24"), adjust)
    rgb = salida.reformat(format="rgb24")
    plano = rgb.planes[0]
    return Frame(bytes(plano), rgb.width, rgb.height, plano.line_size)


def inside(clip, t: float) -> float:
    """El tiempo recortado al material del clip.

    Durante una transición se le pide cuadro a un clip fuera de su tramo;
    sin el recorte se le pediría al archivo algo que no tiene.
    """
    return min(max(t, clip.start), clip.end - 1e-6)


def local_in(item, t: float) -> float:
    """Segundos desde el inicio del elemento, dentro de su tramo."""
    return max(0.0, min(t, item.start + item.duration) - item.start)


def layer_for(clip, frame, t: float, weight: float, fps: float = 30.0) -> Layer:
    vista = animate.view(clip, local_in(clip, t))
    encuadre = framing_of(clip.transform)
    fuerza = getattr(clip, "stabilize", 0)
    if fuerza > 0:
        from vortex_studio.media.stabilize import STABILIZER
        encuadre["stabilize"] = STABILIZER.offset(clip.source, clip.source_time(inside(clip, t)),
                                                  fuerza, fps)
    return Layer(
        frame,
        weight * clip.fade_at(inside(clip, t)),
        clip.transform.values_at(clip.local(t)),
        clip.blend,
        vista.mask,
        None,
        encuadre,
    )


def overlays_at(sequence, t: float, image_for) -> list:
    """Imágenes del instante, ya con sus valores animados."""
    return [(animate.view(o, local_in(o, t)), image_for(o.source))
            for o in sequence.overlays_at(t)]


def titles_at(sequence, t: float) -> list:
    return [animate.view(ti, local_in(ti, t)) for ti in sequence.titles_at(t)]


def adjustment_layer(capa, t: float, weight: float) -> Layer:
    vista = animate.view(capa, local_in(capa, t))
    return Layer(None, weight * capa.fade_at(t) * max(0.0, vista.opacity), None,
                 vista.blend, vista.mask, None, None, vista.color)


def fill_layer(fill: Fill, weight: float) -> Layer:
    return Layer(None, weight, None, "Normal", None, fill.color, None)


class SequenceRenderer:
    """Cuadros compuestos de una secuencia, a resolución de salida."""

    def __init__(self, sequence, media: dict | None = None,
                 sources: SourcePool | None = None,
                 images: dict | None = None, resolve=None) -> None:
        self.sequence = sequence
        self.resolve = resolve          # id -> Sequence, para las anidadas
        self._children: dict[str, "SequenceRenderer"] = {}
        self._depth = 0
        self._processor = None
        self.media = media if media is not None else {}
        self.sources = sources if sources is not None else SourcePool()
        self.images = images if images is not None else {}

    def aspect_of(self, clip) -> float | None:
        """La proporción del material, del caché de sondeos."""
        try:
            info = lookup(self.media, clip.source, probe_media)
        except Exception:
            return None
        if info.width and info.height:
            return info.width / info.height
        return None

    def stack(self, t: float) -> list[tuple]:
        return self.sequence.video_stack_at(t, self.aspect_of)

    def image_for(self, path: Path) -> QImage:
        if path not in self.images:
            self.images[path] = QImage(str(path))
        return self.images[path]

    def nested_frame(self, clip, t: float):
        """El cuadro de una secuencia anidada: se compone la hija en su tiempo."""
        if self.resolve is None or self._depth > 6:
            return None
        hija = self.resolve(clip.sequence_id)
        if hija is None or hija is self.sequence:
            return None
        hijo = self._children.get(clip.sequence_id)
        if hijo is None or hijo.sequence is not hija:
            hijo = SequenceRenderer(hija, self.media, SourcePool(4), self.images, self.resolve)
            hijo._depth = self._depth + 1
            self._children[clip.sequence_id] = hijo
        imagen = hijo.compose(clip.source_time(inside(clip, t)), hija.width, hija.height)
        if self._processor is None:
            from vortex_studio.media.color import ColorProcessor
            self._processor = ColorProcessor()
        color = animate.view(clip, local_in(clip, t)).color
        return color_frame(image_to_rgb_frame(imagen), color, self._processor)

    def frame_of(self, clip, t: float):
        if clip is None or not HAS_PYAV:
            return None
        if isinstance(clip, NestedClip):
            return self.nested_frame(clip, t)
        try:
            fuente = self.sources.get(id(clip), clip.source)
            color = animate.view(clip, local_in(clip, t)).color
            vista = animate.view(clip, local_in(clip, t))
            momento = clip.source_time(inside(clip, t))
            llave = getattr(vista, "chroma", None)
            if llave is None or not llave.is_on:
                return fuente.frame_at(momento, color)
            return fuente.frame_at(momento, color, llave)
        except Exception:
            return None

    def layers(self, t: float) -> list[Layer]:
        capas = []
        for item, peso in self.stack(t):
            if isinstance(item, Fill):
                capas.append(fill_layer(item, peso))
            elif isinstance(item, AdjustmentLayer):
                capas.append(adjustment_layer(item, t, peso))
            else:
                capas.append(layer_for(item, self.frame_of(item, t), t, peso, self.sequence.fps))
        return capas

    def compose(self, t: float, width: int, height: int) -> QImage:
        return compose(
            width, height,
            self.layers(t),
            overlays_at(self.sequence, t, self.image_for),
            titles_at(self.sequence, t),
            t,
        )

    def frames(self, start: float, end: float, fps: float,
               size: tuple[int, int] | None = None) -> Iterator[QImage]:
        """Va entregando el cuadro compuesto de cada instante.

        Es un generador para que la codificación avance mientras se dibuja,
        en vez de armar todos los cuadros en memoria primero — una secuencia
        de un minuto en 1080p serían varios gigabytes.
        """
        ancho, alto = size or (self.sequence.width, self.sequence.height)
        count = max(1, int(round((end - start) * fps)))
        for index in range(count):
            yield self.compose(start + index / fps, ancho, alto)

    def close(self) -> None:
        self.sources.close_all()
        for hijo in self._children.values():
            hijo.close()
