/**
 * Shared field of view: who can see what, and how brightly.
 *
 * This is a VISUAL system. The server keeps broadcasting the whole world and
 * this decides what the player is allowed to make out — no snapshot culling, no
 * netcode change, and shared vision is a `max()` instead of a per-viewer
 * subscription set. In a co-op PvE game the trade is free: the only thing a
 * modified client gains by ignoring the dark is spoiling its own tension.
 *
 * Three lights per viewer, and the brightest one wins on each tile:
 *
 *   ambient   a small omnidirectional glow, so you can always see your feet
 *   beam      a cone along your aim, reaching much further
 *   spill     a wide, weak, short halo around the beam
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

import { expDamp } from '../lib/math';
import type { TileMap } from '../game/world';

/** Anything a light can be attached to. Aim must be normalized. */
export interface Viewer {
  /** Stable per-player, so the beam's lag and flicker follow the right light. */
  id: string;
  x: number;
  y: number;
  ax: number;
  ay: number;
}

export interface VisionConfig {
  ambientTiles: number;
  lanternTiles: number;
  coneDegrees: number;
}

/** Light at or above this counts as "seen" and is committed to memory. */
const EXPLORE_THRESHOLD = 0.12;
/** Fraction of the ambient radius that stays at full brightness. */
const AMBIENT_CORE = 0.45;
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

interface Lag {
  ax: number;
  ay: number;
}

export class FovField {
  readonly width: number;
  readonly height: number;
  /** 0..1 current light per tile. Rebuilt every update. */
  readonly light: Float32Array;
  /** 1 once anyone has ever seen this tile. Never cleared. */
  readonly explored: Uint8Array;

  /** Per-player beam direction, trailing the aim it is chasing. */
  private readonly lag = new Map<string, Lag>();

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.light = new Float32Array(width * height);
    this.explored = new Uint8Array(width * height);
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
    config: VisionConfig,
    time: number,
    dt: number,
  ): void {
    this.light.fill(0);
    this.pruneLag(viewers);

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
      const beamReach = config.lanternTiles * (1 + flicker * FLICKER_REACH);
      const beamGain = LANTERN_GAIN * (1 + flicker * FLICKER_GAIN);
      const spillReach = beamReach * SPILL_REACH;
      const outer = Math.max(config.ambientTiles, beamReach);
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
          value = falloff(dist, config.ambientTiles, AMBIENT_CORE);
          const alignment = (dx * aim.ax + dy * aim.ay) / dist;

          if (alignment > cosSpill) {
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
      };

      shine(cx, cy);
      for (let octant = 0; octant < 8; octant++) {
        castLight(world, cx, cy, 1, 1, 0, radius, OCTANTS[octant], shine);
      }
    }

    for (let i = 0; i < this.light.length; i++) {
      if (this.light[i] >= EXPLORE_THRESHOLD) this.explored[i] = 1;
    }
  }

  /** Forget everything. Called on a new map. */
  clear(): void {
    this.light.fill(0);
    this.explored.fill(0);
    this.lag.clear();
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

      const solid = world.isSolidTile(tx, ty);
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
