"""Every physical constant in the system.

Invariant 4: no physical-quantity literal appears anywhere else in domain/.
The architecture test enforces this. The point is that a number like 380.0 or
3.0103 can never be inlined at one call site and silently disagree with the
same number used elsewhere.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# --- Audible range -----------------------------------------------------------

FREQ_MIN_HZ = 20.0
FREQ_MAX_HZ = 20000.0
FREQ_REF_HZ = 1000.0
"""Reference frequency for the slope power law: S(FREQ_REF_HZ) == 1 with no band."""

OCTAVE_SPAN = float(np.log2(FREQ_MAX_HZ / FREQ_MIN_HZ))
"""~9.9658 octaves from 20 Hz to 20 kHz."""

# --- Visible range -----------------------------------------------------------

WAVELENGTH_RED_NM = 750.0
WAVELENGTH_VIOLET_NM = 380.0
WAVELENGTH_SPAN_NM = WAVELENGTH_RED_NM - WAVELENGTH_VIOLET_NM

# Visible light spans only ~0.98 octaves against sound's ~10, which is why the
# frequency-to-wavelength map has to compress rather than transpose. See
# docs/color-mapping.md.

# --- Decibel conventions -----------------------------------------------------

DECIBEL_BASE = 10.0
"""Decibels are base-10 logarithmic."""

DB_PER_OCTAVE_UNIT = DECIBEL_BASE * float(np.log10(2.0))
"""3.0103 dB. One "unit" of spectral slope: pink noise is -1 of these."""

AMPLITUDE_DB_SCALE = 20.0
"""Amplitude ratios are 20*log10."""

POWER_DB_SCALE = 10.0
"""Power ratios are 10*log10.

S(f) is a power spectrum, so anything expressed as a power ratio uses this.
A biquad's `gain_db` is an amplitude-dB figure, but since power = |H|^2 its
contribution in power-dB is 20*log10|H| = gain_db -- the two coincide, which is
why filter gains and spectral slope share one unit.
"""

# --- Parameter ranges --------------------------------------------------------

SLOPE_MAX_DB_PER_OCT = 2.0 * DB_PER_OCTAVE_UNIT
SLOPE_MIN_DB_PER_OCT = -SLOPE_MAX_DB_PER_OCT
"""+/-6.0206 dB/oct: exactly two slope units, brown noise through violet noise.

Expressed as a multiple of DB_PER_OCTAVE_UNIT rather than a rounded 6.0, so the
endpoints land precisely on the standard family instead of 0.02 dB short of it.
"""

BAND_GAIN_MIN_DB = 0.0
BAND_GAIN_MAX_DB = 12.0
"""0 dB disables the band entirely, leaving a pure power law.

Capped at 12 dB because the color stops responding above it. Once the band
dominates the spectrum the integrated hue is already the wavelength at its
center, so further gain is audible but invisible: measured deltaE00 is 9.1 for
6->12 dB, then 0.46 for 12->18 and 0.24 for 30->40. A control that keeps
changing the sound while the color sits still breaks invariant 3, so the range
stops where the coupling does.
"""

BAND_WIDTH_MIN_OCT = 0.05
BAND_WIDTH_MAX_OCT = 4.0
BAND_WIDTH_DEFAULT_OCT = 0.3

LEVEL_MIN_DB = -30.0
LEVEL_MAX_DB = 0.0
"""dBFS. 0 dB is full scale; above it the audio would clip."""

LEVEL_SPAN_DB = LEVEL_MAX_DB - LEVEL_MIN_DB

# --- Colorimetry -------------------------------------------------------------

D65_WHITE_XYZ: NDArray[np.float64] = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)

XYZ_TO_LINEAR_SRGB: NDArray[np.float64] = np.array(
    [
        [3.2404542, -1.5371385, -0.4985314],
        [-0.9692660, 1.8760108, 0.0415560],
        [0.0556434, -0.2040259, 1.0572252],
    ],
    dtype=np.float64,
)

SRGB_LINEAR_THRESHOLD = 0.0031308
SRGB_LINEAR_SLOPE = 12.92
SRGB_GAMMA_SCALE = 1.055
SRGB_GAMMA_EXPONENT = 1.0 / 2.4
SRGB_GAMMA_OFFSET = 0.055

SRGB_8BIT_MAX = 255
"""Full scale for an 8-bit-per-channel hex triplet."""

# --- Audio filter graph ------------------------------------------------------

EQ_BAND_BASE_HZ = 20.0
"""Lowest shelving band. Octave-spaced from here: 20 Hz ... 20.48 kHz."""

EQ_BAND_COUNT = 11
"""Enough octave-spaced shelves to span the whole audible range.

