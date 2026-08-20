#!/usr/bin/env python3
"""Asset pipeline: things PEOPLE left in the forest.

Fourth generator in the family, after make_textures.py (the forest itself),
make_vfx.py and make_hud_icons.py. Same rules: no raw stage, final-resolution
pixels straight into assets/processed/, deterministic, shading helpers imported
from make_textures rather than copied.

This module draws what is STILL and what has STOPPED. The objects a player
walks up and interacts with — barrels, boxes, chests, stashes, vehicles,
altars — are drawn in `make_objects.py` and packed by `build()` here, into the
same folder and the same manifest, because the client keys its atlas off that
one manifest and a second one would buy nothing.

THERE ARE NO BUILDINGS. A cabin sheet used to live here and it was the largest
asset in the game; it was cut with the homestead scene that placed it. A
procedurally dropped house teaches the player "house = loot" inside two
expeditions, and after that the forest is a list of houses. What replaced it
is a vocabulary of things somebody drove, packed, buried or carved — see
`make_objects.py` — which does the same navigational job without ever
resolving into one repeated noun.

Output (assets/processed/scenery/):

  standing — bottom-anchored silhouettes, depth-sorted with the party
    tent.png       3 frames, 32x28   canvas, sagging / collapsed / torn open.
                                     The forest no longer places one; the
                                     MERCHANT is pitched in it (store.py).
    fence.png      6 frames, 16x22   post-and-rail, whole through to splintered
    sign.png       3 frames, 16x28   a board on a post. SWAYS.
    logs.png       4 frames, 32x14   a felled trunk lying across the ground
    firepit.png    3 frames, 20x12   cold stones and burnt wood. SMOKES.
    statue.png     6 frames, 16x36   carved stone. See make_objects.py.
    barrel/crate/box/chest/stash/vehicle/altar
                                     animated, kind-major. make_objects.py.

  decals — flat, no outline, baked into the client's ground canvas
    blood.png      6 frames, 32x32   spray, pool, drag, spatter, arc, print
    tracks.png     8 frames, 16x16   one pair of boot prints per compass point
    clothes.png    5 frames, 20x16   shirt, coat, pack, boot, hat
    debris.png     6 frames, 16x16   bottle, planks, bones, lantern, crockery,
                                     a wheel
    bones.png      6 frames, 16x16   skull, ribs, scatter, ash. make_objects.py
    oil.png        4 frames, 32x32   a slick under a dead engine.
    manifest.json

WHY THIS IS A SEPARATE FOLDER FROM terrain/
`terrain/` is the place: soil, stone, wood that grew there. Everything here was
CARRIED in by somebody, and the difference is not decorative. Terrain is
scattered by the client off the map seed, because a rock does not mean
anything and one rock is as good as another. Scenery is PLACED by the server
in groups (see server/app/scenery.py), because a tent, a cold firepit and a
blood trail leading away from them are one sentence and shuffling them breaks
it. Two folders, two manifests, two placement rules — one for texture, one for
narrative.

HOW A STANDING PROP IS BUILT. Three primitives and one camera, all shared with
`make_objects.py` so a fence post and a crate are the same solid in the same
light: `_box` (a dimetric box with a top face and two walls — posts, boards,
sign planks), `_billet` (a cylinder with a lit crest, a wide flank, a thin
underside and a sawn end — trunks, rails, ridge poles) and `_stone` (a faceted
boulder). Every one of them bands on `TOP` / `FRONT` / `SIDE` and never on a
falloff. `_shadow` puts the contact patch under the result.

STANDING VS DECAL is the other split, and it is a drawing rule as much as a
sorting one. A standing prop has an OUTLINE and shading that implies a face
turned toward the camera; it is depth-sorted with the bodies, so the player
walks in front of and behind it. A decal has neither: it lies on the floor, it
is baked into the ground canvas, and giving it a keyline would make it read as
a thing standing up at ankle height.

READ ORDER AT 16px. Every silhouette here has to survive being three tiles
tall on a dark screen with a lantern moving across it. What carries is
VALUE and SHAPE, never hue and never fine detail: a firepit is a light stone
ring around a dark middle, a totem is a narrow column with bright notches down
it, and a blood pool is the only near-red on the forest floor.

Usage:
    python tools/make_scenery.py
    python tools/make_scenery.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

import make_objects as objects
from make_textures import (
    BLOOD,
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    clamp01,
    hash01,
    outline,
    pack,
    pick,
    rgb,
)

# --- palette ----------------------------------------------------------------
# Worked material against the forest's palette in make_textures.py. Wood here
# is GREYER than a living trunk and colder than the leaf litter: a plank has
# been out in the weather, and if it shares the bark ramp a cabin reads as a
# very square tree.

PLANK: Ramp = [rgb(c) for c in ("#1b1710", "#272118", "#342c20", "#413628", "#4f4232")]
PLANK_DARK: Ramp = [rgb(c) for c in ("#100d09", "#181410", "#211b15", "#2b2419")]
#: Six steps, not five, so canvas indexes on the same plane table (`TOP` /
#: `FRONT` / `SIDE`) as every other volume here. The added step is at the top:
#: a tent is the one thing in the clearing with a large surface angled at the
#: sky, and it needs somewhere to put it.
CANVAS: Ramp = [rgb(c) for c in ("#171410", "#241f18", "#332c22", "#4e4433", "#655945", "#847457")]
METAL: Ramp = [rgb(c) for c in ("#16181b", "#212429", "#2e3238", "#3d4249", "#4d535b")]
GLASS: Ramp = [rgb(c) for c in ("#1c242b", "#2a3742", "#3d4f5d", "#56707f", "#7794a4")]
STONE: Ramp = [rgb(c) for c in ("#1e1d21", "#2a292e", "#37353b", "#454249", "#545059")]
CHAR: Ramp = [rgb(c) for c in ("#0a0908", "#131110", "#1e1a17", "#2b2420", "#3a2f26")]
BONE: Ramp = [rgb(c) for c in ("#38362e", "#49463c", "#5c584b", "#726d5c", "#8a8471")]
ROPE: Ramp = [rgb(c) for c in ("#2b2418", "#3a3120", "#4a3f29", "#5b4e33")]

# BLOOD is imported from make_textures: the stain on the floor here and the
# wound on a body in make_gore.py are the same material.

# Abandoned clothing. Four washed-out dye lots — the point is that a person
# chose these, so they are the one place in the forest with arbitrary hue.
CLOTH_RUST: Ramp = [rgb(c) for c in ("#2a1712", "#3b2019", "#4d2a20", "#603428")]
CLOTH_BLUE: Ramp = [rgb(c) for c in ("#161d26", "#1f2833", "#2a3542", "#374553")]
CLOTH_OLIVE: Ramp = [rgb(c) for c in ("#1d2016", "#272b1d", "#333825", "#40462e")]
CLOTH_PALE: Ramp = [rgb(c) for c in ("#2e2c26", "#3d3a32", "#4d493e", "#5f5a4c")]
CLOTHS = (CLOTH_RUST, CLOTH_BLUE, CLOTH_OLIVE, CLOTH_PALE)

LEATHER: Ramp = [rgb(c) for c in ("#1a1310", "#251b16", "#31241c", "#3f2f24")]

# Soil pushed out of a footprint. Lighter than any ground texture in
# make_textures.py on purpose — it is the ONLY part of a print that is visible
# at night, and it has to beat the darkest soil the print might land on.
DISPLACED: Ramp = [rgb(c) for c in ("#4a4033", "#574c3c", "#645845")]

OUTLINE_WOOD = rgb("#0c0a07")
OUTLINE_COLD = rgb("#0a0b0d")

# Peak horizontal lean, in world px, for a prop the client animates. A sign on
# a post is the only thing out here with enough leverage to move visibly; the
# tent's canvas breathes about a third as far.
SWAY_SIGN = 1.6
SWAY_TENT = 0.5


# --- shared drawing ---------------------------------------------------------



# THE CAMERA, AND IT IS NOT THIS MODULE'S. `objects.SLOPE` is the 2:1 dimetric
# every crate and barrel in the folder is built on, and these props stand in
# the same clearing. `objects.tone` is its flat-step painter. Both are imported
# rather than restated for the reason spelled out beside them there.
#
# WHAT THESE PRIMITIVES REPLACED. Every prop below used to be a front elevation
# shaded by `pick(ramp, <continuous value>)` — a gradient with a dither on it,
# which S7 rules out and which the crates and the guns had both already stopped
# doing. The result was a folder where a crate was a solid object and the fence
# beside it was a sticker of a fence. A volume here is now BANDS: a top plane,
# a near plane two steps under it, a far plane two under that, and a contact
# row darker than all three. No value between the bands, ever.
SLOPE = objects.SLOPE
TOP, FRONT, SIDE = objects.PLANE_TOP, objects.PLANE_FRONT, objects.PLANE_SIDE
#: Wood and stone come from `make_objects` too, so a fence rail and a crate
#: slat are cut from the same tree. The five-step ramps at the top of this file
#: stay for the DECALS, which are flat by contract and want a continuous value.
BEAM: Ramp = objects.PLANK
ROCK: Ramp = objects.STONE


#: The volume toolkit lives in `make_objects.py` — see the block above its
#: crate helpers. Aliased rather than re-exported so the call sites here stay
#: short and the ownership stays obvious.
_shadow, _box, _billet, _stone = (
    objects.shadow, objects.box, objects.billet, objects.stone
)


def _stroke(px, x: float, y: float, angle: float, length: float, thick: float,
            ramp: Ramp, shade: float, salt: int, width: int, height: int) -> None:
    """A tapering line of pixels. The workhorse for planks, rails and bones."""
    for step in range(int(length)):
        t = step / max(length - 1, 1)
        ix = int(round(x + math.cos(angle) * step))
        iy = int(round(y + math.sin(angle) * step))
        half = max(0.0, thick * (1.0 - t * 0.35))
        for offset in range(-int(half), int(half) + 1):
            jy = iy + offset
            if 0 <= ix < width and 0 <= jy < height:
                px[ix, jy] = pick(
                    ramp, shade - offset * 0.16 + (hash01(ix, jy, salt) - 0.5) * 0.22, ix, jy
                )


# --- standing: camp remains -------------------------------------------------


def make_tent(width: int, height: int, state: int, rng: random.Random) -> Image.Image:
    """Canvas over two poles. `state` 0 sagging, 1 collapsed, 2 torn open.

    A TENT IS EXTRUDED, AND THAT IS THE ONLY WAY IT STOPS BEING A HILL. The
    old one drew the gable triangle flat and shaded it with a falloff to both
    sides; S15's own test — the silhouette in solid black — returns a cone,
    and no amount of shading inside a cone makes a shelter. Splitting the
    triangle down the middle into two "slopes" does not help either, because
    seen end-on a gable IS one plane, and drawing a value break across a flat
    wall is a drawing of a fold rather than a fold.

    So the triangle is swept BACK along the camera slope, far copy first and
    near copy last. What the nearest copy covers is the near gable, at the
    base plane. What the far copies leave sticking out along the top right is
    the ROOF, at the lit plane — a real surface, generated by the sweep rather
    than drawn, and automatically in perspective because the sweep runs on the
    same 2:1 the crates and the fence posts do. The ridge is where the two
    meet, and it needs no line: it is a two-step value break between planes
    that genuinely face different ways.

    The door is cut into the near gable, which is the only face the player can
    walk into, and it is the darkest thing on the sprite. The lit lip down one
    side is the flap pulled back — a black wedge with no rim reads as a hole
    punched in the sprite rather than as a way in.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)

    cx = (width - 1) / 2.0
    ground = height - 1
    collapsed = state == 1
    # WIDER THAN TALL. A ridge tent is a low thing you crawl into; pitched
    # steep it reads as a cone, which is the shape this prop keeps trying to
    # become. Base to height runs about 1.3:1 here, against S17's note that
    # the readable feature gets the room.
    ridge_y = height * (0.62 if collapsed else 0.32)
    gw = width * (0.46 if collapsed else 0.37)
    depth = int(width * (0.16 if collapsed else 0.26))

    def gable(ax: float, ay: float, by: float, plane: int) -> None:
        """One filled triangle: apex at (ax, ay), base `gw` either side at by."""
        for y in range(max(0, int(round(ay))), min(height, int(round(by)) + 1)):
            t = (y - ay) / max(by - ay, 1)
            span = gw * (0.08 + t * 0.92)
            for x in range(int(round(ax - span)), int(round(ax + span)) + 1):
                if 0 <= x < width:
                    px[x, y] = objects.tone(CANVAS, plane, x, y)

    # THE SWEEP. Far copy first, near copy last, each stepped back up-screen at
    # the camera slope. Everything but the last is roof.
    near_x = cx - depth * 0.5
    for offset in range(depth, -1, -1):
        gable(near_x + offset, ridge_y - offset * SLOPE,
              ground - offset * SLOPE, FRONT if offset == 0 else TOP)

    # The eave: the row where the roof meets the ground on the far side takes
    # the contact step, so the tent sits in the clearing instead of on it.
    for offset in range(1, depth + 1):
        y = int(round(ground - offset * SLOPE))
        for x in range(int(near_x + offset - gw), int(near_x + offset + gw) + 1):
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = objects.tone(CANVAS, SIDE, x, y)

    # Seams down the fall of the near gable, splaying with it the way real
    # panels do. One step under the plane they land on, so the ridge break
    # stays the loudest edge on the sprite.
    for column in (-0.58, 0.16, 0.62):
        for y in range(int(ridge_y) + 3, ground + 1):
            t = (y - ridge_y) / max(ground - ridge_y, 1)
            x = int(round(near_x + column * gw * (0.08 + t * 0.92)))
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = objects.tone(CANVAS, FRONT - 1, x, y)

    if not collapsed:
        mouth_h = (ground - ridge_y) * 0.52
        for step in range(int(mouth_h)):
            y = int(ground - step)
            spread = int(1 + (mouth_h - step) * 0.20)
            for x in range(int(near_x - spread), int(near_x + spread) + 1):
                if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                    px[x, y] = objects.tone(PLANK_DARK, 0, x, y)
            for edge, plane in ((int(near_x - spread) - 1, TOP),
                                (int(near_x + spread) + 1, SIDE)):
                if 0 <= edge < width and 0 <= y < height and px[edge, y][3]:
                    px[edge, y] = objects.tone(CANVAS, plane, edge, y)

    if state == 2:
        # A tear in the ROOF, where a branch would come through — edges lit so
        # the canvas reads as split rather than as a painted hole.
        tear_x = near_x + depth * 0.7
        for step in range(int(height * 0.22)):
            y = int(ridge_y + 2 + step)
            spread = int(1 + step * 0.26)
            wobble = int(math.sin(step * 1.3) * 1.2)
            lo = int(tear_x) - spread + wobble
            for x in range(lo, int(tear_x) + spread + wobble):
                if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                    px[x, y] = objects.tone(PLANK_DARK, 0, x, y)
            if 0 <= lo - 1 < width and 0 <= y < height and px[lo - 1, y][3]:
                px[lo - 1, y] = objects.tone(CANVAS, TOP, lo - 1, y)

    # Poles: one still up at the near gable, one down. The one on the ground
    # is why it sagged.
    _box(px, size, near_x - gw - 1.0, ground - 0.5, 0.8, 0.8,
         (ground - ridge_y) * (0.4 if collapsed else 0.9), BEAM)
    if collapsed:
        _billet(px, size, near_x + gw - 2, near_x + gw + 5, ground - 1.5, 1.0,
                BEAM, cap=False)
    else:
        _box(px, size, near_x + gw + 1.0, ground - 0.5, 0.8, 0.8,
             (ground - ridge_y) * 0.8, BEAM)

    # Guy lines pegged out to the sides — the detail that says "pitched", and
    # the only thing in the frame that is one pixel wide on purpose.
    for side in (-1, 1):
        rope_x = near_x + side * (gw + 1.0)
        for step in range(int(width * 0.13)):
            ix, iy = int(rope_x + side * step), int(ridge_y + 4 + step * 1.7)
            if 0 <= ix < width and 0 <= iy < height and px[ix, iy][3] == 0:
                px[ix, iy] = objects.tone(ROPE, 3, ix, iy)

    _shadow(img, near_x + depth * 0.4, ground - 0.5, gw * 1.3, 2.2)
    outline(img, OUTLINE_WOOD)
    return img


