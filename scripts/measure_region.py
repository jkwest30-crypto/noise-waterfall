#!/usr/bin/env python
"""Measure where the waterfall sits inside a backdrop photo, and write it down.

Give it the *annotated* image -- the photo with the cascade outlined -- and it
finds the outline, fills it into a mask, and updates web/src/backdrop.ts plus
web/public/waterfall-mask.png.

    .venv/bin/python scripts/measure_region.py "~/Downloads/waterfall area.png"

To install a new backdrop photo at the same time:

    .venv/bin/python scripts/measure_region.py "~/Downloads/waterfall area.png" \\
        --plain "~/Downloads/jungle waterfall.png"

Handles either annotation style: a freehand lasso (marching ants) or a
rectangle with blue handles. A lasso is better -- the cascade is not a rectangle,
and a bounding box spills the rendered water onto the rocks beside it.

Measured rather than eyeballed on purpose. Nudging numbers by hand until it
"looks about right" is how the rendered cascade ends up subtly off the
photographed one in a way nobody can quite name.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BACKDROP_TS = ROOT / "web" / "src" / "backdrop.ts"
PUBLIC_IMAGE = ROOT / "web" / "public" / "jungle-waterfall.png"
PUBLIC_MASK = ROOT / "web" / "public" / "waterfall-mask.png"
REFERENCE_IMAGE = ROOT / "docs" / "reference" / "waterfall-area.png"

MASK_FEATHER_PX = 4
"""Softens the mask edge so the water fades out instead of ending in a hard cut."""


def annotation_mask(pixels: np.ndarray) -> np.ndarray:
    """Pixels belonging to the drawn outline, whichever style was used.

    Marching ants alternate pure black and pure white along a line. A white
    pixel with a black one a few pixels away is annotation; the photograph's
    bright water never has pure black beside it, which is what makes this
    separable from the picture itself.
    """
    low, high = pixels.min(axis=2), pixels.max(axis=2)
    white = low > 235
    black = high < 30
    near_black = ndimage.binary_dilation(black, np.ones((7, 7), bool))
    near_white = ndimage.binary_dilation(white, np.ones((7, 7), bool))
    ants = (white & near_black) | (black & near_white)

    # A rectangle-with-handles selection instead: saturated UI blue.
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    handles = (blue > 150) & (blue - red > 70) & (blue - green > 45)

    return ants | handles


def fill_outline(outline: np.ndarray) -> np.ndarray:
    """Close the dashes into a loop, then fill its interior."""
    closed = ndimage.binary_closing(
        ndimage.binary_dilation(outline, np.ones((5, 5), bool)), np.ones((9, 9), bool)
    )
    filled = ndimage.binary_fill_holes(closed)
    if filled is None or not filled.any():
        raise SystemExit("Could not close the outline into a region.")
    # Keep only the largest enclosed area, so a stray mark cannot add a second
    # patch of water somewhere unrelated.
    labels, count = ndimage.label(filled)
    if count > 1:
        sizes = ndimage.sum(filled, labels, range(1, count + 1))
        filled = labels == (int(np.argmax(sizes)) + 1)
    return np.asarray(filled, dtype=bool)


def rewrite_backdrop(region: dict[str, float], width: int, height: int, source: str) -> None:
    text = BACKDROP_TS.read_text()
    for key, value in region.items():
        text = re.sub(
            rf"^(\s*{key}:\s*)[0-9.]+(,.*)$",
            rf"\g<1>{value:.4f}\g<2>",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    for name, value in (("BACKDROP_WIDTH", width), ("BACKDROP_HEIGHT", height)):
        text = re.sub(
            rf"^(export const {name} = )\d+;$", rf"\g<1>{value};", text,
            count=1, flags=re.MULTILINE,
        )
    BACKDROP_TS.write_text(text)
    print(f"updated  {BACKDROP_TS.relative_to(ROOT)}   (measured from {source})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotated", help="photo with the cascade outlined")
    parser.add_argument("--plain", help="the same photo without the annotation")
    parser.add_argument("--dry-run", action="store_true", help="print, change nothing")
    args = parser.parse_args()

    annotated = Path(args.annotated).expanduser().resolve()
    if not annotated.is_file():
        raise SystemExit(f"not found: {annotated}")

    image = Image.open(annotated).convert("RGB")
    width, height = image.size
    pixels = np.asarray(image).astype(int)

    outline = annotation_mask(pixels)
    if outline.sum() < 200:
        raise SystemExit(
            f"No outline found in {annotated.name}.\n"
            "Expected the annotated image -- the one with the cascade outlined."
        )
    filled = fill_outline(outline)

    ys, xs = np.nonzero(filled)
    region = {
        "left": xs.min() / width,
        "right": (xs.max() + 1) / width,
        "top": ys.min() / height,
        "bottom": (ys.max() + 1) / height,
    }

    print(f"{annotated.name}  {width}x{height}")
    print(f"  outline pixels {int(outline.sum())}, enclosing "
          f"{filled.sum() / (width * height) * 100:.1f}% of the image")
    for key, value in region.items():
        print(f"  {key:<7} {value:.4f}")
    print(f"  {'width':<7} {region['right'] - region['left']:.4f}")
    print(f"  {'height':<7} {region['bottom'] - region['top']:.4f}")

    if args.dry_run:
        print("\ndry run - nothing written")
        return 0

    if args.plain:
        plain = Path(args.plain).expanduser().resolve()
        if not plain.is_file():
            raise SystemExit(f"not found: {plain}")
        plain_image = Image.open(plain)
        annotated_aspect = width / height
        plain_aspect = plain_image.width / plain_image.height
        if abs(annotated_aspect - plain_aspect) > 0.01:
            # Everything downstream is a fraction of the image, so a different
            # scale is fine but a different shape puts the water in the wrong place.
            raise SystemExit(
                f"aspect mismatch: annotated {annotated_aspect:.4f} vs "
                f"{plain.name} {plain_aspect:.4f}. Must be the same crop."
            )
        shutil.copy(plain, PUBLIC_IMAGE)
        print(f"installed {PUBLIC_IMAGE.relative_to(ROOT)}")
        # The displayed photo's dimensions drive the stage's CSS aspect ratio,
        # so record those rather than the annotated copy's -- the two are the
        # same picture but not always exported at the same size.
        width, height = plain_image.size

    # Crop the mask to the region, so the water plane's own UVs index it directly
    # with no offset maths in the shader to get wrong.
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    region_width_px = box[2] - box[0]

    coverage = Image.fromarray((filled * 255).astype(np.uint8)).crop(box)
    coverage = coverage.filter(ImageFilter.GaussianBlur(MASK_FEATHER_PX))

    # Second channel: how far inside the shape each pixel is. The shader uses it
    # to lighten the edges toward white so the cascade blends into the rocks
    # instead of ending at a cut line. Baked as a distance rather than as a
    # finished gradient, so the blend width stays adjustable in backdrop.ts
    # without regenerating this file.
    distance = ndimage.distance_transform_edt(filled)
    normalised = np.clip(distance / (region_width_px * 0.5), 0.0, 1.0)
    inset = Image.fromarray((normalised * 255).astype(np.uint8)).crop(box)

    blank = Image.new("L", coverage.size, 0)
    combined = Image.merge("RGB", (coverage, inset, blank))
    PUBLIC_MASK.parent.mkdir(parents=True, exist_ok=True)
    combined.save(PUBLIC_MASK)
    print(f"installed {PUBLIC_MASK.relative_to(ROOT)}  "
          f"({combined.width}x{combined.height}, R=coverage G=inset)")

    REFERENCE_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    if annotated != REFERENCE_IMAGE.resolve():
        shutil.copy(annotated, REFERENCE_IMAGE)
        print(f"kept      {REFERENCE_IMAGE.relative_to(ROOT)}")
    else:
        # Re-running against the already-installed reference is a normal thing
        # to do after changing how the mask is built.
        print(f"reusing   {REFERENCE_IMAGE.relative_to(ROOT)}")

    rewrite_backdrop(region, width, height, annotated.name)
    print("\nNow check it still lands where it should:")
    print('  npx playwright test -g "sits on the photographed"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
