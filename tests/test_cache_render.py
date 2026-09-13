"""Caché de render por zonas en la ventana."""

import av
import pytest
from PySide6.QtGui import QColor

from vortex_studio.model.render_zones import HEAVY
from vortex_studio.ui import render_cache


@pytest.fixture(autouse=True)
def cache_limpia():
    render_cache.clear_cache()
    yield
    render_cache.clear_cache()


def pesada(ventana, media):
    ventana._place_video(media["gris"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    clip.color.exposure = 100
    ventana._commit("exposición")
    return clip


def test_la_barra_marca_rojo_lo_pesado(ventana, media):
    pesada(ventana, media)
    assert ventana.timeline.render_bar == [(0.0, 2.0, HEAVY)]


def test_renderizar_la_zona_la_pone_en_verde_y_escribe_el_archivo(ventana, media):
    pesada(ventana, media)
    assert ventana.render_zones() == 1
    assert ventana.cache_worker.wait(60)
    ventana._cache_finished(1)
    zona = ventana.zones()[0]
    archivo = render_cache.cached_file(zona.signature)
    assert archivo.exists()
    with av.open(str(archivo)) as c:
        assert float(c.duration / av.time_base) == pytest.approx(2.0, abs=0.15)
    assert ventana.timeline.render_bar == [(0.0, 2.0, "listo")]


def test_el_preview_lee_de_la_cache_y_se_ve_igual(ventana, media):
    pesada(ventana, media)
    ventana._seek(0.5)
    ventana._settle_preview()
    compuesto = QColor(ventana.preview.current_image().pixel(80, 60)).lightness()
    ventana.render_zones()
    ventana.cache_worker.wait(60)
    ventana._cache_finished(1)
    ventana._seek(0.5)
    zona = ventana.zones()[0]
    assert ventana._showing_cache == zona.signature
    import time
    fin = time.monotonic() + 10
    while time.monotonic() < fin and not ventana.preview._layers:
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        ventana._render(0.5)
        time.sleep(0.02)
    capa = ventana.preview._layers[0]
    from vortex_studio.ui.compositor import compose
    desde_cache = QColor(compose(160, 120, [capa], [], []).pixel(80, 60)).lightness()
    assert desde_cache == pytest.approx(compuesto, abs=6)


def test_cambiar_algo_invalida_la_zona(ventana, media):
    clip = pesada(ventana, media)
    ventana.render_zones()
    ventana.cache_worker.wait(60)
    ventana._cache_finished(1)
    assert ventana.timeline.render_bar[0][2] == "listo"
    clip.color.exposure = 150
    ventana._commit("más exposición")
    assert ventana.timeline.render_bar == [(0.0, 2.0, HEAVY)]
    ventana._seek(0.5)
    assert ventana._showing_cache is None


def test_lo_ligero_no_se_renderiza_y_borrar_la_cache(ventana, media):
    ventana._place_video(media["gris"])
    assert ventana.render_zones() == 0
    assert "No hay zonas" in ventana.statusBar().currentMessage()
    pesada_clip = ventana.sequence.video_tracks()[-1].clips[0]
    pesada_clip.color.saturation = 0
    ventana._commit("gris")
    ventana.render_zones()
    ventana.cache_worker.wait(60)
    assert ventana.clear_render_cache() == 1
    assert ventana.timeline.render_bar == [(0.0, 2.0, HEAVY)]


def test_el_atajo_esta_en_el_mapa(ventana):
    assert ventana._actions["reproducir.renderizar"].shortcut().toString() == "Return"
