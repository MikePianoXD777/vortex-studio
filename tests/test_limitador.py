"""El limitador de la mezcla: nada pasa del tope y nada se retrasa."""

import numpy as np
import pytest

from vortex_studio.media.audio import RATE
from vortex_studio.media.limiter import CEILING, PeakLimiter
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip


def seno(amplitud, segundos=1.0, hz=220.0):
    t = np.arange(int(segundos * RATE)) / RATE
    uno = (amplitud * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.vstack([uno, uno])


def test_por_debajo_del_tope_no_toca_nada():
    datos = seno(0.5)
    salida = PeakLimiter(RATE).process(datos)
    assert salida is datos


def test_nada_pasa_del_tope():
    salida = PeakLimiter(RATE).process(seno(2.0))
    assert np.max(np.abs(salida)) <= CEILING + 1e-6


def test_no_retrasa_el_sonido():
    """Sin mirar adelante: el golpe sale en la misma muestra en que entra."""
    datos = np.zeros((2, RATE), dtype=np.float32)
    datos[:, 12345] = 3.0
    datos[:, 30000] = 0.4
    salida = PeakLimiter(RATE).process(datos)
    assert int(np.argmax(np.abs(salida[0]))) == 12345
    assert salida[0, 30000] == pytest.approx(0.4, abs=1e-6)     # ya se recuperó


def test_la_ganancia_regresa_despues_del_golpe():
    limitador = PeakLimiter(RATE)
    golpe = seno(2.0, 0.2)
    calma = seno(0.5, 1.0)
    limitador.process(golpe)
    salida = limitador.process(calma)
    # Medio segundo después ya suena como entró.
    assert np.max(np.abs(salida[:, RATE // 2:])) == pytest.approx(0.5, rel=0.01)


def test_recuerda_entre_bloques():
    """Si cada bloque empezara con la ganancia en 1, el principio del
    siguiente bloque se pasaría del tope."""
    limitador = PeakLimiter(RATE)
    entero = seno(3.0, 2.0)
    partes = [limitador.process(entero[:, i:i + 4800]) for i in range(0, entero.shape[1], 4800)]
    assert np.max(np.abs(np.hstack(partes))) <= CEILING + 1e-6


def test_los_dos_canales_bajan_igual():
    """Enlazado en estéreo: si bajara solo un lado, la imagen se movería."""
    datos = seno(0.3)
    datos[0] *= 5.0
    salida = PeakLimiter(RATE).process(datos)
    razon = salida[1, 1000:2000] / np.where(datos[1, 1000:2000] == 0, 1, datos[1, 1000:2000])
    izquierda = salida[0, 1000:2000] / np.where(datos[0, 1000:2000] == 0, 1, datos[0, 1000:2000])
    assert np.allclose(razon, izquierda, atol=1e-5)


# --- en la mezcla de verdad ------------------------------------------------

def mezcla(media, fmt="fltp", limit=True):
    fuerte = Clip(source=media["tono"], start=0.0, duration=2.0, gain=3.0)   # 0.5 × 3
    otro = Clip(source=media["tono"], start=0.0, duration=2.0)
    mezclador = AudioMixer([fuerte, otro], fmt=fmt, limit=limit)
    return mezclador, list(mezclador.stream(0.0, 2.0))


def maximo(frames):
    picos = []
    for f in frames:
        datos = f.to_ndarray().astype(np.float64)
        if np.issubdtype(f.to_ndarray().dtype, np.integer):
            datos = datos / 32768.0
        picos.append(np.max(np.abs(datos)))
    return max(picos)


def test_la_mezcla_ya_no_recorta(media):
    mezclador, frames = mezcla(media)
    assert maximo(frames) <= CEILING + 1e-4
    assert mezclador.reductions, "el limitador debió avisar que actuó"


def test_tampoco_en_el_play(media):
    """El play pide s16: antes el recorte pasaba al convertir a enteros."""
    _, frames = mezcla(media, fmt="s16")
    assert frames[0].format.name == "s16"
    assert maximo(frames) <= CEILING + 1e-3


def test_la_duracion_no_cambia(media):
    _, frames = mezcla(media, fmt="s16")
    assert sum(f.samples for f in frames) == 2 * RATE


def test_sin_limitador_si_recorta(media):
    mezclador, frames = mezcla(media, limit=False)
    assert maximo(frames) > 1.0
    assert not mezclador.reductions


def test_una_mezcla_normal_no_se_entera(media):
    mezclador, frames = mezcla(media, limit=True)
    tranquila = AudioMixer([Clip(source=media["tono"], start=0.0, duration=2.0)])
    list(tranquila.stream(0.0, 2.0))
    assert not tranquila.reductions
