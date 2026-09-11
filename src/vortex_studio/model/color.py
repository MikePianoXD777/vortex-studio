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


@dataclass
class ColorAdjust:
    """Corrección de color de un clip, en las unidades de la interfaz."""

    brightness: int = 0     # -100 a 100
    contrast: int = 100     # 0 a 200, 100 = sin cambio
    saturation: int = 100   # 0 a 200, 100 = sin cambio
    gamma: int = 100        # 10 a 300, 100 = sin cambio

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, no vale la pena montar el filtro."""
        return (self.brightness, self.contrast, self.saturation, self.gamma) == (0, 100, 100, 100)

    def reset(self) -> None:
        self.brightness, self.contrast, self.saturation, self.gamma = 0, 100, 100, 100

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

    def copy(self) -> ColorAdjust:
        return ColorAdjust(self.brightness, self.contrast, self.saturation, self.gamma)
