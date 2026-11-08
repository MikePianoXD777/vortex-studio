"""Pincel, borrador, máscara, clonar, varita mágica y quitar fondo."""

from __future__ import annotations

import numpy as np
import pytest
from ayuda_photo import colorido, ruido, solido

from vortex_studio.photo.paint import (Brush, clone, magic_wand, remove_background, stroke,
                                       stroke_mask)


def blanco(w=100, h=100):
    return solido(w, h, (255, 255, 255, 255))


def rojo_en(px):
    return (px[..., 1] < 128) & (px[..., 0] > 128)


def test_trazo_pinta_y_no_toca_el_original():
    px = blanco()
    copia = px.copy()
    out = stroke(px, [(50, 50, 1.0)], Brush(size=20, color="#ff0000"))
    assert np.array_equal(px, copia)
    assert out[50, 50].tolist() == [255, 0, 0, 255]
    assert out[50, 5].tolist() == [255, 255, 255, 255]


def test_el_tamano_del_pincel_es_su_diametro():
    out = stroke(blanco(), [(50.5, 50.5, 1.0)], Brush(size=20, hardness=1.0, color="#ff0000"))
    ys, xs = np.nonzero(rojo_en(out))
    assert xs.max() - xs.min() + 1 == pytest.approx(20, abs=2)
    assert ys.max() - ys.min() + 1 == pytest.approx(20, abs=2)
    assert abs(xs.mean() - 50) < 1


def test_trazo_rapido_no_deja_huecos():
    # El mouse salta 200 px de golpe: la línea tiene que salir continua.
    out = stroke(blanco(220, 60), [(10, 30, 1.0), (210, 30, 1.0)], Brush(size=8, hardness=1.0, color="#ff0000"))
    assert rojo_en(out)[30, 8:213].all()
    # y de grosor parejo en toda su longitud
    grosor = rojo_en(out)[:, 20:200].sum(axis=0)
    assert grosor.min() >= 7 and grosor.max() <= 10


def test_trazo_diagonal_continuo():
    out = stroke(blanco(), [(5, 5, 1.0), (95, 95, 1.0)], Brush(size=6, hardness=1.0, color="#ff0000"))
    m = rojo_en(out)
    for i in range(6, 94):
        assert m[i, i], i


def test_trazo_con_muchos_puntos_y_puntos_repetidos():
    pts = [(10 + i, 50, 1.0) for i in range(0, 80, 2)] + [(90, 50, 1.0)] * 5
    out = stroke(blanco(), pts, Brush(size=6, hardness=1.0, color="#ff0000"))
    assert rojo_en(out)[50, 10:90].all()


def test_dureza_suave_degrada_el_borde_y_dura_no():
    suave = stroke(blanco(), [(50.5, 50.5, 1.0)], Brush(size=40, hardness=0.0, color="#000000"))
    dura = stroke(blanco(), [(50.5, 50.5, 1.0)], Brush(size=40, hardness=1.0, color="#000000"))
    fs, fd = suave[50, 50:72, 0].astype(int), dura[50, 50:72, 0].astype(int)
    intermedios = lambda f: ((f > 20) & (f < 235)).sum()
    assert intermedios(fs) >= 8 > intermedios(fd)
    assert np.all(np.diff(fs) >= -1)                        # baja monótona del centro al borde


def test_presion_cambia_el_grosor():
    pesado = stroke(blanco(), [(20, 50, 1.0), (80, 50, 1.0)], Brush(size=30, hardness=1.0, color="#ff0000"))
    ligero = stroke(blanco(), [(20, 50, 0.2), (80, 50, 0.2)], Brush(size=30, hardness=1.0, color="#ff0000"))
    assert rojo_en(pesado).sum() > 2 * rojo_en(ligero).sum()
    # presión que varía a lo largo del trazo: más grueso al final
    rampa = stroke(blanco(), [(10, 50, 0.1), (90, 50, 1.0)], Brush(size=30, hardness=1.0, color="#ff0000"))
    g = rojo_en(rampa).sum(axis=0)
    assert g[85] > g[15]


def test_opacidad_es_el_tope_del_trazo_sin_acumularse():
    # Un trazo que se cruza a sí mismo no debe oscurecerse más que la opacidad.
    pts = [(20, 50, 1.0), (80, 50, 1.0), (20, 50, 1.0), (80, 50, 1.0)]
    out = stroke(blanco(), pts, Brush(size=10, hardness=1.0, opacity=0.5, color="#000000"))
    assert abs(int(out[50, 50, 0]) - 128) <= 2


