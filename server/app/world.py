"""Tile grid world: map data + collision queries.

The grid is a plain 2D array of ints so future maps can be authored as JSON,
Python literals or generated procedurally. 0 = walkable floor, 1 = solid wall.

Movement is continuous (float world pixels); the grid only answers "is this box
/ ray blocked". Collision boxes are axis-aligned rectangles given as half
extents (hw, hh) around the entity position — see config.py for why the box is
smaller than the sprite.
"""

from __future__ import annotations

from .config import TILE_SIZE

FLOOR = 0
WALL = 1

_EPS = 1e-4


class TileMap:
    def __init__(self, tiles: list[list[int]]):
        self.tiles = tiles
        self.height = len(tiles)
        self.width = len(tiles[0]) if tiles else 0
        self.tile_size = TILE_SIZE
        self.pixel_width = self.width * TILE_SIZE
        self.pixel_height = self.height * TILE_SIZE

    # --- queries ------------------------------------------------------------
    def is_solid_tile(self, tx: int, ty: int) -> bool:
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return True
        return self.tiles[ty][tx] == WALL

    def is_solid_at(self, x: float, y: float) -> bool:
        return self.is_solid_tile(int(x // TILE_SIZE), int(y // TILE_SIZE))

    def box_blocked(self, cx: float, cy: float, hw: float, hh: float) -> bool:
        """Axis-aligned box centred on (cx, cy) with half-extents (hw, hh)."""
        x0 = int((cx - hw) // TILE_SIZE)
        x1 = int((cx + hw) // TILE_SIZE)
        y0 = int((cy - hh) // TILE_SIZE)
        y1 = int((cy + hh) // TILE_SIZE)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if self.is_solid_tile(tx, ty):
                    return True
        return False

    def free_spawn_points(self, hw: float, hh: float) -> list[tuple[float, float]]:
        """Tile centres where a (hw, hh) box fits without touching a wall."""
        pts = []
        for ty in range(self.height):
            for tx in range(self.width):
                if self.tiles[ty][tx] != FLOOR:
                    continue
                cx = tx * TILE_SIZE + TILE_SIZE / 2
                cy = ty * TILE_SIZE + TILE_SIZE / 2
                if not self.box_blocked(cx, cy, hw, hh):
                    pts.append((cx, cy))
        return pts

    # --- movement -----------------------------------------------------------
    def move_axis(
        self, x: float, y: float, hw: float, hh: float, delta: float, axis: int
    ) -> float:
        """Move one axis with wall snapping. axis 0 = x, 1 = y.

        Mirrored exactly by client/src/game/world.ts — keep both in sync.
        """
        if delta == 0.0:
            return x if axis == 0 else y

        if axis == 0:
            nx = x + delta
            if not self.box_blocked(nx, y, hw, hh):
                return nx
            if delta > 0:
                col = int((nx + hw) // TILE_SIZE)
                return col * TILE_SIZE - hw - _EPS
            col = int((nx - hw) // TILE_SIZE)
            return (col + 1) * TILE_SIZE + hw + _EPS

        ny = y + delta
        if not self.box_blocked(x, ny, hw, hh):
            return ny
        if delta > 0:
            row = int((ny + hh) // TILE_SIZE)
            return row * TILE_SIZE - hh - _EPS
        row = int((ny - hh) // TILE_SIZE)
        return (row + 1) * TILE_SIZE + hh + _EPS

    def to_payload(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "tileSize": TILE_SIZE,
            "tiles": self.tiles,
        }
