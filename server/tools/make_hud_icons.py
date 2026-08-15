#!/usr/bin/env python3
"""Asset pipeline: procedural HUD icons.

Third sibling of the asset scripts, and the same split as the others:

    make_placeholder_sheet.py   raw art  -> assets/raw/
    process_sprites.py          raw art  -> assets/processed/ (keyed, cropped)
    make_textures.py            nothing  -> assets/processed/terrain/
    make_hud_icons.py           nothing  -> assets/processed/hud/     <- this one

Like terrain, HUD icons are *generated*: there is no raw stage, the script
writes final-resolution pixels, and the same --seed-free code always produces
byte-identical PNGs. The drawing helpers (ramp dithering, the 1px outline pass)
are imported from make_textures rather than copied, so every generated asset in
the game shares one shading vocabulary.

Output (assets/processed/hud/):
    battery.png    one 10x18 frame — a single cell of the lantern's battery
    backpack.png   one 16x16 frame — the pocket on the HUD, seen from the back
    coin.png       one 8x8 frame — slot gold badge, not the world pickup

Why one frame and not a strip of charge levels: the HUD draws this sprite FOUR
times side by side and drains each one from the top down by clipping a
grayscale copy over a colour copy (see components/hud/BatteryGauge.tsx). The
charge level is therefore a continuous CSS clip, not a frame index — which is
what lets a cell read as 60% full instead of snapping between steps.

That trick is the one constraint on the art: the sprite has to survive being
cut in half at any height and desaturated, so the cell window is a plain
vertical gradient with no lettering or gloss that would look severed.

Usage:
    python tools/make_hud_icons.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from make_textures import RGBA, Ramp, outline, pick, rgb

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

TRANSPARENT: RGBA = (0, 0, 0, 0)

# --- palette ----------------------------------------------------------------
# The HUD sits on `--panel` (#0a0a10), so the outline is a shade ABOVE the panel
# rather than black: a black keyline on a black panel does not draw a silhouette,
# it deletes one. Everything else is the amber of `--night-lantern` — the battery
# is the lantern's charge, and it should read as the same light.

OUTLINE = rgb("#101018")
SHELL: Ramp = [rgb(c) for c in ("#22222e", "#33334a", "#4a4a66", "#6c6c8c")]
CELL: Ramp = [rgb(c) for c in ("#8a4a12", "#c47a28", "#f2a541", "#ffd678", "#fff1c2")]
BOLT = rgb("#5c3410")

# The HUD pack. Leather a shade above the panel so the silhouette holds, with
# a flap and two straps — the same object the character wears, read as an icon.
LEATHER: Ramp = [rgb(c) for c in ("#3a2a1c", "#5a4030", "#8a6244", "#c49a68")]
STRAP = rgb("#2a2218")
BUCKLE = rgb("#d8c078")

# Slot gold. Same ramp as the world coin, shrunk to an 8px badge so it
# sits next to an 11px value without covering the item.
COIN: Ramp = [rgb(c) for c in ("#a05a1c", "#f2a541", "#ffd678", "#fff1c2")]
COIN_OUTLINE = rgb("#482a12")

# The charge glyph, punched into the cell window as a silhouette. Authored by
# hand because a 4x6 bolt is below the size where any procedural stroke reads.
BOLT_ART = (
    "..#.",
    ".##.",
    "###.",
    ".###",
    ".##.",
    ".#..",
)


def make_battery(width: int, height: int) -> Image.Image:
    """One battery cell, upright, lit from the left.

    Laid out inset by 1px on every side so `outline()` has somewhere to put the
    keyline — a silhouette flush with the canvas edge would come out unbordered
    on that side.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    nub_w = max(2, round(width * 0.4))
    nub_h = max(1, round(height * 0.11))
    nub_x = (width - nub_w) // 2
    # Body starts below the nub, inset 1px for the keyline.
    body_top = nub_h + 1
    body_bottom = height - 2
    body_left, body_right = 1, width - 2

    for y in range(1, 1 + nub_h):
        for x in range(nub_x, nub_x + nub_w):
            px[x, y] = SHELL[3] if x == nub_x else SHELL[2]

    # Shell: a vertical metal ramp, brightest down the left edge so the cell
    # reads as a cylinder rather than a rectangle.
    for y in range(body_top, body_bottom + 1):
        for x in range(body_left, body_right + 1):
            across = (x - body_left) / max(1, body_right - body_left)
            px[x, y] = pick(SHELL, 0.85 - across * 0.62, x, y)

    # Window: the electrolyte itself. Two pixels of shell above and below it so
    # the casing has a cap and a base to sit on.
    win_left, win_right = body_left + 1, body_right - 1
    win_top, win_bottom = body_top + 2, body_bottom - 2
    win_h = win_bottom - win_top
    for y in range(win_top, win_bottom + 1):
        for x in range(win_left, win_right + 1):
            # Hot at the top, deepening toward the base, plus a highlight down
            # the left. The gradient is gentle on purpose: the HUD slices this
            # sprite at an arbitrary height, and a busy interior would show the
            # cut.
            down = (y - win_top) / max(1, win_h)
            across = (x - win_left) / max(1, win_right - win_left)
            px[x, y] = pick(CELL, 0.92 - down * 0.45 - across * 0.22, x, y)

    stamp(px, BOLT_ART, win_left, win_right, win_top, win_bottom, BOLT)
    outline(img, OUTLINE)
    return img


