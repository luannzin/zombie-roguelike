"""The extraction point: one per forest, and the only thing on a map that
ANSWERS BACK.

Everything else the generator lays down is finished before the player arrives.
A cabin is a cabin whether you look at it or not; a crate has exactly one thing
left to do and then it is gone. The rift is the first object in this game with a
STATE MACHINE: it sits dormant until somebody walks up to the console and
presses it, and then it spends four seconds becoming something else while the
whole party watches.

WHY THIS IS SERVER-SIDE AND WHY IT SHIPS COORDINATES
Same reason `scenery.py` is. Placement has to know which ground is open, it
makes tiles solid, and every client has to agree on where the thing is down to
the pixel — so the server picks the spot, stamps the tiles, and ships absolute
world positions. The client never re-derives the arrangement. The `layout` block
in `assets/processed/rift/manifest.json` is the ART's copy of the same offsets,
and `_LAYOUT` below mirrors it exactly; if one moves the other has to, the same
way `TRACK_DIRECTIONS` is one number in three files.

WHERE IT GOES
At the far end of the story. `scenery.Population.route` is a walk from the spawn
clearing outward through the scenes that landed, ordered so the last stop is the
landmark — the module has said since it was written that this is what extraction
wants. Dropping the rift at `route[-1]` gives a run a SHAPE: out along the
trail, and back through it with your pockets full. A uniformly random tile gives
an errand.

THE TIMELINE IS THE SHEETS
`CHARGE_TIME` and `EMERGE_TIME` are `frames / fps` out of `server/tools/
make_rift.py`, and the client mirrors this whole block through `client_config`
so there is one clock. The gaps between them are the ceremony: the console
answers first, then the stones catch ONE AT A TIME so the light visibly runs
around the ring, and only once the last crown is lit does the middle tear open.
Firing all four together costs nothing and reads as a light switch.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import TILE_SIZE
from .world import FLOOR, LOW, PROP

KIND = "rift"

#: The plot, in tiles. Mirrors `PLOT_TILES` in server/tools/make_rift.py.
PLOT = 7

#: Where each piece stands inside the plot, in TILE offsets from its top-left.
#: Mirrors `_layout()` in server/tools/make_rift.py. A standing piece's `dy` is
#: the BOTTOM EDGE of the row it stands on — its contact point — exactly as in
#: `scenery.Piece`. There is no `flip`: the stones are shaded from the upper
#: left and a mirrored one is lit from the wrong side, which is why the art
#: ships four cuts instead of two.
_PILLARS: tuple[tuple[float, float, int], ...] = (
    (0.5, 1.0, 0),
    (PLOT - 0.5, 1.0, 1),
    (0.5, float(PLOT), 2),
    (PLOT - 0.5, float(PLOT), 3),
)
_CONSOLE = (PLOT / 2.0, float(PLOT))
_CENTRE = (PLOT / 2.0, PLOT / 2.0)
_ANOMALY = (PLOT / 2.0, PLOT / 2.0 + 0.5)

#: Radius of the beacon once it is open, in tiles. Small on purpose: this is
#: not an area of safety, it is a thing you can see from far away — which is
#: the whole point of putting a light on it. `kind` 2 is `scenery.BEACON`.
LIGHT_TILES = 3.5
LIGHT_KIND = 2

# --- the timeline ------------------------------------------------------------
# Sheet durations. Change a sheet's `frames / fps` in make_rift.py and these
# change with it, or the sprite finishes before the state does.
CHARGE_TIME = 14 / 14
EMERGE_TIME = 20 / 16

#: The console answers before anything else does. Without this beat the press
#: and the first stone are the same instant and the button reads as decoration.
CONSOLE_LAG = 0.35
#: One stone at a time, so the light RUNS AROUND THE RING. This number is the
#: single most load-bearing one in the file: at 0 the structure switches on, at
#: 0.45 it wakes up.
PILLAR_STAGGER = 0.45
#: A held breath between the last crown and the tear. The pause is what makes
#: the tear land — the same trick `make_vfx.py` documents between a summon's
#: charge and its strike.
SETTLE = 0.30

PILLARS = 4
LAST_PILLAR_AT = CONSOLE_LAG + (PILLARS - 1) * PILLAR_STAGGER
CROWNED_AT = LAST_PILLAR_AT + CHARGE_TIME
EMERGE_AT = CROWNED_AT + SETTLE
OPEN_AT = EMERGE_AT + EMERGE_TIME

DORMANT = "dormant"
CHARGING = "charging"
OPEN = "open"


def pillar_charge_at(index: int) -> float:
    """When stone `index` starts waking, in seconds after the press."""
    return CONSOLE_LAG + index * PILLAR_STAGGER


@dataclass
class Rift:
    """One placed extraction point, in world pixels."""

    tx: int
    ty: int
    x: float
    y: float
    console_x: float
    console_y: float
    anomaly_x: float
    anomaly_y: float
    pillars: tuple[tuple[float, float, int], ...]
    state: str = DORMANT
    #: Seconds since the console was pressed. Only meaningful while CHARGING,
    #: and it is on the wire so a player who joins mid-sequence sees the rest
    #: of it rather than a structure that snaps to finished.
    elapsed: float = 0.0

    def step(self, dt: float) -> bool:
        """Advance the sequence. True when the state changed this tick."""
        if self.state != CHARGING:
            return False
        self.elapsed += dt
        if self.elapsed >= OPEN_AT:
            self.state = OPEN
            self.elapsed = OPEN_AT
            return True
        return False

    def geometry_payload(self) -> dict:
        """The static half: where the pieces are. Rides on the map payload."""
        return {
            "tx": self.tx,
            "ty": self.ty,
            "plot": PLOT,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "anomaly": [round(self.anomaly_x, 1), round(self.anomaly_y, 1)],
            "console": [round(self.console_x, 1), round(self.console_y, 1)],
            "pillars": [[round(px, 1), round(py, 1), shape] for px, py, shape in self.pillars],
            "lightTiles": LIGHT_TILES,
            "lightKind": LIGHT_KIND,
            **self.state_payload(),
        }

    def state_payload(self) -> dict:
        """The live half: what it is doing. Rides on the snapshot when dirty."""
        return {"state": self.state, "t": round(self.elapsed, 2)}


def from_payload(row: dict | None) -> Rift | None:
    if not row:
        return None
    return Rift(
        tx=int(row["tx"]),
        ty=int(row["ty"]),
        x=float(row["x"]),
        y=float(row["y"]),
        anomaly_x=float(row["anomaly"][0]),
        anomaly_y=float(row["anomaly"][1]),
        console_x=float(row["console"][0]),
        console_y=float(row["console"][1]),
        pillars=tuple((float(p[0]), float(p[1]), int(p[2])) for p in row["pillars"]),
        state=str(row.get("state", DORMANT)),
        elapsed=float(row.get("t", 0.0)),
    )


# --- placement ---------------------------------------------------------------

#: Tiles of treeline kept clear at every edge. Matches `scenery.BORDER`.
BORDER = 2
#: How much of the plot must ALREADY be open ground for a spot to qualify.
#:
#: This is the connectivity rule wearing a costume. Clearing a 7x7 box adds
#: floor connected to whatever it touches, so a box drilled into deep forest
#: comes out as an island nobody can reach and `build_forest` refuses the map.
#: Requiring that the plot is mostly a clearing already means the structure is
#: found in a space rather than punched into the trees — which is also the
#: better read: somebody chose this spot.
MIN_OPEN = 0.55


def place(
    tiles: list[list[int]],
    route: list[tuple[float, float]],
    origin: tuple[float, float],
    rng: random.Random,
) -> Rift | None:
    """Clear a plot, stamp its tiles, and return the rift standing in it.

    Mutates `tiles`. Returns None if the map has nowhere to put one, which is
    survivable — a forest without an extraction point is a forest you leave the
    way you came — and is why the caller treats the rift as optional.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    if width < PLOT + BORDER * 2 or height < PLOT + BORDER * 2:
        return None

    aim = route[-1] if route else None
    for tx, ty in _candidates(width, height, aim, origin, rng):
        if not _plot_open(tiles, tx, ty):
            continue
        return _stamp(tiles, tx, ty)
    return None


