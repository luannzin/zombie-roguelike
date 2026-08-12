"""Enemy behaviour: who to chase, where to step, when to swing — and the
director that decides when new enemies show up.

Two entry points, both called once per tick from `Room.step`:

    update(enemies, players, world, dt) -> Outcome(attacks, despawned)
    EnemyDirector.update(dt, players, enemy_count) -> list[(EnemyType, x, y)]

Neither one mutates players or the room. `update` decides that a swing lands
and hands back an intent; the room resolves damage, i-frames, death and
events. Keeping the decision and the consequence apart is what lets the room
stay the only place that can change a player's hp.

Steering has two modes and picks per tick:

    clear line of sight  -> walk straight at the target
    anything in the way  -> follow the flow field from pathing.py

The direct mode is what makes a zombie look like a zombie in the open: it comes
at you in a straight line, not along tile centres. The field mode is what stops
it pressing itself into the side of a pillar forever — walking downhill on a
BFS distance field commits to going AROUND cover. The line-of-sight test is
swept, not a single ray: it checks the enemy's full body width, so a route that
would only fit a point does not count as clear.

A stuck detector backs both of them up. If an enemy travels far less than its
speed says it should, it stops trusting line of sight and follows the field
until it is moving again — the difference between "briefly snagged" and
"trapped against a wall for the rest of the match".

On top of that a light separation push keeps a pack spread into a crescent
instead of stacked into one sprite.

Per tick this is O(enemies x players + enemies²) with tiny constants, plus one
BFS per player when they change tile; the director's population cap and the
field's rebuild interval are what keep both bounded.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from . import combat
from .config import (
    ENEMY_DESPAWN_DELAY,
    ENEMY_DESPAWN_DIST,
    ENEMY_DIRECT_SIGHT_DIST,
    ENEMY_FIRST_SPAWN_DELAY,
    ENEMY_MAX_PER_PLAYER,
    ENEMY_MAX_TOTAL,
    ENEMY_SEPARATION,
    ENEMY_SPAWN_INTERVAL,
    ENEMY_SPAWN_MAX_DIST,
    ENEMY_SPAWN_MIN_DIST,
    ENEMY_STUCK_DELAY,
)
from .enemies import SPAWN_TABLE, Enemy, EnemyType
from .entities import Player
from .pathing import Navigator
from .world import TileMap

#: How strongly the separation push competes with the chase direction.
SEPARATION_WEIGHT = 0.65
#: Spawn placement attempts before giving up for this interval.
SPAWN_ATTEMPTS = 24
#: Below this fraction of the distance it should have covered, an enemy counts
#: as making no progress this tick.
PROGRESS_RATIO = 0.35
#: Separation is muted while following the field — the field already knows
#: where the walls are, and a shove sideways is how a pack pushes one of its
#: own into a corner.
FIELD_SEPARATION_WEIGHT = 0.25


@dataclass
class Attack:
    """One enemy's swing connecting with one player. The room resolves it."""

    enemy: Enemy
    target: Player


@dataclass
class Outcome:
    """What one AI tick decided. The room applies both lists."""

    attacks: list[Attack]
    #: Enemies stranded far from everyone — remove them, no reward, no event.
    despawned: list[Enemy]


