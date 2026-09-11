"""Marcadores en la línea de tiempo."""

from vortex_studio.model.serialize import load_project, save_project


def test_poner_y_ordenar(secuencia):
    secuencia.add_marker(3.0, "corte")
    secuencia.add_marker(1.0, "intro")
    assert [m.name for m in secuencia.markers] == ["intro", "corte"]


def test_poner_dos_en_el_mismo_cuadro_reemplaza(secuencia):
    secuencia.add_marker(1.0, "viejo")
    secuencia.add_marker(1.0, "nuevo")
    assert len(secuencia.markers) == 1
    assert secuencia.markers[0].name == "nuevo"


def test_navegar_entre_marcadores(secuencia):
    for t in (1.0, 3.0, 5.0):
        secuencia.add_marker(t)

    assert secuencia.next_marker(0.0).time == 1.0
    assert secuencia.next_marker(1.0).time == 3.0      # no se queda en el mismo
    assert secuencia.previous_marker(3.0).time == 1.0
    assert secuencia.next_marker(5.0) is None
    assert secuencia.previous_marker(1.0) is None


def test_desde_la_ventana(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    ventana.add_marker("uno")
    ventana._seek(3.0)
    ventana.add_marker("dos")

    ventana._seek(0.0)
    ventana.next_marker()
    assert ventana.timeline.playhead == 1.0
    ventana.next_marker()
    assert ventana.timeline.playhead == 3.0
    ventana.previous_marker()
    assert ventana.timeline.playhead == 1.0


def test_entran_al_historial(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_marker("x")
    assert ventana.history.undo_label == "Poner marcador"
    ventana.undo()
    assert ventana.sequence.markers == []


def test_borrar_todos(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_marker("a")
    ventana._seek(2.0)
    ventana.add_marker("b")
    ventana.clear_markers()
    assert ventana.sequence.markers == []


def test_sobreviven_al_guardado(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.add_marker("aquí va el corte")

    destino = save_project(ventana.project, tmp_path / "p")
    marcadores = load_project(destino).active.markers

    assert len(marcadores) == 1
    assert marcadores[0].name == "aquí va el corte"
    assert marcadores[0].time == 2.0


def test_salen_en_la_barra_de_estado(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_marker()
    assert "1 marcador" in ventana.statusBar().currentMessage()
    ventana._seek(2.0)
    ventana.add_marker()
    assert "2 marcadores" in ventana.statusBar().currentMessage()
