"""The night's script: three ways a thing can happen, and one gate over all of them.

Run:  python tests/test_events.py   (from server/)

`EnemyDirector` is a slope and a slope has no moments in it — nobody has ever
noticed a population ceiling move. `events.py` is what puts moments on it, and
almost everything that can go wrong with a scheduler is invisible from inside
the game:

  * A TRIGGER THAT NEVER FIRES looks exactly like a trigger whose odds are low,
    and on a permanent run nobody plays enough nights to tell the difference.
    All three shapes are driven here with nobody watching.
  * AN EFFECT THAT SWALLOWED ITS OWN FAILURE spends a rare event's whole
    per-night allowance on nothing. The player sees a night with no crate in
    it and has no way to know one was "sent" into a wall.
  * THE GATE IS THE WHOLE SAFETY ARGUMENT. Nothing may fire during a pickup,
    the run for the exit, an arrival, a departure, in the shop or in the arena
    — every one of those is a beat the game has already committed the player
    to. It is checked in the director rather than per row precisely so a new
    event cannot forget it, and this is what proves it cannot.
  * "ADDING AN EVENT IS A DATA ROW" IS A CLAIM, and claims rot. It is asserted
    here against a row built in the test itself, so the day it stops being
    true is the day this fails rather than the day somebody tries it.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import events, mapgen, protocol, zones  # noqa: E402
from app.config import DT, EVENT_DARK_AT, EVENT_DARK_SECONDS  # noqa: E402
from app.room import Room  # noqa: E402

# SEEDED, because this file drives CHANCE triggers and a scheduler test must
# not be a dice test. What is under test is that rolls HAPPEN on their clock,
# never what they came up — an unseeded run would fail this file a few times a
# hundred for reasons that say nothing about the code.
random.seed(20260823)

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    async def send_text(self, text: str) -> None:
        pass


def forest_room(players: int = 1, day: int = 3) -> tuple[Room, list[str]]:
    room = Room(code="EVT")
    room.phase = protocol.PHASE_PLAYING
    ids = [room.add_player(Socket(), f"P{i}").id for i in range(players)]
    asyncio.run(room.embark())
    room.arriving = False
    # The forest is only allowed to act once the entrance is gone.
    room.gate = None
    room.day = day
    room.events = events.EventDirector(day)
    return room, ids


def run(room: Room, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        room.events.update(DT, room)


# --- the catalog is well formed ---------------------------------------------

seen: set[str] = set()
for row in events.EVENTS:
    check(f"{row.key} has a unique key", row.key not in seen)
    seen.add(row.key)
    check(
        f"{row.key} has a known trigger",
        row.trigger in (events.TRIGGER_TIME, events.TRIGGER_CHANCE, events.TRIGGER_ACTION),
    )
    if row.trigger == events.TRIGGER_CHANCE:
        check(f"{row.key} rolls on a real interval", row.interval > 0.0)
        check(f"{row.key} has odds worth rolling", row.chance > 0.0)
    if row.trigger == events.TRIGGER_TIME:
        check(f"{row.key} has a moment", row.at > 0.0)
        # A TIME row without an allowance would re-fire every tick after its
        # moment, because `elapsed >= at` stays true for the rest of the night.
        # `_State.done` is what actually stops that; this pins the intent.
        check(f"{row.key} fires a bounded number of times", row.max_per_night > 0)
    if row.trigger == events.TRIGGER_ACTION:
        check(f"{row.key} names an action", bool(row.action))

# ALL THREE SHAPES ARE IN USE. A trigger nobody uses is a trigger nobody has
# ever run, and the first event to try it would be the one that finds out.
kinds = {row.trigger for row in events.EVENTS}
check("all three triggers are exercised by the catalog", len(kinds) == 3)
# And at least one is used TWICE, which is the real generalisation test: a
# trigger is a mechanism, not a category, and the second user must cost nothing.
counts = {k: sum(1 for r in events.EVENTS if r.trigger == k) for k in kinds}
check("some trigger is used by more than one row", max(counts.values()) >= 2)


# --- TIME: it happens when it says it does ----------------------------------

room, _ids = forest_room(day=9)
# Just short of the moment.
run(room, EVENT_DARK_AT - 5.0)
check("before its moment, the dark has not fallen", room.dark_left == 0.0)

run(room, 10.0)
check("the dark falls at its moment", room.dark_left > 0.0)
check("and it says so on the wire", any(r["k"] == "dark" for r in room.events.drain()))

# THE LAMPS ARE ACTUALLY OFF, through the same branch the extraction blackout
# uses. This is the half that matters: a timer that ran while lanterns kept
# working would be an event with no mechanic in it.
pid = _ids[0]
room.queue_input(pid, {"sequence": 900, "lantern": True})
check(
    "a lantern cannot be lit while the dark is on",
    not room.players[pid].inputs[-1].lantern,
)

# ONCE A NIGHT. `_State.done` rather than the clock, because `elapsed >= at`
# stays true for the rest of the night.
room.dark_left = 0.0
run(room, 120.0)
check("the dark does not fall twice in one night", room.dark_left == 0.0)

# ...and it LIFTS, on both edges, or a client is left predicting a lamp that
# cannot come on.
room2, ids2 = forest_room(day=9)
run(room2, EVENT_DARK_AT + 1.0)
check("the dark is running", room2.dark_left > 0.0)
for _ in range(int((EVENT_DARK_SECONDS + 1.0) / DT)):
    room2._step_dark(DT)
check("the dark lifts by itself", room2.dark_left == 0.0)
check("and the lift is marked for the wire", room2._dark_dirty)
room2.queue_input(ids2[0], {"sequence": 901, "lantern": True})
check("the lantern works again afterwards", room2.players[ids2[0]].inputs[-1].lantern)

# NOT ON NIGHT ONE. The only event that changes a rule the player has been
# relying on, and doing that before they have relied on it is noise.
room3, _ = forest_room(day=1)
run(room3, EVENT_DARK_AT + 30.0)
check("the dark is gated off night one", room3.dark_left == 0.0)


# --- ACTION: the world answers something the party did ----------------------

room, ids = forest_room(players=2, day=3)
room.noises.clear()
before = len(room.noises)
# Nobody is down: the effect must REFUSE, and refusing must cost nothing.
room.events.report("downed", room)
check("a stir with nobody down does not happen", len(room.noises) == before)
check(
    "and it spent no allowance",
    room.events.state["blood"].fired == 0 and room.events.state["blood"].cooling == 0.0,
)

# Now put one down for real, through the one door damage comes in.
victim = room.players[ids[1]]
room.damage_player(victim, 10_000, None)
check("the body is down", victim.downed)
check("the woods heard it", len(room.noises) > before)
check("the row reached the wire", any(r["k"] == "blood" for r in room.events.drain()))

# THE COOLDOWN IS REAL. A party losing two people in ten seconds is already in
# the worst trouble the game has; stirring twice for it is piling on.
room.noises.clear()
room.events.report("downed", room)
check("a second fall inside the cooldown does not stir again", not room.noises)

# An action nobody answers is not an error — the room announces what it did
# without knowing whether anything is listening.
room.events.report("nothing-answers-this", room)
check("an unanswered action is harmless", not room.noises)


# --- CHANCE: it is rolled, and the odds climb -------------------------------

room, _ = forest_room(day=6)
# Driven long enough that a working chance trigger is overwhelmingly likely to
# have landed at least once. This is a scheduler test, not a dice test: what is
# under test is that rolls HAPPEN, not what they came up.
run(room, 900.0)
fired = [r["k"] for r in room.events.drain()]
check("a long night contains at least one horde", "horde" in fired)
check("a long night contains at least one airdrop", "airdrop" in fired)

# THE ALLOWANCE HOLDS. A third crate turns the night into a supply run.
airdrop_row = events.BY_KEY["airdrop"]
check(
    "the airdrop respects its per-night allowance",
    room.events.state["airdrop"].fired <= airdrop_row.max_per_night,
)
# And a crate that landed put real loot on the ground somewhere.
check("the airdrop left something to walk to", len(room.drops) > 0)

# The odds CLIMB. A flat chance is memoryless, which allows a twenty-minute
# night with nothing in it — the one outcome the file exists to prevent.
st = events.EventDirector(1).state["horde"]
row = events.BY_KEY["horde"]
first = row.chance
st.rolls = 6
later = min(1.0, row.chance + row.chance_per_roll * st.rolls)
check("the odds climb with the night", later > first)


# --- the gate ---------------------------------------------------------------
#
# One place, over every row, so a new event cannot forget it.

for label, setup in (
    # `sirening` is derived from the pads and `alarm` from the pad's own
    # clock, so the pickup is set up the way a real one is — by giving a pad a
    # `close_at` — rather than by poking flags that do not exist.
    ("a pickup", lambda r: setattr(r.rifts[0], "close_at", 0.0)),
    ("the run for the exit", lambda r: setattr(r, "blackout", True)),
    ("an arrival", lambda r: setattr(r, "arriving", True)),
    ("a departure", lambda r: setattr(r, "departing", True)),
):
    room, _ = forest_room(day=9)
    setup(room)
    run(room, 1_200.0)
    check(f"nothing fires during {label}", not room.events.drain())
    # And the night's clock did not advance either — an event that had been
    # building through a two-minute extraction would land the instant it ended.
    check(f"the script's clock is paused during {label}", room.events.elapsed == 0.0)

# The arena is a conversation between a party and one body. Nobody else is
# invited — the same rule `step_enemies` applies to the population director.
room, _ = forest_room(day=9)
# `Zone` carries a lot of arrival copy this test has no opinion about, so the
# real one is re-labelled rather than rebuilt.
room.zone = dataclasses.replace(room.zone, kind=zones.KIND_ARENA, hostile=True)
run(room, 1_200.0)
check("nothing fires in the arena", not room.events.drain())

# A safe zone has no script at all.
room, _ = forest_room(day=9)
room.zone = dataclasses.replace(room.zone, kind=zones.KIND_STORE, hostile=False)
run(room, 1_200.0)
check("nothing fires in the shop", not room.events.drain())

# COOLDOWNS RUN THROUGH THE GATE EVEN THOUGH THE CLOCK DOES NOT. Opposite
# answers to the same question, and both deliberate: "that just happened, let
# it breathe" stays true while the party is running for the exit.
room, _ = forest_room(day=9)
room.events.state["horde"].cooling = 10.0
room.rifts[0].close_at = 0.0  # a pickup is running: the gate is shut
run(room, 12.0)
check("a cooldown still runs while the gate is shut", room.events.state["horde"].cooling == 0.0)


# --- a new night is a new script --------------------------------------------

room, _ = forest_room(day=9)
run(room, EVENT_DARK_AT + 5.0)
check("the first night ran its script", room.events.elapsed > 0.0)
before_director = room.events
# A REAL SECOND NIGHT. `embark` early-returns off the forest (it is the walk
# out of the CAMP), so the crossing every later night actually takes is
# `_swap_map` — which is the one that has to do the resetting.
asyncio.run(
    room._swap_map(
        zones.forest(room.day),
        mapgen.build_forest(day=room.day, calibres=()),
    )
)
check("an entrance builds a fresh script", room.events is not before_director)
check("and its clock starts at zero", room.events.elapsed == 0.0)
check("and the dark it left behind is gone", room.dark_left == 0.0)


# --- adding an event is a data row ------------------------------------------
#
# THE CLAIM, ASSERTED. A fourth event is built here the way a real one would
# be — a function and a row — and driven through the unmodified director. If
# this ever needs a change anywhere else, the architecture stopped being what
# it says it is and this is where that surfaces.

hits: list[str] = []


def _probe(room: Room) -> dict | None:
    hits.append("fired")
    return {"x": 1.0, "y": 2.0}


probe = events.EventDef(
    key="probe",
    trigger=events.TRIGGER_TIME,
    effect=_probe,
    at=5.0,
    max_per_night=1,
)

original = events.EVENTS
try:
    events.EVENTS = original + (probe,)
    room, _ = forest_room(day=9)
    run(room, 20.0)
    check("a row added to the catalog fires", hits == ["fired"])
    rows = room.events.drain()
    probe_rows = [r for r in rows if r["k"] == "probe"]
    check("its row reaches the wire under its own key", len(probe_rows) == 1)
    # The place an effect reports rides its row — which is what lets the client
    # point a cue or push a beacon without `events.py` knowing either exists.
    check("and carries whatever the effect reported", probe_rows[0]["x"] == 1.0)
finally:
    events.EVENTS = original

# AN EFFECT THAT REFUSES COSTS NOTHING. The other half of the same contract,
# and the one that hides: a rare event silently consumed by a firing nobody
# saw is invisible from inside the game.
refusals: list[str] = []


def _never(room: Room) -> dict | None:
    refusals.append("asked")
    return None


shy = events.EventDef(
    key="shy",
    trigger=events.TRIGGER_TIME,
    effect=_never,
    at=5.0,
    max_per_night=1,
)

try:
    events.EVENTS = original + (shy,)
    room, _ = forest_room(day=9)
    run(room, 20.0)
    check("a refusing effect was asked", refusals == ["asked"])
    check("a refusing effect writes no wire row", not any(r["k"] == "shy" for r in room.events.drain()))
    check("and spends no cooldown", room.events.state["shy"].cooling == 0.0)
    check("and spends no allowance", room.events.state["shy"].fired == 0)
finally:
    events.EVENTS = original


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
