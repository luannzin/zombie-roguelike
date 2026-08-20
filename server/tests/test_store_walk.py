"""The shop has to be WALKABLE, and that is the one thing its layout can break.

Run:  python tests/test_store_walk.py   (from server/)

`store._tiles` clears a SPINE up the centreline so the generator's own noise —
a pinched neck plus an unlucky boulder — can never wall the yard off from its
own door. That guarantee used to be absolute because nothing was authored on
the spine: the trader stood on the west rim and his stock on the east one.

It is not absolute any more, in two ways. A landing skid claims tiles on the
centreline and the party goes AROUND it. And the zone is a BUILDING now: the
spine stops at the shop's south wall, and from there the only ways through are
two gaps `store._stamp_shop` punches in the masonry — a door in the south wall
and the exit corridor's mouth in the north one. A fixture nudged across either
of them walls a party into a shop they cannot leave, or out of one they cannot
enter, and nothing else in the codebase would notice.

So the check is the thing that actually matters rather than the rule that used
to imply it: from the arrival mouth, can you reach the exit mouth, the
merchant, every stall and the cabinet — walking on open tiles only, after every
fixture has claimed its footprint.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402
from app.config import STORE_BUY_DIST, STORE_SPIN_DIST, TILE_SIZE  # noqa: E402
from app.world import FIRE, FLOOR, ROCK, TILEFLOOR  # noqa: E402

#: What a body may stand on. Mirrors `world.GROUNDS`: soil out in the yard and
#: the shop's laid brick floor indoors. Everything else — trees, the LOW
#: footprint under a table or a counter section, a landed skid, the fire, the
#: masonry, the VOID in the corridors — is not walkable.
OPEN = {FLOOR, TILEFLOOR}


def reachable(tiles: list[list[int]], start: tuple[int, int]) -> set[tuple[int, int]]:
    """Every tile a body can walk to from `start`, four-connected."""
    height = len(tiles)
    width = len(tiles[0])
    seen = {start}
    queue = deque([start])
    while queue:
        tx, ty = queue.popleft()
        for nx, ny in ((tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in seen or tiles[ny][nx] not in OPEN:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


def near(seen: set[tuple[int, int]], x: float, y: float, reach: float) -> bool:
    """Is any reachable tile close enough to `(x, y)` to interact with it?

    Measured in world pixels against the same distance the server checks, so a
    stall the party can see but not stand within `STORE_BUY_DIST` of counts as
    unreachable — which is what it is.
    """
    for tx, ty in seen:
        cx = (tx + 0.5) * TILE_SIZE
        cy = (ty + 1.0) * TILE_SIZE
        if (cx - x) ** 2 + (cy - y) ** 2 <= reach * reach:
            return True
    return False


def check(day: int, seed: int) -> None:
    world = store.build_store(day, seed, takes=[120, 90, 60])
    tiles = world.tiles
    height = len(tiles)
    width = len(tiles[0])
    payload = world.store

    # Start where the party actually arrives: the first open row in front of
    # the south mouth. The corridor itself is VOID and nobody stands in it, and
    # the search walks INWARD from the mouth rather than up from the bottom of
    # the map — the treeline is full of stray open tiles that are nowhere.
    def inward(gate: dict) -> tuple[int, int] | None:
        mx = int(gate["mouth"][0] // TILE_SIZE)
        my = int(gate["mouth"][1] // TILE_SIZE)
        step = int(gate["dir"][1]) or 1
        for ahead in range(0, 8):
            ty = my + step * ahead
            if not (0 <= ty < height):
                break
            for dx in (0, -1, 1, -2, 2):
                tx = mx + dx
                if 0 <= tx < width and tiles[ty][tx] in OPEN:
                    return (tx, ty)
        return None

    start = inward(world.entrance)
    assert start, f"day {day} seed {seed}: no open ground inside the south mouth"

    seen = reachable(tiles, start)

    # The way out. Same treatment: the corridor is VOID, so what has to be
    # reachable is the open ground in front of it.
    exit_ok = inward(world.egress) in seen
    assert exit_ok, f"day {day} seed {seed}: the exit is walled off from the entrance"

    mx, my = payload["merchant"]
    # He is BEHIND a counter now, so the nearest tile a body can occupy is on
    # the other side of it. Three tiles is the counter's depth plus a body —
    # any further and "walked up to" stops meaning anything.
    assert near(seen, mx, my, TILE_SIZE * 3.0), (
        f"day {day} seed {seed}: the merchant cannot be walked up to"
    )

    # THE DOOR AND THE SHELVES. The door is the only way into the building and
    # the shelves are the only fixture bolted to a wall the party never touches
    # — if a shelf has drifted off the north wall into the pocket, the merchant
    # is standing inside it.
    dx, dy = payload["door"]
    assert near(seen, dx, dy, TILE_SIZE * 1.5), (
        f"day {day} seed {seed}: the shop's door is not walkable"
    )

    # Every counter section, shelf and crate has to be INSIDE the building.
    # A fixture authored off the interior's centre that landed in the masonry
    # or out in the yard is an offset somebody typed wrong.
    left, top, right, bottom = store.shop_bounds(width)
    for name in ("counter", "shelves", "crates", "rugs", "lamps"):
        for row in payload[name]:
            fx, fy = row[0], row[1]
            tx = int(fx // TILE_SIZE)
            ty = int((fy - 1e-6) // TILE_SIZE)
            assert left < tx < right and top < ty < bottom, (
                f"day {day} seed {seed}: {name} at ({tx},{ty}) is not inside "
                f"the shop ({left}..{right}, {top}..{bottom})"
            )

    for stand in payload["stands"]:
        assert near(seen, stand["x"], stand["y"], STORE_BUY_DIST), (
            f"day {day} seed {seed}: stall {stand['id']} is out of buying reach"
        )

    cx, cy = payload["machine"]
    assert near(seen, cx, cy, STORE_SPIN_DIST), (
        f"day {day} seed {seed}: the cabinet's lever cannot be reached"
    )

    # Nothing may be standing in the fire, and the fire must be a tile — it is
    # what the client's campfire sprite and its light both hang off.
    fires = sum(row.count(FIRE) for row in tiles)
    assert fires == 1, f"day {day} seed {seed}: expected one campfire, found {fires}"

    # Sanity on the room itself: a clearing this small is easy to fill up by
    # accident, and a shop with nowhere to stand is the failure this whole file
    # is about.
    open_tiles = sum(row.count(FLOOR) + row.count(ROCK) + row.count(TILEFLOOR) for row in tiles)
    assert len(seen) > open_tiles * 0.55, (
        f"day {day} seed {seed}: only {len(seen)} of {open_tiles} open tiles "
        "are reachable — something split the room in two"
    )


def main() -> None:
    for day in range(1, 7):
        for seed in (1, 7, 99, 1337, 20250819):
            check(day, seed)
    print("ok")


if __name__ == "__main__":
    main()
