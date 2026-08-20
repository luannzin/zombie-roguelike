#!/usr/bin/env python3
"""Asset pipeline: the MERCHANT'S CAMP — where the night's take gets spent.

Output (assets/processed/store/):
    wagon.png    1 frame,  96x80    PROP   — his cart, and the zone's backdrop
    counter.png  1 frame,  35x22    PROP   — the plank he trades over
    table.png    4 frames, 36x32    PROP   — the round pedestals goods lie on
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
`make_textures.py`'s forest soil, unchanged, because it is the same forest. The
shelter is his own WAGON, which is drawn here — a covered cart is the one piece
of a trader nobody else in this game owns, and it is also where his stock, his
shelter and the answer to "where did all this come from" fit into one
silhouette.

WHAT IS LEFT IS WHAT IS HIS. The tables, the mat under his feet, and the
torches he drove into the ground when he pitched — plus the pool that says
which weapon you are standing at. Everything else on that map belongs to the
forest and comes from the forest's own generators, which is the same rule
`server/app/scenery.py` keeps for every other scene.

THE KIT IS THE STORY, AND IT IS DELIBERATELY NOT INTERACTIVE.
Six tables in a clearing is a shop. Six tables with crates roped up behind
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
picks: the four pedestals are different heights on purpose (a turned column, a
barrel, a cable spool, a stone drum), and a single hardcoded offset would float
one gun and sink another.

MATERIALS COME FROM `make_scenery.py`. The wagon, the counter and the stalls
are built out of the same worked timber, canvas and rope as the crates and the
cabin, for the reason there is only one blood in the game: a shop that shares no
material with the world outside it reads as a different game's asset pack.

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
    CLOTH_PALE,
    CLOTH_RUST,
    LEATHER,
    METAL,
    OUTLINE_WOOD,
    PLANK,
    PLANK_DARK,
    ROPE,
    STONE,
)
from make_textures import (
    DEFAULT_TILE,
    RGBA,
    FLAME,
    PROCESSED_DIR,
    Ramp,
    TRANSPARENT,
    add,
    clamp01,
    ellipse,
    hash01,
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

#: THE SHOP'S OWN TIMBER, and it is lighter than the forest's.
#:
#: `make_scenery`'s `PLANK` is the wood a crate abandoned in the woods is made
#: of: dark, desaturated, and correct for something you find. Everything on
#: this pitch is something a person owns and maintains, and at the size these
#: props are now drawn the dark ramp came out as brown mush — six identical
#: silhouettes with no readable top. This one is warmer and a step brighter at
#: every stop, which is what lets a table read as a TABLE from the door.
WOOD: Ramp = [rgb(c) for c in ("#3c2a1a", "#5f4227", "#8a6236", "#b08349", "#d0a566")]
#: The cloth on the pitch: his mat, the drape over a drum, the wagon's canopy.
LINEN: Ramp = [rgb(c) for c in ("#4a4034", "#6d5f4c", "#94856b", "#bcae91", "#ded3b6")]


def flat(ramp: Ramp, index: int) -> RGBA:
    """One exact ramp step, no dithering.

    `pick` dithers between the two nearest stops, which is right for soil and
    wrong for furniture: a Bayer checker across a table top reads as grime, and
    the shop is the one zone whose whole job is looking looked-after. Every
    surface here is ONE colour with a lit edge and a shadow edge.
    """
    return ramp[max(0, min(len(ramp) - 1, index))]

TILE_TABLE_W = 1.5
TILE_TABLE_H = 1.25


# --- the stalls -------------------------------------------------------------
# SIX SMALL ROUND TABLES, and both words are the point.
#
# ROUND, because the stock stands in the middle of a room and every one of
# these is walked AROUND rather than along: a rectangular board has a front and
# a back and reads wrong from three of the four sides you can approach it from,
# and a disc reads the same from all of them.
#
# SMALL, because they were not. A stall used to be 2.25 tiles across and two
# tall — taller than the gun lying on it and nearly as wide as the merchant —
# which put six objects in the middle of the shop that were bigger than
# anything they were selling. The eye read the furniture first and the goods
# second, which is exactly backwards for a shop, and six of them made a small
# clearing look like a warehouse. At 1.5 x 1.25 the pedestal is a stand for a
# weapon rather than a piece of scenery with a weapon on it.
#
# They are also drawn FLAT — one fill, a lit rim and a shadow row, no per-pixel
# grain. Grain at this size reads as dirt, and a shop is the one place in the
# loop that is supposed to look looked-after.
#
# `topY` is the row the stock rests on and it ships with the art: the four
# pedestals are deliberately different heights, so a single hardcoded offset
# would float one gun and sink another.

#: Half-depth of a table's disc, in pixels. It is the whole reason these read
#: as ROUND rather than as a plank seen edge-on: a top one pixel deep is a
#: line, and one much deeper is a drum seen from the side.
TABLE_DISC_RY = 2.4

#: The row each pedestal's disc sits at, per variant.
TABLE_TOP_Y = (6, 7, 5, 8)


def _disc(
    px,
    w: int,
    h: int,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    ramp,
    step: int,
    _salt: int = 0,
) -> None:
    """A flat elliptical top with a dark rim and a lit back edge.

    The gradient runs front to back rather than left to right, because that is
    where the light in this zone comes from — his fire and the torches are
    around the party, and a disc lit from one side would read as a coin
    standing up. Three tones and no grain: rim, face, and one lit row along the
    far edge, which is the whole reason a 17-pixel ellipse reads as a surface.
    """
    for y in range(max(0, int(cy - ry - 1)), min(h, int(cy + ry + 2))):
        for x in range(max(0, int(cx - rx - 1)), min(w, int(cx + rx + 2))):
            nx = (x - cx) / rx
            ny = (y - cy) / ry
            radius = nx * nx + ny * ny
            if radius > 1.0:
                continue
            if radius > 0.70:
                px[x, y] = flat(ramp, step - 1)      # the edge turning away
            elif ny < -0.35:
                px[x, y] = flat(ramp, step + 1)      # the far edge, catching
            else:
                px[x, y] = flat(ramp, step)


def make_table(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One round stall. Bottom-anchored, outlined, depth-sorted with the party.

    Four pedestals under four discs. They are different objects rather than one
    object at four heights, because six of these stand in one grid and a grid of
    identical furniture is a shop that was generated — the disc is the constant
    the eye reads and the leg is where the variation goes.

    THE LEG IS THICK. A wide top on a thin stalk is a mushroom, which is what
    the first pass of these looked like standing in a forest; a top only a
    little wider than what holds it up is a table.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    cx = (w - 1) / 2.0
    top = TABLE_TOP_Y[variant]
    rx = w / 2.0 - 2.5

    def column(half: float, y0: int, y1: int, ramp, step: int) -> None:
        """A flat vertical solid, lit down its left edge."""
        for y in range(max(0, y0), min(h, y1 + 1)):
            for x in range(int(cx - half), int(cx + half) + 1):
                if not (0 <= x < w):
                    continue
                near = x - cx
                px[x, y] = flat(ramp, step + (1 if near < -half * 0.4 else 0)
                                - (1 if near > half * 0.4 else 0))

    if variant == 0:  # a turned pedestal on a round foot
        column(2.6, top + 1, h - 4, WOOD, 2)
        _disc(px, w, h, cx, h - 3.0, rx * 0.70, 1.8, WOOD, 1)

    elif variant == 1:  # a small barrel, two hoops
        column(4.6, top + 1, h - 2, WOOD, 2)
        for band in (top + 3, h - 4):
            for x in range(w):
                if 0 <= band < h and px[x, band][3]:
                    px[x, band] = flat(METAL, 3)

    elif variant == 2:  # a cable spool stood on its end: the tall one
        column(3.4, top + 2, h - 3, WOOD, 1)
        _disc(px, w, h, cx, h - 2.5, rx * 0.85, 1.8, WOOD, 2)

    else:  # a stone drum with a cloth thrown over its foot
        column(4.2, top + 1, h - 4, STONE, 2)
        for y in range(h - 5, h - 1):
            for x in range(2, w - 2):
                if abs(x - cx) > 4.4 + (y - (h - 5)) * 0.5:
                    continue
                if y >= h - 2 and (x % 4) == 0:
                    continue  # the cloth is cut, and it does not reach the floor
                px[x, y] = flat(LINEN, 3 - (y - (h - 5)) // 2)

    # The top goes on LAST so it sits over whatever the pedestal did, which is
    # what makes the leg read as being under the board rather than beside it.
    _disc(px, w, h, cx, float(top), rx, TABLE_DISC_RY, WOOD, 3)
    outline(img, OUTLINE_WOOD)
    return img


# --- his own kit ------------------------------------------------------------
# Five props standing around the pitch. See the module docstring for why none
# of them opens: this is the one zone in the game where a box is furniture.
#
# THEY SHARE THE TABLES' MATERIALS on purpose. The stalls, the crates and the
# shelf are the same worked timber, canvas and rope, so they read as one
# person's belongings rather than as five things that happened to land in one
# clearing.

TILE_KIT_W = 22
TILE_KIT_H = 20


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
        box(1, h - 10, 11, h - 1, WOOD, 0.62, 11)
        box(11, h - 8, 20, h - 1, WOOD, 0.54, 23)
        box(3, h - 17, 12, h - 11, WOOD, 0.68, 37)
        # The rope over the top box. It is the entire "shut" statement, and it
        # is why this reads as stock rather than as three things to open.
        for x in range(3, 13):
            if 0 <= x < w:
                px[x, h - 14] = pick(ROPE, 0.8 - hash01(x, 0, 41) * 0.2, x, h - 14)
        for y in range(h - 17, h - 11):
            if 0 <= y < h:
                px[7, y] = pick(ROPE, 0.72, 7, y)

    elif variant == 1:  # a barrel with rods and tools fanned out of it
        cx = 8
        for y in range(h - 13, h):
            span = 6 - abs(y - (h - 7)) // 6
            for x in range(cx - span, cx + span):
                hoop = y in (h - 12, h - 7, h - 2)
                curve = 1.0 - abs(x - cx + 0.5) / (span + 1.0)
                value = 0.3 if hoop else 0.32 + curve * 0.48
                px[x, y] = pick(WOOD, value - hash01(x, y, 71) * 0.1, x, y)
        for y in (h - 12, h - 7, h - 2):
            for x in range(cx - 6, cx + 6):
                if 0 <= x < w and px[x, y][3]:
                    px[x, y] = pick(METAL, 0.52 + hash01(x, y, 19) * 0.2, x, y)
        # The rods. The one vertical in an otherwise low, heavy piece — and
        # what stops the barrel reading as one more thing you can break.
        for index, lean in enumerate((-3, -1, 2, 4)):
            for step in range(7 + index % 3):
                x = cx + lean + (step * (1 if lean > 0 else -1)) // 3
                y = h - 13 - step
                if 0 <= x < w and 0 <= y < h:
                    px[x, y] = pick(METAL, 0.6 - step * 0.02, x, y)

    elif variant == 2:  # a rack of spare barrels and stocks
        for foot in (3, w - 5):  # the A-frame
            for step in range(h - 6):
                y = 4 + step
                x = foot + (step * (1 if foot < w // 2 else -1)) // 6
                if 0 <= x < w:
                    px[x, y] = pick(WOOD, 0.58 - step * 0.012, x, y)
        for x in range(3, w - 3):  # the crossbar
            px[x, 9] = pick(WOOD, 0.7, x, 9)
        for index, slot in enumerate(range(5, w - 5, 5)):
            length = min(h - 7, 10 + (index % 3) * 3)
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
                px[x, y] = pick(WOOD, lit - hash01(x, y, 53) * 0.16, x, y)
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
        # reads as CLOSED from across the clearing.
        for y in range(h - 13, h - 9):
            px[w // 2, y] = pick(METAL, 0.85, w // 2, y)
        box(w // 2 - 2, h - 10, w // 2 + 1, h - 7, METAL, 0.86, 7)
        # The tarp thrown half over it, hanging off the back-left corner. One
        # soft shape against four hard ones, so the group has a silhouette.
        for y in range(h - 17, h - 9):
            for x in range(1, 13 - (y - (h - 17))):
                fold = math.sin(x * 0.8 + y * 0.3) * 0.1
                px[x, y] = pick(LINEN, 0.56 + fold - hash01(x, y, 83) * 0.12, x, y)

    outline(img, OUTLINE_WOOD)
    return img


# --- the wagon --------------------------------------------------------------
# THE BACKDROP THE PITCH IS ARRANGED AGAINST, and the answer to "who is this
# man and why is he in a forest full of the dead".
#
# A tent answered half of it: somebody is camped out here. A WAGON answers the
# rest — he did not walk here with six tables on his back, he DRIVES, which
# means he was somewhere else last week and will be somewhere else next week,
# and the reason he is worth finding is that he is the only thing in the run
# that moves between the places the party cannot reach.
#
# IT USED TO BE A HEARSE AND IT IS NOT ANY MORE. The first version hung three
# bone masks on a cord along the flank and laid TWO COVERED BODIES with their
# boots out at the front wheel — the argument being that the party should work
# out where the stock comes from on their own. The argument was fine and the
# result was not: the shop is the one beat of the loop that exists to be a
# relief from the night, and the biggest sprite in it was a cart with corpses
# under a tarp. A player who has just walked out of a dark wood does not need
# the safe room to be quietly menacing as well. So the cord carries LANTERNS
# now, the wheel carries CRATES, and what the wagon says is "somebody lives out
# of this thing" instead of "somebody loots bodies for a living".
#
# IT IS ONE FRAME. The wagon does not animate, does not open and does not sell:
# everything the party may touch stands in front of it.

TILE_WAGON_W = 4.5
TILE_WAGON_H = 3.5

#: A lantern hanging off the front bow, and the three on the flank line. Warm,
#: so they still read as flames under the darkness multiply even though the
#: additive fire is drawn separately from the torches.
EMBER: Ramp = [rgb(c) for c in ("#3a1608", "#7a3410", "#b3591a", "#e08a2c")]


def make_wagon(w: int, h: int, rng: random.Random) -> Image.Image:
    """His cart. Bottom-anchored, outlined, depth-sorted with the party."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()

    # Everything below is authored against a 96x80 frame and scaled, so the
    # composition survives a change of tile size without being re-eyeballed.
    sx = w / 96.0
    sy = h / 80.0

    def X(v: float) -> int:
        return int(round(v * sx))

    def Y(v: float) -> int:
        return int(round(v * sy))

    def put(x: int, y: int, ramp, step: int) -> None:
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = flat(ramp, step)

    def box(x0: int, y0: int, x1: int, y1: int, ramp, step: int) -> None:
        for y in range(max(0, y0), min(h, y1 + 1)):
            for x in range(max(0, x0), min(w, x1 + 1)):
                edge = x in (x0, x1) or y in (y0, y1)
                put(x, y, ramp, step - (1 if edge else 0))

    # 1. THE CANOPY. An arch of cream canvas over six hoops, drawn as darker
    #    columns THROUGH the cloth rather than as arcs behind it: at this scale
    #    a rib you can see the shape of is a rib that has become the subject.
    bed_top = 34.0
    for xv in range(18, 97):
        span = abs(xv - 57.0) / 39.0
        if span > 1.0:
            continue
        crown = 9.0 + span * span * 15.0
        # A shallow sag between the hoops. Without it the arch is an extruded
        # curve and the canvas reads as sheet metal.
        crown += math.sin(xv * 0.52) * 0.9
        rib = (xv % 13) in (0, 1)
        for yv in range(int(crown), int(bed_top) + 1):
            down = (yv - crown) / max(bed_top - crown, 1.0)
            step = 4 if down < 0.25 else 3 if down < 0.7 else 2
            put(X(xv), Y(yv), LINEN, step - (2 if rib else 0))
        # The eave: the cloth hangs a little past the boards it is lashed to.
        put(X(xv), Y(bed_top + 1), LINEN, 1)

    # 2. THE BED. Worked planks with three seams and a rail along the top.
    box(X(20), Y(34), X(94), Y(58), WOOD, 2)
    for seam in (40, 46, 52):
        for xv in range(21, 94):
            put(X(xv), Y(seam), WOOD, 1)
    for xv in range(20, 95):
        put(X(xv), Y(35), WOOD, 4)

    # 3. THE LANTERN LINE, strung along the flank under the eave. Three lamps
    #    and a canteen on one cord — the cord is what makes them read as
    #    somebody's belongings rather than as things stuck to a wall, and a row
    #    of small warm lights is the friendliest thing a silhouette can carry.
    for xv in range(24, 55):
        put(X(xv), Y(38 + int(math.sin((xv - 24) * 0.25) * 1.2)), ROPE, 4)
    for mx, drop in ((28, 41), (36, 42), (44, 41)):
        box(X(mx - 2), Y(drop), X(mx + 2), Y(drop + 7), METAL, 2)
        box(X(mx - 1), Y(drop + 2), X(mx + 1), Y(drop + 5), EMBER, 3)
    # A canteen on the same cord: not a lamp, so the line reads as a line of
    # things rather than as a string of identical bulbs.
    box(X(50), Y(41), X(54), Y(46), METAL, 3)

    # 4. THE GUN RACK, on the near flank. Three leaning barrels with wooden
    #    stocks — the one thing on this cart the party can actually buy, so it
    #    is the detail placed at eye height and dead centre of the sprite.
    for index, foot in enumerate((62, 70, 78)):
        lean = -0.22 - (index % 2) * 0.08
        for step in range(18):
            yv = 58 - step
            xv = foot + lean * step
            put(X(xv), Y(yv), WOOD if step < 6 else METAL, 3)
            put(X(xv + 1), Y(yv), WOOD if step < 6 else METAL, 1)
        # The stock's cheek, which is what stops three vertical bars reading as
        # a fence.
        for yv in range(53, 59):
            put(X(foot - 1), Y(yv), WOOD, 3)

    # 5. WHEELS AND AXLE. Spoked, because a solid disc at this size is a bin
    #    lid — the spokes are the only thing that says the cart rolls.
    box(X(34), Y(59), X(82), Y(62), METAL, 1)
    for hub_x in (36.0, 80.0):
        for yv in range(48, 77):
            for xv in range(int(hub_x - 13), int(hub_x + 14)):
                dx = (xv - hub_x) / 12.4
                dy = (yv - 62.0) / 12.4
                radius = math.hypot(dx, dy)
                if radius > 1.0:
                    continue
                if radius > 0.80:
                    put(X(xv), Y(yv), WOOD, 1)           # the felloe
                    continue
                angle = math.atan2(dy, dx)
                spoke = abs(math.sin(angle * 4.0)) < 0.16
                if radius < 0.20:
                    put(X(xv), Y(yv), METAL, 4)          # the hub
                elif spoke:
                    put(X(xv), Y(yv), WOOD, 3)
    # The iron tyre, one ring outside the felloe, so the wheel has an edge that
    # is not the keyline.
    for hub_x in (36.0, 80.0):
        for step in range(64):
            angle = step / 64.0 * math.tau
            put(X(hub_x + math.cos(angle) * 12.0), Y(62.0 + math.sin(angle) * 12.0),
                METAL, 3)

    # 6. HIS LUGGAGE at the front wheel: two crates and a barrel, roped shut.
    #    This is where the covered bodies were — see the section comment. Same
    #    job (the cart is loaded, somebody lives out of it), opposite mood.
    box(X(2), Y(64), X(18), Y(78), WOOD, 2)
    for yv in range(65, 78, 6):
        for xv in range(2, 19):
            put(X(xv), Y(yv), ROPE, 3)
    box(X(19), Y(69), X(31), Y(78), WOOD, 3)
    for xv in range(19, 32):
        put(X(xv), Y(73), ROPE, 3)

    # 7. THE LANTERN on the front bow. Small, warm, and the light that says
    #    somebody is home.
    for yv in range(16, 22):
        put(X(20), Y(yv), METAL, 2)
    box(X(17), Y(22), X(23), Y(30), METAL, 2)
    box(X(18), Y(24), X(22), Y(28), EMBER, 3)

    outline(img, OUTLINE_WOOD)
    return img


