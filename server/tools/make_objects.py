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
# are allowed a hue the forest never has. They are still dark: a white
# ambulance at full value would be the brightest object on a night map and
# would read as lit rather than as painted.

PLANK: Ramp = [rgb(c) for c in ("#1b1710", "#272118", "#342c20", "#413628", "#4f4232")]
PLANK_DARK: Ramp = [rgb(c) for c in ("#100d09", "#181410", "#211b15", "#2b2419")]
STEEL: Ramp = [rgb(c) for c in ("#16181b", "#212429", "#2e3238", "#3d4249", "#4d535b", "#666d77")]
RUST: Ramp = [rgb(c) for c in ("#241410", "#331c15", "#44251b", "#5a3323", "#70432c")]
HAZARD: Ramp = [rgb(c) for c in ("#3a2a0c", "#5c4210", "#8a6417", "#b8871f")]
STONE: Ramp = [rgb(c) for c in ("#1e1d21", "#2a292e", "#37353b", "#454249", "#545059", "#666270")]
GRANITE: Ramp = [rgb(c) for c in ("#191a1d", "#242529", "#313338", "#3f4249", "#4f535c")]
BONE: Ramp = [rgb(c) for c in ("#38362e", "#49463c", "#5c584b", "#726d5c", "#8a8471", "#a49d86")]
ROPE: Ramp = [rgb(c) for c in ("#2b2418", "#3a3120", "#4a3f29", "#5b4e33")]
GLASS: Ramp = [rgb(c) for c in ("#12171c", "#1a232b", "#25323d", "#33454f", "#476068")]
TYRE: Ramp = [rgb(c) for c in ("#0a0b0c", "#111214", "#181a1d", "#212428")]
CHROME: Ramp = [rgb(c) for c in ("#2a2e33", "#3d434a", "#555c65", "#6f7883", "#8d97a3")]
BRASS: Ramp = [rgb(c) for c in ("#332208", "#523710", "#7a541b", "#a37628", "#c69a3c")]
OCHRE: Ramp = [rgb(c) for c in ("#2c1d0d", "#402a13", "#573a1b", "#6f4c25", "#87602f")]
LEATHER: Ramp = [rgb(c) for c in ("#1a1310", "#251b16", "#31241c", "#3f2f24", "#534033")]

# Vehicle paint. Each is a body ramp; the roof gets the top step, the flank the
# middle, the shadowed sill the bottom.
PAINT_SEDAN: Ramp = [rgb(c) for c in ("#101820", "#18242f", "#22323f", "#2e4250", "#3b5462")]
PAINT_VAN: Ramp = [rgb(c) for c in ("#1a1a18", "#262622", "#34342e", "#43423a", "#535148")]
PAINT_AMBU: Ramp = [rgb(c) for c in ("#1b1d1f", "#26292c", "#343a3e", "#454b50", "#5a6165")]
PAINT_POLICE: Ramp = [rgb(c) for c in ("#0c0d10", "#141619", "#1e2126", "#2a2e34", "#383d45")]
PAINT_TRUCK: Ramp = [rgb(c) for c in ("#1d1410", "#2b1e17", "#3b2b20", "#4c392a", "#5d4835")]
PAINT_BUS: Ramp = [rgb(c) for c in ("#2a2110", "#3c3018", "#524122", "#68532c", "#7d6537")]

# Signal colours. Used in single pixels only -- a red cross, a light bar, the
# ember inside an opened chest. Anything larger and the map stops being dark.
RED: Ramp = [rgb(c) for c in ("#3a0d0c", "#5e1512", "#8a1f19", "#b52c22")]
BLUE: Ramp = [rgb(c) for c in ("#0d1a3a", "#153060", "#1f4a8a", "#2c6ab5")]
EMBER: Ramp = [rgb(c) for c in ("#3a2410", "#6a4018", "#a06820", "#d4a040", "#f2c14b")]
COLD: Ramp = [rgb(c) for c in ("#16232b", "#1f3644", "#2c505f", "#3d707f", "#5a97a4")]

