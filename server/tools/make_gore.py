#!/usr/bin/env python3
"""Asset pipeline: wound decals worn by a body that has been shot.

Same rules as the rest of the family: no raw stage, final pixels straight into
assets/processed/, deterministic, shading helpers imported from make_textures
rather than copied.

Output (assets/processed/gore/):
    sheet.png      6 frames, 8x8 — one wound each, centred in its cell
    manifest.json

THIS IS NOT A VFX SHEET AND NOT A SCENERY DECAL, and the difference is where
it ends up.

    vfx/       greyscale TIMELINES, tinted at draw time, drawn ADDITIVELY over
               the darkness, because a beam is a light source
    scenery/   flat stains the server placed, baked into the GROUND canvas
    gore/      this: a mark stamped on a BODY, drawn with the sprite in the
               entity pass and lit by the same night the sprite is

So the colour is baked (blood is blood, not a per-player tint) and the frames
are VARIANTS, not an animation: the client picks one per hit, keeps it at a
fixed spot on the creature, and the zombie carries it around until it dies.

READ ORDER AT 8px. A wound has to survive being drawn quarter-size on a 16px
body under a lantern. What carries is a DARK CORE with one or two bright rim
pixels — the shape is barely legible at this size, so the frames differ by
WEIGHT and DIRECTION (a hole, a spray, a run, a gash) rather than by outline.
Nothing here is outlined: a keyline would lift the mark off the body and make
it read as a sticker.

Usage:
    python tools/make_gore.py
    python tools/make_gore.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

from make_textures import (
    BLOOD,
    DEFAULT_TILE,
    PROCESSED_DIR,
    TRANSPARENT,
    pack,
    pick,
)

#: Wound kinds, in sheet order. The client rolls one per landed shot.
KINDS = ("hole", "spray", "run", "splash", "streak", "gash")

#: The frame is half a tile: at tile 16 that is 8x8 on a 16x16 creature, so a
#: wound covers a quarter of the body's width and several can sit on one
#: zombie without merging into a red blob.
FRAME_DIVISOR = 2

DEFAULT_SEED = 4242


def make_wound(size: int, kind: int, rng: random.Random) -> Image.Image:
    """One wound, centred in a `size` cell.

    Kinds are the four things a bullet does to a body plus the two a claw
    does: punch a hole, throw a spray, open something that runs, and tear.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    centre = (size - 1) / 2.0

    def drop(x: float, y: float, radius: float, shade: float) -> None:
        for iy in range(int(y - radius) - 1, int(y + radius) + 2):
            for ix in range(int(x - radius) - 1, int(x + radius) + 2):
                if not (0 <= ix < size and 0 <= iy < size):
                    continue
                dx, dy = ix - x, iy - y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > radius:
                    continue
                # Wet in the middle, dark at the rim — the same falloff the
                # ground stains use, so a wound and a pool are one material.
                px[ix, iy] = pick(BLOOD, shade * (1.0 - dist / max(radius, 0.6) * 0.5), ix, iy)

    if kind == 0:  # hole — a punched entry, tight and dark
        drop(centre, centre, size * 0.15, 1.0)
        drop(centre - 0.6, centre - 0.6, 0.8, 0.45)
    elif kind == 1:  # spray — a few flecks thrown off a point
        angle = rng.uniform(0, math.tau)
        for index in range(4):
            t = (index + rng.random()) / 4.0
            spread = rng.uniform(-0.7, 0.7) * t
            reach = t * centre * 1.1
            drop(centre + math.cos(angle + spread) * reach,
                 centre + math.sin(angle + spread) * reach,
                 0.8, 0.65 + (1 - t) * 0.35)
    elif kind == 2:  # run — an entry with a bead crawling down out of it
        drop(centre, centre - size * 0.19, size * 0.12, 1.0)
        for step in range(1, 3):
            drop(centre + (0.9 if step == 2 else 0.0), centre + step * 1.6,
                 0.8, 0.8 - step * 0.15)
    elif kind == 3:  # splash — an off-centre mass with a fleck thrown clear
        ox = rng.uniform(-0.9, 0.9)
        oy = rng.uniform(-0.9, 0.9)
        drop(centre + ox, centre + oy, size * 0.15, 1.0)
        a = rng.uniform(0, math.tau)
        r = rng.uniform(size * 0.3, size * 0.4)
        drop(centre + math.cos(a) * r, centre + math.sin(a) * r, 0.8, 0.7)
    elif kind == 4:  # streak — a graze that skidded across
        angle = rng.uniform(0, math.tau)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for step in range(4):
            t = step / 3.0
            u = -1.5 + step
            drop(centre + u * cos_a, centre + u * sin_a, 0.8, 0.6 + (1 - t) * 0.35)
    else:  # gash — a short tear with a bead squeezed out of it
        angle = rng.uniform(0, math.tau)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for step in range(3):
            u = -1.0 + step
            drop(centre + u * cos_a, centre + u * sin_a, 0.8, 1.0 - abs(u) * 0.15)
        v = rng.choice((-1, 1)) * 1.6
        drop(centre - v * sin_a, centre + v * cos_a, 0.8, 0.7)

    return img


def build(args) -> Path:
    tile = args.tile
    size = tile // FRAME_DIVISOR
    out_dir = PROCESSED_DIR / "gore"
    out_dir.mkdir(parents=True, exist_ok=True)

    # One RNG per frame, seeded off the frame index: a shared stream would mean
    # editing one wound silently redraws every wound after it.
    frames = [
        make_wound(size, kind, random.Random(args.seed + kind * 977))
        for kind in range(len(KINDS))
    ]
    pack(frames, size, size).save(out_dir / "sheet.png")

    manifest = {
        "tile": tile,
        "frameWidth": size,
        "frameHeight": size,
        "frames": len(KINDS),
        "kinds": list(KINDS),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(KINDS)} wounds @ {size}x{size}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
