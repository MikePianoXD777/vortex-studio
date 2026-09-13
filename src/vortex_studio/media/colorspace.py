"""Espacios de color de entrada: material HDR, logarítmico o de OCIO a Rec.709.

Un video HDR (Rec.2020 con PQ o HLG, el de los iPhone y las cámaras
nuevas) decodificado tal cual se ve lavado y gris: sus valores están pensados
para una pantalla de 1000 nits y se muestran en una de 100. Hay que
**convertirlo**: quitarle la curva de transferencia, pasar de los primarios
de Rec.2020 a los de Rec.709, **comprimir las luces** (tonemapping) y volver
a ponerle la curva de una pantalla normal.

El camino de siempre en FFmpeg es `zscale` + `tonemap`, y `zscale` no viene
en las ruedas de PyAV. En vez de eso, la conversión se **hornea a un LUT
3D** `.cube` de 33 puntos con NumPy, y se aplica con el mismo `lut3d` que ya
se usaba para los looks: una sola tabla por cuadro, en C.

Con **OCIO** (`opencolorio`, opcional) la tabla sale del procesador de OCIO
en vez de las fórmulas de aquí: cualquier espacio de su configuración —la de
estudio que trae incluida, o una propia— se puede usar como entrada. Sin
`opencolorio` instalado, esa opción simplemente no aparece.

Las tablas se guardan en la caché con una firma de lo que las define, como
todo lo demás.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

from vortex_studio.media.waveform import cache_dir as _waves_dir
from vortex_studio.model.color import SPACE_HLG, SPACE_OCIO, SPACE_PQ

LUT_SIZE = 33
VERSION = 1
REFERENCE_WHITE = 203.0      # nits del blanco de papel en HDR (BT.2408)
PEAK = 1000.0                # nits que se comprimen hasta el blanco de la pantalla
OCIO_DISPLAY = "Rec.1886 Rec.709 - Display"

BT2020_TO_709 = np.array([[1.6605, -0.5876, -0.0728],
                          [-0.1246, 1.1329, -0.0083],
                          [-0.0182, -0.1006, 1.1187]])


def has_ocio() -> bool:
    try:
        import PyOpenColorIO  # noqa: F401
    except ImportError:
        return False
    return True


# --- curvas -----------------------------------------------------------------------

def pq_to_nits(e: np.ndarray) -> np.ndarray:
    """SMPTE ST 2084: del valor codificado (0 a 1) a nits."""
    m1, m2 = 2610 / 16384, 2523 / 4096 * 128
    c1, c2, c3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
    p = np.power(np.clip(e, 0.0, 1.0), 1.0 / m2)
    return 10000.0 * np.power(np.maximum(p - c1, 0.0) / (c2 - c3 * p), 1.0 / m1)


def hlg_to_nits(rgb: np.ndarray, peak: float = PEAK) -> np.ndarray:
    """ARIB STD-B67: OETF inversa y OOTF de una pantalla de `peak` nits."""
    a = 0.17883277
    b = 1 - 4 * a
    c = 0.5 - a * np.log(4 * a)
    e = np.clip(rgb, 0.0, 1.0)
    escena = np.where(e <= 0.5, e * e / 3.0, (np.exp((e - c) / a) + b) / 12.0)
    luminancia = escena @ np.array([0.2627, 0.6780, 0.0593])
    ootf = np.power(np.maximum(luminancia, 1e-9), 1.2 - 1.0)
    return peak * escena * ootf[..., None]


def tonemap(nits: np.ndarray, peak: float = PEAK) -> np.ndarray:
    """Reinhard extendido sobre el canal más alto: el blanco de referencia queda en
    medios tonos altos, el pico en 1.0, y el matiz no se corre."""
    x = nits / REFERENCE_WHITE
    w = peak / REFERENCE_WHITE
    maximo = np.maximum(x.max(axis=-1, keepdims=True), 1e-9)
    comprimido = maximo * (1 + maximo / (w * w)) / (1 + maximo)
    return np.clip(x * (comprimido / maximo), 0.0, 1.0)


def bt709_oetf(lineal: np.ndarray) -> np.ndarray:
    lineal = np.clip(lineal, 0.0, 1.0)
    return np.where(lineal < 0.018, 4.5 * lineal, 1.099 * np.power(lineal, 0.45) - 0.099)


def lattice(size: int = LUT_SIZE) -> np.ndarray:
    """La rejilla de entrada: arreglo (azul, verde, rojo, 3) con valores RGB de 0 a 1."""
    v = np.linspace(0.0, 1.0, size)
    b, g, r = np.meshgrid(v, v, v, indexing="ij")
    return np.stack([r, g, b], axis=-1)


def convert(rgb: np.ndarray, space: str, ocio_config: str = "", ocio_space: str = "") -> np.ndarray:
    """Valores codificados en `space` a Rec.709 de pantalla normal, de 0 a 1."""
    if space == SPACE_OCIO:
        return _ocio(rgb, ocio_config, ocio_space)
    if space == SPACE_PQ:
        nits = pq_to_nits(rgb)
    elif space == SPACE_HLG:
        nits = hlg_to_nits(rgb)
    else:
        return np.clip(rgb, 0.0, 1.0)
    en_709 = np.maximum(nits @ BT2020_TO_709.T, 0.0)
    return bt709_oetf(tonemap(en_709))


def _config(ocio_config: str):
    import PyOpenColorIO as ocio

    if ocio_config:
        return ocio.Config.CreateFromFile(str(ocio_config))
    return ocio.Config.CreateFromBuiltinConfig("studio-config-latest")


def ocio_spaces(ocio_config: str = "") -> list[str]:
    """Los espacios de color de la configuración de OCIO, o [] sin OCIO."""
    if not has_ocio():
        return []
    try:
        return [c.getName() for c in _config(ocio_config).getColorSpaces()]
    except Exception:
        return []


def _ocio(rgb: np.ndarray, ocio_config: str, ocio_space: str) -> np.ndarray:
    if not has_ocio():
        raise RuntimeError("Para usar OCIO hace falta opencolorio:  pip install opencolorio")
    configuracion = _config(ocio_config)
    nombres = {c.getName() for c in configuracion.getColorSpaces()}
    destino = OCIO_DISPLAY if OCIO_DISPLAY in nombres else "sRGB - Display"
    procesador = configuracion.getProcessor(ocio_space, destino).getDefaultCPUProcessor()
    plano = np.ascontiguousarray(rgb.reshape(-1, 3).astype(np.float32))
    procesador.applyRGB(plano)
    return np.clip(plano.reshape(rgb.shape), 0.0, 1.0)


# --- el LUT horneado ----------------------------------------------------------------

def _firma(adjust) -> str:
    partes = [adjust.input_space, adjust.ocio_space, str(LUT_SIZE), str(VERSION)]
    if adjust.input_space == SPACE_OCIO and adjust.ocio_config:
        try:
            estado = Path(adjust.ocio_config).stat()
            partes += [str(Path(adjust.ocio_config).resolve()), str(estado.st_mtime_ns)]
        except OSError:
            partes.append(adjust.ocio_config)
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()


def input_lut(adjust) -> Path | None:
    """El `.cube` que convierte el espacio de entrada del ajuste, horneado si hace falta.

    None si el material es Rec.709 normal, o si la conversión no se puede
    hacer (OCIO sin instalar, espacio que no existe): mejor la imagen sin
    convertir que un cuadro en negro.
    """
    espacio = getattr(adjust, "input_space", "")
    if not espacio:
        return None
    destino = _waves_dir().parent / "luts" / f"{_firma(adjust)}.cube"
    if destino.exists():
        return destino
    try:
        tabla = convert(lattice(), espacio, adjust.ocio_config, adjust.ocio_space)
    except Exception:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [f'TITLE "Vortex Studio · {espacio} a Rec.709"', f"LUT_3D_SIZE {LUT_SIZE}"]
    lineas += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in tabla.reshape(-1, 3)]
    temporal = destino.with_name(destino.stem + f".{os.getpid()}.tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.replace(temporal, destino)
    return destino


TRANSFER_SPACES = {"smpte2084": SPACE_PQ, "arib-std-b67": SPACE_HLG}


def space_for_transfer(transfer: str) -> str:
    """El espacio de entrada que corresponde a la curva que dice el archivo, o ""."""
    return TRANSFER_SPACES.get(str(transfer or "").lower(), "")
