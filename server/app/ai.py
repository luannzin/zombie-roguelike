"""Enemy behaviour: what it has noticed, where it steps, when it swings — and
the director that decides when new enemies show up.

Two entry points, both called once per tick from `Room.step`:

    update(enemies, players, world, navigator, dt, noises)
        -> Outcome(attacks, despawned)
    EnemyDirector.update(dt, players, enemy_count) -> list[(EnemyType, x, y)]

Neither one mutates players or the room. `update` decides that a swing lands
and hands back an intent; the room resolves damage, i-frames, death and
events. Keeping the decision and the consequence apart is what lets the room
stay the only place that can change a player's hp.

==========================================================================
NOTICING
==========================================================================
An enemy does not chase anything it has not noticed, and noticing is a thing
that takes time and can be watched happening.

Three modes, and every enemy is in exactly one:

    idle      patrol a short leash around the tile it spawned on
    hunt      go to the target; keep going to where it last was
    return    walk home, then go back to idle

`Enemy.awareness` is the meter between the first two. It fills while a living
player stands inside the SIGHT CONE — a wedge of `view_tiles` and
`view_degrees` off the enemy's own facing, occluded by the tile grid, so a
thicket really does hide you. Filling is faster the closer you are. It drains
whenever the cone is empty. At 1 the enemy commits, and the meter is PINNED
there for the whole hunt: the client paints the cone from this number (white →
orange → red), and a hunter whose meter sagged every time you rounded a corner
would flicker back to "calm" while it was actively coming for you.

Three things fill the meter without the enemy seeing anything itself:

    a shout   an enemy that just committed wakes everyone within
              ENEMY_ALERT_SHARE_DIST. One hop only — a chain reaction from one
              careless step would wake the map and there would be nothing left
              to disengage from.
    a noise   see `Noise`. A gunshot is the only one so far; the shape is
              generic because footsteps and thrown objects are the same event
              with a different radius.
    a bullet  `alarm()`, called by the room when something takes damage. Being
              shot in the back is not a thing you can fail to notice.

Losing you is the mirror of finding you: ENEMY_LOSE_DELAY seconds walking to
where you last were, and then home. Wandering more than ENEMY_LEASH_DIST from
home ends the hunt on the spot, so outrunning a pack is a real option rather
than a slow one.

==========================================================================
STEERING
==========================================================================
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
    ENEMY_ALERT_SHARE_DIST,
    ENEMY_ARRIVE_DIST,
    ENEMY_DESPAWN_DELAY,
    ENEMY_DESPAWN_DIST,
    ENEMY_DIRECT_SIGHT_DIST,
    ENEMY_FIRST_SPAWN_DELAY,
    ENEMY_FORGET_RATE,
    ENEMY_GROUP_SIZES,
    ENEMY_GROUP_SPREAD,
    ENEMY_GROUP_WEIGHTS,
    ENEMY_HOME_DIST,
    ENEMY_LEASH_DIST,
    ENEMY_LOSE_DELAY,
    ENEMY_MAX_PER_PLAYER,
    ENEMY_MAX_TOTAL,
    ENEMY_NOTICE_FAR,
    ENEMY_NOTICE_NEAR,
    ENEMY_SEPARATION,
    ENEMY_SPAWN_INTERVAL,
    ENEMY_SPAWN_MAX_DIST,
    ENEMY_SPAWN_MIN_DIST,
    ENEMY_STUCK_DELAY,
    ENEMY_WANDER_PAUSE_MAX,
    ENEMY_WANDER_PAUSE_MIN,
    ENEMY_WANDER_SPEED_SCALE,
    NOISE_ALERT_GAIN,
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

#: What an enemy is doing. See the header.
MODE_IDLE = "idle"
MODE_HUNT = "hunt"
MODE_RETURN = "return"

#: Patrol waypoint placement attempts before just standing still this leg.
WANDER_ATTEMPTS = 8
#: How long an enemy may fail to make headway on its way home before it accepts
#: where it is standing as the new home. Cheaper than pathfinding a route back,
#: and the outcome is the same shape: an enemy patrolling a patch of forest.
RESETTLE_DELAY = 1.5


@dataclass
class Attack:
    """One enemy's swing connecting with one player. The room resolves it."""

    enemy: Enemy
    target: Player


