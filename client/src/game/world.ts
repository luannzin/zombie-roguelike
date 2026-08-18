/**
 * Client-side tile map. Mirror of server/app/world.py.
 *
 * `moveAxis` MUST stay numerically identical to the Python version, otherwise
 * client prediction and the server disagree near walls and the local player
 * rubber-bands. VOID is a shadowed winding path in the woods, not a hole
 * in the ground: solid at camp and on the forest arrival, walkable only
 * while an extraction `egress` is open.
 */

import type { MapPayload } from '../net/protocol';

/** Tile kinds. Mirror of server/app/world.py. */
export const FLOOR = 0;
export const ROCK = 1;
/** Solid trunk — one tile, the contact. The canopy is art on the tiles above. */
export const TREE = 2;
export const FIRE = 3;
/** Dark gap in the trees. Painted as floor; walkable only with `egress`. */
export const VOID = 4;
/**
 * Solid doorstep of a BUILDING from a placed scene — one tile tall, at the
 * contact. Painted as floor and drawn with nothing: the cabin or tent sprite
 * covers it, including the roof you walk behind. Blocks light too.
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

/**
 * How far a threshold torch lifts the night, in tiles.
 *
 * Smaller than a powered platform's light and much smaller than a bonfire. It
 * has to make the place findable and no more: four torches that lit the
 * clearing would undo the blackout the extraction just imposed, and the run
 * home is supposed to be dark. An extraction pad wears one of these all night;
 * the exit corridor wears four.
 */
const TORCH_LIGHT_TILES = 3.4;
/** Scene-light kind 2 — see `theme/palette.ts` `scene`. */
const BEACON_LIGHT = 2;

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

/** A live crate. Drawn like standing scenery; removed when it breaks. */
export interface CratePiece {
  id: string;
  x: number;
  y: number;
  variant: number;
  flip: boolean;
}

/**
 * The extraction point, placed by `server/app/rift.py`: an abandoned cargo
 * platform, four lift drones on ropes, a console and a torch.
 *
 * Geometry arrives once on the map payload and never moves; `state`, `elapsed`
 * and `woke` are the live half. The client runs `elapsed` on its OWN clock
 * between the snapshots the server sends, because a rig winding up and a
 * platform flying away resolved at 6 Hz would step rather than play.
 */
export type RiftState = 'dormant' | 'charging' | 'open' | 'spent';

export interface RiftDrone {
  /** Ground contact of the parked airframe. */
  x: number;
  y: number;
}

export interface Rift {
  id: string;
  /** Middle of the deck's footprint: the imprint, the light, the core drop. */
  x: number;
  y: number;
  /** Contact point of the skid — the row its beams stand on. */
  deckX: number;
  deckY: number;
  /** The console you press. Distance is measured from a player's FEET to this. */
  consoleX: number;
  consoleY: number;
  /** The torch marking the pad. Burning from the moment the map is built. */
  torchX: number;
  torchY: number;
  /** The four parked drones, in the corner order the server wakes them. */
  drones: readonly RiftDrone[];
  /** Which way the platform leaves, in radians. Rolled once, by the map. */
  heading: number;
  lightTiles: number;
  lightKind: number;
  state: RiftState;
  /** Seconds since the console was pressed. */
  elapsed: number;
  /** When the launch begins, in the same clock as `elapsed`. Null while holding. */
  closeAt: number | null;
  /**
   * `elapsed` at which each drone started spooling. Its LENGTH is how many are
   * awake — one for the pad being open, one more per overfeed tier.
   */
  woke: number[];
  /** Catalog value put into THIS pad, and the quota it asked for. */
  fed: number;
  need: number;
  /** Overfeed tier, 0..3, straight off the server. */
  level: number;
  /** Quota paid and still on the ground: the console is a launch button now. */
  ready: boolean;
}

/** One table in the shop, and the weapon lying on it. */
export interface Stand {
  id: string;
  /** Weapon catalog key. */
  key: string;
  price: number;
  /** Centre of the table. */
  x: number;
  /** Contact — the row its feet stand on. */
  y: number;
  /** Which table sheet frame this stall uses. */
  variant: number;
  /** Bought. The table stays; the gap where the gun was is the information. */
  sold: boolean;
}

