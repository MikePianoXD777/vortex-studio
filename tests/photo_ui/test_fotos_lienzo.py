"""El lienzo con eventos de ratón y teclado sintetizados."""

import math

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt

from ayudas import (arrastrar, asa, asa_giro, centro, clic, doble_clic, esperar, foto_de_prueba,
                    mover, presionar, rueda, soltar, tecla)
from vortex_studio.photo.document import KIND_IMAGE, KIND_SHAPE, KIND_TEXT
from vortex_studio.ui.photo import geometry as geo

SHIFT = Qt.ShiftModifier
CTRL = Qt.ControlModifier


@pytest.fixture
def img(s):
    """Una foto de 400×300 en el centro del lienzo de 1080×1080."""
    capa = s.add_image(foto_de_prueba(400, 300))
    s.clear_selection()
    return capa


@pytest.fixture
def dos(s):
    """Dos fotos separadas: a la izquierda y a la derecha."""
    a = s.add_image(foto_de_prueba(200, 200), at=(250, 540))
    b = s.add_image(foto_de_prueba(200, 200), at=(800, 540))
    s.clear_selection()
    return a, b


# --- seleccionar ----------------------------------------------------------------

def test_clic_selecciona_la_capa(s, lienzo, img):
    clic(lienzo, 540, 540)
    assert s.selection == [img.id]


def test_clic_en_el_vacio_deselecciona(s, lienzo, img):
    clic(lienzo, 540, 540)
    clic(lienzo, 50, 50)
    assert s.selection == []


def test_clic_toma_la_capa_de_arriba(s, lienzo, img):
    forma = s.add_shape("rect")
    s.clear_selection()
    clic(lienzo, 540, 540)
    assert s.selection == [forma.id]


def test_shift_suma_y_quita_de_la_seleccion(s, lienzo, dos):
    a, b = dos
    clic(lienzo, 250, 540)
    clic(lienzo, 800, 540, SHIFT)
    assert set(s.selection) == {a.id, b.id}
    clic(lienzo, 250, 540, SHIFT)
    assert s.selection == [b.id]


def test_rectangulo_de_seleccion_en_vacio(s, lienzo, dos):
    a, b = dos
    arrastrar(lienzo, (50, 400), (1000, 700))
    assert set(s.selection) == {a.id, b.id}
    arrastrar(lienzo, (50, 400), (400, 700))
    assert s.selection == [a.id]


def test_rectangulo_con_shift_conserva_lo_anterior(s, lienzo, dos):
    a, b = dos
    clic(lienzo, 800, 540)
    arrastrar(lienzo, (50, 400), (400, 700), SHIFT)
    assert set(s.selection) == {a.id, b.id}


def test_seleccionar_no_toca_el_historial(s, lienzo, img):
    n = len(s.history)
    clic(lienzo, 540, 540)
    clic(lienzo, 50, 50)
    assert len(s.history) == n
    assert not s.history.can_redo


def test_capa_oculta_no_se_selecciona_con_clic(s, lienzo, img):
    s.set_visible(img.id, False)
    clic(lienzo, 540, 540)
    assert s.selection == []


# --- mover -------------------------------------------------------------------------

def test_arrastrar_mueve_la_capa_y_deja_un_solo_paso(s, lienzo, img):
    pasos = len(s.history)
    arrastrar(lienzo, (540, 540), (640, 590))
    assert centro(img) == pytest.approx((640, 590))
    assert len(s.history) == pasos + 1
    assert s.history.undo_label == "Mover"


def test_un_clic_sin_arrastrar_no_mueve_ni_guarda_paso(s, lienzo, img):
    pasos = len(s.history)
    presionar(lienzo, 540, 540)
    mover(lienzo, 541, 541)          # menos que el umbral
    soltar(lienzo, 541, 541)
    assert centro(img) == (540, 540)
    assert len(s.history) == pasos


