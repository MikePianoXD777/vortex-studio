"""Lo que se sabe de cada archivo importado, sondeado una sola vez.

Abrir un contenedor para leer su duración, su resolución y sus códecs cuesta
poco con un archivo, pero se repite: al importar, al ajustar el formato de
la secuencia, al abrir el proyecto otra vez. Con material en un disco lento
o en red, cada sondeo es un acceso al archivo.

Aquí se guarda el resultado dentro del proyecto, con el tamaño y la fecha
del archivo. Mientras esos dos no cambien, el sondeo guardado vale; si
cambian —alguien reemplazó el video con otro del mismo nombre— se vuelve a
sondear. Comparar tamaño y fecha es lo mismo que hace `make` para saber si
algo cambió, y no obliga a leer el archivo completo.

Python puro: quien sondea de verdad se inyecta, así que la lógica del caché
se prueba sin tocar un solo video.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

VIDEO = "video"
AUDIO = "audio"
IMAGE = "imagen"


@dataclass
class MediaInfo:
    """Metadatos de un archivo de medios."""

    path: Path
    kind: str = VIDEO           # "video" | "audio" | "imagen"
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    channels: int = 0
    sample_rate: int = 0
    size: int = 0               # bytes, para saber si el archivo cambió
    mtime: float = 0.0          # fecha de modificación, ídem

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    @property
    def has_audio(self) -> bool:
        return self.channels > 0

    @property
    def has_video(self) -> bool:
        return self.kind in (VIDEO, IMAGE)

    def matches(self, size: int, mtime: float) -> bool:
        return self.size == size and abs(self.mtime - mtime) < 1e-6


def library_key(path: str | Path) -> str:
    """La clave con la que se guarda un archivo: su ruta absoluta.

    Absoluta y con barras normales, para que el mismo archivo pedido por dos
    caminos distintos —relativo y absoluto— no se sondee dos veces.
    """
    return Path(path).expanduser().resolve().as_posix()


def lookup(library: dict[str, MediaInfo], path: str | Path,
           prober: Callable[[Path], MediaInfo]) -> MediaInfo:
    """El sondeo del archivo, del caché si sigue vigente.

    Si el archivo desapareció se devuelve lo último que se supo de él: un
    proyecto con material desconectado tiene que poder abrirse y mostrar
    sus clips, aunque no se puedan reproducir.
    """
    path = Path(path)
    key = library_key(path)
    cached = library.get(key)

    try:
        stat = path.stat()
    except OSError:
        if cached is not None:
            return cached
        raise

    if cached is not None and cached.matches(stat.st_size, stat.st_mtime):
        return cached

    info = prober(path)
    info.path = Path(key)
    info.size, info.mtime = stat.st_size, stat.st_mtime
    library[key] = info
    return info
