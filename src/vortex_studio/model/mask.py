"""Máscaras: dejar ver solo una parte de la capa.

Es lo que en After Effects son las máscaras de capa y en CapCut el botón
"Máscara". La versión de aquí tiene cuatro formas y seis controles, no un
editor de trazados con puntos bezier: con eso se cubre lo que de verdad se
usa —tapar una cara, revelar media pantalla, encerrar algo en un círculo—
sin volverse un programa aparte.

Todo va en fracciones del cuadro, como las posiciones de los títulos, para
que una máscara puesta en 1080p siga en su lugar si la secuencia cambia
de formato.
"""

from __future__ import annotations

from dataclasses import dataclass

NONE = "Ninguna"
SHAPES = (NONE, "Rectángulo", "Círculo", "Lineal")

# Qué controles tienen sentido en cada forma. La `Lineal` es un corte recto:
# no tiene tamaño, se define por dónde pasa la línea y hacia dónde apunta.
USES_SIZE = {"Rectángulo", "Círculo"}


@dataclass
class Mask:
    """Qué parte de la capa se ve.

    `feather` es el ancho del degradado del borde, también en fracciones
    del cuadro. Con 0 el borde queda duro y se nota el recorte; el valor por
    omisión trae un poco de suavizado porque es lo que se ve bien casi
    siempre y ahorra tener que buscarlo.
    """

    shape: str = NONE
    x: float = 0.50           # centro de la forma, 0 a 1
    y: float = 0.50
    width: float = 0.60       # ancho como fracción del cuadro
    height: float = 0.60
    rotation: float = 0.0     # grados
    feather: float = 0.03     # ancho del degradado del borde
    invert: bool = False      # tapar lo de dentro en vez de lo de fuera

    @property
    def is_off(self) -> bool:
        """Sin forma no hay máscara, y el compositor se salta el trabajo."""
        return self.shape == NONE or self.shape not in SHAPES

    @property
    def uses_size(self) -> bool:
        return self.shape in USES_SIZE

    def reset(self) -> None:
        self.shape = NONE
        self.x, self.y = 0.50, 0.50
        self.width, self.height = 0.60, 0.60
        self.rotation, self.feather = 0.0, 0.03
        self.invert = False

    def copy(self) -> "Mask":
        return Mask(self.shape, self.x, self.y, self.width, self.height,
                    self.rotation, self.feather, self.invert)
