"""Lectura de audio: onda y mezcla para exportar."""

import struct

import pytest

from vortex_studio.media.audio import RATE, AudioRenderer, has_audio, peaks
from vortex_studio.model import Clip


def energia(frames, desde, hasta):
    """Nivel medio del audio entre dos segundos de la línea de tiempo."""
    pos, total, n = 0.0, 0.0, 0
    for frame in frames:
        dur = frame.samples / RATE
        if pos + dur > desde and pos < hasta:
            crudo = bytes(frame.planes[0])[: frame.samples * 4]
            valores = struct.unpack(f"<{len(crudo) // 4}f", crudo)
            total += sum(abs(v) for v in valores)
            n += len(valores)
        pos += dur
    return total / max(1, n)


def test_detecta_si_hay_audio(media):
    assert has_audio(media["sonoro"])
    assert not has_audio(media["mudo"])
    assert not has_audio("/no/existe.mp4")


def test_onda(media):
    p = peaks(media["sonoro"], per_second=40)
    assert len(p) > 100
    assert all(0 <= v <= 1 for v in p)
    assert max(p) > 0.4          # el tono de prueba es fuerte


def test_un_video_mudo_no_tiene_onda(media):
    assert peaks(media["mudo"]) == []


def test_la_duracion_de_salida_es_exacta(media):
    clip = Clip(source=media["sonoro"], start=0.0, duration=6.0)
    total = sum(f.samples for f in AudioRenderer([clip]).stream(0.0, 4.0))
    assert abs(total - 4 * RATE) < RATE * 0.02


def test_los_huecos_se_rellenan_con_silencio(media):
    """Sin relleno el audio se recorre y pierde la sincronía con la imagen."""
    clip = Clip(source=media["sonoro"], start=2.0, duration=3.0)
    frames = list(AudioRenderer([clip]).stream(0.0, 6.0))

    assert abs(sum(f.samples for f in frames) - 6 * RATE) < RATE * 0.05
    assert energia(frames, 0.2, 1.5) < 0.001      # el hueco va mudo
    assert energia(frames, 3.0, 4.5) > 0.2        # el clip sí suena


def test_un_clip_sin_audio_aporta_silencio(media):
    clip = Clip(source=media["mudo"], start=0.0, duration=2.0)
    frames = list(AudioRenderer([clip]).stream(0.0, 2.0))
    assert abs(sum(f.samples for f in frames) - 2 * RATE) < RATE * 0.02


def test_un_archivo_inexistente_no_truena(media):
    clip = Clip(source="/no/existe.mp4", start=0.0, duration=1.0)
    frames = list(AudioRenderer([clip]).stream(0.0, 1.0))
    assert abs(sum(f.samples for f in frames) - RATE) < RATE * 0.05


# --- volumen y fundidos ---------------------------------------------------

def render(media, **kw):
    from vortex_studio.media.audio import AudioRenderer
    clip = Clip(source=media["sonoro"], start=0.0, duration=6.0, **kw)
    return list(AudioRenderer([clip]).stream(0.0, 6.0))


def test_el_volumen_del_clip_se_aplica(media):
    normal = energia(render(media), 1.0, 5.0)
    bajo = energia(render(media, gain=0.25), 1.0, 5.0)
    assert 0.15 * normal < bajo < 0.35 * normal


def test_volumen_cero_es_silencio(media):
    assert energia(render(media, gain=0.0), 1.0, 5.0) < 0.001


def test_el_fundido_de_audio_baja_el_inicio(media):
    frames = render(media, fade_in=3.0)
    assert energia(frames, 0.0, 1.0) < energia(frames, 4.0, 5.5) * 0.4


def test_el_volumen_no_cambia_la_duracion(media):
    frames = render(media, gain=0.3, fade_in=2.0, fade_out=2.0)
    assert abs(sum(f.samples for f in frames) - 6 * RATE) < RATE * 0.05


# --- el final del archivo -------------------------------------------------

@pytest.mark.parametrize("formato", ["fltp", "s16"])
def test_el_final_del_archivo_no_se_pierde(media, formato):
    """El bug: un clip que llegaba al final de su archivo perdía hasta un
    segundo del cierre, cambiado por silencio. El FIFO solo soltaba bloques
    completos de un segundo y el pedazo sobrante nunca se leía."""
    import numpy as np

    clip = Clip(source=media["tono"], start=0.0, duration=3.0)
    frames = list(AudioRenderer([clip], fmt=formato).stream(0.0, 3.0))
    datos = np.concatenate([
        (f.to_ndarray()[0] if f.format.is_planar
         else f.to_ndarray()[0, ::len(f.layout.channels)]).astype(np.float64)
        for f in frames])

    def nivel(desde, hasta):
        tramo = datos[int(desde * RATE):int(hasta * RATE)]
        return float(np.sqrt(np.mean(tramo * tramo)))

    assert nivel(2.2, 2.9) > nivel(0.5, 1.5) * 0.8, "el último segundo salió en silencio"


def test_el_final_del_archivo_llega_en_la_mezcla(media):
    """La mezcla usa el mismo renderizador: tiene que heredar el arreglo."""
    from vortex_studio.media.mixer import AudioMixer

    clip = Clip(source=media["tono"], start=0.0, duration=3.0)
    frames = list(AudioMixer([clip, Clip(source=media["tono"], start=0.0, duration=3.0)])
                  .stream(0.0, 3.0))
    assert energia(frames, 2.2, 2.9) > energia(frames, 0.5, 1.5) * 0.8


def test_pedir_mas_audio_del_que_hay_rellena_con_silencio(media):
    """El arreglo no puede inventar audio: más allá del archivo, silencio."""
    clip = Clip(source=media["tono"], start=0.0, duration=5.0)
    frames = list(AudioRenderer([clip]).stream(0.0, 5.0))
    assert abs(sum(f.samples for f in frames) - 5 * RATE) < RATE * 0.02
    assert energia(frames, 3.3, 4.8) < 0.001
