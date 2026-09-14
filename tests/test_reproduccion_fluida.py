"""Reproducción sin tirones.

En la beta la imagen daba tirones con clips de celular: el reloj pedía un
instante un poco antes del cuadro recién decodificado, el decodificador lo
tomaba como "ir hacia atrás" y volvía a buscar el keyframe, que en esos
archivos queda a varios segundos. Además el reloj revisaba cada cuadro entero
y, con el temblor del temporizador, repetía unos y se brincaba otros.
"""

import shutil
import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

from vortex_studio.media import VideoSource
from vortex_studio.media.frameserver import FrameJob, FrameServer

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def gop_largo(tmp_path_factory):
    """Keyframe cada 3 s, como sale de un celular o de Pexels."""
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("gop") / "gop.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=320x180:rate=30:duration=6",
                    "-c:v", "libx264", "-g", "90", "-keyint_min", "90", "-sc_threshold", "0",
                    "-pix_fmt", "yuv420p", str(ruta)], check=True)
    return ruta


def contar_busquedas(fuente, monkeypatch):
    cuenta = [0]
    real = fuente._seek

    def contando(t):
        cuenta[0] += 1
        real(t)

    monkeypatch.setattr(fuente, "_seek", contando)
    return cuenta


def limpio(ruta, t):
    with VideoSource(ruta) as fuente:
        return fuente.frame_at(t).data


def test_un_instante_dentro_del_mismo_cuadro_no_busca(gop_largo, monkeypatch):
    with VideoSource(gop_largo) as fuente:
        fuente.frame_at(1.0)
        fuente.frame_at(1.0 + 3 / 30 + 0.01)
        busquedas = contar_busquedas(fuente, monkeypatch)
        # Un poco antes del cuadro recién servido, pero después del anterior.
        fuente.frame_at(1.0 + 3 / 30 + 0.004)
        assert busquedas[0] == 0


def test_reproducir_con_keyframes_lejanos_no_busca(gop_largo, monkeypatch):
    """El patrón de la reproducción: cada tick pide su cuadro y ocho adelantados
    al servidor, en la rejilla de cuadros, como lo hace la ventana."""
    cuenta = [0]
    real = VideoSource._seek

    def contando(self, t):
        cuenta[0] += 1
        real(self, t)

    monkeypatch.setattr(VideoSource, "_seek", contando)
    servidor = FrameServer()
    try:
        def job(n):
            return FrameJob.make(1, gop_largo, n / 30)

        assert servidor.wait_for([job(30)])
        cuenta[0] = 0
        for n in range(31, 120):
            ahora = [job(n)]
            servidor.request(ahora, [job(n + i) for i in range(1, 9)])
            assert servidor.wait_for(ahora)
        assert cuenta[0] == 0
    finally:
        servidor.close()


def test_a_29_97_cada_cuadro_es_distinto(tmp_path):
    """A 29.97 el instante redondeado puede quedar un pelo después del cuadro.
    Antes eso servía el cuadro siguiente, y el que venía repetía el mismo: la
    imagen corría a medio cuadro por segundo."""
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg")
    ruta = tmp_path / "ntsc.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x90:rate=30000/1001:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ruta)], check=True)
    fps = 30000 / 1001
    with VideoSource(ruta) as fuente:
        anterior = None
        for n in range(30, 75):
            t = FrameJob.make(1, ruta, n / fps).time      # el mismo redondeo que la app
            datos = fuente.frame_at(t).data
            assert datos != anterior, n
            anterior = datos


def test_el_cuadro_servido_sigue_siendo_el_correcto(gop_largo):
    instantes = [1.0, 1.05, 1.034, 1.2, 1.18, 1.19, 1.5, 1.4999, 2.01]
    with VideoSource(gop_largo) as fuente:
        for t in instantes:
            assert fuente.frame_at(t).data == limpio(gop_largo, t), t


def test_pedir_el_mismo_instante_dos_veces_da_el_mismo_cuadro(gop_largo):
    """Antes la segunda vez avanzaba al siguiente: la mezcla de cuadros y el
    flujo óptico, que piden los vecinos una y otra vez, brincaban hacia atrás."""
    with VideoSource(gop_largo) as fuente:
        primero = fuente.frame_at(1 / 30).data
        segundo = fuente.frame_at(1 / 30).data
    assert primero == segundo == limpio(gop_largo, 1 / 30)


def test_la_mezcla_en_camara_lenta_avanza_en_orden(gop_largo):
    """A 0.25× cada cuadro del archivo va seguido de tres mezclas y luego el siguiente."""
    from vortex_studio.model.project import SAMPLE_BLEND

    cuadros = [limpio(gop_largo, n / 30) for n in range(8)]
    vistos = []
    with VideoSource(gop_largo) as fuente:
        for i in range(4, 20):
            datos = fuente.frame_at(i / 120, sampling=SAMPLE_BLEND).data
            vistos.append(cuadros.index(datos) if datos in cuadros else "mezcla")
    assert vistos == [1, "mezcla", "mezcla", "mezcla", 2, "mezcla", "mezcla", "mezcla",
                      3, "mezcla", "mezcla", "mezcla", 4, "mezcla", "mezcla", "mezcla"]


def test_ir_de_verdad_hacia_atras_si_busca(gop_largo, monkeypatch):
    with VideoSource(gop_largo) as fuente:
        fuente.frame_at(2.0)
        busquedas = contar_busquedas(fuente, monkeypatch)
        cuadro = fuente.frame_at(1.0)
        assert busquedas[0] == 1
        assert cuadro.data == limpio(gop_largo, 1.0)


def test_el_reloj_revisa_varias_veces_por_cuadro(ventana):
    cuadro_ms = 1000 / ventana.sequence.fps
    assert ventana._interval() <= cuadro_ms / 2


def test_el_playhead_cae_en_un_cuadro_exacto(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(0.0)
    ventana.audio.start = lambda *a, **k: False
    ventana.toggle_play()
    fin = time.monotonic() + 0.3
    while time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.005)
    ventana._tick()
    ventana._pause()

    cuadros = ventana.timeline.playhead * ventana.sequence.fps
    assert ventana.timeline.playhead > 0
    assert abs(cuadros - round(cuadros)) < 1e-6
