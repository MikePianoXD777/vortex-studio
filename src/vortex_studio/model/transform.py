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

Aquí también vive el **encuadre**: cómo se acomoda el material dentro del
cuadro de la secuencia (ajustar, rellenar o estirar), cuánto se le recorta
por cada orilla, y el punto de anclaje alrededor del cual se escala y se
gira. Van juntos porque son la misma pregunta —dónde y cómo cae la imagen—
y porque "pegar atributos de transformación" tiene que llevárselos todos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vortex_studio.model import keyframes as kf

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

# Cómo cae el material en el cuadro cuando no tiene su misma proporción.
FIT = "Ajustar"        # cabe entero; lo que sobra del cuadro queda negro
FILL = "Rellenar"      # llena el cuadro; lo que sobra del material se sale
STRETCH = "Estirar"    # llena deformando, como se veía antes de la 0.4
FIT_MODES = (FIT, FILL, STRETCH)

CROP_SIDES = ("crop_left", "crop_top", "crop_right", "crop_bottom")
CROP_MAX = 0.49        # por orilla: con dos orillas al 50 % no queda nada


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

    # Punto de anclaje: alrededor de dónde se escala y se gira, en fracciones
    # del cuadro medidas desde el centro (-0.5 es la orilla izquierda). No
    # mueve la imagen por sí solo, como en CapCut: en After Effects mover el
    # ancla desplaza la capa, y eso sorprende a quien solo quería girar un
    # logo desde su esquina.
    anchor_x: float = 0.0
    anchor_y: float = 0.0

    # Recorte por orilla, en fracciones del material. Lo recortado queda
    # transparente y la imagen no se mueve de lugar, igual que el efecto
    # Recortar de Premiere: así recortar un cuadro dentro de cuadro no lo
    # hace brincar.
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 0.0
    crop_bottom: float = 0.0

    fit: str = FIT

    # --- lectura ----------------------------------------------------------

    def at(self, prop: str, local: float) -> float:
        """El valor de esa propiedad a `local` segundos del inicio del clip.

        Cada keyframe puede traer su interpolación (ver `model/keyframes.py`);
        el que no trae usa la de `ease`: suave o lineal.
        """
        puntos = self.keys.get(prop)
        if not puntos:
            return getattr(self, prop)
        return kf.evaluate(puntos, local, kf.EASE if self.ease else kf.LINEAR)

    def values_at(self, local: float) -> dict[str, float]:
        return {p: self.at(p, local) for p in PROPS}

    @property
    def is_neutral(self) -> bool:
        """Si nada está tocado, el compositor puede saltarse el trabajo."""
        if any(self.keys.get(p) for p in PROPS):
            return False
        if self.has_crop:
            return False
        return all(abs(getattr(self, p) - NEUTRAL[p]) < 1e-9 for p in PROPS)

    @property
    def has_crop(self) -> bool:
        return any(getattr(self, lado) > 1e-9 for lado in CROP_SIDES)

    @property
    def crop(self) -> tuple[float, float, float, float]:
        """(izquierda, arriba, derecha, abajo), ya dentro de sus topes."""
        return tuple(max(0.0, min(CROP_MAX, getattr(self, lado))) for lado in CROP_SIDES)

    def animated(self, prop: str) -> bool:
        return len(self.keys.get(prop, ())) > 0

    # --- edición ----------------------------------------------------------

    def set_key(self, prop: str, local: float, value: float,
                interp: str | None = None) -> None:
        """Pone o reemplaza un keyframe. Dos en el mismo instante no tiene sentido."""
        self.keys[prop] = kf.set_key(self.keys.get(prop, []), local, value, interp)

    def remove_key(self, prop: str, local: float, tolerance: float = 0.05) -> bool:
        puntos = self.keys.get(prop, [])
        quedan = kf.remove_key(puntos, local, tolerance)
        if len(quedan) == len(puntos):
            return False

        if quedan:
            self.keys[prop] = quedan
        else:
            # Sin keyframes, la propiedad vuelve a ser un número fijo: se
            # congela en el último valor que tenía para que no pegue un salto.
            self.keys.pop(prop, None)
            setattr(self, prop, kf.value_of(puntos[0]))
        return True

    def key_near(self, prop: str, local: float, tolerance: float = 0.05):
        return kf.key_near(self.keys.get(prop, []), local, tolerance)

    def clear_keys(self, prop: str | None = None) -> None:
        objetivos = [prop] if prop else list(self.keys)
        for p in objetivos:
            puntos = self.keys.pop(p, None)
            if puntos:
                setattr(self, p, kf.value_of(puntos[0]))

    def reset(self) -> None:
        """Vuelve a llenar el cuadro: sin animación, sin recorte, ancla al centro.

        El modo de encuadre no se toca: es una decisión sobre el material, no
        un ajuste que uno quiera perder al restablecer la posición.
        """
        self.keys.clear()
        for p, v in NEUTRAL.items():
            setattr(self, p, v)
        self.anchor_x = self.anchor_y = 0.0
        for lado in CROP_SIDES:
            setattr(self, lado, 0.0)

    def all_keys(self) -> list[float]:
        """Todos los instantes con keyframe, para dibujarlos en el timeline."""
        return sorted({kf.time_of(k) for puntos in self.keys.values() for k in puntos})
