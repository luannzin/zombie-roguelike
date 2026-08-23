"""The thing that reaches, and why walking backwards stops working.

Run:  python tests/test_ranged.py   (from server/)

Position was never a decision in this game. A zombie is slower than you and a
wolf has to touch you, so backing away is the correct answer to the entire
bestiary — which quietly meant cover was scenery, worn armour was a number that
rarely mattered, and the shield was a boss-fight item. One creature that hurts
you from where it is standing makes all three mean something everywhere.

Five things about it are invisible from inside the game:

  * THE BAND, AND ESPECIALLY ITS NEAR EDGE. Inside `ranged_min` it must not be
    able to fire, because CLOSING is the answer to it — the exact inversion of
    every other threat here. A minimum that silently stopped working would turn
    it into a creature that is strictly better the closer it gets, which leaves
    the player nothing to do but retreat, which is the posture it was added to
    break. Nothing about that is visible: it would just feel unfair.
  * THE TELEGRAPH. A ranged attack with no windup is damage arriving out of the
    dark with nothing to react to, and on a permanent run that is a deleted run
    rather than a threat. The windup must exist, must PLANT the creature, and
    must be on the wire — a telegraph nobody can see is not one.
  * IT MUST BE OUTWALKABLE. `projectiles.py`'s whole argument is that a
    projectile you cannot outrun is a number the game subtracts rather than an
    attack you answer. That is arithmetic against the player's own speed and
    nothing at runtime checks it.
  * IT MUST NOT SHOOT THROUGH WALLS. A disc is tested against bodies AFTER it
    is tested against the map, and getting that order wrong is a hit through
    cover — which is most of what a ranged attacker is supposed to make the
    player think about.
  * NO CREATURE NAME IN `ai.py`. The whole promise of `EnemyType` is that a
    creature is a stat block and a sheet. The ranged branch is driven by a
    field, and this fails if anybody ever reaches for a key comparison.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, enemies, projectiles, protocol, zones  # noqa: E402
from app.config import DT, MOVE_SPEED, TILE_SIZE  # noqa: E402
from app.room import Room  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


class Socket:
    async def send_text(self, text: str) -> None:
        pass


BLOATER = enemies.ENEMY_TYPES["bloater"]


def forest_room() -> tuple[Room, str]:
    room = Room(code="RNG")
    room.phase = protocol.PHASE_PLAYING
    pid = room.add_player(Socket(), "P0").id
    asyncio.run(room.embark())
    room.arriving = False
    room.gate = None
    room.enemies.clear()
    # A CLEAR NIGHT, PINNED. Weather is rolled per night and fog multiplies
    # every sight reach by `zones.WeatherRule.sight` — which on a foggy roll
    # puts this creature's own band outside what it can SEE, so it never winds
    # up and the band assertions fail for a reason that has nothing to do with
    # the band. `tests/test_weather.py` owns the coats; this file owns the
    # band, and it asks its question on the night the numbers mean what they
    # say. (This flake was one run in three, and it is exactly the kind that
    # gets "fixed" by rerunning until it passes.)
    room.zone = dataclasses.replace(room.zone, weather=zones.WEATHER_CLEAR)
    # STAND THEM SOMEWHERE REAL. Players are placed when the arrival cinematic
    # finishes, and skipping it (as every headless test does) leaves them on
    # the coordinates they had in the camp — which on a forest map is usually
    # inside a tree. A disc that bursts on the frame it is created is a
    # perfectly correct outcome that says nothing about the code under test.
    player = room.players[pid]
    player.x, player.y = room.pick_spawn()
    return room, pid


def place(room: Room, pid: str, tiles_away: float, seen: bool = True):
    """One bloater `tiles_away` from the player, already hunting, WITH A VIEW.

    THE BEARING IS SEARCHED, NOT ASSUMED. A generated forest has trees in it,
    and a creature placed due east about a third of the time has one between
    it and the player — so `ai.look` finds nobody, the ranged branch correctly
    declines to fire at a target it cannot see, and every band assertion fails
    for a reason that has nothing to do with the band.

    That flake was one run in three and it is exactly the kind that gets
    "fixed" by rerunning until it passes. Returns the unit bearing as well, so
    the cases that HOLD a creature at a distance hold it on the same clear line
    rather than snapping it back behind a tree.
    """
    player = room.players[pid]
    for step in range(36):
        angle = step * (math.tau / 36)
        ux, uy = math.cos(angle), math.sin(angle)
        bx = player.x + ux * tiles_away * TILE_SIZE
        by = player.y + uy * tiles_away * TILE_SIZE
        if room.world.box_blocked(bx, by, BLOATER.half_width, BLOATER.half_height):
            continue
        beast = room.spawn_enemy(BLOATER, bx, by)
        beast.target_id = pid
        beast.mode = ai.MODE_HUNT
        beast.awareness = 1.0
        beast.aim_x, beast.aim_y = -ux, -uy
        # The line has to be genuinely open, which only `look` can answer —
        # it is the same ray the ranged branch gates on.
        #
        # `seen=False` for the OUT-OF-BAND case, where the creature is
        # deliberately parked beyond its own sight: requiring a view there
        # would be requiring the thing the case exists to rule out.
        if not seen or ai.look(beast, [player], room.world) is not None:
            return beast, ux, uy
        room.enemies.pop(beast.id, None)
    raise AssertionError(f"no clear bearing at {tiles_away} tiles on this map")


def clear_line(room: Room, player, tiles: float) -> tuple[float, float] | None:
    """A launch point `tiles` from the player with nothing solid in between.

    A generated forest has trees in it, so a fixed offset lands a test disc
    inside one about as often as not — and a disc that bursts on the frame it
    is created is a perfectly correct outcome that says nothing about the code
    under test. This walks the compass for a bearing that is actually open.
    """
    for step in range(24):
        angle = step * (math.tau / 24)
        ox = player.x + math.cos(angle) * tiles * TILE_SIZE
        oy = player.y + math.sin(angle) * tiles * TILE_SIZE
        if room.world.box_blocked(ox, oy, 2.0, 2.0):
            continue
        # And the whole path back to the player, or it bursts halfway.
        blocked = False
        for i in range(1, 21):
            t = i / 20
            if room.world.box_blocked(
                ox + (player.x - ox) * t, oy + (player.y - oy) * t, 2.0, 2.0
            ):
                blocked = True
                break
        if not blocked:
            return ox, oy
    return None


def tick(room: Room, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        room.step_enemies(DT)
        room.step_shots(DT)


# --- the stat block ----------------------------------------------------------

check("the bloater reaches", BLOATER.ranged_damage > 0)
check("it is the only thing that does",
      [t.key for t in enemies.ENEMY_TYPES.values() if t.ranged_damage > 0] == ["bloater"])

# THE BAND HAS A NEAR EDGE, and it is the mechanic.
check("its band has a floor", BLOATER.ranged_min_tiles > 0)
check("and a ceiling above it", BLOATER.ranged_max_tiles > BLOATER.ranged_min_tiles)
# The floor has to be OUTSIDE its own melee reach, or "get inside it" lands the
# player in a place where it simply bites them instead — which is not an
# inversion, it is a creature with two answers and no weakness.
check(
    "getting inside it is a real place to stand",
    BLOATER.ranged_min_tiles > BLOATER.attack_range_tiles,
)

# IT TELEGRAPHS.
check("it winds up before it throws", BLOATER.ranged_windup > 0.0)

# IT IS OUTWALKABLE. The whole argument of `projectiles.py`, as arithmetic.
walk = MOVE_SPEED / TILE_SIZE
check(
    f"the disc ({BLOATER.shot_speed_tiles}) is slower than a walk ({walk:.1f})",
    BLOATER.shot_speed_tiles < walk,
)

# IT IS FRAGILE AND SLOW. Both are load-bearing: a durable ranged attacker
# becomes the only thing on screen the player is allowed to think about.
zombie = enemies.ENEMY_TYPES["zombie"]
check("it is frailer than a zombie", BLOATER.max_hp < zombie.max_hp)
check("and slower than one", BLOATER.speed_tiles < zombie.speed_tiles)

# AND IT IS RARE.
weights = dict((t.key, w) for t, w in enemies.SPAWN_TABLE)
check("it is rarer than the wolf", weights["bloater"] < weights["wolf"])


# --- no creature name in ai.py -----------------------------------------------
#
# The promise `EnemyType` makes. It is checked as text because that is the only
# way to check it: a key comparison would work perfectly and would quietly make
# the SECOND ranged creature a code change instead of a stat block.

source = (Path(__file__).resolve().parents[1] / "app" / "ai.py").read_text(encoding="utf-8")
for key in enemies.ENEMY_TYPES:
    check(
        f'ai.py does not know what a "{key}" is',
        not re.search(rf'["\']{re.escape(key)}["\']', source),
    )


# --- the band, driven -------------------------------------------------------

# TOO CLOSE: it must not fire, however long it stands there.
#
# COUNTED IN LAUNCHES (`shot_events`) AND NOT IN LIVE DISCS. A disc that was
# thrown and then expired leaves `room.shots` empty, so asserting on that would
# pass while the rule under test was completely broken — which is exactly what
# it did on the first cut of this file, and the mutation check is what found
# it. `shot_events` accumulates until a broadcast, so it is the honest count.
room, pid = forest_room()
beast, ux, uy = place(room, pid, BLOATER.ranged_min_tiles - 1.0)
# PINNED THERE. Left alone it would close to melee and walk out of the case
# under test within a second; what is being asked is whether the near edge of
# the band holds, not whether the creature can walk.
for _ in range(int(6.0 / DT)):
    beast.x = room.players[pid].x + ux * (BLOATER.ranged_min_tiles - 1.0) * TILE_SIZE
    beast.y = room.players[pid].y + uy * (BLOATER.ranged_min_tiles - 1.0) * TILE_SIZE
    room.step_enemies(DT)
    room.step_shots(DT)
check("inside its band it never throws", not room.shot_events)
check("and never even winds up", beast.windup == 0.0)

# TOO FAR: same, and held at range for the same reason.
room, pid = forest_room()
beast, ux, uy = place(room, pid, BLOATER.ranged_max_tiles + 4.0, seen=False)
for _ in range(int(6.0 / DT)):
    beast.x = room.players[pid].x + ux * (BLOATER.ranged_max_tiles + 4.0) * TILE_SIZE
    beast.y = room.players[pid].y + uy * (BLOATER.ranged_max_tiles + 4.0) * TILE_SIZE
    room.step_enemies(DT)
    room.step_shots(DT)
check("beyond its band it never throws", not room.shot_events)

# INSIDE THE BAND: it winds up, holds, then throws.
room, pid = forest_room()
mid = (BLOATER.ranged_min_tiles + BLOATER.ranged_max_tiles) / 2
beast, ux, uy = place(room, pid, mid)
room.step_enemies(DT)
check("in the band it starts winding up", beast.windup > 0.0)
check("and nothing has left it yet", not room.shots)

# THE WINDUP PLANTS IT. That is what the creature PAYS for reaching, and it is
# the beat the player is being handed.
beast.vx, beast.vy = 40.0, 40.0
room.step_enemies(DT)
check("a winding creature does not move", beast.vx == 0.0 and beast.vy == 0.0)

# AND IT IS ON THE WIRE, as a fraction. A telegraph nobody can see is not one.
row = beast.to_payload()
check("the windup ships", "wu" in row)
# Guarded rather than chained: if the field is missing the line above has
# already said so, and reading it anyway turns a clear failure into a
# KeyError that buries the other checks after it.
check("as a 0..1 fraction", 0.0 <= row.get("wu", -1.0) <= 1.0)

for _ in range(int((BLOATER.ranged_windup + 0.2) / DT)):
    # HELD IN THE BAND. Left alone it would close while winding, and what is
    # under test is the CLOCK, not whether the creature can walk.
    beast.x = room.players[pid].x + ux * mid * TILE_SIZE
    beast.y = room.players[pid].y + uy * mid * TILE_SIZE
    room.step_enemies(DT)
    room.step_shots(DT)
check("the throw happens at the end of the windup", len(room.shot_events) == 1)
check("and the windup is spent", beast.windup == 0.0)
check("the launch reached the wire", len(room.shot_events) == 1)

# A resting creature carries no telegraph — it is a per-tick field on a row
# every creature in the forest pays for.
quiet, _qx, _qy = place(room, pid, 40.0, seen=False)
check("a creature that is not winding up carries no field", "wu" not in quiet.to_payload())

# AND IT RATE-LIMITS ITSELF. Counted in LAUNCHES rather than live discs: a
# disc that expired or hit a tree would make the live count fall, which is not
# what this is asking about.
before = len(room.shot_events)
tick(room, 0.5)
check("it does not throw again immediately", len(room.shot_events) == before)


# --- the disc ----------------------------------------------------------------

room, pid = forest_room()
player = room.players[pid]
start_hp = player.hp
spot = clear_line(room, player, 5.0)
check("the map has an open line to fire down", spot is not None)
if spot:
    ox, oy = spot
    length = math.hypot(player.x - ox, player.y - oy)
    shot = projectiles.Projectile(
        id=1,
        x=ox,
        y=oy,
        dx=(player.x - ox) / length * BLOATER.shot_speed,
        dy=(player.y - oy) / length * BLOATER.shot_speed,
        life=BLOATER.shot_life,
        radius=BLOATER.shot_radius,
        damage=BLOATER.ranged_damage,
    )
    room.shots.append(shot)
    tick(room, BLOATER.shot_life + 0.5)
    check("a disc aimed at a standing player lands", player.hp < start_hp)
    check("and is gone afterwards", not room.shots)

# IT BILLS EACH BODY ONCE. A disc passes THROUGH a party rather than stopping —
# stopping would make the person at the back safe behind their friends, which
# is the opposite of what a ranged attack should do to a formation.
room, pid = forest_room()
player = room.players[pid]
player.hp = player.max_hp
hits = []


class _Spy:
    id = "spy"
    x = 0.0
    y = 0.0
    radius = 8.0


spy = _Spy()
spy.x, spy.y = player.x, player.y


class _NoWalls:
    """A map with nothing in it. What is under test here is the BILLING rule,
    not the map, and a real forest would burst the disc on a tree half the
    time — which is a correct outcome that proves nothing."""

    @staticmethod
    def box_blocked(cx, cy, hw, hh):
        return False


shot = projectiles.Projectile(
    id=2, x=spy.x - 40.0, y=spy.y, dx=60.0, dy=0.0,
    life=4.0, radius=BLOATER.shot_radius, damage=1,
)
live = [shot]
total = 0
for _ in range(int(4.0 / DT)):
    live, impact = projectiles.advance(live, [spy], _NoWalls, DT)
    total += len(impact.hits)
    if not live:
        break
check(f"a disc bills one body exactly once (billed {total})", total == 1)

# IT DOES NOT SHOOT THROUGH WALLS. The wall test runs BEFORE the body test —
# get that order wrong and cover stops working, which is most of what a ranged
# attacker is supposed to make the player think about.
room, pid = forest_room()
player = room.players[pid]
start = player.hp
# A disc launched INSIDE solid ground: it must burst rather than reach anybody.
wall = None
for ty in range(room.world.height):
    for tx in range(room.world.width):
        if room.world.is_solid_tile(tx, ty):
            wall = (tx, ty)
            break
    if wall:
        break
check("the map has a wall to test against", wall is not None)
if wall:
    room.shots.append(
        projectiles.Projectile(
            id=3,
            x=(wall[0] + 0.5) * TILE_SIZE,
            y=(wall[1] + 0.5) * TILE_SIZE,
            dx=0.0,
            dy=0.0,
            life=2.0,
            # Enormous, so a body test that ran first would certainly catch
            # somebody — the point is that it never runs.
            radius=40.0 * TILE_SIZE,
            damage=99,
        )
    )
    room.step_shots(DT)
    check("a disc in a wall bursts", not room.shots)
    check("and bills nobody on the way", player.hp == start)


# --- a spit goes through the one damage door ---------------------------------
#
# The reason `damage_player` is one method: a disc has to meet the shield, the
# worn plate and `Mods.armor` in exactly the order a claw does.

room, pid = forest_room()
player = room.players[pid]
player.hp = player.max_hp
room.shots.append(
    projectiles.Projectile(
        id=4, x=player.x, y=player.y, dx=0.0, dy=0.0,
        life=1.0, radius=BLOATER.shot_radius, damage=BLOATER.ranged_damage,
    )
)
room.step_shots(DT)
check("a spit hurts", player.hp < player.max_hp)
# The drag goes on, for the same reason a claw's does — a player who could
# stand in a firing line at full walking speed has no reason to leave it.
check("and staggers", player.stagger > 0.0)


# --- the wire ----------------------------------------------------------------

payload = BLOATER.client_payload()
for field in ("shotRadius", "rangedMin", "rangedMax"):
    check(f"{field} ships to the client", field in payload)
check("a melee creature ships a zero band", zombie.client_payload()["rangedMax"] == 0)


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
