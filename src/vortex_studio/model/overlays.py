"""Lo que va encima del video: texto e imágenes.

Las dos clases exponen `start`, `duration`, `end`, `name` y `contains()`,
igual que un `Clip`. Así el timeline las dibuja con el mismo código sin
tener que saber de qué tipo es cada cosa.

Las posiciones y los tamaños se guardan relativos al cuadro (0 a 1), no en
pixeles: así un título puesto sobre un video de 720p se sigue viendo en el
mismo lugar si la secuencia cambia a 4K.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ALIGNMENTS = ("izquierda", "centro", "derecha")

# Posiciones de uso común, como fracción del cuadro.
ANCHORS = {
    "Arriba izquierda": (0.06, 0.10),
    "Arriba centro": (0.50, 0.10),
    "Arriba derecha": (0.94, 0.10),
    "Centro izquierda": (0.06, 0.50),
    "Centro": (0.50, 0.50),
    "Centro derecha": (0.94, 0.50),
    "Abajo izquierda": (0.06, 0.88),
    "Subtítulo": (0.50, 0.88),
    "Abajo derecha": (0.94, 0.88),
}


@dataclass
class TimedItem:
    """Lo mínimo para vivir en una pista: cuándo empieza y cuánto dura."""

    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end


@dataclass
class Title(TimedItem):
    """Un texto sobre el video: título o subtítulo."""

    text: str = "Texto"
    x: float = 0.50           # posición del ancla, 0 a 1
    y: float = 0.88
    size: float = 0.075       # altura de la letra como fracción del cuadro
    color: str = "#ffffff"
    align: str = "centro"
    bold: bool = True
    italic: bool = False
    outline: bool = True      # contorno oscuro, para que se lea sobre cualquier fondo
    background: bool = False  # caja detrás del texto, estilo subtítulo duro

    @property
    def name(self) -> str:
        first = self.text.strip().splitlines()[0] if self.text.strip() else "(vacío)"
        return first[:28] + ("…" if len(first) > 28 else "")


@dataclass
class ImageOverlay(TimedItem):
    """Una imagen encima del video: logo, marca de agua, gráfico."""

    source: Path = Path()
    x: float = 0.50           # centro de la imagen, 0 a 1
    y: float = 0.50
    scale: float = 0.35       # ancho como fracción del cuadro
    opacity: float = 1.0

    def __post_init__(self) -> None:
        self.source = Path(self.source)

    @property
    def name(self) -> str:
        return self.source.stem[:28]
