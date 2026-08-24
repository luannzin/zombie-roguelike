#!/usr/bin/env python3
"""Asset pipeline: collectable loot icons.

Output (assets/processed/loot/):
    sheet.png      one 16x16 frame per item, left to right in catalog order
    manifest.json  frame index per item key

These sit ON the ground as small standing props and are the same pixels the
bag, the belt and the price tag show. The server places them next to scenes and
the player picks them up.

THE SHEET IS BUILT OUT OF VOLUMES NOW, NOT OUT OF STENCILS
Every item here used to be a flat character map painted by one diagonal
falloff — brighter at the top-left, darker at the bottom-right, run through
`pick`, which DITHERS between the two nearest steps. Three things followed from
that and all three are what the pixel-art direction rules out:

  * a "shade" that slides continuously across a shape is a gradient (S7), and
    at 16px a gradient over four steps is a flat fill with speckle on it;
  * `pick` on a continuous value scatters single pixels of the neighbouring
    step across every face (S5), so nothing had a plane and nothing had an
    edge — the crates and the guns each had this exact failure before their
    own pass;
  * a falloff that runs corner to corner is not a light direction. It lights a
    bottle and a wrench identically regardless of what shape either one is,
    which is the definition of a sticker.

What replaced it is `paint_form` below: a map is broken into SUB-BLOBS (S2),
each blob gets its own full five-step ramp, and a pixel's step is a function of
where it sits in ITS OWN blob — crest, key flank, shade flank, contact. Volume
is facet and band, never falloff. That is the same construction `make_objects`
gives a barrel and `make_guns` gives a receiver, expressed for a 16px stencil.

WHY THE CAMERA IS NOT THE WORLD'S DIMETRIC
`make_objects.SLOPE` is the 2:1 the crates stand on, and a crate is 48 pixels
across. At 16 a rhombus top face is three pixels of lozenge and the object
loses its silhouette to its own perspective. So the sheet runs S21's ICON
sub-mode: near-elevation, the long axis tipped 15-20 degrees down-right, the
outline fully closed and higher contrast than a world prop's. What it keeps
from the world is everything that actually makes the set cohere (S20): one key
at 135deg, one derived palette with hue-shifted ramps, and one ground shadow
convention — which is why these still plant on a tile beside a barrel instead
of hovering over it as icons.

READ ORDER AT 16px IS SILHOUETTE, THEN VALUE, THEN COLOUR (S15). Every map here
is authored top contour first: a bottle is a long neck on a shoulder, a crown
is three uneven points, a key is a bit and a bow, a totem is a stack of faces.
Colour is the LAST thing that tells two items apart and the first thing the
night takes away.

Usage:
    python tools/make_loot.py
    python tools/make_loot.py --tile 16
"""

from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    material_ramp,
    pack,
)

#: The held-weapon generator, imported for its PAINTER and its material ramps.
#: The twelve gun icons on this sheet are the same twelve objects that sheet
#: draws, so they are shaded by its code and coloured out of its ramps rather
#: than out of a matching set kept here — see the comment over `WEAPONS`.
import make_guns as guns  # noqa: E402

# --- the palette --------------------------------------------------------------
#
# FOURTEEN RAMPS, ALL DERIVED, NONE TYPED. Every one is `material_ramp` out of
# S11's law — hue, saturation, and where the two ends sit — so a material is
# authored as the four things that actually differ between materials and the
# hue-shift-and-desaturate rule is written once, in `make_textures.py`, for the
# whole game. The hand-typed hex ramps this replaced had four of them changing
# value without changing hue at all, which is the one thing S11 calls wrong.
#
# S11 asks for 6-8 ramps and this is fourteen. It earns them: this sheet is the
# game's entire MATERIAL CATALOG — forty-six objects spanning junk, tools,
# electronics, treasure and ammunition, and the whole point of a loot tier is
# that the player can tell brass from gold from crystal across a dark clearing.
# The economy S11 actually wants is shared ENDPOINTS, and these have them: every
# `lo` sits in 0.09-0.19 and every `hi` in 0.48-0.88, so no material bottoms out
# into the keyline (S7).
#
# THE CEILINGS ARE HIGHER HERE THAN ANYWHERE ELSE IN THE GAME AND THAT IS THE
# POINT. S11's table puts the base step at L 50-58; the scenery ramps sit well
# under that because a trunk is meant to recede, and `make_guns`' sit under it
# again because the lantern multiplies over a weapon held in a dark forest. A
# drop is the opposite errand: it is a thing on a dark floor that the player has
# to SEE, from far enough away to decide whether the walk is worth it, and a
# loot ramp tuned like a tree ramp is litter. The first cut of this rewrite kept
# the guns' ceilings and forty-six objects came out as forty-six dark lumps with
# a bright edge — every one correctly banded and not one of them legible.

#: Handles, hafts, stocks. The one wood on the sheet.
WOOD: Ramp = material_ramp(26, 0.38, 0.12, 0.68)
#: Painted / dull steel (S14: large flat planes, one streak along the form).
METAL: Ramp = material_ramp(212, 0.14, 0.13, 0.66)
#: Bare metal: the same planes plus a tight step-4 to step-1 jump. Brighter
#: than METAL by design — this is what a polished thing is made of, and value
#: is how a 16px sprite says "polished".
CHROME: Ramp = material_ramp(205, 0.07, 0.16, 0.84)
#: Corrosion. The warmest of the metals and the most saturated, because rust is
#: the only one of them that is a COLOUR rather than a value.
RUST: Ramp = material_ramp(18, 0.45, 0.13, 0.62)
#: Glass (S14): flat step-3 fill with two parallel diagonal streaks. Cool and
#: tinted, never neutral — clear glass drawn neutral is a hole in the sprite.
GLASS: Ramp = material_ramp(196, 0.26, 0.15, 0.74)
#: Treasure gold. The sheet's brightest warm ramp and the one that has to still
#: read as gold after the night multiply lands on it.
GOLD: Ramp = material_ramp(43, 0.58, 0.16, 0.82)
#: Cartridge brass. A step down and a step cooler than GOLD: a box of ammunition
#: must never flash like a payday from across a clearing.
BRASS: Ramp = material_ramp(38, 0.48, 0.14, 0.70)
#: Carved stone. Near-neutral with a violet lean, so it separates from bone by
#: hue at the same value.
STONE: Ramp = material_ramp(268, 0.08, 0.13, 0.64)
BONE: Ramp = material_ramp(45, 0.17, 0.17, 0.76)
#: Leather and hide. Dark, warm, low ceiling — straps and thongs are the thing
#: that must not out-read what they are attached to.
LEATHER: Ramp = material_ramp(22, 0.32, 0.10, 0.56)
#: Cloth (S14): wide soft bands, low step count. Its ramp is short in RANGE for
#: that reason — fabric has no specular.
CLOTH: Ramp = material_ramp(48, 0.15, 0.15, 0.66)
#: Crystal / ice (S14): tall prisms, hard 2x2 hit per face. The highest ceiling
#: on the sheet and the reason a gem reads before its shape does.
CRYSTAL: Ramp = material_ramp(202, 0.50, 0.17, 0.88)
#: Obsidian. Nearly the lowest ceiling here on purpose: the black tier's whole
#: identity is that it eats light, and the accent hue is what rescues it.
OBSIDIAN: Ramp = material_ramp(258, 0.18, 0.09, 0.48)
#: Nacre. Violet, and the one ramp whose midpoint is lighter than its
#: neighbours' — a pearl is a sheen, not a surface.
PEARL: Ramp = material_ramp(285, 0.14, 0.19, 0.80)
#: Military drab. The saturated dull green nothing else on the sheet is.
OLIVE: Ramp = material_ramp(78, 0.30, 0.12, 0.58)
#: The one loud accent (S12). Medical crosses, a flare, a shotgun shell — every
#: use is something the player is meant to find fast.
RED: Ramp = material_ramp(4, 0.55, 0.14, 0.62)

