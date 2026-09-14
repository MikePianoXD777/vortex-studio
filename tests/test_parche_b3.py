"""Lo que salió en el QA a mano de la 0.1.0b2 y se arregló en la 0.1.0b3.

Cada bloque dice la fila de la hoja de QA de donde salió.
"""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDropEvent, QImage
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from vortex_studio.model import Clip
from vortex_studio.model.project import NestedClip

FFMPEG = shutil.which("ffmpeg")


def _video(ventana):
    return [c for c in ventana.sequence.video_tracks()[-1].clips]


def _audio(ventana):
    return [c for c in ventana.sequence.audio_tracks()[0].clips]


def _accion(ventana, texto):
    return next(a for a in ventana.findChildren(QAction) if a.text() == texto)


def _ffmpeg(*args):
    if FFMPEG is None:
        pytest.skip("Hace falta ffmpeg")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


# --- MAR-05 / MAR-09: marcadores desde el menú ---------------------------------------

def test_poner_marcador_desde_el_menu_no_lo_llama_false(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    _accion(ventana, "Poner &marcador").trigger()
    assert ventana.sequence.markers[0].name == ""


def test_marcador_en_el_clip_desde_el_menu_no_lo_llama_false(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(_video(ventana)[0])
    ventana._seek(1.0)
    _accion(ventana, "Marcador en el &clip").trigger()
    assert _video(ventana)[0].markers[0].name == ""


def test_editar_un_marcador_puesto_con_m_abre_su_dialogo(ventana, media, monkeypatch):
    import vortex_studio.ui.main_window as ventana_mod

    abiertos = []

    class Dialogo:
        def __init__(self, parent, marker, owner=""):
            abiertos.append(marker)

        def exec(self):
            return 0

    monkeypatch.setattr(ventana_mod, "MarkerDialog", Dialogo)
    ventana._place_video(media["mudo"])
    ventana._seek(1.0)
    _accion(ventana, "Poner &marcador").trigger()
    _accion(ventana, "&Editar marcador…").trigger()
    assert abiertos and abiertos[0].name == ""


def test_un_marcador_guardado_con_false_se_puede_editar(ventana, monkeypatch):
    import vortex_studio.ui.main_window as ventana_mod
    from vortex_studio.model.project import Marker

    vistos = []

    class Dialogo:
        DELETE = 2

        def __init__(self, parent, marker, owner=""):
            vistos.append(marker.name)

        def exec(self):
            return 0

    monkeypatch.setattr(ventana_mod, "MarkerDialog", Dialogo)
    ventana.edit_marker(Marker(time=1.0, name=False))
    assert vistos == [""]


# --- PRO-10: guardar versión ---------------------------------------------------------

def test_guardar_version_pide_el_nombre_y_guarda(ventana, media, tmp_path, monkeypatch):
    ventana._place_video(media["mudo"])
    ventana._path = tmp_path / "proyecto.vortex"
    ventana.save()
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Primer corte", True)))
    version = ventana.save_version()
    assert version is not None and version.label == "Primer corte"


def test_guardar_version_cancelada_no_guarda(ventana, media, tmp_path, monkeypatch):
    ventana._place_video(media["mudo"])
    ventana._path = tmp_path / "proyecto.vortex"
    ventana.save()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    assert ventana.save_version() is None


def test_guardar_version_desde_el_menu_no_truena(ventana, media, tmp_path, monkeypatch):
    ventana._place_video(media["mudo"])
    ventana._path = tmp_path / "proyecto.vortex"
    ventana.save()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Menú", True)))
    accion = next(a for a in ventana.findChildren(QAction) if "versión" in a.text().lower()
                  and "guardar" in a.text().lower())
    accion.trigger()
    assert "Menú" in ventana.statusBar().currentMessage()


# --- EXP-02: exportar a 29.97 ---------------------------------------------------------

def test_los_fps_de_ntsc_quedan_exactos():
    from fractions import Fraction

    from vortex_studio.media.encoder import frame_rate

    assert frame_rate(30000 / 1001) == Fraction(30000, 1001)
    assert frame_rate(29.97) == Fraction(30000, 1001)
    assert frame_rate(23.976) == Fraction(24000, 1001)
    assert frame_rate(59.94) == Fraction(60000, 1001)


def test_los_fps_enteros_siguen_enteros():
    from vortex_studio.media.encoder import frame_rate

    for fps in (24, 25, 30, 50, 60):
        assert frame_rate(fps) == fps
    assert frame_rate(0) == 30


def test_exportar_a_29_97_sale_a_29_97_y_dura_lo_que_debe(tmp_path):
    import av

    from vortex_studio.media.encoder import export_video

    imagen = QImage(64, 36, QImage.Format_RGB888)
    imagen.fill(QColor("#336699"))
    destino = export_video(tmp_path / "ntsc.mp4", iter([imagen] * 60), 60, 64, 36, 30000 / 1001)
    with av.open(str(destino)) as archivo:
        flujo = archivo.streams.video[0]
        assert flujo.average_rate == 30000 / 1001 or float(flujo.average_rate) == pytest.approx(29.97, abs=0.01)
        cuadros = sum(1 for _ in archivo.decode(flujo))
    assert cuadros == 60


# --- TL-06: ajustar timeline -----------------------------------------------------------

@pytest.mark.parametrize("ancho", [900, 1200, 1600])
def test_ajustar_timeline_deja_ver_el_final(ventana, media, ancho):
    ventana._place_video(media["mudo"])
    ventana.resize(ancho, 700)
    QApplication.processEvents()
    ventana._fit_zoom()
    final = ventana.timeline.x_for(ventana.sequence.duration)
    assert final <= ventana.timeline.width()
    assert final >= ventana.timeline.width() - 60      # y sin desperdiciar media pantalla


# --- MON-11: volumen al arrancar ---------------------------------------------------------

def test_el_volumen_arranca_como_dice_el_deslizador(ventana):
    assert ventana.audio._volume == pytest.approx(ventana.transport.volume())
    assert ventana.audio._volume == pytest.approx(0.8)


def test_mover_el_volumen_sigue_llegando(ventana):
    ventana.transport._volume.setValue(30)
    assert ventana.audio._volume == pytest.approx(0.3)


def test_silenciar_sigue_apagando(ventana):
    ventana.transport._mute.setChecked(True)
    assert ventana.audio._volume == 0.0
    ventana.transport._mute.setChecked(False)
    assert ventana.audio._volume == pytest.approx(0.8)


# --- CLI-09 / CLI-10: modo de audio desde el panel ----------------------------------------

def _con_video_seleccionado(ventana, media):
    ventana._place_video(media["sonoro"])
    video = _video(ventana)[0]
    ventana.timeline.select(video)
    ventana._sync_panels(1.0)
    return video, _audio(ventana)[0]


def test_silenciar_desde_el_panel_calla_el_audio_enlazado(ventana, media):
    video, audio = _con_video_seleccionado(ventana, media)
    ventana.clip_panel._mute_audio.setChecked(True)
    assert video.audio_mode == audio.audio_mode == "Silenciar"


def test_cambiar_tono_desde_el_panel_llega_al_audio_enlazado(ventana, media):
    video, audio = _con_video_seleccionado(ventana, media)
    ventana.clip_panel._audio_mode.setCurrentText("Cambiar tono")
    assert audio.audio_mode == "Cambiar tono"


def test_el_modo_de_audio_del_panel_se_puede_deshacer(ventana, media):
    video, audio = _con_video_seleccionado(ventana, media)
    ventana.clip_panel._audio_mode.setCurrentText("Cambiar tono")
    ventana.undo()
    audio = _audio(ventana)[0]
    assert audio.audio_mode == "Mantener tono"


# --- SEC-02: ajustar al primer clip --------------------------------------------------------

@pytest.fixture
def a_25(tmp_path):
    ruta = tmp_path / "pal.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=352x288:rate=25:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ruta))
    return ruta


def test_ajustar_al_primer_clip_toma_los_fps(ventana, a_25):
    ventana._place_video(a_25)
    ventana.sequence.fps = 60.0
    ventana.format_from_clip()
    assert ventana.sequence.fps == pytest.approx(25.0)


def test_ajustar_al_primer_clip_toma_el_tamano(ventana, a_25):
    ventana._place_video(a_25)
    ventana.set_format(1920, 1080)
    ventana.format_from_clip()
    assert (ventana.sequence.width, ventana.sequence.height) == (352, 288)


def test_ajustar_sin_clips_no_cambia_nada(ventana):
    antes = (ventana.sequence.width, ventana.sequence.height, ventana.sequence.fps)
    ventana.format_from_clip()
    assert (ventana.sequence.width, ventana.sequence.height, ventana.sequence.fps) == antes


# --- SEC-09: pegar una anidada dentro de sí misma --------------------------------------------

def _anidada(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.select(_video(ventana)[0])
    ventana.nest_selection()
    return next(c for t in ventana.sequence.tracks for c in t.clips if isinstance(c, NestedClip))


def _hay_anidada(ventana):
    return any(isinstance(c, NestedClip) for t in ventana.sequence.tracks for c in t.clips)


def test_pegar_la_anidada_dentro_de_si_misma_no_se_deja(ventana, media):
    anidada = _anidada(ventana, media)
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    ventana.open_nested(anidada)
    ventana.paste()
    assert not _hay_anidada(ventana)
    assert "dentro de sí misma" in ventana.statusBar().currentMessage()


def test_pegar_la_anidada_en_otra_secuencia_si_se_deja(ventana, media):
    anidada = _anidada(ventana, media)
    ventana.timeline.select(anidada)
    ventana.copy_selected()
    ventana.new_sequence()
    ventana.paste()
    assert _hay_anidada(ventana)


def test_pegar_un_clip_normal_dentro_de_la_anidada_si_se_deja(ventana, media):
    anidada = _anidada(ventana, media)
    ventana.open_nested(anidada)
    ventana.timeline.select(_video(ventana)[0])
    ventana.copy_selected()
    antes = len(_video(ventana))
    ventana._seek(ventana.sequence.duration)
    ventana.paste()
    assert len(_video(ventana)) == antes + 1


# --- CLP-27: congelar cuadro sin comerse el resto ----------------------------------------------

def test_congelar_conserva_todo_el_material(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(2.0)
    ventana.freeze_frame()
    antes, congelado, resto = _video(ventana)
    assert antes.duration + resto.duration == pytest.approx(6.0)
    assert ventana.sequence.duration == pytest.approx(8.0)


def test_congelar_corre_tambien_el_audio_enlazado(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana._seek(2.0)
    ventana.freeze_frame()
    piezas = _audio(ventana)
    assert [round(c.start, 3) for c in piezas] == [0.0, 4.0]
    assert piezas[1].source_time(4.0) == pytest.approx(2.0)
    # Video y audio siguen alineados después del congelado.
    assert _video(ventana)[2].start == pytest.approx(piezas[1].start)


def test_congelar_se_deshace_de_un_jalon(ventana, media):
    ventana._place_video(media["sonoro"])
    ventana._seek(2.0)
    ventana.freeze_frame()
    ventana.undo()
    assert len(_video(ventana)) == 1 and len(_audio(ventana)) == 1
    assert ventana.sequence.duration == pytest.approx(6.0)


# --- CLP-10 / EFE-04: el cuadro que se ve --------------------------------------------------------

def test_entre_dos_cuadros_se_ve_el_que_empezo(media):
    from vortex_studio.media import VideoSource

    with VideoSource(media["mudo"]) as a, VideoSource(media["mudo"]) as b:
        assert a.frame_at(1.5 / 30 + 1.0).data == b.frame_at(1.0 + 1 / 30).data


def test_justo_antes_del_siguiente_cuadro_sigue_el_mismo(media):
    from vortex_studio.media import VideoSource

    with VideoSource(media["mudo"]) as a, VideoSource(media["mudo"]) as b:
        assert a.frame_at(1.0 + 2 / 30 - 0.002).data == b.frame_at(1.0 + 1 / 30).data
        assert a.frame_at(1.0 + 2 / 30).data != b.frame_at(1.0 + 1 / 30).data


def test_ir_y_venir_entre_cuadros_da_lo_mismo_que_decodificar_limpio(media):
    from vortex_studio.media import VideoSource

    instantes = [2.0, 2.051, 2.017, 2.3, 1.95, 2.301, 2.299]
    with VideoSource(media["mudo"]) as fuente:
        for t in instantes:
            with VideoSource(media["mudo"]) as limpia:
                assert fuente.frame_at(t).data == limpia.frame_at(t).data, t


# --- TXT-07: posición del texto en las orillas ---------------------------------------------------

@pytest.mark.parametrize("posicion, alineacion", [
    ("Arriba izquierda", "izquierda"), ("Centro derecha", "derecha"),
    ("Abajo izquierda", "izquierda"), ("Subtítulo", "centro"), ("Centro", "centro"),
])
def test_la_posicion_alinea_hacia_su_orilla(ventana, posicion, alineacion):
    ventana.add_title()
    titulo = ventana.text_panel._title
    ventana.text_panel._anchor.setCurrentText(posicion)
    assert titulo.align == alineacion


def test_el_texto_en_la_orilla_no_se_sale_del_cuadro(ventana):
    from vortex_studio.ui.compositor import ALIGN_OFFSET

    ventana.add_title()
    titulo = ventana.text_panel._title
    ventana.text_panel._anchor.setCurrentText("Arriba derecha")
    # Alineado a la derecha, el bloque termina en el ancla (94 %), no la rebasa.
    assert ALIGN_OFFSET[titulo.align] == 1.0 and titulo.x < 1.0


def test_la_alineacion_se_puede_cambiar_despues_a_mano(ventana):
    ventana.add_title()
    titulo = ventana.text_panel._title
    ventana.text_panel._anchor.setCurrentText("Arriba izquierda")
    ventana.text_panel._align.setCurrentText("centro")
    assert titulo.align == "centro"


# --- IMG-05: llenar el cuadro -------------------------------------------------------------------

@pytest.fixture
def foto_ancha(tmp_path):
    ruta = tmp_path / "ancha.png"
    imagen = QImage(320, 180, QImage.Format_RGB888)
    imagen.fill(QColor("#aa3355"))
    imagen.save(str(ruta))
    return ruta


def _llenar(ventana, ruta, ancho, alto):
    ventana.set_format(ancho, alto)
    ventana._place_image(Path(ruta))
    overlay = ventana.image_panel._overlay
    ventana.image_panel._cover()
    return overlay


def test_llenar_con_foto_ancha_en_secuencia_vertical_cubre_el_alto(ventana, foto_ancha):
    overlay = _llenar(ventana, foto_ancha, 1080, 1920)
    alto = overlay.scale * 1080 * (180 / 320)
    assert alto >= 1920 - 5


def test_llenar_con_foto_ancha_en_secuencia_horizontal_queda_al_ancho(ventana, foto_ancha):
    overlay = _llenar(ventana, foto_ancha, 1920, 1080)
    assert overlay.scale == pytest.approx(1.0)


def test_llenar_con_logo_cuadrado_en_vertical_cubre_el_alto(ventana, media):
    overlay = _llenar(ventana, media["logo"], 1080, 1920)
    assert overlay.scale * 1080 >= 1920 - 5


# --- EFE-09: efecto propio mal escrito -----------------------------------------------------------

@pytest.fixture
def carpeta_plugins(tmp_path, monkeypatch, ventana):
    monkeypatch.setenv("VORTEX_CONFIG_DIR", str(tmp_path))
    from vortex_studio.model import plugins

    carpeta = plugins.plugins_dir()
    carpeta.mkdir(parents=True, exist_ok=True)
    yield carpeta
    monkeypatch.undo()
    ventana.effects_panel.reload_plugins()


def test_un_efecto_roto_se_avisa_en_el_panel(ventana, carpeta_plugins):
    (carpeta_plugins / "Roto.json").write_text("{ esto no es json", encoding="utf-8")
    ventana.effects_panel.reload_plugins()
    etiqueta = ventana.effects_panel.plugin_warning_label
    assert not etiqueta.isHidden()
    assert "Roto.json" in etiqueta.text()


def test_sin_efectos_rotos_no_hay_aviso(ventana, carpeta_plugins):
    ventana.effects_panel.reload_plugins()
    assert ventana.effects_panel.plugin_warning_label.isHidden()


def test_arreglar_el_efecto_quita_el_aviso(ventana, carpeta_plugins):
    roto = carpeta_plugins / "Roto.json"
    roto.write_text("{", encoding="utf-8")
    ventana.effects_panel.reload_plugins()
    roto.unlink()
    ventana.effects_panel.reload_plugins()
    assert ventana.effects_panel.plugin_warning_label.isHidden()


# --- MED-20: archivos faltantes ---------------------------------------------------------------------

@pytest.fixture
def proyecto_movido(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project

    origen = tmp_path / "antes"
    origen.mkdir()
    clip = origen / "toma.mp4"
    shutil.copy(media["mudo"], clip)
    ventana._place_video(clip)
    ventana._path = tmp_path / "proyecto.vortex"
    ventana.save()

    nueva = tmp_path / "despues" / "sub"
    nueva.mkdir(parents=True)
    shutil.move(str(clip), nueva / "toma.mp4")
    ruta = ventana._path
    ventana.adopt_project(load_project(ruta), ruta)
    QApplication.processEvents()
    return clip, nueva / "toma.mp4"


def test_al_abrir_se_marcan_los_clips_que_faltan(ventana, proyecto_movido):
    viejo, _ = proyecto_movido
    assert str(viejo) in ventana.timeline.missing


def test_al_abrir_sale_un_aviso_que_no_detiene_nada(ventana, proyecto_movido):
    avisos = [m for m in ventana.findChildren(QMessageBox) if m.isVisible()]
    assert avisos and "Faltan" in avisos[0].windowTitle()
    assert not avisos[0].isModal() or avisos[0].windowModality() != Qt.ApplicationModal


def test_buscar_en_una_carpeta_los_vuelve_a_enlazar(ventana, proyecto_movido, tmp_path):
    _, nuevo = proyecto_movido
    assert ventana.relink_media(tmp_path / "despues") == 1
    assert Path(_video(ventana)[0].source) == nuevo
    assert not ventana.timeline.missing
    assert "1 de 1" in ventana.statusBar().currentMessage()


def test_buscar_donde_no_estan_no_cambia_nada(ventana, proyecto_movido, tmp_path):
    viejo, _ = proyecto_movido
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    assert ventana.relink_media(vacia) == 0
    assert str(viejo) in ventana.timeline.missing


# --- TL-25: soltar desde el gestor de archivos ----------------------------------------------------------

def test_un_archivo_del_gestor_se_reconoce(media):
    from vortex_studio.ui.timeline import TimelineWidget

    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(media["mudo"]))])
    assert TimelineWidget._dropped_paths(datos) == [Path(media["mudo"])]


def test_una_url_de_internet_o_un_archivo_que_no_existe_no_se_aceptan(tmp_path):
    from vortex_studio.ui.timeline import TimelineWidget

    datos = QMimeData()
    datos.setUrls([QUrl("https://example.com/video.mp4"),
                   QUrl.fromLocalFile(str(tmp_path / "no-existe.mp4"))])
    assert TimelineWidget._dropped_paths(datos) == []


def test_soltar_un_archivo_del_gestor_lo_pone_en_el_timeline(ventana, media):
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(media["mudo"]))])
    evento = QDropEvent(QPointF(400, 60), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
    ventana.timeline.dropEvent(evento)
    assert any(isinstance(c, Clip) for t in ventana.sequence.tracks for c in t.clips)


# --- MON-12: archivo incompleto -----------------------------------------------------------------------------

def test_moov_atom_se_explica(ventana):
    from vortex_studio.ui.main_window import open_error_text

    assert "incompleto" in open_error_text("moov atom not found")
    assert "incompleto" in open_error_text("[Errno 1094995529] Invalid data found when processing input")


def test_otros_errores_pasan_tal_cual():
    from vortex_studio.ui.main_window import open_error_text

    assert open_error_text("Permission denied") == "Permission denied"


def test_un_mp4_cortado_avisa_que_parece_incompleto(ventana, media, tmp_path):
    cortado = tmp_path / "cortado.mp4"
    cortado.write_bytes(Path(media["sonoro"]).read_bytes()[:4096])
    ventana.place_media(cortado)
    assert "incompleto" in ventana.statusBar().currentMessage()


# --- VER-03: proxies de lo que se importa después -----------------------------------------------------------

def test_con_proxies_prendidos_lo_importado_usa_su_proxy(ventana, media, monkeypatch, tmp_path):
    import vortex_studio.ui.main_window as ventana_mod

    falso = tmp_path / "proxy.mp4"
    monkeypatch.setattr(ventana_mod, "existing_proxy", lambda ruta: falso)
    ventana.use_proxies = True
    ventana._place_video(media["mudo"])
    assert ventana._proxy_paths.get(Path(media["mudo"])) == falso


def test_sin_proxies_prendidos_no_se_buscan(ventana, media, monkeypatch, tmp_path):
    import vortex_studio.ui.main_window as ventana_mod

    monkeypatch.setattr(ventana_mod, "existing_proxy", lambda ruta: tmp_path / "proxy.mp4")
    ventana.use_proxies = False
    ventana._place_video(media["mudo"])
    assert Path(media["mudo"]) not in ventana._proxy_paths


def test_el_preview_lee_del_proxy_de_lo_importado(ventana, media, monkeypatch, tmp_path):
    import vortex_studio.ui.main_window as ventana_mod

    falso = tmp_path / "proxy.mp4"
    monkeypatch.setattr(ventana_mod, "existing_proxy", lambda ruta: falso)
    ventana.use_proxies = True
    ventana._place_video(media["mudo"])
    assert ventana._preview_path(_video(ventana)[0]) == falso


# --- SEC-10: la multicámara se pinta como anidada ----------------------------------------------------------------

def test_multicamara_se_pinta_como_anidada():
    from vortex_studio.model.multicam import MulticamClip
    from vortex_studio.ui.timeline import CLIP_NESTED, _color_for

    pista = SimpleNamespace(kind="video")
    assert _color_for(pista, object.__new__(MulticamClip)) == CLIP_NESTED


def test_anidada_sigue_pintandose_igual():
    from vortex_studio.ui.timeline import CLIP_NESTED, _color_for

    assert _color_for(SimpleNamespace(kind="video"), object.__new__(NestedClip)) == CLIP_NESTED


def test_un_clip_normal_no_se_pinta_como_anidada():
    from vortex_studio.ui.timeline import CLIP_NESTED, _color_for

    assert _color_for(SimpleNamespace(kind="video"), Clip("a.mp4", 0.0, 1.0)) != CLIP_NESTED


# --- AUD-02: normalizar dice la verdad ------------------------------------------------------------------------------

@pytest.fixture
def bajito(tmp_path):
    ruta = tmp_path / "bajito.wav"
    # Unos −51 LUFS: se alcanza a medir, pero llegar a −14 pide más que el
    # tope de ganancia.
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3,volume=-30dB", "-ac", "2", str(ruta))
    return ruta


def test_normalizar_material_muy_bajo_avisa_que_no_llega(ventana, bajito):
    ventana._place_audio(bajito)
    ventana.normalize_loudness(-14.0)
    assert "no llega" in ventana.statusBar().currentMessage()


def test_normalizar_material_normal_no_avisa_de_mas(ventana, media):
    ventana._place_audio(media["tono"])
    ventana.normalize_loudness(-14.0)
    mensaje = ventana.statusBar().currentMessage()
    assert "LUFS" in mensaje and "no llega" not in mensaje


def test_normalizar_material_bajo_igual_sube_lo_que_puede(ventana, bajito):
    ventana._place_audio(bajito)
    ventana.normalize_loudness(-14.0)
    assert _audio(ventana)[0].gain > 1.0
