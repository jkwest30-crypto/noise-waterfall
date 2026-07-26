/**
 * The control panel.
 *
 * Bounds mirror the Python constants exactly; the server revalidates anyway,
 * but a slider that can reach an invalid value is a slider that looks broken.
 */

export interface Params {
  slope_db_per_oct: number;
  band_gain_db: number;
  band_center_hz: number;
  band_width_oct: number;
  level_db: number;
}

/** One slope unit, 10*log10(2). Pink noise is exactly -1 of these. */
const UNIT = 3.010299956639812;

export const SLOPE_LIMIT = 2 * UNIT;
export const BAND_GAIN_MAX = 12;
export const FREQ_MIN = 20;
export const FREQ_MAX = 20000;

export const DEFAULTS: Params = {
  slope_db_per_oct: 0,
  band_gain_db: 0,
  band_center_hz: 1000,
  band_width_oct: 0.3,
  level_db: 0,
};

/** Presets named for the familiar noises, which is the menu this app improves on.
 *
 * `honest` records where the standard name and the rendered color disagree, so
 * the UI can say so rather than quietly showing something else. */
export const PRESETS: { name: string; params: Params; honest?: string }[] = [
  { name: "White", params: { ...DEFAULTS } },
  { name: "Pink", params: { ...DEFAULTS, slope_db_per_oct: -UNIT }, honest: "renders orange — pink is non-spectral" },
  { name: "Brown", params: { ...DEFAULTS, slope_db_per_oct: -2 * UNIT } },
  {
    name: "Green",
    params: { ...DEFAULTS, band_gain_db: 12, band_center_hz: 500, band_width_oct: 1 },
    honest: "renders yellow — 500 Hz lands at 578 nm",
  },
  { name: "Blue", params: { ...DEFAULTS, slope_db_per_oct: UNIT } },
  { name: "Violet", params: { ...DEFAULTS, slope_db_per_oct: 2 * UNIT } },
];

interface SliderSpec {
  key: keyof Params;
  label: string;
  min: number;
  max: number;
  step: number;
  logarithmic?: boolean;
  format: (value: number) => string;
}

const SLIDERS: SliderSpec[] = [
  {
    key: "slope_db_per_oct",
    label: "Slope",
    min: -SLOPE_LIMIT,
    max: SLOPE_LIMIT,
    step: 0.01,
    format: (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)} dB/oct`,
  },
  {
    key: "band_gain_db",
    label: "Band gain",
    min: 0,
    max: BAND_GAIN_MAX,
    step: 0.1,
    format: (v) => (v <= 0 ? "off" : `+${v.toFixed(1)} dB`),
  },
  {
    key: "band_center_hz",
    label: "Band center",
    min: FREQ_MIN,
    max: FREQ_MAX,
    step: 0.001,
    logarithmic: true,
    format: (v) => (v >= 1000 ? `${(v / 1000).toFixed(2)} kHz` : `${Math.round(v)} Hz`),
  },
  {
    key: "band_width_oct",
    label: "Band width",
    min: 0.05,
    max: 4,
    step: 0.01,
    format: (v) => `${v.toFixed(2)} oct`,
  },
  {
    key: "level_db",
    label: "Level",
    min: -30,
    max: 0,
    step: 0.5,
    format: (v) => `${v.toFixed(1)} dBFS`,
  },
];

export class Controls {
  private params: Params = { ...DEFAULTS };
  private readonly inputs = new Map<keyof Params, HTMLInputElement>();
  private readonly readouts = new Map<keyof Params, HTMLElement>();
  private readonly rows = new Map<keyof Params, HTMLElement>();
  private onChange: (params: Params) => void = () => {};

  constructor(private readonly root: HTMLElement) {
    this.render();
  }

  subscribe(handler: (params: Params) => void): void {
    this.onChange = handler;
  }

  get value(): Params {
    return { ...this.params };
  }

  set(params: Partial<Params>, notify = true): void {
    this.params = { ...this.params, ...params };
    for (const spec of SLIDERS) {
      const input = this.inputs.get(spec.key);
      if (!input) continue;
      const raw = this.params[spec.key];
      input.value = String(spec.logarithmic ? Math.log2(raw) : raw);
      this.readouts.get(spec.key)!.textContent = spec.format(raw);
    }
    this.updateBandAvailability();
    if (notify) this.onChange(this.value);
  }

  /** Band center and width do nothing while the band is off, so they are
   * disabled rather than left looking live but unresponsive. */
  private updateBandAvailability(): void {
    const live = this.params.band_gain_db > 0;
    for (const key of ["band_center_hz", "band_width_oct"] as const) {
      this.inputs.get(key)!.disabled = !live;
      this.rows.get(key)!.classList.toggle("is-disabled", !live);
    }
  }

  private render(): void {
    const presets = document.createElement("div");
    presets.className = "presets";
    for (const preset of PRESETS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preset";
      button.dataset.preset = preset.name.toLowerCase();
      button.textContent = preset.name;
      if (preset.honest) button.title = preset.honest;
      button.addEventListener("click", () => this.set(preset.params));
      presets.appendChild(button);
    }
    this.root.appendChild(presets);

    for (const spec of SLIDERS) {
      const row = document.createElement("label");
      row.className = "row";

      const label = document.createElement("span");
      label.className = "label";
      label.textContent = spec.label;

      const input = document.createElement("input");
      input.type = "range";
      input.dataset.control = spec.key;
      input.min = String(spec.logarithmic ? Math.log2(spec.min) : spec.min);
      input.max = String(spec.logarithmic ? Math.log2(spec.max) : spec.max);
      input.step = String(spec.step);
      input.value = String(
        spec.logarithmic ? Math.log2(DEFAULTS[spec.key]) : DEFAULTS[spec.key],
      );

      const readout = document.createElement("span");
      readout.className = "readout";
      readout.dataset.readout = spec.key;
      readout.textContent = spec.format(DEFAULTS[spec.key]);

      input.addEventListener("input", () => {
        const raw = Number(input.value);
        this.params = {
          ...this.params,
          [spec.key]: spec.logarithmic ? 2 ** raw : raw,
        };
        readout.textContent = spec.format(this.params[spec.key]);
        this.updateBandAvailability();
        this.onChange(this.value);
      });

      row.append(label, input, readout);
      this.root.appendChild(row);
      this.inputs.set(spec.key, input);
      this.readouts.set(spec.key, readout);
      this.rows.set(spec.key, row);
    }

    this.updateBandAvailability();
  }
}
