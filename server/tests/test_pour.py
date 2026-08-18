"""Loading a platform is a POUR, and the pour is what this pins down.

Run:  python tests/test_pour.py   (from server/)

Three things about it are load-bearing and all three are invisible from the
outside if they regress:
  * the pocket empties ONE ITEM PER BEAT, not all at once — the whole point of
    moving the spend onto the room's clock is that the HUD and the sprites
    falling out of the backpack are the same event
  * a pour started UNDER the quota stops on the bill; one started at or past it
    takes the whole bag, which is the overfeed
  * a movement key ends it where it stands, and everything already tipped stays
    in the pad
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import protocol, rift  # noqa: E402
from app.config import DT, PLAYER_HALF_HEIGHT  # noqa: E402
from app.entities import POUR_DUMP, POUR_STOW, InputCmd  # noqa: E402
from app.inventory import Slot  # noqa: E402
from app.room import Room  # noqa: E402


def make_room(need: int, stock: list[Slot]) -> tuple[Room, object, object]:
    """A room with one OPEN pad and one player standing at its console."""
    room = Room()
    room.phase = protocol.PHASE_PLAYING
    player = room.add_player(None, "Tester")
    pad = rift.Rift(
        tx=0, ty=0, x=200.0, y=200.0,
        console_x=200.0, console_y=232.0,
        torch_x=180.0, torch_y=232.0,
        deck_x=200.0, deck_y=216.0,
        id="r0", state=rift.OPEN, need=need,
    )
    room.rifts = [pad]
    player.x = pad.console_x
    player.y = pad.console_y - PLAYER_HALF_HEIGHT
    player.inventory.slots = list(stock) + [None] * (
        len(player.inventory.slots) - len(stock)
    )
    return room, player, pad


def run(room: Room, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        room.step_players(DT)


def to_dump(room: Room, player) -> None:
    """Step until the first item is actually falling.

    Stepped to a CONDITION rather than for a fixed count on purpose: the walk
    up to the mark ends early or times out depending on what is in front of the
    pad, and a test that counted ticks would be measuring the map.
    """
    for _ in range(300):
        room.step_players(DT)
        if player.pour is None or player.pour.phase >= POUR_DUMP:
            return
    raise AssertionError("the pour never reached the dump")


def main() -> None:
    # --- one item at a time, and it stops on the bill ------------------------
    # Six bottles at 5 each is 30 in the bag against a bill of 20: four of them
    # go in and two stay, which is the "does not make change" rule paced out.
    unit = Slot(key="broken_toy", qty=6, value=5, weight=0.1)
    room, player, pad = make_room(need=20, stock=[unit])
    room.activate_rift(player.id)
    assert player.pour is not None, "the press has to start a pour"
    assert pad.fed == 0, "nothing may be spent on the press itself"
    assert player.inventory.slots[0].qty == 6, "the bag may not empty on a press"

    # Through the walk and the lift, and exactly one item has left.
    to_dump(room, player)
    assert player.pour.phase == POUR_DUMP, f"expected DUMP, got {player.pour.phase}"
    assert pad.fed == 5, f"one item per beat, got {pad.fed}"
    assert pad.cargo == 1, f"one thing on the deck, got {pad.cargo}"
    assert len(room.pour_events) == 1, "one event per item"

    # Four beats settles a bill of 20 at 5 a piece, and the fifth finds the
    # ceiling and hands over to the stow.
    run(room, rift.POUR_BEAT * 5)
    assert pad.fed == 20, f"a pour under the quota stops on it, got {pad.fed}"
    assert player.inventory.slots[0].qty == 2, "the rest stays in the pocket"
    assert player.pour.phase == POUR_STOW, "a finished pour puts the pack back"
    assert room.pour_events[0]["n"] == 0 and room.pour_events[3]["n"] == 3, (
        "the pile index is the pad's own running count"
    )

    run(room, rift.POUR_STOW + DT)
    assert player.pour is None, "the ceremony has to end"

    # --- past the quota it takes the lot ------------------------------------
    room, player, pad = make_room(
        need=10, stock=[Slot(key="broken_toy", qty=4, value=5, weight=0.1)]
    )
    pad.fed = 10
    room.activate_rift(player.id)
    to_dump(room, player)
    run(room, rift.POUR_BEAT * 6)
    assert pad.fed == 30, f"an overfeed takes the whole bag, got {pad.fed}"
    assert player.inventory.slots[0] is None, "and leaves nothing behind"

    # --- a step cancels it --------------------------------------------------
    room, player, pad = make_room(
        need=100, stock=[Slot(key="broken_toy", qty=8, value=5, weight=0.1)]
    )
    room.activate_rift(player.id)
    to_dump(room, player)
    run(room, rift.POUR_BEAT * 2)
    banked = pad.fed
    assert banked > 0, "something has to have gone in before the cancel"
    player.inputs.append(InputCmd(sequence=99, up=True))
    room.step_players(DT)
    assert player.pour is None, "a movement key ends the pour"
    assert player.last_processed_seq == 99, "and the input still has to be acked"
    run(room, rift.POUR_BEAT * 4)
    assert pad.fed == banked, "nothing else may be tipped after a cancel"
    assert player.inventory.slots[0] is not None, "and the rest stays in the bag"

    print("ok")


if __name__ == "__main__":
    main()
