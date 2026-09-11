"""Historial de deshacer y rehacer.

Guarda instantáneas completas de la secuencia en vez de operaciones
reversibles. Con proyectos de este tamaño una instantánea son unos pocos
kilobytes, y a cambio es imposible que deshacer deje el proyecto en un
estado que nunca existió — que es el error clásico de los historiales que
invierten operación por operación.

Reutiliza la misma serialización del archivo .vortex: si algo se guarda,
se deshace igual.
"""

from __future__ import annotations

from vortex_studio.model.project import Sequence
from vortex_studio.model.serialize import sequence_from_dict, sequence_to_dict

LIMIT = 100


class History:
    def __init__(self, limit: int = LIMIT) -> None:
        self._states: list[tuple[str, dict]] = []
        self._index = -1
        self._limit = limit

    def reset(self, sequence: Sequence) -> None:
        """Arranca el historial desde este estado, sin nada que deshacer."""
        self._states = [("Inicio", sequence_to_dict(sequence))]
        self._index = 0

    def push(self, sequence: Sequence, label: str) -> None:
        """Registra un cambio ya aplicado.

        Si veníamos de deshacer, lo que estaba adelante se descarta: acaba
        de nacer una rama nueva y la vieja ya no es alcanzable.
        """
        snapshot = sequence_to_dict(sequence)
        if self._index >= 0 and snapshot == self._states[self._index][1]:
            return  # nada cambió de verdad

        del self._states[self._index + 1:]
        self._states.append((label, snapshot))

        if len(self._states) > self._limit:
            self._states.pop(0)
        self._index = len(self._states) - 1

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    @property
    def undo_label(self) -> str:
        return self._states[self._index][0] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        return self._states[self._index + 1][0] if self.can_redo else ""

    def undo(self) -> Sequence | None:
        if not self.can_undo:
            return None
        self._index -= 1
        return sequence_from_dict(self._states[self._index][1])

    def redo(self) -> Sequence | None:
        if not self.can_redo:
            return None
        self._index += 1
        return sequence_from_dict(self._states[self._index][1])
