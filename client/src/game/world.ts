/**
 * Client-side tile map. Mirror of server/app/world.py.
 *
 * `moveAxis` MUST stay numerically identical to the Python version, otherwise
 * client prediction and the server disagree near walls and the local player
 * rubber-bands. VOID is solid like a tree — the camp exit is a shadowed
 * winding path in the woods, not a hole in the ground.
 */

import type { MapPayload } from '../net/protocol';

/** Tile kinds. Mirror of server/app/world.py. */
export const FLOOR = 0;
export const ROCK = 1;
export const TREE = 2;
export const FIRE = 3;
/** Solid gap in the trees. Painted as floor, blocks bodies, not light. */
export const VOID = 4;
/**
 * Solid footprint of a BUILDING from a placed scene. Painted as floor and
 * drawn with nothing: the cabin or tent sprite in `TileMap.scenery` covers it.
 * Blocks light too — a cabin is a cabin.
 */
export const PROP = 5;
/**
 * Waist-high cover: a fallen log, a crate, a fence rail, a signpost.
 * Solid to bodies and bullets, transparent to light. Making these PROP would
 * put a hard shadow wedge behind every crate; leaving them walkable throws
 * away the best cover the forest has.
 */
export const LOW = 6;

/** Legacy alias: '#' in a hand-drawn ASCII map is a rock. */
export const WALL = ROCK;

const EPS = 1e-4;

/** A bonfire, at the BASE of its flame in world pixels — where the sprite sits. */
export interface FirePlace {
  x: number;
  y: number;
}

/**
 * One placed scenery piece, unpacked from the wire's compact row.
 *
 * `y` is a contact point for a standing piece and a centre for a flat one,
 * which is the same split `render/scenery.ts` draws on. The two lists are kept
 * apart here rather than filtered per frame: `standing` is merged into the
 * entity depth sort every frame and `flat` is baked once, so sorting them into
 * one array would cost a scan of the whole map's scenery sixty times a second.
 */
export interface SceneryPiece {
  kind: string;
  x: number;
  y: number;
  variant: number;
  flip: boolean;
}

/** A light the map owns, at the point it burns from, in world pixels. */
export interface SceneryLight {
  x: number;
  y: number;
  radiusTiles: number;
  /** 0 lamp, 1 ember, 2 beacon — see `theme/palette.ts` `scene`. */
  kind: number;
}

export interface Scenery {
  /** Flat on the floor, baked into the ground canvas. */
  flat: readonly SceneryPiece[];
  /** Stands up, depth-sorted with the party. Sorted by `y` at parse time. */
  standing: readonly SceneryPiece[];
  /**
   * Still burning. Fed to `FovField` exactly like a bonfire is — the map does
   * not distinguish between a light the camp owns and a light a dead
   * homestead owns, and neither should the lighting.
   */
  lights: readonly SceneryLight[];
}

export class TileMap {
  readonly tiles: number[][];
  readonly width: number;
  readonly height: number;
  readonly tileSize: number;
  readonly pixelWidth: number;
  readonly pixelHeight: number;
  /** Generator seed — hashed with tile coords to place decoration. */
  readonly seed: number;
  /**
   * Every FIRE tile, resolved once. A fire is three things — a blocker, a
   * sprite and a light — and all three read this list, so the map is the only
   * place any of them is written down.
   */
  readonly fires: readonly FirePlace[];
  /**
   * Mouth of the camp exit — west-most VOID tile centre — or null on a map
   * without one (the forest). Resolved with the fires rather than on demand:
   * the walk-out camera asks for it every frame, and it cannot move.
   */
  readonly exit: { x: number; y: number } | null;
  /**
   * The scenes the server laid over this map, split by how they are drawn.
   * Empty on a locally generated map — the title screen's clearing has no
   * story in it, because nobody is standing in it to read one.
   */
  readonly scenery: Scenery;

  constructor(payload: MapPayload) {
    this.tiles = payload.tiles;
    this.width = payload.width;
    this.height = payload.height;
    this.tileSize = payload.tileSize;
    this.seed = payload.seed ?? 0;
    this.pixelWidth = this.width * this.tileSize;
    this.pixelHeight = this.height * this.tileSize;
    this.fires = findFires(this.tiles, this.tileSize);
    this.exit = findExitMouth(this.tiles, this.tileSize);
    this.scenery = unpackScenery(payload);
  }

