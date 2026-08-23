"""Scenes: the things people left behind, placed in GROUPS that mean something.

`mapgen.py` grows a forest. This grows what happened in it.

THE RULE THIS MODULE EXISTS TO ENFORCE
A prop scattered by a hash is texture. A car, a suitcase open beside it, a
pack forty paces on and blood after that is a sentence, and the player reads it
whether or not they notice they are reading. So nothing here places a single
object: the unit of placement is a SCENE — a small handful of props with fixed
relationships — and the procedural part is which scenes, in what order, facing
which way, with which details rolled in.

That is also why this is server-side. Everything else the client draws comes
off the map seed, because one rock is as good as another and both sides can
agree on a hash. A scene cannot work that way: it has to know which side of the
lorry the load spilled onto and that the blood runs AWAY from the doors, it may
make tiles solid, and reproducing that on the client would mean mirroring this
whole file the way `simulation.py` is mirrored. The map already ships as tiles;
scenes ship beside them as a flat list of drawables and cost a few hundred
bytes.

THE SCENES

    sanctuary   A LANDMARK, one per map. Carved stone in a ring, bones on
                the floor, an altar in the middle that always pays — and a
                nest of creatures standing on it. The only place anybody
                BUILT, and the only bargain the map states in advance.
    den         A LANDMARK, one per map, and the only scene about an ANIMAL
                rather than about people: trunks dragged into a lee, a floor
                of bones, a drag mark going out. The MINIBOSS is asleep in
                the middle of it (`mapgen.DEN_SCENES`), which makes it the
                only place in the game whose danger you can see before it can
                see you — and therefore the only one you get to decline.
    roadside    one vehicle, an oil slick, and whichever way somebody walked.
    convoy      three or four vehicles nose to tail, still queued. People were
                being moved out and did not get out.
    medevac     an ambulance with its doors open and blood fanning away from
                them. Somebody was still trying.
    checkpoint  a cruiser across the road, a barricade with a hole punched
                through it, barrels stacked as a block.
    haulage     a lorry that shed its load in a cone behind the tailgate. The
                densest object scene there is.
    busstop     a bus with the bay open and cases on BOTH sides of it, so
                reading the scene means walking around something solid.
    flight      the micro-history: car, case, pack, blood, nothing. Four props
                in an order, and the order is the whole scene.
    last_stand  no shelter and no comfort: a barricade of logs, spent brass,
                blood in a ring. It ended here.
    dumpsite    barrels, bins and boxes. No story, and that is its job — it is
                where a player learns the two verbs before a scene with a
                stake in it asks them to use one.
    boundary    a fence run with a gap smashed through it, and prints in the
                gap. Something did not use the gate.
    trailhead   footprints crossing open ground, one dropped thing at the
                start, blood halfway, nothing at the end.
    deadfall    felled trunks, nothing human at all. The quiet scene, and it
                is load-bearing — a forest where every clearing has a story is
                a theme park, and the loud ones only land if most of the woods
                is just woods.

NOTHING IN A FOREST IS LIT ANY MORE. `SceneLight` still exists and the STORE
still uses it (the merchant's torches are navigation in a zone with no
lantern), but no forest scene emits one. A lamp on a dark map does the
player's reading for them from across the level, through the treeline, before
they have spent anything to find out — and the darkness is the only real
inventory of tension the game has. The party's own lamp and the extraction
platform they woke are the whole light budget of a night.

Determinism: one rng in, one set of scenes out. The caller seeds it from the
map seed, so a map and its story are the same pair every time.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import TILE_SIZE
from .world import FLOOR, LOW, PROP, ROCK, TREE

#: Tiles of treeline kept clear of scenes at every edge. Matches the border
#: both generators draw (`mapgen.BORDER_TILES`, `camp.BORDER_TILES`).
BORDER = 2

# --- what a scene is made of -------------------------------------------------

#: Flat on the floor. The client bakes these into its ground canvas: no
#: silhouette, no depth sort, no per-frame cost.
DECAL = 0
#: Stands up. Depth-sorted with the party, so a body passes in front of and
#: behind it.
STANDING = 1


@dataclass(frozen=True)
class Piece:
    """One drawable, in TILE offsets from its scene's top-left corner.

    `variant` indexes the sheet's frames and the client takes it modulo the
    frame count, so a scene may ask for "some variant" with a large number and
    never go out of range. The one exception is `tracks`, whose variant is a
    COMPASS POINT — the sheet has one frame per direction, and the modulo has
    to land on the frame that actually points that way.
    """

    kind: str
    layer: int
    dx: float
    dy: float
    variant: int
    flip: bool = False


#: Light kinds. The client maps these to tones; the NUMBERS are the contract
#: and must not be renumbered — `client/src/game/world.ts` pushes a beacon on
#: as kind 2 by literal.
#:
#: LAMP is the merchant's torches, and after the forest lights were cut it is
#: the only one any generator still emits. EMBER is kept because the client
#: already has a tone for it and because the next warm thing somebody adds —
#: a burning wreck, a flare somebody dropped — wants exactly this slot rather
#: than a new one; it is not currently placed anywhere.
LAMP = 0
EMBER = 1
#: The EXTRACTION point, and it is a light like any other — which is the whole
#: reason this is a list on the map payload and not a field on the cabin. When
#: `rift.py` opens, the client pushes one `SceneLight(BEACON, ...)` onto this
#: same list and the lighting burns it, feeds the fov with it and draws its
#: glow with no idea that it is special. That was not a rendering change.
BEACON = 2
#: The upgrade machine's marquee in the shop — the only ELECTRIC light in the
#: game, and the reason it gets its own kind rather than borrowing EMBER. It
#: has to read as neither fire nor extraction: everything warm out here is
#: something burning, and the one cold light already means "a platform".
NEON = 3


@dataclass(frozen=True)
class SceneLight:
    """Something in a scene that is still burning, in TILE offsets.

    Scenes are invisible until a lantern reaches them, which means a map full
    of stories nobody walks past. A light turns a scene into a DESTINATION: you
    see a dot of warmth across the dark and you choose to go to it, and the
    choice is the whole point — it is the cheapest navigation the game has, and
    it makes a landmark out of a pile of props.

    Small radii. These are not areas of safety; they are things you can see
    from far away and read from close up.
    """

    dx: float
    dy: float
    radius_tiles: float
    kind: int = LAMP


@dataclass(frozen=True)
class Prop:
    """A placed piece, in world pixels. This is the wire row."""

    kind: str
    x: float
    y: float
    variant: int
    flip: bool
    layer: int

    def to_row(self, kinds: list[str]) -> list:
        """Compact array form. Keys would triple the payload for no gain."""
        return [
            kinds.index(self.kind),
            round(self.x),
            round(self.y),
            self.variant,
            1 if self.flip else 0,
            self.layer,
        ]


@dataclass(frozen=True)
class PlacedLight:
    """A scene light anchored on the map, in world pixels."""

    x: float
    y: float
    radius_tiles: float
    kind: int

    def to_row(self) -> list:
        return [round(self.x), round(self.y), round(self.radius_tiles, 2), self.kind]


@dataclass(frozen=True)
class PlacedScene:
    """A scene that landed, in TILES. Kind is what the place *is*."""

    kind: str
    x: float
    y: float


@dataclass(frozen=True)
class Population:
    """Everything one call to `populate` put on a map.

    `props` and `lights` go on the wire. `scenes` and `route` do not, yet —
    they are where the scenes ended up, in TILES, and the order the thread
    walks them. They are returned rather than thrown away because the
    EXTRACTION point is going to want exactly this: a set of places worth
    standing in, and a direction that leads away from spawn. Placing extraction
    at or past `route[-1]` gives a run a shape — out along the story, back
    through it carrying something — where a uniformly random tile gives an
    errand. Loot also reads `scenes`: a drop is a second pass over the
    places that landed, not a third scatter.
    """

    props: list[Prop]
    lights: list[PlacedLight]
    scenes: list[PlacedScene]
    route: list[tuple[float, float]]


@dataclass(frozen=True)
class Layout:
    """A scene resolved into local tile space, before it is anchored."""

    width: int
    height: int
    pieces: tuple[Piece, ...]
    #: Anything in this scene that is still lit. Usually empty.
    lights: tuple[SceneLight, ...] = ()


#: What each standing kind does to the tiles under it: (width, depth, kind) in
#: tiles. Anything absent is walked through — cold ash, a dropped pack, a stain.
#:
#: DERIVED FROM THE PIECES, never listed by hand. A scene that wrote its own
#: solid tiles would drift from its own art the first time somebody nudged a
#: crate half a tile, and the failure mode is invisible walls — the worst bug a
#: 2D game can have, because nothing on screen explains it.
#:
#: The kind matters as much as the size, and there are exactly two answers.
#: A VEHICLE is a wall of steel taller than a person: it is PROP, so it stops
#: sight as well as bodies, and that is what makes a convoy somewhere to fight
#: rather than a row of decorations — you lose a creature behind a bus. A
#: STATUE is the same, and for the same reason: a ring of them is a ring of
#: blind corners, which is most of what makes the shrine expensive.
#: Everything else here is waist-high, so it is LOW — solid to bodies and
#: bullets, transparent to sight. You take cover behind a barrel, you do not
#: disappear behind it.
#:
#: Widths match the sheets in `make_scenery.py` / `make_objects.py` (a vehicle
#: is 4, an altar 2, tent 2, logs 2, the rest 1). Height is always one tile,
#: on the contact point — the feet, the sill, the post. A statue is 2.25 tiles
#: tall and a bus is 2.5; those pixels are drawn, not walked into. Claiming
#: only the contact row is how a board becomes a wall without a roofline
#: becoming something you bounce off two tiles above your own head.
FOOTPRINTS: dict[str, tuple[int, int, int]] = {
    "tent": (2, 1, PROP),
    "logs": (2, 1, LOW),
    "fence": (1, 1, LOW),
    "sign": (1, 1, LOW),
    "statue": (1, 1, PROP),
    # Interactive objects. Their tiles are claimed here and then the pieces
    # are pulled onto the live list by `crates.attach`, so a smash or an open
    # can free the ground again — see `Room.smash_crate`.
    "barrel": (1, 1, LOW),
    "drum": (1, 1, LOW),
    "fuel_drum": (1, 1, LOW),
    # Eight crates, one tile each — the stacked one included. It is drawn two
    # boxes tall and it still stands on one footprint, which is the same rule
    # the statue and the bus follow: you claim the ground the thing touches,
    # not the air above it.
    "crate": (1, 1, LOW),
    "crate_broken": (1, 1, LOW),
    "crate_braced": (1, 1, LOW),
    "crate_stacked": (1, 1, LOW),
    "crate_battered": (1, 1, LOW),
    "crate_rotted": (1, 1, LOW),
    "crate_ironbound": (1, 1, LOW),
    "crate_collapsed": (1, 1, LOW),
    "box": (1, 1, LOW),
    "ammo_case": (1, 1, LOW),
    "tote": (1, 1, LOW),
    "chest": (1, 1, LOW),
    "strongbox": (1, 1, LOW),
    "mailbox": (1, 1, LOW),
    "suitcase": (1, 1, LOW),
    "freezer": (1, 1, LOW),
    "bin": (1, 1, LOW),
    "toolbox": (1, 1, LOW),
    "car": (4, 1, PROP),
    "van": (4, 1, PROP),
    "ambulance": (4, 1, PROP),
    "cruiser": (4, 1, PROP),
    "lorry": (4, 1, PROP),
    "bus": (4, 1, PROP),
    "altar": (2, 1, LOW),
    "cairn": (2, 1, LOW),
}


def _cells(layout: Layout, x0: int, y0: int) -> list[tuple[int, int, int]]:
    """Every tile this scene's standing pieces claim, as (tx, ty, kind).

    A standing piece is anchored on its CONTACT POINT — bottom centre — and
    the solid slab sits on that point, one tile tall. Growing the box upward
    from `dy - depth` put the sign's board and the cabin's eaves in the way,
    which is the top of the sprite. The client draws from the same contact
    number, so the tiles you bump into are the tiles the feet stand on.
    """
    cells: list[tuple[int, int, int]] = []
    for piece in layout.pieces:
        spec = FOOTPRINTS.get(piece.kind)
        if spec is None or piece.layer != STANDING:
            continue
        width, _, kind = spec
        bx = int(math.floor(x0 + piece.dx - width / 2 + 0.5))
        # Tile containing the point just above the contact — the feet, not
        # the canopy. An integer `dy` is the bottom edge of that tile.
        by = int(math.floor(y0 + piece.dy - 1e-6))
        for ox in range(width):
            cells.append((bx + ox, by, kind))
    return cells


#: Compass points in the tracks sheet. Mirrors TRACK_DIRECTIONS in
#: server/tools/make_scenery.py: frame N points at N/8 of a full turn,
#: clockwise from straight up the screen being frame 0... in the sheet's own
#: frame, angle 0 is +y (down the screen), so a heading of (dx, dy) is
#: `atan2(dx, dy)`. Getting this backwards puts every trail in reverse.
TRACK_DIRECTIONS = 8


def track_frame(dx: float, dy: float) -> int:
    """Which tracks frame walks along (dx, dy)."""
    angle = math.atan2(dx, dy)
    return int(round(angle / math.tau * TRACK_DIRECTIONS)) % TRACK_DIRECTIONS


def _trail(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    rng: random.Random,
    step: float = 0.9,
    wander: float = 0.35,
) -> list[Piece]:
    """A line of boot prints from one point to another, in tiles.

    Wanders, because a straight line of prints is a diagram. Every pair points
    along the LOCAL heading rather than the overall one, so the trail turns
    with its own curve — prints that all face the start-to-end vector while the
    line bends are the tell that nobody walked this.
    """
    span = math.hypot(x1 - x0, y1 - y0)
    if span < 0.5:
        return []
    count = max(2, int(span / step))
    pieces: list[Piece] = []
    prev = (x0, y0)
    for index in range(count + 1):
        t = index / count
        # A single sine bow plus per-print jitter: enough to look walked,
        # not enough to look drunk.
        offset = math.sin(t * math.pi) * wander * span * 0.2
        nx = -(y1 - y0) / span
        ny = (x1 - x0) / span
        px = x0 + (x1 - x0) * t + nx * offset + (rng.random() - 0.5) * 0.3
        py = y0 + (y1 - y0) * t + ny * offset + (rng.random() - 0.5) * 0.3
        heading = (px - prev[0], py - prev[1])
        if index > 0 and (abs(heading[0]) > 1e-3 or abs(heading[1]) > 1e-3):
            pieces.append(
                Piece("tracks", DECAL, prev[0], prev[1], track_frame(*heading))
            )
        prev = (px, py)
    return pieces


# --- the scenes --------------------------------------------------------------
# Each builds a Layout in its own local tile space. They are functions rather
# than tables because the interesting part of every one of them is procedural:
# which way a car is facing, where a barricade got pushed through, how far a
# trail runs. A table of fixed offsets would give a dozen scenes; these give a
# dozen KINDS of scene.
#
# NOTHING HERE IS A BUILDING, AND NOTHING HERE IS LIT.
#
# There used to be a cabin and a tent out in these woods, with a lamp burning
# over the door. Both are gone, and for two different reasons that turned out
# to be the same reason.
#
#   The BUILDINGS taught the wrong lesson. A procedurally dropped house is
#   read once as "what is that" and forever after as "loot house", and after
#   two expeditions the forest is a list of houses with a fixed payout. What
#   replaced them is a vocabulary of things somebody DROVE, packed, buried or
#   carved — none of which resolves into one repeated noun, and all of which
#   the player has to walk up to before they know what they have found.
#
#   The LIGHTS did the reading for the player. A lamp on a dark map is not
#   decoration, it is a waypoint: it says "something is over there" from
#   across the whole level, and it says it through the treeline, through the
#   fog, and before the party has spent anything to find out. The darkness is
#   the game's only real inventory of tension and a scene light was quietly
#   spending it. The only lights left in a forest now come from the party
#   themselves and from the extraction platform they woke up — see
#   `SceneLight`, which the STORE still uses, and `BEACON`.
#
# A silhouette in the dark that could be a tree, a car or a body is worth more
# than any of the three would be lit.


def _vehicle(rng: random.Random, dx: float, dy: float, pool=None) -> Piece:
    """One abandoned vehicle, rolled off a weighted pool.

    Vehicles are the load-bearing prop of the whole forest now, so the roll is
    in one place: a `car` is what most of a road is, and an ambulance or a
    cruiser is a find. Each is FOUR TILES WIDE and solid, which makes them the
    only cover out here long enough to break a sightline while you stand still
    behind it — and the reason a convoy reads as a place to fight rather than
    as scenery to walk past.
    """
    table = pool or VEHICLE_POOL
    total = sum(weight for _, weight in table)
    roll = rng.uniform(0, total)
    kind = table[0][0]
    for name, weight in table:
        roll -= weight
        if roll <= 0:
            kind = name
            break
    return Piece(kind, STANDING, dx, dy, 0, rng.random() < 0.5)


#: (object key, weight). A road is mostly cars.
VEHICLE_POOL = (
    ("car", 46.0),
    ("van", 20.0),
    ("lorry", 12.0),
    ("bus", 9.0),
    ("cruiser", 8.0),
    ("ambulance", 5.0),
)

#: Small openables, for dressing any scene. Same shape, same reason.
STASH_POOL = (
    ("suitcase", 26.0),
    ("toolbox", 22.0),
    ("box", 20.0),
    ("bin", 14.0),
    ("mailbox", 10.0),
    ("freezer", 8.0),
)

BARREL_POOL = (("barrel", 46.0), ("drum", 34.0), ("fuel_drum", 20.0))

#: Crates, weighted by how much of the forest is wreckage. The three CLEAN
#: builds — plain, braced, ironbound — are together a third of the pool, and
#: that split is the point of drawing eight of them: a player who learns the
#: silhouettes is reading a table before they commit to the walk, and a pool
#: where the good builds were common would turn that reading into a formality.
#: The other five are what a year outdoors does, and they are the ones that
#: teach the shapes, because they are the ones you keep seeing.
CRATE_POOL = (
    ("crate", 22.0),
    ("crate_broken", 16.0),
    ("crate_battered", 15.0),
    ("crate_rotted", 13.0),
    ("crate_collapsed", 12.0),
    ("crate_stacked", 10.0),
    ("crate_braced", 7.0),
    ("crate_ironbound", 5.0),
)


def _from_pool(rng: random.Random, pool, dx: float, dy: float) -> Piece:
    total = sum(weight for _, weight in pool)
    roll = rng.uniform(0, total)
    kind = pool[0][0]
    for name, weight in pool:
        roll -= weight
        if roll <= 0:
            kind = name
            break
    return Piece(kind, STANDING, dx, dy, 0, rng.random() < 0.5)


#: Every openable kind — the three pools plus the one-off containers scenes
#: place by hand. Derived from the pools rather than listed, so a crate added
#: to `CRATE_POOL` is thinned like the other seven without a second edit.
CONTAINER_KINDS: frozenset[str] = frozenset(
    [kind for pool in (CRATE_POOL, BARREL_POOL, STASH_POOL) for kind, _ in pool]
    + ["chest", "strongbox", "tote", "ammo_case"]
)

#: The most openables one scene may keep. Scenes roll their containers
#: independently — the roadblock rolls barrels AND crates, the haulage spill
#: rolls up to seven — and the rolls sum, so the densest scenes were putting a
#: dozen boxes in a nine-tile clearing. A pile that size is not a find, it is
#: furniture: the player stops reading silhouettes and just walks the row
#: pressing E, and the eight crate builds the pool exists to teach stop meaning
#: anything. Five is still a haul and still leaves floor to walk on.
MAX_CONTAINERS = 5


def _thin_containers(layout: Layout, rng: random.Random) -> Layout:
    """Drop openables that stack on each other, and cap what is left.

    TWO FAULTS, ONE PASS. Scenes place their boxes at `rng.uniform` offsets
    with nothing checking what is already there, so two of them land on the
    same tile — and because a container's footprint is claimed as LOW by
    `_cells`, the second one is a sprite standing inside another sprite on a
    tile that can only be smashed once. Thinning here rather than in each
    builder is the whole point: fifteen scenes roll containers and every one
    of them had the same bug.

    Order is shuffled first so the cap is not always paid by whichever loop the
    builder happens to run last — that would quietly delete the roadblock's
    crates every time its barrels rolled high.
    """
    containers = [p for p in layout.pieces if p.kind in CONTAINER_KINDS and p.layer == STANDING]
    if len(containers) <= 1:
        return layout

    rng.shuffle(containers)
    taken: set[tuple[int, int]] = set()
    keep: set[int] = set()
    for piece in containers:
        if len(keep) >= MAX_CONTAINERS:
            break
        # Same anchoring as `_cells`, in local tile space: contact point,
        # bottom centre, one tile. Containers are all 1 wide, so one cell.
        cell = (
            int(math.floor(piece.dx + 0.5)),
            int(math.floor(piece.dy - 1e-6)),
        )
        if cell in taken:
            continue
        taken.add(cell)
        keep.add(id(piece))

    pieces = tuple(
        p
        for p in layout.pieces
        if p.kind not in CONTAINER_KINDS or p.layer != STANDING or id(p) in keep
    )
    return Layout(layout.width, layout.height, pieces, layout.lights)


def _roadside(rng: random.Random) -> Layout:
    """One vehicle where the road used to be, and whatever fell out of it.

    The commonest of the vehicle scenes and deliberately the least
    conclusive. Most of what a player walks up to should turn out to be one
    car with a boot full of nothing, or the scenes that DO pay stop being
    events.
    """
    width, height = 10, 7
    cy = height / 2
    pieces = [_vehicle(rng, width / 2, cy)]

    # An oil slick under the engine, always. It is the one decal in the game
    # darker than the floor, so it does not advertise the car — it confirms it
    # once you are close enough to be committed.
    pieces.append(Piece("oil", DECAL, width / 2 + rng.uniform(-1.4, 1.4), cy + 0.6,
                        rng.randrange(4)))
    for _ in range(rng.randint(0, 2)):
        pieces.append(_from_pool(rng, STASH_POOL, rng.uniform(1.2, width - 1.2),
                                 cy + rng.uniform(0.8, 2.2)))
    pieces.append(Piece("debris", DECAL, width / 2 + rng.uniform(-3, 3),
                        cy + rng.uniform(-1, 1.8), rng.randrange(6)))
    if rng.random() < 0.5:
        pieces.append(Piece("clothes", DECAL, rng.uniform(1, width - 1),
                            cy + rng.uniform(0.5, 2.0), rng.randrange(5)))
    # Somebody got out and walked. Which way is the only information here.
    angle = rng.uniform(0, math.tau)
    pieces += _trail(width / 2, cy + 1.4,
                     width / 2 + math.cos(angle) * 3.6, cy + 1.4 + math.sin(angle) * 2.6, rng)
    return Layout(width, height, tuple(pieces))


def _convoy(rng: random.Random) -> Layout:
    """Three or four vehicles nose to tail. Somebody was moving people out.

    The shape is the story: a line, all facing the same way, stopped. Cars
    scattered at angles would read as a car park; a queue reads as traffic
    that was going somewhere and did not get there.
    """
    width, height = 20, 8
    cy = height / 2
    count = rng.randint(3, 4)
    pieces: list[Piece] = []
    # One heading for the whole line, and each vehicle nudged off it — a
    # perfectly aligned queue is a diagram, a queue with two cars slewed is a
    # queue people were trying to get around.
    facing = rng.random() < 0.5
    for index in range(count):
        x = 2.6 + index * (width - 5.0) / max(count - 1, 1)
        y = cy + rng.uniform(-1.1, 1.1)
        vehicle = _vehicle(rng, x, y)
        pieces.append(Piece(vehicle.kind, STANDING, x, y, 0, facing))
        pieces.append(Piece("oil", DECAL, x + rng.uniform(-1, 1), y + 0.5, rng.randrange(4)))
    for _ in range(rng.randint(1, 3)):
        pieces.append(_from_pool(rng, STASH_POOL, rng.uniform(1.5, width - 1.5),
                                 cy + rng.uniform(1.6, 3.0)))
    for _ in range(rng.randint(2, 4)):
        pieces.append(Piece("debris", DECAL, rng.uniform(1, width - 1),
                            rng.uniform(1, height - 1), rng.randrange(6)))
    for _ in range(rng.randint(1, 3)):
        pieces.append(Piece("blood", DECAL, rng.uniform(2, width - 2),
                            cy + rng.uniform(-2, 2), rng.randrange(6)))
    return Layout(width, height, tuple(pieces))


def _medevac(rng: random.Random) -> Layout:
    """An ambulance with its doors already open, and what came out of it.

    The one scene that says somebody was still TRYING. Blood in a fan behind
    the rear doors, dressings dropped where they fell, and — usually — a
    second vehicle that brought them.
    """
    width, height = 12, 9
    cx, cy = width / 2, height / 2
    flip = rng.random() < 0.5
    pieces = [
        Piece("ambulance", STANDING, cx, cy, 0, flip),
        Piece("oil", DECAL, cx + rng.uniform(-1.5, 1.5), cy + 0.6, rng.randrange(4)),
    ]
    # The fan of blood behind the doors. It spreads AWAY from the vehicle,
    # which is the difference between somebody being treated here and
    # somebody being dragged out.
    back = (1 if flip else -1)
    for _ in range(rng.randint(4, 7)):
        pieces.append(Piece("blood", DECAL,
                            cx + back * rng.uniform(1.5, 4.0),
                            cy + rng.uniform(-1.6, 2.2), rng.randrange(6)))
    for _ in range(rng.randint(1, 2)):
        pieces.append(Piece("box", STANDING, cx + back * rng.uniform(1.8, 3.6),
                            cy + rng.uniform(0.6, 2.0), 0, rng.random() < 0.5))
    pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-2, 2), cy + rng.uniform(0.5, 2.4),
                        rng.randrange(5)))
    for _ in range(rng.randint(1, 3)):
        pieces.append(Piece("debris", DECAL, cx + rng.uniform(-4, 4),
                            cy + rng.uniform(-2, 2.6), rng.randrange(6)))
    if rng.random() < 0.55:
        pieces.append(_from_pool(rng, STASH_POOL, cx + rng.uniform(-3.5, 3.5),
                                 cy + rng.uniform(1.4, 2.6)))
    return Layout(width, height, tuple(pieces))


def _checkpoint(rng: random.Random) -> Layout:
    """A cruiser across the road and a barricade that did not hold.

    A LINE with a hole in it, same grammar as `boundary` — the reason the two
    coexist is that a fence is what a farmer builds and this is what a
    government does, and the player can tell which failed harder.
    """
    width, height = 14, 9
    row = height / 2
    pieces: list[Piece] = []

    gap = rng.randrange(4, width - 5)
    for tx in range(2, width - 2):
        if gap <= tx <= gap + 1:
            continue
        if rng.random() < 0.22:
            continue
        distance = abs(tx - gap)
        state = 0 if distance > 3 else max(0, min(5, 5 - distance))
        pieces.append(Piece("fence", STANDING, tx + 0.5, row, state))

    pieces.append(Piece("cruiser", STANDING, rng.uniform(3.0, width - 3.0), row - 2.4,
                        0, rng.random() < 0.5))
    # Barrels used as a road block. They are the only BREAKABLE thing in the
    # scene, so a party with a gun can open the gap without walking into it.
    for index in range(rng.randint(2, 4)):
        pieces.append(_from_pool(rng, BARREL_POOL,
                                 gap + 0.5 + rng.uniform(-2.5, 2.5),
                                 row + 1.2 + index * 0.35 + rng.uniform(-0.4, 0.4)))
    if rng.random() < 0.6:
        pieces.append(Piece("ammo_case", STANDING, rng.uniform(2.5, width - 2.5),
                            row + rng.uniform(1.4, 2.6), 0, rng.random() < 0.5))
    # What the roadblock was issued. Behind the line, so reading it means
    # committing to the gap first.
    for _ in range(rng.randint(1, 2)):
        pieces.append(_from_pool(rng, CRATE_POOL, rng.uniform(2.5, width - 2.5),
                                 row + rng.uniform(-2.4, -1.2)))
    pieces.append(Piece("sign", STANDING, gap + 0.5, row - 0.4, rng.randrange(3)))
    for _ in range(rng.randint(2, 5)):
        pieces.append(Piece("debris", DECAL, rng.uniform(2, width - 2),
                            row + rng.uniform(-2.5, 2.5), rng.choice((0, 1, 4))))
    for _ in range(rng.randint(2, 4)):
        pieces.append(Piece("blood", DECAL, gap + rng.uniform(-2.0, 3.0),
                            row + rng.uniform(-1.5, 1.5), rng.randrange(6)))
    # And whatever came through went one way, through the gap.
    direction = 1 if rng.random() < 0.5 else -1
    pieces += _trail(gap + 1.0, row - direction * 2.4,
                     gap + 1.0 + rng.uniform(-2.0, 2.0), row + direction * 2.6, rng)
    return Layout(width, height, tuple(pieces))


def _haulage(rng: random.Random) -> Layout:
    """A lorry that shed its load. The densest object scene in the forest.

    Everything a supply run was carrying, on the ground, in a spill pattern
    that widens away from the tailgate. It is the scene that most rewards
    stopping — and the one most likely to keep somebody standing still for
    twenty seconds, which is a long time out here.
    """
    width, height = 14, 9
    cy = height / 2
    flip = rng.random() < 0.5
    pieces = [
        Piece("lorry", STANDING, width * 0.34, cy, 0, flip),
        Piece("oil", DECAL, width * 0.34 + rng.uniform(-1.5, 1.5), cy + 0.6, rng.randrange(4)),
    ]
    # The spill: a cone opening away from the bed, denser at the tailgate.
    for _ in range(rng.randint(4, 7)):
        t = rng.random()
        x = width * 0.52 + t * width * 0.42
        y = cy + rng.uniform(-1.0 - t * 2.0, 1.4 + t * 2.0)
        # CRATES ARE THE LOAD, and this is the scene they belong to before any
        # other: a lorry sheds boxes, not bins. They lead the roll here, which
        # is also the only place in the forest a player reliably sees several
        # of the eight builds side by side — which is how the silhouettes get
        # learned in the first place.
        roll = rng.random()
        pool = CRATE_POOL if roll < 0.5 else BARREL_POOL if roll < 0.78 else STASH_POOL
        pieces.append(_from_pool(rng, pool, x, y))
    for _ in range(rng.randint(2, 4)):
        pieces.append(Piece("debris", DECAL, rng.uniform(2, width - 1),
                            cy + rng.uniform(-2.5, 2.5), rng.randrange(6)))
    if rng.random() < 0.5:
        pieces.append(Piece("clothes", DECAL, rng.uniform(2, width - 2),
                            cy + rng.uniform(-2, 2), rng.randrange(5)))
    return Layout(width, height, tuple(pieces))


def _busstop(rng: random.Random) -> Layout:
    """A bus with the luggage bay open and the cases already gone through.

    A natural mini-dungeon: the longest solid object in the game, with things
    on both sides of it, so reading the scene means walking around something
    you cannot see past.
    """
    width, height = 14, 9
    cy = height / 2
    flip = rng.random() < 0.5
    pieces = [
        Piece("bus", STANDING, width / 2, cy, 0, flip),
        Piece("oil", DECAL, width / 2 + rng.uniform(-2, 2), cy + 0.6, rng.randrange(4)),
    ]
    # Cases strung out along the flank, some on the far side. The far side is
    # the point: you have to commit to a lap of the bus to see all of it.
    for _ in range(rng.randint(3, 5)):
        side = 1 if rng.random() < 0.6 else -1
        pieces.append(Piece("suitcase", STANDING,
                            rng.uniform(1.5, width - 1.5),
                            cy + side * rng.uniform(1.4, 2.6), 0, rng.random() < 0.5))
    for _ in range(rng.randint(1, 2)):
        pieces.append(Piece("clothes", DECAL, rng.uniform(1.5, width - 1.5),
                            cy + rng.uniform(-2.6, 2.6), rng.randrange(5)))
    for _ in range(rng.randint(1, 3)):
        pieces.append(Piece("blood", DECAL, rng.uniform(2, width - 2),
                            cy + rng.uniform(-2.4, 2.4), rng.randrange(6)))
    pieces.append(Piece("debris", DECAL, rng.uniform(2, width - 2),
                        cy + rng.uniform(-2, 2), rng.randrange(6)))
    return Layout(width, height, tuple(pieces))


def _flight(rng: random.Random) -> Layout:
    """THE MICRO-HISTORY, and the only scene built to be read in ORDER.

    A car. Beside it, a case somebody stopped to open. Further on, a pack
    they gave up on. Further still, blood. Nothing at the end.

    Every other scene here is a tableau you take in at once. This one is a
    SENTENCE with a direction, and the direction is what carries it: the props
    get cheaper and the ground gets worse the further you follow the line,
    which is the shape of somebody losing. No NPC, no quest, no dialogue —
    four props in an order.
    """
    width, height = 16, 10
    # One heading, and everything is placed along it.
    angle = rng.uniform(0, math.tau)
    cx, cy = 3.0 + rng.uniform(0, 1.5), height / 2
    ux, uy = math.cos(angle), math.sin(angle) * 0.6

    def at(distance: float, jitter: float = 0.7) -> tuple[float, float]:
        return (
            min(width - 1.5, max(1.5, cx + ux * distance + rng.uniform(-jitter, jitter))),
            min(height - 1.2, max(1.2, cy + uy * distance + rng.uniform(-jitter, jitter))),
        )

    pieces = [
        Piece("car", STANDING, cx, cy, 0, ux < 0),
        Piece("oil", DECAL, cx + rng.uniform(-1, 1), cy + 0.6, rng.randrange(4)),
    ]
    sx, sy = at(3.4)
    pieces.append(Piece("suitcase", STANDING, sx, sy, 0, rng.random() < 0.5))
    px, py = at(6.2)
    pieces.append(Piece("clothes", DECAL, px, py, 2))
    for step in range(rng.randint(3, 5)):
        bx, by = at(7.6 + step * 0.9, 0.5)
        pieces.append(Piece("blood", DECAL, bx, by, rng.choice((0, 2, 3))))
    # And the trail runs the whole way, so the order is walkable rather than
    # something the player has to guess at.
    ex, ey = at(9.8, 0.3)
    pieces += _trail(cx, cy + 1.2, ex, ey, rng, step=1.0, wander=0.4)
    if rng.random() < 0.45:
        # Sometimes they made it far enough to drop one more thing. Sometimes.
        fx, fy = at(11.0)
        pieces.append(_from_pool(rng, STASH_POOL, fx, fy))
    return Layout(width, height, tuple(pieces))


def _last_stand(rng: random.Random) -> Layout:
    width, height = 9, 9
    cx, cy = width / 2, height / 2
    facing = rng.uniform(0, math.tau)

    pieces: list[Piece] = []
    # A barricade thrown together on one side, facing whatever came.
    for index in range(rng.randint(2, 3)):
        offset = (index - 1) * 1.3
        pieces.append(
            Piece(
                "logs",
                STANDING,
                cx + math.cos(facing) * 1.9 - math.sin(facing) * offset,
                cy + math.sin(facing) * 1.6 + math.cos(facing) * offset,
                rng.randrange(4),
                rng.random() < 0.5,
            )
        )
    # Whatever they were shooting FROM behind, still there.
    for _ in range(rng.randint(1, 2)):
        pieces.append(
            _from_pool(rng, BARREL_POOL,
                       cx - math.cos(facing) * rng.uniform(0.8, 2.2),
                       cy - math.sin(facing) * rng.uniform(0.6, 1.8))
        )
    if rng.random() < 0.55:
        pieces.append(Piece("ammo_case", STANDING, cx + rng.uniform(-1.6, 1.6),
                            cy + rng.uniform(-0.6, 1.6), 0, rng.random() < 0.5))
    # Blood in a ring rather than a blot: the fight moved, and a single stain
    # would say somebody bled, not that somebody fought.
    for _ in range(rng.randint(4, 7)):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(0.4, 2.6)
        pieces.append(
            Piece("blood", DECAL, cx + math.cos(angle) * radius, cy + math.sin(angle) * radius,
                  rng.randrange(6))
        )
    for _ in range(rng.randint(2, 4)):
        pieces.append(
            Piece("debris", DECAL, cx + rng.uniform(-2.5, 2.5), cy + rng.uniform(-2.5, 2.5),
                  rng.choice((0, 2, 3, 4)))
        )
    pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-1.5, 1.5),
                        cy + rng.uniform(-1.5, 1.5), rng.randrange(5)))
    # One of them was dragged away. The drag is the last thing that happened
    # here, so it starts at the middle and leaves the scene entirely.
    away = facing + math.pi + rng.uniform(-0.6, 0.6)
    for step in range(4):
        t = step / 3
        pieces.append(
            Piece("blood", DECAL, cx + math.cos(away) * (1.0 + t * 2.4),
                  cy + math.sin(away) * (1.0 + t * 2.0), 2)
        )
    return Layout(width, height, tuple(pieces))


def _deadfall(rng: random.Random) -> Layout:
    width, height = 7, 6
    pieces: list[Piece] = []
    for _ in range(rng.randint(2, 4)):
        pieces.append(
            Piece("logs", STANDING, rng.uniform(1.0, width - 1.0), rng.uniform(1.5, height - 0.5),
                  rng.randrange(4), rng.random() < 0.5)
        )
    for _ in range(rng.randint(1, 3)):
        pieces.append(
            Piece("debris", DECAL, rng.uniform(0.5, width - 0.5), rng.uniform(0.5, height - 0.5), 1)
        )
    return Layout(width, height, tuple(pieces))


def _boundary(rng: random.Random) -> Layout:
    width, height = 11, 5
    row = height / 2
    gap = rng.randrange(3, width - 4)
    pieces: list[Piece] = []
    for tx in range(1, width - 1):
        if gap <= tx <= gap + 1:
            continue
        distance = abs(tx - gap)
        state = 0 if distance > 3 else max(0, min(5, 5 - distance))
        pieces.append(Piece("fence", STANDING, tx + 0.5, row, state))
    # Rails knocked flat inside the gap — the fence did not rot open, it was
    # pushed through.
    pieces.append(Piece("debris", DECAL, gap + 1.0, row + 0.2, 1))
    if rng.random() < 0.6:
        pieces.append(Piece("sign", STANDING, 1.5 if rng.random() < 0.5 else width - 1.5,
                            row - 0.3, rng.randrange(3)))
    if rng.random() < 0.4:
        pieces.append(Piece("mailbox", STANDING, 1.5 if rng.random() < 0.5 else width - 1.5,
                            row + 0.8, 0, rng.random() < 0.5))
    # Through the gap and onward, one way only.
    direction = 1 if rng.random() < 0.5 else -1
    pieces += _trail(gap + 1.0, row - direction * 2.0, gap + 1.0 + rng.uniform(-1.5, 1.5),
                     row + direction * 2.2, rng)
    if rng.random() < 0.5:
        pieces.append(Piece("blood", DECAL, gap + rng.uniform(0.4, 1.6), row, 0))
    return Layout(width, height, tuple(pieces))


def _trailhead(rng: random.Random) -> Layout:
    width, height = 9, 9
    angle = rng.uniform(0, math.tau)
    cx, cy = width / 2, height / 2
    x0 = cx - math.cos(angle) * 3.4
    y0 = cy - math.sin(angle) * 3.4
    x1 = cx + math.cos(angle) * 3.4
    y1 = cy + math.sin(angle) * 3.4

    pieces = _trail(x0, y0, x1, y1, rng, step=0.85, wander=0.5)
    # Something dropped at the start, blood at the middle, nothing at the end.
    # The nothing is the point: the scene ends without resolving, which is the
    # one thing a pile of props can do that a cutscene cannot.
    pieces.append(Piece("clothes", DECAL, x0 + rng.uniform(-0.6, 0.6),
                        y0 + rng.uniform(-0.6, 0.6), rng.randrange(5)))
    pieces.append(Piece("blood", DECAL, cx + rng.uniform(-0.8, 0.8),
                        cy + rng.uniform(-0.8, 0.8), rng.choice((0, 3, 4))))
    if rng.random() < 0.35:
        pieces.append(_from_pool(rng, STASH_POOL, x0 + rng.uniform(-1.2, 1.2),
                                 y0 + rng.uniform(-1.2, 1.2)))
    return Layout(width, height, tuple(pieces))


def _dumpsite(rng: random.Random) -> Layout:
    """Everything somebody stopped bothering to sort. Barrels and bins.

    The quiet workhorse of the object vocabulary: no vehicle, no story, just a
    heap of things with lids, which is where a player learns the two verbs
    before a scene with a stake in it asks them to use one.
    """
    width, height = 8, 7
    cx, cy = width / 2, height / 2
    pieces = [Piece("debris", DECAL, cx + rng.uniform(-1, 1), cy + rng.uniform(-1, 1), 5)]
    for _ in range(rng.randint(3, 6)):
        pieces.append(_from_pool(rng, BARREL_POOL if rng.random() < 0.55 else CRATE_POOL,
                                 cx + rng.uniform(-2.6, 2.6),
                                 cy + rng.uniform(-1.8, 2.2)))
    for _ in range(rng.randint(1, 3)):
        pieces.append(_from_pool(rng, STASH_POOL, cx + rng.uniform(-2.8, 2.8),
                                 cy + rng.uniform(-1.8, 2.2)))
    for _ in range(rng.randint(1, 2)):
        pieces.append(
            Piece("debris", DECAL, cx + rng.uniform(-2.5, 2.5), cy + rng.uniform(-2, 2),
                  rng.randrange(6))
        )
    if rng.random() < 0.5:
        pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-2, 2), cy + rng.uniform(-2, 2),
                            rng.randrange(5)))
    return Layout(width, height, tuple(pieces))


def _sanctuary(rng: random.Random) -> Layout:
    """THE LANDMARK. Carved stone in a ring, bones on the floor, an altar.

    Everything else in this forest is something that BROKE — a car that
    stopped, a fence that failed, a load that spilled. This is the one place
    somebody BUILT, and every decision in it is aimed at that difference being
    readable from as far away as the dark allows:

      * it is the only scene made of vertical shapes. A totem is taller than
        it is wide and the whole rest of the map is low horizontal mass, so a
        row of narrow columns at the edge of a lantern's reach does not read
        as more forest;
      * the shapes are arranged in a CIRCLE, and a circle is the one
        arrangement nothing in nature and nothing in a crash produces;
      * the floor inside the ring is bones, which is the scene telling the
        player what standing here has cost other people.

    And it always pays. `loot.SCENE_COUNTS` gives it the only guaranteed
    scatter in the game, its altar is one of the two objects that never comes
    up empty, and `enemies` seeds a nest on top of it (see
    `mapgen.populate_forest`). The bargain is stated in props before the
    player commits: this is worth more, and it is guarded.
    """
    width, height = 13, 13
    cx, cy = width / 2, height / 2
    radius = rng.uniform(3.6, 4.4)
    count = rng.randint(5, 7)
    start = rng.uniform(0, math.tau)

    pieces: list[Piece] = []
    for index in range(count):
        angle = start + math.tau * index / count
        # A ring squashed on Y by the same ratio everything else in this game
        # is, so it reads as a circle on the ground rather than as a hoop
        # standing up in the air.
        px = cx + math.cos(angle) * radius
        py = cy + math.sin(angle) * radius * 0.62
        pieces.append(Piece("statue", STANDING, px, py, rng.randrange(6), rng.random() < 0.5))

    # The altar in the middle, and it is the reason to walk in.
    pieces.append(
        Piece("altar" if rng.random() < 0.6 else "cairn", STANDING, cx, cy + 0.4, 0,
              rng.random() < 0.5)
    )

    # Bones inside the ring, denser toward the middle.
    for _ in range(rng.randint(7, 12)):
        angle = rng.uniform(0, math.tau)
        r = rng.uniform(0.6, radius * 0.95) ** 0.7
        pieces.append(Piece("bones", DECAL, cx + math.cos(angle) * r,
                            cy + math.sin(angle) * r * 0.7, rng.randrange(6)))
    for _ in range(rng.randint(2, 5)):
        angle = rng.uniform(0, math.tau)
        r = rng.uniform(0.5, radius)
        pieces.append(Piece("blood", DECAL, cx + math.cos(angle) * r,
                            cy + math.sin(angle) * r * 0.7, rng.randrange(6)))
    # OFFERINGS, AT THE FEET OF THE CARVINGS. Scattered anywhere inside the
    # ring these were containers that happened to be in a circle of statues;
    # placed at a statue's base they are things somebody CARRIED here and put
    # down in front of one, which is the same prop doing an entirely different
    # job. The angle is reused from the ring, so the offering and the figure it
    # was left for line up rather than nearly lining up.
    for _ in range(rng.randint(1, 3)):
        index = rng.randrange(count)
        angle = start + math.tau * index / count
        pieces.append(_from_pool(rng, STASH_POOL,
                                 cx + math.cos(angle) * (radius - 0.9)
                                 + rng.uniform(-0.4, 0.4),
                                 cy + math.sin(angle) * (radius - 0.7) * 0.62 + 0.8))
    # Broken stone between the figures, swept out from the middle. It is what
    # says the ring is OLDER than the bodies in it — the bones arrived recently
    # and the masonry has been coming apart for a long time.
    for _ in range(rng.randint(3, 6)):
        angle = rng.uniform(0, math.tau)
        r = rng.uniform(radius * 0.7, radius * 1.15)
        pieces.append(Piece("debris", DECAL, cx + math.cos(angle) * r,
                            cy + math.sin(angle) * r * 0.7, rng.randrange(6)))
    # And a path worn in to it, from one side only.
    approach = rng.uniform(0, math.tau)
    pieces += _trail(cx + math.cos(approach) * (radius + 2.2),
                     cy + math.sin(approach) * (radius + 1.6),
                     cx + math.cos(approach) * 1.4,
                     cy + math.sin(approach) * 1.1, rng, step=1.0, wander=0.3)
    return Layout(width, height, tuple(pieces))


def _den(rng: random.Random) -> Layout:
    """THE DEN. Where the alpha sleeps, and the only scene about an ANIMAL.

    Every other place on this map is about people: a car that stopped, a fence
    that failed, a shrine somebody built, a wreck somebody died in. The den is
    the first one that is not — nobody made it, nobody left it, something
    LIVES here — and every decision below is aimed at that being readable
    before the shape in the middle of it resolves.

      * IT IS A HOLLOW, NOT A CLEARING. The scene is walled on one side by
        felled trunks lying the same way, which is the one arrangement in this
        forest that is neither a crash nor a construction: it is where a big
        animal dragged its cover into a heap.
      * THE FLOOR IS BONES, and there are more of them here than anywhere
        except the shrine. The shrine's bones say "standing here has cost
        other people something"; these say "this is where it eats", which is
        the same sentence about a different subject.
      * THE KILLS CAME FROM SOMEWHERE. Clothes, dropped packs and blood run
        OUT of the hollow along a drag mark rather than sitting in it — the
        trail is the scene's only piece of narration and it points at where
        the thing hunts.
      * IT PAYS. `loot.SCENE_COUNTS` gives it the second-best scatter in the
        game and the stashes are what its victims were carrying, because the
        bargain has to be worth the animal: a den with nothing in it is a
        thing you walk around, and walking around it is the outcome the
        encounter is supposed to make you EARN.

    NO LIGHT, deliberately, and it is the one place that pointedly does not
    get one. A scene light makes a place a destination you choose from across
    the dark (see `SceneLight`), which is exactly right for a shrine and
    exactly wrong here: the whole encounter is that your own lantern reaches
    further than the thing's ears do, so the lamp is what finds the den and
    the finding is the reward for carrying it lit.
    """
    width, height = 12, 10
    cx, cy = width / 2, height / 2
    # The lee: trunks piled along one side, all lying the same way.
    lee = rng.uniform(0, math.tau)
    pieces: list[Piece] = []
    for index in range(rng.randint(3, 5)):
        offset = (index - 1) * 1.6
        pieces.append(
            Piece(
                "logs",
                STANDING,
                cx + math.cos(lee) * 3.2 - math.sin(lee) * offset,
                cy + math.sin(lee) * 2.4 + math.cos(lee) * offset * 0.7,
                rng.randrange(4),
                rng.random() < 0.5,
            )
        )
    # The floor of the hollow. Denser toward the middle, which is where it lies.
    for _ in range(rng.randint(9, 14)):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(0.3, 3.4) ** 0.7
        pieces.append(
            Piece("bones", DECAL, cx + math.cos(angle) * radius,
                  cy + math.sin(angle) * radius * 0.7, rng.randrange(6))
        )
    for _ in range(rng.randint(3, 6)):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(0.4, 3.0)
        pieces.append(
            Piece("blood", DECAL, cx + math.cos(angle) * radius,
                  cy + math.sin(angle) * radius * 0.7, rng.randrange(6))
        )
    # The drag mark, out of the hollow and away. One direction only: it is
    # where the kills come FROM, and a trail with two ends is a path.
    drag = lee + math.pi + rng.uniform(-0.6, 0.6)
    pieces += _trail(cx + math.cos(drag) * 1.0, cy + math.sin(drag) * 0.8,
                     cx + math.cos(drag) * 4.6, cy + math.sin(drag) * 3.6,
                     rng, step=0.9, wander=0.45)
    for _ in range(rng.randint(1, 3)):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(1.2, 3.6)
        pieces.append(
            Piece("clothes", DECAL, cx + math.cos(angle) * radius,
                  cy + math.sin(angle) * radius * 0.7, rng.randrange(5))
        )
    # What they were carrying, at the edge of the hollow rather than under the
    # animal — a container you cannot reach without waking it is not a choice.
    for _ in range(rng.randint(1, 2)):
        angle = rng.uniform(0, math.tau)
        pieces.append(
            _from_pool(rng, STASH_POOL, cx + math.cos(angle) * 3.6,
                       cy + math.sin(angle) * 2.8 + 0.5)
        )
    return Layout(width, height, tuple(pieces))


#: (kind, builder, weight). Weights are the pacing.
#:
#: `deadfall` is still the most common thing on the map and that is not an
#: oversight — a forest where every clearing has a wreck in it is a scrapyard,
#: and the loud scenes only land if most of the woods is just woods. The
#: vehicle scenes together are about a third of the roll: enough that a walk
#: crosses two or three, few enough that the fourth one still gets looked at.
SCENES = (
    ("deadfall", _deadfall, 22),
    ("roadside", _roadside, 16),
    ("dumpsite", _dumpsite, 12),
    ("trailhead", _trailhead, 11),
    ("boundary", _boundary, 10),
    ("flight", _flight, 9),
    ("last_stand", _last_stand, 9),
    ("checkpoint", _checkpoint, 7),
    ("convoy", _convoy, 6),
    ("haulage", _haulage, 6),
    ("busstop", _busstop, 5),
    ("medevac", _medevac, 5),
)


def _woodpile(rng: random.Random) -> Layout:
    """Firewood, stacked. Camp furniture — it says somebody keeps this place.

    No containers. Those are forest loot you open or smash; a barrel by the
    fire would be a shop in the one zone that is not supposed to have one.
    """
    width, height = 4, 3
    pieces = [
        Piece("logs", STANDING, rng.uniform(1.0, 2.2), rng.uniform(1.4, 2.4),
              rng.randrange(4), rng.random() < 0.5)
        for _ in range(rng.randint(2, 3))
    ]
    return Layout(width, height, tuple(pieces))


def _marker(rng: random.Random) -> Layout:
    """One sign, standing alone. The cheapest scene there is and still a scene:
    a board on a post in an empty clearing is somebody's decision about where
    people should go."""
    return Layout(2, 2, (Piece("sign", STANDING, 1.0, 1.4, rng.randrange(3)),))


#: What may stand in the CAMP. The camp is the party's own ground and the one
#: place in the game that is not hostile, so it gets the scenes that read as
#: "people live here" and none of the ones that read as "people died here".
#: A wreck outside the fire you are about to sit at is a promise the zone does
#: not keep. No containers either — those become live objects and the camp is
#: not a loot zone.
CAMP_POOL = (
    ("woodpile", _woodpile, 18),
    ("marker", _marker, 8),
    ("deadfall", _deadfall, 4),
)

#: THE LANDMARKS. Attempted first, in order, on their own and before the
#: weighted pool — because they are the two largest layouts by a wide margin
#: and both are ONE PER MAP. Rolled in with everything else they lose every
#: anchor race to a 4x3 woodpile and a player can go three expeditions without
#: seeing either; and a second shrine turns the first one from a place into a
#: prop, which is just as true of a second den.
#:
#: THE SHRINE IS FIRST BECAUSE IT IS BIGGER (13x13 against 12x10) and because
#: the thread is routed through it (`populate` keeps the first landmark that
#: lands as the route's far end). A run has one place it is walking TOWARD;
#: the den is a thing it walks PAST, and it should not be able to take over
#: the shape of the night.
LANDMARKS = (
    ("sanctuary", _sanctuary),
    ("den", _den),
)

#: Scenes per map, before rejections. A map that rolls badly gets fewer, which
#: is fine — an empty stretch of woods is a legitimate outcome.
#:
#: Raised with the map. The forest is roughly twice the area it was, and
#: holding the old count would have made the same number of stories float in
#: twice the emptiness, which is not atmosphere, it is a longer walk.
FOREST_SCENES = (13, 18)
#: The camp is small and mostly hearth. Three is furniture; eight is a junkyard.
CAMP_SCENES = (3, 5)
#: Tiles between two scene anchors. Below this they read as one heap.
MIN_SEPARATION = 11.0
#: Placement attempts per scene. Rejection sampling: most failures are a scene
#: landing in a thicket, which is cheap to detect and cheaper to retry.
ATTEMPTS = 40


def _pick(rng: random.Random, pool):
    total = sum(weight for _, _, weight in pool)
    roll = rng.uniform(0, total)
    for kind, builder, weight in pool:
        roll -= weight
        if roll <= 0:
            return kind, builder
    return pool[0][0], pool[0][1]


#: Share of a scene's box that may be scrub the placement is allowed to clear.
#: Demanding a perfectly bald rectangle rejects nearly every anchor in a forest
#: whose whole point is scattered cover; allowing the scene to CLEAR its own
#: plot is both easier to place and truer — a homestead stands in a clearing
#: because somebody made one, and a woodpile sits where the wood came from.
CLEARABLE = 0.4


def _plot(tiles: list[list[int]], x0: int, y0: int, w: int, h: int) -> list[tuple[int, int]] | None:
    """The scrub inside this box, or None if the box cannot host a scene.

    FIRE and VOID are refusals, not scrub: the bonfire is the camp's anchor and
    VOID is the walk-out corridor, and both have code elsewhere that assumes
    they are exactly where they were put. PROP and LOW are refusals too — those
    are another scene's things, and scenes do not stack.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    if x0 < 0 or y0 < 0 or x0 + w > width or y0 + h > height:
        return None
    scrub: list[tuple[int, int]] = []
    for ty in range(y0, y0 + h):
        row = tiles[ty]
        for tx in range(x0, x0 + w):
            tile = row[tx]
            if tile == FLOOR:
                continue
            if tile in (ROCK, TREE):
                scrub.append((tx, ty))
                continue
            return None
    if len(scrub) > w * h * CLEARABLE:
        return None
    return scrub


