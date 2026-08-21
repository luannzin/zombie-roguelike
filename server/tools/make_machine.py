#!/usr/bin/env python3
"""Asset pipeline: THE UPGRADE MACHINE — the slot cabinet in the merchant's shop.

Output (assets/processed/machine/):
    cabinet.png    2 frames, 32x46   PROP   — idle, and settled after a pull
    strip.png      1 frame,  6x100   PART   — the REEL BAND: ten cells, looped
    lever.png      6 frames, 11x24   PART   — the arm, up to fully pulled
    marquee.png   10 frames, 38x18   VFX    — loop, the hood lights chasing
    window.png     6 frames, 30x16   VFX    — loop, the backlight behind the reels
    burst.png     12 frames, 48x48   VFX    — one-shot, the payout flash
    manifest.json

IT IS A TOY, AND IT USED TO BE A WRECK.
The first cabinet was three tiles wide, grey, dented, missing a corner of its
hood, with a car battery cabled to its base — the argument being that a clean
machine would be the one object in the game that came from a different one. Two
things were wrong with it. It was drawn for a clearing twice this size, so in
the shop as it now stands it read as a wall rather than as something to walk up
to; and a dark dented box is indistinguishable, at a glance and at night, from
the market stalls beside it. So it is SMALL, RED and FLAT-SHADED now: a gold
hood with bulbs in it, a cream fascia with three windows, a lever and a tray.
Nothing is grimy, because grime at this size is noise, and the shop is the one
beat of the loop that is supposed to feel safe.

WHY IT IS STILL UNMISTAKABLY A SLOT MACHINE.
Three lit windows in a row, a hood of bulbs, a lever on the right and a tray at
the bottom. Those four are the whole vocabulary and none of them may be subtle
— a player has to read it from the door, before the prompt, before the tooltip,
and think *that thing is for me*.

IT IS A BAND, NOT A FRAME NUMBER, AND THAT IS THE REWRITE.
The reels used to be nine sprites: four frames of horizontal blur cycled while
spinning, then a hard cut to one of five rarity faces. It read as a colour
appearing in a box. A real reel is a CONTINUOUS STRIP that goes past, slows,
and stops on a symbol — and the second and a half where it is crawling past
faces one at a time, with the answer already decided, is the entire reason
anybody has ever pulled a lever. So `strip.png` is one tall image of ten cells
and the client scrolls a window over it (`game/machine.ts` `reelScroll`), which
gets three things the old sheet could not:

    THE TEASE      the band decelerates through six or seven faces before it
                   lands, so a legendary is visibly ALMOST on the line for a
                   beat before it either arrives or goes past
    THE NEAR MISS  free, and never authored: the band's order puts a legendary
                   next to a common, so the reel that stopped one cell short
                   really did stop one cell short
    THE WEIGHT     motion blur is the strip drawn twice at an offset scaled by
                   its own speed, so slowing down is something you SEE rather
                   than a frame index changing

The band's order is fixed and deliberately not sorted. Ascending would teach
the player that blue means purple is next, which turns the last half second
into arithmetic; commons appear four times because they are the likeliest roll,
so the strip looks like the odds it is paying.

THE LIGHT IS THE POINT AND IT IS ADDITIVE.
The cabinet body takes the darkness multiply like every other prop. The
marquee, the window backlight and the payout burst are drawn AFTER that pass,
additively, because they are light sources and not things being lit. The
marquee and the burst are GREYSCALE so the client can tint them: the hood
burns `--scene-neon` while the machine is idle and the winning RARITY's colour
while a canister is coming out, and one multiply gets both out of one sheet.

Usage:
    python tools/make_machine.py
    python tools/make_machine.py --seed 5
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

from make_textures import (
    BEAM,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    add,
    ellipse,
    material_ramp,
    outline,
    pack,
    pick,
    resolve,
    rgb,
)

# --- palette ----------------------------------------------------------------
# Toned like scenery, because it stands in the same night the trees do. The
# only saturated things here are the reel faces and the lever ball, and both
# are small — the cabinet reads as a dark shape with light coming out of it,
# which is what a machine at night looks like.
#
# EXCEPT THAT IT IS THE ONE FRIENDLY OBJECT IN THE ZONE, so the body is not
# scenery-toned any more. It was a dented grey locker with a brass hood, which
# at two tiles across read as a market stall with the lights off; it is a RED
# cabinet with a cream fascia and a gold hood now. Three flat colours, one
# highlight each, no dents and no grime — the same read a toy has. The shop is
# the safe beat of the loop and the machine is the toy in it.

#: THE RAMPS ARE DERIVED NOW, AND THE CEILING CAME DOWN WITH THEM.
#:
#: Two changes, one cause. They were hand-typed hex, which means each one
#: hue-shifted however it felt like rather than the way S11 says every other
#: material in the game does — `material_ramp` is that law as four numbers.
#: And they were tuned for a cabinet standing in a DARK CLEARING, where "a
#: dark shape with light coming out of it" is exactly what a machine at night
#: should be. It stands against a brick wall in a LIT ROOM now. At the old
#: top step the cream fascia was #f6e6c8 — brighter than anything else in the
#: shop, including the counter, which is the one surface that is supposed to
#: win. The hierarchy is the counter, then the man, then this; so every ramp
#: here tops out under `make_store.WOOD` and the machine reads as the loudest
#: OBJECT rather than as the brightest surface.
#:
#: The cabinet is still cherry red with a cream fascia and a gold hood, and
#: that decision is unchanged and is the point of it: it was a dented grey
#: locker before, which at two tiles across read as a market stall with the
#: lights off. Three flat colours, one highlight each, no dents and no grime —
#: the same read a toy has. The shop is the safe beat of the loop and the
#: machine is the toy in it.

#: The shell. Cherry red, because nothing else in this game is, and the whole
#: job of this sprite is to be picked out from across the room.
SHELL: Ramp = material_ramp(352.0, 0.56, 0.13, 0.52, steps=5)
#: The fascia the windows are set into, and the plinth. Warm cream: it is the
#: contrast that makes the red read as paint rather than as rust.
PANEL: Ramp = material_ramp(34.0, 0.30, 0.19, 0.68, steps=5)
#: The hood, the bezel and the tray lip. Gold, flat, and the only metal left.
TRIM: Ramp = material_ramp(43.0, 0.54, 0.14, 0.60, steps=5)
CHROME: Ramp = material_ramp(220.0, 0.10, 0.11, 0.50, steps=5)
#: The dead glass behind the reels. Near-black on purpose: it is the hole the
#: lit faces are seen through, so it has to stay under everything.
GLASSDARK: Ramp = [rgb(c) for c in ("#080a0e", "#0e1218", "#151b23", "#1d242e")]
BULB: Ramp = material_ramp(45.0, 0.58, 0.16, 0.72, steps=5)
RED: Ramp = material_ramp(6.0, 0.60, 0.10, 0.44, steps=5)
OUTLINE: RGBA = rgb("#120a10")

#: The five rarity ramps, same five as `make_skills.py` and the same five the
#: HUD paints. A reel face that stopped on a colour the bag does not use would
#: be a sixth grade nobody could look up.
RARITY: dict[str, Ramp] = {
    "common": [rgb(c) for c in ("#3a3a42", "#565660", "#7c7c88", "#a8a8b4", "#e8e8f0")],
    "uncommon": [rgb(c) for c in ("#123020", "#1d4d32", "#2c7a4d", "#42a86a", "#5dce7a")],
    "rare": [rgb(c) for c in ("#131f3d", "#1d3160", "#2c4b96", "#3e6ac6", "#5b8def")],
    "epic": [rgb(c) for c in ("#2a1440", "#3f1d63", "#5f2d94", "#8a48c4", "#b46ee8")],
    "legendary": [rgb(c) for c in ("#3a2a0c", "#5e4413", "#96701f", "#c99a34", "#f2c14b")],
}

#: THE REEL BAND, top to bottom, and it wraps. See the module docstring: the
#: order is fixed, deliberately unsorted, and weighted toward common so the
#: strip looks like the odds it is paying. The two places a LEGENDARY sits are
#: both next to a COMMON, which is where every near miss in this machine comes
#: from — nothing about it is authored per pull.
BAND: tuple[str, ...] = (
    "common",
    "rare",
    "common",
    "legendary",
    "uncommon",
    "epic",
    "common",
    "uncommon",
    "rare",
    "common",
)

# --- geometry ---------------------------------------------------------------
# TWO TILES WIDE AND UNDER THREE TALL, and it used to be three by four and a
# half. The big one was authored for a cabinet standing alone on the arc of a
# wide clearing, and the clearing shrank: in a small shop a sprite that size is
# a wall the party walks around rather than an object in the room, and it made
# every table beside it look like furniture for somebody else. Small enough to
# stand next to and still read as a slot machine from the door is the brief,
# and the four things that carry that read — hood, three windows, lever, tray —
# are exactly what the pixels are spent on. Everything else went.
#
# IT IS A SOLID NOW, NOT A FRONT ELEVATION. What stood here was a flat red
# rectangle with lighter rows painted on top of each part: no top plane, no
# side, and the one object in the shop a player is supposed to walk up to had
# less volume than the crates in the forest. §2a says a face-on solid is FRONT
# + TOP + SHADE SIDE and that none of the three is optional, so the cabinet is
# built from that stack now — every part of it is a box run back along the
# depth axis (up and to the RIGHT at `SLOPE`), and the lever is bolted to the
# flank that run opens up, which is where an arcade cabinet keeps it.
#
# EVERYTHING BELOW IS AUTHORED IN THE FRONT'S OWN COORDINATES — the 32x46
# elevation this machine has always been measured in, bottom-anchored on the
# contact row. `_put` is the only thing that knows the frame is bigger than
# that, so a part moves by editing the number it was authored with and nothing
# else. The frame carries a margin on both sides because the client draws a
# prop CENTRED on its contact point: the front is the plane standing on that
# point, so the front is what has to be centred, and the run back spends the
# columns to its right.

FRONT_W, FRONT_H = 32, 46
#: The camera, as one number, and it is the same one every other solid in the
#: game is built on: 2 px back per 1 px up.
SLOPE = 0.5
#: How far the cabinet runs back from the camera. AUTHORED rather than derived
#: from its width (§3a's exception, and the same call the vehicles make): a
#: slot machine is deeper than it is wide, and a run back at the true ratio
#: puts more rise on the crown than the crown is tall.
#:
#: IT WAS TWELVE, AND TWELVE IS A THREE-QUARTER VIEW OF A CABINET RATHER THAN A
#: CABINET. Two things went wrong at that depth and they compound. The run back
#: is as wide as a third of the front, so the swept planes — deck top, hood top,
#: flank — carried more of the sprite than the fascia did: the biggest surface
#: on a slot machine became its control shelf seen from above, and the three
#: windows, the one thing that has to read from the shop door, sat on a face
#: the eye took second. And the run only ever spends columns to the RIGHT, so a
#: frame centred on the contact point put the machine visibly off its own tile,
#: leaning away from the player walking up to it.
#:
#: FIVE IS A FRONT VIEW OF A SOLID, which is what everything else in this room
#: is. §2a still holds — front, top and shade side, none of them optional — but
#: the top is now a two-pixel cap and the flank a sliver, the same proportions
#: the stalls and the counter are drawn at. The cabinet reads as a box standing
#: square to the screen with its face toward the door, the fascia is the biggest
#: plane on it again, and the art lands within a pixel or two of the centre of
#: its own frame. It is also still deep enough to hang the lever off, which was
#: the only thing the twelve was actually buying.
DEPTH = 5
CAB_W = FRONT_W + 2 * DEPTH
CAB_H = FRONT_H + int(DEPTH * SLOPE)
#: Where the front's own origin sits in the frame.
ORIGIN_X, ORIGIN_Y = DEPTH, CAB_H - FRONT_H

#: Plane -> ramp step on the five-step ramps above, and the gaps are the whole
#: read: TWO steps between planes, never one (§3). One step apart at this size
#: is a smudge and the cabinet goes back to being a rectangle with stripes.
PLANE_TOP, PLANE_FRONT, PLANE_SIDE = 4, 2, 0

BODY_L, BODY_R = 3, 28
CROWN_TOP, CROWN_BOTTOM = 1, 9
#: The three reel windows: left edge of the first, cell size, and the gap.
#: Centred in the body by hand — `BODY_L + (26 - (3 * REEL_W + 2 * REEL_GAP)) // 2`.
REEL_X, REEL_Y = 5, 14
REEL_W, REEL_H = 6, 10
REEL_GAP = 2
#: How many cells the band holds. The client scrolls a `REEL_H` window over
#: `CELLS * REEL_H` pixels and wraps, so the strip has no ends.
CELLS = len(BAND)
#: THE CONTROL DECK: the shelf under the glass, and the part that does most of
#: the work of saying this thing is three-dimensional. It overhangs the body on
#: both sides, so its top plane and its underside are the one horizontal break
#: in a tall vertical object — which is exactly what the references lean on.
DECK_TOP, DECK_BOTTOM = 26, 30
#: The tray the canister comes out of. `trayMouth` is the pixel the client
#: launches a can from, and it rides the manifest so the arc starts at the hole
#: rather than at a guess about where the hole is.
TRAY_L, TRAY_R = 9, 22
TRAY_TOP, TRAY_BOTTOM = 33, 38
#: Where the lever's pivot sits, and it is ON THE FLANK now: half the run back,
#: at the height of the deck. A lever on the front edge of a cabinet is a lever
#: seen edge-on, which is why every arcade machine ever built puts it on the
#: side — and there was no side to put it on until the cabinet became a solid.
#: The pivot is in the LEVER frame's own left margin, and `LEVER_ANCHOR` is
#: where that pivot lands in the cabinet frame — so the client blits the arm at
#: `anchor - pivot` and the two never have to agree about anything else.
LEVER_ANCHOR = (ORIGIN_X + BODY_R + int(DEPTH * 0.55),
                ORIGIN_Y + DECK_BOTTOM + 3 - int(DEPTH * 0.55 * SLOPE))
LEVER_PIVOT = (2, 12)
LEVER_W, LEVER_H = 11, 24

MARQUEE_W, MARQUEE_H = 38, 18
WINDOW_W, WINDOW_H = 30, 16
BURST = 48

#: How many bulbs ride the hood. Odd, so one of them is dead centre and the
#: chase reads as going round a sign rather than as two rows blinking. Seven
#: rather than eleven: at this width eleven bulbs are one lit bar.
BULBS = 7


def _reel_slot(index: int) -> tuple[int, int]:
    """Top-left of reel window `index`, in the FRAME."""
    return (ORIGIN_X + REEL_X + index * (REEL_W + REEL_GAP), ORIGIN_Y + REEL_Y)


# --- the cabinet ------------------------------------------------------------


def _step(ramp: Ramp, index: int) -> RGBA:
    """One exact ramp step, no dithering.

    `pick` dithers between the two nearest steps, which is right for soil and
    wrong for a painted machine: at this size a Bayer checker between two reds
    reads as rust. Flat fills are the whole cartoon style — every surface on
    this cabinet is ONE colour, and what separates two of them is a plane
    break, not a gradient (§5).
    """
    return ramp[max(0, min(len(ramp) - 1, index))]


def _put(px, x: int, y: int, colour: RGBA) -> None:
    """One pixel, in the FRONT's coordinates. The only place the margins live."""
    fx, fy = x + ORIGIN_X, y + ORIGIN_Y
    if 0 <= fx < CAB_W and 0 <= fy < CAB_H:
        px[fx, fy] = colour


