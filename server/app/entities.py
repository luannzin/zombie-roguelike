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
    PLAYER_HALF_HEIGHT,
    PLAYER_HIT_RADIUS,
    SPRITE_HEIGHT,
    level_progress,
)
from .inventory import Inventory
from .skills import Loadout
from .weapons import Hotbar

# Imported after `weapons` on purpose: `ammo` reads the weapon catalog to
# answer what calibre a key eats, so the module order here is the dependency.
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
    #: Hotbar slot the client wants in hand. -1 is holstered.
    held: int = 0

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
            lantern=bool(msg.get("lantern")),
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

    A pour ENDS ITSELF (bag empty, or the quota settled when it started under
    one) and any movement key cancels it. There is no way to be stuck in one:
    it is a few seconds standing still in a dark forest, and the player has to
    be able to take that back the instant something walks out of the trees.
    """

    rift_id: str
    phase: int = POUR_WALK
    #: Seconds left in this beat — or, inside POUR_DUMP, until the next item.
    left: float = 0.0
    #: The mark in front of the deck this walks to. FEET, in world pixels.
    x: float = 0.0
    y: float = 0.0
    #: Value still owed to the quota when this press started, or 0 for a pour
    #: with no ceiling — the pad is already paid and this is an overfeed, which
    #: takes the whole bag.
    cap: int = 0
    #: What has gone in on this press. Only ever read against `cap`.
    paid: int = 0


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
    radius: float = PLAYER_HIT_RADIUS

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
    #: How long the trigger has been held. AWP spends this before it fires.
    aim_hold: float = 0.0
    #: Which beat of the melee chain the next swing is. Never on the wire —
    #: the swing event carries the step it was, and that is what the client
    #: draws; a counter would only let the two disagree.
    combo_step: int = 0
    #: Seconds left to keep the chain. Runs out and the next swing is a first
    #: slash again.
    combo_left: float = 0.0

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

    @property
    def max_hp(self) -> int:
        """This body's ceiling, which is no longer everybody's.

        `config.MAX_HP` is the value a run OPENS at; a skill moves it, so every
        heal, respawn and HUD bar reads this instead. A site that still reads
        the constant is a site where Couro Grosso silently does nothing.
        """
        return self.skills.mods.max_hp

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

        The client mirrors this sum from the same catalog — see
        `Game.moveWeight`.
        """
        return self.inventory.weight + self.hotbar.held_weight

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
            # Not identity, but it has to land the moment it flips: it is what
            # the campfire's ready count is counting.
            "ready": self.ready,
            "held": self.hotbar.held,
            "ads": ads,
        }
        # Omitted for everybody who is not pouring, which is everybody almost
        # all of the time — this is a per-tick row and a field that is null for
        # eight players costs more than the one it describes.
        if self.pour is not None:
            row["pour"] = self.pour.phase
        return row

    def to_payload(self) -> dict:
        """The whole player: `welcome`, and the snapshot roster."""
        level, into_level, to_level = level_progress(self.xp)
        return {
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
        }


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
