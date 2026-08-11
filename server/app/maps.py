"""Map data + builders.

Two authoring styles are supported so future maps can come from either:

  * `from_ascii()`  — hand-drawn maps ('#' wall, anything else floor)
  * `from_rects()`  — declarative wall rectangles, easy to tweak/generate

Both produce a plain `list[list[int]]`, which is also the JSON wire format,
so a map can equally well be loaded from a .json file later.
"""

from __future__ import annotations

from .world import FLOOR, WALL, TileMap

ARENA_WIDTH = 64
ARENA_HEIGHT = 40

# (x, y, w, h) wall blocks in tile coordinates.
ARENA_WALLS: list[tuple[int, int, int, int]] = [
    # outer border
    (0, 0, ARENA_WIDTH, 1),
    (0, ARENA_HEIGHT - 1, ARENA_WIDTH, 1),
    (0, 0, 1, ARENA_HEIGHT),
    (ARENA_WIDTH - 1, 0, 1, ARENA_HEIGHT),
    # top-left room
    (8, 6, 12, 1),
    (8, 6, 1, 8),
    (16, 12, 4, 1),
    # top-right pillars
    (44, 5, 3, 3),
    (52, 9, 3, 3),
    (44, 13, 3, 3),
    # central cross
    (28, 16, 10, 2),
    (31, 12, 2, 4),
    (31, 18, 2, 6),
    # bottom-left blocks
    (7, 24, 8, 2),
    (7, 30, 2, 6),
    (13, 30, 8, 2),
    # bottom-right room
    (44, 26, 14, 1),
    (57, 26, 1, 9),
    (44, 34, 8, 1),
    # scattered cover
    (22, 4, 2, 2),
    (38, 30, 2, 2),
    (24, 33, 3, 2),
    (48, 18, 2, 4),
    (18, 19, 3, 2),
]


def from_rects(width: int, height: int, rects) -> list[list[int]]:
    tiles = [[FLOOR for _ in range(width)] for _ in range(height)]
    for x, y, w, h in rects:
        for ty in range(y, min(y + h, height)):
            for tx in range(x, min(x + w, width)):
                if tx >= 0 and ty >= 0:
                    tiles[ty][tx] = WALL
    return tiles


def from_ascii(rows: list[str]) -> list[list[int]]:
    return [[WALL if ch == "#" else FLOOR for ch in row] for row in rows]


def build_arena() -> TileMap:
    return TileMap(from_rects(ARENA_WIDTH, ARENA_HEIGHT, ARENA_WALLS))
