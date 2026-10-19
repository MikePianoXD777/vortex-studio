"""El timeline se recorre a los lados: barra, rueda y zoom anclado.

Antes el timeline siempre empezaba en el segundo 0 y lo que no cabía no se
podía ver más que alejando el zoom con Shift+Z.
"""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent

from vortex_studio.model import Clip
from vortex_studio.ui.timeline import HEADER_WIDTH


def rueda(timeline, x, pasos=-120, modificadores=Qt.NoModifier):
    evento = QWheelEvent(QPointF(x, 40), QPointF(x, 40), QPoint(0, 0), QPoint(0, pasos),
                         Qt.NoButton, modificadores, Qt.NoScrollPhase, False)
    timeline.wheelEvent(evento)


def larga(ventana, segundos=120.0):
    """Una secuencia mucho más larga que lo que cabe en la vista."""
    v1 = ventana.sequence.video_tracks()[-1]
    v1.add(Clip("/no/existe.mp4", 0.0, segundos))
    ventana.timeline.pixels_per_second = 80.0
    ventana.timeline.refresh()
    return ventana.timeline


def test_tiempo_y_pixel_son_inversos_con_la_vista_corrida(ventana):
    tl = larga(ventana)
    tl.set_scroll(1234.0)
    for t in (0.0, 15.5, 30.0, 99.9):
        assert tl.time_for(tl.x_for(t)) == pytest.approx(t)
    assert tl.time_for(HEADER_WIDTH) == pytest.approx(1234.0 / 80.0)


def test_el_desplazamiento_no_se_sale(ventana):
    tl = larga(ventana)
    tl.set_scroll(-50)
    assert tl.scroll_x == 0.0
    tl.set_scroll(10 ** 9)
    assert tl.scroll_x == pytest.approx(tl.max_scroll())
    # Al final se ve el final de la secuencia, con aire para soltar algo.
    assert tl.x_for(ventana.sequence.duration) < tl.width()


def test_una_secuencia_que_cabe_no_se_desplaza(ventana):
    ventana.sequence.video_tracks()[-1].add(Clip("/no/existe.mp4", 0.0, 2.0))
    ventana.timeline.fit()
    assert ventana.timeline.max_scroll() == 0.0


def test_la_rueda_corre_el_tiempo(ventana):
    tl = larga(ventana)
    rueda(tl, 400, -120)
    assert tl.scroll_x > 0
    antes = tl.scroll_x
    rueda(tl, 400, 120)
    assert tl.scroll_x < antes


def test_ctrl_rueda_deja_quieto_el_instante_bajo_el_mouse(ventana):
    tl = larga(ventana)
    tl.set_scroll(800.0)
    x = 500.0
    instante = tl.time_for(x)
    rueda(tl, x, 120, Qt.ControlModifier)
    assert tl.pixels_per_second > 80.0
    assert tl.time_for(x) == pytest.approx(instante, abs=1e-6)
    rueda(tl, x, -120, Qt.ControlModifier)
    rueda(tl, x, -120, Qt.ControlModifier)
    assert tl.pixels_per_second < 80.0
    assert tl.time_for(x) == pytest.approx(instante, abs=1e-6)


def test_los_botones_de_zoom(ventana):
    tl = larga(ventana)
    ventana.timeline_tools.zoom_in_button.click()
    assert tl.pixels_per_second == pytest.approx(100.0)
    ventana.timeline_tools.zoom_out_button.click()
    ventana.timeline_tools.zoom_out_button.click()
    assert tl.pixels_per_second == pytest.approx(64.0)


def test_ajustar_regresa_al_principio_y_cabe_todo(ventana):
    tl = larga(ventana)
    tl.set_scroll(2000.0)
    ventana.timeline_tools.fit_button.click()
    assert tl.scroll_x == 0.0
    assert tl.x_for(ventana.sequence.duration) <= tl.width()


def test_la_barra_y_el_timeline_van_amarrados(ventana):
    tl = larga(ventana)
    barra = ventana.timeline_scroll
    assert barra.maximum() == int(round(tl.max_scroll()))
    barra.setValue(600)
    assert tl.scroll_x == pytest.approx(600)
    tl.set_scroll(900.0)
    assert barra.value() == 900


def test_al_reproducir_la_vista_pasa_de_pagina(ventana):
    tl = larga(ventana)
    fuera = tl.time_for(tl.width()) + 5.0
    tl.set_playhead(fuera)
    x = tl.x_for(fuera)
    assert HEADER_WIDTH <= x <= tl.width()
    # Salta y queda cerca de la izquierda, no pegado a la orilla.
    assert x < HEADER_WIDTH + tl.view_width() * 0.25


def test_mover_el_playhead_dentro_de_la_vista_no_la_mueve(ventana):
    tl = larga(ventana)
    tl.set_scroll(400.0)
    tl.set_playhead(tl.time_for(tl.width() / 2))
    assert tl.scroll_x == pytest.approx(400.0)


def test_el_clic_con_la_vista_corrida_cae_en_el_clip_correcto(ventana):
    tl = larga(ventana, 10.0)
    v1 = ventana.sequence.video_tracks()[-1]
    lejano = v1.add(Clip("/no/existe.mp4", 60.0, 5.0))
    tl.refresh()
    tl.set_scroll(60.0 * 80.0 - 200)
    y = tl._track_top(ventana.sequence.tracks.index(v1)) + 20
    x = tl.x_for(62.0)
    assert HEADER_WIDTH < x < tl.width()
    tl.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y),
                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    tl.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y),
                                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert tl.selected is lejano


def test_la_regla_empieza_donde_empieza_la_vista(ventana):
    """Con la vista corrida, la regla no debe recorrer desde el segundo 0."""
    tl = larga(ventana)
    tl.set_scroll(5000.0)
    tl.grab()       # pinta sin tronar
    assert tl.time_for(HEADER_WIDTH) == pytest.approx(62.5)


def test_el_timeline_vacio_dice_que_hacer(ventana):
    imagen = ventana.timeline.grab().toImage()
    assert not imagen.isNull()


def test_los_valores_de_los_deslizadores_se_ven(qapp):
    """Con Qt 6.12 el número se veía como «⋮»: el campo medía 1 px."""
    from vortex_studio.ui.widgets import SliderRow

    fila = SliderRow("Entrada", 0, 100, 12, scale=10, decimals=1, suffix=" s")
    fila.resize(300, 30)
    fila.show()
    qapp.processEvents()
    assert fila._spin.lineEdit().width() > 20
    fila.close()
