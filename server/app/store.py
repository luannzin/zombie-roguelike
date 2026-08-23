"""The merchant's clearing: the room between one night and the next.

A run is a loop — prepare at the camp, go out, extract, SPEND, go again — and
this is the fourth beat. The party walks out of a forest with the night's take
already converted (see `Room.enter_store`: everything loaded onto the platforms
is the group's balance now), arrives through a corridor at the BOTTOM of the
map, and the way back seals behind them exactly as the forest's did. A second
corridor leaves from the TOP, it is open the whole time, and walking out of it
is the next day.

IT IS ONE WALK, SOUTH TO NORTH, AND THE MIDDLE OF IT IS A SHOP.
Corridor, clearing, corridor. The two ends are throats — narrow, dark at the
mouth, dressed at the threshold — and between them is a small round CLEARING
with the trader standing in the MIDDLE of it: his cart behind him, his counter
in front of him, his six stalls laid out in front of that, and the upgrade
cabinet on the west arc.

WHY A SMALL ROOM WITH THE MAN IN THE MIDDLE.
It was a long east-west glade first, with the tables strung along it, which
guaranteed nobody walked past the stock and made the visit a queue. So it
became a room — and then the room was sixteen tiles of radius with the trader
on the west rim and the stalls on the east one, which is a field, not a shop.
The party crossed twenty tiles to look at a price and twenty back to pay for
it, and the two halves read as two unrelated places. A SHOP IS A COUNTER YOU
STAND AT: one man in the middle, his goods in front of him, everything else
around the rim, and the whole thing readable from the door in one look. The
corridors on the ends keep the arrival and the departure as separate events,
which is the half of the lane that was worth keeping.

IT IS THE ONE LIT PLACE AND THAT IS THE ZONE'S JOB.
Everywhere else the party goes is a black wood with a torch in it somewhere.
Here they can see the treeline, the far rim, the way out and each other. The
floor under the darkness is `zones.STORE_AMBIENT`; on top of it a ring of
torches marks the clearing's rim, a chain runs down each neck, and the trader's
fire and the cabinet's marquee are the two brightest things in it. The contrast
is the reward — a night is only frightening if there is somewhere that is not.
The floor and the torches are ONE BUDGET and they are tuned against each other:
every light in the world is drawn additively over that floor, and additive
pools sum. See the `--- light ---` block below for what happened the first time
they were not.

THE STOCK IS ROLLED, THE PRICES ARE DERIVED.
Six stalls, three across and two deep in front of the man, rolled WITH
REPLACEMENT against the day —
so he can be holding three of the same pistol, and the thing that makes those
three different is `STORE_PRICE_SPREAD`, one stall's haggle either side of the
catalog markup. What a gun is WORTH is never typed here: it is `loot.py`'s
value column times `STORE_MARKUP`, because the whole economy already runs off
that column and a second price list would be two places to disagree about what
an AK is.

WHAT THIS MODULE OWNS AND WHAT IT DOES NOT
It owns the tiles, the two end corridors, and where everything stands: his
wagon, his counter, his fire, his own gear, the torches, the six stalls and
the stock rolled onto them, `price_of`, the ammunition crates along the south
wall and what a crate-load costs, the cabinet's spot, and the apron the
night's platforms are lowered onto. It does not own the ART
(`server/tools/make_store.py`, `make_merchant.py`, `make_machine.py`), and it
does not own what a purchase DOES — that is `Room.buy`, for the same reason
feeding a rift lives in the room rather than in `rift.py`.
"""

from __future__ import annotations

import math
import random

from . import scenery, weapons
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
from .world import BRICK, FIRE, FLOOR, LOW, ROCK, TILEFLOOR, TREE, VOID, TileMap

#: Trunks around the edge, in tiles. Matches `camp.BORDER_TILES` — it is the
#: same job: stop the camera framing the end of the world.
BORDER_TILES = 2
#: How far the treeline wanders in and out, in tiles. Without it the clearing
#: is a circle of grass with trees drawn on a compass, which is the tell that
#: a room was stamped rather than found.
EDGE_JITTER = 2.0
#: Boulders and scrub out near the rim, well clear of the pitch.
BOULDER_CHANCE = 0.972
#: Half-width of the band of ground cleared up the middle, in tiles. See
#: `_tiles` — it is a guarantee about the GENERATOR, not about the furniture.
SPINE_TILES = 2.5

# --- the shop, in tiles ------------------------------------------------------
# THE ZONE IS TWO PLACES AND THEY ARE MEASURED FROM TWO ORIGINS.
#
# The APRON is outdoor ground: a round clearing where the night's platforms
# come down, with his wagon parked on it and his fire beside that. Everything
# on it is authored against the apron's own centre (`_at`), because it is a
# composition read from the middle of a circle and an offset measured from a
# map edge would move the day the map got taller.
#
# The SHOP is a rectangle of brick standing at the north end of that clearing —
# the first and only building in the game. Everything inside it is authored
# against the INTERIOR's centre (`_in`), which is a different origin on
# purpose: a counter is fitted to a wall, not to a treeline, and a fixture that
# drifted when the apron was resized would come away from the wall it is
# supposed to be bolted to.

#: The building's outer footprint, in tiles, walls included.
#:
#: TWENTY-FOUR BY EIGHTEEN, and both numbers are the smallest that work. It has
#: to hold a counter long enough to read as a counter, six tables laid out in a
#: grid, a cabinet against the far wall and enough floor between them that two
#: players are never squeezing past each other — and it has to fit on one
#: screen from the door, which is the whole reason the old sixteen-tile
#: clearing was thrown out. Anything larger is a hall.
SHOP_COLS = 24
SHOP_ROWS = 18
#: Which row the north wall sits on. Flush against the exit corridor, so the
#: way out is a door in the back of the shop rather than a walk across a field
#: to a gap in the trees.
SHOP_TOP = STORE_CORRIDOR_TILES
#: How much open ground is cleared around the building before the woods start.
#: Without it the generator buries the shop in trunks: it is a rectangle
#: stamped over forest, and a treeline growing out of a brick wall is the tell
#: that nobody put the building there.
SHOP_YARD = 2
#: Half-width of the DOOR in the south wall and of the gap in the north wall,
#: in tiles. Matches the corridor's own half-width — the way in and the way on
#: are the same size, so neither reads as the important one.
SHOP_GATE_HALF = 2.5

# --- inside the shop, in tiles from the INTERIOR'S CENTRE --------------------
# +x is east, +y is south. The interior runs -10.5..+10.5 across and
# -7.5..+7.5 down.

