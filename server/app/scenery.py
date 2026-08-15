"""Scenes: the things people left behind, placed in GROUPS that mean something.

`mapgen.py` grows a forest. This grows what happened in it.

THE RULE THIS MODULE EXISTS TO ENFORCE
A prop scattered by a hash is texture. A tent, a cold firepit, a dropped pack
and a line of boot prints walking away from all three is a sentence, and the
player reads it whether or not they notice they are reading. So nothing here
places a single object: the unit of placement is a SCENE — a small handful of
props with fixed relationships — and the procedural part is which scenes, in
what order, facing which way, with which details rolled in.

That is also why this is server-side. Everything else the client draws comes
off the map seed, because one rock is as good as another and both sides can
agree on a hash. A scene cannot work that way: it has to know that a doorway is
open ground and that the blood trail runs OUT of it, it may make tiles solid,
and reproducing that on the client would mean mirroring this whole file the way
`simulation.py` is mirrored. The map already ships as tiles; scenes ship beside
them as a flat list of drawables and cost a few hundred bytes.

THE SCENES

    homestead   a cabin, its fence, a sign at the approach. Somebody LIVED
                here. Tracks go IN through the door and do not come out.
    campsite    tent, cold firepit, logs to sit on, a pack still open. Left
                fast — the tracks leave, the gear does not.
    last_stand  no shelter and no comfort: a barricade of logs, spent glass,
                bones, and blood in a ring. It ended here.
    deadfall    felled trunks and stumps, nothing human at all. The quiet
                scene, and it is load-bearing — a forest where every clearing
                has a story is a theme park, and the loud ones only land if
                most of the woods is just woods.
    boundary    a fence run with a gap smashed through it, and prints in the
                gap. Something did not use the gate.
    trailhead   footprints crossing open ground, one dropped thing at the
                start, blood halfway, nothing at the end.
    dumpsite    crates, sacks, a cart wheel off its axle. A supply run that
                did not arrive.

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


#: Light kinds. The client maps these to tones; the numbers are the contract.
LAMP = 0
EMBER = 1
#: Reserved. The EXTRACTION point will be a light like any other — that is the
#: whole reason this is a list on the map payload and not a field on the cabin.
#: When extraction lands, the room drops one `SceneLight(BEACON, ...)` at the
#: chosen tile and the client already knows how to burn it, feed the fov with
#: it and draw its glow. Nothing about that is a rendering change.
BEACON = 2


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
class Population:
    """Everything one call to `populate` put on a map.

    `props` and `lights` go on the wire. `scenes` and `route` do not, yet —
    they are where the scenes ended up, in TILES, and the order the thread
    walks them. They are returned rather than thrown away because the
    EXTRACTION point is going to want exactly this: a set of places worth
    standing in, and a direction that leads away from spawn. Placing extraction
    at or past `route[-1]` gives a run a shape — out along the story, back
    through it carrying something — where a uniformly random tile gives an
    errand.
    """

    props: list[Prop]
    lights: list[PlacedLight]
    scenes: list[tuple[float, float]]
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
#: The kind matters as much as the size. A CABIN is a building: it stops light.
#: Everything else here is waist-high, so it is LOW — solid to bodies and
#: bullets, transparent to sight. You take cover behind a log, you do not
#: disappear behind it.
#:
#: Widths match the sheets in `make_scenery.py` (cabin 5, tent 2, logs 2,
#: the rest 1). Depth is the contact slab, not the sprite height — a cabin's
#: roof is 4.5 tiles tall and must not be a wall you bounce off.
FOOTPRINTS: dict[str, tuple[int, int, int]] = {
    "cabin": (5, 3, PROP),
    "tent": (2, 1, PROP),
    "logs": (2, 1, LOW),
    "crate": (1, 1, LOW),
    "fence": (1, 1, LOW),
    "sign": (1, 1, LOW),
}


def _cells(layout: Layout, x0: int, y0: int) -> list[tuple[int, int, int]]:
    """Every tile this scene's standing pieces claim, as (tx, ty, kind).

    A standing piece is anchored on its CONTACT POINT — bottom centre — so the
    footprint is centred on `dx` and grows upward from `dy`. That is the same
    anchor the client draws from, which is the point: the tiles you bump into
    are computed from the same number that decides where the sprite lands.
    """
    cells: list[tuple[int, int, int]] = []
    for piece in layout.pieces:
        spec = FOOTPRINTS.get(piece.kind)
        if spec is None or piece.layer != STANDING:
            continue
        width, depth, kind = spec
        bx = int(math.floor(x0 + piece.dx - width / 2 + 0.5))
        by = int(math.floor(y0 + piece.dy - depth + 0.5))
        for oy in range(depth):
            for ox in range(width):
                cells.append((bx + ox, by + oy, kind))
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
# where the gap in a fence falls, how far a trail runs, which way somebody was
# going. A table of fixed offsets would give seven scenes; these give seven
# KINDS of scene.


def _homestead(rng: random.Random) -> Layout:
    width, height = 12, 10
    cabin_x, cabin_y = 3.5, 4.0
    flip = rng.random() < 0.5
    ruined = rng.random() < 0.45

    pieces = [Piece("cabin", STANDING, cabin_x + 2.5, cabin_y + 3.0, 1 if ruined else 0, flip)]

    # The door is off centre in the art; the story hangs off knowing where.
    door_x = cabin_x + (3.4 if flip else 1.6)
    door_y = cabin_y + 3.0

    # A fence running out from one side, with a gate gap the path goes through.
    fence_y = cabin_y + 5.5
    gap = rng.randrange(3, width - 4)
    for tx in range(1, width - 1):
        if gap <= tx <= gap + 1:
            continue
        distance = abs(tx - gap)
        # Ruin concentrates AT the gap: the further from whatever came
        # through, the more of the fence is still standing.
        state = 0 if distance > 4 else min(5, 5 - distance + rng.randint(-1, 1))
        pieces.append(Piece("fence", STANDING, tx + 0.5, fence_y, max(0, state)))

    pieces.append(Piece("sign", STANDING, gap + 0.5, fence_y - 0.4, rng.randrange(3)))

    # Somebody's things against the wall.
    for _ in range(rng.randint(2, 4)):
        pieces.append(
            Piece(
                "crate",
                STANDING,
                cabin_x + rng.uniform(-0.6, 5.4),
                cabin_y + 3.0 + rng.uniform(0.1, 0.7),
                rng.randrange(5),
            )
        )
    pieces.append(Piece("clothes", DECAL, door_x + rng.uniform(-0.8, 0.8), door_y + 0.9,
                       rng.randrange(5)))

    # Tracks come up the path and go IN. They do not come out, and that is the
    # only thing this scene is trying to say.
    pieces += _trail(gap + 0.5, fence_y + 1.4, door_x, door_y + 0.6, rng)
    if rng.random() < 0.7:
        pieces.append(Piece("blood", DECAL, door_x + rng.uniform(-0.5, 0.5),
                            door_y + 0.4, rng.choice((1, 2, 5))))

    # A lamp still lit over the door, most of the time. It is the only warm
    # point on a dark map that is not a player, and it does two jobs at once:
    # it makes the landmark FINDABLE from across the woods, and it asks the
    # question the rest of the scene refuses to answer — somebody lit that.
    lights: tuple[SceneLight, ...] = ()
    if rng.random() < 0.75:
        lights = (SceneLight(door_x + (0.9 if flip else -0.9), door_y - 0.4, 3.4, LAMP),)
    return Layout(width, height, tuple(pieces), lights)


def _campsite(rng: random.Random) -> Layout:
    width, height = 9, 8
    cx, cy = width / 2, height / 2
    flip = rng.random() < 0.5

    tent_x, tent_y = cx + rng.uniform(-1.6, 1.6), cy - 1.4
    pieces = [
        Piece("tent", STANDING, tent_x, tent_y, rng.randrange(3), flip),
        Piece("firepit", STANDING, cx, cy + 1.0, rng.randrange(3)),
    ]
    # Two logs pulled up to the fire — the detail that makes it a place people
    # sat rather than a pile of equipment.
    for side in (-1, 1):
        if rng.random() < 0.75:
            pieces.append(
                Piece("logs", STANDING, cx + side * rng.uniform(1.5, 2.2),
                      cy + 1.0 + rng.uniform(-0.5, 0.8), rng.randrange(4), side < 0)
            )
    for _ in range(rng.randint(1, 3)):
        pieces.append(
            Piece("crate", STANDING, cx + rng.uniform(-3, 3), cy + rng.uniform(-1.5, 2.2),
                  rng.randrange(5))
        )
    # Somebody's pack, still open, and their coat where they were sitting.
    pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-2, 2), cy + rng.uniform(0, 2), 2))
    if rng.random() < 0.6:
        pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-2, 2), cy + rng.uniform(-1, 1),
                            rng.randrange(5)))
    pieces.append(Piece("debris", DECAL, cx + rng.uniform(-2.5, 2.5), cy + rng.uniform(-1, 2),
                        rng.randrange(6)))

    # And they left in a hurry, in one direction, all at once.
    angle = rng.uniform(0, math.tau)
    pieces += _trail(cx, cy + 1.6, cx + math.cos(angle) * 4.2, cy + math.sin(angle) * 3.4, rng)

    # Sometimes the fire is only just out, and that changes what the scene
    # says: cold ash is history, live embers are a WARNING. Rare enough that
    # finding one means something.
    lights: tuple[SceneLight, ...] = ()
    if rng.random() < 0.3:
        lights = (SceneLight(cx, cy + 1.0, 2.2, EMBER),)
    return Layout(width, height, tuple(pieces), lights)


def _last_stand(rng: random.Random) -> Layout:
    width, height = 8, 8
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
    return Layout(width, height, tuple(pieces))


def _dumpsite(rng: random.Random) -> Layout:
    width, height = 7, 6
    cx, cy = width / 2, height / 2
    pieces = [Piece("debris", DECAL, cx + rng.uniform(-1, 1), cy + rng.uniform(-1, 1), 5)]
    for _ in range(rng.randint(3, 6)):
        pieces.append(
            Piece("crate", STANDING, cx + rng.uniform(-2.4, 2.4), cy + rng.uniform(-1.6, 2.0),
                  rng.randrange(5))
        )
    for _ in range(rng.randint(1, 2)):
        pieces.append(
            Piece("debris", DECAL, cx + rng.uniform(-2.5, 2.5), cy + rng.uniform(-2, 2),
                  rng.randrange(6))
        )
    if rng.random() < 0.5:
        pieces.append(Piece("clothes", DECAL, cx + rng.uniform(-2, 2), cy + rng.uniform(-2, 2),
                            rng.randrange(5)))
    return Layout(width, height, tuple(pieces))


#: (builder, weight). Weights are the pacing: `deadfall` is common because most
#: of a forest has to be unremarkable, and `homestead` is rare because a
#: landmark stops being one the moment there are three of them.
SCENES = (
    (_deadfall, 26),
    (_campsite, 17),
    (_boundary, 14),
    (_trailhead, 14),
    (_last_stand, 12),
    (_dumpsite, 11),
)

def _woodpile(rng: random.Random) -> Layout:
    """Firewood, stacked. Camp furniture — it says somebody keeps this place."""
    width, height = 4, 3
    pieces = [
        Piece("logs", STANDING, rng.uniform(1.0, 2.2), rng.uniform(1.4, 2.4),
              rng.randrange(4), rng.random() < 0.5)
        for _ in range(rng.randint(2, 3))
    ]
    if rng.random() < 0.5:
        pieces.append(Piece("crate", STANDING, rng.uniform(0.8, 3.2), rng.uniform(1.6, 2.6), 3))
    return Layout(width, height, tuple(pieces))


def _stores(rng: random.Random) -> Layout:
    """Crates and sacks against the treeline. Supplies, not wreckage."""
    width, height = 4, 3
    pieces = [
        Piece("crate", STANDING, rng.uniform(0.7, 3.3), rng.uniform(1.4, 2.6),
              rng.choice((0, 2, 3, 4)))
        for _ in range(rng.randint(2, 4))
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
#: A last stand outside the tent you are about to sleep in is a promise the
#: zone does not keep.
CAMP_POOL = (
    (_stores, 12),
    (_woodpile, 12),
    (_marker, 6),
    (_deadfall, 4),
)

#: The one LANDMARK. Attempted first and on its own, before the weighted pool,
#: because it is the largest layout by a wide margin: rolled in with everything
#: else it loses every anchor race to a 4x3 woodpile and a player can go three
#: expeditions without seeing a building. One per map, never two — a second
#: cabin turns the first one from a place into a prop.
LANDMARK = _homestead

#: Scenes per map, before rejections. A map that rolls badly gets fewer, which
#: is fine — an empty stretch of woods is a legitimate outcome.
FOREST_SCENES = (7, 11)
#: The camp is small and mostly hearth. Three is furniture; eight is a junkyard.
CAMP_SCENES = (3, 5)
#: Tiles between two scene anchors. Below this they read as one heap.
MIN_SEPARATION = 11.0
#: Placement attempts per scene. Rejection sampling: most failures are a scene
#: landing in a thicket, which is cheap to detect and cheaper to retry.
ATTEMPTS = 40


def _pick(rng: random.Random, pool):
    total = sum(weight for _, weight in pool)
    roll = rng.uniform(0, total)
    for builder, weight in pool:
        roll -= weight
        if roll <= 0:
            return builder
    return pool[0][0]


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
    placed: list[tuple[float, float]] = []
    landmark_at: tuple[float, float] | None = None
    props: list[Prop] = []
    lights: list[PlacedLight] = []
    #: Scrub the scenes cleared, with what it used to be. See `_seal`.
    cleared: list[tuple[int, int, int]] = []
    # Carried across attempts instead of recomputed on both sides of every
    # stamp: the set only changes when a scene actually lands, and a flood of
    # the whole map per attempt is most of what map generation costs.
    reach = _reachable(tiles, origin)

    def attempt(layout: Layout, budget: int) -> bool:
        nonlocal reach
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
            if any(math.hypot(cx - px, cy - py) < separation for px, py in placed):
                continue
            scrub = _plot(tiles, x0, y0, layout.width, layout.height)
            if scrub is None:
                continue
            grown = _stamp(tiles, layout, x0, y0, scrub, origin, reach, cleared)
            if grown is None:
                continue
            reach = grown

            placed.append((cx, cy))
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

    # The landmark goes down first, on an empty map and with a much bigger
    # budget: it is the only layout that needs a large box of open ground, and
    # every scene already standing is one more thing for it to collide with.
    if landmark is not None and attempt(landmark(rng), tries * 6):
        landmark_at = placed[-1]

    for _ in range(rng.randint(*count)):
        attempt(_pick(rng, pool)(rng), tries)

    _seal(tiles, origin, cleared)

    route: list[tuple[float, float]] = []
    if thread:
        route = _route(placed, landmark_at, (float(origin[0]), float(origin[1])), rng)
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
