"""PROVISIONAL: almacén de imágenes mínimo para poder correr la interfaz."""

from __future__ import annotations

import hashlib

import numpy as np


class AssetStore:
    def __init__(self) -> None:
        self._data: dict[str, np.ndarray] = {}

    def put(self, pixels: np.ndarray) -> str:
        arr = np.ascontiguousarray(pixels, dtype=np.uint8)
        h = hashlib.sha1(str(arr.shape).encode())
        h.update(arr.tobytes())
        asset_id = h.hexdigest()[:24]
        if asset_id not in self._data:
            arr = arr.copy()
            arr.setflags(write=False)
            self._data[asset_id] = arr
        return asset_id

    def get(self, asset_id: str) -> np.ndarray:
        return self._data[asset_id]

    def has(self, asset_id: str) -> bool:
        return asset_id in self._data

    def size(self, asset_id: str) -> tuple[int, int]:
        a = self._data[asset_id]
        return int(a.shape[1]), int(a.shape[0])

    def ids(self) -> set[str]:
        return set(self._data)

    def collect(self, keep: set[str]) -> None:
        for k in list(self._data):
            if k not in keep:
                del self._data[k]
