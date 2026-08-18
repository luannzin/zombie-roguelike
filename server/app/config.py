"""Authoritative tuning constants.

These values are shipped to the client inside the `welcome` message so that
client-side prediction runs the exact same numbers as the server simulation.
Never hardcode a gameplay constant on the client: read it from the welcome
payload instead.

==========================================================================
SCALE
==========================================================================
`TILE_SIZE` is THE scale of the game. Every size, speed and distance below is
authored in TILES and multiplied by it, so changing this one number rescales
the whole game consistently — art, collision, movement speed, weapon range.

    TILE_SIZE = 16   ->  sprite 16x16, box 9.6x7.2, speed 70 px/s, range 128
    TILE_SIZE = 32   ->  sprite 32x32, box 19.2x14.4, speed 141 px/s, range 256

Canonical shape:
    tile           1   x 1     tiles   (16 x 16 px)
    sprite frame   1   x 1     tiles   (16 x 16 px)
    collision box  0.6 x 0.45  tiles   (9.6 x 7.2 px, feet footprint)
    hit capsule    r 0.3, full sprite height (stadium from feet to head)

Taller characters (bosses, zombie variants) only need SPRITE_TILES_H raised
for that entity's asset — the renderer anchors any frame height by its bottom
edge, and the hit capsule grows with sprite height, so nothing else changes.

Movement is continuous, not tile-by-tile: position is a float in world pixels
and the grid is only used for collision and (later) pathfinding. That is
cheaper than it sounds — a move costs a handful of float ops plus an overlap
test against at most 4 tiles, so a tick is O(entities), never O(map).

The collision box is deliberately much smaller than the sprite. A full 1-tile
box cannot fit through a 1-tile gap, and a character whose feet collide on its
own shoulders feels awful. Position = CENTRE of the collision box; the sprite
is drawn with its bottom edge at `y + PLAYER_HALF_HEIGHT`.
"""

import math

# --- scale ------------------------------------------------------------------
TILE_SIZE = 16

# --- simulation -------------------------------------------------------------
TICK_RATE = 30
DT = 1.0 / TICK_RATE

# How many queued inputs a single player may consume in one server tick.
# 1 is the normal case; a small burst allowance absorbs network jitter without
# letting a client trivially speed-hack by flooding input packets.
MAX_INPUTS_PER_TICK = 2
MAX_INPUT_QUEUE = 10

# --- player (authored in tiles) ---------------------------------------------
SPRITE_TILES_W = 1.0
SPRITE_TILES_H = 1.0
PLAYER_BOX_TILES_W = 0.6
PLAYER_BOX_TILES_H = 0.45
# Capsule radius ≈ collision half-width; vertical span = full sprite.
PLAYER_HIT_TILES_R = 0.3
MOVE_TILES_PER_SEC = 4.4

SPRITE_WIDTH = round(TILE_SIZE * SPRITE_TILES_W)        # 16
SPRITE_HEIGHT = round(TILE_SIZE * SPRITE_TILES_H)       # 16
PLAYER_HALF_WIDTH = TILE_SIZE * PLAYER_BOX_TILES_W / 2  # 4.8
PLAYER_HALF_HEIGHT = TILE_SIZE * PLAYER_BOX_TILES_H / 2 # 3.6
PLAYER_HIT_RADIUS = TILE_SIZE * PLAYER_HIT_TILES_R      # 4.8
MOVE_SPEED = TILE_SIZE * MOVE_TILES_PER_SEC             # 70.4 px/s

MAX_HP = 100
RESPAWN_DELAY = 2.0          # seconds

# --- spawning (authored in tiles) -------------------------------------------
# After the camp walk-out the party emerges from a VOID corridor on a random
# map edge, then that path seals. Respawn (and a late join) uses a ring around
# that mouth so a death does not throw someone into the middle of the woods.
SPAWN_RING_TILES = 2.5
SPAWN_SEPARATION_TILES = 1.2

SPAWN_RING = TILE_SIZE * SPAWN_RING_TILES
SPAWN_SEPARATION = TILE_SIZE * SPAWN_SEPARATION_TILES

