"""Looks de color y formatos de secuencia."""

import pytest

from vortex_studio.media import VideoSource
from vortex_studio.model.color import LOOKS, ColorAdjust


def canales(frame):
    px = frame.data[:30000]
    return (sum(px[0::3]) / 10000, sum(px[1::3]) / 10000, sum(px[2::3]) / 10000)


@pytest.fixture
def gris(media):
    fuente = VideoSource(media["gris"])
    yield fuente
    fuente.close()


def test_calido_sube_el_rojo(gris):
    r, g, b = canales(gris.frame_at(1.0, ColorAdjust(temperature=60)))
    assert r > b + 5


def test_frio_sube_el_azul(gris):
    r, g, b = canales(gris.frame_at(1.0, ColorAdjust(temperature=-60)))
    assert b > r + 5


def test_temperatura_cero_no_tiñe(gris):
    r, g, b = canales(gris.frame_at(1.0, ColorAdjust(temperature=0)))
    assert abs(r - b) < 2


def test_todos_los_looks_se_aplican_sin_reventar(gris):
    for nombre, look in LOOKS.items():
        assert gris.frame_at(1.0, look) is not None, nombre


def test_el_look_ninguno_es_neutro():
    assert LOOKS["Ninguno"].is_neutral


def test_blanco_y_negro_quita_el_color(media):
    fuente = VideoSource(media["mudo"])
    try:
        f = fuente.frame_at(2.0, LOOKS["Blanco y negro"])
        px = f.data[:30000]
        separacion = max(abs(a - b) for a, b in zip(px[0::3], px[2::3]))
        assert separacion < 8
    finally:
        fuente.close()


def test_aplicar_un_look_escribe_en_los_controles(ventana, media):
    """El look es un punto de partida: deja los deslizadores donde se ve."""
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    clip = ventana.sequence.top_clip_at(2.0)

    ventana.color_panel._look.setCurrentText("Cine")
    assert clip.color.contrast == LOOKS["Cine"].contrast
    assert clip.color.temperature == LOOKS["Cine"].temperature

    # y se puede seguir ajustando encima
    ventana.color_panel._brightness._slider.setValue(25)
    assert clip.color.brightness == 25
    assert clip.color.contrast == LOOKS["Cine"].contrast


def test_restablecer_vuelve_a_ninguno(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.color_panel._look.setCurrentText("Vívido")
    ventana.color_panel._reset()

    assert ventana.sequence.top_clip_at(2.0).color.is_neutral
    assert ventana.color_panel._look.currentText() == "Ninguno"


def test_la_temperatura_se_guarda(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    ventana.sequence.top_clip_at(1.0).color.temperature = -40
    destino = save_project(ventana.project, tmp_path / "p")
    assert load_project(destino).active.video_tracks()[-1].clips[0].color.temperature == -40


# --- formatos -------------------------------------------------------------

def test_formato_vertical(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.set_format(1080, 1920)

    assert (ventana.sequence.width, ventana.sequence.height) == (1080, 1920)
    assert ventana.history.undo_label.startswith("Formato")


def test_el_formato_no_recorta_el_material(ventana, media):
    """El clip se acomoda dentro del cuadro nuevo; lo que sobra queda negro."""
    ventana._place_video(media["mudo"])
    duracion = ventana.sequence.duration
    ventana.set_format(1080, 1920)

    assert ventana.sequence.duration == duracion
    imagen = ventana.preview.current_image()
    assert imagen.width() < imagen.height(), "el preview no quedó vertical"


def test_ajustar_al_primer_clip(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.set_format(1080, 1920)
    ventana.format_from_clip()
    assert (ventana.sequence.width, ventana.sequence.height) == (320, 180)


def test_el_formato_se_puede_deshacer(ventana, media):
    ventana._place_video(media["mudo"])
    antes = (ventana.sequence.width, ventana.sequence.height)
    ventana.set_format(1080, 1080)
    ventana.undo()
    assert (ventana.sequence.width, ventana.sequence.height) == antes
