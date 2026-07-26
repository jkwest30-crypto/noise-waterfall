/**
 * Web Audio realization of S(f).
 *
 * The browser owns audio synthesis because Web Audio lives here, while the
 * color is computed in Python. That split is the main architectural risk in the
 * app -- the two could drift. Nothing in this file decides what the sound
 * should be; it only realizes the coefficients Python sends. Invariant 6
 * (tests/ui/audio-contract.spec.ts) measures the response this produces against
 * Python's S(f) to prove they still agree.
 */

export interface BiquadSpec {
  kind: "lowshelf" | "peaking";
  frequency_hz: number;
  gain_db: number;
  q: number;
}

export interface AudioParams {
  bands: BiquadSpec[];
  output_gain: number;
}

/** Ramp constant for setTargetAtTime, in seconds.
 *
 * Parameters arrive as discrete 60 Hz frames from the server; ramping smooths
 * them into a continuous glide. Without it every frame boundary is a step, and
 * stepping a filter frequency produces audible zipper noise. */
export const RAMP_SECONDS = 0.05;

const NOISE_SECONDS = 4;
const DEFAULT_SEED = 0x9e3779b9;

/** Deterministic PRNG so the noise buffer is identical across runs.
 *
 * Reproducibility matters here: without a fixed seed the audio contract test
 * would compare against a different noise realization every run. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Samples crossfaded at the loop point. ~21 ms at 48 kHz. */
const LOOP_CROSSFADE_SAMPLES = 1024;

export function createNoiseBuffer(
  ctx: BaseAudioContext,
  seconds: number = NOISE_SECONDS,
  seed: number = DEFAULT_SEED,
): AudioBuffer {
  const length = Math.floor(ctx.sampleRate * seconds);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  const random = mulberry32(seed);

  // Generate a crossfade's worth of extra, so the start of the loop can be
  // blended with the samples that would have followed the end. Without this the
  // buffer steps discontinuously where it wraps and ticks once per loop.
  const extra = new Float32Array(LOOP_CROSSFADE_SAMPLES);
  for (let i = 0; i < length; i += 1) data[i] = random() * 2 - 1;
  for (let i = 0; i < LOOP_CROSSFADE_SAMPLES; i += 1) extra[i] = random() * 2 - 1;

  for (let i = 0; i < LOOP_CROSSFADE_SAMPLES; i += 1) {
    const t = (i / LOOP_CROSSFADE_SAMPLES) * Math.PI * 0.5;
    // Equal power (cos^2 + sin^2 = 1) rather than linear: the two sides are
    // uncorrelated noise, so a linear fade would dip the RMS through the seam
    // and Python's headroom maths assumes a constant one.
    data[i] = extra[i] * Math.cos(t) + data[i] * Math.sin(t);
  }
  return buffer;
}

/** Build the filter cascade. Node count is fixed for the session.
 *
 * Python always sends the same number of bands -- the emphasis band is present
 * even at 0 dB, where a peaking filter is transparent -- so this graph is
 * constructed once and afterwards only has its parameters ramped. Adding or
 * removing a node mid-playback would click. */
export function buildFilterChain(
  ctx: BaseAudioContext,
  bands: BiquadSpec[],
): BiquadFilterNode[] {
  return bands.map((band) => {
    const node = ctx.createBiquadFilter();
    node.type = band.kind;
    node.frequency.value = band.frequency_hz;
    node.gain.value = band.gain_db;
    node.Q.value = band.q;
    return node;
  });
}

export function connectSeries(nodes: AudioNode[]): void {
  for (let i = 0; i < nodes.length - 1; i += 1) {
    nodes[i].connect(nodes[i + 1]);
  }
}

export function applyBands(
  nodes: BiquadFilterNode[],
  bands: BiquadSpec[],
  when: number,
  ramp: number = RAMP_SECONDS,
): void {
  const count = Math.min(nodes.length, bands.length);
  for (let i = 0; i < count; i += 1) {
    const node = nodes[i];
    const band = bands[i];
    if (ramp <= 0) {
      node.frequency.value = band.frequency_hz;
      node.gain.value = band.gain_db;
      node.Q.value = band.q;
    } else {
      node.frequency.setTargetAtTime(band.frequency_hz, when, ramp);
      node.gain.setTargetAtTime(band.gain_db, when, ramp);
      node.Q.setTargetAtTime(band.q, when, ramp);
    }
  }
}

/** Live playback graph: seeded noise -> filter cascade -> gain -> speakers. */
export class WaterfallAudio {
  private ctx: AudioContext | null = null;
  private nodes: BiquadFilterNode[] = [];
  private gain: GainNode | null = null;
  private pending: AudioParams | null = null;

  get running(): boolean {
    return this.ctx !== null && this.ctx.state === "running";
  }

  /** Must be called from a user gesture -- browsers block autoplay otherwise. */
  async start(params: AudioParams): Promise<void> {
    if (this.ctx) {
      await this.ctx.resume();
      this.update(params);
      return;
    }
    const ctx = new AudioContext();
    this.ctx = ctx;

    const source = ctx.createBufferSource();
    source.buffer = createNoiseBuffer(ctx);
    source.loop = true;

    this.nodes = buildFilterChain(ctx, params.bands);
    this.gain = ctx.createGain();
    // Start silent and ramp up, so beginning playback is a fade rather than a
    // click at whatever amplitude the level slider happens to sit at.
    this.gain.gain.value = 0;

    connectSeries([source, ...this.nodes, this.gain]);
    this.gain.connect(ctx.destination);

    source.start();
    await ctx.resume();
    this.update(params);
  }

  update(params: AudioParams): void {
    this.pending = params;
    if (!this.ctx || !this.gain) return;
    const now = this.ctx.currentTime;
    applyBands(this.nodes, params.bands, now);
    this.gain.gain.setTargetAtTime(params.output_gain, now, RAMP_SECONDS);
  }

  async stop(): Promise<void> {
    if (!this.ctx) return;
    if (this.gain) this.gain.gain.setTargetAtTime(0, this.ctx.currentTime, RAMP_SECONDS);
    await this.ctx.suspend();
  }

  get lastParams(): AudioParams | null {
    return this.pending;
  }
}
