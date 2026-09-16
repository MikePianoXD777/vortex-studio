"""Keyframes con interpolación: lineal, suave, sostenida y bezier.

Un keyframe es `[tiempo, valor]`, o `[tiempo, valor, interpolación]`, o
`[tiempo, valor, "Bezier", [x1, y1, x2, y2]]`. La interpolación de un
keyframe manda en el tramo que **empieza** en él, como en After Effects: el
tramo del keyframe 2 al 3 lo decide el 2.

Sin interpolación escrita se usa la de omisión de quien pregunta. Así los
proyectos anteriores a la 0.5, que guardaban `[t, v]`, se siguen viendo
igual sin migrar nada.

La bezier es una función de tiempo como las de CSS: los dos puntos de
control dicen cómo se reparte el avance dentro del tramo. `(0.33, 0, 0.67,
1)` es un suave; `(0, 0, 0.2, 1)` arranca de golpe y frena largo.

Python puro, con una versión en NumPy para evaluar muchos instantes de un
jalón: el volumen animado se calcula muestra por muestra.
"""

from __future__ import annotations

import math

import numpy as np

LINEAR = "Lineal"
EASE = "Suave"
HOLD = "Sostenida"
BEZIER = "Bezier"
INTERPOLATIONS = (LINEAR, EASE, HOLD, BEZIER)

DEFAULT_HANDLES = (0.33, 0.0, 0.67, 1.0)
TIME_TOLERANCE = 1e-4


def time_of(key) -> float:
    return float(key[0])


def value_of(key) -> float:
    return float(key[1])


def interp_of(key, default: str = EASE) -> str:
    if len(key) > 2 and key[2] in INTERPOLATIONS:
        return key[2]
    return default


def handles_of(key) -> tuple[float, float, float, float]:
    if len(key) > 3 and key[3] and len(key[3]) == 4:
        x1, y1, x2, y2 = (float(v) for v in key[3])
        return (min(1.0, max(0.0, x1)), y1, min(1.0, max(0.0, x2)), y2)
    return DEFAULT_HANDLES


# --- las curvas de avance ----------------------------------------------------

def smooth(p):
    """Suave: arranca y frena. La curva de siempre de Vortex Studio."""
    return p * p * (3.0 - 2.0 * p)


def _bezier_coord(t, a, b):
    """Un eje de una bezier cúbica con extremos en 0 y 1."""
    u = 1.0 - t
    return 3.0 * u * u * t * a + 3.0 * u * t * t * b + t * t * t


def bezier(p, handles):
    """El avance del valor para un avance de tiempo `p`, con esos controles.

    Se busca el parámetro de la curva cuya x es `p` por bisección: con los
    controles en x dentro de [0, 1] la x es monótona, así que 30 pasos dan
    precisión de sobra y nunca se va de lado como Newton con controles
    extremos. Funciona igual con un número que con un arreglo.
    """
    x1, y1, x2, y2 = handles
    p = np.clip(np.asarray(p, dtype=np.float64), 0.0, 1.0)
    bajo = np.zeros_like(p)
    alto = np.ones_like(p)
    for _ in range(30):
        medio = (bajo + alto) / 2.0
        x = _bezier_coord(medio, x1, x2)
        menor = x < p
        bajo = np.where(menor, medio, bajo)
        alto = np.where(menor, alto, medio)
    y = _bezier_coord((bajo + alto) / 2.0, y1, y2)
    return float(y) if y.ndim == 0 else y


def progress(p, interp: str, handles=DEFAULT_HANDLES):
    if interp == LINEAR:
        return p
    if interp == HOLD:
        return np.zeros_like(p) if isinstance(p, np.ndarray) else 0.0
    if interp == BEZIER:
        return bezier(p, handles)
    return smooth(p)


# --- evaluar -----------------------------------------------------------------

def evaluate(points, local: float, default_interp: str = EASE) -> float:
    """El valor en `local`. Fuera del primero y el último, se sostiene."""
    if not points:
        raise ValueError("sin keyframes")
    if local <= time_of(points[0]):
        return value_of(points[0])
    if local >= time_of(points[-1]):
        return value_of(points[-1])

    for a, b in zip(points, points[1:]):
        t0, t1 = time_of(a), time_of(b)
        if t0 <= local <= t1:
            v0, v1 = value_of(a), value_of(b)
            if t1 - t0 < 1e-9:
                return v1
            interp = interp_of(a, default_interp)
            if interp == HOLD:
                return v1 if local >= t1 else v0
            p = (local - t0) / (t1 - t0)
            return v0 + (v1 - v0) * float(progress(p, interp, handles_of(a)))
    return value_of(points[-1])


