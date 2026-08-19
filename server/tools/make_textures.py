#!/usr/bin/env python3
"""Asset pipeline: procedural forest terrain textures.

Sibling of make_placeholder_sheet.py + process_sprites.py, but with no "raw"
stage. Characters start as hand- or AI-drawn art that has to be keyed, cropped
and downscaled; terrain is *generated*, so this script writes final-resolution
pixels directly into assets/processed/.

Output (assets/processed/terrain/):
    ground_loam.png    64x64 — a 4x4 grid of 16px floor tiles
    ground_turf.png    64x64
    ground_mud.png     64x64
    ground_litter.png  64x64
    blend.png     8 frames, 16x16   ALPHA STENCILS, graded coverage
    patch.png     6 frames, 32x32   ground stains ("manchas"), flat decal
    rock.png      8 frames, 20x26   solid blocker, 8 recipes, shadow BAKED IN
    tree.png      4 frames, 24x40   solid blocker, overhangs its tile
    deadtree.png  4 frames, 24x40   solid blocker, bare — a blighted TREE tile
    stump.png     4 frames, 16x14   solid blocker, a felled trunk
    grass.png     6 frames, 10x10   decoration, non-solid, sways
    bush.png      5 frames, 20x16   decoration, non-solid, sways, BEHIND bodies
    branch.png    5 frames, 16x7    flat decal, baked into the ground
    leaves.png    6 frames, 16x12   flat decal, baked into the ground
    fern.png      5 frames, 20x18   FOREGROUND decoration, drawn over characters
    campfire.png  8 frames, 24x28   solid blocker, ANIMATED (a frame loop)
    manifest.json

Three shapes of asset, because the world has three kinds of thing in it:

  * The GROUND is square. It tiles, so it must be seamless, and it is the only
    asset the client draws for every single tile. There are FOUR of them and a
    map mixes them — see below.
  * ROCKS, TREES and GRASS are not square. They are silhouettes with alpha that
    sit ON TOP of the ground, bottom-anchored and centred on their tile, the
    same anchoring process_sprites.py gives a character. A tree is 40px tall on
    a 16px tile: the extra 24px is canopy that overhangs the tile above.
  * DECALS (patch, branch, leaves) lie FLAT. They have no silhouette and no
    outline; the client bakes them into the ground canvas, so they cost
    nothing per frame and never occlude a body.

Seamlessness is the whole trick of a ground atlas. Each is generated as ONE
64x64 image from *periodic* value noise — the noise lattice wraps at 64px, so
the left edge is the continuation of the right edge — and then read back as a
4x4 grid of 16px tiles. The client picks its tile with `(tx % 4, ty % 4)`,
which gives 16 distinct-looking floor tiles that are guaranteed to line up,
because they are neighbouring windows into one continuous texture. Choosing a
random variant per tile instead would put a visible seam on every tile
boundary.

FOUR GROUNDS, AND WHY THEY NEED A STENCIL. One soil over a whole map is the
single loudest tell that a forest was generated: the eye finds the 4x4 repeat
in seconds. So the client runs a low-frequency material field over the map and
picks loam, turf, mud or leaf litter per tile. A hard tile boundary between two
soils would just move the tell — a checkerboard instead of a repeat — so the
fringe is dissolved through `blend.png`, eight alpha stencils of increasing
coverage. The client draws the neighbouring soil through the stencil whose
coverage matches how far that tile has crossed the boundary, and the two soils
interlock in ragged pixel-art teeth instead of meeting on a grid line.

Everything is deterministic: the same --seed produces byte-identical PNGs.

Usage:
    python tools/make_textures.py
    python tools/make_textures.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

# Mirrors server/app/config.py TILE_SIZE. The ground atlas is GROUND_TILES
# square, so at tile 16 it is a 64x64 image.
DEFAULT_TILE = 16
GROUND_TILES = 4

# Alpha stencils for the boundary between two soils, coverage ascending. Eight
# is enough that a two-tile-wide fringe never shows the same tooth twice and
# few enough that the sheet stays one tile row tall.
BLEND_STEPS = 8

# Campfire animation. Eight frames is enough for the loop to read as fire and
# short enough that the whole sheet stays under one tile-row of pixels.
CAMPFIRE_FRAMES = 8
CAMPFIRE_FPS = 12

RGBA = tuple[int, int, int, int]
Ramp = list[RGBA]


def rgb(hex_code: str) -> RGBA:
    value = hex_code.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


# --- palette ----------------------------------------------------------------
# Damp forest floor. Kept dark on purpose: the lantern lighting in the client
# multiplies over this, so a bright texture would leave nothing for the light to
# add. Ramps run darkest -> lightest and are indexed by noise.

# GOLD IS THE GROUP'S, and it is the only currency `paint_coin` still strikes:
# catalog value, the platform's quota, a shop price. It is never a thing on the
# floor; it is a number the party earned by extracting.
COIN_RAMP: Ramp = [rgb(c) for c in ("#a05a1c", "#f2a541", "#ffd678", "#fff1c2")]
COIN_OUTLINE = rgb("#482a12")

# DARK GOLD USED TO BE THE SECOND METAL HERE — a purple disc off the same
# painter, kept clear of `--rarity-epic` so a purple glow across a clearing
# could not mean two things. It is no longer struck from anything: it is a
# piece of the anomaly, painted with the anomaly's own prism in
# `make_rift.PRISM`, and `make_coin.py` owns it end to end. The ramp is gone
# rather than kept "in case" — a palette nobody paints with is a palette that
# drifts out of agreement with what is on screen.

# The only near-red in the game, and shared for the same reason as the coin:
# the stain a scene left on the floor (make_scenery) and the wound a bullet
# just opened on a body (make_gore) have to be one material, or the forest has
# two kinds of blood in it. It has to survive the darkness multiply, so the top
# steps go brighter than anything else on the ground — but the mass of a stain
# sits in the bottom two, which are almost black. Bright all the way through
# reads as paint.
BLOOD: Ramp = [rgb(c) for c in ("#1a0507", "#2e070a", "#460c0f", "#5f1216", "#7d1c20", "#a02a26")]

EARTH: Ramp = [rgb(c) for c in ("#1d1a15", "#26221a", "#2f2a20", "#383026", "#43392d")]
MOSS: Ramp = [rgb(c) for c in ("#22291d", "#2b3524", "#33402b", "#3c4c32")]
GRIT: Ramp = [rgb(c) for c in ("#4b4034", "#554839", "#3a3228")]

# The other three soils. They are separated by HUE AND VALUE, not by hue alone:
# under the client's darkness pass everything collapses toward black, and two
# soils that differ only in tint become one soil the moment you step away from
# the lantern. Turf is greener AND lighter, mud is cooler AND darker, litter is
# warmer AND lighter — so the material field is still legible at the edge of
# the beam, which is where the player actually reads the ground.
TURF: Ramp = [rgb(c) for c in ("#182014", "#1e2a19", "#25341f", "#2d4026", "#354d2c")]
TURF_BARE: Ramp = [rgb(c) for c in ("#242017", "#2d271c", "#372f23")]
MUD: Ramp = [rgb(c) for c in ("#101109", "#17180f", "#1e1e15", "#26251b", "#2e2c21")]
MUD_WET: Ramp = [rgb(c) for c in ("#1c2128", "#252c34", "#313944")]
LITTER: Ramp = [rgb(c) for c in ("#211810", "#2b2015", "#352819", "#40301e", "#4b3923")]
LITTER_DRY: Ramp = [rgb(c) for c in ("#43301a", "#513a1e", "#5e4522")]

# Stains dropped on top of a soil — "manchas". Deliberately low contrast: a
# patch is meant to break the repeat, not to be an object the player checks.
PATCH_MOSS: Ramp = [rgb(c) for c in ("#1e2718", "#26331e", "#2f4025", "#384d2c")]
PATCH_PUDDLE: Ramp = [rgb(c) for c in ("#0f1114", "#161a1e", "#1f262b", "#28323a")]
PATCH_SCORCH: Ramp = [rgb(c) for c in ("#100e0c", "#191614", "#231e1b", "#2e2723")]
PATCH_DUST: Ramp = [rgb(c) for c in ("#3a3126", "#463b2d", "#524634", "#5e513c")]
PATCH_ROT: Ramp = [rgb(c) for c in ("#241c12", "#2f2517", "#3a2e1c", "#453721")]
PATCH_GRAVEL: Ramp = [rgb(c) for c in ("#2a2823", "#37342e", "#454139", "#534e44")]

ROCK_RAMP: Ramp = [rgb(c) for c in ("#242327", "#312f34", "#403d43", "#4e4a51", "#5d5860")]
ROCK_OUTLINE = rgb("#131418")

BARK: Ramp = [rgb(c) for c in ("#231a13", "#2e231a", "#3b2d21", "#493829")]
LEAF: Ramp = [rgb(c) for c in ("#1a2618", "#22321f", "#2b3f26", "#354d2d", "#425e37")]
TREE_OUTLINE = rgb("#10160f")

# Dead wood is GREY, not brown. A dead tree drawn in the same bark ramp as a
# living one only reads as a tree that lost its leaves; drained of hue it reads
# as bone, and a stand of them reads as something that happened here.
DEADWOOD: Ramp = [rgb(c) for c in ("#1d1b19", "#2b2825", "#3b3733", "#4b4641", "#5d5750")]
DEAD_OUTLINE = rgb("#0f0e0d")
# The heartwood of a fresh stump: still warm, so a cut trunk reads as recent.
HEARTWOOD: Ramp = [rgb(c) for c in ("#33261a", "#443322", "#55402a", "#664d33")]

# Bushes sit BEHIND the player and in front of the floor, so they are lighter
# than a fern (which is in front and must not fight the character) and darker
# than grass (which is underfoot and catches the lantern first).
SHRUB: Ramp = [rgb(c) for c in ("#151f14", "#1d2b1a", "#263822", "#31462b", "#3d5735")]
# Fallen wood on the floor: read at a glance as "not soil", nothing more.
TWIG: Ramp = [rgb(c) for c in ("#1b150f", "#261d14", "#33281b", "#413324")]
FALLEN_LEAF: Ramp = [rgb(c) for c in ("#2b1f11", "#3a2a16", "#4a361c", "#5a4222", "#6b5029")]

# Campfire. The flame ramp is the one place in this file that goes bright: it is
# the only self-lit object in the game, and the client's darkness pass multiplies
# over everything else. A flame in the same value range as the forest floor would
# have nothing left to read as fire.
FLAME: Ramp = [rgb(c) for c in ("#5c1606", "#a82c0c", "#d9531a", "#f5892a", "#ffc44e", "#fff2bd")]
COAL: Ramp = [rgb(c) for c in ("#140f0c", "#2a1710", "#4d2410", "#8a3a12", "#d4600f")]
TIMBER: Ramp = [rgb(c) for c in ("#241a11", "#332417", "#46311f", "#5e4229")]
TIMBER_OUTLINE = rgb("#0d0907")

BLADE: Ramp = [rgb(c) for c in ("#26331f", "#324428", "#3f5632", "#4d693d")]
# Ferns are FOREGROUND: they draw over the player, so they are deliberately
# darker and cooler than the grass underfoot. A bright silhouette in front of
# the character would read as an obstruction; a dark one reads as depth.
FROND: Ramp = [rgb(c) for c in ("#0b100b", "#131c12", "#1d2b1b", "#2a3f28")]

TRANSPARENT: RGBA = (0, 0, 0, 0)

# Ordered dithering. Blending two ramp steps with a Bayer threshold keeps the
# hard pixel-art edge that a straight linear gradient would smudge away.
BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def pick(ramp: Ramp, value: float, x: int, y: int) -> RGBA:
    """Index a ramp by a 0..1 value, dithering between the two nearest steps."""
    scaled = clamp01(value) * (len(ramp) - 1)
    low = int(scaled)
    if low >= len(ramp) - 1:
        return ramp[-1]
    threshold = (BAYER4[y % 4][x % 4] + 0.5) / 16.0
    return ramp[low + 1] if (scaled - low) > threshold else ramp[low]


# --- the effect field -------------------------------------------------------
# The second drawing vocabulary in this file, and it lives here for the same
# reason the ramps do: an effect is not painted pixel by pixel, it is SUMMED
# into a float field of intensity and resolved once at the end. Overlapping
# shapes then add up — the crossing of two flame tongues is the hot core, a
# shockwave riding over a ground flash is brighter where they meet — which is
# how light actually behaves and is impossible to fake by drawing shapes in
# order.
#
# Written for make_vfx.py and shared with make_rift.py. Two generators drawing
# light out of the same primitives is what keeps the extraction rift lit in the
# same steps as the summon column instead of becoming a second kind of glow.


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


# NEUTRAL ON PURPOSE — the hue is the client's to decide.
#
# Effect sheets are greyscale so they can be multiplied by whoever the effect
# belongs to: an arriving player's roster colour, the fire's core, the
# extraction beacon's cold mint. Ramp the steps here and every tint gets the
# same shape for free.
#
# The top step is pure white: the core of a strike has to be the brightest
# pixel on screen at the moment it lands, or it has no punch — and under a
# multiply it is the step that comes out as the colour itself.
BEAM: Ramp = [
    rgb(c) for c in ("#232329", "#4a4a55", "#7d7d8c", "#b4b4c0", "#e2e2e8", "#ffffff")
]


def quantize_alpha(value: float) -> int:
    """Snap coverage to five steps.

    Smooth alpha on a pixel-art sprite reads as a soft PNG overlay laid on the
    scene; five hard steps read as light with an edge, which is what everything
    else in this game is made of.
    """
    steps = (0, 56, 118, 186, 255)
    return steps[int(clamp01(value) * (len(steps) - 1) + 0.5)]


def add(field: list[list[float]], x: int, y: int, amount: float) -> None:
    if 0 <= y < len(field) and 0 <= x < len(field[0]):
        field[y][x] += amount


def ellipse(
    field: list[list[float]],
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    strength: float,
    hollow: float = 0.0,
) -> None:
    """Fill (or ring) a flattened ellipse into the intensity field.

    `hollow` > 0 turns it into a shockwave: intensity peaks at the rim and
    falls away on both sides, which is what a travelling wave looks like from
    above. A filled ellipse with a dark centre would just look like a hole.
    """
    if rx <= 0.2 or ry <= 0.2:
        return
    for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 1.0:
                continue
            if hollow > 0.0:
                edge = 1.0 - abs(dist - 1.0) / max(hollow, 1e-3)
                if edge <= 0.0:
                    continue
                add(field, x, y, strength * edge)
            else:
                add(field, x, y, strength * (1.0 - dist) ** 1.4)


def resolve(
    field: list[list[float]],
    image: Image.Image,
    ramp: Ramp = BEAM,
    floor: float = 0.07,
    tone: float = 0.92,
    gain: float = 1.1,
) -> None:
    """Paint an intensity field into an image through a ramp.

    The last step of every effect frame. `floor` is what counts as nothing —
    without it the quantizer's lowest step paints a haze over the whole frame.
    """
    px = image.load()
    height = len(field)
    width = len(field[0]) if height else 0
    for y in range(height):
        for x in range(width):
            value = field[y][x]
            if value <= floor:
                continue
            colour: RGBA = pick(ramp, clamp01(value * tone), x, y)
            px[x, y] = (colour[0], colour[1], colour[2], quantize_alpha(value * gain))


# --- periodic value noise ---------------------------------------------------
# Lattice indices wrap with `% cells`, which is what makes the field tileable
# over `size` pixels. Nothing here is fast; it runs on a 64x64 image once.


def lattice(rng: random.Random, cells: int) -> list[list[float]]:
    return [[rng.random() for _ in range(cells)] for _ in range(cells)]


def _fade(t: float) -> float:
    """Quintic, not the usual smoothstep.

    Bilinear interpolation with a cubic fade is only C1: its second derivative
    jumps at every lattice line, and on a low-contrast soil that shows up as a
    faint grid of creases once the camera zooms in. The quintic flattens the
    second derivative at both ends too, and the creases go away.
    """
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def noise_at(grid: list[list[float]], x: float, y: float, cells: int, size: int) -> float:
    fx = x / size * cells
    fy = y / size * cells
    x0 = int(math.floor(fx))
    y0 = int(math.floor(fy))
    tx = _fade(fx - x0)
    ty = _fade(fy - y0)
    x0 %= cells
    y0 %= cells
    x1 = (x0 + 1) % cells
    y1 = (y0 + 1) % cells
    top = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
    bottom = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
    return top * (1 - ty) + bottom * ty


def fbm(grids: list[tuple[list[list[float]], int]], x: float, y: float, size: int) -> float:
    """Sum octaves of periodic noise, normalized to 0..1."""
    total = 0.0
    weight = 0.0
    amplitude = 1.0
    for grid, cells in grids:
        total += amplitude * noise_at(grid, x, y, cells, size)
        weight += amplitude
        amplitude *= 0.5
    return total / weight


def hash01(*values: int) -> float:
    """Deterministic 0..1 from integers. Used for per-pixel grain.

    The avalanche at the end is not optional. FNV alone leaves the high bits of
    the result dominated by the FIRST value mixed in, and since every call site
    here passes (x, y, salt), that puts a strong per-column correlation into
    what is supposed to be white noise — visible on a soil texture as faint
    vertical dotted lines exactly where the speckle lands.
    """
    h = 2166136261
    for value in values:
        h ^= value & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489917) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 0xFFFFFFFF


# --- ground -----------------------------------------------------------------


class Soil:
    """One ground material: a base ramp, a sparse accent, and speckle.

    Every soil is drawn by the same routine and differs only in these numbers.
    That is on purpose — four soils authored by four separate functions drift
    apart in grain size and contrast, and once they are tiled next to each
    other on the same map the seam between them stops reading as a change of
    ground and starts reading as a change of art style.
    """

    def __init__(
        self,
        name: str,
        base: Ramp,
        accent: Ramp,
        accent_at: float,
        grain: float,
        gain: float,
        bias: float,
        speck: Ramp,
        speck_rate: float,
    ):
        self.name = name
        self.base = base
        self.accent = accent
        # Threshold on the accent noise field. Higher = rarer.
        self.accent_at = accent_at
        self.grain = grain
        # Contrast on the base field. `gain` stretches it, `bias` shifts it.
        self.gain = gain
        self.bias = bias
        self.speck = speck
        # Share of pixels replaced by a single bright speck (pebbles, twigs).
        self.speck_rate = speck_rate


# The four soils a map mixes. Order is the manifest order and the client's
# material index, so appending is safe and reordering is not.
SOILS = (
    # Accent thresholds are high and they are the reason the 4x4 repeat stays
    # invisible: the accent is the only feature big enough to recognise, so the
    # rarer it is, the further apart its copies land. Everything the player
    # reads as variety comes from the material field and the client's scatter.
    Soil("loam", EARTH, MOSS, 0.80, 0.26, 1.25, -0.14, GRIT, 0.025),
    Soil("turf", TURF, TURF_BARE, 0.85, 0.30, 1.30, -0.12, GRIT, 0.014),
    Soil("mud", MUD, MUD_WET, 0.88, 0.18, 1.15, -0.06, MUD_WET, 0.012),
    Soil("litter", LITTER, LITTER_DRY, 0.80, 0.34, 1.22, -0.10, LITTER_DRY, 0.028),
)


def make_ground(size: int, seed: int, soil: Soil) -> Image.Image:
    """One seamless size x size floor texture, read back as a grid of tiles."""
    rng = random.Random(seed)
    # High cell counts on purpose, and the LOWEST one is what matters: at 4
    # cells across a 64px atlas the coarsest blob is a whole tile wide, and
    # tiling that across a field of one soil draws a legible 4x4 checker on the
    # floor. Starting at 8 keeps every feature well under a tile, so the repeat
    # has nothing in it big enough to recognise. Structure at map scale is the
    # client's material field's job, not the texture's.
    base_field = [(lattice(rng, cells), cells) for cells in (8, 16, 32)]
    accent_field = [(lattice(rng, cells), cells) for cells in (7, 14)]

    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            base = fbm(base_field, x, y, size)
            # Fine grain breaks up the smooth interpolation into soil speckle.
            grain = (hash01(x, y, seed) - 0.5) * soil.grain
            colour = pick(soil.base, base * soil.gain + soil.bias + grain, x, y)

            # The accent is a faint second surface, not a feature. Kept rare on
            # purpose: the atlas repeats every 4 tiles, and anything big or
            # bright enough to notice turns that repeat into a visible lattice.
            # What the player actually sees as variety is the material field
            # and the client's tufts, neither of which repeats.
            damp = fbm(accent_field, x, y, size)
            if damp > soil.accent_at:
                span = max(1e-3, 1.0 - soil.accent_at)
                colour = pick(soil.accent, (damp - soil.accent_at) / span + grain, x, y)

            if hash01(x, y, seed + 991) > 1.0 - soil.speck_rate:
                colour = soil.speck[int(hash01(y, x, seed) * len(soil.speck)) % len(soil.speck)]

            px[x, y] = colour
    return img


# --- blend stencils ---------------------------------------------------------


def make_blend(size: int, step: int, steps: int, seed: int) -> Image.Image:
    """One alpha stencil: white where the neighbouring soil shows through.

    Coverage climbs with `step`, so the client can pick a stencil by how far a
    tile has crossed a material boundary and get a dissolve rather than a line.
    The pattern is thresholded value noise, NOT a gradient: the client draws
    the other soil through this with `destination-in`, and a soft edge there
    would give a blurred seam in the middle of otherwise hard pixel art.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    rng = random.Random(seed + step * 7717)
    # Two octaves: the coarse one decides the shape of the tooth, the fine one
    # frays its edge so the boundary never comes out as a smooth curve.
    field = [(lattice(rng, cells), cells) for cells in (3, 6)]
    coverage = (step + 0.5) / steps

    values = [
        (fbm(field, x, y, size) + (hash01(x, y, seed + step) - 0.5) * 0.22, x, y)
        for y in range(size)
        for x in range(size)
    ]
    # Threshold by RANK, not by value. Summed value noise clusters hard around
    # 0.5, so a fixed threshold gives a stencil that is empty, empty, empty,
    # then solid — the dissolve collapses into two states. Sorting and cutting
    # at the requested fraction makes every step differ from the last by
    # exactly 1/steps of the tile, which is what a graded set has to do.
    values.sort(key=lambda item: item[0], reverse=True)
    for _, x, y in values[: int(round(size * size * coverage))]:
        px[x, y] = (255, 255, 255, 255)
    return img


