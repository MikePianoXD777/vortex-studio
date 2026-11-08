"""La geometría pura del lienzo: cajas giradas, asas, escalado, giro e imán."""

import math

import pytest

from vortex_studio.photo.document import Transform
from vortex_studio.ui.photo import crop as cropmod
from vortex_studio.ui.photo import geometry as geo


def aprox(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_un_punto_gira_alrededor_del_centro():
    t = Transform(100, 100, 40, 20, rotation=90)
    x, y = geo.to_canvas(t, 20, 0)          # el borde derecho, girado 90° a favor del reloj
    assert aprox(x, 100) and aprox(y, 120)
    lx, ly = geo.to_local(t, x, y)
    assert aprox(lx, 20) and aprox(ly, 0)


def test_las_esquinas_de_una_caja_sin_girar():
    t = Transform(50, 50, 20, 10)
    assert geo.corners(t) == [(40.0, 45.0), (60.0, 45.0), (60.0, 55.0), (40.0, 55.0)]


def test_contiene_respeta_el_giro():
    t = Transform(0, 0, 100, 10, rotation=90)   # una caja alta y delgada
    assert geo.contains(t, 0, 40)
    assert not geo.contains(t, 40, 0)
    assert geo.contains(t, 7, 0, pad=3)


def test_el_envolvente_de_dos_cajas():
    a, b = Transform(10, 10, 10, 10), Transform(100, 50, 20, 20)
    assert geo.bbox([a, b]) == (5.0, 5.0, 110.0, 60.0)
    assert geo.bbox([]) is None


@pytest.mark.parametrize("asa", list(geo.HANDLES))
def test_escalar_con_el_asa_deja_fijo_el_lado_opuesto(asa):
    t = Transform(200, 200, 100, 60)
    hx, hy = geo.HANDLES[asa]
    px, py = geo.handle_points(t)[asa]
    nt = geo.resize_transform(t, asa, px + hx * 40, py + hy * 20, proportional=False)
    ax, ay = geo.handle_points(t)[{"nw": "se", "n": "s", "ne": "sw", "e": "w", "se": "nw", "s": "n",
                                   "sw": "ne", "w": "e"}[asa]]
    nax, nay = geo.handle_points(nt)[{"nw": "se", "n": "s", "ne": "sw", "e": "w", "se": "nw",
                                      "s": "n", "sw": "ne", "w": "e"}[asa]]
    assert aprox(ax, nax) and aprox(ay, nay)
    assert nt.width >= t.width and nt.height >= t.height


def test_escalar_proporcional_conserva_la_proporcion():
    t = Transform(0, 0, 100, 50)
    nt = geo.resize_transform(t, "se", 150, 40, proportional=True)
    assert aprox(nt.width / nt.height, 2.0)
    assert nt.width >= 100


def test_escalar_girado_mueve_el_asa_en_su_marco():
    t = Transform(0, 0, 100, 100, rotation=45)
    px, py = geo.handle_points(t)["se"]
    nt = geo.resize_transform(t, "se", px * 1.5, py * 1.5, proportional=True)
    assert nt.rotation == 45
    assert nt.width > 100
    # La esquina opuesta no se movió.
    assert tuple(round(v, 6) for v in geo.handle_points(nt)["nw"]) == \
        tuple(round(v, 6) for v in geo.handle_points(t)["nw"])


def test_no_se_voltea_al_pasar_el_asa_del_otro_lado():
    t = Transform(0, 0, 100, 100)
    nt = geo.resize_transform(t, "e", -500, 0, proportional=False)
    assert nt.width == geo.MIN_SIZE
    assert nt.cx - nt.width / 2 == -50


def test_angulos():
    assert aprox(geo.angle_to(0, 0, 0, 10), 90)
    assert geo.normalize_angle(190) == -170
    assert geo.normalize_angle(-180) == 180
    assert geo.snap_angle(22.4) == 15
    assert geo.snap_angle(23) == 30
    x, y = geo.rotate_point(10, 0, 0, 0, 90)
    assert aprox(x, 0) and aprox(y, 10)


def test_el_asa_de_giro_queda_sobre_la_caja():
    t = Transform(100, 100, 50, 50)
    assert geo.rotate_handle_point(t, 30) == (100.0, 45.0)
    g = Transform(100, 100, 50, 50, rotation=90)
    x, y = geo.rotate_handle_point(g, 30)
    assert aprox(x, 155) and aprox(y, 100)


def test_el_iman_se_pega_al_centro_del_lienzo():
    dx, dy, guias = geo.compute_snap((440, 100, 640, 200), [], 1080, 1080, 6)
    assert dx == 0 or abs(dx + 0) <= 6          # el centro (540) ya cae justo
    dx, dy, guias = geo.compute_snap((443, 100, 643, 200), [], 1080, 1080, 6)
    assert dx == -3 and dy == 0
    assert any(g[0] == "v" and g[1] == 540 and g[4] == "lienzo" for g in guias)


def test_el_iman_no_actua_lejos():
    dx, dy, guias = geo.compute_snap((300, 300, 400, 400), [], 1080, 1080, 6)
    assert (dx, dy, guias) == (0.0, 0.0, [])


def test_el_iman_se_pega_a_otra_capa():
    otra = (100.0, 600.0, 300.0, 700.0)
    dx, dy, guias = geo.compute_snap((103, 100, 253, 200), [otra], 1080, 1080, 6)
    assert dx == -3
    v = [g for g in guias if g[0] == "v" and g[4] == "capa"]
    assert v and v[0][1] == 100 and v[0][2] == 100 and v[0][3] == 700


def test_el_iman_elige_la_guia_mas_cercana():
    dx, dy, _ = geo.compute_snap((0, 0, 100, 100), [(104.0, 0.0, 200.0, 50.0)], 1080, 1080, 6)
    assert dx == 0        # el borde izquierdo ya está en 0 (borde del lienzo)


# --- recortar ------------------------------------------------------------------

def _capa(crop=None, w=200.0, h=100.0, **kw):
    from vortex_studio.photo.document import KIND_IMAGE, Layer
    return Layer(kind=KIND_IMAGE, asset="x", crop=crop, transform=Transform(500, 500, w, h, **kw))


def test_la_imagen_entera_cabe_en_su_caja():
    capa = _capa()
    m = cropmod.CropMath(capa, (400, 200))       # 2 unidades por píxel
    assert m.full_rect() == (-100.0, -50.0, 100.0, 50.0)
    assert m.current_rect() == (-100.0, -50.0, 100.0, 50.0)


def test_recortar_la_mitad_deja_la_otra_en_su_sitio():
    capa = _capa()
    m = cropmod.CropMath(capa, (400, 200))
    crop, t = m.result((0.0, -50.0, 100.0, 50.0))        # la mitad derecha
    assert crop == (200.0, 0.0, 200.0, 200.0)
    assert t.width == 100 and t.height == 100
    assert t.cx == 550 and t.cy == 500                  # la mitad derecha quedó donde estaba


def test_recortar_con_la_capa_girada():
    capa = _capa(rotation=90)
    m = cropmod.CropMath(capa, (400, 200))
    crop, t = m.result((-100.0, -50.0, 0.0, 50.0))       # la mitad izquierda local
    assert crop[0] == 0.0 and crop[2] == 200.0
    # Girada 90°, «izquierda» local queda arriba en el lienzo.
    assert aprox(t.cx, 500) and aprox(t.cy, 450)
    assert t.rotation == 90


def test_recortar_con_la_capa_volteada():
    capa = _capa(flip_h=True)
    m = cropmod.CropMath(capa, (400, 200))
    crop, t = m.result((-100.0, -50.0, 0.0, 50.0))       # lo que se VE a la izquierda
    assert crop[0] == 200.0 and crop[2] == 200.0          # es la mitad derecha de la imagen


def test_recortar_sobre_un_recorte_previo():
    capa = _capa(crop=(100.0, 0.0, 200.0, 100.0), w=200.0, h=100.0)   # 1 unidad por píxel
    m = cropmod.CropMath(capa, (400, 200))
    assert m.full_rect() == (-200.0, -50.0, 200.0, 150.0)
    crop, t = m.result((-100.0, -50.0, 0.0, 0.0))
    assert crop == (100.0, 0.0, 100.0, 50.0)


def test_el_rectangulo_no_se_sale_de_la_imagen():
    r = cropmod.clamp_rect((-300, -300, -100, -100), (-100, -50, 100, 50))
    assert r == (-100, -50, 100, 50) or (r[0] >= -100 and r[1] >= -50 and r[2] <= 100 and r[3] <= 50)


def test_proporciones_de_recorte():
    r = cropmod.fit_ratio((-100, -50, 100, 50), 1.0)
    assert aprox(r[2] - r[0], r[3] - r[1])
    assert r == (-50.0, -50.0, 50.0, 50.0)
    r = cropmod.fit_ratio((-100, -50, 100, 50), 9 / 16)
    assert aprox((r[2] - r[0]) / (r[3] - r[1]), 9 / 16)


@pytest.mark.parametrize("asa", list(geo.HANDLES))
def test_arrastrar_asas_con_proporcion_la_conserva_y_no_sale(asa):
    bounds = (-100.0, -50.0, 100.0, 50.0)
    rect = (-30.0, -20.0, 30.0, 20.0)
    hx, hy = geo.HANDLES[asa]
    x = (rect[0] + rect[2]) / 2 + hx * 500
    y = (rect[1] + rect[3]) / 2 + hy * 500
    nr = cropmod.drag_handle(rect, asa, x, y, bounds, 1.0)
    assert nr[0] >= bounds[0] - 1e-6 and nr[2] <= bounds[2] + 1e-6
    assert nr[1] >= bounds[1] - 1e-6 and nr[3] <= bounds[3] + 1e-6
    assert aprox((nr[2] - nr[0]) / (nr[3] - nr[1]), 1.0, 1e-4)


def test_arrastrar_libre_se_detiene_en_el_borde():
    nr = cropmod.drag_handle((-30, -20, 30, 20), "se", 999, 999, (-100, -50, 100, 50), None)
    assert nr == (-30, -20, 100, 50)
