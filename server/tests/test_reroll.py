"""Buying a new shelf, and the exploit that is one line away from it.

Run:  python tests/test_reroll.py   (from server/)

The shop had exactly one decision in it: buy what is there, or save. Both
answers are fine and neither is interesting on the fourth night, because the
shelf is not a CHOICE — it is a hand the party was dealt. A reroll turns saving
into a gamble against the shelf, and the price is what stops that gamble being
free.

Four things about it are invisible from inside the game:

  * A SOLD TABLE MUST STAY SOLD. This is the whole difference between a reroll
    and an infinite-stock exploit: if a purchase came back on the next spin,
    the correct play would be to buy the cheapest thing on the shelf and reroll
    until the shop had paid for itself. Nobody reports a shop that is too
    generous — they just get rich, and the economy quietly stops mattering.
  * THE LADDER HAS TO DOUBLE, AND HAS TO RESET. Flat means a rich night is a
    queue at the merchant until the balance runs out, which turns a shelf into
    a vending machine. Carried across the run means the price by night six is a
    number nobody can reach and the mechanic silently stops existing. Both
    failures look like "the reroll is fine" from inside one visit.
  * AN EMPTY SHELF IS A REFUSAL. A party who bought everything pressing this
    would pay for a shuffle of nothing, which is the one thing a doubling
    ladder must never do.
  * THE FURNITURE MUST NOT MOVE. A shop that rearranged itself would make the
    player re-read a room they had already learned — a cost with no decision
    in it. The whole value of a reroll is that the ANSWER changes and the
    question does not.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import protocol, store, zones  # noqa: E402
from app.config import (  # noqa: E402
    PLAYER_HALF_HEIGHT,
    STORE_REROLL_PRICE,
    STORE_SPIN_PRICE,
)
from app.room import Room  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    async def send_text(self, text: str) -> None:
        pass


def shop_room(balance: int = 10_000) -> tuple[Room, str]:
    """A room standing in the merchant's clearing, at the counter, with money."""
    room = Room(code="RRL")
    room.phase = protocol.PHASE_PLAYING
    pid = room.add_player(Socket(), "P0").id
    asyncio.run(room.embark())
    asyncio.run(room.enter_store())
    room.arriving = False
    room.departing = False
    room.balance = balance
    player = room.players[pid]
    spot = room._merchant_spot()
    assert spot is not None, "the shop has a merchant to stand at"
    player.x = spot[0]
    player.y = spot[1] - PLAYER_HALF_HEIGHT
    return room, pid


def shelf(room: Room) -> list[tuple[str, str, int]]:
    return [(s.id, s.key, s.price) for s in room.stands]


# --- the ladder --------------------------------------------------------------

room, pid = shop_room()
check("the shop has tables", len(room.stands) > 0)
check("the first reroll costs the base price", room.reroll_price == STORE_REROLL_PRICE)

# CHEAPER THAN A PULL, and the gap is the argument: a bought pull is a skill
# kept for the rest of the run, a reroll is six things you might not want.
check("a reroll is cheaper than a bought pull", STORE_REROLL_PRICE < STORE_SPIN_PRICE)

before = room.balance
room.reroll(pid)
check("it takes the money", room.balance == before - STORE_REROLL_PRICE)
check("and doubles", room.reroll_price == STORE_REROLL_PRICE * 2)
room.reroll(pid)
check("and doubles again", room.reroll_price == STORE_REROLL_PRICE * 4)
check("the lever reached the wire", len(room.reroll_events) == 2)
check("with what it cost on it", room.reroll_events[0]["cost"] == STORE_REROLL_PRICE)

# IT DOUBLES FOREVER WITHIN A VISIT — the point is that the party always gets
# to buy one more and never gets to buy five.
for _ in range(4):
    room.reroll(pid)
check("six rerolls cost 32x the first", room.reroll_price == STORE_REROLL_PRICE * 64)

