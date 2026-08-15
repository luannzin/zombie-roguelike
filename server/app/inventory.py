"""The pocket a player carries into a level.

Loot on the ground is `loot.py`. This is what happens after E: a short row of
slots, a running weight, and a place extraction can later spend from. Slots
are the hard limit — a full bag refuses a new kind. Weight is not: the bar
can go past max, and the only cost is that the body gets slower.

Same item key stacks in the first matching slot. A later upgrade grows
`cap`; nothing here assumes three forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loot import BY_KEY


@dataclass
class Slot:
    key: str
    qty: int

    def to_payload(self) -> dict:
        return {"k": self.key, "n": self.qty}


@dataclass
class Inventory:
    cap: int
    slots: list[Slot | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.slots) < self.cap:
            self.slots.extend([None] * (self.cap - len(self.slots)))
        elif len(self.slots) > self.cap:
            self.slots = self.slots[: self.cap]

    def add(self, key: str) -> int | None:
        """Put one of `key` in the bag. Returns the slot index, or None if full."""
        if key not in BY_KEY:
            return None
        for index, slot in enumerate(self.slots):
            if slot is not None and slot.key == key:
                slot.qty += 1
                return index
        for index, slot in enumerate(self.slots):
            if slot is None:
                self.slots[index] = Slot(key=key, qty=1)
                return index
        return None

    def can_stow(self, key: str) -> bool:
        if key not in BY_KEY:
            return False
        return any(
            slot is None or slot.key == key for slot in self.slots
        )

    @property
    def weight(self) -> float:
        total = 0.0
        for slot in self.slots:
            if slot is None:
                continue
            item = BY_KEY.get(slot.key)
            if item is None:
                continue
            total += item.weight * slot.qty
        return total

    def to_payload(self) -> dict:
        return {
            "cap": self.cap,
            "bag": [slot.to_payload() if slot else None for slot in self.slots],
            "w": round(self.weight, 2),
        }
