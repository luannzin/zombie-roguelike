/**
 * The exit arrow routes AROUND things.
 *
 * Plain script, no framework, prints `ok` — the same shape as `grade.ts` and
 * the server's checks. Run it with `bun tests/exit-path.ts` from `client/`.
 *
 * One claim, and it is the whole reason the module exists: with a wall between
 * the player and the exit, the arrow must not point at the wall. A compass
 * passes every test you can write about direction and still walks the player
 * into a thicket, so the test is built as a map with exactly one way through.
 */

import { dropExitPath, exitWaypoint, type WalkableMap } from '../src/game/exit-path';

let checks = 0;

function assert(condition: boolean, message: string): void {
  checks++;
  if (!condition) throw new Error(message);
}

const TILE = 32;

/** `#` solid, `.` walkable. Row 0 is the top. */
function mapOf(rows: readonly string[]): WalkableMap {
  return {
    width: rows[0].length,
    height: rows.length,
    tileSize: TILE,
    isSolidTile: (tx, ty) =>
      tx < 0 || ty < 0 || ty >= rows.length || tx >= rows[0].length || rows[ty][tx] === '#',
  };
}

const centre = (t: number): number => (t + 0.5) * TILE;

// The exit is due east of the player, and due east is a wall. The only way
// through is the gap at the bottom.
const world = mapOf([
  '....#.....',
  '....#.....',
  '....#.....',
  '....#.....',
  '....#.....',
  '..........',
]);

dropExitPath();
const exitX = 9;
const exitY = 2;

{
  const point = exitWaypoint(world, centre(1), centre(2), centre(exitX), centre(exitY));
  assert(point !== null, 'a reachable player must get a waypoint');
  assert(
    point!.y > centre(2),
    `must route toward the gap below the wall, got y=${point!.y} from ${centre(2)}`,
  );
}

{
  // Standing past the wall, the route is a straight run east again.
  const point = exitWaypoint(world, centre(6), centre(2), centre(exitX), centre(exitY));
  assert(point !== null, 'past the wall there is still a route');
  assert(point!.x > centre(6), 'past the wall the arrow points at the exit');
  assert(Math.abs(point!.y - centre(2)) < TILE, 'no detour once the way is clear');
}

{
  // A sealed pocket has no route: the caller falls back to the bearing.
  const sealed = mapOf([
    '.#...',
    '#####',
    '.....',
  ]);
  dropExitPath();
  const point = exitWaypoint(sealed, centre(0), centre(0), centre(4), centre(2));
  assert(point === null, 'an unreachable player must get null, not a guess');
}

console.log(`ok (${checks} checks)`);
