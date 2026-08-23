"""Armour: what a player WEARS, what it stops, and how it comes apart.

The fourth container. A player already had three — the pocket
(`inventory.py`, valuables and weight), the belt (`weapons.Hotbar`, what is
in the hand) and the reserve (`ammo.py`, rounds by calibre) — and worn gear
is none of them. It takes no bag slot, because a chestplate you are wearing
is not loot you are carrying out; it is not on the belt, because you do not
select it; and it is not a multiplier, because it BREAKS.

THE ZOMBIE'S CLAW IS THE UNIT, EXACTLY AS ITS HEALTH IS THE UNIT FOR GUNS
=========================================================================
`weapons.py` anchors every firearm on what a zombie can survive. This file
anchors every plate on what a zombie can do: one claw, `ZOMBIE.damage`, read
off the same stat block. Everything below is a function of it plus three
tables — the MATERIALS, the SLOTS and one exponent — and there is not a
hand-picked durability number anywhere.

  * ARMOUR is what the material is: a FLAT number of damage points taken off
    every blow that lands on the part it covers. Four tiers, each a quarter
    of the ceiling.
  * DURABILITY is what the material is, again: a piece survives
    `HITS_BASE * tier` blows LANDING ON IT before it comes apart, so the
    number on the HUD is honest in the only unit the player has.
  * COVERAGE is what the SLOT is, and it decides nothing except where a
    blow lands. It is taken off the player sprite's own anatomy — see
    `COVERAGE` — so the part of the body the art spends the most pixels on
    is the part that gets hit.

WHY A ROLL AND NOT A SUM
Every worn piece could soak its coverage-weighted share of every blow. That
is smoother, and it is worse: the pieces would then wear at exactly the rate
that makes a whole set fail at the same moment, and a set that fails all at
once is a stat that went away rather than an event. One blow lands on one
part. The chest goes first because the chest is hit most, and it goes in the
middle of a fight, and the player finds out by looking at the same three
numbers they have been ignoring all night.

FLAT, NOT A PERCENTAGE, AND THAT IS A DECISION ABOUT WHAT THE PLAYER READS
This started as a fraction — steel took 56% of a blow — which is a clean rule
and an unreadable stat. A percentage cannot be put on a card without naming
the blow it is a percentage OF, and the moment the card names one ("a walker
hits for 9, five of it stops here") the whole stat block is anchored on one
creature and starts lying the day there is a second one. There is no honest
way to print a proportional mitigation as a number.

A flat value has no such problem: `ARMADURA 5` means five, against anything
that ever gets added to this game. And the shape it gives the category is the
better one anyway — armour is now STRONG against a crowd of small hits and
WEAK against one big one, so plate is what you wear for the forest and not
what saves you from the Sawyer's bar. A proportional mitigation is equally
good against everything, which is another way of saying it never makes a
decision interesting.

WHAT IT IS NOT
Not persisted — nothing in this game is. Not a `Mods` field: `Mods.armor` is
TOUGHNESS, a multiplier a skill buys and nothing takes away, and this is
GEAR, an object with a number on it that ends at zero. They multiply in that
order in `Room.damage_player`, and the order is the argument: steel stops
part of the blow, and what gets through is what the body has to be tough
about.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .enemies import ZOMBIE

#: The three places a blow can land, in the order the HUD reads them: top
#: to bottom, the way you look at a person.
SLOT_HEAD = "head"
SLOT_BODY = "body"
SLOT_LEGS = "legs"
SLOTS: tuple[str, ...] = (SLOT_HEAD, SLOT_BODY, SLOT_LEGS)

#: WHERE A BLOW LANDS, and it is the player sprite's own anatomy rather than
#: a table of what feels fair.
#:
#: The processed player sheet spends its fifteen occupied rows like this:
#: head 1-8, torso 9-12, legs 13-15 — eight, four and three. That is S17's
#: proportion, a head over half the person, and it is what makes sixteen
#: pixels read as a character rather than as a small adult.
#:
#: So the helmet answers more blows than the other two put together, and that
#: is not a balance decision anybody made — it is what the silhouette says. A
#: player aiming at this sprite is aiming mostly at a head, and armour that did
#: not agree with the picture would be a rule the game never shows you. It also
#: gives the three slots genuinely different jobs: the helmet is the one worth
#: finding, and it is the one that wears out first.
#: EIGHT, FOUR AND THREE OF FIFTEEN, and they sum to exactly one — which is
#: not decoration, it is the check. This table was 7/4/3 for a while: fourteen
#: fifteenths, so `_roll_slot` normalised by the total and every share the HUD
#: printed was a fifteenth too small. Nothing at runtime notices a probability
#: table that does not sum, which is why `_check_coverage` fails the import
#: instead.
COVERAGE: dict[str, float] = {
    SLOT_HEAD: 8 / 15,
    SLOT_BODY: 4 / 15,
    SLOT_LEGS: 3 / 15,
}


def _check_coverage() -> None:
    """The parts have to add up to a body. Run at import."""
    total = sum(COVERAGE.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"COVERAGE sums to {total}, not 1 — every share the HUD prints "
            f"would be off, and `_roll_slot` would silently renormalise"
        )


_check_coverage()

#: Portuguese for the slot, for a HUD row and a tooltip line.
SLOT_NAMES: dict[str, str] = {
    SLOT_HEAD: "Cabeça",
    SLOT_BODY: "Tronco",
    SLOT_LEGS: "Pernas",
}

# --- the ladder --------------------------------------------------------------

#: What one claw is worth. Read off the stat block rather than typed, so
#: making the walker hit harder re-sizes every plate in the game in the same
#: motion — the same contract `weapons.ZOMBIE_HP` has.
CLAW = ZOMBIE.damage

#: What the TOP of the ladder takes off a blow, as a share of one claw.
#:
#: The claw is the sizing anchor and it stays one — `weapons.py` sizes guns
#: against the walker's health and this sizes plate against its hit, on the
#: same argument that the weakest creature is the only honest unit. What
#: changed is that it is a share of a claw HERE, once, at build time: what
#: comes out the other side is a flat number of damage points, and nothing
#: downstream — not the wire, not the HUD, not a tooltip — ever has to
#: mention a zombie to explain it.
#:
#: Deliberately short of the whole claw. A set that reduced a walker's hit to
#: nothing would end the night's tension for as long as it lasted, and the
#: thing in this game that stops a blow COMPLETELY is the shield, which you
#: have to be holding, facing the right way, in place of a gun.
CEILING_SHARE = 0.75

#: How many blows a TIER-ONE piece survives. Multiplied by the tier, so the
#: ladder is 4 / 8 / 12 / 16 hits taken on that part.
#:
#: Four is short on purpose. Cloth is meant to be the thing you are relieved
#: to find on night one and have forgotten about by night three, not a
#: permanent twenty percent. A piece that outlived the run it was found in
#: would make the whole category a stat rather than a supply.
HITS_BASE = 4

#: kg per tier, per piece. A full set is `KG_BASE * tier * 3`.
#:
#: NOT scaled by coverage, even though it is tempting: coverage is how much
#: of the SPRITE a slot is, and on this sprite that would make a helmet
#: heavier than a chestplate, which is the one place the derivation would
#: have produced a number the player can see is wrong. Weight belongs to the
#: material for the same reason durability does — material sets the numbers,
#: slot sets where the hits land, and the rule holds all the way across.
#:
#: WORN ARMOUR IS ON THE WALK, NOT IN THE BAG. It never touches `inv.w` —
#: that budget answers "how much loot can I still carry out" and a helmet is
#: not cargo — but it is absolutely on `Player.carry_weight`, because the
#: thing steel costs you is speed. A full set of the top material is over the
#: soft carry threshold on its own, which is the trade the category is FOR:
#: you are slower, and you were going to die at that corner anyway.
KG_BASE = 0.3

#: What a point of absorbed damage is worth on the loot catalog, and the
#: exponent that stops the ladder being linear.
#:
#: Linear pricing would say a kevlar plate is fifteen cloth ones, and nobody
#: values it that way: the difference between a fifth of a blow and three
#: quarters of it is the difference between dying at that corner and not. The
#: curve is the same shape `weapons.BLADE_VALUE_CURVE` puts on steel and for
#: the same reason.
VALUE_CURVE = 1.35


@dataclass(frozen=True)
class Material:
    """One rung of the ladder. Four columns and nothing else."""

    key: str
    #: Portuguese, as it appears in the item's name.
    name: str
    #: 1..4. The ONE number: soak, durability, weight and price are all
    #: functions of it.
    tier: int
    #: The colour the name is drawn in. Set by MATERIAL rather than derived
    #: from price, unlike the guns — a player learns "green is leather" in
    #: one pickup and then never has to read the number again, and the whole
    #: point of a material ladder is that the material is the information.
    rarity: str


MATERIALS: tuple[Material, ...] = (
    Material("cloth", "pano", 1, "common"),
    Material("leather", "couro", 2, "uncommon"),
    Material("steel", "aço", 3, "rare"),
    Material("kevlar", "kevlar", 4, "epic"),
)

MATERIAL_BY_KEY: dict[str, Material] = {m.key: m for m in MATERIALS}
TIERS = len(MATERIALS)


def armor_of(tier: int) -> int:
    """DAMAGE POINTS this material takes off every blow that lands on it.

    A quarter of the ceiling per rung. Even steps because the player counts
    in rungs: "one better" has to mean the same thing everywhere on the
    ladder or the middle of it is dead weight.

    The number that comes out is what the HUD prints and what
    `Room.damage_player` subtracts — one value, no conversion, nothing to
    resolve against an example. That is the whole reason this is not a
    fraction.
    """
    return max(1, round(CLAW * CEILING_SHARE * tier / TIERS))


def hp_of(tier: int) -> int:
    """Points of damage this piece will absorb before it comes apart.

    Durability is measured in what it STOPS rather than in blows, because
    that is the only unit that stays honest when something other than a
    walker hits you: a plate meeting the Sawyer's bar spends its whole
    allowance in a few swings and the bar on the HUD says so without being
    told about him. `HITS_BASE * tier` blows-on-this-part is what sizes it,
    and because the take is flat that arithmetic is exact — a tier-3 plate
    stops 5 a hit and holds 60, which is twelve hits, and twelve is what the
    table says.
    """
    return max(1, HITS_BASE * tier * armor_of(tier))


def weight_of(tier: int) -> float:
    """Kilos on the WALK. See `KG_BASE`."""
    return round(KG_BASE * tier, 2)


def value_from_hp(points: int) -> int:
    """What something that stops `points` of damage is worth.

    THE ONE PRICE FUNCTION FOR EVERYTHING THAT STOPS A BLOW, plates and the
    shield alike. A shield is armour you hold rather than wear, and pricing
    it off a second curve would be the same mistake `store.price_of` exists
    to avoid — two opinions about one question, drifting apart the first time
    either is rebalanced.

    It prices what a thing will absorb OVER ITS LIFE, which is why it takes
    durability rather than the per-blow rating: two plates that take the same
    five off a hit are not worth the same if one of them survives three times
    as many.
    """
    floor = hp_of(1)
    if floor <= 0 or points <= 0:
        return 1
    return max(1, round(floor * (points / floor) ** VALUE_CURVE))


def value_of(tier: int) -> int:
    """What one plate is worth on the loot catalog. See `VALUE_CURVE`."""
    return value_from_hp(hp_of(tier))


# --- the shield --------------------------------------------------------------
#
# THE THING THAT STOPS A BLOW OUTRIGHT. Every plate above is attrition — it
# takes a share and lets the rest through — and this is the one piece of gear
# in the game that answers a blow with nothing at all. Everything about how it
# is carried is the price of that: it eats a GUN CELL rather than a worn slot,
# it only works in the direction you are pointing it, it only works while you
# are holding the button, and it slows you while you do.
#
# It lives here rather than in `weapons.py` because what it IS is armour. What
# `weapons.py` owns is the fact that you select it off the belt.

#: How many walker claws the shield eats before it comes apart.
#:
#: Fourteen, against a plate's four-to-sixteen, and the comparison is the
#: point: a shield does not last longer than the best armour in the game, it
#: works completely for as long as it lasts. That is a different promise, and
#: a player who has one learns quickly that it is a resource to spend at a
#: doorway rather than a wall to live behind.
#:
#: It is also the one thing in the game that is still good against a BIG hit,
#: now that plate is flat: armour takes five off the Sawyer's thirty-four and
#: a shield takes all of it. Two answers to two different problems, which is
#: what stops the shield being a plate you have to hold.
SHIELD_HITS = 14

#: How wide the protected arc is, in degrees, centred on the aim.
#:
#: A hundred and forty: generous enough that "point it at them" is the whole
#: skill, narrow enough that being flanked is a real thing that happens to
#: somebody hiding behind one. A shield with no back is what makes a second
#: player worth having.
SHIELD_ARC_DEGREES = 140.0

#: What the walk is multiplied by while the shield is up. Slower than a full
#: kevlar set costs, and unlike the set it is a choice you make per moment
#: rather than per night — which is what makes raising it a decision instead
#: of a posture.
SHIELD_SPEED = 0.55


def shield_hp() -> int:
    """Points of damage a fresh shield eats before it breaks."""
    return SHIELD_HITS * CLAW


def shield_value() -> int:
    """What one is worth. Same curve as a plate — see `value_from_hp`."""
    return value_from_hp(shield_hp())


def shield_weight() -> float:
    """Kilos IN THE HAND. Twice the top plate, and it is carried in front of you."""
    return round(KG_BASE * TIERS * 2, 2)


def fresh_shield(key: str, hp: int | None = None) -> "Piece":
    """A shield's durability, whole or carried over from a previous owner."""
    full = shield_hp()
    return Piece(key=key, hp=full if hp is None else max(1, min(hp, full)), max_hp=full)


