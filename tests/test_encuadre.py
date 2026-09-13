"""Encuadre, recorte y punto de anclaje."""

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from vortex_studio.media import Frame
from vortex_studio.model import Clip, Sequence
from vortex_studio.model.transform import FILL, FIT, STRETCH, Transform
from vortex_studio.ui.compositor import Layer, compose, fit_rect, framing_of


def blanco(ancho, alto):
    return Frame(bytes([255]) * (ancho * 3 * alto), ancho, alto, ancho * 3)


def pintar(frame, lienzo, **kw):
    tr = Transform(**kw)
    capa = Layer(frame, 1.0, tr.values_at(0.0), "Normal", None, None, framing_of(tr))
    return compose(*lienzo, [capa], [], [])


def brillo(imagen, x, y):
    return QColor(imagen.pixel(x, y)).lightness()


# --- la cuenta ------------------------------------------------------------

def test_ajustar_un_horizontal_en_vertical_deja_franjas():
    r = fit_rect(QRectF(0, 0, 90, 160), 160, 90, FIT)
    assert r.width() == pytest.approx(90)
    assert r.height() == pytest.approx(90 * 90 / 160)
    assert r.center().y() == pytest.approx(80)


def test_rellenar_cubre_y_se_sale():
    r = fit_rect(QRectF(0, 0, 90, 160), 160, 90, FILL)
    assert r.height() == pytest.approx(160)
    assert r.width() > 90


def test_estirar_llena_exacto():
    assert fit_rect(QRectF(0, 0, 90, 160), 160, 90, STRETCH) == QRectF(0, 0, 90, 160)


def test_misma_proporcion_no_cambia_nada():
    for modo in (FIT, FILL, STRETCH):
        assert fit_rect(QRectF(0, 0, 320, 180), 160, 90, modo) == QRectF(0, 0, 320, 180)


# --- los pixeles ----------------------------------------------------------

def test_ajustar_pinta_negro_arriba_y_blanco_al_centro(qapp):
    img = pintar(blanco(160, 88), (90, 160))
    assert brillo(img, 45, 5) < 10
    assert brillo(img, 45, 80) > 245


def test_rellenar_no_deja_franjas(qapp):
    img = pintar(blanco(160, 88), (90, 160), fit=FILL)
    assert brillo(img, 45, 3) > 245 and brillo(img, 45, 156) > 245


def test_el_recorte_deja_transparente_esa_orilla(qapp):
    img = pintar(blanco(160, 88), (160, 88), crop_left=0.4)
    assert brillo(img, 20, 44) < 10          # dentro del 40 % recortado
    assert brillo(img, 120, 44) > 245
    # La imagen no se mueve de lugar: la orilla del recorte cae en el 40 %.
    assert brillo(img, 66, 44) > 245 and brillo(img, 62, 44) < 10


def test_el_ancla_en_la_esquina_escala_desde_la_esquina(qapp):
    img = pintar(blanco(160, 88), (160, 88), scale=0.5, anchor_x=-0.5, anchor_y=-0.5)
    assert brillo(img, 20, 10) > 245         # arriba a la izquierda
    assert brillo(img, 140, 80) < 10         # abajo a la derecha quedó vacío


def test_el_ancla_al_centro_escala_desde_el_centro(qapp):
    img = pintar(blanco(160, 88), (160, 88), scale=0.5)
    assert brillo(img, 80, 44) > 245
    assert brillo(img, 10, 5) < 10