def make_firepit(width: int, height: int, variant: int, rng: random.Random) -> Image.Image:
    """A cold fire. The stone ring is intact; what burned in it is not.

    Same shape as the camp fire in make_textures.py with the light taken out —
    a player who has stood at the live one recognises it and knows what is
    missing. What is new is that the stones are STONES: a lit cap over a flank
    over the contact band it sits in (`_stone`), set on a RHOMBUS rather than a
    circle so the ring lies on the ground plane instead of standing up like a
    dial. Back stones are drawn first and front stones last, so the ring
    overlaps itself and the pit reads as something you look INTO.

    FIVE STONES, NOT SIX, and that is a legibility decision rather than a
    design one. Six around a 20px frame leaves each one four pixels across,
    and four pixels cannot hold three value bands — S16 caps a 16px mass at
    two or three sub-masses for exactly this reason. Five stones are six
    pixels each, they overlap their neighbours, and a ring of overlapping
    solids is worth more than a ring of separate dots.

    The ash bed is the one flat thing here and it should be: it is a decal
    lying inside a bowl, and giving it a plane would fight the stones for the
    silhouette. It is also kept DARK — the whole read of this prop is a pale
    ring around a black middle, and ash bright enough to have texture of its
    own closes the ring up into a disc.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)

    cx = (width - 1) / 2.0
    ring_y = height - 1.0 - height * 0.18
    ring_rx = width * 0.34
    ring_ry = max(1.8, ring_rx * SLOPE)

    for y in range(int(ring_y - ring_ry), int(ring_y + ring_ry) + 1):
        for x in range(int(cx - ring_rx), int(cx + ring_rx) + 1):
            if not (0 <= x < width and 0 <= y < height):
                continue
            dx, dy = (x - cx) / ring_rx, (y - ring_y) / ring_ry
            if dx * dx + dy * dy > 0.95:
                continue
            px[x, y] = pick(CHAR, 0.10 + hash01(x, y, 67) * 0.34, x, y)

    # Two burnt billets across the bed, crossed. Charcoal keeps the cylinder —
    # a spent log is still a log — and it is the one place `grain` is wanted,
    # because char genuinely breaks up where clean wood does not.
    for ox, oy, ln in ((-0.20, -0.06, 0.34), (0.00, 0.10, 0.30)):
        x0 = cx + ox * width
        _billet(px, size, x0, x0 + ln * width, ring_y + oy * height,
                1.4, CHAR, grain=0.30, salt=71 + variant, cap=False)

    # Stones, BACK OF THE RING FIRST so the front row overlaps it.
    count = 5
    order = sorted(range(count),
                   key=lambda i: math.sin(math.tau * i / count + 0.5 + variant * 0.4))
    for index in order:
        if variant == 2 and index == 2:
            continue  # one kicked out of the ring
        angle = math.tau * index / count + 0.5 + variant * 0.4
        sx = cx + math.cos(angle) * ring_rx
        sy = ring_y + math.sin(angle) * ring_ry
        # Sized on a 1 : 0.7 : 0.5 rhythm (S17) rather than five of one stone.
        scale = (1.0, 0.74, 0.88, 0.66, 0.94)[index % 5]
        _stone(px, size, sx, sy, 3.0 * scale, 2.3 * scale, ROCK, 83 + index * 7)

    _shadow(img, cx, ring_y + ring_ry * 0.7, ring_rx * 1.15, ring_ry * 0.9)
    outline(img, OUTLINE_COLD)
    return img


# --- standing: boundaries and markers ---------------------------------------


def make_fence(width: int, height: int, state: int, rng: random.Random) -> Image.Image:
    """One post-and-rail segment. `state` 0..5, whole through to nothing.

    Segments are drawn as a POST with rails running off both edges of the
    frame, so a run of them laid side by side joins up with no corner pieces
    and no orientation logic. The break in a fence is the story — the server
    picks which segments are ruined and where the gap someone came through is.

    THE POST IS A BOX AND THE RAILS ARE ROUND, and drawing that difference is
    most of what this prop is. A sawn post has a TOP FACE — the one surface on
    a fence the camera looks straight down at — and the old flat version had
    none, so a run of fence read as a row of pencil strokes. Split rails are
    cylinders and get `_billet`'s crest and underside.

    RAILS ARE DRAWN FIRST AND THE POST LAST, so the post overlaps them. That
    order is the only thing here that says the rails pass BEHIND rather than
    being glued to the front, and it costs nothing.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)

    cx = (width - 1) / 2.0
    ground = height - 1
    tall = height * (0.74 if state < 3 else 0.40)
    lean = 0.0 if state < 2 else rng.uniform(-0.16, 0.16)

    rails = {0: (0.40, 0.72), 1: (0.72,), 2: (0.40, 0.72), 3: (0.74,), 4: (), 5: ()}[state]
    for ratio in rails:
        axis = ground - tall * (1.0 - ratio) - 1.0
        drop = 0.0 if state < 2 else rng.uniform(0.0, 1.6)
        # Sagging rails are drawn as two short billets meeting at the post, so
        # the sag is a real break in the run rather than a bent line.
        for x0, x1, sag in ((0.0, cx + 1, drop), (cx - 1, width - 1.0, drop)):
            _billet(px, size, x0, x1, axis + sag, 1.3, BEAM, cap=False)

    if state != 5:
        base = ground - 1.0
        fx = cx + lean * tall
        _box(px, size, fx, base, 2.2, 2.2, tall, BEAM)
        if state >= 3:
            # A SNAPPED post has no lid. Everything the box drew above the
            # break comes off, and what is left is splinters standing out of
            # the shaft — one column of wood each, at the shaded step, because
            # a torn end catches nothing. Leaving the box's clean top face on
            # and roughing its edge is what made this read as a mushroom.
            top_y = int(round(base - tall - 2.2 * SLOPE))
            for x in range(max(0, int(fx - 4)), min(width, int(fx + 5))):
                for y in range(max(0, top_y - 1), min(height, top_y + 3)):
                    if px[x, y][3]:
                        px[x, y] = TRANSPARENT
            for x in range(max(0, int(fx - 2)), min(width, int(fx + 3))):
                spike = int(hash01(x, 0, 101) * 3.0)
                for y in range(top_y + 2 - spike, top_y + 3):
                    if 0 <= y < height:
                        px[x, y] = objects.tone(BEAM, SIDE, x, y)

    if state >= 4:
        # Collapsed: what is left is lying down, so it is billets on the floor
        # rather than a standing thing at all.
        for index in range(2 if state == 4 else 1):
            y = ground - 1.5 - index * 2.2
            _billet(px, size, 0.0, width - 1.0 - index * 3, y, 1.2, BEAM, cap=False)

    if state != 5:
        _shadow(img, cx, ground - 0.5, 4.0, 1.8)
    outline(img, OUTLINE_WOOD)
    return img


