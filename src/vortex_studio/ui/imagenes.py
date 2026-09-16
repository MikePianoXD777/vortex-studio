"""Cargar imágenes del usuario como se ven, no como están guardadas.

Una foto de celular casi siempre está guardada acostada, con una marca EXIF
que dice cómo girarla. `QImage(ruta)` no la aplica —hay que pedirla— y por eso
las fotos verticales entraban de lado. Es lo mismo que pasa con el video; ver
`media/decoder.py`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QImageReader


def load_image(path: str | Path) -> QImage:
    """La imagen ya derecha, según su marca de orientación."""
    lector = QImageReader(str(path))
    lector.setAutoTransform(True)
    imagen = lector.read()
    return imagen if not imagen.isNull() else QImage(str(path))
