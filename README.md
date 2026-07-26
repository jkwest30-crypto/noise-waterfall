# Waterfall

Dial in a sound, listen to it, and see what color it is — rendered as a waterfall.

Sleep and focus apps offer a fixed menu: white noise, pink noise, green noise.
This lets you shape exactly the sound you want and shows you its color.

## The rule

> **Every control changes both the sound and the color.**

Nothing repaints the water without altering what you hear, and nothing alters what
you hear without moving the color. This is enforced by a test, not a convention —
see `tests/unit/test_control_coupling.py`.

## Run it

**Double-click `start.command` in Finder.** It starts both servers, waits for the
engine, and opens your browser. Press **Listen**.

Or from a terminal, from anywhere in the project:

```bash
npm start
```

Ctrl-C in that window stops both servers. The engine's lifetime is tied to the
script's, so quitting never strands a process holding a port.

First time only:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
nvm install 20 && npm install && npx playwright install chromium
```

The launcher checks all of this and tells you exactly what to run if something is
missing, rather than failing somewhere confusing.

### About the ports

The app uses **5373** (web) and **8317** (engine), deliberately off the defaults —
5173 is already taken by another project on this machine, and Vite silently falls
back to the next free port when one is busy, which is how a whole test run once
ended up pointed at a different app. `strictPort` now makes that a loud failure.

The launcher also resolves Node itself rather than trusting `PATH`: a
non-interactive shell never sources nvm, and an old default Node fails deep inside
Vite's own source with `Unexpected token '||='` rather than saying the version is
wrong.

## Test it

```bash
.venv/bin/python -m pytest tests/unit tests/integration && .venv/bin/python -m mypy src/waterfall && npx playwright test
```

95 Python tests, 29 Playwright tests, `mypy --strict` on the domain layer.

## Changing the look

Two things you will probably want to adjust, both without touching anything else.

### What level does to the water

Level sets the **pace** of the cascade — quiet water falls more gently. It does
not thin the water or narrow it: a quiet sound should look like gentler water,
not less of it. The floor is one number in the same file:

```ts
export const LEVEL_SPEED_FLOOR = 0.28;
```

That is the speed at the quietest setting, as a fraction of full. Never `0`, so
the water never freezes.

Level still changes the *colour*, by dimming it — Scarlet at 0 dBFS becomes
Black Cherry at −30. That is what keeps every control changing both the sound and the
colour.

### How much of the photo's water you see

```ts
export const WATER_OPACITY = 1;
```

At `1` the photograph's own white cascade is **completely hidden** — the picture
supplies the shape and the setting, and every drop you see is generated and
carries the colour of the sound.

Lower it to let the photographed water show through and blend with the tint.
Around `0.5` reads as the two being one body of water; below about `0.25` the
colour stops being legible.


### How the edges blend

The rim of the cascade fades out so the photograph shows through it, becoming
fully opaque further in. A hard boundary between solid colour and bare rock
reads as a cut-out; letting the picture bleed through the border settles it into
the scene. Two knobs, same file:

```ts
export const EDGE_FADE  = 1.0;   // 1 = rim fully see-through, 0 = hard edge
export const EDGE_BLEND = 0.14;  // how far in before the water is solid
```

`EDGE_BLEND` is measured against the mask's baked distance channel, where `1.0`
is half the cascade's width — so `0.14` reaches full opacity about a fourteenth
of the width in from either side. Larger shows more of the photograph; smaller
sharpens the edge back into a line.

The distance is computed once by `measure_region.py` and stored in the mask's
green channel, so changing either number takes effect immediately without
regenerating anything.


### How high the spray throws

```ts
export const SPRAY_RISE = 0.07;  // peak height, as a fraction of the cascade's width
```

The arc is written as `4·h·t·(1−t)`, which peaks at exactly `h` when `t` is 0.5 —
so this number *is* the height, rather than something you have to solve for out
of a velocity and a gravity term.

### Using a different photo

Outline the cascade in any image editor — a freehand lasso, not a rectangle —
save the outlined and clean versions, then:

```bash
.venv/bin/python scripts/measure_region.py "~/Downloads/waterfall area.png" \
    --plain "~/Downloads/jungle waterfall.png"
```

It finds the outline, fills it into a cutout mask, installs both images and
rewrites the region in `backdrop.ts`. Add `--dry-run` to see the numbers without
changing anything. Then confirm:

```bash
npx playwright test -g "sits on the photographed"
```

**Outline the shape, don't box it.** A waterfall narrows at the lip and widens
into the pool; a rectangle spills rendered water onto the rocks either side. The
script handles a rectangle-with-handles selection too, but the result is worse.

Nothing here should be hand-edited. Nudging the region by eye until it "looks
about right" is how the rendered cascade ends up subtly off the photographed one
in a way nobody can quite name.

## The readout names itself

Stop moving the controls for three seconds and the hex code becomes the colour's
name — `#FF1500` settles into **Scarlet**, `#FFDF5A` into **Mustard**. Touch any
control and it goes back to hex.

The delay is the point: naming during a drag would flicker through a dozen words
as the colour sweeps past them. The nearest name is found in CIELAB rather than
RGB, because RGB distance does not match how different two colours look — in RGB
a dark navy sits closer to black than to blue.

## How it works

Python owns every number. The browser renders pixels and realizes audio, and
decides nothing. The whole contract is one small struct: a color, three motion
scalars, and a filter chain.

The filter chain **is** the spectrum — `S(f)` is defined as its realized magnitude
response rather than as an ideal curve the filters try to match. So the color and
the sound are not two things kept in sync; they are one object viewed twice.

The full derivation, including the parts that are physics and the parts that are
designed metaphor, is in [docs/color-mapping.md](docs/color-mapping.md).

### The headline result

The color of noise is *formally defined* by its power spectral density slope.
Run that family through the colorimetry and it reproduces its own names:

| Noise | dB/octave | Renders |
|---|---|---|
| Violet | +6.02 | `#3B00FF` violet |
| Blue / azure | +3.01 | `#006EFF` azure |
| **White** | **0.00** | **`#FFFFFF`** exactly, zero saturation |
| Pink | −3.01 | `#FF7406` orange |
| Brown / red | −6.02 | `#FF1500` red |

Four of five land on their name. Pink renders orange because pink is a
*non-spectral* color that no power law can produce, and green noise renders yellow
because 500 Hz maps to 578 nm. Both are asserted in tests so they stay documented
behavior rather than drifting into bugs. The app shows the color it really
produces rather than bending the math to hit the label.

## Working on it

```
/feature <description>
```

Runs architect → implement → test-engineer. The architect decides which layer a
change belongs in and refuses changes that violate an invariant; the test engineer
ensures coverage exists and runs everything. Definitions are in `.claude/agents/`.

### The six invariants

All machine-enforced. Never weaken a test to make a change fit.

1. `domain/` imports only numpy and stdlib
2. Dependencies point inward: `api → engine → domain`, no cycles
3. Every control changes both the sound and the color
4. All physical constants live in `domain/constants.py`
5. Every `domain/` function is pure and fully typed
6. The browser's realized audio matches Python's `S(f)` within 0.5 dB

Invariants 3 and 6 have already paid for themselves. Invariant 6 failed on the
original filter design and forced the inversion in
[ADR 2](docs/adr/0002-filter-chain-is-the-spectrum.md). Invariant 3 revealed that
two thirds of the band-gain slider changed the sound while the color sat still,
which is why that control stops at 12 dB.
