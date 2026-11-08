"""PROVISIONAL: ajustes que no hacen nada."""

from __future__ import annotations

import numpy as np

from vortex_studio.photo.document import Adjustments


def apply_adjustments(pixels: np.ndarray, adj: Adjustments, scale: float = 1.0) -> np.ndarray:
    return pixels


def auto_enhance(pixels: np.ndarray) -> Adjustments:
    return Adjustments(contrast=12, vibrance=15, shadows=10)
