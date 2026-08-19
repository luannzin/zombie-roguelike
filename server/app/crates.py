"""Interactive objects: the things in the forest a player walks up to and USES.

The module is still called `crates.py` and the wire still says `crates`, the
same way `rift.py` still says `rifts`. That is history, not a second mechanic:
this list used to hold five kinds of anonymous wood and it now holds barrels,
boxes, chests, mailboxes, altars and abandoned vehicles, and renaming a field
across twenty client files buys nothing this line cannot say.

WHY A CRATE WAS NOT ENOUGH
A crate is a noun with one verb, and once a player has smashed four of them
the fifth is furniture. What the map needed was not more containers but more
KINDS of promise, so an object here carries its own:

    verb        BREAK (a barrel: shoot it, or E) or OPEN (everything else).
    drop table  what falls out, and how often nothing does.
    tags        what KIND of thing belongs in it, biasing the catalog roll —
                an ambulance holds different things from a mailbox.
    rarity      some objects roll off a better table. A chest always pays.
    ambush      the chance that what is inside a vehicle is a passenger.

Every one of those is data on `ObjectType` and reaches the client through
`welcome.config.objects`, so adding an object is a row here, a sheet in
`server/tools/make_objects.py` and a scene in `scenery.py`.

Scenery still PLACES them — a checkpoint without its barrels is not a
checkpoint — but once the stamp has claimed the tiles they become live
objects. The client draws them from this list, not from the scenery props, so
using one can change its state without rewriting the map payload. USING DOES
NOT DELETE: the object flips to `opened`, keeps its tiles unless it was a
BREAK, and stands there holding its last animation frame for the rest of the
night.

Server-authoritative, both verbs. E sends `{type:"break","id"}` (one message,
because from the input's point of view "use the thing in front of me" is one
intent); a bullet that hits a BREAK object's sprite box does the same. An OPEN
object ignores bullets: shooting a car bonnet open is not a thing, and letting
a stray round pop every container on the map would delete the walk.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .config import TILE_SIZE
from .loot import RARITY_WEIGHTS, roll_item
from .scenery import STANDING, Prop

KIND = "crate"

VERB_BREAK = "break"
VERB_OPEN = "open"

DROP_EMPTY = "empty"
DROP_COIN = "coin"
DROP_ITEM = "item"

#: The default table. Empty is the common case — a pile of wood is not a shop.
#:
#: COIN is DARK GOLD (`coins.py`), the player's own currency and now an ANOMALY
#: SHARD, and it is the thinnest slice on every object in the game on purpose.
#: What an explorable is FOR is the ITEM: that is what gets carried to a
#: platform and becomes the group's balance, which is the number a night is
#: scored on. Coin weight is the second tap on dark gold — the first is
#: `config.COIN_DROP_CHANCE` on corpses — and the two move together. Both were
#: cut again when the coin became a shard: a piece of the anomaly is a rare
#: find or it is nothing, and the weight that survives here is what stops a
#: party who opens every crate in the forest from routing around the corpse
#: tap. Item weight is untouched, as it was the last time: this made a currency
#: scarcer, not the forest poorer — the difference goes to EMPTY.
BASE_DROPS: dict[str, float] = {DROP_EMPTY: 77, DROP_COIN: 5, DROP_ITEM: 18}


@dataclass(frozen=True)
class ObjectType:
    """One kind of interactive object. Frozen data, like `EnemyType`."""

    key: str
    #: Scenery prop sheet this draws from, and the sheet KIND inside it.
    #: Several types can share one sheet — every vehicle is a frame row of
    #: `vehicle.png` — which is why the two are separate fields.
    sheet: str
    variant: int
    verb: str
    #: The VERB the HUD offers, and only the verb: the prompt itself reads
    #: "Aperte E para {label}". Portuguese, because the HUD is. Authored here
    #: next to the drop table so the promise and the wording cannot drift —
    #: `vasculhar` is on the objects that mostly hold nothing, `abrir` on the
    #: ones that mostly do.
    label: str
    #: Footprint in tiles. Vehicles are FOUR wide, and that is the point of
    #: them: a car is the only piece of cover in the forest long enough to
    #: break a sightline while you are standing still behind it.
    tiles_w: int = 1
    #: Shot box, in tiles, bottom-centred on the contact. Only BREAK objects
    #: are ever tested against it.
    hit_w_tiles: float = 1.0
    hit_h_tiles: float = 2.0
    #: How far the verb carries as sound, in tiles. Breaking is louder than
    #: opening, and a car bonnet is louder than a mailbox.
    noise_tiles: float = 5.5
    drops: dict[str, float] = field(default_factory=lambda: dict(BASE_DROPS))
    #: Dark gold paid when the roll lands on COIN, inclusive. Left wide while
    #: the WEIGHT came down: a coin drop should stay worth the walk over to it,
    #: and a currency that got both rarer and smaller in the same pass would be
    #: two cuts sold as one.
    coins: tuple[int, int] = (1, 3)
    #: Catalog tags the item roll is biased toward. Empty means no bias.
    tags: tuple[str, ...] = ()
    #: Rarity table override. None uses the world's own.
    rarity: dict[str, float] | None = None
    #: Chance that opening this wakes something that was inside it.
    ambush: float = 0.0

    @property
    def hit_w(self) -> float:
        return TILE_SIZE * self.hit_w_tiles

    @property
    def hit_h(self) -> float:
        return TILE_SIZE * self.hit_h_tiles

    @property
    def noise(self) -> float:
        return TILE_SIZE * self.noise_tiles

    def client_payload(self) -> dict:
        return {
            "sheet": self.sheet,
            "variant": self.variant,
            "verb": self.verb,
            "label": self.label,
            "tilesW": self.tiles_w,
            "hitW": self.hit_w,
            "hitH": self.hit_h,
        }


#: Rarity tables the objects lean on. The world's own (`RARITY_WEIGHTS`) is
#: the floor; these are the reasons to walk to a specific thing.
GOOD_ODDS: dict[str, float] = {
    "common": 26, "uncommon": 32, "rare": 24, "epic": 13, "legendary": 5,
}
#: The shrine's. Nothing in the forest else rolls off this — it is what a
#: clearing full of statues and a dozen creatures is paying for.
SHRINE_ODDS: dict[str, float] = {
    "common": 6, "uncommon": 18, "rare": 30, "epic": 30, "legendary": 16,
}
#: A bin. Mostly rubbish, and once in a while not, which is the joke.
JUNK_ODDS: dict[str, float] = {
    "common": 72, "uncommon": 18, "rare": 6, "epic": 3, "legendary": 1,
}

OPEN_LABEL = "abrir"
BREAK_LABEL = "destruir"
SEARCH_LABEL = "vasculhar"

TYPES: tuple[ObjectType, ...] = (
    # --- BREAK ---------------------------------------------------------
    # The one verb with a gun attached to it. A barrel is the object you can
    # deal with from across the clearing, and paying for that with a louder
    # noise and a worse table is what keeps the quiet verb worth walking for.
    ObjectType(
        key="barrel", sheet="barrel", variant=0, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=5.5, tags=("supplies", "scrap", "camp"),
    ),
    ObjectType(
        key="drum", sheet="barrel", variant=1, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=6.5, tags=("supplies", "tools", "scrap"),
        drops={DROP_EMPTY: 62, DROP_COIN: 16, DROP_ITEM: 22},
    ),
    ObjectType(
        key="fuel_drum", sheet="barrel", variant=2, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=7.5, tags=("supplies", "travel", "scrap"),
        drops={DROP_EMPTY: 68, DROP_COIN: 14, DROP_ITEM: 18},
    ),
    # THE CRATE SHEET IS EIGHT ROWS OF ONE OBJECT, AND THE CONDITION IS THE
    # TABLE. A barrel tells you nothing about itself from across a clearing —
    # that is the point of it, and why all three roll off much the same odds.
    # A crate is the opposite: `make_objects.CRATE_RECIPES` spends its whole
    # silhouette budget on saying what has HAPPENED to this one, so the art is
    # already making a promise before the player has walked over, and the
    # table's only job is to keep it. Read down the list and the rule is one
    # sentence: what somebody bothered to reinforce is worth more, and what
    # the forest has already had a year with is worth less.
    #
    # They are BREAK rather than OPEN for the same reason the barrels are:
    # wood in this game is the thing you can deal with from range, and a
    # sheet whose eight frames are all smashes cannot also hold eight lid
    # animations. The noise is the price, and it scales with the build —
    # bursting an ironbound crate is the loudest thing in the forest short of
    # a fuel drum.
    ObjectType(
        key="crate", sheet="crate", variant=0, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=5.0, tags=("supplies", "tools", "abandoned"),
    ),
    # Already open to the sky, and it has been for a while. The worst table on
    # the sheet, and the silhouette says so before the player commits to it.
    ObjectType(
        key="crate_broken", sheet="crate", variant=1, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=4.0, tags=("scrap", "abandoned"),
        drops={DROP_EMPTY: 86, DROP_COIN: 4, DROP_ITEM: 10},
    ),
    # Battens, a rope lashing and the height of something packed to travel.
    # The best wooden table in the forest, and the second loudest.
    ObjectType(
        key="crate_braced", sheet="crate", variant=2, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=6.5, tags=("military", "supplies", "travel"),
        drops={DROP_EMPTY: 44, DROP_COIN: 14, DROP_ITEM: 42},
        rarity=GOOD_ODDS,
    ),
    # Two boxes, so two chances at the same table — the only object in the
    # game whose art says "this is more than one of the thing" and then is.
    ObjectType(
        key="crate_stacked", sheet="crate", variant=3, verb=VERB_BREAK, label=BREAK_LABEL,
        hit_h_tiles=2.5, noise_tiles=6.0, tags=("supplies", "tools", "camp"),
        drops={DROP_EMPTY: 50, DROP_COIN: 12, DROP_ITEM: 38},
    ),
    # Something already went through this one. Middling, and the hole in the
    # near wall is the tell.
    ObjectType(
        key="crate_battered", sheet="crate", variant=4, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=4.5, tags=("scrap", "abandoned", "camp"),
        drops={DROP_EMPTY: 74, DROP_COIN: 8, DROP_ITEM: 18},
    ),
    # A year of wet. Rotted wood barely holds a table at all, but the moss is
    # the only saturated thing on the sheet and the forest owes the player
    # something for reading it.
    ObjectType(
        key="crate_rotted", sheet="crate", variant=5, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=3.5, tags=("living", "abandoned"),
        drops={DROP_EMPTY: 80, DROP_COIN: 6, DROP_ITEM: 14},
        rarity=JUNK_ODDS,
    ),
    # Steel corners, bands and bolts. Whatever is in here was worth the iron,
    # and bursting it is heard across the clearing.
    ObjectType(
        key="crate_ironbound", sheet="crate", variant=6, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=7.5, tags=("military", "combat", "supplies"),
        drops={DROP_EMPTY: 38, DROP_COIN: 16, DROP_ITEM: 46},
        coins=(2, 5), rarity=GOOD_ODDS,
    ),
    # The lid has fallen in. Whatever it held has been under the weather ever
    # since, and the table is the second worst here.
    ObjectType(
        key="crate_collapsed", sheet="crate", variant=7, verb=VERB_BREAK, label=BREAK_LABEL,
        noise_tiles=4.0, tags=("scrap", "abandoned"),
        drops={DROP_EMPTY: 84, DROP_COIN: 5, DROP_ITEM: 11},
    ),
    # --- OPEN: containers ----------------------------------------------
    ObjectType(
        key="box", sheet="box", variant=0, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.5, noise_tiles=3.0, tags=("supplies", "tools", "abandoned"),
        drops={DROP_EMPTY: 52, DROP_COIN: 16, DROP_ITEM: 32},
    ),
    ObjectType(
        key="ammo_case", sheet="box", variant=1, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.5, noise_tiles=3.0, tags=("military", "supplies", "combat"),
        drops={DROP_EMPTY: 36, DROP_COIN: 12, DROP_ITEM: 52},
    ),
    ObjectType(
        key="tote", sheet="box", variant=2, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.5, noise_tiles=3.0, tags=("living", "camp", "abandoned"),
    ),
    # A chest ALWAYS pays, and it is the only object in the game that does.
    # That guarantee is the whole design: the domed lid is visible from across
    # a clearing, so the walk to it is a decision the player is allowed to
    # make on information, and a decision on information that comes up empty
    # teaches them to stop reading the map.
    ObjectType(
        key="chest", sheet="chest", variant=0, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_w_tiles=1.25, hit_h_tiles=1.5, noise_tiles=4.0,
        tags=("valuables", "relics", "living"),
        drops={DROP_ITEM: 100}, rarity=GOOD_ODDS,
    ),
    ObjectType(
        key="strongbox", sheet="chest", variant=1, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_w_tiles=1.25, hit_h_tiles=1.5, noise_tiles=4.0,
        tags=("valuables", "military", "supplies"),
        drops={DROP_ITEM: 100}, rarity=GOOD_ODDS,
    ),
    # --- OPEN: the small stuff -----------------------------------------
    ObjectType(
        key="mailbox", sheet="stash", variant=0, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.5, noise_tiles=2.5, tags=("living", "dropped"),
        drops={DROP_EMPTY: 68, DROP_COIN: 18, DROP_ITEM: 14},
    ),
    ObjectType(
        key="suitcase", sheet="stash", variant=1, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.0, noise_tiles=2.5, tags=("travel", "living", "dropped"),
        drops={DROP_EMPTY: 44, DROP_COIN: 14, DROP_ITEM: 42},
    ),
    ObjectType(
        key="freezer", sheet="stash", variant=2, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.25, noise_tiles=3.5, tags=("supplies", "living", "electronics"),
        drops={DROP_EMPTY: 56, DROP_COIN: 14, DROP_ITEM: 30},
    ),
    ObjectType(
        key="bin", sheet="stash", variant=3, verb=VERB_OPEN, label=SEARCH_LABEL,
        hit_h_tiles=1.25, noise_tiles=3.0, tags=("scrap", "abandoned"),
        drops={DROP_EMPTY: 70, DROP_COIN: 12, DROP_ITEM: 18}, rarity=JUNK_ODDS,
    ),
    ObjectType(
        key="toolbox", sheet="stash", variant=4, verb=VERB_OPEN, label=OPEN_LABEL,
        hit_h_tiles=1.0, noise_tiles=2.5, tags=("tools", "scrap", "supplies"),
        drops={DROP_EMPTY: 40, DROP_COIN: 12, DROP_ITEM: 48},
    ),
    # --- OPEN: vehicles -------------------------------------------------
    # FOUR TILES WIDE, and every one of them can have somebody still in it.
    # The ambush is not a spawn budget trick: it is what makes opening the
    # third car of the night a decision rather than a chore, and it is the
    # cheapest source of a story the map has. You open a boot, nothing. You
    # open a boot, a passenger.
    ObjectType(
        key="car", sheet="vehicle", variant=0, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=6.0,
        tags=("travel", "living", "dropped"), ambush=0.22,
        drops={DROP_EMPTY: 56, DROP_COIN: 14, DROP_ITEM: 30},
    ),
    ObjectType(
        key="van", sheet="vehicle", variant=1, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=6.5,
        tags=("supplies", "tools", "travel"), ambush=0.26,
        drops={DROP_EMPTY: 46, DROP_COIN: 14, DROP_ITEM: 40},
    ),
    ObjectType(
        key="ambulance", sheet="vehicle", variant=2, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=6.5,
        tags=("medical", "supplies", "electronics"), ambush=0.42,
        drops={DROP_EMPTY: 34, DROP_COIN: 12, DROP_ITEM: 54}, rarity=GOOD_ODDS,
    ),
    ObjectType(
        key="cruiser", sheet="vehicle", variant=3, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=6.5,
        tags=("military", "combat", "supplies"), ambush=0.34,
        drops={DROP_EMPTY: 40, DROP_COIN: 12, DROP_ITEM: 48}, rarity=GOOD_ODDS,
    ),
    ObjectType(
        key="lorry", sheet="vehicle", variant=4, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=7.0,
        tags=("supplies", "scrap", "tools"), ambush=0.30,
        drops={DROP_EMPTY: 38, DROP_COIN: 12, DROP_ITEM: 50},
    ),
    ObjectType(
        key="bus", sheet="vehicle", variant=5, verb=VERB_OPEN, label=SEARCH_LABEL,
        tiles_w=4, hit_w_tiles=4.0, hit_h_tiles=2.5, noise_tiles=7.0,
        tags=("travel", "living", "dropped"), ambush=0.46,
        drops={DROP_EMPTY: 42, DROP_COIN: 14, DROP_ITEM: 44},
    ),
    # --- OPEN: the shrine ------------------------------------------------
    ObjectType(
        key="altar", sheet="altar", variant=0, verb=VERB_OPEN, label=OPEN_LABEL,
        tiles_w=2, hit_w_tiles=1.75, hit_h_tiles=1.5, noise_tiles=5.0,
        tags=("relics", "valuables", "nature"),
        drops={DROP_ITEM: 100}, rarity=SHRINE_ODDS,
    ),
    ObjectType(
        key="cairn", sheet="altar", variant=1, verb=VERB_OPEN, label=OPEN_LABEL,
        tiles_w=2, hit_w_tiles=1.75, hit_h_tiles=1.5, noise_tiles=5.0,
        tags=("relics", "valuables"),
        drops={DROP_ITEM: 100}, rarity=SHRINE_ODDS,
    ),
)

BY_KEY: dict[str, ObjectType] = {kind.key: kind for kind in TYPES}
#: What `scenery.py` may emit as a piece kind and `attach` will pull out.
OBJECT_KINDS: frozenset[str] = frozenset(BY_KEY)

DEFAULT_TYPE = TYPES[0]


def type_of(key: str) -> ObjectType:
    return BY_KEY.get(key, DEFAULT_TYPE)


def catalog_payload() -> dict:
    """Sheet, verb, prompt and hit box per object, for `welcome.config`."""
    return {kind.key: kind.client_payload() for kind in TYPES}


@dataclass
class Crate:
    """One live object on the map."""

    id: str
    #: Object TYPE key — `barrel`, `ambulance`, `altar`. On the wire as `t`.
    kind: str
    x: float
    y: float
    #: Sheet frame row. Carried rather than looked up so the client can draw a
    #: break event for an object that is already gone from the live list.
    variant: int
    flip: bool
    tx: int
    ty: int
    #: Already used. The object STAYS ON THE MAP — a searched car is still a
    #: car — it just holds its last animation frame, refuses the prompt and
    #: never rolls a second drop. Removing it was the old behaviour and it
    #: read as the forest deleting its own furniture.
    opened: bool = False

    @property
    def type(self) -> ObjectType:
        return type_of(self.kind)

    def cells(self) -> list[tuple[int, int]]:
        """Every tile this object stands on. Vehicles claim four."""
        width = self.type.tiles_w
        left = self.tx - (width - 1) // 2
        return [(left + offset, self.ty) for offset in range(width)]

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "t": self.kind,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
            "flip": 1 if self.flip else 0,
            "o": 1 if self.opened else 0,
        }


@dataclass
class CrateBreak:
    """An object that was just used. The client plays the sheet and the juice."""

    crate_id: str
    kind: str
    x: float
    y: float
    variant: int
    flip: bool
    drop: str
    key: str | None = None
    #: Something came out that was not loot.
    ambush: bool = False

    def to_payload(self) -> dict:
        row = {
            "id": self.crate_id,
            "t": self.kind,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
            "flip": 1 if self.flip else 0,
            "drop": self.drop,
        }
        if self.key:
            row["k"] = self.key
        if self.ambush:
            row["amb"] = 1
        return row


def footprint(x: float, y: float) -> tuple[int, int]:
    """The tile a contact point lands in. Mirrors `scenery._cells`."""
    tx = int(math.floor(x / TILE_SIZE))
    ty = int(math.floor(y / TILE_SIZE - 1e-6))
    return tx, ty


def attach(population) -> list[dict]:
    """Strip interactive objects from a Population and return their wire rows.

    Their tiles are already stamped. Call this after `scenery.populate`,
    before `to_payload`, so the map does not draw the same barrel twice.
    """
    kept, objects = extract(population.props)
    population.props[:] = kept
    return [obj.to_payload() for obj in objects]


def extract(props: list[Prop]) -> tuple[list[Prop], list[Crate]]:
    """Pull interactive objects out of a scenery prop list and give them ids."""
    kept: list[Prop] = []
    objects: list[Crate] = []
    next_id = 1
    for prop in props:
        if prop.kind in OBJECT_KINDS and prop.layer == STANDING:
            tx, ty = footprint(prop.x, prop.y)
            objects.append(
                Crate(
                    id=f"k{next_id}",
                    kind=prop.kind,
                    x=prop.x,
                    y=prop.y,
                    variant=prop.variant,
                    flip=prop.flip,
                    tx=tx,
                    ty=ty,
                )
            )
            next_id += 1
        else:
            kept.append(prop)
    return kept, objects


def from_payloads(rows: list[dict]) -> dict[str, Crate]:
    objects: dict[str, Crate] = {}
    for row in rows:
        crate_id = str(row["id"])
        x = float(row["x"])
        y = float(row["y"])
        tx, ty = footprint(x, y)
        kind = str(row.get("t", DEFAULT_TYPE.key))
        objects[crate_id] = Crate(
            id=crate_id,
            kind=kind,
            x=x,
            y=y,
            variant=int(row.get("v", type_of(kind).variant)),
            flip=bool(row.get("flip")),
            tx=tx,
            ty=ty,
            opened=bool(row.get("o")),
        )
    return objects


def nearest(crates: dict[str, Crate], x: float, y: float, max_dist: float) -> Crate | None:
    """Closest object whose BODY is within reach.

    Distance is measured to the nearest point of the footprint rather than to
    the contact point, because a bus is four tiles long: measured centre to
    centre, standing at its rear door is standing two tiles from the object
    and the prompt refuses on the exact spot the art says to press.
    """
    best: Crate | None = None
    best_d2 = max_dist * max_dist
    for crate in crates.values():
        if crate.opened:
            continue
        half = crate.type.tiles_w * TILE_SIZE * 0.5
        dx = max(0.0, abs(crate.x - x) - half)
        dy = crate.y - y
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = crate
    return best


def hitbox(crate: Crate) -> tuple[float, float, float, float]:
    """Sprite box, bottom-centred on the contact. Read off the object's type."""
    kind = crate.type
    half = kind.hit_w * 0.5
    return crate.x - half, crate.y - kind.hit_h, crate.x + half, crate.y


