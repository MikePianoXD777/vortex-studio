"""Punto de entrada.

Los imports pesados (PyAV, los widgets) se hacen dentro de `main()` a
propósito, después de mostrar el splash. Si se hicieran arriba, la pantalla
de carga aparecería cuando la carga ya terminó, que es justo al revés.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from vortex_studio import __version__


def _dark_palette() -> QPalette:
    """Tema oscuro. Un editor de video se usa en cuarto oscuro, no en blanco."""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1b1d21"))
    palette.setColor(QPalette.WindowText, QColor("#d6dae0"))
    palette.setColor(QPalette.Base, QColor("#15171a"))
    palette.setColor(QPalette.AlternateBase, QColor("#212429"))
    palette.setColor(QPalette.Text, QColor("#d6dae0"))
    palette.setColor(QPalette.Button, QColor("#2b2f34"))
    palette.setColor(QPalette.ButtonText, QColor("#d6dae0"))
    palette.setColor(QPalette.Highlight, QColor("#3d6fa8"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#2b2f34"))
    palette.setColor(QPalette.ToolTipText, QColor("#d6dae0"))
    return palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Vortex Studio")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())

    from vortex_studio.ui.splash import SplashScreen

    splash = SplashScreen(__version__)
    splash.show()
    splash.ensure_painted()

    splash.status("Cargando códecs…")
    from vortex_studio.media import HAS_PYAV

    splash.status("Preparando interfaz…" if HAS_PYAV else "Sin códecs — continuando…")
    from vortex_studio.ui.launcher import VIDEO, Launcher

    launcher = Launcher(__version__)

    splash.status("Listo")

    # Primero se cumple el tiempo del splash, y hasta entonces aparece la
    # siguiente ventana. Al revés, la taparía: bajo Wayland no hay manera de
    # forzar que una ventana se quede encima de otra.
    splash.hold()
    launcher.show()
    splash.finish(launcher)

    if launcher.exec() != Launcher.Accepted or launcher.choice != VIDEO:
        return 0

    # El editor se importa hasta aquí: si algún día se elige Fotos, no tiene
    # por qué haberse cargado el de video.
    from vortex_studio.ui import MainWindow

    window = MainWindow()
    window.show()
    window.offer_recovery()     # si la vez pasada se cerró de golpe

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
