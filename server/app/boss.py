"""THE SAWYER: the night's last thing, and the only enemy with a name on screen.

He is not an `EnemyType` and this is not `ai.py`. Everything in that module is
built for a CROWD — a hundred bodies that notice, walk, swing and are rate
limited against each other, whose whole behaviour is "come here and touch you".
A boss is the opposite object: one body, always aware, whose entire design is
the ORDER of what it does and how long each part of it lasts. Sharing the
crowd's code would have meant an `Enemy` with a mode field nothing else uses
and a special case in every function of `ai.py`.

What he does share is the CAPSULE. `Boss` exposes `radius` / `capsule_y0` /
`capsule_y1` / `x` / `y` / `id` exactly the way `Player` and `Enemy` do, so
`combat.raycast` and `combat.sweep` hit him without knowing he exists. Every
gun and the knife work on him on the day he ships, and no weapon will ever
need a boss branch.

THE ART OWNS THE CLOCK.
`assets/processed/sawyer/manifest.json` carries every clip's frame count, its
fps and its EVENT frames — `hit`, `release`, `roar`, `impact`. This module
reads that file and derives its own timings from it, so a move's windup is
literally the number of frames the boss spends raising the bar. The rule that
follows is the important one:

    THE TELEGRAPH IS THE MECHANIC. A player learns this fight by watching the
    windup, so the windup has to be the same length on screen and in the
    simulation. Hard-code 0.5s here and re-time the clip in `make_sawyer.py`
    and the fight silently becomes unfair — the bar lands before the animation
    says it does, and nobody can see why they died.

Change a clip's length in the generator and the fight re-times itself. That is
the whole reason the manifest is read at import instead of copied.

FOUR MOVES, FOUR SHAPES, ONE RANGE BAND EACH.
    CHOP    close, a point, the heaviest. Lands where he is looking.
    SWEEP   close, a circle, hits everything. The answer to crowding him.
    RIP     far, a crescent that leaves the bar and keeps going. The answer to
            standing off and plinking.
    REV     nothing. It is the enrage and the free window in one.
Two attacks that punish the same mistake are one attack, so the picker
(`_choose`) is a RANGE decision first and a dice roll second.

HE IS FAIR BECAUSE HE IS SLOW AND COMMITTED. He walks slower than a player
runs, every move roots him for its whole length, and the recovery on the chop
is the longest window in the fight. Everything that makes him dangerous is
positional: the sweep punishes standing next to him, the crescent punishes
standing still far away, and the roar means the next one comes faster.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    BOSS_ATTACK_COOLDOWN,
    BOSS_CHOP_DAMAGE,
    BOSS_CHOP_REACH_TILES,
    BOSS_CREST_DAMAGE,
    BOSS_CREST_LIFE,
    BOSS_CREST_RADIUS_TILES,
    BOSS_CREST_SPEED_TILES,
    BOSS_ENRAGE_AT,
    BOSS_ENRAGE_RATE,
    BOSS_ENRAGE_SPEED,
    BOSS_HIT_TILES_R,
    BOSS_HP_BASE,
    BOSS_HP_PER_EXTRA,
    BOSS_MELEE_IMMUNITY,
    BOSS_RIP_RANGE_TILES,
    BOSS_SPEED_TILES,
    BOSS_SPRITE_TILES_H,
    BOSS_STOMP_DAMAGE,
    BOSS_STOMP_REACH_TILES,
    BOSS_SWEEP_DAMAGE,
    BOSS_SWEEP_REACH_TILES,
    BOSS_TURN_DEGREES,
    TILE_SIZE,
)
from .world import TileMap

#: The art's own copy of the clock. Read once, at import, exactly the way
#: `loot.py` reads the atlas it takes frame indices from.
MANIFEST: dict = json.loads(
    (Path(__file__).resolve().parents[2] / "assets/processed/sawyer/manifest.json")
    .read_text()
)
CLIPS: dict = MANIFEST["clips"]

#: His name, on screen, over the bar. The one enemy in the game that has one.
NAME = "O SERRADOR"
TITLE = "capataz da mata"

# --- states -------------------------------------------------------------------
# The order below is the order they can happen in. `sleep` is the state he is
# in for the whole walk down the corridor: he is on the map, he has a hitbox,
# and nothing about him ticks until somebody steps into the ring.

SLEEP = "sleep"
ARRIVE = "arrive"      # the cinematic. Invulnerable, unstoppable, on rails.
IDLE = "idle"
WALK = "walk"
WINDUP = "windup"      # the telegraph. He is rooted and the clip is playing.
STRIKE = "strike"      # the frames that hurt.
RECOVER = "recover"    # the punish window. Rooted, and the longest of the three.
DEAD = "dead"


def _clip(name: str) -> tuple[float, dict]:
    """A clip's length in seconds, and its event frames as seconds."""
    spec = CLIPS[name]
    fps = float(spec["fps"])
    length = spec["frames"] / fps
    events = {key: value / fps for key, value in (spec.get("events") or {}).items()
              if isinstance(value, (int, float))}
    return length, events


