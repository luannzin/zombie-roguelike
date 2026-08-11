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

Taller characters (bosses, zombie variants) only need SPRITE_TILES_H raised
for that entity's asset — the renderer anchors any frame height by its bottom
edge, so nothing else changes.

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
PLAYER_HIT_TILES_R = 0.375
MOVE_TILES_PER_SEC = 4.4

SPRITE_WIDTH = round(TILE_SIZE * SPRITE_TILES_W)        # 16
SPRITE_HEIGHT = round(TILE_SIZE * SPRITE_TILES_H)       # 16
PLAYER_HALF_WIDTH = TILE_SIZE * PLAYER_BOX_TILES_W / 2  # 4.8
PLAYER_HALF_HEIGHT = TILE_SIZE * PLAYER_BOX_TILES_H / 2 # 3.6
PLAYER_HIT_RADIUS = TILE_SIZE * PLAYER_HIT_TILES_R      # 6.0
MOVE_SPEED = TILE_SIZE * MOVE_TILES_PER_SEC             # 70.4 px/s

MAX_HP = 100
RESPAWN_DELAY = 2.0          # seconds

# --- combat (authored in tiles) ---------------------------------------------
SHOT_RANGE_TILES = 8.0
MUZZLE_OFFSET_TILES = 0.25

FIRE_COOLDOWN = 0.18         # seconds between shots
SHOT_RANGE = TILE_SIZE * SHOT_RANGE_TILES       # 128 px @ TILE_SIZE=16
MUZZLE_OFFSET = TILE_SIZE * MUZZLE_OFFSET_TILES # 4 px
SHOT_DAMAGE = 12

# --- networking -------------------------------------------------------------
SNAPSHOT_EVERY_N_TICKS = 1   # broadcast rate = TICK_RATE / this


def client_config() -> dict:
    """Gameplay constants mirrored by the client's prediction code."""
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
    }