/**
 * The merchant's pitch. Null on every map that is not the store.
 *
 * Only what is HIS. The glade around it is an ordinary forest map — its soil
 * is hashed from the seed and his tent is a scenery prop — so nothing about
 * the place he is standing in needs to be here.
 */
export interface StoreFixtures {
  merchantX: number;
  merchantY: number;
  stands: Stand[];
  torches: readonly { x: number; y: number; variant: number }[];
  rugX: number;
  rugY: number;
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
   * without one. Resolved with the fires rather than on demand: the walk-out
   * camera asks for it every frame, and it cannot move.
   */
  readonly exit: { x: number; y: number } | null;
  /**
   * Forest arrival corridor. Null on the camp. Mouth / dir are world pixels;
   * state is rewritten as the woods swallow the path.
   */
  entrance: {
    side: string;
    mouthX: number;
    mouthY: number;
    backX: number;
    backY: number;
    dirX: number;
    dirY: number;
    state: 'open' | 'sealing' | 'gone';
    elapsed: number;
    /**
     * Always EMPTY on an arrival — a corridor you are already inside and about
     * to lose does not get marked. It is on the shape rather than only on
     * `egress` because the two are one thing, unpacked by one function, and
     * splitting the type would mean two unpackers to keep in step.
     */
    torches: readonly { x: number; y: number }[];
  } | null;
  /**
   * The scenes the server laid over this map, split by how they are drawn.
   * Empty on a locally generated map — the title screen's clearing has no
   * story in it, because nobody is standing in it to read one.
   */
  readonly scenery: Scenery;
  /**
   * Breakable crates. Mutable — a smash removes one and opens its LOW tile.
   * Sorted by `y` so the renderer can merge them into the standing pass.
   */
  crates: CratePiece[];
  /**
   * Extraction points, empty on a map without any (every camp). Mutable:
   * activating one is the thing on this map that changes what the map IS.
   */
  rifts: Rift[];
  /**
   * Extraction exit, or null until the feed quota is paid. Mouth / dir are
   * world pixels; the tiles arrive as patches on the same snapshot.
   */
  egress: {
    side: string;
    mouthX: number;
    mouthY: number;
    backX: number;
    backY: number;
    dirX: number;
    dirY: number;
    state: 'open' | 'sealing' | 'gone';
    elapsed: number;
    /**
     * Contact points of the torches marking the way out. Exit only — an
     * arrival corridor is one you are already inside and about to lose.
     */
    torches: readonly { x: number; y: number }[];
  } | null;
  /**
   * The shop's fixtures, or null on every map that is not the store.
   *
   * `stands` is mutable and the rest is not, which is the whole shape of the
   * zone: where the merchant and his tables are was decided when the corridor
   * was built and cannot change, and the only thing that happens in here is
   * that a weapon leaves a table.
   */
  store: StoreFixtures | null;

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
    this.entrance = unpackEntrance(payload);
    this.scenery = unpackScenery(payload);
    this.crates = unpackCrates(payload);
    this.rifts = unpackRifts(payload);
    this.egress = unpackCorridor(payload.egress);
    this.store = unpackStore(payload);
    // A client that arrives mid-run — or reconnects after the exit opened —
    // gets the map with the corridor already on it, and its torches have to be
    // lit here as well as in `setEgress`, or they are dark for that player
    // alone on a map where nothing else is burning.
    this.lightTorches();
    // EVERY PAD'S TORCH BURNS FROM THE START. It is the only part of an
    // extraction point that is alight before anybody touches it, and that is
    // the whole reason it is there: a landmark you can only see once you have
    // found it is not a landmark. The deck's own light is separate and waits
    // for the console.
    for (const row of this.rifts) {
      this.lightAt(row.torchX, row.torchY, TORCH_LIGHT_TILES);
      if (row.state === 'charging' || row.state === 'open') this.lightRift(row);
    }
  }

  /**
   * Adopt the server's word on what the rift is doing.
   *
   * `elapsed` is taken from the server on every update, including the one that
   * starts the sequence — a client that joins mid-charge picks it up in
   * progress rather than replaying it from zero.
   */
  setRiftState(
    id: string,
    state: RiftState,
    elapsed: number,
    closeAt: number | null = null,
    feed?: { fed: number; need: number; level: number; ready: boolean; woke?: number[] },
  ): void {
    const row = this.rifts.find((item) => item.id === id);
    if (!row) return;
    row.state = state;
    row.elapsed = elapsed;
    if (closeAt !== null) row.closeAt = closeAt;
    if (feed) {
      row.fed = feed.fed;
      row.need = feed.need;
      row.level = feed.level;
      row.ready = feed.ready;
      if (feed.woke) row.woke = [...feed.woke];
    }
    if (state === 'charging' || state === 'open') this.lightRift(row);
    if (state === 'spent') this.darkenRift(row);
  }

  /**
   * Adopt the server's word on which tables have been bought from.
   *
   * Matched by id and applied in place rather than replacing the array: the
   * fixtures are the same objects the renderer is holding, and a purchase must
   * not make the corridor rebuild itself.
   */
  setStands(rows: readonly { id: string; sold?: boolean }[]): void {
    const store = this.store;
    if (!store) return;
    for (const row of rows) {
      const stand = store.stands.find((item) => item.id === row.id);
      if (stand) stand.sold = row.sold === true;
    }
  }

  setEntranceState(state: 'open' | 'sealing' | 'gone', elapsed: number): void {
    if (!this.entrance) return;
    this.entrance.state = state;
    this.entrance.elapsed = elapsed;
  }

  setEgress(row: NonNullable<TileMap['egress']>): void {
    this.egress = row;
    this.lightTorches();
  }

  /**
   * Put the exit's torches on the ONE scene-light list.
   *
   * Same rule the rift's beacon follows: the lighting has no concept of a camp
   * light versus a forest light versus a torch and must not grow one. It also
   * matters more here than anywhere else — the exit opens during the blackout,
   * so for the rest of that night these four are the only thing burning on the
   * map, and a torch that only glows in the additive pass would light nothing
   * and reveal nothing.
   */
  private lightTorches(): void {
    const egress = this.egress;
    if (!egress) return;
    for (const torch of egress.torches) this.lightAt(torch.x, torch.y, TORCH_LIGHT_TILES);
  }

  /** One entry on the scene-light list, idempotent by position. */
  private lightAt(x: number, y: number, radiusTiles: number): void {
    const lights = this.scenery.lights as SceneryLight[];
    if (lights.some((light) => light.x === x && light.y === y)) return;
    lights.push({ x, y, radiusTiles, kind: BEACON_LIGHT });
  }

  /**
   * Advance every pad's local clock. Called once per frame.
   *
   * It keeps running AFTER the platform is awake, and that is the point:
   * `elapsed` is what every moving part of this rig is phased against. A
   * drone's spool is measured from its own entry in `woke`, the launch from
   * `closeAt`, and both are in this clock — so one number kept in step between
   * snapshots animates the whole machine.
   */
  stepRift(dt: number): void {
    for (const row of this.rifts) {
      if (row.state === 'charging' || row.state === 'open') row.elapsed += dt;
    }
  }

  /** Take this pad's beacon back off the scene-light list. */
  private darkenRift(row: Rift): void {
    const lights = this.scenery.lights as SceneryLight[];
    const index = lights.findIndex((light) => light.x === row.x && light.y === row.y);
    if (index >= 0) lights.splice(index, 1);
  }

  /**
   * Put this pad's beacon on the ONE scene-light list.
   *
   * Deliberately not a second list the lighting has to know about: the fov
   * field and the glow pass have no concept of a camp light versus a forest
   * light versus this, and must not grow one. A powered platform is simply
   * another thing on the map that is lit.
   */
  private lightRift(row: Rift): void {
    const lights = this.scenery.lights as SceneryLight[];
    if (lights.some((light) => light.x === row.x && light.y === row.y)) return;
    lights.push({
      x: row.x,
      y: row.y,
      radiusTiles: row.lightTiles,
      kind: row.lightKind,
    });
  }

  setTile(tx: number, ty: number, kind: number): void {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return;
    this.tiles[ty][tx] = kind;
  }

  replaceCrates(rows: CratePiece[]): void {
    this.crates = rows.slice().sort((a, b) => a.y - b.y);
  }

  removeCrate(id: string): CratePiece | null {
    const index = this.crates.findIndex((crate) => crate.id === id);
    if (index < 0) return null;
    const [removed] = this.crates.splice(index, 1);
    return removed ?? null;
  }

  /**
   * Anything that is not floor blocks movement and shots, with one named
   * exception: VOID is walkable while `egress` is set (the extraction
   * corridor). Camp VOID and the forest arrival stay solid because those
   * maps have no egress. Sight is `blocksSight` — a fire, the camp exit
   * and waist-high cover stop a body but not a beam.
   */
  isSolidTile(tx: number, ty: number): boolean {
    if (tx < 0 || ty < 0 || tx >= this.width || ty >= this.height) return true;
    const tile = this.tiles[ty][tx];
    if (tile === VOID) return this.egress == null;
    return tile !== FLOOR;
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

function unpackRifts(payload: MapPayload): Rift[] {
  const rows = payload.rifts ?? [];
  return rows.map((row) => ({
    id: row.id,
    x: row.x,
    y: row.y,
    deckX: row.deck[0],
    deckY: row.deck[1],
    consoleX: row.console[0],
    consoleY: row.console[1],
    torchX: row.torch[0],
    torchY: row.torch[1],
    drones: row.drones.map(([x, y]) => ({ x, y })),
    heading: row.heading ?? 0,
    lightTiles: row.lightTiles,
    lightKind: row.lightKind,
    state: row.state,
    elapsed: row.t,
    closeAt: row.closeAt ?? null,
    woke: [...(row.woke ?? [])],
    fed: row.fed ?? 0,
    need: row.need ?? 0,
    level: row.level ?? 0,
    ready: row.ready ?? false,
  }));
}

function unpackStore(payload: MapPayload): StoreFixtures | null {
  const row = payload.store;
  if (!row) return null;
  return {
    merchantX: row.merchant[0],
    merchantY: row.merchant[1],
    stands: (row.stands ?? []).map((stand) => ({
      id: stand.id,
      key: stand.k,
      price: stand.price,
      x: stand.x,
      y: stand.y,
      variant: stand.v,
      sold: stand.sold === true,
    })),
    torches: (row.torches ?? []).map(([x, y, variant]) => ({ x, y, variant })),
    rugX: row.rug[0],
    rugY: row.rug[1],
  };
}

function unpackCrates(payload: MapPayload): CratePiece[] {
  const rows = payload.crates ?? [];
  const crates = rows.map((row) => ({
    id: row.id,
    x: row.x,
    y: row.y,
    variant: row.v,
    flip: row.flip !== 0,
  }));
  crates.sort((a, b) => a.y - b.y);
  return crates;
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
/** The LOW tile a crate claims. Mirrors `crates.footprint` on the server. */
export function crateFootprint(
  x: number,
  y: number,
  tileSize: number,
): { tx: number; ty: number } {
  return {
    tx: Math.floor(x / tileSize),
    ty: Math.floor(y / tileSize - 1e-6),
  };
}

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

function unpackEntrance(payload: MapPayload): TileMap['entrance'] {
  return unpackCorridor(payload.entrance);
}

function unpackCorridor(
  row: MapPayload['entrance'] | MapPayload['egress'],
): TileMap['entrance'] {
  if (!row) return null;
  return {
    side: row.side,
    mouthX: row.mouth[0],
    mouthY: row.mouth[1],
    backX: row.back[0],
    backY: row.back[1],
    dirX: row.dir[0],
    dirY: row.dir[1],
    state: row.state,
    elapsed: row.t,
    torches: (row.torches ?? []).map(([x, y]) => ({ x, y })),
  };
}
