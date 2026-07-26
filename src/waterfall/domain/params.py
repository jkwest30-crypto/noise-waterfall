"""The five controls.

Separated from spectrum.py so the filter design can import them without a cycle:
filters -> params, spectrum -> filters.
"""

from __future__ import annotations

from dataclasses import dataclass

from waterfall.domain.constants import (
    BAND_GAIN_MAX_DB,
    BAND_GAIN_MIN_DB,
    BAND_WIDTH_DEFAULT_OCT,
    BAND_WIDTH_MAX_OCT,
    BAND_WIDTH_MIN_OCT,
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    FREQ_REF_HZ,
    LEVEL_MAX_DB,
    LEVEL_MIN_DB,
    SLOPE_MAX_DB_PER_OCT,
    SLOPE_MIN_DB_PER_OCT,
)


@dataclass(frozen=True)
class SpectrumParams:
    """Every one of these changes both the sound and the color.

    That is invariant 3, and it is what makes the app's premise true rather than
    aspirational: nothing here is decorative, and nothing is silent.
    """

    slope_db_per_oct: float = 0.0
    band_gain_db: float = 0.0
    band_center_hz: float = FREQ_REF_HZ
    band_width_oct: float = BAND_WIDTH_DEFAULT_OCT
    level_db: float = 0.0

    def __post_init__(self) -> None:
        self._require("slope_db_per_oct", SLOPE_MIN_DB_PER_OCT, SLOPE_MAX_DB_PER_OCT)
        self._require("band_gain_db", BAND_GAIN_MIN_DB, BAND_GAIN_MAX_DB)
        self._require("band_center_hz", FREQ_MIN_HZ, FREQ_MAX_HZ)
        self._require("band_width_oct", BAND_WIDTH_MIN_OCT, BAND_WIDTH_MAX_OCT)
        self._require("level_db", LEVEL_MIN_DB, LEVEL_MAX_DB)

    def _require(self, field: str, low: float, high: float) -> None:
        value = float(getattr(self, field))
        if not low <= value <= high:
            raise ValueError(f"{field}={value} outside [{low}, {high}]")

    @property
    def is_white_noise(self) -> bool:
        """White noise is the natural origin of the model, not a special case."""
        return self.slope_db_per_oct == 0.0 and self.band_gain_db == 0.0
