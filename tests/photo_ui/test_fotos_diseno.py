"""Crear diseños, tamaños, lanzador y conexión con la aplicación."""

import subprocess
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ayudas import foto_de_prueba
from vortex_studio.photo import templates
from vortex_studio.photo.document import KIND_IMAGE, KIND_SHAPE, KIND_TEXT


@pytest.mark.parametrize("grupo,nombre,w,h", templates.SIZES)
def test_crear_un_diseno_de_cada_tamano(foto, s, lienzo, grupo, nombre, w, h):
    assert foto.new_design(w, h, nombre)
    assert (s.doc.width, s.doc.height, s.doc.name) == (w, h, nombre)
    lienzo.flush()
    assert lienzo._frame is not None
    r = lienzo.canvas_rect()
    assert r.width() <= lienzo.width() + 1 and r.height() <= lienzo.height() + 1
    assert f"{w} × {h}" in foto.status.text()


def test_el_menu_archivo_crea_cada_tamano(foto, s):
    assert len(foto.new_size_actions) == len(templates.SIZES)
    for a, (g, n, w, h) in zip(foto.new_size_actions, templates.SIZES):
        a.trigger()
        assert (s.doc.width, s.doc.height) == (w, h)


def test_tamano_personalizado_se_limita(s):
    s.new_document(0, -4)
    assert (s.doc.width, s.doc.height) == (1, 1)
    s.new_document(10**6, 10**6)
    assert (s.doc.width, s.doc.height) == (16000, 16000)


def test_agregar_cada_clase_de_elemento(foto, s):
    s.add_image(foto_de_prueba())
    s.add_text(0)
    s.add_shape("heart")
    assert [c.kind for c in s.doc.layers] == [KIND_IMAGE, KIND_TEXT, KIND_SHAPE]


@pytest.mark.parametrize("i", [0, 1, 2])
def test_los_tres_botones_de_texto(foto, s, i):
    foto.show_panel("texto")
    foto.text_panel.buttons[i].click()
    assert s.doc.layers[-1].kind == KIND_TEXT
    assert s.selection == [s.doc.layers[-1].id]


@pytest.mark.parametrize("forma", ["rect", "ellipse", "triangle", "star", "line", "arrow", "heart"])
def test_cada_forma_del_panel(foto, s, forma):
    foto.show_panel("elementos")
    foto.elements_panel.buttons[forma].click()
    assert s.doc.layers[-1].shape == forma
    assert not foto.elements_panel.buttons[forma].icon().isNull()


def test_el_texto_se_adapta_a_un_lienzo_grande(s):
    s.new_document(2160, 2160)
    t = s.add_text(0)
    assert t.font_size > 96


def test_el_texto_cabe_en_un_lienzo_chico(s):
    s.new_document(200, 200)
    t = s.add_text(0)
    assert t.transform.width <= 200 * 0.9


def test_color_de_fondo_y_transparente(foto, s):
    p = foto.design_panel
    p.bg_swatches["#ff3131"].click()
    assert s.doc.background == "#ff3131"
    p.btn_transparent.click()
    assert s.doc.background is None
    foto.canvas.flush()
    s.undo()
    assert s.doc.background == "#ff3131"


def test_cambiar_tamano_adaptando_el_contenido(s):
    t = s.add_text(0)
    f = s.add_shape("rect")
    ancho = f.transform.width
    s.resize_document(2160, 1080)             # el doble de ancho, misma altura
    assert f.transform.cx == pytest.approx(1080)      # x se duplicó
    assert f.transform.width == pytest.approx(ancho)  # la escala es la menor (1)
    s.resize_document(540, 540)
    assert f.transform.width == pytest.approx(ancho * 0.25)   # la menor de 540/2160 y 540/1080
    assert s.history.undo_label == "Cambiar tamaño"
    s.undo()
    assert s.doc.width == 2160


def test_cambiar_tamano_sin_adaptar(s):
    f = s.add_shape("rect")
    cx = f.transform.cx
    s.resize_document(500, 500, adapt=False)
    assert f.transform.cx == cx and (s.doc.width, s.doc.height) == (500, 500)


def test_cambiar_al_mismo_tamano_no_agrega_paso(s):
    n = s.history._pos
    s.resize_document(1080, 1080)
    assert s.history._pos == n


def test_cambiar_tamano_con_el_dialogo(foto, s, monkeypatch):
    from vortex_studio.ui.photo.dialogs import ResizeDialog

    def exec_(self):
        self.picker.lock.setChecked(False)
        self.picker.w.setValue(800)
        self.picker.h.setValue(600)
        self.adapt.setChecked(True)
        return QDialog.Accepted
    monkeypatch.setattr(ResizeDialog, "exec", exec_)
    foto.show_resize()
    assert (s.doc.width, s.doc.height) == (800, 600)


def test_cancelar_el_dialogo_de_tamano(foto, s, monkeypatch):
    from vortex_studio.ui.photo.dialogs import ResizeDialog
    monkeypatch.setattr(ResizeDialog, "exec", lambda self: QDialog.Rejected)
    foto.show_resize()
    assert s.doc.width == 1080


def test_nuevo_diseno_con_el_dialogo(foto, s, monkeypatch):
    from vortex_studio.ui.photo.dialogs import NewDesignDialog

    def exec_(self):
        self.list.setCurrentRow(1)
        self.name.setText("Historia")
        return QDialog.Accepted
    monkeypatch.setattr(NewDesignDialog, "exec", exec_)
    foto.show_new()
    assert (s.doc.width, s.doc.height, s.doc.name) == (*templates.SIZES[1][2:], "Historia")


