"""Capa de comandos: dividir, eliminar con ripple, y el historial con nombre."""

import pytest

from vortex_studio.model import Clip, Sequence, Title
from vortex_studio.model.commands import RippleDelete, Split, run, split_item
from vortex_studio.model.history import History


def secuencia_con(*clips):
    s = Sequence.default()
    for c in clips:
        s.video_tracks()[-1].add(c)
    return s


# --- dividir: qué se lleva cada mitad -------------------------------------

def test_la_segunda_mitad_respeta_la_velocidad():
    """Era bug: en un clip a 2× la segunda mitad leía material equivocado."""
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, in_point=1.0, speed=2.0)
    s = secuencia_con(clip)
    segunda = split_item(s, clip, 1.0)
    assert segunda.in_point == pytest.approx(3.0)       # 1 + 1 s de pista × 2
    assert clip.source_time(0.999) == pytest.approx(segunda.source_time(1.0), abs=0.01)


def test_sin_velocidad_la_segunda_mitad_sigue_leyendo_donde_iba():
    clip = Clip(source="/v.mp4", start=2.0, duration=6.0, in_point=0.5)
    s = secuencia_con(clip)
    segunda = split_item(s, clip, 5.0)
    assert segunda.in_point == pytest.approx(3.5)
    assert clip.duration == pytest.approx(3.0) and segunda.duration == pytest.approx(3.0)


def test_la_animacion_no_brinca_en_el_corte():
    """Los keyframes van relativos al inicio del clip: hay que recorrerlos."""
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0)
    clip.transform.set_key("x", 0.0, 0.0)
    clip.transform.set_key("x", 4.0, 1.0)
    clip.transform.set_key("scale", 1.0, 1.0)
    clip.transform.set_key("scale", 3.0, 2.0)
    antes = [(t, clip.transform.values_at(t)) for t in (0.3, 1.2, 1.9, 2.5, 3.7)]

    s = secuencia_con(clip)
    segunda = split_item(s, clip, 2.0)

    for t, valores in antes:
        mitad = clip if t < 2.0 else segunda
        ahora = mitad.transform.values_at(t - mitad.start)
        for prop in ("x", "scale"):
            assert ahora[prop] == pytest.approx(valores[prop], abs=1e-6), (t, prop)


def test_una_propiedad_sin_keyframes_se_queda_fija_en_las_dos():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0)
    clip.transform.rotation = 15.0
    s = secuencia_con(clip)
    segunda = split_item(s, clip, 1.5)
    assert clip.transform.rotation == 15.0 and segunda.transform.rotation == 15.0
    assert not segunda.transform.keys


def test_los_fundidos_se_reparten():
    """En medio del corte no hay fundido: la entrada se queda en la primera."""
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, fade_in=1.0, fade_out=1.0)
    s = secuencia_con(clip)
    segunda = split_item(s, clip, 2.0)
    assert (clip.fade_in, clip.fade_out) == (1.0, 0.0)
    assert (segunda.fade_in, segunda.fade_out) == (0.0, 1.0)


def test_un_corte_nuevo_no_pide_transicion_cruzada():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, dissolve=1.0)
    s = secuencia_con(clip)
    segunda = split_item(s, clip, 2.0)
    assert clip.dissolve == 1.0         # la de la izquierda se queda
    assert segunda.dissolve == 0.0


def test_un_texto_reparte_sus_animaciones():
    titulo = Title(start=0.0, duration=4.0, text="hola",
                   anim_in="Aparecer", anim_out="Alejarse")
    s = Sequence.default()
    s.text_tracks()[0].add(titulo)
    segunda = split_item(s, titulo, 2.0)
    assert (titulo.anim_in, titulo.anim_out) == ("Aparecer", "Ninguna")
    assert (segunda.anim_in, segunda.anim_out) == ("Ninguna", "Alejarse")


def test_dividir_en_un_borde_no_hace_nada():
    clip = Clip(source="/v.mp4", start=1.0, duration=2.0)
    s = secuencia_con(clip)
    assert split_item(s, clip, 1.0) is None
    assert split_item(s, clip, 3.0) is None
    assert split_item(s, clip, 9.0) is None
    assert len(s.video_tracks()[-1].clips) == 1