@dataclass(frozen=True)
class Move:
    """One attack, timed off its own animation.

    `windup` is measured to the clip's own event frame and `recover` is
    whatever is left of the clip after the hitbox closes. Nothing here is a
    round number on purpose — they are all the art's numbers.
    """

    key: str
    #: Seconds from the start of the clip to the frame the blow lands.
    windup: float
    #: Seconds the hitbox is live. Short: a boss whose swing lingers is a boss
    #: that hits you for walking behind it.
    active: float
    #: Seconds rooted afterwards. THE PUNISH WINDOW, and it is drawn — the
    #: chop's is long because the clip spends four frames wrenching the bar
    #: back out of the floor.
    recover: float
    damage: int
    reach_tiles: float
    #: Half-angle of the arc it covers, in degrees. 180 is everything.
    arc_degrees: float
    #: The band this move is FOR. The picker never rolls a move whose band the
    #: target is not standing in — see `_choose`.
    min_tiles: float
    max_tiles: float

    @property
    def length(self) -> float:
        return self.windup + self.active + self.recover

    @property
    def reach(self) -> float:
        return TILE_SIZE * self.reach_tiles

    def client_payload(self) -> dict:
        """What the client needs to draw the bar's PATH through this move.

        Three numbers and no more. The client's `boss-vfx.tipAt` puts a trail
        on the nose of the bar, and to do that it has to know where in the
        swing the bar is: `windup` and `active` bracket the fast part, and
        `reach` is how far out the nose rides.

        It used to carry the hitbox as well — `arcDegrees`, `damage` — for a
        ground telegraph that has since been cut (see the client module's
        header for why). Those went with it rather than being left on the
        payload: a field nothing reads is a field the next person has to work
        out whether they are allowed to change.
        """
        return {
            "key": self.key,
            "windup": round(self.windup, 4),
            "active": round(self.active, 4),
            "reach": round(self.reach, 2),
        }


def moves_payload() -> dict:
    """Every move's shape and clock, for `welcome.config.bossMoves`."""
    return {key: move.client_payload() for key, move in MOVES.items()}


def crescent_payload() -> dict:
    """The thrown crescent's own geometry.

    `rip`'s `reach` is zero — nothing leaves his hands that touches anybody,
    the crescent does — so the client sizes the throw's trail off this
    instead. `reach` is speed times life: how far the simulation will actually
    carry the thing.
    """
    return {
        "speed": round(TILE_SIZE * BOSS_CREST_SPEED_TILES, 2),
        "life": BOSS_CREST_LIFE,
        "radius": round(TILE_SIZE * BOSS_CREST_RADIUS_TILES, 2),
        "reach": round(TILE_SIZE * BOSS_CREST_SPEED_TILES * BOSS_CREST_LIFE, 2),
    }


def _move(clip: str, event: str, *, damage: int, reach: float, arc: float,
          min_tiles: float, max_tiles: float, active: float = 0.14) -> Move:
    length, events = _clip(clip)
    windup = events.get(event, length * 0.5)
    return Move(
        key=clip,
        windup=windup,
        active=active,
        recover=max(0.12, length - windup - active),
        damage=damage,
        reach_tiles=reach,
        arc_degrees=arc,
        min_tiles=min_tiles,
        max_tiles=max_tiles,
    )


#: THE FOUR. Each one's band is what it is an answer to, and the bands overlap
#: only where a real choice exists.
#:
#: `sweep`'s arc is 180: it is the only move that cannot be dodged by standing
#: behind him, and that is deliberately the answer to a party surrounding a
#: rooted boss. `chop`'s is narrow and long — step out of the line and it
#: misses, which is the move the fight is meant to teach first.
CHOP = _move("chop", "hit", damage=BOSS_CHOP_DAMAGE, reach=BOSS_CHOP_REACH_TILES,
             arc=55.0, min_tiles=0.0, max_tiles=4.4)