def test_proporcion_bloqueada_en_el_selector(qapp):
    from vortex_studio.ui.photo.dialogs import SizePicker
    p = SizePicker(200, 100)
    p.w.setValue(400)
    assert p.values() == (400, 200)
    p.lock.setChecked(False)
    p.h.setValue(50)
    assert p.values() == (400, 50)


def test_los_paneles_de_la_barra_izquierda(foto):
    for clave in foto.panels:
        foto.toggle_panel(clave)
        assert foto.left_frame.isVisible()
        assert foto.left_stack.currentWidget() is foto.panels[clave]
        assert foto.side_buttons[clave].isChecked()
    foto.toggle_panel("capas")                  # el mismo otra vez: se pliega
    assert not foto.left_frame.isVisible()


def test_los_atajos_existen(foto):
    esperados = {"undo": "Ctrl+Z", "save": "Ctrl+S", "export": "Ctrl+E", "fit": "Ctrl+0",
                 "zoom100": "Ctrl+1", "duplicate": "Ctrl+D", "copy": "Ctrl+C", "paste": "Ctrl+V",
                 "cut": "Ctrl+X", "text": "T", "tool_brush": "B", "tool_erase": "E",
                 "tool_move": "V", "crop": "C", "delete": "Del"}
    for nombre, tecla in esperados.items():
        claves = [k.toString() for k in foto.actions_by_name[nombre].shortcuts()]
        assert tecla in claves, (nombre, claves)
    redo = [k.toString() for k in foto.actions_by_name["redo"].shortcuts()]
    assert "Ctrl+Shift+Z" in redo and "Ctrl+Y" in redo
    zin = [k.toString() for k in foto.actions_by_name["zoom_in"].shortcuts()]
    assert "Ctrl++" in zin
    assert "Ctrl+-" in [k.toString() for k in foto.actions_by_name["zoom_out"].shortcuts()]


def test_deshacer_y_rehacer_de_la_ventana(foto, s):
    s.add_shape("rect")
    assert foto.btn_undo.isEnabled() and not foto.btn_redo.isEnabled()
    foto.actions_by_name["undo"].trigger()
    assert foto.btn_redo.isEnabled() and not foto.btn_undo.isEnabled()
    foto.actions_by_name["redo"].trigger()
    assert len(s.doc.layers) == 1
    assert "Agregar forma" in foto.btn_undo.toolTip()


def test_los_atajos_de_copiar_duplicar_y_borrar(foto, s):
    a = s.add_shape("rect")
    foto.actions_by_name["duplicate"].trigger()
    assert len(s.doc.layers) == 2
    foto.actions_by_name["copy"].trigger()
    foto.actions_by_name["paste"].trigger()
    assert len(s.doc.layers) == 3
    foto.actions_by_name["delete"].trigger()
    assert len(s.doc.layers) == 2
    foto.actions_by_name["select_all"].trigger()
    foto.actions_by_name["delete"].trigger()
    assert s.doc.layers == []


def test_el_zoom_de_la_ventana(foto, lienzo):
    foto.actions_by_name["zoom100"].trigger()
    assert lienzo.zoom == 1.0 and foto.zoom_label.text() == "100 %"
    foto.actions_by_name["fit"].trigger()
    assert lienzo.zoom < 1.0
    z = lienzo.zoom
    foto.actions_by_name["zoom_in"].trigger()
    assert lienzo.zoom > z


def test_el_menu_contextual_del_lienzo(foto, s, lienzo):
    a = s.add_shape("rect")
    m = lienzo.build_context_menu()
    assert m._acciones["borrar"].isEnabled()
    m._acciones["duplicar"].trigger()
    assert len(s.doc.layers) == 2
    m._acciones["frente"].trigger()
    s.clear_selection()
    m2 = lienzo.build_context_menu()
    assert not m2._acciones["borrar"].isEnabled()


# --- lanzador y aplicación ----------------------------------------------------------------------------------

def test_la_tarjeta_de_fotos_esta_activa(qapp):
    from vortex_studio.ui import launcher
    ventana = launcher.Launcher("2.0")
    tarjetas = {t.mode: t for t in ventana.findChildren(launcher.ModeCard)}
    assert set(tarjetas) == {launcher.VIDEO, launcher.FOTOS}
    assert tarjetas[launcher.FOTOS]._enabled and not tarjetas[launcher.FOTOS].note
    tarjetas[launcher.FOTOS].clicked.emit(launcher.FOTOS)
    assert ventana.choice == launcher.FOTOS
    ventana.close()


def test_el_launcher_acepta_las_dos_opciones(qapp):
    from vortex_studio.ui import launcher
    v = launcher.Launcher("2.0")
    v._pick(launcher.VIDEO)
    assert v.choice == launcher.VIDEO
    v.close()


def test_el_launcher_no_carga_el_editor_de_fotos():
    codigo = ("import sys, vortex_studio.ui.launcher, vortex_studio.ui; "
              "print('vortex_studio.ui.photo.window' in sys.modules)")
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                            env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen",
                                 "PYTHONPATH": "src"}, check=True)
    assert salida.stdout.strip() == "False"


def test_photowindow_se_importa_bajo_demanda():
    import vortex_studio.ui.photo as paquete
    from vortex_studio.ui.photo.window import PhotoWindow
    assert paquete.PhotoWindow is PhotoWindow
    with pytest.raises(AttributeError):
        paquete.NoExiste  # noqa: B018


def test_la_prueba_de_humo_arma_la_ventana_de_fotos(qapp):
    from vortex_studio import app
    try:
        import av  # noqa: F401
    except ImportError:
        pytest.skip("sin PyAV la prueba de humo del video no corre")
    assert app.smoke_test(qapp) == 0
