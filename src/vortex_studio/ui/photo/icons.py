"""Íconos de línea de Vortex Photo, dibujados a mano (iguales en todos los sistemas).

Cada uno vive en una cuadrícula de 24×24 centrada en el rectángulo que se
pida. Mismo criterio que `ui/widgets.draw_icon`: nada depende de un tema de
íconos instalado ni de fuentes con símbolos.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from vortex_studio.ui import theme

ICONOS = (
    "diseno", "subir", "texto", "elementos", "dibujar", "capas", "deshacer", "rehacer", "ojo",
    "ojo_cerrado", "candado", "candado_abierto", "basura", "copiar", "voltear", "recortar",
    "varita", "descargar", "menu", "mas", "menos", "ajustar", "flecha_abajo", "cerrar", "imagen",
    "pincel", "borrador", "duplicar", "izquierda", "centro", "derecha", "arriba", "medio", "abajo",
    "posicion", "controles", "sparkle", "tampon", "mano", "mover", "reglas", "archivo",
    "sombra", "fusion",
)


def draw_icon(p: QPainter, name: str, rect, color) -> None:
    r = QRectF(rect)
    s = min(r.width(), r.height()) / 24.0
    c = r.center()

    def P(x, y):
        return QPointF(c.x() + (x - 12) * s, c.y() + (y - 12) * s)

    def R(x0, y0, x1, y1):
        return QRectF(P(x0, y0), P(x1, y1))

    pen = QPen(QColor(color), 1.7 * s)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    def poly(*pts, close=False):
        path = QPainterPath(P(*pts[0]))
        for q in pts[1:]:
            path.lineTo(P(*q))
        if close:
            path.closeSubpath()
        p.drawPath(path)

    if name == "diseno":
        for x, y in ((4, 4), (13.5, 4), (4, 13.5), (13.5, 13.5)):
            p.drawRoundedRect(R(x, y, x + 6.5, y + 6.5), 1.5 * s, 1.5 * s)
    elif name == "subir":
        poly((4, 15), (4, 20), (20, 20), (20, 15))
        poly((12, 16), (12, 4))
        poly((7, 9), (12, 4), (17, 9))
    elif name == "texto":
        poly((5, 6), (5, 4.5), (19, 4.5), (19, 6))
        poly((12, 4.5), (12, 19.5))
        poly((9, 19.5), (15, 19.5))
    elif name == "elementos":
        p.drawEllipse(R(3.5, 3.5, 14, 14))
        p.drawRoundedRect(R(10, 10, 20.5, 20.5), 2 * s, 2 * s)
    elif name == "dibujar":
        poly((4, 20), (5, 15), (16, 4), (20, 8), (9, 19), (4, 20), close=True)
        poly((14, 6), (18, 10))
    elif name == "capas":
        poly((12, 4), (21, 9), (12, 14), (3, 9), close=True)
        poly((3, 13), (12, 18), (21, 13))
        poly((3, 17), (12, 22), (21, 17))
    elif name in ("deshacer", "rehacer"):
        k = -1 if name == "rehacer" else 1
        def X(x):
            return 12 + (x - 12) * k
        path = QPainterPath(P(X(9), 8))
        path.lineTo(P(X(4), 13))
        path.lineTo(P(X(9), 18))
        p.drawPath(path)
        path = QPainterPath(P(X(4), 13))
        path.lineTo(P(X(15), 13))
        path.cubicTo(P(X(19), 13), P(X(20), 17), P(X(17), 19))
        p.drawPath(path)
    elif name in ("ojo", "ojo_cerrado"):
        path = QPainterPath(P(2.5, 12))
        path.cubicTo(P(6, 5), P(18, 5), P(21.5, 12))
        path.cubicTo(P(18, 19), P(6, 19), P(2.5, 12))
        p.drawPath(path)
        if name == "ojo":
            p.drawEllipse(P(12, 12), 3 * s, 3 * s)
        else:
            poly((4, 20), (20, 4))
    elif name in ("candado", "candado_abierto"):
        p.drawRoundedRect(R(5, 11, 19, 20.5), 2 * s, 2 * s)
        path = QPainterPath(P(8, 11))
        if name == "candado":
            path.lineTo(P(8, 8))
            path.arcTo(R(8, 3.5, 16, 12.5), 180, -180)
            path.lineTo(P(16, 11))
        else:
            path.lineTo(P(8, 8))
            path.arcTo(R(8, 3.5, 16, 12.5), 180, -180)
            path.lineTo(P(16, 7))
        p.drawPath(path)
    elif name == "basura":
        poly((4, 7), (20, 7))
        poly((9, 7), (9, 4.5), (15, 4.5), (15, 7))
        poly((6, 7), (7, 20), (17, 20), (18, 7))
        poly((10, 11), (10, 16))
        poly((14, 11), (14, 16))
    elif name in ("copiar", "duplicar"):
        p.drawRoundedRect(R(8.5, 8.5, 20, 20), 2 * s, 2 * s)
        path = QPainterPath(P(15.5, 8.5))
        path.lineTo(P(15.5, 6)); path.quadTo(P(15.5, 4), P(13.5, 4)); path.lineTo(P(6, 4))
        path.quadTo(P(4, 4), P(4, 6)); path.lineTo(P(4, 13.5)); path.quadTo(P(4, 15.5), P(6, 15.5))
        path.lineTo(P(8.5, 15.5))
        p.drawPath(path)
    elif name == "voltear":
        poly((12, 3), (12, 21))
        poly((9, 7), (3, 17), (9, 17), close=True)
        poly((15, 7), (21, 17), (15, 17), close=True)
    elif name == "recortar":
        poly((7, 3), (7, 17), (21, 17))
        poly((3, 7), (17, 7), (17, 21))
    elif name in ("varita", "sparkle"):
        poly((12, 3), (13.8, 9), (20, 11), (13.8, 13), (12, 19), (10.2, 13), (4, 11), (10.2, 9),
             close=True)
        poly((19, 3), (19, 6)); poly((17.5, 4.5), (20.5, 4.5))
    elif name == "descargar":
        poly((4, 15), (4, 20), (20, 20), (20, 15))
        poly((12, 4), (12, 15))
        poly((7, 10), (12, 15), (17, 10))
    elif name == "menu":
        for y in (6, 12, 18):
            poly((4, y), (20, y))
    elif name == "mas":
        poly((12, 5), (12, 19)); poly((5, 12), (19, 12))
    elif name == "menos":
        poly((5, 12), (19, 12))
    elif name == "ajustar":
        poly((4, 9), (4, 4), (9, 4)); poly((15, 4), (20, 4), (20, 9))
        poly((20, 15), (20, 20), (15, 20)); poly((9, 20), (4, 20), (4, 15))
    elif name == "flecha_abajo":
        poly((7, 10), (12, 15), (17, 10))
    elif name == "cerrar":
        poly((6, 6), (18, 18)); poly((18, 6), (6, 18))
    elif name == "imagen":
        p.drawRoundedRect(R(3.5, 4.5, 20.5, 19.5), 2.5 * s, 2.5 * s)
        p.drawEllipse(P(9, 10), 1.8 * s, 1.8 * s)
        poly((4, 17), (9.5, 12.5), (13, 15.5), (16, 12.5), (20, 17))
    elif name == "pincel":
        poly((15, 4), (20, 9), (11, 18), (6, 13), close=True)
        path = QPainterPath(P(6, 13))
        path.cubicTo(P(3, 14), P(5, 19), P(3.5, 20.5)); path.cubicTo(P(8, 21), P(11, 19), P(11, 18))
        p.drawPath(path)
    elif name == "borrador":
        poly((14, 4.5), (20, 10.5), (11.5, 19), (5.5, 19), (4, 17.5), close=True)
        poly((9, 9.5), (15, 15.5)); poly((9, 19), (20, 19))
    elif name == "izquierda":
        poly((4, 6), (20, 6)); poly((4, 10), (14, 10)); poly((4, 14), (20, 14)); poly((4, 18), (14, 18))
    elif name == "centro":
        poly((4, 6), (20, 6)); poly((7, 10), (17, 10)); poly((4, 14), (20, 14)); poly((7, 18), (17, 18))
    elif name == "derecha":
        poly((4, 6), (20, 6)); poly((10, 10), (20, 10)); poly((4, 14), (20, 14)); poly((10, 18), (20, 18))
    elif name == "arriba":
        poly((4, 4), (20, 4)); p.drawRoundedRect(R(7, 8, 11, 20), s, s); p.drawRoundedRect(R(13, 8, 17, 15), s, s)
    elif name == "medio":
        poly((3, 12), (21, 12)); p.drawRoundedRect(R(7, 5, 11, 19), s, s); p.drawRoundedRect(R(13, 8, 17, 16), s, s)
    elif name == "abajo":
        poly((4, 20), (20, 20)); p.drawRoundedRect(R(7, 4, 11, 16), s, s); p.drawRoundedRect(R(13, 9, 17, 16), s, s)
    elif name == "posicion":
        p.drawRoundedRect(R(3.5, 3.5, 14, 14), 1.5 * s, 1.5 * s)
        p.drawRoundedRect(R(10, 10, 20.5, 20.5), 1.5 * s, 1.5 * s)
    elif name == "controles":
        poly((4, 7), (20, 7)); poly((4, 17), (20, 17))
        p.setBrush(QColor(color))
        p.drawEllipse(P(9, 7), 2.4 * s, 2.4 * s); p.drawEllipse(P(15, 17), 2.4 * s, 2.4 * s)
    elif name == "tampon":
        poly((9, 4), (15, 4), (15, 11), (19, 14), (19, 16), (5, 16), (5, 14), (9, 11), close=True)
        poly((4, 20), (20, 20))
    elif name == "mano":
        poly((8, 13), (8, 6)); poly((11, 12), (11, 4)); poly((14, 12), (14, 5)); poly((17, 13), (17, 8))
        path = QPainterPath(P(8, 13)); path.lineTo(P(6, 11)); path.cubicTo(P(5, 11), P(5, 13), P(6, 14))
        path.lineTo(P(9, 19)); path.quadTo(P(10, 21), P(13, 21)); path.lineTo(P(15, 21))
        path.quadTo(P(17, 20), P(17, 17)); path.lineTo(P(17, 13))
        p.drawPath(path)
    elif name == "mover":
        poly((12, 3), (12, 21)); poly((3, 12), (21, 12))
        poly((9, 6), (12, 3), (15, 6)); poly((9, 18), (12, 21), (15, 18))
        poly((6, 9), (3, 12), (6, 15)); poly((18, 9), (21, 12), (18, 15))
    elif name == "reglas":
        p.drawRoundedRect(R(3, 8, 21, 16), 1.5 * s, 1.5 * s)
        for x in (7, 11, 15, 19):
            poly((x, 8), (x, 11.5))
    elif name == "archivo":
        poly((6, 3.5), (14, 3.5), (19, 8.5), (19, 20.5), (6, 20.5), close=True)
        poly((14, 3.5), (14, 8.5), (19, 8.5))
    elif name == "sombra":
        p.drawRoundedRect(R(4, 4, 15, 15), 2 * s, 2 * s)
        poly((18, 8), (18, 18), (8, 18))
    elif name == "fusion":
        p.drawEllipse(R(3.5, 6, 14.5, 17)); p.drawEllipse(R(9.5, 6, 20.5, 17))
    else:
        p.drawRect(R(5, 5, 19, 19))
    p.restore()


def draw_letter(p: QPainter, letra: str, rect, color, *, bold=False, italic=False,
                underline=False) -> None:
    """Las letras de negrita/cursiva/subrayado, con la tipografía de la interfaz."""
    f = QFont()
    f.setPixelSize(int(min(rect.width(), rect.height()) * 0.78))
    f.setBold(bold)
    f.setItalic(italic)
    f.setUnderline(underline)
    p.save()
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(rect), Qt.AlignCenter, letra)
    p.restore()


def make_icon(name: str, color: str = theme.TENUE, size: int = 20) -> QIcon:
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(2.0)
    p = QPainter(pix)
    draw_icon(p, name, QRectF(0, 0, size, size), QColor(color))
    p.end()
    return QIcon(pix)
