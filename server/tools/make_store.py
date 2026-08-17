#!/usr/bin/env python3
"""Asset pipeline: the STORE — the lit corridor the party spends the night's take in.

Output (assets/processed/store/):
    ground_boards.png  64x64        GROUND — one seamless plank floor, 4x4 tiles
    wall.png     6 frames, 16x36    PROP   — the corridor's far side, tiled
    table.png    4 frames, 32x20    PROP   — the stalls a weapon lies on
    lamp.png     2 frames, 12x30    PROP   — what lights the place (unlit body)
    rug.png      2 frames, 48x32    DECAL  — the mat he stands on
    lampfire.png 10 frames, 16x26   VFX    — loop, the flame in the lamp
    glow.png     8 frames,  32x16   VFX    — loop, under a weapon you are near
    manifest.json

THE STORE IS THE FIRST INTERIOR IN THE GAME, AND THAT IS THE WHOLE BRIEF.
Everything else the pipeline makes is outdoors and unlit: a forest at night
where the lantern is the only reason anything is visible, drawn dark on purpose
because the client's darkness pass multiplies over it. This corridor is the
opposite — it is somewhere with a roof and a lamp on, the one zone in the loop
where the party is safe and standing still, and the art has to say so before
the title card does. So it runs WARM and a step lighter than the forest, and
the light in it comes from a source you can see.

WHAT IS HERE AND WHAT IS NOT.
The corridor is a straight run left to right, the way in seals behind the
party, the merchant stands at the middle of it and his tables are in front of
him. That is a handful of pieces repeated, so this file draws the pieces and
nothing else: a floor, a wall that tiles, a table, a lamp, a mat. It does NOT
draw the merchant (`make_merchant.py`), the guns on the tables
(`make_guns.py`), the coin on the price tag (`make_hud_icons.py`) or the void
the entrance collapses into — that is the same black corridor the camp exit
uses and it is already drawn.

ONE FLOOR, NOT FOUR. The forest ships four soils and dissolves between them
because a hashed material field is the only thing that hides a 4x4 repeat over
a whole map. A built floor is one material by definition, and the corridor is
a few tiles of it with tables standing on most of them, so a second atlas would
buy nothing. The repeat is broken the way a real floor breaks it: the planks
run ALONG the corridor with their butt joints staggered every other course, so
the eye follows the boards out towards the exit instead of finding the tile
grid.

A WALL TILES, SO IT HAS NO SIDE KEYLINE. Every other standing prop in the game
is one object and carries an outline all the way round. A wall segment's
neighbours are more wall: give it vertical edges and the corridor grows a black
stripe every sixteen pixels. It is outlined top and bottom only, and its
variants are the interruptions — a missing board, a shelf, a hung banner, a
doorway — because a corridor of identical panels is a corridor nobody believes.

THE TABLE SHIPS ITS SURFACE. `topY` in the manifest is the row a weapon lies
on, in frame pixels, and it is part of the ART rather than a number the client
picks: three of the four tables are different heights on purpose (a trestle, a
board over crates, a board over a barrel), and a single hardcoded offset would
float one gun and sink another. The client draws the weapon at `topY` and lifts
it from there when somebody comes close.

MATERIALS COME FROM `make_scenery.py`. The stall is built out of the same
worked timber, canvas and metal as the crates and the cabin, for the reason
there is only one blood in the game: a shop that shares no material with the
world outside it reads as a different game's asset pack.

Usage:
    python tools/make_store.py
    python tools/make_store.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

from make_scenery import (
    CANVAS,
    CLOTH_RUST,
    GLASS,
    LEATHER,
    METAL,
    OUTLINE_WOOD,
    PLANK,
    PLANK_DARK,
    ROPE,
)
from make_textures import (
    BEAM,
    COIN_RAMP,
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    add,
    clamp01,
    ellipse,
    fbm,
    hash01,
    lattice,
    outline,
    pack,
    pick,
    resolve,
    rgb,
)

# --- palette ----------------------------------------------------------------
# Indoor timber: the same wood as the forest's crates, dried out and standing
# under a lamp. It is ramped brighter than anything in `terrain/` because this
# zone is LIT — the darkness pass is off here, so a floor authored for the
# lantern would read as a cellar.

FLOOR: Ramp = [rgb(c) for c in ("#2a2118", "#372b1e", "#453626", "#54432e", "#635038")]
FLOOR_SEAM: Ramp = [rgb(c) for c in ("#150f0a", "#1d1610", "#261d15")]
#: The wall behind him is a value darker than the floor. A room where the walls
#: and the floor sit on the same step has no corner in it.
WALL: Ramp = [rgb(c) for c in ("#201912", "#2b2118", "#362a1e", "#413425", "#4d3e2d")]
WALL_DEEP: Ramp = [rgb(c) for c in ("#0b0806", "#120e0a", "#191410")]
#: Brass and lamp oil. The only warm metal in the game outside the coin, and it
#: is deliberately close to it: this is the room where gold is what matters.
BRASS: Ramp = [rgb(c) for c in ("#3a2a12", "#584018", "#7a5a22", "#9c7530", "#c09b4a")]

TILE_TABLE_W = 2.0
TILE_TABLE_H = 1.25


def _grain_field(rng: random.Random, cells: tuple[int, ...]) -> list:
    return [(lattice(rng, count), count) for count in cells]


# --- the floor --------------------------------------------------------------

#: Board height in pixels. Eight divides the 64px atlas, so the courses wrap.
BOARD_H = 8


def make_boards(size: int, seed: int) -> Image.Image:
    """One seamless plank floor, read back by the client as a 4x4 grid of tiles.

    The grain is sampled at twice the vertical frequency, which stretches every
    feature along X: that is what makes it read as a sawn board running the
    length of the corridor rather than as soil with lines drawn on it. It still
    wraps, because the lattice wraps in both axes whatever rate it is read at.
    """
    rng = random.Random(seed)
    field = _grain_field(rng, (8, 16, 32))
    knots = _grain_field(rng, (5, 10))

    img = Image.new("RGBA", (size, size))
    px = img.load()
    half = size // 2
    for y in range(size):
        course = y // BOARD_H
        within = y % BOARD_H
        # Butt joints alternate course to course. Aligned joints would draw a
        # second grid on top of the tile grid, which is the exact thing the
        # staggering exists to hide.
        offset = half // 2 if course % 2 else 0
        for x in range(size):
            grain = fbm(field, x, y * 2, size)
            speck = (hash01(x, y, seed) - 0.5) * 0.22
            value = grain * 0.85 + 0.12 + speck

            knot = fbm(knots, x, y * 2, size)
            if knot > 0.80:
                value -= (knot - 0.80) * 3.2

            colour = pick(FLOOR, clamp01(value), x, y)

            if within == 0:  # the seam between two courses
                colour = pick(FLOOR_SEAM, clamp01(0.3 + grain * 0.5), x, y)
            elif within == 1:
                colour = pick(FLOOR, clamp01(value * 0.62), x, y)
            elif within == BOARD_H - 1:  # the lit top edge of the board below
                colour = pick(FLOOR, clamp01(value * 1.15 + 0.16), x, y)

            if (x + offset) % half == 0 and within != 0:  # a butt joint
                colour = pick(FLOOR_SEAM, clamp01(0.2 + grain * 0.4), x, y)
            elif (x + offset) % half == 2 and within in (3, 4):  # nail heads
                colour = pick(METAL, 0.55 + speck, x, y)

            px[x, y] = colour
    return img


# --- the wall ---------------------------------------------------------------


def _wall_boards(img: Image.Image, rng: random.Random, top: int) -> None:
    """Vertical boarding from `top` to the floor, with a rail near the bottom."""
    px = img.load()
    field = _grain_field(rng, (4, 8))
    for y in range(top, img.height):
        for x in range(img.width):
            grain = fbm(field, x * 2, y, img.width * 2)
            value = grain * 0.7 + 0.18 + (hash01(x, y, 4409) - 0.5) * 0.18
            colour = pick(WALL, clamp01(value), x, y)
            if x % 5 == 0:  # the gap between two boards
                colour = pick(WALL_DEEP, clamp01(0.3 + grain * 0.5), x, y)
            elif x % 5 == 1:
                colour = pick(WALL, clamp01(value * 1.2 + 0.1), x, y)
            px[x, y] = colour
    # A rail across the boarding: the one horizontal in an otherwise vertical
    # panel, and what stops a run of wall reading as a barcode.
    rail = img.height - 11
    for y in range(rail, rail + 3):
        for x in range(img.width):
            shade = 0.7 if y == rail else (0.45 if y == rail + 2 else 0.9)
            px[x, y] = pick(PLANK, shade, x, y)


def make_wall(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One segment of the corridor's far side. Six of them, and they TILE.

    No side keyline: the neighbour of a wall is more wall. The top edge is the
    only outline, because that is the one edge that meets something else.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    _wall_boards(img, rng, 2)

    for x in range(w):  # the top edge, where the wall meets the dark above it
        px[x, 0] = OUTLINE_WOOD
        px[x, 1] = pick(WALL_DEEP, 0.6, x, 1)

    if variant == 1:  # a board sprung off, and the dark behind it
        for y in range(6, h - 14):
            for x in range(5, 9):
                px[x, y] = pick(WALL_DEEP, clamp01(0.15 + hash01(x, y, 77) * 0.3), x, y)
        for y in range(6, 9):
            px[9, y] = pick(PLANK, 0.8, 9, y)

    elif variant == 2:  # a shelf, and what is left on it
        shelf = 12
        for x in range(1, w - 1):
            px[x, shelf] = pick(PLANK, 0.85, x, shelf)
            px[x, shelf + 1] = pick(PLANK_DARK, 0.5, x, shelf + 1)
        for index, (cx, tall, ramp) in enumerate(
            ((3, 4, GLASS), (7, 5, GLASS), (11, 3, METAL))
        ):
            for y in range(shelf - tall, shelf):
                for x in range(cx, cx + 3):
                    lit = 0.75 if x == cx else 0.45
                    px[x, y] = pick(ramp, lit + (y - shelf + tall) * 0.05, x, y)
            px[cx + 1, shelf - tall] = pick(ROPE, 0.7, cx + 1, shelf - tall)

    elif variant == 3:  # a banner, the one soft thing on a hard wall
        for y in range(3, h - 16):
            for x in range(3, w - 3):
                edge = x in (3, w - 4)
                fold = math.sin((x - 3) * 0.9) * 0.16
                value = 0.55 + fold - (0.25 if edge else 0.0)
                px[x, y] = pick(CLOTH_RUST, clamp01(value + (y * 0.012)), x, y)
        for x in range(3, w - 3):  # the pole it hangs from
            px[x, 2] = pick(METAL, 0.6, x, 2)
        tip = h - 16
        for x in range(3, w - 3):  # a cut hem, not a straight one
            if (x - 3) % 4 in (0, 3):
                px[x, tip] = TRANSPARENT
                px[x, tip - 1] = pick(CLOTH_RUST, 0.35, x, tip - 1)

    elif variant == 4:  # a window, boarded over, with the night behind it
        for y in range(5, 18):
            for x in range(3, w - 3):
                px[x, y] = pick(WALL_DEEP, clamp01(0.1 + hash01(x, y, 991) * 0.25), x, y)
        for index, y in enumerate(range(6, 18, 5)):  # the boards across it
            for x in range(1, w - 1):
                for row in (y, y + 1):
                    px[x, row] = pick(PLANK, 0.75 if row == y else 0.45, x, row)

    elif variant == 5:  # a doorway: the corridor has to end somewhere
        for y in range(4, h - 2):
            for x in range(3, w - 3):
                px[x, y] = pick(WALL_DEEP, clamp01(0.05 + hash01(x, y, 313) * 0.14), x, y)
        for y in range(3, h - 2):  # the frame
            for x in (2, w - 3):
                px[x, y] = pick(PLANK, 0.8 if x == 2 else 0.5, x, y)
        for x in range(2, w - 2):
            px[x, 3] = pick(PLANK, 0.9, x, 3)

    return img


# --- the tables -------------------------------------------------------------
# Four stalls, three heights. `topY` is the row the stock lies on and it ships
# with the art; see the module docstring.


def _board_top(img: Image.Image, top: int, thickness: int, inset: int) -> None:
    px = img.load()
    for y in range(top, top + thickness):
        for x in range(inset, img.width - inset):
            lit = 0.92 if y == top else (0.7 if y == top + 1 else 0.4)
            px[x, y] = pick(PLANK, lit - hash01(x, y, 61) * 0.14, x, y)


def make_table(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One stall. Bottom-anchored, outlined, depth-sorted with the party."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()

    if variant == 0:  # a trestle: two sawhorses and a board
        _board_top(img, 4, 3, 0)
        for foot in (4, w - 8):
            for step in range(h - 8):
                y = 7 + step
                spread = step // 3
                for x in (foot - spread, foot + 3 + spread):
                    if 0 <= x < w:
                        px[x, y] = pick(PLANK, 0.55 - step * 0.02, x, y)
            for x in range(foot - 1, foot + 5):  # the cross-brace
                px[x, h - 7] = pick(PLANK, 0.45, x, h - 7)

    elif variant == 1:  # a board over two crates
        _board_top(img, 3, 3, 0)
        for box in (1, w - 12):
            for y in range(6, h - 1):
                for x in range(box, box + 11):
                    edge = x in (box, box + 10) or y in (6, h - 2)
                    value = 0.35 if edge else 0.6 - hash01(x, y, 131) * 0.2
                    px[x, y] = pick(PLANK, value, x, y)
            for y in range(6, h - 1):  # the diagonal batten
                run = box + (y - 6)
                if box <= run < box + 11:
                    px[run, y] = pick(PLANK_DARK, 0.7, run, y)

    elif variant == 2:  # a board over a barrel: the tall one
        _board_top(img, 1, 3, 2)
        cx = w // 2
        for y in range(4, h - 1):
            span = 8 - abs(y - (h // 2)) // 5
            for x in range(cx - span, cx + span):
                rim = y in (5, 10, h - 5)
                curve = 1.0 - abs(x - cx + 0.5) / (span + 1.0)
                value = 0.28 if rim else 0.3 + curve * 0.5
                px[x, y] = pick(PLANK, value - hash01(x, y, 211) * 0.12, x, y)
        for y in (5, 10, h - 5):  # the iron hoops
            for x in range(cx - 8, cx + 8):
                if px[x, y][3]:
                    px[x, y] = pick(METAL, 0.5 + hash01(x, y, 17) * 0.2, x, y)

    else:  # a table under a cloth: the one that hides its legs
        _board_top(img, 5, 2, 1)
        for y in range(7, h - 1):
            for x in range(1, w - 1):
                hem = y >= h - 3
                fold = math.sin(x * 0.7 + y * 0.15) * 0.12
                value = 0.5 + fold - (0.22 if hem else 0.0)
                if hem and (x % 5) in (0, 1):
                    continue  # the cloth is cut, and it does not reach the floor
                px[x, y] = pick(CANVAS, clamp01(value), x, y)
        for x in range(1, w - 1):  # a cord holding it on
            px[x, 9] = pick(ROPE, 0.6 + hash01(x, 9, 5) * 0.2, x, 9)

    outline(img, OUTLINE_WOOD)
    return img


#: The row a weapon lies on, per table variant. Part of the art: the four
#: stalls are deliberately different heights.
TABLE_TOP_Y = (4, 3, 1, 5)


# --- the lamp ---------------------------------------------------------------


def make_lamp(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """A lamp on a post. Its FIRE is not here — that is `lampfire.png`.

    Same split as the rift's pillar: paint the flame into the prop and the
    light goes under whatever the client multiplies over the frame, which
    leaves a lamp that is only lit when you are already standing in it.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    cx = w // 2
    housing_h = 9 if variant == 0 else 7
    post_top = 3 + housing_h

    for y in range(post_top, h - 2):  # the post
        for x in range(cx - 1, cx + 1):
            px[x, y] = pick(METAL, 0.55 if x == cx - 1 else 0.32, x, y)
    for y in range(h - 3, h):  # the foot
        span = 2 + (h - y)
        for x in range(cx - span, cx + span):
            px[x, y] = pick(METAL, 0.45 - (h - y) * 0.05, x, y)

    for y in range(3, 3 + housing_h):  # the glass housing
        for x in range(cx - 3, cx + 3):
            frame_px = x in (cx - 3, cx + 2) or y in (3, 2 + housing_h)
            ramp = BRASS if frame_px else GLASS
            value = 0.6 if frame_px else 0.35 + (y - 3) * 0.05
            px[x, y] = pick(ramp, value, x, y)
    for x in range(cx - 4, cx + 4):  # the cap
        px[x, 2] = pick(BRASS, 0.7, x, 2)
        px[x, 1] = pick(BRASS, 0.45, x, 1)
    if variant == 1:  # a hook, so it can hang off a wall instead
        for y in range(0, 2):
            px[cx, y] = pick(METAL, 0.6, cx, y)

    outline(img, OUTLINE_WOOD)
    return img