# --- ground stains ("manchas") ----------------------------------------------


PATCHES = (
    ("moss", PATCH_MOSS, 0.62, 0.0),
    ("puddle", PATCH_PUDDLE, 0.70, 0.22),
    ("scorch", PATCH_SCORCH, 0.58, 0.0),
    ("dust", PATCH_DUST, 0.55, 0.0),
    ("rot", PATCH_ROT, 0.60, 0.0),
    ("gravel", PATCH_GRAVEL, 0.50, 0.0),
)


def make_patch(size: int, ramp: Ramp, density: float, rim: float, seed: int) -> Image.Image:
    """A soft-edged organic stain, drawn FLAT on the ground.

    Radial falloff times noise, thresholded. The falloff is what keeps it a
    blotch rather than a square of texture; the noise is what keeps its edge
    from being a circle. `rim` lights the last ring of pixels, which is how a
    puddle reads as standing water instead of as dark soil.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    rng = random.Random(seed)
    field = [(lattice(rng, cells), cells) for cells in (2, 4, 8)]
    centre = (size - 1) / 2.0

    # Falloff is squashed on one axis by a random amount, so the stains are not
    # all the same circle at different sizes.
    squash = rng.uniform(0.72, 1.35)
    tilt = rng.uniform(0, math.pi)
    cos_t, sin_t = math.cos(tilt), math.sin(tilt)

    for y in range(size):
        for x in range(size):
            ox = (x - centre) / centre
            oy = (y - centre) / centre
            dx = (ox * cos_t - oy * sin_t)
            dy = (ox * sin_t + oy * cos_t) * squash
            radial = 1.0 - math.sqrt(dx * dx + dy * dy)
            if radial <= -0.35:
                continue
            # ADDED, not multiplied. Multiplying keeps the level sets circular
            # and only varies how fast the circle fades; adding lets the noise
            # push the boundary itself in and out, which is what turns a disc
            # into a stain.
            value = radial + (fbm(field, x, y, size) - 0.42) * 1.15
            if value < 1.0 - density:
                continue
            shade = clamp01((value - (1.0 - density)) / max(density, 1e-3))
            if rim > 0.0 and shade < rim:
                px[x, y] = ramp[-1]
                continue
            px[x, y] = pick(ramp, shade, x, y)
    return img


# --- props ------------------------------------------------------------------
# Rocks, trees and grass are silhouettes: they are drawn into a transparent
# frame, then outlined, so they read against any ground tile underneath.


def outline(img: Image.Image, colour: RGBA) -> None:
    """Add a 1px dark border around the opaque silhouette, in place."""
    px = img.load()
    edges = []
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] != 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < img.width and 0 <= ny < img.height and px[nx, ny][3] != 0:
                    edges.append((x, y))
                    break
    for x, y in edges:
        px[x, y] = colour


def paint_coin(
    img: Image.Image,
    *,
    radius: float | None = None,
    scale_x: float = 1.0,
    shine_x: float = -1.1,
    shine_y: float = -1.1,
    dim: float = 1.0,
    ramp: Ramp = COIN_RAMP,
    edge: RGBA = COIN_OUTLINE,
    groove: float = 0.0,
) -> Image.Image:
    """The disc both currencies are struck from — `ramp` says which metal.

    `scale_x` is a Y-axis squash (1 = face, ~0 = rim). Shine is in pixels
    from the centre so a world light stays put while the coin turns. `dim`
    is the back-face drop so the flip reads. `groove` sinks a ring inside
    the rim; it is measured in NORMALISED radius, so the mark squashes with
    the coin instead of sliding off the face halfway through the spin.
    """
    px = img.load()
    width, height = img.size
    cx = (width - 1) / 2
    cy = (height - 1) / 2
    if radius is None:
        radius = min(width, height) / 2 - 1.15
    rx = max(0.85, radius * max(0.0, scale_x))
    for y in range(height):
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - cy) / radius
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 1:
                continue
            falloff = 1 - dist
            shine = max(
                0.0,
                1 - ((x - cx - shine_x) ** 2 + (y - cy - shine_y) ** 2) ** 0.5 / radius,
            )
            tone = (0.32 + falloff * 0.28 + shine * 0.42) * dim
            if groove:
                tone *= 1 - groove * max(0.0, 1 - abs(dist - 0.7) / 0.18)
            px[x, y] = pick(ramp, tone, x, y)
    outline(img, edge)
    return img


# --- rocks ------------------------------------------------------------------
# Rocks are drawn as EXTRUDED PRISMS, not as shaded blobs. A blob has one
# surface and therefore one shading rule, and at 20px that reads as a lump of
# gravel however carefully it is lit. A prism has a top face and two side
# faces, each a flat band of one colour, and the eye reconstructs the volume
# from the plane break alone — the same trick the reference sheets use. See
# PIXEL-ART-DIRECTION.md: stacked convex masses (§2), top plane 35-45% of the
# silhouette (§3), hard cel bands with no dithering (§7), key light from the
# upper left (§8).
#
# Eight rocks, eight different recipes, because randomising one recipe eight
# times gives eight rocks with the same silhouette and different noise.

# Four stone families. Each is a 5-step ramp that shifts hue as it climbs —
# shadow toward violet/blue, light toward warm ochre (§11) — kept inside this
# game's night value key, which is much darker than the reference sheets. A
# rock painted at reference brightness would read as a lamp on this floor.
ROCK_STONE: dict[str, tuple[Ramp, RGBA]] = {
    "granite": (
        [rgb(c) for c in ("#17161c", "#25232c", "#3b3841", "#565059", "#7a6e64")],
        rgb("#0d0c11"),
    ),
    "sandstone": (
        [rgb(c) for c in ("#1a1410", "#2b2118", "#3f3122", "#5d4830", "#856a43")],
        rgb("#0f0b08"),
    ),
    "basalt": (
        [rgb(c) for c in ("#101319", "#1d222b", "#323945", "#4b535f", "#6b727a")],
        rgb("#07090d"),
    ),
    "limestone": (
        [rgb(c) for c in ("#1b1c23", "#292b34", "#454750", "#63646a", "#87867e")],
        rgb("#121218"),
    ),
}

# A chunk: (cx, base_y, rx, ry, height, sides, jag, skew, taper), every value a
# fraction of the frame — width for the x terms, body height for the y terms —
# so the recipes survive a change of TILE_SIZE.
#   cx, base_y  where the chunk stands
#   rx, ry      rx is the half-width; ry is a RATIO of rx (~0.5 = 55deg pitch)
#   height      how far it is extruded upward
#   sides, jag  vertex count and how far each vertex may be bitten inward
#   skew        lean: horizontal drift of the top face over the extrusion
#   taper       how much the section shrinks on the way up (shards, spires)
ROCK_RECIPES: dict[str, dict] = {
    # Wide table rock. One dominant top plane, deliberately the flattest of the
    # eight, so the set has a clear horizontal anchor.
    "slab": {
        "stone": "limestone",
        "cracks": 2,
        "chunks": [
            (0.30, 0.84, 0.19, 0.83, 0.10, 5, 0.24, 0.02, 0.05),
            (0.53, 1.00, 0.41, 0.81, 0.15, 6, 0.20, -0.02, 0.04),
        ],
    },
    # Standing stone: tall, narrow, leaning. Height:footprint ~1.6, the top of
    # the range (§17).
    "monolith": {
        "stone": "basalt",
        "cracks": 1,
        "chunks": [
            (0.44, 1.00, 0.23, 0.86, 0.49, 5, 0.18, 0.12, 0.16),
            (0.69, 1.00, 0.16, 0.88, 0.21, 5, 0.22, -0.04, 0.08),
        ],
    },
    # Three masses stacked at 1 : 0.7 : 0.5, the size rhythm from §17.
    "stack": {
        "stone": "granite",
        "cracks": 1,
        "chunks": [
            (0.50, 1.00, 0.32, 0.83, 0.14, 6, 0.20, 0.00, 0.05),
            (0.38, 0.78, 0.23, 0.86, 0.13, 5, 0.22, 0.06, 0.08),
            (0.62, 0.58, 0.16, 0.88, 0.10, 5, 0.24, -0.05, 0.10),
        ],
    },
    # Fanned shards: the spikiest silhouette in the set, and the only one whose
    # top faces are small enough to carry no cracks.
    "shards": {
        "stone": "basalt",
        "cracks": 0,
        "chunks": [
            (0.27, 1.00, 0.13, 0.66, 0.30, 5, 0.16, -0.07, 0.34),
            (0.44, 1.00, 0.14, 0.66, 0.54, 5, 0.14, 0.06, 0.40),
            (0.60, 0.96, 0.12, 0.68, 0.40, 5, 0.16, 0.09, 0.36),
            (0.75, 1.00, 0.11, 0.70, 0.22, 4, 0.18, 0.04, 0.26),
        ],
    },
    # One boulder cleaved in two. The gap between the halves is the silhouette
    # feature, so the halves stand apart far enough for the floor to show
    # through — overlap them and the split is just a drawn line.
    "split": {
        "stone": "sandstone",
        "cracks": 1,
        "chunks": [
            (0.28, 1.00, 0.23, 0.83, 0.34, 5, 0.20, 0.07, 0.12),
            (0.73, 1.00, 0.23, 0.86, 0.26, 5, 0.22, -0.07, 0.10),
            (0.50, 1.00, 0.11, 0.88, 0.08, 4, 0.24, 0.00, 0.08),
        ],
    },
    # Low rubble: wide, ragged, no single dominant mass. The horizontal
    # counterweight to the monolith.
    "rubble": {
        "stone": "granite",
        "cracks": 0,
        "chunks": [
            (0.20, 0.90, 0.15, 0.86, 0.09, 5, 0.22, 0.02, 0.08),
            (0.46, 1.00, 0.20, 0.83, 0.12, 5, 0.20, -0.04, 0.06),
            (0.69, 0.96, 0.17, 0.86, 0.10, 5, 0.22, 0.05, 0.08),
            (0.85, 1.00, 0.11, 0.88, 0.07, 4, 0.24, 0.00, 0.10),
            (0.33, 0.74, 0.12, 0.88, 0.08, 4, 0.26, 0.03, 0.12),
        ],
    },
    # Asymmetric wedge: one steep face, one long ramp. Carries the largest skew
    # in the set, which is what stops the eight from averaging out upright.
    "wedge": {
        "stone": "sandstone",
        "cracks": 2,
        "chunks": [
            (0.40, 1.00, 0.31, 0.81, 0.30, 5, 0.18, 0.26, 0.26),
            (0.75, 1.00, 0.16, 0.86, 0.11, 5, 0.22, -0.05, 0.08),
        ],
    },
    # The bottom of the ladder. Detail is DELETED, not shrunk (§16): three
    # tones instead of five, no crest accent, no cracks.
    "pebbles": {
        "stone": "limestone",
        "cracks": 0,
        "lod": True,
        "chunks": [
            (0.37, 1.00, 0.13, 0.86, 0.07, 5, 0.22, 0.02, 0.10),
            (0.62, 0.98, 0.10, 0.88, 0.06, 4, 0.24, -0.02, 0.12),
            (0.50, 0.80, 0.08, 0.91, 0.05, 4, 0.26, 0.03, 0.14),
        ],
    },
}

# Reserved at the bottom of the frame for the cast shadow, in fractions of the
# frame height. The rock stands on top of this band, not in it.
ROCK_SHADOW_BAND = 0.16


def _rock_poly(
    cx: float, cy: float, rx: float, ry: float, sides: int, jag: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    """An irregular convex-ish top face: vertices walked in angle order so the
    ring never self-crosses, each pulled inward by its own bite (§15)."""
    start = rng.uniform(0, math.tau)
    points = []
    for index in range(sides):
        angle = start + math.tau * index / sides + rng.uniform(-0.10, 0.10)
        radius = 1.0 - rng.uniform(0.0, jag)
        points.append((round(cx + math.cos(angle) * rx * radius),
                       round(cy + math.sin(angle) * ry * radius)))
    return points


def _rock_prism(
    size: tuple[int, int], chunk: tuple, width: int, body_h: int, base: float,
    rng: random.Random,
) -> tuple[Image.Image, Image.Image, list[tuple[float, float]]]:
    """Extrude one chunk. Returns (whole body mask, top face mask, top polygon).

    The body is every polygon from the base to the top stamped in place; the
    top face is the last one. Subtracting gives the vertical sides, and that
    subtraction — not a normal — is what makes the plane break land on an exact
    pixel row.
    """
    fx, fy, frx, fry, fh, sides, jag, skew, taper = chunk
    cx = fx * (width - 1)
    base_y = base - (1.0 - fy) * body_h
    rx = max(1.5, frx * width)
    # The top face is foreshortened by the camera pitch, so its depth is a
    # fixed fraction of its width (§3) — never a fraction of the frame, which
    # is what shrank it to a two-pixel sliver and killed the volume.
    ry = max(1.5, fry * rx)
    height = max(1.0, fh * body_h)
    poly = _rock_poly(cx, base_y, rx, ry, sides, jag, rng)

    body = Image.new("1", size, 0)
    draw = ImageDraw.Draw(body)
    steps = max(1, int(round(height)))
    top = Image.new("1", size, 0)
    for step in range(steps + 1):
        t = step / steps
        shift_x = skew * width * t
        shift_y = -height * t
        keep = 1.0 - taper * t
        pts = [
            (x * keep + cx * (1 - keep) + shift_x,
             y * keep + base_y * (1 - keep) + shift_y)
            for x, y in poly
        ]
        draw.polygon(pts, fill=1)
        if step == steps:
            ImageDraw.Draw(top).polygon(pts, fill=1)
            cap = pts
    return body, top, cap


def _rock_faces(poly: list[tuple[float, float]], width: int) -> dict[int, int]:
    """Which ramp step each COLUMN of the sides takes.

    A prism's vertical faces are the edges of its top polygon dragged
    downward, so an edge's outward normal decides the whole column of pixels
    under it. Shading by distance from the chunk's centre instead — which is
    what a blob does — gives two soft bands and a sack; shading by edge gives
    the hard planar break the reference sheets are built on (§2, §3).

    Only the edges facing the camera are visible. Where two of them cover the
    same column the FRONT one wins, because that is the face that occludes.
    Each normal is read against the key at 135deg: facing left is lit, facing
    right is in shade, facing the viewer sits between.
    """
    count = len(poly)
    cx = sum(x for x, _ in poly) / count
    cy = sum(y for _, y in poly) / count
    columns: dict[int, tuple[float, int]] = {}
    for index in range(count):
        x0, y0 = poly[index]
        x1, y1 = poly[(index + 1) % count]
        if x1 == x0:
            continue
        nx, ny = (y1 - y0), -(x1 - x0)
        # Wind-independent: flip the normal until it points away from the
        # centroid, so the recipe order of the vertices cannot invert the light.
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        if nx * (mid_x - cx) + ny * (mid_y - cy) < 0:
            nx, ny = -nx, -ny
        length = math.hypot(nx, ny) or 1.0
        nx, ny = nx / length, ny / length
        if ny <= 0.05:
            continue
        step = 3 if nx < -0.30 else (1 if nx > 0.30 else 2)
        lo, hi = sorted((x0, x1))
        for x in range(max(0, int(math.floor(lo))), min(width, int(math.ceil(hi)) + 1)):
            t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            depth = y0 + (y1 - y0) * min(1.0, max(0.0, t))
            if x not in columns or depth > columns[x][0]:
                columns[x] = (depth, step)
    return {x: step for x, (_, step) in columns.items()}


def _rock_crest(img: Image.Image, top_mask, ramp: Ramp, accent: int) -> None:
    """Roll the far edge of a top face off by one step.

    A flat top and a flat side meeting at a hard value jump reads as a folded
    sheet. One step of roll on the edge that faces away from the key gives the
    plane a thickness, and it is the only place on a rock where two steps are
    allowed to touch without a plane break between them (§7).
    """
    px = img.load()
    mask = top_mask.load()
    for y in range(img.height):
        for x in range(img.width):
            if not mask[x, y]:
                continue
            down = y + 1 >= img.height or not mask[x, y + 1]
            right = x + 1 >= img.width or not mask[x + 1, y]
            if down or right:
                px[x, y] = ramp[accent]


def _rock_crack(
    img: Image.Image, top_mask, ramp: Ramp, rng: random.Random, count: int,
) -> None:
    """Split a top face with 1px fissures: dark line, one lit lip above it.

    The lip is what stops a crack reading as a scratch — a real fissure has a
    near wall catching the key and a far wall in shadow.
    """
    mask = top_mask.load()
    cells = [(x, y) for y in range(img.height) for x in range(img.width) if mask[x, y]]
    if len(cells) < 24:
        return
    px = img.load()
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    for _ in range(count):
        x = float(rng.choice(range(min(xs), max(xs) + 1)))
        y = float(rng.uniform(min(ys), max(ys)))
        drift = rng.uniform(-0.8, 0.8)
        for _ in range(max(xs) - min(xs) + 2):
            ix, iy = int(round(x)), int(round(y))
            inside = (
                0 <= ix < img.width and 0 <= iy < img.height and mask[ix, iy]
                and (iy + 1 < img.height and mask[ix, iy + 1])
            )
            if inside:
                # Two steps under the top face, never the contact black: a
                # crack cut to step 0 punches a hole straight through the rock.
                px[ix, iy] = ramp[2]
                if iy > 0 and mask[ix, iy - 1]:
                    px[ix, iy - 1] = ramp[4]
            x += 1
            y += drift * rng.uniform(0.2, 1.0)
            if not (min(xs) - 1 <= x <= max(xs) + 1):
                break


def _rock_shadow(
    size: tuple[int, int], body: Image.Image, tone: RGBA,
) -> Image.Image:
    """The cast shadow, offset down-right off the footprint (§9).

    Drawn as a flat two-band ellipse sized from the FOOTPRINT, not the
    silhouette — a shadow that traces the outline reads as a mirror, and the
    reference sheets never do it.
    """
    layer = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()
    columns = [
        (x, max(y for y in range(size[1]) if px[x, y][3] != 0))
        for x in range(size[0])
        if any(px[x, y][3] != 0 for y in range(size[1]))
    ]
    if not columns:
        return layer
    left = min(x for x, _ in columns)
    right = max(x for x, _ in columns)
    bottom = max(y for _, y in columns)
    span = right - left + 1
    cx = (left + right) / 2 + span * 0.12          # offset right  (§9)
    cy = bottom + max(1.0, size[1] * 0.04)         # offset down   (§9)
    rx = span * 0.55
    ry = max(1.5, rx * 0.32)
    draw = ImageDraw.Draw(layer)
    outer = (tone[0], tone[1], tone[2], 46)
    core = (tone[0], tone[1], tone[2], 92)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=outer)
    draw.ellipse((cx - rx * 0.66, cy - ry * 0.62, cx + rx * 0.66, cy + ry * 0.62),
                 fill=core)
    return layer


def make_rock(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the eight rocks, by name. Prisms, hard bands, cast shadow."""
    recipe = ROCK_RECIPES[kind]
    ramp, edge = ROCK_STONE[recipe["stone"]]
    lod = recipe.get("lod", False)
    # Full detail spends all five steps: top, lit face, near face, shade face,
    # contact. The pebbles get three (§16), so their faces are clamped.
    top_i, side_i, accent_i = (2, 1, 2) if lod else (4, 2, 3)

    size = (width, height)
    body = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()
    band = height * ROCK_SHADOW_BAND
    base = height - 1 - band
    body_h = base - 1

    for chunk in recipe["chunks"]:
        mask, top, poly = _rock_prism(size, chunk, width, body_h, base, rng)
        solid = mask.load()
        cap = top.load()
        faces = _rock_faces(poly, width)

        # Seam occlusion: whatever this chunk lands against loses a step, so
        # two masses meeting read as one in front of the other (§10).
        for y in range(height):
            for x in range(width):
                if solid[x, y] or px[x, y][3] == 0:
                    continue
                if any(
                    0 <= x + dx < width and 0 <= y + dy < height and solid[x + dx, y + dy]
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                ):
                    px[x, y] = ramp[0]

        for y in range(height):
            for x in range(width):
                if not solid[x, y]:
                    continue
                if cap[x, y]:
                    px[x, y] = ramp[top_i]
                else:
                    step = faces.get(x, side_i)
                    px[x, y] = ramp[min(step, side_i) if lod else step]

        _rock_crest(body, top, ramp, accent_i)
        if recipe["cracks"]:
            _rock_crack(body, top, ramp, rng, recipe["cracks"])

    # Contact darkening, INSIDE the silhouette and above the cast shadow (§10).
    for x in range(width):
        column = [y for y in range(height) if px[x, y][3] != 0]
        if not column:
            continue
        floor = max(column)
        px[x, floor] = ramp[0]
        if not lod and floor - 1 in column:
            px[x, floor - 1] = ramp[min(1, len(ramp) - 1)]

    outline(body, edge)
    shadow = _rock_shadow(size, body, ramp[0])
    return Image.alpha_composite(shadow, body)


