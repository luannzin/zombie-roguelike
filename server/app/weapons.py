"""Guns: catalog, hotbar, and the stats that make each one a different shot.

Loot on the ground is still `loot.py`. This is what a collected gun *is* —
damage, cadence, reach, weight, the laser, the AWP's hold-to-aim. Ammo
types are named here so the catalog is honest; magazines are a later
pass and nothing here spends a round.

The pocket (`inventory.py`) holds valuables. Guns live on a 3-slot
HOTBAR. They do not stack. 1/2/3 selects a slot; selecting the held
slot again holsters it. An empty hand does not fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import TILE_SIZE

HOTBAR_SLOTS = 3
STARTING_WEAPON = "glock18"

#: Named so a later magazine pass has somewhere to land. Unused today.
AMMO_PISTOL = "pistol"
AMMO_RIFLE = "rifle"
AMMO_AWP = "awp"

LASER_ALWAYS = "always"
LASER_ADS = "ads"


@dataclass(frozen=True)
class WeaponDef:
    key: str
    name: str
    #: pistol / rifle / sniper — presentation and the ammo it will eat.
    kind: str
    ammo: str
    damage: int
    #: Seconds between shots once the trigger is live.
    fire_cooldown: float
    range_tiles: float
    #: World-pixel offset of the muzzle along aim, from the body centre.
    muzzle_tiles: float
    #: How far the bang carries, in tiles. A pistol is not an AWP.
    noise_tiles: float
    #: Seconds the trigger must be held before the first shot. 0 = instant.
    aim_delay: float
    laser: str
    #: Absolute camera zoom while holding to shoot. 0 = do not change zoom.
    scope_zoom: float
    #: Body kick, world px, opposite aim.
    kick: float
    #: Camera trauma on fire.
    trauma: float
    #: Gun sprite punch: radians up, and pixels of slide back along aim.
    gun_kick: float
    gun_pump: float
    tracer_life: float
    #: Multiplier on the default tracer width.
    tracer_width: float
    flash: float
    casings: int
    light_radius: float
    light_life: float

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
        return {
            "name": self.name,
            "kind": self.kind,
            "ammo": self.ammo,
            "damage": self.damage,
            "fireCooldown": self.fire_cooldown,
            "range": self.range,
            "muzzle": self.muzzle,
            "noise": self.noise,
            "aimDelay": self.aim_delay,
            "laser": self.laser,
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
        muzzle_tiles=0.85,
        noise_tiles=12.0,
        aim_delay=0.0,
        laser=LASER_ALWAYS,
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
        muzzle_tiles=1.05,
        noise_tiles=18.0,
        aim_delay=0.0,
        laser=LASER_ALWAYS,
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
        muzzle_tiles=1.15,
        noise_tiles=16.0,
        aim_delay=0.0,
        laser=LASER_ALWAYS,
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
        muzzle_tiles=1.25,
        noise_tiles=17.0,
        aim_delay=0.0,
        laser=LASER_ALWAYS,
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
        muzzle_tiles=1.55,
        noise_tiles=24.0,
        aim_delay=0.38,
        laser=LASER_ADS,
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
)

BY_KEY: dict[str, WeaponDef] = {weapon.key: weapon for weapon in WEAPONS}


def catalog_payload() -> dict:
    """Combat stats the client needs to predict a shot and draw the gun."""
    return {weapon.key: weapon.client_payload() for weapon in WEAPONS}


@dataclass
class Hotbar:
    """Three gun slots. No stacking. `held` is -1 when the hand is empty."""

    cap: int = HOTBAR_SLOTS
    slots: list[str | None] = field(default_factory=list)
    held: int = 0

    def __post_init__(self) -> None:
        if len(self.slots) < self.cap:
            self.slots.extend([None] * (self.cap - len(self.slots)))
        elif len(self.slots) > self.cap:
            self.slots = self.slots[: self.cap]
        if self.held < -1 or self.held >= self.cap:
            self.held = -1

    @classmethod
    def starting(cls) -> Hotbar:
        bar = cls()
        bar.slots[0] = STARTING_WEAPON
        bar.held = 0
        return bar

    def add(self, key: str) -> int | None:
        """Put `key` in the first empty slot. None if unknown or full."""
        if key not in BY_KEY:
            return None
        for index, slot in enumerate(self.slots):
            if slot is None:
                self.slots[index] = key
                return index
        return None

    def can_stow(self, key: str) -> bool:
        if key not in BY_KEY:
            return False
        return any(slot is None for slot in self.slots)

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
    def weight(self) -> float:
        # Imported lazily: loot.ItemDef owns the kg number so a gun on the
        # ground and a gun in the hand are the same object.
        from .loot import BY_KEY as ITEMS

        total = 0.0
        for key in self.slots:
            if key is None:
                continue
            item = ITEMS.get(key)
            if item is not None:
                total += item.weight
        return total

    def to_payload(self) -> dict:
        return {
            "cap": self.cap,
            "slots": list(self.slots),
            "held": self.held,
        }