def test_rellenar_crecido_no_se_sale_del_cuadro_en_el_preview(ventana, media):
    """En el preview el cuadro es un pedazo del widget: nada se pinta afuera."""
    ventana._place_video(media["gris"])
    ventana.set_format(1080, 1920)
    ventana.reframe_all(FILL)
    ventana.preview.resize(800, 400)
    ventana._settle_preview()          # que el cuadro ya esté, no el mensaje vacío
    imagen = ventana.preview.grab().toImage()
    objetivo = ventana.preview._fit(ventana.preview._aspect)
    dentro = QColor(imagen.pixel(int(objetivo.center().x()), 200)).lightness()
    fuera = QColor(imagen.pixel(int(objetivo.left()) - 20, 200)).lightness()
    assert dentro > 100, "el cuadro no se pintó"
    # Fuera del cuadro va el fondo de la tarjeta, casi negro; el gris del
    # material tiene brillo de ~128.
    assert fuera < 30, "el material rellenado se salió sobre la franja"


# --- el modelo ------------------------------------------------------------

def test_restablecer_quita_recorte_y_ancla_pero_no_el_encuadre():
    tr = Transform(crop_top=0.2, anchor_x=0.3, fit=FILL, scale=2.0)
    tr.reset()
    assert not tr.has_crop and tr.anchor_x == 0 and tr.scale == 1.0
    assert tr.fit == FILL


def test_el_recorte_tiene_topes():
    assert Transform(crop_left=0.9).crop[0] == 0.49


def test_un_clip_ajustado_de_otra_proporcion_no_tapa_lo_de_abajo():
    seq = Sequence.default()
    seq.width, seq.height = 1080, 1920
    abajo = seq.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 5.0))
    arriba = seq.video_tracks()[0].add(Clip("/tmp/b.mp4", 0.0, 5.0))
    horizontal = lambda clip: 16 / 9

    assert len(seq.video_stack_at(1.0, horizontal)) == 2
    arriba.transform.fit = FILL
    assert [c for c, _ in seq.video_stack_at(1.0, horizontal)] == [arriba]
    arriba.transform.crop_bottom = 0.1
    assert abajo in [c for c, _ in seq.video_stack_at(1.0, horizontal)]


def test_se_guarda(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    clip = proyecto.active.video_tracks()[-1].add(Clip("/tmp/a.mp4", 0.0, 2.0))
    clip.transform = Transform(fit=FILL, crop_right=0.25, anchor_y=0.5)
    leido = load_project(save_project(proyecto, tmp_path / "p")).active.video_tracks()[-1].clips[0]
    assert (leido.transform.fit, leido.transform.crop_right, leido.transform.anchor_y) == \
           (FILL, 0.25, 0.5)


# --- en la ventana --------------------------------------------------------

def test_reencuadrar_todo_para_vertical(ventana, media):
    ventana._place_video(media["gris"])
    ventana.set_format(1080, 1920)
    arriba_antes = ventana.preview.current_image()
    assert QColor(arriba_antes.pixel(540, 20)).lightness() < 10, "ajustado deja franja"

    ventana.reframe_all(FILL)
    imagen = ventana.preview.current_image()
    assert QColor(imagen.pixel(540, 20)).lightness() > 100
    assert ventana.history.undo_label == "Encuadre de todo: rellenar"


def test_el_panel_escribe_encuadre_recorte_y_ancla(ventana, media):
    ventana._place_video(media["gris"])
    clip = ventana.sequence.video_tracks()[-1].clips[0]
    ventana.timeline.select(clip)
    panel = ventana.transform_panel

    panel._fit.setCurrentText(STRETCH)
    assert clip.transform.fit == STRETCH
    panel._crop["crop_top"]._slider.setValue(30)
    assert clip.transform.crop_top == pytest.approx(0.30)
    indice = panel._anchor_preset.findText("Abajo derecha")
    panel._apply_anchor_preset(indice)
    assert (clip.transform.anchor_x, clip.transform.anchor_y) == (0.5, 0.5)
    assert ventana.history.undo_label == "Punto de anclaje"


def test_transformar_se_apaga_con_un_clip_de_audio(ventana, media):
    ventana._place_video(media["sonoro"])
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(audio)
    indice = ventana.panel._tabs.indexOf(ventana.transform_panel)
    assert not ventana.panel._tabs.isTabEnabled(indice)
    assert ventana.transform_panel._clip is None
