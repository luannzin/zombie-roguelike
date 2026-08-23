"""THE LANDING: the round yard the Sawyer is fought in.

One map, built once per boss night, and it is deliberately the simplest
geometry in the game: a circle of open ground with a ring of fires round the
rim and nothing in the middle. Everything else the generator does is DRESSING.

WHY A CIRCLE AND NOT A CLEARING.
`mapgen.py` builds forests out of noise, and a forest is the right shape for
the thing a forest is for — you cannot see across it, cover is everywhere, and
finding anything is the game. A boss fight is the opposite activity. It wants
one legible space, no dead ends to be cornered in, no rock to lose a 41-pixel
chainsaw behind, and a rim you can put your back to without being safe. So this
map is authored rather than generated: a disc, a corridor in, and a ring of
light. There is nothing to explore here because exploring is over.

THE FIRES ARE TILES, NOT PROPS, AND THAT IS THE WHOLE LIGHTING DESIGN.
`world.FIRE` already blocks a body, draws an animated flame and throws
`CAMPFIRE_LIGHT_TILES` of light — the camp is built out of them. So the ring
is nine of those tiles, and the arena gets its light, its shadows and its rim
for free, with no new client code and no new asset. It also gets the thing the
zone actually needs: the boss is lit FROM BEHIND wherever he stands, so a
three-and-a-half tile silhouette against a fire is readable from anywhere in
the ring.

That is why this zone keeps `ambient` at zero like every other place a player
can be killed (see `zones.py`). The rule was never "hostile places are hard to
see in" — it is that light must come from something you can point at. Nine
burning drums is an answer to "why can I see"; a floor value is not.

THE EXIT IS SHUT UNTIL HE IS DOWN, and it is shut by simply not existing:
`build_arena` carves the arrival corridor and nothing else, and `Room` calls
`entrance.open_exit` on the frame the boss dies. A door that is drawn and
locked invites a party to stand in it; a treeline with no gap in it is a
treeline.
"""

from __future__ import annotations

import math
import random

from . import entrance, scenery
from .config import (
    ARENA_FIRES,
    ARENA_RADIUS_TILES,
    TILE_SIZE,
)
from .maps import count_reachable
from .world import FIRE, FLOOR, ROCK, TileMap

#: Tiles of treeline outside the ring. Enough that the corridor has somewhere
#: to run and the border is never the thing you are looking at.
MARGIN = 9
#: How far in from the rim the drums stand.
FIRE_INSET = 1.6
#: The lane that joins the arrival corridor to the ring, in tiles either side.
LANE_HALF = 2


def size() -> tuple[int, int]:
    span = int(ARENA_RADIUS_TILES * 2) + MARGIN * 2
    return span, span


def _disc(tiles: list[list[int]], cx: float, cy: float, radius: float) -> None:
    height = len(tiles)
    width = len(tiles[0])
    for ty in range(height):
        for tx in range(width):
            if math.hypot(tx + 0.5 - cx, ty + 0.5 - cy) <= radius:
                tiles[ty][tx] = FLOOR


def _lane(tiles: list[list[int]], x0: float, y0: float, x1: float, y1: float) -> None:
    """A straight walk from the corridor mouth to the ring.

    The corridor lands somewhere random along the south edge and the ring is a
    circle, so the two do not meet on their own. Carving toward the CENTRE
    rather than to the nearest rim point is what keeps the approach pointed at
    the fight: a player walks out of the dark facing the middle of the yard,
    which is where he lands.
    """
    steps = int(math.hypot(x1 - x0, y1 - y0) * 2) + 1
    height = len(tiles)
    width = len(tiles[0])
    for step in range(steps + 1):
        t = step / steps
        cx = x0 + (x1 - x0) * t
        cy = y0 + (y1 - y0) * t
        for dy in range(-LANE_HALF, LANE_HALF + 1):
            for dx in range(-LANE_HALF, LANE_HALF + 1):
                tx, ty = int(cx) + dx, int(cy) + dy
                if 0 <= tx < width and 0 <= ty < height and tiles[ty][tx] == ROCK:
                    tiles[ty][tx] = FLOOR


