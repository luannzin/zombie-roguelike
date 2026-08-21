"""The forest is sized to the night it has to hold.

One pad is a third of the ground, three is the full map, and the scenes shrink
with it — nothing at runtime notices a map that grew without its stories, or a
night whose only pad is a long walk from anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import mapgen, rift
from app.maps import count_reachable
from app.world import FLOOR

full = mapgen.size_for_pads(3)
assert full == (mapgen.DEFAULT_WIDTH, mapgen.DEFAULT_HEIGHT), full
one, two = mapgen.size_for_pads(1), mapgen.size_for_pads(2)
assert one[0] < two[0] < full[0] and one[1] < two[1] < full[1], (one, two)
# Area per pad is the constant, so the aspect must not drift with it.
for size in (one, two, full):
    assert abs(size[0] / size[1] - full[0] / full[1]) < 0.02, size
assert mapgen.size_for_pads(0) == one and mapgen.size_for_pads(9) == full

sizes = {}
for day in (1, 3, 5):
    pads = rift.count_for_day(day)
    for seed in range(4100, 4106):
        m = mapgen.build_forest(day=day, seed=seed)
        h, w = len(m.tiles), len(m.tiles[0])
        assert (w, h) == mapgen.size_for_pads(pads), (day, w, h)
        assert len(m.rifts) == pads, (day, seed, len(m.rifts))
        floor = sum(row.count(FLOOR) for row in m.tiles)
        assert count_reachable(m.tiles) == floor, (day, seed)
        sizes.setdefault(pads, []).append(len(m.scenery["props"]))

# Fewer pads, fewer stories: the map and its content are one decision.
assert max(sizes[1]) < min(sizes[3]), sizes

print("ok")
