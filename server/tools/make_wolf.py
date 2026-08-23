#!/usr/bin/env python3
"""Asset pipeline: THE PACK — three zombie wolves, and the one that leads them.

Output (assets/raw/, then `process_sprites --exact` into assets/processed/):

    wolf.png / -death.png            ONE HEAD. What a pack is made of.
    wolf-twin.png / -death.png       TWO HEADS. The same animal, gone further.
    wolf-alpha.png / -death.png      THREE HEADS. The miniboss.
    wolf-alpha-sleep.png             the alpha CURLED UP, breathing. No death.

Like `make_armor.py` this script writes the raw art AND processes it, because
eight pairs of commands in a README is a list nobody keeps in step.

THE HEADS ARE THE WHOLE DESIGN, AND THEY ARE DERIVED
====================================================
`make_zombie.py` earned its three creatures by drawing three anatomies — a
person, a skeleton, a mass. That is the right answer when the three are
unrelated. These three are the SAME animal at three stages of the same
sickness, and drawing them three times would be three chances for them to stop
looking related.

So there is one wolf here, and `Build.heads` is a tuple of OFFSETS. One head
is a wolf. Two is a wolf whose shoulders grew a second neck, splayed so one
skull rides above and behind the other. Three fans them. Every other number on
the build — the torso, the legs, the tail, the gait — is shared, which is why
they read as a family, and the top contour is nothing like each other, which
is S15's test and the one thing a variant has to pass.

COUNT THE LIGHTS AND YOU KNOW WHAT IT IS
========================================
Every creature in this game carries ONE lit pixel in a dark socket (S12), and
that pixel is what a player actually tracks at the edge of the lantern. A wolf
carries one per HEAD. So the miniboss announces itself before any HUD does and
before its silhouette is even resolvable: three embers moving together in the
dark is a thing you have never seen, and it is the only thing in the forest
that looks like that. The HUD's crown is the confirmation, not the warning.

WHY IT IS PAINTED IN THREE PASSES AND NOT DRAWN
===============================================
`make_zombie.py` is hand-placed boxes because a person at 16px is mostly
proportion and there is nowhere to hide an error. A quadruped is a chain of
masses at an angle, drawn three times at two scales, and hand-counting that is
how one facing ends up a pixel out of register with another and nobody can say
which is wrong. So:

    1. MASS      every part paints solid into one mask — torso, neck, heads,
                 legs, tail. Nothing decides a colour.
    2. SHADE     the mask is outlined (any solid pixel touching air becomes
                 the player's own ink) and what survives is lit on top, shaded
                 underneath. The keyline is therefore never missing and never
                 doubled, on any build, at any scale.
    3. DETAIL    sockets, eyes, teeth, ribs and blood go ON TOP of the
                 keyline, because they are the only marks allowed to break it.

The thin parts come out solid ink and that is correct rather than a
concession: a wolf's legs and tail ARE dark sticks at this size, and a leg
with an interior is a leg you cannot tell from the body it hangs off.

THE SLEEP SHEET IS THE MINIBOSS'S TELEGRAPH
===========================================
He is not hunting when you find him — he is asleep in his den, and the whole
encounter is a decision the player gets to make before anything is decided for
them. That only works if "asleep" is READABLE from across a clearing, so it is
a real pose and not a still frame of the walk: a curled mass with the heads
tucked, no legs under it, and three frames of BREATH so it is alive rather
than dead. It loops, unlike every other one-shot in this folder, because it is
a state and not an event.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import process_sprites
from make_player import KEY, RAW_DIR, TILE, rgba_of
from make_zombie import BONE, EYE, GORE, ROT, _hex
from make_textures import material_ramp

# --- palette ----------------------------------------------------------------
# THE WOLVES ARE MADE OF THE ZOMBIES' OWN MATERIALS, and that is the same
# argument `make_sawyer.py` makes about the boss: the three creatures answer
# "what happened to the people who lived here", and anything else in this
# forest has to answer it with the same evidence or it is a monster from
# another game standing in this one. Rot is rot, bone is bone, and the eye is
# the eye — one accent hue in the whole world.
#
# ONE MATERIAL IS NEW, because nothing in this game had fur yet. It is
# deliberately the coldest, least saturated thing on any creature sheet: a
# saturated pelt at sixteen pixels is a costume, and what has to read across a
# dark clearing is the SHAPE. The colour's whole job is to not compete with
# the three embers riding on top of it.

#: Matted fur. Cold, grey-green, barely saturated — see above.
PELT = material_ramp(96, 0.11, 0.17, 0.58)
#: The alpha's coat: darker and heavier, the same hue. Mass reads dark, which
#: is the one thing `make_zombie.py` proved twice (the brute, then the boss).
PELT_ALPHA = material_ramp(96, 0.14, 0.12, 0.46)

PALETTE: dict[str, str] = {
    "o": "#141220",        # the player's own ink. One pen for the whole world.
    "F": _hex(PELT[3]),    # fur, lit
    "f": _hex(PELT[2]),    # fur
    "s": _hex(PELT[1]),    # fur, shade
    "A": _hex(PELT_ALPHA[3]),
    "a": _hex(PELT_ALPHA[2]),
    "m": _hex(PELT_ALPHA[1]),
    "r": _hex(ROT[2]),     # bare flesh: the nose, and the sores on the flank
    "N": _hex(BONE[3]),    # teeth, and the ribs coming through
    "b": _hex(BONE[2]),
    "E": _hex(EYE[4]),     # THE ACCENT. One per head and nothing else.
    "d": _hex(EYE[1]),     # the socket's own dim step — a cavity, not a bruise
    "X": _hex(GORE[3]),    # wet
    "x": _hex(GORE[1]),    # dry
}
RGBA = {key: rgba_of(colour) for key, colour in PALETTE.items()}

INK = "o"
SOLID = "#"


# --- builds ------------------------------------------------------------------
# ONE ANIMAL, THREE NUMBERS OF HEADS. Everything below is in pixels of the
# build's own frame, measured from the top-left, and every part is placed off
# these rather than off a literal — which is what lets the alpha be the same
# wolf at a different scale instead of a second drawing of one.


class Build:
    """One wolf's proportions and how many skulls come off its shoulders."""

    def __init__(
        self,
        key: str,
        width: int,
        height: int,
        ramp: tuple[str, str, str],
        back: int,
        belly: int,
        torso: tuple[int, int],
        head: tuple[int, int],
        head_size: tuple[int, int],
        heads: tuple[tuple[int, int], ...],
        leg_len: int,
        tail: int,
    ):
        self.key = key
        self.width = width
        self.height = height
        #: (lit, mid, shade) — the letters `_shade` paints the interior with.
        self.ramp = ramp
        #: Top and bottom rows of the torso in the SIDE view. The legs hang
        #: off `belly` and the ground is the last row of the frame, so leg
        #: length is what decides how tall the animal stands.
        self.back = back
        self.belly = belly
        #: (x0, x1) of the torso in the side view.
        self.torso = torso
        #: Where the FIRST head's skull box starts, side view.
        self.head = head
        #: (w, h) of a skull box, before the muzzle.
        self.head_size = head_size
        #: Offsets from `head`, one per skull, FAR FIRST. Drawing order is
        #: depth: the last one painted is the one nearest the camera.
        self.heads = heads
        self.leg_len = leg_len
        #: How far the tail reaches back past the torso.
        self.tail = tail

    @property
    def count(self) -> int:
        return len(self.heads)

    @property
    def ground(self) -> int:
        return self.height - 1

    @property
    def mid_x(self) -> int:
        return self.width // 2


