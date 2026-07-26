"""Step 2: audio frequency to light wavelength.

Visible light spans ~0.98 octaves; audible sound spans ~10. There is no
physically inevitable mapping between them, so this one is chosen: compress the
audible decade log-linearly onto 750-380 nm. Documented in docs/color-mapping.md.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.cie1931_data import WAVELENGTHS_NM
from waterfall.domain.constants import (
    FREQ_MIN_HZ,
    SUBSAMPLES_PER_WAVELENGTH_BIN,
    OCTAVE_SPAN,
    WAVELENGTH_RED_NM,
    WAVELENGTH_SPAN_NM,
)


def wavelength_for_frequency(
    frequencies: NDArray[np.float64],
) -> NDArray[np.float64]:
    """20 Hz -> 750 nm (red), 20 kHz -> 380 nm (violet)."""
    position = (np.log2(frequencies) - np.log2(FREQ_MIN_HZ)) / OCTAVE_SPAN
    return np.asarray(WAVELENGTH_RED_NM - WAVELENGTH_SPAN_NM * position, dtype=np.float64)


def frequency_for_wavelength(
    wavelengths_nm: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Inverse of `wavelength_for_frequency`. Single-valued, so no octave folding."""
    position = (WAVELENGTH_RED_NM - wavelengths_nm) / WAVELENGTH_SPAN_NM
    return np.asarray(
        2.0 ** (np.log2(FREQ_MIN_HZ) + OCTAVE_SPAN * position), dtype=np.float64
    )


CANONICAL_FREQUENCIES: NDArray[np.float64] = frequency_for_wavelength(WAVELENGTHS_NM)
"""The audio frequencies that the CMF wavelength samples correspond to.

Because wavelength is affine in log-frequency, uniform 1 nm steps land on
uniform log-frequency steps -- so this single grid is simultaneously the right
sampling for the CIE integral and for the spectral descriptors. Evaluating S(f)
here once is what makes "the color and the sound come from the same array"
literally true rather than merely intended.
"""

_BIN_OFFSETS_NM: NDArray[np.float64] = (
    np.arange(SUBSAMPLES_PER_WAVELENGTH_BIN, dtype=np.float64) + 0.5
) / SUBSAMPLES_PER_WAVELENGTH_BIN - 0.5

CANONICAL_SUBSAMPLES: NDArray[np.float64] = frequency_for_wavelength(
    WAVELENGTHS_NM[:, np.newaxis] + _BIN_OFFSETS_NM[np.newaxis, :]
)
"""Shape (wavelengths, subsamples): the frequencies spanning each 1 nm bin.

Averaging S(f) across a row integrates the spectrum over that bin rather than
point-sampling its center, which matters for bands sharp enough to vary inside
one bin. See SUBSAMPLES_PER_WAVELENGTH_BIN for the measured error this removes.
"""
