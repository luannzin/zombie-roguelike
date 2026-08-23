"""Medicine: two cells, and the only way health ever comes back.

Run:  python tests/test_medical.py   (from server/)

Four things about the medical belt have no symptom you would see while
playing, and every one of them is the kind of bug you only find out about in
front of something:

  * IT IS NOT CARGO. `first_aid` and `morphine` were ordinary loot with a price
    on them until death started ending runs. They still sit in `loot.ITEMS`
    with their old keys and their old art, and the ONLY things that moved were
    `pocket` and `value` — so a kit that quietly regained a price would go back
    to competing with a gold ring for a pocket cell, and a quota would start
    counting medicine as loot. Neither is visible; both change the whole
    economy.
  * THE CELL IS SPENT ON THE LAST FRAME AND ONLY THERE. An interrupted heal
    costs the seconds and keeps the item, because what interrupts a heal is the
    thing you were healing because of — taking the kit as well is punishing the
    player twice for one mistake. Spending it on the FIRST frame instead looks
    identical right up until somebody gets hit.
  * IT REFUSES RATHER THAN SWAPPING. Two kits are a QUANTITY, not alternatives,
    so a third pickup must leave the drop on the ground. A cell that traded
    would silently bin the resource the player bent down to stockpile.
  * THE TWO KITS TRADE ON DIFFERENT AXES. They are deliberately not a ladder —
    if one ever heals more AND faster AND lighter than the other, the second
    cell stops being a decision and the design collapses into one item twice.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import loot, medical, store  # noqa: E402
from app.config import client_config  # noqa: E402
from app.entities import Player  # noqa: E402
from app.room import Room  # noqa: E402

TICK = 1.0 / 30.0


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _room() -> tuple[Room, Player]:
    room = Room(code="MED", seed=11)
    player = Player(id="p1", name="Ana", color="#fff")
    player.x, player.y = room.pick_spawn()
    room.players[player.id] = player
    return room, player


def _run_use(room: Room, player: Player, seconds: float) -> None:
    """Tick just the heal channel, the way `step_players` does mid-use."""
    steps = int(round(seconds / TICK))
    for _ in range(steps):
        if player.using is None:
            return
        room._step_use(player, TICK)


# --- medicine is not cargo ---------------------------------------------------


def test_not_cargo() -> None:
    for kit in medical.KITS:
        item = next((i for i in loot.ITEMS if i.key == kit.key), None)
        check(item is not None, f"{kit.key} is not in the loot catalog")
        assert item is not None
        check(
            item.pocket == medical.POCKET,
            f"{kit.key} routes to {item.pocket!r}, not the medical cells",
        )
        # THE LOAD-BEARING ZERO. `Rift.feed` counts catalog value toward the
        # quota, `store.price_of` reads it, and the pocket's weight bar sums
        # it — a price here puts medicine back in the economy in three places
        # at once, none of which announces itself.
        check(item.value == 0, f"{kit.key} has a value of {item.value}; medicine is unsellable")
        # The weight is mirrored in two tables and they must not drift: the
        # catalog row is what a client sums, `MedicalDef` is what the server
        # does.
        check(
            item.weight == kit.weight,
            f"{kit.key} weighs {item.weight} in the catalog and {kit.weight} in medical.py",
        )


def test_the_merchant_sells_it_and_the_player_cannot() -> None:
    """Medicine flows ONE WAY: gold buys it, it never turns back into gold.

    Both halves matter and they are easy to confuse. The merchant stocking kits
    is deliberate — it is the only thing on his shelf that is spent rather than
    owned, which is what gives him something to sell a party who already own
    every gun. What must never come back is the return trip: a kit with a
    payout is a kit somebody hoards to sell, which is exactly the dead decision
    the whole redesign removed.
    """
    for kit in medical.KITS:
        check(kit.key in store.SELLABLE, f"the merchant should stock {kit.key}")
        # Priced off its own heal, NOT off the catalog column — medicine's
        # catalog value is zero, so a price that came from there would be free.
        check(store.price_of(kit.key) > 0, f"{kit.key} must cost real gold")
        # AND THE RETURN TRIP IS SHUT. `value == 0` is what closes it: the
        # payout at extraction sums catalog value, so a kit in the bag pays
        # nothing. Asserted here as the sentence it actually means.
        item = next(i for i in loot.ITEMS if i.key == kit.key)
        check(item.value == 0, f"{kit.key} must be worth nothing at the pad")

    # The big kit is anchored to the cheapest firearm on the shelf, and the
    # small one is cheaper because it does less. Derived, so rebalancing a
    # pistol moves medicine with it.
    big = max(medical.KITS, key=lambda k: k.heal)
    small = min(medical.KITS, key=lambda k: k.heal)
    check(
        store.price_of(big.key) > store.price_of(small.key),
        "the bigger heal costs more; the ladder is priced off heal, not off a guess",
    )


def test_medicine_is_not_gated_like_a_power_curve() -> None:
    """Both kits are on the shelf from night one.

    They are alternatives, not rungs — which is better depends on whether you
    are being chased. Left to `_unlock_day`'s arithmetic they would be sorted
    by a zero-value tiebreak on the KEY, and "morphine" losing an alphabetical
    coin flip would have hidden the panic heal behind night five. A gate
    nobody designed, expressing nothing.
    """
    table = store.STOCK_UNLOCK
    for kit in medical.KITS:
        check(
            table.get(kit.key) == 1,
            f"{kit.key} unlocks on night {table.get(kit.key)}, not night one",
        )


def test_kits_are_not_a_ladder() -> None:
    """No kit may dominate another on every axis at once."""
    for a in medical.KITS:
        for b in medical.KITS:
            if a.key == b.key:
                continue
            dominates = a.heal >= b.heal and a.use_time <= b.use_time and a.weight <= b.weight
            check(
                not dominates,
                f"{a.key} is at least as good as {b.key} on heal, time AND weight — "
                "the second cell has stopped being a decision",
            )


# --- the channel -------------------------------------------------------------


def test_heal_takes_time_and_then_lands() -> None:
    room, player = _room()
    kit = medical.BY_KEY["first_aid"]
    check(player.medical.add("first_aid"), "an empty belt takes a kit")
    # Hurt enough that the whole kit fits under the ceiling, so this test is
    # about the CHANNEL rather than about the cap — `test_heal_caps_at_max`
    # owns that.
    player.hp = max(1, player.max_hp - kit.heal)
    start_hp = player.hp

    room.use_medical(player.id, 0)
    check(player.using is not None, "pressing the cell opens the channel")
    assert player.using is not None
    check(player.using.total == kit.use_time, "the channel runs for the kit's authored time")

    # HALFWAY THROUGH, NOTHING HAS HAPPENED YET. Not the health, and — the
    # important half — not the cell either.
    _run_use(room, player, kit.use_time * 0.5)
    check(player.using is not None, "the channel is still running at the halfway mark")
    check(player.hp == start_hp, "health does not trickle in; it lands at the end")
    check(player.medical.peek(0) == "first_aid", "the cell is not spent until the last frame")

    _run_use(room, player, kit.use_time)
    check(player.using is None, "the channel closes")
    check(player.hp == start_hp + kit.heal, f"the kit put back {kit.heal}")
    check(player.medical.peek(0) is None, "and the cell is empty")
    check(len(room.heal_events) == 1, "one heal event, for the juice")
    check(room.heal_events[0]["hp"] == kit.heal, "the event carries what actually went in")


def test_heal_caps_at_max() -> None:
    room, player = _room()
    player.medical.add("first_aid")
    # One point short of full, so the kit has far more to give than there is
    # room for.
    player.hp = player.max_hp - 1
    room.use_medical(player.id, 0)
    _run_use(room, player, medical.BY_KEY["first_aid"].use_time + TICK)
    check(player.hp == player.max_hp, "a heal cannot overfill the bar")
    # The EVENT carries what was actually restored, not what the kit is worth —
    # a "+55" floating off somebody who gained 1 is a lie the player can read.
    check(room.heal_events[0]["hp"] == 1, "the float reports the real gain")


def test_full_health_is_refused() -> None:
    room, player = _room()
    player.medical.add("morphine")
    player.hp = player.max_hp
    room.use_medical(player.id, 0)
    check(player.using is None, "a heal at full health does not start")
    check(player.medical.peek(0) == "morphine", "and costs nothing")


def test_empty_cell_is_refused() -> None:
    room, player = _room()
    player.hp = 10
    room.use_medical(player.id, 0)
    check(player.using is None, "an empty cell does nothing")
    # And so does a cell that is not there at all. The client sends an index.
    for bad in (-1, medical.MEDICAL_SLOTS, 99):
        room.use_medical(player.id, bad)
        check(player.using is None, f"cell {bad} does not exist and must not open a channel")


def test_a_blow_costs_the_seconds_and_keeps_the_kit() -> None:
    """THE ONE THAT MATTERS. An interrupted heal must not eat the item."""
    room, player = _room()
    player.hp = 40
    player.medical.add("first_aid")

    room.use_medical(player.id, 0)
    _run_use(room, player, medical.BY_KEY["first_aid"].use_time * 0.6)
    check(player.using is not None, "still healing when the blow arrives")

    before = player.hp
    room.damage_player(player, 5, None)
    check(player.using is None, "a blow closes the channel")
    check(player.medical.peek(0) == "first_aid", "the kit is still on the belt")
    check(player.hp < before, "the blow landed")
    check(player.hp <= 40, "and no health was restored — only the seconds were spent")

    # And the belt still works afterwards. An interrupted channel that left
    # something set would make the next press a no-op, which reads as the game
    # ignoring you at the worst possible moment.
    room.use_medical(player.id, 0)
    check(player.using is not None, "the kit can be spent again after an interruption")


def test_the_body_is_a_puppet() -> None:
    room, player = _room()
    player.hp = 50
    player.medical.add("first_aid")
    room.use_medical(player.id, 0)
    player.vx, player.vy = 5.0, 5.0
    room._step_use(player, TICK)
    check(player.vx == 0.0 and player.vy == 0.0, "a healing body does not move")


# --- the two cells -----------------------------------------------------------


def test_cells_refuse_rather_than_swap() -> None:
    belt = medical.Medical()
    check(belt.add("first_aid"), "first cell takes one")
    check(belt.add("morphine"), "second cell takes one")
    check(belt.full(), "both cells are full")
    check(not belt.add("first_aid"), "a third kit is REFUSED, not swapped in")
    check(
        belt.slots == ["first_aid", "morphine"],
        "and the refusal did not disturb what was already there",
    )
    check(not belt.add("gold_ring"), "a non-kit never enters the medical belt")


def test_weight_costs_the_walk() -> None:
    _unused, player = _room()
    before = player.carry_weight
    player.medical.add("first_aid")
    check(
        player.carry_weight > before,
        "medicine takes no pocket CELL and does take pocket SPEED — that is the "
        "greed trade that replaced the sell price",
    )
    # But it must not eat a bag slot, which is the whole point of the move.
    check(
        all(slot is None for slot in player.inventory.slots),
        "a kit does not occupy a pocket slot",
    )
    # And the bag itself refuses to take one, which is the rule underneath:
    # `Inventory.add` only accepts `pocket == "bag"`.
    check(
        player.inventory.add("first_aid") is None,
        "the pocket must refuse medicine outright, not merely be bypassed",
    )


# --- the wire ----------------------------------------------------------------


def test_config_ships_what_the_client_draws() -> None:
    cfg = client_config()
    check(cfg["medicalSlots"] == medical.MEDICAL_SLOTS, "the cell count ships")
    for kit in medical.KITS:
        row = cfg["medical"].get(kit.key)
        check(row is not None, f"{kit.key} is missing from welcome.config")
        assert row is not None
        # All three, because the client draws all three: the duration drives
        # the ring, the heal is the cell's label, and the weight is summed
        # into the client's own `moveWeight`.
        check(row["heal"] == kit.heal, f"{kit.key} heal drifted")
        check(row["useTime"] == kit.use_time, f"{kit.key} useTime drifted")
        check(row["weight"] == kit.weight, f"{kit.key} weight drifted")


def test_roster_and_tick_rows() -> None:
    _unused, player = _room()
    player.medical.add("morphine")
    check(player.to_payload()["med"] == ["morphine", None], "the cells ride the roster")
    # `use` is omitted unless a heal is actually running — it is a per-tick
    # field on a row every player pays for thirty times a second.
    check("use" not in player.snapshot_payload(), "a resting body carries no heal field")


def main() -> None:
    test_not_cargo()
    test_the_merchant_sells_it_and_the_player_cannot()
    test_medicine_is_not_gated_like_a_power_curve()
    test_kits_are_not_a_ladder()
    test_heal_takes_time_and_then_lands()
    test_heal_caps_at_max()
    test_full_health_is_refused()
    test_empty_cell_is_refused()
    test_a_blow_costs_the_seconds_and_keeps_the_kit()
    test_the_body_is_a_puppet()
    test_cells_refuse_rather_than_swap()
    test_weight_costs_the_walk()
    test_config_ships_what_the_client_draws()
    test_roster_and_tick_rows()
    print("ok")


if __name__ == "__main__":
    main()