@dataclass(frozen=True)
class ArmorDef:
    """One wearable piece: a slot and a material, and nothing else.

    MATERIAL SETS THE NUMBERS, SLOT SETS WHERE THE HITS LAND. That split is
    what keeps twelve rows readable — a player who has learnt what leather
    does has learnt it for all three slots, and the only question left about
    a piece is whether they are already wearing something better THERE.
    """

    key: str
    name: str
    slot: str
    material: str

    @property
    def tier(self) -> int:
        return MATERIAL_BY_KEY[self.material].tier

    @property
    def armor(self) -> int:
        """Damage taken off every blow that lands on this part."""
        return armor_of(self.tier)

    @property
    def max_hp(self) -> int:
        return hp_of(self.tier)

    @property
    def weight(self) -> float:
        return weight_of(self.tier)

    @property
    def value(self) -> int:
        return value_of(self.tier)

    @property
    def rarity(self) -> str:
        return MATERIAL_BY_KEY[self.material].rarity

    @property
    def sheet(self) -> str:
        """The overlay sheet the client draws on the body.

        One sheet per piece, registered to the player's own 16x16 grid and
        drawn by the same `blitGear` that already draws the backpack and a
        zombie's hat. Armour is VISIBLE and it is visible through the system
        that was already there — a second way to put something on a body
        would be a second thing to keep in step with the walk cycle.
        """
        return f"armor-{self.slot}-{self.material}"

    def client_payload(self) -> dict:
        return {
            "name": self.name,
            "slot": self.slot,
            "material": self.material,
            # The material's own NAME, and it ships rather than being mapped
            # client-side. It is a catalog string like every other one on the
            # wire (`name`, `SLOT_NAMES`), and a second table of Portuguese in
            # the HUD is a second place for "steel" to leak out of when
            # somebody adds a rung.
            "materialName": MATERIAL_BY_KEY[self.material].name,
            "tier": self.tier,
            "armor": self.armor,
            "maxHp": self.max_hp,
            "weight": self.weight,
            "value": self.value,
            "rarity": self.rarity,
            "sheet": self.sheet,
        }


