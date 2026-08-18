"""The merchant's camp: the clearing between one night and the next.

A run is a loop — prepare at the camp, go out, extract, SPEND, go again — and
this is the fourth beat. The party walks out of a forest with the night's take
already converted (see `Room.enter_store`: everything loaded onto the platforms is
the group's balance now), arrives at the west end of a long glade, and the way
back seals behind them exactly as the forest's did. A trader has pitched in the
middle of it. His tables are in front of him with one weapon on each. The east
end is open, and walking out of it is the next day.

IT IS OUTDOORS, AND THAT IS DELIBERATE.
This was an interior first — a plank corridor with walls and hanging lamps —
and the problem with it outweighed everything it got right: it was the only
room in the game. Every other place the party stands is forest at night, so a
building did not read as somewhere they had walked to, it read as a menu the
game had cut to. A clearing with a tent in it reads as a person who is also out
here, which is a far better answer to "who is this man and why is he in a
forest full of the dead".

WHY IT IS STILL A CORRIDOR IN SHAPE
Because the zone is one decision repeated three or four times, and a long glade
read left to right is the only shape that guarantees the player is offered all
of them. A round clearing lets a party cut a diagonal and leave without seeing
half the stock. So the treeline squeezes the walkable ground into a lane, the
way in is at one end and the way out at the other, and every table is between
them. It is a corridor made of woods rather than of walls.

THE STOCK IS ROLLED, THE PRICES ARE NOT
Which guns are on the tables tonight is a roll against the day, so a party is
not shown the AWP on day one and is not still being offered a Glock on day six.
What each one COSTS is `loot.py`'s catalog value times `STORE_MARKUP` — one
number, derived, never typed per weapon — because the whole economy already
runs off that column and a second price list would be two places to disagree
about what an AK is worth.

WHAT THIS MODULE OWNS AND WHAT IT DOES NOT
It owns the tiles, the two end corridors, and where the pitch is: the merchant,
his tent, his tables, the stock on them, his torches and his mat. It does not
own the ART (`server/tools/make_store.py`, `make_merchant.py`, and the tent out
of `make_scenery.py`), and it does not own what a purchase DOES — that is
`Room.buy`, for the same reason feeding a rift lives in the room rather than in
`rift.py`.
"""

from __future__ import annotations

import math
import random

from . import scenery
from .config import (
    PLAYER_HALF_HEIGHT,
    STORE_CORRIDOR_TILES,
    STORE_HEIGHT_TILES,
    STORE_LANE_TILES,
    STORE_MACHINE_LIGHT_TILES,
    STORE_MARKUP,
    STORE_WIDTH_TILES,
    TILE_SIZE,
)
from .entrance import Entrance
from .loot import BY_KEY as ITEMS
from .world import FIRE, FLOOR, LOW, ROCK, TREE, VOID, TileMap

#: Trunks around the edge, in tiles. Matches `camp.BORDER_TILES` — it is the
#: same job: stop the camera framing the end of the world.
BORDER_TILES = 2
#: How far the treeline wanders in and out of the lane, in tiles. Without it
#: the glade is a rectangle of grass with trees drawn along two straight lines,
#: which is the tell that a corridor was stamped rather than found.
EDGE_JITTER = 2.4
#: Boulders and scrub out on the open ground, well clear of the pitch.
BOULDER_CHANCE = 0.965
#: Half-height of the guaranteed walk down the middle, in tiles. See `_tiles`.
SPINE_TILES = 2.5

