"""Fixtures de las pruebas de la interfaz de Vortex Photo."""

import gc

import pytest
from PySide6.QtCore import QEvent


@pytest.fixture
def foto(qapp):
    """Una ventana de Vortex Photo limpia, con el lienzo ajustado a la ventana."""
    from vortex_studio.ui.photo import PhotoWindow

    w = PhotoWindow()
    w.resize(1280, 720)
    w.show()
    qapp.processEvents()
    w.canvas.fit()
    w.canvas.flush()
    yield w
    w.session.dirty = False         # closeEvent preguntaría y un diálogo colgaría la prueba
    w.close()
    # Sin esto cada prueba deja su ventana viva y el banco entero se come la memoria.
    w.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    gc.collect()


@pytest.fixture
def s(foto):
    return foto.session


@pytest.fixture
def lienzo(foto):
    return foto.canvas
