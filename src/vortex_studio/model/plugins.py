"""Efectos como plugins: un archivo JSON describe un filtro y sus controles.

Cualquiera puede agregar un efecto sin tocar el código: se deja un `.json`
en la carpeta `plugins` de la configuración y aparece en el panel de
Efectos con sus deslizadores. Un plugin dice qué filtro de FFmpeg usa, qué
opciones son deslizadores —con su rango y su valor de omisión— y qué
opciones van fijas:

    {
      "id": "nitidez",
      "nombre": "Nitidez",
      "filtro": "unsharp",
      "parametros": [
        {"id": "cantidad", "nombre": "Cantidad", "opcion": "la",
         "min": 0, "max": 3, "omision": 1}
      ],
      "fijos": {"lx": 5, "ly": 5}
    }

**Declarativo a propósito, y con lista de filtros permitidos.** Un plugin
no trae código, así que no puede hacer nada más que poner un filtro de
video en la cadena de color. Y solo filtros que trabajan cuadro por cuadro
y sin archivos: nada de `movie` ni `amovie`, que abren archivos, ni de los
que dependen de cuadros anteriores, que harían que el preview y la
exportación no coincidieran. Los nombres de opción se validan letra por
letra y los valores son números dentro de su rango: un JSON malicioso no
puede meter nada a la cadena del filtro.

Un plugin que no pasa la validación se ignora y se avisa; nunca impide abrir
el editor.

Python puro.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Filtros de video que PyAV trae y que trabajan un cuadro a la vez, sin archivos.
ALLOWED_FILTERS = {
    "unsharp", "gblur", "noise", "hue", "vibrance", "lenscorrection", "chromashift",
    "edgedetect", "negate", "hflip", "vflip", "pixelize", "monochrome", "deband",
    "median", "colortemperature", "exposure", "colorchannelmixer", "selectivecolor",
    "colorbalance", "sobel", "convolution", "rotate", "vignette",
}

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_WORD = re.compile(r"^[A-Za-z0-9_.#+-]{1,40}$")


class PluginError(ValueError):
    """El plugin no es válido. El mensaje es para el usuario."""


@dataclass(frozen=True)
class Param:
    id: str
    label: str
    option: str
    minimum: float
    maximum: float
    default: float
    integer: bool = False

    def clamp(self, valor) -> float:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            numero = self.default
        if numero != numero:            # NaN
            numero = self.default
        numero = max(self.minimum, min(self.maximum, numero))
        return float(round(numero)) if self.integer else numero


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    filter: str
    params: tuple = ()
    fixed: tuple = ()               # ((opción, valor), …)
    source: str = "incluido"        # o la ruta del archivo

    def defaults(self) -> dict:
        return {p.id: p.default for p in self.params}

    def arguments(self, valores: dict | None) -> str:
        """Las opciones del filtro, ya validadas: `la=1.5:lx=5:ly=5`."""
        valores = valores or {}
        partes = []
        for param in self.params:
            numero = param.clamp(valores.get(param.id, param.default))
            texto = str(int(numero)) if param.integer else f"{numero:.6g}"
            partes.append(f"{param.option}={texto}")
        partes += [f"{opcion}={valor}" for opcion, valor in self.fixed]
        return ":".join(partes)


def from_dict(datos: dict, source: str = "incluido") -> Plugin:
    """Valida y arma un plugin. Truena con `PluginError` si algo no cuadra."""
    if not isinstance(datos, dict):
        raise PluginError("no es un objeto JSON")
    ident = str(datos.get("id", ""))
    if not _NAME.match(ident):
        raise PluginError(f"id inválido: «{ident}» (minúsculas, números y guion bajo)")
    filtro = str(datos.get("filtro", ""))
    if filtro not in ALLOWED_FILTERS:
        raise PluginError(f"el filtro «{filtro}» no está permitido")
    nombre = str(datos.get("nombre") or ident)[:40]

    params = []
    vistos = set()
    for crudo in datos.get("parametros") or []:
        if not isinstance(crudo, dict):
            raise PluginError("un parámetro no es un objeto")
        pid, opcion = str(crudo.get("id", "")), str(crudo.get("opcion", ""))
        if not _NAME.match(pid) or not _NAME.match(opcion) or pid in vistos:
            raise PluginError(f"parámetro inválido o repetido: «{pid}»")
        try:
            minimo, maximo = float(crudo["min"]), float(crudo["max"])
            omision = float(crudo.get("omision", minimo))
        except (KeyError, TypeError, ValueError):
            raise PluginError(f"«{pid}» necesita min y max numéricos") from None
        if not minimo < maximo:
            raise PluginError(f"«{pid}»: min tiene que ser menor que max")
        entero = bool(crudo.get("entero", False))
        params.append(Param(pid, str(crudo.get("nombre") or pid)[:40], opcion, minimo, maximo,
                            max(minimo, min(maximo, omision)), entero))
        vistos.add(pid)

    fijos = []
    for opcion, valor in (datos.get("fijos") or {}).items():
        if not _NAME.match(str(opcion)):
            raise PluginError(f"opción fija inválida: «{opcion}»")
        if isinstance(valor, bool) or not (isinstance(valor, (int, float))
                                           or _WORD.match(str(valor))):
            raise PluginError(f"valor fijo inválido en «{opcion}»")
        fijos.append((str(opcion), valor if isinstance(valor, (int, float)) else str(valor)))
    return Plugin(ident, nombre, filtro, tuple(params), tuple(fijos), source)


BUILTIN = [
    {"id": "nitidez", "nombre": "Nitidez", "filtro": "unsharp",
     "parametros": [{"id": "cantidad", "nombre": "Cantidad", "opcion": "la",
                     "min": 0, "max": 3, "omision": 1}],
     "fijos": {"lx": 5, "ly": 5}},
    {"id": "desenfoque", "nombre": "Desenfoque", "filtro": "gblur",
     "parametros": [{"id": "radio", "nombre": "Radio", "opcion": "sigma",
                     "min": 0.1, "max": 30, "omision": 4}]},
    {"id": "grano", "nombre": "Grano de película", "filtro": "noise",
     "parametros": [{"id": "fuerza", "nombre": "Fuerza", "opcion": "alls",
                     "min": 0, "max": 60, "omision": 12, "entero": True}],
     "fijos": {"allf": "t"}},
    {"id": "pixelado", "nombre": "Pixelado", "filtro": "pixelize",
     "parametros": [{"id": "ancho", "nombre": "Ancho del bloque", "opcion": "w",
                     "min": 2, "max": 64, "omision": 16, "entero": True},
                    {"id": "alto", "nombre": "Alto del bloque", "opcion": "h",
                     "min": 2, "max": 64, "omision": 16, "entero": True}]},
    {"id": "aberracion", "nombre": "Aberración cromática", "filtro": "chromashift",
     "parametros": [{"id": "azul", "nombre": "Azul", "opcion": "cbh",
                     "min": -20, "max": 20, "omision": 4, "entero": True},
                    {"id": "rojo", "nombre": "Rojo", "opcion": "crh",
                     "min": -20, "max": 20, "omision": -4, "entero": True}]},
    {"id": "vibrancia", "nombre": "Vibrancia", "filtro": "vibrance",
     "parametros": [{"id": "intensidad", "nombre": "Intensidad", "opcion": "intensity",
                     "min": -2, "max": 2, "omision": 0.5}]},
    {"id": "lente", "nombre": "Distorsión de lente", "filtro": "lenscorrection",
     "parametros": [{"id": "k1", "nombre": "Curvatura", "opcion": "k1",
                     "min": -1, "max": 1, "omision": -0.2},
                    {"id": "k2", "nombre": "Curvatura de orillas", "opcion": "k2",
                     "min": -1, "max": 1, "omision": 0}]},
    {"id": "espejo", "nombre": "Espejo horizontal", "filtro": "hflip"},
    {"id": "negativo", "nombre": "Negativo", "filtro": "negate"},
    {"id": "bordes", "nombre": "Bordes", "filtro": "edgedetect",
     "parametros": [{"id": "bajo", "nombre": "Umbral bajo", "opcion": "low",
                     "min": 0.01, "max": 1, "omision": 0.1},
                    {"id": "alto", "nombre": "Umbral alto", "opcion": "high",
                     "min": 0.01, "max": 1, "omision": 0.4}]},
]


def plugins_dir() -> Path:
    """`plugins` dentro de la carpeta de configuración (o de `VORTEX_CONFIG_DIR`)."""
    propia = os.environ.get("VORTEX_CONFIG_DIR")
    if propia:
        base = Path(propia)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "VortexStudio"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "VortexStudio"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vortex-studio"
    return base / "plugins"


def catalog(folder: Path | None = None) -> tuple[dict[str, Plugin], list[str]]:
    """Los plugins incluidos más los del usuario, y los avisos de los que no sirvieron.

    Uno del usuario con el mismo id que uno incluido lo reemplaza: así se
    puede ajustar un efecto de fábrica sin esperar una versión nueva.
    """
    plugins = {p["id"]: from_dict(p) for p in BUILTIN}
    avisos: list[str] = []
    carpeta = Path(folder) if folder is not None else plugins_dir()
    if carpeta.is_dir():
        for archivo in sorted(carpeta.glob("*.json")):
            try:
                plugin = from_dict(json.loads(archivo.read_text(encoding="utf-8")), str(archivo))
            except (OSError, ValueError) as error:
                avisos.append(f"Plugin {archivo.name}: {error}")
                continue
            plugins[plugin.id] = plugin
    return plugins, avisos


_cache: dict | None = None


def get(ident: str) -> Plugin | None:
    """El plugin de ese id, del catálogo leído una vez por sesión."""
    global _cache
    if _cache is None:
        _cache = catalog()[0]
    return _cache.get(ident)


def reload() -> list[str]:
    global _cache
    _cache, avisos = catalog()
    return avisos


@dataclass
class Effect:
    """Un efecto puesto en un clip: qué plugin, con qué valores, prendido o no."""

    plugin: str
    values: dict = field(default_factory=dict)
    enabled: bool = True

    @property
    def signature(self) -> tuple:
        return (self.plugin, tuple(sorted(self.values.items())), self.enabled)


def clean_effects(raw) -> list[dict]:
    """La lista de efectos de un proyecto, sin lo que no tiene forma de efecto."""
    salida = []
    for crudo in raw if isinstance(raw, list) else []:
        if not isinstance(crudo, dict) or not _NAME.match(str(crudo.get("plugin", ""))):
            continue
        valores = {str(k): float(v) for k, v in (crudo.get("values") or {}).items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v}
        salida.append({"plugin": str(crudo["plugin"]), "values": valores,
                       "enabled": bool(crudo.get("enabled", True))})
    return salida
