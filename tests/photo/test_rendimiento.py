"""Rendimiento con umbrales holgados: no deben fallar por una máquina lenta,
pero sí atrapar un bucle por píxel en Python (que tardaría minutos)."""

from __future__ import annotations

import time

import numpy as np
import pytest
from ayuda_photo import capa_imagen, colorido, doc_con, ruido, solido

from vortex_studio.photo.adjust import apply_adjustments
from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.blend import composite
from vortex_studio.photo.document import Adjustments, Effects, Layer, Outline, Shadow, Transform
from vortex_studio.photo.document import BLENDS
from vortex_studio.photo.paint import Brush, magic_wand, remove_background, stroke
from vortex_studio.photo.render import Renderer


def medir(f, veces=1):
    mejor = 1e9
    for _ in range(veces):
        t = time.perf_counter()
        f()
        mejor = min(mejor, time.perf_counter() - t)
    return mejor


def escena_1080(st, capas=10):
    imgs = [colorido(400, 300), ruido(300, 300, 3)]
    ls = []
    for i in range(capas):
        c = capa_imagen(st, imgs[i % 2], 200 + i * 60, 300 + i * 40, 500, 400, rotation=(i * 9) % 40,
                        adjustments=Adjustments(exposure=10, contrast=15, saturation=10, vibrance=10),
                        opacity=0.9)
        ls.append(c)
    return doc_con(st, 1080, 1080, *ls)


def test_render_1080_con_10_capas_en_frio_y_con_cache():
    st = AssetStore()
    d = escena_1080(st)
    r = Renderer(st)
    frio = medir(lambda: r.render(d, 0.5))
    caliente = medir(lambda: r.render(d, 0.5), 5)
    print(f"\n[perf] render 1080² 10 capas a 0,5: frío {frio * 1000:.0f} ms, caliente {caliente * 1000:.0f} ms")
    assert frio < 5.0
    assert caliente < 0.25


def test_arrastrar_una_capa_con_el_resto_en_cache_es_rapido():
    st = AssetStore()
    d = escena_1080(st)
    r = Renderer(st)
    r.render(d, 0.5)
    mover = d.layers[5]

    def paso():
        mover.transform.cx += 3
        r.render(d, 0.5)

    t = medir(paso, 5)
    print(f"[perf] arrastrar una capa: {t * 1000:.0f} ms")
    assert t < 0.4


def test_ajustes_sobre_foto_de_24_megapixeles_a_escala_de_vista_previa():
    st = AssetStore()
    rng = np.random.default_rng(0)
    foto = np.empty((4000, 6000, 4), np.uint8)
    foto[..., :3] = rng.integers(0, 256, (4000, 6000, 3), dtype=np.uint8)
    foto[..., 3] = 255
    c = Layer(kind="image", asset=st.put(foto), transform=Transform(540, 360, 1080, 720),
              adjustments=Adjustments(exposure=20, contrast=20, highlights=-30, shadows=30, saturation=15,
                                      clarity=30, sharpen=30, vignette=30, grain=20))
    del foto
    d = doc_con(st, 1080, 1080, c)
    r = Renderer(st)
    frio = medir(lambda: r.render(d, 0.5))
    c.adjustments.exposure = 25                         # mover un deslizador: el origen ya está reducido
    deslizador = medir(lambda: r.render(d, 0.5))
    print(f"[perf] 24 MP a escala 0,5: primera vez {frio * 1000:.0f} ms, mover un ajuste {deslizador * 1000:.0f} ms")
    assert frio < 8.0
    assert deslizador < 1.0


def test_ajustes_de_pantalla_completa_son_rapidos():
    px = ruido(1080, 1080)
    todo = Adjustments(exposure=20, contrast=20, saturation=15, temperature=10, clarity=30, sharpen=30, vignette=30,
                       grain=20, blur=5, curve=[(0, 0), (0.5, 0.6), (1, 1)], hsl={"green": (10, -20, 5)})
    t = medir(lambda: apply_adjustments(px, todo, 1.0))
    tonos = medir(lambda: apply_adjustments(px, Adjustments(exposure=20, contrast=20), 1.0), 3)
    print(f"[perf] ajustes 1080² todo encendido {t * 1000:.0f} ms; solo tonos {tonos * 1000:.0f} ms")
    assert t < 6.0 and tonos < 0.5


@pytest.mark.parametrize("modo", ["Normal", "Multiplicar", "Superponer", "Luz suave", "Tono", "Luminosidad"])
def test_composicion_de_1080_por_modo(modo):
    dst = solido(1080, 1080, (120, 80, 200, 255))
    src = ruido(1080, 1080)
    t = medir(lambda: composite(dst, src, modo, 0.8, 0, 0))
    assert t < 3.0, (modo, t)


def test_pincel_y_varita_en_imagen_grande():
    px = solido(3000, 2000, (255, 255, 255, 255))
    px[500:1500, 500:1500] = (255, 0, 0, 255)
    t = medir(lambda: magic_wand(px, 1000, 1000, 10))
    tg = medir(lambda: magic_wand(px, 0, 0, 10, contiguous=False))
    ts = medir(lambda: stroke(px, [(100, 100, 1.0), (2900, 1900, 1.0), (100, 1900, 0.5)], Brush(size=40, hardness=0.5)))
    tf = medir(lambda: remove_background(px))
    print(f"[perf] varita {t * 1000:.0f} ms, global {tg * 1000:.0f} ms, trazo {ts * 1000:.0f} ms, quitar fondo 6 MP {tf * 1000:.0f} ms")
    assert t < 3 and tg < 3 and ts < 3 and tf < 6


def test_efectos_de_capa_grande():
    from vortex_studio.photo.effects import apply_effects
    px = solido(800, 800, (255, 0, 0, 255))
    e = Effects(shadow=Shadow(True, blur=30, dx=10, dy=10), outline=Outline(True, width=20))
    t = medir(lambda: apply_effects(px, e, 1.0))
    print(f"[perf] sombra + contorno de 20 px en 800²: {t * 1000:.0f} ms")
    assert t < 4


def test_vista_previa_y_exportacion_coinciden_visualmente():
    """Render a escala 0,5 contra el render a escala 1 reducido a la mitad:
    mismo aspecto (error medio chico) aunque los radios se calculen aparte."""
    from vortex_studio.photo._util import resize_rgba
    st = AssetStore()
    base = colorido(300, 300)
    base[100:200, 100:200, :3] = 40
    todo = Adjustments(exposure=15, contrast=20, saturation=15, temperature=10, clarity=40, sharpen=40,
                       vignette=30, grain=0, blur=25, hsl={"green": (10, -30, 5)})
    d = doc_con(st, 600, 600, capa_imagen(st, base, 300, 300, 600, 600, adjustments=todo))
    previa = Renderer(st).render(d, 0.5)
    grande = Renderer(st).render(d, 1.0)
    reducida = resize_rgba(grande, 300, 300)
    err = np.abs(previa[..., :3].astype(int) - reducida[..., :3]).mean()
    assert err < 6, err
    d.layers[0].adjustments.grain = 40
    g1 = Renderer(st).render(d, 0.5).astype(int)
    g2 = resize_rgba(Renderer(st).render(d, 1.0), 300, 300).astype(int)
    assert abs(g1[..., :3].mean() - g2[..., :3].mean()) < 3          # el grano no cambia el brillo general
