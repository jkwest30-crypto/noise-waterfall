"""The filter chain, and therefore the spectrum.

The chain is the source of truth. `S(f)` is defined as the realized magnitude
response of these filters, so the color and the sound are not two things kept in
sync -- they are one thing viewed twice. The browser builds the same nodes from
the same coefficients, and invariant 6 checks it implements RBJ the way we do.

An earlier design went the other way: define an ideal spectrum, then hope a
filter cascade reproduced it. Invariant 6 measured errors up to 7.8 dB and a
factor-of-2 decibel-scale mismatch, which is what prompted the inversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.constants import (
    AMPLITUDE_DB_SCALE,
    DECIBEL_BASE,
    DEFAULT_SAMPLE_RATE_HZ,
    EQ_BAND_BASE_HZ,
    EQ_BAND_COUNT,
    FIT_CACHE_SIZE,
    FIT_GRID_POINTS,
    FIT_HIGH_HZ,
    FIT_ITERATIONS,
    FIT_LOW_HZ,
    FREQ_MIN_HZ,
    FREQ_REF_HZ,
    NOISE_CREST_FACTOR,
    RMS_GRID_SPLIT_HZ,
    RMS_INTEGRATION_MIN_HZ,
    RMS_INTEGRATION_POINTS,
    SOURCE_NOISE_RMS,
)
from waterfall.domain.params import SpectrumParams

FilterKind = Literal["lowshelf", "peaking"]


@dataclass(frozen=True)
class BiquadSpec:
    """One Web Audio `BiquadFilterNode`."""

    kind: FilterKind
    frequency_hz: float
    gain_db: float
    q: float


def q_for_octaves(width_oct: float) -> float:
    """Standard bandwidth-to-Q conversion: Q = sqrt(2^B) / (2^B - 1)."""
    ratio = 2.0**width_oct
    return float(np.sqrt(ratio) / (ratio - 1.0))


def shelf_centers() -> NDArray[np.float64]:
    return np.array(
        [EQ_BAND_BASE_HZ * 2.0**index for index in range(EQ_BAND_COUNT)],
        dtype=np.float64,
    )


def _biquad_coefficients(
    spec: BiquadSpec, sample_rate: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """RBJ cookbook coefficients -- the same formulas Web Audio uses."""
    amplitude = DECIBEL_BASE ** (spec.gain_db / (2.0 * AMPLITUDE_DB_SCALE))
    omega = 2.0 * np.pi * spec.frequency_hz / sample_rate
    cos_w = np.cos(omega)
    sin_w = np.sin(omega)

    if spec.kind == "lowshelf":
        alpha = sin_w / 2.0 * np.sqrt(2.0)
        shared = 2.0 * np.sqrt(amplitude) * alpha
        b = np.array(
            [
                amplitude * ((amplitude + 1) - (amplitude - 1) * cos_w + shared),
                2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cos_w),
                amplitude * ((amplitude + 1) - (amplitude - 1) * cos_w - shared),
            ]
        )
        a = np.array(
            [
                (amplitude + 1) + (amplitude - 1) * cos_w + shared,
                -2 * ((amplitude - 1) + (amplitude + 1) * cos_w),
                (amplitude + 1) + (amplitude - 1) * cos_w - shared,
            ]
        )
    else:
        alpha = sin_w / (2.0 * spec.q)
        b = np.array([1 + alpha * amplitude, -2 * cos_w, 1 - alpha * amplitude])
        a = np.array([1 + alpha / amplitude, -2 * cos_w, 1 - alpha / amplitude])
    return b, a


def response_db(
    specs: tuple[BiquadSpec, ...],
    frequencies: NDArray[np.float64],
    sample_rate: float = DEFAULT_SAMPLE_RATE_HZ,
) -> NDArray[np.float64]:
    """Cascaded magnitude response in dB. Cascading multiplies, so dB adds."""
    total = np.zeros_like(frequencies, dtype=np.float64)
    z = np.exp(-1j * 2.0 * np.pi * frequencies / sample_rate)
    for spec in specs:
        b, a = _biquad_coefficients(spec, sample_rate)
        transfer = (b[0] + b[1] * z + b[2] * z**2) / (a[0] + a[1] * z + a[2] * z**2)
        total = total + AMPLITUDE_DB_SCALE * np.log10(np.abs(transfer))
    return total


def _shelves(gains: tuple[float, ...]) -> tuple[BiquadSpec, ...]:
    return tuple(
        BiquadSpec(kind="lowshelf", frequency_hz=float(center), gain_db=gain, q=1.0)
        for center, gain in zip(shelf_centers(), gains, strict=True)
    )


@lru_cache(maxsize=FIT_CACHE_SIZE)
def fit_shelf_gains(
    slope_db_per_oct: float, sample_rate: float = DEFAULT_SAMPLE_RATE_HZ
) -> tuple[float, ...]:
    """Solve for the shelf gains that actually produce the requested slope.

    Cached because the smoother calls this every frame while a slider is moving,
    and the least-squares solve would otherwise repeat 60 times a second for
    values that mostly repeat.
    """
    if slope_db_per_oct == 0.0:
        # Exactly flat, with no fitting residue: white noise must land on a
        # perfectly flat spectrum or the default color is not exactly #FFFFFF.
        return tuple(0.0 for _ in range(EQ_BAND_COUNT))

    grid = np.logspace(
        np.log2(FIT_LOW_HZ), np.log2(FIT_HIGH_HZ), FIT_GRID_POINTS, base=2.0
    )
    target = slope_db_per_oct * np.log2(grid / FREQ_REF_HZ)

    unit = np.column_stack(
        [
            response_db(
                (BiquadSpec("lowshelf", float(center), 1.0, 1.0),), grid, sample_rate
            )
            for center in shelf_centers()
        ]
    )

    gains, *_ = np.linalg.lstsq(unit, target, rcond=None)
    for _ in range(FIT_ITERATIONS):
        realized = response_db(_shelves(tuple(gains)), grid, sample_rate)
        correction, *_ = np.linalg.lstsq(unit, target - realized, rcond=None)
        gains = gains + correction
    return tuple(float(g) for g in gains)


def filter_chain(
    params: SpectrumParams, sample_rate: float = DEFAULT_SAMPLE_RATE_HZ
) -> tuple[BiquadSpec, ...]:
    """EQ_BAND_COUNT shelves for the slope, plus one peaking band.

    The peaking band is present even at 0 dB, where it is transparent, so the
    node count never changes -- the browser builds its graph once and only ramps
    parameters. Adding or removing a node mid-playback would click.
    """
    return (
        *_shelves(fit_shelf_gains(params.slope_db_per_oct, sample_rate)),
        BiquadSpec(
            kind="peaking",
            frequency_hz=params.band_center_hz,
            gain_db=params.band_gain_db,
            q=q_for_octaves(params.band_width_oct),
        ),
    )


@lru_cache(maxsize=FIT_CACHE_SIZE)
def chain_rms_gain(
    slope_db_per_oct: float,
    band_gain_db: float,
    band_center_hz: float,
    band_width_oct: float,
    sample_rate: float = DEFAULT_SAMPLE_RATE_HZ,
) -> float:
    """How much the filter chain multiplies the RMS of white noise.

    White noise carries equal power per Hz, so this is an integral over linear
    frequency -- but the grid is logarithmic at the bottom and linear at the top,
    because neither spacing resolves the whole range on its own. See
    RMS_GRID_SPLIT_HZ for what goes wrong with either alone.

    Keyed on the filter parameters rather than the whole SpectrumParams so that
    moving the level slider, which does not change the chain, keeps hitting the
    cache.
    """
    params = SpectrumParams(
        slope_db_per_oct=slope_db_per_oct,
        band_gain_db=band_gain_db,
        band_center_hz=band_center_hz,
        band_width_oct=band_width_oct,
    )
    nyquist = sample_rate / 2.0
    half = RMS_INTEGRATION_POINTS // 2
    grid = np.unique(
        np.concatenate(
            [
                np.logspace(
                    np.log10(RMS_INTEGRATION_MIN_HZ),
                    np.log10(RMS_GRID_SPLIT_HZ),
                    half,
                ),
                np.linspace(RMS_GRID_SPLIT_HZ, nyquist, half),
            ]
        )
    )
    amplitude = DECIBEL_BASE ** (
        response_db(filter_chain(params, sample_rate), grid, sample_rate)
        / AMPLITUDE_DB_SCALE
    )
    power = float(np.trapezoid(amplitude**2, grid) / (nyquist - RMS_INTEGRATION_MIN_HZ))
    return float(np.sqrt(power))


def output_gain(
    params: SpectrumParams, sample_rate: float = DEFAULT_SAMPLE_RATE_HZ
) -> float:
    """Playback gain, scaled so the filtered noise fits inside full scale.

    Without dividing by the chain's own gain the output clips: a -6 dB/oct tilt
    lifts the bottom of the spectrum by 30 dB, and even a flat chain clips
    because the source already runs at full amplitude. Every setting was
    clipping before this existed, which is what made the sound choppy.

    Normalising by RMS rather than by peak response also evens out loudness
    across the slope range -- violet noise used to be about nine times louder
    than white.
    """
    requested = DECIBEL_BASE ** (params.level_db / AMPLITUDE_DB_SCALE)
    rms_gain = chain_rms_gain(
        params.slope_db_per_oct,
        params.band_gain_db,
        params.band_center_hz,
        params.band_width_oct,
        sample_rate,
    )
    headroom = SOURCE_NOISE_RMS * NOISE_CREST_FACTOR * rms_gain
    return float(requested / headroom)
