"""El compositor: colocación, transformaciones, capas de ajuste, máscaras,
caché y casos raros."""

from __future__ import annotations

import numpy as np
import pytest
from ayuda_photo import capa_imagen, colorido, degradado, doc_con, lum, ruido, solido

from vortex_studio.photo import render as render_mod
from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (Adjustments, Document, Effects, Filter, Layer, Outline,
                                          Shadow, Transform)
from vortex_studio.photo.render import Renderer, from_qimage, to_qimage


@pytest.fixture
def st():
    return AssetStore()


def test_documento_sin_capas_es_el_fondo(st):
    out = Renderer(st).render(Document(30, 20, "#ff0000"))
    assert out.shape == (20, 30, 4)
    assert (out == (255, 0, 0, 255)).all()


def test_fondo_transparente_es_transparente(st):
    out = Renderer(st).render(Document(10, 10, None))
    assert out.max() == 0


def test_tamano_sigue_la_escala(st):
    r = Renderer(st)
    d = Document(100, 60)
    assert r.render(d, 0.5).shape == (30, 50, 4)
    assert r.render(d, 2).shape == (120, 200, 4)
    assert r.render(d, 0.01).shape == (1, 1, 4)
    assert r.render(Document(1080, 1080), 0.01).shape == (11, 11, 4)


def test_lienzo_de_un_pixel(st):
    d = doc_con(st, 1, 1, capa_imagen(st, solido(10, 10, (255, 0, 0, 255)), 0.5, 0.5))
    assert Renderer(st).render(d).tolist() == [[[255, 0, 0, 255]]]


def test_capa_queda_donde_dice_su_transformacion(st):
    d = doc_con(st, 100, 100, capa_imagen(st, solido(20, 10, (255, 0, 0, 255)), 50, 30))
    out = Renderer(st).render(d)
    rojo = (out[..., 0] == 255) & (out[..., 1] == 0)
    ys, xs = np.nonzero(rojo)
    assert (xs.min(), xs.max(), ys.min(), ys.max()) == (40, 59, 25, 34)


def test_la_imagen_se_estira_a_su_caja(st):
    d = doc_con(st, 100, 100, capa_imagen(st, solido(4, 4, (0, 255, 0, 255)), 50, 50, 40, 20))
    out = Renderer(st).render(d)
    verde = (out[..., 0] == 0) & (out[..., 1] == 255)
    assert verde.sum() == 40 * 20


def test_escala_mantiene_la_composicion(st):
    d = doc_con(st, 100, 100, capa_imagen(st, solido(20, 20, (0, 0, 255, 255)), 25, 25, 20, 20))
    a = Renderer(st).render(d, 1.0)
    b = Renderer(st).render(d, 0.5)
    azul = lambda o: np.argwhere((o[..., 2] == 255) & (o[..., 0] == 0)).mean(axis=0)
    assert azul(a)[0] == pytest.approx(azul(b)[0] * 2 + 0.5, abs=2)


def test_recorte_toma_solo_esa_parte(st):
    px = solido(40, 20, (255, 0, 0, 255))
    px[:, 20:, :3] = (0, 0, 255)
    capa = capa_imagen(st, px, 10, 10, 20, 20)
    capa.crop = (20, 0, 20, 20)
    out = Renderer(st).render(doc_con(st, 20, 20, capa))
    assert (out[..., 2] == 255).all() and (out[..., 0] == 0).all()


def test_recorte_fuera_de_la_imagen_no_truena(st):
    capa = capa_imagen(st, solido(10, 10), 5, 5)
    for crop in ((-50, -50, 5, 5), (500, 500, 10, 10), (0, 0, 0, 0), (3, 3, -4, -4)):
        capa.crop = crop
        assert Renderer(st).render(doc_con(st, 10, 10, capa)).shape == (10, 10, 4)


