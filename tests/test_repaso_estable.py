"""Lo que salió del repaso a fondo antes de la 0.1.0 estable.

Cinco revisiones simultáneas —modelo, media, ventana, paneles y empaque—
sobre la 0.1.0b3. Aquí queda cada falla con su prueba.
"""

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from vortex_studio.model import Clip, Sequence


def _video(ventana):
    return ventana.sequence.video_tracks()[-1].clips


def _audio(ventana):
    return ventana.sequence.audio_tracks()[0].clips


def _evento(tipo, x, y, boton=Qt.LeftButton):
    return QMouseEvent(tipo, QPointF(x, y), Qt.LeftButton, boton, Qt.NoModifier)


# --- exportar no destruye archivos -------------------------------------------------

def test_cancelar_una_exportacion_no_borra_el_archivo_que_ya_estaba(tmp_path, media):
    from vortex_studio.media.encoder import Cancelled, export_video
    from vortex_studio.ui.imagenes import load_image

    destino = tmp_path / "entrega.mp4"
    destino.write_bytes(b"la entrega de ayer")

    imagen = load_image(media["logo"])
    with pytest.raises(Cancelled):
        export_video(destino, iter([imagen] * 30), 30, 64, 64, 30, "Borrador",
                     progress=lambda hechos, total: hechos < 3)

    assert destino.read_bytes() == b"la entrega de ayer"
    assert not list(tmp_path.glob("*.parte.mp4"))


def test_una_exportacion_que_truena_no_deja_el_archivo_a_medias(tmp_path):
    from vortex_studio.media.encoder import export_video

    destino = tmp_path / "salida.mp4"

    def cuadros():
        raise RuntimeError("se acabó la luz")
        yield

    with pytest.raises(RuntimeError):
        export_video(destino, cuadros(), 10, 64, 64, 30, "Borrador")
    assert not destino.exists()
    assert not list(tmp_path.glob("*.parte*"))


def test_no_deja_exportar_encima_del_material_del_proyecto(ventana, media, tmp_path,
                                                           monkeypatch):
    copia = tmp_path / "toma.mp4"
    shutil.copy(media["mudo"], copia)
    ventana._place_video(copia)
    assert ventana._media_in_use(copia)
    assert not ventana._media_in_use(tmp_path / "otro.mp4")


def test_el_nombre_con_puntos_conserva_su_extension():
    from vortex_studio.ui.main_window import _con_extension

    assert _con_extension(Path("corte final v1.2"), ".mp4") == Path("corte final v1.2.mp4")
    assert _con_extension(Path("corte.mp4"), ".mp4") == Path("corte.mp4")
    assert _con_extension(Path("corte.MP4"), ".mp4") == Path("corte.MP4")


def test_guardar_un_proyecto_con_puntos_en_el_nombre(tmp_path, ventana, media):
    from vortex_studio.model.serialize import save_project

    ventana._place_video(media["mudo"])
    destino = save_project(ventana.project, tmp_path / "Entrevista v1.2")
    assert destino.name == "Entrevista v1.2.vortex"
    otro = save_project(ventana.project, tmp_path / "Entrevista v1.3")
    assert otro.name == "Entrevista v1.3.vortex" and destino.exists()


# --- versiones y guardar ------------------------------------------------------------

def test_volver_a_una_version_pregunta_antes_de_tirar_lo_no_guardado(ventana, media,
                                                                     tmp_path, monkeypatch):
    from vortex_studio.model import versions

    ventana._place_video(media["mudo"])
    ventana._path = tmp_path / "proyecto.vortex"
    ventana.save()
    version = versions.save_version(ventana.project, ventana._path, "primera")

    ventana._place_video(media["gris"])
    antes = len(_video(ventana))
    monkeypatch.setattr(ventana, "_confirm_discard", lambda: False)
    assert ventana.restore_version(version) is False
    assert len(_video(ventana)) == antes


def test_un_guardar_como_que_falla_no_mueve_el_proyecto(ventana, media, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    ventana._place_video(media["mudo"])
    bueno = tmp_path / "bueno.vortex"
    ventana._path = bueno
    ventana.save()

    imposible = tmp_path / "no-existe" / "malo.vortex"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(imposible), "")))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    assert ventana.save_as() is False
    assert ventana._path == bueno


