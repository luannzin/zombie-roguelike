#!/usr/bin/env python3
"""Asset pipeline: the MERCHANT'S CAMP — where the night's take gets spent.

Output (assets/processed/store/):
    table.png    4 frames, 32x20    PROP   — the trestles a weapon lies on
    kit.png      5 frames, 26x24    PROP   — his own gear, and NOT for sale
    torch.png    2 frames, 12x30    PROP   — the posts lighting the pitch
    rug.png      2 frames, 48x32    DECAL  — the mat he trades over
    torchfire.png 12 frames, 20x40  VFX    — loop, warm fire in a torch head
    glow.png      8 frames, 32x16   VFX    — loop, under a weapon you are near
    manifest.json

IT IS OUTDOORS, AND THAT IS THE WHOLE BRIEF.
This was an interior once — a plank corridor with walls and hanging lamps — and
it was wrong for one reason that outweighed everything it got right: it was the
only room in the game. Every other place the party stands is forest at night,
so a building with a floor and a ceiling did not read as somewhere they had
walked to, it read as a menu the game had cut to. The camp is now a CLEARING:
the same trees, the same soil, the same dark, with a trader's pitch set up in
the middle of it and torches keeping the night off the stock.

So this file no longer draws a floor, a wall or a hanging lamp. The ground is
`make_textures.py`'s forest soil, unchanged, because it is the same forest;
the shelter is the TENT out of `make_scenery.py`, because a trader sleeping
under canvas in the woods is a thing that already exists in this game's world
and a second tent sheet would only be a slightly different one.

WHAT IS LEFT IS WHAT IS HIS. The tables, the mat under his feet, and the
torches he drove into the ground when he pitched — plus the pool that says
which weapon you are standing at. Everything else on that map belongs to the
forest and comes from the forest's own generators, which is the same rule
`server/app/scenery.py` keeps for every other scene.

THE KIT IS THE STORY, AND IT IS DELIBERATELY NOT INTERACTIVE.
Four tables in a clearing is a shop. Four tables with crates roped up behind
them, a rack of spare barrels, a plank shelf of tins and a padlocked strongbox
is somebody LIVING out here and selling out of what they have. Nothing in
`kit.png` can be opened, bought or broken — and the ART has to say so, because
the player spent the whole previous night learning that a box in this game is a
thing you open. So every frame is drawn SHUT: roped, strapped, lidded,
padlocked. A silhouette that reads "closed" is what stops a safe zone reading
as unclaimed loot, and it is cheaper than any amount of prompt suppression.

THE TORCH IS WARM, and it is not the extraction pad's. `make_rift.py` also
draws a torch and its fire, but that one burns the anomaly's prism — cyan and
violet, because it is marking a hole in the world. This one is a man's
campfire on a stick. Sharing the sheet would have said the merchant and the
rift are the same kind of thing, which is the one thing the scene must not say.

THE TABLE SHIPS ITS SURFACE. `topY` in the manifest is the row a weapon lies
on, in frame pixels, and it is part of the ART rather than a number the client
picks: three of the four tables are different heights on purpose (a trestle, a
board over crates, a board over a barrel), and a single hardcoded offset would
float one gun and sink another.

MATERIALS COME FROM `make_scenery.py`. The stall is built out of the same
worked timber, canvas and rope as the crates and the cabin, for the reason
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
    LEATHER,
    METAL,
    OUTLINE_WOOD,
    PLANK,
    PLANK_DARK,
    ROPE,
)
from make_textures import (
    DEFAULT_TILE,
    FLAME,
    PROCESSED_DIR,
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
# Everything here stands in the forest at night and is multiplied by the same
# darkness pass the trees are, so it is toned like scenery and not like an
# interior. The one exception is the fire, which is drawn additively AFTER that
# pass — see `make_torchfire`.

#: Iron on a torch head, and the bands lashing it to its post.
IRON: Ramp = [rgb(c) for c in ("#1b1a1d", "#2b2a2f", "#3d3b42", "#514e57", "#6a6670")]
#: Coals sitting in a torch head that is not currently being drawn over by its
#: own flame. Warm, so an unlit frame still reads as something that burns.
COALS: Ramp = [rgb(c) for c in ("#3a1608", "#6b2a0d", "#9c4415", "#c96a22")]

TILE_TABLE_W = 2.0
TILE_TABLE_H = 1.25


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


# --- his own kit ------------------------------------------------------------
# Five props standing around the pitch. See the module docstring for why none
# of them opens: this is the one zone in the game where a box is furniture.
#
# THEY SHARE THE TABLES' MATERIALS on purpose. The stalls, the crates and the
# shelf are the same worked timber, canvas and rope, so they read as one
# person's belongings rather than as five things that happened to land in one
# clearing.

TILE_KIT_W = 26
TILE_KIT_H = 24


def make_kit(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One piece of the trader's own gear. Bottom-anchored, outlined."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()

    def box(x0: int, y0: int, x1: int, y1: int, ramp, base: float, salt: int) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not (0 <= x < w and 0 <= y < h):
                    continue
                edge = x in (x0, x1) or y in (y0, y1)
                value = base - (0.22 if edge else 0.0) - hash01(x, y, salt) * 0.14
                px[x, y] = pick(ramp, value, x, y)

    if variant == 0:  # crates, stacked and roped shut
        box(2, h - 11, 14, h - 1, PLANK, 0.62, 11)
        box(13, h - 9, 24, h - 1, PLANK, 0.54, 23)
        box(4, h - 19, 15, h - 12, PLANK, 0.68, 37)
        # The rope over the top box. It is the entire "shut" statement, and it
        # is why this reads as stock rather than as three things to open.
        for x in range(4, 16):
            px[x, h - 16] = pick(ROPE, 0.8 - hash01(x, 0, 41) * 0.2, x, h - 16)
        for y in range(h - 19, h - 12):
            px[9, y] = pick(ROPE, 0.72, 9, y)

    elif variant == 1:  # a barrel with rods and tools fanned out of it
        cx = 9
        for y in range(h - 15, h):
            span = 7 - abs(y - (h - 8)) // 6
            for x in range(cx - span, cx + span):
                hoop = y in (h - 14, h - 8, h - 2)
                curve = 1.0 - abs(x - cx + 0.5) / (span + 1.0)
                value = 0.3 if hoop else 0.32 + curve * 0.48
                px[x, y] = pick(PLANK, value - hash01(x, y, 71) * 0.1, x, y)
        for y in (h - 14, h - 8, h - 2):
            for x in range(cx - 7, cx + 7):
                if 0 <= x < w and px[x, y][3]:
                    px[x, y] = pick(METAL, 0.52 + hash01(x, y, 19) * 0.2, x, y)
        # The rods. The one vertical in an otherwise low, heavy piece — and
        # what stops the barrel reading as one more thing you can break.
        for index, lean in enumerate((-3, -1, 2, 4)):
            for step in range(9 + index % 3):
                x = cx + lean + (step * (1 if lean > 0 else -1)) // 3
                y = h - 15 - step
                if 0 <= x < w and 0 <= y < h:
                    px[x, y] = pick(METAL, 0.6 - step * 0.02, x, y)

    elif variant == 2:  # a rack of spare barrels and stocks
        for foot in (3, w - 5):  # the A-frame
            for step in range(h - 6):
                y = 4 + step
                x = foot + (step * (1 if foot < w // 2 else -1)) // 6
                if 0 <= x < w:
                    px[x, y] = pick(PLANK, 0.58 - step * 0.012, x, y)
        for x in range(3, w - 3):  # the crossbar
            px[x, 9] = pick(PLANK, 0.7, x, 9)
        for index, slot in enumerate(range(5, w - 5, 5)):
            length = 12 + (index % 3) * 3
            for y in range(6, 6 + length):
                px[slot, y] = pick(METAL, 0.62 - (y - 6) * 0.02, slot, y)
                if slot + 1 < w:
                    px[slot + 1, y] = pick(METAL, 0.42, slot + 1, y)
            for x in range(slot - 1, slot + 3):  # the strap holding it on
                if 0 <= x < w:
                    px[x, 9] = pick(LEATHER, 0.7, x, 9)

    elif variant == 3:  # planks on blocks, with tins standing on them
        box(1, h - 6, 7, h - 1, METAL, 0.34, 91)
        box(w - 8, h - 6, w - 2, h - 1, METAL, 0.34, 97)
        for x in range(w):  # the shelf board
            for y in range(h - 9, h - 6):
                lit = 0.9 if y == h - 9 else 0.55
                px[x, y] = pick(PLANK, lit - hash01(x, y, 53) * 0.16, x, y)
        for index, tin in enumerate(range(2, w - 4, 5)):
            tall = 5 + (index % 3)
            box(tin, h - 9 - tall, tin + 3, h - 10, METAL, 0.6 + (index % 2) * 0.12, 61)
            band = h - 12 + (index % 2)
            for x in range(tin, tin + 4):  # a paper label round each one
                if 0 <= x < w and 0 <= band < h and px[x, band][3]:
                    px[x, band] = pick(CLOTH_RUST, 0.72, x, band)

    else:  # a strongbox under a tarp, padlocked
        box(3, h - 12, w - 4, h - 2, METAL, 0.5, 101)
        for x in range(3, w - 3):  # the lid's lip
            px[x, h - 12] = pick(METAL, 0.78, x, h - 12)
        # The hasp and the lock: small, central, and the reason this piece
        # reads as CLOSED from the far end of the glade.
        for y in range(h - 13, h - 9):
            px[w // 2, y] = pick(METAL, 0.85, w // 2, y)
        box(w // 2 - 2, h - 10, w // 2 + 1, h - 7, METAL, 0.86, 7)
        # The tarp thrown half over it, hanging off the back-left corner. One
        # soft shape against four hard ones, so the group has a silhouette.
        for y in range(h - 17, h - 9):
            for x in range(1, 13 - (y - (h - 17))):
                fold = math.sin(x * 0.8 + y * 0.3) * 0.1
                px[x, y] = pick(CANVAS, 0.56 + fold - hash01(x, y, 83) * 0.12, x, y)

    outline(img, OUTLINE_WOOD)
    return img


# --- the torches ------------------------------------------------------------


def make_torch(w: int, h: int, variant: int) -> Image.Image:
    """One torch post, UNLIT. The fire is `torchfire.png`.

    Same split every light in this game makes, and for the same reason: paint
    the flame into the prop and it goes under whatever the client multiplies
    over the frame, which leaves a torch that is only lit once you are already
    standing in its light. These exist to be seen from the far end of a dark
    clearing, so the burning half has to be additive and drawn after the night.

    Two variants because a merchant drove them in by hand: one is a straight
    post with an iron basket, the other is a lashed bundle on a leaning stake.
    A row of identical posts is a fence, not a camp somebody made.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    cx = (w - 1) / 2.0
    head_top = 2
    head_bottom = 9

    # The post. Variant 1 leans, and the lean is applied as a per-row shift so
    # the whole thing stays one silhouette rather than a stack of offset boxes.
    def centre_at(y: int) -> float:
        if variant == 0:
            return cx
        return cx + (y - h) * 0.055

    body: dict[tuple[int, int], str] = {}
    for y in range(head_top, h):
        c = centre_at(y)
        if y <= head_bottom:
            t = (y - head_top) / max(head_bottom - head_top, 1)
            # Wide at the lip, pinched where it meets the post: the silhouette
            # has to say "something is held up here" at twelve pixels across.
            half = w * 0.38 - t * (w * 0.38 - 1.3)
            part = "head"
        else:
            t = (y - head_bottom) / max(h - head_bottom, 1)
            half = 1.1 + t * 0.85  # thicker where it is driven in
            part = "post"
        for x in range(w):
            if abs(x - c) <= half:
                body[(x, y)] = part

    for (x, y), part in body.items():
        edge = any(
            (x + ox, y + oy) not in body for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        if edge:
            px[x, y] = OUTLINE_WOOD
            continue
        across = (x - centre_at(y)) / max(w * 0.5, 0.5)
        if part == "head":
            ramp = IRON if variant == 0 else ROPE
            shade = 0.62 - across * 0.28
            px[x, y] = pick(ramp, clamp01(shade + (hash01(x, y, 907) - 0.5) * 0.14), x, y)
        else:
            shade = 0.55 - across * 0.26 - (y / h) * 0.18
            px[x, y] = pick(PLANK, clamp01(shade + (hash01(x, y, 911) - 0.5) * 0.16), x, y)

    # Two bands lashing the head to the post. At twelve pixels wide this is the
    # only detail that survives, and without it the head is a blob.
    for y in (head_bottom + 1, head_bottom + 3):
        for x in range(w):
            if body.get((x, y)) == "post":
                px[x, y] = (LEATHER if variant == 1 else IRON)[1]

    # Coals in the head. Scattered over two rows rather than filling one — a
    # solid row at the lip reads as a coloured lid on the sprite, not as
    # something burning inside a basket.
    for y in (head_top + 1, head_top + 2):
        for x in range(w):
            if body.get((x, y)) != "head" or hash01(x, y, 919) > 0.5:
                continue
            px[x, y] = pick(COALS, 0.55 + hash01(x, y, 923) * 0.4, x, y)
    return img


#: Where the flame sits inside the head, per variant, in frame pixels.
TORCH_FLAME_Y = (3, 3)


# --- the mat ----------------------------------------------------------------


def make_rug(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """The mat he trades over. A DECAL: flat, no outline, baked into the ground.

    It is the only thing on the pitch that says a person chose this spot rather
    than that a clearing happens to contain him.
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
# Additive, drawn after the darkness pass. `torchfire` carries its own WARM
# colour rather than being tinted at draw time: a flame is not one hue, it is a
# ramp from a dull red root to a white core, and a single draw-time multiply
# cannot produce that — the same reason `make_rift.py`'s sheets are `tinted:
# false`. `glow` stays neutral and takes the coin's gold, because what it is
# marking is a price.


def make_torchfire(w: int, h: int, frames: int, anchor: int) -> list[Image.Image]:
    """The fire in a torch head, as a loop.

    Every wobble is a sine of the frame phase, so the last frame hands back to
    the first with nothing to see. Rolling it per frame stutters at the wrap
    even when each frame looks right on its own.

    Bigger than the head it sits in, and deliberately: this is the one thing on
    the map that has to be legible from the far side of a dark clearing, and a
    flame cropped to its basket is a pilot light.
    """
    out: list[Image.Image] = []
    cx = (w - 1) / 2
    for index in range(frames):
        phase = index / frames * math.tau
        field = [[0.0] * w for _ in range(h)]
        lean = math.sin(phase) * 0.7
        tall = 5.2 + math.sin(phase * 2.0) * 0.8

        # Root, body, tip. Three ellipses up one leaning axis is the cheapest
        # shape that reads as fire rather than as a glowing blob.
        ellipse(field, cx + lean * 0.3, anchor - 1.0, 2.6, 1.7, 0.95)
        ellipse(field, cx + lean, anchor - tall * 0.55, 2.0, tall * 0.6, 1.05)
        ellipse(field, cx + lean * 1.6, anchor - tall, 1.1, 1.6, 0.85)
        # The air around it: a wide, weak bloom, so the torch is a source and
        # not a sticker.
        ellipse(field, cx, anchor - 2.5, 8.5, 6.5, 0.30)

        for step in range(4):  # sparks, on the same phase so they loop too
            sway = math.sin(phase + step * 1.7)
            rise = ((index + step * 3) % frames) / frames
            add(field, int(round(cx + sway * 3.0)), int(anchor - 4 - rise * 11),
                0.5 * (1.0 - rise))

        img = Image.new("RGBA", (w, h), TRANSPARENT)
        resolve(field, img, FLAME, floor=0.09, tone=0.88, gain=1.15)
        out.append(img)
    return out


def make_glow(w: int, h: int, frames: int, anchor: int) -> list[Image.Image]:
    """The pool under a weapon you are close enough to buy.

    A flat ellipse on the table's surface with a slow pulse and two motes
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
        resolve(field, img, FLAME, floor=0.09, tone=0.8, gain=1.0)
        out.append(img)
    return out


# --- build ------------------------------------------------------------------

TABLE_VARIANTS = 4
TORCH_VARIANTS = 2
RUG_VARIANTS = 2
TORCHFIRE_FRAMES = 12
TORCHFIRE_FPS = 12
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

    table_w = round(tile * TILE_TABLE_W)
    table_h = round(tile * TILE_TABLE_H)
    tables = [
        make_table(table_w, table_h, variant, random.Random(args.seed + 200 + variant * 11))
        for variant in range(TABLE_VARIANTS)
    ]
    pack(tables, table_w, table_h).save(out_dir / "table.png")

    torch_w, torch_h = round(tile * 0.75), round(tile * 1.875)
    torches = [make_torch(torch_w, torch_h, variant) for variant in range(TORCH_VARIANTS)]
    pack(torches, torch_w, torch_h).save(out_dir / "torch.png")

    rug_w, rug_h = tile * 3, tile * 2
    rugs = [
        make_rug(rug_w, rug_h, variant, random.Random(args.seed + 400 + variant))
        for variant in range(RUG_VARIANTS)
    ]
    pack(rugs, rug_w, rug_h).save(out_dir / "rug.png")

    fire_w, fire_h = round(tile * 1.25), round(tile * 2.5)
    fire_anchor = fire_h - 6
    fire = make_torchfire(fire_w, fire_h, TORCHFIRE_FRAMES, fire_anchor)
    pack(fire, fire_w, fire_h).save(out_dir / "torchfire.png")

    glow_w, glow_h = tile * 2, tile
    glow_anchor = glow_h - 4
    glow = make_glow(glow_w, glow_h, GLOW_FRAMES, glow_anchor)
    pack(glow, glow_w, glow_h).save(out_dir / "glow.png")

    for name, frames in (("torchfire", fire), ("glow", glow)):
        margin = _loop_seam(frames)
        print(f"  loop {name}: wrap step vs worst inner step = {margin:+d}")
        if margin > 0:
            raise SystemExit(f"{name} snaps at the wrap — phase it, do not roll it")

    kits = [
        make_kit(TILE_KIT_W, TILE_KIT_H, index, random.Random(args.seed + 900 + index))
        for index in range(5)
    ]
    pack(kits, TILE_KIT_W, TILE_KIT_H).save(out_dir / "kit.png")

    manifest = {
        "tile": tile,
        "seed": args.seed,
        # NO GROUND. The camp stands on the forest's own soil — see the module
        # docstring on why this stopped being an interior.
        # PROPS: bottom-anchored, depth-sorted with the party.
        "props": {
            "table": {
                "file": "table.png", "frameWidth": table_w, "frameHeight": table_h,
                "frames": len(tables), "sway": 0,
                # The row the stock lies on, per variant. Pose, not decoration.
                "topY": list(TABLE_TOP_Y),
            },
            # His gear. Five frames, none of them a container — see the module
            # docstring. Placed by `server/app/store.py` as ordinary scenery
            # props, so nothing on the client knows they are special.
            "kit": {
                "file": "kit.png", "frameWidth": TILE_KIT_W,
                "frameHeight": TILE_KIT_H, "frames": len(kits), "sway": 0,
            },
            "torch": {
                "file": "torch.png", "frameWidth": torch_w, "frameHeight": torch_h,
                "frames": len(torches), "sway": 0,
                # Where `torchfire` burns inside the head, per variant.
                "flameY": list(TORCH_FLAME_Y),
            },
        },
        # DECALS: flat, centred on their point, baked into the ground canvas.
        "decals": {
            "rug": {"file": "rug.png", "frameWidth": rug_w, "frameHeight": rug_h,
                    "frames": len(rugs)},
        },
        # VFX: additive, drawn after the darkness pass. `torchfire` carries its
        # own warm colour — a flame is a ramp, not a hue, and a draw-time
        # multiply cannot make one.
        "effects": {
            "torchfire": {
                "file": "torchfire.png", "frameWidth": fire_w, "frameHeight": fire_h,
                "frames": TORCHFIRE_FRAMES, "fps": TORCHFIRE_FPS,
                "anchorY": fire_anchor, "loop": True, "tinted": False,
            },
            "glow": {
                "file": "glow.png", "frameWidth": glow_w, "frameHeight": glow_h,
                "frames": GLOW_FRAMES, "fps": GLOW_FPS,
                "anchorY": glow_anchor, "loop": True, "tinted": False,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: "
        f"table {len(tables)}x{table_w}x{table_h}, "
        f"torch {len(torches)}x{torch_w}x{torch_h}, "
        f"rug {len(rugs)}x{rug_w}x{rug_h}, "
        f"torchfire {TORCHFIRE_FRAMES}x{fire_w}x{fire_h} @{TORCHFIRE_FPS}fps, "
        f"glow {GLOW_FRAMES}x{glow_w}x{glow_h} @{GLOW_FPS}fps"
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--preview", default="",
                    help="write a scaled mock-up of the pitch HERE (outside "
                         "the tree) for eyeballing the art")
    ap.add_argument("--preview-scale", type=int, default=6)
    args = ap.parse_args()
    out_dir = build(args)
    if args.preview:
        _preview(out_dir, Path(args.preview), args.preview_scale, args.tile)


def _preview(out_dir: Path, path: Path, scale: int, tile: int) -> None:
    """A mock-up of the pitch: soil, tent, mat, tables, torches, merchant.

    Not shipped, and not how the client composes the scene — this exists so the
    art can be judged as a place rather than as five sheets in a folder. The
    ground and the tent are pulled from the OTHER generators on purpose: this
    camp's whole argument is that it is made of the same forest everything else
    is, and a preview on a flat background could not show that.
    """
    manifest = json.loads((out_dir / "manifest.json").read_text())
    cols, rows = 22, 12
    scene = Image.new("RGBA", (cols * tile, rows * tile), (12, 14, 12, 255))

    terrain_dir = PROCESSED_DIR / "terrain"
    if terrain_dir.exists():
        spec = json.loads((terrain_dir / "manifest.json").read_text())
        soil = Image.open(terrain_dir / spec["grounds"][0]["file"])
        cells = spec["grounds"][0]
        for ty in range(rows):
            for tx in range(cols):
                cell = soil.crop((
                    (tx % cells["cols"]) * tile, (ty % cells["rows"]) * tile,
                    (tx % cells["cols"] + 1) * tile, (ty % cells["rows"] + 1) * tile,
                ))
                scene.paste(cell, (tx * tile, ty * tile))

    def strip(spec: dict, root: Path) -> list[Image.Image]:
        sheet = Image.open(root / spec["file"])
        w, h = spec["frameWidth"], spec["frameHeight"]
        return [sheet.crop((i * w, 0, (i + 1) * w, h)) for i in range(spec["frames"])]

    tables = strip(manifest["props"]["table"], out_dir)
    torches = strip(manifest["props"]["torch"], out_dir)
    rugs = strip(manifest["decals"]["rug"], out_dir)
    fire = strip(manifest["effects"]["torchfire"], out_dir)

    scenery_dir = PROCESSED_DIR / "scenery"
    if scenery_dir.exists():
        spec = json.loads((scenery_dir / "manifest.json").read_text())
        tents = strip(spec["props"]["tent"], scenery_dir)
        tent = tents[0]
        scene.paste(tent, ((cols // 2) * tile - tent.width // 2, 5 * tile - tent.height), tent)

    rug = rugs[0]
    scene.paste(rug, ((cols // 2) * tile - rug.width // 2, 5 * tile), rug)

    merchant_dir = PROCESSED_DIR / "merchant"
    if merchant_dir.exists():
        spec = json.loads((merchant_dir / "manifest.json").read_text())
        idle = Image.open(merchant_dir / "idle.png")
        mw, mh = spec["frameWidth"], spec["frameHeight"]
        art = idle.crop((0, 0, mw, mh))
        scene.paste(art, ((cols // 2) * tile - mw // 2, 6 * tile - mh), art)

    guns_dir = PROCESSED_DIR / "guns"
    gun_frames: list[Image.Image] = []
    if guns_dir.exists():
        spec = json.loads((guns_dir / "manifest.json").read_text())
        sheet = Image.open(guns_dir / "sheet.png")
        gw, gh = spec["frameWidth"], spec["frameHeight"]
        gun_frames = [
            sheet.crop((i * gw, 0, (i + 1) * gw, gh)) for i in range(spec["frames"])
        ]

    # Deliberately IRREGULAR, the way the server places them: a row on a
    # perfect grid is the tell that nobody set these up by hand.
    for index, (tx, dy) in enumerate(((4, 0), (9, -1), (14, 1), (18, 0))):
        table = tables[index]
        x = tx * tile
        y = 9 * tile + dy * 4
        scene.paste(table, (x, y - table.height), table)
        if gun_frames:
            gun = gun_frames[index % len(gun_frames)]
            top = y - table.height + manifest["props"]["table"]["topY"][index]
            scene.paste(gun, (x + table.width // 2 - gun.width // 2,
                              top - gun.height), gun)

    for index, (tx, ty) in enumerate(((2, 7), (11, 4), (20, 7))):
        torch = torches[index % len(torches)]
        base_y = ty * tile
        scene.paste(torch, (tx * tile, base_y - torch.height), torch)
        flame = fire[(index * 3) % len(fire)]
        flame_y = manifest["props"]["torch"]["flameY"][index % len(torches)]
        fy = base_y - torch.height + flame_y
        scene.paste(flame, (tx * tile + torch.width // 2 - flame.width // 2,
                            fy - manifest["effects"]["torchfire"]["anchorY"]), flame)

    scene = scene.resize((scene.width * scale, scene.height * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
