"""Breakable crates: boxes, barrels and the other wood on the crate sheet.

Scenery still PLACES them — a dumpsite without its pile is not a dumpsite —
but once the stamp has claimed the LOW tiles they become live objects. The
client draws them from this list, not from the scenery props, so a smash can
remove one without rewriting the map payload.

Smash is server-authoritative. E sends `{type:"break","id"}`; a bullet that
stops on a crate's tile does the same. Three outcomes, rolled here: nothing
(the client plays wind), a few coins, or one catalog item on the floor.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .config import TILE_SIZE
from .loot import roll_item
from .scenery import STANDING, Prop

KIND = "crate"

DROP_EMPTY = "empty"
DROP_COIN = "coin"
DROP_ITEM = "item"

# Empty is the common case — a pile of wood is not a shop. Coin next.
# An item is the surprise.
DROP_WEIGHTS: dict[str, float] = {
    DROP_EMPTY: 50,
    DROP_COIN: 32,
    DROP_ITEM: 18,
}

COIN_MIN = 1
COIN_MAX = 3


@dataclass
class Crate:
    id: str
    x: float
    y: float
    variant: int
    flip: bool
    tx: int
    ty: int

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
            "flip": 1 if self.flip else 0,
        }


@dataclass
class CrateBreak:
    crate_id: str
    x: float
    y: float
    variant: int
    flip: bool
    drop: str
    key: str | None = None

    def to_payload(self) -> dict:
        row = {
            "id": self.crate_id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "v": self.variant,
            "flip": 1 if self.flip else 0,
            "drop": self.drop,
        }
        if self.key:
            row["k"] = self.key
        return row


def footprint(x: float, y: float) -> tuple[int, int]:
    """The LOW tile a crate claims. Mirrors `scenery._cells` for a 1-wide piece."""
    tx = int(math.floor(x / TILE_SIZE))
    ty = int(math.floor(y / TILE_SIZE - 1e-6))
    return tx, ty


def attach(population) -> list[dict]:
    """Strip standing crates from a Population and return their wire rows.

    The LOW tiles are already stamped. Call this after `scenery.populate`,
    before `to_payload`, so the map does not draw the same box twice.
    """
    kept, crates = extract(population.props)
    population.props[:] = kept
    return [crate.to_payload() for crate in crates]


def extract(props: list[Prop]) -> tuple[list[Prop], list[Crate]]:
    """Pull standing crates out of a scenery prop list and give them ids."""
    kept: list[Prop] = []
    crates: list[Crate] = []
    next_id = 1
    for prop in props:
        if prop.kind == KIND and prop.layer == STANDING:
            tx, ty = footprint(prop.x, prop.y)
            crates.append(
                Crate(
                    id=f"k{next_id}",
                    x=prop.x,
                    y=prop.y,
                    variant=prop.variant,
                    flip=prop.flip,
                    tx=tx,
                    ty=ty,
                )
            )
            next_id += 1
        else:
            kept.append(prop)
    return kept, crates


def from_payloads(rows: list[dict]) -> dict[str, Crate]:
    crates: dict[str, Crate] = {}
    for row in rows:
        crate_id = str(row["id"])
        x = float(row["x"])
        y = float(row["y"])
        tx, ty = footprint(x, y)
        crates[crate_id] = Crate(
            id=crate_id,
            x=x,
            y=y,
            variant=int(row.get("v", 0)),
            flip=bool(row.get("flip")),
            tx=tx,
            ty=ty,
        )
    return crates


def nearest(crates: dict[str, Crate], x: float, y: float, max_dist: float) -> Crate | None:
    best: Crate | None = None
    best_d2 = max_dist * max_dist
    for crate in crates.values():
        dx = crate.x - x
        dy = crate.y - y
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = crate
    return best


def at_tile(crates: dict[str, Crate], tx: int, ty: int) -> Crate | None:
    for crate in crates.values():
        if crate.tx == tx and crate.ty == ty:
            return crate
    return None


def hit_tile(ox: float, oy: float, dx: float, dy: float, distance: float) -> tuple[int, int]:
    """The tile a wall-hit landed in. Step a hair past the face into the cell."""
    px = ox + dx * (distance + 0.5)
    py = oy + dy * (distance + 0.5)
    return int(px // TILE_SIZE), int(py // TILE_SIZE)


def roll_drop(rng: random.Random) -> tuple[str, str | None, int]:
    """`(kind, item_key, coin_count)`. Only one of item/coins is set."""
    total = sum(DROP_WEIGHTS.values())
    roll = rng.uniform(0, total)
    kind = DROP_EMPTY
    for name, weight in DROP_WEIGHTS.items():
        roll -= weight
        if roll <= 0:
            kind = name
            break
    if kind == DROP_COIN:
        return DROP_COIN, None, rng.randint(COIN_MIN, COIN_MAX)
    if kind == DROP_ITEM:
        item = roll_item(rng)
        if item is None:
            return DROP_EMPTY, None, 0
        return DROP_ITEM, item.key, 0
    return DROP_EMPTY, None, 0
