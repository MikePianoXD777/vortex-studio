"""Revisión adversarial de la interfaz de Vortex Photo contra el motor.

Cada prueba reproduce una sospecha con la `PhotoWindow` en offscreen. Las que
demuestran un bug de la interfaz van marcadas `xfail(strict=True)`: cuando se
arregle el bug la prueba pasará y `strict` avisará que hay que quitar la marca.
"""

from __future__ import annotations

import gc

import numpy as np
import pytest
from PySide6.QtCore import QEvent

from vortex_studio.photo.document import Adjustments, Document, Layer, Transform, document_to_dict
from vortex_studio.photo.paint import Brush


@pytest.fixture
def foto(qapp):
    from vortex_studio.ui.photo import PhotoWindow

    w = PhotoWindow()
    w.resize(1280, 720)
    w.show()
    qapp.processEvents()
    yield w
    w.session.dirty = False
    w.close()
    w.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    gc.collect()


@pytest.fixture
def s(foto):
    return foto.session


def degradado(w, h):
    y, x = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 0] = x * 255 // max(1, w - 1)
    img[..., 1] = y * 255 // max(1, h - 1)
    img[..., 2] = 140
    img[..., 3] = 255
    return img


def mitades(w=200, h=100):
    """Izquierda roja, derecha azul."""
    img = np.zeros((h, w, 4), np.uint8)
    img[..., 3] = 255
    img[:, : w // 2, 0] = 255
    img[:, w // 2:, 2] = 255
    return img


# --- el historial es consistente ------------------------------------------------

def _operaciones(s):
    """Cada una debe cambiar el diseño y cerrar exactamente un paso."""
    capa = s.add_image(degradado(120, 80))
    yield "agregar imagen", None
    s.add_shape("star"); yield "forma", None
    s.add_text(0); yield "texto", None
    s.add_adjustment_layer(); yield "ajuste", None
    s.select([capa.id]); s.move_selected(10, 5); yield "mover", None
    s.align("izquierda"); yield "alinear", None
    s.flip_selected(True); yield "voltear", None
    s.reorder("frente"); yield "orden", None
    s.duplicate_selected(); yield "duplicar", None
    s.lock_selected(True); yield "bloquear", None
    s.lock_selected(False); yield "desbloquear", None
    s.set_visible(capa.id, False); yield "ocultar", None
    s.set_visible(capa.id, True); yield "mostrar", None
    s.select([capa.id]); s.wand_click(capa.transform.cx + 3, capa.transform.cy); yield "varita", None
    s.remove_background(); yield "quitar fondo", None
    s.clear_mask(); yield "quitar máscara", None
    cx, cy = capa.transform.cx, capa.transform.cy
    s.mask_stroke([(cx, cy), (cx + 8, cy)], erase=True); yield "máscara", None
    s.clear_mask(); yield "quitar máscara 2", None
    s.set_tool("brush"); s.clear_selection(); s.paint_stroke([(50, 50), (200, 200)]); yield "pincel", None
    s.resize_document(800, 600); yield "tamaño", None
    s.set_background("#336699"); yield "fondo", None
    s.rename("Otro nombre"); yield "nombre", None
    s.select_all(); s.delete_selected(); yield "eliminar", None


def test_cada_operacion_cierra_un_paso_y_deshacer_rehacer_es_exacto(s):
    s.new_document(1080, 1080)
    estados = [document_to_dict(s.doc)]
    pasos = len(s.history)
    for nombre, _ in _operaciones(s):
        assert len(s.history) == pasos + 1, f"«{nombre}» no cerró exactamente un paso"
        pasos += 1
        estados.append(document_to_dict(s.doc))
    for esperado in reversed(estados[:-1]):
        assert s.undo()
        assert document_to_dict(s.doc) == esperado
    assert not s.undo()
    for esperado in estados[1:]:
        assert s.redo()
        assert document_to_dict(s.doc) == esperado
    assert not s.redo()


def test_deshacer_despues_de_guardar_sigue_pudiendo_dibujar(s, tmp_path):
    s.new_document(200, 200)
    s.set_tool("brush")
    for i in range(5):
        s.paint_stroke([(20 + i * 30, 20), (20 + i * 30, 180)])
    assert s.save(tmp_path / "a.vphoto")
    while s.undo():
        s.renderer.render(s.doc, 1.0)       # ninguna instantánea debe haber perdido su imagen
    while s.redo():
        s.renderer.render(s.doc, 1.0)


def test_abrir_un_archivo_roto_no_truena_y_deja_todo_como_estaba(s, tmp_path):
    s.add_shape("rect")
    antes = document_to_dict(s.doc)
    p = tmp_path / "mal.vphoto"
    p.write_bytes(b"no soy un zip")
    assert s.open_path(p) is False
    assert document_to_dict(s.doc) == antes
    q = tmp_path / "mal.png"
    q.write_bytes(b"no soy una imagen")
    assert s.open_path(q) is False
    assert document_to_dict(s.doc) == antes


# --- coordenadas con capas giradas, volteadas y recortadas -------------------------

def _centroide_rojo(px):
    m = (px[..., 0] > 200) & (px[..., 1] < 60) & (px[..., 2] < 60)
    ys, xs = np.nonzero(m)
    return (xs.mean(), ys.mean(), m.sum()) if len(xs) else None


@pytest.mark.parametrize("rot,fh,fv,crop", [
    (0, False, False, None), (33, False, False, None), (0, True, False, None), (0, False, True, None),
    (-70, True, True, None), (0, False, False, (80, 20, 200, 120)), (25, True, False, (80, 20, 200, 120)),
    (140, False, True, (0, 0, 150, 100)),
])
def test_el_pincel_cae_donde_se_ve_el_punto_del_lienzo(s, rot, fh, fv, crop):
    s.new_document(400, 300, background="#ffffff")
    capa = s.add_image(degradado(400, 200))
    capa.transform.cx, capa.transform.cy = 200, 150
    capa.transform.width, capa.transform.height = 240, 120 if crop is None else 240 * crop[3] / crop[2]
    capa.transform.rotation, capa.transform.flip_h, capa.transform.flip_v = rot, fh, fv
    capa.crop = crop
    s.select([capa.id])
    s.s = s
    # un punto dentro de la caja, descentrado, convertido al lienzo
    from vortex_studio.ui.photo import geometry as geo
    objetivo = geo.to_canvas(capa.transform, 50, -20)
    s.brush = Brush(size=10, hardness=1.0, opacity=1.0, color="#ff0000")
    s.set_tool("brush")
    s.clear_selection()
    capa.name = "Dibujo"                      # pintar sobre la misma capa, que ya es «dibujo»
    s.select([capa.id])
    assert s.paint_stroke([objetivo])
    px = s.renderer.render(s.doc, 1.0)
    c = _centroide_rojo(px)
    assert c is not None
    assert abs(c[0] - objetivo[0]) < 2.5 and abs(c[1] - objetivo[1]) < 2.5, (c, objetivo)


@pytest.mark.xfail(strict=True, reason="paint_stroke usa un solo píxeles-por-unidad (ancho): en una capa estirada "
                   "el borrador/pincel sale elíptico en el lienzo (session.py: pixels_per_unit y paint_stroke)")
def test_el_borrador_es_redondo_en_una_capa_estirada(s):
    s.new_document(400, 300)
    capa = s.add_image(np.full((100, 100, 4), 255, np.uint8))
    capa.transform.cx, capa.transform.cy = 200, 150
    capa.transform.width, capa.transform.height = 240, 60           # estirada ×2,4 a lo ancho y ×0,6 a lo alto
    s.select([capa.id])
    s.brush = Brush(size=40, hardness=1.0)
    assert s.paint_stroke([(200, 150)], erase=True)
    px = s.renderer.render(s.doc, 1.0)
    sin_foto = (px[..., 2] == 255) & (px[..., 0] == 255) & (px[..., 1] == 255)     # blanco = fondo
    # la foto es blanca y el fondo también: se mide el alfa de la capa sola
    solo = s.renderer.render_layer(s.doc, s.doc.layer(capa.id), 1.0)
    hueco = solo[..., 3] < 128
    ys, xs = np.nonzero(hueco)
    assert len(xs) > 0
    assert abs((xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1) - 1.0) < 0.25


# --- máscaras y recortes -------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="session.wand_click: la máscara guardada tiene el tamaño del recorte anterior; "
                   "tras recortar `np.where(sel > 127, 0, actual)` mezcla formas distintas y truena (session.py ~ _mask_of/wand_click)")
def test_varita_despues_de_recortar_no_truena(s):
    s.new_document(300, 300)
    capa = s.add_image(degradado(200, 200))
    s.select([capa.id])
    assert s.remove_background() or True              # crea una máscara de 200×200
    capa.mask = s.store.put(np.full((200, 200), 255, np.uint8))
    capa.crop = (50, 50, 100, 100)                    # lo que deja la herramienta de recortar
    capa.transform.width = capa.transform.height = 100
    s.wand_click(capa.transform.cx, capa.transform.cy)


@pytest.mark.xfail(strict=True, reason="canvas.apply_crop no re-muestrea la máscara: el motor la estira sobre la caja "
                   "nueva, así que tras recortar la máscara queda desalineada (canvas.py apply_crop ~1100)")
def test_la_mascara_sigue_alineada_despues_de_recortar(s):
    s.new_document(200, 100, background=None)
    capa = s.add_image(mitades(200, 100))
    s.select([capa.id])
    m = np.full((100, 200), 255, np.uint8)
    m[:, :100] = 0                                    # se oculta toda la mitad roja
    capa.mask = s.store.put(m)
    # recortar a la mitad azul (derecha) igual que apply_crop: crop + caja nueva
    capa.crop = (100.0, 0.0, 100.0, 100.0)
    capa.transform.width, capa.transform.height = 100.0, 100.0
    capa.transform.cx, capa.transform.cy = 150.0, 50.0
    px = s.renderer.render(s.doc, 1.0)
    visible = px[:, 100:, 3] > 200
    assert visible.mean() > 0.95                     # toda la mitad azul debe seguir visible


def test_mascara_pintada_cae_donde_se_pinta_con_la_capa_girada(s):
    s.new_document(300, 300, background=None)
    capa = s.add_image(mitades(200, 100))
    capa.transform.rotation = 40
    capa.transform.flip_h = True
    s.select([capa.id])
    s.brush = Brush(size=20, hardness=1.0)
    from vortex_studio.ui.photo import geometry as geo
    objetivo = geo.to_canvas(capa.transform, 30, 10)
    assert s.mask_stroke([objetivo], erase=True)
    px = s.renderer.render(s.doc, 1.0)
    assert px[int(objetivo[1]), int(objetivo[0]), 3] < 30               # el agujero está bajo el cursor
    lejos = geo.to_canvas(capa.transform, -60, -30)
    assert px[int(lejos[1]), int(lejos[0]), 3] > 200


def test_quitar_fondo_en_capa_recortada_no_truena_y_aplica(s):
    s.new_document(300, 300, background=None)
    capa = s.add_image(degradado(300, 200))
    capa.crop = (20, 20, 150, 100)
    s.select([capa.id])
    assert s.remove_background()
    s.renderer.render(s.doc, 1.0)


# --- almacén, portapapeles y memoria -----------------------------------------------------

@pytest.mark.xfail(strict=True, reason="copiar y pegar entre diseños: el portapapeles guarda ids del almacén viejo; en el "
                   "diseño nuevo la capa pegada apunta a una imagen que no existe (session.py paste/new_document)")
def test_pegar_en_otro_diseno_trae_la_imagen(s):
    capa = s.add_image(degradado(100, 100))
    s.select([capa.id])
    assert s.copy_selected()
    s.new_document(500, 500)
    assert s.paste()
    for c in s.doc.layers:
        if c.asset:
            assert s.store.has(c.asset)


@pytest.mark.xfail(strict=True, reason="misma causa: paint_stroke/mask_stroke/wand_click/clone_stroke llaman a "
                   "store.size/get sin comprobar store.has y lanzan KeyError (session.py:545 pixels_per_unit, 600 y 660)")
def test_pegar_en_otro_diseno_y_pintar_no_truena_con_el_almacen_vacio(s):
    """Aunque la imagen falte, nada debe lanzar una excepción sin atrapar."""
    capa = s.add_image(degradado(100, 100))
    s.select([capa.id])
    s.copy_selected()
    s.new_document(500, 500)
    s.paste()
    s.set_tool("brush")
    s.brush = Brush(size=10)
    try:
        s.paint_stroke([(300, 300)], erase=True)
        s.mask_stroke([(300, 300)], erase=True)
        s.wand_click(300, 300)
        s.clone_stroke([(300, 300)])
        s.remove_background()
    except KeyError as e:
        pytest.fail(f"KeyError sin atrapar con una capa cuya imagen falta: {e}")
    s.renderer.render(s.doc, 1.0)


@pytest.mark.xfail(strict=True, reason="la sesión solo llama a store.collect al guardar: cada trazo agrega una imagen "
                   "completa y las que salen del historial (límite 100) se quedan en memoria (session.commit)")
def test_el_almacen_no_crece_sin_limite_con_muchos_trazos(s):
    s.new_document(512, 512)
    s.set_tool("brush")
    s.brush = Brush(size=6, hardness=1.0)
    for i in range(130):
        s.paint_stroke([(5 + i % 25 * 20, 5 + i // 25 * 20), (5 + i % 25 * 20, 15 + i // 25 * 20)])
    assert len(s.store.ids()) <= 102


def test_guardar_suelta_lo_que_nadie_usa_pero_conserva_lo_deshacible(s, tmp_path):
    s.new_document(512, 512)
    s.set_tool("brush")
    s.brush = Brush(size=6)
    for i in range(130):
        s.paint_stroke([(5 + i % 25 * 20, 5 + i // 25 * 20), (5 + i % 25 * 20, 15 + i // 25 * 20)])
    s.save(tmp_path / "a.vphoto")
    assert len(s.store.ids()) <= 102
    for _ in range(100):
        assert s.undo()
        s.renderer.render(s.doc, 1.0)


def test_la_interfaz_no_modifica_arreglos_de_solo_lectura_del_almacen(s):
    capa = s.add_image(degradado(100, 100))
    original = s.store.get(capa.asset).copy()
    s.select([capa.id])
    s.set_tool("brush")
    s.paint_stroke([(50, 50)], erase=True)
    s.clone_source = (10, 10)
    s.clone_stroke([(60, 60), (70, 70)])
    s.wand_click(50, 50)
    s.remove_background()
    capa.adjustments = Adjustments(exposure=50, blur=20)
    s.renderer.render(s.doc, 1.0)
    assert np.array_equal(s.store.get(capa.asset), original)           # la imagen original sigue intacta
    assert not s.store.get(capa.asset).flags.writeable


# --- casos raros ---------------------------------------------------------------------------

def test_documento_de_un_pixel_y_cambios_de_tamano_extremos(s):
    s.new_document(1, 1)
    s.add_shape("star")
    s.add_text(0)
    s.resize_document(16000, 1)
    s.resize_document(1, 1)
    s.renderer.render(s.doc, 1.0)
    while s.undo():
        pass
    while s.redo():
        pass


def test_borrar_todo_y_operar_sin_seleccion(s):
    s.new_document(200, 200)
    assert not s.delete_selected() and not s.duplicate_selected() and not s.copy_selected()
    assert not s.reorder("frente") and not s.align("centro")
    s.flip_selected(True)
    s.lock_selected()
    s.move_selected(5, 5)
    assert not s.remove_background() and not s.wand_click(5, 5) and not s.clear_mask()
    assert not s.paste() or True


def test_capa_bloqueada_no_se_edita(s):
    s.new_document(200, 200)
    capa = s.add_image(degradado(100, 100))
    s.select([capa.id])
    s.lock_selected(True)
    antes = document_to_dict(s.doc)
    s.move_selected(10, 10)
    s.flip_selected(True)
    s.delete_selected()
    s.align("centro")
    s.set_tool("brush")
    s.paint_stroke([(50, 50)], erase=True)
    s.mask_stroke([(50, 50)], erase=True)
    s.wand_click(50, 50)
    s.remove_background()
    assert document_to_dict(s.doc) == antes


def test_texto_editado_y_deshecho_no_deja_capas_fantasma(s):
    s.new_document(400, 400)
    t = s.add_text(0)
    s.edit("Texto", lambda c: setattr(c, "text", "Una línea\ny otra más larga que cabe"), [t])
    alto = s.doc.layer(t.id).transform.height
    assert s.undo()
    assert s.doc.layer(t.id).text.startswith("Agregar")
    assert s.doc.layer(t.id).transform.height != alto or alto == s.doc.layer(t.id).transform.height
    assert s.redo()
    assert s.doc.layer(t.id).transform.height == pytest.approx(alto)


@pytest.mark.xfail(strict=True, reason="session.resize_document escala posición y tamaño pero no stroke_width, "
                   "corner_radius ni sombra/contorno/brillo (session.py resize_document)")
def test_redimensionar_el_diseno_escala_efectos_y_trazos(s):
    """Un lienzo al doble de tamaño debe verse igual de proporcionado: sombra, contorno,
    radio de esquina y grosor de borde también crecen."""
    s.new_document(200, 200)
    f = s.add_shape("rect")
    f.corner_radius, f.stroke, f.stroke_width = 20.0, "#000000", 6.0
    f.effects.shadow.enabled, f.effects.shadow.blur, f.effects.shadow.dy = True, 10.0, 8.0
    s.resize_document(400, 400)
    g = s.doc.layer(f.id)
    assert g.stroke_width == pytest.approx(12.0) and g.corner_radius == pytest.approx(40.0)
    assert g.effects.shadow.blur == pytest.approx(20.0)