#: What each piece is CALLED, per slot, per material. The one table here that
#: is not arithmetic — a helmet of cloth is a hood and a helmet of kevlar is
#: not, and no formula knows that.
_NAMES: dict[str, dict[str, str]] = {
    SLOT_HEAD: {
        "cloth": "Capuz de pano",
        "leather": "Capacete de couro",
        "steel": "Elmo de aço",
        "kevlar": "Capacete tático",
    },
    SLOT_BODY: {
        "cloth": "Colete de pano",
        "leather": "Jaqueta de couro",
        "steel": "Peitoral de aço",
        "kevlar": "Colete balístico",
    },
    SLOT_LEGS: {
        "cloth": "Perneiras de pano",
        "leather": "Perneiras de couro",
        "steel": "Grevas de aço",
        "kevlar": "Calças táticas",
    },
}


def _catalog() -> tuple[ArmorDef, ...]:
    """Twelve rows, slot-major: every head, then every torso, then every leg.

    Slot-major rather than material-major because that is the order the
    generator paints them in and the order the HUD stacks them, and a list
    whose order means the same thing in three places is a list nobody has to
    re-sort.
    """
    rows: list[ArmorDef] = []
    for slot in SLOTS:
        for material in MATERIALS:
            rows.append(
                ArmorDef(
                    key=f"{slot}_{material.key}",
                    name=_NAMES[slot][material.key],
                    slot=slot,
                    material=material.key,
                )
            )
    return tuple(rows)


