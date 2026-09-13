"""Multicámara sincronizada por audio o por código de tiempo."""

import shutil
import subprocess

import numpy as np
import pytest

from vortex_studio.model import Clip, Sequence
from vortex_studio.model import multicam as mc

FFMPEG = shutil.which("ffmpeg")


def _ffmpeg(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture(scope="module")
def camaras(tmp_path_factory):
    """Dos cámaras del mismo ruido rosa: la B empezó a grabar 1.7 s después.

    Cada una con su propio patrón de video y color, para saber cuál se ve.
    """
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    base = tmp_path_factory.mktemp("multicam")
    ruido = base / "ruido.wav"
    _ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=8:c=pink:r=48000:seed=7", str(ruido))
    a, b = base / "camara_a.mp4", base / "camara_b.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=8", "-i", str(ruido),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            "-timecode", "10:00:00:00", str(a))
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=6", "-ss", "1.7", "-i", str(ruido),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            "-timecode", "10:00:01:21", str(b))
    return a, b


# --- sincronía --------------------------------------------------------------------------

def test_el_audio_encuentra_el_desfase(camaras):
    from vortex_studio.media.sync import audio_offset

    desfase, confianza = audio_offset(*camaras)
    assert desfase == pytest.approx(1.7, abs=0.01) and confianza > 5


def test_el_desfase_al_reves_sale_negativo(camaras):
    from vortex_studio.media.sync import audio_offset

    desfase, _ = audio_offset(camaras[1], camaras[0])
    assert desfase == pytest.approx(-1.7, abs=0.01)


def test_sin_audio_el_desfase_es_cero_y_sin_confianza(media, camaras):
    from vortex_studio.media.sync import audio_offset

    assert audio_offset(media["mudo"], camaras[0]) == (0.0, 0.0)


def test_codigo_de_tiempo_de_los_metadatos(camaras):
    from vortex_studio.media.sync import timecode_seconds

    a, b = (timecode_seconds(c) for c in camaras)
    assert a == pytest.approx(36000.0) and b - a == pytest.approx(1.7, abs=0.001)


def test_codigos_de_tiempo_raros(media):
    from vortex_studio.media.sync import parse_timecode, timecode_seconds

    assert parse_timecode("01:00:00;15", 29.97) == pytest.approx(3600.5)
    assert parse_timecode("nada", 30) is None and parse_timecode("1:2:3", 30) is None
    assert timecode_seconds(media["mudo"]) is None


# --- armar la secuencia -------------------------------------------------------------------

def _angulos():
    return [mc.Angle("a.mp4", 0.0, 8.0), mc.Angle("b.mp4", 1.7, 6.0),
            mc.Angle("c.mp4", -0.5, 5.0, has_audio=False)]


def test_una_pista_por_camara_y_nadie_antes_de_cero():
    secuencia = mc.build(_angulos(), 1920, 1080, 30)
    videos = secuencia.video_tracks()
    assert [t.name for t in videos] == ["Cámara 1", "Cámara 2", "Cámara 3"]
    assert [t.clips[0].start for t in videos] == pytest.approx([0.5, 2.2, 0.0])
    assert mc.angle_count(secuencia) == 3


def test_suena_solo_la_camara_de_referencia():
    secuencia = mc.build(_angulos(), 1920, 1080, 30)
    audios = secuencia.audio_tracks()
    assert [t.name for t in audios] == ["Audio 1", "Audio 2"]
    assert [t.muted for t in audios] == [False, True]
    assert [c.source.name for c in secuencia.audio_clips()] == ["a.mp4"]


def test_sin_camaras_la_secuencia_queda_vacia():
    assert mc.build([], 1920, 1080, 30).tracks == []
    assert mc.angle_count(None) == 0


# --- cortar entre ángulos ---------------------------------------------------------------------

def test_los_cortes_son_sostenidos():
    clip = mc.MulticamClip(source="", start=0, duration=10, sequence_id="m")
    mc.cut_to(clip, 2.0, 1)
    mc.cut_to(clip, 5.0, 2)
    assert [mc.angle_at(clip, t) for t in (0.0, 1.99, 2.0, 4.9, 5.0, 9.0)] == [0, 0, 1, 1, 2, 2]
    assert mc.cuts(clip) == [(0.0, 0), (2.0, 1), (5.0, 2)]


def test_cortar_dos_veces_en_el_mismo_lugar_reemplaza():
    clip = mc.MulticamClip(source="", start=0, duration=10, sequence_id="m", angle=2)
    mc.cut_to(clip, 3.0, 1)
    mc.cut_to(clip, 3.0, 0)
    assert mc.cuts(clip) == [(0.0, 2), (3.0, 0)]
    assert mc.angle_at(clip, 1.0) == 2


def test_el_angulo_se_limita_a_las_camaras_que_hay():
    clip = mc.MulticamClip(source="", start=0, duration=10, sequence_id="m")
    mc.cut_to(clip, 0.0, 7)
    assert mc.angle_at(clip, 1.0, count=3) == 2
    assert mc.angle_at(clip, 1.0) == 7


