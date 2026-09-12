"""Modelo del proyecto.

Python puro a propósito: aquí no se importa Qt ni PyAV, para poder probar
la lógica de edición sin abrir una ventana ni tocar un archivo de video.
Los tiempos van en segundos (float) salvo donde se diga lo contrario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vortex_studio.model.blend import NORMAL, is_normal
from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.mask import Mask
from vortex_studio.model.media import MediaInfo
from vortex_studio.model.overlays import ImageOverlay, Title
from vortex_studio.model.transform import Transform


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
        """Cambia la velocidad ajustando la duración para no perder material."""
        speed = max(0.1, min(10.0, speed))
        material = self.duration * self.speed      # segundos de archivo que usa
        self.speed = speed
        self.duration = material / speed


@dataclass
class Track:
    """Una pista de la secuencia.

    Guarda `Clip`, `ImageOverlay` o `Title` según su tipo. Los tres exponen
    `start`, `duration`, `end`, `name` y `contains()`, así que todo lo que
    ordena y dibuja pistas funciona igual para los tres.
    """

    name: str
    kind: str = "video"  # "video" | "audio" | "texto"
    clips: list = field(default_factory=list)

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
class Marker:
    """Una nota clavada en un punto de la línea de tiempo."""

    time: float
    name: str = ""
    color: str = "#e8c15a"


@dataclass
class Sequence:
    """Una secuencia (timeline) con sus pistas."""

    name: str = "Secuencia 1"
    fps: float = 30.0
    width: int = 1920
    height: int = 1080
    tracks: list[Track] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

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

    def audio_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "audio"]

    def text_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "texto"]

    def top_clip_at(self, t: float) -> Clip | None:
        """El video de fondo: el de la pista de video más alta que tenga uno."""
        for track in self.video_tracks():
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
        for track in self.video_tracks():
            cruce = self.track_dissolve_at(track, t)
            if cruce is not None:
                return cruce
        return None

    def video_stack_at(self, t: float) -> list[tuple]:
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
        """
        capas: list[tuple] = []
        for track in self.video_tracks():        # de la más alta a la más baja
            cruce = self.track_dissolve_at(track, t)
            if cruce is not None:
                saliente, entrante, avance = cruce
                capas.append((entrante, avance))
                capas.append((saliente, 1.0 - avance))
                continue

            clip = track.video_at(t)
            if clip is None:
                continue
            capas.append((clip, 1.0))
            if self.covers(clip, t):
                break

        capas.reverse()
        return capas

    def covers(self, clip, t: float) -> bool:
        """¿Este clip tapa por completo lo que tenga debajo?

        Tapa si está entero: opaco, sin máscara, sin modo de fusión, sin
        fundido a medias, y sin haberse encogido ni movido del cuadro.
        """
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
        for track in reversed(self.video_tracks()):
            found += [c for c in track.items_at(t) if isinstance(c, ImageOverlay)]
        return found

    def titles_at(self, t: float) -> list[Title]:
        """Textos activos. Siempre van hasta arriba de todo."""
        found: list[Title] = []
        for track in reversed(self.text_tracks()):
            found += [c for c in track.items_at(t) if isinstance(c, Title)]
        return found

    def track_named(self, name: str) -> Track | None:
        return next((t for t in self.tracks if t.name == name), None)

    # --- marcadores -------------------------------------------------------

    def add_marker(self, t: float, name: str = "") -> Marker:
        """Pone un marcador, o reemplaza el que ya hubiera en ese cuadro."""
        self.markers = [m for m in self.markers
                        if abs(m.time - t) > self.frame_duration / 2]
        marker = Marker(time=t, name=name)
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
