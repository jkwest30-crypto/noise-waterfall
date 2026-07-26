---
name: feature
description: Build a change through the architect -> implement -> test pipeline. Use when adding or modifying a feature in the waterfall app, so the architecture is decided before code is written and coverage is verified after.
---

# /feature

Run a change through three stages, in order. The point is that the architecture
is decided **before** code exists and the coverage is verified **after** it does,
rather than both being judged by whoever happened to write the code.

Usage: `/feature <description of the change>`

## Stage 1 — architect

Spawn the `architect` agent with the change description. It decides which layer
the change belongs in, checks the six invariants, writes an ADR if boundaries
move, and implements within that design.

**If the architect refuses the change, stop.** Report its reasoning to the user
and ask how they want to proceed. A refusal means the change as described would
violate an invariant — routing around it defeats the entire pipeline. Do not
implement it yourself.

## Stage 2 — implement

Usually the architect has already done this. If it stopped at a design, implement
exactly what it specified. Do not improve on the design silently; if you disagree,
say so and go back to stage 1.

## Stage 3 — test-engineer

Spawn the `test-engineer` agent with a summary of what changed. It ensures unit,
integration and UI coverage exists, writes what is missing, and runs everything.

**Report the real result.** If the suite is red, say so with the failure output
and do not describe the feature as done. A green report on a red suite is worse
than no pipeline at all.

## Rules for the pipeline itself

- Run the stages in order. Skipping the architect on "small" changes is how the
  structure erodes, since every erosion is individually small.
- Never weaken a test to make a stage pass. If a test blocks the change, that is
  the pipeline working. Bring it back to the architect.
- If a new control was added, confirm the test engineer added it to
  `PERTURBATIONS` in `tests/unit/test_control_coupling.py`. That test is the app's
  defining rule — every control must change both the sound and the color — and it
  does not cover controls nobody registered.

## Summarize for the user

At the end, report in this shape:

- **Design** — layer chosen, invariants verified, ADR written (or why none).
- **Change** — what was actually modified.
- **Tests** — what was added, and the real pass/fail counts.
- **Open** — anything refused, skipped, or untestable, with the reason.
