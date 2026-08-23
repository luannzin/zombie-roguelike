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

FIVE MOVES, FIVE SHAPES, ONE RANGE BAND EACH.
    CHOP    close, a point, the heaviest. Lands where he is looking.
    SWEEP   close, a circle, hits everything. The answer to crowding him.
    RIP     far, a crescent that leaves the bar and keeps going. The answer to
            standing still at range.
    CHARGE  far, a body. The answer to a GUN — see below.
    REV     nothing. It is the enrage and the free window in one.
Two attacks that punish the same mistake are one attack, so the picker
(`_choose`) is a RANGE decision first and a dice roll second.

THE CHARGE IS THE ANSWER TO A RIFLE, and it is the move this fight was missing.
Everything else on the list is authored around a player who came close; the
crescent is the only thing that reaches, and it is DELIBERATELY slow enough to
walk out of, so a player who never stops moving and never closes could not be
touched. Kiting a body that walks slower than you run has no counter in a move
list made entirely of swings. The counter has to be a move that closes the
distance instead of reaching across it, and the fairness has to be the same
fairness the chop already has: HE COMMITS. The heading locks on the roar and
he cannot steer after it, so the charge is beaten by moving sideways — the
lesson the chop teaches, asked again at a range where the player thought the
answer was "stand here".

THE PICKER IS WEIGHTED, NOT ALTERNATING. It used to ban the last move outright
and roll uniformly over whatever else the range allowed, which at close
quarters is chop / sweep / chop / sweep forever and past four tiles was the
crescent alone. Bands now OVERLAP and taper (`BOSS_BAND_EDGE`), a repeat is
merely expensive (`BOSS_REPEAT_PENALTY`) rather than forbidden, and only three
of the same in a row is actually banned. A boss that never repeats is exactly
as readable as one that always does.

ENRAGED, THE MOVES CHANGE SHAPE — THEY ARE NOT JUST FASTER. Speed alone is the
same fight on a shorter clock, and the player already learned it. Each of the
three swings gets a variant that costs no art, because it changes what leaves
the weapon rather than how the weapon is posed:
    RIP     throws `BOSS_FAN_CRESCENTS` on a spread instead of one. A sidestep
            was the answer; now the sidestep has to have a DIRECTION.
    SWEEP   walks while it spins (`BOSS_SWEEP_DRIFT`). Backing off one tile
            was the answer; now backing off is a retreat.
    CHOP    comes straight back with no cooldown, half the time. The longest
            punish window in the fight becomes one you have to CHECK.
Same clips, same telegraphs, same lengths. The player's knowledge is not
invalidated — it is made insufficient, which is what a phase change is for.

