/**
 * GLSL for the water sheet and the spray.
 *
 * `uWaterColor` is the single tint uniform: recoloring the entire cascade is one
 * assignment, because Python already reduced the whole spectrum to one color.
 * Nothing here decides what that color is.
 */

import {
  EDGE_BLEND,
  EDGE_FADE,
  LEVEL_SPEED_FLOOR,
  SPRAY_RISE,
} from "./backdrop";

/** Render a number as a GLSL float literal.
 *
 * Necessary, not decorative: JavaScript stringifies 1.0 as "1", and GLSL has no
 * implicit int-to-float conversion, so interpolating a whole number straight
 * into a shader produces something like `1.0 - 1` and the whole program fails
 * to compile. The failure is quiet from the outside -- the material simply
 * stops drawing -- so it is worth never being able to make. */
function glslFloat(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(value);
}

const NOISE = /* glsl */ `
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
    u.y
  );
}

float fbm(vec2 p) {
  float total = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 5; i++) {
    total += valueNoise(p) * amplitude;
    p *= 2.02;
    amplitude *= 0.5;
  }
  return total;
}
`;

export const waterVertex = /* glsl */ `
varying vec2 vUv;

void main() {
  // No widening as it falls: the sheet has to stay inside the region measured
  // from the backdrop photo, and a spreading cascade would drift outside the
  // photographed one it is meant to sit on.
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const waterFragment = /* glsl */ `
precision highp float;
varying vec2 vUv;

uniform vec3 uWaterColor;
uniform float uTime;
uniform float uFlow;
uniform float uTurbulence;
uniform float uFallSpeed;
uniform float uOpacity;
uniform sampler2D uMask;

${NOISE}

void main() {
  // uv.y is 1 at the lip and 0 at the pool, so scrolling +y moves water down.
  float fall = 1.0 - vUv.y;
  // Level sets the pace. It does not thin the water or narrow it: the cascade
  // is the same size and density at any volume, it just falls more gently.
  float speed = mix(0.55, 2.10, uFallSpeed) * mix(${glslFloat(LEVEL_SPEED_FLOOR)}, 1.0, uFlow);
  float scroll = uTime * speed;

  // Turbulence breaks the sheet into chaotic strands; a coherent spectrum
  // leaves it as smooth glassy sheets.
  float wobble = fbm(vec2(vUv.x * 6.0, fall * 2.0 - scroll * 0.7)) - 0.5;
  float x = vUv.x + wobble * 0.09 * uTurbulence * fall;

  // Strands stretch as they accelerate, so the vertical scale grows with fall.
  float stretch = mix(2.2, 0.9, fall);
  float strands = fbm(vec2(x * 30.0, fall * stretch * 5.0 - scroll * 3.0));
  float fine = fbm(vec2(x * 90.0, fall * 3.0 - scroll * 5.0));
  float body = mix(strands, fine, 0.35 * uTurbulence);

  // Water aerates on the way down: whiter and more broken near the bottom.
  float aeration = smoothstep(0.15, 1.0, fall);
  float lit = pow(clamp(body, 0.0, 1.0), mix(1.6, 0.8, aeration));

  // The strands have to read entirely as colour, because the sheet is opaque:
  // deep is a darker version of the tint, not a hole through to the picture.
  //
  // Kept fairly high. While the photographed water still showed between the
  // strands it supplied the brightness; now that it is covered, a dark floor
  // makes the whole cascade read grey instead of like water.
  vec3 deep = uWaterColor * 0.46;
  vec3 col = mix(deep, uWaterColor, lit);

  // Specular glints on the strand crests, tinted toward white as foam -- but
  // scaled by how bright the water itself is. Foam is light reflected off the
  // water, so it cannot out-shine it. Without this factor a quiet sound washes
  // out toward white instead of staying a dim version of its own color, which
  // breaks the "level never changes hue" rule visually even though the computed
  // color is correct.
  float tone = max(max(uWaterColor.r, uWaterColor.g), uWaterColor.b);
  col += mix(uWaterColor, vec3(1.0), 0.7) * tone * pow(lit, 4.0)
       * (0.45 + 0.55 * aeration);

  // Clip to the outlined shape of the photographed cascade. The mask is
  // cropped to this plane so vUv indexes it directly, and it is already
  // feathered -- so there is no separate edge falloff here that would pull the
  // water in from the shape that was traced.
  // R is coverage, G is how far inside the shape this pixel sits. The distance
  // is baked at generation time and scaled here, so the blend width is a knob
  // in backdrop.ts rather than something that needs the mask regenerating.
  vec2 shape = texture2D(uMask, vUv).rg;
  float cutout = shape.r;
  float inset = clamp(shape.g / ${glslFloat(EDGE_BLEND)}, 0.0, 1.0);


  // Opaque wherever the cutout says there is water, so the photographed
  // cascade underneath is completely hidden -- the picture supplies the shape
  // and the setting, not the water. The strands show up as colour variation
  // above rather than by letting the photo through between them, and there is
  // no fade at the lip for the same reason.
  //
  // (No backticks in these shader comments -- the GLSL lives in a TypeScript
  // template literal, so a stray backtick ends the string mid-shader.)
  //
  // uOpacity below 1 reveals the photographed water again; see backdrop.ts.
  //
  // The rim is the exception: alpha eases in from the edge so the photograph
  // bleeds through the border and the cascade settles into the scene instead of
  // ending at a cut line. Fully opaque from EDGE_BLEND inward.
  float rim = mix(1.0 - ${glslFloat(EDGE_FADE)}, 1.0, inset);
  float alpha = cutout * rim * uOpacity;

  gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
}
`;

export const sprayVertex = /* glsl */ `
attribute float aSeed;
attribute float aScale;

