"""Cuadros intermedios en cámara lenta: mezcla de cuadros y flujo óptico."""

import numpy as np
import pytest

from vortex_studio.model import Clip, Sequence
from vortex_studio.model.project import SAMPLE_BLEND, SAMPLE_FLOW, SAMPLE_NEAREST

FPS = 10


def _escribir(path, cuadros):
    import av

    alto, ancho, _ = cuadros[0].shape
    with av.open(str(path), "w") as contenedor:
        flujo = contenedor.add_stream("libx264", rate=FPS)
        flujo.width, flujo.height, flujo.pix_fmt = ancho, alto, "yuv444p"
        flujo.options = {"qp": "0", "preset": "ultrafast"}
        for arreglo in cuadros:
            for paquete in flujo.encode(__import__("av").VideoFrame.from_ndarray(arreglo, format="rgb24")):
                contenedor.mux(paquete)
        for paquete in flujo.encode():
            contenedor.mux(paquete)
    return path


@pytest.fixture(scope="module")
def grises(tmp_path_factory):
    """Cada cuadro un gris parejo 12 niveles más claro que el anterior.

    Doce segundos y no dos: un archivo más corto que lo que el decodificador
    lee por adelantado obliga a volver a buscar en cada paso.
    """
    cuadros = [np.full((36, 64, 3), (12 * n) % 240, np.uint8) for n in range(120)]
    return _escribir(tmp_path_factory.mktemp("grises") / "grises.mp4", cuadros)


@pytest.fixture(scope="module")
def cuadrito(tmp_path_factory):
    """Un cuadro blanco de 30 pixeles que avanza 8 por cuadro sobre negro."""
    cuadros = []
    for n in range(12):
        arreglo = np.zeros((90, 160, 3), np.uint8)
        arreglo[30:60, 20 + 8 * n:50 + 8 * n] = 255
        cuadros.append(arreglo)
    return _escribir(tmp_path_factory.mktemp("cuadrito") / "cuadrito.mp4", cuadros)


def _gris(frame):
    return float(np.frombuffer(frame.data, np.uint8).reshape(frame.height, frame.stride)
                 [:, :frame.width * 3].mean())


def _fila(frame, y=45):
    crudo = np.frombuffer(frame.data, np.uint8).reshape(frame.height, frame.stride)
    return crudo[y, 0:frame.width * 3:3].astype(int)


# --- mezcla de cuadros -----------------------------------------------------------------

def test_sin_muestreo_se_repite_un_cuadro_entero(grises):
    from vortex_studio.media.decoder import VideoSource

    # 0.15 s cae entre el cuadro 1 (gris 12) y el 2 (gris 24): se ve el 1,
    # que es el que empezó. Hasta la 0.1.0b2 se daba el siguiente.
    with VideoSource(grises) as fuente:
        assert _gris(fuente.frame_at(0.15)) == pytest.approx(12, abs=2)


def test_la_mezcla_a_la_mitad_da_el_promedio_de_los_vecinos(grises):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(grises) as fuente:
        assert _gris(fuente.frame_at(0.15, sampling=SAMPLE_BLEND)) == pytest.approx(18, abs=2)


def test_la_mezcla_pesa_segun_la_distancia(grises):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(grises) as fuente:
        assert _gris(fuente.frame_at(0.125, sampling=SAMPLE_BLEND)) == pytest.approx(15, abs=2)
        assert _gris(fuente.frame_at(0.175, sampling=SAMPLE_BLEND)) == pytest.approx(21, abs=2)


def test_justo_en_un_cuadro_no_se_mezcla_nada(grises):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(grises) as a, VideoSource(grises) as b:
        assert a.frame_at(0.3, sampling=SAMPLE_BLEND).data == b.frame_at(0.3).data


def test_avanzar_entre_los_mismos_vecinos_no_vuelve_a_buscar(grises):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(grises) as fuente:
        busquedas = []
        original = fuente._seek
        fuente._seek = lambda t: (busquedas.append(t), original(t))[1]
        for t in np.arange(0.51, 0.99, 0.02):
            fuente.frame_at(float(t), sampling=SAMPLE_BLEND)
        assert len(busquedas) <= 1


def test_la_mezcla_conserva_la_transparencia_de_la_llave(grises):
    from vortex_studio.media.decoder import VideoSource
    from vortex_studio.model.chroma import ChromaKey

    with VideoSource(grises) as fuente:
        cuadro = fuente.frame_at(0.15, None, ChromaKey(enabled=True), sampling=SAMPLE_FLOW)
    assert cuadro.alpha and len(cuadro.data) == cuadro.stride * cuadro.height


# --- flujo óptico -------------------------------------------------------------------------

def test_el_flujo_optico_pone_el_objeto_a_medio_camino(cuadrito):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(cuadrito) as fuente:
        fila = _fila(fuente.frame_at(0.35, sampling=SAMPLE_FLOW))
    blancos = np.where(fila > 128)[0]
    # Cuadro 3 empieza en 44 y el 4 en 52: a la mitad, en 48.
    assert blancos.min() == pytest.approx(48, abs=2)
    assert blancos.max() - blancos.min() == pytest.approx(29, abs=3)


def test_la_mezcla_en_cambio_deja_dos_objetos_a_medias(cuadrito):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(cuadrito) as fuente:
        mezcla = _fila(fuente.frame_at(0.35, sampling=SAMPLE_BLEND))
        flujo = _fila(fuente.frame_at(0.35, sampling=SAMPLE_FLOW))
    medios = (mezcla > 90) & (mezcla < 170)
    # Los cuadros 3 y 4 no se enciman de 44 a 51 ni de 74 a 81: ahí la mezcla
    # queda a medio gris, dos fantasmas; el flujo óptico no deja ninguno.
    assert medios[44:52].all() and medios[74:82].all()
    assert ((flujo > 90) & (flujo < 170)).sum() < 6


