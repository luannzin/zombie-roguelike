"""World gold pickups.

Enemies no longer credit gold on death — they scatter one `Coin` per gold
point. A nearby living player triggers a short outward kick (repulse), then the
coin accelerates in (attract) until collected. Server-authoritative; the client
only draws and juicing the pickup event.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .config import (
    COIN_ATTRACT_ACCEL,
    COIN_ATTRACT_MAX_SPEED,
    COIN_BURST_SPEED,
    COIN_COLLECT_DIST,
    COIN_DRAG,
    COIN_MAGNET_DIST,
    COIN_ORBIT_DAMP,
    COIN_REPULSE_DURATION,
    COIN_REPULSE_SPEED,
)
from .entities import Player

Phase = Literal["loose", "repulse", "attract"]


@dataclass
class Coin:
    id: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    value: int = 1
    phase: Phase = "loose"
    phase_t: float = 0.0
    #: Player the magnet locked onto — sticks until collect or they die.
    target_id: str | None = None

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2),
        }


@dataclass
class PickupEvent:
    coin_id: str
    player_id: str
    x: float
    y: float
    gold: int

    def to_payload(self) -> dict:
        return {
            "id": self.coin_id,
            "by": self.player_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "gold": self.gold,
        }


@dataclass
class CoinStepResult:
    collected: list[PickupEvent] = field(default_factory=list)


def spawn_burst(coin_id: str, x: float, y: float, index: int, total: int) -> Coin:
    """One coin popping off a corpse — fan them so stacks read as a spray."""
    base = (index / max(1, total)) * math.tau
    angle = base + random.uniform(-0.35, 0.35)
    speed = COIN_BURST_SPEED * (0.55 + random.random() * 0.7)
    return Coin(
        id=coin_id,
        x=x + math.cos(angle) * random.uniform(0.0, 2.0),
        y=y + math.sin(angle) * random.uniform(0.0, 2.0),
        vx=math.cos(angle) * speed,
        vy=math.sin(angle) * speed,
    )


def step(
    coins: dict[str, Coin],
    players: Iterable[Player],
    dt: float,
) -> CoinStepResult:
    """Advance every coin. Mutates `coins` in place; removes collected ones."""
    living = [p for p in players if p.alive]
    result = CoinStepResult()
    dead: list[str] = []

    for coin in coins.values():
        if coin.phase == "loose":
            _drag(coin, dt)
            target = _nearest(coin, living, COIN_MAGNET_DIST)
            if target is not None:
                _begin_repulse(coin, target)
        elif coin.phase == "repulse":
            _drag(coin, dt)
            coin.phase_t += dt
            if coin.phase_t >= COIN_REPULSE_DURATION:
                coin.phase = "attract"
                coin.phase_t = 0.0
        elif coin.phase == "attract":
            target = _resolve_target(coin, living)
            if target is None:
                coin.phase = "loose"
                coin.target_id = None
                _drag(coin, dt)
            else:
                _attract(coin, target, dt)
                if _dist2(coin, target) <= COIN_COLLECT_DIST * COIN_COLLECT_DIST:
                    target.gold += coin.value
                    result.collected.append(
                        PickupEvent(coin.id, target.id, coin.x, coin.y, coin.value)
                    )
                    dead.append(coin.id)
                    continue

        coin.x += coin.vx * dt
        coin.y += coin.vy * dt

    for cid in dead:
        coins.pop(cid, None)
    return result


def _begin_repulse(coin: Coin, target: Player) -> None:
    coin.phase = "repulse"
    coin.phase_t = 0.0
    coin.target_id = target.id
    dx = coin.x - target.x
    dy = coin.y - target.y
    dist = math.hypot(dx, dy) or 1.0
    # Kick straight out — tiny noise only. Sideways kick is what starts orbits.
    coin.vx = (dx / dist) * COIN_REPULSE_SPEED + random.uniform(-2.0, 2.0)
    coin.vy = (dy / dist) * COIN_REPULSE_SPEED + random.uniform(-2.0, 2.0)


def _attract(coin: Coin, target: Player, dt: float) -> None:
    dx = target.x - coin.x
    dy = target.y - coin.y
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist

    # Bleed tangential speed every tick so centripetal pull cannot loop forever.
    radial = coin.vx * ux + coin.vy * uy
    tx = coin.vx - ux * radial
    ty = coin.vy - uy * radial
    side = math.exp(-COIN_ORBIT_DAMP * dt)
    # Keep only the inward component (ux points at the player).
    radial = max(radial, 0.0)
    coin.vx = ux * radial + tx * side
    coin.vy = uy * radial + ty * side

    coin.vx += ux * COIN_ATTRACT_ACCEL * dt
    coin.vy += uy * COIN_ATTRACT_ACCEL * dt
    speed = math.hypot(coin.vx, coin.vy)
    if speed > COIN_ATTRACT_MAX_SPEED:
        scale = COIN_ATTRACT_MAX_SPEED / speed
        coin.vx *= scale
        coin.vy *= scale


def _drag(coin: Coin, dt: float) -> None:
    damp = math.exp(-COIN_DRAG * dt)
    coin.vx *= damp
    coin.vy *= damp


def _resolve_target(coin: Coin, living: list[Player]) -> Player | None:
    if coin.target_id is None:
        return None
    for player in living:
        if player.id == coin.target_id:
            return player
    return None


def _nearest(coin: Coin, living: list[Player], max_dist: float) -> Player | None:
    best: Player | None = None
    best_d2 = max_dist * max_dist
    for player in living:
        d2 = _dist2(coin, player)
        if d2 < best_d2:
            best_d2 = d2
            best = player
    return best


def _dist2(coin: Coin, player: Player) -> float:
    dx = coin.x - player.x
    dy = coin.y - player.y
    return dx * dx + dy * dy
