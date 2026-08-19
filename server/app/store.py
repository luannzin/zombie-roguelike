"""The merchant's clearing: the room between one night and the next.

A run is a loop — prepare at the camp, go out, extract, SPEND, go again — and
this is the fourth beat. The party walks out of a forest with the night's take
already converted (see `Room.enter_store`: everything loaded onto the platforms
is the group's balance now), arrives through a corridor at the BOTTOM of the
map, and the way back seals behind them exactly as the forest's did. A second
corridor leaves from the TOP, it is open the whole time, and walking out of it
is the next day.

IT IS ONE WALK, SOUTH TO NORTH, AND THE MIDDLE OF IT IS A ROOM.
Corridor, clearing, corridor. The two ends are throats — narrow, dark at the
mouth, dressed at the threshold — and everything else happens in a round
CLEARING between them, with the trader on the west rim, the stalls on the east
rim and the machine on the north-west arc.

WHY A CIRCLE AND NOT A LANE.
It was a long east-west glade first, with three or four tables strung along it,
and the shape was doing exactly one thing: guaranteeing nobody walked past the
stock. That is a corridor's whole argument and it is a weak one — the party has
to walk the same straight line every night whether or not they can afford
anything, and a shop that is a queue is a shop nobody stands still in. A ROOM
is different. Everything in it is visible from the middle at once, so the visit
is a decision about where to WALK rather than a sequence you are pushed
through; two players can be at the trader and at the cabinet at the same time
without one of them walking back through the other; and a party with nothing to
spend can cross it in a straight line instead of being marched past six prices
they already know they cannot meet. The corridors on the ends keep the arrival
and the departure as separate events, which is the half of the lane that was
worth keeping.

IT IS THE ONE LIT PLACE AND THAT IS THE ZONE'S JOB.
Everywhere else the party goes is a black wood with a torch in it somewhere.
Here they can see the treeline, the far rim, the way out and each other. The
floor under the darkness is `zones.STORE_AMBIENT`; on top of it a RING of
torches burns around the clearing's rim, a chain runs down each neck, and the
trader's fire and the cabinet's marquee are the two brightest things in it. The
contrast is the reward — a night is only frightening if there is somewhere that
is not.

THE STOCK IS ROLLED, THE PRICES ARE DERIVED.
Six stalls, in two columns of three, rolled WITH REPLACEMENT against the day —
so he can be holding three of the same pistol, and the thing that makes those
three different is `STORE_PRICE_SPREAD`, one stall's haggle either side of the
catalog markup. What a gun is WORTH is never typed here: it is `loot.py`'s
value column times `STORE_MARKUP`, because the whole economy already runs off
that column and a second price list would be two places to disagree about what
an AK is.

WHAT THIS MODULE OWNS AND WHAT IT DOES NOT
It owns the tiles, the two end corridors, and where everything stands: his
wagon, his counter, his fire, his own gear, the torch ring, the six stalls and
the stock rolled onto them, `price_of`, the cabinet's spot, and the apron the
night's platforms are lowered onto. It does not own the ART
(`server/tools/make_store.py`, `make_merchant.py`, `make_machine.py`), and it
does not own what a purchase DOES — that is `Room.buy`, for the same reason
feeding a rift lives in the room rather than in `rift.py`.
"""

from __future__ import annotations

import math
import random

from . import scenery
from .config import (
    PLAYER_HALF_HEIGHT,
    STORE_CIRCLE_TILES,
    STORE_CORRIDOR_TILES,
    STORE_HEIGHT_TILES,
    STORE_LANE_TILES,
    STORE_MACHINE_LIGHT_TILES,
    STORE_MARKUP,
    STORE_PRICE_SPREAD,
    STORE_WIDTH_TILES,
    TILE_SIZE,
)
from .entrance import Entrance
from .loot import BY_KEY as ITEMS
from .world import FIRE, FLOOR, LOW, ROCK, TREE, VOID, TileMap

#: Trunks around the edge, in tiles. Matches `camp.BORDER_TILES` — it is the
#: same job: stop the camera framing the end of the world.
BORDER_TILES = 2
#: How far the treeline wanders in and out, in tiles. Without it the clearing
#: is a circle of grass with trees drawn on a compass, which is the tell that
#: a room was stamped rather than found.
EDGE_JITTER = 2.0
#: Boulders and scrub out near the rim, well clear of the pitch.
BOULDER_CHANCE = 0.972
#: Half-width of the guaranteed walk up the middle, in tiles. See `_tiles`.
SPINE_TILES = 2.5

# --- the pitch, in tiles from the CLEARING'S CENTRE --------------------------
# +x is east, +y is south. Every fixture in the zone is authored against this
# one origin, because the whole composition is a ring read from the middle: an
# offset measured from a map edge would move when the map got taller.

