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
  AMBIENT            how much light the PLACE has of its own, 0..1. It is zero
                     everywhere a player can be killed, and that is the rule
                     rather than a tuning value: darkness hiding information is
                     what makes exploring mean anything, and a forest with an
                     ambient floor is a forest with no reason to own a lantern.
                     The SHOP is the exception and it is the whole point of the
                     shop — a party walks out of a black wood into somewhere
                     they can see the edges of, and that contrast is the beat
                     the zone exists for. See `store`.

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

#: How much light the merchant's clearing has of its own. See `store`.
#:
#: TUNED AGAINST THE TORCHES, not against a screenshot of an empty map. At this
#: value the whole room is legible from the middle of it — the rim, the far
#: arc, the way out and the other players — and his fire, the torches and the
#: cabinet's marquee are still visibly the brightest things in it.
#:
#: IT CAME BACK DOWN, and the reason is the one bug this zone has ever really
#: had. Every light in the world is drawn ADDITIVELY over this floor —
#: `layers/darkness`'s scene lights and fires, `layers/store`'s flames, and
#: `layers/payout`'s rotor wash — and additive pools SUM with nothing clamping
#: the total. Three skids used to land within five tiles of each other on the
#: apron at 0.85 alpha a wash; two overlapping washes is 1.7 of a full-bright
#: sheet before eight rotors and eight strobes go on top, and on a 0.7 floor
#: the south half of the room saturated to WHITE for the length of the payout.
#: The floor and every light above it are one budget, and this is that budget's
#: share of it. Raising this means taking the same amount back out of
#: `store.RING_TORCHES`, `store.TORCH_LIGHT_TILES`,
#: `config.STORE_MACHINE_LIGHT_TILES` or `layers/payout`'s alphas — never on
#: its own.
STORE_AMBIENT = 0.45

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
    #: Floor under the darkness pass, 0..1. Zero in every hostile place.
    ambient: float = 0.0
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
            "ambient": round(self.ambient, 3),
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
    """The merchant's glade, between one night and the next.

    THE ONE LIT PLACE, and that is the zone's entire job. Everywhere else a
    party goes is a black wood with a torch in it somewhere; here they can see
    the treeline, the far end of the lane and each other. The contrast is the
    reward — a night is only frightening if there is somewhere that is not —
    and it is why `ambient` is a property of the ZONE rather than a pile of
    extra torches: fourteen lamps to fill in the gaps between six would read as
    a lighting rig, and the honest statement is "this place is safe", which is
    a fact about the place.

    It is still a NIGHT and it is still a forest. The floor is well under one:
    the glade is visible, not daylit, and the fire, the torches and the
    machine's marquee still draw the eye by being brighter than it. Push this
    to 1 and the pitch stops being a pool of warmth in a clearing and becomes a
    flat green field with a tent on it.

    The lantern stays OFF for the same reason it is off at the fire: the
    battery is a resource carried OUT of a place, and there is nothing here to
    need it for.

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
        ambient=STORE_AMBIENT,
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
