"""The extraction point: one or more per forest, scaled by the day, and the
only thing on a map that ANSWERS BACK.

WHAT IT IS
An abandoned cargo skid — an iron box open at the front, still half loaded with
crates nobody came back for — with four dead lift drones parked at its corners
on the ropes they were rigged with. Pressing the console wakes the first drone:
it spools up, climbs until its line comes straight, and holds there. Every
overfeed tier past the quota wakes another one. Pressing a paid console makes
the woken drones take the weight: the skid strains, breaks ground, and flies
off along a heading the map rolled when it placed the pad, climbing until it is
gone. What is left is the hole it was sitting in.

The name `rift` is what this module was called when the extraction point was a
tear in the world with stones around it. The wire, the config and twenty client
files still say `rift`, and renaming them buys nothing a line here cannot say.
The art it used to draw is still in `assets/processed/rift/` — this pad borrows
its CONSOLE and its TORCH, and nothing else.

ONE PAD AT A TIME, AND THE PLAYER SENDS IT
A night's pads are a queue, not a menu: `Room` refuses a console while another
platform is awake, so three pads is three separate walks. Each carries its own
quota (`pad_need`). Paying it does not launch the platform — it ARMS the
console, which goes gold, and pressing again is what starts the lift. That
extra press is what makes overfeeding possible at all: the window between
"paid" and "gone" is time the party chooses to spend, and everything they load
during it comes back at the far end as one dense object (`LEVEL_STEPS` and
`Room._drop_excess`). A timer never launched a platform and never did.

THE DRONES ARE THE METER
`level_for` is the overfeed tier and `awake` is `1 + tier`, capped at four. So
how much has gone into a pad is legible from across the clearing without a
number: one drone turning is the minimum, four is a party that emptied their
bags into it. That is the same job the anomaly's colour tiers used to do, moved
onto something with moving parts.

WHY THIS IS SERVER-SIDE AND WHY IT SHIPS COORDINATES
Same reason `scenery.py` is. Placement has to know which ground is open, it
makes tiles solid, and every client has to agree on where the thing is to the
pixel — so the server picks the spot, stamps the tiles, and ships absolute
world positions. The client never re-derives the arrangement. The `layout`
block in `assets/processed/platform/manifest.json` is the ART's copy of the
same offsets and `_LAYOUT` below mirrors it exactly; if one moves the other
has to.

WHERE IT GOES
At the far end of the story. `scenery.Population.route` is a walk from the
spawn clearing outward through the scenes that landed, ordered so the last stop
is the landmark. Dropping the pad at `route[-1]` gives a run a SHAPE: out along
the trail, and back through it with your pockets full. A uniformly random tile
gives an errand.

THE TIMELINE IS THE RIG
Every duration below is a physical claim about a machine — how long four
rotors take to reach lift speed, how long a line takes to come straight, how
long a tonne of iron argues with the ground before it lets go. The client
mirrors this whole block through `client_config` so there is one clock.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .config import TILE_SIZE
from .maps import count_reachable
from .world import FLOOR, LOW, PROP

KIND = "rift"

#: The plot, in tiles. Mirrors `plot` in server/tools/make_platform.py.
PLOT = 7

#: Where each piece stands inside the plot, in TILE offsets from its top-left.
#: Mirrors `_layout()` in server/tools/make_platform.py. A standing piece's
#: `dy` is the BOTTOM EDGE of the row it stands on — its contact point —
#: exactly as in `scenery.Piece`.
#:
#: The skid is 5 tiles wide and its contact is two rows up from the plot's own
#: edge, which is what leaves standing room in front of it for the console and
#: the torch. A structure that filled its plot would be a wall with a button.
_PLATFORM = (PLOT / 2.0, 5.0)

#: The tiles the box actually SITS ON, as (x, y, w, h) from the plot corner.
#: These go solid — see `_stamp`. THE PLAYER MAY NOT GET ON THE PLATFORM: it is
#: cargo space, and a party standing on the deck when it lifts would be a whole
#: second physics problem for no gameplay.
_DECK = (1, 3, 5, 2)

#: The four drones, in the DIAGONAL order the art and the client both use:
#: front-left, back-right, front-right, back-left. Parked outside the skid's
#: own columns, so a body can still walk down either side of the pad — and
#: opposite corners first, so a platform lifting on two drones hangs level
#: instead of hinging.
_DRONES: tuple[tuple[float, float], ...] = (
    (0.5, 5.0),
    (PLOT - 0.5, 3.0),
    (PLOT - 0.5, 5.0),
    (0.5, 3.0),
)
DRONES = len(_DRONES)

#: On the approach row, in front of the skid. The console is the one piece the
#: player has to walk up to; out on the plot's own south edge a tree growing
#: just past the plot drew its canopy — painted several tiles above its trunk —
#: straight over it.
_CONSOLE = (PLOT / 2.0, PLOT - 1.0)
#: THE TORCH IS THE PAD'S ADDRESS, and it burns from the moment the map is
#: built. Everything else here is dark until somebody presses the button, and a
#: landmark you can only see once you have already found it is not a landmark —
#: so the same torch that dresses the exit corridor stands on the approach,
#: lit, all night. It is the one piece of this structure whose whole job is to
#: be visible from somewhere else.
_TORCH = (1.0, PLOT - 1.0)
#: The middle of the deck's footprint: where the imprint is centred, where the
#: pad's light comes from, and where the condensed core lands once the skid has
#: flown and the ground under it is walkable again.
_CENTRE = (PLOT / 2.0, 4.0)

#: Radius of the pad's own light once it is powered, in tiles.
#:
#: Bigger than a cabin lamp, smaller than the campfire. It has to light the pad
#: — you can see what is coming at you, which is the difference between a
#: beacon and a lamp — without washing the forest around it. `kind` 2 is
#: `scenery.BEACON`.
LIGHT_TILES = 4.0
LIGHT_KIND = 2

# --- the timeline ------------------------------------------------------------

#: The console answers before anything else does. Without this beat the press
#: and the first rotor are the same instant and the button reads as decoration.
CONSOLE_LAG = 0.30
#: Rotors from dead to lift speed. THE SINGLE MOST LOAD-BEARING NUMBER HERE: at
#: 0 a drone switches on, at 0.85 it winds up, and winding up is the difference
#: between a prop that changed frame and a machine that started.
DRONE_SPOOL = 0.85
#: The climb, from the ground to wherever its own rope runs out. The rope
#: coming STRAIGHT is the end of this — the client eases the drone up until the
#: line has no sag left, which is why the hover height is not a number here.
DRONE_RISE = 0.85
#: One drone's whole wake-up, and the beat every later drone repeats when an
#: overfeed tier lands.
DRONE_WAKE = DRONE_SPOOL + DRONE_RISE
#: Held between two drones woken by the SAME press. See `sync_drones`.
DRONE_LAG = 0.34

OPEN_AT = CONSOLE_LAG + DRONE_WAKE

#: How long the platform waits if nothing feeds it. INFINITE: the window closes
#: when a player launches it, not on a clock. `begin_collapse` walks the SPENT
#: path.
OPEN_TIME = math.inf

# --- the lift ----------------------------------------------------------------
#
# THE LAUNCH IS THREE BEATS AND THEY ARE NOT INTERCHANGEABLE. A platform that
# simply rose would be an elevator; what makes this land is that the ground
# argues first.

#: Rotors to maximum, lines taut, the skid rattling in its own hole and not
#: moving. Everything the party can see is straining and nothing has happened
#: yet — this is the beat that says the thing is HEAVY.
LIFT_STRAIN = 1.10
#: It breaks ground. The ground under it is uncovered on the first frame of
#: this window, the deck's tiles go walkable, and the burst fires.
LIFT_BREAK = 0.45
#: The flight: up and away along `heading`, accelerating, shrinking, gone.
LIFT_CLIMB = 3.30

#: When the skid comes free, measured from the launch press.
BREAK_AT = LIFT_STRAIN
#: The whole launch. Named `COLLAPSE_TIME` because `Rift.step` and the client
#: both time the pad's end off one number and this is it.
COLLAPSE_TIME = LIFT_STRAIN + LIFT_BREAK + LIFT_CLIMB

COLLAPSE_AT = OPEN_AT + OPEN_TIME
SPENT_AT = COLLAPSE_AT + COLLAPSE_TIME

DORMANT = "dormant"
CHARGING = "charging"
OPEN = "open"
#: Gone. The console is dead, the drones went with the platform, and the ground
#: keeps the mark — the whole point of the state is that the map remembers.
SPENT = "spent"


# --- overfeeding ---------------------------------------------------------------
#
# THE QUOTA IS A FLOOR, NOT A CEILING, and that is the whole decision the pad
# exists to offer. Paying exactly what it asks lets you launch. Keeping the bag
# going past that does not — the platform takes everything, and it WAKES
# ANOTHER DRONE for each tier, so a party can read from across the clearing how
# much has gone in.
#
# What buys that back is `excess_item` in `room.py`: what you overpaid comes
# back as one dense object you carry to the NEXT pad. Overfeeding is therefore
# never a donation, it is moving value forward through a bag that has a slot
# count — which is the only reason it is worth doing at all.

#: How many tiers past the quota the rig walks before it stops. One per extra
#: drone, so the art and the economy cannot disagree about the ceiling.
MAX_LEVEL = DRONES - 1
#: Where each tier starts, as a fraction of the quota paid ON TOP of it. The
#: first is any overpayment at all, so a single item past the line already wakes
#: something; the two above it are half again and double.
LEVEL_STEPS: tuple[float, ...] = (0.0, 0.5, 1.0)


def level_for(fed: int, need: int) -> int:
    """Which overfeed tier `fed` sits in against a quota of `need`. 0..MAX_LEVEL."""
    if need <= 0 or fed <= need:
        return 0
    over = (fed - need) / need
    level = sum(1 for step in LEVEL_STEPS if over >= step)
    return min(MAX_LEVEL, max(1, level))


@dataclass
class Rift:
    """One placed extraction platform, in world pixels."""

    tx: int
    ty: int
    x: float
    y: float
    console_x: float
    console_y: float
    torch_x: float
    torch_y: float
    #: Contact point of the skid — the row its beams stand on.
    deck_x: float
    deck_y: float
    #: Ground contact of each parked drone, in `_DRONES` order.
    drones: tuple[tuple[float, float], ...]
    #: Which way it leaves, in radians. Rolled at placement rather than at
    #: launch so it rides on the map payload: every client has to agree about
    #: where a departing platform went, and a client that joined during the
    #: climb has to be able to place it.
    heading: float = 0.0
    id: str = "r0"
    state: str = DORMANT
    #: Seconds since the console was pressed. Only meaningful while CHARGING or
    #: OPEN, and it is on the wire so a player who joins mid-sequence sees the
    #: rest of it rather than a rig that snaps to finished.
    elapsed: float = 0.0
    #: When the launch begins, in the same clock as `elapsed`. None while the
    #: platform is holding. Set by `begin_collapse` on the tick a player sends
    #: it — not by an authored window.
    close_at: float | None = None
    #: `elapsed` at which each drone started spooling, in `_DRONES` order. The
    #: length IS how many are awake, and shipping the times rather than a count
    #: is what lets a drone that woke thirty seconds ago be already hovering
    #: while the one that woke this tick is still winding up.
    woke: list[float] = field(default_factory=list)
    #: The deck's tiles have been handed back to the floor. Server-side truth
    #: about the map, and it rides on the geometry payload because that payload
    #: is also the room's STORE — a rehydrate must not re-free ground that is
    #: already free.
    freed: bool = False
    #: The console has been pressed. Server-only in spirit; the extract quest
    #: ticks off this, not off standing nearby.
    found: bool = False
    #: Catalog value THIS pad asks for. Per-pad rather than per-night: only one
    #: platform may be awake at a time, so a night with three of them is three
    #: separate walks and three separate bills.
    need: int = 0
    #: Catalog value put into it. May go past `need` — see `level_for`.
    fed: int = 0
    #: What the overpayment condensed into, banked when the launch starts and
    #: spent when it finishes. Zero once the drop has been placed, so a pad
    #: cannot pay out twice however the room ticks.
    excess: int = 0

    @property
    def ready(self) -> bool:
        """Quota paid and still on the ground: the console is a launch button."""
        return self.state == OPEN and self.close_at is None and self.fed >= self.need

    @property
    def level(self) -> int:
        return level_for(self.fed, self.need)

    @property
    def awake(self) -> int:
        """How many drones should be turning. One, plus one per overfeed tier."""
        if self.state in (DORMANT, SPENT):
            return 0
        return min(DRONES, 1 + self.level)

    @property
    def lifted(self) -> bool:
        """The skid has broken ground. Its tiles are no longer anybody's wall."""
        return self.close_at is not None and self.elapsed >= self.close_at + BREAK_AT

    def feed(self, value: int) -> None:
        if value > 0:
            self.fed += value

    def press(self) -> None:
        """Wake the pad: power up, first drone spooling after `CONSOLE_LAG`.

        The lag lives HERE rather than in the room, because it is a fact about
        this rig — the console answers, and a moment later something on the
        skid starts turning. Waking the first drone on the same tick as the
        press makes the button read as a light switch.
        """
        self.state = CHARGING
        self.elapsed = 0.0
        self.woke = [CONSOLE_LAG]

    def sync_drones(self) -> bool:
        """Wake whatever the current tier is owed. True if anything changed.

        Each new drone starts its spool at the moment the tier landed, so two
        drones woken by two different presses are never in phase — which is
        what makes a four-drone rig look like four machines rather than one
        sprite drawn four times.
        """
        want = self.awake
        if len(self.woke) >= want:
            return False
        added = 0
        # A bag big enough to cross two tiers on one press wakes two drones,
        # and they must not wake on the same frame: two identical machines
        # spooling in perfect sync read as one sprite drawn twice. A third of a
        # second apart is enough that the ear and the eye both get two events.
        while len(self.woke) < want:
            self.woke.append(round(self.elapsed + added * DRONE_LAG, 2))
            added += 1
        return True

    def step(self, dt: float) -> bool:
        """Advance the sequence. True when the state changed this tick.

        One clock for the whole life of the thing: spool, hold, launch and gone
        are all read off `elapsed`, so there is no separate timer to fall out of
        step and a client that joins at any point can be told where it is with
        one number.
        """
        if self.state in (DORMANT, SPENT):
            return False
        self.elapsed += dt
        changed = False
        if self.state == CHARGING and self.elapsed >= OPEN_AT:
            self.state = OPEN
            changed = True
        if (
            self.state == OPEN
            and self.close_at is not None
            and self.elapsed >= self.close_at + COLLAPSE_TIME
        ):
            self.state = SPENT
            self.elapsed = self.close_at + COLLAPSE_TIME
            changed = True
        return changed

    def begin_collapse(self) -> bool:
        """Start the launch. True if this call changed anything.

        A player sending a paid platform is what ends a pad, not a timer. A
        dormant one just stays dead. A pad still spooling is jumped to open so
        the lift has a rig to strain against rather than a half-played wake-up.

        The overpayment is BANKED HERE and paid out at SPENT, because the drop
        belongs to the moment the skid is gone — it is what did not fit aboard.
        """
        if self.state == SPENT:
            return False
        if self.state == DORMANT:
            self.state = SPENT
            self.elapsed = 0.0
            return True
        if self.state == CHARGING and self.elapsed < OPEN_AT:
            self.elapsed = OPEN_AT
            self.state = OPEN
        if self.close_at is None:
            self.close_at = self.elapsed
            self.excess = max(0, self.fed - self.need)
            self.sync_drones()
            return True
        return False

    def deck_tiles(self) -> list[tuple[int, int]]:
        """The tiles the box stands on, in map coordinates."""
        dx, dy, dw, dh = _DECK
        return [
            (self.tx + dx + ox, self.ty + dy + oy)
            for oy in range(dh)
            for ox in range(dw)
        ]

    def geometry_payload(self) -> dict:
        """The static half: where the pieces are. Rides on the map payload.

        Also the room's STORE — `Room._load_rifts` hydrates straight back out
        of it — which is why `found`, `excess` and `freed` ride along here and
        not on the snapshot's state row. They reach the client as a side effect
        of that and none of them is a secret.
        """
        return {
            "found": self.found,
            "excess": self.excess,
            "freed": self.freed,
            "id": self.id,
            "tx": self.tx,
            "ty": self.ty,
            "plot": PLOT,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "deck": [round(self.deck_x, 1), round(self.deck_y, 1)],
            "console": [round(self.console_x, 1), round(self.console_y, 1)],
            "torch": [round(self.torch_x, 1), round(self.torch_y, 1)],
            "drones": [[round(dx, 1), round(dy, 1)] for dx, dy in self.drones],
            "heading": round(self.heading, 3),
            "lightTiles": LIGHT_TILES,
            "lightKind": LIGHT_KIND,
            **self.state_payload(),
        }

    def state_payload(self) -> dict:
        """The live half: what it is doing. Rides on the snapshot when dirty.

        `level` is derived and shipped anyway, and `woke` is shipped because
        the client cannot derive it: a tier's wake time is the moment somebody
        pressed a button, which is not a function of anything the client holds.
        """
        row = {
            "id": self.id,
            "state": self.state,
            "t": round(self.elapsed, 2),
            "fed": self.fed,
            "need": self.need,
            "level": self.level,
            "woke": list(self.woke),
        }
        if self.close_at is not None:
            row["closeAt"] = round(self.close_at, 2)
        if self.ready:
            row["ready"] = True
        return row