# --- the camp (authored in tiles) -------------------------------------------
# The clearing the party gathers in. It is ONE place shown twice: the lobby
# draws it while people trickle in, and `preparation` is the same map, walkable,
# once the host starts. Every number below is therefore read by both — the seat
# a player was standing on at the campfire is the tile they wake up on.
# Sized so the WIDE shot never frames the edge of the world. The lobby holds the
# camp at `ARENA_ZOOM - 1` (see client/src/render/framing.ts), which on a very
# wide monitor is a lot of forest — the map has to be bigger than that view or
# the camera clamps and the treeline stops looking like it goes on.
CAMP_WIDTH_TILES = 76
CAMP_HEIGHT_TILES = 48
# Open ground around the fire before the treeline starts.
CAMP_CLEARING_TILES = 8.2
# The hearth: the fire plus the ring of players around it. Nothing grows here —
# the map generator refuses trees and rocks, and the client refuses grass and
# ferns on the same ellipse. A bush in front of a seated player hides the
# character the roster is pointing at.
CAMP_HEARTH_TILES = 5.6
# The seat ring. Elliptical: a circle reads as a flat disc from this angle, and
# it is squashed by exactly the ratio the clearing and the decoration mask use.
CAMP_RING_TILES_X = 3.5
CAMP_RING_TILES_Y = 2.0
# How far the bonfire throws light, in tiles. In the camp this is the ONLY light
# — lanterns are off (see zones.py), so this number decides whether the party
# can see each other.
CAMPFIRE_LIGHT_TILES = 10.0

CAMP_RING_X = TILE_SIZE * CAMP_RING_TILES_X
CAMP_RING_Y = TILE_SIZE * CAMP_RING_TILES_Y

# The camp exit: a winding VOID path through the trees on the RIGHT of the
# clearing. This is the typical half-width at the mouth, not a stamped
# rectangle — `camp._carve_exit` wanders, narrows, and frays around it.
# Wide enough for two staggered files, narrow enough to read as a gap in
# the woods. The mouth sits in the treeline, where the party can walk up
# to it and bounce. Forest floor under extreme shadow, not a missing texture.
CAMP_EXIT_HALF_TILES = 2
# How close to the fire (in tiles, from the flame's base to the player's feet)
# you must stand to ready up. Matches the hearth so anyone in the seat ring
# can press E, and nobody out in the scrub can.
CAMP_READY_RANGE_TILES = CAMP_HEARTH_TILES
# Walk-out: a touch slower than a run, so the files read as a departure
# rather than as a race to the trees.
MARCH_TILES_PER_SEC = 3.6
MARCH_SPEED = TILE_SIZE * MARCH_TILES_PER_SEC

# Forest entrance: the camp's black corridor, continued. A winding VOID path
# through a random edge, deep enough to read as the same walk, then a mouth
# clearing the party is marched onto before the woods swallow the way back.
ENTRANCE_DEPTH_TILES = 12
ENTRANCE_MOUTH_TILES = 4.6
# THE EXIT IS SHALLOW, AND THE ARRIVAL IS DEEP, AND THEY ARE READ FROM
# OPPOSITE ENDS — the same asymmetry `entrance.EDGE_PINCH` / `EDGE_FLARE`
# already encodes for how the border ranks are cut.
#
# An arrival corridor is walked from the world's edge INWARD: its depth is the
# length of the dark walk out of it, and twelve tiles of that is the point.
# An exit is walked toward the edge, and what the party sees "appear" is not
# its far end — that end is off in the dark — but its MOUTH: the floor
# threshold with the torches and the paving. At the arrival's depth that
# threshold lands twelve tiles inland, which on a 64-tall map reads as the way
# out having opened in the middle of the woods rather than at the border.
# Short, so the mouth is right against the treeline and the hole in it is the
# thing you walk to.
EXIT_DEPTH_TILES = 5

