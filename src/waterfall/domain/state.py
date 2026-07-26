"""Assembles everything the browser needs from a single evaluation of S(f).

This module is where the app's central guarantee lives: `power_spectrum` is
called exactly once, and both the color and the audio parameters are derived
from that one array. They cannot disagree, because they are the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from waterfall.domain.filters import BiquadSpec, filter_chain, output_gain
from waterfall.domain.colorimetry import srgb_from_spectral_weights
from waterfall.domain.constants import LEVEL_MIN_DB, LEVEL_SPAN_DB
from waterfall.domain.descriptors import spectral_centroid, spectral_flatness
from waterfall.domain.mapping import CANONICAL_FREQUENCIES, CANONICAL_SUBSAMPLES
from waterfall.domain.naming import name_for
from waterfall.domain.spectrum import SpectrumParams, amplitude, power_spectrum


@dataclass(frozen=True)
class WaterState:
    """What the renderer needs. Every field moves only when the sound moves."""

    color: tuple[float, float, float]
    color_name: str
    flow: float
    turbulence: float
    fall_speed: float


@dataclass(frozen=True)
class AudioParams:
    bands: tuple[BiquadSpec, ...]
    output_gain: float


@dataclass(frozen=True)
class RenderState:
    water: WaterState
    audio: AudioParams


def render_state(params: SpectrumParams) -> RenderState:
    # One evaluation. Everything below is derived from it.
    # Averaging across each 1 nm bin integrates S(f) over the bin instead of
    # point-sampling its center, which is what keeps narrow bands from being
    # under-counted at the resolution limit of the wavelength grid.
    spectrum = power_spectrum(params, CANONICAL_SUBSAMPLES).mean(axis=1)

    # CANONICAL_FREQUENCIES is f(lambda) for each CMF wavelength sample, so this
    # array is already P(lambda) = S(f(lambda)) aligned row-for-row with the
    # colour matching functions. Step 3 needs no resampling.
    color = srgb_from_spectral_weights(spectrum, amplitude(params))

    return RenderState(
        water=WaterState(
            color=color,
            color_name=name_for(color),
            flow=(params.level_db - LEVEL_MIN_DB) / LEVEL_SPAN_DB,
            turbulence=spectral_flatness(spectrum),
            fall_speed=spectral_centroid(spectrum, CANONICAL_FREQUENCIES),
        ),
        audio=AudioParams(
            bands=filter_chain(params),
            output_gain=output_gain(params),
        ),
    )
