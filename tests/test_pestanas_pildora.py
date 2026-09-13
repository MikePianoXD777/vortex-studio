"""Las pestañas en píldora del panel de propiedades (diseño de la beta)."""

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QLabel, QTabWidget, QWidget

from vortex_studio.ui.widgets import FlowLayout, PillTabs


def _pestanas(n=4):
    tabs = QTabWidget()
    for i in range(n):
        tabs.addTab(QLabel(str(i)), f"Página{i}")
    return tabs


# --- que haya una píldora por pestaña ---------------------------------------

def test_una_pildora_por_pestana_con_su_titulo(ventana):
    tabs = ventana.panel._tabs
    pills = ventana.panel.pills
    assert [pills.button(i).text() for i in range(tabs.count())] == \
        [tabs.tabText(i) for i in range(tabs.count())]


def test_la_barra_vieja_no_se_ve(ventana):
    assert ventana.panel._tabs.tabBar().isHidden()


def test_pildoras_sueltas_toman_los_titulos(qapp):
    tabs = _pestanas(3)
    pills = PillTabs(tabs)
    assert [pills.button(i).text() for i in range(3)] == ["Página0", "Página1", "Página2"]


# --- que cambien de página -------------------------------------------------

def test_clic_en_pildora_cambia_la_pagina(ventana):
    panel = ventana.panel
    panel.pills.button(panel._tabs.indexOf(panel.color)).click()
    assert panel.current_is(panel.color)


def test_mostrar_pagina_marca_su_pildora(ventana):
    panel = ventana.panel
    panel.show_page(panel.mask)
    indice = panel._tabs.indexOf(panel.mask)
    marcadas = [i for i in range(panel._tabs.count()) if panel.pills.button(i).isChecked()]
    assert marcadas == [indice]


def test_solo_una_pildora_marcada(qapp):
    tabs = _pestanas(4)
    pills = PillTabs(tabs)
    for i in (2, 0, 3):
        pills.button(i).click()
        assert tabs.currentIndex() == i
        assert sum(pills.button(j).isChecked() for j in range(4)) == 1


# --- que se apaguen con su pestaña -----------------------------------------

def test_pestana_apagada_apaga_su_pildora(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    panel = ventana.panel
    assert not panel.pills.button(panel._tabs.indexOf(panel.text)).isEnabled()
    assert panel.pills.button(panel._tabs.indexOf(panel.color)).isEnabled()


def test_al_haber_texto_su_pildora_se_enciende(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    panel = ventana.panel
    assert panel.pills.button(panel._tabs.indexOf(panel.text)).isEnabled()
    assert panel.pills.button(panel._tabs.indexOf(panel.text)).isChecked()


def test_apagar_la_actual_mueve_la_marca(qapp):
    tabs = _pestanas(3)
    pills = PillTabs(tabs)
    tabs.setCurrentIndex(1)
    tabs.setTabEnabled(1, False)
    pills.sync()
    assert not pills.button(1).isEnabled()
    assert pills.button(tabs.currentIndex()).isChecked()
    assert tabs.currentIndex() != 1


# --- que quepan en un panel angosto ----------------------------------------

def _flujo(n, ancho_boton=80):
    caja = QWidget()
    flujo = FlowLayout(caja, spacing=4)
    flujo.setContentsMargins(0, 0, 0, 0)
    for _ in range(n):
        w = QLabel("x")
        w.setFixedSize(ancho_boton, 20)
        flujo.addWidget(w)
    return caja, flujo


def test_el_flujo_brinca_de_fila_si_no_cabe(qapp):
    _caja, flujo = _flujo(8)
    assert flujo.heightForWidth(2000) == 20
    assert flujo.heightForWidth(170) > 20


def test_el_flujo_no_se_sale_del_ancho(qapp):
    _caja, flujo = _flujo(8)
    flujo.setGeometry(QRect(0, 0, 250, 200))
    for i in range(flujo.count()):
        assert flujo.itemAt(i).geometry().right() < 250


def test_todas_las_pildoras_caben_en_330(ventana):
    pills = ventana.panel.pills
    alto = pills._flow.heightForWidth(330)
    pills.resize(330, alto)
    pills._flow.setGeometry(QRect(0, 0, 330, alto))
    for i in range(ventana.panel._tabs.count()):
        geo = pills.button(i).geometry()
        assert geo.right() <= 330 and geo.bottom() <= alto