def test_deshacer_y_rehacer_el_movimiento(s, lienzo, img):
    arrastrar(lienzo, (540, 540), (600, 600), CTRL)
    s.undo()
    assert centro(s.doc.layer(img.id)) == (540, 540)
    s.redo()
    assert centro(s.doc.layer(img.id)) == pytest.approx((600, 600))


def test_una_capa_bloqueada_no_se_mueve(s, lienzo, img):
    s.set_locked(img.id, True)
    pasos = len(s.history)
    arrastrar(lienzo, (540, 540), (700, 700))
    assert centro(s.doc.layer(img.id)) == (540, 540)
    assert s.selection == [img.id]            # se puede seleccionar
    assert len(s.history) == pasos


def test_las_capas_bloqueadas_no_muestran_asas(s, lienzo, img):
    s.set_locked(img.id, True)
    s.select([img.id])
    assert lienzo.hit_handle(*[lienzo.to_screen(*asa(lienzo, "se")).x(),
                               lienzo.to_screen(*asa(lienzo, "se")).y()]) is None


def test_mover_con_shift_se_queda_en_un_eje(s, lienzo, img):
    # Shift se aprieta durante el arrastre (al pulsar, Shift sumaría a la selección).
    presionar(lienzo, 540, 540)
    mover(lienzo, 600, 550, SHIFT | CTRL)
    mover(lienzo, 700, 560, SHIFT | CTRL)
    soltar(lienzo, 700, 560, SHIFT | CTRL)
    assert centro(s.doc.layer(img.id)) == pytest.approx((700, 540))


def test_mover_varias_juntas(s, lienzo, dos):
    a, b = dos
    s.select([a.id, b.id])
    arrastrar(lienzo, (250, 540), (270, 600), CTRL)
    assert centro(a) == pytest.approx((270, 600))
    assert centro(b) == pytest.approx((820, 600))
    assert s.history.undo_label == "Mover"


def test_mover_una_de_la_seleccion_mueve_toda_la_seleccion(s, lienzo, dos):
    a, b = dos
    s.select([a.id, b.id])
    arrastrar(lienzo, (800, 540), (800, 640), CTRL)
    assert a.transform.cy == pytest.approx(640)


def test_arrastrar_una_no_seleccionada_cambia_la_seleccion(s, lienzo, dos):
    a, b = dos
    s.select([a.id])
    arrastrar(lienzo, (800, 540), (800, 600), CTRL)
    assert s.selection == [b.id]
    assert a.transform.cy == 540


# --- guías con imán ----------------------------------------------------------------------

def test_el_iman_pega_el_centro_al_centro_del_lienzo(s, lienzo, img):
    clic(lienzo, 540, 540)
    presionar(lienzo, 540, 540)
    mover(lienzo, 540, 560)
    mover(lienzo, 545, 760)            # +5 en x: dentro del imán
    assert lienzo._guides, "debería mostrar una guía"
    assert any(g[0] == "v" for g in lienzo._guides)
    soltar(lienzo, 545, 760)
    assert img.transform.cx == pytest.approx(540)
    assert lienzo._guides == []


def test_ctrl_apaga_el_iman(s, lienzo, img):
    arrastrar(lienzo, (540, 540), (545, 640), CTRL)
    assert img.transform.cx == pytest.approx(545)


def test_lejos_de_una_guia_no_se_pega(s, lienzo, img):
    arrastrar(lienzo, (540, 540), (580, 640))
    assert img.transform.cx == pytest.approx(580)


def test_el_iman_alinea_con_el_borde_de_otra_capa(s, lienzo, dos):
    a, b = dos
    # Borde derecho de a = 350; se lleva el borde izquierdo de b (700) hacia 350+ (cerca de 355).
    s.select([b.id])
    presionar(lienzo, 800, 540)
    mover(lienzo, 800, 700)
    mover(lienzo, 800 - 345, 700)       # el borde izquierdo de b queda en 355: cerca de 350
    soltar(lienzo, 800 - 345, 700)
    assert b.transform.cx - b.transform.width / 2 == pytest.approx(350)