HE IS FAIR BECAUSE HE IS SLOW AND COMMITTED. He walks slower than a player
runs, every move roots him for its whole length (the roving sweep drifts, it
does not chase), and the recovery on the chop is the longest window in the
fight. Everything that makes him dangerous is positional.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    BOSS_ATTACK_COOLDOWN,
    BOSS_BAND_EDGE,
    BOSS_CHARGE_DAMAGE,
    BOSS_CHARGE_MAX_TILES,
    BOSS_CHARGE_MIN_TILES,
    BOSS_CHARGE_RECOVER,
    BOSS_CHARGE_SPEED_TILES,
    BOSS_CHARGE_TIME,
    BOSS_CHARGE_WIDTH_TILES,
    BOSS_CHOP_DAMAGE,
    BOSS_CHOP_REACH_TILES,
    BOSS_CREST_DAMAGE,
    BOSS_CREST_LIFE,
    BOSS_CREST_RADIUS_TILES,
    BOSS_CREST_SPEED_TILES,
    BOSS_DOUBLE_CHOP_CHANCE,
    BOSS_ENRAGE_AT,
    BOSS_ENRAGE_RATE,
    BOSS_ENRAGE_SPEED,
    BOSS_FAN_CRESCENTS,
    BOSS_FAN_SPREAD_DEGREES,
    BOSS_HIT_TILES_R,
    BOSS_HP_BASE,
    BOSS_HP_PER_EXTRA,
    BOSS_MELEE_IMMUNITY,
    BOSS_REPEAT_PENALTY,
    BOSS_RIP_RANGE_TILES,
    BOSS_SLAM_RECOVER,
    BOSS_SPEED_TILES,
    BOSS_SPRITE_TILES_H,
    BOSS_STOMP_DAMAGE,
    BOSS_STOMP_REACH_TILES,
    BOSS_SWEEP_DAMAGE,
    BOSS_SWEEP_DRIFT,
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
CHARGE = "charge"      # the run. The ONE state in which the hitbox is moving.
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
    #: The sheet the WINDUP (and, for a swing, the strike) plays.
    #:
    #: Separate from `key` because of the charge, which is the one move whose
    #: animation is not a swing: it telegraphs on `rev` (he pulls the cord and
    #: roars), runs on `walk`, and comes down on `idle`. Every other move is
    #: one clip and sets all three to its own name, which is why this used to
    #: be `key` doing double duty. `row.m` still carries the MOVE's name, so
    #: the client resolves the sheet through `welcome.config.bossMoves` rather
    #: than assuming the two are the same string.
    clip: str
    #: The sheet the RECOVERY plays. Equal to `clip` for a swing — a swing is
    #: one animation and splitting it would restart the sprite mid-blow.
    after: str
    #: How often the picker reaches for it, before the range weighting. Not a
    #: probability: `_choose` normalises whatever is legal.
    weight: float
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

    @property
    def one_clip(self) -> bool:
        """True when the whole move is one animation — every swing.

        `_enter` keeps the playhead running across windup / strike / recover
        for these, because the art does not split a swing. The charge is the
        exception and it resets on every phase, because each phase of it is a
        different sheet.
        """
        return self.clip == self.after

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
            # WHICH SHEET, because `row.m` is a move and a move is no longer
            # guaranteed to be a clip. The charge telegraphs on `rev` and
            # recovers on `idle`; letting the client assume `m` names a sheet
            # would draw the run as a boss standing still shaking a chainsaw.
            "clip": self.clip,
            "after": self.after,
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
          min_tiles: float, max_tiles: float, active: float = 0.14,
          key: str | None = None, after: str | None = None,
          weight: float = 1.0, recover: float | None = None) -> Move:
    """One move, timed off `clip`'s own event frame. Nothing here is typed."""
    length, events = _clip(clip)
    windup = events.get(event, length * 0.5)
    return Move(
        key=key or clip,
        clip=clip,
        after=after or clip,
        weight=weight,
        windup=windup,
        active=active,
        recover=recover if recover is not None else max(0.12, length - windup - active),
        damage=damage,
        reach_tiles=reach,
        arc_degrees=arc,
        min_tiles=min_tiles,
        max_tiles=max_tiles,
    )


#: THE FIVE. Each one's band is what it is an answer to, and THE BANDS OVERLAP
#: — that is the change that made him stop reading as a script.
#:
#: They used to abut: chop to 4.4, rip from 4.0, and nothing else past that.
#: So under four tiles the only legal pair was chop and sweep, which with a
#: no-repeat rule is a metronome, and over 4.4 the crescent was the sole legal
#: move for the rest of the arena. Overlapping them means four tiles is a place
#: where three different things can happen, and `_choose` tapers each move's
#: weight toward the edges of its own band so the overlap is a blend rather
#: than a cliff.
#:
#: `sweep`'s arc is 180: it is the only move that cannot be dodged by standing
#: behind him, and that is deliberately the answer to a party surrounding a
#: rooted boss. `chop`'s is narrow and long — step out of the line and it
#: misses, which is the move the fight is meant to teach first.
CHOP = _move("chop", "hit", damage=BOSS_CHOP_DAMAGE, reach=BOSS_CHOP_REACH_TILES,
             arc=55.0, min_tiles=0.0, max_tiles=4.6, weight=1.0)
SWEEP = _move("sweep", "spin", damage=BOSS_SWEEP_DAMAGE, reach=BOSS_SWEEP_REACH_TILES,
              arc=180.0, min_tiles=0.0, max_tiles=3.8, active=1.5, weight=0.85)
RIP = _move("rip", "release", damage=BOSS_CREST_DAMAGE, reach=0.0, arc=0.0,
            min_tiles=3.2, max_tiles=BOSS_RIP_RANGE_TILES, weight=1.0)
