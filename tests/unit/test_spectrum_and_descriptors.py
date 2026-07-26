"""Spectrum synthesis, spectral descriptors, and audio filter design."""

from __future__ import annotations

import numpy as np
import pytest

from waterfall.domain.filters import (
    BiquadSpec,
    filter_chain,
    fit_shelf_gains,
    output_gain,
    q_for_octaves,
    response_db,
    shelf_centers,
)
from waterfall.domain.constants import (
    BAND_GAIN_MAX_DB,
    DB_PER_OCTAVE_UNIT,
    EQ_BAND_BASE_HZ,
    EQ_BAND_COUNT,
    FIT_HIGH_HZ,
    FIT_LOW_HZ,
    FREQ_REF_HZ,
    LEVEL_MIN_DB,
    SLOPE_MAX_DB_PER_OCT,
)
from waterfall.domain.descriptors import spectral_centroid, spectral_flatness
from waterfall.domain.mapping import (
    CANONICAL_FREQUENCIES,
    frequency_for_wavelength,
    wavelength_for_frequency,
)
from waterfall.domain.spectrum import SpectrumParams, power_spectrum
from waterfall.domain.state import render_state

UNIT = DB_PER_OCTAVE_UNIT


def spectrum_for(params: SpectrumParams) -> np.ndarray:
    return power_spectrum(params, CANONICAL_FREQUENCIES)


# --- Spectrum synthesis ------------------------------------------------------


def test_white_noise_is_exactly_flat() -> None:
    """Not "approximately flat with a very wide band" -- exactly flat.

    White noise is the natural origin of the model (slope 0, band off) rather
    than a special-cased branch, which is what lets the default land on a clean
    #FFFFFF instead of a fraction of a percent off it.
    """
    values = spectrum_for(SpectrumParams())
    # 1e-12 rather than exactly 0: the response is evaluated through complex
    # arithmetic, which leaves ~1e-15 of float residue. Far below anything a
    # display or an ear can resolve, and the color still lands on #FFFFFF.
    assert np.allclose(values, values[0], rtol=0, atol=1e-12)


def test_slope_tilts_the_spectrum_by_the_stated_db_per_octave() -> None:
    """Approximate, not exact: a shelf cascade traces a power law rather than
    reproducing it. Worst case across the range is ~1.4 dB, and the color is
    computed from the realized response, so what you see matches what you hear
    even where the realization departs from the ideal."""
    for slope in (-2 * UNIT, -UNIT, UNIT, 2 * UNIT):
        values = power_spectrum(
            SpectrumParams(slope_db_per_oct=slope),
            np.array([FREQ_REF_HZ, 2 * FREQ_REF_HZ], dtype=np.float64),
        )
        measured_db = 10.0 * np.log10(values[1] / values[0])
        assert measured_db == pytest.approx(slope, abs=0.6)


def test_band_emphasis_peaks_at_its_center() -> None:
    params = SpectrumParams(band_gain_db=12.0, band_center_hz=1000.0, band_width_oct=0.3)
    values = spectrum_for(params)
    peak_hz = float(CANONICAL_FREQUENCIES[int(np.argmax(values))])
    assert peak_hz == pytest.approx(1000.0, rel=0.02)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slope_db_per_oct", 99.0),
        ("band_gain_db", -1.0),
        ("band_center_hz", 5.0),
        ("band_width_oct", 0.0),
        ("level_db", 6.0),
    ],
)
def test_out_of_range_parameters_are_rejected(field: str, value: float) -> None:
    """Level above 0 dBFS is rejected too: it would clip the audio."""
    with pytest.raises(ValueError):
        SpectrumParams(**{field: value})


def test_slope_range_covers_the_standard_family_exactly() -> None:
    """+/-6.0206 dB/oct, not a rounded 6.0, so violet and brown are reachable."""
    assert SLOPE_MAX_DB_PER_OCT == pytest.approx(2 * UNIT)
    SpectrumParams(slope_db_per_oct=2 * UNIT)  # must not raise


# --- Wavelength mapping ------------------------------------------------------


