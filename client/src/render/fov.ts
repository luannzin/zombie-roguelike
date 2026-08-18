/**
 * Shared field of view: who can see what, and how brightly.
 *
 * This is a VISUAL system. The server keeps broadcasting the whole world and
 * this decides what the player is allowed to make out — no snapshot culling, no
 * netcode change, and shared vision is a `max()` instead of a per-viewer
 * subscription set. In a co-op PvE game the trade is free: the only thing a
 * modified client gains by ignoring the dark is spoiling its own tension.
 *
 * Four lights per viewer, and the brightest one wins on each tile:
 *
 *   sight     a nearly-invisible wash over what the player is FACING, so the
 *             dark holds silhouettes rather than nothing at all
 *   ambient   a small omnidirectional glow, so you can always see your feet
 *   beam      a cone along your aim, reaching much further
 *   spill     a wide, weak, short halo around the beam
 *
 * Two fields come out of this, not one. `light` is VISIBILITY and saturates at
 * 1 — once a tile is fully visible it cannot become more visible. `heat` is
 * WARMTH, and it keeps climbing past 1 as you approach the lamp. That split is
 * what makes the ground under your feet read as *bright* rather than merely
 * legible: the darkness layer converts heat into additive amber, so the hearth
 * around the player glows while the far end of the beam stays a pale wash.
 * Heat is also what the lantern's battery dims — with the lamp off you still
 * see by ambient light, but it is cold.
 *
 * The spill is what stops the lantern reading as a graphics primitive. A hard
 * cone with nothing around it looks like a stencil; real light leaks sideways
 * off whatever the beam is hitting, so a dim wash around the beam is the single
 * cheapest thing that makes it look like illumination instead of a mask.
 *
 * Two more details in the same spirit. The beam's reach WOBBLES with the angle
 * (a couple of low harmonics), so its edge is slightly irregular rather than
 * geometric; and the whole lantern FLICKERS a few percent on a slow, per-player
 * noise. Both are small enough that you cannot point at them, which is the
 * intent — an effect you notice is an effect that is too strong.
 *
 * The beam also LAGS the aim. Your arm does not teleport, so the light swings
 * toward the cursor and settles, which turns mouse movement into motion in the
 * world instead of an instant state change.
 *
 * All of it is occluded: sight is traced with recursive shadowcasting over the
 * tile grid, so a thicket throws a real shadow and a zombie can genuinely be
 * hidden behind one. Radius, reach and cone width come from `welcome.config`.
 *
 * Team vision is the per-tile maximum across every living player, local and
 * remote alike. `explored` is the memory of that — once anyone has seen a tile
 * it stays dimly readable forever, which is what makes the map worth exploring
 * instead of a torch-lit tunnel.
 *
 * Cost: 8 octants of a bounded flood per viewer. At the default 11-tile reach
 * that is a few hundred tiles each, so it runs every frame with no caching and
 * no staleness to reason about.
 */

import { clamp01, expDamp } from '../lib/math';
import type { TileMap } from '../game/world';

/** Anything a light can be attached to. Aim must be normalized. */
export interface Viewer {
  /** Stable per-player, so the beam's lag and flicker follow the right light. */
  id: string;
  x: number;
  y: number;
  ax: number;
  ay: number;
  /**
   * 0..1 lantern output — the battery, the blink and the switch, collapsed into
   * one number (see `game/lantern.ts`). 0 leaves this viewer with nothing but
   * the cold ambient glow. Remotes pass 0 or 1 from the snapshot switch.
   */
  lantern: number;
}

/**
 * A light that is part of the WORLD rather than carried by somebody: the
 * bonfire in the camp, and whatever else gets planted in a level later.
 *
 * It is not a `Viewer` with the aim fields zeroed. A viewer's light is shaped
 * by where they are looking and dimmed by their battery; a fire has neither, it
 * is omnidirectional, always at full power, and WARM — the camp is lit by fire
 * and has to read that way, not as a lantern somebody left on the ground.
 *
 * Occlusion is the same shadowcast, so the trees around the clearing still
 * throw real shadows across it.
 */