def test_voltear_horizontal_y_vertical(st):
    px = solido(4, 4, (0, 0, 0, 255))
    px[:2, :2, :3] = (255, 0, 0)               # rojo arriba a la izquierda
    r = Renderer(st)
    base = r.render(doc_con(st, 4, 4, capa_imagen(st, px, 2, 2)))
    h = r.render(doc_con(st, 4, 4, capa_imagen(st, px, 2, 2, flip_h=True)))
    v = r.render(doc_con(st, 4, 4, capa_imagen(st, px, 2, 2, flip_v=True)))
    assert base[0, 0, 0] == 255 and h[0, 3, 0] == 255 and h[0, 0, 0] == 0
    assert v[3, 0, 0] == 255 and v[0, 0, 0] == 0


def test_giro_de_90_cambia_el_alto_por_el_ancho(st):
    capa = capa_imagen(st, solido(40, 10, (255, 0, 0, 255)), 50, 50, rotation=90)
    out = Renderer(st).render(doc_con(st, 100, 100, capa))
    ys, xs = np.nonzero(out[..., 1] < 10)
    assert xs.max() - xs.min() + 1 == pytest.approx(10, abs=2)
    assert ys.max() - ys.min() + 1 == pytest.approx(40, abs=2)


def test_giro_a_favor_del_reloj(st):
    # Rojo a la derecha de la caja; girado 90° debe quedar ABAJO.
    px = solido(20, 20, (0, 0, 0, 255))
    px[:, 10:, :3] = (255, 0, 0)
    out = Renderer(st).render(doc_con(st, 40, 40, capa_imagen(st, px, 20, 20, rotation=90), fondo="#ffffff"))
    rojo = (out[..., 0] > 200) & (out[..., 1] < 60)
    ys, xs = np.nonzero(rojo)
    assert ys.mean() > 20 and abs(xs.mean() - 20) < 3


def test_giro_45_conserva_el_area_y_antialias(st):
    capa = capa_imagen(st, solido(40, 40, (255, 0, 0, 255)), 60, 60, rotation=45)
    out = Renderer(st).render(doc_con(st, 120, 120, capa, fondo=None))
    area = out[..., 3].astype(float).sum() / 255
    assert area == pytest.approx(1600, rel=0.03)
    parcial = ((out[..., 3] > 10) & (out[..., 3] < 245)).sum()
    assert parcial > 60                                           # bordes suaves, no escalera
    # sin halo oscuro en el borde: el color de los píxeles translúcidos sigue siendo rojo
    borde = out[(out[..., 3] > 30) & (out[..., 3] < 220)]
    assert (borde[:, 0] > 240).all() and (borde[:, 1] < 15).all()


def test_giro_ligero_no_deja_la_capa_ni_fuera_de_lugar(st):
    capa = capa_imagen(st, solido(30, 30, (255, 0, 0, 255)), 50, 50, rotation=3)
    out = Renderer(st).render(doc_con(st, 100, 100, capa, fondo=None))
    ys, xs = np.nonzero(out[..., 3] > 128)
    assert abs(xs.mean() - 49.5) < 1.0 and abs(ys.mean() - 49.5) < 1.0


def test_opacidad_cero_y_capa_invisible_no_dibujan(st):
    base = capa_imagen(st, solido(10, 10, (255, 0, 0, 255)), 5, 5)
    r = Renderer(st)
    for cambio in (dict(opacity=0.0), dict(visible=False)):
        for k, v in cambio.items():
            setattr(base, k, v)
        out = r.render(doc_con(st, 10, 10, base))
        assert (out == 255).all()
        base.opacity, base.visible = 1.0, True


def test_hide_oculta_por_id(st):
    capa = capa_imagen(st, solido(10, 10, (255, 0, 0, 255)), 5, 5)
    d = doc_con(st, 10, 10, capa)
    assert (Renderer(st).render(d, hide={capa.id}) == 255).all()
    assert Renderer(st).render(d)[0, 0, 1] == 0


def test_capa_totalmente_fuera_del_lienzo(st):
    d = doc_con(st, 20, 20, capa_imagen(st, solido(10, 10), 500, 500),
                capa_imagen(st, solido(10, 10), -300, 5, rotation=30))
    assert (Renderer(st).render(d) == 255).all()


