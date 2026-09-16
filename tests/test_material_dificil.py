"""Material incómodo del mundo real: NTSC, keyframes lejanos, HEVC, 44.1 kHz.

El banco pasaba con material demasiado cómodo y por eso no vio la
reproducción cortada de la beta. Estas pruebas usan las fixtures de
`dificil`, que se parecen a lo que sale de un celular o de un banco de clips.
"""

import av
import pytest

from vortex_studio.media import VideoSource, probe_media
from vortex_studio.media.audio import LAYOUT, RATE, peaks
from vortex_studio.media.encoder import export_video
from vortex_studio.media.frameserver import FrameJob, FrameServer
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.model import Clip

NTSC = 30000 / 1001


def datos(path):
    with av.open(str(path)) as c:
        video = c.streams.video[0]
        audio = c.streams.audio[0] if c.streams.audio else None
        return {
            "fps": video.average_rate,
            "ancho": video.codec_context.width,
            "alto": video.codec_context.height,
            "video_s": float(video.duration * video.time_base) if video.duration else 0.0,
            "audio_s": float(audio.duration * audio.time_base) if audio and audio.duration else 0.0,
        }


# --- como sale de un celular: 29.97 vertical con keyframes cada 3 s -----------------

def test_reproducir_material_de_celular_no_vuelve_a_buscar(dificil, monkeypatch):
    """El patrón de la reproducción sobre un archivo con keyframes lejanos."""
    cuenta = [0]
    real = VideoSource._seek
    monkeypatch.setattr(VideoSource, "_seek",
                        lambda self, t: (cuenta.__setitem__(0, cuenta[0] + 1), real(self, t))[1])

    servidor = FrameServer()
    try:
        def job(n):
            return FrameJob.make(1, dificil["celular"], n / NTSC)

        assert servidor.wait_for([job(20)])
        cuenta[0] = 0
        for n in range(21, 100):
            ahora = [job(n)]
            servidor.request(ahora, [job(n + i) for i in range(1, 9)])
            assert servidor.wait_for(ahora)
        assert cuenta[0] == 0
    finally:
        servidor.close()


def test_cada_cuadro_de_ese_material_es_distinto(dificil):
    """A 29.97 el tiempo redondeado puede caer un pelo después del cuadro."""
    with VideoSource(dificil["celular"]) as fuente:
        anterior = None
        for n in range(30, 80):
            t = FrameJob.make(1, dificil["celular"], n / NTSC).time
            datos_cuadro = fuente.frame_at(t).data
            assert datos_cuadro != anterior, n
            anterior = datos_cuadro


def test_el_playhead_cae_en_cuadro_con_material_de_celular(ventana, dificil):
    import time

    from PySide6.QtWidgets import QApplication

    ventana._place_video(dificil["celular"])
    ventana.format_from_clip()
    assert ventana.sequence.fps == pytest.approx(NTSC, abs=0.01)

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


# --- exportar sin desfase ------------------------------------------------------------

def test_exportar_material_de_celular_conserva_los_fps(ventana, dificil, tmp_path):
    ventana._place_video(dificil["celular"])
    ventana.format_from_clip()
    salida = tmp_path / "celular.mp4"
    total = int(round(2 * ventana.sequence.fps))
    export_video(salida, ventana._frames(0.0, 2.0, ventana.sequence.fps), total,
                 ventana.sequence.width, ventana.sequence.height,
                 ventana.sequence.fps, "Borrador")
    assert float(datos(salida)["fps"]) == pytest.approx(NTSC)


def test_el_video_y_el_audio_exportados_no_se_desfasan(ventana, dificil, tmp_path):
    ventana._place_video(dificil["celular"])
    ventana.format_from_clip()
    fps = ventana.sequence.fps
    salida = tmp_path / "con-audio.mp4"
    mezcla = AudioMixer(ventana._audio_clips(), rate=RATE, layout=LAYOUT, fmt="s16")
    export_video(salida, ventana._frames(0.0, 4.0, fps), int(round(4 * fps)),
                 ventana.sequence.width, ventana.sequence.height, fps, "Borrador",
                 audio=mezcla.stream(0.0, 4.0), audio_rate=RATE, audio_layout=LAYOUT)

    info = datos(salida)
    assert info["audio_s"] > 0
    # Menos de un cuadro de diferencia entre la imagen y el sonido.
    assert abs(info["video_s"] - info["audio_s"]) < 1 / fps