export interface LightSource {
  /** Stable per light, so its flicker does not walk when the list re-orders. */
  id: number;
  x: number;
  y: number;
  /** Omnidirectional reach, in tiles. */
  radiusTiles: number;
}

export interface VisionConfig {
  ambientTiles: number;
  lanternTiles: number;
  coneDegrees: number;
}

/** Light at or above this counts as "seen" and is committed to memory. */
const EXPLORE_THRESHOLD = 0.12;
/** Fraction of the ambient radius that stays at full brightness. */
const AMBIENT_CORE = 0.55;
/**
 * How much of the ambient glow survives with the lantern switched off. Small on
 * purpose: ambient is omnidirectional, so it is the one thing that can still
 * light an enemy standing behind you, and a wide dark ambient would undo the
 * naked-eye cone. At this radius the bubble is arm's reach — something touching
 * you is not something you can fail to notice.
 */
const AMBIENT_DARK = 0.45;

/**
 * SIGHT: a nearly-invisible wash over what the viewer has line of sight to,
 * lantern or no lantern, out to `lanternTiles * SIGHT_REACH`.
 *
 * Without it the beam is a hard question — anything outside the cone does not
 * exist, so a zombie two tiles to your left is *nothing* until you sweep over
 * it. That is not what being in a dark forest is like. This is the shape you
 * half-see: enemies standing in it are drawn, but at a fraction of their alpha,
 * so you get a silhouette you are not sure about rather than an empty screen.
 *
 * It is kept below EXPLORE_THRESHOLD on purpose. Half-seeing a tile must not
 * commit it to the explored map — that is what pointing the lantern at it is
 * for.
 *
 * With the lamp ON the wash is omnidirectional — the lantern is doing the
 * pointing, and the beam is the thing the player aims. With the lamp OFF it
 * collapses to the NAKED-EYE cone below: a wide, short, low-opacity wedge along
 * the aim. That cone is the whole answer to "what can I see in the dark" — a
 * shape you half-make-out inside it, and nothing at all outside it. Being
 * flanked in the dark is then a real thing that can happen to you, which is
 * what the lamp costs battery to prevent.
 */
const SIGHT_GAIN = 0.085;
const SIGHT_REACH = 1;
/**
 * Naked-eye cone with the lamp off: full width, and reach vs the beam's.
 *
 * `EYE_REACH` and `SIGHT_REACH` are mirrored by `ENEMY_VIEW_DARK_SCALE` and
 * `ENEMY_VIEW_LIT_SCALE` in `server/app/config.py`, which is what makes sight
 * symmetric: an enemy sees a shape exactly as far as the shape sees it, and a
 * lit player exactly as far as the lamp reaches. Move one of these and move
 * the other, or the cones the client draws stop matching the rule the server
 * is enforcing.
 */
const EYE_CONE_DEGREES = 110;
const EYE_REACH = 0.62;
/** How much of the eye cone's half-angle is spent softening its edge. */
const EYE_SOFTNESS = 0.5;
const EYE_COS = Math.cos((EYE_CONE_DEGREES * Math.PI) / 360);
const EYE_EDGE = EYE_COS + (1 - EYE_COS) * EYE_SOFTNESS;
/** Beam reach with a dying battery, as a fraction of its reach at full output. */
const BEAM_FLOOR = 0.55;

/**
 * Warmth constants. `heat` = light x warmth x (base + near-field bonus), so a
 * tile's amber is the product of "can I see it", "is the lamp on" and "how
 * close is it".
 */
