"""The wolves, and the thing asleep in the den.

Run:  python tests/test_pack.py   (from server/)

Everything here is a rule with NO SYMPTOM YOU WOULD SEE WHILE PLAYING. A wolf
that stopped calling its pack is a wolf; a miniboss that woke to the siren is
a miniboss that was already awake when you got there; a den that never landed
is a forest with one fewer clearing in it. All of those look like a working
game right up until somebody asks why the new creature never feels like a
pack, and by then the answer is four modules away.

Five things, and the order is the encounter's own:

  1. **A PACK ARRIVES AS A PACK.** `EnemyType.group_min` is the floor under a
     wave's size and it is read in exactly one place. Break it and wolves
     spawn one at a time — which is a fast zombie, and the whole creature is
     the fact that it is not one.
  2. **THE HOWL REACHES ITS OWN KIND AND NOTHING ELSE.** Four times a shout's
     range, wolves only. If it ever woke the dead as well it would be a
     strictly better shout at every distance, and the next creature would
     inherit a general-purpose alarm by accident.
  3. **THE ALPHA IS ASLEEP UNTIL SOMEBODY COMES CLOSE**, and specifically not
     until then: not for a lantern, not for the extraction siren that commits
     every other creature on the map. The whole encounter is that the party
     sees it before it sees them, and every one of those is a way to lose that
     without noticing.
  4. **IT STANDS UP BEFORE IT COMES.** A free beat between the eyes opening
     and the first step. It is the telegraph, it is one number, and nothing
     at runtime would tell you it had gone to zero.
  5. **AND YOU CAN LEAVE.** Run far enough and it gives up, walks home and
     GOES BACK TO SLEEP — so the den is still there and still a decision.
     A miniboss that idled in the treeline afterwards would have turned a
     place into a wandering monster the first time anybody escaped one.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, mapgen, protocol, zones  # noqa: E402
from app.config import (  # noqa: E402
    ALPHA_WAKE_DELAY,
    DT,
    ENEMY_ALERT_SHARE_TILES,
    TILE_SIZE,
)
from app.enemies import (  # noqa: E402
    ENEMY_TYPES,
    RANK_MINIBOSS,
    SPAWN_TABLE,
    WOLF,
    WOLF_ALPHA,
    ZOMBIE,
    Enemy,
)
from app.pathing import Navigator  # noqa: E402
from app.room import Room  # noqa: E402

PROCESSED = Path(__file__).resolve().parents[2] / "assets/processed"


def check(label: str, ok: bool) -> None:
    print(f"  {label}: {'ok' if ok else 'FAILED'}")
    if not ok:
        raise SystemExit(1)


def make_room(seed: int = 4242) -> tuple[Room, object]:
    """A room standing in a real forest with one living player in it."""
    room = Room()
    room.phase = protocol.PHASE_PLAYING
    player = room.add_player(None, "Tester")
    room.zone = zones.forest(1)
    room.world = mapgen.build_forest(day=1, seed=seed)
    room.arriving = False
    # What `_swap_map` does on the way into a forest, minus the socket traffic:
    # the nests are the map's own creatures and they are standing before
    # anybody arrives.
    room.navigator = Navigator(room.world)
    room._rebuild_spawns()
    room._seed_nests()
    player.alive = True
    player.hp = player.max_hp
    return room, player


def find_alpha(room: Room) -> Enemy | None:
    for enemy in room.enemies.values():
        if enemy.type is WOLF_ALPHA:
            return enemy
    return None


def main() -> None:
    print("the stat block")
    check("the alpha is ranked", WOLF_ALPHA.rank == RANK_MINIBOSS)
    check("and the pack is not", WOLF.rank == "")
    # The catalog is what the client resolves a creature against; the spawn
    # table is what the director rolls. The alpha is in exactly one of them,
    # and being in the second would make a miniboss a random event.
    check("the alpha is in the catalog", ENEMY_TYPES.get(WOLF_ALPHA.key) is WOLF_ALPHA)
    check(
        "and NOT on the spawn table",
        all(kind is not WOLF_ALPHA for kind, _ in SPAWN_TABLE),
    )
    check("the wolf is on it", any(kind is WOLF for kind, _ in SPAWN_TABLE))
    # Both halves of "asleep" are one field. A creature the client cannot draw
    # curled up must not be able to spawn curled up.
    check("the alpha sleeps", WOLF_ALPHA.sleeps and WOLF_ALPHA.wake_tiles > 0)
    check(
        "and its sleep sheet exists",
        (PROCESSED / WOLF_ALPHA.sleep_sprite / "sheet.png").exists(),
    )
    check("the pack never sleeps", not WOLF.sleeps)
    # It was placed by the map, so nothing may recycle it.
    check("the alpha persists", WOLF_ALPHA.persists and not WOLF.persists)

    print("a pack is not one wolf")
    # `group_min` is read in exactly one place — the director — and it is what
    # separates a pack from a fast zombie.
    director = ai.EnemyDirector([(x * TILE_SIZE, 0.0) for x in range(5, 40)], day=1)
    random.seed(7)
    sizes: dict[str, list[int]] = {}
    for _ in range(400):
        director.timer = 0.0
        wave = director.update(
            DT,
            [_Standing(TILE_SIZE * 20, 0.0)],
            0,
        )
        if not wave:
            continue
        sizes.setdefault(wave[0][0].key, []).append(len(wave))
    check("wolves showed up at all", bool(sizes.get(WOLF.key)))
    check(
        f"never fewer than {WOLF.group_min} (smallest {min(sizes[WOLF.key])})",
        min(sizes[WOLF.key]) >= WOLF.group_min,
    )
    # And the floor is a floor, not a fixed size: a wave of exactly two every
    # time is a formation.
    check("and not always the same", len(set(sizes[WOLF.key])) > 1)
    check(
        "the dead still arrive alone sometimes",
        min(sizes.get(ZOMBIE.key, [99])) == 1,
    )

    print("the howl")
    # Four wolves and four zombies in a line, all at the same distances from
    # one spotter. The call has to pick out exactly the wolves inside its own
    # reach and leave everything else standing.
    spotter = Enemy(id="w0", type=WOLF, x=0.0, y=0.0)
    target = _Standing(0.0, TILE_SIZE * 2)
    reach = WOLF.pack_call_tiles
    near = TILE_SIZE * (reach - 2.0)
    far = TILE_SIZE * (reach + 4.0)
    pack = [
        spotter,
        Enemy(id="w1", type=WOLF, x=near, y=0.0),
        Enemy(id="w2", type=WOLF, x=far, y=0.0),
        Enemy(id="z1", type=ZOMBIE, x=near, y=0.0),
        Enemy(id="z2", type=ZOMBIE, x=TILE_SIZE * (ENEMY_ALERT_SHARE_TILES - 1), y=0.0),
    ]
    ai.shout(spotter, target, pack)
    by_id = {enemy.id: enemy for enemy in pack}
    check("the howl reaches its own kind", by_id["w1"].mode == ai.MODE_HUNT)
    check("and stops at its reach", by_id["w2"].mode != ai.MODE_HUNT)
    # THE ONE WORTH HAVING. A howl that woke the dead too would be strictly
    # better than a shout at every range, and nothing would look wrong.
    check("it does not wake the dead", by_id["z1"].mode != ai.MODE_HUNT)
    check("not even one a shout would have", by_id["z2"].mode != ai.MODE_HUNT)
    # And the ordinary shout is untouched: a zombie still nudges whatever is
    # standing next to it, wolves included.
    caller = Enemy(id="z9", type=ZOMBIE, x=0.0, y=0.0)
    neighbour = Enemy(
        id="w9", type=WOLF, x=TILE_SIZE * (ENEMY_ALERT_SHARE_TILES - 1), y=0.0
    )
    ai.shout(caller, target, [caller, neighbour])
    check("a shout is still a shout", neighbour.mode == ai.MODE_HUNT)
    # THE ALPHA CALLS WOLVES, NOT ALPHAS. Keyed on the type this reached
    # exactly nobody — there is only ever one of him — so the loudest call in
    # the game belonged to the creature with nothing to call. `EnemyType.pack`
    # is the group, and a leader brings the animals already out there.
    leader = Enemy(id="a0", type=WOLF_ALPHA, x=0.0, y=0.0)
    leader.mode = ai.MODE_HUNT
    answering = Enemy(
        id="w8", type=WOLF, x=TILE_SIZE * (WOLF_ALPHA.pack_call_tiles - 3.0), y=0.0
    )
    bystander = Enemy(
        id="z8", type=ZOMBIE, x=TILE_SIZE * (WOLF_ALPHA.pack_call_tiles - 3.0), y=0.0
    )
    ai.shout(leader, target, [leader, answering, bystander])
    check("the alpha's howl brings wolves", answering.mode == ai.MODE_HUNT)
    check("and still not the dead", bystander.mode != ai.MODE_HUNT)
    check("they share a pack", WOLF.pack and WOLF.pack == WOLF_ALPHA.pack)
    check("the dead have none", ZOMBIE.pack == "")
    # AND IT DOES NOT REACH INTO A DEN. A call carries thirty tiles, past the
    # lantern, so a howl that woke sleepers would wake a miniboss for somebody
    # who shot at a pack across a clearing and never saw the place. See
    # `ai.shout` — this is the trade, written down.
    dozing = Enemy(id="a1", type=WOLF_ALPHA, x=TILE_SIZE * 2, y=0.0)
    dozing.mode = ai.MODE_SLEEP
    ai.shout(leader, target, [leader, dozing])
    check("a howl does not reach a den", dozing.mode == ai.MODE_SLEEP)

    print("the den")
    # It is a landmark, so it lands on every forest — and the thing that lives
    # in it is standing in it before anybody has walked there.
    room, player = make_room()
    alpha = find_alpha(room)
    check("the map placed one", alpha is not None)
    assert alpha is not None
    check("asleep on arrival", alpha.mode == ai.MODE_SLEEP and alpha.asleep)
    check("and the snapshot says so", alpha.to_payload().get("sl") == 1)
    check("with an empty diamond", alpha.awareness == 0.0)
    den = next(
        (row for row in room.world.nests if row[3] == WOLF_ALPHA.key), None
    )
    check("in its own scene", den is not None)
    assert den is not None
    # Not ON the anchor — `loot.place_near` walks out to a free tile and the
    # hollow has trunks in it — but well inside the scene rather than in the
    # treeline beside a den with nothing in it, which is what the scatter the
    # other nests use would have done.
    check(
        "standing in the middle of it",
        math.hypot(alpha.x - den[0], alpha.y - den[1]) <= TILE_SIZE * 2.5,
    )

    print("nothing wakes it but you")
    # Parked far away, with the whole map hunting: the siren is the loudest
    # thing anybody does on a night and it commits every creature there is.
    # It must not reach a den nobody has found, or the encounter has happened
    # to a party that never chose it.
    player.x = alpha.x + TILE_SIZE * 40
    player.y = alpha.y
    room.panic = True
    for _ in range(60):
        room.step_enemies(DT)
    check("the siren does not", alpha.mode == ai.MODE_SLEEP)
    room.panic = False
    # And neither does the abandonment timer, which would have recycled
    # anything else standing that far from anybody.
    for _ in range(int(12.0 / DT)):
        room.step_enemies(DT)
    check("nor does being forgotten", alpha.id in room.enemies)
    check("still asleep", alpha.mode == ai.MODE_SLEEP)

    print("walking up to it")
    # Just outside the wake radius: the gap between this and the lantern's
    # reach is the entire decision the encounter exists to offer.
    player.x = alpha.x + WOLF_ALPHA.wake_range + TILE_SIZE * 1.5
    player.y = alpha.y
    for _ in range(30):
        room.step_enemies(DT)
    check("a step short and it sleeps", alpha.mode == ai.MODE_SLEEP)

    player.x = alpha.x + WOLF_ALPHA.wake_range * 0.5
    room.step_enemies(DT)
    check("a step closer and it is up", alpha.mode == ai.MODE_HUNT)
    check("committed to the body that woke it", alpha.target_id == player.id)
    check("diamond full at once", alpha.awareness >= 1.0)
    check("and the snapshot stops saying asleep", "sl" not in alpha.to_payload())

    print("it stands before it comes")
    # THE FREE BEAT. Nothing else in this game gets one, and it is the whole
    # difference between waking something and being ambushed by it.
    started = (alpha.x, alpha.y)
    held = 0.0
    while alpha.waking > 0.0 and held < 5.0:
        room.step_enemies(DT)
        held += DT
    check(
        f"it held for {held:.2f}s (~{ALPHA_WAKE_DELAY}s)",
        abs(held - ALPHA_WAKE_DELAY) <= DT * 3,
    )
    check(
        "without moving",
        math.hypot(alpha.x - started[0], alpha.y - started[1]) < 1e-6,
    )
    room.step_enemies(DT)
    room.step_enemies(DT)
    check(
        "then it comes",
        math.hypot(alpha.x - started[0], alpha.y - started[1]) > 0.0,
    )

    print("and you can leave")
    # Past the give-up distance and past the leash, which is what running
    # away actually looks like from the creature's side.
    player.x = alpha.home_x + TILE_SIZE * 60
    player.y = alpha.home_y + TILE_SIZE * 60
    gave_up = False
    for _ in range(int(8.0 / DT)):
        room.step_enemies(DT)
        if alpha.mode == ai.MODE_RETURN:
            gave_up = True
            break
    check("it gives up", gave_up)
    # ...and goes home, and goes back to sleep. The den is still a den.
    for _ in range(int(90.0 / DT)):
        room.step_enemies(DT)
        if alpha.mode == ai.MODE_SLEEP:
            break
    check("walks home and lies back down", alpha.mode == ai.MODE_SLEEP)
    check("in its den", math.hypot(alpha.x - den[0], alpha.y - den[1]) <= TILE_SIZE * 3)
    check("and can be walked up to again", alpha.awareness == 0.0)

    print("ok")


class _Standing:
    """The smallest thing the director will accept as a player."""

    alive = True

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.id = "p"


if __name__ == "__main__":
    main()
