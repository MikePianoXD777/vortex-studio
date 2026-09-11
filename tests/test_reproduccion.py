"""Reproducción con sonido."""

import time

import pytest
from PySide6.QtWidgets import QApplication


def esperar(ms: int) -> None:
    """Deja correr el ciclo de eventos, que es quien alimenta al audio."""
    fin = time.monotonic() + ms / 1000.0
    while time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.005)


def test_hay_reproductor(ventana):
    assert ventana.audio is not None
    assert not ventana.audio.playing


def test_sin_audio_la_imagen_corre_igual(ventana, media):
    """Un video mudo debe reproducirse aunque no haya nada que sonar."""
    ventana._place_video(media["mudo"])
    ventana._seek(0.0)
    ventana.toggle_play()

    assert ventana._playing
    assert not ventana._audio_on
    esperar(250)
    ventana._tick()
    assert ventana.timeline.playhead > 0
    ventana._pause()


def test_con_audio_arranca_el_sonido(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana._seek(0.0)

    if not ventana.audio.available:
        pytest.skip("esta máquina no tiene salida de audio")

    ventana.toggle_play()
    assert ventana._audio_on, "había clips de audio y no arrancó el sonido"
    assert ventana.audio.playing

    esperar(300)
    assert ventana.audio.position() > 0, "la tarjeta no consumió nada"
    ventana._pause()
    assert not ventana.audio.playing


def test_la_imagen_sigue_al_sonido(ventana, media):
    """Con audio activo el playhead se guía por lo que ya salió por la tarjeta."""
    ventana._place_video(media["sonoro"])
    ventana._seek(0.0)
    if not ventana.audio.available:
        pytest.skip("esta máquina no tiene salida de audio")

    ventana.toggle_play()
    esperar(400)
    ventana._tick()

    posicion = ventana.timeline.playhead
    assert 0.1 < posicion < 1.2, f"el playhead se fue a {posicion}s"
    assert abs(posicion - ventana.audio.position()) < 0.25, "imagen y sonido desfasados"
    ventana._pause()


def test_a_otra_velocidad_no_suena(ventana, media):
    """A 2× el tono saldría cambiado: es peor que no oírlo."""
    ventana._place_video(media["sonoro"])
    ventana.set_speed(2.0)
    ventana._seek(0.0)
    ventana.toggle_play()

    assert not ventana._audio_on
    ventana._pause()
    ventana.set_speed(1.0)


def test_pausar_corta_el_sonido(ventana, media):
    ventana._place_video(media["sonoro"])
    if not ventana.audio.available:
        pytest.skip("esta máquina no tiene salida de audio")

    ventana._seek(0.0)
    ventana.toggle_play()
    esperar(150)
    ventana.toggle_play()

    assert not ventana._playing
    assert not ventana.audio.playing


def test_el_volumen_se_puede_bajar(ventana):
    ventana.audio.set_volume(0.3)
    assert ventana.audio._volume == pytest.approx(0.3)
    ventana.audio.set_volume(5.0)
    assert ventana.audio._volume == 1.0        # se recorta al tope
    ventana.audio.set_volume(-1.0)
    assert ventana.audio._volume == 0.0


def test_silenciar_desde_el_transporte(ventana):
    recibido = []
    ventana.transport.volume_changed.connect(recibido.append)
    ventana.transport._mute.setChecked(True)
    assert recibido[-1] == 0.0
    ventana.transport._mute.setChecked(False)
    assert recibido[-1] > 0