#: THE COUNTER, an L in the NORTH-EAST CORNER, and it is the whole composition.
#:
#: `(col, row, kind)` where kind is 0 corner, 1 run-east, 2 run-north. The
#: corner is the elbow; the long arm runs east along to the far WALL, and the
#: short arm turns NORTH and runs to the north wall.
#:
#: THE SHORT ARM USED TO TURN THE OTHER WAY and it left the pocket open. It ran
#: SOUTH out of the elbow, into the room, which fences nothing: a body walked
#: round the west end of the counter, up the gap between it and the north wall,
#: and stood inside the merchant. The two arms have to close ONTO MASONRY —
#: north wall, east wall, and the L — for the pocket to be a room he is in and
#: the party is not. The east arm reaches the east wall for the same reason it
#: always should have: one open tile at the end of a counter is a door.
#:
#: WHY A CORNER AND NOT THE MIDDLE. He stood in the MIDDLE of a round clearing
#: before this, on the argument that a shop is a counter you stand at and the
#: man should be the first thing you see from the door. That argument survives
#: — it is why he is still the only person in the zone and why his stock is
#: still laid out in front of him — but the middle of a ROOM is not the middle
#: of a clearing. A counter in the centre of a rectangle is an island, with a
#: walkable gap behind it that a player will walk into looking for the back of
#: the shop; a counter fitted into a corner has a back the building provides.
#: It also buys the thing the clearing could never have: a POCKET that is HIS,
#: which the party can see into and not walk into, with his shelves on the wall
#: behind him. That split is what the rim of the clearing used to do with
#: crates, done properly.
COUNTER_L: tuple[tuple[float, float, int], ...] = (
    (4.0, -4.0, 0),
    (5.0, -4.0, 1), (6.0, -4.0, 1), (7.0, -4.0, 1),
    (8.0, -4.0, 1), (9.0, -4.0, 1), (10.0, -4.0, 1), (11.0, -4.0, 1),
    (4.0, -5.0, 2), (4.0, -6.0, 2), (4.0, -7.0, 2), (4.0, -8.0, 2),
)
#: How wide one counter section is, in tiles. Mirrors `TILE_COUNTER_W` in
#: server/tools/make_store.py — the art and the cover it provides are the same
#: object, so they are the same number.
COUNTER_TILES_W = 1.0

#: THE MAN, in his own pocket, standing at the long arm.
#:
#: ONE ROW BEHIND THE COUNTER, not two. The pocket is four rows deep and he
#: used to stand in the middle of it, which put a body's width of empty floor
#: between him and the thing he trades over — from the customer's side he was a
#: man standing in a room with a counter in front of him rather than a man
#: SERVING at one. It is also the reach: `STORE_BUY_DIST` is measured from
#: where he stands, and a step back is a step out of the conversation.
#:
#: Nothing under him is made solid — he is drawn, not walked into — but he is
#: fenced by the counter in front and the walls behind, so the party cannot
#: stand where he is standing without any code saying so. That is the same call
#: `rift._stamp` makes about the middle of its sigil: geometry, not a rule.
MERCHANT_COL = 7.5
MERCHANT_ROW = -5.0

#: HIS SHELVES, on the north wall behind him. `(col, row, variant)`.
#:
#: THEY ARE THE ANSWER TO "WHAT ELSE HAS HE GOT". Six tables hold six guns and
#: nothing else in the zone has ever suggested there is more to him than that.
#: A wall of jars, tins and bundles behind the counter says the stock on the
#: floor is a selection, which is a different and better statement than a man
#: with exactly six things. None of it opens, and the art carries that: it is
#: high on a wall, behind a counter, out of reach.
SHELF_SPOTS: tuple[tuple[float, float, int], ...] = (
    (5.5, -6.6, 0),
    (7.5, -6.6, 1),
    (9.5, -6.6, 2),
    (11.0, -6.6, 0),
)
SHELF_TILES_W = 1.6

#: THE CABINET, against the WEST wall.
#:
#: Same argument it had on the west arc of the clearing and it survives the
#: move: everything else in this room is a decision about money, so the one
#: thing that is not gets its own wall. It is across the room from the counter,
#: which is somewhere you WALK — the whole difference between a machine and a
#: menu item — and it is against masonry rather than standing in the open,
#: which is what a cabinet actually is.
#:
#: IN THE CORNER, not halfway down the wall. The counter's pocket is the
#: north-EAST corner and the room reads on one diagonal: the man at the far
#: right, the machine at the far left, the stock in the middle between them.
#: Parked at the wall's midpoint the cabinet was beside the stalls rather than
#: opposite the man, and the two things you can spend at were both on the same
#: half of the floor.
MACHINE_COL = -9.0
MACHINE_ROW = -7.0
#: Its footprint in tiles. Solid — you walk up to a machine, not through it.
#: Mirrors the two-tile cabinet in server/tools/make_machine.py.
MACHINE_TILES_W = 2.0

#: THE STALLS: three across, two deep, in the middle of the floor.
#:
#: A GRID, and the argument is unchanged from the clearing: a trader who lays
#: his goods out in rows is a trader who wants them compared, and six prices
#: scattered around a room is six things to hunt rather than one decision to
#: make. What the building adds is that the grid now has a room around it
#: rather than a treeline, so the regularity reads as arrangement instead of as
#: the generator giving up.
#:
#: Read SOUTH TO NORTH and priced cheapest-first, because that is the direction
#: the party walks in from the door: the first table they reach is the one they
#: can afford, and the row nearest the counter is the one they are saving for.
STALL_COLS: tuple[float, ...] = (-4.5, 0.0, 4.5)
STALL_ROWS: tuple[float, ...] = (4.5, 0.5)
#: How wide one round table is, in tiles. Mirrors `TILE_TABLE_W` in
#: server/tools/make_store.py.
TABLE_TILES_W = 1.5

#: THE RUGS. `(col, row, variant)` — one inside the door, one under the stock,
#: one along the front of the counter.
#:
#: They are the cheapest thing in the room and they do the most work. A brick
#: floor with furniture on it is a warehouse; the same floor with three worn
#: mats laid on the lines people actually walk is somewhere somebody lives.
#: They are flat, they claim no tiles, and they are drawn with the ground.
RUG_SPOTS: tuple[tuple[float, float, int], ...] = (
    (0.0, 6.2, 0),
    (0.0, 2.6, 1),
    (7.5, -2.6, 2),
)

#: DECORATION CRATES, around the edges of the room. `(col, row, variant)`.
#:
#: NONE OF THEM OPEN, and that is the point of where they are. The party spent
#: the previous night learning that a box in this game is a thing you open, so
#: every one of these is out at a wall, stacked, roped or lidded — the same
#: statement his gear made around the rim of the clearing, made by a room
#: instead of by a circle. They are LOW: cover you can see over, so a crate
#: never puts a shadow across the shop.
CRATE_SPOTS: tuple[tuple[float, float, int], ...] = (
    (-9.5, 4.5, 0),
    (-8.0, 6.5, 1),
    (9.5, 2.0, 2),
    (8.0, 5.5, 0),
    (-9.5, 1.5, 1),
    (10.0, 6.5, 2),
)
CRATE_TILES_W = 1.2

