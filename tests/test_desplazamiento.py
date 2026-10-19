"""El timeline se recorre a los lados: barra, rueda y zoom anclado.

Antes el timeline siempre empezaba en el segundo 0 y lo que no cabía no se
podía ver más que alejando el zoom con Shift+Z.
"""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QKeySequence, QMouseEvent, QPainter, QWheelEvent

from vortex_studio.model import Clip
from vortex_studio.ui.timeline import HEADER_WIDTH


def rueda(timeline, x, pasos=-120, modificadores=Qt.NoModifier):
    evento = QWheelEvent(QPointF(x, 40), QPointF(x, 40), QPoint(0, 0), QPoint(0, pasos),
                         Qt.NoButton, modificadores, Qt.NoScrollPhase, False)
    timeline.wheelEvent(evento)


def clic(timeline, x, y):
    timeline.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y),
                                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    timeline.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y),
                                           Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


def y_hueco(ventana):
    """La altura de V2, que `larga` deja vacía: ahí un clic es un clic en un hueco."""
    v2 = ventana.sequence.video_tracks()[0]
    return ventana.timeline._track_top(ventana.sequence.tracks.index(v2)) + 20


class _Espia(QPainter):
    """Un pintor que anota qué texto pone y en qué pixeles queda."""

    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.textos = []

    def drawText(self, punto, texto):
        izquierda = punto.x()
        self.textos.append((izquierda, izquierda + self.fontMetrics().horizontalAdvance(texto),
                            texto))
        super().drawText(punto, texto)


def etiquetas_de_la_regla(timeline):
    imagen = QImage(timeline.size(), QImage.Format_ARGB32)
    pintor = _Espia(imagen)
    timeline._draw_ruler(pintor)
    pintor.end()
    return pintor.textos


def larga(ventana, segundos=120.0):
    """Una secuencia mucho más larga que lo que cabe en la vista."""
    v1 = ventana.sequence.video_tracks()[-1]
    v1.add(Clip("/no/existe.mp4", 0.0, segundos))
    ventana.timeline.pixels_per_second = 80.0
    ventana.timeline.refresh()
    return ventana.timeline


def test_tiempo_y_pixel_son_inversos_con_la_vista_corrida(ventana):
    tl = larga(ventana)
    tl.set_scroll(1234.0)
    for t in (0.0, 15.5, 30.0, 99.9):
        assert tl.time_for(tl.x_for(t)) == pytest.approx(t)
    assert tl.time_for(HEADER_WIDTH) == pytest.approx(1234.0 / 80.0)


def test_el_desplazamiento_no_se_sale(ventana):
    tl = larga(ventana)
    tl.set_scroll(-50)
    assert tl.scroll_x == 0.0
    tl.set_scroll(10 ** 9)
    assert tl.scroll_x == pytest.approx(tl.max_scroll())
    # Al final se ve el final de la secuencia, con aire para soltar algo.
    assert tl.x_for(ventana.sequence.duration) < tl.width()


def test_una_secuencia_que_cabe_no_se_desplaza(ventana):
    ventana.sequence.video_tracks()[-1].add(Clip("/no/existe.mp4", 0.0, 2.0))
    ventana.timeline.fit()
    assert ventana.timeline.max_scroll() == 0.0


def test_la_rueda_corre_el_tiempo(ventana):
    tl = larga(ventana)
    rueda(tl, 400, -120)
    assert tl.scroll_x > 0
    antes = tl.scroll_x
    rueda(tl, 400, 120)
    assert tl.scroll_x < antes


def test_ctrl_rueda_deja_quieto_el_instante_bajo_el_mouse(ventana):
    tl = larga(ventana)
    tl.set_scroll(800.0)
    x = 500.0
    instante = tl.time_for(x)
    rueda(tl, x, 120, Qt.ControlModifier)
    assert tl.pixels_per_second > 80.0
    assert tl.time_for(x) == pytest.approx(instante, abs=1e-6)
    rueda(tl, x, -120, Qt.ControlModifier)
    rueda(tl, x, -120, Qt.ControlModifier)
    assert tl.pixels_per_second < 80.0
    assert tl.time_for(x) == pytest.approx(instante, abs=1e-6)


def test_ctrl_rueda_sobre_las_cabeceras_no_esconde_el_principio(ventana):
    """Antes el ancla caía en el segundo 0 y el zoom lo dejaba detrás de ellas."""
    tl = larga(ventana)
    rueda(tl, 20, 120, Qt.ControlModifier)
    assert tl.pixels_per_second > 80.0
    assert tl.scroll_x == 0.0
    # Con la vista corrida, lo que se queda quieto es la orilla izquierda.
    tl.set_scroll(800.0)
    orilla = tl.time_for(HEADER_WIDTH)
    rueda(tl, 20, -120, Qt.ControlModifier)
    assert tl.time_for(HEADER_WIDTH) == pytest.approx(orilla, abs=1e-6)


def test_los_botones_de_zoom(ventana):
    tl = larga(ventana)
    ventana.timeline_tools.zoom_in_button.click()
    assert tl.pixels_per_second == pytest.approx(100.0)
    ventana.timeline_tools.zoom_out_button.click()
    ventana.timeline_tools.zoom_out_button.click()
    assert tl.pixels_per_second == pytest.approx(64.0)


