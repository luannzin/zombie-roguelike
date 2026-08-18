"""The pocket a player carries into a level.

Loot on the ground is `loot.py`. This is what happens after E: a short row of
slots, a running weight, and a place extraction can later spend from. Slots
are the hard limit — a full bag refuses a new kind. Weight is not: the bar
can go past max, and the only cost is that the body gets slower.

Same item key stacks in the first matching slot. A later upgrade grows
`cap`; nothing here assumes three forever.

ONE EXCEPTION TO THE CATALOG, and it is the reason `Slot` carries numbers at
all. Everything the world scatters is worth exactly what its catalog row says,
so a stack only ever needs a key and a count. A condensed core out of an
overfed pad is worth whatever was overpaid into that pad, so it arrives with
its own value, weight and drawn size. Those travel on the slot, and a slot
carrying them NEVER STACKS — two cores worth 40 and 300 are not two of a thing,
and merging them would have to invent a number for the pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loot import BY_KEY


@dataclass
class Slot:
    key: str
    qty: int
    #: Per-unit overrides. None means "read the catalog row" — which is every
    #: item in the game except a condensed core.
    value: int | None = None
    weight: float | None = None
    scale: float | None = None

    @property
    def unique(self) -> bool:
        """Carries its own numbers, so nothing may stack onto it."""
        return self.value is not None or self.weight is not None

    def unit_value(self) -> int:
        if self.value is not None:
            return self.value
        item = BY_KEY.get(self.key)
        return item.value if item else 0

    def unit_weight(self) -> float:
        if self.weight is not None:
            return self.weight
        item = BY_KEY.get(self.key)
        return item.weight if item else 0.0

    def to_payload(self) -> dict:
        row: dict = {"k": self.key, "n": self.qty}
        if self.value is not None:
            row["v"] = self.value
        if self.weight is not None:
            row["w"] = round(self.weight, 2)
        if self.scale is not None:
            row["s"] = round(self.scale, 3)
        return row


@dataclass
class Inventory:
    cap: int
    slots: list[Slot | None] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.slots) < self.cap:
            self.slots.extend([None] * (self.cap - len(self.slots)))
        elif len(self.slots) > self.cap:
            self.slots = self.slots[: self.cap]

    def add(
        self,
        key: str,
        value: int | None = None,
        weight: float | None = None,
        scale: float | None = None,
    ) -> int | None:
        """Put one of `key` in the bag. Returns the slot index, or None if full.

        An item carrying its own numbers takes a whole cell of its own — see
        the module note. Everything else stacks onto a matching plain slot.
        """
        item = BY_KEY.get(key)
        if item is None or item.pocket != "bag":
            return None
        unique = value is not None or weight is not None
        if not unique:
            for index, slot in enumerate(self.slots):
                if slot is not None and slot.key == key and not slot.unique:
                    slot.qty += 1
                    return index
        for index, slot in enumerate(self.slots):
            if slot is None:
                self.slots[index] = Slot(
                    key=key, qty=1, value=value, weight=weight, scale=scale
                )
                return index
        return None

    def take(self, index: int) -> Slot | None:
        """Pull the whole stack out of `index`. None if that cell is empty."""
        if index < 0 or index >= len(self.slots):
            return None
        slot = self.slots[index]
        if slot is None:
            return None
        self.slots[index] = None
        return slot

    def spend_toward(self, remaining: int) -> int:
        """Consume bag items until `remaining` value is paid. Returns spent.

        Slot order, one unit at a time. The last item may overshoot — a ring
        worth 70 still goes in when 10 is left, because extraction does not
        make change. Guns stay on the belt: they are not what the platform carries.
        """
        if remaining <= 0:
            return 0
        spent = 0
        left = remaining
        for index, slot in enumerate(self.slots):
            if left <= 0:
                break
            if slot is None:
                continue
            item = BY_KEY.get(slot.key)
            if item is None or item.pocket != "bag":
                continue
            unit = slot.unit_value()
            while slot.qty > 0 and left > 0:
                slot.qty -= 1
                spent += unit
                left -= unit
                # A worthless row would never pay the bill and would spin here
                # forever emptying the bag. Take the one unit and move on.
                if unit <= 0:
                    break
            if slot.qty <= 0:
                self.slots[index] = None
        return spent

    def spend_all(self) -> int:
        """Empty every bag slot onto the platform. Returns the value that went in.

        What "alimentar além do limite" runs through: `spend_toward` stops at
        the quota by design, and past the quota there is no number to stop at.
        """
        spent = 0
        for index, slot in enumerate(self.slots):
            if slot is None:
                continue
            item = BY_KEY.get(slot.key)
            if item is None or item.pocket != "bag":
                continue
            spent += slot.unit_value() * slot.qty
            self.slots[index] = None
        return spent

    def bag_value(self) -> int:
        """Catalog value still in the pocket. What a feed press would pay."""
        total = 0
        for slot in self.slots:
            if slot is None:
                continue
            item = BY_KEY.get(slot.key)
            if item is None or item.pocket != "bag":
                continue
            total += slot.unit_value() * slot.qty
        return total

    def can_stow(self, key: str, unique: bool = False) -> bool:
        """Whether E on this drop would find it a home.

        `unique` is the drop carrying its own numbers — a condensed core. It
        cannot merge into a stack, so for it a full bag is a bag with no EMPTY
        cell, not a bag with no matching one.
        """
        item = BY_KEY.get(key)
        if item is None or item.pocket != "bag":
            return False
        if unique:
            return any(slot is None for slot in self.slots)
        return any(
            slot is None or (slot.key == key and not slot.unique)
            for slot in self.slots
        )

    @property
    def weight(self) -> float:
        total = 0.0
        for slot in self.slots:
            if slot is None:
                continue
            if BY_KEY.get(slot.key) is None:
                continue
            total += slot.unit_weight() * slot.qty
        return total

    def to_payload(self) -> dict:
        return {
            "cap": self.cap,
            "bag": [slot.to_payload() if slot else None for slot in self.slots],
            "w": round(self.weight, 2),
        }
