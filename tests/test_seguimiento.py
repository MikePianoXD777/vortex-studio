"""Seguimiento de movimiento: una máscara o un texto siguen a un objeto."""

import numpy as np
import pytest

from vortex_studio.model import Clip, Sequence, Title, Transform
from vortex_studio.model import tracking as seguir
from vortex_studio.model.transform import FILL, FIT


def _escribir(path, cuadros, fps=30):
    import av

    alto, ancho, _ = cuadros[0].shape
    with av.open(str(path), "w") as contenedor:
        flujo = contenedor.add_stream("libx264", rate=fps)
        flujo.width, flujo.height, flujo.pix_fmt = ancho, alto, "yuv420p"
        flujo.options = {"crf": "10", "preset": "ultrafast"}
        for arreglo in cuadros:
            for paquete in flujo.encode(av.VideoFrame.from_ndarray(arreglo, format="rgb24")):
                contenedor.mux(paquete)
        for paquete in flujo.encode():
            contenedor.mux(paquete)
    return path


@pytest.fixture(scope="module")
def pelota(tmp_path_factory):
    """Una mancha con textura que cruza en diagonal un fondo con ruido, 2 s a 30 fps.

    Va de (80, 60) a (240, 120) en pixeles de un cuadro de 320×180.
    """
    rng = np.random.default_rng(11)
    fondo = (rng.random((180, 320)) * 60 + 40).astype(np.uint8)
    mancha = (rng.random((24, 24)) * 200 + 55).astype(np.uint8)
    cuadros = []
    for n in range(60):
        x = int(round(80 + 160 * n / 59)) - 12
        y = int(round(60 + 60 * n / 59)) - 12
        gris = fondo.copy()
        gris[y:y + 24, x:x + 24] = mancha
        cuadros.append(np.repeat(gris[:, :, None], 3, axis=2))
    return _escribir(tmp_path_factory.mktemp("pelota") / "pelota.mp4", cuadros)


def _esperado(t):
    n = t * 30
    return (80 + 160 * n / 59) / 320, (60 + 60 * n / 59) / 180


# --- buscar ----------------------------------------------------------------------------

def test_encuentra_un_molde_donde_se_puso():
    from vortex_studio.media.tracking import match

    rng = np.random.default_rng(1)
    busqueda = rng.random((80, 120))
    molde = busqueda[30:50, 55:85].copy()
    x, y, parecido = match(molde, busqueda)
    assert (x, y) == pytest.approx((55, 30), abs=0.3) and parecido > 0.99


def test_el_parecido_no_depende_del_brillo():
    from vortex_studio.media.tracking import match

    rng = np.random.default_rng(2)
    busqueda = rng.random((80, 120))
    molde = busqueda[10:30, 20:40] * 0.5 + 0.3          # más oscuro y lavado
    x, y, parecido = match(molde, busqueda)
    assert (x, y) == pytest.approx((20, 10), abs=0.3) and parecido > 0.99


def test_un_molde_parejo_o_mas_grande_no_se_puede_buscar():
    from vortex_studio.media.tracking import match

    assert match(np.ones((10, 10)), np.random.default_rng(3).random((40, 40))) is None
    assert match(np.random.default_rng(3).random((50, 50)), np.zeros((40, 40))) is None


def test_sigue_la_mancha_de_principio_a_fin(pelota):
    from vortex_studio.media.tracking import track

    filas = track(pelota, 0.0, 2.0, (80 / 320, 60 / 180, 24 / 320, 24 / 180))
    assert len(filas) == 60
    for t, x, y, parecido in filas[::10]:
        ex, ey = _esperado(t)
        assert (x, y) == pytest.approx((ex, ey), abs=0.012)
    assert filas[:, 3].min() > 0.5


def test_seguir_desde_la_mitad_empieza_ahi(pelota):
    from vortex_studio.media.tracking import track

    ex, ey = _esperado(1.0)
    filas = track(pelota, 1.0, 1.5, (ex, ey, 24 / 320, 24 / 180))
    assert filas[0, 0] == pytest.approx(1.0, abs=0.02)
    assert filas[-1, 0] == pytest.approx(1.5, abs=0.04)
    assert tuple(filas[-1, 1:3]) == pytest.approx(_esperado(filas[-1, 0]), abs=0.012)


def test_seguir_en_un_audio_explica_que_no_hay_video(media):
    from vortex_studio.media.tracking import track

    with pytest.raises(ValueError, match="no tiene video"):
        track(media["tono"], 0, 1, (0.5, 0.5, 0.1, 0.1))


# --- del material al cuadro de salida ---------------------------------------------------

def test_sin_encuadre_ni_transformacion_el_punto_no_cambia():
    assert seguir.source_to_frame(0.3, 0.7, (320, 180), (1920, 1080), Transform()) == \
        pytest.approx((0.3, 0.7))


def test_ajustar_un_vertical_en_horizontal_mete_el_punto_al_centro():
    x, y = seguir.source_to_frame(0.0, 0.5, (1080, 1920), (1920, 1080), Transform(fit=FIT))
    ancho = 1080 * 1080 / 1920
    assert x == pytest.approx((1920 - ancho) / 2 / 1920) and y == pytest.approx(0.5)