def test_los_botones_de_zoom_dicen_su_tecla(ventana):
    """El de acercar decía «+», pero la tecla es «=»: con «+» no pasaba nada."""
    herramientas = ventana.timeline_tools
    for boton, clave in ((herramientas.zoom_in_button, "ver.acercar"),
                         (herramientas.zoom_out_button, "ver.alejar"),
                         (herramientas.fit_button, "ver.ajustar")):
        tecla = ventana._actions[clave].shortcut().toString(QKeySequence.PortableText)
        assert boton.toolTip().endswith(f"  ·  {tecla}"), (boton.toolTip(), tecla)


def test_ajustar_regresa_al_principio_y_cabe_todo(ventana):
    tl = larga(ventana)
    tl.set_scroll(2000.0)
    ventana.timeline_tools.fit_button.click()
    assert tl.scroll_x == 0.0
    assert tl.x_for(ventana.sequence.duration) <= tl.width()


@pytest.mark.parametrize("horas", [1, 10, 100])
def test_ajustar_hace_caber_una_secuencia_de_horas(ventana, horas):
    """Con el piso de 0.5 px/s, una hora no cabía en menos de 1800 px."""
    segundos = horas * 3600.0
    tl = larga(ventana, segundos)
    tl.set_scroll(5000.0)
    ventana._fit_zoom()
    assert tl.scroll_x == 0.0
    assert tl.x_for(segundos) <= tl.width()
    assert tl.max_scroll() == 0.0
    # Alejar desde ahí no brinca de regreso al mínimo de antes.
    tl.zoom_out()
    assert tl.x_for(segundos) <= tl.width()
    # Y la regla no encima las etiquetas aunque cada pixel sea más de un minuto.
    assert tl._ruler_step() * tl.pixels_per_second >= 110
    textos = etiquetas_de_la_regla(tl)
    assert len(textos) >= 2
    for (_, fin, _), (inicio, _, _) in zip(textos, textos[1:]):
        assert inicio > fin
    tl.grab()       # pinta sin tronar


@pytest.mark.parametrize("pps", [0.5, 0.05, 0.005, 0.0005, 1e-6])
def test_la_regla_tiene_marcas_para_cualquier_zoom(ventana, pps):
    tl = ventana.timeline
    tl.pixels_per_second = pps
    assert tl._ruler_step() * pps >= 110


def test_la_barra_y_el_timeline_van_amarrados(ventana):
    tl = larga(ventana)
    barra = ventana.timeline_scroll
    assert barra.maximum() == int(round(tl.max_scroll()))
    barra.setValue(600)
    assert tl.scroll_x == pytest.approx(600)
    tl.set_scroll(900.0)
    assert barra.value() == 900


def barra_al_dia(ventana):
    tl, barra = ventana.timeline, ventana.timeline_scroll
    return (tl.scroll_x <= tl.max_scroll() + 1e-6
            and barra.maximum() == int(round(tl.max_scroll()))
            and barra.value() == int(round(tl.scroll_x)))


def test_borrar_el_final_reacomoda_la_vista_y_la_barra(ventana):
    """Antes la vista se quedaba más allá del final, toda vacía, y la barra con
    el rango viejo, hasta la siguiente vuelta de la rueda."""
    tl = larga(ventana, 10.0)
    cola = ventana.sequence.video_tracks()[-1].add(Clip("/no/existe.mp4", 10.0, 110.0))
    tl.refresh()
    tl.set_scroll(10 ** 9)
    assert tl.scroll_x > 9000
    tl.select(cola)
    ventana.delete_selected()
    assert ventana.sequence.duration == pytest.approx(10.0)
    assert barra_al_dia(ventana)
    assert tl.x_for(10.0) > HEADER_WIDTH       # el final de lo que quedó se ve


def test_alargar_la_secuencia_alarga_la_barra(ventana):
    """Arrastrar un clip más allá de la orilla dejaba la barra sin recorrido."""
    tl = ventana.timeline
    clip = ventana.sequence.video_tracks()[-1].add(Clip("/no/existe.mp4", 0.0, 5.0))
    tl.refresh()
    tl.fit()
    assert ventana.timeline_scroll.maximum() == 0
    clip.start = 30.0                       # lo que deja un arrastre al soltar
    tl.edit_finished.emit("Mover clip")
    assert tl.max_scroll() > 0
    assert barra_al_dia(ventana)


def test_al_reproducir_la_vista_pasa_de_pagina(ventana):
    tl = larga(ventana)
    fuera = tl.time_for(tl.width()) + 5.0
    tl.set_playhead(fuera)
    x = tl.x_for(fuera)
    assert HEADER_WIDTH <= x <= tl.width()
    # Salta y queda cerca de la izquierda, no pegado a la orilla.
    assert x < HEADER_WIDTH + tl.view_width() * 0.25


