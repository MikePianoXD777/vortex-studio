"""Lectura de audio: onda y mezcla para exportar."""

import struct

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
