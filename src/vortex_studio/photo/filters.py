"""PROVISIONAL: filtros que no hacen nada (solo el catálogo)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from vortex_studio.photo.document import Adjustments, Filter


@dataclass
class FilterPreset:
    id: str
    name: str
    adjustments: Adjustments = field(default_factory=Adjustments)


_NOMBRES = [("vivido", "Vívido"), ("calido", "Cálido"), ("frio", "Frío"), ("bn", "Blanco y negro"),
            ("sepia", "Sepia"), ("desvanecido", "Desvanecido"), ("dramatico", "Dramático"),
            ("cine", "Cine"), ("vintage", "Vintage"), ("suave", "Suave")]
FILTERS: dict[str, FilterPreset] = {i: FilterPreset(i, n) for i, n in _NOMBRES}


def apply_filter(pixels: np.ndarray, flt: Filter, scale: float = 1.0) -> np.ndarray:
    return pixels


def auto_enhance(pixels: np.ndarray) -> Adjustments:
    return Adjustments(contrast=12, vibrance=15, shadows=10)
