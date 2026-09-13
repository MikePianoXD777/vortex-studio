"""Perspectiva en 3D y corner pin."""

import numpy as np
import pytest

from vortex_studio.media import Frame
from vortex_studio.model import Clip, Sequence, Transform
from vortex_studio.model import animate
from vortex_studio.model.serialize import item_from_dict, item_to_dict

ANCHO, ALTO = 320, 180


def _blanco(ancho=ANCHO, alto=ALTO):
    return Frame(bytes([255]) * (ancho * 3 * alto), ancho, alto, ancho * 3)


def _pintar(transform, ancho=ANCHO, alto=ALTO):
    from vortex_studio.ui.compositor import Layer, compose, framing_of

    capa = Layer(_blanco(), 1.0, transform.values_at(0.0), "Normal", None, None,
                 framing_of(transform))
    imagen = compose(ancho, alto, [capa], [], [], 0.0)
    datos = np.frombuffer(bytes(imagen.constBits()), np.uint8).reshape(alto, imagen.bytesPerLine())
    return datos[:, :ancho * 3:3] > 128        # blanco o no, por pixel


# --- inclinar ------------------------------------------------------------------------

def test_sin_inclinacion_llena_el_cuadro():
    assert _pintar(Transform()).all()
    assert _pintar(Transform(tilt_x=0.0, tilt_y=0.0)).all()


def test_girar_de_lado_hace_un_lado_mas_chico_que_el_otro():
    blanco = _pintar(Transform(scale=0.6, tilt_y=50))
    columnas = blanco.sum(axis=0)
    visibles = np.where(columnas > 0)[0]
    izquierda, derecha = columnas[visibles[2]], columnas[visibles[-3]]
    assert abs(int(izquierda) - int(derecha)) > 15
    assert visibles.max() - visibles.min() < ANCHO * 0.6 - 10   # más angosta de frente


def test_inclinar_hacia_atras_hace_arriba_y_abajo_distintos():
    blanco = _pintar(Transform(scale=0.6, tilt_x=50))
    filas = blanco.sum(axis=1)
    visibles = np.where(filas > 0)[0]
    assert abs(int(filas[visibles[2]]) - int(filas[visibles[-3]])) > 15


def test_la_perspectiva_se_ve_igual_en_el_preview_chico_y_en_el_archivo():
    from PySide6.QtCore import Qt

    transform = Transform(scale=0.7, tilt_y=35, tilt_x=-20)
    chico = _pintar(transform, ANCHO, ALTO).astype(float)
    grande = _pintar(transform, ANCHO * 2, ALTO * 2).astype(float)
    reducido = grande.reshape(ALTO, 2, ANCHO, 2).mean(axis=(1, 3))
    assert np.abs(chico - reducido).mean() < 0.03


def test_la_inclinacion_tiene_tope_para_no_quedar_de_canto():
    assert _pintar(Transform(scale=0.6, tilt_y=500)).any()
    assert (_pintar(Transform(scale=0.6, tilt_y=500)) == _pintar(Transform(scale=0.6, tilt_y=80))).all()


# --- corner pin ------------------------------------------------------------------------

def test_mover_una_esquina_destapa_esa_esquina():
    blanco = _pintar(Transform(pin_tl_x=0.25, pin_tl_y=0.25))
    assert not blanco[5, 5]
    assert blanco[90, 160] and blanco[175, 315] and blanco[5, 315]


def test_las_cuatro_esquinas_hacia_adentro_dejan_un_marco_negro():
    blanco = _pintar(Transform(pin_tl_x=0.1, pin_tl_y=0.1, pin_tr_x=-0.1, pin_tr_y=0.1,
                               pin_br_x=-0.1, pin_br_y=-0.1, pin_bl_x=0.1, pin_bl_y=-0.1))
    assert not blanco[:10].any() and not blanco[-10:].any()
    assert blanco[40:140, 60:260].all()


def test_esquinas_imposibles_no_truenan():
    from PySide6.QtCore import QRectF

    from vortex_studio.ui.compositor import corner_pin

    cruzadas = [1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0]
    assert corner_pin(QRectF(0, 0, ANCHO, ALTO), [0.0] * 8) is not None
    _pintar(Transform(**dict(zip(("pin_tl_x", "pin_tl_y", "pin_tr_x", "pin_tr_y",
                                  "pin_br_x", "pin_br_y", "pin_bl_x", "pin_bl_y"), cruzadas))))


