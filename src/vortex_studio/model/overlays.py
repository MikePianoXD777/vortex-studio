"""Lo que va encima del video: texto e imágenes.

Las dos clases exponen `start`, `duration`, `end`, `name` y `contains()`,
igual que un `Clip`. Así el timeline las dibuja con el mismo código sin
tener que saber de qué tipo es cada cosa.

Las posiciones y los tamaños se guardan relativos al cuadro (0 a 1), no en
pixeles: así un título puesto sobre un video de 720p se sigue viendo en el
mismo lugar si la secuencia cambia a 4K.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vortex_studio.model.animation import DEFAULT_TIME
from vortex_studio.model.blend import NORMAL
from vortex_studio.model.mask import Mask

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


@dataclass(eq=False)
class TimedItem:
    """Lo mínimo para vivir en una pista: cuándo empieza y cuánto dura.

    Como los clips, se comparan por identidad y no por valor: dos subtítulos
    con el mismo texto y la misma duración son dos subtítulos distintos.
    """

    start: float
    duration: float
    fade_in: float = 0.0     # segundos de entrada en fundido
    fade_out: float = 0.0    # segundos de salida

    # Animación de entrada y de salida, por nombre. Ver `model/animation.py`:
    # se guarda el nombre y no los keyframes que genera, para que cambiar una
    # curva no rompa los proyectos ya guardados.
    anim_in: str = "Ninguna"
    anim_out: str = "Ninguna"
    anim_time: float = DEFAULT_TIME

    # Marcadores del elemento, en tiempo relativo a su inicio.
    markers: list = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.start + self.duration

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end

    def fade_at(self, t: float) -> float:
        """Cuánta opacidad le toca en ese instante, de 0 a 1.

        Si los dos fundidos juntos no caben en el clip, se reparten a
        prorrata en vez de encimarse: encimados producen un bajón al centro
        que se ve como un parpadeo.
        """
        entrada, salida = self.fade_in, self.fade_out
        if entrada <= 0 and salida <= 0:
            return 1.0

        total = entrada + salida
        if total > self.duration > 0:
            factor = self.duration / total
            entrada, salida = entrada * factor, salida * factor

        dentro = t - self.start
        alfa = 1.0
        if entrada > 0 and dentro < entrada:
            alfa = min(alfa, max(0.0, dentro / entrada))
        if salida > 0 and dentro > self.duration - salida:
            alfa = min(alfa, max(0.0, (self.duration - dentro) / salida))
        return alfa


@dataclass(eq=False)
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
    outline: bool = True      # contorno, para que se lea sobre cualquier fondo
    background: bool = False  # caja detrás del texto, estilo subtítulo duro

    # Tipografía. Vacío = la fuente de la interfaz, que siempre existe. Se
    # guarda el nombre de la familia y no un archivo: si el proyecto se abre
    # en otra máquina sin esa fuente, Qt pone la más parecida en vez de
    # tronar.
    font: str = ""
    outline_color: str = "#000000"
    outline_width: float = 0.055  # grosor, como fracción del alto de la letra
    shadow: bool = False
    shadow_color: str = "#000000"
    shadow_distance: float = 0.06  # como fracción del alto de la letra
    shadow_blur: float = 0.0       # ídem; 0 = sombra dura
    shadow_opacity: float = 0.75

    @property
    def name(self) -> str:
        first = self.text.strip().splitlines()[0] if self.text.strip() else "(vacío)"
        return first[:28] + ("…" if len(first) > 28 else "")


@dataclass(eq=False)
class ImageOverlay(TimedItem):
    """Una imagen encima del video: logo, marca de agua, gráfico."""

    source: Path = Path()
    x: float = 0.50           # centro de la imagen, 0 a 1
    y: float = 0.50
    scale: float = 0.35       # ancho como fracción del cuadro
    opacity: float = 1.0
    blend: str = NORMAL       # cómo se combina con lo de abajo
    mask: Mask = field(default_factory=Mask)

    def __post_init__(self) -> None:
        self.source = Path(self.source)

    @property
    def name(self) -> str:
        return self.source.stem[:28]
