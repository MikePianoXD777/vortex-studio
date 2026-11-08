"""La interfaz de Vortex Photo.

`PhotoWindow` se importa hasta que alguien la pide, igual que `MainWindow`:
elegir «Video» en el launcher no debe cargar el editor de fotos.
"""

__all__ = ["PhotoWindow"]


def __getattr__(nombre: str):
    if nombre == "PhotoWindow":
        from vortex_studio.ui.photo.window import PhotoWindow

        return PhotoWindow
    raise AttributeError(f"module 'vortex_studio.ui.photo' has no attribute {nombre!r}")
