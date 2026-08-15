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
from .maps import count_reachable
from .world import FLOOR, PROP, ROCK, TREE

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
class Layout:
    """A scene resolved into local tile space, before it is anchored."""

    width: int
    height: int
    #: Tile offsets that become PROP. Only buildings claim tiles — see below.
    solid: tuple[tuple[int, int], ...]
    pieces: tuple[Piece, ...]


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

    # The cabin's own tiles. Five wide and three deep — the sprite is taller
    # than that, but a building's FOOTPRINT is its ground floor, and letting
    # the roof claim tiles would make players bounce off the eaves.
    solid = tuple(
        (int(cabin_x) + ox, int(cabin_y) + oy) for ox in range(5) for oy in range(3)
    )

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
    return Layout(width, height, solid, tuple(pieces))


def _campsite(rng: random.Random) -> Layout:
    width, height = 9, 8
    cx, cy = width / 2, height / 2
    flip = rng.random() < 0.5

    tent_x, tent_y = cx + rng.uniform(-1.6, 1.6), cy - 1.4
    solid = tuple((int(tent_x) - 1 + ox, int(tent_y) - 1 + oy) for ox in range(3) for oy in range(1))

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
    return Layout(width, height, solid, tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


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
    return Layout(width, height, (), tuple(pieces))


def _stores(rng: random.Random) -> Layout:
    """Crates and sacks against the treeline. Supplies, not wreckage."""
    width, height = 4, 3
    pieces = [
        Piece("crate", STANDING, rng.uniform(0.7, 3.3), rng.uniform(1.4, 2.6),
              rng.choice((0, 2, 3, 4)))
        for _ in range(rng.randint(2, 4))
    ]
    return Layout(width, height, (), tuple(pieces))


def _marker(rng: random.Random) -> Layout:
    """One sign, standing alone. The cheapest scene there is and still a scene:
    a board on a post in an empty clearing is somebody's decision about where
    people should go."""
    return Layout(2, 2, (), (Piece("sign", STANDING, 1.0, 1.4, rng.randrange(3)),))


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
    they are exactly where they were put. PROP is a refusal too — that is
    another scene's building.
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


def _stamp(
    tiles: list[list[int]],
    layout: Layout,
    x0: int,
    y0: int,
    scrub: list[tuple[int, int]],
) -> bool:
    """Clear the plot and claim the building's tiles, or leave the map as it was.

    Clearing only ever ADDS floor, so it cannot disconnect anything. Buildings
    can, which is why the connectivity guarantee is re-checked here and why the
    failure path reverts instead of drilling: a corridor cut through a cabin to
    keep the map connected is a map with a hole in a cabin.
    """
    changed: list[tuple[int, int, int]] = []
    for tx, ty in scrub:
        changed.append((tx, ty, tiles[ty][tx]))
        tiles[ty][tx] = FLOOR
    for ox, oy in layout.solid:
        tx, ty = x0 + ox, y0 + oy
        changed.append((tx, ty, tiles[ty][tx]))
        tiles[ty][tx] = PROP

    if not layout.solid:
        return True
    floor = sum(row.count(FLOOR) for row in tiles)
    if count_reachable(tiles) == floor:
        return True
    for tx, ty, was in changed:
        tiles[ty][tx] = was
    return False


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
) -> list[Prop]:
    """Place scenes on a finished map. Mutates `tiles`; returns the drawables.

    `avoid` is a list of (tile x, tile y, radius in tiles) the scenes must keep
    out of — the spawn clearing, the camp hearth, the mouth of the exit. Those
    are places the game needs legible and empty, and a story told on top of
    them is a story nobody can walk around.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    placed: list[tuple[float, float]] = []
    props: list[Prop] = []

    def attempt(layout: Layout, budget: int) -> bool:
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
            if not _stamp(tiles, layout, x0, y0, scrub):
                continue

            placed.append((cx, cy))
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
    if landmark is not None:
        attempt(landmark(rng), tries * 6)

    for _ in range(rng.randint(*count)):
        attempt(_pick(rng, pool)(rng), tries)
    return props


def to_payload(props: list[Prop]) -> dict:
    """The map payload's scenery half: a legend plus compact rows.

    Kinds are interned into a legend because the same seven strings would
    otherwise be repeated a few hundred times, and this message is already the
    largest one the server sends.
    """
    kinds: list[str] = []
    for prop in props:
        if prop.kind not in kinds:
            kinds.append(prop.kind)
    return {"propKinds": kinds, "props": [prop.to_row(kinds) for prop in props]}
