"""Guardar y abrir proyectos, y sacar copias del estado.

El mismo código sirve para dos cosas: escribir el archivo .vortex y tomar
las instantáneas del historial de deshacer. Son el mismo problema —
convertir la secuencia a datos planos y de regreso— y tener una sola
implementación evita que el archivo guarde algo que deshacer no restaura.

Al abrir, el archivo se trata como algo que pudo editarse a mano o dañarse:
lo que no se entiende se ignora o se corrige a un valor que sirve, y lo que
de plano no es un proyecto se rechaza con un `ProjectError` que se le puede
mostrar al usuario tal cual. Antes un campo de más o un fps en cero tumbaba
la carga —o peor, la dejaba pasar y tronaba después, al pintar— con un
`TypeError` o un `ZeroDivisionError` que no decían nada.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vortex_studio.model import keyframes as kf
from vortex_studio.model.audio_fx import AudioFx
from vortex_studio.model.chroma import ChromaKey
from vortex_studio.model.color import INPUT_SPACES, ColorAdjust
from vortex_studio.model.plugins import clean_effects
from vortex_studio.model.curves import Curves
from vortex_studio.model.mask import Mask
from vortex_studio.model.multicam import MulticamClip
from vortex_studio.model.media import MediaInfo, library_key
from vortex_studio.model.overlays import AdjustmentLayer, ImageOverlay, Title
from vortex_studio.model.project import (
    SAMPLE_NEAREST,
    SAMPLINGS,
    SPEED_MAX,
    Clip,
    Marker,
    NestedClip,
    Project,
    Sequence,
    Track,
)
from vortex_studio.model.transform import Transform

# 2: máscaras, modos de fusión, curva de color, viñeta y animación de texto.
# 3: el sondeo de los medios guardado en el proyecto.
# 4: encuadre y anclaje, transiciones a color, modo de audio por velocidad,
#    enlaces, marcadores con nota en clips, tipografía de títulos y los
#    interruptores de pista.
# 5: keyframes con interpolación y de cualquier parámetro, y lo del nivel 3.
# 6: lo del nivel 4 —remapeo de tiempo, cuadros intermedios, perspectiva y
#    corner pin, y lo que sigue—.
# Se sube el número para que una versión vieja diga "esto es más nuevo que
# yo" en vez de abrir el proyecto a medias y perder esos ajustes al guardar.
FORMAT_VERSION = 6
EXTENSION = ".vortex"

KINDS = ("clip", "anidada", "multicam", "imagen", "texto", "ajuste")
TRACK_KINDS = ("video", "audio", "texto")
MIN_DURATION = 1.0 / 30.0       # lo mínimo que se le deja a un elemento dañado


class ProjectError(ValueError):
    """El archivo no se puede abrir como proyecto. El mensaje es para el usuario."""


# --- limpieza de lo que viene del archivo -------------------------------------

def _fields(cls, data) -> dict:
    """Solo los campos que la clase conoce.

    Un campo de más —de un proyecto editado a mano, o de una versión de
    desarrollo— tumbaba la carga entera con un `TypeError`. Se ignora: lo
    que sí se entiende se abre.
    """
    if not isinstance(data, dict):
        return {}
    nombres = {f.name for f in dataclasses.fields(cls) if f.init}
    return {k: v for k, v in data.items() if k in nombres}


def _number(valor, omision: float, minimo: float | None = None,
            maximo: float | None = None) -> float:
    """Un número finito dentro de sus topes, o el de omisión si no lo es."""
    if isinstance(valor, bool):
        return omision
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return omision
    if not math.isfinite(numero):
        return omision
    if minimo is not None:
        numero = max(minimo, numero)
    if maximo is not None:
        numero = min(maximo, numero)
    return numero


def _keys(raw) -> dict:
    """Keyframes por propiedad, sin los que no se pueden evaluar."""
    if not isinstance(raw, dict):
        return {}
    salida = {}
    for prop, puntos in raw.items():
        limpios = kf.clean(puntos)
        if limpios:
            salida[str(prop)] = limpios
    return salida


def _markers(raw) -> list[Marker]:
    salida = []
    for m in raw if isinstance(raw, list) else []:
        datos = _fields(Marker, m)
        tiempo = _number(datos.get("time"), float("nan"))
        if math.isnan(tiempo):
            continue
        datos["time"] = max(0.0, tiempo)
        salida.append(Marker(**datos))
    salida.sort(key=lambda m: m.time)
    return salida


def _sane(item) -> None:
    """Deja los números de un elemento en valores con los que se puede pintar.

    Una duración negativa hacía que el timeline dibujara hacia atrás; una
    velocidad negativa pedía cuadros de antes del segundo cero. No se tira
    el elemento: se le deja lo mínimo para que se vea y el usuario lo corrija.
    """
    item.start = _number(item.start, 0.0, 0.0)
    duracion = _number(item.duration, 0.0)
    item.duration = duracion if duracion > 0 else MIN_DURATION
    for campo in ("fade_in", "fade_out"):
        if hasattr(item, campo):
            setattr(item, campo, _number(getattr(item, campo), 0.0, 0.0))
    if isinstance(item, Clip):
        item.in_point = _number(item.in_point, 0.0, 0.0)
        item.speed = min(SPEED_MAX, abs(_number(item.speed, 1.0)))
        item.gain = _number(item.gain, 1.0, 0.0)
        item.dissolve = _number(item.dissolve, 0.0, 0.0)
        item.markers = list(item.markers) if isinstance(item.markers, list) else []
        if item.interpolation not in SAMPLINGS:
            item.interpolation = SAMPLE_NEAREST
    if hasattr(item, "transform"):
        item.transform.keys = _keys(item.transform.keys)
    if hasattr(item, "anim"):
        item.anim = _keys(item.anim)


# --- rutas ---------------------------------------------------------------------

def _write_path(path: Path, base: Path | None) -> str:
    """Cómo se guarda la ruta de un archivo dentro del proyecto.

    Si el material está junto al proyecto o debajo de él, se guarda relativo
    y con barras normales. Así el proyecto se puede mover de carpeta, pasar
    de Linux a Windows o mandarse junto con sus videos y sigue abriendo.
    Solo se guarda absoluta cuando el archivo vive en otro lado.
    """
    path = Path(path)
    if base is not None:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return path.as_posix()


def _read_path(texto: str, base: Path | None) -> Path:
    path = Path(texto)
    if not path.is_absolute() and base is not None:
        return (base / path).resolve()
    return path


# --- elementos -----------------------------------------------------------------

def item_to_dict(item: Any, base: Path | None = None) -> dict:
    data = asdict(item)
    if isinstance(item, MulticamClip):
        data["tipo"] = "multicam"
        data["source"] = ""
    elif isinstance(item, NestedClip):
        data["tipo"] = "anidada"
        data["source"] = ""
    elif isinstance(item, Clip):
        data["tipo"] = "clip"
        data["source"] = _write_path(item.source, base)
        if item.color.lut:
            # El LUT viaja con el proyecto igual que el material: relativo si
            # está junto al proyecto.
            data["color"]["lut"] = _write_path(Path(item.color.lut), base)
    elif isinstance(item, ImageOverlay):
        data["tipo"] = "imagen"
        data["source"] = _write_path(item.source, base)
    elif isinstance(item, Title):
        data["tipo"] = "texto"
    elif isinstance(item, AdjustmentLayer):
        data["tipo"] = "ajuste"
        if item.color.lut:
            data["color"]["lut"] = _write_path(Path(item.color.lut), base)
    else:  # pragma: no cover - no debería pasar
        raise TypeError(f"No sé guardar {type(item).__name__}")
    return data


def _color(raw: dict | None, base: Path | None = None) -> ColorAdjust | None:
    """Reconstruye el color, con su curva adentro.

    `asdict` aplana los dataclasses anidados a diccionarios, así que al
    volver hay que armarlos de nuevo uno por uno. Sin esto, `clip.color`
    quedaba siendo un `dict` y todo lo que le pedía un atributo tronaba —
    pero hasta varios pasos después, que es lo que lo vuelve difícil de
    encontrar.
    """
    if not raw or not isinstance(raw, dict):
        return None
    raw = dict(raw)
    curva = raw.pop("curves", None)
    if raw.get("lut"):
        raw["lut"] = str(_read_path(str(raw["lut"]), base))
    adjust = ColorAdjust(**_fields(ColorAdjust, raw))
    if curva:
        adjust.curves = Curves(**_fields(Curves, curva))
    adjust.effects = clean_effects(adjust.effects)
    if adjust.input_space not in INPUT_SPACES:
        adjust.input_space = ""
    return adjust


def item_from_dict(data: dict, base: Path | None = None) -> Any:
    if not isinstance(data, dict):
        raise ProjectError("Un elemento de una pista está dañado: no trae datos.")
    data = dict(data)
    kind = data.pop("tipo", None)
    if kind not in KINDS:
        raise ProjectError(f"Tipo desconocido en el proyecto: {kind}")
    data.setdefault("start", 0.0)
    data.setdefault("duration", MIN_DURATION)

    # `transform` y `mask` se sacan para todos porque solo los tienen los
    # que los tienen. `color` NO: en un `Title` ese campo es el color de la
    # letra, una cadena como "#ffcc00", y sacarlo de ahí borraba el color
    # del texto al abrir el proyecto.
    transform = data.pop("transform", None)
    mask = data.pop("mask", None)
    markers = data.pop("markers", None)

    if kind in ("clip", "anidada", "multicam"):
        color = _color(data.pop("color", None), base)
        chroma = data.pop("chroma", None)
        audio_fx = data.pop("audio_fx", None)
        if kind == "multicam":
            data["source"] = Path("")
            item = MulticamClip(**_fields(MulticamClip, data))
            item.angle = int(_number(item.angle, 0.0, 0.0, 64.0))
        elif kind == "anidada":
            data["source"] = Path("")
            item = NestedClip(**_fields(NestedClip, data))
        else:
            data["source"] = _read_path(str(data.get("source") or ""), base)
            item = Clip(**_fields(Clip, data))
        if color:
            item.color = color
        if isinstance(chroma, dict):
            item.chroma = ChromaKey(**_fields(ChromaKey, chroma))
        if isinstance(audio_fx, dict):
            item.audio_fx = AudioFx(**_fields(AudioFx, audio_fx))
    elif kind == "imagen":
        data["source"] = _read_path(str(data.get("source") or ""), base)
        item = ImageOverlay(**_fields(ImageOverlay, data))
    elif kind == "texto":
        item = Title(**_fields(Title, data))
    else:
        color = _color(data.pop("color", None), base)
        item = AdjustmentLayer(**_fields(AdjustmentLayer, data))
        if color:
            item.color = color

    if isinstance(transform, dict) and hasattr(item, "transform"):
        item.transform = Transform(**_fields(Transform, transform))
    if isinstance(mask, dict) and hasattr(item, "mask"):
        item.mask = Mask(**_fields(Mask, mask))
    if markers and hasattr(item, "markers"):
        item.markers = _markers(markers)
    _sane(item)
    return item


# --- secuencias ------------------------------------------------------------------

def _unique_uids(sequence: Sequence) -> None:
    """Que no haya dos elementos con el mismo `uid`.

    Dividir, pisar a la mitad o duplicar copian el elemento entero, `uid`
    incluido. En vez de acordarse de renovarlo en cada lugar que copia, se
    revisa aquí, que es por donde pasa todo lo que se guarda o se deshace: el
    primero en la pista —la mitad izquierda— se queda con el suyo.
    """
    vistos: set[str] = set()
    for track in sequence.tracks:
        for item in track.clips:
            if not hasattr(item, "uid"):
                continue
            if not item.uid or item.uid in vistos:
                item.uid = uuid.uuid4().hex[:12]
            vistos.add(item.uid)


def sequence_to_dict(sequence: Sequence, base: Path | None = None) -> dict:
    _unique_uids(sequence)
    return {
        "id": sequence.id,
        "name": sequence.name,
        "fps": sequence.fps,
        "width": sequence.width,
        "height": sequence.height,
        "tracks": [
            {
                "name": track.name,
                "kind": track.kind,
                "enabled": track.enabled,
                "locked": track.locked,
                "muted": track.muted,
                "solo": track.solo,
                "role": track.role,
                "clips": [item_to_dict(c, base) for c in track.clips],
            }
            for track in sequence.tracks
        ],
        "markers": [asdict(m) for m in sequence.markers],
        "duck_depth": sequence.duck_depth,
    }


def sequence_from_dict(data: dict, base: Path | None = None) -> Sequence:
    if not isinstance(data, dict):
        raise ProjectError("Una secuencia del proyecto está dañada.")

    # Un fps en cero, nulo o absurdo dividía entre cero en cuanto se pedía
    # un código de tiempo; un tamaño en cero dejaba el lienzo nulo.
    fps = _number(data.get("fps"), 30.0)
    if not 1.0 <= fps <= 1000.0:
        fps = 30.0
    ancho = int(_number(data.get("width"), 1920))
    alto = int(_number(data.get("height"), 1080))
    if not 16 <= ancho <= 16384:
        ancho = 1920
    if not 16 <= alto <= 16384:
        alto = 1080

    sequence = Sequence(name=str(data.get("name") or "Secuencia 1"), fps=fps,
                        width=ancho, height=alto)
    if data.get("id"):
        sequence.id = str(data["id"])

    pistas = []
    for indice, track in enumerate(data.get("tracks") or []):
        if not isinstance(track, dict):
            continue
        kind = track.get("kind", "video")
        pistas.append(Track(
            name=str(track.get("name") or f"Pista {indice + 1}"),
            kind=kind if kind in TRACK_KINDS else "video",
            clips=[item_from_dict(c, base) for c in track.get("clips") or []],
            enabled=bool(track.get("enabled", True)),
            locked=bool(track.get("locked", False)),
            muted=bool(track.get("muted", False)),
            solo=bool(track.get("solo", False)),
            role=str(track.get("role", "Normal")),
        ))
    for pista in pistas:
        pista.clips.sort(key=lambda c: c.start)
    sequence.tracks = pistas
    sequence.markers = _markers(data.get("markers"))
    sequence.duck_depth = _number(data.get("duck_depth"), 12.0, 0.0, 60.0)
    return sequence


# --- migraciones ------------------------------------------------------------
#
# Cada función lleva un proyecto de una versión del formato a la siguiente.
# Se aplican en cadena: uno del formato 1 pasa por 1→2 y luego por 2→3.
#
# Así, cada vez que cambie el formato basta con escribir UNA función nueva, y
# los proyectos de cualquier versión anterior siguen abriendo. Sin la cadena,
# cada cambio obligaría a pensar en todas las combinaciones posibles.

def _de_1_a_2(data: dict) -> dict:
    """Máscaras, fusión, curva, viñeta y animación de texto.

    Todos son campos nuevos con valor por omisión, así que no hay nada que
    reescribir: el dataclass los llena solo al cargar.
    """
    return data


def _de_2_a_3(data: dict) -> dict:
    """El caché de sondeos de medios."""
    data.setdefault("media", [])
    return data


def _de_3_a_4(data: dict) -> dict:
    """Lo del nivel 2 del roadmap. Todo son campos nuevos con valor por
    omisión, así que tampoco hay nada que reescribir.

    Hay un cambio de aspecto que sí se nota: antes el material de otra
    proporción se **estiraba** para llenar el cuadro, que era un error. Los
    clips ahora entran en modo Ajustar. No se migra a Estirar a propósito:
    conservar la deformación sería conservar el error.
    """
    return data


def _de_4_a_5(data: dict) -> dict:
    """Nivel 3. Los keyframes viejos `[t, v]` siguen valiendo tal cual: sin
    interpolación escrita, cada uno usa la de omisión. Lo demás son campos
    nuevos con valor por omisión."""
    return data


def _de_5_a_6(data: dict) -> dict:
    """Nivel 4. Campos nuevos con valor por omisión: el remapeo de tiempo son
    keyframes de la ruta `time`, que un proyecto viejo simplemente no trae."""
    return data


MIGRATIONS = {1: _de_1_a_2, 2: _de_2_a_3, 3: _de_3_a_4, 4: _de_4_a_5, 5: _de_5_a_6}


def migrate(data: dict) -> dict:
    """Lleva un proyecto de cualquier formato anterior al actual.

    Un proyecto sin número de formato es anterior a que existiera el número,
    así que cuenta como el 1.
    """
    if not isinstance(data, dict):
        raise ProjectError("El archivo no es un proyecto de Vortex Studio.")
    data = dict(data)
    try:
        version = max(1, int(data.get("formato", 1) or 1))
    except (TypeError, ValueError):
        raise ProjectError("El número de formato del proyecto está dañado.") from None

    if version > FORMAT_VERSION:
        raise ProjectError(
            f"El proyecto es de una versión más nueva (formato {version}). "
            f"Esta versión de Vortex Studio entiende hasta la {FORMAT_VERSION}."
        )

    while version < FORMAT_VERSION:
        paso = MIGRATIONS.get(version)
        if paso is None:  # pragma: no cover - lo vigila una prueba
            raise ValueError(f"No hay migración del formato {version} al {version + 1}")
        data = paso(data)
        version += 1

    data["formato"] = FORMAT_VERSION
    return data


# --- el proyecto completo ---------------------------------------------------

def media_to_list(library: dict[str, MediaInfo], base: Path | None = None) -> list:
    salida = []
    for info in library.values():
        fila = asdict(info)
        fila["path"] = _write_path(info.path, base)
        salida.append(fila)
    return salida


def media_from_list(rows: list, base: Path | None = None) -> dict[str, MediaInfo]:
    """El caché de sondeos. Una fila dañada se tira: se vuelve a sondear sola."""
    library: dict[str, MediaInfo] = {}
    for fila in rows if isinstance(rows, list) else []:
        if not isinstance(fila, dict) or not fila.get("path"):
            continue
        datos = _fields(MediaInfo, fila)
        datos["path"] = _read_path(str(fila["path"]), base)
        try:
            info = MediaInfo(**datos)
        except TypeError:
            continue
        library[library_key(info.path)] = info
    return library


def project_to_dict(project: Project, base: Path | None = None) -> dict:
    return {
        "formato": FORMAT_VERSION,
        "name": project.name,
        "sequences": [sequence_to_dict(s, base) for s in project.sequences],
        "activa": project.active.id,
        "media": media_to_list(project.media, base),
        "version_base": project.version_base,
    }


def project_from_dict(data: dict, base: Path | None = None) -> Project:
    data = migrate(data)

    project = Project(name=str(data.get("name") or "Sin título"))
    crudas = data.get("sequences")
    sequences = [sequence_from_dict(s, base) for s in crudas if isinstance(s, dict)] \
        if isinstance(crudas, list) else []
    project.sequences = sequences or [Sequence.default()]
    project.media = media_from_list(data.get("media", []), base)
    project.active_id = str(data.get("activa") or "")
    project.version_base = str(data.get("version_base") or "")
    return project


def save_project(project: Project, path: str | Path) -> Path:
    """Escribe el proyecto a un temporal y lo pone en su lugar de un jalón.

    Antes se escribía directo encima: si el disco se llenaba o se iba la luz
    a media escritura, el .vortex quedaba cortado y ya no abría — justo el
    archivo que el usuario acababa de pedir que se guardara.

    Un archivo de solo lectura se respeta: renombrar encima lo sobrescribiría
    igual, así que se revisa antes.
    """
    path = Path(path).with_suffix(EXTENSION)
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"«{path.name}» es de solo lectura.")
    # `encoding="utf-8"` explícito: en Windows el valor por omisión suele ser
    # cp1252 y los acentos de los nombres se escribirían mal.
    texto = json.dumps(project_to_dict(project, path.parent), indent=2, ensure_ascii=False)
    temporal = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporal.write_text(texto, encoding="utf-8")
        os.replace(temporal, path)
    finally:
        temporal.unlink(missing_ok=True)
    return path


def load_project(path: str | Path) -> Project:
    path = Path(path)
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise ProjectError(f"«{path.name}» no es un proyecto de Vortex Studio: "
                           f"no es texto.") from None
    except json.JSONDecodeError as error:
        raise ProjectError(f"«{path.name}» está dañado: se corta en la línea "
                           f"{error.lineno}.") from None
    return project_from_dict(datos, path.parent)