def evaluate_many(points, locals_: np.ndarray, default_interp: str = EASE) -> np.ndarray:
    """Lo mismo para muchos instantes a la vez, en NumPy."""
    locals_ = np.asarray(locals_, dtype=np.float64)
    salida = np.full(locals_.shape, value_of(points[0]), dtype=np.float64)
    salida[locals_ >= time_of(points[-1])] = value_of(points[-1])
    for a, b in zip(points, points[1:]):
        t0, t1 = time_of(a), time_of(b)
        if t1 - t0 < 1e-9:
            continue
        tramo = (locals_ >= t0) & (locals_ < t1)
        if not tramo.any():
            continue
        p = (locals_[tramo] - t0) / (t1 - t0)
        interp = interp_of(a, default_interp)
        avance = progress(p, interp, handles_of(a))
        salida[tramo] = value_of(a) + (value_of(b) - value_of(a)) * avance
    return salida


# --- editar -------------------------------------------------------------------

def _sorted(points) -> list:
    return sorted(points, key=time_of)


def set_key(points, local: float, value: float, interp: str | None = None,
            handles=None) -> list:
    """Pone o reemplaza el keyframe de ese instante.

    Si ya había uno ahí, conserva su interpolación salvo que se pida otra:
    mover un deslizador no debe borrar la curva que el usuario ajustó.
    """
    local = round(float(local), 4)
    previo = next((k for k in points if abs(time_of(k) - local) <= TIME_TOLERANCE), None)
    nuevo = [local, float(value)]
    extra_interp = interp if interp is not None else (
        previo[2] if previo is not None and len(previo) > 2 else None)
    extra_handles = handles if handles is not None else (
        previo[3] if previo is not None and len(previo) > 3 else None)
    if extra_interp is not None:
        nuevo.append(extra_interp)
        if extra_interp == BEZIER:
            nuevo.append(list(extra_handles or DEFAULT_HANDLES))
    quedan = [k for k in points if abs(time_of(k) - local) > TIME_TOLERANCE]
    return _sorted(quedan + [nuevo])


# Medio cuadro a 120 fps: lo justo para reconocer "este mismo keyframe" sin
# llevarse el de junto. Con 0.05 s, a 60 fps se borraban tres de un jalón.
def remove_key(points, local: float, tolerance: float = 4e-3) -> list:
    return [k for k in points if abs(time_of(k) - local) > tolerance]


def key_near(points, local: float, tolerance: float = 0.05):
    candidatos = [k for k in points if abs(time_of(k) - local) <= tolerance]
    return min(candidatos, key=lambda k: abs(time_of(k) - local)) if candidatos else None


def set_interpolation(points, local: float, interp: str, handles=None,
                      tolerance: float = 0.05) -> list:
    """Cambia la interpolación del tramo que empieza en ese keyframe."""
    if interp not in INTERPOLATIONS:
        raise ValueError(interp)
    objetivo = key_near(points, local, tolerance)
    salida = []
    for k in points:
        if k is objetivo:
            nuevo = [time_of(k), value_of(k), interp]
            if interp == BEZIER:
                nuevo.append(list(handles or (k[3] if len(k) > 3 and k[3] else DEFAULT_HANDLES)))
            salida.append(nuevo)
        else:
            salida.append(list(k))
    return salida


def move_key(points, local: float, new_local: float, new_value: float,
             tolerance: float = 0.05) -> list:
    """Mueve un keyframe en tiempo y valor, conservando su interpolación.

    Si cae encima de otro, lo reemplaza: dos keyframes en el mismo instante
    no significan nada.
    """
    objetivo = key_near(points, local, tolerance)
    if objetivo is None:
        return [list(k) for k in points]
    resto = [list(k) for k in points if k is not objetivo]
    nuevo = [round(float(new_local), 4), float(new_value), *objetivo[2:]]
    resto = [k for k in resto if abs(time_of(k) - nuevo[0]) > TIME_TOLERANCE]
    return _sorted(resto + [nuevo])


def shift(points, delta: float) -> list:
    return [[round(time_of(k) + delta, 4), *k[1:]] for k in points]


def clean(points) -> list:
    """Solo los keyframes que se pueden evaluar, ordenados.

    Un proyecto editado a mano —o dañado— puede traer `[0]`, textos o
    `NaN`. Cualquiera de esos tronaba al pintar, cuadro tras cuadro. Se
    quedan los que traen tiempo y valor numéricos y finitos, con su
    interpolación si es una que existe.
    """
    if not isinstance(points, (list, tuple)):
        return []
    salida = []
    for k in points:
        if not isinstance(k, (list, tuple)) or len(k) < 2:
            continue
        try:
            t, v = float(k[0]), float(k[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(t) and math.isfinite(v)):
            continue
        nuevo: list = [t, v]
        if len(k) > 2 and k[2] in INTERPOLATIONS:
            nuevo.append(k[2])
            if k[2] == BEZIER and len(k) > 3 and isinstance(k[3], (list, tuple)) \
                    and len(k[3]) == 4:
                try:
                    nuevo.append([float(x) for x in k[3]])
                except (TypeError, ValueError):
                    pass
        salida.append(nuevo)
    return _sorted(salida)