#: HIS WAGON, and it is the biggest thing in the zone.
#:
#: A trader in a forest full of the dead did not walk here with six tables on
#: his back. The wagon is the answer to that, and it is also the only piece of
#: scene in the game that carries the world's history on it: guns racked along
#: its flank, masks strung on a line under the canopy, crates roped to the
#: boards, and two bodies laid out and covered at its wheels. Everything he
#: sells came off somebody. The art says that once, from the far side of the
#: clearing, and then no dialogue ever has to.
#:
#: WEST, and hard against the rim: it is a vehicle, so it is parked at the edge
#: of a clearing rather than standing in one.
WAGON_COL = -12.0
WAGON_ROW = -3.0

#: The man himself, and the counter he trades over. He stands BEHIND it —
#: north — because everything a party may touch is on the south side of him,
#: which is the split that teaches which half of the pitch answers E.
#:
#: He is beside the wagon and not in front of it. Stacked on one column the two
#: occlude each other and the wagon becomes a hat; the step across is what
#: makes them a pitch instead of a sprite in front of a backdrop.
MERCHANT_COL = -8.4
MERCHANT_ROW = -1.6
COUNTER_COL = -8.2
COUNTER_ROW = 0.2
#: The mat he stands on. Under him, and the one thing on the pitch that says a
#: person chose this spot rather than that a clearing happens to contain one.
RUG_COL = -8.3
RUG_ROW = 0.9

#: His campfire. A `world.FIRE` TILE rather than a prop, which means the client
#: draws the animated flame and burns its light with no code at all — the same
#: fire the camp has, because it is the same kind of thing: a person keeping
#: warm. It is what turns a parked wagon into somewhere somebody is living.
FIRE_COL = -13.0
FIRE_ROW = 3.6

#: THE CABINET, on the NORTH-WEST arc.
#:
#: Not beside him and not among the stalls. Everything else in this clearing is
#: a decision about money, so the one thing that is not gets its own arc, lit by
#: nothing but its own marquee, on the side of the room the exit is on. A party
#: that has finished spending turns toward the way out and it is the thing in
#: the way. A cabinet in the middle of the stock would compete with the prices;
#: a cabinet across the room is somewhere you WALK, which is the whole
#: difference between a machine and a menu item.
MACHINE_COL = -9.0
MACHINE_ROW = -10.0
#: Its footprint in tiles. Solid — you walk up to a machine, not through it.
MACHINE_TILES_W = 3.0

#: HIS OWN GEAR, and where each piece goes is the composition.
#:
#: `(column, row, variant)` against the clearing's centre. All of it on the
#: WEST arc, around the wagon, because everything a party may touch is on the
#: east one. That separation is doing more work than any prompt could: a
#: player learns in one visit which half of the room answers E.
#:
#: The ring is DELIBERATELY UNEVEN, and the variants are pinned rather than
#: rolled. Five pieces at five equal angles is a display case; five pieces
#: stepped in and out around a parked wagon is a camp somebody has been living
#: in. The stock rolls nightly; the man's own belongings do not, and a shop
#: whose furniture rearranged itself would be the one thing in the loop that
#: felt generated.
KIT_SPOTS: tuple[tuple[float, float, int], ...] = (
    (-15.2, 1.6, 0),    # crates, roped, out past the fire
    (-14.0, -6.4, 3),   # the shelf of tins, tucked behind the wagon
    (-10.2, -7.2, 1),   # the barrel of rods
    (-15.4, -2.4, 2),   # the rack of spare barrels, hard against the rim
    (-5.6, -8.2, 4),    # the strongbox, furthest out on his side
)
#: How wide one piece of kit is, in tiles. Mirrors `TILE_KIT_W` in
#: server/tools/make_store.py — the art and the cover it provides are the same
#: object, so they are the same number.
KIT_TILES_W = 1.6

#: THE STALLS: two columns of three, on the EAST arc.
#:
#: A GRID, and that is a reversal. The old lane jittered its tables off an even
#: rhythm on the argument that four identical stalls at four identical
#: intervals is the loudest tell that nobody set this up by hand. That argument
#: is right about a CORRIDOR and wrong about a market: a trader who lays his
#: goods out in rows is a trader who wants them compared, and six prices
#: scattered around a clearing is six things to hunt rather than one decision
#: to make. So the goods are square and everything around them — the wagon, the
#: fire, the gear, the torch ring — is not. The irregularity lives in the
#: clearing; the stock is the one thing in it that was arranged.
#:
#: Read SOUTH TO NORTH, because that is the direction the party walks in, and
#: the rows are priced cheapest-first for the same reason: the first thing they
#: pass is the thing they can afford.
STALL_COLS: tuple[float, ...] = (4.6, 10.2)
STALL_ROWS: tuple[float, ...] = (5.6, -0.4, -6.4)
#: How wide one round table is, in tiles. Mirrors `TILE_TABLE_W` in
#: server/tools/make_store.py — the art and the cover it provides are the same
#: object, so they are the same number.
TABLE_TILES_W = 2.25

