"""The audio must not clip.

Clipping is what "choppy" sounds like. It is entirely predictable from the
filter chain, so it belongs here rather than in anyone's ears: the source noise
has a known RMS, the chain has a computable gain, and the product either fits
inside full scale or it does not.

Every setting was clipping before these tests existed -- including plain white
noise, and violet noise by a factor of twenty.
"""

from __future__ import annotations

import numpy as np
import pytest

from waterfall.domain.constants import (
    BAND_GAIN_MAX_DB,
    BAND_WIDTH_MAX_OCT,
    BAND_WIDTH_MIN_OCT,
    DB_PER_OCTAVE_UNIT,
    DEFAULT_SAMPLE_RATE_HZ,
    FREQ_MIN_HZ,
    LEVEL_MIN_DB,
    NOISE_CREST_FACTOR,
    SLOPE_MAX_DB_PER_OCT,
    SOURCE_NOISE_RMS,
)
from scipy.signal import sosfilt

from waterfall.domain.filters import (
    _biquad_coefficients,
    chain_rms_gain,
    filter_chain,
    output_gain,
    response_db,
)
from waterfall.domain.spectrum import SpectrumParams

UNIT = DB_PER_OCTAVE_UNIT


SETTLE_SAMPLES = 4800
"""Discarded from the front: the filters start from rest and ring in."""


def render(params: SpectrumParams, seconds: float = 3.0) -> np.ndarray:
    """Actually run noise through the chain and return the output samples.

    Renders rather than predicts. An earlier version of this file estimated the
    peak as rms x crest factor -- but the output gain *divides* by that same
    crest factor, so the estimate was algebraically pinned to 1.0 and the
    assertion could never fail. Filtering real noise is the only way the test
    can disagree with the code.
    """
    sections = []
    for spec in filter_chain(params):
        b, a = _biquad_coefficients(spec, DEFAULT_SAMPLE_RATE_HZ)
        sections.append(np.concatenate([b / a[0], a / a[0]]))

    generator = np.random.default_rng(0x5EED)
    count = int(DEFAULT_SAMPLE_RATE_HZ * seconds)
    noise = generator.uniform(-1.0, 1.0, count)
    filtered = sosfilt(np.array(sections), noise)
    return np.asarray(filtered[SETTLE_SAMPLES:] * output_gain(params), dtype=np.float64)


def rendered_peak(params: SpectrumParams) -> float:
    """Loudest sample as a fraction of full scale. Above 1.0 the output clips."""
    return float(np.abs(render(params)).max())


def measured_rms_gain(params: SpectrumParams) -> float:
    """A second, denser integration, so the test is not just restating the code.

    Same hybrid grid shape -- a uniform linear grid cannot resolve a steep
    low-frequency tilt and disagrees by whatever resolution it happens to have.
    """
    nyquist = DEFAULT_SAMPLE_RATE_HZ / 2.0
    grid = np.unique(
        np.concatenate(
            [
                np.logspace(np.log10(0.5), np.log10(1000.0), 4000),
                np.linspace(1000.0, nyquist, 4000),
            ]
        )
    )
    amplitude = 10.0 ** (response_db(filter_chain(params), grid) / 20.0)
    return float(np.sqrt(np.trapezoid(amplitude**2, grid) / (nyquist - 0.5)))


# --- The headline: nothing clips ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("white", SpectrumParams()),
        ("pink", SpectrumParams(slope_db_per_oct=-UNIT)),
        ("brown", SpectrumParams(slope_db_per_oct=-2 * UNIT)),
        ("azure", SpectrumParams(slope_db_per_oct=UNIT)),
        ("violet", SpectrumParams(slope_db_per_oct=2 * UNIT)),
        # The configuration reported as choppy.
        (
            "brown + 12 dB band at 1 kHz",
            SpectrumParams(-2 * UNIT, 12.0, 1000.0, 0.30, 0.0),
        ),
        ("green noise", SpectrumParams(0.0, 12.0, 500.0, 1.0, 0.0)),
        ("narrow band, full gain", SpectrumParams(0.0, 12.0, 8000.0, 0.05, 0.0)),
        ("violet + band", SpectrumParams(2 * UNIT, 12.0, 60.0, 2.0, 0.0)),
    ],
)
def test_named_configurations_do_not_clip(name: str, params: SpectrumParams) -> None:
    peak = rendered_peak(params)
    assert peak <= 1.0, f"{name} clips: peak reaches {peak:.2f} of full scale"
    assert peak > 0.05, f"{name} is nearly silent at {peak:.3f} - overpaid headroom"