PIECES: tuple[ArmorDef, ...] = _catalog()
BY_KEY: dict[str, ArmorDef] = {piece.key: piece for piece in PIECES}


def catalog_payload() -> dict:
    """Every piece the client has to be able to name, draw and price."""
    return {piece.key: piece.client_payload() for piece in PIECES}


def is_armor(key: str | None) -> bool:
    return key is not None and key in BY_KEY


# --- what a body is wearing --------------------------------------------------


@dataclass
class Piece:
    """One thing with a durability on it: a worn plate, or the shield.

    IT CARRIES ITS OWN CEILING rather than looking one up, and that is what
    lets the same type hold a helmet and a riot shield. A shield's numbers
    live on `weapons.ShieldDef` because a shield is selected off the belt,
    and a plate's live on `ArmorDef` because a plate is worn — a `Piece` that
    resolved its own catalog row would have to know which of the two it was,
    which is exactly the branch this type exists to not have.
    """

    key: str
    hp: int
    max_hp: int

    @property
    def spent(self) -> bool:
        return self.hp <= 0

    def take(self, amount: int) -> int:
        """Absorb up to `amount`. Returns what it actually took."""
        soaked = max(0, min(amount, self.hp))
        self.hp -= soaked
        return soaked

    def to_payload(self) -> dict:
        # `max` rides along rather than being looked up: the HUD draws a bar,
        # and a bar that had to resolve a catalog row to know its own ceiling
        # is one more thing that can be undefined for a frame.
        return {"k": self.key, "hp": self.hp, "max": self.max_hp}


