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
  EXIT        a VOID corridor through the trees on the right. Solid ground
              between trunks, crushed into shadow. The party can walk up to
              the mouth and bounce; only the walk-out puppets them through.

Determinism: one seed in, one camp out. The seed also ships to the client, which
hashes it with tile coordinates to place grass, ferns and prop variants — the
same contract `mapgen.py` has.
"""

from __future__ import annotations

import math

from .config import (
    CAMP_CLEARING_TILES,
    CAMP_EXIT_HALF_TILES,
    CAMP_HEARTH_TILES,
    CAMP_HEIGHT_TILES,
    CAMP_READY_RANGE_TILES,
    CAMP_RING_TILES_X,
    CAMP_RING_TILES_Y,
    CAMP_RING_X,
    CAMP_RING_Y,
    CAMP_WIDTH_TILES,
    PLAYER_HALF_HEIGHT,
    TILE_SIZE,
)
from .world import FIRE, FLOOR, ROCK, TREE, VOID, TileMap

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
    _carve_exit(tiles, cx, cy)
    return TileMap(tiles, seed=seed)


def _carve_exit(tiles: list[list[int]], cx: float, cy: float) -> None:
    """Punch a VOID corridor through the trees on the right, to the map edge.

    The mouth sits in the treeline, just past the clearing: a gap between
    trunks, not a missing floor. VOID is solid, so nobody walks in until the
    walk-out puppets them through.
    """
    fy = int(round(cy))
    start_x = int(cx + CAMP_CLEARING_TILES) + 1
    half = CAMP_EXIT_HALF_TILES
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    for tx in range(start_x, width):
        for ty in range(fy - half, fy + half + 1):
            if 0 <= ty < height:
                tiles[ty][tx] = VOID


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


def exit_corridor(world: TileMap) -> tuple[float, float, float]:
    """The black exit as (mouth_x, centre_y, east_x) in world pixels.

    Mouth is the west-most VOID tile centre — where the party lines up.
    East is the last VOID tile, past which they have crossed.
    """
    min_tx = world.width
    max_tx = -1
    ys: list[int] = []
    for ty, row in enumerate(world.tiles):
        for tx, tile in enumerate(row):
            if tile != VOID:
                continue
            min_tx = min(min_tx, tx)
            max_tx = max(max_tx, tx)
            ys.append(ty)
    if max_tx < 0:
        fire_x, fire_y = fire_position(world)
        return fire_x + CAMP_CLEARING_TILES * TILE_SIZE, fire_y, world.pixel_width
    centre_y = (sum(ys) / len(ys) + 0.5) * TILE_SIZE
    mouth_x = (min_tx + 0.5) * TILE_SIZE
    east_x = (max_tx + 0.5) * TILE_SIZE
    return mouth_x, centre_y, east_x


def near_fire(player_x: float, player_y: float, world: TileMap) -> bool:
    """True when the player's feet are inside the ready range of the bonfire."""
    fire_x, fire_y = fire_position(world)
    feet_y = player_y + PLAYER_HALF_HEIGHT
    dist = math.hypot(player_x - fire_x, feet_y - fire_y)
    return dist <= CAMP_READY_RANGE_TILES * TILE_SIZE


def _wobble(index: int, salt: int) -> float:
    """Deterministic -0.5..0.5, so every client would agree if it had to."""
    h = (index * 374761393 + salt * 668265263) & 0xFFFFFFFF
    h ^= h >> 13
    return ((h & 0xFFFF) / 0xFFFF) - 0.5


def formation_slots(
    world: TileMap, seating: list[str], present: set[str]
) -> dict[str, tuple[float, float]]:
    """Two staggered files, west of the exit mouth, facing east.

    Not a grid: the lower file sits a half-step closer to the mouth, and each
    body gets a small hash wobble, so a pair walking out does not look like
    they were placed with a ruler.
    """
    ids = [pid for pid in seating if pid in present]
    mouth_x, centre_y, _ = exit_corridor(world)
    base_x = mouth_x - TILE_SIZE * 1.6
    slots: dict[str, tuple[float, float]] = {}
    for index, pid in enumerate(ids):
        file = index % 2
        col = index // 2
        x = base_x - col * TILE_SIZE * 1.35
        if file == 1:
            x += TILE_SIZE * 0.4
        y = centre_y + (1 if file else -1) * TILE_SIZE * 0.62
        x += _wobble(index, 1) * TILE_SIZE * 0.35
        y += _wobble(index, 2) * TILE_SIZE * 0.18
        slots[pid] = (x, y - PLAYER_HALF_HEIGHT)
    return slots


def march_towards(
    player_x: float,
    player_y: float,
    tx: float,
    ty: float,
    speed: float,
    dt: float,
) -> tuple[float, float, float, float, float, float, bool]:
    """Slide a body toward (tx, ty) with no collision. Returns x,y,vx,vy,ax,ay,arrived."""
    dx = tx - player_x
    dy = ty - player_y
    dist = math.hypot(dx, dy)
    if dist < 0.8:
        return tx, ty, 0.0, 0.0, 1.0, 0.0, True
    inv = 1.0 / dist
    nx, ny = dx * inv, dy * inv
    step = speed * dt
    if step >= dist:
        return tx, ty, 0.0, 0.0, nx, ny, True
    return (
        player_x + nx * step,
        player_y + ny * step,
        nx * speed,
        ny * speed,
        nx,
        ny,
        False,
    )


#: Exported for anyone measuring the camp in pixels rather than tiles.
CAMP_PIXEL_WIDTH = CAMP_WIDTH_TILES * TILE_SIZE
CAMP_PIXEL_HEIGHT = CAMP_HEIGHT_TILES * TILE_SIZE
