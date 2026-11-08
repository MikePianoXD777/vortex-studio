"""Efectos de capa, texto y formas."""

from __future__ import annotations

import numpy as np
import pytest
from ayuda_photo import solido

from vortex_studio.photo.document import Effects, Glow, Layer, Outline, Shadow, Transform
from vortex_studio.photo.effects import apply_effects, dilate
from vortex_studio.photo.shapes import render_shape
from vortex_studio.photo.text import render_text, text_height


def cuadro(n=20, color=(255, 0, 0, 255)):
    return solido(n, n, color)


# --- efectos -----------------------------------------------------------------------

def test_sin_efectos_devuelve_lo_mismo():
    px = cuadro()
    out, ox, oy = apply_effects(px, Effects(), 1.0)
    assert out is px and (ox, oy) == (0, 0)


def test_sombra_crece_lo_necesario_y_cae_donde_dice():
    px = cuadro(20)
    out, ox, oy = apply_effects(px, Effects(shadow=Shadow(True, "#000000", 1.0, 0.0, 10, 6)), 1.0)
    h, w = out.shape[:2]
    assert w >= 30 and h >= 26
    # el original está intacto en su lugar
    assert np.array_equal(out[oy:oy + 20, ox:ox + 20], px)
    # sombra a la derecha y abajo, nada a la izquierda ni arriba
    assert out[oy + 25, ox + 22, 3] > 200        # debajo-derecha, en la sombra
    assert out[oy + 10, ox - 3, 3] == 0 if ox >= 3 else True
    assert out[oy - 1, ox + 10, 3] == 0 if oy >= 1 else True
    assert out[oy + 10, ox + 25, :3].tolist() == [0, 0, 0]


def test_sombra_desenfocada_se_degrada():
    out, ox, oy = apply_effects(cuadro(20), Effects(shadow=Shadow(True, "#000000", 1.0, 16.0, 0, 0)), 1.0)
    fila = out[oy + 10, ox + 20:, 3].astype(int)
    assert fila[0] > fila[6] > fila[12] >= 0
    assert fila[0] < 255


def test_sombra_con_opacidad():
    out, ox, oy = apply_effects(cuadro(20), Effects(shadow=Shadow(True, "#000000", 0.5, 0.0, 0, 10)), 1.0)
    a = out[oy + 25, ox + 10, 3]
    assert 115 <= a <= 140


def test_contorno_es_un_anillo_del_ancho_pedido():
    out, ox, oy = apply_effects(cuadro(20), Effects(outline=Outline(True, "#00ff00", 5.0)), 1.0)
    fila = out[oy + 10]
    assert fila[ox - 3].tolist() == [0, 255, 0, 255] or (fila[ox - 3, 1] > 240 and fila[ox - 3, 3] > 240)
    assert fila[ox - 8, 3] == 0
    assert np.array_equal(out[oy:oy + 20, ox:ox + 20], cuadro(20))
    # redondeado en las esquinas: el punto a 4,5 px en diagonal queda fuera del disco de 5
    assert out[oy - 4, ox - 4, 3] < 128


def test_contorno_menos_de_un_pixel_y_cero():
    for ancho in (0.0, 0.3, 1.0):
        out, ox, oy = apply_effects(cuadro(10), Effects(outline=Outline(True, "#ffffff", ancho)), 1.0)
        assert out.shape[0] >= 10


def test_brillo_exterior_baja_con_la_distancia():
    out, ox, oy = apply_effects(cuadro(20), Effects(glow=Glow(True, "#ffff00", 1.0, 20.0)), 1.0)
    fila = out[oy + 10, ox + 20:, 3].astype(int)
    assert fila[1] > 100 and fila[1] > fila[8] > fila[16] >= 0
    assert out[oy + 10, ox + 21, 0] > 200 and out[oy + 10, ox + 21, 2] < 50     # amarillo