def test_color_con_alfa_y_nombre_de_color():
    out = stroke(blanco(), [(50, 50, 1.0)], Brush(size=20, color="red"))
    assert out[50, 50].tolist() == [255, 0, 0, 255]
    out = stroke(blanco(), [(50, 50, 1.0)], Brush(size=20, hardness=1.0, color="#80000000"))
    assert abs(int(out[50, 50, 0]) - 127) <= 2
    out = stroke(blanco(), [(50, 50, 1.0)], Brush(size=20, color="roto-roto"))
    assert out[50, 50, 3] == 255


def test_pintar_sobre_transparente_conserva_el_color_puro():
    out = stroke(np.zeros((40, 40, 4), np.uint8), [(20, 20, 1.0)], Brush(size=16, hardness=0.3, color="#336699"))
    borde = out[(out[..., 3] > 5) & (out[..., 3] < 250)]
    assert len(borde) > 5 and (np.abs(borde[:, :3].astype(int) - (51, 102, 153)).max() <= 1)


def test_borrador_baja_el_alfa():
    px = blanco()
    out = stroke(px, [(50, 50, 1.0)], Brush(size=30, hardness=1.0, mode="erase"))
    assert out[50, 50, 3] == 0 and out[5, 5, 3] == 255
    medio = stroke(px, [(50, 50, 1.0)], Brush(size=30, hardness=1.0, opacity=0.5, mode="erase"))
    assert abs(int(medio[50, 50, 3]) - 128) <= 2


def test_trazo_fuera_del_lienzo_y_casos_raros():
    px = blanco(50, 50)
    assert np.array_equal(stroke(px, [], Brush()), px)
    assert np.array_equal(stroke(px, [(500, 500, 1.0)], Brush(size=10)), px)
    assert stroke(px, [(-3, -3, 1.0), (60, 60, 1.0)], Brush(size=10, color="#ff0000"))[0, 0, 1] == 0
    assert stroke(solido(1, 1), [(0, 0, 1.0)], Brush(size=10)).shape == (1, 1, 4)
    assert stroke(px, [(10, 10, 1.0)], Brush(size=0)).shape == px.shape
    assert stroke(px, [(10, 10)], Brush(size=6, color="#ff0000"))[10, 10, 1] == 0       # punto sin presión


def test_trazo_larguisimo_se_hace_rapido():
    import time
    t = time.time()
    stroke(blanco(1000, 1000), [(0, 0, 1.0), (999, 999, 1.0), (0, 999, 1.0), (999, 0, 1.0)], Brush(size=30))
    assert time.time() - t < 3


def test_pintar_solo_toca_el_rectangulo_del_trazo():
    px = ruido(200, 200)
    out = stroke(px, [(100, 100, 1.0)], Brush(size=10, color="#ff0000"))
    cambiado = np.any(out != px, axis=2)
    ys, xs = np.nonzero(cambiado)
    assert ys.min() >= 93 and ys.max() <= 107 and xs.min() >= 93 and xs.max() <= 107


def test_mascara_revelar_y_ocultar():
    m = np.zeros((60, 60), np.uint8)
    rev = stroke_mask(m, [(30, 30, 1.0)], Brush(size=20, hardness=1.0, mode="paint"))
    assert rev[30, 30] == 255 and rev[2, 2] == 0 and m.max() == 0
    ocu = stroke_mask(np.full((60, 60), 255, np.uint8), [(30, 30, 1.0)], Brush(size=20, hardness=1.0, mode="erase"))
    assert ocu[30, 30] == 0 and ocu[2, 2] == 255
    medio = stroke_mask(m, [(30, 30, 1.0)], Brush(size=20, hardness=1.0, opacity=0.5))
    assert abs(int(medio[30, 30]) - 128) <= 1
    suave = stroke_mask(m, [(30, 30, 1.0)], Brush(size=30, hardness=0.0))
    assert 0 < suave[30, 42] < 255 and suave.dtype == np.uint8


def test_mascara_trazo_continuo_y_vacio():
    m = np.zeros((20, 200), np.uint8)
    out = stroke_mask(m, [(5, 10, 1.0), (195, 10, 1.0)], Brush(size=6, hardness=1.0))
    assert (out[10, 5:196] == 255).all()
    assert np.array_equal(stroke_mask(m, [], Brush()), m)