def _flat(
    px,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    ramp: Ramp,
    step: int,
    radius: int = 2,
) -> None:
    """The FRONT plane of a part: one flat rectangle with its corners knocked off.

    Flat, and that is the change. It used to carry a lighter row along its top
    and a darker one down its right, which is a drawing of a light source on a
    surface that has no other surface to be lit against. A plane is one step
    (§7); what says which way it faces is the plane NEXT to it.
    """
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if radius > 0:
                dx = min(x - x0, x1 - x)
                dy = min(y - y0, y1 - y)
                if dx < radius and dy < radius and (dx + dy) < radius:
                    continue
            _put(px, x, y, _step(ramp, step))


def _solid(
    px,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    ramp: Ramp,
    step: int = PLANE_FRONT,
    radius: int = 2,
    depth: int = DEPTH,
    top: int | None = None,
) -> None:
    """A part of the cabinet as a box: top plane, front plane, shade side.

    THE ORDER IS BACK TO FRONT. The two swept planes are laid down first and
    the front is painted over whatever they left in its rectangle, so the
    silhouette is the front's — a swept plane can only ever add to it, never
    eat into it.

    The terminator (§2a) is the last row of the top plane rather than a line
    drawn afterwards: one step under the top, where the two planes fold. Same
    at the contact, where §10 asks for the ground to eat the bottom row.
    """
    # TOP, swept up and to the right off the front's top edge. `top` is worth
    # overriding on the GOLD parts and nowhere else: two steps over the front
    # is the right distance on red and on cream, and on trim it lands above
    # `make_store.WOOD` — which would make the crown of this cabinet the
    # brightest surface in a room whose counter is supposed to win.
    lit = step + 2 if top is None else top
    for index in range(int(depth * 2) + 1):
        back = index * 0.5
        row = int(round(y0 - back * SLOPE))
        far = back > depth - 1.01
        for x in range(int(round(x0 + back + radius)), int(round(x1 + back)) + 1):
            _put(px, x, row, _step(ramp, lit if not far else lit - 1))
    # SIDE, swept off the front's right edge. The plane the key does not reach
    # (§8: key at 135°), and the one the lever hangs on.
    for index in range(int(depth * 2) + 1):
        back = index * 0.5
        col = int(round(x1 + back))
        shift = back * SLOPE
        for y in range(int(round(y0 - shift + radius)), int(round(y1 - shift)) + 1):
            _put(px, col, y, _step(ramp, step - 2))
    # FRONT.
    _flat(px, x0, y0, x1, y1, ramp, step, radius=radius)
    # The fold where the top meets the front, and the contact under it.
    for x in range(x0 + radius, x1 + 1):
        _put(px, x, y0, _step(ramp, step - 1))
    for x in range(x0 + radius, x1 - radius + 1):
        _put(px, x, y1, _step(ramp, step - 2))


