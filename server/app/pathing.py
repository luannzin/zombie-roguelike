"""Grid navigation for enemies: one BFS flow field per player.

Greedy chase — walk straight at the target and let wall collision slide you
along — cannot get around cover. Anything shaped like a pillar or an L traps a
chaser: it presses into the wall, the slide cancels the blocked axis, and the
remaining axis points back at the obstacle it just hit. That is the bug this
module exists to fix.

**Why a flow field and not A* per enemy.** The arena has a handful of goals
(players) and up to 32 chasers. Per-enemy A* runs one search per enemy; a flow
field runs one breadth-first search per PLAYER, and every enemy hunting that
player reads its answer in O(1) — the cost stops scaling with the size of the
horde, which is exactly the direction a zombie game grows in. On the 64x40
arena a rebuild visits ~2500 tiles, and it only happens when the player crosses
a tile boundary (rate-limited by REBUILD_INTERVAL).

The field stores, for every walkable tile, the number of 4-neighbour steps to
the goal. Steering reads the current tile, picks the neighbour with the lowest
count, and walks to that tile's centre. Following the gradient downhill is what
makes an enemy commit to walking AROUND a wall instead of into it.

Diagonals are allowed when stepping, but never through a corner: a diagonal
move is only taken when both of its orthogonal neighbours are open, so a body
never clips the point where two walls meet.
"""

from __future__ import annotations

from collections import deque

from .config import TILE_SIZE
from .world import TileMap

#: Tile that the BFS never reached — a wall, or floor sealed off from the goal.
UNREACHABLE = -1

#: Minimum seconds between rebuilds of one player's field. A player crossing
#: tiles at full speed would otherwise trigger ~4 rebuilds a second.
REBUILD_INTERVAL = 0.2

#: 4-neighbour steps used to build the distance field.
_ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
#: 8-neighbour steps used when reading it. Diagonals are corner-checked.
_NEIGHBOURS = _ORTHOGONAL + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def tile_of(x: float, y: float) -> tuple[int, int]:
    return int(x // TILE_SIZE), int(y // TILE_SIZE)


def tile_centre(tx: int, ty: int) -> tuple[float, float]:
    half = TILE_SIZE / 2
    return tx * TILE_SIZE + half, ty * TILE_SIZE + half


class FlowField:
    """Step-count-to-goal for every walkable tile, plus the downhill step."""

    def __init__(self, world: TileMap):
        self.world = world
        self.width = world.width
        self.height = world.height
        self.dist: list[int] = [UNREACHABLE] * (self.width * self.height)
        self.goal: tuple[int, int] | None = None

    def rebuild(self, gx: int, gy: int) -> bool:
        """Flood the map outward from the goal tile. False if it is not walkable."""
        if self.world.is_solid_tile(gx, gy):
            return False

        width = self.width
        dist = [UNREACHABLE] * (width * self.height)
        dist[gy * width + gx] = 0
        queue = deque([(gx, gy, 0)])

        while queue:
            x, y, d = queue.popleft()
            step = d + 1
            for dx, dy in _ORTHOGONAL:
                nx = x + dx
                ny = y + dy
                if nx < 0 or ny < 0 or nx >= width or ny >= self.height:
                    continue
                index = ny * width + nx
                if dist[index] != UNREACHABLE or self.world.is_solid_tile(nx, ny):
                    continue
                dist[index] = step
                queue.append((nx, ny, step))

        self.dist = dist
        self.goal = (gx, gy)
        return True

    def distance(self, tx: int, ty: int) -> int:
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return UNREACHABLE
        return self.dist[ty * self.width + tx]

    def next_step(self, tx: int, ty: int) -> tuple[int, int] | None:
        """The neighbouring tile to walk into, or None at the goal / off-field."""
        here = self.distance(tx, ty)
        if here <= 0:
            # 0 = standing on the goal, UNREACHABLE = walled in or off-map.
            return None

        best: tuple[int, int] | None = None
        best_dist = here
        for dx, dy in _NEIGHBOURS:
            nx = tx + dx
            ny = ty + dy
            neighbour = self.distance(nx, ny)
            if neighbour == UNREACHABLE or neighbour >= best_dist:
                continue
            # No corner cutting: a diagonal needs both orthogonals open, or the
            # body clips the wall junction and sticks.
            if dx and dy:
                if self.world.is_solid_tile(tx + dx, ty) or self.world.is_solid_tile(tx, ty + dy):
                    continue
            best_dist = neighbour
            best = (nx, ny)
        return best


class Navigator:
    """Keeps one FlowField per living player and answers steering queries.

    Fields are rebuilt when their player changes tile (rate-limited), and
    dropped when the player dies or leaves — a dead player is not a destination.
    """

    def __init__(self, world: TileMap):
        self.world = world
        self.fields: dict[str, FlowField] = {}
        self.cooldowns: dict[str, float] = {}

    def update(self, players, dt: float) -> None:
        """Refresh every living player's field. Call once per tick."""
        living = {p.id: p for p in players if p.alive}

        for pid in [pid for pid in self.fields if pid not in living]:
            self.fields.pop(pid, None)
            self.cooldowns.pop(pid, None)

        for pid, player in living.items():
            cooldown = self.cooldowns.get(pid, 0.0) - dt
            field = self.fields.get(pid)
            goal = tile_of(player.x, player.y)

            if field is not None and (field.goal == goal or cooldown > 0.0):
                self.cooldowns[pid] = cooldown
                continue

            if field is None:
                field = FlowField(self.world)
                self.fields[pid] = field
            field.rebuild(*goal)
            self.cooldowns[pid] = REBUILD_INTERVAL

    def invalidate(self) -> None:
        """Drop every field. A smashed crate opens a tile the last flood missed."""
        self.fields.clear()
        self.cooldowns.clear()

    def steer(self, x: float, y: float, target_id: str) -> tuple[float, float] | None:
        """Unit direction from (x, y) towards `target_id`, following the field.

        None when there is no usable field — the caller falls back to walking
        straight at the target, which is correct in open ground anyway.
        """
        field = self.fields.get(target_id)
        if field is None:
            return None

        tx, ty = tile_of(x, y)
        step = field.next_step(tx, ty)
        if step is None:
            return None

        cx, cy = tile_centre(*step)
        dx = cx - x
        dy = cy - y
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 1e-6:
            return None
        return dx / length, dy / length
