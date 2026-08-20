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
    tree.png      6 frames, 24x40   solid blocker, 6 species, overhangs its tile
    deadtree.png  6 frames, 24x40   solid blocker, bare — a blighted TREE tile
    stump.png     4 frames, 16x14   solid blocker, a felled trunk, 4 states
    grass.png     6 frames, 10x10   decoration, non-solid, sways, LOD floor
    bush.png      5 frames, 20x16   decoration, non-solid, sways, OVER bodies
    branch.png    5 frames, 16x7    flat decal, baked into the ground
    leaves.png    6 frames, 16x12   flat decal, baked into the ground
    fern.png      5 frames, 20x18   FOREGROUND decoration, over characters, NO shadow
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
import colorsys
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


# --- material ramps, DERIVED --------------------------------------------------
# PIXEL-ART-DIRECTION-V2.md S11 is a table, not a taste: a material's five steps
# are its hue, its saturation and where its two ends sit, and everything between
# is a law — value climbs on a fixed curve, saturation peaks in the mid-to-shadow
# range and DROPS at the highlight, hue swings cool into the shadows and warm
# into the lights. A ramp written as five hex triples is five chances to get one
# of those wrong, and the failure is invisible per-colour and obvious per-set:
# one material in a sheet that does not shift hue reads as plastic beside eleven
# that do.
#
# `make_guns.py` derived its ramps this way first and the loot sheet copied the
# idea; the function lives HERE for the reason every other shared helper does —
# two generators drawing the same world out of two copies of one law is two
# laws, and they drift.

#: S11's five lightness steps, normalised off its L column (21/36/54/70/84) so a
#: material only has to say where its own ends are. Non-linear on purpose: the
#: gap from base to key light is wider than the gap from core shadow to base.
STEP_L: tuple[float, ...] = (0.0, 0.238, 0.524, 0.778, 1.0)
#: S12: saturation peaks in the mid-to-shadow range and DROPS at the highlight,
#: which is what keeps a specular from reading as a white sticker.
STEP_S: tuple[float, ...] = (1.10, 1.06, 1.00, 0.95, 0.72)
#: S11: shadows cool, lights warm, never the reverse.
STEP_H: tuple[int, ...] = (-18, -10, 0, 8, 14)


def _lerp(table: tuple[float, ...], t: float) -> float:
    """S11's tables read at any position along the ramp, not just at its steps."""
    span = (len(table) - 1) * max(0.0, min(1.0, t))
    low = min(int(span), len(table) - 2)
    return table[low] + (table[low + 1] - table[low]) * (span - low)


def material_ramp(hue: float, sat: float, lo: float, hi: float,
                  steps: int = 5) -> Ramp:
    """A material ramp from S11's law. Five steps unless asked for more.

    `hue` in degrees, `sat` at the base step, `lo`/`hi` the lightness of the two
    ends as fractions. Everything between is the tables above — the point being
    that a new material is four numbers and not fifteen hex triples that may or
    may not shift hue the way the rest of the world does.

    The `lo` end is the number that matters. A ramp bottoming out a hair off the
    outline means every plane the shading puts on step 0 or 1 sinks into the
    keyline, and S7 is explicit that step 2 is the ambient reference and is "not
    black".

    `steps` exists for the SIX-step ramps the dimetric props are banded on:
    `make_objects` puts its top plane on step 5, its near face on 3 and its far
    face on 1, so a five-step ramp collapses the top plane into the specular and
    a crate loses the difference between "lit" and "the brightest thing on the
    object". The law is the same either way — the tables are read at fractional
    positions rather than at their own indices — which is the whole reason it is
    one function and not two.
    """
    ramp: Ramp = []
    for index in range(steps):
        t = index / max(steps - 1, 1)
        light = lo + (hi - lo) * _lerp(STEP_L, t)
        red, green, blue = colorsys.hls_to_rgb(
            ((hue + _lerp(STEP_H, t)) % 360) / 360.0,
            light,
            min(1.0, sat * _lerp(STEP_S, t)),
        )
        ramp.append((round(red * 255), round(green * 255), round(blue * 255), 255))
    return ramp


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

BARK: Ramp = [rgb(c) for c in ("#17120f", "#241a12", "#33261a", "#453421", "#5a442a")]
# Foliage. The span from step 1 to step 4 is the whole budget the canopy has
# to say which mass is in front of which (§13), and it used to be 17 L —
# five clumps in that range are one silhouette with texture in it. Widened
# to the same reach the rock ramps get, hue shifting cool at the bottom and
# toward yellow at the top (§11), still under the night key.
LEAF: Ramp = [rgb(c) for c in ("#111a10", "#1b2916", "#2a3d1f", "#3d5628", "#597033")]
TREE_OUTLINE = rgb("#10160f")

# Dead wood is GREY, not brown. A dead tree drawn in the same bark ramp as a
# living one only reads as a tree that lost its leaves; drained of hue it reads
# as bone, and a stand of them reads as something that happened here.
DEADWOOD: Ramp = [rgb(c) for c in ("#1a1917", "#2a2724", "#3e3a35", "#565049", "#726a60")]
DEAD_OUTLINE = rgb("#0f0e0d")
# The heartwood of a fresh stump: still warm, so a cut trunk reads as recent.
HEARTWOOD: Ramp = [rgb(c) for c in ("#2a1e14", "#3b2c1c", "#4e3b26", "#644c31", "#7d613e")]

# Bushes sit BEHIND the player and in front of the floor, so they are lighter
# than a fern (which is in front and must not fight the character) and darker
# than grass (which is underfoot and catches the lantern first).
SHRUB: Ramp = [rgb(c) for c in ("#101a0f", "#1b2a17", "#2b3f21", "#3d5629", "#526d33")]
# Fallen wood on the floor: read at a glance as "not soil", nothing more.
TWIG: Ramp = [rgb(c) for c in ("#1b150f", "#261d14", "#33281b", "#413324")]
FALLEN_LEAF: Ramp = [rgb(c) for c in ("#2b1f11", "#3a2a16", "#4a361c", "#5a4222", "#6b5029")]

# Campfire. The flame ramp is the one place in this file that goes bright: it is
# the only self-lit object in the game, and the client's darkness pass multiplies
# over everything else. A flame in the same value range as the forest floor would
# have nothing left to read as fire.
FLAME: Ramp = [rgb(c) for c in ("#5c1606", "#a82c0c", "#d9531a", "#f5892a", "#ffc44e", "#fff2bd")]
COAL: Ramp = [rgb(c) for c in ("#140f0c", "#2a1710", "#4d2410", "#8a3a12", "#d4600f")]
TIMBER: Ramp = [rgb(c) for c in ("#1d1510", "#2c2016", "#402d1d", "#573d26", "#755233")]
TIMBER_OUTLINE = rgb("#0d0907")

BLADE: Ramp = [rgb(c) for c in ("#1a2615", "#2a3a20", "#3c5229", "#557036")]
# Ferns are FOREGROUND: they draw over the player, so they are deliberately
# darker and cooler than the grass underfoot. A bright silhouette in front of
# the character would read as an obstruction; a dark one reads as depth.
FROND: Ramp = [rgb(c) for c in ("#080d08", "#111a10", "#1e2d1a", "#2e4526")]

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
# PIXEL-ART-DIRECTION-V2.md: stacked convex masses (§2), top plane 35-45% of the
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


