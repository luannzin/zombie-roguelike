"""Run objectives. Authoritative, room-wide, one list.

The HUD is a MIRROR of this list: progress as numbers, a done flag, an optional
risk mark, and dropping a row is how a task leaves the screen. The client never
invents a quest and never ticks one off on its own.

The first objective of a forest is finding the extraction point — the anomaly
`rift.py` placed. It appears after the entrance seals, which is the moment the
party knows they cannot leave the way they came. Pressing a console unlocks
feeding (`gold` on the row, so the HUD shows the coin); paying that pad's quota
arms its console, and shutting it by hand collapses the pad. When the last one
is shut the way out opens.

THE FEED ROW IS PER-PAD AND IT MAY OVERSHOOT. Only one anomaly is ever awake,
so there is only ever one feed row, carrying that pad's quota; it is dropped
when the pad is shut and a fresh one goes up at the next console. `have` is
deliberately allowed past `need` while it stays done — the overshoot is what
the party is choosing to build, and clamping it would hide the number that says
how big the core coming out the other side will be.
"""

from __future__ import annotations

from dataclasses import dataclass

EXTRACT = "extract"
EXTRACT_LABEL = "Encontre o ponto de extração"
FEED = "feed"
FEED_LABEL = "Alimente a fenda"
EXIT = "exit"
EXIT_LABEL = "Encontre a saída"
#: The store's row. Same id as the forest's, because it is the same mechanic —
#: a living body crossing the VOID at the end of the map — and `Room` ticks it
#: through one path. Only the wording differs, and it differs completely: the
#: forest's exit is something you have to FIND in the dark with the pack
#: hunting, and this one is a lit doorway forty tiles away that has been open
#: since you walked in. Calling both "encontre a saída" would make the word
#: mean nothing on the night it matters.
STORE_EXIT_LABEL = "Siga para o acampamento"


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


def store_exit_quest() -> Quest:
    """Leave the shop. Not `risk` — there is nothing in here to be afraid of."""
    return Quest(id=EXIT, label=STORE_EXIT_LABEL, have=0, need=1)


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
