"""Texto: editar en el lugar y la barra contextual."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QApplication

from ayudas import centro, clic, doble_clic, esperar
from vortex_studio.photo.document import KIND_TEXT


@pytest.fixture
def texto(s, lienzo):
    t = s.add_text(2)
    lienzo.flush()
    s.clear_selection()
    return t


def test_doble_clic_en_un_texto_lo_edita(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    assert lienzo.is_editing()
    assert lienzo.editor().toPlainText() == texto.text
    assert s.selection == [texto.id]


def test_escribir_cambia_el_texto_y_termina_en_un_paso(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    n = len(s.history)
    lienzo.editor().setPlainText("Hola")
    lienzo.editor().setPlainText("Hola mundo")
    assert s.doc.layer(texto.id).text == "Hola mundo"
    assert len(s.history) == n                    # nada en el historial mientras se escribe
    lienzo.end_text_edit()
    assert not lienzo.is_editing()
    assert len(s.history) == n + 1 and s.history.undo_label == "Editar texto"
    s.undo()
    assert s.doc.layer(texto.id).text != "Hola mundo"
    s.redo()
    assert s.doc.layer(texto.id).text == "Hola mundo"


def test_escape_termina_la_edicion(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    lienzo.editor().setPlainText("Otro")
    QApplication.sendEvent(lienzo.editor(), QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert not lienzo.is_editing()
    assert s.doc.layer(texto.id).text == "Otro"


def test_clic_fuera_termina_la_edicion(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    lienzo.editor().setPlainText("Fuera")
    clic(lienzo, 40, 40)
    assert not lienzo.is_editing()
    assert s.doc.layer(texto.id).text == "Fuera"


def test_editar_sin_cambiar_no_agrega_paso(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    n = len(s.history)
    lienzo.end_text_edit()
    assert len(s.history) == n


def test_dejar_el_texto_vacio_borra_la_capa(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    lienzo.editor().setPlainText("   ")
    lienzo.end_text_edit()
    assert s.doc.layer(texto.id) is None
    s.undo()
    assert s.doc.layer(texto.id) is not None


def test_el_texto_en_edicion_no_se_dibuja_dos_veces(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    assert texto.id in lienzo._hidden()
    lienzo.end_text_edit()
    assert texto.id not in lienzo._hidden()


def test_un_texto_bloqueado_no_se_edita(s, lienzo, texto):
    s.set_locked(texto.id, True)
    doble_clic(lienzo, *centro(texto))
    assert not lienzo.is_editing()


def test_borrar_la_capa_que_se_edita(s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    s.delete_selected()
    esperar(QApplication.instance())
    assert not lienzo.is_editing()
    assert s.doc.layer(texto.id) is None
    lienzo.end_text_edit()       # no truena


def test_deshacer_con_el_texto_en_edicion(foto, s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    lienzo.editor().setPlainText("Algo")
    foto.undo()
    assert not lienzo.is_editing()


def test_el_atajo_t_agrega_un_texto_y_lo_edita(foto, s, lienzo):
    foto.actions_by_name["text"].trigger()
    assert lienzo.is_editing()
    assert len(s.doc.layers) == 1 and s.doc.layers[0].kind == KIND_TEXT
    lienzo.editor().setPlainText("Escrito")
    lienzo.end_text_edit()
    assert s.doc.layers[0].text == "Escrito"


def test_con_el_editor_abierto_las_letras_no_cambian_de_herramienta(foto, s, lienzo, texto):
    doble_clic(lienzo, *centro(texto))
    foto.actions_by_name["tool_brush"].trigger()
    assert s.tool == "move"


def test_el_texto_cambia_de_alto_al_escribir_mas_lineas(s, lienzo, texto):
    h = texto.transform.height
    doble_clic(lienzo, *centro(texto))
    lienzo.editor().setPlainText("\n".join(["linea"] * 6))
    assert s.doc.layer(texto.id).transform.height > h
    lienzo.end_text_edit()


# --- barra contextual -------------------------------------------------------------------------

def test_la_barra_muestra_los_controles_de_texto(foto, s, texto):
    s.select([texto.id])
    c = foto.context
    assert c.pages.currentWidget() is c.p_text
    assert c.size_spin.value() == round(texto.font_size)


def test_cambiar_el_tamano_de_letra(foto, s, texto):
    s.select([texto.id])
    foto.context.size_spin.setValue(80)
    assert s.doc.layer(texto.id).font_size == 80
    assert s.history.undo_label == "Tamaño de letra"
    s.undo()
    assert s.doc.layer(texto.id).font_size != 80


def test_negrita_cursiva_subrayado_mayusculas(foto, s, texto):
    s.select([texto.id])
    c = foto.context
    for btn, attr in ((c.btn_bold, "bold"), (c.btn_italic, "italic"), (c.btn_underline, "underline"),
                      (c.btn_upper, "uppercase")):
        antes = getattr(s.doc.layer(texto.id), attr)
        btn.click()
        assert getattr(s.doc.layer(texto.id), attr) is (not antes)


def test_alineacion_cicla(foto, s, texto):
    s.select([texto.id])
    c = foto.context
    vistos = []
    for _ in range(3):
        c.btn_align.click()
        vistos.append(s.doc.layer(texto.id).align)
    assert set(vistos) == {"left", "center", "right"}


def test_fuente_y_color(foto, s, texto):
    s.select([texto.id])
    c = foto.context
    c.font_box.setCurrentFont(QFont("DejaVu Sans"))
    assert s.doc.layer(texto.id).font_family == "DejaVu Sans"
    c.text_color.open_popup()
    c.text_color.popup.swatches["#ff3131"].click()
    assert s.doc.layer(texto.id).color == "#ff3131"
    assert c.text_color.color() == "#ff3131"


def test_espaciado_arrastrando_es_un_paso(foto, s, texto):
    s.select([texto.id])
    c = foto.context
    n = len(s.history)
    sl = c.sp_letter._slider
    sl.sliderPressed.emit()
    for v in (2, 5, 9):
        sl.setValue(v)
    assert len(s.history) == n
    sl.sliderReleased.emit()
    assert len(s.history) == n + 1
    assert s.doc.layer(texto.id).letter_spacing == 9


def test_estilo_a_varios_textos(foto, s):
    a, b = s.add_text(0), s.add_text(1)
    s.select([a.id, b.id])
    assert foto.context.pages.currentWidget() is foto.context.p_multi
    s.edit("Negrita", lambda c: setattr(c, "bold", False))
    assert not a.bold and not b.bold


def test_estilo_no_afecta_a_otras_clases_de_capa(foto, s, texto):
    f = s.add_shape("rect")
    s.select([texto.id, f.id])
    foto.context._text_edit("Negrita", bold=True)
    assert s.doc.layer(texto.id).bold and not hasattr(s.doc.layer(f.id), "nada")


def test_un_texto_bloqueado_ignora_los_controles(foto, s, texto):
    s.select([texto.id])
    s.set_locked(texto.id, True)
    s.select([texto.id])
    foto.context.size_spin.setValue(10)
    assert s.doc.layer(texto.id).font_size != 10


def test_la_barra_sin_seleccion(foto, s):
    c = foto.context
    assert c.pages.currentWidget() is c.p_none
    assert not c.btn_del.isEnabled()
