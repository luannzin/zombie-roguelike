"""The forest entrance: the camp's black corridor, continued.

Leaving the camp is a walk into VOID. Arriving in the forest is walking OUT of
the same kind of path, punched through a random edge of the map. The party does
not spawn in a clearing in the middle — they emerge, and then the woods eat the
way they came.

WHY THIS IS SERVER-SIDE
Same reason the camp exit is. The corridor is tiles (solid VOID, then TREE when
it seals), spawn positions are on those tiles, and every client has to agree
which edge opened. A hash cannot pick an edge and keep the mouth connected.

THE SEAL
VOID stays until every living body has stepped onto floor. Then the corridor
closes from the map edge inward, one rank of tiles at a time, so the dark path
is visibly swallowed rather than switched off. After that there is no exit.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .config import (
    CAMP_EXIT_HALF_TILES,
    ENTRANCE_DEPTH_TILES,
    ENTRANCE_MOUTH_TILES,
    PLAYER_HALF_HEIGHT,
    TILE_SIZE,
)
from .world import FLOOR, ROCK, TREE, VOID

OPEN = "open"
SEALING = "sealing"
GONE = "gone"

SIDES = ("e", "w", "n", "s")

#: Tiles of treeline the corridor is allowed to cut. Matches scenery.BORDER.
BORDER = 2
#: Keep the mouth off the map's corners so the camera has forest on both sides.
EDGE_MARGIN = 10
#: How far behind the mouth the party lines up, in tiles.
FORMATION_BACK = 4.2
#: How far past the mouth they are marched, onto floor.
EMERGE_PAST = 2.4
#: Seconds between seal ranks. Short enough to read as one slam, long enough
#: that each rank of trees is a beat rather than a pop.
SEAL_RANK_TIME = 0.08


def _hash(tx: int, ty: int, seed: int, salt: int = 0) -> float:
    """Deterministic 0..1 from a tile coordinate. Same mixer as camp._hash."""
    h = (tx * 374761393 + ty * 668265263 + ((seed ^ salt) * 2246822519)) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


@dataclass
class Entrance:
    """One forest arrival corridor, in world pixels plus the tiles it owns."""

    side: str
    mouth_x: float
    mouth_y: float
    back_x: float
    back_y: float
    dx: float
    dy: float
    state: str = OPEN
    elapsed: float = 0.0
    #: VOID tiles grouped by distance from the edge, nearest the edge first.
    #: Empty once gone. Rebuilt from the live grid if a room hydrates mid-seal.
    ranks: list[list[tuple[int, int]]] = field(default_factory=list)
    rank: int = 0

    def geometry_payload(self) -> dict:
        """Static half: where the corridor is. Rides on the map payload."""
        return {
            "side": self.side,
            "mouth": [round(self.mouth_x, 1), round(self.mouth_y, 1)],
            "back": [round(self.back_x, 1), round(self.back_y, 1)],
            "dir": [round(self.dx, 3), round(self.dy, 3)],
            **self.state_payload(),
        }

    def state_payload(self) -> dict:
        """Live half: open / sealing / gone. Snapshot when it changes."""
        return {"state": self.state, "t": round(self.elapsed, 2)}

    def past_mouth(self, x: float, y: float) -> bool:
        """True when a body has stepped through the mouth into the forest."""
        along = (x - self.mouth_x) * self.dx + (y - self.mouth_y) * self.dy
        return along >= TILE_SIZE * 1.15


def from_payload(row: dict | None) -> Entrance | None:
    if not row:
        return None
    return Entrance(
        side=str(row["side"]),
        mouth_x=float(row["mouth"][0]),
        mouth_y=float(row["mouth"][1]),
        back_x=float(row["back"][0]),
        back_y=float(row["back"][1]),
        dx=float(row["dir"][0]),
        dy=float(row["dir"][1]),
        state=str(row.get("state", OPEN)),
        elapsed=float(row.get("t", 0.0)),
    )


def hydrate(tiles: list[list[int]], row: dict | None) -> Entrance | None:
    """Rebuild a live entrance, including whatever VOID is still waiting to seal."""
    placed = from_payload(row)
    if placed is None:
        return None
    if placed.state != GONE:
        placed.ranks = _ranks(tiles, placed.side)
    return placed


def carve(tiles: list[list[int]], seed: int) -> Entrance:
    """Punch a winding VOID corridor through a random edge. Mutates `tiles`."""
    rng = random.Random(seed ^ 0xE071)
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    side = rng.choice(SIDES)
    depth = min(ENTRANCE_DEPTH_TILES, (width if side in ("e", "w") else height) - BORDER * 2 - 4)
    half0 = float(CAMP_EXIT_HALF_TILES)

    if side in ("e", "w"):
        along0 = rng.randint(EDGE_MARGIN, max(EDGE_MARGIN, height - 1 - EDGE_MARGIN))
    else:
        along0 = rng.randint(EDGE_MARGIN, max(EDGE_MARGIN, width - 1 - EDGE_MARGIN))

    centre = float(along0)
    void: list[tuple[int, int]] = []

    for step in range(depth):
        t = step / max(1, depth - 1)
        centre += (along0 - centre) * 0.16 + (rng.random() - 0.5) * 1.05
        lo = along0 - 3.4
        hi = along0 + 3.4
        if centre < lo:
            centre = lo
        elif centre > hi:
            centre = hi

        pinch = 0.5 if step < BORDER else 1.0
        half = (
            half0 * (0.72 + (1.0 - t) * 0.38)
            + (rng.random() - 0.5) * 0.7
        ) * pinch
        if half < 0.8:
            half = 0.8

        tx, ty = _along(side, step, centre, width, height)
        painted = _paint_slice(tiles, tx, ty, side, half, seed, step)
        void.extend(painted)

    mouth_step = depth - 1
    mouth_tx, mouth_ty = _along(side, mouth_step, centre, width, height)
    back_tx, back_ty = _along(side, 0, along0, width, height)
    dx, dy = _inward(side)
    _carve_mouth(tiles, mouth_tx, mouth_ty, dx, dy, seed)

    ranks = _group_ranks(void, side)
    return Entrance(
        side=side,
        mouth_x=(mouth_tx + 0.5) * TILE_SIZE,
        mouth_y=(mouth_ty + 0.5) * TILE_SIZE,
        back_x=(back_tx + 0.5) * TILE_SIZE,
        back_y=(back_ty + 0.5) * TILE_SIZE,
        dx=dx,
        dy=dy,
        ranks=ranks,
    )


def _inward(side: str) -> tuple[float, float]:
    if side == "e":
        return (-1.0, 0.0)
    if side == "w":
        return (1.0, 0.0)
    if side == "n":
        return (0.0, 1.0)
    return (0.0, -1.0)


def _along(side: str, step: int, centre: float, width: int, height: int) -> tuple[int, int]:
    """Tile on the corridor centreline `step` tiles in from the edge."""
    c = int(round(centre))
    if side == "e":
        return width - 1 - step, max(0, min(height - 1, c))
    if side == "w":
        return step, max(0, min(height - 1, c))
    if side == "n":
        return max(0, min(width - 1, c)), step
    return max(0, min(width - 1, c)), height - 1 - step


def _paint_slice(
    tiles: list[list[int]],
    cx: int,
    cy: int,
    side: str,
    half: float,
    seed: int,
    step: int,
) -> list[tuple[int, int]]:
    """VOID a cross-section of the corridor, frayed like the camp exit."""
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    painted: list[tuple[int, int]] = []
    across = side in ("e", "w")
    span = int(math.ceil(half + 1.4))
    for d in range(-span, span + 1):
        if across:
            tx, ty = cx, cy + d
        else:
            tx, ty = cx + d, cy
        if not (0 <= tx < width and 0 <= ty < height):
            continue
        dist = abs(d)
        mark = False
        if dist <= half * 0.5:
            mark = True
        elif dist <= half + 0.2:
            mark = not (tiles[ty][tx] == TREE and _hash(tx, ty, seed, 23 + step) > 0.68)
        elif dist <= half + 1.25 and _hash(tx, ty, seed, 24 + step) < 0.22:
            mark = True
        if mark:
            tiles[ty][tx] = VOID
            painted.append((tx, ty))
    return painted


def _carve_mouth(
    tiles: list[list[int]],
    mx: int,
    my: int,
    dx: float,
    dy: float,
    seed: int,
) -> None:
    """Open floor at the inner end so the VOID hands the party to the forest.

    Tiles further toward the edge than the mouth stay VOID — that is the
    corridor. Everything on the forest side of the mouth, inside the clearing,
    becomes walkable. A mouth that stayed VOID would trap them on solid dark.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    radius = ENTRANCE_MOUTH_TILES
    r2 = radius * radius
    for ty in range(max(0, int(my - radius)), min(height, int(my + radius) + 1)):
        for tx in range(max(0, int(mx - radius)), min(width, int(mx + radius) + 1)):
            if (tx - mx) ** 2 + (ty - my) ** 2 > r2:
                continue
            # Behind the mouth is the corridor. Do not flatten it.
            if (tx - mx) * dx + (ty - my) * dy < -0.4:
                continue
            # The solid world-edge stays woods except where VOID already cut it.
            if tx < BORDER or ty < BORDER or tx >= width - BORDER or ty >= height - BORDER:
                continue
            if tiles[ty][tx] == VOID:
                tiles[ty][tx] = FLOOR
            elif tiles[ty][tx] in (TREE, ROCK):
                tiles[ty][tx] = FLOOR
            elif tiles[ty][tx] != FLOOR:
                continue
            # A couple of boulders on the rim, never in the landing strip.
            if (tx - mx) ** 2 + (ty - my) ** 2 > (radius * 0.55) ** 2:
                if _hash(tx, ty, seed, 31) > 0.93:
                    tiles[ty][tx] = ROCK