def _candidates(
    width: int,
    height: int,
    aim: tuple[float, float] | None,
    origin: tuple[float, float],
    rng: random.Random,
):
    """Plot corners to try, best first.

    Ordered by distance from the aim — the end of the story thread — so the
    extraction lands where the trail was already leading. With no thread it
    falls back to "as far from the spawn clearing as possible", which keeps the
    walk home long even on a map with nothing to say.
    """
    corners = [
        (tx, ty)
        for ty in range(BORDER, height - PLOT - BORDER)
        for tx in range(BORDER, width - PLOT - BORDER)
    ]
    if aim is not None:
        target = (aim[0] - PLOT / 2.0, aim[1] - PLOT / 2.0)
        corners.sort(key=lambda c: math.hypot(c[0] - target[0], c[1] - target[1]))
    else:
        corners.sort(
            key=lambda c: -math.hypot(
                c[0] + PLOT / 2.0 - origin[0], c[1] + PLOT / 2.0 - origin[1]
            )
        )
    # A little noise on the front of the list, so two maps that happen to put
    # their last scene in the same place do not put the rift on the same tile.
    head = corners[:24]
    rng.shuffle(head)
    return head + corners[24:]


def _plot_open(tiles: list[list[int]], tx: int, ty: int) -> bool:
    """Whether a plot at this corner is a clearing rather than a thicket.

    Rejects any plot that already contains a building or cover: those tiles
    belong to a scene, and dropping a monolith through somebody's cabin is the
    one placement bug that would be visible from across the map.
    """
    open_tiles = 0
    for oy in range(PLOT):
        for ox in range(PLOT):
            kind = tiles[ty + oy][tx + ox]
            if kind in (PROP, LOW):
                return False
            if kind == FLOOR:
                open_tiles += 1
    if tiles[ty + PLOT // 2][tx + PLOT // 2] != FLOOR:
        return False
    return open_tiles >= PLOT * PLOT * MIN_OPEN


def _stamp(tiles: list[list[int]], tx: int, ty: int) -> Rift:
    """Clear the plot to floor, then put the structure's own tiles back.

    A pillar is PROP — solid AND sight-blocking. It is a three-metre stone, and
    the four of them throwing hard shadows across the pad is worth more than the
    convenience of shooting through them. The console is LOW: waist-high cover
    you can see over and shoot over, which is what you want on the one tile the
    party will be standing on.
    """
    for oy in range(PLOT):
        for ox in range(PLOT):
            tiles[ty + oy][tx + ox] = FLOOR

    pillars: list[tuple[float, float, int]] = []
    for dx, dy, shape in _PILLARS:
        # Same arithmetic as `scenery._cells` for a 1-wide piece: the tile is
        # the one containing the point just ABOVE the contact, so the feet are
        # what claims ground and a capstone drawn overhead claims nothing.
        px = int(math.floor(tx + dx))
        py = int(math.floor(ty + dy - 1e-6))
        tiles[py][px] = PROP
        pillars.append(((tx + dx) * TILE_SIZE, (ty + dy) * TILE_SIZE, shape))

    cx = int(math.floor(tx + _CONSOLE[0]))
    cy = int(math.floor(ty + _CONSOLE[1] - 1e-6))
    tiles[cy][cx] = LOW

    return Rift(
        tx=tx,
        ty=ty,
        x=(tx + _CENTRE[0]) * TILE_SIZE,
        y=(ty + _CENTRE[1]) * TILE_SIZE,
        anomaly_x=(tx + _ANOMALY[0]) * TILE_SIZE,
        anomaly_y=(ty + _ANOMALY[1]) * TILE_SIZE,
        console_x=(tx + _CONSOLE[0]) * TILE_SIZE,
        console_y=(ty + _CONSOLE[1]) * TILE_SIZE,
        pillars=tuple(pillars),
    )
