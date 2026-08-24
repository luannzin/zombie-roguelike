"""ULTIMATES AND THE SYNERGY THEY HANG OFF.

Five things here have no symptom you would ever see while playing, and every
one of them is the kind of failure a player would read as the game being
badly designed rather than broken:

  * A REQUIREMENT THAT SILENTLY PASSES. A tag test that answered "yes" for
    every loadout would make every ultimate unlock the moment its weapon was
    picked up, and the whole feature — "I need the right armour for this" —
    would simply not exist. Nobody reports an ability that is too easy to get.
  * A REQUIREMENT THAT SILENTLY FAILS. The mirror, and worse: an ultimate that
    can never unlock looks exactly like one the player has not found the
    armour for yet. They would go and buy the set, press R, get nothing, and
    conclude the key is broken.
  * A BAR THAT FILLS OFF THE WRONG THING. Charge is per ULTIMATE and per
    SOURCE. If a katana's bar filled while its owner shot a Deagle, the
    correct play would be to charge with whatever is convenient and fire with
    whatever is strongest — which is the opposite of what this system is for,
    and it would look like generosity rather than like a bug.
  * A WINDOW THAT OUTLIVES ITS WEAPON. Six seconds of free ammunition that
    followed a player onto their pistol is an exploit whose only symptom is
    that somebody had a very good night.
  * THE ARCHITECTURE ITSELF. "Adding an ultimate is a data row" is a claim,
    and a claim in a docstring rots. It is asserted here against a row this
    file builds and drives through the unmodified room.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import armor, ultimates, weapons, zones  # noqa: E402
from app.config import DT  # noqa: E402
from app.entities import InputCmd, Player  # noqa: E402
from app.room import Room  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        return
    FAILURES.append(message)
    print(f"  FAIL  {message}")


def _room() -> tuple[Room, Player]:
    """A room in a HOSTILE zone, because R is refused everywhere else."""
    room = Room(code="ULTS", seed=11)
    # The camp is where a room opens and an ultimate is illegal there on
    # purpose — see `Room.use_ultimate`. Every test below is about the forest.
    room.zone = zones.forest(1)
    player = Player(id="p1", name="Ana", color="#fff")
    player.x, player.y = room.pick_spawn()
    room.players[player.id] = player
    return room, player


def _wear(player: Player, material: str, count: int) -> None:
    """Put `count` pieces of one material on, top down."""
    player.armor.worn.clear()
    for slot in armor.SLOTS[:count]:
        player.armor.equip(f"{slot}_{material}")


def _hold(player: Player, key: str) -> weapons.WeaponDef:
    """Put `key` in the hand, whichever kind of cell it belongs in."""
    player.hotbar.add(key)
    for index, cell in enumerate(player.hotbar.slots):
        if cell == key:
            player.hotbar.held = index
            break
    weapon = player.hotbar.equipped()
    assert weapon is not None and weapon.key == key, key
    return weapon


# --- the catalog itself ------------------------------------------------------


def test_catalog() -> None:
    """Every claim `ultimates.py` makes about its own shape.

    These are import-time invariants in the module and they are re-asserted
    here for one reason: the module raises on the ones it can see, and it
    cannot see the ones that involve `weapons.py`. An ultimate whose weapon
    does not exist is a panel that can never appear.
    """
    for row in ultimates.ULTIMATES:
        check(row.weapon in weapons.BY_KEY, f"{row.key} belongs to a weapon that exists")
        blocks = [row.volley, row.empower, row.aura]
        check(
            sum(1 for block in blocks if block is not None) == 1,
            f"{row.key} carries exactly one effect block",
        )
        check(bool(row.requires), f"{row.key} requires something")
        check(row.charge_full > 0, f"{row.key} has a bar to fill")
        for tag in row.requires:
            check(tag in ultimates.TAG_BY_KEY, f"{row.key} requires a tag the HUD can name")

    # EVERY ARMOUR TAG THAT GATES AN ULTIMATE IS REACHABLE, and it is checked
    # against the MATERIALS rather than against the tag list — a tag can be
    # declared and still be on nothing.
    worn = {tag for material in armor.MATERIALS for tag in material.tags}
    for row in ultimates.ULTIMATES:
        for tag in row.requires:
            if ultimates.TAG_BY_KEY[tag].source != ultimates.SOURCE_ARMOR:
                continue
            check(tag in worn, f"{row.key} needs '{tag}', which some material has")

    # AND NO RUNG UNLOCKS TWO. This is the balance claim the whole ladder rests
    # on: if one material carried the tags for two ultimates it would be
    # strictly the best armour in the game for two builds, and "wear the most
    # expensive thing you can afford" would come straight back.
    for material in armor.MATERIALS:
        gated = [
            row.key
            for row in ultimates.ULTIMATES
            if any(tag in material.tags for tag in row.requires)
        ]
        check(len(gated) <= 1, f"{material.key} gates {gated} — no rung may unlock two")


# --- is it unlocked ----------------------------------------------------------


def test_requirements() -> None:
    """The gap, and it has to be a real gap in both directions."""
    room, player = _room()
    katana = _hold(player, "katana")
    row = ultimates.BY_WEAPON["katana"]

    # BARE: the weapon's own tag is met and the armour's is not. That split is
    # the whole reason `TagDef.source` exists.
    gap = ultimates.missing_tags(row, katana.tags, player.armor.tag_pieces())
    check(gap == ("ninja",), f"a naked swordsman is missing only the set, got {gap}")

    # A PARTIAL SET IS STILL A GAP. One under the threshold has to fail, or
    # "wear the set" would mean "own one glove".
    _wear(player, "leather", ultimates.SET_PIECES - 1)
    check(
        ultimates.missing_tags(row, katana.tags, player.armor.tag_pieces()) == ("ninja",),
        f"{ultimates.SET_PIECES - 1} pieces is not the set",
    )
    _wear(player, "leather", ultimates.SET_PIECES)
    check(
        ultimates.unlocked(row, katana.tags, player.armor.tag_pieces()),
        f"{ultimates.SET_PIECES} pieces is",
    )

    # THE WRONG SET DOES NOT DO. The best armour in the game unlocks the
    # marksman's and locks the assassin's, which is the trade the whole
    # feature is built on.
    _wear(player, "kevlar", len(armor.SLOTS))
    check(
        ultimates.missing_tags(row, katana.tags, player.armor.tag_pieces()) == ("ninja",),
        "a full kevlar suit does NOT unlock the blade's ultimate",
    )

    # AND A BROKEN PIECE STOPS COUNTING. It is off the body — `tag_pieces`
    # skips a spent plate — so a set that failed mid-fight takes the ultimate
    # with it rather than leaving a phantom third piece behind.
    _wear(player, "leather", ultimates.SET_PIECES)
    piece = player.armor.get(armor.SLOTS[0])
    assert piece is not None
    piece.hp = 0
    check(
        not ultimates.unlocked(row, katana.tags, player.armor.tag_pieces()),
        "a spent plate stops counting toward its set",
    )


# --- the bar -----------------------------------------------------------------


def test_charge() -> None:
    """Per ultimate, per source, and only once unlocked."""
    room, player = _room()
    katana = _hold(player, "katana")
    row = ultimates.BY_WEAPON["katana"]

    # LOCKED MEANS THE BAR DOES NOT MOVE. This is what makes the state machine
    # the player is shown — locked, charging, ready — the one the server runs.
    room._charge_ult(player, katana, ultimates.CHARGE_DAMAGE, 5000)
    check(
        player.ult_charge.get(row.key, 0.0) == 0.0,
        "a locked ultimate does not charge at all",
    )

    _wear(player, "leather", ultimates.SET_PIECES)
    room._charge_ult(player, katana, ultimates.CHARGE_DAMAGE, 40)
    check(player.ult_charge.get(row.key) == 40, "unlocked, damage fills it")

    # THE WRONG SOURCE IS WORTH NOTHING. A blade's bar is melee damage and a
    # medic's is healing; if either could be filled by the other, the support
    # build would be "carry the healer and play normally".
    before = player.ult_charge[row.key]
    room._charge_ult(player, katana, ultimates.CHARGE_HEAL, 500)
    check(player.ult_charge[row.key] == before, "healing does not charge a blade")

    # AND IT IS CAPPED. A bar that overfilled would bank a second ultimate.
    room._charge_ult(player, katana, ultimates.CHARGE_DAMAGE, 99999)
    check(
        player.ult_charge[row.key] == row.charge_full,
        f"the bar stops at {row.charge_full}, got {player.ult_charge[row.key]}",
    )

    # THE BARS ARE SEPARATE. Charging the katana leaves every other one alone,
    # which is what makes the belt a set of promises rather than one meter.
    check(
        "extreme_shot" not in player.ult_charge,
        "the Deagle's bar did not move while the katana filled",
    )


# --- firing it ---------------------------------------------------------------


def test_volley() -> None:
    """The katana's: a crescent leaves, and it belongs to whoever threw it."""
    room, player = _room()
    katana = _hold(player, "katana")
    row = ultimates.BY_WEAPON["katana"]
    _wear(player, "leather", ultimates.SET_PIECES)

    # NOT READY IS A REFUSAL AND IT COSTS NOTHING.
    room.use_ultimate(player.id)
    check(not room.ult_shots, "a half-charged bar throws nothing")
    check(not room.ult_events, "and announces nothing")

    room._charge_ult(player, katana, ultimates.CHARGE_DAMAGE, row.charge_full)
    player.aim_x, player.aim_y = 1.0, 0.0
    room.use_ultimate(player.id)

    check(len(room.ult_shots) == row.volley.count, "the volley left")
    check(player.ult_charge[row.key] == 0.0, "and it spent the whole bar")
    check(len(room.ult_events) == 1, "and said so, once")
    shot = room.ult_shots[0]
    check(shot.owner == player.id, "the crescent knows whose it is")
    check(shot.look == row.volley.look, "and which picture to be drawn as")
    check(shot.damage == row.volley.damage, "and what it is worth")

    # THE OWNER IS WHY THE KILL PAYS. Without it an ultimate would be the one
    # way in the game to clear a pack for no xp — a button that makes the run
    # worse, which is the exact opposite of what it is for.
    from app.enemies import ZOMBIE  # noqa: PLC0415

    victim = room.spawn_enemy(ZOMBIE, shot.x + 40.0, shot.y)
    victim.hp = 1
    before = player.xp
    for _ in range(20):
        room.step_ult_shots(DT)
        if victim.id not in room.enemies:
            break
    check(victim.id not in room.enemies, "the crescent reached it")
    check(player.xp > before, f"and the thrower was paid for it ({before} -> {player.xp})")

    # A SECOND PRESS IS REFUSED. The bar is empty and pressing R again must not
    # produce a free one.
    room.ult_shots.clear()
    room.use_ultimate(player.id)
    check(not room.ult_shots, "an empty bar throws nothing")


