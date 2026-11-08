"""PROVISIONAL: tamaños y textos de ejemplo."""

from __future__ import annotations

from vortex_studio.photo.document import KIND_TEXT, Layer, Transform

SIZES: list[tuple[str, str, int, int]] = [
    ("Redes sociales", "Post de Instagram", 1080, 1080),
    ("Redes sociales", "Historia / Reel", 1080, 1920),
    ("Redes sociales", "Portada de YouTube", 1280, 720),
    ("Redes sociales", "Post de Facebook", 1200, 630),
    ("Imprimir", "Póster A4", 2480, 3508),
    ("Pantalla", "Full HD", 1920, 1080),
]


def text_presets() -> list[tuple[str, Layer]]:
    def t(texto, tam, neg, ancho):
        return Layer(kind=KIND_TEXT, name=texto, text=texto, font_size=tam, bold=neg,
                     color="#111111", transform=Transform(0, 0, ancho, tam * 1.3))
    return [("Agregar un título", t("Agregar un título", 96, True, 700)),
            ("Agregar un subtítulo", t("Agregar un subtítulo", 56, True, 600)),
            ("Agregar un poco de texto de cuerpo", t("Agregar un poco de texto de cuerpo", 32, False, 500))]
