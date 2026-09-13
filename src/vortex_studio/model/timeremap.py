"""Remapeo de tiempo: la velocidad cambia dentro del mismo clip.

Es el Remapeo de tiempo de Premiere y la curva de velocidad de CapCut: el
clip va normal, frena a cámara lenta en el golpe y vuelve a arrancar.

Se guarda como keyframes de la ruta `time` en `clip.anim`. Cada keyframe
dice, en ese instante del clip (tiempo local), **qué segundo del material se
ve**, medido desde el punto de entrada. Entre dos keyframes la cuenta es
lineal, así que la pendiente del tramo es la velocidad: de `[0, 0]` a
`[2, 4]` son dos segundos de clip que recorren cuatro de material, a 2×. Un
tramo plano es un cuadro congelado. Con interpolación suave en un keyframe,
la velocidad arranca y frena sola: una rampa.

Por qué keyframes de tiempo y no una lista de velocidades por tramo:
`Clip.source_time` —la única cuenta que usan el preview, la exportación, el
corte y el audio para saber qué cuadro va— queda bien con cambiar una línea,
y el editor de curvas de la 0.5 ya los edita sin saber que son tiempo.

Python puro.
"""

from __future__ import annotations

from vortex_studio.model import keyframes as kf

TIME = "time"
MAX_SPEED = 4.0


def keys(clip) -> list:
    return list((getattr(clip, "anim", None) or {}).get(TIME, []))


def is_remapped(clip) -> bool:
    return bool(keys(clip))


def material_at(clip, local: float) -> float:
    """Segundos de material desde el punto de entrada, en ese instante del clip."""
    puntos = keys(clip)
    if not puntos:
        return max(0.0, local) * max(0.0, getattr(clip, "speed", 1.0))
    return max(0.0, kf.evaluate(puntos, local, kf.LINEAR))


def speed_at(clip, local: float) -> float:
    """La velocidad en ese instante: la pendiente de la curva de tiempo."""
    if not is_remapped(clip):
        return getattr(clip, "speed", 1.0)
    paso = 1e-3
    a = max(0.0, min(clip.duration - 2 * paso, local - paso))
    return (material_at(clip, a + 2 * paso) - material_at(clip, a)) / (2 * paso)


def enable(clip) -> bool:
    """Prende el remapeo sin cambiar lo que se ve: una recta con la velocidad de ahora."""
    if is_remapped(clip) or not hasattr(clip, "anim"):
        return False
    material = clip.duration * max(0.0, clip.speed)
    clip.anim[TIME] = [[0.0, 0.0, kf.LINEAR],
                       [round(clip.duration, 4), material, kf.LINEAR]]
    return True


def disable(clip) -> bool:
    """Apaga el remapeo con la velocidad promedio, empezando en el mismo cuadro."""
    if not is_remapped(clip):
        return False
    inicio = material_at(clip, 0.0)
    fin = material_at(clip, clip.duration)
    clip.in_point = max(0.0, clip.in_point + inicio)
    pendiente = (fin - inicio) / clip.duration if clip.duration > 0 else 1.0
    clip.speed = 0.0 if pendiente < 1e-6 else max(0.25, min(MAX_SPEED, pendiente))
    clip.anim.pop(TIME, None)
    return True


def set_speed_from(clip, local: float, speed: float) -> None:
    """A partir de `local` y hasta el final, el clip va a `speed`.

    Lo de antes de `local` no cambia: se ve exactamente lo mismo. Velocidad
    0 congela desde ahí; negativa va en reversa, y se detiene en el primer
    cuadro del material si llega a él.
    """
    enable(clip)
    speed = max(-MAX_SPEED, min(MAX_SPEED, float(speed)))
    local = max(0.0, min(clip.duration, float(local)))
    valor = material_at(clip, local)
    puntos = [list(k) for k in keys(clip) if kf.time_of(k) < local - kf.TIME_TOLERANCE]
    puntos.append([round(local, 4), valor, kf.LINEAR])
    restante = clip.duration - local
    if restante > kf.TIME_TOLERANCE:
        final = valor + restante * speed
        if final < 0.0 and speed < 0.0:
            # La reversa llega al primer cuadro antes del final: ahí se pone un
            # keyframe y de ahí se sostiene. Recortar solo el último valor a
            # cero cambiaba la pendiente, y la reversa iba a otra velocidad.
            llega = local + valor / -speed
            if llega < clip.duration - kf.TIME_TOLERANCE:
                puntos.append([round(llega, 4), 0.0, kf.LINEAR])
            final = 0.0
        puntos.append([round(clip.duration, 4), final, kf.LINEAR])
    clip.anim[TIME] = kf.clean(puntos)


def rebase(points, left: float, offset: float) -> list:
    """Los keyframes de tiempo de la parte que empieza `left` segundos después.

    Al cortar, la segunda mitad empieza en otro punto del material: su punto
    de entrada avanza `offset`, así que a cada valor se le resta eso y a
    cada tiempo `left`. La curva sigue siendo la misma, vista desde el corte.
    """
    return [[round(kf.time_of(k) - left, 4), kf.value_of(k) - offset, *k[2:]]
            for k in points]
