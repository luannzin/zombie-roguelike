/**
 * Which way to WALK to the extraction exit, as opposed to which way it lies.
 *
 * The exit arrow used to be a compass: a bearing straight from the player to
 * the corridor's back point. That is the right answer on open ground and the
 * wrong one everywhere else — the forest is a maze of trunks, boulders and
 * scenery, and the shortest line to the exit routinely leaves through a
 * thicket you cannot walk into. Players followed the chevron into a wall,
 * decided it was broken, and started ignoring it during the one sequence in
 * the game where nobody has time to read a minimap.
 *
 * So the arrow points at the ROUTE. One breadth-first flood outward from the
 * mouth of the corridor gives every reachable tile its distance to the exit;
 * the arrow then walks a few tiles downhill from wherever the player is
 * standing and aims at where that walk ends up. The bearing bends around the
 * obstacle instead of through it, and it keeps bending as you move, which is
 * what makes it read as a route rather than a direction.
 *
 * WHY A FIELD AND NOT A PATH. A path is per-player and has to be recomputed
 * every time they step off it; a distance field is computed once per map per
 * exit and answers every player, every frame, with two array lookups. It also
 * degrades correctly: a tile the flood never reached has no answer, and the
 * caller falls back to the old straight bearing rather than pointing nowhere.
 *
 * The flood is deliberately over TILES the player may stand on, using the
 * client's own `isSolidTile` — the same predicate prediction moves against, so
 * the arrow cannot route through a gap the player will bump into. VOID counts
 * as walkable exactly while the egress is open, which is what makes the
 * corridor itself the tail of the route.
 */

/**
 * What the flood needs off the map, and no more.
 *
 * Structural on purpose: `TileMap` satisfies it, and so does a hand-written
 * grid in a test — this file's whole job is routing, and routing is the part
 * worth pinning down without a map payload to build first.
 */
export interface WalkableMap {
  readonly width: number;
  readonly height: number;
  readonly tileSize: number;
  isSolidTile(tx: number, ty: number): boolean;
}

/** Unreachable. Also what an out-of-bounds lookup answers. */
const FAR = -1;

/**
 * How many tiles downhill the arrow looks before it commits to a bearing.
 *
 * SHORT ENOUGH TO BE THE NEXT MOVE, long enough not to jitter. At one tile the
 * bearing snaps between the four axes as the flood's gradient does; at twenty
 * it cuts every corner the route takes and is a compass again. Around a screen
 * height of walking is the distance where the arrow answers "which way out of
 * THIS clearing", which is the question being asked.
 */
const LOOKAHEAD = 7;

interface Field {
  world: WalkableMap;
  /** Identity of the corridor this was flooded from — see `fieldFor`. */
  mouthX: number;
  mouthY: number;
  width: number;
  height: number;
  distance: Int32Array;
}

let cached: Field | null = null;

/** Four-way. Diagonals would cut corners the body cannot fit through. */
const STEPS: readonly (readonly [number, number])[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

/**
 * The distance field for this map's open exit, flooded on first use.
 *
 * Rebuilt when the map changes or the corridor moves. It is NOT rebuilt as the
 * corridor seals: a route to an exit that is closing is still the route, and
 * the arrow is dropped by the quest going away, not by this.
 */
function fieldFor(world: WalkableMap, mouthX: number, mouthY: number): Field | null {
  if (
    cached &&
    cached.world === world &&
    cached.mouthX === mouthX &&
    cached.mouthY === mouthY
  ) {
    return cached;
  }

  const { width, height, tileSize } = world;
  const sx = Math.floor(mouthX / tileSize);
  const sy = Math.floor(mouthY / tileSize);
  if (sx < 0 || sy < 0 || sx >= width || sy >= height) return null;

  const distance = new Int32Array(width * height).fill(FAR);
  // The mouth tile itself can be solid for a frame while the corridor is still
  // being carved. Seeding it anyway costs nothing and means the flood starts
  // the moment the tiles around it open, rather than returning an empty field
  // that gets cached and never revisited.
  const queue = [sy * width + sx];
  distance[queue[0]] = 0;
  for (let head = 0; head < queue.length; head++) {
    const index = queue[head];
    const x = index % width;
    const y = (index - x) / width;
    const next = distance[index] + 1;
    for (const [dx, dy] of STEPS) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const ni = ny * width + nx;
      if (distance[ni] !== FAR) continue;
      if (world.isSolidTile(nx, ny)) continue;
      distance[ni] = next;
      queue.push(ni);
    }
  }

  cached = { world, mouthX, mouthY, width, height, distance };
  return cached;
}

/** Forget the flood. Called when the map goes away. */
export function dropExitPath(): void {
  cached = null;
}

/**
 * A point on the walkable route out, `LOOKAHEAD` tiles ahead of the player.
 *
 * `null` when there is no route from where they are standing — inside a sealed
 * pocket, or before the corridor's tiles have arrived — and the caller should
 * fall back to the straight bearing.
 */
export function exitWaypoint(
  world: WalkableMap,
  fromX: number,
  fromY: number,
  mouthX: number,
  mouthY: number,
): { x: number; y: number } | null {
  const field = fieldFor(world, mouthX, mouthY);
  if (!field) return null;

  const { width, height, distance } = field;
  const size = world.tileSize;
  let x = Math.floor(fromX / size);
  let y = Math.floor(fromY / size);
  if (x < 0 || y < 0 || x >= width || y >= height) return null;
  let here = distance[y * width + x];
  if (here === FAR) return null;

  for (let step = 0; step < LOOKAHEAD && here > 0; step++) {
    let bestX = x;
    let bestY = y;
    let best = here;
    for (const [dx, dy] of STEPS) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const value = distance[ny * width + nx];
      if (value === FAR || value >= best) continue;
      best = value;
      bestX = nx;
      bestY = ny;
    }
    if (bestX === x && bestY === y) break;
    x = bestX;
    y = bestY;
    here = best;
  }

  return { x: (x + 0.5) * size, y: (y + 0.5) * size };
}
