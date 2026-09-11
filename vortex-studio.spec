# -*- mode: python ; coding: utf-8 -*-
"""Receta de compilación para PyInstaller.

Modo onedir: arranca rápido porque no descomprime nada al abrir.
El resultado queda en dist/vortex-studio/.
"""

a = Analysis(
    ["src/vortex_studio/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=["av"],
    # PySide6 trae módulos pesados que no usamos; fuera del paquete.
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtQuick3D", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtDesigner",
        "tkinter", "numpy", "matplotlib",
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
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="vortex-studio",
)
