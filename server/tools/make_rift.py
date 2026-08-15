#!/usr/bin/env python3
"""Asset pipeline: the extraction rift — a STRUCTURE, not a prop.

Everything else in `scenery/` is something people left behind. This is the one
thing on the map that answers back: four cut stones at the corners of a sigil,
a console on the approach face, and a tear in the world at the centre that is
not there until somebody presses the button.

Output (assets/processed/rift/):
    scar.png      1 frame,   64x64  DECAL — the sigil cut into the ground
    pillar.png    4x2,       16x48  PROP  — four stones, dormant then awake
    console.png   2 frames,  20x24  PROP  — the button, idle then armed
    charge.png    14 frames, 32x56  VFX   — one-shot: a pillar waking
    crown.png     8 frames,  32x56  VFX   — loop: an awake pillar's halo
    emerge.png    20 frames, 64x80  VFX   — one-shot: the rift tearing open
    rift.png      16 frames, 64x80  VFX   — loop: the rift at rest, unstable
    manifest.json

THREE SHAPES, AND THE SPLIT IS THE WHOLE DESIGN
This file writes into all three of the pipeline's categories at once, and it has
to, because the structure is made of three different kinds of thing:

  * The SIGIL is a DECAL. It lies flat, has no outline and no implied face, and
    the client bakes it into its ground canvas. It is cut INTO the soil, so it
    is partly transparent and the ground's own grain reads through the grooves.
  * The STONES and the CONSOLE are PROPS. Baked colour, bottom-anchored,
    depth-sorted with the party, lit by the same night everything else is lit
    by. A player walks behind a pillar and disappears behind it.
  * The LIGHT — a pillar charging, a pillar's crown, the rift itself — is VFX.
    Greyscale, anchored on `anchorY`, drawn additively AFTER the darkness pass,
    tinted at draw time. A pillar is a thing being lit; the light coming out of
    it is not.

Drawing the awake pillar as one baked sprite with its glow painted in would put
the glow under the night multiply, and a beacon you can only see when you are
already standing next to it is not a beacon.

THE HUE IS `--scene-beacon`, AND IT IS ALREADY DECIDED
`client/src/styles/index.css` reserved `--scene-beacon: 118 255 196` for this
and nothing else — cold mint, deliberately the odd one out against a forest lit
entirely by fire. `BEACON` below is that colour ramped, and it is baked into the
two PROP sheets because a prop's colour is its material. The VFX sheets stay
greyscale and the client multiplies the same mint onto them, exactly as the
kindle roar is greyscale and gets `fire.core`. If that CSS variable ever moves,
this ramp moves with it or the structure grows two greens.

THE HANDOFFS ARE THE HARD PART
Two of these sheets are one-shots that hand over to loops, and a one-shot whose
last frame does not equal its loop's frame 0 pops on the seam — the one artifact
that would give away that the rift is a sprite. So the convergence is
STRUCTURAL, not eyeballed: `charge` ends by calling the same `_crown_paint` that
draws `crown`, at `phase=0`, with its own one-shot extras already faded to
nothing; `emerge` ends by calling the same `_anomaly` that draws `rift`, with
the parameters `_rift_state(0.0)` returns. `build` then measures both seams and
prints the worst channel difference. It must be 0.

WHY THE ANOMALY IS DRAWN AS ABSENCE
The reference is a dark spiked shell with light pouring out of cell-shaped
openings. You cannot draw a dark body additively — additive light cannot
subtract. So the shell is never drawn: the CELLS are, as filled lozenges lying
on the surface of an implied sphere, and the dark body is the negative space
between them. Over a night forest that reads exactly as the reference does, and
it costs nothing. Cells on the far hemisphere are drawn faintly too, which is
what makes it a translucent volume instead of a sticker.

Usage:
    python tools/make_rift.py
    python tools/make_rift.py --seed 7 --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    ROCK_OUTLINE,
    ROCK_RAMP,
    Ramp,
    TRANSPARENT,
    add,
    clamp01,
    ease_in,
    ease_out,
    ellipse,
    hash01,
    pack,
    pick,
    quantize_alpha,
    resolve,
    rgb,
)

# --- materials ---------------------------------------------------------------

#: The beacon, ramped. Step 4 is `--scene-beacon` itself (118 255 196); the two
#: below it are what the mint collapses to in shadow and the one above is the
#: core. It goes brighter at the top than any soil ramp for the same reason
#: FLAME does: this is a self-lit thing and the client's darkness pass
#: multiplies over the sprite, so a mint in the forest's own value range would
#: have nothing left to read as light.
BEACON: Ramp = [
    rgb(c) for c in ("#08201d", "#0e4034", "#1c6d54", "#33a37c", "#76ffc4", "#e4fff4")
]

#: A dead socket: the lens in a dormant pillar and the ring on an idle console.
#: Cooler and darker than the stone around it, so an unlit fitting reads as
#: something switched OFF rather than as a hole in the sprite.
SOCKET = rgb("#0b1a16")

#: The console's head. Nothing else in the game is worked metal — the stones are
#: quarried and everything in `scenery/` is wood, cloth or bone — so the console
#: reads as the one part of this that somebody BUILT, which is why it is also
#: the part you are allowed to touch.
#: Six steps, not five: the top two carry an UNLIT plunger's highlight, and
#: without them the idle button is a dark patch on a dark panel.
IRON: Ramp = [
    rgb(c) for c in ("#15171a", "#1f2329", "#2c3138", "#3a4048", "#4a515a", "#626a75")
]

#: Cut stone seen from directly above, for the sigil. Lower contrast than
#: `ROCK_RAMP` on purpose: a decal is a mark on the floor and must never start
#: reading as an object standing on it.
GROOVE: Ramp = [rgb(c) for c in ("#0c0e0c", "#141713", "#1d211b", "#282d24", "#343a2f")]


# --- the prism ---------------------------------------------------------------
#
# THE ANOMALY IS THE ONE VFX IN THIS GAME THAT CARRIES ITS OWN COLOUR, and it is
# an exception with a reason rather than a shortcut.
#
# Every other effect sheet is greyscale because it BELONGS to something whose
# colour varies: a summon column is the arriving player's, an aura is the loot's
# rarity, the kindle roar is the fire's. Tinting at draw time is what lets one
# sheet serve a whole roster.
#
# The rift belongs to nobody. It is not light cast by an object, it IS the
# object, and its colour is its identity — the one thing on the map that is not
# lit by fire and not lit by a lamp. And it is not one colour: the reference is
# IRIDESCENT, every opening in the shell a different pastel, which is precisely
# what a single draw-time tint can never produce. So the hue is resolved here.
#
# `charge` and `crown` stay greyscale and stay tinted with `--scene-beacon`,
# because those belong to the PILLARS — quarried, built, part of this world. The
# structure is cold mint; the thing it opens is not. That contrast is the point.

#: Ordered as a spectrum, because overlapping shapes blend to the WEIGHTED MEAN
#: of their hue indices — so neighbours in this list have to be neighbours to
#: the eye, or two crossing cells resolve to a colour neither of them is.
ROSE, VIOLET, CYAN, MINT, AMBER, CORE = range(6)

#: Six ramps, sampled off the reference. TWO dark steps and FOUR pale ones, and
#: that split is the whole balance: the dark pair is where a faint contribution
#: lands, so the shell's own body and the far-side cells stay nearly black
#: instead of glowing; the pale four are where a lit opening lands, and the
#: reference's openings are PASTEL — almost white with a colour cast — not
#: saturated. Ramping these the way a soil ramp is ramped, evenly from dark to
#: hue, produced candy: legibly coloured, and half the luminance of the
#: greyscale sheet it replaced.
#:
#: Each tops out near white on purpose: where two openings overlap the field
#: sums past the end of the ramp and the crossing goes hot, which is what makes
#: the lattice read as light coming THROUGH something rather than as paint.
PRISM: tuple[Ramp, ...] = tuple(
    [rgb(c) for c in steps]
    for steps in (
        ("#2a0a18", "#6b2040", "#c4557f", "#ff9dc0", "#ffc8dd", "#ffeaf2"),
        ("#180d2e", "#3a2470", "#7a55c4", "#b08cf0", "#d4bcff", "#f0e6ff"),
        ("#041c2a", "#0d4a68", "#2288b4", "#5cc4e8", "#9ee4f8", "#d8f6ff"),
        ("#08201d", "#10503c", "#26906a", "#4fd6a0", "#96ffd4", "#dcfff0"),
        ("#2b1c06", "#6b4a12", "#b8862c", "#ffc766", "#ffdf9c", "#fff4d4"),
        ("#232329", "#55555f", "#8f8f9c", "#c8c8d2", "#ececf2", "#ffffff"),
    )
)


def conduit(up: float) -> int:
    """Which prism ramp the structure's own light is in, `up` = 0 at the foot.

    THE PILLARS BURN THE ANOMALY'S LIGHT, NOT THEIR OWN. They were mint — the
    reserved beacon colour — while the thing they open is iridescent, and that
    made the stones read as somebody else's equipment parked around it. Running
    them up the same prism says the opposite: this is the rift's light, and the
    stones are only the plumbing.

    It is a GRADIENT UP THE SHAFT rather than one hue, because a channel of even
    colour reads as a painted stripe. Deep violet at the foot where the light
    is still under pressure, through cyan, to a white-hot crown — cold at the
    bottom and hot at the top is the same rule the campfire's flame ramp
    follows, borrowed for a colder fire.

    All four stones share it. Giving each its own accent would be prettier for
    one screenshot and would stop them reading as four parts of one structure.
    """
    if up < 0.34:
        return VIOLET
    if up < 0.68:
        return CYAN
    if up < 0.90:
        return MINT
    return CORE


def lit(hue: int, value: float) -> RGBA:
    """One flat step off a prism ramp — no dithering.

    Ordered dither is right for a broad soil where the eye reads an average.
    Inside a three-pixel channel it is a checkerboard, and a checkerboard is
    what a light looks like when it is broken.
    """
    ramp = PRISM[hue]
    return ramp[int(clamp01(value) * (len(ramp) - 1) + 0.5)]


class Prism:
    """An intensity field and, beside it, the hue that intensity is arriving in.

    `make_textures.resolve` paints one field through one ramp, which is right
    for every effect that is a single colour. An iridescent object needs a
    second channel, and the cheap correct one is a hue field weighted by
    intensity: each shape adds `amount` to `light` and `amount * hue` to `tone`,
    so dividing at the end gives the weighted mean hue at that pixel. A bright
    cell overlapping a faint one wins the crossing in proportion to how much
    light each is actually contributing, which is what mixing looks like.

    Shapes go in through `ellipse`/`add` so the geometry still comes from the
    shared vocabulary in `make_textures.py` — this only decides what colour the
    light that arrives is, never what shape it is.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.light = [[0.0] * width for _ in range(height)]
        self.tone = [[0.0] * width for _ in range(height)]

    def add(self, x: int, y: int, amount: float, hue: float) -> None:
        if 0 <= y < self.height and 0 <= x < self.width and amount > 0.0:
            self.light[y][x] += amount
            self.tone[y][x] += amount * hue

    def ellipse(
        self, cx: float, cy: float, rx: float, ry: float,
        strength: float, hue: float, hollow: float = 0.0,
    ) -> None:
        scratch = [[0.0] * self.width for _ in range(self.height)]
        ellipse(scratch, cx, cy, rx, ry, strength, hollow)
        for y in range(self.height):
            row = scratch[y]
            for x in range(self.width):
                value = row[x]
                if value > 0.0:
                    self.light[y][x] += value
                    self.tone[y][x] += value * hue

    def paint(
        self, image: Image.Image, floor: float = 0.08,
        tone: float = 1.04, gain: float = 1.05,
    ) -> None:
        px = image.load()
        top = len(PRISM) - 1
        for y in range(self.height):
            for x in range(self.width):
                value = self.light[y][x]
                if value <= floor:
                    continue
                # Round to a whole ramp rather than interpolating between two.
                # Blending the ramps themselves would put every crossing in a
                # muddy in-between step; snapping keeps six clean families and
                # lets the ordered dither in `pick` do the mixing, which is the
                # same way every other surface in this game blends.
                index = int(self.tone[y][x] / value + 0.5)
                ramp = PRISM[0 if index < 0 else top if index > top else index]
                colour: RGBA = pick(ramp, clamp01(value * tone), x, y)
                px[x, y] = (colour[0], colour[1], colour[2], quantize_alpha(value * gain))


