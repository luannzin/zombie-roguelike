"""Map data + builders.

Maps are plain `list[list[int]]` (0 = floor, 1 = wall), which is also the JSON
wire format, so a map can equally well be loaded from a .json file or produced
by a generator later.

Two authoring styles:
  * `from_ascii()` — hand-drawn maps, '#' = wall. This is the readable one.
  * `from_rects()` — declarative wall rectangles, easy to generate.

ARENA is 64x40 tiles = 1024x640 world px at TILE_SIZE 16, comfortably larger
than the viewport so the camera always has somewhere to go. It is symmetric on
both axes, fully connected (validated at build time — no sealed pockets), and
built from lanes and cover rather than tight corridors so hitscan lines of
sight stay interesting.

Editing: just redraw the ASCII. Rows must all be the same length and the floor
must stay connected; `build_arena()` checks both.
"""

from __future__ import annotations

from .world import FLOOR, WALL, TileMap

ARENA: list[str] = [
    "################################################################",
    "#..............................................................#",
    "#..............................................................#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..........####......####..........#.............#",
    "#.............#.....##....................##.....#.............#",
    "#...................##....................##...................#",
    "#.............................####.............................#",
    "#.............................####.............................#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#..#####..#####..................................#####..#####..#",
    "#..............................................................#",
    "#.....#####...........#....##########....#...........#####.....#",
    "#.....#####...........#....##########....#...........#####.....#",
    "#.....................#....##########....#.....................#",
    "#.....................#....##########....#.....................#",
    "#.....#####...........#....##########....#...........#####.....#",
    "#.....#####...........#....##########....#...........#####.....#",
    "#..............................................................#",
    "#..#####..#####..................................#####..#####..#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............................####.............................#",
    "#.............................####.............................#",
    "#...................##....................##...................#",
    "#.............#.....##....................##.....#.............#",
    "#.............#..........####......####..........#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#.............#..................................#.............#",
    "#..............................................................#",
    "#..............................................................#",
    "################################################################",
]


def from_ascii(rows: list[str]) -> list[list[int]]:
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("ascii map rows must all be the same length")
    return [[WALL if ch == "#" else FLOOR for ch in row] for row in rows]


def from_rects(width: int, height: int, rects) -> list[list[int]]:
    tiles = [[FLOOR for _ in range(width)] for _ in range(height)]
    for x, y, w, h in rects:
        for ty in range(max(0, y), min(y + h, height)):
            for tx in range(max(0, x), min(x + w, width)):
                tiles[ty][tx] = WALL
    return tiles


def count_reachable(tiles: list[list[int]]) -> int:
    """Flood fill from the first floor tile. Guards against sealed-off rooms."""
    height = len(tiles)
    width = len(tiles[0])
    start = None
    for ty in range(height):
        for tx in range(width):
            if tiles[ty][tx] == FLOOR:
                start = (tx, ty)
                break
        if start:
            break
    if not start:
        return 0

    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and tiles[ny][nx] == FLOOR:
                if (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
    return len(seen)


def build_arena() -> TileMap:
    tiles = from_ascii(ARENA)
    floor = sum(row.count(FLOOR) for row in tiles)
    reachable = count_reachable(tiles)
    if reachable != floor:
        raise ValueError(f"arena has {floor - reachable} unreachable floor tiles")
    return TileMap(tiles)
