"""Capa de ajuste: corregir todo lo de abajo de un jalón."""

import pytest
from PySide6.QtGui import QColor

from vortex_studio.model import Clip, Sequence, Title
from vortex_studio.model.overlays import AdjustmentLayer


def brillo(img, x=80, y=60):
    return QColor(img.pixel(x, y)).lightness()


# --- el modelo ------------------------------------------------------------

def test_entra_en_la_pila_encima_de_su_pista(secuencia):
    v2, v1 = secuencia.video_tracks()
    clip = v1.add(Clip("/tmp/a.mp4", 0.0, 5.0))
    ajuste = v2.add(AdjustmentLayer(start=1.0, duration=2.0))
    assert [c for c, _ in secuencia.video_stack_at(0.5)] == [clip]
    assert [c for c, _ in secuencia.video_stack_at(1.5)] == [clip, ajuste]


def test_no_tapa_lo_de_abajo(secuencia):
    v2, v1 = secuencia.video_tracks()
    v1.add(Clip("/tmp/a.mp4", 0.0, 5.0))
    v2.add(AdjustmentLayer(start=0.0, duration=5.0))
    assert len(secuencia.video_stack_at(1.0)) == 2


def test_una_pista_oculta_apaga_la_capa(secuencia):
    v2, v1 = secuencia.video_tracks()
    v1.add(Clip("/tmp/a.mp4", 0.0, 5.0))
    v2.add(AdjustmentLayer(start=0.0, duration=5.0))
    v2.enabled = False
    assert len(secuencia.video_stack_at(1.0)) == 1


def test_se_guarda_con_color_y_mascara(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    capa = AdjustmentLayer(start=0.0, duration=3.0, opacity=0.6)
    capa.color.exposure = 80
    capa.mask.shape = "Círculo"
    proyecto.active.video_tracks()[0].add(capa)
    leida = load_project(save_project(proyecto, tmp_path / "p")).active.video_tracks()[0].clips[0]
    assert isinstance(leida, AdjustmentLayer)
    assert (leida.color.exposure, leida.mask.shape, leida.opacity) == (80, "Círculo", 0.6)


# --- los pixeles ------------------------------------------------------------

def con_capa(ventana, media, **color):
    ventana._place_video(media["gris"])
    ventana._seek(0.5)
    capa = ventana.add_adjustment_layer()
    for campo, valor in color.items():
        setattr(capa.color, campo, valor)
    ventana._seek(0.5)
    return capa


def test_aclara_lo_de_abajo(ventana, media):
    ventana._place_video(media["gris"])
    ventana._seek(0.5)
    antes = brillo(ventana.preview.current_image())
    capa = ventana.add_adjustment_layer()
    capa.color.exposure = 100
    ventana._seek(0.5)
    despues = brillo(ventana.preview.current_image())
    assert despues > antes + 60
    assert ventana.history.undo_label == "Capa de ajuste"


def test_la_opacidad_mezcla_a_la_mitad(ventana, media):
    capa = con_capa(ventana, media, exposure=100)
    lleno = brillo(ventana.preview.current_image())
    capa.opacity = 0.5
    ventana._seek(0.5)
    mitad = brillo(ventana.preview.current_image())
    capa.opacity = 0.0
    ventana._seek(0.5)
    nada = brillo(ventana.preview.current_image())
    assert nada < mitad < lleno
    assert mitad == pytest.approx((lleno + nada) / 2, abs=12)


def test_la_mascara_limita_donde_corrige(ventana, media):
    capa = con_capa(ventana, media, exposure=100)
    capa.mask.shape = "Rectángulo"
    capa.mask.x, capa.mask.width, capa.mask.height, capa.mask.feather = 0.25, 0.5, 1.0, 0.0
    ventana._seek(0.5)
    img = ventana.preview.current_image()
    assert brillo(img, 40, 60) > brillo(img, 120, 60) + 60


def test_los_textos_de_arriba_no_se_corrigen(ventana, media):
    capa = con_capa(ventana, media, saturation=0)
    ventana.add_title()
    titulo = ventana.timeline.selected
    titulo.text, titulo.color, titulo.size, titulo.y = "ROJO", "#ff0000", 0.3, 0.5
    titulo.outline = False
    ventana._seek(0.5)
    img = ventana.preview.current_image()
    rojos = [QColor(img.pixel(x, 60)) for x in range(100, 220, 4)]
    assert any(c.red() > 200 and c.green() < 60 for c in rojos)


def test_la_exportacion_lleva_la_capa(ventana, media):
    con_capa(ventana, media, exposure=-200)
    cuadro = next(ventana._frames(0.5, 0.6, 30))
    assert brillo(cuadro) < 50


def test_seleccionarla_abre_su_color(ventana, media):
    capa = con_capa(ventana, media)
    ventana.timeline.select(capa)
    ventana._sync_panels(0.5)
    assert ventana.color_panel._adjust is capa.color
    ventana.color_panel._exposure._slider.setValue(150)
    assert capa.color.exposure == 150
