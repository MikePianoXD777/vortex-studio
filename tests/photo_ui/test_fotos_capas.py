"""Capas, copiar/pegar, historial y panel de capas."""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from ayudas import clic, foto_de_prueba
from vortex_studio.photo.document import KIND_ADJUST, KIND_IMAGE, KIND_SHAPE, KIND_TEXT


@pytest.fixture
def tres(s):
    a = s.add_shape("rect")
    b = s.add_shape("ellipse")
    c = s.add_text(0)
    s.clear_selection()
    return a, b, c


def ids(s):
    return [c.id for c in s.doc.layers]


# --- historial de cada operación ----------------------------------------------------

def test_agregar_imagen_texto_y_forma_se_deshacen(s):
    s.add_image(foto_de_prueba())
    s.add_text(1)
    s.add_shape("star")
    assert len(s.doc.layers) == 3
    for esperado in (2, 1, 0):
        assert s.undo()
        assert len(s.doc.layers) == esperado
    assert not s.undo()
    for esperado in (1, 2, 3):
        assert s.redo()
        assert len(s.doc.layers) == esperado
    assert not s.redo()


def test_las_etiquetas_del_historial(s):
    s.add_text(0)
    assert s.history.undo_label == "Agregar texto"
    s.add_shape("rect")
    assert s.history.undo_label == "Agregar forma"
    s.add_image(foto_de_prueba())
    assert s.history.undo_label == "Agregar imagen"
    s.duplicate_selected()
    assert s.history.undo_label == "Duplicar"
    s.delete_selected()
    assert s.history.undo_label == "Eliminar"


def test_borrar_duplicar_y_pegar_se_deshacen(s, tres):
    a, b, c = tres
    s.select([a.id])
    s.delete_selected()
    assert a.id not in ids(s)
    s.undo()
    assert a.id in ids(s)
    s.select([a.id])
    nuevas = s.duplicate_selected()
    assert len(s.doc.layers) == 4
    s.undo()
    assert len(s.doc.layers) == 3
    s.select([a.id])
    s.copy_selected()
    s.paste()
    assert len(s.doc.layers) == 4
    s.undo()
    assert len(s.doc.layers) == 3


def test_reordenar_se_deshace(s, tres):
    a, b, c = tres
    s.select([a.id])
    s.reorder("frente")
    assert ids(s) == [b.id, c.id, a.id]
    s.undo()
    assert ids(s) == [a.id, b.id, c.id]


def test_visibilidad_bloqueo_y_transparencia_se_deshacen(s, tres):
    a, b, c = tres
    s.set_visible(a.id, False)
    s.undo()
    assert s.doc.layer(a.id).visible
    s.set_locked(a.id, True)
    s.undo()
    assert not s.doc.layer(a.id).locked
    s.select([a.id])
    s.edit("Transparencia", lambda x: setattr(x, "opacity", 0.4))
    s.undo()
    assert s.doc.layer(a.id).opacity == 1.0


def test_el_color_de_fondo_y_el_tamano_se_deshacen(s):
    s.set_background("#ff0000")
    s.resize_document(500, 300)
    s.undo()
    assert (s.doc.width, s.doc.height) == (1080, 1080)
    s.undo()
    assert s.doc.background == "#ffffff"


def test_al_deshacer_la_seleccion_solo_conserva_lo_que_existe(s, tres):
    a, b, c = tres
    s.select([c.id])
    s.undo()          # quita el texto
    assert s.selection == []


def test_cambios_marcan_el_diseno_como_sin_guardar(s):
    assert not s.dirty
    s.add_shape("rect")
    assert s.dirty


# --- copiar, pegar, duplicar, borrar --------------------------------------------------------

def test_duplicar_deja_la_copia_encima_y_desplazada(s, tres):
    a, b, c = tres
    s.select([a.id])
    (n,) = s.duplicate_selected()
    assert s.doc.layers[-1].id == n.id and n.id != a.id
    assert n.transform.cx == a.transform.cx + 24
    assert s.selection == [n.id]


def test_duplicar_sin_seleccion_no_hace_nada(s, tres):
    assert s.duplicate_selected() == []
    assert len(s.doc.layers) == 3


def test_copiar_y_pegar_varias_veces_desplaza_cada_una(s, tres):
    a, b, c = tres
    s.select([a.id])
    s.copy_selected()
    s.paste()
    s.paste()
    p1, p2 = s.doc.layers[-2], s.doc.layers[-1]
    assert p2.transform.cx - p1.transform.cx == 24
    assert p1.id not in (a.id, p2.id)


