"""Marcadores con nota y color, en la secuencia y dentro de los clips."""

import pytest

from vortex_studio.model import Clip, Marker, Sequence
from vortex_studio.model.commands import split_item
from vortex_studio.model.serialize import load_project, save_project
from vortex_studio.ui.dialogs import MarkerDialog


def test_nota_y_color_se_guardan(tmp_path):
    from vortex_studio.model import Project

    proyecto = Project()
    proyecto.active.add_marker(1.0, "intro", color="#5cb85c", note="entra la voz")
    clip = proyecto.active.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 4.0))
    clip.markers = [Marker(time=0.5, name="golpe", color="#e0574a", note="subir volumen")]

    leido = load_project(save_project(proyecto, tmp_path / "p")).active
    m = leido.markers[0]
    assert (m.name, m.color, m.note) == ("intro", "#5cb85c", "entra la voz")
    c = leido.video_tracks()[-1].clips[0].markers[0]
    assert isinstance(c, Marker) and (c.time, c.name, c.note) == (0.5, "golpe", "subir volumen")


def test_un_proyecto_viejo_sin_nota_abre(tmp_path):
    from vortex_studio.model.serialize import project_from_dict

    datos = {"formato": 3, "sequences": [{"tracks": [], "markers": [
        {"time": 1.0, "name": "x", "color": "#ffffff"}]}]}
    assert project_from_dict(datos).active.markers[0].note == ""


def test_marcador_en_el_clip_viaja_con_el_clip(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana._seek(2.0)
    marcador = ventana.add_marker_to_clip("aquí")
    assert marcador.time == pytest.approx(2.0)
    assert ventana.history.undo_label == "Marcador en el clip"

    clip.start = 10.0
    assert clip.start + clip.markers[0].time == pytest.approx(12.0)


def test_fuera_del_clip_no_pone_marcador(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    ventana.timeline.playhead = 50.0
    assert ventana.add_marker_to_clip() is None


def test_dividir_reparte_los_marcadores():
    seq = Sequence.default()
    clip = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 6.0))
    clip.markers = [Marker(time=1.0, name="a"), Marker(time=4.0, name="b")]
    segunda = split_item(seq, clip, 3.0)
    assert [m.name for m in clip.markers] == ["a"]
    assert [(m.name, m.time) for m in segunda.markers] == [("b", 1.0)]


def test_editar_y_borrar(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.add_marker()
    marcador = ventana.sequence.markers[0]
    ventana.update_marker(marcador, None, name="corte", note="revisar", color="#5f9bd8")
    assert (marcador.name, marcador.note, marcador.color) == ("corte", "revisar", "#5f9bd8")
    assert ventana.history.undo_label == "Editar marcador"
    ventana.delete_marker(marcador)
    assert ventana.sequence.markers == []


def test_el_dialogo_entrega_sus_valores(qapp):
    marcador = Marker(time=0.0, name="uno", color="#e0574a", note="n")
    dialogo = MarkerDialog(None, marcador, "clip")
    assert dialogo.values() == {"name": "uno", "note": "n", "color": "#e0574a"}
    dialogo.set_values(name=" dos ", note="otra", color="Verde")
    assert dialogo.values() == {"name": "dos", "note": "otra", "color": "#5cb85c"}


def test_el_timeline_encuentra_los_dos_tipos(ventana, media):
    ventana._place_video(media["mudo"])
    tl = ventana.timeline
    tl.pixels_per_second = 80
    ventana._seek(1.0)
    ventana.add_marker("regla")
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana._seek(3.0)
    ventana.add_marker_to_clip("dentro")

    m, dueno = tl.markers_near(tl.x_for(1.0), 10)
    assert m.name == "regla" and dueno is None
    y = tl._track_top(ventana.sequence.tracks.index(ventana._track_of(clip))) + 20
    m, dueno = tl.markers_near(tl.x_for(3.0), y)
    assert m.name == "dentro" and dueno is clip


def test_el_iman_se_pega_al_marcador_del_clip(ventana, media):
    ventana._place_video(media["mudo"])
    tl = ventana.timeline
    tl.pixels_per_second = 80
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    clip.markers = [Marker(time=2.5)]
    assert tl._snap(2.45) == pytest.approx(2.5)