def _footprint(body: Image.Image, foot: list[int]) -> tuple[int, int]:
    """The horizontal extent a cast shadow is sized from.

    `foot` is what touched the contact line. When nothing did — a mass drawn
    a pixel shy of it — falling back to the whole frame draws a shadow slab
    wider than the sprite, so the fallback is the object's own opaque extent.
    """
    if foot:
        return min(foot), max(foot)
    px = body.load()
    columns = [
        x for x in range(body.width)
        if any(px[x, y][3] != 0 for y in range(body.height))
    ]
    return (min(columns), max(columns)) if columns else (0, body.width - 1)


def _cast_shadow(
    size: tuple[int, int], left: int, right: int, bottom: float, tone: RGBA,
    drop: float = 0.04,
) -> Image.Image:
    """A flat two-band ellipse under a footprint, offset down-right (§9).

    Takes the footprint as numbers rather than reading it off the sprite,
    because the two callers disagree about what their footprint is: a rock's
    is its own silhouette, and a tree's is its ROOTS — a shadow as wide as a
    canopy puts the tree on a plate.
    """
    layer = Image.new("RGBA", size, TRANSPARENT)
    span = right - left + 1
    cx = (left + right) / 2 + span * 0.12          # offset right  (§9)
    cy = bottom + max(1.0, size[1] * drop)         # offset down   (§9)
    rx = span * 0.55
    ry = max(1.5, rx * 0.32)
    draw = ImageDraw.Draw(layer)
    outer = (tone[0], tone[1], tone[2], 46)
    core = (tone[0], tone[1], tone[2], 92)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=outer)
    draw.ellipse((cx - rx * 0.66, cy - ry * 0.62, cx + rx * 0.66, cy + ry * 0.62),
                 fill=core)
    return layer


def _rock_shadow(
    size: tuple[int, int], body: Image.Image, tone: RGBA,
) -> Image.Image:
    """The rock's cast shadow. Its footprint IS its silhouette — nothing on a
    rock overhangs far enough for the two to disagree."""
    px = body.load()
    columns = [
        (x, max(y for y in range(size[1]) if px[x, y][3] != 0))
        for x in range(size[0])
        if any(px[x, y][3] != 0 for y in range(size[1]))
    ]
    if not columns:
        return Image.new("RGBA", size, TRANSPARENT)
    return _cast_shadow(
        size,
        min(x for x, _ in columns),
        max(x for x, _ in columns),
        max(y for _, y in columns),
        tone,
    )


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


# --- trees ------------------------------------------------------------------
# A tree used to be a trunk with a cluster of circles on it, and at 24x40 that
# reads as a lollipop: one surface, one shading rule, no information about
# which part of it is in front of which. It is now built the way the rocks are
# (see the rock section above) — as MASSES with plane breaks between them —
# because the same argument applies. A canopy is not a ball of leaves, it is
# three or four clumps hanging off limbs at different depths, and what tells
# the eye that is the 1px dark seam where the near one cuts the far one, not
# the shading inside either.
#
# Five things carry the volume, and each of them is cheap:
#   trunk    three vertical value bands (lit left face, front, shade face) plus
#            long bark strips along the grain axis (§14). A trunk shaded by
#            distance from its own centre is a cylinder in a gradient; shaded
#            by face it is a solid with sides.
#   roots    spurs fanning to the contact line. They break the silhouette away
#            from the cast ellipse (§19) — without them the sprite and its
#            shadow are two concentric shapes and the tree floats.
#   limbs    drawn BEFORE the foliage, then painted back in afterwards wherever
#            the leaves above them landed on ramp step 0 or 1. That is what
#            "seen through the canopy" is: a limb only shows where the foliage
#            is in shadow, and where it is lit the leaves win.
#   clumps   lobed domes, hard cel bands off one key (§7, §8), with a step-0
#            rim under the lower arc. Painted back to front; each one darkens
#            whatever it lands against by a step first (§10), so the stack has
#            depth instead of being one silhouette with texture in it.
#   shadow   the flat offset ellipse every prop in this game stands on, sized
#            from the ROOT SPREAD and not from the canopy — a shadow as wide as
#            the crown puts the tree on a plate.
#
# Six species, six recipes, for the reason the rocks have eight: silhouette is
# what has to differ between two trees, and rerolling one recipe six times
# varies the noise inside a shape it never varies. Their top contours (§15) are
# broad dome / tiered spire / open and sparse / weeping / twin-lobed / leaning
# wedge, and each is identifiable in solid black.
#
# One green for all six. The reference sheet gets its variety from hue — a pink
# blossom next to an autumn orange — and that is a daylight sheet on a neutral
# field. This is one forest at night under a lantern that multiplies over
# everything, and six foliage hues would collapse into the same dark smear two
# tiles from the light while breaking the palette economy that makes the rest
# of the set look authored (§11).

# The key, as a unit vector: 135deg azimuth, ~60deg elevation (§8). Written out
# rather than derived so the foliage cannot drift away from the rocks' light.
TREE_KEY = (-0.50, -0.50, 0.71)

# Reserved at the bottom of the frame for the cast shadow. Smaller than the
# rock's band because a tree is anchored by its roots, which are already wide:
# the ellipse only has to escape the trunk, not the whole footprint.
TREE_SHADOW_BAND = 0.08