def from_payload(row: dict | None) -> Rift | None:
    if not row:
        return None
    close = row.get("closeAt")
    return Rift(
        tx=int(row["tx"]),
        ty=int(row["ty"]),
        x=float(row["x"]),
        y=float(row["y"]),
        deck_x=float(row["deck"][0]),
        deck_y=float(row["deck"][1]),
        console_x=float(row["console"][0]),
        console_y=float(row["console"][1]),
        torch_x=float(row["torch"][0]),
        torch_y=float(row["torch"][1]),
        drones=tuple((float(p[0]), float(p[1])) for p in row["drones"]),
        heading=float(row.get("heading", 0.0)),
        id=str(row.get("id", "r0")),
        state=str(row.get("state", DORMANT)),
        elapsed=float(row.get("t", 0.0)),
        close_at=None if close is None else float(close),
        woke=[float(v) for v in row.get("woke") or []],
        freed=bool(row.get("freed", False)),
        need=int(row.get("need", 0)),
        fed=int(row.get("fed", 0)),
        excess=int(row.get("excess", 0)),
        found=bool(row.get("found", False)),
    )


def from_payloads(rows: list | None) -> list[Rift]:
    out: list[Rift] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        placed = from_payload(row)
        if placed is not None:
            out.append(placed)
    return out