def test_efectos_a_otra_escala_son_proporcionales():
    e = Effects(outline=Outline(True, "#ffffff", 10.0))
    _, ox1, _ = apply_effects(cuadro(20), e, 1.0)
    _, ox2, _ = apply_effects(cuadro(10), e, 0.5)
    assert ox1 == pytest.approx(ox2 * 2, abs=3)


def test_efectos_sobre_imagen_transparente_y_de_un_pixel():
    e = Effects(shadow=Shadow(True), outline=Outline(True), glow=Glow(True))
    out, ox, oy = apply_effects(np.zeros((8, 8, 4), np.uint8), e, 1.0)
    assert out[..., 3].max() == 0
    out, ox, oy = apply_effects(solido(1, 1, (255, 0, 0, 255)), e, 1.0)
    assert out.shape[0] > 1 and out[oy, ox].tolist() == [255, 0, 0, 255]


def test_efectos_con_escala_minuscula_no_truena():
    e = Effects(shadow=Shadow(True), outline=Outline(True), glow=Glow(True))
    out, _, _ = apply_effects(cuadro(4), e, 0.01)
    assert out.ndim == 3


def test_dilatacion_es_aproximadamente_un_disco():
    a = np.zeros((41, 41), np.float32)
    a[20, 20] = 1.0
    d = dilate(a, 8.0)
    assert d[20, 20 + 7] > 0.9 and d[20 + 7, 20] > 0.9
    assert d[20, 20 + 11] < 0.1
    assert d[20 + 8, 20 + 8] < 0.2                  # la diagonal a 11,3 px queda fuera de un disco de 8


# --- texto ---------------------------------------------------------------------------

def capa_texto(texto="Hola", **kw):
    t = kw.pop("transform", Transform(0, 0, 300, 100))
    return Layer(kind="text", text=texto, transform=t, color=kw.pop("color", "#ff0000"), **kw)


def tinta(px):
    ys, xs = np.nonzero(px[..., 3] > 40)
    return (xs.min(), xs.max(), ys.min(), ys.max()) if len(xs) else None


def test_texto_tiene_el_tamano_de_la_caja_y_su_color():
    c = capa_texto("Hola", font_size=40)
    px = render_text(c, 1.0)
    assert px.shape == (100, 300, 4)
    pintado = px[px[..., 3] == 255]
    assert len(pintado) > 50 and (pintado[:, 0] == 255).all() and (pintado[:, 1] == 0).all()


def test_texto_a_media_escala_mide_la_mitad():
    c = capa_texto("Hola", font_size=40)
    assert render_text(c, 0.5).shape == (50, 150, 4)
    a, b = tinta(render_text(c, 1.0)), tinta(render_text(c, 0.5))
    assert (b[1] - b[0]) == pytest.approx((a[1] - a[0]) / 2, abs=3)


def test_texto_vacio_es_transparente():
    assert render_text(capa_texto(""), 1.0)[..., 3].max() == 0


def test_ajuste_de_linea_al_ancho_de_la_caja():
    largo = "uno dos tres cuatro cinco seis siete ocho nueve diez once doce"
    angosto = capa_texto(largo, font_size=30, transform=Transform(0, 0, 150, 50))
    ancho = capa_texto(largo, font_size=30, transform=Transform(0, 0, 2000, 50))
    assert text_height(angosto) >= 3 * 30 * 1.2 - 1
    assert text_height(ancho) == pytest.approx(30 * 1.2, abs=1)
    px = render_text(Layer(**{**angosto.__dict__, "transform": Transform(0, 0, 150, 400)}), 1.0)
    x0, x1, _, _ = tinta(px)
    assert x1 <= 150                                  # nada se sale de la caja


def test_una_palabra_larguisima_se_parte_en_vez_de_salirse():
    c = capa_texto("A" * 60, font_size=30, transform=Transform(0, 0, 120, 50))
    assert text_height(c) > 30 * 1.2 * 2