# --- the structure -----------------------------------------------------------

#: The plot, in tiles. Big enough that the anomaly (4 tiles across) has a tile
#: of air between it and the stones, small enough that the four corners still
#: read as the corners of ONE thing rather than as a fence. The space you
#: actually fight in is the clearing around this, not inside it.
PLOT_TILES = 7

#: One stone per corner, each cut differently. There is no `flip` anywhere in
#: the layout and that is deliberate: these are shaded from the upper left like
#: every other sprite in the game, and a mirrored pillar is lit from the wrong
#: side. Four shapes is what buys the variety a flip would have bought.
PILLAR_SHAPES = 4
#: Dormant, awake. Frame index is `shape * PILLAR_STATES + state`, packed
#: shape-major so state 0 of each shape is its idle — the same convention the
#: crate sheet uses for its kinds.
PILLAR_STATES = 2

CONSOLE_STATES = 2

# One pillar waking: a spark at the foot, the light climbing the channel, the
# crown catching. `CHARGE_CROWN` is the frame the capstone flashes on and is
# what a sound would land its impact on.
CHARGE_FRAMES = 14
CHARGE_FPS = 14
CHARGE_WAKE = 0.08
CHARGE_CROWN = 0.55

# An awake pillar, holding. LOOPING — every term is a sine of the frame phase.
CROWN_FRAMES = 8
CROWN_FPS = 10

# The rift tearing open: a seam, the pull, the burst, the settle. `EMERGE_BURST`
# is the frame it actually arrives on.
EMERGE_FRAMES = 20
EMERGE_FPS = 16
EMERGE_SEAM = 0.10
EMERGE_BURST = 0.40
#: By here the shell is at its resting size and everything after is the
#: one-shot's own debris fading out. Past this point the frame is already the
#: loop's frame 0 with extras on top.
EMERGE_SETTLE = 0.82

# The rift at rest. LOOPING, and it must never look restful.
#
# `frames / fps` is ALSO the rotation period, because the lattice spins exactly
# one turn per loop — that is the only spin that brings every cell back to
# where it started, so the loop is the revolution and there is no separate
# knob for it. Four seconds. At 16 frames and 12 fps this was 1.3 s and the
# sphere read as a spinning top: menace comes from something big moving
# slowly, and a fast rotation makes a 64px object look small and light.
#
# The frame count went up with the period rather than the fps coming down, so
# the step stays 11 degrees a frame and the spin stays smooth instead of
# strobing round in visible jumps.
RIFT_FRAMES = 32
RIFT_FPS = 8

#: Openings on the shell. Enough that the sphere reads as a lattice, few enough
#: that at 64px each one is still a shape rather than a speck.
CELLS = 46
#: Spines. They live on the same sphere as the cells and stick out along the
#: radius, so one pointing at the camera is a dot and one at the limb is a
#: needle — which is what makes a flat ring of them read as a ball.
SPIKES = 26


# --- pillar ------------------------------------------------------------------


class PillarGeometry:
    """Where the stone is, so nothing has to guess where its channel runs.

    `charge.png` and `crown.png` are ONE pair of sheets shared by all four
    stones, so they are built against shape 0's geometry and every row they
    light comes from here. Hardcoding the channel's rows in the effect would
    mean a pillar redesign silently lighting the air beside it.
    """

    def __init__(self, height: int, shape: int) -> None:
        # Same family, four cuts: one plumb, one leaning with a chipped cap, one
        # squat, one tall and narrow with a crack through the shaft.
        shorten = (0, 0, 3, -2)[shape]
        self.shape = shape
        self.lean = (0.0, 0.9, 0.0, -0.6)[shape]
        self.cap_half = (5.4, 5.4, 5.9, 4.9)[shape]
        self.cap_top = 3 + shorten
        self.cap_bot = self.cap_top + 8
        self.base_top = height - 7
        self.height = height
        #: The lens in the capstone — the fitting the light actually lives in.
        self.lens_y = self.cap_top + 4.0
        #: The channel cut up the front of the shaft. It runs INTO the base
        #: rather than stopping above it — see `sink` in `_pillar_channel`.
        self.groove_top = self.cap_bot + 1
        self.groove_bot = self.base_top + 2
        #: Where the channel starts being swallowed by the footing.
        self.sink_top = self.base_top - 3
        #: Awake, the capstone comes off the shaft and hangs. Two pixels is
        #: enough to read at this size and small enough that it still looks
        #: like a stone held up rather than a stone thrown.
        self.lift = 2

    def centre(self, width: int, y: float) -> float:
        """Column centre at row `y` — a leaning stone's is not constant."""
        span = max(self.height - self.cap_top, 1)
        fall = clamp01((y - self.cap_top) / span)
        return (width - 1) / 2.0 + self.lean * (1.0 - fall)

    def half_width(self, y: float) -> float:
        if y < self.cap_bot:
            # A chamfer on the very top row, or the capstone reads as a brick.
            return self.cap_half - (0.9 if y <= self.cap_top else 0.0)
        if y < self.base_top:
            t = (y - self.cap_bot) / max(self.base_top - self.cap_bot, 1)
            # Battered: wider at the foot. A stone with parallel sides reads as
            # a post, and a post does not look like it is holding anything up.
            return 3.6 + t * 0.8
        t = (y - self.base_top) / max(self.height - self.base_top, 1)
        return 5.3 + t * 1.1


