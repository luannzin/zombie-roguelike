#!/usr/bin/env python3
"""Asset pipeline: the world gold pickup.

The HUD badge (`make_hud_icons.make_coin`) is the face of this disc. This
script is the same painter, turned on the Y-axis — eight frames, a full
spin, looping because each squash is a cosine of the frame phase.

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

from make_textures import TRANSPARENT, paint_coin

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

FRAMES = 8
FPS = 12
SIZE = 16


def make_spin_frame(index: int) -> Image.Image:
    """One step of a Y-axis tumble. Frame 0 is the HUD disc, face-on."""
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    angle = (index / FRAMES) * math.tau
    scale_x = math.cos(angle)
    back = scale_x < 0
    paint_coin(
        img,
        scale_x=abs(scale_x),
        shine_x=1.1 if back else -1.1,
        dim=0.86 if back else 1.0,
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
