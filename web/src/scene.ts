/**
 * The three.js waterfall, drawn over a photograph.
 *
 * The camera is orthographic and spans 0..1 in both axes, matching the backdrop
 * image's own coordinates. That is what lets the cascade sit exactly on the
 * photographed one: the region was measured off the picture as fractions, and
 * those fractions are used here unchanged, with no projection maths in between
 * to drift.
 *
 * The canvas is transparent and the photo is a CSS background behind it. The
 * browser composites the two, and a canvas readback captures only the generated
 * water -- which is what the colour assertions in the UI tests want to measure.
 *
 * Renders whatever WaterState it is handed and decides nothing itself. The
 * deterministic test hooks are built in rather than bolted on: retrofitting
 * determinism into a shader pipeline is painful enough that in practice the
 * screenshot tests just never get written.
 */

import * as THREE from "three";

import {
  MASK_SRC,
  FALL_BOTTOM_Y,
  FALL_CENTER_X,
  FALL_CENTER_Y,
  FALL_HEIGHT,
  FALL_WIDTH,
  WATER_OPACITY,
} from "./backdrop";
import {
  glowFragment,
  glowVertex,
  sprayFragment,
  sprayVertex,
  waterFragment,
  waterVertex,
} from "./shaders";

export interface WaterState {
  color: [number, number, number];
  /** Nearest named colour, e.g. "Rust". Computed in Python like everything else. */
  color_name: string;
  flow: number;
  turbulence: number;
  fall_speed: number;
}

const SPRAY_COUNT = 1400;

/** Fraction of the water's opacity the impact glow gets.
 *
 * Fixed, not keyed to level: level changes how fast the water falls, not how
 * much of it there is, so the impact should not brighten with volume. */
const GLOW_STRENGTH = 0.22;

/** Droplet diameter in pixels at a 1000px-tall stage, for a unit-scale droplet.
 *
 * Small on purpose. These are additive and there are 1400 of them: at 26 they
 * came out ~65px on a retina stage and overlapped into one white-hot blob that
 * looked like a fire rather than spray. */
const SPRAY_POINT_SCALE = 3.0;

/** The cutout that clips the water to the photographed cascade's shape. */
function loadMask(): THREE.Texture {
  const texture = new THREE.TextureLoader().load(MASK_SRC);
  // Clamped, so the edge pixels do not wrap round and paint a sliver of water
  // on the opposite side of the sheet.
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.colorSpace = THREE.NoColorSpace;
  return texture;
}

/** Fixed seed so `?test=1` renders identically on every run. */
function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

export class WaterfallScene {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.OrthographicCamera;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly water: THREE.ShaderMaterial;
  private readonly spray: THREE.ShaderMaterial;
  private readonly glowMaterial: THREE.ShaderMaterial;
  private readonly glow: THREE.Mesh;
  private current: WaterState = {
    color: [1, 1, 1],
    color_name: "White",
    flow: 1,
    turbulence: 1,
    fall_speed: 0.5,
  };

  constructor(
    canvas: HTMLCanvasElement,
    options: { seed?: number; preserveBuffer?: boolean; opacity?: number } = {},
  ) {
    const seed = options.seed ?? 0x5eed;
    const opacity = options.opacity ?? WATER_OPACITY;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      // Transparent, so the photograph behind shows through.
      alpha: true,
      // Costs performance, so it is on only under test, where the suite needs
      // to read the rendered pixels back to assert on the water's colour.
      preserveDrawingBuffer: options.preserveBuffer ?? false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);

    // Left 0, right 1, top 1, bottom 0 -- the backdrop's own coordinates.
    this.camera = new THREE.OrthographicCamera(0, 1, 1, 0, -1, 1);

    this.water = new THREE.ShaderMaterial({
      vertexShader: waterVertex,
      fragmentShader: waterFragment,
      transparent: true,
      depthWrite: false,
      uniforms: {
        uWaterColor: { value: new THREE.Color(1, 1, 1) },
        uTime: { value: 0 },
        uFlow: { value: 1 },
        uTurbulence: { value: 1 },
        uFallSpeed: { value: 0.5 },
        uOpacity: { value: opacity },
        uMask: { value: loadMask() },
      },
    });
    const sheet = new THREE.Mesh(
      new THREE.PlaneGeometry(FALL_WIDTH, FALL_HEIGHT, 24, 64),
      this.water,
    );
    sheet.position.set(FALL_CENTER_X, FALL_CENTER_Y, 0);
    this.scene.add(sheet);

