# How a sound becomes a color

Every number here was derived and verified during design, and every table below
is pinned by a test. If you change a formula, the golden tests will tell you.

## The rule the app is built on

> Every control changes both the sound and the color.

Nothing repaints the water without altering what you hear, and nothing alters
what you hear without moving the color. This is invariant 3, enforced by
`tests/unit/test_control_coupling.py`. An earlier design carried a
wavelength-mapping toggle that changed only the color; the test exists because
that kind of thing is easy to add and hard to notice.

## The constraint that shapes everything

Visible light spans **0.98 octaves** (400–789 THz). Audible sound spans about
**10 octaves** (20 Hz – 20 kHz). The textbook "raise sound by 40 octaves" trick
therefore lands inside the visible band only for **363.5–717.5 Hz** — roughly F♯4
to F5. Everything else is infrared or ultraviolet.

So there is no physically inevitable mapping. Ours is chosen: compress the
audible range log-linearly onto 750–380 nm.

## The seven steps

Implemented across `domain/spectrum.py`, `mapping.py`, `colorimetry.py`,
`descriptors.py` and `audio.py`. Constants live in `domain/constants.py` and
nowhere else (invariant 4).

**1. Spectrum — the filter chain *is* the source of truth.**

`S(f)` is defined as the realized magnitude response of the filter chain:

```
S(f) = |H(f)|²   where H is  11 low-shelf filters (slope) + 1 peaking filter (band)
```

The chain is built in `domain/filters.py` and evaluated **once** per parameter
change in `domain/state.py`. The color and the audio are not two things kept in
sync — they are one object viewed twice.

This is an inversion of the original design, which defined an ideal spectrum and
asked filters to reproduce it. Invariant 6 measured that arrangement failing by
up to **7.8 dB**, plus a factor-of-2 decibel-scale mismatch between the band gain
(amplitude dB) and the spectrum (power dB). Both disappear when the chain defines
the spectrum rather than chasing it.

The shelf gains are **solved for**, not set to the local slope value. Octave-spaced
filters overlap, so their skirts add: setting each gain naively overshoots by up
to 14 dB. A least-squares fit with iterative refinement tracks the target power
law to within 1.45 dB at the extremes, and exactly 0.000 dB at slope 0.

White noise is `slope = 0, gain = 0`: every filter transparent, response exactly
flat, color exactly `#FFFFFF`. Not a special case — the origin of the model.

**2. Frequency → wavelength.** `λ(f) = 750 − 370·(log₂f − log₂20)/9.9658`

**3. Spectral weight.** `P(λ) = S(f(λ))`, preserving the shape of the density
curve. The alternative — literal measure transport, `P(λ) = S(f)·|df/dλ|` — was
evaluated and rejected: the Jacobian is proportional to `f`, which shifts the
whole noise family one step and renders white noise azure and pink noise white.

**4. CIE integration** against the 1931 2° observer, 380–750 nm at 1 nm.

**5. Chromatic adaptation to Illuminant E.** This is what makes a flat spectrum
land on exactly `#FFFFFF`. Under a plain D65 white point it renders warm.

**6. XYZ → sRGB.** Normalize luminance, apply the D65 matrix, **lift** negative
channels rather than clamping them, peak-normalize, scale by amplitude, gamma
encode. Lifting is what preserves saturation: clamping inflates it and shifts hue.

**7. Audio realization.** A ten-band octave-spaced graphic EQ traces the slope;
one peaking filter realizes the band. `Q = √(2^B)/(2^B − 1)`.

**8. Motion** from standard MIR descriptors — spectral centroid drives fall
speed, spectral flatness drives turbulence. Both are defined for any spectrum,
unlike a "center frequency," which is meaningless for a pure power law.

Level drives **pace** as well: quiet water falls more gently, down to
`LEVEL_SPEED_FLOOR` of full speed. It deliberately does *not* thin the cascade or
narrow it — a quiet sound should look like gentler water, not less of it. Level
still changes the colour, through luminance, which is what keeps invariant 3
satisfied: `#FF1600` at 0 dBFS becomes `#630300` at −30, Scarlet to Black Cherry.

