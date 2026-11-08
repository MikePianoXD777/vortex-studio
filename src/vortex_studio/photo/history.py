"""PROVISIONAL: historial por instantáneas."""

from __future__ import annotations

import json

from vortex_studio.photo.document import Document, document_from_dict, document_to_dict


class PhotoHistory:
    def __init__(self) -> None:
        self._stack: list[tuple[str, str]] = []
        self._pos = -1

    def reset(self, doc: Document) -> None:
        self._stack = [("Inicio", json.dumps(document_to_dict(doc)))]
        self._pos = 0

    def push(self, doc: Document, label: str) -> None:
        del self._stack[self._pos + 1:]
        self._stack.append((label, json.dumps(document_to_dict(doc))))
        self._pos = len(self._stack) - 1

    def undo(self) -> Document | None:
        if not self.can_undo:
            return None
        self._pos -= 1
        return document_from_dict(json.loads(self._stack[self._pos][1]))

    def redo(self) -> Document | None:
        if not self.can_redo:
            return None
        self._pos += 1
        return document_from_dict(json.loads(self._stack[self._pos][1]))

    @property
    def can_undo(self) -> bool:
        return self._pos > 0

    @property
    def can_redo(self) -> bool:
        return self._pos < len(self._stack) - 1

    @property
    def undo_label(self) -> str:
        return self._stack[self._pos][0] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        return self._stack[self._pos + 1][0] if self.can_redo else ""

    def assets_in_use(self) -> set[str]:
        usados: set[str] = set()
        for _, s in self._stack:
            usados |= document_from_dict(json.loads(s)).assets()
        return usados