#: Where the merchant stands, as a row offset from the lane's centreline.
#: North of centre, because everything he is selling is south of him and he has
#: to be behind his own counter.
MERCHANT_ROW = -1.8
#: His tent, and his fire between it and him.
#:
#: THE THREE OF THEM STEP DOWN AND ACROSS, and the offsets are the composition:
#: the tent furthest back and furthest left, the fire in front of it and to the
#: right, the merchant in front of both. Stacked on one column they occlude
#: each other — a tent directly behind his head is a hat, and a campfire there
#: is a halo — and spread along one row they read as three unrelated objects
#: that happen to share a clearing. The diagonal is what makes it a pitch.
TENT_ROW = -4.2
TENT_COL = -6.0
#: His campfire, beside the tent. A `world.FIRE` TILE rather than a prop, which
#: means the client draws the animated flame and burns its light with no code
#: at all — the same fire the camp has, because it is the same kind of thing: a
#: person keeping warm. It is what turns the pitch from a stall somebody set up
#: into somewhere somebody is living.
FIRE_ROW = -3.4
FIRE_COL = -3.0
#: The row the tables' feet sit on, relative to the centreline. Close to him:
#: the tables are his counter, and a gap wide enough to walk down between the
#: trader and his stock reads as two unrelated things in one clearing.
TABLE_ROW = 0.9
#: How wide one table is, in tiles. Mirrors `TILE_TABLE_W` in
#: server/tools/make_store.py — the art and the cover it provides are the same
#: object, so they are the same number.
TABLE_TILES_W = 2.0
#: Spacing centre to centre. Comfortably more than twice `STORE_BUY_TILES`, so
#: the prompt only ever has one table to offer and walking the glade is a
#: sequence of decisions rather than a fight with a radius.
TABLE_SPACING = 6

#: HOW FAR A TABLE MAY WANDER OFF ITS SLOT, in tiles. This is the whole
#: difference between "a trader set up here" and "a level designer placed a
#: row", and it is small on purpose: the jitter has to survive the reading that
#: these are four things arranged for you to walk past, so it is enough to
#: break the alignment and not enough to break the line.
TABLE_JITTER_X = 1.1
TABLE_JITTER_Y = 0.9

#: How far a torch throws, in tiles. Bigger than a cabin lamp and smaller than
#: the campfire: the pitch has to be a pool of warmth you can see from the far
#: end of the glade, without lifting the night off the whole map.
TORCH_LIGHT_TILES = 6.5
#: How far apart the torches lining the walk are, in tiles. Close enough that
#: their pools overlap into one lit path — a chain of separate islands of light
#: with dark between them reads as somewhere to be careful, which is the
#: opposite of what this zone is.
TORCH_SPACING = 8
#: How far a lane torch has to stay from any table, in tiles.
TORCH_CLEAR = 3.5

#: HIS GEAR, and where each piece goes is the composition.
#:
#: `(column, row)` offsets from the centre of the map, in tiles, against the
#: lane's centreline. They sit BEHIND him — north of the counter, on the same
#: side as his tent and his fire — because everything a party may touch is on
#: the south side and everything that is only scenery is on the north. That
#: separation is doing more work than any prompt could: a player learns in one
#: visit which half of the glade answers E.
#:
#: The row is DELIBERATELY UNEVEN. Four pieces on one line behind a trader is a
#: shelf; four pieces stepped back and forth around his tent is a camp somebody
#: has been living in. The variants are pinned rather than rolled so the pitch
#: is the same pitch every night — the stock rolls, the man's own belongings do
#: not, and a shop whose furniture rearranged itself nightly would be the one
#: thing in the loop that felt generated.
KIT_SPOTS: tuple[tuple[float, float, int], ...] = (
    (-9.5, -3.0, 0),   # crates, out past the tent
    (-2.2, -5.2, 3),   # the shelf of tins, tucked behind him
    (2.6, -4.4, 1),    # the barrel of rods
    (6.8, -5.0, 2),    # the rack, at the far end of his pitch
    (9.6, -3.4, 4),    # the strongbox, furthest from the lane
)