def test_la_vista_de_un_angulo_no_toca_la_secuencia():
    secuencia = mc.build(_angulos(), 1920, 1080, 30)
    vista = mc.angle_view(secuencia, 1)
    assert [t.enabled for t in vista.video_tracks()] == [False, True, False]
    assert all(t.enabled for t in secuencia.video_tracks())
    assert vista.video_tracks()[1].clips is secuencia.video_tracks()[1].clips


def test_guardar_y_abrir_conserva_el_clip_multicamara():
    from vortex_studio.model.serialize import item_from_dict, item_to_dict

    clip = mc.MulticamClip(source="", start=1, duration=10, sequence_id="m", angle=1)
    mc.cut_to(clip, 4.0, 2)
    otro = item_from_dict(item_to_dict(clip))
    assert isinstance(otro, mc.MulticamClip)
    assert otro.angle == 1 and otro.sequence_id == "m" and mc.cuts(otro) == mc.cuts(clip)


# --- se ve el ángulo que toca, y suena corrido ------------------------------------------------------

def _proyecto(camaras):
    from vortex_studio.model import Project
    from vortex_studio.media import probe_media

    proyecto = Project()
    angulos = [mc.Angle(c, o, probe_media(c).duration) for c, o in zip(camaras, (0.0, 1.7))]
    multi = mc.build(angulos, 160, 90, 30)
    proyecto.sequences.append(multi)
    edicion = proyecto.sequences[0]
    edicion.width, edicion.height = 160, 90
    clip = mc.MulticamClip(source="", start=0, duration=multi.duration, sequence_id=multi.id)
    edicion.track_named("V1").add(clip)
    return proyecto, edicion, clip


def test_el_render_muestra_el_angulo_de_cada_momento(camaras):
    from vortex_studio.ui.renderer import SequenceRenderer

    proyecto, edicion, clip = _proyecto(camaras)
    mc.cut_to(clip, 3.0, 1)
    render = SequenceRenderer(edicion, resolve=proyecto.sequence_by_id)
    rojo = render.compose(2.0, 160, 90).pixelColor(80, 45)
    azul = render.compose(4.0, 160, 90).pixelColor(80, 45)
    assert rojo.red() > 150 and rojo.blue() < 80
    assert azul.blue() > 150 and azul.red() < 80
    render.close()


def test_el_audio_sale_corrido_sin_importar_los_cortes(camaras):
    from vortex_studio.media.mixer import AudioMixer

    proyecto, edicion, clip = _proyecto(camaras)
    mc.cut_to(clip, 3.0, 1)
    clips = edicion.audio_clips(proyecto.sequence_by_id)
    assert [c.source.name for c in clips] == ["camara_a.mp4"]
    bloques = list(AudioMixer(clips).stream(0.0, 6.0))
    assert sum(b.samples for b in bloques) == 6 * 48000


def test_la_zona_multicamara_es_pesada(camaras):
    from vortex_studio.model import render_zones

    _, edicion, clip = _proyecto(camaras)
    assert render_zones.level_of(edicion, 0, 2) == render_zones.HEAVY


# --- ventana -------------------------------------------------------------------------------------

def test_la_ventana_crea_la_multicamara_sincronizada(ventana, camaras):
    clip = ventana.create_multicam(list(camaras), method="audio")
    assert isinstance(clip, mc.MulticamClip)
    multi = ventana.project.sequence_by_id(clip.sequence_id)
    assert [t.clips[0].start for t in multi.video_tracks()] == pytest.approx([0.0, 1.7], abs=0.02)
    assert ventana.sequence.track_named("V1").clips == [clip]


def test_la_ventana_sincroniza_por_codigo_de_tiempo(ventana, camaras):
    clip = ventana.create_multicam(list(camaras), method="timecode")
    multi = ventana.project.sequence_by_id(clip.sequence_id)
    assert multi.video_tracks()[1].clips[0].start == pytest.approx(1.7, abs=0.001)
    assert ventana.create_multicam([camaras[0]]) is None
    assert "dos" in ventana.statusBar().currentMessage()


def test_la_ventana_corta_al_angulo_en_el_playhead_y_se_ve(ventana, camaras):
    clip = ventana.create_multicam(list(camaras), method="audio")
    ventana.sequence.width, ventana.sequence.height = 160, 90
    ventana._scrubbed(4.0)
    assert ventana.switch_angle(1)
    assert mc.cuts(clip) == [(0.0, 0), (4.0, 1)]
    ventana._settle_preview()
    color = ventana.preview.current_image().pixelColor(80, 45)
    assert color.blue() > 150 and color.red() < 80
    assert not ventana.switch_angle(5)
    ventana.undo()
    assert mc.cuts(ventana.sequence.track_named("V1").clips[0]) == []
