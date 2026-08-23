"""The extraction point: one or more per forest, scaled by the day, and the
only thing on a map that ANSWERS BACK.

WHAT IT IS
An abandoned cargo skid — an iron box open at the front, still half loaded with
crates nobody came back for. Four corner posts, a console, a torch that burns
from the moment the map is built. The aircraft are not part of this structure:
they come when it calls them. What is left when it goes is the hole it was
sitting in.

The name `rift` is what this module was called when the extraction point was a
tear in the world with stones around it. The wire, the config and twenty client
files still say `rift`, and renaming them buys nothing a line here cannot say.
The art it used to draw is still in `assets/processed/rift/` — this pad borrows
its CONSOLE and its TORCH, and nothing else.

THREE PRESSES, AND EACH ONE BUYS THE NEXT
    press    Power to the deck and GREEN on the four corner lamps: found,
             running, safe to use. Nothing is in the air and nothing has heard
             anything. What the party has bought is the right to load the thing.
    load     Catalog gold out of the pocket until the quota is settled, and
             then as much past it as they feel like risking.
    call     THE EXPENSIVE ONE. The lamps go RED, the pad starts sweeping a
             siren across a black forest, and `Room._siren` throws a map-wide
             noise every `SIREN_PULSE` for the whole thirteen seconds that
             follow. Four drones come in from one treeline, take a corner
             each, drop their lines, and lift. The party cannot leave and
             cannot take it back.

THE PICKUP IS THE ONLY THING IN THIS GAME THAT COSTS TIME
Everything else resolves in under a second. This one is a decision the party
has already made and now has to survive standing next to, which is the whole
reason it is thirteen seconds long and the whole reason the siren is loud.

ONE PAD AT A TIME, AND THE PLAYER SENDS IT
A night's pads are a queue, not a menu: `Room` refuses a console while another
platform is awake, so three pads is three separate walks. Each carries its own
quota (`pad_need`). Paying it does not call the pickup, and that separation is
what makes overfeeding possible at all: the window between "paid" and "called"
is time the party chooses to spend, and everything they load during it comes
back at the far end as one dense object (`Room._drop_excess`). A timer never
called a pickup and never will.

WHY THIS IS SERVER-SIDE AND WHY IT SHIPS COORDINATES
Same reason `scenery.py` is. Placement has to know which ground is open, it
makes tiles solid, and every client has to agree on where the thing is to the
pixel — so the server picks the spot, stamps the tiles, and ships absolute
world positions. The client never re-derives the arrangement. The `layout`
block in `assets/processed/platform/manifest.json` is the ART's copy of the
same offsets and `_LAYOUT` below mirrors it exactly; if one moves the other
has to.

WHERE IT GOES
THE FIRST ONE IS NEAR THE DOOR. A night opens with an empty bag, so a first
console two minutes' walk away is an objective the party cannot act on yet —
they were finding a machine with nothing to give it. It stands a clearing out
from the arrival mouth instead (`NEAR_SPAWN_CLEARANCE`), and the run works
OUTWARD from there.

The story thread is not lost, it moves down the queue. `scenery.Population.route`
is a walk from the spawn clearing outward through the scenes that landed,
ordered so the last stop is the landmark, and the SECOND pad takes `route[-1]`:
out along the trail, and back through it with your pockets full. Anything after
that goes as far from spawn as the clearances allow. A uniformly random tile
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
#: The skid is 5 tiles wide and its contact is THREE rows up from the plot's
#: own edge, which is what leaves standing room in front of it.
#:
#: IT USED TO BE TWO, AND THAT ROW IS THE WHOLE FIX. The console stood on the
#: row directly against the deck, so the tile a player walks to in order to
#: press the button was also the tile the platform occupied the far side of —
#: there was nowhere to STAND at the pad. The thing this structure is for is
#: emptying a bag into it, which means a player parked in front of it for
#: several seconds with drops landing around them; a doorway with no landing
#: is a place you get pushed out of. One empty row between the console and the
#: skid is that landing, and it costs nothing else: the plot is unchanged, the
#: console and the torch have not moved, and reach is measured to the console
#: (`Room._rift_in_reach`), not to the deck.
_PLATFORM = (PLOT / 2.0, 4.0)

#: The tiles the box actually SITS ON, as (x, y, w, h) from the plot corner.
#: These go solid — see `_stamp`. THE PLAYER MAY NOT GET ON THE PLATFORM: it is
#: cargo space, and a party standing on the deck when it lifts would be a whole
#: second physics problem for no gameplay.
_DECK = (1, 2, 5, 2)

#: How many corners the lift takes, and therefore how many aircraft answer the
#: call. THE DRONES ARE NOT PART OF THIS STRUCTURE and the server ships no
#: position for them: they arrive from off-map along `approach` when the pad
#: calls, take a corner each in the DIAGONAL order the art uses (front-left,
#: back-right, front-right, back-left) and are gone with the platform. Opposite
#: corners first, so a rig part-way through tying on holds a level load.
DRONES = 4

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
#: flown and the ground under it is walkable again. Moves with `_DECK` — it is
#: the deck's own middle, not a number about the plot.
_CENTRE = (PLOT / 2.0, 3.0)

#: Radius of the pad's own light once it is powered, in tiles.
#:
#: Bigger than a cabin lamp, smaller than the campfire. It has to light the pad
#: — you can see what is coming at you, which is the difference between a
#: beacon and a lamp — without washing the forest around it. `kind` 2 is
#: `scenery.BEACON`.
LIGHT_TILES = 4.0
LIGHT_KIND = 2

# --- the timeline ------------------------------------------------------------

#: The console answers before anything else does, and then the deck's lamps
#: come up GREEN. Without this beat the press and the light are the same
#: instant and the button reads as decoration rather than as a switch.
CONSOLE_LAG = 0.30
OPEN_AT = CONSOLE_LAG + 0.55

#: How long the platform waits if nothing loads it. INFINITE: the window closes
#: when a player calls for the pickup, not on a clock. `begin_collapse` walks
#: the SPENT path.
OPEN_TIME = math.inf

# --- the pour ------------------------------------------------------------------
#
# LOADING IS A PERFORMANCE, NOT A TRANSACTION. It used to be one press: the bag
# emptied, the meter jumped, and the single most important verb in the game
# resolved in the same frame as opening a barrel. What the party is actually
# doing is carrying a night's work up to a machine and giving it away, so they
# now WATCH themselves do it — the walk up to the skid, the pack off the back
# and turned over, the contents falling out of it one at a time and landing on
# the deck, the pack going back on.
#
# The items leave the pocket AS THEY LEAVE THE BAG, one per `POUR_BEAT`, which
# is the whole reason the server owns this clock: a client-side flourish over
# an inventory that emptied instantly is a bag that is visibly still full and
# already spent.
#
# THE PLAYER MAY WALK OUT OF IT AT ANY POINT. A movement key cancels, and
# everything already tipped stays in the pad. Standing still for three seconds
# in a dark forest has to be a choice that can be un-made.

#: How long the walk up to the mark is allowed to take before the pour starts
#: anyway. A ceiling, not a duration — the walk normally finishes early.
POUR_WALK_MAX = 0.80
#: The pack coming off the back and turning over.
POUR_LIFT = 0.42
#: One item out of the bag. Fast enough to feel like pouring rather than
#: placing, slow enough that the eye can still count them.
POUR_BEAT = 0.15
#: The pack going back on.
POUR_STOW = 0.40
#: Where the pour happens, in tiles in front of the deck's own contact row.
#: Close enough that the items are being tipped INTO the skid, far enough that
#: the body is not standing inside the sprite.
POUR_STAND = 0.85

# --- the pickup ----------------------------------------------------------------
#
# THIS IS THE SET PIECE OF THE NIGHT AND IT IS DELIBERATELY LONG.
#
# Every other interaction in this game resolves in under a second. This one
# takes thirteen, and the party cannot leave, because what it actually is is a
# decision they have already made and now have to survive: the lamps go from
# green to RED, the pad starts sweeping a siren across a black forest, and
# every creature on the map turns toward it (`Room._siren`). The drones are
# still two clearings away.
#
# The beats, in order, and none of them is interchangeable:
#
#   ALARM     Sirens, and nothing else. The aircraft have not even launched.
#             This is the beat that costs — a party that pressed the button
#             without clearing the clearing first finds out here.
#   INBOUND   Four drones come in from one bearing, staggered, and each takes
#             a corner. Staggered because four aircraft arriving on the same
#             frame is one sprite drawn four times.
#   DROP      Each pays out a line to its eye. It is only tied when the end
#             gets there, and the lift waits for the LAST one.
#   STRAIN    Rotors to maximum, lines taut, the skid rattling in its own hole
#             and not moving. The beat that says the thing is HEAVY.
#   BREAK     It comes free. The ground under it is uncovered, the deck's tiles
#             go walkable, and the burst fires.
#   CLIMB     Up and away along `heading`, accelerating, shrinking, gone.

#: Sirens alone, before anything is in the air.
LIFT_ALARM = 3.20
#: Between one drone leaving the treeline and the next.
DRONE_STAGGER = 0.55
#: One drone's flight from the edge of sight to its corner.
DRONE_INBOUND = 2.40
#: Paying the line out until the end reaches the eye.
DRONE_DROP = 1.00
#: Rotors to maximum against ground that will not let go.
LIFT_STRAIN = 1.10
#: Coming free.
LIFT_BREAK = 0.45
#: The flight out.
LIFT_CLIMB = 3.40

#: When each drone leaves the treeline, arrives, and finishes tying on.
def drone_departs(index: int) -> float:
    return LIFT_ALARM + index * DRONE_STAGGER


def drone_arrives(index: int) -> float:
    return drone_departs(index) + DRONE_INBOUND


def drone_tied(index: int) -> float:
    return drone_arrives(index) + DRONE_DROP


#: All four on, and the lift can start. Derived, never typed: adding a corner
#: re-times the whole sequence and the client reads the result through
#: `client_config`, so all three stay in step.
TIED_AT = drone_tied(DRONES - 1)
#: When the skid comes free, measured from the launch press.
BREAK_AT = TIED_AT + LIFT_STRAIN
#: The whole pickup. Named `COLLAPSE_TIME` because `Rift.step` and the client
#: both time the pad's end off one number and this is it.
COLLAPSE_TIME = BREAK_AT + LIFT_BREAK + LIFT_CLIMB

#: How often the siren throws a noise event while the pickup runs, and how far
#: it carries in tiles. THE RADIUS IS THE WHOLE POINT: a gunshot is a local
#: problem, this is a map-wide announcement, and the party has to feel that
#: they have just told everything in the forest exactly where they are.
SIREN_PULSE = 0.75
SIREN_TILES = 46.0

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
# exists to offer. Paying exactly what it asks is what turns the console into
# a call button. Keeping the bag going past that does
# not close anything — the platform takes everything, and what you overpaid
# comes back as one dense object you carry to the NEXT pad (`Room._drop_excess`).
# Overfeeding is therefore never a donation, it is moving value forward through
# a bag that has a slot count, which is the only reason it is worth doing.
#
# THERE ARE NO TIERS AND THE DRONES ARE NOT A METER. They were once: each
# overpayment step woke one more of them, so a saturated pad had four turning
# and an untouched one had a single machine. It read well and it made the quota
# feel optional — a rig with one drone on it looks like a rig that will fly, so
# there was no moment where the platform was visibly NOT READY. What the pad
# says now is simpler and harder: green means loading, red means the aircraft
# are coming, and the party chooses when to cross that line.


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
    #: The bearing the drones come in on, in radians. Rolled at placement
    #: rather than at the call so it rides on the map payload: every client has
    #: to agree about which treeline four aircraft appeared over, and a client
    #: that joined mid-pickup has to be able to place them.
    approach: float = 0.0
    #: Which way the loaded platform leaves, in radians. Set opposite the
    #: approach, so the flight reads as ONE PASS — in over that treeline, out
    #: over the far one — rather than as a round trip that turned around.
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
    #: Which siren pulse has already been thrown, as an index into the pickup's
    #: own clock. Server-only and NOT on the wire: it exists so `Room._siren`
    #: fires once per pulse rather than once per tick, and a rehydrate that
    #: resets it costs one extra noise nobody can distinguish from the rest.
    siren_pulse: int = -1
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
    #: Catalog value put into it. May go past `need` — the overshoot is the
    #: size of the core waiting at the far end.
    fed: int = 0
    #: How many items have been tipped onto this deck. Never decreases while
    #: the pad lives, and it rides the geometry payload because it is the index
    #: every client stacks the pile off — two players watching the same pour
    #: have to see the same crate land in the same place on the same deck.
    cargo: int = 0
    #: What the overpayment condensed into, banked when the launch starts and
    #: spent when it finishes. Zero once the drop has been placed, so a pad
    #: cannot pay out twice however the room ticks.
    excess: int = 0

    @property
    def ready(self) -> bool:
        """The quota is settled: the console is a CALL button now.

        Nothing about this is automatic. A paid pad sits there with green lamps
        for as long as the party wants — they can keep loading it, or walk off
        and clear the clearing first, or fight next to it. Pressing again is
        what brings the aircraft, and that press is the loudest thing anybody
        does on a night.
        """
        return self.state == OPEN and self.close_at is None and self.fed >= self.need

    @property
    def alarm(self) -> bool:
        """The pickup has been called: lamps red, siren sweeping, drones coming."""
        return self.close_at is not None and self.state != SPENT

    @property
    def lifted(self) -> bool:
        """The skid has broken ground. Its tiles are no longer anybody's wall."""
        return self.close_at is not None and self.elapsed >= self.close_at + BREAK_AT

    def feed(self, value: int) -> None:
        if value > 0:
            self.fed += value

    def press(self) -> None:
        """Wake the pad: power to the deck, green lamps, light on the clearing.

        NOTHING FLIES YET, and that restraint is the whole shape of the pad.
        The console answers, the corner lamps come up green and the ground
        around it is lit — which is everything the party needs to work here and
        none of what they need to leave. The aircraft are a separate decision
        and a much more expensive one.
        """
        self.state = CHARGING
        self.elapsed = 0.0

    def step(self, dt: float) -> bool:
        """Advance the sequence. True when the state changed this tick.

        One clock for the whole life of the thing: power-up, hold, the whole
        thirteen-second pickup and gone are all read off `elapsed`, so there is
        no separate timer to fall out of step and a client that joins at any
        point can be told where it is with one number.

        `ready` is watched here as well as the state string. The quota can be
        settled by a press (an event `Room` already reports) but it can also
        become the thing that matters on a tick where nothing was pressed at
        all, and a console that changed its mind without the row going dirty is
        a button the client draws wrong until something else happens.
        """
        if self.state in (DORMANT, SPENT):
            return False
        was_ready = self.ready
        self.elapsed += dt
        changed = self.ready != was_ready
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

        A player calling for the pickup is what ends a pad, not a timer. A
        dormant one just stays dead. A pad still powering up is jumped to open,
        so the sequence has a lit platform to run on rather than a half-played
        switch-on.

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
            "cargo": self.cargo,
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
            "approach": round(self.approach, 3),
            "heading": round(self.heading, 3),
            "lightTiles": LIGHT_TILES,
            "lightKind": LIGHT_KIND,
            **self.state_payload(),
        }

    def state_payload(self) -> dict:
        """The live half: what it is doing. Rides on the snapshot when dirty.

        There is nothing here about the aircraft. `closeAt` is the moment the
        pickup was called and every drone's whole flight — when it leaves the
        treeline, when it reaches its corner, when its line is tied — is that
        one number plus the constants in `client_config`. Shipping four flight
        plans at 6 Hz to describe something already fully determined would be
        the largest message in the game for no information at all.
        """
        row = {
            "id": self.id,
            "state": self.state,
            "t": round(self.elapsed, 2),
            "fed": self.fed,
            "need": self.need,
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
        approach=float(row.get("approach", 0.0)),
        heading=float(row.get("heading", 0.0)),
        id=str(row.get("id", "r0")),
        state=str(row.get("state", DORMANT)),
        elapsed=float(row.get("t", 0.0)),
        close_at=None if close is None else float(close),
        freed=bool(row.get("freed", False)),
        need=int(row.get("need", 0)),
        fed=int(row.get("fed", 0)),
        excess=int(row.get("excess", 0)),
        cargo=int(row.get("cargo", 0)),
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

    THE MAP IS SIZED OFF THIS (`mapgen.size_for_pads`), so the count is the
    day's difficulty curve AND the day's map size: one pad on a third of the
    ground, three on the whole forest.
    """
    if day <= 2:
        return 1
    if day <= 4:
        return 2
    return 3


#: Catalog value one night's quota grows by per day, and the surcharge each
#: EXTRA pad adds.
#:
#: PINNED TO WHAT A MAP ACTUALLY HOLDS, not to a feeling. Sampled over forty
#: seeds, a forest carries a MEDIAN of about 910 points of findable value —
#: roughly 340 scattered on the ground by `loot.scatter` across sixteen or so
#: scenes plus the shrine, and about 600 more inside the forty-odd objects
#: `scenery.py` stands up. The spread is wide on purpose (a quarter of maps
#: come in under 640, a quarter over 1170), so the quota is set against the
#: LOW quarter rather than the median: a bad roll should make a night hard,
#: never impossible. The quota is a SHARE OF THE MAP:
#:
#:     day 1     40   one pad. Under five per cent. A first night has to be
#:                    winnable by a party with a knife and no idea where
#:                    anything is, and its whole take is the shop budget that
#:                    buys the first gun (`store.price_of`: a Glock is 46).
#:     day 3    144   two pads, 72 each. About a sixth of the map.
#:     day 5    248   three pads, 83 each. A bit over a quarter.
#:     day 10   448   half of everything out there, which is the night the
#:                    walk stops being optional and the shrine stops being
#:                    a question.
#:
#: The per-pad surcharge is smaller than a day's step on purpose: a map that
#: found room for three platforms is a longer night, not a harder one, and the
#: extra should be paid for in walking rather than in loot.
# --- what a night costs ------------------------------------------------------
#
# THE OLD FORMULA WAS `40 * day + 24 * (pads - 1)` AND IT WAS WRONG AT BOTH
# ENDS, in opposite directions, for the same reason: it was a straight line
# with no idea what was actually out there.
#
#   Night 1 asked 40 against a forest holding about 500. Seven per cent. At an
#   expected 34 gold an item that is 1.2 OBJECTS — under a quarter of one
#   backpack — so the thing the whole night is supposedly about was cleared by
#   accident on the way to the first platform, and no exploration decision was
#   ever forced.
#
#   Night 24 asked 1008 against a forest still holding about 1000, because the
#   bill kept climbing linearly for ever while the MAP STOPPED GROWING AT DAY
#   FIVE (`count_for_day` caps at three pads, and `mapgen.size_for_pads` with
#   it). Somewhere around night twenty the quota crosses what a bad seed can
#   even produce and the night becomes unwinnable through no decision anybody
#   made.
#
# So the bill is a SHARE OF WHAT IS OUT THERE, and both halves of that are
# derived rather than picked: the supply from the pad count (which is what
# sizes the map and scales the scene budget — see `mapgen.populate_forest`),
# and the share from the day, capped where the map stops growing.

#: The LOW QUARTER of a night's findable value, in catalog gold, as a function
#: of how many platforms landed. Measured over forty generated forests per pad
#: count and fitted; `tests/test_quota.py` re-measures and fails if the fit has
#: drifted more than a tenth, which is the only way this stays honest when
#: somebody edits `loot.SCENE_COUNTS` or `crates.TYPES`.
#:
#: THE LOW QUARTER AND NOT THE MEDIAN, deliberately and unchanged from the
#: original design: half the nights should have comfortable margin and a bad
#: roll should make a night HARD rather than impossible.
#:
#: IT HAS A CONSTANT TERM because the two LANDMARKS are one per map whatever
#: the map's size — a one-pad forest still gets a shrine or a den, and that is
#: a big share of a small night's value.
#: RE-FITTED WHEN MEDICINE LEFT THE ECONOMY. `first_aid` and `morphine` were
#: ordinary ground loot worth 30 and 58 until they became medical-cell items
#: with `value=0` (see `medical.py`), and taking two uncommon-to-rare rows out
#: of the findable pile dropped what a real forest holds by about a tenth at
#: every pad count. `test_quota.py` caught it, which is the entire reason that
#: file re-measures instead of trusting a number written down once.
SUPPLY_BASE = 210.0
SUPPLY_PER_PAD = 243.0

#: What share of that low quarter night one asks for. A third: enough that the
#: quota is roughly one full backpack and the party has to actually look for
#: it, nowhere near enough that a first night is a sweep of the whole map.
NIGHT_SHARE_BASE = 0.30
#: What each night adds. Small — the DAY's difficulty is supposed to arrive as
#: population and as a longer walk, not as a bigger bill.
NIGHT_SHARE_PER_DAY = 0.025
#: Where it stops, and this cap is the important half of the whole rewrite.
#:
#: The map stops growing at day five. A bill that kept climbing past that point
#: is a difficulty curve made of the same forest and a bigger number, which
#: ends in a night nobody can finish. Past the cap the nights get harder the
#: way they should — more bodies, arriving faster, for longer
#: (`config.ENEMY_NIGHT_RAMP`) — and the quota holds still.
NIGHT_SHARE_MAX = 0.55


def night_supply(count: int) -> float:
    """The low quarter of what a forest with `count` pads has lying in it."""
    return SUPPLY_BASE + SUPPLY_PER_PAD * max(1, count)


def night_share(day: int) -> float:
    """What fraction of that the party is asked to load."""
    return min(
        NIGHT_SHARE_MAX,
        NIGHT_SHARE_BASE + NIGHT_SHARE_PER_DAY * (max(1, day) - 1),
    )


def night_need(day: int, count: int) -> int:
    """Catalog value the party has to load across the whole night.

    A share of what is actually out there — see the banner above. Rounded to
    the nearest five, because a quota is a number a player reads off a console
    in the dark and `413` reads as noise where `415` reads as a price.
    """
    raw = night_supply(count) * night_share(day)
    return max(1, int(round(raw / 5.0)) * 5)


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

#: THE FIRST PAD IS NEAR THE DOOR, AND THAT IS A CHANGE OF SHAPE.
#:
#: It used to sit at `route[-1]`, the far end of the story thread, so the night
#: opened with a long walk to a console nobody had seen yet. What that actually
#: bought was a first objective the party could not act on for two minutes: the
#: bag is empty on arrival, so the walk out was spent finding a machine that had
#: nothing to be given. The first platform stands a clearing away from the
#: arrival mouth instead — found almost immediately, loaded a little, and then
#: the party works OUTWARD from it. The trail's payoff is not lost, it moves
#: down the queue: the SECOND pad is the one that takes `route[-1]`.
#:
#: The clearance is a floor, not a target. `_candidates` sorts nearest-first
#: around the mouth, so the pad lands just outside this ring — far enough that
#: the arrival corridor, its avoid radius (`ENTRANCE_MOUTH_TILES + 6`) and the
#: pad's own plot do not overlap, near enough that it is the first structure
#: the party walks into.
NEAR_SPAWN_CLEARANCE = 12.0


def place_many(
    tiles: list[list[int]],
    route: list[tuple[float, float]],
    scenes: list[tuple[float, float]],
    origin: tuple[float, float],
    rng: random.Random,
    count: int,
) -> list[Rift]:
    """Place up to `count` extraction points. The first stands a clearing away
    from the ARRIVAL MOUTH (`NEAR_SPAWN_CLEARANCE`); the second follows the
    story thread to its far end; the rest go as far from spawn and from each
    other as the clearances allow. Fewer than asked is survivable — the quest
    need is however many actually landed.
    """
    want = max(0, count)
    if want == 0:
        return []
    placed: list[Rift] = []
    keepout = list(scenes)
    for index in range(want):
        # THE QUEUE IS ORDERED BY DISTANCE FROM THE DOOR, and the first stop is
        # the nearest one. The SECOND pad is the end of the trail — the thread
        # `scenery.Population.route` was strung for still pays off, one console
        # later. Anything after that has no thread left to honour and falls back
        # to "as far from spawn as possible", which is also as far from the
        # party as the night can make them walk.
        if index == 0:
            row = place(
                tiles, [], keepout, origin, rng,
                aim=origin,
                spawn_clearance=NEAR_SPAWN_CLEARANCE,
            )
        else:
            row = place(tiles, route if index == 1 else [], keepout, origin, rng)
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
    aim: tuple[float, float] | None = None,
    spawn_clearance: float = SPAWN_CLEARANCE,
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

    if aim is None:
        aim = route[-1] if route else None
    for scene_relax, spawn_relax, edge_relax in (
        (1.00, 1.00, 1.00),
        (0.70, 0.85, 1.00),
        (0.40, 0.65, 1.00),
        (0.15, 0.40, 0.75),
        (0.00, 0.00, 0.50),
    ):
        scene_clear = SCENE_CLEARANCE * scene_relax
        spawn_clear = spawn_clearance * spawn_relax
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

    The torch claims NOTHING — a torch you can walk through is the same torch
    the exit corridor uses. Neither do the drones, and they could not: they are
    not on this map until the pad calls them.
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

    approach = rng.uniform(0.0, math.tau)
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
        # Which treeline the aircraft come over, and which one they leave over.
        # Rolled HERE so the whole thing is decided once, by the map, and every
        # client watching the same pickup watches the same four machines arrive
        # from the same direction.
        #
        # The departure is the approach CONTINUED, not reversed: they fly in,
        # take the load, and carry on the way they were already going. A round
        # trip out of the same trees they came from reads as a delivery van.
        approach=approach,
        heading=approach + math.pi + rng.uniform(-0.45, 0.45),
    )
