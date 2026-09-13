"""Ecualizador, compresor, normalización LUFS y ducking."""

import shutil
import subprocess

import av
import numpy as np
import pytest

from vortex_studio.media.audio import RATE, AudioRenderer
from vortex_studio.media.loudness import gain_for, integrated, loudness_of
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip, Sequence
from vortex_studio.model.audio_fx import DUCKED, VOICE, AudioFx

FFMPEG = shutil.which("ffmpeg")


def generar(tmp, nombre, expresion, segundos=3):
    ruta = tmp / nombre
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='{expresion}':d={segundos}:s=48000", "-ac", "2", str(ruta)],
                   check=True)
    return ruta


@pytest.fixture(scope="module")
def sonidos(tmp_path_factory):
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    tmp = tmp_path_factory.mktemp("fx")
    return {
        "grave": generar(tmp, "grave.wav", "0.2*sin(2*PI*100*t)"),
        "agudo": generar(tmp, "agudo.wav", "0.2*sin(2*PI*8000*t)"),
        "fuerte": generar(tmp, "fuerte.wav", "0.9*sin(2*PI*440*t)"),
        "suave": generar(tmp, "suave.wav", "0.05*sin(2*PI*440*t)"),
        "medio": generar(tmp, "medio.wav", "0.1*sin(2*PI*440*t)"),
        "voz": generar(tmp, "voz.wav", "if(between(t,1,2),0.3*sin(2*PI*300*t),0)", 4),
        "musica": generar(tmp, "musica.wav", "0.2*sin(2*PI*660*t)", 4),
    }


def datos(frames):
    return np.concatenate([f.to_ndarray()[0] for f in frames])


def nivel(arr, a=0.0, b=None):
    tramo = arr[int(a * RATE):int(b * RATE) if b else None]
    return float(np.sqrt(np.mean(tramo.astype(np.float64) ** 2)))


def render(ruta, fx=None, segundos=3.0):
    clip = Clip(source=ruta, start=0.0, duration=segundos)
    if fx:
        clip.audio_fx = fx
    return datos(list(AudioRenderer([clip]).stream(0.0, segundos)))


# --- ecualizador ----------------------------------------------------------

def test_subir_graves_sube_un_tono_grave(sonidos):
    plano = nivel(render(sonidos["grave"]), 0.5)
    arriba = nivel(render(sonidos["grave"], AudioFx(low=9.0)), 0.5)
    assert arriba > plano * 2.0


def test_bajar_agudos_baja_un_tono_agudo_y_no_toca_el_grave(sonidos):
    assert nivel(render(sonidos["agudo"], AudioFx(high=-12.0)), 0.5) < \
        nivel(render(sonidos["agudo"]), 0.5) * 0.4
    assert nivel(render(sonidos["grave"], AudioFx(high=-12.0)), 0.5) == \
        pytest.approx(nivel(render(sonidos["grave"]), 0.5), rel=0.1)


def test_los_efectos_no_cambian_la_duracion(sonidos):
    arr = render(sonidos["grave"], AudioFx(low=6, mid=-3, high=2, compressor=True))
    assert len(arr) == 3 * RATE


# --- compresor -----------------------------------------------------------

def test_el_compresor_baja_lo_fuerte(sonidos):
    sin = nivel(render(sonidos["fuerte"]), 0.5)
    con = nivel(render(sonidos["fuerte"], AudioFx(compressor=True, threshold=-30, ratio=8)), 0.5)
    assert con < sin * 0.5


def test_el_compresor_no_toca_lo_que_queda_bajo_el_umbral(sonidos):
    sin = nivel(render(sonidos["suave"]), 0.5)
    con = nivel(render(sonidos["suave"], AudioFx(compressor=True, threshold=-6, ratio=8)), 0.5)
    assert con == pytest.approx(sin, rel=0.1)


def test_la_ganancia_de_compensacion_sube(sonidos):
    base = AudioFx(compressor=True, threshold=-30, ratio=4)
    compensado = AudioFx(compressor=True, threshold=-30, ratio=4, makeup=6)
    assert nivel(render(sonidos["fuerte"], compensado), 0.5) > \
        nivel(render(sonidos["fuerte"], base), 0.5) * 1.7


# --- sonoridad -----------------------------------------------------------

def test_lufs_de_tonos_conocidos():
    for amplitud, esperado in ((1.0, 0.0), (0.1, -20.0)):
        t = np.arange(3 * RATE) / RATE
        x = (amplitud * np.sin(2 * np.pi * 997 * t)).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(np.vstack([x, x]), format="fltp", layout="stereo")
        frame.sample_rate = RATE
        assert integrated([frame]) == pytest.approx(esperado, abs=0.2)


