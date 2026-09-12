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


# --- lo nuevo llega al archivo final --------------------------------------

def test_lo_exportado_trae_la_mascara_quemada(tmp_path, ventana, media):
    """Si el compositor de la exportación no la aplicara, se vería al
    editar y no en el archivo. Es el bug que evita tener un solo
    compositor para las dos cosas."""
    from vortex_studio.media import VideoSource

    ventana._place_video(media["gris"])
    clip = ventana.sequence.top_clip_at(0.5)
    clip.mask.shape = "Círculo"
    clip.mask.width = clip.mask.height = 0.5
    clip.mask.feather = 0.0

    salida = tmp_path / "mascara.mp4"
    total = 15
    export_video(salida, ventana._frames(0.0, 0.5, 30), total,
                 ventana.sequence.width, ventana.sequence.height,
                 30, "Máxima")

    fuente = VideoSource(salida)
    try:
        f = fuente.frame_at(0.2)
        centro = sum(f.data[(f.height // 2) * f.stride + (f.width // 2) * 3:]
                     [:3])
        esquina = sum(f.data[2 * f.stride + 6:2 * f.stride + 9])
        assert centro > 250, "el centro tenía que seguir gris"
        assert esquina < 60, "la esquina tenía que salir negra"
    finally:
        fuente.close()


def test_lo_exportado_trae_las_dos_pistas_de_audio_mezcladas(tmp_path, ventana, media):
    """Con el bug de la mezcla, el segundo clip salía mudo en el archivo."""
    from vortex_studio.media.mixer import AudioMixer
    from vortex_studio.model import Clip

    ventana._place_video(media["sonoro"])
    segunda = ventana.sequence.audio_tracks()[1]
    segunda.add(Clip(source=media["sonoro"], start=0.0, duration=3.0))

    def exportar(nombre, clips):
        salida = tmp_path / nombre
        export_video(salida, ventana._frames(0.0, 2.0, 30), 60,
                     ventana.sequence.width, ventana.sequence.height,
                     30, "Borrador", None,
                     AudioMixer(clips).stream(0.0, 2.0))
        return max(peaks(salida, 40))

    una = exportar("una.mp4", ventana.sequence.audio_tracks()[0].clips)
    dos = exportar("dos.mp4", ventana._audio_clips())

    assert una > 0.2
    assert dos > una * 1.3, "las dos pistas no se sumaron"


def test_lo_exportado_trae_la_animacion_del_texto(tmp_path, ventana, media):
    """A la mitad de la entrada el texto va transparente: el archivo
    tiene que verse distinto ahí que cuando ya está puesto."""
    from vortex_studio.media import VideoSource

    ventana._place_video(media["gris"])
    ventana._seek(0.0)
    ventana.add_title()
    t = ventana._title
    t.text, t.start, t.duration = "MMMM", 0.0, 2.0
    t.anim_in, t.anim_time = "Escribiéndose", 1.0

    salida = tmp_path / "animado.mp4"
    export_video(salida, ventana._frames(0.0, 1.5, 30), 45,
                 ventana.sequence.width, ventana.sequence.height,
                 30, "Máxima")

    def banda(f) -> bytes:
        """La franja del cuadro donde va el subtítulo."""
        inicio = int(f.height * 0.86) * f.stride
        return bytes(f.data[inicio: inicio + f.width * 3])

    fuente = VideoSource(salida)
    try:
        assert banda(fuente.frame_at(0.05)) != banda(fuente.frame_at(1.2))
    finally:
        fuente.close()
