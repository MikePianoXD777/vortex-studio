"""El propio banco de pruebas: que falle rápido y que pase en todas partes.

Dos versiones salieron sin binarios porque el banco tronaba solo en la
máquina de compilación (Ubuntu 22.04, con el ffmpeg 4.4 de apt): el material
de prueba usaba opciones que ese ffmpeg no conoce. Y un diálogo modal que el
candado no atrapa no hace fallar la prueba: congela el banco entero.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

# Habla como el ffmpeg 4.4 de la máquina de compilación, aunque el de verdad
# sea uno nuevo: no conoce lo que llegó después, y lo que el 4.4 sí sabía se
# lo traduce al nuevo, que ya lo quitó.
VIEJO = """\
import os
import sys

REAL = {real!r}
NUEVO = {nuevo!r}
NO_CONOCE = {no_conoce!r}

args = sys.argv[1:]
for arg in args:
    if arg.split(":")[0] in NO_CONOCE:
        sys.stderr.write("Unrecognized option '%s'.\\n"
                         "Error splitting the argument list: Option not found\\n" % arg[1:])
        sys.exit(8)
if NUEVO:
    args = ["-fps_mode" if a == "-vsync" else a for a in args]
    if "-metadata:s:v:0" in args:
        i = args.index("-metadata:s:v:0")
        if args[i + 1].startswith("rotate="):
            # El 4.4 guardaba `rotate` como giro horario; el nuevo ya no lo
            # escribe y -display_rotation lo cuenta al revés.
            grados = float(args[i + 1].split("=", 1)[1])
            del args[i:i + 2]
            j = args.index("-i")
            args[j:j] = ["-display_rotation", str(-grados)]
os.execv(REAL, [REAL, *args])
"""

COMO_EL_44 = ("-fps_mode", "-display_rotation")


def _es_nuevo() -> bool:
    ayuda = subprocess.run([FFMPEG, "-hide_banner", "-h", "full"],
                           capture_output=True, text=True).stdout
    return "-fps_mode" in ayuda


def _material_con(tmp_path, no_conoce, *argumentos):
    """Corre las pruebas del material difícil con un ffmpeg que no conoce esas opciones."""
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg en el PATH")
    if os.name == "nt":
        pytest.skip("El ffmpeg de mentiras es un script de sh")

    guion = tmp_path / "ffmpeg_viejo.py"
    guion.write_text(VIEJO.format(real=FFMPEG, nuevo=_es_nuevo(), no_conoce=no_conoce),
                     encoding="utf-8")
    carpeta = tmp_path / "bin"
    carpeta.mkdir()
    falso = carpeta / "ffmpeg"
    falso.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} '
                     f'{shlex.quote(str(guion))} "$@"\n', encoding="utf-8")
    falso.chmod(0o755)

    entorno = dict(os.environ, PATH=f"{carpeta}{os.pathsep}{os.environ.get('PATH', '')}")
    salida = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
         f"--basetemp={tmp_path / 'banco'}", "tests/test_material_dificil.py", *argumentos],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=900)
    resumen = salida.stdout.strip().splitlines()[-1] if salida.stdout.strip() else ""
    return salida, resumen


# --- el ffmpeg de la máquina de compilación ---------------------------------------------

def test_el_material_dificil_sale_con_el_ffmpeg_de_la_maquina_de_compilacion(tmp_path):
    """Con `-fps_mode` a secas, ahí tronaba la fixture y las 27 pruebas con ella."""
    salida, resumen = _material_con(tmp_path, COMO_EL_44)
    assert salida.returncode == 0, salida.stdout[-4000:] + salida.stderr[-2000:]
    assert "Este ffmpeg no sabe" not in salida.stdout, salida.stdout[-4000:]
    assert re.search(r"\d+ passed", resumen), resumen


def test_si_no_sabe_hacer_cuadros_disparejos_solo_saltan_esas(tmp_path):
    """Que le falte una pieza no tumba las pruebas que no la usan."""
    salida, resumen = _material_con(tmp_path, (*COMO_EL_44, "-vsync"),
                                    "-k", "fps_variable or hevc")
    assert salida.returncode == 0, salida.stdout[-4000:] + salida.stderr[-2000:]
    assert "cuadros disparejos" in salida.stdout, salida.stdout[-4000:]
    assert re.search(r"\d+ passed", resumen) and re.search(r"\d+ skipped", resumen), resumen
    assert "error" not in resumen, resumen


# --- el candado de diálogos -----------------------------------------------------------

@contextmanager
def _sin_colgarse(segundos=3.0):
    """Si de todos modos se abre un diálogo modal, lo cierra a los pocos segundos.

    Sin el candado, estas pruebas fallan en vez de colgarse, que es justo lo
    que el candado debe lograr. Dice qué alcanzó a abrirse.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    abiertos = []

    def cerrar():
        modal = QApplication.activeModalWidget()
        if modal is None:
            modal = next((w for w in QApplication.topLevelWidgets()
                          if isinstance(w, QDialog) and w.isVisible()), None)
        if modal is not None:
            abiertos.append(type(modal).__name__)
            modal.reject()

    reloj = QTimer()
    reloj.setInterval(int(segundos * 1000))
    reloj.timeout.connect(cerrar)
    reloj.start()
    try:
        yield abiertos
    finally:
        reloj.stop()


