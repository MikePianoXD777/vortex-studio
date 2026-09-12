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
import uuid
from dataclasses import dataclass, field

from vortex_studio.model.project import Clip, Sequence, accepts


def track_of(sequence: Sequence, item):
    """La pista que tiene a ese elemento, comparando por identidad."""
    return next((t for t in sequence.tracks if any(c is item for c in t.clips)), None)


def new_link() -> str:
    return uuid.uuid4().hex[:12]


def editable(sequence: Sequence, item) -> bool:
    """Un elemento se puede editar si existe y su pista no está bloqueada."""
    track = track_of(sequence, item)
    return track is not None and not track.locked


def editable_group(sequence: Sequence, items, with_links: bool = True) -> list:
    """Los elementos con sus enlazados, quitando los de pistas bloqueadas.

    Bloquear una pista protege lo que tiene aunque esté enlazado con algo
    de otra pista: si A1 está bloqueada, cortar el video no le corta el audio.
    """
    base = [x for x in items if x is not None]
    grupo = sequence.with_linked(base) if with_links else base
    return [i for i in grupo if editable(sequence, i)]


def overwrite(track, item) -> None:
    """Lo que se suelta encima tapa a lo que ya estaba.

    Es como funciona el arrastre por defecto en un editor: mandas algo
    sobre otra cosa y la pisa. Antes se permitía el traslape en silencio
    y lo que veías era el primero de la lista, que no siempre es el de
    arriba — parecía que el clip se había perdido.
    """
    for other in list(track.clips):
        if other is item or other.end <= item.start or other.start >= item.end:
            continue

        if other.start >= item.start and other.end <= item.end:
            track.clips.remove(other)          # queda tapado por completo
        elif other.start < item.start:
            if other.end > item.end:
                # El nuevo cae en medio: el de abajo queda partido en dos,
                # como al pegar en medio de un clip en Premiere.
                cola = copy.deepcopy(other)
                recorte = item.end - other.start
                cola.start = item.end
                cola.duration = other.end - item.end
                if hasattr(cola, "in_point"):
                    cola.in_point = other.in_point + recorte * max(other.speed, 0.0)
                    cola.dissolve = 0.0
                cola.fade_in = 0.0
                other.fade_out = 0.0
                if getattr(cola, "link", ""):
                    cola.link = ""
                track.clips.append(cola)
            other.duration = item.start - other.start   # se le corta la cola
        else:
            recorte = item.end - other.start             # se le corta la cabeza
            other.start = item.end
            other.duration -= recorte
            if hasattr(other, "in_point"):
                other.in_point += recorte * max(other.speed, 0.0)
    track.clips.sort(key=lambda c: c.start)


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

    # Cada marcador se queda en la mitad donde cae, con su tiempo relativo.
    if getattr(item, "markers", None):
        second.markers = [copy.copy(m) for m in item.markers if m.time >= left - 1e-9]
        for m in second.markers:
            m.time = round(m.time - left, 6)
        item.markers = [m for m in item.markers if m.time < left - 1e-9]

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
    """Divide en `time` todos los elementos que lo crucen, y sus enlazados.

    Las segundas mitades quedan enlazadas entre sí con un enlace nuevo: el
    video y el audio siguen yendo juntos, pero cada mitad con la suya.
    """

    items: list = field(default_factory=list)
    time: float = 0.0
    created: list = field(default_factory=list)
    name: str = "Dividir"
    with_links: bool = True

    def apply(self, sequence: Sequence) -> bool:
        nuevos: dict[str, str] = {}
        self.created = []
        for item in editable_group(sequence, self.items, self.with_links):
            segunda = split_item(sequence, item, self.time)
            if segunda is None:
                continue
            if getattr(segunda, "link", ""):
                segunda.link = nuevos.setdefault(segunda.link, new_link())
            self.created.append(segunda)
        return bool(self.created)


@dataclass
class Delete(Command):
    """Borra los elementos y sus enlazados, sin tocar pistas bloqueadas."""

    items: list = field(default_factory=list)
    name: str = "Eliminar"
    with_links: bool = True

    def apply(self, sequence: Sequence) -> bool:
        grupo = editable_group(sequence, self.items, self.with_links)
        for item in grupo:
            track = track_of(sequence, item)
            track.clips = [c for c in track.clips if c is not item]
        return bool(grupo)


