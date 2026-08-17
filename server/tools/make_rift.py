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

#: The ground the blast drained, and what it cracked it into.
#:
#: NEUTRAL AND DARK on purpose. These do most of the work in a corrupted tile;
#: the prism only shows up in crystal and along a crack's lip. Make these
#: colourful and the field becomes neon — the strangeness has to come from the
#: ground being WRONG, not from it being bright.
CORRUPT_DARK = rgb("#181a22")
CORRUPT_FISSURE = rgb("#0a0b10")
CORRUPT_GRIT = rgb("#3c3f4c")

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


#: THE OVERFEED TIERS, as a remap of the resolved hue index.
#:
#: A pad's quota is a floor, not a ceiling (`server/app/rift.py`), and what a
#: party keeps pouring into an anomaly past that has to be VISIBLE from across
#: the clearing — that is the whole payoff for choosing to overpay. So each tier
#: is the same lattice in a different key, walked steadily WARMER: the authored
#: violet-and-cyan is a thing that does not belong here, and by tier three it is
#: gorged, amber and near-white, which is the one direction that reads as
#: "full" rather than as "different".
#:
#: CORE stays CORE at every tier. It is the white a crossing goes when two
#: openings sum past the end of their ramp, and re-tinting it would take the
#: hot spots out of the lattice and flatten the sphere into a painted ball.
LEVEL_HUES: tuple[tuple[int, ...], ...] = (
    (ROSE, VIOLET, CYAN, MINT, AMBER, CORE),
    (VIOLET, CYAN, MINT, MINT, AMBER, CORE),
    (CYAN, MINT, MINT, AMBER, AMBER, CORE),
    (MINT, AMBER, AMBER, AMBER, CORE, CORE),
)
RIFT_LEVELS = len(LEVEL_HUES)


def level_hues(level: int) -> tuple[int, ...]:
    return LEVEL_HUES[max(0, min(RIFT_LEVELS - 1, level))]


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
        hues: tuple[int, ...] | None = None,
    ) -> None:
        """Resolve the field onto `image`.

        `hues` remaps the RESOLVED hue index, which is what an overfeed tier
        is. Remapping the input hues instead would change how shapes blend
        with each other — two cells crossing would land somewhere different —
        and the whole lattice would come out a different SHAPE per tier rather
        than the same shape in a different colour. See `LEVEL_HUES`.
        """
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
                index = 0 if index < 0 else top if index > top else index
                ramp = PRISM[hues[index] if hues else index]
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

#: Idle, armed, READY, spent. Four, and each one is a different sentence the
#: button is saying:
#:
#:   idle   nothing has happened here. Press me.
#:   armed  the anomaly is open and hungry. Feed me.
#:   READY  the quota is paid. The plunger is GOLD, and pressing now shuts the
#:          rift rather than feeding it — a different verb needs a different
#:          sprite, or the one press in the game that ends an extraction looks
#:          identical to the press before it.
#:   spent  the plunger still driven home with every lamp on it dead. A used
#:          console must not look pressable.
CONSOLE_STATES = 4
CONSOLE_IDLE, CONSOLE_ARMED, CONSOLE_READY, CONSOLE_SPENT = range(CONSOLE_STATES)

#: What the anomaly leaves on the ground when it goes off. Six cuts of the same
#: material, scattered by the blast — see `make_residue`.
RESIDUE_VARIANTS = 6

# --- the ground the blast went through ---------------------------------------
#
# THE GROUND IS A TEXTURE, NOT A TINT, AND IT IS AIMED.
#
# The first version washed each affected tile with a colour picked by hash. It
# was cheap and wrong twice over: a flat fill has no detail, so at any zoom it
# reads as a coloured rectangle — and picking the hue per tile made the field a
# patchwork of unrelated colours, neon confetti rather than a place something
# happened to.
#
# So it is drawn: cracks, dark stains, grit and a little crystal, on ground that
# has been DRAINED rather than dyed. The prism appears only in the crystal and
# along one lip of each crack, which is what makes it read as strange instead of
# decorated — the eye finds the colour by looking rather than having it thrown.
#
# And every mark is ORIENTED. The blast came out of one point and dragged
# everything outward, so each tile is cut for the direction it sits in relative
# to that point, the same way `tracks.png` is cut per compass heading. Marks are
# kept SHORT: a streak spanning the tile would have to line up with its
# neighbour's and at these angles never can. Short dashes all leaning one way
# give the radial read with nothing to misalign.
CORRUPT_DIRECTIONS = 8
#: Near the centre, mid, and the fringe. Distance picks it.
CORRUPT_LEVELS = 3
#: EIGHT cuts of each, and it needs every one.
#:
#: At two, a 68-tile field alternated between the same pair inside each of the
#: eight sectors and the whole thing came out as a lattice of identical stamps
#: — the single most obvious way to give away that a texture is tiled. Eight
#: rolls times three levels is enough that the eye stops finding the period.
CORRUPT_ROLLS = 8


def corrupt_frame(direction: int, level: int, roll: int) -> int:
    """Index into the corrupt sheet. Mirrored by `layers/corruption.ts`."""
    return ((direction * CORRUPT_LEVELS) + level) * CORRUPT_ROLLS + roll

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
# knob for it. Four seconds: menace comes from something big moving slowly, and
# a fast rotation makes a 64px object look small and light.
#
# THE FRAME RATE MATCHES `emerge`, and the frame count carries the period. At 8
# fps the idle was strobing round in visible steps while the burst that handed
# over to it was smooth, so the effect got WORSE at the moment it settled. Both
# sheets now run at 16 fps and the period is bought with frames instead — 5.6
# degrees a step, and the whole sequence moves at one rate.
RIFT_FRAMES = 64
RIFT_FPS = 16

