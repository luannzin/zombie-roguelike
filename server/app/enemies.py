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

from dataclasses import dataclass

from .config import (
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
    #: How far it notices a player. Beyond this it stands still.
    aggro_tiles: float
    #: Centre-to-centre distance at which it can swing.
    attack_range_tiles: float
    #: Seconds between its own swings (its personal rate limit).
    attack_cooldown: float

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
        }


ZOMBIE = EnemyType(
    key="zombie",
    sprite="zombie",
    max_hp=30,          # 4 hits at SHOT_DAMAGE 8
    damage=9,           # ~15 dps against a swarm, given MELEE_IMMUNITY
    xp=12,
    gold=3,
    speed_tiles=2.6,    # vs the player's 4.4 — always outrunnable
    aggro_tiles=24.0,   # most of the arena: a zombie you can see is coming
    attack_range_tiles=0.85,
    attack_cooldown=1.1,
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
    #: Facing, as a unit vector — the renderer picks a sprite row from it.
    aim_x: float = 0.0
    aim_y: float = 1.0
    alive: bool = True

    # server bookkeeping (never sent verbatim)
    attack_cooldown: float = 0.0
    target_id: str | None = None
    #: Seconds spent with no living player anywhere near — see ai.update.
    abandoned: float = 0.0
    #: Seconds spent making no headway; switches steering to the flow field.
    stuck: float = 0.0

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.type.max_hp

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
        }
