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
    4 VOID    dark gap — winding forest floor between trees. Blocks light
              never; blocks bodies UNLESS an extraction `egress` is open,
              in which case it is the corridor you walk into to leave.
              Camp and the forest arrival stay solid (no egress). The
              client paints ground and crushes a darkness falloff around
              the path so it reads as a hole in the woods.
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
    7 BRICK    solid MASONRY WALL — the merchant's shop, and the only
              built structure in the game. Solid and OPAQUE, like PROP: a
              wall is a wall. It is its own kind rather than ROCK because
              the client draws it as a course of brick with a face and a
              cap, autotiled off its neighbours, and a boulder sprite in a
              doorway would be the whole illusion gone.
    8 TILEFLOOR
              WALKABLE BRICK FLOOR — the shop's interior ground. The one
              tile kind other than FLOOR a body may stand on, and the only
              reason the solidity rule below is a pair rather than a single
              comparison. Transparent to light: it is a floor.

Solidity is "not one of the two GROUNDS" with one named exception: VOID is
walkable while `egress` is set. SIGHT is `blocks_sight`, which is the narrower
question and has its own exceptions: FIRE (knee-high, and it is the thing doing
the lighting), VOID (a gap between trees — light falls in), LOW and TILEFLOOR.

THERE ARE TWO WALKABLE GROUNDS AND THAT IS WHY THE RULE IS `GROUNDS`, NOT
`!= FLOOR`. It was a single comparison for the whole life of the project and
that was right while every map was made of soil. The shop's interior is a laid
brick floor — a different surface the client bakes from a different sheet — and
the choice was between a second ground kind or painting brick over FLOOR from
the store layer and hoping the two never disagreed about where the building
was. A tile kind is the honest answer: the grid says what the ground IS, one
frozenset says which grounds carry a body, and adding a third surface later is
one entry rather than a new special case. The cost is that this rule is
MIRRORED in `client/src/game/world.ts` and a change to one side alone desyncs
prediction — see AGENTS.md's mirror list.

Adding a new BLOCKER is still nothing at all: anything outside `GROUNDS` is
solid by default. `WALL` remains as an alias for ROCK so hand-drawn ASCII maps
keep building. VOID is floor art with no prop: a shadowed winding path, not a
black rectangle.

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

from .config import BUSH_CHANCE, TILE_SIZE

FLOOR = 0
ROCK = 1
TREE = 2
FIRE = 3
VOID = 4
PROP = 5
LOW = 6
BRICK = 7
TILEFLOOR = 8

# Legacy name: '#' in an ASCII map is a rock.
WALL = ROCK

#: THE TILE KINDS A BODY MAY STAND ON. Everything else is solid.
#:
#: Mirrored by `GROUNDS` in client/src/game/world.ts. The two must hold the
#: same members or prediction and the server disagree about where a wall is,
#: which shows up as rubber-banding along the shop's doorway rather than as an
#: error anywhere.
GROUNDS = frozenset((FLOOR, TILEFLOOR))

#: WHAT LIGHT PASSES THROUGH. Wider than `GROUNDS` and deliberately so: a
#: bonfire is knee-high and is the source, VOID is a gap between trunks, LOW is
#: cover you look over. Mirrored by `CLEAR` in client/src/game/world.ts.
CLEAR = frozenset((FLOOR, TILEFLOOR, FIRE, VOID, LOW))

_EPS = 1e-4


def tile_hash(tx: int, ty: int, seed: int, salt: int = 0) -> float:
    """Deterministic 0..1 from a tile coordinate. Mirrors `render/terrain.ts`.

    Bit-for-bit, not merely "a hash": the client places decoration with this
    and the server now reads that placement back (`TileMap.bush_at`), so the
    two must agree on every tile of every map. `Math.imul` is a 32-bit signed
    multiply and `>>>` an unsigned shift, hence the masking here — a plain
    Python `*` would agree for the first few thousand tiles and then quietly
    stop.
    """
    h = _i32(_imul(tx, 374761393) + _imul(ty, 668265263) + _imul((seed ^ salt), 2246822519))
    h = _i32(h ^ (_u32(h) >> 13))
    h = _imul(h, 1274126177)
    return (_u32(h ^ (_u32(h) >> 16))) / 4294967295