/** Warmth of ambient light with the lantern off — moon, not flame. */
const HEAT_COLD = 0.25;
/** Warmth every lit tile gets regardless of range. */
const HEAT_BASE = 0.62;
/**
 * Extra warmth at the lamp itself, on top of HEAT_BASE. Deliberately small: the
 * near field only has to be *warmer* than the far end of the beam, and a big
 * value stops reading as brightness and starts reading as a bright disc drawn
 * around the player.
 */
const HEAT_NEAR = 0.42;
/**
 * The hearth — the pool of spilled light around the lamp. It falls off from the
 * very centre (no flat core) precisely so that it has no edge to see.
 */
const HEARTH_SPAN = 1.6;
const HEARTH_BEAM = 0.42;
/** Fraction of the lantern reach that stays at full brightness. */
const LANTERN_CORE = 0.3;
/** How much of the cone's half-angle is spent softening its edge. */
const CONE_SOFTNESS = 0.45;
/** The lantern never quite matches the glow you are standing in. */
const LANTERN_GAIN = 0.95;

/** How fast the beam catches up to the aim. Higher = tighter, less lag. */
const AIM_FOLLOW_RATE = 9;
/** Spill: how wide the halo is relative to the beam, and how far/bright. */
const SPILL_WIDTH = 2.6;
const SPILL_REACH = 0.5;
const SPILL_GAIN = 0.42;
/** Flicker depth on the beam's reach and brightness (fractions of 1). */
const FLICKER_REACH = 0.05;
const FLICKER_GAIN = 0.07;
/** Depth of the two harmonics that make the beam's edge irregular. */
const WOBBLE_A = 0.055;
const WOBBLE_B = 0.035;

/**
 * A bonfire's light. Brighter and much warmer than a lantern's — standing at
 * the hearth is the warmest the game gets, and it is the reference the lantern
 * is deliberately measured against (see LANTERN_GAIN).
 */
const FIRE_CORE = 0.34;
const FIRE_GAIN = 1;
const FIRE_WARMTH = 1.25;
/** Fraction of the reach that stays at full warmth around the flame. */
const FIRE_HEARTH = 0.42;
/** How much of the fire's reach and brightness the flicker moves. */
const FIRE_FLICKER_REACH = 0.06;
const FIRE_FLICKER_GAIN = 0.1;

/**
 * 0..1 flame brightness for fire `index` at `time`.
 *
 * Three sines with no common period, so the fire never repeats a beat — that
 * is the whole difference between "burning" and "animated". Exported because
 * the additive glow the darkness layer paints has to breathe on exactly the
 * same curve as the light this file writes; two fires flickering out of phase
 * on the same log reads as a bug.
 */
export function fireFlicker(time: number, index = 0): number {
  const phase = index * 1.7;
  return clamp01(
    0.78 +
      Math.sin(time * 7.3 + phase) * 0.1 +
      Math.sin(time * 13.1 + 1.7 + phase) * 0.07 +
      Math.sin(time * 2.9 + 0.4 + phase) * 0.08,
  );
}

interface Lag {
  ax: number;
  ay: number;
}

export class FovField {
  readonly width: number;
  readonly height: number;
  /** 0..1 current light per tile. Rebuilt every update. */
  readonly light: Float32Array;
  /** Warmth per tile, 0..~1.8. Unbounded on purpose — see the header. */
  readonly heat: Float32Array;
  /** 1 once anyone has ever seen this tile. Never cleared. */
  readonly explored: Uint8Array;

  /**
   * The tile rectangle a consumer has to repaint, in tiles, inclusive.
   *
   * Light only exists within a light's own radius, so everything outside this
   * box holds exactly the values it held last frame — including the fog, since
   * `explored` can only flip somewhere that is currently lit. It is the union
   * of this update's lit boxes with the PREVIOUS one, because a tile that just
   * fell dark has changed too. Whoever caches pixels per tile (see
   * `layers/darkness`) rebuilds this and leaves the rest of the map alone.
   */
  readonly dirty = { x0: 0, y0: 0, x1: 0, y1: 0 };
  /** Lit box of the update in progress; empty until something shines. */
  private readonly written = { x0: 0, y0: 0, x1: -1, y1: -1 };
  private readonly previous = { x0: 0, y0: 0, x1: -1, y1: -1 };