#: THE LAMPS. `(col, row)`, and there is no variant field: the sheet has two
#: vessels and the renderer picks between them off the position's own hash.
#:
#: THIS IS THE ZONE'S JOB AND THE LAMPS ARE HOW IT IS DONE. Everywhere else a
#: party goes is a black wood with a torch in it; here they can see the room,
#: the far wall, the way out and each other. Out in the clearing that was a
#: ring of torches on the rim, which is what you light a clearing with. A room
#: is lit by lamps STANDING IN IT, on a regular grid — they are the one
#: arranged thing about the lighting, and regularity is exactly right for them:
#: somebody put these out.
#:
#: THEY USED TO HANG FROM CHAINS AND THAT WAS WRONG ABOUT THE CAMERA. A lamp
#: two tiles over the floor is DRAWN two tiles up the screen from the tile it
#: is lighting, so the flame and its own pool never appeared in the same place,
#: and the chain over it ran up into a ceiling this roofless cutaway does not
#: have. Five lanterns floating in mid-air. A lamp on a table has its flame
#: where its light is.
#:
#: THEY ARE ALSO THE LIGHT BUDGET. `zones.STORE_AMBIENT` is a floor under the
#: darkness pass and every one of these is drawn ADDITIVELY on top of it with
#: nothing clamping the sum — the same bug that blew this zone to flat white
#: when it was a clearing. Five at `LAMP_LIGHT_TILES` is what the floor can
#: carry with the apron's three landing skids going at the same time. Adding a
#: sixth means taking reach out of the other five.
LAMP_SPOTS: tuple[tuple[float, float], ...] = (
    (-5.5, -4.5),
    (6.5, -1.0),
    (-5.5, 3.0),
    (5.5, 4.5),
    (0.0, -1.0),
)
#: How far above its own contact the flame burns, in tiles. The light is placed
#: at the WICK rather than at the floor under it, because a pool centred on the
#: boards would light the stand and leave the thing that is glowing in the dark.
#: It is about a foot now rather than the two tiles a chain gave it.
LAMP_FLAME_TILES = 1.1
#: Footprint of a lamp's stand, in tiles. Solid: it is furniture with an open
#: flame on it, and walking through one should not be possible.
LAMP_TILES_W = 1.0

# --- the apron, in tiles from the CLEARING'S CENTRE --------------------------

#: HIS WAGON, parked on the apron, west of the door.
#:
#: IT IS OUTSIDE NOW AND THAT IS THE POINT. A covered cart is the answer to
#: "who is this man" — he DRIVES, he was somewhere else last week, and that is
#: the reason he is worth finding. A building is the opposite answer, so the
#: two only work together if the cart is what he ARRIVED IN and the shop is
#: what he unloaded into. Parked in the yard, between the party and the door,
#: it is read on the walk up: cart first, then the building it feeds.
WAGON_COL = -6.0
WAGON_ROW = -3.0
#: The wagon's footprint, in tiles. LOW rather than PROP, because this is the
#: one zone whose job is that you can see across it and a sight blocker parked
#: in the yard would put the shop's front in a shadow.
WAGON_TILES_W = 4.5

#: His campfire, on the apron beside the wagon. A `world.FIRE` TILE rather than
#: a prop, so the client draws the animated flame and burns its light with no
#: code at all.
#:
#: IT IS OUTDOORS FOR A REASON BEYOND TASTE. It throws ten tiles of light, and
#: ten tiles of additive light inside an eighteen-tile room on a 0.45 ambient
#: floor is the flat-white bug again with one tile instead of eleven. Out here
#: it lights the yard, which is what the yard is for.
FIRE_COL = 6.5
FIRE_ROW = -3.5

#: HIS OWN GEAR, out on the apron. `(column, row, variant)`.
#:
#: The ring is DELIBERATELY UNEVEN and the variants are pinned rather than
#: rolled. Four pieces at four equal angles is a display case; four pieces
#: stepped in and out around a parked wagon is somewhere somebody has been
#: living. The stock rolls nightly; the man's own belongings do not.
KIT_SPOTS: tuple[tuple[float, float, int], ...] = (
    (-8.5, -5.5, 0),    # crates, roped, behind the cart
    (-2.5, -6.5, 1),    # the barrel of rods, off the cart's tail
    (8.5, 0.0, 3),      # the shelf of tins, east of the fire
    (7.0, 4.5, 4),      # the strongbox, furthest out on the east arc
)
#: How wide one piece of kit is, in tiles. Mirrors `TILE_KIT_W` in
#: server/tools/make_store.py.
KIT_TILES_W = 1.4

#: WHERE THE NIGHT'S PLATFORMS COME DOWN, on the apron.
#:
#: THE APRON IS THE FIRST BEAT OF THE ZONE AND IT IS RESERVED GROUND. The party
#: walks out of the neck and the skids they loaded an hour ago are being
#: lowered around them — before a door, a price tag or a counter is on screen.
#: Nothing else is ever placed here: a skid is three tiles wide, it is solid
#: the moment it lands, and anything that had drifted into this band would be
#: something a platform came down on top of.
#:
#: THEY STAY WHERE THEY LAND. The decks are drawn for the rest of the visit and
#: their tiles stay solid, so the yard the party walks up through is a yard
#: with three landed platforms in it — the night, parked. A skid that faded out
#: once its coins had flown would make the payout a cutscene.
#:
#: SPREAD SO NO TWO ROTOR WASHES TOUCH. A wash is seven tiles across at 0.85
#: alpha and `lighter` SUMS: two overlapping is 1.7 of a full-bright sheet
#: before eight rotors and eight strobes go on top. The nearest pair here is
#: 8.5 tiles apart. See `zones.STORE_AMBIENT`.
PAYOUT_SPOTS: tuple[tuple[float, float], ...] = (
    (-6.5, 2.5),
    (6.5, 2.5),
    (0.0, 8.0),
)
#: Footprint of a landed skid, in tiles. Mirrors the deck in `rift.py`.
PAYOUT_TILES_W = 3.0

# --- light ------------------------------------------------------------------
# THE WHOLE ZONE HAS ONE LIGHT BUDGET AND THIS IS MOST OF IT.
#
# `zones.STORE_AMBIENT` is a floor under the darkness pass; every torch, every
# hanging lamp, the fire, the cabinet's marquee and every landing skid's rotor
# wash are drawn ADDITIVELY on top of that floor, and additive pools SUM with
# nothing clamping the total. That is what blew this zone out to flat white
# when it was one clearing: three skids landing within five tiles of each other
# at 0.85 alpha a wash, on a 0.7 floor, with eleven seven-tile torches ringing
# the room behind them.
#
# THE BUILDING MADE THE BUDGET EASIER AND THE RULE HAS NOT CHANGED. The two
# halves of the zone light SEPARATELY now — the apron has the ring, the fire
# and the skids; the shop has five short lamps and a marquee — and the wall
# between them is opaque, so neither set ever sums with the other. That is
# worth more than any of the numbers below. Move one and check the rest.

