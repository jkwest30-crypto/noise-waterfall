/**
 * UI tests against the real WebGL scene.
 *
 * These run in `?test=1`, where the animation loop is replaced by explicit
 * frame rendering at a given time. That makes every frame a pure function of
 * (state, seconds) -- without it, a screenshot would depend on when the
 * screenshot happened to be taken.
 */

import { expect, test, type Page } from "@playwright/test";

// Imported rather than duplicated: these tests must keep passing after
// scripts/measure_region.py rewrites the region for a new photo. Hard-coded
// bounds would have to be hand-edited every time, which is exactly the kind of
// chore that ends with someone deleting the test.
import {FALL_REGION} from "../../web/src/backdrop";

const UNIT = 3.010299956639812;

/** Mean color of the generated water.
 *
 * The canvas is transparent over a photographic backdrop supplied by CSS, so a
 * canvas readback captures only what this app drew -- the photograph is not in
 * it. That is deliberate: it lets these assertions measure the rendered colour
 * rather than a blend with whatever the picture happens to show.
 *
 * The threshold is relative to the brightest pixel in the region, not absolute.
 * An absolute cutoff biases with overall brightness: at -24 dBFS a fixed
 * threshold of 110 matched zero pixels, so the test was quietly measuring
 * nothing and reporting a colour of (0,0,0). */
async function waterColor(page: Page): Promise<{ r: number; g: number; b: number; n: number }> {
  return page.evaluate(() => {
    const source = document.getElementById("view") as HTMLCanvasElement;
    const scratch = document.createElement("canvas");
    scratch.width = source.width;
    scratch.height = source.height;
    const ctx = scratch.getContext("2d")!;
    ctx.drawImage(source, 0, 0);

    // A column down the middle of the fall region, kept clear of the soft top
    // edge and the spray at the base.
    const x = Math.floor(source.width * 0.42);
    const w = Math.floor(source.width * 0.14);
    const y = Math.floor(source.height * 0.32);
    const h = Math.floor(source.height * 0.38);
    const data = ctx.getImageData(x, y, w, h).data;

    let brightest = 0;
    for (let i = 0; i < data.length; i += 4) {
      brightest = Math.max(brightest, data[i] + data[i + 1] + data[i + 2]);
    }
    const cutoff = brightest * 0.4;

    let r = 0;
    let g = 0;
    let b = 0;
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      const luma = data[i] + data[i + 1] + data[i + 2];
      if (luma < cutoff) continue; // rock and fog, not water
      r += data[i];
      g += data[i + 1];
      b += data[i + 2];
      n += 1;
    }
    return n === 0 ? { r: 0, g: 0, b: 0, n: 0 } : { r: r / n, g: g / n, b: b / n, n };
  });
}

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/?test=1${query}`);
  await page.waitForFunction(() => window.__ready === true);
}

async function setParams(page: Page, params: Record<string, number>): Promise<void> {
  await page.evaluate((p) => window.__setParams!(p), params);
  await page.evaluate(() => window.__renderFrame!(1.5));
}

test.describe("the water shows the color of the sound", () => {
  test("white noise renders white water", async ({ page }) => {
    await open(page);
    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0 });

    const { r, g, b, n } = await waterColor(page);
    expect(n, "no water pixels found - the scene did not draw").toBeGreaterThan(500);

    // Neutral: no channel dominates. Generous because the shader adds foam
    // highlights and fog, but a tinted cascade fails this comfortably.
    const spread = (Math.max(r, g, b) - Math.min(r, g, b)) / Math.max(r, g, b);
    expect(spread).toBeLessThan(0.12);
  });

  test("brown noise renders red water", async ({ page }) => {
    await open(page);
    await setParams(page, { slope_db_per_oct: -2 * UNIT });
    const { r, g, b } = await waterColor(page);
    expect(r).toBeGreaterThan(g * 1.5);
    expect(r).toBeGreaterThan(b * 1.5);
  });

  test("violet noise renders blue-violet water", async ({ page }) => {
    await open(page);
    await setParams(page, { slope_db_per_oct: 2 * UNIT });
    const { r, g, b } = await waterColor(page);
    expect(b).toBeGreaterThan(r * 1.5);
    expect(b).toBeGreaterThan(g * 1.5);
  });

  test("a band at 1 kHz renders green water", async ({ page }) => {
    await open(page);
    await setParams(page, {
      slope_db_per_oct: 0,
      band_gain_db: 12,
      band_center_hz: 1000,
      band_width_oct: 0.5,
    });
    const { r, g, b } = await waterColor(page);
    expect(g).toBeGreaterThan(r);
    expect(g).toBeGreaterThan(b);
  });

  test("lowering the level dims the water and keeps its hue", async ({ page }) => {
    await open(page);
    await setParams(page, { slope_db_per_oct: -2 * UNIT, level_db: 0 });
    const loud = await waterColor(page);

    await setParams(page, { level_db: -12 });
    const quiet = await waterColor(page);

    const luma = (c: { r: number; g: number; b: number }) => c.r + c.g + c.b;
    expect(luma(quiet)).toBeLessThan(luma(loud) * 0.9);

    // Red still dominates: the water is a dimmer version of the same colour.
    //
    // Only the *direction* is checked, not the exact ratio. The water is
    // translucent over a grey cliff, so as it dims the composite legitimately
    // moves toward the backdrop -- that is correct rendering, not a hue shift.
    // Exact hue invariance is a property of the computed colour and is pinned
    // to twelve decimals in tests/unit/test_colorimetry.py, where there is no
    // backdrop to blend with.
    expect(quiet.r).toBeGreaterThan(quiet.g);
    expect(quiet.r).toBeGreaterThan(quiet.b);
  });
});

test.describe("the interface", () => {
  test("the swatch reports the color Python computed", async ({ page }) => {
    await open(page);
    await setParams(page, { slope_db_per_oct: -2 * UNIT });

    const shown = await page.textContent("#hex");
    const computed = await page.evaluate(() =>
      window.__renderState!.water.color
        .map((c) => Math.round(Math.max(0, Math.min(1, c)) * 255).toString(16).padStart(2, "0"))
        .join("")
        .toUpperCase(),
    );
    expect(shown).toBe(`#${computed}`);
  });

  test("band center and width are disabled while the band is off", async ({ page }) => {
    await open(page);
    // Not a cosmetic detail: with the band at 0 dB a peaking filter is
    // transparent, so these two controls genuinely do nothing. Leaving them
    // live would make them look broken rather than inactive.
    await setParams(page, { band_gain_db: 0 });
    await expect(page.locator('[data-control="band_center_hz"]')).toBeDisabled();
    await expect(page.locator('[data-control="band_width_oct"]')).toBeDisabled();

    await setParams(page, { band_gain_db: 8 });
    await expect(page.locator('[data-control="band_center_hz"]')).toBeEnabled();
  });

  test("every preset produces a distinct color", async ({ page }) => {
    await open(page);
    const seen = new Set<string>();
    for (const name of ["white", "pink", "brown", "green", "blue", "violet"]) {
      await page.click(`[data-preset="${name}"]`);
      await page.waitForTimeout(30);
      const hex = await page.evaluate(async () => {
        await window.__setParams!({});
        return window.__renderState!.water.color.join(",");
      });
      seen.add(hex);
    }
    expect(seen.size).toBe(6);
  });
});