def test_cortar_y_pegar(s, tres):
    a, b, c = tres
    s.select([b.id])
    s.cut_selected()
    assert b.id not in ids(s)
    assert s.paste()
    assert len(s.doc.layers) == 3


def test_pegar_sin_nada_no_hace_nada(s):
    QApplication.clipboard().clear()
    assert not s.paste()


def test_pegar_una_imagen_del_portapapeles(s):
    from vortex_studio.photo.render import to_qimage
    QApplication.clipboard().setImage(to_qimage(foto_de_prueba(60, 40)))
    assert s.paste()
    assert s.doc.layers[-1].kind == KIND_IMAGE


def test_pegar_conserva_las_propiedades(s):
    t = s.add_text(0)
    t.bold, t.color, t.font_size = True, "#ff0000", 77.0
    s.commit("x")
    s.copy_selected()
    s.paste()
    p = s.doc.layers[-1]
    assert (p.kind, p.color, p.font_size, p.text) == (KIND_TEXT, "#ff0000", 77.0, t.text)


def test_borrar_varias(s, tres):
    a, b, c = tres
    s.select([a.id, c.id])
    s.delete_selected()
    assert ids(s) == [b.id]
    assert s.selection == []


def test_borrar_sin_seleccion(s, tres):
    assert not s.delete_selected()


def test_una_capa_bloqueada_no_se_borra(s, tres):
    a, b, c = tres
    s.set_locked(a.id, True)
    s.select([a.id])
    assert not s.delete_selected()
    assert a.id in ids(s)
    s.select([a.id, b.id])
    s.delete_selected()
    assert ids(s) == [a.id, c.id]


def test_bloquear_la_seleccion_con_el_boton(foto, s, tres):
    a, b, c = tres
    s.select([a.id, b.id])
    foto.context.btn_lock.click()
    assert s.doc.layer(a.id).locked and s.doc.layer(b.id).locked
    foto.context.btn_lock.click()
    assert not s.doc.layer(a.id).locked


# --- orden ---------------------------------------------------------------------------------------

def test_traer_y_enviar(s, tres):
    a, b, c = tres
    s.select([a.id])
    s.reorder("adelante")
    assert ids(s) == [b.id, a.id, c.id]
    s.reorder("atras")
    assert ids(s) == [a.id, b.id, c.id]
    s.reorder("fondo")      # ya está: no cambia nada
    assert s.history.undo_label != "Enviar al fondo"
    s.select([c.id])
    s.reorder("fondo")
    assert ids(s) == [c.id, a.id, b.id]
    s.reorder("frente")
    assert ids(s) == [a.id, b.id, c.id]


def test_reordenar_varias_a_la_vez(s, tres):
    a, b, c = tres
    s.select([a.id, b.id])
    s.reorder("frente")
    assert ids(s) == [c.id, a.id, b.id]


def test_reordenar_sin_seleccion(s, tres):
    assert not s.reorder("frente")


def test_mover_capa_a_una_posicion(s, tres):
    a, b, c = tres
    assert s.move_layer_to(c.id, 0)
    assert ids(s) == [c.id, a.id, b.id]
    assert not s.move_layer_to(c.id, 0)
    assert not s.move_layer_to("no existe", 0)
    s.move_layer_to(c.id, 99)
    assert ids(s)[-1] == c.id


def test_alinear_una_capa_al_lienzo(s, tres):
    a, b, c = tres
    s.select([a.id])
    s.align("izquierda")
    assert a.transform.cx - a.transform.width / 2 == pytest.approx(0)
    s.align("derecha")
    assert a.transform.cx + a.transform.width / 2 == pytest.approx(1080)
    s.align("abajo")
    assert a.transform.cy + a.transform.height / 2 == pytest.approx(1080)
    s.align("arriba")
    assert a.transform.cy - a.transform.height / 2 == pytest.approx(0)
    s.align("centro")
    s.align("medio")
    assert (a.transform.cx, a.transform.cy) == pytest.approx((540, 540))


def test_alinear_varias_entre_si(s):
    a = s.add_shape("rect")
    b = s.add_shape("rect")
    a.transform.cx, b.transform.cx = 200, 600
    s.select([a.id, b.id])
    s.align("izquierda")
    assert a.transform.cx - a.transform.width / 2 == pytest.approx(b.transform.cx - b.transform.width / 2)
    assert a.transform.cx - a.transform.width / 2 == pytest.approx(200 - a.transform.width / 2)


