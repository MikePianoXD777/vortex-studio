"""Animaciones de texto listas: lo que hace rápido a CapCut."""

import pytest

from vortex_studio.model import Title, anim_state
from vortex_studio.model.animation import (
    DEFAULT_TIME,
    IN_ANIMS,
    OUT_ANIMS,
    TEXT_ANIMS,
    AnimState,
    visible_text,
)


def titulo(**kw) -> Title:
    base = dict(start=0.0, duration=4.0, text="Hola mundo")
    base.update(kw)
    return Title(**base)


# --- el modelo ------------------------------------------------------------

def test_sin_animacion_no_pasa_nada():
    assert anim_state(titulo(), 1.0).is_neutral


def test_por_omision_un_texto_nuevo_no_esta_animado():
    """Meter animación a todo por omisión sería decidir por el usuario."""
    t = titulo()
    assert t.anim_in == "Ninguna"
    assert t.anim_out == "Ninguna"


def test_aparecer_sube_la_opacidad():
    t = titulo(anim_in="Aparecer", anim_time=1.0)
    assert anim_state(t, 0.0).opacity == pytest.approx(0.0, abs=0.02)
    assert anim_state(t, 0.5).opacity == pytest.approx(0.5, abs=0.05)
    assert anim_state(t, 1.0).opacity == pytest.approx(1.0, abs=0.02)


def test_al_terminar_la_entrada_queda_quieto():
    t = titulo(anim_in="Desde la izquierda", anim_time=0.5)
    assert anim_state(t, 2.0).is_neutral


def test_deslizar_llega_a_su_lugar():
    t = titulo(anim_in="Desde la izquierda", anim_time=1.0)
    assert anim_state(t, 0.0).dx < -0.2        # empieza fuera, a la izquierda
    assert abs(anim_state(t, 1.0).dx) < 0.01   # y termina en su lugar


def test_cada_direccion_entra_por_su_lado():
    lados = {
        "Desde la izquierda": lambda s: s.dx < -0.1,
        "Desde la derecha": lambda s: s.dx > 0.1,
        "Desde arriba": lambda s: s.dy < -0.1,
        "Desde abajo": lambda s: s.dy > 0.1,
    }
    for nombre, comprueba in lados.items():
        estado = anim_state(titulo(anim_in=nombre, anim_time=1.0), 0.0)
        assert comprueba(estado), nombre


def test_acercarse_se_pasa_de_tamano_y_regresa():
    """El sobretiro es lo que lo hace ver hecho a mano y no calculado."""
    t = titulo(anim_in="Acercarse", anim_time=1.0)
    tamanos = [anim_state(t, x / 40).scale for x in range(41)]
    assert tamanos[0] < 0.7              # arranca chico
    assert max(tamanos) > 1.0            # se pasa
    assert tamanos[-1] == pytest.approx(1.0, abs=0.02)   # y aterriza en 1


def test_la_maquina_de_escribir_va_letra_por_letra():
    t = titulo(anim_in="Escribiéndose", anim_time=1.0)
    assert anim_state(t, 0.0).chars == pytest.approx(0.0)
    assert anim_state(t, 0.5).chars == pytest.approx(0.5, abs=0.02)
    assert anim_state(t, 1.0).chars == pytest.approx(1.0)


def test_la_salida_corre_al_final():
    t = titulo(anim_out="Aparecer", anim_time=1.0)
    assert anim_state(t, 1.0).is_neutral                  # a media duración
    assert anim_state(t, 3.5).opacity < 0.7               # ya saliendo
    assert anim_state(t, 3.99).opacity < 0.05             # casi ida


def test_la_entrada_y_la_salida_conviven():
    t = titulo(anim_in="Aparecer", anim_out="Aparecer", anim_time=0.5)
    assert anim_state(t, 0.1).opacity < 0.5
    assert anim_state(t, 2.0).is_neutral
    assert anim_state(t, 3.9).opacity < 0.5


