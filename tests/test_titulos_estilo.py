"""Fuente, contorno y sombra de los títulos."""

import pytest
from PySide6.QtGui import QColor, QFontDatabase

from vortex_studio.model import Title
from vortex_studio.ui.compositor import compose


def pintar(**kw):
    titulo = Title(start=0.0, duration=2.0, text="VORTEX", x=0.5, y=0.5, size=0.3,
                   outline=False, **kw)
    return compose(320, 180, [], [], [titulo])


def contar(imagen, prueba):
    return sum(1 for y in range(0, imagen.height(), 2) for x in range(0, imagen.width(), 2)
               if prueba(QColor(imagen.pixel(x, y))))


def verde(c):
    return c.green() > 60 and c.red() < 40 and c.blue() < 40


def test_la_fuente_cambia_el_dibujo(qapp):
    familias = [f for f in QFontDatabase.families() if not QFontDatabase.isPrivateFamily(f)]
    distintas = [f for f in familias if "mono" in f.lower()] or familias[1:]
    if not distintas:
        pytest.skip("esta máquina solo tiene una fuente")
    assert pintar().constBits().tobytes() != pintar(font=distintas[0]).constBits().tobytes()


def test_color_y_grosor_del_contorno(qapp):
    rojo = lambda c: c.red() > 150 and c.green() < 60
    delgado = contar(pintar(outline_color="#ff0000", outline_width=0.02) if False else
                     compose(320, 180, [], [], [Title(start=0, duration=2, text="VORTEX",
                             x=0.5, y=0.5, size=0.3, outline_color="#ff0000",
                             outline_width=0.02)]), rojo)
    grueso = contar(compose(320, 180, [], [], [Title(start=0, duration=2, text="VORTEX",
                            x=0.5, y=0.5, size=0.3, outline_color="#ff0000",
                            outline_width=0.15)]), rojo)
    assert delgado > 0
    assert grueso > delgado * 1.5


def test_sin_sombra_no_hay_sombra(qapp):
    assert contar(pintar(shadow_color="#00ff00"), verde) == 0


def test_la_sombra_se_dibuja_desplazada(qapp):
    img = pintar(shadow=True, shadow_color="#00ff00", shadow_opacity=1.0,
                 shadow_distance=0.12)
    assert contar(img, verde) > 20


def test_la_sombra_desenfocada_se_reparte(qapp):
    """Con desenfoque hay más pixeles tocados, y más tenues."""
    dura = pintar(shadow=True, shadow_color="#00ff00", shadow_opacity=1.0,
                  shadow_distance=0.1)
    suave = pintar(shadow=True, shadow_color="#00ff00", shadow_opacity=1.0,
                   shadow_distance=0.1, shadow_blur=0.15)
    tenue = lambda c: 8 < c.green() < 90 and c.red() < 30
    assert contar(suave, tenue) > contar(dura, tenue)


def test_el_estilo_se_guarda(tmp_path):
    from vortex_studio.model import Project
    from vortex_studio.model.serialize import load_project, save_project

    proyecto = Project()
    proyecto.active.text_tracks()[0].add(Title(
        start=0.0, duration=2.0, font="DejaVu Sans", outline_color="#123456",
        outline_width=0.1, shadow=True, shadow_color="#654321", shadow_blur=0.2))
    t = load_project(save_project(proyecto, tmp_path / "p")).active.text_tracks()[0].clips[0]
    assert (t.font, t.outline_color, t.outline_width, t.shadow, t.shadow_color,
            t.shadow_blur) == ("DejaVu Sans", "#123456", 0.1, True, "#654321", 0.2)


def test_el_panel_escribe_el_estilo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo = ventana.timeline.selected
    panel = ventana.text_panel

    panel._shadow.setChecked(True)
    panel._shadow_blur._slider.setValue(12)
    panel._outline_width._slider.setValue(10)
    panel.set_style_color("shadow_color", "#ff00ff")
    assert titulo.shadow and titulo.shadow_blur == pytest.approx(0.12)
    assert titulo.outline_width == pytest.approx(0.10)
    assert titulo.shadow_color == "#ff00ff"

    familias = QFontDatabase.families()
    if len(familias) > 1:
        panel._font.setCurrentFont(familias[-1])
        assert titulo.font == panel._font.currentFont().family()


def test_cargar_un_titulo_no_lo_reescribe(ventana, media):
    """Mostrar un texto en el panel no puede ponerle la fuente de la interfaz."""
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo = ventana.timeline.selected
    ventana.text_panel.edit(titulo)
    assert titulo.font == ""
