#!/usr/bin/env python3
"""Asset pipeline: THE DEAD — three creatures, what they fall like, what they wear.

Output (assets/raw/, then `process_sprites.py --exact` turns each into
assets/processed/<name>/):

    zombie.png / -death.png          the WALKER. What most of a night is.
    zombie-husk.png / -death.png     the picked-clean one: a skeleton.
    zombie-brute.png / -death.png    the overgrown one. No neck, and growing.
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
are playing is.

WHAT THE REDRAW CHANGED, AND WHY
================================
The first cut of this sheet obeyed the anatomy and lost the creature. Three
green-grey boxes with a dark stripe across the top: same head width, same
symmetry, same value structure, and the only difference between the walker,
the husk and the brute was which four hex values the box was filled with.
Every rule below is a specific answer to that.

  * **A FACE IS A LIGHT, NOT A HOLE.** The sockets were ink on rot, which is
    two dark values at eight pixels and therefore one. They now carry an EYE:
    one saturated pixel inside the socket, the single accent this sprite is
    allowed (S12: one accent hue, <=8% of pixels). It is the thing the player
    actually tracks across a dark clearing, and it is why a creature at the
    edge of the lantern is a creature rather than a bush.
  * **THE THREE ARE THREE SILHOUETTES** (S15), and now they are three
    ANATOMIES. The walker is a person with its head sunk and its arms out.
    The husk is a SKELETON — skull, a gap of neck, a ribcage you can see
    between — so its top contour is nothing like a person's. The brute is a
    mass with growths coming out of its shoulders, wider than its own head is
    tall. Take the colour away and the three are still three things.
  * **NOTHING IS SYMMETRICAL ANY MORE.** S15 bans bilateral symmetry on
    organic assets and the old sheet was symmetrical everywhere: same shoulder
    height, same arm, same jaw. Every creature here now leads with one side —
    a dropped shoulder, a bitten skull, a longer arm — because a body that is
    the same on both sides reads as a machine.
  * **THE RAMPS ARE DERIVED** (S11) rather than typed. Four numbers per
    material through `make_textures.material_ramp`, the same law the guns, the
    loot and the ground are shaded by. Fifteen hand-typed hex values were
    fifteen chances to break the hue-shift rule silently, and the old bone and
    the old rot were two greens with nothing between them.

WHAT MAKES A ZOMBIE READ AS ONE AT SIXTEEN PIXELS.
Not the colour — green at the edge of a lantern is grey. Four marks, and all
four are silhouette or light:

    THE REACH    an arm out PAST the body's outline. A player's arms are at
                 their sides; a walker's are in front of it, and that is the
                 difference you can see before you can see a face.
    THE LEAN     the head sits forward of the shoulders and a row lower than a
                 living one, so the whole figure is pitched at you.
    THE GAIT     the stride is wider and the bob is deeper. It does not walk,
                 it falls forward repeatedly and catches itself.
    THE EYE      one lit pixel in a dark socket. The only saturated thing on
                 the creature, and the last thing to disappear as it walks out
                 of the light.

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
from make_textures import material_ramp

# --- palette ----------------------------------------------------------------
# THE DEAD ARE NOT TINTED, so unlike the player sheets these are free to use
# any colour they like — no pixel here has to survive a multiply. What they
# are not free to do is leave the world's own shading law: every material is
# S11's five-step ramp, DERIVED from four numbers, and the three the art
# actually spends are steps 1, 2 and 3 — S16 gives a 16px sprite three steps,
# and the outline is the player's own ink so a corpse and the thing that shot
# it are drawn with the same pen.
#
# ROT IS GREEN AND GREY, NOT GREEN. A saturated green creature is a cartoon
# frog at this size and a grey one is a rock; what reads as dead flesh is a
# low-saturation green whose shadows go cool, which is also what survives the
# darkness multiply the night lays over everything.

#: Dead flesh. The walker, and the one everything else is measured against.
ROT = material_ramp(104, 0.20, 0.20, 0.66)
#: Bone. Warmer and much lighter at the top than rot, because the husk has to
#: read as a different MATERIAL across a clearing and not as a paler zombie.
BONE = material_ramp(46, 0.14, 0.22, 0.80)
#: The brute's hide: darker, greener, more saturated. Mass reads dark.
HIDE = material_ramp(88, 0.30, 0.14, 0.52)
#: What is left of clothing. Cool and desaturated so it never competes with
#: the eye — a rag is the quietest thing on the creature.
RAG = material_ramp(216, 0.10, 0.18, 0.52)
#: Blood, shared in spirit with the ground's own stain: dark, and only the
#: wet step is allowed anywhere near saturated.
GORE = material_ramp(2, 0.52, 0.12, 0.44)
#: THE EYE, and the only accent on the sheet (S12). It is deliberately hotter
#: and lighter than anything else here: it has to be the first thing found in
#: the dark and the last thing lost, and at one or two pixels per creature it
#: is nowhere near the 8% ceiling.
EYE = material_ramp(16, 0.78, 0.26, 0.70)
#: Fungal growth on the brute — the one hue on the sheet that is not rot,
#: bone or blood, so the thing coming out of its shoulders reads as something
#: that GREW there rather than as more brute.
FUNGUS = material_ramp(58, 0.34, 0.20, 0.62)
#: THE BLOATER'S SKIN, and it has to say "swollen" at sixteen pixels with no
#: room for a bulge. What does that is HUE: rot is a cool desaturated green,
#: and this is pushed toward sick yellow and up in saturation, which is the
#: colour of something distended and about to give. A recolour would not be
#: enough on its own — the silhouette carries the shape (see `Build`) — but
#: the two together are what stop it reading as a fat walker.
BILE = material_ramp(74, 0.40, 0.22, 0.62)


def _hex(colour) -> str:
    red, green, blue, _ = colour
    return f"#{red:02x}{green:02x}{blue:02x}"


#: Letter -> colour, and the letters are what the art below is written in.
#: Three steps per material and no more (S16), taken off the derived ramps
#: rather than typed: `3` is the key-lit plane, `2` the base, `1` the core
#: shadow. Two steps apart is a plane change, one step is a nuance (S7), which
#: is why nothing here uses adjacent steps for adjacent planes.
PALETTE: dict[str, str] = dict(PLAYER_PALETTE)
PALETTE.update({
    "R": _hex(ROT[3]),      # rot, lit
    "r": _hex(ROT[2]),      # rot
    "e": _hex(ROT[1]),      # rot, shade
    "N": _hex(BONE[3]),     # bone, lit
    "b": _hex(BONE[2]),     # bone
    "c": _hex(BONE[1]),     # bone, shade
    "G": _hex(HIDE[3]),     # brute hide, lit
    "y": _hex(HIDE[2]),     # brute hide
    "u": _hex(HIDE[1]),     # brute hide, shade
    "P": _hex(BILE[3]),     # bloater skin, lit
    "p": _hex(BILE[2]),     # bloater skin
    "k": _hex(BILE[1]),     # bloater skin, shade
    "F": _hex(FUNGUS[3]),   # growth, lit
    "f": _hex(FUNGUS[1]),   # growth, shade
    "X": _hex(GORE[3]),     # blood, wet
    "x": _hex(GORE[1]),     # blood, dry
    "S": _hex(RAG[3]),      # rags, lit
    "z": _hex(RAG[1]),      # rags
    "E": _hex(EYE[4]),      # THE EYE
    "d": _hex(EYE[1]),      # the socket it burns in
    "T": "#7d3f33",         # the vest's canvas
    "t": "#54291f",         # the vest, shade
    "J": "#3a4a66",         # the jacket's denim
    "i": "#26314a",         # denim, shade
    "Y": "#c8a63c",         # the hard hat
    "q": "#8f7222",         # the hard hat, shade
    "C": "#7a5c86",         # the beanie
    "V": "#8a3a3a",         # the cap
    "L": _hex(ROT[2]),      # a leg — remapped per creature, see `_legs`
    "D": _hex(ROT[1]),      # a leg, in shadow
    "M": "#242a20",         # hair, in shadow
})
RGBA = {key: rgba_of(colour) for key, colour in PALETTE.items()}

INK = "o"
BLOOD, BLOOD_DRY = "X", "x"
HAIR_LOW = "M"
EYE_LIT, SOCKET = "E", "d"


# --- builds -----------------------------------------------------------------
# THREE SETS OF WIDTHS, THREE ANATOMIES, and the pair is the whole difference
# between the creatures before a single pixel of colour is chosen. `kind` is
# what the painters branch on; everything else is proportion.

class Build:
    """One creature's proportions, in the player's own coordinates."""

    def __init__(self, kind: str, head_half: int, body_half: int, head_top: int,
                 head_bottom: int, body_bottom: int, ramp: tuple[str, str, str],
                 rags: tuple[str, str] | None, reach: int):
        #: `walker` / `husk` / `brute`. Which anatomy the painters draw.
        self.kind = kind
        self.head_half = head_half
        self.body_half = body_half
        self.head_top = head_top
        self.head_bottom = head_bottom
        #: The body starts where the head ends: one shared outline row, never
        #: two — see `make_player.BODY_TOP`. The husk breaks this on purpose
        #: (see its `neck`), because a gap is the whole point of a skeleton.
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
    "zombie": Build("walker", 4, 4, 2, 8, 12, ("R", "r", "e"), ("S", "z"), 2),
    # THE HUSK. A SKELETON, and it is the one variant that stopped being a
    # recolour: a skull, a pixel of neck under it with light through the gap,
    # and a ribcage you can count. Narrow, so the top contour is a small round
    # skull over a body half the walker's width — nothing else on the sheet
    # has that outline.
    "zombie-husk": Build("husk", 4, 3, 1, 7, 12, ("N", "b", "c"), None, 3),
    # THE BRUTE. Wider than its own head is tall, NO NECK — the head sits
    # inside the shoulder line rather than on top of it — and something is
    # GROWING out of it. The growths are what make its outline unmistakable
    # at the size where the brute is still a blob.
    "zombie-brute": Build("brute", 4, 6, 3, 9, 13, ("G", "y", "u"), None, 2),
    # THE BLOATER. A PEAR, and it is the only one on the sheet.
    #
    # Every other build here is widest at the shoulders — a walker is straight,
    # a husk is narrow, a brute is a wedge. This one is widest at the BELLY and
    # has a small head sunk into almost nothing, so its top contour is the
    # opposite shape to all three: narrow where they are wide, and bulging
    # where they taper. That inversion is what makes it identifiable as a black
    # shape at the edge of a lantern, which is the only distance that matters
    # for a creature you are supposed to react to before it fires.
    #
    # SHORT ARMS (`reach=1`). The overhang is the walker's tell and this thing
    # does not want it: a bloater that read as reaching would look like a
    # melee creature, and the entire encounter is about it NOT needing to
    # reach you.
    # SQUAT AND NEARLY THE FULL WIDTH OF THE CELL, with a head barely bigger
    # than a fist. The first cut kept the brute's proportions and only pulled
    # the shoulders in, and the silhouette test correctly called it a recolour:
    # both were simply "wide". What separates them now is HEIGHT — the brute is
    # tall and wide, this is short and wide — and a head half the size.
    "zombie-bloater": Build("bloater", 2, 7, 5, 9, 15, ("P", "p", "k"), None, 1),
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


# --- shared marks -------------------------------------------------------------


def _socket(cell, x: int, y: int, lit: bool) -> None:
    """One eye: a hole with something still burning in it.

    TWO PIXELS WIDE AND TWO DEEP, which is the smallest a hole can be and
    still be a hole rather than a dot. The rim under it is the eye's own dim
    step rather than the creature's shade, so the socket reads as a cavity
    with a light inside it instead of a bruise.

    `lit` is the asymmetry: on every creature here ONE eye carries the accent
    pixel and the other is dark. Two lit eyes is a face looking at you and
    reads as a character; one is a thing whose head is turned slightly away,
    which is what these are.
    """
    _put(cell, x, y, INK)
    _put(cell, x + 1, y, INK)
    _put(cell, x, y + 1, SOCKET)
    _put(cell, x + 1, y + 1, INK)
    if lit:
        _put(cell, x, y, EYE_LIT)


def _bite(cell, x: int, y: int) -> None:
    """Take a pixel out of the silhouette (S15: notch the outline).

    Organic outlines are broken (S6) and organic silhouettes are notched, and
    the cheapest place to spend that on a sixteen-pixel creature is the edge
    of the skull. Clearing the pixel rather than darkening it is deliberate:
    what makes a bite read is the BACKGROUND coming through.
    """
    _put(cell, x, y, ".")


# --- the creature -----------------------------------------------------------


def _head(cell, facing: str, build: Build, top: int, dx: int = 0,
          flat: bool = False) -> None:
    """A dead head, in whichever of the three anatomies this creature has."""
    lit, mid, shade = build.ramp
    if flat:
        _head_flat(cell, build, top, dx)
        return
    if build.kind == "husk":
        _skull(cell, facing, build, top, dx)
        return
    if build.kind == "brute":
        _brute_head(cell, facing, build, top, dx)
        return
    if build.kind == "bloater":
        _bloater_head(cell, facing, build, top, dx)
        return
    _walker_head(cell, facing, build, top, dx, lit, mid, shade)


def _head_flat(cell, build: Build, top: int, dx: int) -> None:
    """A head lying down. Not a head standing up, squashed.

    It is nearly round from this camera and it is the width of a SKULL, not of
    a face — drawn at the standing width it came out as a plank with an eye on
    it. One socket, still burning, and the jaw open against the ground.
    """
    lit, mid, shade = build.ramp
    half = build.head_half - 2
    x0 = MID - half + dx
    x1 = x0 + half * 2 - 1
    bottom = top + 2
    _box(cell, x0, top, x1, bottom, mid)
    _put(cell, x0 + 1, top + 1, lit)
    _socket(cell, x0 + 2, top + 1, lit=True)
    _put(cell, x0 + 1, bottom - 1, BLOOD_DRY)


def _walker_head(cell, facing: str, build: Build, top: int, dx: int,
                 lit: str, mid: str, shade: str) -> None:
    """A person's head with the light gone out of it.

    THE SOCKETS ARE THE FACE. A living head on this grid spends its four
    darkest pixels on two eyes; a dead one spends them on two HOLES a row
    deeper, with the brow in shadow over them — and one of those holes has
    something in it.

    THE HAIR IS A CLUMP, NOT A ROW, and it is off-centre. The first pass
    scattered it with a hash (the per-pixel noise S5 exists to forbid); the
    second made it a full symmetrical cap, which is a hat. What reads as
    matted hair is one mass weighted to the side the key is on, with the
    scalp showing through on the other.
    """
    x0 = MID - build.head_half + dx
    x1 = x0 + build.head_half * 2 - 1
    bottom = top + build.head_bottom - build.head_top
    _box(cell, x0, top, x1, bottom, mid)
    # FIVE INTERIOR ROWS AND EACH ONE HAS A JOB: hair, brow, sockets, cheek,
    # jaw. The first two cuts of this head gave three of those rows to hair
    # and shadow, which is why it came out as a dark slab with two dots at the
    # bottom — a face needs its light in the MIDDLE, where the eyes are.
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 1, "j")
    # The hair is a CLUMP on the key side and stops: the scalp shows through
    # on the other, which is both the asymmetry (S15) and the reason the brow
    # under it has anything to be lit against.
    for x in range(x0 + 1, x0 + 4):
        _put(cell, x, top + 2, "j")
    _put(cell, x0 + 2, top + 1, HAIR_LOW)
    for x in range(x0 + 4, x1):
        _put(cell, x, top + 2, lit if x < x1 - 1 else mid)
    # The hair keeps going down the far side of the skull for one more pixel,
    # so the TOP CONTOUR is not the same shape twice (S15: the upper profile
    # carries the identity, and a symmetrical cap has no identity).
    _put(cell, x0 + 1, top + 3, "j")
    # The temple, in shade: it is what rounds the side of the head off. A
    # sixteen-pixel head with two flat sides is a die.
    for y in range(top + 2, bottom - 1):
        _put(cell, x1 - 1, y, shade)
    # The cheek row under the sockets keeps the light on the near side and
    # loses it round the jaw — two steps between the two planes (S7).
    for x in range(x0 + 1, x1 - 1):
        _put(cell, x, bottom - 2, lit if x < MID + dx else mid)
    _put(cell, x1 - 1, bottom - 2, shade)
    for x in range(x0 + 1, x1):
        _put(cell, x, bottom - 1, shade)
    if facing == "up":
        # The back of the head: hair to the jaw and the wound in it. On the
        # one facing with no face to read, the wound is what says this is the
        # dead one and which way round it is standing.
        for y in range(top + 1, bottom):
            for x in range(x0 + 1, x1):
                _put(cell, x, y, "j")
        for x in range(x0 + 2, x1 - 1):
            _put(cell, x, bottom - 1, HAIR_LOW)
        _put(cell, MID - 2 + dx, top + 3, BLOOD_DRY)
        _put(cell, MID - 1 + dx, top + 3, BLOOD)
        _put(cell, MID - 1 + dx, top + 4, BLOOD_DRY)
        return
    eye = top + 3
    if facing == "down":
        # TWO SOCKETS WITH THE FACE BETWEEN THEM. Set at the edges with two
        # pixels of cheek down the middle: sockets any closer together are a
        # pair of nostrils, and any wider have no head left to sit in.
        _socket(cell, x0 + 1, eye, lit=True)
        _socket(cell, x1 - 2, eye, lit=False)
        # The bridge between them, one step down. Without it the two sockets
        # are a pair of holes in a flat plane; with it they are set into a
        # face that has a middle.
        _put(cell, MID + dx - 1, eye + 1, shade)
        # The jaw: two pixels of dark with blood at one corner. A whole mouth
        # is three pixels wide at this size and reads as a smile.
        _put(cell, MID - 1 + dx, bottom - 1, INK)
        _put(cell, MID + dx, bottom - 1, BLOOD)
        # A BITE out of the crown, on the side away from the key: the skull is
        # not intact and the outline should say so before the face does.
        _bite(cell, x1 - 1, top)
        return
    # SIDE: one socket, the hair down the back, and the jaw hanging past the
    # chin — a pixel proud of the silhouette, which is the profile's whole
    # difference from a living one.
    _socket(cell, x1 - 3, eye, lit=True)
    for y in range(top + 2, bottom):
        _put(cell, x0 + 1, y, "j")
    _put(cell, x1 - 1, bottom - 1, BLOOD)
    _put(cell, x1 + 1, bottom - 2, mid)
    _put(cell, x1 + 1, bottom - 1, INK)
    _put(cell, x1 + 2, bottom - 2, INK)
    _bite(cell, x0, top)


def _skull(cell, facing: str, build: Build, top: int, dx: int) -> None:
    """The husk's head, and it is a SKULL — the variant's whole identity.

    A small round cranium, a brow that overhangs, sockets that take up a third
    of the face, and TEETH. None of that is a zombie with the colour changed:
    the top contour is narrower than the walker's and the bottom of the head
    is a jaw line rather than a chin, so the two are told apart in silhouette
    at the distance where neither has a face yet (S15).

    The teeth are the cheapest four pixels on this sheet. Two ink notches in a
    lit jaw is a grin; anything more careful is a mouth, and a mouth on a
    skull at eight pixels is a smudge.
    """
    lit, mid, shade = build.ramp
    x0 = MID - build.head_half + dx
    x1 = x0 + build.head_half * 2 - 1
    bottom = top + build.head_bottom - build.head_top
    _box(cell, x0, top, x1, bottom, mid)
    # THE CRANIUM is the brightest thing on the sheet — bone is the one
    # material here allowed near the top of its ramp — and it is a DOME: the
    # light row is inset a pixel at each end so the top of the skull is round
    # rather than a lid.
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, top + 1, lit)
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 2, lit if x < x1 - 2 else mid)
    if facing == "up":
        # The back of a skull is a dome and a suture, and the hole somebody
        # put in it is the only mark that says which one this is.
        for x in range(x0 + 1, x1):
            for y in range(top + 3, bottom):
                _put(cell, x, y, mid)
        _put(cell, MID + dx - 1, top + 2, shade)
        _put(cell, MID + dx - 1, top + 3, BLOOD_DRY)
        _put(cell, MID + dx, top + 3, BLOOD)
        return
    eye = top + 3
    if facing == "down":
        # SOCKETS ARE A THIRD OF THIS FACE and there is a NOSE between them.
        # A skull's whole read at eight pixels is two holes and a gap, and the
        # gap has to be as dark as the holes or the face is a visor.
        _socket(cell, x0 + 1, eye, lit=True)
        _socket(cell, x1 - 2, eye, lit=False)
        _put(cell, MID + dx - 1, eye + 1, INK)
        # THE TEETH: a lit jaw with two gaps bitten out of it.
        for x in range(x0 + 1, x1):
            _put(cell, x, bottom - 1, lit)
        _put(cell, x0 + 2, bottom - 1, INK)
        _put(cell, x1 - 2, bottom - 1, INK)
        _bite(cell, x1 - 1, top)
        return
    # In profile the skull shows one socket, the cheekbone under it and the
    # jaw hinging back — the hinge is what stops a profile skull reading as a
    # ball with a dot on it.
    _socket(cell, x1 - 3, eye, lit=True)
    for x in range(x0 + 1, x1 - 3):
        _put(cell, x, eye, mid)
    for x in range(x0 + 1, x1):
        _put(cell, x, bottom - 1, lit)
    _put(cell, x1 - 2, bottom - 1, INK)
    _put(cell, x0 + 1, bottom - 1, shade)
    _bite(cell, x0, top)


def _bloater_head(cell, facing: str, build: Build, top: int, dx: int) -> None:
    """A small head on a swollen neck, with the jaw already open.

    THE HEAD IS THE SMALLEST ON THE SHEET and that is the whole read. Every
    other creature here is identified by what is on top of it — hair, a skull,
    growths — and this one is identified by there being almost nothing there
    over a body that is enormous. Narrow-over-wide is the inverted silhouette
    (see the `Build`), and the head is the half of it that has to be small.

    THE JAW IS OPEN, ALWAYS. It is the only face on the sheet drawn mid-action,
    because this creature's whole verb comes out of its mouth — a bloater with
    a closed jaw is a fat zombie, and the player has to be able to tell before
    it fires rather than after.

    ONE SOCKET, not two. The other side of the face is swollen shut, which is
    the asymmetry (S15) and is also cheaper than it sounds: the lit accent is
    what a player finds in the dark, and one of them on a body this wide reads
    as a bigger creature than two would.
    """
    lit, mid, shade = build.ramp
    x0 = MID - build.head_half + dx
    x1 = x0 + build.head_half * 2 - 1
    bottom = top + build.head_bottom - build.head_top
    _box(cell, x0, top, x1, bottom, mid)
    # The crown takes the light; the far side goes to shade, so a head this
    # small still has a direction to it.
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 1, lit if x < x1 - 1 else shade)
    if facing == "up":
        # From behind there is no face and no jaw — just the swollen mass.
        for y in range(top + 2, bottom):
            _put(cell, x1 - 1, y, shade)
        return
    # THE SOCKET, on the key side. The other eye is swollen shut and is drawn
    # as skin rather than as a second hole.
    _put(cell, x0 + 1, top + 2, SOCKET)
    _put(cell, x0 + 1, top + 2, EYE_LIT if facing != "up" else SOCKET)
    _put(cell, x1 - 1, top + 2, shade)
    # THE OPEN JAW. Two rows of ink under the face with a lip of skin either
    # side, so it reads as a mouth held open rather than as a shadow.
    for x in range(x0 + 1, x1):
        _put(cell, x, bottom, INK)
    _put(cell, x0, bottom, mid)
    _put(cell, x1, bottom, shade)


def _brute_head(cell, facing: str, build: Build, top: int, dx: int) -> None:
    """The brute's head, which is barely a head: a mass with eyes in it.

    NO NECK AND NO FOREHEAD. The skull sits inside the shoulder line and the
    face is pushed to the bottom of it, so the top two thirds of the mass are
    just mass — which is what says WEIGHT at a size too small for muscle.

    THE GROWTHS ARE THE SILHOUETTE. Two lumps of fungus off the crown, one
    bigger than the other (S17's `1 : 0.7` rhythm), breaking the outline on
    both sides at different heights. They are the reason this creature is
    identifiable as a black shape, and they are a second HUE — something grew
    on it, it is not simply a fatter zombie.
    """
    lit, mid, shade = build.ramp
    x0 = MID - build.head_half + dx
    x1 = x0 + build.head_half * 2 - 1
    bottom = top + build.head_bottom - build.head_top
    _box(cell, x0, top, x1, bottom, mid)
    for x in range(x0 + 1, x1 - 1):
        _put(cell, x, top + 1, lit if x < x1 - 3 else mid)
    for y in range(top + 1, bottom):
        _put(cell, x1 - 1, y, shade)
    # THE GROWTHS. Crown-left is the big one and it takes the light; the
    # smaller one sits a row lower on the right, where it breaks the outline
    # against the shade side.
    _put(cell, x0 + 1, top - 1, "F")
    _put(cell, x0 + 2, top - 1, "F")
    _put(cell, x0 + 2, top - 2, "F")
    _put(cell, x0 + 1, top, "f")
    _put(cell, x1 - 1, top - 1, "f")
    _put(cell, x1, top, "F")
    if facing == "up":
        for x in range(x0 + 1, x1):
            for y in range(top + 1, bottom):
                _put(cell, x, y, shade if y > top + 2 else mid)
        _put(cell, MID + dx - 1, top + 3, BLOOD_DRY)
        _put(cell, MID + dx, top + 3, BLOOD)
        return
    eye = top + 2
    if facing == "down":
        # BOTH EYES BURN on this one — the brute is the thing that has already
        # seen you — and they are set wide with the mass hanging over them.
        _socket(cell, x0 + 1, eye, lit=True)
        _socket(cell, x1 - 2, eye, lit=True)
        # THE MAW: a wide dark mouth across the bottom of the mass, wet at one
        # corner. A brute with a jaw like a person's is a fat zombie.
        for x in range(x0 + 1, x1 - 1):
            _put(cell, x, bottom - 1, INK)
        _put(cell, x0 + 2, bottom - 1, BLOOD)
        _put(cell, x1 - 2, bottom - 1, BLOOD_DRY)
        return
    _socket(cell, x1 - 3, eye, lit=True)
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, bottom - 1, INK)
    _put(cell, x1 - 2, bottom - 1, BLOOD)
    _put(cell, x1 + 1, bottom - 2, mid)
    _put(cell, x1 + 1, bottom - 1, INK)


def _belly(cell, build: Build, x0: int, x1: int, top: int, bottom: int) -> None:
    """A torso that gets WIDER on the way down. The whole silhouette.

    THIS IS THE ONLY SHAPE ON THE SHEET THAT TAPERS UPWARD. A walker is a
    rectangle, a husk is a narrow cage, a brute is a wedge with the mass at
    the shoulders — all three are widest at the top. Drawing this one as a
    fatter rectangle would have made it a fat walker, which is the failure the
    variants test exists to catch (a variant that is a recolour of another).
    So the shoulders are pulled IN by two pixels and the belly is left at full
    width, and the outline does the work.

    THE SEAMS ARE HORIZONTAL. A distended thing is under pressure, and what
    reads as pressure at this size is banding across the widest part — the same
    trick a barrel's hoops play in `make_objects`. Two bands, unevenly spaced,
    because two evenly spaced ones are a pattern and a pattern reads as cloth.
    """
    lit, mid, shade = build.ramp
    # THE SHOULDERS, pulled in HARD. Three pixels narrower than the belly on
    # each side — the first cut used two and the silhouette test called the
    # result a recolour of the brute, because a barely-tapered wide body is
    # just a wide body. The taper has to be visible in the outline at one
    # pixel per pixel or it is not a shape, it is a shading choice.
    for y in range(top, top + 2):
        for x in range(x0 + 3, x1 - 2):
            _put(cell, x, y, mid)
        _put(cell, x0 + 3, y, INK)
        _put(cell, x1 - 3, y, INK)
    # THE BELLY, at full width from the third row down.
    _box(cell, x0, top + 2, x1, bottom, mid, round_top=False, round_bottom=False)
    for y in range(top + 3, bottom):
        for x in range(x0 + 1, x1):
            # Light from the same key corner every other body here uses, so a
            # clearing of mixed creatures is lit by one sun.
            reach = (x - x0) + (y - top)
            if reach <= 4:
                _put(cell, x, y, lit)
            elif reach >= 9:
                _put(cell, x, y, shade)
    # THE SEAMS. Unevenly spaced — see the docstring.
    for x in range(x0 + 1, x1):
        _put(cell, x, top + 4, shade)
    for x in range(x0 + 2, x1 - 1):
        _put(cell, x, bottom - 2, shade)
    # And one split already open, low and off-centre, with bile in it. It is
    # the two-pixel promise that this thing is going to come apart.
    _put(cell, x0 + 2, bottom - 1, "F")
    _put(cell, x0 + 3, bottom - 1, "f")


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
    if build.kind == "husk" and not flat:
        _ribcage(cell, facing, build, x0, x1, top, bottom)
    elif build.kind == "bloater" and not flat:
        _belly(cell, build, x0, x1, top, bottom)
    else:
        _box(cell, x0, top, x1, bottom, mid, round_top=False, round_bottom=False)
        for y in range(top + 1, bottom):
            for x in range(x0 + 1, x1):
                reach = (x - x0) + (y - top)
                if reach <= 3:
                    _put(cell, x, y, lit)
                elif reach >= 7:
                    _put(cell, x, y, shade)
        # THE DROPPED SHOULDER (S15: no bilateral symmetry). One corner of the
        # torso is a row lower than the other, which tilts the whole body
        # without moving anything else — and it is the side the head leans to.
        _put(cell, x0, top, ".")
        _put(cell, x0 + 1, top, INK)
    if build.rags and not flat:
        # WHAT IS LEFT OF A SHIRT, and it is a SHAPE: a band across the chest
        # with a torn hem under it, not a scatter of cloth pixels. Never a
        # whole shirt — the tear is the difference between a creature wearing
        # clothes and a creature that USED to.
        rag_lit, rag_mid = build.rags
        # A BAND, NOT A COAT. Rags used to run the full width of the torso on
        # two rows, which is a shirt — and a grey shirt across a green body is
        # the loudest thing on the sprite, louder than the face. What is left
        # of a shirt is a strip over the ribs with the chest showing at both
        # ends of it.
        for x in range(x0 + 2, x1 - 1):
            _put(cell, x, top + 2, rag_lit if x < MID else rag_mid)
        # THE TEAR: the hem comes down on ONE side and the chest is through it
        # on the other. A hem that alternated pixel by pixel was the same
        # scatter the hair had, and it read as tweed.
        for x in range(x0 + 2, MID):
            _put(cell, x, top + 3, rag_mid)
    if flat:
        return
    # THE WOUND. One mark of dry blood, placed off the centreline so it does
    # not read as a fastening.
    _put(cell, x0 + 2, bottom - 1, BLOOD_DRY)
    if build.kind == "brute":
        # A growth on the shoulder as well as the crown, so the mass reads as
        # covered in the stuff rather than wearing a hat of it.
        _put(cell, x1 - 1, top + 1, "F")
        _put(cell, x1 - 2, top + 2, "f")
        # And a BITE out of the other shoulder. The brute is the widest thing
        # in the game and a wide rectangle is a wall — two pixels of missing
        # edge is what turns it back into a body (S15).
        _bite(cell, x0, top)
        _bite(cell, x0 + 1, top)
        _put(cell, x0 + 2, top, INK)
    if facing == "up":
        return
    # THE ARMS. Out in front, and on the side facing that means OUT PAST the
    # silhouette by `reach`. Straight, because a dead arm does not hold a
    # pose — it is carried. The two are NOT the same length: the near one
    # reaches and the far one hangs, which is the asymmetry the old sheet had
    # nowhere at all.
    hands = (x0 - 1, x1 + 1) if facing == "down" else (x1 + 1,)
    for index, hx in enumerate(hands):
        drop = 1 if index == 0 and len(hands) > 1 else 0
        _put(cell, hx, top + drop, INK)
        _put(cell, hx, top + 1 + drop, mid)
        _put(cell, hx, top + 2 + drop, shade)
    if facing == "side":
        for step in range(build.reach):
            _put(cell, x1 + 2 + step, top + 1, mid if step % 2 else lit)
            _put(cell, x1 + 2 + step, top + 2, INK)
        _put(cell, x1 + 1 + build.reach, top, INK)


def _ribcage(cell, facing: str, build: Build, x0: int, x1: int,
             top: int, bottom: int) -> None:
    """The husk's torso: ribs with the night showing between them.

    THE GAPS ARE THE WHOLE THING. A skeleton drawn as a pale torso with lines
    on it is a zombie in a striped shirt; what makes a ribcage read is that
    the BACKGROUND comes through it, which at this size means alternating rows
    of bone and nothing at all. Three ribs, because two is a ladder and four
    is corduroy.

    The spine holds them together down the middle on the facings that show a
    back, and the pelvis is the one solid row at the bottom — a ribcage with
    no base under it floats.
    """
    lit, mid, shade = build.ramp
    for x in range(x0, x1 + 1):
        _put(cell, x, top, INK)
    ribs = (top + 1, top + 3)
    for y in ribs:
        for x in range(x0, x1 + 1):
            _put(cell, x, y, INK if x in (x0, x1) else (lit if y == ribs[0] else mid))
    if facing != "up":
        # The sternum, holding the front ribs together. Down the middle and a
        # step darker, so the ribs read as attached to something.
        for y in range(top + 1, bottom):
            _put(cell, MID, y, shade)
    else:
        for y in range(top + 1, bottom):
            _put(cell, MID - 1, y, shade)
    # THE PELVIS. Solid, one row, and a pixel wider than the ribs on the
    # shaded side so the bottom of the creature is its heaviest shape.
    for x in range(x0, x1 + 1):
        _put(cell, x, bottom, INK if x in (x0, x1) else mid)
    for x in range(x0 + 1, x1):
        _put(cell, x, bottom - 1, shade)


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
    """The stride, in the creature's OWN material.

    THE ART IS EDITED AS LETTERS AND PAINTED LAST, and the order is a bug this
    replaced: remapping `L`/`D` to colours first and then thinning meant the
    thinning could not tell a leg from a pelvis, so the husk's hips — which
    land on the leg row on a bob frame — were eaten a pixel at a time and the
    bones came away from the body.

    The legs used to be two shared colours, one green for all three, which is
    how the husk ended up a bone torso standing on rotten shins.
    """
    art = LEGS_SIDE if facing == "side" else LEGS
    _blit(cell, art[frame], LEG_TOP)
    lit, mid, shade = build.ramp
    bones = ("L", "D")
    if build.kind == "husk":
        # A SKELETON'S LEGS ARE BONES, not shins: one column each, and the
        # column that survives is the INNER one. The husk's pelvis is narrower
        # than the walker's, so a bone left in the outer column lands beside
        # the hip rather than under it, and a leg that does not meet the body
        # reads as a stick lying on the floor.
        for y in range(LEG_TOP, TILE):
            x = 0
            while x < TILE:
                if _get(cell, x, y) not in bones:
                    x += 1
                    continue
                run = x
                while run < TILE and _get(cell, run, y) in bones:
                    run += 1
                # HALF OF EACH RUN, KEPT ON THE INSIDE. A run is one leg (two
                # px) on a contact frame and both legs together (four) on the
                # passing one, so halving is the rule that gives a bone in
                # both cases — thinning pixel by pixel instead left the idle
                # pose standing on a single column, which is a skeleton
                # balancing on a stick.
                keep = max(1, (run - x) // 2)
                for index in range(x, run):
                    inside = index >= run - keep if x < MID else index < x + keep
                    if not inside:
                        _put(cell, index, y, ".")
                x = run
    if build.body_half >= 5:
        # The brute stands on more leg than it walks with. One column either
        # side of each shin, and the thing gets its weight without a taller
        # frame.
        for y in range(LEG_TOP, TILE):
            for x in range(TILE):
                if _get(cell, x, y) == "L" and _get(cell, x - 1, y) == ".":
                    _put(cell, x - 1, y, "L")
    for y in range(LEG_TOP, TILE):
        for x in range(TILE):
            key = _get(cell, x, y)
            if key == "L":
                _put(cell, x, y, lit if build.kind == "husk" else mid)
            elif key == "D":
                _put(cell, x, y, shade)


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
    lit, mid, shade = build.ramp
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
                _put(cell, x, min(TILE - 1, by + 5), mid)
                _put(cell, x, min(TILE - 1, by + 6), shade)
        return cell
    # THE HEAP: the torso across the frame, the head at the end it fell
    # toward, and the legs trailing behind it. Three masses, because a corpse
    # that is one mass is a stain and the player has to be able to tell at a
    # glance that something used to be walking here.
    _body(cell, facing, build, min(TILE - 3, by + 4), dx=-1, flat=True)
    _head(cell, facing, build, min(TILE - 4, hy + 2), dx=HEAD_POSE[frame][0] + 1,
          flat=True)
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