def test_la_guia_se_muestra_con_su_color(s, lienzo, img):
    clic(lienzo, 540, 540)
    presionar(lienzo, 540, 540)
    mover(lienzo, 540, 700)
    tipos = {g[4] for g in lienzo._guides}
    assert "lienzo" in tipos
    soltar(lienzo, 540, 700)


# --- flechas ---------------------------------------------------------------------------------

def test_flechas_empujan_un_pixel(s, lienzo, img):
    s.select([img.id])
    tecla(lienzo, Qt.Key_Right)
    tecla(lienzo, Qt.Key_Down)
    assert centro(img) == (541, 541)
    tecla(lienzo, Qt.Key_Left)
    tecla(lienzo, Qt.Key_Up)
    assert centro(img) == (540, 540)


def test_flechas_con_shift_empujan_diez(s, lienzo, img):
    s.select([img.id])
    tecla(lienzo, Qt.Key_Right, SHIFT)
    assert centro(img) == (550, 540)


def test_flechas_sin_seleccion_no_hacen_nada(s, lienzo, img):
    pasos = len(s.history)
    tecla(lienzo, Qt.Key_Right)
    assert len(s.history) == pasos and centro(img) == (540, 540)


def test_flechas_no_mueven_una_capa_bloqueada(s, lienzo, img):
    s.set_locked(img.id, True)
    s.select([img.id])
    pasos = len(s.history)
    tecla(lienzo, Qt.Key_Right)
    assert centro(s.doc.layer(img.id)) == (540, 540) and len(s.history) == pasos


def test_flechas_se_deshacen_de_a_una(s, lienzo, img):
    s.select([img.id])
    tecla(lienzo, Qt.Key_Right)
    tecla(lienzo, Qt.Key_Right)
    s.undo()
    assert centro(s.doc.layer(img.id)) == (541, 540)


# --- escalar --------------------------------------------------------------------------------------

OPUESTA = {"nw": "se", "n": "s", "ne": "sw", "e": "w", "se": "nw", "s": "n", "sw": "ne", "w": "e"}


@pytest.mark.parametrize("nombre", list(geo.HANDLES))
def test_escalar_una_foto_por_cada_asa(s, lienzo, img, nombre):
    s.select([img.id])
    fija0 = asa(lienzo, OPUESTA[nombre])
    hx, hy = geo.HANDLES[nombre]
    x, y = asa(lienzo, nombre)
    arrastrar(lienzo, (x, y), (x + hx * 60, y + hy * 45), CTRL)
    capa = s.doc.layer(img.id)
    fija1 = asa(lienzo, OPUESTA[nombre])
    assert fija1 == pytest.approx(fija0, abs=1e-6)
    assert capa.transform.width > 400 or capa.transform.height > 300
    assert s.history.undo_label == "Cambiar tamaño"


@pytest.mark.parametrize("nombre", ["nw", "ne", "se", "sw"])
def test_las_esquinas_de_una_foto_son_proporcionales(s, lienzo, img, nombre):
    s.select([img.id])
    hx, hy = geo.HANDLES[nombre]
    x, y = asa(lienzo, nombre)
    arrastrar(lienzo, (x, y), (x + hx * 80, y + hy * 10))
    t = s.doc.layer(img.id).transform
    assert t.width / t.height == pytest.approx(400 / 300, rel=1e-6)
    assert t.width > 400


@pytest.mark.parametrize("nombre", ["nw", "ne", "se", "sw"])
def test_shift_libera_la_proporcion_de_una_foto(s, lienzo, img, nombre):
    s.select([img.id])
    hx, hy = geo.HANDLES[nombre]
    x, y = asa(lienzo, nombre)
    arrastrar(lienzo, (x, y), (x + hx * 80, y + hy * 10), SHIFT)
    t = s.doc.layer(img.id).transform
    assert t.width / t.height != pytest.approx(400 / 300, rel=1e-3)
    assert t.width == pytest.approx(480)
    assert t.height == pytest.approx(310)