BUILDS: dict[str, Build] = {
    # THE WOLF. Low, long and quick — the silhouette is a horizontal mass with
    # a head hung off the front of it, which is nothing like anything else on
    # this map. Every other creature in the game is a vertical.
    "wolf": Build(
        key="wolf",
        width=22,
        height=16,
        ramp=("F", "f", "s"),
        back=7,
        belly=11,
        torso=(3, 14),
        head=(14, 6),
        head_size=(6, 6),
        heads=((0, 0),),
        leg_len=4,
        tail=3,
    ),
    # THE TWIN. The same animal, one stage further gone. The second neck comes
    # off the same shoulders and rides HIGH AND BACK, so the top contour is a
    # skull above a skull — which is the whole read, and it survives being
    # drawn in solid black.
    "wolf-twin": Build(
        key="wolf-twin",
        width=22,
        height=16,
        ramp=("F", "f", "s"),
        back=7,
        belly=11,
        torso=(3, 14),
        head=(14, 6),
        head_size=(6, 6),
        heads=((-3, -4), (0, 0)),
        leg_len=4,
        tail=3,
    ),
    # THE ALPHA. Half again the size, a heavier coat, and three skulls fanned
    # so the thing is as tall as it is deep. It is the only creature in this
    # game with three lit eyes, and that is the tell it wears in the dark.
    "wolf-alpha": Build(
        key="wolf-alpha",
        width=32,
        height=22,
        ramp=("A", "a", "m"),
        back=10,
        belly=16,
        torso=(4, 20),
        head=(20, 10),
        head_size=(8, 7),
        heads=((-9, -8), (-5, -4), (0, 0)),
        leg_len=5,
        tail=4,
    ),
}


