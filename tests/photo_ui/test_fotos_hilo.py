"""El lienzo dibuja en un hilo: sin carreras, la última imagen gana y nada se traba."""

import threading
import time

import numpy as np
import pytest

from ayudas import foto_de_prueba


def _espiar(s, retraso=0.0):
    """Cambia `renderer.render` por uno que anota el hilo, el documento y espera `retraso`."""
    original = s.renderer.render
    visto = []

    def espia(doc, scale=1.0, **kw):
        visto.append({"hilo": threading.current_thread(), "doc": doc, "candado": s.render_lock._is_owned()})
        if retraso:
            time.sleep(retraso)
        return original(doc, scale, **kw)
    s.renderer.render = espia
    return visto


def _color_central(lienzo):
    f = lienzo._frame
    c = f.pixelColor(f.width() // 2, f.height() // 2)
    return c.red(), c.green(), c.blue()


def test_el_dibujo_se_hace_fuera_del_hilo_de_la_interfaz(s, lienzo):
    visto = _espiar(s)
    s.touch()
    lienzo.flush()
    assert visto
    assert all(v["hilo"] is not threading.main_thread() for v in visto)


def test_el_hilo_recibe_una_copia_del_documento_y_toma_el_candado(s, lienzo):
    visto = _espiar(s)
    s.touch()
    lienzo.flush()
    assert all(v["doc"] is not s.doc for v in visto)
    assert all(v["candado"] for v in visto)


def test_la_ultima_imagen_gana_con_cambios_rapidos(s, lienzo, qapp):
    s.set_background("#000000")
    lienzo.flush()
    _espiar(s, retraso=0.03)
    for i in range(12):                              # doce cambios seguidos, sin esperar
        s.doc.background = f"#{i * 20:02x}{i * 20:02x}{i * 20:02x}"
        s.touch()
        qapp.processEvents()
        time.sleep(0.005)
    final = s.doc.background
    lienzo.flush()
    esperado = int(final[1:3], 16)
    r, g, b = _color_central(lienzo)
    assert (r, g, b) == (esperado, esperado, esperado)


def test_mientras_se_dibuja_se_ve_la_imagen_anterior(s, lienzo):
    s.set_background("#ff0000")
    lienzo.flush()
    antes = lienzo._frame
    assert _color_central(lienzo)[0] == 255
    _espiar(s, retraso=0.25)
    s.doc.background = "#0000ff"
    s.touch()
    lienzo._render()                                 # lanza el hilo sin esperarlo
    assert lienzo._running
    assert lienzo._frame is antes                    # nada cambió todavía: se sigue viendo la anterior
    lienzo.flush()
    assert _color_central(lienzo) == (0, 0, 255)


def test_un_resultado_de_un_documento_viejo_se_descarta(s, lienzo):
    s.set_background("#ff0000")
    lienzo.flush()
    _espiar(s, retraso=0.2)
    s.touch()
    lienzo._render()                                  # dibujo en curso del diseño viejo
    s.new_document(300, 300)                          # se reemplaza el documento
    s.doc.background = "#00ff00"
    lienzo.flush()
    assert lienzo._frame.width() > 0
    r, g, b = _color_central(lienzo)
    assert (r, g, b) == (0, 255, 0)


def test_pedidos_durante_un_dibujo_se_juntan_en_uno_solo(s, lienzo, qapp):
    lienzo.flush()
    visto = _espiar(s, retraso=0.1)
    s.touch()
    lienzo._render()
    for _ in range(20):                               # llegan mientras el hilo trabaja
        s.touch()
        lienzo.request_render()
        qapp.processEvents()
    lienzo.flush()
    assert len(visto) <= 3


def test_flush_espera_a_que_termine_todo(s, lienzo):
    _espiar(s, retraso=0.05)
    s.touch()
    lienzo.flush()
    assert not lienzo._running and not lienzo._again


def test_un_error_en_el_hilo_se_avisa_y_el_lienzo_sigue(s, lienzo):
    mensajes = []
    s.message.connect(mensajes.append)

    def malo(*a, **k):
        raise RuntimeError("falla")
    original = s.renderer.render
    s.renderer.render = malo
    s.touch()
    lienzo.flush()
    assert any("No se pudo dibujar" in m for m in mensajes)
    s.renderer.render = original
    s.touch()
    lienzo.flush()
    assert lienzo._frame is not None


def test_muchas_ediciones_con_el_hilo_trabajando_no_dan_errores(s, lienzo, qapp):
    img = s.add_image(foto_de_prueba(600, 400))
    mensajes = []
    s.message.connect(mensajes.append)
    for i in range(40):
        img.transform.cx += 3
        s.touch()
        if i % 7 == 0:
            s.commit("Mover")
        qapp.processEvents()
    lienzo.flush()
    assert not [m for m in mensajes if "No se pudo dibujar" in m]
    assert not lienzo._running


def test_los_assets_soltados_mientras_se_dibuja_no_dejan_error(s, lienzo, qapp):
    s.new_document(256, 256)
    s.set_tool("brush")
    mensajes = []
    s.message.connect(mensajes.append)
    _espiar(s, retraso=0.01)
    for i in range(30):
        s.paint_stroke([(10 + i * 5, 10), (10 + i * 5, 200)])
        qapp.processEvents()
    lienzo.flush()
    assert not [m for m in mensajes if "No se pudo dibujar" in m]
