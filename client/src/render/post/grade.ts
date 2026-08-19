/**
 * The colour grade: what the frame looks like, as data.
 *
 * A `Grade` is the whole screen-effect state in one plain object — the film
 * stock, not a stack of toggles. It is authored nowhere in this module: the
 * looks live in `looks.ts`, the maths lives in `chain.ts`, and the game pushes
 * changes onto a `GradeStack` as events happen.
 *
 * WHY A STACK AND NOT A SETTING. The interesting grades in this game are
 * momentary — a pad lighting up, a round landing on the player, the merchant's
 * clearing, a critical wound. If each of those wrote into one shared grade,
 * whichever event fired last would win and whichever finished last would clear
 * it, so a hit taken during an extraction would end by resetting the extraction
 * back to the forest. Layers with their own envelopes compose instead: the
 * base look crossfades between PLACES, and every event is a named layer that
 * fades in over the current answer, holds, and fades out — in any overlap, in
 * any order, without any of them knowing about each other.
 *
 * A layer is a PARTIAL grade. Fields it does not name are not touched, which
 * is what lets "the anomaly" say only "more aberration, colder shadows" without
 * also having an opinion about the shop's bloom.
 */

import { lerp } from '../../lib/math';

/** Three floats. Lift / gamma / gain wheels and raw `R G B` colour bytes. */
export type Triple = [number, number, number];

export interface Grade {
  // --- exposure and response ---
  /** Linear multiplier before anything else. 1 is neutral. */
  exposure: number;
  /** Highlight rolloff, 0 linear (clips) .. 1 filmic shoulder. */
  shoulder: number;
  /** Around a 0.5 pivot. 1 is neutral. */
  contrast: number;
  /** 0 greyscale, 1 neutral, >1 pushed. */
  saturation: number;
  /** -1 cold .. 0 neutral .. +1 warm. */
  temperature: number;
  /** -1 green .. 0 neutral .. +1 magenta. */
  tint: number;

  // --- the three wheels ---
  /** Shadows offset, per channel. 0 is neutral. */
  lift: Triple;
  /** Midtone gamma, per channel. 1 is neutral. */
  gamma: Triple;
  /** Highlight gain, per channel. 1 is neutral. */
  gain: Triple;

  // --- light that leaves the frame ---
  /** Bloom intensity. 0 is off and costs nothing — the passes are skipped. */
  bloom: number;
  /** Luminance a pixel has to beat to bloom at all. High keeps it to lights. */
  bloomThreshold: number;
  /** Volumetric shafts out of the brightest sources on screen. */
  shafts: number;

  // --- air ---
  /** Screen-wide haze toward `fogTint`. Distance the map does not have. */
  fog: number;
  /** `R G B` bytes. */
  fogTint: Triple;

  // --- lens ---
  /** Radial RGB split, in pixels at the corner. Keep under ~3 or it is a toy. */
  aberration: number;
  /** Defocus outside `focus`. Near zero during play; a shot uses it. */
  blur: number;
  /** Radius (0..1 of the half-diagonal) that stays sharp. */
  focus: number;

  // --- the frame ---
  /** Corner crush, 0..1. */
  vignette: number;
  /** How far in the crush reaches. Low is a hard iris, high is a soft fall. */
  vignetteSoft: number;
  /** `R G B` bytes. */
  vignetteTint: Triple;
  /** Flat colour over everything — a flash, a wash, a blackout. */
  wash: number;
  /** `R G B` bytes. */
  washTint: Triple;

  // --- surface ---
  /** Film grain, 0..1. 0.02-0.05 is the whole useful range. */
  grain: number;
}

/**
 * Every scalar and every triple, listed once.
 *
 * The mixer walks these instead of the object's own keys so that a field added
 * to `Grade` and forgotten here fails the type check rather than silently
 * refusing to animate.
 */
const SCALARS = [
  'exposure', 'shoulder', 'contrast', 'saturation', 'temperature', 'tint',
  'bloom', 'bloomThreshold', 'shafts', 'fog', 'aberration', 'blur', 'focus',
  'vignette', 'vignetteSoft', 'wash', 'grain',
] as const satisfies readonly (keyof Grade)[];

const TRIPLES = [
  'lift', 'gamma', 'gain', 'fogTint', 'vignetteTint', 'washTint',
] as const satisfies readonly (keyof Grade)[];