@pytest.mark.parametrize("nombre", ["e", "w"])
def test_asas_de_lado_solo_cambian_el_ancho(s, lienzo, img, nombre):
    s.select([img.id])
    hx, _ = geo.HANDLES[nombre]
    x, y = asa(lienzo, nombre)
    arrastrar(lienzo, (x, y), (x + hx * 50, y))
    t = s.doc.layer(img.id).transform
    assert t.width == pytest.approx(450) and t.height == pytest.approx(300)


def test_escalar_con_deshacer(s, lienzo, img):
    s.select([img.id])
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x + 100, y + 75))
    s.undo()
    t = s.doc.layer(img.id).transform
    assert (t.width, t.height) == (400, 300)


def test_no_se_pasa_del_otro_lado_ni_se_hace_negativa(s, lienzo, img):
    s.select([img.id])
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x - 2000, y - 2000), CTRL)
    t = s.doc.layer(img.id).transform
    assert t.width >= geo.MIN_SIZE and t.height >= geo.MIN_SIZE


def test_escalar_un_texto_por_la_esquina_cambia_el_tamano_de_letra(s, lienzo):
    t = s.add_text(0)
    fs = t.font_size
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x + 100, y + 20))
    assert s.doc.layer(t.id).font_size > fs
    assert s.history.undo_label == "Cambiar tamaño"


def test_el_texto_solo_tiene_asas_de_esquina_y_ancho(s, lienzo):
    s.add_text(0)
    assert set(lienzo.handle_points(s.selected())) == {"nw", "ne", "se", "sw", "e", "w"}


def test_el_asa_de_ancho_de_un_texto_no_cambia_la_letra(s, lienzo):
    t = s.add_text(2)
    fs = t.font_size
    ancho = t.transform.width
    x, y = asa(lienzo, "e")
    arrastrar(lienzo, (x, y), (x - 80, y))
    capa = s.doc.layer(t.id)
    assert capa.font_size == fs
    assert capa.transform.width == pytest.approx(ancho - 80)


def test_una_forma_es_libre_y_con_shift_proporcional(s, lienzo):
    f = s.add_shape("rect")
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x + 100, y + 20))
    t = s.doc.layer(f.id).transform
    assert t.width != pytest.approx(t.height)
    x, y = asa(lienzo, "se")
    ancho, alto = t.width, t.height
    arrastrar(lienzo, (x, y), (x + 100, y + 5), SHIFT)
    t = s.doc.layer(f.id).transform
    assert t.width / t.height == pytest.approx(ancho / alto, rel=1e-6)


def test_escalar_una_foto_girada(s, lienzo, img):
    img.transform.rotation = 30
    s.commit("Girar")
    s.select([img.id])
    fija = asa(lienzo, "nw")
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x + 60, y + 60), CTRL)
    assert asa(lienzo, "nw") == pytest.approx(fija, abs=1e-6)
    assert s.doc.layer(img.id).transform.rotation == 30


def test_escalar_varias_a_la_vez(s, lienzo, dos):
    a, b = dos
    s.select([a.id, b.id])
    caja0 = geo.bbox([a.transform, b.transform])
    x, y = asa(lienzo, "se")
    arrastrar(lienzo, (x, y), (x + 100, y + 100))
    caja1 = geo.bbox([a.transform, b.transform])
    assert caja1[0] == pytest.approx(caja0[0]) and caja1[1] == pytest.approx(caja0[1])
    assert caja1[2] > caja0[2]
    assert a.transform.width == pytest.approx(b.transform.width)
    assert s.history.undo_label == "Cambiar tamaño"


# --- girar ---------------------------------------------------------------------------------------------

