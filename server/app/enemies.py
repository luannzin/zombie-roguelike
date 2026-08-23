"""Enemies: the stat block (`EnemyType`) and the live instance (`Enemy`).

An **EnemyType** is the designer-facing answer to "what is a zombie": how much
health it has, how hard it hits, how fast it shambles, how far it can see, and
what it pays out when it dies (xp, gold). It is frozen data — one entry in
`ENEMY_TYPES` plus a processed sprite sheet of the same name is a whole new
creature. Nothing in the room, the renderer or the protocol is per-creature.

An **Enemy** is one live instance of a type: position, hp, cooldowns, stagger
from stacked gun hits, current target. It deliberately exposes the same
`(id, x, capsule_y0, capsule_y1, radius, alive)` shape as `Player`, so
`combat.raycast` shoots it with no changes and players and enemies can share
one target list. Stagger never rides the snapshot — `ai.move` writes the
slowed vx/vy instead.

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
    Visual variants and accessories are lists on that type; spawn rolls them
    and the snapshot carries the indices. Same stats, different sheets.

    Its VOICE is `voice`, a prefix into the audio library; its RANK is `rank`,
    which is all the HUD is told. A MINIBOSS adds `sleep_sprite` (which is
    also what makes it spawn asleep), `wake_tiles` and `persists`, plus a
    scene of its own — and stays OFF `SPAWN_TABLE`, because a placed encounter
    the director could also roll is a random event rather than a place.
    See docs/design/enemies.md.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import (
    ALPHA_AGGRO_TILES,
    ALPHA_ATTACK_COOLDOWN,
    ALPHA_CALL_TILES,
    ALPHA_DAMAGE,
    ALPHA_SPEED_TILES,
    ALPHA_WAKE_TILES,
    MINIBOSS_HP,
    WOLF_AGGRO_TILES,
    WOLF_ATTACK_COOLDOWN,
    WOLF_CALL_TILES,
    WOLF_DAMAGE,
    WOLF_HP,
    WOLF_PACK_MIN,
    WOLF_SPAWN_WEIGHT,
    WOLF_SPEED_TILES,
    ENEMY_STAGGER_DECAY,
    ENEMY_STAGGER_HOLD,
    ENEMY_STAGGER_HOLD_MAX,
    ENEMY_STAGGER_HOLD_SCALE,
    ENEMY_STAGGER_MAX_ADD,
    ENEMY_STAGGER_MIN,
    ENEMY_STAGGER_PER_DAMAGE,
    ENEMY_VIEW_DARK_TILES,
    ENEMY_VIEW_LIT_TILES,
    PLAYER_BOX_TILES_H,
    PLAYER_BOX_TILES_W,
    PLAYER_HIT_TILES_R,
    SPRITE_TILES_H,
    TILE_SIZE,
)


#: WHAT KIND OF THING A CREATURE IS, as far as the HUD is concerned. Two
#: values and no more until there is a third kind of encounter: `""` is
#: everything the director spawns, and a miniboss is a placed, sleeping,
#: crowned one. See `EnemyType.rank`.
RANK_COMMON = ""
RANK_MINIBOSS = "miniboss"

#: Social groups — who answers whose call. See `EnemyType.pack`. The dead have
#: none: a zombie's shout is a nudge to whatever is standing next to it,
#: which is a fact about proximity rather than about kinship.
PACK_WOLVES = "wolves"


@dataclass(frozen=True)
class EnemyType:
    """One creature's stat block. Everything spatial is in tiles."""

    key: str
    #: Processed asset folder name — assets/processed/<sprite>/sheet.png.
    #: Fallback when `variants` is empty or an index is out of range.
    sprite: str
    max_hp: int
    #: Damage per landed melee hit (before the victim's i-frames are checked).
    damage: int
    #: Paid to whoever lands the killing blow.
    xp: int
    #: The MOST this creature can drop, in coins — not what it does drop. Each
    #: point is rolled on its own when it dies (`coins.roll_drop`), so the
    #: payout is a spread with both ends rare. Nothing is credited: the coins
    #: land on the ground and somebody has to walk over them.
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
    view_degrees: float = 75.0
    #: Body sheets rolled on spawn. Index rides the snapshot as `v`.
    variants: tuple[str, ...] = ()
    #: Hat overlay sheets. Spawn may pick one, or none. Snapshot `hat`.
    hats: tuple[str, ...] = ()
    #: Clothes overlay sheets. Spawn may pick one, or none. Snapshot `cloth`.
    clothes: tuple[str, ...] = ()

    # --- WHAT KIND OF THING THIS IS -----------------------------------------
    #: `RANK_COMMON` or `RANK_MINIBOSS`, and it is DATA rather than a name the
    #: client special-cases. A miniboss wears a crown over its head and its
    #: health bar is drawn even when it is untouched; both of those read this
    #: field, so the SECOND miniboss costs no client change — which is the
    #: same promise `EnemyType` already makes about ordinary creatures.
    #:
    #: A rank is not a stat block. Nothing in `ai.py` branches on it: what
    #: makes a miniboss a miniboss is `sleep_sprite`, `persists`, its numbers
    #: and its own scene. This is only how the HUD is told.
    rank: str = ""
    #: WHAT IT SOUNDS LIKE, as a prefix. The client asks the audio library for
    #: `<voice>-idle`, `<voice>-alert` and `<voice>-death`, so a creature's
    #: whole vocabulary is this one string — the same promise `sprite` makes
    #: about its art. Everything defaults to the dead, because the dead are
    #: what this game is made of and a new creature with no recipes of its own
    #: should sound like one rather than be silent.
    voice: str = "zombie"
    #: The processed folder for the CURLED-UP pose, or "" for a creature that
    #: is never asleep. Its presence is also what makes the creature spawn
    #: asleep — see `ai.MODE_SLEEP`. One field, because a sleeping creature
    #: the client cannot draw asleep is worse than one that never sleeps.
    sleep_sprite: str = ""
    #: How close a player has to come before a sleeper wakes on its own. It is
    #: a HEARING radius, not a sight cone: a sleeping animal has its eyes shut,
    #: so the cone is off and this is the only thing that can find you.
    wake_tiles: float = 0.0
    #: THE HOWL. How far a commit is shared with the rest of this creature's
    #: OWN PACK, in tiles. Zero means the ordinary neighbour shout
    #: (`ENEMY_ALERT_SHARE_DIST`, everything nearby, one hop). A wolf that has
    #: found you calls its pack across most of a clearing and calls nothing
    #: else, because a howl is a wolf talking to wolves.
    pack_call_tiles: float = 0.0
    #: WHO ANSWERS IT. A group name shared by every type in one pack, so the
    #: alpha's howl brings WOLVES rather than other alphas — there is only
    #: ever one of him, and a leader whose call nothing can answer is not a
    #: leader.
    #:
    #: A FIELD OF ITS OWN rather than reusing `key` or `voice`. `key` was the
    #: first cut and it made the miniboss's howl reach exactly nobody; `voice`
    #: is nearly right and is the footgun version — a creature given a wolf's
    #: growl for flavour would silently join the pack. Who answers a call is a
    #: fact about the AI, so it is written down as one.
    pack: str = ""
    #: The director never sends fewer than this many together. A pack of one
    #: is a stray dog.
    group_min: int = 1
    #: Never recycled by the abandonment timer. For anything the MAP placed
    #: rather than the director: a miniboss that despawned because nobody had
    #: walked to its den yet would leave the den empty for the whole night.
    persists: bool = False

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

    @property
    def wake_range(self) -> float:
        return TILE_SIZE * self.wake_tiles

    @property
    def pack_call_range(self) -> float:
        """The howl's reach, or 0 for a creature that only nudges neighbours."""
        return TILE_SIZE * self.pack_call_tiles

    @property
    def sleeps(self) -> bool:
        return bool(self.sleep_sprite)

    def client_payload(self) -> dict:
        """What the client needs: art, hit geometry, and numbers it displays."""
        return {
            "key": self.key,
            "sprite": self.sprite,
            "maxHp": self.max_hp,
            "damage": self.damage,
            "xp": self.xp,
            # The ceiling, not the payout — what actually fell is on the kill
            # event, because it is rolled per corpse.
            "goldMax": self.gold,
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
            "variants": list(self.variants),
            "hats": list(self.hats),
            "clothes": list(self.clothes),
            # What KIND of thing this is, and the sheet to draw it with while
            # it is still asleep. Both are presentation: the crown, the
            # always-on health bar and the curled pose are decided off these
            # two strings, so a second miniboss is a stat block and nothing
            # else. Empty strings mean "an ordinary creature that never
            # sleeps", which is every zombie in the game.
            "rank": self.rank,
            "sleepSprite": self.sleep_sprite,
            # The audio library prefix. See `voice` — three sound keys, one
            # field, and the client never learns a creature's name.
            "voice": self.voice,
            # `pack`, `wake_tiles`, `pack_call_tiles`, `group_min` and
            # `persists` deliberately do NOT ship. They are facts about how
            # the simulation behaves, and the client neither draws nor
            # predicts any of them — a constant on this payload is a constant
            # `test_config_parity.py` then has to keep in step for no reason.
        }