# --- modelo -------------------------------------------------------------------------------

def test_una_capa_inclinada_no_tapa_lo_de_abajo():
    secuencia = Sequence.default()
    clip = secuencia.track_named("V1").add(Clip("a.mp4", 0, 2))
    assert secuencia.covers(clip, 1.0)
    clip.transform.tilt_y = 10
    assert not secuencia.covers(clip, 1.0)
    clip.transform.tilt_y = 0
    clip.transform.pin_br_x = -0.05
    assert not secuencia.covers(clip, 1.0)


def test_la_perspectiva_se_anima_con_keyframes():
    clip = Clip("a.mp4", 0, 2)
    rutas = [p.path for p in animate.params_for(clip)]
    assert "transform.tilt_x" in rutas and "transform.pin_bl_y" in rutas
    animate.add_key(clip, "transform.tilt_x", 0.0, 0.0)
    animate.add_key(clip, "transform.tilt_x", 1.0, 40.0)
    assert clip.transform.values_at(0.5)["tilt_x"] == pytest.approx(20.0)
    assert clip.transform.has_perspective


def test_guardar_y_abrir_conserva_perspectiva_y_esquinas():
    clip = Clip("a.mp4", 0, 2)
    clip.transform.tilt_x, clip.transform.pin_tr_y = 25.0, 0.2
    clip.transform.set_key("tilt_y", 1.0, 30.0)
    otro = item_from_dict(item_to_dict(clip))
    assert otro.transform.tilt_x == 25.0 and otro.transform.pin_tr_y == 0.2
    assert otro.transform.keys["tilt_y"] == [[1.0, 30.0]]


def test_quitar_la_perspectiva_deja_lo_demas():
    transform = Transform(x=0.2, tilt_x=30, pin_tl_x=0.1)
    transform.set_key("tilt_y", 0.5, 10)
    transform.reset_perspective()
    assert not transform.has_perspective and transform.x == 0.2
    assert not transform.is_neutral


def test_un_clip_real_inclinado_destapa_las_esquinas(media):
    from vortex_studio.ui.renderer import SequenceRenderer

    secuencia = Sequence.default()
    secuencia.width, secuencia.height = ANCHO, ALTO
    clip = secuencia.track_named("V1").add(Clip(media["mudo"], 0, 2))
    clip.transform.tilt_y = 45
    clip.transform.scale = 0.8
    imagen = SequenceRenderer(secuencia).compose(1.0, ANCHO, ALTO)
    assert imagen.pixelColor(2, 2).value() == 0
    assert imagen.pixelColor(160, 90).value() > 20


# --- panel ---------------------------------------------------------------------------------

def _panel_con_clip(ventana, media):
    clip = ventana.sequence.track_named("V1").add(Clip(media["mudo"], 0, 2))
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    return clip, ventana.transform_panel


def test_el_panel_inclina_con_sus_deslizadores(ventana, media):
    clip, panel = _panel_con_clip(ventana, media)
    panel._rows["tilt_y"]._slider.setValue(30)
    panel._rows["pin_tl_x"]._slider.setValue(15)
    assert clip.transform.tilt_y == pytest.approx(30.0)
    assert clip.transform.pin_tl_x == pytest.approx(0.15)


def test_el_panel_muestra_la_perspectiva_del_clip(ventana, media):
    clip = ventana.sequence.track_named("V1").add(Clip(media["mudo"], 0, 2))
    clip.transform.tilt_x = -25.0
    clip.transform.pin_br_y = -0.4
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    panel = ventana.transform_panel
    assert panel._rows["tilt_x"].value() == -25 and panel._rows["pin_br_y"].value() == -40
    assert panel._perspective_group.abierto


def test_quitar_perspectiva_desde_el_panel(ventana, media):
    clip, panel = _panel_con_clip(ventana, media)
    clip.transform.tilt_y, clip.transform.pin_tr_x = 20.0, 0.1
    clip.transform.x = 0.3
    panel._reset_perspective()
    assert not clip.transform.has_perspective and clip.transform.x == 0.3
    assert panel._rows["tilt_y"].value() == 0