test.describe("determinism", () => {
  test("the same state and time render identical pixels", async ({ page }) => {
    // The property the screenshot tests depend on. If this fails, image
    // comparison is measuring timing noise rather than the scene.
    await open(page);
    await setParams(page, { slope_db_per_oct: -UNIT, band_gain_db: 6 });

    const first = await page.evaluate(() => {
      window.__renderFrame!(2.25);
      return (document.getElementById("view") as HTMLCanvasElement).toDataURL();
    });
    const second = await page.evaluate(() => {
      window.__renderFrame!(2.25);
      return (document.getElementById("view") as HTMLCanvasElement).toDataURL();
    });
    expect(first).toBe(second);
  });

  test("different times render different pixels", async ({ page }) => {
    // ... and the water is actually moving, not a frozen image.
    await open(page);
    const at = async (t: number) =>
      page.evaluate((seconds) => {
        window.__renderFrame!(seconds);
        return (document.getElementById("view") as HTMLCanvasElement).toDataURL();
      }, t);
    expect(await at(0.5)).not.toBe(await at(3.5));
  });
});

test.describe("the readout names the color once you stop fiddling", () => {
  // ?idle= shortens the three-second wait so the suite does not sit through it.
  const QUICK = "&idle=250";

  test("hex while adjusting, a name once settled", async ({ page }) => {
    await open(page, QUICK);
    await setParams(page, { slope_db_per_oct: -2 * UNIT });

    // Immediately after a change it is still a hex code.
    await expect(page.locator("#hex")).toHaveText(/^#[0-9A-F]{6}$/);

    // ... and after the pause it says what the color is called.
    await expect(page.locator("#hex")).toHaveText("Scarlet", { timeout: 4000 });
    await expect(page.locator("#hex")).toHaveClass(/is-name/);
  });

  test("touching a control puts the hex back", async ({ page }) => {
    await open(page, QUICK);
    await setParams(page, { slope_db_per_oct: -2 * UNIT });
    await expect(page.locator("#hex")).toHaveText("Scarlet", { timeout: 4000 });

    await setParams(page, { slope_db_per_oct: 2 * UNIT });
    await expect(page.locator("#hex")).toHaveText(/^#[0-9A-F]{6}$/);
    await expect(page.locator("#hex")).not.toHaveClass(/is-name/);

    // ... then settles again on the new color's name.
    await expect(page.locator("#hex")).toHaveText("Ultramarine", { timeout: 4000 });
  });

  test("the name matches the color Python computed", async ({ page }) => {
    await open(page, QUICK);
    await setParams(page, { band_gain_db: 12, band_center_hz: 1000, band_width_oct: 0.5 });
    await page.waitForFunction(() =>
      document.getElementById("hex")!.classList.contains("is-name"),
    );

    const shown = await page.textContent("#hex");
    const fromEngine = await page.evaluate(() => window.__renderState!.water.color_name);
    expect(shown).toBe(fromEngine);
  });

  test("it does not name the color while a control is still moving", async ({ page }) => {
    // The point of the delay: a name appearing mid-drag would flicker through a
    // dozen words as the colour sweeps past them.
    await open(page, "&idle=1500");
    await setParams(page, { slope_db_per_oct: -UNIT });
    await page.waitForTimeout(400);
    await setParams(page, { slope_db_per_oct: 0 });
    await page.waitForTimeout(400);
    await setParams(page, { slope_db_per_oct: UNIT });
    await page.waitForTimeout(400);
    await expect(page.locator("#hex")).toHaveText(/^#[0-9A-F]{6}$/);
  });
});

test.describe("the water sits on the photographed cascade", () => {
  /** Alpha profile across a horizontal line, as fractions of canvas width. */
  async function alphaAcross(page: Page, atHeight: number): Promise<number[]> {
    return page.evaluate((fraction) => {
      const source = document.getElementById("view") as HTMLCanvasElement;
      const scratch = document.createElement("canvas");
      scratch.width = source.width;
      scratch.height = source.height;
      scratch.getContext("2d")!.drawImage(source, 0, 0);
      const y = Math.floor(source.height * fraction);
      const row = scratch.getContext("2d")!.getImageData(0, y, source.width, 1).data;
      const out: number[] = [];
      for (let x = 0; x < source.width; x += 1) out.push(row[x * 4 + 3]);
      return out;
    }, atHeight);
  }

  test("the cascade is drawn only inside the measured region", async ({ page }) => {
    // The point of the backdrop feature: the generated water has to land on the
    // photographed cascade, not beside it. Bounds come from backdrop.ts, so a
    // re-measure moves the test with the code instead of breaking it.
    await open(page);
    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0 });

    const alpha = await alphaAcross(page, 0.5); // mid-fall, clear of the spray
    const width = alpha.length;

    const drawn = alpha.map((a, i) => (a > 4 ? i / width : -1)).filter((v) => v >= 0);
    expect(drawn.length, "no water drawn at all").toBeGreaterThan(20);

    // Nothing outside the outlined region, allowing a pixel or two for the
    // mask's feathered edge.
    const margin = 0.01;
    expect(Math.min(...drawn)).toBeGreaterThanOrEqual(FALL_REGION.left - margin);
    expect(Math.max(...drawn)).toBeLessThanOrEqual(FALL_REGION.right + margin);

    // And well clear of the frame edges either side.
    const outside = [0.05, 0.95, FALL_REGION.left - 0.06, FALL_REGION.right + 0.06];
    for (const at of outside) {
      if (at < 0 || at > 1) continue;
      expect(alpha[Math.floor(width * at)], `x=${at.toFixed(2)} should be empty`).toBe(0);
    }
  });

  test("the cutout follows the shape of the cascade, not a rectangle", async ({ page }) => {
    // A waterfall is not a box. This one narrows at the lip and widens on the
    // way down, so a rectangular region would spill water onto the rocks.
    await open(page);
    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0 });

    const spanAt = async (height: number) => {
      const alpha = await alphaAcross(page, height);
      const drawn = alpha.map((a, i) => (a > 4 ? i / alpha.length : -1)).filter((v) => v >= 0);
      return drawn.length ? Math.max(...drawn) - Math.min(...drawn) : 0;
    };

    const high = await spanAt(0.30);
    const low = await spanAt(0.75);
    expect(high).toBeGreaterThan(0.1);
    expect(low, "the fall should widen on the way down").toBeGreaterThan(high * 1.05);
  });

  test("the water is opaque, hiding the photographed cascade", async ({ page }) => {
    // Reversed from an earlier version of this test, which asserted the water
    // was translucent. The requirement changed: the photograph now supplies the
    // shape and the setting only, and every drop you see is generated and
    // carries the colour of the sound. Lower WATER_OPACITY in backdrop.ts and
    // this is what fails.
    await open(page);
    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0 });

    const alpha = await alphaAcross(page, 0.5);
    const drawn = alpha.map((a, i) => (a > 4 ? i : -1)).filter((i) => i >= 0);
    expect(drawn.length, "no water drawn").toBeGreaterThan(50);

    // The middle is solid, so the photographed cascade is hidden there. Measured
    // over the central half rather than the whole span, because the rim is
    // deliberately see-through -- see the edge-fade test below.
    const first = drawn[0];
    const last = drawn[drawn.length - 1];
    const quarter = Math.round((last - first) * 0.25);
    const middle = alpha.slice(first + quarter, last - quarter);
    const mean = middle.reduce((a, b) => a + b, 0) / middle.length;
    expect(mean).toBeGreaterThan(240);
  });

  test("the edges fade so the photograph shows through them", async ({ page }) => {
    // The rim is deliberately translucent: a hard boundary between opaque water
    // and bare rock reads as a cut-out. EDGE_FADE and EDGE_BLEND in backdrop.ts
    // control it, and setting EDGE_FADE to 0 is what makes this fail.
    await open(page);
    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0 });

    const alpha = await alphaAcross(page, 0.5);
    const drawn = alpha.map((a, i) => (a > 4 ? i : -1)).filter((i) => i >= 0);
    const first = drawn[0];
    const last = drawn[drawn.length - 1];
    const span = last - first;

    // Just inside either edge the photograph is still visible through the water.
    const nearLeft = alpha[first + Math.round(span * 0.02)];
    const nearRight = alpha[last - Math.round(span * 0.02)];
    expect(nearLeft).toBeLessThan(200);
    expect(nearRight).toBeLessThan(200);

    // ... and it has become solid by the time you reach the middle.
    expect(alpha[first + Math.round(span * 0.5)]).toBeGreaterThan(240);
  });

  test("level changes the pace, not the size or the transparency", async ({ page }) => {
    // What level does to the water was deliberately changed: it used to thin
    // the cascade and narrow it, which made a quiet sound look like less water
    // rather than gentler water. Now it only slows it down.
    await open(page);

    const profile = async () => {
      const alpha = await alphaAcross(page, 0.5);
      const drawn = alpha.map((a, i) => (a > 4 ? i / alpha.length : -1)).filter((v) => v >= 0);
      const inside = alpha.filter((a) => a > 4);
      // Mean rather than peak: a single brightest pixel depends on where the
      // noise happens to sit, and the two speeds are at different phases of it.
      // The mean over the whole width is the density of water, which is the
      // thing that must not change.
      const mean = inside.reduce((a, b) => a + b, 0) / Math.max(inside.length, 1);
      return { span: Math.max(...drawn) - Math.min(...drawn), mean };
    };

    await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0, level_db: 0 });
    const loud = await profile();

    await setParams(page, { level_db: -30 });
    const quiet = await profile();

    // Same width, same density.
    expect(quiet.span).toBeCloseTo(loud.span, 2);
    expect(quiet.mean).toBeGreaterThan(loud.mean * 0.9);
    expect(quiet.mean).toBeLessThan(loud.mean * 1.1);
  });

  test("a quiet sound falls more slowly than a loud one", async ({ page }) => {
    // Measured as how much the frame changes over a fixed slice of time: slower
    // water moves less between two instants.
    await open(page);

    const movement = async (level: number) => {
      await setParams(page, { slope_db_per_oct: 0, band_gain_db: 0, level_db: level });
      return page.evaluate(() => {
        const canvas = document.getElementById("view") as HTMLCanvasElement;
        const scratch = document.createElement("canvas");
        scratch.width = canvas.width;
        scratch.height = canvas.height;
        const ctx = scratch.getContext("2d")!;
        const grab = (t: number) => {
          window.__renderFrame!(t);
          ctx.clearRect(0, 0, scratch.width, scratch.height);
          ctx.drawImage(canvas, 0, 0);
          return ctx.getImageData(0, 0, scratch.width, scratch.height).data;
        };
        const a = grab(4.0);
        const b = grab(4.25);
        let total = 0;
        for (let i = 0; i < a.length; i += 4) total += Math.abs(a[i] - b[i]);
        return total;
      });
    };

    const loud = await movement(0);
    const quiet = await movement(-30);
    expect(quiet, "quiet water should move less in the same time").toBeLessThan(loud * 0.75);
  });

  test("the backdrop is behind the stage", async ({ page }) => {
    await open(page);
    const background = await page.evaluate(
      () => getComputedStyle(document.querySelector(".stage")!).backgroundImage,
    );
    expect(background).toContain("jungle-waterfall.png");

    const status = await page.evaluate(async () => {
      const response = await fetch("/jungle-waterfall.png");
      return response.status;
    });
    expect(status).toBe(200);
  });
});
