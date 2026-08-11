/**
 * Client-side hitscan, used ONLY to draw the local player's own tracer
 * immediately instead of waiting a round trip. The server remains the sole
 * authority on damage; mirror of server/app/combat.py.
 */

import type { TileMap } from './world';

export interface RayTarget {
  id: string;
  x: number;
  y: number;
  radius: number;
  alive: boolean;
}

export function rayCircle(
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  cx: number,
  cy: number,
  r: number,
): number | null {
  const mx = ox - cx;
  const my = oy - cy;
  const b = mx * dx + my * dy;
  const c = mx * mx + my * my - r * r;
  if (c > 0 && b > 0) return null;
  const disc = b * b - c;
  if (disc < 0) return null;
  return Math.max(0, -b - Math.sqrt(disc));
}

export function hitscan(
  world: TileMap,
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  maxDist: number,
  targets: RayTarget[],
  ignoreId?: string,
): { distance: number; target: RayTarget | null } {
  let distance = world.raycastTiles(ox, oy, dx, dy, maxDist);
  let target: RayTarget | null = null;
  for (const candidate of targets) {
    if (candidate.id === ignoreId || !candidate.alive) continue;
    const d = rayCircle(ox, oy, dx, dy, candidate.x, candidate.y, candidate.radius);
    if (d !== null && d <= distance) {
      distance = d;
      target = candidate;
    }
  }
  return { distance, target };
}