@dataclass(frozen=True)
class Noise:
    """Something an enemy can hear, at a place, with a reach.

    The room collects these during a tick and hands them to the next `update`.
    A gunshot is the only source so far (`Room.fire`), and the point of the type
    is that the second one costs nothing: footsteps, a thrown bottle and a door
    are this with a different radius.

    `source_id` is the player who made it. An enemy loud enough to be woken by a
    noise hunts THAT player — a sound in a dark forest is a person, and sending
    zombies to investigate an empty patch of dirt is a worse game than sending
    them at the idiot who fired.
    """

    x: float
    y: float
    radius: float
    source_id: str | None = None


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
    noises: Sequence[Noise] = (),
) -> Outcome:
    """Advance every enemy one tick."""
    pack = [e for e in enemies if e.alive]
    living = [p for p in players if p.alive]
    by_id = {p.id: p for p in living}
    attacks: list[Attack] = []
    despawned: list[Enemy] = []

    navigator.update(living, dt)

    # Ears before eyes. The room steps players first, so a shot fired this tick
    # is already in the list and is answered on the same tick it was fired.
    for noise in noises:
        hear(pack, noise, by_id)

    #: Committed this tick. Their shout goes out after the loop, so an enemy
    #: woken by a neighbour is not itself a shouter — one hop, see the header.
    shouted: list[tuple[Enemy, Player]] = []

    for enemy in pack:
        if enemy.attack_cooldown > 0.0:
            enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)

        nearest, nearest_dist = nearest_player(enemy, living)

        # Abandonment is measured against the nearest player at ANY distance,
        # not the aggro range: an enemy idling just outside aggro is still part
        # of the fight, one on the far side of the map is not. A hunter is never
        # recycled — it is on its way to somebody, however far that is.
        if nearest is None or nearest_dist > ENEMY_DESPAWN_DIST:
            enemy.abandoned += dt
            if enemy.abandoned >= ENEMY_DESPAWN_DELAY and enemy.mode != MODE_HUNT:
                despawned.append(enemy)
        else:
            enemy.abandoned = 0.0

        seen = look(enemy, living, world)

        if enemy.mode != MODE_HUNT:
            if seen is not None:
                # Noticing costs the enemy its footing: it stops, it stares, and
                # the cone over it climbs. That pause is the player's whole
                # window to back out of it.
                enemy.vx = enemy.vy = 0.0
                enemy.wander_x = enemy.wander_y = None
                face(enemy, seen.x, seen.y)
                enemy.awareness = min(
                    1.0, enemy.awareness + dt / notice_time(enemy, seen)
                )
                if enemy.awareness < 1.0:
                    continue
                commit(enemy, seen)
                shouted.append((enemy, seen))
            else:
                enemy.awareness = max(0.0, enemy.awareness - ENEMY_FORGET_RATE * dt)
                patrol(enemy, world, dt)
                continue

        # --- hunting ---------------------------------------------------------
        target = by_id.get(enemy.target_id or "")
        if target is None:
            # Target died or left. The nearest living player is not a
            # replacement — it never saw them.
            give_up(enemy)
            continue

        distance = math.hypot(target.x - enemy.x, target.y - enemy.y)
        if seen is target:
            enemy.lost = 0.0
            enemy.last_seen_x = target.x
            enemy.last_seen_y = target.y
        else:
            enemy.lost += dt

        # Two ways to end a hunt: it has been too long since you were visible,
        # or the chase has pulled the enemy off its own patch entirely.
        if (
            enemy.lost >= ENEMY_LOSE_DELAY
            or distance > enemy.type.aggro_range
            or math.hypot(enemy.x - enemy.home_x, enemy.y - enemy.home_y) > ENEMY_LEASH_DIST
        ):
            give_up(enemy)
            continue

        # Out of sight, it walks to where the player WAS; the flow field still
        # routes to the real one, which is the small cheat that keeps a lost
        # zombie from walking into a tree for four seconds.
        goal_x = target.x if enemy.lost == 0.0 else enemy.last_seen_x
        goal_y = target.y if enemy.lost == 0.0 else enemy.last_seen_y
        goal_dist = math.hypot(goal_x - enemy.x, goal_y - enemy.y)
        if goal_dist > 1e-6:
            enemy.aim_x = (goal_x - enemy.x) / goal_dist
            enemy.aim_y = (goal_y - enemy.y) / goal_dist

        if distance <= enemy.type.attack_range:
            # In reach: plant your feet and swing when your own cooldown allows.
            face(enemy, target.x, target.y)
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

    for spotter, target in shouted:
        shout(spotter, target, pack)

    return Outcome(attacks=attacks, despawned=despawned)


