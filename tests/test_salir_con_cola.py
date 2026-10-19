"""Cerrar el editor con exportaciones en curso.

Antes la única salida era cancelarlas: una exportación de una hora se perdía
por cerrar la ventana. Ahora también se puede dejar que terminen.
"""

import time

from PySide6.QtWidgets import QApplication, QMessageBox

from vortex_studio.ui.render_queue import CANCELLED, DONE, FAILED


def esperar(condicion, segundos=60):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def exportando(ventana, media, tmp_path, ruta="largo.mp4"):
    ventana._place_video(media["mudo"])
    ventana._dirty = False
    return ventana.queue_export(tmp_path / ruta, 0.0, 6.0, "Borrador")


def test_seguir_editando_no_cierra_nada(ventana, media, tmp_path, monkeypatch):
    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "seguir")
    ventana.close()
    assert ventana.isVisible()
    assert ventana.render_queue.wait(60)
    assert job.status == DONE


def test_cancelarlas_y_salir(ventana, media, tmp_path, monkeypatch):
    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "cancelar")
    ventana.close()
    assert not ventana.isVisible()
    assert job.status == CANCELLED or job.status == DONE   # pudo alcanzar a terminar


def test_salir_al_terminar(ventana, media, tmp_path, monkeypatch):
    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    assert ventana.isVisible(), "no debe cerrar mientras exporta"
    assert not ventana.queue_panel.isHidden()
    assert esperar(lambda: not ventana.isVisible(), 60), "debió cerrarse al terminar"
    assert job.status == DONE and job.path.exists()


def test_si_falla_no_se_cierra_solo(ventana, media, tmp_path, monkeypatch):
    ventana._place_video(media["mudo"])
    ventana._dirty = False
    malo = ventana.queue_export(tmp_path / "no" / "existe" / "x.mp4", 0.0, 1.0, "Borrador")
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    assert esperar(lambda: malo.status == FAILED and avisos, 60)
    assert ventana.isVisible()
    assert not ventana._quit_after_render


def test_cambiar_de_opinion(ventana, media, tmp_path, monkeypatch):
    """Elegir esperar y luego volver a cerrar pregunta otra vez."""
    job = exportando(ventana, media, tmp_path)
    respuestas = iter(["esperar", "cancelar"])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: next(respuestas))
    ventana.close()
    assert ventana.isVisible()
    ventana.close()
    assert not ventana.isVisible()
    assert job.status in (CANCELLED, DONE)