def ray_aabb(
    ox: float,
    oy: float,
    dx: float,
    dy: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> float | None:
    """Nearest t>=0 where the unit ray hits the axis-aligned box, else None."""
    tmin = 0.0
    tmax = math.inf

    if abs(dx) < 1e-12:
        if ox < left or ox > right:
            return None
    else:
        tx1 = (left - ox) / dx
        tx2 = (right - ox) / dx
        if tx1 > tx2:
            tx1, tx2 = tx2, tx1
        tmin = max(tmin, tx1)
        tmax = min(tmax, tx2)

    if abs(dy) < 1e-12:
        if oy < top or oy > bottom:
            return None
    else:
        ty1 = (top - oy) / dy
        ty2 = (bottom - oy) / dy
        if ty1 > ty2:
            ty1, ty2 = ty2, ty1
        tmin = max(tmin, ty1)
        tmax = min(tmax, ty2)

    if tmax < tmin:
        return None
    return tmin


def along_ray(
    crates: dict[str, Crate],
    ox: float,
    oy: float,
    dx: float,
    dy: float,
    max_dist: float,
) -> tuple[Crate | None, float]:
    """Closest BREAKABLE object whose sprite box the ray hits, within range.

    Openable objects are skipped, and that is a rule about what a gun is for:
    a car bonnet does not come open because somebody shot near it, and a
    single stray round that popped every container in a clearing would delete
    the walk this whole module exists to create.
    """
    best: Crate | None = None
    best_d = max_dist
    for crate in crates.values():
        if crate.opened or crate.type.verb != VERB_BREAK:
            continue
        left, top, right, bottom = hitbox(crate)
        dist = ray_aabb(ox, oy, dx, dy, left, top, right, bottom)
        if dist is not None and dist <= best_d:
            best = crate
            best_d = dist
    return best, best_d


def roll_drop(
    kind: ObjectType, rng: random.Random, items: bool = True
) -> tuple[str, str | None, int]:
    """`(outcome, item_key, coin_count)` for opening or breaking one object.

    `items=False` is the run home. Once the last pad has launched there is
    nothing left to spend a find on and the ground has been swept
    (`Room._clear_loot`), so an object rolls COINS ONLY from there — putting a
    fresh bottle back on a map that was just cleared of them would undo the
    sweep one boot at a time.

    The item weight FOLDS INTO COIN rather than into empty. What changes is
    what falls out, not whether anything does: an object that mostly stopped
    paying at the exact moment the party is running past it would read as the
    game switching off, and coins still count on the way out.
    """
    weights = dict(kind.drops)
    if not items:
        weights[DROP_COIN] = weights.get(DROP_COIN, 0.0) + weights.pop(DROP_ITEM, 0.0)
        # A chest is nothing but item weight, so folding it leaves a table that
        # is all coin — which is right: the guarantee is that it pays, and on
        # the way out gold is the only thing that still counts as paying.
        if not weights:
            weights = {DROP_COIN: 1.0}
    total = sum(weights.values())
    if total <= 0:
        return DROP_EMPTY, None, 0
    roll = rng.uniform(0, total)
    outcome = DROP_EMPTY
    for name, weight in weights.items():
        roll -= weight
        if roll <= 0:
            outcome = name
            break
    if outcome == DROP_COIN:
        return DROP_COIN, None, rng.randint(*kind.coins)
    if outcome == DROP_ITEM:
        item = roll_item(rng, kind.tags, kind.rarity or RARITY_WEIGHTS)
        if item is None:
            return DROP_EMPTY, None, 0
        return DROP_ITEM, item.key, 0
    return DROP_EMPTY, None, 0
