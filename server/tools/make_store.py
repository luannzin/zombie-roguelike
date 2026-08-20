#!/usr/bin/env python3
"""Asset pipeline: the MERCHANT'S SHOP — where the night's take gets spent.

Output (assets/processed/store/):
    brick.png     4 frames, 16x24   PROP   — masonry: 2 plain, 2 trimmed
    tilefloor.png 4 frames, 16x16   GROUND — the laid brick floor, baked
    counter.png   3 frames, 16x22   PROP   — the L he trades over
    shelf.png     3 frames, 26x30   PROP   — his stock on the wall behind him
    crate.png     3 frames, 20x24   PROP   — decoration, and none of it opens
    lamp.png      2 frames, 16x28   PROP   — oil lamps on stands, the room's light
    table.png     4 frames, 24x20   PROP   — the pedestals goods lie on
    kit.png       5 frames, 22x32   PROP   — his own gear, out in the yard
    wagon.png     1 frame,  72x56   PROP   — his cart, parked in the yard
    torch.png     2 frames, 12x30   PROP   — the posts lighting the yard
    rug.png       3 frames, 48x32   DECAL  — the mats on the shop floor
    torchfire.png 12 frames, 20x40  VFX    — loop, warm fire in a torch head
    lampfire.png  12 frames, 14x20  VFX    — loop, the same fire behind glass
    glow.png       8 frames, 32x16  VFX    — loop, under a weapon you are near
    manifest.json

IT IS A BUILDING NOW, AND THAT REVERSES THIS FILE'S OLDEST DECISION.
The shop was an interior once, it was thrown out for being one, and this is the
argument for putting it back. The old interior was wrong because it was the
WHOLE ZONE: the party walked out of a corridor and were already inside, so the
game had cut to a menu rather than taken them somewhere. What is here now is
two places with a walk between them — an outdoor APRON where the night's
platforms come down, his cart parked on it and his fire beside that, and then a
brick SHOP at the far end of the yard that the party can see from the moment
they arrive and have to cross the yard to reach. A door you walk up to is the
opposite of a cut.

And the building buys the two things a clearing never could. LIGHT: five lamps
on chains over a closed room is even, calm, arranged light, where a clearing
could only ever be a ring of torches around a dark middle. And a BACK WALL:
a counter fitted into a corner has a behind, so the trader has a pocket that is
his — visible, and not walkable — with his shelves on the wall over his
shoulder. Out in the open his "back" was a parked cart and everything else was
scattered round a rim.

THE ART RULE FOR THIS ZONE IS UNCHANGED AND IT IS THE IMPORTANT ONE.
It may be poor, worn and improvised; IT MAY NOT BE GRIM. This is the one beat
of the loop that exists as a relief from the night. Nothing here is bloodied,
nothing is a body, nothing is a bone. Chipped brick, a scuffed floor, a mat
somebody has walked a hole in — that is the register.

EVERYTHING IS BANDED ON THE SHARED CAMERA. `make_objects.py` owns the
projection (`SLOPE`), the plane table (`TOP` / `FRONT` / `SIDE`), the flat-step
painter (`tone`) and the solid toolkit (`box`, `cap`, `billet`, `stone`,
`shadow`). Every volume in this folder is built out of those, for the same
reason a fence post and a crate are: a prop lit on its own slope with its own
steps is a prop from a different game standing next to one from this one. The
ramps come from `make_textures.material_ramp`, which is S11's law as four
numbers rather than as fifteen hand-picked hex triples that may or may not
hue-shift the way the rest of the world does.

WHAT THE OLD SHADING WAS AND WHY IT HAD TO GO. Every prop in this file used to
be a FRONT ELEVATION: a flat face with a value ramp across it, dithered
through `pick`, with no top surface anywhere. That reads as a drawing of a
table rather than as a table, it has no ground plane to plant it on, and it is
the exact failure the crates, the guns and the loot atlas each had before their
own pass. See PIXEL-ART-DIRECTION.md §2, §3, §7.

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

THE BRICK SHEET ASKS ONE QUESTION AND IT IS NOT AN AUTOTILE MASK. Is there
masonry to the NORTH of this tile? If there is, the tile is in the body of the
wall and draws one tile of face. If there is not, it is on the wall's top edge
and gets the TRIM as well — the bright lid that is the only part of a wall
leaving its own footprint. That single test makes the back wall a band with a
lit top, the side walls solid vertical bands, and the front wall something the
camera sees over, with no case for any of the three. Two earlier cuts got this
wrong in two different ways; both are written up over `make_brick`.

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

import make_objects as objects
from make_objects import FRONT, SIDE, SLOPE, TOP, billet, box, cap, shadow, stone, tone
from make_scenery import (
    LEATHER,
    OUTLINE_WOOD,
    ROPE,
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
    material_ramp,
    outline,
    pack,
    pick,
    resolve,
    rgb,
)

# --- palette ----------------------------------------------------------------
# SIX STEPS EVERYWHERE, because `tone` indexes the shared plane table and that
# table is `TOP = 5` / `FRONT = 3` / `SIDE = 1`. A five-step ramp collapses the
# top plane into the specular and the object loses the difference between "lit"
# and "the brightest thing on it" — see `make_textures.material_ramp`.
#
# THE SHOP IS THE ONE WARM PLACE IN THE GAME AND THE PALETTE IS HALF OF THAT.
# Every other generator here is tuned dark, because the client multiplies a
# darkness pass over it and a bright texture leaves the lantern nothing to add.
# This zone has an AMBIENT FLOOR under that pass (`zones.STORE_AMBIENT`), so its
# materials can afford to sit a stop higher and warmer than the forest's — and
# they have to, or the one lit room in the game comes out the same value as the
# woods outside it.
#
# BUT THE CEILING IS STILL LOW, AND THAT IS THE MISTAKE THIS BLOCK ALREADY MADE
# ONCE. The first pass ran these ramps out to `hi` around 0.70-0.80 on the
# argument that a lit room should be light. What came out was a set where every
# TOP plane was near-white against a FRONT plane in the middle of the ramp: the
# top of a counter read as a separate pale slab floating over its own body, a
# table read as a mushroom, and a shelf board read as a tan rhombus with no
# bracket under it. S13 says step 1 to step 4 spans about 55 L, not 100, and
# every scenery ramp already in this game tops out near 0.43 — `make_scenery`'s
# CANVAS, the lightest material in the forest, ends at #847457. The shop sits
# just above that and no higher. The ROOM is bright because the LIGHT is; the
# materials in it are still made of the same world.

#: THE MASONRY, and it is DARKER THAN THE FLOOR IT STANDS ON.
#:
#: THAT ORDER WAS BACKWARDS FOR A PASS AND IT IS THE WHOLE READ OF THE ROOM.
#: The first cut had the wall lighter than the floor on the reasoning that a
#: wall is a lit vertical surface. It is not, at this camera: the key is at 60
#: degrees of elevation, so the plane facing UP catches it and the planes
#: facing SIDEWAYS do not. A room drawn the other way round has no floor in it
#: — the eye reads the lightest large field as the ground and the whole shop
#: turns inside out. Every reference for this zone shows the same thing: a dark
#: band of wall, a warmer floor inside it, and a bright trim line where the two
#: meet.
BRICK: Ramp = material_ramp(7.0, 0.42, 0.030, 0.185, steps=6)
#: The mortar between the courses. Not a line — a VALUE STEP under the brick's
#: own face (S6: interior form breaks get no line).
MORTAR: Ramp = material_ramp(20.0, 0.14, 0.06, 0.30, steps=6)
#: THE TRIM ON TOP OF THE WALL, and it is its own ramp rather than the top of
#: the brick's. WARM STONE, not timber: at a tan hue and half a tile deep it
#: came out as a plank laid along the top of every wall, which is a completely
#: different building.
#:
#: The cap is the one plane in the room turned at the sky, so it is the one
#: place the key light lands square — and it has to be lighter than the FLOOR
#: as well as than the wall, or the room has no lid on it and the masonry
#: reads as a dark rectangle painted on the ground. Running it off the brick
#: ramp's own top step could not do that without dragging the wall's face up
#: with it, which is what put the two surfaces four points apart and made the
#: whole shop one continuous field of brick.
TRIM: Ramp = material_ramp(17.0, 0.26, 0.09, 0.40, steps=6)
#: THE LAID FLOOR: warm, red, and QUIET.
#:
#: It is the largest surface in the game and almost none of it is ever looked
#: at directly, which is the entire brief. It sits between the wall (under it)
#: and the counter (well over it), it is warm so the room feels heated rather
#: than damp, and its internal contrast is deliberately tiny — see
#: `make_tilefloor` on why the module is a SQUARE and why the wear is three
#: scuffs and not a texture.
TILE_RAMP: Ramp = material_ramp(3.0, 0.38, 0.085, 0.36, steps=6)

#: THE SHOP'S OWN TIMBER, and it is the BRIGHTEST MATERIAL IN THE GAME.
#:
#: `make_scenery`'s `PLANK` is the wood a crate abandoned in the woods is made
#: of: dark, desaturated, and correct for something you FIND. Everything the
#: trader owns is something a person maintains, and at the size these props are
#: drawn the forest ramp came out as brown mush — six identical silhouettes
#: with no readable top.
#:
#: IT RUNS ALL THE WAY UP BECAUSE THE COUNTER IS THE FOCAL MASS. S13 gives the
#: focal mass the full five-step ramp and leaves the background sub-masses on
#: steps 1-3; in this room the counter and the tables ARE the focal mass —
#: they are what the party walked in to look at — and everything else (the
#: walls, the floor, his crates) is background. A pale cream counter against a
#: dark red floor is the single strongest thing in the frame and it is the
#: first thing the eye lands on from the door, which is exactly right. The
#: previous cut topped out at 0.46 and the counter disappeared into its own
#: room.
WOOD: Ramp = material_ramp(33.0, 0.28, 0.13, 0.74, steps=6)
#: The same timber, weathered: the wagon's body, his crates, a torch post.
WOOD_WORN: Ramp = material_ramp(24.0, 0.30, 0.06, 0.38, steps=6)
#: Iron: torch baskets, lamp chains, the bands on a crate.
IRON: Ramp = material_ramp(228.0, 0.09, 0.07, 0.40, steps=6)
#: BRASS, and it is the zone's ACCENT (S12: one hue, under 8% of pixels). It
#: appears on exactly three things — the lamps' collars, the counter's edging
#: and the strongbox's lock — because those are the three things in the room
#: that are supposed to look cared for.
BRASS: Ramp = material_ramp(43.0, 0.52, 0.10, 0.56, steps=6)
#: The cloth on the pitch: the wagon's canopy, a drape over a drum.
LINEN: Ramp = material_ramp(40.0, 0.20, 0.12, 0.50, steps=6)
#: LAMP GLASS, and it is WARM. Glass in this game is cold everywhere else —
#: `make_scenery.GLASS` is a blue-grey, because what it is usually covering is
#: a dial or a dead window. A lantern is the opposite: it is glass with a FLAME
#: behind it, so it is amber before anything additive is drawn over it. The
#: first cut used the cold ramp and five blue beads on chains read as potions
#: hanging over a brick room.
GLASS: Ramp = material_ramp(38.0, 0.30, 0.14, 0.60, steps=6)
#: The cold glass, for the jars on his shelves — those really are dead
#: containers on a wall and they are not supposed to compete with the lamps.
GLASS_COLD: Ramp = material_ramp(196.0, 0.20, 0.11, 0.44, steps=6)

#: THE MATS, one ramp each. Three DIFFERENT dyes rather than three shades of
#: one, because they are laid on three different lines the party walks and the
#: only thing telling them apart at this pitch is hue.
RUG_RED: Ramp = material_ramp(6.0, 0.46, 0.08, 0.38, steps=6)
RUG_BLUE: Ramp = material_ramp(206.0, 0.34, 0.08, 0.35, steps=6)
RUG_GOLD: Ramp = material_ramp(38.0, 0.44, 0.09, 0.40, steps=6)

#: Coals sitting in a torch head that is not currently being drawn over by its
#: own flame. Warm, so an unlit frame still reads as something that burns.
COALS: Ramp = [rgb(c) for c in ("#3a1608", "#6b2a0d", "#9c4415", "#c96a22")]

#: The keyline for everything in this folder. `make_objects`' wood outline —
#: NOT black (S6), and shared with the crates so a counter and a barrel are
#: bounded by the same line.
OUTLINE = OUTLINE_WOOD
#: Masonry gets its own, one hue cooler: brick outlined in the wood line reads
#: as a painted flat, because the line is warmer than the surface it bounds.
OUTLINE_BRICK = rgb("#150c09")


# --- the masonry ------------------------------------------------------------
# THE WALL IS TWO TILES TALL AND STANDS ON ONE, and that is the whole trick
# that makes a roofless building read as a building.
#
# The grid says a tile is a wall. The sprite drawn on it is 16 wide and 32
# tall, bottom-anchored on that tile, so a metre of masonry rises out of the
# footprint into the tile ABOVE — exactly the way a TREE's canopy does. The
# camera looks down at ~55 degrees, so what the player sees of the north wall
# is a tall face with a lit cap on top of it, and what they see of the east and
# west walls is mostly cap. That difference is what gives the room a back
# without anybody drawing a roof, and it is the reason the party can stand
# outside and see the shop's inside at the same time.
#
# COURSES ARE A VALUE STEP, NEVER A LINE (S6). A brick wall drawn with dark
# mortar lines is a wall with a grid on it; a brick wall where each course is
# offset half a brick and every brick is one of three ramp steps is masonry.
# The variation is a coarse per-brick hash, not per-pixel noise (S5) — one
# brick is one flat colour.
#
# AND THERE IS NO AUTOTILE. Wall tiles are depth-sorted north to south like
# every other prop, so the tile in front of one already covers its face — the
# occlusion an eight- or sixteen-way mask would compute is the draw order,
# for free. See `make_brick`.

#: How tall a wall sprite is, in tiles. The extra half-tile is the TRIM.
TILE_WALL_H = 1.3125
#: How far the TRIM rises above the wall's own tile, in pixels at a 16px tile.
#: It is the top surface of the masonry — the one plane in the room turned at
#: the sky — and it is the only part of a wall that leaves its own footprint.
#: KEPT THIN. At half a tile it stopped being the edge of a wall and became a
#: band in its own right, wide enough to read as a separate object sitting on
#: the masonry. What it has to say is "the wall stops here", and a few pixels
#: of lit stone say that.
WALL_CAP = 5
#: One brick, in pixels. Wide and short — a course that reads at 16px across
#: cannot be more than four courses per tile or it turns to stripes.
BRICK_W = 8
BRICK_H = 4


def _brick_step(x: int, y: int, salt: int) -> int:
    """Which ramp step this brick's FACE is on. Per BRICK, never per pixel.

    Bricks are fired in batches and no two come out the same, which is the one
    piece of texture masonry gets for free. Three steps around `FRONT`: most
    bricks sit on the base plane, a few are a stop up, a few a stop down. S5's
    rule holds — the cluster is the whole brick, so the wall reads as courses
    rather than as grain.
    """
    course = y // BRICK_H
    # Every other course is offset half a brick. Without it the wall is a grid
    # of squares, which is tile, not brick.
    slot = (x + (BRICK_W // 2 if course % 2 else 0)) // BRICK_W
    roll = hash01(slot, course, salt)
    if roll > 0.86:
        return 1
    if roll > 0.62:
        return -1
    return 0


def _is_mortar(x: int, y: int) -> bool:
    """Is this pixel in the joint between two bricks?

    ONE PIXEL, on the bottom and the right of each brick only. A joint drawn on
    all four sides doubles up where two bricks meet and comes out 2px, which at
    this scale is a mortar wall with brick decoration on it.
    """
    course = y // BRICK_H
    if y % BRICK_H == BRICK_H - 1:
        return True
    slot_x = x + (BRICK_W // 2 if course % 2 else 0)
    return slot_x % BRICK_W == BRICK_W - 1


def make_brick(w: int, h: int, variant: int, crown: bool) -> Image.Image:
    """One wall tile: a full tile of brick face, and a TRIM above it or not.

    THIS IS THE THIRD CUT AND THE OTHER TWO ARE WORTH WRITING DOWN, because
    both were reasonable and both produced a wall nobody would call a wall.

    ATTEMPT ONE was a south-neighbour mask, which turned out to be computing
    the draw order the renderer already knows. ATTEMPT TWO deleted the mask and
    gave every tile a two-tile block: a trim on top of a tall face. That is
    right for a wall run seen END ON — the back wall, one row of tiles, reading
    as a band with a lit lid. It is wrong for a run going AWAY from the camera.
    The side walls are a column of tiles, each sprite covers the face of the
    one behind it but NOT its trim, so what came out was a dashed line of
    bright rungs down both sides of the room with dark gaps between them —
    a ladder, not a wall.

    THE FIX IS TO ASK WHICH TILES ARE ON THE MASONRY'S TOP EDGE. A wall tile's
    face fills its OWN tile and never more; the TRIM is the top surface of the
    whole mass, so it belongs only to the tiles with no masonry to the NORTH of
    them. On the back wall that is every tile, and it comes out as a band with
    a lit lid. On a side wall it is only the corner, and the rest is solid
    face — a continuous vertical band, which is what a wall running away from
    you looks like. On the front wall it is every tile again, low, and the
    camera looks over it into the room.

    One question, three correct answers, and the same two frames per wear
    variant the ladder version needed.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    base = h - 1
    face_top = h - w   # the sprite's bottom square: this tile and no more

    # THE FACE. Exactly one tile of it, so a run of them tiles seamlessly in
    # both directions with nothing to line up.
    for y in range(face_top, base + 1):
        for x in range(w):
            if _is_mortar(x, y):
                px[x, y] = tone(MORTAR, FRONT - 1, x, y)
                continue
            step = FRONT + _brick_step(x, y, 4001 + variant * 37)
            px[x, y] = tone(BRICK, step, x, y)

    # Variant 1 carries a patch of older, darker brick — S15's "bite negative
    # space into the edge" applied to a surface. The COURSES still line up with
    # variant 0, because a run mixes the two and a sheared course is a wall
    # that fell over.
    if variant == 1:
        for y in range(face_top + 4, min(base, face_top + 11)):
            for x in range(w - 6, w - 1):
                if px[x, y][3] and hash01(x, y, 4103) > 0.30:
                    px[x, y] = tone(BRICK, SIDE + 1, x, y)

    if crown:
        # THE TRIM. Drawn off its own ramp, not off the brick's top steps: it
        # has to be lighter than the FLOOR as well as than the wall, or the
        # room has no lid on it and the masonry reads as a dark rectangle
        # painted on the ground.
        for y in range(face_top - WALL_CAP, face_top):
            for x in range(w):
                step = TOP - 1 if y > face_top - WALL_CAP else TOP - 2
                # The joints ALONG the wall: one line per brick width and no
                # courses. Up here the camera looks down the LENGTH of a
                # course, so the pattern it can see runs one way only. Running
                # the face's test over this plane put a joint every four rows
                # along the top of the wall — masonry seen from two angles at
                # once.
                if (x + variant * 3) % BRICK_W == BRICK_W - 1:
                    step -= 2
                px[x, y] = tone(TRIM, step, x, y)
        # The terminator, and it is the DARKEST row on the sprite rather than a
        # middle step: what sells a bright lid sitting ON a dark wall is the
        # shadow the lid throws down the top course, not a smooth handover.
        for x in range(w):
            px[x, face_top] = tone(BRICK, SIDE, x, face_top)

    # AMBIENT OCCLUSION at the contact (S10): a darkening band INSIDE the
    # sprite where the wall meets the floor. It is the difference between a
    # wall standing on the ground and a wall pasted over it.
    for x in range(w):
        px[x, base] = tone(BRICK, SIDE, x, base)
    return img