SWEEP = _move("sweep", "spin", damage=BOSS_SWEEP_DAMAGE, reach=BOSS_SWEEP_REACH_TILES,
              arc=180.0, min_tiles=0.0, max_tiles=3.6, active=1.5)
RIP = _move("rip", "release", damage=BOSS_CREST_DAMAGE, reach=0.0, arc=0.0,
            min_tiles=4.0, max_tiles=BOSS_RIP_RANGE_TILES)
REV = _move("rev", "roar", damage=0, reach=0.0, arc=0.0,
            min_tiles=0.0, max_tiles=99.0)

MOVES: dict[str, Move] = {m.key: m for m in (CHOP, SWEEP, RIP, REV)}

#: The arrival cinematic's length and the frame he lands on. Both the server's
#: (it holds input for exactly this long) and the client's (it plays the clip),
#: which is the point of taking them from one file.
ARRIVE_LENGTH, ARRIVE_EVENTS = _clip("arrive")
ARRIVE_IMPACT = ARRIVE_EVENTS.get("impact", 0.5)
DEATH_LENGTH, _DEATH_EVENTS = _clip("death")


@dataclass
class Crescent:
    """What leaves the bar on `rip`. A disc that travels and expires.

    It is not a bullet and it does not use `combat.raycast`: a raycast is a
    line that arrives instantly, and the entire point of this attack is that
    the thing is SLOW ENOUGH TO WALK AWAY FROM. It moves a fixed distance per
    tick and tests a circle, so a player who keeps moving is never hit by it
    and a player standing still plinking always is.
    """

    id: int
    x: float
    y: float
    dx: float
    dy: float
    life: float
    #: Everybody it has already hit. It passes THROUGH a party rather than
    #: stopping on the first body — but it only ever bills each of them once.
    struck: set[str] = field(default_factory=set)

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
            "t": round(self.life, 2),
        }


@dataclass
class Outcome:
    """What one tick of the boss did. `Room` applies all of it."""

    #: `(player, damage, source_x, source_y)` — melee landings.
    hits: list = field(default_factory=list)
    #: Things the client turns into shake, dust, sound and light.
    events: list[dict] = field(default_factory=list)
    #: True on the tick he finishes dying.
    died: bool = False
    #: True on the tick the cinematic ends and the fight starts.
    engaged: bool = False


@dataclass
class Boss:
    """One Sawyer. Position, a clock, and what he is in the middle of."""

    id: str
    x: float
    y: float
    max_hp: int
    hp: int = 0
    aim_x: float = 0.0
    aim_y: float = 1.0
    state: str = SLEEP
    #: Seconds spent in the current state. The simulation's clock: it is what
    #: `update` compares against a move's windup and recovery.
    timer: float = 0.0
    #: Seconds into the current CLIP, which is not the same thing.
    #:
    #: A move is three states (windup, strike, recover) and ONE animation. The
    #: states exist because the hitbox opens between them; the animation does
    #: not split, because a swing is a swing. So the playhead has to run across
    #: all three, and it is kept here rather than reconstructed on the client
    #: from `timer` — the client would need this module's phase lengths to do
    #: it, and the first version that tried restarted the clip on the exact
    #: frame the bar landed. The boss looked like he was winding up again while
    #: the blow was being dealt.
    clip_t: float = 0.0
    #: The move being performed, while `state` is one of the three attack
    #: states. None otherwise.
    move: Move | None = None
    #: Who he is walking at. Re-picked when he commits to a move, not every
    #: tick — a boss that re-targets mid-swing swings at nobody.
    target_id: str | None = None
    #: Seconds until he may start another move. What separates a fight from a
    #: blender, and the one number that `rev` changes.
    cooldown: float = 0.0
    #: Under `BOSS_ENRAGE_AT` of his health he moves faster and waits less.
    enraged: bool = False
    #: Set for the one tick the enrage happens on, so `Room` can broadcast it.
    just_enraged: bool = False
    #: Live crescents, and the id counter that names them.
    crescents: list[Crescent] = field(default_factory=list)
    _crest_id: int = 0
    #: Per-victim melee i-frames, by player id. His own, separate from
    #: `MELEE_IMMUNITY`: a sweep that ticks for 1.5 seconds would otherwise
    #: bill the same body forty-five times.
    _immune: dict[str, float] = field(default_factory=dict)
    #: Rolled per move so the same two do not alternate forever.
    _rng: random.Random = field(default_factory=random.Random)
    #: What he did last. The picker refuses to repeat it twice running unless
    #: it is the only move the range allows.
    _last: str = ""

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.max_hp

    # --- the capsule, shared verbatim with Player and Enemy ------------------
    @property
    def radius(self) -> float:
        return TILE_SIZE * BOSS_HIT_TILES_R

    @property
    def sprite_height(self) -> float:
        return TILE_SIZE * BOSS_SPRITE_TILES_H

    @property
    def half_height(self) -> float:
        return TILE_SIZE * 0.5

    @property
    def capsule_y0(self) -> float:
        return self.y + self.half_height - self.radius

    @property
    def capsule_y1(self) -> float:
        return self.y + self.half_height - self.sprite_height + self.radius

    @property
    def alive(self) -> bool:
        return self.state != DEAD or self.timer < DEATH_LENGTH

    @property
    def vulnerable(self) -> bool:
        """He can be hurt from the moment the cinematic ends until he falls.

        Deliberately NOT "except while attacking". Invulnerability frames on a
        boss teach the player that their damage is a suggestion, and every
        window this fight has is a POSITIONAL one — the recovery on the chop is
        a real four-frame gift, and it is worth more than an i-frame because
        you can see it coming.
        """
        return self.state not in (SLEEP, ARRIVE, DEAD)

    def to_payload(self) -> dict:
        row = {
            "id": self.id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "ax": round(self.aim_x, 3),
            "ay": round(self.aim_y, 3),
            "hp": self.hp,
            "max": self.max_hp,
            "s": self.state,
            # THE CLIP'S PLAYHEAD, not the state's clock. See `clip_t`: the
            # client draws frame `t * fps` and does no arithmetic of its own,
            # which is the only arrangement in which the frame on screen and
            # the frame the hitbox opens on are the same frame.
            "t": round(self.clip_t, 3),
            "m": self.move.key if self.move is not None else None,
        }
        if self.enraged:
            row["rage"] = True
        if self.crescents:
            row["crest"] = [c.to_payload() for c in self.crescents]
        return row


