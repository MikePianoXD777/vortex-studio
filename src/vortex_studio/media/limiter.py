"""Limitador de picos para la salida de la mezcla.

Sumar pistas puede pasarse de 1.0, y ahí el audio se recorta: un chasquido
áspero en el play y en el archivo exportado. Antes la mezcla dejaba recortar
porque un limitador de los de siempre mira unos milisegundos hacia adelante,
y ese adelanto desfasaría el sonido de la imagen.

Este no mira hacia adelante, así que no retrasa ni una muestra:

- la envolvente sigue al pico **al instante** y baja despacio (`release`);
- la ganancia es `tope / envolvente` donde la envolvente pasa del tope, y 1
  donde no. Como la envolvente nunca es menor que la señal, la salida nunca
  pasa del tope;
- por debajo del tope no toca nada: la mezcla normal sale idéntica.

El precio de no mirar adelante es que el primer pico de un golpe se aplasta
de golpe en vez de con rampa. Para un seguro contra recortes —que es lo que
es esto, no un maximizador— se oye mucho mejor que recortar.
"""

from __future__ import annotations

import math

import numpy as np

CEILING_DB = -0.3
CEILING = 10 ** (CEILING_DB / 20)
RELEASE = 0.080         # segundos para que la ganancia regrese
_CHUNK = 4096           # para que r^-k no se desborde al vectorizar


class PeakLimiter:
    """Limitador estéreo enlazado: los dos canales bajan lo mismo."""

    def __init__(self, rate: int, ceiling: float = CEILING, release: float = RELEASE) -> None:
        self.ceiling = float(ceiling)
        self._log_r = -1.0 / (max(release, 1e-4) * rate)   # caída por muestra, en log
        self._env = 0.0
        self.reduction = 1.0    # la ganancia más baja que se aplicó en el último bloque

    def process(self, datos: np.ndarray) -> np.ndarray:
        """Limita un bloque `(canales, muestras)` en flotante. Guarda estado
        entre bloques: si no, cada bloque empezaría con la ganancia en 1 y el
        principio de cada segundo saldría recortado."""
        if datos.ndim != 2 or datos.shape[1] == 0:
            self.reduction = 1.0
            return datos
        if not np.isfinite(datos).all():
            # Un NaN o un infinito —un WAV flotante dañado— entraba a la
            # envolvente y ya no salía: todo lo que seguía en el play o en la
            # exportación salía NaN (en `s16`, corriente directa a todo
            # volumen) o mudo. Sin limitador era un chasquido de una muestra;
            # aquí se queda en eso. `nan_to_num` da una copia, así que quien
            # llama sabe que hay que rearmar el cuadro.
            datos = np.nan_to_num(datos, nan=0.0, posinf=self.ceiling, neginf=-self.ceiling)
        pico = np.max(np.abs(datos), axis=0).astype(np.float64)
        envolvente = self._envelope(pico)
        ganancia = np.minimum(1.0, self.ceiling / np.maximum(envolvente, 1e-12))
        self.reduction = float(ganancia.min())
        if self.reduction >= 1.0:
            return datos
        return (datos * ganancia[np.newaxis, :]).astype(datos.dtype, copy=False)

    def _envelope(self, pico: np.ndarray) -> np.ndarray:
        """`env[n] = max(pico[n], env[n-1] · r)`, sin un ciclo de Python.

        Es lo mismo que `r^n · max_{k≤n}(pico[k] · r^-k)`: un máximo
        acumulado, que NumPy hace en C. Por trozos, porque `r^-k` crece
        exponencial y en un bloque largo se desbordaría.
        """
        salida = np.empty_like(pico)
        previo = self._env
        for inicio in range(0, len(pico), _CHUNK):
            trozo = pico[inicio:inicio + _CHUNK]
            k = np.arange(len(trozo), dtype=np.float64)
            subida = np.exp(-k * self._log_r)          # r^-k
            bajada = np.exp(k * self._log_r)           # r^k
            env = np.maximum.accumulate(trozo * subida) * bajada
            env = np.maximum(env, previo * bajada * math.exp(self._log_r))
            salida[inicio:inicio + len(trozo)] = env
            previo = float(env[-1])
        # Segundo seguro: un estado que no es un número no se recupera nunca,
        # porque cada bloque arrastra el anterior.
        self._env = previo if math.isfinite(previo) else 0.0
        return salida
