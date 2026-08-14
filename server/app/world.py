"""Tile grid world: map data + collision queries.

The grid is a plain 2D array of ints so future maps can be authored as JSON,
Python literals or generated procedurally.

    0 FLOOR   walkable
    1 ROCK    solid boulder
    2 TREE    solid trunk
    3 FIRE    solid campfire — a lit tile, and a landmark
    4 VOID    solid, unpainted — the black exit cut through the camp treeline

Only FLOOR is walkable, and the solidity test is `!= FLOOR` rather than a list
of known blockers: adding a fifth tile kind (water, rubble, a bush) is then a
generator change and a client sprite, never a change to collision, pathing or
raycasting. `WALL` remains as an alias for ROCK so hand-drawn ASCII maps keep
building. VOID is the same contract with no art: the renderer leaves it as the
clear colour, which is how a corridor through the trees reads as a hole.

FIRE is a tile rather than an entity for exactly that reason. It blocks, it
casts a shadow and it stops a shot with no special case anywhere, and the client
reads the same tiles to place the animated sprite and the light it throws — so
the fire in the camp is in one place on the wire, not three.

Movement is continuous (float world pixels); the grid only answers "is this box
/ ray blocked". Collision boxes are axis-aligned rectangles given as half
extents (hw, hh) around the entity position — see config.py for why the box is
smaller than the sprite.
"""

from __future__ import annotations

from .config import TILE_SIZE

FLOOR = 0
ROCK = 1
TREE = 2
FIRE = 3
VOID = 4

# Legacy name: '#' in an ASCII map is a rock.
WALL = ROCK

_EPS = 1e-4


class TileMap:
    def __init__(self, tiles: list[list[int]], seed: int = 0):
        self.tiles = tiles
        # Shipped to the client, which hashes it with tile coordinates to place
        # decoration (grass tufts, prop variants). Sending a seed instead of a
        # decoration layer keeps the map payload the size of the map.
        self.seed = seed
        self.height = len(tiles)
        self.width = len(tiles[0]) if tiles else 0
        self.tile_size = TILE_SIZE
        self.pixel_width = self.width * TILE_SIZE
        self.pixel_height = self.height * TILE_SIZE

    # --- queries ------------------------------------------------------------
    def is_solid_tile(self, tx: int, ty: int) -> bool:
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return True
        return self.tiles[ty][tx] != FLOOR

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

    def fire_points(self) -> list[tuple[float, float]]:
        """Every FIRE tile, as the BASE of its flame in world pixels.

        Bottom-centre rather than centre, because that is where the sprite is
        anchored and where the light comes from — the client derives both from
        the same tiles, so the seat ring, the glow and the art cannot drift.
        """
        return [
            (tx * TILE_SIZE + TILE_SIZE / 2, (ty + 1) * TILE_SIZE)
            for ty in range(self.height)
            for tx in range(self.width)
            if self.tiles[ty][tx] == FIRE
        ]

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
            "seed": self.seed,
            "tiles": self.tiles,
        }
