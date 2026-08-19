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
    coin.png       one 8x8 frame — GROUP gold: catalog value, quota, price
    darkcoin.png   one 8x8 frame — the player's dark gold, face of the
                   purple pickup `make_coin.py` spins in the world
    arrow.png      one 21x13 frame — gold dart, authored pointing right;
                   still used wherever a thin pointer is wanted
    chevron.png    one 17x17 frame — gold TRIANGLE, authored pointing right;
                   ExitGuide rotates it toward the way out and blinks it

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

from make_textures import (
    DARK_COIN_OUTLINE,
    DARK_COIN_RAMP,
    RGBA,
    Ramp,
    outline,
    paint_coin,
    pick,
    rgb,
)

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

# The pointer's own gold. Deeper at the tail than the battery's electrolyte and
# hotter at the tip, because this sprite is read as ONE shape at a glance and
# the whole job of the ramp is to say which end is the front.
POINT: Ramp = [rgb(c) for c in ("#7a3d0c", "#b96c1c", "#e89a30", "#ffcc63", "#fff0b4")]


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
    """Group gold, 8x8 so a slot value stays a badge.

    Nothing on the floor is made of this: it is what a catalog item is worth,
    what a platform is owed and what the merchant charges.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    return paint_coin(img)


def make_dark_coin(size: int = 8) -> Image.Image:
    """The player's dark gold — the face of the purple disc in the woods.

    Same 8x8 badge as its gold sibling, and deliberately the same silhouette:
    at this size the METAL is the whole message, and two different shapes
    would make the panel look like it holds two unrelated icons rather than
    two currencies. The groove is shallower than the world coin's — an 8px
    disc has half the room for it.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    return paint_coin(
        img, ramp=DARK_COIN_RAMP, edge=DARK_COIN_OUTLINE, groove=0.22
    )


#: Where the head starts, as a fraction of the sprite's length. The rest is
#: shaft. Just over half: a head much shorter than this stops being the thing
#: the eye lands on, and much longer swallows the shaft and the sprite is a
#: triangle again.
ARROW_HEAD_AT = 0.55
#: Half-thickness of the shaft in pixels. 1.5 is three rows — the thinnest a
#: bar can be and still have a lit centreline with a darker edge either side.
ARROW_SHAFT_HALF = 1.5
#: The nock: how much the last few pixels of the tail flare out. Small, because
#: it is punctuation. Without it the back of the arrow is a cut-off bar and the
#: sprite looks like it continues off screen.
ARROW_NOCK = 0.62
ARROW_NOCK_LEN = 3.0


def make_arrow(width: int = 19, height: int = 11) -> Image.Image:
    """Gold pointer for the extraction exit. Points RIGHT, 1px pad for the keyline.

    AN ARROW: a triangular head on a shaft, with a small flare at the nock.
    The sprite this replaced was a caret — a wedge crossed by a bar — and
    rotating a caret around the screen reads as a cross or a plus, not as
    something with a front and a back. What makes this one legible at 26
    screen pixels while spinning is that the head and the shaft are DIFFERENT
    WIDTHS: the eye finds the wide end, and the thin end tells it which way the
    wide end is facing.
    """
    img = Image.new("RGBA", (width + 2, height + 2), TRANSPARENT)
    px = img.load()
    cy = (height - 1) / 2.0
    tip = float(width - 1)
    head_at = tip * ARROW_HEAD_AT

    for y in range(height):
        dy = abs(y - cy)
        for x in range(width):
            # The head, tapering from full height at its base to the tip.
            head = (tip - x) / max(tip - head_at, 1.0) * cy if x >= head_at else 0.0
            # The shaft, running the whole length under it, with the nock flare
            # on its last few pixels.
            shaft = ARROW_SHAFT_HALF
            if x < ARROW_NOCK_LEN:
                shaft += (ARROW_NOCK_LEN - x) * ARROW_NOCK
            if x > head_at:
                shaft = 0.0
            if dy > max(head, shaft):
                continue
            # Hot toward the tip and along the centreline, deep at the nock.
            # A flat fill at this size loses the silhouette into the keyline;
            # the gradient is what keeps the tip the brightest pixel on the HUD
            # after the sprite has been rotated somewhere unhelpful.
            ahead = x / tip
            spine = 1.0 - (dy / max(cy, 0.5))
            value = 0.18 + ahead * 0.60 + spine * 0.28
            px[1 + x, 1 + y] = pick(POINT, value, 1 + x, 1 + y)
    outline(img, OUTLINE)
    return img


