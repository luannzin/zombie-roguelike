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

Four modes, and every enemy is in exactly one:

    idle      patrol a short leash around the tile it spawned on
    hunt      go to the target; keep going to where it last was
    return    walk home, then go back to idle — or back to sleep
    sleep     switched off. No cone, no patrol, no despawn, no diamond.

`sleep` is the odd one and it exists for the MINIBOSS. Everything else in this
game is already looking for you when you find it; the alpha is curled up in
its own den, and the encounter is the decision a party gets to make before
anything has been decided for them. Only three things reach it: a body inside
`EnemyType.wake_range` (it hears you — its eyes are shut), a noise, and being
shot. Not a lantern, and NOT the extraction siren: a pickup called across a
forest waking a den nobody has found is the fight happening TO the party.
Waking is a commit with a beat on the front (`wake`) — it stands, it howls,
and only then does it come.

`Enemy.awareness` is the meter between the first two. It fills while a living
player stands inside the SIGHT CONE — a wedge of `view_tiles` and
`view_degrees` off the enemy's own facing, occluded by the tile grid, so a
thicket really does hide you. Filling is faster the closer you are. It drains
whenever the cone is empty. At 1 the enemy commits, and the meter is PINNED
there for the whole hunt: the client fills the hunt diamond from this number,
and a hunter whose meter sagged every time you rounded a corner would flicker
back to "calm" while it was actively coming for you.

**Sight is symmetric.** The cone's reach is not a number the creature owns, it
is a fraction of the lantern's, chosen PER TARGET by that player's own switch:
in the same dark forest, if you can make a shape out at that distance it can
make you out at the same distance. Turning the lamp on to see further is
turning it on to be seen further — by everything already facing you.

Four things fill the meter without the enemy seeing anybody itself:

    a glare   `glare()`. The beam falling on something that is NOT looking at
              you turns it around and makes it uneasy, capped below the commit
              line. It never spots you; it points a cone at you and lets the
              cone do it. That is the lantern's real price.
    a shout   an enemy that just committed wakes everyone within
              ENEMY_ALERT_SHARE_DIST. One hop only — a chain reaction from one
              careless step would wake the map and there would be nothing left
              to disengage from. A creature with `pack_call_tiles` HOWLS
              instead: four times the reach, and only to its own PACK
              (`EnemyType.pack`, not its type — the alpha calls wolves). See
              `shout`.
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

Gun hits stack a stagger meter on the enemy (`Enemy.take_stagger`). `move`
scales vx/vy by it, so a burst slows then plants them. The meter is never
on the snapshot — the slowed velocity is enough. A pause in fire decays it.

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
    ALPHA_WAKE_DELAY,
    TILE_SIZE,
    BUSH_CONCEAL_SCALE,
    ENEMY_ALERT_SHARE_DIST,
    ENEMY_ARRIVE_DIST,
    ENEMY_DESPAWN_DELAY,
    ENEMY_DESPAWN_DIST,
    ENEMY_DIRECT_SIGHT_DIST,
    ENEMY_FIRST_SPAWN_DELAY,
    ENEMY_FORGET_RATE,
    ENEMY_GLARE_CAP,
    ENEMY_GLARE_DIST,
    ENEMY_GLARE_RATE,
    ENEMY_GROUP_SIZES,
    ENEMY_GROUP_SPREAD,
    ENEMY_GROUP_WEIGHTS,
    ENEMY_HOME_DIST,
    ENEMY_IDLE_TURN_DEGREES,
    ENEMY_LEASH_DIST,
    ENEMY_LOSE_DELAY,
    ENEMY_DAY_GROUP_TILT,
    ENEMY_DAY_POPULATION,
    ENEMY_DAY_RATE,
    ENEMY_MAX_PER_PLAYER,
    ENEMY_MAX_TOTAL,
    ENEMY_HARD_CAP,
    ENEMY_NOTICE_FAR,
    ENEMY_NOTICE_NEAR,
    ENEMY_SEPARATION,
    ENEMY_SPAWN_INTERVAL,
    ENEMY_SPAWN_INTERVAL_MIN,
    ENEMY_NIGHT_RAMP,
    ENEMY_NIGHT_RAMP_MAX,
    ENEMY_NIGHT_GRACE,
    HORDE_SIZE,
    HORDE_SIZE_PER_DAY,
    HORDE_SPAWN_TILES,
    HORDE_ARC_DEGREES,
    ENEMY_SPAWN_MAX_DIST,
    ENEMY_SPAWN_MIN_DIST,
    ENEMY_STAGGER_STOP,
    ENEMY_STUCK_DELAY,
    ENEMY_SUSPICIOUS,
    ENEMY_TURN_DEGREES,
    ENEMY_WANDER_PAUSE_MAX,
    ENEMY_WANDER_PAUSE_MIN,
    ENEMY_WANDER_SPEED_SCALE,
    NOISE_ALERT_GAIN,
    VISION_CONE_DEGREES,
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
#: CURLED UP WITH ITS EYES SHUT, and it is the only mode in which a creature
#: is switched off. It does not look, does not patrol, does not despawn and
#: does not fill a diamond; the only things that can reach it are a body close
#: enough to hear (`EnemyType.wake_range`), a noise, and being shot.
#:
#: It is a MODE rather than a flag because everything the other three modes do
#: is wrong for it, and a boolean checked at four sites is four sites that
#: will one day forget. `Enemy.asleep` is the read-only view the snapshot uses.
MODE_SLEEP = "sleep"

