"""World loot: collectable items placed next to scenes.

Coins are gold that flies off a corpse. These are the things people left —
a bottle by a tent, a ring in a cabin, a relic at the landmark — and the
player walks up and presses E. Server-authoritative: the client draws and
sends `{type:"collect","id"}`; this module decides whether they were close
enough and what they got. A bag toss (`{type:"drop","slot"}`) comes back
through `place_near` — walkable floor around the feet, never a client
position.

Placement is a consequence of scenery. A scene is still the unit of
decoration; loot is a second pass over the scenes that landed, rolling a
rarity and picking an item that belongs in that kind of place. A cabin holds
valuables. A dumpsite holds scrap. A deadfall almost never holds anything.
Nothing here places an item on its own — that would be texture, and texture
is the client's job.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import TILE_SIZE
from .world import FLOOR

RARITIES = ("common", "uncommon", "rare", "epic", "legendary")

# Base odds for a roll that is not standing in a landmark. Common is the
# forest floor; legendary is a story.
RARITY_WEIGHTS: dict[str, float] = {
    "common": 55,
    "uncommon": 28,
    "rare": 12,
    "epic": 4,
    "legendary": 1,
}

# The cabin is the one place that was *lived in*. Shift the table toward
# the top so a homestead is worth walking to.
LANDMARK_WEIGHTS: dict[str, float] = {
    "common": 18,
    "uncommon": 28,
    "rare": 28,
    "epic": 18,
    "legendary": 8,
}


@dataclass(frozen=True)
class ItemDef:
    key: str
    name: str
    rarity: str
    #: What kind of place this belongs in. Overlap with a scene's tags is
    #: how a radio lands at a campsite and a crown lands in a cabin.
    tags: tuple[str, ...]
    #: How heavy one of these is. The bag sums them; past a fraction of
    #: max carry the walk slows. Not a reject — overweight is allowed.
    weight: float
    #: What it is worth. The HUD slot shows it; extraction will spend it.
    value: int
    #: Where a collect puts it. `hotbar` is guns (no stack); `bag` is the
    #: pocket; `ammo` goes straight into the reserve for its calibre and takes
    #: no slot at all — see `ammo.py`. Ammunition is not cargo, it is upkeep,
    #: and a round that ate a pocket slot would be competing with the loot the
    #: gun exists to help you carry out.
    pocket: str = "bag"
    #: Which reserve an `ammo` row fills, and how many rounds one box is
    #: worth. Empty on everything else.
    ammo: str = ""
    rounds: int = 0
    #: Whether the world may ever produce one. False for gear everybody
    #: already has — it keeps the row in the catalog, so the HUD can name it
    #: and draw it, while keeping it out of every rarity pool.
    droppable: bool = True


# Catalog order is the loot atlas frame order (see tools/make_loot.py).
ITEMS: tuple[ItemDef, ...] = (
    ItemDef("old_tools", "Ferramentas velhas", "common", ("tools", "abandoned", "scrap"), 2.5, 8),
    ItemDef("empty_bottle", "Garrafa vazia", "common", ("camp", "abandoned", "scrap"), 0.8, 4),
    ItemDef("broken_toy", "Brinquedo quebrado", "common", ("living", "dropped"), 0.6, 5),
    ItemDef("broken_clock", "Relógio quebrado", "common", ("living", "abandoned"), 1.2, 7),
    ItemDef("scrap", "Sucata", "common", ("scrap", "supplies"), 2.0, 6),
    ItemDef("rusty_can", "Lata enferrujada", "common", ("scrap", "supplies", "camp"), 0.3, 3),
    ItemDef("torn_map", "Mapa rasgado", "common", ("travel", "dropped"), 0.1, 6),
    ItemDef("spark_plug", "Vela de ignição", "common", ("tools", "travel", "scrap"), 0.2, 5),
    ItemDef("license_plate", "Placa de carro", "common", ("travel", "scrap", "dropped"), 0.9, 7),
    ItemDef("camera", "Câmera", "uncommon", ("electronics", "abandoned", "living"), 1.0, 22),
    ItemDef("old_headphone", "Fone velho", "uncommon", ("electronics", "camp"), 0.4, 18),
    ItemDef("portable_radio", "Rádio portátil", "uncommon", ("electronics", "camp", "travel"), 1.4, 28),
    ItemDef("compass", "Bússola", "uncommon", ("travel", "dropped"), 0.3, 24),
    ItemDef("car_battery", "Bateria automotiva", "uncommon", ("travel", "tools", "electronics"), 5.0, 26),
    ItemDef("first_aid", "Kit de primeiros socorros", "uncommon", ("medical", "supplies"), 1.0, 30),
    ItemDef("road_flare", "Sinalizador", "uncommon", ("travel", "supplies", "military"), 0.3, 20),
    ItemDef("wrench_set", "Jogo de chaves", "uncommon", ("tools", "travel", "scrap"), 1.8, 21),
    ItemDef("military_camera", "Câmera militar", "rare", ("military", "electronics"), 1.2, 55),
    ItemDef("gold_ring", "Anel de ouro", "rare", ("valuables", "living"), 0.15, 70),
    ItemDef("binoculars", "Binóculo", "rare", ("travel", "military"), 1.0, 60),
    ItemDef("precious_gem", "Gema preciosa", "rare", ("valuables", "nature"), 0.25, 75),
    ItemDef("morphine", "Morfina", "rare", ("medical", "supplies"), 0.2, 58),
    ItemDef("police_radio", "Rádio policial", "rare", ("military", "electronics", "combat"), 0.8, 62),
    ItemDef("night_vision", "Visão noturna", "rare", ("military", "electronics"), 1.1, 80),
    ItemDef("bone_charm", "Amuleto de osso", "rare", ("relics", "nature"), 0.2, 52),
    ItemDef("stone_idol", "Ídolo de pedra", "epic", ("relics", "nature"), 2.2, 120),
    ItemDef("tribal_mask", "Máscara tribal", "epic", ("relics", "living"), 1.1, 130),
    ItemDef("ancient_amulet", "Amuleto antigo", "epic", ("relics", "valuables"), 0.4, 150),
    ItemDef("gold_figurine", "Estatueta de ouro", "epic", ("valuables", "living"), 1.6, 160),
    ItemDef("raw_diamond", "Diamante bruto", "epic", ("valuables", "nature"), 0.5, 170),
    ItemDef("black_pearl", "Pérola negra", "epic", ("valuables", "relics"), 0.2, 180),
    ItemDef("ritual_dagger", "Adaga ritual", "epic", ("relics", "combat", "valuables"), 0.7, 140),
    ItemDef("bank_ledger", "Livro-caixa do banco", "epic", ("valuables", "living", "supplies"), 1.4, 125),
    ItemDef("black_diamond", "Diamante negro", "legendary", ("valuables", "relics"), 0.5, 320),
    ItemDef("lost_crown", "Coroa perdida", "legendary", ("valuables", "living"), 1.8, 400),
    ItemDef("sanctuary_relic", "Relíquia do santuário", "legendary", ("relics",), 2.0, 380),
    ItemDef("vault_key", "Chave do cofre nacional", "legendary", ("valuables", "supplies"), 0.3, 350),
    ItemDef("royal_ring", "Anel da família real", "legendary", ("valuables", "living"), 0.15, 420),
    ItemDef("obsidian_totem", "Totem de obsidiana", "legendary", ("relics", "nature"), 2.4, 360),
    ItemDef("ancestor_skull", "Crânio do ancestral", "legendary", ("relics",), 1.2, 340),
    # AMMUNITION. `pocket="ammo"` means a collect never touches a bag slot —
    # it tops up the reserve for that calibre (`ammo.py`) and is gone. Their
    # `value` is deliberately ZERO: an extraction platform carries CARGO, and
    # a box of rounds is what you spent getting the cargo, not the cargo.
    # Never rolled off a rarity table either — `droppable` is False and
    # `ammo.scatter` is the only thing in the game that places one, because a
    # box of .308 on a map where nobody owns a rifle is litter.
    ItemDef("ammo_pistol", "Munição de pistola", "common", ("military", "combat"), 0.4, 0,
            "ammo", ammo="pistol", rounds=24, droppable=False),
    ItemDef("ammo_rifle", "Munição de rifle", "uncommon", ("military", "combat"), 0.8, 0,
            "ammo", ammo="rifle", rounds=45, droppable=False),
    ItemDef("ammo_awp", "Munição de precisão", "rare", ("military", "combat"), 0.6, 0,
            "ammo", ammo="awp", rounds=6, droppable=False),
    # Guns. Combat stats live in weapons.py; these rows are the name, the
    # rarity, the loot-atlas frame and the weight — and the PRICE the shop
    # derives its own from (`store.price_of`).
    #
    # NOT DROPPABLE, AND THAT IS THE WHOLE FIREARM ECONOMY. No barrel, no
    # boot, no shrine and no scene ever produces one: the merchant is the
    # only source, so a gun is something the party DECIDED to buy with a
    # night's extraction rather than something the forest handed them. It also
    # makes ammunition mean something — a calibre nobody paid for is a calibre
    # nobody finds boxes of.
    ItemDef("glock18", "Glock 18", "common", ("military", "combat"), 1.1, 40, "hotbar",
            droppable=False),
    ItemDef("deagle", "Desert Eagle", "uncommon", ("military", "combat"), 2.2, 90, "hotbar",
            droppable=False),
    ItemDef("famas", "FAMAS", "rare", ("military", "combat"), 3.4, 160, "hotbar",
            droppable=False),
    ItemDef("ak47", "AK-47", "epic", ("military", "combat"), 4.0, 240, "hotbar",
            droppable=False),
    ItemDef("awp", "AWP", "legendary", ("military", "combat"), 6.2, 400, "hotbar",
            droppable=False),
    # The knife is a catalog row for its NAME, its ICON and its WEIGHT, and
    # for nothing else: it is never scattered, never rolled and never
    # collected — everybody already has one. It stays out of `BY_RARITY`'s
    # useful half by being the cheapest common in the game, and `scatter`
    # only ever reaches it through a tag overlap it does not have.
    ItemDef("knife", "Faca", "common", ("combat",), 0.5, 12, "hotbar", droppable=False),
    # WHAT THE ANOMALY GAVE BACK. Never scattered, never rolled, never in a
    # crate: the only thing that makes one is overfeeding a pad and then
    # closing it (`Room._drop_excess`). Its catalog `value` and `weight` are a
    # BASE — the real ones ride on the drop, because what it is worth is
    # whatever the party overpaid. See `Drop.value` and `SHARD_*` below.
    ItemDef("rift_shard", "Núcleo condensado", "legendary", ("relics",), 1.0, 100,
            droppable=False),
)

BY_KEY: dict[str, ItemDef] = {item.key: item for item in ITEMS}
#: The roll pools, and they are built from what the world may PRODUCE rather
#: than from the catalog. A knife on the forest floor would be a second one
#: nobody has room for.
BY_RARITY: dict[str, tuple[ItemDef, ...]] = {
    rarity: tuple(item for item in ITEMS if item.rarity == rarity and item.droppable)
    for rarity in RARITIES
}

# What a scene is *about*, for the overlap test. `deadfall` is quiet woods;
# `sanctuary` is the one place somebody built rather than abandoned.
SCENE_TAGS: dict[str, tuple[str, ...]] = {
    "sanctuary": ("relics", "valuables", "nature"),
    "roadside": ("travel", "dropped", "living"),
    "convoy": ("travel", "supplies", "military"),
    "medevac": ("medical", "supplies", "electronics"),
    "checkpoint": ("military", "combat", "supplies"),
    "haulage": ("supplies", "tools", "scrap"),
    "busstop": ("travel", "living", "dropped"),
    "flight": ("living", "dropped", "travel", "valuables"),
    "last_stand": ("military", "combat", "scrap", "tools"),
    "dumpsite": ("scrap", "supplies", "tools", "abandoned"),
    "trailhead": ("travel", "dropped", "tools"),
    "deadfall": ("nature", "relics"),
    "boundary": ("travel", "mixed", "dropped"),
}

# How many items a scene of this kind SCATTERS on the ground, before anything
# inside its objects is counted. The landmark always pays; a deadfall almost
# never does.
#
# THESE ARE THE GROUND HALF OF A NIGHT'S BUDGET, and they went up with the map.
# The forest is roughly twice the area it was and carries about half again as
# many scenes, and the extraction quota (`rift.night_need`) is set against the
# total the two halves produce — so moving a number here without re-reading
# that one moves how many nights a party can survive.
SCENE_COUNTS: dict[str, tuple[float, int, int]] = {
    # (chance of at least one, min, max)
    "sanctuary": (1.0, 2, 3),
    "flight": (0.95, 1, 2),
    "medevac": (0.90, 1, 2),
    "checkpoint": (0.90, 1, 2),
    "dumpsite": (0.90, 1, 2),
    "convoy": (0.85, 1, 2),
    "haulage": (0.85, 1, 2),
    "last_stand": (0.85, 1, 2),
    "busstop": (0.80, 1, 2),
    "roadside": (0.70, 0, 2),
    "trailhead": (0.70, 0, 1),
    "boundary": (0.60, 0, 1),
    "deadfall": (0.25, 0, 1),
}

SEARCH_RADIUS = 4.0
MIN_SEPARATION = 1.2


#: THE CONDENSED CORE, and the three numbers that turn a value into an object.
#:
#: Overfeeding a rift is only worth doing if what comes back is CARRYABLE, and
#: carryable is a bag with a slot count and a weight bar. So the excess comes
#: out as ONE item in ONE slot — which is the win, four slots of loot becoming
#: one — and pays for that in kilos and in how much of the ground it covers.
#: A shard worth 300 is not a free ride to the next pad; it is most of your
#: walk speed.
#:
#: THE RATE IS DELIBERATELY WORSE THAN THE CATALOG'S. A crown carries 400
#: points in 1.8 kg and a ring carries 70 in 0.15 — call it 0.004 kg a point
#: across the good end of the table. Condensing runs at half again that, so
#: putting four slots through a rift and carrying the result costs real walk
#: speed: the win is the SLOTS, and it has to be paid for somewhere or
#: overfeeding is just free storage. Tried at 0.010 first and a big core was
#: 82% of max carry on its own, which is not a trade-off, it is a refusal.
SHARD_KEY = "rift_shard"
SHARD_KG_PER_VALUE = 0.006
#: Drawn size, as a multiplier on the sprite. Clamped at both ends: below the
#: floor a shard is a speck nobody finds in a blackout, above the ceiling it
#: stops reading as something you pick up.
SHARD_SCALE_SPAN = (0.8, 2.0)
SHARD_SCALE_FULL = 400.0


def shard_stats(value: int) -> tuple[int, float, float]:
    """`(value, kg, scale)` for a core condensed out of `value` overpaid."""
    worth = max(1, int(value))
    kg = round(worth * SHARD_KG_PER_VALUE, 2)
    low, high = SHARD_SCALE_SPAN
    scale = low + (high - low) * min(1.0, worth / SHARD_SCALE_FULL)
    return worth, kg, round(scale, 3)


@dataclass
class Drop:
    id: str
    key: str
    x: float
    y: float
    #: PER-DROP OVERRIDES, and the catalog is the default for all three.
    #:
    #: Every other item in the game is worth what its row says it is worth,
    #: which is why the catalog ships once in `welcome.config` and the wire
    #: carries a key. A condensed core breaks that on purpose: what it is worth
    #: is whatever was overpaid into the rift that made it, so those numbers
    #: have to travel WITH the object — through the ground, through the bag,
    #: and into the tooltip.
    value: int | None = None
    weight: float | None = None
    #: Sprite multiplier. Only ever set on a shard; everything else draws at 1.
    scale: float | None = None

    def to_payload(self) -> dict:
        row = {
            "id": self.id,
            "k": self.key,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
        }
        if self.value is not None:
            row["v"] = self.value
        if self.weight is not None:
            row["w"] = round(self.weight, 2)
        if self.scale is not None:
            row["s"] = round(self.scale, 3)
        return row


@dataclass
class LootPickup:
    drop_id: str
    player_id: str
    key: str
    x: float
    y: float
    #: Which bag or hotbar slot it landed in. The client flies the sprite there.
    slot: int
    #: `hotbar` for guns; omitted on the wire when it is the pocket.
    dest: str = "bag"

    def to_payload(self) -> dict:
        row = {
            "id": self.drop_id,
            "by": self.player_id,
            "k": self.key,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "slot": self.slot,
        }
        if self.dest != "bag":
            row["dest"] = self.dest
        return row


def catalog_payload() -> dict:
    """Item defs the client needs to draw a name, a rarity, a frame and a slot."""
    payload: dict[str, dict] = {}
    for index, item in enumerate(ITEMS):
        row = {
            "name": item.name,
            "rarity": item.rarity,
            "frame": index,
            "weight": item.weight,
            "value": item.value,
            "pocket": item.pocket,
        }
        # Omitted rather than nulled on the forty rows that are not rounds.
        if item.pocket == "ammo":
            row["ammo"] = item.ammo
            row["rounds"] = item.rounds
        payload[item.key] = row
    return payload


def from_payloads(rows: list[dict]) -> dict[str, Drop]:
    drops: dict[str, Drop] = {}
    for row in rows:
        value = row.get("v")
        weight = row.get("w")
        scale = row.get("s")
        drop = Drop(
            id=str(row["id"]),
            key=str(row["k"]),
            x=float(row["x"]),
            y=float(row["y"]),
            value=None if value is None else int(value),
            weight=None if weight is None else float(weight),
            scale=None if scale is None else float(scale),
        )
        if drop.key in BY_KEY:
            drops[drop.id] = drop
    return drops


def scatter(tiles: list[list[int]], scenes, rng: random.Random) -> list[Drop]:
    """Place loot next to the scenes that landed. `scenes` is PlacedScene rows."""
    drops: list[Drop] = []
    occupied: list[tuple[float, float]] = []
    next_id = 1
    for scene in scenes:
        kind = scene.kind
        chance, low, high = SCENE_COUNTS.get(kind, (0.4, 0, 1))
        if rng.random() > chance:
            continue
        count = rng.randint(low, high) if high > 0 else 0
        if count <= 0:
            continue
        weights = LANDMARK_WEIGHTS if kind == "homestead" else RARITY_WEIGHTS
        tags = SCENE_TAGS.get(kind, ())
        for _ in range(count):
            rarity = _roll_rarity(rng, weights)
            item = _pick_item(rng, rarity, tags)
            if item is None:
                continue
            pos = _find_floor(tiles, scene.x, scene.y, occupied, rng)
            if pos is None:
                continue
            tx, ty = pos
            occupied.append((tx, ty))
            drops.append(
                Drop(
                    id=f"l{next_id}",
                    key=item.key,
                    x=(tx + 0.5) * TILE_SIZE,
                    y=(ty + 0.5) * TILE_SIZE,
                )
            )
            next_id += 1
    return drops


DROP_RADIUS = 2.5
DROP_RADIUS_WIDE = 5.0
DROP_SEPARATION = 0.8


def place_near(
    tiles: list[list[int]],
    x: float,
    y: float,
    occupied: list[tuple[float, float]],
    rng: random.Random,
) -> tuple[float, float] | None:
    """A walkable world-pixel near `(x, y)`. `occupied` is tile coords."""
    cx = x / TILE_SIZE
    cy = y / TILE_SIZE
    for radius in (DROP_RADIUS, DROP_RADIUS_WIDE):
        tile = _find_floor(
            tiles, cx, cy, occupied, rng, radius=radius, min_sep=DROP_SEPARATION
        )
        if tile is not None:
            tx, ty = tile
            return ((tx + 0.5) * TILE_SIZE, (ty + 0.5) * TILE_SIZE)
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    tx = int(math.floor(cx))
    ty = int(math.floor(cy))
    if 0 <= ty < height and 0 <= tx < width and tiles[ty][tx] == FLOOR:
        return ((tx + 0.5) * TILE_SIZE, (ty + 0.5) * TILE_SIZE)
    return None


def free_tile_near(
    tiles: list[list[int]],
    cx: float,
    cy: float,
    occupied: list[tuple[float, float]],
    rng: random.Random,
    radius: float = SEARCH_RADIUS,
    min_sep: float = MIN_SEPARATION,
) -> tuple[int, int] | None:
    """A walkable tile near `(cx, cy)` in TILE coordinates, or None.

    The placement scan every scatter in the game shares. `ammo.py` runs a
    second pass over the same scenes this one does, and both have to agree
    about what "next to" means or the boxes end up in the treeline while the
    loot sits in the clearing.
    """
    return _find_floor(tiles, cx, cy, occupied, rng, radius=radius, min_sep=min_sep)


def roll_item(
    rng: random.Random,
    tags: tuple[str, ...] = (),
    weights: dict[str, float] | None = None,
) -> ItemDef | None:
    """One catalog roll, optionally biased.

    `tags` is what KIND of place this is — an ambulance leans medical, a
    shrine leans relic — and it weights the pick without ever forbidding
    anything, because a bandage in a totem pile is a better story than a
    lookup table. `weights` swaps the rarity curve itself, which is how a
    chest is worth more than a bin without either of them holding a
    different list of objects.
    """
    rarity = _roll_rarity(rng, weights or RARITY_WEIGHTS)
    return _pick_item(rng, rarity, tags)


def nearest(drops: dict[str, Drop], x: float, y: float, max_dist: float) -> Drop | None:
    best: Drop | None = None
    best_d2 = max_dist * max_dist
    for drop in drops.values():
        dx = drop.x - x
        dy = drop.y - y
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = drop
    return best


def _roll_rarity(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values())
    roll = rng.uniform(0, total)
    for rarity, weight in weights.items():
        roll -= weight
        if roll <= 0:
            return rarity
    return "common"


def _pick_item(rng: random.Random, rarity: str, tags: tuple[str, ...]) -> ItemDef | None:
    pool = BY_RARITY.get(rarity) or ()
    if not pool:
        return None
    if not tags:
        return rng.choice(pool)
    scored = []
    for item in pool:
        overlap = len(set(item.tags) & set(tags))
        scored.append((overlap + 1, item))
    # Weight by overlap so a tagged match is likelier, not mandatory.
    total = sum(score for score, _ in scored)
    roll = rng.uniform(0, total)
    for score, item in scored:
        roll -= score
        if roll <= 0:
            return item
    return scored[-1][1]


def _find_floor(
    tiles: list[list[int]],
    cx: float,
    cy: float,
    occupied: list[tuple[float, float]],
    rng: random.Random,
    radius: float = SEARCH_RADIUS,
    min_sep: float = MIN_SEPARATION,
) -> tuple[int, int] | None:
    height = len(tiles)
    width = len(tiles[0]) if tiles else 0
    candidates: list[tuple[int, int]] = []
    x0 = max(1, int(math.floor(cx - radius)))
    x1 = min(width - 1, int(math.ceil(cx + radius)))
    y0 = max(1, int(math.floor(cy - radius)))
    y1 = min(height - 1, int(math.ceil(cy + radius)))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if tiles[ty][tx] != FLOOR:
                continue
            if math.hypot(tx + 0.5 - cx, ty + 0.5 - cy) > radius:
                continue
            if any(math.hypot(tx - ox, ty - oy) < min_sep for ox, oy in occupied):
                continue
            candidates.append((tx, ty))
    if not candidates:
        return None
    return rng.choice(candidates)