# The rift going out. ONE-SHOT, and it is the one sheet in this file that ends
# on NOTHING rather than handing over to a loop.
#
# It is in three acts and the order matters. First the lattice loses its
# composure — it was always unstable, and now the lurches come one on top of
# another and it starts tearing light out of itself. Then it PULLS IN: the
# shell contracts and everything it was holding gets brighter as it goes,
# because the light is not leaving, it is being concentrated. Then it is a
# point, and then it is not there. A fade would have said "switched off"; this
# says the hole in the world closed, which is what actually happened.
#
# `frames / fps` is mirrored by `COLLAPSE_TIME` in server/app/rift.py.
COLLAPSE_FRAMES = 28
COLLAPSE_FPS = 16
#: Where the unrest peaks and the contraction takes over.
COLLAPSE_TEAR = 0.34
#: By here the shell is a point. What is left is the last spark going out.
COLLAPSE_PINCH = 0.86

# The console's aura once its pad's quota is paid. LOOPING.
#
# There is no other way to say "this button does something different now" from
# outside a tooltip's range. The console's own sprite goes gold, which is worth
# nothing at all until you are standing at it — so the pad also starts throwing
# a band of the anomaly's own colours off the console, slowly, on a full rainbow
# turn. It is the one effect in the game whose hue is a function of POSITION
# rather than of what threw it, and it looks like nothing else on the map for
# exactly that reason.
AURA_FRAMES = 16
AURA_FPS = 12
#: Motes in the band. Enough that it reads as continuous colour at 12 fps.
AURA_MOTES = 22
#: Specks rising off it, so the band is a thing shedding light rather than a
#: painted ellipse.
AURA_SPARKS = 9

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