# --- the tick ------------------------------------------------------------------


def update(boss: Boss, living: list, world: TileMap, dt: float) -> Outcome:
    """One tick. Returns what `Room` has to apply; touches nothing outside `boss`."""
    out = Outcome()
    boss.timer += dt
    boss.clip_t += dt
    for key in list(boss._immune):
        boss._immune[key] -= dt
        if boss._immune[key] <= 0.0:
            boss._immune.pop(key, None)

    _step_crescents(boss, living, world, dt, out)

    if boss.state == SLEEP:
        return out

    if boss.state == DEAD:
        return out

    if boss.state == ARRIVE:
        # ON RAILS. He is invulnerable, he does not steer, and the only thing
        # that happens is the clock running out — which is the definition of a
        # cinematic and the reason it is a state rather than a flag.
        if boss.timer >= ARRIVE_LENGTH:
            _enter(boss, IDLE)
            out.engaged = True
        return out

    if boss.cooldown > 0.0:
        boss.cooldown = max(0.0, boss.cooldown - dt)

    target = _target(boss, living)
    if boss.state in (IDLE, WALK):
        _step_free(boss, target, world, dt, out)
        return out

    move = boss.move
    if move is None:
        _enter(boss, IDLE)
        return out

    # Rooted for the whole move. He still TURNS during the windup — slowly,
    # and only during the windup — which is what makes the telegraph readable
    # as "he is coming for YOU" without making it undodgeable.
    if boss.state == WINDUP:
        if target is not None and move.key != REV.key:
            _turn(boss, target, dt, BOSS_TURN_DEGREES * 0.55)
        if boss.timer >= move.windup:
            _enter(boss, STRIKE)
            _land(boss, move, living, out)
        return out

    if boss.state == STRIKE:
        # The sweep is the one move whose hitbox is open for more than a frame,
        # so it keeps testing — that is what makes standing next to a spinning
        # chainsaw for a second and a half cost you.
        if move.key == SWEEP.key:
            _land(boss, move, living, out)
        if boss.timer >= move.active:
            _enter(boss, RECOVER)
        return out

    if boss.state == RECOVER:
        if boss.timer >= move.recover:
            boss.cooldown = _wait(boss)
            _enter(boss, IDLE)
        return out

    return out


def _enter(boss: Boss, state: str) -> None:
    boss.state = state
    boss.timer = 0.0
    # The playhead restarts only when the CLIP does. Crossing from windup into
    # strike into recover is the same animation continuing, so those three
    # deliberately do not reset it.
    if state not in (STRIKE, RECOVER):
        boss.clip_t = 0.0
    if state in (IDLE, WALK):
        boss.move = None


