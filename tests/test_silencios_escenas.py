"""Detección de silencios con corte automático, y de cambios de escena."""

import shutil
import subprocess

import numpy as np
import pytest

from vortex_studio.model import Clip, Sequence
from vortex_studio.model.cuts import CutRanges, timeline_ranges
from vortex_studio.model import timeremap

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def platica(tmp_path_factory):
    """Video con audio: tono 0–1 s, silencio 1–2.5 s, tono 2.5–3.5 s, silencio 3.5–4 s."""
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path_factory.mktemp("platica") / "platica.mp4"
    expresion = "if(lt(t,1)+between(t,2.5,3.5),0.5*sin(2*PI*440*t),0)"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=4",
                    "-f", "lavfi", "-i", f"aevalsrc='{expresion}':s=48000:d=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", str(ruta)], check=True)
    return ruta


@pytest.fixture(scope="module")
def tomas(tmp_path_factory):
    """Tres tomas de un segundo con texturas distintas, y un paneo en la segunda."""
    import av

    ruta = tmp_path_factory.mktemp("tomas") / "tomas.mp4"
    rng = np.random.default_rng(5)
    texturas = [(rng.random((90, 400, 3)) * 255).astype(np.uint8) for _ in range(3)]
    texturas[1] = (texturas[1] * 0.5).astype(np.uint8)
    with av.open(str(ruta), "w") as contenedor:
        flujo = contenedor.add_stream("libx264", rate=30)
        flujo.width, flujo.height, flujo.pix_fmt = 160, 90, "yuv420p"
        flujo.options = {"crf": "18", "preset": "ultrafast"}
        for toma in range(3):
            for n in range(30):
                x = n * 3 if toma == 1 else 0          # paneo: no es corte
                cuadro = np.ascontiguousarray(texturas[toma][:, x:x + 160])
                for paquete in flujo.encode(av.VideoFrame.from_ndarray(cuadro, format="rgb24")):
                    contenedor.mux(paquete)
        for paquete in flujo.encode():
            contenedor.mux(paquete)
    return ruta


# --- silencios ------------------------------------------------------------------------------

def test_encuentra_los_silencios_con_margen(platica):
    from vortex_studio.media.silence import silent_ranges

    tramos = silent_ranges(platica, padding=0.1)
    assert len(tramos) == 2
    (a, b), (c, d) = tramos
    assert a == pytest.approx(1.1, abs=0.06) and b == pytest.approx(2.4, abs=0.06)
    assert c == pytest.approx(3.6, abs=0.06) and d == pytest.approx(4.0, abs=0.06)


def test_un_silencio_mas_corto_que_el_minimo_no_cuenta(platica):
    from vortex_studio.media.silence import silent_ranges

    tramos = silent_ranges(platica, min_duration=1.0)
    assert len(tramos) == 1 and tramos[0][0] == pytest.approx(1.12, abs=0.06)


def test_sin_audio_no_hay_silencios(media):
    from vortex_studio.media.silence import silent_ranges

    assert silent_ranges(media["mudo"]) == []
    assert silent_ranges(media["tono"], threshold_db=-80) == []


def test_los_tramos_del_archivo_se_pasan_a_la_linea_de_tiempo():
    clip = Clip("a.mp4", 10.0, 4.0, in_point=2.0, speed=2.0)
    # Archivo 3–4 s → pista 10.5–11; 8–20 s → recortado a 13–14.
    assert timeline_ranges(clip, [(8.0, 20.0), (3.0, 4.0), (0.0, 1.0)]) == \
        [(10.5, 11.0), (13.0, 14.0)]


def test_tramos_encimados_se_juntan_y_el_remapeo_no_se_adivina():
    clip = Clip("a.mp4", 0.0, 10.0)
    assert timeline_ranges(clip, [(1.0, 3.0), (2.5, 4.0), (4.0, 4.01)]) == [(1.0, 4.0)]
    timeremap.enable(clip)
    assert timeline_ranges(clip, [(1.0, 3.0)]) == []
    assert timeline_ranges(Clip("a.mp4", 0, 5, speed=0.0), [(1, 2)]) == []


def test_cortar_tramos_cierra_huecos_en_video_y_audio():
    secuencia = Sequence.default()
    video = secuencia.track_named("V1").add(Clip("a.mp4", 0.0, 10.0, link="x"))
    secuencia.track_named("A1").add(Clip("a.mp4", 0.0, 10.0, link="x"))
    despues = secuencia.track_named("V1").add(Clip("b.mp4", 10.0, 2.0))
    comando = CutRanges(item=video, ranges=[(2.0, 3.0), (6.0, 8.0)])
    assert comando.apply(secuencia)
    assert comando.count == 2 and comando.removed == pytest.approx(3.0)
    assert [(c.start, c.duration, c.in_point) for c in secuencia.track_named("V1").clips] == \
        pytest.approx([(0, 2, 0), (2, 3, 3), (5, 2, 8), (7, 2, 0)])
    assert [(c.start, c.duration) for c in secuencia.track_named("A1").clips] == \
        pytest.approx([(0, 2), (2, 3), (5, 2)])
    assert despues.start == pytest.approx(7.0)