@dataclass
class RippleDelete(Command):
    """Borra y recorre lo que sigue en cada pista, sin dejar hueco.

    Con enlace, el audio de un video borrado también se va y su pista
    también se recorre: si no, todo lo que sigue quedaría desfasado.
    """

    item: object = None
    name: str = "Eliminar y cerrar hueco"
    with_links: bool = True

    def apply(self, sequence: Sequence) -> bool:
        grupo = editable_group(sequence, [self.item], self.with_links)
        for item in grupo:
            track = track_of(sequence, item)
            hueco, inicio = item.duration, item.start
            track.clips = [c for c in track.clips if c is not item]
            for otro in track.clips:
                if otro.start >= inicio:
                    otro.start -= hueco
        return bool(grupo)


@dataclass
class Slip(Command):
    """Desliza el contenido del clip. Ver `slip`."""

    clip: object = None
    delta: float = 0.0
    source_duration: float | None = None
    applied: float = 0.0
    name: str = "Deslizar contenido"

    def apply(self, sequence: Sequence) -> bool:
        if not editable(sequence, self.clip):
            return False
        self.applied = slip(self.clip, self.delta, self.source_duration)
        # El audio enlazado se desliza lo mismo, o dejaría de coincidir con
        # la boca que se ve.
        if abs(self.applied) > 1e-9:
            for otro in editable_group(sequence, [self.clip]):
                if otro is not self.clip and isinstance(otro, Clip):
                    slip(otro, self.applied, self.source_duration)
        return abs(self.applied) > 1e-9


@dataclass
class SetSpeed(Command):
    """Cambia la velocidad del clip y de su audio enlazado a la vez."""

    clip: object = None
    speed: float = 1.0
    name: str = "Velocidad"

    def apply(self, sequence: Sequence) -> bool:
        cambio = False
        for otro in editable_group(sequence, [self.clip]):
            if isinstance(otro, Clip) and abs(otro.speed - self.speed) > 1e-9:
                otro.retime(self.speed)
                cambio = True
        return cambio


# --- enlazar --------------------------------------------------------------

@dataclass
class Link(Command):
    """Enlaza los clips: a partir de aquí se editan como uno solo."""

    items: list = field(default_factory=list)
    name: str = "Enlazar"

    def apply(self, sequence: Sequence) -> bool:
        clips = [i for i in sequence.with_linked(self.items) if isinstance(i, Clip)]
        if len(clips) < 2:
            return False
        grupo = new_link()
        for clip in clips:
            clip.link = grupo
        return True


@dataclass
class Unlink(Command):
    """Suelta el enlace: el audio y el video se pueden mover por separado."""

    items: list = field(default_factory=list)
    name: str = "Desenlazar"

    def apply(self, sequence: Sequence) -> bool:
        grupo = [i for i in sequence.with_linked(self.items) if getattr(i, "link", "")]
        for item in grupo:
            item.link = ""
        return bool(grupo)


def link_offset(sequence: Sequence, clip) -> float:
    """Cuántos segundos de archivo está desfasado un clip de su enlazado.

    Cero si van sincronizados. Es el número rojo que Premiere pone en el
    clip cuando el audio y el video del mismo archivo se deslizaron por
    separado: dice cuánto hay que mover para volver a juntarlos.
    """
    if not isinstance(clip, Clip):
        return 0.0
    for otro in sequence.linked(clip):
        if isinstance(otro, Clip) and otro.source == clip.source:
            return round((clip.in_point - clip.start * clip.speed)
                         - (otro.in_point - otro.start * otro.speed), 6)
    return 0.0


# --- portapapeles ---------------------------------------------------------

def copy_items(sequence: Sequence, items, with_links: bool = True) -> list[dict]:
    """Copia los elementos —con sus enlazados— a datos planos.

    Planos y no objetos: lo copiado no puede cambiar si después se edita el
    original, y así mismo se podría llevar al portapapeles del sistema.
    """
    from vortex_studio.model.serialize import item_to_dict

    base = [i for i in items if i is not None]
    grupo = sequence.with_linked(base) if with_links else base
    if not grupo:
        return []
    origen = min(i.start for i in grupo)
    salida = []
    for item in grupo:
        track = track_of(sequence, item)
        if track is None:
            continue
        salida.append({
            "track": sequence.tracks.index(track),
            "kind": track.kind,
            "offset": item.start - origen,
            "data": item_to_dict(item),
        })
    return salida