def make_backpack(size: int = 16) -> Image.Image:
    """The pocket, from the back. 16x16 so it sits on the same HUD grid."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()

    # Body: a rounded satchel, inset 1px for the keyline.
    for y in range(4, 14):
        for x in range(3, 13):
            if (x in (3, 12) and y in (4, 13)) or (x in (3, 12) and y == 4):
                continue
            across = (x - 3) / 9
            down = (y - 4) / 9
            px[x, y] = pick(LEATHER, 0.78 - across * 0.28 - down * 0.18, x, y)

    # Flap: a darker lid across the top third.
    for y in range(4, 8):
        for x in range(3, 13):
            if x in (3, 12) and y == 4:
                continue
            across = (x - 3) / 9
            px[x, y] = pick(LEATHER, 0.55 - across * 0.2, x, y)

    # Two vertical straps and a buckle on the flap.
    for y in range(5, 13):
        px[5, y] = STRAP
        px[10, y] = STRAP
    px[7, 6] = BUCKLE
    px[8, 6] = BUCKLE

    outline(img, OUTLINE)
    return img


def make_coin(size: int = 8) -> Image.Image:
    """A face-on gold disc. 8x8 so a slot value stays a badge, not a cover."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    cx = cy = (size - 1) / 2
    radius = size / 2 - 1.15
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > radius:
                continue
            falloff = 1 - dist / radius
            shine = max(0.0, 1 - ((dx + 1.1) ** 2 + (dy + 1.1) ** 2) ** 0.5 / radius)
            px[x, y] = pick(COIN, 0.32 + falloff * 0.28 + shine * 0.42, x, y)
    outline(img, COIN_OUTLINE)
    return img


def stamp(
    px,
    art: tuple[str, ...],
    left: int,
    right: int,
    top: int,
    bottom: int,
    colour: RGBA,
) -> None:
    """Centre an ASCII glyph in a box, skipping it if it will not fit."""
    art_w = max(len(row) for row in art)
    art_h = len(art)
    if art_w > right - left + 1 or art_h > bottom - top + 1:
        return
    ox = left + (right - left + 1 - art_w) // 2
    oy = top + (bottom - top + 1 - art_h) // 2
    for row, line in enumerate(art):
        for col, char in enumerate(line):
            if char != ".":
                px[ox + col, oy + row] = colour


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "hud"
    out_dir.mkdir(parents=True, exist_ok=True)

    battery = make_battery(args.width, args.height)
    path = out_dir / "battery.png"
    battery.save(path)
    print(f"wrote {path} ({battery.width}x{battery.height})")

    pack = make_backpack()
    pack_path = out_dir / "backpack.png"
    pack.save(pack_path)
    print(f"wrote {pack_path} ({pack.width}x{pack.height})")

    coin = make_coin()
    coin_path = out_dir / "coin.png"
    coin.save(coin_path)
    print(f"wrote {coin_path} ({coin.width}x{coin.height})")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=10, help="battery frame width in px")
    ap.add_argument("--height", type=int, default=18, help="battery frame height in px")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
