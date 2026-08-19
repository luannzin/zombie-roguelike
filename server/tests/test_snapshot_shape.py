"""The snapshot's wire contract, which the client mirrors.

Run:  python tests/test_snapshot_shape.py   (from server/)

Three things break the client silently if they regress:
  * a per-recipient field creeping back onto the snapshot — it is serialised
    ONCE for the whole room, so `ack` lives on each player's row as `seq`
  * identity leaking back into the 30 Hz row instead of the roster
  * a settled coin paying for velocity keys it does not need
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ammo, protocol  # noqa: E402
from app.config import INVENTORY_SLOTS  # noqa: E402
from app.coins import Coin  # noqa: E402
from app.entities import Player  # noqa: E402

# What legitimately changes every tick. `held` and `ads` are in here rather
# than on the roster because both are read by the RENDERER on the frame they
# flip — which gun is in the hand and whether the scope is up. `st` is the
# breath: it drains and refills continuously while somebody runs, so it is a
# moving value in the same sense position is. Its companion `wind` is NOT
# listed, and must not be — it is omitted from the row unless it is true
# (`entities.py`), so a resting player's row does not carry it and an
# equality check against this set would fail the moment somebody got tired.
MOVING = {
    "id", "x", "y", "vx", "vy", "ax", "ay", "seq", "lantern", "hp", "alive",
    "ready", "held", "ads", "st",
}
# What rides the 5 Hz roster. `ammo` is here and not above on purpose: the
# client predicts its own trigger and this is the resync, so paying for three
# integers thirty times a second would buy nothing. `skills` / `spins` / `mods`
# are the same call taken further: they change once a day, in a shop, in front
# of a machine.
IDENTITY = {
    "name", "color", "kills", "deaths", "xp", "gold", "level", "xpInLevel",
    "xpToLevel", "inv", "guns", "ammo", "skills", "spins", "mods",
}


def main() -> None:
    player = Player(id="p1", name="Ana", color="#fff", x=1.0, y=2.0)
    player.last_processed_seq = 42

    row = player.snapshot_payload()
    assert set(row) == MOVING, set(row) ^ MOVING
    assert row["seq"] == 42, "the row carries this player's own input ack"

    full = player.to_payload()
    assert set(full) == MOVING | IDENTITY, set(full) ^ (MOVING | IDENTITY)
    assert full["inv"]["cap"] == INVENTORY_SLOTS
    assert full["inv"]["bag"] == [None] * INVENTORY_SLOTS
    # A run opens with no rounds, because it opens with no gun — and the row
    # carries EVERY calibre, including the zeroes, so the HUD can tell "you
    # have none" from "this calibre does not exist" without a lookup.
    #
    # Derived from the catalog rather than written out. The calibre list is
    # generated from the weapons (`weapons.AMMO_TYPES`), so a new gun with a
    # new calibre arrives with a reserve, a counter and a box already wired;
    # a hand-written set here would turn adding one into a test failure and
    # teach the next person that the contract is the literal rather than the
    # rule.
    assert full["ammo"] == {calibre: 0 for calibre in ammo.TYPES}, full["ammo"]
    # ...and with no skills and nothing owed. The first spin is paid by the
    # first level, and level 1 is where everybody starts.
    assert full["skills"] == [] and full["spins"] == 0, full["skills"]
    assert full["mods"]["speed"] == 1.0 and full["mods"]["slots"] == 0, full["mods"]

    packet = protocol.snapshot(1, [row], [], [], [], [], [], [])
    assert "ack" not in packet, "per-recipient field would force a dump per socket"
    assert "roster" not in packet, "roster is attached only when due"
    assert "roster" in protocol.snapshot(1, [row], [], [], [], [], [], [], roster=[full])

    settled = Coin(id="c1", x=1.0, y=2.0).to_payload()
    assert "vx" not in settled and "vy" not in settled, settled
    flying = Coin(id="c2", x=1.0, y=2.0, vx=30.0, vy=-8.0).to_payload()
    assert flying["vx"] == 30.0 and flying["vy"] == -8.0, flying

    assert protocol.dumps({"a": 1, "b": 2}) == '{"a":1,"b":2}', "compact separators"

    print("ok")


if __name__ == "__main__":
    main()