#: Chance a spawned zombie wears a hat / a piece of clothing. Independent.
ZOMBIE_HAT_CHANCE = 0.55
ZOMBIE_CLOTH_CHANCE = 0.45

ZOMBIE = EnemyType(
    key="zombie",
    sprite="zombie",
    variants=("zombie", "zombie-husk", "zombie-brute"),
    hats=("zhat-cap", "zhat-beanie", "zhat-hardhat"),
    clothes=("zcloth-vest", "zcloth-jacket", "zcloth-tie"),
    max_hp=30,          # 4 hits at SHOT_DAMAGE 8
    damage=9,           # ~15 dps against a swarm, given MELEE_IMMUNITY
    xp=12,
    gold=3,
    speed_tiles=2.6,    # vs the player's 4.4 — always outrunnable
    aggro_tiles=24.0,   # once it has you, most of the arena is not far enough
    attack_range_tiles=0.85,
    attack_cooldown=1.1,
    # Reaches left at the defaults: a zombie sees exactly as far as you do, and
    # exactly as far as your lamp lets it. The cone is three-quarters of a
    # right angle — you can spot one before it spots you, but only by looking
    # at it.
    view_degrees=75.0,
)

#: THE SECOND SILHOUETTE, and it was the thing this module owed the game.
#:
#: `ENEMY_TYPES` held exactly one row for the whole of the game's life: the
#: three "variants" are sprites over identical stats, so a run's entire
#: bestiary was learned in the first sixty seconds and nothing new walked out
#: of the dark until the Sawyer. Population scaling buys pressure; it does not
#: buy surprise.
#:
#: A WOLF IS THE OPPOSITE OF A ZOMBIE ON EVERY AXIS THE PLAYER CAN FEEL, which
#: is the point — a second creature that is a zombie with different numbers is
#: a zombie. It is faster than you walk, it bites more than twice as often for
#: half as much, it dies in three pistol rounds instead of four, and it gives
#: up at less than half the distance. So the answer to a zombie (back away and
#: shoot) is the wrong answer to a pack, and the answer to a pack (break the
#: line and keep moving) does not work on a horde that never stops coming.
#:
#: AND IT NEVER ARRIVES ALONE. `group_min` is what makes it a pack rather
#: than a fast zombie, and the howl (`pack_call_tiles`) is what makes the pack
#: a THREAT: one wolf finding you is every wolf in the clearing finding you,
#: at four times the reach a shout carries and only to its own kind.
WOLF = EnemyType(
    key="wolf",
    sprite="wolf",
    # Two heads is the same animal further gone, not a second creature: same
    # stats, one more skull. The alpha below is where the stats change.
    variants=("wolf", "wolf-twin"),
    voice="wolf",
    max_hp=WOLF_HP,
    damage=WOLF_DAMAGE,
    xp=9,
    gold=2,
    speed_tiles=WOLF_SPEED_TILES,
    # THE ESCAPE VALVE, and it is the whole reason a creature this fast is
    # fair. A zombie chases for twenty-four tiles; a wolf loses interest at
    # ten. Outrunning one is not a matter of stamina, it is a matter of
    # committing to leave — which is the decision the pack exists to ask.
    aggro_tiles=WOLF_AGGRO_TILES,
    attack_range_tiles=0.9,
    attack_cooldown=WOLF_ATTACK_COOLDOWN,
    # A wider cone than a zombie's and the same reach. It notices you sooner
    # and forgets you faster, which is the same trade the numbers above make.
    view_degrees=100.0,
    pack_call_tiles=WOLF_CALL_TILES,
    pack=PACK_WOLVES,
    group_min=WOLF_PACK_MIN,
    hit_tiles_r=0.32,
    # A quadruped is LONG AND LOW. The box is what the player collides with
    # and the sprite height is what the hit capsule reaches to; both are read
    # off the sheet `make_wolf.py` writes rather than left at the player's.
    sprite_tiles_h=0.8125,
    box_tiles_w=0.85,
    box_tiles_h=0.4,
)

