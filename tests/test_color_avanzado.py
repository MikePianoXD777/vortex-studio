"""Exposición, tinte, lift/gamma/gain y LUTs."""

import av
import pytest

from vortex_studio.media.color import ColorProcessor
from vortex_studio.model import Clip, Project
from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.lut import read_cube, write_cube


def plano(r, g, b, w=64, h=36):
    import numpy as np
    arr = np.zeros((h, w, 3), dtype="uint8")
    arr[..., 0], arr[..., 1], arr[..., 2] = r, g, b
    return av.VideoFrame.from_ndarray(arr, format="rgb24")


def color(adjust, rgb=(128, 128, 128)):
    salida = ColorProcessor().apply(plano(*rgb), adjust)
    return [int(v) for v in salida.reformat(format="rgb24").to_ndarray()[18, 32]]


# --- exposición y tinte -------------------------------------------------------

def test_un_paso_de_exposicion_dobla_la_luz():
    r, g, b = color(ColorAdjust(exposure=100), (60, 60, 60))
    assert r == pytest.approx(120, abs=3) and r == g == b


def test_exposicion_negativa_oscurece():
    assert color(ColorAdjust(exposure=-100), (120, 120, 120))[0] == pytest.approx(60, abs=3)


def test_tinte_positivo_quita_verde():
    r, g, b = color(ColorAdjust(tint=80))
    assert g < r - 20 and abs(r - b) <= 2
    r2, g2, _ = color(ColorAdjust(tint=-80))
    assert g2 >= r2


# --- lift, gamma y gain -------------------------------------------------------------

def test_lift_levanta_el_negro_y_no_el_blanco():
    assert color(ColorAdjust(lift_r=100, lift_g=100, lift_b=100), (0, 0, 0))[0] > 50
    assert color(ColorAdjust(lift_r=100, lift_g=100, lift_b=100), (255, 255, 255))[0] >= 253


def test_gain_escala_las_luces_y_deja_el_negro():
    assert color(ColorAdjust(gain_r=50), (200, 200, 200))[0] == pytest.approx(100, abs=3)
    assert color(ColorAdjust(gain_r=50), (0, 0, 0))[0] <= 1


def test_gamma_por_canal_solo_toca_su_canal():
    r, g, b = color(ColorAdjust(gamma_b=200))
    assert b > r + 30 and abs(r - g) <= 1


# --- LUT ----------------------------------------------------------------------------

@pytest.fixture
def invertir(tmp_path):
    return write_cube(tmp_path / "invertir.cube", 17,
                      lambda r, g, b: (1 - r, 1 - g, 1 - b), "Invertir")


def test_leer_un_cube(invertir, tmp_path):
    cubo = read_cube(invertir)
    assert cubo.size == 17 and cubo.title == "Invertir" and len(cubo.table) == 17 ** 3
    roto = tmp_path / "roto.cube"
    roto.write_text("LUT_3D_SIZE 4\n0 0 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_cube(roto)


def test_el_lut_se_aplica_completo(invertir):
    r, g, b = color(ColorAdjust(lut=str(invertir)), (200, 50, 100))
    assert (r, g, b) == pytest.approx((55, 205, 155), abs=4)


def test_la_intensidad_mezcla_con_la_original(invertir):
    r, _, _ = color(ColorAdjust(lut=str(invertir), lut_intensity=50), (200, 50, 100))
    assert r == pytest.approx(128, abs=5)
    assert color(ColorAdjust(lut=str(invertir), lut_intensity=0), (200, 50, 100))[0] == 200


def test_un_lut_que_ya_no_esta_no_rompe_el_cuadro(tmp_path):
    assert color(ColorAdjust(lut=str(tmp_path / "no.cube"), exposure=0), (90, 90, 90))[0] == 90


def test_la_firma_cambia_con_lo_nuevo():
    base = ColorAdjust().signature
    for campo, valor in (("exposure", 10), ("tint", 5), ("lift_g", 3), ("lut", "x.cube"),
                         ("lut_intensity", 40)):
        otro = ColorAdjust()
        setattr(otro, campo, valor)
        assert otro.signature != base, campo


def test_copiar_y_restablecer():
    a = ColorAdjust(exposure=40, gain_b=150, lut="/tmp/a.cube", lut_intensity=30)
    b = a.copy()
    assert (b.exposure, b.gain_b, b.lut, b.lut_intensity) == (40, 150, "/tmp/a.cube", 30)
    a.reset()
    assert a.is_neutral


def test_el_lut_se_guarda_relativo(tmp_path, invertir):
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    clip = proyecto.active.video_tracks()[-1].add(Clip(tmp_path / "a.mp4", 0.0, 2.0))
    clip.color.lut = str(invertir)
    clip.color.gamma_g = 140
    ruta = save_project(proyecto, tmp_path / "p")
    assert '"lut": "invertir.cube"' in ruta.read_text(encoding="utf-8")
    leido = load_project(ruta).active.video_tracks()[-1].clips[0]
    assert leido.color.lut == str(invertir.resolve()) and leido.color.gamma_g == 140


# --- en la ventana ----------------------------------------------------------------------

def test_el_panel_carga_el_lut_y_mueve_las_ruedas(ventana, media, invertir, tmp_path):
    from PySide6.QtGui import QColor

    ventana._place_video(media["gris"])
    ventana._seek(0.5)
    panel = ventana.color_panel
    assert panel.set_lut(str(invertir)) == ""
    ventana._flush()
    clip = ventana.sequence.top_clip_at(0.5)
    assert clip.color.lut == str(invertir)
    panel._lgg["gain_r"]._slider.setValue(150)
    assert clip.color.gain_r == 150
    malo = tmp_path / "malo.cube"
    malo.write_text("hola", encoding="utf-8")
    assert panel.set_lut(str(malo))
    assert clip.color.lut == str(invertir)

    # Gain rojo al 150 % sube el rojo antes del LUT y el LUT lo invierte:
    # el rojo baja y el verde queda en el gris invertido.
    pixel = QColor(ventana.preview.current_image().pixel(80, 60))
    assert pixel.green() == pytest.approx(127, abs=8)
    assert pixel.red() == pytest.approx(63, abs=10)