# --- the store (authored in tiles) ------------------------------------------
# The night's takings, spent. A trader's pitch in a long forest GLADE, read
# left to right: the way in at one end, the way out at the other, and his
# tables strung between them.
#
# `STORE_LANE_TILES` is the load-bearing one. It is the typical height of the
# walkable lane, not a hard width — `store._lane_half` breathes and frays
# around it so the treeline reads as woods rather than as two drawn lines. Kept
# narrow on purpose: this is the one zone whose whole content is "walk past
# four tables and decide", and a glade wide enough to cut a diagonal across is
# a glade where a party leaves without seeing half the stock.
#
# The map is TALLER than the lane so the treeline has depth to thicken into;
# most of that height is woods the party never walks in.
STORE_WIDTH_TILES = 56
STORE_HEIGHT_TILES = 24
STORE_LANE_TILES = 9.0
#: VOID at each end: the way in (which seals) and the way out (which does not).
STORE_CORRIDOR_TILES = 7
#: How close the feet have to be for E to buy. Tighter than a crate — the
#: tables are shoulder to shoulder and a loose radius would offer two at once.
STORE_BUY_TILES = 1.9
STORE_BUY_DIST = TILE_SIZE * STORE_BUY_TILES
#: How far a weapon lifts off its table when somebody is in range, in tiles.
#: Client-side juice, authored here so the lift and the reach cannot drift.
STORE_LIFT_TILES = 0.4
#: What the merchant charges, as a multiple of the gun's catalog value. He is
#: the only place to buy one and he knows it.
#:
#: KEPT LOW ON PURPOSE, and the number is pinned to the first night rather than
#: to a feeling about margins. Day one has a single pad, a single pad is always
#: the LAST pad, and the last pad never offers to keep loading — so a first
#: night banks its quota (`rift.night_need`, 24) plus whatever the final item
#: overshot by, and nothing else. At a 35% markup the cheapest gun on the
#: cheapest table is 54 and that shop is a corridor of things nobody can buy,
#: which is the worst possible first impression for a zone whose whole job is
#: to make the night's take feel like it bought something.
STORE_MARKUP = 1.15

# --- vision (authored in tiles) ---------------------------------------------
# The client draws the darkness; these numbers decide its shape. They live here
# for the same reason every other constant does — one source of truth — and are
# shipped in `welcome.config` so the client never invents its own.
#
# Sight is blocked by solid tiles, so a thicket casts a real shadow. Two lights
# stack: a small glow you always carry, and a directional lantern along your aim.
# Vision is SHARED: the team sees the union of what its members see.
VISION_AMBIENT_TILES = 3.5   # omnidirectional glow around a player
VISION_LANTERN_TILES = 11.0  # how far the lantern cone reaches
VISION_CONE_DEGREES = 75.0   # full width of the cone

VISION_AMBIENT_DIST = TILE_SIZE * VISION_AMBIENT_TILES
VISION_LANTERN_DIST = TILE_SIZE * VISION_LANTERN_TILES

# --- enemies -----------------------------------------------------------------
# Per-creature stat blocks (health, damage, xp, gold, speed…) are NOT here:
# they are `EnemyType` entries in enemies.py, authored in the same tiles/seconds
# units and shipped to the client in `welcome.config.enemyTypes`. Only the rules
# that apply to *every* enemy live below.

# Damage a player can take from melee is rate-limited PER PLAYER, not per
# attacker. Without this, N zombies in contact deal N x damage on the same tick
# and a pack is an instant death sentence no matter how well you play. One hit
# opens a window during which further melee whiffs harmlessly, so the ceiling is
# `max(enemy damage) / MELEE_IMMUNITY` dps regardless of how many are on you.
MELEE_IMMUNITY = 0.6         # seconds of melee i-frames after being hit
RESPAWN_IMMUNITY = 1.5       # longer window on respawn, so you can walk away

# Gun hits slow then pin. Damage adds to a 0..1 meter; at STOP they plant.
# A Glock (~7) is a hitch; a burst stacks into a stop. A Deagle (~24) almost
# pins in one; an AWP (~55) plants on the first round. The hold is how long
# the meter stays before it decays — a pause in fire lets them walk again.
# Never on the wire: the snapshot already carries the slowed vx/vy.
ENEMY_STAGGER_PER_DAMAGE = 1 / 32
ENEMY_STAGGER_MIN = 0.16
ENEMY_STAGGER_MAX_ADD = 0.92
ENEMY_STAGGER_STOP = 0.82
ENEMY_STAGGER_HOLD = 0.22
ENEMY_STAGGER_HOLD_SCALE = 0.35
ENEMY_STAGGER_HOLD_MAX = 1.05
ENEMY_STAGGER_DECAY = 1.6

