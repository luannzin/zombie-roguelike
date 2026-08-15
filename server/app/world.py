"""Tile grid world: map data + collision queries.

The grid is a plain 2D array of ints so future maps can be authored as JSON,
Python literals or generated procedurally.

    0 FLOOR   walkable
    1 ROCK    solid boulder
    2 TREE    solid TRUNK — one tile, the contact. The canopy is 1.5 tiles
              of art on the tiles above and is not a wall; walking behind a
              tree is walking on those tiles. A second TREE there is another
              trunk, not this one's leaves.
    3 FIRE    solid campfire — a lit tile, and a landmark
    4 VOID    solid gap — winding forest floor between trees, too dark to
              walk into. Blocks bodies, not light; the client paints ground
              and crushes a darkness falloff around the path so it reads as
              a hole in the woods, not as a missing texture or a corridor.
    5 PROP    solid DOORSTEP of a BUILDING placed by scenery.py — one tile
              tall, at the contact. The client paints ground here and draws
              nothing: the cabin or tent sprite covers it, including the
              roof you walk behind. Blocks light too — a cabin is a cabin.
    6 LOW     WAIST-HIGH COVER: a fallen log, a crate, a fence rail, a signpost.
              Solid to bodies and to BULLETS, transparent to LIGHT. That
              combination is the whole reason it is its own kind. Making these
              PROP would put a hard shadow wedge behind every crate and turn a
              fence run into a wall of black, which is both wrong and ugly;
              leaving them walkable throws away the best cover the forest has.
              You can see your target over the log and still not shoot through
              it, which is what cover is supposed to mean.

Solidity is `!= FLOOR`, so movement, pathing and hitscan pick up a new kind for
free. SIGHT is `blocks_sight`, which is the narrower question and has its own
exceptions: FIRE (knee-high, and it is the thing doing the lighting), VOID (a
gap between trees — light falls in) and LOW.

Only FLOOR is walkable, and the solidity test is `!= FLOOR` rather than a list
of known blockers: adding a fifth tile kind (water, rubble, a bush) is then a
generator change and a client sprite, never a change to collision, pathing or
raycasting. `WALL` remains as an alias for ROCK so hand-drawn ASCII maps keep
building. VOID is the same solidity contract as a tree, with floor art and
no prop: the camp exit is a shadowed winding path, not a black rectangle.

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
PROP = 5
LOW = 6

# Legacy name: '#' in an ASCII map is a rock.
WALL = ROCK

_EPS = 1e-4


class TileMap:
    def __init__(
        self,
        tiles: list[list[int]],
        seed: int = 0,
        scenery: dict | None = None,
        loot: list | None = None,
        crates: list | None = None,
    ):
        self.tiles = tiles
        # The story laid over this map: a legend plus one compact row per
        # drawable, straight from `scenery.to_payload`. Held as the payload
        # rather than as objects because nothing on the server reads it back —
        # it is placed once at generation time and forwarded verbatim.
        self.scenery = scenery or {"propKinds": [], "props": []}
        # Initial loot rows from `loot.scatter`. The room hydrates live drops
        # from this; collected items do not write back. Camp maps leave it empty.
        self.loot = loot or []
        # Live crates pulled out of scenery. The stamp already claimed their
        # LOW tiles; this list is what the room smashes and what the client
        # draws. Camp and forest both carry it.
        self.crates = crates or []
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

    def blocks_sight(self, tx: int, ty: int) -> bool:
        """Whether this tile stops LIGHT. Mirrors `TileMap.blocksSight`.

        Narrower than solidity, and the difference is not cosmetic: the client
        draws exactly this, so an enemy that could not see over a log the
        player can see over would be enforcing a rule the screen contradicts.
        Three exceptions — a bonfire is knee-high and is the light source, VOID
        is a gap between trunks that light falls into, and LOW is cover you
        look over.
        """
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return True
        tile = self.tiles[ty][tx]
        return tile != FLOOR and tile != FIRE and tile != VOID and tile != LOW

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

    def set_tile(self, tx: int, ty: int, kind: int) -> None:
        """Rewrite one cell. A smashed crate turns its LOW tile back to FLOOR."""
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return
        self.tiles[ty][tx] = kind

    def to_payload(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "tileSize": TILE_SIZE,
            "seed": self.seed,
            "tiles": self.tiles,
            **self.scenery,
            "crates": list(self.crates),
        }
