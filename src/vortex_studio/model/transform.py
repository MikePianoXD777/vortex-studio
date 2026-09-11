"""Posición, tamaño, giro y opacidad de un clip, con animación por keyframes.

Es lo que en After Effects son las propiedades de transformación y en
Premiere el efecto Movimiento. La idea aquí es tener la misma capacidad sin
el editor de gráficas: si una propiedad no tiene keyframes vale un número
fijo, y en cuanto tiene dos o más se anima sola entre ellos.

Los keyframes se guardan en tiempo relativo al inicio del clip, no absoluto.
Así, mover el clip en la línea de tiempo se lleva su animación pegada en vez
de dejarla atrás.

Todo va en unidades relativas al cuadro: `x = 0.5` es medio cuadro a la
derecha, sin importar si la secuencia es de 720p o de 4K.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROPS = ("x", "y", "scale", "rotation", "opacity")

NEUTRAL = {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "opacity": 1.0}

# Rangos para la interfaz: (mínimo, máximo, neutro), en centésimas o grados.
RANGES = {
    "x": (-200, 200, 0),
    "y": (-200, 200, 0),
    "scale": (1, 500, 100),
    "rotation": (-180, 180, 0),
    "opacity": (0, 100, 100),
}


def _smooth(p: float) -> float:
    """Suaviza la entrada y la salida del tramo entre dos keyframes.

    Un movimiento lineal delata que lo hizo una máquina: arranca y frena de
    golpe. Esta curva es la que hace que se vea intencional sin pedirle al
    usuario que toque una gráfica de bezier.
    """
    return p * p * (3.0 - 2.0 * p)


@dataclass
class Transform:
    x: float = 0.0           # desplazamiento, en fracciones de cuadro
    y: float = 0.0
    scale: float = 1.0       # 1.0 llena el cuadro
    rotation: float = 0.0    # grados
    opacity: float = 1.0

    # propiedad -> [[tiempo relativo, valor], …], siempre ordenada
    keys: dict[str, list[list[float]]] = field(default_factory=dict)
    ease: bool = True

    # --- lectura ----------------------------------------------------------

    def at(self, prop: str, local: float) -> float:
        """El valor de esa propiedad a `local` segundos del inicio del clip."""
        puntos = self.keys.get(prop)
        if not puntos:
            return getattr(self, prop)

        if local <= puntos[0][0]:
            return puntos[0][1]
        if local >= puntos[-1][0]:
            return puntos[-1][1]

        for (t0, v0), (t1, v1) in zip(puntos, puntos[1:]):
            if t0 <= local <= t1:
                if t1 - t0 < 1e-9:
                    return v1
                p = (local - t0) / (t1 - t0)
                return v0 + (v1 - v0) * (_smooth(p) if self.ease else p)
        return puntos[-1][1]

    def values_at(self, local: float) -> dict[str, float]:
        return {p: self.at(p, local) for p in PROPS}

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, el compositor puede saltarse el trabajo."""
        if any(self.keys.get(p) for p in PROPS):
            return False
        return all(abs(getattr(self, p) - NEUTRAL[p]) < 1e-9 for p in PROPS)

    def animated(self, prop: str) -> bool:
        return len(self.keys.get(prop, ())) > 0

    # --- edición ----------------------------------------------------------

    def set_key(self, prop: str, local: float, value: float) -> None:
        """Pone o reemplaza un keyframe. Dos en el mismo instante no tiene sentido."""
        puntos = [k for k in self.keys.get(prop, []) if abs(k[0] - local) > 1e-4]
        puntos.append([round(local, 4), value])
        puntos.sort(key=lambda k: k[0])
        self.keys[prop] = puntos

    def remove_key(self, prop: str, local: float, tolerance: float = 0.05) -> bool:
        puntos = self.keys.get(prop, [])
        quedan = [k for k in puntos if abs(k[0] - local) > tolerance]
        if len(quedan) == len(puntos):
            return False

        if quedan:
            self.keys[prop] = quedan
        else:
            # Sin keyframes, la propiedad vuelve a ser un número fijo: se
            # congela en el último valor que tenía para que no pegue un salto.
            self.keys.pop(prop, None)
            setattr(self, prop, puntos[0][1])
        return True

    def key_near(self, prop: str, local: float, tolerance: float = 0.05):
        return next((k for k in self.keys.get(prop, []) if abs(k[0] - local) <= tolerance),
                    None)

    def clear_keys(self, prop: str | None = None) -> None:
        objetivos = [prop] if prop else list(self.keys)
        for p in objetivos:
            puntos = self.keys.pop(p, None)
            if puntos:
                setattr(self, p, puntos[0][1])

    def reset(self) -> None:
        self.keys.clear()
        for p, v in NEUTRAL.items():
            setattr(self, p, v)

    def all_keys(self) -> list[float]:
        """Todos los instantes con keyframe, para dibujarlos en el timeline."""
        return sorted({k[0] for puntos in self.keys.values() for k in puntos})