def test_girar_con_el_asa(s, lienzo, img):
    s.select([img.id])
    cx, cy = centro(img)
    x, y = asa_giro(lienzo)
    d = cy - y
    arrastrar(lienzo, (x, y), (cx + d, cy))            # de arriba a la derecha: +90°
    assert s.doc.layer(img.id).transform.rotation == pytest.approx(90, abs=1e-6)
    assert s.history.undo_label == "Girar"


def test_girar_con_shift_va_de_15_en_15(s, lienzo, img):
    s.select([img.id])
    cx, cy = centro(img)
    x, y = asa_giro(lienzo)
    d = cy - y
    ang = math.radians(-90 + 25)
    arrastrar(lienzo, (x, y), (cx + d * math.cos(ang), cy + d * math.sin(ang)), SHIFT)
    r = s.doc.layer(img.id).transform.rotation
    assert r % 15 == pytest.approx(0, abs=1e-6) and r == pytest.approx(30)


def test_girar_sin_shift_es_continuo(s, lienzo, img):
    s.select([img.id])
    cx, cy = centro(img)
    x, y = asa_giro(lienzo)
    d = cy - y
    ang = math.radians(-90 + 22)
    arrastrar(lienzo, (x, y), (cx + d * math.cos(ang), cy + d * math.sin(ang)))
    assert s.doc.layer(img.id).transform.rotation == pytest.approx(22, abs=1e-6)


def test_girar_se_deshace(s, lienzo, img):
    s.select([img.id])
    cx, cy = centro(img)
    x, y = asa_giro(lienzo)
    arrastrar(lienzo, (x, y), (cx + 200, cy))
    s.undo()
    assert s.doc.layer(img.id).transform.rotation == 0


def test_girar_varias_alrededor_del_centro_del_conjunto(s, lienzo, dos):
    a, b = dos
    s.select([a.id, b.id])
    caja = geo.selection_box([a.transform, b.transform])
    x, y = asa_giro(lienzo)
    d = caja.cy - y
    arrastrar(lienzo, (x, y), (caja.cx + d, caja.cy))
    assert a.transform.rotation == pytest.approx(90) and b.transform.rotation == pytest.approx(90)
    assert (a.transform.cx, a.transform.cy) == pytest.approx((caja.cx, caja.cy - 275), abs=1e-6)


def test_girar_una_capa_bloqueada_no_hace_nada(s, lienzo, img):
    s.set_locked(img.id, True)
    s.select([img.id])
    assert lienzo.hit_handle(*[lienzo.to_screen(*asa_giro(lienzo)).x(),
                               lienzo.to_screen(*asa_giro(lienzo)).y()]) is None


def test_el_asa_se_detecta_bajo_el_puntero(s, lienzo, img):
    s.select([img.id])
    for nombre in geo.HANDLES:
        pt = lienzo.to_screen(*asa(lienzo, nombre))
        assert lienzo.hit_handle(pt.x(), pt.y()) == nombre
    pt = lienzo.to_screen(*asa_giro(lienzo))
    assert lienzo.hit_handle(pt.x(), pt.y()) == "rotate"
    assert lienzo.hit_handle(5, 5) is None


# --- zoom y desplazamiento ---------------------------------------------------------------------------------

def test_zoom_con_ctrl_rueda_se_ancla_al_puntero(s, lienzo, img):
    px, py = 300.0, 700.0
    antes = lienzo.to_screen(px, py)
    rueda(lienzo, px, py, 240, CTRL)
    assert lienzo.zoom > 0.5 or lienzo.zoom > 0.4
    despues = lienzo.to_screen(px, py)
    assert (despues.x(), despues.y()) == pytest.approx((antes.x(), antes.y()), abs=1e-6)


def test_zoom_se_aleja_con_la_rueda_hacia_abajo(s, lienzo):
    z = lienzo.zoom
    rueda(lienzo, 540, 540, -240, CTRL)
    assert lienzo.zoom < z


