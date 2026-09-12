"""Fundido a negro y a blanco."""

import pytest
from PySide6.QtGui import QColor

from vortex_studio.model import Clip, Fill, Sequence
from vortex_studio.model.project import CROSS, DIP_BLACK, DIP_WHITE


def dos_clips(tipo):
    seq = Sequence.default()
    pista = seq.video_tracks()[-1]
    a = pista.add(Clip("/tmp/a.mp4", 0.0, 4.0))
    b = pista.add(Clip("/tmp/b.mp4", 4.0, 4.0, dissolve=2.0, transition=tipo))
    return seq, a, b


def test_a_mitad_del_fundido_solo_hay_color():
    seq, a, b = dos_clips(DIP_BLACK)
    capas = seq.video_stack_at(4.0)
    fill = [(c, p) for c, p in capas if isinstance(c, Fill)]
    assert fill and fill[0][0].color == "#000000"
    assert fill[0][1] == pytest.approx(1.0)


def test_primera_mitad_se_ve_el_que_sale_cubriendose():
    seq, a, b = dos_clips(DIP_BLACK)
    capas = seq.video_stack_at(3.5)       # avance 0.25
    assert capas[0] == (a, 1.0)
    assert isinstance(capas[1][0], Fill) and capas[1][1] == pytest.approx(0.5)


def test_segunda_mitad_se_ve_el_que_entra_descubriendose():
    seq, a, b = dos_clips(DIP_WHITE)
    capas = seq.video_stack_at(4.5)       # avance 0.75
    assert capas[0] == (b, 1.0)
    assert capas[1][0].color == "#ffffff" and capas[1][1] == pytest.approx(0.5)


def test_la_cruzada_sigue_igual():
    seq, a, b = dos_clips(CROSS)
    capas = seq.video_stack_at(4.0)
    assert {id(c) for c, _ in capas} == {id(a), id(b)}
    assert sum(p for _, p in capas) == pytest.approx(1.0)


@pytest.mark.parametrize("tipo, esperado", [(DIP_BLACK, 0), (DIP_WHITE, 255)])
def test_en_pantalla(ventana, media, tipo, esperado):
    ventana._place_video(media["gris"])
    ventana._place_video(media["gris"])
    segundo = ventana.sequence.video_tracks()[-1].clips[1]
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0, tipo)
    assert ventana.history.undo_label == ("Fundido a negro" if tipo == DIP_BLACK
                                          else "Fundido a blanco")

    ventana._seek(segundo.start)
    img = ventana.preview.current_image()
    assert abs(QColor(img.pixel(80, 60)).lightness() - esperado) < 12

    ventana._seek(1.0)
    img = ventana.preview.current_image()
    assert 100 < QColor(img.pixel(80, 60)).lightness() < 160


def test_lo_exportado_pasa_por_negro(ventana, media):
    ventana._place_video(media["gris"])
    ventana._place_video(media["gris"])
    segundo = ventana.sequence.video_tracks()[-1].clips[1]
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0, DIP_BLACK)
    cuadro = next(ventana._frames(segundo.start, segundo.start + 0.1, 30))
    assert QColor(cuadro.pixel(80, 60)).lightness() < 12


def test_el_tipo_se_elige_en_el_panel(ventana, media):
    ventana._place_video(media["gris"])
    ventana._place_video(media["gris"])
    segundo = ventana.sequence.video_tracks()[-1].clips[1]
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0)
    ventana.clip_panel._transition.setCurrentText(DIP_WHITE)
    assert segundo.transition == DIP_WHITE
    ventana.undo()
    assert ventana.sequence.video_tracks()[-1].clips[1].transition == CROSS


def test_se_guarda(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    pista = proyecto.active.video_tracks()[-1]
    pista.add(Clip("/tmp/a.mp4", 0.0, 2.0))
    pista.add(Clip("/tmp/b.mp4", 2.0, 2.0, dissolve=1.0, transition=DIP_WHITE))
    leido = load_project(save_project(proyecto, tmp_path / "p"))
    assert leido.active.video_tracks()[-1].clips[1].transition == DIP_WHITE
