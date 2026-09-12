"""Sondeo de medios, su caché dentro del proyecto, e importar audio suelto."""

import os
import shutil

import pytest

from vortex_studio.media import probe_media
from vortex_studio.model import Project
from vortex_studio.model.media import AUDIO, IMAGE, VIDEO, MediaInfo, library_key, lookup
from vortex_studio.model.serialize import (
    FORMAT_VERSION,
    MIGRATIONS,
    load_project,
    migrate,
    project_from_dict,
    save_project,
)


# --- sondeo ---------------------------------------------------------------

def test_un_video_con_audio_trae_todo(media):
    info = probe_media(media["sonoro"])
    assert info.kind == VIDEO
    assert (info.width, info.height) == (320, 180)
    assert info.fps == pytest.approx(30.0)
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert info.channels >= 1 and info.sample_rate > 0
    assert info.duration == pytest.approx(6.0, abs=0.2)


def test_un_video_mudo_no_tiene_audio(media):
    info = probe_media(media["mudo"])
    assert info.kind == VIDEO
    assert not info.has_audio
    assert info.audio_codec == "" and info.channels == 0


def test_un_archivo_de_audio_se_reconoce(media):
    info = probe_media(media["tono"])
    assert info.kind == AUDIO
    assert info.has_audio and not info.has_video
    assert info.channels == 2
    assert (info.width, info.height) == (0, 0)
    assert info.duration == pytest.approx(3.0, abs=0.1)


def test_una_imagen_se_reconoce(media):
    info = probe_media(media["logo"])
    assert info.kind == IMAGE
    assert (info.width, info.height) == (120, 120)


def test_un_archivo_que_no_es_medio_truena(tmp_path):
    basura = tmp_path / "no-es-video.mp4"
    basura.write_bytes(b"esto no es un video")
    with pytest.raises(Exception):
        probe_media(basura)


# --- caché ----------------------------------------------------------------

class Contador:
    """Un sondeador que cuenta cuántas veces lo llamaron."""

    def __init__(self):
        self.veces = 0

    def __call__(self, path):
        self.veces += 1
        return MediaInfo(path=path, duration=5.0, width=64, height=48)


def test_el_segundo_sondeo_sale_del_cache(tmp_path):
    archivo = tmp_path / "a.mp4"
    archivo.write_bytes(b"x" * 100)
    biblioteca, sondeo = {}, Contador()

    primero = lookup(biblioteca, archivo, sondeo)
    segundo = lookup(biblioteca, archivo, sondeo)
    assert sondeo.veces == 1
    assert primero is segundo


def test_el_mismo_archivo_por_dos_caminos_es_uno(tmp_path, monkeypatch):
    archivo = tmp_path / "a.mp4"
    archivo.write_bytes(b"x" * 100)
    biblioteca, sondeo = {}, Contador()
    monkeypatch.chdir(tmp_path)

    lookup(biblioteca, archivo, sondeo)
    lookup(biblioteca, "a.mp4", sondeo)
    assert sondeo.veces == 1
    assert len(biblioteca) == 1


def test_si_el_archivo_cambia_se_vuelve_a_sondear(tmp_path):
    archivo = tmp_path / "a.mp4"
    archivo.write_bytes(b"x" * 100)
    biblioteca, sondeo = {}, Contador()
    lookup(biblioteca, archivo, sondeo)

    archivo.write_bytes(b"y" * 250)                     # otro tamaño
    lookup(biblioteca, archivo, sondeo)
    assert sondeo.veces == 2

    os.utime(archivo, (1_000_000, 1_000_000))           # misma talla, otra fecha
    lookup(biblioteca, archivo, sondeo)
    assert sondeo.veces == 3


def test_un_archivo_perdido_devuelve_lo_ultimo_que_se_supo(tmp_path):
    """Un proyecto con material desconectado tiene que poder abrirse."""
    archivo = tmp_path / "a.mp4"
    archivo.write_bytes(b"x" * 100)
    biblioteca, sondeo = {}, Contador()
    lookup(biblioteca, archivo, sondeo)

    archivo.unlink()
    info = lookup(biblioteca, archivo, sondeo)
    assert info.duration == 5.0
    assert sondeo.veces == 1


def test_un_archivo_perdido_y_nunca_sondeado_truena(tmp_path):
    with pytest.raises(OSError):
        lookup({}, tmp_path / "nunca.mp4", Contador())


