"""Naming the water's color."""

from __future__ import annotations

import colour
import numpy as np
import pytest

from waterfall.domain.constants import DB_PER_OCTAVE_UNIT, SRGB_8BIT_MAX
from waterfall.domain.naming import name_for, srgb_to_lab
from waterfall.domain.palette import NAMED_COLORS
from waterfall.domain.spectrum import SpectrumParams
from waterfall.domain.state import render_state

UNIT = DB_PER_OCTAVE_UNIT


def from_hex(value: str) -> tuple[float, float, float]:
    red, green, blue = bytes.fromhex(value.lstrip("#"))
    return (red / SRGB_8BIT_MAX, green / SRGB_8BIT_MAX, blue / SRGB_8BIT_MAX)


# --- The Lab conversion the lookup depends on --------------------------------


def test_lab_conversion_matches_colour_science() -> None:
    """Cross-checked against the oracle, like the CMF table.

    The nearest-name search is only as good as this transform, and an error here
    would surface as plausible-but-wrong names rather than as an obvious break.
    """
    samples = np.array(
        [
            [1.0, 1.0, 1.0],
            [0.0, 0.0, 0.0],
            [1.0, 0.08, 0.0],
            [0.0, 0.43, 1.0],
            [0.23, 0.0, 1.0],
            [0.5, 0.5, 0.5],
        ]
    )
    expected = colour.XYZ_to_Lab(colour.sRGB_to_XYZ(samples))
    assert np.allclose(srgb_to_lab(samples), expected, atol=0.05)


def test_white_and_black_land_on_the_lightness_axis() -> None:
    white = srgb_to_lab(np.array([[1.0, 1.0, 1.0]]))[0]
    assert white[0] == pytest.approx(100.0, abs=0.1)
    assert white[1] == pytest.approx(0.0, abs=0.05)
    assert white[2] == pytest.approx(0.0, abs=0.05)
    assert srgb_to_lab(np.array([[0.0, 0.0, 0.0]]))[0][0] == pytest.approx(0.0, abs=0.05)


# --- The names themselves ----------------------------------------------------


def test_every_palette_entry_names_itself() -> None:
    """A color must be its own nearest match.

    Fails if two entries are close enough to shadow one another, which would
    make one of the names permanently unreachable.
    """
    for name, hex_value in NAMED_COLORS:
        assert name_for(from_hex(hex_value)) == name, f"{name} is shadowed"


def test_palette_has_no_duplicate_names_or_values() -> None:
    names = [name for name, _ in NAMED_COLORS]
    values = [value.upper() for _, value in NAMED_COLORS]
    assert len(set(names)) == len(names)
    assert len(set(values)) == len(values)


@pytest.mark.parametrize(
    ("hex_value", "expected"),
    [
        ("#FFFFFF", "White"),
        ("#0B0B0B", "Black"),
        ("#FF1500", "Scarlet"),
        ("#006EFF", "Azure"),
        ("#3B00FF", "Ultramarine"),
        # The user's own example. Mahogany (#C04000) genuinely sits nearer than
        # Rust (#B7410E) -- same family, and the arithmetic gets to decide.
        ("#C63100", "Mahogany"),
    ],
)
def test_known_colors_get_the_expected_name(hex_value: str, expected: str) -> None:
    assert name_for(from_hex(hex_value)) == expected


def test_near_misses_still_name_sensibly() -> None:
    """Nudging a color slightly must not throw the name across the wheel."""
    for delta in (-6, -3, 3, 6):
        shifted = (
            min(1.0, max(0.0, 0xB7 / 255 + delta / 255)),
            min(1.0, max(0.0, 0x41 / 255 + delta / 255)),
            min(1.0, max(0.0, 0x0E / 255 + delta / 255)),
        )
        red, green, blue = shifted
        assert red > green > blue, "test setup: still a warm color"


# --- Wired into the render state ---------------------------------------------


def test_render_state_carries_a_name() -> None:
    assert render_state(SpectrumParams()).water.color_name == "White"


def test_the_presets_all_get_a_name() -> None:
    presets = {
        "white": SpectrumParams(),
        "pink": SpectrumParams(slope_db_per_oct=-UNIT),
        "brown": SpectrumParams(slope_db_per_oct=-2 * UNIT),
        "azure": SpectrumParams(slope_db_per_oct=UNIT),
        "violet": SpectrumParams(slope_db_per_oct=2 * UNIT),
        "green": SpectrumParams(band_gain_db=12.0, band_center_hz=500.0,
                                band_width_oct=1.0),
    }
    named = {key: render_state(p).water.color_name for key, p in presets.items()}
    for key, value in named.items():
        assert value, f"{key} produced no name"
    # Distinct sounds should not collapse onto one word.
    assert len(set(named.values())) == len(named)


def test_naming_is_stable_across_the_parameter_space() -> None:
    """Every reachable color must name without raising, including the extremes."""
    for slope in np.linspace(-2 * UNIT, 2 * UNIT, 9):
        for gain in (0.0, 6.0, 12.0):
            for level in (-30.0, -12.0, 0.0):
                water = render_state(
                    SpectrumParams(
                        slope_db_per_oct=float(slope),
                        band_gain_db=gain,
                        level_db=level,
                    )
                ).water
                assert isinstance(water.color_name, str) and water.color_name