def test_window() -> None:
    """The minigun's: six seconds of free ammunition, and it stays on the minigun."""
    room, player = _room()
    minigun = _hold(player, "minigun")
    row = ultimates.BY_WEAPON["minigun"]
    _wear(player, "steel", ultimates.SET_PIECES)
    room._charge_ult(player, minigun, ultimates.CHARGE_DAMAGE, row.charge_full)
    room.use_ultimate(player.id)

    check(player.ult is not None, "the window opened")
    check(player.ult.key == row.key, "and it is the minigun's")
    check(
        room._empower(player, minigun) is row.empower,
        "and the weapon in hand is inside it",
    )

    # IT DOES NOT FOLLOW THE PLAYER TO ANOTHER WEAPON. Six seconds of free
    # ammunition on a pistol is an exploit whose only symptom is a very good
    # night, which is why this is the one test in the file that would never
    # have been written from a bug report.
    pistol = _hold(player, "glock18")
    check(
        room._empower(player, pistol) is None,
        "and a different weapon gets nothing out of it",
    )
    check(player.ult is not None, "while the window keeps burning regardless")

    # AND THE CLOCK RUNS EVEN WITH THE WEAPON PUT AWAY. What was spent is
    # TIME, and the player spent it.
    for _ in range(int(row.empower.duration / DT) + 2):
        room.step_players(DT)
    check(player.ult is None, "the window closed on its own")

    # THE FREE ROUNDS ARE REAL. Fire with an EMPTY reserve inside the window
    # and a shot still leaves — which is the whole promise of this ultimate
    # and the one thing about it that a branch could silently drop.
    _hold(player, "minigun")
    room._charge_ult(player, minigun, ultimates.CHARGE_DAMAGE, row.charge_full)
    room.use_ultimate(player.id)
    player.ammo.rounds[minigun.ammo] = 0
    player.fire_cooldown = 0.0
    shots = len(room.shot_events)
    cmd = InputCmd(shoot=True, aim_x=1.0, aim_y=0.0)
    room.handle_attack(player, cmd, DT)
    check(len(room.shot_events) > shots, "a dry minigun still fires inside the storm")
    check(player.ammo.rounds[minigun.ammo] == 0, "and the reserve is untouched")


