# 1. Layered architecture with machine-enforced invariants

**Status:** accepted

## Context

The app splits across two languages: Python computes every number, the browser
renders pixels and realizes audio. That split is necessary — Web Audio and WebGL
live in the browser, and the colour science is far more testable in Python — but
it creates an obvious failure mode where the two sides drift apart.

## Decision

Strict inward-pointing layers: `api -> engine -> domain`, never the reverse. The
`domain` package depends on numpy and stdlib alone.

Six invariants, all machine-enforced rather than documented and hoped for:

1. `domain/` imports only numpy and stdlib
2. dependencies point inward, no cycles
3. every user-facing control changes both the sound and the colour
4. all physical constants live in `domain/constants.py`
5. every `domain/` function is pure and fully typed
6. the browser's realized audio matches Python's `S(f)` within 0.5 dB

## Consequences

Invariants 3 and 6 together guarantee the app's premise: nothing decorative, and
nothing silent. They have already earned their cost — invariant 6 failed on the
original filter design and forced the inversion recorded in ADR 2, and invariant 3
revealed that two thirds of the band-gain slider was visually dead.

The cost is real: adding a control means registering it in the coupling test, and
adding a constant means putting it in one specific file. Both are cheap next to
the failures they prevent, which are the kind that look like features until
someone measures them.
