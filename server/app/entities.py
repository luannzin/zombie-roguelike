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
from .weapons import Hotbar

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
    #: Three gun slots plus the fixed knife cell. Starts with a Glock 18.
    hotbar: Hotbar = field(default_factory=Hotbar.starting)
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
        """Bag plus every gun on the belt. The walk reads this, not the bag alone."""
        return self.inventory.weight + self.hotbar.weight

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
        return {
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
            "inv": {
                **self.inventory.to_payload(),
                # Total carried kg — bag plus the belt — so prediction and the
                # weight bar agree without a second field.
                "w": round(self.carry_weight, 2),
            },
            "guns": self.hotbar.to_payload(),
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