#: Patrol waypoint placement attempts before just standing still this leg.
WANDER_ATTEMPTS = 8
#: How long an enemy may fail to make headway on its way home before it accepts
#: where it is standing as the new home. Cheaper than pathfinding a route back,
#: and the outcome is the same shape: an enemy patrolling a patch of forest.
RESETTLE_DELAY = 1.5


@dataclass
class Attack:
    """One enemy's attack landing on one player. The room resolves it.

    `ranged` is what the room reads to decide whether this is a blow or a
    THROW. It is a flag rather than two lists because everything upstream is
    identical — the same cooldown discipline, the same target, the same
    facing — and the only thing that differs is what `Room` does with it.
    """

    enemy: Enemy
    target: Player
    #: A projectile leaves the creature instead of a blow landing. The damage
    #: arrives later, from wherever the disc gets to — which is the whole point
    #: of it (see `projectiles.py`).
    ranged: bool = False


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
    hunt_all: bool = False,
    alarm_at: tuple[float, float] | None = None,
    sight_scale: float = 1.0,
    noise_scale: float = 1.0,
) -> Outcome:
    """Advance every enemy one tick.

    `hunt_all` is the extraction chase: every living creature commits to the
    nearest player and does not give up. Sight still aims them; the commit
    itself does not wait for a cone.

    `alarm_at` is WHERE that chase came from — the platform whose pickup was
    called. It is what a creature turns to look at during its startle, and it
    is why the pack visibly reacts outward from the pad instead of everything
    simply facing the party. See `startle`.
    """
    pack = [e for e in enemies if e.alive]
    living = [p for p in players if p.alive]
    by_id = {p.id: p for p in living}
    attacks: list[Attack] = []
    despawned: list[Enemy] = []

    navigator.update(living, dt)

    # Ears before eyes. The room steps players first, so a shot fired this tick
    # is already in the list and is answered on the same tick it was fired.
    for noise in noises:
        hear(pack, noise, by_id, noise_scale)

    # Then the beam, before anything looks: an enemy the lantern is turning has
    # to be facing its new direction when its own cone is tested this tick, or
    # every glare would cost an extra frame to resolve.
    glare(pack, living, world, dt)

    #: Committed this tick. Their shout goes out after the loop, so an enemy
    #: woken by a neighbour is not itself a shouter — one hop, see the header.
    shouted: list[tuple[Enemy, Player]] = []

    for enemy in pack:
        enemy.tick_stagger(dt)
        if enemy.attack_cooldown > 0.0:
            enemy.attack_cooldown = max(0.0, enemy.attack_cooldown - dt)
        # ITS OWN CLOCK, and deliberately not nested under the one above: a
        # creature that reaches has two rate limits and they are independent,
        # so walking into a bloater's face must not also hand you a free melee
        # beat it had been saving — nor stall its shots because it happened to
        # swing once.
        if enemy.shot_cooldown > 0.0:
            enemy.shot_cooldown = max(0.0, enemy.shot_cooldown - dt)

        nearest, nearest_dist = nearest_player(enemy, living)

        # ASLEEP IS THE FIRST QUESTION AND IT SHORT-CIRCUITS EVERYTHING.
        # A sleeping creature has no cone, no patrol and no abandonment clock:
        # it was placed by the map and it is part of the map until somebody
        # comes close enough to hear. The extraction alarm does not reach it
        # either — a siren across a whole forest waking a miniboss in a den
        # nobody has found is the encounter happening to a party that never
        # chose it.
        if enemy.mode == MODE_SLEEP:
            enemy.vx = enemy.vy = 0.0
            if nearest is not None and nearest_dist <= enemy.type.wake_range:
                wake(enemy, nearest)
                shouted.append((enemy, nearest))
            continue

        # Abandonment is measured against the nearest player at ANY distance,
        # not the aggro range: an enemy idling just outside aggro is still part
        # of the fight, one on the far side of the map is not. A hunter is never
        # recycled — it is on its way to somebody, however far that is.
        if nearest is None or nearest_dist > ENEMY_DESPAWN_DIST:
            enemy.abandoned += dt
            if (
                enemy.abandoned >= ENEMY_DESPAWN_DELAY
                and enemy.mode != MODE_HUNT
                and not enemy.type.persists
            ):
                despawned.append(enemy)
        else:
            enemy.abandoned = 0.0

        seen = look(enemy, living, world, sight_scale)

        if hunt_all and nearest is not None and enemy.mode != MODE_HUNT:
            commit(enemy, nearest)
            shouted.append((enemy, nearest))
            # It has committed. It has not moved. See `startle`.
            if alarm_at is not None:
                startle(
                    enemy,
                    alarm_at[0],
                    alarm_at[1],
                    math.hypot(alarm_at[0] - enemy.x, alarm_at[1] - enemy.y),
                    world.tile_size,
                )

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
                if enemy.awareness >= ENEMY_SUSPICIOUS:
                    # Something has its attention — a beam on its back, a shot
                    # across the clearing — and it stops to look rather than
                    # carrying on with its rounds. Holding still is also what
                    # protects the facing: the next leg of a patrol would aim
                    # the head at a waypoint and undo the turn the glare just
                    # spent half a second making.
                    enemy.vx = enemy.vy = 0.0
                    enemy.wander_x = enemy.wander_y = None
                    continue
                patrol(enemy, world, dt)
                continue

        # --- hunting ---------------------------------------------------------
        # GETTING UP. The beat between a sleeper's eyes opening and its first
        # step: it stands, it howls, and only then does it come. It runs
        # before the startle for the same reason the startle runs before the
        # target lookup — a body that is not moving does not need a path — and
        # ahead of it because a pickup called next to a den must not be able
        # to skip the wake and have the thing simply be on its feet.
        if enemy.waking > 0.0:
            enemy.waking = max(0.0, enemy.waking - dt)
            enemy.vx = enemy.vy = 0.0
            if nearest is not None:
                face(enemy, nearest.x, nearest.y)
            continue

        # THE HELD BEAT. Committed, diamond lit, facing the noise, not walking.
        # It runs before the target lookup on purpose: a creature standing and
        # staring does not need a path, and stepping the chase for a body that
        # is not moving would spend a navigator query per frame on every enemy
        # on the map at exactly the tick the map is busiest.
        if enemy.startle > 0.0:
            enemy.startle = max(0.0, enemy.startle - dt)
            enemy.vx = enemy.vy = 0.0
            face(enemy, enemy.startle_x, enemy.startle_y)
            continue

        target = by_id.get(enemy.target_id or "")
        if target is None:
            # Target died or left. The nearest living player is not a
            # replacement — it never saw them. The extraction chase is the
            # exception: the whole pack is already committed to the party.
            if hunt_all and nearest is not None:
                commit(enemy, nearest)
                target = nearest
            else:
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
            not hunt_all
            and (
                enemy.lost >= ENEMY_LOSE_DELAY
                or distance > enemy.type.aggro_range
                or math.hypot(enemy.x - enemy.home_x, enemy.y - enemy.home_y) > ENEMY_LEASH_DIST
            )
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

        # --- ATTACKING FROM A DISTANCE --------------------------------------
        #
        # DRIVEN BY A FIELD. `ranged_damage` is the switch and nothing in this
        # module knows the name of the creature that has it — the second ranged
        # creature is a stat block and a sheet, exactly like the second melee
        # one was.
        #
        # It sits ABOVE the melee test, and the order is the mechanic: a
        # creature that reaches will always prefer to stand off, so the only
        # way to stop it is to get INSIDE its band. That is what makes it the
        # one threat in the game whose answer is to move toward it.
        if enemy.type.ranged_damage > 0:
            if enemy.windup > 0.0:
                # COMMITTED. Planted, facing where it aimed, and the easiest
                # thing on the map to shoot. The windup is not a courtesy to
                # the player — it is what the creature PAYS for reaching.
                face(enemy, target.x, target.y)
                enemy.vx = enemy.vy = 0.0
                enemy.stuck = 0.0
                enemy.windup -= dt
                if enemy.windup <= 0.0:
                    enemy.windup = 0.0
                    enemy.shot_cooldown = enemy.type.ranged_cooldown
                    attacks.append(Attack(enemy=enemy, target=target, ranged=True))
                continue
            if (
                enemy.type.ranged_min <= distance <= enemy.type.ranged_max
                and enemy.shot_cooldown <= 0.0
                # ONLY AT SOMETHING IT CAN SEE. `lost` is the beat after a
                # target breaks line of sight, and a creature that kept firing
                # through it would be shooting at a remembered position through
                # a tree — which reads as the map being able to hit you.
                and enemy.lost == 0.0
            ):
                face(enemy, target.x, target.y)
                enemy.vx = enemy.vy = 0.0
                enemy.stuck = 0.0
                enemy.windup = enemy.type.ranged_windup
                continue

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
def look(
    enemy: Enemy,
    living: Sequence[Player],
    world: TileMap,
    sight_scale: float = 1.0,
) -> Player | None:
    """The closest living player inside this enemy's sight cone, or None.

    Three tests, cheapest first: range, then the cone's half angle against the
    enemy's own facing, then one ray for occlusion. A single centre ray is
    enough here — unlike `has_clearance`, which asks whether a BODY fits through
    the gap, this only asks whether light does.

    Range is decided PER PLAYER by that player's own lantern switch. It is one
    dark forest: a shape gets the short reach, a shape holding a lamp gets the
    long one. That is the same trade the player took when they pressed the key.

    AND BY WHAT THEY ARE STANDING IN. Undergrowth cuts the reach against the
    player inside it (`BUSH_CONCEAL_SCALE`) — the client has always drawn a
    bush closing over a body, and until this line that picture was a lie every
    creature on the map saw through. It scales the reach rather than blocking
    the ray on purpose: cover is where you STAND, not something a single bush
    somewhere on the line grants a player standing in the open behind it.

    The lamp still overrules it. Light in a bush is a lit bush.

    AND BY THE WEATHER. `sight_scale` is the coat's own multiplier
    (`zones.WeatherRule.sight`), and it is applied to BOTH reaches rather than
    only the dark one: fog does not care whether you are carrying a lamp, and a
    coat that shortened one reach and not the other would quietly make the
    lantern a stealth item on foggy nights.

    IT SHIPS TO THE CLIENT AND MUST. Sight is symmetric in this game — the
    player's fov and this cone are a mirror pair — so the same scalar has to
    shorten the wash the client draws. Hardcoding it on either side is how a
    creature ends up seeing exactly as far as the player was shown it could, on
    a night when it could not.
    """
    cos_half = enemy.type.view_cos
    best: Player | None = None
    best_d = math.inf

    for player in living:
        reach = (
            enemy.type.view_lit_range
            if player.last_input.lantern
            else enemy.type.view_range * (
                BUSH_CONCEAL_SCALE if world.bush_at_point(player.x, player.y) else 1.0
            )
        ) * sight_scale
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
            # `sight=True`: what stops a look is not what stops a body. A
            # creature can see you over a fallen log and across the mouth of
            # the camp exit, and the client draws it that way — see
            # `world.blocks_sight`.
            if (
                combat.raycast_tiles(
                    world, enemy.x, enemy.y, dx / distance, dy / distance, distance, sight=True
                )
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


#: How long a creature stands after the extraction alarm reaches it, before
#: the smallest of them: the beat where nothing moves is the one that says
#: HEARD. Under about a third of a second it reads as network lag; much over a
#: second and the party has already run past them.
STARTLE_BASE = 0.35
#: How fast the alarm travels outward, in tiles per second. Not the speed of
#: sound — it is a READING speed. The whole point is that the player, standing
#: at the console they just pressed, watches the reaction spread away from them
#: rather than happen everywhere at once, so it moves slowly enough to see.
STARTLE_SPREAD_TILES = 44.0
#: Longest anything will stand, however far away it is. Past this the pause
#: stops being a beat and becomes a creature that failed to notice.
STARTLE_MAX = 2.2


def startle(enemy: Enemy, x: float, y: float, distance: float, tile: float) -> None:
    """Freeze a creature that has just heard the extraction, facing the noise.

    Called from `commit` under `hunt_all` and nowhere else. It is deliberately
    NOT a mode: the enemy is already hunting on the frame this runs, its
    awareness is already pinned, and the hunt diamond is already lit — what it
    is not doing yet is walking. A player watching a clearing sees every mark
    in it come up, hold, and only then start moving toward them, which is a
    sentence about cause and effect that no HUD warning can say.
    """
    if enemy.startle > 0.0:
        return
    delay = STARTLE_BASE + (distance / max(1.0, tile)) / STARTLE_SPREAD_TILES
    enemy.startle = min(STARTLE_MAX, delay)
    enemy.startle_x = x
    enemy.startle_y = y
    face(enemy, x, y)


def wake(enemy: Enemy, target: Player) -> None:
    """Open a sleeper's eyes. It commits, and then it stands there.

    THE PAUSE IS THE POINT, and it is the only free second this game gives
    anybody. The whole miniboss encounter is a decision the player gets to
    make BEFORE anything is decided for them: they find a den, they see a
    shape breathing in it, and they choose. Waking it has to be the last beat
    of that decision rather than the end of it — so it gets up, it calls its
    pack, and a party that has already turned round is already leaving.

    It is a commit, not a notice: nothing about a sleeping animal noticing you
    should be gradual, and the diamond is full on the frame its eyes open.
    """
    if enemy.mode == MODE_SLEEP:
        enemy.waking = ALPHA_WAKE_DELAY
    commit(enemy, target)


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
    """End a hunt: head home, and let the diamond empty.

    A sleeper goes home and goes BACK TO SLEEP (see `patrol`), which is what
    makes escaping a miniboss a real outcome rather than a delay. The den is
    still there, it is still occupied, and the party has to decide about it
    all over again — that is the encounter working, not the encounter being
    skipped.
    """
    enemy.mode = MODE_RETURN
    enemy.target_id = None
    enemy.awareness = 0.0
    enemy.lost = 0.0
    enemy.waking = 0.0
    enemy.vx = enemy.vy = 0.0
    enemy.wander_x = enemy.wander_y = None
    enemy.wander_wait = 0.0


def shout(spotter: Enemy, target: Player, pack: Sequence[Enemy]) -> None:
    """One enemy spotting a player is every enemy near it spotting them.

    TWO SHAPES, AND THE SECOND ONE IS A HOWL. The default is a nudge: whatever
    is within `ENEMY_ALERT_SHARE_DIST`, one hop, regardless of what it is. A
    creature with `pack_call_tiles` instead CALLS ITS OWN PACK, four times as
    far — which is the entire difference between four animals that happen to
    be in the same field and a pack.

    Restricting it to the pack is the half worth arguing about. A howl that
    woke the zombies too would be strictly better than a shout at every range,
    and the wolf's whole design is that it is not a better zombie: it is fast,
    fragile, and it fights with the other wolves. One creature's social range
    must not become a general-purpose alarm, or every future creature
    inherits it by accident.

    IT IS `EnemyType.pack` AND NOT THE TYPE KEY, which is the correction worth
    keeping. Keyed on the type, the alpha's howl reached exactly nobody —
    there is only ever one of him — so the loudest call in the game was the
    one attached to the creature with nothing to call. A leader brings the
    animals that are already out there.

    **A SLEEPER NEVER ANSWERS**, and this is the one that cost something worth
    naming. A wolf howling next to a den waking its alpha is a good scene, and
    it is also the encounter happening to a party that never found the den: a
    call carries thirty tiles, well past the lantern, so somebody shooting at
    a pack across a clearing would wake a miniboss they cannot see and have no
    reason to expect. What reaches a sleeper stays the three things that are
    about IT — a body close enough to hear, a noise, a bullet — because those
    are the three a player can choose not to do.
    """
    reach = spotter.type.pack_call_range
    group = spotter.type.pack
    calling = reach > 0.0 and bool(group)
    if not calling:
        reach = ENEMY_ALERT_SHARE_DIST
    reach2 = reach * reach
    for other in pack:
        if other is spotter or other.mode in (MODE_HUNT, MODE_SLEEP):
            continue
        if calling and other.type.pack != group:
            continue
        if (other.x - spotter.x) ** 2 + (other.y - spotter.y) ** 2 > reach2:
            continue
        commit(other, target)


def hear(
    pack: Sequence[Enemy],
    noise: Noise,
    by_id: dict[str, Player],
    noise_scale: float = 1.0,
) -> None:
    """Fold one noise into every enemy within its radius.

    Awareness gain tapers from the centre outward and overshoots on purpose
    (NOISE_ALERT_GAIN > 1), so the middle of a gunshot is an instant hunt and
    the outer band only turns heads. An enemy already hunting has nothing to
    learn from it.

    `noise_scale` is the weather's (`zones.WeatherRule.noise`), applied HERE
    rather than where each noise is made. Every sound in the game — a gunshot,
    the extraction siren, a horde's howl, a vault being forced — goes through
    this one door, and a coat applied at the four call sites instead would be
    missing from the fifth.
    """
    radius = noise.radius * noise_scale
    if radius <= 0.0:
        return
    source = by_id.get(noise.source_id or "")
    for enemy in pack:
        if enemy.mode == MODE_HUNT:
            continue
        distance = math.hypot(noise.x - enemy.x, noise.y - enemy.y)
        if distance > radius:
            continue
        # A SLEEPER EITHER WAKES OR HEARS NOTHING. Awareness is what the hunt
        # diamond is drawn from, and a curled body with a half-full meter over
        # it would tell the player something is deciding about them when the
        # thing is still asleep. So the taper does not apply: inside the
        # radius it gets up, outside it the sound never happened.
        if enemy.mode == MODE_SLEEP:
            if source is not None:
                wake(enemy, source)
            continue
        face(enemy, noise.x, noise.y)
        enemy.awareness = min(
            # THE TAPER USES THE SCALED RADIUS TOO. Against the raw one, a
            # rainy night would shorten how far a sound reached and leave the
            # gain at the edge of that shorter circle still counted as though
            # the sound were quiet — so the last creature to hear a shot would
            # react as hard as one standing on top of it.
            1.0, enemy.awareness + NOISE_ALERT_GAIN * (1.0 - distance / radius)
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
    # Shooting a sleeping animal wakes it — with the same beat, because the
    # beat is the telegraph and a player who opened with a rifle round has
    # earned the same second of warning as one who walked too close.
    wake(enemy, source)


def glare(pack: Sequence[Enemy], living: Sequence[Player], world: TileMap, dt: float) -> None:
    """The lantern beam falling on something that is not looking at you.

    For every player holding a lit lamp, everything inside the bright part of
    their beam TURNS TOWARD IT and grows uneasy. It does not get spotted by
    this — awareness is capped below the commit line — it gets pointed at you,
    and then `look` does the rest a moment later.

    That is deliberately the long way round. A beam that spotted people
    directly would make the lantern a button nobody presses; a beam that swings
    heads around gives the player a second to kill the light and back off, and
    makes the cost of seeing something the fact that it is now facing you.

    Occlusion is the same single ray `look` uses — light that cannot reach an
    enemy cannot be noticed by it.
    """
    reach = ENEMY_GLARE_DIST
    if reach <= 0.0:
        return
    cos_half = math.cos(math.radians(VISION_CONE_DEGREES) / 2)

    for player in living:
        if not player.last_input.lantern:
            continue
        for enemy in pack:
            # A BEAM DOES NOT WAKE ANYTHING. `glare` turns heads and makes
            # bodies uneasy, which are both things a creature with its eyes
            # shut cannot do — and a lantern that woke a den from across a
            # clearing would take the decision away from the party holding it.
            if (
                enemy.mode in (MODE_HUNT, MODE_SLEEP)
                or enemy.awareness >= ENEMY_GLARE_CAP
            ):
                continue
            dx = enemy.x - player.x
            dy = enemy.y - player.y
            distance = math.hypot(dx, dy)
            if distance > reach or distance <= 1e-6:
                continue
            # Inside the beam, not merely inside its radius: what is being
            # noticed is where the player is pointing.
            if (dx * player.aim_x + dy * player.aim_y) / distance < cos_half:
                continue
            # Light, not a bullet: a log you can see over does not hide you
            # from the lamp any more than it hides you from an enemy's eyes.
            if (
                combat.raycast_tiles(
                    world, player.x, player.y, dx / distance, dy / distance, distance, sight=True
                )
                < distance - 1e-3
            ):
                continue
            # Brighter the closer it is standing to the lamp.
            strength = 1.0 - distance / reach
            enemy.awareness = min(
                ENEMY_GLARE_CAP, enemy.awareness + ENEMY_GLARE_RATE * strength * dt
            )
            turn_towards(enemy, player.x, player.y, dt)


def face(enemy: Enemy, x: float, y: float) -> None:
    """Point the enemy's facing (and so its sight test) at a world point."""
    dx = x - enemy.x
    dy = y - enemy.y
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return
    enemy.aim_x = dx / length
    enemy.aim_y = dy / length


def turn_towards(
    enemy: Enemy, x: float, y: float, dt: float, degrees_per_sec: float = ENEMY_TURN_DEGREES
) -> None:
    """Swing the facing toward a point at a bounded rate, never instantly.

    Nothing here ever snaps its head. A body that changes facing between two
    frames reads as a turret, and a cone that jumped would be a state change
    rather than a thing happening in front of the player — which is the entire
    warning both the glare and the patrol are there to give.
    """
    dx = x - enemy.x
    dy = y - enemy.y
    if math.hypot(dx, dy) <= 1e-6:
        return
    turn_to(enemy, math.atan2(dy, dx), dt, degrees_per_sec)


def turn_to(enemy: Enemy, wanted: float, dt: float, degrees_per_sec: float) -> None:
    """Ease the facing toward an absolute angle at a bounded rate."""
    current = math.atan2(enemy.aim_y, enemy.aim_x)
    # Shortest way round: an enemy that took the long way would spin away from
    # the thing it is turning to look at.
    delta = (wanted - current + math.pi) % math.tau - math.pi
    step = math.radians(degrees_per_sec) * dt
    angle = wanted if abs(delta) <= step else current + math.copysign(step, delta)
    enemy.aim_x = math.cos(angle)
    enemy.aim_y = math.sin(angle)


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
            enemy.mode = MODE_SLEEP if enemy.type.sleeps else MODE_IDLE
            enemy.wander_wait = random.uniform(ENEMY_WANDER_PAUSE_MIN, ENEMY_WANDER_PAUSE_MAX)
            enemy.vx = enemy.vy = 0.0
            return
        if enemy.stuck >= RESETTLE_DELAY:
            # A SLEEPER NEVER RESETTLES. Accepting wherever it got wedged as
            # its new home is the right answer for a zombie — one patch of
            # forest is as good as another — and the wrong one for something
            # whose whole encounter is a PLACE. A miniboss that gave up
            # halfway back and curled up in a thicket would leave its den
            # empty and put itself somewhere with no story in it.
            if enemy.type.sleeps:
                enemy.stuck = 0.0
                walk(enemy, dx, dy, speed, world, dt)
                return
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
    """Shamble toward an offset at `speed`, turning into it rather than at it.

    The head eases round at ENEMY_IDLE_TURN_DEGREES and the body walks along
    whatever the head is currently pointing at, so a new waypoint is a CURVE
    rather than a change of direction. That is the whole difference between a
    thing wandering the woods and a sprite being teleported through headings —
    and, since the sight test is measured off this facing, it is also what
    stops a clearing of heads from flicking about like searchlights.
    """
    if math.hypot(dx, dy) <= 1e-6:
        enemy.vx = enemy.vy = 0.0
        return
    turn_towards(enemy, enemy.x + dx, enemy.y + dy, dt, ENEMY_IDLE_TURN_DEGREES)
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


def gait(enemy: Enemy) -> float:
    """0..1 walk scale from stacked gun hits. 0 plants them.

    Written onto vx/vy inside `move` so the snapshot already carries the slow
    and interpolation does the rest — stagger itself never goes on the wire.
    """
    if enemy.stagger >= ENEMY_STAGGER_STOP:
        return 0.0
    return max(0.0, 1.0 - enemy.stagger)


def move(enemy: Enemy, world: TileMap, dt: float) -> None:
    """Axis-separated move against the tile grid — the player's rule, reused.

    Also keeps the stuck timer: walls silently eat one or both axes here, so
    this is the only place that knows the difference between "walking" and
    "walking into something".
    """
    scale = gait(enemy)
    if scale < 1.0:
        enemy.vx *= scale
        enemy.vy *= scale

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

    AND IT SCALES WITH THE NIGHT. It did not use to — neither this module nor
    `enemies.py` had ever heard of the day — while the map it fills triples
    across a run, so the forest got measurably emptier every night the party
    survived. Three numbers walk with the day and they are deliberately the
    three about PRESSURE rather than about any individual creature:

      how many the forest holds  `ENEMY_DAY_POPULATION`
      how fast it refills        `ENEMY_DAY_RATE`
      how big a wave is          `ENEMY_DAY_GROUP_TILT`

    NOT their health and NOT their damage, which is the tempting fourth and
    the wrong one. A zombie with 90 HP on night five is the same encounter
    taking three times as long, and a player reads that as their gun getting
    worse — the classic bullet-sponge trade, where the game's answer to "make
    it harder" is "make it slower". Now that a crowd can actually kill
    (`config.MELEE_IMMUNITY`), population IS the difficulty knob: the same
    zombie is frightening in sixes and was never frightening alone.
    """

    def __init__(self, spawn_points: Sequence[tuple[float, float]], day: int = 1):
        self.spawn_points = spawn_points
        #: Which night this forest is. Held rather than passed per call because
        #: it cannot change while a map is alive — a new night is a new map and
        #: therefore a new director (`Room._swap_map`).
        self.day = max(1, day)
        self.timer = ENEMY_FIRST_SPAWN_DELAY
        #: HOW LONG THE PARTY HAS BEEN ON THIS MAP, in seconds. The night's own
        #: clock, and the thing the design law claimed existed and did not —
        #: see `config.ENEMY_NIGHT_RAMP`. Zero on arrival because a new night
        #: is a new director (`Room._swap_map`), so nothing has to reset it.
        self.elapsed = 0.0
        # The horde's CLOCK lives in `events.py` now — see `plan_horde`. This
        # director owns how full the forest is, not when it gets a moment.

    @property
    def population_scale(self) -> float:
        """What the day AND the night so far multiply the population by.

        TWO TERMS, MULTIPLIED. The day says how full this forest starts; the
        night says how much worse it has got since the party walked in. They
        multiply rather than add because they are answering different
        questions — "which night is this" and "how long have you been out" —
        and a party on night eight who leaves after two minutes should meet
        night eight's forest, not night three's.
        """
        return self.day_scale * self.night_scale

    @property
    def day_scale(self) -> float:
        """What the day alone multiplies the population ceiling by."""
        return 1.0 + ENEMY_DAY_POPULATION * (self.day - 1)

    @property
    def night_scale(self) -> float:
        """What time-on-this-map multiplies it by. 1.0 for the first minute.

        THE GRACE IS NOT POLITENESS. A party walks out of the corridor with an
        empty bag and the first platform a clearing away; taking the night away
        from them before they have found it would make the opening a race
        rather than an arrival, which is the exact failure the night clock was
        removed for.
        """
        over = max(0.0, self.elapsed - ENEMY_NIGHT_GRACE)
        return min(ENEMY_NIGHT_RAMP_MAX, 1.0 + ENEMY_NIGHT_RAMP * (over / 60.0))

    @property
    def interval(self) -> float:
        """Seconds between waves tonight, floored so groups stay groups.

        THE NIGHT'S RAMP IS IN HERE TOO, and it has to be: the cap says how
        many the forest HOLDS and this says how fast it refills toward that
        cap. Raising only the ceiling makes a late night one that slowly
        becomes crowded if nobody fights; raising both makes it one that comes
        back at you after you have cleared it, which is the thing a party
        actually feels.
        """
        pace = (1.0 + ENEMY_DAY_RATE * (self.day - 1)) * self.night_scale
        return max(ENEMY_SPAWN_INTERVAL_MIN, ENEMY_SPAWN_INTERVAL / pace)

    def cap(self, living: int) -> int:
        """The ceiling for this many living players, on this night.

        BOTH TERMS SCALE, and the total is what stops that compounding into a
        slideshow: a full room on night ten is capped at 32 * 3.97 rather than
        at 6 * 4 * 3.97, so the per-player number is what a solo run feels and
        the total is what a party shares.
        """
        scale = self.population_scale
        return int(
            min(
                ENEMY_MAX_TOTAL * scale,
                ENEMY_MAX_PER_PLAYER * scale * max(1, living),
                # THE BUDGET, under everything. See `config.ENEMY_HARD_CAP`:
                # the day and the night multiply, and two multiplied curves
                # reach numbers that are neither drawable nor survivable.
                ENEMY_HARD_CAP,
            )
        )

    def update(
        self, dt: float, players: Iterable[Player], enemy_count: int
    ) -> list[tuple[EnemyType, float, float]]:
        living = [p for p in players if p.alive]
        if not living or not self.spawn_points:
            return []

        # THE NIGHT'S OWN CLOCK, and it only runs while somebody is standing.
        # A party wiped to one downed body is not "waiting out there getting
        # into trouble" — they are finished, and winding the forest up while
        # the last of them bleeds would be the game kicking a corpse.
        self.elapsed += dt

        self.timer -= dt
        if self.timer > 0.0:
            return []
        self.timer = self.interval

        room = self.cap(len(living)) - enemy_count
        if room <= 0:
            return []

        spot = self.pick_spot(random.choice(living), living)
        if spot is None:
            return []

        # THE TYPE IS ROLLED BEFORE THE SIZE, because some creatures do not
        # come alone. A pack of one is a stray dog: `EnemyType.group_min` is
        # the floor, and it is on the stat block rather than in the weights
        # table so a second social creature costs nothing here.
        kind = self.pick_type()
        # A group clipped by the cap is still a group: three of four is better
        # than skipping the wave and leaving the map empty for another interval.
        size = min(max(self.pick_size(), kind.group_min), room)
        return [(kind, *place) for place in self.scatter(spot, size)]

    def plan_horde(self, players: Iterable[Player]) -> tuple[float, float, float, int] | None:
        """WHERE a wave would land: `(x, y, bearing, size)`, or None.

        THE SCHEDULE IS NOT HERE ANY MORE and that is the point of the split.
        This director keeps a forest populated — a background process nobody is
        supposed to notice. WHEN a wave happens is a question about the night's
        script, and it belongs with every other such question in `events.py`.
        What is left here is the half that is genuinely about population: which
        creature, how many for the day, and a bearing anchored on a real player
        against this map's own free-tile list.

        WHY IT RETURNS A PLACE RATHER THAN SPAWNING. The warning has to go out
        before the bodies do (`config.HORDE_TELEGRAPH`), and the thing being
        warned about is a BEARING — "they are coming from over there". So the
        director answers where, `Room` holds it for a few seconds while the
        howl carries, and only then asks for the bodies. A horde that spawned
        on the frame it was decided would be a horde nobody was warned about,
        and with the run permanent that is a deleted run rather than a scare.
        """
        living = [p for p in players if p.alive]
        if not living or not self.spawn_points:
            return None

        anchor = random.choice(living)
        bearing = random.uniform(0.0, math.tau)
        reach = TILE_SIZE * HORDE_SPAWN_TILES
        x = anchor.x + math.cos(bearing) * reach
        y = anchor.y + math.sin(bearing) * reach
        size = max(2, round(HORDE_SIZE + HORDE_SIZE_PER_DAY * (self.day - 1)))
        return x, y, bearing, size

    def horde_places(
        self, x: float, y: float, bearing: float, size: int
    ) -> list[tuple[EnemyType, float, float]]:
        """Bodies for one wave, landed in an ARC on the far side of `bearing`.

        AN ARC, NOT A RING, and that is what makes a horde answerable. A wave
        you can turn to face is a fight with a shape to it — back into
        something, put the axe where they are coming from, decide whether to
        run through the gap. The same bodies spread evenly around the party is
        not a harder version of that, it is a different and much worse thing:
        an encounter with no correct answer, which on a permanent run is just a
        death with extra steps.

        They are placed against the map's own free-tile list like every other
        spawn, so a wave can no more arrive inside a tree than a wanderer can.
        """
        if not self.spawn_points:
            return []
        spread = math.radians(HORDE_ARC_DEGREES)
        reach = TILE_SIZE * HORDE_SPAWN_TILES
        out: list[tuple[EnemyType, float, float]] = []
        # ONE TYPE FOR THE WHOLE WAVE. A horde is a thing that arrives, and a
        # mixed one reads as the ordinary director having a busy minute.
        kind = self.pick_type()
        for index in range(size):
            offset = ((index / max(1, size - 1)) - 0.5) * spread if size > 1 else 0.0
            angle = bearing + offset
            # A little depth as well as width, so they arrive as a body of
            # bodies rather than as a rank.
            dist = reach * random.uniform(0.82, 1.12)
            want_x = x - math.cos(bearing) * reach + math.cos(angle) * dist
            want_y = y - math.sin(bearing) * reach + math.sin(angle) * dist
            spot = self._nearest_free(want_x, want_y)
            if spot is not None:
                out.append((kind, spot[0], spot[1]))
        return out

    def _nearest_free(self, x: float, y: float) -> tuple[float, float] | None:
        """The closest tile the map will actually take. Sampled, not searched —
        the free list is thousands of entries and this runs a handful of times
        a night."""
        best: tuple[float, float] | None = None
        best_d2 = float("inf")
        for _ in range(SPAWN_ATTEMPTS * 3):
            point = random.choice(self.spawn_points)
            d2 = (point[0] - x) ** 2 + (point[1] - y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = point
        return best

    def pick_size(self) -> int:
        """How many arrive together, tilted toward the big end by the night.

        The tilt is applied as `(1 + tilt*(day-1)) ** index`, so night one is
        the authored table untouched and every night after bends the SAME
        curve rather than switching to a second hand-written one. By night ten
        a four is likelier than a one, which is the difference between a forest
        with things in it and a forest that sends waves.
        """
        bend = 1.0 + ENEMY_DAY_GROUP_TILT * (self.day - 1)
        weights = [w * bend**i for i, w in enumerate(ENEMY_GROUP_WEIGHTS)]
        return random.choices(ENEMY_GROUP_SIZES, weights=weights, k=1)[0]

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
