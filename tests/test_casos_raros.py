"""Casos raros: proyectos dañados, archivos que faltan, valores imposibles.

Cada caso salió de un sondeo al arrancar la 0.6: se disparó a propósito y
tronó, o dejó el cuadro en negro sin decir nada. Cada arreglo lleva al
menos tres pruebas.
"""

import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from vortex_studio.model import Clip, Project, Sequence, Title, Transform, timecode
from vortex_studio.model.chroma import ChromaKey
from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.commands import Delete, Paste, RippleDelete, Split, copy_items
from vortex_studio.model.mask import Mask
from vortex_studio.model.serialize import (
    ProjectError,
    item_from_dict,
    load_project,
    project_from_dict,
    save_project,
    sequence_from_dict,
)


def _clip_dict(**extra):
    datos = {"tipo": "clip", "source": "a.mp4", "start": 0.0, "duration": 2.0}
    datos.update(extra)
    return datos


# --- cargar lo que se pueda --------------------------------------------------------

def test_un_campo_de_mas_no_tumba_la_carga():
    clip = item_from_dict(_clip_dict(campo_del_futuro=3, transform={"x": 0.2, "otro": 1}))
    assert clip.duration == 2.0 and clip.transform.x == 0.2


def test_los_keyframes_mal_formados_se_tiran_y_los_buenos_se_quedan():
    clip = item_from_dict(_clip_dict(transform={"keys": {
        "x": [[0], ["a", "b"], [1.0, 0.5], [0.0, float("nan")], [0.5, 0.25, "Lineal"]],
        "scale": [[1]],
    }}, anim={"gain": "basura", "color.exposure": [[0, 10], [2, 50, "Inventada"]]}))
    assert clip.transform.keys == {"x": [[0.5, 0.25, "Lineal"], [1.0, 0.5]]}
    assert clip.transform.at("x", 0.75) == pytest.approx(0.375)
    assert clip.anim == {"color.exposure": [[0.0, 10.0], [2.0, 50.0]]}


def test_numeros_imposibles_quedan_en_valores_que_se_pintan():
    clip = item_from_dict(_clip_dict(start=-5, duration=-2, speed=-2, in_point="x",
                                     gain=float("nan"), fade_in=-1))
    assert clip.start == 0.0 and clip.duration > 0
    assert clip.speed == 2.0 and clip.in_point == 0.0 and clip.gain == 1.0
    assert clip.fade_in == 0.0


def test_fps_y_tamano_danados_vuelven_a_valores_de_siempre():
    for fps in (0, None, -24, "treinta", float("inf")):
        secuencia = sequence_from_dict({"fps": fps, "width": 0, "height": -5, "tracks": []})
        assert secuencia.fps == 30.0
        assert (secuencia.width, secuencia.height) == (1920, 1080)


def test_pistas_sin_nombre_o_de_tipo_raro_se_abren():
    secuencia = sequence_from_dict({"tracks": [
        {"kind": "video"}, {"name": "X", "kind": "holograma"}, "basura",
        {"name": "A", "kind": "audio", "clips": [_clip_dict(start=3), _clip_dict(start=1)]}]})
    assert [t.name for t in secuencia.tracks] == ["Pista 1", "X", "A"]
    assert secuencia.tracks[1].kind == "video"
    assert [c.start for c in secuencia.tracks[2].clips] == [1.0, 3.0]


def test_marcadores_danados_se_ignoran():
    secuencia = sequence_from_dict({"tracks": [], "markers": [
        {"time": float("nan")}, {"name": "sin tiempo"}, {"time": 2, "extra": 1}, {"time": -1}]})
    assert [m.time for m in secuencia.markers] == [0.0, 2.0]


# --- rechazar con un mensaje que se entienda ----------------------------------------

def test_json_cortado_dice_en_que_linea(tmp_path):
    ruta = tmp_path / "roto.vortex"
    ruta.write_text('{\n  "formato": 5,\n  "sequences": [', encoding="utf-8")
    with pytest.raises(ProjectError, match="línea"):
        load_project(ruta)


def test_un_archivo_que_no_es_texto_se_rechaza_claro(tmp_path):
    ruta = tmp_path / "video.vortex"
    ruta.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ProjectError, match="no es texto"):
        load_project(ruta)


