#!/usr/bin/env python3
"""Asset pipeline: procedural forest terrain textures.

Sibling of make_placeholder_sheet.py + process_sprites.py, but with no "raw"
stage. Characters start as hand- or AI-drawn art that has to be keyed, cropped
and downscaled; terrain is *generated*, so this script writes final-resolution
pixels directly into assets/processed/.

Output (assets/processed/terrain/):
    ground.png    64x64 — a 4x4 grid of 16px floor tiles
    rock.png      5 frames, 16x20   solid blocker
    tree.png      4 frames, 24x40   solid blocker, overhangs its tile
    grass.png     6 frames, 10x10   decoration, non-solid, sways
    fern.png      5 frames, 20x18   FOREGROUND decoration, drawn over characters
    campfire.png  8 frames, 24x28   solid blocker, ANIMATED (a frame loop)
    manifest.json

Two shapes of asset, because the world has two kinds of thing in it:

  * The GROUND is square. It tiles, so it must be seamless, and it is the only
    asset the client draws for every single tile.
  * ROCKS, TREES and GRASS are not square. They are silhouettes with alpha that
    sit ON TOP of the ground, bottom-anchored and centred on their tile, the
    same anchoring process_sprites.py gives a character. A tree is 40px tall on
    a 16px tile: the extra 24px is canopy that overhangs the tile above.

Seamlessness is the whole trick of ground.png. It is generated as ONE 64x64
image from *periodic* value noise — the noise lattice wraps at 64px, so the
left edge is the continuation of the right edge — and then read back as a 4x4
grid of 16px tiles. The client picks its tile with `(tx % 4, ty % 4)`, which
gives 16 distinct-looking floor tiles that are guaranteed to line up, because
they are neighbouring windows into one continuous texture. Choosing a random
variant per tile instead would put a visible seam on every tile boundary.

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

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "assets" / "processed"

# Mirrors server/app/config.py TILE_SIZE. The ground atlas is GROUND_TILES
# square, so at tile 16 it is a 64x64 image.
DEFAULT_TILE = 16
GROUND_TILES = 4

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

EARTH: Ramp = [rgb(c) for c in ("#1d1a15", "#26221a", "#2f2a20", "#383026", "#43392d")]
MOSS: Ramp = [rgb(c) for c in ("#22291d", "#2b3524", "#33402b", "#3c4c32")]
GRIT: Ramp = [rgb(c) for c in ("#4b4034", "#554839", "#3a3228")]

ROCK_RAMP: Ramp = [rgb(c) for c in ("#242327", "#312f34", "#403d43", "#4e4a51", "#5d5860")]
ROCK_OUTLINE = rgb("#131418")
ROCK_MOSS = rgb("#33422c")

BARK: Ramp = [rgb(c) for c in ("#231a13", "#2e231a", "#3b2d21", "#493829")]
LEAF: Ramp = [rgb(c) for c in ("#1a2618", "#22321f", "#2b3f26", "#354d2d", "#425e37")]
TREE_OUTLINE = rgb("#10160f")

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


# --- periodic value noise ---------------------------------------------------
# Lattice indices wrap with `% cells`, which is what makes the field tileable
# over `size` pixels. Nothing here is fast; it runs on a 64x64 image once.


def lattice(rng: random.Random, cells: int) -> list[list[float]]:
    return [[rng.random() for _ in range(cells)] for _ in range(cells)]


def _fade(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


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
    """Deterministic 0..1 from integers. Used for per-pixel grain."""
    h = 2166136261
    for value in values:
        h ^= value & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


# --- ground -----------------------------------------------------------------


def make_ground(size: int, seed: int) -> Image.Image:
    """One seamless size x size floor texture, read back as a grid of tiles."""
    rng = random.Random(seed)
    # High cell counts on purpose: features smaller than a tile keep the 4x4
    # repeat from being legible once the atlas is tiled across a whole map.
    earth = [(lattice(rng, cells), cells) for cells in (4, 8, 16)]
    moss = [(lattice(rng, cells), cells) for cells in (5, 10)]

    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            base = fbm(earth, x, y, size)
            # Fine grain breaks up the smooth interpolation into soil speckle.
            grain = (hash01(x, y, seed) - 0.5) * 0.26
            colour = pick(EARTH, base * 1.25 - 0.14 + grain, x, y)

            # Moss is a faint accent, not the surface. Kept rare on purpose:
            # the atlas repeats every 4 tiles, and any feature big or bright
            # enough to notice turns that repeat into a visible lattice. The
            # greenery the player actually sees is the client's grass tufts,
            # which are hashed across the whole map and never repeat.
            damp = fbm(moss, x, y, size)
            if damp > 0.78:
                colour = pick(MOSS, (damp - 0.78) / 0.22 + grain, x, y)

            # Sparse grit: single bright pixels reading as pebbles and twigs.
            if hash01(x, y, seed + 991) > 0.975:
                colour = GRIT[int(hash01(y, x, seed) * len(GRIT)) % len(GRIT)]

            px[x, y] = colour
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


def make_rock(width: int, height: int, rng: random.Random, scale: float) -> Image.Image:
    """A squat boulder: jagged radial silhouette, lit from the upper left."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()

    cx = (width - 1) / 2.0
    base_y = height - 1.0
    rx = width * 0.48 * scale
    ry = height * 0.62 * scale
    # Per-rock lumpiness: a few sine harmonics on the radius, so no two frames
    # share a silhouette but every one still reads as a rounded boulder. Kept
    # small — big amplitudes turn a boulder into gravel at this size.
    harmonics = [(rng.uniform(0.03, 0.09), rng.uniform(0, math.tau)) for _ in range(3)]

    for y in range(height):
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - base_y) / ry
            if dy > 0.15:
                continue
            angle = math.atan2(dy, dx)
            wobble = 1.0
            for index, (amp, phase) in enumerate(harmonics):
                wobble += amp * math.sin(angle * (index + 2) + phase)
            if dx * dx + dy * dy > wobble * wobble:
                continue
            # Shade by height on the rock plus a light direction from up-left.
            up = clamp01(-dy)
            side = clamp01(0.5 - dx * 0.45)
            shade = up * 0.55 + side * 0.45 + (hash01(x, y, 7) - 0.5) * 0.14
            px[x, y] = pick(ROCK_RAMP, shade, x, y)

    # Moss creeps up the shaded base — ties the rock to the forest floor.
    for y in range(height):
        for x in range(width):
            if px[x, y][3] == 0:
                continue
            if y > height * 0.62 and hash01(x, y, 313) > 0.72:
                px[x, y] = ROCK_MOSS

    outline(img, ROCK_OUTLINE)
    return img


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
    ground = make_ground(ground_size, args.seed)
    ground.save(out_dir / "ground.png")

    rock_w, rock_h = tile, round(tile * 1.25)
    rng = random.Random(args.seed + 101)
    # Sizes stagger from pebble to boulder so a cluster does not look stamped.
    rocks = [
        make_rock(rock_w, rock_h, rng, scale)
        for scale in (0.55, 0.72, 0.86, 1.0, 0.94)
    ]
    pack(rocks, rock_w, rock_h).save(out_dir / "rock.png")

    tree_w, tree_h = round(tile * 1.5), round(tile * 2.5)
    rng = random.Random(args.seed + 202)
    trees = [make_tree(tree_w, tree_h, tile, rng) for _ in range(4)]
    pack(trees, tree_w, tree_h).save(out_dir / "tree.png")

    grass_w = grass_h = round(tile * 0.625)
    rng = random.Random(args.seed + 303)
    grasses = [make_grass(grass_w, grass_h, rng) for _ in range(6)]
    pack(grasses, grass_w, grass_h).save(out_dir / "grass.png")

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
        "ground": {
            "file": "ground.png",
            "tile": tile,
            "cols": GROUND_TILES,
            "rows": GROUND_TILES,
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
            "grass": {
                "file": "grass.png",
                "frameWidth": grass_w,
                "frameHeight": grass_h,
                "frames": len(grasses),
                "solid": False,
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
        f"wrote {out_dir}: ground {ground_size}x{ground_size} "
        f"({GROUND_TILES}x{GROUND_TILES} tiles), "
        f"rock {len(rocks)}x{rock_w}x{rock_h}, "
        f"tree {len(trees)}x{tree_w}x{tree_h}, "
        f"grass {len(grasses)}x{grass_w}x{grass_h}, "
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
