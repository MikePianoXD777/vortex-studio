"""Scopes: histograma, forma de onda y vectorscopio."""

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage

from vortex_studio.media import scopes


def plano(r, g, b, h=40, w=60):
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:] = (r, g, b)
    return arr


def test_histograma_de_un_plano_cae_en_un_solo_nivel():
    h = scopes.histogram(plano(200, 50, 10))
    assert h[0, 200] == h[1, 50] == h[2, 10] == 40 * 60
    assert h[:3].sum() == 3 * 40 * 60


def test_histograma_de_la_luminancia():
    h = scopes.histogram(plano(255, 255, 255))
    assert h[3, 255] == 40 * 60
    assert scopes.histogram(plano(0, 0, 0))[3, 0] == 40 * 60


def test_forma_de_onda_ubica_la_luz_por_columna():
    arr = plano(0, 0, 0)
    arr[:, 30:] = 255                         # mitad derecha blanca
    w = scopes.waveform(arr, columns=60, levels=256)
    assert w[255, 10] == 40 and w[0, 10] == 0      # izquierda negra: abajo
    assert w[0, 50] == 40                           # derecha blanca: arriba
    assert w.sum() == 40 * 60


def test_forma_de_onda_de_un_gris_medio_queda_al_centro():
    w = scopes.waveform(plano(128, 128, 128), columns=8, levels=256)
    assert w[127].sum() == 40 * 60


def test_vectorscopio_sin_color_cae_al_centro():
    v = scopes.vectorscope(plano(90, 90, 90), size=65)
    assert v[32, 32] == 40 * 60


def test_vectorscopio_rojo_arriba_y_azul_a_la_derecha():
    rojo = scopes.vectorscope(plano(220, 0, 0), size=65)
    azul = scopes.vectorscope(plano(0, 0, 220), size=65)
    y, x = np.unravel_index(rojo.argmax(), rojo.shape)
    assert y < 32
    y, x = np.unravel_index(azul.argmax(), azul.shape)
    assert x > 32


def test_las_casillas_de_los_colores_puros():
    casillas = scopes.targets(256)
    assert casillas["R"][1] < 128 and casillas["B"][0] > 128
    assert len(casillas) == 6


def test_imagen_a_arreglo_respeta_el_ancho_de_renglon(qapp):
    from vortex_studio.ui.scopes import image_to_array

    img = QImage(33, 10, QImage.Format_RGB888)     # 33 × 3 = 99: Qt rellena a 100
    img.fill(QColor(10, 200, 30))
    arr = image_to_array(img)
    assert arr.shape == (10, 33, 3)
    assert tuple(arr[5, 32]) == (10, 200, 30)


def test_el_panel_calcula_desde_la_ventana(ventana, media):
    ventana._place_video(media["gris"])
    ventana._seek(0.5)
    ventana._settle_preview()          # el cuadro llega de otro hilo
    dock = ventana.scopes
    ventana.show_scopes()
    assert not dock.isHidden()
    dock.mode.setCurrentText("Histograma")
    datos = dock.calculate(ventana.scope_image())
    assert datos is not None and datos.shape == (4, 256)
    assert datos[3, 120:140].sum() > datos[3].sum() * 0.9      # el gris medio

    dock.mode.setCurrentText("Vectorscopio")
    assert dock.view.data.shape == (256, 256)


def test_la_correccion_se_ve_en_el_scope(ventana, media):
    ventana._place_video(media["gris"])
    ventana._seek(0.5)
    ventana._settle_preview()
    ventana.show_scopes()
    ventana.scopes.mode.setCurrentText("Histograma")
    antes = int(np.argmax(ventana.scopes.calculate(ventana.scope_image())[3]))
    ventana.sequence.top_clip_at(0.5).color.exposure = 100
    ventana._seek(0.5)
    ventana._settle_preview()
    despues = int(np.argmax(ventana.scopes.calculate(ventana.scope_image())[3]))
    assert despues > antes + 60