def count_for_day(day: int) -> int:
    """How many extraction points a forest of this day carries.

    The first two nights are one pad — find it, feed it, run. After that the
    woods grow more of them, so the walk is longer and the feed quota has more
    mouths. Capped at three: a fourth is another errand, not a harder night.
    """
    if day <= 2:
        return 1
    if day <= 4:
        return 2
    return 3


def night_need(day: int, count: int) -> int:
    """Catalog value the party has to load across the whole night.

    Scales with the day AND with how many pads landed, so a cramped map that
    only fitted one still asks less than a night that found room for three.
    """
    return 24 * max(1, day) + 16 * max(0, count - 1)


def pad_need(day: int, count: int) -> int:
    """What ONE pad asks for.

    The night's bill split evenly, because only one platform may be awake at a
    time: three pads is three walks and three separate payments, not one pot
    you can empty at whichever console you reached first. Rounded up, so the
    pads together never ask for less than the night was supposed to cost.
    """
    pads = max(1, count)
    total = night_need(day, pads)
    return max(1, -(-total // pads))


# --- placement ---------------------------------------------------------------

#: Tiles of treeline kept clear at every edge. Matches `scenery.BORDER`.
BORDER = 2

#: KEEP-OUT FROM THE MAP'S OWN EDGE, in tiles, beyond the plot itself.
#:
#: `BORDER` alone is the treeline's width — enough to stop a scene hanging off
#: the world, and nowhere near enough for this. The extraction point is a place
#: you fight AT: you get pushed off it, you circle it, you come back to it. Two
#: tiles of forest behind it means half of that happens against an invisible
#: wall, and the map's edge is the one wall with nothing on screen explaining
#: it. It is also the destination of the whole run, so landing it in a corner
#: wastes the walk out that `route` exists to shape.
EDGE_MARGIN = 8
#: How much of the plot must ALREADY be open ground for a spot to qualify.
#:
#: This is the connectivity rule wearing a costume. Clearing a 7x7 box adds
#: floor connected to whatever it touches, so a box drilled into deep forest
#: comes out as an island nobody can reach and `build_forest` refuses the map.
#: Requiring that the plot is mostly a clearing already means the structure is
#: found in a space rather than punched into the trees — which is also the
#: better read: somebody chose this spot to leave it in.
MIN_OPEN = 0.70
#: And the MARGIN ring around it has to be mostly open too.
#:
#: The plot gets cleared, so trees inside it are not the problem — trees just
#: OUTSIDE it are. A canopy is drawn several tiles above its own trunk, so a
#: treeline hugging the south edge paints leaves over the structure standing
#: inside. Requiring the ring to be open as well is what puts the whole thing
#: in a clearing instead of in a hole cut out of a thicket.
MIN_MARGIN_OPEN = 0.55

#: THE STRUCTURE STANDS ALONE, and these three numbers are what enforce it.
#:
#: Everything else on this map is somebody's leftovers, arranged into scenes
#: that mean something. The skid is not part of any of them, and dropping it
#: beside a cabin makes it read as that homestead's equipment — the one reading
#: that costs it the whole "somebody flew this in and never came back" effect.
#:
#: `MARGIN` also protects the approach: a fence or a woodpile lapping onto the
#: pad would be cover the player fights from on the one tile they are supposed
#: to be standing exposed on.
SCENE_CLEARANCE = 13.0
SPAWN_CLEARANCE = 20.0
MARGIN = 3


def place_many(
    tiles: list[list[int]],
    route: list[tuple[float, float]],
    scenes: list[tuple[float, float]],
    origin: tuple[float, float],
    rng: random.Random,
    count: int,
) -> list[Rift]:
    """Place up to `count` extraction points. The first follows the story
    thread; the rest go as far from spawn and from each other as the clearances
    allow. Fewer than asked is survivable — the quest need is however many
    actually landed.
    """
    want = max(0, count)
    if want == 0:
        return []
    placed: list[Rift] = []
    keepout = list(scenes)
    for index in range(want):
        # The first pad is the end of the trail. Later ones have no thread to
        # honour, so they fall back to "as far from spawn as possible", which
        # is also as far from the party as the night can make them walk.
        aim_route = route if index == 0 else []
        row = place(tiles, aim_route, keepout, origin, rng)
        if row is None:
            break
        row.id = f"r{index}"
        placed.append(row)
        keepout.append((row.tx + PLOT / 2.0, row.ty + PLOT / 2.0))
    return placed


def place(
    tiles: list[list[int]],
    route: list[tuple[float, float]],
    scenes: list[tuple[float, float]],
    origin: tuple[float, float],
    rng: random.Random,
) -> Rift | None:
    """Clear a plot, stamp its tiles, and return the platform standing in it.

    Mutates `tiles`. Returns None if the map has nowhere to put one, which is
    survivable — a forest without an extraction point is a forest you leave the
    way you came — and is why the caller treats the pad as optional.

    The clearances are RELAXED rather than absolute. A cramped map that cannot
    honour them should still get an extraction point somewhere imperfect: the
    isolation is what makes the structure read best, but having one at all is
    what makes the run work.

    THEY DO NOT ALL GIVE WAY AT THE SAME RATE, and the order is the ranking.
    Distance from the other scenes goes first — a pad a bit close to a cabin is
    merely less striking. Distance from spawn goes next. The MAP EDGE holds at
    full strength through three passes and only bends in the last two, because
    it is the only one of the three whose failure is not cosmetic: you fight at
    this place, and a wall the screen does not explain is worse than a
    structure that landed nearer a campsite than you would have liked.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    if width < PLOT + BORDER * 2 or height < PLOT + BORDER * 2:
        return None

    aim = route[-1] if route else None
    for scene_relax, spawn_relax, edge_relax in (
        (1.00, 1.00, 1.00),
        (0.70, 0.85, 1.00),
        (0.40, 0.65, 1.00),
        (0.15, 0.40, 0.75),
        (0.00, 0.00, 0.50),
    ):
        scene_clear = SCENE_CLEARANCE * scene_relax
        spawn_clear = SPAWN_CLEARANCE * spawn_relax
        # Never past the treeline, whatever happens: a pad with its back to the
        # forest is a compromise, a pad hanging off the map is broken.
        margin = max(BORDER, round(EDGE_MARGIN * edge_relax))
        for tx, ty in _candidates(width, height, aim, origin, rng, margin):
            if not _plot_open(tiles, tx, ty):
                continue
            cx = tx + PLOT / 2.0
            cy = ty + PLOT / 2.0
            if math.hypot(cx - origin[0], cy - origin[1]) < spawn_clear:
                continue
            if any(math.hypot(cx - sx, cy - sy) < scene_clear for sx, sy in scenes):
                continue
            # STAMP, THEN CHECK, THEN KEEP OR PUT IT BACK.
            #
            # Clearing the plot only ever ADDS reachable ground — but the solid
            # deck in the middle takes ten tiles away, and if the plot happens
            # to straddle a neck in the forest those ten were the bridge. The
            # far side is then unreachable and `build_forest` rightly refuses
            # the whole map. Rather than forbid narrow spots up front (hard to
            # measure, and it would reject good ones), the placement tries it
            # and rolls back if the map came out worse.
            before = [row[tx:tx + PLOT] for row in tiles[ty:ty + PLOT]]
            placed = _stamp(tiles, tx, ty, rng)
            floor = sum(row.count(FLOOR) for row in tiles)
            if count_reachable(tiles) == floor:
                return placed
            for oy in range(PLOT):
                tiles[ty + oy][tx:tx + PLOT] = before[oy]
    return None


def _candidates(
    width: int,
    height: int,
    aim: tuple[float, float] | None,
    origin: tuple[float, float],
    rng: random.Random,
    margin: int,
):
    """Plot corners to try, best first.

    Ordered by distance from the aim — the end of the story thread — so the
    extraction lands where the trail was already leading. With no thread it
    falls back to "as far from the spawn clearing as possible", which keeps the
    walk home long even on a map with nothing to say.
    """
    corners = [
        (tx, ty)
        for ty in range(margin, height - PLOT - margin)
        for tx in range(margin, width - PLOT - margin)
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
    # their last scene in the same place do not put the pad on the same tile.
    head = corners[:24]
    rng.shuffle(head)
    return head + corners[24:]


def _plot_open(tiles: list[list[int]], tx: int, ty: int) -> bool:
    """Whether a plot at this corner is a clearing rather than a thicket.

    Rejects any plot — or `MARGIN` tiles around it — that already contains a
    building or cover: those tiles belong to a scene, and dropping a cargo skid
    through somebody's cabin is the one placement bug that would be visible
    from across the map.
    """
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    margin_tiles = 0
    margin_open = 0
    for oy in range(-MARGIN, PLOT + MARGIN):
        for ox in range(-MARGIN, PLOT + MARGIN):
            x, y = tx + ox, ty + oy
            if not (0 <= x < width and 0 <= y < height):
                continue
            if tiles[y][x] in (PROP, LOW):
                return False
            if 0 <= ox < PLOT and 0 <= oy < PLOT:
                continue
            margin_tiles += 1
            if tiles[y][x] == FLOOR:
                margin_open += 1
    if margin_tiles and margin_open < margin_tiles * MIN_MARGIN_OPEN:
        return False

    open_tiles = 0
    for oy in range(PLOT):
        for ox in range(PLOT):
            if tiles[ty + oy][tx + ox] == FLOOR:
                open_tiles += 1
    if tiles[ty + PLOT // 2][tx + PLOT // 2] != FLOOR:
        return False
    return open_tiles >= PLOT * PLOT * MIN_OPEN


def _stamp(tiles: list[list[int]], tx: int, ty: int, rng: random.Random) -> Rift:
    """Clear the plot to floor, then put the structure's own tiles back.

    THE DECK IS `LOW`, NOT `PROP`. Solid — you cannot get on the platform, and
    that is deliberate: it is cargo space, and a party riding it out would be a
    whole second problem for nothing. But you can SEE and SHOOT over it, which
    a five-by-two block of sight-blocker in the middle of the one clearing the
    party fights in would take away. The console is `LOW` for the same reason:
    waist-high cover on the tile everyone is standing at.

    The drones and the torch claim NOTHING. A drone is knee-high and about to
    fly away, and a torch you can walk through is the same torch the exit
    corridor uses.
    """
    for oy in range(PLOT):
        for ox in range(PLOT):
            tiles[ty + oy][tx + ox] = FLOOR

    dx, dy, dw, dh = _DECK
    for oy in range(dh):
        for ox in range(dw):
            tiles[ty + dy + oy][tx + dx + ox] = LOW

    cx = int(math.floor(tx + _CONSOLE[0]))
    cy = int(math.floor(ty + _CONSOLE[1] - 1e-6))
    tiles[cy][cx] = LOW

    return Rift(
        tx=tx,
        ty=ty,
        x=(tx + _CENTRE[0]) * TILE_SIZE,
        y=(ty + _CENTRE[1]) * TILE_SIZE,
        deck_x=(tx + _PLATFORM[0]) * TILE_SIZE,
        deck_y=(ty + _PLATFORM[1]) * TILE_SIZE,
        console_x=(tx + _CONSOLE[0]) * TILE_SIZE,
        console_y=(ty + _CONSOLE[1]) * TILE_SIZE,
        torch_x=(tx + _TORCH[0]) * TILE_SIZE,
        torch_y=(ty + _TORCH[1]) * TILE_SIZE,
        drones=tuple(
            ((tx + ox) * TILE_SIZE, (ty + oy) * TILE_SIZE) for ox, oy in _DRONES
        ),
        # Where it goes when it goes. Rolled here so it is decided once, by the
        # map, and every client watching the same launch watches it leave in
        # the same direction.
        heading=rng.uniform(0.0, math.tau),
    )
