"""Exportar, guardar, abrir, soltar archivos, pegar y cerrar con cambios."""

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from ayudas import foto_de_prueba
from vortex_studio.photo import io as photo_io
from vortex_studio.photo import templates
from vortex_studio.photo.render import to_qimage


def esperar_export(foto, qapp):
    w = foto._export_worker
    if w is not None:
        w.wait(20000)
    for _ in range(5):
        qapp.processEvents()


@pytest.fixture
def con_contenido(s):
    s.new_document(200, 100)
    s.add_image(foto_de_prueba(100, 50))
    s.add_text(0)
    s.set_background("#2040a0")
    return s


@pytest.fixture
def png(tmp_path):
    ruta = tmp_path / "foto.png"
    to_qimage(foto_de_prueba(120, 80)).save(str(ruta))
    return ruta


# --- exportar -----------------------------------------------------------------------------

@pytest.mark.parametrize("fmt,ext", [("PNG", ".png"), ("JPG", ".jpg"), ("WEBP", ".webp")])
def test_exportar_en_cada_formato(foto, con_contenido, qapp, tmp_path, fmt, ext):
    foto.export_with(tmp_path / f"salida{ext}", fmt=fmt, quality=80)
    esperar_export(foto, qapp)
    img = QImage(str(tmp_path / f"salida{ext}"))
    assert not img.isNull() and (img.width(), img.height()) == (200, 100)
    assert foto.last_export.endswith(ext)


@pytest.mark.parametrize("escala,ancho", [(0.5, 100), (1.0, 200), (2.0, 400)])
def test_exportar_en_cada_tamano(foto, con_contenido, qapp, tmp_path, escala, ancho):
    foto.export_with(tmp_path / "e.png", scale=escala)
    esperar_export(foto, qapp)
    assert QImage(str(tmp_path / "e.png")).width() == ancho


def test_exportar_con_fondo_transparente(foto, con_contenido, qapp, tmp_path):
    foto.export_with(tmp_path / "t.png", transparent=True)
    esperar_export(foto, qapp)
    img = QImage(str(tmp_path / "t.png"))
    assert img.hasAlphaChannel() and img.pixelColor(0, 0).alpha() == 0
    foto.export_with(tmp_path / "o.png", transparent=False)
    esperar_export(foto, qapp)
    assert QImage(str(tmp_path / "o.png")).pixelColor(0, 0).alpha() == 255


def test_exportar_jpg_no_lleva_transparencia(foto, con_contenido, qapp, tmp_path):
    foto.export_with(tmp_path / "j.jpg", fmt="JPG", transparent=True)
    esperar_export(foto, qapp)
    assert not QImage(str(tmp_path / "j.jpg")).hasAlphaChannel()


def test_exportar_corrige_la_extension(foto, con_contenido, qapp, tmp_path):
    foto.export_with(tmp_path / "sin_ext", fmt="PNG")
    esperar_export(foto, qapp)
    assert (tmp_path / "sin_ext.png").exists()


def test_exportar_no_cambia_el_diseno_ni_el_historial(foto, con_contenido, qapp, tmp_path):
    n, bg = len(con_contenido.history), con_contenido.doc.background
    foto.export_with(tmp_path / "x.png", transparent=True)
    esperar_export(foto, qapp)
    assert len(con_contenido.history) == n and con_contenido.doc.background == bg


def test_exportar_no_bloquea_y_avisa(foto, con_contenido, qapp, tmp_path):
    w = foto.export_with(tmp_path / "a.png")
    assert foto.exporting()
    assert foto.export_with(tmp_path / "b.png") is None      # no se encima otra
    esperar_export(foto, qapp)
    assert not foto.exporting()


def test_un_error_al_exportar_no_tumba_la_ventana(foto, con_contenido, qapp, tmp_path):
    foto.export_with(tmp_path / "no_existe" / "x.png")
    esperar_export(foto, qapp)
    assert not foto.exporting()
    assert "No se pudo exportar" in foto.status.text()


def test_opciones_del_panel_exportar(foto, s):
    p = foto.export_popup
    assert p.options() == {"fmt": "PNG", "quality": 92, "scale": 1.0, "transparent": False}
    assert not p.quality.isEnabled()
    p.fmt.buttons["JPG"].click()
    assert p.quality.isEnabled() and not p.transparent.isEnabled()
    p.size.buttons[2.0].click()
    assert p.dims.text() == "2160 × 2160 px"
    p.fmt.buttons["WEBP"].click()
    p.transparent.setChecked(True)
    assert p.options()["transparent"] and p.options()["fmt"] == "WEBP"
    p.fmt.buttons["JPG"].click()
    assert not p.options()["transparent"]


def test_el_boton_exportar_emite_las_opciones(foto, s):
    recibido = []
    foto.export_popup.requested.connect(recibido.append)
    foto.export_popup.fmt.buttons["JPG"].click()
    foto.export_popup.btn.click()
    assert recibido and recibido[0]["fmt"] == "JPG"