def _reachable(tiles: list[list[int]], anchor: tuple[int, int]) -> set[tuple[int, int]]:
    """Every floor tile reachable from `anchor`, as a set.

    Anchored rather than seeded from the first floor tile in scan order, which
    is what `maps.count_reachable` does. That distinction is not academic: the
    camp is a clearing inside a ragged treeline and its first floor tile in
    scan order is a two-tile pocket between trunks, so a whole-map "is
    everything connected" test answers no before a scene has touched anything.
    What actually matters is whether the ground the PLAYERS are standing on
    stays connected, and that is a flood from where they stand.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    start = _nearest_floor(tiles, anchor)
    if start is None:
        return set()

    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and tiles[ny][nx] == FLOOR:
                if (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
    return seen


def _nearest_floor(
    tiles: list[list[int]], anchor: tuple[int, int]
) -> tuple[int, int] | None:
    """Walkable tile closest to `anchor`. The anchor itself is often not one —
    the camp's is the bonfire, which is solid."""
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    ax, ay = anchor
    for radius in range(0, max(width, height)):
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                # Ring only: the interior was covered by a smaller radius.
                if radius and max(abs(ox), abs(oy)) != radius:
                    continue
                tx, ty = ax + ox, ay + oy
                if 0 <= tx < width and 0 <= ty < height and tiles[ty][tx] == FLOOR:
                    return tx, ty
    return None


