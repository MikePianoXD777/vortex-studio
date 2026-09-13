"""Cortar tramos de un clip de un jalón: silencios, o lo que se detecte.

Quitar silencios a mano en una plática de una hora son cientos de cortes
con la navaja y cientos de eliminar y cerrar hueco. Aquí es un comando: se
le da el clip y los tramos, y hace exactamente eso —dividir y eliminar
cerrando hueco, con el audio y el video enlazados— en una sola entrada del
historial.

Los tramos se cortan **de atrás para adelante**: cerrar el hueco de uno
recorre lo que viene después, y si se empezara por el primero, los tiempos
de los demás ya no corresponderían.

Python puro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vortex_studio.model import timeremap
from vortex_studio.model.commands import Command, RippleDelete, Split, editable, track_of


def timeline_ranges(clip, source_ranges, minimum: float = 0.02) -> list[tuple[float, float]]:
    """Tramos del archivo pasados a la línea de tiempo, recortados al clip y juntados.

    Con remapeo de tiempo o cuadro congelado no hay una cuenta de ida y
    vuelta confiable, así que no se devuelve nada.
    """
    if timeremap.is_remapped(clip) or getattr(clip, "speed", 1.0) <= 0:
        return []
    salida: list[list[float]] = []
    for inicio, fin in sorted(source_ranges):
        a = clip.start + (inicio - clip.in_point) / clip.speed
        b = clip.start + (fin - clip.in_point) / clip.speed
        a, b = max(a, clip.start), min(b, clip.end)
        if b - a < minimum:
            continue
        if salida and a <= salida[-1][1] + 1e-6:
            salida[-1][1] = max(salida[-1][1], b)
        else:
            salida.append([a, b])
    return [(round(a, 6), round(b, 6)) for a, b in salida]


@dataclass
class CutRanges(Command):
    """Quita los tramos `[(inicio, fin)]` de la línea de tiempo del clip, cerrando hueco."""

    item: object = None
    ranges: list = field(default_factory=list)
    removed: float = 0.0
    count: int = 0
    name: str = "Quitar tramos"

    def apply(self, sequence) -> bool:
        self.removed, self.count = 0.0, 0
        if self.item is None or not editable(sequence, self.item):
            return False
        for inicio, fin in sorted(self.ranges, reverse=True):
            pieza = self._piece(sequence, inicio, fin)
            if pieza is None:
                continue
            duracion = pieza.duration
            if RippleDelete(item=pieza).apply(sequence):
                self.removed += duracion
                self.count += 1
        return self.count > 0

    def _piece(self, sequence, inicio: float, fin: float):
        """Deja el tramo como un clip aparte —con sus enlazados— y lo devuelve."""
        clip = self.item
        if track_of(sequence, clip) is None or fin <= clip.start + 1e-6 or inicio >= clip.end - 1e-6:
            return None
        pista = track_of(sequence, clip)
        if fin < clip.end - 1e-6:
            Split(items=[clip], time=fin).apply(sequence)
        if inicio > clip.start + 1e-6:
            corte = Split(items=[clip], time=inicio)
            if not corte.apply(sequence):
                return None
            return next((c for c in corte.created if track_of(sequence, c) is pista), None)
        return clip