# --- noticing ----------------------------------------------------------------
def look(enemy: Enemy, living: Sequence[Player], world: TileMap) -> Player | None:
    """The closest living player inside this enemy's sight cone, or None.

    Three tests, cheapest first: range, then the cone's half angle against the
    enemy's own facing, then one ray for occlusion. A single centre ray is
    enough here — unlike `has_clearance`, which asks whether a BODY fits through
    the gap, this only asks whether light does.
    """
    reach = enemy.type.view_range
    cos_half = enemy.type.view_cos
    best: Player | None = None
    best_d = math.inf

    for player in living:
        dx = player.x - enemy.x
        dy = player.y - enemy.y
        distance = math.hypot(dx, dy)
        if distance > reach or distance >= best_d:
            continue
        if distance > 1e-6:
            # Standing on top of something is not something you can fail to
            # notice, whichever way you are facing — hence the guard.
            if (dx * enemy.aim_x + dy * enemy.aim_y) / distance < cos_half:
                continue
            if (
                combat.raycast_tiles(world, enemy.x, enemy.y, dx / distance, dy / distance, distance)
                < distance - 1e-3
            ):
                continue
        best = player
        best_d = distance
    return best


def notice_time(enemy: Enemy, target: Player) -> float:
    """Seconds this player has to stay in the cone to be committed to.

    Linear in distance between the two ends of the range. Close is nearly
    instant; the far edge of the cone gives you time to step back out of it.
    """
    reach = enemy.type.view_range
    if reach <= 1e-6:
        return ENEMY_NOTICE_NEAR
    ratio = min(1.0, math.hypot(target.x - enemy.x, target.y - enemy.y) / reach)
    return ENEMY_NOTICE_NEAR + (ENEMY_NOTICE_FAR - ENEMY_NOTICE_NEAR) * ratio


def commit(enemy: Enemy, target: Player) -> None:
    """Stop patrolling and start hunting this player."""
    enemy.mode = MODE_HUNT
    enemy.target_id = target.id
    enemy.awareness = 1.0
    enemy.lost = 0.0
    enemy.last_seen_x = target.x
    enemy.last_seen_y = target.y
    enemy.wander_x = enemy.wander_y = None
    enemy.wander_wait = 0.0


def give_up(enemy: Enemy) -> None:
    """End a hunt: head home, and let the cone cool back to white."""
    enemy.mode = MODE_RETURN
    enemy.target_id = None
    enemy.awareness = 0.0
    enemy.lost = 0.0
    enemy.vx = enemy.vy = 0.0
    enemy.wander_x = enemy.wander_y = None
    enemy.wander_wait = 0.0


