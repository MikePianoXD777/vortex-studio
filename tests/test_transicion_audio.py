"""El audio enlazado sigue a la transición de su video.

Antes, en una transición de video el sonido cortaba seco en el corte: la
imagen se cruzaba y el audio brincaba de un clip al otro.
"""

import numpy as np
import pytest

from vortex_studio.media.audio import RATE, transition_envelope
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip
from vortex_studio.model.project import CROSS, DIP_BLACK


def muestras(frames) -> np.ndarray:
    trozos = []
    for f in frames:
        datos = f.to_ndarray().astype(np.float64)
        trozos.append(datos[0] if f.format.is_planar else datos[0, :: len(f.layout.channels)])
    return np.concatenate(trozos)


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def cortado(ventana, media, segundos=1.0, tipo=CROSS):
    """Un video con sonido partido a la mitad, con transición en el corte."""
    ventana._place_video(media["sonoro"])
    ventana._seek(3.0)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    ventana.cut_at_playhead()
    _, segundo = ventana.sequence.video_tracks()[-1].clips
    ventana.timeline.select(segundo)
    ventana.set_dissolve(segundos, tipo)
    return segundo


def audio_de(ventana):
    return sorted(ventana._audio_clips(), key=lambda c: c.start)


def test_el_corte_tiene_audio_enlazado(ventana, media):
    cortado(ventana, media)
    a1 = ventana.sequence.audio_tracks()[0]
    assert len(a1.clips) == 2 and all(c.link for c in a1.clips)


def test_en_la_cruzada_los_audios_se_enciman(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    corte = segundo.start
    sale, entra = audio_de(ventana)

    assert sale.end == pytest.approx(corte + 0.5)
    assert entra.start == pytest.approx(corte - 0.5)
    # El que entra toma material de antes de su punto de entrada.
    assert entra.in_point == pytest.approx(corte - 0.5, abs=1e-6)


def test_los_clips_del_timeline_no_se_tocan(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    a1 = ventana.sequence.audio_tracks()[0]
    antes = [(c.start, c.duration, c.in_point) for c in a1.clips]
    ventana._audio_clips()
    assert [(c.start, c.duration, c.in_point) for c in a1.clips] == antes
    assert a1.clips[0].end == pytest.approx(segundo.start)


def test_las_curvas_son_de_potencia_constante(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    sale, entra = audio_de(ventana)
    t = np.linspace(segundo.start - 0.5, segundo.start + 0.5, 41)
    energia = transition_envelope(sale, t) ** 2 + transition_envelope(entra, t) ** 2
    assert energia == pytest.approx(np.ones_like(t), abs=1e-9)
    # En el corte, cada uno a −3 dB.
    medio = np.array([segundo.start])
    assert transition_envelope(sale, medio)[0] == pytest.approx(np.sqrt(0.5))


def test_a_negro_el_audio_pasa_por_silencio(ventana, media):
    segundo = cortado(ventana, media, 1.0, DIP_BLACK)
    corte = segundo.start
    sale, entra = audio_de(ventana)
    # No se enciman: cada uno se apaga o se enciende en su mitad.
    assert sale.end == pytest.approx(corte) and entra.start == pytest.approx(corte)

    arr = muestras(AudioMixer(ventana._audio_clips()).stream(0.0, 6.0))
    en_el_corte = rms(arr[int((corte - 0.02) * RATE):int((corte + 0.02) * RATE)])
    normal = rms(arr[int(1.0 * RATE):int(1.5 * RATE)])
    assert en_el_corte < normal * 0.1


def test_la_cruzada_no_se_hunde_en_el_corte(ventana, media):
    segundo = cortado(ventana, media, 1.0)
    corte = segundo.start
    arr = muestras(AudioMixer(ventana._audio_clips()).stream(0.0, 6.0))
    normal = rms(arr[int(1.0 * RATE):int(1.5 * RATE)])
    for t in (corte - 0.3, corte, corte + 0.3):
        tramo = rms(arr[int((t - 0.05) * RATE):int((t + 0.05) * RATE)])
        assert tramo > normal * 0.7


def test_sin_material_antes_el_cruce_empieza_donde_puede(secuencia):
    """Si el que entra arranca en el segundo 0.2 del archivo, solo hay 0.2 s
    para encimar: no se inventa material de antes del principio."""
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    v_a = v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v_b = v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=0.2, link="b"))
    a1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    a1.add(Clip("/b.mp4", 3.0, 3.0, in_point=0.2, link="b"))
    v_b.dissolve = 1.0

    sale, entra = sorted(secuencia.audio_clips(), key=lambda c: c.start)
    assert entra.start == pytest.approx(2.8)
    assert entra.in_point == pytest.approx(0.0)
    assert sale.end == pytest.approx(3.5)
    assert v_a.end == pytest.approx(3.0)


def test_audio_suelto_no_se_toca(secuencia):
    """Si el audio no está enlazado al video, no sabemos que van juntos."""
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b")).dissolve = 1.0
    sueltos = [a1.add(Clip("/m.wav", 0.0, 3.0)), a1.add(Clip("/m.wav", 3.0, 3.0))]
    assert secuencia.audio_clips() == sueltos


def test_el_ducking_reconoce_las_copias(secuencia):
    v1, a1 = secuencia.video_tracks()[-1], secuencia.audio_tracks()[0]
    a1.role = "Voz"
    v1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    v1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b")).dissolve = 1.0
    a1.add(Clip("/a.mp4", 0.0, 3.0, link="a"))
    a1.add(Clip("/b.mp4", 3.0, 3.0, in_point=1.0, link="b"))
    voces = secuencia.audio_mix_options()["voices"]
    assert {c.uid for c in secuencia.audio_clips()} == voces
