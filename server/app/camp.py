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
  EXIT        a winding VOID path through the trees on the right. Solid
              ground between trunks, crushed into shadow. Not a rectangle:
              the centreline wanders and the edges fray. The party can walk
              up to the mouth and bounce; only the walk-out puppets them
              through.

Determinism: one seed in, one camp out. The seed also ships to the client, which
hashes it with tile coordinates to place grass, ferns and prop variants — the
same contract `mapgen.py` has.
"""

from __future__ import annotations

import math
import random

from . import scenery
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
    _carve_exit(tiles, cx, cy, seed)
    population = _dress_camp(tiles, cx, cy, seed)
    return TileMap(
        tiles,
        seed=seed,
        scenery=scenery.to_payload(population),
    )


def _dress_camp(tiles: list[list[int]], cx: float, cy: float, seed: int) -> scenery.Population:
    """A couple of scenes out at the edge of the clearing. Mutates `tiles`.

    The camp is a place the party owns, so it gets firewood and a sign and
    nothing that bled, and no crates. It also gets a lighter hand than the
    forest: the whole clearing is barely wider than one forest scene, and
    everything standing in it competes with the one thing the lobby is actually
    about, which is four characters around a fire.

    Two exclusions, and they are both hard. The HEARTH, because a woodpile
    standing where a player is sitting hides the character the roster is
    pointing at — the same rule the decoration mask enforces for grass. And the
    EXIT, because the walk-out marches the party through it on rails and a prop
    in the mouth would have bodies sliding through solid wood.
    """
    population = scenery.populate(
        tiles,
        random.Random(seed ^ 0xCA47),
        count=scenery.CAMP_SCENES,
        pool=scenery.CAMP_POOL,
        # The fire, not the first floor tile in scan order. The camp's treeline
        # is full of two-tile pockets; a flood that starts in one of those
        # answers "is the map connected?" with no before a scene has landed.
        anchor=(int(cx), int(cy)),
        # Tight, because the clearing has room for maybe three anchors and the
        # forest's spacing would reject all but one of them.
        separation=5.5,
        # The camp is mostly treeline, so most anchors land in woods that are
        # too thick to clear. The forest's budget would give up before finding
        # the handful of spots on the clearing's rim that actually work.
        tries=400,
        avoid=(
            (cx, cy, CAMP_HEARTH_TILES + 1.5),
            (cx + CAMP_CLEARING_TILES, cy, 6.0),
        ),
    )
    if any(prop.kind == "crate" for prop in population.props):
        raise ValueError("camp scenes must not place crates")
    return population


def _carve_exit(tiles: list[list[int]], cx: float, cy: float, seed: int) -> None:
    """Open a winding VOID path through the trees on the right.

    The mouth sits in the treeline, just past the clearing. The centreline
    wanders, the width breathes, and the edges fray so trunks still stand in
    the mouth — a gap in the woods, not a corridor. VOID is solid, so nobody
    walks in until the walk-out puppets them through.

    Numbers here are mirrored in `client/src/game/lobby-scene.ts` `carveExit`
    so the title screen's rest shot has the same kind of path.
    """
    fy = int(round(cy))
    start_x = int(cx + CAMP_CLEARING_TILES) + 1
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    if width <= start_x:
        return

    centre = float(fy)
    span = width - start_x
    half0 = float(CAMP_EXIT_HALF_TILES)

    for tx in range(start_x, width):
        t = (tx - start_x) / span
        centre += (fy - centre) * 0.18 + (_hash(tx, fy, seed, 21) - 0.5) * 1.05
        if centre < fy - 3.2:
            centre = fy - 3.2
        elif centre > fy + 3.2:
            centre = fy + 3.2

        pinch = 0.45 if tx >= width - BORDER_TILES else 1.0
        half = (
            half0 * (0.7 + (1.0 - t) * 0.4)
            + (_hash(tx, fy, seed, 22) - 0.5) * 0.75
        ) * pinch
        if half < 0.8:
            half = 0.8

        y0 = max(0, int(centre - half - 2))
        y1 = min(height - 1, int(centre + half + 2))
        for ty in range(y0, y1 + 1):
            dist = abs(ty - centre)
            if dist <= half * 0.5:
                tiles[ty][tx] = VOID
            elif dist <= half + 0.2:
                if not (tiles[ty][tx] == TREE and _hash(tx, ty, seed, 23) > 0.68):
                    tiles[ty][tx] = VOID
            elif dist <= half + 1.25 and _hash(tx, ty, seed, 24) < 0.22:
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
    """The shadowed exit as (mouth_x, centre_y, east_x) in world pixels.

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
