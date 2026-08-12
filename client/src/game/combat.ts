/**
 * Client-side hitscan, used ONLY to draw the local player's own tracer
 * immediately instead of waiting a round trip. The server remains the sole
 * authority on damage; mirror of server/app/combat.py.
 */

import type { TileMap } from './world';

export interface RayTarget {
  id: string;
  x: number;
  /** Feet end of vertical hit capsule (world y). */
  capsuleY0: number;
  /** Head end of vertical hit capsule (world y). */
  capsuleY1: number;
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

function pointSegmentDist2(
  px: number,
  py: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
): number {
  const abx = bx - ax;
  const aby = by - ay;
  const apx = px - ax;
  const apy = py - ay;
  const ab2 = abx * abx + aby * aby;
  if (ab2 < 1e-12) return apx * apx + apy * apy;
  const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / ab2));
  const cx = ax + abx * t;
  const cy = ay + aby * t;
  return (px - cx) * (px - cx) + (py - cy) * (py - cy);
}

/** Nearest t>=0 where unit ray hits capsule (segment AB + radius), else null. */
export function rayCapsule(
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
  r: number,
): number | null {
  if (pointSegmentDist2(ox, oy, ax, ay, bx, by) <= r * r) return 0;

  let best: number | null = null;
  const consider = (t: number | null) => {
    if (t !== null && (best === null || t < best)) best = t;
  };

  consider(rayCircle(ox, oy, dx, dy, ax, ay, r));
  consider(rayCircle(ox, oy, dx, dy, bx, by, r));

  const abx = bx - ax;
  const aby = by - ay;
  const ab2 = abx * abx + aby * aby;
  if (ab2 < 1e-12) return best;

  const abLen = Math.sqrt(ab2);
  const crossD = dx * aby - dy * abx;
  const crossOa = (ox - ax) * aby - (oy - ay) * abx;
  if (Math.abs(crossD) > 1e-12) {
    for (const sign of [1, -1]) {
      const t = (sign * r * abLen - crossOa) / crossD;
      if (t < 0) continue;
      const px = ox + t * dx;
      const py = oy + t * dy;
      const proj = ((px - ax) * abx + (py - ay) * aby) / ab2;
      if (proj > 0 && proj < 1) consider(t);
    }
  }

  return best;
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
    const d = rayCapsule(
      ox,
      oy,
      dx,
      dy,
      candidate.x,
      candidate.capsuleY0,
      candidate.x,
      candidate.capsuleY1,
      candidate.radius,
    );
    if (d !== null && d <= distance) {
      distance = d;
      target = candidate;
    }
  }
  return { distance, target };
}
