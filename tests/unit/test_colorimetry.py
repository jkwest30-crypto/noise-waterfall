"""Colorimetry: the noise-color family, and the results the app rests on."""

from __future__ import annotations

import colour
import numpy as np
import pytest
from numpy.typing import NDArray

from waterfall.domain.cie1931_data import CMF, WAVELENGTHS_NM
from waterfall.domain.colorimetry import (
    ILLUMINANT_E_XYZ,
    linear_srgb_from_spectral_weights,
    saturation,
    srgb_from_spectral_weights,
    to_hex,
)
from waterfall.domain.constants import DB_PER_OCTAVE_UNIT
from waterfall.domain.spectrum import SpectrumParams
from waterfall.domain.state import render_state

UNIT = DB_PER_OCTAVE_UNIT  # 3.0103 dB/oct, one slope unit


def delta_e(hex_a: str, hex_b: str) -> float:
    """Perceptual distance between two hex colors. Under ~2 is imperceptible."""

    def to_lab(value: str) -> NDArray[np.float64]:
        rgb = np.array(
            [int(value[i : i + 2], 16) / 255.0 for i in (1, 3, 5)], dtype=np.float64
        )
        return np.asarray(colour.XYZ_to_Lab(colour.sRGB_to_XYZ(rgb)), dtype=np.float64)

    return float(colour.difference.delta_E(to_lab(hex_a), to_lab(hex_b), method="CIE 2000"))


def color_of(params: SpectrumParams) -> tuple[float, float, float]:
    return render_state(params).water.color


# --- The headline result -----------------------------------------------------


def test_white_noise_is_exactly_white() -> None:
    """The app's entire premise, and it must be exact rather than close.

    Achieved by the Illuminant E adaptation in step 5. Under a plain D65 white
    point a flat spectrum renders slightly warm.
    """
    water = render_state(SpectrumParams()).water
    assert to_hex(water.color) == "#FFFFFF"

    # Not bit-exact zero: the vendored CMF table is stored to 9 decimals, so the
    # integral carries ~1e-8 of residue. That is roughly 1e5 times finer than
    # 8-bit quantization (1/255), hence the exact #FFFFFF above. The tolerance
    # documents the precision floor rather than papering over a real tint.
    assert saturation(water.color) == pytest.approx(0.0, abs=1e-6)


def test_flat_spectrum_has_equal_energy_chromaticity() -> None:
    """Illuminant E sits at x = y = 1/3 by definition."""
    total = float(ILLUMINANT_E_XYZ.sum())
    assert ILLUMINANT_E_XYZ[0] / total == pytest.approx(1 / 3, abs=5e-4)
    assert ILLUMINANT_E_XYZ[1] / total == pytest.approx(1 / 3, abs=5e-4)


@pytest.mark.parametrize(
    ("name", "slope", "expected_hex"),
    [
        ("violet", 2 * UNIT, "#3B00FF"),
        ("azure", 1 * UNIT, "#006EFF"),
        ("white", 0.0, "#FFFFFF"),
        ("red", -2 * UNIT, "#FF1500"),
    ],
)
def test_noise_family_reproduces_its_own_names(
    name: str, slope: float, expected_hex: str
) -> None:
    """The colors of noise are defined by PSD slope, and they render as named.

    These names were coined by analogy to light a century ago; the colorimetry
    reproduces them independently. That agreement is the strongest available
    evidence the mapping is principled rather than invented.
    """
    rendered = to_hex(color_of(SpectrumParams(slope_db_per_oct=slope)))
    assert delta_e(rendered, expected_hex) < 2.0, f"{name}: {rendered} != {expected_hex}"


