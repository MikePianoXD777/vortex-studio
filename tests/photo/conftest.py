"""Las pruebas del motor de Vortex Photo comparten la aplicación Qt del banco
(una `QApplication`): si el motor creara su propia `QGuiApplication` antes, el
resto del banco —que sí usa widgets— no podría crear la suya."""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _qt_del_banco(qapp):
    return qapp