def test_decir_que_no_a_recuperar_conserva_la_copia(ventana, media, monkeypatch):
    from vortex_studio.model import autosave

    ventana._place_video(media["mudo"])
    copia = ventana.autosave()
    assert copia is not None and Path(copia).exists()
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    otra = type(ventana)()
    try:
        assert otra.offer_recovery() is False
        assert Path(copia).exists()
    finally:
        otra._dirty = False
        otra.close()
    autosave.discard(Path(copia))


# --- edición que no pisa lo de junto -------------------------------------------------

def test_duplicar_recorre_lo_que_sigue(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(6.0)
    ventana._place_video(media["gris"])
    v = _video(ventana)
    assert len(v) == 2
    ventana.timeline.select(v[0])
    ventana.duplicate_selected()

    inicios = [round(c.start, 2) for c in _video(ventana)]
    assert len(inicios) == 3
    assert inicios == sorted(inicios)
    assert len(_video(ventana)) == 3


def test_duplicar_se_deshace_completo(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(6.0)
    ventana._place_video(media["gris"])
    antes = [(round(c.start, 3), round(c.duration, 3)) for c in _video(ventana)]
    ventana.timeline.select(_video(ventana)[0])
    ventana.duplicate_selected()
    ventana.undo()
    assert [(round(c.start, 3), round(c.duration, 3)) for c in _video(ventana)] == antes


def test_importar_un_video_no_pisa_la_musica(ventana, media):
    ventana._place_audio(media["tono"])
    musica = _audio(ventana)[0]
    musica.duration = 60.0
    ventana._place_video(media["sonoro"])

    assert musica.start == pytest.approx(0.0) and musica.duration == pytest.approx(60.0)
    sonidos = [c for pista in ventana.sequence.audio_tracks() for c in pista.clips]
    assert len(sonidos) == 2


def test_soltar_en_una_pista_bloqueada_avisa_y_no_toca_nada(ventana, media):
    ventana._place_video(media["mudo"])
    pistas = ventana.sequence.video_tracks()
    arriba = pistas[0]
    arriba.locked = True
    indice = ventana.sequence.tracks.index(arriba)
    antes = [(c.start, c.duration) for c in _video(ventana)]

    ventana.place_media(media["gris"], at=2.0, track_index=indice)

    assert not arriba.clips
    assert [(c.start, c.duration) for c in _video(ventana)] == antes
    assert "bloqueada" in ventana.statusBar().currentMessage()


# --- el candado protege de verdad ----------------------------------------------------

def test_una_pista_bloqueada_apaga_los_paneles(ventana, media):
    ventana._place_video(media["mudo"])
    clip = _video(ventana)[0]
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    assert ventana.transform_panel._clip is clip

    ventana.sequence.track_of(clip).locked = True
    ventana._sync_panels(1.0)
    assert ventana.transform_panel._clip is None


def test_no_se_puede_borrar_un_texto_de_una_pista_bloqueada(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo = ventana.timeline.selected
    ventana.sequence.track_of(titulo).locked = True
    ventana.delete_title(titulo)
    assert any(titulo in pista.clips for pista in ventana.sequence.text_tracks())


def test_borrar_la_seleccion_limpia_los_paneles(ventana, media):
    ventana._place_video(media["mudo"])
    clip = _video(ventana)[0]
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)
    ventana.delete_selected()
    assert ventana.transform_panel._clip is not clip


# --- congelar, anidar y marcas -------------------------------------------------------

def test_congelar_cuadro_respeta_la_seleccion(ventana, media):
    ventana._place_video(media["mudo"])            # va a V1
    abajo = _video(ventana)[0]
    arriba = ventana.sequence.video_tracks()[0]
    encima = Clip(source=media["gris"], start=0.0, duration=2.0, name="encima")
    arriba.add(encima)
    ventana.timeline.select(abajo)
    ventana._seek(1.0)
    ventana.freeze_frame()

    assert len(arriba.clips) == 1                  # el de arriba ni se entera
    assert len(_video(ventana)) == 3


def test_anidar_no_cae_en_una_pista_de_video_bloqueada(ventana, media):
    ventana._place_audio(media["tono"])
    for pista in ventana.sequence.video_tracks():
        pista.locked = True
    ventana.timeline.select(_audio(ventana)[0])
    assert ventana.nest_selection() is None
    assert "bloqueadas" in ventana.statusBar().currentMessage()


def test_las_marcas_no_viajan_a_otra_secuencia(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.timeline.mark_in, ventana.timeline.mark_out = 1.0, 4.0
    ventana.new_sequence()
    assert ventana.timeline.mark_in is None and ventana.timeline.mark_out is None
    assert ventana._range() == (0.0, ventana.sequence.duration)


def test_cada_secuencia_conserva_su_deshacer(ventana, media):
    ventana._place_video(media["mudo"])
    primera = ventana.sequence.id
    assert ventana.history.can_undo
    otra = ventana.new_sequence()
    assert not ventana.history.can_undo          # la nueva empieza limpia
    ventana.switch_sequence(primera)
    assert ventana.history.can_undo              # la de antes conserva lo suyo
    ventana.switch_sequence(otra.id)
    assert not ventana.history.can_undo


# --- modelo --------------------------------------------------------------------------

def test_cambiar_la_velocidad_de_un_congelado_no_lo_desaparece():
    clip = Clip("a.mp4", 0.0, 2.0, speed=0.0)
    clip.retime(2.0)
    assert clip.duration == pytest.approx(2.0) and clip.speed == pytest.approx(2.0)


def test_una_transicion_a_negro_detras_de_una_imagen_no_truena(ventana, media):
    from vortex_studio.model.project import DIP_BLACK
    from vortex_studio.model.overlays import ImageOverlay

    pista = ventana.sequence.video_tracks()[-1]
    imagen = ImageOverlay(start=0.0, duration=2.0, source=media["logo"])
    pista.add(imagen)
    clip = Clip(source=media["mudo"], start=2.0, duration=2.0, dissolve=1.0,
                transition=DIP_BLACK)
    pista.add(clip)
    # Antes tronaba al componer cada cuadro del cruce.
    assert ventana.sequence.covers(imagen, 2.5) in (True, False)
    ventana._seek(2.5)


def test_estirar_la_cabeza_se_detiene_en_el_primer_cuadro():
    from vortex_studio.model.commands import trim_head

    clip = Clip("a.mp4", 5.0, 4.0, in_point=1.0)
    trim_head(clip, -3.0)          # se pide estirar 3 s con solo 1 s de material
    assert clip.in_point == pytest.approx(0.0)
    assert clip.start == pytest.approx(4.0) and clip.duration == pytest.approx(5.0)


def test_quitar_un_keyframe_no_se_lleva_a_los_vecinos():
    from vortex_studio.model import keyframes as kf

    puntos = [[0.0, 0.0, kf.LINEAR], [1 / 60, 1.0, kf.LINEAR], [2 / 60, 2.0, kf.LINEAR],
              [3 / 60, 3.0, kf.LINEAR]]
    quedan = kf.remove_key(puntos, 1 / 60)
    assert len(quedan) == 3
    assert [round(kf.time_of(k), 4) for k in quedan] == [0.0, round(2 / 60, 4),
                                                         round(3 / 60, 4)]


def test_pegar_la_velocidad_sobre_un_clip_con_remapeo(ventana):
    from vortex_studio.model import timeremap
    from vortex_studio.model.commands import paste_attributes

    origen = Clip("a.mp4", 0.0, 4.0, speed=2.0)
    destino = Clip("b.mp4", 0.0, 4.0)
    timeremap.set_speed_from(destino, 1.0, 0.5)
    assert timeremap.is_remapped(destino)

    paste_attributes(origen, destino, ("Velocidad",))
    assert not timeremap.is_remapped(destino)
    assert destino.speed == pytest.approx(2.0)


def test_el_codigo_de_tiempo_del_edl_cuadra_con_el_del_editor():
    from vortex_studio.model.interchange import tc
    from vortex_studio.model.project import timecode

    for segundos in (10.0, 60.0, 600.0):
        assert tc(segundos, 30000 / 1001) == timecode(segundos, 30000 / 1001)


def test_un_efecto_con_valores_raros_no_truena():
    from vortex_studio.model.plugins import clean_effects

    assert clean_effects([{"plugin": "grano", "values": "no soy un diccionario"}]) == []
    assert len(clean_effects([{"plugin": "grano", "values": {"cantidad": 0.5}}])) == 1


def test_una_ruta_imposible_se_rechaza_como_proyecto_danado():
    from vortex_studio.model.serialize import ProjectError, item_from_dict

    with pytest.raises(ProjectError):
        item_from_dict({"tipo": "clip", "source": "a\x00b.mp4", "start": 0, "duration": 1})


# --- audio ---------------------------------------------------------------------------

@pytest.fixture
def golpe(tmp_path):
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("Hace falta ffmpeg")
    ruta = tmp_path / "golpe.wav"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "aevalsrc='if(between(t,1.0,1.005),0.9,0)':d=3:s=48000",
                    "-ac", "2", str(ruta)], check=True)
    return ruta


def _donde_suena(clip):
    import numpy as np

    from vortex_studio.media.audio import RATE, AudioRenderer

    cuadros = list(AudioRenderer([clip]).stream(0.0, clip.duration))
    izquierda = np.concatenate([f.to_ndarray()[0] for f in cuadros]).astype(float)
    return int(np.argmax(np.abs(izquierda))) / RATE


@pytest.mark.parametrize("velocidad, esperado", [(0.5, 2.0), (0.25, 4.0), (2.0, 0.5)])
def test_en_camara_lenta_el_audio_no_se_adelanta(golpe, velocidad, esperado):
    """Antes el filtro de velocidad se comía hasta 101 ms del arranque."""
    clip = Clip(golpe, 0.0, 3.0 / velocidad, speed=velocidad)
    assert _donde_suena(clip) == pytest.approx(esperado, abs=0.015)


def test_el_punto_de_entrada_del_audio_es_exacto(golpe):
    clip = Clip(golpe, 0.0, 2.5, in_point=0.5)
    assert _donde_suena(clip) == pytest.approx(0.5, abs=0.005)


def test_la_camara_lenta_con_recorte_tambien_queda_en_su_lugar(golpe):
    clip = Clip(golpe, 0.0, 4.0, in_point=0.5, speed=0.5)
    assert _donde_suena(clip) == pytest.approx(1.0, abs=0.015)


# --- estabilización ------------------------------------------------------------------

def test_la_cache_de_estabilizacion_distingue_los_fps(tmp_path, monkeypatch):
    import numpy as np

    from vortex_studio.media import stabilize

    ruta = tmp_path / "toma.mp4"
    ruta.write_bytes(b"x")
    analisis = tmp_path / "toma.npy"
    tiempos = np.arange(0, 60, 1 / 30)
    np.save(analisis, np.column_stack([tiempos, np.sin(tiempos), np.cos(tiempos)]))
    monkeypatch.setattr(stabilize, "analysis_path", lambda p: analisis)

    quieto = stabilize.Stabilizer()
    a = quieto.offset(ruta, 1.0, 50.0, fps=30.0)
    b = quieto.offset(ruta, 1.0, 50.0, fps=60.0)
    assert a is not None and b is not None and a != b


def test_la_cache_de_estabilizacion_no_crece_sin_tope(tmp_path, monkeypatch):
    import numpy as np

    from vortex_studio.media import stabilize

    ruta = tmp_path / "toma.mp4"
    analisis = tmp_path / "toma.npy"
    tiempos = np.arange(0, 10, 1 / 30)
    np.save(analisis, np.column_stack([tiempos, np.sin(tiempos), np.cos(tiempos)]))
    monkeypatch.setattr(stabilize, "analysis_path", lambda p: analisis)

    quieto = stabilize.Stabilizer()
    for fuerza in range(1, 30):
        quieto.offset(ruta, 1.0, float(fuerza), fps=30.0)
    assert len(quieto._datos) <= 4


# --- paneles y timeline ---------------------------------------------------------------

def test_escribir_la_velocidad_en_la_casilla_se_aplica(ventana, media):
    ventana._place_video(media["mudo"])
    clip = _video(ventana)[0]
    ventana.timeline.select(clip)
    ventana._sync_panels(1.0)

    ventana.clip_panel._speed._spin.setValue(200)   # escribir 2.00×, sin arrastrar
    QApplication.processEvents()
    assert _video(ventana)[0].speed == pytest.approx(2.0)


def test_el_look_no_se_queda_del_clip_anterior(ventana, media):
    ventana._place_video(media["mudo"])
    ventana._seek(6.0)
    ventana._place_video(media["gris"])
    primero, segundo = _video(ventana)

    ventana.color_panel.set_target(primero.color, primero.name)
    ventana.color_panel._look.setCurrentText(ventana.color_panel._look.itemText(1))
    ventana.color_panel.set_target(segundo.color, segundo.name)
    assert ventana.color_panel._look.currentIndex() == 0


def test_recortar_un_par_enlazado_no_deja_el_audio_encimado(ventana, media):
    ventana._place_video(media["sonoro"])          # par de 0 a 6
    ventana._seek(8.0)
    ventana._place_video(media["sonoro"])          # otro par de 8 a 14
    linea = ventana.timeline
    linea.snapping = False
    primero = _video(ventana)[0]
    linea.select(primero)
    QApplication.processEvents()

    y = linea._track_top(ventana.sequence.tracks.index(ventana.sequence.track_of(primero))) + 20
    x_fin = linea.x_for(primero.end) - 1
    x_destino = linea.x_for(10.0)
    linea.mousePressEvent(_evento(QEvent.MouseButtonPress, x_fin, y))
    linea.mouseMoveEvent(_evento(QEvent.MouseMove, x_destino, y, Qt.NoButton))
    linea.mouseReleaseEvent(_evento(QEvent.MouseButtonRelease, x_destino, y, Qt.NoButton))
    QApplication.processEvents()

    sonidos = sorted(_audio(ventana), key=lambda c: c.start)
    for uno, otro in zip(sonidos, sonidos[1:]):
        assert uno.end <= otro.start + 1e-6, "quedaron dos audios encimados"
    videos = sorted(_video(ventana), key=lambda c: c.start)
    assert videos[1].start == pytest.approx(sonidos[1].start, abs=1e-6)


def test_el_editor_de_keyframes_no_se_dispara(ventana, media):
    from vortex_studio.ui.keyframe_editor import CurveGraph

    ventana._place_video(media["mudo"])
    clip = _video(ventana)[0]
    ventana.timeline.select(clip)
    ventana._seek(1.0)
    ventana.key_all_transform()
    ventana.open_keyframe_editor("transform.scale")
    QApplication.processEvents()

    editor = ventana.keyframe_editor.graph
    assert isinstance(editor, CurveGraph)
    editor.resize(400, 200)
    if not editor.points:
        pytest.skip("El editor de keyframes no tiene puntos que arrastrar")
    rango = editor.value_range()

    punto = editor.to_screen(editor.points[0][0], editor.points[0][1])
    editor.mousePressEvent(_evento(QEvent.MouseButtonPress, punto.x(), punto.y()))
    editor.mouseMoveEvent(_evento(QEvent.MouseMove, punto.x(), 10.0, Qt.NoButton))
    assert editor.value_range() == rango       # la escala no se mueve a medio arrastre
    editor.mouseReleaseEvent(_evento(QEvent.MouseButtonRelease, punto.x(), 10.0, Qt.NoButton))


def test_agregar_del_panel_de_medios_pide_seleccion(ventana, media):
    ventana.import_to_bin([str(media["mudo"])])
    QApplication.processEvents()
    assert not ventana.media_bin.insert_button.isEnabled()
    ventana.media_bin.list.item(0).setSelected(True)
    QApplication.processEvents()
    assert ventana.media_bin.insert_button.isEnabled()


# --- el audio de una anidada sigue a la anidada ---------------------------------------

def _con_anidada(ventana, media, velocidad=1.0):
    ventana._place_video(media["sonoro"])
    ventana.timeline.select(_video(ventana)[0])
    anidada = ventana.nest_selection()
    anidada.speed = velocidad
    if velocidad != 1.0:
        anidada.duration = 6.0 / velocidad
    return anidada


def test_el_audio_de_una_anidada_acelerada_va_a_su_velocidad(ventana, media):
    _con_anidada(ventana, media, 2.0)
    sonidos = ventana.sequence.audio_clips(ventana.project.sequence_by_id)
    assert sonidos, "la anidada no aportó audio"
    assert sonidos[0].speed == pytest.approx(2.0)
    assert sonidos[0].duration == pytest.approx(3.0, abs=0.05)


def test_el_audio_de_una_anidada_normal_no_cambia(ventana, media):
    _con_anidada(ventana, media, 1.0)
    sonidos = ventana.sequence.audio_clips(ventana.project.sequence_by_id)
    assert sonidos and sonidos[0].speed == pytest.approx(1.0)
    assert sonidos[0].duration == pytest.approx(6.0, abs=0.05)


def test_una_anidada_con_remapeo_va_muda(ventana, media):
    from vortex_studio.model import timeremap

    anidada = _con_anidada(ventana, media, 1.0)
    timeremap.set_speed_from(anidada, 1.0, 2.0)
    assert ventana.sequence.audio_clips(ventana.project.sequence_by_id) == []
