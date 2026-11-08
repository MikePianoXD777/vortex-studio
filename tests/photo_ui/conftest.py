"""Fixtures de las pruebas de la interfaz de Vortex Photo."""

import pytest


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
    qapp.processEvents()


@pytest.fixture
def s(foto):
    return foto.session


@pytest.fixture
def lienzo(foto):
    return foto.canvas