def shout(spotter: Enemy, target: Player, pack: Sequence[Enemy]) -> None:
    """One enemy spotting a player is every enemy near it spotting them."""
    reach2 = ENEMY_ALERT_SHARE_DIST * ENEMY_ALERT_SHARE_DIST
    for other in pack:
        if other is spotter or other.mode == MODE_HUNT:
            continue
        if (other.x - spotter.x) ** 2 + (other.y - spotter.y) ** 2 > reach2:
            continue
        commit(other, target)


def hear(pack: Sequence[Enemy], noise: Noise, by_id: dict[str, Player]) -> None:
    """Fold one noise into every enemy within its radius.

    Awareness gain tapers from the centre outward and overshoots on purpose
    (NOISE_ALERT_GAIN > 1), so the middle of a gunshot is an instant hunt and
    the outer band only turns heads. An enemy already hunting has nothing to
    learn from it.
    """
    if noise.radius <= 0.0:
        return
    source = by_id.get(noise.source_id or "")
    for enemy in pack:
        if enemy.mode == MODE_HUNT:
            continue
        distance = math.hypot(noise.x - enemy.x, noise.y - enemy.y)
        if distance > noise.radius:
            continue
        face(enemy, noise.x, noise.y)
        enemy.awareness = min(
            1.0, enemy.awareness + NOISE_ALERT_GAIN * (1.0 - distance / noise.radius)
        )
        if enemy.awareness >= 1.0 and source is not None:
            commit(enemy, source)


def alarm(enemy: Enemy, source: Player | None) -> None:
    """Something hurt this enemy. Whoever did it is now its problem.

    Called by the room rather than discovered here: damage is the room's to
    resolve, and an enemy that had to SEE the shot that killed it would be
    invulnerable from behind.
    """
    if source is None or not source.alive or enemy.mode == MODE_HUNT:
        return
    commit(enemy, source)


def face(enemy: Enemy, x: float, y: float) -> None:
    """Point the enemy's facing (and so its sight cone) at a world point."""
    dx = x - enemy.x
    dy = y - enemy.y
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return
    enemy.aim_x = dx / length
    enemy.aim_y = dy / length


# --- patrol ------------------------------------------------------------------
def patrol(enemy: Enemy, world: TileMap, dt: float) -> None:
    """Idle behaviour: drift around home, or walk back to it.

    Deliberately not pathfound. The flow fields exist per PLAYER (see
    pathing.py) and building one per enemy home would cost a BFS per creature;
    an enemy that cannot walk home in a straight line instead accepts where it
    is standing as home, which lands in the same place — a creature patrolling
    a patch of forest — for none of the price.
    """
    speed = enemy.type.speed * ENEMY_WANDER_SPEED_SCALE

    if enemy.mode == MODE_RETURN:
        dx = enemy.home_x - enemy.x
        dy = enemy.home_y - enemy.y
        if math.hypot(dx, dy) <= ENEMY_ARRIVE_DIST:
            enemy.mode = MODE_IDLE
            enemy.wander_wait = random.uniform(ENEMY_WANDER_PAUSE_MIN, ENEMY_WANDER_PAUSE_MAX)
            enemy.vx = enemy.vy = 0.0
            return
        if enemy.stuck >= RESETTLE_DELAY:
            enemy.home_x = enemy.x
            enemy.home_y = enemy.y
            enemy.mode = MODE_IDLE
            enemy.stuck = 0.0
            return
        walk(enemy, dx, dy, speed, world, dt)
        return

    if enemy.wander_wait > 0.0:
        enemy.wander_wait -= dt
        enemy.vx = enemy.vy = 0.0
        return

    if enemy.wander_x is None or enemy.wander_y is None:
        spot = pick_waypoint(enemy, world)
        if spot is None:
            enemy.wander_wait = random.uniform(ENEMY_WANDER_PAUSE_MIN, ENEMY_WANDER_PAUSE_MAX)
            enemy.vx = enemy.vy = 0.0
            return
        enemy.wander_x, enemy.wander_y = spot

    dx = enemy.wander_x - enemy.x
    dy = enemy.wander_y - enemy.y
    # Arrived, or wedged on the way — either way this leg is over.
    if math.hypot(dx, dy) <= ENEMY_ARRIVE_DIST or enemy.stuck >= ENEMY_STUCK_DELAY:
        enemy.wander_x = enemy.wander_y = None
        enemy.stuck = 0.0
        enemy.wander_wait = random.uniform(ENEMY_WANDER_PAUSE_MIN, ENEMY_WANDER_PAUSE_MAX)
        enemy.vx = enemy.vy = 0.0
        return
    walk(enemy, dx, dy, speed, world, dt)