OUTLINE_WOOD = rgb("#0c0a07")
OUTLINE_COLD = rgb("#0a0b0d")
OUTLINE_STONE = rgb("#0b0b0e")

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


def _wheel(px, cx: float, cy: float, r: float, width: int, height: int) -> None:
    _disc(px, cx, cy, r, TYRE, 0.55, 211, width, height)
    _disc(px, cx, cy, max(1.0, r * 0.45), CHROME, 0.6, 213, width, height)


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


def _bar(px, x0: int, y: int, x1: int, width: int, height: int,
         ramps: tuple[Ramp, Ramp]) -> None:
    """A roof light bar: alternating pixels of two signal colours, UNLIT.

    Unlit matters. A flashing bar would be the brightest moving thing on a
    dark map and would read as an active vehicle, which is the one thing none
    of these are.
    """
    for index, x in enumerate(range(x0, x1 + 1)):
        if 0 <= x < width and 0 <= y < height:
            px[x, y] = pick(ramps[(index // 2) % 2], 0.5, x, y)
        if 0 <= x < width and 0 <= y + 1 < height:
            px[x, y + 1] = pick(CHROME, 0.35, x, y + 1)


def make_vehicle(width: int, height: int, kind: int, frame: int, frames: int) -> Image.Image:
    """A dead vehicle, seen from the side and slightly above. `frame` opens it.

    THE SILHOUETTE IS THE WHOLE ASSET. At this size nobody reads a badge; what
    they read across a dark clearing is a long low mass with two black holes
    under it, and then the ROOFLINE tells them which one it is -- flat and low
    is a car, a tall box is a van, a tall box with a bar on top is an
    ambulance, a cab with a bed behind it is a lorry, a very long box with a
    row of windows is a bus.

    What opens is the compartment that vehicle would actually have somebody
    still in it or still packed: a bonnet on a car that died on the road, rear
    doors on the vans, the bed on a lorry, the luggage bay on a bus. It lifts
    from the front edge and the black underneath is the reward -- or the
    warning.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    ground = height - 1
    open_t = _ease(frame / max(frames - 1, 1))
    paint = VEHICLE_PAINT[kind % len(VEHICLE_PAINT)]

    # Chassis geometry per kind, in fractions of the frame. `body_top` is the
    # bonnet line; `cab_top` is the roof.
    if kind == 0:      # sedan
        x0, x1 = width * 0.05, width * 0.95
        body_top, cab_top = height * 0.52, height * 0.28
        cab0, cab1 = width * 0.30, width * 0.72
    elif kind == 1:    # van
        x0, x1 = width * 0.06, width * 0.94
        body_top, cab_top = height * 0.44, height * 0.14
        cab0, cab1 = width * 0.20, width * 0.94
    elif kind == 2:    # ambulance
        x0, x1 = width * 0.04, width * 0.96
        body_top, cab_top = height * 0.42, height * 0.10
        cab0, cab1 = width * 0.30, width * 0.96
    elif kind == 3:    # police cruiser
        x0, x1 = width * 0.04, width * 0.96
        body_top, cab_top = height * 0.52, height * 0.28
        cab0, cab1 = width * 0.28, width * 0.70
    elif kind == 4:    # lorry
        x0, x1 = width * 0.03, width * 0.97
        body_top, cab_top = height * 0.44, height * 0.12
        cab0, cab1 = width * 0.04, width * 0.38
    else:              # bus
        x0, x1 = width * 0.02, width * 0.98
        body_top, cab_top = height * 0.40, height * 0.06
        cab0, cab1 = width * 0.04, width * 0.96

    sill = ground - max(2, int(height * 0.12))

    # 1. the flank
    _fill(px, int(x0), int(body_top), int(x1), sill, paint, 0.58, 181 + kind,
          width, height, grain=0.14)
    # 2. the sill, one step darker: it is the shadow the body throws on itself
    #    and it is what plants the vehicle instead of floating it.
    _fill(px, int(x0), sill, int(x1), ground - 1, paint, 0.24, 183 + kind,
          width, height, grain=0.10)
    # 3. the cabin
    _fill(px, int(cab0), int(cab_top), int(cab1), int(body_top), paint, 0.70, 185 + kind,
          width, height, grain=0.12)
    # 4. glass. Windows are DARK, not bright: there is nothing behind them,
    #    and a lit window on an abandoned car is a promise the map cannot keep.
    glass_top = int(cab_top) + 2
    glass_bot = int(body_top) - 2
    if glass_bot > glass_top:
        if kind in (1, 2, 4):
            _fill(px, int(cab0) + 2, glass_top, int(cab0 + (cab1 - cab0) * 0.32), glass_bot,
                  GLASS, 0.18, 187, width, height)
        elif kind == 5:
            # A row of bus windows with pillars between them.
            span = cab1 - cab0
            for index in range(6):
                wx0 = int(cab0 + 2 + span * index / 6.0)
                wx1 = int(cab0 + span * (index + 0.86) / 6.0)
                _fill(px, wx0, glass_top, wx1, glass_bot, GLASS, 0.18, 187 + index,
                      width, height)
        else:
            _fill(px, int(cab0) + 2, glass_top, int(cab1) - 2, glass_bot,
                  GLASS, 0.18, 187, width, height)
        # One pale streak along the top of the screen. The only specular here.
        for x in range(int(cab0) + 3, int(cab1) - 3, 5):
            if 0 <= x < width and 0 <= glass_top < height:
                px[x, glass_top] = pick(CHROME, 0.62, x, glass_top)

    # 5. wheels, sunk into the sill so the arches read
    r = max(2.0, height * 0.13)
    front = x0 + (x1 - x0) * (0.18 if kind != 4 else 0.14)
    rear = x0 + (x1 - x0) * (0.82 if kind != 4 else 0.80)
    _wheel(px, front, ground - r * 0.75, r, width, height)
    _wheel(px, rear, ground - r * 0.75, r, width, height)
    if kind in (4, 5):
        _wheel(px, rear - r * 1.7, ground - r * 0.75, r, width, height)

    # 6. per-kind markings, all of them one or two pixels wide
    if kind == 2:
        # Red cross and a light bar. The cross is the single most legible
        # symbol available at 16px and it is worth its four pixels: it is what
        # makes a player detour for a medical box.
        mx = int(x0 + (x1 - x0) * 0.62)
        my = int(body_top + (sill - body_top) * 0.45)
        for offset in range(-2, 3):
            if 0 <= mx + offset < width and 0 <= my < height:
                px[mx + offset, my] = pick(RED, 0.85, mx + offset, my)
            if 0 <= mx < width and 0 <= my + offset < height:
                px[mx, my + offset] = pick(RED, 0.85, mx, my + offset)
        _bar(px, int(cab0) + 2, int(cab_top) - 2, int(cab0 + (cab1 - cab0) * 0.5),
             width, height, (RED, BLUE))
    elif kind == 3:
        _bar(px, int(cab0) + 1, int(cab_top) - 2, int(cab1) - 1, width, height, (BLUE, RED))
        # The pale door panel a cruiser has and a sedan does not.
        _fill(px, int(x0 + (x1 - x0) * 0.36), int(body_top) + 2,
              int(x0 + (x1 - x0) * 0.66), sill - 2, CHROME, 0.55, 191, width, height)
    elif kind == 4:
        # A load still strapped on the bed. Half the reason to walk to a lorry.
        bed0 = int(x0 + (x1 - x0) * 0.44)
        bed1 = int(x1) - 2
        _fill(px, bed0, int(body_top) - 5, bed1, int(body_top) - 1, PLANK, 0.5, 193,
              width, height)
        for x in range(bed0, bed1, 5):
            _line(px, x, int(body_top) - 5, x, int(body_top) - 1, ROPE, 0.6, width, height)

    # 7. THE COMPARTMENT. Cut a dark mouth into the body and lift its panel
    #    off the front edge of it.
    if kind in (0, 3):
        px0, px1 = int(x0) + 1, int(x0 + (x1 - x0) * 0.26)   # bonnet
        panel_top = int(body_top)
    elif kind in (1, 2):
        px0, px1 = int(x1 - (x1 - x0) * 0.24), int(x1) - 1   # rear doors
        panel_top = int(cab_top) + 3
    elif kind == 4:
        px0, px1 = int(x0 + (x1 - x0) * 0.46), int(x0 + (x1 - x0) * 0.74)
        panel_top = int(body_top) - 1
    else:
        px0, px1 = int(x0 + (x1 - x0) * 0.32), int(x0 + (x1 - x0) * 0.58)
        panel_top = int(body_top) + 1

    if open_t > 0.04:
        mouth_bot = min(sill - 1, panel_top + max(2, int((sill - panel_top) * 0.7)))
        _hollow(px, px0 + 1, panel_top, px1 - 1, mouth_bot, width, height)
        _spark(px, px0 + 1, panel_top, px1 - 1, mouth_bot, EMBER, open_t * 0.75,
               197 + kind, width, height)

    lift = open_t * (height * 0.13 + 1)
    plate_y = int(panel_top - lift)
    plate_h = max(2, int(4 - open_t * 1.2))
    _fill(px, px0, plate_y, px1, plate_y + plate_h, paint, 0.86, 199 + kind,
          width, height, grain=0.12)
    if open_t > 0.05:
        # The hinge, still holding at the far edge, so the panel is attached.
        _line(px, px1, plate_y + plate_h, px1, panel_top, CHROME, 0.4, width, height)

    outline(img, OUTLINE_COLD)
    return img


# --- the tribal ground ------------------------------------------------------


def make_statue(width: int, height: int, variant: int, rng: random.Random) -> Image.Image:
    """Somebody carved this. `variant`: 0 totem, 1 idol, 2 figure, 3 broken,
    4 skull post, 5 monolith.

    These are the only objects in the forest that are TALLER than they are
    wide and made of worked stone, and both halves of that are on purpose.
    Everything else out here is a low horizontal mass -- a car, a log, a
    barrel -- so a narrow vertical shape at the far end of a clearing does not
    read as more of the same. It reads as a question, which is exactly how far
    a landmark has to get you before the loot has to do the rest.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    cx = (width - 1) / 2.0
    ground = height - 1
    ramp = GRANITE if variant % 2 == 0 else STONE

    if variant == 0:
        # Totem: a stacked column of carved faces. Each notch is a face, and
        # the notches are what make it carved rather than quarried.
        half = width * 0.30
        top = int(height * 0.06)
        _fill(px, int(cx - half), top, int(cx + half), ground, ramp, 0.55, 221, width, height)
        for index in range(4):
            fy = top + 3 + index * max(1, int((ground - top - 4) / 4))
            for x in range(int(cx - half), int(cx + half) + 1):
                if 0 <= x < width and 0 <= fy < height:
                    px[x, fy] = pick(ramp, 0.20, x, fy)
            for ex in (int(cx - 2), int(cx + 2)):
                if 0 <= ex < width and 0 <= fy + 2 < height:
                    px[ex, fy + 2] = pick(ramp, 0.90, ex, fy + 2)
        # Wings at the crown, which is the tell at a glance.
        for wx in range(int(cx - half * 1.9), int(cx + half * 1.9) + 1):
            if 0 <= wx < width and 0 <= top + 1 < height:
                px[wx, top + 1] = pick(ramp, 0.68, wx, top + 1)
    elif variant == 1:
        # Squat idol: a wide crouching mass with a heavy brow.
        for y in range(int(height * 0.30), ground + 1):
            t = (y - height * 0.30) / max(height * 0.70, 1)
            half = width * (0.22 + 0.20 * t)
            _fill(px, int(cx - half), y, int(cx + half), y, ramp,
                  0.58 - t * 0.12, 223, width, height)
        brow = int(height * 0.38)
        for x in range(int(cx - width * 0.26), int(cx + width * 0.26) + 1):
            if 0 <= x < width and 0 <= brow < height:
                px[x, brow] = pick(ramp, 0.18, x, brow)
        for ex in (int(cx - 2), int(cx + 2)):
            if 0 <= ex < width and 0 <= brow + 2 < height:
                px[ex, brow + 2] = pick(BONE, 0.55, ex, brow + 2)
    elif variant == 2:
        # A standing figure, robed. Narrow, tall, no face -- the absence of a
        # face is the effect.
        for y in range(int(height * 0.10), ground + 1):
            # Clamped before the fractional power: `int()` on the start row can
            # land a hair above the float it came from, and a negative base
            # under a non-integer exponent is a complex number, not a taper.
            t = clamp01((y - height * 0.10) / max(height * 0.90, 1))
            half = width * (0.13 + 0.22 * t ** 1.4)
            _fill(px, int(cx - half), y, int(cx + half), y, ramp,
                  0.60 - t * 0.14, 225, width, height)
        _disc(px, cx, height * 0.13, width * 0.16, ramp, 0.66, 227, width, height)
    elif variant == 3:
        # Broken: the base still standing and the top lying beside it. The one
        # variant that says TIME rather than intent.
        stump = int(height * 0.52)
        half = width * 0.24
        _fill(px, int(cx - half), stump, int(cx + half), ground, ramp, 0.52, 229, width, height)
        for x in range(int(cx - half), int(cx + half) + 1):
            if 0 <= x < width and 0 <= stump < height:
                px[x, stump] = pick(ramp, 0.86, x, stump)
        _fill(px, int(cx - width * 0.44), ground - 3, int(cx - half) - 1, ground - 1,
              ramp, 0.44, 231, width, height)
    elif variant == 4:
        # A pole with a skull on it. The most direct sentence on the map:
        # somebody put this here, and they meant it as a boundary.
        for y in range(int(height * 0.24), ground + 1):
            for x in (int(cx - 1), int(cx)):
                if 0 <= x < width and 0 <= y < height:
                    px[x, y] = pick(PLANK, 0.44, x, y)
        sy = int(height * 0.20)
        _disc(px, cx, sy, width * 0.24, BONE, 0.72, 233, width, height, squash=1.15)
        for ex in (int(cx - 2), int(cx + 1)):
            if 0 <= ex < width and 0 <= sy < height:
                px[ex, sy] = pick(PLANK_DARK, 0.2, ex, sy)
        if 0 <= int(cx) < width and 0 <= sy + 3 < height:
            px[int(cx), sy + 3] = pick(PLANK_DARK, 0.2, int(cx), sy + 3)
        for offset in range(-1, 2):
            bx = int(cx + offset)
            by = int(height * 0.44)
            if 0 <= bx < width and 0 <= by < height:
                px[bx, by] = pick(ROPE, 0.6, bx, by)
    else:
        # Monolith. A slab with a carved spiral. It does not represent
        # anything, and that is the point of keeping one in the set.
        half = width * 0.34
        top = int(height * 0.14)
        _fill(px, int(cx - half), top, int(cx + half), ground, ramp, 0.50, 235, width, height)
        for step in range(18):
            angle = step * 0.7
            radius = 1.0 + step * 0.16
            gx = int(cx + math.cos(angle) * radius)
            gy = int(height * 0.42 + math.sin(angle) * radius * 1.5)
            if 0 <= gx < width and 0 <= gy < height and px[gx, gy][3]:
                px[gx, gy] = pick(ramp, 0.88, gx, gy)

    # Lichen. Three or four pale specks, because unweathered stone in a wet
    # forest is the one thing that would make these read as freshly placed.
    for _ in range(rng.randint(3, 6)):
        lx = int(rng.uniform(0, width))
        ly = int(rng.uniform(height * 0.3, height))
        if 0 <= lx < width and 0 <= ly < height and px[lx, ly][3]:
            px[lx, ly] = pick(BONE, 0.34, lx, ly)

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
    w, h = tile, round(tile * 2.25)
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