Starting at 31.25 Hz with 10 shelves leaves the bottom octave unsupported and
the realized slope misses the target by ~8 dB there. Covering 20 Hz brings the
worst-case error to ~1.4 dB.
"""

SHELF_SLOPE = 1.0
"""RBJ shelf slope parameter S, matching Web Audio's lowshelf."""

DEFAULT_SAMPLE_RATE_HZ = 48000.0

SOURCE_NOISE_RMS = 1.0 / float(np.sqrt(3.0))
"""RMS of the browser's noise source: uniform over [-1, 1].

A cross-language assumption -- Python sizes the output gain against this, the
browser produces it. tests/ui/audio-contract.spec.ts measures the real buffer
and fails if the two ever disagree.
"""

NOISE_CREST_FACTOR = 5.0
"""How far noise peaks above its RMS, as an amplitude ratio (~14 dB).

Headroom, not a physical constant: noise has no hard maximum, so this is the
level at which excursions become rare enough not to matter. Measured across the
preset family the real crest ranges from 1.74 (white) to 4.15 (a tilt with a
band on top) -- filtering makes the waveform swing wider relative to its RMS.
Set at 5.0 for margin above the worst case observed.
"""

RMS_INTEGRATION_MIN_HZ = 0.5
"""Lower bound of the power integral -- effectively DC, not the audible floor.

Starting at 20 Hz looks reasonable and is wrong: white noise carries energy all
the way down, and a -6 dB/oct tilt has its *largest* response below 20 Hz. That
band is narrow but enormous, and omitting it under-estimated brown noise's true
RMS by 1.7x, which is what let it clip after the first round of compensation.
"""

RMS_INTEGRATION_POINTS = 2048
RMS_GRID_SPLIT_HZ = 1000.0
"""Sampling for the integral of the chain's power gain.

The grid is logarithmic below RMS_GRID_SPLIT_HZ and linear above it, integrated
by trapezoid so the uneven spacing is handled correctly.

Neither spacing works alone. White noise is flat per Hz, so the top octave holds
half the total energy and a purely logarithmic grid under-counts it badly. But a
purely linear grid cannot resolve a -6 dB/oct tilt, which lifts the bottom of the
spectrum 30 dB in the first few hertz: that arrangement was still drifting -- 1.96
down to 1.51 and falling -- at 65536 points. The hybrid converges to five decimals
by about 1024.
"""

FIT_LOW_HZ = 25.0
FIT_HIGH_HZ = 16000.0
FIT_GRID_POINTS = 300
FIT_ITERATIONS = 8
FIT_CACHE_SIZE = 4096
"""Least-squares refinement passes when fitting shelf gains to a target slope.

Octave-spaced shelves overlap heavily, so each band's skirts add to its
neighbours; setting every gain to the local slope value overshoots badly.
The fit solves for the gains that actually produce the requested slope, and
iterates because a biquad's dB response is only approximately linear in gain.
"""

# --- CIELAB (used to pick the nearest named colour) --------------------------

LAB_EPSILON = 216.0 / 24389.0
LAB_KAPPA = 24389.0 / 27.0
LAB_CUBE_ROOT = 1.0 / 3.0
LAB_L_SCALE = 116.0
LAB_L_OFFSET = 16.0
LAB_A_SCALE = 500.0
LAB_B_SCALE = 200.0

SRGB_INVERSE_GAMMA = 2.4
"""Decoding exponent. The encoding side uses its reciprocal."""

NAME_CACHE_SIZE = 4096
"""Distinct 8-bit colours to remember a name for.

Lookups are quantized to 8 bits first, so the cache is bounded by what a screen
can actually display. Without quantizing, 60 frames a second would each present
a slightly different float triple and nothing would ever hit.
"""

# --- Analysis ----------------------------------------------------------------

SUBSAMPLES_PER_WAVELENGTH_BIN = 8
"""Sub-samples averaged within each 1 nm bin when integrating S(f).

The CMF grid is 1 nm, or ~0.0269 octaves per bin. Point-sampling S(f) once per
bin misrepresents a sharp band that varies within the bin; measured worst case
across the parameter space is ~1.2e-2 relative error, about three 8-bit
quantization steps, at the narrowest width and highest gain. Averaging over the
bin integrates the spectrum instead of sampling its center.
"""

DESCRIPTOR_EPSILON = 1e-12
"""Floor for the geometric mean, so a zeroed bin cannot produce log(0)."""