def test_estructuras_que_no_son_proyecto_se_rechazan_claro():
    with pytest.raises(ProjectError):
        project_from_dict([1, 2, 3])
    with pytest.raises(ProjectError, match="formato"):
        project_from_dict({"formato": "cinco"})
    with pytest.raises(ProjectError, match="Tipo desconocido"):
        item_from_dict({"tipo": "holograma"})
    with pytest.raises(ProjectError):
        item_from_dict("no soy un diccionario")


def test_proyecto_error_sigue_siendo_valueerror():
    # La ventana y el autoguardado atrapan ValueError: no hay que tocarlos.
    assert issubclass(ProjectError, ValueError)
    with pytest.raises(ValueError):
        project_from_dict({"formato": 999})


def test_secuencias_danadas_dejan_una_por_omision():
    proyecto = project_from_dict({"formato": 5, "sequences": "nada", "media": [{"x": 1}, 5]})
    assert len(proyecto.sequences) == 1 and proyecto.media == {}


# --- guardar sin dejar el archivo a medias -------------------------------------------

def test_guardar_no_deja_temporales(tmp_path):
    ruta = save_project(Project(), tmp_path / "proyecto")
    assert ruta.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["proyecto.vortex"]


def test_si_falla_la_escritura_el_proyecto_anterior_queda_intacto(tmp_path, monkeypatch):
    ruta = save_project(Project(name="Bueno"), tmp_path / "proyecto")
    antes = ruta.read_text(encoding="utf-8")

    def falla(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(Path, "write_text", falla)
    with pytest.raises(OSError):
        save_project(Project(name="Nuevo"), ruta)
    monkeypatch.undo()
    assert ruta.read_text(encoding="utf-8") == antes
    assert load_project(ruta).name == "Bueno"
    assert [p.name for p in tmp_path.iterdir()] == ["proyecto.vortex"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permisos de POSIX")
def test_un_proyecto_de_solo_lectura_no_se_sobrescribe(tmp_path):
    ruta = save_project(Project(name="Original"), tmp_path / "proyecto")
    os.chmod(ruta, 0o444)
    try:
        with pytest.raises(PermissionError):
            save_project(Project(name="Otro"), ruta)
        assert load_project(ruta).name == "Original"
    finally:
        os.chmod(ruta, 0o644)


def test_guardar_y_abrir_de_ida_y_vuelta_sigue_igual(tmp_path, media):
    proyecto = Project()
    proyecto.active.track_named("V1").add(Clip(media["mudo"], 1.0, 2.0, in_point=0.5))
    otra = load_project(save_project(proyecto, tmp_path / "vuelta"))
    clip = otra.active.track_named("V1").clips[0]
    assert (clip.start, clip.duration, clip.in_point) == (1.0, 2.0, 0.5)


# --- llave con color mal escrito -------------------------------------------------------

def test_color_de_llave_invalido_cae_al_verde():
    for malo in ("#zzzzzz", "", "#12", None, "rojo"):
        assert ChromaKey(enabled=True, color=malo).rgb == (0x00, 0xB1, 0x40)


def test_color_de_llave_corto_se_entiende():
    assert ChromaKey(color="#0f0").rgb == (0, 255, 0)
    assert ChromaKey(color="0047bb").rgb == (0x00, 0x47, 0xBB)


def test_llave_con_color_invalido_no_deja_el_cuadro_en_negro(media):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(media["mudo"]) as fuente:
        cuadro = fuente.frame_at(1.0, None, ChromaKey(enabled=True, color="#no-es-color"))
    assert cuadro is not None and cuadro.alpha


# --- fps en cero ----------------------------------------------------------------------

def test_timecode_con_fps_cero_no_divide_entre_cero():
    assert timecode(3.0, 0) == timecode(3.0, 30.0)
    assert timecode(1.0, 0.3) == timecode(1.0, 30.0) or timecode(1.0, 0.3)


def test_duracion_de_cuadro_con_fps_cero():
    assert Sequence(fps=0).frame_duration == pytest.approx(1 / 30)
    assert Sequence(fps=-5).snap_to_frame(1.01) == pytest.approx(1.0)


def test_timecode_con_nan_da_cero():
    assert timecode(float("nan"), 30) == "00:00:00:00"


# --- LUT dañado -------------------------------------------------------------------------

def _primer_cuadro(path):
    import av

    with av.open(str(path)) as contenedor:
        return next(contenedor.decode(video=0))


def test_un_lut_danado_no_deja_el_cuadro_en_negro(tmp_path, media):
    from vortex_studio.media.color import ColorProcessor

    malo = tmp_path / "malo.cube"
    malo.write_text("LUT_3D_SIZE 2\nbasura\n", encoding="utf-8")
    salida = ColorProcessor().apply(_primer_cuadro(media["gris"]), ColorAdjust(lut=str(malo)))
    assert salida is not None and salida.to_ndarray().mean() > 60


def test_con_lut_danado_lo_demas_del_color_si_se_aplica(tmp_path, media):
    from vortex_studio.media.color import ColorProcessor

    malo = tmp_path / "malo.cube"
    malo.write_text("no soy un lut", encoding="utf-8")
    cuadro = _primer_cuadro(media["gris"])
    con = ColorProcessor().apply(cuadro, ColorAdjust(exposure=100, lut=str(malo)))
    sin = ColorProcessor().apply(cuadro, ColorAdjust(exposure=100))
    assert np.array_equal(con.to_ndarray(), sin.to_ndarray())


def test_un_lut_bueno_despues_de_uno_danado_si_se_aplica(tmp_path, media):
    from vortex_studio.media.color import ColorProcessor
    from vortex_studio.model.lut import write_cube

    malo = tmp_path / "malo.cube"
    malo.write_text("x", encoding="utf-8")
    negativo = write_cube(tmp_path / "negativo.cube", 2, lambda r, g, b: (1 - r, 1 - g, 1 - b))
    procesador = ColorProcessor()
    cuadro = _primer_cuadro(media["gris"])
    procesador.apply(cuadro, ColorAdjust(lut=str(malo)))
    invertido = procesador.apply(cuadro, ColorAdjust(lut=str(negativo))).to_ndarray()
    assert abs(float(invertido.mean()) - (255 - 128)) < 6


# --- más allá del final del archivo ---------------------------------------------------

def test_mas_alla_del_final_se_sostiene_el_ultimo_cuadro(media):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(media["mudo"]) as a, VideoSource(media["mudo"]) as b:
        ultimo = a.frame_at(5.96)
        despues = b.frame_at(10.0)
    assert despues is not None and despues.data == ultimo.data


def test_el_servidor_no_da_por_perdido_un_cuadro_despues_del_final(media):
    from vortex_studio.media.frameserver import FrameJob, FrameServer

    servidor = FrameServer()
    try:
        trabajo = FrameJob.make(1, media["mudo"], 8.0)
        assert servidor.wait_for([trabajo], 10.0)
        assert not servidor.failed(trabajo) and servidor.get(trabajo) is not None
    finally:
        servidor.close()


def test_pedir_varias_veces_despues_del_final_no_vuelve_a_buscar(media):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(media["mudo"]) as fuente:
        fuente.frame_at(9.0)
        busquedas = []
        original = fuente._hold_last
        fuente._hold_last = lambda *a: (busquedas.append(a), original(*a))[1]
        for t in (9.5, 10.0, 12.0, 30.0):
            assert fuente.frame_at(t) is not None
        assert busquedas == []
        # Y regresar dentro del material sigue funcionando.
        assert fuente.frame_at(1.0).data != fuente.frame_at(30.0).data


def test_un_clip_estirado_se_exporta_sin_negro_al_final(media):
    from vortex_studio.ui.renderer import SequenceRenderer

    secuencia = Sequence.default()
    secuencia.width, secuencia.height = 320, 180
    secuencia.track_named("V1").add(Clip(media["mudo"], 0.0, 9.0))
    imagen = SequenceRenderer(secuencia).compose(8.5, 320, 180)
    assert imagen.pixelColor(160, 90).value() > 20


# --- máscara y texto con tamaños absurdos -------------------------------------------------

def test_suavizado_enorme_no_desaparece_la_mascara(qapp):
    from vortex_studio.ui.compositor import clear_mask_cache, mask_image

    clear_mask_cache()
    enorme = mask_image(320, 180, Mask(shape="Círculo", feather=1000))
    tope = mask_image(320, 180, Mask(shape="Círculo", feather=0.5))
    assert not enorme.isNull()
    assert enorme == tope


def test_suavizado_negativo_es_borde_duro(qapp):
    from vortex_studio.ui.compositor import clear_mask_cache, mask_image

    clear_mask_cache()
    assert mask_image(320, 180, Mask(shape="Rectángulo", feather=-3)) == \
        mask_image(320, 180, Mask(shape="Rectángulo", feather=0))


def test_texto_gigante_se_pinta_rapido(qapp):
    from vortex_studio.ui.compositor import compose

    inicio = time.monotonic()
    imagen = compose(320, 180, [], [], [Title(0, 2, text="Hola", size=50.0)], 0.5)
    assert not imagen.isNull() and time.monotonic() - inicio < 2.0


# --- exportar a un cuadro diminuto ----------------------------------------------------------

@pytest.mark.parametrize("ancho,alto", [(1, 1), (0, 0), (1, 400)])
def test_exportar_a_cuadro_diminuto_explica_por_que(tmp_path, ancho, alto):
    from vortex_studio.media.encoder import export_video

    with pytest.raises(ValueError, match="demasiado chico"):
        export_video(tmp_path / "x.mp4", iter([]), 0, ancho, alto, 30)
    assert not (tmp_path / "x.mp4").exists()


# --- subtítulos en Windows-1252 ------------------------------------------------------------

SRT = "1\n00:00:01,000 --> 00:00:02,500\nCanción del ñandú\n"


def test_srt_en_windows_1252_conserva_los_acentos(tmp_path):
    from vortex_studio.model.subtitles import read_file

    ruta = tmp_path / "viejo.srt"
    ruta.write_bytes(SRT.encode("cp1252"))
    assert read_file(ruta)[0].text == "Canción del ñandú"


def test_srt_en_utf8_sigue_igual(tmp_path):
    from vortex_studio.model.subtitles import read_file

    ruta = tmp_path / "nuevo.srt"
    ruta.write_text(SRT, encoding="utf-8")
    assert read_file(ruta)[0].text == "Canción del ñandú"


def test_srt_con_bom_y_fin_de_linea_de_windows(tmp_path):
    from vortex_studio.model.subtitles import read_file

    ruta = tmp_path / "bom.srt"
    ruta.write_bytes(("﻿" + SRT.replace("\n", "\r\n")).encode("utf-8"))
    cue = read_file(ruta)[0]
    assert (cue.start, cue.end, cue.text) == (1.0, 2.5, "Canción del ñandú")


# --- estabilizar algo que no es video ---------------------------------------------------------

def test_estabilizar_un_audio_dice_que_no_hay_video(media):
    from vortex_studio.media.stabilize import analyze

    with pytest.raises(ValueError, match="no tiene video"):
        analyze(media["tono"])


def test_estabilizar_un_archivo_danado_falla_sin_dejar_cache(tmp_path):
    from vortex_studio.media.stabilize import STABILIZER, load_or_analyze

    roto = tmp_path / "roto.mp4"
    roto.write_text("no soy video", encoding="utf-8")
    with pytest.raises(Exception):
        load_or_analyze(roto)
    assert not STABILIZER.has_analysis(roto)


def test_el_analizador_avisa_la_falla_y_sigue_con_el_siguiente(qapp, media, tmp_path):
    from vortex_studio.media.stabilize import STABILIZER, load_or_analyze
    from vortex_studio.ui.analysis import BackgroundAnalyzer

    fallas, listos = [], []
    analizador = BackgroundAnalyzer(load_or_analyze, STABILIZER.has_analysis)
    analizador.failed.connect(lambda p, e: fallas.append((p, e)))
    analizador.ready.connect(listos.append)
    copia = tmp_path / "mudo.mp4"
    shutil.copy(media["mudo"], copia)
    analizador.request([media["tono"], copia])
    assert analizador.wait(60)
    qapp.processEvents()
    assert [Path(p).name for p, _ in fallas] == ["tono.wav"]
    assert [Path(p).name for p in listos] == ["mudo.mp4"]


# --- rutas con acentos y emoji ---------------------------------------------------------------

@pytest.fixture
def ruta_rara(tmp_path, media):
    carpeta = tmp_path / "Tomas de mamá ñ 🎬"
    carpeta.mkdir()
    destino = carpeta / "canción 🎸 ñ.mp4"
    shutil.copy(media["sonoro"], destino)
    return destino


def test_sondeo_y_onda_con_emoji_en_la_ruta(ruta_rara):
    from vortex_studio.media import probe_media
    from vortex_studio.media.waveform import load_or_compute

    assert probe_media(ruta_rara).duration == pytest.approx(6.0, abs=0.1)
    assert load_or_compute(ruta_rara).shape[1] > 300


def test_guardar_junto_a_material_con_emoji_guarda_relativo(ruta_rara):
    proyecto = Project()
    proyecto.active.track_named("V1").add(Clip(ruta_rara, 0, 2))
    ruta = save_project(proyecto, ruta_rara.parent / "proyecto 🎬")
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    guardada = crudo["sequences"][0]["tracks"][2]["clips"][0]["source"]
    assert guardada == "canción 🎸 ñ.mp4"
    assert load_project(ruta).active.track_named("V1").clips[0].source == ruta_rara.resolve()


def test_se_ve_y_se_oye_material_con_emoji(ruta_rara):
    from vortex_studio.media.mixer import AudioMixer
    from vortex_studio.ui.renderer import SequenceRenderer

    secuencia = Sequence.default()
    secuencia.track_named("V1").add(Clip(ruta_rara, 0, 2))
    assert SequenceRenderer(secuencia).compose(1.0, 320, 180).pixelColor(160, 90).value() > 20
    bloques = list(AudioMixer([Clip(ruta_rara, 0, 2)]).stream(0, 2))
    pico = max(float(np.abs(b.to_ndarray()).max()) for b in bloques)
    assert pico > 0.1


# --- archivos que faltan ------------------------------------------------------------------------

def _proyecto_con_faltante(tmp_path, media):
    copia = tmp_path / "se-va.mp4"
    shutil.copy(media["mudo"], copia)
    proyecto = Project()
    proyecto.active.track_named("V1").add(Clip(copia, 0, 2))
    proyecto.active.track_named("V2").add(Clip(media["mudo"], 2, 2))
    ruta = save_project(proyecto, tmp_path / "con-faltante")
    copia.unlink()
    return ruta


def test_la_ventana_dice_que_archivos_faltan(ventana, tmp_path, media):
    ruta = _proyecto_con_faltante(tmp_path, media)
    ventana.adopt_project(load_project(ruta), ruta)
    assert [p.name for p in ventana.missing_media()] == ["se-va.mp4"]
    assert "Faltan 1 archivo" in ventana.statusBar().currentMessage()


def test_un_proyecto_completo_no_avisa_nada(ventana, tmp_path, media):
    proyecto = Project()
    proyecto.active.track_named("V1").add(Clip(media["mudo"], 0, 2))
    ventana.adopt_project(proyecto, None)
    assert ventana.missing_media() == []
    assert "Faltan" not in ventana.statusBar().currentMessage()


def test_con_archivos_faltantes_se_sigue_viendo_lo_demas(ventana, tmp_path, media, qapp):
    ruta = _proyecto_con_faltante(tmp_path, media)
    ventana.adopt_project(load_project(ruta), ruta)
    ventana._scrubbed(3.0)
    ventana._settle_preview()
    imagen = ventana.preview.current_image()
    assert imagen is not None and imagen.pixelColor(960, 540).value() > 20
    ventana._scrubbed(1.0)
    ventana._settle_preview()          # el faltante: negro, pero no truena


# --- todo bloqueado ---------------------------------------------------------------------------------

def _todo_bloqueado(media):
    secuencia = Sequence.default()
    clip = secuencia.track_named("V1").add(Clip(media["mudo"], 0, 2))
    datos = copy_items(secuencia, [clip])
    for pista in secuencia.tracks:
        pista.locked = True
    return secuencia, clip, datos


def test_con_todo_bloqueado_ningun_comando_cambia_nada(media):
    secuencia, clip, datos = _todo_bloqueado(media)
    assert not Split(items=[clip], time=1.0).apply(secuencia)
    assert not Delete(items=[clip]).apply(secuencia)
    assert not RippleDelete(item=clip).apply(secuencia)
    assert not Paste(entries=datos, time=5.0).apply(secuencia)
    assert [c.duration for c in secuencia.track_named("V1").clips] == [2]


def test_con_todo_bloqueado_la_ventana_no_inserta_texto(ventana, media):
    for pista in ventana.sequence.tracks:
        pista.locked = True
    ventana.add_title()
    assert all(not p.clips for p in ventana.sequence.text_tracks())


def test_con_todo_bloqueado_no_se_pone_capa_de_ajuste(ventana):
    for pista in ventana.sequence.tracks:
        pista.locked = True
    assert ventana.add_adjustment_layer() is None
    assert "bloqueadas" in ventana.statusBar().currentMessage()


def test_con_v1_bloqueada_el_video_entra_en_v2(ventana, media):
    ventana.sequence.track_named("V1").locked = True
    ventana.place_media(media["sonoro"])
    assert not ventana.sequence.track_named("V1").clips
    assert len(ventana.sequence.track_named("V2").clips) == 1
    assert len(ventana.sequence.track_named("A1").clips) == 1


def test_con_video_bloqueado_no_entra_ni_imagen_ni_video(ventana, media):
    for pista in ventana.sequence.video_tracks():
        pista.locked = True
    ventana.place_media(media["logo"])
    ventana.place_media(media["mudo"])
    assert all(not p.clips for p in ventana.sequence.video_tracks())
    assert "bloqueadas" in ventana.statusBar().currentMessage()


def test_con_audio_bloqueado_el_video_entra_sin_su_audio(ventana, media):
    for pista in ventana.sequence.audio_tracks():
        pista.locked = True
    ventana.place_media(media["sonoro"])
    clip = ventana.sequence.track_named("V1").clips[0]
    assert clip.link == "" and all(not p.clips for p in ventana.sequence.audio_tracks())
    ventana.place_media(media["tono"])
    assert all(not p.clips for p in ventana.sequence.audio_tracks())


def test_menus_de_clip_no_tocan_una_pista_bloqueada(ventana, media):
    secuencia = ventana.sequence
    a = secuencia.track_named("V1").add(Clip(media["mudo"], 0, 2))
    b = secuencia.track_named("V1").add(Clip(media["mudo"], 2, 2))
    secuencia.track_named("V1").locked = True
    ventana.timeline.select(b)
    ventana.set_fade(entrada=1.0, salida=1.0)
    ventana.set_dissolve(1.0)
    ventana.key_all_transform()
    assert (b.fade_in, b.fade_out, b.dissolve, b.transform.keys) == (0.0, 0.0, 0.0, {})
    ventana._scrubbed(1.0)
    ventana.timeline.select(None)
    ventana.freeze_frame()
    assert [c.duration for c in secuencia.track_named("V1").clips] == [2, 2]
    assert a.speed == 1.0


# --- secuencia vacía -----------------------------------------------------------------------------------

def test_secuencia_vacia_no_exporta(ventana):
    ventana.export_video()
    assert "vacía" in ventana.statusBar().currentMessage()


def test_secuencia_vacia_no_tiene_zonas_que_renderizar(ventana):
    assert ventana.zones() == []
    assert ventana.render_zones() == 0


def test_secuencia_vacia_se_pinta_negra(ventana):
    ventana._settle_preview()
    assert ventana.preview.current_image() is None or \
        ventana.preview.current_image().pixelColor(10, 10).value() == 0


# --- archivos más cortos que la lectura adelantada del decodificador ----------------------

@pytest.fixture(scope="module")
def corto(tmp_path_factory):
    """Doce cuadros, cada uno más claro: menos de lo que el decodificador lee adelantado."""
    import av

    ruta = tmp_path_factory.mktemp("corto") / "corto.mp4"
    with av.open(str(ruta), "w") as contenedor:
        flujo = contenedor.add_stream("libx264", rate=10)
        flujo.width, flujo.height, flujo.pix_fmt = 64, 36, "yuv444p"
        flujo.options = {"qp": "0", "preset": "ultrafast"}
        for n in range(12):
            cuadro = av.VideoFrame.from_ndarray(np.full((36, 64, 3), 20 * n, np.uint8),
                                                format="rgb24")
            for paquete in flujo.encode(cuadro):
                contenedor.mux(paquete)
        for paquete in flujo.encode():
            contenedor.mux(paquete)
    return ruta


def _nivel(frame):
    return int(np.frombuffer(frame.data, np.uint8)[0])


def test_leer_hacia_adelante_un_archivo_corto_no_truena(corto):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(corto) as fuente:
        niveles = [_nivel(fuente.frame_at(n / 10)) for n in range(12)]
    assert niveles == pytest.approx([20 * n for n in range(12)], abs=2)


def test_despues_del_final_de_un_archivo_corto_se_puede_regresar(corto):
    from vortex_studio.media.decoder import VideoSource

    with VideoSource(corto) as fuente:
        assert _nivel(fuente.frame_at(1.1)) == pytest.approx(220, abs=2)
        assert _nivel(fuente.frame_at(0.9)) == pytest.approx(180, abs=2)
        assert _nivel(fuente.frame_at(1.0)) == pytest.approx(200, abs=2)


def test_el_servidor_saca_todos_los_cuadros_de_un_archivo_corto(corto):
    from vortex_studio.media.frameserver import FrameJob, FrameServer

    servidor = FrameServer()
    try:
        trabajos = [FrameJob.make(1, corto, n / 10) for n in range(12)]
        for trabajo in trabajos:
            assert servidor.wait_for([trabajo], 10)
        assert not any(servidor.failed(t) for t in trabajos)
    finally:
        servidor.close()