def test_el_silencio_no_tiene_sonoridad_y_no_cambia_la_ganancia():
    assert loudness_of(np.zeros((2, RATE))) == float("-inf")
    assert gain_for(float("-inf"), -14) == 1.0
    assert gain_for(-20.0, -14.0) == pytest.approx(10 ** (6 / 20))
    assert gain_for(-40.0, -14.0) == 4.0                    # el tope: no se sube a lo loco


def test_normalizar_desde_la_ventana(ventana, sonidos):
    # 0.1 de amplitud en mono, subido a estéreo con −3 dB por canal: unos
    # −23 LUFS. Cabe en el tope de 4× (+12 dB) para llegar a −14.
    ventana._place_audio(sonidos["medio"])
    clip = ventana.sequence.audio_tracks()[0].clips[0]
    medidas = ventana.normalize_loudness(-14.0)
    assert medidas[id(clip)] == pytest.approx(-23.0, abs=1.0)
    prueba = Clip(source=clip.source, start=0, duration=clip.duration, gain=clip.gain)
    final = integrated(AudioRenderer([prueba]).stream(0.0, clip.duration))
    assert final == pytest.approx(-14.0, abs=0.6)
    assert ventana.history.undo_label == "Normalizar a -14 LUFS"


# --- ducking --------------------------------------------------------------

def mezcla(sonidos, con_ducking):
    voz = Clip(source=sonidos["voz"], start=0.0, duration=4.0)
    musica = Clip(source=sonidos["musica"], start=0.0, duration=4.0)
    opciones = {"voices": {id(voz)}, "ducked": {id(musica)}, "depth": 12.0} if con_ducking else {}
    return voz, musica, datos(list(AudioMixer([voz, musica], **opciones).stream(0.0, 4.0)))


def musica_sola(arr, a, b):
    """El nivel de la música en un tramo: se filtra la voz de 300 Hz midiendo 660 Hz."""
    tramo = arr[int(a * RATE):int(b * RATE)].astype(np.float64)
    espectro = np.abs(np.fft.rfft(tramo * np.hanning(len(tramo))))
    frec = np.fft.rfftfreq(len(tramo), 1 / RATE)
    return float(espectro[(frec > 640) & (frec < 680)].max())


# Ventanas del mismo largo: la magnitud de la FFT crece con la ventana, y mi
# primera versión comparaba 0.6 s contra 0.8 s.
def test_la_musica_se_agacha_mientras_habla_la_voz(sonidos):
    _, _, arr = mezcla(sonidos, True)
    antes = musica_sola(arr, 0.2, 0.7)
    durante = musica_sola(arr, 1.3, 1.8)
    assert durante < antes * 0.4          # −12 dB son un cuarto


def test_la_musica_vuelve_cuando_la_voz_calla(sonidos):
    _, _, arr = mezcla(sonidos, True)
    assert musica_sola(arr, 3.2, 3.7) == pytest.approx(musica_sola(arr, 0.2, 0.7), rel=0.15)


def test_sin_ducking_la_musica_no_se_mueve(sonidos):
    _, _, arr = mezcla(sonidos, False)
    assert musica_sola(arr, 1.3, 1.8) == pytest.approx(musica_sola(arr, 0.2, 0.7), rel=0.15)


def test_el_papel_de_la_pista_arma_las_opciones():
    seq = Sequence.default()
    a1, a2, _ = seq.audio_tracks()
    voz = a1.add(Clip("/tmp/v.wav", 0.0, 2.0))
    musica = a2.add(Clip("/tmp/m.wav", 0.0, 2.0))
    a1.role, a2.role = VOICE, DUCKED
    opciones = seq.audio_mix_options()
    assert opciones["voices"] == {id(voz)} and opciones["ducked"] == {id(musica)}
    a1.muted = True
    assert seq.audio_mix_options()["voices"] == set()


def test_se_guarda_todo(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    a1 = proyecto.active.audio_tracks()[0]
    clip = a1.add(Clip("/tmp/v.wav", 0.0, 2.0))
    clip.audio_fx = AudioFx(low=3.5, compressor=True, ratio=6.0)
    a1.role = VOICE
    proyecto.active.duck_depth = 18.0
    leido = load_project(save_project(proyecto, tmp_path / "p")).active
    fx = leido.audio_tracks()[0].clips[0].audio_fx
    assert (fx.low, fx.compressor, fx.ratio) == (3.5, True, 6.0)
    assert leido.audio_tracks()[0].role == VOICE and leido.duck_depth == 18.0


def test_el_panel_de_audio(ventana, sonidos):
    ventana._place_audio(sonidos["grave"])
    clip = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(clip)
    panel = ventana.audio_panel
    panel.low._slider.setValue(60)
    assert clip.audio_fx.low == pytest.approx(6.0)
    assert not panel.threshold.isEnabled()
    panel.compressor.setChecked(True)
    assert clip.audio_fx.compressor and panel.threshold.isEnabled()
    panel.role.setCurrentText(VOICE)
    assert ventana.sequence.audio_tracks()[0].role == VOICE
    assert ventana.history.undo_label == "A1: voz"
