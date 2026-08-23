"""Movement simulation.

This is the function the client re-implements for prediction
(client/src/game/simulation.ts). Any change here MUST be mirrored there or
prediction will drift and the player will rubber-band.

Movement is continuous: velocity * dt in world pixels, then one axis-separated
collision pass against the tile grid. Cost per entity is constant — a couple of
float ops plus an overlap test over at most 2x2 tiles.
"""

from __future__ import annotations

from .config import (
    CARRY_MAX_WEIGHT,
    CARRY_SLOW_AT_MAX,
    CARRY_SLOW_FLOOR,
    CARRY_SLOW_START,
    HIT_STAGGER_SCALE,
    MOVE_SPEED,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    SPRINT_SPEED,
    STAMINA_DRAIN,
    STAMINA_MAX,
    STAMINA_RECOVER,
    STAMINA_REGEN_REST,
    STAMINA_REGEN_WALK,
)
from .entities import InputCmd, Player
from .world import TileMap

_SQRT1_2 = 0.7071067811865476


def carry_scale(weight: float, max_weight: float = CARRY_MAX_WEIGHT) -> float:
    """How much of MOVE_SPEED a body gets at this carried weight.

    Full speed up to CARRY_SLOW_START of max. Then a straight line down to
    CARRY_SLOW_AT_MAX at the cap, and it keeps falling if they go over,
    never below CARRY_SLOW_FLOOR. Mirror: client/src/game/simulation.ts.

    `max_weight` is a PARAMETER rather than the constant because a skill moves
    it (`skills.Mods.carry`). The shape of the curve is still one decision —
    only where the free band ends slides.
    """
    if max_weight <= 0.0:
        return 1.0
    ratio = weight / max_weight
    if ratio <= CARRY_SLOW_START:
        return 1.0
    span = 1.0 - CARRY_SLOW_START
    t = (ratio - CARRY_SLOW_START) / span if span > 0.0 else 1.0
    scale = 1.0 + (CARRY_SLOW_AT_MAX - 1.0) * t
    return CARRY_SLOW_FLOOR if scale < CARRY_SLOW_FLOOR else scale


def move_dir(cmd: InputCmd) -> tuple[float, float]:
    dx = (1.0 if cmd.right else 0.0) - (1.0 if cmd.left else 0.0)
    dy = (1.0 if cmd.down else 0.0) - (1.0 if cmd.up else 0.0)
    if dx != 0.0 and dy != 0.0:
        dx *= _SQRT1_2
        dy *= _SQRT1_2
    return dx, dy


def running(player: Player, cmd: InputCmd, moving: bool) -> bool:
    """Whether this body is actually RUNNING this tick.

    Holding SHIFT is a request, not a state: a body standing still is not
    running (it would drain the bar for nothing), and a body that spent the bar
    is locked out until `STAMINA_RECOVER` of it is back — see `Player.winded`.
    Mirror: client/src/game/simulation.ts.
    """
    return moving and cmd.sprint and not player.winded and player.stamina > 0.0


def step_stamina(player: Player, run: bool, moving: bool, dt: float) -> None:
    """Spend or refill the breath, and work the exhaustion latch.

    STATELESS BY DESIGN — no rest timer, no cooldown. What the bar reads is
    decided entirely by (running, moving), so prediction can replay it from the
    server's number and land on exactly the value the server holds. The one
    piece of memory is `winded`, and it is a latch rather than a clock, which
    is why it rides the snapshot beside the number.

    Standing still refills faster than walking does. That is the only place the
    system asks for a decision: catching your breath properly means stopping in
    a dark forest. Mirror: client/src/game/simulation.ts.
    """
    if run:
        player.stamina -= STAMINA_DRAIN * dt
        if player.stamina <= 0.0:
            player.stamina = 0.0
            player.winded = True
        return
    regen = STAMINA_REGEN_WALK if moving else STAMINA_REGEN_REST
    player.stamina = min(STAMINA_MAX, player.stamina + regen * dt)
    if player.winded and player.stamina >= STAMINA_MAX * STAMINA_RECOVER:
        player.winded = False


def step_stagger(player: Player, dt: float) -> float:
    """Run the drag from the last blow down, and return what it multiplies by.

    A CLOCK, TICKED IN THE WALK, and it lives here rather than in the room's
    tick for exactly one reason: prediction. The client replays unacked inputs
    through `apply_input` after every reconcile, so anything that decays with
    time and changes speed has to decay inside the same function, or the replay
    walks the body at a speed the server never used. Same shape as
    `step_stamina` above and for the same reason.

    Mirror: client/src/game/simulation.ts.
    """
    if player.stagger <= 0.0:
        return 1.0
    player.stagger = max(0.0, player.stagger - dt)
    return HIT_STAGGER_SCALE


def apply_input(player: Player, cmd: InputCmd, world: TileMap, dt: float) -> None:
    dx, dy = move_dir(cmd)
    moving = dx != 0.0 or dy != 0.0
    run = running(player, cmd, moving)
    step_stamina(player, run, moving, dt)

    mods = player.skills.mods
    speed = MOVE_SPEED * mods.speed * carry_scale(player.carry_weight, mods.carry)
    if run:
        speed *= SPRINT_SPEED
    # THE SHIELD IS THE LAST TERM AND IT MULTIPLIES EVERYTHING. A body behind
    # one is slow whatever else is true about it — sprinting behind a riot
    # shield is still slower than walking without one, which is the whole
    # reason raising it is a decision rather than a posture. Resolved before
    # this runs; see `Player.block_speed`.
    speed *= player.block_speed
    # AND THE DRAG IS THE LAST TERM OF ALL, under even the shield. Being hit
    # takes precedence over every choice the player made about how fast to
    # move, because the entire point of it is that it is not a choice — a body
    # that could sprint out of a pack at full speed is a body for which being
    # surrounded costs nothing. See `HIT_STAGGER_SCALE`.
    speed *= step_stagger(player, dt)
    player.vx = dx * speed
    player.vy = dy * speed

    hw = PLAYER_HALF_WIDTH
    hh = PLAYER_HALF_HEIGHT
    player.x = world.move_axis(player.x, player.y, hw, hh, player.vx * dt, 0)
    player.y = world.move_axis(player.x, player.y, hw, hh, player.vy * dt, 1)

    player.aim_x = cmd.aim_x
    player.aim_y = cmd.aim_y