def test_exportar_una_resolucion_impar_no_truena(ventana, dificil, tmp_path):
    ventana._place_video(dificil["impar"])
    salida = tmp_path / "impar.mp4"
    export_video(salida, ventana._frames(0.0, 1.0, 30), 30, 321, 181, 30, "Borrador")
    info = datos(salida)
    assert info["ancho"] % 2 == 0 and info["alto"] % 2 == 0


# --- HEVC ------------------------------------------------------------------------------

def test_un_hevc_se_importa_con_sus_datos(dificil):
    info = probe_media(dificil["hevc"])
    assert info.video_codec == "hevc"
    assert (info.width, info.height) == (320, 180)
    assert info.duration == pytest.approx(3.0, abs=0.2)


def test_un_hevc_se_ve_y_avanza(dificil):
    with VideoSource(dificil["hevc"]) as fuente:
        vistos = [fuente.frame_at(t).data for t in (0.2, 1.0, 2.0)]
    assert all(v is not None for v in vistos)
    assert len(set(vistos)) == 3


def test_un_hevc_se_exporta_a_h264(ventana, dificil, tmp_path):
    ventana._place_video(dificil["hevc"])
    salida = tmp_path / "de-hevc.mp4"
    export_video(salida, ventana._frames(0.0, 1.0, 25), 25,
                 ventana.sequence.width, ventana.sequence.height, 25, "Borrador")
    with av.open(str(salida)) as c:
        assert c.streams.video[0].codec_context.name == "h264"


# --- 44.1 kHz y mono -------------------------------------------------------------------

def test_un_audio_a_44100_suena_en_la_mezcla(dificil):
    import numpy as np

    clip = Clip(dificil["mono441"], 0.0, 2.0)
    muestras = np.concatenate([f.to_ndarray().reshape(-1)
                               for f in AudioMixer([clip], rate=RATE, layout=LAYOUT).stream(0.0, 2.0)])
    assert float(np.sqrt(np.mean(muestras.astype("float64") ** 2))) > 0.01


