"""La cola de render: exportar en segundo plano, con progreso y cancelar."""

import time

import av
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vortex_studio.media.presets import PRESETS, by_name
from vortex_studio.ui.render_queue import CANCELLED, DONE, FAILED, RUNNING


def esperar(condicion, segundos=60):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def duracion(path):
    with av.open(str(path)) as c:
        return float(c.duration / av.time_base), sorted(s.type for s in c.streams)


def test_exporta_en_segundo_plano(tmp_path, ventana, media):
    ventana._place_video(media["sonoro"])
    job = ventana.queue_export(tmp_path / "fondo.mp4", 0.0, 2.0, "Borrador")
    assert not ventana.queue_panel.isHidden(), "la cola tenía que asomarse"
    assert ventana.render_queue.wait(60)
    assert job.status == DONE, job.error
    segundos, tipos = duracion(job.path)
    assert segundos == pytest.approx(2.0, abs=0.15) and tipos == ["audio", "video"]
    # El aviso llega por una señal encolada desde el hilo del render.
    assert esperar(lambda: "Exportado" in ventana.statusBar().currentMessage(), 5)


def test_editar_despues_no_cambia_lo_que_se_exporta(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    job = ventana.queue_export(tmp_path / "congelado.mp4", 0.0, 3.0, "Borrador")
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    ventana.delete_selected()                 # justo después de darle Exportar
    assert ventana.render_queue.wait(60)
    assert job.status == DONE
    assert duracion(job.path)[0] == pytest.approx(3.0, abs=0.15)


def test_cancelar_a_media_exportacion(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    cola = ventana.render_queue
    cola.NOTIFY_SECONDS = 0.0

    def al_avanzar(job):
        if job is not None and job.status == RUNNING and job.done >= 5:
            cola.cancel(job)

    # Conexión directa: corre en el hilo del render, a media codificación,
    # que es justo el caso que hay que probar.
    cola.changed.connect(al_avanzar, Qt.DirectConnection)
    job = ventana.queue_export(tmp_path / "cancelado.mp4", 0.0, 6.0, "Borrador")
    assert cola.wait(60)
    cola.changed.disconnect(al_avanzar)
    assert job.status == CANCELLED
    assert 5 <= job.done < job.total
    assert not job.path.exists()


def test_cancelar_uno_en_fila_no_toca_al_que_corre(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    primero = ventana.queue_export(tmp_path / "uno.mp4", 0.0, 2.0, "Borrador")
    segundo = ventana.queue_export(tmp_path / "dos.mp4", 0.0, 2.0, "Borrador")
    ventana.render_queue.cancel(segundo)
    assert ventana.render_queue.wait(60)
    assert primero.status == DONE and segundo.status == CANCELLED
    assert primero.path.exists() and not segundo.path.exists()


def test_solo_audio_en_la_cola(tmp_path, ventana, media):
    ventana._place_video(media["sonoro"])
    preset = next(p for p in PRESETS if p.kind == "audio")
    job = ventana.queue_export(tmp_path / "sonido.m4a", 0.0, 2.0, preset=preset)
    assert ventana.render_queue.wait(60)
    assert job.status == DONE
    assert duracion(job.path)[1] == ["audio"]


def test_un_error_se_reporta_sin_tumbar_la_cola(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    malo = ventana.queue_export(tmp_path / "no" / "existe" / "x.mp4", 0.0, 1.0, "Borrador")
    bueno = ventana.queue_export(tmp_path / "bien.mp4", 0.0, 1.0, "Borrador")
    assert ventana.render_queue.wait(60)
    QApplication.processEvents()
    assert malo.status == FAILED and malo.error
    assert bueno.status == DONE


def test_el_panel_muestra_cada_trabajo(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    job = ventana.queue_export(tmp_path / "panel.mp4", 0.0, 1.0,
                               preset=by_name("H.264 1080p"))
    assert ventana.render_queue.wait(60)
    assert esperar(lambda: ventana.queue_panel.row_for(job) is not None and
                   not ventana.queue_panel.row_for(job).cancel_button.isEnabled())
    fila = ventana.queue_panel.row_for(job)
    assert "Listo" in fila._state.text()
    with av.open(str(job.path)) as c:
        assert c.streams.video[0].codec_context.height == 1080

    ventana.render_queue.clear_finished()
    assert esperar(lambda: ventana.queue_panel.row_for(job) is None)