def _chipped(geo: PillarGeometry, x: int, y: int, cx: float) -> bool:
    """Damage that removes stone, so the outline follows the break."""
    if geo.shape == 1:
        # A corner knocked off the cap.
        return y < geo.cap_top + 3 and x - cx > 2.4 - (y - geo.cap_top)
    if geo.shape == 2:
        # A notch bitten out of the left flank.
        return abs(y - (geo.cap_bot + 9)) < 2 and cx - x > 2.6
    return False


def make_pillar(width: int, height: int, shape: int, awake: bool) -> Image.Image:
    """One standing stone, dormant or awake.

    Baked colour, bottom-anchored, outlined — a prop, drawn in the depth sort
    and multiplied by the night like everything else standing in the forest.
    The mint in the awake frame is the crystal itself, not its glow: the glow is
    `crown.png` and it is added over the darkness, not under it.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    geo = PillarGeometry(height, shape)
    lift = geo.lift if awake else 0

    # Build the silhouette first, then paint it. Deriving the outline from the
    # body means a chip or a lean cannot leave a keyline hanging in the air.
    body: dict[tuple[int, int], float] = {}
    for row in range(geo.cap_top, height):
        cx = geo.centre(width, row)
        half = geo.half_width(row)
        # The capstone is a separate piece and rides up when the stone wakes.
        drawn = row - lift if row < geo.cap_bot else row
        for x in range(width):
            if abs(x - cx) > half or _chipped(geo, x, row, cx):
                continue
            if 0 <= drawn < height:
                body[(x, drawn)] = (x - cx) / max(half, 0.5)

    # Quarried, not extruded. A handful of pixels bitten off the flanks of the
    # shaft, before the outline is derived, so the keyline follows the damage.
    # At 16 pixels wide this is the entire difference between a standing stone
    # and a lamp post: a machined edge reads as manufactured no matter what
    # colour it is painted.
    for (x, y), u in list(body.items()):
        if geo.cap_bot < y < geo.base_top and abs(u) > 0.78:
            if hash01(x, y, shape * 41 + 13) > 0.84:
                del body[(x, y)]

    for (x, y), u in body.items():
        edge = any((x + ox, y + oy) not in body for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if edge:
            px[x, y] = ROCK_OUTLINE
            continue
        # Lit from the upper left, darker toward the foot — the same light every
        # other sprite in the game is under.
        shade = 0.68 - u * 0.40 - (y / height) * 0.12
        shade += (hash01(x, y, shape * 97 + 5) - 0.5) * 0.22
        if shape == 3 and abs(y - (geo.cap_bot + 12)) < 1.2 and abs(u) < 0.85:
            shade -= 0.45  # the crack, drawn as shadow rather than as a hole
        px[x, y] = pick(ROCK_RAMP, clamp01(shade), x, y)

    _pillar_channel(px, width, height, geo, awake)
    return img


def _pillar_channel(px, width: int, height: int, geo: PillarGeometry, awake: bool) -> None:
    """The channel up the shaft and the lens in the cap.

    Dormant these are CUT: a dark groove with a lit lip on the far side, which
    is how a chisel mark reads from above-left. Awake they are FILLED, and the
    fill runs brightest at the top because the light is going somewhere — a
    channel of even brightness reads as a painted stripe.

    THE LIT PIXELS ARE PICKED OFF THE RAMP DIRECTLY, not dithered through
    `pick`. Ordered dither is right for a broad soil where the eye reads an
    average; inside a three-pixel channel it is a checkerboard, and a
    checkerboard is what a light looks like when it is broken.
    """
    lift = geo.lift if awake else 0
    span = max(geo.groove_bot - geo.groove_top, 1)

    for row in range(geo.groove_top, geo.groove_bot + 1):
        cx = geo.centre(width, row)
        up = 1.0 - (row - geo.groove_top) / span
        for x in range(int(cx - 1.5), int(cx + 2.5)):
            if not 0 <= x < width:
                continue
            off = abs(x - cx) / 1.6
            if off > 1.0:
                continue
            if awake:
                # THE CHANNEL DOES NOT STOP, IT SINKS. Ending it in mid-shaft
                # left a bright violet band floating above the footing, which
                # reads as paint that ran out — the light has to come from
                # somewhere, and the only place it can come from is under the
                # stone. So the last rows dim and narrow into the base.
                sink = clamp01((geo.groove_bot - row + 1) / 5.0) if row > geo.sink_top else 1.0
                if sink <= 0.05 or off > sink:
                    continue
                px[x, row] = lit(
                    conduit(up), (0.52 + 0.44 * up) * (1.0 - 0.30 * off) * (0.35 + 0.65 * sink)
                )
            elif row > geo.sink_top:
                continue  # the dormant groove stops at the footing
            elif off > 0.62 and x > cx:
                px[x, row] = ROCK_RAMP[2]  # the far lip catching the light
            else:
                px[x, row] = ROCK_RAMP[0]

    # The gap the capstone leaves when it comes off the shaft. Filled with the
    # brightest step there is: this is the whole tell that the stone is ON.
    if awake:
        for row in range(geo.cap_bot - lift, geo.cap_bot):
            cx = geo.centre(width, row)
            for x in range(int(cx - 3.0), int(cx + 4.0)):
                if 0 <= x < width and abs(x - cx) <= 3.0:
                    px[x, row] = lit(CORE, 1.0) if abs(x - cx) < 1.6 else lit(MINT, 0.9)

    lens_y = geo.lens_y - lift
    lens_x = geo.centre(width, geo.lens_y)
    for row in range(int(lens_y - 3.5), int(lens_y + 4.5)):
        if not 0 <= row < height:
            continue
        for x in range(width):
            d = math.hypot((x - lens_x) / 2.3, (row - lens_y) / 2.9)
            if d > 1.0:
                continue
            if awake:
                # The lens is where the light leaves: white core, cyan rim.
                px[x, row] = lit(CORE if d < 0.5 else CYAN, 0.62 + (1.0 - d) * 0.38)
            else:
                px[x, row] = SOCKET if d > 0.55 else ROCK_RAMP[0]


# --- console -----------------------------------------------------------------


def make_console(width: int, height: int, armed: bool) -> Image.Image:
    """The button. Idle, then slammed.

    Everything else in this structure is quarried stone and light. This is iron
    on a stone footing, and it is the only piece the player is meant to walk up
    to and touch — so it is the only piece drawn at eye height, with a face
    turned toward the camera and one plunger big enough to read as pressable
    from across the clearing.

    It is a LECTERN, not a box: the panel is a trapezoid, narrow at the far
    edge and wide at the near one. That single taper is what tells the eye the
    face is tilted up at it, and without it the head is a rectangle standing on
    a post and the whole thing reads as a sign.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    lip, face_top, face_bot = 5, 7, 17

    body: dict[tuple[int, int], tuple[float, str]] = {}
    for y in range(lip, height):
        if y < face_top:
            # The far edge, seen nearly end-on: a dark lip above the face.
            half, part = 5.4, "lip"
        elif y < face_bot:
            t = (y - face_top) / max(face_bot - face_top, 1)
            half, part = 5.6 + t * 1.9, "face"
        else:
            t = (y - face_bot) / max(height - face_bot, 1)
            half, part = 3.4 + t * 1.3, "post"
        for x in range(width):
            if abs(x - cx) <= half:
                body[(x, y)] = ((x - cx) / max(half, 0.5), part)

    for (x, y), (u, part) in body.items():
        edge = any((x + ox, y + oy) not in body for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if edge:
            px[x, y] = ROCK_OUTLINE
            continue
        if part == "post":
            shade = 0.60 - u * 0.34 - (y / height) * 0.14
            px[x, y] = pick(ROCK_RAMP, clamp01(shade + (hash01(x, y, 613) - 0.5) * 0.18), x, y)
            continue
        # The lip is in its own shadow; the face catches the light. Two flat
        # values with a hard boundary, because that boundary IS the fold.
        shade = 0.24 - u * 0.10 if part == "lip" else 0.70 - u * 0.30 - (y - face_top) * 0.022
        px[x, y] = pick(IRON, clamp01(shade + (hash01(x, y, 613) - 0.5) * 0.12), x, y)

    # The plunger: proud when idle, driven flush when armed. The travel is a
    # pixel and a half — at this size the state is carried by the socket
    # LIGHTING UP, not by the throw of the button, so the travel only has to be
    # enough that the two frames are not mistaken for one.
    plunger_y = 12.4 if armed else 10.9
    for y in range(lip, face_bot + 3):
        for x in range(width):
            if (x, y) not in body:
                continue
            d = math.hypot((x - cx) / 3.4, (y - plunger_y) / 2.8)
            if d <= 1.0:
                if armed:
                    px[x, y] = lit(CORE if d < 0.45 else CYAN, 0.55 + (1.0 - d) * 0.45)
                else:
                    # A DOME, lit from the upper left like everything else in
                    # the game. A flat disc reads as a hole, and a hole is the
                    # one thing a button must not look like.
                    px[x, y] = pick(IRON, clamp01(
                        0.86 - d * 0.16 - (x - cx) / 3.4 * 0.24
                        - (y - plunger_y) / 2.8 * 0.28
                    ), x, y)
            elif d <= 1.36:
                px[x, y] = lit(VIOLET, 0.62) if armed else SOCKET

    # Two pips flanking the plunger. Nothing says "console" at 20 pixels like a
    # pair of indicator lamps that are dead until they are not.
    for side in (-1, 1):
        for oy in range(2):
            x, y = int(round(cx + side * 6.0)), int(round(plunger_y - 0.5 + oy))
            if (x, y) in body:
                px[x, y] = lit(MINT, 0.78) if armed else SOCKET

    if not armed:
        # A shadow under a raised button. Without it the plunger is a sticker.
        for x in range(width):
            y = int(plunger_y + 3)
            if (x, y) in body and abs(x - cx) < 3.2:
                px[x, y] = IRON[0]
    else:
        # Spill along the fold, where the live face meets its own lip. Painted
        # only on pixels the body actually owns — a highlight drawn one row
        # above the silhouette is a line floating in the air.
        for x in range(width):
            if (x, face_top) in body and abs(x - cx) < 3.4:
                px[x, face_top] = lit(CYAN, 0.82)
    return img


# --- the sigil ---------------------------------------------------------------


def make_scar(size: int, rng: random.Random) -> Image.Image:
    """The mark on the ground the rift opens out of.

    A DECAL, and it obeys the decal rules exactly: flat, no outline, no implied
    face, and partly transparent so the soil's own grain reads through the
    grooves. It is cut INTO the floor. Giving this a keyline would stand it up
    at ankle height and the structure would gain a fifth object nobody built.

    It is also the only piece that is on screen when nothing is happening, so it
    carries the whole "there is something here" read on its own: two rings, four
    channels running out at the diagonals toward the stones, and glyph chords
    between them.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    c = (size - 1) / 2.0
    outer = size * 0.38
    inner = size * 0.20

    def cut(x: int, y: int, depth: float, alpha: float) -> None:
        if not (0 <= x < size and 0 <= y < size):
            return
        prior = px[x, y][3]
        value = clamp01(depth + (hash01(x, y, 421) - 0.5) * 0.30)
        colour: RGBA = pick(GROOVE, value, x, y)
        px[x, y] = (colour[0], colour[1], colour[2], max(prior, int(clamp01(alpha) * 255)))

    for y in range(size):
        for x in range(size):
            dx, dy = x - c, y - c
            dist = math.hypot(dx, dy)
            for radius, thick, depth in ((outer, 1.7, 0.05), (inner, 1.3, 0.12)):
                off = abs(dist - radius)
                if off <= thick:
                    fade = 1.0 - off / thick
                    # The far lip of a groove catches the light; the near lip
                    # and the bottom do not. That gradient is the only thing
                    # telling the eye this is cut rather than drawn.
                    lip = 0.45 if (dist > radius and dy > 0) else 0.0
                    cut(x, y, depth + lip * fade, 0.55 + fade * 0.35)

    # Four channels out to the corners, where the stones are. They stop at the
    # edge of the decal rather than reaching the pillars: a line drawn all the
    # way would be a diagram, and the gap is what makes the player join it up.
    for corner in range(4):
        angle = math.pi / 4.0 + corner * math.pi / 2.0
        ux, uy = math.cos(angle), math.sin(angle)
        steps = int((size * 0.5 - inner) * 2.2)
        for step in range(steps + 1):
            t = step / steps
            r = inner + t * (size * 0.5 - inner)
            wobble = math.sin(t * 7.0 + corner) * 0.5
            x = int(round(c + ux * r - uy * wobble))
            y = int(round(c + uy * r + ux * wobble))
            # Fades out toward the rim: the cut got shallower as it ran.
            cut(x, y, 0.04, 0.92 * (1.0 - t * 0.45))
            cut(x + int(round(uy)), y - int(round(ux)), 0.48, 0.60 * (1.0 - t * 0.5))
            cut(x - int(round(uy)), y + int(round(ux)), 0.10, 0.55 * (1.0 - t * 0.5))

    # Glyph chords between the rings — the part that is writing rather than
    # geometry. Rolled, because six identical marks would read as a clock face.
    for glyph in range(8):
        angle = rng.uniform(0, math.tau)
        arc = rng.uniform(0.18, 0.42)
        radius = rng.uniform(inner + 2.5, outer - 2.5)
        steps = int(arc * radius * 2.0) + 2
        for step in range(steps + 1):
            a = angle + arc * (step / steps)
            x = int(round(c + math.cos(a) * radius))
            y = int(round(c + math.sin(a) * radius))
            cut(x, y, 0.02, 0.80)

    # Chips knocked out of the floor around it. Keeps the ring from reading as
    # something that was printed on undamaged ground.
    for _ in range(60):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(inner * 0.35, size * 0.47)
        x = int(round(c + math.cos(angle) * radius))
        y = int(round(c + math.sin(angle) * radius))
        cut(x, y, rng.uniform(0.0, 0.5), rng.uniform(0.18, 0.45))
    return img


# --- a pillar's light --------------------------------------------------------


def _crown_paint(
    prism: Prism,
    width: int,
    geo: PillarGeometry,
    contact_y: int,
    phase: float,
    level: float,
) -> None:
    """An awake pillar's steady light. Shared by `crown` and `charge`'s tail.

    Every term is a sine of `phase` or an integer harmonic of it, so the loop
    wraps. `charge` calls this at `phase=0` with `level=1` on its last frame,
    which is what makes the one-shot hand over to the loop without a snap —
    the two frames are the same call, not two drawings that look alike.

    PRISMATIC AND BAKED, like the anomaly and unlike every other effect sheet
    in the game. The stone's glow has to be the same light as the thing it
    opened, and a single draw-time tint can only ever be one hue — so the
    conduit gradient is resolved here and `tinted` is false in the manifest.
    """
    cx = geo.centre(width, geo.lens_y)
    breathe = 0.90 + 0.10 * math.sin(phase)
    lens_y = geo.lens_y - geo.lift
    span = max(geo.groove_bot - geo.groove_top, 1)

    for row in range(geo.groove_top, geo.groove_bot + 1):
        up = 1.0 - (row - geo.groove_top) / span
        # A band running UP the channel — the light is going somewhere.
        band = 0.84 + 0.16 * math.sin(row * 0.55 - phase * 2.0)
        centre = geo.centre(width, row)
        # The glow sinks with the channel it is sitting on, or the sprite
        # goes dark at the footing while the light over it does not.
        sink = clamp01((geo.groove_bot - row + 1) / 5.0) if row > geo.sink_top else 1.0
        for x in range(int(centre - 2.5), int(centre + 3.5)):
            if not 0 <= x < width:
                continue
            off = abs(x - centre) / 2.4
            if off > 1.0:
                continue
            prism.add(x, row,
                      level * (0.34 + 0.42 * up) * (1.0 - off) ** 1.3 * band * sink,
                      conduit(up))

    # The lens, and the halo it throws. White at the source, cooling outward —
    # the same read the anomaly's core has.
    prism.ellipse(cx, lens_y, 2.6 * breathe, 3.0 * breathe, level * 1.55, CORE)
    prism.ellipse(cx, lens_y, 5.2 * breathe, 5.8 * breathe, level * 0.34, CYAN)
    prism.ellipse(cx, lens_y, 4.4 * breathe, 5.0 * breathe, level * 0.30, VIOLET, hollow=0.42)

    # Motes leaving the lens, wrapping with the phase.
    for i in range(3):
        rise = ((phase / math.tau) + i / 3.0) % 1.0
        mx = int(round(cx + math.sin(phase + i * 2.1) * 2.6))
        my = int(round(lens_y - rise * 15.0))
        prism.add(mx, my, level * 0.75 * (1.0 - rise), MINT)

    # A pool at the foot, so the stone is standing IN its own light. Violet:
    # the cold end of the conduit, where the light has not gone anywhere yet.
    prism.ellipse(geo.centre(width, geo.height), contact_y,
                  6.0 * breathe, 2.1 * breathe, level * 0.60, VIOLET)


def make_crown_frame(
    width: int, height: int, contact_y: int, geo: PillarGeometry, index: int, total: int
) -> Image.Image:
    """One frame of an awake pillar holding. LOOP."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    prism = Prism(width, height)
    _crown_paint(prism, width, geo, contact_y, (index / total) * math.tau, 1.0)
    prism.paint(img, floor=0.08, tone=1.02, gain=1.05)
    return img


def make_charge_frame(
    width: int, height: int, contact_y: int, geo: PillarGeometry, index: int, total: int
) -> Image.Image:
    """One frame of a pillar waking. ONE-SHOT: spark, climb, crown, hold.

    Ends ON `crown` frame 0 by construction — the tail is `_crown_paint` at
    phase 0 plus extras that reach exactly zero at t=1.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    prism = Prism(width, height)
    t = index / max(total - 1, 1)
    if t <= 0.0:
        return img

    cx = geo.centre(width, geo.lens_y)
    base_x = geo.centre(width, geo.height)
    lens_y = geo.lens_y - geo.lift
    wake = clamp01(t / CHARGE_WAKE)

    if t < CHARGE_CROWN:
        # A spark at the foot first: the light comes from the ground, and you
        # have to see where it started or the climb reads as the stone
        # switching on from the top.
        prism.ellipse(base_x, contact_y, 3.0 + wake * 4.0, 1.2 + wake * 1.4,
                      0.5 + wake * 0.9, VIOLET)
        climb = ease_in(clamp01((t - CHARGE_WAKE) / (CHARGE_CROWN - CHARGE_WAKE)))
        front = geo.groove_bot - climb * (geo.groove_bot - lens_y)
        for row in range(int(front), geo.groove_bot + 1):
            # Brightest at the head, trailing off behind it.
            tail = clamp01(1.0 - (row - front) / 9.0)
            centre = geo.centre(width, row)
            for x in range(int(centre - 2.5), int(centre + 3.5)):
                if not 0 <= x < width:
                    continue
                off = abs(x - centre) / 2.2
                if off > 1.0:
                    continue
                # The climbing head carries the conduit's colour for the row
                # it is passing, so the light CHANGES as it rises rather than
                # arriving at the crown the colour it left the ground.
                up = 1.0 - (row - geo.groove_top) / max(geo.groove_bot - geo.groove_top, 1)
                prism.add(x, row, wake * (0.35 + tail * 1.25) * (1.0 - off) ** 1.3,
                          conduit(up))
        # Motes shaken loose along the shaft as the front goes past.
        for i in range(5):
            my = int(round(front + 2.0 + i * 1.7))
            mx = int(round(geo.centre(width, my) + math.sin(i * 2.4 + index * 0.7) * 3.4))
            prism.add(mx, my, wake * 0.55 * (1.0 - i / 5.0), CYAN)
        prism.paint(img, floor=0.08, tone=1.02, gain=1.05)
        return img

    # --- the crown catches, then settles into the loop ------------------------
    _crown_paint(prism, width, geo, contact_y, 0.0, 1.0)
    since = (t - CHARGE_CROWN) / (1.0 - CHARGE_CROWN)
    flash = max(0.0, 1.0 - since * 2.0)
    if flash > 0.0:
        prism.ellipse(cx, lens_y, 3.0 + flash * 7.0, 3.4 + flash * 7.5, 1.9 * flash, CORE)
        # A ring thrown along the ground, not through the air: what the stone
        # did was land, and the ground is what answers.
        radius = ease_out(min(1.0, since / 0.6))
        prism.ellipse(base_x, contact_y, 4.0 + radius * 11.0, 1.4 + radius * 3.4,
                      (1.0 - min(1.0, since / 0.6)) * 1.3, CYAN, hollow=0.5)
        for i in range(9):
            if hash01(i, index, 733) < 0.3:
                continue
            angle = hash01(i, 5, 91) * math.tau
            travel = since * (5.0 + hash01(i, 8, 17) * 9.0)
            prism.add(int(round(cx + math.cos(angle) * travel)),
                      int(round(lens_y + math.sin(angle) * travel * 0.75)),
                      max(0.0, 0.95 - since * 1.9), MINT)
    prism.paint(img, floor=0.08, tone=1.02, gain=1.05)
    return img


# --- the anomaly -------------------------------------------------------------


#: The golden angle. Successive multiples of it never repeat and never bunch,
#: which is the whole reason a sunflower packs seeds this way.
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def _cell_table(count: int) -> tuple[tuple[float, float, float, float], ...]:
    """Openings on the shell: (latitude, longitude, radius, aspect).

    SPREAD BY THE GOLDEN ANGLE, NOT ROLLED, and that is the difference between
    a lattice and a rash. Random points on a sphere clump — a dozen land on top
    of one another, the additive field saturates where they overlap, and the
    shell comes out as a white blob with bald patches beside it. A Fibonacci
    spiral covers evenly at any count, so the GAPS between cells stay even too,
    and the gaps are what is doing the work here: they are the dark shell.

    A little jitter goes back on top, because a perfectly even lattice reads as
    a golf ball. Sizes are skewed hard toward pinholes with a few real lenses
    among them, and each cell is stretched tangentially, so they sit on the
    surface like scales rather than like drilled holes.
    """
    #: Which pastel each opening arrives in. Mint appears twice so it stays the
    #: plurality — the rift has to look related to the mint the pillars burn,
    #: or the structure and the thing it opened read as two unconnected props.
    #: The rest are accents, in the proportions the reference uses.
    palette = (MINT, CYAN, MINT, ROSE, AMBER, VIOLET, CYAN, ROSE)
    cells = []
    for i in range(count):
        lat = math.asin(1.0 - 2.0 * (i + 0.5) / count)
        lat += (hash01(i, 9, 71) - 0.5) * 0.20
        cells.append((
            lat,
            i * GOLDEN_ANGLE + hash01(i, 10, 137) * 0.12,
            1.1 + hash01(i, 3, 197) ** 2.2 * 4.2 * (1.75 if i % 7 == 3 else 1.0),
            1.15 + hash01(i, 8, 419) * 1.30,
            # Walked, not rolled. A rolled hue puts three roses side by side
            # somewhere on the sphere and the iridescence turns into a stain;
            # stepping through the palette guarantees every neighbour differs.
            palette[i % len(palette)],
        ))
    return tuple(cells)


def _spike_table(count: int) -> tuple[tuple[float, float, float], ...]:
    """Spines: (latitude, longitude, length). Spread the same way, for the same
    reason — a corona with a gap in it reads as a sprite that was cropped."""
    return tuple(
        (
            math.asin(1.0 - 2.0 * (i + 0.5) / count) + (hash01(i, 4, 509) - 0.5) * 0.30,
            i * GOLDEN_ANGLE + hash01(i, 5, 227) * 0.20,
            3.5 + hash01(i, 6, 881) * 8.5,
            # Cooler than the openings. The reference's corona is blue-violet
            # while its cells are pastel: the light leaving the shell has
            # already been through it, and it comes out the far end shifted.
            (CYAN, VIOLET, CYAN, MINT)[i % 4],
        )
        for i in range(count)
    )


CELL_TABLE = _cell_table(CELLS)
SPIKE_TABLE = _spike_table(SPIKES)


def _shell(
    prism: Prism,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    spin: float,
    bright: float,
    shear: float,
    opened: float,
) -> None:
    """The cells, projected onto an implied sphere.

    NOTHING DRAWS THE BODY. The dark shell in the reference is the gaps between
    these, and over a night forest that is exactly how it reads — additive light
    cannot subtract, so a body drawn here could only ever brighten the hole it
    is supposed to be.

    Cells on the far hemisphere are drawn at a fraction of the strength, which
    is what turns a ring of blobs into a translucent volume with a back to it.
    Each one is squashed ALONG THE RADIUS from the disc's centre, because that
    is the direction a patch on a sphere foreshortens in — squashing everything
    horizontally instead is right at the equator and visibly wrong at the poles.
    """
    for lat, lon0, size, aspect, hue in CELL_TABLE:
        lon = lon0 + spin
        depth = math.cos(lat) * math.cos(lon)
        sx = cx + rx * math.cos(lat) * math.sin(lon)
        sy = cy - ry * math.sin(lat)
        # The lurch: the top of the shell slides against the bottom.
        sx += shear * math.sin(lat)
        visible = abs(depth)
        front = depth > 0.0
        strength = bright * (0.26 + 0.62 * visible) * (1.0 if front else 0.20) * opened
        if strength <= 0.04:
            continue

        dxc, dyc = sx - cx, sy - cy
        angle = math.atan2(dyc, dxc) if math.hypot(dxc, dyc) > 1e-4 else 0.0
        ca, sa = math.cos(angle), math.sin(angle)
        radial = max(0.5, size * max(visible, 0.14) * opened)
        across = max(0.5, size * aspect * opened)

        for y in range(int(sy - across) - 1, int(sy + across) + 2):
            for x in range(int(sx - max(radial, across)) - 1, int(sx + max(radial, across)) + 2):
                ddx, ddy = x - sx, y - sy
                a = (ddx * ca + ddy * sa) / radial
                b = (-ddx * sa + ddy * ca) / across
                dist = math.hypot(a, b)
                if dist > 1.0:
                    continue
                # A PLATEAU, not a bell. These are OPENINGS: flat inside, hard
                # at the rim. A falloff from the centre reads as glare on glass
                # and turns the whole lattice into a field of soft blobs, which
                # is the one failure that stops it looking like the reference.
                #
                # The rim of an opening runs HOTTER than its middle — light
                # bending round the edge of the hole it is coming through. That
                # is where the reference's warm outlines on the pale cells come
                # from, and it is one term.
                fill = min(1.0, (1.0 - dist) * 3.2)
                edge = max(0.0, 1.0 - abs(dist - 0.82) / 0.26)
                prism.add(x, y, strength * (fill + edge * 0.45), hue)


def _spines(
    prism: Prism,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    spin: float,
    bright: float,
    phase: float,
    reach: float,
) -> None:
    """Needles out of the shell, along the radius.

    Length scales with how far off the view axis the spine is, so one pointing
    at the camera collapses to a dot and one at the limb is full length. That
    single rule is what makes a two-dimensional ring of lines read as spines on
    a ball instead of as a sun.
    """
    for index, (lat, lon0, length, hue) in enumerate(SPIKE_TABLE):
        lon = lon0 + spin
        depth = math.cos(lat) * math.cos(lon)
        if depth < -0.15:
            continue
        ex = cx + rx * math.cos(lat) * math.sin(lon)
        ey = cy - ry * math.sin(lat)
        dxc, dyc = ex - cx, ey - cy
        dist = math.hypot(dxc, dyc)
        if dist < 1e-3:
            continue
        ux, uy = dxc / dist, dyc / dist
        off_axis = math.sqrt(max(0.0, 1.0 - depth * depth))
        # An integer harmonic of the phase, so the flicker wraps with the loop.
        flick = 0.70 + 0.30 * math.sin(phase * 2.0 + index * 1.7)
        span = length * off_axis * flick * reach
        if span < 0.8:
            continue
        steps = max(2, int(span * 2.0))
        for step in range(steps + 1):
            t = step / steps
            px_ = ex + ux * span * t
            py_ = ey + uy * span * t
            taper = (1.0 - t) ** 1.25
            # A spine runs hot at the root and cools to its own hue at the
            # tip, so the corona is white where it leaves the shell and
            # coloured where it ends — which is what a prism does to a spike.
            prism.add(int(round(px_)), int(round(py_)), bright * 0.80 * taper,
                      hue + (CORE - hue) * taper * 0.55)
            if t < 0.34:
                # A needle has a root. One pixel wide all the way down reads as
                # a scratch on the glass rather than as part of the object.
                prism.add(int(round(px_ + uy)), int(round(py_ - ux)),
                          bright * 0.32 * taper, CORE)
                prism.add(int(round(px_ - uy)), int(round(py_ + ux)),
                          bright * 0.32 * taper, CORE)
        # The dotted net trailing past the tips — the reference's best detail
        # and nearly free: two detached specks on the same ray.
        for k in range(2):
            if hash01(index, k, 61) < 0.45:
                continue
            far = 1.13 + k * 0.22
            prism.add(int(round(ex + ux * span * far)),
                      int(round(ey + uy * span * far)), bright * 0.22, hue)


def _anomaly(
    prism: Prism,
    width: int,
    contact_y: int,
    cy: float,
    radius: float,
    spin: float,
    stretch_x: float,
    stretch_y: float,
    bright: float,
    shear: float,
    phase: float,
    reach: float,
    opened: float,
) -> None:
    """One complete picture of the rift, at whatever state it is in.

    `rift` and the tail of `emerge` both go through here, with the same
    arguments at the seam. That is the only reason the handoff is clean.
    """
    cx = (width - 1) / 2.0
    rx = radius * stretch_x
    ry = radius * stretch_y

    # IT FLOATS. Breathing alone made it a pulsing ball sitting in mid-air; a
    # slow vertical drift is what says the thing is HANGING there, unsupported,
    # and it is the cheapest possible term — one sine of the loop phase, so it
    # wraps like everything else and is exactly 0 at phase 0 (which is what
    # keeps the emerge handoff exact).
    #
    # The floor does NOT move with it. The pool stays where the ground is and
    # only tightens and brightens as the sphere comes down, which is what a
    # light source approaching a surface actually does — and that contrast is
    # what makes the rise read as the RIFT moving rather than the camera.
    bob = math.sin(phase) * radius * 0.10
    cy += bob
    near = 1.0 - bob / max(radius * 0.10, 1e-6) * 0.18

    # The core, seen through the biggest opening. Sat low, like the reference:
    # the shell is thinner underneath and that is where the inside shows.
    prism.ellipse(cx, cy + ry * 0.20, rx * 0.34, ry * 0.26, bright * 0.42, CORE)
    # A whisper of a rim so the silhouette has an edge without being outlined.
    # VIOLET, because in the reference the shell's own edge is the one part that
    # is not pastel — it is the dark body catching light from behind.
    prism.ellipse(cx, cy, rx, ry, bright * 0.15, VIOLET, hollow=0.24)
    _shell(prism, cx, cy, rx, ry, spin, bright, shear, opened)
    _spines(prism, cx, cy, rx, ry, spin, bright, phase, reach)

    # It is HOVERING, and the ground under it has to say so.
    #
    # THE POOL IS MEASURED FROM THE SPHERE, not from a floor row. This effect
    # never touches the ground, so `contact_y` was a fiction inherited from the
    # sheets that do — and pinning the pool to it left the glow a full sphere
    # further down than the ball, landing on the far rim of the sigil instead
    # of inside it. Under the sphere's own lower edge is where light cast by a
    # hovering object actually falls.
    floor_y = cy - bob + ry * 0.78
    bloom = (0.85 + 0.15 * math.sin(phase)) * near
    # The pool on the floor is COOL — cyan into violet at its rim, the same
    # gradient the pillars run and the coldest end of the prism. Mint made it
    # the greenest thing on screen and pulled the eye off the sphere onto the
    # dirt underneath it, which is the wrong half of the object.
    prism.ellipse(cx, floor_y, rx * 0.52 * bloom, ry * 0.13 * bloom,
                  0.95 * bright * opened, CYAN)
    prism.ellipse(cx, floor_y, rx * 0.66 * bloom, ry * 0.16 * bloom,
                  0.34 * bright * opened, VIOLET, hollow=0.40)

    # Motes falling INTO it out of the ground: the rift is taking, not giving.
    for i in range(7):
        drift = ((phase / math.tau) + i / 7.0) % 1.0
        mx = int(round(cx + math.sin(phase + i * 1.9) * rx * 0.7))
        my = int(round(floor_y - drift * (floor_y - cy - ry * 0.4)))
        prism.add(mx, my, bright * 0.55 * (1.0 - drift) * opened,
                  CELL_TABLE[i * 5 % len(CELL_TABLE)][4])


def _rift_state(phase: float) -> tuple[float, float, float, float, float]:
    """`(spin, stretch_x, stretch_y, bright, instability)` at a loop phase.

    THE WHOLE LOOP IS A FUNCTION OF PHASE and every term is a sine, a cosine, or
    an integer harmonic of one, so frame 0 and the last frame meet with nothing
    to hide. Using `rng` per frame here would stutter at the wrap even though
    each frame looked right on its own — the same trap the crate sheet documents.

    `instability` is the point of the whole sheet. A fourth power of a raised
    cosine is nearly zero almost everywhere and spikes hard twice a cycle, so
    the rift sits there breathing and then LURCHES — which is what "unstable"
    looks like. A smooth pulse would read as calm, and a thing you are about to
    stand inside should not read as calm.
    """
    spin = phase  # exactly one turn per loop, so the lattice wraps onto itself
    instability = ((1.0 - math.cos(phase * 2.0)) * 0.5) ** 4
    breathe = 1.0 + 0.045 * math.sin(phase * 2.0)
    stretch_x = breathe * (1.0 + 0.11 * instability)
    stretch_y = breathe * (1.0 - 0.08 * instability)
    bright = 0.92 + 0.16 * math.sin(phase) + 0.24 * instability
    return spin, stretch_x, stretch_y, bright, instability


def make_rift_frame(
    width: int, height: int, contact_y: int, radius: float, index: int, total: int
) -> Image.Image:
    """One frame of the rift at rest. LOOP."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    prism = Prism(width, height)
    phase = (index / total) * math.tau
    spin, stretch_x, stretch_y, bright, instability = _rift_state(phase)
    _anomaly(
        prism, width, contact_y, _hover_y(contact_y, radius), radius, spin,
        stretch_x, stretch_y, bright, instability * 2.0, phase, 1.0, 1.0,
    )
    prism.paint(img)
    return img


def _hover_y(contact_y: int, radius: float) -> float:
    """Centre row of the sphere. It hangs clear of the floor by design — a rift
    resting on the ground is a bonfire, and the gap under it is what says the
    thing is not obeying the same rules the players are."""
    return contact_y - radius - 5.0


def make_emerge_frame(
    width: int, height: int, contact_y: int, radius: float, index: int, total: int
) -> Image.Image:
    """One frame of the rift tearing open. ONE-SHOT.

    Seam, pull, burst, settle. It lands EXACTLY on `rift` frame 0: past
    `EMERGE_SETTLE` the shell arguments are literally `_rift_state(0.0)` and the
    only thing left is one-shot debris whose envelope reaches zero before t=1.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    prism = Prism(width, height)
    t = index / max(total - 1, 1)
    if t <= 0.0:
        return img

    cx = (width - 1) / 2.0
    cy = _hover_y(contact_y, radius)
    # Same rule as `_anomaly`: the floor this throws light onto is under the
    # SPHERE, not at the bottom of the frame. The rest of the resting state is
    # no longer read here — the tail derives its own from `_rift_state(phase)`
    # so that it is already moving at loop rate before the handover.
    _, _, rest_y, _, _ = _rift_state(0.0)
    floor_y = cy + radius * rest_y * 0.78

    # --- SEAM: a hairline splits, and the air starts falling into it ---------
    if t < EMERGE_BURST:
        wake = clamp01(t / EMERGE_SEAM)
        opening = ease_in(clamp01((t - EMERGE_SEAM) / (EMERGE_BURST - EMERGE_SEAM)))
        lens_w = 0.9 + opening * radius * 0.30
        lens_h = 4.0 + opening * radius * 0.92
        # The seam is WHITE. Nothing has come through yet, so there is nothing
        # for the prism to split — the colour arrives WITH the shell, at the
        # burst, and that is what makes the burst read as an arrival rather
        # than as the same light getting bigger.
        prism.ellipse(cx, cy, lens_w, lens_h, wake * (0.85 + opening * 1.35), CORE)
        prism.ellipse(cx, cy, lens_w * 1.7, lens_h * 1.12,
                      wake * (0.35 + opening * 0.55), VIOLET, hollow=0.40)
        prism.ellipse(cx, floor_y, radius * (0.20 + opening * 0.45),
                      radius * (0.05 + opening * 0.12),
                      wake * (0.45 + opening * 0.85), CYAN)
        # Specks pulled IN, against the way everything flies at the burst. The
        # reversal is what makes the burst feel like a release.
        for i in range(16):
            pull = 1.0 - clamp01(opening * 1.15 + hash01(i, 2, 97) * 0.22)
            angle = hash01(i, 3, 41) * math.tau
            far = radius * (0.75 + hash01(i, 9, 13) * 1.05) * pull
            prism.add(int(round(cx + math.cos(angle) * far)),
                      int(round(cy + math.sin(angle) * far * 0.85)),
                      wake * (0.30 + opening * 0.75) * (1.0 - pull), VIOLET)
        prism.paint(img)
        return img

    # --- BURST and SETTLE: it inflates past its size and contracts onto it ---
    settle = clamp01((t - EMERGE_BURST) / (EMERGE_SETTLE - EMERGE_BURST))
    grown = ease_out(settle)

    # THE TAIL IS ALREADY THE LOOP, RUN BACKWARDS FROM ITS OWN FRAME 0.
    #
    # It used to hold `phase = 0` for the whole settle, which made every term a
    # constant — so once the debris had faded (well before the end) the sheet
    # played several byte-identical frames and the effect visibly emerged,
    # FROZE, and only started moving again when the client swapped to the loop.
    # The seam was perfect and the motion was not, which is the harder half.
    #
    # Instead the phase counts UP to exactly 0 on the last frame at the loop's
    # own angular rate, so the shell is already turning, breathing and floating
    # at rest speed before the handover — there is no frame where it stops. The
    # step is derived from both sheets' rates rather than typed in, or re-timing
    # either one silently reintroduces the stall.
    step = math.tau * RIFT_FPS / (EMERGE_FPS * RIFT_FRAMES)
    phase = -(total - 1 - index) * step
    base_spin, base_x, base_y, base_bright, base_instability = _rift_state(phase)

    over = 1.0 + 0.34 * (1.0 - grown)
    # An extra turn on top while it inflates, decaying to nothing — so it spins
    # up and DECELERATES into its resting rate instead of stepping down to it.
    # Exactly `base_spin` at grown = 1, which is what keeps the seam exact.
    spin = base_spin + math.tau * (1.0 - grown)
    stretch_x = base_x * over
    stretch_y = base_y * (1.0 + 0.20 * (1.0 - grown))
    bright = base_bright + 1.30 * (1.0 - grown)
    shear = base_instability * 2.0 + 3.4 * (1.0 - grown)
    reach = 1.0 + 1.5 * (1.0 - grown)
    opened = grown if settle < 1.0 else 1.0

    _anomaly(prism, width, contact_y, cy, radius, spin, stretch_x, stretch_y,
             bright, shear, phase, reach, opened)

    # One-shot debris, on its own clock. Reaches zero at `since = 0.72`, well
    # inside the tail, so the last frame carries none of it.
    since = (t - EMERGE_BURST) / (1.0 - EMERGE_BURST)
    fade = max(0.0, 1.0 - since / 0.72)
    if fade > 0.0:
        prism.ellipse(cx, cy, radius * (0.5 + fade * 0.9), radius * (0.4 + fade * 0.8),
                      2.1 * fade * fade, CORE)
        for delay, span, weight in ((0.0, 0.55, 1.0), (0.15, 0.78, 0.6)):
            wave = (since - delay) / span
            if not 0.0 < wave < 1.0:
                continue
            spread = ease_out(wave)
            prism.ellipse(cx, floor_y, radius * (0.3 + spread * 1.15),
                          radius * (0.07 + spread * 0.22),
                          (1.0 - wave) * 1.45 * weight, CYAN, hollow=0.5)
        for i in range(20):
            if hash01(i, 11, 307) < 0.28:
                continue
            angle = hash01(i, 12, 59) * math.tau
            travel = since * radius * (0.9 + hash01(i, 13, 151) * 1.5)
            prism.add(int(round(cx + math.cos(angle) * travel)),
                      int(round(cy + math.sin(angle) * travel * 0.9)),
                      max(0.0, 1.0 - since * 1.5),
                      CELL_TABLE[i % len(CELL_TABLE)][4])
    prism.paint(img)
    return img


# --- build -------------------------------------------------------------------


def _seam(one_shot: Image.Image, loop: Image.Image) -> int:
    """Worst channel difference between a one-shot's last frame and its loop's
    first. Anything but 0 is a visible pop on the handover."""
    a, b = one_shot.convert("RGBA").tobytes(), loop.convert("RGBA").tobytes()
    return max((abs(p - q) for p, q in zip(a, b)), default=0)


def _layout(plot: int) -> dict:
    """Where the pieces stand, in TILE offsets from the plot's top-left.

    Same coordinate language as `scenery.Piece`: a standing piece's `dy` is the
    BOTTOM EDGE of the tile row it stands on (its contact point), a decal's is
    its centre. Shipping the arrangement with the art is what makes this a
    structure rather than seven loose sheets — whoever wires it up should not
    have to re-derive where a corner is.
    """
    # ONE TILE IN FROM THE CORNERS. At the corners the stones were three tiles
    # from an anomaly a tile and a half wide, and the gap read as four lamp
    # posts standing near a sphere rather than as one structure holding it. In
    # here the ring closes to the point where the rift's own spines reach the
    # stones, which is the picture: they are what is holding it open.
    #
    # The PLOT does not shrink with them — it is the cleared ground and the
    # isolation footprint, and the room to fight in around the structure is
    # worth more than a tighter box.
    far, near = 2.0, plot - 1.0           # contact rows: back row, front row
    left, right = 1.5, plot - 1.5         # tile centres of the stone columns
    middle = plot / 2.0
    return {
        # One shape per corner, no flips — see PILLAR_SHAPES.
        "pillars": [
            {"dx": left, "dy": far, "shape": 0},
            {"dx": right, "dy": far, "shape": 1},
            {"dx": left, "dy": near, "shape": 2},
            {"dx": right, "dy": near, "shape": 3},
        ],
        # Flat, centred on the plot's middle.
        "scar": {"dx": middle, "dy": middle},
        # THE SAME POINT as the scar: the anomaly is anchored on its core and
        # sits IN the sigil, not above it.
        "anomaly": {"dx": middle, "dy": middle},
        # Front face, centred between the two near stones: you walk up to this
        # from the approach, not from inside the ring.
        "console": {"dx": middle, "dy": near},
        # The light the structure is on the map for. `kind` 2 is BEACON in
        # `server/app/scenery.py` — the value is the contract.
        "light": {"dx": middle, "dy": middle, "radiusTiles": 3.5, "kind": 2},
    }


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "rift"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- props ---------------------------------------------------------------
    pillar_w, pillar_h = tile, tile * 3
    pillar_strip: list[Image.Image] = []
    for shape in range(PILLAR_SHAPES):
        for state in range(PILLAR_STATES):
            pillar_strip.append(make_pillar(pillar_w, pillar_h, shape, awake=state == 1))
    pack(pillar_strip, pillar_w, pillar_h).save(out_dir / "pillar.png")

    # Wider than its tile and taller than a crate. It still claims one tile of
    # floor; the overhang is drawn, not walked into, exactly as a sign's board is.
    console_w, console_h = round(tile * 1.25), round(tile * 1.5)
    consoles = [make_console(console_w, console_h, armed) for armed in (False, True)]
    pack(consoles, console_w, console_h).save(out_dir / "console.png")

    # --- decal ---------------------------------------------------------------
    scar_size = tile * 4
    scars = [make_scar(scar_size, random.Random(args.seed + 31))]
    pack(scars, scar_size, scar_size).save(out_dir / "scar.png")

    # --- a pillar's light ----------------------------------------------------
    # Wider and taller than the stone itself: the crown throws a halo past the
    # capstone and the foot pool spreads below the contact line, and both need
    # rows to spread into. Anchored on the pillar's BASE, so drawing the effect
    # at `y - anchorY` lands its row 0 on the pillar's row 0 exactly.
    glow_w, glow_h = tile * 2, round(tile * 3.5)
    glow_anchor = pillar_h
    geo = PillarGeometry(pillar_h, 0)
    charge_frames = [
        make_charge_frame(glow_w, glow_h, glow_anchor, geo, i, CHARGE_FRAMES)
        for i in range(CHARGE_FRAMES)
    ]
    crown_frames = [
        make_crown_frame(glow_w, glow_h, glow_anchor, geo, i, CROWN_FRAMES)
        for i in range(CROWN_FRAMES)
    ]
    pack(charge_frames, glow_w, glow_h).save(out_dir / "charge.png")
    pack(crown_frames, glow_w, glow_h).save(out_dir / "crown.png")

    # --- the anomaly ---------------------------------------------------------
    rift_w, rift_h = tile * 4, tile * 5
    rift_anchor = rift_h - round(tile * 0.75)
    radius = tile * 1.55
    # THE ANOMALY IS ANCHORED ON ITS CORE, not on a ground contact, and it is
    # the only sheet here that is. Everything else in this game registers where
    # it touches the floor because everything else touches the floor; this one
    # HOVERS, so the meaningful point is the centre of the sphere. Anchoring it
    # on the row its ground bloom sits in would hang the ball a sphere-radius
    # above the sigil it is supposed to be sitting in the middle of — which is
    # exactly what it did. The bloom is still drawn, further down the frame,
    # and lands on the near rim of the ring.
    rift_core = round(_hover_y(rift_anchor, radius))
    emerge_frames = [
        make_emerge_frame(rift_w, rift_h, rift_anchor, radius, i, EMERGE_FRAMES)
        for i in range(EMERGE_FRAMES)
    ]
    rift_frames = [
        make_rift_frame(rift_w, rift_h, rift_anchor, radius, i, RIFT_FRAMES)
        for i in range(RIFT_FRAMES)
    ]
    pack(emerge_frames, rift_w, rift_h).save(out_dir / "emerge.png")
    pack(rift_frames, rift_w, rift_h).save(out_dir / "rift.png")

    charge_seam = _seam(charge_frames[-1], crown_frames[0])
    emerge_seam = _seam(emerge_frames[-1], rift_frames[0])

    manifest = {
        "tile": tile,
        "seed": args.seed,
        "plot": {"widthTiles": PLOT_TILES, "heightTiles": PLOT_TILES},
        # STANDING: bottom-anchored, depth-sorted with the party, baked colour.
        # `states` says the frames are STATES the structure is switched between,
        # not variants to roll — the frame index is authoritative, never random.
        "props": {
            "pillar": {
                "file": "pillar.png",
                "frameWidth": pillar_w,
                "frameHeight": pillar_h,
                "frames": len(pillar_strip),
                "sway": 0,
                "shapes": PILLAR_SHAPES,
                "states": PILLAR_STATES,
            },
            "console": {
                "file": "console.png",
                "frameWidth": console_w,
                "frameHeight": console_h,
                "frames": len(consoles),
                "sway": 0,
                "states": CONSOLE_STATES,
            },
        },
        # FLAT: baked into the client's ground canvas, centred on its point.
        "decals": {
            "scar": {
                "file": "scar.png",
                "frameWidth": scar_size,
                "frameHeight": scar_size,
                "frames": len(scars),
            },
        },
        # GREYSCALE, additive, after the darkness pass, tinted `--scene-beacon`.
        #
        # `handsOffTo` names the loop a one-shot ends on: the last frame of the
        # timeline IS that loop's frame 0, so a caller swapping sheets on the
        # last frame sees nothing happen.
        #
        # `crownAt` and `burstAt` are the frames the PROP UNDERNEATH changes
        # state on, as well as where a sound would put its impact. The stone
        # goes dormant -> awake on `crownAt` and the console goes idle -> armed
        # with it, because that is the frame the sheet whites the capstone out
        # — the flash is what hides the swap. Flipping the sprite a frame early
        # or late is a visible cut from one stone to a different one.
        "effects": {
            "charge": {
                "file": "charge.png",
                "frameWidth": glow_w,
                "frameHeight": glow_h,
                "frames": CHARGE_FRAMES,
                "fps": CHARGE_FPS,
                "anchorY": glow_anchor,
                "loop": False,
                "crownAt": CHARGE_CROWN,
                "handsOffTo": "crown",
                # Baked prismatic, like the anomaly: the stones burn the
                # rift's light, and one draw-time tint cannot be four hues.
                "tinted": False,
            },
            "crown": {
                "file": "crown.png",
                "frameWidth": glow_w,
                "frameHeight": glow_h,
                "frames": CROWN_FRAMES,
                "fps": CROWN_FPS,
                "anchorY": glow_anchor,
                "loop": True,
                "tinted": False,
            },
            "emerge": {
                "file": "emerge.png",
                "frameWidth": rift_w,
                "frameHeight": rift_h,
                "frames": EMERGE_FRAMES,
                "fps": EMERGE_FPS,
                "anchorY": rift_core,
                "loop": False,
                "burstAt": EMERGE_BURST,
                "handsOffTo": "rift",
                # IRIDESCENT and baked. Draw it additively with NO tint —
                # multiplying a colour onto this would collapse six hues to one.
                "tinted": False,
            },
            "rift": {
                "file": "rift.png",
                "frameWidth": rift_w,
                "frameHeight": rift_h,
                "frames": RIFT_FRAMES,
                "fps": RIFT_FPS,
                "anchorY": rift_core,
                "loop": True,
                "tinted": False,
            },
        },
        "layout": _layout(PLOT_TILES),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: "
        f"scar 1x{scar_size}x{scar_size}, "
        f"pillar {PILLAR_SHAPES}x{PILLAR_STATES}x{pillar_w}x{pillar_h}, "
        f"console {CONSOLE_STATES}x{console_w}x{console_h}, "
        f"charge {CHARGE_FRAMES}x{glow_w}x{glow_h} @{CHARGE_FPS}fps, "
        f"crown {CROWN_FRAMES}x{glow_w}x{glow_h} @{CROWN_FPS}fps loop, "
        f"emerge {EMERGE_FRAMES}x{rift_w}x{rift_h} @{EMERGE_FPS}fps, "
        f"rift {RIFT_FRAMES}x{rift_w}x{rift_h} @{RIFT_FPS}fps loop, "
        f"anchors {glow_anchor}/{rift_core} (core, not contact), "
        f"seams charge->crown {charge_seam}, emerge->rift {emerge_seam}"
    )
    if charge_seam or emerge_seam:
        raise SystemExit(
            f"handoff is not seamless (charge->crown {charge_seam}, "
            f"emerge->rift {emerge_seam}): a one-shot's last frame must BE its "
            f"loop's frame 0, or the effect pops when the client swaps sheets"
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
