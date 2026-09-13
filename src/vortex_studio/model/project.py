"""Modelo del proyecto.

Python puro a propósito: aquí no se importa Qt ni PyAV, para poder probar
la lógica de edición sin abrir una ventana ni tocar un archivo de video.
Los tiempos van en segundos (float) salvo donde se diga lo contrario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vortex_studio.model.blend import NORMAL, is_normal
from vortex_studio.model.audio_fx import DUCKED, NORMAL as ROLE_NORMAL, VOICE, AudioFx
from vortex_studio.model.chroma import ChromaKey
from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.mask import Mask
from vortex_studio.model.media import MediaInfo
from vortex_studio.model.overlays import AdjustmentLayer, ImageOverlay, Title
from vortex_studio.model.transform import FIT, Transform

SPEED_MIN = 0.25
SPEED_MAX = 4.0

# Transiciones. La cruzada mezcla los dos clips; las otras dos pasan por un
# color: el clip de salida se funde al color y de ahí sale el de entrada.
CROSS = "Cruzada"
DIP_BLACK = "A negro"
DIP_WHITE = "A blanco"
TRANSITIONS = (CROSS, DIP_BLACK, DIP_WHITE)
DIP_COLORS = {DIP_BLACK: "#000000", DIP_WHITE: "#ffffff"}

# Qué pasa con el sonido de un clip que no va a velocidad normal.
KEEP_PITCH = "Mantener tono"     # como Premiere: la voz se oye natural
SHIFT_PITCH = "Cambiar tono"     # como una cinta: más agudo si va rápido
MUTE_AUDIO = "Silenciar"
AUDIO_MODES = (KEEP_PITCH, SHIFT_PITCH, MUTE_AUDIO)

MARKER_COLORS = {
    "Amarillo": "#e8c15a",
    "Rojo": "#e0574a",
    "Naranja": "#e8904a",
    "Verde": "#5cb85c",
    "Azul": "#5f9bd8",
    "Morado": "#a07ad8",
    "Rosa": "#e07ab8",
    "Blanco": "#e8ebef",
}


@dataclass
class Marker:
    """Una nota clavada en un punto del tiempo.

    En la secuencia, `time` es el tiempo de la línea de tiempo. Dentro de un
    clip es relativo al inicio del clip, igual que los keyframes: así el
    marcador viaja con el clip cuando lo mueves.
    """

    time: float
    name: str = ""
    color: str = "#e8c15a"
    note: str = ""


@dataclass(frozen=True)
class Fill:
    """Una capa de color liso: el negro o el blanco de un fundido a color.

    Va en la pila de capas como si fuera un clip, para que quede exactamente
    en el lugar de la pista donde ocurre la transición.
    """

    color: str


@dataclass(eq=False)
class Clip:
    """Un pedazo de un archivo fuente colocado en una pista.

    `eq=False` a propósito: dos clips con los mismos datos siguen siendo
    cosas distintas en la línea de tiempo. Con la igualdad por valor que da
    un dataclass, el clip de video y el de audio que salen del mismo archivo
    resultaban iguales, y `lista.remove(x)`, `x in lista` y `lista.index(x)`
    —que usan `==`— agarraban el equivocado: borrabas el audio y se iba el
    video. Con `eq=False` la comparación es por identidad y cada uno es él.
    """

    source: Path
    start: float  # dónde empieza dentro de la pista
    duration: float
    in_point: float = 0.0  # desde qué segundo del archivo fuente se toma
    name: str = ""
    speed: float = 1.0       # 0.25 = cámara lenta, 4.0 = cámara rápida
    color: ColorAdjust = field(default_factory=ColorAdjust)
    fade_in: float = 0.0
    fade_out: float = 0.0
    gain: float = 1.0        # volumen del clip, solo aplica en pistas de audio
    dissolve: float = 0.0    # transición cruzada con el clip de la izquierda
    transform: Transform = field(default_factory=Transform)
    blend: str = NORMAL     # cómo se combina con la pista de abajo
    mask: Mask = field(default_factory=Mask)
    transition: str = CROSS  # de qué tipo es la transición de `dissolve`
    audio_mode: str = KEEP_PITCH
    # Clips con el mismo `link` se mueven, recortan, cortan y borran juntos:
    # el video y su audio. Vacío = suelto.
    link: str = ""
    markers: list = field(default_factory=list)
    # Keyframes de todo lo que no es transformación: ruta -> keyframes.
    # Ver `model/animate.py`.
    anim: dict = field(default_factory=dict)
    chroma: ChromaKey = field(default_factory=ChromaKey)
    audio_fx: AudioFx = field(default_factory=AudioFx)

    def __post_init__(self) -> None:
        self.source = Path(self.source)
        if not self.name:
            self.name = self.source.stem

    @property
    def end(self) -> float:
        return self.start + self.duration

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end

    def source_time(self, t: float) -> float:
        """Convierte un tiempo de la pista al tiempo del archivo fuente.

        Con velocidad distinta de 1, el archivo se recorre más rápido o más
        lento que la línea de tiempo: dos segundos de pista a 2× consumen
        cuatro segundos de material.
        """
        return self.in_point + (t - self.start) * self.speed

    def local(self, t: float) -> float:
        """Segundos transcurridos desde el inicio del clip."""
        return max(0.0, t - self.start)

    def fade_at(self, t: float) -> float:
        """La misma cuenta que en los demás elementos con tiempo."""
        entrada, salida = self.fade_in, self.fade_out
        if entrada <= 0 and salida <= 0:
            return 1.0

        total = entrada + salida
        if total > self.duration > 0:
            factor = self.duration / total
            entrada, salida = entrada * factor, salida * factor

        dentro = t - self.start
        alfa = 1.0
        if entrada > 0 and dentro < entrada:
            alfa = min(alfa, max(0.0, dentro / entrada))
        if salida > 0 and dentro > self.duration - salida:
            alfa = min(alfa, max(0.0, (self.duration - dentro) / salida))
        return alfa

    def retime(self, speed: float) -> None:
        """Cambia la velocidad ajustando la duración para no perder material.

        De 0.25× a 4×, el rango de CapCut y el que se oye bien: más allá, la
        voz con el tono corregido se vuelve un arrastre de sílabas. Para
        congelar se usa velocidad 0 directo, no esto.
        """
        speed = max(SPEED_MIN, min(SPEED_MAX, speed))
        material = self.duration * self.speed      # segundos de archivo que usa
        self.speed = speed
        self.duration = material / speed


def accepts(track, item) -> bool:
    """¿Cabe este elemento en esa pista? Video e imágenes en video, texto en
    texto, y clips de archivo en audio."""
    tipos = {"video": (Clip, ImageOverlay, AdjustmentLayer), "texto": (Title,), "audio": (Clip,)}
    return isinstance(item, tipos.get(track.kind, ()))


@dataclass
class Track:
    """Una pista de la secuencia.

    Guarda `Clip`, `ImageOverlay` o `Title` según su tipo. Los tres exponen
    `start`, `duration`, `end`, `name` y `contains()`, así que todo lo que
    ordena y dibuja pistas funciona igual para los tres.

    Los cuatro interruptores de la cabecera, como en Premiere:

    - `enabled`: la pista se ve (en video y texto). Apagada no se pinta ni
      se exporta, pero sus clips siguen ahí;
    - `locked`: nada de lo que tiene se puede mover, recortar ni borrar;
    - `muted` y `solo`: en audio. Si alguna pista está en solo, solo esas
      suenan; silenciar gana siempre.
    """

    name: str
    kind: str = "video"  # "video" | "audio" | "texto"
    clips: list = field(default_factory=list)
    enabled: bool = True
    locked: bool = False
    muted: bool = False
    solo: bool = False
    # En audio: "Voz", o "Música" que se agacha cuando suena la voz.
    role: str = ROLE_NORMAL

    @property
    def duration(self) -> float:
        return max((c.end for c in self.clips), default=0.0)

    def clip_at(self, t: float):
        for clip in self.clips:
            if clip.contains(t):
                return clip
        return None

    def items_at(self, t: float) -> list:
        """Todo lo que esté vivo en ese instante, en orden de la pista."""
        return [c for c in self.clips if c.contains(t)]

    def before(self, clip) -> "Clip | None":
        """El elemento inmediatamente anterior en la pista, si va pegado."""
        anterior = None
        for otro in self.clips:
            if otro is clip:
                return anterior if anterior and abs(anterior.end - clip.start) < 1e-6 else None
            anterior = otro
        return None

    def video_at(self, t: float) -> Clip | None:
        """Solo clips de archivo de video: ignora imágenes y textos."""
        for clip in self.clips:
            if isinstance(clip, Clip) and clip.contains(t):
                return clip
        return None

    def add(self, clip):
        self.clips.append(clip)
        self.clips.sort(key=lambda c: c.start)
        return clip

    def append(self, source: Path, duration: float, in_point: float = 0.0) -> Clip:
        """Pega un clip al final de la pista, sin hueco."""
        return self.add(Clip(source, self.duration, duration, in_point))


@dataclass
class Sequence:
    """Una secuencia (timeline) con sus pistas."""

    name: str = "Secuencia 1"
    fps: float = 30.0
    width: int = 1920
    height: int = 1080
    tracks: list[Track] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    duck_depth: float = 12.0      # cuántos dB baja la música cuando habla la voz

    @classmethod
    def default(cls) -> Sequence:
        """Distribución estándar: texto arriba, video en medio, audio abajo."""
        seq = cls()
        seq.tracks = [
            Track("T1", kind="texto"),
            Track("V2"),
            Track("V1"),
            Track("A1", kind="audio"),
            Track("A2", kind="audio"),
            Track("A3", kind="audio"),
        ]
        return seq

    @property
    def duration(self) -> float:
        return max((t.duration for t in self.tracks), default=0.0)

    @property
    def frame_duration(self) -> float:
        return 1.0 / self.fps

    def snap_to_frame(self, t: float) -> float:
        return round(t * self.fps) / self.fps

    def video_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "video"]

    def visible_video_tracks(self) -> list[Track]:
        return [t for t in self.video_tracks() if t.enabled]

    def audio_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "audio"]

    def audible_tracks(self) -> list[Track]:
        """Las pistas de audio que suenan: solo manda, y silencio gana."""
        pistas = [t for t in self.audio_tracks() if t.enabled]
        if any(t.solo for t in pistas):
            pistas = [t for t in pistas if t.solo]
        return [t for t in pistas if not t.muted]

    def audio_clips(self) -> list:
        """Lo que va a la mezcla: los clips de las pistas que suenan."""
        return [c for t in self.audible_tracks() for c in t.clips
                if getattr(c, "audio_mode", KEEP_PITCH) != MUTE_AUDIO]

    def audio_mix_options(self) -> dict:
        """Lo que el mezclador necesita para el ducking: quién es voz y quién se agacha."""
        pistas = self.audible_tracks()
        voces = {id(c) for t in pistas if t.role == VOICE for c in t.clips}
        agachados = {id(c) for t in pistas if t.role == DUCKED for c in t.clips}
        return {"voices": voces, "ducked": agachados, "depth": self.duck_depth}

    def track_of(self, item) -> Track | None:
        """La pista que tiene a ese elemento, comparando por identidad."""
        return next((t for t in self.tracks if any(c is item for c in t.clips)), None)

    def linked(self, item) -> list:
        """Los compañeros de enlace del elemento, sin incluirlo a él."""
        grupo = getattr(item, "link", "")
        if not grupo:
            return []
        return [c for t in self.tracks for c in t.clips
                if c is not item and getattr(c, "link", "") == grupo]

    def with_linked(self, items) -> list:
        """Los elementos más sus compañeros de enlace, sin repetir."""
        salida: list = []
        for item in items:
            for candidato in [item, *self.linked(item)]:
                if not any(candidato is x for x in salida):
                    salida.append(candidato)
        return salida

    def text_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "texto"]

    def top_clip_at(self, t: float) -> Clip | None:
        """El video de fondo: el de la pista de video más alta que tenga uno."""
        for track in self.visible_video_tracks():
            clip = track.video_at(t)
            if clip is not None:
                return clip
        return None

    def track_dissolve_at(self, track: Track, t: float):
        """La transición viva en esa pista, o None.

        La transición se reparte mitad antes y mitad después del corte, que
        es como la coloca Premiere: el corte queda al centro del cruce, no
        al principio.
        """
        for clip in track.clips:
            d = getattr(clip, "dissolve", 0.0)
            if d <= 0:
                continue

            saliente = track.before(clip)
            if saliente is None:
                continue

            desde, hasta = clip.start - d / 2, clip.start + d / 2
            if desde <= t < hasta:
                return saliente, clip, (t - desde) / d
        return None

    def dissolve_at(self, t: float):
        """La primera transición viva, mirando de la pista más alta abajo."""
        for track in self.visible_video_tracks():
            cruce = self.track_dissolve_at(track, t)
            if cruce is not None:
                return cruce
        return None

    def video_stack_at(self, t: float, aspect_of=None) -> list[tuple]:
        """Lo que hay que pintar en ese instante, de la pista más baja arriba.

        Cada entrada es `(clip, peso)`. Normalmente el peso es 1; durante
        una transición cruzada la pista aporta dos entradas cuyos pesos
        suman 1.

        Antes solo se pintaba la pista más alta con material, así que poner
        algo en V2 hacía desaparecer V1 por completo — no había manera de
        hacer un cuadro dentro del cuadro, y un modo de fusión no tenía con
        qué fusionarse.

        Las pistas de abajo se dejan de mirar en cuanto una de arriba las
        tapa del todo. Sin ese corte, tener dos pistas costaría el doble de
        decodificación aunque la de abajo quedara invisible.

        Un fundido a color aporta el clip que se ve más una capa `Fill`
        encima: en la primera mitad se cubre de color el que sale, y en la
        segunda se descubre el que entra. Un solo clip a la vez, a opacidad
        completa: si se mezclaran los dos, en medio se vería una cruzada
        oscura y no un paso por negro.

        `aspect_of(clip)` dice la proporción del material, si se sabe. Hace
        falta para saber si un clip en modo Ajustar tapa lo de abajo.
        """
        capas: list[tuple] = []
        for track in self.visible_video_tracks():  # de la más alta a la más baja
            cruce = self.track_dissolve_at(track, t)
            if cruce is not None:
                saliente, entrante, avance = cruce
                color = DIP_COLORS.get(getattr(entrante, "transition", CROSS))
                if color is None:
                    capas.append((entrante, avance))
                    capas.append((saliente, 1.0 - avance))
                    continue
                if avance < 0.5:
                    visible, cubierta = saliente, avance * 2.0
                else:
                    visible, cubierta = entrante, (1.0 - avance) * 2.0
                capas.append((Fill(color), cubierta))
                capas.append((visible, 1.0))
                if cubierta >= 0.999 or self.covers(visible, t, aspect_of):
                    break
                continue

            ajuste = next((c for c in track.items_at(t) if isinstance(c, AdjustmentLayer)), None)
            if ajuste is not None:
                capas.append((ajuste, 1.0))     # nunca tapa: corrige lo de abajo
                continue

            clip = track.video_at(t)
            if clip is None:
                continue
            capas.append((clip, 1.0))
            if self.covers(clip, t, aspect_of):
                break

        capas.reverse()
        return capas

    def covers(self, clip, t: float, aspect_of=None) -> bool:
        """¿Este clip tapa por completo lo que tenga debajo?

        Tapa si está entero: opaco, sin máscara, sin modo de fusión, sin
        fundido a medias, sin recorte, sin haberse encogido ni movido del
        cuadro, y —en modo Ajustar— con la misma proporción que la
        secuencia. Si no se sabe la proporción del material se supone que
        coincide, que es el caso común.
        """
        transform = clip.transform
        if transform.has_crop:
            return False
        if getattr(getattr(clip, "chroma", None), "is_on", False):
            return False
        if transform.fit == FIT and aspect_of is not None and self.height > 0:
            aspecto = aspect_of(clip)
            if aspecto and abs(aspecto - self.width / self.height) > 0.01:
                return False
        if not is_normal(getattr(clip, "blend", NORMAL)):
            return False
        mask = getattr(clip, "mask", None)
        if mask is not None and not mask.is_off:
            return False
        if clip.fade_at(t) < 0.999:
            return False

        v = clip.transform.values_at(clip.local(t))
        return (v["opacity"] >= 0.999 and v["scale"] >= 1.0
                and abs(v["x"]) < 1e-9 and abs(v["y"]) < 1e-9
                and abs(v["rotation"]) < 1e-9)

    def overlays_at(self, t: float) -> list[ImageOverlay]:
        """Imágenes activas, de la pista más baja a la más alta.

        Ese orden es el orden de pintado: lo de la pista de arriba queda
        encima, igual que en el timeline.
        """
        found: list[ImageOverlay] = []
        for track in reversed(self.visible_video_tracks()):
            found += [c for c in track.items_at(t) if isinstance(c, ImageOverlay)]
        return found

    def titles_at(self, t: float) -> list[Title]:
        """Textos activos. Siempre van hasta arriba de todo."""
        found: list[Title] = []
        for track in reversed([t for t in self.text_tracks() if t.enabled]):
            found += [c for c in track.items_at(t) if isinstance(c, Title)]
        return found

    def track_named(self, name: str) -> Track | None:
        return next((t for t in self.tracks if t.name == name), None)

    # --- marcadores -------------------------------------------------------

    def add_marker(self, t: float, name: str = "", color: str | None = None,
                   note: str = "") -> Marker:
        """Pone un marcador, o reemplaza el que ya hubiera en ese cuadro."""
        self.markers = [m for m in self.markers
                        if abs(m.time - t) > self.frame_duration / 2]
        marker = Marker(time=t, name=name, note=note)
        if color:
            marker.color = color
        self.markers.append(marker)
        self.markers.sort(key=lambda m: m.time)
        return marker

    def marker_near(self, t: float, tolerance: float = 0.0) -> Marker | None:
        margen = tolerance or self.frame_duration / 2
        return next((m for m in self.markers if abs(m.time - t) <= margen), None)

    def next_marker(self, t: float) -> Marker | None:
        return next((m for m in self.markers if m.time > t + 1e-6), None)

    def previous_marker(self, t: float) -> Marker | None:
        anteriores = [m for m in self.markers if m.time < t - 1e-6]
        return anteriores[-1] if anteriores else None


@dataclass
class Project:
    name: str = "Sin título"
    sequences: list[Sequence] = field(default_factory=lambda: [Sequence.default()])
    # Ruta absoluta -> lo que se sabe del archivo. Ver `model/media.py`.
    media: dict[str, MediaInfo] = field(default_factory=dict)

    @property
    def active(self) -> Sequence:
        return self.sequences[0]


def timecode(seconds: float, fps: float = 30.0) -> str:
    """Formatea segundos como HH:MM:SS:FF."""
    seconds = max(0.0, seconds)
    total_frames = round(seconds * fps)
    frames = int(total_frames % round(fps))
    total_seconds = int(total_frames // round(fps))
    return (
        f"{total_seconds // 3600:02d}:"
        f"{total_seconds // 60 % 60:02d}:"
        f"{total_seconds % 60:02d}:"
        f"{frames:02d}"
    )
