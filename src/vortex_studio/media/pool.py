"""Un decodificador por clip, no por archivo.

Compartir un decodificador entre todos los clips de un mismo archivo parece
ahorro, pero se derrumba en cuanto dos pedazos del mismo video se ven a la
vez — que es exactamente lo que pasa en una transición cruzada después de un
corte. El decodificador tiene que saltar adelante y atrás en cada cuadro, y
cada salto hacia atrás cuesta decodificar desde el keyframe anterior. La
reproducción se cae a segundos por cuadro.

Con uno por clip, cada uno avanza en corrido por su propio tramo. El precio
es tener varios archivos abiertos, así que se cierran los que llevan más
tiempo sin usarse.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from vortex_studio.media.decoder import VideoSource

LIMIT = 8


class SourcePool:
    def __init__(self, limit: int = LIMIT) -> None:
        self.limit = limit
        self._open: OrderedDict[int, tuple[Path, VideoSource]] = OrderedDict()

    def get(self, key: int, path: Path) -> VideoSource:
        """El decodificador de esa clave, abriéndolo si hace falta."""
        entry = self._open.get(key)
        if entry is not None and entry[0] == path:
            self._open.move_to_end(key)
            return entry[1]

        if entry is not None:      # el clip cambió de archivo
            self._close(key)

        source = VideoSource(path)
        self._open[key] = (path, source)
        self._open.move_to_end(key)
        self._evict()
        return source

    def _evict(self) -> None:
        while len(self._open) > self.limit:
            viejo, _ = next(iter(self._open.items()))
            self._close(viejo)

    def _close(self, key: int) -> None:
        path, source = self._open.pop(key)
        try:
            source.close()
        except Exception:
            pass

    def close_all(self) -> None:
        for key in list(self._open):
            self._close(key)

    def __len__(self) -> int:
        return len(self._open)