def test_si_no_caben_se_reparten_a_prorrata():
    """Encimadas, el texto nunca llegaría a estar quieto en su lugar."""
    t = titulo(duration=1.0, anim_in="Aparecer", anim_out="Aparecer",
               anim_time=3.0)
    medio = anim_state(t, 0.5)
    assert medio.opacity > 0.9          # al centro sí llega a verse completo


def test_una_animacion_desconocida_no_truena():
    """Un proyecto de una versión más nueva puede traer un nombre que no sea."""
    assert anim_state(titulo(anim_in="Voltereta cuántica"), 0.1).is_neutral


def test_tiempo_cero_no_anima():
    assert anim_state(titulo(anim_in="Aparecer", anim_time=0.0), 0.0).is_neutral


def test_todas_las_animaciones_dan_valores_sanos():
    for nombre, animacion in TEXT_ANIMS.items():
        if animacion is None:
            continue
        for paso in range(21):
            estado = animacion(paso / 20)
            assert 0.0 <= estado.opacity <= 1.0, nombre
            assert 0.0 <= estado.chars <= 1.0, nombre
            assert 0.0 < estado.scale < 3.0, nombre
            assert abs(estado.dx) < 1.0 and abs(estado.dy) < 1.0, nombre


def test_la_salida_no_ofrece_des_escribirse():
    """Des-escribirse se ve como un error, no como un efecto."""
    assert "Escribiéndose" in IN_ANIMS
    assert "Escribiéndose" not in OUT_ANIMS


# --- recorte del texto ----------------------------------------------------

def test_el_texto_se_recorta_a_la_fraccion():
    assert visible_text("abcdefgh", 0.5) == "abcd"
    assert visible_text("abcdefgh", 1.0) == "abcdefgh"
    assert visible_text("abcdefgh", 0.0) == ""


def test_se_escribe_de_corrido_entre_renglones():
    """Renglón por renglón se verían los dos a la vez, y no es eso."""
    assert visible_text("ab\ncd", 0.5) == "ab"


# --- llega a los pixeles --------------------------------------------------

def brillo(img) -> int:
    return sum(sum(img.pixelColor(x, y).getRgb()[:3])
               for y in range(0, img.height(), 4)
               for x in range(0, img.width(), 4))


def test_la_animacion_llega_al_cuadro(ventana, media):
    """Que el efecto se pinte, no solo que los números salgan bien."""
    ventana._place_video(media["mudo"])
    ventana.add_title()
    titulo_nuevo = ventana._title
    titulo_nuevo.text = "PRUEBA"
    titulo_nuevo.start = 0.0
    titulo_nuevo.duration = 3.0
    titulo_nuevo.anim_in = "Aparecer"
    titulo_nuevo.anim_time = 1.0

    ventana._seek(0.02)
    entrando = brillo(ventana.preview.current_image())
    ventana._seek(2.0)
    puesto = brillo(ventana.preview.current_image())

    assert entrando < puesto        # al entrar todavía está transparente


def test_la_maquina_de_escribir_llega_al_cuadro(ventana, media):
    ventana._place_video(media["mudo"])
    ventana.add_title()
    t = ventana._title
    t.text = "MMMMMMMMMMMMMM"
    t.start, t.duration = 0.0, 3.0
    t.anim_in, t.anim_time = "Escribiéndose", 1.0

    ventana._seek(0.1)
    poco = brillo(ventana.preview.current_image())
    ventana._seek(0.9)
    casi = brillo(ventana.preview.current_image())

    assert poco < casi              # cada vez hay más letras en pantalla


def test_sobrevive_al_guardado(ventana, media, tmp_path):
    from vortex_studio.model.serialize import load_project, save_project

    ventana._place_video(media["mudo"])
    ventana.add_title()
    ventana._title.anim_in = "Desde la izquierda"
    ventana._title.anim_out = "Alejarse"
    ventana._title.anim_time = 0.8

    destino = save_project(ventana.project, tmp_path / "p")
    vuelto = load_project(destino).active.text_tracks()[0].clips[0]

    assert vuelto.anim_in == "Desde la izquierda"
    assert vuelto.anim_out == "Alejarse"
    assert vuelto.anim_time == pytest.approx(0.8)