#: WHERE THE NIGHT'S PLATFORMS COME DOWN, on the SOUTH-WEST of the clearing.
#:
#: THE APRON IS THE FIRST BEAT OF THE ZONE AND IT IS RESERVED GROUND. The party
#: walks out of the neck and the skids they loaded an hour ago are being
#: lowered in front of them and to their left — before a single price tag is on
#: screen, and on the same side of the room as the man who is about to be paid.
#: Nothing else is ever placed here: a skid is three tiles wide, it is solid
#: the moment it lands, and a stall that had drifted into this quadrant would
#: be a stall a platform came down on top of.
#:
#: They stay OFF THE SPINE (see `_tiles`), because the walk from one mouth to
#: the other has to stay unconditional whatever landed.
PAYOUT_SPOTS: tuple[tuple[float, float], ...] = (
    (-8.0, 6.8),
    (-13.2, 8.6),
    (-5.2, 12.0),
)
#: Footprint of a landed skid, in tiles. Mirrors the deck in `rift.py`.
PAYOUT_TILES_W = 3.0

#: The wagon's footprint, in tiles. It is LOW rather than PROP for the zone's
#: own reason: this is the one place in the game whose job is that you can see
#: the far side of it, and a six-tile sight blocker parked on the west rim
#: would put the trader, his fire and half his gear behind a shadow.
WAGON_TILES_W = 5.0
COUNTER_TILES_W = 2.0

# --- light ------------------------------------------------------------------

#: How far a torch throws, in tiles. Bigger than a cabin lamp and smaller than
#: the campfire.
TORCH_LIGHT_TILES = 7.0
#: HOW MANY TORCHES RING THE CLEARING. The ring is the zone's lighting and its
#: shape at the same time: a party stepping out of the neck sees the whole
#: circumference lit before they see anything standing in it, which is what
#: says "this is a room" rather than "this is more forest". Enough that their
#: pools overlap into one continuous rim — a chain of separate islands with
#: dark between them reads as somewhere to be careful, which is the opposite of
#: what this zone is.
RING_TORCHES = 11
#: How far inside the rim they stand, in tiles.
RING_INSET = 2.0
#: How far apart the torches lining a neck are, in tiles.
TORCH_SPACING = 7
#: How far a torch has to stay from anything that is meant to be looked at.
TORCH_CLEAR = 3.4

#: THE THRESHOLD RANKS at the two mouths: two either side of each, in
#: `(across, back-from-mouth)` tiles, and the sign of `back` is the direction
#: into the map.
#:
#: THEY ARE THE STORE'S OWN TORCHES AND NOT THE `Entrance`'S. An `Entrance` can
#: carry torches and a forest's exit uses that — but those are drawn out of the
#: RIFT atlas, and a rift torch burns the anomaly's prism: cyan and violet,
#: because what it marks is a hole in the world. Four of them at the top of
#: this room would be the only cold light in the one zone whose entire job is
#: being warm. So the threshold is dressed with the same fire everything else
#: here is, and the way out reads as somewhere you walk to rather than as
#: somewhere the world tore open.
GATE_TORCHES: tuple[tuple[float, float, int], ...] = (
    (-2.6, 0.6, 1), (2.6, 0.6, -1), (-3.4, 3.4, 1), (3.4, 3.4, -1),
)

# --- stock ------------------------------------------------------------------

#: How many stalls. Six, always: it is a grid, and a grid with a hole in it
#: reads as a shop that has run out rather than as one that is starting small.
STALL_COUNT = 6

#: What he might be selling, cheapest first. The day gates how far down this
#: list the roll may reach — see `_stock_pool`.
STOCK_ORDER = ("glock18", "deagle", "famas", "ak47", "awp")
#: The first day each weapon may appear on a table. An AWP on night one would
#: end the game's difficulty curve at the first shop.
#:
#: THE FLOOR IS THREE. The roll is with replacement, so the pool no longer has
#: to be as long as the grid — but a first shop drawing six stalls out of one
#: weapon is a wall of the same pistol, and three is where the grid starts
#: looking like a choice.
STOCK_UNLOCK = {"glock18": 1, "deagle": 1, "famas": 1, "ak47": 2, "awp": 4}


def price_of(key: str) -> int:
    """What one `key` is worth on a table, before the stall's own haggle.

    DERIVED, never authored. `loot.py` already says what a gun is worth — it is
    the number a party would have loaded onto a platform to get one — so the
    shop is that column with his cut on top. A hand-written price list here
    would be a second opinion about the same thing, and the two would drift the
    first time a weapon was rebalanced.
    """
    item = ITEMS.get(key)
    if item is None:
        return 0
    return max(1, round(item.value * STORE_MARKUP))


