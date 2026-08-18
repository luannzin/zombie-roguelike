"""Skills: what a level is FOR, and the only thing xp buys.

xp used to be a bar that filled and then filled again. A number that goes up
and changes nothing is a score, not progression, so a LEVEL now pays out one
token — a spin — and the only place a spin can be spent is the machine standing
in the merchant's camp. That is the whole loop: kill things in the woods, walk
out, pull the lever, find out what you got.

WHY IT IS A ROLL AND NOT A MENU
A list of upgrades with prices is a spreadsheet the player solves once and then
executes every run afterwards. A roll is a moment: you know a spin is coming,
you know roughly what the odds look like, and you do not know what is about to
come out of the slot. The rarity ladder is the same five steps loot already
uses, so a purple canister means the same thing here that a purple aura means
in the woods, and nobody has to learn a second colour language.

WHAT A SKILL IS
A stack. Every copy of `passo_leve` adds its step to the same field, up to the
row's own `cap`, so a duplicate is never a dead pull — it is a smaller one.
`Mods` is the flattened result: one frozen struct rebuilt whenever the dict
changes, read by the handful of places that already multiply something.

WHAT THIS MODULE DOES NOT OWN
Where the machine stands (`store.py`), what pulling it looks like
(`client/src/render/machine.ts`), what a pull costs (nothing — a spin is a
level, and levels are free), and the art (`server/tools/make_skills.py` for the
icons and canisters, `make_machine.py` for the cabinet).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .config import CARRY_MAX_WEIGHT, COIN_DROP_CHANCE, MAX_HP

#: The same ladder loot rolls on, in the same order, with the same colours on
#: the client. A skill and an item are two things a night can hand you and they
#: must not be graded on two scales.
RARITIES = ("common", "uncommon", "rare", "epic", "legendary")

#: What a pull is worth. Flatter than the loot table on purpose: a spin is
#: earned by playing a whole level rather than found on the floor, so a
#: legendary has to be a thing that actually happens to somebody. It is still
#: the rarest row by a factor of twenty, which is what keeps the machine worth
#: watching.
PULL_WEIGHTS: dict[str, float] = {
    "common": 44,
    "uncommon": 29,
    "rare": 17,
    "epic": 8,
    "legendary": 2,
}


@dataclass(frozen=True)
class SkillDef:
    """One row of the catalog. Catalog order is the icon atlas frame order."""

    key: str
    name: str
    rarity: str
    #: One line, in the player's language, stating the EFFECT rather than the
    #: flavour. It is what the canister says as it lands and what the HUD tile
    #: says on hover, and at both sizes flavour text is a thing to scroll past.
    blurb: str
    #: `(field on Mods, how much ONE copy is worth)`. A tuple because the top
    #: of the ladder is allowed to do two things at once — that is most of why
    #: a legendary reads as a legendary rather than as a bigger common.
    effects: tuple[tuple[str, float], ...]
    #: How many copies stack. Past it a duplicate still pays (see
    #: `Loadout.add`), it just stops moving the number.
    cap: int = 5


#: THE CATALOG. Grouped by rarity, and inside a rarity the rows are deliberately
#: NOT interchangeable: a common that is "+4% speed" beside a common that is
#: "+8 hp" is a choice the machine made for you, and the player should be able
#: to feel which way their build drifted over a run.
#:
#: STEPS ARE SMALL AND THE CAPS ARE LOW. A vertical slice is ten days, not a
#: hundred, so the ceiling that matters is what a party can stack in ten pulls —
#: and a run where the numbers stop mattering by day four has spent the whole
#: curve before the content runs out.
SKILLS: tuple[SkillDef, ...] = (
    # --- common: the floor, and the rows that just make the walk nicer -------
    SkillDef(
        "passo_leve", "Passo Leve", "common",
        "+4% de velocidade",
        (("speed", 0.04),),
    ),
    SkillDef(
        "forro_reforcado", "Forro Reforçado", "common",
        "+1,2 kg de carga",
        (("carry", 1.2),),
    ),
    SkillDef(
        "mao_firme", "Mão Firme", "common",
        "+5% de dano de arma",
        (("gun", 0.05),),
    ),
    SkillDef(
        "couro_grosso", "Couro Grosso", "common",
        "+8 de vida máxima",
        (("max_hp", 8.0),),
    ),
    SkillDef(
        "dedos_rapidos", "Dedos Rápidos", "common",
        "+10% de ouro escuro",
        (("luck", 0.10),),
    ),
    # --- uncommon -----------------------------------------------------------
    SkillDef(
        "lamina_afiada", "Lâmina Afiada", "uncommon",
        "+15% de dano de faca",
        (("melee", 0.15),),
    ),
    SkillDef(
        "bateria_fria", "Bateria Fria", "uncommon",
        "a lanterna dura +18%",
        (("lamp", 0.18),),
    ),
    SkillDef(
        "pulmao_fundo", "Pulmão Fundo", "uncommon",
        "+7% de velocidade",
        (("speed", 0.07),),
    ),
    SkillDef(
        "costura_grossa", "Costura Grossa", "uncommon",
        "+2,5 kg de carga",
        (("carry", 2.5),),
    ),
    # --- rare ---------------------------------------------------------------
    SkillDef(
        "veterano", "Veterano", "rare",
        "+15% de xp",
        (("xp", 0.15),),
    ),
    SkillDef(
        "mira_apurada", "Mira Apurada", "rare",
        "+12% de dano de arma",
        (("gun", 0.12),),
    ),
    SkillDef(
        "pele_dura", "Pele Dura", "rare",
        "+18 de vida máxima",
        (("max_hp", 18.0),),
    ),
    SkillDef(
        "olho_de_sucateiro", "Olho de Sucateiro", "rare",
        "+8% no valor do que você embarca",
        (("haul", 0.08),),
        cap=4,
    ),
    # --- epic ---------------------------------------------------------------
    SkillDef(
        "acougueiro", "Açougueiro", "epic",
        "+30% de dano de faca",
        (("melee", 0.30),),
        cap=3,
    ),
    SkillDef(
        "bolsos_fundos", "Bolsos Fundos", "epic",
        "+1 espaço na mochila",
        (("slots", 1.0),),
        cap=3,
    ),
    SkillDef(
        "faro_de_ouro", "Faro de Ouro", "epic",
        "+35% de ouro escuro e +1,5 kg de carga",
        (("luck", 0.35), ("carry", 1.5)),
        cap=3,
    ),
    # --- legendary ----------------------------------------------------------
    SkillDef(
        "coracao_de_ferro", "Coração de Ferro", "legendary",
        "+35 de vida máxima e +8% de velocidade",
        (("max_hp", 35.0), ("speed", 0.08)),
        cap=2,
    ),
    SkillDef(
        "rei_do_ferro_velho", "Rei do Ferro-Velho", "legendary",
        "+25% no valor do que você embarca",
        (("haul", 0.25),),
        cap=2,
    ),
)

BY_KEY: dict[str, SkillDef] = {row.key: row for row in SKILLS}
#: Frame index into the icon atlas. Catalog order, like every other sheet here.
FRAME: dict[str, int] = {row.key: index for index, row in enumerate(SKILLS)}

_BY_RARITY: dict[str, list[SkillDef]] = {
    rarity: [row for row in SKILLS if row.rarity == rarity] for rarity in RARITIES
}


@dataclass(frozen=True)
class Mods:
    """A loadout flattened into the numbers the rest of the server multiplies.

    ABSOLUTE where the thing it replaces is absolute (`max_hp`, `carry`) and a
    MULTIPLIER where the thing it scales is a rate. Mixing the two in one field
    is how a "+8 hp" and a "+8% hp" end up looking identical in a diff.
    """

    speed: float = 1.0
    max_hp: int = MAX_HP
    carry: float = CARRY_MAX_WEIGHT
    slots: int = 0
    gun: float = 1.0
    melee: float = 1.0
    xp: float = 1.0
    luck: float = 1.0
    lamp: float = 1.0
    haul: float = 1.0

    def payload(self) -> dict:
        """What the owning client needs to predict its own body.

        Only the fields the CLIENT reads: it mirrors movement and carry weight,
        it draws the health bar, and it runs its own battery. Damage, xp and
        drop luck are resolved server-side and never predicted, so shipping
        them would only be inviting somebody to re-implement them.
        """
        return {
            "speed": round(self.speed, 4),
            "maxHp": self.max_hp,
            "carry": round(self.carry, 2),
            "slots": self.slots,
            "lamp": round(self.lamp, 4),
        }


#: How a field starts before any skill touches it. Split out so `flatten` is one
#: loop rather than a per-field special case, and so a new stat is one row here
#: plus one field on `Mods`.
_BASE: dict[str, float] = {
    "speed": 1.0,
    "max_hp": float(MAX_HP),
    "carry": CARRY_MAX_WEIGHT,
    "slots": 0.0,
    "gun": 1.0,
    "melee": 1.0,
    "xp": 1.0,
    "luck": 1.0,
    "lamp": 1.0,
    "haul": 1.0,
}


def flatten(stacks: dict[str, int]) -> Mods:
    """Roll a `{key: copies}` dict up into one `Mods`."""
    totals = dict(_BASE)
    for key, copies in stacks.items():
        row = BY_KEY.get(key)
        if row is None or copies <= 0:
            continue
        effective = min(copies, row.cap)
        for field, step in row.effects:
            if field in totals:
                totals[field] += step * effective
    return Mods(
        speed=totals["speed"],
        max_hp=int(round(totals["max_hp"])),
        carry=totals["carry"],
        slots=int(round(totals["slots"])),
        gun=totals["gun"],
        melee=totals["melee"],
        xp=totals["xp"],
        luck=totals["luck"],
        lamp=totals["lamp"],
        haul=totals["haul"],
    )


def roll(rng: random.Random, owned: dict[str, int] | None = None) -> SkillDef:
    """One pull. Rarity first, then a row inside it.

    TWO ROLLS, NOT ONE WEIGHTED LIST, because the rarity is the thing the
    machine is dramatising: the reels stop on a COLOUR and the canister that
    drops is that colour, so the tier has to be decided before the row is. A
    single flat table over eighteen rows would also mean adding a common
    quietly made every legendary rarer.

    A row already at its cap is pushed to the back of the queue rather than
    removed: a maxed-out tier must still be able to pay, or a lucky party ends
    up rolling legendaries they cannot receive.
    """
    rarity = rng.choices(RARITIES, weights=[PULL_WEIGHTS[r] for r in RARITIES], k=1)[0]
    pool = _BY_RARITY.get(rarity) or list(SKILLS)
    stacks = owned or {}
    fresh = [row for row in pool if stacks.get(row.key, 0) < row.cap]
    return rng.choice(fresh or pool)


class Loadout:
    """A player's skills: the stacks, the flattened mods, and the spins owed.

    SPINS ARE OWED, NOT GRANTED. `sync_level` is called with the player's
    current level every time xp moves, and it pays out the difference — so a
    level earned in the woods on day two is still spendable on day five, and
    dying, reconnecting or walking through three zones never loses one. The
    machine is the only thing that can spend them and it only exists in the
    shop, which is exactly the point: the reward for a level is a reason to
    look forward to the walk out.
    """

    __slots__ = ("stacks", "mods", "spins", "_level")

    def __init__(self) -> None:
        self.stacks: dict[str, int] = {}
        self.mods = flatten({})
        self.spins = 0
        #: The highest level already paid for. Starts at 1 because a run opens
        #: there — paying a spin for the level you were born at would hand out
        #: a free pull before anybody has killed anything.
        self._level = 1

    def sync_level(self, level: int) -> int:
        """Pay out spins for any level gained since the last call. Returns how many."""
        if level <= self._level:
            return 0
        gained = level - self._level
        self._level = level
        self.spins += gained
        return gained

    def add(self, key: str) -> int:
        """Take a skill. Returns how many copies are held after it.

        A copy past the cap is still RECORDED. The tile keeps counting up, so
        somebody who pulled a fourth Coração de Ferro can see that they did,
        and `flatten` is what refuses to keep paying for it — the alternative
        is a canister that visibly comes out of the machine and then does not
        appear anywhere, which reads as a bug rather than as a ceiling.
        """
        if key not in BY_KEY:
            return 0
        self.stacks[key] = self.stacks.get(key, 0) + 1
        self.mods = flatten(self.stacks)
        return self.stacks[key]

    def to_payload(self) -> list[dict]:
        """The tray above the bag: key, copies. Name and icon come off config."""
        return [
            {"k": key, "n": count}
            for key, count in sorted(self.stacks.items(), key=lambda row: FRAME.get(row[0], 0))
        ]


def catalog_payload() -> list[dict]:
    """`welcome.config.skills` — the client's whole table.

    Same contract as the loot catalog: name, rarity and atlas frame ride the
    config so the HUD can draw a tile the server only ever names by key.
    """
    return [
        {
            "k": row.key,
            "name": row.name,
            "rarity": row.rarity,
            "blurb": row.blurb,
            "frame": FRAME[row.key],
            "cap": row.cap,
        }
        for row in SKILLS
    ]


def luck_chance(mods: Mods) -> float:
    """Dark-gold flip odds for a body this player killed.

    Clamped below 1: a guaranteed coin off every point of a corpse's gold would
    turn the faucet `config.COIN_DROP_CHANCE` deliberately holds shut back on,
    and the whole reason that number sits under a half is that group gold is
    what a night is scored on.
    """
    return min(0.85, COIN_DROP_CHANCE * mods.luck)
