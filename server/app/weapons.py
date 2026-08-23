"""Weapons: catalog, hotbar, and the stats that make each one a different hit.

Loot on the ground is still `loot.py`. This is what a bought weapon *is* —
damage, cadence, reach, weight, the AWP's hold-to-aim.

THE ZOMBIE IS THE UNIT, AND EVERY NUMBER BELOW IS DERIVED FROM IT
================================================================
Nothing in this catalog is a hand-picked damage figure any more. The whole
ladder is generated from CS2's published stat block by four functions —
`dmg`, `cadence`, `reach`, `loudness` — and one scale factor:

    DAMAGE_SCALE = ZOMBIE_HP / CS_PLAYER_HP  ==  30 / 100

which is chosen so that **a zombie takes exactly what an unarmoured CS2
player takes**. Four Glock rounds, three AK rounds, two Deagle rounds, one
AWP round: the shots-to-kill column of the source table survives the port
unchanged. That is the point of anchoring on the weakest creature in the
game rather than on a tuned number — the weakest creature is the only thing
a player ever measures a new gun against, so it is the only honest unit, and
a rebalance is now a change to ONE constant instead of to twelve rows.

The knife is anchored the same way (`KNIFE_CHAIN_SHARE`): a full chain is
most of a zombie and never all of one, so the blade always leaves you
holding a swing you have to survive to throw.

WHAT THE SOURCE TABLE DOES *NOT* CARRY, AND WHAT REPLACED IT
CS2 balances its cheap fast guns with recoil and spread, and this game has
neither: a top-down hitscan has no wrist. Three axes carry that weight here
instead, and they are why a Glock does not simply obsolete an AK:

  * ROUNDS PER KILL. Every shot spends a round (`ammo.py`), so the ladder
    that actually matters is damage per round: 4 rounds a zombie on a Glock,
    3 on an AK, 2 on a Deagle, 1 on an AWP. The reserve caps are sized in
    KILLS, not in seconds of trigger, so an upgrade buys you a longer night
    rather than a bigger number.
  * NOISE. `loudness` scales with the round, and the two SUPPRESSED weapons
    (`usp_s`, `m4a1s` — the S is the whole product) cut it by nearly half.
    That is the CS2 identity ported to a game where sound is the enemy AI's
    only long-range sense, and it is what makes a $200 pistol a real answer
    on a night somebody wants to stay unnoticed.
  * WEIGHT. Derived from CS2's own running-speed column (`carry_weight`),
    so the gun that slows you there slows you here.

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

THREE WAYS A TRIGGER RESOLVES, and the catalog says which:

  * ONE RAY. The default. `pellets == 1`, fires the instant the cooldown is
    up, one hitscan, one target.
  * A CONE. `pellets > 1` — the shotgun. One trigger pull spends one SHELL
    and casts `pellets` rays inside `spread_degrees`, each carrying
    `damage`. Reach is short and the cone is fixed in ANGLE, so distance
    thins the pattern on its own and a shell is a decision about how close
    you are willing to be.
  * ON RELEASE. `fire_on_release` — the AWP. Holding the trigger scopes
    (`scope_zoom`) and NEVER fires; letting go is the shot, and only if the
    hold lasted `aim_delay`. A sniper you have to commit to and then let go
    of is the only weapon in the game whose input is a sentence rather than
    a word, and it is what stops the AWP being a Deagle that reaches.

The knife SWINGS: a short arc, no ray, and a three-step chain (`slash`,
`slash`, `cut`) that resets when the player stops. Cadence and reach are the
trade — a knife is quiet enough to kill without waking the forest and short
enough that using it is a decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import armor
from .config import TILE_SIZE
from .enemies import ZOMBIE

#: Gun slots, then the BLADE after them. The belt is three cells total —
#: the lâmina takes one of them rather than adding a fourth, so carrying
#: steel costs a gun slot instead of being free.
#:
#: THE BLADE CELL CANNOT BE EMPTIED, AND THAT IS THE WHOLE INVARIANT. What
#: it holds changed — a better lâmina replaces what is in it — but that it
#: holds SOMETHING never does. The guarantee a player learns on their first
#: screen is "the hand is never empty", not "the hand always holds a knife",
#: and the second one was only ever an implementation of the first.
GUN_SLOTS = 2
BLADE_SLOT = GUN_SLOTS
HOTBAR_SLOTS = GUN_SLOTS + 1
#: What the cell falls back to. The floor of the floor: a run opens holding
#: this, a blade lost or traded away leaves this behind, and no roll, table
#: or corpse can ever produce a second one. There is no starting gun — the
#: first firearm is something you BUY, out of the first night's extraction,
#: which is what makes owning one an event and what makes the first shop
#: mean something.
STARTING_MELEE = "knife"

# --- the scale ---------------------------------------------------------------

#: The weakest creature in the game, and therefore the unit of damage. Read
#: off the stat block rather than typed, so raising a zombie's health
#: rebalances every gun in the catalog in the same motion.
ZOMBIE_HP = ZOMBIE.max_hp
#: What the source table's damage column is measured against.
CS_PLAYER_HP = 100
#: The one number this whole file turns on. See the module docstring.
DAMAGE_SCALE = ZOMBIE_HP / CS_PLAYER_HP

#: The heaviest round in the game, used to normalise recoil and muzzle feel.
#: The AWP's chest number, before scaling.
AWP_CHEST = 115

#: Metres of CS2 "accurate range" -> tiles of hitscan reach.
#:
#: A base plus a slope rather than a straight multiply, because the source
#: numbers span 3.4 m to 69 m and a linear port would give the shotgun a
#: single tile and the AWP half the map. The base is what every weapon can
#: reach regardless; the slope is what the accuracy column buys on top.
#: The cap is the lantern's reach doubled — past that nothing is lit and the
#: ray is arriving somewhere nobody can see.
RANGE_BASE_TILES = 4.0
RANGE_PER_METRE = 0.30
RANGE_MAX_TILES = 22.0

#: How far a bang carries, in tiles: a floor plus the round's weight. The
#: floor is what a gun going off in a forest costs you no matter how small
#: it is, which is most of why the knife exists.
NOISE_BASE_TILES = 9.5
NOISE_PER_DAMAGE = 0.42
#: What a can on the end of the barrel is worth. Not silence — a suppressed
#: rifle still wakes more forest than a blade — but close to halving the
#: circle is enough to change which route a party takes.
SUPPRESSED_NOISE = 0.55

#: CS2 dollars -> this game's catalog VALUE, the number `store.price_of`
#: marks up and the number a night's extraction is measured against.
#:
#: A CURVE, not a division, and the two anchors are what the curve is for.
#: `GUN_PRICE_BASE` dollars has to land on `GUN_VALUE_BASE`, because day one
#: asks for forty points and that whole take is meant to buy the cheapest
#: sidearm in the shop (`rift.night_need`, and the note in AGENTS.md). The
#: AWP has to land near four hundred, because that is the wall the economy
#: is built to make a party stare at for four nights. An exponent under one
#: is what connects those two without making everything in between either
#: free or unreachable — the source table's dollar spread is 24x and this
#: game's night-to-night income spread is nothing like that wide.
GUN_PRICE_BASE = 200
GUN_VALUE_BASE = 40
GUN_VALUE_CURVE = 0.73

#: CS2's running-speed column -> kilos in the hand.
#:
#: The source table already ranks these weapons by how much they slow you
#: down, and this game already has a system that does exactly that
#: (`config.CARRY_*`, and `Hotbar.held_weight`). Porting the column instead
#: of inventing a second opinion means the gun that is heavy over there is
#: heavy here, and it costs one linear map. The base is what the LIGHTEST
#: firearm weighs — deliberately above the knife's, so switching to the
#: blade is still a real way to move faster.
GUN_SPEED_BASE = 250
GUN_WEIGHT_BASE = 0.9
GUN_WEIGHT_PER_SPEED = 0.106


def dmg(chest: int) -> int:
    """CS2 unarmoured CHEST damage, scaled onto the zombie.

    Chest and not head, because this game has no hitboxes: a capsule is a
    capsule, and the torso number is the one a CS2 player would recognise as
    "what it does". Rounded half-up, which is what keeps the shots-to-kill
    column identical to the source (an AK's 35 must land on 11, not 10, or a
    zombie takes four rounds where a player takes three).
    """
    return max(1, int(chest * DAMAGE_SCALE + 0.5))


def cadence(rpm: float) -> float:
    """Rounds per minute -> seconds between shots. Straight from the table."""
    return round(60.0 / rpm, 3)


def reach(metres: float) -> float:
    """CS2 accurate range in metres -> hitscan reach in tiles."""
    return round(min(RANGE_MAX_TILES, RANGE_BASE_TILES + metres * RANGE_PER_METRE), 2)


def loudness(damage: int, suppressed: bool = False) -> float:
    """How far the report carries, in tiles."""
    tiles = NOISE_BASE_TILES + damage * NOISE_PER_DAMAGE
    return round(tiles * (SUPPRESSED_NOISE if suppressed else 1.0), 1)


def feel(damage: int, punch: float = 1.0) -> dict:
    """Recoil, tracer and muzzle numbers off the weight of the round.

    ONE CURVE FOR ELEVEN GUNS. Every field here used to be authored per
    weapon, which meant rows of arbitrary numbers nobody could check against
    each other — and which drifted the moment a damage figure moved. They are
    all functions of how hard the round hits relative to the heaviest one in
    the game, so a new catalog row arrives already feeling like it belongs on
    the same belt.

    `punch` is the ONE piece of character left, and it is deliberately not
    derivable: a Desert Eagle kicks harder than its damage says and an SMG
    kicks less than its cadence says, because that is what those weapons are
    famous for. Keep it inside 0.7..1.3 — past that the curve stops being the
    thing setting the feel and the multiplier starts being it.
    """
    p = damage / dmg(AWP_CHEST)
    return {
        "kick": round((0.55 + p * 4.2) * punch, 2),
        "trauma": round(min(0.55, (0.055 + p * 0.36) * punch), 3),
        "gun_kick": round((0.09 + p * 0.46) * punch, 3),
        "gun_pump": round((0.9 + p * 4.3) * punch, 2),
        "tracer_life": round(0.055 + p * 0.12, 3),
        "tracer_width": round(0.72 + p * 1.10, 2),
        "flash": round((0.60 + p * 1.00) * punch, 2),
        "light_radius": round(44 + p * 66),
        "light_life": round(0.06 + p * 0.10, 3),
    }


def catalog_value(cs_price: int) -> int:
    """CS2 dollars -> what one of these is worth on the loot catalog."""
    if cs_price <= 0:
        return 0
    ratio = cs_price / GUN_PRICE_BASE
    return max(1, round(GUN_VALUE_BASE * ratio**GUN_VALUE_CURVE))


def carry_weight(cs_speed: int) -> float:
    """CS2 running speed -> kilos the body pays for holding it."""
    slowdown = max(0, GUN_SPEED_BASE - cs_speed)
    return round(GUN_WEIGHT_BASE + slowdown * GUN_WEIGHT_PER_SPEED, 1)


#: The calibres. `ammo.py` owns the reserves, the caps and the boxes; these
#: strings are the join between a weapon and the pile of rounds it eats.
#:
#: Five of them, and the split is by what the weapon IS rather than by what
#: the round measures: an SMG that ate pistol rounds would drain a sidearm's
#: reserve at 850 rpm, and a shell that stacked with anything would make the
#: one weapon in the game with a per-shot economy share somebody else's.
AMMO_PISTOL = "pistol"
AMMO_SMG = "smg"
AMMO_RIFLE = "rifle"
AMMO_SHELL = "shell"
AMMO_AWP = "awp"
#: A blade eats nothing, and saying so is cheaper than a null check.
AMMO_NONE = "none"

KIND_MELEE = "melee"
#: The one thing on the belt that does not attack. See `ShieldDef`.
KIND_SHIELD = "shield"

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
    #: HALF-WIDTH of the blade's travel, in radians.
    #:
    #: It is half of `arc_degrees` and that is not a coincidence: the held
    #: sprite TRACKS the drawn white path edge for edge (`entity-visuals.ts`
    #: runs the same easing `drawSwings` does), so a value disagreeing with
    #: the arc would put the steel somewhere the path is not. This used to be
    #: a free number and the blade used to just tilt up and fall back, which
    #: is what a recoiling pistol does, not what a swung knife does.
    swing: float
    #: Seconds the blade takes to travel the arc, wind-up included. Shorter
    #: than `cooldown`, so the follow-through has somewhere to land before
    #: the next beat is legal.
    swing_time: float
    #: World px the grip is thrust out along the blade at mid-swing. The cut
    #: is a lunge and reads as one; a slash barely leaves the body.
    swing_thrust: float
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
            "swingTime": self.swing_time,
            "swingThrust": self.swing_thrust,
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
class ShieldDef:
    """The blocking half of a belt item. Absent on everything that attacks.

    THE THIRD THING A BELT CELL CAN HOLD. A gun fires, a lâmina swings, and a
    shield does neither — `Room.handle_attack` dispatches on which block the
    row carries, never on the `kind` string, exactly as it already did for
    the blade. That is why this is a block and not a flag: a second shield is
    a catalog row and no code.

    Every number is `armor.py`'s. What lives here is only the fact that you
    select it off the belt instead of wearing it.
    """

    #: Points of damage it eats before it comes apart.
    hp: int
    #: Full width of the protected arc, in degrees, centred on the aim.
    arc_degrees: float
    #: What the walk is multiplied by while it is up. See `armor.SHIELD_SPEED`.
    speed: float

    @property
    def half_arc_cos(self) -> float:
        """cos of the half-arc: the dot product a blow has to clear.

        Precomputed because `Room.damage_player` is on the hot path and the
        alternative is an `acos` per blow to compare an angle to a constant.
        """
        return math.cos(math.radians(self.arc_degrees) / 2)

    def client_payload(self) -> dict:
        return {
            "hp": self.hp,
            "arcDegrees": self.arc_degrees,
            "speed": self.speed,
        }


@dataclass(frozen=True)
class WeaponDef:
    """One catalog row.

    Everything past `ammo` has a default because a knife has no tracer and a
    rifle has no arc. Filling a blade's `casings` with a zero to satisfy the
    dataclass would be a row that lies about what the thing is.
    """

    key: str
    name: str
    #: pistol / smg / shotgun / rifle / sniper / melee — presentation only.
    kind: str
    #: The calibre this eats, one per TRIGGER PULL (not per pellet).
    #: `AMMO_NONE` never runs dry.
    ammo: str
    #: THE TWO SOURCE COLUMNS THIS FILE DOES NOT SPEND ITSELF. Price and
    #: running speed are combat-adjacent rather than combat: the economy
    #: (`loot.ItemDef.value` -> `store.price_of`) and the carry system
    #: (`Hotbar.held_weight`) read them through `catalog_value` and
    #: `carry_weight`. They live on the weapon anyway, because keeping the
    #: whole ported stat block in one row is the only way a reader can check
    #: it against the source — and because a gun whose price lived in one
    #: file and whose damage lived in another is a gun that gets rebalanced
    #: in half.
    cs_price: int = 0
    cs_speed: int = GUN_SPEED_BASE
    #: Damage of ONE ray. On a shotgun that is one pellet — `shot_damage`
    #: below is what a whole shell is worth against a single body.
    damage: int = 0
    #: Rays cast per trigger pull. 1 everywhere but the shotgun.
    pellets: int = 1
    #: Full width of the pellet cone, in degrees. Meaningless at 1 pellet.
    spread_degrees: float = 0.0
    #: Seconds between shots once the trigger is live.
    fire_cooldown: float = 0.0
    range_tiles: float = 0.0
    #: World-pixel offset of the muzzle along aim, from the body centre.
    muzzle_tiles: float = 0.0
    #: How far the bang carries, in tiles. A pistol is not an AWP.
    noise_tiles: float = 0.0
    #: Seconds the trigger must be held before the shot is legal. 0 = instant.
    aim_delay: float = 0.0
    #: RELEASE IS THE SHOT. With this set the weapon never fires while the
    #: button is down, however long it is held — it fires on the frame the
    #: button comes UP, and only if the hold reached `aim_delay`. See
    #: `Room.handle_attack`.
    fire_on_release: bool = False
    #: Absolute camera zoom while holding to shoot. 0 = do not change zoom.
    scope_zoom: float = 0.0
    #: Playback rate for the shot sample. Below 1 is a bigger gun; the
    #: catalog has one gunshot and eleven weapons, and pitch is what makes
    #: a Deagle and a P90 stop being the same event.
    shot_pitch: float = 1.0
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
    #: The block. Set on shields and None on everything else. A row with this
    #: has no trigger at all: it is held up, not fired.
    shield: ShieldDef | None = None

    @property
    def range(self) -> float:
        return TILE_SIZE * self.range_tiles

    @property
    def muzzle(self) -> float:
        return TILE_SIZE * self.muzzle_tiles

    @property
    def noise(self) -> float:
        return TILE_SIZE * self.noise_tiles

    @property
    def shot_damage(self) -> int:
        """What ONE trigger pull is worth against one body, all pellets in.

        The number a player would quote for the weapon. `damage` is a ray.
        """
        return self.damage * self.pellets

    @property
    def rounds_per_kill(self) -> int:
        """Trigger pulls this weapon needs to put one zombie down.

        The ladder the ammunition economy is actually built on — see
        `RESERVE_MAX`. A blade returns 0: it never spends anything.
        """
        if self.ammo == AMMO_NONE or self.shot_damage <= 0:
            return 0
        return max(1, math.ceil(ZOMBIE_HP / self.shot_damage))

    @property
    def value(self) -> int:
        """What the loot catalog says one is worth.

        TWO LADDERS, AND THE ROW SAYS WHICH IT IS ON. A firearm is priced off
        the CS2 dollar column (`catalog_value`); a lâmina has no such column
        and is priced off what its chain does (`blade_value`). They meet here
        rather than at every reader, because `store.price_of`, the stock sort
        and the loot catalog all ask this one question and none of them
        should have to know which kind of weapon it is asking about.
        """
        if self.shield is not None:
            return armor.shield_value()
        if self.melee is not None:
            return blade_value(BLADE_BY_KEY[self.key])
        return catalog_value(self.cs_price)

    @property
    def weight(self) -> float:
        """Kilos in the hand. See `carry_weight` and `blade_weight`."""
        if self.shield is not None:
            return armor.shield_weight()
        if self.melee is not None:
            return blade_weight(BLADE_BY_KEY[self.key])
        return carry_weight(self.cs_speed)

    def client_payload(self) -> dict:
        payload = {
            "name": self.name,
            "kind": self.kind,
            "ammo": self.ammo,
            "damage": self.damage,
            "pellets": self.pellets,
            "spreadDegrees": self.spread_degrees,
            "shotDamage": self.shot_damage,
            "fireCooldown": self.fire_cooldown,
            "range": self.range,
            "muzzle": self.muzzle,
            "noise": self.noise,
            "aimDelay": self.aim_delay,
            "fireOnRelease": self.fire_on_release,
            "scopeZoom": self.scope_zoom,
            "shotPitch": self.shot_pitch,
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
        if self.shield is not None:
            payload["shield"] = self.shield.client_payload()
        return payload


# --- the blades --------------------------------------------------------------
#
# THE KNIFE IS THE UNIT, EXACTLY AS THE ZOMBIE IS THE UNIT FOR GUNS.
#
# A blade is not a firearm and there is no published stat block to port, so
# the ladder is anchored on the one melee weapon this game has always had.
# Every lâmina below is the knife's own chain — its three beats, its splits,
# its windows — scaled by SEVEN character columns, and nothing else. That is
# what keeps a katana and a hatchet comparable: they are the same swing seen
# through different multipliers, so "is this better than what I am holding"
# is a question about seven numbers rather than about thirty.
#
# The knife's own profile is all ones, which is not a convenience — it is the
# check. A generator that could not reproduce the weapon it was derived from
# would be a second opinion about the swing, and the swing is tuned.

#: What a WHOLE chain — slash, slash, cut — takes off a zombie, on the KNIFE.
#:
#: Under one, and that is the entire design of the weapon. A chain that
#: killed would make the blade a rotation you execute; a chain that lands on
#: nine tenths leaves you standing in front of something still alive with
#: your cooldown spent, which is the moment the knife is actually about.
#: Every other blade in the game is measured as a multiple of it, and the
#: ones that go past 1.0 are exactly the ones that stopped being a last
#: resort and started being a weapon.
KNIFE_CHAIN_SHARE = 0.9
#: How the chain is split. The finisher is worth more than both slashes
#: together or it is something you get interrupted out of rather than
#: something you land. Shared by every blade — the SHAPE of a chain is the
#: category's identity; what changes between blades is its size.
KNIFE_SPLIT = (0.22, 0.26, 0.52)
#: Kilos of the lightest blade there is. Every lâmina is under the lightest
#: firearm (`GUN_WEIGHT_BASE`) on purpose: switching to steel has to stay a
#: real way to move faster, whatever steel you switched to.
KNIFE_WEIGHT = 0.5
#: What one knife is worth on the loot catalog. It is never sold and never
#: dropped, so this number only ever appears in a tooltip — but it is the
#: anchor the whole blade price ladder hangs off, so it lives here rather
#: than typed into `loot.py` where it used to be.
KNIFE_VALUE = 12

#: THE KNIFE'S OWN CHAIN, as the base every blade is scaled from.
#:
#: `(cooldown, reach_tiles, arc_degrees, window, max_targets, lunge, trauma,
#:   sweep, swing_time, swing_thrust, noise_tiles)`
#:
#: Two slashes that cross — the second sweeps the other way, so the pair
#: reads as one X and not as the same swing played twice — and then a cut
#: that is slower, wider, opens more than one body and ENDS the chain
#: (`window` 0). The finisher's cooldown is the price of whiffing it.
_CHAIN: tuple[tuple[float, float, float, float, int, float, float, int, float, float, float], ...] = (
    (0.30, 1.05, 95.0, 0.55, 1, 2.2, 0.07, 1, 0.17, 2.0, 3.5),
    (0.28, 1.10, 105.0, 0.50, 1, 2.6, 0.09, -1, 0.16, 2.4, 3.5),
    (0.62, 1.35, 130.0, 0.00, 3, 4.4, 0.20, 1, 0.26, 4.2, 5.0),
)

#: The widest a swing may be. Past a half-turn an arc stops reading as a
#: swing and starts reading as an aura: everything behind you is inside it,
#: and the player can no longer tell which way they were facing when it
#: landed. The axe is the only blade that comes near it.
ARC_MAX_DEGREES = 170.0


@dataclass(frozen=True)
class BladeProfile:
    """One lâmina, as seven multipliers on the knife.

    Nothing here is a damage number, a cooldown or a reach — they are all
    RATIOS, so the tuning that made the knife's swing feel like a swing is
    inherited rather than re-litigated per weapon. A blade authored by typing
    absolute numbers into a `ComboStep` would drift out of the category the
    first time the base chain was retuned.
    """

    key: str
    name: str
    #: What a whole chain takes off a zombie. THE headline number and the one
    #: the ladder is really about: under 1.0 the blade cannot finish what it
    #: started, over 1.0 it can.
    share: float
    #: How far the arc reaches. A katana is a longer weapon than a hatchet
    #: and the game has to say so before anybody reads a tooltip.
    reach: float = 1.0
    #: How wide it sweeps. Reach is who you can touch; arc is how many.
    arc: float = 1.0
    #: Cadence. ABOVE ONE IS SLOWER — it multiplies cooldowns and the time
    #: the steel spends travelling, so a heavy blade is heavy to hold as well
    #: as to be hit by.
    tempo: float = 1.0
    #: Lunge, camera trauma and the mid-swing thrust: how much of the body
    #: goes into it. Pure feel, and the only column that touches no rule.
    heft: float = 1.0
    #: How far the swing carries as sound. Every blade is quieter than every
    #: gun — that is the category — but an axe burying itself in something is
    #: not a knife opening it.
    noise: float = 1.0
    #: Extra bodies the FINISHER opens, on top of the knife's three. Only the
    #: wide blades get one: it is the reward for the arc, not a free stat.
    targets: int = 0


#: A blade's worth, and it is derived from what the blade DOES rather than
#: picked off a feel for what a katana ought to cost.
#:
#: Two things make one lâmina better than another and both are in the
#: profile: how fast the chain comes round (share per second of chain), and
#: how much ground one chain covers (reach, and how many bodies the finisher
#: opens). Multiply them, take the ratio against the knife, and raise it —
#: the exponent is what stops a blade that is forty percent better costing
#: forty percent more, which is not how anybody values the difference between
#: a weapon that finishes a zombie and one that does not.
BLADE_VALUE_CURVE = 2.4
#: What one extra body on the finisher is worth against one more of reach.
#: A quarter: an arc that opens a fourth body is real, and it is not the
#: same order of thing as being able to touch something a tile further away.
BLADE_CROWD_SHARE = 0.25


def blade_power(profile: BladeProfile) -> float:
    """Throughput times ground covered. The one ranking of blades there is."""
    seconds = sum(step[0] for step in _CHAIN) * profile.tempo
    crowd = 1.0 + profile.targets * BLADE_CROWD_SHARE
    return (profile.share / seconds) * profile.reach * crowd * math.sqrt(profile.arc)


def blade_value(profile: BladeProfile) -> int:
    """What one is worth on the loot catalog. See `BLADE_VALUE_CURVE`."""
    base = blade_power(BLADES[0])
    if base <= 0:
        return KNIFE_VALUE
    ratio = blade_power(profile) / base
    return max(1, round(KNIFE_VALUE * ratio**BLADE_VALUE_CURVE))


def blade_weight(profile: BladeProfile) -> float:
    """Kilos in the hand. Heft and length, both damped.

    Damped because a blade twice the weapon is not twice the burden — a
    katana is long rather than dense — and because the whole category has to
    stay under the lightest firearm for the knife's oldest promise to hold.
    """
    return round(KNIFE_WEIGHT * profile.heft**0.7 * profile.reach**0.5, 1)


def _blade_melee(profile: BladeProfile) -> MeleeDef:
    """The knife's three beats, seen through one profile's seven columns."""
    chain = round(ZOMBIE_HP * profile.share)
    steps: list[ComboStep] = []
    for index, base in enumerate(_CHAIN):
        (
            cooldown, reach_tiles, arc_degrees, window, max_targets,
            lunge, trauma, sweep, swing_time, swing_thrust, noise_tiles,
        ) = base
        arc = min(ARC_MAX_DEGREES, arc_degrees * profile.arc)
        steps.append(
            ComboStep(
                kind=STEP_CUT if index == len(_CHAIN) - 1 else STEP_SLASH,
                damage=max(1, int(chain * KNIFE_SPLIT[index] + 0.5)),
                cooldown=round(cooldown * profile.tempo, 3),
                reach_tiles=round(reach_tiles * profile.reach, 2),
                arc_degrees=round(arc, 1),
                # The WINDOW does not scale with tempo. It is how long the
                # player has to decide, and a slower blade that also gave you
                # longer to think would be slower for free.
                window=window,
                # Only the finisher takes the crowd column: a slash that
                # opened three bodies would make the chain's own shape
                # pointless.
                max_targets=max_targets + (profile.targets if window == 0.0 else 0),
                lunge=round(lunge * profile.heft, 2),
                trauma=round(trauma * profile.heft, 3),
                sweep=sweep,
                # HALF THE ARC, IN RADIANS, AND DERIVED RATHER THAN TYPED.
                # The held sprite tracks the drawn white path edge for edge
                # (`entity-visuals.ts` runs the same easing `drawSwings`
                # does), so a value disagreeing with the arc would put the
                # steel somewhere the path is not. It used to be a free
                # number on every step that agreed with the arc by hand.
                swing=round(math.radians(arc) / 2, 3),
                swing_time=round(swing_time * profile.tempo, 3),
                swing_thrust=round(swing_thrust * profile.heft, 2),
                noise_tiles=round(noise_tiles * profile.noise, 1),
            )
        )
    return MeleeDef(steps=tuple(steps))


#: EVERY LÂMINA, and the knife is first because it is the unit.
#:
#: The ladder is one column — `share` — and the rest is character. Under 1.0
#: the blade leaves you standing in front of something still alive; over it,
#: the chain finishes what it started, which is the single largest thing that
#: happens to a run that has been living on the knife.
BLADES: tuple[BladeProfile, ...] = (
    # THE FLOOR. Every run opens holding this and nothing takes it away: it
    # is the guarantee that the hand is never empty, so its damage is a floor
    # rather than a benchmark. A full chain lands at about a third of a
    # Glock's dps, which is what keeps the first gun in the shop worth saving
    # for. All ones by definition — see the section header.
    BladeProfile(key="knife", name="Faca", share=KNIFE_CHAIN_SHARE),
    # THE AXE. What the logging crew left behind, and the first blade most
    # parties will ever hold: a common find rather than a purchase. Slow
    # enough that a whiffed finisher is a real mistake, wide enough that the
    # finisher is how you answer three of them at once, and the loudest thing
    # in the category — still under half a pistol shot, because quiet is what
    # the category IS.
    BladeProfile(
        key="axe", name="Machado", share=1.7,
        reach=0.95, arc=1.25, tempo=1.35, heft=1.6, noise=1.5, targets=1,
    ),
    # THE KATANA. The rare one. Long, fast and narrow — everything the axe is
    # not — so the two never obsolete each other: the axe answers a crowd and
    # the katana answers the one thing that got close before you heard it.
    # Its chain kills outright and comes round in a second, which is a
    # sidearm's job done silently, and the price says so.
    BladeProfile(
        key="katana", name="Katana", share=1.5,
        reach=1.5, arc=0.85, tempo=0.85, heft=1.15, noise=1.15,
    ),
)

BLADE_BY_KEY: dict[str, BladeProfile] = {b.key: b for b in BLADES}


def _blade_rows() -> tuple[WeaponDef, ...]:
    """Every lâmina as a catalog row.

    APPENDED AFTER THE GUNS and in `BLADES` order, so the knife keeps the
    index it has always had on the held-weapon atlas and every frame already
    committed stays where it is.
    """
    rows: list[WeaponDef] = []
    for profile in BLADES:
        melee = _blade_melee(profile)
        rows.append(
            WeaponDef(
                key=profile.key,
                name=profile.name,
                kind=KIND_MELEE,
                ammo=AMMO_NONE,
                # What an un-comboed hit is worth, for anything that reads
                # `damage` off the catalog without knowing about steps.
                damage=melee.steps[0].damage,
                range_tiles=melee.steps[0].reach_tiles,
                muzzle_tiles=0.5,
                noise_tiles=melee.steps[-1].noise_tiles,
                kick=0.0,
                trauma=round(0.06 * profile.heft, 3),
                melee=melee,
            )
        )
    return tuple(rows)


# Cadence and punch are the identity. Everything below is generated from the
# CS2 stat block by the four functions at the top of this file — the only
# hand-written numbers left on a gun row are `muzzle_tiles` (where the barrel
# tip is, which is art), `casings`, `shot_pitch`, `punch` (character) and the
# shotgun's cone.
#
# ORDERED BY CLASS, cheapest inside each class — pistols, SMGs, the shotgun,
# rifles, the sniper — and the held-gun atlas, the loot atlas and the audio
# pitch ladder all keep this order, so a catalog row and a sprite are never
# out of step. The SHOP does not: `store.STOCK_ORDER` sorts by price, because
# a shelf is a ladder of what you can afford and a sheet is a ladder of what
# things are.
WEAPONS: tuple[WeaponDef, ...] = (
    # --- pistols --------------------------------------------------------------
    # $200. Four rounds a zombie, the fastest sidearm on the belt, and the
    # cheapest thing in the shop: this is what a party's first night buys.
    WeaponDef(
        key="glock18",
        name="Glock 18",
        kind="pistol",
        ammo=AMMO_PISTOL,
        cs_price=200,
        cs_speed=250,
        damage=dmg(29),
        fire_cooldown=cadence(400),
        range_tiles=reach(20.05),
        muzzle_tiles=0.62,
        noise_tiles=loudness(dmg(29)),
        shot_pitch=1.12,
        casings=1,
        **feel(dmg(29), punch=0.9),
    ),
    # $200, and the same price is the whole question. Three rounds a zombie
    # instead of four, slower, and SUPPRESSED — it wakes barely more forest
    # than a blade does. The Glock is what you buy to fight; this is what you
    # buy to not have to.
    WeaponDef(
        key="usp_s",
        name="USP-S",
        kind="pistol",
        ammo=AMMO_PISTOL,
        cs_price=200,
        cs_speed=240,
        damage=dmg(34),
        fire_cooldown=cadence(352),
        range_tiles=reach(23.81),
        muzzle_tiles=0.80,
        noise_tiles=loudness(dmg(34), suppressed=True),
        shot_pitch=1.24,
        casings=1,
        **feel(dmg(34), punch=0.78),
    ),
    # $300. Two barrels, one trigger: the highest sidearm dps in the game and
    # the shortest sidearm reach, which is exactly the trade the pair makes.
    WeaponDef(
        key="dual_berettas",
        name="Berettas Duplas",
        kind="pistol",
        ammo=AMMO_PISTOL,
        cs_price=300,
        cs_speed=240,
        damage=dmg(37),
        fire_cooldown=cadence(500),
        range_tiles=reach(16.93),
        muzzle_tiles=0.68,
        noise_tiles=loudness(dmg(37)),
        shot_pitch=1.06,
        # Two slides, two cases in the air.
        casings=2,
        **feel(dmg(37), punch=0.92),
    ),
    # $700. TWO ROUNDS A ZOMBIE, and that is what the price buys — not dps,
    # ammunition. A full pistol reserve is a hundred and twenty kills on this
    # and sixty on the Glock.
    WeaponDef(
        key="deagle",
        name="Desert Eagle",
        kind="pistol",
        ammo=AMMO_PISTOL,
        cs_price=700,
        cs_speed=230,
        damage=dmg(52),
        fire_cooldown=cadence(267),
        range_tiles=reach(24.58),
        muzzle_tiles=0.75,
        noise_tiles=loudness(dmg(52)),
        shot_pitch=0.86,
        casings=1,
        **feel(dmg(52), punch=1.25),
    ),
    # --- submachine guns ------------------------------------------------------
    # $1400. The first thing on the shelf that empties a magazine's worth of
    # noise into a clearing. Huge cadence, poor reach, and it eats its own
    # calibre — an SMG that shared the pistol reserve would drain a sidearm.
    WeaponDef(
        key="mp7",
        name="MP7",
        kind="smg",
        ammo=AMMO_SMG,
        cs_price=1400,
        cs_speed=220,
        damage=dmg(28),
        fire_cooldown=cadence(750),
        range_tiles=reach(14.38),
        muzzle_tiles=0.82,
        noise_tiles=loudness(dmg(28)),
        shot_pitch=1.18,
        casings=1,
        **feel(dmg(28), punch=0.8),
    ),
    # $2350. The fastest trigger in the game and the second-shortest reach.
    # A P90 answers a pack standing on top of you and nothing else.
    WeaponDef(
        key="p90",
        name="P90",
        kind="smg",
        ammo=AMMO_SMG,
        cs_price=2350,
        cs_speed=230,
        damage=dmg(25),
        fire_cooldown=cadence(857),
        range_tiles=reach(10.40),
        muzzle_tiles=0.86,
        noise_tiles=loudness(dmg(25)),
        shot_pitch=1.3,
        casings=1,
        **feel(dmg(25), punch=0.72),
    ),
    # --- shotgun --------------------------------------------------------------
    # $2000, and the only weapon in the catalog that resolves as a CONE.
    #
    # Six pellets of six inside a twenty-degree spread. Every pellet on one
    # body is thirty-six damage — a zombie, exactly, in one shell — and the
    # cone is fixed in ANGLE, so it thins itself with distance: at the edge
    # of its reach the pattern is wider than a body and a shell buys you a
    # wound instead of a kill. Nothing about that is a falloff curve; it is
    # geometry, which is why it reads without a tooltip.
    #
    # The reserve is counted in SHELLS and it is the smallest in the game.
    # That is what makes the weapon a decision: sixty answers to "something
    # is already touching me", and no answer at all to anything further off.
    WeaponDef(
        key="xm1014",
        name="XM1014",
        kind="shotgun",
        ammo=AMMO_SHELL,
        cs_price=2000,
        cs_speed=215,
        damage=dmg(20),
        pellets=6,
        spread_degrees=20.0,
        fire_cooldown=cadence(171),
        range_tiles=reach(3.39),
        muzzle_tiles=0.92,
        # The whole shell is what the forest hears, not one pellet.
        noise_tiles=loudness(dmg(20) * 6),
        shot_pitch=0.72,
        casings=1,
        **feel(dmg(20) * 6, punch=1.05),
    ),
    # --- rifles ---------------------------------------------------------------
    # $1950. The cheap rifle: four rounds a zombie like the Glock, at six
    # hundred and sixty a minute. What the price buys is the CADENCE.
    WeaponDef(
        key="famas",
        name="FAMAS",
        kind="rifle",
        ammo=AMMO_RIFLE,
        cs_price=1950,
        cs_speed=220,
        damage=dmg(30),
        fire_cooldown=cadence(666),
        range_tiles=reach(18.61),
        muzzle_tiles=0.88,
        noise_tiles=loudness(dmg(30)),
        shot_pitch=1.08,
        casings=1,
        **feel(dmg(30), punch=0.86),
    ),
    # $2700. Three rounds a zombie and the loudest thing short of a sniper.
    # The AK is the line where a party stops rationing and starts fighting.
    WeaponDef(
        key="ak47",
        name="AK-47",
        kind="rifle",
        ammo=AMMO_RIFLE,
        cs_price=2700,
        cs_speed=215,
        damage=dmg(35),
        fire_cooldown=cadence(600),
        range_tiles=reach(21.74),
        muzzle_tiles=0.88,
        noise_tiles=loudness(dmg(35)),
        shot_pitch=0.94,
        casings=1,
        **feel(dmg(35), punch=1.08),
    ),
    # $2900. The AK's cadence, a little more damage, more reach — and a CAN
    # on the end of it. It costs more than the AK for one reason and the
    # reason is that a night spent shooting it is a night the forest half
    # slept through.
    WeaponDef(
        key="m4a1s",
        name="M4A1-S",
        kind="rifle",
        ammo=AMMO_RIFLE,
        cs_price=2900,
        cs_speed=225,
        damage=dmg(37),
        fire_cooldown=cadence(600),
        range_tiles=reach(28.22),
        muzzle_tiles=1.0,
        noise_tiles=loudness(dmg(37), suppressed=True),
        shot_pitch=1.02,
        casings=1,
        **feel(dmg(37), punch=0.82),
    ),
    # --- sniper ---------------------------------------------------------------
    # $4750, one round a zombie, twice the reach of anything else — and the
    # only trigger in the game you have to LET GO of. Holding scopes the
    # camera out and never fires; release does, and only after the hold has
    # lasted `aim_delay`. That turns the weapon into a commitment with a
    # visible wind-up instead of a Deagle that reaches across the map.
    WeaponDef(
        key="awp",
        name="AWP",
        kind="sniper",
        ammo=AMMO_AWP,
        cs_price=4750,
        cs_speed=200,
        damage=dmg(AWP_CHEST),
        fire_cooldown=cadence(41),
        range_tiles=reach(69.27),
        muzzle_tiles=1.06,
        noise_tiles=loudness(dmg(AWP_CHEST)),
        aim_delay=0.34,
        fire_on_release=True,
        # Integer step below arena zoom — see client/src/render/framing.ts.
        scope_zoom=3.0,
        shot_pitch=0.68,
        casings=1,
        **feel(dmg(AWP_CHEST), punch=1.12),
    ),
)

#: THE SHIELDS. One for now, and the row is the whole feature.
#:
#: A police riot shield: the one thing in the shop that is not a way to hurt
#: something. It costs a GUN CELL, which is the price — a party member behind
#: one is a party member who is not shooting — and it only answers what is in
#: front of them, which is what makes standing behind one a formation rather
#: than a stance.
SHIELDS: tuple[WeaponDef, ...] = (
    WeaponDef(
        key="riot_shield",
        name="Escudo policial",
        kind=KIND_SHIELD,
        ammo=AMMO_NONE,
        shield=ShieldDef(
            hp=armor.shield_hp(),
            arc_degrees=armor.SHIELD_ARC_DEGREES,
            speed=armor.SHIELD_SPEED,
        ),
    ),
)

#: THE WHOLE CATALOG: the guns above, then every lâmina, then the shields.
#:
#: Appended and never inserted — the held-weapon atlas, the loot atlas and
#: the audio pitch ladder all key off this order, so a row that moved would
#: move every committed frame index with it. The knife is the first blade for
#: the same reason it always was the last row: it is the one that was already
#: there.
WEAPONS = WEAPONS + _blade_rows() + SHIELDS


BY_KEY: dict[str, WeaponDef] = {weapon.key: weapon for weapon in WEAPONS}

#: Every gun, in catalog order. `store.STOCK_ORDER` re-sorts this by price
#: and `store.STOCK_UNLOCK` gates it by day, so adding a weapon to the
#: catalog above is the only place a new gun has to be named.
GUN_KEYS: tuple[str, ...] = tuple(
    w.key for w in WEAPONS if w.melee is None and w.shield is None
)

#: Every lâmina, in catalog order. Derived off the `melee` block for the same
#: reason `Room.handle_attack` dispatches on it: what makes a weapon a blade
#: is that it swings, not that somebody typed "melee" into a `kind` field.
BLADE_KEYS: tuple[str, ...] = tuple(w.key for w in WEAPONS if w.melee is not None)

#: Every shield, in catalog order.
SHIELD_KEYS: tuple[str, ...] = tuple(w.key for w in WEAPONS if w.shield is not None)


def is_blade(key: str | None) -> bool:
    """Whether `key` belongs in the blade cell rather than in a gun cell."""
    if key is None:
        return False
    weapon = BY_KEY.get(key)
    return weapon is not None and weapon.melee is not None


def is_shield(key: str | None) -> bool:
    """Whether `key` is a shield. Shields ride a GUN cell — that is the price."""
    if key is None:
        return False
    weapon = BY_KEY.get(key)
    return weapon is not None and weapon.shield is not None

#: Every calibre anything in the catalog actually eats, in catalog order.
#: Derived, so a weapon whose calibre nothing else uses brings its reserve,
#: its box and its HUD counter with it and no list anywhere needs editing.
AMMO_TYPES: tuple[str, ...] = tuple(
    dict.fromkeys(w.ammo for w in WEAPONS if w.ammo != AMMO_NONE)
)


# --- how much ammunition a reserve holds -------------------------------------
#
# THE SIZING LIVES HERE AND THE MECHANICS LIVE IN `ammo.py`, and the split is
# not arbitrary: how many rounds a calibre holds is a QUESTION ABOUT THE
# WEAPONS THAT EAT IT — you cannot answer it without knowing what a round is
# worth against a zombie — while the reserve itself, the boxes on the floor
# and who is allowed to pick one up are about the room. `ammo.py` imports
# these three tables and owns everything else.
#
# A RESERVE IS COUNTED IN KILLS, NOT IN SECONDS OF TRIGGER. The old caps were
# sized so every calibre gave about thirty seconds of continuous fire, which
# sounds fair and is not: thirty seconds of P90 is twenty-one zombies and
# thirty seconds of Deagle is sixty-six, so the cheap fast gun quietly had a
# third of the ammunition economy of the expensive slow one. Sizing on kills
# says the thing the design actually wants to say — a full reserve is a
# night's worth of answers, whatever you are holding — and it lets the
# per-weapon difference stay where it belongs, in rounds per kill, where an
# upgrade buys you a LONGER night rather than a bigger number.

#: Zombies a full reserve is worth to the weakest weapon that eats it.
KILLS_PER_RESERVE = 60
#: The sniper's, and it is half on purpose. An AWP round is a kill wherever
#: it lands, so a full reserve at the standard number would be sixty
#: guaranteed corpses in a bag that also has to fit everything else.
SNIPER_KILLS_PER_RESERVE = 30
#: What a bought gun arrives with, as a share of the cap. Enough that a
#: purchase is immediately usable — walking into a night unable to fire the
#: thing you just saved four days for would make the shop feel broken — and
#: little enough that the first night with a new gun still has to find a box.
STARTING_SHARE = 1 / 3
#: What one box on the floor is worth, as a share of the cap. Six boxes fill
#: an empty reserve, which is about what one forest scatters.
BOX_SHARE = 1 / 6


def _reserve_cap(calibre: str) -> int:
    """Rounds of `calibre` a player may hold.

    Sized against the HUNGRIEST weapon that eats it, so the entry-level gun
    of a calibre is the one that gets `KILLS_PER_RESERVE` and everything
    above it in the same family gets more. That is the shape an upgrade
    should have: the AK does not carry more rounds than the FAMAS, it gets
    more nights out of the same box.
    """
    hunger = max(
        (w.rounds_per_kill for w in WEAPONS if w.ammo == calibre),
        default=1,
    )
    kills = SNIPER_KILLS_PER_RESERVE if calibre == AMMO_AWP else KILLS_PER_RESERVE
    return hunger * kills


#: How much a player may hold, per calibre.
RESERVE_MAX: dict[str, int] = {c: _reserve_cap(c) for c in AMMO_TYPES}
#: What a gun arrives with when the merchant hands it over.
STARTING_ROUNDS: dict[str, int] = {
    c: max(1, round(cap * STARTING_SHARE)) for c, cap in RESERVE_MAX.items()
}
#: What one box on the ground is worth. `loot.py` reads this onto the
#: catalog row, so the box the player picks up and the cap it fills are the
#: same decision written once.
BOX_ROUNDS: dict[str, int] = {
    c: max(1, round(cap * BOX_SHARE)) for c, cap in RESERVE_MAX.items()
}


def catalog_payload() -> dict:
    """Combat stats the client needs to predict a shot and draw the gun."""
    return {weapon.key: weapon.client_payload() for weapon in WEAPONS}


@dataclass
class Hotbar:
    """Two gun cells plus the BLADE cell. No stacking. `held` is -1 for an empty hand.

    The last cell is the lâmina's and it is not a slot in the sense the other
    two are: no gun may be stowed in it, nothing may empty it, and
    `__post_init__` puts a blade back if anything ever built a bar without
    one. A belt whose last cell could be emptied would make "you always have
    something" a thing the player has to check rather than know.

    WHAT IT HOLDS DOES CHANGE. A better blade REPLACES what is in the cell —
    that is the one way steel is upgraded, and the guarantee survives it
    because the replacement lands on the same frame the old one leaves. The
    knife is the floor under that, not the contents of the cell: trade an axe
    for a katana and the axe hits the floor, but trade the KNIFE for anything
    and nothing hits the floor at all, because the knife was never an object
    the party owned. It is the promise that the cell is full.
    """

    cap: int = HOTBAR_SLOTS
    slots: list[str | None] = field(default_factory=list)
    held: int = 0

    def __post_init__(self) -> None:
        if len(self.slots) < self.cap:
            self.slots.extend([None] * (self.cap - len(self.slots)))
        elif len(self.slots) > self.cap:
            self.slots = self.slots[: self.cap]
        if 0 <= BLADE_SLOT < self.cap:
            # Whatever is in the cell has to BE a blade, and the cell has to
            # be full. Anything else — empty, a gun that got in there, a key
            # from a save that no longer exists — falls back to the floor.
            if not is_blade(self.slots[BLADE_SLOT]):
                self.slots[BLADE_SLOT] = STARTING_MELEE
        if self.held < -1 or self.held >= self.cap:
            self.held = -1

    @classmethod
    def starting(cls) -> Hotbar:
        """A knife and two empty cells. `__post_init__` placed the blade."""
        bar = cls()
        bar.held = BLADE_SLOT
        return bar

    @property
    def blade(self) -> str:
        """The lâmina in the blade cell. Never None — see `__post_init__`."""
        if 0 <= BLADE_SLOT < self.cap:
            return self.slots[BLADE_SLOT] or STARTING_MELEE
        return STARTING_MELEE

    def holds_shield(self) -> bool:
        """Whether a shield is already on the belt. At most one, ever.

        Not a technical limit — the durability lives on the body
        (`Player.shield`) and a second one would need a second field — but a
        design one first: nobody carries two riot shields, and a belt holding
        two of them is a belt with no guns on it at all.
        """
        return any(is_shield(key) for key in self.slots)

    def add(self, key: str) -> int | None:
        """Put `key` where it belongs. None if unknown, or if there is no room.

        A BLADE ALWAYS HAS ROOM, because its cell is never empty and picking
        one up is a replacement rather than a stow. What it displaces is the
        caller's problem — `Room.collect_loot` puts the old lâmina on the
        floor, unless it was the knife, which is not an object.
        """
        if key not in BY_KEY:
            return None
        if is_shield(key) and self.holds_shield():
            return None
        if is_blade(key):
            if key == self.blade or not 0 <= BLADE_SLOT < self.cap:
                return None
            self.slots[BLADE_SLOT] = key
            return BLADE_SLOT
        for index in range(min(GUN_SLOTS, self.cap)):
            if self.slots[index] is None:
                self.slots[index] = key
                return index
        return None

    def can_stow(self, key: str) -> bool:
        if key not in BY_KEY:
            return False
        if is_shield(key) and self.holds_shield():
            return False
        if is_blade(key):
            # A duplicate of what is already in the cell is refused: it would
            # be a pickup that changed nothing and dropped the thing it
            # replaced, which reads as the game taking something off you.
            return key != self.blade
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
