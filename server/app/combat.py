"""Hitscan combat.

`raycast` is deliberately entity-agnostic: it takes any iterable of objects
exposing `.id`, `.x`, `.y`, `.radius` and `.alive`. Zombies will drop straight
into `targets` with no changes here.
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
        d = ray_circle(ox, oy, dx, dy, t.x, t.y, t.radius)
        if d is not None and d <= best:
            best = d
            hit = t
    return RayHit(distance=best, target=hit)