def test_zoom_extremo_se_limita(s, lienzo):
    lienzo.set_zoom(100000)
    assert lienzo.zoom == 32.0
    lienzo.set_zoom(0)
    assert lienzo.zoom == 0.01
    lienzo.set_zoom(-5)
    assert lienzo.zoom == 0.01
    lienzo.flush()           # y a ese zoom todavía dibuja
    assert lienzo._frame is not None


def test_zoom_100_y_ajustar(s, lienzo):
    lienzo.zoom_100()
    assert lienzo.zoom == 1.0
    lienzo.fit()
    assert lienzo.zoom < 1.0
    r = lienzo.canvas_rect()
    assert r.width() <= lienzo.width() and r.height() <= lienzo.height()
    assert r.center().x() == pytest.approx(lienzo.width() / 2, abs=1)


def test_zoom_mas_y_menos(s, lienzo):
    z = lienzo.zoom
    lienzo.zoom_in()
    assert lienzo.zoom == pytest.approx(z * 1.25)
    lienzo.zoom_out()
    assert lienzo.zoom == pytest.approx(z)


def test_la_rueda_sola_desplaza(s, lienzo):
    lienzo.zoom_100()
    o = lienzo.origin
    rueda(lienzo, 540, 540, -120)
    assert lienzo.origin.y() == pytest.approx(o.y() - 60)
    rueda(lienzo, 540, 540, 120, SHIFT)
    assert lienzo.origin.x() == pytest.approx(o.x() + 60)


def test_espacio_y_arrastrar_desplaza(s, lienzo, img):
    lienzo.zoom_100()
    o = lienzo.origin
    tecla(lienzo, Qt.Key_Space)
    pasos = len(s.history)
    presionar(lienzo, 540, 540)
    mover(lienzo, 540, 540)
    ev = lienzo.to_screen(540, 540)
    lienzo.mouseMoveEvent(__import__("ayudas")._ev(QEvent.MouseMove, ev + QPointF(40, 25), Qt.NoButton,
                                                   Qt.LeftButton))
    lienzo.mouseReleaseEvent(__import__("ayudas")._ev(QEvent.MouseButtonRelease, ev + QPointF(40, 25),
                                                      Qt.LeftButton, Qt.NoButton))
    tecla(lienzo, Qt.Key_Space, tipo=QEvent.KeyRelease)
    assert lienzo.origin.x() == pytest.approx(o.x() + 40)
    assert lienzo.origin.y() == pytest.approx(o.y() + 25)
    assert centro(img) == (540, 540)             # no movió la capa
    assert len(s.history) == pasos


def test_no_se_pierde_el_lienzo_al_desplazar(s, lienzo):
    for _ in range(200):
        rueda(lienzo, 540, 540, 120)
    r = lienzo.canvas_rect()
    assert r.bottom() >= 0
    assert r.top() <= lienzo.height()


def test_al_cambiar_el_tamano_de_la_ventana_se_reajusta(foto, lienzo, qapp):
    foto.resize(1500, 900)
    esperar(qapp, 3)
    r = lienzo.canvas_rect()
    assert r.center().x() == pytest.approx(lienzo.width() / 2, abs=2)
    assert r.width() <= lienzo.width()


def test_lienzo_enorme(s, lienzo):
    s.new_document(16000, 16000)
    lienzo.flush()
    assert lienzo.zoom < 0.1
    lienzo.zoom_100()
    lienzo.flush()
    # A zoom 100 % de 16000² el motor no recibe 256 MP: se limita la escala de dibujo.
    assert lienzo._frame.width() * lienzo._frame.height() <= 6_100_000
    assert lienzo.last_render_scale < 1.0


def test_lienzo_diminuto(s, lienzo):
    s.new_document(1, 1)
    lienzo.flush()
    assert lienzo._frame is not None
    s.add_shape("ellipse")
    lienzo.flush()


def test_la_lupa_a_zoom_alto_dibuja_con_escala_limitada(s, lienzo, img):
    lienzo.set_zoom(32.0)
    lienzo.flush()
    assert lienzo.last_render_scale <= 32.0
    assert lienzo._frame is not None