uniform float uTime;
uniform float uFlow;
uniform float uTurbulence;
uniform float uPointScale;
uniform float uScale;

varying float vLife;

void main() {
  // Each droplet runs its own loop, offset by its seed, so the impact reads as
  // continuous rather than as synchronised bursts.
  // Slows with the level alongside the sheet, so the whole cascade eases off
  // together rather than the splash carrying on at full pace.
  float speed = (0.55 + 0.55 * fract(aSeed * 7.31))
              * mix(${glslFloat(LEVEL_SPEED_FLOOR)}, 1.0, uFlow);
  float life = fract(uTime * speed + aSeed);
  vLife = life;

  float angle = aSeed * 6.2831853;
  float spread = (0.35 + 1.05 * uTurbulence) * uScale;
  vec3 pos = position;
  pos.x += cos(angle) * life * spread * (0.4 + fract(aSeed * 3.7));
  // Ballistic arc, written so its peak height is exactly SPRAY_RISE: 4*h*t*(1-t)
  // tops out at h when t is 0.5. Parameterised this way rather than as raw
  // velocity and gravity terms so the height is one readable number instead of
  // something you have to solve for.
  pos.y += 4.0 * ${glslFloat(SPRAY_RISE)} * uScale * life * (1.0 - life);

  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = aScale * uPointScale * (1.0 - life * 0.45);
}
`;

export const sprayFragment = /* glsl */ `
precision highp float;
varying float vLife;

uniform vec3 uWaterColor;
uniform float uOpacity;

void main() {
  vec2 d = gl_PointCoord - vec2(0.5);
  float r = dot(d, d);
  if (r > 0.25) discard;
  float soft = 1.0 - smoothstep(0.0, 0.25, r);
  // Droplets are foam-white, carrying only a hint of the tint -- and, like the
  // sheet's highlights, they dim with the water rather than staying bright.
  float tone = max(max(uWaterColor.r, uWaterColor.g), uWaterColor.b);
  vec3 col = mix(uWaterColor, vec3(1.0), 0.55) * tone;
  float fade = (1.0 - vLife) * soft;
  gl_FragColor = vec4(col, fade * 0.34 * uOpacity);
}
`;

export const glowVertex = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

export const glowFragment = /* glsl */ `
precision highp float;
varying vec2 vUv;

uniform vec3 uColor;
uniform float uOpacity;

void main() {
  // Radial falloff rather than a flat disc: a MeshBasicMaterial on a circle
  // renders a hard-edged coin, which reads as a UI element sitting on top of
  // the scene instead of light scattering off the impact.
  float d = length(vUv - vec2(0.5)) * 2.0;
  float a = pow(max(0.0, 1.0 - d), 2.6);
  gl_FragColor = vec4(uColor, a * uOpacity);
}
`;
