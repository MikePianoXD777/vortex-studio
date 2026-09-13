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
EXPOSURE = (-300, 300, 0)      # centésimas de paso: 100 = el doble de luz
TINT = (-100, 100, 0)          # negativo verde, positivo magenta
LIFT = (-100, 100, 0)          # sombras, por canal
GAMMA_CH = (20, 300, 100)      # medios, por canal
GAIN = (0, 200, 100)           # luces, por canal
LUT_INTENSITY = (0, 100, 100)
CHANNELS = ("r", "g", "b")

# Espacio de color del material. Vacío es Rec.709 normal, que no se toca.
# Ver `media/colorspace.py`.
SPACE_NONE = ""
SPACE_PQ = "Rec.2020 PQ (HDR10)"
SPACE_HLG = "Rec.2020 HLG"
SPACE_OCIO = "OCIO"
INPUT_SPACES = (SPACE_NONE, SPACE_PQ, SPACE_HLG, SPACE_OCIO)

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

    # Nivel 3: exposición y tinte, y las tres ruedas de DaVinci en su forma
    # de deslizadores —lift para las sombras, gamma para los medios y gain
    # para las luces—, un trío por canal.
    exposure: int = 0       # -300 a 300: centésimas de paso de diafragma
    tint: int = 0           # -100 verde, 100 magenta
    lift_r: int = 0
    lift_g: int = 0
    lift_b: int = 0
    gamma_r: int = 100
    gamma_g: int = 100
    gamma_b: int = 100
    gain_r: int = 100
    gain_g: int = 100
    gain_b: int = 100

    # LUT .cube: la ruta y cuánto se mezcla con la imagen sin LUT.
    lut: str = ""
    lut_intensity: int = 100

    # Nivel 4. Efectos de plugins, en orden: `[{"plugin", "values", "enabled"}]`
    # (ver `model/plugins.py`). Viven en el color y no aparte porque son lo
    # mismo: filtros de FFmpeg en la cadena de cada cuadro, y así viajan solos
    # al decodificador, a la exportación y a la capa de ajuste.
    effects: list = field(default_factory=list)
    input_space: str = SPACE_NONE
    ocio_config: str = ""       # vacío: la configuración de estudio que trae OCIO
    ocio_space: str = ""

    @property
    def effects_signature(self) -> tuple:
        return tuple((e.get("plugin", ""), tuple(sorted((e.get("values") or {}).items())),
                      bool(e.get("enabled", True))) for e in self.effects)

    @property
    def has_effects(self) -> bool:
        return any(e.get("enabled", True) for e in self.effects)

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
                self.temperature, self.vignette, tuple(self.curves.points()),
                self.exposure, self.tint, self.lgg, self.lut, self.lut_intensity,
                self.effects_signature, self.input_space, self.ocio_config, self.ocio_space)

    @property
    def lgg(self) -> tuple:
        return tuple(getattr(self, f"{g}_{c}") for g in ("lift", "gamma", "gain")
                     for c in CHANNELS)

    @property
    def lgg_is_neutral(self) -> bool:
        return self.lgg == (0, 0, 0, 100, 100, 100, 100, 100, 100)

    @property
    def has_lut(self) -> bool:
        return bool(self.lut) and self.lut_intensity > 0

    def channel_lgg(self, canal: str) -> tuple[float, float, float]:
        """(lift, gamma, gain) de un canal, en las unidades de la fórmula."""
        return (getattr(self, f"lift_{canal}") / 400.0,
                max(0.2, getattr(self, f"gamma_{canal}") / 100.0),
                getattr(self, f"gain_{canal}") / 100.0)

    @property
    def exposure_factor(self) -> float:
        return 2.0 ** (self.exposure / 100.0)

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, no vale la pena montar el filtro."""
        return ((self.brightness, self.contrast, self.saturation,
                 self.gamma, self.temperature, self.vignette,
                 self.exposure, self.tint)
                == (0, 100, 100, 100, 0, 0, 0, 0)
                and self.curves.is_neutral and self.lgg_is_neutral
                and not self.has_lut and not self.has_effects and not self.input_space)

    def reset(self) -> None:
        self.brightness, self.contrast, self.saturation = 0, 100, 100
        self.gamma, self.temperature = 100, 0
        self.vignette = 0
        self.curves.reset()
        self.exposure = self.tint = 0
        for c in CHANNELS:
            setattr(self, f"lift_{c}", 0)
            setattr(self, f"gamma_{c}", 100)
            setattr(self, f"gain_{c}", 100)
        self.lut, self.lut_intensity = "", 100
        self.effects = []
        self.input_space, self.ocio_config, self.ocio_space = SPACE_NONE, "", ""

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
        copia = ColorAdjust(self.brightness, self.contrast, self.saturation,
                            self.gamma, self.temperature, self.vignette,
                            self.curves.copy())
        copia.apply_extras(self)
        return copia

    def apply_extras(self, otro: "ColorAdjust") -> None:
        self.exposure, self.tint = otro.exposure, otro.tint
        for g in ("lift", "gamma", "gain"):
            for c in CHANNELS:
                setattr(self, f"{g}_{c}", getattr(otro, f"{g}_{c}"))
        self.lut, self.lut_intensity = otro.lut, otro.lut_intensity
        self.effects = [{"plugin": e.get("plugin", ""), "values": dict(e.get("values") or {}),
                         "enabled": bool(e.get("enabled", True))} for e in otro.effects]
        self.input_space, self.ocio_config = otro.input_space, otro.ocio_config
        self.ocio_space = otro.ocio_space

    def apply(self, otro: "ColorAdjust") -> None:
        self.brightness, self.contrast = otro.brightness, otro.contrast
        self.saturation, self.gamma = otro.saturation, otro.gamma
        self.temperature = otro.temperature
        self.vignette = otro.vignette
        self.curves.apply(otro.curves)
        self.apply_extras(otro)


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
