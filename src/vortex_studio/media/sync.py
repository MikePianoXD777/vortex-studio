"""Sincronizar cámaras: por el audio o por el código de tiempo.

**Por audio**, como PluralEyes o el Sincronizar de Premiere: las cámaras
grabaron el mismo sonido, así que la correlación cruzada de sus audios
tiene un pico en el desfase. Se decodifica a 4 kHz mono —de sobra para
encontrar el pico y ocho veces menos datos que 48 kHz— y se correlaciona
con FFT, que con dos minutos de audio son milisegundos.

La correlación se hace sobre la **envolvente blanqueada**: la señal con su
espectro aplanado (fase sola, como en la estabilización). Sin eso, un
zumbido grave común a las dos grabaciones —un aire acondicionado— daba un
pico ancho y el desfase salía corrido.

**Por código de tiempo**: si las cámaras traen timecode en sus metadatos,
el desfase es la resta. Es exacto, pero solo si los relojes de las cámaras
estaban sincronizados, que en grabaciones caseras casi nunca.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import av
    from av.audio.resampler import AudioResampler

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

RATE = 4000


def load_audio(path: str | Path, seconds: float | None = None) -> np.ndarray:
    """El audio del archivo en mono a 4 kHz, en float32. Vacío si no trae audio."""
    if not HAS_PYAV:
        return np.zeros(0, np.float32)
    try:
        contenedor = av.open(str(path))
    except Exception:
        return np.zeros(0, np.float32)
    try:
        if not contenedor.streams.audio:
            return np.zeros(0, np.float32)
        flujo = contenedor.streams.audio[0]
        resampler = AudioResampler(format="flt", layout="mono", rate=RATE)
        trozos, total = [], 0
        limite = int(seconds * RATE) if seconds else None
        for frame in contenedor.decode(flujo):
            for chunk in resampler.resample(frame):
                datos = chunk.to_ndarray().reshape(-1)[:chunk.samples]
                trozos.append(datos)
                total += len(datos)
            if limite is not None and total >= limite:
                break
        for chunk in resampler.resample(None):
            trozos.append(chunk.to_ndarray().reshape(-1)[:chunk.samples])
    except Exception:
        pass
    finally:
        contenedor.close()
    if not trozos:
        return np.zeros(0, np.float32)
    salida = np.concatenate(trozos).astype(np.float32)
    return salida[:limite] if limite is not None else salida


def audio_offset(reference: str | Path, other: str | Path,
                 max_seconds: float = 180.0) -> tuple[float, float]:
    """`(desfase, confianza)`: dónde empieza `other` respecto de `reference`, en segundos.

    Positivo quiere decir que `other` empezó a grabar después: se pone ese
    tanto más adelante en la línea de tiempo. La confianza es qué tanto
    destaca el pico sobre el resto de la correlación; debajo de 5, el
    resultado es de dudar.
    """
    a = load_audio(reference, max_seconds)
    b = load_audio(other, max_seconds)
    if len(a) < RATE // 4 or len(b) < RATE // 4:
        return 0.0, 0.0
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    fa = np.fft.rfft(a - a.mean(), n)
    fb = np.fft.rfft(b - b.mean(), n)
    cruzado = fa * np.conj(fb)
    cruzado /= np.maximum(np.abs(cruzado), 1e-9)       # blanqueado: fase sola
    correlacion = np.fft.irfft(cruzado, n)
    pico = int(np.argmax(correlacion))
    desfase = pico if pico < n // 2 else pico - n
    ruido = float(np.std(correlacion)) or 1e-9
    return round(desfase / RATE, 4), float(correlacion[pico] / ruido)


def parse_timecode(texto: str, fps: float) -> float | None:
    """`HH:MM:SS:FF` —o con `;` de drop frame— a segundos."""
    try:
        partes = [int(p) for p in str(texto).replace(";", ":").split(":")]
    except ValueError:
        return None
    if len(partes) != 4 or fps <= 0:
        return None
    horas, minutos, segundos, cuadros = partes
    return horas * 3600 + minutos * 60 + segundos + cuadros / round(fps)


def timecode_seconds(path: str | Path) -> float | None:
    """El código de tiempo de inicio del archivo, en segundos, o None si no trae."""
    if not HAS_PYAV:
        return None
    try:
        with av.open(str(path)) as contenedor:
            fps = 30.0
            if contenedor.streams.video:
                fps = float(contenedor.streams.video[0].average_rate or 30)
            candidatos = [contenedor.metadata.get("timecode")]
            candidatos += [s.metadata.get("timecode") for s in contenedor.streams]
    except Exception:
        return None
    for texto in candidatos:
        if texto:
            segundos = parse_timecode(texto, fps)
            if segundos is not None:
                return segundos
    return None
