"""Panel «Editar foto»: filtros, ajustes, efectos, antes/después y Más opciones."""

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ayudas import arrastrar, centro, clic, esperar, foto_de_prueba, tecla
from vortex_studio.photo.document import KIND_ADJUST
from vortex_studio.photo.filters import FILTERS


@pytest.fixture
def ed(foto, s):
    capa = s.add_image(foto_de_prueba(400, 300))
    foto.open_edit("filtros")
    return foto.edit_panel, capa


def arrastrar_slider(sl, valores):
    """Simula arrastrar un PSlider: pulsar, mover varias veces, soltar."""
    sl._slider.sliderPressed.emit()
    for v in valores:
        sl._slider.setValue(int(v))
    sl._slider.sliderReleased.emit()


def test_el_panel_se_abre_con_editar_foto(foto, s, ed):
    p, capa = ed
    assert foto.right_frame.isVisible()
    assert p.title.text() == "Editar foto"
    foto.close_edit()
    assert not foto.right_frame.isVisible()


def test_el_boton_editar_foto_de_la_barra_abre_el_panel(foto, s):
    capa = s.add_image(foto_de_prueba())
    foto.context.btn_edit_photo.click()
    assert foto.right_frame.isVisible()


def test_el_panel_se_cierra_al_quedarse_sin_seleccion(foto, s, ed):
    s.clear_selection()
    assert not foto.right_frame.isVisible()


# --- filtros ------------------------------------------------------------------------

def test_las_miniaturas_salen_una_por_turno(foto, s, ed, qapp):
    p, capa = ed
    for _ in range(100):
        qapp.processEvents()
        if p.thumbs_ready():
            break
    assert p.thumbs_ready()
    assert set(p._thumb_images) == {""} | set(FILTERS)
    assert not p.filter_buttons["vivido"].icon().isNull()


def test_las_miniaturas_no_se_rehacen_al_editar_otra_cosa(foto, s, ed, qapp):
    p, capa = ed
    for _ in range(100):
        qapp.processEvents()
    clave = p._thumb_key
    imgs = dict(p._thumb_images)
    s.edit("Brillo", lambda c: setattr(c.adjustments, "exposure", 50.0), [capa])
    assert p._thumb_key == clave
    assert p._thumb_images == imgs


def test_elegir_un_filtro(foto, s, ed):
    p, capa = ed
    nombre = next(iter(FILTERS))
    p.pick_filter(nombre)
    assert s.doc.layer(capa.id).filter.name == nombre
    assert s.history.undo_label.startswith("Filtro")
    assert p.filter_buttons[nombre].isChecked()
    s.undo()
    assert s.doc.layer(capa.id).filter.is_off()
    assert p.filter_buttons[""].isChecked()


def test_quitar_el_filtro(foto, s, ed):
    p, capa = ed
    p.pick_filter(next(iter(FILTERS)))
    p.pick_filter("")
    assert s.doc.layer(capa.id).filter.is_off()


def test_la_intensidad_arrastrada_es_un_paso(foto, s, ed):
    p, capa = ed
    p.pick_filter(next(iter(FILTERS)))
    n = s.history._pos
    arrastrar_slider(p.intensity, (90, 70, 40))
    assert s.doc.layer(capa.id).filter.intensity == 40
    assert s.history._pos == n + 1
    s.undo()
    assert s.doc.layer(capa.id).filter.intensity == 100


def test_la_intensidad_esta_apagada_sin_filtro(foto, s, ed):
    p, capa = ed
    assert not p.intensity.isEnabled()
    p.pick_filter(next(iter(FILTERS)))
    assert p.intensity.isEnabled()


def test_un_filtro_conserva_la_intensidad_al_cambiar_de_filtro(foto, s, ed):
    p, capa = ed
    nombres = list(FILTERS)
    p.pick_filter(nombres[0])
    arrastrar_slider(p.intensity, (55,))
    p.pick_filter(nombres[1])
    assert s.doc.layer(capa.id).filter.intensity == 55


