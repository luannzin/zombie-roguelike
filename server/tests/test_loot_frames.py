"""Every catalog row against the atlas the generator actually painted.

Run:  python tests/test_loot_frames.py   (from server/)

THIS IS THE OTHER CONTRACT WITH NO RUNTIME SYMPTOM. A wrong frame is not an
error anywhere — the client draws whatever sprite that index lands on, so a
condensed core came out as a box of rifle rounds and the knife came out as a
box of pistol rounds, and the game kept running. The catalog in `loot.py` and
the paint list in `tools/make_loot.py` are two hand-maintained lists over the
same set of items; `loot.py` now takes the frame from the manifest, so the
only thing left to check is that the manifest HAS one for every key.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import loot  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[2] / "assets/processed/loot/manifest.json"


def main() -> None:
    atlas = json.loads(MANIFEST.read_text())
    frames = atlas["items"]

    missing = sorted(item.key for item in loot.ITEMS if item.key not in frames)
    assert not missing, (
        f"no atlas art for {missing}. Add an entry to tools/make_loot.py's "
        "ITEMS and re-run it — a key with no frame draws nothing."
    )

    payload = loot.catalog_payload()
    wrong = {
        key: (row["frame"], frames[key]["frame"])
        for key, row in payload.items()
        if row["frame"] != frames[key]["frame"]
    }
    assert not wrong, f"catalog frame != atlas frame for {wrong}"

    # The reverse direction is NOT an error: the sheet may carry art for a key
    # the catalog dropped. It costs one dead frame and breaks nothing, and
    # failing on it would make deleting an item a two-commit job.
    print("ok")


if __name__ == "__main__":
    main()
