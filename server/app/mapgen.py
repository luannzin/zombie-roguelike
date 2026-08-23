"""Procedural forest generation.

Produces the same `list[list[int]]` that `maps.py` hand-draws, so everything
downstream — collision, pathing, the wire format, the client — is unchanged.
The only new thing is the tile alphabet: FLOOR / ROCK / TREE (see world.py).

Shape of the result, and why:

  * It is a FOREST, not a dungeon. There are no corridors and no doors. Cover
    comes from thickets and boulder fields with open ground between them, which
    is what makes a lantern interesting: you lose sight of a zombie behind a
    treeline, not behind a doorframe.
  * The CENTRE is a glade so the map breathes. Players no longer spawn there:
    they emerge from a VOID corridor on a random edge (see `entrance.py`) and
    that path seals behind them.
  * It is CONNECTED, and `_connect` cannot fail to make it so. Noise happily
    produces sealed pockets; step 6 finds them, TUNNELS a route out of each
    one (a search, so it can go around the arrival corridor rather than being
    refused by it), and fills whatever is left over — removing floor can never
    strand anything new, so the invariant holds by construction.
    `build_forest` asserts the result, the same guarantee `build_arena` gives.

Determinism: one seed in, one map out. The seed also ships to the client, which
uses it to place decoration.
"""

from __future__ import annotations

import math
import random
from collections import deque

from . import ammo, crates, entrance, loot, rift, scenery
from .config import ENTRANCE_MOUTH_TILES, TILE_SIZE
from .maps import count_reachable
from .world import FLOOR, ROCK, TREE, VOID, TileMap

# --- authoring knobs ---------------------------------------------------------
# Map size in tiles. Big enough that the lantern radius (11 tiles) never lights
# the whole thing, so fog of war has something to hide.
#
# ROUGHLY DOUBLE WHAT IT WAS, and the scene count went up with it (see
# `scenery.FOREST_SCENES`). The two numbers are one decision: a forest that
# grows without growing its stories is not a bigger world, it is a longer walk
# between the same things. What the extra ground actually buys is that a night
# with three extraction pads can put them far enough apart to be three
# separate expeditions rather than three stops on one lap.
#
# THAT IS THE THREE-PAD SIZE, not the size. A night carrying fewer pads is
# built smaller in the same proportion — see `size_for_pads`.
DEFAULT_WIDTH = 132
DEFAULT_HEIGHT = 92

#: Pads a full-size forest is sized for. 132x92 was chosen so THREE extraction
#: points can sit far enough apart to be three expeditions; a one-pad night on
#: that same map is one errand with a long walk either side of it, which is the
#: map refusing to be about anything. So the forest is sized to the night it
#: has to hold: GROUND PER PAD IS CONSTANT, and how many pads there are is the
#: day's (`rift.count_for_day`). Scale is on the AREA, so both sides shrink
#: together and the aspect never changes — a forest is not a corridor at any
#: size.
#:
#:     1 pad    76 x 53    a third of the ground, one place to reach
#:     2 pads  108 x 75
#:     3 pads  132 x 92    the full map, unchanged
FULL_SIZE_PADS = 3


def size_for_pads(count: int) -> tuple[int, int]:
    """Forest dimensions for a night carrying `count` extraction points."""
    scale = math.sqrt(min(max(count, 1), FULL_SIZE_PADS) / FULL_SIZE_PADS)
    return round(DEFAULT_WIDTH * scale), round(DEFAULT_HEIGHT * scale)

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
# Scaled with the map — the same count over twice the area leaves half the
# forest as one unbroken thicket, which is not cover, it is a maze.
GLADE_COUNT = (13, 20)
GLADE_RADIUS = (3.0, 6.5)

CENTRE_CLEARING_TILES = 6.0
BORDER_TILES = 2

# A sealed pocket smaller than this is filled solid; anything larger earns a
# corridor. Drilling out every 3-tile hole would leave the map full of stubs.
MIN_POCKET_TILES = 12
# Drilling passes before `_connect` gives up and fills whatever is left. One
# pass can open a pocket and split another, so this is iterative rather than
# single-shot; twelve is comfortably more than a 132x92 map has ever needed.
PASSES = 12