def make_tree(width: int, height: int, tile: int, rng: random.Random) -> Image.Image:
    """Trunk rooted in its own tile, canopy overhanging the tile above."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    cx = (width - 1) / 2.0
    trunk_half = rng.uniform(2.0, 3.0)
    # Trunk runs up INTO the canopy, otherwise the two read as separate objects
    # with a gap of ground showing between them.
    trunk_top = height * rng.uniform(0.40, 0.48)
    lean = rng.uniform(-0.06, 0.06)

    for y in range(height - 1, int(trunk_top) - 1, -1):
        centre = cx + (height - y) * lean
        # Flare at the base so the trunk plants instead of floating.
        half = trunk_half + max(0.0, (y - (height - 4)) * 0.55)
        for x in range(width):
            offset = x - centre
            if abs(offset) > half:
                continue
            # Bark: dark on the right (away from the light), grooved vertically.
            shade = clamp01(0.72 - offset / max(half, 0.1) * 0.42)
            shade += (hash01(x, y, 41) - 0.5) * 0.25
            px[x, y] = pick(BARK, shade, x, y)

    # Canopy: a cluster of blobs so the silhouette is lumpy, not a circle.
    blob_cx = cx + rng.uniform(-1.0, 1.0)
    blob_cy = height * 0.28
    blobs = [(blob_cx, blob_cy, min(width, height * 0.55) * 0.46)]
    for _ in range(rng.randint(3, 4)):
        blobs.append(
            (
                blob_cx + rng.uniform(-width * 0.28, width * 0.28),
                blob_cy + rng.uniform(-height * 0.10, height * 0.14),
                min(width, height * 0.55) * rng.uniform(0.24, 0.36),
            )
        )

    for y in range(height):
        for x in range(width):
            best = 0.0
            for bx, by, radius in blobs:
                dx = (x - bx) / radius
                dy = (y - by) / (radius * 0.86)
                dist = dx * dx + dy * dy
                if dist < 1.0:
                    best = max(best, 1.0 - math.sqrt(dist))
            if best <= 0.0:
                continue
            # Light from up-left again, plus leaf-scale noise for texture.
            lit = clamp01(0.30 + best * 0.55 - (y - blob_cy) / height * 0.6)
            lit += (hash01(x, y, 613) - 0.5) * 0.42
            px[x, y] = pick(LEAF, lit, x, y)

    outline(img, TREE_OUTLINE)
    return img


def make_fern(width: int, height: int, rng: random.Random) -> Image.Image:
    """A low bush of arcing fronds. Drawn IN FRONT of characters.

    This is the depth trick: a handful of these scattered over open ground means
    the player walks behind foliage instead of across a flat plane, and it costs
    one sprite plus a draw pass. Kept sparse and dark so it never fights the
    character for attention.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    root_x = width / 2.0
    for _ in range(rng.randint(11, 15)):
        # Fronds fan out from a common base, arcing over as they rise.
        angle = rng.uniform(-1.2, 1.2)
        length = rng.uniform(height * 0.6, height * 1.1)
        arc = rng.uniform(0.4, 1.1) * (1 if angle >= 0 else -1)
        x = root_x + rng.uniform(-2.0, 2.0)
        y = float(height - 1)
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            # Straighten near the root, curl over near the tip.
            bend = angle + arc * t * t
            x += math.sin(bend) * 0.9
            y -= math.cos(bend) * 0.9
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= ix < width and 0 <= iy < height):
                break
            # Only the tips catch any light; the mass stays near-black so the
            # bush reads as a silhouette against lit ground.
            px[ix, iy] = pick(FROND, t * t * 0.95, ix, iy)
            # Thicken toward the root so it has a body, not just strands.
            thickness = 2 if t < 0.35 else 1
            for offset in range(1, thickness + 1):
                if ix + offset < width:
                    px[ix + offset, iy] = pick(FROND, t * t * 0.7, ix + offset, iy)
    return img