def pick_waypoint(enemy: Enemy, world: TileMap) -> tuple[float, float] | None:
    """A free point inside the patrol leash around home, or None this leg."""
    hw = enemy.type.half_width
    hh = enemy.type.half_height
    for _ in range(WANDER_ATTEMPTS):
        angle = random.uniform(0.0, math.tau)
        radius = ENEMY_HOME_DIST * math.sqrt(random.random())
        x = enemy.home_x + math.cos(angle) * radius
        y = enemy.home_y + math.sin(angle) * radius
        if not world.box_blocked(x, y, hw, hh):
            return x, y
    return None


def walk(enemy: Enemy, dx: float, dy: float, speed: float, world: TileMap, dt: float) -> None:
    """Step toward an offset at `speed`, facing where it is going."""
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        enemy.vx = enemy.vy = 0.0
        return
    enemy.aim_x = dx / length
    enemy.aim_y = dy / length
    enemy.vx = enemy.aim_x * speed
    enemy.vy = enemy.aim_y * speed
    move(enemy, world, dt)


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

    # Measured against the speed it was ACTUALLY asked for, not the type's top
    # speed: a patrol shambles at a fraction of it, and a threshold written
    # against the sprint would mark every wandering enemy as permanently stuck.
    travelled = math.hypot(enemy.x - before_x, enemy.y - before_y)
    expected = math.hypot(enemy.vx, enemy.vy) * dt
    if expected <= 1e-9:
        return
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
    face, close enough that it is somewhere you might actually go. Placement is
    sampled from the map's precomputed free tiles, so a spawn can never end up
    inside a wall.

    Enemies arrive as a GROUP — one to four, weighted toward the smaller sizes —
    scattered around one landing spot. Each of them takes its own landing tile
    as HOME and patrols it, so what the director really places is a pocket of
    forest that is occupied. Nothing walks at the party until something in that
    pocket notices them.
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
        room = cap - enemy_count
        if room <= 0:
            return []

        spot = self.pick_spot(random.choice(living), living)
        if spot is None:
            return []

        # A group clipped by the cap is still a group: three of four is better
        # than skipping the wave and leaving the map empty for another interval.
        size = min(self.pick_size(), room)
        return [(self.pick_type(), *place) for place in self.scatter(spot, size)]

    def pick_size(self) -> int:
        return random.choices(ENEMY_GROUP_SIZES, weights=ENEMY_GROUP_WEIGHTS, k=1)[0]

    def scatter(self, spot: tuple[float, float], size: int) -> list[tuple[float, float]]:
        """`size` free tiles clustered around `spot`.

        Sampled from the same free-tile list the anchor came from, so a group
        member can no more spawn inside a tree than a lone enemy can. If the
        pocket is too tight to hold the whole group, the rest stack on the
        anchor — separation pushes them apart within a tick or two.
        """
        reach2 = ENEMY_GROUP_SPREAD * ENEMY_GROUP_SPREAD
        nearby = [
            point
            for point in self.spawn_points
            if (point[0] - spot[0]) ** 2 + (point[1] - spot[1]) ** 2 <= reach2
        ]
        if len(nearby) <= size:
            return nearby + [spot] * (size - len(nearby))
        return random.sample(nearby, size)

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