# stems:   (cx, half, top, lean, flare) — x fractions of width, y fractions of
#          frame height from the TOP, lean in px of drift per row climbed.
# roots:   spur count. Even: an odd count puts one root straight down the
#          middle of the trunk where it draws nothing.
# limbs:   (count, start, fan, droop, reach). `droop` is signed — negative
#          lifts the limb as it runs out, positive weeps it over.
# lobes,
# bite:    the angular ripple that keeps a clump's edge notched (§15). More
#          lobes and a deeper bite is a conifer; fewer and shallower is a
#          broadleaf.
# hang:    how far a clump's lower half is stretched past its upper. 1.0 is a
#          dome, 2.0 hangs.
# clumps:  (cx, cy, rx, ry) fractions, listed BACK TO FRONT. The order is the
#          depth order and it is the whole reason the canopy has any.
TREE_RECIPES: dict[str, dict] = {
    # Broad dome, heavy bole. The set's horizontal anchor and the one whose
    # crown actually fills the frame.
    "oak": {
        "stems": [(0.48, 0.105, 0.50, 0.02, 0.045)],
        "roots": 4,
        "limbs": (4, 0.58, 2.2, -0.35, 0.30),
        "lobes": 5, "bite": 0.42, "hang": 1.15, "strands": 0,
        "clumps": [
            (0.30, 0.33, 0.24, 0.115),
            (0.70, 0.30, 0.22, 0.11),
            (0.50, 0.20, 0.29, 0.14),
            (0.38, 0.45, 0.25, 0.115),
            (0.66, 0.43, 0.20, 0.10),
        ],
    },
    # Tiered spire. Four skirts on the 1 : 0.7 : 0.5 rhythm (§17), each hung
    # past its own centre so the tier reads as a cone and not as a disc, and
    # the deepest bite in the set so the outline stays needled.
    "pine": {
        "stems": [(0.50, 0.075, 0.30, 0.0, 0.03)],
        "roots": 4,
        "limbs": (3, 0.40, 1.6, -0.15, 0.16),
        "lobes": 7, "bite": 0.55, "hang": 1.7, "strands": 0,
        "clumps": [
            (0.50, 0.10, 0.14, 0.055),
            (0.46, 0.22, 0.20, 0.065),
            (0.54, 0.34, 0.26, 0.075),
            (0.48, 0.47, 0.32, 0.085),
        ],
    },
    # Slender and leaning, with the crown deliberately left OPEN: four small
    # clumps with floor between them, so this is the one where the limb
    # armature is most of what you read.
    "birch": {
        "stems": [(0.42, 0.062, 0.42, 0.075, 0.025)],
        "roots": 4,
        "limbs": (5, 0.50, 2.4, -0.45, 0.34),
        "lobes": 4, "bite": 0.46, "hang": 1.0, "strands": 0,
        "clumps": [
            (0.26, 0.27, 0.16, 0.085),
            (0.56, 0.16, 0.19, 0.095),
            (0.76, 0.31, 0.15, 0.08),
            (0.48, 0.38, 0.17, 0.085),
        ],
    },
    # Weeping. The only recipe with a positive droop and the only one that
    # grows strands: 1px tails off the underside of the canopy. They are what
    # makes the shape read as hanging rather than as a wide oak.
    "willow": {
        "stems": [(0.50, 0.10, 0.46, -0.03, 0.045)],
        "roots": 4,
        "limbs": (5, 0.54, 2.6, 0.55, 0.32),
        "lobes": 6, "bite": 0.44, "hang": 2.0, "strands": 1,
        "clumps": [
            (0.24, 0.30, 0.20, 0.075),
            (0.50, 0.20, 0.27, 0.10),
            (0.76, 0.32, 0.19, 0.075),
            (0.36, 0.40, 0.21, 0.08),
            (0.64, 0.41, 0.18, 0.075),
        ],
    },
    # Two stems from one root plate. The right lobe is nearly twice the left on
    # purpose: two equal heads is the shape §15 bans, and a split trunk under
    # one dominant crown still reads as ONE tree.
    "twin": {
        "stems": [
            (0.34, 0.075, 0.48, -0.055, 0.03),
            (0.62, 0.085, 0.42, 0.05, 0.035),
        ],
        "roots": 4,
        "limbs": (3, 0.56, 2.0, -0.25, 0.24),
        "lobes": 5, "bite": 0.42, "hang": 1.2, "strands": 0,
        "clumps": [
            (0.26, 0.36, 0.17, 0.085),
            (0.68, 0.22, 0.26, 0.13),
            (0.30, 0.48, 0.15, 0.075),
            (0.72, 0.44, 0.21, 0.10),
        ],
    },
    # Wind-leaned: the bole drifts one way and the crown is shoved the other,
    # carrying the largest lean in the set. It is what stops six trees from
    # averaging out upright the way eight rocks would have.
    "spread": {
        "stems": [(0.60, 0.095, 0.50, -0.095, 0.04)],
        "roots": 4,
        "limbs": (4, 0.58, 2.3, -0.20, 0.34),
        "lobes": 5, "bite": 0.44, "hang": 1.3, "strands": 0,
        "clumps": [
            (0.36, 0.22, 0.27, 0.135),
            (0.64, 0.30, 0.19, 0.095),
            (0.32, 0.42, 0.23, 0.105),
            (0.56, 0.46, 0.16, 0.08),
        ],
    },
}


def _tree_stem(
    px, size: tuple[int, int], stem: tuple, base: float, roots: int,
    rng: random.Random, ramp: Ramp = BARK,
) -> None:
    """One bole and its root spurs, shaded by FACE rather than by radius.

    Three bands across the width — lit left, front, shade right — is the same
    plane break `_rock_faces` gives a prism, done in the one direction a trunk
    actually has. The grain strips are keyed off the frame column, not off the
    leaning centre line, so a leaning trunk slides across its own bark instead
    of dragging a fixed pattern with it.
    """
    width, height = size
    fcx, fhalf, ftop, lean, fflare = stem
    cx = fcx * (width - 1)
    half0 = max(1.2, fhalf * width)
    top = ftop * height
    flare = fflare * width
    run = max(1.0, base - top)

    for y in range(int(round(base)), int(top) - 1, -1):
        up = (base - y) / run
        centre = cx + (base - y) * lean
        # Taper up the bole, and a flare in the bottom sixth so it plants.
        half = half0 * (1.0 - 0.28 * up) + flare * max(0.0, 1.0 - up * 6.0) ** 2
        for x in range(width):
            t = (x - centre) / max(half, 0.6)
            if abs(t) > 1.0:
                continue
            step = 3 if t < -0.55 else 2 if t < 0.15 else 1 if t < 0.62 else 0
            grain = hash01(x, 0, 7717)
            if grain > 0.74:
                step = min(step + 1, 3)
            elif grain < 0.20:
                step = max(step - 1, 0)
            px[x, y] = ramp[step]

    _root_spurs(px, size, cx, half0, base, roots, rng, ramp)


def _root_spurs(
    px, size: tuple[int, int], cx: float, half0: float, base: float,
    roots: int, rng: random.Random, ramp: Ramp, rise_max: float | None = None,
) -> None:
    """Claws fanning to the contact line, 1px apart at the tips.

    They exist to break the silhouette away from the cast ellipse (§19): a
    trunk that meets the ground on a flat edge and a soft blob under it are
    two concentric shapes, and the object floats between them. Spur COUNT must
    stay even — an odd one puts a root straight down the middle of the bole
    where it draws nothing.
    """
    width, height = size
    for index in range(roots):
        frac = (index + 0.5) / roots - 0.5
        side = 1.0 if frac > 0 else -1.0
        reach = side * half0 * (0.9 + 2.4 * abs(frac)) * rng.uniform(0.85, 1.15)
        rise = (
            half0 * rng.uniform(1.4, 2.6) if rise_max is None
            else rise_max * rng.uniform(0.55, 1.0)
        )
        steps = max(2, int(abs(reach)) + 2)
        step_i = 3 if reach < 0 else 1
        for s in range(steps + 1):
            t = s / steps
            fx = cx + reach * t
            fy = base - rise * (1.0 - t) ** 1.3
            ix, iy = int(round(fx)), int(round(fy))
            if not (0 <= ix < width and 0 <= iy < height):
                continue
            px[ix, iy] = ramp[step_i]
            if t < 0.25 and iy - 1 >= 0:
                px[ix, iy - 1] = ramp[step_i]


