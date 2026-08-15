"""Enemies: the stat block (`EnemyType`) and the live instance (`Enemy`).

An **EnemyType** is the designer-facing answer to "what is a zombie": how much
health it has, how hard it hits, how fast it shambles, how far it can see, and
what it pays out when it dies (xp, gold). It is frozen data — one entry in
`ENEMY_TYPES` plus a processed sprite sheet of the same name is a whole new
creature. Nothing in the room, the renderer or the protocol is per-creature.

An **Enemy** is one live instance of a type: position, hp, cooldowns, current
target. It deliberately exposes the same `(id, x, capsule_y0, capsule_y1,
radius, alive)` shape as `Player`, so `combat.raycast` shoots it with no
changes and players and enemies can share one target list.

Sizes and speeds are authored in TILES and seconds, exactly like config.py, and
multiplied by TILE_SIZE here — so changing the game's scale rescales enemies
too. Stats reach the client inside `welcome.config.enemyTypes`; the client
never hardcodes an enemy number.

Behaviour lives in ai.py (chase, attack, spawn cadence). This module is data
and state only.

Adding a creature:
    1. draw it:  tools/make_placeholder_sheet.py --name <n> (or real art)
    2. process:  tools/process_sprites.py --name <n> --tile 16
    3. add an EnemyType to ENEMY_TYPES and a weight to SPAWN_TABLE
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import (
    ENEMY_VIEW_DARK_TILES,
    ENEMY_VIEW_LIT_TILES,
    PLAYER_BOX_TILES_H,
    PLAYER_BOX_TILES_W,
    PLAYER_HIT_TILES_R,
    SPRITE_TILES_H,
    TILE_SIZE,
)


@dataclass(frozen=True)
class EnemyType:
    """One creature's stat block. Everything spatial is in tiles."""

    key: str
    #: Processed asset folder name — assets/processed/<sprite>/sheet.png.
    sprite: str
    max_hp: int
    #: Damage per landed melee hit (before the victim's i-frames are checked).
    damage: int
    #: Paid to whoever lands the killing blow.
    xp: int
    gold: int

    speed_tiles: float
    #: How far it will keep chasing a target it has already committed to.
    #: NOT how far it notices one — that is the sight cone below.
    aggro_tiles: float
    #: Centre-to-centre distance at which it can swing.
    attack_range_tiles: float
    #: Seconds between its own swings (its personal rate limit).
    attack_cooldown: float

    #: SIGHT CONE. How far it can see, and how wide, measured off its facing.
    #: This is the only way an enemy finds a player on its own — everything
    #: else (a shout from a neighbour, a gunshot, a lantern in the face, being
    #: shot) is somebody else's cone doing the work. The client does not
    #: draw this wedge; the hunt diamond is the tell.
    #:
    #: Two reaches, because sight is symmetric and the dark is shared: a player
    #: with the lamp OFF is only a shape, and is made out at `view_tiles`; one
    #: with the lamp ON is a light in a black forest and is made out at
    #: `view_lit_tiles`. Which applies is that player's own switch, so the
    #: choice to see is the choice to be seen. Defaults mirror the two sight
    #: models in the client's fov — see ENEMY_VIEW_*_TILES in config.py.
    view_tiles: float = ENEMY_VIEW_DARK_TILES
    view_lit_tiles: float = ENEMY_VIEW_LIT_TILES
    view_degrees: float = 100.0

    hit_tiles_r: float = PLAYER_HIT_TILES_R
    sprite_tiles_h: float = SPRITE_TILES_H
    box_tiles_w: float = PLAYER_BOX_TILES_W
    box_tiles_h: float = PLAYER_BOX_TILES_H

    # --- derived (world pixels) ---------------------------------------------
    @property
    def speed(self) -> float:
        return TILE_SIZE * self.speed_tiles

    @property
    def aggro_range(self) -> float:
        return TILE_SIZE * self.aggro_tiles

    @property
    def attack_range(self) -> float:
        return TILE_SIZE * self.attack_range_tiles

    @property
    def hit_radius(self) -> float:
        return TILE_SIZE * self.hit_tiles_r

    @property
    def sprite_height(self) -> float:
        return TILE_SIZE * self.sprite_tiles_h

    @property
    def half_width(self) -> float:
        return TILE_SIZE * self.box_tiles_w / 2

    @property
    def half_height(self) -> float:
        return TILE_SIZE * self.box_tiles_h / 2

    @property
    def view_range(self) -> float:
        """Reach against a player with the lamp OFF — a shape in the dark."""
        return TILE_SIZE * self.view_tiles

    @property
    def view_lit_range(self) -> float:
        """Reach against a player with the lamp ON — a light in the dark."""
        return TILE_SIZE * self.view_lit_tiles

    @property
    def view_cos(self) -> float:
        """Cosine of the cone's HALF angle — the alignment test's threshold."""
        return math.cos(math.radians(self.view_degrees) / 2)

    def client_payload(self) -> dict:
        """What the client needs: art, hit geometry, and numbers it displays."""
        return {
            "key": self.key,
            "sprite": self.sprite,
            "maxHp": self.max_hp,
            "damage": self.damage,
            "xp": self.xp,
            "gold": self.gold,
            # Geometry for local hitscan prediction and sprite anchoring.
            "hitRadius": self.hit_radius,
            "spriteHeight": self.sprite_height,
            "halfWidth": self.half_width,
            "halfHeight": self.half_height,
            # The sight cone the server tests against. Both reaches: the
            # client picks between them on the LOCAL lamp. Not drawn — the
            # hunt diamond is the tell.
            "viewRange": self.view_range,
            "viewRangeLit": self.view_lit_range,
            "viewDegrees": self.view_degrees,
        }