def test_el_flujo_de_exportar_pide_la_ruta(foto, con_contenido, qapp, tmp_path, monkeypatch):
    from vortex_studio.ui.photo import window as win
    destino = str(tmp_path / "flujo.png")
    monkeypatch.setattr(win.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (destino, "")))
    foto._export_flow({"fmt": "PNG", "quality": 90, "scale": 1.0, "transparent": False})
    esperar_export(foto, qapp)
    assert (tmp_path / "flujo.png").exists()


def test_cancelar_el_dialogo_de_exportar(foto, con_contenido, tmp_path, monkeypatch):
    from vortex_studio.ui.photo import window as win
    monkeypatch.setattr(win.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    foto._export_flow({"fmt": "PNG", "quality": 90, "scale": 1.0, "transparent": False})
    assert not foto.exporting()


# --- guardar y abrir ---------------------------------------------------------------------------

def test_guardar_y_abrir_un_diseno(foto, con_contenido, tmp_path):
    ruta = tmp_path / "mio.vphoto"
    assert foto.save_as(ruta)
    assert ruta.exists() and not con_contenido.dirty
    n = len(con_contenido.doc.layers)
    con_contenido.new_document(10, 10)
    assert foto.open_file(ruta)
    d = con_contenido.doc
    assert (d.width, d.height, len(d.layers), d.background) == (200, 100, n, "#2040a0")
    assert con_contenido.path == ruta and not con_contenido.dirty
    assert not con_contenido.history.can_undo


def test_guardar_sin_ruta_pide_una(foto, con_contenido, tmp_path, monkeypatch):
    from vortex_studio.ui.photo import window as win
    destino = str(tmp_path / "pedido.vphoto")
    monkeypatch.setattr(win.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (destino, "")))
    assert foto.save()
    assert (tmp_path / "pedido.vphoto").exists()
    n = len(list(tmp_path.iterdir()))
    assert foto.save()                 # ya tiene ruta: no vuelve a preguntar
    assert len(list(tmp_path.iterdir())) == n


def test_guardar_agrega_la_extension(foto, con_contenido, tmp_path):
    assert foto.save_as(tmp_path / "sin")
    assert (tmp_path / "sin.vphoto").exists()


def test_guardar_cancelado(foto, con_contenido, monkeypatch):
    from vortex_studio.ui.photo import window as win
    monkeypatch.setattr(win.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    assert not foto.save()
    assert con_contenido.dirty


def test_abrir_una_imagen_crea_un_diseno_de_su_tamano(foto, s, png):
    assert foto.open_file(png)
    assert (s.doc.width, s.doc.height) == (120, 80)
    assert len(s.doc.layers) == 1 and s.doc.name == "foto"
    assert not s.dirty


def test_abrir_un_archivo_roto_avisa_y_no_cambia_nada(foto, con_contenido, tmp_path):
    malo = tmp_path / "roto.vphoto"
    malo.write_bytes(b"esto no es un zip")
    con_contenido.dirty = False
    assert not foto.open_file(malo)
    assert con_contenido.doc.width == 200
    assert "No se pudo abrir" in foto.status.text()


def test_abrir_algo_que_no_existe(foto, con_contenido, tmp_path):
    con_contenido.dirty = False
    assert not foto.open_file(tmp_path / "nada.png")
    assert con_contenido.doc.width == 200


def test_el_nombre_editable_renombra(foto, s):
    foto.name_edit.setText("Mi cartel")
    foto.name_edit.editingFinished.emit()
    assert s.doc.name == "Mi cartel"
    assert "Mi cartel" in foto.windowTitle()
    foto.name_edit.setText("   ")
    foto.name_edit.editingFinished.emit()
    assert s.doc.name == "Diseño sin título"


def test_el_titulo_marca_los_cambios(foto, s):
    assert not foto.windowTitle().startswith("*")
    s.add_shape("rect")
    assert foto.windowTitle().startswith("*")


# --- soltar archivos y pegar --------------------------------------------------------------------------

def soltar(canvas, rutas, x=300.0, y=400.0):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(r)) for r in rutas])
    pt = canvas.to_screen(x, y)
    ev = QDropEvent(pt, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    canvas.dropEvent(ev)
    return ev


def test_soltar_una_imagen_la_agrega_donde_se_suelta(foto, s, lienzo, png):
    soltar(lienzo, [png], 300, 400)
    assert len(s.doc.layers) == 1
    c = s.doc.layers[0]
    assert (c.transform.cx, c.transform.cy) == pytest.approx((300, 400))
    assert s.selection == [c.id]


def test_soltar_varias_imagenes(foto, s, lienzo, png, tmp_path):
    otra = tmp_path / "otra.png"
    to_qimage(foto_de_prueba(50, 50)).save(str(otra))
    soltar(lienzo, [png, otra])
    assert len(s.doc.layers) == 2
    assert s.doc.layers[1].transform.cx == s.doc.layers[0].transform.cx + 24


def test_soltar_algo_que_no_es_imagen_no_hace_nada(foto, s, lienzo, tmp_path):
    txt = tmp_path / "nota.txt"
    txt.write_text("hola")
    ev = soltar(lienzo, [txt])
    assert s.doc.layers == []


def test_soltar_una_imagen_rota_no_truena(foto, s, lienzo, tmp_path):
    mala = tmp_path / "mala.png"
    mala.write_bytes(b"no soy un png")
    soltar(lienzo, [mala])
    assert s.doc.layers == []
    assert "No se pudo" in foto.status.text()


def test_soltar_un_diseno_lo_abre(foto, con_contenido, lienzo, tmp_path):
    ruta = tmp_path / "d.vphoto"
    foto.save_as(ruta)
    con_contenido.new_document(50, 50)
    soltar(lienzo, [ruta])
    assert con_contenido.doc.width == 200


def test_el_lienzo_acepta_arrastres_de_imagenes(lienzo):
    assert lienzo.acceptDrops()
    assert lienzo._accepts("/x/y.PNG") and lienzo._accepts("a.vphoto")
    assert not lienzo._accepts("a.txt") and not lienzo._accepts("")


def test_pegar_con_la_accion_de_la_ventana(foto, s):
    QApplication.clipboard().setImage(to_qimage(foto_de_prueba(30, 30)))
    foto.actions_by_name["paste"].trigger()
    assert len(s.doc.layers) == 1


def test_pegar_sin_nada_avisa(foto, s):
    QApplication.clipboard().clear()
    foto.actions_by_name["paste"].trigger()
    assert "nada que pegar" in foto.status.text()


def test_subir_con_el_dialogo(foto, s, png, monkeypatch):
    from vortex_studio.ui.photo import window as win
    monkeypatch.setattr(win.QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([str(png)], "")))
    foto.pick_images()
    assert len(s.doc.layers) == 1
    assert len(foto.upload_panel.thumb_buttons) == 1
    foto.upload_panel.thumb_buttons[0].click()          # volver a usarla
    assert len(s.doc.layers) == 2