#: Scene kinds that come with creatures already standing on them.
#:
#: THE ONLY PLACE THE MAP PROMISES A FIGHT. Everything else the director
#: spawns is a wandering group that happened to be near somebody; a nest is
#: pre-placed, does not despawn on arrival, and is exactly where the best loot
#: in the game is. That pairing is the whole point of the shrine — the player
#: can see the totems from a distance, can see the pack around them, and gets
#: to decide. A landmark that was worth more AND safer would not be a
#: decision, it would be an errand.
NEST_SCENES = frozenset({"sanctuary"})

#: SOME OF THEM STAYED, and this is the smallest possible version of that idea.
#:
#: Every scene on this map is a story about people who did not make it, and
#: until now none of them had anybody in it: the wreck said "something happened
#: here" and the forest answered "and nothing is here now". So the scenes that
#: are specifically about somebody DYING keep one or two of them, standing in
#: the thing that killed them, idle until they notice you.
#:
#: IT IS NOT A DIFFICULTY CHANGE, it is an answer to "why is this dangerous".
#: One or two bodies is a thing a party walks up to and deals with in a few
#: seconds — the sanctuary's five to eight is the fight, and it stays the only
#: one. What this buys is that the loot in a wreck is guarded by the reason the
#: wreck exists, so opening an ambulance is a decision rather than a chore.
#:
#: The quiet scenes are deliberately NOT on this list. A deadfall is a tree
#: that came down and a dumpsite is where somebody left rubbish; putting a
#: creature in either would say that the map is a list of encounters, and the
#: stretches with nothing in them are what make the ones with something in them
#: land.
HAUNT_SCENES: dict[str, tuple[int, int]] = {
    "medevac": (1, 2),
    "last_stand": (2, 3),
    "checkpoint": (1, 2),
    "flight": (1, 2),
    "busstop": (1, 1),
}

#: Scenes that come with something SPECIFIC standing in them, by type key.
#:
#: THE THIRD KIND OF NEST, and the difference from the other two is that this
#: one is about WHAT rather than how many. A haunt keeps whatever the director
#: is already spawning, because the story it tells is "the people who died
#: here are still here" and the people who died here were people. A den is not
#: about people at all: it is a place an ANIMAL lives, and the animal is the
#: reason the place exists.
#:
#: One creature, once, and `enemies.WOLF_ALPHA.persists` is what keeps it
#: there — a miniboss recycled by the abandonment timer before anybody walked
#: to its den would leave a den with a story and nothing in it.
DEN_SCENES: dict[str, tuple[str, int]] = {"den": ("wolf-alpha", 1)}


def _nests(population, rng: random.Random) -> list[tuple[float, float, int, str]]:
    """Where creatures are STANDING when the map is built, how many, and what.

    Three kinds and one list. The sanctuary gets a pack, because the whole
    bargain it offers is guarded loot; the scenes in `HAUNT_SCENES` get one or
    two, because the story they tell has bodies in it; a `DEN_SCENES` scene
    gets the one specific creature that LIVES there. Everything else on the
    map gets nobody, and that emptiness is load-bearing — see `HAUNT_SCENES`.

    Zero is returned for the sanctuary's count rather than a number, because
    the pack size for a shrine is `room.NEST_PACK` and belongs to the room: how
    big a landmark's guard is is a tuning decision about the fight, not about
    where the fight is.

    The fourth column is a type KEY or "" for "whatever the director spawns".
    A den is the only thing that names one, and it names one because the whole
    scene is about that animal.
    """
    out: list[tuple[float, float, int, str]] = []
    for scene in population.scenes:
        kind = ""
        if scene.kind in DEN_SCENES:
            kind, count = DEN_SCENES[scene.kind]
        elif scene.kind in NEST_SCENES:
            count = 0
        elif scene.kind in HAUNT_SCENES:
            count = rng.randint(*HAUNT_SCENES[scene.kind])
        else:
            continue
        out.append((scene.x * TILE_SIZE, scene.y * TILE_SIZE, count, kind))
    return out


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


def _carve_circle(
    tiles: list[list[int]],
    cx: float,
    cy: float,
    radius: float,
    protect: int | None = None,
) -> None:
    height = len(tiles)
    width = len(tiles[0])
    r2 = radius * radius
    for ty in range(max(0, int(cy - radius)), min(height, int(cy + radius) + 1)):
        for tx in range(max(0, int(cx - radius)), min(width, int(cx + radius) + 1)):
            if (tx - cx) ** 2 + (ty - cy) ** 2 <= r2:
                if protect is not None and tiles[ty][tx] == protect:
                    continue
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