/** A grade with nothing happening: the identity of the whole chain. */
export const NEUTRAL: Grade = {
  exposure: 1,
  shoulder: 0,
  contrast: 1,
  saturation: 1,
  temperature: 0,
  tint: 0,
  lift: [0, 0, 0],
  gamma: [1, 1, 1],
  gain: [1, 1, 1],
  bloom: 0,
  bloomThreshold: 0.75,
  shafts: 0,
  fog: 0,
  fogTint: [255, 255, 255],
  aberration: 0,
  blur: 0,
  focus: 1,
  vignette: 0,
  vignetteSoft: 0.6,
  vignetteTint: [0, 0, 0],
  wash: 0,
  washTint: [255, 255, 255],
  grain: 0,
};

/** What a look or an event actually writes. Unnamed fields are left alone. */
export type GradeLayer = Partial<Grade>;

export function cloneGrade(grade: Grade): Grade {
  return {
    ...grade,
    lift: [...grade.lift],
    gamma: [...grade.gamma],
    gain: [...grade.gain],
    fogTint: [...grade.fogTint],
    vignetteTint: [...grade.vignetteTint],
    washTint: [...grade.washTint],
  };
}

/**
 * Blend `over` into `out` by `weight`, in place.
 *
 * One cast, here, on purpose: writing `out[key]` through a union of keys is
 * what the whole field-list design is for, and spelling out 23 assignments
 * twice is how a field ends up animated in one direction and not the other.
 */
function mixInto(out: Grade, over: GradeLayer, weight: number): void {
  if (weight <= 0) return;
  const w = Math.min(1, weight);
  const target = out as unknown as Record<string, number | Triple>;
  const source = over as unknown as Record<string, number | Triple | undefined>;

  for (const key of SCALARS) {
    const value = source[key];
    if (typeof value !== 'number') continue;
    target[key] = lerp(target[key] as number, value, w);
  }
  for (const key of TRIPLES) {
    const value = source[key];
    if (!Array.isArray(value)) continue;
    const current = target[key] as Triple;
    target[key] = [
      lerp(current[0], value[0], w),
      lerp(current[1], value[1], w),
      lerp(current[2], value[2], w),
    ];
  }
}

/** `attack` in, `hold` at full (Infinity = until released), `release` out. */
export interface Envelope {
  /** Seconds to reach full weight. 0 snaps. */
  attack?: number;
  /** Seconds at full weight, or `Infinity` for a sustained layer. */
  hold?: number;
  /** Seconds to fade back out. */
  release?: number;
  /** Weight at the top of the envelope, 0..1. Default 1. */
  peak?: number;
}

interface Layer {
  key: string;
  grade: GradeLayer;
  weight: number;
  peak: number;
  attack: number;
  hold: number;
  release: number;
  /** Counts down through `hold`; the release starts when it hits zero. */
  remaining: number;
  phase: 'attack' | 'hold' | 'release';
}

/**
 * The base look plus every event layer on top of it.
 *
 * Owned by `Game`, stepped on the render clock, and resolved once per frame
 * into the `Grade` that goes out on `RenderState`. The renderer never touches
 * it — a pass that decided its own colour temperature would be a pass with
 * gameplay state in it.
 */
export class GradeStack {
  private current: Grade;
  private from: Grade;
  private to: Grade;
  private fade = 1;
  private fadeRate = 0;
  private readonly layers: Layer[] = [];
  private readonly out: Grade;

  constructor(base: Grade) {
    this.current = cloneGrade(base);
    this.from = cloneGrade(base);
    this.to = cloneGrade(base);
    this.out = cloneGrade(base);
  }

  /**
   * Crossfade the persistent look — the PLACE. Camp, forest, shop, the exit
   * corridor. Called on a zone change and essentially never otherwise.
   */
  setBase(base: Grade, seconds = 1.2): void {
    this.from = cloneGrade(this.current);
    this.to = cloneGrade(base);
    this.fade = seconds > 0 ? 0 : 1;
    this.fadeRate = seconds > 0 ? 1 / seconds : 0;
    if (this.fade === 1) this.current = cloneGrade(base);
  }