#: THE ALPHA — the first MINIBOSS, and the class is new.
#:
#: A boss (`boss.py`) is a body with a state machine, a cinematic, an arena
#: and a health bar across the top of the screen; it is a milestone the run is
#: built around and it costs a whole module. A miniboss is none of that. It is
#: an ENEMY — `ai.py` steers it, the same cone notices you, the same flow
#: field routes it — with four differences, all of them data:
#:
#:   it is ASLEEP    until somebody gets close enough. Nothing else in this
#:                   game is switched off when you find it, and that is the
#:                   whole encounter: the player sees it before it sees them
#:                   and gets to decide.
#:   it PERSISTS     the map placed it, so the abandonment timer must not
#:                   recycle it before anybody has walked to its den.
#:   it is RANKED    which is how the HUD knows to crown it and to draw its
#:                   health bar before the first shot lands.
#:   it has a PLACE  `scenery._den`, the way the Sawyer has an arena.
#:
#: HIS HEALTH IS A THIRD OF THE BOSS'S AND IT IS WRITTEN AS THAT FRACTION.
#: Typing a number here would make him a creature somebody balanced once; as a
#: fraction he is a stated portion of the fight the run is already built
#: around, and retuning that fight retunes him in the same motion.
WOLF_ALPHA = EnemyType(
    key="wolf-alpha",
    sprite="wolf-alpha",
    rank=RANK_MINIBOSS,
    voice="wolf",
    sleep_sprite="wolf-alpha-sleep",
    persists=True,
    max_hp=MINIBOSS_HP,
    # THREE HEADS BITE LIKE THREE HEADS. He is not a big wolf with a big
    # number on his swing — he is the wolf's own rhythm, faster, so standing
    # in front of him costs more per second than anything else in the game.
    # That is what makes leaving the correct answer as often as fighting is.
    damage=ALPHA_DAMAGE,
    attack_cooldown=ALPHA_ATTACK_COOLDOWN,
    xp=110,
    gold=34,
    # Faster than a walk and slower than a sprint, so breaking away costs
    # stamina and a decision. Anything faster than a sprint would be the
    # boss's charge, and the charge is a move — this is a chase.
    speed_tiles=ALPHA_SPEED_TILES,
    aggro_tiles=ALPHA_AGGRO_TILES,
    attack_range_tiles=1.4,
    view_degrees=110.0,
    pack_call_tiles=ALPHA_CALL_TILES,
    # THE SAME PACK AS THE ORDINARY WOLVES, which is the whole point of him
    # having a call at all: he brings the animals that are already out there,
    # not more of himself.
    pack=PACK_WOLVES,
    wake_tiles=ALPHA_WAKE_TILES,
    hit_tiles_r=0.55,
    sprite_tiles_h=1.25,
    box_tiles_w=1.35,
    box_tiles_h=0.6,
)