def _recess(
    px,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    lip: Ramp,
) -> None:
    """A hole cut into a plane: dark inside, lit on the lip under it (§2b).

    A hole is the strongest depth cue a sprite can carry because it is the one
    thing that cannot be read as paint. What makes it one is the pair of edges:
    the plane above it throws a shadow onto the inside of its own top row, and
    the lip along the bottom catches the key — which is the whole reason a
    tray reads as somewhere a canister comes OUT of.
    """
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            _put(px, x, y, _step(GLASSDARK, 1 if y > y0 else 0))
    for x in range(x0 - 1, x1 + 2):
        _put(px, x, y1 + 1, _step(lip, 4))
        _put(px, x, y0 - 1, _step(lip, 1))
    for y in range(y0, y1 + 1):
        _put(px, x0 - 1, y, _step(lip, 3))
        _put(px, x1 + 1, y, _step(lip, 1))


def make_cabinet(settled: bool) -> Image.Image:
    """The body. `settled` is the frame after a pull: the shell sits one pixel
    lower on its feet, which is the whole tell that the thing just took a hit
    from its own lever.

    FOUR THINGS AND NOTHING ELSE: a gold hood with bulbs in it, three windows in
    a cream fascia, a lever on the flank and a tray at the bottom. Every pixel
    that was spent on dents, worn stripes, maker's plates, dead buttons and a
    car battery is gone — at two tiles across those details were noise that made
    the silhouette harder to read, which is the opposite of what detail is for.
    The story ("somebody dragged this out here") is told by where it stands.

    WHAT THE VOLUME BOUGHT. Five boxes stacked instead of five rectangles: a
    plinth, the body, the hood, and the control deck that overhangs both sides
    between them. Each one is a `_solid`, so each one has a lit top the eye can
    stand on and a dark flank behind it, and the steps down that stack — hood
    top, deck top, plinth top — are what makes a tall object read as tall
    rather than as a poster of one.
    """
    img = Image.new("RGBA", (CAB_W, CAB_H), TRANSPARENT)
    px = img.load()
    drop = 1 if settled else 0
    floor = FRONT_H - 2

    # 1. THE PLINTH it stands on, wider than the body and in the shell's own
    #    red — the tray is cut into it, so it is the one part of the cabinet a
    #    player looks at twice, and cream down there put the brightest surface
    #    on the sprite at its feet. A machine sitting straight on the floor
    #    looks dropped; a machine on a base looks placed.
    _solid(px, 1, floor - 5 + drop, FRONT_W - 2, floor, SHELL, PLANE_FRONT - 1, radius=2)

    # 2. THE BODY. One red block, corners knocked off, running from under the
    #    hood down to the plinth.
    _solid(px, BODY_L, CROWN_BOTTOM + drop, BODY_R, floor - 4 + drop, SHELL,
           PLANE_FRONT, radius=3)

    # 3. THE HOOD, wider than the body and gold, with the bulb sockets in it.
    #    It is the part that lights up, so the silhouette has to say so before
    #    a single additive pixel is drawn on it.
    _solid(px, 1, CROWN_TOP + drop, FRONT_W - 2, CROWN_BOTTOM + drop, TRIM,
           PLANE_FRONT, radius=3, top=PLANE_FRONT + 1)
    #    The marquee itself: a dark glass bar in the hood's face, so the bulbs
    #    have something to sit on that is not the same gold they are.
    _flat(px, 4, CROWN_TOP + 2 + drop, FRONT_W - 5, CROWN_BOTTOM - 2 + drop,
          GLASSDARK, 1, radius=1)
    span = (FRONT_W - 5) - 4
    for i in range(BULBS):
        bx = 4 + round(i * span / (BULBS - 1))
        by = CROWN_TOP + 4 + drop
        # A dark socket with a lit bead in it. Gold bulbs on a gold hood are
        # invisible until the marquee sheet fires; the socket is what says
        # "bulb" on an unpowered machine.
        _put(px, bx, by, _step(BULB, 4))
        _put(px, bx, by + 1, _step(TRIM, 0))

    # 4. THE FASCIA: one cream panel the three windows are cut into. One panel
    #    rather than three portholes, because three cells on ONE line is the
    #    only rule this machine has. It is INSET into the shell — a step back
    #    from the red on both sides — so the glass sits inside the machine.
    _flat(px, BODY_L + 1, REEL_Y - 3 + drop, BODY_R - 1, REEL_Y + REEL_H + 1 + drop,
          PANEL, PLANE_FRONT + 1, radius=1)
    for x in range(BODY_L + 1, BODY_R):
        _put(px, x, REEL_Y - 3 + drop, _step(PANEL, PLANE_FRONT - 1))
    for lip in (REEL_Y - 2 + drop, REEL_Y + REEL_H + 1 + drop):
        for x in range(BODY_L + 2, BODY_R - 1):
            _put(px, x, lip, _step(TRIM, 3))
    for index in range(3):
        rx = REEL_X + index * (REEL_W + REEL_GAP)
        ry = REEL_Y + drop
        for y in range(ry, ry + REEL_H):
            for x in range(rx, rx + REEL_W):
                _put(px, x, y, _step(GLASSDARK, 1))
        # The bezel each window is sunk into: dark above, gold under. Same pair
        # of edges as `_recess` and for the same reason — a window flush with
        # the panel is a rectangle printed on it.
        for x in range(rx, rx + REEL_W):
            _put(px, x, ry - 1, _step(GLASSDARK, 0))

    # THE PAY LINE: a gold tick in each of the two gaps BETWEEN the windows. It
    # is the one piece of a slot machine that explains the rules without a word,
    # and it is why the client can flash that row and have it mean something. In
    # the gaps rather than in the windows, which are painted over every frame of
    # a spin.
    mid = REEL_Y + REEL_H // 2 + drop
    for gap in range(2):
        tick = REEL_X + REEL_W + gap * (REEL_W + REEL_GAP)
        for y in range(mid - 1, mid + 1):
            for x in range(tick, tick + REEL_GAP):
                _put(px, x, y, _step(TRIM, 4))

    # 5. THE CONTROL DECK. The shelf between the glass and the tray, and the
    #    part that does most of the work: it stands PROUD of the body on both
    #    sides, so the cabinet has one horizontal break in it and the eye gets
    #    a surface to stand on halfway up. Its top plane is where the buttons
    #    are and where the coin goes, which is also where a player's hands
    #    would be — the machine tells you where to stand by its shape.
    _solid(px, BODY_L - 1, DECK_TOP + drop, BODY_R + 1, DECK_BOTTOM + drop, PANEL,
           PLANE_FRONT, radius=1, top=PLANE_FRONT + 1)
    #    Three buttons and a coin slot, ON the deck's top plane rather than on
    #    its front edge — four pixels back and two up, which is where that
    #    plane is. Two pixels each: at this size a button is a colour, not a
    #    shape, and the colours are the two the machine already uses.
    back = 4
    deck_face = DECK_TOP - int(back * SLOPE) + drop
    for index, ramp in enumerate((RED, BULB, RED)):
        bx = BODY_L + 4 + index * 6 + back
        _put(px, bx, deck_face, _step(ramp, 3))
        _put(px, bx + 1, deck_face, _step(ramp, 4))
    for x in range(BODY_R - 6 + back, BODY_R - 2 + back):
        _put(px, x, deck_face, _step(GLASSDARK, 1))
        _put(px, x, deck_face - 1, _step(TRIM, 3))

    # 6. THE TRAY: a hole in the plinth with a gold lip under it. Drawn as a
    #    recess so the eye reads a HOLE, which is what makes a canister
    #    appearing in it a delivery rather than a sprite that faded in.
    _recess(px, TRAY_L, TRAY_TOP + drop, TRAY_R, TRAY_BOTTOM + drop, TRIM)

    # 7. THE LEVER BOSS: a gold mount on the FLANK for the arm to pivot on, so
    #    the sheet the client blits over it has something to be attached to at
    #    every angle. On the side plane, half the run back, which is where the
    #    anchor above puts the arm.
    ax = BODY_R + int(DEPTH * 0.55)
    ay = DECK_BOTTOM + 3 - int(DEPTH * 0.55 * SLOPE) + drop
    for y in range(ay - 1, ay + 2):
        for x in range(ax - 2, ax + 1):
            _put(px, x, y, _step(TRIM, 2 if y != ay else 3))

    outline(img, OUTLINE)
    return img