# AND IT RESETS ON THE NEXT NIGHT'S SHOP. Carried across the run, the price by
# night six would be a number nobody can reach and the mechanic would quietly
# stop existing.
# A REAL SECOND NIGHT: `enter_store` early-returns when the party is already
# in the shop (it is the corridor OUT of a forest), so walking back out and
# home again is the only way to ask this honestly.
asyncio.run(room.depart_store())
asyncio.run(room.enter_store())
check("a new night starts the ladder over", room.reroll_price == STORE_REROLL_PRICE)


# --- a sold table stays sold -------------------------------------------------
#
# THE ONE THAT MATTERS. Without it, buy the cheapest thing and reroll until the
# shop has paid for itself.

room, pid = shop_room()
sold = room.stands[0]
sold_key = sold.key
sold.sold = True
open_before = [(s.id, s.key) for s in room.stands if not s.sold]

room.reroll(pid)
check("the sold table is still sold", sold.sold)
check("and still holds what was bought off it", sold.key == sold_key)

# And the OTHERS moved, or the purchase was not a reroll at all.
open_after = [(s.id, s.key) for s in room.stands if not s.sold]
check("the same tables are still the open ones", [i for i, _ in open_before] == [i for i, _ in open_after])
changed = sum(1 for a, b in zip(open_before, open_after) if a[1] != b[1])
check(f"the unsold stock actually changed ({changed} of {len(open_after)})", changed > 0)

# NOTHING LEFT TO REROLL IS A REFUSAL, not a purchase.
room, pid = shop_room()
for stand in room.stands:
    stand.sold = True
purse = room.balance
price = room.reroll_price
room.reroll(pid)
check("an empty shelf is refused", room.balance == purse)
check("and costs nothing off the ladder", room.reroll_price == price)


# --- the furniture does not move ---------------------------------------------

room, pid = shop_room()
places = [(s.id, s.x, s.y, s.variant) for s in room.stands]
for _ in range(5):
    room.reroll(pid)
after = [(s.id, s.x, s.y, s.variant) for s in room.stands]
check("the tables stay exactly where they were", places == after)


# --- the refusals ------------------------------------------------------------

# BROKE. The ladder must not move and the shelf must not turn.
room, pid = shop_room(balance=0)
was = shelf(room)
room.reroll(pid)
check("a broke party is refused", shelf(room) == was)
check("and pays nothing", room.balance == 0)
check("and the ladder does not move", room.reroll_price == STORE_REROLL_PRICE)

# TOO FAR AWAY. Measured from the FEET, like every other press in this room.
room, pid = shop_room()
was = shelf(room)
room.players[pid].x += 40 * 16.0
room.reroll(pid)
check("standing away from the counter is refused", shelf(room) == was)

# OFF THE SHOP MAP ENTIRELY.
room, pid = shop_room()
room.zone = zones.forest(1)
was = shelf(room)
room.reroll(pid)
check("there is no merchant in the forest", shelf(room) == was)

# A DEAD PLAYER DOES NOT SHOP.
room, pid = shop_room()
room.players[pid].alive = False
was = shelf(room)
room.reroll(pid)
check("a dead player is refused", shelf(room) == was)


# --- what it rolls -----------------------------------------------------------
#
# `reroll_stands` in isolation, because the stock rules are the store's and a
# reroll must not have invented its own.

stands = store._place_stands(60, 60, day=4, rng=random.Random(11))
check("the helper built a shelf", len(stands) > 0)
for stand in stands:
    check(f"{stand.key} is something the merchant sells", stand.key in store.SELLABLE)

store.reroll_stands(stands, day=4, rng=random.Random(12))
for stand in stands:
    check(f"after a reroll {stand.key} is still real stock", stand.key in store.SELLABLE)
    check(f"and {stand.key} still has a price", stand.price > 0)

# A reroll of an all-sold shelf is a no-op rather than an error — the room
# refuses first, but the helper must not depend on that.
for stand in stands:
    stand.sold = True
frozen = [(s.key, s.price) for s in stands]
store.reroll_stands(stands, day=4, rng=random.Random(13))
check("rerolling a sold-out shelf changes nothing", [(s.key, s.price) for s in stands] == frozen)


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
