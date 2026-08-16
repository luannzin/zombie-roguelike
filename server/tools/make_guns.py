#!/usr/bin/env python3
"""Asset pipeline: held gun sprites.

Side-view, pointing RIGHT, one frame per weapon — the knife included, since
a blade in the hand is drawn by exactly the same code as a barrel in the
hand. The client rotates the frame around the grip and mirrors it when the
aim is left, so a single row is every facing.

These are IN HAND, not loot icons. Ground / HUD icons live in
make_loot.py under the same keys, because a drop is a standing prop on
the 16x16 loot atlas. Do not fold the two together: a 16px isometric
pistol rotated around a grip is mush, and a side-view rifle planted on
a tile reads as a signpost.

Every weapon is the same pixel SCALE and the same silhouette HEIGHT
(5 authored rows, barrel on row 1). Length is the class: knife shortest,
pistols short, rifles longer, AWP longest. A mixed scale next to a 16px
body reads as six different toys.

Output (assets/processed/guns/):
    sheet.png      one row, 18x8 frames, catalog order
    manifest.json  frame, grip, muzzle, hold, scale per key

The grip is the pivot (hand). The muzzle is where the tracer starts.
Both are pixel coordinates inside the frame.

`hold` and `scale` are the odd ones out, and both are pose rather than art.
`hold` is WORLD pixels along the aim from the body centre out to that pivot
— how far in front of the character the weapon is carried. A gun is held out
at arm's length, which is why it defaults to `HOLD_OUT`. A knife is not: it
is held IN, at the body, and a blade drawn at a pistol's extension reads as
a tiny sword floating beside the sprite rather than as something in
somebody's hand. `scale` is a multiplier on the drawn frame, 1.0 for
everything the sheet's one-pixel-scale rule covers.

Usage:
    python tools/make_guns.py
    python tools/make_guns.py --tile 16
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    Ramp,
    TRANSPARENT,
    outline,
    pack,
    pick,
    rgb,
)

FRAME_W = 18
FRAME_H = 8

#: World px along aim from the body centre to the grip, for something held
#: out at arm's length. Every gun uses it; see `hold` in the module docstring.
HOLD_OUT = 3.0
#: Held IN: the grip sits ON the body's centre line and the blade is the only
#: part in front of it. That is the difference between a knife and a sword at
#: this size — what reaches forward is the blade's length, never the arm's.
HOLD_IN = 0.0

# Materials against the night. Bright enough to read at 4x, dark enough
# not to glow like a HUD icon on a body.
STEEL: Ramp = [rgb(c) for c in ("#1a1c20", "#2a2e34", "#3c424a", "#555c66", "#7a828c", "#b0b6be")]
SLIDE: Ramp = [rgb(c) for c in ("#121418", "#1c1f24", "#2a2e34", "#3a4048", "#5a616c")]
TAN: Ramp = [rgb(c) for c in ("#2a2218", "#3d3224", "#5a4830", "#7a6240", "#a08458", "#c4a870")]
GRIP: Ramp = [rgb(c) for c in ("#141416", "#1c1c20", "#2a2a30", "#3a3a42")]
CHROME: Ramp = [rgb(c) for c in ("#2a2c30", "#4a5058", "#6a727c", "#8a949e", "#c0c8d0", "#e8eef4")]
WOOD: Ramp = [rgb(c) for c in ("#1c1410", "#2a1c14", "#3d2818", "#5a3820", "#7a4c28", "#a06838")]
OLIVE: Ramp = [rgb(c) for c in ("#1a1e14", "#262c1c", "#343c26", "#485230", "#5e6a3c", "#7a8650")]
POLY: Ramp = [rgb(c) for c in ("#16181c", "#22262c", "#32383e", "#454c54", "#5c646e")]
SCOPE: Ramp = [rgb(c) for c in ("#121410", "#1c2018", "#2a3224", "#3c4630")]
OUTLINE = rgb("#07080a")

Art = list[str]
Palette = dict[str, Ramp]


def _pad(art: Art) -> Art:
    width = max(len(row) for row in art)
    return [row.ljust(width, ".") for row in art]


def _blit(art: Art, ramps: Palette, width: int, height: int) -> Image.Image:
    """Side-view: left is the grip, right is the muzzle. Vertically centred."""
    art = _pad(art)
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    art_w = len(art[0])
    art_h = len(art)
    ox = 1
    oy = (height - art_h) // 2
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            ramp = ramps.get(ch)
            if ramp is None:
                continue
            # Lit from above-left, the way a lantern would catch a barrel.
            shade = 0.78 - (y / max(art_h - 1, 1)) * 0.32 + (x / max(art_w - 1, 1)) * 0.08
            px[ox + x, oy + y] = pick(ramp, shade, ox + x, oy + y)
    outline(img, OUTLINE)
    return img


def _centroid(art: Art, ch: str, ox: int, oy: int) -> tuple[int, int]:
    """Mean of every `ch` pixel — the grip pivot, not a corner of the band."""
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(art):
        for x, cell in enumerate(row):
            if cell == ch:
                xs.append(ox + x)
                ys.append(oy + y)
    if not xs:
        return (ox, oy + len(art) // 2)
    return (round(sum(xs) / len(xs)), round(sum(ys) / len(ys)))


def _rightmost(art: Art, ch: str, ox: int, oy: int) -> tuple[int, int]:
    """Muzzle face: furthest right, then lowest."""
    found = (ox, oy + len(art) // 2)
    for y, row in enumerate(art):
        for x, cell in enumerate(row):
            if cell == ch:
                found = (ox + x, oy + y)
    return found


# Catalog order matches server/app/weapons.py and the loot keys.
# Five authored rows, barrel on row 1, so every gun sits on the same line.
# Marker letters used only for grip/muzzle lookup are still painted:
#   g = grip pivot band, m = muzzle face
# Pistol grips are a SOLID block — no magwell hole, no selector dial, no
# trigger-guard loop. At this size a 1px hole is filled by the outline and
# reads as a circle on the heel. The guard is a squared step under the slide.
GUNS: list[tuple[str, Palette, Art, str, str]] = [
    (
        "glock18",
        {"s": SLIDE, "f": POLY, "g": GRIP, "m": SLIDE},
        [
            "....sssss",
            "....ssssm",
            "...ffsss.",
            "...gf....",
            "...gg....",
        ],
        "g",
        "m",
    ),
    (
        "deagle",
        {"s": CHROME, "p": GRIP, "g": GRIP, "m": CHROME},
        [
            ".....ssssss",
            ".....sssssm",
            "....ppsss..",
            "....gp.....",
            "....gg.....",
        ],
        "g",
        "m",
    ),
    (
        "famas",
        {"b": POLY, "h": STEEL, "n": SLIDE, "g": GRIP, "m": STEEL},
        [
            "...hhhhhh...",
            "bbbbbbbbbnnm",
            "bg..b...nn..",
            ".bbbbb..nn..",
            "......nn....",
        ],
        "g",
        "m",
    ),
    (
        "ak47",
        {"w": WOOD, "k": SLIDE, "n": STEEL, "g": WOOD, "m": STEEL},
        [
            "...........n",
            "wwwwwkkkkkkm",
            "wg..wnnkkkk.",
            ".wwww.nn....",
            "......nn....",
        ],
        "g",
        "m",
    ),
    (
        "awp",
        {"o": OLIVE, "s": SLIDE, "k": STEEL, "c": SCOPE, "g": OLIVE, "m": STEEL},
        [
            ".............cc",
            "oooooooossssssm",
            "og....oskkkkkks",
            ".oooooo.s......",
            "........s......",
        ],
        "g",
        "m",
    ),
    # The knife, and it is the one frame on this sheet that is not a gun.
    # It is drawn STRAIGHT — handle, crossguard and blade on one line — and
    # that is the whole silhouette decision. Every gun here hangs a grip
    # below its barrel, so a blade with any drop at the back reads as one
    # more pistol at 16px no matter what the blade is doing. The guard is
    # the only thing that leaves the line, one pixel above and one below,
    # which is what says "this end is held" without a grip.
    #
    # Same edge on row 1, so swapping to it does not jump the hand, and
    # deliberately the SHORTEST thing on the sheet: length is what this
    # sheet uses to say range, and the weapon you have to walk up to
    # somebody with has to read as short.
    (
        "knife",
        {"b": CHROME, "c": STEEL, "g": GRIP, "m": CHROME},
        [
            "...c......",
            ".ggcbbbbb.",
            ".ggcbbbbbm",
            "...c......",
            "..........",
        ],
        "g",
        "m",
    ),
]


#: How far in front of the body each weapon is carried, and how big it is
#: drawn. Written as the exceptions rather than as extra columns on every
#: row: five of the six entries are guns held the one way guns are held at
#: the one scale this sheet is authored at, and repeating that five times
#: would bury the one row where either is a decision.
HOLD: dict[str, float] = {"knife": HOLD_IN}
#: Draw scale against the authored frame. The sheet's rule is that every
#: weapon shares one pixel scale, and the knife is the deliberate exception:
#: it is the one thing here that is not a firearm, and reading smaller than
#: everything on the belt is how a 16px sprite says "sidearm".
SCALE: dict[str, float] = {"knife": 0.8}


def build(args) -> Path:
    width, height = FRAME_W, FRAME_H
    out_dir = PROCESSED_DIR / "guns"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames: list[Image.Image] = []
    items: dict[str, dict] = {}
    for index, (key, pal, art, grip_ch, muzzle_ch) in enumerate(GUNS):
        frame = _blit(art, pal, width, height)
        frames.append(frame)
        art = _pad(art)
        art_h = len(art)
        ox = 1
        oy = (height - art_h) // 2
        grip = _centroid(art, grip_ch, ox, oy)
        muzzle = _rightmost(art, muzzle_ch, ox, oy)
        items[key] = {
            "frame": index,
            "gripX": grip[0],
            "gripY": grip[1],
            "muzzleX": muzzle[0],
            "muzzleY": muzzle[1],
            "hold": HOLD.get(key, HOLD_OUT),
            "scale": SCALE.get(key, 1.0),
        }

    pack(frames, width, height).save(out_dir / "sheet.png")
    manifest = {
        "tile": args.tile,
        "frameWidth": width,
        "frameHeight": height,
        "frames": len(GUNS),
        "items": items,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(GUNS)} guns @ {width}x{height}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tile",
        type=int,
        default=DEFAULT_TILE,
        help="must match TILE_SIZE in server/app/config.py",
    )
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