#: Where a blow lands, when nothing decides otherwise. Module-level so the
#: whole room shares one stream — `Room.damage_player` is the only caller and
#: it is not predicted client-side, so this never has to be reproducible.
_RNG = random.Random()


@dataclass
class Loadout:
    """What one player is wearing. Three slots, any of them empty.

    NOTHING HERE STACKS AND NOTHING HERE IS OPTIONAL-BUT-BETTER. One piece
    per slot, and putting a piece on takes off whatever was there — the
    replaced piece goes on the floor with however much life it had left,
    which is what makes "is this actually an upgrade" a question worth
    asking with a cracked steel plate on your chest and a fresh cloth one in
    front of you.
    """

    worn: dict[str, Piece] = field(default_factory=dict)

    def get(self, slot: str) -> Piece | None:
        return self.worn.get(slot)

    def holds(self, key: str) -> bool:
        piece = BY_KEY.get(key)
        return piece is not None and self.worn.get(piece.slot) is not None

    def equip(self, key: str, hp: int | None = None) -> Piece | None:
        """Wear `key`. Returns the piece it displaced, or None.

        `hp` carries a used piece's remaining life through a swap; a fresh
        one out of the shop or off the ground passes None and arrives whole.
        """
        definition = BY_KEY.get(key)
        if definition is None:
            return None
        old = self.worn.get(definition.slot)
        life = definition.max_hp if hp is None else max(1, min(hp, definition.max_hp))
        self.worn[definition.slot] = Piece(key=key, hp=life, max_hp=definition.max_hp)
        return old

    def destroy(self, slot: str) -> Piece | None:
        return self.worn.pop(slot, None)

    @property
    def weight(self) -> float:
        """Kilos of worn steel. On the WALK, never in the bag."""
        return round(sum(BY_KEY[p.key].weight for p in self.worn.values()), 2)

    def absorb(self, amount: int) -> tuple[int, str, str | None, bool]:
        """Take one blow. Returns `(through, slot hit, piece key or None, broke)`.

        ONE BLOW LANDS ON ONE PART, rolled against `COVERAGE`. A bare part is
        a bare part: the roll happens whether or not there is anything there,
        so a player in a helmet and nothing else is not quietly wearing a
        helmet on their legs. That is also what makes a partial set feel like
        a partial set — it works most of the time, and the times it does not
        are the ones you remember.

        The KEY comes back rather than only the slot, because a piece that
        broke is already out of `worn` by the time the caller looks — and the
        one event this whole system exists to produce is "your chestplate is
        gone", which needs to be able to name it.

        A piece that breaks still SOAKS the blow that broke it: the last
        thing a chestplate does is its job.
        """
        return self.absorb_at(_roll_slot(), amount)

    def absorb_at(self, slot: str, amount: int) -> tuple[int, str, str | None, bool]:
        """`absorb`, with the roll already made. Same return.

        Split out because WHERE a blow lands and WHAT THE PLATE THERE DOES
        ABOUT IT are two different rules, and only the first one is random.
        Keeping them together made the second untestable: a test that wanted
        to know how many claws a cloth vest survives had to roll until it got
        the chest, four times in a row, or measure it through the noise.
        """
        piece = self.worn.get(slot)
        if piece is None:
            return amount, slot, None, False
        # FLAT, capped by the blow and by what is left of the plate. A hit
        # smaller than the plate's rating is stopped entirely and costs the
        # plate only what it actually absorbed — small hits wear armour
        # slowly, which is the right way round and falls out of the model
        # rather than being a rule on top of it.
        soaked = piece.take(min(amount, BY_KEY[piece.key].armor))
        broke = piece.spent
        if broke:
            self.destroy(slot)
        return amount - soaked, slot, piece.key, broke

    def to_payload(self) -> dict:
        """Worn slots only. An empty slot is an absent key, not a null."""
        return {slot: piece.to_payload() for slot, piece in self.worn.items()}


def _roll_slot() -> str:
    """A part of the body, weighted by how much of the sprite it is."""
    roll = _RNG.random() * sum(COVERAGE[slot] for slot in SLOTS)
    for slot in SLOTS:
        roll -= COVERAGE[slot]
        if roll <= 0:
            return slot
    return SLOT_BODY


def from_payload(row: dict | None) -> Loadout:
    """Rebuild a loadout off the wire. Unknown keys are dropped, not guessed."""
    worn: dict[str, Piece] = {}
    for slot, cell in (row or {}).items():
        if not isinstance(cell, dict):
            continue
        key = cell.get("k")
        definition = BY_KEY.get(key) if isinstance(key, str) else None
        if definition is None or definition.slot != slot:
            continue
        hp = cell.get("hp")
        worn[slot] = Piece(
            key=definition.key,
            hp=max(1, min(int(hp), definition.max_hp)) if isinstance(hp, int) else definition.max_hp,
            max_hp=definition.max_hp,
        )
    return Loadout(worn=worn)