def make_console(width: int, height: int, state: int) -> Image.Image:
    """The button. Idle, slammed, paid, dead.

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
    # `armed` is "the plunger is down", `live` is "there is light in it". Spent
    # is the one state where those disagree, and keeping them as two questions
    # rather than one is what lets the sprite say USED instead of unpressed.
    armed = state != CONSOLE_IDLE
    live = state in (CONSOLE_ARMED, CONSOLE_READY)
    # PAID swaps the fitting's hues to the warm end of the prism and nothing
    # else. Same lectern, same plunger, same pips — only the light in them
    # changes, so it reads as this console having changed its mind rather than
    # as a different object standing in the same place.
    paid = state == CONSOLE_READY
    core_hue = CORE
    hot_hue = AMBER if paid else CYAN
    ring_hue = AMBER if paid else VIOLET
    pip_hue = AMBER if paid else MINT

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
                if live:
                    px[x, y] = lit(
                        core_hue if d < 0.45 else hot_hue,
                        (0.62 if paid else 0.55) + (1.0 - d) * 0.45,
                    )
                else:
                    # A DOME, lit from the upper left like everything else in
                    # the game. A flat disc reads as a hole, and a hole is the
                    # one thing a button must not look like. Spent gets the same
                    # metal, just sunk — the shape says pressed, the dark socket
                    # around it says there is nothing left to press it for.
                    px[x, y] = pick(IRON, clamp01(
                        0.86 - d * 0.16 - (x - cx) / 3.4 * 0.24
                        - (y - plunger_y) / 2.8 * 0.28
                    ), x, y)
            elif d <= 1.36:
                px[x, y] = lit(ring_hue, 0.70 if paid else 0.62) if live else SOCKET

    # Two pips flanking the plunger. Nothing says "console" at 20 pixels like a
    # pair of indicator lamps that are dead until they are not.
    for side in (-1, 1):
        for oy in range(2):
            x, y = int(round(cx + side * 6.0)), int(round(plunger_y - 0.5 + oy))
            if (x, y) in body:
                px[x, y] = lit(pip_hue, 0.86 if paid else 0.78) if live else SOCKET

    if not armed:
        # A shadow under a raised button. Without it the plunger is a sticker.
        for x in range(width):
            y = int(plunger_y + 3)
            if (x, y) in body and abs(x - cx) < 3.2:
                px[x, y] = IRON[0]
    elif live:
        # Spill along the fold, where the live face meets its own lip. Painted
        # only on pixels the body actually owns — a highlight drawn one row
        # above the silhouette is a line floating in the air.
        for x in range(width):
            if (x, face_top) in body and abs(x - cx) < 3.4:
                px[x, face_top] = lit(hot_hue, 0.88 if paid else 0.82)
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


class GroundDecal:
    """A ground mark split into what it DARKENS and what it ADDS.

    THE BLEND IS THE WHOLE REASON THIS CLASS EXISTS. Drawn the obvious way —
    one sheet, `source-over` — a ground decal sits ON the floor: its dark
    pixels replace the soil instead of staining it, so the ground's own grain
    and colour die under every mark and the field reads as stickers laid on
    dirt. That is the single biggest thing separating "painted on top" from
    "happened to".
    So each mark goes to one of two images by its VALUE, and the client draws
    them with two different blend modes:

      dark   `multiply` — soil that was drained, scorched, cracked. Multiplying
             keeps every bit of the terrain texture underneath and only takes
             light out of it, which is what damage actually does to ground.
      lit    `lighter` — crystal, the caught lip of a fissure, a hot speck.
             These are LIGHT, so they add. Additive over a dark forest floor is
             also the only way a two-pixel glint survives being composited.

    Splitting by value rather than by call site means the author does not have
    to remember which layer anything belongs to: a colour resolved out of the
    bottom of a ramp is damage, one out of the top is light.
    """

    #: Ramp value at or above which a mark counts as light rather than damage.
    LIT_AT = 0.55

    def __init__(self, size: int) -> None:
        self.size = size
        self.dark = Image.new("RGBA", (size, size), TRANSPARENT)
        self.lit = Image.new("RGBA", (size, size), TRANSPARENT)
        self._dark = self.dark.load()
        self._lit = self.lit.load()

    def mark(self, x: int, y: int, colour: RGBA, alpha: float) -> None:
        """A neutral, non-luminous mark. Always damage."""
        self._put(self._dark, x, y, colour, alpha)

    def stain(self, x: int, y: int, hue: int, value: float, alpha: float) -> None:
        """A prism mark. Its ramp step decides which layer it lands on."""
        colour = PRISM[hue][int(clamp01(value) * (len(PRISM) - 1) + 0.5)]
        target = self._lit if value >= self.LIT_AT else self._dark
        self._put(target, x, y, colour, alpha)

    def _put(self, px, x: int, y: int, colour: RGBA, alpha: float) -> None:
        if not (0 <= x < self.size and 0 <= y < self.size):
            return
        prior = px[x, y][3]
        px[x, y] = (colour[0], colour[1], colour[2], max(prior, int(clamp01(alpha) * 255)))


def make_residue(size: int, variant: int, rng: random.Random) -> GroundDecal:
    """What the anomaly leaves on the ground when it goes off.

    A DECAL, and it follows the decal rules exactly: flat, no outline, no
    implied face, partly transparent so the soil's own grain reads through. It
    is a stain, not an object standing at ankle height.

    THIS IS THE SAME MATERIAL AS THE ANOMALY, DEAD. Same prism, same lozenge
    cells, same needles — but resolved out of the ramps' BOTTOM half instead of
    their top, because the light has gone out of it. Painting these bright
    would make the aftermath more eye-catching than the event, and the whole
    job of this art is to be found LATER: you walk back through a clearing days
    afterward and the ground tells you something happened here.
    A handful of pixels per mark keep a high step, and they are the ones that
    catch a lantern — so the residue is nearly invisible in the dark and
    unmistakable when you light it.

    Six cuts, thrown by one blast: dense knots near the middle, bare flecks at
    the edge. `_residue_variant` is what the scatter picks by distance, so a
    field of these reads as one event fading outward and not as confetti.
    """
    decal = GroundDecal(size)
    stain = decal.stain
    centre = (size - 1) / 2.0

    # (cells, cell radius, needles, speckle, bleach)
    cells, cell_r, needles, speckle, bleach = (
        (0, 0.0, 0, 30, 0.00),   # flecks — the outermost thing the wave leaves
        (5, 2.6, 2, 20, 0.18),   # cells — crystallised openings, fused flat
        (1, 1.6, 4, 22, 0.10),   # needles — spines that came down and stuck
        (2, 2.1, 1, 24, 0.85),   # bleach — ground the light scoured
        (2, 3.6, 3, 18, 0.55),   # knot — one big cell, the densest cut
        (0, 0.0, 0, 14, 0.00),   # dust — the last thing before nothing
    )[variant % RESIDUE_VARIANTS]

    if bleach > 0.0:
        # Scoured ground: a pale patch with nothing in it. Drawn first so the
        # crystal sits ON the burn rather than beside it.
        br = size * (0.26 + bleach * 0.16)
        for y in range(size):
            for x in range(size):
                d = math.hypot(x - centre, y - centre) / br
                if d > 1.0:
                    continue
                edge = (1.0 - d) ** 1.4
                stain(x, y, VIOLET, 0.10 + edge * 0.30,
                      bleach * edge * (0.55 + hash01(x, y, 811) * 0.35))

    for i in range(cells):
        hue = (MINT, CYAN, ROSE, AMBER, VIOLET)[rng.randrange(5)]
        cx = centre + rng.uniform(-1, 1) * size * 0.26
        cy = centre + rng.uniform(-1, 1) * size * 0.26
        angle = rng.uniform(0, math.tau)
        ca, sa = math.cos(angle), math.sin(angle)
        long_r = cell_r * rng.uniform(1.1, 1.9)
        for y in range(int(cy - long_r) - 1, int(cy + long_r) + 2):
            for x in range(int(cx - long_r) - 1, int(cx + long_r) + 2):
                dx, dy = x - cx, y - cy
                d = math.hypot((dx * ca + dy * sa) / long_r, (-dx * sa + dy * ca) / cell_r)
                if d > 1.0:
                    continue
                # A dead cell is a RIM with a hollow middle: the light that was
                # pouring out of it is the part that left. Filled ones read as
                # gems dropped on the floor.
                rim = max(0.0, 1.0 - abs(d - 0.74) / 0.52)
                grain = hash01(x, y, variant * 53 + 7) * 0.24
                stain(x, y, hue, 0.20 + rim * 0.58 + grain, 0.42 + rim * 0.45)

    for i in range(needles):
        angle = rng.uniform(0, math.tau)
        length = size * rng.uniform(0.16, 0.34)
        ox = centre + rng.uniform(-1, 1) * size * 0.2
        oy = centre + rng.uniform(-1, 1) * size * 0.2
        steps = max(2, int(length * 1.6))
        hue = (CYAN, VIOLET)[i % 2]
        for step in range(steps + 1):
            t = step / steps
            stain(int(round(ox + math.cos(angle) * length * t)),
                  int(round(oy + math.sin(angle) * length * t)),
                  hue, 0.68 - t * 0.34, 0.80 - t * 0.30)

    for _ in range(speckle):
        angle = rng.uniform(0, math.tau)
        radius = rng.uniform(0.0, size * 0.46)
        hue = (MINT, CYAN, ROSE, AMBER, VIOLET, CORE)[rng.randrange(6)]
        # One in six specks keeps a high step. Those are what a lantern finds.
        hot = rng.random() < 0.24
        stain(int(round(centre + math.cos(angle) * radius)),
              int(round(centre + math.sin(angle) * radius)),
              hue, 0.86 if hot else rng.uniform(0.26, 0.54),
              rng.uniform(0.66, 0.95) if hot else rng.uniform(0.34, 0.62))
    return decal


def make_corrupt(size: int, direction: int, level: int, rng: random.Random) -> GroundDecal:
    """One tile of ground the shock front went through, aimed outward.

    A DECAL: flat, no outline, partly transparent, so the soil underneath still
    reads through as soil. The job is to CHANGE that soil, not to replace it.

    The dominant note is dark. Ground the anomaly passed over is drained —
    scorched, cracked, gone grey-violet — and the iridescence survives only as
    crystal that grew in the fissures. Prism across the whole tile made a neon
    floor; prism in a dozen pixels and damage in the rest makes a floor that
    something happened to.
    """
    decal = GroundDecal(size)
    mark, stain = decal.mark, decal.stain

    # Outward, in the sheet's own frame — same convention as `tracks.png`:
    # angle 0 is +y (down the screen), so a heading of (dx, dy) is atan2(dx, dy).
    angle = direction / CORRUPT_DIRECTIONS * math.tau
    ux, uy = math.sin(angle), math.cos(angle)
    # Across the flow: the lip on a crack, and the spread of grit.
    ax, ay = -uy, ux

    heavy = (1.0, 0.62, 0.30)[level]

    # --- the drained ground --------------------------------------------------
    # Blotches, never a fill. Uniform darkening is a rectangle; irregular
    # patches stretched ALONG the flow are ground that was dragged over.
    for _ in range(int(4 + heavy * 7)):
        cx = rng.uniform(0, size)
        cy = rng.uniform(0, size)
        long_r = rng.uniform(2.0, 5.0) * (0.6 + heavy * 0.7)
        thin_r = long_r * rng.uniform(0.35, 0.6)
        for y in range(int(cy - long_r) - 1, int(cy + long_r) + 2):
            for x in range(int(cx - long_r) - 1, int(cx + long_r) + 2):
                dx, dy = x - cx, y - cy
                d = math.hypot((dx * ux + dy * uy) / long_r, (dx * ax + dy * ay) / thin_r)
                if d > 1.0:
                    continue
                mark(x, y, CORRUPT_DARK, heavy * (1.0 - d) ** 0.7 * rng.uniform(0.34, 0.62))

    # --- cracks --------------------------------------------------------------
    # They RUN OUTWARD, the way a shock front splits ground. One lip catches
    # the light; the fissure itself is the darkest thing in the tile.
    for _ in range(int(1 + heavy * 2.4)):
        x = rng.uniform(0, size)
        y = rng.uniform(0, size)
        length = rng.uniform(4.0, 9.0) * (0.5 + heavy * 0.8)
        wander = rng.uniform(-0.35, 0.35)
        hue = (CYAN, VIOLET, MINT)[rng.randrange(3)]
        steps = int(length)
        for step in range(steps + 1):
            t = step / max(steps, 1)
            lean = math.sin(t * 4.0 + wander * 6.0) * wander * 2.2
            cx = int(round(x + ux * length * t + ax * lean))
            cy = int(round(y + uy * length * t + ay * lean))
            mark(cx, cy, CORRUPT_FISSURE, 0.55 + heavy * 0.35)
            # The lit lip, one pixel to one side and only sometimes: a crack
            # outlined down its whole length reads as a drawn line.
            if rng.random() < 0.45:
                stain(cx + int(round(ax)), cy + int(round(ay)),
                      hue, 0.44, (0.22 + heavy * 0.26) * (1.0 - t * 0.5))

    # --- crystal -------------------------------------------------------------
    # The only bright thing here, and there is almost none of it. Angular, and
    # stretched along the flow, so it reads as something that grew in the
    # direction the blast was travelling.
    for _ in range(int(heavy * 1.7)):
        cx = rng.uniform(2, size - 2)
        cy = rng.uniform(2, size - 2)
        long_r = rng.uniform(1.2, 2.6)
        hue = (MINT, CYAN, ROSE, AMBER, VIOLET)[rng.randrange(5)]
        for y in range(int(cy - long_r) - 1, int(cy + long_r) + 2):
            for x in range(int(cx - long_r) - 1, int(cx + long_r) + 2):
                dx, dy = x - cx, y - cy
                along = (dx * ux + dy * uy) / long_r
                across = (dx * ax + dy * ay) / (long_r * 0.42)
                # A DIAMOND, not a disc: |a| + |b| is what makes a facet.
                edge = abs(along) + abs(across)
                if edge > 1.0:
                    continue
                stain(x, y, hue, 0.42 + (1.0 - edge) * 0.5, 0.5 + (1.0 - edge) * 0.42)

    # --- grit ----------------------------------------------------------------
    # Thrown outward and settled. Biased down-flow so the tile has a tail, but
    # scattered from a ROLLED origin rather than from the tile's middle: fixed
    # to the centre, every tile grew the same little rosette and the field came
    # out as a grid of identical dots.
    for _ in range(int(3 + heavy * 9)):
        ox = rng.uniform(0, size)
        oy = rng.uniform(0, size)
        along = rng.uniform(-0.3, 1.0)
        across = rng.uniform(-0.5, 0.5)
        x = int(round(ox + ux * along * size * 0.35 + ax * across * size * 0.5))
        y = int(round(oy + uy * along * size * 0.35 + ay * across * size * 0.5))
        # One speck in nine keeps its colour. More than that and the field
        # is confetti; the strangeness is in the damage, not the palette.
        if rng.random() < 0.11:
            stain(x, y, (MINT, CYAN, ROSE, AMBER)[rng.randrange(4)],
                  0.58, rng.uniform(0.35, 0.6))
        else:
            mark(x, y, CORRUPT_GRIT, rng.uniform(0.2, 0.45) * (0.5 + heavy * 0.6))
    return decal


def residue_variant(distance: float, span: float) -> int:
    """Which cut belongs at this distance from the blast, 0..1 of its reach.

    Mirrored by the client, which generates the scatter itself off the map seed
    (see `render/residue.ts`) — the marks are not on the wire, only the fact
    that the rift went off is. Keeping the CHOICE here means the falloff is
    authored with the art rather than guessed at the far end.
    """
    t = clamp01(distance / max(span, 1e-6))
    if t < 0.22:
        return 4  # knot
    if t < 0.42:
        return 1  # cells
    if t < 0.60:
        return 3  # bleach
    if t < 0.78:
        return 2  # needles
    if t < 0.92:
        return 0  # flecks
    return 5      # dust


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
    # vertical drift is what says the thing is HANGING there, unsupported.
    #
    # TWO harmonics, not one. A single sine is a metronome and reads as
    # mechanical — something on a piston. Adding the second at twice the rate
    # makes the rise and the fall different shapes, so it wanders instead of
    # oscillating. Both are still whole harmonics of the loop phase, so it
    # wraps, and both are exactly 0 at phase 0 — which is what keeps the
    # handoff out of `emerge` exact.
    bob = (math.sin(phase) * 0.72 + math.sin(phase * 2.0) * 0.28) * radius * 0.17
    cy += bob
    near = 1.0 - bob / max(radius * 0.17, 1e-6) * 0.18

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
    floor_y = cy - bob + ry
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
    width: int, height: int, contact_y: int, radius: float, index: int, total: int,
    level: int = 0,
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
    prism.paint(img, hues=level_hues(level))
    return img


def make_collapse_frame(
    width: int, height: int, contact_y: int, radius: float, index: int, total: int,
    level: int = 0,
) -> Image.Image:
    """One frame of the rift going out. ONE-SHOT, and it ends on an empty frame.

    Frame 0 IS `rift` frame 0 of the same tier, byte for byte, so the client
    can cut from the resting loop to this without a pop — the same contract
    `emerge` has with `rift`, run the other way. Everything this adds is scaled
    by a term that is exactly 0 at t=0, which is what makes that true by
    construction rather than by eyeballing it.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    t = index / max(total - 1, 1)
    if t >= 1.0:
        # Nothing left. The sheet has to END on empty or the last frame stays
        # on screen as a bright speck for as long as the caller holds it.
        return img

    prism = Prism(width, height)
    cx = (width - 1) / 2.0
    cy = _hover_y(contact_y, radius)

    # The lattice keeps TURNING into its own collapse, at the resting loop's
    # own angular rate. Freezing the spin here would make the sphere stop the
    # instant it started dying, and a thing that stops moving before it
    # disappears reads as a paused animation.
    step = math.tau * RIFT_FPS / (COLLAPSE_FPS * RIFT_FRAMES)
    phase = index * step
    spin, base_x, base_y, base_bright, instability = _rift_state(phase)

    unrest = ease_in(clamp01(t / COLLAPSE_TEAR))
    shrink = ease_in(clamp01((t - COLLAPSE_TEAR) / (COLLAPSE_PINCH - COLLAPSE_TEAR)))
    left = 1.0 - shrink

    # THE SHELL SWELLS BEFORE IT GOES IN. A thing that only ever contracts
    # reads as a zoom-out; the small overshoot first is what makes the pull
    # afterwards feel like a pull.
    shell = radius * (1.0 + 0.16 * unrest) * left
    stretch_x = base_x * (1.0 + 0.34 * unrest * math.sin(t * math.tau * 5.5))
    stretch_y = base_y * (1.0 - 0.26 * unrest * math.sin(t * math.tau * 4.0))
    # Brighter all the way down: the light is not draining out of it, it is
    # being squeezed into less and less room.
    bright = base_bright * (1.0 + 1.10 * unrest + 2.60 * shrink)
    shear = instability * 2.0 + 6.5 * unrest
    reach = 1.0 + 1.6 * unrest

    if shell > 0.6:
        _anomaly(
            prism, width, contact_y, cy, shell, spin,
            stretch_x, stretch_y, bright, shear, phase, reach, left,
        )

    # Tears: hairlines of raw CORE thrown off the shell while it is failing.
    # They come and go on their own clock so the failure stutters instead of
    # ramping, which is what `_rift_state` already says instability looks like.
    if unrest > 0.0:
        for i in range(14):
            flick = math.sin(t * math.tau * (3.0 + i * 0.7) + i * 2.1)
            if flick < 0.45:
                continue
            angle = hash01(i, 5, 71) * math.tau + spin * 0.4
            far = shell * (0.85 + hash01(i, 6, 131) * 0.9) + radius * 0.25 * unrest
            length = radius * 0.30 * unrest * flick
            for k in range(4):
                reach_k = far + length * (k / 3.0)
                prism.add(
                    int(round(cx + math.cos(angle) * reach_k)),
                    int(round(cy + math.sin(angle) * reach_k * 0.9)),
                    unrest * flick * (1.0 - k / 4.0) * 1.5,
                    CORE,
                )

    # NO SEPARATE FLOOR POOL HERE. `_anomaly` already casts one and scales it
    # by `opened`, which is `left` — so the light on the ground draws in with
    # the shell for free. A second ellipse on top of it was the one term in
    # this function that was not zero at t=0, and it put 199 levels of
    # difference into a seam that has to be exact.

    # The last spark, and a thin ring leaving the point it went out at. Only
    # inside the final act, so nothing here can reach frame 0.
    if shrink > 0.55:
        out = clamp01((shrink - 0.55) / 0.45)
        prism.ellipse(cx, cy, 1.4 + 2.2 * (1.0 - out), 1.4 + 2.2 * (1.0 - out),
                      3.2 * (1.0 - out) + 0.8, CORE)
        ring = ease_out(out)
        prism.ellipse(cx, cy, radius * (0.2 + ring * 1.5), radius * (0.18 + ring * 1.35),
                      1.7 * (1.0 - out) ** 2, VIOLET, hollow=0.72)

    prism.paint(img, hues=level_hues(level))
    return img


