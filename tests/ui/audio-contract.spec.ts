/**
 * Invariant 6: what you hear is what is colored.
 *
 * Python computes S(f) once and derives both the color and these filter
 * coefficients from it. But the audio is *realized* by the browser, so the two
 * could still drift. This test renders the real graph in an OfflineAudioContext,
 * measures its magnitude response from the impulse response, and compares it
 * against the S(f) Python said it should be.
 *
 * An impulse is used rather than noise because it is deterministic: filtering
 * noise would give a different realization on every run and force statistical
 * averaging to get a stable answer.
 */

import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

interface BandSpec {
  kind: "lowshelf" | "peaking";
  frequency_hz: number;
  gain_db: number;
  q: number;
}

interface ContractCase {
  name: string;
  bands: BandSpec[];
  output_gain: number;
  expected: { hz: number; db: number }[];
}

const contract = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../golden/audio_contract.json", import.meta.url)),
    "utf8",
  ),
) as { reference_hz: number; source_noise_rms: number; cases: ContractCase[] };

/** Python and the browser are allowed to disagree by this much, in dB.
 *
 * Tight, because S(f) is *defined* as this chain's response rather than as an
 * ideal curve the filters merely approximate. The only error left is the gap
 * between Chromium's biquad implementation and the RBJ formulas Python uses --
 * the approximation error in tracing a power law has already been accounted for
 * on both sides. A loose tolerance here would let a genuine drift hide. */
const TOLERANCE_DB = 0.5;

async function measureResponse(
  page: import("@playwright/test").Page,
  bands: BandSpec[],
  frequencies: number[],
) {
  return page.evaluate(
    async ({ bands, frequencies }) => {
      const SAMPLE_RATE = 48000;
      const LENGTH = 65536; // 0.73 Hz bins: enough resolution at 31.25 Hz.

      const ctx = new OfflineAudioContext(1, LENGTH, SAMPLE_RATE);
      const impulse = ctx.createBuffer(1, LENGTH, SAMPLE_RATE);
      impulse.getChannelData(0)[0] = 1;

      const source = ctx.createBufferSource();
      source.buffer = impulse;

      const nodes = bands.map((band) => {
        const node = ctx.createBiquadFilter();
        node.type = band.kind;
        node.frequency.value = band.frequency_hz;
        node.gain.value = band.gain_db;
        node.Q.value = band.q;
        return node;
      });

      const chain: AudioNode[] = [source, ...nodes];
      for (let i = 0; i < chain.length - 1; i += 1) chain[i].connect(chain[i + 1]);
      chain[chain.length - 1].connect(ctx.destination);

      source.start();
      const rendered = await ctx.startRendering();
      const signal = rendered.getChannelData(0);

      // Iterative radix-2 FFT of the impulse response.
      const n = LENGTH;
      const re = new Float64Array(n);
      const im = new Float64Array(n);
      re.set(signal);
      for (let i = 1, j = 0; i < n; i += 1) {
        let bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
          [re[i], re[j]] = [re[j], re[i]];
          [im[i], im[j]] = [im[j], im[i]];
        }
      }
      for (let len = 2; len <= n; len <<= 1) {
        const angle = (-2 * Math.PI) / len;
        const half = len >> 1;
        for (let i = 0; i < n; i += len) {
          for (let k = 0; k < half; k += 1) {
            const wr = Math.cos(angle * k);
            const wi = Math.sin(angle * k);
            const xr = re[i + k + half] * wr - im[i + k + half] * wi;
            const xi = re[i + k + half] * wi + im[i + k + half] * wr;
            re[i + k + half] = re[i + k] - xr;
            im[i + k + half] = im[i + k] - xi;
            re[i + k] += xr;
            im[i + k] += xi;
          }
        }
      }

      const magnitudeAt = (hz: number) => {
        const bin = Math.round((hz * n) / SAMPLE_RATE);
        return Math.hypot(re[bin], im[bin]);
      };

      // Amplitude dB (20 log10), relative to 1 kHz. Python's expectation is in
      // power dB (10 log10) -- the two coincide because the EQ gains are
      // themselves specified in amplitude dB.
      const reference = magnitudeAt(1000);
      return frequencies.map(
        (hz) => 20 * Math.log10(magnitudeAt(hz) / reference),
      );
    },
    { bands, frequencies },
  );
}

