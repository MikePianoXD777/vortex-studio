"""El audio de un clip a otra velocidad: que dure lo que la imagen y suene bien.

Antes el archivo se leía siempre a velocidad normal: un clip a 2× sonaba el
doble de largo que su imagen y todo lo que venía detrás en la pista se
desfasaba.
"""

import shutil
import subprocess

import numpy as np
import pytest

from vortex_studio.media.audio import RATE, AudioRenderer
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip
from vortex_studio.model.project import KEEP_PITCH, MUTE_AUDIO, SHIFT_PITCH

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def escalon(tmp_path_factory):
    """Cuatro segundos: 440 Hz los dos primeros y 880 Hz los dos últimos."""
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("vel") / "escalon.wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "aevalsrc='0.5*sin(2*PI*if(lt(t,2),440,880)*t)':d=4:s=48000",
                    "-ac", "2", str(ruta)], check=True)
    return ruta


def muestras(frames):
    return np.concatenate([f.to_ndarray()[0] for f in frames]) if frames else np.zeros(0)


def frecuencia(datos):
    tramo = datos[len(datos) // 8: len(datos) * 7 // 8]
    espectro = np.abs(np.fft.rfft(tramo * np.hanning(len(tramo))))
    return np.argmax(espectro) * RATE / len(tramo)


@pytest.mark.parametrize("velocidad", [0.25, 0.5, 2.0, 4.0])
def test_mantener_tono_dura_lo_que_la_imagen(media, velocidad):
    clip = Clip(source=media["tono"], start=0.0, duration=0.7, speed=velocidad)
    datos = muestras(list(AudioRenderer([clip]).stream(0.0, 0.7)))
    assert len(datos) == round(0.7 * RATE)
    assert abs(frecuencia(datos) - 330) < 8, "el tono no se tenía que mover"
    assert np.abs(datos).mean() > 0.05, "salió mudo"


@pytest.mark.parametrize("velocidad", [0.5, 2.0])
def test_cambiar_tono_sube_con_la_velocidad(media, velocidad):
    clip = Clip(source=media["tono"], start=0.0, duration=0.7, speed=velocidad,
                audio_mode=SHIFT_PITCH)
    datos = muestras(list(AudioRenderer([clip]).stream(0.0, 0.7)))
    assert len(datos) == round(0.7 * RATE)
    assert abs(frecuencia(datos) - 330 * velocidad) < 10


def test_silenciar_da_silencio_del_mismo_largo(media):
    clip = Clip(source=media["tono"], start=0.0, duration=1.0, speed=2.0,
                audio_mode=MUTE_AUDIO)
    datos = muestras(list(AudioRenderer([clip]).stream(0.0, 1.0)))
    assert len(datos) == RATE
    assert np.abs(datos).max() == 0


def test_congelado_no_suena(media):
    clip = Clip(source=media["tono"], start=0.0, duration=1.0, speed=0.0)
    datos = muestras(list(AudioRenderer([clip]).stream(0.0, 1.0)))
    assert len(datos) == RATE and np.abs(datos).max() == 0


def test_empezar_a_media_lectura_respeta_la_velocidad(escalon):
    """El bug: a la mitad de un clip a 2×, el audio se leía desde el segundo 1
    del archivo (440 Hz) y no desde el 2 (880 Hz)."""
    clip = Clip(source=escalon, start=0.0, duration=2.0, speed=2.0)
    datos = muestras(list(AudioRenderer([clip]).stream(1.1, 1.9)))
    assert abs(frecuencia(datos) - 880) < 15


def test_lo_que_sigue_no_se_desfasa(escalon, media):
    """Un clip acelerado seguido de otro: el segundo empieza donde debe."""
    rapido = Clip(source=escalon, start=0.0, duration=1.0, speed=2.0, in_point=0.0)
    despues = Clip(source=media["tono"], start=1.0, duration=1.0)
    datos = muestras(list(AudioRenderer([rapido, despues]).stream(0.0, 2.0)))
    assert len(datos) == 2 * RATE
    assert abs(frecuencia(datos[:RATE]) - 440) < 10
    assert abs(frecuencia(datos[RATE:]) - 330) < 10


def test_la_mezcla_tambien_respeta_la_velocidad(media):
    a = Clip(source=media["tono"], start=0.0, duration=1.0, speed=2.0)
    b = Clip(source=media["tono"], start=0.0, duration=1.0, speed=0.5, audio_mode=KEEP_PITCH)
    datos = muestras(list(AudioMixer([a, b]).stream(0.0, 1.0)))
    assert len(datos) == RATE
    assert abs(frecuencia(datos) - 330) < 8


def test_el_rango_de_velocidad_es_de_025_a_4():
    c = Clip(source="/tmp/a.mp4", start=0.0, duration=4.0)
    c.retime(10.0)
    assert c.speed == 4.0
    c.retime(0.01)
    assert c.speed == 0.25


def test_en_la_ventana_el_audio_enlazado_cambia_junto(ventana, media):
    ventana._place_video(media["sonoro"])
    video = ventana.sequence.video_tracks()[-1].clips[0]
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(video)
    ventana.set_clip_speed(2.0)
    assert video.speed == audio.speed == 2.0
    assert video.duration == pytest.approx(audio.duration) == pytest.approx(3.0)
    assert ventana.history.undo_label == "Velocidad 2×"


def test_modo_de_audio_desde_el_panel_y_el_menu(ventana, media):
    ventana._place_video(media["sonoro"])
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(audio)
    ventana.set_audio_mode(SHIFT_PITCH)
    assert all(c.audio_mode == SHIFT_PITCH
               for c in ventana.sequence.with_linked([audio]))

    ventana.clip_panel._audio_mode.setCurrentText(MUTE_AUDIO)
    assert audio.audio_mode == MUTE_AUDIO
    assert ventana.sequence.audio_clips() == []
    ventana.undo()
    assert ventana.sequence.audio_tracks()[0].clips[0].audio_mode == SHIFT_PITCH


def test_el_modo_se_guarda(tmp_path, media):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    proyecto.active.audio_tracks()[0].add(
        Clip(source=media["tono"], start=0.0, duration=1.0, speed=0.5, audio_mode=SHIFT_PITCH))
    clip = load_project(save_project(proyecto, tmp_path / "p")).active.audio_tracks()[0].clips[0]
    assert (clip.speed, clip.audio_mode) == (0.5, SHIFT_PITCH)