def _haggle(key: str, rng: random.Random) -> int:
    """`price_of` with this particular stall's spread on it.

    The stock is rolled with replacement, so two tables can be holding the same
    gun — and two tables holding the same gun at the same number is not a
    choice, it is a duplicate. See `config.STORE_PRICE_SPREAD`.
    """
    base = price_of(key)
    if base <= 0:
        return 0
    spread = rng.uniform(-STORE_PRICE_SPREAD, STORE_PRICE_SPREAD)
    return max(1, round(base * (1.0 + spread)))


class Stand:
    """One round table with one thing on it.

    `x` is the CENTRE of the table and `y` its contact — the row its foot
    stands on. Which pixel row the stock rests at is NOT here: it comes off the
    art (`table.topY[v]` in the store manifest), because the tables are
    deliberately different heights and a single offset would float one gun and
    sink another.
    """

    __slots__ = ("id", "key", "price", "x", "y", "variant", "sold")

    def __init__(
        self,
        stand_id: str,
        key: str,
        price: int,
        x: float,
        y: float,
        variant: int,
        sold: bool = False,
    ) -> None:
        self.id = stand_id
        self.key = key
        self.price = price
        self.x = x
        self.y = y
        self.variant = variant
        self.sold = sold

    def to_payload(self) -> dict:
        row = {
            "id": self.id,
            "k": self.key,
            "price": self.price,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
        }
        if self.sold:
            row["sold"] = True
        return row


def stands_from_payloads(rows: list | None) -> list[Stand]:
    out: list[Stand] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        out.append(
            Stand(
                stand_id=str(row.get("id", "s0")),
                key=str(row.get("k", "")),
                price=int(row.get("price", 0)),
                x=float(row.get("x", 0.0)),
                y=float(row.get("y", 0.0)),
                variant=int(row.get("v", 0)),
                sold=bool(row.get("sold", False)),
            )
        )
    return out


def _hash(tx: int, ty: int, seed: int, salt: int = 0) -> float:
    """Deterministic 0..1 from a tile coordinate. Same mixer as `camp._hash`."""
    h = (tx * 374761393 + ty * 668265263 + ((seed ^ salt) * 2246822519)) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def _stock_pool(day: int) -> list[str]:
    """What may be on a table tonight, in catalog order."""
    return [key for key in STOCK_ORDER if STOCK_UNLOCK.get(key, 1) <= max(1, day)]


def _roll_stock(day: int, count: int, rng: random.Random) -> list[str]:
    """`count` guns for tonight's grid, weighted toward the day.

    WITH REPLACEMENT, which is the change. Distinct stock was right for a lane
    of four tables read in order — a repeat there was a table that had nothing
    to say. In a grid of six it is the opposite: a trader with three of the
    same pistol at three prices is a trader, and the stall spread (`_haggle`)
    is what turns the repeat into the question the zone is actually about. It
    also means the pool no longer has to be as long as the grid, so a day-one
    shop is six full tables rather than three and a gap.

    The weighting walks with the day rather than switching: an unlocked weapon
    stays possible forever (a cheap sidearm is still a real answer when the
    party came home broke), it just stops being the likely roll.
    """
    pool = _stock_pool(day)
    if not pool:
        return []
    # Distance from the deepest weapon the day has unlocked. The newest thing
    # on the shelf is the likeliest thing on a table.
    weights = [1.0 + pool.index(key) * 1.1 for key in pool]
    return rng.choices(pool, weights=weights, k=max(0, count))


# --- the ground -------------------------------------------------------------


def _centre(width: int, height: int) -> tuple[float, float]:
    """The clearing's middle, in TILES. Everything is authored against it."""
    return (width - 1) / 2.0, (height - 1) / 2.0


def _circle_half(angle: float, tx: int, ty: int, seed: int) -> float:
    """The clearing's radius at `angle`, in tiles.

    Two slow harmonics plus a hash. The harmonics are what make the rim
    BREATHE — bulging in places, pinched in others — and the hash is what stops
    it reading as a drawn curve. Neither is decoration: a clearing of constant
    radius is a circle with a grass texture on it.

    The amplitudes are small relative to the radius on purpose. Wander of the
    same order as the room itself stops being a clearing that breathes and
    becomes a coastline, and this room's job is to be legible as ONE space from
    the middle of it.
    """
    swell = math.sin(angle * 3.0 + 0.7) * 1.1 + math.sin(angle * 5.0 - 1.3) * 0.7
    return STORE_CIRCLE_TILES + swell + (_hash(tx, ty, seed, 5) - 0.5) * EDGE_JITTER


def _neck_half(ty: int, seed: int) -> float:
    """Half-width of the throat at row `ty`, in tiles."""
    base = STORE_LANE_TILES / 2.0
    swell = math.sin(ty * 0.11) * 0.7
    return base + swell + (_hash(0, ty, seed, 7) - 0.5) * (EDGE_JITTER * 0.6)


