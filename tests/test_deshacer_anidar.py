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


# --- solo se aparta con el deshacer de la edición que la creó ---------------

def anidada_sin_usar(ventana, media):
    """Anida y luego borra el clip anidado en la madre: la hija se queda sola."""
    anidada = anidar(ventana, media)
    ventana.timeline.select(anidada)
    ventana.delete_selected()
    assert anidada.sequence_id in ids(ventana)
    return anidada


def test_deshacer_adentro_de_una_anidada_sin_usar_no_la_saca(ventana, media):
    """Antes, deshacer adentro de ella la apartaba mientras se editaba (se
    comparaba el objeto, y deshacer da uno nuevo), y el segundo deshacer
    escribía la hija encima de la madre y dejaba el proyecto vacío."""
    anidada = anidada_sin_usar(ventana, media)
    madre = ventana.project.sequences[0].id
    ventana.switch_sequence(anidada.sequence_id)
    ventana._place_video(media["gris"], at=8.0)
    ventana._place_video(media["gris"], at=16.0)
    ventana.undo()
    assert anidada.sequence_id in ids(ventana)
    assert ventana.project.active is ventana.sequence
    ventana.undo()
    assert ids(ventana) == [madre, anidada.sequence_id]
    assert ventana.project.active is ventana.sequence
    assert ventana.sequence.id == anidada.sequence_id


def test_deshacer_otra_cosa_no_aparta_la_anidada_sin_usar(ventana, media, tmp_path):
    """Antes cualquier deshacer apartaba la anidada que el usuario había dejado
    sin usar, con lo que tuviera adentro, y ya no se guardaba."""
    from vortex_studio.model.serialize import load_project

    anidada = anidar(ventana, media)
    madre = ventana.sequence.id
    ventana.switch_sequence(anidada.sequence_id)
    ventana._place_video(media["gris"], at=8.0)
    ventana.switch_sequence(madre)
    ventana.timeline.select(anidada)
    ventana.delete_selected()
    ventana._place_video(media["gris"], at=20.0)
    ventana.undo()
    assert anidada.sequence_id in ids(ventana)
    ventana.redo()
    assert anidada.sequence_id in ids(ventana)

    ventana._path = tmp_path / "p.vortex"
    assert ventana.save()
    leido = load_project(ventana._path)
    hija = leido.sequence_by_id(anidada.sequence_id)
    assert hija is not None and sum(len(t.clips) for t in hija.tracks) == 2


def test_deshacer_en_otra_secuencia_no_aparta_la_anidada(ventana, media):
    anidada = anidada_sin_usar(ventana, media)
    ventana.new_sequence()
    ventana._place_video(media["gris"])
    ventana.undo()
    assert anidada.sequence_id in ids(ventana)


def test_deshacer_otra_cosa_dentro_de_la_madre_no_aparta_la_que_se_usa(ventana, media):
    anidada = anidar(ventana, media)
    ventana._place_video(media["gris"], at=20.0)
    ventana.undo()
    assert anidada.sequence_id in ids(ventana)
    ventana.undo()
    assert anidada.sequence_id not in ids(ventana)


def test_anidada_dentro_de_la_anidada_se_va_y_vuelve_con_ella(ventana, media):
    """La que se creó adentro de la hija se queda huérfana si la hija se va:
    se aparta con ella, y vuelve con ella."""
    anidada = anidar(ventana, media)
    madre = ventana.sequence.id
    ventana.switch_sequence(anidada.sequence_id)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    nieta = ventana.nest_selection()
    ventana.switch_sequence(madre)
    ventana.undo()
    assert ids(ventana) == [madre]
    ventana.redo()
    assert set(ids(ventana)) == {madre, anidada.sequence_id, nieta.sequence_id}


def test_no_se_aparta_si_otra_secuencia_la_usa(ventana, media):
    """Deshacer «Anidar» con la anidada pegada en otra secuencia la habría
    dejado colgando ahí."""
    anidada = anidar(ventana, media)
    madre = ventana.sequence.id
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    ventana.new_sequence()
    ventana.paste()
    ventana.switch_sequence(madre)
    ventana.undo()
    assert anidada.sequence_id in ids(ventana)


# --- lo apartado que se vuelve a usar regresa -------------------------------

def test_pegar_la_anidada_tras_deshacer_anidar_la_regresa(ventana, media, tmp_path):
    """Antes el clip pegado apuntaba a una secuencia que no estaba en el
    proyecto: se veía vacío y se guardaba colgando."""
    from vortex_studio.model.serialize import load_project

    anidada = anidar(ventana, media)
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    ventana.undo()
    assert anidada.sequence_id not in ids(ventana)
    ventana._scrubbed(10.0)
    ventana.paste()
    assert anidada.sequence_id in ids(ventana)
    assert anidada.sequence_id not in ventana._set_aside

    ventana._path = tmp_path / "p.vortex"
    assert ventana.save()
    leido = load_project(ventana._path)
    assert leido.sequence_by_id(anidada.sequence_id) is not None


def test_rehacer_en_otra_secuencia_regresa_la_que_usa(ventana, media):
    """El pegado se deshace en una secuencia, «Anidar» en otra, y rehacer el
    pegado vuelve a usar la apartada: tiene que regresar."""
    anidada = anidar(ventana, media)
    madre = ventana.sequence.id
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    otra = ventana.new_sequence()
    ventana.paste()
    ventana.undo()
    ventana.switch_sequence(madre)
    ventana.undo()
    assert anidada.sequence_id not in ids(ventana)
    ventana.switch_sequence(otra.id)
    ventana.redo()
    assert anidada.sequence_id in ids(ventana)


def test_pegar_la_apartada_tambien_revisa_ciclos(ventana, media):
    """La apartada que contiene a esta secuencia no se puede pegar en ella:
    con la apartada fuera del proyecto la revisión no la veía."""
    madre = ventana.sequence.id
    otra = ventana.new_sequence()
    ventana._place_video(media["gris"])
    ventana.switch_sequence(madre)
    metida = ventana.insert_sequence(otra.id)
    ventana.timeline.select(metida)
    anidada = ventana.nest_selection()
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    ventana.undo()
    ventana.switch_sequence(otra.id)
    antes = sum(len(t.clips) for t in ventana.sequence.tracks)
    ventana.paste()
    assert sum(len(t.clips) for t in ventana.sequence.tracks) == antes
    assert "dentro de sí misma" in ventana.statusBar().currentMessage()