#: How far a torch throws, in tiles. Smaller than a cabin lamp, and much
#: smaller than the campfire — it lights the rim it stands on and stops.
TORCH_LIGHT_TILES = 4.5
#: HOW MANY TORCHES RING THE APRON. Enough that the rim is a ring of warm
#: marks a party can read the shape of the yard from, and few enough that their
#: pools touch rather than pile up.
RING_TORCHES = 6
#: How far inside the rim they stand, in tiles.
RING_INSET = 1.6
#: How far apart the torches lining the neck are, in tiles.
TORCH_SPACING = 5
#: How far a torch has to stay from anything that is meant to be looked at.
TORCH_CLEAR = 2.6

#: THE PAIR EITHER SIDE OF A THRESHOLD, in `(across, back-from-mouth)` tiles.
#:
#: TWO THRESHOLDS, NOT THREE. The arrival mouth at the south of the map gets a
#: pair, and so does the SHOP'S DOOR — which is the one that matters, because
#: it is the only thing in the zone that has to be findable from across a dark
#: yard. The exit is inside the building and needs nothing: it is a lit doorway
#: in a lit room.
#:
#: THEY ARE THE STORE'S OWN TORCHES AND NOT THE `Entrance`'S. An `Entrance` can
#: carry torches and a forest's exit uses that — but those are drawn out of the
#: RIFT atlas and burn the anomaly's prism, cyan and violet, because what they
#: mark is a hole in the world. Cold light at the door of the one warm zone in
#: the game would be the wrong note.
GATE_TORCHES: tuple[tuple[float, float], ...] = (
    (-2.4, 1.0), (2.4, 1.0),
)
#: The pair flanking the shop's door, in tiles either side of it, standing this
#: far out into the yard.
DOOR_TORCHES = (3.6, 1.4)

#: HOW FAR A HANGING LAMP THROWS, in tiles.
#:
#: SHORT, and shorter than a torch, but the pools have to TOUCH. A lamp on a
#: chain two tiles over your head lights the floor under it and the tables
#: either side; five of them on a grid is what makes the room evenly lit
#: without any one of them being a bonfire. At four tiles they did not reach
#: each other across a twenty-two tile room and what came out was five bright
#: holes in a dark floor — the clearing's own failure, indoors. The ambient
#: floor is what makes the shop LEGIBLE; these are what make it look like
#: somebody lit it, and that only works if the lit parts join up.
LAMP_LIGHT_TILES = 5.2

# --- stock ------------------------------------------------------------------

#: How many stalls. Six, always: it is a grid, and a grid with a hole in it
#: reads as a shop that has run out rather than as one that is starting small.
STALL_COUNT = 6

#: What he might be selling, CHEAPEST FIRST. Derived from the weapons
#: catalog and sorted by what it costs, because a shelf is a ladder of what
#: the party can afford — the catalog's own order groups by weapon class,
#: which is the right order for a sprite sheet and the wrong one for a shop.
#: The day gates how far down this list the roll may reach — see
#: `_stock_pool`.
#: Sorted on the CATALOG value rather than on `price_of` below, which is
#: only defined further down the file — and which is a fixed multiple of
#: it anyway, so the two orders cannot disagree.
STOCK_ORDER: tuple[str, ...] = tuple(
    sorted(weapons.GUN_KEYS, key=lambda key: (weapons.BY_KEY[key].value, key))
)

#: How many nights of shelf there are. The pool is split into this many
#: bands and one band unlocks per day, so a catalog of eleven guns opens at
#: the same pace a catalog of five did and adding a twelfth does not need a
#: new line in a hand-written table.
STOCK_DAYS = 5
#: The first day each weapon may appear on a table. An AWP on night one would
#: end the game's difficulty curve at the first shop.
#:
#: THE FIRST BAND IS WIDER THAN THE REST. The roll is with replacement, so
#: the pool no longer has to be as long as the grid — but a first shop
#: drawing six stalls out of one weapon is a wall of the same pistol, and a
#: opening band of four sidearms is where the grid starts looking like a
#: choice. Everything after it is a fifth of the shelf a night, so the last
#: thing on the ladder lands on `STOCK_DAYS` however long the ladder gets.
STOCK_FIRST_BAND = 4


def _unlock_day(index: int) -> int:
    """The night `STOCK_ORDER[index]` first appears on a table."""
    if index < STOCK_FIRST_BAND:
        return 1
    remaining = max(1, len(STOCK_ORDER) - STOCK_FIRST_BAND)
    step = (index - STOCK_FIRST_BAND) / remaining
    return min(STOCK_DAYS, 2 + int(step * (STOCK_DAYS - 1)))


STOCK_UNLOCK: dict[str, int] = {
    key: _unlock_day(index) for index, key in enumerate(STOCK_ORDER)
}


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


# --- the ammunition crates ---------------------------------------------------
# THE ONE THING IN THIS SHOP THAT IS NOT A DECISION, AND IT IS DELIBERATE.
#
# Six tables are six choices; a crate of rounds is upkeep. It is the counterpart
# of the rule `ammo.py` opens with — ammunition is not cargo — said from the
# other side of the loop: if a round is what you SPEND to fill the bag, then the
# shop has to be where you buy the spending money back. Until this existed a
# party's ammunition came entirely off the forest floor, which made the calibre
# you owned a thing you hoped about rather than a thing you supplied.
#
# A CRATE ONLY EXISTS IF SOMEBODY CAN SHOOT IT, and that is `ammo.scatter`'s
# second rule standing indoors. The merchant does not stock .308 for a party of
# knives — he stocks what they walked in carrying — so the row of crates against
# the south wall is a PORTRAIT OF THE PARTY'S BELT, and the moment somebody buys
# a calibre nobody had, another one lands there. `Room` owns that; this module
# owns where they stand and what they cost.
#
# THEY DO NOT SELL OUT. A table sells once because it holds one specific weapon;
# a crate is a supply, and a supply that emptied after one purchase would make
# the fourth player in a room the one who goes into the night dry.
#
# NOTHING CLAIMS THE TILE UNDER ONE. Every other fixture in this room is stamped
# solid at build time, and a crate that arrives mid-visit cannot be — the tile
# map went out with the map. Rather than reserve five tiles that might stay
# empty (a wall in the middle of a floor with nothing standing on it is the
# worst bug this room can have), they stand flat against the south wall, on the
# strip nobody walks, and you can step through one. The merchant is walked
# through for the same reason and it has never been noticed.

