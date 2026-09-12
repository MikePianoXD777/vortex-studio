"""Atajos de teclado configurables: el mapa, el archivo, la ventana y el editor."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from vortex_studio.ui.shortcuts import (
    DEFAULTS,
    ShortcutsDialog,
    defaults,
    load_shortcuts,
    normalize,
    save_shortcuts,
    shortcuts_path,
    validate,
)

PORTABLE = QKeySequence.PortableText


@pytest.fixture
def config(tmp_path, monkeypatch, qapp):
    carpeta = tmp_path / "config"
    monkeypatch.setenv("VORTEX_CONFIG_DIR", str(carpeta))
    return carpeta


def escribir(config, pedidos):
    config.mkdir(parents=True, exist_ok=True)
    (config / "atajos.json").write_text(
        json.dumps({"version": 1, "atajos": pedidos}), encoding="utf-8")


def tecla(accion) -> str:
    return accion.shortcut().toString(PORTABLE)


@pytest.fixture
def nueva_ventana(qapp):
    """Crea ventanas después de preparar la configuración, y las cierra."""
    from vortex_studio.ui import MainWindow

    abiertas = []

    def crear():
        w = MainWindow()
        abiertas.append(w)
        return w

    yield crear
    for w in abiertas:
        w._dirty = False
        w.close()


# --- el mapa de fábrica ---------------------------------------------------

def test_los_de_fabrica_no_tienen_problemas(qapp):
    """Sin repetidos, sin Ctrl+Alt, y todas las teclas se entienden."""
    mapa, problemas = validate(defaults())
    assert problemas == []
    assert mapa == defaults()


def test_los_de_fabrica_se_entienden_todos(qapp):
    for clave, (_, tecla) in DEFAULTS.items():
        assert normalize(tecla), f"{clave}: no se entiende «{tecla}»"


def test_una_secuencia_de_dos_teclas_no_se_acepta(qapp):
    assert normalize("Ctrl+K, Ctrl+X") is None
    assert normalize("") == ""
    assert normalize(None) is None


# --- cargar del archivo ---------------------------------------------------

def test_sin_archivo_salen_los_de_siempre(config):
    mapa, problemas = load_shortcuts()
    assert mapa == defaults()
    assert problemas == []


def test_un_cambio_valido_se_aplica(config):
    escribir(config, {"editar.cortar": "Ctrl+B"})
    mapa, problemas = load_shortcuts()
    assert mapa["editar.cortar"] == "Ctrl+B"
    assert mapa["editar.duplicar"] == defaults()["editar.duplicar"]
    assert problemas == []


def test_una_accion_desconocida_se_ignora(config):
    escribir(config, {"editar.teletransportar": "Ctrl+B"})
    mapa, problemas = load_shortcuts()
    assert mapa == defaults()
    assert any("teletransportar" in p for p in problemas)


def test_una_tecla_que_no_existe_se_rechaza(config):
    escribir(config, {"editar.cortar": "Ctrl+Patata"})
    mapa, problemas = load_shortcuts()
    assert mapa["editar.cortar"] == defaults()["editar.cortar"]
    assert any("no entiendo" in p for p in problemas)


def test_ctrl_alt_se_rechaza(config):
    escribir(config, {"editar.cortar": "Ctrl+Alt+K"})
    mapa, problemas = load_shortcuts()
    assert mapa["editar.cortar"] == "Ctrl+K"
    assert any("AltGr" in p for p in problemas)


def test_dos_acciones_con_la_misma_tecla(config):
    escribir(config, {"editar.cortar": "Ctrl+B", "editar.duplicar": "Ctrl+B"})
    mapa, problemas = load_shortcuts()
    con_b = [c for c, t in mapa.items() if t == "Ctrl+B"]
    assert con_b == ["editar.cortar"]
    assert any("piden Ctrl+B" in p for p in problemas)


def test_se_le_puede_quitar_la_tecla_a_una_accion(config):
    escribir(config, {"herramienta.navaja": ""})
    mapa, problemas = load_shortcuts()
    assert mapa["herramienta.navaja"] == ""
    assert problemas == []


def test_una_tecla_pedida_desplaza_a_la_de_fabrica(config):
    """Poner C en otra acción fue una decisión: la navaja se queda sin tecla."""
    escribir(config, {"editar.duplicar": "C"})
    mapa, problemas = load_shortcuts()
    assert mapa["editar.duplicar"] == "C"
    assert mapa["herramienta.navaja"] == ""
    assert any("quedó sin atajo" in p for p in problemas)


@pytest.mark.parametrize("pedidos", [
    {"editar.cortar": "C", "editar.duplicar": "V", "reproducir.play": "C"},
    {"navegar.inicio": "End", "navegar.final": "Home"},
    {k: "Ctrl+B" for k in list(DEFAULTS)[:6]},
])
def test_nunca_quedan_teclas_repetidas(qapp, pedidos):
    mapa, _ = validate(pedidos)
    usadas = [t for t in mapa.values() if t]
    assert len(usadas) == len(set(usadas))
    assert list(mapa) == list(DEFAULTS)


def test_un_archivo_danado_no_truena(config):
    config.mkdir(parents=True)
    (config / "atajos.json").write_text("{esto no es json", encoding="utf-8")
    mapa, problemas = load_shortcuts()
    assert mapa == defaults()
    assert any("dañado" in p for p in problemas)


def test_un_archivo_con_otra_forma_no_truena(config):
    config.mkdir(parents=True)
    (config / "atajos.json").write_text('["hola"]', encoding="utf-8")
    mapa, problemas = load_shortcuts()
    assert mapa == defaults()
    assert problemas


# --- guardar --------------------------------------------------------------

def test_guardar_y_volver_a_leer(config):
    mapa = defaults()
    mapa["reproducir.play"] = "P"
    save_shortcuts(mapa)
    leido, problemas = load_shortcuts()
    assert leido == mapa
    assert problemas == []


def test_se_guarda_en_la_carpeta_de_configuracion(config):
    ruta = save_shortcuts(defaults())
    assert ruta == shortcuts_path()
    assert ruta.parent == config
    assert not list(config.glob("*.tmp"))


def test_el_archivo_trae_todas_las_acciones(config):
    save_shortcuts({"editar.cortar": "Ctrl+B"})
    datos = json.loads(shortcuts_path().read_text(encoding="utf-8"))
    assert set(datos["atajos"]) == set(DEFAULTS)
    assert datos["atajos"]["editar.cortar"] == "Ctrl+B"


# --- la ventana -----------------------------------------------------------

def test_la_ventana_usa_el_mapa(config, nueva_ventana):
    escribir(config, {"editar.cortar": "Ctrl+B"})
    w = nueva_ventana()
    assert tecla(w._actions["editar.cortar"]) == "Ctrl+B"


def test_cada_accion_del_mapa_existe_en_la_ventana(ventana):
    assert set(ventana._actions) == set(DEFAULTS)


def test_ninguna_accion_tiene_tecla_fuera_del_mapa(ventana):
    """Una tecla escrita a mano no se podría cambiar desde el editor."""
    from PySide6.QtGui import QAction

    for accion in ventana.findChildren(QAction):
        if not accion.shortcut().isEmpty():
            assert accion.data() in DEFAULTS, f"«{accion.text()}» tiene tecla sin clave"


def test_escribir_una_tecla_a_mano_truena(ventana):
    with pytest.raises(KeyError):
        ventana._action(ventana.menuBar().addMenu("x"), "Algo", "Ctrl+B", lambda: None)


def test_cambiar_atajos_en_vivo(ventana):
    mapa = dict(ventana.shortcuts)
    mapa["reproducir.play"] = "P"
    ventana.apply_shortcuts(mapa)

    play = ventana._actions["reproducir.play"]
    assert tecla(play) == "P"
    assert play in ventana._plain_actions
    assert ventana.shortcuts["reproducir.play"] == "P"


def test_una_tecla_con_ctrl_deja_de_apagarse_al_escribir(ventana):
    mapa = dict(ventana.shortcuts)
    mapa["reproducir.play"] = "Ctrl+Space"
    ventana.apply_shortcuts(mapa)
    assert ventana._actions["reproducir.play"] not in ventana._plain_actions


def test_los_problemas_se_avisan_en_la_barra(config, nueva_ventana):
    escribir(config, {"editar.cortar": "Ctrl+Alt+K"})
    w = nueva_ventana()
    assert w.shortcut_problems
    assert "Atajos" in w.statusBar().currentMessage()


# --- navegación como acciones ---------------------------------------------

def test_la_flecha_avanza_un_cuadro(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana._actions["navegar.cuadro_adelante"].trigger()
    assert ventana.timeline.playhead == pytest.approx(1.0 + 1 / 30, abs=1e-6)


def test_saltos_de_uno_y_diez_segundos(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana._actions["navegar.segundo_adelante"].trigger()
    assert ventana.timeline.playhead == pytest.approx(3.0)
    ventana._actions["navegar.diez_atras"].trigger()
    assert ventana.timeline.playhead == pytest.approx(0.0)


def test_inicio_y_final(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._actions["navegar.final"].trigger()
    assert ventana.timeline.playhead == pytest.approx(ventana.sequence.duration)
    ventana._actions["navegar.inicio"].trigger()
    assert ventana.timeline.playhead == pytest.approx(0.0)


def test_la_navegacion_se_apaga_al_escribir_aunque_lleve_ctrl(ventana):
    """Ctrl+← salta una palabra en un cuadro de texto: no se la robamos."""
    ctrl_izq = ventana._actions["navegar.diez_atras"]
    assert tecla(ctrl_izq) == "Ctrl+Left"
    ventana._focus_changed(None, ventana.text_panel._text)
    assert not ctrl_izq.isEnabled()
    assert not ventana._actions["navegar.cuadro_adelante"].isEnabled()

    ventana._focus_changed(ventana.text_panel._text, ventana.timeline)
    assert ctrl_izq.isEnabled()


def test_en_un_deslizador_solo_se_apagan_las_flechas(ventana):
    """Las flechas mueven el deslizador; Espacio tiene que seguir reproduciendo."""
    deslizador = ventana.color_panel._brightness._slider
    ventana._focus_changed(None, deslizador)
    assert not ventana._actions["navegar.cuadro_adelante"].isEnabled()
    assert ventana._actions["reproducir.play"].isEnabled()
    assert ventana._actions["herramienta.navaja"].isEnabled()


def test_escape_sigue_deseleccionando(ventana, media):
    ventana._place_video(media["mudo"])
    assert ventana.timeline.selected is not None
    QTest.keyClick(ventana, Qt.Key_Escape)
    assert ventana.timeline.selected is None


# --- el editor de atajos --------------------------------------------------

def test_el_editor_guarda_y_la_ventana_cambia(config, ventana):
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo.set_value("editar.cortar", "Ctrl+B")
    assert dialogo.apply()

    assert load_shortcuts()[0]["editar.cortar"] == "Ctrl+B"
    ventana.apply_shortcuts(dialogo.mapping)
    assert tecla(ventana._actions["editar.cortar"]) == "Ctrl+B"


def test_el_editor_no_guarda_teclas_repetidas(config, ventana):
    """No se arregla solo: se dice qué choca y decide el usuario."""
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo.set_value("editar.cortar", "Ctrl+D")        # ya es de Duplicar
    assert not dialogo.apply()
    assert not shortcuts_path().exists()
    assert "Ctrl+D" in dialogo._problemas.text()


def test_el_editor_rechaza_ctrl_alt(config, ventana):
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo.set_value("editar.cortar", "Ctrl+Alt+Q")
    assert not dialogo.apply()
    assert "AltGr" in dialogo._problemas.text()


def test_restablecer_todo(config, ventana):
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo.set_value("editar.cortar", "Ctrl+B")
    dialogo.set_value("herramienta.navaja", "")
    dialogo.reset_defaults()
    assert dialogo.values() == defaults()


def test_buscar_filtra_las_filas(ventana):
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo._buscar.setText("marcador")
    visibles = dialogo.visible_keys()
    assert 0 < len(visibles) < len(DEFAULTS)
    assert all("marcador" in DEFAULTS[c][0].lower() for c in visibles)


def test_buscar_por_tecla(ventana):
    dialogo = ShortcutsDialog(ventana, ventana.shortcuts)
    dialogo._buscar.setText("ctrl+k")
    assert "editar.cortar" in dialogo.visible_keys()


def test_el_editor_se_abre_desde_el_menu(ventana):
    assert "editar.atajos" in ventana._actions
    assert ventana._actions["editar.atajos"].text().startswith("Atajos")