## The colors of noise reproduce their own names

The color of noise is *formally defined* by its power spectral density slope.
Running that family through the pipeline:

| Noise | dB/octave | Renders | Saturation | Centroid | Flatness |
|---|---|---|---|---|---|
| Violet / purple | +6.02 | `#3B00FF` | 1.00 | 0.908 | 0.017 |
| Blue / azure | +3.01 | `#006EFF` | 1.00 | 0.846 | 0.232 |
| **White** | **0.00** | **`#FFFFFF`** | **0.00** | **0.500** | **1.000** |
| Pink | −3.01 | `#FF7406` | 0.98 | 0.143 | 0.221 |
| Brown / red | −6.02 | `#FF1500` | 1.00 | 0.071 | 0.014 |

These names were coined by analogy to light a century ago. The colorimetry
reproduces four of five independently, which is the strongest evidence available
that the mapping is principled rather than invented.

## Two names that do not survive

Both are asserted in tests so they stay documented behavior rather than drifting
into bugs.

**Pink renders orange.** Pink is a *non-spectral* color — red plus blue with
green suppressed. No monotonic power law can produce it, so a −3.01 dB/oct tilt
integrates to orange.

**Green noise renders yellow.** Sleep apps define green noise as mid-band around
500 Hz, which lands at 578 nm (`#FFDF5A`). Green needs roughly 1 kHz.

The pattern is consistent: names defined by an actual power law match, names
defined perceptually do not. The UI shows both the name and the color it really
produces rather than bending the math to hit the label.

## Two behaviors that look like bugs

**Hue appears to shift with level, in hex.** It does not. Chromaticity is exactly
invariant in *linear* light — verified to twelve decimals. Gamma encoding is
nonlinear and does not preserve channel ratios, so comparing hex triplets across
two levels shows a shift that is not physically there. Tests assert on linear
values for this reason.

**Narrowing the band eventually *reduces* saturation.** A band's integrated
energy scales with its width, so a very narrow band stops carrying enough power
to compete with the broadband base and the color returns toward white. Flatness
is non-monotonic in width, monotonic in gain.

**Band gain stops at 12 dB, and that is not an arbitrary limit.** Above it the
color stops responding: once the band dominates, the integrated hue is already
the wavelength at its center. Measured ΔE00 is 26.0 for 0→6 dB, 9.1 for 6→12,
then **0.46** for 12→18 and **0.24** for 30→40 — all imperceptible while
remaining plainly audible. A control that keeps changing the sound while the
color sits still is exactly what invariant 3 forbids, so the range ends where
the coupling does. This was found by the test, not by inspection.

## Naming the colour

`domain/naming.py` finds the nearest entry in `domain/palette.py` by Euclidean
distance in CIELAB. The palette is evocative rather than technical — "Rust"
describes a sound better than "chocolate" does — and deliberately dense in the
regions this app can reach, because a sparse palette produces confident but
wrong names.

Two tests keep it honest: the Lab transform is cross-checked against
colour-science, and every palette entry must name *itself*, which fails if two
entries sit close enough for one to shadow the other and make a name unreachable.

Naming is a readout, not a control, so invariant 3 does not apply to it — but it
is still computed in Python, because the browser decides nothing.

## What is physics and what is metaphor

Steps 1–7 are grounded in colorimetry, the noise-color standard, and standard
filter design. They are defensible.

Step 8 uses real descriptors, but the *choice* to bind flatness to turbulence and
centroid to fall speed is a designed metaphor. Nothing in physics requires
bandwidth to mean turbulence. It is a good metaphor — evenly spread energy really
does suggest chaotic water, concentrated energy suggests coherent sheets — but it
is a choice, and this document would rather say so than imply the whole system
falls out of first principles.

## Verification note

The reference tables above were re-derived from **tabulated** CIE 1931 data
before being pinned. Design-time exploration used the Wyman analytic
approximation, which degrades past ~680 nm and below ~400 nm; pinning golden
values to it would have locked in a known error. `tests/unit/test_colorimetry.py`
cross-checks the vendored table against colour-science.
