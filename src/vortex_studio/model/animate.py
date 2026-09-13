"""Animar cualquier parámetro: color, máscara, volumen, imagen, texto.

Hasta la 0.4 solo la transformación tenía keyframes. Aquí cualquier número
de un elemento se puede animar, nombrándolo por su **ruta**: `color.exposure`,
`mask.x`, `gain`. La transformación sigue guardando los suyos donde siempre
(`transform.keys`); lo demás va en `item.anim`, un diccionario de ruta a
lista de keyframes.

Cómo se usa sin tocar el resto del editor:

- **`view(item, local)`** entrega una copia con los valores animados ya
  puestos. El compositor y el decodificador pintan la copia y no se enteran
  de que había animación.
- **`bake(item, local)`** escribe en el valor base lo que vale la animación
  en ese instante. El valor base de algo animado no se usa para nada, así
  que se puede pisar: sirve para que los paneles muestren lo que se ve.
- **`absorb(item, local)`** hace lo contrario después de que el usuario
  movió un deslizador: si un valor animado cambió, el cambio se vuelve un
  keyframe en el playhead. Es lo que hace After Effects cuando el cronómetro
  de la propiedad está prendido.

Así los paneles de Color y Máscara animan sin saber nada de keyframes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from vortex_studio.model import keyframes as kf

TIME = "time"       # la ruta del remapeo de tiempo; ver `model/timeremap.py`


@dataclass(frozen=True)
class Param:
    path: str
    label: str
    group: str
    minimum: float
    maximum: float
    kinds: tuple = ("clip",)


def _p(path, label, group, lo, hi, kinds=("clip",)):
    return Param(path, label, group, lo, hi, kinds)


PARAMS: dict[str, Param] = {p.path: p for p in (
    _p("transform.x", "Horizontal", "Transformación", -2.0, 2.0),
    _p("transform.y", "Vertical", "Transformación", -2.0, 2.0),
    _p("transform.scale", "Tamaño", "Transformación", 0.01, 5.0),
    _p("transform.rotation", "Giro", "Transformación", -180.0, 180.0),
    _p("transform.opacity", "Opacidad", "Transformación", 0.0, 1.0),
    _p("color.exposure", "Exposición", "Color", -300.0, 300.0),
    _p("color.brightness", "Brillo", "Color", -100.0, 100.0),
    _p("color.contrast", "Contraste", "Color", 0.0, 200.0),
    _p("color.saturation", "Saturación", "Color", 0.0, 200.0),
    _p("color.gamma", "Gamma", "Color", 10.0, 300.0),
    _p("color.temperature", "Temperatura", "Color", -100.0, 100.0),
    _p("color.tint", "Tinte", "Color", -100.0, 100.0),
    _p("color.vignette", "Viñeta", "Color", 0.0, 100.0),
    _p("color.lut_intensity", "Intensidad del LUT", "Color", 0.0, 100.0),
    _p("color.lift_r", "Lift R", "Color", -100.0, 100.0),
    _p("color.lift_g", "Lift G", "Color", -100.0, 100.0),
    _p("color.lift_b", "Lift B", "Color", -100.0, 100.0),
    _p("color.gamma_r", "Gamma R", "Color", 20.0, 300.0),
    _p("color.gamma_g", "Gamma G", "Color", 20.0, 300.0),
    _p("color.gamma_b", "Gamma B", "Color", 20.0, 300.0),
    _p("color.gain_r", "Gain R", "Color", 0.0, 200.0),
    _p("color.gain_g", "Gain G", "Color", 0.0, 200.0),
    _p("color.gain_b", "Gain B", "Color", 0.0, 200.0),
    _p("mask.x", "Máscara X", "Máscara", 0.0, 1.0, ("clip", "imagen")),
    _p("mask.y", "Máscara Y", "Máscara", 0.0, 1.0, ("clip", "imagen")),
    _p("mask.width", "Máscara ancho", "Máscara", 0.01, 2.0, ("clip", "imagen")),
    _p("mask.height", "Máscara alto", "Máscara", 0.01, 2.0, ("clip", "imagen")),
    _p("mask.rotation", "Máscara giro", "Máscara", -180.0, 180.0, ("clip", "imagen")),
    _p("mask.feather", "Máscara suavizado", "Máscara", 0.0, 0.5, ("clip", "imagen")),
    _p("chroma.similarity", "Llave: similitud", "Efectos", 1.0, 100.0),
    _p("chroma.smoothness", "Llave: suavidad", "Efectos", 0.0, 100.0),
    _p("chroma.spill", "Llave: derrame", "Efectos", 0.0, 100.0),
    _p("gain", "Volumen", "Audio", 0.0, 4.0),
    _p("transform.tilt_x", "Inclinar hacia atrás", "3D y distorsión", -80.0, 80.0),
    _p("transform.tilt_y", "Girar de lado", "3D y distorsión", -80.0, 80.0),
    _p("transform.pin_tl_x", "Esquina sup. izq. X", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_tl_y", "Esquina sup. izq. Y", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_tr_x", "Esquina sup. der. X", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_tr_y", "Esquina sup. der. Y", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_br_x", "Esquina inf. der. X", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_br_y", "Esquina inf. der. Y", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_bl_x", "Esquina inf. izq. X", "3D y distorsión", -1.0, 1.0),
    _p("transform.pin_bl_y", "Esquina inf. izq. Y", "3D y distorsión", -1.0, 1.0),
    # Remapeo de tiempo: el segundo del material que se ve. Ver `timeremap.py`.
    _p("time", "Tiempo del material (s)", "Tiempo", 0.0, 3600.0),
    _p("x", "Horizontal", "Imagen", 0.0, 1.0, ("imagen", "texto")),
    _p("y", "Vertical", "Imagen", 0.0, 1.0, ("imagen", "texto")),
    _p("scale", "Tamaño", "Imagen", 0.02, 2.0, ("imagen",)),
    _p("opacity", "Opacidad", "Imagen", 0.0, 1.0, ("imagen",)),
    _p("size", "Tamaño de letra", "Texto", 0.02, 0.25, ("texto",)),
)}


def kind_of(item) -> str:
    from vortex_studio.model.overlays import AdjustmentLayer, ImageOverlay, Title
    if isinstance(item, AdjustmentLayer):
        return "ajuste"
    if isinstance(item, Title):
        return "texto"
    if isinstance(item, ImageOverlay):
        return "imagen"
    return "clip"


def params_for(item) -> list[Param]:
    clase = kind_of(item)
    salida = []
    for param in PARAMS.values():
        # Una capa de ajuste tiene lo del clip que le aplica —color, máscara—
        # y la opacidad de una imagen; lo que no tiene lo descarta `_has`.
        aplica = clase in param.kinds or (
            clase == "ajuste" and bool({"clip", "imagen"} & set(param.kinds)))
        if not aplica:
            continue
        cabeza = param.path.split(".")[0]
        if "." in param.path and not hasattr(item, cabeza):
            continue
        if param.path == TIME and not hasattr(item, "in_point"):
            continue            # solo un clip de material tiene tiempo que remapear
        if not _has(item, param.path):
            continue
        salida.append(param)
    return salida


def _has(item, path: str) -> bool:
    try:
        base_value(item, path)
        return True
    except AttributeError:
        return False


def _owner(item, path: str):
    partes = path.split(".")
    objeto = item
    for parte in partes[:-1]:
        objeto = getattr(objeto, parte)
    return objeto, partes[-1]


def base_value(item, path: str) -> float:
    if path == TIME:
        return 0.0          # el tiempo no tiene valor fijo: sin keyframes lo da la velocidad
    dueno, campo = _owner(item, path)
    return float(getattr(dueno, campo))


def set_base(item, path: str, value: float) -> None:
    if path == TIME:
        return
    dueno, campo = _owner(item, path)
    actual = getattr(dueno, campo)
    setattr(dueno, campo, int(round(value)) if isinstance(actual, int)
            and not isinstance(actual, bool) and path.startswith(("color.", "chroma."))
            else float(value))


def _default_interp(item, path: str) -> str:
    if path == TIME:
        return kf.LINEAR        # un tramo de tiempo lineal es velocidad constante
    if path.startswith("transform."):
        return kf.EASE if getattr(item.transform, "ease", True) else kf.LINEAR
    return kf.EASE


def keys_for(item, path: str) -> list:
    if path.startswith("transform."):
        return list(item.transform.keys.get(path.split(".", 1)[1], []))
    return list(getattr(item, "anim", {}).get(path, []))


def set_keys_for(item, path: str, points: list) -> None:
    """Pone la lista de keyframes. Vacía, la propiedad vuelve a ser fija con
    el último valor que tenía, para que no pegue un salto."""
    anteriores = keys_for(item, path)
    if path.startswith("transform."):
        destino = item.transform.keys
        clave = path.split(".", 1)[1]
    else:
        if not hasattr(item, "anim") or item.anim is None:
            item.anim = {}
        destino = item.anim
        clave = path
    if points:
        destino[clave] = [list(k) for k in points]
    else:
        destino.pop(clave, None)
        if anteriores:
            set_base(item, path, kf.value_of(anteriores[0]))


def is_animated(item, path: str) -> bool:
    return bool(keys_for(item, path))


def animated_paths(item) -> list[str]:
    rutas = [f"transform.{p}" for p, k in getattr(getattr(item, "transform", None), "keys",
                                                    {}).items() if k]
    rutas += [p for p, k in (getattr(item, "anim", None) or {}).items() if k]
    return rutas


def value_at(item, path: str, local: float) -> float:
    puntos = keys_for(item, path)
    if not puntos:
        if path == TIME:
            from vortex_studio.model.timeremap import material_at
            return material_at(item, local)
        return base_value(item, path)
    return kf.evaluate(puntos, local, _default_interp(item, path))


def add_key(item, path: str, local: float, value: float | None = None,
            interp: str | None = None) -> None:
    valor = value_at(item, path, local) if value is None else value
    set_keys_for(item, path, kf.set_key(keys_for(item, path), local, valor, interp))


def remove_key(item, path: str, local: float, tolerance: float = 0.05) -> bool:
    antes = keys_for(item, path)
    despues = kf.remove_key(antes, local, tolerance)
    if len(despues) == len(antes):
        return False
    set_keys_for(item, path, despues)
    return True


def all_key_times(item) -> list[float]:
    tiempos = set()
    for ruta in animated_paths(item):
        tiempos.update(kf.time_of(k) for k in keys_for(item, ruta))
    return sorted(tiempos)


# --- lo que usa el resto del editor ---------------------------------------------

def view(item, local: float):
    """Una copia con los valores de ese instante. Sin animación, el mismo objeto.

    La transformación no se copia: ya se evalúa sola con `values_at`.
    """
    # El tiempo no se pinta: lo usa `Clip.source_time` directo.
    rutas = [r for r in (getattr(item, "anim", None) or {}) if item.anim[r] and r != TIME]
    if not rutas:
        return item
    copia = copy.copy(item)
    for cabeza in {r.split(".")[0] for r in rutas if "." in r}:
        original = getattr(item, cabeza)
        setattr(copia, cabeza, original.copy() if hasattr(original, "copy")
                else copy.deepcopy(original))
    for ruta in rutas:
        valor = kf.evaluate(item.anim[ruta], local, kf.EASE)
        dueno, campo = _owner(copia, ruta)
        setattr(dueno, campo, valor)
    return copia


def bake(item, local: float) -> None:
    for ruta in animated_paths(item):
        if ruta.startswith("transform."):
            continue
        set_base(item, ruta, value_at(item, ruta, local))


def absorb(item, local: float, tolerance: float = 1e-6) -> list[str]:
    """Convierte en keyframe lo que el usuario movió de un valor animado."""
    cambiadas = []
    for ruta in animated_paths(item):
        if ruta.startswith("transform.") or ruta == TIME:
            continue
        base = base_value(item, ruta)
        if abs(base - value_at(item, ruta, local)) > max(tolerance, 1e-6):
            set_keys_for(item, ruta, kf.set_key(keys_for(item, ruta), local, base))
            cambiadas.append(ruta)
    return cambiadas


def shift_all(item, delta: float) -> None:
    """Recorre todos los keyframes. Lo usa dividir, para la segunda mitad."""
    if hasattr(item, "transform"):
        for prop, puntos in list(item.transform.keys.items()):
            item.transform.keys[prop] = kf.shift(puntos, delta)
    for ruta, puntos in list((getattr(item, "anim", None) or {}).items()):
        item.anim[ruta] = kf.shift(puntos, delta)
