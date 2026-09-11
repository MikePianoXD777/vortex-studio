"""Exportar video: que el archivo salga como se ve al editar."""

import av
import pytest

from vortex_studio.media.audio import AudioRenderer, peaks
from vortex_studio.media.encoder import Cancelled, export_video


def datos(path):
    with av.open(str(path)) as c:
        video = c.streams.video[0]
        return {
            "tipos": sorted(s.type for s in c.streams),
            "ancho": video.codec_context.width,
            "alto": video.codec_context.height,
            "duracion": float(c.duration / av.time_base),
        }


@pytest.fixture
def proyecto(ventana, media):
    """Una secuencia con video, imagen, texto y color: todo junto."""
    ventana._place_video(media["sonoro"])
    ventana._seek(1.0)
    ventana._place_image(media["logo"])
    ventana.add_title()
    ventana.text_panel._text.setPlainText("Exportado")
    ventana._flush()
    ventana.sequence.top_clip_at(2.0).color.saturation = 140
    return ventana


def test_exporta_video(tmp_path, proyecto):
    salida = tmp_path / "salida.mp4"
    total = int(round(3 * proyecto.sequence.fps))
    export_video(salida, proyecto._frames(0.0, 3.0, proyecto.sequence.fps), total,
                 proyecto.sequence.width, proyecto.sequence.height,
                 proyecto.sequence.fps, "Borrador")

    info = datos(salida)
    assert info["tipos"] == ["video"]
    assert (info["ancho"], info["alto"]) == (320, 180)
    assert abs(info["duracion"] - 3.0) < 0.15


def test_exporta_con_audio(tmp_path, proyecto):
    salida = tmp_path / "con-audio.mp4"
    total = int(round(3 * proyecto.sequence.fps))
    export_video(salida, proyecto._frames(0.0, 3.0, proyecto.sequence.fps), total,
                 proyecto.sequence.width, proyecto.sequence.height,
                 proyecto.sequence.fps, "Borrador", None,
                 AudioRenderer(proyecto._audio_clips()).stream(0.0, 3.0))

    assert datos(salida)["tipos"] == ["audio", "video"]
    assert max(peaks(salida, 40)) > 0.3, "el audio salió mudo"


def test_lo_exportado_trae_el_texto_quemado(tmp_path, proyecto, media):
    from vortex_studio.media import VideoSource

    salida = tmp_path / "quemado.mp4"
    total = int(round(3 * proyecto.sequence.fps))
    export_video(salida, proyecto._frames(0.0, 3.0, proyecto.sequence.fps), total,
                 proyecto.sequence.width, proyecto.sequence.height,
                 proyecto.sequence.fps, "Borrador")

    original, nuevo = VideoSource(media["sonoro"]), VideoSource(salida)
    try:
        a, b = original.frame_at(2.0), nuevo.frame_at(2.0)
        fila = int(b.height * 0.88)          # la banda donde va el subtítulo
        assert a.data[fila * a.stride: fila * a.stride + 400] != \
               b.data[fila * b.stride: fila * b.stride + 400]
    finally:
        original.close()
        nuevo.close()


def test_cancelar_no_deja_archivo_a_medias(tmp_path, proyecto):
    """Un video truncado que parece terminado es peor que no tener archivo."""
    salida = tmp_path / "cancelado.mp4"
    total = int(round(3 * proyecto.sequence.fps))

    with pytest.raises(Cancelled):
        export_video(salida, proyecto._frames(0.0, 3.0, proyecto.sequence.fps), total,
                     proyecto.sequence.width, proyecto.sequence.height,
                     proyecto.sequence.fps, "Borrador",
                     lambda hecho, de: hecho < 5)

    assert not salida.exists()


def test_dimensiones_impares_se_ajustan(tmp_path, proyecto):
    """H.264 no acepta lados impares: hay que bajarlos al par anterior."""
    salida = tmp_path / "impar.mp4"
    total = 10
    export_video(salida, proyecto._frames(0.0, 10 / 30, 30), total,
                 321, 181, 30, "Borrador")

    info = datos(salida)
    assert (info["ancho"], info["alto"]) == (320, 180)
