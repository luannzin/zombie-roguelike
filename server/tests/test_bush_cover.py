"""Undergrowth is cover, and both sides must agree on where it is.

Run:  python tests/test_bush_cover.py   (from server/)

Two claims, and the first is the one that rots silently:
  * `world.tile_hash` is the client's `render/terrain.ts` hash BIT FOR BIT.
    Nothing at runtime notices when it is not — the server just applies cover
    on tiles the player cannot see a bush on, which reads as broken senses.
  * standing in a bush shortens a creature's reach against you, and the
    lantern overrules it. Light in a bush is a lit bush.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai  # noqa: E402
from app.config import BUSH_CHANCE, BUSH_CONCEAL_SCALE, TILE_SIZE  # noqa: E402
from app.enemies import ZOMBIE, Enemy  # noqa: E402
from app.entities import Player  # noqa: E402
from app.world import FLOOR, TileMap, tile_hash  # noqa: E402

# Straight out of `Math.imul` in a browser — see the header. Regenerate with
# the same loop against client/src/render/terrain.ts if the hash ever moves.
_JS_SAMPLES = {
    (0, 0, 7, 13): 0.647286347497,
    (1, 0, 7, 13): 0.464037768185,
    (0, 1, 7, 13): 0.575926470704,
    (17, 23, 7, 13): 0.581908712299,
    (-3, -3, 7, 13): 0.059678717996,
    (39, 39, 99998, 13): 0.477729154862,
}


def test_hash_matches_client() -> None:
    for (tx, ty, seed, salt), expected in _JS_SAMPLES.items():
        got = tile_hash(tx, ty, seed, salt)
        assert abs(got - expected) < 1e-9, f"tile_hash{(tx, ty, seed, salt)} = {got}"


def _map(seed: int) -> TileMap:
    return TileMap([[FLOOR] * 40 for _ in range(40)], seed=seed)


def test_bush_tiles_exist_and_are_sparse() -> None:
    world = _map(7)
    bushes = [
        (tx, ty)
        for ty in range(world.height)
        for tx in range(world.width)
        if world.bush_at(tx, ty)
    ]
    assert bushes, "no bushes on a 40x40 floor"
    share = len(bushes) / (world.width * world.height)
    # Wide band on purpose: this asserts the hash is a hash, not a specific map.
    assert BUSH_CHANCE * 0.4 < share < BUSH_CHANCE * 2.2, share


def _sees(world: TileMap, bx: int, by: int, tiles: float, lantern: bool) -> bool:
    """Can a zombie `tiles` due west of tile (bx, by) see a player standing on it?"""
    px = (bx + 0.5) * TILE_SIZE
    py = (by + 0.5) * TILE_SIZE
    player = Player(id="p", name="p", color="#fff", x=px, y=py)
    player.last_input.lantern = lantern
    enemy = Enemy(id="e", type=ZOMBIE, x=px - tiles * TILE_SIZE, y=py)
    enemy.aim_x, enemy.aim_y = 1.0, 0.0
    return ai.look(enemy, [player], world) is player


def test_bush_shortens_reach() -> None:
    world = _map(7)
    bush = next(
        (tx, ty)
        for ty in range(4, 36)
        for tx in range(20, 36)
        if world.bush_at(tx, ty)
    )
    open_tile = (bush[0], bush[1] + 1)
    assert not world.bush_at(*open_tile), "picked a bush stack; pick another seed"

    # A distance inside the naked-eye reach but outside the concealed one.
    reach = ZOMBIE.view_tiles
    between = reach * (BUSH_CONCEAL_SCALE + 1.0) / 2

    assert _sees(world, *open_tile, between, lantern=False), "open ground must be seen"
    assert not _sees(world, *bush, between, lantern=False), "bush must conceal"
    assert _sees(world, *bush, between, lantern=True), "a lamp overrules cover"
    assert _sees(world, *bush, 1.5, lantern=False), "cover is not invisibility"


if __name__ == "__main__":
    test_hash_matches_client()
    test_bush_tiles_exist_and_are_sparse()
    test_bush_shortens_reach()
    print("ok")
