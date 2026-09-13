"""Multicámara: varias cámaras de la misma toma, y se corta entre ellas en vivo.

Es el Multicámara de Premiere y Resolve. Se arma en dos piezas que ya
existían:

- una **secuencia** con cada cámara en su propia pista de video, ya
  sincronizadas (por audio o por código de tiempo, ver `media/sync.py`), y
  el audio de la cámara de referencia sonando; los demás audios quedan en
  sus pistas, silenciados, por si hacen falta;
- un **clip multicámara** en la secuencia de edición: una secuencia anidada
  que en vez de mostrar todas sus pistas muestra **un solo ángulo** a la vez.

Qué ángulo se ve en cada momento son keyframes **sostenidos** de la ruta
`angle`: cortar a la cámara 2 en el segundo 14 es poner un keyframe de valor
1 en el 14. Así los cortes se ven y se mueven en el editor de keyframes, se
guardan y se deshacen, y la pista de audio sigue corrida sin un solo corte.

Python puro.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vortex_studio.model import keyframes as kf
from vortex_studio.model.project import Clip, NestedClip, Sequence, Track

ANGLE = "angle"


@dataclass(eq=False)
class MulticamClip(NestedClip):
    """Una secuencia multicámara usada como clip: muestra un ángulo a la vez."""

    angle: int = 0              # el ángulo antes del primer corte

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.name == "Secuencia anidada":
            self.name = "Multicámara"


@dataclass
class Angle:
    path: Path
    offset: float               # dónde empieza en la línea de tiempo de la multicámara
    duration: float
    has_audio: bool = True
    name: str = ""


def build(angles: list[Angle], width: int, height: int, fps: float,
          name: str = "Multicámara") -> Sequence:
    """La secuencia con una pista por cámara, ya sincronizadas.

    Los desfases pueden venir negativos (una cámara empezó antes que la de
    referencia): se recorren todos para que la primera en empezar quede en
    cero y nadie caiga antes del inicio.
    """
    secuencia = Sequence(name=name, fps=fps, width=width, height=height)
    if not angles:
        return secuencia
    base = min(a.offset for a in angles)
    video, audio = [], []
    for indice, angulo in enumerate(angles):
        nombre = angulo.name or f"Cámara {indice + 1}"
        inicio = round(angulo.offset - base, 6)
        video.append(Track(nombre, kind="video",
                           clips=[Clip(angulo.path, inicio, angulo.duration, name=nombre)]))
        if angulo.has_audio:
            audio.append(Track(f"Audio {indice + 1}", kind="audio", muted=indice != 0,
                               clips=[Clip(angulo.path, inicio, angulo.duration, name=nombre)]))
    secuencia.tracks = video + audio
    return secuencia


def angle_count(sequence: Sequence | None) -> int:
    return len(sequence.video_tracks()) if sequence is not None else 0


def angle_at(clip, local: float, count: int | None = None) -> int:
    """El ángulo que se ve en ese instante del clip."""
    puntos = (getattr(clip, "anim", None) or {}).get(ANGLE)
    valor = kf.evaluate(puntos, local, kf.HOLD) if puntos else getattr(clip, "angle", 0)
    indice = int(round(valor))
    if count:
        indice = max(0, min(count - 1, indice))
    return max(0, indice)


def cut_to(clip, local: float, index: int) -> None:
    """Desde `local`, se ve el ángulo `index`. Un corte en el mismo instante lo reemplaza."""
    puntos = list((clip.anim or {}).get(ANGLE, []))
    if not puntos and local > kf.TIME_TOLERANCE:
        # Lo de antes del primer corte sigue en el ángulo que tenía.
        puntos = [[0.0, float(clip.angle), kf.HOLD]]
    clip.anim[ANGLE] = kf.set_key(puntos, max(0.0, local), float(index), kf.HOLD)


def cuts(clip) -> list[tuple[float, int]]:
    """Los cortes del clip: `[(instante, ángulo)]`, sin repetidos seguidos."""
    salida: list[tuple[float, int]] = []
    for k in (clip.anim or {}).get(ANGLE, []):
        indice = int(round(kf.value_of(k)))
        if not salida or salida[-1][1] != indice:
            salida.append((kf.time_of(k), indice))
    return salida


def angle_view(sequence: Sequence, index: int) -> Sequence:
    """La secuencia con solo ese ángulo visible, sin tocar la original.

    Las pistas son objetos nuevos que comparten la lista de clips: cambiar
    `enabled` en la vista no apaga nada en la secuencia que se está editando.
    """
    vista = Sequence(name=sequence.name, fps=sequence.fps, width=sequence.width,
                     height=sequence.height, markers=sequence.markers,
                     duck_depth=sequence.duck_depth)
    vista.id = sequence.id
    videos = sequence.video_tracks()
    elegido = videos[max(0, min(len(videos) - 1, index))] if videos else None
    vista.tracks = [Track(t.name, kind=t.kind, clips=t.clips,
                          enabled=(t is elegido) if t.kind == "video" else t.enabled,
                          locked=t.locked, muted=t.muted, solo=t.solo, role=t.role)
                    for t in sequence.tracks]
    return vista