def test_mezclar_44100_con_48000_no_cambia_la_duracion(dificil, media):
    clips = [Clip(dificil["mono441"], 0.0, 2.0), Clip(media["tono"], 0.0, 2.0)]
    muestras = sum(f.samples for f in
                   AudioMixer(clips, rate=RATE, layout=LAYOUT).stream(0.0, 2.0))
    assert muestras == pytest.approx(2.0 * RATE, abs=RATE // 50)


def test_la_onda_de_un_44100_se_dibuja(dificil):
    valores = peaks(dificil["mono441"])
    assert len(valores) > 10 and max(valores) > 0.1


# --- un archivo cuyo tiempo no empieza en cero ------------------------------------------

def test_un_archivo_corrido_se_ve_desde_su_primer_cuadro(dificil):
    with VideoSource(dificil["corrido"]) as fuente:
        primero = fuente.frame_at(0.0)
        despues = fuente.frame_at(1.0)
    assert primero is not None and despues is not None
    assert primero.data != despues.data


def test_un_archivo_corrido_dice_su_duracion(dificil):
    info = probe_media(dificil["corrido"])
    assert info.duration == pytest.approx(3.0, abs=0.3)


def test_un_archivo_corrido_se_pone_completo_en_el_timeline(ventana, dificil):
    ventana._place_video(dificil["corrido"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    assert clip.duration == pytest.approx(3.0, abs=0.3)
    assert clip.in_point == pytest.approx(0.0, abs=0.05)


# --- video vertical de celular: viene acostado con marca de giro ------------------------

def test_un_vertical_de_celular_se_sondea_como_vertical(dificil):
    info = probe_media(dificil["rotado"])
    assert (info.width, info.height) == (180, 320)


def test_el_cuadro_de_ese_video_sale_derecho(dificil):
    """Se compara contra el propio ffmpeg, que aplica el giro al exportar."""
    import subprocess

    import numpy as np

    referencia = dificil["rotado"].parent / "referencia.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(dificil["rotado"]),
                    "-frames:v", "1", str(referencia)], check=True)
    with av.open(str(referencia)) as c:
        esperado = next(c.decode(video=0)).reformat(format="rgb24").to_ndarray()

    with VideoSource(dificil["rotado"]) as fuente:
        cuadro = fuente.frame_at(0.0)
    salido = np.frombuffer(cuadro.data, np.uint8).reshape(
        cuadro.height, cuadro.stride)[:, :cuadro.width * 3].reshape(
        cuadro.height, cuadro.width, 3)

    assert salido.shape == esperado.shape
    assert float(np.abs(salido.astype(int) - esperado.astype(int)).mean()) < 1.0


def test_un_video_sin_marca_de_giro_no_se_toca(dificil):
    info = probe_media(dificil["acostado"])
    assert (info.width, info.height) == (320, 180)
    with VideoSource(dificil["acostado"]) as fuente:
        cuadro = fuente.frame_at(0.5)
    assert (cuadro.width, cuadro.height) == (320, 180)


def test_la_secuencia_toma_el_tamano_ya_girado(ventana, dificil):
    ventana._place_video(dificil["rotado"])
    assert (ventana.sequence.width, ventana.sequence.height) == (180, 320)


# --- cuadros que no van parejos (fps variable) -------------------------------------------

def test_un_video_de_fps_variable_avanza(dificil):
    with VideoSource(dificil["vfr"]) as fuente:
        vistos = [fuente.frame_at(t).data for t in (0.1, 0.5, 1.0, 2.0)]
    assert all(v is not None for v in vistos)
    assert len(set(vistos)) == 4


def test_un_video_de_fps_variable_se_importa_completo(ventana, dificil):
    ventana._place_video(dificil["vfr"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    assert clip.duration == pytest.approx(3.0, abs=0.3)


def test_exportar_desde_fps_variable_sale_parejo(ventana, dificil, tmp_path):
    ventana._place_video(dificil["vfr"])
    salida = tmp_path / "parejo.mp4"
    export_video(salida, ventana._frames(0.0, 2.0, 30), 60,
                 ventana.sequence.width, ventana.sequence.height, 30, "Borrador")
    assert float(datos(salida)["fps"]) == pytest.approx(30.0)


def test_el_proxy_de_un_vertical_tambien_queda_vertical(dificil, tmp_path, monkeypatch):
    """Sin esto el proxy se vería acostado y el original derecho."""
    monkeypatch.setenv("VORTEX_CACHE_DIR", str(tmp_path))
    from vortex_studio.media.proxy import make_proxy

    proxy = make_proxy(dificil["rotado"])
    info = probe_media(proxy)
    assert info.width < info.height
    with VideoSource(proxy) as fuente:
        cuadro = fuente.frame_at(0.5)
    assert cuadro.width < cuadro.height


# --- foto de celular con marca de orientación ---------------------------------------------

def test_una_foto_con_marca_exif_se_carga_derecha(dificil):
    from vortex_studio.ui.imagenes import load_image

    derecha = load_image(dificil["foto_exif"])
    assert (derecha.width(), derecha.height()) == (180, 320)


def test_una_foto_sin_marca_no_se_toca(dificil):
    from vortex_studio.ui.imagenes import load_image

    igual = load_image(dificil["foto"])
    assert (igual.width(), igual.height()) == (320, 180)


def test_esa_foto_entra_derecha_al_timeline(ventana, dificil):
    ventana._place_image(dificil["foto_exif"])
    imagen = ventana._image_for(dificil["foto_exif"])
    assert imagen.height() > imagen.width()


def test_el_render_tambien_la_pone_derecha(ventana, dificil):
    ventana._place_image(dificil["foto_exif"])
    render = ventana._renderer()
    try:
        imagen = render.images.get(dificil["foto_exif"]) if render.images else None
        if imagen is None:
            imagen = ventana._image_for(dificil["foto_exif"])
        assert imagen.height() > imagen.width()
    finally:
        render.close()