def _tiles(width: int, height: int, seed: int) -> list[list[int]]:
    """Corridor, clearing, corridor: open ground with woods thickening away."""
    cx, cy = _centre(width, height)
    grid: list[list[int]] = []
    for ty in range(height):
        row: list[int] = []
        for tx in range(width):
            if (
                tx < BORDER_TILES
                or ty < BORDER_TILES
                or tx >= width - BORDER_TILES
                or ty >= height - BORDER_TILES
            ):
                row.append(TREE)
                continue
            dx = tx - cx
            dy = ty - cy
            dist = math.hypot(dx, dy)
            # How far outside the walkable shape this tile is, in tiles. The
            # shape is the UNION of the clearing and the throat that runs the
            # whole height of the map, so the smaller excess wins.
            out_circle = dist - _circle_half(math.atan2(dy, dx), tx, ty, seed)
            out_neck = abs(dx) - _neck_half(ty, seed)
            off = min(out_circle, out_neck)
            if off < 0:
                # Open ground. A boulder now and then, out near the rim and
                # never in the middle where everything is going to stand.
                if off > -2.2 and _hash(tx, ty, seed, 8) > BOULDER_CHANCE:
                    row.append(ROCK)
                else:
                    row.append(FLOOR)
                continue
            # Density ramps with depth so the treeline thickens instead of
            # starting solid. Over THREE tiles: the camp is a round clearing
            # with room to spare, and this one has a rim the party is meant to
            # read as a wall of woods from the middle of the room.
            depth = min(1.0, off / 3.0)
            if _hash(tx, ty, seed, 9) < 0.30 + depth * 0.7:
                row.append(TREE)
            elif _hash(tx, ty, seed, 10) < 0.05 + depth * 0.06:
                row.append(ROCK)
            else:
                row.append(FLOOR)
        grid.append(row)

    # THE SPINE, and it is a guarantee rather than dressing. Everything above
    # is noise — a pinched neck plus an unlucky boulder could in principle wall
    # the room off from its own door, and unlike the forest generator this
    # module has no retry loop to fall back on: there is exactly one store map
    # and the party is already walking into it. Clearing a narrow band up the
    # centreline makes the walk from one mouth to the other unconditional. It
    # also reads: a trader who parked here walks that line every day.
    for tx in range(width):
        if abs(tx - cx) > SPINE_TILES:
            continue
        for ty in range(BORDER_TILES, height - BORDER_TILES):
            grid[ty][tx] = FLOOR
    return grid


def _carve_ends(grid: list[list[int]], width: int, height: int) -> tuple[Entrance, Entrance]:
    """VOID at both ends of the walk, and the two gates that own them.

    Not `entrance.carve`: that picks a random edge and winds a path through a
    generated forest, which is right for an arrival nobody chose and wrong for
    two doors this module already knows the position of. These are straight,
    because both are read end-on up the map.

    The two are not symmetrical, and the asymmetry is the zone's whole shape.
    The SOUTH one seals — the same slam the forest arrival gets, so the party
    knows the night is behind them — and the NORTH one never does, because it
    is not a thing to be found. It is the way on, standing open the entire
    time, with a rank of torches either side of it so it is legible from the
    middle of the room.
    """
    depth = STORE_CORRIDOR_TILES
    cx, _ = _centre(width, height)
    half = max(1.5, STORE_LANE_TILES / 2.0 - 1.5)
    x0 = max(0, int(round(cx - half)))
    x1 = min(width - 1, int(round(cx + half)))

    for tx in range(x0, x1 + 1):
        for step in range(depth):
            grid[step][tx] = VOID
            grid[height - 1 - step][tx] = VOID
        # Whatever the treeline did at the very ends, a mouth has to open onto
        # walkable ground or the party is puppeted into a wall.
        for step in range(depth, depth + 3):
            grid[step][tx] = FLOOR
            grid[height - 1 - step][tx] = FLOOR

    mid_x = (cx + 0.5) * TILE_SIZE
    south = Entrance(
        side="s",
        mouth_x=mid_x,
        mouth_y=(height - depth - 0.5) * TILE_SIZE,
        back_x=mid_x,
        back_y=(height - 0.5) * TILE_SIZE,
        dx=0.0,
        dy=-1.0,
        # Its OWN tiles, so the seal cannot eat the exit at the far end. A
        # forest's corridor is the only VOID on its map and can find its ranks
        # by scanning; this map has two, and a scan would swallow both.
        bounds=(x0, height - depth, x1, height - 1),
        # It closes the way every other forest path closes: the woods take it.
        seal_to=TREE,
    )
    north = Entrance(
        side="n",
        mouth_x=mid_x,
        mouth_y=(depth + 0.5) * TILE_SIZE,
        back_x=mid_x,
        back_y=0.5 * TILE_SIZE,
        dx=0.0,
        dy=1.0,
        bounds=(x0, 0, x1, depth - 1),
    )
    return south, north


# --- the pitch --------------------------------------------------------------


