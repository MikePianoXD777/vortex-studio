"""El panel de medios: importar sin poner en el timeline, buscar y arrastrar."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QDropEvent

from vortex_studio.media.thumbnails import extract, pick_time, thumbnail_path
from vortex_studio.ui.timeline import MEDIA_MIME


def importar_todo(ventana, media):
    return ventana.import_to_bin([media["sonoro"], media["tono"], media["logo"]])


def test_importar_al_panel_no_toca_el_timeline(ventana, media):
    assert importar_todo(ventana, media) == 3
    assert ventana.sequence.duration == 0
    assert ventana.media_bin.list.count() == 3
    assert ventana._dirty


def test_lo_importado_al_timeline_tambien_aparece(ventana, media):
    ventana._place_video(media["mudo"])
    assert [p.name for p in ventana.media_bin.visible_paths()] == ["mudo.mp4"]


def test_buscar_sin_acentos_ni_mayusculas(ventana, media):
    importar_todo(ventana, media)
    ventana.media_bin.search.setText("SONÓ")
    assert [p.name for p in ventana.media_bin.visible_paths()] == ["sonoro.mp4"]
    ventana.media_bin.search.setText("")
    assert len(ventana.media_bin.visible_paths()) == 3


def test_filtrar_por_clase(ventana, media):
    importar_todo(ventana, media)
    ventana.media_bin.kind.setCurrentText("Audio")
    assert [p.name for p in ventana.media_bin.visible_paths()] == ["tono.wav"]
    ventana.media_bin.kind.setCurrentText("Imágenes")
    assert [p.name for p in ventana.media_bin.visible_paths()] == ["logo.png"]


def test_las_miniaturas_llegan_y_se_guardan(ventana, media, qapp):
    importar_todo(ventana, media)
    assert ventana.media_bin.wait_thumbnails()
    qapp.processEvents()
    assert Path(media["sonoro"]) in {Path(p) for p in ventana.media_bin._thumbs}
    assert thumbnail_path(media["sonoro"]).exists()


def test_extraer_una_miniatura(media):
    frame = extract(media["sonoro"], 192)
    assert frame is not None and frame.width == 192 and frame.height == 108
    assert extract(media["tono"]) is None
    assert pick_time(100.0) == 2.0 and pick_time(6.0) == pytest.approx(0.6)


def test_doble_clic_agrega_en_el_playhead(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.import_to_bin([media["tono"]])
    ventana._seek(2.0)
    ventana.media_bin.insert_requested.emit(Path(media["tono"]))
    audio = ventana.sequence.audio_tracks()[0].clips
    assert len(audio) == 1 and audio[0].start == pytest.approx(2.0)


def test_soltar_en_el_timeline(ventana, media):
    importar_todo(ventana, media)
    tl = ventana.timeline
    tl.pixels_per_second = 80
    v2 = ventana.sequence.video_tracks()[0]
    indice = ventana.sequence.tracks.index(v2)
    datos = ventana.media_bin.mime_for([media["sonoro"]])
    assert datos.hasFormat(MEDIA_MIME)

    pos = QPointF(tl.x_for(3.0), tl._track_top(indice) + 20)
    evento = QDropEvent(pos, Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
    tl.dropEvent(evento)

    assert len(v2.clips) == 1 and v2.clips[0].start == pytest.approx(3.0, abs=0.05)
    audio = next(t for t in ventana.sequence.audio_tracks() if t.clips).clips[0]
    assert audio.link == v2.clips[0].link and audio.start == v2.clips[0].start


def test_el_panel_se_llena_al_abrir_el_proyecto(tmp_path, ventana, media, monkeypatch):
    from vortex_studio.model.serialize import save_project

    importar_todo(ventana, media)
    destino = save_project(ventana.project, tmp_path / "p")
    ventana._dirty = False
    ventana.new_project()
    assert ventana.media_bin.list.count() == 0

    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(destino), "")))
    ventana.open_project()
    assert ventana.media_bin.list.count() == 3
