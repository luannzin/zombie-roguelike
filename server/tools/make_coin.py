#!/usr/bin/env python3
"""Asset pipeline: the world DARK GOLD pickup.

The only currency that exists as an object. Group gold is a number the
party extracted; this is the purple coin a corpse or a broken barrel
throws on the floor, and somebody has to walk over it. `make_hud_icons`
strikes the badge that stands for it on the panel.

Same painter as the gold disc, turned on the Y-axis — eight frames, a full
spin, looping because each squash is a cosine of the frame phase. The
struck groove rides in normalised radius so it squashes with the face.

No raw stage. Characters go through magenta grids; a coin is generated,
the way terrain and HUD icons are.

Output (assets/processed/coin/):
    sheet.png      8 frames × 16x16, one row
    manifest.json  character-sheet shape so the client loader stays one path
                   (`walkFrameOrder` is the spin; every facing is row 0)

Usage:
    python tools/make_coin.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from make_textures import (
    DARK_COIN_OUTLINE,
    DARK_COIN_RAMP,
    TRANSPARENT,
    paint_coin,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

FRAMES = 8
FPS = 12
SIZE = 16
#: Depth of the struck ring inside the rim. Enough that the disc still has a
#: shape once the darkness multiply has eaten the outline, and not so much
#: that a 16px coin reads as a washer with a hole in it.
GROOVE = 0.38


def make_spin_frame(index: int) -> Image.Image:
    """One step of a Y-axis tumble. Frame 0 is the HUD badge, face-on."""
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    angle = (index / FRAMES) * math.tau
    scale_x = math.cos(angle)
    back = scale_x < 0
    paint_coin(
        img,
        scale_x=abs(scale_x),
        shine_x=1.1 if back else -1.1,
        dim=0.86 if back else 1.0,
        ramp=DARK_COIN_RAMP,
        edge=DARK_COIN_OUTLINE,
        groove=GROOVE,
    )
    return img


def build() -> Path:
    out_dir = PROCESSED_DIR / "coin"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = [make_spin_frame(i) for i in range(FRAMES)]
    sheet = Image.new("RGBA", (SIZE * FRAMES, SIZE), TRANSPARENT)
    for index, frame in enumerate(frames):
        sheet.paste(frame, (index * SIZE, 0))

    path = out_dir / "sheet.png"
    sheet.save(path)

    manifest = {
        "name": "coin",
        "sheet": "sheet.png",
        "frameWidth": SIZE,
        "frameHeight": SIZE,
        "frames": FRAMES,
        "rows": {"down": 0, "left": 0, "right": 0, "up": 0},
        "idleFrame": 0,
        "walkFrameOrder": list(range(FRAMES)),
        "fps": FPS,
        "anchor": {"x": 0.5, "y": 1.0},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {path} ({sheet.width}x{sheet.height}, {FRAMES} frames @ {FPS} fps)")
    return out_dir


def main() -> None:
    build()


if __name__ == "__main__":
    main()
