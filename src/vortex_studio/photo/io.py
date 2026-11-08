"""Abrir, guardar y exportar.

`.vphoto` es un zip con `document.json` y `assets/<id>.png`. Se escribe a un
archivo temporal y se renombra al final, así un corte de luz a medio guardado
no deja un proyecto roto. Al cargar nada truena por un archivo dañado: si
no se puede leer el diseño, se lanza `PhotoFileError` con un mensaje claro; si
solo falta una imagen, el diseño abre y esa capa queda vacía.
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader, QImageWriter

from ._util import ensure_qt, from_qimage, to_qimage
from .adjust import apply_adjustments
from .assets import AssetStore
from .document import (FORMAT_VERSION, Document, Layer, Transform, document_from_dict,
                       document_to_dict)
from .filters import apply_filter
from .render import Renderer

log = logging.getLogger(__name__)

OPEN_FILTER = "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
PROJECT_FILTER = "Proyecto de Vortex Photo (*.vphoto)"
EXPORT_FORMATS = ("PNG", "JPG", "WEBP")
_EXT = {"PNG": "png", "JPG": "jpg", "WEBP": "webp"}
MAX_SIDE = 16384


class PhotoFileError(ValueError):
    """Un archivo que no se pudo leer; el texto está listo para mostrarse."""


# --- imágenes ---------------------------------------------------------------------

def _reader(source) -> QImageReader:
    ensure_qt()
    try:                                            # fotos grandes (la barrera por omisión es 256 MB)
        QImageReader.setAllocationLimit(2048)
    except Exception:                               # pragma: no cover - según la versión de Qt
        pass
    r = QImageReader(str(source))
    r.setAutoTransform(True)                        # orientación EXIF
    return r


def load_image(path) -> np.ndarray:
    """Lee una imagen como RGBA uint8, con la orientación EXIF aplicada."""
    p = Path(path)
    if not p.exists():
        raise PhotoFileError(f"No existe el archivo «{p.name}».")
    r = _reader(p)
    img = r.read()
    if img.isNull():
        raise PhotoFileError(f"No se pudo abrir «{p.name}»: {r.errorString()}")
    return from_qimage(img)


def add_image(doc: Document, store: AssetStore, path_or_pixels, *, fit: bool = True) -> Layer:
    """Agrega una imagen arriba de todo, centrada; con `fit` se reduce lo que
    haga falta para caber en el lienzo (nunca se agranda)."""
    if isinstance(path_or_pixels, np.ndarray):
        pixels, nombre = path_or_pixels, "Imagen"
    else:
        pixels, nombre = load_image(path_or_pixels), Path(path_or_pixels).stem
    if pixels.ndim == 2:
        pixels = np.stack([pixels] * 3 + [np.full_like(pixels, 255)], axis=2)
    elif pixels.shape[2] == 3:
        pixels = np.concatenate([pixels, np.full(pixels.shape[:2] + (1,), 255, np.uint8)], axis=2)
    h, w = pixels.shape[:2]
    ancho, alto = float(w), float(h)
    if fit:
        k = min(1.0, doc.width / w, doc.height / h)
        ancho, alto = w * k, h * k
    capa = Layer(kind="image", name=nombre, asset=store.put(pixels),
                 transform=Transform(cx=doc.width / 2.0, cy=doc.height / 2.0, width=ancho, height=alto))
    doc.layers.append(capa)
    return capa


# --- proyecto ------------------------------------------------------------------------

def _png_bytes(pixels: np.ndarray) -> bytes:
    if pixels.ndim == 2:
        h, w = pixels.shape
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = pixels
        rgba[..., 3] = 255
        img = to_qimage(rgba).convertToFormat(QImage.Format.Format_Grayscale8)
    else:
        img = to_qimage(pixels)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        raise OSError("No se pudo codificar una imagen del proyecto.")
    return bytes(buf.data())


def save_document(doc: Document, store: AssetStore, path) -> None:
    ensure_qt()
    destino = Path(path)
    tmp = destino.with_name(destino.name + ".tmp")
    datos = document_to_dict(doc)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr("document.json", json.dumps(datos, ensure_ascii=False), zipfile.ZIP_DEFLATED)
            for aid in sorted(doc.assets()):
                if store.has(aid):
                    z.writestr(f"assets/{aid}.png", _png_bytes(store.get(aid)), zipfile.ZIP_STORED)
                else:
                    log.warning("vphoto: falta la imagen %s al guardar", aid)
        os.replace(tmp, destino)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _decodificar(datos: bytes, mascara: bool) -> np.ndarray | None:
    img = QImage.fromData(QByteArray(datos), "PNG")
    if img.isNull():
        return None
    px = from_qimage(img)
    return np.ascontiguousarray(px[..., 0]) if mascara else px


def load_document(path) -> tuple[Document, AssetStore]:
    ensure_qt()
    p = Path(path)
    if not p.exists():
        raise PhotoFileError(f"No existe el archivo «{p.name}».")
    try:
        z = zipfile.ZipFile(p)
    except (zipfile.BadZipFile, OSError) as e:
        raise PhotoFileError(f"«{p.name}» no es un proyecto de Vortex Photo válido o está dañado.") from e
    with z:
        try:
            datos = json.loads(z.read("document.json").decode("utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("document.json no es un objeto")
        except (KeyError, ValueError, UnicodeDecodeError, zipfile.BadZipFile) as e:
            raise PhotoFileError(f"«{p.name}» no tiene un diseño legible.") from e
        try:
            doc = document_from_dict(datos)
        except Exception as e:
            raise PhotoFileError(f"«{p.name}» tiene un diseño dañado ({e}).") from e
        if int(datos.get("format", 1) or 1) > FORMAT_VERSION:
            log.warning("vphoto: %s es de una versión más nueva; se abre con lo que se entiende", p.name)
        if doc.width * doc.height > MAX_SIDE * MAX_SIDE:
            raise PhotoFileError(f"«{p.name}» declara un lienzo demasiado grande.")
        store = AssetStore()
        mascaras = {c.mask for c in doc.layers if c.mask}
        for aid in doc.assets():
            try:
                px = _decodificar(z.read(f"assets/{aid}.png"), aid in mascaras)
            except (KeyError, zipfile.BadZipFile, RuntimeError, OSError):
                px = None
            if px is None:
                log.warning("vphoto: no se pudo leer la imagen %s", aid)
                continue
            store.adopt(aid, px)
    return doc, store


# --- exportación ------------------------------------------------------------------------

def _normalizar_formato(fmt: str) -> str:
    f = str(fmt).upper().lstrip(".")
    f = {"JPEG": "JPG"}.get(f, f)
    if f not in _EXT:
        raise ValueError(f"Formato no soportado: {fmt}")
    return f


def _escribir(pixels: np.ndarray, path, fmt: str, quality: int) -> None:
    ensure_qt()
    fmt = _normalizar_formato(fmt)
    if fmt == "JPG":
        # JPG no tiene transparencia: se aplana sobre blanco (el fondo del
        # diseño, si lo hay, ya viene incluido en el render).
        if pixels[..., 3].min() != 255:
            fondo = np.empty_like(pixels)
            fondo[...] = (255, 255, 255, 255)
            from .blend import composite
            composite(fondo, pixels, "Normal", 1.0, 0, 0)
            pixels = fondo
        img = to_qimage(pixels).convertToFormat(QImage.Format.Format_RGB888)
    else:
        img = to_qimage(pixels)
    w = QImageWriter(str(path), _EXT[fmt].encode())
    w.setQuality(int(min(100, max(0, quality))))
    if not w.write(img):
        raise OSError(f"No se pudo guardar «{Path(path).name}»: {w.errorString()}")


def export(doc: Document, store: AssetStore, path, fmt: str = "PNG", quality: int = 92,
           scale: float = 1.0) -> None:
    """Dibuja el diseño a `scale` y lo guarda. JPG se aplana sobre el fondo del
    diseño (blanco si es transparente)."""
    fmt = _normalizar_formato(fmt)
    scale = max(float(scale), 0.01)
    pixels = Renderer(store).render(doc, scale)
    _escribir(pixels, path, fmt, quality)


def export_batch(paths, adjustments, flt, out_dir, fmt: str = "JPG", quality: int = 92,
                 progress: Callable[[int, int], None] | None = None) -> list[Path]:
    """Aplica los mismos ajustes y filtro a muchas fotos. Llama a
    `progress(hechas, total)` antes de empezar y tras cada foto. Las que no se
    puedan leer o escribir se saltan (con aviso en el registro) y no detienen el lote."""
    fmt = _normalizar_formato(fmt)
    paths = list(paths)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    total = len(paths)
    hechos: list[Path] = []
    if progress:
        progress(0, total)
    for i, origen in enumerate(paths, 1):
        try:
            px = load_image(origen)
            if flt is not None:
                px = apply_filter(px, flt, 1.0)
            if adjustments is not None:
                px = apply_adjustments(px, adjustments, 1.0)
            destino = out / f"{Path(origen).stem}.{_EXT[fmt]}"
            n = 2
            while destino.exists() or destino in hechos:    # no pisar nada
                destino = out / f"{Path(origen).stem}_{n}.{_EXT[fmt]}"
                n += 1
            _escribir(px, destino, fmt, quality)
            hechos.append(destino)
        except (OSError, ValueError) as e:
            log.warning("lote: se saltó %s: %s", origen, e)
        if progress:
            progress(i, total)
    return hechos
