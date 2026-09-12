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
from vortex_studio.model.media import lookup
from vortex_studio.model.project import Fill
from vortex_studio.ui.compositor import Layer, compose, framing_of


def inside(clip, t: float) -> float:
    """El tiempo recortado al material del clip.

    Durante una transición se le pide cuadro a un clip fuera de su tramo;
    sin el recorte se le pediría al archivo algo que no tiene.
    """
    return min(max(t, clip.start), clip.end - 1e-6)


def layer_for(clip, frame, t: float, weight: float) -> Layer:
    return Layer(
        frame,
        weight * clip.fade_at(inside(clip, t)),
        clip.transform.values_at(clip.local(t)),
        clip.blend,
        clip.mask,
        None,
        framing_of(clip.transform),
    )


def fill_layer(fill: Fill, weight: float) -> Layer:
    return Layer(None, weight, None, "Normal", None, fill.color, None)


class SequenceRenderer:
    """Cuadros compuestos de una secuencia, a resolución de salida."""

    def __init__(self, sequence, media: dict | None = None,
                 sources: SourcePool | None = None,
                 images: dict | None = None) -> None:
        self.sequence = sequence
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

    def frame_of(self, clip, t: float):
        if clip is None or not HAS_PYAV:
            return None
        try:
            fuente = self.sources.get(id(clip), clip.source)
            return fuente.frame_at(clip.source_time(inside(clip, t)), clip.color)
        except Exception:
            return None

    def layers(self, t: float) -> list[Layer]:
        capas = []
        for item, peso in self.stack(t):
            if isinstance(item, Fill):
                capas.append(fill_layer(item, peso))
            else:
                capas.append(layer_for(item, self.frame_of(item, t), t, peso))
        return capas

    def compose(self, t: float, width: int, height: int) -> QImage:
        return compose(
            width, height,
            self.layers(t),
            [(o, self.image_for(o.source)) for o in self.sequence.overlays_at(t)],
            self.sequence.titles_at(t),
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