def _u32(v: int) -> int:
    return v & 0xFFFFFFFF


def _i32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _imul(a: int, b: int) -> int:
    return _i32(_i32(a) * _i32(b))


class TileMap:
    def __init__(
        self,
        tiles: list[list[int]],
        seed: int = 0,
        scenery: dict | None = None,
        loot: list | None = None,
        crates: list | None = None,
        rifts: list | None = None,
        entrance: dict | None = None,
        egress: dict | None = None,
        store: dict | None = None,
        nests: list[tuple[float, float, int]] | None = None,
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
        # draws. Forest carries it; camp maps leave it empty.
        self.crates = crates or []
        # Extraction points' geometry. Empty on a map that has none (the camp,
        # and any forest with nowhere to put one). Held as payloads for the
        # same reason `scenery` is: the room hydrates live `rift.Rift` rows
        # from it and this copy is only ever forwarded.
        self.rifts = list(rifts or [])
        # Forest arrival corridor. Geometry is placed at generation; `state`
        # is rewritten as the woods swallow it. Camp maps leave it empty.
        self.entrance = entrance
        # Extraction exit, carved when the feed quota is paid. Absent until
        # then, and absent on the camp. Same shape as `entrance`.
        self.egress = egress
        # The shop's fixtures: the merchant, his tables and what is on them,
        # the lamps and the mat (`server/app/store.py`). Absent everywhere
        # else. Held as the payload for the same reason `scenery` is — the
        # room hydrates live `store.Stand` rows out of it and forwards the
        # rest verbatim.
        self.store = store
        # Where the map wants creatures STANDING when the party arrives, as
        # `(x, y, count)` in world pixels. `count` is 0 for a landmark whose
        # guard is the room's to size (the sanctuary) and a small number for a
        # scene that simply kept its dead — see `mapgen.HAUNT_SCENES`.
        #
        # Never on the wire: the enemies themselves ride the snapshot like any
        # other, and a client that was told where the nests are would be told
        # where the shrine is before it can see it.
        self.nests = list(nests or [])
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
        tile = self.tiles[ty][tx]
        if tile == VOID:
            return self.egress is None
        return tile not in GROUNDS

    def is_solid_at(self, x: float, y: float) -> bool:
        return self.is_solid_tile(int(x // TILE_SIZE), int(y // TILE_SIZE))

    def blocks_sight(self, tx: int, ty: int) -> bool:
        """Whether this tile stops LIGHT. Mirrors `TileMap.blocksSight`.

        Narrower than solidity, and the difference is not cosmetic: the client
        draws exactly this, so an enemy that could not see over a log the
        player can see over would be enforcing a rule the screen contradicts.
        The exceptions are `CLEAR` — a bonfire is knee-high and is the light
        source, VOID is a gap between trunks that light falls into, LOW is
        cover you look over, and TILEFLOOR is a floor.
        """
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return True
        return self.tiles[ty][tx] not in CLEAR

    def bush_at(self, tx: int, ty: int) -> bool:
        """Whether the client draws a bush on this tile. Mirrors `layers/terrain`.

        There is no bush in `tiles`. Undergrowth is DERIVED — the map ships a
        seed and both sides hash it with the tile coordinate, which is how a
        forest's worth of decoration costs four bytes on the wire. That made
        bushes invisible to the simulation for as long as they were only
        decoration; they are cover now (`ai.look`), so the server re-derives
        the same tiles rather than anybody shipping a mask.

        `salt=13` and the FLOOR test are the client's, verbatim. Change one
        and undergrowth moves under the rule that reads it.

        The camp's hearth mask is NOT mirrored. It only suppresses decoration
        around the campfire, and nothing hunts in the camp.
        """
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return False
        if self.tiles[ty][tx] != FLOOR:
            return False
        return tile_hash(tx, ty, self.seed, 13) < BUSH_CHANCE

    def bush_at_point(self, x: float, y: float) -> bool:
        return self.bush_at(int(x // TILE_SIZE), int(y // TILE_SIZE))

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
            "rifts": list(self.rifts),
            "entrance": self.entrance,
            "egress": self.egress,
            "store": self.store,
        }