  /**
   * Anything that is not floor blocks movement and shots. Testing for
   * "not floor" rather than a list of known blockers is what lets the server
   * add a tile kind without touching collision on either side. Sight is
   * `blocksSight` — a fire, the camp exit and waist-high cover stop a body
   * but not a beam.
   */
  isSolidTile(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return true;
    return this.tiles[ty][tx] !== FLOOR;
  }

  /**
   * Whether this tile stops LIGHT. Narrower than solidity, and the difference
   * is not cosmetic: the server enforces exactly this, so a log you can see
   * over has to be a log an enemy can see over. Three exceptions — a bonfire
   * is knee-high and is the light source, VOID is a gap between trunks that
   * light falls into, and LOW is cover you look over.
   */
  blocksSight(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return true;
    const tile = this.tiles[ty][tx];
    return tile !== FLOOR && tile !== FIRE && tile !== VOID && tile !== LOW;
  }

  /** Axis-aligned box centred on (cx, cy) with half-extents (hw, hh). */
  boxBlocked(cx: number, cy: number, hw: number, hh: number): boolean {
    const ts = this.tileSize;
    const x0 = Math.floor((cx - hw) / ts);
    const x1 = Math.floor((cx + hw) / ts);
    const y0 = Math.floor((cy - hh) / ts);
    const y1 = Math.floor((cy + hh) / ts);
    for (let ty = y0; ty <= y1; ty++) {
      for (let tx = x0; tx <= x1; tx++) {
        if (this.isSolidTile(tx, ty)) return true;
      }
    }
    return false;
  }

  /** axis: 0 = x, 1 = y. Returns the new coordinate on that axis. */
  moveAxis(
    x: number,
    y: number,
    hw: number,
    hh: number,
    delta: number,
    axis: 0 | 1,
  ): number {
    const ts = this.tileSize;
    if (delta === 0) return axis === 0 ? x : y;

    if (axis === 0) {
      const nx = x + delta;
      if (!this.boxBlocked(nx, y, hw, hh)) return nx;
      if (delta > 0) {
        const col = Math.floor((nx + hw) / ts);
        return col * ts - hw - EPS;
      }
      const col = Math.floor((nx - hw) / ts);
      return (col + 1) * ts + hw + EPS;
    }

    const ny = y + delta;
    if (!this.boxBlocked(x, ny, hw, hh)) return ny;
    if (delta > 0) {
      const row = Math.floor((ny + hh) / ts);
      return row * ts - hh - EPS;
    }
    const row = Math.floor((ny - hh) / ts);
    return (row + 1) * ts + hh + EPS;
  }

  /**
   * DDA ray march. Used for local shot tracers.
   *
   * `sight` asks what stops LIGHT instead of what stops a body — see
   * `blocksSight`. One traversal serves both because the walk is identical
   * and only the predicate differs; two copies of this loop would drift.
   */
  raycastTiles(
    ox: number,
    oy: number,
    dx: number,
    dy: number,
    maxDist: number,
    sight = false,
  ): number {
    const blocked = sight
      ? (tx: number, ty: number) => this.blocksSight(tx, ty)
      : (tx: number, ty: number) => this.isSolidTile(tx, ty);
    const ts = this.tileSize;
    let tx = Math.floor(ox / ts);
    let ty = Math.floor(oy / ts);
    if (blocked(tx, ty)) return 0;

    const stepX = dx > 0 ? 1 : -1;
    const stepY = dy > 0 ? 1 : -1;
    const invDx = dx === 0 ? Infinity : Math.abs(1 / dx);
    const invDy = dy === 0 ? Infinity : Math.abs(1 / dy);

    let tMaxX =
      dx > 0 ? ((tx + 1) * ts - ox) * invDx : dx < 0 ? (ox - tx * ts) * invDx : Infinity;
    let tMaxY =
      dy > 0 ? ((ty + 1) * ts - oy) * invDy : dy < 0 ? (oy - ty * ts) * invDy : Infinity;

    const tDeltaX = ts * invDx;
    const tDeltaY = ts * invDy;

    let travelled = 0;
    while (travelled <= maxDist) {
      if (tMaxX < tMaxY) {
        travelled = tMaxX;
        tx += stepX;
        tMaxX += tDeltaX;
      } else {
        travelled = tMaxY;
        ty += stepY;
        tMaxY += tDeltaY;
      }
      if (travelled > maxDist) break;
      if (blocked(tx, ty)) return travelled;
    }
    return maxDist;
  }
}

