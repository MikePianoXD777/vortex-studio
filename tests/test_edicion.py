"""Edición en el timeline: cortar, mover, recortar, eliminar."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from vortex_studio.ui.timeline import TOOL_RAZOR


def clips(ventana):
    return ventana.sequence.video_tracks()[-1].clips


def _evento(tipo, x, y, boton=Qt.LeftButton, botones=Qt.LeftButton):
    return QMouseEvent(tipo, QPointF(x, y), boton, botones, Qt.NoModifier)


def arrastrar(ventana, desde_x, hasta_x, y):
    ventana.timeline.mousePressEvent(_evento(QEvent.MouseButtonPress, desde_x, y))
    ventana.timeline.mouseMoveEvent(
        _evento(QEvent.MouseMove, hasta_x, y, Qt.NoButton))
    ventana.timeline.mouseReleaseEvent(_evento(QEvent.MouseButtonRelease, hasta_x, y))


def y_de_v1(ventana):
    return ventana.timeline._track_top(2) + 20


# --- cortar ---------------------------------------------------------------

def test_cortar_parte_en_dos(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(3.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()

    piezas = clips(ventana)
    assert len(piezas) == 2
    assert piezas[0].duration == 3.0
    assert piezas[1].start == 3.0


def test_la_segunda_mitad_lee_desde_el_corte(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()
    assert clips(ventana)[1].in_point == 2.0


def test_cortar_no_deja_hueco(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.5)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()
    a, b = clips(ventana)
    assert abs(a.end - b.start) < 1e-9


def test_cada_mitad_tiene_su_propio_color(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(3.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()

    clips(ventana)[1].color.brightness = 60
    assert clips(ventana)[0].color.brightness == 0


def test_cortar_en_un_borde_no_hace_nada(ventana, media):
    ventana._place_video(media["mudo"])
    clip = clips(ventana)[0]
    assert not ventana._cut(clip, clip.start, commit=False)
    assert not ventana._cut(clip, clip.end, commit=False)
    assert len(clips(ventana)) == 1


# --- arrastrar y recortar -------------------------------------------------

def test_arrastrar_mueve_en_el_tiempo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._fit_zoom()
    clip = clips(ventana)[0]

    x = ventana.timeline.x_for(clip.start) + 40
    arrastrar(ventana, x, x + 100, y_de_v1(ventana))

    assert clip.start > 0
    assert ventana.history.undo_label == "Mover clip"


def test_recortar_por_el_borde(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._fit_zoom()
    clip = clips(ventana)[0]
    original = clip.duration

    x = ventana.timeline.x_for(clip.end) - 2
    arrastrar(ventana, x, x - 80, y_de_v1(ventana))

    assert clip.duration < original
    assert ventana.history.undo_label == "Recortar clip"


def test_no_se_puede_recortar_a_cero(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._fit_zoom()
    clip = clips(ventana)[0]

    x = ventana.timeline.x_for(clip.end) - 2
    arrastrar(ventana, x, ventana.timeline.x_for(0) - 500, y_de_v1(ventana))

    assert clip.duration >= ventana.sequence.frame_duration - 1e-9


def test_soltar_encima_sobrescribe(ventana, media):
    """Lo que se suelta encima recorta a lo que ya estaba, no se encima."""
    ventana._place_video(media["mudo"])
    ventana._seek(3.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()
    ventana._fit_zoom()

    segunda = clips(ventana)[1]
    x = ventana.timeline.x_for(segunda.start) + 20
    arrastrar(ventana, x, x - 60, y_de_v1(ventana))

    piezas = sorted(clips(ventana), key=lambda c: c.start)
    for a, b in zip(piezas, piezas[1:]):
        assert a.end <= b.start + 1e-9, "quedó traslape"


# --- navaja, eliminar, duplicar ------------------------------------------

def test_navaja(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._fit_zoom()
    ventana.set_tool(TOOL_RAZOR)

    clip = clips(ventana)[0]
    x = ventana.timeline.x_for(clip.start + clip.duration / 2)
    ventana.timeline.mousePressEvent(_evento(QEvent.MouseButtonPress, x, y_de_v1(ventana)))

    assert len(clips(ventana)) == 2


def test_eliminar_deja_hueco(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()

    ventana.timeline.select(clips(ventana)[0])
    ventana.delete_selected()
    assert clips(ventana)[0].start == 2.0


def test_eliminar_cerrando_hueco(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()

    ventana.timeline.select(clips(ventana)[0])
    ventana.ripple_delete()
    assert clips(ventana)[0].start == 0.0


def test_duplicar(ventana, media):
    ventana._place_video(media["mudo"])
    original = clips(ventana)[0]
    ventana.timeline.select(original)
    ventana.duplicate_selected()

    copia = clips(ventana)[1]
    assert copia.start == original.end
    assert copia is not original

    copia.color.brightness = 40
    assert original.color.brightness == 0


# --- casos límite ---------------------------------------------------------

def test_nada_truena_con_la_secuencia_vacia(ventana):
    ventana.toggle_play()
    ventana.cut_at_playhead()
    ventana.delete_selected()
    ventana.ripple_delete()
    ventana.duplicate_selected()
    ventana.undo()
    ventana.redo()
    assert ventana.preview.current_image() is None
