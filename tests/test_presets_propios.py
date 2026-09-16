"""Presets de exportación propios y exportar por marcadores."""

import time

import av
import pytest
from PySide6.QtWidgets import QApplication

from vortex_studio.media.presets import (
    PRESETS,
    all_presets,
    by_name,
    delete_user_preset,
    presets_path,
    save_user_preset,
    user_presets,
)
from vortex_studio.ui.main_window import ExportDialog


@pytest.fixture(autouse=True)
def limpio():
    presets_path().unlink(missing_ok=True)
    yield
    presets_path().unlink(missing_ok=True)


def test_guardar_y_leer_un_preset_propio():
    from dataclasses import replace

    propio = save_user_preset(replace(by_name("H.264 1080p"), name="TikTok 60", fps=60.0,
                                      quality="Alta"))
    assert propio.user
    leido = by_name("TikTok 60")
    assert (leido.short_side, leido.fps, leido.quality, leido.user) == (1080, 60.0, "Alta", True)
    assert [p.name for p in all_presets()][-1] == "TikTok 60"


def test_los_de_fabrica_no_se_pisan_ni_se_borran():
    from dataclasses import replace

    with pytest.raises(ValueError):
        save_user_preset(replace(PRESETS[1], name="H.264 4K"))
    with pytest.raises(ValueError):
        save_user_preset(replace(PRESETS[1], name="   "))
    assert not delete_user_preset("H.264 1080p")
    assert len(all_presets()) == len(PRESETS)


def test_borrar_y_un_archivo_danado_no_rompe():
    from dataclasses import replace

    save_user_preset(replace(PRESETS[0], name="Borrador"))
    assert delete_user_preset("Borrador") and user_presets() == []
    presets_path().write_text("{no es json", encoding="utf-8")
    assert user_presets() == [] and len(all_presets()) == len(PRESETS)


def test_el_dialogo_guarda_y_borra(ventana, media):
    ventana._place_video(media["mudo"])
    dialogo = ExportDialog(ventana, 0.0, 6.0, ventana.sequence)
    dialogo._quality.setCurrentText("Borrador")
    dialogo._fps.setCurrentIndex(dialogo._fps.findData(24.0))
    assert dialogo.save_current_as("Revisión") is not None
    assert dialogo._preset.currentText() == "Revisión" and dialogo._delete_preset.isEnabled()
    otro = ExportDialog(ventana, 0.0, 6.0, ventana.sequence)
    otro._preset.setCurrentText("Revisión")
    assert otro.quality() == "Borrador" and otro.fps() == 24.0
    assert otro.save_current_as("H.264 4K") is None and "fábrica" in otro._preset_msg.text()
    from PySide6.QtWidgets import QMessageBox

    otro_si = staticmethod(lambda *a, **k: QMessageBox.Yes)
    monkeypatch_local = pytest.MonkeyPatch()
    monkeypatch_local.setattr(QMessageBox, "question", otro_si)
    try:
        assert otro.delete_current() and by_name("Revisión").name == PRESETS[0].name
    finally:
        monkeypatch_local.undo()


def test_los_cuadros_por_segundo_del_preset_llegan_al_archivo(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    dialogo = ExportDialog(ventana, 0.0, 2.0, ventana.sequence)
    dialogo._fps.setCurrentIndex(dialogo._fps.findData(15.0 if dialogo._fps.findData(15.0) >= 0
                                                       else 24.0))
    preset = dialogo.export_preset()
    job = ventana.queue_export(tmp_path / "fps.mp4", 0.0, 2.0, "Borrador", False, preset)
    assert ventana.render_queue.wait(60) and job.status == "Listo", job.error
    with av.open(str(job.path)) as c:
        assert float(c.streams.video[0].average_rate) == pytest.approx(preset.fps, abs=0.5)
        assert c.streams.video[0].frames == pytest.approx(2 * preset.fps, abs=2)


def test_exportar_por_marcadores_manda_un_trabajo_por_tramo(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(0.0)
    ventana.add_marker("Intro")
    ventana._seek(2.0)
    ventana.add_marker("Parte: dos")
    trabajos = ventana.queue_marker_exports(tmp_path, by_name("Tamaño de la secuencia"),
                                            "Borrador", False)
    assert [t.path.name for t in trabajos] == ["01 - Intro.mp4", "02 - Parte dos.mp4"]
    assert [(t.start, t.end) for t in trabajos] == [(0.0, 2.0), (2.0, 6.0)]
    assert ventana.render_queue.wait(90)
    for trabajo in trabajos:
        with av.open(str(trabajo.path)) as c:
            assert float(c.duration / av.time_base) == \
                pytest.approx(trabajo.end - trabajo.start, abs=0.15)


def test_sin_marcadores_avisa(tmp_path, ventana, media):
    ventana._place_video(media["mudo"])
    assert ventana.queue_marker_exports(tmp_path) == []
    assert "marcadores" in ventana.statusBar().currentMessage()
