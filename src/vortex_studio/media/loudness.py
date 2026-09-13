"""Sonoridad integrada en LUFS, según ITU-R BS.1770-4.

Es el número que piden las plataformas: YouTube y TikTok normalizan a unos
−14 LUFS, un podcast va a −16, la tele a −23. Medir el pico no sirve para
esto: una voz comprimida y una música dinámica con el mismo pico se oyen
con volúmenes muy distintos.

La medición tiene tres pasos:

1. **Ponderación K**: dos filtros —un realce de agudos y un pasa-altas— que
   imitan cómo el oído pesa las frecuencias. Van con el filtro `biquad` de
   FFmpeg con los coeficientes exactos de la norma para 48 kHz, así que
   corren en C.
2. **Bloques de 400 ms** con 75 % de traslape; en cada uno, la energía
   media sumada de los canales. Eso es NumPy.
3. **Dos compuertas**: se tiran los bloques por debajo de −70 LUFS
   (silencio), y luego los que queden 10 LU por debajo del promedio. Así una
   pausa larga no baja el número.
"""

from __future__ import annotations

import math

import numpy as np

try:
    import av
    from av.audio.fifo import AudioFifo

    HAS_PYAV = True
except ImportError:  # pragma: no cover - depende del entorno
    av = None
    HAS_PYAV = False

RATE = 48000

# Coeficientes de BS.1770 a 48 kHz (a0 = 1).
_SHELF = (1.53512485958697, -2.69169618940638, 1.19839281085285,
          1.0, -1.69065929318241, 0.73248077421585)
_HIGHPASS = (1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621)


def _k_weighting_graph(layout: str = "stereo"):
    graph = av.filter.Graph()
    entrada = graph.add("abuffer", f"sample_rate={RATE}:sample_fmt=fltp"
                                   f":channel_layout={layout}:time_base=1/{RATE}")
    nodos = []
    for b0, b1, b2, a0, a1, a2 in (_SHELF, _HIGHPASS):
        nodos.append(graph.add("biquad", f"b0={b0}:b1={b1}:b2={b2}:a0={a0}:a1={a1}:a2={a2}"))
    nodos.append(graph.add("aformat", f"sample_fmts=fltp:channel_layouts={layout}"
                                      f":sample_rates={RATE}"))
    nodos.append(graph.add("abuffersink"))
    anterior = entrada
    for nodo in nodos:
        anterior.link_to(nodo)
        anterior = nodo
    graph.configure()
    return graph, entrada


def integrated(frames, layout: str = "stereo") -> float:
    """LUFS integrados de cuadros de audio `fltp` a 48 kHz. `-inf` si todo es silencio."""
    if not HAS_PYAV:
        raise RuntimeError("PyAV no está instalado")
    graph, entrada = _k_weighting_graph(layout)
    partes: list[np.ndarray] = []

    def jalar():
        while True:
            try:
                bloque = graph.pull()
            except (av.error.BlockingIOError, av.error.EOFError, EOFError):
                return
            partes.append(bloque.to_ndarray().astype(np.float64))

    for frame in frames:
        frame.pts = None
        entrada.push(frame)
        jalar()
    try:
        entrada.push(None)
    except Exception:
        pass
    jalar()
    if not partes:
        return float("-inf")
    return loudness_of(np.concatenate(partes, axis=1))


def loudness_of(weighted: np.ndarray) -> float:
    """Sonoridad de muestras ya ponderadas, `(canales, n)`."""
    bloque = int(0.4 * RATE)
    paso = bloque // 4
    n = weighted.shape[1]
    if n < bloque:
        return float("-inf")

    # Energía media por bloque con sumas acumuladas: sin bucles por muestra.
    cuadrados = weighted * weighted
    acumulado = np.concatenate([np.zeros((cuadrados.shape[0], 1)),
                                np.cumsum(cuadrados, axis=1)], axis=1)
    inicios = np.arange(0, n - bloque + 1, paso)
    energia = (acumulado[:, inicios + bloque] - acumulado[:, inicios]) / bloque
    z = energia.sum(axis=0)          # canales frontales: peso 1

    with np.errstate(divide="ignore"):
        por_bloque = -0.691 + 10 * np.log10(z)
    vivos = z[por_bloque > -70.0]
    if vivos.size == 0:
        return float("-inf")
    relativo = -0.691 + 10 * math.log10(vivos.mean()) - 10.0
    finales = vivos[(-0.691 + 10 * np.log10(vivos)) > relativo]
    if finales.size == 0:
        return float("-inf")
    return -0.691 + 10 * math.log10(finales.mean())


def gain_for(current: float, target: float, limit: float = 4.0) -> float:
    """El factor de volumen que lleva de `current` a `target` LUFS."""
    if not math.isfinite(current):
        return 1.0
    return max(0.0, min(limit, 10 ** ((target - current) / 20.0)))
