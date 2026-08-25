"""The Sawyer's fight, driven end to end with nobody watching.

Run:  python tests/test_boss_fight.py   (from server/)

A boss fight is a sequence, and every join in that sequence is a place where
the room can quietly stop: he never wakes, the cinematic never ends, the
crescent never expires, the exit never opens, the night's takings never make
it to the shop. None of those has a symptom you would notice in a screenshot —
you notice them by standing in an empty yard wondering what to do — so they
are pinned here instead.

What this does NOT check is whether the fight is any good. It checks that it
happens.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import arena, boss, entrance, protocol, zones  # noqa: E402
from app.config import (  # noqa: E402
    ARENA_RADIUS_TILES,
    ARENA_TRIGGER_TILES,
    BOSS_DAY,
    BOSS_FAN_CRESCENTS,
    DT,
    TILE_SIZE,
)
from app.room import Room  # noqa: E402
from app.maps import count_reachable  # noqa: E402
from app.world import FLOOR, VOID  # noqa: E402


def make_room() -> tuple[Room, object]:
    """A room standing in the arena with one player in it."""
    room = Room()
    room.phase = protocol.PHASE_PLAYING
    player = room.add_player(None, "Tester")
    room.zone = zones.arena(1)
    room.world = arena.build_arena(1, seed=1234)
    room._load_entrance()
    room._load_boss()
    room.arriving = False
    cx, cy = arena.centre(room.world)
    # Standing in the mouth of the lane, outside the trigger.
    player.x = cx
    player.y = cy + TILE_SIZE * (ARENA_TRIGGER_TILES + 6.0)
    player.alive = True
    player.hp = player.max_hp
    return room, player


def check(label: str, ok: bool) -> None:
    print(f"  {label}: {'ok' if ok else 'FAILED'}")
    if not ok:
        raise SystemExit(1)


def main() -> None:
    print("the arena")
    world = arena.build_arena(1, seed=99)
    floor = sum(row.count(FLOOR) for row in world.tiles)
    # A disc of `ARENA_RADIUS_TILES`, less the drums and whatever the corridor
    # ate. Checked as a FRACTION of the disc rather than as a flat number, so
    # resizing the ring does not need this line edited — only a ring that came
    # out mostly walls would fail it.
    import math as _math
    expect = _math.pi * (ARENA_RADIUS_TILES ** 2)
    check(f"it is one connected yard ({floor} of ~{expect:.0f})", floor > expect * 0.85)
    check("it has a way in", world.entrance is not None)
    check("it has NO way out yet", world.egress is None)
    fires = sum(row.count(3) for row in world.tiles)
    check(f"the rim is lit ({fires} drums)", fires >= 6)

    print("waking him")
    room, player = make_room()
    check("he exists, asleep", room.boss is not None and room.boss.state == boss.SLEEP)
    for _ in range(30):
        room.step_boss(DT)
    check("standing off, he stays asleep", room.boss.state == boss.SLEEP)

    cx, cy = arena.centre(room.world)
    player.x, player.y = cx, cy + TILE_SIZE * 2.0
    room.step_boss(DT)
    check("walk into the ring and he comes down", room.boss.state == boss.ARRIVE)
    check("the arrival is announced",
          any(e["kind"] == "arrive" for e in room.boss_events))

    print("the cinematic")
    # Input is dropped for the whole of it — the party is IN the shot.
    ticks = 0
    while room.boss.state == boss.ARRIVE and ticks < 400:
        room.step_players(DT)
        room.step_boss(DT)
        ticks += 1
    length = ticks * DT
    check(f"it ends ({length:.2f}s, art says {boss.ARRIVE_LENGTH:.2f}s)",
          abs(length - boss.ARRIVE_LENGTH) < 0.12)
    check("and the fight starts", room.boss.state in (boss.IDLE, boss.WALK))

    print("the fight")
    seen: set[str] = set()
    hits_taken = 0
    start_hp = player.hp
    for tick in range(60 * 30):
        # A player who never moves: he should be able to hit them, which is
        # the only thing this loop is asking.
        room.step_boss(DT)
        for event in room.boss_events:
            seen.add(event["kind"])
            if event["kind"] == "hurt":
                hits_taken += 1
        room.boss_events = []
        if player.hp <= 0:
            # STANDING THEM BACK UP MEANS CLEARING `downed` TOO. The two
            # flags are not the same question (`Player.downed`), and a body
            # left `alive=True, downed=True` is a state the room never
            # produces — it used to pass unnoticed because the exit check
            # only read `alive`, and it now silently takes the player out of
            # the party count the corridor is waiting on.
            player.hp = player.max_hp
            player.alive = True
            player.downed = False
    check(f"he lands blows on somebody standing still ({hits_taken})", hits_taken > 0)
    check("he telegraphs before every one", "windup" in seen)
    check("he uses more than one move", len({m for m in seen} & {"impact", "rip"}) >= 1)

    print("the picker")
    # WHAT THIS IS FOR: he used to be a lookup table with a coin flip on top.
    # Bands abutted, so under four tiles the only legal pair was chop and
    # sweep and over four and a half the crescent was the ONLY legal move; the
    # no-repeat rule then made both halves a strict alternation. Nothing about
    # that is visible in a screenshot and nothing about it fails a test — you
    # notice it by playing him twice and knowing what comes next.
    picker = boss.Boss(id="p", x=0.0, y=0.0, max_hp=100)
    picker._rng = random.Random(4)
    for tiles, expect in ((2.0, 2), (4.2, 3), (8.0, 2), (13.0, 1)):
        picked = set()
        picker._last, picker._repeats = "", 0
        for _ in range(400):
            move = boss._choose(picker, tiles)
            if move is not None:
                picked.add(move.key)
        check(f"at {tiles} tiles he has {len(picked)} answers ({sorted(picked)})",
              len(picked) >= expect)
    # …and the bands still MEAN something: the sweep is a close-quarters move
    # and must never be rolled from across the yard.
    picker._last, picker._repeats = "", 0
    far = {boss._choose(picker, 9.0).key for _ in range(400)}
    check(f"but the far bands are still far ({sorted(far)})",
          "sweep" not in far and "chop" not in far)
    # Never three of anything running, which is the one hard rule left.
    picker._last, picker._repeats = "", 0
    seq = [boss._choose(picker, 2.0).key for _ in range(2000)]
    run = best = 1
    for index in range(1, len(seq)):
        run = run + 1 if seq[index] == seq[index - 1] else 1
        best = max(best, run)
    check(f"and never three of one in a row (longest {best})", best <= 2)

    print("the charge")
    # THE ANSWER TO A GUN, and the reason it is pinned: every other move is a
    # swing thrown by a rooted body, so the charge is the only one whose
    # hitbox MOVES and the only one that spans three animations. Nothing at
    # runtime notices if it stops running — he simply stands there, and a
    # player with a rifle wins the fight by walking backwards.
    room2, walker = make_room()
    room2.boss.state = boss.IDLE
    cx2, cy2 = arena.centre(room2.world)
    room2.boss.x, room2.boss.y = cx2, cy2
    # Standing off, well outside every swing's reach.
    walker.x, walker.y = cx2, cy2 + TILE_SIZE * 8.0
    walker.vx = walker.vy = 0.0
    walker.hp = walker.max_hp
    room2.boss.move = boss.RUSH
    room2.boss.target_id = walker.id
    boss._enter(room2.boss, boss.WINDUP)
    saw_charge = False
    hit_by_run = 0
    for _ in range(200):
        room2.step_boss(DT)
        if room2.boss.state == boss.CHARGE:
            saw_charge = True
        for event in room2.boss_events:
            if event["kind"] == "hurt":
                hit_by_run += 1
        room2.boss_events = []
        if room2.boss.state == boss.RECOVER:
            break
    check("the roar becomes a run", saw_charge)
    check(f"and it runs over somebody standing in it ({hit_by_run})", hit_by_run > 0)
    check("then it ends in a punish window", room2.boss.state == boss.RECOVER)
    check(f"whose length is written down ({room2.boss.recover_for:.2f}s)",
          room2.boss.recover_for > 0.0)
    # THE THREE SHEETS. The client resolves the run's animation off this
    # payload, and a move that forgot to say which sheet it plays draws a boss
    # crossing the yard standing still.
    payload = boss.moves_payload()["charge"]
    check(f"and the client is told all three sheets "
          f"({payload['clip']} -> walk -> {payload['after']})",
          payload["clip"] == "rev" and payload["after"] == "idle")

    print("the enrage changes the moves, not just the clock")
    # SPEED ALONE IS THE SAME FIGHT ON A SHORTER TIMER, and the player already
    # learned it. Each variant takes away one specific certainty, and none of
    # them costs a frame of art — which is exactly why nothing would notice if
    # they silently stopped happening.
    raged = boss.Boss(id="r", x=0.0, y=0.0, max_hp=100)
    raged._rng = random.Random(11)
    raged.aim_x, raged.aim_y = 0.0, 1.0
    out = boss.Outcome()
    boss._land(raged, boss.RIP, [], out)
    check(f"calm, the throw is one crescent ({len(raged.crescents)})",
          len(raged.crescents) == 1)
    raged.crescents.clear()
    raged.enraged = True
    boss._land(raged, boss.RIP, [], out)
    check(f"enraged, it is a fan ({len(raged.crescents)})",
          len(raged.crescents) == BOSS_FAN_CRESCENTS)
    # A FAN, not a shotgun: they have to leave on DIFFERENT headings or it is
    # one crescent drawn three times and the sidestep still beats it.
    headings = {round(math.atan2(c.dy, c.dx), 3) for c in raged.crescents}
    check(f"on {len(headings)} different headings", len(headings) == BOSS_FAN_CRESCENTS)

    doubles = 0
    for _ in range(200):
        raged.encore = None
        boss._land(raged, boss.CHOP, [], boss.Outcome())
        if raged.encore is not None:
            doubles += 1
    check(f"and the chop sometimes comes straight back ({doubles} of 200)",
          0 < doubles < 200)
    calm = boss.Boss(id="c", x=0.0, y=0.0, max_hp=100)
    calm._rng = random.Random(11)
    for _ in range(60):
        calm.encore = None
        boss._land(calm, boss.CHOP, [], boss.Outcome())
        if calm.encore is not None:
            break
    check("never before the enrage", calm.encore is None)

    print("the crescent")
    crest = boss.Crescent(id=1, x=player.x - 200.0, y=player.y, dx=200.0, dy=0.0,
                          life=boss.BOSS_CREST_LIFE if hasattr(boss, "BOSS_CREST_LIFE") else 1.9)
    room.boss.crescents = [crest]
    room.boss.state = boss.IDLE
    landed = 0
    for _ in range(120):
        before = player.hp
        room.step_boss(DT)
        for event in room.boss_events:
            if event["kind"] == "hurt":
                landed += 1
        room.boss_events = []
        player.hp = player.max_hp
        if not room.boss.crescents:
            break
    check("it travels, hits once, and expires", landed >= 1 and not room.boss.crescents)

    print("killing him")
    room.boss.hp = room.boss.max_hp
    room.boss.enraged = False
    guard = 0
    while room.boss.state != boss.DEAD and guard < 500:
        room.damage_boss(60, player)
        guard += 1
    check("he goes down", room.boss.state == boss.DEAD)
    check("the enrage fired on the way", room.boss.enraged)
    check("the treeline opens", room.egress is not None)
    # OPPOSITE THE WAY IN, and joined to the ring. Both halves matter: a yard
    # whose exit appears beside its entrance is a room you turn round in, and
    # one whose exit is cut into the treeline without a lane back to the disc
    # seals the party in with a corpse. Neither has a symptom until somebody
    # is standing there looking for a way out.
    check(f"straight across from the way in ({room.gate.side} -> {room.egress.side})",
          room.egress.side == entrance.OPPOSITE[room.gate.side])
    floor = sum(row.count(FLOOR) for row in room.world.tiles)
    check(f"and the party can reach it ({floor} floor)",
          count_reachable(room.world.tiles) == floor)
    check("it is lit", len(room.egress.torches) > 0)
    check("the map itself changed", any(
        world_row.count(VOID) for world_row in room.world.tiles
    ))
    check("and it is announced", any(e["kind"] == "slain" for e in room.boss_events))
    check("he pays the party", player.xp > 0)
    check("and drops coins on the floor", len(room.coins) > 0)

    print("the way out")
    room._pending_return = False
    room._tick_arena_exit()
    check("standing in the yard is not crossing", not room._pending_return)
    gate = room.egress
    player.x = gate.mouth_x
    player.y = gate.mouth_y
    # OUTWARD, which is the opposite of `dx`/`dy`: those point into the map
    # (the emerge direction) and leaving is walking back down the VOID.
    for _ in range(80):
        player.x -= gate.dx * 4.0
        player.y -= gate.dy * 4.0
        room._tick_arena_exit()
        if room._pending_return:
            break
    check("walking into the corridor is", room._pending_return)

    print("the takings survive the detour")
    room2 = Room()
    room2.phase = protocol.PHASE_PLAYING
    room2.add_player(None, "Tester")
    room2._night_takes = [120, 80]
    room2.zone = zones.arena(1)
    room2.world = arena.build_arena(1, seed=5)
    import asyncio
    asyncio.run(room2.enter_store())
    check(f"banked at the shop ({room2.balance})", room2.balance == 200)
    check("and the receipt is torn up", room2._night_takes is None)

    print("the whole night, in one line")
    # THE DISPATCH IS THE THING WORTH PINNING. Everything above tests the
    # fight; this tests that a party ever reaches it — the exit corridor of a
    # boss night has to open onto the yard rather than onto the shop, and the
    # yard's exit has to open onto the shop rather than onto another forest.
    import asyncio as _asyncio
    from app import mapgen
    room3 = Room()
    room3.phase = protocol.PHASE_PLAYING
    room3.add_player(None, "Tester")
    room3.day = BOSS_DAY if BOSS_DAY is not None else 1
    room3.zone = zones.forest(room3.day)
    room3.world = mapgen.build_forest(day=room3.day)
    room3._load_entrance()
    check("a boss night knows it is one", room3.is_boss_night())
    _asyncio.run(room3.advance_zone())
    check(f"the forest's exit opens onto the yard ({room3.zone.kind})",
          room3.zone.kind == zones.KIND_ARENA)
    check("and he is standing in it", room3.boss is not None)
    check("with no director behind him", len(room3.enemies) == 0)
    _asyncio.run(room3.advance_zone())
    check(f"the yard's exit opens onto the shop ({room3.zone.kind})",
          room3.zone.kind == zones.KIND_STORE)
    check("and the boss is gone with the map", room3.boss is None)

    print("a night that is not his")
    room4 = Room()
    room4.phase = protocol.PHASE_PLAYING
    room4.add_player(None, "Tester")
    room4.day = (BOSS_DAY or 1) + 1
    room4.zone = zones.forest(room4.day)
    room4.world = mapgen.build_forest(day=room4.day)
    check("is not a boss night", not room4.is_boss_night())
    _asyncio.run(room4.advance_zone())
    check("and goes straight to the shop", room4.zone.kind == zones.KIND_STORE)

    print("the switch")
    check(f"BOSS_DAY is {BOSS_DAY} and one place reads it",
          BOSS_DAY is None or isinstance(BOSS_DAY, int))
    print("ok")


if __name__ == "__main__":
    main()
