#!/usr/bin/env python3
"""Asset pipeline: the extraction PLATFORM — the thing that carries loot out.

Everything else in `scenery/` is something people left behind. This is the one
object on the map that answers back, and what it is is a CARGO SKID somebody
abandoned in the woods: a welded iron box open at the front, still half full of
crates nobody came back for, with four masts and lamps. The aircraft are not on
it — they come when the pad calls them.

IT IS A SOLID ON THE WORLD'S OWN CAMERA
The skid and the drone are both rasterised in the 2:1 dimetric every crate,
barrel and fence post in this game stands on — `objects.SLOPE`, `objects.tone`
and the `PLANE_TOP/FRONT/SIDE` table, imported from `make_objects.py` rather
than restated. The skid is a HEIGHT FIELD painted back to front; the drone is
four `objects.box` pods on `objects.billet` arms under one hull. What that
replaced was a front elevation with a continuous value ramp poured down it: a
gradient (S7) through a ditherer (S5) with no top plane anywhere (S3), on the
one object in the game the camera looks down at hardest. See the section
comment over `_skid` for the full argument and for the footprint's axes.

Output (assets/processed/platform/):
    platform.png  3 frames,  80x64  PROP  — the skid: cold, green standby, red
                                            alarm. The mast lamps are the only
                                            thing that changes.
    drone.png     2 frames,  24x16  PROP  — a lift drone, hovering then cruising
    rotor.png     8 frames,  28x12  VFX   — loop: four discs turning
    strobe.png    8 frames,  24x16  VFX   — loop: a drone's nav lights
    standby.png   12 frames, 48x48  VFX   — loop: a corner lamp breathing green
    siren.png     12 frames, 48x48  VFX   — loop: the alarm sweeping red
    imprint.png   1 frame,   80x48  DECAL — the hole in the ground it left
    downwash.png  12 frames, 112x56 VFX   — loop: rotor wash under a straining
                                            platform
    burst.png     12 frames, 128x64 VFX   — one-shot: the ground letting go
    manifest.json

THE DRONES DO NOT LIVE HERE
They used to be parked at the skid's corners, which made the pad look like a
complete machine sitting in the woods waiting to be switched on. It is not one:
it is a LOADING DOCK, and the aircraft come when it calls them. So this file
draws a drone in the two postures a flight has — pitched forward crossing the
clearing, level once it is holding station over its corner — and nothing that
implies one was ever standing on the ground here. The four ropes are the only
part of them the structure owns, and even those are paid out on arrival.

THE THREE SHAPES, THE SAME SPLIT `make_rift.py` DOCUMENTS
`platform` and `drone` are PROPS: baked colour, bottom-anchored, in the depth
sort, multiplied by the night like every trunk on the map. `imprint` is a
DECAL — flat, no outline, drawn `multiply` + `lighter` in two halves so the
soil's own grain reads through the dent. `rotor` / `strobe` / `downwash` /
`burst` are VFX: summed into an intensity field and resolved once, drawn
additively AFTER the darkness pass, because a rotor disc catching the light is
light and not a thing being lit.

WHY THE EYES ARE IN THE MANIFEST
The ropes are drawn LIVE by the client — a rope between a fixed eye and a drone
that climbs, strains and then flies off cannot be a sprite. So the four lift
eyes ship as pixel offsets from the platform's contact point (`layout.eyes`),
in the same order the server places the drones, and both sides read that one
list. Baking a rope into the platform sheet would freeze the one part of this
structure whose whole job is to move. The `ROPE` ramp below is that line's
material and the client plots it PIXEL BY PIXEL out of three of its steps —
see `drawRope` in `client/src/render/layers/rift.ts`.

WHY IT IS IRON AND NOT STONE
This replaced a ring of quarried stones around a tear in the world. The tear
was the odd one out on purpose and the stones were its plumbing; a skid with
crates still in it is the opposite claim — somebody's equipment, left here,
that works again if you feed it. `IRON` therefore comes from `make_rift.py`
rather than being re-typed: the console you press is the same metal as the deck
it is bolted beside, and one game has one steel in it.

Usage:
    python tools/make_platform.py
    python tools/make_platform.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import random
from pathlib import Path

from PIL import Image

from make_textures import (
    BEAM,
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TIMBER,
    TIMBER_OUTLINE,
    TRANSPARENT,
    add,
    clamp01,
    ease_in,
    ease_out,
    ellipse,
    hash01,
    material_ramp,
    pack,
    pick,
    resolve,
    rgb,
)
from make_rift import IRON, SOCKET

#: THE CAMERA, AND IT IS NOT THIS MODULE'S. `objects.SLOPE` is the 2:1 dimetric
#: every crate, barrel and fence post in the world is built on; `objects.tone` is
#: its flat-step painter and `PLANE_TOP/FRONT/SIDE` its plane table. The pad
#: stands in the same clearing as those props, so it is rasterised on the same
#: camera by the same rule — imported, never restated, for the reason spelled out
#: beside them in `make_objects.py`. A structure lit on its own slope is a
#: structure from a different game standing next to one from this one.
import make_objects as objects  # noqa: E402
from make_objects import SLOPE  # noqa: E402

# --- materials ---------------------------------------------------------------
#
# SIX-STEP RAMPS, DERIVED. Everything on this prop is banded on
# `objects.PLANE_TOP` / `PLANE_FRONT` / `PLANE_SIDE`, which are steps 5, 3 and 1
# — so a five-step ramp collapses the top plane into the specular and the deck
# stops being brighter than the wall behind it. Each is `material_ramp` out of
# S11's law (hue, saturation, and where the two ends sit) rather than six typed
# hex triples, so the hue-shift-and-desaturate rule is written once for the whole
# game instead of once per material here.

#: The outline every piece of this structure is keyed with, and the one flat
#: colour left on the sheet. It is only used where the keyline has no material to
#: tint off — inside a lift eye, and under a lamp hood, both of which are HOLES
#: rather than surfaces.
EDGE = rgb("#0a0b0d")

#: Corrosion. Warm, and the only warm thing in the metal — which is what makes it
#: read as AGE rather than as paint: the skid has stood in a wet forest for years
#: and the water ran down from every seam and rivet.
RUST: Ramp = material_ramp(20, 0.44, 0.11, 0.52, steps=6)

#: Hazard paint on the front threshold, half worn off. The one saturated colour
#: on the whole prop and it earns its place: black-and-yellow chevrons are the
#: single most legible way a 16px world can say "machinery, stand clear", and
#: they are what a player picks the pad out by from across a clearing before any
#: of the detail resolves.
HAZARD: Ramp = material_ramp(46, 0.66, 0.13, 0.66, steps=6)

#: The threshold's own steel, a hair warmer than the deck's so the painted lip
#: reads as a separate piece bolted on rather than as a stripe drawn on the box.
LIP: Ramp = material_ramp(30, 0.10, 0.09, 0.36, steps=6)

#: The load. Timber, and darker than the crates out in the clearing on purpose —
#: this lot has been sitting in an open box in the rain for years.
CRATE: Ramp = material_ramp(30, 0.34, 0.08, 0.42, steps=6)
#: A rusted drum on the deck. Shares RUST's hue so the load and the corrosion are
#: one story, and sits a step under it so a drum never out-reads the streaks.
DRUM: Ramp = material_ramp(18, 0.40, 0.08, 0.38, steps=6)

#: A powered fitting. GREEN, because every other light in this game is fire or
#: the beacon's mint, and a machine reporting that it is running must be neither
#: — the console goes gold when the quota lands and the deck must not compete
#: with it.
STATUS: Ramp = material_ramp(146, 0.62, 0.11, 0.86, steps=6)

#: A drone's tail light, and the pad's ALARM lamp. Red, and dim at the bottom: a
#: marker, not a floodlight.
STROBE: Ramp = material_ramp(3, 0.72, 0.10, 0.78, steps=6)

#: What the corner lamps throw into the air, one ramp each. These top out
#: brighter than the baked lamps do, for the same reason `FLAME` does: they are
#: drawn ADDITIVELY after the night multiply, so their job is to be light rather
#: than to be a lit surface, and a glare in the forest's own value range would
#: have nothing left to read as glare.
#:
#: THEY USED TO TOP OUT AT NEAR-WHITE and they no longer do. Four of these ring
#: one small clearing and their sheets OVERLAP; at #e8fff2 and #ffdcd0 the sum
#: went flat white over the pad and took the skid's own banding with it, which is
#: the same failure the shop's eleven torches had. A glare that erases the object
#: it belongs to is not glare, it is fog.
GREEN_GLARE: Ramp = [
    rgb(c) for c in ("#0a2414", "#12522c", "#1c8148", "#43b877", "#7fdcab", "#b4efcd")
]
RED_GLARE: Ramp = [
    rgb(c) for c in ("#250606", "#5e0f0f", "#961919", "#cc3328", "#e8705c", "#f2a795")
]

#: Rope. The client draws the rigging from these rather than from a sprite — see
#: `layout.rope` — so this ramp is the SOURCE for `ROPE_STROKES` in
#: `client/src/render/layers/rift.ts`. Six steps, because the client now plots
#: the line as pixel art with a lit crest, a body and a contact underside rather
#: than as two anti-aliased strokes.
ROPE: Ramp = material_ramp(34, 0.44, 0.09, 0.52, steps=6)

#: What the skid crushed: soil that has been under a tonne of iron for years —
#: pressed flat, dead, and darker than the ground beside it.
#:
#: NOT BLACK. These are multiplied over live terrain, so the ramp only has to
#: take light OUT of the soil — pushed to the bottom of the scale the mark stops
#: reading as pressed ground and starts reading as a hole in the floor, which is
#: the one thing it must not be now that the platform is gone and the party can
#: walk over it.
PRESSED: Ramp = [rgb(c) for c in ("#1b1d16", "#22251b", "#2b2e22", "#353829", "#404432")]
#: Oil, and the grit that came out from under the skid feet.
OIL = rgb("#08080b")
GRIT: Ramp = [rgb(c) for c in ("#3a3428", "#4a4234", "#5b5142")]


# --- the skid ----------------------------------------------------------------
#
# THE PLOT IS 7x7 AND THE SKID IS 5x4 OF IT. The rest is the approach: the tile
# the console stands on, the tile the torch stands on, and a lane down each side
# wide enough for a body to get round the back. A structure that filled its own
# plot would be a wall with a button on it.
#
# IT IS BUILT AS A SOLID NOW, ON THE WORLD'S OWN CAMERA.
# What this replaced was a FRONT ELEVATION with a value ramp poured down it: a
# table of row landmarks, a silhouette half-width per row, and `pick(IRON,
# <continuous shade>)` over the lot. Three things followed and every one of them
# is something PIXEL-ART-DIRECTION.md rules out —
#
#   * a continuous shade is a gradient (S7), and a gradient through `pick` is a
#     dither (S5), so no surface on the prop had a value of its own and no fold
#     between two surfaces had an edge;
#   * an elevation has no TOP PLANE, and the top plane is 35-45% of a prop's
#     silhouette on this camera (S3) and the strongest depth cue it has (S18).
#     The deck of a cargo platform is the one surface the whole object is ABOUT
#     and it was drawn as a lighter part of the wall behind it;
#   * `abs(u)` shading is symmetric about the object's centre line, which is a
#     light source sitting behind the camera. The key is at 135deg (S8) and
#     everything else in this game is lit by it.
#
# So the skid is now a HEIGHT FIELD rasterised in the same 2:1 dimetric the
# crates, barrels and fence posts stand on — `objects.SLOPE`, `objects.tone` and
# the `PLANE_TOP/FRONT/SIDE` table, imported rather than restated, for exactly
# the reason those are public. The pad is a man-made box standing in the same
# clearing as the crates; if it is not on their camera it is a matte painting
# they are standing in front of.
#
# THE FOOTPRINT AXES. `a` runs up-LEFT and `b` runs up-RIGHT, both in screen
# pixels, so a cell (a, b) lands at
#
#     x = cx - a + b          y = base - (a + b) * SLOPE - z
#
# and the four corners of the box are NEAR (0,0), LEFT (A,0), RIGHT (0,B) and
# FAR (A,B). The camera looks into the near corner, which is why the two FAR
# walls are the ones the player sees the inside of and the two NEAR edges are
# low lips you can see over. That is a cargo skid with its front dropped, and it
# is the same read the old elevation was reaching for with a taper.
#
# A face pointing -b faces down-LEFT on screen and is therefore the KEY face; a
# face pointing -a faces down-RIGHT and is the SHADE face. Those two lines are
# the entire lighting model and they are the same two `objects.box` uses.

PLATFORM_TILES_W = 5
PLATFORM_TILES_H = 4

#: THREE STATES, AND THE CORNER LAMPS ARE THE WHOLE DIFFERENCE BETWEEN THEM.
#: Cold is a dead machine in the woods. STANDBY is green — found, powered, safe
#: to load, and green because green is the only colour in this game that has
#: ever meant "nothing is wrong". ALARM is red, and it means the party has
#: called for a pickup: from that press the pad is a siren in a dark forest and
#: every creature on the map is walking toward it.
#:
#: STATES, never variants — the frame index says what the machine is doing, and
#: rolling one would make the pad flicker between calm and emergency.
PLATFORM_STATES = 3
PLATFORM_COLD, PLATFORM_STANDBY, PLATFORM_ALARM = range(PLATFORM_STATES)

#: Cruising and holding station. The drones are not part of the structure any
#: more — they fly in from off-map when the pad calls them — so there is no
#: parked pose to draw. A machine crossing a clearing at speed is PITCHED
#: FORWARD and one holding a hover is level, and those two silhouettes are the
#: only thing that says which it is doing at 24 pixels.
DRONE_STATES = 2
DRONE_HOVER, DRONE_CRUISE = range(DRONE_STATES)

#: Four lift points, and THE ORDER IS THE CONTRACT — `layout.eyes` here and
#: `server/app/rift.py`'s corner order are one list. It runs on the DIAGONAL:
#: entry 0 is opposite entry 1 and entry 2 is opposite entry 3, so a rig
#: part-way through tying on is holding opposite sides of the deck and the load
#: hangs level instead of hinging.
DRONES = 4

ROTOR_FRAMES = 8
ROTOR_FPS = 24
STROBE_FRAMES = 8
STROBE_FPS = 8
#: The calm lamp: a slow breath, closer to a pilot light than to a signal.
STANDBY_FRAMES = 12
STANDBY_FPS = 10
#: The siren: a bar of light going round, fast, with a hard leading edge. It is
#: the loudest thing this generator draws and it is meant to be.
SIREN_FRAMES = 12
SIREN_FPS = 16
DOWNWASH_FRAMES = 12
DOWNWASH_FPS = 12
BURST_FRAMES = 12
BURST_FPS = 18

#: The box, as fractions of the sprite. UNEQUAL ON PURPOSE: `objects` documents
#: that a footprint with equal left and right runs is a diamond, and a diamond
#: is a gem rather than a rectangle seen in perspective. Everything else on this
#: prop is derived from these two numbers so the structure re-proportions with
#: `--tile` instead of drifting apart.
FOOT_LEFT = 0.375
FOOT_RIGHT = 0.425
#: Deck, wall and post, in fractions of the frame height. The deck is a SLAB the
#: box sits on rather than a floor drawn inside it — a platform whose deck is
#: level with the ground is a rug.
DECK_RISE = 0.094
WALL_RISE = 0.203
POST_RISE = 0.266
#: Thickness of a wall and of the front lip, in footprint pixels.
WALL_THICK = 5
#: How far along its edge each post stands, from the NEAR corner.
#:
#: NOT THE MIDPOINT, and not the corner either, and both of those were tried. At
#: 45 degrees of yaw a box's four corners project to leftmost, rightmost, top and
#: bottom — so corner posts put two of the four ropes on the same screen column,
#: one above the other, and the client stations both of their drones out to the
#: same side. Edge midpoints fix the stacking and leave the four x offsets in two
#: tight pairs. Two thirds back along each edge is the arrangement that spreads
#: all four across the frame while keeping the diagonal pairing the load needs.
POST_ALONG = 0.65
LIP_RISE = 0.047


def _skid(width: int, height: int) -> dict:
    """Every number the skid is built from, derived once.

    `base` is the NEAR corner's contact row and everything else hangs off it.
    Kept as one dict rather than as constants so the sprite re-proportions with
    `--tile`: a structure authored in absolute pixels at one tile size is a
    structure that comes apart at another.
    """
    left = round(width * FOOT_LEFT)
    right = round(width * FOOT_RIGHT)
    return {
        # INTEGER, and that is not a rounding detail. With a half-pixel centre
        # every screen column of the raster lands on x.5 and `round` breaks the
        # tie to EVEN — so alternate columns of the dimetric grid collapsed onto
        # each other and the skid came out combed into vertical stripes. A 2:1
        # grid has to be laid on whole pixels at both ends (S4: strict 1:1 pixel
        # grid, zero sub-pixel work).
        "cx": width // 2,
        # Room under the near corner for the contact band and the cast shadow
        # (S9, S19) — without it the box stands on the bottom edge of its own
        # frame and the shadow has nowhere to land.
        "base": height - 1 - round(height * 0.078),
        "A": left,
        "B": right,
        "deck": max(3, round(height * DECK_RISE)),
        "wall": max(6, round(height * WALL_RISE)),
        "post": max(8, round(height * POST_RISE)),
        "lip": max(2, round(height * LIP_RISE)),
    }


def _eyes(width: int, height: int) -> tuple[tuple[float, float], ...]:
    """The four lift eyes, in pixels from the sprite's top-left.

    ON THE EDGE MIDPOINTS, NOT ON THE CORNERS. At 45 degrees of yaw one of a
    box's four corners is the NEAR one, and a post standing on it is a bar down
    the middle of the opening — it hides the load, which is the one thing on
    this prop that tells a party the machine carries things. Mid-edge posts ring
    the rim instead, and the diagonal pairing survives: 0 is opposite 1 across
    the b axis, 2 is opposite 3 across the a axis.
    """
    s = _skid(width, height)
    cx, base = s["cx"], s["base"]
    A, B = s["A"], s["B"]
    top = s["deck"] + s["post"]

    def at(a: float, b: float) -> tuple[float, float]:
        return (cx - a + b, _row(base - (a + b) * SLOPE - top))

    return (
        at(A * POST_ALONG, 0.0),   # the near-left lip
        at(A * POST_ALONG, B),     # the far-right wall — opposite it
        at(0.0, B * POST_ALONG),   # the near-right lip
        at(A, B * POST_ALONG),     # the far-left wall — opposite that
    )


#: What a cell of the height field is made of. The region decides the RAMP and
#: nothing else — the plane comes from the geometry, which is the whole point of
#: rasterising a solid instead of painting a picture of one.
REGIONS: dict[str, Ramp] = {
    "deck": IRON,
    "wall": IRON,
    "post": IRON,
    "lip": LIP,
    "crate": CRATE,
    "drum": DRUM,
}


def _column(field: dict, a: int, b: int, z: int, region: str) -> None:
    """Raise the field at (a, b) to `z`, keeping the taller claim."""
    if a < 0 or b < 0:
        return
    have = field.get((a, b))
    if have is None or z >= have[0]:
        field[(a, b)] = (z, region)


def _slab(field: dict, a0: int, a1: int, b0: int, b1: int, z: int,
          region: str) -> None:
    """A rectangular block of the footprint raised to one height."""
    for a in range(a0, a1 + 1):
        for b in range(b0, b1 + 1):
            _column(field, a, b, z, region)


def _build_field(s: dict) -> dict:
    """The skid as a height field: deck, two back walls, two front lips, posts.

    Back to front in construction order, which is also the order somebody would
    weld it: a slab, the walls that stand on the slab, the lips that close the
    open side, then the posts the ropes get tied to.
    """
    A, B = s["A"], s["B"]
    deck, wall, post, lip = s["deck"], s["wall"], s["post"], s["lip"]
    field: dict[tuple[int, int], tuple[int, str]] = {}

    # The slab. Its top face IS the deck — there is no separate floor drawn
    # inside a box, because on this camera the inside of a box IS its top face.
    _slab(field, 0, A, 0, B, deck, "deck")

    # The two far walls, standing on the slab and meeting at the FAR corner.
    _slab(field, A - WALL_THICK + 1, A, 0, B, deck + wall, "wall")
    _slab(field, 0, A, B - WALL_THICK + 1, B, deck + wall, "wall")

    # The two near lips: low enough to see the load over, high enough that the
    # deck reads as a container rather than as a tray.
    _slab(field, 0, WALL_THICK - 2, 0, B, deck + lip, "lip")
    _slab(field, 0, A, 0, WALL_THICK - 2, deck + lip, "lip")

    _cargo(field, s)

    # The posts, last, so they stand proud of whatever they are bolted to. Three
    # cells square: at one cell a post renders in a single screen column and has
    # to fake both of its faces into the same pixel, which is what makes a thin
    # upright read as a scratch rather than as a mast.
    along_a, along_b = int(A * POST_ALONG), int(B * POST_ALONG)
    for a, b in ((along_a, 0), (along_a, B), (0, along_b), (A, along_b)):
        for da in range(-1, 2):
            for db in range(-1, 2):
                _column(field, a + da, b + db, deck + post, "post")
    return field


def make_platform(width: int, height: int, state: int, rng: random.Random) -> Image.Image:
    """One skid. PROP: baked colour, bottom-anchored, lit by the night.

    Rasterised as a solid (see the section comment), then dressed: corrosion
    running DOWN from the seams because water does, rivets along the folds, a
    stencil on the biggest flat area, hazard chevrons on the threshold, the
    corner lamps that carry the state, and the contact band and cast shadow that
    put it on the floor.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    s = _skid(width, height)
    field = _build_field(s)
    plan = _raster(px, (width, height), field, s)

    _weather(px, plan, width, height, rng)
    _rivets(px, plan, s, width)
    _stencil(px, plan, s, width, height)
    _chevrons(px, plan, s, width, height)
    _lamps(px, plan, s, width, height, state)
    _contact(px, plan, width, height)
    _key(px, plan, width, height)
    objects.shadow(img, s["cx"] + width * 0.05, s["base"] + height * 0.035,
                   width * 0.44, height * 0.075)
    return img


