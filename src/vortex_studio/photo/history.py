"""Deshacer y rehacer.

Cada paso es una instantánea de `document_to_dict`: un diccionario pequeño,
porque las imágenes no se copian (viven en el almacén y las capas solo guardan
su id). `assets_in_use()` dice qué ids siguen haciendo falta —de cualquier
paso, para que deshacer pueda traerlos de vuelta— y el almacén puede soltar
el resto con `collect`.
"""

from __future__ import annotations

import copy

from .document import Document, document_from_dict, document_to_dict

LIMIT = 100


class PhotoHistory:
    def __init__(self, limit: int = LIMIT) -> None:
        self.limit = max(1, int(limit))
        self._steps: list[tuple[str, dict]] = []     # (etiqueta de la acción, estado después de ella)
        self._pos = -1

    def reset(self, doc: Document) -> None:
        self._steps = [("Inicio", document_to_dict(doc))]
        self._pos = 0

    def push(self, doc: Document, label: str = "") -> None:
        """Registra el estado actual como resultado de la acción `label`.
        Lo que se había deshecho (la rama de rehacer) se descarta. Un estado
        idéntico al actual no agrega paso."""
        estado = document_to_dict(doc)
        if self._pos < 0:
            self.reset(doc)
            return
        if estado == self._steps[self._pos][1]:
            return
        del self._steps[self._pos + 1:]
        self._steps.append((label, estado))
        # límite: pasos que se pueden deshacer (el estado inicial no cuenta)
        while len(self._steps) > self.limit + 1:
            self._steps.pop(0)
        self._pos = len(self._steps) - 1

    @property
    def can_undo(self) -> bool:
        return self._pos > 0

    @property
    def can_redo(self) -> bool:
        return 0 <= self._pos < len(self._steps) - 1

    @property
    def undo_label(self) -> str:
        return self._steps[self._pos][0] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        return self._steps[self._pos + 1][0] if self.can_redo else ""

    def undo(self) -> Document | None:
        if not self.can_undo:
            return None
        self._pos -= 1
        return document_from_dict(copy.deepcopy(self._steps[self._pos][1]))

    def redo(self) -> Document | None:
        if not self.can_redo:
            return None
        self._pos += 1
        return document_from_dict(copy.deepcopy(self._steps[self._pos][1]))

    def assets_in_use(self) -> set[str]:
        usados: set[str] = set()
        for _, estado in self._steps:
            for capa in estado.get("layers", []):
                if capa.get("asset"):
                    usados.add(capa["asset"])
                if capa.get("mask"):
                    usados.add(capa["mask"])
        return usados

    def __len__(self) -> int:
        return len(self._steps)