# Population. The cap scales with the number of living players so a solo run is
# not a swarm and a full room is not empty.
ENEMY_MAX_PER_PLAYER = 6
ENEMY_MAX_TOTAL = 32
ENEMY_SPAWN_INTERVAL = 2.5   # seconds between spawn attempts
ENEMY_FIRST_SPAWN_DELAY = 4.0

# Spawns land in a ring around a random living player: far enough not to appear
# in your face, close enough that they actually reach you.
ENEMY_SPAWN_MIN_TILES = 7.0
ENEMY_SPAWN_MAX_TILES = 15.0
# How hard packed enemies push each other apart (see ai.separation).
ENEMY_SEPARATION_TILES = 0.75

# Enemies arrive as a GROUP, not one at a time. A lone shambler is a chore; two
# to four sharing a patch of forest is an encounter you have to decide about
# before it decides about you. Weights are relative, matched index for index.
ENEMY_GROUP_SIZES = (1, 2, 3, 4)
ENEMY_GROUP_WEIGHTS = (4.0, 3.0, 2.0, 1.5)
# How far apart a group's members land, in tiles. They wander around their OWN
# landing spot afterwards, so this is also roughly how loose the pack stays.
ENEMY_GROUP_SPREAD_TILES = 2.5

# --- enemy senses (authored in tiles/seconds) --------------------------------
# An enemy that has not noticed anybody does not chase: it patrols the ground it
# spawned on. Being seen is a real event with a real cost, which is what makes
# the lantern a decision instead of a light switch.
#
# The cone itself is per-creature (`EnemyType.view_tiles` / `view_degrees`), for
# the same reason speed and damage are. Everything below applies to all of them.

# SIGHT IS SYMMETRIC. It is one dark forest and everybody is standing in it: if
# you can make a shape out at that distance, it can make you out at the same
# distance — provided it happens to be facing you. So an enemy's reach is not a
# number of its own, it is a fraction of the LANTERN's, and it mirrors the two
# sight models in `client/src/render/fov.ts`: the naked eye (EYE_REACH) with the
# lamp off, and the full wash the lamp opens up (SIGHT_REACH) with it on.
# Changing the lantern rescales the danger along with the visibility.
#
# Which of the two applies is decided PER TARGET, by that player's own switch.
# Switching on does not merely let you see further — it lets you BE seen
# further, by everything already looking your way.
ENEMY_VIEW_DARK_SCALE = 0.62
ENEMY_VIEW_LIT_SCALE = 1.0
ENEMY_VIEW_DARK_TILES = VISION_LANTERN_TILES * ENEMY_VIEW_DARK_SCALE
ENEMY_VIEW_LIT_TILES = VISION_LANTERN_TILES * ENEMY_VIEW_LIT_SCALE

# GLARE: the beam falling on something that is not looking at you.
#
# A lantern pointed at a thing is a thing that can notice the lantern, whichever
# way its head happens to be turned. Being in the beam does NOT spot the player
# — it makes the enemy turn around, and the turn is what puts the player inside
# its own cone. That indirection is the whole mechanic: the lamp is not what
# gets you seen, it is what gets you looked at.
ENEMY_GLARE_RATE = 0.55       # awareness per second in the brightest part
# Fraction of the beam's reach that is bright enough to be noticed. Past this
# the light is a wash on the trees and nothing turns around for it.
ENEMY_GLARE_REACH = 0.7
# Ceiling the glare alone may reach. It can make something look; it can never
# make it commit — committing is the sight cone's job, and an enemy that
# charged a light it had not identified would make the lamp unusable rather
# than expensive.
ENEMY_GLARE_CAP = 0.75
# How fast a glared enemy swings round, in degrees per second. Slow enough to
# watch the head come about, fast enough that it is coming about.
ENEMY_TURN_DEGREES = 200.0
# How fast a creature turns while it is only patrolling. Nothing in this game
# ever snaps its head: a body that changes facing between two frames reads as a
# turret, and half of what makes a shambling thing unsettling is that it takes
# its time. Every facing change goes through `ai.turn_towards` at one of these
# two rates — never by assignment.
ENEMY_IDLE_TURN_DEGREES = 70.0

