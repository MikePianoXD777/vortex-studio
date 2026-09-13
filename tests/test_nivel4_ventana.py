"""Lo del paso 4 desde la ventana: efectos, espacio de color, versiones, intercambio y paralelo."""

import shutil
import subprocess
from pathlib import Path

import pytest

from vortex_studio.model import Clip
from vortex_studio.model import versions as ver
from vortex_studio.model.color import SPACE_HLG, SPACE_NONE, SPACE_OCIO, SPACE_PQ
from vortex_studio.model.serialize import load_project, save_project

FFMPEG = shutil.which("ffmpeg")


def _con_clip(ventana, media):
    clip = ventana.sequence.track_named("V1").add(Clip(media["mudo"], 0.0, 2.0))
    ventana._commit("Poner clip")
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    return clip


# --- panel de efectos ------------------------------------------------------------------------

def test_agregar_un_efecto_desde_el_panel_y_deshacer(ventana, media):
    clip = _con_clip(ventana, media)
    panel = ventana.effects_panel
    indice = panel.plugin_menu.findData("negativo")
    panel.plugin_menu.setCurrentIndex(indice)
    panel.plugin_add.click()
    assert [e["plugin"] for e in clip.color.effects] == ["negativo"]
    assert ventana.history.undo_label == "Efecto: Negativo"
    ventana.undo()
    assert ventana.sequence.track_named("V1").clips[0].color.effects == []


def test_los_controles_del_efecto_cambian_su_valor(ventana, media):
    clip = _con_clip(ventana, media)
    panel = ventana.effects_panel
    assert panel.add_effect("desenfoque")
    assert set(panel.effect_rows) == {"radio"}
    panel.effect_rows["radio"]._slider.setValue(1250)
    assert clip.color.effects[0]["values"]["radio"] == pytest.approx(12.5)
    assert panel.add_effect("pixelado")
    assert set(panel.effect_rows) == {"ancho", "alto"}
    panel.effects_list.setCurrentRow(0)
    assert set(panel.effect_rows) == {"radio"}


def test_apagar_y_quitar_efectos(ventana, media):
    clip = _con_clip(ventana, media)
    panel = ventana.effects_panel
    panel.add_effect("grano")
    panel.add_effect("espejo")
    panel.effects_list.setCurrentRow(0)
    panel.effect_on.setChecked(False)
    assert clip.color.effects[0]["enabled"] is False
    assert "apagado" in panel.effects_list.item(0).text()
    assert panel.remove_effect()
    assert [e["plugin"] for e in clip.color.effects] == ["espejo"]
    assert not panel.add_effect("no-existe")


def test_el_efecto_se_ve_en_el_preview(ventana, media):
    ventana.place_media(media["gris"])
    ventana.timeline.select(ventana.sequence.track_named("V1").clips[0])
    ventana._sync_panels(0.5)
    ventana._scrubbed(0.5)
    ventana.effects_panel.add_effect("negativo")
    ventana._settle_preview()
    color = ventana.preview.current_image().pixelColor(80, 60)
    assert color.red() == pytest.approx(127, abs=6)


# --- espacio de color del material -----------------------------------------------------------------

def test_el_panel_de_color_pone_el_espacio_de_entrada(ventana, media):
    clip = _con_clip(ventana, media)
    panel = ventana.color_panel
    panel.space.setCurrentIndex(panel.space.findData(SPACE_HLG))
    assert clip.color.input_space == SPACE_HLG
    assert not panel.ocio_space.isEnabled()
    panel.space.setCurrentIndex(panel.space.findData(SPACE_NONE))
    assert clip.color.input_space == SPACE_NONE


@pytest.mark.skipif(not __import__("vortex_studio.media.colorspace", fromlist=["x"]).has_ocio(),
                    reason="opencolorio no está instalado")
def test_con_ocio_se_elige_el_espacio_de_la_configuracion(ventana, media):
    clip = _con_clip(ventana, media)
    panel = ventana.color_panel
    panel.set_input_space(SPACE_OCIO)
    assert clip.color.ocio_space == "ACEScct" and panel.ocio_space.isEnabled()
    panel.ocio_space.setCurrentText("ACES2065-1")
    assert clip.color.ocio_space == "ACES2065-1"


def test_importar_un_video_hdr_lo_convierte_solo(ventana, tmp_path):
    if FFMPEG is None:
        pytest.skip("hace falta ffmpeg")
    ruta = tmp_path / "hdr.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x90:rate=30:duration=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p10le",
                    "-x264-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                    "-color_primaries", "bt2020",
                    "-color_trc", "smpte2084", "-colorspace", "bt2020nc", str(ruta)], check=True)
    ventana.place_media(ruta)
    assert ventana.sequence.track_named("V1").clips[0].color.input_space == SPACE_PQ
    assert "Rec.709" in ventana.statusBar().currentMessage()


# --- versiones, candado y fusión -------------------------------------------------------------------

def _guardado(ventana, media, tmp_path):
    _con_clip(ventana, media)
    ruta = save_project(ventana.project, tmp_path / "proyecto")
    ventana.adopt_project(load_project(ruta), ruta)
    return ruta


def test_guardar_version_necesita_proyecto_guardado(ventana, media, tmp_path):
    _con_clip(ventana, media)
    assert ventana.save_version("uno") is None
    assert "Guarda" in ventana.statusBar().currentMessage()
    ruta = _guardado(ventana, media, tmp_path)
    version = ventana.save_version("uno")
    assert version is not None and load_project(ruta).version_base == version.id


