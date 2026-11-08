"""Documentos al azar (con semilla fija): el compositor no debe tronar con
ninguna combinación de capas, giros, volteos, máscaras, recortes, efectos,
modos y escalas, y debe dar siempre un lienzo del tamaño esperado."""

from __future__ import annotations

import random

import numpy as np
import pytest
from ayuda_photo import colorido, ruido

from vortex_studio.photo.assets import AssetStore
from vortex_studio.photo.document import (BLENDS, SHAPES, Adjustments, Document, Effects, Filter, Glow, Layer,
                                          Outline, Shadow, Transform)
from vortex_studio.photo.filters import FILTERS
from vortex_studio.photo.render import Renderer


def _capa_al_azar(rng: random.Random, st: AssetStore, ids: list[str], mascaras: list[str]) -> Layer:
    t = Transform(rng.uniform(-80, 180), rng.uniform(-80, 180), rng.choice([0.5, 1, 7, 30, 90, 250]),
                  rng.choice([0.5, 1, 7, 30, 90, 250]), rng.choice([0, 0, 15, 45, 90, 137, 270, 359.9, -30, 720]),
                  rng.random() < 0.3, rng.random() < 0.3)
    kind = rng.choice(["image", "image", "text", "shape", "adjust"])
    capa = Layer(kind=kind, transform=t, opacity=rng.choice([0, 0.3, 1, 1, 1.7]), blend=rng.choice(BLENDS),
                 visible=rng.random() < 0.9)
    if rng.random() < 0.4:
        capa.effects = Effects(Shadow(rng.random() < 0.7, "#000", rng.random(), rng.uniform(0, 30), rng.uniform(-20, 20),
                                      rng.uniform(-20, 20)),
                               Outline(rng.random() < 0.5, "#fff", rng.uniform(0, 12)),
                               Glow(rng.random() < 0.5, "#ff0", rng.random(), rng.uniform(0, 25)))
    if kind == "image":
        capa.asset = rng.choice(ids)
        if rng.random() < 0.3:
            capa.crop = (rng.uniform(-5, 70), rng.uniform(-5, 50), rng.uniform(0, 80), rng.uniform(0, 60))
        if rng.random() < 0.5:
            capa.adjustments = Adjustments(exposure=rng.uniform(-100, 100), contrast=rng.uniform(-100, 100),
                                           saturation=rng.uniform(-100, 100), blur=rng.uniform(0, 40),
                                           sharpen=rng.uniform(0, 100), clarity=rng.uniform(-100, 100),
                                           vignette=rng.uniform(0, 100), grain=rng.uniform(0, 100),
                                           hsl={"red": (rng.uniform(-100, 100), 0, 0)})
        if rng.random() < 0.3:
            capa.filter = Filter(rng.choice(list(FILTERS)), rng.uniform(0, 100))
        if rng.random() < 0.3:
            capa.mask = rng.choice(mascaras)
    elif kind == "text":
        capa.text = rng.choice(["", "Hola", "Una frase bastante larga para que corte líneas", "A\nB"])
        capa.font_size = rng.choice([1, 12, 40, 200])
        capa.align = rng.choice(["left", "center", "right"])
        capa.bold, capa.italic, capa.uppercase = rng.random() < .5, rng.random() < .5, rng.random() < .5
    elif kind == "shape":
        capa.shape = rng.choice(SHAPES)
        capa.stroke, capa.stroke_width = rng.choice([None, "#00f"]), rng.uniform(0, 30)
        capa.fill = rng.choice([None, "#f00"])
        capa.corner_radius = rng.uniform(0, 100)
    else:
        capa.adjustments = Adjustments(saturation=rng.uniform(-100, 100), exposure=rng.uniform(-100, 100))
        if rng.random() < 0.5:
            capa.mask = rng.choice(mascaras)
    return capa


@pytest.mark.parametrize("semilla", range(40))
def test_documentos_al_azar_no_truenan(semilla):
    rng = random.Random(semilla)
    st = AssetStore()
    ids = [st.put(colorido(60, 40)), st.put(ruido(7, 9, semilla)), st.put(np.zeros((1, 1, 4), np.uint8) + 255)]
    masc = [st.put(np.full((5, 8), 128, np.uint8)), st.put(np.zeros((1, 1), np.uint8)), st.put(np.full((60, 40), 255, np.uint8))]
    doc = Document(rng.choice([1, 2, 50, 100, 160]), rng.choice([1, 3, 50, 100, 120]), rng.choice([None, "#336699", "#80ffffff"]))
    doc.layers = [_capa_al_azar(rng, st, ids, masc) for _ in range(rng.randint(0, 8))]
    r = Renderer(st, max_cache_bytes=rng.choice([0, 200_000, 512 * 1024 * 1024]))
    for escala in (1.0, 0.5, 0.01, 1.7):
        out = r.render(doc, escala)
        assert out.dtype == np.uint8
        assert out.shape == (max(1, round(doc.height * escala)), max(1, round(doc.width * escala)), 4)
        out2 = r.render(doc, escala)                      # con la caché caliente da exactamente lo mismo
        assert np.array_equal(out, out2)
    assert np.array_equal(r.render(doc, 0.5), Renderer(st).render(doc, 0.5))
    r.render(doc, 1.0, original=True)
    r.render(doc, 1.0, hide={c.id for c in doc.layers[:2]})
    r.thumbnail(doc, 16)