# --- campfire ---------------------------------------------------------------
# The only animated prop, and the only light source that is actually drawn
# rather than composited. Frames are a LOOP: every wobble is a sine of the frame
# phase (or an integer multiple of it), so frame N-1 hands back to frame 0 with
# no snap. Nothing here uses rng — an unseeded jitter would make the loop stutter
# at the wrap even though each frame looked fine on its own.


def _blob(px, cx: float, cy: float, radius: float, ramp: Ramp, shade: float) -> None:
    """A small round mass, lit from the upper left. Used for the pit stones."""
    r2 = radius * radius
    for y in range(int(cy - radius) - 1, int(cy + radius) + 2):
        for x in range(int(cx - radius) - 1, int(cx + radius) + 2):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy > r2:
                continue
            lit = clamp01(shade + (-dy / radius) * 0.28 + (-dx / radius) * 0.18)
            try:
                px[x, y] = pick(ramp, lit, x, y)
            except IndexError:
                pass


def _flame_field(width: int, height: int, cx: float, base_y: float,
                 reach: float, phase: float) -> list[list[float]]:
    """Accumulated heat, 0 outside the flame and >1 in its core.

    Three tongues of different width, height and sway rate are summed rather
    than drawn: overlapping tongues add up, so the place where they cross comes
    out hottest, which is where a real flame is brightest too. Drawing them as
    separate shapes gives three flames standing next to each other instead.
    """
    heat = [[0.0] * width for _ in range(height)]
    tongues = (
        # (half width, height ratio, sway px, sway harmonic, phase offset)
        (width * 0.24, 0.80, 1.1, 1, 0.0),
        (width * 0.15, 1.00, 1.9, 2, 2.1),
        (width * 0.10, 0.62, 2.4, 3, 4.3),
    )
    for half_w, tall, sway, harmonic, offset in tongues:
        span = reach * tall * (0.92 + 0.08 * math.sin(phase * 2 + offset))
        steps = int(span * 3)
        for step in range(steps + 1):
            t = step / max(steps, 1)
            # Lean grows with height: the base is anchored in the wood, the tip
            # is what the air is moving.
            lean = math.sin(phase * harmonic + offset + t * 2.6) * sway * t
            fx = cx + lean
            fy = base_y - t * span
            # Tapered: full width at the base, a point at the tip.
            half = max(0.6, half_w * (1.0 - t) ** 0.62)
            for x in range(int(fx - half) - 1, int(fx + half) + 2):
                if not 0 <= x < width:
                    continue
                y = int(round(fy))
                if not 0 <= y < height:
                    continue
                falloff = 1.0 - abs(x - fx) / half
                if falloff <= 0.0:
                    continue
                heat[y][x] += falloff * (1.0 - t * 0.45)
    return heat