def test_clonar_copia_de_donde_dice_el_desplazamiento():
    px = blanco()
    px[20:30, 20:30] = (255, 0, 0, 255)
    out = clone(px, [(75, 75, 1.0)], Brush(size=14, hardness=1.0), offset=(-50, -50))
    assert out[75, 75].tolist() == [255, 0, 0, 255]
    assert out[75, 90].tolist() == [255, 255, 255, 255]
    assert px[75, 75].tolist() == [255, 255, 255, 255]


def test_clonar_toma_siempre_del_original_sin_arrastrar():
    px = blanco(100, 20)
    px[:, :10] = (255, 0, 0, 255)
    # trazo con desplazamiento corto sobre el propio origen: sin arrastre el rojo avanza solo un desplazamiento
    out = clone(px, [(x, 10, 1.0) for x in range(10, 90, 2)], Brush(size=6, hardness=1.0), offset=(-12, 0))
    assert out[10, 14].tolist() == [255, 0, 0, 255]
    assert out[10, 60].tolist() == [255, 255, 255, 255]


def test_clonar_con_el_origen_fuera_no_copia_nada():
    px = blanco(50, 50)
    out = clone(px, [(5, 5, 1.0)], Brush(size=8, hardness=1.0), offset=(-500, -500))
    assert np.array_equal(out, px)
    mitad = clone(px, [(2, 25, 1.0)], Brush(size=10), offset=(-3, 0))
    assert mitad.shape == px.shape


def test_clonar_conserva_la_transparencia():
    px = np.zeros((60, 60, 4), np.uint8)
    px[10:20, 10:20] = (0, 255, 0, 255)
    out = clone(px, [(40, 40, 1.0)], Brush(size=10, hardness=1.0), offset=(-25, -25))
    assert out[40, 40].tolist() == [0, 255, 0, 255] and out[40, 52, 3] == 0


# --- varita ------------------------------------------------------------------------------

def dos_cuadros():
    px = blanco(60, 30)
    px[5:15, 5:15] = (255, 0, 0, 255)
    px[5:15, 40:50] = (255, 0, 0, 255)
    return px


def test_varita_contigua_toma_solo_su_cuadro():
    m = magic_wand(dos_cuadros(), 10, 10, 10, contiguous=True)
    assert m.dtype == np.uint8 and m.shape == (30, 60)
    assert (m[5:15, 5:15] == 255).all() and m.sum() // 255 == 100


def test_varita_global_toma_todos_los_parecidos():
    m = magic_wand(dos_cuadros(), 10, 10, 10, contiguous=False)
    assert m.sum() // 255 == 200


def test_varita_en_el_fondo_toma_el_fondo():
    m = magic_wand(dos_cuadros(), 0, 0, 10)
    assert m.sum() // 255 == 60 * 30 - 200 and m[10, 10] == 0


def test_varita_tolerancia():
    px = blanco(40, 10)
    px[:, :20] = (100, 100, 100, 255)
    px[:, 20:] = (110, 110, 110, 255)
    assert magic_wand(px, 0, 0, 5).sum() // 255 == 200
    assert magic_wand(px, 0, 0, 12).sum() // 255 == 400
    assert magic_wand(px, 0, 0, 0).sum() // 255 == 200


def test_varita_sigue_un_degradado_con_tolerancia_baja_solo_hasta_cierto_punto():
    px = np.zeros((10, 256, 4), np.uint8)
    px[..., :3] = np.arange(256, dtype=np.uint8)[None, :, None]
    px[..., 3] = 255
    m = magic_wand(px, 0, 5, 20)
    assert 0 < (m[5] == 255).sum() <= 22


def test_varita_fuera_de_la_imagen_es_vacia():
    for xy in ((-1, 0), (0, -1), (60, 0), (0, 30), (999, 999)):
        assert magic_wand(dos_cuadros(), *xy).max() == 0


def test_varita_respeta_la_transparencia():
    px = np.zeros((20, 20, 4), np.uint8)
    px[5:15, 5:15] = (10, 20, 30, 255)
    px[0, 0, :3] = (255, 255, 255)                 # color escondido en un píxel transparente
    m = magic_wand(px, 1, 1, 5)
    assert m[0, 0] == 255 and m[10, 10] == 0
    assert magic_wand(px, 10, 10, 5).sum() // 255 == 100


