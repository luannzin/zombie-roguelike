"""Hitscan combat.

`raycast` is deliberately entity-agnostic: it takes any iterable of objects
exposing `.id`, `.x`, `.capsule_y0`, `.capsule_y1`, `.radius` and `.alive`.
A capsule is a vertical stadium (segment + radius) covering the full body.
Zombies drop straight into `targets` with no changes here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

from .world import TileMap


@dataclass
class RayHit:
    distance: float
    target: Optional[object]  # None => hit a wall (or reached max range)


def raycast_tiles(
    world: TileMap, ox: float, oy: float, dx: float, dy: float, max_dist: float
) -> float:
    """DDA grid traversal. Returns distance to the first solid tile, or max_dist."""
    ts = world.tile_size
    tx = int(ox // ts)
    ty = int(oy // ts)

    if world.is_solid_tile(tx, ty):
        return 0.0

    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy > 0 else -1

    inv_dx = math.inf if dx == 0 else abs(1.0 / dx)
    inv_dy = math.inf if dy == 0 else abs(1.0 / dy)

    if dx > 0:
        t_max_x = ((tx + 1) * ts - ox) * inv_dx
    elif dx < 0:
        t_max_x = (ox - tx * ts) * inv_dx
    else:
        t_max_x = math.inf

    if dy > 0:
        t_max_y = ((ty + 1) * ts - oy) * inv_dy
    elif dy < 0:
        t_max_y = (oy - ty * ts) * inv_dy
    else:
        t_max_y = math.inf

    t_delta_x = ts * inv_dx
    t_delta_y = ts * inv_dy

    travelled = 0.0
    while travelled <= max_dist:
        if t_max_x < t_max_y:
            travelled = t_max_x
            tx += step_x
            t_max_x += t_delta_x
        else:
            travelled = t_max_y
            ty += step_y
            t_max_y += t_delta_y
        if travelled > max_dist:
            break
        if world.is_solid_tile(tx, ty):
            return travelled
    return max_dist


def ray_circle(
    ox: float, oy: float, dx: float, dy: float, cx: float, cy: float, r: float
) -> Optional[float]:
    """Nearest non-negative distance along the ray hitting the circle, else None."""
    mx = ox - cx
    my = oy - cy
    b = mx * dx + my * dy
    c = mx * mx + my * my - r * r
    if c > 0.0 and b > 0.0:
        return None
    disc = b * b - c
    if disc < 0.0:
        return None
    t = -b - math.sqrt(disc)
    if t < 0.0:
        t = 0.0
    return t


def _point_segment_dist2(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-12:
        return apx * apx + apy * apy
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    cx = ax + abx * t
    cy = ay + aby * t
    return (px - cx) * (px - cx) + (py - cy) * (py - cy)


def ray_capsule(
    ox: float,
    oy: float,
    dx: float,
    dy: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    r: float,
) -> Optional[float]:
    """Nearest t>=0 where unit ray hits capsule (segment AB + radius), else None."""
    if _point_segment_dist2(ox, oy, ax, ay, bx, by) <= r * r:
        return 0.0

    best: Optional[float] = None

    def consider(t: Optional[float]) -> None:
        nonlocal best
        if t is not None and (best is None or t < best):
            best = t

    consider(ray_circle(ox, oy, dx, dy, ax, ay, r))
    consider(ray_circle(ox, oy, dx, dy, bx, by, r))

    abx = bx - ax
    aby = by - ay
    ab2 = abx * abx + aby * aby
    if ab2 < 1e-12:
        return best

    ab_len = math.sqrt(ab2)
    # 2D cross: hit when |(O + tD - A) × AB| / |AB| == r  and proj in (0, 1)
    cross_d = dx * aby - dy * abx
    cross_oa = (ox - ax) * aby - (oy - ay) * abx
    if abs(cross_d) > 1e-12:
        for sign in (1.0, -1.0):
            t = (sign * r * ab_len - cross_oa) / cross_d
            if t < 0.0:
                continue
            px = ox + t * dx
            py = oy + t * dy
            proj = ((px - ax) * abx + (py - ay) * aby) / ab2
            if 0.0 < proj < 1.0:
                consider(t)

    return best


def raycast(
    world: TileMap,
    ox: float,
    oy: float,
    dx: float,
    dy: float,
    max_dist: float,
    targets: Iterable,
    ignore_id: Optional[str] = None,
) -> RayHit:
    best = raycast_tiles(world, ox, oy, dx, dy, max_dist)
    hit = None
    for t in targets:
        if getattr(t, "id", None) == ignore_id or not getattr(t, "alive", True):
            continue
        d = ray_capsule(
            ox,
            oy,
            dx,
            dy,
            t.x,
            t.capsule_y0,
            t.x,
            t.capsule_y1,
            t.radius,
        )
        if d is not None and d <= best:
            best = d
            hit = t
    return RayHit(distance=best, target=hit)
