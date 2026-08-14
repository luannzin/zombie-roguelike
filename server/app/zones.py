"""Zones: where a run currently is, and how that place announces itself.

A run is a sequence of zones. `camp` is the first one and the one you come back
to between expeditions; the forest levels that follow are the same shape with
different rules. Leaving the camp is the walk-out: everyone readies at the
fire, the party files through the black exit, and the room swaps this zone for
`forest` — same socket, a second `welcome`. A zone owns three separate things
and they are deliberately not the same field:

  TITLE / SUBTITLE   the card the client throws up on arrival — "Preparação"
                     over "Dia 1", later "Dia 3" over "21:58 da noite". This is
                     pure fiction and the server is its only author, so a new
                     level needs no client change to be announced.
  HOSTILE            whether the enemy director runs and whether guns fire. The
                     camp is safe: no spawns, and no shooting the person
                     standing next to you at the fire.
  LANTERN            whether the lamp may be switched on. In the camp it may
                     not: the bonfire is the light, and the battery is a
                     resource you carry OUT of here, not one you burn standing
                     in it.

The client is told all of it in `welcome.zone` and never infers any of it from
the map. A zone that reads as safe but simulates as hostile is the kind of bug
that only shows up when somebody dies in the lobby.
"""

from __future__ import annotations

from dataclasses import dataclass

KIND_CAMP = "camp"
KIND_FOREST = "forest"


@dataclass(frozen=True)
class Zone:
    #: Stable identity for this arrival. The client replays its intro when this
    #: changes, so two different nights must not share one key.
    key: str
    kind: str
    day: int
    title: str
    subtitle: str
    #: Enemies spawn and weapons fire.
    hostile: bool
    #: The lantern switch works.
    lantern: bool

    def to_payload(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "day": self.day,
            "title": self.title,
            "subtitle": self.subtitle,
            "hostile": self.hostile,
            "lantern": self.lantern,
        }


def camp(day: int) -> Zone:
    """The clearing, between expeditions. Safe, lit by the fire, no lamps."""
    return Zone(
        key=f"camp-{day}",
        kind=KIND_CAMP,
        day=day,
        title="Preparação",
        subtitle=f"Dia {day}",
        hostile=False,
        lantern=False,
    )


def forest(day: int, clock: str) -> Zone:
    """An expedition. `clock` is the fiction, e.g. "21:58 da noite"."""
    return Zone(
        key=f"forest-{day}",
        kind=KIND_FOREST,
        day=day,
        title=f"Dia {day}",
        subtitle=clock,
        hostile=True,
        lantern=True,
    )