def _rank_of(tx: int, ty: int, side: str) -> int:
    if side == "e":
        return -tx
    if side == "w":
        return tx
    if side == "n":
        return ty
    return -ty


def _group_ranks(void: list[tuple[int, int]], side: str) -> list[list[tuple[int, int]]]:
    buckets: dict[int, list[tuple[int, int]]] = {}
    for tx, ty in void:
        buckets.setdefault(_rank_of(tx, ty, side), []).append((tx, ty))
    return [buckets[key] for key in sorted(buckets)]


def _ranks(tiles: list[list[int]], side: str) -> list[list[tuple[int, int]]]:
    void = [
        (tx, ty)
        for ty, row in enumerate(tiles)
        for tx, kind in enumerate(row)
        if kind == VOID
    ]
    return _group_ranks(void, side)


def formation_slots(
    placed: Entrance,
    seating: list[str],
    present: set[str],
) -> dict[str, tuple[float, float]]:
    """Two staggered files inside the corridor, facing the forest."""
    ids = [pid for pid in seating if pid in present]
    back_x = placed.mouth_x - placed.dx * TILE_SIZE * FORMATION_BACK
    back_y = placed.mouth_y - placed.dy * TILE_SIZE * FORMATION_BACK
    px, py = -placed.dy, placed.dx
    slots: dict[str, tuple[float, float]] = {}
    for index, pid in enumerate(ids):
        file = index % 2
        col = index // 2
        along = -col * TILE_SIZE * 1.3
        if file == 1:
            along += TILE_SIZE * 0.35
        across = (1 if file else -1) * TILE_SIZE * 0.6
        x = back_x + placed.dx * along + px * across
        y = back_y + placed.dy * along + py * across
        x += _wobble(index, 1) * TILE_SIZE * 0.3
        y += _wobble(index, 2) * TILE_SIZE * 0.16
        slots[pid] = (x, y - PLAYER_HALF_HEIGHT)
    return slots


