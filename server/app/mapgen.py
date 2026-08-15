"""Procedural forest generation.

Produces the same `list[list[int]]` that `maps.py` hand-draws, so everything
downstream — collision, pathing, the wire format, the client — is unchanged.
The only new thing is the tile alphabet: FLOOR / ROCK / TREE (see world.py).

Shape of the result, and why:

  * It is a FOREST, not a dungeon. There are no corridors and no doors. Cover
    comes from thickets and boulder fields with open ground between them, which
    is what makes a lantern interesting: you lose sight of a zombie behind a
    treeline, not behind a doorframe.
  * The CENTRE is always a clearing. Players spawn there together (see
    Room.pick_spawn), so it has to be open and it has to be reachable from
    everywhere.
  * It is CONNECTED. Noise happily produces sealed pockets; step 6 finds them
    and either drills them out or fills them in. `build_forest` asserts the
    result, the same guarantee `build_arena` gives.

Determinism: one seed in, one map out. The seed also ships to the client, which
uses it to place decoration.
"""

from __future__ import annotations

import math
import random

from . import crates, loot, rift, scenery
from .maps import count_reachable
from .world import FLOOR, ROCK, TREE, TileMap

# --- authoring knobs ---------------------------------------------------------
# Map size in tiles. Big enough that the lantern radius (11 tiles) never lights
# the whole thing, so fog of war has something to hide.
DEFAULT_WIDTH = 96
DEFAULT_HEIGHT = 64

# Noise thresholds. The band between them is the fringe of a thicket, which is
# where rocks go — a treeline that fades into scattered boulders reads as a
# natural edge, a hard tree/floor boundary reads as a wall.
TREE_THRESHOLD = 0.62
ROCK_THRESHOLD = 0.555

# Loose cover scattered over open ground, as a fraction of total tiles. Without
# this the noise leaves wide bald fields with nothing to break a sightline.
BOULDER_DENSITY = 0.014
LONE_TREE_DENSITY = 0.010
# Glades: open circles punched through the thickets so the map breathes.
GLADE_COUNT = (6, 10)
GLADE_RADIUS = (3.0, 5.5)

CENTRE_CLEARING_TILES = 6.0
BORDER_TILES = 2

# A sealed pocket smaller than this is filled solid; anything larger earns a
# corridor. Drilling out every 3-tile hole would leave the map full of stubs.
MIN_POCKET_TILES = 12