def update(
    enemies: Iterable[Enemy],
    players: Iterable[Player],
    world: TileMap,
    navigator: Navigator,
    dt: float,
) -> Outcome:
    """Advance every enemy one tick."""
    pack = [e for e in enemies if e.alive]
    living = [p for p in players if p.alive]
    attacks: list[Attack] = []
    despawned: list[Enemy] = []

    navigator.update(living, dt)

    for enemy in pack:
        if enemy.attack_cooldown > 0.0:
            enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)

        target, distance = nearest_player(enemy, living)

        # Abandonment is measured against the nearest player at ANY distance,
        # not the aggro range: an enemy idling just outside aggro is still part
        # of the fight, one on the far side of the map is not.
        if target is None or distance > ENEMY_DESPAWN_DIST:
            enemy.abandoned += dt
            if enemy.abandoned >= ENEMY_DESPAWN_DELAY:
                despawned.append(enemy)
        else:
            enemy.abandoned = 0.0

        if target is None or distance > enemy.type.aggro_range:
            enemy.target_id = None
            enemy.vx = enemy.vy = 0.0
            continue

        enemy.target_id = target.id
        if distance > 1e-6:
            enemy.aim_x = (target.x - enemy.x) / distance
            enemy.aim_y = (target.y - enemy.y) / distance

        if distance <= enemy.type.attack_range:
            # In reach: plant your feet and swing when your own cooldown allows.
            enemy.vx = enemy.vy = 0.0
            enemy.stuck = 0.0
            if enemy.attack_cooldown <= 0.0:
                enemy.attack_cooldown = enemy.type.attack_cooldown
                attacks.append(Attack(enemy=enemy, target=target))
            continue

        chase_x, chase_y, routed = chase_direction(enemy, target, distance, world, navigator)

        # A routed enemy is threading cover; a shove from the pack is what puts
        # it back into the wall it is trying to walk around.
        weight = FIELD_SEPARATION_WEIGHT if routed else SEPARATION_WEIGHT
        push_x, push_y = separation(enemy, pack)
        steer_x = chase_x + push_x * weight
        steer_y = chase_y + push_y * weight

        length = math.hypot(steer_x, steer_y)
        if length <= 1e-6:
            enemy.vx = enemy.vy = 0.0
            continue
        speed = enemy.type.speed
        enemy.vx = steer_x / length * speed
        enemy.vy = steer_y / length * speed
        move(enemy, world, dt)

    return Outcome(attacks=attacks, despawned=despawned)


def chase_direction(
    enemy: Enemy,
    target: Player,
    distance: float,
    world: TileMap,
    navigator: Navigator,
) -> tuple[float, float, bool]:
    """Which way to walk, and whether the flow field chose it.

    Straight at the target whenever the body actually fits through the gap
    between here and there; otherwise downhill on the target's field. An enemy
    that has stopped making progress skips the sight test entirely — whatever
    it can see, it plainly cannot walk through.
    """
    direct = (enemy.aim_x, enemy.aim_y)

    if enemy.stuck < ENEMY_STUCK_DELAY and has_clearance(enemy, target, distance, world):
        return direct[0], direct[1], False

    routed = navigator.steer(enemy.x, enemy.y, target.id)
    if routed is None:
        # No field (target just died, or a sealed pocket): straight line is
        # still better than standing still.
        return direct[0], direct[1], False
    return routed[0], routed[1], True


def has_clearance(enemy: Enemy, target: Player, distance: float, world: TileMap) -> bool:
    """Is there a body-width corridor straight from the enemy to the target?

    A single centre ray is not enough: it slips through gaps narrower than the
    enemy, which is exactly how a chaser ends up wedged on a corner it thought
    it could see past. Two rays offset by the body's half width sweep the whole
    silhouette.
    """
    if distance > ENEMY_DIRECT_SIGHT_DIST or distance <= 1e-6:
        return False

    dx = enemy.aim_x
    dy = enemy.aim_y
    # Perpendicular offsets, one per side of the body.
    px = -dy * enemy.type.half_width
    py = dx * enemy.type.half_width
    for side in (1.0, -1.0):
        ox = enemy.x + px * side
        oy = enemy.y + py * side
        # raycast_tiles reports 0.0 when the origin is already inside a wall,
        # which correctly fails the test for an enemy hugging one.
        if combat.raycast_tiles(world, ox, oy, dx, dy, distance) < distance - 1e-3:
            return False
    return True


def nearest_player(enemy: Enemy, living: Sequence[Player]) -> tuple[Player | None, float]:
    """Closest living player and its distance, ignoring aggro. (None, inf) if empty."""
    best: Player | None = None
    best_d2 = math.inf
    for player in living:
        d2 = (player.x - enemy.x) ** 2 + (player.y - enemy.y) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = player
    return best, math.sqrt(best_d2) if best is not None else math.inf