def _target(boss: Boss, living: list):
    for player in living:
        if player.id == boss.target_id:
            return player
    return _nearest(boss, living)


def _nearest(boss: Boss, living: list):
    best = None
    best_d = 0.0
    for player in living:
        d = math.hypot(player.x - boss.x, player.y - boss.y)
        if best is None or d < best_d:
            best, best_d = player, d
    return best


def _step_free(boss: Boss, target, world: TileMap, dt: float, out: Outcome) -> None:
    """Walking, and deciding. The only state he can be interrupted out of."""
    if target is None:
        _enter(boss, IDLE) if boss.state != IDLE else None
        return
    dx = target.x - boss.x
    dy = target.y - boss.y
    dist = math.hypot(dx, dy)
    tiles = dist / TILE_SIZE
    _turn(boss, target, dt, BOSS_TURN_DEGREES)

    if boss.cooldown <= 0.0:
        move = _choose(boss, tiles)
        if move is not None:
            boss.target_id = target.id
            boss.move = move
            _enter(boss, WINDUP)
            out.events.append({
                "kind": "windup", "move": move.key,
                "x": round(boss.x, 1), "y": round(boss.y, 1),
            })
            return

    # WALK. He never strafes and never backs off: he is a wall that is coming,
    # and the only reason to make him move at all is so that standing still is
    # not a strategy.
    if tiles > BOSS_CHOP_REACH_TILES * 0.72:
        speed = TILE_SIZE * BOSS_SPEED_TILES * (BOSS_ENRAGE_SPEED if boss.enraged else 1.0)
        step = speed * dt
        ux, uy = (dx / dist, dy / dist) if dist > 0.001 else (boss.aim_x, boss.aim_y)
        _slide(boss, ux * step, uy * step, world)
        if boss.state != WALK:
            _enter(boss, WALK)
    elif boss.state != IDLE:
        _enter(boss, IDLE)


def _choose(boss: Boss, tiles: float) -> Move | None:
    """Which move, given the range. A RANGE DECISION FIRST, a roll second.

    The band test is the whole design: every move is an answer to a specific
    mistake, so rolling one whose band the player is not standing in would
    punish them for something they are not doing. What the roll is for is
    stopping the fight from being a lookup table — inside a band there are
    usually two legal answers and he does not always pick the same one.
    """
    if boss.enraged and boss._last != REV.key and tiles > 6.0 and boss._rng.random() < 0.14:
        return _pick(boss, RIP)
    options = [m for m in (CHOP, SWEEP, RIP) if m.min_tiles <= tiles <= m.max_tiles]
    if not options:
        return None
    # Never the same move twice running while a second one is legal. Two chops
    # in a row is the pattern that makes a boss feel like a script.
    fresh = [m for m in options if m.key != boss._last]
    return _pick(boss, boss._rng.choice(fresh or options))


def _pick(boss: Boss, move: Move) -> Move:
    boss._last = move.key
    return move


def _wait(boss: Boss) -> float:
    base = BOSS_ATTACK_COOLDOWN * (BOSS_ENRAGE_RATE if boss.enraged else 1.0)
    return base * (0.8 + 0.4 * boss._rng.random())


def _land(boss: Boss, move: Move, living: list, out: Outcome) -> None:
    """The blow. Everything that can hurt a player goes through here."""
    if move.key == REV.key:
        out.events.append({"kind": "roar", "x": round(boss.x, 1), "y": round(boss.y, 1)})
        return

    if move.key == RIP.key:
        boss._crest_id += 1
        speed = TILE_SIZE * BOSS_CREST_SPEED_TILES
        boss.crescents.append(Crescent(
            id=boss._crest_id,
            x=boss.x + boss.aim_x * TILE_SIZE * 1.6,
            y=boss.y + boss.aim_y * TILE_SIZE * 1.6,
            dx=boss.aim_x * speed,
            dy=boss.aim_y * speed,
            life=BOSS_CREST_LIFE,
        ))
        out.events.append({
            "kind": "rip", "x": round(boss.x, 1), "y": round(boss.y, 1),
            "dx": round(boss.aim_x, 3), "dy": round(boss.aim_y, 3),
        })
        return

    landed = 0
    for player in living:
        if not _in_arc(boss, player, move):
            continue
        if boss._immune.get(player.id, 0.0) > 0.0:
            continue
        boss._immune[player.id] = BOSS_MELEE_IMMUNITY
        out.hits.append((player, move.damage, boss.x, boss.y))
        landed += 1

    out.events.append({
        "kind": "impact",
        "move": move.key,
        "x": round(boss.x + boss.aim_x * move.reach * 0.6, 1),
        "y": round(boss.y + boss.aim_y * move.reach * 0.6, 1),
        "dx": round(boss.aim_x, 3),
        "dy": round(boss.aim_y, 3),
        "hits": landed,
    })