def _fade(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class _ValueNoise:
    """Bilinear value noise on a random lattice. Cheap and good enough here."""

    def __init__(self, seed: int, cell: float):
        self.seed = seed
        self.cell = cell
        self.grid: dict[tuple[int, int], float] = {}

    def _at(self, gx: int, gy: int) -> float:
        key = (gx, gy)
        value = self.grid.get(key)
        if value is None:
            # Hashed per lattice point, so the field does not depend on the
            # order tiles happen to be visited in.
            value = random.Random((gx * 73856093) ^ (gy * 19349663) ^ self.seed).random()
            self.grid[key] = value
        return value

    def sample(self, x: float, y: float) -> float:
        fx = x / self.cell
        fy = y / self.cell
        gx = math.floor(fx)
        gy = math.floor(fy)
        tx = _fade(fx - gx)
        ty = _fade(fy - gy)
        top = self._at(gx, gy) * (1 - tx) + self._at(gx + 1, gy) * tx
        bottom = self._at(gx, gy + 1) * (1 - tx) + self._at(gx + 1, gy + 1) * tx
        return top * (1 - ty) + bottom * ty


def _fbm(octaves: list[_ValueNoise], x: float, y: float) -> float:
    total = 0.0
    weight = 0.0
    amplitude = 1.0
    for octave in octaves:
        total += amplitude * octave.sample(x, y)
        weight += amplitude
        amplitude *= 0.5
    return total / weight


def _carve_circle(tiles: list[list[int]], cx: float, cy: float, radius: float) -> None:
    height = len(tiles)
    width = len(tiles[0])
    r2 = radius * radius
    for ty in range(max(0, int(cy - radius)), min(height, int(cy + radius) + 1)):
        for tx in range(max(0, int(cx - radius)), min(width, int(cx + radius) + 1)):
            if (tx - cx) ** 2 + (ty - cy) ** 2 <= r2:
                tiles[ty][tx] = FLOOR


def _regions(tiles: list[list[int]]) -> list[list[tuple[int, int]]]:
    """Every connected floor region, largest first."""
    height = len(tiles)
    width = len(tiles[0])
    seen = [[False] * width for _ in range(height)]
    found: list[list[tuple[int, int]]] = []

    for sy in range(height):
        for sx in range(width):
            if tiles[sy][sx] != FLOOR or seen[sy][sx]:
                continue
            region = []
            stack = [(sx, sy)]
            seen[sy][sx] = True
            while stack:
                x, y = stack.pop()
                region.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        if tiles[ny][nx] == FLOOR and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            found.append(region)

    found.sort(key=len, reverse=True)
    return found


def _drill(tiles: list[list[int]], start: tuple[int, int], goal: tuple[int, int]) -> None:
    """Clear an L-shaped 2-tile-wide trail between two points."""
    x, y = start
    gx, gy = goal
    while x != gx:
        x += 1 if gx > x else -1
        _carve_circle(tiles, x, y, 1.2)
    while y != gy:
        y += 1 if gy > y else -1
        _carve_circle(tiles, x, y, 1.2)


def _connect(tiles: list[list[int]], centre: tuple[int, int]) -> None:
    """Make every floor tile reachable from the centre clearing.

    Small pockets are filled solid (they are noise artefacts, not places).
    Larger ones get a trail drilled to the nearest tile of the main region, so
    the map keeps its interesting shapes instead of losing them to the fill.
    """
    for _ in range(8):
        regions = _regions(tiles)
        if len(regions) <= 1:
            return

        main = next(
            (r for r in regions if centre in r),
            regions[0],
        )
        main_set = set(main)

        for region in regions:
            if region is main:
                continue
            if len(region) < MIN_POCKET_TILES:
                for x, y in region:
                    tiles[y][x] = ROCK
                continue
            # Nearest pair between the pocket and the main region. Both are
            # sampled rather than scanned in full: a 6000-tile map would
            # otherwise make this quadratic for no visual gain.
            source = min(region, key=lambda p: (p[0] - centre[0]) ** 2 + (p[1] - centre[1]) ** 2)
            target = min(
                main_set,
                key=lambda p: (p[0] - source[0]) ** 2 + (p[1] - source[1]) ** 2,
            )
            _drill(tiles, source, target)


def generate_forest(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    seed: int | None = None,
) -> tuple[list[list[int]], int]:
    """Build one forest. Returns (tiles, seed_actually_used)."""
    if seed is None:
        seed = random.randrange(1, 2**31)
    rng = random.Random(seed)

    octaves = [
        _ValueNoise(seed + index * 7919, cell)
        # Lattice cells in tiles. Kept well under the map size: one big octave
        # produces a map that is half thicket and half empty field, which reads
        # as two places rather than a forest.
        for index, cell in enumerate((13.0, 6.5, 3.25))
    ]

    tiles = [[FLOOR] * width for _ in range(height)]

    # 1. thickets and their rocky fringe
    for ty in range(height):
        for tx in range(width):
            density = _fbm(octaves, tx, ty)
            if density > TREE_THRESHOLD:
                tiles[ty][tx] = TREE
            elif density > ROCK_THRESHOLD:
                tiles[ty][tx] = ROCK

    # 2. loose cover on open ground, so the flat parts still break sightlines:
    #    boulder clusters, plus single trees standing away from the thickets
    for _ in range(int(width * height * BOULDER_DENSITY)):
        bx = rng.randrange(BORDER_TILES, width - BORDER_TILES)
        by = rng.randrange(BORDER_TILES, height - BORDER_TILES)
        if tiles[by][bx] != FLOOR:
            continue
        for _ in range(rng.randint(1, 3)):
            ox = bx + rng.randint(-1, 1)
            oy = by + rng.randint(-1, 1)
            if 0 <= ox < width and 0 <= oy < height:
                tiles[oy][ox] = ROCK

    for _ in range(int(width * height * LONE_TREE_DENSITY)):
        tx = rng.randrange(BORDER_TILES, width - BORDER_TILES)
        ty = rng.randrange(BORDER_TILES, height - BORDER_TILES)
        if tiles[ty][tx] == FLOOR:
            tiles[ty][tx] = TREE

    # 3. glades — open circles so the map has rooms without having rooms
    for _ in range(rng.randint(*GLADE_COUNT)):
        _carve_circle(
            tiles,
            rng.uniform(width * 0.12, width * 0.88),
            rng.uniform(height * 0.12, height * 0.88),
            rng.uniform(*GLADE_RADIUS),
        )

    # 4. the spawn clearing
    cx = width // 2
    cy = height // 2
    _carve_circle(tiles, cx, cy, CENTRE_CLEARING_TILES)

    # 5. solid treeline border — the edge of the world is woods, not a wall
    for ty in range(height):
        for tx in range(width):
            if (
                tx < BORDER_TILES
                or ty < BORDER_TILES
                or tx >= width - BORDER_TILES
                or ty >= height - BORDER_TILES
            ):
                tiles[ty][tx] = TREE

    # 6. guarantee everything is reachable from the clearing
    _connect(tiles, (cx, cy))

    return tiles, seed


def populate_forest(
    tiles: list[list[int]],
    seed: int,
) -> scenery.Population:
    """Lay the story over a finished forest. Mutates `tiles`.

    Runs AFTER connectivity, never before: a scene needs a box of open ground
    to stand in, and `_connect` is the step that decides which ground is open.
    Its own building footprints are re-checked against connectivity inside
    `scenery.populate`, which reverts rather than drilling.

    The spawn clearing is excluded with a generous radius. It is the first
    thing every player sees and the one place the party has to be able to read
    each other; a cabin in it would be the best-lit prop in the game and the
    worst-placed one.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    return scenery.populate(
        tiles,
        random.Random(seed ^ 0x5CE7E),
        landmark=scenery.LANDMARK,
        # One thread linking the scenes into a single route outward from the
        # spawn clearing. The camp does not get one: it is four scenes of
        # firewood around a fire, and a blood trail through it would be the
        # wrong promise.
        thread=True,
        avoid=((width / 2, height / 2, CENTRE_CLEARING_TILES + 6.0),),
    )


def build_forest(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    seed: int | None = None,
) -> TileMap:
    """Generate, populate and validate. Raises rather than shipping a broken map."""
    tiles, used = generate_forest(width, height, seed)
    population = populate_forest(tiles, used)
    floor = sum(row.count(FLOOR) for row in tiles)
    reachable = count_reachable(tiles)
    if reachable != floor:
        raise ValueError(
            f"forest seed {used} has {floor - reachable} unreachable floor tiles"
        )
    if floor < width * height * 0.35:
        raise ValueError(f"forest seed {used} is only {floor / (width * height):.0%} floor")
    # The extraction point goes in LAST and it is the only thing here allowed
    # to open ground back up. It clears its own plot, so it has to run after
    # the connectivity check above has already proved the forest is sound —
    # `_plot_open` then keeps it on ground that was mostly clearing anyway, and
    # the floor it adds is contiguous with the tile it is centred on.
    placed = rift.place(
        tiles,
        population.route,
        [(scene.x, scene.y) for scene in population.scenes],
        (width / 2.0, height / 2.0),
        random.Random(used ^ 0x21F7),
    )
    if placed is not None and count_reachable(tiles) != sum(row.count(FLOOR) for row in tiles):
        raise ValueError(f"forest seed {used} lost reachability placing the extraction point")

    drops = loot.scatter(tiles, population.scenes, random.Random(used ^ 0x1007))
    crate_rows = crates.attach(population)
    return TileMap(
        tiles,
        seed=used,
        scenery=scenery.to_payload(population),
        loot=[drop.to_payload() for drop in drops],
        crates=crate_rows,
        rift=placed.geometry_payload() if placed is not None else None,
    )
