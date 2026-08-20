#!/usr/bin/env python3
"""Asset pipeline: the things you OPEN, and the things somebody built.

A companion module to `make_scenery.py` rather than a second pipeline: it
draws sheets, `make_scenery.build()` packs them and writes them into the one
`assets/processed/scenery/` manifest the client already reads. Splitting the
drawing out keeps that file about the forest people abandoned and this one
about the objects they abandoned in it.

WHY THESE EXIST
The forest used to be scattered with one sheet called `crate`, and a crate is
an anonymous noun: five kinds of wood that all mean "smash me". What replaces
it is a vocabulary the player learns by walking:

    barrel      you BREAK it. Wood, steel or fuel. Might hold nothing.
    box         you OPEN it. The lid hinges back and the inside is visible.
    chest       you OPEN it, slower, and something is always in there.
    stash       small hand-sized containers -- a mailbox, a case, a freezer,
                a bin, a toolbox. Tiny loot, occasionally not tiny.
    vehicle     a car, a van, an ambulance, a cruiser, a lorry, a bus. The
                panel lifts and you look inside. Sometimes something looks back.
    statue      nobody opens these. They mark a place, and the place is what
                the loot is for.
    altar       the one thing at that place you do open.

THE ANIMATION CONTRACT is one of two shapes and the sheet says which:

    BREAK   frame 0 is the idle pose; the rest throws the silhouette apart and
            ends almost empty, so the client can hide the sprite without a pop.
    OPEN    frame 0 is closed; the rest swings a lid or a panel and STOPS on a
            held final pose. An opened thing is removed by the server, but the
            last frame has to be a legible open container or the removal reads
            as the object vanishing instead of being emptied.

Both are packed KIND-MAJOR -- kind 0's whole strip, then kind 1's -- and both
are deterministic: `hash01(x, y, salt)` per pixel, never `rng` per frame, or
the same object would come apart differently on two machines.

READ ORDER AT 16px is the same rule the rest of the art follows. VALUE and
SHAPE carry; hue never does. A vehicle is a dark mass under a pale roofline
with two black wheels; an altar is a light slab over a dark hollow; a totem is
a narrow column with three bright notches down it.
"""

from __future__ import annotations

import math
import random

from PIL import Image

from make_textures import (
    Ramp,
    TRANSPARENT,
    clamp01,
    hash01,
    outline,
    pick,
    rgb,
)

# --- palette ----------------------------------------------------------------
# Paint is the one material in the game that was CHOSEN, so the vehicle ramps
# are allowed a hue the forest never has. The MASS is still dark — a white
# ambulance at full value would be the brightest object on a night map and
# would read as lit rather than as painted — but every ramp now carries a real
# top step, because what makes a curved panel read is the distance between the
# edge the sky hits and the shadow under it, and a ramp spanning four
# near-identical greys has nowhere to put that distance. The night layer
# multiplies over all of this: what is authored here is the object in daylight,
# and the darkness decides how much of it survives.
#
# Six steps, and the two ends are doing different jobs from the middle. Step 0
# is the self-shadow an object throws on its own underside; the top step is the
# one edge with sky on it, spent one pixel at a time. The middle is the body.

PLANK: Ramp = [rgb(c) for c in ("#1b1710", "#2a2318", "#3a3123", "#4b3f2c", "#5e5039", "#786748")]
PLANK_DARK: Ramp = [rgb(c) for c in ("#0d0b07", "#151109", "#1e1810", "#2a2217", "#37301f")]
STEEL: Ramp = [rgb(c) for c in ("#141619", "#212429", "#2f343b", "#41474f", "#565d67", "#767e8a")]
RUST: Ramp = [rgb(c) for c in ("#241410", "#3a1e15", "#4f2a1c", "#683a23", "#82502e", "#9c6a3c")]
HAZARD: Ramp = [rgb(c) for c in ("#3a2a0c", "#5c4210", "#8a6417", "#b8871f", "#d9a62c")]
STONE: Ramp = [rgb(c) for c in ("#1c1b20", "#2a292f", "#3a383f", "#4b4851", "#5f5b66", "#77727f")]
#: The two stones the shrine was cut from. Six steps, and unlike the ramps
#: above them every step also shifts HUE — cool violet in the shadow, warm
#: ochre at the top (§11) — because a statue is lit almost entirely by the
#: difference between one plane and the next, and a ramp that only changes
#: value gives that difference nothing to say. Two families rather than one so
#: a ring of six is not one object repeated; they share their end steps, which
#: is what keeps them the same quarry.
SLATE: Ramp = [rgb(c) for c in ("#14131a", "#21212b", "#34333f", "#4a4753", "#665f68", "#857a72")]
TUFA: Ramp = [rgb(c) for c in ("#171319", "#262029", "#3b3239", "#574a4b", "#766661", "#96877a")]
GRANITE: Ramp = [rgb(c) for c in ("#17181b", "#232529", "#323439", "#43464d", "#565a63", "#6d727c")]
BONE: Ramp = [rgb(c) for c in ("#332f27", "#474337", "#5d584a", "#77705e", "#948c76", "#b3aa90")]
ROPE: Ramp = [rgb(c) for c in ("#2b2418", "#3a3120", "#4d4229", "#615334", "#786745")]
GLASS: Ramp = [rgb(c) for c in ("#0e1216", "#151d24", "#1f2c36", "#2c3f4b", "#3d5866", "#5b7f8e")]
TYRE: Ramp = [rgb(c) for c in ("#08090a", "#0f1012", "#16181b", "#1f2226", "#2b2f34")]
CHROME: Ramp = [rgb(c) for c in ("#23262b", "#383d44", "#525a64", "#6e7883", "#8f99a5", "#b3bcc7")]
BRASS: Ramp = [rgb(c) for c in ("#332208", "#523710", "#7a541b", "#a37628", "#c69a3c", "#e3bd5e")]
OCHRE: Ramp = [rgb(c) for c in ("#2c1d0d", "#402a13", "#573a1b", "#6f4c25", "#8b6231", "#a87b41")]
LEATHER: Ramp = [rgb(c) for c in ("#1a1310", "#251b16", "#33261d", "#443326", "#584434", "#6f5844")]
#: Wet growth on anything that has stood still in a forest for a year.
MOSS: Ramp = [rgb(c) for c in ("#161c14", "#1f281a", "#2b3722", "#3a482c", "#4c5c38")]

# Vehicle paint. Each is a body ramp, and they are pulled apart by HUE rather
# than by value: six dark masses that differ only in brightness are six of the
# same car at the far end of a lantern. The shape says vehicle, the roofline
# says which class, and the hue is what makes the ambulance you already opened
# recognisable from across a clearing from the one you have not.
PAINT_SEDAN: Ramp = [rgb(c) for c in ("#1a0e10", "#2c1518", "#411d1f", "#5a2a29", "#763c37", "#95564a")]
PAINT_VAN: Ramp = [rgb(c) for c in ("#12160f", "#1d2417", "#2b3520", "#3c482b", "#505e38", "#6b7a4b")]
PAINT_AMBU: Ramp = [rgb(c) for c in ("#1b1e20", "#2b3033", "#3f4649", "#565e62", "#6f787c", "#8d979a")]
PAINT_POLICE: Ramp = [rgb(c) for c in ("#0b0c0f", "#141619", "#1f2228", "#2c3038", "#3d434c", "#525a66")]
PAINT_TRUCK: Ramp = [rgb(c) for c in ("#1d1310", "#2e1e16", "#412b1d", "#573a26", "#6f4d31", "#8a6440")]
PAINT_BUS: Ramp = [rgb(c) for c in ("#241a09", "#38290e", "#503b15", "#6b511f", "#87682a", "#a4833a")]

# Signal colours. Used in single pixels only -- a red cross, a light bar, the
# ember inside an opened chest. Anything larger and the map stops being dark.
RED: Ramp = [rgb(c) for c in ("#3a0d0c", "#5e1512", "#8a1f19", "#b52c22", "#d8462f")]
BLUE: Ramp = [rgb(c) for c in ("#0d1a3a", "#153060", "#1f4a8a", "#2c6ab5", "#4a8fd8")]
EMBER: Ramp = [rgb(c) for c in ("#3a2410", "#6a4018", "#a06820", "#d4a040", "#f2c14b", "#ffe08a")]
COLD: Ramp = [rgb(c) for c in ("#16232b", "#1f3644", "#2c505f", "#3d707f", "#5a97a4")]

OUTLINE_WOOD = rgb("#0c0a07")
OUTLINE_COLD = rgb("#08090b")
OUTLINE_STONE = rgb("#0a0a0d")

# --- animation shape --------------------------------------------------------
# One number per sheet, and the client reads them off the manifest. Break is
# faster than open on purpose: wood giving way is an instant, a lid coming up
# is a moment, and a chest is the slowest thing in the game to open because
# the wait is what makes the pop at the end worth watching.

BARREL_KINDS = 3
BARREL_FRAMES = 8
BARREL_FPS = 13

BOX_KINDS = 3
BOX_FRAMES = 6
BOX_FPS = 14

CHEST_KINDS = 2
CHEST_FRAMES = 8
CHEST_FPS = 11

STASH_KINDS = 5
STASH_FRAMES = 6
STASH_FPS = 14

VEHICLE_KINDS = 6
VEHICLE_FRAMES = 5
VEHICLE_FPS = 9

ALTAR_KINDS = 2
ALTAR_FRAMES = 7
ALTAR_FPS = 10

# The second BREAK sheet, and it borrows the barrel's clock: wood giving way
# is wood giving way, and two smash speeds on one map would read as two
# different physics rather than as two different objects.
CRATE_KINDS = 8
CRATE_FRAMES = 8
CRATE_FPS = 13

BONES_VARIANTS = 6
OIL_VARIANTS = 4


# --- shared drawing ---------------------------------------------------------


def _fill(
    px,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    ramp: Ramp,
    shade: float,
    salt: int,
    width: int,
    height: int,
    grain: float = 0.18,
) -> None:
    """A grained rectangle. The workhorse: every flat panel in this file."""
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            px[x, y] = pick(ramp, shade + (hash01(x, y, salt) - 0.5) * grain, x, y)


def _line(px, x0: int, y0: int, x1: int, y1: int, ramp: Ramp, shade: float,
          width: int, height: int) -> None:
    """A short straight run of pixels. Hinges, ribs, rails and ribs of bone."""
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for step in range(steps + 1):
        t = step / steps
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = pick(ramp, shade, x, y)


def _disc(px, cx: float, cy: float, r: float, ramp: Ramp, shade: float, salt: int,
          width: int, height: int, squash: float = 1.0) -> None:
    for y in range(max(0, int(cy - r * squash)), min(height, int(cy + r * squash) + 1)):
        for x in range(max(0, int(cx - r)), min(width, int(cx + r) + 1)):
            dx = (x - cx) / max(r, 0.5)
            dy = (y - cy) / max(r * squash, 0.5)
            if dx * dx + dy * dy <= 1.0:
                px[x, y] = pick(
                    ramp, shade - dy * 0.18 + (hash01(x, y, salt) - 0.5) * 0.16, x, y
                )