#: WHERE THE NIGHT'S PLATFORMS COME DOWN, in tiles from the west edge, with
#: the row measured off the lane's centreline.
#:
#: THE APRON IS THE FIRST BEAT OF THE ZONE. The party walks out of the corridor
#: and the skids they loaded an hour ago are being lowered into the clearing in
#: front of them — before a single price tag is on screen. That order is the
#: whole reason the glade got wider (`config.STORE_WIDTH_TILES`): a reward that
#: arrives while somebody is already reading the AWP's price is a reward that
#: happened to them rather than one they watched.
#:
#: They land OFF THE SPINE (|row| > `SPINE_TILES`), alternating sides, because
#: they are solid once they are down and the walk from one mouth to the other
#: has to stay unconditional. Alternating also makes the apron a slalom rather
#: than a wall, which is what stops three identical skids reading as a fence.
PAYOUT_SPOTS: tuple[tuple[float, float], ...] = (
    (13.0, 3.6),
    (18.5, -3.6),
    (24.0, 3.4),
)
#: Footprint of a landed skid, in tiles. Mirrors the deck in `rift.py`.
PAYOUT_TILES_W = 3.0

#: How wide one piece of kit is, in tiles. Mirrors `TILE_KIT_W` in
#: server/tools/make_store.py — the art and the cover it provides are the same
#: object, so they are the same number.
KIT_TILES_W = 1.6

#: THE MACHINE, and where it stands is the whole reason it works.
#:
#: LAST, past the final table, on the walk to the way out. The glade is read
#: once, left to right, and every other thing in it is a decision about money —
#: so the one thing that is not about money goes at the end, where the party
#: has already spent and is on their way into the next night. A cabinet in the
#: middle of the stalls competes with the prices; a cabinet after them is the
#: last thing anybody sees before the woods, and it is lit.
#:
#: It sits SOUTH of the centreline, opposite the merchant, so the two of them
#: are not a row: he is behind his tables on one side and it is standing on its
#: own on the other, which is what stops it reading as one more thing he sells.
MACHINE_COL = 15.5
MACHINE_ROW = 1.4
#: Its footprint in tiles. Solid — you walk up to a machine, not through it.
MACHINE_TILES_W = 2.0

#: How many stalls. Rolled, because a night with three is a night with less to
#: choose between and that should be something the player notices.
STALL_COUNTS = (3, 4)

#: What he might be selling, cheapest first. The day gates how far down this
#: list the roll may reach — see `_stock_pool`.
STOCK_ORDER = ("glock18", "deagle", "famas", "ak47", "awp")
#: The first day each weapon may appear on a table. An AWP on night one would
#: end the game's difficulty curve at the first shop.
#:
#: THE FLOOR IS THREE, and that is what sets the early rows. Stock is distinct
#: per table, so the pool is also the most stalls a night can have — unlock the
#: first three from day one or the opening shop is two tables and a gap, which
#: reads as a shop that has run out rather than as one that is starting small.
STOCK_UNLOCK = {"glock18": 1, "deagle": 1, "famas": 1, "ak47": 2, "awp": 4}


def price_of(key: str) -> int:
    """What the merchant asks for one `key`.

    DERIVED, never authored. `loot.py` already says what a gun is worth — it is
    the number a party would have fed into a rift to get one — so the shop is
    that column with his cut on top. A hand-written price list here would be a
    second opinion about the same thing, and the two would drift the first time
    a weapon was rebalanced.
    """
    item = ITEMS.get(key)
    if item is None:
        return 0
    return max(1, round(item.value * STORE_MARKUP))