def _grow(
    tiles: list[list[int]],
    reach: set[tuple[int, int]],
    added: list[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Expand `reach` by newly opened floor that touches it.

    Clearing a plot can join a sealed pocket onto the players' ground. Walking
    only from the tiles we just opened finds that pocket without flooding the
    whole map again — the set we already hold is the cache.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    grown = set(reach)
    stack: list[tuple[int, int]] = []
    for tx, ty in added:
        if (tx, ty) in grown or tiles[ty][tx] != FLOOR:
            continue
        if any((tx + dx, ty + dy) in grown for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            grown.add((tx, ty))
            stack.append((tx, ty))
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and tiles[ny][nx] == FLOOR:
                if (nx, ny) not in grown:
                    grown.add((nx, ny))
                    stack.append((nx, ny))
    return grown


def _stamp(
    tiles: list[list[int]],
    layout: Layout,
    x0: int,
    y0: int,
    scrub: list[tuple[int, int]],
    anchor: tuple[int, int],
    reach: set[tuple[int, int]],
    cleared: list[tuple[int, int, int]],
) -> set[tuple[int, int]] | None:
    """Clear the plot and claim what the props stand on, or leave the map alone.

    Returns the new reachable set, or None if the scene was rejected.

    Clearing only ever ADDS floor, so it cannot disconnect anything. Solid props
    can — a fence run is a LINE, and a line is the one shape that seals things —
    so the connectivity guarantee is re-checked here and the failure path
    REVERTS. It does not drill: a corridor cut through a cabin to keep the map
    connected is a map with a hole in a cabin, and a gap punched in a fence
    somewhere other than its gate is a fence that stopped meaning anything.
    Rejected scenes just try another anchor.
    """
    cells = [
        (tx, ty, kind)
        for tx, ty, kind in _cells(layout, x0, y0)
        # Props overhang their scene's box — a log at the edge can reach past
        # it — so cells are bounds-checked here rather than assumed inside.
        if 0 <= ty < len(tiles) and 0 <= tx < len(tiles[0]) and tiles[ty][tx] == FLOOR
    ]

    changed: list[tuple[int, int, int]] = []
    for tx, ty in scrub:
        changed.append((tx, ty, tiles[ty][tx]))
        tiles[ty][tx] = FLOOR
    for tx, ty, kind in cells:
        changed.append((tx, ty, FLOOR))
        tiles[ty][tx] = kind

    if not cells:
        # Nothing solid went down, so nothing can have been cut off — but the
        # cleared scrub may have joined a pocket on, so the set has to grow.
        cleared.extend(changed)
        return _grow(tiles, reach, scrub) if changed else reach

    # The invariant is "nothing that was reachable stopped being reachable,
    # other than what we just built on". Not "the whole map is one region" —
    # both generators leave sealed pockets in their treelines that were never
    # connected to begin with, and holding a scene responsible for those means
    # no scene ever places.
    #
    # Tested as SET CONTAINMENT, not by comparing counts. Clearing scrub can
    # connect a pre-existing pocket at the same moment a fence orphans a
    # corner, and the two cancel out in a total — so the count version passes a
    # scene that just stranded a piece of the map.
    built = {(tx, ty) for tx, ty, _ in cells}
    if not (built & reach):
        # Building on a pocket the players could never reach cannot cut their
        # ground. Grow if we cleared, skip the flood.
        if changed:
            cleared.extend(item for item in changed if item[2] in (ROCK, TREE))
            return _grow(tiles, reach, scrub)
        return reach
    after = _reachable(tiles, anchor)
    if reach <= after | built:
        # Only the scrub it cleared, and only on success — a reverted scene put
        # everything back itself.
        cleared.extend(item for item in changed if item[2] in (ROCK, TREE))
        return after
    for tx, ty, was in changed:
        tiles[ty][tx] = was
    return None


def populate(
    tiles: list[list[int]],
    rng: random.Random,
    *,
    count: tuple[int, int] = FOREST_SCENES,
    avoid: tuple[tuple[float, float, float], ...] = (),
    pool=SCENES,
    separation: float = MIN_SEPARATION,
    landmark=None,
    tries: int = ATTEMPTS,
    thread: bool = False,
    anchor: tuple[int, int] | None = None,
) -> Population:
    """Place scenes on a finished map. Mutates `tiles`; returns what was placed.

    `avoid` is a list of (tile x, tile y, radius in tiles) the scenes must keep
    out of — the spawn clearing, the camp hearth, the mouth of the exit. Those
    are places the game needs legible and empty, and a story told on top of
    them is a story nobody can walk around.

    `thread` links what was placed into ONE story — see `_thread`.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    # Where the players will be standing. Everything a scene builds has to
    # leave this connected to itself — see `_stamp`.
    origin = anchor or (width // 2, height // 2)
    placed: list[PlacedScene] = []
    landmark_at: tuple[float, float] | None = None
    props: list[Prop] = []
    lights: list[PlacedLight] = []
    #: Scrub the scenes cleared, with what it used to be. See `_seal`.
    cleared: list[tuple[int, int, int]] = []
    # Carried across attempts instead of recomputed on both sides of every
    # stamp: the set only changes when a scene actually lands, and a flood of
    # the whole map per attempt is most of what map generation costs.
    reach = _reachable(tiles, origin)

    def attempt(layout: Layout, budget: int, kind: str) -> bool:
        nonlocal reach
        # Before anything is measured: the plot test, the tile claims and the
        # props all read the same piece list, so the pile has to be thinned
        # once, here, and not per consumer.
        layout = _thin_containers(layout, rng)
        for _ in range(budget):
            # The border stays untouched: it is the treeline that keeps the
            # camera from framing the end of the world, and a scene allowed to
            # clear its plot there would open a hole straight through it.
            x0 = rng.randrange(BORDER, max(BORDER + 1, width - layout.width - BORDER))
            y0 = rng.randrange(BORDER, max(BORDER + 1, height - layout.height - BORDER))
            cx = x0 + layout.width / 2
            cy = y0 + layout.height / 2

            if any(math.hypot(cx - ax, cy - ay) < radius for ax, ay, radius in avoid):
                continue
            if any(math.hypot(cx - scene.x, cy - scene.y) < separation for scene in placed):
                continue
            scrub = _plot(tiles, x0, y0, layout.width, layout.height)
            if scrub is None:
                continue
            grown = _stamp(tiles, layout, x0, y0, scrub, origin, reach, cleared)
            if grown is None:
                continue
            reach = grown

            placed.append(PlacedScene(kind, cx, cy))
            for light in layout.lights:
                lights.append(
                    PlacedLight(
                        x=(x0 + light.dx) * TILE_SIZE,
                        y=(y0 + light.dy) * TILE_SIZE,
                        radius_tiles=light.radius_tiles,
                        kind=light.kind,
                    )
                )
            for piece in layout.pieces:
                props.append(
                    Prop(
                        kind=piece.kind,
                        x=(x0 + piece.dx) * TILE_SIZE,
                        y=(y0 + piece.dy) * TILE_SIZE,
                        variant=piece.variant,
                        flip=piece.flip,
                        layer=piece.layer,
                    )
                )
            return True
        return False

    # The landmarks go down first, on an empty map and with a much bigger
    # budget: they are the only layouts that need a large box of open ground,
    # and every scene already standing is one more thing to collide with.
    #
    # `landmark_at` is the FIRST one that lands and the thread is routed
    # through it (see `_route`). A run has one place it is walking toward; the
    # rest are places it walks past.
    for kind, builder in landmark or ():
        if attempt(builder(rng), tries * 6, kind) and landmark_at is None:
            landmark_at = (placed[-1].x, placed[-1].y)

    for _ in range(rng.randint(*count)):
        kind, builder = _pick(rng, pool)
        attempt(builder(rng), tries, kind)

    _seal(tiles, origin, cleared)

    route: list[tuple[float, float]] = []
    if thread:
        positions = [(scene.x, scene.y) for scene in placed]
        route = _route(positions, landmark_at, (float(origin[0]), float(origin[1])), rng)
        props.extend(_thread(tiles, route, rng))
    return Population(props=props, lights=lights, scenes=placed, route=route)


def _seal(
    tiles: list[list[int]],
    anchor: tuple[int, int],
    cleared: list[tuple[int, int, int]],
) -> None:
    """Put back any scrub whose clearing left an orphan tile of floor.

    A scene clears its own plot, and a plot corner can poke into a thicket. The
    tile that gets cleared there comes out surrounded by trunks — a one-tile
    island of walkable ground nothing can ever reach. Harmless to look at and
    fatal to `build_forest`, which asserts every floor tile is reachable.

    Only tiles THIS pass cleared are considered. Both generators leave sealed
    pockets in their own treelines and those are not ours to tidy: filling them
    would salt the camp's treeline with boulders that were never there.
    """
    if not cleared:
        return
    reach = _reachable(tiles, anchor)
    for tx, ty, was in cleared:
        if tiles[ty][tx] == FLOOR and (tx, ty) not in reach:
            tiles[ty][tx] = was


def _route(
    placed: list[tuple[float, float]],
    landmark_at: tuple[float, float] | None,
    origin: tuple[float, float],
    rng: random.Random,
) -> list[tuple[float, float]]:
    """Pick the scenes the thread runs through, in the order it visits them.

    Ordered by distance from the spawn clearing, so the story reads OUTWARD:
    the first thing you find is the least conclusive and the last is the
    landmark. That direction matters more than which scenes get picked — a
    trail that starts at the cabin and peters out is the same props in the
    same places telling you nothing.

    This is also the structure an EXTRACTION point wants. The route is a walk
    from the spawn to the far end of the map through places worth stopping at;
    dropping the extraction at or beyond `route[-1]` gives a run with a shape
    (out along the story, back through it with your pockets full) instead of a
    randomly placed errand.
    """
    if len(placed) < 3:
        return []
    ranked = sorted(placed, key=lambda p: math.hypot(p[0] - origin[0], p[1] - origin[1]))
    # Skip the nearest: a trail that starts on the spawn clearing's doorstep
    # reads as a tutorial arrow rather than as something you came across.
    candidates = [p for p in ranked[1:] if p != landmark_at]
    if not candidates:
        return []
    span = min(len(candidates), rng.randint(2, 3))
    route = candidates[:span]
    if landmark_at is not None:
        route.append(landmark_at)
    return route


def _thread(
    tiles: list[list[int]],
    route: list[tuple[float, float]],
    rng: random.Random,
) -> list[Prop]:
    """One trail linking the route's scenes, escalating as it goes.

    THIS IS THE DIFFERENCE BETWEEN A MAP WITH STORIES ON IT AND A MAP WITH A
    STORY. Seven independent tableaux are seven things you walk past. The same
    seven with prints running between them are a route somebody took, and the
    player can follow it — which turns reading the scenery from something they
    might do into something they choose to do.

    It escalates: blood gets more frequent along the way and the last leg ends
    in a drag. The order is what carries that, and the order came from `_route`.

    Prints that land on anything but open floor are DROPPED rather than moved.
    A trail that breaks where it crosses a thicket and picks up on the far side
    is what a real one does; one that bends around every trunk to stay visible
    reads as a drawn line.
    """
    if len(route) < 2:
        return []
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    props: list[Prop] = []

    for leg, (start, end) in enumerate(zip(route, route[1:])):
        last = leg == len(route) - 2
        # Long legs get sparser prints: a full-density trail across a third of
        # the map is thousands of decals and reads as a paved path.
        pieces = _trail(*start, *end, rng, step=1.6, wander=0.5)
        # Blood frequency climbs along the thread — whoever this was, it was
        # getting worse.
        bleed = 0.04 + leg * 0.05
        for piece in pieces:
            tx, ty = int(piece.dx), int(piece.dy)
            if not (0 <= tx < width and 0 <= ty < height) or tiles[ty][tx] != FLOOR:
                continue
            props.append(
                Prop(piece.kind, piece.dx * TILE_SIZE, piece.dy * TILE_SIZE,
                     piece.variant, piece.flip, piece.layer)
            )
            if rng.random() < bleed:
                props.append(
                    Prop("blood", piece.dx * TILE_SIZE, piece.dy * TILE_SIZE,
                         rng.choice((0, 3)), False, DECAL)
                )
        if last:
            # The last few metres are a drag, not a walk.
            for step in range(3):
                t = 0.7 + step * 0.1
                x = start[0] + (end[0] - start[0]) * t
                y = start[1] + (end[1] - start[1]) * t
                tx, ty = int(x), int(y)
                if 0 <= tx < width and 0 <= ty < height and tiles[ty][tx] == FLOOR:
                    props.append(Prop("blood", x * TILE_SIZE, y * TILE_SIZE, 2, False, DECAL))
    return props


def to_payload(population: Population) -> dict:
    """The map payload's scenery half: a legend plus compact rows.

    Kinds are interned into a legend because the same seven strings would
    otherwise be repeated a few hundred times, and this message is already the
    largest one the server sends.
    """
    kinds: list[str] = []
    for prop in population.props:
        if prop.kind not in kinds:
            kinds.append(prop.kind)
    return {
        "propKinds": kinds,
        "props": [prop.to_row(kinds) for prop in population.props],
        "lights": [light.to_row() for light in population.lights],
    }