ZOMBIE = EnemyType(
    key="zombie",
    sprite="zombie",
    max_hp=30,          # 4 hits at SHOT_DAMAGE 8
    damage=9,           # ~15 dps against a swarm, given MELEE_IMMUNITY
    xp=12,
    gold=3,
    speed_tiles=2.6,    # vs the player's 4.4 — always outrunnable
    aggro_tiles=24.0,   # once it has you, most of the arena is not far enough
    attack_range_tiles=0.85,
    attack_cooldown=1.1,
    # Reaches left at the defaults: a zombie sees exactly as far as you do, and
    # exactly as far as your lamp lets it. Wide, though — you can spot one
    # before it spots you, but only by looking at it.
    view_degrees=100.0,
)

ENEMY_TYPES: dict[str, EnemyType] = {ZOMBIE.key: ZOMBIE}

#: Weighted spawn table used by the director. Add creatures here.
SPAWN_TABLE: list[tuple[EnemyType, float]] = [(ZOMBIE, 1.0)]


def enemy_types_payload() -> dict:
    """Every stat block, for `welcome.config.enemyTypes`."""
    return {key: t.client_payload() for key, t in ENEMY_TYPES.items()}


@dataclass
class Enemy:
    """A live creature. `type` holds everything that does not change."""

    id: str
    type: EnemyType
    x: float
    y: float
    hp: int = 0
    vx: float = 0.0
    vy: float = 0.0
    #: Facing, as a unit vector — the renderer picks a sprite row from it, and
    #: the sight cone is measured off it. Randomised on spawn (see
    #: `__post_init__`): a group that landed all facing south would sweep the
    #: clearing in formation, which is a firing squad, not wildlife.
    aim_x: float = 0.0
    aim_y: float = 1.0
    alive: bool = True

    #: 0..1 how much of a player it has noticed. Below 1 it is only suspicious
    #: and stays on its patrol; at 1 it is hunting, and it is PINNED there for
    #: as long as the hunt lasts (see ai.py). The client fills the hunt
    #: diamond with this, so the number the simulation is deciding on is the
    #: number the player is watching.
    awareness: float = 0.0

    # server bookkeeping (never sent verbatim)
    attack_cooldown: float = 0.0
    target_id: str | None = None
    #: Seconds spent with no living player anywhere near — see ai.update.
    abandoned: float = 0.0
    #: Seconds spent making no headway; switches steering to the flow field.
    stuck: float = 0.0

    #: What it is doing: one of ai.MODE_*. Never sent — `awareness` is the only
    #: thing the client needs, and a patrolling enemy and one walking home look
    #: exactly alike.
    mode: str = "idle"
    #: Where it spawned. It patrols around this and comes back to it, so the
    #: map keeps the shape the director gave it instead of draining toward
    #: whoever fired last.
    home_x: float = 0.0
    home_y: float = 0.0
    #: Current patrol waypoint (None = standing still) and how long it stands.
    wander_x: float | None = None
    wander_y: float | None = None
    wander_wait: float = 0.0
    #: Seconds since a hunter last had eyes on its target. It keeps walking to
    #: the last known position for the whole window, so breaking line of sight
    #: buys distance, not an instant off-switch.
    lost: float = 0.0
    last_seen_x: float = 0.0
    last_seen_y: float = 0.0

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.type.max_hp
        # Spawning IS being placed at home; a zero here would send the whole
        # first wave walking to the top-left corner of the map.
        if self.home_x == 0.0 and self.home_y == 0.0:
            self.home_x = self.x
            self.home_y = self.y
        if self.aim_x == 0.0 and self.aim_y == 1.0:
            angle = random.uniform(0.0, math.tau)
            self.aim_x = math.cos(angle)
            self.aim_y = math.sin(angle)

    # --- hit capsule (same contract as Player) -------------------------------
    @property
    def radius(self) -> float:
        return self.type.hit_radius

    @property
    def capsule_y0(self) -> float:
        """Feet end of the vertical hit capsule (inset by radius)."""
        return self.y + self.type.half_height - self.radius

    @property
    def capsule_y1(self) -> float:
        """Head end of the vertical hit capsule (inset by radius)."""
        return self.y + self.type.half_height - self.type.sprite_height + self.radius

    def to_payload(self) -> dict:
        # `t` (type key) is the client's lookup into welcome.config.enemyTypes,
        # so per-type constants are never repeated in a 30 Hz snapshot.
        return {
            "id": self.id,
            "t": self.type.key,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
            "ax": round(self.aim_x, 3),
            "ay": round(self.aim_y, 3),
            "hp": self.hp,
            # The hunt diamond's fill. Two decimals is under a percent of
            # the meter — finer than the client can paint.
            "aw": round(self.awareness, 2),
        }
