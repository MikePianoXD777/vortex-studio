"""Remapeo de tiempo: la velocidad cambia dentro del mismo clip."""

import numpy as np
import pytest

from vortex_studio.model import Clip, Sequence, Title
from vortex_studio.model import animate
from vortex_studio.model import timeremap as tr
from vortex_studio.model.commands import SetSpeed, Split, overwrite, trim_head
from vortex_studio.model.project import Marker
from vortex_studio.model.serialize import item_from_dict, item_to_dict


def _clip(**extra):
    return Clip("a.mp4", 10.0, 4.0, in_point=2.0, **extra)


def _en_secuencia(clip):
    secuencia = Sequence.default()
    secuencia.track_named("V1").add(clip)
    return secuencia


# --- prender y apagar ---------------------------------------------------------------

def test_prender_el_remapeo_no_cambia_lo_que_se_ve():
    clip = _clip(speed=1.5)
    tiempos = (10.0, 11.0, 12.5, 13.9)
    antes = [clip.source_time(t) for t in tiempos]
    assert tr.enable(clip) and tr.is_remapped(clip)
    assert [clip.source_time(t) for t in tiempos] == pytest.approx(antes)


def test_prender_dos_veces_no_hace_nada():
    clip = _clip()
    assert tr.enable(clip)
    tr.set_speed_from(clip, 2.0, 0.5)
    llaves = tr.keys(clip)
    assert not tr.enable(clip)
    assert tr.keys(clip) == llaves


def test_apagar_regresa_a_velocidad_normal_desde_el_mismo_cuadro():
    """Quitar remapeo es volver a la normalidad, no quedarse con el promedio."""
    clip = _clip()
    tr.set_speed_from(clip, 2.0, 2.0)
    primer_cuadro = clip.source_time(10.0)
    assert tr.disable(clip)
    assert not tr.is_remapped(clip)
    assert clip.speed == pytest.approx(1.0)
    assert clip.source_time(10.0) == pytest.approx(primer_cuadro)
    assert clip.source_time(11.0) == pytest.approx(primer_cuadro + 1.0)


def test_apagar_una_reversa_tambien_regresa_a_normal():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, -1.0)
    assert tr.disable(clip)
    assert clip.speed == pytest.approx(1.0)


def test_apagar_un_clip_congelado_queda_congelado():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, 0.0)
    tr.set_speed_from(clip, 0.0, 0.0)
    assert tr.disable(clip) and clip.speed == 0.0
    assert not tr.disable(clip)


# --- velocidad desde el playhead ------------------------------------------------------

def test_velocidad_desde_aqui_no_cambia_lo_de_antes():
    clip = _clip()
    tr.set_speed_from(clip, 2.0, 0.5)
    assert clip.source_time(11.0) == pytest.approx(3.0)
    assert clip.source_time(12.0) == pytest.approx(4.0)
    assert clip.source_time(13.0) == pytest.approx(4.5)


def test_congelar_desde_aqui_deja_el_mismo_cuadro():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, 0.0)
    assert {round(clip.source_time(t), 6) for t in (11.0, 12.0, 13.5, 13.99)} == {3.0}
    assert tr.speed_at(clip, 2.0) == pytest.approx(0.0, abs=1e-6)


def test_reversa_se_detiene_en_el_primer_cuadro_del_material():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, -4.0)
    assert clip.source_time(11.1) == pytest.approx(2.6)
    assert clip.source_time(13.5) == pytest.approx(2.0)      # el punto de entrada


def test_rampas_encadenadas_tienen_su_velocidad_por_tramo():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, 2.0)
    tr.set_speed_from(clip, 3.0, 0.5)
    assert tr.speed_at(clip, 0.5) == pytest.approx(1.0)
    assert tr.speed_at(clip, 1.5) == pytest.approx(2.0)
    assert tr.speed_at(clip, 3.5) == pytest.approx(0.5)
    assert clip.source_time(14.0 - 1e-9) == pytest.approx(2.0 + 1 + 4 + 0.5)


def test_la_velocidad_tiene_tope():
    clip = _clip()
    tr.set_speed_from(clip, 0.0, 50.0)
    assert tr.speed_at(clip, 1.0) == pytest.approx(tr.MAX_SPEED)


# --- ediciones ---------------------------------------------------------------------------

