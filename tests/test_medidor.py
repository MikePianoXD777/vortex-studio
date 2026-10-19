"""El medidor de audio junto al timeline."""

import time

import numpy as np
import pytest

from vortex_studio.ui.meters import FLOOR_DB, AudioMeter, to_db


def test_decibeles():
    assert to_db(1.0) == pytest.approx(0.0)
    assert to_db(0.5) == pytest.approx(-6.02, abs=0.01)
    assert to_db(0.0) == FLOOR_DB


def test_sube_al_instante_y_retiene_el_pico(qapp):
    medidor = AudioMeter()
    medidor.set_levels(1.0, 0.5)
    assert medidor.shown == pytest.approx([0.0, -6.02], abs=0.01)
    medidor.set_levels(0.1, 0.1)
    assert medidor.hold[0] == pytest.approx(0.0)        # la rayita se queda arriba


def test_baja_despacio_al_pausar(qapp):
    medidor = AudioMeter()
    medidor.set_levels(1.0, 1.0)
    medidor.reset()
    time.sleep(0.25)
    medidor._animate()
    assert FLOOR_DB < medidor.shown[0] < 0.0            # bajando, sin brincar a cero
    medidor.shown = [FLOOR_DB, FLOOR_DB]
    medidor.hold = [FLOOR_DB, FLOOR_DB]
    medidor._animate()
    assert not medidor._timer.isActive()                # en reposo no gasta


def test_la_luz_del_limitador_se_queda_hasta_el_clic(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    medidor = AudioMeter()
    medidor.resize(46, 200)
    medidor.set_levels(0.9, 0.9, limited=True)
    medidor.set_levels(0.1, 0.1, limited=False)
    assert medidor.limited
    QTest.mouseClick(medidor, Qt.LeftButton, Qt.NoModifier, QPoint(20, 8))
    assert not medidor.limited


def test_se_dibuja(qapp):
    medidor = AudioMeter()
    medidor.resize(46, 200)
    medidor.set_levels(0.7, 0.3, limited=True)
    imagen = medidor.grab().toImage()
    assert not imagen.isNull()


def test_el_reproductor_mide_por_ventanas(qapp):
    from vortex_studio.ui.audio_player import METER_WINDOW, AudioPlayer

    jugador = AudioPlayer()
    muestras = np.zeros((METER_WINDOW * 3, 2), dtype=np.int16)
    muestras[METER_WINDOW + 5, 0] = 16384            # medio, en la segunda ventana
    muestras[2 * METER_WINDOW + 1, 1] = -32768        # todo, en la tercera
    jugador._measure(muestras.tobytes())
    niveles = list(jugador._levels)
    assert [n[0] for n in niveles] == [0, METER_WINDOW, 2 * METER_WINDOW]
    assert niveles[1][1] == pytest.approx(0.5)
    assert niveles[2][2] == pytest.approx(1.0)
    assert jugador.levels() == (0.0, 0.0, False)      # sin tarjeta sonando, nada


def test_la_ventana_alimenta_el_medidor_al_reproducir(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana._playing = True
    ventana._audio_on = True
    ventana.audio.position = lambda: 1.0
    ventana.audio.levels = lambda: (0.8, 0.4, True)
    ventana._tick()
    assert ventana.meter.shown[0] == pytest.approx(to_db(0.8))
    assert ventana.meter.limited
    ventana._playing = True
    ventana._pause()
    assert ventana.meter._target == [FLOOR_DB, FLOOR_DB]


def test_el_medidor_va_a_la_derecha_del_timeline(ventana):
    t = ventana.timeline.geometry()
    m = ventana.meter.geometry()
    assert m.left() >= t.right()
    assert ventana.meter.isVisible()