class Stand:
    """One table with one weapon on it.

    `x` is the CENTRE of the table and `y` its contact — the row its feet stand
    on. Which pixel row the stock rests at is NOT here: it comes off the art
    (`table.topY[v]` in the store manifest), because the four tables are
    deliberately three different heights and a single offset would float one
    gun and sink another.
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
    """`count` distinct guns for tonight's tables, weighted toward the day.

    Distinct on purpose: two tables offering the same weapon at the same price
    is not a choice, it is a duplicate. When the pool is smaller than the number
    of stalls the shop simply has fewer tables — see `_place_stands`.

    The weighting walks with the day rather than switching: an unlocked weapon
    stays possible forever (a cheap sidearm is still a real answer when the
    party came home broke), it just stops being the likely roll.
    """
    pool = _stock_pool(day)
    if not pool:
        return []
    picked: list[str] = []
    available = list(pool)
    while available and len(picked) < count:
        weights = []
        for key in available:
            # Distance from the deepest weapon the day has unlocked. The newest
            # thing on the shelf is the likeliest thing on the table.
            rank = pool.index(key)
            weights.append(1.0 + rank * 1.3)
        choice = rng.choices(available, weights=weights, k=1)[0]
        picked.append(choice)
        available.remove(choice)
    # Cheapest first, left to right. The glade is read in one direction, so the
    # stock reads as a ramp rather than as a shuffled hand.
    picked.sort(key=lambda key: price_of(key))
    return picked


# --- the ground -------------------------------------------------------------


def _lane_half(tx: int, seed: int) -> float:
    """Half-height of the walkable lane at column `tx`, in tiles.

    Two slow sines plus a hash. The sines are what make the glade BREATHE —
    wide in places, pinched in others — and the hash is what stops the treeline
    reading as a drawn curve. Neither is decoration: a lane of constant width
    is a corridor with a grass texture on it.

    The amplitudes are small relative to the base on purpose. Wander of the
    same order as the lane itself stops being a glade that breathes and becomes
    a coastline, and the lane's job is to be legible as ONE walk from the mouth
    to the far end.
    """
    base = STORE_LANE_TILES / 2.0
    swell = math.sin(tx * 0.09) * 0.9 + math.sin(tx * 0.031 + 1.7) * 0.6
    return base + swell + (_hash(tx, 0, seed, 5) - 0.5) * EDGE_JITTER


def _tiles(width: int, height: int, seed: int) -> list[list[int]]:
    """The glade: a lane of open ground with woods thickening away from it."""
    mid = (height - 1) / 2.0
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
            half = _lane_half(tx, seed)
            off = abs(ty - mid)
            if off < half:
                # Open ground. A boulder now and then, never near the middle
                # where the pitch is going to stand.
                if off > half * 0.6 and _hash(tx, ty, seed, 8) > BOULDER_CHANCE:
                    row.append(ROCK)
                else:
                    row.append(FLOOR)
                continue
            # Density ramps with depth so the treeline thickens instead of
            # starting solid — the same falloff the camp's clearing uses, but
            # over THREE tiles rather than five. The camp is a round clearing
            # with room to spare; this is a lane, and a treeline that took five
            # tiles to close left the glade reading as open woods with a path
            # suggested through it rather than as a corridor of trees.
            depth = min(1.0, (off - half) / 3.0)
            if _hash(tx, ty, seed, 9) < 0.28 + depth * 0.7:
                row.append(TREE)
            elif _hash(tx, ty, seed, 10) < 0.05 + depth * 0.06:
                row.append(ROCK)
            else:
                row.append(FLOOR)
        grid.append(row)

    # THE SPINE, and it is a guarantee rather than a decoration. Everything
    # above is noise — a pinched lane plus an unlucky boulder could in
    # principle wall the glade in half, and unlike the forest generator this
    # module has no retry loop to fall back on: there is exactly one store map
    # and the party is already walking into it. Clearing a narrow band down the
    # centreline makes the walk from one mouth to the other unconditional.
    # It also reads: a trader who pitched here walks this line every day.
    for ty in range(height):
        if abs(ty - mid) > SPINE_TILES:
            continue
        for tx in range(BORDER_TILES, width - BORDER_TILES):
            grid[ty][tx] = FLOOR
    return grid


def _carve_ends(grid: list[list[int]], width: int, height: int) -> tuple[Entrance, Entrance]:
    """VOID at both ends of the lane, and the two gates that own them.

    Not `entrance.carve`: that picks a random edge and winds a path through a
    generated forest, which is right for an arrival nobody chose and wrong for
    two doors this module already knows the position of. These are straight,
    because the glade is straight and both are read end-on down it.

    The two are not symmetrical, and the asymmetry is the zone's whole shape.
    The west one SEALS — the same slam the forest arrival gets, so the party
    knows the night is behind them — and the east one never does, because it is
    not a thing to be found. It is just the way out, standing open the entire
    time, at the end of a lane with the stock along it.
    """
    depth = STORE_CORRIDOR_TILES
    mid = (height - 1) / 2.0
    half = max(1.5, STORE_LANE_TILES / 2.0 - 1.5)
    y0 = max(0, int(round(mid - half)))
    y1 = min(height - 1, int(round(mid + half)))

    for ty in range(y0, y1 + 1):
        for step in range(depth):
            grid[ty][step] = VOID
            grid[ty][width - 1 - step] = VOID
        # Whatever the treeline did at the very ends, the mouth has to open
        # onto walkable ground or the party is puppeted onto a wall.
        for step in range(depth, depth + 3):
            grid[ty][step] = FLOOR
            grid[ty][width - 1 - step] = FLOOR

    mid_y = (mid + 0.5) * TILE_SIZE
    west = Entrance(
        side="w",
        mouth_x=(depth + 0.5) * TILE_SIZE,
        mouth_y=mid_y,
        back_x=0.5 * TILE_SIZE,
        back_y=mid_y,
        dx=1.0,
        dy=0.0,
        # Its OWN tiles, so the seal cannot eat the exit at the far end. A
        # forest's corridor is the only VOID on its map and can find its ranks
        # by scanning; this map has two, and a scan would swallow both.
        bounds=(0, y0, depth - 1, y1),
        # It closes the way every other forest path closes: the woods take it.
        seal_to=TREE,
    )
    east = Entrance(
        side="e",
        mouth_x=(width - depth - 0.5) * TILE_SIZE,
        mouth_y=mid_y,
        back_x=(width - 0.5) * TILE_SIZE,
        back_y=mid_y,
        dx=-1.0,
        dy=0.0,
        bounds=(width - depth, y0, width - 1, y1),
    )
    return west, east


# --- the pitch --------------------------------------------------------------


def _place_stands(
    width: int, height: int, day: int, rng: random.Random
) -> list[Stand]:
    """The tables, spread along the lane in front of the merchant.

    NOT ON A GRID. Each one starts on an evenly spaced slot and is then pushed
    off it — a little along the lane, a little across it, and its own table
    frame — because four identical stalls at four identical intervals is the
    single loudest tell that nobody set this up by hand. The jitter is bounded
    (`TABLE_JITTER_*`) so the row still reads as a row: these are things you
    walk past in order, and scattering them properly would turn a sequence of
    decisions into a search.
    """
    count = rng.choice(STALL_COUNTS)
    stock = _roll_stock(day, count, rng)
    if not stock:
        return []
    centre = width / 2.0
    mid = (height - 1) / 2.0
    span = (len(stock) - 1) * TABLE_SPACING
    # Snapped to a whole tile before the jitter, so the underlying rhythm is
    # even and only the offsets are irregular.
    first = round(centre - span / 2.0)

    # Which table frame each stall uses. Shuffled rather than cycled: `index %
    # 4` gives the same left-to-right sequence of shapes every single night,
    # which is a pattern the player will read before they read the prices.
    frames = [0, 1, 2, 3]
    rng.shuffle(frames)

    stands: list[Stand] = []
    for index, key in enumerate(stock):
        tx = first + index * TABLE_SPACING + rng.uniform(-TABLE_JITTER_X, TABLE_JITTER_X)
        ty = mid + TABLE_ROW + rng.uniform(-TABLE_JITTER_Y, TABLE_JITTER_Y)
        stands.append(
            Stand(
                stand_id=f"s{index}",
                key=key,
                price=price_of(key),
                x=tx * TILE_SIZE,
                y=(ty + 1.0) * TILE_SIZE,
                variant=frames[index % len(frames)],
            )
        )
    return stands


def payout_spots(height: int, count: int) -> list[tuple[float, float]]:
    """Landing points for `count` platforms, in world pixels.

    Measured from the WEST edge rather than from the centre, because what has
    to be guaranteed is the relationship to the way IN: the party walks out of
    that corridor and the skids are already coming down in front of them.
    """
    mid = (height - 1) / 2.0
    return [
        ((col + 0.5) * TILE_SIZE, (mid + row + 1.0) * TILE_SIZE)
        for col, row in PAYOUT_SPOTS[: max(0, count)]
    ]


def payload_kit(width: int, height: int) -> list[tuple[float, float, int]]:
    """His gear, in world pixels. One list, read twice.

    Built here rather than inline so the tiles it makes solid and the rows the
    client draws come out of the same call — a footprint derived from a second
    copy of the offsets is a footprint that drifts the first time somebody
    nudges the tent.
    """
    mid = (height - 1) / 2.0
    centre = width / 2.0
    return [
        ((centre + col) * TILE_SIZE, (mid + row + 1.0) * TILE_SIZE, variant)
        for col, row, variant in KIT_SPOTS
    ]


def _machine_spot(width: int, height: int) -> tuple[float, float]:
    """Contact point of the cabinet, in world pixels.

    Measured back from the EAST mouth rather than out from the centre, because
    what has to be guaranteed is the relationship to the way out: the machine
    is the last thing on the walk, and on a glade whose lane wanders it must
    not end up level with the final table on one seed and inside the corridor
    on another.
    """
    mid = (height - 1) / 2.0
    tx = width - STORE_CORRIDOR_TILES - MACHINE_COL
    return (tx + 0.5) * TILE_SIZE, (mid + MACHINE_ROW + 1.0) * TILE_SIZE


def _torches(
    width: int, height: int, seed: int, stands: list[Stand], machine_x: float
) -> list[tuple[float, float, int]]:
    """Torch contact points, in world pixels.

    THEY ARE NAVIGATION, not decoration. The glade is a forest at night with
    the lantern off, and a party emerging from the west corridor into unbroken
    dark would have no way of knowing which direction the trader is. A line of
    fires leading away from the mouth answers that before anyone has taken a
    step — the same job the extraction exit's torch ranks do, and the reason
    they are spaced so their pools overlap rather than dotted evenly.

    Staggered either side of the centreline rather than paired, so the walk
    reads as a path somebody lit and not as an avenue somebody surveyed.
    """
    mid = (height - 1) / 2.0
    placed: list[tuple[float, float, int]] = []
    # Measured against the tables that ACTUALLY landed rather than against a
    # guess at how far they spread. The stalls are jittered, so a fixed
    # keep-out band around the centre either clips the outermost table on a
    # bad roll or wastes a third of the lane on a good one.
    keep_out = TORCH_CLEAR * TILE_SIZE
    index = 0
    tx = STORE_CORRIDOR_TILES + 3
    while tx < width - STORE_CORRIDOR_TILES - 2:
        x = (tx + 0.5) * TILE_SIZE
        # A lane torch standing in the stock is one more thing between the
        # player and the thing they are trying to read. The pitch lights
        # itself; the lane only has to get them there.
        # The machine lights its own end of the glade — see
        # `STORE_MACHINE_LIGHT_TILES` — so a torch beside it is one more post
        # in front of the one object here that is supposed to be looked at.
        if abs(x - machine_x) <= keep_out:
            tx += TORCH_SPACING
            continue
        if all(abs(x - stand.x) > keep_out for stand in stands):
            side = 1 if index % 2 else -1
            ty = mid + side * (_lane_half(tx, seed) - 1.4)
            placed.append((x, (ty + 1.0) * TILE_SIZE, index % 2))
            index += 1
        tx += TORCH_SPACING

    # THE PITCH HAS NO TORCH OF ITS OWN, and that is a deliberate subtraction.
    # It had a flanking pair and they fought everything: at any spacing that
    # read as "his", they landed on the tent or on the campfire, and pushed out
    # far enough to clear both they stopped reading as his at all. His CAMPFIRE
    # is the light here — it throws further than a torch, it is warmer, and a
    # man sitting by his own fire is a better picture of a trader camped in the
    # woods than two posts arranged around him. The lane torches get the party
    # to him; the fire is what they walk up to.
    return placed


def _dress(
    width: int,
    height: int,
    torches: list[tuple[float, float, int]],
    machine: tuple[float, float],
) -> dict:
    """The scenery half of the pitch: his tent, and the lights on the map.

    Shipped through `scenery.to_payload` rather than through the store's own
    payload, and that is the point of doing it this way: the tent is a scenery
    prop, so the client already knows how to depth-sort it against the party
    and needs no code at all to draw it. Same for the lights — `SceneLight` is
    how a beacon, a cabin lamp and a torch all reach the lighting, and the
    lighting has no idea which is which.
    """
    mid = (height - 1) / 2.0
    centre = width / 2.0
    props = [
        scenery.Prop(
            kind="tent",
            x=(centre + TENT_COL) * TILE_SIZE,
            y=(mid + TENT_ROW + 1.0) * TILE_SIZE,
            variant=0,
            flip=False,
            layer=1,
        )
    ]
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
    population = scenery.Population(props=props, lights=lights, scenes=[], route=[])
    return scenery.to_payload(population)


def build_store(day: int, seed: int, takes: list[int] | None = None) -> TileMap:
    """Generate the merchant's camp. One shape every night; the details roll.

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
    west, east = _carve_ends(grid, width, height)
    stands = _place_stands(width, height, day, rng)
    machine = _machine_spot(width, height)
    paid = [value for value in (takes or []) if value > 0][: len(PAYOUT_SPOTS)]
    landings = payout_spots(height, len(paid))
    torches = _torches(width, height, seed, stands, machine[0])

    # Tables are cover. Claiming the tiles under each one is what stops a
    # player walking through the stock to stand inside the merchant, and it is
    # LOW rather than PROP for the usual reason: you can see over a table.
    #
    # The footprint is derived from the SPRITE's width rather than assumed to
    # be two cells starting at `x`: `x` is the centre, and the jitter means it
    # no longer lands on a tile boundary. Reading it off the art is the same
    # rule `scenery._cells` keeps.
    half = TABLE_TILES_W / 2.0
    for stand in stands:
        ty = int((stand.y - 1e-6) // TILE_SIZE)
        left = int((stand.x - half * TILE_SIZE) // TILE_SIZE)
        right = int((stand.x + half * TILE_SIZE - 1e-6) // TILE_SIZE)
        for cell in range(left, right + 1):
            if 0 <= cell < width and 0 <= ty < height:
                grid[ty][cell] = LOW

    # Nothing under the merchant, his tent or his torches is made solid. He is
    # drawn, not walked into, and a body-sized hole in the one spot the party
    # gathers reads as the pitch fighting them — the same call `rift._stamp`
    # makes about the middle of its sigil.
    mid = (height - 1) / 2.0
    centre = width / 2.0

    # His campfire. A FIRE tile, so the client's existing campfire sprite and
    # its glow both land with no code — see `FIRE_ROW`. Solid, like every fire
    # in this game, which is correct: you walk around a fire.
    fire_tx = int(round(centre + FIRE_COL))
    fire_ty = int(round(mid + FIRE_ROW))
    if 0 <= fire_ty < height and 0 <= fire_tx < width:
        grid[fire_ty][fire_tx] = FIRE

    payload = {
        "merchant": [
            round(centre * TILE_SIZE, 1),
            round((mid + MERCHANT_ROW + 1.0) * TILE_SIZE, 1),
        ],
        "stands": [stand.to_payload() for stand in stands],
        "torches": [[round(x, 1), round(y, 1), kind] for x, y, kind in torches],
        "rug": [
            round(centre * TILE_SIZE, 1),
            round((mid + MERCHANT_ROW + 1.6) * TILE_SIZE, 1),
        ],
        "machine": [round(machine[0], 1), round(machine[1], 1)],
        "kit": [
            [round(kx, 1), round(ky, 1), variant]
            for kx, ky, variant in payload_kit(width, height)
        ],
        # The apron. One row per platform that came home tonight: where it sets
        # down and what it was carrying. Absent (empty) on a night nobody
        # extracted, which is the one case where there is nothing to show.
        "payout": [
            [round(x, 1), round(y, 1), value]
            for (x, y), value in zip(landings, paid)
        ],
    }

    # His gear is solid too, and it is what actually makes the pitch a PLACE:
    # a party cannot walk through the crates to stand inside the tent, so the
    # north side of the glade reads as somebody's camp rather than as painted
    # scenery. LOW like the tables — waist-high, seen over, not seen through.
    for kx, ky, _variant in payload_kit(width, height):
        ty = int((ky - 1e-6) // TILE_SIZE)
        left = int((kx - KIT_TILES_W / 2.0 * TILE_SIZE) // TILE_SIZE)
        right = int((kx + KIT_TILES_W / 2.0 * TILE_SIZE - 1e-6) // TILE_SIZE)
        for cell in range(left, right + 1):
            if 0 <= cell < width and 0 <= ty < height:
                grid[ty][cell] = LOW

    # A landed skid is solid, exactly as it is out in the woods: it is a
    # loading deck and the party does not stand on it. They are placed off the
    # spine (see `PAYOUT_SPOTS`), so the walk down the glade is still open.
    half_pad = PAYOUT_TILES_W / 2.0
    for px, py in landings:
        ty = int((py - 1e-6) // TILE_SIZE)
        left = int((px - half_pad * TILE_SIZE) // TILE_SIZE)
        right = int((px + half_pad * TILE_SIZE - 1e-6) // TILE_SIZE)
        for cell in range(left, right + 1):
            if 0 <= cell < width and 0 <= ty < height:
                grid[ty][cell] = LOW

    # The cabinet is cover, the same way a table is, and for the same reason:
    # a body standing inside the one object in the glade that is supposed to be
    # looked at is the loudest possible bug. LOW rather than PROP — you can see
    # over it, and its own crown lights are above that line.
    half = MACHINE_TILES_W / 2.0
    machine_ty = int((machine[1] - 1e-6) // TILE_SIZE)
    left = int((machine[0] - half * TILE_SIZE) // TILE_SIZE)
    right = int((machine[0] + half * TILE_SIZE - 1e-6) // TILE_SIZE)
    for cell in range(left, right + 1):
        if 0 <= cell < width and 0 <= machine_ty < height:
            grid[machine_ty][cell] = LOW

    return TileMap(
        grid,
        seed=seed,
        scenery=_dress(width, height, torches, machine),
        entrance=west.geometry_payload(),
        egress=east.geometry_payload(),
        store=payload,
    )


def formation_slots(
    gate: Entrance,
    seating: list[str],
    present: set[str],
) -> dict[str, tuple[float, float]]:
    """Two files inside the west corridor, facing the glade.

    The forest's version wobbles every body a little, because a party emerging
    into woods should not look placed. It could be reused here — but this
    arrival is a party walking up to somebody, and a ragged clump reads as
    stumbling out of the dark rather than as arriving somewhere. Square files,
    and the tidiness is the difference.
    """
    ids = [pid for pid in seating if pid in present]
    slots: dict[str, tuple[float, float]] = {}
    for index, pid in enumerate(ids):
        file = index % 2
        col = index // 2
        x = gate.back_x + TILE_SIZE * (1.2 + col * 1.35 + (0.35 if file else 0.0))
        y = gate.mouth_y + (1 if file else -1) * TILE_SIZE * 0.75
        slots[pid] = (x, y - PLAYER_HALF_HEIGHT)
    return slots
