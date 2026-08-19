/**
 * The post chain: the frame, finished.
 *
 * WHY THERE IS A GPU IN A CANVAS 2D GAME. Everything in `layers/` draws pixel
 * art into a 2D context and that is not changing — the world is authored at
 * one pixel per pixel and it has to stay that way. But the things that make a
 * frame look expensive are the things that are NOT pixel art: light that
 * spills, air that scatters, a lens that is a lens. Doing those in 2D means
 * blur by repeated `drawImage`, which is both slow and banded. So the scene is
 * drawn into an offscreen 2D surface exactly as before, handed here as one
 * texture, and finished on the GPU.
 *
 * That split is the house style stated as code: WORLD is pixel art, LIGHT and
 * AIR and LENS are smooth. Nothing here is ever nearest-filtered.
 *
 * THE ORDER IS THE POINT, and it is the order a film camera would impose:
 *
 *   scene ─┬─> bright pass ─> blur x3 ──────────────> bloom
 *          │                     └─> radial blur ──> shafts
 *          ├─> downsample + blur ───────────────────> defocus
 *          └───────────────────────────────────────> sharp
 *                                                      │
 *   composite:  aberrated sample -> defocus mix -> + bloom -> + shafts
 *               -> fog -> GRADE (exposure, balance, wheels, contrast,
 *               saturation, shoulder) -> wash -> vignette -> grain
 *
 * Grading is LAST of the colour work and the vignette and grain are after it,
 * because a vignette that gets graded is a vignette that changes colour when
 * the look does, and grain that gets graded stops being grain and becomes
 * texture in the image.
 *
 * COST. Every pass except the composite runs at half resolution or smaller,
 * and every one of them is skipped when its grade term is zero — a frame with
 * no bloom, no shafts and no defocus is one upload and one draw.
 *
 * ponytail: the scene arrives as a full-resolution `texImage2D` from a canvas
 * every frame, which is the one unavoidable cost of the hybrid. If it ever
 * shows up in a profile the upgrade is to draw the world into a WebGL target
 * directly, which is a renderer rewrite, not a tweak here.
 */

import type { Grade } from './grade';

/** A light worth throwing shafts out of, in canvas pixels. */
export interface ShaftLight {
  x: number;
  y: number;
  /** Relative brightness, 0..1. Scales that light's contribution. */
  power: number;
}

/** Most shafts we will ever cast. Four is already more than a frame wants. */
export const MAX_SHAFTS = 4;

const VERTEX = `#version 300 es
out vec2 vUv;
void main() {
  // Fullscreen triangle from the vertex id alone — no buffers, no attributes.
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const HEAD = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
`;

/** Everything above the threshold, with a soft knee so nothing pops on. */
const BRIGHT = `${HEAD}
uniform sampler2D uSrc;
uniform float uThreshold;
void main() {
  vec3 c = texture(uSrc, vUv).rgb;
  float l = dot(c, LUMA);
  // Knee: fade in over the eighth of a stop above the threshold rather than
  // switching on, or a light drifting across the cutoff strobes.
  float k = smoothstep(uThreshold, uThreshold + 0.12, l);
  outColor = vec4(c * k, 1.0);
}`;

/** Separable gaussian. `uStep` carries both the direction and the radius. */
const BLUR = `${HEAD}
uniform sampler2D uSrc;
uniform vec2 uStep;
void main() {
  // 9-tap gaussian folded into 5 linear samples.
  vec3 c = texture(uSrc, vUv).rgb * 0.2270270270;
  c += texture(uSrc, vUv + uStep * 1.3846153846).rgb * 0.3162162162;
  c += texture(uSrc, vUv - uStep * 1.3846153846).rgb * 0.3162162162;
  c += texture(uSrc, vUv + uStep * 3.2307692308).rgb * 0.0702702703;
  c += texture(uSrc, vUv - uStep * 3.2307692308).rgb * 0.0702702703;
  outColor = vec4(c, 1.0);
}`;

