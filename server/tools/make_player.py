#!/usr/bin/env python3
"""Asset pipeline: THE PLAYERS — the body, the pack it carries, and the skins.

Output (assets/raw/, then `process_sprites.py --exact` turns each into
assets/processed/<name>/):

    player.png            3x3 grid, 16x16   the survivor everybody starts as
    player-explorer.png   3x3 grid, 16x16   ALT SKIN — the one who came out here
    backpack.png          3x3 grid, 16x16   OVERLAY, worn over either of them

WHY THIS FILE EXISTS.
The player was the last thing in the game still coming out of hand-drawn raw
art, and it showed: a white capsule with a dark cap on it, four rows of the
same blob, a walk cycle that was one pixel of vertical bob and nothing else.
Every other sprite in this repository is a RECIPE — the reason a barrel and a
cabinet look like they come from one hand is that the rules are written down
once, in code, and every asset is drawn through them. The body the camera is
locked to is the last place that should be an exception.

WHAT A PLAYER IS, IN THIS GAME'S GRAMMAR.
Sixteen pixels, and the reference sheets that set this style spend them the
same way every time: a HEAD that is nearly half the sprite, a small body under
it, a one-pixel dark outline all the way round, and two or three flat colours
inside. Nothing is rendered — a face is four dark pixels, a hand is one. What
carries a character at this size is the SILHOUETTE and the value structure, so
that is where the pixels go, and detail below that threshold is deleted rather
than shrunk (S16).

THE SHEET IS MULTIPLIED BY THE PLAYER'S COLOUR, and it decides the palette.
`client/src/render/sprites.ts` multiplies the whole bitmap by one of fifteen
saturated hues, so anything authored near WHITE comes out as that hue at full
strength and anything authored near BLACK stays black whatever the hue is.
That is the whole reason the coat is a three-step near-neutral ramp and the
boots, the straps, the outline and the hair are not: the coat is the part that
says WHICH PLAYER, and everything else has to survive fifteen multiplies
without turning into a colour nobody chose. Skin is the one compromise — it is
warm, so it tints — and it is kept to a face-sized patch for exactly that
reason.

THE WALK IS THE LEGS AND ONE PIXEL OF BOB.
Three columns per row, ordered `[0, 1, 2, 1]` by the manifest. Column 1 is the
PASSING pose — legs together, body at full height — and it is also the idle,
which is why a standing player does not look like a walk cycle that stopped.
Columns 0 and 2 are the two CONTACTS: legs apart, body one pixel lower. That
drop is not decoration; a body that keeps its height through a stride is a
sprite sliding along the floor, and one pixel at this scale is the whole
difference. The legs are authored separately from the body for the same
reason a `_solid` is not authored per part: the animation IS the legs, so the
body is drawn once per facing and the legs are three poses over it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "assets" / "raw"

TILE = 16
KEY = (255, 0, 255, 255)

# --- palette ----------------------------------------------------------------
# Two ramps and a handful of accents, and the split between them is the tint
# rule above, not taste.
#
# CLOTH is the tinted half: three steps of near-neutral, spaced far enough
# apart to still read as three after a multiply by a mid-value hue (S7 — hard
# cel bands, no gradient). Lit on the top-left, shaded bottom-right, per S8.
#
# Everything else is authored to SURVIVE the multiply: the outline, the boots,
# the straps and the hair are dark enough that any hue leaves them dark, and
# the leather is warm enough to stay leather.

#: Letter -> colour, and the letters are what the art is written in. One table
#: for every sheet here: a skin is a different recipe over the same alphabet,
#: never a second alphabet.
PALETTE: dict[str, str] = {
    "o": "#141220",   # the outline, and the darkest thing on the sprite
    "k": "#3a3550",   # hair, and the coat's dark opening
    "j": "#26223a",   # hair in shadow
    "W": "#f2f2f2",   # cloth, lit    | PURE GREY = DYED. See `DYED` below.
    "w": "#c6c6c6",   # cloth, body    |
    "v": "#949494",   # cloth, shade   |
    "B": "#5a5a5a",   # boots          |
    "s": "#f0c9a3",   # skin
    "d": "#cf9f76",   # skin, shade
    "P": "#4a4560",   # trousers
    "p": "#332f45",   # trousers, the far leg
    "h": "#514b6e",   # hair, lit
    "L": "#a97c4c",   # leather, lit
    "l": "#7d5a36",   # leather
    "n": "#4e3823",   # leather, shade
    "g": "#5e93a3",   # goggle glass
}

#: The alphabet under names, so the drawing below reads as anatomy rather than
#: as letters. Nothing here picks a colour — it picks a MATERIAL, and the table
#: above is the only place a hex value is written down.
#: THE DYE CONTRACT, and it is half of a rule whose other half lives in
#: `client/src/render/sprites.ts`. A player's colour is multiplied onto the
#: sheet's PURE GREY pixels and nothing else, so the coat and the boots come
#: out in that colour and the face, the hair, the hat, the leather and the
#: trousers come out as themselves.
#:
#: It used to multiply the whole bitmap. Fifteen hues of a person made
#: entirely of one hue is fifteen palette swaps of the same blob — the
#: character underneath was gone in all of them, and the alt skin was
#: pointless the moment a colour was assigned. Which is why the rule is
#: ASSERTED at the bottom of this file rather than described: a new material
#: authored grey by accident is a new material that changes colour per player,
#: and nothing at runtime can tell that was not intended.
DYED = ("W", "w", "v", "B")

SKIN, SKIN_SHADE = "s", "d"
HAIR_SHADE, HAIR_LIT = "j", "h"
CLOTH_HI, CLOTH_M, CLOTH_LO = "W", "w", "v"
BOOT = "B"
DARKCLOTH = "k"
HAND = "s"
LEATHER_H, LEATHER_M, LEATHER_L = "L", "l", "n"
GLASS = "g"


def rgba_of(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


RGBA = {key: rgba_of(colour) for key, colour in PALETTE.items()}


# --- the anatomy -------------------------------------------------------------
# EVERY PIXEL BELOW IS DERIVED FROM FIVE NUMBERS, and that is deliberate. The
# first cut of this file was hand-counted ASCII rows, which is how a sprite
# ends up one pixel wider on one facing than on another and nobody can say
# which one is wrong. Bands, not art: the head is a box with rounded corners
# and a hair cap on it, the body is a box with sleeves, and the two agree
# about the centreline because they are both measured from it.
#
# THE PROPORTIONS ARE THE STYLE (S17). Head seven rows of fifteen, body four,
# legs three: a head just under half the figure, which is what the reference
# sheets spend their pixels on and what makes sixteen pixels read as a person
# rather than as a small adult. Anything else is detail, and detail below the
# threshold is DELETED rather than shrunk (S16) — there is no mouth on this
# sprite, and no fingers.

#: The centreline. Everything is measured out from it, both ways.
MID = 8
HEAD_TOP, HEAD_BOTTOM = 1, 8
HEAD_HALF = 5
#: The body's top row IS the head's bottom row. Two adjacent full-width
#: outline rows put a black bar across the neck, which at this size reads as a
#: gap between two sprites rather than as a join in one.
BODY_TOP, BODY_BOTTOM = 8, 12
BODY_HALF = 4
#: The row the legs start on. The feet land on y15 whatever the body is doing
#: above them, which is the point of authoring the two separately: a bob that
#: moved the contact would be a character bouncing off the floor.
LEG_TOP = 13
#: How far the body drops on a contact frame, in pixels.
BOB = (1, 0, 1)


def _box(cell, x0: int, y0: int, x1: int, y1: int, fill: str, line: str = "o",
         round_top: bool = True, round_bottom: bool = True) -> None:
    """A filled rectangle with a one-pixel outline and its corners knocked off.

    The corner cut is one taxicab pixel, which is all a shape this size can
    afford: two reads as a circle and none reads as a crate. S6 — the outline
    is closed and one pixel at every size, never thicker.
    """
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            corner = (
                (x in (x0, x1) and y == y0 and round_top)
                or (x in (x0, x1) and y == y1 and round_bottom)
            )
            if corner:
                continue
            edge = x in (x0, x1) or y in (y0, y1)
            _put(cell, x, y, line if edge else fill)


def _band(cell, y: int, x0: int, x1: int, key: str) -> None:
    """One row of one value, inside whatever is already there."""
    for x in range(x0, x1 + 1):
        if _get(cell, x, y) not in (".", "o"):
            _put(cell, x, y, key)


def _head(cell, facing: str, top: int, hair: str) -> None:
    """The head: a box, a hair cap over it, a face under that.

    THE HAIR IS A SEPARATE VALUE FROM THE OUTLINE and that is not a detail. At
    the first pass both were near-black and the whole top half of the sprite
    came out as one dark mass with a light slot in it — the head had no shape,
    only a hole. Two steps apart (S3) is what makes a cap read as hair sitting
    ON a skull.

    THE SHADE GOES DOWN BEFORE THE HAIR DOES. Painted the other way round the
    shade column ate the right temple and the sprite came out with hair on one
    side of its face and none on the other — a bug that is invisible in code
    and unmissable on screen.
    """
    x0, x1 = MID - HEAD_HALF, MID + HEAD_HALF - 1
    bottom = top + HEAD_BOTTOM - HEAD_TOP
    _box(cell, x0, top, x1, bottom, SKIN)
    # THE KEY IS TOP-LEFT (S8): the right-hand column of the face is the shade
    # side on every facing, and the jaw takes a second step under it.
    for y in range(top + 3, bottom):
        _put(cell, x1 - 1, y, SKIN_SHADE)
    # The jaw's shadow is the RIGHT half of the chin, not the whole row. Run
    # across, it is a beard: the face came out as a light band between two
    # dark ones and read as a mask rather than as a head.
    _band(cell, bottom - 1, MID - 1, x1 - 2, SKIN_SHADE)
    # The cap: two rows solid INSIDE the outline, then the temples one row
    # further down, so the hairline is a shape rather than a straight cut
    # across the forehead. Row `top` is the outline itself — painting the cap
    # onto it is how the first pass ended up with a head one row shorter than
    # the one it was measured for.
    _band(cell, top + 1, x0 + 1, x1 - 1, hair)
    _band(cell, top + 2, x0 + 1, x1 - 1, hair)
    _put(cell, x0 + 1, top + 3, hair)
    _put(cell, x1 - 1, top + 3, hair)
    # Two lit pixels where the sky hits the crown. It is the only highlight on
    # the head and it is what stops the cap reading as a flat lid.
    _put(cell, x0 + 2, top + 1, HAIR_LIT)
    _put(cell, x0 + 3, top + 1, HAIR_LIT)
    if facing == "up":
        # From behind there is no face: the cap runs to the jaw, and the last
        # row under it is the neck in its own shadow.
        for y in range(top + 3, bottom):
            _band(cell, y, x0 + 1, x1 - 1, hair)
        _band(cell, bottom - 1, x0 + 2, x1 - 2, HAIR_SHADE)
        _put(cell, x1 - 1, bottom - 2, HAIR_SHADE)
        return
    if facing == "down":
        # Two eyes, two pixels each, and the whole nose is the gap between
        # them. A pupil inside a sclera at this size is four pixels of mud.
        for ex in (x0 + 2, x1 - 3):
            _put(cell, ex, top + 4, "o")
            _put(cell, ex + 1, top + 4, "o")
        return
    # SIDE. The raw sheet's side row faces RIGHT (`process_sprites
    # --side-facing right` mirrors it into the left row), so the back of the
    # head is the LEFT edge: the cap runs down that side to the jaw, and the
    # face is the two columns before the nose.
    for y in range(top + 3, bottom):
        _band(cell, y, x0 + 1, x0 + 2, hair)
    _put(cell, x1 - 3, top + 4, "o")
    _put(cell, x1 - 2, top + 4, "o")
    # The nose: one pixel PROUD of the silhouette, with an outline on its far
    # side so it does not read as a stray. It is most of what makes a profile
    # a profile at this size.
    _put(cell, x1 + 1, top + 5, SKIN)
    _put(cell, x1 + 2, top + 5, "o")
    _put(cell, x1 + 1, top + 6, "o")


def _body(cell, facing: str, top: int) -> None:
    """The coat, the sleeves and the hands.

    THE COAT IS THE TINTED PART. Three steps of the cloth ramp, lit top-left
    and shaded into the bottom-right corner, so a multiply by any of the
    fifteen player hues lands three readable values of that hue rather than
    one flat patch of it. The break runs DIAGONALLY, with the key at 135deg,
    which is the same terminator every solid in the scenery folder uses.

    THE SLEEVES ARE CAPPED. A bare column of cloth hanging off the shoulder
    line is a pixel that fell off the sprite; an outline over it and a hand
    under it is an arm.
    """
    x0, x1 = MID - BODY_HALF, MID + BODY_HALF - 1
    bottom = top + BODY_BOTTOM - BODY_TOP
    _box(cell, x0, top, x1, bottom, CLOTH_M, round_top=False, round_bottom=False)
    for y in range(top + 1, bottom):
        for x in range(x0 + 1, x1):
            reach = (x - x0) + (y - top)
            if reach <= 4:
                _put(cell, x, y, CLOTH_HI)
            elif reach >= 8:
                _put(cell, x, y, CLOTH_LO)
    # THE HEM is the coat's own shade, not an outline. A full dark row over
    # the legs reads as a gap the light gets through; the coat has to end IN
    # the legs, the way a coat does.
    for x in range(x0 + 1, x1):
        _put(cell, x, bottom, CLOTH_LO)
    if facing == "up":
        # The back of the coat: no fastening, one seam down the middle.
        for y in range(top + 1, bottom):
            _put(cell, MID - 1, y, CLOTH_LO)
    elif facing == "down":
        # The front: a dark opening down the centre, which is the one mark
        # that says COAT rather than jumper and it costs three pixels.
        for y in range(top + 1, bottom):
            _put(cell, MID - 1, y, DARKCLOTH)
    # SLEEVES, one column proud of the coat on each side, with a hand under
    # them. On the side facing only the NEAR arm is drawn — the far one is
    # behind the body, and drawing it anyway is what makes a profile sprite
    # look like it is standing with its arms held out.
    arms = (x0 - 1, x1 + 1) if facing != "side" else (x1,)
    for ax in arms:
        if facing == "side":
            # Held across the front, not out at the side: one pixel of cloth
            # and one hand, on the leading edge of the body.
            _put(cell, ax + 1, top + 1, "o")
            _put(cell, ax + 1, top + 2, CLOTH_LO)
            _put(cell, ax + 1, top + 3, HAND)
            continue
        _put(cell, ax, top, "o")
        _put(cell, ax, top + 1, CLOTH_HI if ax < MID else CLOTH_LO)
        _put(cell, ax, top + 2, CLOTH_M if ax < MID else CLOTH_LO)
        _put(cell, ax, top + 3, HAND)


#: WHICH SIDE THE WEAPON HAND IS ON, per source row, as a cell column.
#:
#: THE CHARACTER IS RIGHT-HANDED and that is the whole table: facing the
#: camera his right hand is on the LEFT of the screen, facing away it is on
#: the right, and in profile it is the near one — the arm the camera can see.
#: The client mirrors these three numbers (`render/guns.ts` `HOLD_HAND`) to
#: decide which side of the body the weapon hangs off, so a pose authored here
#: and a grip placed there cannot disagree about which hand is holding it.
HOLD_ARM_X = {
    "down": MID - BODY_HALF - 1,
    "side": MID + BODY_HALF,
    "up": MID + BODY_HALF,
}
#: The row the raised wrist lands on, measured from `BODY_TOP`. One row above
#: where the arm hangs at rest, which is the whole animation: a hand at the
#: hem is a hand doing nothing, and a hand at the chest is a hand holding
#: something. Anything more at this size is a limb with a joint in it, and
#: sixteen pixels does not have room for a joint.
HOLD_WRIST_ROW = 2


def _hold(cell, facing: str, top: int) -> None:
    """The HOLDING pose: the weapon arm up at the chest, the other one in.

    THIS IS A SECOND POSE OF THE SAME CHARACTER, not a second character. The
    walk rows are somebody with their arms down; these are the same body, the
    same stride, the same head, with two pixels moved — and two pixels is the
    entire budget a pose change has here. What sells it is not the arm, it is
    the ASYMMETRY: one hand up and forward, one hand tucked in against the
    coat. A figure with both arms raised reads as surrender and a figure with
    both arms down reads as somebody out for a walk, so the pose has to be
    lopsided or it says nothing at all.

    The raised hand is where the WEAPON is, and the client places the grip off
    the same side (`HOLD_ARM_X`). The gap between this wrist and that grip is
    closed at runtime by `client/src/render/arms.ts`, which is why the arm is
    authored SHORT: a long arm drawn here would point one way while the mouse
    pointed another.
    """
    wx = HOLD_ARM_X[facing]
    lit = CLOTH_HI if wx < MID else CLOTH_LO
    out = wx + 1 if wx > MID else wx - 1
    _put(cell, wx, top, "o")
    _put(cell, wx, top + 1, lit)
    # THE ARM COMES OFF THE BODY. A hand raised inside the sleeve's own column
    # is a pixel that moved; a hand a column PROUD of it is a limb, and the
    # silhouette is the only thing that survives at this size (S15).
    _put(cell, wx, top + HOLD_WRIST_ROW, CLOTH_M)
    _put(cell, out, top + HOLD_WRIST_ROW, HAND)
    _put(cell, out, top + 1, "o")
    # The hand that used to hang at the hem is up at the chest now, so the hem
    # row goes back to being the coat's.
    _put(cell, wx, top + 3, ".")
    if facing == "side":
        # In profile the arm reads along its LENGTH rather than across it, so
        # it spends its outline pixel under the hand instead of over it: from
        # the side you are looking down the arm, not at it.
        _put(cell, out, top + 1, ".")
        _put(cell, out, top + 3, "o")
        return
    # THE OFF HAND COMES ACROSS, one column inside the coat's edge. It is not
    # a second grip — this pose is worn by a pistol as well as a rifle — it is
    # the tuck that makes the raised arm read as deliberate.
    ox = MID + BODY_HALF if wx < MID else MID - BODY_HALF - 1
    _put(cell, ox, top + 3, ".")
    _put(cell, ox, top + 2, CLOTH_HI if ox < MID else CLOTH_LO)
    _put(cell, ox - 1 if ox > MID else ox + 1, top + 3, HAND)


#: THE THREE LEG POSES, y13..y15. Column 1 is legs together — the passing
#: pose, and also the idle, which is why a standing player does not look like
#: a walk cycle somebody paused. Columns 0 and 2 are the contacts, and what
#: moves between them is the BOOT: one foot planted on the ground row and the
#: other lifted a pixel off it. Nothing here is allowed outside the coat's own
#: width — legs that stick out past the shoulders read as a stance, not a
#: stride, and the silhouette stops being one shape.
LEGS_DOWN = (
    (
        ".....PP..PP.....",
        ".....PP..BB.....",
        ".....BB.........",
    ),
    (
        ".....PP..PP.....",
        ".....PP..PP.....",
        ".....BB..BB.....",
    ),
    (
        ".....PP..PP.....",
        ".....BB..PP.....",
        ".........BB.....",
    ),
)

#: The profile stride separates ALONG the walk rather than across it. The
#: front leg is the lit one and the back leg is a step darker, which is the
#: only thing telling the two apart when they are the same two pixels.
LEGS_SIDE = (
    (
        ".....pp..PP.....",
        ".....pp..PP.....",
        ".....BB..BB.....",
    ),
    (
        "......PPPP......",
        "......PPPP......",
        "......BBBB......",
    ),
    (
        "......pp.PP.....",
        "......pp.PP.....",
        "......BB.BB.....",
    ),
)


# --- skins ------------------------------------------------------------------
# A SKIN IS A RECIPE, NOT A SECOND SHEET. Everything above is the anatomy —
# the same head, the same stride, the same silhouette — and a skin is a short
# list of pixels stamped over it plus a letter remap. That is what keeps two
# skins the same CHARACTER in two outfits rather than two characters, and it
# is why adding a third is a dict entry.


def _stamp_explorer(cell, facing: str, frame: int, bob: int) -> None:
    """The ALT SKIN: the one who came out here on purpose.

    Everything in this world is somebody's leftovers — a wrecked car, a crate
    nobody came back for, a shop run out of a cart. The default body is
    dressed like somebody who WOKE UP in it. This one is dressed like somebody
    who packed for it: a wide brim, goggles worn (not pushed up — they are for
    the dust and the dark), a heavy collar and gloves.

    THE BRIM IS THE SKIN, and it is the only part of this that is load
    bearing. Six identical round heads at the edge of a lantern are six of the
    same person; one with a straight dark line across it is somebody else at
    any distance the sprite survives (S15). It is the widest thing on the
    figure and it overhangs the head on both sides, which is what a hat does
    to a silhouette and what a hairstyle can never do.

    IT REPLACES THE HAIR RATHER THAN SITTING ON IT. Four rows of head are the
    hat — crown, crown, brim, the brim's own shadow — and the face keeps the
    three under them. A hat drawn over the hair as well needs a taller head
    than sixteen pixels has to give.
    """
    top = HEAD_TOP + bob
    x0, x1 = MID - HEAD_HALF, MID + HEAD_HALF - 1
    # THE CROWN, two rows, narrower than the head so the brim reads as proud
    # of it rather than as the same shape twice.
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, top, LEATHER_H if x < MID else LEATHER_M)
        _put(cell, x, top + 1, LEATHER_M if x < MID else LEATHER_L)
    _put(cell, x0 + 1, top + 1, "o")
    _put(cell, x1 - 1, top + 1, "o")
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, top - 1, "o")
    # THE BRIM: one lit row a pixel proud of the head on both sides, and its
    # own shadow under it. That second row is the line the eye actually reads
    # — a brim with no dark under it is a stripe painted on a forehead.
    for x in range(x0 - 1, x1 + 2):
        _put(cell, x, top + 2, LEATHER_H if x < MID else LEATHER_M)
    _put(cell, x0 - 1, top + 2, "o")
    _put(cell, x1 + 1, top + 2, "o")
    for x in range(x0, x1 + 1):
        _put(cell, x, top + 3, LEATHER_L)
    _put(cell, x0, top + 3, "o")
    _put(cell, x1, top + 3, "o")
    if facing != "up":
        # THE GOGGLES, worn. Two lenses with the strap between them on the
        # facing that has a face, one lens and a strap running back on a
        # profile. They sit ON the eye row: this is somebody who came out here
        # expecting the dust, not somebody wearing them as a hat decoration.
        eye = top + 4
        if facing == "down":
            for ex in (x0 + 2, x1 - 3):
                _put(cell, ex, eye, GLASS)
                _put(cell, ex + 1, eye, "o")
            _put(cell, x0 + 1, eye, LEATHER_L)
            _put(cell, x1 - 1, eye, LEATHER_L)
            _put(cell, MID - 1, eye, LEATHER_L)
            _put(cell, MID, eye, LEATHER_L)
        else:
            _put(cell, x1 - 3, eye, GLASS)
            _put(cell, x1 - 2, eye, "o")
            for x in range(x0 + 1, x1 - 3):
                _put(cell, x, eye, LEATHER_L)
    else:
        # From behind, the strap is all there is of them, and it is what says
        # the back of this head is still the explorer's.
        for x in range(x0 + 1, x1):
            _put(cell, x, top + 4, LEATHER_L)
    # THE COLLAR over the shoulders and the GLOVES on the hands. Both leather:
    # warm enough to stay leather under any of the fifteen player multiplies.
    collar = BODY_TOP + 1 + bob
    for x in range(MID - BODY_HALF + 1, MID + BODY_HALF - 1):
        if _get(cell, x, collar) in (CLOTH_HI, CLOTH_M, CLOTH_LO, DARKCLOTH):
            _put(cell, x, collar, LEATHER_L if x >= MID else LEATHER_M)
    # The gloves. The span is two columns wider than the coat on each side
    # because the HOLDING pose puts a hand out past the sleeve — a bare hand
    # on a body wearing gloves is the sort of thing nobody can name and
    # everybody sees.
    for x in range(MID - BODY_HALF - 2, MID + BODY_HALF + 2):
        for y in range(collar, collar + 4):
            if _get(cell, x, y) == HAND:
                _put(cell, x, y, LEATHER_M)


SKINS: dict[str, dict] = {
    #: The default. Dark hair, a pale coat, nothing on him that was chosen.
    "player": {"hair": "k", "stamp": None},
    #: The explorer. The hair goes a step warmer so the hat has something to
    #: sit on that is not the same colour as its own shadow.
    "player-explorer": {"hair": "n", "stamp": _stamp_explorer},
}


# --- the pack ---------------------------------------------------------------
# THE OVERLAY, and it is drawn from the wearer's side of the story: what you
# see of a rucksack depends entirely on which way its owner is standing.
#
#   down   two straps over the chest and nothing else. The pack is behind him.
#   side   a slab standing off the back, with the strap crossing the shoulder.
#   up     the whole pack, because that is what a pack looks like from behind.
#
# It is tinted with the wearer's colour like the body, so the canvas of it is
# on the same near-neutral cloth ramp with leather trim that survives the
# multiply — a pack that stayed brown while its owner went red would read as
# somebody else's pack.


def _pack(cell, facing: str, top: int) -> None:
    """The rucksack, from whichever side its owner is showing.

    IT IS DRAWN AT THE SIZE IT WEIGHS. The first pass was two strap pixels and
    a small box, which is a bag; what a player is carrying out of a night is a
    load, and the sprite has to be able to say so from across a clearing. From
    behind it is most of the torso. From the side it OVERHANGS the silhouette,
    and that overhang is the whole read — a loaded body has a different
    outline from an empty one, which is a thing you can see at eight pixels
    and a shade of colour is not.
    """
    x0, x1 = MID - BODY_HALF, MID + BODY_HALF - 1
    if facing == "down":
        # Two straps over the chest with a buckle on each, and nothing else:
        # the pack itself is behind him and drawing any of it here would be
        # drawing through his body.
        for x in (x0 + 2, x1 - 2):
            _put(cell, x, top + 1, LEATHER_M)
            _put(cell, x, top + 2, LEATHER_H)
            _put(cell, x, top + 3, LEATHER_L)
        _put(cell, x1 - 2, top + 2, LEATHER_M)
        return
    if facing == "up":
        # THE WHOLE PACK. A lid, a body, two side pockets and the roll strapped
        # under it — four masses at four values (S2), because one flat slab
        # the width of a back is a board, not a bag.
        _box(cell, x0, top, x1, top + 4, CLOTH_M, round_bottom=False)
        for x in range(x0 + 1, x1):
            _put(cell, x, top + 1, LEATHER_M if x < MID else LEATHER_L)
        for x in range(x0 + 1, x1):
            _put(cell, x, top + 2, CLOTH_HI if x < MID else CLOTH_M)
            _put(cell, x, top + 3, CLOTH_M if x < MID else CLOTH_LO)
        # The lid's own strap, straight down the middle, and the buckle on it.
        _put(cell, MID - 1, top + 1, LEATHER_H)
        _put(cell, MID - 1, top + 2, LEATHER_L)
        _put(cell, MID - 1, top + 3, LEATHER_M)
        # The roll, lashed across the bottom.
        for x in range(x0 + 1, x1):
            _put(cell, x, top + 4, LEATHER_L if x % 2 else LEATHER_M)
        _put(cell, x0, top + 4, "o")
        _put(cell, x1, top + 4, "o")
        return
    # SIDE: the pack stands off the BACK — the left of a sprite facing right —
    # and overhangs by two pixels. The strap comes over the shoulder and down
    # the chest, which is what ties the mass to the body carrying it.
    _box(cell, x0 - 2, top, x0 + 1, top + 4, CLOTH_M, round_bottom=False)
    for y in range(top + 1, top + 4):
        _put(cell, x0 - 1, y, CLOTH_HI if y < top + 3 else CLOTH_M)
        _put(cell, x0, y, CLOTH_M if y < top + 3 else CLOTH_LO)
    _put(cell, x0 - 1, top + 1, LEATHER_H)
    _put(cell, x0, top + 1, LEATHER_M)
    for x in range(x0 - 1, x0 + 2):
        _put(cell, x, top + 4, LEATHER_L)
    _put(cell, x0 + 2, top + 1, LEATHER_M)
    _put(cell, x0 + 3, top + 2, LEATHER_M)
    _put(cell, x0 + 3, top + 3, LEATHER_L)


# --- drawing ----------------------------------------------------------------


def _put(cell: list[list[str]], x: int, y: int, key: str) -> None:
    if 0 <= x < TILE and 0 <= y < TILE:
        cell[y][x] = key


def _get(cell: list[list[str]], x: int, y: int) -> str:
    if 0 <= x < TILE and 0 <= y < TILE:
        return cell[y][x]
    return "."


def _blit(cell: list[list[str]], art: tuple[str, ...], dy: int = 0) -> None:
    for y, row in enumerate(art):
        assert len(row) == TILE, f"row {y} is {len(row)} wide, not {TILE}"
        for x, key in enumerate(row):
            if key != ".":
                _put(cell, x, y + dy, key)


def _frame(facing: str, frame: int, skin: str, hold: bool = False) -> list[list[str]]:
    """One 16x16 cell as letters: body, head, legs, then whatever the skin adds.

    HEAD LAST OF THE THREE, because it overhangs: the cap is wider than the
    shoulders and it has to sit in front of them, the same way the pack sits
    behind. Order is the only depth this sprite has.
    """
    cell = [["." for _ in range(TILE)] for _ in range(TILE)]
    bob = BOB[frame]
    recipe = SKINS[skin]
    _body(cell, facing, BODY_TOP + bob)
    # Over the body and UNDER the head, like everything else on this sprite:
    # the arm belongs to the torso, and the head overhangs both.
    if hold:
        _hold(cell, facing, BODY_TOP + bob)
    _head(cell, facing, HEAD_TOP + bob, recipe["hair"])
    legs = LEGS_SIDE if facing == "side" else LEGS_DOWN
    _blit(cell, legs[frame], LEG_TOP)
    if recipe["stamp"]:
        recipe["stamp"](cell, facing, frame, bob)
    return cell


def _pack_frame(facing: str, frame: int) -> list[list[str]]:
    cell = [["." for _ in range(TILE)] for _ in range(TILE)]
    _pack(cell, facing, BODY_TOP + BOB[frame])
    return cell


def sheet(cells: list[list[list[str]]], rgba: dict | None = None) -> Image.Image:
    """A grid of lettered cells onto the raw magenta sheet.

    MAGENTA, because this is a RAW sheet: `process_sprites.py --exact` keys it
    out, mirrors the side row into the fourth and writes the manifest the
    client reads. One path to `processed/`, not two.

    Rows are facings (down, side, up) and columns are frames — three of them
    on a walk sheet, five on a death timeline. PUBLIC, and `rgba` is why:
    `make_zombie.py` draws the creatures on the same grid with the same
    primitives and its own colour table, and a second copy of this loop is a
    second opinion about what a raw sheet is.
    """
    rgba = RGBA if rgba is None else rgba
    rows = len(cells)
    cols = max(len(row) for row in cells)
    img = Image.new("RGBA", (TILE * cols, TILE * rows), KEY)
    px = img.load()
    for row, facing_cells in enumerate(cells):
        for col, cell in enumerate(facing_cells):
            for y in range(TILE):
                for x in range(TILE):
                    key = cell[y][x]
                    if key == ".":
                        continue
                    px[col * TILE + x, row * TILE + y] = rgba[key]
    return img


def _check_dye_contract() -> None:
    """PURE GREY IS THE DYE MASK. Both directions, before anything is written.

    Grey where it should not be is a material that changes colour per player;
    not-grey where it should be is a coat that never does. Neither is visible
    in this file, both are obvious on screen, and only one of them will ever
    be reported as a bug.
    """
    for key, value in PALETTE.items():
        r, g, b, _ = rgba_of(value)
        grey = r == g == b
        if key in DYED:
            assert grey, f"{key} ({value}) is dyed but is not pure grey"
        else:
            assert not grey, f"{key} ({value}) is not dyed but is pure grey"


def build(args) -> list[Path]:
    _check_dye_contract()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for skin in SKINS:
        # SIX ROWS: the three walk facings, then the same three HOLDING.
        # Appended rather than interleaved — the walk rows keep the indices
        # every processed sheet and every manifest already gives them, and a
        # sheet with no hold block simply has four output rows instead of
        # eight (`process_sprites.py`).
        cells = [[_frame(facing, frame, skin, hold) for frame in range(3)]
                 for hold in (False, True)
                 for facing in ("down", "side", "up")]
        path = RAW_DIR / f"{skin}.png"
        sheet(cells).save(path)
        written.append(path)
    cells = [[_pack_frame(facing, frame) for frame in range(3)]
             for facing in ("down", "side", "up")]
    path = RAW_DIR / "backpack.png"
    sheet(cells).save(path)
    written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the player sheets.")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    for path in build(args):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
