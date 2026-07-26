"""Step 8: standard spectral descriptors that drive the water's motion.

Both are established MIR descriptors, and both are defined for *any* spectrum --
unlike a "center frequency", which is meaningless for a pure power law with no
band. That is the reason they are used here instead of the raw slider values.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.constants import (
    DESCRIPTOR_EPSILON,
    FREQ_MIN_HZ,
    OCTAVE_SPAN,
)


def spectral_centroid(
    spectrum: NDArray[np.float64], frequencies: NDArray[np.float64]
) -> float:
    """Center of mass in log-frequency, normalized to 0..1 across the audible range.

    0.071 for brown noise, exactly 0.5 for white, 0.929 for violet.
    """
    total = float(spectrum.sum())
    if total <= 0.0:
        return 0.5
    centroid_log2 = float((spectrum * np.log2(frequencies)).sum() / total)
    position = (centroid_log2 - np.log2(FREQ_MIN_HZ)) / OCTAVE_SPAN
    return float(np.clip(position, 0.0, 1.0))


def spectral_flatness(spectrum: NDArray[np.float64]) -> float:
    """Wiener entropy: geometric mean over arithmetic mean.

    Exactly 1.0 for a perfectly flat spectrum, falling toward 0 as energy
    concentrates. Measures how evenly power is spread, which is why it makes a
    good turbulence driver: evenly spread energy gives chaotic broadband water,
    concentrated energy gives coherent sheets.
    """
    floored = np.maximum(spectrum, DESCRIPTOR_EPSILON)
    arithmetic = float(floored.mean())
    if arithmetic <= 0.0:
        return 0.0
    geometric = float(np.exp(np.log(floored).mean()))
    return float(np.clip(geometric / arithmetic, 0.0, 1.0))
