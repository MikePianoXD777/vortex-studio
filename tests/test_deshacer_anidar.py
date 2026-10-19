"""Deshacer «Anidar» también quita la secuencia que creó; rehacer la regresa.

Antes la anidada se quedaba en el proyecto, huérfana, y se guardaba con él.
"""

from vortex_studio.model import Clip
from vortex_studio.model.project import NestedClip


def anidar(ventana, media):
    ventana._place_video(media["gris"])
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    return ventana.nest_selection()


def ids(ventana):
    return [s.id for s in ventana.project.sequences]


def test_deshacer_anidar_quita_la_secuencia(ventana, media):
    anidada = anidar(ventana, media)
    assert anidada.sequence_id in ids(ventana)
    ventana.undo()
    assert anidada.sequence_id not in ids(ventana)
    assert len(ventana.project.sequences) == 1


def test_rehacer_la_regresa_la_misma(ventana, media):
    anidada = anidar(ventana, media)
    hija = ventana.project.sequence_by_id(anidada.sequence_id)
    ventana.undo()
    ventana.redo()
    assert ventana.project.sequence_by_id(anidada.sequence_id) is hija
    clip = next(c for t in ventana.sequence.tracks for c in t.clips)
    assert isinstance(clip, NestedClip) and clip.sequence_id == hija.id


def test_lo_editado_adentro_sobrevive_a_deshacer_y_rehacer(ventana, media):
    anidada = anidar(ventana, media)
    madre = ventana.sequence.id
    ventana.switch_sequence(anidada.sequence_id)
    ventana.sequence.video_tracks()[-1].add(Clip(media["gris"], 5.0, 1.0))
    ventana._commit("Agregar")
    ventana.switch_sequence(madre)
    ventana.undo()
    ventana.redo()
    hija = ventana.project.sequence_by_id(anidada.sequence_id)
    assert sum(len(t.clips) for t in hija.tracks) == 2
    # Y su historial también regresa: se puede deshacer lo de adentro.
    ventana.switch_sequence(hija.id)
    assert ventana.history.undo_label == "Agregar"


def test_lo_que_se_guarda_tras_deshacer_no_trae_la_huerfana(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    anidar(ventana, media)
    ventana.undo()
    destino = tmp_path / "p.vortex"
    save_project(ventana.project, destino)
    assert len(load_project(destino).sequences) == 1


def test_una_secuencia_hecha_a_mano_no_se_toca(ventana, media):
    """Solo se apartan las que nacieron de una edición. «Nueva secuencia»
    no es una edición de la línea de tiempo y no se deshace."""
    madre = ventana.sequence.id
    nueva = ventana.new_sequence()
    ventana.switch_sequence(madre)
    ventana._place_video(media["gris"])
    ventana.undo()
    assert nueva.id in ids(ventana)


def test_anidada_dentro_de_anidada(ventana, media):
    """Deshacer la de afuera aparta las dos; rehacer regresa las dos."""
    anidar(ventana, media)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    exterior = ventana.nest_selection()
    assert len(ventana.project.sequences) == 3
    ventana.undo()
    assert len(ventana.project.sequences) == 2
    ventana.undo()
    assert len(ventana.project.sequences) == 1
    ventana.redo()
    ventana.redo()
    assert len(ventana.project.sequences) == 3
    assert exterior.sequence_id in ids(ventana)


def test_abrir_otro_proyecto_olvida_lo_apartado(ventana, media):
    anidar(ventana, media)
    ventana.undo()
    ventana._dirty = False
    ventana.new_project()
    assert not ventana._set_aside and not ventana._made_sequences