def test_el_flujo_optico_sigue_la_proporcion_del_instante(cuadrito):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(cuadrito) as fuente:
        cuarto = np.where(_fila(fuente.frame_at(0.325, sampling=SAMPLE_FLOW)) > 128)[0].min()
        tres = np.where(_fila(fuente.frame_at(0.375, sampling=SAMPLE_FLOW)) > 128)[0].min()
    assert cuarto == pytest.approx(46, abs=2) and tres == pytest.approx(50, abs=2)


# --- a través del servidor, el render y el proyecto ------------------------------------------

def test_el_servidor_distingue_el_mismo_instante_con_otro_muestreo(grises):
    from vortex_studio.media.frameserver import FrameJob, FrameServer

    servidor = FrameServer()
    try:
        cercano = FrameJob.make(1, grises, 0.15)
        mezcla = FrameJob.make(1, grises, 0.15, sampling=SAMPLE_BLEND)
        assert cercano.cache_key != mezcla.cache_key
        assert FrameJob.make(1, grises, 0.15, sampling=SAMPLE_NEAREST).cache_key == cercano.cache_key
        assert servidor.wait_for([cercano, mezcla], 10)
        assert _gris(servidor.get(cercano)) == pytest.approx(12, abs=2)
        assert _gris(servidor.get(mezcla)) == pytest.approx(18, abs=2)
    finally:
        servidor.close()


def test_el_render_usa_el_muestreo_del_clip(grises):
    from vortex_studio.ui.renderer import SequenceRenderer

    clip = Clip(grises, 0.0, 4.0, speed=0.25, interpolation=SAMPLE_BLEND)
    secuencia = Sequence.default()
    secuencia.track_named("V1").add(clip)
    render = SequenceRenderer(secuencia)
    # 0.6 s de pista a 0.25× son 0.15 s de material: entre el cuadro 1 y el 2.
    assert _gris(render.frame_of(clip, 0.6)) == pytest.approx(18, abs=2)
    clip.interpolation = SAMPLE_NEAREST
    assert _gris(render.frame_of(clip, 0.6)) == pytest.approx(12, abs=2)
    render.close()


def test_un_muestreo_desconocido_en_el_archivo_vuelve_al_cercano():
    from vortex_studio.model.serialize import item_from_dict

    clip = item_from_dict({"tipo": "clip", "source": "a.mp4", "start": 0, "duration": 1,
                           "interpolation": "Magia"})
    assert clip.interpolation == SAMPLE_NEAREST
    assert item_from_dict({"tipo": "clip", "source": "a.mp4", "start": 0, "duration": 1,
                           "interpolation": SAMPLE_FLOW}).interpolation == SAMPLE_FLOW


def test_la_camara_lenta_con_intermedios_marca_la_zona_pesada():
    from vortex_studio.model import render_zones

    secuencia = Sequence.default()
    clip = secuencia.track_named("V1").add(Clip("a.mp4", 0.0, 2.0, speed=0.5))
    assert render_zones.level_of(secuencia, 0, 2) == render_zones.LIGHT
    clip.interpolation = SAMPLE_BLEND
    assert render_zones.level_of(secuencia, 0, 2) == render_zones.HEAVY
    clip.speed = 1.0
    assert render_zones.level_of(secuencia, 0, 2) == render_zones.NONE


# --- ventana y panel ----------------------------------------------------------------------------

def test_el_menu_pone_los_cuadros_intermedios_y_se_deshace(ventana, grises):
    clip = ventana.sequence.track_named("V1").add(Clip(grises, 0.0, 4.0, speed=0.25))
    ventana._commit("Poner clip")
    ventana.timeline.select(clip)
    assert ventana.set_interpolation(SAMPLE_BLEND)
    assert clip.interpolation == SAMPLE_BLEND
    ventana.undo()
    assert ventana.sequence.track_named("V1").clips[0].interpolation == SAMPLE_NEAREST


def test_los_cuadros_intermedios_respetan_el_bloqueo_y_los_valores(ventana, grises):
    clip = ventana.sequence.track_named("V1").add(Clip(grises, 0.0, 4.0))
    ventana.timeline.select(clip)
    assert not ventana.set_interpolation("Magia")
    ventana.sequence.track_named("V1").locked = True
    assert not ventana.set_interpolation(SAMPLE_FLOW)
    assert clip.interpolation == SAMPLE_NEAREST


def test_el_panel_de_clip_cambia_los_cuadros_intermedios(ventana, grises):
    clip = ventana.sequence.track_named("V1").add(Clip(grises, 0.0, 4.0, speed=0.5))
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    panel = ventana.clip_panel
    assert panel._interp.isEnabled()
    panel._interp.setCurrentText(SAMPLE_FLOW)
    assert clip.interpolation == SAMPLE_FLOW
    assert ventana.history.undo_label.startswith("Cuadros intermedios")


def test_el_preview_con_mezcla_se_ve_como_el_archivo(ventana, grises):
    from vortex_studio.ui.renderer import SequenceRenderer

    ventana.sequence.width, ventana.sequence.height = 64, 36
    clip = ventana.sequence.track_named("V1").add(
        Clip(grises, 0.0, 4.0, speed=0.25, interpolation=SAMPLE_BLEND))
    ventana._commit("prueba")
    ventana._scrubbed(0.6)
    ventana._settle_preview()
    preview = ventana.preview.current_image()
    archivo = SequenceRenderer(ventana.sequence).compose(0.6, 64, 36)
    assert abs(preview.pixelColor(32, 18).red() - archivo.pixelColor(32, 18).red()) <= 2
    assert archivo.pixelColor(32, 18).red() == pytest.approx(18, abs=3)
