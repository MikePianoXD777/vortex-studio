# -*- mode: python ; coding: utf-8 -*-
"""Receta de compilación para PyInstaller.

Modo onedir: arranca rápido porque no descomprime nada al abrir.
El resultado queda en dist/vortex-studio/.
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(SPECPATH, "empaquetado"))
from bibliotecas_linux import binarios_x11  # noqa: E402

# OCIO y AAF son opcionales: entran al ejecutable solo si están instalados
# en el entorno que compila (la compilación de los binarios instala `.[pro]`).
OPCIONALES = [m for m in ("PyOpenColorIO", "aaf2") if importlib.util.find_spec(m)]

a = Analysis(
    ["src/vortex_studio/__main__.py"],
    pathex=["src"],
    # En Linux, las bibliotecas de X11 que Qt pide y no todos los escritorios
    # traen. Ver `empaquetado/bibliotecas_linux.py`.
    binaries=binarios_x11(),
    # El ícono va adentro para que la ventana lo use en cualquier sistema.
    datas=[("src/vortex_studio/assets", "vortex_studio/assets")],
    hiddenimports=["av", *OPCIONALES],
    # PySide6 trae módulos pesados que no usamos; fuera del paquete.
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtQuick3D", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtDesigner",
        # numpy YA NO va aquí: desde la 0.3 calcula la onda y los fundidos
        # de audio. Excluido, el ejecutable tronaba al abrir un clip.
        "tkinter", "matplotlib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="vortex-studio",
    console=False,          # app de ventana: sin terminal detrás
    strip=False,
    upx=False,
    icon="src/vortex_studio/assets/vortex-studio.ico",   # el del .exe en Windows
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="vortex-studio",
)
