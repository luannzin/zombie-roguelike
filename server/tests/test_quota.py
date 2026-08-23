"""The night's bill against what the night actually holds.

`rift.SUPPLY_BASE` / `SUPPLY_PER_PAD` are a FIT — they were measured over
generated forests and written down, and a written-down measurement rots the
moment somebody edits `loot.SCENE_COUNTS`, `crates.TYPES`, `scenery.SCENES` or
`mapgen.size_for_pads`. Nothing at runtime notices: the quota just quietly
becomes 20% of a night or 90% of one, and the first symptom is "extraction
feels pointless" or "day 12 is impossible", neither of which anybody would
trace back to a loot table.

So this re-measures. It generates real maps, values everything a party could
find on them, and fails if the fit has drifted.

It also pins the two properties the rewrite exists for, which are ABOUT the
shape rather than about any number:

  * the bill is a real fraction of the map at EVERY day — never the 7% that
    made night one's objective free, and never over the low quarter, which is
    what made night 24 unwinnable
  * it STOPS CLIMBING where the map stops growing. That is the whole fix: past
    day five the forest is a fixed size, so a bill that kept rising would be a
    difficulty curve made of the same woods and a bigger number.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import crates, loot, mapgen, rift

FAILED = []
SAMPLES = 32


def check(label, cond):
    if not cond:
        FAILED.append(label)
        print(f"  FAIL  {label}")


def _item_ev(table):
    """Expected catalog value of one roll off a rarity table."""
    total = sum(table.values())
    out = 0.0
    for rarity, weight in table.items():
        pool = loot.BY_RARITY.get(rarity, ())
        if pool:
            out += (weight / total) * statistics.mean(item.value for item in pool)
    return out


def findable(day: int, seed: int) -> float:
    """Everything on one map a party could turn into quota.

    Ground scatter at face value, plus the EXPECTED value of every container
    standing on it. Ammunition is skipped the way the pad skips it — a box of
    rounds is not cargo.
    """
    world = mapgen.build_forest(seed=seed, day=day, calibres={"pistol"})
    ground = 0.0
    for row in world.loot or []:
        value = row.get("v")
        if value is None:
            item = loot.BY_KEY.get(row.get("k", ""))
            value = item.value if item else 0
        ground += value
    inside = 0.0
    for row in world.crates or []:
        kind = crates.type_of(row.get("t", ""))
        weights = kind.drops
        total = sum(weights.values())
        p_item = weights.get(crates.DROP_ITEM, 0) / total
        inside += p_item * _item_ev(kind.rarity or loot.RARITY_WEIGHTS)
    return ground + inside


# --- the fit still describes the world --------------------------------------
print("  re-measuring generated forests…")
for day, pads in ((1, 1), (3, 2), (5, 3)):
    check(f"day {day} really does land {pads} pad(s)", rift.count_for_day(day) == pads)
    values = sorted(findable(day, 7000 + i) for i in range(SAMPLES))
    p25 = values[len(values) // 4]
    predicted = rift.night_supply(pads)
    drift = abs(p25 - predicted) / max(1.0, p25)
    print(f"    {pads} pad(s): measured p25 {p25:6.0f}   fit {predicted:6.0f}   drift {drift * 100:4.1f}%")
    check(
        f"the supply fit still holds for {pads} pad(s) "
        f"(measured {p25:.0f}, fit {predicted:.0f})",
        drift <= 0.10,
    )


# --- the bill is a real share of the night, at every day --------------------
for day in range(1, 31):
    pads = rift.count_for_day(day)
    need = rift.night_need(day, pads)
    supply = rift.night_supply(pads)
    share = need / supply
    # THE FLOOR. Night one used to ask 7% — an objective cleared by accident,
    # which is the whole reason nothing about exploration was ever a decision.
    check(f"day {day}: the bill is worth walking for (share {share:.0%})", share >= 0.25)
    # THE CEILING. The measurement above is the LOW QUARTER, so a bill over it
    # is a bill a bad seed cannot pay.
    check(f"day {day}: the bill fits inside a bad night (share {share:.0%})", share <= 0.60)


# --- and it stops where the map stops ---------------------------------------
plateau_day = 12
before = rift.night_need(plateau_day, rift.count_for_day(plateau_day))
for day in (15, 20, 30, 60):
    later = rift.night_need(day, rift.count_for_day(day))
    check(f"day {day} asks no more than day {plateau_day}", later == before)

check(
    "the map really has stopped growing by then",
    mapgen.size_for_pads(rift.count_for_day(plateau_day))
    == mapgen.size_for_pads(rift.count_for_day(60)),
)

# It does still climb before that, or the day would mean nothing at all.
check(
    "the bill climbs over the days the map is still growing",
    rift.night_need(5, rift.count_for_day(5)) > rift.night_need(1, rift.count_for_day(1)),
)

# --- one pad's share of it --------------------------------------------------
for day in (1, 5, 12):
    pads = rift.count_for_day(day)
    per = rift.pad_need(day, pads)
    check(
        f"day {day}: the pads together ask for at least the night's bill",
        per * pads >= rift.night_need(day, pads),
    )


print("ok" if not FAILED else f"FAILED ({len(FAILED)})")
sys.exit(1 if FAILED else 0)