def test_capa_parcialmente_fuera_del_lienzo(st):
    d = doc_con(st, 20, 20, capa_imagen(st, solido(20, 20, (255, 0, 0, 255)), 0, 0))
    out = Renderer(st).render(d)
    assert out[0, 0, 1] == 0 and out[19, 19, 1] == 255 and out[9, 9, 1] == 0 and out[10, 10, 1] == 255


def test_capa_con_caja_de_cero_o_negativa_se_salta(st):
    d = doc_con(st, 20, 20, capa_imagen(st, solido(10, 10), 5, 5, 0, 10), capa_imagen(st, solido(10, 10), 5, 5, -5, 10))
    assert (Renderer(st).render(d) == 255).all()


def test_capa_con_imagen_que_falta_se_salta(st):
    capa = Layer(kind="image", asset="no-existe", transform=Transform(5, 5, 10, 10))
    capa2 = Layer(kind="image", asset=st.put(solido(4, 4)), mask="tampoco", transform=Transform(5, 5, 10, 10))
    out = Renderer(st).render(doc_con(st, 10, 10, capa, capa2))
    assert out.shape == (10, 10, 4)


def test_imagen_de_un_pixel_se_agranda(st):
    d = doc_con(st, 10, 10, capa_imagen(st, solido(1, 1, (0, 255, 0, 255)), 5, 5, 10, 10))
    out = Renderer(st).render(d)
    assert (out[..., 1] == 255).all() and (out[..., 0] == 0).all()


def test_modo_de_fusion_de_la_capa(st):
    fondo = capa_imagen(st, solido(10, 10, (200, 100, 50, 255)), 5, 5)
    arriba = capa_imagen(st, solido(10, 10, (128, 128, 128, 255)), 5, 5, blend="Multiplicar")
    out = Renderer(st).render(doc_con(st, 10, 10, fondo, arriba))
    assert np.abs(out[0, 0, :3].astype(int) - (100, 50, 25)).max() <= 1


def test_opacidad_de_la_capa(st):
    arriba = capa_imagen(st, solido(10, 10, (0, 0, 0, 255)), 5, 5, opacity=0.25)
    out = Renderer(st).render(doc_con(st, 10, 10, arriba))
    assert abs(int(out[0, 0, 0]) - 191) <= 1


def test_ajustes_y_filtro_de_la_capa_se_aplican_y_original_los_quita(st):
    capa = capa_imagen(st, colorido(20, 20), 10, 10, adjustments=Adjustments(saturation=-100))
    d = doc_con(st, 20, 20, capa)
    r = Renderer(st)
    gris = r.render(d)
    assert np.abs(gris[..., 0].astype(int) - gris[..., 1]).max() <= 1
    antes = r.render(d, original=True)
    assert np.abs(antes[..., 0].astype(int) - antes[..., 1]).max() > 20
    capa.adjustments = Adjustments()
    capa.filter = Filter("bn", 100)
    assert np.abs(r.render(d)[..., 0].astype(int) - r.render(d)[..., 1]).max() <= 2
    assert np.abs(r.render(d, original=True)[..., 0].astype(int) - antes[..., 0]).max() == 0


def test_mascara_de_capa_oculta_su_parte(st):
    m = np.zeros((10, 20), np.uint8)
    m[:, :10] = 255
    capa = capa_imagen(st, solido(20, 10, (255, 0, 0, 255)), 10, 5, mask=st.put(m))
    out = Renderer(st).render(doc_con(st, 20, 10, capa, fondo=None))
    assert out[5, 2, 3] == 255 and out[5, 15, 3] == 0


def test_mascara_con_otra_resolucion_se_estira_a_la_capa(st):
    m = np.zeros((2, 2), np.uint8)
    m[:, 0] = 255
    capa = capa_imagen(st, solido(40, 20, (255, 0, 0, 255)), 20, 10, mask=st.put(m))
    out = Renderer(st).render(doc_con(st, 40, 20, capa, fondo=None))
    assert out[10, 3, 3] > 200 and out[10, 36, 3] < 55