#: THE CHARGE. Three sheets, because it is the one move that is not a swing:
#: `rev` is the cord and the roar (the telegraph), `walk` is the run, `idle`
#: is him pulling up. Its damage is dealt in `_step_charge`, not `_land`, and
#: its `recover` is decided at the end of the run — a clean pull-up and a bar
#: buried in the treeline are not the same window.
#: NAMED `RUSH`, NOT `CHARGE`, because `CHARGE` is already the STATE above and
#: one of them silently shadowed the other — the boss's `state` field ended up
#: holding a `Move` object, which is invisible until it reaches the wire.
RUSH = _move("rev", "roar", key="charge", after="idle",
             damage=BOSS_CHARGE_DAMAGE, reach=0.0, arc=0.0,
             min_tiles=BOSS_CHARGE_MIN_TILES, max_tiles=BOSS_CHARGE_MAX_TILES,
             weight=0.95, recover=BOSS_CHARGE_RECOVER)
REV = _move("rev", "roar", damage=0, reach=0.0, arc=0.0,
            min_tiles=0.0, max_tiles=99.0)

MOVES: dict[str, Move] = {m.key: m for m in (CHOP, SWEEP, RIP, RUSH, REV)}

#: What the picker will actually roll. `rev` is not in it: the roar is the
#: enrage answering itself (see `hurt`), never something he decides to do.
ATTACKS: tuple[Move, ...] = (CHOP, SWEEP, RIP, RUSH)

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
    #: Seconds the current RECOVER lasts. Set on the way in rather than read
    #: off the move, because one move has two of them: a charge that pulled up
    #: on its own feet and a charge that went into the treeline are the same
    #: animation and very different windows.
    recover_for: float = 0.0
    #: THE RUN. The heading is locked when the roar lands and nothing changes
    #: it — the commitment IS the counterplay — and `hit` names everybody it
    #: has already shouldered so a 1.05-second run bills each body once.
    charge_dx: float = 0.0
    charge_dy: float = 0.0
    charge_hit: set[str] = field(default_factory=set)
    #: A move owed with no cooldown in front of it: the enraged double chop.
    #: Cleared the moment it is spent, so it can never queue on itself.
    encore: Move | None = None
    #: Rolled per move so the same two do not alternate forever.
    _rng: random.Random = field(default_factory=random.Random)
    #: What he did last, and how many times running INCLUDING that last one.
    #: The picker makes a repeat EXPENSIVE rather than illegal (see `_choose`)
    #: and bans only a third, and even that ban yields when the range leaves
    #: him nothing else to do.
    _last: str = ""
    _repeats: int = 0

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
            if move.key == RUSH.key:
                _launch(boss, target, out)
            else:
                _enter(boss, STRIKE)
                _land(boss, move, living, out)
        return out

    if boss.state == CHARGE:
        _step_charge(boss, living, world, dt, out)
        return out

    if boss.state == STRIKE:
        # The sweep is the one move whose hitbox is open for more than a frame,
        # so it keeps testing — that is what makes standing next to a spinning
        # chainsaw for a second and a half cost you.
        if move.key == SWEEP.key:
            _land(boss, move, living, out)
            # AND ENRAGED IT WALKS. Rooted, the answer to the spin is to back
            # off one tile and wait it out; drifting, backing off has to be a
            # retreat. A fraction of his walk, never his full speed — the one
            # move with no blind side must not also be unloseable.
            if boss.enraged and target is not None:
                _drift(boss, target, world, dt)
        if boss.timer >= move.active:
            _recover(boss, move.recover)
        return out

    if boss.state == RECOVER:
        if boss.timer >= boss.recover_for:
            # AN ENCORE SKIPS THE WAIT. That is the whole of the enraged
            # double chop: the same clip, the same telegraph, arriving in the
            # window the player had learned was free.
            encore, boss.encore = boss.encore, None
            if encore is not None:
                boss.move = encore
                _enter(boss, WINDUP)
                out.events.append({
                    "kind": "windup", "move": encore.key, "encore": True,
                    "x": round(boss.x, 1), "y": round(boss.y, 1),
                })
                return out
            boss.cooldown = _wait(boss)
            _enter(boss, IDLE)
        return out

    return out


def _recover(boss: Boss, seconds: float) -> None:
    """Into the punish window, with the length of THIS one written down."""
    boss.recover_for = max(0.12, seconds)
    _enter(boss, RECOVER)


