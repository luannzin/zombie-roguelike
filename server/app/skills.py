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
#: legendary has to be a thing that actually happens to somebody.
#:
#: THE TOP OF THE LADDER IS TWICE WHAT IT WAS (2 -> 4), and the argument is
#: about how long a run is. A vertical slice is ten days and a level is a pull,
#: so a party sees somewhere near a dozen of these in a whole run: at one in
#: fifty, most runs ended without anybody ever seeing the machine pay out the
#: colour it spends four seconds building up to. One in twenty-five is still
#: the rarest row on the reel by a factor of eleven — it is the thing that
#: happens ONCE in a good run rather than the thing that never happens.
PULL_WEIGHTS: dict[str, float] = {
    "common": 44,
    "uncommon": 29,
    "rare": 17,
    "epic": 8,
    "legendary": 4,
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
    #:
    #: A NEGATIVE STEP IS A REAL DOWNSIDE and needs no new machinery: `armor`
    #: has always been stored as the multiplier on damage TAKEN, so a row that
    #: pushes it UP is a row that makes you softer. See the trade-off tier at
    #: the bottom of the catalog for why that is worth having.
    effects: tuple[tuple[str, float], ...] = ()
    #: RULES THIS ROW FLIPS, by name. Booleans on `Mods`, not numbers.
    #:
    #: WHY THE CATALOG NEEDED THIS AT ALL. Every row above is `(field, number)`,
    #: which means every build in the game is the same build with different
    #: dials — you are always the same survivor, moving a bit faster or hitting
    #: a bit harder. That is a difficulty slider wearing a skill tree's clothes,
    #: and it is the single reason no archetype in this game has ever felt
    #: different to play rather than merely better.
    #:
    #: A rule has no number, does not stack, and CHANGES WHAT YOU CAN DO. It is
    #: the difference between "I take 12% less damage" and "a blow does not
    #: interrupt my bandage" — the second one changes where you are willing to
    #: stand, which is a decision rather than an amount.
    #:
    #: A row may carry both. A rule row with a small number attached is still a
    #: rule row; what it must not be is a number row with a rule bolted on as a
    #: sweetener, because then the rule is something the player got by accident.
    rules: tuple[str, ...] = ()
    #: How many copies stack. Past it a duplicate still pays (see
    #: `Loadout.add`), it just stops moving the number.
    #:
    #: A PURE RULE ROW CAPS AT ONE. A boolean cannot be flipped twice, so a
    #: second copy would be a canister that did nothing at all — which is a
    #: worse outcome than a duplicate that merely does little.
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
    # --- the second pass ----------------------------------------------------
    # EIGHTEEN MORE ROWS, APPENDED RATHER THAN FILED UNDER THEIR TIERS.
    #
    # Catalog order is the ICON ATLAS's frame order (`FRAME`, and
    # `tools/make_skills.ICONS` beside it), and generated-asset lists in this
    # repository are append-only: slotting a new common in next to the old ones
    # would move every frame index after it, and the first thing anybody would
    # notice is that half the tray is wearing somebody else's picture. Nothing
    # reads this tuple in order except the sheet — `roll` goes through
    # `_BY_RARITY` — so the tiers below are a comment, not a structure.
    #
    # WHY MORE AT ALL. Five commons and two legendaries is a machine that
    # repeats itself inside one run: by the fourth pull a party has seen most
    # of the tier they are actually rolling in, and a duplicate that is only a
    # smaller version of the same number is the least interesting thing this
    # cabinet can do. Nine, eight, eight, six and five is roughly double, which
    # is the point where a ten-day run stops showing you the same three commons.
    #
    # WHAT IS NEW IN THEM IS `armor`. Every row above scales something you DO —
    # move, hit, carry, earn — and there was nothing to buy that made being hit
    # cost less, which is the one axis a roguelike about walking into the dark
    # cannot leave empty. It is a multiplier on damage TAKEN, so it stacks
    # multiplicatively with `max_hp` rather than duplicating it: more health is
    # a longer bar, armour is a bar that drains slower.

    # --- common -------------------------------------------------------------
    SkillDef(
        "lamparina_limpa", "Lamparina Limpa", "common",
        "a lanterna dura +8%",
        (("lamp", 0.08),),
    ),
    SkillDef(
        "punho_calejado", "Punho Calejado", "common",
        "+6% de dano de faca",
        (("melee", 0.06),),
    ),
    SkillDef(
        "colete_improvisado", "Colete Improvisado", "common",
        "-4% de dano sofrido",
        (("armor", -0.04),),
    ),
    SkillDef(
        "caderneta_do_sucateiro", "Caderneta do Sucateiro", "common",
        "+6% de xp",
        (("xp", 0.06),),
    ),
    # --- uncommon -----------------------------------------------------------
    SkillDef(
        "mira_de_ferro", "Mira de Ferro", "uncommon",
        "+9% de dano de arma",
        (("gun", 0.09),),
    ),
    SkillDef(
        "couro_batido", "Couro Batido", "uncommon",
        "-7% de dano sofrido",
        (("armor", -0.07),),
    ),
    SkillDef(
        "mao_leve", "Mão Leve", "uncommon",
        "+18% de ouro escuro",
        (("luck", 0.18),),
    ),
    SkillDef(
        "ombro_firme", "Ombro Firme", "uncommon",
        "+12 de vida máxima",
        (("max_hp", 12.0),),
    ),
    # --- rare ---------------------------------------------------------------
    SkillDef(
        "pisada_de_gato", "Pisada de Gato", "rare",
        "+10% de velocidade",
        (("speed", 0.10),),
    ),
    SkillDef(
        "placa_de_aco", "Placa de Aço", "rare",
        "-12% de dano sofrido",
        (("armor", -0.12),),
        cap=4,
    ),
    SkillDef(
        "mochila_de_lona", "Mochila de Lona", "rare",
        "+4 kg de carga",
        (("carry", 4.0),),
        cap=4,
    ),
    SkillDef(
        "fio_da_navalha", "Fio da Navalha", "rare",
        "+22% de dano de faca",
        (("melee", 0.22),),
    ),
    # --- epic ---------------------------------------------------------------
    SkillDef(
        # NAMED FOR ITS ICON, and that is a legitimate reason. It was "Pulso de
        # Aço" — a steel wrist — which at sixteen pixels is a grey fist, and
        # the tray already had a helmet, a pauldron and two plates in the same
        # grey. A longer barrel is the same +22% and it draws as a barrel with
        # a flash coming off it, which nobody has to be told about.
        "cano_longo", "Cano Longo", "epic",
        "+22% de dano de arma",
        (("gun", 0.22),),
        cap=3,
    ),
    SkillDef(
        "casco_de_ferro", "Casco de Ferro", "epic",
        "-18% de dano sofrido",
        (("armor", -0.18),),
        cap=3,
    ),
    SkillDef(
        "passo_de_sombra", "Passo de Sombra", "epic",
        "+12% de velocidade e a lanterna dura +20%",
        (("speed", 0.12), ("lamp", 0.20)),
        cap=3,
    ),
    # --- legendary ----------------------------------------------------------
    SkillDef(
        "pele_de_pedra", "Pele de Pedra", "legendary",
        "-25% de dano sofrido e +20 de vida máxima",
        (("armor", -0.25), ("max_hp", 20.0)),
        cap=2,
    ),
    SkillDef(
        "maos_do_armeiro", "Mãos do Armeiro", "legendary",
        "+30% de dano de arma e +25% de dano de faca",
        (("gun", 0.30), ("melee", 0.25)),
        cap=2,
    ),
    SkillDef(
        "bolsa_sem_fundo", "Bolsa Sem Fundo", "legendary",
        "+2 espaços na mochila e +3 kg de carga",
        (("slots", 2.0), ("carry", 3.0)),
        cap=2,
    ),

    # --- the third pass: rows that are not numbers ---------------------------
    #
    # FIVE ROWS, NOT EIGHTEEN, AND THAT IS THE POINT OF THEM.
    #
    # Everything above this line is `(field, number)`. Thirty-six rows of it,
    # and the honest description of what they build is: the same survivor, with
    # different dials. You are always the same person moving a bit faster or
    # hitting a bit harder, and no two runs ever PLAY differently — they only
    # go better or worse. That is a difficulty slider wearing a skill tree's
    # clothes, and it is the single reason no archetype in this game has ever
    # felt like a character.
    #
    # These five are the other kind. Three of them flip a RULE — no number
    # attached, no stacking, and what changes is what you are able to do rather
    # than how much of it. Two of them COST something real, which is the other
    # half of the same idea: a catalog where every row is an improvement is a
    # catalog where every choice is "yes", and a choice with one answer is not
    # a choice.
    #
    # They are appended, like every pass before them, because catalog order IS
    # the icon atlas's frame order. See the note at the head of the second pass.
    #
    # DELIBERATELY FEW. Rule rows need PLAYING, not volume: each one removes a
    # constraint the rest of the game is balanced against, and the only way to
    # find out whether that is interesting or ruinous is to live with it for a
    # few nights. Eighteen at once would be eighteen unknowns interacting.

    # --- rules ---------------------------------------------------------------
    SkillDef(
        # PAIRS WITH THE NIGHT'S SCRIPT (`events.py`'s `dark`). The dark is the
        # one event that SUBTRACTS — it takes away the lantern trade the player
        # has been making all night — and this is the row that says it does not
        # apply to you. Being the only lit thing in a black forest is not
        # strictly an advantage either, which is what makes it interesting.
        "filamento_frio", "Filamento Frio", "rare",
        "sua lanterna não apaga quando a noite fecha",
        rules=("lamp_immune",),
        # A BOOLEAN CANNOT BE FLIPPED TWICE. A second copy would be a canister
        # that did nothing at all, which is worse than one that does little.
        cap=1,
    ),
    SkillDef(
        # PAIRS WITH MEDICINE (`medical.py`). A heal's entire cost is standing
        # still where something can reach you, and this does not remove the
        # damage — only the interruption. What it buys is the ability to COMMIT
        # to a heal somewhere you expect to be hit, which is a decision about
        # position rather than a discount on being wrong.
        "sangue_frio", "Sangue Frio", "epic",
        "levar um golpe não interrompe seu curativo",
        rules=("steady",),
        cap=1,
    ),
    SkillDef(
        # PAIRS WITH THE VAULT (`crates.open_time`). The strongest rule here
        # and deliberately so: it removes the whole STAKE of forcing a
        # container — the noise that goes out before you know whether it was
        # worth it — rather than shortening the seconds. That is what a
        # legendary should be allowed to be: not a bigger number, but a rule of
        # the world that stops applying to you.
        "maos_de_veludo", "Mãos de Veludo", "legendary",
        "forçar um cofre não faz barulho",
        rules=("quiet_hands",),
        cap=1,
    ),

    # --- rows that cost something -------------------------------------------
    #
    # NO NEW MACHINERY. `armor` has always been the multiplier on damage TAKEN,
    # so a row that pushes it UP is a row that makes you softer, and `speed`
    # going down is a row that makes you slower. The catalog could always have
    # done this and simply never did.
    #
    # THE DOWNSIDE IS IN THE BLURB, first, before the upside. A cost the player
    # discovers by dying is a bug report; a cost they read on the canister and
    # took anyway is a build.
    SkillDef(
        # The classic trade, and it is here because it is the one that most
        # obviously produces a DIFFERENT RUN rather than a better one: a party
        # carrying this fights at a range they would not otherwise pick, and
        # has to solve being hit some other way.
        "gatilho_nervoso", "Gatilho Nervoso", "epic",
        "+35% de dano de arma, mas +20% de dano sofrido",
        (("gun", 0.35), ("armor", 0.20)),
        # Capped LOW. Three copies is +60% damage taken, which stops being a
        # trade and becomes a way to delete yourself with a skill.
        cap=2,
    ),
    SkillDef(
        # THE HAULER. Everything this game rewards is carried out on your back,
        # and this is the row that says you may carry more of it if you accept
        # being slower with it — which under permadeath is a real question,
        # because the thing you cannot do with a full bag is run away.
        "mula_de_carga", "Mula de Carga", "rare",
        "+4 kg de carga e +1 espaço, mas -6% de velocidade",
        (("carry", 4.0), ("slots", 1.0), ("speed", -0.06)),
        cap=3,
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
    #: Damage TAKEN, as a multiplier. The only field on this struct that a
    #: skill pushes DOWN — see the armour note in the catalog — and the only
    #: one with a floor under it, in `flatten`.
    armor: float = 1.0

    # --- the rules ----------------------------------------------------------
    #
    # Booleans rather than numbers, and that is the whole point of them: every
    # field above answers "how much", and these answer "can I". A build made
    # only of the fields above is the same survivor with different dials; a
    # build with one of these in it plays differently.
    #
    # They are read at exactly one site each, named in the comment, because a
    # rule checked in two places is a rule that will be missing from the third.

    #: An event dark does not take YOUR lamp. Read by `Room.begin_dark` and
    #: `Room.queue_input` — the two halves of the suppression.
    lamp_immune: bool = False
    #: A blow does not interrupt your medical channel. Read by
    #: `Room.damage_player`, right where the channel is cleared.
    #:
    #: It does NOT stop the damage. What it buys is the ability to commit to a
    #: heal in a place where you expect to be hit, which is a decision about
    #: position — the exact axis medicine was designed around — rather than a
    #: discount on being wrong.
    steady: bool = False
    #: Forcing a container makes no noise. Read by `Room._begin_force`.
    #:
    #: The strongest rule in the catalog and deliberately so: it removes the
    #: entire stake of the vault (see `crates.ObjectType.open_time`), which is
    #: exactly what a legendary should be allowed to do — not a bigger number,
    #: but a rule of the world that stops applying to you.
    quiet_hands: bool = False

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
            # THE ONE RULE THE CLIENT HAS TO KNOW, because the client runs the
            # battery and predicts its own lamp: without this the owner of the
            # skill would watch their light go out on an event dark and come
            # back a packet later. `steady` and `quiet_hands` are resolved
            # entirely server-side and are deliberately NOT here — shipping a
            # rule nobody predicts is inviting somebody to re-implement it.
            "lampImmune": self.lamp_immune,
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
    "armor": 1.0,
}


def flatten(stacks: dict[str, int]) -> Mods:
    """Roll a `{key: copies}` dict up into one `Mods`."""
    totals = dict(_BASE)
    rules: set[str] = set()
    for key, copies in stacks.items():
        row = BY_KEY.get(key)
        if row is None or copies <= 0:
            continue
        effective = min(copies, row.cap)
        for field, step in row.effects:
            if field in totals:
                totals[field] += step * effective
        # A RULE IS A SET MEMBERSHIP AND NOT A SUM. Owning one copy and owning
        # three are the same sentence, so `effective` is deliberately not
        # consulted here — the cap on a rule row exists to stop the machine
        # handing out a canister that does nothing, not to scale anything.
        rules.update(row.rules)
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
        # THE ONE CLAMPED FIELD. Every other stat here is unbounded because an
        # unbounded speed or carry is a number that gets silly; an unbounded
        # armour is a number that ENDS THE GAME — five Placas, three Cascos and
        # two Peles is -1.54, and a player taking negative damage is a player
        # being healed by zombies. A third of the hit still lands however lucky
        # the machine has been.
        armor=max(0.35, totals["armor"]),
        lamp_immune="lamp_immune" in rules,
        steady="steady" in rules,
        quiet_hands="quiet_hands" in rules,
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


def catalog_payload() -> dict[str, dict]:
    """`welcome.config.skills` — the client's whole table, KEYED BY KEY.

    Same contract as the loot catalog: name, rarity and atlas frame ride the
    config so the HUD can draw a tile the server only ever names by key.

    A DICT AND NOT A LIST, because every consumer on the other side is a
    lookup: the tray row, the canister's icon and the hover card all start
    from a key that arrived on the roster or on a spin event. This shipped a
    list of `{"k": ...}` rows once while the client declared
    `Record<string, SkillConfig>`, and the result was `config.skills[key]`
    resolving to `undefined` for every skill in the game — the tray stayed
    empty for a whole run and the canister always wore frame 0. Nothing
    errored, on either side, because an array IS an object in JS and
    `test_config_parity` only compares the top-level key sets.
    """
    return {
        row.key: {
            "name": row.name,
            "rarity": row.rarity,
            "blurb": row.blurb,
            "frame": FRAME[row.key],
            "cap": row.cap,
        }
        for row in SKILLS
    }


def luck_chance(mods: Mods) -> float:
    """Dark-gold flip odds for a body this player killed.

    Clamped below 1: a guaranteed coin off every point of a corpse's gold would
    turn the faucet `config.COIN_DROP_CHANCE` deliberately holds shut back on,
    and the whole reason that number sits under a half is that group gold is
    what a night is scored on.
    """
    return min(0.85, COIN_DROP_CHANCE * mods.luck)