def _tunnel(
    tiles: list[list[int]],
    region: list[tuple[int, int]],
    main: set[tuple[int, int]],
    protect: int | None = None,
) -> bool:
    """Carve the SHORTEST route from `region` to `main`. False if there is none.

    A breadth-first search out of the whole pocket at once, over every tile
    the carve is allowed to touch, stopping on the first tile of the main
    region it meets — then the path is carved back along `prev`.

    THIS REPLACED AN L-SHAPED DRILL, and the difference is not tidiness. An L
    goes across and then down whether or not that route is legal, and
    `protect` makes one route illegal: the arrival corridor. A pocket sitting
    on the far side of that corridor from the main region got the same refused
    L every pass, forever — the map generated fine on a 96x64 forest because
    there was less room for it to happen in, and reliably wedged on a few
    seeds once the map doubled. A search cannot be refused by a wall it can
    walk around.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    frontier: deque[tuple[int, int]] = deque(region)
    seen: set[tuple[int, int]] = set(region)
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    goal: tuple[int, int] | None = None

    while frontier:
        x, y = frontier.popleft()
        if (x, y) in main:
            goal = (x, y)
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in seen:
                continue
            # The corridor is not ours to dig through. Everything else — rock,
            # trunk, open floor — is fair game for a route.
            if protect is not None and tiles[ny][nx] == protect:
                continue
            seen.add((nx, ny))
            prev[(nx, ny)] = (x, y)
            frontier.append((nx, ny))

    if goal is None:
        return False
    cell: tuple[int, int] | None = goal
    while cell is not None:
        _carve_circle(tiles, cell[0], cell[1], 1.1, protect)
        cell = prev.get(cell)
    return True


def _connect(
    tiles: list[list[int]],
    centre: tuple[int, int],
    protect: int | None = None,
) -> None:
    """Make every floor tile reachable from the centre clearing.

    Small pockets are filled solid (they are noise artefacts, not places).
    Larger ones get a trail drilled to the nearest tile of the main region, so
    the map keeps its interesting shapes instead of losing them to the fill.

    IT ALWAYS SUCCEEDS, and the last pass is why. Drilling can FAIL: `protect`
    stops `_carve_circle` writing over the arrival corridor, so a pocket whose
    only line to the main region runs along that corridor keeps its trail
    refused however many passes it gets. On the old map that was rare enough
    to never be seen; at 132x92 there is simply more forest for it to happen
    in, and `build_forest` asserts the result, so "rare" is a crash a player
    eventually meets. Anything still isolated after the drilling passes is
    FILLED — removing floor can never disconnect anything, so the invariant
    holds by construction rather than by luck, and what is lost is a piece of
    forest nobody could have walked to in the first place.
    """
    for _ in range(PASSES):
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
            _tunnel(tiles, region, main_set, protect)

    # Whatever the drilling could not reach. See the note above: filling only
    # ever removes floor, so this cannot strand anything new.
    regions = _regions(tiles)
    if len(regions) <= 1:
        return
    main = next((r for r in regions if centre in r), regions[0])
    for region in regions:
        if region is main:
            continue
        for x, y in region:
            tiles[y][x] = ROCK


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

    # 4. a centre glade — the map still wants a heart, even though the party
    #    arrives from an edge rather than standing in it
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
    origin: tuple[float, float],
    pads: int = FULL_SIZE_PADS,
) -> scenery.Population:
    """Lay the story over a finished forest. Mutates `tiles`.

    Runs AFTER connectivity, never before: a scene needs a box of open ground
    to stand in, and `_connect` is the step that decides which ground is open.
    Its own building footprints are re-checked against connectivity inside
    `scenery.populate`, which reverts rather than drilling.

    The arrival mouth is excluded with a generous radius. It is the first
    thing every player sees and the one place the party has to be able to read
    each other; a cabin in it would be the best-lit prop in the game and the
    worst-placed one. The centre glade is kept clear too, so the map still
    has a heart that is not somebody's leftover camp.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    # Scenes scale with the ground, because they are one decision: a map that
    # shrinks without shedding stories is a junkyard, one that grows without
    # gaining them is a walk. `size_for_pads` scales AREA, so the same fraction
    # applies here.
    share = min(max(pads, 1), FULL_SIZE_PADS) / FULL_SIZE_PADS
    low, high = scenery.FOREST_SCENES
    return scenery.populate(
        tiles,
        random.Random(seed ^ 0x5CE7E),
        count=(max(3, round(low * share)), max(4, round(high * share))),
        landmark=scenery.LANDMARKS,
        # One thread linking the scenes into a single route outward from the
        # mouth the party walked out of. The camp does not get one: it is four
        # scenes of firewood around a fire, and a blood trail through it would
        # be the wrong promise.
        thread=True,
        anchor=(int(origin[0]), int(origin[1])),
        avoid=(
            (origin[0], origin[1], ENTRANCE_MOUTH_TILES + 6.0),
            (width / 2, height / 2, CENTRE_CLEARING_TILES + 4.0),
        ),
    )


