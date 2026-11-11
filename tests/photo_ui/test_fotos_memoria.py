"""Cerrar la ventana de Fotos suelta su memoria.

Antes cada ventana cerrada se quedaba viva con su almacén de imágenes y sus
cachés: la sesión no tenía padre y sus conexiones a lambdas de la ventana
formaban un ciclo que el recolector de Python no ve. El banco entero llegaba
a más de 4 GB.
"""

import gc

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication


def vivas(nombre):
    return sum(1 for o in gc.get_objects() if type(o).__name__ == nombre)


def abrir_y_cerrar(qapp, usar=None):
    from vortex_studio.ui.photo import PhotoWindow

    w = PhotoWindow()
    w.resize(1280, 720)
    w.show()
    qapp.processEvents()
    w.canvas.flush()
    if usar:
        usar(w)
    w.session.dirty = False
    w.close()
    w.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    gc.collect()


def test_cerrar_la_ventana_la_suelta(qapp):
    # Se compara contra lo que ya había: `smoke_test`, en otra prueba, cierra su
    # ventana sin borrarla (el proceso termina ahí, en el programa real no importa).
    antes = vivas("PhotoWindow")
    for _ in range(4):
        abrir_y_cerrar(qapp)
    assert vivas("PhotoWindow") == antes


def test_no_quedan_ventanas_sueltas(qapp):
    """Los deslizadores de «Transparencia» y «Espaciado» nacían sin padre."""
    antes = len(QApplication.topLevelWidgets())
    abrir_y_cerrar(qapp)
    assert len(QApplication.topLevelWidgets()) == antes


def test_abrir_las_ventanitas_no_las_acumula(qapp):
    def usar(w):
        s = w.session
        s.add_shape("rect")
        botones = [w.context.btn_shape_opacity, w.context.fill_color]
        for _ in range(5):
            for b in botones:
                b.open_popup()
                b.popup.close()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
        qapp.processEvents()
        assert len(w.context.btn_shape_opacity.findChildren(type(w.context.btn_shape_opacity.popup))) == 1

    antes = vivas("PhotoWindow")
    abrir_y_cerrar(qapp, usar)
    assert vivas("PhotoWindow") == antes
