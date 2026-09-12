"""Slip: cambiar qué pedazo del archivo se ve sin mover el clip. E imán a marcadores."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from vortex_studio.model import Clip, Title
from vortex_studio.model.commands import slip
from vortex_studio.ui.timeline import TOOL_SLIP


def _evento(tipo, x, y, boton=Qt.LeftButton, botones=Qt.LeftButton):
    return QMouseEvent(tipo, QPointF(x, y), boton, botones, Qt.NoModifier)


def arrastrar(timeline, desde_x, hasta_x, y):
    timeline.mousePressEvent(_evento(QEvent.MouseButtonPress, desde_x, y))
    timeline.mouseMoveEvent(_evento(QEvent.MouseMove, hasta_x, y, Qt.NoButton))
    timeline.mouseReleaseEvent(_evento(QEvent.MouseButtonRelease, hasta_x, y))


def mitad_con_margen(ventana, media):
    """Un clip de 3 s sacado de un archivo de 6 s: hay material a los lados."""
    ventana._place_video(media["mudo"])
    ventana._cut(ventana.sequence.video_tracks()[-1].clips[0], 3.0, commit=False)
    clip = ventana.sequence.video_tracks()[-1].clips[1]      # lee de 3 a 6
    ventana.sequence.video_tracks()[-1].clips.remove(ventana.sequence.video_tracks()[-1].clips[0])
    clip.start, clip.in_point = 1.0, 1.5
    ventana._commit("preparar")
    ventana.timeline.select(clip)
    return clip


# --- el modelo ------------------------------------------------------------

def test_mueve_la_entrada_y_deja_el_clip_en_su_lugar():
    clip = Clip(source="/v.mp4", start=2.0, duration=3.0, in_point=1.0)
    assert slip(clip, 0.5, 10.0) == pytest.approx(0.5)
    assert clip.in_point == pytest.approx(1.5)
    assert (clip.start, clip.duration) == (2.0, 3.0)


def test_no_pasa_del_inicio_del_archivo():
    clip = Clip(source="/v.mp4", start=0.0, duration=3.0, in_point=0.4)
    assert slip(clip, -2.0, 10.0) == pytest.approx(-0.4)
    assert clip.in_point == 0.0


def test_no_pasa_del_final_del_archivo():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, in_point=1.0)
    slip(clip, 5.0, 6.0)
    assert clip.in_point == pytest.approx(2.0)          # 6 − 4 de material


def test_la_velocidad_cuenta_en_el_material():
    """A 2×, 4 s de pista gastan 8 s de archivo: en uno de 6 no hay de dónde."""
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, speed=2.0)
    assert slip(clip, 1.0, 6.0) == 0.0


def test_sin_duracion_conocida_solo_se_detiene_en_cero():
    clip = Clip(source="/v.mp4", start=0.0, duration=4.0, in_point=1.0)
    slip(clip, 100.0, None)
    assert clip.in_point == pytest.approx(101.0)
    slip(clip, -500.0, None)
    assert clip.in_point == 0.0


def test_un_texto_no_se_desliza():
    titulo = Title(start=0.0, duration=2.0, text="x")
    assert slip(titulo, 1.0, 5.0) == 0.0


# --- la herramienta en el timeline ----------------------------------------

def test_la_herramienta_se_elige_con_y(ventana):
    accion = ventana._actions["herramienta.slip"]
    assert accion.shortcut().toString() == "Y"
    accion.trigger()
    assert ventana.timeline.tool == TOOL_SLIP
    assert "Deslizar" in ventana.statusBar().currentMessage()


def test_arrastrar_a_la_derecha_muestra_material_de_antes(ventana, media):
    clip = mitad_con_margen(ventana, media)
    ventana.set_tool(TOOL_SLIP)
    tl = ventana.timeline
    y = tl._track_top(2) + 20
    x = tl.x_for(2.0)

    arrastrar(tl, x, x + 0.5 * tl.pixels_per_second, y)
    assert clip.in_point == pytest.approx(1.0, abs=0.02)
    assert (clip.start, clip.duration) == (1.0, 3.0)
    assert ventana.history.undo_label == "Deslizar contenido"


def test_arrastrar_de_mas_se_detiene_en_el_borde(ventana, media):
    clip = mitad_con_margen(ventana, media)
    ventana.set_tool(TOOL_SLIP)
    tl = ventana.timeline
    y = tl._track_top(2) + 20
    x = tl.x_for(2.0)

    arrastrar(tl, x, x - 20 * tl.pixels_per_second, y)     # hacia material de después
    assert clip.in_point == pytest.approx(3.0, abs=0.02)   # 6 s de archivo − 3 de clip


def test_deshacer_el_slip(ventana, media):
    clip = mitad_con_margen(ventana, media)
    ventana.set_tool(TOOL_SLIP)
    tl = ventana.timeline
    y = tl._track_top(2) + 20
    arrastrar(tl, tl.x_for(2.0), tl.x_for(2.0) + 40, y)
    ventana.undo()
    assert ventana.sequence.video_tracks()[-1].clips[0].in_point == pytest.approx(1.5)


def test_el_preview_sigue_al_slip(ventana, media):
    """Sin ver el cuadro mientras se arrastra, el slip se hace a ciegas."""
    clip = mitad_con_margen(ventana, media)
    ventana._seek(2.0)
    antes = ventana.preview.current_image()

    ventana.set_tool(TOOL_SLIP)
    tl = ventana.timeline
    y = tl._track_top(2) + 20
    tl.mousePressEvent(_evento(QEvent.MouseButtonPress, tl.x_for(2.0), y))
    tl.mouseMoveEvent(_evento(QEvent.MouseMove, tl.x_for(2.0) + 60, y, Qt.NoButton))
    durante = ventana.preview.current_image()
    tl.mouseReleaseEvent(_evento(QEvent.MouseButtonRelease, tl.x_for(2.0) + 60, y))

    assert antes != durante


def test_el_slip_sobre_un_texto_no_hace_nada(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(0.5)
    ventana.add_title()
    antes = ventana.history._index
    ventana.set_tool(TOOL_SLIP)
    tl = ventana.timeline
    y = tl._track_top(0) + 20
    arrastrar(tl, tl.x_for(1.0), tl.x_for(1.0) + 60, y)
    assert ventana.history._index == antes


# --- de cuadro en cuadro --------------------------------------------------

def test_alt_punto_adelanta_un_cuadro_de_material(ventana, media):
    clip = mitad_con_margen(ventana, media)
    assert ventana._actions["editar.slip_adelante"].shortcut().toString() == "Alt+."
    ventana._actions["editar.slip_adelante"].trigger()
    assert clip.in_point == pytest.approx(1.5 + 1 / 30)
    assert ventana.history.undo_label == "Deslizar contenido"


def test_alt_coma_regresa_un_cuadro(ventana, media):
    clip = mitad_con_margen(ventana, media)
    ventana._actions["editar.slip_atras"].trigger()
    assert clip.in_point == pytest.approx(1.5 - 1 / 30)


def test_en_el_limite_avisa_y_no_ensucia_el_historial(ventana, media):
    ventana._place_video(media["mudo"])            # entrada en 0, sin margen
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    antes = ventana.history._index
    ventana.slip_selected(-1)
    assert ventana.history._index == antes
    assert "No hay más material" in ventana.statusBar().currentMessage()


def test_sin_clip_seleccionado_lo_dice(ventana):
    ventana.timeline.select(None)
    ventana.slip_selected(1)
    assert "Selecciona" in ventana.statusBar().currentMessage()


# --- imán a marcadores ----------------------------------------------------

def test_el_iman_pega_a_un_marcador(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.sequence.add_marker(2.5)
    tl = ventana.timeline
    cerca = 2.5 + 3 / tl.pixels_per_second           # 3 pixeles
    assert tl._snap(cerca) == pytest.approx(2.5)


def test_lejos_del_marcador_no_pega(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.sequence.add_marker(2.5)
    tl = ventana.timeline
    lejos = 2.5 + 40 / tl.pixels_per_second
    assert tl._snap(lejos) != pytest.approx(2.5)


def test_arrastrar_un_clip_pega_su_inicio_al_marcador(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._place_image(media["logo"])
    imagen = ventana.sequence.video_tracks()[0].clips[0]
    ventana.sequence.add_marker(3.0)

    tl = ventana.timeline
    y = tl._track_top(1) + 20
    agarre = tl.x_for(imagen.start + 0.5)
    destino = agarre + (3.0 - imagen.start) * tl.pixels_per_second + 4
    arrastrar(tl, agarre, destino, y)
    assert imagen.start == pytest.approx(3.0)
