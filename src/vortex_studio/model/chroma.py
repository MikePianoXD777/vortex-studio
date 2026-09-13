"""Llave de croma: quitar el fondo verde o azul, con supresión de derrame.

Python puro: aquí solo se guardan los valores. Quien la aplica es
`media/color.py`, con los filtros `colorkey` y `despill` de FFmpeg.

Tres controles y no los doce de un keyer de Resolve, porque con estos se
resuelve una toma de pantalla verde decente:

- **similitud**: qué tan lejos del color de la llave todavía cuenta como
  fondo. Poco deja bordes verdes; mucho se come el pelo;
- **suavidad**: el ancho de la orilla semitransparente;
- **derrame**: cuánto del verde que rebota en la piel y en la ropa se
  neutraliza. Sin eso la persona recortada se ve con un halo verde.
"""

from __future__ import annotations

from dataclasses import dataclass

SIMILARITY = (1, 100, 30)
SMOOTHNESS = (0, 100, 10)
SPILL = (0, 100, 50)
PRESETS = {"Verde": "#00b140", "Azul": "#0047bb"}


@dataclass
class ChromaKey:
    enabled: bool = False
    color: str = "#00b140"
    similarity: int = 30
    smoothness: int = 10
    spill: int = 50

    @property
    def is_on(self) -> bool:
        return self.enabled

    @property
    def signature(self) -> tuple:
        if not self.enabled:
            return ()
        return (self.color.lower(), self.similarity, self.smoothness, self.spill)

    @property
    def rgb(self) -> tuple[int, int, int]:
        texto = self.color.lstrip("#")
        return tuple(int(texto[i:i + 2], 16) for i in (0, 2, 4))

    @property
    def spill_type(self) -> str:
        """`despill` solo sabe de verde o azul: se elige por el canal dominante."""
        r, g, b = self.rgb
        return "blue" if b > g else "green"

    def copy(self) -> "ChromaKey":
        return ChromaKey(self.enabled, self.color, self.similarity, self.smoothness, self.spill)

    def reset(self) -> None:
        self.enabled, self.color = False, PRESETS["Verde"]
        self.similarity, self.smoothness, self.spill = 30, 10, 50