def separation(enemy: Enemy, pack: Sequence[Enemy]) -> tuple[float, float]:
    """Unit-ish push away from crowding neighbours (zero when no one is close).

    Enemies do not collide with each other — resolving that properly costs more
    than it is worth at this population. This just biases their steering, which
    is enough to keep a pack legible as several bodies.
    """
    px = 0.0
    py = 0.0
    for other in pack:
        if other is enemy:
            continue
        dx = enemy.x - other.x
        dy = enemy.y - other.y
        d2 = dx * dx + dy * dy
        if d2 >= ENEMY_SEPARATION * ENEMY_SEPARATION:
            continue
        if d2 < 1e-6:
            # Exactly stacked: shove apart in an arbitrary but stable direction.
            angle = (hash(enemy.id) % 628) / 100.0
            px += math.cos(angle)
            py += math.sin(angle)
            continue
        distance = math.sqrt(d2)
        # Closer neighbours push harder.
        weight = (ENEMY_SEPARATION - distance) / ENEMY_SEPARATION
        px += dx / distance * weight
        py += dy / distance * weight
    return px, py


def move(enemy: Enemy, world: TileMap, dt: float) -> None:
    """Axis-separated move against the tile grid — the player's rule, reused.

    Also keeps the stuck timer: walls silently eat one or both axes here, so
    this is the only place that knows the difference between "walking" and
    "walking into something".
    """
    hw = enemy.type.half_width
    hh = enemy.type.half_height
    before_x = enemy.x
    before_y = enemy.y

    enemy.x = world.move_axis(enemy.x, enemy.y, hw, hh, enemy.vx * dt, 0)
    enemy.y = world.move_axis(enemy.x, enemy.y, hw, hh, enemy.vy * dt, 1)

    travelled = math.hypot(enemy.x - before_x, enemy.y - before_y)
    expected = enemy.type.speed * dt
    if travelled < expected * PROGRESS_RATIO:
        enemy.stuck += dt
    else:
        # Recover twice as fast as it accrues: one snagged tick should not put
        # an enemy on the field route for a noticeable stretch of open ground.
        enemy.stuck = max(0.0, enemy.stuck - dt * 2.0)


class EnemyDirector:
    """Decides when and where enemies appear.

    Population scales with the number of living players, and spawns land in a
    ring around a random one: far enough away that nothing materialises in your
    face, close enough that it walks into the fight rather than idling across
    the map. Placement is sampled from the map's precomputed free tiles, so a
    spawn can never end up inside a wall.
    """

    def __init__(self, spawn_points: Sequence[tuple[float, float]]):
        self.spawn_points = spawn_points
        self.timer = ENEMY_FIRST_SPAWN_DELAY

    def update(
        self, dt: float, players: Iterable[Player], enemy_count: int
    ) -> list[tuple[EnemyType, float, float]]:
        living = [p for p in players if p.alive]
        if not living or not self.spawn_points:
            return []

        self.timer -= dt
        if self.timer > 0.0:
            return []
        self.timer = ENEMY_SPAWN_INTERVAL

        cap = min(ENEMY_MAX_TOTAL, ENEMY_MAX_PER_PLAYER * len(living))
        if enemy_count >= cap:
            return []

        spot = self.pick_spot(random.choice(living), living)
        if spot is None:
            return []
        return [(self.pick_type(), spot[0], spot[1])]

    def pick_type(self) -> EnemyType:
        types = [t for t, _ in SPAWN_TABLE]
        weights = [w for _, w in SPAWN_TABLE]
        return random.choices(types, weights=weights, k=1)[0]

    def pick_spot(
        self, anchor: Player, living: Sequence[Player]
    ) -> tuple[float, float] | None:
        """A free tile inside the ring around `anchor`, clear of every player."""
        fallback: tuple[float, float] | None = None
        min_d2 = ENEMY_SPAWN_MIN_DIST ** 2
        max_d2 = ENEMY_SPAWN_MAX_DIST ** 2

        for _ in range(SPAWN_ATTEMPTS):
            x, y = random.choice(self.spawn_points)
            if any((p.x - x) ** 2 + (p.y - y) ** 2 < min_d2 for p in living):
                continue
            fallback = (x, y)
            d2 = (anchor.x - x) ** 2 + (anchor.y - y) ** 2
            if d2 <= max_d2:
                return x, y
        # Nothing inside the ring: anywhere that is not on top of a player will
        # do — better a distant zombie than a skipped spawn.
        return fallback