def test_el_cache_se_guarda_en_el_proyecto(tmp_path, media):
    carpeta = tmp_path / "proyecto"
    carpeta.mkdir()
    video = carpeta / "video.mp4"
    shutil.copy(media["sonoro"], video)

    proyecto = Project()
    lookup(proyecto.media, video, probe_media)
    destino = save_project(proyecto, carpeta / "p")

    vuelto = load_project(destino)
    info = vuelto.media[library_key(video)]
    assert info.audio_codec == "aac"
    assert info.kind == VIDEO

    # Recién abierto, el archivo no cambió: no se vuelve a sondear.
    sondeo = Contador()
    assert lookup(vuelto.media, video, sondeo) is info
    assert sondeo.veces == 0


def test_el_cache_guarda_rutas_relativas(tmp_path, media):
    """Igual que los clips: la carpeta se tiene que poder mover."""
    import json

    carpeta = tmp_path / "proyecto"
    carpeta.mkdir()
    video = carpeta / "video.mp4"
    shutil.copy(media["mudo"], video)

    proyecto = Project()
    lookup(proyecto.media, video, probe_media)
    destino = save_project(proyecto, carpeta / "p")

    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["media"][0]["path"] == "video.mp4"


# --- migraciones ----------------------------------------------------------

def test_hay_migracion_para_cada_formato_anterior():
    """Si alguien sube el formato y olvida la migración, esto truena."""
    for version in range(1, FORMAT_VERSION):
        assert version in MIGRATIONS, f"falta la migración {version}→{version + 1}"


def test_un_proyecto_del_formato_1_llega_al_actual():
    datos = migrate({"formato": 1, "name": "viejo", "sequences": []})
    assert datos["formato"] == FORMAT_VERSION
    assert datos["media"] == []


def test_un_proyecto_del_formato_2_llega_al_actual():
    datos = migrate({"formato": 2, "name": "anterior", "sequences": []})
    assert datos["formato"] == FORMAT_VERSION
    assert "media" in datos


def test_sin_numero_de_formato_cuenta_como_el_1():
    proyecto = project_from_dict({"name": "prehistórico"})
    assert proyecto.name == "prehistórico"
    assert proyecto.media == {}


def test_migrar_no_modifica_el_diccionario_original():
    original = {"formato": 1, "sequences": []}
    migrate(original)
    assert original == {"formato": 1, "sequences": []}


# --- importar desde la ventana --------------------------------------------

def test_importar_audio_lo_pone_en_una_pista_de_audio(ventana, media):
    ventana._place_audio(media["tono"])
    assert len(ventana.sequence.audio_tracks()[0].clips) == 1
    assert all(not t.clips for t in ventana.sequence.video_tracks())
    assert ventana.history.undo_label == "Importar audio"


def test_un_audio_encima_cae_en_la_siguiente_pista_libre(ventana, media):
    ventana._place_audio(media["tono"])
    ventana._seek(0.0)
    ventana._place_audio(media["tono"])
    a1, a2, _ = ventana.sequence.audio_tracks()
    assert len(a1.clips) == 1
    assert len(a2.clips) == 1


def test_con_todas_las_pistas_ocupadas_se_pega_al_final(ventana, media):
    for _ in range(3):
        ventana._seek(0.0)
        ventana._place_audio(media["tono"])
    ventana._seek(0.0)
    ventana._place_audio(media["tono"])

    a1 = ventana.sequence.audio_tracks()[0]
    assert len(a1.clips) == 2
    assert a1.clips[1].start == pytest.approx(a1.clips[0].end)


def test_importar_como_video_un_archivo_de_audio_lo_redirige(ventana, media):
    """La extensión no manda; manda el sondeo."""
    ventana._place_video(media["tono"])
    assert not ventana.sequence.video_tracks()[-1].clips
    assert ventana.sequence.audio_tracks()[0].clips


def test_importar_dos_veces_el_mismo_video_sondea_una(ventana, media, monkeypatch):
    import vortex_studio.ui.main_window as ventana_mod

    llamadas = []
    real = ventana_mod.probe_media
    monkeypatch.setattr(ventana_mod, "probe_media",
                        lambda p: llamadas.append(p) or real(p))

    ventana._place_video(media["mudo"])
    ventana._place_video(media["mudo"])
    assert len(llamadas) == 1
    assert len(ventana.sequence.video_tracks()[-1].clips) == 2


def test_deshacer_quita_el_audio_importado(ventana, media):
    ventana._place_audio(media["tono"])
    ventana.undo()
    assert not ventana.sequence.audio_tracks()[0].clips