def _at(width: int, height: int, col: float, row: float) -> tuple[float, float]:
    """A `(column, row)` offset from the clearing's centre, in world pixels.

    The `+ 1.0` on the row is the same convention every fixture in this game
    uses: an offset names the tile a thing stands ON, and a contact point is
    the BOTTOM of that tile.
    """
    cx, cy = _centre(width, height)
    return (cx + col) * TILE_SIZE, (cy + row + 1.0) * TILE_SIZE


def _place_stands(width: int, height: int, day: int, rng: random.Random) -> list[Stand]:
    """The six tables, in two columns of three on the east arc.

    ON THE GRID, not knocked off it — see `STALL_COLS`. Cheapest first, filled
    SOUTH TO NORTH and west to east, because that is the order the party walks
    past them: the first table they reach is the one they can afford, and the
    last one they reach is the one they are saving for. That ramp is the
    zone's only tutorial about money.
    """
    stock = _roll_stock(day, STALL_COUNT, rng)
    if not stock:
        return []
    priced = sorted(
        ((key, _haggle(key, rng)) for key in stock),
        key=lambda pair: pair[1],
    )
    # Which table frame each stall uses. Shuffled rather than cycled: `index %
    # n` gives the same sequence of shapes every single night, which is a
    # pattern the player will read before they read the prices.
    frames = [0, 1, 2, 3]
    rng.shuffle(frames)

    stands: list[Stand] = []
    index = 0
    for row in STALL_ROWS:
        for col in STALL_COLS:
            if index >= len(priced):
                break
            key, price = priced[index]
            x, y = _at(width, height, col, row)
            stands.append(
                Stand(
                    stand_id=f"s{index}",
                    key=key,
                    price=price,
                    x=x,
                    y=y,
                    variant=frames[index % len(frames)],
                )
            )
            index += 1
    return stands


def payout_spots(width: int, height: int, count: int) -> list[tuple[float, float]]:
    """Landing points for `count` platforms, in world pixels.

    Measured from the clearing's CENTRE like everything else, because what has
    to be guaranteed is the relationship to the trader and to the way in: the
    party walks out of the neck and the skids are already coming down in front
    of them and on his side of the room.
    """
    return [_at(width, height, col, row) for col, row in PAYOUT_SPOTS[: max(0, count)]]


def payload_kit(width: int, height: int) -> list[tuple[float, float, int]]:
    """His gear, in world pixels. One list, read twice.

    Built here rather than inline so the tiles it makes solid and the rows the
    client draws come out of the same call — a footprint derived from a second
    copy of the offsets is a footprint that drifts the first time somebody
    nudges the wagon.
    """
    out: list[tuple[float, float, int]] = []
    for col, row, variant in KIT_SPOTS:
        x, y = _at(width, height, col, row)
        out.append((x, y, variant))
    return out


def _torches(
    width: int,
    height: int,
    seed: int,
    keep_out: list[tuple[float, float]],
) -> list[tuple[float, float, int]]:
    """Torch contact points, in world pixels: the rim ring and the two necks.

    THEY ARE THE ZONE. Everywhere else in this game is a forest at night with
    the lantern off; here the ring around the clearing is what a party sees
    before they see anything standing in it, and it is the difference between
    walking into a room and walking into more woods. The necks are navigation
    on top of that — a chain of fires leading away from a mouth answers "which
    way" before anybody has taken a step.

    A torch is never placed within `TORCH_CLEAR` of something meant to be
    LOOKED AT. A post standing in the stock is one more thing between the
    player and the price they are trying to read, and the cabinet and the
    wagon light their own patch anyway.
    """
    cx, cy = _centre(width, height)
    clear = TORCH_CLEAR * TILE_SIZE
    placed: list[tuple[float, float, int]] = []

    def free(x: float, y: float) -> bool:
        return all(math.hypot(x - ox, y - oy) > clear for ox, oy in keep_out)

    # THE RING. Started at a quarter turn so the first torch lands due south
    # and the pair either side of it flank the neck's mouth rather than one of
    # them standing in it.
    for index in range(RING_TORCHES):
        angle = math.pi / 2 + (index / RING_TORCHES) * math.tau
        radius = _circle_half(angle, index, 0, seed) - RING_INSET
        tx = cx + math.cos(angle) * radius
        ty = cy + math.sin(angle) * radius
        x = (tx + 0.5) * TILE_SIZE
        y = (ty + 1.0) * TILE_SIZE
        if free(x, y):
            placed.append((x, y, index % 2))

    # THE THRESHOLDS. Ranked and PAIRED, which is the one place in this zone
    # that is allowed to look arranged: a doorway is a thing somebody built, and
    # two ranks of two either side of a mouth is what a threshold looks like in
    # every culture that has ever had one. They go in before the necks so a
    # neck torch can never land on top of one.
    for across, back, _side in GATE_TORCHES:
        for mouth_y, into in (
            ((STORE_CORRIDOR_TILES + 0.5), 1.0),
            ((height - STORE_CORRIDOR_TILES - 1.5), -1.0),
        ):
            placed.append(
                (
                    (cx + across + 0.5) * TILE_SIZE,
                    (mouth_y + into * back + 1.0) * TILE_SIZE,
                    0 if across < 0 else 1,
                )
            )

    # THE NECKS. Staggered either side of the centreline rather than paired, so
    # a throat reads as a path somebody lit and not as an avenue somebody
    # surveyed.
    index = 0
    span = range(STORE_CORRIDOR_TILES + 3, height - STORE_CORRIDOR_TILES - 2, TORCH_SPACING)
    for ty in span:
        if abs(ty - cy) < STORE_CIRCLE_TILES - 1.0:
            continue  # inside the clearing: that is the ring's job
        side = 1 if index % 2 else -1
        tx = cx + side * (_neck_half(ty, seed) - 1.3)
        x = (tx + 0.5) * TILE_SIZE
        y = (ty + 1.0) * TILE_SIZE
        if free(x, y):
            placed.append((x, y, index % 2))
        index += 1

    return placed