  /** Per-player beam direction, trailing the aim it is chasing. */
  private readonly lag = new Map<string, Lag>();

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.light = new Float32Array(width * height);
    this.heat = new Float32Array(width * height);
    this.explored = new Uint8Array(width * height);
    this.dirtyAll();
  }

  lightAt(tx: number, ty: number): number {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return 0;
    return this.light[ty * this.width + tx];
  }

  isExplored(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return false;
    return this.explored[ty * this.width + tx] === 1;
  }

  /** Recompute team light from scratch, then fold it into the explored memory. */
  update(
    world: TileMap,
    viewers: readonly Viewer[],
    lights: readonly LightSource[],
    config: VisionConfig,
    time: number,
    dt: number,
  ): void {
    this.light.fill(0);
    this.heat.fill(0);
    this.pruneLag(viewers);
    this.written.x1 = -1;

    const ts = world.tileSize;
    const cosHalf = Math.cos((config.coneDegrees * Math.PI) / 360);
    // The spill is a much wider cone; past 180° it is simply omnidirectional.
    const cosSpill = Math.cos(
      Math.min(Math.PI, (config.coneDegrees * SPILL_WIDTH * Math.PI) / 360),
    );
    const softEdge = cosHalf + (1 - cosHalf) * CONE_SOFTNESS;
    const spillEdge = cosSpill + (1 - cosSpill) * CONE_SOFTNESS;

    for (const viewer of viewers) {
      const aim = this.trackAim(viewer, dt);
      // Two incommensurate sines: a repeat you can count is a repeat you see.
      const seed = hashId(viewer.id);
      const flicker =
        Math.sin(time * 2.7 + seed) * 0.6 + Math.sin(time * 6.1 + seed * 2.3) * 0.4;
      // A dying lantern throws a shorter, weaker cone; a dead one throws none
      // at all, and the beam maths is skipped rather than multiplied by zero.
      const power = clamp01(viewer.lantern);
      const beamReach =
        power > 0
          ? config.lanternTiles *
            (1 + flicker * FLICKER_REACH) *
            (BEAM_FLOOR + (1 - BEAM_FLOOR) * power)
          : 0;
      const beamGain = LANTERN_GAIN * (1 + flicker * FLICKER_GAIN) * power;
      const spillReach = beamReach * SPILL_REACH;
      // Your eyes still work in the dark; the lantern only widens the pool.
      const ambientTiles = config.ambientTiles * (AMBIENT_DARK + (1 - AMBIENT_DARK) * power);
      const hearth = Math.max(ambientTiles * HEARTH_SPAN, beamReach * HEARTH_BEAM);
      const warmth = HEAT_COLD + power * (1 - HEAT_COLD);
      // With the lamp off, sight is the naked eye: shorter, and a cone rather
      // than a full circle. Both open back up as the lamp comes on, so a
      // stutter or a dropout closes the world in around you instead of
      // switching between two unrelated vision models.
      const sight = config.lanternTiles * (EYE_REACH + (SIGHT_REACH - EYE_REACH) * power);
      const outer = Math.max(ambientTiles, beamReach, sight);
      const radius = Math.ceil(outer);

      const ox = viewer.x / ts;
      const oy = viewer.y / ts;
      const cx = Math.floor(ox);
      const cy = Math.floor(oy);

      const shine = (tx: number, ty: number): void => {
        if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return;
        // Tile centres, so a tile is lit by where it is rather than its corner.
        const dx = tx + 0.5 - ox;
        const dy = ty + 0.5 - oy;
        const dist = Math.hypot(dx, dy);
        if (dist > outer) return;

        let value: number;
        if (dist <= 1e-4) {
          value = 1;
        } else {
          const alignment = (dx * aim.ax + dy * aim.ay) / dist;
          // Blend the mask, not the angle: interpolating the cone's cosine
          // toward -1 leaves a soft edge behind the player that never closes.
          const eyes =
            smoothstep(EYE_COS, EYE_EDGE, alignment) * (1 - power) + power;

          value = Math.max(
            falloff(dist, ambientTiles, AMBIENT_CORE),
            falloff(dist, sight, 0) * SIGHT_GAIN * eyes,
          );

          if (beamGain > 0 && alignment > cosSpill) {
            // Angle around the beam, used to ripple its reach. Cheap harmonics
            // beat noise here: they are continuous, so the edge undulates
            // instead of shimmering frame to frame.
            const angle = Math.atan2(dy, dx);
            const wobble =
              1 +
              Math.sin(angle * 3 + seed) * WOBBLE_A +
              Math.sin(angle * 7 - seed * 1.7) * WOBBLE_B;

            if (alignment > cosHalf) {
              const angular = softEdge > cosHalf ? smoothstep(cosHalf, softEdge, alignment) : 1;
              const radial = falloff(dist, beamReach * wobble, LANTERN_CORE);
              value = Math.max(value, angular * radial * beamGain);
            }
            const spillAngular =
              spillEdge > cosSpill ? smoothstep(cosSpill, spillEdge, alignment) : 1;
            const spillRadial = falloff(dist, spillReach * wobble, LANTERN_CORE);
            value = Math.max(value, spillAngular * spillRadial * SPILL_GAIN);
          }
        }
        if (value <= 0) return;

        const index = ty * this.width + tx;
        if (value > this.light[index]) this.light[index] = value;
        // Committed here rather than in a pass over the whole field afterwards:
        // final light is the max of every value written, so any single write
        // over the threshold already means the tile was seen.
        if (value >= EXPLORE_THRESHOLD) this.explored[index] = 1;

        // Warmth. `light` has already saturated at 1 by the time you are a
        // couple of tiles from the lamp, so without this second term walking
        // right up to something would not make it any brighter.
        const heat = value * warmth * (HEAT_BASE + falloff(dist, hearth, 0) * HEAT_NEAR);
        if (heat > this.heat[index]) this.heat[index] = heat;
      };

      this.markLit(cx, cy, radius);
      shine(cx, cy);
      for (let octant = 0; octant < 8; octant++) {
        castLight(world, cx, cy, 1, 1, 0, radius, OCTANTS[octant], shine);
      }
    }

    this.burn(world, lights, time);
    this.publishDirty();
  }

  /**
   * Fold the world's own lights in on top of the team's.
   *
   * A second, much simpler loop rather than a branch inside the viewer pass: a
   * fire has no aim, no cone, no spill and no battery, so everything that makes
   * the viewer path complicated is dead weight here. Same `max()` merge, same
   * shadowcast, so a fire and a lantern lighting the same tile agree about it.
   *
   * IT LIGHTS, AND IT DOES NOT EXPLORE. That single omission is the rule the
   * whole night runs on: only what the PARTY has seen counts as seen. A light
   * the party did not carry there — a torch beside an extraction console, the
   * merchant's lamps — makes its own pool visible while you are looking at it
   * and leaves no permanent mark on the map or the minimap. Otherwise every
   * fixed light on the level would quietly hand over the ground around it
   * before anybody had spent a step finding out what was on it, and the
   * darkness is the only real inventory of tension this game has.
   */
  private burn(world: TileMap, lights: readonly LightSource[], time: number): void {
    if (lights.length === 0) return;
    const ts = world.tileSize;

    for (const light of lights) {
      const flicker = fireFlicker(time, light.id);
      const reach = light.radiusTiles * (1 - FIRE_FLICKER_REACH + flicker * FIRE_FLICKER_REACH);
      const gain = FIRE_GAIN * (1 - FIRE_FLICKER_GAIN + flicker * FIRE_FLICKER_GAIN);
      const hearth = reach * FIRE_HEARTH;
      const radius = Math.ceil(reach);

      const ox = light.x / ts;
      const oy = light.y / ts;
      const cx = Math.floor(ox);
      const cy = Math.floor(oy);

      const shine = (tx: number, ty: number): void => {
        if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return;
        const dx = tx + 0.5 - ox;
        const dy = ty + 0.5 - oy;
        const dist = Math.hypot(dx, dy);
        if (dist > reach) return;

        const value = falloff(dist, reach, FIRE_CORE) * gain;
        if (value <= 0) return;

        const index = ty * this.width + tx;
        if (value > this.light[index]) this.light[index] = value;

        const heat =
          value * FIRE_WARMTH * (HEAT_BASE + falloff(dist, hearth, 0) * HEAT_NEAR);
        if (heat > this.heat[index]) this.heat[index] = heat;
      };

      this.markLit(cx, cy, radius);
      shine(cx, cy);
      for (let octant = 0; octant < 8; octant++) {
        castLight(world, cx, cy, 1, 1, 0, radius, OCTANTS[octant], shine);
      }
    }
  }

  /** Forget everything. Called on a new map. */
  clear(): void {
    this.light.fill(0);
    this.heat.fill(0);
    this.explored.fill(0);
    this.lag.clear();
    this.dirtyAll();
  }

  /** Grow this update's lit box to cover one light at (cx, cy). */
  private markLit(cx: number, cy: number, radius: number): void {
    const box = this.written;
    if (box.x1 < box.x0) {
      box.x0 = cx - radius;
      box.y0 = cy - radius;
      box.x1 = cx + radius;
      box.y1 = cy + radius;
      return;
    }
    if (cx - radius < box.x0) box.x0 = cx - radius;
    if (cy - radius < box.y0) box.y0 = cy - radius;
    if (cx + radius > box.x1) box.x1 = cx + radius;
    if (cy + radius > box.y1) box.y1 = cy + radius;
  }

  /** Union this update's box with the last one, clamped to the map. */
  private publishDirty(): void {
    const now = this.written;
    const before = this.previous;
    const empty = now.x1 < now.x0;
    const x0 = empty ? before.x0 : Math.min(now.x0, before.x0);
    const y0 = empty ? before.y0 : Math.min(now.y0, before.y0);
    const x1 = empty ? before.x1 : Math.max(now.x1, before.x1);
    const y1 = empty ? before.y1 : Math.max(now.y1, before.y1);

    this.dirty.x0 = Math.max(0, x0);
    this.dirty.y0 = Math.max(0, y0);
    this.dirty.x1 = Math.min(this.width - 1, x1);
    this.dirty.y1 = Math.min(this.height - 1, y1);

    before.x0 = now.x0;
    before.y0 = now.y0;
    before.x1 = now.x1;
    before.y1 = now.y1;
  }

  /** Mark the whole field dirty — a new map, or a field nobody has drawn yet. */
  private dirtyAll(): void {
    this.dirty.x0 = 0;
    this.dirty.y0 = 0;
    this.dirty.x1 = this.width - 1;
    this.dirty.y1 = this.height - 1;
    this.previous.x0 = 0;
    this.previous.y0 = 0;
    this.previous.x1 = this.width - 1;
    this.previous.y1 = this.height - 1;
  }

  /** Ease this viewer's beam toward its aim and return where it points now. */
  private trackAim(viewer: Viewer, dt: number): Lag {
    const current = this.lag.get(viewer.id);
    if (!current) {
      const fresh = { ax: viewer.ax, ay: viewer.ay };
      this.lag.set(viewer.id, fresh);
      return fresh;
    }
    const k = 1 - expDamp(AIM_FOLLOW_RATE, dt);
    current.ax += (viewer.ax - current.ax) * k;
    current.ay += (viewer.ay - current.ay) * k;
    // Renormalize: lerping two unit vectors shortens the result, and a short
    // aim vector would quietly widen the cone as it swings.
    const length = Math.hypot(current.ax, current.ay);
    if (length > 1e-4) {
      current.ax /= length;
      current.ay /= length;
    } else {
      current.ax = viewer.ax;
      current.ay = viewer.ay;
    }
    return current;
  }

  /** Drop lag state for players who left, so the map cannot grow forever. */
  private pruneLag(viewers: readonly Viewer[]): void {
    if (this.lag.size === viewers.length) return;
    const live = new Set(viewers.map((v) => v.id));
    for (const id of this.lag.keys()) {
      if (!live.has(id)) this.lag.delete(id);
    }
  }
}