def make_campfire(width: int, height: int, frame: int, frames: int) -> Image.Image:
    """One frame of a lit campfire: stone ring, logs, coals, flame, sparks.

    Read order matters more than detail at this size. The silhouette is three
    bands stacked bottom to top — a broken ring of stones, crossed logs with
    burning ends, and the flame — and each one is drawn in a value range the
    others do not use, so the whole prop still resolves when the client scales
    it down to a couple of tiles on screen.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    phase = math.tau * frame / frames
    cx = (width - 1) / 2.0
    ring_y = height - 1.0 - height * 0.11
    ring_rx = width * 0.30
    ring_ry = max(1.8, height * 0.075)
    # Everything the fire does breathes on one slow pulse.
    pulse = 0.5 + 0.5 * math.sin(phase)

    # A BROKEN ring: seven stones with gaps between them. A closed ring at this
    # scale merges into one grey slab and the pit stops being a pit.
    stones = []
    for i in range(5):
        angle = math.tau * i / 5 + 0.55
        stones.append(
            (
                cx + math.cos(angle) * ring_rx,
                ring_y + math.sin(angle) * ring_ry,
                math.sin(angle),
                1.05 + 0.45 * abs(math.cos(angle * 2.3)),
            )
        )

    for sx, sy, facing, radius in stones:
        if facing < 0:
            _blob(px, sx, sy - 0.5, radius, ROCK_RAMP, 0.34)

    # Coal bed: charred ground with embers that brighten on the pulse.
    coal_rx = ring_rx * 0.82
    coal_ry = ring_ry * 0.9
    for y in range(int(ring_y - coal_ry) - 1, int(ring_y + coal_ry) + 2):
        for x in range(int(cx - coal_rx) - 1, int(cx + coal_rx) + 2):
            if not (0 <= x < width and 0 <= y < height):
                continue
            dx = (x - cx) / coal_rx
            dy = (y - ring_y) / max(coal_ry, 0.6)
            dist = dx * dx + dy * dy
            if dist > 1.0:
                continue
            ember = (1.0 - dist) * 0.7 + hash01(x, y, 77) * 0.5
            px[x, y] = pick(COAL, ember * (0.5 + pulse * 0.5), x, y)

    # Three logs crossing the pit, ends poking out past the stones so the
    # silhouette has something sticking out of it.
    # Two logs lying across the pit and one leaning in from the right. Angles
    # stay shallow: anything steeper walks off the bottom of the frame, which
    # reads as a leg rather than as firewood.
    logs = ((-0.44, -0.05, 0.20), (0.44, -0.02, math.pi - 0.24), (0.40, -0.13, math.pi - 0.05))
    for ox, oy, angle in logs:
        length = width * 0.58
        lx = cx + ox * width
        ly = ring_y + oy * height
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            x = int(round(lx + math.cos(angle) * step))
            y = int(round(ly + math.sin(angle) * step * 0.42))
            if not (0 <= x < width and 0 <= y < height):
                continue
            grain = (hash01(x, y, 151) - 0.5) * 0.35
            # The end nearest the middle is glowing, not wood any more.
            burn = clamp01(1.0 - abs(t - 0.62) * 3.2)
            for w in (0, 1):
                yy = y + w
                if not 0 <= yy < height:
                    continue
                if burn > 0.4:
                    px[x, yy] = pick(COAL, 0.5 + burn * 0.45 * (0.6 + pulse * 0.4), x, yy)
                else:
                    px[x, yy] = pick(TIMBER, clamp01(0.62 - w * 0.3 + grain), x, yy)

    # Flame.
    reach = height * 0.56 * (0.86 + 0.14 * math.sin(phase * 2 + 0.6))
    heat = _flame_field(width, height, cx, ring_y - 1.0, reach, phase)
    for y in range(height):
        for x in range(width):
            value = heat[y][x]
            if value < 0.30:
                continue
            # Divided, not scaled: three overlapping tongues push the sum well
            # past 1, and mapping that straight onto the ramp made every lit
            # pixel the top step — a white blob with no fire in it.
            #
            # The height term is the other half of that: a flame is hottest at
            # its root and cools on the way up, so without it the tips came out
            # as bright as the core and the shape lost its direction.
            rise = clamp01((ring_y - y) / max(reach, 1.0))
            px[x, y] = pick(FLAME, clamp01((value - 0.28) / 1.9) * (1.0 - rise * 0.34), x, y)

    # Front of the ring, over the flame's feet — this is what makes the fire
    # read as burning in a pit rather than on top of one.
    for sx, sy, facing, radius in stones:
        if facing >= 0:
            _blob(px, sx, sy, radius + 0.55, [ROCK_OUTLINE], 1.0)
            _blob(px, sx, sy, radius, ROCK_RAMP, 0.5)

    # A few sparks riding the column. Their height is keyed to the frame index
    # so they travel up the loop instead of blinking in place.
    for i in range(4):
        rise = ((frame + i * 2) % frames) / frames
        sx = int(round(cx + math.sin(phase + i * 1.9) * width * 0.14))
        sy = int(round(ring_y - reach * 0.8 - rise * height * 0.32))
        if 0 <= sx < width and 0 <= sy < height and px[sx, sy][3] == 0:
            px[sx, sy] = pick(FLAME, 0.45 + (1 - rise) * 0.45, sx, sy)

    return img


def make_grass(width: int, height: int, rng: random.Random) -> Image.Image:
    """A tuft of blades rising from the bottom edge. Decoration only."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    for _ in range(rng.randint(5, 9)):
        root = rng.uniform(width * 0.15, width * 0.85)
        length = rng.uniform(height * 0.55, height * 1.0)
        bend = rng.uniform(-0.45, 0.45)
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            x = int(round(root + bend * step * t))
            y = height - 1 - step
            if not (0 <= x < width and 0 <= y < height):
                break
            # Tips catch the light, roots stay in shadow.
            px[x, y] = pick(BLADE, 0.15 + t * 0.85, x, y)
    return img