#: `x`. Not a material — a hole in one. Shared, so a rivet hole in a crate lid
#: and a bore in a barrel are the same darkness. The only ramp allowed to sit
#: near the outline, because that is what a hole looks like.
VOID: Ramp = material_ramp(228, 0.16, 0.05, 0.17)

Art = list[str]
Palette = dict[str, Ramp]

#: Which ramp letter maps to which material, for every map below. ONE ALPHABET
#: FOR THE WHOLE SHEET, so a map reads as an engineering drawing rather than as
#: a private key — `m` is metal in all forty-six of them, and the palette dict
#: on each item only exists to say which of these it actually spends.
#:
#:     w wood     m metal    c chrome   r rust     g glass
#:     o gold     n brass    s stone    b bone     l leather
#:     f cloth    y crystal  k obsidian p pearl    v olive
#:     e red      x recess
#:
#: Two modifiers, the same two `make_guns.py` uses:
#:     UPPERCASE  lift one ramp step — the specular hit (S14) and a lit crest.
#:     x          a recess in VOID. Interior form breaks are value steps and
#:                never lines (S6); a recess is the one step allowed to be a
#:                single pixel wide.
ALPHABET: Palette = {
    "w": WOOD, "m": METAL, "c": CHROME, "r": RUST, "g": GLASS,
    "o": GOLD, "n": BRASS, "s": STONE, "b": BONE, "l": LEATHER,
    "f": CLOTH, "y": CRYSTAL, "k": OBSIDIAN, "p": PEARL, "v": OLIVE,
    "e": RED,
}


# --- the painter --------------------------------------------------------------
#
# S2: form is a STACK OF CONVEX MASSES, never one hull, and each sub-blob gets
# its own full ramp with the boundaries between them read as a value step rather
# than as a line. At this size a "sub-blob" is exactly a run of one material —
# a bottle's neck, its body, the rag round it — so the blobs are found rather
# than authored, and the maps stay readable as shapes instead of as shading.


def _pad(art: Art) -> Art:
    width = max(len(row) for row in art)
    return [row.ljust(width, ".") for row in art]


def art_size(art: Art) -> tuple[int, int]:
    """(columns, rows) of a map. For placing an origin."""
    return (max(len(row) for row in art), len(art))


def _blobs(cells: dict[tuple[int, int], str]) -> dict[tuple[int, int], int]:
    """Every cell's sub-blob: the connected run of one material it belongs to.

    Four-connected and material-keyed, so two crates touching side by side are
    one blob and a crate touching a strap is two. `x` is never in a blob: a
    recess is a hole in a mass, not a mass.
    """
    blob: dict[tuple[int, int], int] = {}
    index = 0
    for key in sorted(cells):
        if key in blob or cells[key] == "x":
            continue
        material = cells[key].lower()
        stack = [key]
        blob[key] = index
        while stack:
            cx, cy = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                near = (cx + dx, cy + dy)
                if near in blob or near not in cells:
                    continue
                if cells[near] == "x" or cells[near].lower() != material:
                    continue
                blob[near] = index
                stack.append(near)
        index += 1
    return blob


#: The key is at 135deg / elevation 60 (S8). On a grid that is exactly "up and
#: left", which is why the shader below never needs a light vector: the two
#: offsets ARE the azimuth.
KEY = ((-1, 0), (0, -1))
SHADE = ((1, 0), (0, 1))


def _plane(inside, x: int, y: int, tall: int) -> int:
    """One pixel's ramp step, from which of its own mass's edges it sits on.

    S7 SAYS THE TERMINATOR FOLLOWS FORM CURVATURE AND NEVER CUTS STRAIGHT, and
    that one sentence is why this is an edge test and not a coordinate test. The
    first cut of this shader banded off the bounding box — top two rows bright,
    then everything left of 58% at the base step and everything right of it a
    step down — which is a vertical terminator on every object regardless of
    what shape it is. Forty-six items came out as forty-six lumps: a bright cap,
    a mid-grey left half and a dark right half, identical on a bottle, a wrench
    and a skull.

    Asking the MASS instead gives the curvature for free:

        lit rim     step 3, the upper-left boundary — the plane turned toward
                    the key. Lifts to 4 where up AND left are both open, which
                    is a corner pointing straight into the light (S7's step-4
                    accent, and by construction it can only ever be a handful
                    of pixels).
        shade rim   step 1, the lower-right boundary.
        underside   step 0, wherever a mass has nothing beneath it. That is the
                    contact band S10 and S19 both ask for, drawn INSIDE the
                    silhouette, and it lands under every sub-mass rather than
                    only at the sprite's feet — which is what makes a stack of
                    masses read as stacked.
        core        step 2, everything the rims did not claim. The base owns the
                    most pixels because the interior is always bigger than its
                    own outline, which is S7's rule falling out of the geometry
                    rather than being enforced on top of it.

    A "mass" here is the sub-blob (S2), so a recess and a neighbouring material
    are both OUTSIDE it — a hole in a plate gets its own lit lip and its own
    dark underside, and two materials touching read as two volumes rather than
    as one silhouette in two colours.
    """
    if tall <= 1:
        # S16: a one-pixel band deletes rather than shrinks. It gets the base
        # step and no rim — a highlight the same size as the shape is a shape
        # made of highlight.
        return 2
    if not inside(x, y + 1):
        return 0
    lit = any(not inside(x + dx, y + dy) for dx, dy in KEY)
    dark = any(not inside(x + dx, y + dy) for dx, dy in SHADE)
    if lit and dark:
        # A one-pixel sliver: both rims want it, so neither gets it. Handing it
        # to either one turns every thin feature into a line of pure highlight
        # or pure shadow.
        return 2
    if lit:
        corner = not inside(x - 1, y) and not inside(x, y - 1)
        return 4 if corner else 3
    if dark:
        return 1
    return 2


