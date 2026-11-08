"""Modo recortar: proporciones, enderezar, aplicar y cancelar."""

import pytest
from PySide6.QtCore import Qt

from ayudas import arrastrar, centro, clic, doble_clic, foto_de_prueba, tecla
from vortex_studio.ui.photo import geometry as geo


@pytest.fixture
def img(s):
    capa = s.add_image(foto_de_prueba(400, 300))
    return capa


def test_doble_clic_en_una_imagen_entra_a_recortar(s, lienzo, img):
    s.clear_selection()
    doble_clic(lienzo, 540, 540)
    assert lienzo.in_crop()
    assert lienzo.crop_rect() == (-200.0, -150.0, 200.0, 150.0)


def test_la_barra_cambia_en_modo_recortar(foto, s, lienzo, img):
    lienzo.begin_crop()
    assert foto.context.pages.currentWidget() is foto.context.p_crop
    lienzo.cancel_crop()
    assert foto.context.pages.currentWidget() is foto.context.p_image


def test_recortar_a_cuadrado(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    r = lienzo.crop_rect()
    assert r[2] - r[0] == pytest.approx(r[3] - r[1])
    assert lienzo.apply_crop()
    capa = s.doc.layer(img.id)
    assert capa.crop is not None
    assert capa.crop[2] == pytest.approx(capa.crop[3])
    assert capa.transform.width == pytest.approx(capa.transform.height)
    assert s.history.undo_label == "Recortar"
    assert not lienzo.in_crop()


@pytest.mark.parametrize("ratio", [1.0, 4 / 5, 9 / 16, 16 / 9])
def test_cada_proporcion_se_respeta_al_aplicar(s, lienzo, img, ratio):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(ratio)
    lienzo.apply_crop()
    t = s.doc.layer(img.id).transform
    assert t.width / t.height == pytest.approx(ratio, rel=1e-6)


def test_deshacer_el_recorte(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    lienzo.apply_crop()
    s.undo()
    capa = s.doc.layer(img.id)
    assert capa.crop is None
    assert (capa.transform.width, capa.transform.height) == (400, 300)


def test_el_recorte_no_cambia_la_escala_de_lo_que_se_ve(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    lienzo.apply_crop()
    capa = s.doc.layer(img.id)
    # 400×300 a 1 unidad por píxel: el cuadrado recortado mide 300×300 píxeles → 300 unidades.
    assert capa.transform.width == pytest.approx(300)
    assert capa.crop[2] == pytest.approx(300)


def test_arrastrar_un_asa_del_recorte(s, lienzo, img):
    lienzo.begin_crop()
    x, y = 540 + 200, 540            # asa derecha (e)
    arrastrar(lienzo, (x, y), (x - 100, y))
    r = lienzo.crop_rect()
    assert r[2] == pytest.approx(100.0)
    lienzo.apply_crop()
    assert s.doc.layer(img.id).crop[2] == pytest.approx(300)


def test_arrastrar_asa_con_proporcion_fija(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    r = lienzo.crop_rect()
    x, y = 540 + r[2], 540 + r[3]
    arrastrar(lienzo, (x, y), (x - 60, y - 10))
    r = lienzo.crop_rect()
    assert r[2] - r[0] == pytest.approx(r[3] - r[1], rel=1e-6)


def test_mover_el_rectangulo_de_recorte(s, lienzo, img):
    lienzo.begin_crop()
    x, y = 540 + 200, 540
    arrastrar(lienzo, (x, y), (x - 100, y))       # achica por la derecha
    arrastrar(lienzo, (540 - 20, 540), (540 - 120, 540))    # lo mueve
    r = lienzo.crop_rect()
    assert r[0] == pytest.approx(-200.0)           # tope izquierdo de la imagen
    assert r[2] - r[0] == pytest.approx(300.0)


def test_el_recorte_no_sale_de_la_imagen(s, lienzo, img):
    lienzo.begin_crop()
    x, y = 540 + 200, 540
    arrastrar(lienzo, (x, y), (x + 500, y))
    assert lienzo.crop_rect()[2] == pytest.approx(200.0)


def test_cancelar_no_cambia_nada(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    lienzo.set_straighten(10)
    n = len(s.history)
    lienzo.cancel_crop()
    capa = s.doc.layer(img.id)
    assert capa.crop is None and capa.transform.rotation == 0
    assert len(s.history) == n


def test_enderezar_gira_la_capa(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_straighten(7.5)
    assert s.doc.layer(img.id).transform.rotation == pytest.approx(7.5)
    assert lienzo.apply_crop()
    assert s.doc.layer(img.id).transform.rotation == pytest.approx(7.5)
    s.undo()
    assert s.doc.layer(img.id).transform.rotation == 0


def test_aplicar_sin_cambios_no_agrega_paso(s, lienzo, img):
    lienzo.begin_crop()
    n = len(s.history)
    assert not lienzo.apply_crop()
    assert len(s.history) == n


def test_enter_aplica_y_escape_cancela(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    tecla(lienzo, Qt.Key_Escape)
    assert not lienzo.in_crop() and s.doc.layer(img.id).crop is None
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    tecla(lienzo, Qt.Key_Return)
    assert s.doc.layer(img.id).crop is not None


def test_la_barra_manda_proporcion_y_enderezar(foto, s, lienzo, img):
    lienzo.begin_crop()
    foto.context.ratio_seg.buttons["1:1"].click()
    r = lienzo.crop_rect()
    assert r[2] - r[0] == pytest.approx(r[3] - r[1])
    foto.context.straighten._slider.setValue(5)
    assert s.doc.layer(img.id).transform.rotation == pytest.approx(5)
    foto.context.btn_crop_ok.click()
    assert not lienzo.in_crop()


def test_recortar_una_capa_bloqueada_no_se_puede(s, lienzo, img):
    s.set_locked(img.id, True)
    s.select([img.id])
    assert not lienzo.begin_crop()


def test_recortar_algo_que_no_es_foto_no_se_puede(s, lienzo):
    s.add_shape("rect")
    assert not lienzo.begin_crop()
    s.add_text(0)
    assert not lienzo.begin_crop()


def test_cambiar_la_seleccion_cancela_el_recorte(s, lienzo, img):
    otra = s.add_shape("rect")
    s.select([img.id])
    lienzo.begin_crop()
    s.select([otra.id])
    assert not lienzo.in_crop()


def test_borrar_la_capa_que_se_recorta(s, lienzo, img):
    lienzo.begin_crop()
    s.delete_selected()
    assert not lienzo.in_crop()
    assert not lienzo.apply_crop()


def test_recortar_una_foto_girada_y_volteada(s, lienzo, img):
    img.transform.rotation = 20
    img.transform.flip_h = True
    s.commit("x")
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    antes = centro(s.doc.layer(img.id))
    lienzo.apply_crop()
    capa = s.doc.layer(img.id)
    assert capa.transform.rotation == pytest.approx(20)
    assert capa.transform.flip_h
    assert capa.crop[2] == pytest.approx(capa.crop[3])


def test_dos_recortes_seguidos(s, lienzo, img):
    lienzo.begin_crop()
    lienzo.set_crop_ratio(1.0)
    lienzo.apply_crop()
    lienzo.begin_crop()
    assert lienzo.crop_rect()[2] - lienzo.crop_rect()[0] == pytest.approx(300)
    lienzo.set_crop_ratio(16 / 9)
    lienzo.apply_crop()
    t = s.doc.layer(img.id).transform
    assert t.width / t.height == pytest.approx(16 / 9, rel=1e-6)