def make_dead_tree(width: int, height: int, rng: random.Random) -> Image.Image:
    """A bare trunk with forked limbs. Same footprint as a living tree.

    Drawn on a TREE tile the client has decided is blighted, so it must occupy
    the same frame and anchor identically — a dead tree that sat differently on
    its tile would make a blighted stand pop as the material changed. What
    changes is the silhouette: no canopy mass, so the sky (such as it is) comes
    through, and a grove of them opens sightlines that a living thicket closes.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    cx = (width - 1) / 2.0
    lean = rng.uniform(-0.10, 0.10)
    trunk_top = height * rng.uniform(0.20, 0.30)
    trunk_half = rng.uniform(1.6, 2.4)

    def limb(x: float, y: float, angle: float, length: float, thick: float, depth: int) -> None:
        """One tapering branch, forking twice. Recursion is the whole shape."""
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            # Branches curl as they thin, so the silhouette is never a starburst.
            bend = angle + math.sin(t * 2.2) * 0.18
            x += math.sin(bend)
            y -= math.cos(bend)
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= ix < width and 0 <= iy < height):
                return
            half = max(0.0, thick * (1.0 - t))
            for offset in range(-int(half), int(half) + 1):
                jx = ix + offset
                if 0 <= jx < width:
                    px[jx, iy] = pick(DEADWOOD, 0.28 + t * 0.5 - offset * 0.12, jx, iy)
        if depth <= 0:
            return
        for side in (-1, 1):
            limb(
                x,
                y,
                angle + side * rng.uniform(0.35, 0.75),
                length * rng.uniform(0.44, 0.62),
                thick * 0.55,
                depth - 1,
            )

    for y in range(height - 1, int(trunk_top) - 1, -1):
        centre = cx + (height - y) * lean
        half = trunk_half + max(0.0, (y - (height - 5)) * 0.5)
        for x in range(width):
            offset = x - centre
            if abs(offset) > half:
                continue
            shade = clamp01(0.68 - offset / max(half, 0.1) * 0.40)
            shade += (hash01(x, y, 811) - 0.5) * 0.28
            px[x, y] = pick(DEADWOOD, shade, x, y)

    # Three limbs off the top of the trunk, each forking twice.
    for _ in range(rng.randint(3, 4)):
        limb(
            cx + (height - trunk_top) * lean + rng.uniform(-1.0, 1.0),
            trunk_top + rng.uniform(0.0, height * 0.14),
            rng.uniform(-1.15, 1.15),
            height * rng.uniform(0.16, 0.26),
            2.0,
            2,
        )

    outline(img, DEAD_OUTLINE)
    return img


def make_stump(width: int, height: int, rng: random.Random) -> Image.Image:
    """A felled trunk, cut face up. Growth rings are the whole read."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    cx = (width - 1) / 2.0
    # Wide and low. A stump the proportions of a barrel is a barrel; the read
    # is "something was cut down here", and that lives entirely in a broad cut
    # face sitting close to the ground.
    rx = width * rng.uniform(0.40, 0.46)
    ry = max(2.0, rx * 0.42)
    top_y = height - 1.0 - ry - rng.uniform(1.0, 2.5)
    lumps = [(rng.uniform(0.06, 0.14), rng.uniform(0, math.tau)) for _ in range(2)]

    def edge(angle: float) -> float:
        """Radius multiplier at this angle — bark is not a smooth cylinder."""
        wobble = 1.0
        for index, (amp, phase) in enumerate(lumps):
            wobble += amp * math.sin(angle * (index + 3) + phase)
        return wobble

    # Bark sides: the cut ellipse extruded down to the ground.
    for y in range(int(top_y), height):
        for x in range(width):
            dx = (x - cx) / (rx * edge(0.0 if x >= cx else math.pi))
            if dx * dx > 1.0:
                continue
            shade = clamp01(0.55 - dx * 0.40 + (hash01(x, y, 97) - 0.5) * 0.34)
            # Vertical grain: a plain gradient reads as metal at this size.
            if hash01(x, 0, 313) > 0.72:
                shade -= 0.18
            px[x, y] = pick(DEADWOOD, shade, x, y)

    # Cut face: concentric rings in warm heartwood, so it reads as fresh.
    for y in range(int(top_y - ry) - 1, int(top_y + ry) + 2):
        for x in range(width):
            if not (0 <= y < height):
                continue
            dx = (x - cx) / rx
            dy = (y - top_y) / ry
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > edge(math.atan2(dy, dx)):
                continue
            # Alternating hard rings, not a smooth sine: at 6px across, a
            # gradient of rings averages out into one flat disc.
            ring = 1.0 if math.sin(dist * 11.0) > 0 else 0.0
            px[x, y] = pick(HEARTWOOD, 0.22 + ring * 0.62 - dist * 0.15, x, y)

    outline(img, DEAD_OUTLINE)
    return img