def emerge_point(placed: Entrance, slot_x: float, slot_y: float) -> tuple[float, float]:
    """Where this body is marched to: past the mouth, same file."""
    px, py = -placed.dy, placed.dx
    across = (slot_x - placed.mouth_x) * px + (slot_y - placed.mouth_y) * py
    x = placed.mouth_x + placed.dx * TILE_SIZE * EMERGE_PAST + px * across
    y = placed.mouth_y + placed.dy * TILE_SIZE * EMERGE_PAST + py * across
    return x, y


def mouth_spawns(
    placed: Entrance,
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Floor spawns around the mouth, nearest first. Used after the seal."""
    mx, my = placed.mouth_x, placed.mouth_y
    dx, dy = placed.dx, placed.dy

    def score(p: tuple[float, float]) -> float:
        x, y = p
        along = (x - mx) * dx + (y - my) * dy
        # Prefer just inside the forest, not back toward the (now gone) path.
        if along < 0:
            along = -along * 4
        across = abs((x - mx) * -dy + (y - my) * dx)
        return along + across * 0.35

    return sorted(points, key=score)


def seal_rank(tiles: list[list[int]], placed: Entrance) -> list[tuple[int, int, int]]:
    """Convert the next rank of VOID into woods. Returns (tx, ty, kind) patches.

    TREE is the default — the forest closing. A few ROCKS so the slam is not a
    planted row of identical trunks. Hashed, so two clients sealing the same
    map grow the same woods.
    """
    if placed.rank >= len(placed.ranks):
        return []
    wave = placed.ranks[placed.rank]
    placed.rank += 1
    patches: list[tuple[int, int, int]] = []
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    for tx, ty in wave:
        if not (0 <= tx < width and 0 <= ty < height):
            continue
        if tiles[ty][tx] != VOID:
            continue
        kind = ROCK if _hash(tx, ty, tx * 13 + ty, 40) > 0.86 else TREE
        tiles[ty][tx] = kind
        patches.append((tx, ty, kind))
    return patches


def _wobble(index: int, salt: int) -> float:
    h = (index * 374761393 + salt * 668265263) & 0xFFFFFFFF
    h ^= h >> 13
    return ((h & 0xFFFF) / 0xFFFF) - 0.5
