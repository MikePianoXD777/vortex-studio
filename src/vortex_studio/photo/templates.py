"""Tamaños de lienzo comunes y textos prediseñados."""

from __future__ import annotations

from .document import Layer, Transform

# (grupo, nombre, ancho, alto) en píxeles. Impresos a 300 ppp.
SIZES: list[tuple[str, str, int, int]] = [
    ("Redes sociales", "Instagram publicación", 1080, 1080),
    ("Redes sociales", "Instagram vertical 4:5", 1080, 1350),
    ("Redes sociales", "Instagram historia", 1080, 1920),
    ("Redes sociales", "TikTok", 1080, 1920),
    ("Redes sociales", "Facebook publicación", 1200, 630),
    ("Redes sociales", "Facebook portada", 820, 312),
    ("Redes sociales", "X (Twitter) publicación", 1600, 900),
    ("Redes sociales", "LinkedIn publicación", 1200, 627),
    ("Redes sociales", "Pinterest pin", 1000, 1500),
    ("Video", "YouTube miniatura", 1280, 720),
    ("Video", "YouTube banner", 2560, 1440),
    ("Video", "Full HD", 1920, 1080),
    ("Video", "4K", 3840, 2160),
    ("Presentación", "Presentación 16:9", 1920, 1080),
    ("Presentación", "Presentación 4:3", 1600, 1200),
    ("Impresión", "A4 (300 ppp)", 2480, 3508),
    ("Impresión", "Carta (300 ppp)", 2550, 3300),
    ("Impresión", "Foto 4×6 (300 ppp)", 1800, 1200),
    ("Impresión", "Foto 5×7 (300 ppp)", 2100, 1500),
    ("Impresión", "Tarjeta de presentación (300 ppp)", 1050, 600),
    ("Web", "Banner", 1500, 500),
    ("Web", "Banner largo", 728, 90),
    ("Web", "Icono de app", 1024, 1024),
]

# nombre, texto, tamaño, negrita, alto de la caja (se ajusta con text_height al usarlo)
_PRESETS = [
    ("Agregar un título", "Agregar un título", 96, True),
    ("Agregar un subtítulo", "Agregar un subtítulo", 56, False),
    ("Agregar un cuerpo de texto", "Agregar un cuerpo de texto", 36, False),
]


def text_presets() -> list[tuple[str, Layer]]:
    """Capas de texto listas para insertar (centradas en el origen: la
    interfaz las coloca en el lienzo). El alto de la caja ya está ajustado."""
    from .text import text_height
    salida = []
    for nombre, texto, tam, negrita in _PRESETS:
        capa = Layer(kind="text", name=nombre, text=texto, font_size=float(tam), bold=negrita,
                     color="#222222", align="center",
                     transform=Transform(cx=0.0, cy=0.0, width=float(max(560, tam * 9)), height=float(tam)))
        capa.transform.height = float(text_height(capa))
        salida.append((nombre, capa))
    return salida
