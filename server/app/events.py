"""The night's script: things that HAPPEN, on top of the slope that builds.

WHY THIS EXISTS AT ALL
======================
`EnemyDirector` makes the forest fill up as the night goes on, and it is the
right pressure — but a slope has no moments in it. Nobody has ever noticed a
population ceiling move. What a player remembers, and what makes one night
different from the last, is a thing that ARRIVED: the wave out of the treeline,
the lights going out, the crate that came down two clearings away.

That is what this module schedules. It owns no mechanics of its own. Every
effect here is a call into machinery `Room` already had for some other reason —
the horde's spawn geometry, the blackout's lantern rule, the siren's noise, the
loot scatter. An event is a ROW that says when, how often, and which of those
doors to open. If an event in here needs new mechanics, the mechanics belong in
the subsystem that owns them and this file calls them.

THREE WAYS A THING CAN HAPPEN, AND THAT IS DELIBERATELY ALL THREE
=================================================================
Every event any of us sketched for this game fell into one of three shapes, so
those are the triggers and there is no fourth:

    TIME    it happens at a point in the night. The player can learn it and
            plan around it, which is the whole value — a scheduled danger is
            the only kind you can be early for.
    CHANCE  it is rolled, repeatedly, with the odds climbing. Nobody can plan
            around it, so it is what stops a learned night becoming a script.
    ACTION  the world answers something the party DID. This is the only one
            that makes the player the cause, and it is the strongest of the
            three for exactly that reason.

Two of the four rows below share `CHANCE`, which is the point: a trigger is a
mechanism, not a category, and the second event to use one must cost nothing.

WHAT ADDING AN EVENT COSTS
==========================
A row in `EVENTS` and an effect function above it — and, because this server
holds no interface copy, one line of text on the client keyed to the same
string (`client/src/game/events.ts`). That is the honest answer; the horde
already worked that way before this file existed and it is the same trade the
whole HUD makes.

THE GUARDS ARE HERE AND NOT ON THE ROWS
=======================================
Nothing fires during a pickup, during the run for the exit, during an arrival
or a departure, in the shop, or in the arena. Every one of those is a beat the
game has already committed the player to, and an event landing inside one is
not tension — it is two things asking for the same attention with no way to
answer either.

They are checked in `EventDirector.update` rather than declared per row so that
a new event cannot forget one. A row that genuinely wants to fire during
extraction would need to say so explicitly, and none does.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .config import (
    EVENT_AIRDROP_CHANCE,
    EVENT_AIRDROP_CHANCE_PER_ROLL,
    EVENT_AIRDROP_INTERVAL,
    EVENT_AIRDROP_ITEMS,
    EVENT_AIRDROP_MIN_DAY,
    EVENT_AIRDROP_TILES,
    EVENT_BLOOD_TILES,
    EVENT_DARK_AT,
    EVENT_DARK_MIN_DAY,
    EVENT_DARK_SECONDS,
    EVENT_GRACE,
    HORDE_CHANCE,
    HORDE_CHANCE_PER_ROLL,
    HORDE_INTERVAL,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .room import Room

# --- the three shapes --------------------------------------------------------

#: Once, at a fixed point into the night. Learnable, and meant to be.
TRIGGER_TIME = "time"
#: Rolled every `interval`, at odds that climb with the number of rolls. The
#: same shape the horde has always had — see `EventDef.chance_per_roll` for why
#: it climbs rather than sitting flat.
TRIGGER_CHANCE = "chance"
#: The world answering something the party did. `EventDirector.report` is how
#: `Room` says it happened.
TRIGGER_ACTION = "action"


@dataclass(frozen=True)
class EventDef:
    """One thing that can happen, and the rules about when.

    A row is data. The only code on it is `effect`, and an effect may do
    nothing but call `Room` — see the module header.
    """

    key: str
    trigger: str
    #: What it does, and what the wire should say about it.
    #:
    #: `None` means IT DID NOT HAPPEN — no spot on the map, nobody left
    #: standing, a wave already in the air. That must not spend the cooldown or
    #: the per-night allowance, because a rare event silently consumed by a
    #: firing the player never saw is the hardest kind of bug to see from
    #: inside the game. Every one of those comes from an effect that swallowed
    #: its own failure.
    #:
    #: A DICT means it happened, and whatever is in it rides the event's wire
    #: row. Empty is the common case — most events are just "this happened".
    #: `{"x", "y"}` is for the ones with a PLACE, which is what lets the client
    #: point a cue or push a beacon without this file knowing either exists.
    effect: Callable[["Room"], dict | None]

    #: TRIGGER_TIME: seconds into the night, measured from the same clock the
    #: population ramp uses.
    at: float = 0.0

    #: TRIGGER_CHANCE: seconds between rolls, and the odds on each.
    interval: float = 0.0
    chance: float = 0.0
    #: How much each roll adds to the odds. IT CLIMBS ON PURPOSE. A flat chance
    #: per roll is memoryless, so a party can have a twenty-minute night with
    #: nothing in it, which is the one outcome this whole file exists to
    #: prevent. Climbing makes "nothing yet" into "soon", which is a different
    #: and much better feeling to sit in.
    chance_per_roll: float = 0.0

    #: TRIGGER_ACTION: the name `Room` reports.
    action: str = ""

    #: Not before this night. The only difficulty gate on a row, and it is for
    #: events that would be unreadable to somebody who has not learned the game
    #: yet — never for events that are merely strong.
    min_day: int = 1
    #: How many times this may fire in one night. 0 is unlimited.
    max_per_night: int = 0
    #: Seconds before this event may fire again after it has.
    cooldown: float = 0.0


# --- the effects -------------------------------------------------------------
#
# Each is a door into machinery that already exists. They are written as free
# functions rather than methods so that a row is readable in one screen: the
# name of the thing, then exactly what it opens.


def _horde(room: "Room") -> dict | None:
    """A wave, from one bearing, announced before it arrives.

    The whole mechanic lives in `Room.send_horde` — the telegraph, the arc, the
    noise that wakes the woods on the way in. This is the schedule for it, and
    moving that schedule here is what made the horde stop being a special case
    hidden inside the population director.
    """
    return room.send_horde()


def _dark(room: "Room") -> dict | None:
    """The lights go out, everywhere, for a while.

    IT TAKES AWAY THE ONE THING THE PLAYER CHOSE. The lantern is already the
    game's sharpest trade — see it, or be seen — and every other pressure in
    this file adds something to the map. This one subtracts, and what it
    subtracts is a decision the player had been making for themselves all
    night. That asymmetry is why it is on the TIME trigger: taking away the
    lamp at random would be a punishment, and taking it away at a moment the
    party can learn, and be somewhere sensible for, is a plan.

    It reuses the extraction blackout's rule exactly (`Room.queue_input` drops
    `lantern` while the dark is on), so there is no second way for a lamp to be
    off and no chance of the two disagreeing.
    """
    return room.begin_dark(EVENT_DARK_SECONDS)


def _airdrop(room: "Room") -> dict | None:
    """Supplies come down somewhere else.

    THE ONLY EVENT IN THIS FILE THAT IS AN OPPORTUNITY, and it is here to keep
    the others honest. If every scheduled thing is a threat, the correct answer
    to "an event fired" is always the same — leave — and a night with one
    answer is not a night with decisions in it. This one asks the opposite
    question, at the worst possible time, which is what makes it interesting:
    the crate is across the map, the forest is fuller than it was an hour ago,
    and the party has a bag that is already worth something.

    It lands AWAY from the party on purpose. A crate at your feet is a reward;
    a crate two clearings away is a decision, and the walk is the whole event.

    A beacon marks it, because an opportunity nobody can find is a threat with
    extra steps — the light is what makes the trade legible from where they are
    standing rather than something they have to be told about.
    """
    return room.drop_supplies(EVENT_AIRDROP_ITEMS, EVENT_AIRDROP_TILES)


def _blood(room: "Room") -> dict | None:
    """A body went down, and the forest noticed.

    THE ONE THAT MAKES THE PLAYER THE CAUSE. Everything else in here happens
    TO a party; this happens BECAUSE of one, and that is worth more than its
    mechanical weight. A run where the woods turn toward your friend the
    moment he falls teaches a lesson about spacing that no tutorial can.

    It matters most under permadeath, which is what earns it a place. Since
    T-01 a downed body is not a respawn timer, it is a teammate who has to be
    reached — so making the rescue harder is making the game's most important
    decision harder, at exactly the moment the party is deciding it.

    It is a NOISE and not a hunt, and the difference is the design. `ai.hear`
    with no source turns heads and raises awareness without telling anything
    where the party is standing — so the woods stir toward the fall rather
    than every creature on the map committing to the survivors. A blanket
    `hunt_all` here would make one player going down equivalent to pressing
    the extraction siren, which is a far bigger event than it should be.
    """
    return room.stir_at_downed(EVENT_BLOOD_TILES)


# --- the catalog -------------------------------------------------------------
#
# APPEND-ONLY IS NOT REQUIRED HERE and that is worth saying, because most
# tables in this repository are. Nothing indexes an event by position: the wire
# carries the KEY, the client looks its copy up by the same string, and the
# director keys its own bookkeeping off it too. Rows may be reordered or
# removed freely; a key may not be reused for a different thing.

EVENTS: tuple[EventDef, ...] = (
    EventDef(
        key="horde",
        trigger=TRIGGER_CHANCE,
        effect=_horde,
        # ITS OWN CONSTANTS, NOT NEW ONES. The horde was built and tuned
        # before this director existed and it is already balanced against the
        # population ramp; re-deriving its numbers here would be a second
        # opinion about the same thing, and the two would drift the first time
        # anybody touched a wave.
        interval=HORDE_INTERVAL,
        chance=HORDE_CHANCE,
        chance_per_roll=HORDE_CHANCE_PER_ROLL,
        # No allowance and a cooldown just under the roll interval: the horde
        # IS the night's texture and on a long one it should keep coming. What
        # stops it becoming a slideshow is `ENEMY_HARD_CAP`, which is a tick
        # budget, not a counter here.
        cooldown=HORDE_INTERVAL * 0.8,
    ),
    EventDef(
        key="dark",
        trigger=TRIGGER_TIME,
        effect=_dark,
        at=EVENT_DARK_AT,
        min_day=EVENT_DARK_MIN_DAY,
        # ONCE A NIGHT. Twice would make it weather rather than an event, and
        # the whole value of the TIME trigger is that the player can be
        # somewhere sensible for it — which is only true if there is one.
        max_per_night=1,
    ),
    EventDef(
        key="airdrop",
        trigger=TRIGGER_CHANCE,
        effect=_airdrop,
        interval=EVENT_AIRDROP_INTERVAL,
        chance=EVENT_AIRDROP_CHANCE,
        chance_per_roll=EVENT_AIRDROP_CHANCE_PER_ROLL,
        min_day=EVENT_AIRDROP_MIN_DAY,
        # Twice at most. A third crate turns the night into a supply run and
        # the quota stops being the reason anybody is out here.
        max_per_night=2,
        cooldown=90.0,
    ),
    EventDef(
        key="blood",
        trigger=TRIGGER_ACTION,
        effect=_blood,
        action="downed",
        # A cooldown rather than an allowance. A party losing two people in
        # ten seconds is already in the worst trouble the game has; stirring
        # the woods twice for it would be piling on rather than responding.
        cooldown=25.0,
    ),
)

BY_KEY: dict[str, EventDef] = {row.key: row for row in EVENTS}


# --- the director ------------------------------------------------------------


@dataclass
class _State:
    """Per-event bookkeeping for one night. Reset with the director."""

    fired: int = 0
    #: Seconds of cooldown left, or 0.
    cooling: float = 0.0
    #: TRIGGER_CHANCE: seconds to the next roll, and how many have happened.
    next_roll: float = 0.0
    rolls: int = 0
    #: TRIGGER_TIME: whether the scheduled moment has been passed.
    done: bool = False


class EventDirector:
    """Runs the catalog against one night on one map.

    ONE PER MAP AND NOT ONE PER RUN, which is what makes "this night" mean
    anything: every clock in here restarts when the party walks through an
    entrance, so a night is a fresh script rather than a continuation. `Room`
    builds a new one in `_swap_map` for exactly the same reason it builds a new
    `EnemyDirector` there.
    """

    def __init__(self, day: int) -> None:
        self.day = max(1, day)
        #: Seconds on this map. The same clock `EnemyDirector` ramps on, kept
        #: separately rather than read off it so the two systems are not
        #: coupled through a field neither of them owns.
        self.elapsed = 0.0
        self.state: dict[str, _State] = {}
        for row in EVENTS:
            st = _State()
            if row.trigger == TRIGGER_CHANCE:
                # THE GRACE IS ON THE FIRST ROLL, not on the clock. A party
                # that has just walked into a dark forest gets the beat they
                # were promised before it starts happening at them — the same
                # argument, and the same constant, as the population ramp's.
                st.next_roll = EVENT_GRACE + row.interval
            self.state[row.key] = st
        #: Rows that fired this tick, for the wire. `Room` drains it.
        self.fired: list[dict] = []

    # -- the gate --------------------------------------------------------

    def _quiet(self, room: "Room") -> bool:
        """Is the night in a beat that must not be interrupted?

        Every one of these is a sequence the game has already committed the
        player to. See the module header for why they live here rather than
        on the rows.
        """
        if room.sirening or room.blackout:
            return True
        if room.departing or room.arriving:
            return True
        if not room.zone.hostile:
            return True
        # The arena is a conversation between a party and one body. Nothing
        # else is invited — the same rule `step_enemies` applies to the
        # population director, for the same reason.
        from . import zones

        if room.zone.kind == zones.KIND_ARENA:
            return True
        return False

    def _allowed(self, row: EventDef, st: _State) -> bool:
        if self.day < row.min_day:
            return False
        if row.max_per_night and st.fired >= row.max_per_night:
            return False
        return st.cooling <= 0.0

    def _fire(self, row: EventDef, st: _State, room: "Room") -> None:
        """Run an effect and, only if it actually happened, spend the budget.

        An effect that returns None costs NOTHING — no cooldown, no allowance,
        no wire row. That is what lets an effect refuse honestly (no room on
        the map, nobody left standing) instead of having to pretend, and it
        means a rare event cannot be silently consumed by a firing the player
        never saw.
        """
        extra = row.effect(room)
        if extra is None:
            return
        st.fired += 1
        st.cooling = row.cooldown
        self.fired.append({"k": row.key, **extra})

    # -- the clock -------------------------------------------------------

    def update(self, dt: float, room: "Room") -> None:
        """One tick. Called from `Room.step` after the night's own systems.

        THE COOLDOWNS RUN EVEN WHILE THE GATE IS SHUT, and the clock does not.
        Those are opposite answers to the same question and both are
        deliberate: a cooldown is "that just happened, let it breathe", which
        stays true while the party is running for the exit — but the night's
        elapsed time is what the TIME trigger and the climbing odds are
        measured against, and letting it run through a two-minute extraction
        would mean a party that came home to a fresh map arrived into an event
        that had been building while nothing could happen.
        """
        for st in self.state.values():
            if st.cooling > 0.0:
                st.cooling = max(0.0, st.cooling - dt)

        if self._quiet(room):
            return
        self.elapsed += dt

        for row in EVENTS:
            st = self.state[row.key]
            if row.trigger == TRIGGER_TIME:
                if st.done or self.elapsed < row.at:
                    continue
                # Marked done whether or not the effect took. A scheduled
                # moment is a MOMENT: if the party was somewhere it could not
                # land, it has passed, and holding it pending would drop it on
                # them the instant they came back — which is the opposite of
                # the learnable thing this trigger exists to be.
                st.done = True
                if self._allowed(row, st):
                    self._fire(row, st, room)
            elif row.trigger == TRIGGER_CHANCE:
                st.next_roll -= dt
                if st.next_roll > 0.0:
                    continue
                st.next_roll = row.interval
                if not self._allowed(row, st):
                    continue
                odds = min(1.0, row.chance + row.chance_per_roll * st.rolls)
                st.rolls += 1
                if random.random() <= odds:
                    self._fire(row, st, room)
            # TRIGGER_ACTION rows do nothing here; they wait on `report`.

    def report(self, action: str, room: "Room") -> None:
        """`Room` says something happened. Fire whatever answers it.

        Deliberately a STRING and not a method per action: the whole point of
        the action trigger is that the room announces what it did without
        knowing whether anything is listening. A room that called
        `director.on_downed()` would be a room that knows the catalog.
        """
        if self._quiet(room):
            return
        for row in EVENTS:
            if row.trigger != TRIGGER_ACTION or row.action != action:
                continue
            st = self.state[row.key]
            if self._allowed(row, st):
                self._fire(row, st, room)

    def drain(self) -> list[dict]:
        out = self.fired
        self.fired = []
        return out
