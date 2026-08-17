"""Zones: where a run currently is, and how that place announces itself.

A run is a sequence of zones. `camp` is the first one and the one you come back
to between expeditions; the forest levels that follow are the same shape with
different rules. Leaving the camp is the walk-out: everyone readies at the
fire, the party files through the black exit, and the room swaps this zone for
`forest` — same socket, a second `welcome`. A zone owns three separate things
and they are deliberately not the same field:

  TITLE / SUBTITLE   the card the client throws up on arrival — "Preparação"
                     over "Dia 1", later "Dia 3" over a rolled clock
                     ("21:44 da noite", "1:44 da manhã"). The clock is fiction
                     the server authors, so a new level needs no client change
                     to be announced.
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

WEATHER is rolled with the clock. A rainy night is the same map in a
different coat — no new generator, no new tiles — so day 2 can feel like
somewhere else. Camp nights are always clear: the fire is the weather.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

KIND_CAMP = "camp"
KIND_FOREST = "forest"
KIND_STORE = "store"

WEATHER_CLEAR = "clear"
WEATHER_RAIN = "rain"
WEATHER_FOG = "fog"

# 20:00 through 03:00 inclusive, in minutes from 20:00.
_NIGHT_SPAN_MINUTES = 7 * 60 + 1

# Most nights are dry. Rain is common enough that a second expedition often
# feels like a different place; fog is the rarer coat.
_WEATHER_TABLE: tuple[tuple[str, int], ...] = (
    (WEATHER_CLEAR, 5),
    (WEATHER_RAIN, 3),
    (WEATHER_FOG, 2),
)


def night_clock() -> str:
    """A time between 20:00 and 03:00. Rolled fresh every expedition.

    Before midnight the line is "da noite"; after, "da manhã". Hours are not
    padded, so 1:44 not 01:44 — that is how the card reads it.
    """
    offset = random.randrange(_NIGHT_SPAN_MINUTES)
    hour = (20 + offset // 60) % 24
    minute = offset % 60
    period = "da noite" if hour >= 20 else "da manhã"
    return f"{hour}:{minute:02d} {period}"


def roll_weather() -> str:
    """A night's coat. Rolled with the clock so one expedition is one scene."""
    names, weights = zip(*_WEATHER_TABLE)
    return random.choices(names, weights=weights, k=1)[0]


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
    #: Night coat. `clear` / `rain` / `fog`. Camp is always clear.
    weather: str = WEATHER_CLEAR

    def to_payload(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "day": self.day,
            "title": self.title,
            "subtitle": self.subtitle,
            "hostile": self.hostile,
            "lantern": self.lantern,
            "weather": self.weather,
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
        weather=WEATHER_CLEAR,
    )


def store(day: int) -> Zone:
    """The merchant's corridor, between the forest and the next camp.

    Safe, and lit by something you can see — which is why the lantern is off
    here for the same reason it is off at the fire. The battery is a resource
    the party carries OUT of a place, and this is the one zone in the loop with
    a roof and a lamp already burning in it.

    The subtitle names the DAY the party just survived, not the one they are
    about to start: this is the end of that night, and the balance being spent
    is the balance that night paid.
    """
    return Zone(
        key=f"store-{day}",
        kind=KIND_STORE,
        day=day,
        title="Mercador",
        subtitle=f"Fim do dia {day}",
        hostile=False,
        lantern=False,
        weather=WEATHER_CLEAR,
    )


def forest(
    day: int,
    clock: str | None = None,
    weather: str | None = None,
) -> Zone:
    """An expedition. Clock and weather are the fiction; omit them and both roll."""
    return Zone(
        key=f"forest-{day}",
        kind=KIND_FOREST,
        day=day,
        title=f"Dia {day}",
        subtitle=clock if clock is not None else night_clock(),
        hostile=True,
        lantern=True,
        weather=weather if weather is not None else roll_weather(),
    )
