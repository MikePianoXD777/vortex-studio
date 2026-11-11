"""El almacén de imágenes de Vortex Photo.

Las capas no llevan píxeles, solo el id de su imagen. El id es el hash del
contenido, así que la misma imagen pegada dos veces ocupa lugar una vez y
deshacer/rehacer solo mueve ids. Los arreglos se guardan de solo lectura: lo
que ya está en el almacén nadie lo modifica por accidente (los pinceles
devuelven copias y se registran con un id nuevo).
"""

from __future__ import annotations

import hashlib

import numpy as np


class AssetStore:
    def __init__(self) -> None:
        self._data: dict[str, np.ndarray] = {}

    @staticmethod
    def hash_of(pixels: np.ndarray) -> str:
        """Id estable: forma + tipo + bytes. El mismo contenido da el mismo id
        en cualquier sesión (importa para guardar y cargar)."""
        px = np.ascontiguousarray(pixels)
        h = hashlib.blake2b(digest_size=16)
        h.update(f"{px.dtype.str}{px.shape}".encode())
        h.update(px.data)
        return h.hexdigest()

    def put(self, pixels: np.ndarray) -> str:
        px = np.asarray(pixels)
        if px.dtype != np.uint8:
            px = np.clip(px, 0, 255).astype(np.uint8)
        asset_id = self.hash_of(px)
        if asset_id not in self._data:
            copia = np.array(px, dtype=np.uint8, copy=True, order="C")
            copia.setflags(write=False)
            self._data[asset_id] = copia
        return asset_id

    def adopt(self, asset_id: str, pixels: np.ndarray) -> None:
        """Guarda bajo un id dado (al cargar un archivo, para que las capas
        sigan apuntando a lo que ya decían, aunque el códec cambie un bit)."""
        copia = np.array(pixels, dtype=np.uint8, copy=True, order="C")
        copia.setflags(write=False)
        self._data[asset_id] = copia

    def get(self, asset_id: str) -> np.ndarray:
        return self._data[asset_id]          # KeyError si no está

    def has(self, asset_id: str) -> bool:
        return asset_id in self._data

    def size(self, asset_id: str) -> tuple[int, int]:
        """(ancho, alto)."""
        a = self._data[asset_id]
        return int(a.shape[1]), int(a.shape[0])

    def ids(self) -> set[str]:
        return set(self._data)

    def collect(self, keep: set[str]) -> None:
        for k in [k for k in self._data if k not in keep]:
            del self._data[k]

    def __len__(self) -> int:
        return len(self._data)

    def nbytes(self) -> int:
        return sum(a.nbytes for a in self._data.values())
