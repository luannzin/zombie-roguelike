"""Weather that does something, and the mirror it is half of.

Run:  python tests/test_weather.py   (from server/)

Weather used to be PAINT. It was rolled, shipped and drawn — a rainy night was
the same night with a wash over it — which made it the cheapest thing in the
game to notice and the least worth noticing. Two scalars turn it into a thing
the player plays around.

Four things about that are invisible from inside the game:

  * SIGHT IS SYMMETRIC AND THE TWO SIDES ARE IN DIFFERENT LANGUAGES. `ai.look`
    and the client's `render/fov.ts` multiply by the same shipped number, and
    the failure when they stop doing that has no symptom at all: the player
    simply gets spotted from further away than the wash they were shown said
    they could be. Nobody reports that — they report the game feeling unfair.
  * A COAT MUST CUT BOTH REACHES. Fog does not care whether you are carrying a
    lamp, and a scalar applied to the naked-eye reach alone would quietly make
    the lantern a stealth item on foggy nights.
  * THE NOISE SCALAR HAS ONE DOOR. Every sound in the game — a gunshot, the
    siren, a horde's howl, a vault being forced — goes through `ai.hear`, and a
    coat applied at the call sites instead would be missing from the next one
    somebody adds.
  * THEY ARE AN INVERTED PAIR, not a difficulty ladder. Rain is the night you
    can see and cannot hear; fog is the night you can hear and cannot see. If
    one coat ever became strictly worse than another on both axes, weather
    would go back to being a difficulty roll wearing a costume.

Plain script: run it from `server/`, it prints `ok`.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, enemies, zones  # noqa: E402
from app.config import TILE_SIZE, client_config  # noqa: E402
from app.entities import Player  # noqa: E402
from app.world import FLOOR, TileMap  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


def open_map(size: int = 90) -> TileMap:
    """Nothing but floor. What is under test is reach, never occlusion."""
    return TileMap([[FLOOR] * size for _ in range(size)])


def watcher(world: TileMap) -> enemies.Enemy:
    beast = enemies.Enemy(
        id="e1",
        type=enemies.ENEMY_TYPES["zombie"],
        x=10.0 * TILE_SIZE,
        y=10.0 * TILE_SIZE,
    )
    beast.aim_x, beast.aim_y = 1.0, 0.0
    return beast


def body(world: TileMap, tiles_east: float, lantern: bool) -> Player:
    p = Player(id="p1", name="A", color="#fff")
    p.x = (10.0 + tiles_east) * TILE_SIZE
    p.y = 10.0 * TILE_SIZE
    p.last_input.lantern = lantern
    return p


def furthest_seen(lantern: bool, scale: float) -> float:
    """The greatest distance, in tiles, at which `look` still finds a body."""
    world = open_map()
    beast = watcher(world)
    best = 0.0
    step = 0.05
    tiles = step
    while tiles < 60.0:
        if ai.look(beast, [body(world, tiles, lantern)], world, scale) is None:
            break
        best = tiles
        tiles += step
    return best


# --- the table ---------------------------------------------------------------

check("every rolled coat has a rule", set(zones.WEATHER_RULES) >= {
    zones.WEATHER_CLEAR, zones.WEATHER_RAIN, zones.WEATHER_FOG,
})

clear = zones.rule_for(zones.WEATHER_CLEAR)
rain = zones.rule_for(zones.WEATHER_RAIN)
fog = zones.rule_for(zones.WEATHER_FOG)

# CLEAR IS THE BASELINE. Not an absence of a rule — the reference the other two
# are read against, and the only night where what the player learned about
# ranges is true.
check("clear leaves sight alone", clear.sight == 1.0)
check("clear leaves sound alone", clear.noise == 1.0)

# EACH OF THE OTHER TWO CHANGES SOMETHING MEASURABLE.
check("fog cuts sight", fog.sight < 1.0)
check("rain cuts sound", rain.noise < 1.0)

# AND THEY ARE AN INVERTED PAIR. If either were worse than the other on BOTH
# axes it would be strictly harder, and weather would go back to being a
# difficulty roll in a costume.
check(
    "fog is the blind night and rain is the deaf one",
    fog.sight < rain.sight and rain.noise < fog.noise,
)
# Neither may dominate the other.
for a, b, an, bn in ((fog, rain, "fog", "rain"), (rain, fog, "rain", "fog")):
    check(
        f"{an} is not strictly worse than {bn} on both axes",
        not (a.sight <= b.sight and a.noise <= b.noise),
    )

# An unknown coat plays as a clear night rather than taking the room down.
check("an unknown coat falls back to clear", zones.rule_for("hail") == clear)


# --- sight, driven -----------------------------------------------------------
#
# Against `look` itself rather than against arithmetic, because the arithmetic
# is what is under test.

for lantern in (False, True):
    which = "a lit player" if lantern else "a shape in the dark"
    base = furthest_seen(lantern, 1.0)
    check(f"{which} is seen at all on a clear night", base > 1.0)
    misty = furthest_seen(lantern, fog.sight)
    check(f"fog shortens the cone against {which}", misty < base)
    # A COAT MUST CUT BOTH REACHES. Applied to the naked eye alone, the lantern
    # would become a stealth item on foggy nights — which nothing would report.
    check(
        f"and by the coat's own factor against {which} "
        f"(expected ~{base * fog.sight:.1f}, got {misty:.1f})",
        abs(misty - base * fog.sight) < 0.3,
    )

# Rain touches sight too, lightly — it is the night you can still see.
check("rain barely touches sight", 0.8 < rain.sight < 1.0)


# --- sound, driven -----------------------------------------------------------


def heard_by(scale: float, tiles: float) -> bool:
    """Does a creature `tiles` away notice a 10-tile noise under this coat?"""
    world = open_map()
    beast = watcher(world)
    beast.x = (10.0 + tiles) * TILE_SIZE
    beast.mode = ai.MODE_IDLE
    beast.awareness = 0.0
    noise = ai.Noise(x=10.0 * TILE_SIZE, y=10.0 * TILE_SIZE, radius=10.0 * TILE_SIZE)
    ai.hear([beast], noise, {}, scale)
    return beast.awareness > 0.0

check("a shot carries its full radius on a clear night", heard_by(clear.noise, 9.0))
check("and not past it", not heard_by(clear.noise, 11.0))
# RAIN EATS SOUND. The same shot, the same distance, unheard.
check("rain swallows the same shot", not heard_by(rain.noise, 9.0))
check("but not one right on top of it", heard_by(rain.noise, 3.0))
# FOG CARRIES IT FURTHER. Still air, and the reason a gunshot is a much worse
# idea on a foggy night than on any other.
check("fog carries a shot past its usual reach", heard_by(fog.noise, 10.5))

# THE TAPER USES THE SCALED RADIUS. Against the raw one, the last creature to
# hear a shot on a rainy night would react as hard as one standing on it.
world = open_map()
near = watcher(world)
near.x = (10.0 + 1.0) * TILE_SIZE
near.mode = ai.MODE_IDLE
far = watcher(world)
far.id = "e2"
far.x = (10.0 + 5.0) * TILE_SIZE
far.mode = ai.MODE_IDLE
noise = ai.Noise(x=10.0 * TILE_SIZE, y=10.0 * TILE_SIZE, radius=10.0 * TILE_SIZE)
ai.hear([near, far], noise, {}, rain.noise)
check("the edge of a muffled sound is still quieter than its middle",
      far.awareness < near.awareness)


# --- the mirror --------------------------------------------------------------
#
# The one with no symptom. Sight is symmetric and the two halves are in
# different languages.

cfg = client_config()
check("the weather table ships", "weather" in cfg)
for key, rule in zones.WEATHER_RULES.items():
    row = cfg["weather"].get(key)
    check(f"{key} ships", row is not None)
    if row:
        check(f"{key}'s sight scalar ships unchanged", row["sight"] == rule.sight)
        check(f"{key}'s noise scalar ships unchanged", row["noise"] == rule.noise)

# AND NEITHER SIDE MAY HARDCODE IT. The client reads the table off the config;
# `ai.py` must not carry a copy of any of these numbers, or the mirror is two
# independent numbers that happen to agree today.
source = (Path(__file__).resolve().parents[1] / "app" / "ai.py").read_text(encoding="utf-8")
for key, rule in zones.WEATHER_RULES.items():
    if rule.sight == 1.0:
        continue
    check(
        f"ai.py does not hardcode {key}'s sight scalar",
        not re.search(rf"(?<![\d.]){re.escape(str(rule.sight))}(?![\d])", source),
    )


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
