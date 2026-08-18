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

STATUE_VARIANTS = 6
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
    """Rust, rot or moss, scattered over a band of an object.

    Everything in this forest has been standing in it for a year, and the
    difference between a prop and a prop somebody abandoned is entirely in
    this pass: unbroken paint reads as a car parked five minutes ago.
    """
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            if px[x, y][3] > 20 and hash01(x, y, salt) < amount:
                px[x, y] = pick(ramp, 0.30 + hash01(x, y, salt + 7) * 0.35, x, y)


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

    Lifted out of `make_scenery.make_crate_break` unchanged in behaviour and
    generalised on the salt, because a steel drum and a wooden barrel have to
    come apart on different noise or two barrels side by side burst in step.
    """
    if frame <= 0:
        return intact.copy()

    width, height = intact.size
    src = intact.load()
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    t = frame / max(frames - 1, 1)
    cx = (width - 1) / 2.0
    ground = height - 1

    for y in range(height):
        for x in range(width):
            pixel = src[x, y]
            if pixel[3] < 20:
                continue
            seed = hash01(x, y, salt)
            leave = seed < (t * 0.55 + 0.12)
            if t < 0.18:
                leave = seed < 0.08
            if leave:
                angle = seed * math.tau
                dist = t * (3.2 + seed * 7.5)
                nx = int(round(x + math.cos(angle) * dist))
                ny = int(round(y + math.sin(angle) * dist * 0.7 + t * 4.5))
                if ny > ground:
                    ny = ground
                    nx = int(round(cx + (nx - cx) * 0.4))
                fade = 1.0 - t * 0.85
                if 0 <= nx < width and 0 <= ny < height and fade > 0.12:
                    alpha = int(pixel[3] * fade)
                    if alpha > 20:
                        px[nx, ny] = (pixel[0], pixel[1], pixel[2], alpha)
            elif t < 0.72:
                if y < height * (0.28 + t * 0.55) and seed > 0.35:
                    continue
                px[x, y] = pixel

    if t > 0.55:
        for index in range(3):
            sx = int(cx + (hash01(salt, index, 41) - 0.5) * width * 0.7)
            sy = int(ground - hash01(salt, index, 43) * 2)
            if 0 <= sx < width and 0 <= sy < height:
                alpha = int(200 * (1.0 - t))
                if alpha > 30:
                    px[sx, sy] = (*pick(PLANK, 0.7 - t * 0.3, sx, sy)[:3], alpha)
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
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    body_h = int(height * 0.82)
    top = ground - body_h

    ramp = PLANK if kind == 0 else (STEEL if kind == 1 else RUST)
    band = STEEL if kind == 0 else CHROME

    for y in range(top, ground + 1):
        t = (y - top) / max(body_h, 1)
        # The bulge. A straight-sided cylinder reads as a bucket.
        half = width * (0.29 + 0.09 * math.sin(t * math.pi))
        for x in range(int(cx - half), int(cx + half) + 1):
            if not 0 <= x < width:
                continue
            shade = 0.63 - abs(x - cx) / max(half, 0.5) * 0.36 - t * 0.06
            px[x, y] = pick(ramp, shade + (hash01(x, y, 89 + kind) - 0.5) * 0.2, x, y)

    # Hoops. Two on wood, three on steel -- and they are the only horizontal
    # beat on the sprite, which is what stops the cylinder reading as a blob.
    hoops = (0.16, 0.72) if kind == 0 else (0.10, 0.44, 0.80)
    for hoop in hoops:
        y = int(top + body_h * hoop)
        half = width * (0.29 + 0.09 * math.sin(hoop * math.pi))
        for x in range(int(cx - half), int(cx + half) + 1):
            if 0 <= x < width and 0 <= y < height:
                px[x, y] = pick(band, 0.62 - abs(x - cx) / max(half, 0.5) * 0.3, x, y)

    # The lid, seen from just above: an ellipse of end grain or pressed steel.
    _disc(px, cx, top + 1.2, width * 0.29, ramp, 0.78, 91 + kind, width, height, squash=0.42)

    if kind == 2:
        # Hazard band. Two rows, the one warm thing on the object, and it is
        # the only reason a fuel drum reads differently from a rusty one.
        for y in (int(top + body_h * 0.30), int(top + body_h * 0.34)):
            half = width * 0.33
            for x in range(int(cx - half), int(cx + half) + 1):
                if 0 <= x < width and 0 <= y < height and (x + y) % 3:
                    px[x, y] = pick(HAZARD, 0.62, x, y)

    if kind == 0 and rng.random() < 0.6:
        # A stave sprung at the seam. Damage before anybody shot it.
        sx = int(cx + rng.uniform(-width * 0.2, width * 0.2))
        for y in range(top + 2, top + body_h // 2):
            if 0 <= sx < width:
                px[sx, y] = pick(PLANK_DARK, 0.5, sx, y)

    outline(img, OUTLINE_WOOD if kind == 0 else OUTLINE_COLD)
    return img


# --- boxes: the things you open ---------------------------------------------


def make_box(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """`kind`: 0 supply crate, 1 ammo case, 2 plastic tote. `frame` swings the lid.

    The lid hinges at the BACK and falls away from the camera, so an open box
    is a shallower silhouette with a bright rim where the inside catches what
    little light there is. Hinging it forward would hide the interior behind
    the lid, and the interior is the entire reason the animation exists.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    body = PLANK if kind == 0 else (OCHRE if kind == 1 else STEEL)
    trim = PLANK_DARK if kind == 0 else (STEEL if kind == 1 else CHROME)

    box_h = int(height * 0.58)
    half = width * 0.38
    top = ground - box_h

    # The body: courses of board with a dark seam, so it is a box and not a
    # rectangle of noise.
    for y in range(top, ground + 1):
        band = (y - top) % 3
        shade = 0.64 - band * 0.05 - (y - top) / max(box_h, 1) * 0.16
        if band == 2:
            shade -= 0.22
        for x in range(int(cx - half), int(cx + half) + 1):
            if not 0 <= x < width:
                continue
            px[x, y] = pick(
                body,
                shade - abs(x - cx) / half * 0.14 + (hash01(x, y, 51 + kind) - 0.5) * 0.2,
                x, y,
            )

    if kind == 0:
        # Diagonal brace. One mark, and it is what says "crate".
        for step in range(box_h):
            ix = int(cx - half + step * (2 * half) / max(box_h, 1))
            iy = ground - step
            if 0 <= ix < width and 0 <= iy < height:
                px[ix, iy] = pick(trim, 0.8, ix, iy)
    elif kind == 1:
        # Two latches and a stencil bar: an ammo case is a box with hardware.
        for lx in (int(cx - half * 0.55), int(cx + half * 0.55)):
            for y in range(top + 2, top + 5):
                if 0 <= lx < width and 0 <= y < height:
                    px[lx, y] = pick(trim, 0.75, lx, y)
        for x in range(int(cx - half * 0.6), int(cx + half * 0.6) + 1):
            y = ground - 3
            if 0 <= x < width and 0 <= y < height and x % 2 == 0:
                px[x, y] = pick(BONE, 0.55, x, y)
    else:
        # Ribbed sides. A tote is stiffened plastic and the ribs are its tell.
        for x in range(int(cx - half), int(cx + half) + 1, 3):
            for y in range(top + 1, ground):
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(trim, 0.52, x, y)

    # THE INSIDE. Opens as a widening band under the rim, with sparks in it.
    if open_t > 0.05:
        inner_h = max(1, int(open_t * box_h * 0.42))
        _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner_h, width, height)
        _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner_h,
               EMBER if kind != 2 else COLD, open_t, 57 + kind, width, height)

    # THE LID. A slab that lifts off the rim and tips back, shrinking in
    # apparent height as it goes over -- which is the only perspective cue a
    # 16-pixel sprite can afford.
    lift = open_t * (box_h * 0.32 + 1.5)
    lid_h = max(2, int(3 - open_t * 1.0))
    lid_half = half * (1.0 - open_t * 0.16)
    lid_y = int(top - lift)
    for y in range(lid_y, lid_y + lid_h + 1):
        for x in range(int(cx - lid_half), int(cx + lid_half) + 1):
            if 0 <= x < width and 0 <= y < height:
                px[x, y] = pick(
                    body,
                    0.80 - (y - lid_y) * 0.14 + (hash01(x, y, 61 + kind) - 0.5) * 0.16,
                    x, y,
                )
    # The hinge line stays welded to the back edge of the body the whole way.
    if open_t > 0.05:
        _line(px, int(cx - lid_half), lid_y + lid_h, int(cx - half), top,
              trim, 0.42, width, height)
        _line(px, int(cx + lid_half), lid_y + lid_h, int(cx + half), top,
              trim, 0.42, width, height)

    outline(img, OUTLINE_WOOD if kind != 2 else OUTLINE_COLD)
    return img


