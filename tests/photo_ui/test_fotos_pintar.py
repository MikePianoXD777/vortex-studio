"""Pincel, borrador y tampón de clonar con eventos de ratón."""

import numpy as np
import pytest
from PySide6.QtCore import Qt

from ayudas import arrastrar, clic, foto_de_prueba, mover, presionar, soltar
from vortex_studio.photo.document import KIND_IMAGE
from vortex_studio.ui.photo.session import DRAWING_NAME

ALT = Qt.AltModifier


def test_el_pincel_crea_una_capa_de_dibujo_del_tamano_del_lienzo(s, lienzo):
    s.set_tool("brush")
    arrastrar(lienzo, (200, 200), (600, 400))
    assert len(s.doc.layers) == 1
    d = s.doc.layers[0]
    assert d.kind == KIND_IMAGE and d.name == DRAWING_NAME
    assert (d.transform.width, d.transform.height) == (1080, 1080)
    assert s.selection == [d.id]
    assert s.history.undo_label == "Pincel"
    px = s.store.get(d.asset)
    assert px[..., 3].max() > 0           # algo se pintó


def test_el_segundo_trazo_usa_la_misma_capa(s, lienzo):
    pasos = []
    s.committed.connect(pasos.append)
    s.set_tool("brush")
    arrastrar(lienzo, (200, 200), (600, 400))
    arrastrar(lienzo, (200, 500), (600, 500))
    assert len(s.doc.layers) == 1
    assert pasos == ["Pincel", "Pincel"]


def test_el_pincel_sobre_una_foto_no_la_daña(s, lienzo):
    f = s.add_image(foto_de_prueba(300, 300))
    antes = s.store.get(f.asset).copy()
    s.set_tool("brush")
    arrastrar(lienzo, (500, 500), (580, 540))
    assert len(s.doc.layers) == 2
    assert np.array_equal(s.store.get(s.doc.layer(f.id).asset), antes)


def test_el_trazo_se_deshace(s, lienzo):
    s.set_tool("brush")
    arrastrar(lienzo, (200, 200), (600, 400))
    s.undo()
    assert s.doc.layers == []


def test_un_clic_pinta_un_punto(s, lienzo):
    s.set_tool("brush")
    clic(lienzo, 300, 300)
    assert len(s.doc.layers) == 1


def test_el_trazo_se_ve_mientras_se_arrastra_y_no_toca_el_historial(s, lienzo):
    s.set_tool("brush")
    n = len(s.history)
    presionar(lienzo, 200, 200)
    mover(lienzo, 300, 300)
    assert len(lienzo._stroke) == 2
    assert len(s.history) == n
    soltar(lienzo, 300, 300)
    assert lienzo._stroke == []


def test_borrador_borra_sobre_la_foto_seleccionada(s, lienzo):
    f = s.add_image(foto_de_prueba(300, 300))
    s.set_tool("erase")
    arrastrar(lienzo, (540, 540), (560, 540))
    px = s.store.get(s.doc.layer(f.id).asset)
    assert px[..., 3].min() < 255
    assert s.history.undo_label == "Borrador"
    s.undo()
    assert s.store.get(s.doc.layer(f.id).asset)[..., 3].min() == 255


def test_borrador_sin_foto_seleccionada_avisa(s, lienzo):
    mensajes = []
    s.message.connect(mensajes.append)
    s.set_tool("erase")
    arrastrar(lienzo, (540, 540), (560, 540))
    assert s.doc.layers == []
    assert mensajes


def test_pintar_en_una_capa_bloqueada_no_se_puede(s, lienzo):
    f = s.add_image(foto_de_prueba(300, 300))
    s.set_locked(f.id, True)
    s.select([f.id])
    s.set_tool("brush")
    n = len(s.doc.layers)
    arrastrar(lienzo, (540, 540), (560, 540))
    assert len(s.doc.layers) == n
    s.set_tool("erase")
    arrastrar(lienzo, (540, 540), (560, 540))
    assert s.store.get(s.doc.layer(f.id).asset)[..., 3].min() == 255


def test_el_trazo_fuera_del_lienzo_no_truena(s, lienzo):
    s.set_tool("brush")
    arrastrar(lienzo, (-500, -500), (2000, 2000))
    assert len(s.doc.layers) == 1


def test_con_el_pincel_no_se_selecciona_ni_se_mueve(s, lienzo):
    f = s.add_image(foto_de_prueba(300, 300))
    s.clear_selection()
    s.set_tool("brush")
    arrastrar(lienzo, (540, 540), (600, 600))
    assert s.doc.layer(f.id).transform.cx == 540


def test_atajos_b_e_v_y_esc(foto, s):
    foto.actions_by_name["tool_brush"].trigger()
    assert s.tool == "brush"
    foto.actions_by_name["tool_erase"].trigger()
    assert s.tool == "erase"
    foto.actions_by_name["tool_move"].trigger()
    assert s.tool == "move"
    s.set_tool("brush")
    foto.actions_by_name["escape"].trigger()
    assert s.tool == "move"


def test_el_panel_dibujar_cambia_el_pincel(foto, s):
    p = foto.draw_panel
    p.btn_brush.click()
    assert s.tool == "brush" and p.btn_brush.isChecked()
    p.size._slider.setValue(120)
    p.hard._slider.setValue(30)
    p.opac._slider.setValue(50)
    assert s.brush.size == 120 and s.brush.hardness == pytest.approx(0.3) and s.brush.opacity == pytest.approx(0.5)
    p.color.open_popup()
    p.color.popup.swatches["#ff3131"].click()
    assert s.brush.color == "#ff3131"
    p.btn_brush.click()
    assert s.tool == "move"


def test_el_tamano_del_pincel_cambia_el_trazo(s, lienzo):
    s.brush.size = 200
    s.set_tool("brush")
    arrastrar(lienzo, (300, 300), (700, 300))
    grande = (s.store.get(s.doc.layers[0].asset)[..., 3] > 0).sum()
    s.undo()
    s.brush.size = 10
    arrastrar(lienzo, (300, 300), (700, 300))
    chico = (s.store.get(s.doc.layers[-1].asset)[..., 3] > 0).sum()
    assert grande > chico


def test_tampon_pide_el_origen_con_alt(s, lienzo):
    f = s.add_image(foto_de_prueba(300, 300))
    mensajes = []
    s.message.connect(mensajes.append)
    s.set_tool("clone")
    arrastrar(lienzo, (540, 540), (560, 540))          # sin origen
    assert s.clone_source is None and mensajes
    n = len(s.history)
    assert len(s.history) == n
    presionar(lienzo, 480, 480, ALT)
    soltar(lienzo, 480, 480, ALT)
    assert s.clone_source is not None
    arrastrar(lienzo, (540, 540), (560, 540))
    assert s.history.undo_label == "Tampón de clonar"


def test_el_origen_del_tampon_se_olvida_al_abrir_otro_diseno(s, lienzo):
    s.add_image(foto_de_prueba(300, 300))
    s.clone_source = (3.0, 4.0)
    s.new_document(500, 500)
    assert s.clone_source is None