def test_shot_budget() -> None:
    """The Deagle's: one round, and the window ends with it."""
    room, player = _room()
    deagle = _hold(player, "deagle")
    row = ultimates.BY_WEAPON["deagle"]
    _wear(player, "kevlar", ultimates.SET_PIECES)
    room._charge_ult(player, deagle, ultimates.CHARGE_DAMAGE, row.charge_full)
    player.ammo.rounds[deagle.ammo] = 10
    room.use_ultimate(player.id)

    check(player.ult is not None and player.ult.shots == 1, "one round is budgeted")
    player.fire_cooldown = 0.0
    room.handle_attack(player, InputCmd(shoot=True, aim_x=1.0, aim_y=0.0), DT)
    check(player.ult is None, "and firing it closes the window")

    # IT STILL COSTS A ROUND. Only `free_ammo` pays for ammunition, and the
    # Deagle's window does not set it — an ultimate that also refilled the gun
    # would be two rewards for one bar.
    check(player.ammo.rounds[deagle.ammo] == 9, "the round was spent")


def test_aura() -> None:
    """The medic's: a pulse, and it reaches the party rather than the crowd."""
    room, player = _room()
    medgun = _hold(player, "medgun")
    row = ultimates.BY_WEAPON["medgun"]
    _wear(player, "cloth", ultimates.SET_PIECES)

    friend = Player(id="p2", name="Bia", color="#0f0")
    friend.x, friend.y = player.x + 40.0, player.y
    friend.hp = 10
    room.players[friend.id] = friend

    far = Player(id="p3", name="Cau", color="#00f")
    far.x, far.y = player.x + row.aura.radius_tiles * 32 * 4, player.y
    far.hp = 10
    room.players[far.id] = far

    room._charge_ult(player, medgun, ultimates.CHARGE_HEAL, row.charge_full)
    room.use_ultimate(player.id)
    check(friend.hp > 10, f"somebody standing by you is healed, got {friend.hp}")
    check(far.hp == 10, "and somebody across the map is not")

    # A DOWNED BODY IS NOT STOOD UP. Nothing brings one back but the party
    # reaching the next zone — `_check_wipe` is built on that — and an
    # ultimate that revived would quietly delete permadeath, which every other
    # system in this game is balanced against.
    friend.alive = False
    friend.downed = True
    friend.hp = 0
    room._charge_ult(player, medgun, ultimates.CHARGE_HEAL, row.charge_full)
    room.use_ultimate(player.id)
    check(friend.hp == 0 and friend.downed, "a downed body stays down")