def test_el_corte_de_lineas_no_depende_de_la_escala():
    largo = "uno dos tres cuatro cinco seis siete ocho nueve diez"
    c = capa_texto(largo, font_size=24, transform=Transform(0, 0, 200, 300))
    alto = text_height(c)
    for s in (0.25, 1.0, 2.0):
        px = render_text(c, s)
        filas = np.nonzero(px[..., 3].max(axis=1) > 40)[0]
        assert filas.max() / s <= alto + 2


def test_saltos_de_linea_y_lineas_vacias():
    c = capa_texto("a\n\nb", font_size=20)
    assert text_height(c) == pytest.approx(3 * 20 * 1.2, abs=1)


def test_interlineado_cambia_la_altura():
    a = text_height(capa_texto("a\nb", font_size=20, line_height=1.0))
    b = text_height(capa_texto("a\nb", font_size=20, line_height=2.0))
    assert b == pytest.approx(2 * a, abs=1)


def test_tamano_mayor_ocupa_mas():
    a = tinta(render_text(capa_texto("Hola", font_size=20), 1.0))
    b = tinta(render_text(capa_texto("Hola", font_size=60), 1.0))
    assert (b[1] - b[0]) > 2 * (a[1] - a[0])


def test_negrita_y_espaciado_ensanchan_y_mayusculas_cambian():
    base = tinta(render_text(capa_texto("Hola mundo", font_size=30), 1.0))
    neg = tinta(render_text(capa_texto("Hola mundo", font_size=30, bold=True), 1.0))
    esp = tinta(render_text(capa_texto("Hola mundo", font_size=30, letter_spacing=8), 1.0))
    mayus = render_text(capa_texto("Hola mundo", font_size=30, uppercase=True), 1.0)
    minus = render_text(capa_texto("HOLA MUNDO", font_size=30), 1.0)
    assert (neg[1] - neg[0]) >= (base[1] - base[0])
    assert (esp[1] - esp[0]) > (base[1] - base[0]) + 40
    assert np.array_equal(mayus, minus)


def test_cursiva_y_subrayado_modifican_el_dibujo():
    base = render_text(capa_texto("Hola", font_size=30), 1.0)
    assert not np.array_equal(base, render_text(capa_texto("Hola", font_size=30, italic=True), 1.0))
    sub = render_text(capa_texto("Hola", font_size=30, underline=True), 1.0)
    assert (sub[..., 3] > 40).sum() > (base[..., 3] > 40).sum()


def test_alineacion():
    izq = tinta(render_text(capa_texto("Hola", font_size=30, align="left"), 1.0))
    cen = tinta(render_text(capa_texto("Hola", font_size=30, align="center"), 1.0))
    der = tinta(render_text(capa_texto("Hola", font_size=30, align="right"), 1.0))
    assert izq[0] < 8
    assert 100 < cen[0] < 200
    assert der[1] > 285 and izq[0] < cen[0] < der[0]


def test_fuente_que_no_existe_usa_la_del_sistema():
    c = capa_texto("Hola", font_family="Fuente Inventada 123", font_size=30)
    assert render_text(c, 1.0)[..., 3].max() == 255
    assert text_height(c) > 0


def test_texto_con_color_translucido_y_nombre():
    for col in ("#80ff0000", "red", "no-es-color"):
        assert render_text(capa_texto("Hola", color=col, font_size=30), 1.0).shape == (100, 300, 4)


def test_texto_cajas_diminutas_y_tamanos_raros():
    for tr, fs in ((Transform(0, 0, 1, 1), 40), (Transform(0, 0, 300, 100), 0.1), (Transform(0, 0, 300, 100), 0)):
        assert render_text(capa_texto("Hola", font_size=fs, transform=tr), 1.0).ndim == 3
    assert render_text(capa_texto("Hola", font_size=30), 0.01).shape == (1, 3, 4)


def test_caracteres_especiales_y_emoji_no_truenan():
    c = capa_texto("¡Ñandú! 日本語 😀 \t", font_size=30)
    assert render_text(c, 1.0).shape == (100, 300, 4)


# --- formas -----------------------------------------------------------------------------

def forma(nombre, w=60, h=60, **kw):
    return Layer(kind="shape", shape=nombre, transform=Transform(0, 0, w, h), **kw)