def test_ida_y_vuelta_con_escala_giro_y_rellenar():
    transform = Transform(x=0.1, y=-0.05, scale=1.3, rotation=20, fit=FILL, anchor_x=0.2)
    for sx, sy in ((0.2, 0.3), (0.8, 0.6), (0.5, 0.5)):
        fx, fy = seguir.source_to_frame(sx, sy, (1280, 720), (1080, 1920), transform)
        assert seguir.frame_to_source(fx, fy, (1280, 720), (1080, 1920), transform) == \
            pytest.approx((sx, sy), abs=1e-9)


# --- escribir keyframes ---------------------------------------------------------------------

def _filas():
    t = np.linspace(0, 2, 61)
    return np.column_stack([t, 0.2 + 0.3 * t, 0.4 + 0.1 * t, np.ones_like(t)])


def test_la_mascara_recibe_un_keyframe_por_cuadro():
    clip = Clip("a.mp4", 5.0, 2.0)
    puntos = seguir.samples(clip, _filas(), 0.0, 30, (320, 180), (320, 180))
    assert seguir.apply_to_mask(clip, puntos) == len(puntos) == 61
    from vortex_studio.model import animate
    assert animate.value_at(clip, "mask.x", 1.0) == pytest.approx(0.5, abs=1e-6)
    assert animate.value_at(clip, "mask.y", 2.0) == pytest.approx(0.6, abs=1e-6)


def test_la_velocidad_del_clip_cuenta_al_escribir_keyframes():
    clip = Clip("a.mp4", 0.0, 4.0, speed=0.5)
    puntos = seguir.samples(clip, _filas(), 0.0, 30, (320, 180), (320, 180))
    local, x, _ = puntos[-1]
    assert local == pytest.approx(4.0, abs=0.04)          # 4 s de clip = 2 s de material
    assert x == pytest.approx(0.2 + 0.3 * local * 0.5, abs=1e-3)


def test_seguir_desde_la_mitad_no_borra_los_keyframes_de_antes():
    clip = Clip("a.mp4", 0.0, 2.0)
    clip.anim["mask.x"] = [[0.0, 0.9], [0.5, 0.8]]
    puntos = seguir.samples(clip, _filas(), 1.0, 30, (320, 180), (320, 180))
    seguir.apply_to_mask(clip, puntos)
    assert clip.anim["mask.x"][:2] == [[0.0, 0.9], [0.5, 0.8]]
    assert clip.anim["mask.x"][2][0] == pytest.approx(1.0)


def test_un_texto_sigue_con_la_distancia_que_tenia():
    from vortex_studio.model import animate

    clip = Clip("a.mp4", 2.0, 2.0)
    titulo = Title(start=1.0, duration=4.0, x=0.7, y=0.2)
    puntos = seguir.samples(clip, _filas(), 0.0, 30, (320, 180), (320, 180))
    assert seguir.apply_to_item(titulo, clip, puntos) == 61
    # En el segundo 3 de la secuencia el objeto avanzó 0.3 en x.
    assert animate.value_at(titulo, "x", 2.0) == pytest.approx(1.0, abs=1e-3)
    assert animate.value_at(titulo, "y", 2.0) == pytest.approx(0.3, abs=1e-3)


def test_sin_seguimiento_no_se_escribe_nada():
    clip = Clip("a.mp4", 0.0, 2.0)
    vacio = np.zeros((0, 4))
    assert seguir.samples(clip, vacio, 0.0, 30, (320, 180), (320, 180)) == []
    assert seguir.apply_to_mask(clip, []) == 0
    assert seguir.apply_to_item(Title(0, 2), clip, []) == 0
    assert clip.anim == {}


# --- ventana ------------------------------------------------------------------------------------

def _ventana_con_pelota(ventana, pelota):
    ventana.place_media(pelota)
    clip = ventana.sequence.track_named("V1").clips[0]
    clip.mask.shape = "Círculo"
    clip.mask.x, clip.mask.y = 80 / 320, 60 / 180
    clip.mask.width, clip.mask.height = 30 / 320, 30 / 180
    ventana.timeline.select(clip)
    ventana._scrubbed(0.0)
    return clip


def test_la_ventana_hace_que_la_mascara_siga_al_objeto(ventana, pelota):
    from vortex_studio.model import animate

    clip = _ventana_con_pelota(ventana, pelota)
    assert ventana.track_with_mask("mascara") > 50
    for t in (0.5, 1.0, 1.9):
        assert (animate.value_at(clip, "mask.x", t), animate.value_at(clip, "mask.y", t)) == \
            pytest.approx(_esperado(t), abs=0.015)


def test_la_ventana_hace_que_el_texto_siga_y_se_deshace(ventana, pelota):
    clip = _ventana_con_pelota(ventana, pelota)
    ventana.add_title()
    titulo = ventana.sequence.text_tracks()[0].clips[0]
    ventana.timeline.select(clip)
    assert ventana.track_with_mask("texto") > 50
    assert "x" in titulo.anim
    ventana.undo()
    assert "x" not in ventana.sequence.text_tracks()[0].clips[0].anim


def test_seguir_sin_mascara_o_bloqueado_avisa(ventana, pelota):
    clip = _ventana_con_pelota(ventana, pelota)
    clip.mask.shape = "Ninguna"
    assert ventana.track_with_mask("mascara") == 0
    assert "máscara" in ventana.statusBar().currentMessage()
    clip.mask.shape = "Círculo"
    ventana.sequence.track_named("V1").locked = True
    assert ventana.track_with_mask("mascara") == 0
    assert clip.anim.get("mask.x") is None
