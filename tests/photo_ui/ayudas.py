"""Ayudas para probar la interfaz de Vortex Photo con eventos de ratón sintetizados."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

NINGUNA = Qt.NoModifier


def foto_de_prueba(ancho: int = 400, alto: int = 300) -> np.ndarray:
    """Un degradado RGBA hecho con numpy: nada con derechos de autor."""
    y, x = np.mgrid[0:alto, 0:ancho]
    img = np.zeros((alto, ancho, 4), np.uint8)
    img[..., 0] = x * 255 // max(1, ancho - 1)
    img[..., 1] = y * 255 // max(1, alto - 1)
    img[..., 2] = 140
    img[..., 3] = 255
    return img


def _ev(tipo, pt, boton=Qt.LeftButton, botones=Qt.LeftButton, mods=NINGUNA):
    return QMouseEvent(tipo, QPointF(pt), boton, botones, mods)


def pantalla(canvas, x, y) -> QPointF:
    return canvas.to_screen(x, y)


def presionar(canvas, x, y, mods=NINGUNA, boton=Qt.LeftButton):
    canvas.mousePressEvent(_ev(QEvent.MouseButtonPress, pantalla(canvas, x, y), boton, boton, mods))


def mover(canvas, x, y, mods=NINGUNA, botones=Qt.LeftButton):
    canvas.mouseMoveEvent(_ev(QEvent.MouseMove, pantalla(canvas, x, y), Qt.NoButton, botones, mods))


def soltar(canvas, x, y, mods=NINGUNA, boton=Qt.LeftButton):
    canvas.mouseReleaseEvent(_ev(QEvent.MouseButtonRelease, pantalla(canvas, x, y), boton, Qt.NoButton, mods))


def clic(canvas, x, y, mods=NINGUNA):
    presionar(canvas, x, y, mods)
    soltar(canvas, x, y, mods)


def doble_clic(canvas, x, y):
    clic(canvas, x, y)
    canvas.mouseDoubleClickEvent(_ev(QEvent.MouseButtonDblClick, pantalla(canvas, x, y)))
    soltar(canvas, x, y)


def arrastrar(canvas, a, b, mods=NINGUNA, pasos=4):
    """Arrastra de a=(x, y) a b, en coordenadas del lienzo."""
    presionar(canvas, *a, mods=mods)
    for i in range(1, pasos + 1):
        t = i / pasos
        mover(canvas, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, mods=mods)
    soltar(canvas, *b, mods=mods)


def asa(canvas, nombre):
    """Dónde está un asa de la selección actual, en coordenadas del lienzo."""
    sel = canvas.s.selected()
    return canvas.handle_points(sel)[nombre]


def asa_giro(canvas):
    from vortex_studio.ui.photo import geometry as geo
    from vortex_studio.ui.photo.canvas import ROTATE_OFFSET_PX
    caja = geo.selection_box([c.transform for c in canvas.s.selected()])
    return geo.rotate_handle_point(caja, ROTATE_OFFSET_PX / canvas.zoom)


def tecla(widget, tecla, mods=NINGUNA, tipo=QEvent.KeyPress):
    widget.keyPressEvent(QKeyEvent(tipo, tecla, mods)) if tipo == QEvent.KeyPress \
        else widget.keyReleaseEvent(QKeyEvent(tipo, tecla, mods))


def rueda(canvas, x, y, delta=120, mods=NINGUNA):
    """Una vuelta de rueda con el puntero en (x, y) del lienzo."""
    pt = canvas.to_screen(x, y)
    ev = QWheelEvent(pt, canvas.mapToGlobal(pt.toPoint()), QPoint(0, 0), QPoint(0, delta),
                     Qt.NoButton, mods, Qt.NoScrollPhase, False)
    canvas.wheelEvent(ev)


def esperar(app, n=5):
    for _ in range(n):
        app.processEvents()


def centro(capa):
    return capa.transform.cx, capa.transform.cy