def make_chest(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """`kind`: 0 iron-bound chest, 1 strongbox. Slower, taller, always paying.

    Deliberately the ONE object in the forest with a curved lid. Everything
    else here is a flat top -- a box, a bin, a bonnet -- so the dome is doing
    the same job a rarity colour does in the HUD: it says, from across a dark
    clearing and before you can read anything else, that this one is different.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    body = PLANK if kind == 0 else STEEL
    bandmetal = BRASS if kind == 0 else CHROME

    box_h = int(height * 0.46)
    half = width * 0.40
    top = ground - box_h

    for y in range(top, ground + 1):
        band = (y - top) % 3
        shade = 0.60 - band * 0.05 - (y - top) / max(box_h, 1) * 0.14
        if band == 2:
            shade -= 0.20
        for x in range(int(cx - half), int(cx + half) + 1):
            if not 0 <= x < width:
                continue
            px[x, y] = pick(
                body,
                shade - abs(x - cx) / half * 0.12 + (hash01(x, y, 71 + kind) - 0.5) * 0.18,
                x, y,
            )
    # Iron straps down the front, and the lock plate between them.
    for bx in (int(cx - half * 0.62), int(cx + half * 0.62)):
        for y in range(top, ground + 1):
            if 0 <= bx < width and 0 <= y < height:
                px[bx, y] = pick(bandmetal, 0.55 + (y - top) * 0.01, bx, y)
    lock_y = top + max(1, box_h // 3)
    for y in range(lock_y, lock_y + 2):
        for x in range(int(cx - 1), int(cx + 2)):
            if 0 <= x < width and 0 <= y < height:
                px[x, y] = pick(bandmetal, 0.82, x, y)

    # THE HOLLOW, and it grows warm rather than just dark: a chest is the one
    # container that is guaranteed to be holding something, and the light
    # coming up out of it is the promise being made before the lid clears.
    if open_t > 0.04:
        inner_h = max(1, int(open_t * box_h * 0.7))
        _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner_h, width, height)
        _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner_h,
               EMBER, open_t, 73 + kind, width, height)

    # THE DOMED LID, hinged at the back and rolling up and over.
    lift = open_t * (box_h * 0.52 + 2.0)
    lid_half = half * (1.0 - open_t * 0.10)
    dome = max(1.0, (height - box_h) * 0.34 * (1.0 - open_t * 0.45))
    base_y = top - lift
    for x in range(int(cx - lid_half), int(cx + lid_half) + 1):
        if not 0 <= x < width:
            continue
        t = (x - (cx - lid_half)) / max(2 * lid_half, 1)
        arch = math.sin(t * math.pi) * dome
        for y in range(int(base_y - arch), int(base_y) + 2):
            if 0 <= y < height:
                px[x, y] = pick(
                    body,
                    0.84 - (base_y - y) / max(dome, 1) * 0.22
                    + (hash01(x, y, 77 + kind) - 0.5) * 0.16,
                    x, y,
                )
        # One brass rib over the crown, so the dome reads as bound and not
        # as a loaf of bread.
        if abs(t - 0.5) < 0.06:
            for y in range(int(base_y - arch), int(base_y) + 1):
                if 0 <= y < height:
                    px[x, y] = pick(bandmetal, 0.7, x, y)

    if open_t > 0.05:
        _line(px, int(cx - lid_half), int(base_y) + 1, int(cx - half), top,
              bandmetal, 0.4, width, height)
        _line(px, int(cx + lid_half), int(base_y) + 1, int(cx + half), top,
              bandmetal, 0.4, width, height)

    outline(img, OUTLINE_WOOD if kind == 0 else OUTLINE_COLD)
    return img


def make_stash(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """Small containers. `kind`: 0 mailbox, 1 suitcase, 2 freezer, 3 bin, 4 toolbox.

    These are the objects that make the map read as a place people commuted
    through rather than a place they fought in. A mailbox on a forest road is
    a question -- there was a house here once -- and it costs one 16-pixel
    sheet to ask it.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    if kind == 0:
        # Mailbox: a post with a drum on it. The door drops toward the camera.
        post_h = int(height * 0.55)
        for y in range(ground - post_h, ground + 1):
            for x in (int(cx - 1), int(cx)):
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(PLANK, 0.5, x, y)
        box_top = ground - post_h - int(height * 0.28)
        box_bot = ground - post_h + 1
        _fill(px, int(cx - width * 0.32), box_top, int(cx + width * 0.32), box_bot,
              STEEL, 0.6, 121, width, height)
        # Rounded shoulder, so it is a mailbox and not a shoebox on a stick.
        for x in range(int(cx - width * 0.32), int(cx + width * 0.32) + 1):
            if 0 <= x < width and 0 <= box_top < height:
                if abs(x - cx) / (width * 0.32) > 0.72:
                    px[x, box_top] = TRANSPARENT
        if open_t > 0.05:
            _hollow(px, int(cx - width * 0.26), box_top + 1,
                    int(cx + width * 0.26), box_bot - 1, width, height)
            _spark(px, int(cx - width * 0.26), box_top + 1,
                   int(cx + width * 0.26), box_bot - 1, BONE, open_t, 123, width, height)
            # The door, swung down and hanging off the bottom lip.
            drop = int(open_t * 4)
            _fill(px, int(cx + width * 0.18), box_bot - 1,
                  int(cx + width * 0.34), box_bot - 1 + drop,
                  CHROME, 0.55, 125, width, height)
        # The flag. Up when it is closed, because somebody was still waiting.
        flag_x = int(cx + width * 0.36)
        for y in range(box_top - 3, box_top + 1):
            if 0 <= flag_x < width and 0 <= y < height:
                px[flag_x, y] = pick(RED, 0.62, flag_x, y)
        outline(img, OUTLINE_COLD)
        return img

    if kind == 1:
        # Suitcase, lying on its side in the road. Lid opens away.
        case_h = int(height * 0.34)
        half = width * 0.42
        top = ground - case_h
        _fill(px, int(cx - half), top, int(cx + half), ground, LEATHER, 0.58, 131,
              width, height)
        for x in range(int(cx - half), int(cx + half) + 1, 4):
            for y in range(top, ground + 1):
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(LEATHER, 0.40, x, y)
        if open_t > 0.05:
            inner = max(1, int(open_t * case_h * 0.8))
            _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner, width, height)
            _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner,
                   BONE, open_t, 133, width, height)
        lift = open_t * (case_h * 0.55 + 2)
        lid_y = int(top - lift)
        lid_half = half * (1 - open_t * 0.1)
        _fill(px, int(cx - lid_half), lid_y, int(cx + lid_half), lid_y + 2,
              LEATHER, 0.74, 135, width, height)
        if open_t > 0.05:
            # The hinges. Without them the lid is a leather bar hovering over
            # a leather box, which is two objects rather than one opening.
            _line(px, int(cx - lid_half), lid_y + 2, int(cx - half), top,
                  LEATHER, 0.30, width, height)
            _line(px, int(cx + lid_half), lid_y + 2, int(cx + half), top,
                  LEATHER, 0.30, width, height)
        # Two brass catches, the only bright pixels on it.
        for lx in (int(cx - half * 0.5), int(cx + half * 0.5)):
            if 0 <= lx < width and 0 <= lid_y + 2 < height:
                px[lx, lid_y + 2] = pick(BRASS, 0.8, lx, lid_y + 2)
        outline(img, OUTLINE_WOOD)
        return img

    if kind == 2:
        # Chest freezer. The one container that is COLD inside, and the cold
        # is what tells you the power was on here recently enough to matter.
        body_h = int(height * 0.46)
        half = width * 0.44
        top = ground - body_h
        _fill(px, int(cx - half), top, int(cx + half), ground, CHROME, 0.52, 141,
              width, height)
        _fill(px, int(cx - half), ground - 1, int(cx + half), ground, STEEL, 0.3, 143,
              width, height)
        if open_t > 0.05:
            inner = max(1, int(open_t * body_h * 0.6))
            _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner, width, height)
            _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner,
                   COLD, open_t, 145, width, height)
        lift = open_t * (body_h * 0.5 + 2)
        lid_y = int(top - lift)
        _fill(px, int(cx - half), lid_y, int(cx + half), lid_y + 2, CHROME, 0.76, 147,
              width, height)
        if open_t > 0.05:
            _line(px, int(cx - half), lid_y + 2, int(cx - half), top,
                  STEEL, 0.35, width, height)
            _line(px, int(cx + half), lid_y + 2, int(cx + half), top,
                  STEEL, 0.35, width, height)
        outline(img, OUTLINE_COLD)
        return img

    if kind == 3:
        # Wheelie bin. The lid tips OFF rather than hinging: a bin lid that
        # stays attached at this size reads as a second bin balanced on top.
        body_h = int(height * 0.62)
        top = ground - body_h
        for y in range(top, ground + 1):
            t = (y - top) / max(body_h, 1)
            half = width * (0.30 + 0.08 * t)
            _fill(px, int(cx - half), y, int(cx + half), y, PAINT_VAN,
                  0.56 - t * 0.1, 151, width, height)
        if open_t > 0.05:
            half = width * 0.30
            inner = max(1, int(open_t * body_h * 0.45))
            _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner, width, height)
            _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner,
                   BONE, open_t * 0.6, 153, width, height)
        lid_half = width * 0.32
        lid_x = int(cx + open_t * width * 0.34)
        lid_y = int(top - 1 - open_t * 2)
        _fill(px, int(lid_x - lid_half * (1 - open_t * 0.4)), lid_y,
              int(lid_x + lid_half * (1 - open_t * 0.4)), lid_y + 1 + int(open_t * 1.5),
              PAINT_VAN, 0.72, 155, width, height)
        outline(img, OUTLINE_COLD)
        return img

    # Toolbox. Small, red, hinged at the back -- the cheapest silhouette here
    # and the one most likely to be holding something worth carrying.
    body_h = int(height * 0.30)
    half = width * 0.36
    top = ground - body_h
    _fill(px, int(cx - half), top, int(cx + half), ground, RED, 0.48, 161, width, height)
    _fill(px, int(cx - half), ground - 1, int(cx + half), ground, RUST, 0.4, 163, width, height)
    if open_t > 0.05:
        inner = max(1, int(open_t * body_h * 0.8))
        _hollow(px, int(cx - half + 1), top, int(cx + half - 1), top + inner, width, height)
        _spark(px, int(cx - half + 1), top, int(cx + half - 1), top + inner,
               CHROME, open_t, 165, width, height)
    lift = open_t * (body_h * 0.9 + 2)
    lid_y = int(top - lift)
    _fill(px, int(cx - half), lid_y, int(cx + half), lid_y + 1, RED, 0.7, 167, width, height)
    if open_t > 0.05:
        _line(px, int(cx - half), lid_y + 1, int(cx - half), top, RUST, 0.4, width, height)
        _line(px, int(cx + half), lid_y + 1, int(cx + half), top, RUST, 0.4, width, height)
    # Handle over the lid. Two pixels, and without them it is a red brick.
    for hx in (int(cx - 2), int(cx + 2)):
        if 0 <= hx < width and 0 <= lid_y - 1 < height:
            px[hx, lid_y - 1] = pick(CHROME, 0.7, hx, lid_y - 1)
    outline(img, OUTLINE_COLD)
    return img


