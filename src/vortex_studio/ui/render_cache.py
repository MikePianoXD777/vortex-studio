"""Caché de render por zonas: renderizar lo pesado una vez y reproducirlo liso.

Una zona roja —color, LUT, llave, capa de ajuste, anidada, varias capas— se
compone cuadro por cuadro en cada reproducción. Renderizarla la escribe a un
archivo en la caché, con todo quemado, y a partir de ahí el preview la lee
como si fuera un video más: un solo cuadro que decodificar.

El nombre del archivo es la **firma** de la zona (`model/render_zones.py`).
Si algo de la zona cambia, la firma cambia, el archivo ya no corresponde a
nada y la zona vuelve a rojo sola: la caché nunca muestra algo viejo.

El archivo es H.264 casi sin pérdida (CRF 12) con un keyframe cada 15
cuadros, para que saltar dentro de la zona sea tan barato como en un proxy.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from vortex_studio.media.encoder import Cancelled, image_to_frame
from vortex_studio.media.waveform import cache_dir as _waves_dir

try:
    import av
except ImportError:  # pragma: no cover - depende del entorno
    av = None


def render_dir() -> Path:
    return _waves_dir().parent / "render"


def cached_file(signature: str) -> Path:
    return render_dir() / f"{signature}.mp4"


def is_cached(signature: str) -> bool:
    return cached_file(signature).exists()


def clear_cache() -> int:
    carpeta = render_dir()
    if not carpeta.exists():
        return 0
    cuantos = len(list(carpeta.glob("*.mp4")))
    shutil.rmtree(carpeta, ignore_errors=True)
    return cuantos


def render_zone(renderer, zone, fps: float, width: int, height: int,
                cancel: threading.Event | None = None) -> Path:
    """Escribe la zona a su archivo de caché. Temporal primero, luego renombra."""
    destino = cached_file(zone.signature)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.stem + f".{os.getpid()}.parte.mp4")
    ancho, alto = width - width % 2, height - height % 2
    cuadros = max(1, int(round(zone.duration * fps)))
    try:
        with av.open(str(temporal), mode="w") as salida:
            flujo = salida.add_stream("libx264", rate=round(fps))
            flujo.width, flujo.height, flujo.pix_fmt = ancho, alto, "yuv420p"
            flujo.options = {"crf": "12", "preset": "veryfast", "g": "15", "bf": "0"}
            for indice in range(cuadros):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                imagen = renderer.compose(zone.start + indice / fps, ancho, alto)
                for paquete in flujo.encode(image_to_frame(imagen, ancho, alto)):
                    salida.mux(paquete)
            for paquete in flujo.encode():
                salida.mux(paquete)
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return destino


class RenderCacheWorker(QObject):
    """Renderiza zonas en su hilo, una tras otra, con su copia de la secuencia."""

    zone_ready = Signal(str)            # firma
    finished = Signal(int)              # cuántas quedaron
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._busy = False

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def start(self, sequence_data: dict, nested: dict, media: dict, zones: list) -> bool:
        if self.busy or not zones:
            return False
        with self._lock:
            self._busy = True
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(sequence_data, nested, media, zones),
                                        name="vortex-cache-render", daemon=True)
        self._thread.start()
        return True

    def wait(self, timeout: float = 120.0) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
        return not self.busy

    def cancel(self) -> None:
        self._cancel.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout)

    def _emit(self, signal, *args) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            pass        # la ventana se cerró

    def _run(self, sequence_data, nested, media, zones) -> None:
        from vortex_studio.model.serialize import sequence_from_dict
        from vortex_studio.ui.renderer import SequenceRenderer

        hechas = 0
        renderer = None
        try:
            secuencia = sequence_from_dict(sequence_data)
            hijas = {i: sequence_from_dict(d) for i, d in nested.items()}
            renderer = SequenceRenderer(secuencia, dict(media), resolve=hijas.get)
            for zona in zones:
                if self._cancel.is_set():
                    break
                if is_cached(zona.signature):
                    continue
                render_zone(renderer, zona, secuencia.fps, secuencia.width, secuencia.height,
                            self._cancel)
                hechas += 1
                self._emit(self.zone_ready, zona.signature)
        except Cancelled:
            pass
        except Exception as error:
            self._emit(self.failed, str(error) or type(error).__name__)
        finally:
            if renderer is not None:
                renderer.close()
            with self._lock:
                self._busy = False
            self._emit(self.finished, hechas)