ENEMY_TYPES: dict[str, EnemyType] = {
    kind.key: kind for kind in (ZOMBIE, WOLF, WOLF_ALPHA)
}

#: Weighted spawn table used by the director. Add creatures here.
#:
#: THE ALPHA IS DELIBERATELY NOT ON IT. He is in `ENEMY_TYPES` because the
#: client resolves his stat block out of that catalog, and out of this list
#: because the director must never roll one: he is placed by the map, once, in
#: his own den (`mapgen.DEN_SCENES`). A miniboss that could also wander out of
#: a spawn ring would stop being a place and become a random event.
SPAWN_TABLE: list[tuple[EnemyType, float]] = [(ZOMBIE, 1.0), (WOLF, WOLF_SPAWN_WEIGHT)]


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
    #: 0..1 walk slow from stacked gun hits. At ENEMY_STAGGER_STOP they plant.
    #: Decays after stagger_left; never on the snapshot — vx/vy already slow.
    stagger: float = 0.0
    #: Seconds the meter holds before decaying. Refreshed by each landed shot.
    stagger_left: float = 0.0
    target_id: str | None = None
    #: Seconds spent with no living player anywhere near — see ai.update.
    abandoned: float = 0.0
    #: Seconds spent making no headway; switches steering to the flow field.
    stuck: float = 0.0

    #: What it is doing: one of ai.MODE_*. Never sent — `awareness` is the only
    #: thing the client needs, and a patrolling enemy and one walking home look
    #: exactly alike.
    #:
    #: `ai.MODE_SLEEP` IS THE ONE EXCEPTION, and it is why `sl` rides the
    #: snapshot below: a sleeping creature and a standing one do not look
    #: alike, they are drawn from different sheets. Everything else about the
    #: mode stays private.
    mode: str = "idle"
    #: Seconds left in the beat between a sleeper's eyes opening and its first
    #: step — it stands, it howls, and only then does it come. It is the same
    #: shape as `startle` and deliberately a different field: startle is the
    #: extraction alarm reaching a body that was already awake, and mixing the
    #: two would mean a pad called next to a den skipped the wake entirely.
    waking: float = 0.0
    #: Where it spawned. It patrols around this and comes back to it, so the
    #: map keeps the shape the director gave it instead of draining toward
    #: whoever fired last.
    home_x: float = 0.0
    home_y: float = 0.0
    #: Current patrol waypoint (None = standing still) and how long it stands.
    wander_x: float | None = None
    wander_y: float | None = None
    wander_wait: float = 0.0
    #: Seconds left STANDING STILL after the extraction alarm reached it.
    #:
    #: THE PAUSE IS THE MESSAGE. When a pickup is called the whole map commits
    #: at once, and a hundred bodies that all start walking on the same frame
    #: reads as a switch being thrown rather than as something having heard
    #: something. So a creature the alarm reaches stops, turns toward the
    #: noise, and stands — hunt diamond already lit, because it HAS committed —
    #: for a beat scaled by how far the sound had to travel. Near ones snap
    #: round first and distant ones a moment later, which is the sound moving
    #: outward, and the player watches the reaction spread from the platform
    #: they just pressed. See `ai.startle`.
    startle: float = 0.0
    #: What it turned to look at. Only meaningful while `startle` is running.
    startle_x: float = 0.0
    startle_y: float = 0.0
    #: Seconds since a hunter last had eyes on its target. It keeps walking to
    #: the last known position for the whole window, so breaking line of sight
    #: buys distance, not an instant off-switch.
    lost: float = 0.0
    last_seen_x: float = 0.0
    last_seen_y: float = 0.0

    #: Visual look, rolled once at spawn. `variant` indexes `type.variants`;
    #: `hat` / `cloth` index those pools, or -1 for none. Never change after.
    variant: int = 0
    hat: int = -1
    cloth: int = -1

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

    def take_stagger(self, amount: int) -> None:
        """Stack a gun hit onto the walk-slow meter. Call from damage_enemy."""
        add = max(
            ENEMY_STAGGER_MIN,
            min(ENEMY_STAGGER_MAX_ADD, amount * ENEMY_STAGGER_PER_DAMAGE),
        )
        self.stagger = min(1.0, self.stagger + add)
        hold = ENEMY_STAGGER_HOLD + add * ENEMY_STAGGER_HOLD_SCALE
        self.stagger_left = min(ENEMY_STAGGER_HOLD_MAX, self.stagger_left + hold)

    def tick_stagger(self, dt: float) -> None:
        """Hold, then decay. Call once per tick before steering."""
        if self.stagger_left > 0.0:
            self.stagger_left = max(0.0, self.stagger_left - dt)
            return
        if self.stagger <= 0.0:
            return
        self.stagger = max(0.0, self.stagger - ENEMY_STAGGER_DECAY * dt)

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
        row = {
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
            "v": self.variant,
        }
        # Omit empty slots so a bare zombie stays a short row.
        if self.hat >= 0:
            row["hat"] = self.hat
        if self.cloth >= 0:
            row["cloth"] = self.cloth
        # THE ONLY PIECE OF `mode` ON THE WIRE, and it is here because it is
        # the only one that changes what is DRAWN: asleep is a different sheet
        # and a dark socket where every other creature carries an ember.
        # Omitted while awake, so it costs a bare zombie nothing.
        if self.asleep:
            row["sl"] = 1
        return row

    @property
    def asleep(self) -> bool:
        """Curled up in its den, eyes shut. See `ai.MODE_SLEEP`."""
        return self.mode == "sleep"


def dress(enemy: Enemy) -> None:
    """Pick a body variant and optional hat / clothes. Call once at spawn."""
    kind = enemy.type
    if kind.variants:
        enemy.variant = random.randrange(len(kind.variants))
    if kind.hats and random.random() < ZOMBIE_HAT_CHANCE:
        enemy.hat = random.randrange(len(kind.hats))
    if kind.clothes and random.random() < ZOMBIE_CLOTH_CHANCE:
        enemy.cloth = random.randrange(len(kind.clothes))
