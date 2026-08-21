#!/usr/bin/env python3
"""Asset pipeline: held weapon sprites.

Twelve weapons, one frame each, drawn from ABOVE at the same high 3/4 the rest
of the world is drawn at (PIXEL-ART-DIRECTION-V2.md S1). The knife is on the sheet
too, since a blade in the hand is drawn by exactly the same code as a barrel in
the hand. The client rotates the frame around the grip and mirrors it when the
aim is left, so a single row is every facing.

These are IN HAND, not loot icons. Ground / HUD icons live in make_loot.py
under the same keys, because a drop is a standing prop on the 16x16 loot
atlas. Do not fold the two together: a 16px isometric pistol rotated around a
grip is mush, and a side-view rifle planted on a tile reads as a signpost.

Every weapon is the same pixel SCALE and the same authored HEIGHT (seven rows,
the bore always on row 1). Length is the class: knife shortest, pistols short,
rifles longer, AWP longest. A mixed scale next to a 16px body reads as twelve
different toys.

LENGTH IS DERIVED, AND THE LADDER IS THE WHOLE OF IT — 9 / 9 / 10 / 12 for the
pistols, 12-13 for the SMGs, 14-16 for the rifles and the shotgun, 18 for the
AWP, 8 for the blade. Two rules produce those numbers and neither is a taste
call:

  * A PISTOL is drawn at its real proportion. Six rows is genuinely the whole
    height of a handgun here — grip heel to slide top — so its length is
    `real length / real height * 6`: a Glock is 20.4 by 13.8 cm, so 1.48, so
    nine pixels. The Deagle's 1.72 makes it ten, and it is the only pistol
    with a crown row, which is what makes it read as the big one.
  * EVERYTHING LONGER is compressed, because six rows stops being a real
    height the moment a weapon has a stock: an AK at true scale is 22 columns
    against a 16px body, and an AWP is 28. Those run on `1.278 * cm ** 0.55`,
    anchored so the AK — the reference rifle — lands at 15.

The first cut of this sheet had the pistols at 11-15 and they overhung the
body they were held against; the correction overshot to 7 and turned them into
hammers — a three-pixel receiver under a three-row grip. Both failures are the
same mistake, which is picking a length instead of deriving one.

GRIPS ARE FORESHORTENED, AND THAT IS WHY A PISTOL IS NOT A SIDE VIEW WITH THE
TOP SHADED. A real handgun is about 60% grip by height, and drawing it that
way here is what made the stubby version read as a hammer: this camera looks
DOWN, so a grip pointing at the floor is the one part of the weapon the angle
takes away, while the body shows its full length. Pistols get two rows of grip
under three rows of body. The Berettas are the exception and earn it — their
lower rows are a second gun, not a longer grip.

THE CAMERA IS A ROW GRID, AND THAT IS THE WHOLE CONSTRUCTION.

These used to be flat side elevations shaded by a diagonal gradient, which is a
drawing of a gun rather than a gun: no top face, so no thickness, so twelve
decals lying on a world that had just been rebuilt out of stacked volumes. The
fix is not more pixels, it is committing to one camera — and because the frame
ROTATES with the aim, that camera cannot be expressed as a light azimuth. Spin
a sprite lit from the upper left through 360 degrees and the key light spins
with it.

What survives the rotation is PITCH. A face that points at the sky points at
the sky at every heading, so the plane a pixel belongs to is a function of its
ROW and nothing else, identical for all twelve:

    row 0   crown       step 4   sight, optic, carry handle, a mag lying on top
    row 1   BORE        step 3   the lit top plane: barrel, receiver, stock
    row 2   near side   step 2   the same masses turning away from the camera
    row 3   under-shelf step 1   handguard belly, tube mag, trigger group
    row 4   hang upper  step 2   grip and magazine, the near face of each
    row 5   hang lower  step 1   the same, receding under the gun
    row 6   heel        step 0   floorplate, butt, the contact-dark tip

Row 3 is deliberately darker than row 4. It is the seam where the body ends and
the things hanging off it begin (S10's contact band), and without it a rifle's
magazine welds itself to the receiver and the whole silhouette is one slab.

THICKNESS IS ROW COUNT, AND THAT IS THE OTHER HALF OF IT. A row grid gives
every mass its plane, but it says nothing about how thick that mass is; the
first cut of this sheet ran barrel, receiver and butt all three rows deep for
the entire length of every rifle, and three rows deep for the entire length is
a slab with a bright line painted on it. A real weapon tapers, and on this
camera the taper is vertical: the butt is the thickest thing on the gun, the
receiver next, the handguard next, and the barrel is TWO rows against their
three. Five of the twelve used to be one shared blob at 1x for exactly this
reason. Read the maps as a taper first and as parts second.

The alphabet is one letter per PART; the plane comes from the row and the
material from the palette beside each map, so the art maps read as engineering
drawings rather than as shading. Two modifiers:

    UPPERCASE   lift one ramp step. The specular streak along a form's length
                (S14, bare metal) and a lit crest. Nothing else.
    x           a recess, in the shared VOID ramp: ejection port, dust-cover
                seam, stock seam, trigger notch, bolt cut. Interior form breaks
                are value steps and never lines (S6), and a recess is the one
                value step allowed to be a single pixel wide.

Frames are CENTRED in the cell, not left-aligned. The grip and the muzzle are
derived from the same offset, so nothing downstream notices — but the store
tables blit this sheet centred on the boards (render/layers/store.ts), and a
left-aligned knife sat off the edge of its own pedestal.

Output (assets/processed/guns/):
    sheet.png      one row, 20x9 frames, catalog order
    manifest.json  frame, grip, muzzle, hold, scale per key

The grip is the pivot (hand). The muzzle is where the tracer starts. Both are
pixel coordinates inside the frame.

`hold` and `scale` are the odd ones out, and both are pose rather than art.
`hold` is WORLD pixels along the aim from the body centre out to that pivot
— how far in front of the character the weapon is carried. A gun is held out
at arm's length, which is why it defaults to `HOLD_OUT`. A knife is not: it
is held IN, at the body, and a blade drawn at a pistol's extension reads as
a tiny sword floating beside the sprite rather than as something in
somebody's hand. `scale` is a multiplier on the drawn frame, 1.0 for
everything the sheet's one-pixel-scale rule covers.

Usage:
    python tools/make_guns.py
    python tools/make_guns.py --tile 16
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    Ramp,
    TRANSPARENT,
    material_ramp,
    outline,
    pack,
    rgb,
)

#: Authored rows per weapon. Every art map is exactly this tall — a shorter one
#: would centre differently and its bore would leave the line.
ROWS = 7
#: Two wider than the longest map (the AWP, at 18), which is the outline's
#: margin. Nothing downstream reads a frame size that is not in the manifest.
FRAME_W = 20
FRAME_H = 9

#: Ramp step per authored row: the camera, written down. See the module
#: docstring — this table is the reason twelve weapons read as one set.
ROW_STEP: tuple[int, ...] = (4, 3, 2, 1, 2, 1, 0)

#: World px along aim from the body centre to the grip, for something held
#: out at arm's length. Every gun uses it; see `hold` in the module docstring.
HOLD_OUT = 3.0
#: Held IN: the grip sits ON the body's centre line and the blade is the only
#: part in front of it. That is the difference between a knife and a sword at
#: this size — what reaches forward is the blade's length, never the arm's.
HOLD_IN = 0.0

# Materials against the night, DERIVED rather than picked. Every ramp is five
# steps built by `_ramp` out of PIXEL-ART-DIRECTION-V2.md S11's table, so a
# material is authored as the three things that actually differ — its hue, how
# saturated it is, and how far its darkest and lightest steps sit apart — and
# the hue-shift and saturation law is written once instead of twelve times in
# hex.
#
# The `lo` end is the important number and it is the one this sheet had wrong.
# These ramps used to bottom out around #0b0d11, a hair off the outline, which
# meant every plane the row grid puts on step 0 or 1 — the whole underside of
# the gun, and the entire grip and magazine — collapsed into the outline. A
# grip you cannot see is not a grip, and twelve dark blobs with a bright strip
# on top is what that produces. S7 is explicit that step 2 is the ambient
# reference and "not black", and S13 caps the internal span at ~55 L; the floor
# here is set so the darkest fill still reads against `OUTLINE`, and the
# ceilings stay under the world's own (`ROCK_RAMP` tops out at #5d5860) because
# the lantern multiplies over all of it.

#: S11's law, IMPORTED. It used to live here as `_ramp` plus its three step
#: tables; `make_loot.py` needs the same law for the same reason (its ground
#: icons are the same objects), so it moved to `make_textures.py` beside every
#: other shared shading helper. Aliased rather than called through the module,
#: because the ramps below read as a materials list and `material_ramp(...)`
#: fifteen times over would bury what each line is actually saying.
_ramp = material_ramp


#: Painted metal (S14): large flat planes, one long streak along the form.
STEEL: Ramp = _ramp(214, 0.15, 0.09, 0.58)
#: Polymer furniture. The same cool family as steel but flatter and darker at
#: the top, so a polymer receiver never out-reads the barrel bolted to it.
POLY: Ramp = _ramp(220, 0.13, 0.08, 0.46)
#: The grip, and the one deliberately WARM neutral on the sheet. A grip cut
#: from the receiver's own ramp is a grip you have to already know is there;
#: a hue apart at the same value is a shape the eye separates without any
#: value step at all, which matters because the grip hangs on the rows the row
#: grid has already darkened.
GRIP: Ramp = _ramp(28, 0.14, 0.10, 0.44)
#: Magazine steel. A step cooler and darker than the receiver so the mag reads
#: as a separate object hung off it rather than as part of the same casting.
MAG: Ramp = _ramp(206, 0.17, 0.09, 0.50)
#: AK bakelite and the P90's translucent shell — the sheet's warm magazines.
TAN: Ramp = _ramp(34, 0.38, 0.12, 0.56)
#: AK furniture. The only wood on the sheet and the reason the AK is the one
#: weapon identifiable across a dark clearing without reading its outline.
WOOD: Ramp = _ramp(26, 0.42, 0.10, 0.52)
#: The can on a suppressed weapon. A step LIGHTER than the receiver it bolts
#: to, which is backwards from the real thing — a real suppressor is matte
#: black on a black upper. Two dark greys touching at this size are one shape,
#: and that shape is the entire reason a player buys the USP-S over the Glock
#: or the M4A1-S over the AK, so the art says it where a photograph would not.
CAN: Ramp = _ramp(210, 0.11, 0.13, 0.62)
#: Bare metal (S14): the same planes plus a tight step-4 to step-1 jump. Nickel
#: on the Deagle, the Berettas and the knife — the brightest frames here.
CHROME: Ramp = _ramp(205, 0.07, 0.12, 0.72)
#: The AWP's stock. The one saturated body on the sheet.
OLIVE: Ramp = _ramp(78, 0.26, 0.10, 0.48)
#: Optic housing: matte, low-saturation, and darker than the rifle under it so
#: the tube reads as a thing sitting ON the receiver.
OPTIC: Ramp = _ramp(150, 0.09, 0.07, 0.36)
#: The AWP's objective. The one accent hue on this sheet (S12), two pixels
#: wide, which is the whole budget an accent gets.
LENS: Ramp = _ramp(196, 0.62, 0.12, 0.74)
#: `x`. Not a material — a hole in one. Shared by every weapon, so a port on a
#: Glock and a port on an AK are the same darkness. It is the only ramp allowed
#: to sit near the outline, because that is what a hole looks like.
VOID: Ramp = _ramp(225, 0.18, 0.04, 0.15)
OUTLINE = rgb("#06070b")

Art = list[str]
Palette = dict[str, Ramp]

#: The grip — the pivot the hand closes on and the sprite turns around.
#: Matched case-insensitively, so a lit crest on a grip still counts as grip.
GRIP_CHARS = frozenset("g")
#: The muzzle face. Exactly one per weapon, always on the bore row, because the
#: tracer leaves from it.
MUZZLE_CHARS = frozenset("m")

#: THE ACTION FRAME IS DERIVED, NOT DRAWN. A second art map per weapon would
#: be twelve more hand-counted grids to keep in step with the first twelve, and
#: the thing a second map would say is mechanical rather than artistic: the
#: reciprocating group — slide, bolt carrier, breech block — travels BACKWARD
#: and leaves a hole where it was. That is a transform of the closed frame, so
#: it is written once here and applied to all of them.
#:
#: WHAT RECIPROCATES is the run of receiver letters on the two top planes: row
#: 1 (the bore) and row 2 (the side it turns away on). A barrel does not move,
#: a grip does not move, a magazine does not move, and none of them are `r`.
#: Recesses already inside the run travel with it — a dust-cover seam is cut
#: INTO the slide — which is why `x` joins a run but never starts one.
CYCLE_ROWS = (1, 2)
CYCLE_CHARS = frozenset("r")
#: What may be crossed or swallowed as the group travels back: its own letters,
#: its own seams, and empty space. A stock or a wooden butt is none of those,
#: and a bolt that ate one would be a rifle a pixel shorter every shot.
CYCLE_JOIN = frozenset("rx.")
#: The hole the group leaves. `x` is the sheet's shared VOID ramp, so an open
#: port on a Glock is exactly as dark as an open port on an AK.
PORT = "x"


def _pad(art: Art) -> Art:
    width = max(len(row) for row in art)
    return [row.ljust(width, ".") for row in art]


def _origin(art: Art, width: int, height: int) -> tuple[int, int]:
    """Where the art map's (0, 0) lands in the frame. Centred both ways."""
    return ((width - len(art[0])) // 2, (height - len(art)) // 2)


def art_size(art: Art) -> tuple[int, int]:
    """(columns, rows) of a map, before it is padded. For placing an origin."""
    return (max(len(row) for row in art), len(art))


def paint_rows(art: Art, ramps: Palette, size: tuple[int, int],
               origin: tuple[int, int]) -> Image.Image:
    """The row grid, painted. NO OUTLINE — the caller owns that.

    No gradient and no dither: a pixel's value is its ROW's plane (`ROW_STEP`)
    and its letter's material, and that pair is the only rule this whole sheet
    is shaded by. The old diagonal falloff is what made twelve guns look like
    twelve stickers — it lit them from a direction the client then spun.

    THIS IS PUBLIC BECAUSE THE GROUND ICONS ARE PAINTED BY IT TOO.
    `make_loot.py` draws the same twelve weapons at 16px for the floor and the
    hotbar, and "the icon matches the thing in your hands" is a promise no
    amount of matching prose keeps — the two sheets ran on different shaders
    for exactly as long as the shading lived in a private function here, and
    the loot copies were still lit by a diagonal falloff after this sheet had
    stopped being. Sharing the painter is what makes the match structural.
    Only the ORIGIN differs, which is why it is an argument: a held frame is
    centred in its cell, and a thing lying on the ground is planted on the
    bottom of one.
    """
    art = _pad(art)
    img = Image.new("RGBA", size, TRANSPARENT)
    px = img.load()
    width, height = size
    ox, oy = origin
    for y, row in enumerate(art):
        plane = ROW_STEP[y]
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px_x, px_y = ox + x, oy + y
            if not (0 <= px_x < width and 0 <= px_y < height):
                continue
            if ch == "x":
                px[px_x, px_y] = VOID[plane]
                continue
            ramp = ramps.get(ch.lower())
            if ramp is None:
                continue
            step = min(plane + 1, len(ramp) - 1) if ch.isupper() else plane
            px[px_x, px_y] = ramp[step]
    return img


def _blit(art: Art, ramps: Palette, width: int, height: int) -> Image.Image:
    """One weapon in its held frame, centred."""
    padded = _pad(art)
    img = paint_rows(art, ramps, (width, height),
                     _origin(padded, width, height))
    outline(img, OUTLINE)
    return img


def _centroid(art: Art, chars: frozenset[str], ox: int, oy: int) -> tuple[int, int]:
    """Mean of every grip pixel — the pivot, not a corner of the band."""
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(art):
        for x, cell in enumerate(row):
            if cell.lower() in chars:
                xs.append(ox + x)
                ys.append(oy + y)
    if not xs:
        return (ox, oy + len(art) // 2)
    return (round(sum(xs) / len(xs)), round(sum(ys) / len(ys)))


def _cycled(art: Art) -> tuple[Art, tuple[int, int]] | None:
    """The same weapon with its action OPEN, and where the brass comes out.

    One pixel of travel is the whole animation, and one pixel is all a nine-row
    frame has: the group moves back into the space behind it and the cell it
    vacated at the front becomes a port. At this size that reads as a slide
    cycling — the eye is catching the DARK NOTCH appearing under the rear
    sight, not measuring a distance.

    A group with nothing behind it (the P90 and the FAMAS both run their
    receiver to the back of the frame — one is a bullpup and the other very
    nearly one) cannot travel, so its port simply opens. That is the honest
    drawing rather than a fallback: on a real bullpup the breech is behind the
    grip, and what a shooter sees move is the ejection cover and nothing else.

    Returns the map and the PORT cell in map coordinates, or None for a weapon
    with no reciprocating group at all — the knife, which is the whole reason
    this returns an option instead of asserting.
    """
    rows = list(_pad(art))
    port: tuple[int, int] | None = None
    for y in CYCLE_ROWS:
        row = list(rows[y])
        start = next((i for i, ch in enumerate(row) if ch.lower() in CYCLE_CHARS), None)
        if start is None:
            continue
        end = start
        while end + 1 < len(row) and row[end + 1].lower() in CYCLE_JOIN - {"."}:
            end += 1
        # A run ENDS on metal. A trailing seam is the gap before the next part
        # — the AWP's bolt handle sits in one — and travelling to it would open
        # the port a pixel further forward than the breech actually is.
        while end > start and row[end].lower() not in CYCLE_CHARS:
            end -= 1
        if start > 0 and row[start - 1].lower() in CYCLE_JOIN:
            row[start - 1:end] = row[start:end + 1]
        row[end] = PORT
        rows[y] = "".join(row)
        if y == 1:
            port = (end, y)
    return None if port is None else (rows, port)


def _rightmost(art: Art, chars: frozenset[str], ox: int, oy: int) -> tuple[int, int]:
    """Muzzle face: furthest right, then lowest."""
    found = (ox, oy + len(art) // 2)
    for y, row in enumerate(art):
        for x, cell in enumerate(row):
            if cell.lower() in chars:
                found = (ox + x, oy + y)
    return found


# Catalog order matches server/app/weapons.py and the loot keys.
#
# ONE LETTER PER PART, and that is what makes these maps readable as
# engineering drawings instead of as shading:
#
#     t  stock / butt        b  barrel            g  grip (the pivot)
#     r  receiver / body     h  handguard         n  magazine
#     c  suppressor can      k  mechanical bits — sight, carry handle,
#     e  optic housing          charging handle, barrel rib, crossguard
#     l  lens                m  muzzle face       x  recess / seam
#
# The palette dict beside each map assigns a MATERIAL to each letter, so the
# same drawing is steel on one weapon and wood on another, and so a part that
# has to separate from its neighbour separates by material where the row grid
# has already spent the value step. That is why the grip is the one warm
# neutral here: grip and magazine hang on the same three rows, at the same two
# planes, and nothing but hue was left to tell them apart.
#
# Read every map against the row table in the module docstring: row 1 is the
# bore on all twelve, row 3 is the seam under the body, and what hangs below it
# is grip and magazine. Length is the class, and the top contour is the
# identity (S15) — an AK is told from an M4 by its wood and its curved mag,
# never by a label.
#
# Pistol grips are a SOLID block — no magwell hole, no selector dial, no
# trigger-guard loop. At this size a 1px hole is filled by the outline pass and
# reads as a circle on the heel. The guard is an `x` notch bitten out of the
# under-shelf, which is the same statement one pixel cheaper.
GUNS: list[tuple[str, Palette, Art]] = [
    # --- pistols --------------------------------------------------------------
    # The short end of the sheet, and the reference for how a pistol is built
    # here: slide across rows 1-2 (the top plane, then the side it turns away
    # on), a barrel one row THINNER poking out of it, the polymer frame on row
    # 3, and the grip hanging off rows 4-6 with its rake going BACK — the butt
    # a column behind the web of the hand. A vertical grip reads as a drill.
    #
    # The floorplate on row 6 is the magazine, and it is one pixel pair: a
    # pistol's magazine lives inside the grip, so the only honest way to say
    # there is one is the plate it stands on.
    (
        "glock18",
        {"r": STEEL, "b": STEEL, "f": POLY, "g": GRIP, "n": MAG, "m": STEEL},
        [
            ".........",
            "..rrRRrbm",
            "..rxrrrb.",
            ".fffffx..",
            ".ggg.....",
            "ggn......",
            ".........",
        ],
    ),
    # THE CAN IS THE WHOLE SILHOUETTE. A suppressed pistol at this size is a
    # pistol with a fat cylinder where the barrel should be — three rows deep
    # against the slide's two, crown included — and it has to be legible from
    # across a dark clearing, because the reason to own this instead of the
    # Glock is that it is quiet and the player has to see which one is in hand.
    # The streak sits on the can and not on the slide for the same reason: the
    # eye is being sent to the cylinder.
    (
        "usp_s",
        {"r": STEEL, "f": POLY, "g": GRIP, "n": MAG, "c": CAN, "m": CAN},
        [
            ".......cccc.",
            "..rrRRrccccm",
            "..rxrrrcccc.",
            ".fffffx.....",
            ".ggg........",
            "ggn.........",
            "............",
        ],
    ),
    # TWO GUNS, DRAWN AS TWO SILHOUETTES, AND THE ROW GRID DOES THE DEPTH.
    # There is no room at this size to draw a second pistol properly, and one
    # pistol with a wider slide would read as a bigger pistol. What reads is a
    # whole second gun slung BELOW the first out of the same fist — and because
    # the lower rows are the darker planes, that second gun comes out
    # value-compressed without being drawn in a second material (S13: masses
    # further back lose the ends of the ramp). The eye counts guns, not detail,
    # and this frame has two. Only the upper one carries `m`: there is one
    # tracer origin however many barrels are in the drawing.
    (
        "dual_berettas",
        {"r": CHROME, "b": CHROME, "f": POLY, "g": GRIP, "m": CHROME},
        [
            ".........",
            "..rrRRrbm",
            "..rxrrrb.",
            ".fffffx..",
            "ggrrrrbb.",
            ".grxrrbb.",
            "..fffx...",
        ],
    ),
    # The heaviest thing anybody carries in one hand, and the only pistol that
    # spends a crown row: the rib down the top of the barrel is what separates
    # a big pistol from a big-looking one. Nickel, so it is also the brightest
    # frame on the sheet, and the rubber grip is the one dark mass on it.
    (
        "deagle",
        {
            "r": CHROME, "b": CHROME, "k": CHROME, "f": CHROME,
            "g": GRIP, "n": MAG, "m": CHROME,
        },
        [
            "...kkkk...",
            "..rrRRrbbm",
            "..rxrrrbb.",
            ".fffffx...",
            ".ggg......",
            "ggn.......",
            "..........",
        ],
    ),
    # --- submachine guns ------------------------------------------------------
    # Short, boxy, and the two frames whose magazine lives INSIDE the grip
    # rather than in front of it — so the hang is one narrow column of grip
    # with a floorplate under it instead of a grip beside a mag. Length is how
    # this sheet says range, and an SMG has to sit visibly between the pistols
    # and the rifles or the belt stops teaching anything.
    #
    # The stock is a folded stub behind an `x` seam. It is four pixels, and it
    # is the whole difference between an SMG and a very long pistol.
    (
        "mp7",
        {
            "t": POLY, "r": POLY, "h": POLY, "b": STEEL, "f": POLY,
            "g": GRIP, "n": MAG, "k": STEEL, "m": STEEL,
        },
        [
            "....kk......",
            "ttxrrRRrbbbm",
            "txrrrrrrbbb.",
            "..fffxff....",
            "...gg.......",
            "...gg.......",
            "...nn.......",
        ],
    ),
    # The P90 is the one real silhouette in the SMG class: a humped shell with
    # the magazine lying FLAT ALONG THE TOP and almost no barrel past it. That
    # mag is the whole reason row 0 is the brightest plane on the grid — it is
    # the highest surface on the weapon and the first thing the eye should
    # find — and it is drawn in TAN because the real one is translucent and
    # because a warm mass on the crown of a cool gun cannot be missed.
    (
        "p90",
        {
            "r": POLY, "h": POLY, "b": STEEL, "f": POLY,
            "g": GRIP, "n": TAN, "m": STEEL,
        },
        [
            "..nnnnnn.....",
            "rrrRRrrrhbbm.",
            "rrxrrrrrhbb..",
            ".fffffxff....",
            "...gg........",
            "...gg........",
            "..ff.........",
        ],
    ),
    # --- shotgun --------------------------------------------------------------
    # The tube magazine under the barrel is the tell, and on this camera it is
    # a THIRD BAND rather than a second outline: barrel top on row 1, barrel
    # side on row 2, tube on row 3. It stops short of the muzzle, which is what
    # says two tubes instead of one thick one — a tube running the full length
    # is just a fatter barrel. Longest stock on the sheet, because the thing
    # that kicks hardest is the thing you brace.
    (
        "xm1014",
        {
            "t": POLY, "r": STEEL, "h": POLY, "b": STEEL, "f": POLY,
            "g": GRIP, "n": MAG, "m": STEEL,
        },
        [
            "................",
            "tttxrrRRhhbbbbbm",
            "ttxrrrrrhhbbbbb.",
            "..fffxfnnnnnn...",
            "....gg..........",
            "...gg...........",
            "..gg............",
        ],
    ),
    # --- rifles ---------------------------------------------------------------
    # Bullpup, and it is drawn as one: the carry handle across the crown, and
    # the magazine BEHIND the grip instead of in front of it. Those two facts
    # are the entire difference between this frame and the M4A1-S at a glance,
    # so both are silhouette rather than detail. Bullpup also means there is no
    # stock to draw — the receiver runs all the way to the butt, which is why
    # this is the one rifle here with no seam near its left end.
    (
        "famas",
        {
            "r": POLY, "h": POLY, "b": STEEL, "f": POLY,
            "g": GRIP, "n": POLY, "k": STEEL, "m": STEEL,
        },
        [
            "...kkkkk......",
            "rrrrrRRhhbbbbm",
            "rrxrrrrhhbbbb.",
            ".ffffxff......",
            "..nn.gg.......",
            "..nn.gg.......",
            "..nn..........",
        ],
    ),
    # Wood furniture and a CURVED magazine, walking one column forward as it
    # drops. Nothing else on the sheet is warm across its whole body and
    # nothing else leans, which is why the AK is identifiable in a fist across
    # a clearing. The bakelite mag is warmer still than the furniture, so the
    # two warm masses do not merge into one. The `x` at the left is the seam
    # where the wooden butt meets the receiver, the one on row 2 is the
    # dust-cover seam, and the one on row 3 is the trigger: three recesses,
    # each a single pixel, all load-bearing.
    (
        "ak47",
        {
            "w": WOOD, "r": STEEL, "b": STEEL, "f": STEEL,
            "g": GRIP, "n": TAN, "k": STEEL, "m": STEEL,
        },
        [
            ".......k.......",
            "wwwxrrRRkwwbbbm",
            "wwwxrrrrkwbbbb.",
            ".ffxff.nn......",
            "...gg...nn.....",
            "..gg....nnn....",
            "..g......nn....",
        ],
    ),
    # The AK's twin, told apart by four things and no label: a carry handle on
    # the crown, a STRAIGHT magazine, a polymer stock behind its own seam, and
    # a CAN — the same three-row cylinder the USP-S wears, so the two
    # suppressed weapons in the catalog say it the same way. The can is also
    # why it costs more.
    (
        "m4a1s",
        {
            "t": POLY, "r": POLY, "h": POLY, "c": CAN, "f": POLY,
            "g": GRIP, "n": MAG, "k": STEEL, "m": CAN,
        },
        [
            "...kkkk...cccc.",
            "ttxrrRRhhhccccm",
            "txrrrrrhhhcccc.",
            ".ffxfff........",
            "...gg..nn......",
            "..gg...nn......",
            "..g....nn......",
        ],
    ),
    # --- sniper ---------------------------------------------------------------
    # The longest frame on the sheet, and the only one that spends its crown on
    # an OPTIC. The objective is two pixels of `LENS` at the front of the tube:
    # the sheet's single accent hue, small enough to obey S12 and cool enough
    # that it cannot be mistaken for a muzzle flash. The `x` past the receiver
    # on rows 1-2 is the bolt handle. The barrel runs TWO rows for nine
    # columns, which is the whole point of the weapon expressed as taper.
    (
        "awp",
        {
            "o": OLIVE, "r": STEEL, "b": STEEL, "e": OPTIC, "l": LENS,
            "f": STEEL, "g": GRIP, "n": MAG, "m": STEEL,
        },
        [
            "....eeell.........",
            "ooxrrRRxbbbbbbbbbm",
            "ooxrrrrxbbbbbbbb..",
            ".ooxffff..........",
            "....gg..nn........",
            "...gg...nn........",
            "...g....nn........",
        ],
    ),
    # --- the blade ------------------------------------------------------------
    # The knife, and it is the one frame on this sheet that is not a gun.
    # It is drawn STRAIGHT — handle, crossguard and blade on one line — and
    # that is the whole silhouette decision. Every gun here hangs a grip below
    # its barrel, so a blade with any drop at the back reads as one more pistol
    # no matter what the blade is doing. The crossguard is the only thing that
    # leaves the line, one row above and one below, and those two rows are also
    # what give it thickness: row 0 is its lit crown and row 3 is its shadow
    # side, out of one pixel each.
    #
    # Same bore row as everything else, so swapping to it does not jump the
    # hand, and deliberately the SHORTEST thing on the sheet: length is what
    # this sheet uses to say range, and the weapon you have to walk up to
    # somebody with has to read as short.
    (
        "knife",
        {"b": CHROME, "k": STEEL, "g": GRIP, "m": CHROME},
        [
            "..k.....",
            "ggkbBbbm",
            "ggkbbbb.",
            "..k.....",
            "........",
            "........",
            "........",
        ],
    ),
]

#: How far in front of the body each weapon is carried, and how big it is
#: drawn. Written as the exceptions rather than as extra columns on every
#: row: eleven of the twelve entries are guns held the one way guns are held
#: at the one scale this sheet is authored at, and repeating that eleven times
#: would bury the one row where either is a decision.
HOLD: dict[str, float] = {"knife": HOLD_IN}
#: DRAWN SMALLER THAN IT IS AUTHORED, and the two numbers are answering two
#: different questions.
#:
#: The art above is drawn at one pixel scale because that is what it takes to
#: SAY a weapon: an AK needs its wood, its curved magazine and its dust-cover
#: seam or it is a grey stick, and none of those survive being authored at
#: eleven columns. The same frame in a fist is answering a different question
#: — how big is this thing against the person holding it — and there the full
#: size is wrong: an AK authored at 15 columns is as long as its owner is
#: tall, which reads as a prop being carried rather than a weapon being held.
#:
#: Three quarters is where the barrel stops out-measuring the body and the
#: port, the streak and the magazine are all still there. Below about two
#: thirds the resample starts eating the one-pixel detail the art spends
#: everything on, which is the floor this number sits above rather than a
#: taste boundary.
#:
#: It is applied HERE rather than in the renderer so that one number moves the
#: sprite, the muzzle, the ejection port and the support hand together — they
#: are all the same frame measured from the same grip (`render/guns.ts`).
DRAW_SCALE = 0.75
#: Absolute draw scales for the rows that are not simply `DRAW_SCALE`. The
#: knife is the one entry and it earns it: it is the one thing on this sheet
#: that is not a firearm, and reading smaller than everything on the belt is
#: how a 16px sprite says "sidearm".
SCALE: dict[str, float] = {"knife": 0.65}


def _check(key: str, art: Art) -> None:
    """The invariants the row grid rests on.

    A map that breaks one of the first two is a weapon whose bore has left the
    line, and in game that shows up only as a tracer leaving somebody's hip.
    The third catches a second `m`, which would silently move the tracer
    origin to whichever barrel happened to be drawn lowest.
    """
    if len(art) != ROWS:
        raise ValueError(f"{key}: {len(art)} rows, every weapon is authored at {ROWS}")
    span = max(len(row) for row in art)
    if span > FRAME_W - 2:
        raise ValueError(f"{key}: {span} columns leaves no room for the outline")
    muzzles = [
        (x, y)
        for y, row in enumerate(art)
        for x, cell in enumerate(row)
        if cell.lower() in MUZZLE_CHARS
    ]
    if len(muzzles) != 1:
        raise ValueError(f"{key}: {len(muzzles)} muzzle pixels, the tracer needs one")
    if muzzles[0][1] != 1:
        raise ValueError(f"{key}: muzzle on row {muzzles[0][1]}, the bore is row 1")


def build(args) -> Path:
    width, height = FRAME_W, FRAME_H
    out_dir = PROCESSED_DIR / "guns"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames: list[Image.Image] = []
    items: dict[str, dict] = {}
    # THE ACTION FRAMES ARE APPENDED, never interleaved. Every closed frame
    # keeps the index it has had since this sheet was first packed: a frame
    # index is a number already baked into a committed PNG's meaning, and
    # inserting a row moves all of them (root AGENTS.md).
    cycles: list[tuple[Art, Palette]] = []
    for index, (key, pal, art) in enumerate(GUNS):
        _check(key, art)
        frames.append(_blit(art, pal, width, height))
        cycle = _cycled(art)
        art = _pad(art)
        ox, oy = _origin(art, width, height)
        grip = _centroid(art, GRIP_CHARS, ox, oy)
        muzzle = _rightmost(art, MUZZLE_CHARS, ox, oy)
        items[key] = {
            "frame": index,
            "gripX": grip[0],
            "gripY": grip[1],
            "muzzleX": muzzle[0],
            "muzzleY": muzzle[1],
            "hold": HOLD.get(key, HOLD_OUT),
            "scale": SCALE.get(key, DRAW_SCALE),
        }
        if cycle is None:
            continue
        cycle_art, port = cycle
        # The cycled map is the same padded size as the closed one — the group
        # travels INSIDE the frame — so the two share one origin and the grip
        # does not move between them. A weapon whose pivot jumped on the frame
        # its action opened would fire out of a hand that had let go of it.
        items[key]["cycleFrame"] = len(GUNS) + len(cycles)
        items[key]["portX"] = ox + port[0]
        items[key]["portY"] = oy + port[1]
        cycles.append((cycle_art, pal))
    for cycle_art, cycle_pal in cycles:
        frames.append(_blit(cycle_art, cycle_pal, width, height))

    pack(frames, width, height).save(out_dir / "sheet.png")
    manifest = {
        "tile": args.tile,
        "frameWidth": width,
        "frameHeight": height,
        "frames": len(frames),
        "items": items,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"wrote {out_dir}: {len(GUNS)} weapons + {len(cycles)} action "
        f"frames @ {width}x{height}"
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tile",
        type=int,
        default=DEFAULT_TILE,
        help="must match TILE_SIZE in server/app/config.py",
    )
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
