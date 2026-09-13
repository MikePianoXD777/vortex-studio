"""Estabilización por correlación de fase."""

import shutil
import subprocess
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from vortex_studio.media.stabilize import (
    STABILIZER,
    analyze,
    corrections,
    load_or_analyze,
    phase_shift,
    radius_for,
    smoothed,
    zoom_for,
)

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def temblor(tmp_path_factory):
    """Un recorte de 240×135 que tiembla sobre un testsrc2 de 320×180."""
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("estab") / "temblor.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=30:duration=3,"
                    "crop=240:135:x='40+14*sin(n*1.7)':y='22+9*cos(n*2.3)'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", str(ruta)],
                   check=True)
    return ruta


# --- medir ----------------------------------------------------------------

def test_la_correlacion_encuentra_un_desplazamiento_conocido():
    rng = np.random.default_rng(3)
    base = rng.random((90, 160)).astype(np.float32)
    movida = np.roll(np.roll(base, 5, axis=1), -3, axis=0)
    dx, dy = phase_shift(base, movida)
    assert dx == pytest.approx(5, abs=0.3) and dy == pytest.approx(-3, abs=0.3)


def test_sin_movimiento_da_cero():
    rng = np.random.default_rng(7)
    base = rng.random((90, 160)).astype(np.float32)
    assert phase_shift(base, base) == pytest.approx((0.0, 0.0), abs=0.05)


def test_la_toma_temblorosa_tiene_trayectoria_que_tiembla(temblor):
    trayectoria = analyze(temblor)
    assert len(trayectoria) == pytest.approx(90, abs=2)
    saltos = np.abs(np.diff(trayectoria[:, 1]))
    assert saltos.mean() > 0.01            # varios pixeles por cuadro, en fracción


def test_corregir_deja_la_toma_quieta(temblor):
    trayectoria = analyze(temblor)
    corr = corrections(trayectoria, 100, 30)
    corregida = trayectoria[:, 1:3] + corr
    temblor_antes = np.abs(np.diff(trayectoria[:, 1:3], axis=0)).mean()
    temblor_despues = np.abs(np.diff(corregida, axis=0)).mean()
    assert temblor_despues < temblor_antes * 0.35


# --- suavizar ---------------------------------------------------------------

def test_un_paneo_limpio_no_se_corrige_casi():
    t = np.arange(90) / 30
    trayectoria = np.column_stack([t, t * 0.1, np.zeros_like(t)])
    corr = corrections(trayectoria, 100, 30)
    # Fuera de las orillas: con radio de 30 cuadros, los primeros y últimos 30
    # promedian contra el relleno y ahí sí se mueven un poco.
    assert np.abs(corr[31:-31]).max() < 1e-6


def test_la_fuerza_decide_el_radio_y_cero_apaga():
    assert radius_for(100, 30) == 30 and radius_for(10, 30) == 3
    trayectoria = np.column_stack([np.arange(10), np.random.default_rng(1).random((10, 2))])
    assert np.all(corrections(trayectoria, 0) == 0)
    assert smoothed(trayectoria, 0).shape == (10, 2)


def test_el_zoom_tapa_las_orillas_con_tope():
    assert zoom_for(np.array([[0.02, -0.05]])) == pytest.approx(1.10)
    assert zoom_for(np.array([[0.4, 0.0]])) == 1.25
    assert zoom_for(np.zeros((0, 2))) == 1.0


def test_el_analisis_se_guarda_y_se_reutiliza(temblor):
    primero = load_or_analyze(temblor)
    inicio = time.monotonic()
    segundo = load_or_analyze(temblor)
    assert time.monotonic() - inicio < 0.2
    assert np.allclose(primero, segundo)
    assert STABILIZER.offset(temblor, 1.0, 80) is not None
    assert STABILIZER.offset(temblor, 1.0, 0) is None


# --- en la ventana ------------------------------------------------------------

def esperar(condicion, segundos=60):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_prender_estabilizacion_analiza_y_corrige_el_cuadro(ventana, temblor):
    ventana._place_video(temblor)
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana.effects_panel.stabilize.setChecked(True)
    assert clip.stabilize > 0
    assert esperar(lambda: STABILIZER.has_analysis(temblor))
    capa = ventana._layers_at(1.5, sync=True)[0]
    assert capa.framing["stabilize"] is not None
    assert capa.framing["stabilize"][2] > 1.0            # el zoom que tapa orillas


def test_la_estabilizacion_se_guarda_y_se_pega(tmp_path, ventana, temblor):
    from vortex_studio.model import Clip
    from vortex_studio.model.commands import paste_attributes
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(temblor)
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    clip.stabilize = 60
    leido = load_project(save_project(ventana.project, tmp_path / "p")).active
    assert leido.video_tracks()[-1].clips[0].stabilize == 60
    otro = Clip(temblor, 10.0, 1.0)
    assert paste_attributes(clip, otro, ("Efectos",)) and otro.stabilize == 60
