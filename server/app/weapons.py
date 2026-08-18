"""Weapons: catalog, hotbar, and the stats that make each one a different hit.

Loot on the ground is still `loot.py`. This is what a bought weapon *is* —
damage, cadence, reach, weight, the AWP's hold-to-aim.

`ammo` names the CALIBRE each one eats, and it is load-bearing rather than
decorative: every shot spends a round out of the firing player's reserve
(`ammo.py`), and what the party is carrying decides which boxes the next
forest bothers to stock. The knife's `AMMO_NONE` is the exception that makes
the blade matter — it is the one weapon that never runs out.

GUNS ARE NOT FOUND. Every row here is `droppable=False` in the loot catalog:
the merchant is the only source (`store.py`), so a firearm is something the
party spent a night's extraction on rather than something the forest handed
them, and a calibre nobody paid for is a calibre nobody finds ammunition for.

The pocket (`inventory.py`) holds valuables. Weapons live on a 3-slot
HOTBAR: two gun cells and then ONE FIXED CELL holding the knife. Guns are
bought and swapped; the knife is neither, which is the point of it —
a run STARTS with no gun at all and the hand is still not empty.
1/2/3 selects a slot; selecting the held slot again holsters it.

A gun FIRES: one hitscan ray, one target, at whatever range the barrel
carries. The knife SWINGS: a short arc, no ray, and a three-step chain
(`slash`, `slash`, `cut`) that resets when the player stops. Cadence and
reach are the trade — a knife is quiet enough to kill without waking the
forest and short enough that using it is a decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import TILE_SIZE

#: Gun slots, then the knife after them. The knife's cell is `KNIFE_SLOT`
#: and nothing else may ever land in it. The belt is three cells total —
#: the blade takes one of them rather than adding a fourth, so carrying it
#: costs a gun slot instead of being free.
GUN_SLOTS = 2
KNIFE_SLOT = GUN_SLOTS
HOTBAR_SLOTS = GUN_SLOTS + 1
#: The one weapon nobody picks up, drops or loses — and the ONLY thing a
#: run starts with. There is no starting gun: the first one is something
#: you BUY, out of the first night's extraction, which is what makes owning
#: one an event and what makes the first shop mean something.
STARTING_MELEE = "knife"

#: The calibres. `ammo.py` owns the reserves, the caps and the boxes; these
#: three strings are the join between a weapon and the pile of rounds it eats.
AMMO_PISTOL = "pistol"
AMMO_RIFLE = "rifle"
AMMO_AWP = "awp"
#: A blade eats nothing, and saying so is cheaper than a null check.
AMMO_NONE = "none"

KIND_MELEE = "melee"

#: What a combo step reads as. `slash` is a sweep across the body; `cut` is
#: the finisher that goes through it. The client draws them differently and
#: the difference is the only reason the chain is legible.
STEP_SLASH = "slash"
STEP_CUT = "cut"


@dataclass(frozen=True)
class ComboStep:
    """One beat of a melee chain.

    `window` is what makes it a chain rather than a list: it is how long the
    NEXT step stays available after this one, and a player who stops swinging
    for longer than that starts again at the first slash. The finisher's
    window is deliberately 0 — the cut ends the chain, it does not loop into
    another one.
    """

    kind: str
    damage: int
    #: Seconds before anything may be swung again.
    cooldown: float
    #: How far the arc reaches from the body centre, in tiles.
    reach_tiles: float
    #: Full width of the arc, in degrees. The cut is wider than the slashes.
    arc_degrees: float
    #: Seconds the chain stays open after this step. 0 ends it.
    window: float
    #: How many bodies one swing may open. The slashes take one; the cut
    #: goes through everything in front of it, which is what it is for.
    max_targets: int
    #: Body lunge along aim, world px. A swing carries you into it.
    lunge: float
    #: Camera trauma when it lands.
    trauma: float
    #: Which way the arc travels: +1 or -1. The two slashes cross.
    sweep: int
    #: Radians the held sprite sweeps through the swing.
    swing: float
    #: How far the swing carries as sound, in tiles. Silent on a whiff.
    noise_tiles: float

    @property
    def reach(self) -> float:
        return TILE_SIZE * self.reach_tiles

    @property
    def noise(self) -> float:
        return TILE_SIZE * self.noise_tiles

    def client_payload(self) -> dict:
        return {
            "kind": self.kind,
            "damage": self.damage,
            "cooldown": self.cooldown,
            "reach": self.reach,
            "arcDegrees": self.arc_degrees,
            "window": self.window,
            "maxTargets": self.max_targets,
            "lunge": self.lunge,
            "trauma": self.trauma,
            "sweep": self.sweep,
            "swing": self.swing,
        }


@dataclass(frozen=True)
class MeleeDef:
    """The swinging half of a weapon. Absent on everything that shoots."""

    steps: tuple[ComboStep, ...]

    def step(self, index: int) -> ComboStep:
        """The step at `index`, wrapped. A chain that ran off the end restarts."""
        return self.steps[index % len(self.steps)]

    def client_payload(self) -> dict:
        return {"steps": [step.client_payload() for step in self.steps]}


@dataclass(frozen=True)
class WeaponDef:
    """One catalog row.

    Everything past `ammo` has a default because a knife has no tracer and a
    rifle has no arc. Filling a blade's `casings` with a zero to satisfy the
    dataclass would be a row that lies about what the thing is.
    """

    key: str
    name: str
    #: pistol / rifle / sniper / melee — presentation only.
    kind: str
    #: The calibre this eats, one per shot. `AMMO_NONE` never runs dry.
    ammo: str
    damage: int = 0
    #: Seconds between shots once the trigger is live.
    fire_cooldown: float = 0.0
    range_tiles: float = 0.0
    #: World-pixel offset of the muzzle along aim, from the body centre.
    muzzle_tiles: float = 0.0
    #: How far the bang carries, in tiles. A pistol is not an AWP.
    noise_tiles: float = 0.0
    #: Seconds the trigger must be held before the first shot. 0 = instant.
    aim_delay: float = 0.0
    #: Absolute camera zoom while holding to shoot. 0 = do not change zoom.
    scope_zoom: float = 0.0
    #: Body kick, world px, opposite aim.
    kick: float = 0.0
    #: Camera trauma on fire.
    trauma: float = 0.0
    #: Gun sprite punch: radians up, and pixels of slide back along aim.
    gun_kick: float = 0.0
    gun_pump: float = 0.0
    tracer_life: float = 0.0
    #: Multiplier on the default tracer width.
    tracer_width: float = 1.0
    flash: float = 0.0
    casings: int = 0
    light_radius: float = 0.0
    light_life: float = 0.0
    #: The swing. Set on melee weapons and None on everything else — it is
    #: what `Room.handle_attack` dispatches on, not the `kind` string.
    melee: MeleeDef | None = None

    @property
    def range(self) -> float:
        return TILE_SIZE * self.range_tiles

    @property
    def muzzle(self) -> float:
        return TILE_SIZE * self.muzzle_tiles

    @property
    def noise(self) -> float:
        return TILE_SIZE * self.noise_tiles

    def client_payload(self) -> dict:
        payload = {
            "name": self.name,
            "kind": self.kind,
            "ammo": self.ammo,
            "damage": self.damage,
            "fireCooldown": self.fire_cooldown,
            "range": self.range,
            "muzzle": self.muzzle,
            "noise": self.noise,
            "aimDelay": self.aim_delay,
            "scopeZoom": self.scope_zoom,
            "kick": self.kick,
            "trauma": self.trauma,
            "gunKick": self.gun_kick,
            "gunPump": self.gun_pump,
            "tracerLife": self.tracer_life,
            "tracerWidth": self.tracer_width,
            "flash": self.flash,
            "casings": self.casings,
            "lightRadius": self.light_radius,
            "lightLife": self.light_life,
        }
        # Omitted rather than nulled: every gun would otherwise carry a field
        # that only one weapon in the catalog has ever used.
        if self.melee is not None:
            payload["melee"] = self.melee.client_payload()
        return payload


# Cadence and punch are the identity. DPS is close on purpose so a pickup
# is a *feel* change, not a strict upgrade — except the AWP, which is a
# different weapon entirely.
WEAPONS: tuple[WeaponDef, ...] = (
    WeaponDef(
        key="glock18",
        name="Glock 18",
        kind="pistol",
        ammo=AMMO_PISTOL,
        damage=7,
        fire_cooldown=0.16,
        range_tiles=7.5,
        muzzle_tiles=0.62,
        noise_tiles=12.0,
        aim_delay=0.0,
        scope_zoom=0.0,
        kick=1.1,
        trauma=0.10,
        gun_kick=0.18,
        gun_pump=1.6,
        tracer_life=0.07,
        tracer_width=0.85,
        flash=0.7,
        casings=1,
        light_radius=52,
        light_life=0.07,
    ),
    WeaponDef(
        key="deagle",
        name="Desert Eagle",
        kind="pistol",
        ammo=AMMO_PISTOL,
        damage=24,
        fire_cooldown=0.72,
        range_tiles=9.5,
        muzzle_tiles=0.75,
        noise_tiles=18.0,
        aim_delay=0.0,
        scope_zoom=0.0,
        kick=3.2,
        trauma=0.28,
        gun_kick=0.42,
        gun_pump=3.8,
        tracer_life=0.12,
        tracer_width=1.55,
        flash=1.35,
        casings=1,
        light_radius=92,
        light_life=0.12,
    ),
    WeaponDef(
        key="famas",
        name="FAMAS",
        kind="rifle",
        ammo=AMMO_RIFLE,
        damage=9,
        fire_cooldown=0.11,
        range_tiles=11.0,
        muzzle_tiles=0.88,
        noise_tiles=16.0,
        aim_delay=0.0,
        scope_zoom=0.0,
        kick=1.6,
        trauma=0.13,
        gun_kick=0.14,
        gun_pump=2.1,
        tracer_life=0.08,
        tracer_width=1.0,
        flash=0.85,
        casings=1,
        light_radius=64,
        light_life=0.08,
    ),
    WeaponDef(
        key="ak47",
        name="AK-47",
        kind="rifle",
        ammo=AMMO_RIFLE,
        damage=12,
        fire_cooldown=0.13,
        range_tiles=12.0,
        muzzle_tiles=0.88,
        noise_tiles=17.0,
        aim_delay=0.0,
        scope_zoom=0.0,
        kick=2.2,
        trauma=0.17,
        gun_kick=0.22,
        gun_pump=2.6,
        tracer_life=0.09,
        tracer_width=1.15,
        flash=1.0,
        casings=1,
        light_radius=70,
        light_life=0.09,
    ),
    WeaponDef(
        key="awp",
        name="AWP",
        kind="sniper",
        ammo=AMMO_AWP,
        damage=55,
        fire_cooldown=1.55,
        range_tiles=22.0,
        muzzle_tiles=1.06,
        noise_tiles=24.0,
        aim_delay=0.38,
        # Integer step below arena zoom — see client/src/render/framing.ts.
        scope_zoom=3.0,
        kick=4.8,
        trauma=0.42,
        gun_kick=0.55,
        gun_pump=5.2,
        tracer_life=0.18,
        tracer_width=1.85,
        flash=1.6,
        casings=1,
        light_radius=110,
        light_life=0.16,
    ),
    # The knife is last in the catalog and last on the belt, and it is the
    # only row here with no ammo, no tracer and no light. Two quick slashes
    # that cross, then a cut that is slower, wider, hits everything in front
    # of it and is worth waiting for. Nothing in the chain is loud: a gun
    # wakes sixteen tiles of forest, the whole combo wakes five.
    #
    # It is also the weapon every run STARTS with, so its damage is a floor
    # rather than a benchmark: the whole chain lands under half a Glock's
    # dps, which is what keeps the first gun on the ground worth walking to.
    WeaponDef(
        key="knife",
        name="Faca",
        kind=KIND_MELEE,
        ammo=AMMO_NONE,
        # What an un-comboed hit is worth, for anything that reads `damage`
        # off the catalog without knowing about steps.
        damage=5,
        range_tiles=1.05,
        muzzle_tiles=0.5,
        noise_tiles=4.0,
        kick=0.0,
        trauma=0.06,
        melee=MeleeDef(
            steps=(
                ComboStep(
                    kind=STEP_SLASH,
                    damage=5,
                    cooldown=0.30,
                    reach_tiles=1.05,
                    arc_degrees=95.0,
                    window=0.55,
                    max_targets=1,
                    lunge=2.2,
                    trauma=0.07,
                    sweep=1,
                    swing=1.5,
                    noise_tiles=3.5,
                ),
                ComboStep(
                    kind=STEP_SLASH,
                    damage=6,
                    cooldown=0.28,
                    reach_tiles=1.1,
                    arc_degrees=105.0,
                    window=0.5,
                    max_targets=1,
                    lunge=2.6,
                    trauma=0.09,
                    # Back the other way, so the pair reads as one X and not
                    # as the same swing played twice.
                    sweep=-1,
                    swing=1.65,
                    noise_tiles=3.5,
                ),
                ComboStep(
                    kind=STEP_CUT,
                    # Still worth more than both slashes together — the
                    # finisher has to pay for the wind-up or the chain is
                    # something you interrupt rather than something you land.
                    damage=13,
                    # The price of the finisher. Long enough that whiffing it
                    # is a real mistake.
                    cooldown=0.62,
                    reach_tiles=1.35,
                    arc_degrees=130.0,
                    # Zero: the cut ENDS the chain rather than looping it.
                    window=0.0,
                    max_targets=3,
                    lunge=4.4,
                    trauma=0.2,
                    sweep=1,
                    swing=2.5,
                    noise_tiles=5.0,
                ),
            )
        ),
    ),
)

BY_KEY: dict[str, WeaponDef] = {weapon.key: weapon for weapon in WEAPONS}


def catalog_payload() -> dict:
    """Combat stats the client needs to predict a shot and draw the gun."""
    return {weapon.key: weapon.client_payload() for weapon in WEAPONS}


@dataclass
class Hotbar:
    """Three gun slots plus the knife. No stacking. `held` is -1 for an empty hand.

    The last cell is the knife's and it is not a slot in the sense the other
    three are: nothing may be stowed in it, nothing may push the knife out of
    it, and `__post_init__` puts the blade back if anything ever built a bar
    without one. A belt whose last cell could be emptied would make "you
    always have something" a thing the player has to check rather than know.
    """

    cap: int = HOTBAR_SLOTS
    slots: list[str | None] = field(default_factory=list)
    held: int = 0

    def __post_init__(self) -> None:
        if len(self.slots) < self.cap:
            self.slots.extend([None] * (self.cap - len(self.slots)))
        elif len(self.slots) > self.cap:
            self.slots = self.slots[: self.cap]
        if 0 <= KNIFE_SLOT < self.cap:
            self.slots[KNIFE_SLOT] = STARTING_MELEE
        if self.held < -1 or self.held >= self.cap:
            self.held = -1

    @classmethod
    def starting(cls) -> Hotbar:
        """A blade and two empty cells. `__post_init__` placed the knife."""
        bar = cls()
        bar.held = KNIFE_SLOT
        return bar

    def add(self, key: str) -> int | None:
        """Put `key` in the first empty GUN slot. None if unknown or full."""
        if key not in BY_KEY or key == STARTING_MELEE:
            return None
        for index in range(min(GUN_SLOTS, self.cap)):
            if self.slots[index] is None:
                self.slots[index] = key
                return index
        return None

    def can_stow(self, key: str) -> bool:
        if key not in BY_KEY or key == STARTING_MELEE:
            return False
        return any(self.slots[i] is None for i in range(min(GUN_SLOTS, self.cap)))

    def select(self, index: int) -> None:
        """Equip `index`, or holster it if it is already held."""
        if index < 0 or index >= self.cap:
            return
        if self.slots[index] is None:
            return
        self.held = -1 if self.held == index else index

    def apply_held(self, index: int) -> None:
        """Client-authored selection. Empty slots collapse to unarmed."""
        if index < 0 or index >= self.cap:
            self.held = -1
            return
        if self.slots[index] is None:
            self.held = -1
            return
        self.held = index

    def equipped(self) -> WeaponDef | None:
        if self.held < 0 or self.held >= self.cap:
            return None
        key = self.slots[self.held]
        if key is None:
            return None
        return BY_KEY.get(key)

    @property
    def held_weight(self) -> float:
        """Kilos of the weapon IN HAND. Zero when holstered.

        Only the held weapon has a weight the body pays, because only the
        held weapon is being carried in front of you — the rest of the belt
        is on the belt. The whole rack summed here is what used to make a
        third gun a movement decision, which quietly punished the player for
        picking things up in a game about picking things up.
        """
        # Imported lazily: loot.ItemDef owns the kg number so a gun on the
        # ground and a gun in the hand are the same object.
        from .loot import BY_KEY as ITEMS

        weapon = self.equipped()
        if weapon is None:
            return 0.0
        item = ITEMS.get(weapon.key)
        return item.weight if item is not None else 0.0

    def to_payload(self) -> dict:
        return {
            "cap": self.cap,
            "slots": list(self.slots),
            "held": self.held,
        }