def test_volver_a_una_version(ventana, media, tmp_path):
    _guardado(ventana, media, tmp_path)
    version = ventana.save_version("antes")
    ventana.sequence.track_named("V1").clips[0].start = 5.0
    ventana._commit("Mover")
    assert ventana.restore_version(version)
    assert ventana.sequence.track_named("V1").clips[0].start == 0.0
    assert ventana._dirty and "antes" in ventana.statusBar().currentMessage()


def test_el_menu_de_versiones_las_lista(ventana, media, tmp_path):
    _guardado(ventana, media, tmp_path)
    ventana._fill_versions_menu()
    assert [a.text() for a in ventana._versions_menu.actions()] == ["No hay versiones guardadas"]
    ventana.save_version("primera")
    ventana._fill_versions_menu()
    assert ventana._versions_menu.actions()[0].text().startswith("primera")


def test_el_candado_avisa_si_otra_sesion_tiene_el_proyecto(ventana, media, tmp_path):
    ruta = _guardado(ventana, media, tmp_path)
    assert ventana.lock_holder is None
    assert ver.read_lock(ruta).session == ventana._session
    ver.release(ruta, ventana._session)
    ver.acquire(ruta, "otra-persona")
    ventana.adopt_project(load_project(ruta), ruta)
    assert ventana.lock_holder is not None
    assert "también tiene abierto" in ventana.statusBar().currentMessage()


def test_cerrar_suelta_el_candado(qapp, media, tmp_path):
    from vortex_studio.ui import MainWindow

    ventana = MainWindow()
    ruta = _guardado(ventana, media, tmp_path)
    assert ver.read_lock(ruta) is not None
    ventana._dirty = False
    ventana.close()
    qapp.processEvents()
    assert ver.read_lock(ruta) is None


def test_fusionar_con_la_copia_de_otro(ventana, media, tmp_path):
    ruta = _guardado(ventana, media, tmp_path)
    ventana.save_version("base")
    copia = tmp_path / "copia.vortex"
    shutil.copy(ruta, copia)
    otro = load_project(copia)
    otro.active.track_named("V1").clips[0].color.saturation = 160
    save_project(otro, copia)
    ventana.sequence.track_named("V1").clips[0].fade_in = 0.5
    ventana._commit("Fundido")
    assert ventana.merge_with(copia) == []
    clip = ventana.sequence.track_named("V1").clips[0]
    assert clip.fade_in == 0.5 and clip.color.saturation == 160


def test_fusionar_sin_version_en_comun_no_hace_nada(ventana, media, tmp_path):
    ruta = _guardado(ventana, media, tmp_path)
    ajena = save_project(load_project(ruta), tmp_path / "ajena")
    assert ventana.merge_with(ajena) is None
    assert "versión guardada" in ventana.statusBar().currentMessage()


def test_fusionar_con_conflicto_reporta_y_gana_lo_tuyo(ventana, media, tmp_path):
    ruta = _guardado(ventana, media, tmp_path)
    ventana.save_version("base")
    copia = tmp_path / "copia.vortex"
    shutil.copy(ruta, copia)
    otro = load_project(copia)
    otro.active.track_named("V1").clips[0].color.exposure = -50
    save_project(otro, copia)
    ventana.sequence.track_named("V1").clips[0].color.exposure = 70
    ventana._commit("Exposición")
    conflictos = ventana.merge_with(copia)
    assert len(conflictos) == 1 and "exposure" in conflictos[0]
    assert ventana.sequence.track_named("V1").clips[0].color.exposure == 70
    assert "conflicto" in ventana.statusBar().currentMessage()


# --- exportar la edición y render en paralelo -----------------------------------------------------------

def test_exportar_la_edicion_en_los_tres_formatos(ventana, media, tmp_path):
    _con_clip(ventana, media)
    for extension in (".edl", ".xml"):
        ruta = ventana.export_edit(tmp_path / f"edicion{extension}")
        assert ruta.exists() and ruta.stat().st_size > 50
    pytest.importorskip("aaf2")
    assert ventana.export_edit(tmp_path / "edicion.aaf").exists()


def test_exportar_edicion_vacia_o_con_extension_rara(ventana, media, tmp_path):
    assert ventana.export_edit(tmp_path / "vacia.xml") is None
    _con_clip(ventana, media)
    assert ventana.export_edit(tmp_path / "rara.mov") is None
    assert "No se pudo" in ventana.statusBar().currentMessage()


def test_el_dialogo_de_exportar_ofrece_render_en_paralelo(ventana, media):
    from vortex_studio.ui.main_window import ExportDialog

    _con_clip(ventana, media)
    dialogo = ExportDialog(ventana, 0.0, 2.0, ventana.sequence)
    assert not dialogo.parallel()
    dialogo._parallel.setChecked(True)
    assert dialogo.parallel()
    solo_audio = next(i for i in range(dialogo._preset.count())
                      if "audio" in dialogo._preset.itemText(i).lower())
    dialogo._preset.setCurrentIndex(solo_audio)
    assert not dialogo.parallel()


def test_la_exportacion_en_paralelo_desde_la_ventana(ventana, media, tmp_path):
    import av

    _con_clip(ventana, media)
    trabajo = ventana.queue_export(tmp_path / "paralelo.mp4", 0.0, 2.0, parallel=True)
    assert trabajo.parallel
    assert ventana.render_queue.wait(120)
    with av.open(str(trabajo.path)) as contenedor:
        assert sum(1 for _ in contenedor.decode(video=0)) == 60
