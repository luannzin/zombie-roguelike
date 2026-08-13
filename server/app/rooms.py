"""Room registry: many rooms in one process, addressed by a short code.

A room is created on demand, lives in memory, and is dropped the moment its
last socket leaves. Nothing here is persisted on purpose — a room's entire
content is its live players and the forest they are standing in, and both die
with the connection.
"""

from __future__ import annotations

import random

from .room import Room

# Uppercase letters + digits, minus the glyphs that get misread when a code is
# read aloud or off a screenshot: I/1, L, O/0, U/V. A code is meant to be typed
# by a friend on a phone, so ambiguity costs more than alphabet size.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 7

_rooms: dict[str, Room] = {}


def normalize(code: str) -> str:
    """Fold user input into a canonical code: upper-case, junk stripped.

    Lets `abc-1234 ` land on `ABC1234` instead of a 404, which is what people
    paste when they copy a code out of a chat message.
    """
    return "".join(c for c in code.upper() if c in CODE_ALPHABET)[:CODE_LENGTH]


def new_code() -> str:
    while True:
        code = "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))
        if code not in _rooms:
            return code


def create() -> Room:
    """A fresh room with its own procedurally generated forest."""
    room = Room(code=new_code())
    _rooms[room.code] = room
    return room


def get(code: str) -> Room | None:
    return _rooms.get(normalize(code))


def all_rooms() -> list[Room]:
    return list(_rooms.values())


async def drop(code: str) -> None:
    """Forget a room and stop its tick. Safe to call on an unknown code."""
    room = _rooms.pop(code, None)
    if room is not None:
        await room.stop()
