"""Steps 3-6: spectral power distribution to an sRGB color."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.cie1931_data import CMF
from waterfall.domain.constants import (
    D65_WHITE_XYZ,
    SRGB_8BIT_MAX,
    SRGB_GAMMA_EXPONENT,
    SRGB_GAMMA_OFFSET,
    SRGB_GAMMA_SCALE,
    SRGB_LINEAR_SLOPE,
    SRGB_LINEAR_THRESHOLD,
    XYZ_TO_LINEAR_SRGB,
)

ILLUMINANT_E_XYZ: NDArray[np.float64] = CMF.sum(axis=0)
"""Tristimulus of a perfectly flat spectrum -- the equal-energy illuminant."""


def xyz_from_spectral_weights(weights: NDArray[np.float64]) -> NDArray[np.float64]:
    """Step 4: integrate P(lambda) against the colour matching functions."""
    return np.asarray(weights @ CMF, dtype=np.float64)


def adapt_to_illuminant_e(xyz: NDArray[np.float64]) -> NDArray[np.float64]:
    """Step 5: divide out the equal-energy white point.

    This is what makes a flat spectrum land on exactly #FFFFFF. Under a plain
    D65 white point an equal-energy spectrum renders slightly warm, because
    D65 is bluer than E. Without this line white noise would not be white, and
    that result is the whole premise of the app -- so it looks like a bug only
    if you don't know why it's here.
    """
    return np.asarray(xyz / ILLUMINANT_E_XYZ, dtype=np.float64)


def gamma_encode(linear: NDArray[np.float64]) -> NDArray[np.float64]:
    """sRGB transfer function."""
    clipped = np.clip(linear, 0.0, 1.0)
    return np.asarray(
        np.where(
            clipped <= SRGB_LINEAR_THRESHOLD,
            clipped * SRGB_LINEAR_SLOPE,
            SRGB_GAMMA_SCALE * clipped**SRGB_GAMMA_EXPONENT - SRGB_GAMMA_OFFSET,
        ),
        dtype=np.float64,
    )


def linear_srgb_from_spectral_weights(
    weights: NDArray[np.float64], luminance: float
) -> tuple[float, float, float]:
    """Steps 4-6 up to but excluding gamma encoding.

    Linear light is where the physics lives, so this is the representation to
    assert chromaticity against. Gamma encoding is nonlinear and does not
    preserve channel *ratios*, so comparing hex triplets across two luminances
    shows a hue shift that is not really there -- the emitted light has
    identical chromaticity. Tests check hue here, not on the encoded output.
    """
    adapted = adapt_to_illuminant_e(xyz_from_spectral_weights(weights))

    # Normalize by luminance, not by chroma, so the result is a pure
    # chromaticity that `luminance` then scales. A uniform scale of linear RGB
    # cannot change chromaticity, which is what makes hue provably invariant
    # under level.
    if adapted[1] <= 0.0:
        return (0.0, 0.0, 0.0)
    chromatic = adapted / adapted[1] * D65_WHITE_XYZ

    linear = XYZ_TO_LINEAR_SRGB @ chromatic

    # Lift out-of-gamut channels rather than clamping them. Spectral colors sit
    # outside sRGB and produce negative linear values; clamping to zero inflates
    # saturation and shifts hue, while adding the deficit to all three
    # desaturates toward white, which is the correct rendering intent. With
    # clamping, nearly every input reads fully saturated and the
    # white-noise-is-desaturated result is destroyed.
    deficit = float(linear.min())
    if deficit < 0.0:
        linear = linear - deficit

    peak = float(linear.max())
    if peak <= 0.0:
        return (0.0, 0.0, 0.0)

    # Peak-normalize before applying luminance, so the luminance scale is a
    # uniform multiple of a fixed chromaticity vector. That is what makes hue
    # exactly invariant under level rather than approximately so.
    scaled = linear / peak * luminance
    return (float(scaled[0]), float(scaled[1]), float(scaled[2]))


def srgb_from_spectral_weights(
    weights: NDArray[np.float64], luminance: float
) -> tuple[float, float, float]:
    """Steps 4-6 end to end. Returns gamma-encoded sRGB in 0..1."""
    linear = np.array(
        linear_srgb_from_spectral_weights(weights, luminance), dtype=np.float64
    )
    encoded = gamma_encode(linear)
    return (float(encoded[0]), float(encoded[1]), float(encoded[2]))


def saturation(rgb: tuple[float, float, float]) -> float:
    """Chroma as a 0..1 fraction. Exactly 0 for any neutral gray."""
    peak = max(rgb)
    if peak <= 0.0:
        return 0.0
    return float(1.0 - min(rgb) / peak)


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(np.clip(c, 0.0, 1.0) * SRGB_8BIT_MAX):02X}" for c in rgb)
