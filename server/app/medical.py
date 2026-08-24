"""The medical belt: two cells, and the only way health ever comes back.

WHY THIS IS NOT IN THE BAG
==========================
It was going to be. The obvious design is a medkit as ordinary loot with a
`value` on it, so the player weighs "this is fifty-eight gold at the platform"
against "this is being alive right now" — a nice greed decision on paper.

It stopped being one the moment death started ending runs. Nobody sells the
thing that saves a run to buy a marginally better rifle, so the choice resolves
to KEEP every single time, and a choice with one answer is a slot in the bag
that always holds the same object. Worse, it would be competing with loot for
pocket cells, which makes surviving a decision against extracting — a tax on
playing rather than a trade-off.

So medicine came out of the pocket entirely. It has no value, it cannot be
poured into a platform, it cannot be sold, and it lives in CELLS OF ITS OWN
on the keys straight after the belt (`MEDICAL_SLOTS`). What that buys is a better question than the one it replaced:
two is a hard ceiling, so the decision is never "should I own this", it is
**"do I spend my second-to-last one here, or push one more clearing?"** That is
the survival-horror question, and it is asked several times a night instead of
once at a shop counter.

IT STILL COSTS THE BAG SOMETHING
================================
`Medical.weight` is summed into `Player.carry_weight` exactly like worn plate
is. It takes no pocket CELL and it does take pocket SPEED, so a party that
walks in carrying two kits carries less loot out. The greed trade did not
disappear when the sell price did — it moved somewhere it actually holds.

THE TWO KITS ARE A REAL CHOICE, NOT A LADDER
============================================
They are deliberately not "small heal" and "big heal", because that is one item
twice and the second cell would always hold the better one. They trade on
different axes:

    first_aid   heals a LOT, takes a LONG time, is HEAVY   — the safe heal
    morphine    heals LESS, is nearly INSTANT, is LIGHT    — the panic heal

So the interesting loadout is one of each: something to spend after a fight and
something to spend during one. Two of either is a legitimate and different
plan, which is what makes the second cell worth thinking about.

BOTH ARE ALREADY IN THE LOOT CATALOG AND ALREADY HAVE ART. `first_aid` and
`morphine` have been rows in `loot.ITEMS` since the beginning, sitting there as
pure cargo with a price on them. They keep their keys, their names and their
atlas frames — all that changed is `pocket`, from `bag` to `med`, and `value`,
to nothing. Nothing in the pipeline moved, which is the whole reason these two
were chosen over inventing a new pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How many cells. The number is the mechanic — see the header: one cell
#: removes the question altogether, and more of them turns "when do I spend"
#: into "which do I carry". Three is the current answer; the client reads it
#: off `welcome.config` and the hotkeys are derived from the belt's length, so
#: moving it moves the panel and the keys with it.
MEDICAL_SLOTS = 3


@dataclass(frozen=True)
class MedicalDef:
    """One kind of medicine. Keyed to its own `loot.ItemDef`, so the art,
    the name and the icon are already answered elsewhere."""

    key: str
    #: Points of health it puts back. FLAT, not a fraction, so a skill that
    #: raises the ceiling makes a kit worth proportionally less — which is the
    #: honest relationship between a bigger bar and a fixed bandage.
    heal: int
    #: Seconds the body is a puppet for. This is the entire cost of using one:
    #: standing still, in the open, unable to answer anything that walks up.
    use_time: float
    #: What carrying it does to the walk. Mirrors the catalog row's weight, so
    #: the two numbers cannot drift.
    weight: float


KITS: tuple[MedicalDef, ...] = (
    # THE SAFE HEAL. Nearly three seconds is a very long time in a dark forest
    # — long enough that using one is a decision about POSITION rather than
    # about health, which is what a heal in a game with no pause should be.
    MedicalDef("first_aid", heal=55, use_time=2.8, weight=1.0),
    # THE PANIC HEAL. Under a second, half the health, and light enough that
    # carrying one costs nothing you would notice. It is the answer to "it is
    # already on me", and it is deliberately not enough to survive being wrong
    # twice.
    MedicalDef("morphine", heal=30, use_time=0.9, weight=0.2),
)

BY_KEY: dict[str, MedicalDef] = {kit.key: kit for kit in KITS}
#: What `loot.ItemDef.pocket` says to route here.
POCKET = "med"


def is_medical(key: str) -> bool:
    return key in BY_KEY


def catalog_payload() -> dict:
    """Heal, duration and weight per kit, for `welcome.config`.

    The client needs all three: the duration drives the ring that fills over
    the player's head, the heal drives the hover card, and the weight is part
    of `Game.moveWeight`, which is rebuilt client-side.
    """
    return {
        kit.key: {"heal": kit.heal, "useTime": kit.use_time, "weight": kit.weight}
        for kit in KITS
    }


@dataclass
class Medical:
    """The cells. A cell holds a catalog KEY or nothing."""

    slots: list[str | None] = field(default_factory=lambda: [None] * MEDICAL_SLOTS)

    def __post_init__(self) -> None:
        # Defensive: a hydrated or hand-built loadout must still be exactly
        # `MEDICAL_SLOTS` long, or the client's cells and the server's list
        # disagree about which key is bound to which.
        if len(self.slots) < MEDICAL_SLOTS:
            self.slots += [None] * (MEDICAL_SLOTS - len(self.slots))
        elif len(self.slots) > MEDICAL_SLOTS:
            del self.slots[MEDICAL_SLOTS:]

    @property
    def weight(self) -> float:
        return sum(
            BY_KEY[key].weight for key in self.slots if key is not None and key in BY_KEY
        )

    @property
    def count(self) -> int:
        return sum(1 for key in self.slots if key is not None)

    def full(self) -> bool:
        return all(key is not None for key in self.slots)

    def first_empty(self) -> int | None:
        for index, key in enumerate(self.slots):
            if key is None:
                return index
        return None

    def add(self, key: str) -> bool:
        """Put one in the first empty cell. False when both are full.

        REFUSES RATHER THAN SWAPPING, unlike the belt's gun cells. A gun cell
        trades because a rifle and a pistol are alternatives; two kits are a
        QUANTITY, and silently dropping one to pick up another would be the
        game throwing away a resource the player was trying to stockpile.
        """
        if not is_medical(key):
            return False
        index = self.first_empty()
        if index is None:
            return False
        self.slots[index] = key
        return True

    def peek(self, index: int) -> str | None:
        if 0 <= index < len(self.slots):
            return self.slots[index]
        return None

    def take(self, index: int) -> str | None:
        """Empty a cell and hand back what was in it.

        Called on the frame a use COMPLETES, never on the frame it starts —
        a cancelled use must not have cost anything. See `Room._step_use`.
        """
        if 0 <= index < len(self.slots):
            key = self.slots[index]
            self.slots[index] = None
            return key
        return None

    def payload(self) -> list[str | None]:
        return list(self.slots)