# --- the reel band ----------------------------------------------------------


def _face(px, top: int, rarity: str) -> None:
    """One cell of the band: a filled lozenge in the tier's colour.

    It has to be readable as a COLOUR at ten pixels across and while it is
    moving, so it is a solid mass rather than a symbol — the symbol is on the
    canister, where there is room for one. A rim of glass either side keeps the
    cells from merging into a stripe when the band is running.
    """
    ramp = RARITY[rarity]
    for row in range(REEL_H):
        y = top + row
        for x in range(REEL_W):
            nx = (x + 0.5) / REEL_W - 0.5
            ny = (row + 0.5) / REEL_H - 0.5
            d = abs(nx) * 1.5 + abs(ny) * 1.25
            if d > 0.60:
                px[x, y] = pick(GLASSDARK, 0.2, x, y)
            elif d > 0.32:
                px[x, y] = pick(ramp, 0.9 - d * 0.4, x, y)
            else:
                px[x, y] = pick(ramp, 0.25, x, y)


def make_strip() -> Image.Image:
    """The whole band as one tall image. See `BAND` and the module docstring.

    A DIVIDER BETWEEN CELLS, and it is not decoration: a band of ten lozenges
    with nothing between them slides past as one texture, and the eye cannot
    count what it cannot separate. One dark row per cell is what turns a moving
    strip into a moving strip of THINGS, which is the whole reason slowing down
    means anything.
    """
    img = Image.new("RGBA", (REEL_W, REEL_H * CELLS), TRANSPARENT)
    px = img.load()
    for index, rarity in enumerate(BAND):
        top = index * REEL_H
        _face(px, top, rarity)
        for x in range(REEL_W):
            px[x, top] = pick(GLASSDARK, 0.05, x, top)
    return img


