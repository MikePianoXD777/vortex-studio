"""Curva de color: cinco puntos, no un editor de bezier.

En DaVinci y en Premiere la curva se edita arrastrando puntos sobre una
gráfica, y es de las cosas que más asustan a quien abre un editor por
primera vez. Aquí son cinco deslizadores —negros, sombras, medios, luces y
blancos— y la gráfica se dibuja sola para que uno vea qué está haciendo.

Es la misma capacidad: con esos cinco puntos se arma cualquier curva en S,
se levantan las sombras sin quemar las luces, y se hace el "film look" de
negros lavados. Lo que no se puede es poner un punto donde uno quiera, y a
cambio no hay nada que arrastrar.

Python puro. Quien la aplica es `media/color.py`, con el filtro `curves`
de FFmpeg.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cuánto puede mover un deslizador al máximo, en niveles de 0 a 1.
REACH = 0.30

# Los cinco puntos de anclaje: nombre del campo -> entrada donde manda.
ANCHORS = (
    ("blacks", 0.00),
    ("shadows", 0.25),
    ("mids", 0.50),
    ("highs", 0.75),
    ("whites", 1.00),
)

# Cuántos puntos se le pasan a FFmpeg. Con cinco, su interpolación no es la
# misma que la de aquí y la gráfica del panel mentiría un poco; mandando la
# curva ya muestreada las dos coinciden hasta el redondeo.
SAMPLES = 17


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


@dataclass
class Curves:
    """Los cinco puntos, en las unidades de la interfaz (-100 a 100).

    Cada uno sube o baja la salida en su nivel de entrada. En 0 la curva es
    la diagonal y no hace nada.
    """

    blacks: int = 0
    shadows: int = 0
    mids: int = 0
    highs: int = 0
    whites: int = 0

    @property
    def is_neutral(self) -> bool:
        return (self.blacks, self.shadows, self.mids,
                self.highs, self.whites) == (0, 0, 0, 0, 0)

    def reset(self) -> None:
        self.blacks = self.shadows = self.mids = self.highs = self.whites = 0

    def copy(self) -> "Curves":
        return Curves(self.blacks, self.shadows, self.mids,
                      self.highs, self.whites)

    def apply(self, otra: "Curves") -> None:
        self.blacks, self.shadows = otra.blacks, otra.shadows
        self.mids, self.highs = otra.mids, otra.highs
        self.whites = otra.whites

    # --- la curva ---------------------------------------------------------

    def points(self) -> list[tuple[float, float]]:
        """Los cinco anclajes como pares (entrada, salida), de 0 a 1."""
        return [(x, _clamp(x + getattr(self, campo) / 100.0 * REACH))
                for campo, x in ANCHORS]

    def at(self, x: float) -> float:
        """La salida para la entrada `x`. Es lo que dibuja la gráfica.

        Interpola con Hermite monótono (Fritsch–Carlson) y no con una
        spline natural: la natural se pasa del anclaje entre dos puntos
        muy separados y eso aparece como un rebote de brillo donde el
        usuario no puso nada.
        """
        return _hermite(self.points(), _clamp(x))

    def ffmpeg_points(self) -> str:
        """La curva muestreada, en el formato que espera el filtro `curves`."""
        pares = []
        for indice in range(SAMPLES):
            x = indice / (SAMPLES - 1)
            pares.append(f"{x:.4f}/{self.at(x):.4f}")
        return " ".join(pares)


def _hermite(puntos: list[tuple[float, float]], x: float) -> float:
    """Hermite cúbico con pendientes que no se pasan de los anclajes.

    Las pendientes salen del promedio de las secantes vecinas, recortadas a
    tres veces la secante del tramo. Ese recorte es lo que garantiza que la
    curva no se salga del rango entre dos puntos: sin él, subir mucho las
    luces hacía que los medios bajaran de paso.
    """
    n = len(puntos)
    if n < 2:
        return puntos[0][1] if puntos else x

    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]

    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]

    secantes = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]

    pendientes = [secantes[0]]
    for i in range(1, n - 1):
        if secantes[i - 1] * secantes[i] <= 0:
            pendientes.append(0.0)      # hay un pico: se aplana para no rebotar
        else:
            pendientes.append((secantes[i - 1] + secantes[i]) / 2.0)
    pendientes.append(secantes[-1])

    for i in range(n - 1):
        if abs(secantes[i]) < 1e-12:
            pendientes[i] = pendientes[i + 1] = 0.0      # tramo plano
            continue
        alfa = pendientes[i] / secantes[i]
        beta = pendientes[i + 1] / secantes[i]
        radio = (alfa * alfa + beta * beta) ** 0.5
        if radio > 3.0:
            factor = 3.0 / radio
            pendientes[i] = factor * alfa * secantes[i]
            pendientes[i + 1] = factor * beta * secantes[i]

    for i in range(n - 1):
        if xs[i] <= x <= xs[i + 1]:
            h = xs[i + 1] - xs[i]
            t = (x - xs[i]) / h
            t2, t3 = t * t, t * t * t
            return (
                ys[i] * (2 * t3 - 3 * t2 + 1)
                + h * pendientes[i] * (t3 - 2 * t2 + t)
                + ys[i + 1] * (-2 * t3 + 3 * t2)
                + h * pendientes[i + 1] * (t3 - t2)
            )
    return ys[-1]


# Curvas de un clic, para no arrancar siempre de la diagonal.
CURVE_LOOKS = {
    "Ninguna": Curves(),
    "Contraste en S": Curves(shadows=-28, highs=28),
    "Negros lavados": Curves(blacks=22, shadows=10, highs=-6),
    "Abrir sombras": Curves(shadows=30, mids=12),
    "Bajar luces": Curves(highs=-30, whites=-14),
    "Plano de cine": Curves(blacks=16, shadows=6, highs=-10, whites=-14),
}