def test_mascara_suave_da_alfa_intermedio(st):
    m = np.full((10, 10), 128, np.uint8)
    capa = capa_imagen(st, solido(10, 10, (255, 0, 0, 255)), 5, 5, mask=st.put(m))
    out = Renderer(st).render(doc_con(st, 10, 10, capa, fondo=None))
    assert abs(int(out[5, 5, 3]) - 128) <= 1


def test_capa_de_ajuste_corrige_lo_de_abajo(st):
    foto = capa_imagen(st, colorido(20, 20), 10, 10)
    aj = Layer(kind="adjust", transform=Transform(10, 10, 20, 20), adjustments=Adjustments(saturation=-100))
    r = Renderer(st)
    d = doc_con(st, 20, 20, foto, aj)
    out = r.render(d)
    assert np.abs(out[..., 0].astype(int) - out[..., 1]).max() <= 1
    sin = r.render(d, original=True)                   # «antes» no aplica capas de ajuste
    assert np.abs(sin[..., 0].astype(int) - sin[..., 1]).max() > 20
    aj.visible = False
    assert np.array_equal(r.render(d), sin)


def test_capa_de_ajuste_no_toca_lo_que_esta_encima(st):
    foto = capa_imagen(st, colorido(20, 20), 10, 10)
    aj = Layer(kind="adjust", transform=Transform(10, 10, 20, 20), adjustments=Adjustments(saturation=-100))
    sticker = capa_imagen(st, solido(6, 6, (255, 0, 0, 255)), 10, 10)
    out = Renderer(st).render(doc_con(st, 20, 20, foto, aj, sticker))
    assert out[10, 10].tolist() == [255, 0, 0, 255]


def test_capa_de_ajuste_con_mascara_y_opacidad(st):
    foto = capa_imagen(st, colorido(20, 20), 10, 10)
    m = np.zeros((20, 20), np.uint8)
    m[:, :10] = 255
    aj = Layer(kind="adjust", transform=Transform(10, 10, 20, 20), mask=st.put(m),
               adjustments=Adjustments(saturation=-100))
    r = Renderer(st)
    out = r.render(doc_con(st, 20, 20, foto, aj))
    sin = r.render(doc_con(st, 20, 20, foto), original=False)
    assert np.abs(out[:, :9, 0].astype(int) - out[:, :9, 1]).max() <= 1       # izquierda corregida
    assert np.array_equal(out[:, 11:], sin[:, 11:])                           # derecha intacta
    aj.opacity = 0.5
    medio = r.render(doc_con(st, 20, 20, foto, aj))
    esperado = (out[:, :9, :3].astype(int) + sin[:, :9, :3].astype(int)) / 2
    assert np.abs(medio[:, :9, :3] - esperado).max() <= 2


def test_capa_de_ajuste_en_una_zona_chica(st):
    foto = capa_imagen(st, colorido(20, 20), 10, 10)
    aj = Layer(kind="adjust", transform=Transform(5, 5, 10, 10), adjustments=Adjustments(exposure=-300))
    r = Renderer(st)
    out = r.render(doc_con(st, 20, 20, foto, aj))
    sin = r.render(doc_con(st, 20, 20, foto))
    assert lum(out[:10, :10]).mean() < lum(sin[:10, :10]).mean() * 0.5
    assert np.array_equal(out[12:, 12:], sin[12:, 12:])


def test_capa_de_ajuste_sin_nada_debajo_y_neutra(st):
    aj = Layer(kind="adjust", transform=Transform(5, 5, 10, 10), adjustments=Adjustments(exposure=50))
    assert Renderer(st).render(doc_con(st, 10, 10, aj, fondo=None)).shape == (10, 10, 4)
    neutra = Layer(kind="adjust", transform=Transform(5, 5, 10, 10))
    assert (Renderer(st).render(doc_con(st, 10, 10, neutra)) == 255).all()