def _row(value: float) -> int:
    """A dimetric row, rounded HALF UP.

    `round` in Python breaks a .5 tie toward the even integer, and half of this
    grid lands on exactly .5 — a cell with `a + b` odd sits half a pixel between
    two rows. Banker's rounding sends two neighbouring cells to the same row and
    leaves the next one empty, which reads as a comb of vertical stripes down the
    whole prop rather than as a surface.
    """
    return int(math.floor(value + 0.5))


#: Plane -> ramp step, straight off `make_objects`. Named again here only
#: because the rasteriser reads them on every pixel and `objects.PLANE_TOP` at
#: that rate buries the geometry under attribute lookups.
TOP, FRONT, SIDE = objects.PLANE_TOP, objects.PLANE_FRONT, objects.PLANE_SIDE


def _raster(px, size: tuple[int, int], field: dict, s: dict) -> dict:
    """Paint the height field back to front. Returns the per-pixel plan.

    PAINTER'S ALGORITHM ON THE DIAGONAL. Cells are drawn in descending `a + b`,
    so a near mass overwrites the far one it stands in front of and the 1px
    occlusion seam S18 asks for falls out of the draw order rather than being
    painted on afterwards. Each cell contributes ONE top-face pixel and a run of
    side-face pixels down to whatever the cell in front of it reaches — which is
    what makes a wall standing on a slab draw its own face and stop, instead of
    running to the floor through the slab.
    """
    width, height = size
    cx, base = s["cx"], s["base"]
    plan: dict[tuple[int, int], tuple[Ramp, int]] = {}

    def put(x: int, y: int, ramp: Ramp, step: int) -> None:
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = objects.tone(ramp, step, x, y)
            plan[(x, y)] = (ramp, step)

    for (a, b) in sorted(field, key=lambda cell: -(cell[0] + cell[1])):
        z, region = field[(a, b)]
        ramp = REGIONS[region]
        x = cx - a + b
        y_top = _row(base - (a + b) * SLOPE - z)
        put(x, y_top, ramp, TOP)

        near = field.get((a - 1, b - 1))
        near_z = near[0] if near else 0
        y_bot = _row(base - (a + b - 2) * SLOPE - near_z) - 1
        if y_bot < y_top:
            continue
        # Which of the two near faces this run is showing. -b points down-left
        # into the key (S8), -a points down-right away from it. When a mass has
        # both open — a free-standing post — the pixel is the corner between
        # them, and the side of the sprite it is on decides which one wins.
        lit = (a, b - 1) not in field or field[(a, b - 1)][0] < z
        shade = (a - 1, b) not in field or field[(a - 1, b)][0] < z
        if lit and shade:
            plane = FRONT if x <= cx else SIDE
        else:
            plane = FRONT if lit else SIDE
        for y in range(y_top + 1, y_bot + 1):
            put(x, y, ramp, plane)
    return plan