  /**
   * A layer that stays until `release(key)`. Re-pushing the same key retargets
   * it without restarting the attack, so a state that is refreshed every frame
   * (danger, the pad's siren) does not stutter at full weight.
   */
  hold(key: string, grade: GradeLayer, envelope: Envelope = {}): void {
    const existing = this.layers.find((layer) => layer.key === key);
    if (existing) {
      existing.grade = grade;
      existing.peak = envelope.peak ?? existing.peak;
      existing.remaining = Infinity;
      existing.phase = existing.weight < existing.peak ? 'attack' : 'hold';
      return;
    }
    this.push(key, grade, { hold: Infinity, ...envelope });
  }

  /** A one-shot: attack, hold, release, then the layer drops itself. */
  pulse(key: string, grade: GradeLayer, envelope: Envelope = {}): void {
    const existing = this.layers.find((layer) => layer.key === key);
    if (existing) {
      // Retrigger. The weight is NOT reset — a second hit landing during the
      // first one's release should carry on from where the screen already is,
      // not drop to zero and climb again, which reads as a flicker.
      existing.grade = grade;
      existing.peak = envelope.peak ?? 1;
      existing.attack = envelope.attack ?? 0.06;
      existing.hold = envelope.hold ?? 0;
      existing.release = envelope.release ?? 0.35;
      existing.remaining = existing.hold;
      existing.phase = 'attack';
      return;
    }
    this.push(key, grade, envelope);
  }

  /** Start this layer's release. Unknown keys are ignored. */
  release(key: string, seconds?: number): void {
    const layer = this.layers.find((entry) => entry.key === key);
    if (!layer) return;
    layer.phase = 'release';
    layer.remaining = 0;
    if (seconds !== undefined) layer.release = seconds;
  }

  has(key: string): boolean {
    return this.layers.some((layer) => layer.key === key);
  }

  /** Drop everything, base included. Zone changes that are cuts, not fades. */
  clear(): void {
    this.layers.length = 0;
  }

  private push(key: string, grade: GradeLayer, envelope: Envelope): void {
    const attack = envelope.attack ?? 0.06;
    this.layers.push({
      key,
      grade,
      weight: attack > 0 ? 0 : (envelope.peak ?? 1),
      peak: envelope.peak ?? 1,
      attack,
      hold: envelope.hold ?? 0,
      release: envelope.release ?? 0.35,
      remaining: envelope.hold ?? 0,
      phase: 'attack',
    });
  }

  step(dt: number): void {
    if (this.fade < 1) {
      this.fade = Math.min(1, this.fade + this.fadeRate * dt);
      const eased = this.fade * this.fade * (3 - 2 * this.fade);
      this.current = cloneGrade(this.from);
      mixInto(this.current, this.to, eased);
    }

    for (let i = this.layers.length - 1; i >= 0; i--) {
      const layer = this.layers[i];
      if (layer.phase === 'attack') {
        layer.weight =
          layer.attack > 0
            ? Math.min(layer.peak, layer.weight + (layer.peak / layer.attack) * dt)
            : layer.peak;
        if (layer.weight >= layer.peak) layer.phase = 'hold';
      } else if (layer.phase === 'hold') {
        layer.remaining -= dt;
        if (layer.remaining <= 0) layer.phase = 'release';
      } else {
        layer.weight =
          layer.release > 0
            ? Math.max(0, layer.weight - (layer.peak / layer.release) * dt)
            : 0;
        if (layer.weight <= 0) this.layers.splice(i, 1);
      }
    }
  }

  /**
   * The frame's grade. The returned object is REUSED every frame — read it or
   * upload it, never keep it.
   */
  resolve(): Grade {
    const out = this.out;
    Object.assign(out, this.current);
    out.lift = [...this.current.lift];
    out.gamma = [...this.current.gamma];
    out.gain = [...this.current.gain];
    out.fogTint = [...this.current.fogTint];
    out.vignetteTint = [...this.current.vignetteTint];
    out.washTint = [...this.current.washTint];
    for (const layer of this.layers) {
      // Smoothstep the weight so a layer arrives and leaves like a dissolve
      // rather than a linear ramp, which is visible on anything slow.
      const w = layer.weight * layer.weight * (3 - 2 * layer.weight);
      mixInto(out, layer.grade, w);
    }
    return out;
  }
}