def paint_form(art: Art, ramps: Palette, size: tuple[int, int],
               origin: tuple[int, int]) -> tuple[Image.Image, dict]:
    """A character map, painted as banded volume. NO OUTLINE — see `_key`.

    Returns the image and a per-pixel plan (`(x, y) -> (ramp, step)`), which the
    outline pass needs: S6 says the keyline is the neighbouring material's own
    darkest step hue-shifted, and that it DROPS where the light hits — neither
    of which is decidable from the finished pixels alone.
    """
    art = _pad(art)
    cells = {
        (x, y): ch
        for y, row in enumerate(art)
        for x, ch in enumerate(row)
        if ch != "."
    }
    blob = _blobs(cells)
    tall: dict[int, int] = {}
    for key, index in blob.items():
        tall[index] = tall.get(index, 0)
    for index in tall:
        rows = [y for (x, y), i in blob.items() if i == index]
        tall[index] = max(rows) - min(rows) + 1

    img = Image.new("RGBA", size, TRANSPARENT)
    px = img.load()
    plan: dict[tuple[int, int], tuple[Ramp, int]] = {}
    width, height = size
    ox, oy = origin

    for (x, y), ch in cells.items():
        sx, sy = ox + x, oy + y
        if not (0 <= sx < width and 0 <= sy < height):
            continue
        if ch == "x":
            px[sx, sy] = VOID[1]
            plan[(sx, sy)] = (VOID, 1)
            continue
        ramp = ramps.get(ch.lower())
        if ramp is None:
            continue
        index = blob[(x, y)]
        step = _plane(lambda ax, ay: blob.get((ax, ay)) == index, x, y, tall[index])
        if ch.isupper():
            step = min(step + 1, len(ramp) - 1)
        px[sx, sy] = ramp[step]
        plan[(sx, sy)] = (ramp, step)
    return img, plan


# --- ground, contact and key --------------------------------------------------


def _shift(colour: RGBA, light: float, hue: float, sat: float) -> RGBA:
    """A ramp step moved by S6/S11's law: cooler, darker, a touch more saturated."""
    red, green, blue, alpha = colour
    h, l, s = colorsys.rgb_to_hls(red / 255.0, green / 255.0, blue / 255.0)
    h = ((h * 360.0 + hue) % 360.0) / 360.0
    l = max(0.0, min(1.0, l * (1.0 + light)))
    s = max(0.0, min(1.0, s * (1.0 + sat)))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255), alpha)


#: S6's exterior keyline: the darkest ramp step, hue -15deg, value -25%.
def _keyline(ramp: Ramp) -> RGBA:
    return _shift(ramp[0], -0.25, -15.0, 0.10)


#: S6 again: the bottom edge darkens further, because that is the contact.
def _contactline(ramp: Ramp) -> RGBA:
    return _shift(ramp[0], -0.48, -18.0, 0.14)


def _key(img: Image.Image, plan: dict) -> None:
    """The 1px outline, hue-tinted per material and BROKEN ON THE LIT CREST.

    S6, and every clause of it is load-bearing at this size:

      * the colour comes off the neighbour's OWN ramp, so a gold ring is keyed
        in dark gold and a bottle in dark green. One flat near-black round every
        object on a sheet is what makes a set of icons read as stickers — the
        keyline stops being part of the material and becomes a border;
      * the bottom edge goes darker still. That is the contact (S19), and it is
        the single cheapest thing that plants an object on a floor;
      * where the key light lands, the line DROPS — the whole TOP PLANE's outer
        edge, not just its specular. An unbroken border is 30-40% of every
        opaque pixel on a 16px sprite; on the crest it is competing with the
        two brightest steps in the ramp, and the object comes out looking
        traced. Light eats the line.
    """
    px = img.load()
    edges: dict[tuple[int, int], RGBA] = {}
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] != 0:
                continue
            below = plan.get((x, y + 1))
            above = plan.get((x, y - 1))
            # The lit crest of the mass immediately below: no line. Only the
            # TOP edge qualifies — a crest pixel with sky above it — because
            # that is the edge the 135deg key actually rakes.
            if below is not None and below[1] >= 3 and above is None:
                continue
            best: tuple[Ramp, int] | None = None
            contact = False
            for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1)):
                near = plan.get((x + dx, y + dy))
                if near is None:
                    continue
                # Prefer the darkest neighbour: where two materials meet at a
                # corner the keyline belongs to the one in shadow.
                if best is None or near[1] < best[1]:
                    best = near
                if (dx, dy) == (0, -1):
                    contact = True
            if best is None:
                continue
            ramp = best[0]
            edges[(x, y)] = _contactline(ramp) if contact else _keyline(ramp)
    for (x, y), colour in edges.items():
        px[x, y] = colour


#: S9's ground shadow, as ratios of the sprite's own footprint. It is a separate
#: FLAT element echoing the footprint, never projected geometry and never
#: detailed — two alpha bands, offset down-right, and nothing else.
SHADOW_WIDTH = 1.06
SHADOW_RATIO = 0.31
SHADOW_OFFSET_X = 0.11
SHADOW_OFFSET_Y = 0.045
SHADOW_TONE = (10, 11, 16)
SHADOW_ALPHA = (96, 52)