def test_dividir_conserva_los_cuadros_de_las_dos_mitades():
    clip = _clip()
    secuencia = _en_secuencia(clip)
    tr.set_speed_from(clip, 1.0, 2.0)
    tiempos = (10.5, 11.5, 12.5, 13.5)
    antes = [clip.source_time(t) for t in tiempos]
    comando = Split(items=[clip], time=12.0)
    assert comando.apply(secuencia)
    segunda = comando.created[0]
    despues = [(clip if t < 12.0 else segunda).source_time(t) for t in tiempos]
    assert despues == pytest.approx(antes)
    assert tr.speed_at(segunda, 0.5) == pytest.approx(2.0)


def test_pisar_la_cabeza_conserva_los_cuadros_de_lo_que_queda():
    clip = _clip()
    secuencia = _en_secuencia(clip)
    tr.set_speed_from(clip, 0.5, 3.0)
    tiempos = (11.5, 12.5, 13.9)
    antes = [clip.source_time(t) for t in tiempos]
    pista = secuencia.track_named("V1")
    nuevo = Clip("b.mp4", 9.0, 2.0)
    overwrite(pista, nuevo)
    pista.add(nuevo)
    assert clip.start == pytest.approx(11.0)
    assert [clip.source_time(t) for t in tiempos] == pytest.approx(antes)


def test_pisar_en_medio_deja_la_cola_con_sus_cuadros():
    clip = _clip()
    secuencia = _en_secuencia(clip)
    tr.set_speed_from(clip, 1.0, 0.25)
    pista = secuencia.track_named("V1")
    antes = [clip.source_time(t) for t in (12.5, 13.5)]
    nuevo = Clip("b.mp4", 11.0, 1.0)
    overwrite(pista, nuevo)
    pista.add(nuevo)
    cola = pista.clips[-1]
    assert cola.start == pytest.approx(12.0)
    assert [cola.source_time(t) for t in (12.5, 13.5)] == pytest.approx(antes)


def test_una_velocidad_fija_reemplaza_al_remapeo():
    clip = _clip()
    secuencia = _en_secuencia(clip)
    tr.set_speed_from(clip, 1.0, 2.0)
    assert SetSpeed(clip=clip, speed=0.5).apply(secuencia)
    assert not tr.is_remapped(clip) and clip.speed == 0.5


# --- recortar la cabeza sin despegar la animación ----------------------------------------

def test_recortar_la_cabeza_recorre_los_keyframes():
    clip = _clip()
    clip.transform.set_key("x", 2.0, 0.5)
    clip.transform.set_key("x", 3.0, 1.0)
    clip.anim["gain"] = [[1.0, 0.0], [3.0, 2.0]]
    antes = (clip.transform.at("x", 12.5 - clip.start), animate.value_at(clip, "gain", 2.0))
    trim_head(clip, 1.0)
    assert (clip.start, clip.duration, clip.in_point) == (11.0, 3.0, 3.0)
    assert clip.transform.at("x", 12.5 - clip.start) == pytest.approx(antes[0])
    assert animate.value_at(clip, "gain", 1.0) == pytest.approx(antes[1])


def test_recortar_la_cabeza_recorre_los_marcadores_y_tira_los_que_quedan_fuera():
    clip = _clip()
    clip.markers = [Marker(0.5, "fuera"), Marker(2.0, "dentro")]
    trim_head(clip, 1.0)
    assert [(m.name, m.time) for m in clip.markers] == [("dentro", 1.0)]


def test_alargar_la_cabeza_regresa_material_y_keyframes():
    clip = _clip(speed=2.0)
    clip.transform.set_key("x", 1.0, 0.3)
    trim_head(clip, -0.5)
    assert (clip.start, clip.duration, clip.in_point) == (9.5, 4.5, 1.0)
    assert clip.transform.keys["x"][0][0] == pytest.approx(1.5)


def test_recortar_la_cabeza_de_un_texto_recorre_su_animacion():
    titulo = Title(start=0.0, duration=4.0)
    titulo.anim["x"] = [[1.0, 0.2], [2.0, 0.8]]
    trim_head(titulo, 0.5)
    assert titulo.anim["x"] == [[0.5, 0.2], [1.5, 0.8]]


# --- editor de keyframes, guardado y audio ----------------------------------------------------