def test_filtro_en_una_capa_bloqueada_no_se_aplica(foto, s, ed):
    p, capa = ed
    s.set_locked(capa.id, True)
    s.select([capa.id])
    p.pick_filter(next(iter(FILTERS)))
    assert s.doc.layer(capa.id).filter.is_off()


# --- ajustes ----------------------------------------------------------------------------

def test_arrastrar_un_deslizador_deja_un_solo_paso(foto, s, ed):
    p, capa = ed
    n = s.history._pos
    arrastrar_slider(p.sliders["contrast"], (5, 15, 30, 42))
    assert s.doc.layer(capa.id).adjustments.contrast == 42
    assert s.history._pos == n + 1
    assert s.history.undo_label == "Contraste"
    s.undo()
    assert s.doc.layer(capa.id).adjustments.contrast == 0
    assert p.sliders["contrast"].value() == 0


def test_mientras_se_arrastra_se_redibuja_sin_historial(foto, s, lienzo, ed):
    p, capa = ed
    lienzo.flush()
    r0 = lienzo.render_count
    n = s.history._pos
    p.sliders["shadows"]._slider.sliderPressed.emit()
    for v in range(0, 40, 4):
        p.sliders["shadows"]._slider.setValue(v)
    assert s.history._pos == n
    lienzo.flush()
    assert lienzo.render_count == r0 + 1          # los cambios se juntaron en un solo dibujo
    p.sliders["shadows"]._slider.sliderReleased.emit()


def test_cada_deslizador_cambia_su_campo(foto, s, ed):
    p, capa = ed
    for campo, sl in p.sliders.items():
        arrastrar_slider(sl, (10,))
        v = getattr(s.doc.layer(capa.id).adjustments, campo)
        assert v != 0, campo


def test_la_exposicion_se_muestra_en_pasos_de_luz(foto, s, ed):
    p, capa = ed
    arrastrar_slider(p.sliders["exposure"], (150,))     # 1,5 pasos = 150 en el modelo
    assert s.doc.layer(capa.id).adjustments.exposure == 150


def test_restablecer_un_grupo_es_un_paso(foto, s, ed):
    p, capa = ed
    arrastrar_slider(p.sliders["contrast"], (20,))
    arrastrar_slider(p.sliders["shadows"], (30,))
    arrastrar_slider(p.sliders["vibrance"], (30,))
    n = s.history._pos
    p.reset_group("Luz")
    a = s.doc.layer(capa.id).adjustments
    assert a.contrast == 0 and a.shadows == 0 and a.vibrance == 30
    assert s.history._pos == n + 1
    p.reset_group("Luz")                                # ya está en neutro: sin paso nuevo
    assert s.history._pos == n + 1


def test_mejorar_con_un_clic(foto, s, ed):
    p, capa = ed
    p.auto_enhance()
    assert not s.doc.layer(capa.id).adjustments.is_neutral()
    assert s.history.undo_label == "Mejorar con un clic"
    assert p.sliders["contrast"].value() == s.doc.layer(capa.id).adjustments.contrast
    s.undo()
    assert s.doc.layer(capa.id).adjustments.is_neutral()


def test_doble_clic_en_un_deslizador_lo_regresa_al_neutro(foto, s, ed):
    p, capa = ed
    arrastrar_slider(p.sliders["blacks"], (25,))
    p.sliders["blacks"].mouseDoubleClickEvent(None)
    assert s.doc.layer(capa.id).adjustments.blacks == 0


def test_ajustes_en_una_capa_bloqueada_se_ignoran(foto, s, ed):
    p, capa = ed
    s.set_locked(capa.id, True)
    s.select([capa.id])
    p._adj_live("contrast", 40)
    assert s.doc.layer(capa.id).adjustments.contrast == 0


def test_el_panel_sigue_a_la_seleccion(foto, s, ed):
    p, capa = ed
    arrastrar_slider(p.sliders["contrast"], (33,))
    otra = s.add_image(foto_de_prueba(100, 100))
    assert p.sliders["contrast"].value() == 0
    s.select([capa.id])
    assert p.sliders["contrast"].value() == 33


# --- capa de ajuste -----------------------------------------------------------------------------

