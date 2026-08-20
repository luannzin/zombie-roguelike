#!/usr/bin/env python3
"""Asset pipeline: THE DEAD — three creatures, what they fall like, what they wear.

Output (assets/raw/, then `process_sprites.py --exact` turns each into
assets/processed/<name>/):

    zombie.png / -death.png          the WALKER. What most of a night is.
    zombie-husk.png / -death.png     starved to the frame. Thin and fast-looking.
    zombie-brute.png / -death.png    the one with no neck.
    zhat-cap / -beanie / -hardhat    head overlays, plus a -death each
    zcloth-vest / -jacket / -tie     torso overlays, plus a -death each

    Walk sheets are 3 frames; death sheets are a 5-frame one-shot whose last
    column is the prone rest the corpse holds for the rest of the night.

IT IS THE PLAYER'S ANATOMY, ROTTED, AND THAT IS THE POINT.
`make_player.py` owns the construction — the box, the outline, the plane
values, the head over the shoulders, the stride — and this module imports it
rather than restating it. A creature drawn on its own grid is a creature from
another game standing next to yours, and the whole reason a zombie in this
world is frightening is that it is built out of the same parts the thing you
are playing is. What differs is the BUILD (three sets of widths), the palette
(rot, not skin) and the posture. Nothing else.

WHAT MAKES A ZOMBIE READ AS ONE AT SIXTEEN PIXELS.
Not the colour — green at the edge of a lantern is grey. Three marks, and all
three are silhouette:

    THE REACH    an arm out PAST the body's outline. A player's arms are at
                 their sides; a walker's are in front of it, and that is the
                 difference you can see before you can see a face.
    THE LEAN     the head sits forward of the shoulders and a row lower than a
                 living one, so the whole figure is pitched at you.
    THE GAIT     the stride is wider and the bob is deeper. It does not walk,
                 it falls forward repeatedly and catches itself.

THE THREE VARIANTS ARE THREE SILHOUETTES, NOT THREE PALETTES (S15). Set them
side by side at eight pixels: the walker is a person, the husk is a narrower
person with a longer neck, the brute is a wide mass with no neck at all. If
you cannot tell which is which with the colour taken away, the variant has
not been drawn — it has been recoloured.

THE DEATH IS ONE TIMELINE AND EVERYTHING RIDES IT.
`HEAD_POSE` and `BODY_POSE` are the collapse, in offsets from the standing
pose, and the creature, its hat and its shirt all read the same two tables.
That is what keeps a cap ON a head through a fall it was authored separately
from — the alternative is three sheets that agree by hand until one of them
is edited.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from make_player import (
    MID,
    RAW_DIR,
    TILE,
    PALETTE as PLAYER_PALETTE,
    _blit,
    _box,
    _get,
    _put,
    rgba_of,
    sheet,
)

# --- palette ----------------------------------------------------------------
# THE DEAD ARE NOT TINTED, so unlike the player sheets these are free to use
# any colour they like — no pixel here has to survive a multiply. What they
# are not free to do is leave the game's own ramps: the outline is the same
# ink the player is drawn with, and every material is three flat steps with
# two ramp steps between them (S7), lit from the top-left like everything
# else standing in this forest (S8).
#
# ROT IS GREEN AND GREY, NOT GREEN. A saturated green creature is a cartoon
# frog at this size and a grey one is a rock; what reads as dead flesh is a
# desaturated green that goes GREY in its shadows, which is also what makes it
# survive the darkness multiply the night lays over everything.

PALETTE: dict[str, str] = dict(PLAYER_PALETTE)
PALETTE.update({
    "R": "#ccd8a8",   # rot, lit
    "r": "#a8b781",   # rot
    "e": "#6d7b52",   # rot, shade
    "N": "#c9c6a8",   # bone / husk skin, lit
    "b": "#9d9a80",   # bone
    "c": "#6e6c58",   # bone, shade
    "G": "#a8ae79",   # brute hide, lit
    "y": "#7f8750",   # brute hide
    "u": "#4c5530",   # brute hide, shade
    "X": "#7a1f1f",   # blood, wet
    "x": "#4a1414",   # blood, dry
    "S": "#6b7480",   # rags, lit
    "z": "#464e58",   # rags
    "T": "#7d3f33",   # the vest's canvas
    "t": "#54291f",   # the vest, shade
    "J": "#3a4a66",   # the jacket's denim
    "i": "#26314a",   # denim, shade
    "Y": "#c8a63c",   # the hard hat
    "q": "#8f7222",   # the hard hat, shade
    "C": "#7a5c86",   # the beanie
    "V": "#8a3a3a",   # the cap
    "L": "#6f7550",   # a dead leg
    "D": "#3b4230",   # a dead leg, in shadow
    "M": "#242a20",   # hair, in shadow
})
RGBA = {key: rgba_of(colour) for key, colour in PALETTE.items()}

INK = "o"
BLOOD, BLOOD_DRY = "X", "x"
HAIR_LOW = "M"


# --- builds -----------------------------------------------------------------
# THREE SETS OF WIDTHS AND ONE OF HEIGHTS, and that is the whole difference
# between the three creatures before a single pixel of colour is chosen.

class Build:
    """One creature's proportions, in the player's own coordinates."""

    def __init__(self, head_half: int, body_half: int, head_top: int,
                 head_bottom: int, body_bottom: int, ramp: tuple[str, str, str],
                 rags: tuple[str, str] | None, reach: int):
        self.head_half = head_half
        self.body_half = body_half
        self.head_top = head_top
        self.head_bottom = head_bottom
        #: The body starts where the head ends: one shared outline row, never
        #: two — see `make_player.BODY_TOP`.
        self.body_top = head_bottom
        self.body_bottom = body_bottom
        self.ramp = ramp
        self.rags = rags
        #: How far the arm reaches past the body, in pixels. It is the mark.
        self.reach = reach


BUILDS: dict[str, Build] = {
    # THE WALKER. The player's own build with its head pushed a row down into
    # its shoulders and its arms out. Deliberately the same size: the first
    # thing a night has to teach is that these are people, and a monster that
    # was never a person is a different game.
    "zombie": Build(5, 4, 2, 8, 12, ("R", "r", "e"), ("S", "z"), 2),
    # THE HUSK. Narrower everywhere and a row taller in the neck, so it reads
    # as the same creature with everything taken out of it. Bone, not rot: it
    # is the one that has been out here longest.
    "zombie-husk": Build(4, 3, 1, 8, 12, ("N", "b", "c"), None, 3),
    # THE BRUTE. Wider than its own head is tall, and NO NECK — the head sits
    # inside the shoulder line rather than on top of it, which is the only way
    # to say MASS with two more pixels of width.
    "zombie-brute": Build(6, 5, 3, 9, 13, ("G", "y", "u"), ("z", "z"), 2),
}


# --- the collapse -----------------------------------------------------------
# FIVE FRAMES, and the last one holds for the rest of the night. Offsets from
# the standing pose, in pixels: `(dx, dy)` for the head and for the body, and
# a flag for the two frames where the creature is no longer standing up at
# all and gets drawn lying down instead.
#
# THE SHAPE OF THE FALL is a buckle, not a topple. A body that rotates about
# its feet is a plank; what a person does when they stop is drop at the knees
# first, pitch forward second, and land in a heap that is wider than they
# were tall. Frames 1 and 2 are the drop and the pitch; 3 and 4 are the heap.

HEAD_POSE = ((0, 0), (1, 2), (2, 5), (3, 7), (4, 8))
BODY_POSE = ((0, 0), (0, 2), (1, 4), (0, 5), (0, 5))
#: The frames drawn lying down rather than standing.
PRONE = (False, False, False, True, True)


def head_anchor(frame: int, build: Build) -> tuple[int, int]:
    """Top-left of the head box on a death frame. Overlays ride this."""
    dx, dy = HEAD_POSE[frame]
    return MID - build.head_half + dx, build.head_top + dy


def body_anchor(frame: int, build: Build) -> tuple[int, int]:
    """Top-left of the torso box on a death frame. Overlays ride this."""
    dx, dy = BODY_POSE[frame]
    return MID - build.body_half + dx, build.body_top + dy


# --- the creature -----------------------------------------------------------


def _head(cell, facing: str, build: Build, top: int, dx: int = 0,
          flat: bool = False) -> None:
    """A dead head. Sockets, a jaw, and hair that is not a haircut any more.

    THE SOCKETS ARE THE FACE. A living head on this grid spends its four
    darkest pixels on two eyes; a dead one spends the same four on two HOLES —
    the same shape, one row deeper, with the socket's shadow under it and no
    glint in either. Nothing else about the face changes, which is exactly why
    it lands: the eye reads the same head and finds the light gone out of it.

    THE HAIR IS A CLUMP, NOT A ROW. The first pass scattered it with a
    hash — every third pixel — which is the per-pixel noise S5 exists to
    forbid: at this size it comes out as static on the forehead rather than as
    matted hair. What reads is one clustered mass over the top-left, which is
    also where the key is.
    """
    lit, mid, shade = build.ramp
    # A HEAD LYING DOWN IS NOT A HEAD STANDING UP, SQUASHED. It is nearly
    # round from this camera and it is the width of a skull, not of a face —
    # drawn at the standing width it came out as a plank with an eye on it.
    half = build.head_half - 2 if flat else build.head_half
    x0 = MID - half + dx
    x1 = x0 + half * 2 - 1
    bottom = top + (2 if flat else build.head_bottom - build.head_top)
    _box(cell, x0, top, x1, bottom, mid)
    if flat:
        # Lying on its side: one socket, and the jaw open against the ground.
        _put(cell, x0 + 2, top + 1, INK)
        _put(cell, x0 + 3, top + 1, INK)
        _put(cell, x0 + 1, bottom - 1, BLOOD_DRY)
        return
    if facing == "up":
        # The back of the head: flat hair to the jaw, and the wound in it. On
        # the one facing with no face to read, the wound is what says this is
        # the dead one and which way round it is standing.
        for y in range(top + 1, bottom):
            for x in range(x0 + 1, x1):
                _put(cell, x, y, "j")
        for x in range(x0 + 2, x1 - 1):
            _put(cell, x, bottom - 1, HAIR_LOW)
        _put(cell, MID - 2 + dx, top + 3, BLOOD_DRY)
        _put(cell, MID - 1 + dx, top + 3, BLOOD)
        _put(cell, MID - 1 + dx, top + 4, BLOOD_DRY)
        return
    # THE HAIR takes the crown and the back of the skull, the way the player's
    # cap does — the face is the three rows under it and no more. Left as a
    # clump over one corner it was a light box with a smudge on it: a head
    # this size needs its dark half to be dark, or the sockets have nothing to
    # be sockets IN.
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 1, "j")
    for x in range(x0 + 1, x0 + build.head_half):
        _put(cell, x, top + 2, "j")
    _put(cell, x0 + 2, top + 1, HAIR_LOW)
    # THE FACE IS PAINTED AFTER THE HAIR, and the order is the bug this
    # replaced: the lit band went down first, the cap went over the top of it,
    # and the head shipped with two values instead of three — a flat mid-green
    # box with black holes in it, which at eight pixels is a rock. The brow
    # takes the light, the jaw takes the shade, and the sockets have something
    # to be dark against.
    for x in range(x0 + build.head_half - 1, x1 - 1):
        _put(cell, x, top + 2, lit)
    for x in range(x0 + 1, x1 - 1):
        _put(cell, x, top + 3, lit if x < x1 - 2 else mid)
    for y in range(top + 3, bottom):
        _put(cell, x1 - 1, y, shade)
    _band = bottom - 1
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, _band, shade)
    eye = top + 4
    if facing == "down":
        for ex in (x0 + 2, x1 - 3):
            _put(cell, ex, eye, INK)
            _put(cell, ex + 1, eye, INK)
            _put(cell, ex, eye + 1, shade)
        # The jaw. Two pixels of dark with blood at one corner — a whole mouth
        # is three pixels wide at this size and reads as a smile.
        _put(cell, MID - 1 + dx, bottom - 1, INK)
        _put(cell, MID + dx, bottom - 1, BLOOD)
        return
    # SIDE: one socket, the hair down the back, and the jaw hanging past the
    # chin — one pixel proud of the silhouette, which is the profile's whole
    # difference from a living one.
    _put(cell, x1 - 3, eye, INK)
    _put(cell, x1 - 2, eye, INK)
    _put(cell, x1 - 3, eye + 1, shade)
    for y in range(top + 2, bottom):
        _put(cell, x0 + 1, y, "j")
    _put(cell, x1 - 1, bottom - 1, BLOOD)
    _put(cell, x1 + 1, bottom - 2, mid)
    _put(cell, x1 + 1, bottom - 1, INK)
    _put(cell, x1 + 2, bottom - 2, INK)


def _body(cell, facing: str, build: Build, top: int, dx: int = 0,
          flat: bool = False) -> None:
    """The torso, and the arms that are the whole tell.

    THE REACH IS DRAWN PAST THE OUTLINE on purpose. Everything else on this
    sheet fits inside the body's own silhouette the way the player's does;
    the arms do not, and that overhang is what a player actually reads at the
    distance where a zombie is still a shape rather than a face.
    """
    lit, mid, shade = build.ramp
    x0 = MID - build.body_half + dx
    x1 = x0 + build.body_half * 2 - 1
    bottom = top + (2 if flat else build.body_bottom - build.body_top)
    _box(cell, x0, top, x1, bottom, mid, round_top=False, round_bottom=False)
    for y in range(top + 1, bottom):
        for x in range(x0 + 1, x1):
            reach = (x - x0) + (y - top)
            if reach <= 3:
                _put(cell, x, y, lit)
            elif reach >= 7:
                _put(cell, x, y, shade)
    if build.rags:
        # WHAT IS LEFT OF A SHIRT, and it is a SHAPE: a band across the chest
        # with a torn hem under it, not a scatter of cloth pixels. Never a
        # whole shirt — the tear is the difference between a creature wearing
        # clothes and a creature that USED to. The husk has none at all.
        rag_lit, rag_mid = build.rags
        # UNDER THE SHOULDERS, never over them: the lit row is the only light
        # on this body and a shirt painted across it costs the torso its third
        # value. What is left of the collar is two pixels at the neck.
        for x in range(x0 + 1, x1):
            _put(cell, x, top + 2, rag_lit)
        # THE TEAR: the hem comes down on ONE side and the chest is through it
        # on the other. A hem that alternated pixel by pixel was the same
        # scatter the hair had, and it read as tweed.
        for x in range(x0 + 1, MID):
            _put(cell, x, top + 3, rag_mid)
        _put(cell, x0 + 1, top + 1, rag_lit)
        _put(cell, x1 - 1, top + 1, rag_mid)
    if flat:
        return
    # THE WOUND. One mark of dry blood, placed off the centreline so it does
    # not read as a fastening.
    _put(cell, x0 + 2, bottom - 1, BLOOD_DRY)
    if facing == "up":
        return
    # THE ARMS. Out in front, and on the side facing that means OUT PAST the
    # silhouette by `reach`. Straight, because a dead arm does not hold a
    # pose — it is carried.
    hands = (x0 - 1, x1 + 1) if facing == "down" else (x1 + 1,)
    for hx in hands:
        _put(cell, hx, top, INK)
        _put(cell, hx, top + 1, mid)
        _put(cell, hx, top + 2, shade)
    if facing == "side":
        for step in range(build.reach):
            _put(cell, x1 + 2 + step, top + 1, mid if step % 2 else lit)
            _put(cell, x1 + 2 + step, top + 2, INK)
        _put(cell, x1 + 1 + build.reach, top, INK)


#: The shamble. Wider than the player's stride and a row deeper in the bob —
#: it is the same three-column contract (`[0, 1, 2, 1]`, column 1 the idle)
#: with the legs stiff: a dead leg swings from the hip, it does not step.
LEGS = (
    (
        "....LL....LL....",
        "....LL....DD....",
        "....DD..........",
    ),
    (
        ".....LL..LL.....",
        ".....LL..LL.....",
        ".....DD..DD.....",
    ),
    (
        "....LL....LL....",
        "....DD....LL....",
        "..........DD....",
    ),
)
LEGS_SIDE = (
    (
        "....DD...LL.....",
        "....DD...LL.....",
        "....DD...DD.....",
    ),
    (
        ".....LLLL.......",
        ".....LLLL.......",
        ".....DDDD.......",
    ),
    (
        "...DD....LL.....",
        "...DD....LL.....",
        "...DD....DD.....",
    ),
)
LEG_TOP = 13
BOB = (1, 0, 1)


def _legs(cell, facing: str, frame: int, build: Build) -> None:
    art = LEGS_SIDE if facing == "side" else LEGS
    _blit(cell, art[frame], LEG_TOP)
    # The brute stands on more leg than it walks with. One column either side
    # of each shin, and the thing gets its weight without a taller frame.
    if build.body_half >= 5:
        for y in range(LEG_TOP, TILE):
            for x in range(TILE):
                if _get(cell, x, y) == "L" and _get(cell, x - 1, y) == ".":
                    _put(cell, x - 1, y, "L")


def _walk_frame(name: str, facing: str, frame: int) -> list[list[str]]:
    build = BUILDS[name]
    cell = [["." for _ in range(TILE)] for _ in range(TILE)]
    bob = BOB[frame]
    # THE LEAN: the head rides a pixel forward of the shoulders on the facings
    # that can show it. It is two pixels of the whole sprite and it is most of
    # what makes the thing look like it is coming at you.
    lean = 0 if facing == "up" else 1
    _body(cell, facing, build, build.body_top + bob)
    _head(cell, facing, build, build.head_top + bob, dx=lean if facing == "side" else 0)
    _legs(cell, facing, frame, build)
    return cell


def _death_frame(name: str, facing: str, frame: int) -> list[list[str]]:
    """One column of the collapse. See `HEAD_POSE` — the overlays ride it too."""
    build = BUILDS[name]
    cell = [["." for _ in range(TILE)] for _ in range(TILE)]
    hx, hy = head_anchor(frame, build)
    bx, by = body_anchor(frame, build)
    flat = PRONE[frame]
    if not flat:
        _body(cell, facing, build, by, dx=BODY_POSE[frame][0])
        _head(cell, facing, build, hy, dx=HEAD_POSE[frame][0])
        if frame == 0:
            _legs(cell, facing, 1, build)
        else:
            # The legs fold under the drop rather than staying planted: a
            # corpse sinking with its shins still upright is a body standing
            # in a hole.
            for x in range(MID - build.body_half + 1, MID + build.body_half - 1):
                _put(cell, x, min(TILE - 1, by + 5), "L")
                _put(cell, x, min(TILE - 1, by + 6), "D")
        return cell
    # THE HEAP. Two masses and a stain: the body lying across the frame with
    # the head at the end it fell toward, both squashed to the two or three
    # rows a thing lying down actually occupies from this camera.
    # THE HEAP: the torso across the frame, the head at the end it fell
    # toward, and the legs trailing behind it. Three masses, because a corpse
    # that is one mass is a stain and the player has to be able to tell at a
    # glance that something used to be walking here.
    _body(cell, facing, build, min(TILE - 3, by + 4), dx=-1, flat=True)
    _head(cell, facing, build, min(TILE - 4, hy + 2), dx=HEAD_POSE[frame][0] + 1,
          flat=True)
    lit, mid, shade = build.ramp
    tail = MID - build.body_half - 1
    for x in range(max(0, tail - 2), tail + 1):
        _put(cell, x, TILE - 2, shade)
        _put(cell, x, TILE - 3, mid)
    _put(cell, max(0, tail - 3), TILE - 2, INK)
    pool = TILE - 1
    for x in range(MID - build.body_half, MID + build.body_half):
        if (x * 5) % 3:
            _put(cell, x, pool, BLOOD_DRY)
    if frame == 4:
        for x in range(MID - 2, MID + 2):
            _put(cell, x, pool, BLOOD)
    return cell


# --- what they wear ---------------------------------------------------------
# OVERLAYS, drawn on the same grid and blitted over the creature by the
# client. They are NOT tinted (that is the player's contract, not this one),
# so each carries its own colour — and each needs a matching `-death` sheet,
# because a hat that stayed where the head used to be is the loudest possible
# bug in a corpse.
#
# THEY ARE AUTHORED AGAINST THE WALKER'S BUILD and worn by all three. A hat
# sized per variant is three hats; a hat that sits a pixel proud of a brute's
# wider skull is a hat.


def _cap(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """A baseball cap: a crown and a PEAK, and the peak is the whole read."""
    for x in range(x0 + 1, x1):
        _put(cell, x, top, INK)
        _put(cell, x, top + 1, "V" if x < MID else "t")
    _put(cell, x0, top + 1, INK)
    _put(cell, x1, top + 1, INK)
    if facing == "up":
        return
    # The peak, forward of the crown. On a profile it sticks out past the
    # face, which is exactly what a cap does and what makes it read at eight
    # pixels as something other than a beanie.
    peak = range(x0 + 1, x1) if facing == "down" else range(MID, x1 + 3)
    for x in peak:
        _put(cell, x, top + 2, "t")
    _put(cell, x1 + 2 if facing != "down" else x1, top + 2, INK)


def _beanie(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """Knitted, pulled down over the ears, with a rolled brim."""
    for x in range(x0 + 1, x1):
        _put(cell, x, top, "C")
        _put(cell, x, top + 1, "C" if (x + top) % 2 else "i")
        _put(cell, x, top + 2, "i")
    _put(cell, x0, top + 1, INK)
    _put(cell, x1, top + 1, INK)
    _put(cell, x0, top + 2, INK)
    _put(cell, x1, top + 2, INK)
    _put(cell, MID - 1, top - 1, "C")


def _hardhat(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """A hard hat: a dome, a BRIM all the way round, and a ridge down it."""
    for x in range(x0 + 1, x1):
        _put(cell, x, top, "Y" if x < MID else "q")
    for x in range(x0 - 1, x1 + 2):
        _put(cell, x, top + 2, "q")
    _put(cell, x0 - 1, top + 2, INK)
    _put(cell, x1 + 1, top + 2, INK)
    for x in range(x0, x1 + 1):
        _put(cell, x, top + 1, "Y" if x < MID else "q")
    _put(cell, x0, top + 1, INK)
    _put(cell, x1, top + 1, INK)
    _put(cell, MID - 1, top, INK)


HATS = {"zhat-cap": _cap, "zhat-beanie": _beanie, "zhat-hardhat": _hardhat}


def _vest(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """A hi-vis vest, filthy. Two panels and the band across them."""
    for y in range(top + 1, top + 4):
        for x in (x0 + 1, x1 - 1):
            _put(cell, x, y, "T" if y < top + 3 else "t")
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 2, "T" if x % 2 else "t")


def _jacket(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """Denim, open down the front, collar up."""
    for y in range(top + 1, top + 4):
        for x in range(x0, x1 + 1):
            if x in (x0, x1):
                _put(cell, x, y, INK)
            elif abs(x - MID) >= 2:
                _put(cell, x, y, "J" if y < top + 3 else "i")
    for x in range(x0 + 1, x1):
        if abs(x - MID) >= 1:
            _put(cell, x, top, "i")


def _tie(cell, facing: str, x0: int, x1: int, top: int) -> None:
    """A shirt and a tie. The joke is that he came from somewhere with a dress code."""
    for y in range(top + 1, top + 4):
        for x in range(x0 + 1, x1):
            _put(cell, x, y, "W" if y == top + 1 else "w")
    if facing == "up":
        return
    for y in range(top + 1, top + 4):
        _put(cell, MID - 1, y, "V" if y < top + 3 else "t")


CLOTHES = {"zcloth-vest": _vest, "zcloth-jacket": _jacket, "zcloth-tie": _tie}


def _overlay_frame(name: str, facing: str, frame: int, dying: bool) -> list[list[str]]:
    """One cell of a hat or a shirt, pinned to wherever the body has got to."""
    build = BUILDS["zombie"]
    cell = [["." for _ in range(TILE)] for _ in range(TILE)]
    hat = HATS.get(name)
    if dying:
        if hat:
            hx, hy = head_anchor(frame, build)
            if PRONE[frame]:
                # OFF THE HEAD. A hat stays on for the drop and comes off in
                # the landing — it ends up beside the body, which is a better
                # story than a corpse still neatly wearing one, and it costs
                # the same pixels.
                hat(cell, "up", hx - 3, hx + build.head_half * 2 - 4, TILE - 3)
                return cell
            hat(cell, facing, hx, hx + build.head_half * 2 - 1, hy + 1)
            return cell
        bx, by = body_anchor(frame, build)
        if PRONE[frame]:
            by = min(TILE - 4, by + 4)
        CLOTHES[name](cell, facing, bx - 1, bx + build.body_half * 2, by)
        return cell
    bob = BOB[frame]
    if hat:
        hat(cell, facing, MID - build.head_half, MID + build.head_half - 1,
            build.head_top + bob + 1)
        return cell
    CLOTHES[name](cell, facing, MID - build.body_half - 1, MID + build.body_half,
                  build.body_top + bob)
    return cell


# --- build ------------------------------------------------------------------


def build(args) -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def write(name: str, cells) -> None:
        path = RAW_DIR / f"{name}.png"
        sheet(cells, RGBA).save(path)
        written.append(path)

    facings = ("down", "side", "up")
    for name in BUILDS:
        write(name, [[_walk_frame(name, f, i) for i in range(3)] for f in facings])
        write(f"{name}-death",
              [[_death_frame(name, f, i) for i in range(5)] for f in facings])
    for name in list(HATS) + list(CLOTHES):
        write(name, [[_overlay_frame(name, f, i, False) for i in range(3)]
                     for f in facings])
        write(f"{name}-death", [[_overlay_frame(name, f, i, True) for i in range(5)]
                                for f in facings])
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the zombie sheets.")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    for path in build(args):
        print(f"wrote {path.relative_to(RAW_DIR.parents[1])}")


if __name__ == "__main__":
    main()
