"""Run objectives. Authoritative, room-wide, one list.

The HUD is a MIRROR of this list: progress as numbers, a done flag, an optional
risk mark, and dropping a row is how a task leaves the screen. The client never
invents a quest and never ticks one off on its own.

The first objective of a forest is finding the extraction point — the anomaly
`rift.py` placed. It appears after the entrance seals, which is the moment the
party knows they cannot leave the way they came. Pressing a console unlocks
feeding (`gold` on the row, so the HUD shows the coin); paying the quota
collapses the pad and opens the way out.
"""

from __future__ import annotations

from dataclasses import dataclass

EXTRACT = "extract"
EXTRACT_LABEL = "Encontre o ponto de extração"
FEED = "feed"
FEED_LABEL = "Alimente a fenda"
EXIT = "exit"
EXIT_LABEL = "Encontre a saída"


@dataclass
class Quest:
    id: str
    label: str
    have: int = 0
    need: int = 1
    done: bool = False
    #: Dangerous work. The HUD paints the count in the danger tone.
    risk: bool = False
    #: Progress is catalog gold. The HUD draws the coin badge next to it.
    gold: bool = False

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
        if self.gold:
            row["gold"] = True
        return row


def extract(need: int = 1) -> Quest:
    return Quest(id=EXTRACT, label=EXTRACT_LABEL, have=0, need=max(1, need))


def feed(need: int) -> Quest:
    return Quest(id=FEED, label=FEED_LABEL, have=0, need=max(1, need), gold=True)


def exit_quest() -> Quest:
    return Quest(id=EXIT, label=EXIT_LABEL, have=0, need=1, risk=True)


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
                gold=bool(row.get("gold", False)),
            )
        )
    return out