#: Where the crates stand: `(col, row)` from the INTERIOR'S CENTRE, one slot per
#: calibre in `weapons.AMMO_TYPES` order, so a given calibre is always in the
#: same place and a returning party knows where their rounds are without
#: reading a label.
#:
#: ALONG THE SOUTH WALL, EAST OF THE DOOR. Two reasons and both are about the
#: walk: it is the first wall the party passes coming in, which is when
#: resupply is the cheap decision to make, and it is the one strip of floor the
#: room's own furniture never uses — the stalls are in the middle and his
#: counter is in the far corner. The last slot stops short of the decoration
#: crate at `(10.0, 6.5)` by a tile and a half.
AMMO_SPOTS: tuple[tuple[float, float], ...] = (
    (3.2, 6.6),
    (4.6, 6.6),
    (6.0, 6.6),
    (7.4, 6.6),
    (8.8, 6.6),
)
#: How wide one crate is, in tiles. Mirrors `TILE_AMMO_W` in
#: server/tools/make_store.py. Nothing is claimed with it — see above — but the
#: renderer sorts and shadows off the same footprint every other prop uses.
AMMO_TILES_W = 1.1

#: What filling an EMPTY reserve costs, as a share of the cheapest weapon that
#: eats the calibre.
#:
#: DERIVED LIKE EVERY OTHER PRICE IN THIS ROOM, and off the same column: a box
#: has `value` 0 in the loot catalog (it is not cargo and may not be shipped),
#: so the thing that has to answer "what is a round worth" is the GUN. Half a
#: pistol buys six boxes of pistol rounds; half an AWP buys six of its five —
#: so a calibre costs what its weapon costs, ammunition never overtakes the
#: thing it feeds, and a party can rearm twice a night for a long time before
#: they have paid for the weapon a second time.
#:
#: It is also what keeps the ladder honest at both ends without a table: the
#: cheap sidearm's rounds are almost free and the sniper's are the most
#: expensive thing on the floor that is not a gun, which is exactly the shape
#: `weapons.catalog_value` already gave the weapons themselves.
AMMO_RESERVE_SHARE = 0.5


def ammo_price_of(calibre: str) -> int:
    """What ONE crate-load of `calibre` costs, with the merchant's cut on top.

    The box is the same box the forest scatters (`weapons.BOX_ROUNDS`), so its
    share of a full reserve is read off the two tables rather than typed here:
    a shell box is a sixth of sixty and a pistol box is a sixth of two hundred
    and forty, and both come out of the same line.
    """
    cap = weapons.RESERVE_MAX.get(calibre, 0)
    rounds = weapons.BOX_ROUNDS.get(calibre, 0)
    if cap <= 0 or rounds <= 0:
        return 0
    floor_value = min(
        (gun.value for gun in weapons.WEAPONS if gun.ammo == calibre),
        default=0,
    )
    if floor_value <= 0:
        return 0
    full = floor_value * AMMO_RESERVE_SHARE
    return max(1, round(full * (rounds / cap) * STORE_MARKUP))


class AmmoBox:
    """One crate of rounds against the wall. Sells forever; never sells out.

    `x` is the CENTRE and `y` the contact, exactly like a `Stand`. `variant` is
    the frame on the ammunition sheet and it is the calibre's index in
    `weapons.AMMO_TYPES` — shipped rather than derived on the client, so the
    art's frame order is a fact one side owns.
    """

    __slots__ = ("id", "calibre", "key", "price", "rounds", "x", "y", "variant")

    def __init__(
        self,
        calibre: str,
        x: float,
        y: float,
        variant: int,
    ) -> None:
        self.id = f"b_{calibre}"
        self.calibre = calibre
        self.key = f"ammo_{calibre}"
        self.price = ammo_price_of(calibre)
        self.rounds = weapons.BOX_ROUNDS.get(calibre, 0)
        self.x = x
        self.y = y
        self.variant = variant

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "c": self.calibre,
            "k": self.key,
            "price": self.price,
            "n": self.rounds,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
        }


def ammo_boxes(width: int, calibres: set[str]) -> list[AmmoBox]:
    """A crate for every calibre in `calibres`, in `weapons.AMMO_TYPES` order.

    The ORDER IS THE TABLE'S, not the party's: a calibre keeps its slot on the
    wall whether or not the ones before it are stocked, so the .308 crate does
    not slide two feet to the left the night somebody sells the shotgun.
    """
    out: list[AmmoBox] = []
    for index, calibre in enumerate(weapons.AMMO_TYPES):
        if calibre not in calibres or index >= len(AMMO_SPOTS):
            continue
        col, row = AMMO_SPOTS[index]
        x, y = _in(width, col, row)
        out.append(AmmoBox(calibre=calibre, x=x, y=y, variant=index))
    return out


def ammo_boxes_from_payloads(rows: list | None) -> list[AmmoBox]:
    """Rebuild the crates off a map payload — a late join, or a reconnect."""
    out: list[AmmoBox] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        calibre = str(row.get("c", ""))
        if calibre not in weapons.AMMO_TYPES:
            continue
        out.append(
            AmmoBox(
                calibre=calibre,
                x=float(row.get("x", 0.0)),
                y=float(row.get("y", 0.0)),
                variant=int(row.get("v", 0)),
            )
        )
    return out


# --- the ground -------------------------------------------------------------


def _apron(width: int, height: int) -> tuple[float, float]:
    """The APRON's middle, in TILES. Everything outdoors is authored against it.

    Not the map's centre any more: the building takes the top eighteen rows, so
    the clearing sits in what is left below it. Derived rather than written
    down, because the two have to stay flush — a gap between the shop's south
    wall and the top of the circle would be a strip of forest nobody can
    explain between a yard and the door it serves.
    """
    top = SHOP_TOP + SHOP_ROWS          # first row south of the building
    bottom = height - STORE_CORRIDOR_TILES - 1
    return (width - 1) / 2.0, (top + bottom) / 2.0


def shop_bounds(width: int) -> tuple[int, int, int, int]:
    """The building's OUTER rectangle as `(left, top, right, bottom)` in tiles.

    Inclusive on every side, and those four rows and columns are the WALLS.
    Public because the flood-fill test and `build_store` both need to know
    where the masonry is, and a second copy of the arithmetic is a second
    opinion about where the door is.
    """
    left = (width - SHOP_COLS) // 2
    return left, SHOP_TOP, left + SHOP_COLS - 1, SHOP_TOP + SHOP_ROWS - 1


def _shop_centre(width: int) -> tuple[float, float]:
    """The middle of the INTERIOR, in tiles. The origin for `_in`."""
    left, top, right, bottom = shop_bounds(width)
    return (left + 1 + right - 1) / 2.0, (top + 1 + bottom - 1) / 2.0


