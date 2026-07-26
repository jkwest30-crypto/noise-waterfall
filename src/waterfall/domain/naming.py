"""Give the water's color a name.

"Rust" tells you more about a sound than "#B7410E" does. The nearest named
color is found in CIELAB rather than in RGB, because RGB distance does not
correspond to how different two colors look -- in RGB, a dark navy sits closer
to black than to blue.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from waterfall.domain.constants import (
    D65_WHITE_XYZ,
    LAB_A_SCALE,
    LAB_B_SCALE,
    LAB_EPSILON,
    LAB_KAPPA,
    LAB_L_OFFSET,
    LAB_L_SCALE,
    NAME_CACHE_SIZE,
    SRGB_8BIT_MAX,
    SRGB_GAMMA_OFFSET,
    SRGB_GAMMA_SCALE,
    SRGB_INVERSE_GAMMA,
    SRGB_LINEAR_SLOPE,
    SRGB_LINEAR_THRESHOLD,
    XYZ_TO_LINEAR_SRGB,
)
from waterfall.domain.palette import NAMED_COLORS

_LINEAR_SRGB_TO_XYZ: NDArray[np.float64] = np.asarray(
    np.linalg.inv(XYZ_TO_LINEAR_SRGB), dtype=np.float64
)


def gamma_decode(encoded: NDArray[np.float64]) -> NDArray[np.float64]:
    """sRGB transfer function, inverted."""
    clipped = np.clip(encoded, 0.0, 1.0)
    return np.asarray(
        np.where(
            clipped <= SRGB_LINEAR_THRESHOLD * SRGB_LINEAR_SLOPE,
            clipped / SRGB_LINEAR_SLOPE,
            ((clipped + SRGB_GAMMA_OFFSET) / SRGB_GAMMA_SCALE) ** SRGB_INVERSE_GAMMA,
        ),
        dtype=np.float64,
    )


def srgb_to_lab(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """Gamma-encoded sRGB in 0..1 to CIELAB. Accepts one color or many rows."""
    linear = gamma_decode(np.atleast_2d(np.asarray(rgb, dtype=np.float64)))
    xyz = linear @ _LINEAR_SRGB_TO_XYZ.T
    scaled = xyz / D65_WHITE_XYZ

    # The linear segment near black keeps the transform from having an infinite
    # slope at zero, which would make very dark colors numerically unstable.
    f = np.where(
        scaled > LAB_EPSILON,
        np.cbrt(np.maximum(scaled, 0.0)),
        (LAB_KAPPA * scaled + LAB_L_OFFSET) / LAB_L_SCALE,
    )
    lightness = LAB_L_SCALE * f[:, 1] - LAB_L_OFFSET
    return np.stack(
        [
            lightness,
            LAB_A_SCALE * (f[:, 0] - f[:, 1]),
            LAB_B_SCALE * (f[:, 1] - f[:, 2]),
        ],
        axis=1,
    )


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    red, green, blue = bytes.fromhex(value.lstrip("#"))
    return (red / SRGB_8BIT_MAX, green / SRGB_8BIT_MAX, blue / SRGB_8BIT_MAX)


_PALETTE_RGB: NDArray[np.float64] = np.array(
    [_hex_to_rgb(hex_value) for _, hex_value in NAMED_COLORS], dtype=np.float64
)
_PALETTE_LAB: NDArray[np.float64] = srgb_to_lab(_PALETTE_RGB)
_PALETTE_NAMES: tuple[str, ...] = tuple(name for name, _ in NAMED_COLORS)


@lru_cache(maxsize=NAME_CACHE_SIZE)
def _nearest(quantized: tuple[int, int, int]) -> str:
    lab = srgb_to_lab(
        np.array([[c / SRGB_8BIT_MAX for c in quantized]], dtype=np.float64)
    )
    distances = np.linalg.norm(_PALETTE_LAB - lab, axis=1)
    return _PALETTE_NAMES[int(np.argmin(distances))]


def name_for(rgb: tuple[float, float, float]) -> str:
    """The nearest named color to a gamma-encoded sRGB triple in 0..1."""
    red, green, blue = (
        int(round(float(np.clip(c, 0.0, 1.0)) * SRGB_8BIT_MAX)) for c in rgb
    )
    return _nearest((red, green, blue))
