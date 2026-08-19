#!/usr/bin/env python3
"""Asset pipeline: the world DARK GOLD pickup — the ANOMALY SHARD.

The only currency that exists as an object. Group gold is a number the party
extracted; this is the thing a corpse or a broken barrel throws on the floor,
and somebody has to walk over it. `make_hud_icons` strikes the badge that
stands for it on the panel, off this same painter.

IT USED TO BE A STRUCK PURPLE DISC and it is now a sphere of the anomaly's own
material, because the disc was answering the wrong question. A coin is money
somebody minted — it says there is a treasury, a face, an economy — and the
only thing in this world that pays out is the rift. Dark gold is what the
anomaly leaves behind, so it is made of what the anomaly is made of: the same
six-ramp prism (`make_rift.PRISM`), the same iridescence, drawn as light
coming THROUGH a shell rather than as a lit surface. A player who has stood at
a pad knows what this is the first time they see one on the floor, which is a
thing no amount of purple could have bought.

It is also RARE now (`config.COIN_DROP_CHANCE`): a shard off the anomaly that
fell out of every second corpse would be a coin with a different hat on.

Same eight frames and the same sheet shape as the disc it replaced — the
lattice turns instead of the face flipping, so the manifest, the loader and
the world sprite are untouched.

No raw stage. Characters go through magenta grids; a shard is generated, the
way terrain and HUD icons are.

Output (assets/processed/coin/):
    sheet.png      8 frames × 16x16, one row
    manifest.json  character-sheet shape so the client loader stays one path
                   (`walkFrameOrder` is the turn; every facing is row 0)

Usage:
    python tools/make_coin.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from make_textures import TRANSPARENT
from make_rift import CORE, CYAN, MINT, Prism, ROSE, VIOLET

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

FRAMES = 8
FPS = 12
SIZE = 16

#: Fraction of the cell the ball spans. Smaller than the disc's, because this
#: one glows: the light it throws past its own edge is part of the silhouette,
#: and a shard sized like the coin filled the frame corner to corner.
FILL = 0.74

#: The openings in the shell, walked round the equator. FOUR, not the prism's
#: six: at eleven pixels across, two cells crossing is already the whole
#: picture and more only fills the ball back in. They are consecutive in the
#: spectrum for the reason `make_rift.PRISM` documents — overlapping shapes
#: resolve to the weighted MEAN hue, so neighbours here have to be neighbours
#: to the eye. AMBER is left out: it is the overfed rift's colour and a shard
#: is what a rift gives BACK.
CELLS = (ROSE, VIOLET, CYAN, MINT)


def make_spin_frame(
    index: int, size: int = SIZE, frames: int = FRAMES, light: float = 1.0
) -> Image.Image:
    """One step of the lattice turning. Frame 0 is the HUD badge.

    LOOPS BY CONSTRUCTION: every term is a sine or a cosine of the frame
    phase, so the last frame meets the first with nothing to hide — the same
    rule the rift's own sheets are built on, and the reason the disc this
    replaced tumbled on a cosine rather than on a table of squash values.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    prism = Prism(size, size)
    phase = (index / frames) * math.tau
    cx = cy = (size - 1) / 2.0

    # One breath per loop rather than two: this is a fragment, not the open
    # anomaly, and it should read as something resting on the floor.
    breathe = 1.0 + 0.05 * math.sin(phase)
    rx = size * FILL * 0.5 * breathe
    ry = rx * 0.96

    # THE BODY FIRST, and it is why this reads as a ball rather than as a ring
    # of specks. The rift can afford to be drawn as absence — it is four tiles
    # across and the gaps are legible. Eleven pixels of the same treatment is
    # confetti: the shell has to be filled, faintly, before anything is cut
    # into it.
    prism.ellipse(cx, cy, rx, ry, 0.42, VIOLET)
    # The core, seen through the widest opening, and sat low like the rift's.
    prism.ellipse(cx, cy + ry * 0.14, rx * 0.32, ry * 0.26, 0.46, CORE)
    # A rim so the silhouette has an edge without being outlined — VIOLET, the
    # one part of the shell that is not pastel.
    prism.ellipse(cx, cy, rx, ry, 0.30, VIOLET, hollow=0.55)

    for i, hue in enumerate(CELLS):
        angle = phase + i * math.tau / len(CELLS)
        # +1 on the near face, -1 on the far one. A cell on the far side is
        # light arriving through the whole shell, so it is dim and it is what
        # keeps the ball from reading as a flat painted circle.
        depth = math.cos(angle)
        near = max(0.0, depth)
        prism.ellipse(
            cx + math.sin(angle) * rx * 0.50,
            cy - ry * 0.08,
            rx * 0.30 * abs(depth) + 0.85,
            ry * 0.66,
            0.30 + 0.52 * near,
            hue,
        )

    # Brighter than the rift sheets: those are drawn at four tiles and can
    # spend pixels on falloff, this has eleven and has to survive the darkness
    # multiply lying on a forest floor. `light` is one knob over both the ramp
    # step and the alpha, turned up for the 8px badge — that one is smaller
    # still and sits on a panel the night never reaches, so the world sprite's
    # exposure came out muddy next to the gold coin beside it.
    prism.paint(img, gain=1.5 * light, tone=0.95 * light)
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