def build_forest(
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    day: int = 1,
    calibres: set[str] | None = None,
) -> TileMap:
    """Generate, populate and validate. Raises rather than shipping a broken map.

    `calibres` is what the PARTY is carrying, and it is the only thing the
    forest asks about the players before it is built. Ammunition is stocked
    against the belt (`ammo.scatter`): a room with nothing but knives finds no
    boxes at all, and a room with one pistol does not spend the night walking
    past rifle rounds nobody can fire.
    """
    pads = rift.count_for_day(day)
    sized = size_for_pads(pads)
    width = sized[0] if width is None else width
    height = sized[1] if height is None else height
    tiles, used = generate_forest(width, height, seed)
    gate = entrance.carve(tiles, used)
    mouth_tx = int(gate.mouth_x // TILE_SIZE)
    mouth_ty = int(gate.mouth_y // TILE_SIZE)
    # The mouth has to be floor — it is the tile connectivity and the party
    # walk onto. VOID behind it is the corridor and must not be drilled out.
    if 0 <= mouth_ty < height and 0 <= mouth_tx < width:
        tiles[mouth_ty][mouth_tx] = FLOOR
    _connect(tiles, (mouth_tx, mouth_ty), protect=VOID)

    origin = (gate.mouth_x / TILE_SIZE, gate.mouth_y / TILE_SIZE)
    population = populate_forest(tiles, used, origin, pads)
    floor = sum(row.count(FLOOR) for row in tiles)
    reachable = count_reachable(tiles)
    if reachable != floor:
        raise ValueError(
            f"forest seed {used} has {floor - reachable} unreachable floor tiles"
        )
    if floor < width * height * 0.35:
        raise ValueError(f"forest seed {used} is only {floor / (width * height):.0%} floor")
    # Extraction points go in LAST and they are the only thing here allowed
    # to open ground back up. They clear their own plots, so they have to run
    # after the connectivity check above has already proved the forest is
    # sound — `_plot_open` then keeps them on ground that was mostly clearing
    # anyway, and the floor they add is contiguous with the tile they sit on.
    # How many is the DAY's: the first nights are one pad, later nights more.
    placed = rift.place_many(
        tiles,
        population.route,
        [(scene.x, scene.y) for scene in population.scenes],
        origin,
        random.Random(used ^ 0x21F7),
        pads,
    )
    if placed and count_reachable(tiles) != sum(row.count(FLOOR) for row in tiles):
        raise ValueError(f"forest seed {used} lost reachability placing the extraction point")

    drops = loot.scatter(tiles, population.scenes, random.Random(used ^ 0x1007))
    # Ammunition is a SECOND pass over the same scenes, with its own ids and
    # its own rng stream, so a party that bought a rifle last night does not
    # get a different arrangement of gold rings tonight than one that did not.
    occupied = [(drop.x / TILE_SIZE - 0.5, drop.y / TILE_SIZE - 0.5) for drop in drops]
    drops += ammo.scatter(
        tiles,
        population.scenes,
        random.Random(used ^ 0x0AA0),
        calibres or set(),
        day,
        next_id=1,
        occupied=occupied,
    )
    crate_rows = crates.attach(population)
    return TileMap(
        tiles,
        seed=used,
        scenery=scenery.to_payload(population),
        loot=[drop.to_payload() for drop in drops],
        crates=crate_rows,
        rifts=[row.geometry_payload() for row in placed],
        entrance=gate.geometry_payload(),
        nests=_nests(population, random.Random(used ^ 0x4E5D)),
    )