# --- the lever --------------------------------------------------------------


def make_lever(frame: int, frames: int) -> Image.Image:
    """The arm, from resting to fully pulled.

    IT ROTATES AROUND ITS PIVOT AND NOTHING ELSE. An earlier version walked the
    arm out with a per-step drift that looked fine at rest and posted the ball
    off the top of the frame at full travel, which is the failure mode of every
    hand-tuned pixel animation: it is drawn for the pose you were looking at.
    A real angle sweep between two authored stops cannot do that.

    The ball is the only pure red thing on the machine and it stays red at
    every angle — the eye tracks the knob, so the knob is what has to stay
    legible while it moves.
    """
    img = Image.new("RGBA", (LEVER_W, LEVER_H), TRANSPARENT)
    px = img.load()
    t = frame / max(1, frames - 1)
    # Up-and-out at rest, down-and-out when pulled. Not a full sweep to
    # horizontal: an arm that ends level reads as a handle that came off.
    angle = math.radians(-72.0 + t * 118.0)
    pivot_x, pivot_y = LEVER_PIVOT
    reach_x, reach_y = 6.0, 10.0

    steps = 22
    for step in range(steps + 1):
        f = step / steps
        x = pivot_x + math.cos(angle) * reach_x * f
        y = pivot_y + math.sin(angle) * reach_y * f
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < LEVER_W and 0 <= iy < LEVER_H):
            continue
        px[ix, iy] = _step(CHROME, 4)
        # A second column, so the shaft has thickness and does not disappear
        # into the cabinet behind it at the angles where it is nearly vertical.
        if ix + 1 < LEVER_W:
            px[ix + 1, iy] = _step(CHROME, 2)

    bx = pivot_x + math.cos(angle) * reach_x
    by = pivot_y + math.sin(angle) * reach_y
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy > 5:
                continue
            ix, iy = int(round(bx + dx)), int(round(by + dy))
            if 0 <= ix < LEVER_W and 0 <= iy < LEVER_H:
                # One white bead top-left, which is the whole cartoon
                # highlight vocabulary and the reason the knob reads as a
                # sphere at five pixels across.
                px[ix, iy] = _step(RED, 4) if (dx, dy) == (-1, -1) else _step(RED, 3)
    outline(img, OUTLINE)
    return img