/** Stable pseudo-random phase per player, so two lanterns never flicker alike. */
function hashId(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) / 4294967295) * Math.PI * 2;
}

/** 1 in the core, easing to 0 at `radius`. */
function falloff(dist: number, radius: number, core: number): number {
  if (dist >= radius) return 0;
  const inner = radius * core;
  if (dist <= inner) return 1;
  return 1 - smoothstep(inner, radius, dist);
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/**
 * The eight symmetry transforms of one octant: [xx, xy, yx, yy]. Scanning a
 * single octant and mapping it through these is what keeps the shadowcast to
 * one loop instead of eight near-identical ones.
 */
const OCTANTS: ReadonlyArray<readonly [number, number, number, number]> = [
  [1, 0, 0, 1],
  [0, 1, 1, 0],
  [0, -1, 1, 0],
  [-1, 0, 0, 1],
  [-1, 0, 0, -1],
  [0, -1, -1, 0],
  [0, 1, -1, 0],
  [1, 0, 0, -1],
];

/**
 * Recursive shadowcasting over one octant.
 *
 * Walks outward row by row inside a slope wedge. A blocker narrows the wedge:
 * the scan recurses into the still-visible part to its side and continues past
 * it with a tighter start slope, which is what produces a real shadow with a
 * penumbra-free edge — the standard roguelike algorithm, on floats.
 *
 * Occlusion is `blocksSight`, not `isSolidTile`: see world.ts for why a
 * campfire, the camp exit and waist-high cover block a body but not a beam.
 */
function castLight(
  world: TileMap,
  cx: number,
  cy: number,
  row: number,
  startSlope: number,
  endSlope: number,
  radius: number,
  [xx, xy, yx, yy]: readonly [number, number, number, number],
  shine: (tx: number, ty: number) => void,
): void {
  if (startSlope < endSlope) return;

  let nextStart = startSlope;
  for (let distance = row; distance <= radius; distance++) {
    let blocked = false;
    for (let deltaX = -distance, deltaY = -distance; deltaX <= 0; deltaX++) {
      const tx = cx + deltaX * xx + deltaY * xy;
      const ty = cy + deltaX * yx + deltaY * yy;
      const leftSlope = (deltaX - 0.5) / (deltaY + 0.5);
      const rightSlope = (deltaX + 0.5) / (deltaY - 0.5);

      if (rightSlope > nextStart) continue;
      if (leftSlope < endSlope) break;

      shine(tx, ty);

      const solid = world.blocksSight(tx, ty);
      if (blocked) {
        if (solid) {
          nextStart = rightSlope;
        } else {
          blocked = false;
          startSlope = nextStart;
        }
      } else if (solid && distance < radius) {
        // Step into the gap beside this blocker, then carry on with the wedge
        // narrowed to whatever is left of it.
        blocked = true;
        castLight(
          world,
          cx,
          cy,
          distance + 1,
          startSlope,
          leftSlope,
          radius,
          [xx, xy, yx, yy],
          shine,
        );
        nextStart = rightSlope;
      }
    }
    if (blocked) break;
  }
}