def _tree_limbs(
    px, size: tuple[int, int], stem: tuple, spec: tuple, base: float,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """The armature, drawn before the leaves. Returns every pixel it touched.

    The trail is the point: the foliage is painted straight over this, and the
    caller then puts the limb back wherever the leaves above it landed dark.
    Drawing branches on TOP of a canopy instead gives twigs lying on the
    leaves; drawing them only underneath gives a canopy with nothing in it.
    """
    width, height = size
    count, fstart, fan, droop, reach = spec
    fcx, _, _, lean, _ = stem
    start_y = fstart * height
    origin = fcx * (width - 1) + (base - start_y) * lean
    trail: list[tuple[int, int]] = []

    for index in range(count):
        frac = (index + 0.5) / count - 0.5
        angle = -math.pi / 2 + frac * fan
        length = max(3.0, reach * width * rng.uniform(0.7, 1.25))
        x, y = origin, start_y
        steps = max(2, int(length))
        for s in range(steps):
            t = s / (steps - 1)
            bend = angle + droop * t * t
            x += math.cos(bend)
            y += math.sin(bend)
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= ix < width and 0 <= iy < height):
                break
            px[ix, iy] = BARK[2 if t < 0.6 else 1]
            trail.append((ix, iy))
            # Thick at the shoulder, 1px at the tip (§17).
            if t < 0.4 and iy + 1 < height:
                px[ix, iy + 1] = BARK[1]
                trail.append((ix, iy + 1))
    return trail


def _contact(
    px, size: tuple[int, int], base: float, ramp: Ramp, band: int = 2,
) -> list[int]:
    """Darken where the object meets the floor, and report the footprint (§19).

    Only columns whose LOWEST pixel is at the contact line get the band. An
    overhanging mass — a canopy, a shrub's shoulder — does not touch the
    ground, and darkening its underside here draws a second contact line
    halfway up the sprite, which reads as the object being cut in two.
    """
    width, height = size
    foot: list[int] = []
    for x in range(width):
        column = [y for y in range(height) if px[x, y][3] != 0]
        if not column:
            continue
        floor = max(column)
        if floor < base - 1.5:
            continue
        foot.append(x)
        px[x, floor] = ramp[0]
        if band > 1 and floor - 1 in column:
            px[x, floor - 1] = ramp[1]
    return foot


def _tree_clump(
    size: tuple[int, int], clump: tuple, hang: float, lobes: int, bite: float,
    seed: int,
) -> list[tuple[int, int, int]]:
    """One foliage mass as (x, y, ramp step). No pixels written yet.

    The boundary is a lobed radius rather than a circle — an ellipse at this
    size is unmistakably a stamp, and five of them is a stamp repeated. The
    shading is a dome normal against the one key, quantised hard: no dither,
    because `pick` would soften exactly the plane break the mass is made of.
    The step-0 band under the lower arc is not shading, it is the SEAM the
    next clump forward will sit against.
    """
    width, height = size
    fcx, fcy, frx, fry = clump
    cx = fcx * (width - 1)
    cy = fcy * height
    rx = max(2.0, frx * width)
    ry = max(2.0, fry * height)
    phase = hash01(seed, 3, 11) * math.tau
    kx, ky, kz = TREE_KEY

    cells: list[tuple[int, int, int]] = []
    for y in range(height):
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - cy) / (ry * (hang if y > cy else 1.0))
            dist = math.hypot(dx, dy)
            if dist > 1e-6:
                angle = math.atan2(dy, dx)
                ripple = (
                    0.65 * (0.5 + 0.5 * math.sin(lobes * angle + phase))
                    + 0.35 * (0.5 + 0.5 * math.sin(2 * lobes * angle + phase * 2.3))
                )
                edge = 1.0 - bite * ripple * ripple
            else:
                edge = 1.0
            if dist > edge:
                continue
            near = min(1.0, dist)
            up = math.sqrt(max(0.0, 1.0 - near * near))
            lam = dx * kx + dy * ky + up * kz
            step = (
                4 if lam > 0.93 else
                3 if lam > 0.62 else
                2 if lam > 0.05 else
                1 if lam > -0.35 else 0
            )
            # Leaf texture is CLUSTERED, never per-pixel noise (§5): the hash
            # is read at half resolution so the smallest bump is 2x2.
            bump = hash01(x >> 1, y >> 1, seed)
            if bump > 0.87:
                step = min(step + 1, 4)
            elif bump < 0.13:
                step = max(step - 1, 0)
            if near > 0.72 and dy > 0.28:
                step = 0
            cells.append((x, y, step))
    return cells


