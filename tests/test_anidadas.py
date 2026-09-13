"""Secuencias anidadas en la ventana: anidar, entrar, pintar, sonar y guardar."""

import numpy as np
import pytest
from PySide6.QtGui import QColor

from vortex_studio.model import Clip
from vortex_studio.model.project import NestedClip


def anidar_video(ventana, media, fuente="gris"):
    ventana._place_video(media[fuente])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    return ventana.nest_selection()


def test_anidar_mueve_la_seleccion_a_una_secuencia_nueva(ventana, media):
    madre = ventana.sequence
    anidada = anidar_video(ventana, media, "sonoro")
    assert isinstance(anidada, NestedClip)
    hija = ventana.project.sequence_by_id(anidada.sequence_id)
    assert hija is not None and hija is not madre
    assert [c for t in madre.tracks for c in t.clips] == [anidada]    # el audio también se fue
    assert sum(len(t.clips) for t in hija.tracks) == 2
    assert anidada.duration == pytest.approx(6.0)
    assert ventana.history.undo_label == "Anidar"


def test_la_anidada_se_ve_en_la_madre(ventana, media):
    anidada = anidar_video(ventana, media)
    ventana._seek(0.5)
    img = ventana.preview.current_image()
    assert 100 < QColor(img.pixel(80, 60)).lightness() < 160


def test_corregir_la_anidada_colorea_el_resultado(ventana, media):
    anidada = anidar_video(ventana, media)
    anidada.color.exposure = 100
    cuadro = next(ventana._frames(0.5, 0.6, 30))
    assert QColor(cuadro.pixel(80, 60)).lightness() > 200


def test_la_anidada_suena_en_la_madre(ventana, media):
    anidada = anidar_video(ventana, media, "sonoro")
    clips = ventana._audio_clips()
    assert len(clips) == 1 and clips[0].source == media["sonoro"]
    anidada.start, anidada.in_point, anidada.duration = 10.0, 2.0, 3.0
    corrido = ventana._audio_clips()[0]
    assert corrido.start == pytest.approx(10.0) and corrido.in_point == pytest.approx(2.0)
    assert corrido.duration == pytest.approx(3.0)


def test_entrar_editar_y_volver_se_ve_en_la_madre(ventana, media):
    madre = ventana.sequence
    anidada = anidar_video(ventana, media)
    ventana.open_nested(anidada)
    assert ventana.sequence.id == anidada.sequence_id
    ventana.sequence.video_tracks()[-1].clips[0].color.saturation = 0
    ventana.sequence.video_tracks()[-1].clips[0].color.exposure = -300
    ventana._commit("oscurecer")
    ventana.switch_sequence(madre.id)
    assert ventana.sequence is madre
    ventana._seek(0.5)
    img = ventana.preview.current_image()
    assert QColor(img.pixel(80, 60)).lightness() < 40


def test_no_deja_meter_una_secuencia_en_si_misma(ventana, media):
    anidada = anidar_video(ventana, media)
    hija_id = anidada.sequence_id
    madre_id = ventana.sequence.id
    ventana.open_nested(anidada)
    assert ventana.insert_sequence(madre_id) is None          # la madre dentro de la hija: ciclo
    assert "ciclo" in ventana.statusBar().currentMessage()
    assert ventana.insert_sequence(hija_id) is None
    assert not any(isinstance(c, NestedClip) for t in ventana.sequence.tracks for c in t.clips)


def test_insertar_otra_secuencia(ventana, media):
    ventana._place_video(media["gris"])
    otra = ventana.new_sequence()
    ventana._place_video(media["mudo"])
    ventana.switch_sequence(ventana.project.sequences[0].id)
    insertada = ventana.insert_sequence(otra.id)
    assert isinstance(insertada, NestedClip) and insertada.duration == pytest.approx(6.0)


def test_guardar_y_abrir_con_anidadas_y_activa(tmp_path, ventana, media):
    from vortex_studio.model.serialize import load_project, save_project

    anidada = anidar_video(ventana, media, "sonoro")
    ventana.open_nested(anidada)
    leido = load_project(save_project(ventana.project, tmp_path / "p"))
    assert len(leido.sequences) == 2
    assert leido.active.id == anidada.sequence_id
    madre = next(s for s in leido.sequences if s.id != anidada.sequence_id)
    nueva = madre.video_tracks()[-1].clips[0]
    assert isinstance(nueva, NestedClip) and nueva.sequence_id == anidada.sequence_id


def test_la_cola_exporta_la_anidada(tmp_path, ventana, media):
    import av

    anidar_video(ventana, media, "sonoro")
    job = ventana.queue_export(tmp_path / "anidada.mp4", 0.0, 2.0, "Borrador")
    assert ventana.render_queue.wait(60) and job.status == "Listo", job.error
    with av.open(str(job.path)) as c:
        assert sorted(s.type for s in c.streams) == ["audio", "video"]