def test_varita_no_se_cuela_en_diagonal_ni_entre_filas():
    px = blanco(10, 10)
    px[:] = (0, 0, 0, 255)
    px[0, 9] = (255, 255, 255, 255)                # esquina opuesta a la de la fila siguiente
    px[1, 0] = (255, 255, 255, 255)
    m = magic_wand(px, 0, 1, 5)
    assert m[1, 0] == 255 and m[0, 9] == 0 and m.sum() // 255 == 1
    px2 = blanco(4, 4)
    px2[:] = (0, 0, 0, 255)
    px2[0, 3] = px2[1, 0] = (255, 255, 255, 255)   # fin de una fila y comienzo de la siguiente
    assert magic_wand(px2, 3, 0, 5).sum() // 255 == 1


def test_varita_en_un_laberinto_largo_sin_recursion():
    # Un camino en serpiente de ~20 000 píxeles de largo: la inundación recursiva reventaría.
    n = 201
    px = np.zeros((n, n, 4), np.uint8)
    px[..., 3] = 255
    px[1::2, 1:-1] = 255
    for i in range(1, n - 1, 2):
        if (i // 2) % 2 == 0:
            px[i + 1, n - 2] = 255
        else:
            px[i + 1, 1] = 255
    m = magic_wand(px, 1, 1, 10)
    assert m[1, 1] == 255 and (m[n - 2, 1] == 255 or m[n - 2, n - 2] == 255)
    assert (m == 255).sum() == (px[..., 0] == 255).sum()


def test_varita_imagen_de_un_pixel():
    assert magic_wand(solido(1, 1), 0, 0).tolist() == [[255]]


# --- quitar fondo --------------------------------------------------------------------------

def figura_sobre_liso(fondo=(240, 240, 240), figura=(200, 30, 30), n=100):
    px = np.empty((n, n, 4), np.uint8)
    px[..., :3] = fondo
    px[..., 3] = 255
    yy, xx = np.mgrid[:n, :n]
    disco = (yy - n / 2) ** 2 + (xx - n / 2) ** 2 < (n * 0.3) ** 2
    px[disco, :3] = figura
    return px, disco


def test_quitar_fondo_deja_la_figura_y_borra_el_fondo():
    px, disco = figura_sobre_liso()
    m = remove_background(px)
    assert m.dtype == np.uint8 and m.shape == px.shape[:2]
    assert (m[disco & (np.hypot(*(np.mgrid[:100, :100] - 50)) < 24)] == 255).all()
    assert m[:8, :8].max() == 0 and m[-8:, -8:].max() == 0 and m[0, 50] == 0
    acierto = ((m > 127) == disco).mean()
    assert acierto > 0.98


def test_quitar_fondo_con_ruido_en_el_fondo():
    rng = np.random.default_rng(3)
    px, disco = figura_sobre_liso()
    px[..., :3] = np.clip(px[..., :3].astype(int) + rng.integers(-6, 7, (100, 100, 1)), 0, 255)
    assert ((remove_background(px) > 127) == disco).mean() > 0.95


def test_quitar_fondo_con_degradado_suave():
    px, disco = figura_sobre_liso()
    deg = np.linspace(200, 250, 100).astype(np.uint8)
    px[..., :3] = deg[:, None, None]
    px[disco, :3] = (30, 60, 200)
    assert ((remove_background(px) > 127) == disco).mean() > 0.95


def test_quitar_fondo_conserva_los_huecos_internos():
    # Una dona: el hueco del centro tiene el color del fondo pero no toca el borde → se queda.
    px, disco = figura_sobre_liso()
    yy, xx = np.mgrid[:100, :100]
    hueco = (yy - 50) ** 2 + (xx - 50) ** 2 < 10 ** 2
    px[hueco, :3] = (240, 240, 240)
    m = remove_background(px)
    assert m[50, 50] > 200 and m[0, 0] == 0


def test_quitar_fondo_borde_suave():
    px, _ = figura_sobre_liso()
    m = remove_background(px)
    assert ((m > 5) & (m < 250)).sum() > 20          # hay transición, no escalera dura


def test_quitar_fondo_imagen_ya_transparente_y_casos_chicos():
    px = np.zeros((40, 40, 4), np.uint8)
    px[10:30, 10:30] = (50, 90, 200, 255)
    m = remove_background(px)
    assert m[20, 20] == 255 and m[0, 0] == 0
    assert remove_background(solido(2, 2)).shape == (2, 2)
    assert remove_background(solido(1, 1)).tolist() == [[255]]
    todo = remove_background(solido(30, 30, (10, 200, 10, 255)))
    assert todo.max() == 0                            # todo es fondo
    assert remove_background(colorido(5, 5)).shape == (5, 5)
