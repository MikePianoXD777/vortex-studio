"""Transición cruzada entre dos clips."""

import pytest


def clips(ventana):
    return ventana.sequence.video_tracks()[-1].clips


def dos_clips(ventana, media):
    """Parte un video en dos mitades pegadas."""
    ventana._place_video(media["mudo"])
    ventana._seek(3.0)
    ventana.timeline.select(clips(ventana)[0])
    ventana.cut_at_playhead()
    return clips(ventana)


def test_necesita_un_clip_a_la_izquierda(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(clips(ventana)[0])
    ventana.set_dissolve(1.0)
    assert clips(ventana)[0].dissolve == 0.0


def test_poner_transicion(ventana, media):
    primero, segundo = dos_clips(ventana, media)
    ventana.timeline.select(segundo)
    ventana.set_dissolve(1.0)

    assert segundo.dissolve == 1.0
    assert ventana.history.undo_label == "Transición"


def test_no_puede_pasar_de_la_mitad_del_material(ventana, media):
    primero, segundo = dos_clips(ventana, media)
    ventana.timeline.select(segundo)
    ventana.set_dissolve(999.0)
    assert segundo.dissolve <= min(primero.duration, segundo.duration)


def test_se_reparte_alrededor_del_corte(ventana, media):
    """El corte queda al centro del cruce, como en Premiere."""
    primero, segundo = dos_clips(ventana, media)
    segundo.dissolve = 1.0
    corte = segundo.start

    assert ventana.sequence.dissolve_at(corte - 0.6) is None
    assert ventana.sequence.dissolve_at(corte - 0.4) is not None
    assert ventana.sequence.dissolve_at(corte + 0.4) is not None
    assert ventana.sequence.dissolve_at(corte + 0.6) is None


def test_el_avance_va_de_cero_a_uno(ventana, media):
    primero, segundo = dos_clips(ventana, media)
    segundo.dissolve = 1.0
    corte = segundo.start

    _, _, inicio = ventana.sequence.dissolve_at(corte - 0.49)
    _, _, medio = ventana.sequence.dissolve_at(corte)
    _, _, final = ventana.sequence.dissolve_at(corte + 0.49)

    assert inicio < 0.05
    assert medio == pytest.approx(0.5, abs=0.01)
    assert final > 0.95


def test_durante_el_cruce_se_componen_dos_capas(ventana, media):
    primero, segundo = dos_clips(ventana, media)
    segundo.dissolve = 1.0
    corte = segundo.start

    assert len(ventana._layers_at(corte - 1.0)) == 1     # fuera del cruce
    assert len(ventana._layers_at(corte)) == 2           # dentro


def test_las_opacidades_del_cruce_suman_uno(ventana, media):
    primero, segundo = dos_clips(ventana, media)
    segundo.dissolve = 1.0
    capas = ventana._layers_at(segundo.start)
    assert sum(a for _, a in capas) == pytest.approx(1.0, abs=0.02)


def test_el_cruce_cambia_la_imagen(ventana, media):
    """Que la mezcla llegue a los pixeles, no solo a los números."""
    def brillo(img):
        return sum(sum(img.pixelColor(x, y).getRgb()[:3])
                   for y in range(0, img.height(), 8)
                   for x in range(0, img.width(), 8))

    primero, segundo = dos_clips(ventana, media)
    corte = segundo.start

    ventana._seek(corte - 0.4)
    sin_cruce = brillo(ventana.preview.current_image())

    segundo.dissolve = 1.0
    ventana._seek(corte - 0.4)
    con_cruce = brillo(ventana.preview.current_image())

    assert sin_cruce != con_cruce


def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    primero, segundo = dos_clips(ventana, media)
    ventana.timeline.select(segundo)
    ventana.set_dissolve(0.8)

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[-1].clips[1]
    assert vuelto.dissolve == 0.8
