/**
 * Client-side hitscan, used ONLY to draw the local player's own tracer
 * immediately instead of waiting a round trip. The server remains the sole
 * authority on damage. Capsules and tile DDA mirror `server/app/combat.py`;
 * crate sprite boxes mirror `server/app/crates.py` `along_ray`.
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

/** Nearest t>=0 where the unit ray hits the axis-aligned box, else null. */
export function rayAabb(
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  left: number,
  top: number,
  right: number,
  bottom: number,
): number | null {
  let tmin = 0;
  let tmax = Infinity;

  if (Math.abs(dx) < 1e-12) {
    if (ox < left || ox > right) return null;
  } else {
    let tx1 = (left - ox) / dx;
    let tx2 = (right - ox) / dx;
    if (tx1 > tx2) {
      const swap = tx1;
      tx1 = tx2;
      tx2 = swap;
    }
    tmin = Math.max(tmin, tx1);
    tmax = Math.min(tmax, tx2);
  }

  if (Math.abs(dy) < 1e-12) {
    if (oy < top || oy > bottom) return null;
  } else {
    let ty1 = (top - oy) / dy;
    let ty2 = (bottom - oy) / dy;
    if (ty1 > ty2) {
      const swap = ty1;
      ty1 = ty2;
      ty2 = swap;
    }
    tmin = Math.max(tmin, ty1);
    tmax = Math.min(tmax, ty2);
  }

  if (tmax < tmin) return null;
  return tmin;
}

/**
 * Closest BREAKABLE object's sprite box on the ray, at or before `maxDist`.
 *
 * Mirrors `crates.along_ray`, including the skip: openable objects are not
 * targets. A car bonnet does not come open because somebody shot near it, and
 * a stray round that popped every container on the map would delete the walk
 * the whole object vocabulary exists to create.
 *
 * The box is per object rather than one size for all — `boxOf` answers it —
 * because a bus is four tiles long and a toolbox is one.
 */
export function crateAlongRay(
  crates: readonly { kind: string; x: number; y: number; opened?: boolean }[],
  ox: number,
  oy: number,
  dx: number,
  dy: number,
  maxDist: number,
  breakable: (kind: string) => boolean,
  boxOf: (kind: string) => { w: number; h: number },
): number | null {
  let best: number | null = null;
  for (const crate of crates) {
    // An opened object is scenery: it already paid out and a round through it
    // must not pop a second drop out of the same barrel.
    if (crate.opened || !breakable(crate.kind)) continue;
    const { w, h } = boxOf(crate.kind);
    const half = w * 0.5;
    const dist = rayAabb(
      ox,
      oy,
      dx,
      dy,
      crate.x - half,
      crate.y - h,
      crate.x + half,
      crate.y,
    );
    if (dist !== null && dist <= maxDist && (best === null || dist < best)) {
      best = dist;
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