# --- the light --------------------------------------------------------------


def make_marquee(frame: int, frames: int) -> Image.Image:
    """The crown's bulbs, chasing. Greyscale, additive, tinted by the client.

    A CHASE RATHER THAN A PULSE. Every other light in this game breathes,
    because everything else that glows out here is fire. Bulbs going round a
    sign in sequence is the one motion nothing organic makes, and it is what
    says ELECTRIC from across the clearing without a single word.
    """
    field = [[0.0] * MARQUEE_W for _ in range(MARQUEE_H)]
    phase = frame / frames
    for i in range(BULBS):
        bx = 4.0 + i * (MARQUEE_W - 8.0) / (BULBS - 1)
        # Each bulb peaks a fraction of a cycle after the one to its left.
        local = (phase - i / BULBS) % 1.0
        heat = max(0.0, 1.0 - abs(local - 0.5) * 3.2)
        ellipse(field, bx, 5.0, 2.2, 2.2, 0.55 + heat * 1.5)
        ellipse(field, bx, 5.0, 4.4, 3.8, 0.12 + heat * 0.3)
    # The wash the whole crown throws down over the glass.
    ellipse(field, MARQUEE_W / 2.0, 11.0, 17.0, 7.0, 0.28)
    img = Image.new("RGBA", (MARQUEE_W, MARQUEE_H), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def make_window(frame: int, frames: int) -> Image.Image:
    """The backlight behind the three reels. Greyscale, additive.

    Steady with a slow sag, because it is a lamp behind glass rather than a
    signal: the reels are what move, and a backlight that flickered would make
    them look like they were stuttering.
    """
    field = [[0.0] * WINDOW_W for _ in range(WINDOW_H)]
    sag = 0.88 + 0.12 * math.sin(frame / frames * math.tau)
    for index in range(3):
        # Centred on the glass the client centres this sheet on, derived from
        # the same three numbers rather than eyeballed — see `drawMachineLight`.
        cx = (WINDOW_W - (3 * REEL_W + 2 * REEL_GAP)) / 2.0 + index * (
            REEL_W + REEL_GAP
        ) + REEL_W / 2.0
        ellipse(field, cx, WINDOW_H / 2.0, 4.0, 6.5, 0.85 * sag)
        ellipse(field, cx, WINDOW_H / 2.0, 6.5, 8.0, 0.2 * sag)
    img = Image.new("RGBA", (WINDOW_W, WINDOW_H), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def make_burst(frame: int, frames: int) -> Image.Image:
    """The payout flash. Greyscale, additive, tinted with the RARITY.

    One shot, and the whole reason the tier is worth watching for: a common
    pull throws a small dim ring and a legendary throws a wide one, because the
    CLIENT scales this sheet by the tier rather than the sheet carrying five
    versions of itself. Shape here, magnitude there.

    A ring plus a star, not a ball. A filled flash at this size is a white
    blob; a ring says something LEFT the machine, which is what happened.
    """
    field = [[0.0] * BURST for _ in range(BURST)]
    t = frame / max(1, frames - 1)
    cx = cy = BURST / 2.0
    grow = 3.0 + t * 19.0
    fade = (1.0 - t) ** 1.6
    ellipse(field, cx, cy, grow, grow * 0.82, 1.5 * fade, hollow=0.62)
    ellipse(field, cx, cy, 5.0 - t * 3.0, 5.0 - t * 3.0, 2.2 * (1.0 - t) ** 3)
    # Four spikes, on the diagonals so they do not sit on the ring's own axes.
    reach = 6.0 + t * 19.0
    for angle in (0.7854, 2.3562, 3.9270, 5.4978):
        for step in range(int(reach)):
            f = step / max(1.0, reach)
            add(
                field,
                int(cx + math.cos(angle) * step),
                int(cy + math.sin(angle) * step),
                1.3 * fade * (1.0 - f),
            )
    img = Image.new("RGBA", (BURST, BURST), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "machine"
    out_dir.mkdir(parents=True, exist_ok=True)

    cabinets = [make_cabinet(settled) for settled in (False, True)]
    pack(cabinets, CAB_W, CAB_H).save(out_dir / "cabinet.png")

    strip = make_strip()
    strip.save(out_dir / "strip.png")

    lever_frames = 6
    levers = [make_lever(i, lever_frames) for i in range(lever_frames)]
    pack(levers, LEVER_W, LEVER_H).save(out_dir / "lever.png")

    marquee_frames = 10
    marquees = [make_marquee(i, marquee_frames) for i in range(marquee_frames)]
    pack(marquees, MARQUEE_W, MARQUEE_H).save(out_dir / "marquee.png")

    window_frames = 6
    windows = [make_window(i, window_frames) for i in range(window_frames)]
    pack(windows, WINDOW_W, WINDOW_H).save(out_dir / "window.png")

    burst_frames = 12
    bursts = [make_burst(i, burst_frames) for i in range(burst_frames)]
    pack(bursts, BURST, BURST).save(out_dir / "burst.png")

    manifest = {
        "seed": args.seed,
        "cabinet": {
            "file": "cabinet.png",
            "frameWidth": CAB_W,
            "frameHeight": CAB_H,
            "frames": len(cabinets),
            # The contact is the bottom row: this is a bottom-anchored prop
            # like a table or a torch, and the client sorts it by that row.
            "reels": [list(_reel_slot(i)) for i in range(3)],
            "reelWidth": REEL_W,
            "reelHeight": REEL_H,
            "lever": list(LEVER_ANCHOR),
            # Where a canister is launched from, in frame pixels. The client
            # arcs it out of this hole rather than out of the cabinet's centre.
            "trayMouth": [ORIGIN_X + (TRAY_L + TRAY_R) // 2, ORIGIN_Y + TRAY_BOTTOM - 1],
            "crown": [ORIGIN_X + FRONT_W // 2,
                      ORIGIN_Y + (CROWN_TOP + CROWN_BOTTOM) // 2],
            # The row the three cells have to agree on, in frame pixels. The
            # client flashes it when they do — see the brass ticks above.
            "payLine": ORIGIN_Y + REEL_Y + REEL_H // 2,
        },
        # THE BAND. One image, `cells` tall, scrolled and wrapped by the client
        # — see `game/machine.ts` `reelScroll`. `frameHeight` is the WINDOW,
        # not the sheet: what the cabinet shows is one cell at a time.
        "reel": {
            "file": "strip.png",
            "frameWidth": REEL_W,
            "frameHeight": REEL_H,
            "cells": CELLS,
            "band": list(BAND),
        },
        "lever": {
            "file": "lever.png",
            "frameWidth": LEVER_W,
            "frameHeight": LEVER_H,
            "frames": lever_frames,
            # Where the pivot is INSIDE this sheet. The client draws the arm at
            # `cabinet.lever - lever.pivot`, so moving either end is one edit.
            "pivot": list(LEVER_PIVOT),
        },
        "effects": {
            "marquee": {
                "file": "marquee.png",
                "frameWidth": MARQUEE_W,
                "frameHeight": MARQUEE_H,
                "frames": marquee_frames,
                "fps": 14,
                "anchorY": MARQUEE_H // 2,
                "loop": True,
                "tinted": True,
            },
            "window": {
                "file": "window.png",
                "frameWidth": WINDOW_W,
                "frameHeight": WINDOW_H,
                "frames": window_frames,
                "fps": 8,
                "anchorY": WINDOW_H // 2,
                "loop": True,
                "tinted": True,
            },
            "burst": {
                "file": "burst.png",
                "frameWidth": BURST,
                "frameHeight": BURST,
                "frames": burst_frames,
                "fps": 18,
                "anchorY": BURST // 2,
                "loop": False,
                "tinted": True,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the upgrade machine.")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    out = build(args)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
