"""Openables must not stand inside each other, and a scene may not hoard them.

Run:  python tests/test_scenery_containers.py   (from server/)

A container claims its tile as LOW (`scenery._cells`) and the room hydrates it
as something to smash or open. Two on the same tile is one sprite drawn inside
another over ground that can only be cleared once — invisible in a screenshot,
obvious the moment somebody tries to open the second one.
"""

from __future__ import annotations

import math
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import scenery  # noqa: E402
from app.config import TILE_SIZE  # noqa: E402

MAPS = 60


def _containers(props) -> Counter:
    """Container props by the TILE they contact — the anchoring `_cells` uses."""
    cells: Counter = Counter()
    for prop in props:
        if prop.kind in scenery.CONTAINER_KINDS:
            cells[(
                math.floor(prop.x / TILE_SIZE + 0.5),
                math.floor(prop.y / TILE_SIZE - 1e-6),
            )] += 1
    return cells


def test_no_two_containers_share_a_tile() -> None:
    for seed in range(MAPS):
        tiles = [[0] * 70 for _ in range(70)]
        population = scenery.populate(tiles, random.Random(seed))
        stacked = [cell for cell, n in _containers(population.props).items() if n > 1]
        assert not stacked, f"seed {seed}: {len(stacked)} stacked container tiles"


def test_scene_container_cap() -> None:
    for seed in range(MAPS):
        rng = random.Random(seed)
        for _, builder, _weight in scenery.SCENES:
            layout = scenery._thin_containers(builder(rng), rng)
            kept = sum(
                1
                for piece in layout.pieces
                if piece.kind in scenery.CONTAINER_KINDS and piece.layer == scenery.STANDING
            )
            assert kept <= scenery.MAX_CONTAINERS, f"seed {seed}: {kept} containers"


if __name__ == "__main__":
    test_no_two_containers_share_a_tile()
    test_scene_container_cap()
    print("ok")
