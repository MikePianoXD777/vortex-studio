"""Ajustes de color. Python puro: aquí no se procesa nada, solo se guardan
los valores. Quien los aplica es `media/color.py` con filtros de FFmpeg.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vortex_studio.model.curves import Curves

# Rangos tal como se ven en la interfaz. El neutro de cada uno es el valor
# en que el ajuste no hace nada.
BRIGHTNESS = (-100, 100, 0)
CONTRAST = (0, 200, 100)
SATURATION = (0, 200, 100)
GAMMA = (10, 300, 100)
TEMPERATURE = (-100, 100, 0)
VIGNETTE = (0, 100, 0)
CURVE_POINT = (-100, 100, 0)

# Ángulo máximo que se le pasa al filtro `vignette`. Medido a ojo sobre un
# plano parejo de 16:9: más allá de esto las esquinas se van a negro y el
# control deja de servir para nada.
VIGNETTE_ANGLE = 0.85


@dataclass
class ColorAdjust:
    """Corrección de color de un clip, en las unidades de la interfaz."""

    brightness: int = 0     # -100 a 100
    contrast: int = 100     # 0 a 200, 100 = sin cambio
    saturation: int = 100   # 0 a 200, 100 = sin cambio
    gamma: int = 100        # 10 a 300, 100 = sin cambio
    temperature: int = 0    # -100 frío, 100 cálido
    vignette: int = 0       # 0 a 100, oscurece las esquinas
    curves: Curves = field(default_factory=Curves)

    @property
    def signature(self) -> tuple:
        """Todo lo que cambia la imagen, en una tupla que se puede comparar.

        Un solo lugar para esto, porque ya hubo un bug por tenerlo repetido:
        el decodificador comparaba solo brillo, contraste, saturación y
        gamma. Con el video en pausa, mover la temperatura, la viñeta o la
        curva no se reconocía como "mismo cuadro, otro color", y en vez de
        recolorear el cuadro que ya tenía, decodificaba el siguiente: el
        preview avanzaba un cuadro con cada movimiento del deslizador.
        """
        return (self.brightness, self.contrast, self.saturation, self.gamma,
                self.temperature, self.vignette, tuple(self.curves.points()))

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, no vale la pena montar el filtro."""
        return ((self.brightness, self.contrast, self.saturation,
                 self.gamma, self.temperature, self.vignette)
                == (0, 100, 100, 100, 0, 0)
                and self.curves.is_neutral)

    def reset(self) -> None:
        self.brightness, self.contrast, self.saturation = 0, 100, 100
        self.gamma, self.temperature = 100, 0
        self.vignette = 0
        self.curves.reset()

    # --- conversión a los factores que espera FFmpeg ----------------------

    @property
    def brightness_offset(self) -> float:
        """De -100..100 a un corrimiento de -255..255 sobre el valor del pixel."""
        return self.brightness * 2.55

    @property
    def contrast_factor(self) -> float:
        return self.contrast / 100.0

    @property
    def saturation_factor(self) -> float:
        return self.saturation / 100.0

    @property
    def gamma_value(self) -> float:
        return self.gamma / 100.0

    @property
    def warmth(self) -> float:
        """De -100..100 al desplazamiento que espera `colorbalance`.

        Cálido sube el rojo y baja el azul; frío al revés. Se aplica a los
        medios tonos, no a las luces ni a las sombras, que es donde el ojo
        lee la temperatura de una escena.
        """
        return self.temperature / 400.0

    @property
    def vignette_angle(self) -> float:
        """De 0..100 al ángulo que espera el filtro `vignette`."""
        return max(0, min(100, self.vignette)) / 100.0 * VIGNETTE_ANGLE

    def copy(self) -> ColorAdjust:
        return ColorAdjust(self.brightness, self.contrast, self.saturation,
                           self.gamma, self.temperature, self.vignette,
                           self.curves.copy())

    def apply(self, otro: "ColorAdjust") -> None:
        self.brightness, self.contrast = otro.brightness, otro.contrast
        self.saturation, self.gamma = otro.saturation, otro.gamma
        self.temperature = otro.temperature
        self.vignette = otro.vignette
        self.curves.apply(otro.curves)


# Looks de un clic. Son combinaciones de los mismos controles, no filtros
# aparte: así el usuario puede partir de uno y seguir ajustando a mano.
#
# Los que imitan cine traen curva y viñeta, que es de donde sale el "se ve
# como película": los negros lavados y las esquinas un poco cerradas. Con
# puros brillo y contraste el look se queda a medias.
LOOKS = {
    "Ninguno": ColorAdjust(),
    "Cálido": ColorAdjust(temperature=45, saturation=112, contrast=105),
    "Frío": ColorAdjust(temperature=-45, saturation=108, contrast=106),
    "Cine": ColorAdjust(contrast=112, saturation=88, gamma=96, temperature=18,
                        vignette=22, curves=Curves(blacks=14, shadows=4,
                                                   highs=-8, whites=-10)),
    "Vívido": ColorAdjust(saturation=148, contrast=115, brightness=4,
                          curves=Curves(shadows=-12, highs=12)),
    "Suave": ColorAdjust(contrast=88, gamma=112, saturation=94, brightness=6,
                         curves=Curves(blacks=10, highs=-6)),
    "Blanco y negro": ColorAdjust(saturation=0, contrast=108,
                                  curves=Curves(shadows=-14, highs=14)),
    "Noche": ColorAdjust(brightness=-18, temperature=-30, gamma=88,
                         saturation=80, vignette=38,
                         curves=Curves(blacks=8, highs=-12)),
}
