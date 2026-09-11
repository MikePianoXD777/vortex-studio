"""Banco de pruebas de Vortex Studio.

Genera su propio material con ffmpeg la primera vez y lo reutiliza, así que
no depende de que haya videos a la mano ni deja basura en el proyecto.

Todo corre sin mostrar ventanas (`offscreen`), por eso se puede ejecutar en
una terminal, por SSH o en un servidor sin pantalla.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Debe quedar puesto ANTES de que cualquier import cree la QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


# En Windows suele venir como ffmpeg.exe y puede no estar en el PATH.
FFMPEG = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    """Material de prueba: video mudo, video con audio, e imagen."""
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg en el PATH para generar el material de prueba")

    base = tmp_path_factory.mktemp("media")

    mudo = base / "mudo.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mudo))

    sonoro = base / "sonoro.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6,volume=12dB",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(sonoro))

    gris = base / "gris.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:size=160x120:rate=30:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "0", str(gris))

    logo = base / "logo.png"
    _ffmpeg("-f", "lavfi",
            "-i", "color=c=black:size=120x120,format=rgba,"
                  "geq=r=40:g=200:b=140:a='if(lt(hypot(X-60,Y-60),55),255,0)'",
            "-frames:v", "1", str(logo))

    return {"mudo": mudo, "sonoro": sonoro, "gris": gris, "logo": logo}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from vortex_studio.app import _dark_palette

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    return app


@pytest.fixture
def ventana(qapp):
    """Una ventana limpia por prueba, cerrada al terminar.

    Se marca como guardada antes de cerrar porque `closeEvent` pregunta si
    hay cambios pendientes, y un diálogo modal colgaría la prueba.
    """
    from vortex_studio.ui import MainWindow

    w = MainWindow()
    w.resize(1200, 700)
    w.show()
    qapp.processEvents()
    yield w

    w._dirty = False
    w.close()
    qapp.processEvents()


@pytest.fixture
def secuencia():
    from vortex_studio.model import Sequence
    return Sequence.default()


@pytest.fixture(autouse=True)
def sin_dialogos_modales(monkeypatch, request):
    """Hace que un diálogo modal falle en vez de colgar la prueba.

    Un QMessageBox dentro de una prueba se queda esperando un clic que nunca
    llega: la prueba no falla, se congela, y de paso arrastra a todas las que
    vienen atrás. Ya pasó una vez con el aviso de la transición.

    Las pruebas que sí quieren verificar un diálogo pueden pedir el permiso
    marcándose con @pytest.mark.permite_dialogos.
    """
    if request.node.get_closest_marker("permite_dialogos"):
        return

    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    def prohibido(nombre):
        def _falla(*args, **kwargs):
            raise AssertionError(
                f"{nombre} abrió un diálogo modal durante la prueba. "
                f"Usa la barra de estado, o marca la prueba con "
                f"@pytest.mark.permite_dialogos.")
        return _falla

    for clase, metodos in (
        (QMessageBox, ("information", "warning", "critical", "question", "about")),
        (QInputDialog, ("getText", "getInt", "getDouble", "getItem")),
        (QFileDialog, ("getOpenFileName", "getSaveFileName", "getExistingDirectory")),
    ):
        for metodo in metodos:
            monkeypatch.setattr(clase, metodo,
                                staticmethod(prohibido(f"{clase.__name__}.{metodo}")),
                                raising=False)