def test_nothing_in_the_whole_parameter_space_clips() -> None:
    """Swept rather than spot-checked, because the worst case is not obvious.

    The reported problem was a slope and a band together; either alone was
    milder. Only the product of the two shows it.
    """
    worst = 0.0
    offender = None
    # Coarser than it looks: each point renders three seconds of audio.
    for slope in np.linspace(-SLOPE_MAX_DB_PER_OCT, SLOPE_MAX_DB_PER_OCT, 5):
        for gain in (0.0, BAND_GAIN_MAX_DB):
            for centre in (25.0, 1000.0, 18000.0):
                for width in (BAND_WIDTH_MIN_OCT, 1.0, BAND_WIDTH_MAX_OCT):
                    params = SpectrumParams(float(slope), gain, centre, width, 0.0)
                    peak = rendered_peak(params)
                    if peak > worst:
                        worst, offender = peak, params
    assert worst <= 1.0, f"peak {worst:.2f} of full scale at {offender}"


def test_the_previous_design_would_fail_this() -> None:
    """Pins why the compensation exists, so it cannot be simplified away.

    The old output gain was simply 10^(L/20), ignoring the chain entirely.

    Plain white noise is left out on purpose: rendered, it peaks at exactly
    1.000 under the naive gain -- sitting on full scale rather than past it. It
    was marginal, not broken. Every configuration with any tilt or band was
    genuinely over.
    """
    for params in (
        SpectrumParams(slope_db_per_oct=2 * UNIT),
        SpectrumParams(slope_db_per_oct=-2 * UNIT),
        SpectrumParams(-2 * UNIT, 12.0, 1000.0, 0.30, 0.0),
    ):
        # What the old code produced: no compensation for the chain at all.
        naive_peak = rendered_peak(params) / output_gain(params) * 10.0 ** (
            params.level_db / 20.0
        )
        assert naive_peak > 1.0, "the naive gain should clip; compensation is needed"


# --- Loudness should not lurch between settings ------------------------------


def test_loudness_is_even_across_the_slope_range() -> None:
    """A slope change should recolour the sound, not change how loud it is.

    Before RMS compensation, violet noise came out about nine times louder than
    white -- which on its own makes the app unpleasant to sweep through.
    """
    levels = [
        SOURCE_NOISE_RMS
        * chain_rms_gain(float(slope), 0.0, 1000.0, 0.3)
        * output_gain(SpectrumParams(slope_db_per_oct=float(slope)))
        for slope in np.linspace(-SLOPE_MAX_DB_PER_OCT, SLOPE_MAX_DB_PER_OCT, 13)
    ]
    assert max(levels) / min(levels) < 1.05


def test_loudness_is_even_across_the_band_range() -> None:
    levels = [
        SOURCE_NOISE_RMS
        * chain_rms_gain(0.0, gain, 1000.0, 0.5)
        * output_gain(SpectrumParams(band_gain_db=gain, band_width_oct=0.5))
        for gain in (0.0, 3.0, 6.0, 9.0, BAND_GAIN_MAX_DB)
    ]
    assert max(levels) / min(levels) < 1.05


# --- The level control still works -------------------------------------------


def test_level_still_scales_the_output() -> None:
    """Compensation must not swallow the one control that means volume."""
    loud = output_gain(SpectrumParams(slope_db_per_oct=-2 * UNIT, level_db=0.0))
    quiet = output_gain(SpectrumParams(slope_db_per_oct=-2 * UNIT, level_db=-20.0))
    assert quiet == pytest.approx(loud / 10.0, rel=1e-9)

    assert output_gain(SpectrumParams(level_db=LEVEL_MIN_DB)) < output_gain(
        SpectrumParams(level_db=0.0)
    )


def test_gain_is_finite_and_positive_everywhere() -> None:
    for slope in np.linspace(-SLOPE_MAX_DB_PER_OCT, SLOPE_MAX_DB_PER_OCT, 7):
        for gain in (0.0, BAND_GAIN_MAX_DB):
            for width in (BAND_WIDTH_MIN_OCT, BAND_WIDTH_MAX_OCT):
                value = output_gain(
                    SpectrumParams(float(slope), gain, 1000.0, width, 0.0)
                )
                assert np.isfinite(value) and value > 0.0


def test_chain_rms_gain_matches_an_independent_integration() -> None:
    for params in (
        SpectrumParams(),
        SpectrumParams(slope_db_per_oct=-2 * UNIT),
        SpectrumParams(2 * UNIT, 12.0, 500.0, 0.4, 0.0),
    ):
        cached = chain_rms_gain(
            params.slope_db_per_oct,
            params.band_gain_db,
            params.band_center_hz,
            params.band_width_oct,
        )
        assert cached == pytest.approx(measured_rms_gain(params), rel=0.002)