def _in_arc(boss: Boss, player, move: Move) -> bool:
    dx = player.x - boss.x
    dy = player.y - boss.y
    dist = math.hypot(dx, dy)
    if dist > move.reach + player.radius:
        return False
    if move.arc_degrees >= 179.0:
        return True
    if dist < 0.001:
        return True
    cos = (dx * boss.aim_x + dy * boss.aim_y) / dist
    return cos >= math.cos(math.radians(move.arc_degrees) / 2.0)


def _turn(boss: Boss, target, dt: float, degrees_per_sec: float) -> None:
    dx = target.x - boss.x
    dy = target.y - boss.y
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return
    want = math.atan2(dy, dx)
    have = math.atan2(boss.aim_y, boss.aim_x)
    delta = (want - have + math.pi) % math.tau - math.pi
    limit = math.radians(degrees_per_sec) * dt
    if delta > limit:
        delta = limit
    elif delta < -limit:
        delta = -limit
    have += delta
    boss.aim_x = math.cos(have)
    boss.aim_y = math.sin(have)


def _slide(boss: Boss, dx: float, dy: float, world: TileMap) -> None:
    """Move, one axis at a time, against the tile grid.

    He is a wide body and the arena is round, so he WILL be pressed into the
    treeline by his own steering. Per-axis is what lets him slide along it
    instead of stopping dead a tile short of a player standing by the rim.
    """
    half = TILE_SIZE * 0.9
    if dx:
        boss.x = world.move_axis(boss.x, boss.y, half, half, dx, 0)
    if dy:
        boss.y = world.move_axis(boss.x, boss.y, half, half, dy, 1)


def _step_crescents(boss: Boss, living: list, world: TileMap, dt: float,
                    out: Outcome) -> None:
    keep: list[Crescent] = []
    radius = TILE_SIZE * BOSS_CREST_RADIUS_TILES
    for crest in boss.crescents:
        crest.life -= dt
        crest.x += crest.dx * dt
        crest.y += crest.dy * dt
        if crest.life <= 0.0 or world.box_blocked(crest.x, crest.y, 2.0, 2.0):
            out.events.append({
                "kind": "crestBurst", "x": round(crest.x, 1), "y": round(crest.y, 1),
            })
            continue
        for player in living:
            if player.id in crest.struck:
                continue
            if math.hypot(player.x - crest.x, player.y - crest.y) > radius + player.radius:
                continue
            crest.struck.add(player.id)
            out.hits.append((player, BOSS_CREST_DAMAGE, crest.x, crest.y))
        keep.append(crest)
    boss.crescents = keep


def wake(boss: Boss) -> None:
    """Start the cinematic. Called once, by `Room`, when the ring is entered."""
    if boss.state != SLEEP:
        return
    _enter(boss, ARRIVE)


def hurt(boss: Boss, amount: int) -> bool:
    """Take damage. Returns True on the tick he starts dying.

    The ENRAGE lives here rather than in `update` because it is a property of
    the health bar crossing a line, and the health bar only ever moves here.
    """
    if not boss.vulnerable:
        return False
    boss.hp = max(0, boss.hp - amount)
    if boss.hp <= 0:
        _enter(boss, DEAD)
        boss.crescents.clear()
        return True
    if not boss.enraged and boss.hp <= boss.max_hp * BOSS_ENRAGE_AT:
        boss.enraged = True
        boss.just_enraged = True
        # He answers the enrage immediately, with the one move that is not an
        # attack: the roar IS the phase change and the player gets to watch it.
        boss.move = REV
        boss.cooldown = 0.0
        _enter(boss, WINDUP)
    return False


def hp_for(players: int) -> int:
    """His health, scaled to how many guns are pointed at him.

    Flat health means a boss that is a wall solo and a speed bump for four,
    and the fight is authored around its LENGTH — long enough to learn the
    telegraphs, short enough that learning them pays off. The first player is
    worth more than the rest because a party also brings more ways to be
    revived and more bodies for him to have to choose between.
    """
    return BOSS_HP_BASE + BOSS_HP_PER_EXTRA * max(0, players - 1)