def test_efectos_agrandan_la_capa_mas_alla_de_su_caja(st):
    capa = capa_imagen(st, solido(20, 20, (255, 0, 0, 255)), 50, 50)
    capa.effects = Effects(shadow=Shadow(True, "#000000", 1.0, 4.0, 0, 10))
    out = Renderer(st).render(doc_con(st, 100, 100, capa, fondo=None))
    assert out[62, 50, 3] > 0                       # sombra debajo de la caja (40…59)
    assert out[30, 50, 3] == 0


def test_sombra_gira_con_el_lienzo_no_con_la_capa(st):
    # Aunque la capa gire 90°, la sombra «cae» hacia abajo en el lienzo.
    capa = capa_imagen(st, solido(20, 20, (255, 0, 0, 255)), 50, 50, rotation=90)
    capa.effects = Effects(shadow=Shadow(True, "#000000", 1.0, 0.0, 0, 12))
    out = Renderer(st).render(doc_con(st, 100, 100, capa, fondo=None))
    assert out[66, 50, 3] > 128 and out[34, 50, 3] == 0


def test_contorno_rodea_la_capa(st):
    capa = capa_imagen(st, solido(20, 20, (255, 0, 0, 255)), 50, 50)
    capa.effects = Effects(outline=Outline(True, "#00ff00", 5.0))
    out = Renderer(st).render(doc_con(st, 100, 100, capa, fondo=None))
    assert out[50, 37].tolist()[1] > 200 and out[50, 37, 3] > 200      # 3 px afuera del borde izquierdo (40)
    assert out[50, 50, 0] == 255                                      # el centro sigue rojo
    assert out[50, 30, 3] == 0


def test_render_layer_y_su_version_con_efectos(st):
    capa = capa_imagen(st, solido(20, 10, (255, 0, 0, 255)), 50, 50, adjustments=Adjustments(saturation=-100))
    capa.effects = Effects(shadow=Shadow(True, "#000000", 1.0, 4.0, 3, 3))
    d = doc_con(st, 100, 100, capa)
    r = Renderer(st)
    c = r.render_layer(d, capa, 1.0)
    assert c.shape == (10, 20, 4)
    assert r.render_layer(d, capa, 0.5).shape == (5, 10, 4)
    img, ox, oy = r.render_layer_fx(d, capa, 1.0)
    assert ox > 0 and oy > 0 and img.shape[0] > 10 and img.shape[1] > 20


def test_miniatura(st):
    d = doc_con(st, 400, 200, capa_imagen(st, solido(100, 100), 200, 100))
    t = Renderer(st).thumbnail(d, 100)
    assert t.shape == (50, 100, 4)
    assert Renderer(st).thumbnail(d, 1).shape[0] >= 1


def test_to_y_from_qimage_ida_y_vuelta():
    px = ruido(13, 7)
    px[..., 3] = np.linspace(0, 255, 13).astype(np.uint8)[None, :]
    assert np.array_equal(from_qimage(to_qimage(px)), px)


# --- caché ---------------------------------------------------------------------------

