"""The camp: one clearing, a bonfire in the middle of it, a ring of seats.

This is the map the lobby draws and the map `preparation` is played on — the
same tiles, sent once, so nobody teleports when the host presses start. The
player standing at the fire while the party gathers is standing on the tile they
will walk off.

Shape, from the middle out:

  HEARTH      the fire plus the seat ring. Solid FIRE tile in the centre, bare
              floor around it. Nothing may stand here, decorative or otherwise.
  CLEARING    open ground with the odd boulder, edged raggedly so it does not
              read as a stamped circle.
  TREELINE    density ramps with depth, then a solid border of trunks so the
              camera never frames the end of the world.

Determinism: one seed in, one camp out. The seed also ships to the client, which
hashes it with tile coordinates to place grass, ferns and prop variants — the
same contract `mapgen.py` has.
"""

from __future__ import annotations

import math

from .config import (
    CAMP_CLEARING_TILES,
    CAMP_HEARTH_TILES,
    CAMP_HEIGHT_TILES,
    CAMP_RING_TILES_X,
    CAMP_RING_TILES_Y,
    CAMP_RING_X,
    CAMP_RING_Y,
    CAMP_WIDTH_TILES,
    PLAYER_HALF_HEIGHT,
    TILE_SIZE,
)
from .world import FIRE, FLOOR, ROCK, TREE, TileMap

#: Trunks around the edge, in tiles.
BORDER_TILES = 2
#: Boulders on the open clearing floor, out past the hearth.
BOULDER_CHANCE = 0.94
#: Ragged edge of the clearing: how far the treeline wanders, in tiles.
EDGE_JITTER = 1.8
#: Vertical squash of the clearing. Matches the seat ring's, so a landscape
#: viewport frames an oval of open ground rather than a bulge.
CLEARING_SQUASH = 1.45


def _hash(tx: int, ty: int, seed: int, salt: int = 0) -> float:
    """Deterministic 0..1 from a tile coordinate. Mirrors the client's tileHash.

    Not required to match — the tiles travel on the wire — but keeping the same
    mixer means a camp generated here and a clearing generated client-side (the
    title screen has no server) come out looking like the same forest.
    """
    h = (tx * 374761393 + ty * 668265263 + ((seed ^ salt) * 2246822519)) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def hearth_distance(tx: float, ty: float, cx: float, cy: float) -> float:
    """Distance from the fire in tiles, on the ellipse the seats sit on.

    Elliptical rather than circular because the seat ring is: measuring with a
    circle leaves the players at the top and bottom of the ring standing in
    scrub while the ones at the sides have room.
    """
    dx = tx - cx
    dy = (ty - cy) * (CAMP_RING_TILES_X / CAMP_RING_TILES_Y)
    return math.hypot(dx, dy)


def _camp_tile(tx: int, ty: int, cx: float, cy: float, seed: int) -> int:
    if (
        tx < BORDER_TILES
        or ty < BORDER_TILES
        or tx >= CAMP_WIDTH_TILES - BORDER_TILES
        or ty >= CAMP_HEIGHT_TILES - BORDER_TILES
    ):
        return TREE

    hearth = hearth_distance(tx, ty, cx, cy)
    # Nothing stands in the hearth. The fire itself is stamped after this.
    if hearth < CAMP_HEARTH_TILES:
        return FLOOR

    dx = tx - cx
    dy = (ty - cy) * CLEARING_SQUASH
    distance = math.hypot(dx, dy)
    edge = CAMP_CLEARING_TILES + _hash(tx, ty, seed, 7) * EDGE_JITTER - EDGE_JITTER / 2

    if distance < edge:
        # A couple of boulders out on the floor, well clear of the party.
        if hearth > CAMP_HEARTH_TILES + 1.5 and _hash(tx, ty, seed, 8) > BOULDER_CHANCE:
            return ROCK
        return FLOOR

    # Density ramps with depth so the treeline thickens instead of starting solid.
    depth = min(1.0, max(0.0, (distance - edge) / 5.0))
    if _hash(tx, ty, seed, 9) < 0.16 + depth * 0.66:
        return TREE
    if _hash(tx, ty, seed, 10) < 0.05 + depth * 0.06:
        return ROCK
    return FLOOR


def build_camp(seed: int) -> TileMap:
    """Generate the camp. The fire tile is always the exact centre of the map."""
    fx = CAMP_WIDTH_TILES // 2
    fy = CAMP_HEIGHT_TILES // 2
    cx = float(fx)
    cy = float(fy)

    tiles = [
        [_camp_tile(tx, ty, cx, cy, seed) for tx in range(CAMP_WIDTH_TILES)]
        for ty in range(CAMP_HEIGHT_TILES)
    ]
    tiles[fy][fx] = FIRE
    return TileMap(tiles, seed=seed)


def fire_position(world: TileMap) -> tuple[float, float]:
    """The bonfire's base in world pixels — the anchor everything else uses."""
    fires = world.fire_points()
    if fires:
        return fires[0]
    return world.pixel_width / 2, world.pixel_height / 2


def seat_position(world: TileMap, index: int, total: int) -> tuple[float, float]:
    """Where player `index` of `total` stands around the fire.

    Returned as a PLAYER POSITION — the centre of the collision box — not as the
    point their feet touch, so it can be assigned straight onto `Player.x/y`.
    The ring starts at the front seat (nearest the camera) and spaces the party
    evenly around it; the order is join order, which every client agrees on
    because it comes from here.
    """
    fire_x, fire_y = fire_position(world)
    angle = math.pi / 2 + (index / max(1, total)) * math.tau
    feet_x = fire_x + math.cos(angle) * CAMP_RING_X
    feet_y = fire_y + math.sin(angle) * CAMP_RING_Y
    return feet_x, feet_y - PLAYER_HALF_HEIGHT


def seat_positions(world: TileMap, total: int) -> list[tuple[float, float]]:
    return [seat_position(world, index, total) for index in range(total)]


#: Exported for anyone measuring the camp in pixels rather than tiles.
CAMP_PIXEL_WIDTH = CAMP_WIDTH_TILES * TILE_SIZE
CAMP_PIXEL_HEIGHT = CAMP_HEIGHT_TILES * TILE_SIZE
