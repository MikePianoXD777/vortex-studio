"""Ediciones con nombre, encima del historial de instantáneas.

Deshacer sigue funcionando con instantáneas completas (`model/history.py`):
nunca deja el proyecto en un estado que no existió. Lo que agrega esta capa
es que cada edición sea **un objeto con nombre** en vez de un bloque de
código suelto en la ventana:

    run(Split([clip], 3.0), secuencia, historial)

Eso importa por dos razones. La lógica de edición se prueba sin abrir una
ventana. Y quien no es la interfaz —la consola de scripts o el agente con IA
que viene después— puede editar el proyecto con las mismas piezas, y todo
lo que haga entra al historial y se deshace igual.

Python puro, como todo `model/`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from vortex_studio.model.project import Clip, Sequence


def track_of(sequence: Sequence, item):
    """La pista que tiene a ese elemento, comparando por identidad."""
    return next((t for t in sequence.tracks if any(c is item for c in t.clips)), None)


# --- dividir --------------------------------------------------------------

def _split_keys(transform, left: float):
    """Reparte los keyframes entre las dos mitades sin cambiar la animación.

    Los keyframes van en tiempo relativo al inicio del clip. La segunda
    mitad empieza `left` segundos después, así que **todos** sus keyframes
    se recorren esa cantidad, y la primera se queda con los suyos tal cual.

    Ninguna mitad pierde los keyframes que le caen fuera de su rango. Mi
    primera versión los recortaba y ponía uno nuevo justo en el corte, con
    el valor que llevaba la animación ahí. Con interpolación lineal eso da
    lo mismo; con la suave no: una curva suave de 0 a 4 no es igual a dos
    curvas suaves de 0 a 2 y de 2 a 4, porque cada mitad frena y arranca en
    el corte. La prueba lo agarró. Conservando los keyframes de afuera, cada
    mitad interpola exactamente entre los mismos puntos que antes.
    """
    primera = copy.deepcopy(transform)
    segunda = copy.deepcopy(transform)
    for prop, puntos in transform.keys.items():
        segunda.keys[prop] = [[round(t - left, 4), v] for t, v in puntos]
    return primera, segunda


def split_item(sequence: Sequence, item, t: float):
    """Parte un elemento en dos por el tiempo `t`. Devuelve la segunda mitad.

    Cada mitad se lleva lo que le toca, y no una copia de todo:

    - el material: la segunda mitad lee desde donde iba el archivo en el
      corte, **contando la velocidad** — en un clip a 2×, un segundo de
      pista son dos de archivo;
    - la animación, recortada y recorrida (ver `_split_keys`);
    - los fundidos: la entrada se queda en la primera mitad y la salida en
      la segunda — en medio del corte no hay fundido;
    - la transición cruzada se queda donde estaba: un corte nuevo no pide
      fundido cruzado;
    - en un texto, la animación de entrada va en la primera mitad y la de
      salida en la segunda.
    """
    track = track_of(sequence, item)
    if track is None or not (item.start + 1e-9 < t < item.end - 1e-9):
        return None

    left = t - item.start
    second = copy.deepcopy(item)
    second.start = t
    second.duration = item.duration - left

    if isinstance(item, Clip):
        second.in_point = item.source_time(t)
        second.dissolve = 0.0
        item.transform, second.transform = _split_keys(item.transform, left)

    if hasattr(item, "fade_in"):
        second.fade_in = 0.0
        item.fade_out = 0.0

    if hasattr(item, "anim_in"):
        second.anim_in = "Ninguna"
        item.anim_out = "Ninguna"

    item.duration = left
    track.add(second)
    return second


# --- slip -----------------------------------------------------------------

def slip(clip, delta: float, source_duration: float | None) -> float:
    """Cambia qué pedazo del archivo se ve, sin mover ni estirar el clip.

    Es la herramienta *slip* de Premiere: el clip se queda en su lugar y con
    su duración, y lo que cambia es el punto de entrada. `delta` va en
    segundos de archivo; positivo muestra material de más adelante.

    Se detiene en los dos extremos del archivo: antes del segundo 0 no hay
    nada, y después del final tampoco. Devuelve cuánto se movió de verdad.
    """
    if not isinstance(clip, Clip):
        return 0.0

    material = clip.duration * max(0.0, clip.speed)
    if source_duration is None:
        maximo = float("inf")
    else:
        maximo = max(0.0, source_duration - material)

    nuevo = min(max(0.0, clip.in_point + delta), maximo)
    aplicado = nuevo - clip.in_point
    clip.in_point = nuevo
    return aplicado


# --- los comandos ---------------------------------------------------------

@dataclass
class Command:
    """Una edición con nombre. `apply` dice si de verdad cambió algo."""

    name: str = ""

    def apply(self, sequence: Sequence) -> bool:  # pragma: no cover
        raise NotImplementedError


@dataclass
class Split(Command):
    """Divide en `time` todos los elementos que lo crucen."""

    items: list = field(default_factory=list)
    time: float = 0.0
    created: list = field(default_factory=list)
    name: str = "Dividir"

    def apply(self, sequence: Sequence) -> bool:
        self.created = [s for s in (split_item(sequence, i, self.time) for i in self.items) if s]
        return bool(self.created)


@dataclass
class RippleDelete(Command):
    """Borra y recorre lo que sigue en esa pista, sin dejar hueco."""

    item: object = None
    name: str = "Eliminar y cerrar hueco"

    def apply(self, sequence: Sequence) -> bool:
        track = track_of(sequence, self.item)
        if track is None:
            return False
        hueco, inicio = self.item.duration, self.item.start
        track.clips = [c for c in track.clips if c is not self.item]
        for otro in track.clips:
            if otro.start >= inicio:
                otro.start -= hueco
        return True


@dataclass
class Slip(Command):
    """Desliza el contenido del clip. Ver `slip`."""

    clip: object = None
    delta: float = 0.0
    source_duration: float | None = None
    applied: float = 0.0
    name: str = "Deslizar contenido"

    def apply(self, sequence: Sequence) -> bool:
        self.applied = slip(self.clip, self.delta, self.source_duration)
        return abs(self.applied) > 1e-9


def run(command: Command, sequence: Sequence, history) -> bool:
    """Aplica el comando y, si cambió algo, lo registra con su nombre.

    Un comando que no hizo nada no deja entrada en el historial: si no,
    deshacer tendría pasos que no deshacen nada.
    """
    if not command.apply(sequence):
        return False
    history.push(sequence, command.name)
    return True