def _cargo(field: dict, s: dict) -> None:
    """What is still in it. SCENERY, and it never changes.

    The box is not a container the game tracks — nothing fed into the pad goes in
    here and nothing comes out. It is there to say the skid was loaded once and
    abandoned loaded, which is what makes a party believe the thing can carry
    their bag. Raised into the same height field as the structure, so a crate is
    a SOLID standing on the deck and gets its own top face and its own occlusion
    seam rather than being a rectangle painted on the floor.

    DELIBERATELY NOT FULL. The gap in the middle of the deck is where the eye
    goes; a load packed wall to wall reads as a texture.
    """
    A, B = s["A"], s["B"]
    deck = s["deck"]
    unit = max(4, A // 7)

    def crate(a: int, b: int, da: int, db: int, tall: int, region: str) -> None:
        _slab(field, a, a + da, b, b + db, deck + tall, region)

    crate(A - unit * 4, B - unit * 4, unit * 2, unit * 2, unit * 3, "crate")
    crate(A - unit * 5, B - unit * 6, unit, unit + 1, unit * 2, "crate")
    crate(unit, B - unit * 3, unit + 1, unit + 1, unit * 2, "drum")
    crate(A - unit * 3, unit, unit + 1, unit, unit + 1, "crate")
    crate(unit * 2, unit * 2, unit, unit, unit, "drum")


def _weather(px, plan: dict, width: int, height: int, rng: random.Random) -> None:
    """Corrosion, and it RUNS DOWNWARD because water does.

    A streak that starts anywhere but a seam or an edge reads as brown paint,
    which is the failure mode of every weathered-metal sprite. Each run is a
    CLUSTER of two or three pixels wide at one exact ramp step (S5: texture is
    clustered shape, never scattered noise) — the per-pixel `hash01` grain this
    replaced put a single stray pixel of the neighbouring step on every face of
    the prop, which is the dither S5 exists to forbid.
    """
    starts = [
        (x, y) for (x, y), (ramp, step) in plan.items()
        if ramp is IRON and step == TOP and (x + y) % 7 == 0
    ]
    rng.shuffle(starts)
    for sx, sy in starts[: max(8, width // 4)]:
        run = rng.randint(2, max(3, height // 10))
        wide = rng.randint(1, 2)
        step = rng.choice((2, 3))
        for down in range(1, run + 1):
            for across in range(wide):
                x, y = sx + across, sy + down
                cell = plan.get((x, y))
                if cell is None or cell[0] is not IRON:
                    break
                if cell[1] == TOP:
                    continue
                px[x, y] = objects.tone(RUST, step if down < run - 1 else 1, x, y)
                plan[(x, y)] = (RUST, step)


def _rivets(px, plan: dict, s: dict, width: int) -> None:
    """Two pixels each: a light one and the shadow under it.

    One pixel is a speck; three is a bolt head the size of a fist at this scale.
    They go on the TOP faces only — a rivet is a thing standing proud of a
    surface, and the only surface this camera can see a proud thing on is the
    one pointing at the sky.
    """
    step = max(5, width // 11)
    for (x, y), (ramp, plane) in list(plan.items()):
        if ramp is not IRON or plane != TOP:
            continue
        if x % step or y % 3:
            continue
        px[x, y] = objects.tone(IRON, min(TOP, len(IRON) - 1), x, y)
        under = plan.get((x, y + 1))
        if under is not None and under[0] is IRON:
            px[x, y + 1] = objects.tone(IRON, 0, x, y + 1)
            plan[(x, y + 1)] = (IRON, 0)


def _stencil(px, plan: dict, s: dict, width: int, height: int) -> None:
    """A painted block on the inside of a wall, half gone.

    It carries no information and is not meant to: it is there so the biggest
    flat area on the prop has something on it, and so the box reads as a
    numbered unit out of a fleet rather than as a one-off somebody welded in a
    shed. Drawn as a value step on the wall's own ramp (S6: interior form breaks
    are value steps, never lines).
    """
    A, B = s["A"], s["B"]
    cx, base = s["cx"], s["base"]
    deck, wall = s["deck"], s["wall"]
    for block in range(4):
        a = A - WALL_THICK
        b = int(B * 0.30 + block * B * 0.12)
        x = cx - a + b
        y = _row(base - (a + b) * SLOPE - deck - wall * 0.45)
        for oy in range(max(2, height // 20)):
            for ox in range(max(2, width // 34)):
                cell = plan.get((x + ox, y + oy))
                if cell is None or cell[0] is not IRON or cell[1] == TOP:
                    continue
                if hash01(x + ox, y + oy, 3301) < 0.30:
                    continue
                px[x + ox, y + oy] = objects.tone(IRON, TOP - 1, x + ox, y + oy)


def _chevrons(px, plan: dict, s: dict, width: int, height: int) -> None:
    """Hazard paint on the threshold, worn.

    The one saturated colour on the whole prop and it earns its place: black and
    yellow chevrons are the single most legible way a 16px world can say
    "machinery, stand clear", and they are what a player picks the pad out by
    from across a clearing before any of the detail resolves. On the LIP's top
    face, because that is the surface somebody would actually have painted and
    the only one the camera sees square on.

    The wear is what keeps them from reading as a decal: a clean stripe on a
    rusted box is a sticker applied yesterday. It is a clustered mask on a 2x2
    lattice, not per-pixel noise (S5).
    """
    for (x, y), (ramp, plane) in list(plan.items()):
        if ramp is not LIP or plane != TOP:
            continue
        if (x + y * 2) % 8 >= 4:
            continue
        if hash01(x // 2, y // 2, 2711) < 0.22:
            continue
        px[x, y] = objects.tone(HAZARD, TOP - 1, x, y)
        plan[(x, y)] = (HAZARD, TOP - 1)


def _lamps(px, plan: dict, s: dict, width: int, height: int, state: int) -> None:
    """The eye a rope goes through, and the lamp in a hood under it.

    THE LAMPS ARE THE PAD'S WHOLE VOCABULARY. Dead, green, red, and each one is
    the entire state of the night in two pixels seen from across a clearing:
    nobody has been here; this one is open for business; this one has called for
    a pickup and is screaming about it. They are baked because a prop's colour is
    its material — the GLARE around them is additive and lives in `standby.png` /
    `siren.png`, because light is not a thing being lit.

    The eye is a RING WITH A HOLE PUNCHED THROUGH IT so it reads as something a
    rope goes THROUGH; a filled knob is a bolt, and a rope tied to a bolt looks
    glued on. The hole is keyed rather than left transparent — a gap in the
    sprite would let the forest through a piece of solid iron.
    """
    ring = max(2.0, width / 26.0)
    hood = max(1, int(round(width / 40.0)))
    for ex, ey in _eyes(width, height):
        col, row = int(round(ex)), int(round(ey)) - int(ring) - 1
        for oy in range(-int(ring) - 1, int(ring) + 2):
            for ox in range(-int(ring) - 1, int(ring) + 2):
                x, y = col + ox, row + oy
                if not (0 <= x < width and 0 <= y < height):
                    continue
                d = math.hypot(ox, oy * 1.15)
                if d > ring:
                    continue
                if d < ring - 1.6:
                    px[x, y] = EDGE
                    plan[(x, y)] = (IRON, 0)
                else:
                    step = TOP if oy <= 0 and ox <= 0 else (FRONT if ox <= 0 else SIDE)
                    px[x, y] = objects.tone(IRON, step, x, y)
                    plan[(x, y)] = (IRON, step)
        lamp_y = int(round(ey)) + 1
        for ox in range(-hood - 1, hood + 2):
            x = col + ox
            if not (0 <= x < width and 0 <= lamp_y < height):
                continue
            if 0 <= lamp_y - 1 < height:
                px[x, lamp_y - 1] = EDGE
                plan[(x, lamp_y - 1)] = (IRON, 0)
            if abs(ox) > hood:
                continue
            if state == PLATFORM_COLD:
                px[x, lamp_y] = SOCKET
                plan[(x, lamp_y)] = (IRON, 1)
                continue
            ramp = STATUS if state == PLATFORM_STANDBY else STROBE
            px[x, lamp_y] = ramp[len(ramp) - 1 - abs(ox)]
            plan[(x, lamp_y)] = (ramp, len(ramp) - 1 - abs(ox))


def _contact(px, plan: dict, width: int, height: int) -> None:
    """The 1-2px band where the mass meets the ground, INSIDE the sprite (S10).

    Above the cast shadow, never part of it, and the darkest thing on the object
    (S19). It is drawn from the plan rather than from a row number because the
    skid's contact line is a rhombus and not a row: the near corner touches down
    thirty rows below the left and right ones.
    """
    for (x, y), (ramp, step) in list(plan.items()):
        if (x, y + 1) in plan or step == TOP:
            continue
        px[x, y] = objects.tone(ramp, 0, x, y)
        plan[(x, y)] = (ramp, 0)
        above = plan.get((x, y - 1))
        if above is not None and above[1] not in (TOP, 0):
            px[x, y - 1] = objects.tone(above[0], 1, x, y - 1)
            plan[(x, y - 1)] = (above[0], 1)


def _key(px, plan: dict, width: int, height: int) -> None:
    """S6's keyline: 1px, hue-tinted off the material, gone on the lit crest.

    Only the outer boundary — outlining every internal surface draws the object
    as a wireframe, and the folds are already carried by the value breaks between
    the surfaces themselves. The colour comes off whatever it is keying rather
    than being one flat near-black for the whole prop, so rusted steel, painted
    hazard yellow and bare timber each carry their own edge; and where the key
    light lands on a top face the line drops entirely, because a border competing
    with the brightest step in a ramp is what makes a prop look traced.
    """
    edges: dict[tuple[int, int], RGBA] = {}
    for y in range(height):
        for x in range(width):
            if px[x, y][3] != 0:
                continue
            below = plan.get((x, y + 1))
            above = plan.get((x, y - 1))
            if below is not None and below[1] >= TOP and above is None:
                continue
            best = None
            contact = False
            for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1)):
                near = plan.get((x + dx, y + dy))
                if near is None:
                    continue
                if best is None or near[1] < best[1]:
                    best = near
                if (dx, dy) == (0, -1):
                    contact = True
            if best is None:
                continue
            edges[(x, y)] = _tint(best[0][0], -0.45 if contact else -0.22)
    for (x, y), colour in edges.items():
        px[x, y] = colour


def _tint(colour: RGBA, light: float) -> RGBA:
    """A ramp's darkest step pushed further down and round toward blue (S6)."""
    red, green, blue, alpha = colour
    hue, lightness, sat = colorsys.rgb_to_hls(red / 255.0, green / 255.0, blue / 255.0)
    hue = ((hue * 360.0 - 15.0) % 360.0) / 360.0
    out = max(0.0, min(1.0, lightness * (1.0 + light)))
    r2, g2, b2 = colorsys.hls_to_rgb(hue, out, min(1.0, sat * 1.10))
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255), alpha)


# --- the drones --------------------------------------------------------------
#
# ONE MACHINE, ON THE SAME CAMERA AS THE SKID IT LIFTS. What this replaced was
# four soft ellipses and a `pick(IRON, <continuous shade>)` falloff away from
# the hull's centre — a radial gradient through a ditherer, so an aircraft
# twenty-four pixels wide had no plane on it anywhere and read as a smudge with
# two coloured pixels in it. Built out of `objects.box` and `objects.billet`
# instead, it is a HULL, four PODS and four ARMS, each one a solid with a top
# face and two flanks, banded on the world's own plane table.
#
# THE POSTURE IS THE STATE AND THE ONLY STATE. Cruise is pitched nose-down —
# the only way a multirotor goes anywhere and the only way this silhouette can
# say it is travelling — and hover is level and holding station. On this camera
# a pitch is a SHEAR of the pod ring: the far pair lifts and the near pair
# drops, which is what a tilted disc does, and it costs two pixels.
#
# The blades are never drawn in either pose. That is `rotor`'s job (a smear, not
# a shape), because a drone whose props are painted on is a drone that never
# actually spins.


#: Where the four motor pods sit, as fractions of the frame. Wider than it is
#: deep, because on a high 3/4 camera a square plan foreshortens to a rhombus
#: half as tall as it is wide (S1) — a pod ring drawn square reads as a drone
#: seen from directly above, which is a camera this game does not have.
POD_SPREAD_X = 0.34
POD_SPREAD_Y = 0.15
#: How far the cruise pose shears the ring. Small on purpose: past about a fifth
#: of the pod spread the aircraft stops reading as tilted and starts reading as
#: broken.
CRUISE_PITCH = 0.42


def make_drone(width: int, height: int, state: int) -> Image.Image:
    """One lift drone. PROP, drawn in the AIR pass — it never touches the floor.

    Solids, back to front: the two far pods and their arms, then the hull over
    them, then the two near pods, so the near ones cut into the hull and the
    hull cuts into the far ones. That overlap is the depth cue (S18) and it is
    the only one an aircraft gets — there is no ground under it to cast onto.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)
    cruise = state == DRONE_CRUISE
    cx = width // 2
    # Rides a little higher in its own frame when it is travelling: nothing is
    # under it and the tail is up.
    cy = height * (0.46 if cruise else 0.52)
    sx = width * POD_SPREAD_X
    sy = height * POD_SPREAD_Y
    pitch = sy * CRUISE_PITCH if cruise else 0.0

    #: (x, y, far?) — far pair first so the painter's order is the draw order.
    pods = [
        (cx - sx, cy - sy - pitch, True),
        (cx + sx, cy - sy - pitch, True),
        (cx - sx, cy + sy + pitch, False),
        (cx + sx, cy + sy + pitch, False),
    ]

    def arm(pod_x: float, pod_y: float, far: bool) -> None:
        """A boom from the hull out to a pod. A cylinder, so `billet` draws it."""
        x0, x1 = (min(pod_x, cx), max(pod_x, cx))
        axis = (pod_y + cy) / 2.0
        objects.billet(px, size, x0, x1, axis, max(1.2, height * 0.075),
                       IRON, cap=False)

    def pod(pod_x: float, pod_y: float) -> None:
        """A motor can: a short box with a lid, wider than it is tall."""
        objects.box(px, size, pod_x, pod_y + height * 0.09,
                    width * 0.075, width * 0.075, height * 0.10, IRON)

    for pod_x, pod_y, far in pods:
        if far:
            arm(pod_x, pod_y, far)
            pod(pod_x, pod_y)
    # The hull. Unequal left and right runs — a footprint with `lw == rw` is a
    # diamond, and a diamond is a gem (see `make_objects`).
    objects.box(px, size, cx, cy + height * 0.16,
                width * 0.155, width * 0.185, height * 0.24, IRON)
    for pod_x, pod_y, far in pods:
        if not far:
            arm(pod_x, pod_y, far)
            pod(pod_x, pod_y)

    # The winch, under the hull. Without something for a line to come out of, a
    # rope appearing below a drone reads as a bug rather than as rigging.
    objects.billet(px, size, cx - width * 0.05, cx + width * 0.05,
                   cy + height * 0.21, max(1.2, height * 0.065), IRON, cap=False)

    plan = _survey(px, width, height)
    # Nav lights: green forward, red aft. Two pixels each, and the only thing on
    # a 24px sprite that says which way it is facing — which matters far more now
    # that these arrive across a clearing instead of sitting still.
    for index, (pod_x, pod_y, far) in enumerate(pods):
        ramp = STATUS if not far else STROBE
        x, y = int(round(pod_x)), int(round(pod_y - height * 0.02))
        if plan.get((x, y)) is not None:
            px[x, y] = ramp[len(ramp) - 2]
            plan[(x, y)] = (ramp, len(ramp) - 2)
    # A lit eye on the hull, so a drone still reads as switched on when its
    # rotors are lost against the treeline.
    hx, hy = cx, int(round(cy))
    if plan.get((hx, hy)) is not None:
        px[hx, hy] = STATUS[len(STATUS) - 3]
        plan[(hx, hy)] = (STATUS, len(STATUS) - 3)

    _key(px, plan, width, height)
    return img


def _survey(px, width: int, height: int) -> dict:
    """Recover the per-pixel plan from a frame the volume toolkit painted.

    `objects.box` / `objects.billet` write pixels and keep no record of which
    plane each one landed on, and `_key` needs that to tint a keyline off the
    material it is keying (S6). Reading the colours back and matching them to
    `IRON` is exact rather than approximate: `objects.tone` lands on a ramp step
    and nothing on this sprite is between two of them, which is the whole point
    of banding instead of dithering.
    """
    plan: dict[tuple[int, int], tuple[Ramp, int]] = {}
    index = {colour[:3]: step for step, colour in enumerate(IRON)}
    for y in range(height):
        for x in range(width):
            pixel = px[x, y]
            if not pixel[3]:
                continue
            step = index.get(pixel[:3])
            plan[(x, y)] = (IRON, step if step is not None else 2)
    return plan


def make_rotor_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """Four turning discs. VFX: additive, over the drone, after the darkness.

    A ROTOR IS NOT A SHAPE, IT IS A SMEAR. Drawing blades and stepping them
    round strobes horribly at any frame rate a sprite sheet can afford — so
    what is drawn is the disc the blades sweep, faint, with one bright arc
    running round it. The arc carries the speed; the disc carries the fact that
    something is there at all.

    LOOPS: every term is a function of the frame phase, so the last frame hands
    back to the first with nothing to snap.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    phase = index / total
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    arm = width * 0.32
    reach = height * 0.30
    pods = (
        (cx - arm, cy - reach), (cx + arm, cy - reach),
        (cx - arm, cy + reach), (cx + arm, cy + reach),
    )
    rx, ry = width * 0.21, height * 0.22
    for pod, (pod_x, pod_y) in enumerate(pods):
        # The faint disc.
        ellipse(field, pod_x, pod_y, rx, ry, 0.30, hollow=0.55)
        ellipse(field, pod_x, pod_y, rx * 0.55, ry * 0.55, 0.10)
        # The arc. Counter-rotating pairs, like a real quad — diagonal
        # neighbours turn the same way, so the four are never in lockstep.
        spin = 1.0 if pod in (0, 3) else -1.0
        base = (phase * spin + pod * 0.25) * math.tau
        for step in range(9):
            a = base + step * 0.16 * spin
            fade = 1.0 - step / 9.0
            x = int(round(pod_x + math.cos(a) * rx * 0.92))
            y = int(round(pod_y + math.sin(a) * ry * 0.92))
            add(field, x, y, 0.85 * fade)
            add(field, x, y + 1, 0.30 * fade)
    resolve(field, img, BEAM, floor=0.06, tone=0.80, gain=0.72)
    return img


def make_strobe_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """A live drone's nav lights, blinking. VFX, additive, over the drone.

    THE BLINK IS WHY THIS IS A SHEET AND NOT A BAKED PIXEL. Four drones on the
    same rig, each offset around this loop by the client, is what turns a row
    of switched-on props into machinery with power running through it — and a
    blink is the one signal that reads at any zoom and through the dark.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    phase = index / total
    cx = (width - 1) / 2.0
    cy = height * 0.44
    arm = width * 0.375
    reach = height * 0.22
    # A sharp pulse, not a sine: a marker light snaps on and decays.
    pulse = ease_out(clamp01(1.0 - (phase % 0.5) * 3.4))
    lead = 1.0 if phase < 0.5 else 0.35
    corners = (
        (cx - arm, cy - reach), (cx + arm, cy - reach),
        (cx - arm, cy + reach), (cx + arm, cy + reach),
    )
    for i, (sx, sy) in enumerate(corners):
        gain = pulse * (lead if i < 2 else 1.35 - lead)
        if gain <= 0.02:
            continue
        ellipse(field, sx, sy, width * 0.13, height * 0.13, 0.75 * gain)
        add(field, int(round(sx)), int(round(sy)), 0.55 * gain)
    resolve(field, img, BEAM, floor=0.06, tone=0.85, gain=0.62)
    return img


# --- the corner lamps ----------------------------------------------------------
#
# TWO SHEETS, NOT ONE WITH A TINT, and the reason is that they are not the same
# light doing different colours — they are different KINDS of light.
#
# Standby breathes. It is a lamp somebody left on, and everything about it is
# soft: no edge, no rhythm you could count, a glare that is always there and
# never demands anything. It says the pad is found and working.
#
# The siren SWEEPS. A hard bar of light going round with a bright leading edge
# and a dark side, fast enough that you catch it out of the corner of your eye
# from across a clearing. It says the party has just told the whole forest
# where they are, which is the single most dangerous thing they can do on a
# night, and it has to feel like that before a single zombie has moved.
#
# A draw-time tint could turn one of these into the other's colour and never
# into its shape, which is the same argument every `tinted: false` sheet in
# this game makes.


def _lamp_field(width: int, height: int):
    return [[0.0] * width for _ in range(height)]


def make_standby_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """The calm lamp, breathing. VFX, additive, LOOPING.

    A sine of the frame phase and nothing else, so the wrap cannot snap. It is
    deliberately the quietest sheet this generator writes: the pad spends most
    of the night in this state and a glare that pulsed hard would turn the
    place a party works at into a place a party is warned away from.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = _lamp_field(width, height)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    beat = 0.72 + 0.28 * math.sin(index / total * math.tau)
    ellipse(field, cx, cy, width * 0.44, height * 0.44, 0.34 * beat)
    ellipse(field, cx, cy, width * 0.20, height * 0.20, 0.55 * beat)
    add(field, int(round(cx)), int(round(cy)), 0.50 * beat)
    resolve(field, img, GREEN_GLARE, floor=0.06, tone=0.86, gain=0.58)
    return img


def make_siren_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """The alarm, sweeping. VFX, additive, LOOPING.

    A ROTATING BAR, not a flash. A lamp that simply blinks reads as a fault
    light; a beam going round reads as a machine broadcasting, and broadcasting
    is exactly what has just happened — the pad has called for a pickup and
    every creature on this map heard it.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = _lamp_field(width, height)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    angle = (index / total) * math.tau
    reach = width * 0.70

    # The bulb never goes out — a siren has a hot lamp behind the sweep, and
    # without it the corner disappears entirely between passes.
    ellipse(field, cx, cy, width * 0.22, height * 0.22, 0.55)
    ellipse(field, cx, cy, width * 0.10, height * 0.10, 0.85)
    add(field, int(round(cx)), int(round(cy)), 1.0)

    # The beam: a SOLID WEDGE thrown from the bulb, not a line. Sampled densely
    # enough that the field has no holes in it — a beam you can see gaps in
    # reads as sparks rather than as light, and this is the one sheet in the
    # game whose whole job is to be impossible to ignore. Foreshortened
    # vertically like every other ground quantity, so it lies ACROSS the
    # clearing instead of standing up in it.
    steps = 22
    for step in range(steps):
        along = (step + 1) / steps
        spread = 0.13 + along * 0.30
        for i in range(9):
            side = (i / 4.0) - 1.0
            a = angle + side * spread
            # Hot along the centreline and at the near end, dying at the rim.
            fade = (1.0 - along * 0.66) * (1.0 - abs(side) ** 1.6 * 0.62)
            x = cx + math.cos(a) * reach * along
            y = cy + math.sin(a) * reach * along * 0.45
            add(field, int(round(x)), int(round(y)), 0.42 * fade)
    resolve(field, img, RED_GLARE, floor=0.07, tone=0.72, gain=0.86)
    return img


# --- the ground --------------------------------------------------------------


class GroundDecal:
    """A ground mark split into what it DARKENS and what it ADDS.

    Same two-blend contract `make_rift.py` documents, for the same reason:
    drawn `source-over` a decal's dark pixels REPLACE the soil, the terrain's
    grain dies under the mark, and the field reads as a sticker laid on dirt
    instead of as something that happened to the ground.
    """

    def __init__(self, width: int, height: int) -> None:
        self.dark = Image.new("RGBA", (width, height), TRANSPARENT)
        self.lit = Image.new("RGBA", (width, height), TRANSPARENT)
        self._dark = self.dark.load()
        self._lit = self.lit.load()
        self.width = width
        self.height = height

    def put(self, x: int, y: int, colour: RGBA, alpha: float, luminous: bool = False) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        px = self._lit if luminous else self._dark
        prior = px[x, y][3]
        px[x, y] = (colour[0], colour[1], colour[2], max(prior, int(clamp01(alpha) * 255)))


def make_imprint(width: int, height: int, rng: random.Random) -> GroundDecal:
    """What is left when the skid goes. DECAL — flat, no outline, no face.

    THE POINT OF THIS SPRITE IS THAT THE PLAYER WATCHES IT ARRIVE. It is
    uncovered on the frame the platform breaks ground, so it is not scenery the
    map came with — it is the answer to "what was under there", and it has to
    land as an answer at that moment: a pressed rectangle of dead soil, four
    deep dents where the feet stood, oil where the gear sat, and the grit that
    came out from underneath.

    The rectangle is deliberately RAGGED. A crisp edge would say the object was
    lifted off clean ground; a frayed one says it has been settling into this
    spot for years and the forest has been creeping back at it.
    """
    decal = GroundDecal(width, height)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    half_w = width * 0.46
    half_h = height * 0.42

    for y in range(height):
        for x in range(width):
            u = abs(x - cx) / half_w
            v = abs(y - cy) / half_h
            # A soft RECTANGLE rather than an ellipse: the thing that stood
            # here had corners, and rounding them off loses the one clue that
            # says a machine was parked here rather than that something burned.
            edge = max(u, v) + (hash01(x, y, 1091) - 0.5) * 0.16
            if edge > 1.0:
                continue
            depth = clamp01((1.0 - edge) * 1.5)
            grain = hash01(x, y, 5501)
            step = clamp01(0.30 + depth * 0.40 + (grain - 0.5) * 0.34)
            decal.put(x, y, pick(PRESSED, step, x, y), 0.34 + depth * 0.32)

    # Drag scars: it did not land here gently, and it has shifted since.
    for _ in range(int(width * 0.5)):
        sx = int(cx + (rng.random() - 0.5) * half_w * 1.7)
        sy = int(cy + (rng.random() - 0.5) * half_h * 1.7)
        run = rng.randint(3, max(4, width // 8))
        for step in range(run):
            decal.put(sx + step, sy, PRESSED[0], 0.30 + 0.30 * (1.0 - step / run))

    # The four dents. DEEPEST THING IN THE FRAME, with a lip of thrown soil on
    # the low side — a flat dark ellipse is a puddle, and a puddle says nothing
    # about weight.
    # Eight, because the skid rides on a beam front and back rather than on
    # four posts — and they are NUDGED off the grid they would otherwise form.
    # A perfect lattice of identical dents is the one thing that would give
    # away that this was stamped rather than settled into.
    for side in (-1, 1):
        for lane in (0.80, 0.30):
            for row in (-1, 1):
                nudge = hash01(int(side * 7), int(lane * 100), int(row * 13))
                fx = cx + side * half_w * (lane + (nudge - 0.5) * 0.08)
                fy = cy + row * half_h * (0.62 + (nudge - 0.5) * 0.10)
                rx = width * (0.048 + nudge * 0.016)
                ry = height * (0.066 + nudge * 0.020)
                for y in range(int(fy - ry * 2), int(fy + ry * 2) + 1):
                    for x in range(int(fx - rx * 2), int(fx + rx * 2) + 1):
                        d = math.hypot((x - fx) / rx, (y - fy) / ry)
                        if d <= 1.0:
                            decal.put(x, y, OIL, 0.40 + (1.0 - d) * 0.38)
                        elif d <= 1.5 and y > fy:
                            decal.put(x, y, pick(GRIT, 0.7, x, y), 0.30, luminous=True)

    # Oil pooled where the lift gear sat, and bolts that shook loose. The bolts
    # are the LIT half: two bright pixels are what a lantern finds when a
    # player walks back across this later in the night.
    for _ in range(int(width * 0.35)):
        x = int(cx + (rng.random() - 0.5) * half_w * 1.2)
        y = int(cy + (rng.random() - 0.5) * half_h * 1.2)
        decal.put(x, y, OIL, 0.5 + rng.random() * 0.4)
    for _ in range(int(width * 0.22)):
        x = int(cx + (rng.random() - 0.5) * half_w * 1.9)
        y = int(cy + (rng.random() - 0.5) * half_h * 1.9)
        decal.put(x, y, pick(GRIT, rng.random(), x, y), 0.55, luminous=True)
    return decal


def make_downwash_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """Rotor wash under a platform that is straining. VFX, additive, LOOPING.

    Four rotors at full power over dry soil push a ring of dust outward, it
    thins, and the next one is already leaving. Three rings a third of a cycle
    apart is what makes that continuous — one ring reads as a pulse, and a
    pulse under a machine holding station reads as the machine misfiring.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    reach = width * 0.48
    for ring in range(3):
        phase = ((index / total) + ring / 3.0) % 1.0
        radius = ease_out(phase) * reach
        # Brightest in the middle of its travel: dust needs a moment to be
        # lifted and has thinned to nothing by the time it reaches the rim.
        strength = math.sin(math.pi * phase) * 0.62
        if radius < 2.0 or strength <= 0.01:
            continue
        ellipse(field, cx, cy, radius, radius * 0.42, strength, hollow=0.42)
    # The churn directly under the deck never clears.
    ellipse(field, cx, cy, width * 0.20, height * 0.20,
            0.30 + 0.08 * math.sin(index / total * math.tau))
    # Grit whipping round, on its own turn, so the ring is never a clean circle.
    for i in range(14):
        a = (i / 14.0 + index / total * 0.5) * math.tau
        rad = reach * (0.35 + 0.55 * ((i * 7 % 11) / 11.0))
        add(field, int(round(cx + math.cos(a) * rad)),
            int(round(cy + math.sin(a) * rad * 0.42)), 0.45)
    resolve(field, img, BEAM, floor=0.07, tone=0.62, gain=0.50)
    return img


def make_burst_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """The ground letting go. VFX one-shot, on the frame the skid breaks free.

    A TONNE OF IRON COMING UNSTUCK IS ONE EVENT, not a fade-up: everything
    under it that had been pressed flat for years is thrown out at once, and
    after that there is only settling dust. So the field is nearly all in the
    first third and the tail is empty — frame 0 and the last frame are both
    near nothing, the rule every one-shot in this game follows, so there is no
    pop at either end.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    t = index / max(total - 1, 1)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    reach = width * 0.50

    front = ease_out(clamp01(t * 1.35))
    strength = (1.0 - ease_in(clamp01(t * 1.05))) * 1.15
    # Frame 0 opens on nothing and grows into the blast within one frame.
    strength *= min(1.0, t * total * 0.9)
    if strength > 0.01:
        ellipse(field, cx, cy, max(2.0, front * reach), max(1.2, front * reach * 0.40),
                strength * 0.72, hollow=0.34)
        ellipse(field, cx, cy, max(2.0, front * reach * 0.62),
                max(1.2, front * reach * 0.26), strength * 0.40)
    # Debris thrown along fixed bearings, so the burst has direction in it
    # rather than being a symmetric puff. It slows as it goes, like thrown dirt.
    for i in range(20):
        a = (i / 20.0) * math.tau + 0.31
        speed = 0.55 + ((i * 13 % 17) / 17.0) * 0.75
        rad = ease_out(clamp01(t * speed * 1.6)) * reach * 1.06
        fade = (1.0 - ease_in(t)) * 0.95 * min(1.0, t * total * 0.9)
        if fade <= 0.02:
            continue
        x = int(round(cx + math.cos(a) * rad))
        y = int(round(cy + math.sin(a) * rad * 0.42 - ease_out(t) * height * 0.14))
        add(field, x, y, fade)
        add(field, x, y + 1, fade * 0.45)
    resolve(field, img, BEAM, floor=0.07, tone=0.70, gain=0.62)
    return img


# --- build -------------------------------------------------------------------


def _layout(plot: int, width: int, height: int) -> dict:
    """Where every piece stands, in TILE offsets from the plot's top-left.

    Same coordinate language as `scenery.Piece` and as `make_rift.py`'s own
    layout: a standing piece's `dy` is the BOTTOM EDGE of the row it stands on
    (its contact point), a decal's `dy` is its centre. `server/app/rift.py`
    mirrors this exactly — if one moves the other has to.

    `eyes` and `rope` are the exceptions and are in PIXELS, because they are
    details of the ART: where on the sprite a rope is tied and how much of it
    was rigged are not tile quantities, and the client is the only side that
    needs them.
    """
    middle = plot / 2.0
    deck = 5.0                 # contact row of the skid
    front = plot - 1.0         # the approach: console and torch
    eyes = _eyes(width, height)
    return {
        # The skid. 5 tiles wide, contact two rows up from the plot's edge so
        # there is standing room in front of it for the console.
        "platform": {"dx": middle, "dy": deck},
        # THE PLAYER MAY NOT GET ON IT — the two rows the box actually sits on
        # are made solid. See `_stamp` in server/app/rift.py.
        "footprint": {"x": 1, "y": 3, "w": PLATFORM_TILES_W, "h": 2},
        # Lift eyes, in pixels from the platform's contact point, in the
        # diagonal corner order. THERE IS NO PARKED-DRONE LIST any more: the
        # drones are not part of this structure, they fly in from off-map when
        # the pad calls them, so the only thing the art has to say about them is
        # where their ropes end up.
        "eyes": [
            {"dx": round(ex - (width - 1) / 2.0, 1), "dy": round(ey - height, 1)}
            for ex, ey in eyes
        ],
        # The corner lamps, in the same pixel frame and the same order. They sit
        # just under their eye — close enough that the glare reads as belonging
        # to the post rather than floating beside it.
        "lamps": [
            {"dx": round(ex - (width - 1) / 2.0, 1), "dy": round(ey + 4 - height, 1)}
            for ex, ey in eyes
        ],
        # How much line a drone pays out, in pixels. It is what sets the hover
        # height: an arriving drone stations itself and lowers a rope until the
        # end reaches its eye, so this number alone decides how high over the
        # pad the rig ends up sitting.
        "rope": {"length": round(height * 1.05, 1)},
        # Flat, centred on the skid's own footprint — this is a picture of what
        # stood there, so it is the same rectangle.
        "imprint": {"dx": middle, "dy": deck - 1.0},
        # The approach. The same console `make_rift.py` draws, and one of the
        # same torches the exit corridor is dressed with.
        "console": {"dx": middle, "dy": front},
        "torch": {"dx": 1.0, "dy": front},
        # The light the pad puts on the map. `kind` 2 is BEACON in
        # `server/app/scenery.py` — the value is the contract.
        "light": {"dx": middle, "dy": deck - 1.0, "radiusTiles": 4.0, "kind": 2},
    }


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "platform"
    out_dir.mkdir(parents=True, exist_ok=True)

    plat_w, plat_h = tile * PLATFORM_TILES_W, tile * PLATFORM_TILES_H
    platforms = [
        make_platform(plat_w, plat_h, state, random.Random(args.seed + 17))
        for state in range(PLATFORM_STATES)
    ]
    pack(platforms, plat_w, plat_h).save(out_dir / "platform.png")

    drone_w, drone_h = round(tile * 1.5), tile
    drones = [make_drone(drone_w, drone_h, state) for state in range(DRONE_STATES)]
    pack(drones, drone_w, drone_h).save(out_dir / "drone.png")

    # Wider than the drone: the discs overhang its arms, which is what makes it
    # read as a machine with props on rather than as a lit toy. Anchored on the
    # ROTOR PLANE, not on the skids — `rotorY` in the manifest is how far above
    # a drone's contact point that plane sits.
    rotor_w, rotor_h = round(tile * 1.75), round(tile * 0.75)
    rotors = [make_rotor_frame(rotor_w, rotor_h, i, ROTOR_FRAMES) for i in range(ROTOR_FRAMES)]
    pack(rotors, rotor_w, rotor_h).save(out_dir / "rotor.png")

    strobes = [
        make_strobe_frame(drone_w, drone_h, i, STROBE_FRAMES) for i in range(STROBE_FRAMES)
    ]
    pack(strobes, drone_w, drone_h).save(out_dir / "strobe.png")

    # The corner lamps' glare. Square and centred on the lamp, and BIG relative
    # to a two-pixel fitting — a siren is mostly the light it throws, and a
    # glare cropped to the lamp's own size is just a brighter lamp.
    lamp_size = tile * 3
    standbys = [
        make_standby_frame(lamp_size, lamp_size, i, STANDBY_FRAMES)
        for i in range(STANDBY_FRAMES)
    ]
    pack(standbys, lamp_size, lamp_size).save(out_dir / "standby.png")
    sirens = [
        make_siren_frame(lamp_size, lamp_size, i, SIREN_FRAMES) for i in range(SIREN_FRAMES)
    ]
    pack(sirens, lamp_size, lamp_size).save(out_dir / "siren.png")

    imp_w, imp_h = tile * PLATFORM_TILES_W, tile * 3
    imprint = make_imprint(imp_w, imp_h, random.Random(args.seed + 29))
    pack([imprint.dark], imp_w, imp_h).save(out_dir / "imprint.png")
    pack([imprint.lit], imp_w, imp_h).save(out_dir / "imprint-lit.png")

    wash_w, wash_h = tile * 7, round(tile * 3.5)
    washes = [
        make_downwash_frame(wash_w, wash_h, i, DOWNWASH_FRAMES) for i in range(DOWNWASH_FRAMES)
    ]
    pack(washes, wash_w, wash_h).save(out_dir / "downwash.png")

    burst_w, burst_h = tile * 8, tile * 4
    bursts = [make_burst_frame(burst_w, burst_h, i, BURST_FRAMES) for i in range(BURST_FRAMES)]
    pack(bursts, burst_w, burst_h).save(out_dir / "burst.png")

    head_alpha = bursts[0].getchannel("A").getextrema()[1]
    tail_alpha = bursts[-1].getchannel("A").getextrema()[1]

    manifest = {
        "tile": tile,
        "seed": args.seed,
        "plot": {"widthTiles": 7, "heightTiles": 7},
        "props": {
            "platform": {
                "file": "platform.png",
                "frameWidth": plat_w,
                "frameHeight": plat_h,
                "frames": PLATFORM_STATES,
                "shapes": 1,
                "states": PLATFORM_STATES,
            },
            "drone": {
                "file": "drone.png",
                "frameWidth": drone_w,
                "frameHeight": drone_h,
                "frames": DRONE_STATES,
                "shapes": 1,
                "states": DRONE_STATES,
                # Where the rotor plane sits above a drone's contact point.
                "rotorY": round(drone_h * 0.56, 1),
            },
        },
        "decals": {
            "imprint": {
                "file": "imprint.png",
                "litFile": "imprint-lit.png",
                "frameWidth": imp_w,
                "frameHeight": imp_h,
                "frames": 1,
            },
        },
        "effects": {
            "rotor": {
                "file": "rotor.png",
                "frameWidth": rotor_w,
                "frameHeight": rotor_h,
                "frames": ROTOR_FRAMES,
                "fps": ROTOR_FPS,
                "anchorY": rotor_h / 2.0,
                "loop": True,
                "tinted": False,
            },
            "strobe": {
                "file": "strobe.png",
                "frameWidth": drone_w,
                "frameHeight": drone_h,
                "frames": STROBE_FRAMES,
                "fps": STROBE_FPS,
                "anchorY": drone_h,
                "loop": True,
                "tinted": False,
            },
            "standby": {
                "file": "standby.png",
                "frameWidth": lamp_size,
                "frameHeight": lamp_size,
                "frames": STANDBY_FRAMES,
                "fps": STANDBY_FPS,
                "anchorY": lamp_size / 2.0,
                "loop": True,
                "tinted": False,
            },
            "siren": {
                "file": "siren.png",
                "frameWidth": lamp_size,
                "frameHeight": lamp_size,
                "frames": SIREN_FRAMES,
                "fps": SIREN_FPS,
                "anchorY": lamp_size / 2.0,
                "loop": True,
                "tinted": False,
            },
            "downwash": {
                "file": "downwash.png",
                "frameWidth": wash_w,
                "frameHeight": wash_h,
                "frames": DOWNWASH_FRAMES,
                "fps": DOWNWASH_FPS,
                "anchorY": wash_h / 2.0,
                "loop": True,
                "tinted": False,
            },
            "burst": {
                "file": "burst.png",
                "frameWidth": burst_w,
                "frameHeight": burst_h,
                "frames": BURST_FRAMES,
                "fps": BURST_FPS,
                "anchorY": burst_h / 2.0,
                "loop": False,
                "tinted": False,
            },
        },
        "layout": _layout(7, plat_w, plat_h),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: "
        f"platform {PLATFORM_STATES}x{plat_w}x{plat_h}, "
        f"drone {DRONE_STATES}x{drone_w}x{drone_h}, "
        f"rotor {ROTOR_FRAMES}x{rotor_w}x{rotor_h} @{ROTOR_FPS}fps loop, "
        f"strobe {STROBE_FRAMES}x{drone_w}x{drone_h} @{STROBE_FPS}fps loop, "
        f"standby {STANDBY_FRAMES}x{lamp_size}x{lamp_size} @{STANDBY_FPS}fps loop, "
        f"siren {SIREN_FRAMES}x{lamp_size}x{lamp_size} @{SIREN_FPS}fps loop, "
        f"imprint 1x{imp_w}x{imp_h}, "
        f"downwash {DOWNWASH_FRAMES}x{wash_w}x{wash_h} @{DOWNWASH_FPS}fps loop, "
        f"burst {BURST_FRAMES}x{burst_w}x{burst_h} @{BURST_FPS}fps, "
        f"burst edges {head_alpha}/{tail_alpha}"
    )
    if head_alpha > 8 or tail_alpha > 8:
        raise SystemExit(
            f"burst does not open and close on nothing (first {head_alpha}, "
            f"last {tail_alpha}): a one-shot whose ends carry alpha pops when "
            f"the client starts it and leaves dust hanging over a bare imprint"
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