# How long a player has to stand in the cone before the enemy commits. Scales
# with distance: right in its face is nearly instant, the far edge of the cone
# takes its time. Both are short enough that walking through a cone is a
# mistake, long enough that clipping the edge is survivable.
ENEMY_NOTICE_NEAR = 0.45     # seconds to be spotted at touching distance
ENEMY_NOTICE_FAR = 2.0       # seconds to be spotted at the edge of the cone
# How fast suspicion drains once nobody is in the cone any more.
ENEMY_FORGET_RATE = 0.5      # awareness per second
# Above this, an enemy with nothing in its cone stops patrolling and just
# LOOKS. It is what makes a glare or a distant shot visible from across the
# clearing — the pack stops shambling and holds still, facing you — and it is
# also what keeps a turn from being undone by the next leg of its rounds.
ENEMY_SUSPICIOUS = 0.12

# A hunter that has not had eyes on its target for this long goes home. It keeps
# walking to where it last saw them for the whole window, which is what stops a
# corner from being a hard off-switch.
ENEMY_LOSE_DELAY = 4.0
# How far from HOME an enemy will chase before it turns around. Past this it
# stops being a patrol that got interrupted and starts being a conga line.
ENEMY_LEASH_TILES = 22.0
# The patrol: how far from its spawn point an idle enemy will drift, and how
# long it stands still between legs.
ENEMY_HOME_TILES = 3.5
ENEMY_WANDER_PAUSE_MIN = 1.0
ENEMY_WANDER_PAUSE_MAX = 3.5
# Patrol pace, as a fraction of the creature's own speed. A shamble, not a jog —
# the difference between a wandering enemy and a hunting one has to be legible
# from across the clearing.
ENEMY_WANDER_SPEED_SCALE = 0.42
# Close enough to a patrol waypoint (or to home) to call it arrived. It has to
# comfortably exceed the creature's TURN RADIUS (patrol speed over
# ENEMY_IDLE_TURN_DEGREES, about 0.9 tiles for a zombie) — a body that turns in
# a wider circle than its own arrival radius orbits a waypoint it can never
# reach, and the patrol becomes a carousel.
ENEMY_ARRIVE_TILES = 1.3

# One enemy spotting you is every enemy near it spotting you. The shout is a
# single hop on purpose: a chain would walk across the whole map from one
# careless step, and a fight you cannot disengage from is not a fight.
ENEMY_ALERT_SHARE_TILES = 8.0

# --- noise (authored in tiles) ----------------------------------------------
# Anything the player does that an enemy can HEAR emits one of these. Only the
# gunshot exists so far; footsteps, doors and thrown objects are the same shape
# (`ai.Noise`) with a different radius, which is the whole reason this is a list
# on the room and not a flag on the shot event.
#
# A noise fills awareness by `1 + spare` at its centre and tapers to nothing at
# the rim, so the middle of the blast is an instant hunt and the outer band only
# makes heads turn.
SHOT_NOISE_TILES = 16.0
NOISE_ALERT_GAIN = 1.45

# Navigation. An enemy walks straight at its target while it has a clear
# body-width corridor within this range, and follows the flow field otherwise
# (see pathing.py). The cap bounds how far the clearance rays are traced.
ENEMY_DIRECT_SIGHT_TILES = 12.0
# How long an enemy may make no headway before it stops trusting its eyes and
# commits to the field route. Short enough to be invisible, long enough that
# brushing a wall does not send it onto tile centres.
ENEMY_STUCK_DELAY = 0.25

# An enemy nobody is near stops being content and starts being budget: after
# this long with every living player beyond the distance, it is recycled so the
# director can spawn a fresh one where the fight actually is. Players outrun
# zombies by design, so without this the map slowly fills with statues.
ENEMY_DESPAWN_TILES = 34.0
ENEMY_DESPAWN_DELAY = 8.0    # seconds abandoned before recycling

