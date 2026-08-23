"""Permadeath: the down state, the wipe, and what a run costs when it ends.

Drives the whole thing with nobody watching, because every one of these has no
symptom you would see in a screenshot until it is far too late:

  * a downed body does not stand back up on a timer — the bug that would undo
    the entire feature is one subtraction in `step_players`, and its symptom is
    "death still costs two seconds", which looks exactly like nothing happening
  * one player down out of two is NOT a wipe, and the survivor can still finish
    the night — the co-op half of the rule
  * the crossing is the rescue: a downed body that reaches the next zone stands
    up carrying everything it had
  * a wipe strips the run to the bone. This is the one worth pinning hardest,
    because a partial reset is indistinguishable from a total one for the first
    thirty seconds of the next run, and by the time anybody notices the AWP
    survived they have played four nights with it
  * the camp comes back for a wipe, which is the ONE exception to the loop
    never returning home
  * nothing in the camp or the shop can down anybody, so a knife at the
    merchant's counter is still a fumble rather than the end of four nights
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import zones, protocol
from app.config import MAX_HP, WIPE_HOLD, DT
from app.room import Room

FAILED = []


def check(label, cond):
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    """Enough of a WebSocket that `_swap_map` can send a welcome down it.

    A `None` socket is what the other tests pass, and it works for them
    because they never swap a map — here the crossing IS the thing under test,
    and `_safe_send` evicts any player whose socket raises.
    """

    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(text)


def forest_room(players=1):
    """A room already standing in a forest, with `players` living bodies."""
    room = Room(code="TEST")
    room.phase = protocol.PHASE_PLAYING
    ids = []
    for i in range(players):
        player = room.add_player(Socket(), f"P{i}")
        ids.append(player.id)
    asyncio.run(room.embark())
    return room, ids


def kill(room, player):
    """Take one body to zero through the one door damage comes through."""
    room.damage_player(player, 10_000, None)


# --- a body goes DOWN and stays down ----------------------------------------
room, ids = forest_room(1)
p0 = room.players[ids[0]]
check("forest is hostile", room.zone.hostile)
kill(room, p0)
check("a killed body is not alive", not p0.alive)
check("a killed body is DOWNED", p0.downed)
check("a downed body has no respawn timer", p0.respawn_timer == 0.0)

# Ten seconds of ticking. The old code would have stood this body up in two.
for _ in range(int(10.0 / DT)):
    room.step(DT)
check("a downed body is STILL down after 10s", p0.downed and not p0.alive)
check("solo down starts the wipe hold", room._wipe_day == 1)

# --- the snapshot says so ----------------------------------------------------
payload = protocol.snapshot(
    0, [p.snapshot_payload() for p in room.players.values()], [], [], [], [], [], [],
    wipe={"day": room._wipe_day} if room._wipe_day else None,
)
check("the tick row carries `down`", payload["players"][0]["down"] is True)
check("the snapshot carries `wipe`", payload.get("wipe") == {"day": 1})


# --- one down out of two is NOT a wipe --------------------------------------
room, ids = forest_room(2)
a, b = room.players[ids[0]], room.players[ids[1]]
kill(room, a)
for _ in range(int(2.0 / DT)):
    room.step(DT)
check("one down out of two: that body is down", a.downed)
check("one down out of two: the other still stands", b.alive and not b.downed)
check("one down out of two is NOT a wipe", room._wipe_day == 0)

# ...and the survivor going down IS.
kill(room, b)
room.step(DT)
check("both down IS a wipe", room._wipe_day == 1)


# --- the crossing is the rescue ---------------------------------------------
room, ids = forest_room(2)
a, b = room.players[ids[0]], room.players[ids[1]]
a.hotbar.slots[0] = "ak47"
a.xp = 500
kill(room, a)
room.step(DT)
check("rescue setup: one down, one up", a.downed and b.alive)
check("rescue setup: no wipe pending", room._wipe_day == 0)
asyncio.run(room.enter_store())
check("crossing stands the downed body up", a.alive and not a.downed)
check("crossing heals it", a.hp == a.max_hp)
check("a rescued body keeps its gun", a.hotbar.slots[0] == "ak47")
check("a rescued body keeps its xp", a.xp == 500)
check("the day did NOT reset on a rescue", room.day == 1)


# --- the wipe strips the run ------------------------------------------------
room, ids = forest_room(1)
p0 = room.players[ids[0]]
room.day = 7
room.balance = 4321
p0.hotbar.slots[0] = "awp"
p0.hotbar.slots[1] = "deagle"
p0.hotbar.slots[2] = "katana"
p0.xp = 9999
p0.gold = 250
p0.ammo.add("rifle", 120)
p0.skills.add("passo_leve")
p0.medical.add("first_aid")
p0.inventory.add("gold_ring")
before_deaths = p0.deaths

kill(room, p0)
room.step(DT)
check("wipe card names the night it ended on", room._wipe_day == 7)

# Hold, then the reset fires out of the run loop.
for _ in range(int((WIPE_HOLD + 0.2) / DT)):
    room.step(DT)
check("the hold expires", room._wipe_hold == 0.0)
check("the latch survives the hold", room._wipe_day == 7)
asyncio.run(room.wipe())

check("wipe: day back to one", room.day == 1)
check("wipe: balance gone", room.balance == 0)
check("wipe: back at the CAMP", room.zone.kind == zones.KIND_CAMP)
check("wipe: the camp is not hostile", not room.zone.hostile)
check("wipe: guns gone", p0.hotbar.slots[0] is None and p0.hotbar.slots[1] is None)
check("wipe: the blade cell is a knife again", p0.hotbar.blade == "knife")
check("wipe: skills gone", p0.skills.mods.speed == 1.0 and not p0.skills.stacks)
check("wipe: xp gone", p0.xp == 0)
check("wipe: dark gold gone", p0.gold == 0)
check("wipe: reserve empty", sum(p0.ammo.rounds.values()) == 0)
check("wipe: pocket empty", all(sl is None for sl in p0.inventory.slots))
check("wipe: medical cells empty", p0.medical.count == 0)
check("wipe: armour off", p0.armor.weight == 0.0 and p0.shield is None)
check("wipe: standing and whole", p0.alive and not p0.downed and p0.hp == MAX_HP)
check("wipe: max hp back to the opening value", p0.max_hp == MAX_HP)
check("wipe: not ready", not p0.ready)
check("wipe: the latch is cleared", room._wipe_day == 0)
check("wipe: deaths are a SESSION counter and survive", p0.deaths == before_deaths + 1)


# --- a non-hostile zone cannot end a run ------------------------------------
room, ids = forest_room(1)
asyncio.run(room.enter_store())
# The arrival cinematic puppets bodies and returns out of `step_players` before
# any timer is touched, which is correct and is not what this block is about.
room.arriving = False
p0 = room.players[ids[0]]
check("the shop is not hostile", not room.zone.hostile)
kill(room, p0)
check("a death in the shop does NOT down anybody", not p0.downed)
check("a death in the shop keeps the respawn timer", p0.respawn_timer > 0.0)
for _ in range(int(3.0 / DT)):
    room.step(DT)
check("a death in the shop respawns as it always did", p0.alive)
check("a death in the shop never starts a wipe", room._wipe_day == 0)


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
