"""Deshacer y rehacer."""

from vortex_studio.model import Sequence
from vortex_studio.model.history import History


def test_arranca_sin_nada_que_deshacer(secuencia):
    h = History()
    h.reset(secuencia)
    assert not h.can_undo and not h.can_redo


def test_deshacer_y_rehacer(secuencia):
    v1 = secuencia.video_tracks()[-1]
    h = History()
    h.reset(secuencia)

    v1.append("/tmp/a.mp4", 4.0)
    h.push(secuencia, "Importar")
    v1.append("/tmp/b.mp4", 2.0)
    h.push(secuencia, "Importar")

    assert h.undo().duration == 4.0
    assert h.undo().duration == 0.0
    assert not h.can_undo
    assert h.redo().duration == 4.0


def test_ramificar_descarta_lo_de_adelante(secuencia):
    v1 = secuencia.video_tracks()[-1]
    h = History()
    h.reset(secuencia)
    v1.append("/tmp/a.mp4", 4.0)
    h.push(secuencia, "Uno")

    vuelto = h.undo()
    assert h.can_redo

    # Un cambio de verdad sí abre una rama nueva y tira lo que estaba adelante.
    vuelto.video_tracks()[-1].append("/tmp/otro.mp4", 9.0)
    h.push(vuelto, "Otro camino")
    assert not h.can_redo
    assert h.undo_label == "Otro camino"


def test_un_estado_identico_no_crea_entrada(secuencia):
    h = History()
    h.reset(secuencia)
    h.push(secuencia, "Sin cambios")
    assert not h.can_undo


def test_etiquetas(secuencia):
    h = History()
    h.reset(secuencia)
    secuencia.video_tracks()[-1].append("/tmp/a.mp4", 1.0)
    h.push(secuencia, "Importar video")
    assert h.undo_label == "Importar video"
    h.undo()
    assert h.redo_label == "Importar video"


def test_no_crece_sin_limite(secuencia):
    h = History(limit=5)
    h.reset(secuencia)
    for i in range(20):
        secuencia.video_tracks()[-1].append(f"/tmp/{i}.mp4", 1.0)
        h.push(secuencia, f"Paso {i}")
    assert len(h._states) <= 5
