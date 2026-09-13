"""Render por segmentos en paralelo, unidos sin volver a codificar.

Componer un cuadro —decodificar, corregir color, pintar capas— usa sobre
todo un núcleo: el compositor de Qt y los filtros de FFmpeg de un cuadro no
se reparten solos. Con ocho núcleos, exportar dejaba siete sin hacer nada.

Aquí el tramo se parte en segmentos del mismo largo, cada segmento se
exporta en su propio hilo con **su propia copia** de la secuencia y sus
propios decodificadores, y al final los archivos se **pegan sin
recodificar**: se copian los paquetes de H.264 uno tras otro, corriendo sus
marcas de tiempo. El audio se mezcla una sola vez, en orden, al pegar.

Hilos y no procesos: PyAV suelta el candado de Python mientras decodifica y
codifica, y QPainter sobre QImage funciona en cualquier hilo. Un proceso por
segmento tendría que volver a importar Qt y el proyecto entero.

Dos detalles que no son opcionales:

- los segmentos se cortan en **cuadros exactos**, o al pegar sobraría o
  faltaría medio cuadro en cada unión;
- se codifican **sin cuadros B**. Con cuadros B las marcas de decodificación
  de un segmento empiezan antes que las de presentación, y al pegarlo
  detrás del anterior quedarían yendo hacia atrás: el contenedor lo rechaza.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterator

from vortex_studio.media.encoder import Cancelled, _AudioWriter, export_video

try:
    import av

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

SEGMENT_OPTIONS = {"bf": "0"}


def default_workers() -> int:
    """La mitad de los núcleos, de 2 a 6: deja aire para seguir editando."""
    return max(2, min(6, (os.cpu_count() or 2) // 2))


def frame_ranges(start: float, end: float, fps: float, parts: int) -> list[tuple[float, float]]:
    """Tramos contiguos que empiezan y terminan en cuadros exactos."""
    total = max(1, int(round((end - start) * fps)))
    partes = max(1, min(parts, total))
    cortes = [round(total * i / partes) for i in range(partes + 1)]
    return [(start + a / fps, start + b / fps) for a, b in zip(cortes, cortes[1:]) if b > a]


def concat(segments: list[Path], path: Path, audio: Iterator | None = None,
           audio_rate: int = 48000, audio_layout: str = "stereo") -> Path:
    """Pega los segmentos copiando paquetes, y codifica el audio al parejo."""
    salida = av.open(str(path), mode="w")
    try:
        with av.open(str(segments[0])) as primero:
            flujo = salida.add_stream_from_template(primero.streams.video[0])
        sonido = _AudioWriter(salida, audio, audio_rate, audio_layout) if audio else None

        corrimiento = 0              # en la base de tiempo del flujo de entrada
        segundos = 0.0
        for segmento in segments:
            with av.open(str(segmento)) as entrada:
                origen = entrada.streams.video[0]
                base = origen.time_base
                fin = corrimiento
                for paquete in entrada.demux(origen):
                    if paquete.dts is None:
                        continue
                    paquete.pts += corrimiento
                    paquete.dts += corrimiento
                    fin = max(fin, paquete.pts + (paquete.duration or 0))
                    paquete.stream = flujo
                    salida.mux(paquete)
                segundos = float((fin) * base)
                corrimiento = fin
            if sonido is not None:
                sonido.advance(segundos)
        if sonido is not None:
            sonido.finish()
    finally:
        salida.close()
    return path


def render_segments(make_renderer: Callable, path: str | Path, start: float, end: float,
                    size: tuple[int, int], fps: float, quality: str = "Normal",
                    audio: Iterator | None = None, workers: int | None = None,
                    progress: Callable[[int, int], bool] | None = None) -> Path:
    """Exporta `[start, end)` en paralelo. `make_renderer()` da un armador de cuadros nuevo.

    `progress(hechos, total)` se llama desde los hilos y puede devolver False
    para cancelar todo. Si algo falla o se cancela, no queda ningún archivo
    a medias: ni los segmentos ni la salida.
    """
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado: no se puede exportar")
    ruta = Path(path)
    tramos = frame_ranges(start, end, fps, workers or default_workers())
    total = sum(max(1, int(round((b - a) * fps))) for a, b in tramos)
    carpeta = Path(tempfile.mkdtemp(prefix="vortex-segmentos-"))
    archivos = [carpeta / f"segmento-{i:03d}.mp4" for i in range(len(tramos))]
    hechos = [0] * len(tramos)
    candado = threading.Lock()
    detener = threading.Event()
    errores: list[BaseException] = []

    def trabajar(indice: int, desde: float, hasta: float) -> None:
        armador = make_renderer()
        cuadros = max(1, int(round((hasta - desde) * fps)))

        def avance(hecho: int, _total: int) -> bool:
            with candado:
                hechos[indice] = hecho
                seguir = progress(sum(hechos), total) if progress is not None else True
            if seguir is False:
                detener.set()
            return not detener.is_set()

        try:
            export_video(archivos[indice], armador.frames(desde, hasta, fps, size), cuadros,
                         size[0], size[1], fps, quality, avance, options=SEGMENT_OPTIONS)
        except Cancelled:
            detener.set()
        except BaseException as error:       # el disco, el códec…
            errores.append(error)
            detener.set()
        finally:
            armador.close()

    hilos = [threading.Thread(target=trabajar, args=(i, a, b), name=f"vortex-segmento-{i}",
                              daemon=True) for i, (a, b) in enumerate(tramos)]
    try:
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        if errores:
            raise errores[0]
        if detener.is_set():
            raise Cancelled()
        concat(archivos, ruta, audio)
    except BaseException:
        ruta.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    return ruta
