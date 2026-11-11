"""Un texto largo se parte en renglones y nunca se sale del cuadro.

Pasó con el MCP: en una secuencia vertical (1080×1920), «Prueba del MCP —
Vortex Studio» con el tamaño de siempre se salía por los dos lados.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFontMetricsF

from vortex_studio.model import ANCHORS, Title
from vortex_studio.model.overlays import align_for_anchor
from vortex_studio.ui.compositor import SAFE_MARGIN, _title_font, compose, title_layout

ANCHO, ALTO = 1080, 1920
LARGO = "Prueba del MCP — Vortex Studio"


def titulo(texto=LARGO, posicion="Abajo izquierda", **kw):
    x, y = ANCHORS[posicion]
    datos = dict(start=0.0, duration=3.0, text=texto, x=x, y=y, bold=True,
                 background=True, align=align_for_anchor(posicion))
    datos.update(kw)
    return Title(**datos)


def tinta(imagen):
    """Las columnas y filas donde hay algo que no es el negro del fondo."""
    xs, ys = set(), set()
    for y in range(0, imagen.height(), 2):
        for x in range(0, imagen.width(), 2):
            c = QColor(imagen.pixel(x, y))
            if c.red() + c.green() + c.blue() > 30:
                xs.add(x)
                ys.add(y)
    return xs, ys


def dentro_del_margen(imagen, holgura=3):
    xs, ys = tinta(imagen)
    assert xs, "no se dibujó nada"
    mx = imagen.width() * SAFE_MARGIN - holgura
    my = imagen.height() * SAFE_MARGIN - holgura
    assert min(xs) >= mx and max(xs) <= imagen.width() - mx
    assert min(ys) >= my and max(ys) <= imagen.height() - my


def test_el_texto_largo_se_parte_en_renglones(qapp):
    px, renglones = title_layout(QRectF(0, 0, ANCHO, ALTO), titulo())
    assert px == int(ALTO * 0.075)              # no hizo falta achicarlo
    assert len(renglones) >= 2
    assert "".join(r for r, _ in renglones).replace(" ", "") == LARGO.replace(" ", "")


def test_el_texto_largo_queda_dentro_del_cuadro_vertical(qapp):
    for posicion in ("Abajo izquierda", "Subtítulo", "Abajo derecha", "Arriba izquierda"):
        dentro_del_margen(compose(ANCHO, ALTO, [], [], [titulo(posicion=posicion)]))


def test_aunque_este_centrado_en_la_orilla(qapp):
    """Un proyecto viejo con el ancla al 6 % y el texto centrado tampoco se sale."""
    dentro_del_margen(compose(ANCHO, ALTO, [], [], [titulo(align="centro")]))


def test_una_palabra_que_no_cabe_se_achica(qapp):
    largo = "Supercalifragilisticoespialidoso"
    t = titulo(texto=largo, posicion="Centro", size=0.2)
    px, renglones = title_layout(QRectF(0, 0, ANCHO, ALTO), t)
    assert px < int(ALTO * 0.2)
    assert len(renglones) == 1
    ancho = QFontMetricsF(_title_font(t, px)).horizontalAdvance(largo)
    assert ancho <= ANCHO * (1 - 2 * SAFE_MARGIN)
    dentro_del_margen(compose(ANCHO, ALTO, [], [], [t]))


def test_se_parte_igual_en_la_vista_previa_y_en_la_exportacion(qapp):
    """`ver_cuadro` y la vista previa pintan chico; la exportación, a tamaño real."""
    t = titulo()
    _, grande = title_layout(QRectF(0, 0, ANCHO, ALTO), t)
    _, chico = title_layout(QRectF(0, 0, 360, 640), t)
    assert [r for r, _ in grande] == [r for r, _ in chico]
    dentro_del_margen(compose(360, 640, [], [], [t]), holgura=2)


def test_un_texto_corto_no_cambia(qapp):
    _, renglones = title_layout(QRectF(0, 0, 1920, 1080), titulo(texto="Hola"))
    assert [r for r, _ in renglones] == ["Hola"]


def test_los_saltos_de_linea_se_respetan(qapp):
    _, renglones = title_layout(QRectF(0, 0, 1920, 1080), titulo(texto="uno\ndos"))
    assert [r for r, _ in renglones] == ["uno", "dos"]


def blancos(imagen):
    return sum(1 for y in range(0, imagen.height(), 3) for x in range(0, imagen.width(), 3)
               if QColor(imagen.pixel(x, y)).lightness() > 200)


def test_escribiendose_con_renglones_partidos(qapp):
    """A media animación se ven menos letras, en su lugar y dentro del cuadro."""
    entero = compose(ANCHO, ALTO, [], [], [titulo(background=False)], 2.5)
    medio = compose(ANCHO, ALTO, [], [], [titulo(background=False, anim_in="Escribiéndose",
                                                  anim_time=2.0)], 1.0)
    dentro_del_margen(entero)
    dentro_del_margen(medio)
    assert 0 < blancos(medio) < blancos(entero)