def test_agregar_capa_de_ajuste_y_editarla(foto, s, ed):
    p, capa = ed
    p.btn_add_adjust.click()
    aj = s.single()
    assert aj.kind == KIND_ADJUST
    foto.open_edit("ajustes")
    assert p.title.text() == "Capa de ajuste"
    arrastrar_slider(p.sliders["saturation"], (-40,))
    assert s.doc.layer(aj.id).adjustments.saturation == -40
    assert s.doc.layer(capa.id).adjustments.saturation == 0


# --- efectos ------------------------------------------------------------------------------------------

def test_sombra_contorno_y_brillo(foto, s, ed):
    p, capa = ed
    for clave in ("shadow", "outline", "glow"):
        p.fx[clave]["check"].setChecked(True)
        assert getattr(s.doc.layer(capa.id).effects, clave).enabled
        p.fx[clave]["check"].setChecked(False)
        assert not getattr(s.doc.layer(capa.id).effects, clave).enabled


def test_el_desenfoque_de_la_sombra_arrastrado_es_un_paso(foto, s, ed):
    p, capa = ed
    n = s.history._pos
    arrastrar_slider(p.fx["shadow"]["sliders"]["blur"][0], (5, 20, 33))
    e = s.doc.layer(capa.id).effects.shadow
    assert e.blur == 33 and e.enabled
    assert s.history._pos == n + 1


def test_color_del_contorno(foto, s, ed):
    p, capa = ed
    c = p.fx["outline"]["color"]
    c.open_popup()
    c.popup.swatches["#ff3131"].click()
    assert s.doc.layer(capa.id).effects.outline.color == "#ff3131"


def test_efectos_para_texto_y_formas(foto, s):
    t = s.add_text(0)
    foto.context.btn_text_fx.click()
    assert foto.right_frame.isVisible()
    assert foto.edit_panel.title.text() == "Efectos"
    foto.edit_panel.fx["glow"]["check"].setChecked(True)
    assert s.doc.layer(t.id).effects.glow.enabled
    f = s.add_shape("star")
    foto.context.btn_shape_fx.click()
    foto.edit_panel.fx["shadow"]["check"].setChecked(True)
    assert s.doc.layer(f.id).effects.shadow.enabled


# --- antes y después --------------------------------------------------------------------------------------------

def test_mantener_el_ojo_muestra_el_original(foto, s, lienzo, ed):
    llamadas = []
    original = s.renderer.render

    def espia(doc, scale=1.0, **kw):
        llamadas.append(kw.get("original", False))
        return original(doc, scale, **kw)

    s.renderer.render = espia
    foto.btn_compare.pressed.emit()
    lienzo.flush()
    assert lienzo.show_original and llamadas[-1] is True
    foto.btn_compare.released.emit()
    lienzo.flush()
    assert not lienzo.show_original and llamadas[-1] is False


def test_la_tecla_barra_invertida_muestra_el_original(foto, s, lienzo):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    foto.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backslash, Qt.NoModifier))
    assert lienzo.show_original
    foto.keyReleaseEvent(QKeyEvent(QEvent.KeyRelease, Qt.Key_Backslash, Qt.NoModifier))
    assert not lienzo.show_original


def test_antes_despues_no_toca_el_historial(foto, s, lienzo, ed):
    n = s.history._pos
    lienzo.set_show_original(True)
    lienzo.set_show_original(False)
    assert s.history._pos == n


# --- más opciones --------------------------------------------------------------------------------------------------

def test_curva_agregar_mover_y_quitar_puntos(foto, s, ed):
    p, capa = ed
    p.sub_curve.abrir()
    c = p.curve
    c.points = []
    from ayudas import _ev
    from PySide6.QtCore import QEvent, QPointF
    r = c._rect()
    centro_ = QPointF(r.center())
    n = s.history._pos
    c.mousePressEvent(_ev(QEvent.MouseButtonPress, centro_))
    c.mouseMoveEvent(_ev(QEvent.MouseMove, centro_ + QPointF(0, -30), Qt.NoButton, Qt.LeftButton))
    c.mouseReleaseEvent(_ev(QEvent.MouseButtonRelease, centro_ + QPointF(0, -30), Qt.LeftButton, Qt.NoButton))
    curva = s.doc.layer(capa.id).adjustments.curve
    assert len(curva) == 3 and curva[1][1] > 0.5
    assert s.history._pos == n + 1 and s.history.undo_label == "Curva"
    c.mouseDoubleClickEvent(_ev(QEvent.MouseButtonDblClick, c._to_pt(*curva[1])))
    assert s.doc.layer(capa.id).adjustments.curve == []