/**
 * Unpack the map payload's scenery rows into the two lists that get drawn.
 *
 * `standing` is sorted by `y` here, once, because the renderer merges it into
 * the entity depth order every frame the way it already merges the bonfires —
 * that merge is a walk of two ascending lists, and it only works if this one
 * is ascending.
 */
function unpackScenery(payload: MapPayload): Scenery {
  const kinds = payload.propKinds ?? [];
  const rows = payload.props ?? [];
  const flat: SceneryPiece[] = [];
  const standing: SceneryPiece[] = [];

  for (const [kind, x, y, variant, flip, layer] of rows) {
    const name = kinds[kind];
    if (name === undefined) continue;
    (layer === 0 ? flat : standing).push({ kind: name, x, y, variant, flip: flip !== 0 });
  }
  standing.sort((a, b) => a.y - b.y);

  const lights: SceneryLight[] = (payload.lights ?? []).map(
    ([x, y, radiusTiles, kind]) => ({ x, y, radiusTiles, kind }),
  );
  return { flat, standing, lights };
}

/**
 * Bottom-centre of every FIRE tile, in world pixels.
 *
 * Bottom-centre because that is where a prop is anchored and where the light
 * comes from — mirrors `TileMap.fire_points` in server/app/world.py.
 */
function findFires(tiles: number[][], tileSize: number): FirePlace[] {
  const found: FirePlace[] = [];
  for (let ty = 0; ty < tiles.length; ty++) {
    const row = tiles[ty];
    for (let tx = 0; tx < row.length; tx++) {
      if (row[tx] === FIRE) {
        found.push({ x: (tx + 0.5) * tileSize, y: (ty + 1) * tileSize });
      }
    }
  }
  return found;
}

/**
 * Distance from a fire in tiles, on the ellipse the seat ring sits on.
 *
 * Mirrors `hearth_distance` in server/app/camp.py. Elliptical rather than
 * circular because the ring is: measuring with a circle would leave the players
 * at the top and bottom of it standing in scrub while the ones at the sides had
 * room.
 */
export function hearthDistance(
  tx: number,
  ty: number,
  fire: FirePlace,
  tileSize: number,
  ringRatio: number,
): number {
  const dx = tx + 0.5 - fire.x / tileSize;
  const dy = (ty + 0.5 - fire.y / tileSize) * ringRatio;
  return Math.hypot(dx, dy);
}

/**
 * Whether a decorative tuft or bush may stand on this tile.
 *
 * The hearth is kept clear: a fern in front of a seated player hides the
 * character the roster is pointing at, and grass growing out of the fire reads
 * as a bug. Past the threshold the chance ramps in over a couple of tiles
 * rather than switching on, so the cleared ground has a soft edge instead of
 * looking stamped.
 *
 * Returns `null` when the map has no fire in it — the forest wants undergrowth
 * everywhere, and a mask that allows everything still costs a call per tile.
 */
export function hearthMask(
  world: TileMap,
  hearthTiles: number,
  ringRatio: number,
  hash: (tx: number, ty: number, seed: number, salt: number) => number,
): ((tx: number, ty: number) => boolean) | null {
  const fires = world.fires;
  if (fires.length === 0) return null;
  const ts = world.tileSize;
  const seed = world.seed;

  return (tx, ty) => {
    let nearest = Infinity;
    for (const fire of fires) {
      const distance = hearthDistance(tx, ty, fire, ts, ringRatio);
      if (distance < nearest) nearest = distance;
    }
    if (nearest < hearthTiles) return false;
    return hash(tx, ty, seed, 61) < Math.min(1, (nearest - hearthTiles) / 2.2);
  };
}

/**
 * West-most VOID tile centre, in world pixels — the mouth of the camp exit.
 * Null when this map has no exit (the forest).
 */
function findExitMouth(tiles: number[][], tileSize: number): { x: number; y: number } | null {
  let minTx = Infinity;
  let sumTy = 0;
  let count = 0;
  for (let ty = 0; ty < tiles.length; ty++) {
    const row = tiles[ty];
    for (let tx = 0; tx < row.length; tx++) {
      if (row[tx] !== VOID) continue;
      if (tx < minTx) minTx = tx;
      sumTy += ty;
      count++;
    }
  }
  if (count === 0) return null;
  return {
    x: (minTx + 0.5) * tileSize,
    y: (sumTy / count + 0.5) * tileSize,
  };
}
