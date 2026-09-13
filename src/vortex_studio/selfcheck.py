"""Revisión a fondo del editor, pensada para correr dentro del ejecutable.

`vortex-studio --smoke-test` solo comprueba que el editor arma su ventana.
Eso no ve lo que truena hasta que se usa: un códec que no vino en el
paquete, un formato de imagen de Qt que no se empacó, una biblioteca que
solo se carga al exportar. `vortex-studio --self-check` usa el editor como
lo usaría alguien —importa, pone en el timeline, reproduce, exporta,
guarda— con material que crea ella misma, porque el ejecutable no trae
ffmpeg.

Corre en la compilación de cada sistema antes de publicar. En Windows es la
única forma de probar el `.exe` sin tener una máquina con Windows a la mano.

Todo lo que escribe va a una carpeta temporal: cachés, ajustes y
autoguardados incluidos, para no ensuciar los del usuario si alguien la corre
en su máquina.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

SEGUNDOS = 3.0
FPS = 30
ANCHO, ALTO = 320, 180
RATE = 48000
ROJO, AZUL = (220, 40, 40), (40, 60, 220)


@dataclass
class Resultado:
    nombre: str
    ok: bool
    detalle: str = ""
    segundos: float = 0.0


class Contexto:
    """Lo que los pasos se van pasando: carpeta, material y la ventana."""

    def __init__(self, carpeta: Path, app) -> None:
        self.carpeta = carpeta
        self.app = app
        self.video = carpeta / "material.mp4"
        self.imagen = carpeta / "logo.png"
        self.srt = carpeta / "subtitulos.srt"
        self.ventana = None


class Falla(Exception):
    """Un paso corrió pero el resultado no es el esperado."""


def aislar(carpeta: Path) -> None:
    """Manda cachés, ajustes y datos a la carpeta de la revisión."""
    for variable, sub in (("VORTEX_CACHE_DIR", "cache"), ("VORTEX_CONFIG_DIR", "config"),
                          ("VORTEX_DATA_DIR", "datos")):
        os.environ.setdefault(variable, str(carpeta / sub))


def crear_video(ruta: Path, segundos: float = SEGUNDOS) -> Path:
    """Video con sonido hecho con PyAV.

    La primera mitad es roja con tono de 440 Hz; la segunda, azul y en
    silencio. Así hay un cambio de escena y un silencio que encontrar.
    """
    import av
    import numpy as np

    with av.open(str(ruta), "w") as contenedor:
        video = contenedor.add_stream("libx264", rate=FPS)
        video.width, video.height, video.pix_fmt = ANCHO, ALTO, "yuv420p"
        audio = contenedor.add_stream("aac", rate=RATE)
        audio.layout = "stereo"

        cuadros = int(round(segundos * FPS))
        bloque = 1024
        escritas = 0
        for i in range(cuadros):
            imagen = np.empty((ALTO, ANCHO, 3), np.uint8)
            imagen[:] = ROJO if i < cuadros // 2 else AZUL
            x = (i * 7) % (ANCHO // 2)            # una barra que se mueve, en la mitad izquierda
            imagen[:, x:x + 12] = 255
            cuadro = av.VideoFrame.from_ndarray(imagen, format="rgb24")
            cuadro.pts, cuadro.time_base = i, Fraction(1, FPS)
            for paquete in video.encode(cuadro):
                contenedor.mux(paquete)

            while escritas < (i + 1) * RATE / FPS:
                n = np.arange(escritas, escritas + bloque)
                tono = 0.5 * np.sin(2 * np.pi * 440 * n / RATE) * (n < RATE * segundos / 2)
                sonido = av.AudioFrame.from_ndarray(np.stack([tono, tono]).astype(np.float32),
                                                    format="fltp", layout="stereo")
                sonido.sample_rate = RATE
                sonido.pts, sonido.time_base = escritas, Fraction(1, RATE)
                for paquete in audio.encode(sonido):
                    contenedor.mux(paquete)
                escritas += bloque

        for flujo in (video, audio):
            for paquete in flujo.encode():
                contenedor.mux(paquete)
    return ruta


def _esperar(app, condicion: Callable[[], bool], segundos: float) -> bool:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.02)
    return False


def _flujos(ruta: Path) -> list[str]:
    import av

    with av.open(str(ruta)) as contenedor:
        return sorted(s.type for s in contenedor.streams)


# --- los pasos ----------------------------------------------------------------------

def paso_material(ctx: Contexto) -> str:
    from PySide6.QtGui import QColor, QImage

    crear_video(ctx.video)
    imagen = QImage(64, 64, QImage.Format_ARGB32)
    imagen.fill(QColor("#40c88c"))
    if not imagen.save(str(ctx.imagen)):
        raise Falla("Qt no pudo escribir un PNG")
    ctx.srt.write_text("1\n00:00:00,200 --> 00:00:01,000\nHola\n\n"
                       "2\n00:00:01,200 --> 00:00:02,000\nAdiós\n", encoding="utf-8")
    tipos = _flujos(ctx.video)
    if tipos != ["audio", "video"]:
        raise Falla(f"El material salió con {tipos}")
    return f"{ctx.video.stat().st_size // 1024} KB"


def paso_formatos_de_qt(ctx: Contexto) -> str:
    from PySide6.QtGui import QFontDatabase, QImage, QImageReader

    from vortex_studio.app import app_icon
    from vortex_studio.ui import theme

    formatos = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
    faltan = {"png", "jpg", "svg", "ico"} - formatos
    if faltan:
        raise Falla(f"Qt no puede leer: {', '.join(sorted(faltan))}")
    if theme.FLECHA and QImage(theme.FLECHA).isNull():
        raise Falla("No se pudo leer la flecha de los combos")
    if app_icon().isNull():
        raise Falla("No cargó el ícono")
    if not QFontDatabase.families():
        raise Falla("No hay fuentes")
    return f"{len(formatos)} formatos de imagen"


def paso_ventana(ctx: Contexto) -> str:
    from vortex_studio.ui import MainWindow

    ctx.ventana = MainWindow()
    ctx.ventana.resize(1280, 760)
    ctx.ventana.show()
    ctx.app.processEvents()
    return ""


def paso_importar(ctx: Contexto) -> str:
    ventana = ctx.ventana
    traidos = ventana.import_to_bin([ctx.video, ctx.imagen])
    if traidos != 2 or ventana.media_bin.list.count() != 2:
        raise Falla(f"Se importaron {traidos} de 2")
    ventana.media_bin.wait_thumbnails(30000)
    ctx.app.processEvents()
    return ""


def paso_miniatura(ctx: Contexto) -> str:
    from vortex_studio.media.thumbnails import extract

    if extract(ctx.video) is None:
        raise Falla("No salió la miniatura del video")
    return ""


def paso_timeline_y_monitor(ctx: Contexto) -> str:
    from PySide6.QtGui import QColor

    ventana = ctx.ventana
    ventana._place_video(ctx.video)
    if not ventana.sequence.video_tracks()[-1].clips:
        raise Falla("El video no llegó al timeline")
    ventana._seek(0.5)
    ventana._settle_preview()
    imagen = ventana.preview.current_image()
    if imagen is None or imagen.isNull():
        raise Falla("El monitor no dio cuadro")
    color = QColor(imagen.pixel(int(imagen.width() * 0.85), imagen.height() // 2))
    if not (color.red() > 150 and color.blue() < 100):
        raise Falla(f"El cuadro no se ve rojo: {color.name()}")
    return f"{imagen.width()}×{imagen.height()}"


def paso_onda(ctx: Contexto) -> str:
    ondas = ctx.ventana.timeline.waves
    ondas.get(ctx.video)
    ondas.wait(30000)
    # La onda llega por una señal encolada desde el hilo: hasta que corre el
    # ciclo de eventos, `get` sigue devolviéndola vacía.
    _esperar(ctx.app, lambda: ondas.get(ctx.video).size > 0, 10.0)
    datos = ondas.get(ctx.video)
    if datos is None or datos.size == 0 or float(abs(datos).max()) < 0.1:
        raise Falla("La onda salió vacía")
    return f"{datos.shape[1]} picos"


def paso_reproducir(ctx: Contexto) -> str:
    ventana = ctx.ventana
    ventana._seek(0.0)
    ventana.toggle_play()
    _esperar(ctx.app, lambda: ventana.timeline.playhead > 0.3, 3.0)
    ventana.toggle_play()
    if ventana.timeline.playhead <= 0.0:
        raise Falla("El playhead no avanzó al reproducir")
    salida = "con salida de audio" if ventana.audio.available else "sin salida de audio"
    return f"llegó a {ventana.timeline.playhead:.2f} s, {salida}"


def paso_escenas(ctx: Contexto) -> str:
    ventana = ctx.ventana
    ventana._seek(0.5)
    ventana.timeline.select(ventana.sequence.video_tracks()[-1].clips[0])
    encontradas = ventana.detect_scenes(split=False)
    if encontradas < 1:
        raise Falla(ventana.statusBar().currentMessage() or "No encontró el cambio de escena")
    return f"{encontradas} cambio(s)"


def paso_silencios(ctx: Contexto) -> str:
    ventana = ctx.ventana
    ventana._seek(0.5)
    quitados = ventana.remove_silences()
    if quitados < 1:
        raise Falla(ventana.statusBar().currentMessage() or "No quitó el silencio")
    ventana.undo()
    return f"{quitados} silencio(s)"


def paso_subtitulos(ctx: Contexto) -> str:
    ventana = ctx.ventana
    if ventana.import_subtitles(ctx.srt) != 2:
        raise Falla("No entraron los dos subtítulos")
    salida = ventana.export_subtitles(ctx.carpeta / "salida.vtt")
    if salida is None or "Adiós" not in Path(salida).read_text(encoding="utf-8"):
        raise Falla("No salió el VTT")
    return ""


def paso_exportar(ctx: Contexto) -> str:
    from vortex_studio.ui.render_queue import DONE

    ventana = ctx.ventana
    trabajo = ventana.queue_export(ctx.carpeta / "exportado.mp4", 0.0, 1.0, "Borrador")
    if not ventana.render_queue.wait(180):
        raise Falla("La exportación no terminó a tiempo")
    ctx.app.processEvents()
    if trabajo.status != DONE:
        raise Falla(f"La exportación terminó en {trabajo.status}: {trabajo.error}")
    tipos = _flujos(trabajo.path)
    if tipos != ["audio", "video"]:
        raise Falla(f"El archivo salió con {tipos}")
    return f"{trabajo.path.stat().st_size // 1024} KB"


def paso_render_paralelo(ctx: Contexto) -> str:
    import av

    from vortex_studio.media.segments import render_segments
    from vortex_studio.ui.renderer import SequenceRenderer

    secuencia = ctx.ventana.sequence
    ruta = render_segments(lambda: SequenceRenderer(secuencia), ctx.carpeta / "paralelo.mp4",
                           0.0, 1.0, (ANCHO, ALTO), secuencia.fps, quality="Borrador", workers=2)
    with av.open(str(ruta)) as contenedor:
        cuadros = sum(1 for _ in contenedor.decode(video=0))
    if abs(cuadros - round(secuencia.fps)) > 1:
        raise Falla(f"Salieron {cuadros} cuadros")
    return f"{cuadros} cuadros"


def paso_intercambio(ctx: Contexto) -> str:
    from vortex_studio.media import aaf_export
    from vortex_studio.model import interchange

    secuencia = ctx.ventana.sequence
    edl = interchange.write_file(ctx.carpeta / "edicion.edl", secuencia)
    xml = interchange.write_file(ctx.carpeta / "edicion.xml", secuencia)
    if not edl.read_text().startswith("TITLE") or "<xmeml" not in xml.read_text():
        raise Falla("EDL o XML mal escritos")
    if not aaf_export.available():
        return "EDL y XML; AAF no viene en este paquete"
    aaf = aaf_export.write_aaf(ctx.carpeta / "edicion.aaf", secuencia)
    if not aaf_export.read_aaf(aaf):
        raise Falla("El AAF salió sin pistas")
    return "EDL, XML y AAF"


def paso_color(ctx: Contexto) -> str:
    from vortex_studio.media import colorspace
    from vortex_studio.model.color import SPACE_PQ, ColorAdjust

    lut = colorspace.input_lut(ColorAdjust(input_space=SPACE_PQ))
    if lut is None or not Path(lut).exists():
        raise Falla("No se horneó el LUT de HDR")
    if not colorspace.has_ocio():
        return "HDR; OCIO no viene en este paquete"
    espacios = colorspace.ocio_spaces()
    if not espacios:
        raise Falla("OCIO cargó sin espacios de color")
    return f"HDR y OCIO ({len(espacios)} espacios)"


def paso_plugins(ctx: Contexto) -> str:
    from vortex_studio.model import plugins

    catalogo, _avisos = plugins.catalog()
    if not catalogo:
        raise Falla("No hay efectos")
    return f"{len(catalogo)} efectos"


def paso_estabilizar(ctx: Contexto) -> str:
    from vortex_studio.media.stabilize import load_or_analyze

    movimiento = load_or_analyze(ctx.video)
    if movimiento is None or len(movimiento) == 0:
        raise Falla("El análisis salió vacío")
    return f"{len(movimiento)} cuadros"


def paso_guardar_y_abrir(ctx: Contexto) -> str:
    from vortex_studio.model.serialize import load_project, save_project

    ventana = ctx.ventana
    ruta = save_project(ventana.project, ctx.carpeta / "proyecto")
    vuelto = load_project(ruta)
    if len(vuelto.active.video_tracks()[-1].clips) != len(ventana.sequence.video_tracks()[-1].clips):
        raise Falla("El proyecto no volvió igual")
    respaldo = ventana.autosave()
    if respaldo is None or not Path(respaldo).exists():
        raise Falla("No se autoguardó")
    return ruta.name


PASOS: list[tuple[str, Callable[[Contexto], str]]] = [
    ("material", paso_material),
    ("formatos de Qt", paso_formatos_de_qt),
    ("ventana", paso_ventana),
    ("importar", paso_importar),
    ("miniatura", paso_miniatura),
    ("timeline y monitor", paso_timeline_y_monitor),
    ("onda", paso_onda),
    ("reproducir", paso_reproducir),
    ("escenas", paso_escenas),
    ("silencios", paso_silencios),
    ("subtítulos", paso_subtitulos),
    ("exportar", paso_exportar),
    ("render en paralelo", paso_render_paralelo),
    ("EDL, XML y AAF", paso_intercambio),
    ("HDR y OCIO", paso_color),
    ("efectos", paso_plugins),
    ("estabilizar", paso_estabilizar),
    ("guardar y abrir", paso_guardar_y_abrir),
]

# Sin estos no tiene caso seguir: los demás pasos los usan.
INDISPENSABLES = {"material", "ventana"}


def run(app, carpeta: Path | None = None) -> list[Resultado]:
    """Corre todos los pasos y devuelve cómo le fue a cada uno."""
    carpeta = Path(carpeta or tempfile.mkdtemp(prefix="vortex-revision-"))
    carpeta.mkdir(parents=True, exist_ok=True)
    ctx = Contexto(carpeta, app)
    resultados: list[Resultado] = []
    for nombre, paso in PASOS:
        inicio = time.monotonic()
        try:
            detalle = paso(ctx)
            resultados.append(Resultado(nombre, True, detalle or "", time.monotonic() - inicio))
        except Exception as error:
            detalle = str(error) if isinstance(error, Falla) else traceback.format_exc()
            resultados.append(Resultado(nombre, False, detalle, time.monotonic() - inicio))
            if nombre in INDISPENSABLES:
                break
        app.processEvents()
    if ctx.ventana is not None:
        ctx.ventana._dirty = False
        ctx.ventana.close()
        app.processEvents()
    return resultados


def report(resultados: list[Resultado]) -> str:
    lineas = []
    for r in resultados:
        marca = "OK   " if r.ok else "FALLA"
        detalle = r.detalle.strip()
        if r.ok:
            lineas.append(f"{marca} {r.nombre} ({r.segundos:.1f} s){' — ' + detalle if detalle else ''}")
        else:
            lineas.append(f"{marca} {r.nombre} ({r.segundos:.1f} s)")
            lineas.extend("      " + linea for linea in detalle.splitlines())
    fallas = sum(1 for r in resultados if not r.ok)
    faltantes = len(PASOS) - len(resultados)
    resumen = f"{len(resultados) - fallas} de {len(PASOS)} pasos bien"
    if faltantes:
        resumen += f", {faltantes} sin correr"
    lineas.append(resumen)
    return "\n".join(lineas)


def main(app) -> int:
    """Para `--self-check`: corre, escribe el reporte y sale con 0 o 1."""
    carpeta = Path(tempfile.mkdtemp(prefix="vortex-revision-"))
    aislar(carpeta)
    resultados = run(app, carpeta / "trabajo")
    texto = report(resultados)
    destino = os.environ.get("VORTEX_SELFCHECK_LOG")
    if destino:
        Path(destino).write_text(texto + "\n", encoding="utf-8")
    if sys.stdout is not None:         # en Windows, sin consola, no hay dónde imprimir
        print(texto)
    completo = len(resultados) == len(PASOS)
    return 0 if completo and all(r.ok for r in resultados) else 1
