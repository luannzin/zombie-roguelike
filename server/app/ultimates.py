"""ULTIMATES: what a weapon does when the armour agrees with it.

A weapon is a rate of damage. Armour is a rate of damage taken. Both are
dials, both are bought with the same gold, and a party's whole build decision
was therefore "buy the biggest number you can afford" — twice. Nothing about
what you were WEARING ever changed what you could DO.

This is the join. Every weapon owns exactly one ultimate; the ultimate is
locked until the body wearing that weapon also carries the right SET. So the
minigun's answer to a crowd exists only for somebody dressed in riot plate,
and the katana's exists only for somebody who gave up plate to move. Two
players holding identical weapons are different characters because of what
they put on.

THE THREE RULES THIS FILE EXISTS TO KEEP
========================================

1. NOTHING HERE NAMES A COMBINATION. There is no `if weapon == "minigun" and
   armor == "steel"`. A weapon carries TAGS, a material carries TAGS
   (`armor.Material.tags`), and an ultimate lists the tags it needs. Adding a
   fifth ultimate is a row in `ULTIMATES`; adding a second weapon that can
   satisfy an existing one is a tag on that weapon's row. `Room` never learns
   a weapon's name and neither does the HUD.

2. THE CHARGE IS EARNED WITH THE WEAPON THE ULTIMATE BELONGS TO, and it is
   kept PER ULTIMATE. Your katana's bar does not fill while you are shooting
   the Deagle, and switching to the Deagle does not spend it. That is what
   makes the belt a set of separate promises rather than one meter with
   different skins on it — and it is why the HUD panel changes with the
   weapon in hand rather than tracking one global number.

3. THERE IS NO COOLDOWN TIMER, AND THAT IS DELIBERATE. Firing spends the
   whole bar and the bar refills by playing. A timer on top would be a second
   clock saying the same thing as the first, and worse: a cooldown is a
   promise the game will give it back for free, which is exactly the
   "arbitrary ability button" this system is meant not to be. What you get
   back is what you go and earn.

WHAT AN ULTIMATE MAY BE
=======================
Three effect BLOCKS, and a row carries exactly one — the same shape
`weapons.WeaponDef` already uses for `melee` and `shield`, and for the same
reason: `Room` dispatches on which block is present, never on the key, so a
fourth ultimate that throws something is a `Volley` row and no new code.

    Volley    things leave the body and fly. Slow enough to be seen, passing
              through bodies and billing each once (`projectiles.py`).
    Empower   a WINDOW in which the weapon in hand is a different weapon:
              faster, harder, or free to fire. Optionally budgeted in SHOTS
              rather than in seconds, which is what makes a single enormous
              round a legal member of the same family as a six-second
              suppression.
    Aura      one pulse centred on the body. Heals, or hurts, or both.

WHAT IT IS NOT
==============
Not a skill. `skills.py` is what a run BOUGHT and it is permanent and
invisible; this is what the loadout in your hands right now can do, and it
goes away the moment you put the weapon down. Not persisted, like everything
else here. And not a damage number: an ultimate that was only "the same shot
but bigger" would be a stat, and a stat does not make anybody rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import armor

# --- what a tag IS -----------------------------------------------------------
#
# THE ONE VOCABULARY BOTH SIDES SPEAK. A weapon's tags and a material's tags
# live on their own catalogs — this is only the dictionary that says what each
# word means and which kind of thing can say it, so the HUD can draw a
# requirement row without a table of Portuguese of its own.
#
# `source` is not decoration. An ARMOUR tag is satisfied by wearing enough of
# a set and a WEAPON tag is satisfied by holding one thing, so the HUD draws
# the first as progress ("2/3") and the second as a plain tick — and a
# requirement the player cannot meet says which of the two it is asking for.

SOURCE_WEAPON = "weapon"
SOURCE_ARMOR = "armor"


@dataclass(frozen=True)
class TagDef:
    key: str
    #: Portuguese, for the requirement row. For an armour tag this is the SET
    #: name rather than the material's, because "Conjunto Sombra" is what the
    #: player is being asked to go and get and `couro` is only what it is made
    #: of.
    name: str
    source: str


TAGS: tuple[TagDef, ...] = (
    # --- what a weapon is ---------------------------------------------------
    TagDef("ballistic", "Arma de fogo", SOURCE_WEAPON),
    TagDef("automatic", "Automática", SOURCE_WEAPON),
    TagDef("precision", "Precisão", SOURCE_WEAPON),
    TagDef("blade", "Lâmina", SOURCE_WEAPON),
    TagDef("swift", "Ágil", SOURCE_WEAPON),
    TagDef("bulk", "Pesada", SOURCE_WEAPON),
    TagDef("support", "Suporte", SOURCE_WEAPON),
    # --- what a body is wearing ---------------------------------------------
    # These four are `armor.MATERIALS`' own tags, one per rung, which is what
    # makes the ladder a set of IDENTITIES rather than a set of numbers: the
    # best plate in the game carries exactly one of them, so wearing it locks
    # three ultimates as surely as it unlocks the fourth.
    TagDef("medic", "Conjunto Campo", SOURCE_ARMOR),
    TagDef("ninja", "Conjunto Sombra", SOURCE_ARMOR),
    TagDef("riot", "Conjunto Muralha", SOURCE_ARMOR),
    TagDef("tactical", "Conjunto Tático", SOURCE_ARMOR),
    # The weight class, shared by two rungs each. Nothing requires one today;
    # it exists so a future ultimate can ask for "anything light" without
    # naming a rung, and still be asking for the same thing when there is a
    # fifth material.
    TagDef("light", "Armadura leve", SOURCE_ARMOR),
    TagDef("heavy", "Armadura pesada", SOURCE_ARMOR),
)

TAG_BY_KEY: dict[str, TagDef] = {tag.key: tag for tag in TAGS}

#: HOW MUCH OF A SET COUNTS AS WEARING IT. Three of the five slots — a
#: majority of the body.
#:
#: COUNTED IN PIECES AND NOT IN COVERAGE, which is the one judgement call in
#: this whole file. Coverage is the more elegant sum and it is wrong here: the
#: head is over half of this sprite, so a coverage rule would make ONE LEATHER
#: CAP into a full ninja set. Pieces are what the player watches themselves
#: collect, what the mannequin draws, and what a HUD row can print as "2/3".
SET_PIECES = 3


# --- what builds the bar -----------------------------------------------------
#
# THE SOURCE IS PART OF THE ULTIMATE'S IDENTITY, not a global rule. A gunner
# charges by dealing damage, a medic charges by healing, and neither of them
# can charge by doing the other's job — which is what stops the support build
# from being "carry the healer and play normally".

#: Points of damage this weapon dealt to anything.
CHARGE_DAMAGE = "damage"
#: Points of health this weapon put back into somebody.
CHARGE_HEAL = "heal"
#: Bodies this weapon put down. Counted in KILLS, so one unit is one corpse.
CHARGE_KILL = "kill"


# --- what an ultimate does ---------------------------------------------------


@dataclass(frozen=True)
class Volley:
    """Things that leave the body and fly.

    Runs on `projectiles.py`, which means it inherits the two rules that
    module exists for: it is slow enough to walk out of, and it passes THROUGH
    a crowd billing each body once. Both matter here — an ultimate that
    stopped on the first zombie would be a very expensive way to kill one
    zombie, and one that arrived instantly would be a bigger bullet.
    """

    #: How many leave at once. One is a single enormous thing; several laid
    #: across `spread_degrees` is a fan.
    count: int
    spread_degrees: float
    damage: int
    #: Tiles per second. Under the player's own walk on anything meant to be
    #: dodgeable; well over it on something meant to be a strike.
    speed_tiles: float
    life: float
    #: Half-width of what it sweeps, in tiles. This is the number that makes a
    #: crescent a crescent rather than a bullet.
    radius_tiles: float
    #: Which sprite the client draws for it. Presentation stays with the
    #: caller — see `projectiles.py`'s header — so this string is the whole of
    #: what the wire says about how it looks.
    look: str = "slash"


@dataclass(frozen=True)
class Empower:
    """A window in which the weapon in hand is a different weapon.

    BUDGETED IN SECONDS OR IN SHOTS, and having both is what lets one block
    cover a six-second suppression and a single enormous round. A shot budget
    without a duration would be a buff you could carry into the next fight;
    a duration without a shot budget cannot express "the next one".
    """

    duration: float
    #: Shots the window is worth, or 0 for "as many as the seconds allow".
    #: The window ends on whichever runs out first.
    shots: int = 0
    damage_scale: float = 1.0
    #: Multiplier on `fire_cooldown`. Under one is faster.
    cadence_scale: float = 1.0
    range_scale: float = 1.0
    #: The trigger costs no rounds while it is up. What makes a suppression
    #: ultimate a suppression rather than a way to empty your reserve faster.
    free_ammo: bool = False


@dataclass(frozen=True)
class Aura:
    """One pulse centred on the body. No travel, no aim, no dodge.

    The shape a SUPPORT ultimate has to have: what it answers is "the party is
    about to die where they are standing", and anything with a direction in it
    answers a different question.
    """

    radius_tiles: float
    heal: int = 0
    damage: int = 0


@dataclass(frozen=True)
class UltimateDef:
    """One catalog row. A weapon, a bar, a requirement and one effect block."""

    key: str
    name: str
    #: WHOSE it is. Exactly one per weapon — the HUD panel is the weapon in
    #: hand, so two ultimates on one weapon would have nowhere to be drawn and
    #: no key to be fired with.
    weapon: str
    #: One line, present tense, saying what pressing R does. It is on the
    #: catalog rather than in the HUD for the same reason a skill's blurb is.
    blurb: str
    #: Every tag that must be satisfied. A WEAPON tag is met by holding
    #: something that carries it; an ARMOUR tag is met by wearing `pieces` of
    #: a material that carries it.
    requires: tuple[str, ...]
    charge_on: str
    #: Units of `charge_on` a full bar is worth. The one number to turn when an
    #: ultimate comes round too often or never.
    charge_full: float
    volley: Volley | None = None
    empower: Empower | None = None
    aura: Aura | None = None
    #: How many pieces of a set an armour requirement wants. Defaults to the
    #: module's rule; on the row so a future ultimate can ask for the whole
    #: body without changing what every other one means.
    pieces: int = SET_PIECES

    @property
    def duration(self) -> float:
        """Seconds the effect lasts. Zero for anything that resolves at once."""
        return self.empower.duration if self.empower is not None else 0.0

    def client_payload(self) -> dict:
        return {
            "name": self.name,
            "weapon": self.weapon,
            "blurb": self.blurb,
            "requires": list(self.requires),
            "chargeOn": self.charge_on,
            "chargeFull": self.charge_full,
            "duration": self.duration,
            "pieces": self.pieces,
        }


#: FOUR ROWS, AND FOUR DIFFERENT VERBS. That is the acceptance test for this
#: catalog and it is worth stating before the rows: if two ultimates would
#: both read as "press R for more damage", one of them should not exist. A
#: crescent that cuts a lane through a pack, one round that deletes whatever
#: it touches, six seconds of not having to think about ammunition, and a
#: pulse that puts the party back on its feet are four things a player would
#: describe differently afterwards.
#:
#: THE REQUIREMENTS ARE ONE PER RUNG, ON PURPOSE. Leather unlocks the blade's,
#: steel the minigun's, kevlar the Deagle's, cloth the medic's — so there is no
#: armour in this game that unlocks two, and the best armour does not unlock
#: the most. A party of four dressed identically has one ultimate between them.
ULTIMATES: tuple[UltimateDef, ...] = (
    # THE ASSASSIN'S. A katana's whole problem is that it answers ONE thing
    # that got close; this is the beat where it answers the six behind it.
    # The crescent is fast (a strike, not a lobbed thing), long-lived and
    # wide, and because `projectiles.py` bills each body once it opens a LANE
    # through a pack rather than killing the front of it.
    #
    # It charges off melee damage, which is the only source that requires
    # standing in the middle of them. You earn the escape by having been
    # somewhere you needed one.
    UltimateDef(
        key="shadow_slash",
        name="Corte Sombrio",
        weapon="katana",
        blurb="Um corte que atravessa tudo em linha reta.",
        requires=("blade", "ninja"),
        charge_on=CHARGE_DAMAGE,
        charge_full=300.0,
        volley=Volley(
            count=1,
            spread_degrees=0.0,
            damage=90,
            # Fast — this is a strike thrown from the hand, and a slow one
            # would be a thing the pack simply steps around.
            speed_tiles=15.0,
            life=1.1,
            # Nearly a tile and a half of sweep. The number that makes it read
            # as an arc of steel rather than as a very large bullet.
            radius_tiles=1.4,
            look="slash",
        ),
    ),
    # THE MARKSMAN'S. One round, and the whole point is that it is ONE: a
    # window budgeted in shots rather than in seconds, so the ultimate is over
    # the instant you use it and the decision is entirely about WHAT you point
    # it at. Six times a Deagle's damage puts it past anything in the forest
    # and makes it a real bite out of the Sawyer, which is the only target in
    # the game worth saving it for.
    #
    # The seconds on it are a leash, not a buff: hold the round too long
    # without firing and you lose it, so it cannot be carried between fights.
    UltimateDef(
        key="extreme_shot",
        name="Tiro Extremo",
        weapon="deagle",
        blurb="O próximo tiro atravessa a clareira e leva tudo junto.",
        requires=("precision", "tactical"),
        charge_on=CHARGE_DAMAGE,
        charge_full=420.0,
        empower=Empower(
            duration=6.0,
            shots=1,
            damage_scale=6.0,
            range_scale=2.4,
        ),
    ),
    # THE GUNNER'S. A minigun's real enemy is its own reserve — two hundred
    # and forty rifle rounds is about thirteen seconds of held trigger — so
    # the ultimate is not "more damage", it is SIX SECONDS OF NOT COUNTING.
    # That is the correct shape for this weapon: the fantasy was never that it
    # hits hard, it is that it does not stop.
    #
    # The cadence lift is small beside the free ammunition, deliberately. What
    # the player should remember afterwards is the length of the burst.
    UltimateDef(
        key="bullet_storm",
        name="Tempestade de Balas",
        weapon="minigun",
        blurb="Seis segundos sem munição, sem pausa e sem recuo.",
        requires=("automatic", "riot"),
        charge_on=CHARGE_DAMAGE,
        charge_full=900.0,
        empower=Empower(
            duration=6.0,
            cadence_scale=0.7,
            damage_scale=1.35,
            free_ammo=True,
        ),
    ),
    # THE MEDIC'S. The only ultimate in the catalog that does no damage at
    # all, and the only one that can be aimed at nothing — it is a pulse
    # centred on the body, because what it answers is "everybody here is about
    # to die where they are standing" and a direction would answer a different
    # question.
    #
    # It charges off HEALING, which solo is nearly unreachable and in a party
    # is the natural consequence of doing the job. That asymmetry is the
    # point: this is the one row in the catalog that is a statement about
    # having other people with you.
    UltimateDef(
        key="emergency_protocol",
        name="Protocolo de Emergência",
        weapon="medgun",
        blurb="Um pulso de cura que alcança toda a equipe por perto.",
        requires=("support", "medic"),
        charge_on=CHARGE_HEAL,
        charge_full=110.0,
        aura=Aura(radius_tiles=6.5, heal=55),
    ),
)

BY_KEY: dict[str, UltimateDef] = {row.key: row for row in ULTIMATES}

#: Which ultimate a weapon carries. Built rather than written, so "exactly one
#: per weapon" is enforced by the build instead of by a comment.
BY_WEAPON: dict[str, UltimateDef] = {}
for _row in ULTIMATES:
    if _row.weapon in BY_WEAPON:
        raise ValueError(
            f"{_row.weapon} carries two ultimates ({BY_WEAPON[_row.weapon].key} "
            f"and {_row.key}) — the HUD panel is the weapon in hand and has "
            f"room for one"
        )
    BY_WEAPON[_row.weapon] = _row
    for _tag in _row.requires:
        if _tag not in TAG_BY_KEY:
            raise ValueError(
                f"{_row.key} requires '{_tag}', which is not in TAGS — the HUD "
                f"would print a requirement it cannot name"
            )
del _row


def _check_armor_tags() -> None:
    """Every armour tag in `TAGS` has to exist on a material, and vice versa.

    Run at import, because the failure has no runtime symptom worth the name:
    an ultimate requiring a tag no material carries is simply an ultimate that
    can never be unlocked, and it looks exactly like one the player has not
    found the armour for yet.
    """
    worn = {tag for material in armor.MATERIALS for tag in material.tags}
    declared = {tag.key for tag in TAGS if tag.source == SOURCE_ARMOR}
    missing = worn - declared
    if missing:
        raise ValueError(f"armour carries untagged {sorted(missing)} — the HUD cannot name it")
    unreachable = declared - worn
    if unreachable:
        raise ValueError(
            f"{sorted(unreachable)} is required of armour and no material has it — "
            f"an ultimate behind it can never unlock"
        )


_check_armor_tags()


# --- is it unlocked ----------------------------------------------------------


def missing_tags(
    ultimate: UltimateDef,
    weapon_tags: tuple[str, ...] | set[str],
    worn_pieces: dict[str, int],
) -> tuple[str, ...]:
    """Which requirements are NOT met, in the row's own order.

    RETURNS THE GAP RATHER THAN A BOOLEAN, because the HUD's whole job when an
    ultimate is locked is to say what is missing. A predicate would make the
    panel ask the same question a second time with its own copy of the rule,
    which is how the tooltip ends up disagreeing with the trigger.
    """
    held = set(weapon_tags)
    gap: list[str] = []
    for tag in ultimate.requires:
        definition = TAG_BY_KEY[tag]
        if definition.source == SOURCE_WEAPON:
            if tag not in held:
                gap.append(tag)
        elif worn_pieces.get(tag, 0) < ultimate.pieces:
            gap.append(tag)
    return tuple(gap)


def unlocked(
    ultimate: UltimateDef,
    weapon_tags: tuple[str, ...] | set[str],
    worn_pieces: dict[str, int],
) -> bool:
    return not missing_tags(ultimate, weapon_tags, worn_pieces)


def catalog_payload() -> dict:
    """Every ultimate the client has to be able to name, draw and explain."""
    return {row.key: row.client_payload() for row in ULTIMATES}


def tags_payload() -> dict:
    """The vocabulary, so the HUD can print a requirement without a table."""
    return {tag.key: {"name": tag.name, "source": tag.source} for tag in TAGS}
