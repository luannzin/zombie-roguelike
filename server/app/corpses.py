"""Persistent enemy corpses: the record of a fight, left on the floor.

A kill used to be a particle burst that vanished. The body now STAYS — one
row per dead creature, shipped like crates (on welcome, and on a snapshot
only when the list changed). Walking back through your own dead is how an
extraction run reads the map you made.

Nothing here moves, blocks, or drops. The juice (the fall, the growing pool)
is client-side, timed off the kill event; this list is the authoritative
set so a late joiner sees the same forest of bodies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Corpse:
    id: str
    x: float
    y: float
    #: Enemy type key — the client resolves the sheet from enemyTypes.
    t: str
    variant: int
    hat: int
    cloth: int
    #: Last facing, so the fallen sprite keeps the direction it was looking.
    ax: float
    ay: float
    #: Killing blow, so the body falls away from the shot.
    dx: float
    dy: float

    def to_payload(self) -> dict:
        row: dict = {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "t": self.t,
            "v": self.variant,
            "ax": round(self.ax, 3),
            "ay": round(self.ay, 3),
            "dx": round(self.dx, 3),
            "dy": round(self.dy, 3),
        }
        if self.hat >= 0:
            row["hat"] = self.hat
        if self.cloth >= 0:
            row["cloth"] = self.cloth
        return row