# --- vehicles ---------------------------------------------------------------

VEHICLE_PAINT = (PAINT_SEDAN, PAINT_VAN, PAINT_AMBU, PAINT_POLICE, PAINT_TRUCK, PAINT_BUS)

#: THE PROFILE IS THE VEHICLE. Each row is the upper silhouette of one kind as
#: control points in fractions of the frame — left to right, y down from the
#: top — interpolated per column into the line the body is filled down from.
#:
#: This replaced six stacked rectangles, and the difference is the whole read.
#: A car and a van drawn as boxes are the same object in two palettes: you
#: cannot tell them apart at the edge of a lantern, so the map stops being a
#: place with an ambulance in it and becomes a map with dark blocks on it. A
#: bonnet that slopes, a windscreen that rakes back and a roof that stops
#: before the boot is a SEDAN from as far away as the pixels survive — and the
#: ambulance's box roof standing proud of its cab is legible at the same range,
#: which is what makes detouring for the medical drop table a decision.
VEHICLE_PROFILE: tuple[tuple[tuple[float, float], ...], ...] = (
    # 0 sedan: long bonnet, raked screen, roof over the middle third, and a
    #   BOOT — a flat deck behind the cabin rather than a slope to the tail.
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
    #   gave a wedge, and a wedge is not a car — the notch behind the cabin is
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
#: a bus — the extra axle is most of what says WEIGHT at this size.
VEHICLE_WHEELS: tuple[tuple[float, ...], ...] = (
    (0.20, 0.79), (0.19, 0.81), (0.18, 0.82), (0.19, 0.80),
    (0.13, 0.72, 0.85), (0.14, 0.74, 0.87),
)

#: Glazing, per kind: (x0, x1, y0, y1) in frame fractions. Punched into the
#: body after it is filled, so a window is a HOLE in the paint rather than a
#: rectangle sitting on top of it — which is the difference between a car with
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
#: packed into or trapped behind — a bonnet on the car that died on the road,
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

    # 1. THE BODY, one column at a time down from the profile. The vertical
    #    ramp is the whole of the form: a panel is bright where it turns
    #    toward the sky and dark where it tucks under itself, and a flat fill
    #    with an outline round it is a sticker of a car.
    for x in range(body_x0, body_x1 + 1):
        top = int(round(_profile_y(profile, x / max(width - 1, 1)) * height))
        depth = max(sill - top, 1)
        for y in range(top, sill + 1):
            t = (y - top) / depth
            shade = 0.74 - t * 0.46 + (hash01(x, y, 181 + kind) - 0.5) * 0.10
            px[x, y] = pick(paint, shade, x, y)

    # 2. The lit edge, one pixel per column, before anything is cut into it.
    _top_light(img, paint, 0.97)

    # 3. GLASS. Punched into the paint, dark, with one specular streak each.
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

    # 4. Panel gaps. Two vertical seams turn one long flank into doors, and
    #    doors are most of what says the mass has a scale a person fits in.
    for cut in (0.42, 0.60) if kind in (0, 3) else (0.36, 0.62, 0.80):
        cx = int(width * cut)
        if body_x0 < cx < body_x1:
            top = int(round(_profile_y(profile, cut) * height))
            _seam(px, cx, max(top + 1, belt + 1), cx, sill - 1, width, height, paint, 0.06)

    # 5. Wheels, and the arch shadow above each. The arch is what sinks a
    #    wheel into the body instead of parking it in front.
    for index, wx in enumerate(VEHICLE_WHEELS[kind % len(VEHICLE_WHEELS)]):
        cx = width * wx
        for ax in range(int(cx - radius - 1), int(cx + radius + 2)):
            ay = int(axle - math.sqrt(max(radius * radius + 2 -
                                          (ax - cx) ** 2, 0.0)))
            if 0 <= ax < width and 0 <= ay < height and px[ax, ay][3]:
                px[ax, ay] = pick(paint, 0.06, ax, ay)
        _wheel(px, cx, axle, radius, width, height, flat=(index == kind % 2))

    # 6. Bumpers and lamps. Four pixels of amber and red, and they are the only
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

    # 7. Per-kind markings. All of them one or two pixels wide.
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


def _plinth(px, cx: float, ground: int, half: float, width: int, height: int,
            ramp: Ramp, steps: int = 2) -> None:
    """The block a carved figure stands on.

    Every statue in the ring gets one, and it is doing two jobs. It says
    somebody PLACED this rather than that it grew here, which is the entire
    difference between the shrine and the rest of the forest; and it gives the
    figure a wide dark base, so a narrow silhouette at the edge of a lantern
    still plants on the ground instead of hovering over it.
    """
    for step in range(steps):
        y1 = ground - step * 2
        y0 = y1 - 1
        spread = half * (1.0 + 0.22 * step)
        _fill(px, int(cx - spread), y0, int(cx + spread), y1, ramp,
              0.42 - step * 0.10, 271 + step, width, height, grain=0.06)
    # The top step, in the figure's own stone. It is relit with everything
    # else by `_sculpt`, so nothing here needs to guess where the light is.
    top = ground - steps * 2
    _fill(px, int(cx - half), top, int(cx + half), top, ramp, 0.50, 273,
          width, height, grain=0.04)


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


def make_statue(width: int, height: int, variant: int, rng: random.Random) -> Image.Image:
    """Somebody carved this, and what they carved is WHAT IS OUT HERE.

    `variant`: 0 walker, 1 brute, 2 husk, 3 kneeling supplicant, 4 skull post,
    5 toppled walker.

    THE SUBJECT IS THE POINT, and it changed. These used to be totems, idols
    and a monolith — worked stone that meant "old" and nothing else, which
    made the shrine a texture rather than a statement. Carving the CREATURES
    instead costs the same pixels and says something the map could not say
    before: whoever built this had seen the things in these woods, stood in
    front of one long enough to get the shoulders right, and then built a ring
    of them around an altar and left offerings in the middle. The player meets
    the walker in stone before they meet it in the dark, and meets it again
    afterwards knowing what the ring was for.

    They are still the only objects in the forest TALLER than they are wide,
    and still the only worked stone. Everything else out here is a low
    horizontal mass — a car, a log, a barrel — so a column of narrow vertical
    shapes at the far end of a clearing does not read as more of the same. It
    reads as a question, which is as far as a landmark has to get you before
    the loot has to do the rest.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    ramp = GRANITE if variant % 2 == 0 else STONE

    def fx(f: float) -> int:
        return int(round(width * f))

    def fy(f: float) -> int:
        return int(round(height * f))

    # Every carving stands on a block, and the block eats the bottom sixth of
    # the frame — so the figure is authored above `feet`, never down to it.
    _plinth(px, cx, ground, width * 0.40, width, height, ramp)
    feet = ground - 5

    if variant == 0:
        # THE WALKER. Head narrow, shoulders WIDER than the head, both arms
        # out — the pose the player is going to see coming at them out of the
        # dark about ninety seconds after they first look at this.
        #
        # The head has to be narrower than the shoulders or the figure reads
        # as a cabinet. That single ratio is what makes a stack of stone
        # rectangles resolve into a body.
        head0, head1 = fy(0.12), fy(0.25)
        _fill(px, fx(0.34), head0, fx(0.64), head1, ramp, 0.62, 281, width, height)
        _carve(px, fx(0.35), fy(0.20), fx(0.63), fy(0.20), width, height)   # brow
        for ex in (fx(0.39), fx(0.58)):
            _chip(px, ex, fy(0.22), width, height)                          # sockets
        _carve(px, fx(0.40), fy(0.24), fx(0.58), fy(0.24), width, height)   # slack jaw
        _fill(px, fx(0.42), head1, fx(0.56), head1 + 1, ramp, 0.42, 282, width, height)
        # Shoulders rolled forward, then a torso tapering into the hips.
        for y in range(fy(0.28), fy(0.60)):
            t = (y - fy(0.28)) / max(fy(0.60) - fy(0.28), 1)
            half = width * (0.34 - 0.10 * t)
            _fill(px, int(cx - half), y, int(cx + half), y, ramp,
                  0.60 - t * 0.10, 283, width, height)
        # THE ARMS, and they are the tell. Reaching, so they hang clear of the
        # ribs with daylight carved between, and end in hands lower and
        # blockier than the elbows above them.
        for side in (-1, 1):
            ax = cx + side * width * 0.40
            _fill(px, int(ax - 1), fy(0.31), int(ax + 1), fy(0.58), ramp, 0.52,
                  285 + side, width, height)
            _fill(px, int(ax - 2), fy(0.56), int(ax + 2), fy(0.63), ramp, 0.66,
                  287 + side, width, height)
            _carve(px, int(cx + side * width * 0.31), fy(0.32),
                   int(cx + side * width * 0.31), fy(0.57), width, height)
        # Legs, apart, with the gap carved between them.
        for side in (-1, 1):
            lx = cx + side * width * 0.15
            _fill(px, int(lx - 2), fy(0.60), int(lx + 2), feet, ramp, 0.54,
                  289 + side, width, height)
        _carve(px, int(cx), fy(0.60), int(cx), feet, width, height)
    elif variant == 1:
        # THE BRUTE. Shoulders first, head last: the head is a detail on this
        # one and the shoulders ARE the silhouette. Same reading order as the
        # creature itself, which is the whole reason to carve it.
        _fill(px, fx(0.38), fy(0.16), fx(0.62), fy(0.30), ramp, 0.56, 291, width, height)
        for ex in (fx(0.43), fx(0.56)):
            _chip(px, ex, fy(0.24), width, height)
        # The TORSO stays inside the arms. Drawn as wide as the shoulders it
        # swallowed both of them and the figure came out as one slab: the
        # carve between an arm and a rib only works if there is a rib edge for
        # it to be beside.
        for y in range(fy(0.26), fy(0.40)):
            t = (y - fy(0.26)) / max(fy(0.40) - fy(0.26), 1)
            half = width * (0.26 + 0.06 * t)
            _fill(px, int(cx - half), y, int(cx + half), y, ramp,
                  0.66 - t * 0.08, 292, width, height)
        for y in range(fy(0.40), fy(0.66)):
            t = (y - fy(0.40)) / max(fy(0.66) - fy(0.40), 1)
            half = width * (0.32 - 0.08 * t)
            _fill(px, int(cx - half), y, int(cx + half), y, ramp,
                  0.58 - t * 0.10, 293, width, height)
        # Arms to the knees, thicker than the legs, hung OUTSIDE the ribs.
        for side in (-1, 1):
            ax = cx + side * width * 0.38
            _fill(px, int(ax - 1), fy(0.26), int(ax + 1), fy(0.70), ramp, 0.50,
                  294 + side, width, height)
            _fill(px, int(ax - 2), fy(0.68), int(ax + 2), fy(0.76), ramp, 0.64,
                  296 + side, width, height)
            # The shoulder that joins them, so the mass is one creature.
            _fill(px, int(min(cx, ax)), fy(0.28), int(max(cx, ax)), fy(0.34), ramp,
                  0.60, 297 + side, width, height)
            _carve(px, int(cx + side * width * 0.30), fy(0.36),
                   int(cx + side * width * 0.30), fy(0.68), width, height)
        for side in (-1, 1):
            lx = cx + side * width * 0.18
            _fill(px, int(lx - 3), fy(0.66), int(lx + 3), feet, ramp, 0.52,
                  298 + side, width, height)
        _carve(px, int(cx), fy(0.68), int(cx), feet, width, height)
    elif variant == 2:
        # THE HUSK. Everything the walker has, thinner, with the ribs cut in.
        # Parallel arcs are the one bone shape that survives being half in
        # shadow, which is why this variant is the one that still reads when a
        # lantern only catches an edge of it.
        _fill(px, fx(0.34), fy(0.10), fx(0.64), fy(0.23), ramp, 0.64, 301, width, height)
        _carve(px, fx(0.36), fy(0.21), fx(0.62), fy(0.21), width, height)
        for ex in (fx(0.40), fx(0.57)):
            _chip(px, ex, fy(0.18), width, height)
        _fill(px, fx(0.44), fy(0.23), fx(0.55), fy(0.28), ramp, 0.40, 302, width, height)
        # Ribcage: narrow, and carved rather than shaded.
        _fill(px, fx(0.34), fy(0.28), fx(0.66), fy(0.52), ramp, 0.58, 303, width, height)
        for index in range(4):
            ry = fy(0.31) + index * max(1, fy(0.05))
            _carve(px, fx(0.36), ry, fx(0.64), ry, width, height)
        # Hips, then the long thin limbs.
        _fill(px, fx(0.38), fy(0.52), fx(0.62), fy(0.62), ramp, 0.50, 304, width, height)
        for side in (-1, 1):
            ax = cx + side * width * 0.36
            # The shoulder first: an arm that starts in mid-air beside a
            # ribcage is a slab floating next to a statue, not a limb.
            _fill(px, int(min(cx, ax)), fy(0.28), int(max(cx, ax)), fy(0.32), ramp,
                  0.54, 304 + side, width, height)
            _fill(px, int(ax), fy(0.30), int(ax + side), fy(0.68), ramp, 0.48,
                  305 + side, width, height)
            _carve(px, int(cx + side * width * 0.28), fy(0.33),
                   int(cx + side * width * 0.28), fy(0.62), width, height)
            lx = cx + side * width * 0.14
            _fill(px, int(lx - 1), fy(0.62), int(lx + 1), feet, ramp, 0.52,
                  307 + side, width, height)
        _carve(px, int(cx), fy(0.62), int(cx), feet, width, height)
    elif variant == 3:
        # THE SUPPLICANT. A PERSON, kneeling, head down, hands on a planted
        # rod. The one figure in the ring that is not a creature, and it is
        # what turns a circle of monsters into a place where somebody knelt in
        # front of them. Without it the shrine is a trophy rack.
        # The head, bowed and clear of the shoulders. A hooded head merged
        # into the back gave one lump; the NECK GAP is what makes it a person
        # looking at the ground.
        _fill(px, fx(0.28), fy(0.20), fx(0.54), fy(0.31), ramp, 0.60, 311, width, height)
        _carve(px, fx(0.28), fy(0.29), fx(0.54), fy(0.29), width, height)   # bowed brow
        _carve(px, fx(0.30), fy(0.32), fx(0.52), fy(0.32), width, height)   # neck shadow
        # The back, curved forward over the knee. It leans LEFT, over the head,
        # so the silhouette is a hunch rather than a column with a lid.
        for y in range(fy(0.33), fy(0.58)):
            t = (y - fy(0.33)) / max(fy(0.58) - fy(0.33), 1)
            _fill(px, fx(0.26) + int(t * width * 0.06), y,
                  fx(0.62) + int(t * width * 0.10), y, ramp,
                  0.58 - t * 0.08, 312, width, height)
        # The kneeling mass: one knee down and forward, the other folded under,
        # with the carve between them doing the work of two shapes.
        _fill(px, fx(0.22), fy(0.58), fx(0.78), feet, ramp, 0.50, 313, width, height)
        _carve(px, fx(0.50), fy(0.60), fx(0.50), feet, width, height)
        _carve(px, fx(0.22), fy(0.66), fx(0.49), fy(0.66), width, height)
        # The rod, planted at arm's length, and the hands folded over it. It is
        # the only STRAIGHT line in the figure, which is what makes the rest of
        # it read as slumped — and the ARM has to reach it, or the rod is a
        # post that happens to be standing next to somebody.
        _fill(px, fx(0.80), fy(0.26), fx(0.86), feet, ramp, 0.68, 314, width, height)
        _fill(px, fx(0.52), fy(0.36), fx(0.82), fy(0.41), ramp, 0.56, 316, width, height)
        _fill(px, fx(0.68), fy(0.40), fx(0.90), fy(0.46), ramp, 0.74, 315, width, height)
        _carve(px, fx(0.68), fy(0.47), fx(0.90), fy(0.47), width, height)
    elif variant == 4:
        # THE SKULL POST. Not carved and not stone — a pole somebody drove in
        # and tied a head to. The most direct sentence on the map, and the one
        # object at the shrine that a person could have made in an afternoon.
        for y in range(fy(0.26), ground + 1):
            for x in (int(cx - 1), int(cx)):
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(PLANK, 0.46 + (hash01(x, y, 321) - 0.5) * 0.2, x, y)
        sy = fy(0.18)
        _disc(px, cx, sy, width * 0.22, BONE, 0.74, 322, width, height, squash=1.15)
        for ex in (int(cx - 2), int(cx + 1)):
            if 0 <= ex < width and 0 <= sy < height:
                px[ex, sy] = pick(PLANK_DARK, 0.16, ex, sy)
        # The jaw, one row of teeth. Four dark pixels, and it is what makes the
        # disc a skull instead of a stone on a stick.
        for tx in range(int(cx - 2), int(cx + 3), 2):
            if 0 <= tx < width and 0 <= sy + 3 < height and px[tx, sy + 3][3]:
                px[tx, sy + 3] = pick(PLANK_DARK, 0.18, tx, sy + 3)
        for by in (fy(0.30), fy(0.34)):
            _line(px, int(cx - 2), by, int(cx + 2), by, ROPE, 0.68, width, height)
        # Two small bones lashed crossways below it.
        _line(px, int(cx - 4), fy(0.40), int(cx + 4), fy(0.44), BONE, 0.58, width, height)
        _line(px, int(cx - 4), fy(0.44), int(cx + 4), fy(0.40), BONE, 0.58, width, height)
    else:
        # THE TOPPLED WALKER. The same figure as variant 0, snapped at the
        # shins, its top half lying across its own base. The one variant that
        # says TIME rather than intent — and saying it with a recognisable
        # subject is worth more than a broken column, because the player can
        # see what it used to be.
        # THE STUMPS STAY UP, on the right of the frame, and the fallen half
        # lies to the LEFT of them. Drawn on top of each other the two shapes
        # became one heap and the whole sentence was lost: a break only reads
        # if the player can see both ends of it at once.
        # The legs still standing, snapped mid-thigh, on the right of the base.
        _fill(px, fx(0.58), fy(0.46), fx(0.70), feet, ramp, 0.54, 331, width, height)
        _fill(px, fx(0.74), fy(0.42), fx(0.86), feet, ramp, 0.52, 332, width, height)
        _carve(px, fx(0.72), fy(0.50), fx(0.72), feet, width, height)
        for x in range(fx(0.58), fx(0.87)):
            if 0 <= x < width and hash01(x, 7, 333) < 0.6:
                _chip(px, x, fy(0.45), width, height)
                _chip(px, x, fy(0.41), width, height)
        # The upper half lying across the front of its own base, head at the
        # far end, one arm still out in front of it — the pose it fell in. A
        # player who has met variant 0 standing knows what came off this.
        _fill(px, fx(0.14), fy(0.70), fx(0.56), fy(0.80), ramp, 0.58, 334, width, height)
        _fill(px, fx(0.04), fy(0.66), fx(0.20), fy(0.78), ramp, 0.68, 335,
              width, height)                                          # the head
        _carve(px, fx(0.21), fy(0.67), fx(0.21), fy(0.79), width, height)  # the neck
        _fill(px, fx(0.20), fy(0.81), fx(0.50), fy(0.85), ramp, 0.44, 336,
              width, height)                                          # the arm
        # Rubble between the two halves. Four pixels, and they are what say
        # this FELL rather than that it was laid down here.
        for index in range(4):
            rx = fx(0.50) + index * 2
            ry = feet - (index % 2)
            if 0 <= rx < width and 0 <= ry < height:
                px[rx, ry] = pick(ramp, 0.40, rx, ry)

    # The light, once, over whatever the variant built. It belongs to the
    # silhouette rather than to each shape that happened to make it, which is
    # why it runs here instead of inside the fills — and why moving an arm two
    # pixels does not mean re-authoring its shading.
    _sculpt(img, ramp)

    # WEATHER. Lichen on the shaded lower two thirds, chips off the corners.
    # Unweathered stone in a wet forest is the one thing that would make these
    # read as freshly placed, which is the opposite of everything else here.
    for _ in range(rng.randint(5, 9)):
        lx = int(rng.uniform(0, width))
        ly = int(rng.uniform(height * 0.35, height))
        if 0 <= lx < width and 0 <= ly < height and px[lx, ly][3]:
            px[lx, ly] = pick(MOSS, rng.uniform(0.35, 0.75), lx, ly)
    for _ in range(rng.randint(2, 4)):
        _chip(px, int(rng.uniform(0, width)), int(rng.uniform(height * 0.1, height * 0.7)),
              width, height)

    _ground_dark(img, rows=1, drop=0.7)
    outline(img, OUTLINE_STONE)
    return img


def make_altar(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """The one thing at a shrine you open. `kind`: 0 stone altar, 1 bone cairn.

    The lid SLIDES rather than hinges, and it slides sideways rather than up.
    Everything else in the game that opens hinges, so a slab grinding aside is
    a different verb even though it is the same key -- and it is the only
    animation here that uncovers a hole in the GROUND rather than the inside
    of a container.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))

    base_h = int(height * 0.34)
    base_top = ground - base_h
    half = width * 0.40

    # The plinth: a stepped base, so it reads as built and not as dropped.
    _fill(px, int(cx - half), base_top, int(cx + half), ground, GRANITE, 0.48, 241,
          width, height)
    _fill(px, int(cx - half * 1.14), ground - 2, int(cx + half * 1.14), ground,
          GRANITE, 0.36, 243, width, height)

    if kind == 1:
        # A cairn of bones piled around the plinth. Same silhouette, and the
        # difference is what the place cost.
        for index in range(9):
            bx = cx + math.cos(index * 1.9) * half * 1.05
            by = ground - 1 - (index % 3)
            _line(px, int(bx), int(by), int(bx + 3), int(by - 1), BONE, 0.5, width, height)

    # The hollow under the slab.
    hollow_top = base_top - 3
    if open_t > 0.03:
        _hollow(px, int(cx - half + 2), hollow_top, int(cx + half - 2), base_top - 1,
                width, height)
        _spark(px, int(cx - half + 2), hollow_top, int(cx + half - 2), base_top - 1,
               EMBER, open_t, 245 + kind, width, height)

    # THE SLAB, ground sideways off the mouth.
    slide = int(open_t * half * 1.5)
    slab_x0 = int(cx - half + slide)
    slab_x1 = int(cx + half + slide)
    _fill(px, slab_x0, hollow_top - 1, slab_x1, base_top - 1, STONE, 0.72, 247,
          width, height)
    # A carved rim on the slab's top edge, so a flat grey bar reads as worked.
    for x in range(slab_x0, slab_x1 + 1, 3):
        if 0 <= x < width and 0 <= hollow_top - 1 < height:
            px[x, hollow_top - 1] = pick(STONE, 0.34, x, hollow_top - 1)

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
    w, h = tile, round(tile * 1.25)
    rng = random.Random(seed)
    frames: list[Image.Image] = []
    for kind in range(BARREL_KINDS):
        intact = make_barrel(w, h, kind, rng)
        for frame in range(BARREL_FRAMES):
            frames.append(_explode(intact, frame, BARREL_FRAMES, kind * 31 + 17))
    return frames, w, h


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
    w, h = round(tile * 1.75), round(tile * 1.5)
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
    rng = random.Random(seed)
    frames = [make_statue(w, h, variant, rng) for variant in range(STATUE_VARIANTS)]
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
