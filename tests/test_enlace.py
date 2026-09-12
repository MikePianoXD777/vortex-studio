"""Video y audio enlazados: se editan como uno solo."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vortex_studio.model import Clip, Link, Sequence, Unlink
from vortex_studio.model.commands import link_offset


def importar(ventana, media):
    ventana._place_video(media["sonoro"])
    return (ventana.sequence.video_tracks()[-1].clips[0],
            ventana.sequence.audio_tracks()[0].clips[0])


def test_al_importar_entran_enlazados(ventana, media):
    video, audio = importar(ventana, media)
    assert video.link and video.link == audio.link
    assert ventana.sequence.linked(video) == [audio]


def test_borrar_el_video_se_lleva_su_audio(ventana, media):
    video, audio = importar(ventana, media)
    ventana.timeline.select(video)
    ventana.delete_selected()
    assert not ventana.sequence.video_tracks()[-1].clips
    assert not ventana.sequence.audio_tracks()[0].clips


def test_alt_agarra_un_solo_lado(ventana, media):
    video, audio = importar(ventana, media)
    tl = ventana.timeline
    y = int(tl._track_top(ventana.sequence.tracks.index(ventana._track_of(audio))) + 20)
    QTest.mouseClick(tl, Qt.LeftButton, Qt.AltModifier, QPoint(int(tl.x_for(1.0)), y))
    assert tl.selected is audio and tl.ignore_link
    ventana.delete_selected()
    assert ventana.sequence.video_tracks()[-1].clips == [video]


def test_cortar_parte_los_dos_y_las_mitades_quedan_enlazadas(ventana, media):
    video, audio = importar(ventana, media)
    ventana._seek(2.0)
    ventana.timeline.select(video)
    ventana.cut_at_playhead()
    v1 = ventana.sequence.video_tracks()[-1].clips
    a1 = ventana.sequence.audio_tracks()[0].clips
    assert len(v1) == len(a1) == 2
    assert v1[0].link == a1[0].link
    assert v1[1].link == a1[1].link
    assert v1[0].link != v1[1].link


def test_arrastrar_el_video_mueve_el_audio(ventana, media):
    video, audio = importar(ventana, media)
    tl = ventana.timeline
    ventana.timeline.pixels_per_second = 80
    y = int(tl._track_top(ventana.sequence.tracks.index(ventana._track_of(video))) + 20)
    x0 = int(tl.x_for(2.0))
    QTest.mousePress(tl, Qt.LeftButton, Qt.NoModifier, QPoint(x0, y))
    QTest.mouseMove(tl, QPoint(x0 + 80, y))
    QTest.mouseRelease(tl, Qt.LeftButton, Qt.NoModifier, QPoint(x0 + 80, y))
    assert video.start == pytest.approx(1.0, abs=0.05)
    assert audio.start == pytest.approx(video.start)
    assert ventana.history.undo_label == "Mover clip"


def test_recortar_la_cola_recorta_los_dos(ventana, media):
    video, audio = importar(ventana, media)
    tl = ventana.timeline
    tl.pixels_per_second = 80
    y = int(tl._track_top(ventana.sequence.tracks.index(ventana._track_of(video))) + 20)
    x0 = int(tl.x_for(video.end)) - 2
    QTest.mousePress(tl, Qt.LeftButton, Qt.NoModifier, QPoint(x0, y))
    QTest.mouseMove(tl, QPoint(x0 - 160, y))
    QTest.mouseRelease(tl, Qt.LeftButton, Qt.NoModifier, QPoint(x0 - 160, y))
    assert video.duration == pytest.approx(4.0, abs=0.1)
    assert audio.duration == pytest.approx(video.duration)


def test_ctrl_l_desenlaza_y_vuelve_a_enlazar(ventana, media):
    video, audio = importar(ventana, media)
    ventana.timeline.select(video)
    ventana.toggle_link()
    assert not video.link and not audio.link
    assert ventana.history.undo_label == "Desenlazar"

    ventana.timeline.select(video)
    ventana.timeline.toggle_extra(audio)
    ventana.toggle_link()
    assert video.link and video.link == audio.link


def test_enlazar_uno_solo_avisa(ventana, media):
    video, audio = importar(ventana, media)
    ventana.timeline.select(video)
    ventana.toggle_link()
    ventana.timeline.select(video)
    ventana.toggle_link()
    assert not video.link
    assert "Ctrl+clic" in ventana.statusBar().currentMessage()


def test_desfase_entre_enlazados():
    seq = Sequence.default()
    v = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 4.0, link="x"))
    a = seq.audio_tracks()[0].add(Clip("/tmp/a.mp4", 0.0, 4.0, link="x"))
    assert link_offset(seq, v) == 0
    a.in_point = 0.5
    assert link_offset(seq, v) == pytest.approx(-0.5)
    assert link_offset(seq, a) == pytest.approx(0.5)


def test_el_slip_mueve_los_dos(ventana, media):
    video, audio = importar(ventana, media)
    ventana.timeline.select(video)
    video.duration = audio.duration = 3.0
    ventana.slip_selected(15)
    assert video.in_point == pytest.approx(0.5)
    assert audio.in_point == pytest.approx(video.in_point)


def test_comandos_de_modelo():
    seq = Sequence.default()
    v = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 4.0))
    a = seq.audio_tracks()[0].add(Clip("/tmp/a.mp4", 0.0, 4.0))
    assert not Link(items=[v]).apply(seq)
    assert Link(items=[v, a]).apply(seq) and v.link == a.link
    assert Unlink(items=[a]).apply(seq) and not v.link and not a.link


def test_el_enlace_se_guarda(tmp_path, ventana, media):
    from vortex_studio.model.serialize import load_project, save_project

    importar(ventana, media)
    leido = load_project(save_project(ventana.project, tmp_path / "p")).active
    assert leido.video_tracks()[-1].clips[0].link == leido.audio_tracks()[0].clips[0].link != ""
