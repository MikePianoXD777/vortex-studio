"""Llave de croma con supresión de derrame."""

import shutil
import subprocess

import av
import numpy as np
import pytest
from PySide6.QtGui import QColor

from vortex_studio.media.color import ColorProcessor
from vortex_studio.model import Clip
from vortex_studio.model.chroma import ChromaKey
from vortex_studio.model.color import ColorAdjust

FFMPEG = shutil.which("ffmpeg")


def cuadro(fondo=(0, 177, 64), centro=(220, 30, 30)):
    arr = np.zeros((60, 80, 3), dtype="uint8")
    arr[:] = fondo
    arr[20:40, 30:50] = centro
    return av.VideoFrame.from_ndarray(arr, format="rgb24")


def procesar(key, adjust=None, frame=None):
    salida = ColorProcessor().apply(frame or cuadro(), adjust, key)
    return salida.to_ndarray()


@pytest.fixture(scope="module")
def pantalla_verde(tmp_path_factory):
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("croma") / "verde.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=0x00b140:size=160x120:rate=30:duration=2,"
                    "drawbox=x=60:y=40:w=40:h=40:color=red@1:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv444p", "-crf", "0", str(ruta)],
                   check=True)
    return ruta


# --- el modelo ------------------------------------------------------------

def test_apagada_no_cambia_la_firma_ni_el_cuadro():
    key = ChromaKey()
    assert key.signature == () and not key.is_on
    assert ColorProcessor().apply(cuadro(), None, key).format.name == "rgb24"


def test_el_derrame_se_elige_por_el_canal_dominante():
    assert ChromaKey(color="#00b140").spill_type == "green"
    assert ChromaKey(color="#0047bb").spill_type == "blue"
    assert ChromaKey(enabled=True, similarity=40).signature != ChromaKey(enabled=True).signature


# --- los pixeles ----------------------------------------------------------

def test_quita_el_fondo_y_deja_al_sujeto():
    arr = procesar(ChromaKey(enabled=True))
    assert arr.shape[2] == 4
    assert arr[5, 5, 3] < 10, "el verde tenía que volverse transparente"
    assert arr[30, 40, 3] > 245, "el rojo del centro tenía que quedar opaco"


def test_la_similitud_decide_cuanto_se_va():
    parecido = cuadro(centro=(40, 150, 90))           # un verde apagado, no el de la pantalla
    poca = procesar(ChromaKey(enabled=True, similarity=5, smoothness=0), frame=parecido)
    mucha = procesar(ChromaKey(enabled=True, similarity=70, smoothness=0), frame=parecido)
    assert poca[30, 40, 3] > 200
    assert mucha[30, 40, 3] < 60


def test_el_derrame_le_quita_verde_a_la_piel():
    piel = cuadro(centro=(150, 190, 140))                # piel con reflejo verde
    sin = procesar(ChromaKey(enabled=True, similarity=10, spill=0), frame=piel)
    con = procesar(ChromaKey(enabled=True, similarity=10, spill=100), frame=piel)
    assert con[30, 40, 1] < sin[30, 40, 1] - 15


def test_corregir_color_no_se_come_el_alfa():
    arr = procesar(ChromaKey(enabled=True), ColorAdjust(exposure=100, saturation=40))
    assert arr[5, 5, 3] < 10 and arr[30, 40, 3] > 245
    assert arr[30, 40, 0] != 220                        # la corrección sí se aplicó


# --- en la ventana --------------------------------------------------------

def preparar(ventana, media, verde):
    ventana._place_video(media["gris"])
    arriba = ventana.sequence.video_tracks()[0]
    clip = Clip(source=verde, start=0.0, duration=2.0)
    arriba.add(clip)
    ventana._commit("prueba")
    return clip


def test_se_ve_la_pista_de_abajo_por_donde_estaba_el_verde(ventana, media, pantalla_verde):
    clip = preparar(ventana, media, pantalla_verde)
    ventana.timeline.select(clip)
    ventana.effects_panel.key_enabled.setChecked(True)
    assert clip.chroma.enabled and ventana.history.undo_label == "Llave de croma"
    assert len(ventana.sequence.video_stack_at(1.0)) == 2

    ventana._seek(1.0)
    img = ventana.preview.current_image()
    esquina, centro = QColor(img.pixel(10, 10)), QColor(img.pixel(80, 60))
    assert abs(esquina.red() - esquina.green()) < 25 and 90 < esquina.lightness() < 170
    assert centro.red() > 180 and centro.green() < 80


def test_la_exportacion_tambien_quita_el_fondo(ventana, media, pantalla_verde):
    clip = preparar(ventana, media, pantalla_verde)
    clip.chroma.enabled = True
    img = next(ventana._frames(1.0, 1.1, 30))
    esquina = QColor(img.pixel(10, 10))
    assert esquina.green() < esquina.red() + 25


def test_el_panel_mueve_los_controles_y_se_guarda(tmp_path, ventana, media, pantalla_verde):
    from vortex_studio.model.serialize import load_project, save_project

    clip = preparar(ventana, media, pantalla_verde)
    ventana.timeline.select(clip)
    panel = ventana.effects_panel
    assert not panel.similarity.isEnabled()
    panel.key_enabled.setChecked(True)
    panel.similarity._slider.setValue(55)
    panel.set_key_color("#0047bb")
    assert (clip.chroma.similarity, clip.chroma.color) == (55, "#0047bb")

    leido = load_project(save_project(ventana.project, tmp_path / "p")).active
    llave = leido.video_tracks()[0].clips[0].chroma
    assert (llave.enabled, llave.similarity, llave.color) == (True, 55, "#0047bb")


def test_pegar_efectos_lleva_la_llave():
    from vortex_studio.model import Sequence
    from vortex_studio.model.commands import paste_attributes

    a = Clip("/tmp/a.mp4", 0.0, 1.0)
    a.chroma = ChromaKey(enabled=True, spill=80)
    b = Clip("/tmp/b.mp4", 1.0, 1.0)
    assert paste_attributes(a, b, ("Efectos",))
    assert b.chroma.enabled and b.chroma.spill == 80 and b.chroma is not a.chroma