def make_aura_frame(width: int, height: int, anchor_y: int, index: int, total: int) -> Image.Image:
    """One frame of the paid console's rainbow band. LOOP.

    EVERY TERM IS A FUNCTION OF PHASE, so frame 0 and the last frame meet with
    nothing to hide — the same rule `crown` and `rift` are built on. The hue of
    a mote comes from WHERE IT IS on the band rather than from when it was
    spawned, which is what keeps the colours standing still while the band
    turns under them, instead of the whole ring strobing through the spectrum.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    prism = Prism(width, height)
    phase = (index / total) * math.tau
    cx = (width - 1) / 2.0
    # Around the console's head, not around its feet: the band belongs to the
    # part of the object the player is looking at.
    ring_y = anchor_y - height * 0.42
    rx = width * 0.40
    ry = height * 0.10
    top = len(PRISM) - 1

    for i in range(AURA_MOTES):
        around = i / AURA_MOTES * math.tau
        turned = around + phase
        x = cx + math.cos(turned) * rx
        y = ring_y + math.sin(turned) * ry
        # Front of the band is nearer the camera and brighter; the back half
        # stays faint, which is what makes a flat ellipse read as a ring around
        # something rather than as a painted oval.
        front = 0.42 + 0.58 * (0.5 + 0.5 * math.sin(turned))
        # Hue by ANGLE, so the spectrum is nailed to the world and the motes
        # slide through it.
        hue = (turned % math.tau) / math.tau * top
        prism.ellipse(x, y, 1.9 * front, 1.5 * front, 1.85 * front, hue)

    # Specks lifting off the band. `drift` wraps with the phase, so a speck
    # that runs out at the top is the same speck arriving at the bottom.
    for i in range(AURA_SPARKS):
        drift = ((phase / math.tau) + i / AURA_SPARKS) % 1.0
        around = i / AURA_SPARKS * math.tau + phase * 0.6
        x = cx + math.cos(around) * rx * 0.8
        y = ring_y - drift * height * 0.34
        fade = (1.0 - drift) * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(around)))
        prism.add(int(round(x)), int(round(y)), fade * 1.45,
                  (around % math.tau) / math.tau * top)

    # A soft pool on the ground so the band is lighting something. Kept a few
    # rows clear of the frame's bottom edge — an ellipse centred on the anchor
    # is cut in half by the frame and comes out as an arc, which reads as a
    # bowl the console is standing in rather than as light on dirt.
    prism.ellipse(cx, anchor_y - 4.0, rx * 0.92, ry * 0.85,
                  0.60 + 0.12 * math.sin(phase), AMBER)
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
    floor_y = cy + radius * rest_y

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


def _level_file(stem: str, level: int) -> str:
    """`rift.png`, `rift-1.png`, … — tier 0 keeps the plain name."""
    return f"{stem}.png" if level == 0 else f"{stem}-{level}.png"


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
    # ONE STONE, not four.
    #
    # A ring of four framed the anomaly symmetrically and, being symmetrical,
    # said nothing: it read as a fixture the rift had been installed into. A
    # single stone off to one side reads as a thing somebody DROVE INTO THE
    # GROUND next to a hole in the world, which is the story this structure is
    # actually telling. It also stops the pad being a diagram — you approach
    # from anywhere except the one corner that is already occupied.
    #
    # The sheet still carries four cuts. They are not dead: the shape is a field
    # on the placed stone, so this can be rolled per map, and four maps' worth
    # of extraction points do not all have the same rock in them.
    near = plot - 1.0                     # contact row of the front pieces
    left = 1.5                            # tile centre of the stone's column
    middle = plot / 2.0
    return {
        "pillars": [
            {"dx": left, "dy": near, "shape": 2},
        ],
        # Flat, centred on the plot's middle.
        "scar": {"dx": middle, "dy": middle},
        # THE SAME POINT as the scar: the anomaly is anchored on its core and
        # sits IN the sigil, not above it.
        "anomaly": {"dx": middle, "dy": middle},
        # Front face, centred between the two near stones and ON THEIR ROW.
        # It used to stand a tile further out, on the plot's own south edge —
        # close enough that a tree just outside the plot drew its CANOPY over
        # it, and a canopy is painted several tiles above its trunk. The one
        # piece the player has to walk up to and find was behind foliage.
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
    consoles = [make_console(console_w, console_h, state) for state in range(CONSOLE_STATES)]
    pack(consoles, console_w, console_h).save(out_dir / "console.png")

    # --- decal ---------------------------------------------------------------
    scar_size = tile * 4
    scars = [make_scar(scar_size, random.Random(args.seed + 31))]
    pack(scars, scar_size, scar_size).save(out_dir / "scar.png")

    # One tile square, like every other scatter decal in the game (`debris`,
    # `tracks`). The blast lays hundreds of these; anything bigger and the
    # falloff would be built out of visible tiles rather than out of density.
    # TWO SHEETS PER GROUND DECAL, one per blend mode — see `GroundDecal`. The
    # `-lit` half is what the client adds; the other half is what it multiplies.
    residue_size = tile
    rng = random.Random(args.seed + 43)
    residues = [make_residue(residue_size, v, rng) for v in range(RESIDUE_VARIANTS)]
    pack([d.dark for d in residues], residue_size, residue_size).save(out_dir / "residue.png")
    pack([d.lit for d in residues], residue_size, residue_size).save(out_dir / "residue-lit.png")

    # Packed direction-major, so `corrupt_frame` is one multiply-add and the
    # client can pick a tile from an angle without a lookup table.
    rng = random.Random(args.seed + 57)
    corrupts = [
        make_corrupt(tile, d, level, rng)
        for d in range(CORRUPT_DIRECTIONS)
        for level in range(CORRUPT_LEVELS)
        for _ in range(CORRUPT_ROLLS)
    ]
    pack([d.dark for d in corrupts], tile, tile).save(out_dir / "corrupt.png")
    pack([d.lit for d in corrupts], tile, tile).save(out_dir / "corrupt-lit.png")

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
    # THE ANOMALY IS ANCHORED ON ITS UNDERSIDE, not on a ground contact and not
    # on its centre.
    #
    # Everything else in this game registers where it touches the floor, because
    # everything else touches the floor. This one hovers over a ring cut into
    # the ground, and the picture is that the ring is a MOUTH: the sphere's
    # bottom sits in the middle of it and its top half stands clear above the
    # sigil's far edge. Anchoring on the centre buried half the ball below the
    # ring; anchoring on the bloom row hung it a whole radius too high.
    #
    # The pool is drawn on this same row, so the anchor, the underside and the
    # light on the floor are all one point.
    rift_core = round(_hover_y(rift_anchor, radius) + radius)
    emerge_frames = [
        make_emerge_frame(rift_w, rift_h, rift_anchor, radius, i, EMERGE_FRAMES)
        for i in range(EMERGE_FRAMES)
    ]
    # ONE SHEET PER OVERFEED TIER, and they are separate FILES rather than one
    # long strip. Four tiers of a 64-frame loop packed together is a bitmap
    # 16384 pixels wide, which is exactly the maximum dimension a good number
    # of GPUs will accept — a sheet that decodes on the author's machine and
    # comes out blank on somebody's laptop is the worst possible way to find
    # that out. `levelFiles` in the manifest is the index.
    rift_banks = [
        [
            make_rift_frame(rift_w, rift_h, rift_anchor, radius, i, RIFT_FRAMES, level)
            for i in range(RIFT_FRAMES)
        ]
        for level in range(RIFT_LEVELS)
    ]
    collapse_banks = [
        [
            make_collapse_frame(
                rift_w, rift_h, rift_anchor, radius, i, COLLAPSE_FRAMES, level
            )
            for i in range(COLLAPSE_FRAMES)
        ]
        for level in range(RIFT_LEVELS)
    ]
    rift_files = [_level_file("rift", level) for level in range(RIFT_LEVELS)]
    collapse_files = [_level_file("collapse", level) for level in range(RIFT_LEVELS)]
    pack(emerge_frames, rift_w, rift_h).save(out_dir / "emerge.png")
    for name, frames in zip(rift_files, rift_banks):
        pack(frames, rift_w, rift_h).save(out_dir / name)
    for name, frames in zip(collapse_files, collapse_banks):
        pack(frames, rift_w, rift_h).save(out_dir / name)

    # --- the paid console's band ---------------------------------------------
    aura_w, aura_h = tile * 2, round(tile * 2.5)
    aura_anchor = aura_h
    aura_frames = [
        make_aura_frame(aura_w, aura_h, aura_anchor, i, AURA_FRAMES)
        for i in range(AURA_FRAMES)
    ]
    pack(aura_frames, aura_w, aura_h).save(out_dir / "aura.png")

    charge_seam = _seam(charge_frames[-1], crown_frames[0])
    emerge_seam = _seam(emerge_frames[-1], rift_banks[0][0])
    # Every tier's collapse must start on that tier's resting frame 0, or the
    # anomaly changes colour and shape on the frame the party shuts it.
    collapse_seam = max(
        _seam(collapse_banks[level][0], rift_banks[level][0])
        for level in range(RIFT_LEVELS)
    )
    collapse_tail = max(
        (collapse_banks[level][-1].getchannel("A").getextrema()[1]
         for level in range(RIFT_LEVELS)),
        default=0,
    )

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
            # Thrown across the ground by the burst and never cleaned up. The
            # client generates WHERE they land itself, deterministically from
            # the map seed — see `render/residue.ts`. Only the fact that the
            # rift went off is on the wire.
            "residue": {
                "file": "residue.png",
                # Drawn `lighter`, over the multiplied half.
                "litFile": "residue-lit.png",
                "frameWidth": residue_size,
                "frameHeight": residue_size,
                "frames": len(residues),
            },
            # The ground the front went over. AIMED: the frame is picked by the
            # tile's direction from the blast, so every mark on the field leans
            # away from the centre — see `corrupt_frame`.
            "corrupt": {
                "file": "corrupt.png",
                "litFile": "corrupt-lit.png",
                "frameWidth": tile,
                "frameHeight": tile,
                "frames": len(corrupts),
                "directions": CORRUPT_DIRECTIONS,
                "levels": CORRUPT_LEVELS,
                "rolls": CORRUPT_ROLLS,
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
                "file": rift_files[0],
                # ONE FILE PER OVERFEED TIER. `levelFiles[level]` is the sheet
                # to draw; the frame index inside it is unchanged, so a pad
                # changing tier does not restart or rephase its loop — the
                # client swaps which bitmap it is reading and nothing else.
                "levels": RIFT_LEVELS,
                "levelFiles": rift_files,
                "frameWidth": rift_w,
                "frameHeight": rift_h,
                "frames": RIFT_FRAMES,
                "fps": RIFT_FPS,
                "anchorY": rift_core,
                "loop": True,
                "tinted": False,
            },
            # The vanish. Starts on `rift` frame 0 of the SAME tier and ends on
            # an empty frame — it hands off to nothing, which is the point.
            "collapse": {
                "file": collapse_files[0],
                "levels": RIFT_LEVELS,
                "levelFiles": collapse_files,
                "frameWidth": rift_w,
                "frameHeight": rift_h,
                "frames": COLLAPSE_FRAMES,
                "fps": COLLAPSE_FPS,
                "anchorY": rift_core,
                "loop": False,
                "tinted": False,
            },
            # Thrown off the CONSOLE, not off the anomaly, and anchored on the
            # console's contact rather than on the sphere's underside.
            "aura": {
                "file": "aura.png",
                "frameWidth": aura_w,
                "frameHeight": aura_h,
                "frames": AURA_FRAMES,
                "fps": AURA_FPS,
                "anchorY": aura_anchor,
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
        f"residue {RESIDUE_VARIANTS}x{residue_size}x{residue_size}, "
        f"corrupt {CORRUPT_DIRECTIONS}x{CORRUPT_LEVELS}x{CORRUPT_ROLLS}x{tile}x{tile}, "
        f"pillar {PILLAR_SHAPES}x{PILLAR_STATES}x{pillar_w}x{pillar_h}, "
        f"console {CONSOLE_STATES}x{console_w}x{console_h}, "
        f"charge {CHARGE_FRAMES}x{glow_w}x{glow_h} @{CHARGE_FPS}fps, "
        f"crown {CROWN_FRAMES}x{glow_w}x{glow_h} @{CROWN_FPS}fps loop, "
        f"emerge {EMERGE_FRAMES}x{rift_w}x{rift_h} @{EMERGE_FPS}fps, "
        f"rift {RIFT_LEVELS}x{RIFT_FRAMES}x{rift_w}x{rift_h} @{RIFT_FPS}fps loop, "
        f"collapse {RIFT_LEVELS}x{COLLAPSE_FRAMES}x{rift_w}x{rift_h} @{COLLAPSE_FPS}fps, "
        f"aura {AURA_FRAMES}x{aura_w}x{aura_h} @{AURA_FPS}fps loop, "
        f"anchors {glow_anchor}/{rift_core} (underside, not contact), "
        f"seams charge->crown {charge_seam}, emerge->rift {emerge_seam}, "
        f"rift->collapse {collapse_seam}, collapse tail alpha {collapse_tail}"
    )
    if charge_seam or emerge_seam or collapse_seam:
        raise SystemExit(
            f"handoff is not seamless (charge->crown {charge_seam}, "
            f"emerge->rift {emerge_seam}, rift->collapse {collapse_seam}): a "
            f"sheet that continues another must START on, or END as, that "
            f"sheet's own frame, or the effect pops when the client swaps"
        )
    if collapse_tail:
        raise SystemExit(
            f"collapse ends on {collapse_tail} alpha: the vanish hands off to "
            f"NOTHING, so its last frame has to be empty or a client holding "
            f"the final frame leaves a spark burning on a dead pad"
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
