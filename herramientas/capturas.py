"""Capturas de la ventana sin abrirla en pantalla, para revisar la interfaz.

    ./.venv/bin/python herramientas/capturas.py carpeta-de-salida [ANCHOxALTO ...]

Genera su propio material con ffmpeg (dos videos con sonido y una música),
arma una secuencia y guarda una captura por tamaño, más una de cada pestaña
del panel de propiedades. Corre con la plataforma `offscreen` de Qt: no
aparece ninguna ventana.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def _material(base: Path) -> dict[str, Path]:
    def ffmpeg(*args: str) -> None:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)

    base.mkdir(parents=True, exist_ok=True)
    toma1, toma2, musica = base / "toma1.mp4", base / "toma2.mp4", base / "musica.wav"
    if not toma1.exists():
        ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=20",
               "-f", "lavfi", "-i", "sine=frequency=330:duration=20",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(toma1))
        ffmpeg("-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=30",
               "-f", "lavfi", "-i", "anoisesrc=d=15:c=pink:a=0.2", "-t", "15",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(toma2))
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=40,volume=-6dB",
               "-ac", "2", str(musica))
    return {"toma1": toma1, "toma2": toma2, "musica": musica}


def main() -> None:
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else "capturas")
    tamanos = sys.argv[2:] or ["1280x720", "1440x860", "1920x1080"]
    salida.mkdir(parents=True, exist_ok=True)
    medios = _material(Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "vortex-capturas")

    from PySide6.QtWidgets import QApplication

    from vortex_studio.app import _dark_palette

    app = QApplication([])
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())

    from vortex_studio.ui import MainWindow

    def esperar(segundos: float) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.01)

    for tamano in tamanos:
        ancho, alto = (int(n) for n in tamano.split("x"))
        ventana = MainWindow()
        ventana.resize(ancho, alto)
        ventana.show()
        esperar(0.4)
        ventana.grab().save(str(salida / f"vacio-{tamano}.png"))

        ventana._place_video(medios["toma1"])
        ventana._place_video(medios["toma2"])
        ventana._place_audio(medios["musica"])
        ventana._seek(8.0)
        ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
        esperar(2.0)
        ventana.grab().save(str(salida / f"lleno-{tamano}.png"))

        if tamano == tamanos[0]:
            panel = ventana.panel
            for nombre in ("clip", "transform", "color", "mask", "effects"):
                panel.show_page(getattr(panel, nombre))
                esperar(0.3)
                panel.grab().save(str(salida / f"panel-{nombre}.png"))
            ventana.timeline.select(ventana.sequence.audio_tracks()[1].clips[0])
            panel.show_page(panel.audio)
            esperar(0.3)
            panel.grab().save(str(salida / "panel-audio.png"))

        ventana._dirty = False
        ventana.close()
    print(f"Capturas en {salida.resolve()}")


if __name__ == "__main__":
    main()
