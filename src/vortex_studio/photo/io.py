"""PROVISIONAL: abrir, guardar y exportar."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader

from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (KIND_IMAGE, Document, Layer, Transform,
                                          document_from_dict, document_to_dict)
from vortex_studio.photo.render import Renderer, from_qimage, to_qimage

OPEN_FILTER = "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
EXPORT_FORMATS = ("PNG", "JPG", "WEBP")


def load_image(path) -> np.ndarray:
    lector = QImageReader(str(path))
    lector.setAutoTransform(True)
    img = lector.read()
    if img.isNull():
        raise ValueError(f"No se pudo abrir {path}")
    return from_qimage(img)


def add_image(doc: Document, store: AssetStore, path_or_pixels, *, fit: bool = True) -> Layer:
    px = path_or_pixels if isinstance(path_or_pixels, np.ndarray) else load_image(path_or_pixels)
    h, w = px.shape[:2]
    k = min(1.0, doc.width * 0.8 / w, doc.height * 0.8 / h) if fit else 1.0
    name = "Imagen" if isinstance(path_or_pixels, np.ndarray) else Path(str(path_or_pixels)).stem
    layer = Layer(kind=KIND_IMAGE, name=name, asset=store.put(px),
                  transform=Transform(doc.width / 2, doc.height / 2, w * k, h * k))
    doc.layers.append(layer)
    return layer


def _png(pixels: np.ndarray) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    to_qimage(pixels).save(buf, "PNG")
    return bytes(buf.data())


def save_document(doc: Document, store: AssetStore, path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("document.json", json.dumps(document_to_dict(doc)))
        for a in doc.assets():
            z.writestr(f"assets/{a}.png", _png(_a_rgba(store.get(a))))


def _a_rgba(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return np.dstack([arr, arr, arr, np.full_like(arr, 255)])
    return arr


def load_document(path) -> tuple[Document, AssetStore]:
    store = AssetStore()
    with zipfile.ZipFile(path) as z:
        doc = document_from_dict(json.loads(z.read("document.json")))
        remap = {}
        for a in doc.assets():
            img = QImage.fromData(z.read(f"assets/{a}.png"))
            px = from_qimage(img)
            remap[a] = store.put(px if a not in {c.mask for c in doc.layers} else px[..., 0])
        for c in doc.layers:
            c.asset = remap.get(c.asset, c.asset)
            c.mask = remap.get(c.mask, c.mask) if c.mask else None
    return doc, store


def export(doc: Document, store: AssetStore, path, fmt="PNG", quality=92, scale=1.0) -> None:
    px = Renderer(store).render(doc, scale)
    img = to_qimage(px)
    if fmt.upper() in ("JPG", "JPEG"):
        base = QImage(img.size(), QImage.Format_RGB888)
        base.fill(0xFFFFFFFF if doc.background is None else int(doc.background[1:], 16) | 0xFF000000)
        from PySide6.QtGui import QPainter
        p = QPainter(base); p.drawImage(0, 0, img); p.end()
        img = base
        fmt = "JPG"
    if not img.save(str(path), fmt.upper(), int(quality)):
        raise OSError(f"No se pudo guardar {path}")


def export_batch(paths, adjustments, flt, out_dir, fmt="JPG", quality=92,
                 progress: Callable[[int, int], None] | None = None) -> list[Path]:
    salida = []
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(paths):
        img = to_qimage(load_image(p))
        destino = Path(out_dir) / (Path(p).stem + "." + fmt.lower())
        img.save(str(destino), fmt.upper(), int(quality))
        salida.append(destino)
        if progress:
            progress(i + 1, len(paths))
    return salida
