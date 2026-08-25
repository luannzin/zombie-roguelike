"""Carrying a body out: the pack, the escort, the platform, and the corridor.

Run:  python tests/test_rescue.py   (from server/)

This whole feature is a chain of joins where each link is invisible from
inside the game if it quietly stops working, and every one of them looks like
bad luck rather than like a bug. A rescue that silently did nothing reads as
"the platform does not revive people"; a pack anybody could take reads as "my
mate stole my loot"; an exit that turned over early reads as "the game kicked
me out of the map". Nobody reports any of those as defects.

What it pins, in the order a night hits them:

  * THE TRADE IS ATOMIC. Picking a body up puts the bag down, always, on the
    same frame, and the bag keeps what was in it. Either half happening alone
    is either a free rescue or a bag dropped for nothing.
  * A CARRIER CANNOT TAKE CARGO, and can still take everything else. The
    refusal is the POCKET and not the player: rounds, plate, medicine and
    weapons all still work, because what a rescue costs is the night's takings
    rather than the ability to survive the walk back.
  * THE PACK IS OWNED. Only its owner may take it back, and only with empty
    arms. A pack the party could pool is a rescue nobody pays for.
  * THE PLATFORM IS WHAT REVIVES, not the player who carried them. Laying a
    body on the deck does nothing on its own; the pickup call is what stands
    them up, at half health, on the same press that banks the haul.
  * THE ZONE WAITS FOR EVERYBODY. The first player across the corridor used to
    end the night for the party, which made "sprint for the exit and leave
    your friends" the optimal line in a co-op extraction game.
  * A CARRIER WHO GOES DOWN LETS GO. Four unrelated places can end a carry and
    none of them knows this mechanic exists, which is why the tick repairs the
    pairing instead of four call sites remembering to.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import mapgen, protocol, rift, zones  # noqa: E402
from app.config import (  # noqa: E402
    CARRY_BODY_SCALE,
    DT,
    PLAYER_HALF_HEIGHT,
    REVIVE_HP_SHARE,
    TILE_SIZE,
)
from app.entities import Player  # noqa: E402
from app.loot import Drop  # noqa: E402
from app.pathing import Navigator  # noqa: E402
from app.room import Room  # noqa: E402


def check(label: str, ok: bool) -> None:
    print(f"  {label}: {'ok' if ok else 'FAILED'}")
    if not ok:
        raise AssertionError(label)


def _room() -> tuple[Room, Player, Player]:
    """A real forest with two players standing on the same walkable tile.

    The world has to be a FOREST and not the camp a bare `Room` opens with:
    the corridor tests carve an exit through it (`_open_egress`), and a camp
    has no edge for one.
    """
    room = Room(code="RESQ", seed=11)
    room.phase = protocol.PHASE_PLAYING
    room.zone = zones.forest(1)
    room.world = mapgen.build_forest(day=1, seed=11)
    room.navigator = Navigator(room.world)
    room._rebuild_spawns()
    room.arriving = False
    ana = room.add_player(None, "Ana")
    beto = room.add_player(None, "Beto")
    ana.x, ana.y = room.pick_spawn()
    beto.x, beto.y = ana.x, ana.y
    for body in (ana, beto):
        body.alive = True
        body.hp = body.max_hp
    return room, ana, beto


def down(player: Player) -> None:
    """Put a body on the floor the way a hostile zone does."""
    player.hp = 0
    player.alive = False
    player.downed = True


def drop_on(room: Room, player: Player, key: str) -> str:
    """One drop EXACTLY at this player's feet. Returns its id.

    `Room._drop_at_feet` scatters onto nearby walkable tiles and can land a
    step past `LOOT_COLLECT_DIST`, which would make these checks a coin flip on
    the map seed. What is being tested here is the CONTAINER rule, not the
    reach — the reach has its own tests.
    """
    drop_id = room._next_drop_id()
    room.drops[drop_id] = Drop(
        id=drop_id, key=key, x=player.x, y=player.y + PLAYER_HALF_HEIGHT
    )
    return drop_id


# --- the trade ---------------------------------------------------------------


def test_pack_for_body() -> None:
    print("the trade")
    room, ana, beto = _room()
    ana.inventory.add("broken_toy")
    ana.inventory.add("broken_toy")
    carried_before = ana.inventory.weight
    check("Ana starts with a bag and something in it", ana.has_pack and carried_before > 0)

    down(beto)
    room.carry_body(ana.id)
    check("she has him", ana.carrying == beto.id and beto.carried_by == ana.id)
    # BOTH HALVES OR NEITHER. A version where the body came up without the bag
    # going down would be a free rescue, and one where the bag went down
    # without the body would be a bag dropped for nothing.
    check("and the bag is off her back", not ana.has_pack)
    check("her pocket is empty", ana.inventory.weight == 0)
    packs = list(room.packs.values())
    check("there is exactly one pack on the ground", len(packs) == 1)
    check("it is hers", packs[0].owner == ana.id)
    check("and it still holds the night", packs[0].count == 2)

    # THE WALK. A flat multiplier rather than a weight, because the bag has
    # just been dropped — put it on the weight curve and the player would be at
    # their lightest exactly when they are meant to be at their slowest.
    room.sync_carry(ana)
    check("carrying costs speed", ana.carry_speed == CARRY_BODY_SCALE)
    room.sync_carry(beto)
    check("and nobody else's", beto.carry_speed == 1.0)


def test_carrier_cannot_take_cargo() -> None:
    print("a carrier's pockets")
    room, ana, beto = _room()
    down(beto)
    room.carry_body(ana.id)

    # THE REFUSAL IS THE POCKET, NOT THE PLAYER. Everything below is in one of
    # the other four containers, and every one of them still works — what a
    # rescue costs is the NIGHT'S TAKINGS, not the ability to survive the walk
    # back. Getting this wrong in the generous direction is invisible (loot
    # quietly appears in a bag that is not there); getting it wrong in the
    # strict direction makes carrying a teammate a death sentence.
    drop_id = drop_on(room, ana, "broken_toy")
    room.collect_loot(ana.id, drop_id)
    check("cargo is refused", drop_id in room.drops)
    check("and nothing went into the phantom bag", ana.inventory.weight == 0)

    kit = drop_on(room, ana, "morphine")
    room.collect_loot(ana.id, kit)
    check("medicine still goes on the belt", kit not in room.drops)

    plate = drop_on(room, ana, "head_leather")
    room.collect_loot(ana.id, plate)
    check("armour still goes on the body", plate not in room.drops)

    axe = drop_on(room, ana, "axe")
    room.collect_loot(ana.id, axe)
    check("and steel still goes on the belt", ana.hotbar.blade == "axe")


# --- the pack ----------------------------------------------------------------


def test_pack_is_owned() -> None:
    print("the pack")
    room, ana, beto = _room()
    ana.inventory.add("broken_toy")
    down(beto)
    room.carry_body(ana.id)
    pack = next(iter(room.packs.values()))

    # A PACK THE PARTY COULD POOL IS A RESCUE NOBODY PAYS FOR: one player
    # carries the body, another scoops the bag, and the trade this whole
    # mechanic is built on never happens.
    carla = room.add_player(None, "Carla")
    carla.x, carla.y = ana.x, ana.y
    room.take_pack(carla.id)
    check("somebody else may not take it", pack.id in room.packs)
    check("and it did not land in their pocket", carla.inventory.weight == 0)

    # FULL ARMS MAY NOT EITHER. You put it down to carry somebody, so getting
    # it back means setting them down first — which is the decision, not a
    # guard around it.
    room.take_pack(ana.id)
    check("nor may the owner with full arms", pack.id in room.packs)

    room.carry_body(ana.id)
    check("she sets him down", ana.carrying is None and beto.carried_by is None)
    check("and he is still on the floor", beto.downed)
    check("the bag did NOT come back on its own", not ana.has_pack)

    room.take_pack(ana.id)
    check("now she can take it", pack.id not in room.packs)
    check("the bag is back on", ana.has_pack)
    check("with the night still in it", ana.inventory.weight > 0)


def test_spent_pads_empty_the_pack() -> None:
    print("a pack nobody can spend")
    room, ana, beto = _room()
    ana.inventory.add("broken_toy")
    down(beto)
    room.carry_body(ana.id)
    pack = next(iter(room.packs.values()))

    room.rifts = [
        rift.Rift(
            tx=0, ty=0, x=200.0, y=200.0,
            console_x=200.0, console_y=232.0,
            torch_x=180.0, torch_y=232.0,
            deck_x=200.0, deck_y=216.0,
            need=10,
        )
    ]
    room.rifts[0].state = rift.OPEN
    room._strip_spent_packs()
    check("while a pad is still up, the night waits in the bag", pack.count == 1)

    # AND WHEN THERE IS NOTHING LEFT TO LOAD IT INTO, the promise cannot be
    # kept and stops being made. The PACK stays: a player who spent their bag
    # on a rescue and could never pick anything up again for the rest of the
    # night would be a softlock wearing a consequence's clothes.
    room.rifts[0].state = rift.SPENT
    room._strip_spent_packs()
    check("once every pad is spent, the items go", pack.count == 0)
    check("and the bag itself does not", pack.id in room.packs)
    room.carry_body(ana.id)  # set him down; the arms have to be empty
    room.take_pack(ana.id)
    check("so she can still get it back, empty", ana.has_pack)
    check("and it is genuinely empty", ana.inventory.weight == 0)


# --- the platform ------------------------------------------------------------


def test_platform_revives() -> None:
    print("the platform")
    room, ana, beto = _room()
    pad = rift.Rift(
        tx=0, ty=0, x=200.0, y=200.0,
        console_x=200.0, console_y=232.0,
        torch_x=180.0, torch_y=232.0,
        deck_x=200.0, deck_y=216.0,
        need=10,
    )
    pad.state = rift.OPEN
    pad.fed = 10
    room.rifts = [pad]

    down(beto)
    beto.x = pad.deck_x
    beto.y = pad.deck_y - PLAYER_HALF_HEIGHT

    # LAYING A BODY ON THE DECK DOES NOTHING ON ITS OWN. It is cargo, lying
    # where the loot lies, waiting for the same flight — and that is the whole
    # design: what turns it back into a person is somebody deciding the night
    # is over, which is the same press that banks the haul.
    room.step_rift(DT)
    check("a body on the deck is not revived by sitting there", beto.downed)

    ana.x = pad.console_x
    ana.y = pad.console_y - PLAYER_HALF_HEIGHT
    room.activate_rift(ana.id)
    check("calling the pickup stands him up", not beto.downed and beto.alive)
    # HALF, and that is design rather than tuning: full health would make the
    # platform a free reset and the escort a formality.
    check(
        f"at half health ({beto.hp} of {beto.max_hp})",
        beto.hp == max(1, int(beto.max_hp * REVIVE_HP_SHARE)),
    )
    check("and the pad was called", pad.close_at is not None)


def test_revive_is_not_a_heal() -> None:
    print("revive is its own door")
    room, _ana, beto = _room()
    down(beto)
    # `heal_player` refuses a downed body outright, because a heal that stood
    # somebody up would quietly delete permadeath — the thing every other
    # system in this game is balanced against.
    check("medicine cannot stand a body up", room.heal_player(beto, 90) == 0)
    check("it is still down", beto.downed)
    check("the platform's door can", room.revive_player(beto))
    check("and it refuses a body that is already up", not room.revive_player(beto))


# --- letting go --------------------------------------------------------------


def test_carrier_lets_go() -> None:
    print("letting go")
    room, ana, beto = _room()
    down(beto)
    room.carry_body(ana.id)

    # FOUR UNRELATED PLACES CAN END A CARRY — a death, a downing, a disconnect,
    # a walk out of the zone — and not one of them has any business knowing
    # this mechanic exists. So the tick checks that both halves still agree
    # about each other rather than four call sites remembering to release.
    down(ana)
    room._step_carried()
    check("a carrier who goes down lets go", ana.carrying is None)
    check("and the body is free to be picked up again", beto.carried_by is None)


def test_carried_body_follows() -> None:
    print("the escort")
    room, ana, beto = _room()
    down(beto)
    room.carry_body(ana.id)
    ana.x += TILE_SIZE * 3
    ana.y += TILE_SIZE * 2
    room._step_carried()
    check("the body is where the arms are", beto.x == ana.x and beto.y == ana.y)


# --- the corridor ------------------------------------------------------------


def test_exit_waits_for_everybody() -> None:
    print("the corridor")
    room, ana, beto = _room()
    room._open_egress()
    gate = room.egress
    assert gate is not None
    room.offer_extract_quest()

    def walk_out(player: Player) -> None:
        player.x, player.y = gate.mouth_x, gate.mouth_y - PLAYER_HALF_HEIGHT
        for _ in range(80):
            player.x -= gate.dx * 4.0
            player.y -= gate.dy * 4.0
            room._tick_exit_quest()
            if player.exited:
                return

    walk_out(ana)
    check("the first one out is marked", ana.exited)
    # THE RULE THIS WHOLE TEST EXISTS FOR. One person walking into the dark
    # used to take the map away from everybody else mid-fight, mid-pour,
    # mid-anything — which made "sprint for the exit and leave your friends
    # standing there" the optimal line in a co-op extraction game.
    check("but the night does NOT turn over", not room._pending_return)

    # AND THEY ARE OUT OF THE NIGHT WHILE THEY WAIT. A body that could still be
    # killed in the corridor would make being first out the most dangerous
    # thing anybody could do, which is the opposite of what crossing means.
    before = ana.hp
    room.damage_player(ana, 40, None)
    check("nothing can hurt them while they wait", ana.hp == before)

    walk_out(beto)
    check("once everybody is out, it does", room._pending_return)


def test_a_body_on_the_floor_does_not_hold_the_door() -> None:
    print("leaving one behind")
    room, ana, beto = _room()
    room._open_egress()
    gate = room.egress
    assert gate is not None
    room.offer_extract_quest()

    # A body on the floor cannot walk to a corridor, so counting it would mean
    # a party could never leave with a casualty — and the whole point of
    # `carry_body` is that they can, either by putting them on a platform or by
    # walking out one short. `_check_wipe` answers the case where nobody is up.
    down(beto)
    ana.x, ana.y = gate.mouth_x, gate.mouth_y - PLAYER_HALF_HEIGHT
    for _ in range(80):
        ana.x -= gate.dx * 4.0
        ana.y -= gate.dy * 4.0
        room._tick_exit_quest()
        if room._pending_return:
            break
    check("the last one standing can still leave", room._pending_return)


def test_walking_out_sets_a_body_down() -> None:
    print("walking out mid-carry")
    room, ana, beto = _room()
    room._open_egress()
    gate = room.egress
    assert gate is not None
    room.offer_extract_quest()
    down(beto)
    room.carry_body(ana.id)

    ana.x, ana.y = gate.mouth_x, gate.mouth_y - PLAYER_HALF_HEIGHT
    for _ in range(80):
        ana.x -= gate.dx * 4.0
        ana.y -= gate.dy * 4.0
        room._tick_exit_quest()
        if ana.exited:
            break
    # A pair glued together where one half has left the night is a body being
    # dragged by a ghost. It is not cruelty either: the carried body is downed,
    # so it was never in the count the corridor is waiting on.
    check("she is out", ana.exited)
    check("and she is not still holding him", ana.carrying is None)
    check("he is on the floor where she left him", beto.downed and beto.carried_by is None)


def main() -> None:
    test_pack_for_body()
    test_carrier_cannot_take_cargo()
    test_pack_is_owned()
    test_spent_pads_empty_the_pack()
    test_platform_revives()
    test_revive_is_not_a_heal()
    test_carrier_lets_go()
    test_carried_body_follows()
    test_exit_waits_for_everybody()
    test_a_body_on_the_floor_does_not_hold_the_door()
    test_walking_out_sets_a_body_down()
    print("ok")


if __name__ == "__main__":
    main()