# --- the grid ----------------------------------------------------------------
# `make_player.py`'s helpers are hardwired to a 16x16 cell and these frames are
# not, so the primitives are re-stated here rather than parameterised over
# there — the player's grid IS 16 and a flag saying otherwise would be an
# invitation to draw a person at the wrong scale.


def _cell(build: Build) -> list[list[str]]:
    return [["." for _ in range(build.width)] for _ in range(build.height)]


def _put(cell, x: int, y: int, key: str) -> None:
    if 0 <= y < len(cell) and 0 <= x < len(cell[0]):
        cell[y][x] = key


def _get(cell, x: int, y: int) -> str:
    if 0 <= y < len(cell) and 0 <= x < len(cell[0]):
        return cell[y][x]
    return "."


def _span(cell, x0: int, x1: int, y: int, key: str = SOLID) -> None:
    for x in range(x0, x1 + 1):
        _put(cell, x, y, key)


def _rounded(cell, x0: int, y0: int, x1: int, y1: int, inset: int = 1) -> None:
    """A blob: a box whose first and last rows are pulled in.

    Everything on this sheet is one of these. A quadruped is four of them in a
    chain and the chain is what carries the animal — a rectangle would read as
    furniture at any size.
    """
    for y in range(y0, y1 + 1):
        cut = inset if y in (y0, y1) else 0
        _span(cell, x0 + cut, x1 - cut, y)


# --- pass 2: the keyline and the light ---------------------------------------