def test_una_caja_abierta_con_exec_hace_fallar_la_prueba(qapp, sin_dialogos_modales):
    from PySide6.QtWidgets import QMessageBox

    caja = QMessageBox()
    caja.setText("¿Seguro?")
    with _sin_colgarse() as abiertos:
        with pytest.raises(AssertionError, match="QMessageBox.exec abrió un diálogo modal"):
            caja.exec()
    assert abiertos == []
    assert sin_dialogos_modales == ["QMessageBox.exec"]
    sin_dialogos_modales.clear()        # provocado a propósito


@pytest.mark.parametrize("nombre", ["QDialog", "QInputDialog", "QFileDialog"])
def test_cualquier_dialogo_abierto_con_exec_hace_fallar_la_prueba(qapp, sin_dialogos_modales,
                                                                  nombre):
    from PySide6 import QtWidgets

    dialogo = getattr(QtWidgets, nombre)()
    with _sin_colgarse() as abiertos:
        with pytest.raises(AssertionError, match=f"{nombre}.exec"):
            dialogo.exec()
    assert abiertos == []
    assert sin_dialogos_modales == [f"{nombre}.exec"]
    sin_dialogos_modales.clear()


def test_el_selector_de_color_tambien_hace_fallar_la_prueba(qapp):
    """Los paneles de títulos y de croma lo usan."""
    from PySide6.QtWidgets import QColorDialog

    with _sin_colgarse() as abiertos:
        with pytest.raises(AssertionError, match="QColorDialog.getColor"):
            QColorDialog.getColor()
    assert abiertos == []


CIERRA_A_MEDIAS = """\
def test_cierra_a_media_exportacion(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    ventana._dirty = False
    ventana.queue_export(tmp_path / "largo.mp4", 0.0, 6.0, "Borrador")
    assert ventana.render_queue.busy
    ventana.close()
"""


def test_cerrar_a_media_exportacion_falla_en_segundos_en_vez_de_colgarse(tmp_path):
    """El caso de verdad: una prueba de exportar cuyo `wait` se vence en una máquina lenta.

    Se corre aparte porque lo que se comprueba es el resultado de la prueba:
    PySide se traga el error del closeEvent y, sin el cobro al terminar, la
    prueba pasaba con la ventana a medio cerrar.
    """
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg en el PATH")
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    shutil.copy(RAIZ / "tests" / "conftest.py", carpeta / "conftest.py")
    (carpeta / "test_cierra.py").write_text(CIERRA_A_MEDIAS, encoding="utf-8")
    try:
        salida = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--basetemp={tmp_path / 'banco'}", str(carpeta)],
            cwd=carpeta, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        pytest.fail("Se colgó con la caja de «Hay exportaciones en curso» abierta")
    assert salida.returncode != 0, salida.stdout[-3000:]
    assert "QMessageBox.exec abrió un diálogo modal" in salida.stdout, salida.stdout[-3000:]


@pytest.mark.permite_dialogos
def test_con_el_permiso_exec_abre_de_verdad(qapp):
    from PySide6.QtWidgets import QDialog

    with _sin_colgarse(0.2) as abiertos:
        QDialog().exec()
    assert abiertos == ["QDialog"]