ENEMY_SPAWN_MIN_DIST = TILE_SIZE * ENEMY_SPAWN_MIN_TILES
ENEMY_SPAWN_MAX_DIST = TILE_SIZE * ENEMY_SPAWN_MAX_TILES
ENEMY_SEPARATION = TILE_SIZE * ENEMY_SEPARATION_TILES
ENEMY_DESPAWN_DIST = TILE_SIZE * ENEMY_DESPAWN_TILES
ENEMY_DIRECT_SIGHT_DIST = TILE_SIZE * ENEMY_DIRECT_SIGHT_TILES
ENEMY_GROUP_SPREAD = TILE_SIZE * ENEMY_GROUP_SPREAD_TILES
ENEMY_LEASH_DIST = TILE_SIZE * ENEMY_LEASH_TILES
ENEMY_HOME_DIST = TILE_SIZE * ENEMY_HOME_TILES
ENEMY_ARRIVE_DIST = TILE_SIZE * ENEMY_ARRIVE_TILES
ENEMY_ALERT_SHARE_DIST = TILE_SIZE * ENEMY_ALERT_SHARE_TILES
ENEMY_GLARE_DIST = VISION_LANTERN_DIST * ENEMY_GLARE_REACH
SHOT_NOISE_DIST = TILE_SIZE * SHOT_NOISE_TILES

# --- progression -------------------------------------------------------------
# Levels are derived from total xp by the server and sent already split into
# (level, xp into level, xp needed) so the client never re-implements the curve.
XP_BASE = 40                 # xp required for level 2
XP_GROWTH = 1.4              # each level costs this much more than the last
MAX_LEVEL = 30

# --- coins (authored in tiles) ----------------------------------------------
# A creature's gold is how many coins it CAN drop, not how many it does: each
# point is rolled on its own at COIN_DROP_CHANCE, so a 3-gold zombie pays 0..3
# on a curve with both ends rare and one or two in the middle. A fixed payout
# makes every corpse the same corpse; a roll makes a good one worth noticing.
COIN_DROP_CHANCE = 0.45
COIN_MAGNET_TILES = 2.4
COIN_COLLECT_TILES = 0.4
COIN_BURST_TILES_PER_SEC = 5.5    # pop off the corpse
COIN_REPULSE_TILES_PER_SEC = 3.2  # kick away when magnet starts
COIN_ATTRACT_ACCEL_TILES = 70.0   # px/s² toward the locked player
COIN_ATTRACT_MAX_TILES_PER_SEC = 16.0
COIN_REPULSE_DURATION = 0.1       # seconds of outward kick before attract
COIN_DRAG = 5.5                   # loose / repulse air drag
# How fast attract kills tangential velocity (higher = less orbit).
COIN_ORBIT_DAMP = 18.0

COIN_MAGNET_DIST = TILE_SIZE * COIN_MAGNET_TILES
COIN_COLLECT_DIST = TILE_SIZE * COIN_COLLECT_TILES
COIN_BURST_SPEED = TILE_SIZE * COIN_BURST_TILES_PER_SEC
COIN_REPULSE_SPEED = TILE_SIZE * COIN_REPULSE_TILES_PER_SEC
COIN_ATTRACT_ACCEL = TILE_SIZE * COIN_ATTRACT_ACCEL_TILES
COIN_ATTRACT_MAX_SPEED = TILE_SIZE * COIN_ATTRACT_MAX_TILES_PER_SEC

# --- loot (authored in tiles) -----------------------------------------------
# How close the feet have to be for E to collect. A reach, not a magnet.
LOOT_COLLECT_TILES = 2.25
LOOT_COLLECT_DIST = TILE_SIZE * LOOT_COLLECT_TILES

# How close the feet have to be for E to smash a crate. Same reach as loot.
CRATE_BREAK_TILES = 2.25
CRATE_BREAK_DIST = TILE_SIZE * CRATE_BREAK_TILES

# How close to the extraction console E answers. Wider than a crate: the
# console is the one interactive thing on the map you are meant to be able to
# find while something is chasing you, and a tight radius turns that into
# pixel-hunting at the worst possible moment.
RIFT_ACTIVATE_TILES = 2.75
RIFT_ACTIVATE_DIST = TILE_SIZE * RIFT_ACTIVATE_TILES
# How far into the extraction VOID a living player must walk, past the
# FLOOR mouth toward the map edge, before "Encontre a saída" ticks.
# Standing at the threshold is finding it; crossing the dark is leaving.
EXIT_CROSS_TILES = 1.75
# Quieter than a gunshot — wood giving way, not a muzzle.
CRATE_NOISE_TILES = 5.5
CRATE_NOISE_DIST = TILE_SIZE * CRATE_NOISE_TILES
# Shot box. Walking still uses the 1×1 foot tile; a bullet has to hit the
# wood you aim at. The sheet is 1 × 1.125 tiles — two tiles of height so
# the barrel's body is not empty air.
CRATE_HIT_W_TILES = 1.0
CRATE_HIT_H_TILES = 2.0
CRATE_HIT_W = TILE_SIZE * CRATE_HIT_W_TILES
CRATE_HIT_H = TILE_SIZE * CRATE_HIT_H_TILES