def test_dividir_algo_que_no_esta_en_la_secuencia_no_hace_nada():
    assert split_item(Sequence.default(), Clip(source="/v.mp4", start=0, duration=2), 1.0) is None


# --- el historial con nombre ----------------------------------------------

def test_un_comando_entra_al_historial_con_su_nombre():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0)
    s = secuencia_con(clip)
    h = History()
    h.reset(s)

    assert run(Split(items=[clip], time=2.0), s, h)
    assert h.undo_label == "Dividir"
    assert len(s.video_tracks()[-1].clips) == 2


def test_deshacer_un_comando_regresa_el_estado():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0)
    s = secuencia_con(clip)
    h = History()
    h.reset(s)
    run(Split(items=[clip], time=2.0), s, h)

    anterior = h.undo()
    assert len(anterior.video_tracks()[-1].clips) == 1


def test_un_comando_que_no_hace_nada_no_deja_rastro():
    """Si no, deshacer tendría pasos que no deshacen nada."""
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0)
    s = secuencia_con(clip)
    h = History()
    h.reset(s)
    assert not run(Split(items=[clip], time=0.0), s, h)
    assert not h.can_undo


def test_dividir_varias_cosas_es_un_solo_paso():
    a = Clip(source="/v.mp4", start=0.0, duration=4.0)
    b = Clip(source="/v.mp4", start=0.0, duration=4.0)
    s = Sequence.default()
    s.video_tracks()[-1].add(a)
    s.audio_tracks()[0].add(b)
    h = History()
    h.reset(s)

    comando = Split(items=[a, b], time=1.0)
    assert run(comando, s, h)
    assert len(comando.created) == 2
    h.undo()
    assert not h.can_undo


def test_eliminar_con_ripple_cierra_el_hueco():
    a = Clip(source="/v.mp4", start=0.0, duration=2.0)
    b = Clip(source="/v.mp4", start=2.0, duration=3.0)
    c = Clip(source="/v.mp4", start=5.0, duration=1.0)
    s = secuencia_con(a, b, c)
    assert RippleDelete(item=b).apply(s)
    assert [x.start for x in s.video_tracks()[-1].clips] == [0.0, 2.0]


def test_eliminar_con_ripple_no_toca_otras_pistas():
    a = Clip(source="/v.mp4", start=0.0, duration=2.0)
    musica = Clip(source="/m.wav", start=4.0, duration=2.0)
    s = secuencia_con(a)
    s.audio_tracks()[0].add(musica)
    RippleDelete(item=a).apply(s)
    assert musica.start == 4.0


# --- desde la ventana: S --------------------------------------------------

def test_s_divide_en_el_playhead(ventana, media):
    ventana._place_video(media["mudo"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    ventana._seek(2.0)

    accion = ventana._actions["editar.dividir"]
    assert accion.shortcut().toString() == "S"
    accion.trigger()
    assert len(ventana.sequence.video_tracks()[-1].clips) == 2


def test_s_sin_seleccion_divide_todo_lo_que_cruza(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana.timeline.select(None)
    ventana._seek(3.0)
    ventana._actions["editar.dividir"].trigger()
    assert len(ventana.sequence.video_tracks()[-1].clips) == 2
    assert len(ventana.sequence.audio_tracks()[0].clips) == 2
    assert ventana.history.undo_label == "Cortar"


def test_s_se_apaga_al_escribir(ventana):
    accion = ventana._actions["editar.dividir"]
    ventana._focus_changed(None, ventana.text_panel._text)
    assert not accion.isEnabled()


def test_eliminar_con_ripple_desde_la_ventana_se_deshace(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._place_video(media["mudo"])
    v1 = ventana.sequence.video_tracks()[-1]
    ventana.timeline.select(v1.clips[0])
    ventana.ripple_delete()
    assert len(v1.clips) == 1 and v1.clips[0].start == 0.0
    assert ventana.history.undo_label == "Eliminar y cerrar hueco"
    ventana.undo()
    assert len(ventana.sequence.video_tracks()[-1].clips) == 2