@dataclass
class Paste(Command):
    """Pega lo copiado en `time`, cada cosa en su pista y a su distancia.

    Si la pista original ya no acepta el elemento o está bloqueada, va a la
    primera pista libre de su clase. Lo pegado pisa lo que haya abajo, igual
    que al soltarlo con el mouse. Los enlaces se renuevan: el par pegado va
    enlazado entre sí, no con el original.
    """

    entries: list = field(default_factory=list)
    time: float = 0.0
    created: list = field(default_factory=list)
    name: str = "Pegar"

    def apply(self, sequence: Sequence) -> bool:
        from vortex_studio.model.serialize import item_from_dict

        nuevos: dict[str, str] = {}
        self.created = []
        for entrada in self.entries:
            item = item_from_dict(entrada["data"])
            item.start = max(0.0, self.time + entrada["offset"])
            if getattr(item, "link", ""):
                item.link = nuevos.setdefault(item.link, new_link())

            track = self._target(sequence, entrada, item)
            if track is None:
                continue
            overwrite(track, item)
            track.add(item)
            self.created.append(item)
        return bool(self.created)

    @staticmethod
    def _target(sequence: Sequence, entrada: dict, item):
        indice = entrada.get("track", -1)
        if 0 <= indice < len(sequence.tracks):
            pista = sequence.tracks[indice]
            if pista.kind == entrada.get("kind") and accepts(pista, item) and not pista.locked:
                return pista
        return next((p for p in sequence.tracks
                     if p.kind == entrada.get("kind") and accepts(p, item) and not p.locked),
                    None)


ATTRIBUTES = ("Transformación", "Color", "Máscara y fusión", "Velocidad",
              "Volumen", "Fundidos")


def paste_attributes(source, target, groups) -> bool:
    """Copia a `target` los grupos de ajustes de `source`.

    Es el Pegar atributos de Premiere: se elige qué se lleva y el resto del
    clip destino queda intacto. Un grupo que el destino no tiene —color en
    un texto, volumen en una imagen— simplemente se salta.
    """
    if source is target:
        return False
    cambio = False

    def puede(nombre):
        return hasattr(source, nombre) and hasattr(target, nombre)

    if "Transformación" in groups and puede("transform"):
        target.transform = copy.deepcopy(source.transform)
        cambio = True
    if "Color" in groups and puede("color") and isinstance(target, Clip):
        target.color = source.color.copy()
        cambio = True
    if "Máscara y fusión" in groups and puede("mask"):
        target.mask = copy.deepcopy(source.mask)
        target.blend = source.blend
        cambio = True
    if "Velocidad" in groups and isinstance(source, Clip) and isinstance(target, Clip):
        if source.speed == 0:
            target.speed = 0.0
        else:
            if target.speed == 0:
                target.speed = 1.0
            target.retime(source.speed)
        target.audio_mode = source.audio_mode
        cambio = True
    if "Volumen" in groups and isinstance(source, Clip) and isinstance(target, Clip):
        target.gain = source.gain
        cambio = True
    if "Fundidos" in groups and puede("fade_in"):
        target.fade_in = min(source.fade_in, target.duration)
        target.fade_out = min(source.fade_out, target.duration)
        cambio = True
    return cambio


@dataclass
class PasteAttributes(Command):
    source: object = None
    targets: list = field(default_factory=list)
    groups: tuple = ATTRIBUTES
    name: str = "Pegar atributos"

    def apply(self, sequence: Sequence) -> bool:
        resultados = [paste_attributes(self.source, t, self.groups)
                      for t in self.targets if editable(sequence, t)]
        return any(resultados)


def run(command: Command, sequence: Sequence, history) -> bool:
    """Aplica el comando y, si cambió algo, lo registra con su nombre.

    Un comando que no hizo nada no deja entrada en el historial: si no,
    deshacer tendría pasos que no deshacen nada.
    """
    if not command.apply(sequence):
        return False
    history.push(sequence, command.name)
    return True
