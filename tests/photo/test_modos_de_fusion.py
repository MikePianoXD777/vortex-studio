"""Modos de fusión contra un cálculo de referencia escrito aparte (escalar, a
la letra del estándar W3C) y composición con alfa."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from vortex_studio.photo.blend import composite
from vortex_studio.photo.document import BLENDS


# --- referencia escalar --------------------------------------------------------

def _lum(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _clip(c):
    l, n, x = _lum(c), min(c), max(c)
    if n < 0:
        c = [l + (v - l) * l / (l - n) for v in c]
    if x > 1:
        c = [l + (v - l) * (1 - l) / (x - l) for v in c]
    return c


def _setlum(c, l):
    d = l - _lum(c)
    return _clip([v + d for v in c])


def _sat(c):
    return max(c) - min(c)


def _setsat(c, s):
    idx = sorted(range(3), key=lambda i: c[i])
    mn, md, mx = idx
    out = [0.0, 0.0, 0.0]
    if c[mx] > c[mn]:
        out[md] = (c[md] - c[mn]) * s / (c[mx] - c[mn])
        out[mx] = s
    return out


def _sep(modo, b, s):
    if modo == "Multiplicar":
        return b * s
    if modo == "Oscurecer":
        return min(b, s)
    if modo == "Aclarar":
        return max(b, s)
    if modo == "Trama":
        return b + s - b * s
    if modo == "Diferencia":
        return abs(b - s)
    if modo == "Exclusión":
        return b + s - 2 * b * s
    if modo == "Subexponer color":
        if b == 1:
            return 1.0
        if s == 0:
            return 0.0
        return 1 - min(1, (1 - b) / s)
    if modo == "Sobreexponer color":
        if b == 0:
            return 0.0
        if s == 1:
            return 1.0
        return min(1, b / (1 - s))
    if modo == "Luz fuerte":
        return b * 2 * s if s <= 0.5 else (b + (2 * s - 1) - b * (2 * s - 1))
    if modo == "Superponer":
        return _sep("Luz fuerte", s, b)
    if modo == "Luz suave":
        if s <= 0.5:
            return b - (1 - 2 * s) * b * (1 - b)
        d = ((16 * b - 12) * b + 4) * b if b <= 0.25 else math.sqrt(b)
        return b + (2 * s - 1) * (d - b)
    raise AssertionError(modo)


def referencia(modo, cb, cs):
    cb, cs = [v / 255 for v in cb], [v / 255 for v in cs]
    if modo == "Normal":
        r = cs
    elif modo == "Tono":
        r = _setlum(_setsat(cs, _sat(cb)), _lum(cb))
    elif modo == "Saturación":
        r = _setlum(_setsat(cb, _sat(cs)), _lum(cb))
    elif modo == "Color":
        r = _setlum(cs, _lum(cb))
    elif modo == "Luminosidad":
        r = _setlum(cb, _lum(cs))
    else:
        r = [_sep(modo, b, s) for b, s in zip(cb, cs)]
    return [min(255, max(0, round(v * 255))) for v in r]


MUESTRAS = [(0, 0, 0), (255, 255, 255), (128, 128, 128), (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (200, 100, 50), (30, 160, 220), (90, 90, 200), (250, 240, 10), (64, 192, 128), (10, 10, 10)]


@pytest.mark.parametrize("modo", BLENDS)
def test_modo_de_fusion_coincide_con_la_referencia(modo):
    pares = list(itertools.product(MUESTRAS, MUESTRAS))
    dst = np.zeros((1, len(pares), 4), np.uint8)
    src = np.zeros_like(dst)
    for i, (cb, cs) in enumerate(pares):
        dst[0, i] = (*cb, 255)
        src[0, i] = (*cs, 255)
    composite(dst, src, modo, 1.0, 0, 0)
    for i, (cb, cs) in enumerate(pares):
        esperado = referencia(modo, cb, cs)
        obtenido = dst[0, i, :3].tolist()
        assert max(abs(a - b) for a, b in zip(esperado, obtenido)) <= 2, (modo, cb, cs, esperado, obtenido)
        assert dst[0, i, 3] == 255


def test_hay_16_modos_y_el_normal_copia_la_capa():
    assert len(BLENDS) == 16
    dst = np.full((2, 2, 4), 50, np.uint8)
    src = np.full((2, 2, 4), 200, np.uint8)
    src[..., 3] = 255
    composite(dst, src, "Normal", 1.0, 0, 0)
    assert np.array_equal(dst, src)


def test_multiplicar_con_blanco_no_cambia_y_con_negro_da_negro():
    dst = np.full((1, 2, 4), (120, 60, 200, 255), np.uint8)
    src = np.array([[[255, 255, 255, 255], [0, 0, 0, 255]]], np.uint8)
    composite(dst, src, "Multiplicar", 1.0, 0, 0)
    assert dst[0, 0, :3].tolist() == [120, 60, 200]
    assert dst[0, 1, :3].tolist() == [0, 0, 0]


def test_opacidad_mezcla_proporcionalmente():
    dst = np.full((1, 1, 4), (0, 0, 0, 255), np.uint8)
    src = np.full((1, 1, 4), (200, 100, 50, 255), np.uint8)
    composite(dst, src, "Normal", 0.5, 0, 0)
    assert np.abs(dst[0, 0, :3].astype(int) - (100, 50, 25)).max() <= 1


def test_opacidad_cero_no_cambia_nada():
    dst = np.full((4, 4, 4), 77, np.uint8)
    copia = dst.copy()
    composite(dst, np.full((4, 4, 4), 255, np.uint8), "Normal", 0.0, 0, 0)
    assert np.array_equal(dst, copia)


def test_alfa_de_la_capa_sobre_fondo_opaco():
    dst = np.full((1, 1, 4), (0, 0, 0, 255), np.uint8)
    src = np.full((1, 1, 4), (255, 255, 255, 64), np.uint8)
    composite(dst, src, "Normal", 1.0, 0, 0)
    assert abs(int(dst[0, 0, 0]) - 64) <= 1 and dst[0, 0, 3] == 255


def test_sin_bordes_oscuros_sobre_fondo_transparente():
    # Blanco a medio alfa sobre nada debe quedar BLANCO a medio alfa. Un
    # compositor mal hecho mezcla con el negro transparente y deja gris.
    dst = np.zeros((1, 1, 4), np.uint8)
    src = np.full((1, 1, 4), (255, 255, 255, 128), np.uint8)
    composite(dst, src, "Normal", 1.0, 0, 0)
    assert dst[0, 0, :3].tolist() == [255, 255, 255]
    assert abs(int(dst[0, 0, 3]) - 128) <= 1


def test_alfa_resultante_es_la_union():
    dst = np.full((1, 1, 4), (10, 20, 30, 128), np.uint8)
    src = np.full((1, 1, 4), (200, 100, 50, 128), np.uint8)
    composite(dst, src, "Normal", 1.0, 0, 0)
    assert abs(int(dst[0, 0, 3]) - round(255 * (0.5 + 0.5 * 0.5))) <= 1
    # el color queda entre los dos, más cerca de la capa de arriba
    assert 10 < dst[0, 0, 0] < 200 and dst[0, 0, 0] > 105


def test_fusion_sobre_fondo_transparente_se_ve_como_normal():
    dst = np.zeros((1, 1, 4), np.uint8)
    src = np.full((1, 1, 4), (30, 90, 200, 255), np.uint8)
    composite(dst, src, "Multiplicar", 1.0, 0, 0)
    assert dst[0, 0].tolist() == [30, 90, 200, 255]


def test_la_capa_puede_salirse_por_todos_lados():
    dst = np.zeros((10, 10, 4), np.uint8)
    src = np.full((6, 6, 4), 255, np.uint8)
    composite(dst, src, "Normal", 1.0, -3, -3)
    assert dst[:3, :3, 3].min() == 255 and dst[3:, :, 3].max() == 0
    dst[:] = 0
    composite(dst, src, "Normal", 1.0, 7, 8)
    assert dst[8:, 7:, 3].min() == 255 and dst[:8].max() == 0
    dst[:] = 0
    composite(dst, src, "Normal", 1.0, 100, 100)
    composite(dst, src, "Normal", 1.0, -100, 0)
    composite(dst, src, "Normal", 1.0, 0, -100)
    assert dst.max() == 0


def test_capa_totalmente_transparente_no_toca_el_fondo():
    dst = np.full((4, 4, 4), 90, np.uint8)
    copia = dst.copy()
    composite(dst, np.zeros((4, 4, 4), np.uint8), "Multiplicar", 1.0, 0, 0)
    assert np.array_equal(dst, copia)


def test_modo_desconocido_se_trata_como_normal():
    dst = np.full((1, 1, 4), 10, np.uint8)
    dst[..., 3] = 255
    composite(dst, np.full((1, 1, 4), (200, 200, 200, 255), np.uint8), "Inventado", 1.0, 0, 0)
    assert dst[0, 0, 0] == 200


def test_composicion_vacia_o_de_cero_pixeles():
    dst = np.zeros((0, 0, 4), np.uint8)
    composite(dst, np.full((2, 2, 4), 255, np.uint8), "Normal", 1.0, 0, 0)
    composite(np.zeros((3, 3, 4), np.uint8), np.zeros((0, 5, 4), np.uint8), "Normal", 1.0, 0, 0)
