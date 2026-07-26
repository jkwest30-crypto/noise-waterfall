"""S(f): the power spectrum the listener actually hears.

Defined as the realized magnitude response of the filter chain, not as an ideal
curve the filters are asked to imitate. That inversion is what makes the color
and the sound the same object rather than two things kept in agreement.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.constants import (
    AMPLITUDE_DB_SCALE,
    DECIBEL_BASE,
    DEFAULT_SAMPLE_RATE_HZ,
    POWER_DB_SCALE,
)
from waterfall.domain.filters import filter_chain, response_db
from waterfall.domain.params import SpectrumParams

__all__ = ["SpectrumParams", "amplitude", "power_spectrum"]


def power_spectrum(
    params: SpectrumParams,
    frequencies: NDArray[np.float64],
    sample_rate: float = DEFAULT_SAMPLE_RATE_HZ,
) -> NDArray[np.float64]:
    """Power at each frequency, normalized so a flat chain gives exactly 1.

    Excludes the level term: level scales amplitude uniformly, so it belongs to
    luminance and output gain rather than to the spectrum's shape. Keeping it
    out is what makes hue provably invariant under level.

    A biquad's gain_db is an amplitude figure, but power = |H|^2 means its
    contribution in power-dB is also gain_db -- so the chain's dB response
    converts to a power ratio with the power scale, not the amplitude one.
    """
    chain = filter_chain(params, sample_rate)
    return np.asarray(
        DECIBEL_BASE ** (response_db(chain, frequencies, sample_rate) / POWER_DB_SCALE),
        dtype=np.float64,
    )


def amplitude(params: SpectrumParams) -> float:
    """Linear amplitude from level in dBFS. 0 dB is full scale."""
    return float(DECIBEL_BASE ** (params.level_db / AMPLITUDE_DB_SCALE))