def make_tree(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the six trees, by name. Masses, plane breaks, cast shadow."""
    recipe = TREE_RECIPES[kind]
    size = (width, height)
    body = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()
    base = height - 1 - height * TREE_SHADOW_BAND

    for stem in recipe["stems"]:
        _tree_stem(px, size, stem, base, recipe["roots"], rng)
    trail: list[tuple[int, int]] = []
    for stem in recipe["stems"]:
        trail += _tree_limbs(px, size, stem, recipe["limbs"], base, rng)

    for clump in recipe["clumps"]:
        cells = _tree_clump(
            size, clump, recipe["hang"], recipe["lobes"], recipe["bite"],
            rng.randrange(1 << 20),
        )
        mask = {(x, y) for x, y, _ in cells}
        # Everything this mass lands against loses a step, so the stack reads
        # as one clump IN FRONT of another rather than as a textured blob
        # (§10, §18). Same trick the rocks use between chunks.
        for x, y in list(mask):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if (nx, ny) in mask or px[nx, ny][3] == 0:
                    continue
                px[nx, ny] = LEAF[0]
        for x, y, step in cells:
            px[x, y] = LEAF[step]

    # The limbs, back through the gaps. Only where the canopy above them is in
    # its own shadow, and only on about half of those pixels — a solid limb
    # through a solid canopy is a stick lying on top of it.
    for ix, iy in trail:
        if px[ix, iy] in (LEAF[0], LEAF[1], LEAF[2]) and hash01(ix, iy, 977) > 0.38:
            px[ix, iy] = BARK[1]

    if recipe["strands"]:
        _tree_strands(px, size)

    foot = _contact(px, size, base, BARK)

    outline(body, TREE_OUTLINE)
    _break_crest(body, TREE_OUTLINE, (LEAF[3], LEAF[4]))
    left, right = (min(foot), max(foot)) if foot else (0, width - 1)
    shadow = _cast_shadow(size, left, right, base, LEAF[0], drop=0.03)
    return Image.alpha_composite(shadow, body)


def _break_crest(img: Image.Image, edge: RGBA, lit: tuple[RGBA, ...]) -> None:
    """Drop the outline wherever it sits up-light of a lit foliage pixel (§6).

    `outline()` draws a closed border, which is right for the man-made class
    and wrong for a canopy: a ring all the way round reads as a decal cut out
    and laid on the ground. The line is only removed on the crest facing the
    135deg key — the shade side keeps its border, which is what still holds the
    silhouette up against a lit floor tile.
    """
    px = img.load()
    doomed = [
        (x, y)
        for y in range(img.height)
        for x in range(img.width)
        if px[x, y] == edge
        and any(
            x + dx < img.width and y + dy < img.height and px[x + dx, y + dy] in lit
            for dx, dy in ((1, 0), (0, 1), (1, 1))
        )
    ]
    for x, y in doomed:
        px[x, y] = TRANSPARENT


def _tree_strands(px, size: tuple[int, int]) -> None:
    """1px tails off the underside of a canopy. The willow's whole identity.

    They hang from wherever the foliage currently ends in a column, not from
    the clump centres, so they follow the shape that was actually drawn. Capped
    short of the trunk band: a strand that reaches the floor is a vine.
    """
    width, height = size
    leaf = set(LEAF)
    limit = height * 0.68
    for x in range(width):
        column = [y for y in range(height) if px[x, y] in leaf]
        if not column or hash01(x, 5, 331) > 0.68:
            continue
        bottom = max(column)
        length = 3 + int(hash01(x, 9, 337) * 4)
        for k in range(1, length + 1):
            y = bottom + k
            if y >= height or y > limit or px[x, y][3] != 0:
                break
            px[x, y] = LEAF[1] if k < length else LEAF[0]


# --- campfire ---------------------------------------------------------------
# The only animated prop, and the only light source that is actually drawn
# rather than composited. Frames are a LOOP: every wobble is a sine of the frame
# phase (or an integer multiple of it), so frame N-1 hands back to frame 0 with
# no snap. Nothing here uses rng — an unseeded jitter would make the loop stutter
# at the wrap even though each frame looked fine on its own.


def _blob(px, cx: float, cy: float, radius: float, ramp: Ramp, shade: float) -> None:
    """A small round mass in HARD bands, lit from the upper left (§7, §8).

    Used for the pit stones. It is the rock construction at four pixels
    across: a dome normal against the one key, quantised, with no dither —
    running this through `pick` softened the only plane break the stone had
    and the ring came out as a row of grey dots.
    """
    top = len(ramp) - 1
    kx, ky, kz = TREE_KEY
    r2 = radius * radius
    for y in range(int(cy - radius) - 1, int(cy + radius) + 2):
        for x in range(int(cx - radius) - 1, int(cx + radius) + 2):
            dx = (x - cx) / radius
            dy = (y - cy) / radius
            if (x - cx) ** 2 + (y - cy) ** 2 > r2:
                continue
            up = math.sqrt(max(0.0, 1.0 - dx * dx - dy * dy))
            lam = dx * kx + dy * ky + up * kz
            band = 4 if lam > 0.88 else 3 if lam > 0.58 else 2 if lam > 0.10 else 1
            try:
                px[x, y] = ramp[min(top, max(0, int(band * shade * 2.0)))]
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
            # The end nearest the middle is glowing, not wood any more.
            burn = clamp01(1.0 - abs(t - 0.62) * 3.2)
            for w, band in ((-1, 3), (0, 2), (1, 1)):
                yy = y + w
                if not 0 <= yy < height:
                    continue
                if burn > 0.4:
                    px[x, yy] = pick(COAL, 0.5 + burn * 0.45 * (0.6 + pulse * 0.4), x, yy)
                else:
                    # Long banded strips along the grain axis (§14), keyed off
                    # the column so a strip is one value end to end.
                    dark = hash01(x, 0, 151) > 0.76
                    px[x, yy] = TIMBER[max(0, band - 1) if dark else band]
            if step == 0:
                # The sawn end: the log's one camera-facing plane.
                for w in (-1, 0, 1):
                    yy = y + w
                    if 0 <= yy < height:
                        px[x, yy] = TIMBER[4 if w < 1 else 2]

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


# --- dead wood --------------------------------------------------------------
# A blighted TREE tile swaps this sheet in for `tree.png`, so it shares the
# frame, the anchor and the construction: bole shaded by FACE, root claws at
# the contact line, a cast ellipse sized from those claws. What it does not
# share is the mass — there is no canopy, so the whole read has to come off the
# limb armature, and that is why the limbs are built properly here rather than
# walked as 1px strokes. A branch with no cross-section is a wire, and four
# trees' worth of wire is a scribble.
#
# The wood is GREY (see `DEADWOOD`): drawn in the living bark ramp this is a
# tree that lost its leaves, and drained of hue it reads as bone.

# stems / roots as in TREE_RECIPES. Extra fields:
#   splinter  spikes left standing where the bole broke off. 0 = it did not.
#   limbs     [(start, angle, length, thick, depth)] — start is a fraction of
#             frame height, angle is radians off vertical, length a fraction of
#             frame height, depth how many times it forks.
DEADTREE_RECIPES: dict[str, dict] = {
    # Broken bole with one limb that survived it. The tallest solid shape in
    # the set and the one that still reads as a trunk at a distance.
    "snag": {
        "stems": [(0.48, 0.105, 0.30, 0.02, 0.04)],
        "roots": 4, "splinter": 3,
        "limbs": [(0.46, -0.62, 0.26, 2.2, 2)],
    },
    # A clean Y. Two heavy limbs of equal weight is the one place the
    # no-two-heads rule (§15) is worth breaking: a forked snag is a shape
    # people recognise, and the trunk under it supplies the single thrust.
    "fork": {
        "stems": [(0.50, 0.10, 0.46, 0.0, 0.045)],
        "roots": 4, "splinter": 0,
        "limbs": [(0.48, -0.55, 0.30, 2.6, 2), (0.48, 0.55, 0.30, 2.6, 2)],
    },
    # Five thin limbs off a short bole: the widest, busiest silhouette, and
    # the counterweight to the spire.
    "claw": {
        "stems": [(0.50, 0.115, 0.52, -0.02, 0.05)],
        "roots": 4, "splinter": 0,
        "limbs": [
            (0.54, -1.05, 0.22, 1.6, 2),
            (0.53, -0.50, 0.26, 1.6, 2),
            (0.52, 0.00, 0.28, 1.6, 2),
            (0.53, 0.50, 0.26, 1.6, 2),
            (0.54, 1.05, 0.22, 1.6, 2),
        ],
    },
    # Wind-killed: the bole leans and every limb went with it. One direction
    # of thrust, and the only asymmetric armature in the set.
    "lean": {
        "stems": [(0.60, 0.09, 0.40, -0.13, 0.04)],
        "roots": 4, "splinter": 1,
        "limbs": [(0.44, -0.85, 0.26, 2.0, 2), (0.48, -0.35, 0.30, 2.0, 2)],
    },
    # Tall, thin, almost bare. Height : footprint at the top of the range
    # (§17), which is what makes a stand of these read as depth rather than
    # as clutter.
    "spire": {
        "stems": [(0.50, 0.065, 0.16, 0.03, 0.03)],
        "roots": 4, "splinter": 2,
        "limbs": [
            (0.28, -0.75, 0.16, 1.4, 1),
            (0.34, 0.70, 0.14, 1.4, 1),
            (0.22, 0.35, 0.12, 1.2, 1),
        ],
    },
    # Snapped off low and thick, wearing the heaviest splinter crown. The
    # bottom of the ladder: almost no armature, all bole.
    "stub": {
        "stems": [(0.46, 0.14, 0.52, 0.03, 0.06)],
        "roots": 6, "splinter": 4,
        "limbs": [(0.56, 0.80, 0.20, 2.0, 1)],
    },
}


def _dead_limb(
    px, size: tuple[int, int], x: float, y: float, angle: float, length: float,
    thick: float, depth: int, ramp: Ramp, rng: random.Random,
) -> None:
    """One tapering branch that forks. The cross-section is the point.

    Each step lays a horizontal span whose columns are lit / mid / shade, which
    is the trunk's three faces at branch scale. A limb painted one colour
    across is a wire however carefully it is routed, and the recursion then
    multiplies that into a scribble.
    """
    width, height = size
    for step in range(int(length)):
        t = step / max(length - 1, 1)
        # Curl as it thins: straight limbs off a straight bole make a starburst.
        bend = angle + math.sin(t * 2.2) * 0.20
        x += math.sin(bend)
        y -= math.cos(bend)
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < width and 0 <= iy < height):
            return
        span = max(0, int(thick * (1.0 - t * 0.85)))
        for offset in range(-span, span + 1):
            jx = ix + offset
            if not 0 <= jx < width:
                continue
            if span == 0:
                face = 2
            else:
                across = offset / span
                face = 3 if across < -0.35 else 2 if across < 0.35 else 1
            px[jx, iy] = ramp[face]
        # The shade edge survives down to a 2px limb. It is the last thing to
        # go, because it is the only thing saying the branch has a far side.
        if span >= 1 and ix + span < width:
            px[ix + span, iy] = ramp[0] if span >= 2 else ramp[1]
    if depth <= 0:
        return
    for side in (-1, 1):
        _dead_limb(
            px, size, x, y,
            angle + side * rng.uniform(0.38, 0.80),
            length * rng.uniform(0.44, 0.62),
            thick * 0.55, depth - 1, ramp, rng,
        )


def _dead_splinter(
    px, size: tuple[int, int], cx: float, top: float, half: float,
    count: int, ramp: Ramp, rng: random.Random,
) -> None:
    """The spikes left standing where a bole snapped.

    A flat break reads as a sawn post, which is the stump's job and says
    somebody did it on purpose. Splinters say it came down on its own.
    """
    width, height = size
    for index in range(count):
        frac = (index + 0.5) / count - 0.5
        sx = cx + frac * half * 2.1
        rise = rng.uniform(1.5, 4.0)
        for step in range(int(rise)):
            ix = int(round(sx + frac * step * 0.35))
            iy = int(round(top - step))
            if 0 <= ix < width and 0 <= iy < height:
                px[ix, iy] = ramp[3 if frac < 0 else 1]


def make_dead_tree(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the six dead trees, by name. Same frame and anchor as a living one."""
    recipe = DEADTREE_RECIPES[kind]
    size = (width, height)
    body = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()
    base = height - 1 - height * TREE_SHADOW_BAND

    for stem in recipe["stems"]:
        _tree_stem(px, size, stem, base, recipe["roots"], rng, DEADWOOD)

    stem = recipe["stems"][0]
    cx = stem[0] * (width - 1)
    lean = stem[3]
    for start, angle, length, thick, depth in recipe["limbs"]:
        origin_y = start * height
        _dead_limb(
            px, size, cx + (base - origin_y) * lean, origin_y,
            angle, max(3.0, length * height), thick, depth, DEADWOOD, rng,
        )
    if recipe["splinter"]:
        top = stem[2] * height
        _dead_splinter(
            px, size, cx + (base - top) * lean, top,
            max(1.2, stem[1] * width), recipe["splinter"], DEADWOOD, rng,
        )

    foot = _contact(px, size, base, DEADWOOD)
    outline(body, DEAD_OUTLINE)
    _break_crest(body, DEAD_OUTLINE, (DEADWOOD[2], DEADWOOD[3], DEADWOOD[4]))
    left, right = (min(foot), max(foot)) if foot else (0, width - 1)
    shadow = _cast_shadow(size, left, right, base, DEAD_OUTLINE, drop=0.03)
    return Image.alpha_composite(shadow, body)


# --- stumps -----------------------------------------------------------------
# The one prop in the set whose TOP FACE is most of what you see, so it is the
# clearest statement of the camera (§1): a broad lit ellipse with the bark
# extruded down from it, and the rings are a material detail ON that plane
# rather than the drawing itself. It used to be a rectangle of rings over a
# rectangle of bark, which reads as a low table.
#
# Four states of the same cut, because a stump is a story about what happened
# to a tree and there is more than one story.
STUMP_SHADOW_BAND = 0.14

STUMP_RECIPES: dict[str, dict] = {
    # Sawn flat. Fresh heartwood, full rings — somebody took this one.
    "cut": {"rx": 0.40, "rise": 0.15, "roots": 4, "face": "rings", "wobble": 0.05},
    # Axe-split: a wedge driven out of the cut face. The notch is the
    # silhouette feature and it has to break the top CONTOUR, not just shade it.
    "split": {"rx": 0.42, "rise": 0.13, "roots": 4, "face": "split", "wobble": 0.06},
    # Burnt through. No heartwood at all — the face is char in the dead ramp,
    # which is the only reason four stumps do not read as one recolour.
    "burnt": {"rx": 0.34, "rise": 0.30, "roots": 4, "face": "char", "wobble": 0.07},
    # Rotted hollow. The rim survives, the middle is gone, and the hole is the
    # darkest thing on the sprite.
    "rotten": {"rx": 0.43, "rise": 0.11, "roots": 6, "face": "hollow", "wobble": 0.09},
}


def make_stump(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the four stumps: a lit top plane on an extruded bark drum."""
    recipe = STUMP_RECIPES[kind]
    size = (width, height)
    body = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()

    base = height - 1 - height * STUMP_SHADOW_BAND
    cx = (width - 1) / 2.0
    rx = width * recipe["rx"]
    # Foreshortened by the camera pitch: the top face's depth is a fraction of
    # its WIDTH (§3), never of the frame, which is what shrinks it to a sliver.
    ry = max(1.6, rx * 0.50)
    bottom_y = base - ry
    top_y = bottom_y - height * recipe["rise"]
    lumps = [(rng.uniform(0.5, 1.0) * recipe["wobble"], rng.uniform(0, math.tau))
             for _ in range(2)]

    def edge(angle: float) -> float:
        """Radius multiplier at this angle — bark is not a smooth cylinder."""
        wobble = 1.0
        for index, (amp, phase) in enumerate(lumps):
            wobble += amp * math.sin(angle * (index + 3) + phase)
        return wobble

    # The drum: the cut ellipse dragged down to the contact line, in three
    # vertical faces off one key.
    for x in range(width):
        across = (x - cx) / (rx * edge(0.0 if x >= cx else math.pi))
        if abs(across) > 1.0:
            continue
        face = 3 if across < -0.35 else 2 if across < 0.45 else 1
        # Bark grain: long banded strips along the grain axis (§14), keyed off
        # the frame column so the whole strip is one value top to bottom.
        if hash01(x, 0, 313) > 0.74:
            face = max(face - 1, 0)
        floor = bottom_y + ry * math.sqrt(max(0.0, 1.0 - across * across))
        for y in range(int(top_y), int(round(floor)) + 1):
            if 0 <= y < height:
                px[x, y] = DEADWOOD[face]

    # The cut face. Its mask is kept so the rim can roll off it (§7) — a flat
    # top meeting a flat side on a hard jump reads as folded paper.
    cap = Image.new("1", size, 0)
    cap_px = cap.load()
    char = recipe["face"] == "char"
    notch = rng.uniform(-0.9, -0.3)
    for y in range(int(top_y - ry) - 1, int(top_y + ry) + 2):
        if not 0 <= y < height:
            continue
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - top_y) / ry
            dist = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            if dist > edge(angle):
                continue
            if recipe["face"] == "split" and abs(angle - notch) < 0.55 and dist > 0.2:
                # The split runs INTO the drum, so it takes the wall's darkest
                # step rather than a darker ring: it is a hole, not a mark.
                px[x, y] = DEADWOOD[0]
                continue
            # An upward plane is one value before its material lands on it
            # (§18.3); the rings are that material, banded HARD because a sine
            # of the radius averages to one flat disc at 5px of radius.
            face = 3 if 0.45 < dist < 0.64 else 4
            if dist < 0.18:
                face = 2                       # the pith, and it is not a ring
            if char:
                px[x, y] = DEADWOOD[max(1, face - 2)]
            elif recipe["face"] == "hollow" and dist < 0.46:
                px[x, y] = DEADWOOD[0]
            else:
                px[x, y] = HEARTWOOD[face]
            cap_px[x, y] = 1

    _rock_crest(body, cap, HEARTWOOD, 2)
    _root_spurs(
        px, size, cx, rx * 0.45, base, recipe["roots"], rng, DEADWOOD,
        rise_max=max(1.5, base - bottom_y),
    )
    foot = _contact(px, size, base, DEADWOOD, band=1)
    outline(body, DEAD_OUTLINE)
    _break_crest(body, DEAD_OUTLINE, (HEARTWOOD[3], HEARTWOOD[4], DEADWOOD[3]))
    left, right = (min(foot), max(foot)) if foot else (0, width - 1)
    shadow = _cast_shadow(size, left, right, base, DEAD_OUTLINE, drop=0.05)
    return Image.alpha_composite(shadow, body)


# --- low green --------------------------------------------------------------
# Bush, fern and grass are the three depths a body walks through: a bush is
# BEHIND you, a fern is IN FRONT of you, grass is under your feet. That is a
# rendering fact (see `client/src/render/layers/`) and it decides how each one
# is lit, which is why they do not share a ramp even though they share a
# construction.
#
# All three are built from the canopy's clump — a lobed dome, hard cel bands
# off the one key, a step-0 rim under the lower arc — because a shrub IS a
# small canopy sitting on the ground. What changes per prop is the value key
# and how much of the mass is allowed to be leaves rather than stems:
#
#   bush   lit like the canopy, then sprigs break its outline. It sits behind
#          the player, so it may be the brightest of the three.
#   fern   the same masses drawn two steps down and cooler, with the FRONDS on
#          top of them. It draws OVER the character, so a bright silhouette in
#          front of a body reads as an obstruction rather than as depth — and
#          it gets no cast shadow for the same reason: the ellipse would land
#          on the player.
#   grass  the bottom of the LOD ladder (§16). Three steps, one mass, no
#          accent, no shadow. Detail is DELETED here, not shrunk.

BUSH_SHADOW_BAND = 0.12

# (cx, cy, rx, ry) fractions of the frame, back to front — as TREE_RECIPES.
BUSH_RECIPES: dict[str, dict] = {
    # One dominant mass with two shoulders. The default hedge shape.
    "round": {
        "lobes": 5, "bite": 0.28, "hang": 1.2, "sprigs": 3,
        "clumps": [(0.28, 0.62, 0.26, 0.23), (0.72, 0.60, 0.24, 0.22),
                   (0.48, 0.44, 0.34, 0.27)],
    },
    # Low and wide: reads as ground cover from two tiles away, which is what
    # keeps a clearing's edge from being a line of identical domes.
    "sprawl": {
        "lobes": 6, "bite": 0.32, "hang": 1.1, "sprigs": 4,
        "clumps": [(0.20, 0.66, 0.24, 0.20), (0.52, 0.58, 0.32, 0.25),
                   (0.82, 0.64, 0.22, 0.19)],
    },
    # Tall and narrow, one thrust. The vertical in the set.
    "tuft": {
        "lobes": 5, "bite": 0.32, "hang": 1.3, "sprigs": 4,
        "clumps": [(0.38, 0.66, 0.24, 0.22), (0.58, 0.40, 0.24, 0.27)],
    },
    # Two masses with floor between them — a shrub somebody walked through.
    "split": {
        "lobes": 6, "bite": 0.34, "hang": 1.2, "sprigs": 3,
        "clumps": [(0.24, 0.62, 0.24, 0.24), (0.74, 0.54, 0.29, 0.29)],
    },
    # Half-dead: the smallest mass in the set, so a scattering of these reads
    # as thinning cover rather than as more of the same bush.
    "thin": {
        "lobes": 7, "bite": 0.38, "hang": 1.1, "sprigs": 5,
        "clumps": [(0.38, 0.68, 0.21, 0.20), (0.66, 0.60, 0.23, 0.22)],
    },
}


def _clump_stack(
    px, size: tuple[int, int], recipe: dict, ramp: Ramp, rng: random.Random,
    shade: int = 0,
) -> None:
    """Paint a recipe's clumps back to front, with the seam AO between them.

    `shade` drops every band by that many steps — how the fern gets to be the
    same construction as the bush while staying dark enough to draw over a
    character without fighting it.
    """
    width, height = size
    top = len(ramp) - 1
    for clump in recipe["clumps"]:
        cells = _tree_clump(
            size, clump, recipe["hang"], recipe["lobes"], recipe["bite"],
            rng.randrange(1 << 20),
        )
        mask = {(x, y) for x, y, _ in cells}
        for x, y in mask:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if (nx, ny) in mask or px[nx, ny][3] == 0:
                    continue
                px[nx, ny] = ramp[0]
        for x, y, step in cells:
            px[x, y] = ramp[max(0, min(top, step - shade))]


def _sprigs(
    px, size: tuple[int, int], count: int, ramp: Ramp, rng: random.Random,
    step: int,
) -> None:
    """Loose shoots off the top of a mass, breaking its contour (§15).

    Without them a shrub is a dome, and a dome with hard bands on it is a
    boulder painted green.
    """
    width, height = size
    columns = [x for x in range(width) if any(px[x, y][3] for y in range(height))]
    if not columns:
        return
    for _ in range(count):
        sx = rng.choice(columns)
        crown = min(y for y in range(height) if px[sx, y][3])
        angle = rng.uniform(-0.7, 0.7)
        for k in range(1, rng.randint(3, 4)):
            ix = int(round(sx + math.sin(angle) * k))
            iy = int(round(crown - math.cos(angle) * k))
            if 0 <= ix < width and 0 <= iy < height:
                px[ix, iy] = ramp[step if k < 3 else max(0, step - 1)]
                if k < 2 and ix + 1 < width and px[ix + 1, iy][3] == 0:
                    px[ix + 1, iy] = ramp[max(0, step - 2)]


def make_bush(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the five shrubs. Drawn BEHIND characters, and it sways."""
    recipe = BUSH_RECIPES[kind]
    size = (width, height)
    body = Image.new("RGBA", size, TRANSPARENT)
    px = body.load()
    base = height - 1 - height * BUSH_SHADOW_BAND

    _clump_stack(px, size, recipe, SHRUB, rng)
    _sprigs(px, size, recipe["sprigs"], SHRUB, rng, 3)
    foot = _contact(px, size, base, SHRUB, band=1)
    outline(body, TREE_OUTLINE)
    _break_crest(body, TREE_OUTLINE, (SHRUB[3], SHRUB[4]))
    left, right = _footprint(body, foot)
    shadow = _cast_shadow(size, left, right, base, SHRUB[0], drop=0.05)
    return Image.alpha_composite(shadow, body)


# One mass, a fan of fronds over it, and how far the fan leans. Ferns are the
# ones the player pushes through face-first, so the set varies by LEAN more
# than by outline: five ferns all standing up straight is a fence.
FERN_RECIPES: dict[str, dict] = {
    "open":  {"fronds": 11, "fan": 2.3, "lean": 0.00, "arc": 0.75, "reach": 0.92},
    "left":  {"fronds": 10, "fan": 1.9, "lean": -0.42, "arc": 0.95, "reach": 0.88},
    "right": {"fronds": 10, "fan": 1.9, "lean": 0.42, "arc": 0.95, "reach": 0.88},
    "tall":  {"fronds": 9, "fan": 1.5, "lean": 0.06, "arc": 0.55, "reach": 1.10},
    "flat":  {"fronds": 13, "fan": 2.7, "lean": -0.10, "arc": 1.15, "reach": 0.74},
}

# The crown the fronds rise out of. Shared by all five: what varies is the fan,
# not the root mass, and giving each its own would have been five drawings of
# a thing that is 90% hidden by the fronds standing in front of it.
FERN_CROWN = {
    "lobes": 5, "bite": 0.42, "hang": 1.0,
    "clumps": [(0.34, 0.80, 0.24, 0.16), (0.64, 0.78, 0.26, 0.17)],
}


def make_fern(width: int, height: int, kind: str, rng: random.Random) -> Image.Image:
    """One of the five ferns. Drawn IN FRONT of characters.

    This is the depth trick: a handful scattered over open ground means the
    player walks behind foliage instead of across a flat plane, and it costs
    one sprite plus a draw pass. It gets NO cast shadow — the sprite is drawn
    over the character, so its ellipse would land on the player's chest.
    """
    recipe = FERN_RECIPES[kind]
    size = (width, height)
    img = Image.new("RGBA", size, TRANSPARENT)
    px = img.load()

    _clump_stack(px, size, FERN_CROWN, FROND, rng, shade=1)

    root_x = width * (0.5 + recipe["lean"] * 0.12)
    for index in range(recipe["fronds"]):
        frac = (index + 0.5) / recipe["fronds"] - 0.5
        angle = frac * recipe["fan"] + recipe["lean"]
        arc = recipe["arc"] * (1 if angle >= 0 else -1)
        length = height * recipe["reach"] * rng.uniform(0.62, 1.0)
        x = root_x + rng.uniform(-1.5, 1.5)
        y = float(height - 1)
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            # Straight at the root, curling over at the tip.
            bend = angle + arc * t * t
            x += math.sin(bend) * 0.9
            y -= math.cos(bend) * 0.9
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= ix < width and 0 <= iy < height):
                break
            # A frond has a lit upper edge and a shade under it — that 1px
            # pair is the only volume a 1px stalk can carry, and without it
            # five ferns are a scribble of identical strands.
            px[ix, iy] = FROND[3 if t > 0.45 else 2]
            if iy + 1 < height:
                px[ix, iy + 1] = FROND[1 if t > 0.45 else 0]
            if t < 0.35 and ix + 1 < width:
                px[ix + 1, iy] = FROND[1]
    return img


def make_grass(width: int, height: int, rng: random.Random) -> Image.Image:
    """A tuft of blades. The bottom of the LOD ladder (§16): three steps, one
    mass, no accent, no shadow — at 10px the ramp is spent on saying which side
    the light is on and nothing else."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    root_x = width * rng.uniform(0.42, 0.58)
    for _ in range(rng.randint(5, 8)):
        root = root_x + rng.uniform(-width * 0.3, width * 0.3)
        length = rng.uniform(height * 0.55, height * 1.0)
        bend = rng.uniform(-0.45, 0.45)
        for step in range(int(length)):
            t = step / max(length - 1, 1)
            x = int(round(root + bend * step * t))
            y = height - 1 - step
            if not (0 <= x < width and 0 <= y < height):
                break
            # Tips catch the lantern, the mass stays down the ramp, and the
            # blade's right side carries the shade — three steps, hard.
            px[x, y] = BLADE[3 if t > 0.6 else 2]
            if x + 1 < width and px[x + 1, y][3] == 0:
                px[x + 1, y] = BLADE[1]
    # The tuft plants on a 1px contact line rather than a cast ellipse: a blob
    # of shadow under something 10px tall is bigger than the thing throwing it.
    for x in range(width):
        column = [y for y in range(height) if px[x, y][3] != 0]
        if column:
            px[x, max(column)] = BLADE[0]
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
    # Six species, six recipes — the rocks' argument again: what has to differ
    # between two trees is the silhouette, and noise does not vary a silhouette.
    trees = [make_tree(tree_w, tree_h, kind, rng) for kind in TREE_RECIPES]
    pack(trees, tree_w, tree_h).save(out_dir / "tree.png")

    # Same frame as a living tree, so a blighted tile swaps sheets and nothing
    # else — see the client's `blight` field.
    rng = random.Random(args.seed + 212)
    dead_trees = [make_dead_tree(tree_w, tree_h, kind, rng) for kind in DEADTREE_RECIPES]
    pack(dead_trees, tree_w, tree_h).save(out_dir / "deadtree.png")

    stump_w, stump_h = tile, round(tile * 0.875)
    rng = random.Random(args.seed + 222)
    stumps = [make_stump(stump_w, stump_h, kind, rng) for kind in STUMP_RECIPES]
    pack(stumps, stump_w, stump_h).save(out_dir / "stump.png")

    grass_w = grass_h = round(tile * 0.625)
    rng = random.Random(args.seed + 303)
    grasses = [make_grass(grass_w, grass_h, rng) for _ in range(6)]
    pack(grasses, grass_w, grass_h).save(out_dir / "grass.png")

    bush_w, bush_h = round(tile * 1.25), tile
    rng = random.Random(args.seed + 313)
    bushes = [make_bush(bush_w, bush_h, kind, rng) for kind in BUSH_RECIPES]
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
    ferns = [make_fern(fern_w, fern_h, kind, rng) for kind in FERN_RECIPES]
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