def test_hsl_por_franja(foto, s, ed):
    p, capa = ed
    p.band.setCurrentIndex(p.band.findData("blue"))
    arrastrar_slider(p.hsl[1], (-50,))
    assert s.doc.layer(capa.id).adjustments.hsl["blue"] == (0.0, -50.0, 0.0)
    p.band.setCurrentIndex(p.band.findData("red"))
    assert p.hsl[1].value() == 0
    p.band.setCurrentIndex(p.band.findData("blue"))
    assert p.hsl[1].value() == -50
    arrastrar_slider(p.hsl[1], (0,))
    assert "blue" not in s.doc.layer(capa.id).adjustments.hsl


def test_modo_de_fusion_desde_el_panel(foto, s, ed):
    p, capa = ed
    p.blend.setCurrentText("Superponer")
    p.blend.activated.emit(p.blend.currentIndex())
    assert s.doc.layer(capa.id).blend == "Superponer"


def test_quitar_fondo_y_quitar_mascara(foto, s, ed):
    p, capa = ed
    p.btn_remove_bg.click()
    assert s.doc.layer(capa.id).mask
    assert s.history.undo_label == "Quitar fondo"
    p.btn_clear_mask.click()
    assert s.doc.layer(capa.id).mask is None
    s.undo()
    assert s.doc.layer(capa.id).mask


def test_las_herramientas_de_mascara_se_encienden_y_apagan(foto, s, ed):
    p, capa = ed
    p.btn_mask_paint.click()
    assert s.tool == "mask_paint" and p.btn_mask_paint.isChecked()
    p.btn_wand.click()
    assert s.tool == "wand" and not p.btn_mask_paint.isChecked()
    p.btn_wand.click()
    assert s.tool == "move"
    p.btn_clone.click()
    assert s.tool == "clone"
    tecla(foto.canvas, Qt.Key_Escape)
    assert s.tool == "move" and not p.btn_clone.isChecked()


def test_pintar_y_borrar_la_mascara(foto, s, lienzo, ed):
    p, capa = ed
    p.btn_mask_erase.click()
    arrastrar(lienzo, (500, 540), (580, 540))
    m = s.store.get(s.doc.layer(capa.id).mask)
    assert m.ndim == 2 and m.min() == 0 and m.max() == 255
    assert s.history.undo_label == "Borrar con la máscara"
    p.btn_mask_paint.click()
    arrastrar(lienzo, (500, 540), (580, 540))
    assert s.history.undo_label == "Pintar la máscara"


def test_la_varita_ajusta_su_tolerancia_y_modo(foto, s, lienzo, ed):
    p, capa = ed
    p.btn_wand.click()
    arrastrar_slider(p.wand_tol, (80,))
    assert s.wand_tolerance == 80
    p.wand_mode.buttons[True].click()
    assert s.wand_keep is True
    p.wand_contig.setChecked(False)
    assert s.wand_contiguous is False
    clic(lienzo, 540, 540)
    assert s.history.undo_label == "Varita mágica"
    assert s.doc.layer(capa.id).mask


def test_la_varita_fuera_de_la_foto_no_hace_nada(foto, s, lienzo, ed):
    p, capa = ed
    p.btn_wand.click()
    n = s.history._pos
    clic(lienzo, 540, 540)      # esta sí está dentro
    n2 = s.history._pos
    s.select([capa.id])
    assert not s.wand_click(5.0, 5.0)
    assert s.history._pos == n2


def test_mascara_sin_foto_seleccionada(foto, s, lienzo):
    s.add_shape("rect")
    s.set_tool("mask_paint")
    assert not s.mask_stroke([(540, 540)], erase=False)
    assert not s.remove_background()