def test_mover_el_playhead_dentro_de_la_vista_no_la_mueve(ventana):
    tl = larga(ventana)
    tl.set_scroll(400.0)
    tl.set_playhead(tl.time_for(tl.width() / 2))
    assert tl.scroll_x == pytest.approx(400.0)


def test_al_reproducir_no_se_regresa_la_vista_que_uno_corrio(ventana):
    """Correr la vista para ver más adelante mientras se reproduce.

    Antes el cuadro siguiente la regresaba a la página del playhead: con la
    rueda o con la barra no se podía mirar otra parte durante el play.
    """
    tl = larga(ventana)
    ventana._seek(2.0)
    tl.set_scroll(5000.0)
    ventana._seek(2.0 + 1 / 30)         # un cuadro de reproducción
    assert tl.scroll_x == pytest.approx(5000.0)
    # Si uno vuelve a donde va el playhead, la vista lo sigue otra vez.
    tl.set_scroll(0.0)
    fuera = tl.time_for(tl.width()) + 0.1
    ventana._seek(fuera)
    assert HEADER_WIDTH <= tl.x_for(fuera) <= tl.width()


def test_con_la_barra_agarrada_no_se_pasa_de_pagina(ventana):
    """La vista se movía debajo del mouse que tenía agarrada la barra."""
    tl = larga(ventana)
    barra = ventana.timeline_scroll
    ventana._seek(tl.time_for(tl.width() - 20))
    barra.setSliderDown(True)
    ventana._seek(tl.time_for(tl.width()) + 0.1)
    assert tl.scroll_x == 0.0
    assert barra.value() == 0
    barra.setSliderDown(False)
    # Ya suelta, el play vuelve a pasar de página.
    ventana._seek(1.0)
    fuera = tl.time_for(tl.width()) + 0.1
    ventana._seek(fuera)
    assert tl.scroll_x > 0
    assert HEADER_WIDTH <= tl.x_for(fuera) <= tl.width()


def test_un_clic_cerca_de_la_orilla_derecha_no_pasa_de_pagina(ventana):
    """El mismo clic en la regla no movía la vista, y en un hueco sí."""
    tl = larga(ventana)
    x = tl.width() - 4
    clic(tl, x, y_hueco(ventana))
    assert tl.scroll_x == 0.0
    assert tl.playhead == pytest.approx(tl.time_for(x), abs=1 / 30)


def test_un_clic_a_medio_play_cae_donde_se_hizo(ventana):
    """El clic guarda pixeles: si la vista pasaba de página entre presionar y
    soltar, el playhead caía una página más adelante."""
    tl = larga(ventana)
    ventana._seek(tl.time_for(tl.width() - 20))
    x, y = HEADER_WIDTH + 100, y_hueco(ventana)
    tl.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y),
                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    ventana._seek(tl.time_for(tl.width()) + 0.1)       # el play cruza la orilla
    tl.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y),
                                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert tl.scroll_x == 0.0
    assert tl.playhead == pytest.approx(100 / 80.0, abs=1 / 30)


def test_el_clic_con_la_vista_corrida_cae_en_el_clip_correcto(ventana):
    tl = larga(ventana, 10.0)
    v1 = ventana.sequence.video_tracks()[-1]
    lejano = v1.add(Clip("/no/existe.mp4", 60.0, 5.0))
    tl.refresh()
    tl.set_scroll(60.0 * 80.0 - 200)
    y = tl._track_top(ventana.sequence.tracks.index(v1)) + 20
    x = tl.x_for(62.0)
    assert HEADER_WIDTH < x < tl.width()
    tl.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y),
                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    tl.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y),
                                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert tl.selected is lejano


def test_la_regla_empieza_donde_empieza_la_vista(ventana):
    """Con la vista corrida, la regla no debe recorrer desde el segundo 0."""
    tl = larga(ventana)
    tl.set_scroll(5000.0)
    tl.grab()       # pinta sin tronar
    assert tl.time_for(HEADER_WIDTH) == pytest.approx(62.5)


def test_la_regla_no_deja_etiquetas_cortadas_a_la_izquierda(ventana):
    """Con la vista corrida, una etiqueta quedaba a medias detrás de las cabeceras."""
    tl = larga(ventana)
    tl.set_scroll(170.0)        # la marca del segundo 2 cae 10 px antes del tiempo
    assert tl.x_for(2.0) < HEADER_WIDTH
    textos = etiquetas_de_la_regla(tl)
    assert textos
    for inicio, fin, texto in textos:
        assert inicio >= HEADER_WIDTH - 2, texto
        assert fin <= tl.width(), texto


def test_el_timeline_vacio_dice_que_hacer(ventana):
    imagen = ventana.timeline.grab().toImage()
    assert not imagen.isNull()


def test_los_valores_de_los_deslizadores_se_ven(qapp):
    """Con Qt 6.12 el número se veía como «⋮»: el campo medía 1 px."""
    from vortex_studio.ui.widgets import SliderRow

    fila = SliderRow("Entrada", 0, 100, 12, scale=10, decimals=1, suffix=" s")
    fila.resize(300, 30)
    fila.show()
    qapp.processEvents()
    assert fila._spin.lineEdit().width() > 20
    fila.close()