def make_tilefloor(size: int, variant: int, rng: random.Random) -> Image.Image:
    """One tile of the shop's laid floor. FLAT: no outline, no top plane.

    IT IS GROUND, NOT A PROP, and that decides everything about how it is
    drawn. The client bakes it into the ground canvas with the soil, under
    everything, with no keyline and no shadow — a floor tile with an outline is
    a tray sitting on the floor.

    THE MODULE IS A SQUARE AND THE WALL'S IS NOT, and that is the difference
    between a floor and a wall lying down. Masonry is laid in RUNNING BOND —
    long bricks, every other course offset half a brick — because that is how
    you make a wall stand up. A floor is PAVED: square quarries butted
    together on a grid, no bond, because nothing is holding anything else up.
    Running the wall's own 8x4 bond across the ground was the loudest thing
    wrong with the first cut of this room; it read as a wall the camera had
    fallen over onto.

    AND IT IS QUIET. This is the largest surface in the game and almost none of
    it is ever looked at directly: everything the party came in for — the
    counter, the six tables, the man — has to win against it at a glance. So
    the joint is one step down rather than three, the per-tile value roll is a
    single step either way, and the wear is THREE SCUFFS in a whole tile. The
    temptation on a big empty surface is to fill it, and filling it is what
    turns a calm room into a busy one.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    # A square quarry: half the tile, so four to a cell. Big enough to read as
    # paving at 16px and not so big that a tile is two shapes.
    module = max(4, size // 2)

    for y in range(size):
        for x in range(size):
            joint = (x % module == module - 1) or (y % module == module - 1)
            if joint:
                px[x, y] = tone(MORTAR, FRONT - 1, x, y)
                continue
            # Per-QUARRY, never per-pixel (S5). One step either side of the
            # base, so no two neighbours are the same and none of them shouts.
            roll = hash01(x // module, y // module, 4201 + variant * 53)
            step = FRONT + (1 if roll > 0.80 else (-1 if roll < 0.34 else 0))
            px[x, y] = tone(TILE_RAMP, step, x, y)

    # WEAR, and it is the reason there are four frames rather than one. A floor
    # laid out of identical tiles is a texture; a floor with a few scuffed
    # quarries in four tiles is a floor somebody has been walking on for a
    # year. Clustered (S5): a scuff is a run of 3-5 pixels along a joint, never
    # a scatter of singles.
    for _ in range(1 + variant % 3):
        sx = rng.randrange(1, max(2, size - 5))
        sy = rng.randrange(1, size - 1)
        for step in range(rng.randrange(3, 6)):
            x = sx + step
            if x < size and px[x, sy][3] and (x % module != module - 1):
                px[x, sy] = tone(TILE_RAMP, FRONT + 1, x, sy)
    return img



# --- the counter ------------------------------------------------------------
# THREE FRAMES THAT TILE INTO AN L, and they are three frames rather than one
# long sprite for the reason every other run in this game is: the server places
# a LIST of one-tile sections (`store.COUNTER_L`), each claims its own tile of
# cover, and the shape of the L is an offset table somebody can edit without
# opening this file. One 10-tile sprite would put the geometry in the art.
#
#   0  ELBOW   the corner. Two runs meeting, mitred, with the brass edging
#              carried round the outside of the turn.
#   1  EAST    a straight section running left-right along the north wall.
#   2  SOUTH   a straight section running away from the camera, down the east
#              side of the elbow. Narrower top plane: it is the same box seen
#              along its length.
#
# THE BRASS EDGING IS THE ACCENT (S12) and it is on the counter's FRONT lip
# only — the edge the party's side of the shop touches. A counter edged all
# round is a bar; a counter with a worn brass strip on the customer's side is
# somewhere money has been slid across for years.
#
# AND THE SECTIONS ARE SQUARE-ENDED, WHICH IS THE ONE RULE A RUN HAS. See
# `make_counter`: built as dimetric boxes they laid end to end with a notch
# between every pair.

TILE_COUNTER_W = 1.0
TILE_COUNTER_H = 1.4
#: How tall the counter stands, in pixels at a 16px tile. Waist height on the
#: merchant's sprite: he has to be visible from the chest up behind it, because
#: the whole point of the pocket is that you can SEE him in it.
COUNTER_TALL = 9
#: How deep the top plane reads, in pixels. Same job as `WALL_CAP` and the same
#: number scaled down — a counter and a wall are both architecture the camera
#: looks down at, and if they used two different foreshortenings the L would
#: not sit against the wall it is bolted to.
COUNTER_CAP = 4


def make_counter(w: int, h: int, kind: int, rng: random.Random) -> Image.Image:
    """One section of the L. 0 elbow, 1 running east, 2 running south.

    IT IS DRAWN AS ARCHITECTURE, NOT AS A BOX, and that was the second attempt.
    The first cut built each section with `box` — the shared dimetric solid
    every crate and barrel in the game uses — which is right for a thing
    standing on its own and wrong for a RUN. A dimetric box has a near corner
    and a contact line falling away from it in both directions, so ten of them
    laid end to end came out as ten separate lozenges with a V-shaped notch
    between every pair: a counter with teeth.

    A run tiles only if its ends are SQUARE. So a section is a flat top band
    over a flat front face, full frame width, exactly the way a wall tile is
    built — which is also the honest answer, because that is what a counter is.
    The only section with a corner in it is the elbow, and it is the only one
    that gets one.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    base = h - 2
    lid = base - COUNTER_TALL
    top = lid - COUNTER_CAP

    # EVERY SECTION FILLS ITS FRAME, INCLUDING THE ONE RUNNING SOUTH.
    #
    # That arm was drawn inset — starting 30% into the cell — on the reasoning
    # that a counter seen along its length is narrower on screen. It is not: it
    # occupies one whole tile of the map either way, and what an inset actually
    # produces is a HARD VERTICAL CUT down the middle of the sprite with
    # nothing on the other side of it. In the room it read as a stack of boxes
    # somebody had sliced. A run tiles only if its ends are square, and that
    # applies to all four ends, not just the two the run is travelling along.
    x0, x1 = 0, w - 1

    # THE FRONT FACE. Boarding: a value step every few pixels, which is the
    # only detail a one-tile section can hold and what stops a twelve-tile run
    # reading as one long slab. It runs ACROSS on an east arm and DOWN on a
    # south one, because a board follows the run it is nailed to — and because
    # a section whose boards ran the same way as its neighbour's, at ninety
    # degrees to it, is what makes a corner look like a mistake.
    for y in range(lid + 1, base + 1):
        for x in range(x0, x1 + 1):
            along = x if kind != 2 else y
            step = FRONT - (1 if (along // 4) % 3 == 2 else 0)
            if along % 4 == 3:
                step -= 1  # the seam between two boards
            px[x, y] = tone(WOOD, step, x, y)

    # THE TOP PLANE, two steps up. Flat, square-ended, so section meets section
    # with nothing to see.
    for y in range(top, lid + 1):
        for x in range(x0, x1 + 1):
            px[x, y] = tone(WOOD, TOP - 1 if y > top else TOP - 2, x, y)

    if kind == 0:
        # THE ELBOW. The turn is a second top plane laid across the corner one
        # step darker — that VALUE BREAK is the mitre. A corner drawn as one
        # continuous flat plane has no corner in it.
        for y in range(top + 1, lid + 1):
            for x in range(int(w * 0.55), w):
                px[x, y] = tone(WOOD, TOP - 2, x, y)
        for y in range(lid + 1, base + 1):
            for x in range(int(w * 0.55), w):
                px[x, y] = tone(WOOD, SIDE + 1, x, y)

    # THE BRASS LIP, on the edge the CUSTOMER stands at. One pixel, worn
    # through in places so the light eats the line (S6), and the zone's accent.
    # On an east arm that edge is the front; on a south arm it is the west
    # side, because the party is inside the L and the wall is outside it.
    if kind == 2:
        for y in range(top, base + 1):
            if hash01(y, kind, 1531) > 0.16:
                px[x0, y] = tone(BRASS, TOP - 1, x0, y)
    else:
        for x in range(x0, x1 + 1):
            if hash01(x, kind, 1531) > 0.16:
                px[x, lid] = tone(BRASS, TOP - 1, x, lid)

    # A single specular streak along the top (S14, polished wood): one run of
    # pixels, never a gradient, and never the full width — a highlight that
    # reaches both ends of a tiling section repeats into a stripe.
    for x in range(x0 + 2, min(x1, x0 + int((x1 - x0) * 0.55))):
        px[x, top + 1] = tone(WOOD, TOP, x, top + 1)

    # AMBIENT OCCLUSION where the counter meets the floor (S10).
    for x in range(x0, x1 + 1):
        px[x, base] = tone(WOOD, SIDE, x, base)

    shadow(img, (x0 + x1) / 2 + 1.5, base + 1.0, (x1 - x0) * 0.55, 2.0)
    outline(img, OUTLINE)
    return img


# --- the shelves ------------------------------------------------------------
# WHAT ELSE HAS HE GOT. Six tables hold six guns and nothing in the zone has
# ever suggested there is more to the man than that. A wall of jars, tins and
# bundles behind the counter says the stock on the floor is a SELECTION, which
# is a better statement than a trader with exactly six things — and it costs
# three frames and no gameplay.
#
# NONE OF IT OPENS, and the composition carries that without a prompt: it is
# high on a wall, behind a counter, in the pocket the party cannot walk into.
# The player never gets close enough to press anything at it.
#
# THEY ARE BACKGROUND MASSES (S13): steps 1-3 only, no step 4, no specular.
# The one thing in this corner allowed the full ramp is the merchant.

TILE_SHELF_W = 1.6
TILE_SHELF_H = 1.9


def make_shelf(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One unit of wall shelving: a frame, two or three boards, and stock."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    base = h - 2
    fx = (w - 1) / 2.0
    boards = (3, 2, 3)[variant]

    # THE UPRIGHTS. Two narrow boxes carrying the whole thing, drawn first so
    # every shelf board laps over them — S18.1, near masses cut into far ones.
    for side in (-1, 1):
        box(px, (w, h), fx + side * (w * 0.36), base, 1.6, 1.6,
            h - 5, WOOD_WORN, salt=1600 + variant)

    # THE BOARDS, top-lit rhombi at a `1 : 0.7 : 0.5` rhythm of spacing (S17)
    # rather than at even intervals: a rack with equal gaps is flat-pack, and
    # this man built these out of what he had.
    gaps = (0.30, 0.55, 0.78)[:boards]
    for index, share in enumerate(gaps):
        by = int(round(4 + (h - 8) * share))
        # SQUASHED HARD. A shelf is SHALLOW — six inches of board seen from
        # above is two or three pixels of top plane, not the ten a full-slope
        # rhombus gives. Unsquashed these came out as tan lozenges wide enough
        # to hide the brackets holding them, which is a shelf with no shelf in
        # it.
        cap(px, (w, h), fx, by, w * 0.34, w * 0.34, WOOD, FRONT + 1, squash=0.30)
        for x in range(w):
            y = by + 1
            if 0 <= y < h and px[x, y][3]:
                px[x, y] = tone(WOOD_WORN, SIDE + 1, x, y)  # the board's edge

        # THE STOCK on that board. Jars, tins and a bundle — round, square and
        # soft, in that order, because three silhouettes is the most a 26px
        # sprite can hold and they have to be different SHAPES rather than
        # different colours to read at all.
        slot = w * 0.58 / 3.0
        for item in range(3):
            if hash01(index, item, 1700 + variant * 13) < 0.22:
                continue  # a gap on the shelf: a shop somebody has sold out of
            ix = fx - w * 0.27 + slot * (item + 0.5)
            kind = (index + item + variant) % 3
            tall = 3 + (item % 2)
            if kind == 0:      # a jar: a squat cylinder with a lid
                billet(px, (w, h), ix - 1.6, ix + 1.6, by - tall + 1, 1.8,
                       GLASS_COLD, cap=False)
                for x in range(int(ix - 2), int(ix + 2)):
                    y = by - tall - 1
                    if 0 <= x < w and 0 <= y < h:
                        px[x, y] = tone(IRON, FRONT, x, y)
            elif kind == 1:    # a tin: a small box, the only hard silhouette
                box(px, (w, h), ix, by, 1.7, 1.7, tall, IRON, salt=1711 + item)
            else:              # a bundle: cloth, soft top, no specular
                billet(px, (w, h), ix - 2.0, ix + 2.0, by - tall + 2, 2.0,
                       LINEN, cap=False)

    shadow(img, fx + 1.0, base + 1.0, w * 0.44, 1.8)
    outline(img, OUTLINE)
    return img


# --- the decoration crates --------------------------------------------------
# THEY EXIST TO BE NOT INTERACTIVE, and the art is the only thing that says so.
#
# The player spent the previous night learning that a box in this game is a
# thing you walk up to and open. Put three unmarked crates on a shop floor and
# every one of them is a prompt somebody is going to hunt for. So every frame
# here is drawn SHUT and BOUND — roped, lidded, strapped, stacked under
# something else — and none of them has the metal latch or the raised lid lip
# that `make_objects.make_crate` uses as its "this opens" tell. A silhouette
# that reads "closed" is cheaper and more reliable than any amount of prompt
# suppression, and it is the same rule his kit out in the yard keeps.

TILE_CRATE_W = 1.2
#: TALLER THAN THE FOOTPRINT, per S3, and with rows to spare at the bottom for
#: the contact patch and the keyline `outline` draws round it. Same sizing the
#: kit sheet needed — see `_check_margins`, which now guards both.
TILE_CRATE_H = 1.75

def make_crate(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One piece of shop-floor decoration. Three, and none of them opens.

    BUILT ON `_block`, NOT ON THE SHARED `box`. Same correction the kit sheet
    got and for the same reason: `make_objects.box` slopes the CONTACT as well
    as the lid, so a box drawn with it has a V for a bottom and reads as a
    LOSANGE floating over the floor rather than as a crate standing on it. The
    kit was fixed and these were missed, which is why the shop had one set of
    boxes with a flat base and another set with a diamond one in the same room.
    See `_block` for the construction.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    # Left of centre, because `_block` shears to the RIGHT: an object on the
    # frame's centreline puts its top plane and its shade side over the edge.
    # SIZED OFF THE CELL RATHER THAN TYPED. `_block` shears to the RIGHT, so a
    # drawing's span is `2*half + depth` and it needs a pixel either side for
    # its keyline. Deriving both from the frame is what stops a nudge to one of
    # them pushing the sprite through its own edge — which is what
    # `_check_margins` caught here twice, with hand-picked numbers that were
    # right until the frame width moved.
    depth = (w - 6) * 0.26
    half = (w - 6 - depth) / 2.0
    cx = 2.5 + half
    base = h - 5

    if variant == 0:
        # A ROPED CRATE. One block, one cord over the lid and down the face.
        _block(px, (w, h), cx, base, half, 13.0, depth, WOOD_WORN, salt=1801)
        lid = base - 13.0
        for x in range(int(cx - half), int(cx + half) + 1):
            for y in (int(lid), int(lid) + 1):
                if 0 <= x < w and 0 <= y < h and px[x, y][3]:
                    px[x, y] = tone(ROPE, FRONT, x, y)
        for y in range(int(lid) + 1, int(base) + 1):
            for x in (int(cx - 1), int(cx)):
                if 0 <= x < w and px[x, y][3]:
                    px[x, y] = tone(ROPE, FRONT - 1, x, y)

    elif variant == 1:
        # A STACK: two blocks at 1 : 0.62 by footprint (S17), the upper one set
        # BACK on the lower's lid rather than centred, so you can see the
        # surface it is standing on. That is what makes it a stack instead of a
        # wedding cake.
        _block(px, (w, h), cx, base, half, 10.0, depth, WOOD_WORN, salt=1811)
        _block(px, (w, h), cx + 1.0, base - 11.0, half * 0.62, 7.0, depth * 0.75, WOOD, salt=1813)
        # One iron band round the lower block: the only hard-surface line here,
        # and the sprite's single specular allowance goes on its bolt.
        band = int(base - 4)
        for x in range(int(cx - half), int(cx + half) + 1):
            if 0 <= x < w and 0 <= band < h and px[x, band][3]:
                px[x, band] = tone(IRON, FRONT, x, band)
        if 0 <= band < h:
            px[int(cx), band] = tone(IRON, TOP, int(cx), band)

    else:
        # A BARREL with a folded sack on it. Round against two squares — the
        # set needs one non-box silhouette or three crates in a room read as
        # one crate drawn three times (S15: the top contour carries identity).
        top_y = base - 14
        for y in range(int(top_y), int(base) + 1):
            t = (y - top_y) / max(base - top_y, 1)
            r = half - t * 0.5
            for x in range(int(cx - r), int(cx + r) + 1):
                if not (0 <= x < w):
                    continue
                across = (x - cx) / max(r, 0.5)
                stave = int((x - cx) // 3)
                plane = TOP if across < -0.25 else (FRONT if across < 0.45 else SIDE)
                bump = 1 if hash01(stave, 0, 1821) > 0.60 else 0
                px[x, y] = tone(WOOD_WORN, max(SIDE, plane - bump), x, y)
        for hoop in (int(top_y + 3), int(base - 3)):
            for x in range(w):
                if 0 <= hoop < h and px[x, hoop][3]:
                    px[x, hoop] = tone(IRON, FRONT, x, hoop)
        cap(px, (w, h), cx, top_y, half, half, WOOD_WORN, FRONT + 1, squash=0.45)
        # The sack: cloth, so a soft top and no specular (S14).
        cap(px, (w, h), cx, top_y - 2, half * 0.8, half * 0.8, LINEN, FRONT + 1, squash=0.5)
        cap(px, (w, h), cx - 1, top_y - 4, half * 0.58, half * 0.58, LINEN, TOP - 2, squash=0.5)

    shadow(img, cx + depth * 0.5, base + 0.5, half + depth * 0.35, 1.4)
    outline(img, OUTLINE)
    return img



# --- the lamps --------------------------------------------------------------
# THE ROOM IS LIT BY OIL LAMPS STANDING ON THEIR OWN LITTLE TABLES.
#
# THEY HUNG FROM CHAINS FIRST, and the argument for that was sound: a room is
# lit from above, a clearing can only ever be lit from its rim, and five lamps
# on a regular grid over the floor is the difference between the two. What it
# missed is that this camera is looking DOWN at about sixty degrees. A lamp two
# tiles over the floor is drawn two tiles UP the screen from the tile it lights,
# so the light and the thing making it never appear in the same place — and the
# chain above it runs off the top of the sprite into a ceiling that, in a
# roofless cutaway, does not exist. What the player saw was five lanterns
# floating in mid-air over their own puddles.
#
# A LAMP ON A TABLE HAS ITS FLAME WHERE ITS LIGHT IS. It stands on the floor,
# it sorts with everything else, it casts its pool from a foot above its own
# contact instead of from two tiles above it, and it needs no ceiling to exist.
# It is also the warmer object: a hurricane lamp with a brass collar and a
# smoked chimney on a little side table is furniture somebody put there, where
# a chain is fixtures somebody installed.
#
# THE STAND IS PART OF THE SPRITE. It could have been a separate prop the
# server placed a lamp on top of, and that would mean two payload rows, two
# depth-sort entries and a height the client has to know to stack them — for a
# thing that is never apart. One sprite, one contact, one row.
#
# THEY ARE STILL THE LIGHT BUDGET. `zones.STORE_AMBIENT` is a floor under the
# darkness pass and every one of these is drawn ADDITIVELY on top with nothing
# clamping the sum. Five at `store.LAMP_LIGHT_TILES` is what the floor carries.
# Adding a sixth means taking reach out of the other five.

TILE_LAMP_W = 1.0
TILE_LAMP_H = 1.75
#: Where the flame burns inside the chimney, in frame pixels from the TOP.
#: Derived, not typed — the body is placed off the frame's height below, and a
#: hand-picked number here would come apart the first time the sprite grew.
LAMP_FLAME_Y = 7


def make_lamp(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One oil lamp on a small stand. Two frames: a hurricane and a squat lamp.

    Two, not one, for the same reason there are two torches: a row of five
    identical lamps is a light fitting somebody ordered, and this man put out
    whatever he had. They are the same HEIGHT and the same colour and differ
    only in the vessel, so the room still reads as evenly lit.

    THE VESSEL IS THE SPRITE AND THE STAND IS TRIM. The thing the player has to
    see is the LIT PART, so the chimney owns the top third of the frame, the
    stand under it is deliberately plain, and the brass collar between them is
    the one row of accent.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    cx = (w - 1) / 2.0 - 1.5
    base = h - 4

    # THE STAND: a small round side table. Narrow top, narrower waist, splayed
    # foot — S17's `1 : 0.7 : 0.5` rhythm, so it does not read as a post.
    top_y = base - 9
    cap(px, (w, h), cx, base, 3.6, 3.6, WOOD_WORN, FRONT - 1, squash=0.5)
    for y in range(int(top_y) + 1, int(base)):
        t = (y - top_y) / max(base - top_y, 1)
        r = 1.4 + abs(t - 0.4) * 1.1
        for x in range(int(cx - r), int(cx + r) + 1):
            if 0 <= x < w:
                px[x, y] = tone(WOOD_WORN, FRONT if x <= cx else SIDE, x, y)
    cap(px, (w, h), cx, top_y, 4.2, 4.2, WOOD, FRONT + 1, squash=0.55)

    # THE RESERVOIR: the oil bowl the wick sits in. Brass, and the widest part
    # of the lamp itself, so the silhouette pinches between it and the chimney.
    bowl = top_y - 3
    for y in range(int(bowl), int(top_y)):
        t = (y - bowl) / 3.0
        r = 1.8 + t * 1.4
        for x in range(int(cx - r), int(cx + r) + 1):
            if 0 <= x < w:
                px[x, y] = tone(BRASS, TOP - 1 if x < cx else FRONT, x, y)

    # THE CHIMNEY. Glass is a flat step-3 fill with parallel 1px streaks
    # (S14) — the streaks ARE the material, so nothing else is shaded inside.
    neck = bowl - 1
    chim_top = LAMP_FLAME_Y - 3
    for y in range(int(chim_top), int(neck) + 1):
        t = (y - chim_top) / max(neck - chim_top, 1)
        # A hurricane flares at the top; the squat lamp is a straight sleeve.
        span = (1.6 + t * 1.6) if variant == 0 else (2.2 + t * 0.5)
        for x in range(int(cx - span), int(cx + span) + 1):
            if 0 <= x < w:
                px[x, y] = tone(GLASS, FRONT, x, y)
    for offset in (-1, 1):
        for y in range(int(chim_top) + 1, int(neck)):
            x = int(cx + offset)
            if 0 <= x < w and px[x, y][3]:
                px[x, y] = tone(GLASS, TOP - 1, x, y)

    # THE COLLAR: brass, and the only saturated row on a sprite that is
    # otherwise wood, brass and glass.
    for x in range(int(cx - 2), int(cx + 3)):
        if 0 <= x < w and 0 <= neck < h:
            px[x, neck] = tone(BRASS, TOP - 1, x, neck)

    if variant == 0:
        # A wire handle over the hurricane's mouth: the one thing above the
        # glass, and what makes the two frames differ in TOP CONTOUR (S15)
        # rather than only in their fill.
        for x in range(int(cx - 3), int(cx + 4)):
            y = int(chim_top) - 1
            if 0 <= x < w and 0 <= y < h and abs(x - cx) >= 2:
                px[x, y] = tone(IRON, FRONT, x, y)

    shadow(img, cx + 2.0, base + 0.5, 5.0, 1.3)
    outline(img, OUTLINE)
    return img


# --- the tables -------------------------------------------------------------
# SIX SMALL ROUND PEDESTALS, and every word of that is load-bearing.
#
# SMALL: they used to be taller than the guns lying on them, which put six
# pieces of furniture in the middle of the shop that outweighed everything they
# were selling. ROUND: they are walked around now, and a board has a front and
# a back that read wrong from three of the four sides a room lets you approach
# it from. FOUR FRAMES: a turned column, a barrel, a cable spool and a stone
# drum — four different things pressed into service, because a trader who owns
# six matching display tables owns a shop, and this one owns a cart.
#
# `topY` PER VARIANT is what the manifest ships. The four are deliberately
# different heights, so a single hardcoded surface offset would float one gun
# and sink another. It is pose data, not decoration.

TILE_TABLE_W = 1.5
TILE_TABLE_H = 1.25
#: The row a weapon lies on, per variant, in frame pixels. See above.
TABLE_TOP_Y = (5, 7, 6, 8)


def disc_top(px, size: tuple[int, int], cx: float, y: float, r: float,
             ramp: Ramp, step: int = TOP, *, thick: int = 2,
             squash: float = 1.0) -> None:
    """A ROUND surface seen from the front and above: an ellipse with an edge.

    WHY NOT `cap`. The shared lid is a parallelogram — right for a crate,
    wrong for everything on this bench, because these are pedestals the player
    walks around and a board has corners the eye keeps trying to square up
    with the room. Worse, drawn without the second half of this function it is
    a FLAT SHAPE: a lighter patch sitting where a top ought to be, which is
    the same failure a corner-on box has, one plane short.

    The second half is the whole point. Under the near arc of the ellipse go
    `thick` rows of the BOARD ITSELF, following the curve — the edge grain you
    would see standing in front of a table. That is what gives the top a
    thickness instead of a colour, and it costs two rows. The right of the arc
    takes the shade step, because the key is at 135° like everything else
    here.
    """
    width, height = size
    ry = max(1.0, r * SLOPE * squash)
    for dy in range(-int(round(ry)), int(round(ry)) + 1):
        yy = int(round(y + dy))
        if not 0 <= yy < height:
            continue
        span = r * math.sqrt(max(0.0, 1.0 - (dy / ry) ** 2))
        for x in range(int(round(cx - span)), int(round(cx + span)) + 1):
            if 0 <= x < width:
                px[x, yy] = tone(ramp, step, x, yy)
    if thick <= 0:
        return
    for x in range(int(round(cx - r)), int(round(cx + r)) + 1):
        if not 0 <= x < width:
            continue
        across = (x - cx) / max(r, 0.5)
        edge = y + ry * math.sqrt(max(0.0, 1.0 - across * across))
        rim = FRONT if across <= 0.45 else SIDE
        for t in range(thick):
            yy = int(round(edge)) + t
            if 0 <= yy < height:
                px[x, yy] = tone(ramp, rim, x, yy)


def make_table(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One pedestal. Four, and no two are the same piece of furniture."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    fx = (w - 1) / 2.0
    base = h - 2
    surface = TABLE_TOP_Y[variant]

    if variant == 0:
        # A TURNED COLUMN on a splayed foot. Three masses at S2's descending
        # rhythm — foot, shaft, top — and the FOOT is the widest of the three.
        # S17: the base is wider than the crown for anything grounded.
        disc_top(px, (w, h), fx, base - 1, w * 0.30, WOOD_WORN, FRONT,
                 thick=1, squash=0.55)
        for y in range(surface + 3, base):
            t = (y - surface) / max(base - surface, 1)
            r = w * (0.17 + abs(t - 0.45) * 0.11)
            for x in range(int(fx - r), int(fx + r) + 1):
                if 0 <= x < w:
                    plane = FRONT if x <= fx else SIDE
                    px[x, y] = tone(WOOD, TOP if abs(x - fx) < r * 0.30 else plane, x, y)
        disc_top(px, (w, h), fx, surface + 2, w * 0.29, WOOD, TOP - 1,
                 thick=2, squash=0.62)

    elif variant == 1:
        # A BARREL stood on its end. Staves as vertical value runs, two hoops.
        # The one variant whose body is as wide as its top, which is what a
        # barrel is.
        for y in range(surface + 2, base + 1):
            t = (y - surface) / max(base - surface, 1)
            r = w * (0.27 - t * 0.015)
            for x in range(int(fx - r), int(fx + r) + 1):
                if not (0 <= x < w):
                    continue
                across = (x - fx) / max(r, 0.5)
                # Staves: a coarse band per 3px, not a per-pixel jitter (S5).
                stave = int((x - fx) // 3)
                bend = TOP if across < -0.15 else (FRONT if across < 0.45 else SIDE)
                bump = 1 if hash01(stave, 0, 2100 + variant) > 0.62 else 0
                px[x, y] = tone(WOOD_WORN, max(SIDE, bend - bump), x, y)
        for hoop in (surface + 5, base - 3):
            for x in range(w):
                if 0 <= hoop < h and px[x, hoop][3]:
                    px[x, hoop] = tone(IRON, FRONT, x, hoop)
        disc_top(px, (w, h), fx, surface + 1, w * 0.27, WOOD, TOP - 1,
                 thick=2, squash=0.60)

    elif variant == 2:
        # A CABLE SPOOL laid flat: two discs with a narrow drum between them.
        # The widest silhouette of the four and the only one with a WAIST —
        # which is the whole reason it is on the sheet. S15: assets are told
        # apart by their top contour, and this is the only pinched one.
        disc_top(px, (w, h), fx, base - 1, w * 0.34, WOOD_WORN, FRONT - 1,
                 thick=1, squash=0.55)
        for y in range(surface + 4, base - 1):
            r = w * 0.13
            for x in range(int(fx - r), int(fx + r) + 1):
                if 0 <= x < w:
                    px[x, y] = tone(WOOD_WORN, FRONT if x <= fx else SIDE, x, y)
        disc_top(px, (w, h), fx, surface + 3, w * 0.33, WOOD, TOP - 2,
                 thick=1, squash=0.58)
        disc_top(px, (w, h), fx, surface + 1, w * 0.31, WOOD, TOP - 1,
                 thick=2, squash=0.58)
        # The plank ends showing round the rim: three notches, irregular.
        for share in (0.18, 0.52, 0.83):
            x = int(round(fx - w * 0.31 + w * 0.62 * share))
            y = int(round(surface + 2 - abs(x - fx) * SLOPE * 0.58))
            if 0 <= x < w and 0 <= y < h and px[x, y][3]:
                px[x, y] = tone(WOOD, SIDE + 1, x, y)

    else:
        # A STONE DRUM: something that was already here. Faceted, not curved —
        # stone gets straight breaks and angular chips (S14), which is what
        # keeps it from reading as another wooden thing.
        stone(px, (w, h), fx, base - 3, w * 0.28, 5.0, objects.STONE, 2211)
        disc_top(px, (w, h), fx, surface + 1, w * 0.29, objects.STONE, TOP - 2,
                 thick=2, squash=0.60)
        for _ in range(3):
            cx = fx + (rng.random() - 0.5) * w * 0.4
            cy = surface + 5 + rng.random() * 3
            for step in range(3):
                x, y = int(cx + step), int(cy + step // 2)
                if 0 <= x < w and 0 <= y < h and px[x, y][3]:
                    px[x, y] = tone(objects.STONE, SIDE + 1, x, y)

    # AMBIENT OCCLUSION at the foot (S10) then the contact patch under it.
    for x in range(w):
        if px[x, base][3]:
            px[x, base] = tone(WOOD_WORN if variant != 3 else objects.STONE,
                               SIDE, x, base)
    shadow(img, fx + 1.5, base + 1.0, w * 0.44, 2.4)
    outline(img, OUTLINE)
    return img


# --- the torch --------------------------------------------------------------


def make_torch(w: int, h: int, variant: int) -> Image.Image:
    """One torch post, UNLIT, standing in the YARD. The fire is `torchfire.png`.

    Same split every light in this game makes, and for the same reason: paint
    the flame into the prop and it goes under whatever the client multiplies
    over the frame, which leaves a torch that is only lit once you are already
    standing in its light. These exist to be seen from the far end of a dark
    yard, so the burning half has to be additive and drawn after the night.

    THEY ARE ALL OUTDOORS NOW. Nothing burns on a post inside the shop — that
    is what the lamps are for — so these only ever stand on soil, and they are
    toned for the forest's darkness rather than for the shop's ambient floor.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    cx = (w - 1) / 2.0
    head_bottom = 10
    lean = 0.0 if variant == 0 else 0.055

    def centre_at(y: float) -> float:
        return cx + (y - h) * lean

    # THE POST. A cylinder, not a flat strip: three bands across its width, the
    # crest thin and the underside thinner, which is the whole read at 4px.
    for y in range(head_bottom, h - 1):
        c = centre_at(y)
        t = (y - head_bottom) / max(h - head_bottom, 1)
        r = 1.4 + t * 0.9
        for x in range(int(c - r), int(c + r) + 1):
            if not (0 <= x < w):
                continue
            up = (c - x) / max(r, 0.5)
            plane = TOP if up > 0.35 else (FRONT if up > -0.40 else SIDE)
            px[x, y] = tone(WOOD_WORN, plane, x, y)

    # THE HEAD: an iron basket (0) or a lashed bundle (1). Different TOP
    # CONTOURS (S15), because that is what tells two torches apart across a
    # dark yard — never colour.
    head_ramp = IRON if variant == 0 else ROPE
    for y in range(2, head_bottom + 1):
        c = centre_at(y)
        t = (y - 2) / max(head_bottom - 2, 1)
        # Wide at the lip, pinched where it meets the post: the silhouette has
        # to say "something is held up here" at twelve pixels across.
        half = w * 0.40 - t * (w * 0.40 - 1.4)
        for x in range(int(c - half), int(c + half) + 1):
            if not (0 <= x < w):
                continue
            up = (c - x) / max(half, 0.5)
            plane = TOP if up > 0.30 else (FRONT if up > -0.35 else SIDE)
            px[x, y] = tone(head_ramp, plane, x, y)

    # Two bands lashing the head to the post. At twelve pixels wide this is the
    # only detail that survives, and without it the head is a blob.
    for y in (head_bottom + 1, head_bottom + 3):
        c = centre_at(y)
        for x in range(int(c - 2), int(c + 3)):
            if 0 <= x < w and px[x, y][3]:
                px[x, y] = tone(LEATHER if variant == 1 else IRON, FRONT, x, y)

    # Coals in the head. Scattered over two rows rather than filling one — a
    # solid row at the lip reads as a coloured lid on the sprite rather than as
    # something burning inside a basket.
    for y in (3, 4):
        c = centre_at(y)
        for x in range(int(c - w * 0.3), int(c + w * 0.3) + 1):
            if not (0 <= x < w) or not px[x, y][3] or hash01(x, y, 919) > 0.5:
                continue
            px[x, y] = pick(COALS, 0.55 + hash01(x, y, 923) * 0.4, x, y)

    shadow(img, cx + 1.0, h - 1.0, w * 0.40, 1.6)
    outline(img, OUTLINE)
    return img


#: Where the flame sits inside the head, per variant, in frame pixels.
TORCH_FLAME_Y = (3, 3)


# --- the mats ---------------------------------------------------------------


def make_rug(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One mat. A DECAL: flat, no outline, no top plane, baked into the ground.

    THEY ARE THE CHEAPEST THING IN THE SHOP AND THEY DO THE MOST WORK. A brick
    floor with furniture standing on it is a warehouse; the same floor with
    three worn mats laid along the lines people actually walk is somewhere
    somebody lives. There are three because they mark three different paths —
    the door, the stock, the counter — and at this pitch the only thing telling
    them apart is HUE, so they are three dyes rather than three shades.

    NO SHADING AT ALL, deliberately. A decal is on the floor; giving it a lit
    side and a shaded side would make it read as a thing standing up at ankle
    height. What carries it is WEAVE (a two-axis value beat) and WEAR.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    ramp = (RUG_RED, RUG_BLUE, RUG_GOLD)[variant]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for y in range(h):
        for x in range(w):
            # A rounded rectangle, worn away at the corners like a real mat.
            dx = abs(x - cx) / cx
            dy = abs(y - cy) / cy
            corner = (dx ** 4 + dy ** 4) ** 0.25
            if corner > 0.97 + hash01(x, y, 1201 + variant) * 0.06:
                continue
            border = corner > 0.80
            # The WEAVE. Two sines at different rates so the beat between them
            # never lines up into a visible grid.
            weft = 0.5 + math.sin(x * 0.8) * 0.06 + math.sin(y * 1.7) * 0.05
            value = weft + (0.22 if border else 0.0) - hash01(x, y, 61) * 0.12
            if not border and abs(dy) < 0.45 and (x + y * 2) % 9 < 2:
                value += 0.20  # the pattern woven into the middle
            # WORN THROUGH in the centre, where the feet go. The one thing on
            # the mat that is not symmetrical, and the reason it reads as used.
            if (dx ** 2 + dy ** 2) < 0.30 and hash01(x // 2, y // 2, 1301) > 0.62:
                value -= 0.18
            px[x, y] = pick(ramp, clamp01(value), x, y)
    # Fringe on the short ends only, which is the end a mat is woven from.
    for y in range(h):
        if hash01(0, y, 9 + variant) > 0.45:
            for x in (0, w - 1):
                if px[x, y][3]:
                    px[x, y] = pick(ROPE, 0.55, x, y)
    return img


# --- his cart ---------------------------------------------------------------
# THE WAGON IS THE ANSWER TO "WHO IS THIS MAN", AND IT IS OUTSIDE NOW.
#
# A covered cart says he DRIVES, he was somewhere else last week, and that is
# the reason he is worth finding. A brick building says the opposite. The two
# only work together if the cart is what he ARRIVED IN and the shop is what he
# unloaded into — so it is parked in the YARD, between the party and the door,
# read on the walk up: cart first, then the building it feeds.
#
# IT IS NOT A HEARSE. It used to hang bone masks on a line under the eave and
# lay two covered bodies with their boots out at the front wheel, on the
# argument that the party should work out where the stock comes from on their
# own. The argument was fine and the result was not: this is the one beat of
# the loop that exists to be a relief from the night, and the biggest sprite in
# it was a cart with corpses under a tarp. Same rule for anything added here.
#
# IT IS A CYLINDER ON A BOX ON TWO WHEELS. The canopy is a `billet` — three
# unequal bands across its arc, lit crest, wide flank, thin underside — laid on
# a `box` bed. Drawn as a shaded rectangle with a curve painted on the top it
# was a picture of a wagon; drawn as a solid the camera goes over, it is one.

TILE_WAGON_W = 4.5
TILE_WAGON_H = 3.5


def make_wagon(w: int, h: int, rng: random.Random) -> Image.Image:
    """His cart: bed, canopy, wheels, a lamp on the bow, crates at the axle."""
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    base = h - 4
    fx = w * 0.50
    bed_top = base - h * 0.22

    # THE WHEELS FIRST, so the bed laps over them (S18.1 — near masses cut into
    # far ones). Two visible: the near pair. A wagon drawn with four wheels at
    # this angle is a wagon with two wheels floating behind it.
    for share, r in ((0.24, h * 0.19), (0.79, h * 0.16)):
        cxw = w * share
        cyw = base - r * 0.55
        for y in range(int(cyw - r), int(cyw + r) + 1):
            for x in range(int(cxw - r), int(cxw + r) + 1):
                if not (0 <= x < w and 0 <= y < h):
                    continue
                dx, dy = (x - cxw) / r, (y - cyw) / r
                d = math.hypot(dx, dy)
                if d > 1.0:
                    continue
                if d > 0.72:
                    px[x, y] = tone(WOOD_WORN, TOP - 1 if dy < 0 else FRONT, x, y)
                elif d < 0.20:
                    px[x, y] = tone(IRON, FRONT, x, y)
                elif abs(math.atan2(dy, dx) * 3.4 % 1.0 - 0.5) < 0.16:
                    px[x, y] = tone(WOOD_WORN, SIDE + 1, x, y)  # spokes

    # THE BED. One long box on the shared camera.
    box(px, (w, h), fx, base, w * 0.44, w * 0.44, h * 0.22, WOOD_WORN, salt=1301)
    # Plank seams down the near face: value steps, three of them, unevenly
    # spaced — a bed with evenly ruled planks is a fence panel.
    for share in (0.22, 0.47, 0.79):
        sx = int(round(fx - w * 0.44 + w * 0.88 * share))
        for y in range(int(bed_top) + 2, base + 1):
            if 0 <= sx < w and px[sx, y][3]:
                px[sx, y] = tone(WOOD_WORN, SIDE, sx, y)

    # THE CANOPY, a cylinder lying along the cart. The single biggest mass on
    # the sprite and the thing that has to read from across the yard.
    axis = bed_top - h * 0.24
    billet(px, (w, h), w * 0.10, w * 0.90, axis, h * 0.25, LINEN,
           cap=False)
    # RIBS under the canvas: four arcs, a value step down, so the cover reads
    # as stretched over a frame rather than as a painted tube. Unevenly spaced
    # (S17), because a hand-built tilt has no two bays the same.
    for share in (0.14, 0.39, 0.61, 0.88):
        rx = int(round(w * (0.10 + 0.80 * share)))
        for y in range(int(axis - h * 0.25), int(axis + h * 0.25) + 1):
            if 0 <= rx < w and 0 <= y < h and px[rx, y][3]:
                px[rx, y] = tone(LINEN, SIDE + 1, rx, y)
    # THE OPEN END, and it is the only real depth cue on the sprite.
    #
    # It used to be two columns of frame timber standing at the mouth, which
    # says "the cover ends here" and nothing at all about the cart being
    # hollow. A tilt is a tube: what says so is being able to see INTO it. So
    # the mouth is an ellipse — the cylinder's own cross-section, cut at the
    # camera's slope — filled with the darkest step on the sheet and ringed
    # by the hoop that holds it open. The dark is doing the work: an interior
    # two steps under the shade side is a hole, and a hole is the one thing on
    # this drawing that cannot be read as paint on a flat plane.
    mouth_x = w * 0.17
    mouth_ry = h * 0.19
    mouth_rx = w * 0.05
    for y in range(int(axis - mouth_ry) - 1, int(axis + mouth_ry) + 2):
        for x in range(int(mouth_x - mouth_rx) - 1, int(mouth_x + mouth_rx) + 2):
            if not (0 <= x < w and 0 <= y < h) or not px[x, y][3]:
                continue
            dx, dy = (x - mouth_x) / mouth_rx, (y - axis) / mouth_ry
            d = math.hypot(dx, dy)
            if d > 1.18:
                continue
            if d > 0.92:
                # The hoop: lit on the crown, shaded under, so the ring reads
                # as a bent rod rather than as an outline drawn round a hole.
                px[x, y] = tone(WOOD, TOP - 1 if dy < -0.1 else FRONT, x, y)
            else:
                # Inside. One band of lit floor at the bottom of the tube, so
                # the hole has a BOTTOM and does not read as a black disc.
                px[x, y] = tone(WOOD_WORN, FRONT - 1 if dy > 0.62 else SIDE - 1,
                                x, y)

    # THE GUNS RACKED ALONG THE FLANK. Four short billets under the eave — not
    # readable as models at this size and not meant to be. What they say is
    # that this is where the stock came from.
    for index in range(4):
        gx = w * (0.24 + index * 0.14)
        gy = bed_top - 2
        billet(px, (w, h), gx, gx + w * 0.09, gy, 1.4, IRON, cap=False)

    # CRATES ROPED AT THE WHEELS. Two, at 1 : 0.7 (S17), on the shaded side.
    box(px, (w, h), w * 0.10, base + 1, w * 0.07, w * 0.07, h * 0.13,
        WOOD, salt=1311)
    box(px, (w, h), w * 0.93, base, w * 0.05, w * 0.05, h * 0.09,
        WOOD, salt=1313)

    # THE LAMP ON THE BOW. Brass — the accent, and the same collar the hanging
    # lamps wear, which is what ties the cart to the shop it feeds.
    lx, ly = int(w * 0.93), int(axis - h * 0.08)
    for y in range(ly, ly + 4):
        for x in range(lx - 1, lx + 2):
            if 0 <= x < w and 0 <= y < h:
                px[x, y] = tone(BRASS, TOP - 1 if y == ly else FRONT, x, y)

    shadow(img, fx + 3.0, base + 3.0, w * 0.46, 4.0)
    outline(img, OUTLINE)
    return img


# --- his own gear -----------------------------------------------------------
# FIVE FRAMES, NONE OF WHICH OPENS, all of them out in the YARD.
#
# Six tables in a shop is a shop. Six tables with crates roped up behind them, a
# barrel of spare rods, a plank shelf of tins and a padlocked strongbox is
# somebody LIVING out here and selling out of what they have. Nothing in this
# sheet can be opened, bought or broken — and the ART has to say so, because
# the player spent the whole previous night learning that a box in this game is
# a thing you open. Every frame is drawn SHUT: roped, strapped, lidded,
# padlocked.
#
# THEY ARE BUILT ON `_block`, NOT ON THE SHARED `box`, AND THAT IS THE WHOLE
# POINT OF THIS SECTION. See the comment over `_block` — the shared solid is a
# corner-on dimetric and these came out as clipped diamonds because of it.
#
# THE RACK (frame 2) IS DELIBERATELY THE WEAKEST and it is still here: at the
# size these are drawn it comes out as a handful of loose rods with no frame
# round them, so `server/app/store.py` does not place it. It stays on the sheet
# because generated-asset lists are APPEND-ONLY — pulling a row would move
# every frame index after it.

TILE_KIT_W = 22
#: TALLER THAN IT IS WIDE, and that is a correction. This was 20 against a
#: width of 22, so every frame was SQUAT — and worse, every one of them ran off
#: the bottom and the right of its own cell, because the drawings were sized to
#: fill a box they did not fit in. S3 puts height:footprint between 1.1:1 and
#: 1.6:1 and says squat is wrong; S9 wants a ground shadow under the thing,
#: which needs rows nobody is drawing in; and a silhouette clipped by its own
#: frame edge is not a silhouette (S15). Thirty gives the objects room to
#: STAND, plus two rows at the bottom for the contact patch.
TILE_KIT_H = 32


def _block(px, size: tuple[int, int], cx: float, base: float, half: float,
           tall: float, depth: float, ramp: Ramp, *, salt: int = 0,
           top: int = TOP, front: int = FRONT, side: int = SIDE) -> None:
    """A standing box, with the run back from the camera named by the caller.

    THE SAME CONSTRUCTION `make_objects.box` NOW USES — flat base, rectangular
    front, top plane sheared up and to the right, shade sliver between them.
    This function reached it first: the shared solid was a corner-on dimetric
    with a rhombus footprint, and a row of small props drawn that way came out
    as diamonds floating over the floor rather than as objects standing on it.
    That argument won, so the shared solid was rewritten to match and every
    crate, chest and altar plinth in the forest came with it.

    What survives here is the one thing that did not generalise: `depth` is
    AUTHORED per prop. The shared solid derives it from the width, which is
    right when a sheet of unrelated objects has to agree about the camera and
    wrong for a shelf that has to be shallower than the crate beside it — a
    shelf is a shallow thing, and deriving its depth from how wide it is makes
    it a cabinet.
    """
    width, height = size
    dx = depth
    dy = depth * SLOPE

    x0, x1 = int(round(cx - half)), int(round(cx + half))
    y0, y1 = int(round(base - tall)), int(round(base))

    # THE FRONT. A rectangle: the biggest plane, and the one the silhouette is
    # read from. No slope on the bottom — it is standing on a floor.
    for x in range(max(0, x0), min(width, x1 + 1)):
        for y in range(max(0, y0), min(height, y1 + 1)):
            px[x, y] = tone(ramp, front, x, y, salt=salt)

    # THE RIGHT SIDE. A parallelogram running back from the front's right edge.
    for step in range(1, int(round(dx)) + 1):
        t = step / max(dx, 1.0)
        shift = int(round(t * dy))
        for y in range(max(0, y0 - shift), min(height, y1 - shift + 1)):
            x = x1 + step
            if 0 <= x < width:
                px[x, y] = tone(ramp, side, x, y, salt=salt)

    # THE TOP. The front's upper edge pushed up and right — a parallelogram,
    # not a rhombus, which is the difference between "seen from the front and
    # above" and "seen corner-on".
    for step in range(int(round(dx)) + 1):
        t = step / max(dx, 1.0)
        shift = int(round(t * dy))
        for x in range(max(0, x0 + step), min(width, x1 + step + 1)):
            y = y0 - shift
            if 0 <= y < height:
                px[x, y] = tone(ramp, top, x, y, salt=salt)

    # The terminator between the top and the front: one step down, no line
    # (S6 — interior form breaks are a value step).
    for x in range(max(0, x0), min(width, x1 + 1)):
        if 0 <= y0 < height:
            px[x, y0] = tone(ramp, top - 1, x, y0, salt=salt)

    # AMBIENT OCCLUSION at the contact (S10), inside the sprite, above the
    # shadow. It is what plants the thing rather than parking it.
    for x in range(max(0, x0), min(width, x1 + 1)):
        if 0 <= y1 < height:
            px[x, y1] = tone(ramp, SIDE, x, y1, salt=salt)


def make_kit(w: int, h: int, variant: int, rng: random.Random) -> Image.Image:
    """One piece of the trader's own kit. Five, and every one is shut.

    EVERY FRAME KEEPS A MARGIN. The drawings are laid out against `base` and
    `cx` below with two rows spare at the bottom for the contact patch and a
    pixel either side for the keyline, because the previous cut had all five
    running off their own cells — `outline` had nothing to draw on at the edge,
    `shadow` had nowhere to go, and the sheet packed five objects that each
    ended in a hard vertical cut.
    """
    img = Image.new("RGBA", (w, h), TRANSPARENT)
    px = img.load()
    # LEFT OF CENTRE, because `_block` shears to the RIGHT: an object drawn on
    # the frame's centreline puts its whole top plane and its shade side over
    # the right-hand edge. The offset is the deepest shear on the sheet.
    cx = (w - 1) / 2.0 - 2.5
    # Two rows under the object: one for its keyline, one for the contact
    # patch's. `outline` runs over the shadow too (it tests alpha, not which
    # pass wrote the pixel), which is the house convention every sheet in
    # `make_objects` keeps — so the patch needs a row of its own to be outlined
    # into, or the line lands outside the frame and the sprite ends in a cut.
    base = h - 5

    if variant == 0:
        # ROPED CRATES: two blocks at 1 : 0.62 by footprint (S17), the upper
        # one set BACK on the lower's lid rather than centred, so you can see
        # the surface it is standing on. That is what makes it a stack instead
        # of a wedding cake.
        _block(px, (w, h), cx, base, 6.5, 11.0, 4.5, WOOD_WORN, salt=901)
        _block(px, (w, h), cx + 1.0, base - 12.0, 4.0, 7.0, 3.0, WOOD, salt=903)
        # The cord: over both lids and down the front of the lower box. Two
        # runs, not a lattice — at this size a net is noise.
        for y in range(int(base - 11), int(base) + 1):
            for x in (int(cx - 2), int(cx + 2)):
                if 0 <= x < w and px[x, y][3]:
                    px[x, y] = tone(ROPE, FRONT, x, y)

    elif variant == 1:
        # A BARREL OF RODS. Round against four squares — the set needs one
        # non-box silhouette or five crates read as one crate drawn five times
        # (S15: the top contour carries the identity). The rods standing out of
        # it are the only thing on the sheet that breaks its own top edge,
        # which is what makes this frame findable in a row.
        top_y = base - 15
        for y in range(int(top_y), int(base) + 1):
            t = (y - top_y) / max(base - top_y, 1)
            r = 6.0 - t * 0.5
            for x in range(int(cx - r), int(cx + r) + 1):
                if not (0 <= x < w):
                    continue
                across = (x - cx) / max(r, 0.5)
                # Staves: a coarse band per 3px, never a per-pixel jitter (S5).
                stave = int((x - cx) // 3)
                plane = TOP if across < -0.25 else (FRONT if across < 0.45 else SIDE)
                bump = 1 if hash01(stave, 0, 907) > 0.60 else 0
                px[x, y] = tone(WOOD_WORN, max(SIDE, plane - bump), x, y)
        for hoop in (int(top_y + 3), int(base - 3)):
            for x in range(w):
                if 0 <= hoop < h and px[x, hoop][3]:
                    px[x, hoop] = tone(IRON, FRONT, x, hoop)
        # The open top, as a squashed disc — the one place you see into it.
        cap(px, (w, h), cx, top_y, 6.0, 6.0, WOOD_WORN, FRONT - 1, squash=0.45)
        for index in range(4):
            rx = cx - 3.5 + index * 2.4
            lean = 0.10 * (1 if index % 2 else -1)
            for y in range(int(top_y - 8 + (index % 2) * 2), int(top_y + 2)):
                x = int(round(rx + (y - top_y) * lean))
                if 0 <= x < w and 0 <= y < h:
                    px[x, y] = tone(IRON, FRONT if index % 2 else TOP - 1, x, y)

    elif variant == 2:
        # THE RACK. Not placed — see the block comment above. Two uprights, a
        # rail across them, and rods leaning on it.
        for side in (-1, 1):
            _block(px, (w, h), cx + side * 4.6, base, 1.3, 19.0, 1.8,
                   WOOD_WORN, salt=917)
        # Two rails, not one. A single bar between two posts is a goalpost; the
        # second rail lower down is what says the rods are being HELD rather
        # than leaning against something.
        for rail in (16.0, 6.0):
            billet(px, (w, h), cx - 6.0, cx + 6.2, base - rail, 1.4, WOOD,
                   cap=False)
        for index in range(3):
            rx = cx - 4.2 + index * 4.2
            for y in range(int(base - 21), int(base) - 1):
                x = int(round(rx + (y - base + 11) * 0.12))
                if 0 <= x < w and 0 <= y < h:
                    px[x, y] = tone(IRON, FRONT if index != 1 else TOP - 2, x, y)

    elif variant == 3:
        # A PLANK SHELF OF TINS. Low and wide, with the tins in a
        # `1 : 0.7 : 0.5` rhythm of heights (S17) rather than a row of equals.
        for side in (-1, 1):
            _block(px, (w, h), cx + side * 5.0, base, 1.5, 9.0, 2.0,
                   WOOD_WORN, salt=921)
        _block(px, (w, h), cx, base - 9.0, 6.0, 1.5, 4.0, WOOD, salt=922)
        # SPACED SO THEY DO NOT FUSE. At 1.6 of half-width on a 4.0 pitch the
        # three tins had 0.8px between them, which `outline` then closed up
        # into one grey lump on a plank. A repeated element needs a gap wider
        # than the keyline that is about to be drawn round it.
        for index, tall in enumerate((8.0, 5.5, 4.0)):
            _block(px, (w, h), cx - 4.8 + index * 4.8, base - 10.5,
                   1.4, tall, 1.6, IRON if index != 1 else BRASS,
                   salt=923 + index)

    else:
        # THE STRONGBOX. Iron-bound, and the one frame with a PADLOCK — the
        # sheet's clearest single statement that none of this opens. The lock
        # is BRASS, the zone's accent, and the sprite's only saturated pixels.
        # TALLER THAN IT LOOKS IT SHOULD BE. At thirteen it came out at 0.9
        # height to footprint, under S3's floor of 1.1 — a strongbox lying down.
        # A safe is a thing that stands.
        _block(px, (w, h), cx, base, 6.5, 17.0, 4.5, WOOD, salt=931)
        lid = base - 17.0
        for band in (-3, 3):
            bx = int(round(cx + band))
            for y in range(int(lid) + 1, int(base)):
                if 0 <= bx < w and px[bx, y][3]:
                    px[bx, y] = tone(IRON, FRONT, bx, y)
        # A strap across the lid's front edge, so the box reads as CLOSED
        # rather than as a box that happens to have a lid on it.
        for x in range(int(cx - 6.5), int(cx + 6.5) + 1):
            y = int(lid) + 1
            if 0 <= x < w and 0 <= y < h and px[x, y][3]:
                px[x, y] = tone(IRON, TOP - 2, x, y)
        hx, hy = int(cx), int(lid + 5)
        for y in range(hy, hy + 3):
            for x in range(hx - 1, hx + 2):
                if 0 <= x < w and 0 <= y < h and px[x, y][3]:
                    px[x, y] = tone(BRASS, TOP if y == hy else FRONT, x, y)

    # THE CONTACT PATCH, SIZED TO LEAVE ITS OWN KEYLINE A ROW. `outline` runs
    # after this and tests alpha rather than which pass wrote a pixel, so the
    # patch gets a line drawn round it too — which means the shadow's reach,
    # not the object's, is what decides whether a frame clips. It is the
    # house convention (every sheet in `make_objects` does shadow then
    # outline) and it is cheaper to fit the ellipse than to diverge from it.
    shadow(img, cx + 2.0, base + 0.5, 7.5, 1.4)
    outline(img, OUTLINE)
    return img



# --- light ------------------------------------------------------------------
# Additive, drawn after the darkness pass. `torchfire` carries its own WARM
# colour rather than being tinted at draw time: a flame is not one hue, it is a
# ramp from a dull red root to a white core, and a single draw-time multiply
# cannot produce that. `glow` stays neutral and takes the coin's gold, because
# what it is marking is a price.


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
RUG_VARIANTS = 3
BRICK_VARIANTS = 2
FLOOR_VARIANTS = 4
COUNTER_KINDS = 3
SHELF_VARIANTS = 3
CRATE_VARIANTS = 3
LAMP_VARIANTS = 2
TORCHFIRE_FRAMES = 12
TORCHFIRE_FPS = 12
LAMPFIRE_FRAMES = 12
LAMPFIRE_FPS = 10
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




def _check_margins(name: str, frames: list[Image.Image]) -> None:
    """Fail if any frame's SOLID ink touches its own cell's edge.

    THIS EXISTS BECAUSE THE KIT SHIPPED CLIPPED FOR A WHILE AND NOTHING SAID SO.
    All five frames ran off the bottom and the right of their cells: the
    drawings were sized to fill a box they did not fit in, so `outline` had no
    row to put a keyline in and every silhouette ended in a hard vertical cut.
    Nothing in the pipeline notices — a packed sheet with clipped frames is a
    perfectly valid PNG — and in the game it reads as "the art is wrong"
    without ever reading as "the art is CROPPED", which is why it survived a
    pass. One bbox per frame is cheap and it is the only check this file has.

    SOLID ink only: the contact patch is translucent and is ALLOWED to reach
    the bottom row, because a shadow is the ground and not the object.
    """
    bad: list[str] = []
    for index, frame in enumerate(frames):
        px = frame.load()
        pts = [
            (x, y)
            for y in range(frame.height)
            for x in range(frame.width)
            if px[x, y][3] > 200
        ]
        if not pts:
            continue
        left = min(p[0] for p in pts)
        right = max(p[0] for p in pts)
        top = min(p[1] for p in pts)
        bottom = max(p[1] for p in pts)
        touched = [
            edge for edge, hit in (
                ("left", left == 0),
                ("right", right == frame.width - 1),
                ("top", top == 0),
                ("bottom", bottom == frame.height - 1),
            ) if hit
        ]
        if touched:
            bad.append(f"{name}[{index}] touches {', '.join(touched)}")
    if bad:
        raise SystemExit(
            "clipped frames — give the drawing room or grow the cell:\n  "
            + "\n  ".join(bad)
        )


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "store"
    out_dir.mkdir(parents=True, exist_ok=True)

    # THE MASONRY. One frame per WEAR variant, picked by a hash on the tile —
    # there is no neighbour mask, see `make_brick`. Generated-asset lists are
    # APPEND-ONLY: a new variant goes on the END, never in the middle, because
    # inserting one moves every frame index after it.
    wall_w, wall_h = tile, round(tile * TILE_WALL_H)
    # PLAIN FRAMES FIRST, then the crowned ones — `layers/terrain` indexes
    # `variant` for a tile with masonry to its north and `BRICK_PLAIN + variant`
    # for one on the top edge of the wall. Append-only: a new wear variant goes
    # on the end of EACH half, and both halves move together or the client's
    # offset is wrong.
    walls = [make_brick(wall_w, wall_h, v, crown=False) for v in range(BRICK_VARIANTS)]
    walls += [make_brick(wall_w, wall_h, v, crown=True) for v in range(BRICK_VARIANTS)]
    pack(walls, wall_w, wall_h).save(out_dir / "brick.png")

    floors = [
        make_tilefloor(tile, v, random.Random(args.seed + 4300 + v))
        for v in range(FLOOR_VARIANTS)
    ]
    pack(floors, tile, tile).save(out_dir / "tilefloor.png")

    counter_w = round(tile * TILE_COUNTER_W)
    counter_h = round(tile * TILE_COUNTER_H)
    counters = [
        make_counter(counter_w, counter_h, kind, random.Random(args.seed + 1400 + kind))
        for kind in range(COUNTER_KINDS)
    ]
    pack(counters, counter_w, counter_h).save(out_dir / "counter.png")

    shelf_w = round(tile * TILE_SHELF_W)
    shelf_h = round(tile * TILE_SHELF_H)
    shelves = [
        make_shelf(shelf_w, shelf_h, v, random.Random(args.seed + 1700 + v))
        for v in range(SHELF_VARIANTS)
    ]
    pack(shelves, shelf_w, shelf_h).save(out_dir / "shelf.png")

    crate_w = round(tile * TILE_CRATE_W)
    crate_h = round(tile * TILE_CRATE_H)
    crates = [
        make_crate(crate_w, crate_h, v, random.Random(args.seed + 1800 + v))
        for v in range(CRATE_VARIANTS)
    ]
    _check_margins("crate", crates)
    pack(crates, crate_w, crate_h).save(out_dir / "crate.png")

    lamp_w = round(tile * TILE_LAMP_W)
    lamp_h = round(tile * TILE_LAMP_H)
    lamps = [
        make_lamp(lamp_w, lamp_h, v, random.Random(args.seed + 1900 + v))
        for v in range(LAMP_VARIANTS)
    ]
    _check_margins("lamp", lamps)
    pack(lamps, lamp_w, lamp_h).save(out_dir / "lamp.png")

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

    # THE LAMP'S FLAME IS THE TORCH'S FLAME, SMALLER. It is the same generator
    # because it is the same fire: a wick in a warm room and a wick on a post
    # in a yard differ in scale and in what is around them, not in how they
    # burn. A second flame recipe would be a second opinion about what fire
    # looks like in this game, and the two would drift the first time one was
    # retuned.
    lamp_fire_w, lamp_fire_h = round(tile * 0.875), round(tile * 1.25)
    lamp_fire_anchor = lamp_fire_h - 3
    lamp_fire = make_torchfire(lamp_fire_w, lamp_fire_h, LAMPFIRE_FRAMES, lamp_fire_anchor)
    pack(lamp_fire, lamp_fire_w, lamp_fire_h).save(out_dir / "lampfire.png")

    glow_w, glow_h = tile * 2, tile
    glow_anchor = glow_h - 4
    glow = make_glow(glow_w, glow_h, GLOW_FRAMES, glow_anchor)
    pack(glow, glow_w, glow_h).save(out_dir / "glow.png")

    for name, frames in (("torchfire", fire), ("lampfire", lamp_fire), ("glow", glow)):
        margin = _loop_seam(frames)
        print(f"  loop {name}: wrap step vs worst inner step = {margin:+d}")
        if margin > 0:
            raise SystemExit(f"{name} snaps at the wrap — phase it, do not roll it")

    kits = [
        make_kit(TILE_KIT_W, TILE_KIT_H, index, random.Random(args.seed + 900 + index))
        for index in range(5)
    ]
    _check_margins("kit", kits)
    pack(kits, TILE_KIT_W, TILE_KIT_H).save(out_dir / "kit.png")

    wagon_w, wagon_h = round(tile * TILE_WAGON_W), round(tile * TILE_WAGON_H)
    wagon = make_wagon(wagon_w, wagon_h, random.Random(args.seed + 1300))
    pack([wagon], wagon_w, wagon_h).save(out_dir / "wagon.png")

    manifest = {
        "tile": tile,
        "seed": args.seed,
        # THE BUILDING'S OWN SURFACES. `brick` is a PROP because a wall stands
        # up — it is two tiles tall on a one-tile footprint, bottom-anchored,
        # exactly like a tree's canopy. `tilefloor` is GROUND: baked flat into
        # the ground canvas under everything, with no keyline and no shadow.
        # The split is the same one `make_scenery.py` makes between a standing
        # prop and a decal, and for the same reason.
        "ground": {
            "tilefloor": {
                "file": "tilefloor.png", "frameWidth": tile, "frameHeight": tile,
                "frames": len(floors),
            },
        },
        # PROPS: bottom-anchored, depth-sorted with the party.
        "props": {
            # THE MASONRY. One tile of brick face per tile, plus a TRIM on the
            # tiles that are on the top edge of the wall mass — the ones with
            # no masonry to the NORTH. See `make_brick`: that one question is
            # what makes the back wall a lidded band, the side walls solid
            # vertical bands, and the front wall something you see over.
            "brick": {
                "file": "brick.png", "frameWidth": wall_w, "frameHeight": wall_h,
                "frames": len(walls), "sway": 0,
                # How many PLAIN frames come first. The rest carry the trim.
                # Shipped rather than assumed so the split is never hardcoded
                # on the client — see `make_brick` for what the two are.
                "plain": BRICK_VARIANTS,
            },
            # THE COUNTER, as three tiling sections. Kind order is fixed and
            # mirrored by `store.COUNTER_L`'s third field: 0 elbow, 1 east,
            # 2 south.
            "counter": {
                "file": "counter.png", "frameWidth": counter_w,
                "frameHeight": counter_h, "frames": len(counters), "sway": 0,
            },
            "shelf": {
                "file": "shelf.png", "frameWidth": shelf_w,
                "frameHeight": shelf_h, "frames": len(shelves), "sway": 0,
            },
            "crate": {
                "file": "crate.png", "frameWidth": crate_w,
                "frameHeight": crate_h, "frames": len(crates), "sway": 0,
            },
            # THE LAMPS. Ordinary standing props: they sit on the floor on
            # their own small tables and sort like anything else. `flameY` is
            # the row `lampfire` burns at inside the chimney, which is art —
            # the client never picks it.
            "lamp": {
                "file": "lamp.png", "frameWidth": lamp_w, "frameHeight": lamp_h,
                "frames": len(lamps), "sway": 0,
                "flameY": LAMP_FLAME_Y,
            },
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
            # HIS CART, one frame, parked in the yard. The biggest sprite in
            # the zone and the one that says where the stock comes from.
            "wagon": {
                "file": "wagon.png", "frameWidth": wagon_w,
                "frameHeight": wagon_h, "frames": 1, "sway": 0,
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
            "lampfire": {
                "file": "lampfire.png", "frameWidth": lamp_fire_w,
                "frameHeight": lamp_fire_h, "frames": LAMPFIRE_FRAMES,
                "fps": LAMPFIRE_FPS, "anchorY": lamp_fire_anchor,
                "loop": True, "tinted": False,
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
        f"brick {len(walls)}x{wall_w}x{wall_h}, "
        f"tilefloor {len(floors)}x{tile}x{tile}, "
        f"counter {len(counters)}x{counter_w}x{counter_h}, "
        f"shelf {len(shelves)}x{shelf_w}x{shelf_h}, "
        f"crate {len(crates)}x{crate_w}x{crate_h}, "
        f"lamp {len(lamps)}x{lamp_w}x{lamp_h}, "
        f"table {len(tables)}x{table_w}x{table_h}, "
        f"wagon 1x{wagon_w}x{wagon_h}, "
        f"kit {len(kits)}x{TILE_KIT_W}x{TILE_KIT_H}, "
        f"torch {len(torches)}x{torch_w}x{torch_h}, "
        f"rug {len(rugs)}x{rug_w}x{rug_h}, "
        f"torchfire {TORCHFIRE_FRAMES}x{fire_w}x{fire_h} @{TORCHFIRE_FPS}fps, "
        f"lampfire {LAMPFIRE_FRAMES}x{lamp_fire_w}x{lamp_fire_h} @{LAMPFIRE_FPS}fps, "
        f"glow {GLOW_FRAMES}x{glow_w}x{glow_h} @{GLOW_FPS}fps"
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--preview", default="",
                    help="write a scaled mock-up of the shop HERE (outside "
                         "the tree) for eyeballing the art")
    ap.add_argument("--preview-scale", type=int, default=6)
    args = ap.parse_args()
    out_dir = build(args)
    if args.preview:
        _preview(out_dir, Path(args.preview), args.preview_scale, args.tile)


def _preview(out_dir: Path, path: Path, scale: int, tile: int) -> None:
    """A mock-up of the SHOP INTERIOR, built from the real map and really lit.

    Not shipped, and not how the client composes the scene. It exists so the
    room can be judged as a ROOM — which is the only way to judge the two
    things this zone is actually for, the value hierarchy and the CALM, and
    neither of them is visible in a folder of fourteen sheets.

    IT READS `server/app/store.py` RATHER THAN LAYING OUT ITS OWN MOCK. The
    previous version hand-placed a plausible shop, which meant it could look
    fine while the real one did not: it was checking the art against a second
    opinion about the layout instead of against the layout. Everything below —
    where the walls are, where the counter turns, how much empty floor there
    is between the door and the first table — comes off the same offsets the
    server ships.

    THE LIGHT IS FAKED HERE ON PURPOSE, and it is the crudest possible version
    of what the client does: an ambient floor at `zones.STORE_AMBIENT` plus one
    warm radial per lamp, summed and clamped. It is not the renderer and it is
    not trying to be. What it answers is the only question the art cannot
    answer on its own — whether five short pools on a dark red floor come out
    as an evenly lit room or as five bright holes — and that question is worth
    a hundred lines of approximation.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import store as layout                       # noqa: E402
    from app.world import BRICK, FLOOR, TILEFLOOR         # noqa: E402
    from app.zones import STORE_AMBIENT                   # noqa: E402

    world = layout.build_store(1, 7, takes=[120, 90, 60])
    fixtures = world.store
    left, top, right, bottom = layout.shop_bounds(world.width)
    # Crop to the building plus a row of yard, so the picture is the ROOM.
    x0, x1 = left - 1, right + 1
    y0, y1 = top - 1, bottom + 2
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new("RGBA", (cols * tile, rows * tile), (10, 8, 9, 255))

    manifest = json.loads((out_dir / "manifest.json").read_text())
    sheets: dict[str, tuple[Image.Image, dict]] = {}

    def sheet(group: str, name: str) -> tuple[Image.Image, dict]:
        if name not in sheets:
            spec = manifest[group][name]
            sheets[name] = (Image.open(out_dir / spec["file"]).convert("RGBA"), spec)
        return sheets[name]

    def blit(img: Image.Image, spec: dict, frame: int, px: float, py: float,
             centred: bool = False) -> None:
        fw, fh = spec["frameWidth"], spec["frameHeight"]
        cut = img.crop((frame % spec["frames"] * fw, 0,
                        (frame % spec["frames"] + 1) * fw, fh))
        canvas.alpha_composite(
            cut,
            (int(px - fw / 2), int(py - (fh / 2 if centred else fh))),
        )

    def at(wx: float, wy: float) -> tuple[float, float]:
        """World pixels -> canvas pixels."""
        return wx - x0 * tile, wy - y0 * tile

    # THE GROUND. The shop's paving inside, plain dirt outside — the yard is
    # only here so the door reads as a door rather than as a gap.
    floor_img, floor_spec = sheet("ground", "tilefloor")
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if not (0 <= ty < world.height and 0 <= tx < world.width):
                continue
            kind = world.tiles[ty][tx]
            cx_, cy_ = (tx - x0) * tile, (ty - y0) * tile
            # INSIDE THE WALLS, ANYTHING THAT IS NOT MASONRY IS FLOOR. The
            # fixtures claim their own footprints as LOW cover (`store._claim`)
            # so bodies cannot walk through a table, and those tiles are still
            # FLOOR as far as the eye is concerned — the client's terrain layer
            # treats LOW exactly the same way. Painting only TILEFLOOR left a
            # black hole under every table, counter, shelf and crate in the
            # room, which is what this preview looked like the first time.
            inside = left < tx < right and top < ty < bottom
            if kind == TILEFLOOR or (inside and kind != BRICK):
                frame = int(hash01(tx, ty, 131) * floor_spec["frames"])
                blit(floor_img, floor_spec, frame, cx_ + tile / 2, cy_ + tile)
            elif kind != BRICK:
                canvas.paste((34, 27, 21, 255), (cx_, cy_, cx_ + tile, cy_ + tile))

    # THE MATS, flat, before anything stands on them.
    rug_img, rug_spec = sheet("decals", "rug")
    for rx, ry, variant in fixtures["rugs"]:
        px_, py_ = at(rx, ry)
        blit(rug_img, rug_spec, variant, px_, py_, centred=True)

    # EVERYTHING THAT STANDS UP, in one depth sort by contact row — the same
    # order the renderer uses, which is what makes the walls occlude correctly.
    standing: list[tuple[float, str, float, float, int]] = []
    brick_img, brick_spec = sheet("props", "brick")
    plain = brick_spec["plain"]
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if not (0 <= ty < world.height and 0 <= tx < world.width):
                continue
            if world.tiles[ty][tx] != BRICK:
                continue
            # The trim belongs to tiles on the wall's top edge: no masonry to
            # the north. See `make_brick`.
            crown = ty == 0 or world.tiles[ty - 1][tx] != BRICK
            wear = int(hash01(tx, ty, 137) * plain) % plain
            standing.append((
                (ty + 1) * tile, "brick",
                (tx + 0.5) * tile, (ty + 1) * tile,
                plain + wear if crown else wear,
            ))
    for name, key, field in (
        ("counter", "counter", 2), ("shelf", "shelves", 2),
        ("crate", "crates", 2), ("lamp", "lamps", -1),
    ):
        for row in fixtures[key]:
            variant = row[field] if field >= 0 else 0
            standing.append((row[1], name, row[0], row[1], variant))
    for stand in fixtures["stands"]:
        standing.append((stand["y"], "table", stand["x"], stand["y"], stand["v"]))
    standing.sort(key=lambda row: row[0])

    for _, name, wx, wy, frame in standing:
        img, spec = sheet("props", name)
        px_, py_ = at(wx, wy)
        blit(img, spec, frame, px_, py_)

    # THE LIGHT. Ambient floor plus one warm pool per lamp, summed and clamped
    # — see the docstring. The pools are placed at the BULB, which is what the
    # server does with `LAMP_HANG_TILES`, not at the floor contact.
    lamp_spec = sheets["lamp"][1]
    bulb = lamp_spec["frameHeight"] - lamp_spec["flameY"]
    # The reach is the SERVER's number, not a second copy — the whole value of
    # this preview is that it lies about as little as possible.
    reach = layout.LAMP_LIGHT_TILES * tile
    lit = canvas.load()
    for y in range(canvas.height):
        for x in range(canvas.width):
            level = STORE_AMBIENT
            for lx, ly in fixtures["lamps"]:
                bx, by = at(lx, ly - bulb)
                d = math.hypot(x - bx, y - by) / reach
                if d < 1.0:
                    level += 0.55 * (1.0 - d) ** 2
            level = min(1.15, level)
            r, g, b, a = lit[x, y]
            # Warm the light as well as raising it: a lamp is not a dimmer.
            lit[x, y] = (
                min(255, int(r * level * 1.10)),
                min(255, int(g * level * 0.96)),
                min(255, int(b * level * 0.84)),
                a,
            )

    canvas.resize((canvas.width * scale, canvas.height * scale),
                  Image.NEAREST).save(path)
    print(f"preview -> {path}  ({cols}x{rows} tiles)")


if __name__ == "__main__":
    main()
