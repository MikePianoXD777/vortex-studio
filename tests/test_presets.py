"""Exportar con presets: tamaño de la secuencia, 1080p, 4K y solo audio."""

import av
import pytest
from PySide6.QtWidgets import QLabel

from vortex_studio.media.audio import peaks
from vortex_studio.media.encoder import Cancelled, export_audio
from vortex_studio.media.mixer import AudioMixer
from vortex_studio.media.presets import AUDIO, DEFAULT, PRESETS, by_name, output_size
from vortex_studio.model import Clip
from vortex_studio.ui.main_window import ExportDialog

SECUENCIA = by_name("Tamaño de la secuencia")
FULL_HD = by_name("H.264 1080p")
CUATRO_K = by_name("H.264 4K")
SOLO_AUDIO = by_name("Solo audio (AAC)")


def info(path):
    with av.open(str(path)) as c:
        video = c.streams.video[0] if c.streams.video else None
        return {
            "tipos": sorted(s.type for s in c.streams),
            "tamaño": (video.codec_context.width, video.codec_context.height) if video else None,
            "duracion": float(c.duration / av.time_base) if c.duration else 0.0,
        }


# --- la cuenta de tamaños -------------------------------------------------

def test_hay_los_cuatro_presets():
    assert [p.name for p in PRESETS] == [
        "Tamaño de la secuencia", "H.264 1080p", "H.264 4K", "Solo audio (AAC)"]
    assert DEFAULT is SECUENCIA


def test_el_de_la_secuencia_no_cambia_el_tamano():
    assert output_size(SECUENCIA, 1280, 720) == (1280, 720)


def test_1080p_escala_a_1920_por_1080():
    assert output_size(FULL_HD, 320, 180) == (1920, 1080)
    assert output_size(FULL_HD, 3840, 2160) == (1920, 1080)


def test_4k_escala_a_3840_por_2160():
    assert output_size(CUATRO_K, 1920, 1080) == (3840, 2160)


def test_1080p_es_el_lado_corto():
    """Un vertical de TikTok sale de 1080 × 1920, no de 608 × 1080."""
    assert output_size(FULL_HD, 1080, 1920) == (1080, 1920)
    assert output_size(CUATRO_K, 1080, 1920) == (2160, 3840)
    assert output_size(FULL_HD, 2560, 1080) == (2560, 1080)       # cine 21:9
    assert output_size(FULL_HD, 1080, 1350) == (1080, 1350)       # 4:5


def test_los_lados_siempre_quedan_pares():
    """H.264 no acepta lados impares."""
    for preset in (SECUENCIA, FULL_HD, CUATRO_K):
        for ancho, alto in ((321, 181), (1000, 563), (777, 1333)):
            w, h = output_size(preset, ancho, alto)
            assert w % 2 == 0 and h % 2 == 0, (preset.name, ancho, alto)


def test_solo_audio_no_tiene_tamano():
    assert SOLO_AUDIO.kind == AUDIO
    assert SOLO_AUDIO.extension == ".m4a"
    assert output_size(SOLO_AUDIO, 1920, 1080) == (0, 0)


def test_un_nombre_desconocido_da_el_de_siempre():
    assert by_name("Preset de otra versión") is DEFAULT


# --- exportar desde la ventana --------------------------------------------

def test_exportar_en_1080p(ventana, media, tmp_path):
    ventana._place_video(media["sonoro"])                 # secuencia de 320 × 180
    salida = tmp_path / "hd.mp4"
    assert ventana._run_export(salida, 0.0, 0.2, "Borrador", False, FULL_HD)
    assert info(salida)["tamaño"] == (1920, 1080)