def test_wavelength_mapping_endpoints() -> None:
    assert wavelength_for_frequency(np.array([20.0]))[0] == pytest.approx(750.0)
    assert wavelength_for_frequency(np.array([20000.0]))[0] == pytest.approx(380.0)


@pytest.mark.parametrize(
    ("hz", "nm"),
    [(60.0, 691.2), (250.0, 614.7), (440.0, 584.4), (1000.0, 540.5), (4000.0, 466.2)],
)
def test_wavelength_mapping_golden_values(hz: float, nm: float) -> None:
    assert wavelength_for_frequency(np.array([hz]))[0] == pytest.approx(nm, abs=0.1)


def test_mapping_round_trips() -> None:
    assert np.allclose(
        frequency_for_wavelength(wavelength_for_frequency(CANONICAL_FREQUENCIES)),
        CANONICAL_FREQUENCIES,
    )


def test_canonical_grid_spans_the_audible_range() -> None:
    """The one grid serving both the CIE integral and the descriptors."""
    assert CANONICAL_FREQUENCIES.min() == pytest.approx(20.0)
    assert CANONICAL_FREQUENCIES.max() == pytest.approx(20000.0)


# --- Descriptors -------------------------------------------------------------


def test_flatness_is_exactly_one_for_white_noise() -> None:
    assert spectral_flatness(spectrum_for(SpectrumParams())) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("slope", "centroid", "flatness"),
    [
        (2 * UNIT, 0.908, 0.017),
        (1 * UNIT, 0.846, 0.232),
        (0.0, 0.500, 1.000),
        (-1 * UNIT, 0.143, 0.221),
        (-2 * UNIT, 0.071, 0.014),
    ],
)
def test_descriptor_golden_values(slope: float, centroid: float, flatness: float) -> None:
    values = spectrum_for(SpectrumParams(slope_db_per_oct=slope))
    assert spectral_centroid(values, CANONICAL_FREQUENCIES) == pytest.approx(
        centroid, abs=0.002
    )
    assert spectral_flatness(values) == pytest.approx(flatness, abs=0.002)


def test_centroid_rises_monotonically_with_slope() -> None:
    previous = None
    for slope in np.linspace(-2 * UNIT, 2 * UNIT, 9):
        value = spectral_centroid(
            spectrum_for(SpectrumParams(slope_db_per_oct=float(slope))),
            CANONICAL_FREQUENCIES,
        )
        if previous is not None:
            assert value > previous
        previous = value


def test_flatness_falls_monotonically_as_band_gain_rises() -> None:
    """Gain is the monotonic axis: more emphasis means more concentration."""
    previous = None
    for gain in (0.0, 3.0, 6.0, 9.0, 12.0):
        value = spectral_flatness(
            spectrum_for(SpectrumParams(band_gain_db=gain, band_width_oct=1.0))
        )
        if previous is not None:
            assert value < previous
        previous = value


def test_band_width_moves_the_color_across_its_whole_range() -> None:
    """Width must stay visually live everywhere, not just at one end.

    With a peaking filter the peak height is set by gain, so width acts on the
    skirts. This checks the effect survives across the range rather than
    collapsing once the band dominates -- which is what capped band gain at
    12 dB.
    """
    from waterfall.domain.colorimetry import to_hex
    from tests.unit.test_colorimetry import delta_e

    widths = (4.0, 2.0, 1.0, 0.5, 0.2, 0.05)
    colors = [
        to_hex(render_state(SpectrumParams(band_gain_db=9.0, band_width_oct=w)).water.color)
        for w in widths
    ]
    for narrower, wider in zip(colors, colors[1:]):
        assert delta_e(narrower, wider) > 0.5


# --- Filter design -----------------------------------------------------------


def test_q_matches_the_octave_bandwidth_formula() -> None:
    """Q = sqrt(2^B) / (2^B - 1). One octave gives the familiar 1.4142."""
    assert q_for_octaves(1.0) == pytest.approx(np.sqrt(2.0), abs=1e-9)
    assert q_for_octaves(2.0) == pytest.approx(2.0 / 3.0, abs=1e-9)