def _circle_half(angle: float, tx: int, ty: int, seed: int) -> float:
    """The apron's radius at `angle`, in tiles.

    Two slow harmonics plus a hash. The harmonics are what make the rim
    BREATHE — bulging in places, pinched in others — and the hash is what stops
    it reading as a drawn curve. Neither is decoration: a clearing of constant
    radius is a circle with a grass texture on it.

    The amplitudes are small relative to the radius on purpose. Wander of the
    same order as the yard itself stops being a clearing that breathes and
    becomes a coastline.
    """
    swell = math.sin(angle * 3.0 + 0.7) * 1.1 + math.sin(angle * 5.0 - 1.3) * 0.7
    return STORE_CIRCLE_TILES + swell + (_hash(tx, ty, seed, 5) - 0.5) * EDGE_JITTER


def _neck_half(ty: int, seed: int) -> float:
    """Half-width of the throat at row `ty`, in tiles."""
    base = STORE_LANE_TILES / 2.0
    swell = math.sin(ty * 0.11) * 0.7
    return base + swell + (_hash(0, ty, seed, 7) - 0.5) * (EDGE_JITTER * 0.6)


def _stamp_shop(
    grid: list[list[int]], width: int, height: int, seed: int
) -> tuple[float, float]:
    """Lay the building over the finished forest. Returns the door, in pixels.

    IT IS STAMPED LAST AND IT IS THE ONE THING IN THE ZONE WITH STRAIGHT EDGES.
    Everything under it — the treeline, the rim's harmonics, the neck's
    wander — is noise, because a clearing is FOUND. A building is not: it has a
    square corner, courses that line up and a door in the middle of a wall, and
    that contrast is the entire reason the party reads it as somebody's rather
    than as more terrain. So it overwrites, unconditionally, whatever the
    generator had put there.

    THE YARD COMES FIRST AND ITS EDGE IS RAGGED, WHICH IS THE OPPOSITE RULE.
    The woods have to stop short of the walls — a trunk growing out of brick is
    the tell that nobody put the building there — but clearing a clean
    rectangle around it just moves the problem out three tiles and draws a
    second straight line, this one with no wall under it to justify it. So the
    margin is jittered per tile off the same hash the rim uses. The BUILDING is
    surveyed; the ground it was put down on is not.

    NOTHING IS CLEARED TO THE NORTH. There is no yard back there — the exit
    corridor comes straight off the north wall, and open ground either side of
    it would be a lawn behind a shop that the party can see, walk into and find
    nothing in.
    """
    left, top, right, bottom = shop_bounds(width)

    y0 = max(BORDER_TILES, top)
    y1 = min(height - BORDER_TILES, bottom + SHOP_YARD + 3)
    x0 = max(BORDER_TILES, left - SHOP_YARD - 2)
    x1 = min(width - BORDER_TILES, right + SHOP_YARD + 3)
    for ty in range(y0, y1):
        for tx in range(x0, x1):
            # Chebyshev distance out of the building's rectangle, with the
            # north face excluded so the clearing never opens behind it.
            out = max(left - tx, tx - right, ty - bottom, 0)
            margin = SHOP_YARD + (_hash(tx, ty, seed, 11) - 0.5) * 2.2
            if out <= margin:
                grid[ty][tx] = FLOOR

    for ty in range(top, bottom + 1):
        for tx in range(left, right + 1):
            edge = ty in (top, bottom) or tx in (left, right)
            grid[ty][tx] = BRICK if edge else TILEFLOOR

    # THE TWO OPENINGS, punched through the walls they belong to. The door in
    # the south wall is how the party gets in; the gap in the north wall is the
    # mouth of the exit corridor, which `_carve_ends` then runs off the top of
    # the map. Both are floored with the SHOP'S floor rather than with soil: a
    # threshold you can see the brick run through is a threshold that belongs
    # to the building.
    cx = (width - 1) / 2.0
    gate_x0 = int(round(cx - SHOP_GATE_HALF))
    gate_x1 = int(round(cx + SHOP_GATE_HALF))
    for tx in range(gate_x0, gate_x1 + 1):
        grid[bottom][tx] = TILEFLOOR
        grid[top][tx] = TILEFLOOR

    return (cx + 0.5) * TILE_SIZE, (bottom + 1.0) * TILE_SIZE


