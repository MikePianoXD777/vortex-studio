"""Mostrar, bloquear, silenciar y solo por pista."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip, ImageOverlay, Sequence, Title
from vortex_studio.model.commands import Delete, Paste, Split, copy_items


# --- el modelo ------------------------------------------------------------

def test_solo_manda_y_silencio_gana(secuencia):
    a1, a2, a3 = secuencia.audio_tracks()
    assert secuencia.audible_tracks() == [a1, a2, a3]
    a2.solo = True
    assert secuencia.audible_tracks() == [a2]
    a3.solo = True
    a3.muted = True
    assert secuencia.audible_tracks() == [a2]
    a2.solo = a3.solo = False
    assert secuencia.audible_tracks() == [a1, a2]


def test_una_pista_oculta_no_se_pinta(secuencia):
    v2, v1 = secuencia.video_tracks()
    abajo = v1.add(Clip("/tmp/a.mp4", 0.0, 4.0))
    arriba = v2.add(Clip("/tmp/b.mp4", 0.0, 4.0))
    assert [c for c, _ in secuencia.video_stack_at(1.0)] == [arriba]
    v2.enabled = False
    assert [c for c, _ in secuencia.video_stack_at(1.0)] == [abajo]
    assert secuencia.top_clip_at(1.0) is abajo


def test_texto_e_imagenes_ocultos(secuencia):
    t1 = secuencia.text_tracks()[0]
    t1.add(Title(start=0.0, duration=2.0))
    secuencia.video_tracks()[0].add(ImageOverlay(start=0.0, duration=2.0, source="/tmp/l.png"))
    t1.enabled = False
    secuencia.video_tracks()[0].enabled = False
    assert secuencia.titles_at(1.0) == [] and secuencia.overlays_at(1.0) == []


def test_lo_bloqueado_no_se_borra_ni_se_corta(secuencia):
    v1 = secuencia.video_tracks()[-1]
    clip = v1.add(Clip("/tmp/a.mp4", 0.0, 4.0))
    v1.locked = True
    assert not Delete(items=[clip]).apply(secuencia)
    assert not Split(items=[clip], time=2.0).apply(secuencia)
    assert v1.clips == [clip]


def test_pegar_no_cae_en_pista_bloqueada(secuencia):
    v2, v1 = secuencia.video_tracks()
    clip = v1.add(Clip("/tmp/a.mp4", 0.0, 2.0))
    entradas = copy_items(secuencia, [clip])
    v1.locked = True
    comando = Paste(entries=entradas, time=5.0)
    assert comando.apply(secuencia)
    assert secuencia.track_of(comando.created[0]) is v2


def test_se_guardan(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    v2, v1 = proyecto.active.video_tracks()
    v2.enabled = False
    v1.locked = True
    a1 = proyecto.active.audio_tracks()[0]
    a1.muted = a1.solo = True
    leido = load_project(save_project(proyecto, tmp_path / "p")).active
    v2, v1 = leido.video_tracks()
    a1 = leido.audio_tracks()[0]
    assert (v2.enabled, v1.locked, a1.muted, a1.solo) == (False, True, True, True)


# --- en la ventana --------------------------------------------------------

def centro_del_boton(ventana, pista, nombre):
    indice = ventana.sequence.tracks.index(pista)
    rect = dict(ventana.timeline.header_buttons(indice))[nombre]
    return QPoint(int(rect.center().x()), int(rect.center().y()))


def test_clic_en_la_cabecera_silencia_y_se_deshace(ventana, media):
    ventana._place_video(media["sonoro"])
    a1 = ventana.sequence.audio_tracks()[0]
    QTest.mouseClick(ventana.timeline, Qt.LeftButton, Qt.NoModifier,
                     centro_del_boton(ventana, a1, "muted"))
    assert a1.muted
    assert ventana.history.undo_label == "Silenciar A1"
    assert ventana._audio_clips() == []
    ventana.undo()
    assert not ventana.sequence.audio_tracks()[0].muted


def test_ocultar_v1_desde_la_cabecera_deja_negro(ventana, media):
    from PySide6.QtGui import QColor

    ventana._place_video(media["gris"])
    v1 = ventana.sequence.video_tracks()[-1]
    QTest.mouseClick(ventana.timeline, Qt.LeftButton, Qt.NoModifier,
                     centro_del_boton(ventana, v1, "enabled"))
    assert not v1.enabled
    assert ventana.history.undo_label == "Ocultar V1"
    ventana._seek(0.5)
    assert ventana._layers_at(0.5) == []


def test_un_clip_bloqueado_no_se_selecciona_con_el_mouse(ventana, media):
    ventana._place_video(media["mudo"])
    v1 = ventana.sequence.video_tracks()[-1]
    ventana.set_track_flag(v1, "locked", True)
    tl = ventana.timeline
    y = int(tl._track_top(ventana.sequence.tracks.index(v1)) + 20)
    QTest.mouseClick(tl, Qt.LeftButton, Qt.NoModifier, QPoint(int(tl.x_for(1.0)), y))
    assert tl.selected is None


def test_borrar_con_la_pista_bloqueada_avisa(ventana, media):
    ventana._place_video(media["mudo"])
    v1 = ventana.sequence.video_tracks()[-1]
    clip = v1.clips[0]
    ventana.timeline.select(clip)
    v1.locked = True
    ventana.delete_selected()
    assert v1.clips == [clip]
    assert "bloqueada" in ventana.statusBar().currentMessage()


def test_la_exportacion_respeta_el_silencio(ventana, media):
    import numpy as np

    ventana._place_video(media["sonoro"])
    ventana.set_track_flag(ventana.sequence.audio_tracks()[0], "muted", True)
    assert ventana._audio_clips() == []
    ventana.set_track_flag(ventana.sequence.audio_tracks()[0], "muted", False)
    frames = list(AudioMixer(ventana._audio_clips()).stream(0.0, 1.0))
    assert np.abs(np.concatenate([f.to_ndarray()[0] for f in frames])).mean() > 0.05
