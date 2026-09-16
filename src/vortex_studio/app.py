"""Punto de entrada.

Los imports pesados (PyAV, los widgets) se hacen dentro de `main()` a
propósito, después de mostrar el splash. Si se hicieran arriba, la pantalla
de carga aparecería cuando la carga ya terminó, que es justo al revés.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from vortex_studio import __version__

ASSETS = Path(__file__).resolve().parent / "assets"
SMOKE_FLAG = "--smoke-test"
SELF_CHECK_FLAG = "--self-check"     # ver `selfcheck.py`


def app_icon() -> QIcon:
    """El ícono de la ventana, con todos los tamaños que hay en `assets/`."""
    icono = QIcon()
    for archivo in sorted(ASSETS.glob("vortex-studio-*.png")):
        icono.addFile(str(archivo))
    return icono


def smoke_test(app: QApplication) -> int:
    """Arma el editor completo sin mostrarlo y sale. Para `--smoke-test`.

    Lo corre la compilación de los binarios antes de publicarlos: un
    ejecutable de PyInstaller puede compilar sin errores y aun así tronar al
    abrir porque le faltó una biblioteca de Qt o de FFmpeg. Esto lo descubre
    en la máquina de compilación y no en la del usuario.

    Si algo falla y `VORTEX_SMOKE_LOG` apunta a un archivo, ahí se escribe el
    error: en Windows el ejecutable no tiene consola donde imprimirlo.
    """
    try:
        import numpy  # noqa: F401
        import av

        from vortex_studio.media import HAS_PYAV
        from vortex_studio.ui import MainWindow

        if not HAS_PYAV:
            raise RuntimeError("PyAV no cargó")
        faltan = [c for c in ("h264", "aac") if c not in av.codecs_available]
        if faltan:
            raise RuntimeError(f"Faltan códecs en el FFmpeg empacado: {', '.join(faltan)}")

        ventana = MainWindow()
        app.processEvents()
        ventana._dirty = False
        ventana.close()
        app.processEvents()
    except Exception:
        destino = os.environ.get("VORTEX_SMOKE_LOG")
        if destino:
            Path(destino).write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
        return 1
    return 0


def _dark_palette() -> QPalette:
    """Tema oscuro. Un editor de video se usa en cuarto oscuro, no en blanco."""
    from vortex_studio.ui import theme

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme.FONDO))
    palette.setColor(QPalette.WindowText, QColor(theme.TEXTO))
    palette.setColor(QPalette.Base, QColor(theme.CAMPO))
    palette.setColor(QPalette.AlternateBase, QColor(theme.TARJETA))
    palette.setColor(QPalette.Text, QColor(theme.TEXTO))
    palette.setColor(QPalette.Button, QColor(theme.CAMPO))
    palette.setColor(QPalette.ButtonText, QColor(theme.TEXTO))
    palette.setColor(QPalette.Highlight, QColor(theme.PILDORA))
    palette.setColor(QPalette.HighlightedText, QColor(theme.ACENTO))
    palette.setColor(QPalette.ToolTipBase, QColor(theme.CAMPO))
    palette.setColor(QPalette.ToolTipText, QColor(theme.TEXTO))
    palette.setColor(QPalette.PlaceholderText, QColor(theme.MUY_TENUE))
    return palette


def error_log() -> Path:
    """Dónde se apunta un error que tumbó el arranque."""
    base = Path(os.environ.get("VORTEX_CACHE_DIR")
                or os.environ.get("XDG_CACHE_HOME")
                or (Path.home() / ".cache")) / "vortex-studio"
    base.mkdir(parents=True, exist_ok=True)
    return base / "error.log"


def report_crash(error: BaseException) -> Path | None:
    """Apunta el error en un archivo y lo dice también por la salida de errores.

    El ejecutable de Windows va sin consola: sin esto, un error antes de la
    ventana era doble clic y nada, sin manera de saber qué pasó.
    """
    detalle = "".join(traceback.format_exception(error))
    sys.stderr.write(detalle)
    try:
        ruta = error_log()
        with ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} — "
                          f"Vortex Studio {__version__} ===\n{detalle}")
        return ruta
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except Exception as error:
        ruta = report_crash(error)
        _show_crash(error, ruta)
        return 1


def _show_crash(error: BaseException, ruta: Path | None) -> None:
    """Un aviso con lo que pasó, si es que alcanza a haber ventanas."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            return
        texto = f"{type(error).__name__}: {error}"
        if ruta is not None:
            texto += f"\n\nEl detalle quedó en:\n{ruta}"
        QMessageBox.critical(None, "Vortex Studio no pudo abrir", texto)
    except Exception:
        pass


def _main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    humo = SMOKE_FLAG in argv
    revision = SELF_CHECK_FLAG in argv
    if humo or revision:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Vortex Studio")
    app.setApplicationVersion(__version__)
    # Con este nombre el escritorio de Linux empareja la ventana con su
    # entrada del menú, y en Wayland la barra de tareas le pone su ícono.
    app.setDesktopFileName("vortex-studio")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())

    if humo:
        return smoke_test(app)
    if revision:
        from vortex_studio import selfcheck

        return selfcheck.main(app)

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