/** Straight copy — used to step down a level. Linear filtering does the work. */
const COPY = `${HEAD}
uniform sampler2D uSrc;
void main() { outColor = vec4(texture(uSrc, vUv).rgb, 1.0); }`;

/**
 * Light shafts: a radial blur of the bright buffer TOWARD each light.
 *
 * This is why the shafts land on the right things without any geometry. The
 * bright pass has already thrown away everything that is not a light, and the
 * smear only survives where something occludes the line back to the source —
 * a trunk between the player and a burning rig punches a real gap in the beam,
 * because the trunk is dark in the bright buffer.
 */
const SHAFTS = `${HEAD}
uniform sampler2D uSrc;
uniform vec2 uLight[${MAX_SHAFTS}];
uniform float uPower[${MAX_SHAFTS}];
uniform int uCount;
const int STEPS = 16;
void main() {
  vec3 acc = vec3(0.0);
  for (int i = 0; i < ${MAX_SHAFTS}; i++) {
    if (i >= uCount) break;
    vec2 delta = (uLight[i] - vUv) / float(STEPS) * 0.85;
    vec2 uv = vUv;
    float weight = 1.0;
    vec3 sum = vec3(0.0);
    float total = 0.0;
    for (int s = 0; s < STEPS; s++) {
      uv += delta;
      sum += texture(uSrc, uv).rgb * weight;
      total += weight;
      weight *= 0.92;
    }
    // Shafts die off away from their source, or a light in the corner rakes
    // the whole screen and the effect reads as a lens smudge.
    float reach = 1.0 - smoothstep(0.15, 0.85, distance(vUv, uLight[i]));
    acc += sum / max(total, 0.001) * uPower[i] * reach;
  }
  outColor = vec4(acc, 1.0);
}`;

