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

from app import protocol  # noqa: E402
from app.coins import Coin  # noqa: E402
from app.entities import Player  # noqa: E402

MOVING = {"id", "x", "y", "vx", "vy", "ax", "ay", "seq", "lantern", "hp", "alive", "ready"}
IDENTITY = {"name", "color", "kills", "deaths", "xp", "gold", "level", "xpInLevel", "xpToLevel", "loot"}


def main() -> None:
    player = Player(id="p1", name="Ana", color="#fff", x=1.0, y=2.0)
    player.last_processed_seq = 42

    row = player.snapshot_payload()
    assert set(row) == MOVING, set(row) ^ MOVING
    assert row["seq"] == 42, "the row carries this player's own input ack"

    full = player.to_payload()
    assert set(full) == MOVING | IDENTITY, set(full) ^ (MOVING | IDENTITY)

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
