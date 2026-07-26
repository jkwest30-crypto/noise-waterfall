/**
 * Entry point: wires controls -> Python -> water and audio.
 *
 * `?test=1` swaps the animation loop for explicit frame rendering and exposes
 * hooks on `window`, making the scene a pure function of (state, seconds) so
 * screenshots can be compared across runs.
 */

import { WaterfallAudio } from "./audio";
import { BACKDROP_SRC } from "./backdrop";
import { Controls, DEFAULTS, type Params } from "./controls";
import { WaterfallScene, type WaterState } from "./scene";
import { EngineSocket, renderOnce, type RenderState } from "./socket";

const TEST_MODE = new URLSearchParams(window.location.search).has("test");

/** How long the controls must sit still before the readout names the colour. */
const DEFAULT_IDLE_MS = 3000;

declare global {
  interface Window {
    __renderFrame?: (seconds: number) => void;
    __applyState?: (state: RenderState) => void;
    __setParams?: (params: Partial<Params>) => Promise<void>;
    __renderState?: RenderState | null;
    __settleLabel?: () => void;
    __ready?: boolean;
  }
}

function layout(): { canvas: HTMLCanvasElement; panel: HTMLElement; swatch: HTMLElement } {
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="stage"><canvas id="view"></canvas></div>
    <div class="hud">
      <button type="button" id="listen" class="listen">Listen</button>
      <span class="swatchWrap">
        <span id="swatch" class="swatch"></span>
        <span id="hex" class="hex">#FFFFFF</span>
      </span>
    </div>
    <div class="panel" id="panel"></div>
  `;
  return {
    canvas: document.getElementById("view") as HTMLCanvasElement,
    panel: document.getElementById("panel")!,
    swatch: document.getElementById("swatch")!,
  };
}

function toHex(color: WaterState["color"]): string {
  return (
    "#" +
    color
      .map((c) =>
        Math.round(Math.min(1, Math.max(0, c)) * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
      .toUpperCase()
  );
}

function main(): void {
  const { canvas, panel, swatch } = layout();
  const scene = new WaterfallScene(canvas, { preserveBuffer: TEST_MODE });
  const controls = new Controls(panel);
  const audio = new WaterfallAudio();
  const hex = document.getElementById("hex")!;

  const stage = canvas.parentElement as HTMLElement;
  stage.style.backgroundImage = `url("${BACKDROP_SRC}")`;

  const resize = () => {
    scene.resize(stage.clientWidth, stage.clientHeight);
  };
  window.addEventListener("resize", resize);
  resize();

  // After a spell of not touching anything, the readout stops being a hex code
  // and tells you what the colour is called. Overridable via ?idle= so the UI
  // tests do not have to sit through three real seconds.
  const IDLE_MS = Number(
    new URLSearchParams(window.location.search).get("idle") ?? DEFAULT_IDLE_MS,
  );
  let idleTimer: number | undefined;
  let resting = false;
  let latest: RenderState | null = null;

  const paintLabel = () => {
    if (!latest) return;
    hex.textContent = resting ? latest.water.color_name : toHex(latest.water.color);
    hex.classList.toggle("is-name", resting);
  };

  const apply = (state: RenderState) => {
    latest = state;
    scene.setState(state.water);
    audio.update(state.audio);
    swatch.style.background = toHex(state.water.color);
    paintLabel();
    window.__renderState = state;
  };

  /** Called whenever a control moves: back to the hex, and restart the clock. */
  const touched = () => {
    resting = false;
    paintLabel();
    window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      resting = true;
      paintLabel();
    }, IDLE_MS);
  };
  window.__settleLabel = () => {
    window.clearTimeout(idleTimer);
    resting = true;
    paintLabel();
  };

  const listen = document.getElementById("listen") as HTMLButtonElement;
  listen.addEventListener("click", async () => {
    // Browsers block audio outside a user gesture, so playback starts here
    // rather than on load.
    if (audio.running) {
      await audio.stop();
      listen.textContent = "Listen";
    } else if (window.__renderState) {
      await audio.start(window.__renderState.audio);
      listen.textContent = "Mute";
    }
  });

  if (TEST_MODE) {
    // No animation loop and no live socket: every frame is rendered on demand
    // at an explicit time, so a screenshot is reproducible.
    window.__renderFrame = (seconds) => scene.renderFrame(seconds);
    window.__applyState = apply;
    window.__setParams = async (params) => {
      const merged = { ...DEFAULTS, ...controls.value, ...params };
      controls.set(merged, false);
      apply(await renderOnce(merged));
      touched();
    };
    void window.__setParams({}).then(() => {
      scene.renderFrame(0);
      window.__ready = true;
    });
    return;
  }

  const socket = new EngineSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
  );
  socket.subscribe(apply);
  socket.connect();
  controls.subscribe((params) => {
    socket.send(params);
    touched();
  });
  socket.send(controls.value);
  touched();

  const start = performance.now();
  const frame = () => {
    scene.renderFrame((performance.now() - start) / 1000);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

main();
