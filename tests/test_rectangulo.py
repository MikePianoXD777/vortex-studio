"""Seleccionar con rectángulo: arrastrar en un hueco del timeline."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from vortex_studio.model import Clip


def evento(tipo, x, y, botones=Qt.LeftButton, mods=Qt.NoModifier):
    boton = Qt.NoButton if tipo == QEvent.MouseMove else Qt.LeftButton
    return QMouseEvent(tipo, QPointF(x, y), boton, botones, mods)


def arrastrar(tl, x0, y0, x1, y1, mods=Qt.NoModifier):
    tl.mousePressEvent(evento(QEvent.MouseButtonPress, x0, y0, mods=mods))
    tl.mouseMoveEvent(evento(QEvent.MouseMove, (x0 + x1) / 2, (y0 + y1) / 2, mods=mods))
    tl.mouseMoveEvent(evento(QEvent.MouseMove, x1, y1, mods=mods))
    tl.mouseReleaseEvent(evento(QEvent.MouseButtonRelease, x1, y1, Qt.NoButton, mods))


@pytest.fixture
def tres(ventana):
    """V1: dos clips con hueco en medio; V2: uno arriba; A1: uno suelto."""
    seq = ventana.sequence
    v2, v1 = seq.video_tracks()
    a1 = seq.audio_tracks()[0]
    clips = {
        "v1a": v1.add(Clip("/a.mp4", 0.0, 2.0)),
        "v1b": v1.add(Clip("/b.mp4", 4.0, 2.0)),
        "v2": v2.add(Clip("/c.mp4", 1.0, 2.0)),
        "a1": a1.add(Clip("/m.wav", 4.5, 1.0)),
    }
    tl = ventana.timeline
    tl.pixels_per_second = 80.0
    tl.refresh()
    return tl, seq, clips


def y_de(tl, seq, pista):
    return tl._track_top(seq.tracks.index(pista)) + 20


def seleccion(tl):
    return {id(x) for x in tl.selected_items(with_links=False)}


def test_arrastrar_selecciona_lo_que_toca(tres):
    tl, seq, c = tres
    v2, v1 = seq.video_tracks()
    # Desde el hueco de V1 (segundo 3) hasta el segundo 5 en A1.
    arrastrar(tl, tl.x_for(3.0), y_de(tl, seq, v1) - 2, tl.x_for(5.0),
              y_de(tl, seq, seq.audio_tracks()[0]))
    assert seleccion(tl) == {id(c["v1b"]), id(c["a1"])}


def test_basta_con_tocarlo(tres):
    """No hace falta encerrar el clip entero: con clips largos sería imposible."""
    tl, seq, c = tres
    v2, v1 = seq.video_tracks()
    arrastrar(tl, tl.x_for(3.5), y_de(tl, seq, v2), tl.x_for(2.5), y_de(tl, seq, v1))
    assert seleccion(tl) == {id(c["v2"])}


def test_un_clic_sin_arrastrar_mueve_el_playhead(tres):
    tl, seq, c = tres
    v1 = seq.video_tracks()[1]
    tl.select(c["v1a"])
    x = tl.x_for(3.0)
    tl.mousePressEvent(evento(QEvent.MouseButtonPress, x, y_de(tl, seq, v1)))
    tl.mouseReleaseEvent(evento(QEvent.MouseButtonRelease, x, y_de(tl, seq, v1), Qt.NoButton))
    assert tl.playhead == pytest.approx(3.0, abs=0.04)
    assert tl.selected is None


def test_con_ctrl_se_suma(tres):
    tl, seq, c = tres
    v1 = seq.video_tracks()[1]
    tl.select(c["v1a"])
    arrastrar(tl, tl.x_for(3.0), y_de(tl, seq, v1), tl.x_for(5.0), y_de(tl, seq, v1),
              Qt.ControlModifier)
    assert seleccion(tl) == {id(c["v1a"]), id(c["v1b"])}


def test_las_pistas_bloqueadas_no_cuentan(tres):
    tl, seq, c = tres
    v2, v1 = seq.video_tracks()
    v1.locked = True
    arrastrar(tl, tl.x_for(-0.0) + 2, y_de(tl, seq, v2), tl.x_for(6.0), y_de(tl, seq, v1))
    assert seleccion(tl) == {id(c["v2"])}


def test_mientras_se_arrastra_se_ve_el_rectangulo(tres):
    tl, seq, c = tres
    v1 = seq.video_tracks()[1]
    tl.mousePressEvent(evento(QEvent.MouseButtonPress, tl.x_for(3.0), y_de(tl, seq, v1)))
    tl.mouseMoveEvent(evento(QEvent.MouseMove, tl.x_for(5.0), y_de(tl, seq, v1) + 30))
    assert tl.marquee_rect() is not None
    assert not tl.grab().toImage().isNull()
    tl.mouseReleaseEvent(evento(QEvent.MouseButtonRelease, tl.x_for(5.0), 0, Qt.NoButton))
    assert tl.marquee_rect() is None


def test_lo_seleccionado_se_borra_junto(ventana, tres):
    tl, seq, c = tres
    v2, v1 = seq.video_tracks()
    # Desde un hueco de V2 (no desde la orilla del clip: eso es recortar).
    arrastrar(tl, tl.x_for(3.5), y_de(tl, seq, v2), tl.x_for(1.5), y_de(tl, seq, v1))
    ventana.delete_selected()
    restantes = {x.uid for t in ventana.sequence.tracks for x in t.clips}
    assert restantes == {c["v1b"].uid, c["a1"].uid}