def make_bush(width: int, height: int, rng: random.Random) -> Image.Image:
    """A round shrub. Drawn BEHIND characters and it sways.

    The counterpart to the fern: a fern is in front of you and dark, a bush is
    behind you and lighter. Between them a body walking across open ground
    passes through three depths instead of sliding over one plane.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    base_y = height - 1.0
    cx = (width - 1) / 2.0
    # A cluster of overlapping lobes, so the outline is lumpy rather than
    # domed. One big lobe carries the mass and the rest break its edge — an
    # even spread of equal lobes came out as a flat green mat, which reads as
    # ground cover rather than as something with a front and a back.
    lobes = [(cx + rng.uniform(-1.5, 1.5), base_y - height * 0.46, height * 0.52)]
    for _ in range(rng.randint(3, 5)):
        lobes.append(
            (
                cx + rng.uniform(-width * 0.26, width * 0.26),
                base_y - rng.uniform(height * 0.28, height * 0.72),
                rng.uniform(height * 0.26, height * 0.40),
            )
        )

    for y in range(height):
        for x in range(width):
            best = 0.0
            for bx, by, radius in lobes:
                dx = (x - bx) / radius
                dy = (y - by) / (radius * 0.92)
                dist = dx * dx + dy * dy
                if dist < 1.0:
                    best = max(best, 1.0 - math.sqrt(dist))
            if best <= 0.0:
                continue
            lit = clamp01(0.22 + best * 0.6 - (y / height) * 0.35)
            lit += (hash01(x, y, 421) - 0.5) * 0.45
            px[x, y] = pick(SHRUB, lit, x, y)

    # A handful of loose sprigs breaking the outline, so it is not a blob.
    for _ in range(rng.randint(3, 6)):
        sx = cx + rng.uniform(-width * 0.4, width * 0.4)
        sy = base_y - rng.uniform(height * 0.4, height * 0.85)
        angle = rng.uniform(-0.9, 0.9)
        for step in range(rng.randint(2, 4)):
            ix = int(round(sx + math.sin(angle) * step))
            iy = int(round(sy - math.cos(angle) * step))
            if 0 <= ix < width and 0 <= iy < height:
                px[ix, iy] = pick(SHRUB, 0.75, ix, iy)
    return img


def make_branch(width: int, height: int, rng: random.Random) -> Image.Image:
    """A fallen twig lying flat. A DECAL: no outline, no silhouette.

    Baked into the ground canvas, so it must read as something ON the floor
    rather than something standing in it. That is why it gets no outline — the
    dark keyline is what tells the eye a thing has a side facing the camera.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    y = height * rng.uniform(0.45, 0.65)
    x = rng.uniform(1.0, 3.0)
    angle = rng.uniform(-0.35, 0.35)
    length = rng.uniform(width * 0.6, width * 0.92)

    trail: list[tuple[int, int, float]] = []
    for step in range(int(length)):
        t = step / max(length - 1, 1)
        x += math.cos(angle)
        y += math.sin(angle + math.sin(t * 3.0) * 0.25) * 0.5
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < width and 0 <= iy < height):
            break
        trail.append((ix, iy, t))
        px[ix, iy] = pick(TWIG, 0.35 + t * 0.4, ix, iy)
        if t < 0.7 and iy + 1 < height:
            px[ix, iy + 1] = pick(TWIG, 0.2 + t * 0.3, ix, iy + 1)

    # One or two side shoots — a bare stick reads as a scratch, a forked one
    # reads as wood.
    for _ in range(rng.randint(1, 2)):
        if not trail:
            break
        sx, sy, _ = trail[rng.randrange(len(trail))]
        side = rng.choice((-1, 1))
        for step in range(rng.randint(2, 3)):
            ix = sx + step
            iy = sy + side * step
            if 0 <= ix < width and 0 <= iy < height:
                px[ix, iy] = pick(TWIG, 0.5, ix, iy)
    return img