# --- his counter ------------------------------------------------------------


TILE_COUNTER_W = 1.9
TILE_COUNTER_H = 1.25


def make_counter(w: int, h: int, rng: random.Random) -> Image.Image:
    """The plank he trades over. Bottom-anchored, outlined.

    A COUNTER AND NOT A STALL. The six round tables in the middle of the
    clearing are the stock; this is where the man himself stands, and it is
    deliberately the plainest object in the zone — a board on two trestles with
    a ledger, a scale and a lamp on it. Everything about the pitch that is
    supposed to catch the eye is behind him on the wagon or in front of him on
    the grid, and a counter competing with either would be a third thing to
    read at the exact moment somebody is trying to decide what to buy.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()

    def put(x: int, y: int, ramp, value: float, salt: int = 3) -> None:
        if 0 <= x < w and 0 <= y < h:
            px[x, y] = pick(ramp, clamp01(value - hash01(x, y, salt) * 0.12), x, y)

    top = 4
    for y in range(top, top + 3):
        for x in range(w):
            lit = 0.88 if y == top else (0.66 if y == top + 1 else 0.42)
            put(x, y, WOOD, lit, 61)
    # Two trestles, splayed, and a cross-brace. Splayed rather than vertical
    # because a board on two straight posts is a table and a board on two
    # splayed ones is a thing somebody set up this morning.
    for foot in (3, w - 5):
        for step in range(h - top - 4):
            yv = top + 3 + step
            spread = step // 3
            for xv in (foot - spread, foot + 1 + spread):
                put(xv, yv, WOOD, 0.52 - step * 0.02, 67)
    for x in range(2, w - 2):
        put(x, h - 5, PLANK_DARK, 0.6, 71)
    # The ledger, the scale and the tin lamp, in that order left to right.
    for x in range(4, 11):
        put(x, top - 1, CLOTH_PALE, 0.62 - (x - 4) * 0.02, 73)
        put(x, top - 2, CLOTH_PALE, 0.5, 73)
    for x in range(w // 2 - 3, w // 2 + 4):
        put(x, top - 1, METAL, 0.58, 79)
    put(w // 2, top - 4, METAL, 0.5, 79)
    put(w // 2, top - 3, METAL, 0.5, 79)
    for x in range(w - 8, w - 4):
        for y in range(top - 5, top - 1):
            put(x, y, METAL, 0.46, 83)
    put(w - 6, top - 3, EMBER, 0.8, 83)
    put(w - 7, top - 3, EMBER, 0.62, 83)

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
        # The air around it. WEAK AND TIGHT, and it used to be neither: at
        # 8.5x6.5 and 0.30 this was a soft halo the width of the whole frame,
        # which S14 rules out for emissive material ("flat step-4 core + one
        # step-3 halo ring, no glow blur") and which eleven torches ringing one
        # clearing then ADD together — the shop came out as a lit room with
        # fires drawn on it rather than as a dark clearing eleven fires are
        # holding open. The pool of light this throws on the ground is the
        # scene light's job (`drawSceneLights`); this is only the air right at
        # the flame.
        ellipse(field, cx, anchor - 2.5, 6.2, 4.8, 0.19)

        for step in range(4):  # sparks, on the same phase so they loop too
            sway = math.sin(phase + step * 1.7)
            rise = ((index + step * 3) % frames) / frames
            add(field, int(round(cx + sway * 3.0)), int(anchor - 4 - rise * 11),
                0.5 * (1.0 - rise))

        img = Image.new("RGBA", (w, h), TRANSPARENT)
        # `gain` was 1.15 — over 1, so the field clipped to the top of FLAME
        # across the whole body and the fire resolved as a white pear with a
        # warm rim. At 1.0 the ramp's own steps survive all the way up, which is
        # what makes a flame read as fire rather than as a bulb.
        resolve(field, img, FLAME, floor=0.09, tone=0.88, gain=1.0)
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

    wagon_w, wagon_h = round(tile * TILE_WAGON_W), round(tile * TILE_WAGON_H)
    wagon = make_wagon(wagon_w, wagon_h, random.Random(args.seed + 1300))
    pack([wagon], wagon_w, wagon_h).save(out_dir / "wagon.png")

    counter_w = round(tile * TILE_COUNTER_W)
    counter_h = round(tile * TILE_COUNTER_H)
    counter = make_counter(counter_w, counter_h, random.Random(args.seed + 1400))
    pack([counter], counter_w, counter_h).save(out_dir / "counter.png")

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
            # HIS CART, one frame, parked on the west rim of the clearing. The
            # biggest sprite in the zone and the one that says where the stock
            # comes from — see the section comment above `make_wagon`.
            "wagon": {
                "file": "wagon.png", "frameWidth": wagon_w,
                "frameHeight": wagon_h, "frames": 1, "sway": 0,
            },
            # The plank he stands behind. Deliberately the plainest thing here.
            "counter": {
                "file": "counter.png", "frameWidth": counter_w,
                "frameHeight": counter_h, "frames": 1, "sway": 0,
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
        f"wagon 1x{wagon_w}x{wagon_h}, "
        f"counter 1x{counter_w}x{counter_h}, "
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
    """A mock-up of the pitch: soil, his cart, the mat, the man, the stock.

    Not shipped, and not how the client composes the scene — this exists so the
    art can be judged as a place rather than as eight sheets in a folder. The
    ground is pulled from the OTHER generator on purpose: this shop's whole
    argument is that it is made of the same forest everything else is, and a
    preview on a flat background could not show that.

    It mirrors `server/app/store.py`'s composition — the man in the MIDDLE, the
    cart behind him, his counter in front and two rows of three stalls in front
    of that — because a preview that arranges the art differently from the zone
    is a preview of a shop that does not exist.
    """
    manifest = json.loads((out_dir / "manifest.json").read_text())
    cols, rows = 22, 15
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

    wagon = strip(manifest["props"]["wagon"], out_dir)[0]
    scene.paste(
        wagon,
        ((cols // 2 - 3) * tile - wagon.width // 2, 4 * tile - wagon.height),
        wagon,
    )

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

    counter = strip(manifest["props"]["counter"], out_dir)[0]
    scene.paste(
        counter,
        ((cols // 2) * tile - counter.width // 2, 7 * tile - counter.height),
        counter,
    )

    # THE GRID, exactly as `store.STALL_COLS` / `STALL_ROWS` lay it out: three
    # across and two deep, in front of the man, on his own axis.
    index = 0
    for row in (9, 12):
        for col in (-4, 0, 4):
            table = tables[index % len(tables)]
            x = (cols // 2 + col) * tile - table.width // 2
            y = row * tile
            scene.paste(table, (x, y - table.height), table)
            if gun_frames:
                gun = gun_frames[index % len(gun_frames)]
                top = y - table.height + manifest["props"]["table"]["topY"][
                    index % len(tables)
                ]
                scene.paste(gun, (x + table.width // 2 - gun.width // 2,
                                  top - gun.height), gun)
            index += 1

    for index, (tx, ty) in enumerate(((1, 8), (20, 8), (11, 14))):
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
