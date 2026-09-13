"""Leer LUTs `.cube`: lo mínimo para saber si el archivo sirve.

Quien aplica el LUT es el filtro `lut3d` de FFmpeg. Aquí solo se valida el
archivo al cargarlo: un LUT roto tiene que avisar en ese momento, no dejar
el clip en negro sin decir por qué.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cube:
    size: int
    title: str
    table: list        # size³ tríos RGB, rojo cambiando más rápido


def read_cube(path: str | Path) -> Cube:
    size = 0
    titulo = ""
    tabla: list[tuple[float, float, float]] = []
    for linea in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split()
        clave = partes[0].upper()
        if clave == "TITLE":
            titulo = linea[5:].strip().strip('"')
        elif clave == "LUT_3D_SIZE":
            size = int(partes[1])
        elif clave == "LUT_1D_SIZE":
            raise ValueError("es un LUT 1D; se necesita uno 3D")
        elif clave in ("DOMAIN_MIN", "DOMAIN_MAX"):
            continue
        else:
            try:
                tabla.append(tuple(float(v) for v in partes[:3]))
            except ValueError:
                raise ValueError(f"línea que no entiendo: {linea[:40]}") from None
    if size < 2:
        raise ValueError("no trae LUT_3D_SIZE")
    if len(tabla) != size ** 3:
        raise ValueError(f"trae {len(tabla)} valores y debían ser {size ** 3}")
    return Cube(size, titulo, tabla)


def write_cube(path: str | Path, size: int, fn, title: str = "") -> Path:
    """Escribe un LUT desde una función (r, g, b) -> (r, g, b). Para pruebas y looks."""
    lineas = [f'TITLE "{title}"'] if title else []
    lineas.append(f"LUT_3D_SIZE {size}")
    for b in range(size):
        for g in range(size):
            for r in range(size):
                x = [v / (size - 1) for v in (r, g, b)]
                lineas.append(" ".join(f"{v:.6f}" for v in fn(*x)))
    ruta = Path(path)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta
