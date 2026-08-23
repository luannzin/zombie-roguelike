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

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from . import armor, weapons
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
    #: Where a collect puts it, and there are four answers because a player
    #: has four containers. `bag` is the pocket; `hotbar` is a weapon (a gun
    #: into a gun cell, a lâmina into the blade cell); `ammo` goes straight
    #: into the reserve for its calibre and takes no slot at all (`ammo.py`);
    #: `worn` goes ON the body (`armor.py`) and takes no slot either.
    #:
    #: Neither `ammo` nor `worn` costs a pocket cell, and for the same reason:
    #: the bag's budget answers "how much loot can I still carry out", and a
    #: round or a chestplate competing with a gold ring for a cell would make
    #: surviving a choice against extracting — which is a tax on playing
    #: rather than a trade-off. Armour still costs you SPEED, which is where
    #: the price of wearing it belongs.
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
    # WHAT THE ANOMALY GAVE BACK. Never scattered, never rolled, never in a
    # crate: the only thing that makes one is overfeeding a pad and then
    # closing it (`Room._drop_excess`). Its catalog `value` and `weight` are a
    # BASE — the real ones ride on the drop, because what it is worth is
    # whatever the party overpaid. See `Drop.value` and `SHARD_*` below.
    ItemDef("rift_shard", "Núcleo condensado", "legendary", ("relics",), 1.0, 100,
            droppable=False),
)

# --- the rows nobody types ---------------------------------------------------
#
# GUNS AND AMMUNITION ARE GENERATED FROM `weapons.py`, and that is a rule
# about where a number is allowed to live rather than a convenience. A gun's
# price, its weight and how many rounds a box of its calibre holds are all
# functions of the same ported CS2 stat block its damage comes from — so a
# hand-written row here would be a second opinion about a weapon that already
# has one, and the two would disagree the first time anything was rebalanced.
# That is exactly what happened to the price ladder before this existed.
#
# What is NOT derivable stays written down below: the Portuguese name, the
# tags, and the fact that none of it is droppable.

#: Everything a gun belongs to, for the tag-overlap roll it never takes part
#: in — the tags still decide which OBJECTS pay out its ammunition, which is
#: the only reason a `droppable=False` row carries any.
_ARMS_TAGS = ("military", "combat")

#: Catalog value -> rarity, which is the colour a weapon's name is drawn in
#: on a shop table and in the hotbar tooltip. Bands rather than a per-weapon
#: label, so the price ladder and the colour ladder cannot come apart: a gun
#: that got more expensive gets more expensive-looking in the same commit.
_GUN_RARITY_BANDS: tuple[tuple[int, str], ...] = (
    (60, "common"),
    (130, "uncommon"),
    (220, "rare"),
    (330, "epic"),
)


def _gun_rarity(value: int) -> str:
    for ceiling, rarity in _GUN_RARITY_BANDS:
        if value < ceiling:
            return rarity
    return "legendary"


#: Portuguese names for the boxes, per calibre. The only thing about a box
#: that is not arithmetic.
_AMMO_NAMES: dict[str, str] = {
    weapons.AMMO_PISTOL: "Munição de pistola",
    weapons.AMMO_SMG: "Munição de submetralhadora",
    weapons.AMMO_SHELL: "Cartuchos de calibre 12",
    weapons.AMMO_RIFLE: "Munição de rifle",
    weapons.AMMO_AWP: "Munição de precisão",
}

#: How heavy one box is. Sized off the round rather than the count, which is
#: why a box of shells outweighs a box of pistol rounds carrying four times
#: as many of them. It is charged to nothing — ammunition takes no pocket
#: slot — and exists only so the tooltip is not lying.
_AMMO_WEIGHTS: dict[str, float] = {
    weapons.AMMO_PISTOL: 0.4,
    weapons.AMMO_SMG: 0.5,
    weapons.AMMO_SHELL: 0.9,
    weapons.AMMO_RIFLE: 0.8,
    weapons.AMMO_AWP: 0.6,
}

#: Which rarity tier a box draws its name in. Not a drop table — these are
#: `droppable=False` and `ammo.scatter` is the only thing that places one —
#: just the colour that says "this is the good calibre" at a glance.
_AMMO_RARITY: dict[str, str] = {
    weapons.AMMO_PISTOL: "common",
    weapons.AMMO_SMG: "common",
    weapons.AMMO_SHELL: "uncommon",
    weapons.AMMO_RIFLE: "uncommon",
    weapons.AMMO_AWP: "rare",
}


#: Where a lâmina turns up. NOT the guns' tags: a blade is not ordnance, it
#: is a TOOL somebody was using when this place stopped being a place — an
#: axe at a deadfall, a machete in a shed, and the one imported thing in the
#: category behind glass in a cabin. That is why the pools differ, and it is
#: also why blades are found at all when firearms never are.
_BLADE_TAGS: dict[str, tuple[str, ...]] = {
    "axe": ("tools", "abandoned", "camp", "scrap"),
    "katana": ("relics", "valuables", "living"),
}


#: Where a piece of armour turns up, by MATERIAL rather than by slot: a
#: leather jacket and leather leggings came off the same person, and the
#: place that has one has the other. The ladder doubles as a map of the
#: world — rags at a camp, leather where people lived, plate among the
#: relics, and the one modern material in the game only where there were
#: soldiers.
_ARMOR_TAGS: dict[str, tuple[str, ...]] = {
    "cloth": ("camp", "abandoned", "scrap", "dropped"),
    "leather": ("living", "travel", "camp", "abandoned"),
    "steel": ("relics", "abandoned", "tools"),
    "kevlar": ("military", "combat"),
}


def _armor_rows() -> tuple[ItemDef, ...]:
    """Every wearable piece as a catalog row, derived from `armor.PIECES`.

    ARMOUR IS FOUND AND BOUGHT BOTH, which is the whole reason it is a good
    category to add to this game. A firearm can only be bought, because the
    merchant being the only source is what makes ammunition mean anything; a
    lâmina can be found, because steel eats nothing and a broke party needs a
    route to better steel. Armour is the first thing that is genuinely on
    BOTH ladders — you can walk out of a cabin wearing a leather jacket you
    did not pay for, or you can decide that this night's take is going on a
    helmet instead of on a rifle. That decision is the one the shop has
    always been missing.

    Nothing here is `droppable=False`: every piece can be rolled, and the
    rarity a roll has to clear is the MATERIAL's, so the ladder gates itself.
    """
    rows: list[ItemDef] = []
    for piece in armor.PIECES:
        rows.append(
            ItemDef(
                key=piece.key,
                name=piece.name,
                rarity=piece.rarity,
                tags=_ARMOR_TAGS[piece.material],
                weight=piece.weight,
                value=piece.value,
                pocket="worn",
            )
        )
    return tuple(rows)


def _blade_rows() -> tuple[ItemDef, ...]:
    """Every lâmina as a catalog row, derived from `weapons.BLADES`.

    LÂMINAS ARE FOUND, AND THAT IS THE ONE PLACE THIS CATEGORY PARTS COMPANY
    WITH THE GUNS. A firearm is `droppable=False` because the merchant being
    the only source is what makes calibre and ownership the same question —
    the forest stocks ammunition against what the party PAID for. None of that
    argument survives contact with a blade: steel eats nothing, so there is no
    economy to protect, and a run that opens on the knife with no money needs
    a route to better steel that does not go through a shop it cannot afford.
    A hatchet in a logging camp is also simply what is there.

    The knife is the exception inside the exception: it is `droppable=False`
    because everybody already has one, and a second knife on the forest floor
    would be a pickup that changes nothing. Its rarity is read off its value
    like every other blade's, which lands it on common — where the floor
    belongs.
    """
    rows: list[ItemDef] = []
    for profile in weapons.BLADES:
        value = weapons.blade_value(profile)
        rows.append(
            ItemDef(
                key=profile.key,
                name=profile.name,
                # Off the same bands the guns use, so the colour ladder and
                # the price ladder cannot come apart: a blade that got better
                # gets more expensive-looking in the same commit.
                rarity=_gun_rarity(value),
                tags=_BLADE_TAGS.get(profile.key, ("combat",)),
                weight=weapons.blade_weight(profile),
                value=value,
                pocket="hotbar",
                droppable=profile.key != weapons.STARTING_MELEE,
            )
        )
    return tuple(rows)


def _arms_rows() -> tuple[ItemDef, ...]:
    """Every ammunition-box row and every gun row.

    AMMUNITION FIRST, then the guns in catalog order. The order is for a
    reader rather than for the renderer: `tools/make_loot.py` writes a
    manifest keyed by ITEM KEY, so a sprite finds its row by name and the two
    lists may drift apart without anything on the ground turning into the
    wrong picture. What a missing entry there costs is a missing icon, not a
    scrambled sheet.
    """
    rows: list[ItemDef] = []
    for calibre in weapons.AMMO_TYPES:
        rows.append(
            ItemDef(
                key=f"ammo_{calibre}",
                name=_AMMO_NAMES[calibre],
                rarity=_AMMO_RARITY[calibre],
                tags=_ARMS_TAGS,
                weight=_AMMO_WEIGHTS[calibre],
                # ZERO, and deliberately: an extraction platform carries
                # CARGO, and a box of rounds is what you spent getting the
                # cargo, not the cargo. See `ammo.py`.
                value=0,
                pocket="ammo",
                ammo=calibre,
                rounds=weapons.BOX_ROUNDS[calibre],
                droppable=False,
            )
        )
    for gun in weapons.WEAPONS:
        if gun.melee is not None:
            continue
        rows.append(
            ItemDef(
                key=gun.key,
                name=gun.name,
                rarity=_gun_rarity(gun.value),
                tags=_ARMS_TAGS,
                weight=gun.weight,
                value=gun.value,
                pocket="hotbar",
                # NOT DROPPABLE, AND THAT IS THE WHOLE FIREARM ECONOMY. No
                # barrel, no boot, no shrine and no scene ever produces one:
                # the merchant is the only source, so a gun is something the
                # party DECIDED to buy with a night's extraction rather than
                # something the forest handed them. It also makes ammunition
                # mean something — a calibre nobody paid for is a calibre
                # nobody finds boxes of.
                droppable=False,
            )
        )
    return tuple(rows)


ITEMS = ITEMS + _armor_rows() + _blade_rows() + _arms_rows()

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
    # A DEN'S LOOT IS ITS VICTIMS' POCKETS. Nothing was stored here and
    # nothing was left as an offering — what is on this floor is what people
    # were carrying when they were dragged in, which is why the tags are the
    # walking-around ones and not a single military or supply row.
    "den": ("dropped", "living", "valuables", "travel"),
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
    # THE SECOND-BEST SCATTER IN THE GAME, and it always pays, because the
    # bargain has to be worth the animal. The shrine keeps the top of the
    # ladder: its bargain is stated in props from across a clearing and taken
    # by walking in, and it is the place a run is routed toward. A den is a
    # thing you walk PAST — the loot has to be enough that stopping is a
    # decision, and not so much that declining it feels like a loss.
    "den": (1.0, 2, 2),
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
    #: WHAT IS LEFT OF IT. Only ever set on a piece of armour that has been
    #: worn — a cracked steel plate taken off to put a fresh cloth one on has
    #: to still be cracked when somebody picks it back up, or "is this
    #: actually an upgrade" becomes a question the world quietly answers yes
    #: to every time. A piece that has never been worn leaves this None and
    #: arrives whole.
    hp: int | None = None

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
        if self.hp is not None:
            row["hp"] = self.hp
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
    #: `hotbar` for a weapon, `ammo` for a crate-load, `worn` for a piece of
    #: armour. Omitted on the wire when it is the pocket, which is most of
    #: the time.
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


#: THE ATLAS IS THE AUTHORITY ON ITS OWN FRAME ORDER, and this is the only
#: place that reads it.
#:
#: A frame used to be the catalog POSITION, which was right by coincidence and
#: stopped being right the moment anything was appended above the generated
#: rows: `tools/make_loot.py` keys its manifest by item KEY and paints in its
#: own order, so the knife and the condensed core landed on frames 40 and 41 —
#: a box of pistol rounds and a box of rifle rounds — and every gun under them
#: drew a different weapon. Two lists cannot both own an ordering; the one
#: that produced the pixels owns it.
_ATLAS = json.loads(
    (Path(__file__).resolve().parents[2] / "assets/processed/loot/manifest.json").read_text()
)
_FRAMES: dict[str, int] = {key: row["frame"] for key, row in _ATLAS["items"].items()}
#: One past the end of the sheet, so a key the generator has no art for draws
#: NOTHING rather than somebody else's picture. `tests/test_loot_frames.py` is
#: what stops that being a surprise.
_NO_FRAME: int = int(_ATLAS["frames"])


def catalog_payload() -> dict:
    """Item defs the client needs to draw a name, a rarity, a frame and a slot."""
    payload: dict[str, dict] = {}
    for item in ITEMS:
        row = {
            "name": item.name,
            "rarity": item.rarity,
            "frame": _FRAMES.get(item.key, _NO_FRAME),
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
