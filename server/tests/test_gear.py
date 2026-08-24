"""What a body carries and what stands between it and a blow.

Three systems land on one player and none of them has a symptom you would see
in a screenshot:

  * THE BLADE CELL. It is never empty and its contents change. Every rule
    about it is a rule about a cell that has no "empty" state, which is the
    one shape the rest of the belt does not have — so every off-by-one here
    produces a run where the hand is suddenly empty, which the player finds
    out about in front of something.
  * WORN ARMOUR. A plate that takes nothing off, one that never breaks and a
    plate that breaks on the first hit all look identical while you are
    playing: the number on the HUD is small and the thing hitting you is not
    holding still. The only way to know is arithmetic.
  * THE SHIELD. It is the one thing in the game that takes a blow to ZERO, and
    the one thing that only works in a direction. A shield that blocked from
    behind would be a strictly-better plate and nobody would ever notice it
    was wrong — they would just stop dying.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import armor, loot, weapons  # noqa: E402
from app.entities import InputCmd, Player  # noqa: E402
from app.room import Room  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _room() -> tuple[Room, Player]:
    room = Room(code="GEAR", seed=7)
    player = Player(id="p1", name="Ana", color="#fff")
    # Somewhere walkable, so a displaced piece has floor to land on.
    player.x, player.y = room.pick_spawn()
    room.players[player.id] = player
    return room, player


# --- the blade cell ----------------------------------------------------------


def test_blade_cell() -> None:
    room, player = _room()
    bar = player.hotbar

    check(bar.blade == "knife", "a run opens on the knife")
    check(bar.held == weapons.BLADE_SLOT, "and holding it")
    check(not bar.can_stow("knife"), "a second knife changes nothing and is refused")

    # THE KNIFE IS NOT AN OBJECT. Replacing it leaves nothing on the floor,
    # because it was never a thing the party owned — it is the promise that
    # the cell is full.
    before = len(room.drops)
    slot = room.take_weapon(player, "axe")
    check(slot == weapons.BLADE_SLOT, "a lâmina goes in the blade cell")
    check(bar.blade == "axe", "and replaces what was there")
    check(len(room.drops) == before, "the knife does not fall on the floor")
    check(bar.held == weapons.BLADE_SLOT, "the hand keeps holding the cell it was on")

    # Every OTHER blade does fall, so the trade is reversible one step later.
    before = len(room.drops)
    room.take_weapon(player, "katana")
    check(bar.blade == "katana", "the better blade is in the cell")
    check(len(room.drops) == before + 1, "the axe is on the ground")
    check(
        any(d.key == "axe" for d in room.drops.values()),
        "and it is the axe, not something else",
    )

    # A GUN NEVER LANDS IN THE BLADE CELL, and the blade cell cannot be traded
    # away to make room for one.
    room.take_weapon(player, "glock18")
    room.take_weapon(player, "usp_s")
    check(bar.slots[: weapons.GUN_SLOTS] == ["glock18", "usp_s"], "guns fill gun cells")
    check(bar.blade == "katana", "and leave the blade alone")
    bar.held = weapons.BLADE_SLOT
    check(
        room.swap_weapon(player, "ak47") is None,
        "a full belt refuses to trade the blade cell for a rifle",
    )
    check(bar.blade == "katana", "and the cell is untouched by the refusal")

    # The cell cannot be emptied by anything, including a malformed bar.
    bar.slots[weapons.BLADE_SLOT] = None
    weapons.Hotbar.__post_init__(bar)
    check(bar.blade == "knife", "an emptied blade cell falls back to the floor blade")


# --- the ladder is derived ---------------------------------------------------


def test_blade_ladder() -> None:
    # The knife's own profile is all ones, so the generator has to reproduce
    # the weapon it was derived from EXACTLY. A generator that could not is a
    # second opinion about a swing that is already tuned.
    knife = weapons.BY_KEY["knife"].melee
    check(knife is not None, "the knife swings")
    check(
        [step.damage for step in knife.steps] == [6, 7, 14],
        f"the knife's authored chain, unchanged: {[s.damage for s in knife.steps]}",
    )
    check(
        [step.cooldown for step in knife.steps] == [0.30, 0.28, 0.62],
        "and its authored cadence",
    )
    for step in knife.steps:
        # `swing` is HALF the arc in radians and is derived rather than typed:
        # the held sprite tracks the drawn white path edge for edge, so a
        # value disagreeing with the arc puts the steel where the path is not.
        import math

        check(
            abs(step.swing - math.radians(step.arc_degrees) / 2) < 0.001,
            f"a swing that is not half its own arc: {step.swing} vs {step.arc_degrees}",
        )

    chains = {
        key: sum(s.damage for s in weapons.BY_KEY[key].melee.steps)
        for key in weapons.BLADE_KEYS
    }
    check(
        chains["knife"] < weapons.ZOMBIE_HP < chains["katana"] < chains["axe"],
        f"the ladder is knife < one zombie < katana < axe: {chains}",
    )
    values = {key: loot.BY_KEY[key].value for key in weapons.BLADE_KEYS}
    check(
        values["knife"] < values["axe"] < values["katana"],
        f"and price follows what a blade DOES, not what it hits for: {values}",
    )


# --- worn armour -------------------------------------------------------------


#: Samples per distribution check, and the seed that makes them the same
#: samples every run.
#:
#: WHERE A BLOW LANDS IS THE ONE RANDOM THING IN THIS WHOLE SYSTEM, and a test
#: that measured it unseeded would be a test that fails a couple of times in a
#: hundred for no reason — which is worse than no test, because the next
#: person to see it red will assume it is always flaky and stop reading it.
#: `armor._RNG` is module-level precisely so the room shares one stream; here
#: it is what makes the arithmetic reproducible.
ROLLS = 4000
SEED = 20260823


def test_armor_rating() -> None:
    room, player = _room()
    armor._RNG.seed(SEED)

    # Bare: everything lands.
    player.hp = 100
    room.damage_player(player, 10, None)
    check(player.hp == 90, f"a bare body takes the whole blow, got {player.hp}")

    # A blow only meets the plate on the part it landed on, so the honest test
    # is over the WHOLE distribution rather than one roll.
    for slot in armor.SLOTS:
        player.armor.equip(f"{slot}_steel")
    check(
        abs(player.armor.weight - len(armor.SLOTS) * armor.weight_of(3)) < 1e-6,
        "a set weighs one plate per slot",
    )
    check(
        abs(player.carry_weight - (player.armor.weight + player.hotbar.held_weight)) < 1e-6,
        "and the WALK carries them — the bag does not",
    )

    # A FULL SET IS ITS MATERIAL'S RATING, whatever the blow. Flat means the
    # take does not depend on the size of the hit — and it means the roll
    # cannot change the answer either, because every part is covered by the
    # same material.
    rating = armor.armor_of(3)
    for blow in (16, 9, 40):
        for _ in range(64):
            for piece in player.armor.worn.values():
                piece.hp = piece.max_hp
            through, _, key, _ = player.armor.absorb(blow)
            check(key is not None, "a full set is never bare")
            check(
                blow - through == rating,
                f"a steel set takes {rating} off any blow; off {blow} it took {blow - through}",
            )
    # AND A BLOW SMALLER THAN THE RATING IS STOPPED ENTIRELY, costing the
    # plate only what it actually absorbed. Small hits wear armour slowly,
    # which falls out of the model rather than being a rule on top of it.
    for piece in player.armor.worn.values():
        piece.hp = piece.max_hp
    before = sum(p.hp for p in player.armor.worn.values())
    through, _, _, _ = player.armor.absorb(2)
    check(through == 0, f"a 2-point blow does not get through 5 of armour, got {through}")
    check(
        before - sum(p.hp for p in player.armor.worn.values()) == 2,
        "and it costs the plate 2, not 5",
    )

    # A PARTIAL SET IS PARTIAL. The roll happens whether or not anything is
    # there, so a helmet is not quietly worn on the legs.
    # RE-SEEDED, so this distribution does not depend on how many rolls the
    # checks above happened to consume. A seeded test whose numbers move when
    # an unrelated assertion is added is a seeded test in name only.
    armor._RNG.seed(SEED)
    only_head = armor.Loadout()
    only_head.equip("head_kevlar")
    bare = 0
    for _ in range(ROLLS):
        only_head.worn["head"].hp = only_head.worn["head"].max_hp
        _, _, key, _ = only_head.absorb(16)
        if key is None:
            bare += 1
    check(bare > 0, "a body in one helmet still gets hit somewhere else")
    # THE SHARES HAVE TO ADD UP TO A BODY, or `_roll_slot` renormalises and
    # every number the HUD prints is quietly wrong. Nothing at runtime
    # notices; `armor._check_coverage` fails the import, and this is the
    # behavioural half of the same claim.
    check(
        abs(sum(armor.COVERAGE.values()) - 1.0) < 1e-9,
        f"coverage sums to {sum(armor.COVERAGE.values())}, not 1",
    )
    check(
        abs((1 - bare / ROLLS) - armor.COVERAGE["head"]) < 0.03,
        f"and the helmet only answers its own share of blows: {1 - bare / ROLLS:.3f}",
    )


def test_armor_breaks() -> None:
    room, player = _room()
    player.armor.equip("body_cloth")
    piece = player.armor.get("body")
    check(piece is not None and piece.hp == armor.hp_of(1), "a fresh plate is whole")

    # A piece survives `HITS_BASE * tier` blows LANDING ON IT and then goes,
    # and the blow that finishes it is still absorbed: the last thing a
    # chestplate does is its job. EXACT, not approximate — a flat take out of
    # a durability sized as a multiple of it divides evenly, which is the
    # whole reason the HUD can promise a count.
    blow = armor.armor_of(1) * 3
    hits = 0
    while player.armor.get("body") is not None:
        through, _, _, broke = player.armor.absorb_at("body", blow)
        check(through == blow - armor.armor_of(1), "the plate took its rating off every blow")
        hits += 1
        check(hits < 50, "a cloth vest that will not break")
    check(
        hits == armor.HITS_BASE * 1,
        f"cloth is {armor.HITS_BASE} blows, got {hits}",
    )
    check(player.armor.get("body") is None, "and then it is gone")

    # Gone off the body means gone off the wire, which is what takes the
    # overlay off the sprite.
    check("body" not in player.armor.to_payload(), "a broken plate leaves the roster")


def test_armor_pickup() -> None:
    room, player = _room()
    check(loot.BY_KEY["body_steel"].pocket == "worn", "a plate is worn, not stowed")

    slot = room.wear_armor(player, "body_leather")
    check(slot == armor.SLOTS.index("body"), "it goes on, and names its own row")
    check(room.wear_armor(player, "body_leather") is None, "the same fresh plate is refused")

    # A worn piece keeps its damage through the swap, so "is this actually an
    # upgrade" stays a real question.
    player.armor.get("body").hp = 4
    before = len(room.drops)
    room.wear_armor(player, "body_cloth")
    check(player.armor.get("body").key == "body_cloth", "a WORSE plate still goes on")
    check(len(room.drops) == before + 1, "and the cracked one is on the floor")
    dropped = next(d for d in room.drops.values() if d.key == "body_leather")
    check(dropped.hp == 4, f"still cracked, got {dropped.hp}")

    # And picking it back up restores exactly that.
    room.wear_armor(player, dropped.key, dropped.hp)
    check(player.armor.get("body").hp == 4, "the wear survives the round trip")


# --- the shield --------------------------------------------------------------


def _face(player: Player, dx: float, dy: float) -> None:
    player.aim_x, player.aim_y = dx, dy


def test_shield_blocks_what_it_faces() -> None:
    room, player = _room()
    room.take_weapon(player, "riot_shield")
    check(player.shield is not None, "a shield on the belt brings its durability")
    check(player.shield.max_hp == armor.shield_hp(), "whole")
    slot = next(i for i, k in enumerate(player.hotbar.slots) if k == "riot_shield")
    player.hotbar.held = slot

    # RIGHT MOUSE IS A REQUEST. Down, it buys nothing.
    room.sync_block(player, InputCmd(block=False))
    check(not player.blocking and player.block_speed == 1.0, "a shield down costs nothing")
    player.hp = 100
    room.damage_player(player, 20, None, player.x + 100, player.y)
    check(player.hp == 80, "and stops nothing")

    room.sync_block(player, InputCmd(block=True))
    check(player.blocking, "held, it goes up")
    check(player.block_speed == armor.SHIELD_SPEED, "and the walk pays for it")

    # FROM THE FRONT: the blow does not happen.
    _face(player, 1.0, 0.0)
    player.hp = 100
    left = player.shield.hp
    room.damage_player(player, 20, None, player.x + 100, player.y)
    check(player.hp == 100, f"a blocked blow costs no health, got {player.hp}")
    check(player.shield.hp == left - 20, "it costs the shield instead")

    # FROM BEHIND: it does. A shield with no back is what makes a second
    # player worth having.
    player.hp = 100
    left = player.shield.hp
    room.damage_player(player, 20, None, player.x - 100, player.y)
    check(player.hp == 80, f"nothing stops a blow from behind, got {player.hp}")
    check(player.shield.hp == left, "and the shield is untouched by it")

    # A caller that does not know where the blow came from does not block:
    # guessing would make the one honest thing about a shield a coin flip.
    player.hp = 100
    room.damage_player(player, 20, None)
    check(player.hp == 80, "an unplaced blow is not blocked")


def test_shield_breaks() -> None:
    room, player = _room()
    room.take_weapon(player, "riot_shield")
    slot = next(i for i, k in enumerate(player.hotbar.slots) if k == "riot_shield")
    player.hotbar.held = slot
    room.sync_block(player, InputCmd(block=True))
    _face(player, 1.0, 0.0)

    player.hp = 100
    over = armor.shield_hp() + 15
    room.damage_player(player, over, None, player.x + 100, player.y)
    # The last thing a shield does is spend itself, and what it could not eat
    # goes through.
    check(player.hp == 85, f"the overflow lands, got {100 - player.hp}")
    check(player.shield is None, "the shield is gone")
    check(
        all(not weapons.is_shield(k) for k in player.hotbar.slots),
        "and off the belt — a shield at zero is not a shield",
    )
    check(not player.blocking and player.block_speed == 1.0, "the stance goes with it")

    # A shield in hand has no trigger at all, blocking or not.
    room.take_weapon(player, "riot_shield")
    player.hotbar.held = next(
        i for i, k in enumerate(player.hotbar.slots) if k == "riot_shield"
    )
    room.handle_attack(player, InputCmd(shoot=True), 1 / 30)
    check(not room.shot_events and not room.swing_events, "a shield does not attack")

    # At most one, ever.
    check(not player.hotbar.can_stow("riot_shield"), "a second riot shield is refused")


# --- the shop sells all three ------------------------------------------------


def test_shop_ladders() -> None:
    from app import store

    for key in ("axe", "katana", "riot_shield", "head_kevlar"):
        check(key in store.SELLABLE, f"{key} is not on any shelf")
    check("knife" not in store.SELLABLE, "a table selling the knife sells nothing")

    # THE DAY WALKS EVERY LADDER AT ONCE. Night one is the bottom of each, and
    # the gun ladder is byte-for-byte what it was before there was anything
    # else on the shelf — three cloth rags cost less than a pistol, and a
    # merged sort would have pushed the first firearm off night one.
    day_one = [k for k in store.STOCK_ORDER if store.STOCK_UNLOCK[k] == 1]
    guns = [k for k in day_one if store._category(k) == store.CATEGORY_GUN]
    check(
        len(guns) == store.STOCK_FIRST_BAND,
        f"night one still opens on {store.STOCK_FIRST_BAND} guns, got {guns}",
    )
    for ladder in (store.CATEGORY_ARMOR, store.CATEGORY_STEEL):
        rungs = [k for k in day_one if store._category(k) == ladder]
        check(rungs, f"night one has nothing from the {ladder} ladder")
    # And every ladder TOPS OUT on the last night, whatever the categories
    # happen to cost relative to each other. `STOCK_ORDER` is cheapest-first,
    # so the last rung of a ladder is its dearest.
    for ladder in (store.CATEGORY_GUN, store.CATEGORY_ARMOR, store.CATEGORY_STEEL):
        rungs = [k for k in store.STOCK_ORDER if store._category(k) == ladder]
        check(
            store.STOCK_UNLOCK[rungs[-1]] == store.STOCK_DAYS,
            f"the {ladder} ladder's top rung ({rungs[-1]}) is not on the last night",
        )


def main() -> None:
    test_blade_cell()
    test_blade_ladder()
    test_armor_rating()
    test_armor_breaks()
    test_armor_pickup()
    test_shield_blocks_what_it_faces()
    test_shield_breaks()
    test_shop_ladders()
    print("ok")


if __name__ == "__main__":
    main()