def _dress(
    width: int,
    height: int,
    torches: list[tuple[float, float, int]],
    machine: tuple[float, float],
) -> dict:
    """The lights on the map, shipped as ordinary scenery.

    `SceneLight` is how a beacon, a cabin lamp and a torch all reach the
    lighting, and the lighting has no idea which is which — so the whole ring
    costs no client code at all.

    THERE IS NO TENT ANY MORE. He had one when he was a man camped in a glade;
    he has a WAGON now, and a tent pitched next to a covered wagon is the same
    statement twice. The wagon carries his shelter, his stock and his history
    in one silhouette — see `WAGON_COL`.
    """
    lights = [
        scenery.PlacedLight(x=x, y=y, radius_tiles=TORCH_LIGHT_TILES, kind=scenery.EMBER)
        for x, y, _ in torches
    ]
    # The machine's marquee. A `SceneLight` like every other lit thing, so the
    # lighting has no idea one of its sources is electric — but it is placed
    # ABOVE the cabinet's contact rather than on it, because the bulbs are on
    # the crown and a pool centred on the floor would light the tray and leave
    # the thing that is actually glowing in the dark.
    lights.append(
        scenery.PlacedLight(
            x=machine[0],
            y=machine[1] - TILE_SIZE * 1.6,
            radius_tiles=STORE_MACHINE_LIGHT_TILES,
            kind=scenery.NEON,
        )
    )
    population = scenery.Population(props=[], lights=lights, scenes=[], route=[])
    return scenery.to_payload(population)


