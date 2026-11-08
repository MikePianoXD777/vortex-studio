"""Material de prueba de Vortex Photo, todo generado con numpy."""

from __future__ import annotations

import numpy as np

from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import Document, Layer, Transform


def solido(w, h, color=(128, 128, 128, 255)):
    px = np.empty((h, w, 4), np.uint8)
    px[...] = color
    return px


def degradado(w=64, h=48):
    """Gris horizontal de 0 a 255, opaco."""
    px = np.empty((h, w, 4), np.uint8)
    px[..., :3] = np.linspace(0, 255, w).astype(np.uint8)[None, :, None]
    px[..., 3] = 255
    return px


def colorido(w=64, h=48):
    """Rojo a la izquierda, verde arriba, azul fijo medio: de todo un poco."""
    px = np.empty((h, w, 4), np.uint8)
    px[..., 0] = np.linspace(0, 255, w).astype(np.uint8)[None, :]
    px[..., 1] = np.linspace(255, 0, h).astype(np.uint8)[:, None]
    px[..., 2] = 90
    px[..., 3] = 255
    return px


def ruido(w=64, h=64, semilla=1):
    rng = np.random.default_rng(semilla)
    px = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
    px[..., 3] = 255
    return px


def lum(px):
    f = px[..., :3].astype(np.float64)
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def capa_imagen(store: AssetStore, pixels, cx, cy, w=None, h=None, **kw) -> Layer:
    ph, pw = pixels.shape[:2]
    return Layer(kind="image", asset=store.put(pixels),
                 transform=Transform(cx, cy, w if w is not None else pw, h if h is not None else ph,
                                     kw.pop("rotation", 0.0), kw.pop("flip_h", False), kw.pop("flip_v", False)),
                 **kw)


def doc_con(store, w, h, *capas, fondo="#ffffff") -> Document:
    d = Document(w, h, fondo)
    d.layers.extend(capas)
    return d