# --- cerrar con cambios sin guardar ---------------------------------------------------------------------

def responder(monkeypatch, valor, llamadas):
    def q(*a, **k):
        llamadas.append(a[1] if len(a) > 1 else "")
        return valor
    monkeypatch.setattr(QMessageBox, "question", staticmethod(q))


def test_cerrar_sin_cambios_no_pregunta(foto, monkeypatch):
    llamadas = []
    responder(monkeypatch, QMessageBox.Cancel, llamadas)
    assert foto.close()
    assert llamadas == []


def test_cerrar_con_cambios_y_cancelar(foto, s, monkeypatch):
    s.add_shape("rect")
    llamadas = []
    responder(monkeypatch, QMessageBox.Cancel, llamadas)
    foto.close()
    assert foto.isVisible() and llamadas == ["Hay cambios sin guardar"]


def test_cerrar_con_cambios_y_descartar(foto, s, monkeypatch):
    s.add_shape("rect")
    responder(monkeypatch, QMessageBox.Discard, [])
    foto.close()
    assert not foto.isVisible()


def test_cerrar_con_cambios_y_guardar(foto, s, tmp_path, monkeypatch):
    s.add_shape("rect")
    s.path = tmp_path / "g.vphoto"
    responder(monkeypatch, QMessageBox.Save, [])
    foto.close()
    assert not foto.isVisible() and (tmp_path / "g.vphoto").exists()


def test_cerrar_y_guardar_pero_cancelar_el_guardado_no_cierra(foto, s, monkeypatch):
    from vortex_studio.ui.photo import window as win
    s.add_shape("rect")
    responder(monkeypatch, QMessageBox.Save, [])
    monkeypatch.setattr(win.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    foto.close()
    assert foto.isVisible()


def test_cerrar_termina_la_edicion_de_texto_primero(foto, s, lienzo, monkeypatch):
    t = s.add_text(0)
    lienzo.flush()
    lienzo.begin_text_edit(t.id)
    lienzo.editor().setPlainText("pendiente")
    s.dirty = False
    responder(monkeypatch, QMessageBox.Discard, [])
    foto.close()
    assert s.doc.layer(t.id).text == "pendiente"       # el cambio entró al historial antes de preguntar


def test_nuevo_diseno_pregunta_si_hay_cambios(foto, s, monkeypatch):
    s.add_shape("rect")
    llamadas = []
    responder(monkeypatch, QMessageBox.Cancel, llamadas)
    assert not foto.new_design(500, 500)
    assert s.doc.width == 1080 and llamadas
    responder(monkeypatch, QMessageBox.Discard, [])
    assert foto.new_design(500, 500)
    assert s.doc.width == 500 and s.doc.layers == []


def test_abrir_pregunta_si_hay_cambios(foto, s, png, monkeypatch):
    s.add_shape("rect")
    responder(monkeypatch, QMessageBox.Cancel, [])
    assert not foto.open_file(png)
    assert len(s.doc.layers) == 1