def test_alinear_una_capa_bloqueada_no_la_mueve(s, tres):
    a, *_ = tres
    s.set_locked(a.id, True)
    s.select([a.id])
    cx = a.transform.cx
    assert not s.align("izquierda")
    assert a.transform.cx == cx


def test_voltear(s, tres):
    a, *_ = tres
    s.select([a.id])
    s.flip_selected(True)
    s.flip_selected(False)
    assert a.transform.flip_h and a.transform.flip_v
    s.undo()
    assert not s.doc.layer(a.id).transform.flip_v


def test_capa_de_ajuste(s):
    c = s.add_adjustment_layer()
    assert c.kind == KIND_ADJUST
    assert (c.transform.width, c.transform.height) == (1080, 1080)


# --- el panel de capas ---------------------------------------------------------------------------------

def test_el_panel_lista_con_el_frente_arriba(foto, s, tres):
    a, b, c = tres
    p = foto.layers_panel
    assert p.list.count() == 3
    assert [p.layer_at_row(i).id for i in range(3)] == [c.id, b.id, a.id]


def test_seleccionar_desde_la_lista(foto, s, tres):
    a, b, c = tres
    p = foto.layers_panel
    p.list.item(2).setSelected(True)           # la fila de abajo = a
    assert s.selection == [a.id]
    p.list.clearSelection()
    assert s.selection == []


def test_la_lista_sigue_a_la_seleccion_del_lienzo(foto, s, tres):
    a, b, c = tres
    s.select([b.id])
    p = foto.layers_panel
    assert p.list.item(p.row_of(b.id)).isSelected()
    assert not p.list.item(p.row_of(a.id)).isSelected()


def test_reordenar_arrastrando_en_la_lista(foto, s, tres):
    a, b, c = tres                 # filas: c, b, a
    p = foto.layers_panel
    assert p.move_row(2, 0, after=False)     # a arriba de c
    assert ids(s) == [b.id, c.id, a.id]
    assert [p.layer_at_row(i).id for i in range(3)] == [a.id, c.id, b.id]
    assert p.move_row(0, 2, after=True)      # a al final de la lista = al fondo
    assert ids(s)[0] == a.id


def test_mover_una_fila_donde_ya_esta_no_hace_nada(foto, s, tres):
    p = foto.layers_panel
    n = len(s.history)
    assert not p.move_row(0, 0)
    assert len(s.history) == n


def test_ojo_y_candado_de_la_lista(foto, s, tres):
    from vortex_studio.ui.photo.layers_panel import ROW_H, eye_rect, lock_rect
    a, b, c = tres
    p = foto.layers_panel
    item = p.list.item(0)
    r = p.list.visualItemRect(item).adjusted(2, 2, -2, -2)
    from ayudas import _ev
    from PySide6.QtCore import QEvent
    pt = QPointF(eye_rect(r).center())
    p.list.mousePressEvent(_ev(QEvent.MouseButtonPress, pt))
    assert not s.doc.layer(c.id).visible
    pt = QPointF(lock_rect(r).center())
    p.list.mousePressEvent(_ev(QEvent.MouseButtonPress, pt))
    assert s.doc.layer(c.id).locked


def test_transparencia_y_fusion_desde_el_panel(foto, s, tres):
    a, b, c = tres
    s.select([a.id])
    p = foto.layers_panel
    p.opacity._slider.setValue(40)
    assert s.doc.layer(a.id).opacity == pytest.approx(0.4)
    p.blend.setCurrentText("Multiplicar")
    p.blend.activated.emit(p.blend.currentIndex())
    assert s.doc.layer(a.id).blend == "Multiplicar"


def test_arrastrar_la_transparencia_es_un_solo_paso(foto, s, tres):
    a, *_ = tres
    s.select([a.id])
    p = foto.layers_panel
    n = len(s.history)
    p.opacity._slider.sliderPressed.emit()
    for v in (90, 70, 50, 30):
        p.opacity._slider.setValue(v)
    assert len(s.history) == n                       # nada en el historial mientras se arrastra
    assert s.doc.layer(a.id).opacity == pytest.approx(0.3)
    p.opacity._slider.sliderReleased.emit()
    assert len(s.history) == n + 1
    s.undo()
    assert s.doc.layer(a.id).opacity == 1.0


def test_las_miniaturas_se_guardan_en_cache(foto, s, tres):
    p = foto.layers_panel
    a, *_ = tres
    x = p.thumb(s.doc.layer(a.id))
    y = p.thumb(s.doc.layer(a.id))
    assert x is y


def test_el_panel_no_falla_con_el_diseno_vacio(foto, s):
    assert foto.layers_panel.list.count() == 0
