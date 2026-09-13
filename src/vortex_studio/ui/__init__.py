"""La interfaz.

`MainWindow` se importa hasta que alguien la pide. Si se importara aquí
arriba, cualquier `from vortex_studio.ui import theme` —que el splash usa
para sus colores— cargaría el editor entero antes de mostrar la pantalla de
carga, y el splash aparecería cuando la carga ya terminó.
"""

__all__ = ["MainWindow"]


def __getattr__(nombre: str):
    if nombre == "MainWindow":
        from vortex_studio.ui.main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module 'vortex_studio.ui' has no attribute {nombre!r}")