def make_leaves(width: int, height: int, rng: random.Random) -> Image.Image:
    """A scatter of fallen leaves. A DECAL, baked into the ground.

    Individually drawn rather than noise-thresholded, because a leaf has a
    shape and a pile of noise does not: at this size three lit pixels in a row
    with a dark one under them is the whole difference between litter and dirt.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    for _ in range(rng.randint(9, 14)):
        lx = rng.uniform(1.0, width - 2.0)
        ly = rng.uniform(1.0, height - 2.0)
        span = rng.uniform(1.6, 2.6)
        angle = rng.uniform(0, math.pi)
        shade = rng.uniform(0.3, 1.0)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        # A filled lens, not a stroke. A single-pixel line is a twig; two
        # pixels across the short axis is the smallest thing that still reads
        # as a leaf lying face up.
        for oy in range(-3, 4):
            for ox in range(-3, 4):
                # Rotate into the leaf's own frame, then test an ellipse that
                # is long one way and 2px the other.
                u = ox * cos_a + oy * sin_a
                v = -ox * sin_a + oy * cos_a
                if (u / span) ** 2 + (v / 0.95) ** 2 > 1.0:
                    continue
                ix, iy = int(round(lx + ox)), int(round(ly + oy))
                if not (0 <= ix < width and 0 <= iy < height):
                    continue
                # Lit along the spine, darker at the rim, so each leaf has a
                # curl instead of being a flat chip of colour.
                px[ix, iy] = pick(FALLEN_LEAF, shade - abs(v) * 0.35, ix, iy)
    return img


# --- sheets -----------------------------------------------------------------


def pack(frames: list[Image.Image], width: int, height: int) -> Image.Image:
    sheet = Image.new("RGBA", (width * len(frames), height), TRANSPARENT)
    for index, frame in enumerate(frames):
        sheet.paste(frame, (index * width, 0))
    return sheet


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "terrain"
    out_dir.mkdir(parents=True, exist_ok=True)

    ground_size = tile * GROUND_TILES
    for index, soil in enumerate(SOILS):
        # A per-soil seed offset, not one shared lattice: four soils drawn from
        # the same noise are four recolours of one texture, and tiling them
        # against each other shows the identical blotches lining up.
        make_ground(ground_size, args.seed + index * 1607, soil).save(
            out_dir / f"ground_{soil.name}.png"
        )

    blends = [make_blend(tile, step, BLEND_STEPS, args.seed + 505) for step in range(BLEND_STEPS)]
    pack(blends, tile, tile).save(out_dir / "blend.png")

    patch_size = tile * 2
    patches = [
        make_patch(patch_size, ramp, density, rim, args.seed + 606 + index * 37)
        for index, (_, ramp, density, rim) in enumerate(PATCHES)
    ]
    pack(patches, patch_size, patch_size).save(out_dir / "patch.png")

    # Wider and taller than a tile: a rock overhangs its own footprint the way
    # a tree does, and the bottom sixteenth is the cast shadow's band.
    rock_w, rock_h = round(tile * 1.25), round(tile * 1.625)
    rng = random.Random(args.seed + 101)
    # Eight recipes, not eight rolls of one recipe — silhouette is the thing
    # that has to vary, and noise does not vary a silhouette.
    rocks = [make_rock(rock_w, rock_h, kind, rng) for kind in ROCK_RECIPES]
    pack(rocks, rock_w, rock_h).save(out_dir / "rock.png")

    tree_w, tree_h = round(tile * 1.5), round(tile * 2.5)
    rng = random.Random(args.seed + 202)
    trees = [make_tree(tree_w, tree_h, tile, rng) for _ in range(4)]
    pack(trees, tree_w, tree_h).save(out_dir / "tree.png")

    # Same frame as a living tree, so a blighted tile swaps sheets and nothing
    # else — see the client's `blight` field.
    rng = random.Random(args.seed + 212)
    dead_trees = [make_dead_tree(tree_w, tree_h, rng) for _ in range(4)]
    pack(dead_trees, tree_w, tree_h).save(out_dir / "deadtree.png")

    stump_w, stump_h = tile, round(tile * 0.875)
    rng = random.Random(args.seed + 222)
    stumps = [make_stump(stump_w, stump_h, rng) for _ in range(4)]
    pack(stumps, stump_w, stump_h).save(out_dir / "stump.png")

    grass_w = grass_h = round(tile * 0.625)
    rng = random.Random(args.seed + 303)
    grasses = [make_grass(grass_w, grass_h, rng) for _ in range(6)]
    pack(grasses, grass_w, grass_h).save(out_dir / "grass.png")

    bush_w, bush_h = round(tile * 1.25), tile
    rng = random.Random(args.seed + 313)
    bushes = [make_bush(bush_w, bush_h, rng) for _ in range(5)]
    pack(bushes, bush_w, bush_h).save(out_dir / "bush.png")

    branch_w, branch_h = tile, round(tile * 0.4375)
    rng = random.Random(args.seed + 323)
    branches = [make_branch(branch_w, branch_h, rng) for _ in range(5)]
    pack(branches, branch_w, branch_h).save(out_dir / "branch.png")

    leaf_w, leaf_h = tile, round(tile * 0.75)
    rng = random.Random(args.seed + 333)
    leaf_piles = [make_leaves(leaf_w, leaf_h, rng) for _ in range(6)]
    pack(leaf_piles, leaf_w, leaf_h).save(out_dir / "leaves.png")

    fern_w, fern_h = round(tile * 1.25), round(tile * 1.125)
    rng = random.Random(args.seed + 404)
    ferns = [make_fern(fern_w, fern_h, rng) for _ in range(5)]
    pack(ferns, fern_w, fern_h).save(out_dir / "fern.png")

    fire_w, fire_h = round(tile * 1.5), round(tile * 1.75)
    fires = [make_campfire(fire_w, fire_h, i, CAMPFIRE_FRAMES) for i in range(CAMPFIRE_FRAMES)]
    pack(fires, fire_w, fire_h).save(out_dir / "campfire.png")

    manifest = {
        "tile": tile,
        "seed": args.seed,
        # Order IS the client's material index. Append, never reorder.
        "grounds": [
            {
                "name": soil.name,
                "file": f"ground_{soil.name}.png",
                "tile": tile,
                "cols": GROUND_TILES,
                "rows": GROUND_TILES,
            }
            for soil in SOILS
        ],
        # Alpha stencils, coverage ascending. The client picks by how far a
        # tile has crossed a material boundary.
        "blend": {
            "file": "blend.png",
            "frameWidth": tile,
            "frameHeight": tile,
            "frames": len(blends),
        },
        # Flat stains scattered over the floor. Baked, never depth-sorted.
        "decals": {
            "patch": {
                "file": "patch.png",
                "frameWidth": patch_size,
                "frameHeight": patch_size,
                "frames": len(patches),
            },
            "branch": {
                "file": "branch.png",
                "frameWidth": branch_w,
                "frameHeight": branch_h,
                "frames": len(branches),
            },
            "leaves": {
                "file": "leaves.png",
                "frameWidth": leaf_w,
                "frameHeight": leaf_h,
                "frames": len(leaf_piles),
            },
        },
        "props": {
            "rock": {
                "file": "rock.png",
                "frameWidth": rock_w,
                "frameHeight": rock_h,
                "frames": len(rocks),
                "solid": True,
            },
            "tree": {
                "file": "tree.png",
                "frameWidth": tree_w,
                "frameHeight": tree_h,
                "frames": len(trees),
                "solid": True,
                # Pixels above the prop's own tile. Drawn after entities so a
                # player north of a tree walks under the foliage.
                "canopyHeight": tree_h - tile,
            },
            "deadtree": {
                "file": "deadtree.png",
                "frameWidth": tree_w,
                "frameHeight": tree_h,
                "frames": len(dead_trees),
                "solid": True,
                # Bare limbs still hang over the tile above, and a body has to
                # pass behind them for the stand to have any depth.
                "canopyHeight": tree_h - tile,
            },
            "stump": {
                "file": "stump.png",
                "frameWidth": stump_w,
                "frameHeight": stump_h,
                "frames": len(stumps),
                "solid": True,
            },
            "grass": {
                "file": "grass.png",
                "frameWidth": grass_w,
                "frameHeight": grass_h,
                "frames": len(grasses),
                "solid": False,
            },
            "bush": {
                "file": "bush.png",
                "frameWidth": bush_w,
                "frameHeight": bush_h,
                "frames": len(bushes),
                "solid": False,
                # Drawn live with the grass so it can sway, but taller — a body
                # passes IN FRONT of it, which is the depth a fern gives from
                # the other side.
                "sways": True,
            },
            "fern": {
                "file": "fern.png",
                "frameWidth": fern_w,
                "frameHeight": fern_h,
                "frames": len(ferns),
                "solid": False,
                # Drawn after characters, so the player passes behind it.
                "foreground": True,
            },
            "campfire": {
                "file": "campfire.png",
                "frameWidth": fire_w,
                "frameHeight": fire_h,
                "frames": len(fires),
                "solid": True,
                # The only prop whose frames are an ANIMATION rather than
                # variants. The client plays them on a loop at this rate.
                "animated": True,
                "fps": CAMPFIRE_FPS,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: {len(SOILS)} grounds {ground_size}x{ground_size} "
        f"({GROUND_TILES}x{GROUND_TILES} tiles) [{', '.join(s.name for s in SOILS)}], "
        f"blend {len(blends)}x{tile}x{tile}, "
        f"patch {len(patches)}x{patch_size}x{patch_size}, "
        f"rock {len(rocks)}x{rock_w}x{rock_h}, "
        f"tree {len(trees)}x{tree_w}x{tree_h}, "
        f"deadtree {len(dead_trees)}x{tree_w}x{tree_h}, "
        f"stump {len(stumps)}x{stump_w}x{stump_h}, "
        f"grass {len(grasses)}x{grass_w}x{grass_h}, "
        f"bush {len(bushes)}x{bush_w}x{bush_h}, "
        f"branch {len(branches)}x{branch_w}x{branch_h}, "
        f"leaves {len(leaf_piles)}x{leaf_w}x{leaf_h}, "
        f"fern {len(ferns)}x{fern_w}x{fern_h}, "
        f"campfire {len(fires)}x{fire_w}x{fire_h}"
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