test.describe("invariant 6: the browser realizes Python's S(f)", () => {
  for (const testCase of contract.cases) {
    test(`"${testCase.name}" matches within ${TOLERANCE_DB} dB`, async ({ page }) => {
      await page.goto("/");

      const frequencies = testCase.expected.map((point) => point.hz);
      const measured = await measureResponse(page, testCase.bands, frequencies);

      const failures: string[] = [];
      let worst = 0;
      testCase.expected.forEach((point, index) => {
        const error = Math.abs(measured[index] - point.db);
        worst = Math.max(worst, error);
        if (error > TOLERANCE_DB) {
          failures.push(
            `${point.hz.toFixed(0)} Hz: python ${point.db.toFixed(2)} dB, ` +
              `browser ${measured[index].toFixed(2)} dB (off by ${error.toFixed(2)})`,
          );
        }
      });

      expect(
        failures,
        `worst deviation ${worst.toFixed(2)} dB\n${failures.join("\n")}`,
      ).toEqual([]);
    });
  }

  test("a deliberately wrong coefficient is detected", async ({ page }) => {
    // Guards against the whole suite passing vacuously. If this test ever goes
    // green, the comparison above has stopped comparing anything.
    await page.goto("/");
    const white = contract.cases.find((c) => c.name === "white noise")!;
    const sabotaged = white.bands.map((band, index) =>
      index === 4 ? { ...band, gain_db: 18 } : band,
    );

    const frequencies = white.expected.map((point) => point.hz);
    const measured = await measureResponse(page, sabotaged, frequencies);
    const worst = Math.max(
      ...white.expected.map((point, i) => Math.abs(measured[i] - point.db)),
    );
    expect(worst).toBeGreaterThan(TOLERANCE_DB);
  });
});

test.describe("the noise source matches what Python assumes", () => {
  test("its RMS is the value the output gain was sized against", async ({ page }) => {
    // Python divides the playback gain by an assumed source RMS to keep the
    // filtered signal inside full scale. If the generator ever changes shape,
    // every level in the app is wrong and the sound clips again.
    await page.goto("/");
    const measured = await page.evaluate(async () => {
      // Held in a variable so TypeScript does not try to resolve it: this is a
      // URL the dev server serves, not a path on disk relative to the test.
      const modulePath = "/src/audio.ts";
      const mod = await import(/* @vite-ignore */ modulePath);
      const ctx = new OfflineAudioContext(1, 1024, 48000);
      const data = mod.createNoiseBuffer(ctx, 2).getChannelData(0);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];
      return Math.sqrt(sum / data.length);
    });
    expect(measured).toBeCloseTo(contract.source_noise_rms, 2);
  });

  test("the buffer loops without a step at the seam", async ({ page }) => {
    // A plain random buffer jumps discontinuously where it wraps, which ticks
    // once per loop -- audible as a periodic click under sustained noise.
    await page.goto("/");
    const seam = await page.evaluate(async () => {
      // Held in a variable so TypeScript does not try to resolve it: this is a
      // URL the dev server serves, not a path on disk relative to the test.
      const modulePath = "/src/audio.ts";
      const mod = await import(/* @vite-ignore */ modulePath);
      const ctx = new OfflineAudioContext(1, 1024, 48000);
      const data = mod.createNoiseBuffer(ctx, 2).getChannelData(0);
      const n = data.length;

      // Biggest sample-to-sample step across the wrap, against the typical step
      // inside the buffer. Noise steps around constantly; the seam must not
      // stand out from that.
      const wrap = Math.abs(data[0] - data[n - 1]);
      let total = 0;
      for (let i = 1; i < n; i += 1) total += Math.abs(data[i] - data[i - 1]);
      return { wrap, meanStep: total / (n - 1) };
    });

    // Comfortably within the ordinary variation of the signal itself.
    expect(seam.wrap).toBeLessThan(seam.meanStep * 4);
  });
});

test.describe("nothing clips", () => {
  /** Render the real graph -- seeded noise, real filters, real gain -- and
   * report the loudest sample and how many run past full scale.
   *
   * The Python tests predict this from the chain's RMS; this measures it. A
   * prediction and a measurement failing together is a real problem, and a
   * prediction passing while this fails means the model is wrong. */
  async function renderPeak(
    page: import("@playwright/test").Page,
    bands: BandSpec[],
    outputGain: number,
  ) {
    return page.evaluate(
      async ({ bands, outputGain }) => {
        const modulePath = "/src/audio.ts";
        const mod = await import(/* @vite-ignore */ modulePath);
        const seconds = 2;
        const ctx = new OfflineAudioContext(1, 48000 * seconds, 48000);

        const source = ctx.createBufferSource();
        source.buffer = mod.createNoiseBuffer(ctx, seconds);
        const nodes = mod.buildFilterChain(ctx, bands);
        const gain = ctx.createGain();
        gain.gain.value = outputGain;
        mod.connectSeries([source, ...nodes, gain]);
        gain.connect(ctx.destination);
        source.start();

        const data = (await ctx.startRendering()).getChannelData(0);
        let peak = 0;
        let over = 0;
        // Skip the first 100 ms: the filters start from rest and settle.
        for (let i = 4800; i < data.length; i += 1) {
          const v = Math.abs(data[i]);
          if (v > peak) peak = v;
          if (v > 1) over += 1;
        }
        return { peak, over, samples: data.length - 4800 };
      },
      { bands, outputGain },
    );
  }

  for (const testCase of contract.cases) {
    test(`"${testCase.name}" renders without clipping`, async ({ page }) => {
      await page.goto("/");
      const { peak, over, samples } = await renderPeak(
        page,
        testCase.bands,
        testCase.output_gain,
      );
      expect(
        over,
        `${over} of ${samples} samples past full scale, peak ${peak.toFixed(3)}`,
      ).toBe(0);
      // ... and not so quiet that the headroom has been overpaid for.
      expect(peak, `peak only ${peak.toFixed(3)} - unnecessarily quiet`).toBeGreaterThan(0.1);
    });
  }
});
