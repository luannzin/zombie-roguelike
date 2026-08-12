/**
 * Shared field of view: who can see what, and how brightly.
 *
 * This is a VISUAL system. The server keeps broadcasting the whole world and
 * this decides what the player is allowed to make out — no snapshot culling, no
 * netcode change, and shared vision is a `max()` instead of a per-viewer
 * subscription set. In a co-op PvE game the trade is free: the only thing a
 * modified client gains by ignoring the dark is spoiling its own tension.
 *
 * Two lights per viewer, and the brighter one wins on each tile:
 *
 *   ambient   a small omnidirectional glow, so you can always see your feet
 *   lantern   a cone along your aim, reaching much further
 *
 * Both are occluded: sight is traced with recursive shadowcasting over the tile
 * grid, so a thicket throws a real shadow and a zombie can genuinely be hidden
 * behind one. Radius, reach and cone width all come from `welcome.config`.
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

import type { TileMap } from '../game/world';

/** Anything a light can be attached to. Aim must be normalized. */
export interface Viewer {
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

export class FovField {
  readonly width: number;
  readonly height: number;
  /** 0..1 current light per tile. Rebuilt every update. */
  readonly light: Float32Array;
  /** 1 once anyone has ever seen this tile. Never cleared. */
  readonly explored: Uint8Array;

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
  update(world: TileMap, viewers: readonly Viewer[], config: VisionConfig): void {
    this.light.fill(0);

    const ts = world.tileSize;
    const reach = Math.max(config.ambientTiles, config.lanternTiles);
    const radius = Math.ceil(reach);
    const cosHalf = Math.cos((config.coneDegrees * Math.PI) / 360);

    for (const viewer of viewers) {
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
        if (dist > reach) return;

        let value = falloff(dist, config.ambientTiles, AMBIENT_CORE);
        if (dist > 1e-4) {
          const alignment = (dx * viewer.ax + dy * viewer.ay) / dist;
          if (alignment > cosHalf) {
            const edge = cosHalf + (1 - cosHalf) * CONE_SOFTNESS;
            const angular = edge > cosHalf ? smoothstep(cosHalf, edge, alignment) : 1;
            const radial = falloff(dist, config.lanternTiles, LANTERN_CORE);
            value = Math.max(value, angular * radial * LANTERN_GAIN);
          }
        } else {
          value = 1;
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
  }
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