const COMPOSITE = `${HEAD}
uniform sampler2D uScene;
uniform sampler2D uBloom0;
uniform sampler2D uBloom1;
uniform sampler2D uBloom2;
uniform sampler2D uShafts;
uniform sampler2D uDefocus;

uniform vec2 uResolution;
uniform float uTime;
uniform float uAspect;

uniform float uExposure;
uniform float uShoulder;
uniform float uContrast;
uniform float uSaturation;
uniform float uTemperature;
uniform float uTint;
uniform vec3 uLift;
uniform vec3 uGamma;
uniform vec3 uGain;

uniform float uBloom;
uniform float uShaftAmount;
uniform float uFog;
uniform vec3 uFogTint;
uniform float uAberration;
uniform float uBlur;
uniform float uFocus;
uniform float uVignette;
uniform float uVignetteSoft;
uniform vec3 uVignetteTint;
uniform float uWash;
uniform vec3 uWashTint;
uniform float uGrain;

float hash(vec2 p) {
  p = fract(p * vec2(443.897, 441.423));
  p += dot(p, p + 19.19);
  return fract(p.x * p.y);
}

vec3 tonemap(vec3 c, float amount) {
  // Extended Reinhard with white at 1.7: highlights roll off instead of
  // clipping to flat white, which is the whole reason bloom can be pushed.
  const float W = 1.7;
  vec3 rolled = c * (1.0 + c / (W * W)) / (1.0 + c);
  return mix(c, rolled, amount);
}

void main() {
  // Radial distance, 0 at the centre and ~1 at the corner, aspect corrected
  // so a wide window does not get an oval vignette.
  vec2 centred = (vUv - 0.5) * vec2(uAspect, 1.0);
  float r = length(centred) / (0.5 * length(vec2(uAspect, 1.0)));

  // --- the lens: chromatic aberration on the way in --------------------
  vec2 dir = r > 0.0001 ? normalize(vUv - 0.5) : vec2(0.0);
  vec2 shift = dir * (uAberration * r * r) / uResolution;
  vec3 sharp = vec3(
    texture(uScene, vUv + shift).r,
    texture(uScene, vUv).g,
    texture(uScene, vUv - shift).b
  );

  // --- depth of field: sharp inside the focus radius, soft outside -----
  if (uBlur > 0.001) {
    float defocus = smoothstep(uFocus, 1.0, r) * uBlur;
    sharp = mix(sharp, texture(uDefocus, vUv).rgb, defocus);
  }

  vec3 c = sharp;

  // --- light that leaves the frame -------------------------------------
  if (uBloom > 0.0) {
    vec3 bloom =
      texture(uBloom0, vUv).rgb * 0.5 +
      texture(uBloom1, vUv).rgb * 0.32 +
      texture(uBloom2, vUv).rgb * 0.18;
    c += bloom * uBloom;
  }
  if (uShaftAmount > 0.0) {
    c += texture(uShafts, vUv).rgb * uShaftAmount;
  }

  // --- air: haze, thicker toward the edge of the frame -----------------
  c = mix(c, uFogTint, uFog * (0.55 + 0.45 * r));

  // --- the grade -------------------------------------------------------
  c *= uExposure;
  // White balance. Warm lifts red and drops blue; tint trades green against
  // magenta. Cheap channel scaling, which at these magnitudes is indistinct
  // from a real matrix and costs three multiplies.
  c *= vec3(
    1.0 + uTemperature * 0.18 + uTint * 0.04,
    1.0 - abs(uTemperature) * 0.02 - uTint * 0.07,
    1.0 - uTemperature * 0.18 + uTint * 0.05
  );
  // Lift / gamma / gain, in that order: shadows, midtones, highlights.
  c = c * uGain + uLift * (1.0 - c);
  c = pow(max(c, 0.0), 1.0 / max(uGamma, vec3(0.01)));
  c = (c - 0.5) * uContrast + 0.5;
  c = mix(vec3(dot(max(c, 0.0), LUMA)), c, uSaturation);
  c = tonemap(max(c, 0.0), uShoulder);

  // --- the frame -------------------------------------------------------
  c = mix(c, uWashTint, uWash);
  float vig = smoothstep(uVignetteSoft, 1.15, r);
  c = mix(c, uVignetteTint, vig * uVignette);

  // --- surface ---------------------------------------------------------
  if (uGrain > 0.0) {
    float n = hash(vUv * uResolution + fract(uTime) * 331.7) - 0.5;
    // Grain lives in the shadows and mids, not the highlights — the opposite
    // reads as sensor noise on a blown-out image.
    c += n * uGrain * (1.0 - smoothstep(0.5, 1.0, dot(max(c, 0.0), LUMA)));
  }

  outColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}`;

interface Program {
  program: WebGLProgram;
  uniforms: Map<string, WebGLUniformLocation | null>;
}

interface Target {
  texture: WebGLTexture;
  framebuffer: WebGLFramebuffer;
  width: number;
  height: number;
}

/**
 * One chain per canvas. `create` returns null when WebGL2 is unavailable, and
 * the renderer falls back to blitting the scene straight out — the game is
 * still fully playable, it just looks like it did before this existed.
 */
export class PostChain {
  private readonly gl: WebGL2RenderingContext;
  private readonly programs = new Map<string, Program>();
  private vao: WebGLVertexArrayObject | null = null;
  private sceneTexture: WebGLTexture | null = null;
  private blackTexture: WebGLTexture | null = null;
  /** Half, quarter and eighth resolution, three buffers each. See `resize`. */
  private targets: Target[][] = [];
  private width = 0;
  private height = 0;
  /** False between a context loss and its restore; `render` no-ops. */
  private ready = false;

  private constructor(
    private readonly canvas: HTMLCanvasElement,
    gl: WebGL2RenderingContext,
  ) {
    this.gl = gl;
    canvas.addEventListener('webglcontextlost', this.onLost);
    canvas.addEventListener('webglcontextrestored', this.onRestored);
    this.build();
  }