# --- inventory / carry ------------------------------------------------------
# Starting pocket. A later upgrade grows the slot count; weight is independent
# of that and can go PAST the max — the bag never refuses for being heavy.
INVENTORY_SLOTS = 3
CARRY_MAX_WEIGHT = 10.0
# Fraction of max weight where the walk is still full speed. Past this the
# body starts to feel it; at 1.0 the multiplier is CARRY_SLOW_AT_MAX, and it
# keeps falling if they go over, floored at CARRY_SLOW_FLOOR so they can
# still limp out.
CARRY_SLOW_START = 0.2
CARRY_SLOW_AT_MAX = 0.55
CARRY_SLOW_FLOOR = 0.35

# --- combat (authored in tiles) ---------------------------------------------
SHOT_RANGE_TILES = 8.0
MUZZLE_OFFSET_TILES = 0.25

FIRE_COOLDOWN = 0.5         # seconds between shots (~2 shots/s)
SHOT_RANGE = TILE_SIZE * SHOT_RANGE_TILES       # 128 px @ TILE_SIZE=16
MUZZLE_OFFSET = TILE_SIZE * MUZZLE_OFFSET_TILES # 4 px
SHOT_DAMAGE = 8

# --- networking -------------------------------------------------------------
SNAPSHOT_EVERY_N_TICKS = 1   # broadcast rate = TICK_RATE / this
# A snapshot row carries only what MOVES. Names, colours and the score board
# ride a roster attached every N ticks (and on any membership change) — they
# are read by a HUD that republishes at 5 Hz, so paying for them thirty times a
# second bought nothing. 6 ticks = 5 Hz, the same cadence.
ROSTER_EVERY_N_TICKS = 6


def xp_to_next(level: int) -> int:
    """Total xp required to go from `level` to `level + 1`."""
    return round(XP_BASE * XP_GROWTH ** (level - 1))


def level_progress(xp: int) -> tuple[int, int, int]:
    """Split lifetime xp into (level, xp into this level, xp needed to level)."""
    level = 1
    remaining = max(0, xp)
    while level < MAX_LEVEL:
        need = xp_to_next(level)
        if remaining < need:
            return level, remaining, need
        remaining -= need
        level += 1
    return MAX_LEVEL, remaining, xp_to_next(MAX_LEVEL)


def _finite(value: float) -> float | None:
    """`None` for an infinite deadline, so the payload stays valid JSON."""
    return value if math.isfinite(value) else None


