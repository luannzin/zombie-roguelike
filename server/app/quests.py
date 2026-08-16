"""Run objectives. Authoritative, room-wide, one list.

The HUD is a MIRROR of this list: progress as numbers, a done flag, an optional
risk mark, and dropping a row is how a task leaves the screen. The client never
invents a quest and never ticks one off on its own.

The first objective of a forest is finding the extraction point — the anomaly
`rift.py` placed. It appears after the entrance seals, which is the moment the
party knows they cannot leave the way they came.
"""

from __future__ import annotations

from dataclasses import dataclass

EXTRACT = "extract"
EXTRACT_LABEL = "Encontre o ponto de extração"


@dataclass
class Quest:
    id: str
    label: str
    have: int = 0
    need: int = 1
    done: bool = False
    #: Dangerous work. The HUD paints the count in the danger tone.
    risk: bool = False

    def payload(self) -> dict:
        row = {
            "id": self.id,
            "label": self.label,
            "have": self.have,
            "need": self.need,
        }
        if self.done:
            row["done"] = True
        if self.risk:
            row["risk"] = True
        return row


def extract() -> Quest:
    return Quest(id=EXTRACT, label=EXTRACT_LABEL, have=0, need=1)


def from_payloads(rows: list[dict] | None) -> list[Quest]:
    out: list[Quest] = []
    for row in rows or []:
        out.append(
            Quest(
                id=str(row["id"]),
                label=str(row["label"]),
                have=int(row.get("have", 0)),
                need=int(row.get("need", 1)),
                done=bool(row.get("done", False)),
                risk=bool(row.get("risk", False)),
            )
        )
    return out
