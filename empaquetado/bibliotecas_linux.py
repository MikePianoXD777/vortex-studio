"""Bibliotecas de Linux que el paquete trae aunque sean del sistema.

PyInstaller no empaca las bibliotecas del sistema, a propósito: casi todas
están en cualquier escritorio. Estas no. El plugin de X11 de Qt 6 pide
`libxcb-cursor` y otras utilidades de xcb que Ubuntu 22.04, Mint o XFCE no
instalan solas, y sin ellas el editor no abre en una sesión X11. Truena con
"could not load the Qt platform plugin xcb" antes de mostrar nada. En Wayland
no se nota, por eso pasó desapercibido en la 0.1.0b1.

Son chicas, con licencia MIT y solo dependen de libxcb, que sí está en todos
lados. Van dentro del paquete.

La receta (`vortex-studio.spec`) las busca al compilar. En la compilación
automática `VORTEX_STRICT_BUNDLE=1` hace que falte una y la compilación
truene; en la compu de uno solo avisa.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

X11 = (
    "libxcb-cursor.so.0",
    "libxcb-icccm.so.4",
    "libxcb-image.so.0",
    "libxcb-keysyms.so.1",
    "libxcb-render-util.so.0",
    "libxcb-util.so.1",
    "libxkbcommon-x11.so.0",
)

CARPETAS = ("/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib")

# Dentro del paquete van en dos lugares. Quien las pide es `libQt6XcbQpa.so.6`,
# que solo busca en su propia carpeta (RUNPATH `$ORIGIN`), y PyInstaller deja
# DOS copias de ella: una junto a las demás de Qt y otra en la raíz del
# paquete. Cuál carga el ejecutable depende de la ruta de bibliotecas de cada
# máquina: aquí cargaba la de Qt, en el Ubuntu de la compilación seguía
# tronando. Con las bibliotecas junto a las dos copias, cualquiera que se
# cargue las encuentra. Pesan unos cientos de KB.
DESTINO = "PySide6/Qt/lib"
DESTINOS = (DESTINO, ".")


class Falta(RuntimeError):
    """Una biblioteca que tiene que ir en el paquete no está en la máquina."""


def buscar(nombre: str, carpetas=CARPETAS) -> Path | None:
    for carpeta in carpetas:
        ruta = Path(carpeta) / nombre
        if ruta.exists():
            return ruta
    return None


def binarios_x11(estricto: bool | None = None, carpetas=CARPETAS,
                 plataforma: str = sys.platform) -> list[tuple[str, str]]:
    """Las entradas de `binaries` para el `.spec`: (ruta, carpeta de destino).

    Van a cada carpeta de `DESTINOS`, junto a las copias de la biblioteca de
    Qt que las pide. La ruta es la del nombre corto (`.so.0`), no la del
    archivo real, para que la copia quede con el nombre que pide Qt.
    """
    if not plataforma.startswith("linux"):
        return []
    if estricto is None:
        estricto = os.environ.get("VORTEX_STRICT_BUNDLE") == "1"
    encontradas, faltan = [], []
    for nombre in X11:
        ruta = buscar(nombre, carpetas)
        if ruta is None:
            faltan.append(nombre)
        else:
            encontradas.extend((str(ruta), destino) for destino in DESTINOS)
    if faltan:
        mensaje = f"Faltan bibliotecas de X11 para empacar: {', '.join(faltan)}"
        if estricto:
            raise Falta(mensaje)
        print(f"AVISO: {mensaje}. El ejecutable no abrirá en sesiones X11 que no las tengan.")
    return encontradas
