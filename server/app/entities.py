"""Authoritative entity state.

`Player` lives here; `Enemy` is its sibling in enemies.py and reuses the same
(x, capsule_y0, capsule_y1, radius, hp, alive) shape, so `combat.raycast`
targets both from one list.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from .config import (
    INVENTORY_SLOTS,
    MAX_HP,
    STAMINA_MAX,
    PLAYER_HALF_HEIGHT,
    PLAYER_HIT_RADIUS,
    SPRITE_HEIGHT,
    level_progress,
)
from .inventory import Inventory
from .medical import Medical
from .skills import Loadout
from .weapons import Hotbar

# Imported after `weapons` on purpose: `ammo` reads the weapon catalog to
# answer what calibre a key eats, so the module order here is the dependency.
from . import armor
from .ammo import Reserve

COLORS = [
    "#e6484f", "#f2a541", "#f6e05e", "#7bd389", "#3fb8af",
    "#4d9de0", "#8367c7", "#e07be0", "#f28482", "#57cc99",
    "#ff9f1c", "#8ecae6", "#c77dff", "#90be6d", "#ff6b6b",
]


@dataclass
class InputCmd:
    sequence: int = 0
    up: bool = False
    down: bool = False
    left: bool = False
    right: bool = False
    aim_x: float = 1.0
    aim_y: float = 0.0
    shoot: bool = False
    lantern: bool = False
    #: SHIFT. A REQUEST to run, not a state: what it actually buys is decided
    #: in `simulation.running` against the breath the body has left.
    sprint: bool = False
    #: Hotbar slot the client wants in hand. -1 is holstered.
    held: int = 0
    #: RIGHT MOUSE, held. A REQUEST to raise the shield, and like `sprint` it
    #: is nothing on its own: whether the shield is actually up is decided
    #: per tick against what is in the hand and whether it is still in one
    #: piece (`Player.blocking`). The second button in the game and the first
    #: one that is not the trigger.
    block: bool = False

    @staticmethod
    def from_message(msg: dict) -> "InputCmd":
        mv = msg.get("movement") or {}
        aim = msg.get("aim") or {}
        ax = float(aim.get("x", 1.0))
        ay = float(aim.get("y", 0.0))
        length = (ax * ax + ay * ay) ** 0.5
        if length > 1e-6:
            ax /= length
            ay /= length
        else:
            ax, ay = 1.0, 0.0
        try:
            held = int(msg.get("held", 0))
        except (TypeError, ValueError):
            held = 0
        return InputCmd(
            sequence=int(msg.get("sequence", 0)),
            up=bool(mv.get("up")),
            down=bool(mv.get("down")),
            left=bool(mv.get("left")),
            right=bool(mv.get("right")),
            aim_x=ax,
            aim_y=ay,
            shoot=bool(msg.get("shoot")),
            block=bool(msg.get("block")),
            lantern=bool(msg.get("lantern")),
            sprint=bool(msg.get("sprint")),
            held=held,
        )


#: THE POUR'S FOUR BEATS, and the phase is on the wire because every client in
#: the room draws the same ceremony over the same body: the walk up to the
#: skid, the pack coming off the back and turning over, the items falling out
#: of it one at a time, and the pack going back on. One integer buys all four —
#: the client runs its own clock inside a beat, and the beat it is in is the
#: only thing it cannot know for itself.
POUR_WALK, POUR_LIFT, POUR_DUMP, POUR_STOW = range(4)


@dataclass
class Pour:
    """One player emptying their pocket onto one platform, over time.

    Loading used to be instant: one press, the bag was empty, the meter jumped.
    That is a transaction, and extraction is the thing the whole night is for —
    so it is a PERFORMANCE now, and this is the state that performance runs on.
    It lives on the player rather than on the pad because it is a body doing
    something; the pad only counts what lands in it.

    A pour ENDS ONE WAY: the bag is empty. It cannot be cancelled and it has
    no ceiling — the press is the decision to give the night away, and once the
    pack is off the back the whole thing goes in whether that settles the quota
    or overshoots it. A load that stopped on the bill left the player holding
    half a bag at a machine they had already committed to, and a movement key
    that cancelled turned every pour into a thing you could fumble by leaning
    on W. The risk is still real and still priced — those seconds standing
    still in a dark forest are the cost — it is just no longer takeable back.
    """

    rift_id: str
    phase: int = POUR_WALK
    #: Seconds left in this beat — or, inside POUR_DUMP, until the next item.
    left: float = 0.0
    #: The mark in front of the deck this walks to. FEET, in world pixels.
    x: float = 0.0
    y: float = 0.0


#: What a `Use` channel IS. Two kinds today and the list is open.
#:
#: ONE CHANNEL FOR BOTH, rather than a second timer beside the first, because
#: everything about them is already identical: the body is a puppet, the server
#: owns the clock, movement is acked and ignored, a blow cancels, and the
#: client draws a ring filling over the head. The only thing that differs is
#: what happens on the last frame — which is one branch in `Room._step_use`
#: rather than a parallel system with its own cancel rule to get wrong.
USE_HEAL = "heal"
USE_CRATE = "crate"


@dataclass
class Use:
    """One player standing still doing something that takes real seconds.

    THE SAME SHAPE AS `Pour`, AND THAT IS DELIBERATE. Both are a body standing
    still doing something that takes real seconds, both are driven by the
    server's clock so the client can only ever draw what has already happened,
    and both are read by `step_players` before movement. A heal that resolved
    on the keypress would be a hotkey; a heal that takes three seconds in the
    open is a decision about where you are standing.

    IT DIFFERS FROM A POUR IN EXACTLY ONE WAY, AND IT IS THE IMPORTANT ONE: a
    pour spends as it goes, so being interrupted still costs you what already
    left the bag. A use spends NOTHING until it completes. Losing the kit AND
    the health to a wolf you did not hear would be punishing the player twice
    for one mistake, so an interrupted heal costs the seconds and keeps the
    item. `Medical.take` is therefore called on the last frame and never on
    the first.

    THE SAME RULE COVERS THE VAULT, and it is why forcing one is a gamble
    rather than a tax: an interrupted force costs the seconds and the NOISE
    (which went out at the start, on purpose) and leaves the object shut. The
    party can come back and try again, having spent nothing but the attention
    of everything that heard the first attempt.
    """

    #: `USE_HEAL` or `USE_CRATE`. Decides only what the LAST frame does.
    kind: str = USE_HEAL
    #: Which medical cell is being spent. Held rather than the key, because
    #: the cell is what has to be emptied and two cells can hold the same key.
    #: -1 when this channel is not a heal.
    slot: int = -1
    #: Which object is being forced, or "". Held rather than a reference so a
    #: crate that left the map mid-channel (it cannot today, but the room owns
    #: that question) resolves to a miss rather than to a stale object.
    target: str = ""
    #: Seconds left. The client draws a ring filling from `total`.
    left: float = 0.0
    total: float = 0.0


@dataclass
class Player:
    id: str
    name: str
    color: str
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    aim_x: float = 1.0
    aim_y: float = 0.0
    hp: int = MAX_HP
    alive: bool = True
    #: ON THE FLOOR, AND NOT COMING BACK ON A TIMER.
    #:
    #: `alive` says whether this body acts; `downed` says WHY it stopped, and
    #: the two are not the same question. A body killed in the camp or the shop
    #: is `alive=False` with a respawn timer running — a fumble, two seconds,
    #: it always worked that way. A body killed in a hostile zone is
    #: `alive=False` AND `downed`, with no timer at all: nothing brings it back
    #: except the party reaching the next zone, and if nobody is left standing
    #: to get them there the run is over (`Room._check_wipe`).
    #:
    #: It is a separate flag rather than "alive is false and respawn_timer is
    #: zero" because that reading is true for one tick of an ordinary death
    #: too, and a wipe check that fires on a rounding error is a run deleted by
    #: a float.
    downed: bool = False
    radius: float = PLAYER_HIT_RADIUS
    #: Breath. Spent by SHIFT, refilled by not holding it — the whole system is
    #: `simulation.step_stamina`, and it is on the body rather than in a side
    #: table because the client mirrors it to predict its own speed.
    stamina: float = STAMINA_MAX
    #: Spent the bar to zero. SHIFT is refused until `STAMINA_RECOVER` of it is
    #: back; a latch rather than a timer, so prediction can replay it.
    winded: bool = False

    kills: int = 0
    deaths: int = 0
    #: Lifetime xp; the level curve lives in config.level_progress.
    xp: int = 0
    gold: int = 0
    #: The pocket. Slots and weight; extraction will spend what is in it.
    inventory: Inventory = field(default_factory=lambda: Inventory(INVENTORY_SLOTS))
    #: Two gun cells plus the fixed knife cell. A run opens with no gun.
    hotbar: Hotbar = field(default_factory=Hotbar.starting)
    #: Rounds by calibre. Starts EMPTY, and stays empty for as long as the
    #: belt is: the first reserve in a run arrives with the first gun, out of
    #: the merchant's hands (`Reserve.grant_for`).
    ammo: Reserve = field(default_factory=Reserve)
    #: WHAT THIS BODY IS WEARING. Three slots, any of them empty, each with
    #: its own life left — see `armor.py`. A run opens with nothing on: the
    #: first plate is something the forest handed over or the merchant sold.
    armor: armor.Loadout = field(default_factory=armor.Loadout)
    #: The shield's own durability, or None when there is no shield on the
    #: belt. It is not on the `Hotbar` because a belt cell holds a KEY and
    #: this is state; it is not in `armor.Loadout` because you hold it rather
    #: than wear it. At most one, ever — `Hotbar.holds_shield`.
    shield: armor.Piece | None = None
    #: THE TWO MEDICAL CELLS, on keys 4 and 5. The fifth container, and the
    #: only source of health in the game — see `medical.py` for why medicine
    #: is not in the pocket. Costs no bag cell and does cost bag WEIGHT.
    medical: Medical = field(default_factory=Medical)
    #: How long the trigger has been held. AWP spends this before it fires.
    aim_hold: float = 0.0
    #: Which beat of the melee chain the next swing is. Never on the wire —
    #: the swing event carries the step it was, and that is what the client
    #: draws; a counter would only let the two disagree.
    combo_step: int = 0
    #: Seconds left to keep the chain. Runs out and the next swing is a first
    #: slash again.
    combo_left: float = 0.0
    #: THE SHIELD IS UP. Latched here rather than read off the input at every
    #: reader, because three things ask the question on different clocks —
    #: the walk (`simulation.step_player`), the blow
    #: (`Room.damage_player`) and the wire — and an input packet that has not
    #: arrived yet would make them disagree within one tick.
    blocking: bool = False
    #: What the walk is multiplied by right now because of the shield. 1.0
    #: whenever it is down.
    #:
    #: A RESOLVED NUMBER RATHER THAN A LOOKUP, because `simulation.py` is a
    #: line-for-line mirror of `simulation.ts` and the client cannot reach a
    #: `ShieldDef` from inside its movement code without importing the whole
    #: weapon catalog into prediction. Both sides decide the same thing in the
    #: same place — the frame the button is read — and the movement code just
    #: multiplies.
    block_speed: float = 1.0
    #: Seconds of drag left from the last blow that connected. While it is
    #: above zero the walk is multiplied by `HIT_STAGGER_SCALE`.
    #:
    #: A CLOCK RATHER THAN A RESOLVED MULTIPLIER, unlike `block_speed` beside
    #: it, and the difference is who owns the decision. The shield is decided
    #: by a button both sides can read on the frame it is pressed; a stagger is
    #: decided by a swing only the server can see land, so the number has to
    #: TRAVEL. It rides the tick row like `stamina` does, gets snapped on
    #: reconcile, and both `simulation.py` and `simulation.ts` tick it down the
    #: same way — which means the local body feels the drag about a round trip
    #: after the blow, and then predicts the rest of it exactly.
    stagger: float = 0.0

    # server bookkeeping (never sent verbatim)
    inputs: deque = field(default_factory=deque)
    last_input: InputCmd = field(default_factory=InputCmd)
    last_processed_seq: int = 0
    idle_ticks: int = 0
    fire_cooldown: float = 0.0
    respawn_timer: float = 0.0
    #: Melee i-frames — see MELEE_IMMUNITY in config.py.
    hurt_immunity: float = 0.0
    #: Camp only. Toggled by `{type:"ready"}` while standing at the fire.
    ready: bool = False
    #: What the levels bought. Stacks, the flattened `Mods` every other
    #: module multiplies by, and the spins still owed to the machine in the
    #: shop. It is the ONE place a player's own numbers diverge from
    #: `config.py`, which is why nothing here reads MAX_HP directly any more.
    skills: Loadout = field(default_factory=Loadout)
    #: Mid-pour, or None. While this is set the body is a puppet: input is
    #: acked and dropped, the walk is driven by `Room._step_pour`, and the only
    #: thing a key can still do is cancel.
    pour: "Pour | None" = None
    #: Mid-heal, or None. Same puppet rule as `pour`: input is acked and
    #: dropped and the walk is zero, but unlike a pour this one CAN be ended
    #: early — by a blow, and only by a blow — and ending it costs nothing but
    #: the time already spent.
    using: "Use | None" = None

    @property
    def max_hp(self) -> int:
        """This body's ceiling, which is no longer everybody's.

        `config.MAX_HP` is the value a run OPENS at; a skill moves it, so every
        heal, respawn and HUD bar reads this instead. A site that still reads
        the constant is a site where Couro Grosso silently does nothing.
        """
        return self.skills.mods.max_hp

    def reset_for_new_run(self) -> None:
        """Strip this body back to what a run OPENS with. Nothing survives.

        THE LIST IS EVERYTHING A NIGHT CAN GIVE YOU, and it is written out
        field by field rather than by rebuilding the `Player` because the id,
        the name, the colour and the socket bookkeeping have to survive — the
        person is still sitting there, it is their run that ended.

        The rule for what goes: if a night could have handed it over, it goes.
        The belt drops to a knife, the pocket empties, the reserve empties, the
        plate comes off, the shield is gone, the levels are gone and the xp
        that bought them is gone. `kills` and `deaths` are the only counters
        kept, because they are a record of the session rather than of the run.

        The PARTY's balance is not here: it is `Room.balance`, one number for
        the whole room, and `Room.wipe` clears it in the same breath.
        """
        self.hp = MAX_HP
        self.alive = True
        self.downed = False
        self.stamina = STAMINA_MAX
        self.winded = False
        self.xp = 0
        self.gold = 0
        self.inventory = Inventory(INVENTORY_SLOTS)
        self.hotbar = Hotbar.starting()
        self.ammo = Reserve()
        self.armor = armor.Loadout()
        self.shield = None
        self.skills = Loadout()
        self.pour = None
        self.medical = Medical()
        self.aim_hold = 0.0
        self.combo_step = 0
        self.combo_left = 0.0
        self.blocking = False
        self.block_speed = 1.0
        self.stagger = 0.0
        self.respawn_timer = 0.0
        self.hurt_immunity = 0.0
        self.ready = False
        self.vx = self.vy = 0.0
        self.inputs.clear()

    @property
    def capsule_y0(self) -> float:
        """Feet end of the vertical hit capsule (inset by radius)."""
        return self.y + PLAYER_HALF_HEIGHT - self.radius

    @property
    def capsule_y1(self) -> float:
        """Head end of the vertical hit capsule (inset by radius)."""
        return self.y + PLAYER_HALF_HEIGHT - SPRITE_HEIGHT + self.radius

    @property
    def carry_weight(self) -> float:
        """What the WALK carries: the bag, plus only the weapon in hand.

        Deliberately NOT the same number as the bag's own weight, and
        deliberately not the whole belt either. Two rules meet here:

          * weapons do not eat the bag's capacity — `inv.w` on the wire is
            the pocket alone, so `current / maxkg` answers "how much loot
            can I still carry out" and a rifle never makes that read as
            nearly full before you have picked anything up;
          * only what is in your hands slows you down, so swapping to the
            knife is a real way to move faster and a full rack is not a
            silent tax on having found things.

        MEDICINE IS THE FOURTH TERM and it breaks the second rule for the
        same reason armour does: two kits are not in your hands and they still
        slow you down, because that is the whole price of walking in stocked.
        It stays out of `inv.w` for the same reason too — a bandage is not
        cargo — so a party carrying medicine carries less loot out, which is
        where the greed trade went when medicine stopped being sellable.

        WORN ARMOUR IS THE THIRD TERM, and it breaks the second rule above
        on purpose: a plate is not in your hands, and it still slows you
        down, because that is the entire price of wearing one. It stays out
        of `inv.w` — the bag's bar answers "how much loot can I still carry
        out" and a helmet is not cargo — so the two numbers say two
        different true things about the same body.

        The client mirrors this sum from the same catalog — see
        `Game.moveWeight`.
        """
        return (
            self.inventory.weight
            + self.hotbar.held_weight
            + self.armor.weight
            + self.medical.weight
        )

    def snapshot_payload(self) -> dict:
        """What changes every tick. Everything else rides the roster.

        Positions need ≥4 decimals: wall snaps use EPS=1e-4, and round(_, 2)
        pushes right/down snaps onto the tile boundary so box_blocked flips
        true. Client reconcile then blocks the other axis (strafe "lag"
        while sliding down a wall; up/left were fine because +EPS rounds away).
        """
        weapon = self.hotbar.equipped()
        ads = (
            weapon is not None
            and weapon.aim_delay > 0.0
            and self.last_input.shoot
            and self.aim_hold > 0.0
        )
        row = {
            "id": self.id,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
            "ax": round(self.aim_x, 3),
            "ay": round(self.aim_y, 3),
            # This player's own input ack. It lives on the row rather than at
            # the top of the snapshot so one serialisation serves every socket.
            "seq": self.last_processed_seq,
            "lantern": self.last_input.lantern,
            "hp": self.hp,
            "alive": self.alive,
            # DOWN, rather than merely not alive. The client draws a body on
            # the floor instead of an absence, and the HUD counts how many of
            # the party are still up — which is the only warning anybody gets
            # that the run is one blow from over.
            "down": self.downed,
            # Not identity, but it has to land the moment it flips: it is what
            # the campfire's ready count is counting.
            "ready": self.ready,
            "held": self.hotbar.held,
            "ads": ads,
            # Breath. It is on the TICK row and not the roster because it moves
            # every tick a key is down, and because every client draws the bar
            # under the health bar over every body — not only its own.
            "st": round(self.stamina, 1),
        }
        # THE DRAG, and it is on the tick row for the same two reasons the
        # breath is: it moves every tick it exists, and every client draws it —
        # a staggered body lurches whoever is looking at it. Omitted when zero,
        # which is almost always.
        if self.stagger > 0.0:
            row["sg"] = round(self.stagger, 2)
        # THE SHIELD IS UP, and it is on the TICK row rather than the roster
        # because it is a POSE: every client draws a raised shield over every
        # body that has one up, and a five-hertz pose would let a player watch
        # a blow land on a shield that had not come up yet. Omitted when down,
        # which is almost always — the same trade `wind` makes.
        if self.blocking:
            row["blk"] = True
        # Omitted while there is breath left, which is almost always: it is the
        # exhaustion LATCH, and a false on every row all night costs more than
        # the moment it describes.
        if self.winded:
            row["wind"] = True
        # Omitted for everybody who is not pouring, which is everybody almost
        # all of the time — this is a per-tick row and a field that is null for
        # eight players costs more than the one it describes.
        if self.pour is not None:
            row["pour"] = self.pour.phase
        # MID-HEAL, as a FRACTION rather than as seconds left. The client draws
        # a ring filling over the body, and a ring wants 0..1 — shipping the
        # remaining time would make every client divide by a duration it would
        # have to look up per kit, on a field that is absent almost always.
        #
        # It is on the tick row and not the roster because every client draws
        # it over every body: a teammate standing still with a ring closing
        # over their head is the clearest "do not expect them for two seconds"
        # this game can give, and at roster rate it would arrive half spent.
        if self.using is not None and self.using.total > 0.0:
            row["use"] = round(1.0 - max(0.0, self.using.left) / self.using.total, 3)
            # WHICH KIND OF CHANNEL, so the ring can be the right colour.
            #
            # Sent only for the non-default kind, like every other conditional
            # field on this row: a heal is by far the commoner of the two and
            # paying a string for it thirty times a second to say "the usual"
            # would be the whole saving thrown away. A green ring over somebody
            # forcing a vault would read as healing, which is the one thing it
            # must not — a teammate you think is topping up is a teammate you
            # do not walk over to cover.
            if self.using.kind != USE_HEAL:
                row["uk"] = self.using.kind
        return row

    def to_payload(self) -> dict:
        """The whole player: `welcome`, and the snapshot roster."""
        level, into_level, to_level = level_progress(self.xp)
        row = {
            **self.snapshot_payload(),
            "name": self.name,
            "color": self.color,
            "kills": self.kills,
            "deaths": self.deaths,
            "xp": self.xp,
            "gold": self.gold,
            # Pre-split so the client never re-implements the xp curve.
            "level": level,
            "xpInLevel": into_level,
            "xpToLevel": to_level,
            # Skills ride the ROSTER, not the tick. They change once a day, in
            # a shop, in front of a machine — five times a second is already
            # four and a half more than that moment needs.
            "skills": self.skills.to_payload(),
            "spins": self.skills.spins,
            # The flattened numbers the OWNER's client mirrors: it predicts its
            # own movement and carry scale and draws its own health bar, so a
            # ceiling it had to guess at would be a bar that reads wrong for
            # exactly the frames somebody just changed it.
            "mods": self.skills.mods.payload(),
            # `w` is the POCKET's own weight and nothing else. The number the
            # walk actually reads adds the weapon in hand, and the client
            # rebuilds that from this plus `guns` against the same catalog
            # rather than being sent a second field that would be stale for
            # the frames its own hotbar selection is ahead of the server's.
            "inv": self.inventory.to_payload(),
            "guns": self.hotbar.to_payload(),
            # Rounds by calibre. On the ROSTER rather than the snapshot: the
            # client predicts its own trigger off this the same way it
            # predicts movement, so five times a second is a resync, not the
            # counter. Every calibre is present, including the zeroes.
            "ammo": self.ammo.to_payload(),
            # WHAT THIS BODY IS WEARING, and every client needs it rather than
            # only the owner: armour is DRAWN (`DrawableEntity.gear`), so a
            # teammate's helmet is a thing you can see from across a clearing.
            # Worn slots only — an empty slot is an absent key.
            "armor": self.armor.to_payload(),
            # THE TWO MEDICAL CELLS. On the ROSTER and not the tick row: they
            # change when somebody picks a kit up or spends one, which is a
            # handful of times a night, and two strings thirty times a second
            # would buy nothing. Same call `armor` and `guns` are here on.
            "med": self.medical.payload(),
        }
        # The shield's life. Omitted when there is no shield on the belt,
        # which is most bodies in most runs.
        if self.shield is not None:
            row["shield"] = self.shield.to_payload()
        return row


#: Longest name the roster can show without truncating. Also the cap that keeps
#: a hand-written query string from becoming a broadcast payload.
MAX_NAME_LENGTH = 16


def random_name(taken: set[str]) -> str:
    for _ in range(50):
        name = f"Player{random.randint(100, 999)}"
        if name not in taken:
            return name
    return f"Player{random.randint(1000, 999999)}"


def clean_name(raw: str | None, taken: set[str]) -> str:
    """Sanitise a player-supplied name. Returns "" when nothing usable is left.

    The name arrives in a query string and is echoed to every other player in
    the room, so it is trimmed to printable characters and a fixed length here
    rather than anywhere downstream. Collisions get a numeric suffix: two
    friends both called "ana" must still be two readable rows in the roster.
    """
    if not raw:
        return ""
    name = "".join(c for c in raw.strip() if c.isprintable())[:MAX_NAME_LENGTH].strip()
    if not name:
        return ""
    if name not in taken:
        return name
    for n in range(2, 100):
        suffix = f" {n}"
        candidate = name[: MAX_NAME_LENGTH - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
    return ""


def pick_color(taken: set[str]) -> str:
    """An unused swatch if one is left, otherwise any. Colour is lobby identity."""
    free = [c for c in COLORS if c not in taken]
    return random.choice(free or COLORS)
