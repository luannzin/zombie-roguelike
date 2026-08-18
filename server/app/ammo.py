"""Ammunition: the reserve behind a gun, and the boxes that refill it.

Guns used to be free forever. You found one, and from then on the trigger was
a decision about noise and nothing else. That is a fine weapon and a poor
ECONOMY, and this game already had an economy — a night is a bag of loot
traded for a platform lifting off, and the only thing that was not on that
ledger was the thing you spent to fill the bag.

So: every gun eats a ROUND per shot out of a per-player reserve for its
calibre. The knife eats nothing, which is the entire reason the knife is still
in the game.

THREE RULES, AND THEY ARE THE DESIGN

  1. AMMUNITION IS NOT CARGO. A box has value 0 in the loot catalog, takes no
     pocket slot and cannot be loaded onto a platform. It is upkeep. A round
     that competed with a gold ring for a bag cell would make shooting a
     choice against extracting, which is not a trade-off, it is a tax on
     playing.

  2. A BOX ONLY EXISTS IF SOMEBODY CAN USE IT. `scatter` is given the set of
     calibres the party is actually carrying and places nothing else, so a
     party of knives finds no ammunition at all and a party with one Glock
     does not walk past crates of .308 all night. The forest stocks itself
     against the belt.

  3. A BOX IS COLLECTED BY THE PERSON WHO CAN SHOOT IT. The check is on the
     collecting player's own hotbar, not the party's — in a four-player room
     the rifle rounds go to whoever brought the rifle, and nobody can hoover
     up a calibre they cannot fire. That is also what stops ammunition being
     a second currency people trade over voice.

Guns themselves are bought and never found (`loot.ItemDef.droppable`), so
calibre and ownership are the same question: what the party paid the merchant
for last night decides what the forest offers them tonight.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .config import TILE_SIZE
from .loot import BY_KEY as ITEMS, Drop, free_tile_near
from .weapons import AMMO_AWP, AMMO_NONE, AMMO_PISTOL, AMMO_RIFLE, BY_KEY as WEAPONS

#: Every calibre the game knows, in HUD order.
TYPES: tuple[str, ...] = (AMMO_PISTOL, AMMO_RIFLE, AMMO_AWP)

#: Which catalog row is a box of each. One box, one calibre, one key.
BOX_KEYS: dict[str, str] = {
    AMMO_PISTOL: "ammo_pistol",
    AMMO_RIFLE: "ammo_rifle",
    AMMO_AWP: "ammo_awp",
}

#: How much a player may hold, per calibre.
#:
#: Sized in SECONDS OF TRIGGER, not in a round count that looks tidy. A full
#: pistol reserve is about thirty seconds of continuous fire, a rifle a little
#: under thirty, an AWP about forty-five — so no calibre feels stingier than
#: another when you are actually in trouble, and the difference between them
#: stays what it always was: cadence, damage and how much forest hears it.
RESERVE_MAX: dict[str, int] = {
    AMMO_PISTOL: 180,
    AMMO_RIFLE: 270,
    AMMO_AWP: 30,
}

#: What a gun arrives with when the merchant hands it over.
#:
#: A third of a full reserve. Enough that a purchase is immediately usable —
#: buying a rifle and then walking into a night unable to fire it would make
#: the shop feel broken — and not so much that the first night with a new gun
#: never has to find a box.
STARTING_ROUNDS: dict[str, int] = {
    AMMO_PISTOL: 60,
    AMMO_RIFLE: 90,
    AMMO_AWP: 10,
}

#: Boxes per calibre scattered on a forest map, before the day is counted.
SCATTER_BASE = 2
#: One more every other day, because later nights are longer walks.
SCATTER_PER_DAY = 0.5
SCATTER_MAX = 5

#: How likely an object whose tags say MILITARY pays out rounds instead of
#: rolling the catalog. Only ever consulted for a calibre somebody owns.
CRATE_AMMO_CHANCE = 0.45

#: Tags that make an object a plausible place for ammunition. An ammo case and
#: a police cruiser qualify; a mailbox does not, and the difference is most of
#: what makes the object vocabulary worth having.
MILITARY_TAGS = frozenset({"military", "combat"})


def calibre_of(weapon_key: str | None) -> str | None:
    """The calibre a weapon eats, or None for the knife and for nothing."""
    if not weapon_key:
        return None
    weapon = WEAPONS.get(weapon_key)
    if weapon is None or weapon.ammo == AMMO_NONE:
        return None
    return weapon.ammo


@dataclass
class Reserve:
    """One player's rounds, by calibre. Zero is a real state, not an error."""

    rounds: dict[str, int] = field(default_factory=dict)

    def get(self, calibre: str) -> int:
        return self.rounds.get(calibre, 0)

    def add(self, calibre: str, count: int) -> int:
        """Top up, clamped at the cap. Returns how many actually fitted.

        The return is what makes a full reserve REFUSE a box rather than
        swallow it: `Room.collect_loot` leaves the drop on the ground when
        nothing fitted, so a player who is already carrying everything they
        can shoot walks past the box and it is still there on the way back.
        """
        if calibre not in RESERVE_MAX or count <= 0:
            return 0
        have = self.rounds.get(calibre, 0)
        room = RESERVE_MAX[calibre] - have
        taken = min(room, count)
        if taken > 0:
            self.rounds[calibre] = have + taken
        return taken

    def spend(self, calibre: str | None) -> bool:
        """Take one round. True if there was one; False is a dry trigger.

        `None` — a knife, or anything else with no calibre — always succeeds,
        because a weapon that does not eat rounds cannot run out of them.
        """
        if calibre is None:
            return True
        have = self.rounds.get(calibre, 0)
        if have <= 0:
            return False
        self.rounds[calibre] = have - 1
        return True

    def grant_for(self, weapon_key: str) -> None:
        """Hand over a bought gun's starting load."""
        calibre = calibre_of(weapon_key)
        if calibre is not None:
            self.add(calibre, STARTING_ROUNDS.get(calibre, 0))

    def to_payload(self) -> dict:
        """Every calibre, always, including the zeroes.

        A missing key and a zero would have to be told apart on the client to
        draw the counter, and "you have no rifle rounds" is exactly as much
        information as "you have forty" — the HUD needs to be able to say it.
        """
        return {calibre: self.rounds.get(calibre, 0) for calibre in TYPES}


