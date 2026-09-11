"""Modelo del proyecto.

Python puro a propósito: aquí no se importa Qt ni PyAV, para poder probar
la lógica de edición sin abrir una ventana ni tocar un archivo de video.
Los tiempos van en segundos (float) salvo donde se diga lo contrario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vortex_studio.model.color import ColorAdjust
from vortex_studio.model.overlays import ImageOverlay, Title


@dataclass
class Clip:
    """Un pedazo de un archivo fuente colocado en una pista."""

    source: Path
    start: float  # dónde empieza dentro de la pista
    duration: float
    in_point: float = 0.0  # desde qué segundo del archivo fuente se toma
    name: str = ""
    color: ColorAdjust = field(default_factory=ColorAdjust)

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
        """Convierte un tiempo de la pista al tiempo del archivo fuente."""
        return self.in_point + (t - self.start)


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


@dataclass
class Project:
    name: str = "Sin título"
    sequences: list[Sequence] = field(default_factory=lambda: [Sequence.default()])

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
