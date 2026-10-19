"""El reproductor de audio de la edición, con una tarjeta de sonido de mentira."""

import pytest

from vortex_studio.media.audio import LAYOUT, RATE, silence
from vortex_studio.ui import audio_player
from vortex_studio.ui.audio_player import BYTES_PER_FRAME, AudioPlayer


class TarjetaFalsa:
    """Acepta todo lo que le manden, como un búfer sin fondo."""

    def __init__(self, *args) -> None:
        self.escrito = bytearray()
        self.parada = False

    def setVolume(self, volumen) -> None:
        pass

    def start(self):
        return self

    def write(self, datos) -> int:
        self.escrito += bytes(datos)
        return len(datos)

    def bytesFree(self) -> int:
        return 1 << 30

    def processedUSecs(self) -> int:
        return 0

    def stop(self) -> None:
        self.parada = True


class MezclaRota:
    """Entrega medio segundo y luego truena, como la cola en `s16` de antes."""

    reductions = ()

    def __init__(self, *args, **kwargs) -> None:
        pass

    def stream(self, desde, hasta):
        yield from silence(0.5, RATE, LAYOUT, "s16")
        raise ValueError("Frame does not match AudioResampler setup.")


@pytest.fixture
def tarjeta(monkeypatch):
    tarjetas = []

    def nueva(*args):
        tarjetas.append(TarjetaFalsa(*args))
        return tarjetas[-1]

    monkeypatch.setattr(audio_player, "QAudioSink", nueva)
    monkeypatch.setattr(AudioPlayer, "available", property(lambda self: True))
    return tarjetas


def test_si_la_mezcla_truena_el_play_no_se_queda_a_medias(qapp, tarjeta, monkeypatch, capsys):
    """El error salía de `start()` —o del temporizador que alimenta la
    tarjeta— y dejaba a la ventana con `_playing` puesto y el reloj parado:
    el playhead no se movía y la barra espaciadora solo «pausaba». Ahora lo
    que falta sale en silencio y el play termina como siempre."""
    monkeypatch.setattr(audio_player, "AudioMixer", MezclaRota)
    jugador = AudioPlayer()
    try:
        assert jugador.start([object()], 0.0, 1.0) is True
        assert len(tarjeta[0].escrito) == RATE * BYTES_PER_FRAME     # el segundo entero
        assert jugador.playing
        jugador._push()                     # el temporizador tampoco truena
    finally:
        jugador.stop()
    assert "AudioResampler" in capsys.readouterr().err      # pero el error sí se apunta
