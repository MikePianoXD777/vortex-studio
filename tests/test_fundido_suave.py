"""Volumen y fundidos de audio muestra por muestra, sin escalones."""

import numpy as np
import pytest

from vortex_studio.media.audio import RATE, AudioRenderer, fade_envelope
from vortex_studio.model import Clip


def muestras(frames) -> np.ndarray:
    """Todo el audio en un solo arreglo mono, sea planar o empaquetado."""
    trozos = []
    for f in frames:
        datos = f.to_ndarray().astype(np.float64)
        if f.format.is_planar:
            trozos.append(datos[0])
        else:
            trozos.append(datos[0, :: len(f.layout.channels)])
    return np.concatenate(trozos)


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


# --- la envolvente --------------------------------------------------------

def test_la_envolvente_en_los_bordes():
    clip = Clip(source="/x.wav", start=2.0, duration=4.0, fade_in=1.0, fade_out=1.0)
    t = np.array([2.0, 2.5, 3.0, 4.0, 5.5, 6.0])
    assert fade_envelope(clip, t) == pytest.approx([0.0, 0.5, 1.0, 1.0, 0.5, 0.0])


def test_coincide_con_la_cuenta_del_modelo():
    """Es la misma regla que `fade_at`: si no coincidieran, la imagen y el
    sonido se fundirían distinto."""
    for fi, fo, dur in ((1.0, 0.5, 3.0), (2.0, 2.0, 1.0), (0.0, 1.5, 4.0), (0.7, 0.0, 2.0)):
        clip = Clip(source="/x.wav", start=1.0, duration=dur, fade_in=fi, fade_out=fo)
        t = np.linspace(1.0, 1.0 + dur - 1e-6, 97)
        esperado = [clip.fade_at(float(x)) for x in t]
        assert fade_envelope(clip, t) == pytest.approx(esperado, abs=1e-9)


def test_sin_fundidos_la_envolvente_es_uno():
    clip = Clip(source="/x.wav", start=0.0, duration=2.0)
    assert (fade_envelope(clip, np.linspace(0, 2, 50)) == 1.0).all()


# --- sobre el audio de verdad ---------------------------------------------

def test_el_fundido_sube_dentro_de_un_mismo_bloque(media):
    """El bug: antes cada bloque de un segundo tenía un solo nivel.

    Un fundido de 3 s eran tres escalones. Aquí se mide el primer bloque en
    ventanas de 50 ms: con escalones saldrían todas iguales.
    """
    clip = Clip(source=media["tono"], start=0.0, duration=3.0, fade_in=3.0)
    primer_bloque = next(iter(AudioRenderer([clip]).stream(0.0, 3.0)))
    x = muestras([primer_bloque])

    ventana = RATE // 20
    niveles = [rms(x[i:i + ventana]) for i in range(0, len(x) - ventana, ventana)]
    assert len(niveles) >= 15
    assert all(b > a for a, b in zip(niveles, niveles[1:])), "el fundido va en escalones"


def test_el_fundido_de_salida_llega_a_cero(media):
    clip = Clip(source=media["tono"], start=0.0, duration=3.0, fade_out=1.0)
    x = muestras(AudioRenderer([clip]).stream(0.0, 3.0))
    medio = rms(x[RATE // 2: RATE])
    final = rms(x[-RATE // 50:])
    assert final < medio * 0.05


def test_el_volumen_es_exacto(media):
    lleno = Clip(source=media["tono"], start=0.0, duration=3.0)
    medio = Clip(source=media["tono"], start=0.0, duration=3.0, gain=0.5)
    a = rms(muestras(AudioRenderer([lleno]).stream(0.0, 3.0))[RATE: 2 * RATE])
    b = rms(muestras(AudioRenderer([medio]).stream(0.0, 3.0))[RATE: 2 * RATE])
    assert b / a == pytest.approx(0.5, abs=0.01)


def test_en_s16_tambien(media):
    """La reproducción usa `s16` empaquetado; la exportación, `fltp`."""
    clip = Clip(source=media["tono"], start=0.0, duration=3.0, gain=0.5, fade_in=1.0)
    frames = list(AudioRenderer([clip], fmt="s16").stream(0.0, 3.0))
    assert all(f.format.name == "s16" for f in frames)
    assert all(f.to_ndarray().dtype == np.int16 for f in frames)
    assert sum(f.samples for f in frames) == pytest.approx(3 * RATE, abs=RATE * 0.02)

    x = muestras(frames)
    assert rms(x[: RATE // 10]) < rms(x[2 * RATE: 2 * RATE + RATE // 10]) * 0.3


def test_un_volumen_alto_en_s16_no_se_desborda(media):
    """Multiplicar enteros de 16 bits por 4 se sale del rango: tiene que
    recortar, no dar la vuelta y tronar como ruido."""
    clip = Clip(source=media["tono"], start=0.0, duration=1.0, gain=4.0)
    x = muestras(AudioRenderer([clip], fmt="s16").stream(0.0, 1.0))
    assert x.max() <= 32767 and x.min() >= -32768
    assert x.max() > 30000


def test_sin_fundido_ni_volumen_no_toca_el_bloque(media):
    """El caso común no paga ni la copia del bloque."""
    clip = Clip(source=media["tono"], start=0.0, duration=3.0)
    renderer = AudioRenderer([clip])
    bloque = next(iter(renderer._from_clip(clip, 0.0, 1.0)))
    assert renderer._apply_level(bloque, clip, 0.0) is bloque


def test_el_fundido_no_cambia_la_duracion(media):
    clip = Clip(source=media["tono"], start=0.5, duration=2.0, fade_in=0.7, fade_out=0.9)
    frames = list(AudioRenderer([clip]).stream(0.0, 3.0))
    assert sum(f.samples for f in frames) == pytest.approx(3 * RATE, abs=RATE * 0.02)