# --- the support weapon ------------------------------------------------------


def test_field_gun() -> None:
    """The one trigger in the game that cannot hurt anything."""
    room, player = _room()
    medgun = _hold(player, "medgun")
    check(medgun.heal > 0, "it heals")
    check(medgun.damage == 0, "and does no damage at all")
    check(medgun.ammo == weapons.AMMO_NONE, "and eats no ammunition")

    friend = Player(id="p2", name="Bia", color="#0f0")
    friend.x, friend.y = player.x + 60.0, player.y
    friend.hp = 40
    room.players[friend.id] = friend
    player.aim_x, player.aim_y = 1.0, 0.0

    room.fire(player, 1.0, 0.0, medgun)
    check(friend.hp == 40 + medgun.heal, f"a dart puts {medgun.heal} back, got {friend.hp}")

    # AND IT CHARGES ITS OWN BAR, off what actually LANDED. Topping somebody
    # up from 99 must not be worth the same as catching them at 10, or the
    # correct play would be to spray a healthy party.
    _wear(player, "cloth", ultimates.SET_PIECES)
    friend.hp = friend.max_hp - 1
    player.ult_charge.clear()
    room.fire(player, 1.0, 0.0, medgun)
    check(
        player.ult_charge.get("emergency_protocol") == 1,
        f"one point healed is one point of charge, got {player.ult_charge}",
    )

    # THE SHOT EVENT NAMES NOBODY. A `hit` here would put an impact spark and
    # a spray of blood on a team-mate.
    row = room.shot_events[-1]
    check(row["hit"] is None and row["dmg"] == 0, "and the wire says it hurt nothing")