def _claim(
    grid: list[list[int]],
    width: int,
    height: int,
    x: float,
    y: float,
    tiles_w: float,
    kind: int = LOW,
) -> None:
    """Make the row of tiles under a standing object solid.

    The footprint is derived from the object's WIDTH rather than assumed to be
    a whole number of cells starting at `x`: `x` is a centre and it does not
    land on a tile boundary. Reading it off the art is the same rule
    `scenery._cells` keeps.
    """
    ty = int((y - 1e-6) // TILE_SIZE)
    left = int((x - tiles_w / 2.0 * TILE_SIZE) // TILE_SIZE)
    right = int((x + tiles_w / 2.0 * TILE_SIZE - 1e-6) // TILE_SIZE)
    for cell in range(left, right + 1):
        if 0 <= cell < width and 0 <= ty < height:
            grid[ty][cell] = kind


def build_store(day: int, seed: int, takes: list[int] | None = None) -> TileMap:
    """Generate the merchant's clearing. One shape a night; the details roll.

    `takes` is what each of the night's platforms carried, in the order they
    were loaded. It only decides how many skids come down on the apron and how
    much each one is worth on screen — the BALANCE has already been credited by
    `Room.enter_store`, and the ceremony the client runs off this is pure
    presentation. Keeping the two apart is what stops a party who reconnected
    halfway through the animation from being paid twice.
    """
    rng = random.Random(seed ^ 0x5709E)
    width = STORE_WIDTH_TILES
    height = STORE_HEIGHT_TILES
    grid = _tiles(width, height, seed)
    south, north = _carve_ends(grid, width, height)
    stands = _place_stands(width, height, day, rng)

    wagon = _at(width, height, WAGON_COL, WAGON_ROW)
    merchant = _at(width, height, MERCHANT_COL, MERCHANT_ROW)
    counter = _at(width, height, COUNTER_COL, COUNTER_ROW)
    rug = _at(width, height, RUG_COL, RUG_ROW)
    machine = _at(width, height, MACHINE_COL, MACHINE_ROW)
    kit = payload_kit(width, height)

    paid = [value for value in (takes or []) if value > 0][: len(PAYOUT_SPOTS)]
    landings = payout_spots(width, height, len(paid))

    # Everything a torch has to stand clear of: the stock, the cabinet, the
    # wagon and the man. The apron is NOT on the list — a skid is lowered onto
    # ground that was already lit, and a torch it landed beside is a torch the
    # deck is standing in front of, which is exactly right.
    keep_out: list[tuple[float, float]] = [(stand.x, stand.y) for stand in stands]
    keep_out.extend((machine, wagon, merchant, counter))
    torches = _torches(width, height, seed, keep_out)

    # Tables are cover. Claiming the tiles under each one is what stops a
    # player walking through the stock, and it is LOW rather than PROP for the
    # usual reason: you can see over a table.
    for stand in stands:
        _claim(grid, width, height, stand.x, stand.y, TABLE_TILES_W)
    # His gear is solid too, and it is what actually makes the pitch a PLACE: a
    # party cannot walk through the crates to stand inside the wagon, so the
    # west arc reads as somebody's camp rather than as painted scenery.
    for kx, ky, _variant in kit:
        _claim(grid, width, height, kx, ky, KIT_TILES_W)
    _claim(grid, width, height, wagon[0], wagon[1], WAGON_TILES_W)
    _claim(grid, width, height, counter[0], counter[1], COUNTER_TILES_W)
    # The cabinet is cover the same way a table is, and for the same reason: a
    # body standing inside the one object in the room that is supposed to be
    # looked at is the loudest possible bug.
    _claim(grid, width, height, machine[0], machine[1], MACHINE_TILES_W)
    # A landed skid is solid, exactly as it is out in the woods: it is a
    # loading deck and the party does not stand on it.
    for px, py in landings:
        _claim(grid, width, height, px, py, PAYOUT_TILES_W)

    # Nothing under the MERCHANT is made solid. He is drawn, not walked into,
    # and a body-sized hole in the one spot the party gathers reads as the
    # pitch fighting them — the same call `rift._stamp` makes about the middle
    # of its sigil.

    # His campfire. A FIRE tile, so the client's existing campfire sprite and
    # its glow both land with no code. Solid, like every fire in this game,
    # which is correct: you walk around a fire.
    cx, cy = _centre(width, height)
    fire_tx = int(round(cx + FIRE_COL))
    fire_ty = int(round(cy + FIRE_ROW))
    if 0 <= fire_ty < height and 0 <= fire_tx < width:
        grid[fire_ty][fire_tx] = FIRE

    payload = {
        "merchant": [round(merchant[0], 1), round(merchant[1], 1)],
        "wagon": [round(wagon[0], 1), round(wagon[1], 1)],
        "counter": [round(counter[0], 1), round(counter[1], 1)],
        "stands": [stand.to_payload() for stand in stands],
        "torches": [[round(x, 1), round(y, 1), kind] for x, y, kind in torches],
        "rug": [round(rug[0], 1), round(rug[1], 1)],
        "machine": [round(machine[0], 1), round(machine[1], 1)],
        "kit": [[round(kx, 1), round(ky, 1), variant] for kx, ky, variant in kit],
        # The apron. One row per platform that came home tonight: where it sets
        # down and what it was carrying. Absent (empty) on a night nobody
        # extracted, which is the one case where there is nothing to show.
        "payout": [
            [round(x, 1), round(y, 1), value]
            for (x, y), value in zip(landings, paid)
        ],
    }

    return TileMap(
        grid,
        seed=seed,
        scenery=_dress(width, height, torches, machine),
        entrance=south.geometry_payload(),
        egress=north.geometry_payload(),
        store=payload,
    )


def formation_slots(
    gate: Entrance,
    seating: list[str],
    present: set[str],
) -> dict[str, tuple[float, float]]:
    """Two files inside the arrival corridor, facing the clearing.

    The forest's version wobbles every body a little, because a party emerging
    into woods should not look placed. It could be reused here — but this
    arrival is a party walking up to somebody, and a ragged clump reads as
    stumbling out of the dark rather than as arriving somewhere. Square files,
    and the tidiness is the difference.

    Built off the gate's own AXIS rather than off "west", because the corridor
    moved when the zone turned to run south-to-north and a hardcoded direction
    would have marched the party into a treeline.
    """
    ids = [pid for pid in seating if pid in present]
    # `dx`/`dy` point INWARD, into the map. The files spread across that.
    ax, ay = gate.dx, gate.dy
    sx, sy = -ay, ax
    slots: dict[str, tuple[float, float]] = {}
    for index, pid in enumerate(ids):
        file = index % 2
        col = index // 2
        ahead = TILE_SIZE * (1.2 + col * 1.35 + (0.35 if file else 0.0))
        across = TILE_SIZE * 0.75 * (1 if file else -1)
        x = gate.back_x + ax * ahead + sx * across
        y = gate.back_y + ay * ahead + sy * across
        slots[pid] = (x, y - PLAYER_HALF_HEIGHT)
    return slots
