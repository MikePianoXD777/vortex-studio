"""Ajustes de color. Python puro: aquí no se procesa nada, solo se guardan
los valores. Quien los aplica es `media/color.py` con filtros de FFmpeg.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rangos tal como se ven en la interfaz. El neutro de cada uno es el valor
# en que el ajuste no hace nada.
BRIGHTNESS = (-100, 100, 0)
CONTRAST = (0, 200, 100)
SATURATION = (0, 200, 100)
GAMMA = (10, 300, 100)
TEMPERATURE = (-100, 100, 0)


@dataclass
class ColorAdjust:
    """Corrección de color de un clip, en las unidades de la interfaz."""

    brightness: int = 0     # -100 a 100
    contrast: int = 100     # 0 a 200, 100 = sin cambio
    saturation: int = 100   # 0 a 200, 100 = sin cambio
    gamma: int = 100        # 10 a 300, 100 = sin cambio
    temperature: int = 0    # -100 frío, 100 cálido

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, no vale la pena montar el filtro."""
        return (self.brightness, self.contrast, self.saturation,
                self.gamma, self.temperature) == (0, 100, 100, 100, 0)

    def reset(self) -> None:
        self.brightness, self.contrast, self.saturation = 0, 100, 100
        self.gamma, self.temperature = 100, 0

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

    def copy(self) -> ColorAdjust:
        return ColorAdjust(self.brightness, self.contrast, self.saturation,
                           self.gamma, self.temperature)

    def apply(self, otro: "ColorAdjust") -> None:
        self.brightness, self.contrast = otro.brightness, otro.contrast
        self.saturation, self.gamma = otro.saturation, otro.gamma
        self.temperature = otro.temperature


# Looks de un clic. Son combinaciones de los mismos controles, no filtros
# aparte: así el usuario puede partir de uno y seguir ajustando a mano.
LOOKS = {
    "Ninguno": ColorAdjust(),
    "Cálido": ColorAdjust(temperature=45, saturation=112, contrast=105),
    "Frío": ColorAdjust(temperature=-45, saturation=108, contrast=106),
    "Cine": ColorAdjust(contrast=118, saturation=88, gamma=94, temperature=18),
    "Vívido": ColorAdjust(saturation=148, contrast=115, brightness=4),
    "Suave": ColorAdjust(contrast=88, gamma=112, saturation=94, brightness=6),
    "Blanco y negro": ColorAdjust(saturation=0, contrast=112),
    "Noche": ColorAdjust(brightness=-18, temperature=-30, gamma=88, saturation=80),
}
