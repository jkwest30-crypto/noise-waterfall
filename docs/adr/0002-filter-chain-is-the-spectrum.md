# 2. The filter chain defines the spectrum

**Status:** accepted, supersedes the original design

## Context

The first design defined an ideal spectrum

```
S(f) = (f/f_ref)^(s/3.0103) * [1 + G * exp(...)]
```

and asked a cascade of octave-spaced peaking filters to reproduce it. Invariant 6
measured what the browser actually produced and found two independent faults:

- Octave-spaced peaking filters overlap, so their skirts add. The cascade
  overshot the target slope by up to **7.8 dB**. Setting each band's gain to the
  local slope value is the obvious approach and it does not work.
- The band gain used an amplitude decibel scale (`10^(g/20)`) on a power
  spectrum. A 12 dB band produced 6 dB of power in `S(f)` but 12 dB through the
  filter — a silent factor-of-two disagreement between what you saw and heard.

## Decision

Invert the relationship. `S(f)` is *defined* as the realized magnitude response
of the filter chain: eleven low-shelf filters for the slope, one peaking filter
for the band. The colour and the sound are one object viewed twice.

Peaking filters were also the wrong topology — they cannot sustain a tilt past
their outermost centres. Low shelves can. The shelf gains are solved by least
squares with iterative refinement.

## Consequences

Both faults disappear structurally rather than being patched. The realized slope
tracks the target power law to 1.45 dB at the extremes and **exactly 0.000 dB** at
slope 0, so white noise remains precisely `#FFFFFF`.

Invariant 6's tolerance tightened from 2.0 dB to 0.5 dB, because the only error
left is the gap between Chromium's biquad implementation and Python's RBJ
formulas rather than approximation error in tracing a power law.

The slope control is now an approximation of a power law rather than one exactly.
This is acceptable precisely because the colour is computed from the *realized*
response — what you see matches what you hear even where the realization departs
from the ideal.
