"""El dibujo no bloquea: se junta, usa escala reducida al arrastrar y no se repite sin motivo."""

import pytest
from PySide6.QtWidgets import QApplication

from ayudas import clic, foto_de_prueba, mover, presionar, soltar


@pytest.fixture
def img(s, lienzo):
    c = s.add_image(foto_de_prueba(400, 300))
    lienzo.flush()
    return c


def test_muchos_cambios_se_juntan_en_un_dibujo(s, lienzo, img):
    lienzo.flush()
    r0 = lienzo.render_count
    for _ in range(50):
        s.touch()
    lienzo.flush()
    assert lienzo.render_count == r0 + 1


def test_el_temporizador_es_de_un_disparo(s, lienzo, img):
    lienzo.flush()
    s.touch()
    assert lienzo._timer.isSingleShot() and lienzo._timer.isActive()
    s.touch()
    lienzo.flush()
    assert not lienzo._timer.isActive()


def test_mientras_se_arrastra_usa_escala_reducida_y_al_soltar_la_buena(s, lienzo, img):
    clic(lienzo, 540, 540)
    lienzo.flush()
    buena = lienzo.last_render_scale
    presionar(lienzo, 540, 540)
    mover(lienzo, 560, 540)
    mover(lienzo, 600, 560)
    lienzo.flush()
    assert lienzo.last_render_scale < buena
    soltar(lienzo, 600, 560)
    lienzo.flush()
    assert lienzo.last_render_scale == pytest.approx(buena)


def test_seleccionar_y_pasar_el_raton_no_redibuja(s, lienzo, img):
    lienzo.flush()
    r0 = lienzo.render_count
    clic(lienzo, 540, 540)
    lienzo.flush()
    assert lienzo.render_count == r0


def test_el_dibujo_es_a_la_escala_de_la_vista(s, lienzo, img):
    lienzo.zoom_100()
    lienzo.flush()
    assert lienzo._frame.width() == pytest.approx(1080 * lienzo.last_render_scale, abs=1)
    lienzo.set_zoom(0.25)
    lienzo._final_render()          # lo que dispara el temporizador al asentarse el zoom
    lienzo.flush()
    assert lienzo._frame.width() == pytest.approx(270, abs=1)


def test_un_dibujo_con_muchas_capas_responde_rapido(s, lienzo):
    import time
    for i in range(12):
        s.add_shape("ellipse", at=(100 + i * 60, 300 + i * 20))
    lienzo.flush()
    t = time.monotonic()
    for _ in range(5):
        s.touch()
        lienzo.flush()
    assert (time.monotonic() - t) / 5 < 0.5        # holgado: solo detecta bloqueos graves


def test_un_error_del_motor_no_tumba_el_lienzo(s, lienzo, img):
    def malo(*a, **k):
        raise RuntimeError("falla")
    original = s.renderer.render
    s.renderer.render = malo
    mensajes = []
    s.message.connect(mensajes.append)
    s.touch()
    lienzo.flush()
    assert any("No se pudo dibujar" in m for m in mensajes)
    s.renderer.render = original
    s.touch()
    lienzo.flush()


def test_el_dibujo_nunca_pide_una_escala_enorme(s, lienzo):
    s.new_document(16000, 16000)
    lienzo.set_zoom(32)
    escalas = []
    original = s.renderer.render

    def espia(doc, scale=1.0, **kw):
        escalas.append(scale)
        return original(doc, scale, **kw)
    s.renderer.render = espia
    lienzo.flush()
    assert escalas and 16000 * 16000 * escalas[0] ** 2 <= 6_100_000
