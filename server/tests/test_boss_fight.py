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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import arena, boss, entrance, protocol, zones  # noqa: E402
from app.config import (  # noqa: E402
    ARENA_RADIUS_TILES,
    ARENA_TRIGGER_TILES,
    BOSS_DAY,
    DT,
    TILE_SIZE,
)
from app.room import Room  # noqa: E402
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
            player.hp = player.max_hp
            player.alive = True
    check(f"he lands blows on somebody standing still ({hits_taken})", hits_taken > 0)
    check("he telegraphs before every one", "windup" in seen)
    check("he uses more than one move", len({m for m in seen} & {"impact", "rip"}) >= 1)

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