def _seal_islands(tiles: list[list[int]]) -> int:
    """Fill any pocket of floor that is not the yard. Returns how many.

    `entrance.carve` paints a threshold at its mouth and the winding corridor
    it cuts sometimes leaves a single tile of ground stranded in the treeline
    beside it — a tile nobody can reach, which fails the connectivity check
    the whole map is validated by. Filling it is right rather than convenient:
    a one-tile clearing behind a wall is not a place, and the alternative
    (widening the lane until it happens to swallow it) tunes a corridor to fix
    a rounding error.
    """
    height = len(tiles)
    width = len(tiles[0])
    seen: set[tuple[int, int]] = set()
    groups: list[list[tuple[int, int]]] = []
    for ty in range(height):
        for tx in range(width):
            if tiles[ty][tx] != FLOOR or (tx, ty) in seen:
                continue
            stack = [(tx, ty)]
            seen.add((tx, ty))
            group = [(tx, ty)]
            while stack:
                x, y = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if (0 <= nx < width and 0 <= ny < height
                            and tiles[ny][nx] == FLOOR and (nx, ny) not in seen):
                        seen.add((nx, ny))
                        group.append((nx, ny))
                        stack.append((nx, ny))
            groups.append(group)
    if not groups:
        return 0
    groups.sort(key=len, reverse=True)
    filled = 0
    for group in groups[1:]:
        for (tx, ty) in group:
            tiles[ty][tx] = ROCK
            filled += 1
    return filled


def _ring_fires(tiles: list[list[int]], cx: float, cy: float, radius: float,
                keep_clear: tuple[float, float]) -> list[tuple[int, int]]:
    """The drums, evenly round the rim, with a GAP where the party walks in.

    The gap is not decoration. A fire is a solid tile, and a ring of them with
    no gap in it is a wall the arrival lane has to be cut through — which
    reads, correctly, as the game having put an obstacle in the doorway.
    """
    placed: list[tuple[int, int]] = []
    ax, ay = keep_clear
    gate = math.atan2(ay - cy, ax - cx)
    for index in range(ARENA_FIRES):
        angle = math.tau * index / ARENA_FIRES
        # Rotate the whole ring so no drum ever lands on the entrance.
        angle += gate + math.pi / ARENA_FIRES
        tx = int(cx + math.cos(angle) * (radius - FIRE_INSET))
        ty = int(cy + math.sin(angle) * (radius - FIRE_INSET))
        if 0 <= ty < len(tiles) and 0 <= tx < len(tiles[0]) and tiles[ty][tx] == FLOOR:
            tiles[ty][tx] = FIRE
            placed.append((tx, ty))
    return placed


