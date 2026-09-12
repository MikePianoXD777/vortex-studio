"""Animaciones de texto listas: entrar deslizando, escribiéndose, apareciendo.

Es lo que hace rápido a CapCut. En After Effects el mismo efecto se arma con
keyframes de posición, escala y opacidad, más un expresión para el efecto de
máquina de escribir; aquí se escoge de una lista y ya.

La animación se calcula, no se guarda: en el archivo del proyecto solo van
el nombre de la entrada, el de la salida y cuánto duran. Guardar keyframes
generados ataría el proyecto a la versión que los generó, y cambiar una
curva rompería los proyectos viejos.

Python puro: la interpolación se prueba sin abrir una ventana, y el
compositor solo pinta lo que esta función le diga.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TIME = 0.45     # segundos que dura la entrada o la salida


@dataclass
class AnimState:
    """Cómo se dibuja el texto en un instante dado.

    `dx` y `dy` van en fracciones del cuadro, igual que las posiciones de
    los títulos, para que una animación se vea igual en 720p y en 4K.

    `chars` es la fracción del texto que ya se escribió: 1.0 es todo. Solo
    la mueve la máquina de escribir; las demás animaciones la dejan en 1.
    """

    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0
    chars: float = 1.0

    @property
    def is_neutral(self) -> bool:
        return (abs(self.dx) < 1e-6 and abs(self.dy) < 1e-6
                and abs(self.scale - 1.0) < 1e-6
                and abs(self.opacity - 1.0) < 1e-6
                and self.chars >= 1.0)


def _smooth(p: float) -> float:
    """La misma curva que usan los keyframes, para que todo se mueva igual.

    Ver `model/transform.py`: un movimiento lineal arranca y frena de golpe
    y delata que lo hizo una máquina.
    """
    return p * p * (3.0 - 2.0 * p)


def _ease_out(p: float) -> float:
    """Entra rápido y frena al final. Es el que se siente ágil al entrar."""
    return 1.0 - (1.0 - p) ** 3


# Cada animación es una función de avance (0 = empezando, 1 = ya en su
# lugar) a un `AnimState`. Se escriben para la ENTRADA; la salida usa la
# misma con el avance al revés, así no hay que definir cada una dos veces.
def _aparecer(p: float) -> AnimState:
    return AnimState(opacity=_smooth(p))


def _deslizar(dx: float, dy: float):
    def anim(p: float) -> AnimState:
        avance = _ease_out(p)
        return AnimState(dx=dx * (1.0 - avance), dy=dy * (1.0 - avance),
                         opacity=min(1.0, p * 1.6))
    return anim


def _acercarse(p: float) -> AnimState:
    """El rebote de CapCut: se pasa un poco de tamaño y regresa.

    Pasarse del 100 % y volver es lo que lo hace ver hecho a mano. Sin ese
    sobretiro el texto solo crece y se ve barato.
    """
    avance = _ease_out(p)
    return AnimState(scale=0.55 + 0.52 * avance - 0.07 * _smooth(p),
                     opacity=min(1.0, p * 2.0))


def _alejarse(p: float) -> AnimState:
    avance = _ease_out(p)
    return AnimState(scale=1.6 - 0.6 * avance, opacity=min(1.0, p * 2.0))


def _escribiendose(p: float) -> AnimState:
    """Máquina de escribir. Sin fundido: el fundido delata que es un truco."""
    return AnimState(chars=p)


def _subir(p: float) -> AnimState:
    avance = _ease_out(p)
    return AnimState(dy=0.09 * (1.0 - avance), opacity=_smooth(p))


TEXT_ANIMS = {
    "Ninguna": None,
    "Aparecer": _aparecer,
    "Subir": _subir,
    "Escribiéndose": _escribiendose,
    "Acercarse": _acercarse,
    "Alejarse": _alejarse,
    "Desde la izquierda": _deslizar(-0.35, 0.0),
    "Desde la derecha": _deslizar(0.35, 0.0),
    "Desde arriba": _deslizar(0.0, -0.25),
    "Desde abajo": _deslizar(0.0, 0.25),
}

# La salida ofrece las mismas, salvo la máquina de escribir: des-escribirse
# se ve como un error, no como un efecto.
OUT_ANIMS = tuple(n for n in TEXT_ANIMS if n != "Escribiéndose")
IN_ANIMS = tuple(TEXT_ANIMS)


def anim_state(item, t: float) -> AnimState:
    """Cómo se dibuja `item` en el instante `t` de la línea de tiempo.

    Si las dos animaciones juntas no caben en el elemento, se reparten a
    prorrata — la misma cuenta que los fundidos, por la misma razón: si se
    encimaran, el texto nunca llegaría a estar quieto en su lugar.
    """
    entrada = TEXT_ANIMS.get(getattr(item, "anim_in", "Ninguna"))
    salida = TEXT_ANIMS.get(getattr(item, "anim_out", "Ninguna"))
    if entrada is None and salida is None:
        return AnimState()

    duracion = max(0.0, getattr(item, "duration", 0.0))
    tiempo = max(0.0, getattr(item, "anim_time", DEFAULT_TIME))
    if tiempo <= 0 or duracion <= 0:
        return AnimState()

    cuantas = (1 if entrada else 0) + (1 if salida else 0)
    tiempo = min(tiempo, duracion / cuantas)

    dentro = t - getattr(item, "start", 0.0)

    if entrada is not None and dentro < tiempo:
        return entrada(max(0.0, min(1.0, dentro / tiempo)))
    if salida is not None and dentro > duracion - tiempo:
        restante = (duracion - dentro) / tiempo
        return salida(max(0.0, min(1.0, restante)))
    return AnimState()


def visible_text(text: str, chars: float) -> str:
    """El texto recortado a la fracción que ya se escribió.

    Se cuenta sobre el texto entero y no renglón por renglón: así un
    subtítulo de dos renglones se escribe de corrido, como lo haría alguien
    tecleándolo, en vez de los dos a la vez.
    """
    if chars >= 1.0:
        return text
    if chars <= 0.0:
        return ""
    return text[: max(0, round(len(text) * chars))]