#: Where the flame sits inside the housing, per variant.
LAMP_FLAME_Y = (7, 5)


# --- the mat ----------------------------------------------------------------


def make_rug(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """The mat he stands on. A DECAL: flat, no outline, baked into the floor.

    It is the only thing in the corridor that says a person chose to be here
    rather than that a building happens to contain him.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    ramp = CLOTH_RUST if variant == 0 else CANVAS
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for y in range(h):
        for x in range(w):
            # A rounded rectangle: worn away at the corners, like a real mat.
            dx = abs(x - cx) / cx
            dy = abs(y - cy) / cy
            corner = (dx ** 4 + dy ** 4) ** 0.25
            if corner > 0.97 + hash01(x, y, 1201) * 0.06:
                continue
            border = corner > 0.80
            weft = 0.5 + math.sin(x * 0.8) * 0.06 + math.sin(y * 1.7) * 0.05
            value = weft + (0.22 if border else 0.0) - hash01(x, y, 61) * 0.14
            if not border and abs(dy) < 0.45 and (x + y * 2) % 9 < 2:
                value += 0.2  # the pattern woven into the middle
            px[x, y] = pick(ramp, clamp01(value), x, y)
    # Fringe on the short ends only, which is the end a mat is woven from.
    for y in range(h):
        if hash01(0, y, 9) > 0.45:
            for x in (0, w - 1):
                if px[x, y][3]:
                    px[x, y] = pick(ROPE, 0.55, x, y)
    return img


# --- light ------------------------------------------------------------------
# Greyscale, additive, tinted by the client — the same contract as every other
# VFX sheet. `lampfire` gets `fire.core`; `glow` gets the coin's gold, because
# what it is marking is a price.


def make_lampfire(w: int, h: int, frames: int, anchor: int) -> list[Image.Image]:
    """The flame in the housing, as a loop.

    Every wobble is a sine of the frame phase, so the last frame hands back to
    the first with nothing to see. Rolling it per frame stutters at the wrap
    even when each frame looks right on its own.
    """
    out: list[Image.Image] = []
    cx = (w - 1) / 2
    for index in range(frames):
        phase = index / frames * math.tau
        field = [[0.0] * w for _ in range(h)]
        lean = math.sin(phase) * 0.55
        tall = 3.4 + math.sin(phase * 2.0) * 0.5

        ellipse(field, cx + lean * 0.4, anchor - 1.2, 2.2, 1.5, 0.85)
        ellipse(field, cx + lean, anchor - tall, 1.5, tall * 0.72, 1.05)
        ellipse(field, cx + lean * 1.5, anchor - tall - 1.4, 0.9, 1.2, 0.8)
        # The room around the lamp: a wide, weak bloom, so the fire is a source
        # and not a sticker.
        ellipse(field, cx, anchor - 2.0, 7.0, 5.0, 0.28)

        for step in range(3):  # sparks, on the same phase so they loop too
            sway = math.sin(phase + step * 2.1)
            rise = ((index + step * 4) % frames) / frames
            add(field, int(round(cx + sway * 2.4)), int(anchor - 3 - rise * 7),
                0.55 * (1.0 - rise))

        img = Image.new("RGBA", (w, h), TRANSPARENT)
        resolve(field, img, BEAM, floor=0.10, tone=0.85, gain=1.05)
        out.append(img)
    return out


def make_glow(w: int, h: int, frames: int, anchor: int) -> list[Image.Image]:
    """The pool under a weapon you are close enough to buy.

    It is a flat ellipse on the table's surface with a slow pulse and two motes
    lifting out of it — the visual half of the lift the client gives the gun.
    Deliberately low and wide: a column here would fight the weapon's own
    silhouette, which is the thing the player is being asked to look at.
    """
    out: list[Image.Image] = []
    cx = (w - 1) / 2
    for index in range(frames):
        phase = index / frames * math.tau
        field = [[0.0] * w for _ in range(h)]
        swell = 0.82 + math.sin(phase) * 0.18

        ellipse(field, cx, anchor, 10.5 * swell, 3.2 * swell, 0.55)
        ellipse(field, cx, anchor, 6.0 * swell, 1.8 * swell, 0.5)
        ellipse(field, cx, anchor, 11.5 * swell, 3.6 * swell, 0.42, hollow=0.30)

        for step in range(2):
            rise = ((index + step * (frames // 2)) % frames) / frames
            drift = math.sin(phase + step * math.pi) * 3.0
            add(field, int(round(cx + drift)), int(anchor - 1 - rise * 6.0),
                0.6 * (1.0 - rise) ** 0.7)

        img = Image.new("RGBA", (w, h), TRANSPARENT)
        resolve(field, img, BEAM, floor=0.09, tone=0.8, gain=1.0)
        out.append(img)
    return out


# --- build ------------------------------------------------------------------

WALL_VARIANTS = 6
TABLE_VARIANTS = 4
LAMP_VARIANTS = 2
RUG_VARIANTS = 2
LAMPFIRE_FRAMES = 10
LAMPFIRE_FPS = 12
GLOW_FRAMES = 8
GLOW_FPS = 10


def _loop_seam(frames: list[Image.Image]) -> int:
    """How hard a looping sheet snaps at the wrap. Not zero — but small.

    A loop is a sine of the frame phase, so frame N-1 must be one step away
    from frame 0, never a jump. This measures the worst channel difference
    across the wrap against the worst difference inside the loop; if the wrap
    is the biggest step in the sheet, the wobble was rolled instead of phased.
    """
    def worst(a: Image.Image, b: Image.Image) -> int:
        pa, pb = a.load(), b.load()
        top = 0
        for y in range(a.height):
            for x in range(a.width):
                for ca, cb in zip(pa[x, y], pb[x, y]):
                    top = max(top, abs(ca - cb))
        return top

    inside = max(worst(frames[i], frames[i + 1]) for i in range(len(frames) - 1))
    wrap = worst(frames[-1], frames[0])
    return wrap - inside


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "store"
    out_dir.mkdir(parents=True, exist_ok=True)

    ground_size = tile * 4
    make_boards(ground_size, args.seed + 3).save(out_dir / "ground_boards.png")

    wall_w, wall_h = tile, round(tile * 2.25)
    walls = [
        make_wall(wall_w, wall_h, variant, random.Random(args.seed + 100 + variant * 7))
        for variant in range(WALL_VARIANTS)
    ]
    pack(walls, wall_w, wall_h).save(out_dir / "wall.png")

    table_w = round(tile * TILE_TABLE_W)
    table_h = round(tile * TILE_TABLE_H)
    tables = [
        make_table(table_w, table_h, variant, random.Random(args.seed + 200 + variant * 11))
        for variant in range(TABLE_VARIANTS)
    ]
    pack(tables, table_w, table_h).save(out_dir / "table.png")

    lamp_w, lamp_h = round(tile * 0.75), round(tile * 1.875)
    lamps = [
        make_lamp(lamp_w, lamp_h, variant, random.Random(args.seed + 300 + variant))
        for variant in range(LAMP_VARIANTS)
    ]
    pack(lamps, lamp_w, lamp_h).save(out_dir / "lamp.png")

    rug_w, rug_h = tile * 3, tile * 2
    rugs = [
        make_rug(rug_w, rug_h, variant, random.Random(args.seed + 400 + variant))
        for variant in range(RUG_VARIANTS)
    ]
    pack(rugs, rug_w, rug_h).save(out_dir / "rug.png")

    fire_w, fire_h = tile, round(tile * 1.625)
    fire_anchor = fire_h - 4
    fire = make_lampfire(fire_w, fire_h, LAMPFIRE_FRAMES, fire_anchor)
    pack(fire, fire_w, fire_h).save(out_dir / "lampfire.png")

    glow_w, glow_h = tile * 2, tile
    glow_anchor = glow_h - 4
    glow = make_glow(glow_w, glow_h, GLOW_FRAMES, glow_anchor)
    pack(glow, glow_w, glow_h).save(out_dir / "glow.png")

    for name, frames in (("lampfire", fire), ("glow", glow)):
        margin = _loop_seam(frames)
        print(f"  loop {name}: wrap step vs worst inner step = {margin:+d}")
        if margin > 0:
            raise SystemExit(f"{name} snaps at the wrap — phase it, do not roll it")

    manifest = {
        "tile": tile,
        "seed": args.seed,
        # One built floor. See the module docstring for why there is no second.
        "grounds": [
            {"name": "boards", "file": "ground_boards.png", "tile": tile,
             "cols": 4, "rows": 4}
        ],
        # PROPS: bottom-anchored, depth-sorted with the party.
        "props": {
            "wall": {
                "file": "wall.png", "frameWidth": wall_w, "frameHeight": wall_h,
                "frames": len(walls), "sway": 0,
                # Tiles horizontally, so it carries no side keyline. Variant 5
                # is the doorway the corridor ends on.
                "tiles": True, "doorway": 5,
            },
            "table": {
                "file": "table.png", "frameWidth": table_w, "frameHeight": table_h,
                "frames": len(tables), "sway": 0,
                # The row the stock lies on, per variant. Pose, not decoration.
                "topY": list(TABLE_TOP_Y),
            },
            "lamp": {
                "file": "lamp.png", "frameWidth": lamp_w, "frameHeight": lamp_h,
                "frames": len(lamps), "sway": 0,
                # Where `lampfire` burns inside the housing, per variant.
                "flameY": list(LAMP_FLAME_Y),
            },
        },
        # DECALS: flat, centred on their point, baked into the floor canvas.
        "decals": {
            "rug": {"file": "rug.png", "frameWidth": rug_w, "frameHeight": rug_h,
                    "frames": len(rugs)},
        },
        # VFX: greyscale, additive, tinted at draw time.
        "effects": {
            "lampfire": {
                "file": "lampfire.png", "frameWidth": fire_w, "frameHeight": fire_h,
                "frames": LAMPFIRE_FRAMES, "fps": LAMPFIRE_FPS,
                "anchorY": fire_anchor, "loop": True,
            },
            "glow": {
                "file": "glow.png", "frameWidth": glow_w, "frameHeight": glow_h,
                "frames": GLOW_FRAMES, "fps": GLOW_FPS,
                "anchorY": glow_anchor, "loop": True,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: boards {ground_size}x{ground_size}, "
        f"wall {len(walls)}x{wall_w}x{wall_h}, "
        f"table {len(tables)}x{table_w}x{table_h}, "
        f"lamp {len(lamps)}x{lamp_w}x{lamp_h}, "
        f"rug {len(rugs)}x{rug_w}x{rug_h}, "
        f"lampfire {LAMPFIRE_FRAMES}x{fire_w}x{fire_h} @{LAMPFIRE_FPS}fps, "
        f"glow {GLOW_FRAMES}x{glow_w}x{glow_h} @{GLOW_FPS}fps"
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--preview", default="",
                    help="write a scaled mock-up of the corridor HERE (outside "
                         "the tree) for eyeballing the art")
    ap.add_argument("--preview-scale", type=int, default=6)
    args = ap.parse_args()
    out_dir = build(args)
    if args.preview:
        _preview(out_dir, Path(args.preview), args.preview_scale, args.tile)


def _preview(out_dir: Path, path: Path, scale: int, tile: int) -> None:
    """A mock-up of the corridor: floor, wall, mat, tables, lamps, merchant.

    Not shipped, and not how the client composes the scene — this exists so the
    art can be judged as a room rather than as seven sheets in a folder.
    """
    manifest = json.loads((out_dir / "manifest.json").read_text())
    cols, rows = 20, 9
    scene = Image.new("RGBA", (cols * tile, rows * tile), (0, 0, 0, 255))

    ground = Image.open(out_dir / "ground_boards.png")
    for ty in range(rows):
        for tx in range(cols):
            cell = ground.crop((
                (tx % 4) * tile, (ty % 4) * tile,
                (tx % 4 + 1) * tile, (ty % 4 + 1) * tile,
            ))
            scene.paste(cell, (tx * tile, ty * tile))

    def strip(spec: dict) -> list[Image.Image]:
        sheet = Image.open(out_dir / spec["file"])
        w, h = spec["frameWidth"], spec["frameHeight"]
        return [sheet.crop((i * w, 0, (i + 1) * w, h)) for i in range(spec["frames"])]

    walls = strip(manifest["props"]["wall"])
    tables = strip(manifest["props"]["table"])
    lamps = strip(manifest["props"]["lamp"])
    rugs = strip(manifest["decals"]["rug"])
    fire = strip(manifest["effects"]["lampfire"])
    glow = strip(manifest["effects"]["glow"])

    wall_base = 3 * tile
    order = (5, 0, 2, 0, 3, 0, 1, 0, 4, 0, 0, 3, 0, 2, 0, 1, 0, 0, 0, 5)
    for tx in range(cols):
        art = walls[order[tx % len(order)]]
        scene.paste(art, (tx * tile, wall_base - art.height), art)

    rug = rugs[0]
    scene.paste(rug, ((cols // 2) * tile - rug.width // 2, 4 * tile), rug)

    merchant_dir = PROCESSED_DIR / "merchant"
    if merchant_dir.exists():
        spec = json.loads((merchant_dir / "manifest.json").read_text())
        idle = Image.open(merchant_dir / "idle.png")
        mw, mh = spec["frameWidth"], spec["frameHeight"]
        art = idle.crop((0, 0, mw, mh))
        scene.paste(art, ((cols // 2) * tile - mw // 2, 5 * tile - mh), art)

    guns_dir = PROCESSED_DIR / "guns"
    gun_frames: list[Image.Image] = []
    if guns_dir.exists():
        spec = json.loads((guns_dir / "manifest.json").read_text())
        sheet = Image.open(guns_dir / spec["sheet"])
        gw, gh = spec["frameWidth"], spec["frameHeight"]
        gun_frames = [
            sheet.crop((i * gw, 0, (i + 1) * gw, gh)) for i in range(spec["frames"])
        ]

    for index in range(4):
        table = tables[index]
        x = (3 + index * 4) * tile
        y = 6 * tile
        scene.paste(table, (x, y - table.height), table)
        if gun_frames:
            gun = gun_frames[index % len(gun_frames)]
            top = y - table.height + manifest["props"]["table"]["topY"][index]
            if index == 1:  # one of them lifted, with its pool under it
                pool = glow[0]
                scene.paste(pool, (x + table.width // 2 - pool.width // 2,
                                   top - pool.height + 4), pool)
                top -= 3
            scene.paste(gun, (x + table.width // 2 - gun.width // 2,
                              top - gun.height), gun)

    for tx in (2, cols - 3):
        lamp = lamps[0]
        base = 3 * tile
        scene.paste(lamp, (tx * tile, base - lamp.height), lamp)
        flame = fire[0]
        fy = base - lamp.height + manifest["props"]["lamp"]["flameY"][0]
        scene.paste(flame, (tx * tile + lamp.width // 2 - flame.width // 2,
                            fy - manifest["effects"]["lampfire"]["anchorY"]), flame)

    scene = scene.resize((scene.width * scale, scene.height * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