def test_exportar_en_4k(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    salida = tmp_path / "4k.mp4"
    assert ventana._run_export(salida, 0.0, 0.1, "Borrador", False, CUATRO_K)
    assert info(salida)["tamaño"] == (3840, 2160)


def test_exportar_una_secuencia_vertical_en_1080p(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    ventana.set_format(1080, 1920)
    salida = tmp_path / "vertical.mp4"
    assert ventana._run_export(salida, 0.0, 0.1, "Borrador", False, FULL_HD)
    assert info(salida)["tamaño"] == (1080, 1920)


def test_el_preset_de_siempre_conserva_el_tamano(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    salida = tmp_path / "igual.mp4"
    assert ventana._run_export(salida, 0.0, 0.1, "Borrador", False)
    assert info(salida)["tamaño"] == (320, 180)


def test_el_1080p_trae_el_texto_en_su_lugar(ventana, media, tmp_path):
    """Escalar no es estirar el cuadro chico: se compone al tamaño nuevo,
    y el subtítulo sigue en la franja de abajo."""
    from vortex_studio.media import VideoSource

    ventana._place_video(media["gris"])
    ventana._seek(0.0)
    ventana.add_title()
    ventana._title.text = "MMMMMMMM"
    ventana._title.background = True

    salida = tmp_path / "texto.mp4"
    assert ventana._run_export(salida, 0.0, 0.2, "Alta", False, FULL_HD)
    fuente = VideoSource(salida)
    try:
        f = fuente.frame_at(0.1)

        def desviacion(y):
            """Qué tan lejos del gris liso llega el pixel más distinto del renglón.

            La primera versión promediaba el renglón completo, y el texto
            cubre solo una parte del ancho: el promedio casi no se movía con
            el subtítulo perfectamente dibujado.
            """
            inicio = y * f.stride
            fila = f.data[inicio: inicio + f.width * 3]
            return max(abs(v - 128) for v in fila)

        assert desviacion(int(f.height * 0.88)) > 60      # abajo está el subtítulo
        assert desviacion(int(f.height * 0.40)) < 20      # en medio, gris liso
    finally:
        fuente.close()


def test_terminar_de_exportar_avisa_en_la_barra(ventana, media, tmp_path):
    """Sin diálogo modal: terminar no amerita detener al usuario."""
    ventana._place_video(media["mudo"])
    ventana._run_export(tmp_path / "x.mp4", 0.0, 0.1, "Borrador", False, FULL_HD)
    mensaje = ventana.statusBar().currentMessage()
    assert "Exportado" in mensaje and "1920×1080" in mensaje


# --- solo audio -----------------------------------------------------------

def test_solo_audio_saca_un_archivo_sin_video(ventana, media, tmp_path):
    ventana._place_video(media["sonoro"])
    salida = tmp_path / "sonido.m4a"
    assert ventana._run_export(salida, 0.0, 2.0, "Normal", True, SOLO_AUDIO)

    datos = info(salida)
    assert datos["tipos"] == ["audio"]
    assert datos["duracion"] == pytest.approx(2.0, abs=0.1)
    assert max(peaks(salida, 40)) > 0.2, "el audio salió mudo"


def test_solo_audio_mezcla_todas_las_pistas(ventana, media, tmp_path):
    ventana._place_video(media["sonoro"])
    ventana._seek(0.0)
    ventana._place_audio(media["tono"])            # cae en A2, encimado
    salida = tmp_path / "mezcla.m4a"
    assert ventana._run_export(salida, 0.0, 2.0, "Normal", True, SOLO_AUDIO)
    assert info(salida)["tipos"] == ["audio"]


def test_solo_audio_sin_audio_avisa_y_no_crea_archivo(ventana, media, tmp_path):
    ventana._place_video(media["mudo"])
    salida = tmp_path / "nada.m4a"
    assert not ventana._run_export(salida, 0.0, 1.0, "Normal", True, SOLO_AUDIO)
    assert not salida.exists()
    assert "No hay audio" in ventana.statusBar().currentMessage()


def test_cancelar_el_audio_no_deja_archivo(media, tmp_path):
    salida = tmp_path / "cancelado.m4a"
    clip = Clip(source=media["tono"], start=0.0, duration=3.0)
    with pytest.raises(Cancelled):
        export_audio(salida, AudioMixer([clip]).stream(0.0, 3.0), 3.0,
                     lambda hecho, total: hecho < 1000)
    assert not salida.exists()


def test_el_progreso_del_audio_llega_al_total(media, tmp_path):
    avances = []
    clip = Clip(source=media["tono"], start=0.0, duration=3.0)
    export_audio(tmp_path / "p.m4a", AudioMixer([clip]).stream(0.0, 1.3), 1.3,
                 lambda hecho, total: avances.append((hecho, total)) or True)
    assert avances[-1] == (1300, 1300)
    assert [h for h, _ in avances] == sorted(h for h, _ in avances)


# --- el diálogo -----------------------------------------------------------

def test_el_dialogo_muestra_el_tamano_del_preset(ventana, media):
    ventana._place_video(media["mudo"])
    dialogo = ExportDialog(ventana, 0.0, ventana.sequence.duration, ventana.sequence)
    assert dialogo._size.text() == "320 × 180"
    dialogo._preset.setCurrentText("H.264 1080p")
    assert dialogo._size.text() == "1920 × 1080"
    assert dialogo.preset() is FULL_HD


def test_solo_audio_apaga_lo_que_no_aplica(ventana, media):
    ventana._place_video(media["sonoro"])
    dialogo = ExportDialog(ventana, 0.0, ventana.sequence.duration, ventana.sequence)
    dialogo._preset.setCurrentText("Solo audio (AAC)")
    assert not dialogo._quality.isEnabled()
    assert not dialogo._audio.isEnabled() and dialogo._audio.isChecked()
    assert dialogo._ok.isEnabled()

    dialogo._preset.setCurrentText("H.264 4K")
    assert dialogo._quality.isEnabled()


def test_solo_audio_sin_audio_no_deja_exportar(ventana, media):
    ventana._place_video(media["mudo"])
    dialogo = ExportDialog(ventana, 0.0, ventana.sequence.duration, ventana.sequence)
    dialogo._preset.setCurrentText("Solo audio (AAC)")
    assert not dialogo._ok.isEnabled()


def test_el_dialogo_ya_no_dice_que_el_audio_no_suena(ventana, media):
    """Ese aviso quedó de antes de que hubiera sonido al editar: ya era falso."""
    ventana._place_video(media["sonoro"])
    dialogo = ExportDialog(ventana, 0.0, ventana.sequence.duration, ventana.sequence)
    textos = " ".join(l.text() for l in dialogo.findChildren(QLabel))
    assert "no suena" not in textos