def test_pink_noise_renders_orange_because_pink_is_non_spectral() -> None:
    """Documented disagreement, asserted so it cannot drift unnoticed.

    Pink is red plus blue with green suppressed -- it is not a spectral color,
    so no monotonic power law can produce it. A -3.01 dB/oct tilt integrates to
    orange. The audio world's "pink" was always a loose analogy, and the app
    says so rather than bending the math to hit the name.
    """
    rendered = to_hex(color_of(SpectrumParams(slope_db_per_oct=-UNIT)))
    assert delta_e(rendered, "#FF7406") < 2.0
    red, green, blue = color_of(SpectrumParams(slope_db_per_oct=-UNIT))
    assert red > green > blue, "orange, not pink"


def test_green_noise_renders_yellow_not_green() -> None:
    """The other documented disagreement.

    Sleep apps define green noise as mid-band around 500 Hz. Under this mapping
    500 Hz lands at 578 nm, which is yellow; green needs roughly 1 kHz.
    """
    green_noise = SpectrumParams(band_gain_db=12.0, band_center_hz=500.0, band_width_oct=1.0)
    rendered = to_hex(color_of(green_noise))
    assert delta_e(rendered, "#FFDF5A") < 2.0

    # ... and 1 kHz is where green actually lives.
    at_1k = SpectrumParams(band_gain_db=12.0, band_center_hz=1000.0, band_width_oct=0.5)
    red, green, blue = color_of(at_1k)
    assert green > red and green > blue


# --- Level and hue -----------------------------------------------------------


def test_hue_is_exactly_invariant_under_level() -> None:
    """Amplitude changes brightness and never hue.

    Checked in *linear* light, which is where chromaticity physically lives.
    Gamma encoding is nonlinear and does not preserve channel ratios, so the
    same test run on hex triplets reports a hue shift that is not real.
    """
    reference: NDArray[np.float64] | None = None
    for level in (0.0, -6.0, -12.0, -20.0, -30.0):
        params = SpectrumParams(slope_db_per_oct=-2 * UNIT, level_db=level)
        linear = np.array(
            linear_srgb_from_spectral_weights(
                _weights(params), 10.0 ** (level / 20.0)
            ),
            dtype=np.float64,
        )
        normalized = linear / linear.sum()
        if reference is None:
            reference = normalized
        else:
            assert np.allclose(normalized, reference, atol=1e-12), (
                f"chromaticity drifted at {level} dB"
            )


def test_lower_level_is_strictly_dimmer() -> None:
    previous = None
    for level in (0.0, -6.0, -12.0, -20.0, -30.0):
        color = color_of(SpectrumParams(slope_db_per_oct=-2 * UNIT, level_db=level))
        brightness = max(color)
        if previous is not None:
            assert brightness < previous
        previous = brightness


# --- Spectral sanity ---------------------------------------------------------


def _weights(params: SpectrumParams) -> NDArray[np.float64]:
    from waterfall.domain.mapping import CANONICAL_FREQUENCIES
    from waterfall.domain.spectrum import power_spectrum

    return power_spectrum(params, CANONICAL_FREQUENCIES)


def _monochromatic(wavelength_nm: float) -> NDArray[np.float64]:
    return np.exp(-0.5 * ((WAVELENGTHS_NM - wavelength_nm) / 4.0) ** 2)


@pytest.mark.parametrize(
    ("wavelength", "dominant"),
    [(450.0, "blue"), (550.0, "green"), (700.0, "red")],
)
def test_monochromatic_light_renders_its_own_color(
    wavelength: float, dominant: str
) -> None:
    red, green, blue = srgb_from_spectral_weights(_monochromatic(wavelength), 1.0)
    channels = {"red": red, "green": green, "blue": blue}
    assert max(channels, key=lambda k: channels[k]) == dominant


def test_vendored_cmf_matches_colour_science() -> None:
    """Pins the vendored table to the oracle it was generated from.

    colour-science is a dev dependency only; the domain layer ships this data
    so it can depend on numpy alone (invariant 1). This test is what keeps the
    copy honest.
    """
    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    expected = np.array([cmfs[float(nm)] for nm in WAVELENGTHS_NM], dtype=np.float64)
    assert np.allclose(CMF, expected, atol=1e-9)
