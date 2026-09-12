"""Pistas de video apiladas y modos de fusión.

Antes solo se pintaba la pista más alta con material: poner algo en V2
hacía desaparecer V1 por completo. Sin apilar no hay cuadro dentro de
cuadro, y un modo de fusión no tiene con qué fusionarse.
"""

import pytest

from vortex_studio.model import BLENDS, Clip, is_normal


def apilado(ventana, media, arriba="gris", **kw):
    """Un clip en V1 y otro en V2, los dos de 2 segundos."""
    ventana._place_video(media["gris"])
    abajo = ventana.sequence.video_tracks()[-1].clips[0]

    encima = Clip(source=media[arriba], start=0.0, duration=2.0, **kw)
    ventana.sequence.video_tracks()[0].add(encima)
    return abajo, encima


def luz(img, x: float = 0.5, y: float = 0.5) -> int:
    px = min(img.width() - 1, int(img.width() * x))
    py = min(img.height() - 1, int(img.height() * y))
    return sum(img.pixelColor(px, py).getRgb()[:3])


def cuadro(ventana, t: float = 0.5):
    ventana._seek(t)
    return ventana.preview.current_image()


# --- el apilado -----------------------------------------------------------

def test_una_sola_pista_da_una_capa(ventana, media):
    ventana._place_video(media["gris"])
    assert len(ventana.sequence.video_stack_at(0.5)) == 1


def test_una_capa_opaca_de_arriba_tapa_la_de_abajo(ventana, media):
    """Si tapa, no hay que decodificar lo de abajo: costaría el doble."""
    apilado(ventana, media)
    assert len(ventana.sequence.video_stack_at(0.5)) == 1


def test_una_capa_encogida_deja_ver_la_de_abajo(ventana, media):
    _, encima = apilado(ventana, media)
    encima.transform.scale = 0.4
    assert len(ventana.sequence.video_stack_at(0.5)) == 2


def test_una_capa_a_medias_deja_ver_la_de_abajo(ventana, media):
    _, encima = apilado(ventana, media)
    encima.transform.opacity = 0.5
    assert len(ventana.sequence.video_stack_at(0.5)) == 2


def test_una_capa_con_mascara_deja_ver_la_de_abajo(ventana, media):
    _, encima = apilado(ventana, media)
    encima.mask.shape = "Círculo"
    assert len(ventana.sequence.video_stack_at(0.5)) == 2


def test_una_capa_con_fusion_deja_ver_la_de_abajo(ventana, media):
    _, encima = apilado(ventana, media)
    encima.blend = "Multiplicar"
    assert len(ventana.sequence.video_stack_at(0.5)) == 2


def test_una_capa_en_fundido_deja_ver_la_de_abajo(ventana, media):
    _, encima = apilado(ventana, media)
    encima.fade_in = 1.0
    assert len(ventana.sequence.video_stack_at(0.5)) == 2


def test_el_orden_es_de_abajo_hacia_arriba(ventana, media):
    """Es el orden de pintado: lo de V2 tiene que quedar encima."""
    abajo, encima = apilado(ventana, media)
    encima.transform.scale = 0.4
    capas = ventana.sequence.video_stack_at(0.5)
    assert [c for c, _ in capas] == [abajo, encima]


# --- cuadro dentro de cuadro ----------------------------------------------

def test_el_cuadro_dentro_de_cuadro_deja_ver_el_fondo(ventana, media):
    """La prueba de que V1 dejó de desaparecer."""
    _, encima = apilado(ventana, media, arriba="mudo")
    ventana.timeline.select(encima)
    ventana.picture_in_picture()

    img = cuadro(ventana)
    assert luz(img, 0.5, 0.5) == pytest.approx(384, abs=30)   # el gris de V1


def test_llenar_el_cuadro_lo_deshace(ventana, media):
    _, encima = apilado(ventana, media, arriba="mudo")
    ventana.timeline.select(encima)
    ventana.picture_in_picture()
    assert len(ventana.sequence.video_stack_at(0.5)) == 2

    ventana.fill_frame()
    assert encima.transform.is_neutral
    assert len(ventana.sequence.video_stack_at(0.5)) == 1


def test_el_cuadro_dentro_de_cuadro_borra_la_animacion_previa(ventana, media):
    """Con keyframes puestos, el tamaño fijo no se vería."""
    _, encima = apilado(ventana, media)
    encima.transform.set_key("scale", 0.0, 1.0)
    ventana.timeline.select(encima)
    ventana.picture_in_picture()
    assert not encima.transform.keys


# --- modos de fusión ------------------------------------------------------

def test_normal_deja_el_gris_como_estaba(ventana, media):
    apilado(ventana, media)
    assert luz(cuadro(ventana)) == pytest.approx(384, abs=12)


def test_multiplicar_oscurece(ventana, media):
    """Gris medio por gris medio da la cuarta parte de la luz."""
    _, encima = apilado(ventana, media)
    encima.blend = "Multiplicar"
    assert luz(cuadro(ventana)) == pytest.approx(192, abs=25)


def test_trama_aclara(ventana, media):
    _, encima = apilado(ventana, media)
    encima.blend = "Trama"
    assert luz(cuadro(ventana)) == pytest.approx(576, abs=25)


def test_sumar_llega_al_blanco(ventana, media):
    _, encima = apilado(ventana, media)
    encima.blend = "Sumar"
    assert luz(cuadro(ventana)) > 700


def test_diferencia_de_lo_mismo_da_negro(ventana, media):
    _, encima = apilado(ventana, media)
    encima.blend = "Diferencia"
    assert luz(cuadro(ventana)) < 30


def test_todos_los_modos_pintan_sin_reventar(ventana, media):
    _, encima = apilado(ventana, media)
    for nombre in BLENDS:
        encima.blend = nombre
        assert cuadro(ventana) is not None, nombre


def test_un_modo_desconocido_se_pinta_normal(ventana, media):
    """Más vale que la capa se vea de más que que desaparezca."""
    assert is_normal("Luz galáctica")
    _, encima = apilado(ventana, media)
    encima.blend = "Luz galáctica"
    assert luz(cuadro(ventana)) == pytest.approx(384, abs=12)


def test_el_comando_de_fusion_avisa_si_no_hay_nada_debajo(ventana, media):
    ventana._place_video(media["gris"])
    ventana.set_blend("Multiplicar")
    assert "pista de abajo" in ventana.statusBar().currentMessage()


def test_la_fusion_no_aplica_a_una_pista_de_audio(ventana, media):
    ventana._place_video(media["sonoro"])
    audio = ventana.sequence.audio_tracks()[0].clips[0]
    ventana.timeline.select(audio)
    ventana.set_blend("Multiplicar")
    assert audio.blend == "Normal"


# --- guardado -------------------------------------------------------------

def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    _, encima = apilado(ventana, media)
    encima.blend = "Luz suave"

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.video_tracks()[0].clips[0]
    assert vuelto.blend == "Luz suave"