def from_payload(row: dict | None) -> Reserve:
    reserve = Reserve()
    for calibre in TYPES:
        value = (row or {}).get(calibre)
        if isinstance(value, (int, float)):
            reserve.rounds[calibre] = max(0, int(value))
    return reserve


def carried_by(hotbar) -> set[str]:
    """Calibres on ONE belt. What decides which boxes this player may take."""
    found: set[str] = set()
    for key in hotbar.slots:
        calibre = calibre_of(key)
        if calibre is not None:
            found.add(calibre)
    return found


def party_calibres(players) -> set[str]:
    """Calibres anywhere in the room. What decides what the forest stocks."""
    found: set[str] = set()
    for player in players:
        found |= carried_by(player.hotbar)
    return found


def box_for(calibre: str) -> str | None:
    return BOX_KEYS.get(calibre)


def calibre_for_key(item_key: str) -> str | None:
    """The reserve an `ammo` catalog row fills, or None if it is not one."""
    item = ITEMS.get(item_key)
    if item is None or item.pocket != "ammo":
        return None
    return item.ammo or None


def rounds_in(item_key: str) -> int:
    item = ITEMS.get(item_key)
    return item.rounds if item is not None else 0


def scatter_count(day: int) -> int:
    """Boxes of ONE calibre on a map of this day."""
    return min(SCATTER_MAX, SCATTER_BASE + int(day * SCATTER_PER_DAY))


def scatter(
    tiles: list[list[int]],
    scenes,
    rng: random.Random,
    calibres: set[str],
    day: int,
    next_id: int,
    occupied: list[tuple[float, float]] | None = None,
) -> list[Drop]:
    """Place ammunition next to the scenes that landed.

    A SECOND PASS over the same scene list `loot.scatter` walks, and for the
    same reason: the boxes have to be where the party is already going.
    Ammunition scattered on a uniform grid would turn a walk into a mowing
    pattern, and ammunition placed only in objects would make a night with a
    bad roll unplayable rather than tense.

    Returns drops with ids continuing from `next_id`.
    """
    drops: list[Drop] = []
    if not calibres or not scenes:
        return drops
    taken = occupied if occupied is not None else []
    places = list(scenes)
    index = next_id
    for calibre in TYPES:
        if calibre not in calibres:
            continue
        key = BOX_KEYS.get(calibre)
        if key is None:
            continue
        for _ in range(scatter_count(day)):
            scene = rng.choice(places)
            spot = free_tile_near(tiles, scene.x, scene.y, taken, rng)
            if spot is None:
                continue
            tx, ty = spot
            taken.append((tx, ty))
            drops.append(
                Drop(
                    id=f"a{index}",
                    key=key,
                    x=(tx + 0.5) * TILE_SIZE,
                    y=(ty + 0.5) * TILE_SIZE,
                )
            )
            index += 1
    return drops


def roll_from_object(
    tags: tuple[str, ...], rng: random.Random, calibres: set[str]
) -> str | None:
    """A box out of an opened object, or None to fall through to the catalog.

    Only military-flavoured objects, only calibres somebody owns, and only
    some of the time. An ammo case that produced rounds every single time
    would be a vending machine, and the whole point of the object vocabulary
    is that a player is guessing.
    """
    if not calibres or not (MILITARY_TAGS & set(tags)):
        return None
    if rng.random() > CRATE_AMMO_CHANCE:
        return None
    pool = [calibre for calibre in TYPES if calibre in calibres]
    if not pool:
        return None
    return BOX_KEYS.get(rng.choice(pool))


def client_payload() -> dict:
    """What the HUD needs to draw a counter and predict a dry trigger."""
    return {
        "types": list(TYPES),
        "boxes": dict(BOX_KEYS),
        "max": dict(RESERVE_MAX),
    }