def _ground(img: Image.Image) -> None:
    """The offset ellipse everything on this sheet stands on.

    WHY A SHEET THE HUD ALSO DRAWS STILL GETS ONE. These are ground props first:
    the same pixels lie on a forest floor beside a barrel that has one baked in,
    and an icon with no contact patch floats over the tile it is supposed to be
    resting on. In a bag slot it reads as a soft plate under the item, which is
    what a shadow is. The alternative — two sheets — is two drawings of one
    object that drift, which is the failure `make_guns` documents at length.

    Painted only where the sprite is NOT, so it darkens the ground beside the
    object rather than smudging the object itself.
    """
    px = img.load()
    columns = [
        x for x in range(img.width)
        if any(px[x, y][3] for y in range(img.height))
    ]
    if not columns:
        return
    rows = [y for y in range(img.height) if any(px[x, y][3] for x in range(img.width))]
    left, right, base = columns[0], columns[-1], rows[-1]
    # The FOOTPRINT, not the silhouette (S9): how wide the thing is where it
    # meets the floor. A bottle's shadow is the size of its base, and taking the
    # widest row instead is what makes a top-heavy object look like it is
    # standing on a plate.
    foot = [x for x in range(img.width) if px[x, base][3] or px[x, max(base - 1, 0)][3]]
    span = (foot[-1] - foot[0] + 1) if foot else (right - left + 1)
    cx = ((foot[0] + foot[-1]) / 2.0 if foot else (left + right) / 2.0)
    cx += img.width * SHADOW_OFFSET_X
    cy = base + img.height * SHADOW_OFFSET_Y
    rx = span * SHADOW_WIDTH / 2.0
    ry = max(1.0, rx * SHADOW_RATIO)
    for y in range(max(0, int(cy - ry)), min(img.height, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(img.width, int(cx + rx) + 1)):
            if px[x, y][3]:
                continue
            dx, dy = (x - cx) / rx, (y - cy) / max(ry, 0.5)
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            px[x, y] = (*SHADOW_TONE, SHADOW_ALPHA[0] if d < 0.45 else SHADOW_ALPHA[1])


#: Rows of clearance under the art for the shadow to land in. Two: the ellipse
#: is offset DOWN as well as right, so one row leaves half of it outside the
#: cell and the object reads as standing on the bottom edge of its own frame.
PLANT = 2


def _blit(art: Art, cell: int) -> Image.Image:
    """One item: banded volume, keyed, planted on its own shadow.

    Painted out of `ALPHABET` and nothing else. The per-item palette dict this
    used to take was forty-six chances for a letter to be missing from its own
    map's key — and a missing letter does not raise, it silently drops every
    pixel wearing it, which is an art gap that only ever shows up on a dark
    tile in a live game.
    """
    art_w, art_h = art_size(art)
    origin = ((cell - art_w) // 2, cell - art_h - PLANT)
    img, plan = paint_form(art, ALPHABET, (cell, cell), origin)
    _key(img, plan)
    _ground(img)
    return img


# ---------------------------------------------------------------------------
# THE ITEMS.
#
# The manifest is keyed by ITEM KEY, not by position, so this list only has to
# CONTAIN every key `server/app/loot.py` can produce — it does not have to match
# its order. Guns and ammunition boxes are generated there off the weapons
# catalog, so a new weapon needs one entry down at the bottom of this list and
# nothing else; a weapon with no entry draws nothing and is still collectable,
# which is the right way round for an art gap to fail.
#
# HOW A MAP IS AUTHORED, in the order the decisions have to be made:
#
#   1. THE TOP CONTOUR (S15). It carries the identity — the player names the
#      object off its upper profile before any colour resolves. Two items in the
#      same tier that share a crown are two items nobody can tell apart.
#   2. THE LEAN (S21). The long axis runs 15-20deg down-right. Nothing on this
#      sheet is bilaterally symmetric; a symmetric icon reads as a UI glyph, and
#      the moment one does, the whole set stops looking like objects lying in a
#      forest.
#   3. HEIGHT OVER FOOTPRINT (S17), 1.1:1 to 1.6:1. The old maps ran the other
#      way — four rows tall and eight wide — which is why a first-aid kit, a
#      license plate and a ledger were three rectangles.
#   4. NOTCHES (S15). Two to four pixels bitten out of the edge at irregular
#      intervals, so no outline is ever a smooth arc.
#   5. THE ACCENT (S12), one hue, under 8% of the pixels, and only where the eye
#      should go. Most items here do not get one at all.
# ---------------------------------------------------------------------------

ITEMS: list[tuple[str, Art]] = [
    # --- junk: the bottom of the table -------------------------------------
    (
        # A claw hammer, head-up, leaning off its haft. The head is the contour.
        "old_tools",
        [
            ".rrrrr..",
            "rrrrrrr.",
            "rr.rrrr.",
            "....ww..",
            "....ww..",
            "....ww..",
            ".....ww.",
            ".....ww.",
            ".....ll.",
            ".....ww.",
        ],
    ),
    (
        # Long neck on a sloped shoulder, a rag knotted at the waist. The neck
        # is two thirds of the height: that ratio is the whole silhouette.
        "empty_bottle",
        [
            "...gg...",
            "...gg...",
            "...gg...",
            "..gGgg..",
            "..ffff..",
            "..ffff..",
            ".gGgggg.",
            ".ggGggg.",
            ".gggggg.",
            ".gggggg.",
            "..gggg..",
        ],
    ),
    (
        # One ear gone and a seam split. The missing ear is the read — a bear
        # with two is a toy, a bear with one is a BROKEN toy.
        "broken_toy",
        [
            ".ff.....",
            "ffff....",
            "ffffff..",
            "ffbfbf..",
            ".fffff..",
            "..fff...",
            ".ffffff.",
            "fflffff.",
            "fflfff..",
            ".ff.ff..",
            ".f...f..",
        ],
    ),
    (
        # A mantel clock: a case with a dome, its glass starred, one hand left.
        "broken_clock",
        [
            "..wwww..",
            ".wwwwww.",
            "wwwwwwww",
            "wwgggggw",
            "wgggxggw",
            "wggxxggw",
            "wgggggww",
            "wwwwwwww",
            ".ww..ww.",
            ".w....w.",
        ],
    ),
    (
        # A torn plate, folded. Jagged on three sides — the one item on the
        # sheet whose whole identity is that it has no shape.
        "scrap",
        [
            "..mm.m..",
            ".mmmmmm.",
            "mmm.rmm.",
            "mm.rrrm.",
            ".mrrr.m.",
            ".mmrmm..",
            "..m.mm..",
            "...mm...",
        ],
    ),
    (
        # Lid peeled back and standing up. That flap is what stops this being a
        # cylinder, and a cylinder at 16px is a barrel.
        "rusty_can",
        [
            "..cc....",
            ".ccc....",
            ".rrrrr..",
            "rrrrrrr.",
            "rRRRRrr.",
            "rrrrrrr.",
            "rrrrrrr.",
            "rRRRRrr.",
            "rrrrrr..",
            ".rrrrr..",
        ],
    ),
    (
        # A roll, not a sheet: half furled, one corner torn away. Paper drawn
        # flat is a rectangle, and there are four rectangles on this sheet
        # already.
        "torn_map",
        [
            "..fffff.",
            ".ffffff.",
            "fffxffff",
            "ffxfffff",
            "ffxxfeff",
            ".ffxffff",
            "..fffff.",
            "...ff.f.",
            "...f....",
        ],
    ),
    (
        # Hex nut in the middle, ceramic above, electrode hooked below.
        "spark_plug",
        [
            "..ff....",
            "..ff....",
            ".ffff...",
            ".ffff...",
            "cccccc..",
            "cCcccc..",
            "cccccc..",
            ".mmmm...",
            ".mmmm...",
            ".mm.m...",
            "..mmm...",
        ],
    ),
    (
        # Propped against something, buckled along one edge. Flat-on it was a
        # bar of pixels; leaning, the top contour is a corner.
        "license_plate",
        [
            "...mmmm.",
            "..mmmmmm",
            ".mmmmmmm",
            "mmfmfmfm",
            "mmfmfmf.",
            "mmmmmm..",
            ".mmmrm..",
            "..mmr...",
        ],
    ),
    (
        # Body, a lens barrel standing proud of it, wind lever on top. The
        # barrel breaking the outline is the whole silhouette.
        "camera",
        [
            "...m..m.",
            ".llllll.",
            "llllllll",
            "llmmmmll",
            "llmGgmll",
            "llmggmll",
            "llmmmmll",
            "llllllll",
            ".llllll.",
            "..l..l..",
        ],
    ),
    (
        # A band with one cup swung out on its slider. Symmetric it was a
        # croquet hoop.
        "old_headphone",
        [
            "..mmmm..",
            ".mm..mm.",
            ".m....m.",
            "mm....mm",
            "ll....ll",
            "lfl...ll",
            "lfl...lf",
            "lll...ll",
            ".ll....l",
        ],
    ),
    (
        # Antenna up and raked back, dial on the face, grille below it.
        "portable_radio",
        [
            ".....c..",
            "....c...",
            "...c....",
            "mmmmmmm.",
            "mgggglm.",
            "mggggcm.",
            "mllllllm",
            "mlxlxlxm",
            "mllllllm",
            "mmmmmmmm",
            ".mm..mm.",
        ],
    ),
    (
        # Lid hinged open behind the dial. Shut, it was a coin.
        "compass",
        [
            "..ooo...",
            ".oooooo.",
            ".oo..ooo",
            "oooooomo",
            "omemmmoo",
            "ommemmo.",
            "ommmmmo.",
            ".oooooo.",
            "..oooo..",
        ],
    ),
    (
        # Two posts of different heights on a case with a carry strap. The
        # uneven posts are what makes it a battery and not a crate.
        "car_battery",
        [
            "..c..c..",
            "..c.ccc.",
            ".ec.ccc.",
            "kkkkkkkk",
            "kklllkkk",
            "kkkkkkkk",
            "kkkkkkkk",
            "kkxkkxkk",
            "kkkkkkkk",
            ".kkkkkk.",
        ],
    ),
    (
        # A tin with a sprung catch and a cross. The cross is the accent and is
        # the only thing on the item that is allowed to be loud.
        "first_aid",
        [
            "..cc....",
            ".ffffff.",
            "ffffffff",
            "fffeefff",
            "fffeeffc",
            "feeeeefc",
            "fffeefff",
            "fffeefff",
            "ffffffff",
            ".ffffff.",
        ],
    ),
    (
        # Cap off and hanging, striker exposed. Half the height is the accent
        # and this is the one item where that is right.
        "road_flare",
        [
            "..oo....",
            "..oo....",
            ".ooo....",
            ".eee....",
            ".eee....",
            ".eeef...",
            ".eeef...",
            "..eee...",
            "..eee...",
            "..eee...",
            "..eee...",
        ],
    ),
    (
        # Two spanners crossed, the open jaws up. Jaws are the contour.
        "wrench_set",
        [
            "cc...mm.",
            "cCc.mmm.",
            "ccc.mmm.",
            ".cc.mm..",
            ".cccmm..",
            "..cmmm..",
            "..lllm..",
            "..mcll..",
            "..mc....",
            "..mm....",
        ],
    ),
    (
        # The camera's silhouette in drab with a hood over the lens. Same
        # geometry, different tier — S21's keying rule: a variant is signalled
        # by the accent, not by a new drawing.
        "military_camera",
        [
            "...m..m.",
            ".vvvvvv.",
            "vvvvvvvv",
            "vvmmmmvv",
            "vvmGgmvv",
            "vvmggmvv",
            "vvmmmmvv",
            "vvvvvevv",
            ".vvvvvv.",
            "..v..v..",
        ],
    ),
    # --- worth carrying ------------------------------------------------------
    (
        # Standing on edge and tipped, so the band is an oval rather than a
        # circle. A ring drawn face-on is a washer.
        "gold_ring",
        [
            "..oo....",
            ".oooo...",
            "oo..oo..",
            "o....oo.",
            "o....oo.",
            "oo...oo.",
            ".oo.ooo.",
            "..oooo..",
            "...oo...",
        ],
    ),
    (
        # Two barrels, one nearer than the other — the offset is the depth cue
        # (S18) and the reason this is not a pair of dots.
        "binoculars",
        [
            ".gg.....",
            "mmmm.gg.",
            "mmmmmmmm",
            "mllmmllm",
            "mllmmllm",
            "mllccllm",
            "mmm..mmm",
            ".mm..mm.",
            ".mm..mm.",
            "..m...m.",
        ],
    ),
    (
        # A cut stone: a table facet on top, pavilion tapering below, one girdle
        # break. Crystal is prisms and parallel inner lines (S14).
        "precious_gem",
        [
            "..yYy...",
            ".yyyyy..",
            "yyyyyyy.",
            "yyxyyxy.",
            ".yyyyy..",
            ".yyyyy..",
            "..yyy...",
            "..myy...",
            "...y....",
        ],
    ),
    (
        # An auto-injector: cap, barrel, plunger. Vertical, and the plunger
        # ring at the top is the contour.
        "morphine",
        [
            "..cc....",
            ".c..c...",
            "..cc....",
            "..cc....",
            ".yyy....",
            ".yyy....",
            ".yyyy...",
            ".myyy...",
            ".mmm....",
            "..mm....",
            "..m.....",
        ],
    ),
    (
        # Rubber-ducked antenna, a squelch knob and a speaker grille. The bent
        # antenna is what separates it from every other black box here.
        "police_radio",
        [
            "..m.....",
            "..mm....",
            "...m....",
            ".kkkkk..",
            ".kyyyk..",
            ".kkkkke.",
            ".kxxxk..",
            ".kxxxk..",
            ".kkkkk..",
            ".kkkkk..",
            "..kkk...",
        ],
    ),
    (
        # Two tubes on a headmount, one shorter — a broken pair, which is why
        # they are on a forest floor.
        "night_vision",
        [
            "..vvvv..",
            ".vvvvvv.",
            "vvvvvvvv",
            "vyyvvyyv",
            "vyyvvyyv",
            "vmmvvyyv",
            ".mm..vvv",
            ".mm...m.",
            "..m...m.",
        ],
    ),
    # --- the tribal tier: everything here is CARVED --------------------------
    (
        # A hooked jaw hung off a thong. Hangs, so it is drawn hanging — the
        # thong is the top contour and the bone leans off it.
        "bone_charm",
        [
            ".l...l..",
            "..l.l...",
            "...l....",
            "..bbb...",
            ".bbbbb..",
            ".bb.bb..",
            ".bbebb..",
            "..bbbb..",
            "...bbb..",
            "....bb..",
        ],
    ),
    (
        # A squat figure with a heavy brow and its arms folded in. Chunky,
        # bottom-wide, one shoulder higher (S17: the base is wider than the
        # crown for grounded objects).
        "stone_idol",
        [
            "..sss...",
            ".sssss..",
            ".sxsxs..",
            ".sssss..",
            "..sss...",
            ".ssssss.",
            "ssoossss",
            "ssssssss",
            "sssssss.",
            ".ssssss.",
        ],
    ),
    (
        # Two horns, and they are different lengths. A mask with matched horns
        # is a logo.
        "tribal_mask",
        [
            "w.....w.",
            "ww....w.",
            ".wwwwww.",
            ".wbwwbw.",
            ".wwwwww.",
            ".weewww.",
            ".wwewww.",
            "..wwww..",
            "..ffff..",
            "...ff...",
        ],
    ),
    (
        # A disc on a cord with a stone set off centre. The cord's V is the
        # contour and the setting is the accent.
        "ancient_amulet",
        [
            "l.....l.",
            ".l...l..",
            "..l.l...",
            "..ooo...",
            ".ooooo..",
            ".oyyoo..",
            ".oyooo..",
            ".ooooo..",
            "..ooo...",
        ],
    ),
    (
        # A standing figure on a plinth: head, shoulders, a hip shift. The hip
        # is what stops it being a chess pawn.
        "gold_figurine",
        [
            "..ooo...",
            "..ooo...",
            "...o....",
            ".ooooo..",
            "oooooo..",
            ".ooooo..",
            "..ooo...",
            "..oooo..",
            ".ssssss.",
            "ssssssss",
        ],
    ),
    (
        # Uncut: a cluster of prisms out of a matrix, no two the same height.
        "raw_diamond",
        [
            "...Y....",
            "..yy.y..",
            ".yyyyy..",
            ".yyyyyy.",
            "yyxyyyy.",
            ".yyyyyy.",
            ".syyyys.",
            "sssyyss.",
            ".sssss..",
        ],
    ),
    (
        # A sphere is the one shape that has to be lit rather than drawn, so
        # this is a sphere with one hard hit and a 1px bounce at the base — the
        # one exception S7 allows on the shade side.
        "black_pearl",
        [
            "..kkk...",
            ".kPkkk..",
            "kkkkkkk.",
            "kkkkkkk.",
            "kkkkkkk.",
            ".kkkkkp.",
            "..kkkk..",
            "..oooo..",
        ],
    ),
    (
        # STRAIGHT. Handle, guard and blade on one line, the guard the only
        # thing leaving it — the same rule the knife obeys on both gun sheets,
        # for the same reason: everything else with a hilt here hangs something
        # below its spine.
        "ritual_dagger",
        [
            "...c....",
            "...cc...",
            "...cc...",
            "...cc...",
            "...cc...",
            "..bbbb..",
            "...ll...",
            "...le...",
            "...ll...",
            "...bb...",
        ],
    ),
    (
        # A book on its edge with the block fanned and a ribbon out of it. Lying
        # flat it was the license plate again.
        "bank_ledger",
        [
            "..lll...",
            ".lllll..",
            "llollff.",
            "llollff.",
            "llollff.",
            "llollff.",
            "llollff.",
            "llollef.",
            ".lllff..",
            "..llf...",
        ],
    ),
    (
        # The gem's geometry in black with one crystal window — S21's tier
        # keying: same shape, accent hue does the talking.
        "black_diamond",
        [
            "..kKk...",
            ".kkkkk..",
            "kkkkkkk.",
            "kykkkkk.",
            ".kkkykk.",
            ".kkkkk..",
            "..kkk...",
            "..kkk...",
            "...k....",
        ],
    ),
    (
        # THREE UNEVEN POINTS. A crown is the one object here everybody already
        # knows the silhouette of, so the only way to get it wrong is to make it
        # regular.
        "lost_crown",
        [
            "o.....o.",
            "o..o..o.",
            "o.ooo.oo",
            "oooooooo",
            "oyoooyoo",
            "oooooooo",
            ".oooooo.",
            "..oooo..",
        ],
    ),
    (
        # A reliquary: a house-shaped casket with a spire, standing on feet.
        # The spire is the contour and the only thing above the roofline.
        "sanctuary_relic",
        [
            "...o....",
            "..oyo...",
            "...o....",
            "..ssss..",
            ".ssssss.",
            "sssoosss",
            "ssoyyoss",
            "sssoosss",
            "ssssssss",
            ".ss..ss.",
        ],
    ),
    (
        # Bow, shank, bit — laid on the diagonal S21 asks for, so the shank
        # runs corner to corner instead of down the middle.
        "vault_key",
        [
            "..ooo...",
            ".oo.oo..",
            ".oo.oo..",
            "..ooo...",
            "...oo...",
            "...ooo..",
            "....oo..",
            "....occ.",
            "....oc..",
            "....occ.",
        ],
    ),
    (
        # A ring with a stone big enough to break the band's outline — a royal
        # ring is a gold ring plus one mass, and that mass has to leave the
        # silhouette or nothing has changed.
        "royal_ring",
        [
            "..yy....",
            ".yYyy...",
            ".oyyo...",
            "oo..oo..",
            "o....oo.",
            "o....oo.",
            ".oo..oo.",
            "..oooo..",
            "...oo...",
        ],
    ),
    (
        # A stack of carved faces, each narrower than the one under it. The
        # 1:0.7:0.5 rhythm S17 asks for, made literal.
        "obsidian_totem",
        [
            "..kkk...",
            ".kkkkk..",
            ".kokoko.",
            ".kkkkk..",
            "kkkkkkk.",
            "kkekekk.",
            "kkkkkkk.",
            "kkkkkkkk",
            "kkokkokk",
            "kkkkkkkk",
            ".kkkkkk.",
        ],
    ),
    (
        # A cranium with a gold band across the brow and one socket blown out.
        # The asymmetric socket is the read; a matched pair is a Halloween
        # sticker.
        "ancestor_skull",
        [
            "..bbbb..",
            ".bbbbbb.",
            "bbbbbbbb",
            "oooooooo",
            "bkkbbkbb",
            "bkkbbbbb",
            ".bbbbbb.",
            ".bbbbbb.",
            "..b.b.b.",
            "..b...b.",
        ],
    ),
    # --- AMMUNITION ---------------------------------------------------------
    # Told apart at a glance in a HUD cell the size of a fingernail, and NOT by
    # colour: by COUNT and HEIGHT of the rounds standing in the case. Three
    # short is pistol, four tall is rifle, one big is the AWP, six stubby is the
    # SMG, and the shotgun is the one whose contents are not brass at all. A
    # player reading a box across a dark clearing is deciding whether the walk
    # is for them, and "which calibre" is the only question they have.
    #
    # The CASE is now a box with a lid and a lip rather than an outlined
    # rectangle, so the rounds are standing IN something instead of on top of a
    # line.
    (
        "ammo_pistol",
        [
            "..c.c.c.",
            ".nn.n.nn",
            ".nnnnnnn",
            "VVVVVVVV",
            "vvvvvvvv",
            "vvvvvvvv",
            "vvvvvvvv",
            ".vvvvvv.",
        ],
    ),
    (
        "ammo_rifle",
        [
            ".c.c.c.c",
            ".n.n.n.n",
            ".n.n.n.n",
            ".nnnnnnn",
            "VVVVVVVV",
            "vvvvvvvv",
            "vvvvvvvv",
            "vvvvvvvv",
            ".vvvvvv.",
        ],
    ),
    (
        "ammo_awp",
        [
            "...c....",
            "...n....",
            "..nnn...",
            "..nnn...",
            "..nnn...",
            "..nnn...",
            "KKKKKKKK",
            "kkkkkkkk",
            "kkkkkkkk",
            "kkkkkkk.",
            ".kkkkkk.",
        ],
    ),
    (
        "ammo_smg",
        [
            "cc.cc.cc",
            "nn.nn.nn",
            "nnnnnnnn",
            "VVVVVVVV",
            "vvvvvvvv",
            "vvvvvvvv",
            "vvvvvvvv",
            ".vvvvvv.",
        ],
    ),
    (
        # RED SHELLS ON A BRASS BASE, and this is the only ammunition icon in
        # the game with a colour of its own. It has earned it: a shotgun shell
        # is the one round a player has ever actually held, everybody already
        # knows it is a red plastic tube, and the shell reserve is the smallest
        # and most precious in the game — it should read from further away than
        # the others.
        "ammo_shell",
        [
            ".ee.ee.e",
            ".ee.ee.e",
            ".ee.ee.e",
            ".nn.nn.n",
            "VVVVVVVV",
            "vvvvvvvv",
            "vvvvvvvv",
            "vvvvvvvv",
            ".vvvvvv.",
        ],
    ),
    (
        # The condensed core. Never scattered and never in a crate: the only
        # thing that makes one is overfeeding a rift and shutting it, and what
        # it is WORTH comes off that rift rather than off the catalog — so this
        # frame is the only fixed thing about it. The drop and the bag slot
        # carry the value, the weight, and the SCALE this sprite is drawn at,
        # which is why the art is a cut shard with no baseline detail: it has to
        # survive being drawn at twice the size without reading as a boulder.
        "rift_shard",
        [
            "...Y....",
            "..yyy...",
            ".yyyyy..",
            ".ypppy..",
            "yppyppy.",
            ".ypppy..",
            ".yyppy..",
            "..sppy..",
            "..sss...",
        ],
    ),
]


# ---------------------------------------------------------------------------
# THE ARMOUR, AND IT IS THREE DRAWINGS RATHER THAN TWELVE.
#
# Twelve pieces, and only three SHAPES: a helmet, a cuirass and a pair of
# leggings. The material is the other axis and it is a RECOLOUR — which is
# normally the thing this sheet exists to refuse (S15: three variants of a
# creature have to be three silhouettes, and `test_creature_sheets.py` fails
# the build if they are not).
#
# It is right here for exactly the reason it is wrong there, and the reason is
# what the player is being asked. Two zombies are two THINGS, and telling them
# apart across a dark clearing is a survival question, so they must differ in
# outline. Four helmets are four RUNGS OF ONE LADDER, and the question is not
# "what is that" — the player already knows it is a helmet, the slot label
# says so — it is "is it better than mine". A ladder whose rungs are four
# different shapes is a ladder nobody can order at a glance; a ladder whose
# rungs are one shape in four colours is one everybody can, and it is the same
# rarity ramp this sheet has been teaching since the first night.
#
# So: SLOT SETS THE SHAPE, MATERIAL SETS THE COLOUR — the same split
# `server/app/armor.py` makes about the numbers, said in pixels. A player who
# has learnt that green is leather has learnt it for all three slots at once.
#
# The templates are written in placeholders rather than in letters, so the
# substitution is the only thing that varies and a shape cannot accidentally
# be authored in one material:
#
#     #  the material, at its own step
#     @  the material, lifted one step — the lit crest (S14)
#     x  a recess in VOID: the visor gap, the breastplate seam, the gap
#        between the legs. The one place interior form is allowed a
#        single-pixel line (S6)
_ARMOR_FORMS: dict[str, Art] = {
    # A DOME WITH A FACE CUT OUT OF IT. The crown is the contour and the visor
    # is the only interior mark — at sixteen pixels a helmet is a curve with a
    # dark band across it and nothing else survives. The cheek pieces at the
    # bottom are uneven on purpose: a symmetric helmet reads as a UI icon, and
    # the right one hanging a row lower is the lean (S21) this shape can take
    # without stopping being a helmet.
    "head": [
        "..@@#..",
        ".@####.",
        ".######",
        "#######",
        "##xxx##",
        "#######",
        ".######",
        ".##..##",
        "..#...#",
    ],
    # BRAÇADEIRAS: A PAIR, AND THE PAIR IS THE WHOLE READ.
    #
    # Every other icon on this sheet is one object. This one has to say "two of
    # something you strap on", and there is no way to say that with a single
    # shape — a lone vambrace at 16px is a cuff, which is a bracelet, which is
    # treasure. So: two identical guards, STAGGERED rather than side by side.
    # Side by side is a bilateral figure and reads as a UI glyph (the same
    # reason nothing else here is symmetric); staggered is how a pair of
    # anything is laid on a table.
    #
    # THE STRAP IS THE OBJECT, AND THERE IS EXACTLY ONE OF THEM. The first cut
    # pinched each guard at the wrist to make an hourglass, on the theory that
    # an outline which goes in and comes back out is unlike anything else on
    # the armour sheet. It is — it is a capital T. The second cut put two
    # recessed bands across a plain cuff, which is what a buckle looks like and
    # also, with two enclosed counters stacked in a four-wide box, what a
    # capital B looks like. One band, off centre, and the cuff tapering under
    # it: a counter and a taper is a strapped tube, and the eye has no letter
    # to fall back on.
    "arms": [
        ".@@@.....",
        "####.....",
        "#xx#.....",
        "####.@@@.",
        "####.####",
        ".###.#xx#",
        ".##..####",
        ".....####",
        "......###",
        "......##.",
    ],
    # A CUIRASS: SHOULDERS, A NECK CUT OUT OF THEM, AND A TAPER TO THE WAIST.
    #
    # The two raised pauldrons are the top contour and the notch between them
    # is what makes them pauldrons rather than a flat top edge — a torso icon
    # without a neck is a slab. Under that it is broad and then narrows, which
    # is the one direction none of its neighbours on this sheet go: the
    # trousers fork, the bracers stack, and this closes.
    #
    # The lacing seam runs down the left of centre rather than through it,
    # which is both how a real cuirass is laced and what keeps the icon off its
    # own axis of symmetry.
    "body": [
        "@@@..@@@",
        "########",
        "###xx###",
        "########",
        "########",
        "###x####",
        "########",
        ".######.",
        ".######.",
        "..####..",
    ],
    # CALÇAS: A WAISTBAND AND TWO LEGS THAT END ABOVE THE FLOOR.
    #
    # The band across the top is the read — two vertical bars without one could
    # be anything — and the FORK is what separates this from the cuirass: a
    # breastplate is one closed mass and trousers are one mass that splits. The
    # gap between the legs is two columns rather than one, because a
    # single-column gap at this size is closed by the outline pass and what
    # comes back is an arch.
    #
    # THEY STOP SHORT, and that is a change the boots forced. When legs were
    # the bottom of the body this shape ran to the floor; it cannot now, or the
    # two icons say the same thing about the same part of a person. The right
    # leg still runs two rows longer than the left, which is the lean
    # everything on this sheet has.
    "legs": [
        ".@@@@@@.",
        "########",
        "########",
        "###xx###",
        "###..###",
        "###..###",
        "###..###",
        "###..###",
        "###...##",
        "..#...##",
    ],
    # BOTAS: TWO SHAPES THAT TURN A CORNER.
    #
    # An L is the cheapest unmistakable silhouette in this whole catalog — a
    # shaft going up and a foot going forward — and nothing else on the armour
    # sheet has a horizontal run at the bottom of it. That is the entire design
    # of this icon: the trousers fork downward, the bracers stack, and these
    # turn.
    #
    # They are drawn BIG for their frame, which is the fix the first cut needed:
    # a boot small enough to leave margin on all four sides loses its sole to
    # the contact band and comes back as a block. The foot has to be two rows
    # deep and reach past the shaft, or the corner is not a corner.
    "feet": [
        "@@@..........",
        "###..........",
        "###...@@@....",
        "#xx...###....",
        "######.###...",
        "######.#xx...",
        ".......######",
        ".......######",
    ],
}

#: MATERIAL -> the sheet's own alphabet letter. Four rungs, four materials
#: this catalog already had: rags are cloth, a jacket is leather, plate is
#: metal, and the one modern thing in the game is the sheet's olive — the
#: tactical hue, and the only entry here that is not simply the material's
#: name, because there is no aramid ramp and inventing one for three icons
#: would be a fifth material nothing else on the sheet ever spends.
_ARMOR_LETTERS: dict[str, str] = {
    "cloth": "f",
    "leather": "l",
    "steel": "m",
    "kevlar": "v",
}


def _armor_icons() -> list[tuple[str, Art]]:
    """Twenty icons out of five templates and four letters.

    Keyed to match `server/app/armor.ArmorDef.key` — `{slot}_{material}` —
    which is the same string the loot catalog, the wire and the HUD use. There
    is deliberately no second list of names here: a piece the server can
    produce and this cannot draw is caught by `tests/test_loot_frames.py`, and
    a piece drawn here that the server cannot produce is simply an unused
    frame.
    """
    rows: list[tuple[str, Art]] = []
    for slot, form in _ARMOR_FORMS.items():
        for material, letter in _ARMOR_LETTERS.items():
            art = [
                "".join(
                    letter.upper() if ch == "@" else letter if ch == "#" else ch
                    for ch in line
                )
                for line in form
            ]
            rows.append((f"{slot}_{material}", art))
    return rows


ITEMS += _armor_icons()

# ---------------------------------------------------------------------------
# THE WEAPONS, AND THEY ARE NOT PAINTED BY `paint_form`.
#
# Everything above is banded by the blob rule: a pixel's step comes from where
# it sits in its own mass, under a key at 135deg. That is right for a bottle and
# it is what the guns used to get too — and it is exactly the shading
# `make_guns.py` threw out, because a weapon in this game is drawn from ABOVE on
# a row grid where a pixel's plane is a function of its ROW. The two sheets are
# the same twelve objects, so a player who picks up the thing on the floor has
# to get the thing they were looking at, and for as long as the floor copy was
# lit from the upper left and the held copy was lit from the sky, they did not.
#
# So these rows are painted by `make_guns.paint_rows` — the generator's own
# painter, imported, not reimplemented — with `make_guns`' own material ramps.
# Not a matching palette: THE SAME ONE. A copied constant is a constant that
# drifts, and the whole reason this comment exists is that it already had.
#
# What changes between the two sheets is exactly two things, and both are forced
# by the cell rather than chosen:
#
#   * LENGTH. A held frame is 24px wide and a loot cell is 16, so every map here
#     is the held map with its barrel and stock SHORTENED — S16's rule that a
#     smaller variant deletes rather than shrinks. Class order still holds
#     (knife shortest, AWP longest), it is just compressed;
#   * ORIGIN. A held weapon is centred in its frame because it turns around its
#     grip. One on the ground is planted on the bottom of the cell like every
#     other icon here, so it sits on the tile instead of hovering — and gets the
#     same offset ground shadow, which is what puts it on the same floor as the
#     forty-six items above rather than in a UI.
#
# The muzzle marker `m` is gone: it exists on the held sheet so the tracer knows
# where the barrel ends, and nothing on the floor fires. Everything else is the
# same alphabet — t stock, r receiver, h handguard, b barrel, g grip, n
# magazine, c can, e optic, l lens, k mechanical, x recess.
# ---------------------------------------------------------------------------

#: Weapons whose HELD map is longer than a 16px cell can take, and the shorter
#: map they use here instead. Four of twelve; the other eight use their held map
#: unchanged, which is the point — a list that mostly is not there cannot drift
#: from the sheet it mirrors.
#:
#: The trims are all off the ENDS: barrel, stock, suppressor. Nothing that
#: carries identity moves, so an AK icon still has its wood, its curved bakelite
#: mag and its gas block, and an AWP still has its optic and the one lens accent
#: — they are just standing on a shorter barrel (S16: a smaller variant deletes,
#: it does not scale).
ICON_TRIMS: dict[str, Art] = {
    "ak47": [
        ".......k......",
        "wwwxrrRRkwbbbm",
        "wwwxrrrrkwbbb.",
        ".ffxff.nn.....",
        "...gg...nn....",
        "..gg....nnn...",
        "..g......nn...",
    ],
    "m4a1s": [
        "...kkkk..cccc.",
        "ttxrrRRhhccccm",
        "txrrrrrhhcccc.",
        ".ffxfff.......",
        "...gg..nn.....",
        "..gg...nn.....",
        "..g....nn.....",
    ],
    "xm1014": [
        "..............",
        "ttxrrRRhhbbbbm",
        "ttxrrrrhhbbbb.",
        "..fffxnnnnn...",
        "....gg........",
        "...gg.........",
        "..gg..........",
    ],
    "awp": [
        "...eeell......",
        "ooxrrRRxbbbbbm",
        "ooxrrrrxbbbbb.",
        ".ooxffff......",
        "....gg..nn....",
        "...gg...nn....",
        "...g....nn....",
    ],
}

#: The twelve icons: each weapon's HELD map and HELD palette, trimmed only where
#: the cell cannot take it. There is no second set of drawings here and no
#: second set of ramps — see the comment above.
WEAPONS: list[tuple[str, Palette, Art]] = [
    (key, palette, ICON_TRIMS.get(key, art)) for key, palette, art in guns.GUNS
]


def _weapon_blit(art: Art, ramps: Palette, cell: int) -> Image.Image:
    """One weapon icon, on `make_guns`' row grid and planted on the tile.

    The origin and the ground are the only things this adds. Keyed by the same
    hue-tinted pass every item above gets, off the gun sheet's own ramps: a
    single flat near-black border round twelve weapons and a different, material
    -tinted one round forty-six items is two sheets sharing one atlas, and the
    seam shows on the belt where a pistol sits next to a medkit.
    """
    width, height = guns.art_size(art)
    origin = ((cell - width) // 2, cell - height - PLANT)
    img, plan = _weapon_plan(art, ramps, (cell, cell), origin)
    _key(img, plan)
    _ground(img)
    return img


def _weapon_plan(art: Art, ramps: Palette, size: tuple[int, int],
                 origin: tuple[int, int]) -> tuple[Image.Image, dict]:
    """`guns.paint_rows`' output, plus the plan `_key` needs to tint the border.

    The row grid IS the plan — `guns.ROW_STEP` says which step every authored
    row lands on and the map says which material — so this recovers it from the
    same two tables the painter used rather than sampling the finished pixels
    back into a ramp, which would guess wrong every time two steps of two
    materials happened to resolve to the same colour.
    """
    img = guns.paint_rows(art, ramps, size, origin)
    plan: dict[tuple[int, int], tuple[Ramp, int]] = {}
    ox, oy = origin
    for y, row in enumerate(_pad(art)):
        plane = guns.ROW_STEP[y]
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            key = (ox + x, oy + y)
            if not (0 <= key[0] < size[0] and 0 <= key[1] < size[1]):
                continue
            if ch == "x":
                plan[key] = (guns.VOID, plane)
                continue
            ramp = ramps.get(ch.lower())
            if ramp is None:
                continue
            step = min(plane + 1, len(ramp) - 1) if ch.isupper() else plane
            plan[key] = (ramp, step)
    return img, plan


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "loot"
    out_dir.mkdir(parents=True, exist_ok=True)

    painted = (
        [(key, _blit(art, tile)) for key, art in ITEMS]
        + [(key, _weapon_blit(art, pal, tile)) for key, pal, art in WEAPONS]
    )
    pack([frame for _, frame in painted], tile, tile).save(out_dir / "sheet.png")

    manifest = {
        "tile": tile,
        "frameWidth": tile,
        "frameHeight": tile,
        "frames": len(painted),
        "items": {key: {"frame": index} for index, (key, _) in enumerate(painted)},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(ITEMS)} items + {len(WEAPONS)} weapons @ {tile}x{tile}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