def _shade(cell, build: Build) -> None:
    """Outline the mask, then light what is left of it.

    OUTLINE FIRST AND FROM THE MASK, never per part. Parts that touch share a
    silhouette and a keyline drawn per part would draw the seam between them —
    which is how a leg ends up looking like it is in front of the body it is
    attached to.

    The interior is lit by COLUMN rather than by row: the topmost surviving
    pixel of each column is the plane facing the sky and the bottom one is the
    plane facing the ground, which on an animal whose whole body is horizontal
    is the only lighting decision there is.
    """
    lit, mid, shade = build.ramp
    solid = {
        (x, y)
        for y in range(build.height)
        for x in range(build.width)
        if cell[y][x] == SOLID
    }
    interior: list[tuple[int, int]] = []
    for x, y in sorted(solid):
        edge = any(
            (x + dx, y + dy) not in solid for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        if edge:
            _put(cell, x, y, INK)
        else:
            interior.append((x, y))

    columns: dict[int, list[int]] = {}
    for x, y in interior:
        columns.setdefault(x, []).append(y)
    for x, ys in columns.items():
        ys.sort()
        for index, y in enumerate(ys):
            if index == 0:
                _put(cell, x, y, lit)
            elif index == len(ys) - 1 and len(ys) > 2:
                _put(cell, x, y, shade)
            else:
                _put(cell, x, y, mid)


# --- pass 1: the masses ------------------------------------------------------


def _torso_side(cell, build: Build, bob: int) -> None:
    x0, x1 = build.torso
    # The chest is deeper than the hips: a wolf's mass is at the front, and a
    # body of even depth reads as a barrel on legs.
    _rounded(cell, x0, build.back + bob + 1, x1, build.belly + bob)
    _rounded(cell, x0 + (x1 - x0) // 2, build.back + bob, x1, build.belly + bob)


def _tail_side(cell, build: Build, frame: int, bob: int) -> None:
    """Back and UP, tapering to a point. It is two pixels thick and therefore
    comes out solid ink, which is what a mangy tail at this size is."""
    x0 = build.torso[0]
    lift = (0, 1, 0)[frame]
    y = build.back + bob + 1 - lift
    for step in range(build.tail + 2):
        # It goes back before it goes up, so the base is a thick root off the
        # hips and only the last third leaves the horizontal. A tail that
        # rises from the first pixel is an aerial.
        _span(cell, x0 - step - 1, x0 - step, y)
        if step < build.tail:
            _span(cell, x0 - step - 1, x0 - step, y + 1)
        if step >= 1:
            y -= 1


def _leg(cell, build: Build, x: int, top: int, swing: int) -> None:
    """One leg: a shin that SLANTS to where the paw landed.

    The swing moves the foot, not the shoulder — a leg translated sideways is
    a leg that came off the body, and at four pixels of shin that is the whole
    difference between a walk and a slide.
    """
    span = max(1, build.ground - top)
    for step, y in enumerate(range(top, build.ground + 1)):
        shift = round(swing * step / span)
        _put(cell, x + shift, y, SOLID)
        _put(cell, x + 1 + shift, y, SOLID)
    paw = x + swing
    _span(cell, paw - 1, paw + 2, build.ground)


#: The gait, as pixels of swing per frame. Column 1 is the passing pose (the
#: idle), which is the same three-column contract every walk sheet here uses.
#: The front and rear pairs are in OPPOSITE phase — a quadruped that moved all
#: four legs together would be bounding, and a bounding wolf reads as a toy.
SWING = (-1, 0, 1)
BOB = (0, -1, 0)


def _legs_side(cell, build: Build, frame: int, bob: int) -> None:
    x0, x1 = build.torso
    top = build.belly + bob - 1
    swing = SWING[frame]
    # Far pair first: they are painted into the same mask, so what makes them
    # read as further away is that the near pair is drawn a pixel down and
    # outward over the top of them.
    _leg(cell, build, x1 - 4, top, -swing)
    _leg(cell, build, x0 + 1, top, swing)
    _leg(cell, build, x1 - 2, top, swing)
    _leg(cell, build, x0 + 3, top, -swing)


def _snout(build: Build) -> int:
    """How far the muzzle reaches past the skull. A third of the head, floored
    at two: one pixel of nose is a dog, and this has to read as a wolf."""
    return max(2, build.head_size[0] // 3)


def _head_side(cell, build: Build, hx: int, hy: int) -> None:
    """One skull, pointing right: a WEDGE, not a box.

    THE MUZZLE IS THE MARK. It is what makes this a wolf rather than a dog or
    a large cat at sixteen pixels — long, low, and carried level with the
    bottom of the skull rather than centred on it. Everything above the muzzle
    slopes back to the ears, which is the line a canine skull actually makes
    and the reason the head does not need a single pixel of detail to read.
    """
    w, h = build.head_size
    reach = _snout(build)
    jaw = h - 2
    for index in range(h):
        # The back of the head is vertical; the front runs forward and down
        # into the snout, so the silhouette is a wedge pointing at you.
        x0 = hx + (1 if index == 0 else 0)
        if index in (jaw - 1, jaw):
            x1 = hx + w - 1 + reach
        elif index == jaw + 1:
            # The lower jaw is SHORT of the top one. That gap is the whole
            # difference between a mouth and a snout.
            x1 = hx + w - 2 + reach // 2
        else:
            x1 = hx + w - 1 - (1 if index == h - 1 else 0)
        _span(cell, x0, x1, hy + index)
    # The ears: two of them, off the back of the skull, and the only part of
    # this animal that points up. They are what break the horizontal.
    _put(cell, hx, hy - 1, SOLID)
    _put(cell, hx + 1, hy - 1, SOLID)
    _put(cell, hx + 1, hy - 2, SOLID)
    _put(cell, hx + 3, hy - 1, SOLID)
    if w >= 8:
        _put(cell, hx + 3, hy - 2, SOLID)
        _put(cell, hx + 4, hy - 1, SOLID)


def _neck_side(cell, build: Build, hx: int, hy: int, bob: int) -> None:
    """A wedge from the shoulders to one skull. Drawn per head, so a second
    neck is what a second head costs and nothing else has to know."""
    root_x = build.torso[1] - 3
    root_y = build.back + bob + 1
    tip_x = hx + 1
    tip_y = hy + build.head_size[1] // 2
    # Walked as a LINE rather than as a column per x, because the second and
    # third necks rise almost vertically off the same shoulders — iterating x
    # would draw those as a two-pixel stub floating under a skull.
    steps = max(abs(tip_x - root_x), abs(tip_y - root_y), 1)
    for index in range(steps + 1):
        t = index / steps
        x = round(root_x + (tip_x - root_x) * t)
        y = round(root_y + (tip_y - root_y) * t)
        # A CROSS, not a square brush. Two skulls three pixels apart with a
        # square-brushed neck between them fuse into one wedge and the animal
        # stops being countable, which on this creature is the entire read.
        for dy in range(-1, 2):
            _put(cell, x, y + dy, SOLID)
        _put(cell, x + 1, y, SOLID)


def _eyes_side(cell, build: Build, hx: int, hy: int) -> None:
    """The socket and what is still burning in it. AFTER the keyline.

    A hole with an ember in it, exactly the zombie's contract — this is the
    same accent hue the player has spent a whole night learning means
    something has noticed them, and it is the only saturated pixel a wolf is
    allowed to carry. One per head.
    """
    w, h = build.head_size
    ex = hx + w - 3
    ey = hy + h - 4
    _put(cell, ex, ey + 1, INK)
    _put(cell, ex + 1, ey, "d")
    _put(cell, ex, ey, "E")


def _teeth_side(cell, build: Build, hx: int, hy: int) -> None:
    """The jaw, open. Bone along the gap between the muzzle and the lower jaw
    — the only bright thing on the animal that is not an eye, and it is why
    the head reads as a head and not as a lump."""
    w, h = build.head_size
    reach = _snout(build)
    line = hy + h - 2
    for step in range(reach + 1):
        x = hx + w - 2 + step
        _put(cell, x, line, "N" if step % 2 == 0 else "b")
    # The nose, and the one piece of bare flesh on the sheet.
    _put(cell, hx + w - 1 + reach, line - 1, "r")


def _ribs_side(cell, build: Build, bob: int) -> None:
    """What is left of the flank. Bone showing between rot, on the near side
    only — a ribcage drawn on both sides of a body reads as stripes."""
    x0, x1 = build.torso
    y = build.back + bob + 2
    for step in range(3):
        x = x1 - 5 - step * 3
        if x <= x0 + 1:
            break
        _put(cell, x, y, "b")
        _put(cell, x, y + 1, "r")
    _put(cell, x0 + 2, build.belly + bob - 1, "r")


# --- the head-on and going-away views ----------------------------------------
# A quadruped is the one thing in this game whose facings are not the same
# drawing rotated: side-on it is a long horizontal, head-on it is a narrow
# vertical mass with the heads stacked in FRONT of it, and going away it is a
# rump with a tail up the middle. Two separate builders rather than one with
# flags, because the two views share nothing but the legs.


def _chest_half(build: Build) -> int:
    """Half the width of the animal seen end-on. A third of its own length,
    which is roughly what a canine is, and derived so the alpha does not need
    a second number that could disagree with its side view."""
    return max(3, (build.torso[1] - build.torso[0]) // 3)


def _body_front(cell, build: Build, bob: int, away: bool) -> None:
    """The torso seen end-on. Its LENGTH is hidden behind its own shoulders,
    so this facing is carried almost entirely by the head — which is exactly
    why the multi-headed builds read best from here."""
    mid = build.mid_x
    half = _chest_half(build)
    top = build.back + bob - 1
    _rounded(cell, mid - half, top, mid + half, build.belly + bob)
    # The haunches, a row wider at the bottom on the going-away view: what you
    # actually see of a walking animal from behind is its hips.
    if away:
        _rounded(cell, mid - half - 1, build.belly + bob - 2, mid + half + 1,
                 build.belly + bob, inset=0)
        # The tail, straight up the middle of the rump, and it is the READ on
        # this facing: a wolf walking away is a tail before it is anything
        # else. Two pixels thick for most of its length and clear of the back
        # by a row, so it is a shape rather than a bump in the outline.
        for step in range(build.tail + 3):
            y = top - 1 - step
            _put(cell, mid, y, SOLID)
            if step < build.tail + 1:
                _put(cell, mid + 1, y, SOLID)


def _head_front(cell, build: Build, hx: int, hy: int, away: bool) -> None:
    """One skull face-on, or the back of one. Narrower than it is side-on,
    because a muzzle pointing at the camera is a muzzle you cannot see."""
    w, h = build.head_size
    half = max(2, w // 2)
    _rounded(cell, hx - half, hy, hx + half, hy + h - 3)
    # Ears, and on this facing they are most of the read: a spike off each top
    # corner, which is the shape nothing else in the forest has.
    for side in (-1, 1):
        _put(cell, hx + side * half, hy - 1, SOLID)
        _put(cell, hx + side * (half - 1), hy - 1, SOLID)
    if not away:
        # The muzzle, straight at you: narrower than the skull and hanging a
        # row BELOW the chest. That overhang is the only thing that separates
        # the head from the shoulders on a facing where the two share an
        # outline, and without it the animal is a lump with eyes.
        _rounded(cell, hx - half + 2, hy + h - 4, hx + half - 2, hy + h, inset=0)


def _eyes_front(cell, build: Build, hx: int, hy: int) -> None:
    """BOTH eyes, and this is the one facing where a creature gets two.

    `make_zombie.py`'s rule is one lit socket per head because asymmetry reads
    as a head turned slightly away. Head-on there is nothing turned away —
    the thing is looking at you, and hiding that would be the sprite lying
    about the only fact that matters on this facing.
    """
    w, _ = build.head_size
    half = max(2, w // 2)
    ey = hy + 1
    for dx in (-half + 1, half - 1):
        _put(cell, hx + dx, ey + 1, INK)
        _put(cell, hx + dx, ey, "E")


def _teeth_front(cell, build: Build, hx: int, hy: int) -> None:
    w, h = build.head_size
    half = max(2, w // 2)
    y = hy + h - 1
    for x in range(hx - half + 2, hx + half - 1):
        _put(cell, x, y, "N" if (x - hx) % 2 == 0 else "b")


def _front_offsets(build: Build, away: bool = False) -> list[tuple[int, int]]:
    """Where the skulls sit head-on, derived from the side view's fan.

    The side view spreads them in x (forward) and y (up); face-on the forward
    axis is INTO the screen and cannot be drawn, so it becomes the horizontal
    spread instead. Derived rather than authored so the two views can never
    disagree about how many heads the animal has or how they are arranged —
    and the vertical stagger survives, because three skulls in a straight line
    is a hood ornament and three at different heights is a thing.
    """
    mid = build.mid_x
    # SHOULDER TO SHOULDER, derived from the skull's own width. Anything
    # tighter and two heads face-on are one head with a bulge: the first cut
    # spread them by `w - 2` and a wolf and a twin came out twenty-five pixels
    # apart on the facing a player meets them from, which is a recolour by
    # `test_creature_sheets.py`'s arithmetic and looked like one on screen.
    spread = 2 * max(2, build.head_size[0] // 2)
    count = build.count
    # COMING AT YOU the head is the whole picture, so it hangs off the front
    # of the chest at belly height. GOING AWAY it is behind two feet of
    # shoulder and all you get is the top of a skull over the back — which is
    # correct, and is why the tail has to carry that facing instead.
    # COMING AT YOU the skull shares its top line with the shoulders, so the
    # EARS are the topmost thing on the sprite and the muzzle hangs below the
    # chest — head down, ears up, which is the whole posture. GOING AWAY it
    # sinks two rows so all that shows is the crown of each skull over the
    # back, and the tail carries the facing instead.
    base = build.back - 2 if away else build.back - 1
    out: list[tuple[int, int]] = []
    for index in range(count):
        offset = index - (count - 1) / 2
        out.append((mid + round(offset * spread), base - (index % 2)))
    return out


# --- frames ------------------------------------------------------------------


def _walk_side(build: Build, frame: int) -> list[list[str]]:
    cell = _cell(build)
    bob = BOB[frame]
    _tail_side(cell, build, frame, bob)
    _torso_side(cell, build, bob)
    _legs_side(cell, build, frame, bob)
    for dx, dy in build.heads:
        hx, hy = build.head[0] + dx, build.head[1] + dy + bob
        _neck_side(cell, build, hx, hy, bob)
        _head_side(cell, build, hx, hy)
    _shade(cell, build)
    _ribs_side(cell, build, bob)
    for dx, dy in build.heads:
        hx, hy = build.head[0] + dx, build.head[1] + dy + bob
        _teeth_side(cell, build, hx, hy)
        _eyes_side(cell, build, hx, hy)
    return cell


def _walk_front(build: Build, frame: int, away: bool) -> list[list[str]]:
    cell = _cell(build)
    bob = BOB[frame]
    _body_front(cell, build, bob, away)
    mid = build.mid_x
    half = _chest_half(build)
    swing = SWING[frame]
    top = build.belly + bob - 1
    # Four legs on this facing too, but the far pair is a row shorter and a
    # pixel inboard — that overlap is the only depth an end-on view has.
    _leg(cell, build, mid - half + 1, top + 1, -swing)
    _leg(cell, build, mid + half - 2, top + 1, swing)
    _leg(cell, build, mid - half, top, swing)
    _leg(cell, build, mid + half - 1, top, -swing)
    heads = _front_offsets(build, away)
    for hx, hy in heads:
        _head_front(cell, build, hx, hy + bob, away)
    _shade(cell, build)
    if not away:
        for hx, hy in heads:
            _teeth_front(cell, build, hx, hy + bob)
            _eyes_front(cell, build, hx, hy + bob)
    return cell


#: THE COLLAPSE, and it is the quadruped version of `make_zombie.HEAD_POSE`:
#: offsets from the standing pose, one column per frame, the last of which
#: holds for the rest of the night. A four-legged body does not topple — the
#: legs go out from under it and the chest hits first, which is what these
#: numbers are: the back drops faster than the head does until the head is on
#: the floor too.
FALL = ((0, 0), (0, 2), (1, 4), (2, 5), (2, 5))
#: The frames drawn lying down rather than standing on anything.
DOWN = (False, False, True, True, True)


def _death(build: Build, facing: str, frame: int) -> list[list[str]]:
    cell = _cell(build)
    dx, dy = FALL[frame]
    if not DOWN[frame]:
        if facing == "side":
            _tail_side(cell, build, 1, dy)
            _torso_side(cell, build, dy)
            _legs_side(cell, build, 1, dy)
            for hdx, hdy in build.heads:
                hx, hy = build.head[0] + hdx - dx, build.head[1] + hdy + dy
                _neck_side(cell, build, hx, hy, dy)
                _head_side(cell, build, hx, hy)
        else:
            _body_front(cell, build, dy, facing == "up")
            heads = _front_offsets(build, facing == "up")
            for hx, hy in heads:
                _head_front(cell, build, hx, hy + dy, facing == "up")
        _shade(cell, build)
        _dead_eyes(cell, build, facing, dy, dx)
        return cell

    # THE HEAP. A dead wolf is a long low mass with the heads at one end of it
    # and the legs folded under, and the reason it is worth drawing rather
    # than squashing the walk frame is that the player has to be able to tell,
    # at a glance and in the dark, that the shape on the floor used to have
    # three heads. That is the whole payload of killing one.
    x0, x1 = build.torso
    rest = build.ground - 3
    skull = max(4, build.head_size[0] - 3)
    # The flank, long and low, with the shoulders still a row proud of it: a
    # dead animal deflates from the hips forward and the chest is the last
    # part to give.
    _rounded(cell, x0 - 1, rest + 1, x1 - 3, build.ground)
    _rounded(cell, x1 - 9, rest, x1 - 4, build.ground - 1)
    # The necks went out from under the heads, so the heads are THROWN PAST
    # the body and stepped up away from it. That fan is the payload of the
    # kill — the player has to be able to count them on the floor.
    for index in range(build.count):
        hx = x1 - 4 + index * 2
        hy = rest + 1 - index
        _rounded(cell, hx, hy, hx + skull, hy + 2, inset=0)
        _put(cell, hx, hy - 1, SOLID)
        _put(cell, hx + 2, hy - 1, SOLID)
    # Legs folded under, and the tail trailing away behind. A tail that came
    # back round would be the sleeping pose, which is the one shape this must
    # never be mistaken for.
    for step in range(build.tail + 2):
        _put(cell, x0 - 2 - step, rest + 2, SOLID)
    _shade(cell, build)
    pool = build.ground
    for x in range(x0 - 1, x1 - 3):
        if (x * 5) % 3:
            _put(cell, x, pool, "x")
    if frame == len(FALL) - 1:
        for x in range(x1 - 8, x1 - 4):
            _put(cell, x, pool, "X")
    return cell


def _dead_eyes(cell, build: Build, facing: str, dy: int, dx: int) -> None:
    """The lights, still on. They go out when the body reaches the floor —
    same beat as the Sawyer's ember, for the same reason: the accent is what
    the player has been tracking, so losing it is what says it is over."""
    if facing == "side":
        for hdx, hdy in build.heads:
            _eyes_side(cell, build, build.head[0] + hdx - dx, build.head[1] + hdy + dy)
    else:
        for hx, hy in _front_offsets(build):
            if facing == "down":
                _eyes_front(cell, build, hx, hy + dy)


# --- the sleep sheet ---------------------------------------------------------


#: The breath, in pixels of rise. Three frames, looped: out, in, out. It is
#: one pixel because one pixel at this size is a whole chest, and two would be
#: a body convulsing.
BREATH = (0, -1, 0)


def _sleep(build: Build, frame: int) -> list[list[str]]:
    """CURLED, not lying down. A dead wolf is flat and a sleeping one is a
    ring: the spine comes round, the tail crosses the paws, and the heads are
    tucked into the flank rather than pointing anywhere.

    The difference between this and the death sheet's last column is the whole
    reason the pose exists — a player has to be able to tell a den from a
    corpse across a clearing, before they are close enough to be noticed.
    """
    cell = _cell(build)
    rise = BREATH[frame]
    ground = build.ground
    x0, x1 = build.torso
    depth = build.belly - build.back + 3
    floor = ground - depth

    # THE COIL. Two masses: the flank on the ground, and the spine arched over
    # it. The BREATH moves the spine and the heads and leaves the flank where
    # it is — a body that translates whole is a body bouncing, and the one
    # thing this pose has to say is that the thing is alive without moving.
    _rounded(cell, x0, floor + 2, x1, ground)
    _rounded(cell, x0 + 2, floor + rise, x1 - 3, ground - 1)
    # The tail, round the front and across the paws, closing the ring. It is
    # what makes the shape a CURL rather than a heap: a corpse's tail trails
    # away from the body and a sleeping animal's comes back to its own nose.
    for step in range(build.tail + 4):
        _put(cell, x1 - 1 - step, ground, SOLID)
        _put(cell, x1 - 1 - step, ground - 1, SOLID)
    _put(cell, x1, ground - 2, SOLID)

    # The heads, tucked along the flank and stepped down toward the paws.
    # Nothing points outward — every skull is turned in on the body, which is
    # the difference a player has to be able to read across a clearing.
    skull = max(4, build.head_size[0] - 3)
    for index in range(build.count):
        hx = x1 - skull - 1 - index * (skull - 1)
        # ABOVE the spine, not inside the flank. A head tucked so far in that
        # it is under the body's own outline is a head nobody can count, and
        # counting them is the whole reason the den reads before it is
        # dangerous.
        hy = floor - 2 + index + rise
        _rounded(cell, hx, hy, hx + skull, hy + 2, inset=0)
        # Ears, laid back against the skull but still proud of it.
        _put(cell, hx, hy - 1, SOLID)
        _put(cell, hx + 2, hy - 1, SOLID)
    _shade(cell, build)

    # A CLOSED EYE AND NO EMBER, on every head. The lit socket is this game's
    # word for "it has noticed you", so the one creature that has not is also
    # the only art in the game that wears a dark slit instead — and that
    # absence is the whole telegraph. It is what goes away when he wakes.
    for index in range(build.count):
        hx = x1 - skull - 1 - index * (skull - 1)
        hy = floor - 2 + index + rise
        _put(cell, hx + skull - 2, hy + 1, INK)
        _put(cell, hx + skull - 1, hy + 1, INK)
    return cell


# --- build -------------------------------------------------------------------

FACINGS = ("down", "side", "up")


def _raw(build: Build, cells: list[list[list[str]]]) -> Image.Image:
    rows = len(cells)
    cols = max(len(row) for row in cells)
    img = Image.new("RGBA", (build.width * cols, build.height * rows), KEY)
    px = img.load()
    for row, frames in enumerate(cells):
        for col, cell in enumerate(frames):
            for y in range(build.height):
                for x in range(build.width):
                    key = cell[y][x]
                    if key == ".":
                        continue
                    assert key != SOLID, f"{build.key}: unshaded pixel at {x},{y}"
                    px[col * build.width + x, row * build.height + y] = RGBA[key]
    return img


def _process(name: str, build: Build, tile: int) -> None:
    process_sprites.process(
        SimpleNamespace(
            name=name,
            tile=tile,
            width=build.width,
            height=build.height,
            tolerance=40,
            no_hue_key=False,
            # Same as every creature: the source side row faces right and the
            # pipeline mirrors it into the left one.
            side_facing="right",
            filter="auto",
            alpha_threshold=128,
            bottom_pad=0,
            exact=True,
            uniform=False,
        )
    )


def build(args) -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def write(name: str, spec: Build, cells) -> None:
        path = RAW_DIR / f"{name}.png"
        _raw(spec, cells).save(path)
        _process(name, spec, args.tile)
        written.append(path)

    for key, spec in BUILDS.items():
        walk = [
            [
                _walk_side(spec, i) if facing == "side" else _walk_front(spec, i, facing == "up")
                for i in range(3)
            ]
            for facing in FACINGS
        ]
        write(key, spec, walk)
        write(
            f"{key}-death",
            spec,
            [[_death(spec, facing, i) for i in range(len(FALL))] for facing in FACINGS],
        )

    alpha = BUILDS["wolf-alpha"]
    write(
        "wolf-alpha-sleep",
        alpha,
        [[_sleep(alpha, i) for i in range(3)] for _ in FACINGS],
    )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the zombie wolf sheets.")
    parser.add_argument("--tile", type=int, default=TILE)
    args = parser.parse_args()
    for path in build(args):
        print(f"wrote {path.relative_to(RAW_DIR.parents[1])}")


if __name__ == "__main__":
    main()