def client_config() -> dict:
    """Gameplay constants mirrored by the client's prediction code."""
    # Local import: enemies.py reads TILE_SIZE from this module, so importing it
    # at module scope would be a cycle. Enemy stat blocks still reach the client
    # through this one function, which stays the single client-config contract.
    from . import rift
    from .enemies import enemy_types_payload
    from .loot import catalog_payload
    from .weapons import HOTBAR_SLOTS, catalog_payload as weapons_payload

    return {
        "tickRate": TICK_RATE,
        "dt": DT,
        "tileSize": TILE_SIZE,
        "spriteWidth": SPRITE_WIDTH,
        "spriteHeight": SPRITE_HEIGHT,
        "playerHalfWidth": PLAYER_HALF_WIDTH,
        "playerHalfHeight": PLAYER_HALF_HEIGHT,
        "playerHitRadius": PLAYER_HIT_RADIUS,
        "moveSpeed": MOVE_SPEED,
        "maxHp": MAX_HP,
        "fireCooldown": FIRE_COOLDOWN,
        "shotRange": SHOT_RANGE,
        "shotDamage": SHOT_DAMAGE,
        "muzzleOffset": MUZZLE_OFFSET,
        "enemyTypes": enemy_types_payload(),
        "coinSprite": "coin",
        "backpackSprite": "backpack",
        "visionAmbientTiles": VISION_AMBIENT_TILES,
        "visionLanternTiles": VISION_LANTERN_TILES,
        "visionConeDegrees": VISION_CONE_DEGREES,
        # Camp geometry. The client needs it to keep undergrowth out of the
        # hearth and to light the fire it can already see in the tiles.
        "campfireLightTiles": CAMPFIRE_LIGHT_TILES,
        "hearthTiles": CAMP_HEARTH_TILES,
        "ringTilesX": CAMP_RING_TILES_X,
        "ringTilesY": CAMP_RING_TILES_Y,
        # How close to the fire the ready prompt answers, in tiles.
        "readyRangeTiles": CAMP_READY_RANGE_TILES,
        # How close to a drop E will collect, in tiles.
        "lootCollectTiles": LOOT_COLLECT_TILES,
        # How close to a crate E will smash, in tiles.
        "crateBreakTiles": CRATE_BREAK_TILES,
        # How close to the extraction console E will activate, in tiles.
        "riftActivateTiles": RIFT_ACTIVATE_TILES,
        # The shop. How close to a table E will buy, and how far the weapon on
        # it lifts when somebody is in that range — the lift is the visual half
        # of the same reach, so the two travel together or the gun rises at a
        # distance where the key does nothing.
        "storeBuyTiles": STORE_BUY_TILES,
        "storeLiftTiles": STORE_LIFT_TILES,
        # The extraction platform's clock, in seconds. ONE clock: the client
        # animates the rig off these numbers and the server ends the sequence
        # on them, so the drone that is turning on screen is the drone the
        # server thinks woke. See server/app/rift.py.
        "rift": {
            "consoleLag": rift.CONSOLE_LAG,
            "openAt": rift.OPEN_AT,
            "lightTiles": rift.LIGHT_TILES,
            "drones": rift.DRONES,
            # THE PICKUP, and the client flies the whole thing off these plus
            # the one `closeAt` on the wire. Sirens alone first; then drone `i`
            # leaves the treeline at `liftAlarm + i * droneStagger`, crosses in
            # `droneInbound`, and spends `droneDrop` paying its line down to
            # its corner. `tiedAt` is when the last of them is on.
            "liftAlarm": rift.LIFT_ALARM,
            "droneStagger": rift.DRONE_STAGGER,
            "droneInbound": rift.DRONE_INBOUND,
            "droneDrop": rift.DRONE_DROP,
            "tiedAt": rift.TIED_AT,
            # Then the lift: straining against ground that will not let go, the
            # skid breaking free, and the flight out. `breakAt` is also when
            # the deck's tiles become walkable — the server patches them on
            # that tick — so it is shipped rather than re-derived.
            "liftStrain": rift.LIFT_STRAIN,
            "liftBreak": rift.LIFT_BREAK,
            "liftClimb": rift.LIFT_CLIMB,
            "breakAt": rift.BREAK_AT,
            # The window, and the way it ends. NULL means "never" — the
            # platform waits until a player launches it. It cannot be `inf`:
            # Python serialises that as the bare token `Infinity`, which is not
            # JSON and which `JSON.parse` throws on, taking the entire config
            # payload with it.
            "openTime": _finite(rift.OPEN_TIME),
            "collapseAt": _finite(rift.COLLAPSE_AT),
            "collapseTime": rift.COLLAPSE_TIME,
            "spentAt": _finite(rift.SPENT_AT),
        },
        # Shot box on a crate, in tiles. Bottom-anchored on the contact.
        "crateHitWTiles": CRATE_HIT_W_TILES,
        "crateHitHTiles": CRATE_HIT_H_TILES,
        # Catalog: name, rarity, atlas frame, weight, value, pocket.
        # Guns also have a combat block in `weapons`.
        "loot": catalog_payload(),
        "weapons": weapons_payload(),
        "inventorySlots": INVENTORY_SLOTS,
        "hotbarSlots": HOTBAR_SLOTS,
        "carryMaxWeight": CARRY_MAX_WEIGHT,
        "carrySlowStart": CARRY_SLOW_START,
        "carrySlowAtMax": CARRY_SLOW_AT_MAX,
        "carrySlowFloor": CARRY_SLOW_FLOOR,
    }