def test_cortar_desde_el_inicio_y_hasta_el_final():
    secuencia = Sequence.default()
    video = secuencia.track_named("V1").add(Clip("a.mp4", 0.0, 10.0))
    assert CutRanges(item=video, ranges=[(0.0, 1.0), (9.0, 10.0)]).apply(secuencia)
    assert [(c.start, c.duration, c.in_point) for c in secuencia.track_named("V1").clips] == \
        pytest.approx([(0, 8, 1)])


def test_cortar_en_pista_bloqueada_no_hace_nada():
    secuencia = Sequence.default()
    video = secuencia.track_named("V1").add(Clip("a.mp4", 0.0, 10.0))
    secuencia.track_named("V1").locked = True
    assert not CutRanges(item=video, ranges=[(2.0, 3.0)]).apply(secuencia)
    assert not CutRanges(item=None, ranges=[(2.0, 3.0)]).apply(secuencia)
    assert len(secuencia.track_named("V1").clips) == 1


def test_la_ventana_quita_los_silencios_y_se_deshace(ventana, platica):
    ventana.place_media(platica)
    video = ventana.sequence.track_named("V1").clips[0]
    ventana.timeline.select(video)
    assert ventana.remove_silences() == 2
    assert ventana.sequence.duration == pytest.approx(4.0 - 1.3 - 0.4, abs=0.15)
    assert "silencio" in ventana.statusBar().currentMessage()
    ventana.undo()
    assert ventana.sequence.duration == pytest.approx(4.0, abs=0.05)


def test_la_ventana_sin_silencios_avisa(ventana, media):
    ventana.place_media(media["sonoro"])
    ventana.timeline.select(ventana.sequence.track_named("V1").clips[0])
    assert ventana.remove_silences() == 0
    assert "No hay silencios" in ventana.statusBar().currentMessage()


def test_la_ventana_quita_silencios_del_clip_de_audio_seleccionado(ventana, platica):
    ventana.place_media(platica)
    audio = ventana.sequence.track_named("A1").clips[0]
    ventana.timeline.select(audio)
    assert ventana.remove_silences() == 2
    assert len(ventana.sequence.track_named("V1").clips) == 2


# --- escenas ------------------------------------------------------------------------------------

def test_encuentra_los_dos_cortes_y_no_el_paneo(tomas):
    from vortex_studio.media.scenes import cuts, scores

    cortes = cuts(scores(tomas))
    assert cortes == pytest.approx([1.0, 2.0], abs=0.05)


def test_la_sensibilidad_cambia_cuantos_cortes_hay(tomas):
    from vortex_studio.media.scenes import cuts, scores

    datos = scores(tomas)
    assert cuts(datos, sensitivity=0) == pytest.approx([1.0, 2.0], abs=0.05)
    assert len(cuts(datos, sensitivity=100)) >= 2
    assert cuts(np.zeros((0, 2))) == []


def test_los_puntajes_se_guardan_en_cache(tomas):
    from vortex_studio.media import scenes

    primera = scenes.scores(tomas)
    ruta = scenes._cache_path(tomas)
    assert ruta is not None and ruta.exists()
    assert np.array_equal(np.load(ruta), primera)


def test_un_video_sin_cortes_no_da_cortes(media):
    from vortex_studio.media.scenes import cuts, scores

    assert cuts(scores(media["gris"])) == []
    with pytest.raises(ValueError):
        scores(media["tono"])


def test_la_ventana_divide_el_clip_en_cada_escena(ventana, tomas):
    ventana.place_media(tomas)
    ventana.timeline.select(ventana.sequence.track_named("V1").clips[0])
    assert ventana.detect_scenes(split=True) == 2
    assert [round(c.start, 1) for c in ventana.sequence.track_named("V1").clips] == [0, 1, 2]
    ventana.undo()
    assert len(ventana.sequence.track_named("V1").clips) == 1


def test_la_ventana_marca_las_escenas_sin_cortar(ventana, tomas):
    ventana.place_media(tomas)
    ventana.timeline.select(ventana.sequence.track_named("V1").clips[0])
    assert ventana.detect_scenes(split=False) == 2
    assert [round(m.time, 1) for m in ventana.sequence.markers] == [1.0, 2.0]
    assert len(ventana.sequence.track_named("V1").clips) == 1


def test_la_ventana_con_un_clip_movido_pone_las_escenas_en_su_lugar(ventana, tomas):
    ventana.place_media(tomas)
    clip = ventana.sequence.track_named("V1").clips[0]
    clip.start, clip.in_point, clip.duration = 5.0, 0.5, 2.5
    ventana.timeline.select(clip)
    assert ventana.detect_scenes(split=False) == 2
    assert [round(m.time, 1) for m in ventana.sequence.markers] == [5.5, 6.5]