def _launch(boss: Boss, target, out: Outcome) -> None:
    """The roar landed. Lock the heading and go.

    LOCKED, and that is the entire counterplay. He tracks through the windup
    like every other move — the telegraph has to read as "he is coming for
    YOU" — and then stops tracking completely, so the charge is beaten by
    being somewhere else when it arrives rather than by out-running it. He
    runs faster than a player does; if he steered there would be no answer.

    AND HE AIMS WHERE YOU ARE GOING, not where you are. That is not a
    concession, it is the whole move: aimed at the player's CURRENT tile, a
    charge that takes a second to cross eight tiles cannot touch anybody
    moving at all, in any direction, ever — the first version was tested
    against a player orbiting him at walking pace and landed nought out of
    sixteen. A move that punishes nothing is not a counter to kiting; it is a
    cutscene the player walks around. Leading turns it into the question it is
    supposed to ask: he has committed to where you were HEADED, so the answer
    is to stop doing what you were doing. Autopilot loses, reacting wins, and
    the commitment is still total — he cannot correct once he is running.
    """
    ux, uy = _lead(boss, target)
    boss.charge_dx = ux
    boss.charge_dy = uy
    # The sprite runs the way the body runs.
    boss.aim_x, boss.aim_y = ux, uy
    boss.charge_hit.clear()
    _enter(boss, CHARGE)
    out.events.append({
        "kind": "charge",
        "x": round(boss.x, 1), "y": round(boss.y, 1),
        "dx": round(boss.charge_dx, 3), "dy": round(boss.charge_dy, 3),
    })


def _lead(boss: Boss, target) -> tuple[float, float]:
    """Unit heading at where the target will be, if they keep doing this.

    Three passes of the standard fixed-point intercept: guess the flight time
    from the present distance, move the target along its own velocity by that
    much, re-measure. It converges immediately at these speeds and needs no
    quadratic — and the quadratic's failure case (a target faster than the
    chaser, which has no solution) would need this fallback anyway.
    """
    if target is None:
        return boss.aim_x, boss.aim_y
    speed = TILE_SIZE * BOSS_CHARGE_SPEED_TILES * (BOSS_ENRAGE_SPEED if boss.enraged else 1.0)
    px, py = target.x, target.y
    flight = math.hypot(px - boss.x, py - boss.y) / max(1.0, speed)
    for _ in range(3):
        # Never past the end of the run: aiming at a point he will not reach
        # bends the whole charge away from the only part of it that can hit.
        flight = min(flight, BOSS_CHARGE_TIME)
        px = target.x + getattr(target, "vx", 0.0) * flight
        py = target.y + getattr(target, "vy", 0.0) * flight
        flight = math.hypot(px - boss.x, py - boss.y) / max(1.0, speed)
    dx = px - boss.x
    dy = py - boss.y
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return boss.aim_x, boss.aim_y
    return dx / dist, dy / dist


def _step_charge(boss: Boss, living: list, world: TileMap, dt: float,
                 out: Outcome) -> None:
    """One tick of the run: move, shoulder whoever is in the way, or stop.

    THE HITBOX IS THE BODY, which is why this does not go through `_land`.
    Every other move tests an arc in front of a rooted boss at one instant;
    this one is a moving circle that bills each body once, the way the thrown
    crescent does. Same door out — `out.hits` — so `Room.damage_player` is
    still the only place a player loses health.
    """
    speed = TILE_SIZE * BOSS_CHARGE_SPEED_TILES * (BOSS_ENRAGE_SPEED if boss.enraged else 1.0)
    before_x, before_y = boss.x, boss.y
    _slide(boss, boss.charge_dx * speed * dt, boss.charge_dy * speed * dt, world)
    moved = math.hypot(boss.x - before_x, boss.y - before_y)

    width = TILE_SIZE * BOSS_CHARGE_WIDTH_TILES
    for player in living:
        if player.id in boss.charge_hit:
            continue
        # HIS OWN I-FRAMES STILL APPLY. A body he chopped a third of a second
        # ago is not also run over by the same boss: `_immune` is the one
        # window every one of his attacks shares, and the charge is an attack
        # like the rest of them.
        if boss._immune.get(player.id, 0.0) > 0.0:
            continue
        if math.hypot(player.x - boss.x, player.y - boss.y) > width + player.radius:
            continue
        boss.charge_hit.add(player.id)
        boss._immune[player.id] = BOSS_MELEE_IMMUNITY
        out.hits.append((player, BOSS_CHARGE_DAMAGE, boss.x, boss.y))
        out.events.append({
            "kind": "impact", "move": RUSH.key,
            "x": round(boss.x, 1), "y": round(boss.y, 1),
            "dx": round(boss.charge_dx, 3), "dy": round(boss.charge_dy, 3),
            "hits": 1,
        })

    # THE TREELINE STOPS HIM, and it is the biggest free window in the fight.
    # A charge dodged into the rim buries the bar in a trunk; one that runs
    # its course ends with him on his feet. Rewarding the better dodge more is
    # the only reason the two recoveries are different numbers.
    if moved < speed * dt * 0.4:
        out.events.append({
            "kind": "slam",
            "x": round(boss.x + boss.charge_dx * TILE_SIZE, 1),
            "y": round(boss.y + boss.charge_dy * TILE_SIZE, 1),
            "dx": round(boss.charge_dx, 3), "dy": round(boss.charge_dy, 3),
        })
        _recover(boss, BOSS_SLAM_RECOVER)
        return
    if boss.timer >= BOSS_CHARGE_TIME:
        _recover(boss, BOSS_CHARGE_RECOVER)