def make_sign(width: int, height: int, variant: int, rng: random.Random) -> Image.Image:
    """A board on a post. It SWAYS, which is why it is worth having at all.

    Three readings, none of them text: an ARROW (someone was routing people),
    TALLY marks (someone was counting something), and a board hanging off one
    nail (whatever it said stopped mattering). Lettering at 16px is a smudge —
    a shape the player can name from across the clearing is not.

    THE BOARD HAS A THICKNESS AND THAT IS THE WHOLE UPGRADE. A sign is two
    boxes: a square post with a top face, and a plank nailed across it that is
    wide, shallow and THIN — so the camera sees its face, the sliver of its
    top edge, and the shadow it throws down the post behind it. The old one
    was two rectangles of flat colour and read as a lollipop. The mark carved
    into it is cut with the VOID-dark `CHAR` at the board's own face step, so
    it reads as gouged rather than as painted on.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)

    cx = (width - 1) / 2.0
    ground = height - 1
    board_h = max(5, int(height * 0.26))
    board_top = int(height * 0.12)
    half = width * 0.42

    # The post, full height. Drawn first: the board hangs in front of it.
    _box(px, size, cx, ground - 1.0, 1.6, 1.6, height * 0.80, BEAM)

    # The board. `tilt` hangs it off one nail on variant 2.
    tilt = 0.0 if variant != 2 else 0.42
    base = board_top + board_h
    # A RIGID SLAB. The tilt slides the whole plank down at a constant slope
    # and its height never changes, so a hanging board is a parallelogram —
    # the shape a real board off one nail makes. Dropping each column by its
    # own curve, which is what this did first, wedges the plank thinner at one
    # end and reads as a torn flag.
    left = int(cx - half)
    for column in range(left, int(cx + half) + 1):
        if not (0 <= column < width):
            continue
        top = board_top + tilt * (column - left)
        top_y, base_y = int(round(top)), int(round(top)) + board_h
        for y in range(top_y, base_y + 1):
            if not (0 <= y < height):
                continue
            # Top edge is the plank's THICKNESS — the only surface the camera
            # looks down on, and the only thing separating a board from a
            # painted rectangle. The bottom row is its own contact shadow.
            plane = TOP if y == top_y else (SIDE if y == base_y else FRONT)
            px[column, y] = objects.tone(BEAM, plane, column, y)

    # Occlusion where the board crosses the post: the post is BEHIND it, so
    # the two rows directly under the plank take the contact step (S10).
    under = int(round(board_top + tilt * (cx - left))) + board_h
    for y in (under + 1, under + 2):
        for x in range(int(cx - 2), int(cx + 3)):
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = objects.tone(BEAM, 0, x, y)

    mid = int(round(board_top + tilt * (cx - int(cx - half)))) + board_h // 2
    if variant == 0:
        for step in range(int(half * 1.3)):
            x = int(cx - half * 0.65 + step)
            if 0 <= x < width and 0 <= mid < height and px[x, mid][3]:
                px[x, mid] = objects.tone(CHAR, 2, x, mid)
        for step in range(3):
            for side in (-1, 1):
                x, y = int(cx + half * 0.6 - step), mid + side * step
                if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                    px[x, y] = objects.tone(CHAR, 2, x, y)
    elif variant == 1:
        # Tally marks. Four upright and one struck through — a count somebody
        # kept, which is a smaller and worse thought than any word would be.
        for index in range(4):
            x = int(cx - half * 0.6 + index * 2.4)
            for y in range(mid - 2, mid + 2):
                if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                    px[x, y] = objects.tone(CHAR, 2, x, y)
        for step in range(9):
            x, y = int(cx - half * 0.75 + step), mid + 1 - step // 3
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = objects.tone(CHAR, 2, x, y)
    else:
        nail = (int(cx - half * 0.55), board_top)
        if 0 <= nail[0] < width:
            px[nail] = objects.tone(METAL, 4, *nail)

    _shadow(img, cx, ground - 0.5, 3.4, 1.6)
    outline(img, OUTLINE_WOOD)
    return img


def make_logs(width: int, height: int, variant: int, rng: random.Random) -> Image.Image:
    """A felled trunk lying across the ground. Cover you can see over.

    A log is the simplest volume in the folder and the old one got no benefit
    from it: a horizontal bar with a value ramp across its diameter and a
    three-pixel smear of rings at one end. What makes a trunk read is that it
    is a CYLINDER WITH A SAWN FACE — the crown catches the sky, the flank
    turns away, the underside is in its own shadow, and the cut end is a disc
    standing at an angle to all three. `_billet` draws those four things and
    nothing else.

    The bark is a value break along the GRAIN AXIS (S14: bark is long banded
    strips), so it runs the length of the trunk and never across it. One band
    per trunk, because two is a texture and this is a 14px tall sprite.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)

    ground = height - 1
    r = height * 0.30
    axis = ground - r - 1.0
    # Where the trunk stops. A broken one leaves the stub and the ground.
    end = width - 1 if variant < 2 else int(width * (0.58 + (variant - 2) * 0.10))

    _billet(px, size, 1, end, axis, r, BEAM)

    # Bark, as ONE clustered band along the grain axis (S14: bark is long
    # banded strips) rather than as speckle. It sits on the flank, two rows
    # deep, in runs of three columns — S5 puts the minimum meaningful cluster
    # at 2x2, and a one-pixel scatter reads as dirt rather than as bark.
    strip = int(round(axis - r * 0.06))
    for x in range(2, min(width, int(end))):
        if hash01(x // 3, 0, 127) <= 0.70:
            continue
        for dy in (0, 1):
            y = strip + dy
            if 0 <= y < height and px[x, y][3]:
                px[x, y] = objects.tone(BEAM, SIDE, x, y)

    if variant >= 2:
        # Broken rather than sawn: the far end splinters instead of capping.
        for x in range(max(0, end - 3), min(width, end + 2)):
            for y in range(height):
                if px[x, y][3] and hash01(x, y, 131) > 0.45:
                    px[x, y] = TRANSPARENT
    if variant == 3:
        # A branch stub, drawn as its own small billet standing off the trunk
        # so the silhouette is not a perfect bar (S15: bite the outline).
        _billet(px, size, width * 0.34, width * 0.34 + 4, axis - r - 1.5,
                max(1.2, r * 0.42), BEAM, grain=0.08, salt=137, cap=False)

    _shadow(img, width * 0.5, ground - 0.5, (end - 1) * 0.5, r * 0.9)
    outline(img, OUTLINE_WOOD)
    return img


# --- decals: what happened here ---------------------------------------------


def make_blood(size: int, kind: int, rng: random.Random) -> Image.Image:
    """Blood on the ground. `kind` 0 spray, 1 pool, 2 drag, 3 spatter,
    4 arc, 5 handprint.

    Six kinds and not one, because the SHAPE is the sentence. A pool means
    somebody stopped here. A drag means they did not stop here. A spray means
    it was fast. Six copies of one round stain would only mean "red".
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
                # Darker at the rim: blood dries from the edge inward, and the
                # rim is what keeps a stain from reading as a flat sticker.
                px[ix, iy] = pick(BLOOD, shade * (1.0 - dist / max(radius, 0.6) * 0.55), ix, iy)

    if kind == 0:  # spray — a cone of droplets away from a point
        angle = rng.uniform(0, math.tau)
        for _ in range(rng.randint(26, 38)):
            t = rng.random() ** 0.6
            spread = rng.uniform(-0.5, 0.5) * t
            dist = t * centre * 1.05
            drop(centre + math.cos(angle + spread) * dist,
                 centre + math.sin(angle + spread) * dist,
                 max(0.6, 2.2 * (1.0 - t)), 0.55 + (1 - t) * 0.4)
    elif kind == 1:  # pool — one mass with a ragged edge
        for _ in range(rng.randint(9, 13)):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(0, centre * 0.42)
            drop(centre + math.cos(a) * r, centre + math.sin(a) * r,
                 rng.uniform(centre * 0.24, centre * 0.42), rng.uniform(0.5, 0.85))
        for _ in range(rng.randint(5, 9)):  # flecks thrown clear of it
            a = rng.uniform(0, math.tau)
            r = rng.uniform(centre * 0.55, centre * 0.95)
            drop(centre + math.cos(a) * r, centre + math.sin(a) * r, rng.uniform(0.6, 1.4), 0.7)
    elif kind == 2:  # drag — a smear that thins as it goes
        angle = rng.uniform(0, math.tau)
        for step in range(int(size * 0.9)):
            t = step / (size * 0.9)
            x = centre - math.cos(angle) * centre * 0.9 + math.cos(angle) * step
            y = centre - math.sin(angle) * centre * 0.9 + math.sin(angle) * step
            drop(x + math.sin(t * 5) * 0.8, y, max(0.6, 3.0 * (1.0 - t)), 0.85 - t * 0.45)
    elif kind == 3:  # spatter — scattered, no direction
        for _ in range(rng.randint(18, 26)):
            drop(rng.uniform(2, size - 3), rng.uniform(2, size - 3),
                 rng.uniform(0.6, 2.0), rng.uniform(0.45, 0.9))
    elif kind == 4:  # arc — one swung line of droplets
        angle = rng.uniform(0, math.tau)
        curve = rng.choice((-1, 1)) * rng.uniform(0.9, 1.6)
        for step in range(24):
            t = step / 23
            a = angle + curve * t
            r = centre * 0.9
            drop(centre + math.cos(a) * r, centre + math.sin(a) * r,
                 rng.uniform(0.6, 1.8), 0.6 + rng.random() * 0.35)
    else:  # handprint — four fingers and a palm, pressed and dragged
        angle = rng.uniform(0, math.tau)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        def place(u: float, v: float, radius: float, shade: float) -> None:
            drop(centre + u * cos_a - v * sin_a, centre + u * sin_a + v * cos_a, radius, shade)

        place(0.0, 2.0, 3.4, 0.9)
        for index in range(4):
            place(-4.5 + index * 3.0, -3.0 - abs(index - 1.5) * 0.8, 1.5, 0.8)
        for step in range(6):  # it slid
            place(0.0, 4.0 + step, 3.0 - step * 0.4, 0.7 - step * 0.08)

    return img


def make_tracks(size: int, direction: int, directions: int, rng: random.Random) -> Image.Image:
    """One pair of boot prints, pointing along `direction` of `directions`.

    Rotations are baked as separate frames rather than rotated at draw time:
    a 16px print run through a canvas rotate comes out as grey mush, and the
    whole value of a footprint is that its heel and toe are distinguishable.
    A trail is these frames laid end to end by the server, all on the same
    heading, which is what turns "a footprint" into "somebody went that way".
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()

    angle = math.tau * direction / directions
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    centre = (size - 1) / 2.0

    def place(u: float, v: float, colour: RGBA) -> None:
        x = centre + u * cos_a - v * sin_a
        y = centre + u * sin_a + v * cos_a
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < size and 0 <= iy < size:
            px[ix, iy] = colour

    def sole(u: float, v: float, shade: float) -> None:
        """One print in the print's own frame: +v is the way it is walking.

        A footprint is a HOLE with a lip. Drawn as a dark shape alone it is
        invisible on a dark forest floor — near-black on near-black — so the
        soil pushed out of it gets drawn too, one pale pixel around the rim.
        That lip is the only reason a trail is legible at night, and it is the
        same trick the game's own tile art uses on rocks.
        """
        cells = [
            # (across, along) in the print's frame: a squared-off ball of the
            # foot, an arch two pixels narrower, and a separate heel.
            (-1, -2), (0, -2), (1, -2),
            (-1, -1), (0, -1), (1, -1),
            (0, 0),
            (-1, 1), (0, 1), (1, 1),
            (0, 2),
        ]
        filled = {(du, dv) for du, dv in cells}
        for du, dv in cells:
            # Toe end darker: the weight goes there as you push off.
            lean = 0.55 + (dv + 2) / 4.0 * 0.45
            place(u + du, v + dv, pick(CHAR, clamp01(shade * lean), int(u + du), int(v + dv)))
        for du, dv in cells:
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (du + ox, dv + oy) in filled:
                    continue
                place(u + du + ox, v + dv + oy, DISPLACED[(du + dv) % len(DISPLACED)])

    sole(-2.0, -2.5, 0.95)
    sole(2.0, 2.5, 0.8)
    return img


def make_clothes(width: int, height: int, kind: int, rng: random.Random) -> Image.Image:
    """Something a person was wearing, dropped. `kind` 0..4.

    Flat on the ground, so these are read entirely by outline: a shirt is a
    cross, a coat is a longer cross with a fold, a pack is a rounded block with
    two straps, a boot is an L, a hat is a disc with a crown. Nothing here has
    volume, and adding any would make it look like it was standing up.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    ramp = CLOTHS[kind % len(CLOTHS)] if kind != 3 else LEATHER
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0

    def blot(x0: float, y0: float, w: float, h: float, shade: float, salt: int) -> None:
        for y in range(int(y0), int(y0 + h)):
            for x in range(int(x0), int(x0 + w)):
                if not (0 <= x < width and 0 <= y < height):
                    continue
                # Fray the edge: cloth crumpled on soil has no straight sides.
                edge = min(x - x0, x0 + w - 1 - x, y - y0, y0 + h - 1 - y)
                if edge < 1 and hash01(x, y, salt) > 0.55:
                    continue
                px[x, y] = pick(ramp, shade + (hash01(x, y, salt) - 0.5) * 0.4, x, y)

    if kind == 0:  # shirt
        blot(cx - 3, cy - 4, 7, 9, 0.6, 149)
        blot(cx - 8, cy - 3, 6, 4, 0.45, 151)
        blot(cx + 2, cy - 2, 6, 4, 0.45, 157)
    elif kind == 1:  # coat, one side folded under
        blot(cx - 4, cy - 6, 9, 12, 0.55, 163)
        blot(cx - 9, cy - 4, 6, 5, 0.4, 167)
        blot(cx + 4, cy - 1, 5, 6, 0.75, 173)
    elif kind == 2:  # pack
        blot(cx - 4, cy - 4, 9, 9, 0.6, 179)
        for offset in (-2, 2):  # straps
            for y in range(int(cy - 5), int(cy + 5)):
                x = int(cx + offset)
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(LEATHER, 0.75, x, y)
    elif kind == 3:  # boot
        blot(cx - 2, cy - 5, 5, 7, 0.6, 181)
        blot(cx - 2, cy + 1, 9, 4, 0.75, 191)
    else:  # hat
        blot(cx - 5, cy - 3, 11, 7, 0.45, 193)
        blot(cx - 2, cy - 2, 5, 5, 0.8, 197)
    return img


def make_debris(size: int, kind: int, rng: random.Random) -> Image.Image:
    """Broken things. `kind` 0 bottle, 1 planks, 2 bones, 3 lantern,
    4 crockery, 5 wheel."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    centre = (size - 1) / 2.0

    def shard(x: float, y: float, angle: float, length: float, ramp: Ramp, shade: float) -> None:
        _stroke(px, x, y, angle, length, 0.5, ramp, shade, 199, size, size)

    if kind == 0:  # a bottle, neck intact, body burst
        shard(centre - 4, centre + 1, 0.1, 6, GLASS, 0.55)
        for _ in range(rng.randint(8, 12)):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(1.5, centre * 0.9)
            shard(centre + math.cos(a) * r, centre + math.sin(a) * r,
                  rng.uniform(0, math.tau), rng.uniform(1.5, 3.0), GLASS,
                  rng.uniform(0.5, 1.0))
    elif kind == 1:  # a pile of snapped planks
        for _ in range(rng.randint(4, 6)):
            shard(rng.uniform(1, size - 4), rng.uniform(2, size - 3),
                  rng.uniform(-0.5, 0.5) + rng.choice((0.0, math.pi / 2)),
                  rng.uniform(size * 0.4, size * 0.8), PLANK, rng.uniform(0.4, 0.8))
    elif kind == 2:  # bones — a ribcage read, not an anatomy lesson
        for index in range(5):
            y = centre - 4 + index * 2
            shard(centre - 4, y, 0.12, 8, BONE, 0.6 + index * 0.05)
        shard(centre - 5, centre - 5, math.pi / 2 + 0.1, 11, BONE, 0.85)
    elif kind == 3:  # a lantern, glass out, frame bent
        for y in range(int(centre - 3), int(centre + 4)):
            for x in range(int(centre - 3), int(centre + 4)):
                edge = max(abs(x - centre), abs(y - centre))
                if edge < 2:
                    continue
                px[x, y] = pick(METAL, 0.5 + (hash01(x, y, 211) - 0.5) * 0.5, x, y)
        shard(centre + 2, centre - 4, -0.6, 5, METAL, 0.8)
        for _ in range(4):
            a = rng.uniform(0, math.tau)
            shard(centre + math.cos(a) * 5, centre + math.sin(a) * 5,
                  rng.uniform(0, math.tau), 2.0, GLASS, 0.9)
    elif kind == 4:  # crockery, radiating from where it landed
        for _ in range(rng.randint(6, 9)):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(0.5, centre * 0.8)
            shard(centre + math.cos(a) * r, centre + math.sin(a) * r, a,
                  rng.uniform(2.0, 4.0), BONE, rng.uniform(0.4, 0.9))
    else:  # a cart wheel, off its axle
        radius = centre * 0.75
        for step in range(40):
            a = math.tau * step / 40
            ix = int(round(centre + math.cos(a) * radius))
            iy = int(round(centre + math.sin(a) * radius * 0.55))
            if 0 <= ix < size and 0 <= iy < size:
                px[ix, iy] = pick(PLANK, 0.65, ix, iy)
        for index in range(4):  # spokes, one of them snapped short
            a = math.tau * index / 4 + 0.3
            length = radius * (0.4 if index == 2 else 0.95)
            shard(centre, centre, a, length, PLANK, 0.5)
    return img


# --- build ------------------------------------------------------------------

TRACK_DIRECTIONS = 8


def build(args) -> Path:
    """Pack every scenery sheet and write the one manifest the client reads.

    Two drawing modules feed this: the functions above (what the forest LOOKS
    like after people left) and `make_objects.py` (what they left that you can
    open). They land in the same folder and the same manifest on purpose —
    the client keys its atlas off the manifest, so a new sheet here plus a
    scene in `server/app/scenery.py` is the whole of adding an object.

    ANIMATED SHEETS carry three extra fields and nothing else needs to change:
    `kinds` (how many objects are packed in the strip, kind-major),
    `animFrames` (frames per kind — frame 0 is always the idle pose) and
    `fps`. Whether that animation is a smash or a lid coming up is the
    SERVER's business (`server/app/crates.py`), not the sheet's: the art is
    the same contract either way.
    """
    tile = args.tile
    out_dir = PROCESSED_DIR / "scenery"
    out_dir.mkdir(parents=True, exist_ok=True)

    tent_w, tent_h = tile * 2, round(tile * 1.75)
    rng = random.Random(args.seed + 22)
    tents = [make_tent(tent_w, tent_h, state, rng) for state in range(3)]
    pack(tents, tent_w, tent_h).save(out_dir / "tent.png")

    fence_w, fence_h = tile, round(tile * 1.375)
    rng = random.Random(args.seed + 33)
    fences = [make_fence(fence_w, fence_h, state, rng) for state in range(6)]
    pack(fences, fence_w, fence_h).save(out_dir / "fence.png")

    sign_w, sign_h = tile, round(tile * 1.75)
    rng = random.Random(args.seed + 44)
    signs = [make_sign(sign_w, sign_h, variant, rng) for variant in range(3)]
    pack(signs, sign_w, sign_h).save(out_dir / "sign.png")

    log_w, log_h = tile * 2, round(tile * 0.875)
    rng = random.Random(args.seed + 55)
    logs = [make_logs(log_w, log_h, variant, rng) for variant in range(4)]
    pack(logs, log_w, log_h).save(out_dir / "logs.png")

    pit_w, pit_h = round(tile * 1.25), round(tile * 0.75)
    rng = random.Random(args.seed + 77)
    pits = [make_firepit(pit_w, pit_h, variant, rng) for variant in range(3)]
    pack(pits, pit_w, pit_h).save(out_dir / "firepit.png")

    # --- the objects, from make_objects.py ---------------------------------
    barrels, barrel_w, barrel_h = objects.barrel_strip(tile, args.seed + 201)
    pack(barrels, barrel_w, barrel_h).save(out_dir / "barrel.png")

    crates, crate_w, crate_h = objects.crate_strip(tile, args.seed + 210)
    pack(crates, crate_w, crate_h).save(out_dir / "crate.png")

    boxes, box_w, box_h = objects.box_strip(tile, args.seed + 202)
    pack(boxes, box_w, box_h).save(out_dir / "box.png")

    chests, chest_w, chest_h = objects.chest_strip(tile, args.seed + 203)
    pack(chests, chest_w, chest_h).save(out_dir / "chest.png")

    stashes, stash_w, stash_h = objects.stash_strip(tile, args.seed + 204)
    pack(stashes, stash_w, stash_h).save(out_dir / "stash.png")

    vehicles, veh_w, veh_h = objects.vehicle_strip(tile, args.seed + 205)
    pack(vehicles, veh_w, veh_h).save(out_dir / "vehicle.png")

    altars, altar_w, altar_h = objects.altar_strip(tile, args.seed + 206)
    pack(altars, altar_w, altar_h).save(out_dir / "altar.png")

    statues, statue_w, statue_h = objects.statue_strip(tile, args.seed + 207)
    pack(statues, statue_w, statue_h).save(out_dir / "statue.png")

    # --- decals ------------------------------------------------------------
    blood_size = tile * 2
    rng = random.Random(args.seed + 88)
    bloods = [make_blood(blood_size, kind, rng) for kind in range(6)]
    pack(bloods, blood_size, blood_size).save(out_dir / "blood.png")

    rng = random.Random(args.seed + 99)
    tracks = [make_tracks(tile, d, TRACK_DIRECTIONS, rng) for d in range(TRACK_DIRECTIONS)]
    pack(tracks, tile, tile).save(out_dir / "tracks.png")

    cloth_w, cloth_h = round(tile * 1.25), tile
    rng = random.Random(args.seed + 110)
    clothes = [make_clothes(cloth_w, cloth_h, kind, rng) for kind in range(5)]
    pack(clothes, cloth_w, cloth_h).save(out_dir / "clothes.png")

    rng = random.Random(args.seed + 121)
    debris = [make_debris(tile, kind, rng) for kind in range(6)]
    pack(debris, tile, tile).save(out_dir / "debris.png")

    bones, bones_w, bones_h = objects.bones_strip(tile, args.seed + 208)
    pack(bones, bones_w, bones_h).save(out_dir / "bones.png")

    oils, oil_w, oil_h = objects.oil_strip(tile, args.seed + 209)
    pack(oils, oil_w, oil_h).save(out_dir / "oil.png")

    def sheet(file: str, w: int, h: int, frames: list, **extra) -> dict:
        return {"file": file, "frameWidth": w, "frameHeight": h, "frames": len(frames), **extra}

    manifest = {
        "tile": tile,
        "seed": args.seed,
        # STANDING: bottom-anchored, depth-sorted with the party. `sway` is the
        # peak lean in world px the client animates; 0 means it does not move.
        # `smokes` asks the client for a wisp rising off the anchor point.
        "props": {
            "tent": sheet("tent.png", tent_w, tent_h, tents, sway=SWAY_TENT),
            "fence": sheet("fence.png", fence_w, fence_h, fences, sway=0),
            "sign": sheet("sign.png", sign_w, sign_h, signs, sway=SWAY_SIGN),
            "logs": sheet("logs.png", log_w, log_h, logs, sway=0),
            "firepit": sheet("firepit.png", pit_w, pit_h, pits, sway=0, smokes=True),
            "statue": sheet("statue.png", statue_w, statue_h, statues, sway=0),
            # Animated. Kind-major strips; frame 0 of each kind is the idle.
            "barrel": sheet(
                "barrel.png", barrel_w, barrel_h, barrels, sway=0,
                kinds=objects.BARREL_KINDS,
                animFrames=objects.BARREL_FRAMES,
                fps=objects.BARREL_FPS,
            ),
            "crate": sheet(
                "crate.png", crate_w, crate_h, crates, sway=0,
                kinds=objects.CRATE_KINDS,
                animFrames=objects.CRATE_FRAMES,
                fps=objects.CRATE_FPS,
            ),
            "box": sheet(
                "box.png", box_w, box_h, boxes, sway=0,
                kinds=objects.BOX_KINDS,
                animFrames=objects.BOX_FRAMES,
                fps=objects.BOX_FPS,
            ),
            "chest": sheet(
                "chest.png", chest_w, chest_h, chests, sway=0,
                kinds=objects.CHEST_KINDS,
                animFrames=objects.CHEST_FRAMES,
                fps=objects.CHEST_FPS,
            ),
            "stash": sheet(
                "stash.png", stash_w, stash_h, stashes, sway=0,
                kinds=objects.STASH_KINDS,
                animFrames=objects.STASH_FRAMES,
                fps=objects.STASH_FPS,
            ),
            "vehicle": sheet(
                "vehicle.png", veh_w, veh_h, vehicles, sway=0,
                kinds=objects.VEHICLE_KINDS,
                animFrames=objects.VEHICLE_FRAMES,
                fps=objects.VEHICLE_FPS,
            ),
            "altar": sheet(
                "altar.png", altar_w, altar_h, altars, sway=0,
                kinds=objects.ALTAR_KINDS,
                animFrames=objects.ALTAR_FRAMES,
                fps=objects.ALTAR_FPS,
            ),
        },
        # DECALS: flat, centred on their point, baked into the ground canvas.
        "decals": {
            "blood": sheet("blood.png", blood_size, blood_size, bloods),
            "tracks": sheet("tracks.png", tile, tile, tracks, directions=TRACK_DIRECTIONS),
            "clothes": sheet("clothes.png", cloth_w, cloth_h, clothes),
            "debris": sheet("debris.png", tile, tile, debris),
            "bones": sheet("bones.png", bones_w, bones_h, bones),
            "oil": sheet("oil.png", oil_w, oil_h, oils),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: "
        f"tent {len(tents)}, fence {len(fences)}, sign {len(signs)}, "
        f"logs {len(logs)}, firepit {len(pits)}, statue {len(statues)}, "
        f"barrel {objects.BARREL_KINDS}x{objects.BARREL_FRAMES}, "
        f"crate {objects.CRATE_KINDS}x{objects.CRATE_FRAMES}, "
        f"box {objects.BOX_KINDS}x{objects.BOX_FRAMES}, "
        f"chest {objects.CHEST_KINDS}x{objects.CHEST_FRAMES}, "
        f"stash {objects.STASH_KINDS}x{objects.STASH_FRAMES}, "
        f"vehicle {objects.VEHICLE_KINDS}x{objects.VEHICLE_FRAMES}@{veh_w}x{veh_h}, "
        f"altar {objects.ALTAR_KINDS}x{objects.ALTAR_FRAMES}, "
        f"blood {len(bloods)}, tracks {len(tracks)}, clothes {len(clothes)}, "
        f"debris {len(debris)}, bones {len(bones)}, oil {len(oils)}"
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