  static create(canvas: HTMLCanvasElement): PostChain | null {
    const gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: false,
    });
    if (!gl) return null;
    return new PostChain(canvas, gl);
  }

  private readonly onLost = (event: Event): void => {
    // Without preventDefault the browser never fires a restore.
    event.preventDefault();
    this.ready = false;
    this.programs.clear();
    this.targets = [];
    this.width = 0;
    this.height = 0;
  };

  private readonly onRestored = (): void => {
    this.build();
  };

  private build(): void {
    const { gl } = this;
    this.vao = gl.createVertexArray();
    this.compile('bright', BRIGHT);
    this.compile('blur', BLUR);
    this.compile('copy', COPY);
    this.compile('shafts', SHAFTS);
    this.compile('composite', COMPOSITE);
    this.sceneTexture = this.makeTexture();
    this.blackTexture = this.makeTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.blackTexture);
    gl.texImage2D(
      gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE,
      new Uint8Array([0, 0, 0, 255]),
    );
    this.ready = this.programs.size === 5;
  }

  private compile(name: string, source: string): void {
    const { gl } = this;
    const vs = gl.createShader(gl.VERTEX_SHADER);
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    if (!vs || !fs) return;
    gl.shaderSource(vs, VERTEX);
    gl.compileShader(vs);
    gl.shaderSource(fs, source);
    gl.compileShader(fs);
    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      // Loud, once: a chain that silently fails to link is a black screen with
      // no explanation, and the fallback path exists precisely for this.
      console.error(`post/${name}: ${gl.getProgramInfoLog(program) ?? 'link failed'}`);
      gl.deleteProgram(program);
      return;
    }
    const uniforms = new Map<string, WebGLUniformLocation | null>();
    const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number;
    for (let i = 0; i < count; i++) {
      const info = gl.getActiveUniform(program, i);
      if (!info) continue;
      // Array uniforms report as `uLight[0]`; store both spellings so a call
      // site can ask for either.
      const base = info.name.replace(/\[0\]$/, '');
      uniforms.set(base, gl.getUniformLocation(program, info.name));
    }
    this.programs.set(name, { program, uniforms });
  }

  private makeTexture(): WebGLTexture | null {
    const { gl } = this;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    // LINEAR everywhere and CLAMP everywhere. Nothing in this file is pixel
    // art — the whole point is that light and air are smooth — and a wrapped
    // sample would fold the far edge of the screen into a blur or a shaft.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return texture;
  }

  private makeTarget(width: number, height: number): Target {
    const { gl } = this;
    const texture = this.makeTexture();
    gl.texImage2D(
      gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null,
    );
    const framebuffer = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(
      gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0,
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { texture: texture as WebGLTexture, framebuffer: framebuffer as WebGLFramebuffer, width, height };
  }

  /**
   * Reallocate for a new canvas size.
   *
   * Three levels at 1/2, 1/4 and 1/8, three buffers each. Two of the three are
   * the ping-pong a separable blur needs; the third is only ever used at the
   * half level, to hold the defocused copy of the scene while the other two
   * are busy carrying the bloom.
   */
  private resize(width: number, height: number): void {
    if (this.width === width && this.height === height) return;
    const { gl } = this;
    for (const level of this.targets) {
      for (const target of level) {
        gl.deleteTexture(target.texture);
        gl.deleteFramebuffer(target.framebuffer);
      }
    }
    this.targets = [];
    for (let level = 0; level < 3; level++) {
      const scale = 2 << level;
      const w = Math.max(1, Math.floor(width / scale));
      const h = Math.max(1, Math.floor(height / scale));
      this.targets.push([this.makeTarget(w, h), this.makeTarget(w, h), this.makeTarget(w, h)]);
    }
    this.width = width;
    this.height = height;
  }

  private use(name: string): Program | null {
    const program = this.programs.get(name);
    if (!program) return null;
    this.gl.useProgram(program.program);
    return program;
  }

  private bind(program: Program, name: string, unit: number, texture: WebGLTexture | null): void {
    const { gl } = this;
    const location = program.uniforms.get(name);
    if (location === undefined) return;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(location, unit);
  }

  private drawTo(target: Target | null): void {
    const { gl } = this;
    if (target) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, target.framebuffer);
      gl.viewport(0, 0, target.width, target.height);
    } else {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, this.width, this.height);
    }
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  /** One separable blur, source -> `scratch` -> `dest`. */
  private blur(source: Target, scratch: Target, dest: Target, radius: number): void {
    const program = this.use('blur');
    if (!program) return;
    const step = program.uniforms.get('uStep') ?? null;
    this.bind(program, 'uSrc', 0, source.texture);
    this.gl.uniform2f(step, radius / source.width, 0);
    this.drawTo(scratch);
    this.bind(program, 'uSrc', 0, scratch.texture);
    this.gl.uniform2f(step, 0, radius / scratch.height);
    this.drawTo(dest);
  }

  private copyTexture(source: WebGLTexture | null, dest: Target): void {
    const program = this.use('copy');
    if (!program) return;
    this.bind(program, 'uSrc', 0, source);
    this.drawTo(dest);
  }

  private copy(source: Target, dest: Target): void {
    this.copyTexture(source.texture, dest);
  }

  /**
   * Finish one frame.
   *
   * `scene` is the offscreen 2D surface the whole renderer drew into; `lights`
   * are in canvas pixels. Returns false when there is nothing on screen (a lost
   * context, a failed link) so the caller knows the frame did not land.
   */
  render(
    scene: HTMLCanvasElement,
    grade: Grade,
    lights: readonly ShaftLight[],
    time: number,
  ): boolean {
    if (!this.ready) return false;
    const { gl } = this;
    const width = this.canvas.width;
    const height = this.canvas.height;
    if (width < 1 || height < 1) return false;
    this.resize(width, height);
    gl.bindVertexArray(this.vao);
    gl.disable(gl.BLEND);
    gl.disable(gl.DEPTH_TEST);

    // The one full-resolution transfer in the frame. FLIP_Y because a 2D
    // canvas counts rows from the top and a texture counts them from the
    // bottom; without it the whole game is upside down.
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.sceneTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, scene);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);

    const half = this.targets[0];
    const quarter = this.targets[1];
    const eighth = this.targets[2];
    const black = this.blackTexture;

    // --- bloom ---------------------------------------------------------
    let bloom0 = black;
    let bloom1 = black;
    let bloom2 = black;
    if (grade.bloom > 0.001) {
      const bright = this.use('bright');
      if (bright) {
        this.bind(bright, 'uSrc', 0, this.sceneTexture);
        gl.uniform1f(bright.uniforms.get('uThreshold') ?? null, grade.bloomThreshold);
        this.drawTo(half[0]);
      }
      this.blur(half[0], half[1], half[0], 1.0);
      this.copy(half[0], quarter[0]);
      this.blur(quarter[0], quarter[1], quarter[0], 1.0);
      this.copy(quarter[0], eighth[0]);
      this.blur(eighth[0], eighth[1], eighth[0], 1.0);
      bloom0 = half[0].texture;
      bloom1 = quarter[0].texture;
      bloom2 = eighth[0].texture;
    }

    // --- depth of field ------------------------------------------------
    // Before the shafts, because the shaft pass wants half[1] and this one is
    // finished with it by then.
    let defocus = black;
    if (grade.blur > 0.001) {
      this.copyTexture(this.sceneTexture, half[2]);
      this.blur(half[2], half[1], half[2], 2.0);
      defocus = half[2].texture;
    }

    // --- volumetric shafts ---------------------------------------------
    let shafts = black;
    if (grade.shafts > 0.001 && lights.length > 0 && grade.bloom > 0.001) {
      const program = this.use('shafts');
      if (program) {
        const count = Math.min(MAX_SHAFTS, lights.length);
        const uv = new Float32Array(MAX_SHAFTS * 2);
        const power = new Float32Array(MAX_SHAFTS);
        for (let i = 0; i < count; i++) {
          uv[i * 2] = lights[i].x / width;
          // Flipped, same reason the upload is.
          uv[i * 2 + 1] = 1 - lights[i].y / height;
          power[i] = lights[i].power;
        }
        this.bind(program, 'uSrc', 0, bloom0);
        gl.uniform2fv(program.uniforms.get('uLight') ?? null, uv);
        gl.uniform1fv(program.uniforms.get('uPower') ?? null, power);
        gl.uniform1i(program.uniforms.get('uCount') ?? null, count);
        this.drawTo(half[1]);
        shafts = half[1].texture;
      }
    }

    // --- composite -----------------------------------------------------
    const program = this.use('composite');
    if (!program) return false;
    const u = (name: string): WebGLUniformLocation | null =>
      program.uniforms.get(name) ?? null;

    this.bind(program, 'uScene', 0, this.sceneTexture);
    this.bind(program, 'uBloom0', 1, bloom0);
    this.bind(program, 'uBloom1', 2, bloom1);
    this.bind(program, 'uBloom2', 3, bloom2);
    this.bind(program, 'uShafts', 4, shafts);
    this.bind(program, 'uDefocus', 5, defocus);

    gl.uniform2f(u('uResolution'), width, height);
    gl.uniform1f(u('uTime'), time);
    gl.uniform1f(u('uAspect'), width / Math.max(1, height));

    gl.uniform1f(u('uExposure'), grade.exposure);
    gl.uniform1f(u('uShoulder'), grade.shoulder);
    gl.uniform1f(u('uContrast'), grade.contrast);
    gl.uniform1f(u('uSaturation'), grade.saturation);
    gl.uniform1f(u('uTemperature'), grade.temperature);
    gl.uniform1f(u('uTint'), grade.tint);
    gl.uniform3f(u('uLift'), grade.lift[0], grade.lift[1], grade.lift[2]);
    gl.uniform3f(u('uGamma'), grade.gamma[0], grade.gamma[1], grade.gamma[2]);
    gl.uniform3f(u('uGain'), grade.gain[0], grade.gain[1], grade.gain[2]);

    gl.uniform1f(u('uBloom'), grade.bloom > 0.001 ? grade.bloom : 0);
    gl.uniform1f(u('uShaftAmount'), shafts === black ? 0 : grade.shafts);
    gl.uniform1f(u('uFog'), grade.fog);
    gl.uniform3f(u('uFogTint'), ...norm(grade.fogTint));
    gl.uniform1f(u('uAberration'), grade.aberration);
    gl.uniform1f(u('uBlur'), defocus === black ? 0 : grade.blur);
    gl.uniform1f(u('uFocus'), grade.focus);
    gl.uniform1f(u('uVignette'), grade.vignette);
    gl.uniform1f(u('uVignetteSoft'), grade.vignetteSoft);
    gl.uniform3f(u('uVignetteTint'), ...norm(grade.vignetteTint));
    gl.uniform1f(u('uWash'), grade.wash);
    gl.uniform3f(u('uWashTint'), ...norm(grade.washTint));
    gl.uniform1f(u('uGrain'), grade.grain);

    this.drawTo(null);
    return true;
  }

  dispose(): void {
    const { gl } = this;
    this.canvas.removeEventListener('webglcontextlost', this.onLost);
    this.canvas.removeEventListener('webglcontextrestored', this.onRestored);
    for (const level of this.targets) {
      for (const target of level) {
        gl.deleteTexture(target.texture);
        gl.deleteFramebuffer(target.framebuffer);
      }
    }
    for (const { program } of this.programs.values()) gl.deleteProgram(program);
    if (this.sceneTexture) gl.deleteTexture(this.sceneTexture);
    if (this.blackTexture) gl.deleteTexture(this.blackTexture);
    if (this.vao) gl.deleteVertexArray(this.vao);
    this.targets = [];
    this.programs.clear();
    this.ready = false;
  }
}

/** `R G B` bytes to the 0..1 the shader wants. */
function norm(channels: readonly [number, number, number]): [number, number, number] {
  return [channels[0] / 255, channels[1] / 255, channels[2] / 255];
}