def test_el_editor_de_keyframes_ofrece_el_tiempo_solo_a_clips():
    rutas = [p.path for p in animate.params_for(_clip())]
    assert "time" in rutas
    assert "time" not in [p.path for p in animate.params_for(Title(0, 2))]
    assert animate.value_at(_clip(speed=0.5), "time", 2.0) == pytest.approx(1.0)


def test_pintar_los_paneles_no_toca_el_tiempo():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, 2.0)
    llaves = tr.keys(clip)
    animate.bake(clip, 1.5)
    assert animate.absorb(clip, 1.5) == []
    assert tr.keys(clip) == llaves
    assert not hasattr(animate.view(clip, 1.5), "time")


def test_guardar_y_abrir_conserva_el_remapeo():
    clip = _clip()
    tr.set_speed_from(clip, 1.0, 2.0)
    tr.set_speed_from(clip, 2.5, 0.0)
    otro = item_from_dict(item_to_dict(clip))
    tiempos = np.linspace(10.0, 13.99, 9)
    assert [otro.source_time(t) for t in tiempos] == pytest.approx(
        [clip.source_time(t) for t in tiempos])


def test_el_audio_de_un_clip_remapeado_va_mudo(media):
    from vortex_studio.media.mixer import AudioMixer

    clip = Clip(media["sonoro"], 0.0, 2.0)
    tr.set_speed_from(clip, 0.5, 2.0)
    bloques = list(AudioMixer([clip]).stream(0.0, 2.0))
    assert sum(b.samples for b in bloques) == 96000
    assert max(float(np.abs(b.to_ndarray()).max()) for b in bloques) < 1e-6


def test_el_render_muestra_el_cuadro_del_remapeo(media):
    from vortex_studio.media.decoder import VideoSource
    from vortex_studio.ui.renderer import SequenceRenderer

    clip = Clip(media["mudo"], 0.0, 2.0)
    secuencia = _en_secuencia(clip)
    tr.set_speed_from(clip, 0.0, 2.0)
    render = SequenceRenderer(secuencia)
    with VideoSource(media["mudo"]) as fuente:
        esperado = fuente.frame_at(3.0).data
    assert render.frame_of(clip, 1.5).data == esperado
    render.close()


def test_la_zona_con_remapeo_se_marca_pesada():
    from vortex_studio.model import render_zones

    clip = _clip()
    secuencia = _en_secuencia(clip)
    assert render_zones.level_of(secuencia, 10.0, 14.0) == render_zones.NONE
    tr.enable(clip)
    assert render_zones.level_of(secuencia, 10.0, 14.0) == render_zones.HEAVY


# --- ventana ----------------------------------------------------------------------------------

def _con_video(ventana, media):
    ventana.place_media(media["sonoro"])
    video = ventana.sequence.track_named("V1").clips[0]
    audio = ventana.sequence.track_named("A1").clips[0]
    return video, audio


def test_el_menu_remapea_el_clip_y_su_audio_desde_el_playhead(ventana, media):
    video, audio = _con_video(ventana, media)
    ventana._scrubbed(2.0)
    assert ventana.remap_speed_from_playhead(0.5)
    assert tr.speed_at(video, 3.0) == pytest.approx(0.5)
    assert tr.is_remapped(audio)
    assert video.source_time(1.0) == pytest.approx(1.0)
    assert "mudo" in ventana.statusBar().currentMessage()


def test_remapear_fuera_del_clip_o_bloqueado_no_hace_nada(ventana, media):
    video, _ = _con_video(ventana, media)
    ventana.timeline.select(video)
    ventana._scrubbed(ventana.sequence.duration)
    assert not ventana.remap_speed_from_playhead(2.0)
    ventana._scrubbed(1.0)
    ventana.sequence.track_named("V1").locked = True
    assert not ventana.remap_speed_from_playhead(2.0)
    assert not tr.is_remapped(video)


def test_quitar_el_remapeo_y_deshacer(ventana, media):
    video, audio = _con_video(ventana, media)
    ventana._scrubbed(1.0)
    ventana.remap_speed_from_playhead(0.0)
    assert ventana.remove_time_remap()
    assert not tr.is_remapped(video) and not tr.is_remapped(audio)
    assert not ventana.remove_time_remap()
    ventana.undo()
    assert tr.is_remapped(ventana.sequence.track_named("V1").clips[0])