# --- the architecture --------------------------------------------------------


def test_data_row() -> None:
    """A FIFTH ULTIMATE IS A DATA ROW, asserted rather than claimed.

    The row below is built HERE, in the test, out of the same dataclasses the
    catalog uses, registered, and driven through the unmodified room. If any
    part of the pipeline had learned a weapon's name — the requirement check,
    the charge, the dispatch, the effect — this would fail, and it would fail
    for the right reason: because somebody wrote a branch instead of a row.
    """
    row = ultimates.UltimateDef(
        key="test_pulse",
        name="Pulso de Teste",
        weapon="ak47",
        blurb="Existe apenas neste teste.",
        # An existing weapon tag and an existing armour tag, so the row needs
        # no new vocabulary either.
        requires=("automatic", "riot"),
        charge_on=ultimates.CHARGE_DAMAGE,
        charge_full=10.0,
        aura=ultimates.Aura(radius_tiles=8.0, damage=999),
    )
    ultimates.BY_KEY[row.key] = row
    ultimates.BY_WEAPON[row.weapon] = row
    try:
        room, player = _room()
        rifle = _hold(player, "ak47")
        _wear(player, "steel", ultimates.SET_PIECES)
        room._charge_ult(player, rifle, ultimates.CHARGE_DAMAGE, row.charge_full)
        check(
            player.ult_charge.get(row.key) == row.charge_full,
            "a row nobody wrote code for charges",
        )

        from app.enemies import ZOMBIE  # noqa: PLC0415

        victim = room.spawn_enemy(ZOMBIE, player.x + 30.0, player.y)
        room.use_ultimate(player.id)
        check(victim.id not in room.enemies, "and fires, and its effect lands")
        check(
            any(event["k"] == row.key for event in room.ult_events),
            "and announces itself by key",
        )
    finally:
        ultimates.BY_KEY.pop(row.key, None)
        ultimates.BY_WEAPON.pop(row.weapon, None)


def main() -> None:
    test_catalog()
    test_requirements()
    test_charge()
    test_volley()
    test_window()
    test_shot_budget()
    test_aura()
    test_field_gun()
    test_data_row()
    if FAILURES:
        raise SystemExit(f"FAILED ({len(FAILURES)})")
    print("ok")


if __name__ == "__main__":
    main()