@pytest.mark.parametrize("nombre", ["rect", "ellipse", "triangle", "star", "line", "arrow", "heart"])
def test_cada_forma_dibuja_y_cabe_en_su_caja(nombre):
    px = render_shape(forma(nombre, 80, 50, fill="#ff0000", stroke="#00ff00", stroke_width=4), 1.0)
    assert px.shape == (50, 80, 4)
    assert (px[..., 3] > 200).sum() > 30


def test_rectangulo_relleno_y_esquinas_redondeadas():
    px = render_shape(forma("rect", fill="#ff0000"), 1.0)
    assert px[0, 0].tolist() == [255, 0, 0, 255] and px[30, 30].tolist() == [255, 0, 0, 255]
    red = render_shape(forma("rect", fill="#ff0000", corner_radius=20), 1.0)
    assert red[0, 0, 3] == 0 and red[30, 30, 3] == 255 and red[30, 0, 3] == 255
    enorme = render_shape(forma("rect", fill="#ff0000", corner_radius=9999), 1.0)
    assert enorme[0, 0, 3] == 0 and enorme[30, 30, 3] == 255


def test_elipse_deja_las_esquinas_vacias():
    px = render_shape(forma("ellipse", fill="#ff0000"), 1.0)
    assert px[0, 0, 3] == 0 and px[30, 30, 3] == 255 and px[30, 1, 3] > 100


def test_borde_se_dibuja_dentro_de_la_caja():
    px = render_shape(forma("rect", fill="#ff0000", stroke="#0000ff", stroke_width=6), 1.0)
    assert px[30, 1].tolist() == [0, 0, 255, 255]
    assert px[30, 30].tolist() == [255, 0, 0, 255]


def test_sin_relleno_el_centro_queda_vacio():
    px = render_shape(forma("rect", fill=None, stroke="#0000ff", stroke_width=4), 1.0)
    assert px[30, 30, 3] == 0 and px[30, 1, 3] == 255


def test_sin_relleno_ni_borde_es_transparente():
    assert render_shape(forma("star", fill=None), 1.0)[..., 3].max() == 0


def test_borde_sin_grosor_no_dibuja_borde():
    px = render_shape(forma("rect", fill="#ff0000", stroke="#0000ff", stroke_width=0), 1.0)
    assert px[0, 0].tolist() == [255, 0, 0, 255]


def test_linea_horizontal_y_flecha():
    px = render_shape(forma("line", 80, 20, stroke="#00ff00", stroke_width=4), 1.0)
    assert px[10, 40, 3] == 255 and px[0, 40, 3] == 0 and px[19, 40, 3] == 0
    f = render_shape(forma("arrow", 80, 30, stroke="#00ff00", stroke_width=4), 1.0)
    assert (f[..., 3] > 0).sum() > (px[..., 3] > 0).sum() * 0.5
    sin_estilo = render_shape(forma("line", 80, 20), 1.0)       # sin borde usa el relleno
    assert sin_estilo[10, 40, 3] > 100


def test_triangulo_y_estrella_son_simetricos_y_no_llenan_la_caja():
    for n in ("triangle", "star", "heart"):
        px = render_shape(forma(n, fill="#ff0000"), 1.0)
        a = px[..., 3].astype(int)
        assert abs(a[:, :30].sum() - a[:, 30:].sum()) < 0.06 * a.sum()
        assert a.sum() < 0.9 * 60 * 60 * 255


def test_formas_a_otra_escala():
    capa = forma("ellipse", fill="#ff0000")
    assert render_shape(capa, 0.5).shape == (30, 30, 4)
    assert render_shape(capa, 0.01).shape == (1, 1, 4)
    assert render_shape(forma("rect", 1, 1, fill="#fff"), 1.0).shape == (1, 1, 4)


def test_forma_desconocida_se_dibuja_como_rectangulo():
    assert render_shape(forma("hexagono", fill="#ff0000"), 1.0)[30, 30, 3] == 255
