"""Authoritative entity state.

`Player` is the only entity today. Zombies/NPCs will be a sibling dataclass
that reuses the same (x, y, radius, hp, alive) shape so `combat.raycast` can
target them without changes.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from .config import MAX_HP, PLAYER_HIT_RADIUS

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
        return InputCmd(
            sequence=int(msg.get("sequence", 0)),
            up=bool(mv.get("up")),
            down=bool(mv.get("down")),
            left=bool(mv.get("left")),
            right=bool(mv.get("right")),
            aim_x=ax,
            aim_y=ay,
            shoot=bool(msg.get("shoot")),
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

    # server bookkeeping (never sent verbatim)
    inputs: deque = field(default_factory=deque)
    last_input: InputCmd = field(default_factory=InputCmd)
    last_processed_seq: int = 0
    idle_ticks: int = 0
    fire_cooldown: float = 0.0
    respawn_timer: float = 0.0

    def to_payload(self) -> dict:
        # Positions need ≥4 decimals: wall snaps use EPS=1e-4, and round(_, 2)
        # pushes right/down snaps onto the tile boundary so box_blocked flips
        # true. Client reconcile then blocks the other axis (strafe "lag"
        # while sliding down a wall; up/left were fine because +EPS rounds away).
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
            "ax": round(self.aim_x, 3),
            "ay": round(self.aim_y, 3),
            "hp": self.hp,
            "alive": self.alive,
            "kills": self.kills,
            "deaths": self.deaths,
        }


def random_name(taken: set[str]) -> str:
    for _ in range(50):
        name = f"Player{random.randint(100, 999)}"
        if name not in taken:
            return name
    return f"Player{random.randint(1000, 999999)}"


def random_color() -> str:
    return random.choice(COLORS)