#: How far back from the tip the triangle's base sits, as a fraction of the
#: sprite. A shallow triangle is a dart and a deep one is a diamond; two
#: thirds is the shape that still says "this way" at a glance after it has been
#: rotated somewhere unhelpful.
CHEVRON_REACH = 0.66
#: How far the back edge is scooped IN toward the tip. It is what stops the
#: base reading as a flat wall — the notch gives the shape a back the eye can
#: tell from its front even when the sprite is upside down.
CHEVRON_NOTCH = 0.30


def make_chevron(size: int = 15) -> Image.Image:
    """Gold TRIANGLE for the way out. Points RIGHT, 1px pad for the keyline.

    A DIFFERENT SPRITE FROM `arrow.png`, on purpose. The dart is a thin thing
    that reads by its length: it works parked halfway to the screen edge with
    a steady hand on it. This one has to survive being BLINKED — it appears,
    it is gone, it comes back — and a shape that is mostly empty space loses
    that contest, because what the eye catches in a half-second flash is AREA,
    not line. So the chevron is a solid mass with a notched back: bulk to be
    seen, one point to be read.

    The gradient runs the other way from the arrow's. The tip is the hottest
    pixel here as well, but the mass behind it is deliberately deep rather
    than mid — a flat gold triangle at this size is a lozenge, and the falloff
    is the only thing that keeps a direction in it.
    """
    img = Image.new("RGBA", (size + 2, size + 2), TRANSPARENT)
    px = img.load()
    cy = (size - 1) / 2.0
    tip = float(size - 1)
    base = tip * (1.0 - CHEVRON_REACH)

    for y in range(size):
        dy = abs(y - cy)
        for x in range(size):
            if x < base:
                continue
            # The triangle: full height at the base, nothing at the tip.
            reach = (tip - x) / max(tip - base, 1.0)
            if dy > reach * cy:
                continue
            # The notch, cut out of the back edge along the same taper. It is
            # subtracted rather than drawn so the keyline pass finds it.
            notch = base + (tip - base) * CHEVRON_NOTCH
            if x < notch and dy < (notch - x) / max(notch - base, 1.0) * cy * 0.9:
                continue
            ahead = (x - base) / max(tip - base, 1.0)
            spine = 1.0 - (dy / max(cy, 0.5))
            value = 0.16 + ahead * 0.62 + spine * 0.26
            px[1 + x, 1 + y] = pick(POINT, value, 1 + x, 1 + y)
    outline(img, OUTLINE)
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

    dark_coin = make_dark_coin()
    dark_coin_path = out_dir / "darkcoin.png"
    dark_coin.save(dark_coin_path)
    print(f"wrote {dark_coin_path} ({dark_coin.width}x{dark_coin.height})")

    arrow = make_arrow()
    arrow_path = out_dir / "arrow.png"
    arrow.save(arrow_path)
    print(f"wrote {arrow_path} ({arrow.width}x{arrow.height})")

    chevron = make_chevron()
    chevron_path = out_dir / "chevron.png"
    chevron.save(chevron_path)
    print(f"wrote {chevron_path} ({chevron.width}x{chevron.height})")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=10, help="battery frame width in px")
    ap.add_argument("--height", type=int, default=18, help="battery frame height in px")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