def _hollow(px, x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> None:
    """The dark inside of something that has just been opened.

    Not black: a hole punched in a sprite reads as a hole in the sprite. It is
    the wood ramp's own darkest step, so the interior reads as unlit rather
    than as missing.
    """
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            px[x, y] = pick(PLANK_DARK, 0.06 + (hash01(x, y, 401) - 0.5) * 0.08, x, y)


def _spark(px, x0: int, y0: int, x1: int, y1: int, ramp: Ramp, amount: float,
           salt: int, width: int, height: int) -> None:
    """A few lit pixels inside an opening. `amount` is 0..1 and gates how many.

    This is the whole reward-read of an open container at 16px: you cannot
    draw the item, so what says "there is something in here" is a scatter of
    the only warm pixels on the map falling on the inside of the lid.

    SPARSE, and that number was tuned down twice. At a third of the pixels it
    stopped reading as contents catching the light and started reading as a
    fire burning inside the object — which on a map where the only other warm
    things are torches and the extraction beacon is actively misleading.
    """
    if amount <= 0.0:
        return
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            if hash01(x, y, salt) > 1.0 - 0.16 * amount:
                px[x, y] = pick(ramp, 0.34 + amount * 0.32, x, y)


def _wheel(px, cx: float, cy: float, r: float, width: int, height: int,
           flat: bool = False) -> None:
    """A tyre with a hub in it, and optionally sat down on its rim.

    The hub is what makes a black blob read as a wheel rather than as a hole
    in the sprite, and it is the only place a vehicle spends a bright pixel
    below its waist. `flat` squashes the bottom of the circle onto the ground
    and widens it — a dead car with one flat is the cheapest way to say this
    has been here a while, and the asymmetry is what stops six identical
    wheels reading as a diagram.
    """
    squash = 0.78 if flat else 1.0
    _disc(px, cx, cy + (r * 0.16 if flat else 0.0), r * (1.12 if flat else 1.0),
          TYRE, 0.60, 211, width, height, squash=squash)
    # The hub is small and DIM. Sized up or lit any harder it stops reading as
    # a wheel centre and starts reading as a lamp, which on a vehicle is the
    # one wrong answer — headlights are the four saturated pixels at the nose
    # and nothing below the sill may compete with them.
    _disc(px, cx, cy + (r * 0.14 if flat else 0.0), max(1.0, r * 0.30),
          CHROME, 0.22, 213, width, height, squash=squash)
    # One lit pixel top-left of the hub. A wheel is a cylinder end and this is
    # the entire budget for saying so.
    hx, hy = int(cx - r * 0.20), int(cy - r * 0.24)
    if 0 <= hx < width and 0 <= hy < height and px[hx, hy][3]:
        px[hx, hy] = pick(CHROME, 0.55, hx, hy)


def _top_light(img: Image.Image, ramp: Ramp, shade: float = 0.95,
               inset: int = 0) -> None:
    """Relight the topmost opaque pixel of every column.

    THE ONE RULE THIS FILE'S READ DEPENDS ON. A pixel-art object is legible
    because its lit edge and its shadow are far apart in value, and the lit
    edge is always the same place: whatever the sky can see. Painting it in a
    second pass rather than in each shape means a bonnet, a roof and a lid all
    get the same edge without any of them knowing about the others, and a
    shape moved half a pixel keeps its highlight instead of losing it.
    """
    px = img.load()
    for x in range(inset, img.width - inset):
        for y in range(img.height):
            if px[x, y][3] > 20:
                px[x, y] = pick(ramp, shade, x, y)
                break


def _specular(px, x0: int, y0: int, run: int, ramp: Ramp, width: int, height: int,
              shade: float = 0.95, step: int = 1) -> None:
    """One short diagonal streak. Glass, and nothing else.

    A window is the only surface out here that is FLAT and POLISHED, and one
    pale line across a dark rectangle is what a player reads as glass instead
    of as a hole. Two lines read as a reflection of something, which raises a
    question the map cannot answer.
    """
    for index in range(run):
        x = x0 + index
        y = y0 + index * step
        if 0 <= x < width and 0 <= y < height and px[x, y][3] > 20:
            px[x, y] = pick(ramp, shade, x, y)


def _seam(px, x0: int, y0: int, x1: int, y1: int, width: int, height: int,
          ramp: Ramp = PLANK_DARK, shade: float = 0.12) -> None:
    """A dark line where two forms MEET. Panel gaps, door shuts, lid seals.

    Drawn dark rather than light because at this scale a seam is a crack with
    no light in it, and because the alternative — outlining every sub-shape —
    turns an object into a diagram of itself.
    """
    _line(px, x0, y0, x1, y1, ramp, shade, width, height)


def _wear(px, x0: int, y0: int, x1: int, y1: int, ramp: Ramp, salt: int,
          width: int, height: int, amount: float = 0.14) -> None:
    """Rust, rot or moss, in PATCHES over a band of an object.

    Everything in this forest has been standing in it for a year, and the
    difference between a prop and a prop somebody abandoned is entirely in
    this pass: unbroken paint reads as a car parked five minutes ago.

    THE ROLL IS ON A 2x2 GRID AND THE TONE IS A STEP. It used to roll per
    pixel and then pick a random shade for each hit, which is two separate
    ways of producing the scattered noise S5 rules out — on the vehicles it
    came out as orange confetti along every sill, which is the one part of the
    sheet a player sees at every range. S5 puts the minimum meaningful cluster
    at 2x2, so the hash is quantised to that; the tone is one of two adjacent
    ramp steps chosen by a second coarse roll, so a patch is a patch of a
    material rather than a spray of unrelated values.
    """
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            if px[x, y][3] <= 20:
                continue
            if hash01(x // 2, y // 2, salt) >= amount:
                continue
            # The TONE is quantised coarser than the placement — a 4x4 block
            # picks the step, a 2x2 block decides whether there is any wear
            # there at all. Choosing the step on the same 2x2 grid alternates
            # neighbouring patches between two adjacent ramp steps, and a
            # field of alternating 2x2 blocks is a checkerboard, which is
            # exactly what appeared across the altar slab.
            step = 2 if hash01(x // 4, y // 4, salt + 7) < 0.62 else 3
            px[x, y] = tone(ramp, min(step, len(ramp) - 1), x, y)


def _ground_dark(img: Image.Image, rows: int = 2, drop: float = 0.55) -> None:
    """Darken the bottom rows of a sprite toward its own outline colour.

    The client bakes a contact shadow UNDER a standing prop, which plants it on
    the floor; this is the other half — the object's own underside, which the
    ground shadow cannot supply because it is drawn behind the sprite. Without
    it the bottom edge is as lit as the top and the thing reads as a sticker.
    """
    px = img.load()
    for offset in range(rows):
        y = img.height - 1 - offset
        if y < 0:
            continue
        factor = drop + offset * (1.0 - drop) * 0.5
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a > 20:
                px[x, y] = (int(r * factor), int(g * factor), int(b * factor), a)


def _explode(intact: Image.Image, frame: int, frames: int, salt: int) -> Image.Image:
    """One break frame. Shared by every sheet whose verb is BREAK.

    IT THROWS PIECES, NOT SAND. The old version moved every pixel on its own
    noise, which at eight frames is a barrel dissolving into a cloud of dots —
    legible as "the object went away" and as nothing else. What a player needs
    to read off a smash is that the thing CAME APART: the staves went one way,
    the lid went up, the hoops fell. So the sprite is cut into wedges around
    its own centre, each wedge is thrown as ONE piece on its own heading, and
    the pieces arc down and land. Same cost, and it is the difference between
    an object breaking and an object fading out.

    Three beats, and they are the whole feel:

      * frame 1 is the HIT — the silhouette jolts up a pixel and its rim goes
        bright. Nothing has moved apart yet. A break with no anticipation
        frame reads as a hitbox event rather than as an impact;
      * the middle frames throw the wedges out and down under gravity;
      * the tail fades what is left and leaves dust at the foot, so the client
        can drop the sprite without a pop.
    """
    if frame <= 0:
        return intact.copy()

    width, height = intact.size
    src = intact.load()
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    t = frame / max(frames - 1, 1)
    cx = (width - 1) / 2.0
    cy = height * 0.55
    ground = height - 1

    # THE HIT. One frame of the intact silhouette, lifted and rimmed. The rim
    # is warm rather than white: a white outline on a night map is a light
    # source, and the barrel is not lighting the clearing, it is being hit.
    if frame == 1:
        for y in range(height):
            for x in range(width):
                pixel = src[x, y]
                if pixel[3] < 20:
                    continue
                ny = max(0, y - 1)
                lit = y > 0 and src[x, y - 1][3] < 20
                px[x, ny] = (246, 226, 178, pixel[3]) if lit else pixel
        return img

    #: Wedges the silhouette is cut into. Six is enough to read as pieces and
    #: few enough that each piece survives as a recognisable lump of the thing
    #: it came off.
    wedges = 6
    speed = [4.5 + hash01(salt, index, 61) * 7.0 for index in range(wedges)]
    lift = [2.2 + hash01(salt, index, 67) * 4.5 for index in range(wedges)]
    spin = [(hash01(salt, index, 71) - 0.5) * 2.0 for index in range(wedges)]

    for y in range(height):
        for x in range(width):
            pixel = src[x, y]
            if pixel[3] < 20:
                continue
            angle = math.atan2(y - cy, x - cx)
            index = int((angle + math.pi) / math.tau * wedges) % wedges
            # Each wedge travels as a body: one heading for every pixel in it,
            # which is what makes it a fragment instead of a spray.
            heading = (index + 0.5) / wedges * math.tau - math.pi
            travel = speed[index] * t
            rise = lift[index] * t - 9.0 * t * t
            nx = x + math.cos(heading) * travel + spin[index] * t * (y - cy) * 0.3
            ny = y + math.sin(heading) * travel * 0.55 - rise
            nx, ny = int(round(nx)), int(round(ny))
            if ny > ground:
                ny = ground
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            fade = 1.0 if t < 0.45 else 1.0 - (t - 0.45) / 0.55
            alpha = int(pixel[3] * max(fade, 0.0))
            if alpha > 24:
                px[nx, ny] = (pixel[0], pixel[1], pixel[2], alpha)

    # Dust at the foot, low and wide, under everything. It is what says the
    # pieces hit the ground rather than that they went on travelling.
    if 0.15 < t < 0.9:
        puff = int(200 * (1.0 - abs(t - 0.45) * 2.0))
        for index in range(7):
            dx = int(cx + (hash01(salt, index, 41) - 0.5) * width * (0.6 + t))
            dy = int(ground - hash01(salt, index, 43) * 2.5)
            if 0 <= dx < width and 0 <= dy < height and puff > 30 and px[dx, dy][3] < 40:
                px[dx, dy] = (*pick(PLANK, 0.62, dx, dy)[:3], min(puff, 190))
    return img


def _ease(t: float) -> float:
    """Lid motion. Fast off the seal, slow into the stop -- a hinge, not a slider."""
    return 1.0 - (1.0 - clamp01(t)) ** 2.2


# --- barrels: the things you break ------------------------------------------


def make_barrel(width: int, height: int, kind: int, rng: random.Random) -> Image.Image:
    """`kind`: 0 wooden barrel, 1 steel drum, 2 fuel drum.

    All three are the same cylinder with a different skin, because the
    silhouette IS the promise: a barrel-shaped thing in this game is a thing
    you shoot. What the skin changes is the guess about what falls out.

    A BARREL STANDS ON ITS END, so unlike every other cylinder in this file it
    is not a `billet` — the axis points at the sky and what the camera sees is
    the LID. That lid is the whole upgrade. The old drawing was a front
    elevation: a bulged rectangle with a value ramp running out to both edges
    and a token ellipse dropped on top, which is a drawing of a barrel seen
    from the side by somebody standing on the floor. From this camera you look
    DOWN at the rim, so the lid is a wide ellipse at the lit plane, the staves
    below it are banded — not ramped — and the two are separated by a rim that
    is one step darker than either, because that is where the wood turns.

    The bulge stays: a straight-sided cylinder reads as a bucket. It is now in
    the SILHOUETTE only, where it belongs, instead of being implied by shading.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    body_h = int(height * 0.80)
    top = ground - body_h
    rx = width * 0.30
    ry = max(1.6, rx * SLOPE)

    ramp = PLANK if kind == 0 else (STEEL if kind == 1 else RUST)
    band = STEEL if kind == 0 else CHROME

    # The staves. Three vertical bands, not a falloff: the lit face, the face
    # turned away, and a narrow contact-dark edge on the far side. Where the
    # break falls is a function of x alone, so every stave on the sheet turns
    # at the same place and the barrels read as one family.
    lid_y = top + ry
    for y in range(int(lid_y), ground + 1):
        t = (y - lid_y) / max(ground - lid_y, 1)
        half = rx + width * 0.055 * math.sin(t * math.pi)
        for x in range(int(round(cx - half)), int(round(cx + half)) + 1):
            if not 0 <= x < width:
                continue
            across = (x - cx) / max(half, 0.5)
            plane = FRONT if across < 0.30 else (SIDE if across < 0.86 else 0)
            px[x, y] = tone(ramp, plane, x, y)

    # Hoops. Two on wood, three on steel — the only horizontal beat on the
    # sprite, and what stops the cylinder reading as a slab. Each one follows
    # the bulge and takes the SAME plane break as the stave under it, one step
    # over, so a hoop is a band of metal and not a stripe of paint.
    hoops = (0.14, 0.70) if kind == 0 else (0.08, 0.42, 0.78)
    for hoop in hoops:
        y = int(lid_y + (ground - lid_y) * hoop)
        half = rx + width * 0.055 * math.sin(hoop * math.pi)
        for x in range(int(round(cx - half)), int(round(cx + half)) + 1):
            if not (0 <= x < width and 0 <= y < height):
                continue
            across = (x - cx) / max(half, 0.5)
            px[x, y] = tone(band, TOP if across < 0.30 else FRONT, x, y)

    # THE LID, and it is what makes this a barrel rather than a picture of one.
    # Rim first at the shade step, then the head inside it at the lit step, so
    # the edge of the ellipse is a turn in the material rather than an outline.
    for y in range(int(round(top)), int(round(top + ry * 2)) + 1):
        for x in range(int(round(cx - rx)), int(round(cx + rx)) + 1):
            if not (0 <= x < width and 0 <= y < height):
                continue
            dx, dy = (x - cx) / rx, (y - (top + ry)) / ry
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            px[x, y] = tone(ramp, FRONT if d > 0.66 else TOP, x, y)
    # AMBIENT OCCLUSION WHERE THE HEAD MEETS THE STAVES (S10). One arc at the
    # contact step along the lid's lower edge. Without it the rim of the head
    # and the lit face of the staves land on the same plane step — which they
    # should, they face the same way — and the lid dissolves into the body.
    # Two surfaces that meet are separated by the dark where they meet, not by
    # giving one of them a value it has no business having.
    for x in range(int(round(cx - rx)), int(round(cx + rx)) + 1):
        if not 0 <= x < width:
            continue
        dx = (x - cx) / rx
        edge = int(round(top + ry + ry * math.sqrt(max(0.0, 1.0 - dx * dx))))
        for y in (edge, edge + 1):
            if 0 <= y < height and px[x, y][3]:
                px[x, y] = tone(ramp, 0, x, y)
    # Two staves of end grain across the head. Value steps, never lines.
    for offset in (-0.34, 0.30):
        gx = int(round(cx + offset * rx))
        for y in range(int(round(top)), int(round(top + ry * 2)) + 1):
            if not (0 <= gx < width and 0 <= y < height) or not px[gx, y][3]:
                continue
            dx, dy = (gx - cx) / rx, (y - (top + ry)) / ry
            if dx * dx + dy * dy <= 0.62:
                px[gx, y] = tone(ramp, FRONT, gx, y)

    if kind == 2:
        # Hazard band. Two rows, the one warm thing on the object, and the only
        # reason a fuel drum reads differently from a rusty one.
        for y in (int(lid_y + (ground - lid_y) * 0.28),
                  int(lid_y + (ground - lid_y) * 0.33)):
            half = rx + width * 0.05
            for x in range(int(cx - half), int(cx + half) + 1):
                if 0 <= x < width and 0 <= y < height and px[x, y][3] and (x + y) % 3:
                    across = (x - cx) / max(half, 0.5)
                    px[x, y] = tone(HAZARD, TOP if across < 0.30 else FRONT, x, y)

    if kind == 0 and rng.random() < 0.6:
        # A stave sprung at the seam. Damage before anybody shot it.
        sx = int(cx + rng.uniform(-rx * 0.7, rx * 0.7))
        for y in range(int(lid_y) + 1, int(lid_y + (ground - lid_y) * 0.5)):
            if 0 <= sx < width and px[sx, y][3]:
                px[sx, y] = tone(PLANK_DARK, 1, sx, y)

    shadow(img, cx, ground - 0.5, rx * 1.15, ry * 0.9)
    outline(img, OUTLINE_WOOD if kind == 0 else OUTLINE_COLD)
    return img


# --- crates: eight boxes somebody left in the forest -------------------------
# The one family in this file with no curve anywhere in it, and drawn that way
# on purpose: a crate is three flat planes meeting at three hard edges, so it
# is where the box construction of PIXEL-ART-DIRECTION.md can be built
# STRAIGHT rather than implied. Every plane is one exact band of the ramp and
# the volume is read off the breaks between them (§2, §3) — top face
# brightest, the plane turned into the key next, the plane turned away from it
# darkest. Nothing here is shaded by distance from a centre, because a box has
# no centre. It has faces.
#
# ONE YAW FOR THE WHOLE SHEET (§1, variant A). Every crate is 2:1 dimetric
# with its near corner pointing at the camera, so eight of them piled in a
# dumpsite read as eight boxes and not as eight camera angles. That is also
# why the geometry is COLUMN-SCANNED rather than polygon-filled: at a 1:2
# slope every edge lands on an exact two-pixel run, which is the clean slope
# §5 asks for and is precisely what a polygon rasteriser will not give you at
# sixteen pixels.
#
# WHAT MAKES ONE FEEL SOLID, in the order the eye takes it:
#
#   1. the plane break    three faces, three flat bands, no gradient across any
#   2. the lid lip        one lit row along the top face's near edges and one
#                         dark row directly under it. That PAIR is the board
#                         thickness, and it is the single cue that stops a top
#                         face reading as a lozenge painted on a rectangle
#   3. the corner post    a lit column standing on the near corner with its
#                         shaded cheek beside it, so the two vertical planes
#                         are joined by a batten instead of by a colour change
#   4. the board courses  seams at a fixed pitch, running along the grain axis
#                         of the face they are on (§14, wood)
#   5. the contact        a step-0 band at the bottom, inside the silhouette
#                         (§10, §19)
#
# THE GROUND SHADOW IS NOT BAKED IN, and that is a deliberate difference from
# the rocks and trees in `make_textures.py`. This is a BREAK sheet: `_explode`
# throws every opaque pixel of frame 0 outward, and an ellipse baked into the
# frame would be thrown with them — a crate's own shadow flying off sideways.
# The client lays one under every standing prop instead
# (`client/src/render/layers/scenery.ts`), which is what the barrels standing
# next to these already rely on. What the sprite owes the floor is the half a
# cast shadow cannot supply from behind: the contact band and the darkened
# underside.
#
# EIGHT RECIPES, NOT EIGHT ROLLS OF ONE. Same argument as `ROCK_RECIPES`: what
# has to differ between two crates is the SILHOUETTE, and rerolling one recipe
# varies the noise inside a shape it never varies. The sheet's frame order is
# this dict's order.

#: The camera, as one number. 0.5 is 2:1 dimetric: two pixels across per pixel
#: of depth, so every receding edge is a clean 1:2 run.
CRATE_SLOPE = 0.5

#: Ramp steps by plane, and the gaps between them are the whole design. PLANK
#: has six steps and the three planes take 5 / 3 / 1 — TWO steps apart each
#: time, never one. One step apart is what §3's table reads like on paper and
#: it is wrong at this size: a single ramp step between the lid and the near
#: wall is a difference the eye resolves as texture, and the box goes back to
#: being a shaded rectangle. Two steps and the plane break is the first thing
#: you see, which is what §13 means by contrast as a hierarchy tool. What is
#: left over does the joinery: 4 for a batten catching the key, 2 for the
#: shade wall's hardware, 0 for seams and the contact.
CRATE_TOP = 5
CRATE_LIP = 5
CRATE_FRONT = 3
CRATE_SIDE = 1
CRATE_BATTEN = 4
CRATE_BATTEN_SHADE = 2

#: Board pitch, in pixels, when a recipe does not say otherwise. Four gives
#: three courses on a body this tall — enough to say "planks", few enough that
#: the seams stay a rhythm rather than a texture.
CRATE_BOARDS = 4

# A box: (fx, base, lw, rw, h). x terms are fractions of the frame width, y
# terms of its height, so a recipe survives a change of TILE_SIZE.
#   fx      where the NEAR corner stands, across the frame
#   base    its contact height; 1.0 is the frame's own contact line
#   lw, rw  how far the footprint runs left and right of that corner. Unequal
#           on purpose — a box with lw == rw is a diamond, and a diamond reads
#           as a gem rather than as a crate
#   h       how far the walls rise
CRATE_RECIPES: dict[str, dict] = {
    # The reference box. Everything else on the sheet is this one damaged,
    # reinforced or doubled, so it carries no accident at all: square courses,
    # one diagonal brace, clean lid.
    "plain": {
        "boxes": [(0.50, 1.00, 0.40, 0.33, 0.50)],
        "brace": "/",
    },
    # Lid gone. Two courses of the top face are missing and the rest stands
    # proud, so the top CONTOUR — the thing §15 says carries the identity — is
    # notched instead of straight. The hollow under it is the read.
    "broken": {
        "boxes": [(0.50, 1.00, 0.41, 0.34, 0.46)],
        "brace": "",
        "gaps": (1, 2),
        "splinter": 0.70,
        "debris": 3,
    },
    # Reinforced: the tallest single box, wearing a second set of battens and
    # a rope lashing over the lid. Height:footprint at the top of §17's range
    # is doing the work — a reinforced crate should look like it was packed to
    # travel, and travelling crates are tall.
    "braced": {
        "boxes": [(0.49, 1.00, 0.36, 0.30, 0.64)],
        "brace": "x",
        "bands": (0.28, 0.74),
        "band_ramp": "rope",
        "rope": True,
    },
    # Two boxes at 1 : 0.68 by footprint — §17's rhythm, not two of a size. The
    # upper one is set BACK on the lower's top face rather than centred on it,
    # which is what turns a stack into a stack instead of a wedding cake: you
    # can see the lid it is standing on.
    "stacked": {
        "boxes": [
            (0.51, 1.00, 0.41, 0.33, 0.40),
            (0.43, 0.52, 0.28, 0.22, 0.30),
        ],
        "brace": "/",
    },
    # Damaged: a punched-through near wall and a chewed top edge. The hole is
    # the only place on the sheet where the inside of a wall is visible from
    # the front, so it gets a lit splinter lip on its upper-left rim and
    # nothing on the other three — one key, no fill (§8).
    "battered": {
        "boxes": [(0.51, 1.00, 0.43, 0.29, 0.44)],
        "brace": "\\",
        "holes": ((0.46, 0.46, 2.4),),
        "splinter": 0.25,
        "bite": (0.55, 3.0),
        "debris": 2,
    },
    # Rotted: a year of wet. Low, sagging, mossed along the top plane and the
    # shaded wall, with a course gone out of the lid so the box sits in its own
    # decay rather than on it. The moss is the accent hue (§12) and it is the
    # only saturated thing on the sheet.
    "rotted": {
        "boxes": [(0.50, 1.00, 0.44, 0.36, 0.34)],
        "brace": "",
        "boards": 3,
        "moss": 0.22,
        "splinter": 0.30,
        "sag": 0.34,
        "grain": 0.16,
    },
    # Metal-reinforced: steel brackets on all three visible corners, two bands
    # round the body and bolt heads on them. The bolts are the sheet's only
    # single-pixel speculars and there are three of them, which is exactly the
    # allowance §5 gives.
    "ironbound": {
        "boxes": [(0.50, 1.00, 0.38, 0.31, 0.58)],
        "brace": "",
        "bands": (0.30,),
        "iron": True,
        "rust": 0.30,
    },
    # Partially collapsed: the lid has fallen INTO the box. The top plane is
    # mostly hollow, the walls that held it are low and uneven, and a board
    # that came off leans on the shaded side — one diagonal against a stack of
    # horizontals, which is the whole silhouette read at this size.
    "collapsed": {
        "boxes": [(0.52, 1.00, 0.44, 0.32, 0.30)],
        "brace": "",
        "boards": 3,
        "gaps": (1, 2),
        "splinter": 0.40,
        "planks": ((0.95, 0.94, 0.60, 0.42),),
        "debris": 4,
    },
}


def _tone(ramp: Ramp, step: int, x: int, y: int,
          grain: float = 0.0, salt: int = 0) -> RGBA:
    """One EXACT band of a ramp, grained only when asked.

    `pick` dithers between the two nearest steps, which is what a continuous
    value wants and the opposite of what a flat plane wants: a face shaded
    through `pick` at 0.63 comes out chequered between two steps and the plane
    break stops being a break. Handing it the step's own value lands it on the
    step, so a face is one colour unless the recipe asks for grain.
    """
    value = step / (len(ramp) - 1)
    if grain:
        value += (hash01(x, y, salt) - 0.5) * grain
    return pick(ramp, clamp01(value), x, y)


#: PUBLIC NAMES FOR THE CAMERA AND THE PAINTER. `make_scenery.py` draws the
#: props that were never carried in — tents, fences, signs, felled trunks, a
#: cold fire — and they stand in the same clearing as the crates and barrels
#: here. A prop shaded on its own slope and its own steps is a prop from a
#: different game standing next to one from this one, so the two modules share
#: the camera (`SLOPE`) and the flat-step painter (`tone`) rather than each
#: keeping a copy. Same argument as `make_guns.paint_rows`.
SLOPE = CRATE_SLOPE
#: Plane -> ramp step, on a six-step ramp. Two steps apart, never one: see the
#: note over `CRATE_TOP`. Every volume in the scenery folder is banded on these.
PLANE_TOP = CRATE_TOP
PLANE_FRONT = CRATE_FRONT
PLANE_SIDE = CRATE_SIDE
#: Short names, for the toolkit below and for anything drawing with it.
TOP, FRONT, SIDE = PLANE_TOP, PLANE_FRONT, PLANE_SIDE

#: The flat-step painter under a public name — see `SLOPE` above.
tone = _tone


# --- the volume toolkit -----------------------------------------------------
# THREE SOLIDS AND A CONTACT PATCH, AND EVERY STANDING THING IN THE SCENERY
# FOLDER IS MADE OF THEM. They live here rather than in `make_scenery.py`
# because that module imports this one, so this is the only end of the pair
# both sides can reach — and every sheet in the folder has to be lit by one
# rule or the clearing comes out as a collection of assets rather than a
# place.
#
# WHAT THEY REPLACED. Every object below used to be a FRONT or SIDE ELEVATION:
# a flat face with a value ramp across it, dithered by `pick`, with no top
# surface anywhere. That is a drawing of a barrel rather than a barrel, and it
# is the same failure the guns sheet and the crates each had before their own
# pass. A volume here is BANDS — a top plane, a near plane two steps under it,
# a far plane two under that — and the break between them is the whole read.
#
# `SLOPE`, `PLANE_TOP/FRONT/SIDE` and `tone` above are the camera and the
# painter these are built on. Do not shade a plane through `pick`: it dithers
# between the two nearest steps, so a "subtle" grain scatters single pixels of
# the neighbour across a face, which is the per-pixel noise S5 rules out.


def shadow(img: Image.Image, cx: float, cy: float, rx: float, ry: float) -> None:
    """The contact patch under a standing thing, painted only where it is not.

    Not a drop shadow and not a gradient: two flat alphas of the outline
    colour, laid down only on transparent pixels, so it reads as the ground
    going dark beside the object rather than as a smudge on it. It is the
    cheapest thing on this sheet and most of why a prop stops looking stuck to
    the camera.
    """
    px = img.load()
    for y in range(max(0, int(cy - ry)), min(img.height, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(img.width, int(cx + rx) + 1)):
            if px[x, y][3]:
                continue
            dx, dy = (x - cx) / max(rx, 0.5), (y - cy) / max(ry, 0.5)
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            px[x, y] = (*OUTLINE_WOOD[:3], 104 if d < 0.5 else 58)


def box(px, size: tuple[int, int], fx: float, base: float, lw: float, rw: float,
         tall: float, ramp: Ramp, *, grain: float = 0.0, salt: int = 0,
         top: int = TOP, front: int = FRONT, side: int = SIDE) -> None:
    """A dimetric box standing on the ground: top face, near face, far face.

    Same projection as a crate — the footprint is a rhombus with its near
    corner at `fx`, the contact line falls away from that corner at the camera
    slope in both directions, and the lid is the contact lifted by `tall`.
    Posts, boards, sign planks and a tent's gable are all this.
    """
    width, height = size
    far_x = fx - lw + rw
    for x in range(max(0, int(round(fx - lw))), min(width, int(round(fx + rw)) + 1)):
        contact = base - abs(x - fx) * SLOPE
        lid = contact - tall
        back = contact - tall - (lw + rw) * SLOPE + abs(x - far_x) * SLOPE
        gy, ly = int(round(contact)), int(round(lid))
        by = min(int(round(back)), ly)
        for y in range(max(0, by), min(height, gy + 1)):
            plane = top if y <= ly else (front if x <= fx else side)
            px[x, y] = tone(ramp, plane, x, y, grain, salt)


def cap(px, size: tuple[int, int], fx: float, base: float, lw: float, rw: float,
        ramp: Ramp, step: int = TOP, *, squash: float = 1.0) -> None:
    """Just the LID of a box — the rhombus its top face lands on.

    `box` draws a solid; this draws the one face of it the camera looks down
    at, on its own, at whatever height and whatever foreshortening you hand
    it. That is what an opening lid needs: a lid swinging back is the same
    rhombus seen at a steeper angle, so it squashes toward a line rather than
    sliding up the frame as a slab. A lid drawn as a rectangle that rises is
    a lid on a sprite with no top, which is what the box sheet used to be.
    """
    width, height = size
    far_x = fx - lw + rw
    reach = (lw + rw) * SLOPE * squash
    for x in range(max(0, int(round(fx - lw))), min(width, int(round(fx + rw)) + 1)):
        near = base - abs(x - fx) * SLOPE * squash
        back = near - reach + abs(x - far_x) * SLOPE * squash
        for y in range(max(0, int(round(back))), min(height, int(round(near)) + 1)):
            px[x, y] = tone(ramp, step, x, y)


def dome(px, size: tuple[int, int], fx: float, base: float, lw: float, rw: float,
         rise: float, ramp: Ramp) -> None:
    """A curved lid: rhombi stacked on a circular profile, widest at the rim.

    The chest is the one object in the forest with a curve on top, and it is
    the only reason it reads as different from across a clearing. Drawn as a
    bulged rectangle it was a curve on a FLAT object; stacked as caps it is a
    surface the camera goes over — the rim at the base plane, the crown at the
    lit one, and the steps between them the facets S2 asks for instead of a
    gradient.
    """
    width, height = size
    steps = max(2, int(round(rise)))
    for index in range(steps):
        t = (index + 0.5) / steps
        shrink = math.sqrt(max(0.0, 1.0 - t * t))
        step = TOP if index >= steps - 2 else (FRONT if index else FRONT - 1)
        cap(px, size, fx, base - t * rise, max(1.0, lw * shrink),
            max(1.0, rw * shrink), ramp, step)


def billet(px, size: tuple[int, int], x0: float, x1: float, axis: float,
            r: float, ramp: Ramp, *, grain: float = 0.0, salt: int = 0,
            cap: bool = True) -> None:
    """A cylinder lying along the screen X axis. A trunk, a rail, a ridge pole.

    THREE BANDS, NOT A FALLOFF, and they are UNEQUAL. A round thing under one
    light has a lit crest, a wide flank and a thin underside; the boundaries
    between those three are the only thing at this size that says round, and a
    smooth ramp across the diameter reads as a blurred bar. Sizes follow S7 —
    the flank is the base step and owns the most pixels, the crest the fewest —
    which is also what keeps a 32px trunk from out-glaring the crate beside it.

    NO GRAIN ON THE BANDS. `grain` feeds `_tone`, which feeds `pick`, which
    DITHERS between the two nearest steps whenever the value is not exactly on
    one — so a "subtle" 0.10 of grain does not roughen a plane, it scatters
    single pixels of the neighbouring step across it, which is the per-pixel
    noise S5 rules out. Texture on these props is a clustered BAND (the bark
    strip in `make_logs`), never a jitter. The parameter stays for the
    charcoal, which genuinely wants to break up.

    The ends TAPER, so the silhouette is not a rectangle — a cylinder drawn
    with square ends is a plank however it is shaded. `cap` then draws the
    sawn face at `x0` as a squashed disc: sapwood rim, heartwood, dark pith.
    It is the one part of a felled trunk with any shape at all.
    """
    width, height = size
    for x in range(max(0, int(round(x0))), min(width, int(round(x1)) + 1)):
        # Round both ends over one radius of run. Clean slopes, no jitter (S5).
        t = min((x - x0) / max(r, 1.0), (x1 - x) / max(r, 1.0), 1.0)
        rr = r if t >= 1.0 else r * (0.55 + 0.45 * max(t, 0.0))
        for y in range(max(0, int(round(axis - rr))), min(height, int(round(axis + rr)) + 1)):
            up = (axis - y) / max(rr, 0.5)
            plane = TOP if up > 0.50 else (FRONT if up > -0.45 else SIDE)
            px[x, y] = tone(ramp, plane, x, y, grain, salt)
    if not cap:
        return
    cap_rx = max(2.0, r * 0.70)
    cx = x0 + cap_rx - 0.5
    for y in range(max(0, int(round(axis - r))), min(height, int(round(axis + r)) + 1)):
        for x in range(max(0, int(round(cx - cap_rx))), min(width, int(round(cx + cap_rx)) + 1)):
            dx, dy = (x - cx) / cap_rx, (y - axis) / max(r, 0.5)
            d = dx * dx + dy * dy
            if d > 1.0:
                continue
            # Rim, heartwood, pith — three steps in from the edge, so the face
            # reads as concentric rather than as one lighter blob.
            ring = TOP if d > 0.66 else (FRONT if d > 0.22 else SIDE)
            px[x, y] = tone(ramp, ring, x, y)


def stone(px, size: tuple[int, int], cx: float, cy: float, rx: float, ry: float,
           ramp: Ramp, salt: int) -> None:
    """One boulder: a lit cap, a flank, and the contact band it sits in.

    Stone is heavy (S14), so the bands are wide and the breaks are straight —
    an angular facet, never a soft bulb. The bottom band is `SIDE` rather than
    the flank's `FRONT`: that is the occlusion where the stone meets whatever
    it is standing on.
    """
    width, height = size
    for y in range(max(0, int(cy - ry)), min(height, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(width, int(cx + rx) + 1)):
            dx, dy = (x - cx) / max(rx, 0.5), (y - cy) / max(ry, 0.5)
            if dx * dx + dy * dy > 1.0:
                continue
            # Facet by height on the stone, nudged by a coarse 2x2 hash so two
            # stones in a ring are not the same drawing twice (S5: clustered
            # shape, never per-pixel noise).
            lift = -dy + hash01(int(x) // 2, int(y) // 2, salt) * 0.22
            plane = TOP if lift > 0.34 else (FRONT if lift > -0.30 else SIDE)
            px[x, y] = tone(ramp, plane, x, y)



def _stroke(px, x: float, y: float, angle: float, length: float, thick: float,
            ramp: Ramp, shade: float, salt: int, width: int, height: int) -> None:
    """A tapering line of pixels. The workhorse for planks, rails and bones."""
    for step in range(int(length)):
        t = step / max(length - 1, 1)
        ix = int(round(x + math.cos(angle) * step))
        iy = int(round(y + math.sin(angle) * step))
        half = max(0.0, thick * (1.0 - t * 0.35))
        for offset in range(-int(half), int(half) + 1):
            jy = iy + offset
            if 0 <= ix < width and 0 <= jy < height:
                px[ix, jy] = pick(
                    ramp, shade - offset * 0.16 + (hash01(ix, jy, salt) - 0.5) * 0.22, ix, jy
                )


def _crate_box(width: int, height: int, spec: tuple) -> tuple[float, ...]:
    """A recipe's box in pixels: (fx, fy, lw, rw, h)."""
    fx, base, lw, rw, tall = spec
    ground = height - 1
    return (
        fx * (width - 1),
        ground - (1.0 - base) * ground,
        lw * width,
        rw * width,
        tall * ground,
    )


def _crate_edges(box: tuple, x: float) -> tuple[float, float, float]:
    """(contact, lid, back) y for one column of a box.

    Three edges, and they are the whole projection. The footprint is a rhombus
    with its near corner at `fx`, so the contact line falls away from that
    corner at the camera slope in BOTH directions — one expression, no branch.
    The lid is the contact lifted by the wall height; the back edge is the far
    two sides of the top face, which meet over the rhombus's own far corner.
    """
    fx, fy, lw, rw, tall = box
    contact = fy - abs(x - fx) * CRATE_SLOPE
    far_x = fx - lw + rw
    back = fy - tall - (lw + rw) * CRATE_SLOPE + abs(x - far_x) * CRATE_SLOPE
    return contact, contact - tall, back


def _crate_columns(box: tuple, width: int) -> range:
    fx, _, lw, rw, _ = box
    return range(max(0, int(round(fx - lw))), min(width, int(round(fx + rw)) + 1))


def _crate_hull(
    px, size: tuple[int, int], box: tuple, ramp: Ramp, *,
    boards: int = CRATE_BOARDS, grain: float = 0.0, salt: int = 0,
    faces: dict | None = None,
) -> dict[tuple[int, int], str]:
    """Paint one box's three planes, and report which plane each pixel is on.

    The map it returns is what every later pass addresses — a band, a brace, a
    patch of moss all need to know which face they are landing on, and
    recomputing the projection five times to find out is how five passes drift
    apart by a pixel.

    Board seams run along the grain axis of their own face (§14). On a vertical
    wall the grain is horizontal, so the pitch is measured up from the contact.
    On the lid it runs parallel to the near-left edge, so it is measured along
    `x - 2y`, which is constant in exactly that direction — the reason the
    seams on a lid stay parallel to an edge of the box instead of to the edge
    of the frame.
    """
    width, height = size
    marks: dict[tuple[int, int], str] = {} if faces is None else faces
    fx = box[0]
    for x in _crate_columns(box, width):
        contact, lid, back = _crate_edges(box, x)
        gy, ly = int(round(contact)), int(round(lid))
        by = min(int(round(back)), ly)
        for y in range(max(0, by), min(height, gy + 1)):
            if y <= ly:
                face = "top"
                # ONE pixel of seam. `x - 2y` is the coordinate that runs
                # across the boards, and it steps by one per screen column, so
                # testing it directly gives a 1px line; testing it halved gave
                # a 2px line and the lid came out striped rather than planked.
                # The spacing doubles to compensate, which puts two seams on a
                # lid this size — a rhythm, not a texture (§5).
                face_seam = (x - 2 * y) % (boards * 2) == 0
                step = CRATE_TOP - (1 if face_seam else 0)
            else:
                near = x <= fx
                face = "front" if near else "side"
                base = CRATE_FRONT if near else CRATE_SIDE
                step = base - (1 if (gy - y) % boards == 0 else 0)
            px[x, y] = _tone(ramp, max(step, 0), x, y, grain, salt)
            marks[(x, y)] = face
    return marks


def _crate_lip(px, size: tuple[int, int], box: tuple, ramp: Ramp) -> None:
    """The board thickness, in two rows, and it is the money cue.

    A lid catching the sky along its near edge and throwing a line of shade
    onto the wall directly under it is what a real slab does, and drawing that
    pair is cheaper and far more legible than trying to imply depth by shading
    the top face alone. The far edge rolls off by one step instead — the same
    move `_rock_crest` makes, and the only place on this sheet where two bands
    touch without a plane break between them (§7).
    """
    width, height = size
    fx = box[0]
    for x in _crate_columns(box, width):
        contact, lid, back = _crate_edges(box, x)
        gy, ly = int(round(contact)), int(round(lid))
        by = min(int(round(back)), ly)
        if 0 <= ly < height:
            px[x, ly] = _tone(ramp, CRATE_LIP, x, ly)
        under = ly + 1
        if under <= gy and 0 <= under < height:
            # Two steps under its own wall on both sides. A lid that overhangs
            # throws a hard line, and a soft one reads as the top face being
            # bevelled rather than as a separate board sitting on the box.
            px[x, under] = _tone(ramp, 1 if x <= fx else 0, x, under)
        if by < ly and 0 <= by < height:
            px[x, by] = _tone(ramp, CRATE_TOP - 1, x, by)


def _crate_posts(px, size: tuple[int, int], box: tuple, ramp: Ramp) -> None:
    """Corner battens: a lit column on the near corner, a shaded cheek beside it.

    Without this the two walls meet at a value change and the box reads as a
    folded card. With it they meet at an OBJECT, and the fact that the batten
    runs the full height of both walls is what says the corner is structural
    rather than drawn.
    """
    width, height = size
    fx, _, lw, rw, _ = box
    near = int(round(fx))
    for x, step in (
        (near, CRATE_BATTEN),                 # the post, turned into the key
        (near + 1, CRATE_BATTEN_SHADE),       # its cheek, on the shaded wall
        (int(round(fx - lw)) + 1, CRATE_BATTEN),
        (int(round(fx + rw)) - 1, CRATE_BATTEN_SHADE),
    ):
        if not 0 <= x < width:
            continue
        contact, lid, _ = _crate_edges(box, x)
        gy, ly = int(round(contact)), int(round(lid))
        for y in range(max(0, ly + 2), min(height, gy)):
            if px[x, y][3]:
                px[x, y] = _tone(ramp, step, x, y)


def _crate_brace(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                 style: str) -> None:
    """The diagonal across the near wall. One mark, and it is what says CRATE.

    It is drawn on the front plane only. Repeated on the side wall as well it
    doubles the object's busiest element and turns the silhouette's one
    diagonal — the only one it has — into a pattern.
    """
    width, height = size
    fx, _, lw, _, tall = box
    left = fx - lw
    # Walked over integer COLUMNS, never over a parameter that is rounded into
    # them: sampling `left + lw * index / steps` lands on the same column twice
    # and skips the next, and two pixels of batten in one column at two heights
    # is what turned the first version's single diagonal into a rash.
    first, last = int(math.ceil(left)) + 1, int(math.floor(fx))
    for direction in {"/": (1,), "\\": (-1,), "x": (1, -1)}.get(style, ()):
        for x in range(max(0, first), min(width, last + 1)):
            t = (x - left) / max(lw, 1.0)
            contact, _, _ = _crate_edges(box, x)
            rise = (t if direction > 0 else 1.0 - t) * (tall - 3.5) + 2.0
            y = int(round(contact - rise))
            if not (0 <= x < width):
                continue
            # ONE pixel of board and one of shadow under it, and the pair is
            # what makes it a batten. The board alone is a stripe painted on
            # the wall; three pixels of board — which is what the first version
            # drew — is a band, because the diagonal only falls about one row
            # per column and the stacks overlap into a smear.
            for offset, step in ((0, CRATE_TOP), (1, CRATE_FRONT - 2)):
                iy = y + offset
                if 0 <= iy < height and px[x, iy][3]:
                    px[x, iy] = _tone(ramp, step, x, iy)


#: (near step, shade step) for a band, by what it is made of. ROPE is a pale
#: fibre and goes OVER the wood on both faces; STEEL is dark iron and has to go
#: UNDER the lit wall and OVER the shaded one, for the reason spelled out in
#: `_crate_iron` — a strap keyed to one absolute step comes out as pale blue
#: tape on whichever face the wood happens to be darker than it.
BAND_ROPE_STEPS = (4, 2)
BAND_STEEL_STEPS = (2, 3)


def _crate_band(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                at: float, bolts: bool = False,
                steps: tuple[int, int] = (4, 2)) -> None:
    """A band round both walls at one height, following the camera on each.

    Held at a constant height above the CONTACT rather than at a constant y,
    which is the whole point: a band drawn flat across the frame cuts the box
    in half, and a band that rides both contact slopes wraps it.
    """
    width, height = size
    fx, _, lw, rw, tall = box
    near_step, shade_step = steps
    lift = max(1.0, at * tall)
    for x in _crate_columns(box, width):
        contact, lid, _ = _crate_edges(box, x)
        gy, ly = int(round(contact)), int(round(lid))
        near = x <= fx
        for offset in range(2):
            y = int(round(contact - lift)) - offset
            if ly + 1 < y <= gy and 0 <= y < height and px[x, y][3]:
                px[x, y] = _tone(ramp, (near_step if near else shade_step) - offset,
                                 x, y)
    if bolts:
        # THE SHEET'S ONLY SPECULARS, and there are exactly three, which is the
        # allowance §5 gives for orphan single pixels. They sit two steps over
        # the strap they are driven into rather than on CHROME, which is a
        # material nothing else on this crate is made of and which read as
        # three lit blue dots floating off the band.
        for x in (int(round(fx)), int(round(fx - lw)) + 2, int(round(fx + rw)) - 2):
            y = int(round(_crate_edges(box, x)[0] - lift))
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = _tone(ramp, min(near_step + 2, len(ramp) - 1), x, y)


def _crate_gaps(px, size: tuple[int, int], faces: dict, ramp: Ramp,
                boards: int, gaps: tuple[int, ...]) -> None:
    """Knock whole COURSES out of the lid, never holes out of the middle of it.

    A crate loses boards, not pixels. Removing one course leaves two parallel
    straight edges with a dark trough between them, which reads instantly as a
    missing plank; nibbling the same number of pixels at random reads as damage
    to the sprite. The boards left standing round a gap take a step of
    occlusion on the way in, because that edge is now a wall (§10).
    """
    tops = [(x, y) for (x, y), face in faces.items() if face == "top"]
    if not tops:
        return
    order = sorted({((x - 2 * y) // 2) // boards for x, y in tops})
    chosen = {order[index] for index in gaps if 0 <= index < len(order)}
    hollow = {(x, y) for x, y in tops if ((x - 2 * y) // 2) // boards in chosen}
    for x, y in hollow:
        px[x, y] = _tone(PLANK_DARK, 1, x, y, 0.28, 407)
    # The far inner wall. A gap filled edge to edge with one dark tone is a
    # hole cut in the sprite; two rows of dim wood at the back of it is a box
    # you are looking INTO, which is the whole difference between a crate with
    # its lid off and a crate with a bite out of it.
    #
    # Steps 2 and 1, not 1 and 0. Step 0 on this ramp is a hair off
    # OUTLINE_WOOD, so a far wall drawn on it is the same colour as the line
    # round the sprite and the box reads as having no inside at all — which is
    # exactly what happened to `collapsed`, the recipe with the most lid
    # missing and therefore the most to lose by it. Two steps under the near
    # wall's own 3 keeps the interior clearly BEHIND the front face while
    # staying clearly made of wood.
    for x in {column for column, _ in hollow}:
        rows = sorted(y for column, y in hollow if column == x)
        for offset, y in enumerate(rows[:2]):
            px[x, y] = _tone(ramp, 2 - offset, x, y)
    for x, y in tops:
        if (x, y) in hollow:
            continue
        if any((x + dx, y + dy) in hollow
               for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            px[x, y] = _tone(ramp, 2, x, y)


def _crate_hole(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                spec: tuple[float, float, float]) -> None:
    """A hole punched through the near wall, with one lit lip.

    Splintered wood shows its broken end, and that end faces the way the board
    was pushed — inward and up. So the lip goes on the upper-left rim only.
    Ringing the hole all round would light it from four directions at once,
    which is the one thing §8 does not allow.
    """
    width, height = size
    fx, _, lw, _, tall = box
    at_x, at_t, radius = spec
    cx = fx - lw + lw * at_x
    cy = _crate_edges(box, cx)[0] - at_t * tall
    for y in range(max(0, int(cy - radius) - 1), min(height, int(cy + radius) + 2)):
        for x in range(max(0, int(cx - radius) - 1), min(width, int(cx + radius) + 2)):
            if not px[x, y][3]:
                continue
            dist = math.hypot((x - cx) / radius, (y - cy) / (radius * 0.80))
            bite = dist + (hash01(x // 2, y, 419) - 0.5) * 0.42
            if bite <= 1.0:
                px[x, y] = _tone(PLANK_DARK, 1, x, y, 0.22, 421)
            elif bite <= 1.34 and (x - cx) + (y - cy) < 0:
                px[x, y] = _tone(ramp, CRATE_LIP, x, y)


def _crate_splinter(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                    amount: float, salt: int) -> None:
    """Bite the top CONTOUR (§15). Some columns lose two rows, some gain one.

    Only the back edge is touched, because that is the edge on the silhouette:
    chewing the near edge of a lid damages the line the player reads as the
    board's thickness, and a thickness with bites out of it stops being one.
    """
    width, height = size
    for x in _crate_columns(box, width):
        _, lid, back = _crate_edges(box, x)
        by, ly = int(round(back)), int(round(lid))
        if by >= ly:
            continue
        roll = hash01(x, salt, 431)
        if roll < amount * 0.5:
            for y in range(by, min(by + 2, ly)):
                if 0 <= y < height:
                    px[x, y] = TRANSPARENT
        elif roll > 1.0 - amount * 0.35 and by - 1 >= 0:
            px[x, by - 1] = _tone(ramp, CRATE_TOP - 1, x, by - 1)


def _crate_bite(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                span: float, drop: float) -> None:
    """Crush one top corner off, and show the end grain.

    §15 again, and it is the pass the sheet needed most: eight crates built
    from one construction come out with eight of the same hexagon, and a
    silhouette test on that page is eight identical black blobs. Taking a
    corner off is the cheapest change to the TOP CONTOUR — the part §15 says
    carries the identity — that still leaves the object obviously a crate.

    The exposed end catches the key, because a snapped board's end grain faces
    up and out; the row under it does not, because that is the inside.
    """
    width, height = size
    fx, _, _, rw, _ = box
    edge = fx + rw
    reach = max(2.0, rw * span)
    for x in range(max(0, int(round(edge - reach))), min(width, int(round(edge)) + 1)):
        _, lid, _ = _crate_edges(box, x)
        cut = drop * (1.0 - (edge - x) / reach)
        floor = int(round(lid + cut))
        for y in range(0, min(height, floor)):
            px[x, y] = TRANSPARENT
        if 0 <= floor < height and px[x, floor][3]:
            px[x, floor] = _tone(ramp, CRATE_BATTEN, x, floor)
            if floor + 1 < height and px[x, floor + 1][3]:
                px[x, floor + 1] = _tone(ramp, 1, x, floor + 1)


def _crate_sag(px, size: tuple[int, int], box: tuple, ramp: Ramp,
               amount: float) -> None:
    """Dish the lid inward. A year of weather on a box nobody emptied.

    Eats the TOP contour from the back rather than the front, so the near edge
    — the lid lip, the thing carrying the board thickness — survives intact and
    the crate still reads as a crate that sagged rather than as a crate someone
    stood on.
    """
    width, height = size
    fx, _, lw, rw, _ = box
    depth = (lw + rw) * CRATE_SLOPE
    centre = fx - lw * 0.5 + rw * 0.5
    half = max((lw + rw) * 0.5, 1.0)
    for x in _crate_columns(box, width):
        _, lid, back = _crate_edges(box, x)
        by, ly = int(round(back)), int(round(lid))
        profile = max(0.0, 1.0 - ((x - centre) / half) ** 2)
        eat = int(round(amount * depth * profile))
        if eat <= 0 or by >= ly:
            continue
        for y in range(by, min(by + eat, ly)):
            if 0 <= y < height:
                px[x, y] = TRANSPARENT
        floor = min(by + eat, ly - 1)
        if 0 <= floor < height and px[x, floor][3]:
            px[x, floor] = _tone(ramp, 2, x, floor)


def _crate_plank(px, size: tuple[int, int], ramp: Ramp,
                 spec: tuple[float, float, float, float]) -> None:
    """A board that came off, leaning where it fell.

    Two pixels thick, drawn as a lit face over a shaded one, because a board
    seen at this camera still has a top and a side, and a single-pixel line has
    neither.
    """
    width, height = size
    x0, y0, x1, y1 = spec
    ax, ay = x0 * (width - 1), y0 * (height - 1)
    bx, by = x1 * (width - 1), y1 * (height - 1)
    steps = max(int(round(math.hypot(bx - ax, by - ay))), 2)
    for index in range(steps + 1):
        t = index / steps
        x = int(round(ax + (bx - ax) * t))
        y = int(round(ay + (by - ay) * t))
        for offset, step in ((0, CRATE_TOP), (1, CRATE_SIDE)):
            iy = y + offset
            if 0 <= x < width and 0 <= iy < height:
                px[x, iy] = _tone(ramp, step, x, iy)


def _crate_iron(px, size: tuple[int, int], box: tuple) -> None:
    """Steel brackets on the three visible corners.

    Corner-only, never a full frame: what a bracket is FOR is the corner, and
    plating the edges as well turns a wooden crate into a metal one, which is a
    different object and belongs on a different row of the sheet.

    IRON READS AGAINST THE WOOD IT IS BOLTED TO, NOT AGAINST THE FRAME, and
    that is why there is no single step for it here. The first cut ran the
    straps at STEEL 4 on every corner, which is lighter AND cooler than every
    plank tone on the sheet, so eight brackets came out as pale blue tape and
    the crate stopped being wooden. What a strap actually does is go DARK on
    the plane the key light is on and LIGHT on the plane in shade — one step
    clear of the wood in whichever direction the wood is not — and §14 gives
    painted metal a 1-2px streak for its specular, not the whole part.
    """
    width, height = size
    fx, _, lw, rw, tall = box
    reach = max(2, int(round(tall * 0.24)))
    for corner in (fx, fx - lw + 1, fx + rw - 1):
        x = int(round(corner))
        if not 0 <= x < width:
            continue
        contact, lid, _ = _crate_edges(box, x)
        gy, ly = int(round(contact)), int(round(lid))
        near = x <= fx
        # Against CRATE_FRONT (3) go under it; against CRATE_SIDE (1) go over.
        step = 2 if near else 3
        rows = list(range(ly + 1, ly + 1 + reach)) + list(range(gy - reach + 1, gy + 1))
        for y in rows:
            if ly + 1 <= y <= gy and 0 <= y < height and px[x, y][3]:
                px[x, y] = _tone(STEEL, step, x, y)
        # One row PROUD of the lid. A bracket wraps the corner and stands a
        # little above it, and those three tabs are the whole reason this
        # crate's black silhouette is not the same hexagon as the other seven.
        # They stand against the ground rather than against a plank, so they
        # are the one place the strap is allowed its catch of light.
        for y in (ly, ly - 1):
            if 0 <= y < height:
                px[x, y] = _tone(STEEL, 4 if near else 3, x, y)


def _crate_rust(px, size: tuple[int, int], amount: float, salt: int) -> None:
    """Rot the STEEL, and only the steel.

    Rust scattered over the whole sprite is what the first pass did and it was
    wrong twice: it put orange speckle on wood, which does not rust, and it put
    it there as single pixels, which §5 calls noise rather than texture. Rust
    eats iron, so the pass reads the pixel it is standing on and moves it from
    one ramp to the other at the SAME step — the bracket keeps its place in the
    light and only changes what it is made of.
    """
    width, height = size
    steel = {tone: index for index, tone in enumerate(STEEL)}
    for y in range(height):
        for x in range(width):
            index = steel.get(px[x, y])
            if index is None:
                continue
            if hash01(x // 2, y // 2, salt) < amount:
                px[x, y] = RUST[min(index, len(RUST) - 1)]


def _crate_moss(px, size: tuple[int, int], faces: dict, amount: float,
                salt: int) -> None:
    """Wet growth, in clumps, and never on the lit wall.

    Moss grows where the water sits and the sun does not, so it takes the top
    plane and the wall turned away from the key and leaves the other one alone
    — which is also what stops it flattening the plane break it is sitting on.
    The roll is on a 2x2 grid rather than per pixel: a single mossy pixel is a
    stuck pixel, and §5 puts the minimum meaningful cluster at 2x2.
    """
    for (x, y), face in faces.items():
        if face == "front" or not px[x, y][3]:
            continue
        if hash01(x // 2, y // 2, salt) < amount:
            px[x, y] = _tone(MOSS, 3 if face == "top" else 1, x, y, 0.14, salt + 2)


def _crate_debris(px, size: tuple[int, int], box: tuple, ramp: Ramp,
                  count: int, salt: int) -> None:
    """Splinters at the foot, breaking the join between silhouette and shadow.

    §19: an object whose outline and whose shadow are two concentric shapes
    looks stamped on. Two or three chips of the same wood lying outside the
    footprint are the cheapest way to break that, and on a BREAK object they
    also read forward — this one has been hit before.
    """
    width, height = size
    fx, fy, lw, rw, _ = box
    for index in range(count):
        side = -1 if hash01(salt, index, 443) < 0.5 else 1
        reach = (lw if side < 0 else rw) * (0.86 + hash01(salt, index, 447) * 0.34)
        x = int(round(fx + side * reach))
        # Held near the NEAR corner's own floor row rather than on the contact
        # slope extended past the box: that slope is the bottom of a wall, and
        # a chip riding it lands halfway up the sprite with nothing under it.
        y = int(round(fy - hash01(salt, index, 451) * 1.6))
        run = 1 + int(hash01(salt, index, 449) * 2)
        for offset in range(run + 1):
            ix = x + side * offset
            if 0 <= ix < width and 0 <= y < height and px[ix, y][3] == 0:
                px[ix, y] = _tone(ramp, 1 if offset else 2, ix, y)


def _crate_contact(px, size: tuple[int, int], ramp: Ramp) -> None:
    """The darkest band on the sprite, inside its own bottom edge.

    Run per column rather than across a row, because the contact line of a
    rhombic footprint is not level — it falls away from the near corner at the
    camera slope, and a straight dark row under a box standing on a diagonal is
    a shadow belonging to a different projection.
    """
    width, height = size
    for x in range(width):
        column = [y for y in range(height) if px[x, y][3]]
        if not column:
            continue
        floor = max(column)
        px[x, floor] = _tone(ramp, 0, x, floor)
        if floor - 1 in column:
            px[x, floor - 1] = _tone(ramp, 1, x, floor - 1)


def make_crate(width: int, height: int, kind: str) -> Image.Image:
    """One of the eight crates, by name. Deterministic: no `rng` anywhere.

    Every other prop in this file takes a `random.Random` and spends it on
    grain. A crate does not, because a crate is a MANUFACTURED object: what
    separates two of them is which recipe they were built from and what has
    happened to them since, and a per-run roll on top of that only guarantees
    the sheet comes out different on two machines.
    """
    recipe = CRATE_RECIPES[kind]
    size = (width, height)
    img = Image.new("RGBA", size, TRANSPARENT)
    px = img.load()
    salt = 461 + sum(ord(letter) for letter in kind)

    boards = recipe.get("boards", CRATE_BOARDS)
    grain = recipe.get("grain", 0.0)
    boxes = [_crate_box(width, height, spec) for spec in recipe["boxes"]]
    faces: dict[tuple[int, int], str] = {}

    for index, box in enumerate(boxes):
        below = set(faces) if index else set()
        _crate_hull(px, size, box, PLANK, boards=boards, grain=grain,
                    salt=salt + index, faces=faces)
        _crate_lip(px, size, box, PLANK)
        _crate_posts(px, size, box, PLANK)
        if index == 0:
            _crate_brace(px, size, box, PLANK, recipe.get("brace", ""))
        # Seam occlusion: whatever the new box lands against loses a step, so a
        # stack reads as one box standing ON another rather than as two
        # outlines sharing an edge (§10, §18).
        fresh = set(faces) - below
        for x, y in below:
            if any((x + dx, y + dy) in fresh
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = _tone(PLANK, 0, x, y)

    body = boxes[0]
    rope_band = recipe.get("band_ramp") == "rope"
    band_ramp = ROPE if rope_band else STEEL
    band_steps = BAND_ROPE_STEPS if rope_band else BAND_STEEL_STEPS
    for at in recipe.get("bands", ()):
        _crate_band(px, size, body, band_ramp, at, bolts=recipe.get("iron", False),
                    steps=band_steps)
    if recipe.get("iron"):
        _crate_iron(px, size, body)
    if recipe.get("rope"):
        # Over the LID, and along the axis the boards do NOT run on, so it
        # crosses the courses instead of lying in one. A lashing parallel to
        # the planks is a lashing you cannot see. It starts on the near-left
        # edge and walks the far diagonal, and it stops when the face map says
        # it has left the top plane — following the geometry off the lid and
        # down the wall would draw a rope no knot could hold.
        fx, _, lw, _, _ = body
        for along in (0.34, 0.72):
            start = fx - lw + lw * along
            base = _crate_edges(body, start)[1] - 1
            for step in range(width):
                x, y = int(round(start + step)), int(round(base - step * CRATE_SLOPE))
                if faces.get((x, y)) != "top":
                    break
                px[x, y] = _tone(ROPE, 4, x, y)

    if recipe.get("gaps"):
        _crate_gaps(px, size, faces, PLANK, boards, recipe["gaps"])
    for spec in recipe.get("holes", ()):
        _crate_hole(px, size, body, PLANK, spec)
    for spec in recipe.get("planks", ()):
        _crate_plank(px, size, PLANK, spec)
    if recipe.get("splinter"):
        _crate_splinter(px, size, body, PLANK, recipe["splinter"], salt)
    if recipe.get("sag"):
        _crate_sag(px, size, body, PLANK, recipe["sag"])
    if recipe.get("bite"):
        _crate_bite(px, size, body, PLANK, *recipe["bite"])

    if recipe.get("rust"):
        _crate_rust(px, size, recipe["rust"], salt + 3)
    if recipe.get("moss"):
        _crate_moss(px, size, faces, recipe["moss"], salt + 5)
    if recipe.get("debris"):
        _crate_debris(px, size, body, PLANK, recipe["debris"], salt)

    _crate_contact(px, size, PLANK)
    outline(img, OUTLINE_WOOD)
    _ground_dark(img, rows=1, drop=0.78)
    return img


# --- boxes: the things you open ---------------------------------------------


def make_box(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """`kind`: 0 supply crate, 1 ammo case, 2 plastic tote. `frame` swings the lid.

    The lid hinges at the BACK and falls away from the camera, so an open box
    is a shallower silhouette with the inside catching what little light there
    is. Hinging it forward would hide the interior behind the lid, and the
    interior is the entire reason the animation exists.

    THE BOX IS A BOX NOW. It used to be a front elevation — a rectangle of
    courses with a value ramp across it and a slab that slid up the frame for
    a lid — which gave the sheet no top surface at all, on an object the
    camera looks down at from sixty degrees. It is now `box` plus `cap`: three
    real planes, and a lid that is the same rhombus as the top face, SQUASHED
    as it swings so it foreshortens toward a line instead of levitating.

    The interior is what the lid uncovers, and it is drawn as its own box —
    the far inner wall at the shade step, the floor two steps under that —
    rather than as a black hole. A hole is a hole in the sprite; two dim
    planes are a container you are looking into.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    body = PLANK if kind == 0 else (OCHRE if kind == 1 else STEEL)
    trim = PLANK_DARK if kind == 0 else (STEEL if kind == 1 else CHROME)

    # UNEQUAL, and the crate sheet says why: a box with lw == rw has a diamond
    # for a footprint, and a diamond reads as a gem rather than as a container.
    lw, rw = width * 0.38, width * 0.30
    tall = height * 0.40
    base = ground - 1.0

    box(px, size, cx, base, lw, rw, tall, body)

    # Course seams down the near wall, one step under it. They run with the
    # boards and stop at the corner, so the wall reads as planks rather than
    # as a panel — and they never cross the top face, which has its own grain.
    for course in (0.34, 0.68):
        for x in range(int(cx - lw), int(cx) + 1):
            if not 0 <= x < width:
                continue
            contact = base - abs(x - cx) * SLOPE
            y = int(round(contact - tall * course))
            if 0 <= y < height and px[x, y][3]:
                px[x, y] = tone(body, FRONT - 1, x, y)

    if kind == 0:
        # Diagonal brace across the near wall. One mark, and it says "crate".
        for step in range(int(tall)):
            ix = int(cx - lw + step * lw / max(tall, 1))
            iy = int(base - abs(ix - cx) * SLOPE - step)
            if 0 <= ix < width and 0 <= iy < height and px[ix, iy][3]:
                px[ix, iy] = tone(trim, FRONT, ix, iy)
    elif kind == 1:
        # Two latches on the near wall: an ammo case is a box with hardware.
        for lx in (int(cx - lw * 0.55), int(cx - lw * 0.05)):
            for step in range(2):
                y = int(base - abs(lx - cx) * SLOPE - tall * 0.55) + step
                if 0 <= lx < width and 0 <= y < height and px[lx, y][3]:
                    px[lx, y] = tone(trim, TOP, lx, y)
    else:
        # Ribbed sides. A tote is stiffened plastic and the ribs are its tell.
        for x in range(int(cx - lw), int(cx + rw) + 1, 3):
            if not 0 <= x < width:
                continue
            contact = base - abs(x - cx) * SLOPE
            for y in range(int(contact - tall) + 1, int(contact)):
                if 0 <= y < height and px[x, y][3]:
                    px[x, y] = tone(trim, (FRONT if x <= cx else SIDE) - 1, x, y)

    # THE INSIDE, uncovered as the lid goes over. Far wall then floor, both on
    # the rhombus so the opening lies in the same plane the lid came off.
    if open_t > 0.05:
        # A RIM SURVIVES. The opening is inset by two pixels all round, so the
        # top face is still a visible frame of lit wood around it — an opening
        # cut edge to edge is a hole in the sprite, and a hole has no
        # thickness. Inside: the far wall one step over the floor, both on the
        # same rhombus the lid came off, so you are looking INTO the box
        # rather than at a black shape sitting in it.
        cap(px, size, cx, base - tall, lw - 2, rw - 2, PLANK_DARK, 3)
        cap(px, size, cx, base - tall + 1.0 + open_t, (lw - 2) * 0.80,
            (rw - 2) * 0.80, PLANK_DARK, 1)
        _spark(px, int(cx - lw + 2), int(base - tall - 1), int(cx + rw - 2),
               int(base - tall + 2), EMBER if kind != 2 else COLD, open_t,
               57 + kind, width, height)

    # THE LID. Same rhombus as the top face, lifted off the rim and tipped
    # back — and squashed as it goes, which is the only perspective cue a
    # 16-pixel sprite can afford.
    lift = open_t * (tall * 0.45 + 1.5)
    # The squash floors at a third rather than at a sliver: a lid that
    # foreshortens all the way to a line stops being a lid and starts being a
    # scratch above the box.
    squash = max(0.34, 1.0 - open_t * 0.72)
    cap(px, size, cx, base - tall - lift, lw, rw, body, TOP, squash=squash)
    if open_t > 0.05:
        # The hinge stays welded to the back edge of the body the whole way.
        hinge_y = int(round(base - tall - (lw + rw) * SLOPE))
        for x in (int(cx - lw + 1), int(cx + rw - 1)):
            _line(px, x, int(round(base - tall - lift)), x, hinge_y,
                  trim, 0.42, width, height)

    shadow(img, cx, base + 0.5, lw * 1.1, lw * SLOPE * 0.8)
    outline(img, OUTLINE_WOOD if kind != 2 else OUTLINE_COLD)
    return img



def make_chest(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """`kind`: 0 iron-bound chest, 1 strongbox. Slower, taller, always paying.

    Deliberately the ONE object in the forest with a curved lid. Everything
    else here is a flat top — a box, a bin, a bonnet — so the dome is doing
    the same job a rarity colour does in the HUD: it says, from across a dark
    clearing and before you can read anything else, that this one is different.

    Which is exactly what the old drawing threw away. A bulged rectangle drawn
    front-on has a curve in its OUTLINE and a flat face under it, so the dome
    was a silhouette trick on an object with no top — and the one prop whose
    whole job is to look unlike the others looked like a box with a bump. It
    is now `box` for the chest and `dome` for the lid: the curve is a stack of
    real rhombi the camera passes over, and the straps run down the near wall
    and over the crown instead of down a picture of one.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    body = PLANK if kind == 0 else STEEL
    bandmetal = BRASS if kind == 0 else CHROME

    lw, rw = width * 0.40, width * 0.31
    tall = height * 0.32
    base = ground - 1.0
    rim = base - tall

    box(px, size, cx, base, lw, rw, tall, body)

    # Iron straps down the near wall. They follow the contact slope, so they
    # stay vertical on the object rather than on the frame.
    for offset in (-0.60, -0.12):
        bx = int(round(cx + offset * lw))
        if not 0 <= bx < width:
            continue
        contact = base - abs(bx - cx) * SLOPE
        for y in range(int(contact - tall), int(contact) + 1):
            if 0 <= y < height and px[bx, y][3]:
                px[bx, y] = tone(bandmetal, FRONT, bx, y)
    # The lock plate, on the near wall between them.
    for y in range(int(rim + tall * 0.45), int(rim + tall * 0.45) + 2):
        for x in range(int(cx - 2), int(cx + 1)):
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = tone(bandmetal, TOP, x, y)

    # THE HOLLOW, and it grows warm rather than just dark: a chest is the one
    # container guaranteed to be holding something, and the light coming up
    # out of it is the promise being made before the lid clears.
    if open_t > 0.04:
        cap(px, size, cx, rim, lw - 2, rw - 2, PLANK_DARK, 3)
        cap(px, size, cx, rim + 1.0 + open_t, (lw - 2) * 0.78, (rw - 2) * 0.78,
            PLANK_DARK, 1)
        _spark(px, int(cx - lw + 2), int(rim - 1), int(cx + rw - 2), int(rim + 2),
               EMBER, open_t, 73 + kind, width, height)

    # THE DOMED LID, hinged at the back and rolling up and over. It keeps its
    # curve the whole way — a dome that flattens as it opens reads as a lid
    # made of something soft.
    lift = open_t * (tall * 0.75 + 2.5)
    squash = max(0.30, 1.0 - open_t * 0.74)
    rise = max(1.5, (height - tall) * 0.20 * (1.0 - open_t * 0.30))
    lid_lw, lid_rw = lw * squash + lw * (1 - squash) * 0.55, rw
    dome(px, size, cx, rim - lift, lid_lw, lid_rw, rise, body)
    # A strap over the crown, so the lid is bound to the same chest the walls
    # are — the one detail that stops it reading as a separate object in the
    # frames where it has left the rim.
    crown = int(round(rim - lift - rise * 0.55))
    for x in range(int(cx - 1), int(cx + 2)):
        for y in (crown, crown + 1):
            if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                px[x, y] = tone(bandmetal, TOP, x, y)

    shadow(img, cx, base + 0.5, lw * 1.1, lw * SLOPE * 0.8)
    outline(img, OUTLINE_WOOD if kind == 0 else OUTLINE_COLD)
    return img


def make_stash(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """Small containers. `kind`: 0 mailbox, 1 suitcase, 2 freezer, 3 bin, 4 toolbox.

    These are the objects that make the map read as a place people commuted
    through rather than a place they fought in. A mailbox on a forest road is
    a question — there was a house here once — and it costs one 16-pixel sheet
    to ask it.

    ALL FIVE ARE THE SAME TWO SOLIDS. Four are boxes and one is a cylinder,
    and what separates them is PROPORTION and where the lid is, not detail —
    at sixteen pixels a hinge is one dark pixel and a handle is two, so the
    silhouette has to do all of it. The old sheet drew five flat rectangles in
    five colours, which made them read as five swatches; drawn as solids the
    freezer is unmistakably taller than it is deep and the suitcase
    unmistakably the other way round, and the colour stops carrying the load.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)
    cx = (width - 1) / 2.0
    ground = height - 1
    base = ground - 1.0
    open_t = _ease(frame / max(frames - 1, 1))

    def lid_open(fx, rim, lw, rw, ramp, drop=1.0):
        """The shared opening: a rim, an inside, and a lid tipped back off it."""
        cap(px, size, fx, rim, max(1.0, lw - 1.5), max(1.0, rw - 1.5), PLANK_DARK, 3)
        cap(px, size, fx, rim + drop + open_t, max(1.0, (lw - 1.5) * 0.78),
            max(1.0, (rw - 1.5) * 0.78), PLANK_DARK, 1)
        lift = open_t * 3.4
        squash = max(0.34, 1.0 - open_t * 0.72)
        cap(px, size, fx, rim - lift, lw, rw, ramp, TOP, squash=squash)

    if kind == 0:
        # MAILBOX: a drum on a post, and the drum is a cylinder lying along
        # the axis so its door faces the camera. The one prop on this sheet
        # that is not a box, which is exactly why it reads at a glance.
        post_h = height * 0.46
        box(px, size, cx, base, 1.2, 1.2, post_h, PLANK)
        axis = base - post_h - 2.2
        billet(px, size, cx - width * 0.30, cx + width * 0.30, axis, 2.6, STEEL,
               cap=False)
        # THE DOOR, HINGED AT THE BOTTOM, FALLING TOWARD THE CAMERA. Every
        # other container on this sheet lifts a lid off a rim; a mailbox is
        # the one that opens on its END, and it is the only reason the drum is
        # drawn lying along the axis in the first place. The first cut of this
        # only swapped the door's colour at a threshold, which is not an
        # animation — the frames all had the same silhouette and the object
        # read as closed at every step of its own opening.
        #
        # The swing is one angle. What is still STANDING above the hinge is
        # `cos`, what has FALLEN toward the camera below it is `sin`, and the
        # fallen part is multiplied by the camera slope because a flap
        # pointing at the viewer is the one thing on this sheet seen almost
        # end-on. That is what makes the door foreshorten as it drops instead
        # of sliding down the frame at full height.
        end_x = cx - width * 0.30
        r = 2.6
        hinge = axis + r
        theta = open_t * math.pi * 0.55
        above = 2 * r * max(0.0, math.cos(theta))
        below = 2 * r * math.sin(theta) * SLOPE

        # The mouth behind it: dark at the back, one step over at the lip, so
        # an open mailbox is a tube you are looking into rather than a notch
        # bitten out of the drum.
        if open_t > 0.06:
            for y in range(int(round(axis - r)), int(round(axis + r)) + 1):
                for x in range(int(round(end_x)), int(round(end_x + 2.2)) + 1):
                    if not (0 <= x < width and 0 <= y < height) or not px[x, y][3]:
                        continue
                    # Step 3 at the lip, 1 at the back. Step 0 on this ramp is
                    # a hair off the outline, so a mouth drawn on it is the
                    # same colour as the line round the sprite and the drum
                    # reads as having a bite taken out of it rather than an
                    # inside — the same mistake the collapsed crate made.
                    edge = abs(y - axis) > r - 1.0
                    px[x, y] = tone(PLANK_DARK, 3 if edge else 1, x, y)

        # The door itself: two columns at the end of the drum, spanning from
        # whatever is left standing down to whatever has fallen.
        for x in range(int(round(end_x)), int(round(end_x + 1.6)) + 1):
            for y in range(int(round(hinge - above)), int(round(hinge + below)) + 1):
                if not (0 <= x < width and 0 <= y < height):
                    continue
                # The face of the door catches the key while it is upright and
                # turns away as it goes over — one step down once it is past
                # the hinge, which is the whole of the lighting on it.
                px[x, y] = tone(STEEL, TOP if y < hinge else FRONT, x, y)
        # The catch, on the lip the door swings off.
        catch_y = int(round(hinge - above)) - 1
        if open_t < 0.5 and 0 <= int(end_x) < width and 0 <= catch_y < height:
            px[int(end_x), catch_y] = tone(CHROME, TOP, int(end_x), catch_y)
        # The flag: the one warm pixel pair, and the only thing that says a
        # mailbox rather than a canister.
        fx_ = int(cx + width * 0.26)
        for y in range(int(axis - 5), int(axis - 2)):
            if 0 <= fx_ < width and 0 <= y < height:
                px[fx_, y] = tone(HAZARD, TOP, fx_, y)
    elif kind == 1:
        # SUITCASE: wide, shallow, lying down. Half the height of the freezer
        # and twice its footprint — that inversion is the whole read.
        lw, rw = width * 0.42, width * 0.33
        tall = height * 0.22
        box(px, size, cx, base, lw, rw, tall, LEATHER)
        for offset in (-0.50, 0.10):
            bx = int(round(cx + offset * lw))
            if not 0 <= bx < width:
                continue
            contact = base - abs(bx - cx) * SLOPE
            for y in range(int(contact - tall), int(contact) + 1):
                if 0 <= y < height and px[bx, y][3]:
                    px[bx, y] = tone(BRASS, FRONT, bx, y)
        lid_open(cx, base - tall, lw, rw, LEATHER)
    elif kind == 2:
        # FREEZER: the tallest thing on the sheet and a solid white slab.
        lw, rw = width * 0.35, width * 0.27
        tall = height * 0.48
        box(px, size, cx, base, lw, rw, tall, BONE)
        # A seam across the near wall: the door line, one step under it.
        for x in range(int(cx - lw), int(cx) + 1):
            if not 0 <= x < width:
                continue
            y = int(round(base - abs(x - cx) * SLOPE - tall * 0.62))
            if 0 <= y < height and px[x, y][3]:
                px[x, y] = tone(BONE, FRONT - 1, x, y)
        lid_open(cx, base - tall, lw, rw, BONE)
    elif kind == 3:
        # BIN: a cylinder with a lid. Round where everything beside it is
        # square, which is the cheapest way to make one of five read first.
        rx = width * 0.30
        ry = max(1.5, rx * SLOPE)
        tall = height * 0.40
        rim = base - tall
        for y in range(int(rim), int(base) + 1):
            for x in range(int(round(cx - rx)), int(round(cx + rx)) + 1):
                if not (0 <= x < width and 0 <= y < height):
                    continue
                across = (x - cx) / max(rx, 0.5)
                px[x, y] = tone(MOSS, FRONT if across < 0.30 else (SIDE if across < 0.88 else 0), x, y)
        # Ribs round the drum, following the same break as the wall.
        for hoop in (0.30, 0.66):
            y = int(rim + tall * hoop)
            for x in range(int(round(cx - rx)), int(round(cx + rx)) + 1):
                if 0 <= x < width and 0 <= y < height and px[x, y][3]:
                    across = (x - cx) / max(rx, 0.5)
                    px[x, y] = tone(MOSS, (FRONT if across < 0.30 else SIDE) - 1, x, y)
        lid_open(cx, rim, rx, rx, MOSS, drop=0.8)
    else:
        # TOOLBOX: small, wide, with a handle over it — the only stash whose
        # silhouette leaves the box, and at this size a handle is a bridge of
        # three pixels standing clear of the lid.
        lw, rw = width * 0.36, width * 0.28
        tall = height * 0.24
        box(px, size, cx, base, lw, rw, tall, RUST)
        lid_open(cx, base - tall, lw, rw, RUST)
        arch = int(round(base - tall - 3.5 - open_t * 3.4))
        for x in range(int(cx - lw * 0.5), int(cx + rw * 0.5) + 1):
            y = arch + (1 if abs(x - cx) > lw * 0.32 else 0)
            if 0 <= x < width and 0 <= y < height:
                px[x, y] = tone(CHROME, TOP, x, y)

    shadow(img, cx, base + 0.5, width * 0.34, width * 0.34 * SLOPE * 0.9)
    outline(img, OUTLINE_COLD if kind in (0, 2, 3) else OUTLINE_WOOD)
    return img


def _bar(px, x0: int, y: int, x1: int, width: int, height: int,
         ramps: tuple[Ramp, Ramp]) -> None:
    """A roof light bar: alternating pixels of two signal colours, UNLIT.

    Unlit matters. A flashing bar would be the brightest moving thing on a
    dark map and would read as an active vehicle, which is the one thing none
    of these are. What it gets instead is a dark housing under it, so the two
    dull signal pixels read as lenses in a fitting rather than as a mistake in
    the roofline.
    """
    for index, x in enumerate(range(x0, x1 + 1)):
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = pick(ramps[(index // 2) % 2], 0.42, x, y)
        if 0 <= x < width and 0 <= y + 1 < height:
            px[x, y + 1] = pick(TYRE, 0.6, x, y + 1)


def _profile_y(profile, fx: float) -> float:
    """The silhouette's top edge at one column, in frame fractions."""
    if fx <= profile[0][0]:
        return profile[0][1]
    if fx >= profile[-1][0]:
        return profile[-1][1]
    for (ax, ay), (bx, by) in zip(profile, profile[1:]):
        if ax <= fx <= bx:
            t = (fx - ax) / max(bx - ax, 1e-6)
            return ay + (by - ay) * t
    return profile[-1][1]


def _lid(px, x0: int, x1: int, y: int, lift: float, hinge_right: bool,
         ramp: Ramp, salt: int, width: int, height: int, thickness: int = 3) -> None:
    """A panel lifted off its seal, TILTED around the edge it is hinged on.

    The old one slid a flat plate straight up, which reads as a piece of the
    car floating. A lid that rises at its free edge and stays put at its
    hinge is the only thing in the frame that has to say "this is attached and
    it swung", and the taper — thinner at the top of the swing — is what keeps
    it from reading as a second, smaller vehicle.
    """
    span = max(x1 - x0, 1)
    for x in range(x0, x1 + 1):
        t = (x1 - x) / span if hinge_right else (x - x0) / span
        top = int(round(y - lift * t))
        for offset in range(thickness):
            yy = top + offset
            if 0 <= x < width and 0 <= yy < height:
                shade = 0.90 if offset == 0 else 0.52 - offset * 0.14
                px[x, yy] = pick(ramp, shade + (hash01(x, yy, salt) - 0.5) * 0.10, x, yy)


# --- vehicles ---------------------------------------------------------------

VEHICLE_PAINT = (PAINT_SEDAN, PAINT_VAN, PAINT_AMBU, PAINT_POLICE, PAINT_TRUCK, PAINT_BUS)

#: THE PROFILE IS THE VEHICLE. Each row is the upper silhouette of one kind as
#: control points in fractions of the frame â€” left to right, y down from the
#: top â€” interpolated per column into the line the body is filled down from.
#:
#: This replaced six stacked rectangles, and the difference is the whole read.
#: A car and a van drawn as boxes are the same object in two palettes: you
#: cannot tell them apart at the edge of a lantern, so the map stops being a
#: place with an ambulance in it and becomes a map with dark blocks on it. A
#: bonnet that slopes, a windscreen that rakes back and a roof that stops
#: before the boot is a SEDAN from as far away as the pixels survive â€” and the
#: ambulance's box roof standing proud of its cab is legible at the same range,
#: which is what makes detouring for the medical drop table a decision.
VEHICLE_PROFILE: tuple[tuple[tuple[float, float], ...], ...] = (
    # 0 sedan: long bonnet, raked screen, roof over the middle third, and a
    #   BOOT â€” a flat deck behind the cabin rather than a slope to the tail.
    ((0.03, 0.74), (0.09, 0.70), (0.22, 0.65), (0.30, 0.45), (0.38, 0.35),
     (0.60, 0.34), (0.68, 0.50), (0.74, 0.60), (0.93, 0.61), (0.98, 0.73)),
    # 1 van: stub nose, then a wall. Everything behind the cab is cargo.
    ((0.03, 0.76), (0.07, 0.60), (0.11, 0.30), (0.16, 0.22), (0.94, 0.22),
     (0.97, 0.30)),
    # 2 ambulance: the box body stands PROUD of the cab roof. That step is the
    #   silhouette tell, and it is worth more than the red cross because it
    #   survives to a distance where four pixels of paint do not.
    ((0.03, 0.74), (0.07, 0.58), (0.12, 0.30), (0.17, 0.26), (0.30, 0.26),
     (0.33, 0.15), (0.96, 0.15), (0.98, 0.24)),
    # 3 cruiser: a sedan stretched and dropped, with a bar across the roof.
    #   The boot has to run FLAT to the tail. Sloping it straight off the roof
    #   gave a wedge, and a wedge is not a car â€” the notch behind the cabin is
    #   the whole reason a saloon reads as one from the side.
    ((0.02, 0.72), (0.10, 0.67), (0.24, 0.62), (0.31, 0.43), (0.38, 0.33),
     (0.64, 0.32), (0.71, 0.50), (0.78, 0.58), (0.94, 0.59), (0.99, 0.70)),
    # 4 lorry: a tall cab, a drop, and a flat bed with a rail along it.
    ((0.02, 0.64), (0.05, 0.32), (0.09, 0.22), (0.27, 0.22), (0.29, 0.50),
     (0.33, 0.44), (0.97, 0.44), (0.99, 0.52)),
    # 5 bus: one long box, the tallest thing in the woods that is not a tree.
    ((0.02, 0.26), (0.04, 0.13), (0.10, 0.09), (0.92, 0.09), (0.97, 0.13),
     (0.99, 0.26)),
)

#: Wheel centres, in fractions of the frame width. Three entries is a lorry or
#: a bus â€” the extra axle is most of what says WEIGHT at this size.
VEHICLE_WHEELS: tuple[tuple[float, ...], ...] = (
    (0.20, 0.79), (0.19, 0.81), (0.18, 0.82), (0.19, 0.80),
    (0.13, 0.72, 0.85), (0.14, 0.74, 0.87),
)

#: Glazing, per kind: (x0, x1, y0, y1) in frame fractions. Punched into the
#: body after it is filled, so a window is a HOLE in the paint rather than a
#: rectangle sitting on top of it â€” which is the difference between a car with
#: windows and a car with stickers.
VEHICLE_GLASS: tuple[tuple[tuple[float, float, float, float], ...], ...] = (
    ((0.33, 0.46, 0.40, 0.59), (0.49, 0.62, 0.39, 0.57)),
    ((0.10, 0.21, 0.31, 0.47), (0.79, 0.86, 0.27, 0.42), (0.87, 0.93, 0.27, 0.42)),
    ((0.11, 0.22, 0.33, 0.49), (0.42, 0.55, 0.20, 0.34), (0.86, 0.94, 0.20, 0.34)),
    ((0.34, 0.47, 0.38, 0.57), (0.50, 0.63, 0.37, 0.55)),
    ((0.06, 0.17, 0.27, 0.42),),
    ((0.06, 0.15, 0.13, 0.32), (0.19, 0.29, 0.13, 0.32), (0.33, 0.43, 0.13, 0.32),
     (0.47, 0.57, 0.13, 0.32), (0.61, 0.71, 0.13, 0.32), (0.75, 0.88, 0.13, 0.32)),
)

#: THE COMPARTMENT: (x0, x1) in frame fractions, and which edge the lid is
#: hinged on. It is always the part of that vehicle somebody would still be
#: packed into or trapped behind â€” a bonnet on the car that died on the road,
#: the tailgate on the vans, the bed on the lorry, the luggage bay on a bus.
VEHICLE_PANEL: tuple[tuple[float, float, bool], ...] = (
    (0.05, 0.26, True),     # sedan bonnet, hinged at the screen
    (0.76, 0.96, True),     # van tailgate, hinged at the roof
    (0.78, 0.96, True),     # ambulance rear doors
    (0.04, 0.25, True),     # cruiser bonnet
    (0.40, 0.68, False),    # lorry bed hatch
    (0.30, 0.52, False),    # bus luggage bay
)


def _bar(px, x0: int, y: int, x1: int, width: int, height: int,
         ramps: tuple[Ramp, Ramp]) -> None:
    """A roof light bar: alternating pixels of two signal colours, UNLIT.

    Unlit matters. A flashing bar would be the brightest moving thing on a
    dark map and would read as an active vehicle, which is the one thing none
    of these are. What it gets instead is a dark housing under it, so the two
    dull signal pixels read as lenses in a fitting rather than as a mistake in
    the roofline.
    """
    for index, x in enumerate(range(x0, x1 + 1)):
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = pick(ramps[(index // 2) % 2], 0.42, x, y)
        if 0 <= x < width and 0 <= y + 1 < height:
            px[x, y + 1] = pick(TYRE, 0.6, x, y + 1)


def _profile_y(profile, fx: float) -> float:
    """The silhouette's top edge at one column, in frame fractions."""
    if fx <= profile[0][0]:
        return profile[0][1]
    if fx >= profile[-1][0]:
        return profile[-1][1]
    for (ax, ay), (bx, by) in zip(profile, profile[1:]):
        if ax <= fx <= bx:
            t = (fx - ax) / max(bx - ax, 1e-6)
            return ay + (by - ay) * t
    return profile[-1][1]


def _lid(px, x0: int, x1: int, y: int, lift: float, hinge_right: bool,
         ramp: Ramp, salt: int, width: int, height: int, thickness: int = 3) -> None:
    """A panel lifted off its seal, TILTED around the edge it is hinged on.

    The old one slid a flat plate straight up, which reads as a piece of the
    car floating. A lid that rises at its free edge and stays put at its
    hinge is the only thing in the frame that has to say "this is attached and
    it swung", and the taper â€” thinner at the top of the swing â€” is what keeps
    it from reading as a second, smaller vehicle.
    """
    span = max(x1 - x0, 1)
    for x in range(x0, x1 + 1):
        t = (x1 - x) / span if hinge_right else (x - x0) / span
        top = int(round(y - lift * t))
        for offset in range(thickness):
            yy = top + offset
            if 0 <= x < width and 0 <= yy < height:
                shade = 0.90 if offset == 0 else 0.52 - offset * 0.14
                px[x, yy] = pick(ramp, shade + (hash01(x, yy, salt) - 0.5) * 0.10, x, yy)

def make_vehicle(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """A dead vehicle, seen from the side and slightly above. `frame` opens it.

    THE SILHOUETTE IS THE WHOLE ASSET, and it is drawn from `VEHICLE_PROFILE`
    rather than assembled out of two rectangles. At this size nobody reads a
    badge; what a player reads across a dark clearing is a long low mass with
    two black holes under it, and then the ROOFLINE tells them which one it is
    — a bonnet that slopes into a raked screen is a car, a wall behind a stub
    nose is a van, a box standing proud of its cab is an ambulance, a cab with
    a bed behind it is a lorry, one long box with six windows is a bus.

    THE SECOND READ IS THAT IT DIED HERE. Every one of these carries rust up
    from the sill, moss on the shadowed bottom rows, one flat tyre and a
    smashed window, because a clean car is a car somebody parked, and a map
    full of parked cars is a map that has not been abandoned. None of that
    costs a frame: it is four passes over pixels the body already put down.

    What opens is the compartment that vehicle would actually have somebody
    still in it or still packed. It lifts from its hinge and the black
    underneath is the reward — or the warning.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))
    paint = VEHICLE_PAINT[kind % len(VEHICLE_PAINT)]
    profile = VEHICLE_PROFILE[kind % len(VEHICLE_PROFILE)]

    sill = int(height * 0.87)
    axle = height * 0.885
    radius = max(2.4, height * 0.105)
    body_x0 = int(width * profile[0][0])
    body_x1 = int(width * profile[-1][0])

    # 1. THE BODY, EXTRUDED. This is the change that made a vehicle a vehicle.
    #    It used to be one column of paint per x, ramped from the profile down
    #    to the sill and dithered — a SIDE ELEVATION, with no roof, no bonnet
    #    and no windscreen, on the largest object in the game and the one the
    #    camera looks down at hardest. What a profile actually describes is
    #    the edge where the roof meets the flank, so sweeping it back along
    #    the camera slope generates both surfaces at once: everything the
    #    sweep leaves standing proud along the top is roof and bonnet at the
    #    lit plane, and the last pass down is the near flank.
    #
    #    The sweep costs nothing in authoring — the six profiles are unchanged
    #    and still carry the identity — and it is the same construction the
    #    tent uses in make_scenery.py, for the same reason.
    # How far the roof runs back. A vehicle is drawn nearly side-on here, so
    # what the camera catches of the top is a STRIP — deep enough to read as
    # a surface, shallow enough that a car does not turn into a wedge. A
    # third of the frame height, which this was first, is most of the body.
    body_d = max(3, int(height * 0.14))

    #    The NEAR FLANK first, unshifted: this is the side of the vehicle the
    #    player walks past, and it stays exactly where the profile puts it.
    for x in range(body_x0, body_x1 + 1):
        top = int(round(_profile_y(profile, x / max(width - 1, 1)) * height))
        for y in range(top, sill + 1):
            if not (0 <= x < width and 0 <= y < height):
                continue
            # Two bands: the door above the waist, the rocker under it tucking
            # away from the light. Two steps apart, never one — a single step
            # is a smudge at this size and the flank goes back to a rectangle.
            t = (y - top) / max(sill - top, 1)
            px[x, y] = tone(paint, FRONT if t < 0.66 else SIDE, x, y)

    #    THE ROOF, swept back off the profile. Only the TOP extrudes: a
    #    vehicle's far flank is hidden behind its near one, so sweeping the
    #    whole silhouette shears the entire body into a parallelogram — which
    #    is what the first cut of this did. What the sweep should produce is a
    #    BAND above the profile line, and that band is the roof, the bonnet
    #    and the boot lid, in one pass, following whatever the profile says
    #    this kind's roofline does.
    #    Rasterised as a REGION, not as a swept point set. Stepping the
    #    profile back one offset at a time and plotting a pixel each time
    #    leaves holes wherever two consecutive offsets round to the same row
    #    — which came out as a checkerboard across the back of the car. For
    #    each screen column, take the highest and lowest row the sweep reaches
    #    and fill between them; the band is then solid by construction.
    for sx in range(body_x0, min(width, body_x1 + body_d + 1)):
        reach_hi, reach_lo = None, None
        for offset in range(0, body_d + 1):
            src = sx - offset
            if not body_x0 <= src <= body_x1:
                continue
            row = int(round(_profile_y(profile, src / max(width - 1, 1)) * height
                            - offset * SLOPE))
            reach_hi = row if reach_hi is None else min(reach_hi, row)
            reach_lo = row if reach_lo is None else max(reach_lo, row)
        if reach_hi is None:
            continue
        # CAPPED to the sweep's own depth. Where the profile falls steeply —
        # the back of a car, the step down from a lorry cab — the highest and
        # lowest rows the sweep touches are most of the body apart, and
        # filling between them paints the whole rear quarter as roof. The roof
        # is a surface of one thickness; the profile only says where it sits.
        reach_hi = max(reach_hi, reach_lo - body_d)
        for y in range(max(0, reach_hi), min(height, reach_lo + 1)):
            if px[sx, y][3]:
                continue
            px[sx, y] = tone(paint, TOP, sx, y)

    # 2. THE SHOULDER. One row of contact-dark where the roof turns into the
    #    flank — the fold the sweep produced needs the occlusion S10 asks for,
    #    or the two planes read as one panel with a stripe painted on it.
    for x in range(body_x0, body_x1 + 1):
        top = int(round(_profile_y(profile, x / max(width - 1, 1)) * height))
        if 0 <= x < width and 0 <= top < height and px[x, top][3]:
            px[x, top] = tone(paint, 0, x, top)

    # 3. The lit edge along the crown, one pixel per column.
    _top_light(img, paint, 0.97)

    # 4. GLASS. Punched into the paint, dark, with one specular streak each.
    #    Windows are DARK on purpose: there is nothing behind them, and a lit
    #    window on an abandoned car is a promise the map cannot keep.
    glass = VEHICLE_GLASS[kind % len(VEHICLE_GLASS)]
    belt = 0
    for index, (gx0, gx1, gy0, gy1) in enumerate(glass):
        wx0, wx1 = int(width * gx0), int(width * gx1)
        wy0, wy1 = int(height * gy0), int(height * gy1)
        belt = max(belt, wy1)
        # One window per vehicle is GONE. A hole where glass should be is the
        # single cheapest mark of violence available, and it costs no frame.
        #
        # Never the only window a vehicle has. The lorry has one, in its cab,
        # and smashing it turned the entire cab into a black notch — which
        # deletes the silhouette the profile was drawn to produce. A vehicle
        # with one pane keeps it.
        smashed = len(glass) > 1 and index == (kind % len(glass))
        for y in range(wy0, wy1 + 1):
            for x in range(wx0, wx1 + 1):
                if not (0 <= x < width and 0 <= y < height) or px[x, y][3] == 0:
                    continue
                if smashed and hash01(x, y, 301 + kind) < 0.72:
                    px[x, y] = pick(PLANK_DARK, 0.04, x, y)
                else:
                    px[x, y] = pick(GLASS, 0.30 - (y - wy0) / max(wy1 - wy0, 1) * 0.18,
                                    x, y)
        if smashed:
            # Two shards left in the frame, so the hole reads as broken rather
            # than as a window somebody left open.
            for sx in (wx0 + 1, wx1 - 1):
                if 0 <= sx < width and 0 <= wy0 < height:
                    px[sx, wy0] = pick(CHROME, 0.66, sx, wy0)
        else:
            _specular(px, wx0 + 1, wy0 + 1, min(4, wx1 - wx0), CHROME, width, height,
                      shade=0.72)
        # The seal round the glass, so it sits IN the door.
        _seam(px, wx0 - 1, wy1 + 1, wx1 + 1, wy1 + 1, width, height, paint, 0.10)

    # 5. Panel gaps. Two vertical seams turn one long flank into doors, and
    #    doors are most of what says the mass has a scale a person fits in.
    for cut in (0.42, 0.60) if kind in (0, 3) else (0.36, 0.62, 0.80):
        cx = int(width * cut)
        if body_x0 < cx < body_x1:
            top = int(round(_profile_y(profile, cut) * height))
            _seam(px, cx, max(top + 1, belt + 1), cx, sill - 1, width, height, paint, 0.06)

    # 6. Wheels, and the arch shadow above each. The arch is what sinks a
    #    wheel into the body instead of parking it in front.
    for index, wx in enumerate(VEHICLE_WHEELS[kind % len(VEHICLE_WHEELS)]):
        cx = width * wx
        for ax in range(int(cx - radius - 1), int(cx + radius + 2)):
            ay = int(axle - math.sqrt(max(radius * radius + 2 -
                                          (ax - cx) ** 2, 0.0)))
            if 0 <= ax < width and 0 <= ay < height and px[ax, ay][3]:
                px[ax, ay] = pick(paint, 0.06, ax, ay)
        _wheel(px, cx, axle, radius, width, height, flat=(index == kind % 2))

    # 7. Bumpers and lamps. Four pixels of amber and red, and they are the only
    #    saturated thing below the roofline — which is why they land as FRONT
    #    and BACK the instant the eye gets there.
    _fill(px, body_x0, sill - 2, body_x0 + 1, sill, CHROME, 0.34, 305, width, height)
    _fill(px, body_x1 - 1, sill - 2, body_x1, sill, CHROME, 0.34, 307, width, height)
    lamp_y = int(round(_profile_y(profile, profile[0][0] + 0.03) * height)) + 2
    for offset in range(2):
        if 0 <= body_x0 + offset < width and 0 <= lamp_y < height:
            px[body_x0 + offset, lamp_y] = pick(EMBER, 0.42, body_x0 + offset, lamp_y)
    # The tail lamp sits at the WAIST, not on the roofline. Pinned to the
    # profile it climbed to the top corner of the box bodies and read as a
    # warning light on a roof rather than as the back of a vehicle.
    tail_y = max(int(round(_profile_y(profile, profile[-1][0] - 0.03) * height)) + 2,
                 sill - 6)
    for offset in range(2):
        if 0 <= body_x1 - offset < width and 0 <= tail_y < height:
            px[body_x1 - offset, tail_y] = pick(RED, 0.55, body_x1 - offset, tail_y)

    # 8. Per-kind markings. All of them one or two pixels wide.
    cab_end = int(width * (0.30 if kind == 2 else 0.28))
    if kind == 2:
        # Red cross and a light bar. The cross is the most legible symbol
        # available at 16px and it is worth its eight pixels: it is what makes
        # a player detour for the medical drop table.
        mx = int(width * 0.66)
        my = int(height * 0.44)
        for offset in range(-2, 3):
            if 0 <= mx + offset < width and 0 <= my < height and px[mx + offset, my][3]:
                px[mx + offset, my] = pick(RED, 0.92, mx + offset, my)
            if 0 <= mx < width and 0 <= my + offset < height and px[mx, my + offset][3]:
                px[mx, my + offset] = pick(RED, 0.92, mx, my + offset)
        # The stripe down the flank, one step up from the body: an ambulance
        # is the one vehicle out here that was PAINTED to be found.
        band = int(height * 0.58)
        _fill(px, cab_end, band, body_x1 - 2, band + 1, RED, 0.30, 309, width, height)
        _bar(px, int(width * 0.14), int(height * 0.26) - 2, int(width * 0.26),
             width, height, (RED, BLUE))
    elif kind == 3:
        _bar(px, int(width * 0.40), int(height * 0.32) - 2, int(width * 0.60),
             width, height, (BLUE, RED))
        # The pale door a cruiser has and a sedan does not, and it stops at the
        # DOOR SEAMS. Floating free of them it read as a sticker on the flank;
        # bounded by them it reads as the panel that was painted white.
        _fill(px, int(width * 0.42) + 1, belt + 2, int(width * 0.60) - 1, sill - 3,
              CHROME, 0.32, 191, width, height, grain=0.10)
    elif kind == 4:
        # CRATES still strapped to the bed. Drawn as separate boxes at
        # different heights rather than as one plank band, because a band with
        # verticals across it reads as a railing — and a railing is furniture,
        # while three boxes somebody roped down is cargo that never arrived.
        bed_top = int(height * 0.44)
        bed0, bed1 = int(width * 0.34), body_x1 - 3
        cursor = bed0 + 1
        for index in range(3):
            box_w = int((bed1 - bed0) * (0.22 + 0.06 * (index % 2)))
            box_h = 5 + (index % 2) * 2
            if cursor + box_w > bed1:
                break
            _fill(px, cursor, bed_top - box_h, cursor + box_w, bed_top - 1,
                  PLANK, 0.50, 193 + index, width, height)
            # Lit top edge and a strap over the middle of each.
            _line(px, cursor, bed_top - box_h, cursor + box_w, bed_top - box_h,
                  PLANK, 0.92, width, height)
            _line(px, cursor + box_w // 2, bed_top - box_h, cursor + box_w // 2,
                  bed_top - 1, ROPE, 0.78, width, height)
            _seam(px, cursor + box_w + 1, bed_top - box_h, cursor + box_w + 1,
                  bed_top - 1, width, height, PLANK_DARK, 0.10)
            cursor += box_w + 2
        _seam(px, bed0, bed_top, bed1, bed_top, width, height, PLANK_DARK, 0.10)
    elif kind == 5:
        # A destination board over the windscreen, blank. Nobody is going there.
        _fill(px, int(width * 0.06), int(height * 0.11), int(width * 0.30),
              int(height * 0.12), PLANK_DARK, 0.30, 311, width, height)

    # 8. IT DIED HERE. Rust creeping up from the sill, moss on the rows that
    #    face the ground. Sparse: at any more than this the pass stops reading
    #    as age and starts reading as a stripe somebody painted on.
    # Less of it on the two PALE bodies: rust on white reads at twice the
    # strength it does on maroon, and at equal amounts the ambulance came out
    # looking sprayed with mud rather than parked for a year.
    _wear(px, body_x0, sill - 4, body_x1, sill, RUST, 331 + kind, width, height,
          0.06 if kind in (2, 5) else 0.11)
    _wear(px, body_x0, sill - 1, body_x1, ground, MOSS, 337 + kind, width, height, 0.16)

    # 9. THE COMPARTMENT. Cut a dark mouth into the body and swing its panel.
    pan0, pan1, hinge_right = VEHICLE_PANEL[kind % len(VEHICLE_PANEL)]
    px0, px1 = int(width * pan0), int(width * pan1)
    panel_top = int(round(_profile_y(profile, (pan0 + pan1) / 2) * height))
    if kind in (4, 5):
        panel_top = max(panel_top, belt + 2)
    elif kind in (1, 2):
        # A tailgate hinged at the ROOF of a box body would swing straight off
        # the top of the frame and get clipped. It opens from the waist, which
        # is also where a person would reach it from.
        panel_top = max(panel_top + 4, belt + 1)

    if open_t > 0.04:
        mouth_bot = min(sill - 1, panel_top + max(3, int((sill - panel_top) * 0.72)))
        _hollow(px, px0 + 1, panel_top, px1 - 1, mouth_bot, width, height)
        _spark(px, px0 + 1, panel_top, px1 - 1, mouth_bot, EMBER, open_t * 0.75,
               197 + kind, width, height)

    # Clamped so no lid ever leaves the frame: a panel cut off at the top edge
    # of the sheet reads as a rendering bug, not as a car with its boot up.
    lift = min(open_t * (height * 0.22 + 1), max(panel_top - 2.0, 0.0))
    _lid(px, px0, px1, panel_top, lift, hinge_right, paint, 199 + kind, width, height,
         thickness=3)
    if open_t > 0.05:
        # The hinge itself, still holding, so the panel is attached to a car.
        hx = px1 if hinge_right else px0
        _line(px, hx, panel_top - 1, hx, panel_top + 1, CHROME, 0.5, width, height)

    _ground_dark(img, rows=2, drop=0.62)
    outline(img, OUTLINE_COLD)
    return img


# --- the tribal ground ------------------------------------------------------


#: The groove colour, and it is deliberately NOT a step of any stone ramp.
#: `_sculpt` relights every pixel it finds in a ramp and leaves everything else
#: alone, so a chisel line drawn in this survives the relight instead of being
#: smoothed back into the mass it was cut into.
CARVE = rgb("#0f0e12")


def _carve(px, x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> None:
    """A chisel groove. Dark, one pixel, inside the stone.

    Stone has no seams of its own, so every line a player reads as CARVED is
    one of these: the gap between an arm and a ribcage, the line of a jaw, the
    crack that says this has been out here longer than they have.
    """
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for step in range(steps + 1):
        t = step / steps
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if 0 <= x < width and 0 <= y < height and px[x, y][3] > 20:
            px[x, y] = CARVE


def _sculpt(img: Image.Image, ramp: Ramp, grain: float = 0.10) -> None:
    """Relight a solid mass from its own silhouette. Stone's whole read.

    A carved figure built out of filled rectangles is a set of filled
    rectangles: the arms are the same value as the ribs they hang beside, so
    the only thing separating them is a groove, and a groove alone reads as a
    scratch on a slab rather than as two forms. What separates them is LIGHT —
    the edge of the arm that faces up and left catches the sky, the edge that
    turns away goes to the shadow step, and the eye reassembles the volumes
    without being told.

    So this walks the sprite once, asks each pixel how close it is to an edge
    and in which direction, and rewrites it. It touches ONLY pixels that are
    already a step of `ramp`: chisel grooves (`CARVE`), bone, rope and lichen
    are other materials and keep whatever they were given.
    """
    px = img.load()
    width, height = img.size
    solid = [[px[x, y][3] > 20 for y in range(height)] for x in range(width)]
    members = set(ramp)

    def free(x: int, y: int) -> bool:
        return not (0 <= x < width and 0 <= y < height and solid[x][y])

    for x in range(width):
        for y in range(height):
            if not solid[x][y] or px[x, y] not in members:
                continue
            if free(x - 1, y) or free(x, y - 1):
                shade = 0.94
            elif free(x - 2, y) or free(x, y - 2):
                shade = 0.72
            elif free(x + 1, y) or free(x, y + 1):
                shade = 0.14
            elif free(x + 2, y) or free(x, y + 2):
                shade = 0.34
            else:
                shade = 0.52
            px[x, y] = pick(ramp, shade + (hash01(x, y, 277) - 0.5) * grain, x, y)


def _chip(px, x: int, y: int, width: int, height: int) -> None:
    """Knock a pixel off an edge. Weather, damage, or a hundred years."""
    if 0 <= x < width and 0 <= y < height:
        px[x, y] = TRANSPARENT


# --- carved stone -----------------------------------------------------------
# THE STATUES ARE NOT DRAWN, THEY ARE BUILT AND THEN LIT.
#
# Everything else in this file is a box seen from the front: fill the panels,
# run a bright edge along whatever the sky can see, done. A figure is not a
# box. It is a stack of solids standing at different DISTANCES FROM THE
# CAMERA — a forearm in front of a ribcage, a jaw over a throat, a foot on a
# block — and what tells a player which one is in front is never a line drawn
# between them. It is the planes turning away from the key, the shadow the
# near part throws down-right onto the far one, and the single dark pixel
# where the two tuck together.
#
# The old statues were rectangles filled at a shade and then relit from the
# silhouette's own edges (`_sculpt`, which the altar still uses). One rind
# fits every mass that way, so an arm beside a rib came out as two grey slabs
# with a scratch between them, and six figures came out as six textures. What
# replaced it declares each part as a SOLID WITH A DEPTH and resolves the
# whole figure once — planes first, then the shadows those depths imply. An
# arm moved two pixels re-lights itself and re-shadows what stands behind it
# without being told to.
#
# See PIXEL-ART-DIRECTION.md: stacked convex masses (§2), the top plane's
# share of the silhouette (§3), hard cel bands and no gradient (§7), one key
# at 135deg/60deg (§8), contact AO (§10), overlap as the strongest depth cue
# (§18).

#: How deep a top face looks at this camera pitch, as a fraction of the mass's
#: half width. Around 55deg above the horizon, which is the pitch the rocks
#: and the trees were rebuilt on — the whole world has to agree about this or
#: the shrine sits at a different camera from the clearing it is standing in.
CAP_PITCH = 0.55

#: Where the vertical plane breaks land, as a fraction of a mass's half width.
#: The lit face takes less of the silhouette than the shade face (§3), and
#: neither break sits on the centre line: a mass split down the middle reads
#: as two objects stood back to back.
FACE_KEY = -0.46
FACE_SHADE = 0.34

#: The resolve pass hands out ramp INDICES, not shades. Every pixel of a
#: statue belongs to a named plane and takes that plane's step whole, which is
#: the entire reason these read as carved rather than as noisy:
#:
#:   TOP    anything the sky can see           smallest area, brightest
#:   KEY    the face turned into the 135deg light
#:   FRONT  the face turned at the camera      largest area, the base tone
#:   SHADE  the face turned away from the light
#:   DEEP   any of the above, standing in another part's shadow
#:   SEAM   contact, and the tuck where one mass passes behind another
PLANE_TOP = 5
PLANE_KEY = 4
PLANE_FRONT = 3
PLANE_SHADE = 2
PLANE_DEEP = 1
PLANE_SEAM = 0

#: Depth layers, named for what stands at each. They are WHOLE NUMBERS on
#: purpose: a shadow reaches one pixel down-right per layer of separation, so
#: these are not labels, they are the length of the shadow the part throws and
#: the reason a hand held out at the player darkens the chest behind it.
Z_BASE = 0.0
Z_BACK = 1.0
Z_BODY = 2.0
Z_HEAD = 3.0
Z_LIMB = 4.0
Z_REACH = 5.0

#: How much nearer a part has to be, per pixel of reach, before it throws a
#: shadow that far. Just under one layer, so the comparison never turns on a
#: float that landed a millionth short.
SHADOW_BITE = 0.9
#: How far a shadow reaches down-right, in pixels. Three is the whole budget:
#: at twenty pixels wide a longer one crosses the figure and reads as a band
#: painted onto it.
SHADOW_REACH = 3


class Carve:
    """A carved figure: solids declared with a depth, lit once at the end.

    `mass` is the only shape in here. A head, a shoulder, a forearm, a
    pedestal and a block lying on its side are all the same primitive — a
    tapering vertical solid with a foreshortened top face — because a chisel
    does not have a vocabulary either. What separates them is where they
    stand, how wide they are, and HOW FAR FORWARD, which is the number the
    whole thing turns on: `z` decides who occludes whom, who gets the tuck
    line, and who is standing in whose shadow.

    Nothing in here dithers. `pick` blends between two ramp steps with an
    ordered matrix, which is right for a soil the eye reads as an average and
    wrong for a plane the eye reads as a direction — it is what made the old
    statues look like they had been sprayed with grit. A plane takes its step
    whole, and the one deliberate two-tone band a sprite is allowed (§5) is
    spent on weathering instead.
    """

    def __init__(self, width: int, height: int, stone: Ramp) -> None:
        self.width = width
        self.height = height
        self.stone = stone
        #: Ramp index per pixel; -1 is empty.
        self.plane = [[-1] * width for _ in range(height)]
        #: How far toward the camera the pixel's owner stands.
        self.depth = [[0.0] * width for _ in range(height)]
        #: What the pixel is MADE of. A post is wood and a skull is bone, and
        #: they still want the same planes and the same shadows as the stone.
        self.mat: list[list[Ramp]] = [[stone] * width for _ in range(height)]

    # -- the frame ---------------------------------------------------------

    def fx(self, fraction: float) -> float:
        """A column, as a fraction of the frame. Recipes survive a retile."""
        return fraction * (self.width - 1)

    def fy(self, fraction: float) -> float:
        """A row, as a fraction of the frame."""
        return fraction * (self.height - 1)

    def solid(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and self.plane[y][x] >= 0

    def _put(self, x: int, y: int, step: int, z: float, ramp: Ramp) -> None:
        """Write a pixel unless something NEARER already owns it."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        if self.plane[y][x] >= 0 and self.depth[y][x] > z:
            return
        self.plane[y][x] = step
        self.depth[y][x] = z
        self.mat[y][x] = ramp

    # -- building ----------------------------------------------------------

    def mass(
        self,
        cx: float,
        top: float,
        bottom: float,
        half: float,
        *,
        half_top: float | None = None,
        z: float = Z_BODY,
        cap: float = 1.0,
        lean: float = 0.0,
        bulge: float = 1.0,
        ramp: Ramp | None = None,
    ) -> None:
        """One solid, standing `z` deep, with a top face on it.

        `half` is the half-width at the BOTTOM and `half_top` at the top, so a
        shoulder line is a mass that is wider where it starts and a robe is one
        that is wider where it ends; `bulge` bends that taper, letting a form
        hold its width and then give it up. `lean` drifts the top sideways —
        the only thing in here that stops six upright figures averaging out
        into a fence. `cap` scales the top face, and setting it to zero is how
        a part says it is tucked UNDER something rather than out in the air: a
        thigh disappearing into a hip has no sky on it.
        """
        ramp = self.stone if ramp is None else ramp
        half_top = half if half_top is None else half_top
        span = max(bottom - top, 1.0)
        for y in range(int(round(top)), int(round(bottom)) + 1):
            t = clamp01((y - top) / span)
            centre = cx + lean * (1.0 - t)
            hw = half_top + (half - half_top) * (t ** bulge)
            for x in range(int(round(centre - hw)), int(round(centre + hw)) + 1):
                self._put(x, y, _face((x - centre) / max(hw, 0.5)), z, ramp)
        if cap > 0.0:
            self._cap(cx + lean, top, half_top, cap, z, ramp)

    def _cap(
        self, cx: float, cy: float, half: float, cap: float, z: float, ramp: Ramp,
    ) -> None:
        """The top face, and one step of roll on its far rim.

        Sitting the ellipse ON the mass's top row rather than above it is what
        makes the plane read as the top OF something: half of it overhangs
        into the air and half of it lies over the front face, which is exactly
        what a horizontal surface does at this pitch. The rim facing away from
        the key drops a step so the plane has a thickness — the one place on a
        statue where two steps may touch without a break between them (§7).
        """
        ry = max(1.0, half * CAP_PITCH * cap)
        rx = max(0.9, half)
        cells = []
        for y in range(int(math.floor(cy - ry)), int(math.ceil(cy + ry)) + 1):
            for x in range(int(math.floor(cx - rx)), int(math.ceil(cx + rx)) + 1):
                dx = (x - cx) / rx
                dy = (y - cy) / ry
                if dx * dx + dy * dy <= 1.0:
                    self._put(x, y, PLANE_TOP, z, ramp)
                    cells.append((x, y))
        inside = set(cells)
        for x, y in cells:
            if not self.solid(x, y) or self.plane[y][x] != PLANE_TOP:
                continue
            if (x + 1, y) not in inside or (x, y + 1) not in inside:
                self.plane[y][x] = PLANE_KEY

    def beam(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        half: float,
        *,
        z: float = Z_BODY,
        ramp: Ramp | None = None,
    ) -> None:
        """A solid running at an angle: a lashed bone, a driven post.

        The same three planes as `mass`, laid across the run instead of down
        it, and no top face — everything drawn with this is thin enough that a
        cap would BE the shape.
        """
        ramp = self.stone if ramp is None else ramp
        steps = int(max(abs(x1 - x0), abs(y1 - y0), 1.0) * 2)
        for index in range(steps + 1):
            t = index / steps
            cx = x0 + (x1 - x0) * t
            y = int(round(y0 + (y1 - y0) * t))
            for x in range(int(round(cx - half)), int(round(cx + half)) + 1):
                self._put(x, y, _face((x - cx) / max(half, 0.5)), z, ramp)

    def groove(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """A chisel cut: the dark of the channel, and the lit lip above it.

        Stone has no seams of its own, so everything a player reads as CARVED
        is one of these. The lip is not decoration — a cut with no lit wall
        above it reads as a scratch drawn on the surface rather than as a
        groove taken out of it.
        """
        steps = int(max(abs(x1 - x0), abs(y1 - y0), 1.0))
        for index in range(steps + 1):
            t = index / steps
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            if not self.solid(x, y):
                continue
            self.plane[y][x] = PLANE_SEAM
            if self.solid(x, y - 1) and self.plane[y - 1][x] > PLANE_SHADE:
                self.plane[y - 1][x] = PLANE_KEY

    def hollow(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Cut a void: an eye socket, the dark under a hood.

        The absence is the effect. A socket SHADED instead of cut comes back
        as a cheekbone, and a hood with a chin in it is a person rather than
        the thing that unsettles the player about this one.
        """
        for y in range(int(round(y0)), int(round(y1)) + 1):
            for x in range(int(round(x0)), int(round(x1)) + 1):
                if self.solid(x, y):
                    self.plane[y][x] = PLANE_SEAM

    def bite(self, x: int, y: int) -> None:
        """Knock a corner off. A hammer, or a century of rain."""
        if self.solid(x, y):
            self.plane[y][x] = -1
            self.depth[y][x] = 0.0

    def stain(self, x: int, y: int, ramp: Ramp, step: int) -> None:
        """Put a second material on a pixel the stone already owns."""
        if self.solid(x, y):
            self.mat[y][x] = ramp
            self.plane[y][x] = step

    # -- resolving ---------------------------------------------------------

    def resolve(self, base: float) -> Image.Image:
        """Light the whole figure at once and hand back the sprite."""
        self._cast()
        self._tuck()
        self._contact(base)
        img = Image.new("RGBA", (self.width, self.height), TRANSPARENT)
        px = img.load()
        for y in range(self.height):
            for x in range(self.width):
                step = self.plane[y][x]
                if step >= 0:
                    ramp = self.mat[y][x]
                    px[x, y] = ramp[min(step, len(ramp) - 1)]
        return img

    def _cast(self) -> None:
        """Every part throws its shadow down-right onto what stands behind it.

        Marched from the RECEIVING pixel rather than stamped from the caster,
        which costs the same and gets the hard cases for free: a shadow only
        lands where there is something to land on, two parts at one depth
        never shade each other, and the length is read off the actual gap
        between the two surfaces instead of being a number somebody picked.
        """
        shaded = []
        for y in range(self.height):
            for x in range(self.width):
                if self.plane[y][x] < 0:
                    continue
                here = self.depth[y][x]
                for reach in range(1, SHADOW_REACH + 1):
                    sx, sy = x - reach, y - reach
                    if not self.solid(sx, sy):
                        continue
                    if self.depth[sy][sx] - here >= reach * SHADOW_BITE:
                        shaded.append((x, y, 2 if reach == 1 else 1))
                        break
        for x, y, drop in shaded:
            self.plane[y][x] = max(PLANE_DEEP, self.plane[y][x] - drop)

    def _tuck(self) -> None:
        """One pixel of occlusion where a near mass lands against a far one.

        This is the whole of §10, and it is the thing a groove cannot do: the
        arm does not get a line drawn beside it, the CHEST gets a dark pixel
        where the arm passes in front of it — which is a statement about which
        of the two is nearer rather than about where an edge is.
        """
        seams = []
        for y in range(self.height):
            for x in range(self.width):
                if self.plane[y][x] < 0:
                    continue
                here = self.depth[y][x]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if not self.solid(x + dx, y + dy):
                        continue
                    if self.depth[y + dy][x + dx] - here >= SHADOW_BITE:
                        seams.append((x, y))
                        break
        for x, y in seams:
            self.plane[y][x] = PLANE_SEAM

    def _contact(self, base: float) -> None:
        """The darkest band on the sprite is where it meets the floor (§19).

        Only columns whose lowest pixel is actually at the contact line get
        it. A hand held out at hip height has a lowest pixel too, and
        darkening that draws a second floor halfway up the statue.
        """
        for x in range(self.width):
            column = [y for y in range(self.height) if self.plane[y][x] >= 0]
            if not column:
                continue
            floor = max(column)
            if floor < base - 1:
                continue
            self.plane[floor][x] = PLANE_SEAM
            if floor - 1 in column:
                self.plane[floor - 1][x] = min(self.plane[floor - 1][x], PLANE_DEEP)


def _face(u: float) -> int:
    """Which vertical plane a column of a solid belongs to.

    Three faces and two hard breaks, which is the whole shading model. A
    fourth band would be a gradient wearing a disguise.
    """
    if u <= FACE_KEY:
        return PLANE_KEY
    if u >= FACE_SHADE:
        return PLANE_SHADE
    return PLANE_FRONT


# --- the ring ---------------------------------------------------------------
# Six figures, and every one of them is a NAMED RECIPE rather than a roll of
# one recipe — the same rule the rocks and the trees are built under, for the
# same reason. What has to differ between two statues is the SILHOUETTE, and
# rerolling a figure varies the grain inside a shape it never varies.
#
# THE SUBJECT IS THE POINT. These used to be totems, idols and a monolith —
# worked stone that meant "old" and nothing else, which made the shrine a
# texture rather than a statement. Carving the CREATURES costs the same
# pixels and says something the map could not say before: whoever built this
# had seen the things in these woods, stood in front of one long enough to
# get the shoulders right, and then set a ring of them around an altar and
# left offerings in the middle. The player meets the walker in stone before
# they meet it in the dark, and meets it again afterwards knowing what the
# ring was for.
#
# They are also the only objects in the forest TALLER than they are wide, and
# the only worked stone. Everything else out here is a low horizontal mass —
# a car, a log, a barrel — so a column of narrow vertical shapes at the far
# end of a clearing does not read as more of the same. It reads as a
# question, which is as far as a landmark has to get a player before the loot
# has to do the rest.


def _pedestal(c: Carve, kind: str, cx: float) -> float:
    """The block a carved figure stands on. Returns the row its feet rest at.

    Doing two jobs, and the second one is why there are six of these instead
    of one. It says somebody PLACED this rather than that it grew here, which
    is the whole difference between the shrine and the rest of the forest;
    and because the base is the widest thing in the silhouette, a different
    base is the cheapest way to make two figures unmistakable at the far end
    of a lantern — the bottom third of the shape is doing as much work as the
    head is.
    """
    ground = c.height - 1
    if kind == "block":
        # Squared, dressed, two courses. The one that looks quarried.
        c.mass(cx, c.fy(0.945), ground, c.fx(0.40), z=Z_BASE, cap=0.0)
        c.mass(cx, c.fy(0.885), c.fy(0.95), c.fx(0.35), z=Z_BACK, cap=0.8)
        return c.fy(0.875)
    if kind == "slab":
        # Low, wide, sunk into the ground. Half of it is under the soil.
        c.mass(cx + 0.5, c.fy(0.925), ground, c.fx(0.44), half_top=c.fx(0.40),
               z=Z_BASE, cap=0.9)
        return c.fy(0.915)
    if kind == "drum":
        # A turned column base: narrower, taller, and round, so its top face
        # is a full ellipse instead of a squared plate.
        c.mass(cx, c.fy(0.955), ground, c.fx(0.32), z=Z_BASE, cap=0.0)
        c.mass(cx, c.fy(0.855), c.fy(0.96), c.fx(0.27), half_top=c.fx(0.25),
               z=Z_BACK, cap=1.0)
        return c.fy(0.845)
    if kind == "step":
        # Three courses, the top one small. The tallest base in the ring and
        # the one that makes its figure read as raised rather than as standing.
        c.mass(cx, c.fy(0.94), ground, c.fx(0.42), z=Z_BASE, cap=0.0)
        c.mass(cx - 0.4, c.fy(0.885), c.fy(0.945), c.fx(0.35), z=Z_BACK, cap=0.7)
        c.mass(cx - 0.8, c.fy(0.83), c.fy(0.89), c.fx(0.27), z=Z_BODY, cap=0.8)
        return c.fy(0.82)
    if kind == "cairn":
        # Not worked at all: field stones piled until they held. The post is
        # the one thing at the shrine somebody could have made in an
        # afternoon, and a dressed plinth under it would be a lie.
        c.mass(cx - 3.2, c.fy(0.935), ground, c.fx(0.16), z=Z_BASE, cap=1.0)
        c.mass(cx + 3.4, c.fy(0.945), ground, c.fx(0.14), z=Z_BACK, cap=1.0)
        c.mass(cx + 0.4, c.fy(0.905), c.fy(0.99), c.fx(0.19), z=Z_BODY, cap=1.0)
        return c.fy(0.90)
    # "tilted": one course, cracked through, settled to the right. Whatever
    # took the figure down took the base with it.
    c.mass(cx - 0.6, c.fy(0.90), ground, c.fx(0.41), half_top=c.fx(0.38),
           z=Z_BASE, cap=0.85, lean=-1.2)
    c.groove(cx + c.fx(0.10), c.fy(0.925), cx + c.fx(0.20), ground - 1)
    return c.fy(0.89)


def _walker(c: Carve, cx: float, feet: float) -> None:
    """Arms out, jaw down. The pose the player meets in the dark ninety
    seconds later, and the head is narrower than the shoulders because that
    single ratio is what makes a stack of stone resolve into a body."""
    # Legs, apart, the far one a layer back so the gap between them is a
    # shadow rather than a drawn line.
    c.mass(cx - 2.4, c.fy(0.58), feet, 1.8, half_top=1.5, z=Z_BODY, cap=0.0)
    c.mass(cx + 2.6, c.fy(0.58), feet - 0.6, 1.6, half_top=1.4, z=Z_BACK, cap=0.0)
    c.mass(cx - 2.7, feet - 1.3, feet, 2.3, z=Z_LIMB, cap=0.8)
    c.mass(cx + 2.9, feet - 1.9, feet - 0.6, 2.0, z=Z_HEAD, cap=0.8)
    # Hips, then a torso that is all shoulder at the top and nothing at the
    # waist. `bulge` is what makes the drop happen at the armpit.
    c.mass(cx, c.fy(0.50), c.fy(0.62), 3.0, half_top=3.4, z=Z_BODY, cap=0.0)
    c.mass(cx - 0.3, c.fy(0.305), c.fy(0.55), 2.9, half_top=4.5, z=Z_BODY,
           cap=0.85, bulge=0.55)
    c.groove(cx - 2.6, c.fy(0.355), cx + 2.4, c.fy(0.345))
    c.groove(cx - 0.4, c.fy(0.40), cx - 0.4, c.fy(0.50))
    # Neck sunk between the shoulders, so the jaw has something to shade.
    c.mass(cx - 0.2, c.fy(0.275), c.fy(0.33), 1.4, z=Z_BACK, cap=0.0)
    # THE HEAD. Tipped, browed, and hollow where the eyes were.
    c.mass(cx - 0.4, c.fy(0.165), c.fy(0.295), 2.4, half_top=2.1, z=Z_HEAD,
           cap=1.0, lean=-0.8)
    c.mass(cx - 1.0, c.fy(0.185), c.fy(0.215), 2.4, z=Z_LIMB, cap=0.45)
    c.hollow(cx - 2.4, c.fy(0.225), cx - 1.3, c.fy(0.245))
    c.hollow(cx + 0.3, c.fy(0.225), cx + 1.2, c.fy(0.245))
    c.mass(cx - 0.4, c.fy(0.262), c.fy(0.30), 1.7, z=Z_LIMB, cap=0.0)
    c.groove(cx - 1.7, c.fy(0.268), cx + 1.1, c.fy(0.268))
    # THE ARMS, and they are the tell: held clear of the ribs with daylight
    # between, hands lower and blockier than the elbows, and the near one
    # reaching a whole layer further forward than the far one.
    c.mass(cx - 5.6, c.fy(0.33), c.fy(0.555), 1.5, half_top=1.8, z=Z_LIMB,
           cap=0.5, lean=1.1)
    c.mass(cx - 6.1, c.fy(0.545), c.fy(0.625), 2.0, half_top=1.7, z=Z_REACH, cap=1.0)
    c.mass(cx + 5.4, c.fy(0.335), c.fy(0.505), 1.4, half_top=1.7, z=Z_HEAD,
           cap=0.5, lean=-1.0)
    c.mass(cx + 5.9, c.fy(0.495), c.fy(0.565), 1.8, half_top=1.5, z=Z_LIMB, cap=1.0)


def _brute(c: Carve, cx: float, feet: float) -> None:
    """Shoulders first, head last. The head is a detail on this one and the
    shoulders ARE the silhouette — the same reading order as the creature,
    which is the entire reason to carve it."""
    # Legs wide and short, planted.
    c.mass(cx - 3.0, c.fy(0.66), feet, 2.4, half_top=2.2, z=Z_BODY, cap=0.0)
    c.mass(cx + 3.2, c.fy(0.66), feet - 0.5, 2.2, half_top=2.0, z=Z_BACK, cap=0.0)
    c.mass(cx - 3.2, feet - 1.3, feet, 2.7, z=Z_LIMB, cap=0.8)
    c.mass(cx + 3.4, feet - 1.8, feet - 0.5, 2.4, z=Z_HEAD, cap=0.8)
    # The mass, hunched forward: a barrel of a chest over a short waist, and
    # the whole thing leaning off the vertical so the ring has one figure
    # that is not standing to attention.
    c.mass(cx, c.fy(0.55), c.fy(0.70), 3.6, half_top=4.0, z=Z_BODY, cap=0.0)
    c.mass(cx + 0.4, c.fy(0.335), c.fy(0.60), 3.8, half_top=4.6, z=Z_BODY,
           cap=0.7, bulge=0.6, lean=-1.0)
    # THE SHOULDERS. Wider than anything else in the ring, asymmetric, and
    # capped hard — this slab is the object, everything else hangs off it.
    c.mass(cx - 0.6, c.fy(0.30), c.fy(0.395), 7.0, half_top=6.2, z=Z_HEAD, cap=1.0)
    c.groove(cx - 4.4, c.fy(0.395), cx + 4.0, c.fy(0.41))
    # The head, sunk between them, barely clearing the line.
    c.mass(cx - 0.4, c.fy(0.245), c.fy(0.315), 1.9, half_top=1.7, z=Z_BODY,
           cap=1.0, lean=0.5)
    c.hollow(cx - 1.5, c.fy(0.28), cx - 0.8, c.fy(0.295))
    c.hollow(cx + 0.5, c.fy(0.28), cx + 1.2, c.fy(0.295))
    # Arms to the knees, thicker than the legs. The left one is raised and
    # the right one hangs: two arms doing the same thing is a diagram.
    c.mass(cx - 6.2, c.fy(0.36), c.fy(0.60), 1.9, half_top=2.2, z=Z_LIMB,
           cap=0.4, lean=1.4)
    c.mass(cx - 6.8, c.fy(0.585), c.fy(0.70), 2.4, half_top=2.0, z=Z_LIMB, cap=1.0)
    c.mass(cx + 6.0, c.fy(0.335), c.fy(0.545), 1.8, half_top=2.4, z=Z_HEAD,
           cap=0.4, lean=-0.8)
    c.mass(cx + 6.6, c.fy(0.53), c.fy(0.615), 2.2, half_top=1.9, z=Z_LIMB, cap=1.0)


def _husk(c: Carve, cx: float, feet: float) -> None:
    """Everything the walker has, starved, with the ribs cut in and one arm
    gone below the elbow. Parallel arcs are the one bone shape that survives
    being half in shadow, which is why this is the variant that still reads
    when a lantern only catches an edge of it."""
    c.mass(cx - 1.9, c.fy(0.62), feet, 1.3, half_top=1.1, z=Z_BODY, cap=0.0)
    c.mass(cx + 2.1, c.fy(0.62), feet - 0.6, 1.2, half_top=1.0, z=Z_BACK, cap=0.0)
    c.mass(cx - 2.2, feet - 1.2, feet, 1.9, z=Z_LIMB, cap=0.8)
    c.mass(cx + 2.4, feet - 1.7, feet - 0.6, 1.7, z=Z_HEAD, cap=0.8)
    # Pelvis, narrow, then a ribcage that is WIDER than the hips — the one
    # proportion that says starved rather than thin.
    c.mass(cx, c.fy(0.56), c.fy(0.66), 2.1, half_top=2.3, z=Z_BODY, cap=0.0)
    c.mass(cx - 0.2, c.fy(0.30), c.fy(0.58), 2.0, half_top=3.4, z=Z_BODY,
           cap=0.75, bulge=1.6)
    for index in range(4):
        row = c.fy(0.345) + index * (c.height * 0.045)
        c.groove(cx - 2.6 + index * 0.25, row, cx + 2.3 - index * 0.25, row)
    # Long neck, head thrown back. Nothing else in the ring looks up.
    c.mass(cx + 0.2, c.fy(0.255), c.fy(0.32), 1.1, z=Z_BACK, cap=0.0)
    c.mass(cx + 0.5, c.fy(0.135), c.fy(0.27), 2.2, half_top=2.0, z=Z_HEAD,
           cap=1.0, lean=1.0)
    c.hollow(cx - 0.7, c.fy(0.195), cx + 0.2, c.fy(0.215))
    c.hollow(cx + 1.6, c.fy(0.19), cx + 2.4, c.fy(0.21))
    c.groove(cx - 0.6, c.fy(0.245), cx + 2.2, c.fy(0.25))
    # One whole arm, and one that ends at the elbow. The break is the
    # silhouette feature and it is on the LIT side, where it cannot hide.
    c.mass(cx - 4.6, c.fy(0.325), c.fy(0.44), 1.2, half_top=1.5, z=Z_LIMB,
           cap=0.5, lean=0.6)
    c.mass(cx + 4.4, c.fy(0.325), c.fy(0.62), 1.1, half_top=1.5, z=Z_HEAD,
           cap=0.5, lean=-0.7)
    c.mass(cx + 4.9, c.fy(0.605), c.fy(0.68), 1.6, half_top=1.3, z=Z_LIMB, cap=1.0)


def _supplicant(c: Carve, cx: float, feet: float) -> None:
    """A PERSON, robed and hooded, hands together in front. The one figure in
    the ring that is not a creature, and it is what turns a circle of monsters
    into a place where somebody stood in front of them on purpose — without it
    the shrine is a trophy rack.

    It was a kneeling pose first and it did not survive the size: a crouch is
    a diagonal, and a diagonal in a twenty-pixel silhouette is a lump. Upright
    and conical, it reads at the same distance as the rest of the ring, and
    the hood does the storytelling the pose was supposed to."""
    # The robe: one unbroken cone from the crown to the hem, which is the
    # only silhouette in the ring with no legs in it.
    c.mass(cx - 0.3, c.fy(0.20), feet, c.fx(0.34), half_top=c.fx(0.10),
           z=Z_BODY, cap=0.0, bulge=1.7)
    # The hem, flared and a layer forward, so it throws a shadow back onto
    # the robe and the figure stops being a traffic cone.
    c.mass(cx - 0.3, feet - 2.2, feet, c.fx(0.37), half_top=c.fx(0.33),
           z=Z_HEAD, cap=0.7)
    # Two folds down the front. They run at a slight angle so the cloth is
    # hanging rather than pleated.
    c.groove(cx - 2.0, c.fy(0.50), cx - 3.0, feet - 2)
    c.groove(cx + 1.6, c.fy(0.53), cx + 2.6, feet - 2)
    # THE HOOD, a mass of its own over the shoulders, and the cavity CUT
    # rather than shaded — a shaded one comes back as a chin.
    c.mass(cx - 0.3, c.fy(0.11), c.fy(0.34), c.fx(0.20), half_top=c.fx(0.11),
           z=Z_HEAD, cap=1.0, lean=-0.5, bulge=0.7)
    c.hollow(cx - 2.0, c.fy(0.20), cx + 1.4, c.fy(0.28))
    c.mass(cx - 0.4, c.fy(0.185), c.fy(0.205), c.fx(0.17), z=Z_LIMB, cap=0.4)
    # The sleeves, meeting over the hands. One block, one layer nearer than
    # the robe, which is what makes the arms read as folded in front of it.
    c.mass(cx - 3.4, c.fy(0.37), c.fy(0.52), 1.5, half_top=1.8, z=Z_HEAD,
           cap=0.4, lean=0.5)
    c.mass(cx + 2.9, c.fy(0.37), c.fy(0.52), 1.4, half_top=1.7, z=Z_HEAD,
           cap=0.4, lean=-0.4)
    c.mass(cx - 0.3, c.fy(0.475), c.fy(0.545), 2.4, z=Z_LIMB, cap=1.0)
    c.groove(cx - 0.3, c.fy(0.50), cx - 0.3, c.fy(0.535))


def _post(c: Carve, cx: float, feet: float) -> None:
    """Not carved and not stone: a pole somebody drove in and tied a head to.
    The most direct sentence on the map, and the reason the ring reads as
    something people did rather than as something that was always here."""
    # The post. Wood, so it takes the same three planes out of a different
    # ramp — the plane vocabulary is about light, not about material.
    c.mass(cx + 0.2, c.fy(0.24), feet + 1.5, 1.4, half_top=1.2, z=Z_BODY,
           cap=0.6, lean=-0.6, ramp=PLANK)
    c.groove(cx + 0.9, c.fy(0.33), cx + 0.6, feet)
    # The skull, wider than the post and sat on top of it.
    c.mass(cx - 0.4, c.fy(0.145), c.fy(0.225), 2.5, half_top=2.2, z=Z_HEAD,
           cap=1.0, lean=0.4, ramp=BONE)
    c.hollow(cx - 2.0, c.fy(0.175), cx - 1.0, c.fy(0.20))
    c.hollow(cx + 0.5, c.fy(0.175), cx + 1.4, c.fy(0.20))
    # The jaw, one row of teeth. Four dark pixels, and they are what make the
    # lump on the stick a skull.
    c.mass(cx - 0.4, c.fy(0.215), c.fy(0.245), 1.8, z=Z_LIMB, cap=0.0, ramp=BONE)
    for offset in (-1.4, 0.0, 1.4):
        c.groove(cx - 0.4 + offset, c.fy(0.222), cx - 0.4 + offset, c.fy(0.243))
    # Two turns of rope holding it on, and two bones lashed crossways below.
    for row in (c.fy(0.265), c.fy(0.30)):
        c.beam(cx - 1.9, row, cx + 2.3, row, 0.6, z=Z_LIMB, ramp=ROPE)
    c.beam(cx - 4.4, c.fy(0.37), cx + 4.6, c.fy(0.43), 0.8, z=Z_HEAD, ramp=BONE)
    c.beam(cx - 4.4, c.fy(0.43), cx + 4.6, c.fy(0.37), 0.8, z=Z_LIMB, ramp=BONE)


def _fallen(c: Carve, cx: float, feet: float) -> None:
    """Hips and legs still standing on the block, the head lying at their feet
    where it came off. Two shapes, and the distance between them is the whole
    sentence — a player who has met the walker upright can see exactly what
    used to be here.

    It was a whole toppled body first: torso, arms and stumps all inside
    twenty pixels, and every one of them came out too small to identify. A
    head on the floor beside a pair of snapped legs says the same thing with
    two shapes instead of six."""
    c.mass(cx - 2.2, c.fy(0.62), feet, 1.9, half_top=1.6, z=Z_BODY, cap=0.0)
    c.mass(cx + 2.4, c.fy(0.62), feet - 0.6, 1.7, half_top=1.5, z=Z_BACK, cap=0.0)
    c.mass(cx - 2.5, feet - 1.3, feet, 2.3, z=Z_LIMB, cap=0.8)
    c.mass(cx + 2.7, feet - 1.8, feet - 0.6, 2.0, z=Z_HEAD, cap=0.8)
    # The hips, and the break above them: a shorn top face that is BRIGHTER
    # than anything else on the figure, because it is the one surface out
    # here that has not had a century of weather on it.
    c.mass(cx, c.fy(0.505), c.fy(0.65), 3.0, half_top=3.3, z=Z_BODY, cap=0.9)
    for index, column in enumerate((-2.4, -1.0, 0.6, 2.2)):
        c.bite(int(round(cx + column)), int(round(c.fy(0.495) - (index % 2))))
        c.bite(int(round(cx + column + 1)), int(round(c.fy(0.485))))
    # THE HEAD, on its side on the block, sockets down. Big — it is half the
    # read and it is competing with a leg twice its height.
    c.mass(cx - 5.4, c.fy(0.79), c.fy(0.875), 3.0, half_top=2.6, z=Z_LIMB,
           cap=1.0, lean=-0.6)
    c.hollow(cx - 6.6, c.fy(0.825), cx - 5.6, c.fy(0.845))
    c.groove(cx - 7.4, c.fy(0.862), cx - 3.6, c.fy(0.858))
    # Rubble between the head and the stumps, at the 1 : 0.7 : 0.5 rhythm.
    c.mass(cx + 4.6, c.fy(0.845), c.fy(0.885), 1.6, z=Z_HEAD, cap=1.0)
    c.mass(cx + 6.4, c.fy(0.86), c.fy(0.89), 1.1, z=Z_BODY, cap=1.0)
    c.mass(cx - 1.4, c.fy(0.865), c.fy(0.89), 0.8, z=Z_BACK, cap=1.0)


#: The ring, in sheet order. Each figure names the stone it was cut from and
#: the base it stands on; `make_scenery.build` packs them in the order of this
#: dict, so a new statue is a new entry and nothing else has to know.
STATUE_FIGURES: dict[str, dict] = {
    "walker": {"stone": SLATE, "base": "block", "build": _walker},
    "brute": {"stone": TUFA, "base": "slab", "build": _brute},
    "husk": {"stone": SLATE, "base": "drum", "build": _husk},
    "supplicant": {"stone": TUFA, "base": "step", "build": _supplicant},
    "post": {"stone": SLATE, "base": "cairn", "build": _post},
    "fallen": {"stone": TUFA, "base": "tilted", "build": _fallen},
}


def _weather(c: Carve, salt: int, base: float) -> None:
    """A century of rain, in three passes, and none of them is noise.

    Unweathered stone in a wet forest is the one thing that would make these
    read as freshly placed, which is the opposite of everything else at the
    shrine. But weather has to arrive as SHAPE: chips are taken out of the
    silhouette so the outline stops being a smooth arc (§15), the erosion band
    is the one two-tone dither a sprite is allowed (§5), and the lichen is the
    single accent hue (§12) — which is why it is capped, and why it only lands
    on faces the sun never reaches.
    """
    edges = [
        (x, y)
        for y in range(int(c.fy(0.08)), int(base) - 1)
        for x in range(c.width)
        if c.solid(x, y)
        and not all(c.solid(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, -1)))
    ]
    for x, y in edges:
        if hash01(x, y, salt) < 0.055:
            c.bite(x, y)
    # One eroded band, low, where water has stood against the stone. Two
    # tones alternating on a 2px cell — a material band, never a texture.
    band0, band1 = int(base - c.fy(0.16)), int(base)
    for y in range(band0, band1):
        for x in range(c.width):
            if not c.solid(x, y) or c.plane[y][x] > PLANE_FRONT:
                continue
            if ((x // 2) + (y // 2)) % 2 == 0 and hash01(x, y, salt + 3) < 0.55:
                c.plane[y][x] = max(PLANE_DEEP, c.plane[y][x] - 1)
    lichen = 0
    for y in range(int(c.fy(0.35)), c.height):
        for x in range(c.width):
            if lichen >= 14 or not c.solid(x, y):
                continue
            if c.plane[y][x] not in (PLANE_SHADE, PLANE_DEEP):
                continue
            if hash01(x, y, salt + 11) < 0.10:
                c.stain(x, y, MOSS, PLANE_SHADE)
                lichen += 1


def make_statue(width: int, height: int, kind: str, salt: int) -> Image.Image:
    """One of the six, by name. Solids, planes, shadows, then a century of rain.

    Takes a SALT rather than an `random.Random` the way the rocks do, and the
    difference is worth the inconsistency: a shared generator makes every
    figure's weathering depend on how many pixels the figure before it
    happened to chip, so moving the walker's arm reshuffles the lichen on the
    other five. `hash01` off this salt is stable per statue, which is the same
    rule the animated sheets in this file already follow.
    """
    recipe = STATUE_FIGURES[kind]
    carve = Carve(width, height, recipe["stone"])
    cx = carve.fx(0.5)
    feet = _pedestal(carve, recipe["base"], cx)
    recipe["build"](carve, cx, feet)
    _weather(carve, salt, height - 1)
    img = carve.resolve(height - 1)
    # The one thing the sculpt system does not supply: the ground going dark
    # where the pedestal meets it. Every other standing prop in the folder
    # takes this now, and a statue without it is the only thing in the shrine
    # that does not sit in the clearing (S19).
    shadow(img, (width - 1) / 2.0, height - 1.5, width * 0.40, width * 0.40 * SLOPE)
    outline(img, OUTLINE_STONE)
    return img


#: Wax. Burnt down, never burning — see the note in `make_altar`.
WAX: Ramp = [rgb(c) for c in ("#3b352a", "#4e4735", "#645b44", "#7d7256", "#988b6c")]


def make_altar(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """The one thing at a shrine you open. `kind`: 0 stone altar, 1 bone cairn.

    The lid SLIDES rather than hinges, and it slides sideways rather than up.
    Everything else in the game that opens hinges, so a slab grinding aside is
    a different verb even though it is the same key — and it is the only
    animation here that uncovers a hole in the GROUND rather than the inside
    of a container.

    WHAT IS ON TOP OF IT IS THE SCENE. The altar used to be a grey bar on a
    grey box, which is a fair description of an altar and no description at
    all of a place: it stated a shape and left the player to guess why a ring
    of statues was pointed at it. What it carries now is the evidence —
    burnt-down candle stubs, a stone bowl, small bones, a run of blood down
    the front and rune marks cut into the side. None of that changes what the
    object does. All of it changes what the player thinks happened here, and
    the difference between "a container in a clearing" and "people came here
    and paid for something" is entirely in those pixels.

    THE CANDLES ARE OUT, and that is not an oversight. Nothing in the forest
    burns — see the note on world lights in `server/app/scenery.py` — so these
    are cold wax stubs with black wicks. A lit candle here would be a lamp,
    and a lamp does the player's reading for them from across the map.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    size = (width, height)
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    base_h = int(height * 0.40)
    base_top = ground - base_h
    half = width * 0.36

    # THE PLINTH: three steps, so it reads as BUILT rather than as dropped —
    # and each step is a `box`, not a rectangle. Stacked as flat fills the
    # altar was a stone-coloured staircase seen from straight ahead, which is
    # the one thing a shrine cannot be: the whole scene points at it, so it is
    # the object in the game most worth the top faces. Widest step on the
    # ground, narrowest under the slab (S17: the base is wider than the crown
    # for anything grounded), and each one is a real footprint the next stands
    # on.
    for lift, spread in ((0.0, 1.24), (2.0, 1.12), (4.0, 1.00)):
        box(px, size, cx, ground - lift, half * spread * 1.06, half * spread * 0.84,
            max(2.0, (base_h - lift) * (0.35 if spread > 1.0 else 1.0)), GRANITE)

    if kind == 1:
        # A cairn of bones stacked around the plinth. Same silhouette, and the
        # difference between the two is what the place cost the people who
        # used it — one of them is masonry and the other one is a body count.
        for index in range(11):
            bx = cx + math.cos(index * 1.9) * half * 1.06
            by = ground - 2 - (index % 4)
            _line(px, int(bx), int(by), int(bx + 3), int(by - 1), BONE, 0.55,
                  width, height)
        for index in range(3):
            sx = cx + (index - 1) * half * 0.72
            _disc(px, sx, ground - 5 - (index % 2) * 2, width * 0.07, BONE, 0.70,
                  246 + index, width, height, squash=1.1)
    else:
        # Runes cut down the face of the plinth. Not a language — four short
        # strokes on an even rhythm, which is exactly enough for a player to
        # know a person made the marks and not enough to invite reading them.
        for index in range(4):
            rx = int(cx - half + 3 + index * (half * 2 - 6) / 3)
            _carve(px, rx, base_top + 2, rx, base_top + 5, width, height)
            _carve(px, rx - 1, base_top + 5, rx + 1, base_top + 5, width, height)

    # The hollow under the slab.
    hollow_top = base_top - 4
    if open_t > 0.03:
        _hollow(px, int(cx - half + 2), hollow_top, int(cx + half - 2), base_top - 1,
                width, height)
        _spark(px, int(cx - half + 2), hollow_top, int(cx + half - 2), base_top - 1,
               EMBER, open_t, 245 + kind, width, height)

    # THE SLAB, ground sideways off the mouth — far enough that the hole is
    # unmistakably open, not so far that the stone and everything standing on
    # it leaves the frame. A slab that exits the sprite reads as deleted, and
    # the held final pose has to stay a legible OPEN altar.
    slide = int(open_t * half * 0.85)
    slab_x0 = int(cx - half + slide)
    slab_x1 = int(cx + half + slide)
    slab_top = hollow_top - 2
    # A SLAB HAS A THICKNESS, and it is the whole reason this reads as a lid
    # rather than as a painted rectangle: the camera sees its top face, the
    # sliver of its near edge, and the shadow it drops onto the plinth behind.
    slab_cx = cx + slide
    box(px, size, slab_cx, base_top - 1, half * 1.06, half * 0.84,
        max(2.0, base_top - 1 - slab_top), STONE)
    # The seam where the slab sits on the plinth. Without it the two stones are
    # one stone, and the thing that is supposed to MOVE has no edge to move on.
    for x in range(int(slab_cx - half * 1.06), int(slab_cx + half * 0.84) + 1):
        y = int(round(base_top - 1 - abs(x - slab_cx) * SLOPE)) + 1
        if 0 <= x < width and 0 <= y < height and px[x, y][3]:
            px[x, y] = tone(GRANITE, 0, x, y)

    # WHAT IS ON THE SLAB. It rides with it — an offering that stayed put while
    # the stone under it slid away would read as a bug, and pinning it to the
    # slab costs one variable.
    if kind == 0:
        # A bowl, dead centre, cut into the top of the stone.
        _fill(px, int(cx - 2 + slide), slab_top - 2, int(cx + 2 + slide),
              slab_top, STONE, 0.78, 249, width, height, grain=0.08)
        _carve(px, int(cx - 1 + slide), slab_top - 1, int(cx + 1 + slide),
               slab_top - 1, width, height)
        # Two candle stubs, unequal, both out. The uneven pair is what makes
        # them read as things somebody left rather than as a decoration.
        for offset, stub in ((-int(half * 0.66), 3), (int(half * 0.62), 2)):
            sx = int(cx + offset + slide)
            _fill(px, sx, slab_top - stub, sx + 1, slab_top - 1, WAX, 0.66, 251,
                  width, height, grain=0.10)
            if 0 <= sx < width and 0 <= slab_top - stub - 1 < height:
                px[sx, slab_top - stub - 1] = CARVE          # the spent wick
            # Wax that ran down the stone and set there.
            _line(px, sx, slab_top, sx, slab_top + 1, WAX, 0.34, width, height)
    else:
        # The cairn's capstone carries a skull instead of a bowl.
        _disc(px, cx + slide, slab_top - 2, width * 0.09, BONE, 0.76, 253,
              width, height, squash=1.15)
        for ex in (int(cx + slide - 2), int(cx + slide + 1)):
            if 0 <= ex < width and 0 <= slab_top - 2 < height:
                px[ex, slab_top - 2] = CARVE

    # A run of blood over the front lip, dried. The one warm-dark thing on the
    # object, and the only line on it that says what the bowl was FOR.
    for offset in (-1, 0, 2):
        bx = int(cx + offset + slide)
        _line(px, bx, base_top - 1, bx, base_top + 3 + (offset % 2), RED, 0.12,
              width, height)

    _sculpt(img, STONE, grain=0.08)
    _ground_dark(img, rows=1, drop=0.72)
    outline(img, OUTLINE_STONE)
    return img


def make_bones(size: int, variant: int, rng: random.Random) -> Image.Image:
    """A decal of bones on the floor. Flat, no outline: it lies there.

    Placed around shrines and last stands, never on its own. One skull in an
    empty clearing is a prop; nine of them in a ring around a carved stone is
    a reason to check your ammunition.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    centre = (size - 1) / 2.0

    if variant == 0:
        _disc(px, centre, centre, size * 0.24, BONE, 0.62, 251, size, size, squash=1.1)
        for ex in (int(centre - 2), int(centre + 1)):
            ey = int(centre)
            if 0 <= ex < size and 0 <= ey < size:
                px[ex, ey] = pick(PLANK_DARK, 0.2, ex, ey)
    elif variant == 1:
        # A ribcage, which is the only bone shape that stays readable when the
        # sprite is half in shadow: parallel arcs.
        for index in range(4):
            y = int(centre - 3 + index * 2)
            for x in range(int(centre - 4), int(centre + 5)):
                if 0 <= x < size and 0 <= y < size and abs(x - centre) > 1:
                    px[x, y] = pick(BONE, 0.55, x, y)
    elif variant == 2:
        for _ in range(5):
            x0 = int(rng.uniform(2, size - 4))
            y0 = int(rng.uniform(2, size - 3))
            _line(px, x0, y0, x0 + rng.randint(2, 5), y0 + rng.randint(-2, 2),
                  BONE, 0.52, size, size)
    elif variant == 3:
        # A skull half sunk in the litter, only the crown showing.
        _disc(px, centre, centre + 2, size * 0.26, BONE, 0.48, 253, size, size, squash=0.6)
    elif variant == 4:
        # Ash and charred wood -- the fire part of a rite.
        for _ in range(14):
            x = int(rng.uniform(1, size - 1))
            y = int(rng.uniform(1, size - 1))
            if math.hypot(x - centre, y - centre) < size * 0.4:
                px[x, y] = pick(PLANK_DARK, rng.uniform(0.2, 0.6), x, y)
    else:
        for _ in range(3):
            x0 = int(rng.uniform(2, size - 5))
            y0 = int(rng.uniform(3, size - 3))
            _line(px, x0, y0, x0 + 4, y0, BONE, 0.6, size, size)
            _line(px, x0, y0 - 1, x0, y0 + 1, BONE, 0.5, size, size)
            _line(px, x0 + 4, y0 - 1, x0 + 4, y0 + 1, BONE, 0.5, size, size)
    return img


def make_oil(size: int, variant: int, rng: random.Random) -> Image.Image:
    """A slick under a dead vehicle. Flat, dark, faintly iridescent.

    The one decal in the game that is DARKER than the floor it lands on.
    Everything else people left behind is lighter than the soil so it can be
    seen at night; this is meant to be almost invisible until a lantern
    crosses it, at which point the sheen is the thing that says the machine
    above it was still running not that long ago.
    """
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    px = img.load()
    centre = (size - 1) / 2.0
    lobes = [
        (rng.uniform(-size * 0.18, size * 0.18), rng.uniform(-size * 0.12, size * 0.12),
         rng.uniform(size * 0.16, size * 0.30))
        for _ in range(rng.randint(2, 4))
    ]
    for y in range(size):
        for x in range(size):
            inside = False
            for ox, oy, r in lobes:
                dx = (x - centre - ox) / r
                dy = (y - centre - oy) / (r * 0.62)
                if dx * dx + dy * dy <= 1.0:
                    inside = True
                    break
            if not inside:
                continue
            if hash01(x, y, 261 + variant) < 0.12:
                px[x, y] = pick(BLUE, 0.30, x, y)
            else:
                px[x, y] = pick(PLANK_DARK, 0.10, x, y)
    return img


# --- sheet builders ---------------------------------------------------------
# Each returns (frames, frameWidth, frameHeight) so `make_scenery.build()` can
# pack them and write one manifest row. Kind-major, always.


def barrel_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    """The one sheet whose frames are PADDED, and the padding is the smash.

    A break throws pieces, and pieces need somewhere to go. Drawn at the
    barrel's own size the fragments hit the edge of the frame on the second
    frame and pile up against it, which reads as the sprite tearing rather
    than as a barrel coming apart. So the cylinder is drawn at its real size
    and then dropped into a larger canvas, bottom-centred, and everything the
    smash throws has half a tile of air on each side to travel through.

    Costs nothing at runtime: the prop is bottom-anchored on its contact point
    like every other one, so the extra pixels hang off the sides of a footprint
    that has not changed.
    """
    w, h = tile, round(tile * 1.25)
    pad_w, pad_h = round(tile * 1.75), round(tile * 1.6)
    rng = random.Random(seed)
    frames: list[Image.Image] = []
    for kind in range(BARREL_KINDS):
        body = make_barrel(w, h, kind, rng)
        intact = Image.new("RGBA", (pad_w, pad_h), TRANSPARENT)
        intact.paste(body, ((pad_w - w) // 2, pad_h - h), body)
        for frame in range(BARREL_FRAMES):
            frames.append(_explode(intact, frame, BARREL_FRAMES, kind * 31 + 17))
    return frames, pad_w, pad_h


def crate_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    """Eight crates, padded for the smash, in `CRATE_RECIPES` order.

    Padded for the same reason `barrel_strip` is — pieces need air to travel
    through — and the body is drawn TALLER than a barrel's because the tallest
    recipe is a stack of two. Both numbers are the frame's, not the footprint's:
    a crate still claims one tile, and the overhang hangs off it.
    """
    # THE AIR IS A RATIO, NOT A NUMBER. `barrel_strip` sets the rule — a smash
    # needs somewhere for its pieces to go — but the number that matters is how
    # much air there is RELATIVE TO THE BODY, and a crate is a third bigger
    # than a barrel in both directions. Copying the barrel's padding gave the
    # fragments 25% of the body's width to travel through against the barrel's
    # 37%, and they piled up against the frame edge from the fourth frame on,
    # which is the exact failure that padding exists to prevent.
    body_w, body_h = round(tile * 1.25), round(tile * 1.625)
    pad_w, pad_h = round(tile * 2.125), round(tile * 2.125)
    frames: list[Image.Image] = []
    for index, kind in enumerate(CRATE_RECIPES):
        body = make_crate(body_w, body_h, kind)
        intact = Image.new("RGBA", (pad_w, pad_h), TRANSPARENT)
        intact.paste(body, ((pad_w - body_w) // 2, pad_h - body_h), body)
        for frame in range(CRATE_FRAMES):
            frames.append(_explode(intact, frame, CRATE_FRAMES, index * 29 + 23))
    return frames, pad_w, pad_h


def box_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    w, h = tile, round(tile * 1.125)
    frames = [
        make_box(w, h, kind, frame, BOX_FRAMES)
        for kind in range(BOX_KINDS)
        for frame in range(BOX_FRAMES)
    ]
    return frames, w, h


def chest_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    w, h = round(tile * 1.25), round(tile * 1.25)
    frames = [
        make_chest(w, h, kind, frame, CHEST_FRAMES)
        for kind in range(CHEST_KINDS)
        for frame in range(CHEST_FRAMES)
    ]
    return frames, w, h


def stash_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    w, h = tile, round(tile * 1.25)
    frames = [
        make_stash(w, h, kind, frame, STASH_FRAMES)
        for kind in range(STASH_KINDS)
        for frame in range(STASH_FRAMES)
    ]
    return frames, w, h


def vehicle_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    w, h = tile * 4, round(tile * 2.5)
    frames = [
        make_vehicle(w, h, kind, frame, VEHICLE_FRAMES)
        for kind in range(VEHICLE_KINDS)
        for frame in range(VEHICLE_FRAMES)
    ]
    return frames, w, h


def altar_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    # Taller than it was. The slab now carries offerings, and they need
    # somewhere to stand that is not on top of the frame's own edge.
    w, h = round(tile * 1.75), round(tile * 1.75)
    frames = [
        make_altar(w, h, kind, frame, ALTAR_FRAMES)
        for kind in range(ALTAR_KINDS)
        for frame in range(ALTAR_FRAMES)
    ]
    return frames, w, h


def statue_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    # WIDER THAN A TILE, and deliberately. A statue's footprint is still one
    # tile — the shoulders overhang it the way a tree's canopy overhangs its
    # trunk — but a carved figure with arms out does not fit in sixteen pixels
    # without becoming a column again, and the arms are the read.
    w, h = round(tile * 1.25), round(tile * 2.375)
    frames = [
        make_statue(w, h, kind, seed + index)
        for index, kind in enumerate(STATUE_FIGURES)
    ]
    return frames, w, h


def bones_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    rng = random.Random(seed)
    frames = [make_bones(tile, variant, rng) for variant in range(BONES_VARIANTS)]
    return frames, tile, tile


def oil_strip(tile: int, seed: int) -> tuple[list[Image.Image], int, int]:
    size = tile * 2
    rng = random.Random(seed)
    frames = [make_oil(size, variant, rng) for variant in range(OIL_VARIANTS)]
    return frames, size, size