def _dress(cx: float, cy: float, radius: float, rng: random.Random,
           fires: list[tuple[int, int]]) -> list[scenery.Prop]:
    """What the crew left. Flat marks and low junk, and NOTHING in the middle.

    The centre third of the ring is deliberately bare. Every prop in this game
    is drawn in the depth sort, so a log lying where the boss lands is a log
    the boss disappears behind on the one frame the fight is announced — and
    at four times a creature's size he is behind something on a lot of frames.
    Dressing goes on the OUTER band, where it says what the place was without
    ever being between the camera and the fight.
    """
    props: list[scenery.Prop] = []

    def at(angle: float, r: float) -> tuple[float, float]:
        return ((cx + math.cos(angle) * r) * TILE_SIZE,
                (cy + math.sin(angle) * r) * TILE_SIZE)

    # Log decks: the reason this clearing exists. Stacked round the rim, in
    # pairs, because one is litter and two is a place somebody worked.
    for index in range(6):
        angle = math.tau * (index + 0.35) / 6
        x, y = at(angle, radius * 0.86)
        props.append(scenery.Prop("logs", x, y, rng.randrange(4),
                                  rng.random() < 0.5, scenery.STANDING))
        x, y = at(angle + 0.10, radius * 0.80)
        props.append(scenery.Prop("logs", x, y, rng.randrange(4),
                                  rng.random() < 0.5, scenery.STANDING))

    # The crew. Blood into the dirt, bones, what they were wearing — the
    # answer to "where did the other zombies come from" is standing in it.
    for index in range(14):
        angle = rng.uniform(0.0, math.tau)
        r = radius * rng.uniform(0.42, 0.94)
        x, y = at(angle, r)
        props.append(scenery.Prop("blood", x, y, rng.randrange(6), False, scenery.DECAL))
    for index in range(7):
        angle = rng.uniform(0.0, math.tau)
        r = radius * rng.uniform(0.50, 0.92)
        x, y = at(angle, r)
        kind = "bones" if index % 2 else "clothes"
        props.append(scenery.Prop(kind, x, y, rng.randrange(5),
                                  rng.random() < 0.5, scenery.DECAL))
    for index in range(9):
        angle = rng.uniform(0.0, math.tau)
        r = radius * rng.uniform(0.55, 0.95)
        x, y = at(angle, r)
        props.append(scenery.Prop("debris", x, y, rng.randrange(6),
                                  rng.random() < 0.5, scenery.DECAL))

    # Spilled fuel under the drums. It is what they are burning, and it is the
    # one mark on this map that explains the light.
    for (tx, ty) in fires:
        angle = math.atan2(ty + 0.5 - cy, tx + 0.5 - cx)
        x = (tx + 0.5 - math.cos(angle) * 1.4) * TILE_SIZE
        y = (ty + 0.5 - math.sin(angle) * 1.4) * TILE_SIZE
        props.append(scenery.Prop("oil", x, y, rng.randrange(4), False, scenery.DECAL))

    # Boot prints, all pointing the same way: OUT. Whoever was here ran, and
    # they ran toward the corridor the party has just walked in through.
    for index in range(10):
        angle = rng.uniform(0.0, math.tau)
        r = radius * rng.uniform(0.30, 0.88)
        x, y = at(angle, r)
        props.append(scenery.Prop("tracks", x, y, rng.randrange(8), False, scenery.DECAL))

    return props


def build_arena(day: int, seed: int | None = None) -> TileMap:
    """The yard, its corridor and its ring of fires. Raises on a broken map."""
    used = random.randrange(1, 2**31) if seed is None else seed
    rng = random.Random(used ^ 0x5A77)
    width, height = size()
    tiles = [[ROCK for _ in range(width)] for _ in range(height)]
    cx, cy = width / 2.0, height / 2.0
    radius = float(ARENA_RADIUS_TILES)
    _disc(tiles, cx, cy, radius)

    # SOUTH, always. Every other corridor in the game picks its edge at random
    # and this one does not: the camera looks down the screen, so a party that
    # walks in from the south walks INTO the yard with the fight in front of
    # them. Arriving from the north would put the boss's landing behind their
    # own backs on the one beat that has to be seen.
    gate = entrance.carve(tiles, used, side="s")
    mouth_tx = gate.mouth_x / TILE_SIZE
    mouth_ty = gate.mouth_y / TILE_SIZE
    tiles[int(mouth_ty)][int(mouth_tx)] = FLOOR
    _lane(tiles, mouth_tx, mouth_ty, cx, cy)

    _seal_islands(tiles)
    fires = _ring_fires(tiles, cx, cy, radius, (mouth_tx, mouth_ty))

    floor = sum(row.count(FLOOR) for row in tiles)
    if count_reachable(tiles) != floor:
        raise ValueError(f"arena seed {used} has unreachable floor")

    props = _dress(cx, cy, radius, rng, fires)
    payload = {
        "propKinds": sorted({prop.kind for prop in props}),
        "props": [],
        "lights": [],
    }
    kinds = payload["propKinds"]
    payload["props"] = [prop.to_row(kinds) for prop in props]

    return TileMap(
        tiles,
        seed=used,
        scenery=payload,
        entrance=gate.geometry_payload(),
    )


def centre(world: TileMap) -> tuple[float, float]:
    """The middle of the ring, in world pixels. Where he lands."""
    return (world.width / 2.0 * TILE_SIZE, world.height / 2.0 * TILE_SIZE)


def boss_spawn(world: TileMap) -> tuple[float, float]:
    """Where the Sawyer comes down: the middle, a little north of it.

    North of centre rather than ON it, because the party enters from the south
    and the landing should be in front of them rather than on top of them —
    a boss that lands where the first player is standing is a boss that opens
    the fight by killing somebody for walking forward.
    """
    x, y = centre(world)
    return x, y - TILE_SIZE * 3.0