@pytest.fixture
def contador(monkeypatch):
    llamadas = {"n": 0}
    original = render_mod.apply_adjustments

    def contando(*a, **k):
        llamadas["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(render_mod, "apply_adjustments", contando)
    return llamadas


def _escena(st):
    capas = [capa_imagen(st, colorido(60, 40), 30 + i * 5, 30, adjustments=Adjustments(exposure=10 + i, blur=10))
             for i in range(4)]
    return doc_con(st, 100, 100, *capas), capas


def test_cache_segundo_render_no_recalcula(st, contador):
    d, _ = _escena(st)
    r = Renderer(st)
    r.render(d, 0.5)
    primero = contador["n"]
    assert primero == 4
    r.render(d, 0.5)
    assert contador["n"] == primero
    assert r.hits >= 4


def test_cache_mover_o_girar_no_recalcula_los_ajustes(st, contador):
    d, capas = _escena(st)
    r = Renderer(st)
    r.render(d, 0.5)
    n = contador["n"]
    capas[1].transform.cx += 17
    capas[2].transform.cy -= 9
    capas[3].transform.rotation = 33
    capas[0].opacity = 0.4
    capas[0].blend = "Multiplicar"
    capas[0].name = "otro"
    r.render(d, 0.5)
    assert contador["n"] == n


def test_cache_cambiar_un_ajuste_recalcula_solo_esa_capa(st, contador):
    d, capas = _escena(st)
    r = Renderer(st)
    r.render(d, 0.5)
    n = contador["n"]
    capas[2].adjustments.contrast = 30
    r.render(d, 0.5)
    assert contador["n"] == n + 1


def test_cache_otra_escala_recalcula_y_regresar_no(st, contador):
    d, _ = _escena(st)
    r = Renderer(st)
    r.render(d, 0.5)
    n = contador["n"]
    r.render(d, 1.0)
    assert contador["n"] == n + 4
    r.render(d, 0.5)
    assert contador["n"] == n + 4


def test_cache_invalidate_por_id_y_total(st, contador):
    d, capas = _escena(st)
    r = Renderer(st)
    r.render(d, 0.5)
    n = contador["n"]
    r.invalidate(capas[0].id)
    r.render(d, 0.5)
    assert contador["n"] == n + 1
    r.invalidate()
    assert r.cache_bytes() == 0
    r.render(d, 0.5)
    assert contador["n"] == n + 1 + 4


def test_cache_resultado_igual_con_y_sin_cache(st):
    d, capas = _escena(st)
    r = Renderer(st)
    frio = r.render(d, 0.5)
    caliente = r.render(d, 0.5)
    capas[1].transform.cx += 5
    movido = r.render(d, 0.5)
    nuevo = Renderer(st).render(d, 0.5)
    assert np.array_equal(frio, caliente) and np.array_equal(movido, nuevo)


def test_cache_respeta_su_limite_en_bytes(st):
    capas = [capa_imagen(st, ruido(200, 200, i), 100, 100) for i in range(12)]
    d = doc_con(st, 200, 200, *capas)
    r = Renderer(st, max_cache_bytes=300_000)
    r.render(d, 1.0)
    assert r.cache_bytes() <= 300_000
    assert Renderer(st).render(d, 1.0).shape == (200, 200, 4)


def test_cache_con_limite_cero_sigue_funcionando(st):
    d, _ = _escena(st)
    r = Renderer(st, max_cache_bytes=0)
    assert np.array_equal(r.render(d, 0.5), Renderer(st).render(d, 0.5))


def test_cache_capa_girada_no_vuelve_a_remuestrear(st, monkeypatch):
    capa = capa_imagen(st, colorido(60, 40), 50, 50, rotation=20)
    d = doc_con(st, 100, 100, capa)
    r = Renderer(st)
    r.render(d)
    llamadas = {"n": 0}
    original = r._place

    def contando(*a, **k):
        llamadas["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(r, "_place", contando)
    r.render(d)
    assert llamadas["n"] == 0
    capa.transform.cx += 3
    r.render(d)
    assert llamadas["n"] == 1


def test_documento_con_capa_de_texto_y_forma(st):
    t = Layer(kind="text", text="Hola", transform=Transform(50, 20, 80, 30), font_size=20, color="#ff0000")
    f = Layer(kind="shape", shape="ellipse", fill="#0000ff", transform=Transform(50, 70, 40, 40))
    out = Renderer(st).render(doc_con(st, 100, 100, t, f))
    assert ((out[..., 0] > 200) & (out[..., 2] < 80)).any()
    assert out[70, 50, 2] == 255 and out[70, 50, 0] == 0


def test_tipo_de_capa_desconocido_se_ignora(st):
    d = doc_con(st, 10, 10, Layer(kind="holograma", transform=Transform(5, 5, 10, 10)))
    assert (Renderer(st).render(d) == 255).all()
