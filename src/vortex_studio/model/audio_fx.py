"""Efectos de audio de un clip: ecualizador de tres bandas y compresor.

Python puro: aquí solo se guardan los valores. Quien los aplica es
`media/audio.py`, con los filtros `bass`, `equalizer`, `treble` y
`acompressor` de FFmpeg.

Tres bandas y no un paramétrico de ocho, porque con graves, medios y agudos
se arregla lo que de verdad pasa: una voz con retumbe, un micrófono chillón,
una música que se come la voz. Y un compresor con sus cinco perillas de
siempre, apagado hasta que se prende.
"""

from __future__ import annotations

from dataclasses import dataclass

EQ_RANGE = (-12.0, 12.0)        # dB
# Esquinas de las repisas, no el centro de la banda: una repisa da la mitad
# de su ganancia justo en su frecuencia. Con la esquina de graves en 100 Hz,
# subir 9 dB solo subía 4.5 un bombo de 100 Hz. En 250 Hz y 4 kHz, "graves"
# y "agudos" mueven la banda que la gente espera.
LOW_HZ, MID_HZ, HIGH_HZ = 250, 1000, 4000

ROLES = ("Normal", "Voz", "Música: se agacha bajo la voz")
NORMAL, VOICE, DUCKED = ROLES

LOUDNESS_TARGETS = {
    "Redes (−14 LUFS)": -14.0,
    "Podcast (−16 LUFS)": -16.0,
    "Televisión (−23 LUFS)": -23.0,
}


@dataclass
class AudioFx:
    low: float = 0.0            # dB, repisa bajo 250 Hz
    mid: float = 0.0            # dB, campana en 1 kHz
    high: float = 0.0           # dB, repisa sobre 4 kHz

    compressor: bool = False
    threshold: float = -18.0    # dB
    ratio: float = 3.0
    attack: float = 10.0        # ms
    release: float = 150.0      # ms
    makeup: float = 0.0         # dB

    @property
    def eq_is_flat(self) -> bool:
        return all(abs(v) < 0.05 for v in (self.low, self.mid, self.high))

    @property
    def is_neutral(self) -> bool:
        return self.eq_is_flat and not self.compressor

    def copy(self) -> "AudioFx":
        return AudioFx(self.low, self.mid, self.high, self.compressor, self.threshold,
                       self.ratio, self.attack, self.release, self.makeup)