    this.spray = new THREE.ShaderMaterial({
      vertexShader: sprayVertex,
      fragmentShader: sprayFragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uWaterColor: { value: new THREE.Color(1, 1, 1) },
        uTime: { value: 0 },
        uFlow: { value: 1 },
        uTurbulence: { value: 1 },
        uPointScale: { value: SPRAY_POINT_SCALE },
        uScale: { value: FALL_WIDTH },
        uOpacity: { value: opacity },
      },
    });
    this.scene.add(new THREE.Points(this.buildSprayGeometry(seed), this.spray));

    this.glowMaterial = new THREE.ShaderMaterial({
      vertexShader: glowVertex,
      fragmentShader: glowFragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uColor: { value: new THREE.Color(1, 1, 1) },
        uOpacity: { value: opacity * GLOW_STRENGTH },
      },
    });
    // Wide and faint. Additive light over an already-bright photograph
    // saturates fast, so this is a suggestion of mist catching the light rather
    // than a lamp under the pool.
    this.glow = new THREE.Mesh(
      new THREE.PlaneGeometry(FALL_WIDTH * 2.6, FALL_WIDTH * 1.6),
      this.glowMaterial,
    );
    this.glow.position.set(FALL_CENTER_X, FALL_BOTTOM_Y + FALL_WIDTH * 0.16, 0);
    this.scene.add(this.glow);
  }

  private buildSprayGeometry(seed: number): THREE.BufferGeometry {
    const random = seededRandom(seed);
    const positions = new Float32Array(SPRAY_COUNT * 3);
    const seeds = new Float32Array(SPRAY_COUNT);
    const scales = new Float32Array(SPRAY_COUNT);

    for (let i = 0; i < SPRAY_COUNT; i += 1) {
      positions[i * 3] = FALL_CENTER_X + (random() - 0.5) * FALL_WIDTH * 0.75;
      // Tight vertical scatter: the droplets all come off the same impact, and
      // spreading their origins as far as they travel blurs the base out.
      positions[i * 3 + 1] = FALL_BOTTOM_Y + (random() - 0.5) * FALL_WIDTH * 0.02;
      positions[i * 3 + 2] = 0;
      seeds[i] = random();
      scales[i] = 0.6 + random() * 1.5;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    geometry.setAttribute("aScale", new THREE.BufferAttribute(scales, 1));
    return geometry;
  }

  setState(state: WaterState): void {
    this.current = state;
    const [r, g, b] = state.color;
    (this.water.uniforms.uWaterColor.value as THREE.Color).setRGB(r, g, b);
    (this.spray.uniforms.uWaterColor.value as THREE.Color).setRGB(r, g, b);

    this.water.uniforms.uFlow.value = state.flow;
    this.water.uniforms.uTurbulence.value = state.turbulence;
    this.water.uniforms.uFallSpeed.value = state.fall_speed;
    this.spray.uniforms.uFlow.value = state.flow;
    this.spray.uniforms.uTurbulence.value = state.turbulence;

    // The glow stays put. Level changes how fast the water falls, not how much
    // of it there is, so the impact should not brighten or spread with volume.
    (this.glowMaterial.uniforms.uColor.value as THREE.Color).setRGB(r, g, b);
  }

  get state(): WaterState {
    return this.current;
  }

  resize(width: number, height: number): void {
    this.renderer.setSize(width, height, false);
    // Droplets are sized in pixels, so they must track the stage height or the
    // splash looks coarse on a small window and sparse on a large one.
    this.spray.uniforms.uPointScale.value =
      (SPRAY_POINT_SCALE * height) / 1000 * this.renderer.getPixelRatio();
  }

  /** Render one frame at an explicit time. Pure in `(state, seconds)`. */
  renderFrame(seconds: number): void {
    this.water.uniforms.uTime.value = seconds;
    this.spray.uniforms.uTime.value = seconds;
    this.renderer.render(this.scene, this.camera);
  }

  dispose(): void {
    this.renderer.dispose();
  }
}