def _drift(boss: Boss, target, world: TileMap, dt: float) -> None:
    """The enraged sweep's walk. Toward the target, at a fraction of a walk."""
    dx = target.x - boss.x
    dy = target.y - boss.y
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return
    step = TILE_SIZE * BOSS_SPEED_TILES * BOSS_SWEEP_DRIFT * dt
    _slide(boss, dx / dist * step, dy / dist * step, world)


def _enter(boss: Boss, state: str) -> None:
    boss.state = state
    boss.timer = 0.0
    # The playhead restarts only when the CLIP does. Crossing from windup into
    # strike into recover is the same animation continuing, so for a SWING
    # those three deliberately do not reset it — see `client/tests/boss-clock.ts`
    # for what happens when they do.
    #
    # The charge is the exception and it is an exception about the ART, not
    # about the timing: its three phases are three different sheets (`rev`,
    # `walk`, `idle`), so each of them starts its own clip at zero. `Move.one_clip`
    # is what tells the two apart, and the client resolves the same split off
    # `bossMoves[key].clip` / `.after`.
    swing = boss.move is not None and boss.move.one_clip
    if state not in (STRIKE, RECOVER) or not swing:
        boss.clip_t = 0.0
    if state in (IDLE, WALK):
        boss.move = None
        boss.encore = None


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

    The band test is still the whole design: every move is an answer to a
    specific mistake, so rolling one whose band the player is not standing in
    would punish them for something they are not doing. What changed is
    everything about how the roll inside the bands works, and it changed
    because the old one produced a metronome.

    IT WAS A LOOKUP TABLE WITH A COIN FLIP ON TOP. Bands abutted rather than
    overlapped — chop to 4.4, rip from 4.0 and alone all the way out — and the
    rule was "never the last move again", uniformly, over whatever was legal.
    Under four tiles that is chop, sweep, chop, sweep, forever; over four and a
    half it is the crescent on a timer. A player learns both in about fifteen
    seconds and the rest of the fight is executing a known loop.

    THREE CHANGES, AND EACH ONE REMOVES A DIFFERENT KIND OF PREDICTABILITY:

      OVERLAPPING BANDS mean a range is rarely a single answer. Four tiles is
      now chop, throw and charge; the player cannot read the next move off
      their own distance.

      A TAPER (`BOSS_BAND_EDGE`) inside each band means the overlap is a blend
      rather than a cliff. A move is likeliest in the middle of what it is FOR
      and merely possible at the fringe, so the fight still teaches a shape —
      close is heavy, far is thrown — without being a rule.

      A REPEAT IS EXPENSIVE, NOT ILLEGAL (`BOSS_REPEAT_PENALTY`). Two chops in
      a row is a thing that happens to you now; three never is. A boss that is
      forbidden to repeat is exactly as readable as one that always does, and
      the strict alternation was the single biggest reason he read as a script.
    """
    weights = _legal(boss, tiles, repeats_banned=True)
    if not weights:
        # THE BAN YIELDS WHEN IT IS THE ONLY ANSWER. Out past the throw's
        # range the charge is the sole legal move, and a no-repeat rule with
        # nothing to switch to does not vary the fight — it removes it, and he
        # spends the far half of the yard walking. Refusing to repeat is worth
        # having only while there is something else to do instead.
        weights = _legal(boss, tiles, repeats_banned=False)
    if not weights:
        return None
    total = sum(weight for _, weight in weights)
    roll = boss._rng.random() * total
    for move, weight in weights:
        roll -= weight
        if roll <= 0.0:
            return _pick(boss, move)
    return _pick(boss, weights[-1][0])


def _legal(boss: Boss, tiles: float, *, repeats_banned: bool) -> list[tuple[Move, float]]:
    rows: list[tuple[Move, float]] = []
    for move in ATTACKS:
        weight = _weigh(boss, move, tiles, repeats_banned=repeats_banned)
        if weight > 0.0:
            rows.append((move, weight))
    return rows


def _weigh(boss: Boss, move: Move, tiles: float, *, repeats_banned: bool) -> float:
    """How likely this move is at this range, right now. Zero means illegal."""
    if not (move.min_tiles <= tiles <= move.max_tiles):
        return 0.0
    if repeats_banned and move.key == boss._last and boss._repeats >= 2:
        # The one hard ban left. A THIRD of anything in a row is a pattern —
        # `_repeats` counts consecutive picks including the one that set it.
        return 0.0
    span = max(0.001, move.max_tiles - move.min_tiles)
    where = (tiles - move.min_tiles) / span
    # A smooth hump: full weight in the middle of the band, `BOSS_BAND_EDGE`
    # of it at either lip. Never zero at the lip, or the bands would abut
    # again with extra arithmetic in front of them.
    fit = BOSS_BAND_EDGE + (1.0 - BOSS_BAND_EDGE) * math.sin(where * math.pi)
    weight = move.weight * fit
    if move.key == boss._last:
        weight *= BOSS_REPEAT_PENALTY
    # ENRAGED, HE REACHES FOR THE RUN. It is the move that answers a gun, and
    # a party that has taken him to half health from across the yard is
    # exactly the party it exists for.
    if boss.enraged and move.key == RUSH.key:
        weight *= 1.5
    return weight


def _pick(boss: Boss, move: Move) -> Move:
    boss._repeats = boss._repeats + 1 if move.key == boss._last else 1
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
        # ONE CRESCENT, OR A FAN OF THREE ONCE HE IS ENRAGED.
        #
        # The variant is the whole of what the enrage does to this move: same
        # clip, same windup, same tell, a different thing leaving the bar. One
        # crescent is dodged by taking a step sideways, which is right for the
        # first half of the fight — it is the move that teaches "keep moving".
        # It is also why a player who learned that lesson could not lose the
        # second half. A fan makes the sidestep a DIRECTION: there is still
        # somewhere to be, and now you have to pick it.
        count = BOSS_FAN_CRESCENTS if boss.enraged else 1
        speed = TILE_SIZE * BOSS_CREST_SPEED_TILES
        spread = math.radians(BOSS_FAN_SPREAD_DEGREES)
        centre = (count - 1) / 2.0
        for index in range(count):
            angle = (index - centre) * spread
            cos = math.cos(angle)
            sin = math.sin(angle)
            ux = boss.aim_x * cos - boss.aim_y * sin
            uy = boss.aim_y * cos + boss.aim_x * sin
            boss._crest_id += 1
            boss.crescents.append(Crescent(
                id=boss._crest_id,
                x=boss.x + ux * TILE_SIZE * 1.6,
                y=boss.y + uy * TILE_SIZE * 1.6,
                dx=ux * speed,
                dy=uy * speed,
                life=BOSS_CREST_LIFE,
            ))
        out.events.append({
            "kind": "rip", "x": round(boss.x, 1), "y": round(boss.y, 1),
            "dx": round(boss.aim_x, 3), "dy": round(boss.aim_y, 3),
            "hits": count,
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

    # THE DOUBLE CHOP. Enraged, the chop sometimes comes straight back out of
    # its own recovery with no wait in front of it.
    #
    # This is the variant that changes the most while adding the least: no new
    # clip, no new hitbox, no new number. What it takes away is a CERTAINTY.
    # The chop's recovery is the longest window in the fight and every safe
    # thing a player does — reload, heal, walk in and swing — is scheduled off
    # it. Half the time it is now a window you have to look at first, which is
    # a different fight fought with the same knowledge.
    if (move.key == CHOP.key and boss.enraged and boss.encore is None
            and boss._rng.random() < BOSS_DOUBLE_CHOP_CHANCE):
        boss.encore = CHOP


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
        # It interrupts whatever he was doing, including a run — the encore
        # goes with it, or the roar would chain into a chop nobody was told
        # about.
        boss.encore = None
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