def test_fitted_chain_realizes_the_requested_slope() -> None:
    """The chain must trace the power law, not merely aim at it.

    Setting each band's gain to the local slope value is the obvious approach
    and it is wrong: octave-spaced filters overlap, so the skirts add and the
    cascade overshoots by up to 14 dB. These gains are solved for.
    """
    grid = np.logspace(np.log2(FIT_LOW_HZ), np.log2(FIT_HIGH_HZ), 200, base=2.0)
    for slope in (-2 * UNIT, -UNIT, UNIT, 2 * UNIT):
        chain = filter_chain(SpectrumParams(slope_db_per_oct=slope))
        target = slope * np.log2(grid / FREQ_REF_HZ)
        assert np.abs(response_db(chain, grid) - target).max() < 1.5


def test_naive_local_gains_would_fail_the_same_check() -> None:
    """Pins why the fit exists, so nobody simplifies it away.

    If this ever stops failing, the overlap problem has gone and the fit is
    genuinely unnecessary -- but it has not, and it is not.
    """
    slope = -2 * UNIT
    grid = np.logspace(np.log2(FIT_LOW_HZ), np.log2(FIT_HIGH_HZ), 200, base=2.0)
    naive = tuple(
        BiquadSpec("lowshelf", float(c), slope * np.log2(c / FREQ_REF_HZ), 1.0)
        for c in shelf_centers()
    )
    target = slope * np.log2(grid / FREQ_REF_HZ)
    assert np.abs(response_db(naive, grid) - target).max() > 5.0


def test_flat_slope_fits_exactly_zero() -> None:
    """White noise cannot carry fitting residue, or the default is not #FFFFFF."""
    assert fit_shelf_gains(0.0) == tuple(0.0 for _ in range(EQ_BAND_COUNT))
    grid = np.array([20.0, 1000.0, 20000.0])
    assert np.allclose(response_db(filter_chain(SpectrumParams()), grid), 0.0)


def test_chain_spans_the_audible_range() -> None:
    centers = shelf_centers()
    assert len(centers) == EQ_BAND_COUNT
    assert centers[0] == pytest.approx(EQ_BAND_BASE_HZ)
    assert centers[-1] > 20000.0


def test_emphasis_band_is_always_present_but_neutral_at_zero_gain() -> None:
    """Constant node count keeps the browser graph static.

    A peaking filter at 0 dB is transparent, so the band can be switched off
    without adding or removing a node -- which would click.
    """
    off = filter_chain(SpectrumParams(band_gain_db=0.0))
    on = filter_chain(SpectrumParams(band_gain_db=12.0))
    assert len(off) == len(on) == EQ_BAND_COUNT + 1
    assert off[-1].kind == "peaking"
    assert off[-1].gain_db == 0.0
    assert on[-1].gain_db == 12.0


def test_output_gain_leaves_headroom_for_the_filter_chain() -> None:
    """This used to assert the gain was exactly 1.0 at 0 dBFS.

    That was asserting the bug. A raw gain of 1.0 ignores the chain's own gain,
    and every setting clipped -- which is what made the sound choppy. The gain
    is now divided by the chain's RMS response, so full scale leaves room for
    the filters. tests/unit/test_headroom.py covers the property properly.
    """
    assert output_gain(SpectrumParams(level_db=0.0)) < 1.0
    assert output_gain(SpectrumParams(level_db=LEVEL_MIN_DB)) < output_gain(
        SpectrumParams(level_db=0.0)
    )


# --- Assembled state ---------------------------------------------------------


def test_all_water_fields_stay_in_unit_range() -> None:
    for slope in (-2 * UNIT, 0.0, 2 * UNIT):
        for gain in (0.0, BAND_GAIN_MAX_DB):
            for level in (LEVEL_MIN_DB, 0.0):
                water = render_state(
                    SpectrumParams(
                        slope_db_per_oct=slope, band_gain_db=gain, level_db=level
                    )
                ).water
                for name in ("flow", "turbulence", "fall_speed"):
                    value = getattr(water, name)
                    assert 0.0 <= value <= 1.0, f"{name}={value} out of range"
                assert all(0.0 <= c <= 1.0 for c in water.color)
