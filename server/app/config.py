"""Authoritative tuning constants.

These values are shipped to the client inside the `welcome` message so that
client-side prediction runs the exact same numbers as the server simulation.
Never hardcode a gameplay constant on the client: read it from the welcome
payload instead.
"""

# --- simulation -------------------------------------------------------------
TICK_RATE = 30
DT = 1.0 / TICK_RATE

# How many queued inputs a single player may consume in one server tick.
# 1 is the normal case; a small burst allowance absorbs network jitter without
# letting a client trivially speed-hack by flooding input packets.
MAX_INPUTS_PER_TICK = 2
MAX_INPUT_QUEUE = 10

# --- world ------------------------------------------------------------------
TILE_SIZE = 16

# --- player -----------------------------------------------------------------
PLAYER_RADIUS = 5.0          # half-extent of the square collision box, world px
PLAYER_HIT_RADIUS = 6.0      # circle radius used by hitscan tests
MOVE_SPEED = 70.0            # world px / second
MAX_HP = 100
RESPAWN_DELAY = 2.0          # seconds

# --- combat -----------------------------------------------------------------
FIRE_COOLDOWN = 0.18         # seconds between shots
SHOT_RANGE = 260.0           # world px
SHOT_DAMAGE = 12

# --- networking -------------------------------------------------------------
SNAPSHOT_EVERY_N_TICKS = 1   # broadcast rate = TICK_RATE / this


def client_config() -> dict:
    """Gameplay constants mirrored by the client's prediction code."""
    return {
        "tickRate": TICK_RATE,
        "dt": DT,
        "tileSize": TILE_SIZE,
        "playerRadius": PLAYER_RADIUS,
        "playerHitRadius": PLAYER_HIT_RADIUS,
        "moveSpeed": MOVE_SPEED,
        "maxHp": MAX_HP,
        "fireCooldown": FIRE_COOLDOWN,
        "shotRange": SHOT_RANGE,
        "shotDamage": SHOT_DAMAGE,
    }
