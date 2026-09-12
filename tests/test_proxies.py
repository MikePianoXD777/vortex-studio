"""Proxies de 540p: el preview edita liviano y la exportación sale del original."""

import os
import shutil
import subprocess
import time

import av
import pytest
from PySide6.QtWidgets import QApplication

from vortex_studio.media.encoder import Cancelled
from vortex_studio.media.proxy import (
    GOP,
    existing_proxy,
    make_proxy,
    needs_proxy,
    proxy_path,
    proxy_size,
)

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def pesado(tmp_path_factory):
    """Un video de 1280×720: lo bastante grande para que valga un proxy."""
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("proxy") / "pesado.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=1280x720:rate=30:duration=3",
                    "-c:v", "libx264", "-g", "90", "-pix_fmt", "yuv420p", str(ruta)], check=True)
    return ruta


def esperar(condicion, segundos=60):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_tamanos():
    assert proxy_size(3840, 2160) == (960, 540)
    assert proxy_size(1080, 1920) == (540, 960)
    assert proxy_size(320, 180) == (320, 180)       # nunca más grande
    assert needs_proxy(1920, 1080) and not needs_proxy(960, 540)


def test_crear_un_proxy(pesado):
    ruta = make_proxy(pesado)
    assert ruta == existing_proxy(pesado)
    with av.open(str(ruta)) as c:
        v = c.streams.video[0]
        assert (v.codec_context.width, v.codec_context.height) == (960, 540)
        assert not c.streams.audio
        assert float(c.duration / av.time_base) == pytest.approx(3.0, abs=0.1)
        claves = [float(p.pts * v.time_base) for p in c.demux(v)
                  if p.is_keyframe and p.pts is not None]
    # Un keyframe cada medio segundo como mucho: saltar es barato.
    assert max(b - a for a, b in zip(claves, claves[1:])) <= GOP / 30 + 1e-3


def test_el_proxy_coincide_en_el_tiempo(pesado):
    """El segundo 2 del proxy tiene que ser el segundo 2 del original."""
    from vortex_studio.media import VideoSource

    def huella(fuente, t):
        f = fuente.frame_at(t)
        chico = av.VideoFrame.from_ndarray(
            __import__("numpy").frombuffer(f.data, "uint8").reshape(f.height, f.stride // 3, 3)
            [:, :f.width], format="rgb24").reformat(width=32, height=18)
        return chico.to_ndarray().astype(int)

    original, proxy = VideoSource(pesado), VideoSource(make_proxy(pesado))
    try:
        mismo = abs(huella(original, 2.0) - huella(proxy, 2.0)).mean()
        otro = abs(huella(original, 2.0) - huella(proxy, 1.0)).mean()
        assert mismo < otro / 3
    finally:
        original.close()
        proxy.close()


def test_cancelar_no_deja_archivo(pesado, tmp_path):
    copia = tmp_path / "otro.mp4"
    shutil.copy(pesado, copia)
    with pytest.raises(Cancelled):
        make_proxy(copia, lambda hecho, total: hecho < 500)
    assert existing_proxy(copia) is None
    assert not list(proxy_path(copia).parent.glob("*.parte.mp4"))


def test_cambiar_el_archivo_invalida_el_proxy(pesado, tmp_path):
    copia = tmp_path / "cambia.mp4"
    shutil.copy(pesado, copia)
    antes = proxy_path(copia)
    os.utime(copia, (time.time() + 100, time.time() + 100))
    assert proxy_path(copia) != antes


def test_en_la_ventana_el_preview_usa_el_proxy_y_exportar_no(ventana, pesado):
    ventana._place_video(pesado)
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.set_use_proxies(True)
    assert esperar(lambda: not ventana.proxies.busy and
                   ventana._proxy_paths.get(clip.source) is not None)

    assert ventana._preview_path(clip) == existing_proxy(pesado)
    ventana._settle_preview()
    assert ventana._layers_at(1.0)[0].frame.width == 960
    assert ventana._layers_at(1.0, sync=True)[0].frame.width == 1280
    assert "Proxies" in ventana.statusBar().currentMessage()

    ventana.set_use_proxies(False)
    assert ventana._preview_path(clip) == clip.source


def test_el_interruptor_se_recuerda(ventana, pesado):
    from vortex_studio.ui.settings import load_settings

    ventana.set_use_proxies(True)
    assert load_settings()["proxies"] is True
    ventana.set_use_proxies(False)
    assert load_settings()["proxies"] is False


def test_un_video_chico_no_pide_proxy(ventana, media):
    ventana._place_video(media["mudo"])
    assert ventana.create_proxies() == 0
