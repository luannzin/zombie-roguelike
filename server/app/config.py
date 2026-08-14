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
# Players start together in the middle clearing, not scattered across the map:
# a co-op run that opens with everyone lost is a bad first ten seconds. The ring
# keeps them close without stacking them on one tile.
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

# --- progression -------------------------------------------------------------
# Levels are derived from total xp by the server and sent already split into
# (level, xp into level, xp needed) so the client never re-implements the curve.
XP_BASE = 40                 # xp required for level 2
XP_GROWTH = 1.4              # each level costs this much more than the last
MAX_LEVEL = 30

# --- coins (authored in tiles) ----------------------------------------------
# Enemies drop one world coin per gold point. Magnet: short outward kick, then
# suck in. Attract bleeds sideways speed so coins cannot orbit forever.
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

# --- combat (authored in tiles) ---------------------------------------------
SHOT_RANGE_TILES = 8.0
MUZZLE_OFFSET_TILES = 0.25

FIRE_COOLDOWN = 0.5         # seconds between shots (~2 shots/s)
SHOT_RANGE = TILE_SIZE * SHOT_RANGE_TILES       # 128 px @ TILE_SIZE=16
MUZZLE_OFFSET = TILE_SIZE * MUZZLE_OFFSET_TILES # 4 px
SHOT_DAMAGE = 8

# --- networking -------------------------------------------------------------
SNAPSHOT_EVERY_N_TICKS = 1   # broadcast rate = TICK_RATE / this


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


def client_config() -> dict:
    """Gameplay constants mirrored by the client's prediction code."""
    # Local import: enemies.py reads TILE_SIZE from this module, so importing it
    # at module scope would be a cycle. Enemy stat blocks still reach the client
    # through this one function, which stays the single client-config contract.
    from .enemies import enemy_types_payload

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
    }
