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


# --- con cambios sin guardar ------------------------------------------------

def preguntas_de_guardar(monkeypatch, respuestas):
    """Contesta «¿Guardar?» en orden y apunta cada vez que salió. Cuando se
    acaban, «Cancelar»: es lo que pasa si nadie está para hacer clic."""
    hechas = []
    respuestas = iter(respuestas)

    def question(*args, **kwargs):
        hechas.append(args[1] if len(args) > 1 else "")
        return next(respuestas, QMessageBox.Cancel)
    monkeypatch.setattr(QMessageBox, "question", question)
    return hechas


def test_no_guardar_y_salir_al_terminar_pregunta_una_sola_vez(ventana, media, tmp_path,
                                                              monkeypatch):
    """Antes, al terminar la exportación volvía a salir «Hay cambios sin
    guardar» y el editor se quedaba abierto esperando un clic."""
    job = exportando(ventana, media, tmp_path)
    ventana._place_video(media["gris"], at=10.0)          # queda sin guardar
    hechas = preguntas_de_guardar(monkeypatch, [QMessageBox.Discard])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    assert ventana.isVisible() and len(hechas) == 1
    assert esperar(lambda: job.status == DONE, 60)
    assert esperar(lambda: not ventana.isVisible(), 10), "debió cerrarse solo"
    assert len(hechas) == 1


def test_si_cambia_algo_mientras_espera_vuelve_a_preguntar(ventana, media, tmp_path,
                                                           monkeypatch):
    """Lo de después de contestar no se tira sin avisar, aunque no pase por el
    historial (importar al panel de medios también ensucia el proyecto)."""
    job = exportando(ventana, media, tmp_path)
    ventana._place_video(media["gris"], at=10.0)
    hechas = preguntas_de_guardar(monkeypatch, [QMessageBox.Discard, QMessageBox.Discard])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    ventana.import_to_bin([media["tono"]])
    assert esperar(lambda: job.status == DONE, 60)
    assert esperar(lambda: not ventana.isVisible(), 10)
    assert len(hechas) == 2


def test_cancelar_el_cierre_automatico_lo_desarma(ventana, media, tmp_path, monkeypatch):
    """Antes, cancelar la pregunta del cierre automático dejaba armado «Salir
    al terminar»: una exportación de mucho después cerraba el editor solo."""
    job = exportando(ventana, media, tmp_path)
    hechas = preguntas_de_guardar(monkeypatch, [QMessageBox.Cancel])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()                                     # sin cambios: no pregunta
    ventana._place_video(media["gris"], at=10.0)        # y luego sí los hay
    assert esperar(lambda: job.status == DONE and hechas, 60)
    assert ventana.isVisible() and not ventana._quit_after_render

    ventana._dirty = False                              # como si hubiera guardado
    otro = ventana.queue_export(tmp_path / "otro.mp4", 0.0, 1.0, "Borrador")
    assert esperar(lambda: otro.status == DONE, 60)
    esperar(lambda: not ventana.isVisible(), 1)         # tiempo de sobra para cerrarse
    assert ventana.isVisible()


def test_abrir_otro_proyecto_desarma_salir_al_terminar(ventana, media, tmp_path,
                                                       monkeypatch):
    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    ventana.new_project()
    assert not ventana._quit_after_render
    assert esperar(lambda: job.status == DONE, 60)
    esperar(lambda: not ventana.isVisible(), 1)
    assert ventana.isVisible()


def test_si_termina_mientras_se_pregunta_no_cierra_por_debajo(ventana, media, tmp_path,
                                                              monkeypatch):
    """La exportación termina con «Hay exportaciones sin terminar» abierto otra
    vez: el cierre automático caía adentro de ese cierre y apagaba el editor
    aunque luego se eligiera «Seguir editando»."""
    job = exportando(ventana, media, tmp_path)
    llegados = []
    ventana.render_queue.finished.connect(llegados.append)

    def mientras_termina():
        assert esperar(lambda: llegados, 60)            # el aviso llegó con el diálogo abierto
        return "seguir"

    respuestas = iter([lambda: "esperar", mientras_termina])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: next(respuestas)())
    ventana.close()
    ventana.close()
    assert job.status == DONE
    assert ventana.isVisible()
    assert not ventana._quit_after_render


def test_si_termina_mientras_se_pregunta_y_se_elige_esperar_cierra(ventana, media, tmp_path,
                                                                    monkeypatch):
    """Ya no queda nada que esperar: se cierra, en vez de quedarse armado sin
    que ninguna exportación vaya a avisar."""
    job = exportando(ventana, media, tmp_path)
    llegados = []
    ventana.render_queue.finished.connect(llegados.append)

    def mientras_termina():
        assert esperar(lambda: llegados, 60)
        return "esperar"

    respuestas = iter([lambda: "esperar", mientras_termina])
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: next(respuestas)())
    ventana.close()
    ventana.close()
    assert job.status == DONE
    assert not ventana.isVisible()


def test_no_se_cierra_debajo_de_un_dialogo_abierto(ventana, media, tmp_path, monkeypatch):
    """La cola termina con otro diálogo encima —exportar, guardar como…—:
    antes el editor se apagaba por debajo, y lo que hiciera el diálogo al
    aceptarse caía en una ventana ya cerrada."""
    from PySide6.QtWidgets import QDialog

    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    dialogo = QDialog(ventana)
    dialogo.setModal(True)
    dialogo.show()
    assert esperar(lambda: job.status == DONE, 60)
    esperar(lambda: not ventana.isVisible(), 1)
    assert ventana.isVisible()
    dialogo.close()
    assert esperar(lambda: not ventana.isVisible(), 5), "al cerrar el diálogo sí se cierra"


def test_un_modal_ajeno_no_detiene_el_cierre(ventana, media, tmp_path, monkeypatch):
    """Solo cuentan los diálogos de esta ventana. Con cualquier modal abierto
    —de otra ventana, o uno que quedó colgado—, el editor ya no se cerraba
    nunca solo."""
    from PySide6.QtWidgets import QDialog, QWidget

    job = exportando(ventana, media, tmp_path)
    monkeypatch.setattr(ventana, "_ask_quit_with_exports", lambda: "esperar")
    ventana.close()
    otra = QWidget()
    ajeno = QDialog(otra)
    ajeno.setModal(True)
    ajeno.show()
    try:
        assert esperar(lambda: job.status == DONE, 60)
        assert esperar(lambda: not ventana.isVisible(), 5), "un modal ajeno no lo detiene"
    finally:
        ajeno.close()
        otra.close()
