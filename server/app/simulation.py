"""Movement simulation.

This is the function the client re-implements for prediction
(client/src/game/simulation.ts). Any change here MUST be mirrored there or
prediction will drift and the player will rubber-band.
"""

from __future__ import annotations

from .config import MOVE_SPEED, PLAYER_RADIUS
from .entities import InputCmd, Player
from .world import TileMap

_SQRT1_2 = 0.7071067811865476


def move_dir(cmd: InputCmd) -> tuple[float, float]:
    dx = (1.0 if cmd.right else 0.0) - (1.0 if cmd.left else 0.0)
    dy = (1.0 if cmd.down else 0.0) - (1.0 if cmd.up else 0.0)
    if dx != 0.0 and dy != 0.0:
        dx *= _SQRT1_2
        dy *= _SQRT1_2
    return dx, dy


def apply_input(player: Player, cmd: InputCmd, world: TileMap, dt: float) -> None:
    dx, dy = move_dir(cmd)
    player.vx = dx * MOVE_SPEED
    player.vy = dy * MOVE_SPEED

    player.x = world.move_axis(player.x, player.y, PLAYER_RADIUS, player.vx * dt, 0)
    player.y = world.move_axis(player.x, player.y, PLAYER_RADIUS, player.vy * dt, 1)

    player.aim_x = cmd.aim_x
    player.aim_y = cmd.aim_y