def _tiles(width: int, height: int, seed: int) -> list[list[int]]:
    """Corridor, apron, shop, corridor: the zone's ground, south to north."""
    acx, acy = _apron(width, height)
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
            dx = tx - acx
            dy = ty - acy
            dist = math.hypot(dx, dy)
            # How far outside the walkable shape this tile is, in tiles. The
            # shape is the UNION of the apron and the throat that runs the
            # whole height of the map, so the smaller excess wins.
            out_circle = dist - _circle_half(math.atan2(dy, dx), tx, ty, seed)
            # The neck only exists SOUTH of the building. North of it the
            # ground is the shop's, and a throat that ran the full height of
            # the map would leave two pockets of grass either side of the exit
            # corridor that nobody can reach and nobody can explain.
            out_neck = (
                abs(dx) - _neck_half(ty, seed)
                if ty > SHOP_TOP + SHOP_ROWS - 1
                else 1e6
            )
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
            # starting solid.
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
    # the yard off from its own door, and unlike the forest generator this
    # module has no retry loop to fall back on: there is exactly one store map
    # and the party is already walking into it. Clearing a narrow band up the
    # centreline is what makes the GROUND unconditional.
    #
    # It stops at the building's south wall, because from there the guarantee
    # is the building's own: the door is punched in a known column and the
    # interior is a rectangle of floor. It is not a promise of a straight walk
    # either way — a landing skid and the middle column of stalls both claim
    # tiles on this line and the party goes round them. What replaces that
    # promise is `tests/test_store_walk.py`, which flood-fills the finished map
    # and fails if the exit, the man, a stall or the cabinet cannot be reached.
    _, _, _, shop_bottom = shop_bounds(width)
    for tx in range(width):
        if abs(tx - acx) > SPINE_TILES:
            continue
        for ty in range(shop_bottom, height - BORDER_TILES):
            grid[ty][tx] = FLOOR

    _stamp_shop(grid, width, height, seed)
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
    time.

    THEY ALSO OPEN ONTO DIFFERENT GROUND, and that is the change the building
    made. The south mouth opens onto SOIL and has to guarantee three rows of it
    in case the treeline closed over the end of the throat. The north mouth
    opens into the SHOP, through the gap `_stamp_shop` already punched in the
    north wall — so it must not lay soil at all: three rows of forest floor
    written over the back of the shop would put a patch of dirt inside the
    building and cut the wall in half.
    """
    depth = STORE_CORRIDOR_TILES
    cx, _ = _apron(width, height)
    half = max(1.5, STORE_LANE_TILES / 2.0 - 1.5)
    x0 = max(0, int(round(cx - half)))
    x1 = min(width - 1, int(round(cx + half)))

    for tx in range(x0, x1 + 1):
        for step in range(depth):
            grid[step][tx] = VOID
            grid[height - 1 - step][tx] = VOID
        # Whatever the treeline did at the very end, the SOUTH mouth has to
        # open onto walkable ground or the party is puppeted into a wall.
        for step in range(depth, depth + 3):
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
    """A `(column, row)` offset from the APRON'S centre, in world pixels.

    The `+ 1.0` on the row is the same convention every fixture in this game
    uses: an offset names the tile a thing stands ON, and a contact point is
    the BOTTOM of that tile.
    """
    acx, acy = _apron(width, height)
    return (acx + col) * TILE_SIZE, (acy + row + 1.0) * TILE_SIZE


def _in(width: int, col: float, row: float) -> tuple[float, float]:
    """A `(column, row)` offset from the SHOP INTERIOR'S centre, in pixels.

    The indoor twin of `_at`, and a separate function rather than a parameter
    because the two origins answer different questions. `_at` places things
    against a clearing that breathes; this places things against WALLS, and a
    counter that came away from its wall when the apron was resized would be
    the loudest possible bug in the room.
    """
    scx, scy = _shop_centre(width)
    return (scx + col) * TILE_SIZE, (scy + row + 1.0) * TILE_SIZE


def _place_stands(width: int, height: int, day: int, rng: random.Random) -> list[Stand]:
    """The six tables, three across and two deep on the shop floor.

    ON THE GRID, not knocked off it — see `STALL_COLS`. Cheapest first, filled
    SOUTH TO NORTH and west to east, because that is the order the party walks
    past them coming through the door: the first table they reach is the one
    they can afford, and the row against the counter is the one they are saving
    for. That ramp is the zone's only tutorial about money.
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
            x, y = _in(width, col, row)
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

    Measured from the apron's CENTRE like everything else outdoors, because
    what has to be guaranteed is the relationship to the way in and to the
    shop's door: the party walks out of the neck and the skids are already
    coming down between them and the building.
    """
    return [_at(width, height, col, row) for col, row in PAYOUT_SPOTS[: max(0, count)]]


def payload_kit(width: int, height: int) -> list[tuple[float, float, int]]:
    """His gear on the apron, in world pixels. One list, read twice.

    Built here rather than inline so the tiles it makes solid and the rows the
    client draws come out of the same call — a footprint derived from a second
    copy of the offsets is a footprint that drifts the first time somebody
    nudges the wagon.
    """
    return [(*_at(width, height, col, row), variant) for col, row, variant in KIT_SPOTS]


def payload_counter(width: int) -> list[tuple[float, float, int]]:
    """The L, in world pixels. `(x, y, kind)` — 0 elbow, 1 east, 2 south."""
    return [(*_in(width, col, row), kind) for col, row, kind in COUNTER_L]


def payload_shelves(width: int) -> list[tuple[float, float, int]]:
    """His shelves on the north wall, in world pixels."""
    return [(*_in(width, col, row), variant) for col, row, variant in SHELF_SPOTS]


def payload_crates(width: int) -> list[tuple[float, float, int]]:
    """The decoration crates around the room, in world pixels."""
    return [(*_in(width, col, row), variant) for col, row, variant in CRATE_SPOTS]


def payload_rugs(width: int) -> list[tuple[float, float, int]]:
    """The mats, in world pixels. Flat: they claim nothing and block nothing."""
    return [(*_in(width, col, row), variant) for col, row, variant in RUG_SPOTS]


def payload_lamps(width: int) -> list[tuple[float, float]]:
    """The lamps' floor contacts, in world pixels.

    Ordinary standing props: a lamp is a vessel on a small table and it sits on
    the ground the way the tables do. `LAMP_FLAME_TILES` is how far above this
    the wick burns, and it is one number in one place so the sprite, the flame
    and the pool of light cannot end up at three different heights.
    """
    return [_in(width, col, row) for col, row in LAMP_SPOTS]


def _torches(
    width: int,
    height: int,
    seed: int,
    keep_out: list[tuple[float, float]],
) -> list[tuple[float, float, int]]:
    """Torch contact points on the APRON, in world pixels.

    THERE ARE NONE INSIDE. The shop is lit from above by lamps on chains, which
    is how a room is lit; a burning post in the middle of a brick floor is how
    a clearing is lit, and putting both in the zone would say the building was
    a tent. What is out here is the ring around the yard, the chain down the
    south throat, a pair at the arrival mouth and — the one that matters — a
    pair either side of the SHOP'S DOOR, because that door is the only thing in
    the zone that has to be findable from across a dark yard.

    A torch is never placed within `TORCH_CLEAR` of something meant to be
    LOOKED AT. A post standing in front of the wagon is one more thing between
    the player and the silhouette that explains who the trader is.
    """
    acx, acy = _apron(width, height)
    _, _, _, shop_bottom = shop_bounds(width)
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
        tx = acx + math.cos(angle) * radius
        ty = acy + math.sin(angle) * radius
        x = (tx + 0.5) * TILE_SIZE
        y = (ty + 1.0) * TILE_SIZE
        if free(x, y):
            placed.append((x, y, index % 2))

    # THE ARRIVAL MOUTH. Ranked and PAIRED, which is the one place out here
    # allowed to look arranged: a doorway is a thing somebody built, and two
    # torches either side of a mouth is what a threshold looks like in every
    # culture that has ever had one.
    mouth_y = height - STORE_CORRIDOR_TILES - 1.5
    for across, back in GATE_TORCHES:
        placed.append(
            (
                (acx + across + 0.5) * TILE_SIZE,
                (mouth_y - back + 1.0) * TILE_SIZE,
                0 if across < 0 else 1,
            )
        )

    # THE SHOP'S DOOR. Same pair, at the other end of the walk, standing out in
    # the yard rather than in the threshold — they are lighting a WALL, and a
    # torch in a doorway lights the inside of the frame and nothing else.
    across, out = DOOR_TORCHES
    for side in (-1, 1):
        placed.append(
            (
                (acx + side * across + 0.5) * TILE_SIZE,
                (shop_bottom + out + 1.0) * TILE_SIZE,
                0 if side < 0 else 1,
            )
        )

    # THE NECK. Staggered either side of the centreline rather than paired, so
    # the throat reads as a path somebody lit and not as an avenue somebody
    # surveyed.
    index = 0
    span = range(STORE_CORRIDOR_TILES + 3, height - STORE_CORRIDOR_TILES - 2, TORCH_SPACING)
    for ty in span:
        if ty <= shop_bottom + SHOP_YARD:
            continue  # the yard and the building: not the neck's business
        if abs(ty - acy) < STORE_CIRCLE_TILES - 1.0:
            continue  # inside the apron: that is the ring's job
        side = 1 if index % 2 else -1
        tx = acx + side * (_neck_half(ty, seed) - 1.3)
        x = (tx + 0.5) * TILE_SIZE
        y = (ty + 1.0) * TILE_SIZE
        if free(x, y):
            placed.append((x, y, index % 2))
        index += 1

    return placed


def _dress(
    width: int,
    torches: list[tuple[float, float, int]],
    lamps: list[tuple[float, float]],
    machine: tuple[float, float],
) -> dict:
    """Every light on the map, shipped as ordinary scenery.

    `PlacedLight` is how a beacon, a cabin lamp, a torch and now a shop lamp
    all reach the lighting, and the lighting has no idea which is which — so
    the whole zone costs no client code at all beyond the sprites.

    TWO SETS THAT NEVER SUM. The torches are outdoors and the lamps are inside
    a brick box; the wall between them is opaque, so the shop's five pools and
    the yard's ring plus three rotor washes are two separate budgets rather
    than one that has to be shared. That is the difference between this layout
    and the clearing it replaced, where every light in the zone landed on the
    same floor — see `zones.STORE_AMBIENT`.
    """
    lights = [
        scenery.PlacedLight(x=x, y=y, radius_tiles=TORCH_LIGHT_TILES, kind=scenery.EMBER)
        for x, y, _ in torches
    ]
    # The lamps, at the BULB rather than at the floor contact. A pool centred
    # on the boards would light the rug and leave the thing that is actually
    # glowing in the dark.
    lights.extend(
        scenery.PlacedLight(
            x=x,
            y=y - TILE_SIZE * LAMP_FLAME_TILES,
            radius_tiles=LAMP_LIGHT_TILES,
            kind=scenery.EMBER,
        )
        for x, y in lamps
    )
    # The machine's marquee. A `PlacedLight` like every other lit thing, so the
    # lighting has no idea one of its sources is electric — but it is placed
    # ABOVE the cabinet's contact, because the bulbs are on the crown.
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
    """Generate the yard and the shop. One shape a night; the stock rolls.

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

    _, _, _, shop_bottom = shop_bounds(width)
    door = ((width - 1) / 2.0 + 0.5) * TILE_SIZE, (shop_bottom + 1.0) * TILE_SIZE

    # Outdoors.
    wagon = _at(width, height, WAGON_COL, WAGON_ROW)
    kit = payload_kit(width, height)
    # Indoors.
    merchant = _in(width, MERCHANT_COL, MERCHANT_ROW)
    machine = _in(width, MACHINE_COL, MACHINE_ROW)
    counter = payload_counter(width)
    shelves = payload_shelves(width)
    crates = payload_crates(width)
    rugs = payload_rugs(width)
    lamps = payload_lamps(width)

    paid = [value for value in (takes or []) if value > 0][: len(PAYOUT_SPOTS)]
    landings = payout_spots(width, height, len(paid))

    # Everything an outdoor torch has to stand clear of: the wagon and his kit.
    # The APRON is NOT on the list — a skid is lowered onto ground that was
    # already lit, and a torch it landed beside is a torch the deck is standing
    # in front of, which is exactly right. Nothing indoors is on the list
    # either, because no torch is ever placed indoors.
    keep_out: list[tuple[float, float]] = [wagon]
    keep_out.extend((kx, ky) for kx, ky, _ in kit)
    torches = _torches(width, height, seed, keep_out)

    # Tables are cover. Claiming the tiles under each one is what stops a
    # player walking through the stock, and it is LOW rather than PROP for the
    # usual reason: you can see over a table.
    for stand in stands:
        _claim(grid, width, height, stand.x, stand.y, TABLE_TILES_W)
    # The counter is the same kind of thing, one section at a time, and the run
    # of them is what actually fences the merchant into his pocket.
    for x, y, _kind in counter:
        _claim(grid, width, height, x, y, COUNTER_TILES_W)
    for x, y, _variant in shelves:
        _claim(grid, width, height, x, y, SHELF_TILES_W)
    for x, y, _variant in crates:
        _claim(grid, width, height, x, y, CRATE_TILES_W)
    # A lamp stands on a small table with an open flame on it. It was walkable
    # while it hung from a chain two tiles overhead, which was correct then and
    # is not now.
    for x, y in lamps:
        _claim(grid, width, height, x, y, LAMP_TILES_W)
    # His gear is solid too, and it is what makes the yard a PLACE: a party
    # cannot walk through the crates to stand inside the wagon.
    for kx, ky, _variant in kit:
        _claim(grid, width, height, kx, ky, KIT_TILES_W)
    _claim(grid, width, height, wagon[0], wagon[1], WAGON_TILES_W)
    # The cabinet is cover the same way a table is, and for the same reason: a
    # body standing inside the one object in the room that is supposed to be
    # looked at is the loudest possible bug.
    _claim(grid, width, height, machine[0], machine[1], MACHINE_TILES_W)
    # A landed skid is solid, exactly as it is out in the woods: it is a
    # loading deck and the party does not stand on it. It STAYS solid for the
    # whole visit, because it stays on screen for the whole visit.
    for px, py in landings:
        _claim(grid, width, height, px, py, PAYOUT_TILES_W)

    # NOTHING claims tiles under the MERCHANT or the RUGS. He is drawn, not
    # walked into, and he is already fenced by his own counter; a rug is a flat
    # thing on the floor. A solid tile under either would be a hole in the room
    # with no visible cause.

    # His campfire, out in the yard. A FIRE tile, so the client's existing
    # campfire sprite and its glow both land with no code. Solid, like every
    # fire in this game, which is correct: you walk around a fire.
    acx, acy = _apron(width, height)
    fire_tx = int(round(acx + FIRE_COL))
    fire_ty = int(round(acy + FIRE_ROW))
    if 0 <= fire_ty < height and 0 <= fire_tx < width:
        grid[fire_ty][fire_tx] = FIRE

    payload = {
        "merchant": [round(merchant[0], 1), round(merchant[1], 1)],
        "wagon": [round(wagon[0], 1), round(wagon[1], 1)],
        "door": [round(door[0], 1), round(door[1], 1)],
        "stands": [stand.to_payload() for stand in stands],
        # THE AMMUNITION CRATES START EMPTY AND THE ROOM FILLS THEM. Which
        # calibres are on the wall is a fact about the PARTY's belt, and this
        # function is handed a day and a seed — see `Room._sync_ammo_boxes`,
        # which writes the row back onto this payload the moment somebody
        # walks in carrying a gun.
        "boxes": [],
        "torches": [[round(x, 1), round(y, 1), kind] for x, y, kind in torches],
        "machine": [round(machine[0], 1), round(machine[1], 1)],
        "kit": [[round(x, 1), round(y, 1), variant] for x, y, variant in kit],
        "counter": [[round(x, 1), round(y, 1), kind] for x, y, kind in counter],
        "shelves": [[round(x, 1), round(y, 1), variant] for x, y, variant in shelves],
        "crates": [[round(x, 1), round(y, 1), variant] for x, y, variant in crates],
        "rugs": [[round(x, 1), round(y, 1), variant] for x, y, variant in rugs],
        "lamps": [[round(x, 1), round(y, 1)] for x, y in lamps],
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
        scenery=_dress(width, torches, lamps, machine),
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
