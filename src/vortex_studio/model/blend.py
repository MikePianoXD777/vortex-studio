"""Modos de fusión: cómo se combina una capa con lo que tiene debajo.

Aquí solo vive la lista de nombres. La traducción al modo de composición de
Qt está en `ui/compositor.py`, para que el modelo siga sin saber que Qt
existe — que es lo que permite probar la lógica de edición sin abrir una
ventana.

Los nombres van en español porque son los que ve el usuario. Van en el
orden de siempre en un editor: primero los que oscurecen, luego los que
aclaran, luego los de contraste, y al final los raros.
"""

from __future__ import annotations

NORMAL = "Normal"

BLENDS = (
    NORMAL,
    "Multiplicar",
    "Oscurecer",
    "Subexponer",
    "Trama",
    "Aclarar",
    "Sobreexponer",
    "Sumar",
    "Superponer",
    "Luz fuerte",
    "Luz suave",
    "Diferencia",
    "Exclusión",
)


def is_normal(name: str) -> bool:
    """Cualquier nombre que no conozcamos se trata como normal.

    Un proyecto guardado con una versión más nueva puede traer un modo que
    esta no tenga. Más vale que la capa se vea de más que que desaparezca.
    """
    return name == NORMAL or name not in BLENDS
