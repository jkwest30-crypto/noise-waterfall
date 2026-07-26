"""Gradual parameter easing.

The app is meant to glide rather than jump: you move a slider and the sound and
the color drift to the new value together. Easing the *parameters* rather than
the resulting color is what keeps the two in step, since both are derived from
the eased parameters downstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from waterfall.domain.spectrum import SpectrumParams

DEFAULT_RATE = 0.045
"""Fraction of the remaining distance covered per frame.

At 60 fps this reaches ~93% of a step in one second, which reads as gradual
without feeling unresponsive.
"""

CONVERGENCE_EPSILON = 1e-6


@dataclass
class ParameterSmoother:
    """Exponential ease toward a moving target.

    Exponential rather than linear so the approach decelerates: there is no
    moment where the color arrives and visibly stops.
    """

    current: SpectrumParams
    rate: float = DEFAULT_RATE

    def __post_init__(self) -> None:
        if not 0.0 < self.rate <= 1.0:
            raise ValueError(f"rate={self.rate} must be in (0, 1]")

    def step(self, target: SpectrumParams) -> SpectrumParams:
        self.current = replace(
            self.current,
            slope_db_per_oct=_ease(
                self.current.slope_db_per_oct, target.slope_db_per_oct, self.rate
            ),
            band_gain_db=_ease(
                self.current.band_gain_db, target.band_gain_db, self.rate
            ),
            # Eased in log space: sweeping 100 Hz -> 200 Hz should feel like the
            # same distance as 1 kHz -> 2 kHz, because it is one octave either
            # way. Linear easing would crawl at the bottom and lurch at the top.
            band_center_hz=2.0
            ** _ease(
                math.log2(self.current.band_center_hz),
                math.log2(target.band_center_hz),
                self.rate,
            ),
            band_width_oct=_ease(
                self.current.band_width_oct, target.band_width_oct, self.rate
            ),
            level_db=_ease(self.current.level_db, target.level_db, self.rate),
        )
        return self.current

    def has_converged(self, target: SpectrumParams) -> bool:
        return all(
            abs(getattr(self.current, field) - getattr(target, field))
            < CONVERGENCE_EPSILON
            for field in (
                "slope_db_per_oct",
                "band_gain_db",
                "band_width_oct",
                "level_db",
            )
        )


def _ease(current: float, target: float, rate: float) -> float:
    return current + (target - current) * rate
