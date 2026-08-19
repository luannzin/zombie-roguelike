#!/usr/bin/env python3
"""Asset pipeline: THE UPGRADE MACHINE — a slot cabinet somebody dragged into
the woods and wired to a car battery.

Output (assets/processed/machine/):
    cabinet.png    2 frames, 48x72   PROP   — idle, and settled after a pull
    strip.png      1 frame, 10x160   PART   — the REEL BAND: ten cells, looped
    lever.png      6 frames, 16x34   PART   — the arm, up to fully pulled
    marquee.png   10 frames, 54x24   VFX    — loop, the crown lights chasing
    window.png     6 frames, 40x20   VFX    — loop, the backlight behind the reels
    burst.png     12 frames, 64x64   VFX    — one-shot, the payout flash
    manifest.json

WHY IT IS A WRECK AND NOT A CASINO MACHINE.
Everything else in this forest is something the world left behind, and a clean
Vegas cabinet would be the one object in the game that came from a different
one. So it is DENTED, its chrome is gone, one corner of the marquee is smashed,
and there is a car battery on the ground beside it with a cable running up into
the base. That cable is the whole story: somebody found this thing, hauled it
here, and got it working — which is a better answer to "why is there a slot
machine in a shop in a forest" than any sign could be.

WHY IT IS STILL UNMISTAKABLY A SLOT MACHINE.
Three lit windows in a row, a crown of bulbs, a lever on the right and a tray
at the bottom. Those four are the whole vocabulary and none of them may be
subtle — a player has to read it from across the clearing, before the prompt,
before the tooltip, and think *that thing is for me*.

IT IS A BAND, NOT A FRAME NUMBER, AND THAT IS THE REWRITE.
The reels used to be nine sprites: four frames of horizontal blur cycled while
spinning, then a hard cut to one of five rarity faces. It read as a colour
appearing in a box. A real reel is a CONTINUOUS STRIP that goes past, slows,
and stops on a symbol — and the second and a half where it is crawling past
faces one at a time, with the answer already decided, is the entire reason
anybody has ever pulled a lever. So `strip.png` is one tall image of ten cells
and the client scrolls a window over it (`game/machine.ts` `reelScroll`), which
gets three things the old sheet could not:

    THE TEASE      the band decelerates through six or seven faces before it
                   lands, so a legendary is visibly ALMOST on the line for a
                   beat before it either arrives or goes past
    THE NEAR MISS  free, and never authored: the band's order puts a legendary
                   next to a common, so the reel that stopped one cell short
                   really did stop one cell short
    THE WEIGHT     motion blur is the strip drawn twice at an offset scaled by
                   its own speed, so slowing down is something you SEE rather
                   than a frame index changing

The band's order is fixed and deliberately not sorted. Ascending would teach
the player that blue means purple is next, which turns the last half second
into arithmetic; commons appear four times because they are the likeliest roll,
so the strip looks like the odds it is paying.

THE LIGHT IS THE POINT AND IT IS ADDITIVE.
The cabinet body takes the darkness multiply like every other prop. The
marquee, the window backlight and the payout burst are drawn AFTER that pass,
additively, because they are light sources and not things being lit. The
marquee and the burst are GREYSCALE so the client can tint them: the crown
burns `--scene-neon` while the machine is idle and the winning RARITY's colour
while a canister is coming out, and one multiply gets both out of one sheet.

Usage:
    python tools/make_machine.py
    python tools/make_machine.py --seed 5
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

from make_textures import (
    BEAM,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    add,
    clamp01,
    ellipse,
    hash01,
    outline,
    pack,
    pick,
    resolve,
    rgb,
)

# --- palette ----------------------------------------------------------------
# Toned like scenery, because it stands in the same night the trees do. The
# only saturated things here are the reel faces and the lever ball, and both
# are small — the cabinet reads as a dark shape with light coming out of it,
# which is what a machine at night looks like.

SHELL: Ramp = [rgb(c) for c in ("#131519", "#1c2026", "#272c34", "#343a45", "#454c59", "#5a6270")]
SHELL_WORN: Ramp = [rgb(c) for c in ("#1a1610", "#251f16", "#33291d", "#453626", "#5c4832")]
TRIM: Ramp = [rgb(c) for c in ("#2a1d0c", "#463012", "#6b4a1c", "#8f6626", "#b78633")]
CHROME: Ramp = [rgb(c) for c in ("#1b1f25", "#2b3239", "#434b54", "#5f6872", "#818b96")]
GLASSDARK: Ramp = [rgb(c) for c in ("#080a0e", "#0e1218", "#151b23", "#1d242e")]
BULB: Ramp = [rgb(c) for c in ("#2a1a22", "#4a2438", "#7a3358", "#b04a80", "#e86aa8")]
RED: Ramp = [rgb(c) for c in ("#3a0d0c", "#5e1512", "#8a1f19", "#b52c22", "#d94a34")]
BATTERY: Ramp = [rgb(c) for c in ("#101a14", "#18261c", "#223326", "#2e4432", "#3d5a41")]
CABLE: Ramp = [rgb(c) for c in ("#0b0c0e", "#131519", "#1c1f24", "#262a31")]
OUTLINE: RGBA = rgb("#06070a")

#: The five rarity ramps, same five as `make_skills.py` and the same five the
#: HUD paints. A reel face that stopped on a colour the bag does not use would
#: be a sixth grade nobody could look up.
RARITY: dict[str, Ramp] = {
    "common": [rgb(c) for c in ("#3a3a42", "#565660", "#7c7c88", "#a8a8b4", "#e8e8f0")],
    "uncommon": [rgb(c) for c in ("#123020", "#1d4d32", "#2c7a4d", "#42a86a", "#5dce7a")],
    "rare": [rgb(c) for c in ("#131f3d", "#1d3160", "#2c4b96", "#3e6ac6", "#5b8def")],
    "epic": [rgb(c) for c in ("#2a1440", "#3f1d63", "#5f2d94", "#8a48c4", "#b46ee8")],
    "legendary": [rgb(c) for c in ("#3a2a0c", "#5e4413", "#96701f", "#c99a34", "#f2c14b")],
}

#: THE REEL BAND, top to bottom, and it wraps. See the module docstring: the
#: order is fixed, deliberately unsorted, and weighted toward common so the
#: strip looks like the odds it is paying. The two places a LEGENDARY sits are
#: both next to a COMMON, which is where every near miss in this machine comes
#: from — nothing about it is authored per pull.
BAND: tuple[str, ...] = (
    "common",
    "rare",
    "common",
    "legendary",
    "uncommon",
    "epic",
    "common",
    "uncommon",
    "rare",
    "common",
)

# --- geometry ---------------------------------------------------------------
# The cabinet is THREE TILES wide and four and a half tall, which is the size a
# body has to stand next to and look UP at. It grew when the shop became a room:
# in a lane it was the last thing on a walk and had a corridor's worth of
# attention, and standing alone on the arc of a clearing it has to hold the eye
# from the middle of that clearing instead. Everything below is measured inside
# this frame, bottom-anchored on the contact row.

CAB_W, CAB_H = 48, 72
BODY_L, BODY_R = 5, 42
CROWN_TOP, CROWN_BOTTOM = 1, 12
#: The three reel windows: left edge of the first, cell size, and the gap.
REEL_X, REEL_Y = 8, 20
REEL_W, REEL_H = 10, 16
REEL_GAP = 2
#: How many cells the band holds. The client scrolls a `REEL_H` window over
#: `CELLS * REEL_H` pixels and wraps, so the strip has no ends.
CELLS = len(BAND)
#: The tray the canister comes out of. `trayMouth` is the pixel the client
#: launches a can from, and it rides the manifest so the arc starts at the hole
#: rather than at a guess about where the hole is.
TRAY_L, TRAY_R = 13, 34
TRAY_TOP, TRAY_BOTTOM = 48, 58
#: Where the lever's pivot sits in the cabinet frame. The arm sheet is drawn
#: separately and pinned here, because it is the one part that moves.
#: The pivot is in the LEVER frame's own left margin, and `LEVER_ANCHOR` is
#: where that pivot lands in the cabinet frame — so the client blits the arm at
#: `anchor - pivot` and the two never have to agree about anything else.
LEVER_ANCHOR = (43, 28)
LEVER_PIVOT = (3, 18)
LEVER_W, LEVER_H = 16, 36

MARQUEE_W, MARQUEE_H = 54, 24
WINDOW_W, WINDOW_H = 40, 22
BURST = 64

#: How many bulbs ride the crown. Odd, so one of them is dead centre and the
#: chase reads as going round a sign rather than as two rows blinking.
BULBS = 11


def _rect(px, x0: int, y0: int, x1: int, y1: int, ramp: Ramp, shade: float,
          fall: float = 0.0) -> None:
    """Fill a box out of a ramp, optionally darkening toward the bottom."""
    span = max(1, y1 - y0)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            value = shade - fall * ((y - y0) / span)
            px[x, y] = pick(ramp, clamp01(value), x, y)


def _reel_slot(index: int) -> tuple[int, int]:
    """Top-left of reel window `index` in the cabinet frame."""
    return REEL_X + index * (REEL_W + REEL_GAP), REEL_Y


# --- the cabinet ------------------------------------------------------------


def make_cabinet(rng: random.Random, settled: bool) -> Image.Image:
    """The body. `settled` is the frame after a pull: the shell sits one pixel
    lower on its feet and the dents catch differently, which is the whole tell
    that the thing just took a hit from its own lever."""
    img = Image.new("RGBA", (CAB_W, CAB_H), TRANSPARENT)
    px = img.load()
    drop = 1 if settled else 0
    floor = CAB_H - 3

    # Plinth: wider than the body, so the machine stands on something rather
    # than being a box balanced on the soil.
    _rect(px, BODY_L - 3, floor - 12 + drop, BODY_R + 3, floor - 1, SHELL, 0.30, 0.18)
    _rect(px, BODY_L - 3, floor - 1, BODY_R + 3, floor, SHELL, 0.12)

    # Body.
    _rect(px, BODY_L, CROWN_BOTTOM + drop, BODY_R, floor - 12 + drop, SHELL, 0.62, 0.34)
    # Worn stripe down the left edge — the side that got dragged.
    _rect(px, BODY_L, CROWN_BOTTOM + drop, BODY_L + 3, floor - 12 + drop,
          SHELL_WORN, 0.55, 0.3)
    # Two chrome rails running the height of the front. They are what makes a
    # tall dark box read as a CABINET at a distance: a silhouette this size
    # with nothing vertical in it is a locker.
    for rail in (BODY_L + 1, BODY_R - 1):
        _rect(px, rail, CROWN_BOTTOM + 1 + drop, rail, floor - 13 + drop, CHROME, 0.72, 0.35)

    # Crown. Wider than the body and a step brighter: it is the part that is
    # lit, and the silhouette has to say so before any light is drawn on it.
    _rect(px, BODY_L - 3, CROWN_TOP + drop, BODY_R + 3, CROWN_BOTTOM + drop, TRIM, 0.62, 0.3)
    # ...with the top-right corner smashed off. One asymmetry is what stops a
    # symmetrical object reading as a decal.
    for y in range(CROWN_TOP + drop, CROWN_TOP + 5 + drop):
        for x in range(BODY_R - 2, BODY_R + 4):
            if x - BODY_R + 3 > (y - CROWN_TOP - drop):
                px[x, y] = TRANSPARENT

    # The bulb sockets along the crown. Dark here; the marquee sheet is what
    # lights them, so an unpowered machine still reads as a thing with bulbs.
    span = (BODY_R + 2) - (BODY_L - 2)
    for i in range(BULBS):
        bx = BODY_L - 2 + round(i * span / (BULBS - 1))
        by = CROWN_TOP + 3 + drop
        if 0 <= bx < CAB_W and 0 <= by < CAB_H and px[bx, by][3]:
            _rect(px, bx, by, bx, by + 1, BULB, 0.42)

    # The glass band the reels sit behind: one recessed panel, so the three
    # windows read as one instrument and not as three portholes. A chrome lip
    # top and bottom is the bezel that band is set into.
    _rect(px, BODY_L + 1, REEL_Y - 3 + drop, BODY_R - 1, REEL_Y + REEL_H + 2 + drop,
          GLASSDARK, 0.75, 0.35)
    for lip in (REEL_Y - 3 + drop, REEL_Y + REEL_H + 2 + drop):
        _rect(px, BODY_L + 1, lip, BODY_R - 1, lip, CHROME, 0.66)
    for index in range(3):
        rx, ry = _reel_slot(index)
        _rect(px, rx, ry + drop, rx + REEL_W - 1, ry + REEL_H - 1 + drop, GLASSDARK, 0.18)

    # THE PAY LINE: a brass tick in each of the two gaps BETWEEN the windows.
    # It is the one piece of a slot machine that explains the rules without a
    # word — three cells across one line — and it is why the client can flash
    # that row and have it mean something. In the gaps rather than at the ends
    # because the reels are blitted over their own windows every frame, and a
    # marker inside one would be painted out on the first tick of a spin.
    mid = REEL_Y + REEL_H // 2 + drop
    for gap in range(2):
        tick = REEL_X + REEL_W + gap * (REEL_W + REEL_GAP)
        _rect(px, tick, mid - 1, tick + REEL_GAP - 1, mid + 1, TRIM, 0.85)

    # The front panel under the glass: a brass strip, a maker's plate and two
    # dead buttons. They do nothing — there is one control on this machine and
    # it is the lever — but a fascia with no detail reads as an unfinished box.
    plate_y = REEL_Y + REEL_H + 6
    _rect(px, BODY_L + 2, plate_y + drop, BODY_R - 2, plate_y + 3 + drop, TRIM, 0.5, 0.2)
    for row in range(2):
        for slot in range(6):
            gx = BODY_L + 5 + slot * 5
            gy = plate_y + 1 + row + drop
            if px[gx, gy][3]:
                px[gx, gy] = pick(TRIM, 0.2, gx, gy)
    for bx in (BODY_L + 5, BODY_L + 12):
        _rect(px, bx, plate_y + 6 + drop, bx + 4, plate_y + 8 + drop, RED, 0.5)
        _rect(px, bx, plate_y + 6 + drop, bx + 4, plate_y + 6 + drop, RED, 0.85)

    # The tray: a recess with a lip. Drawn dark and hollow so the eye reads a
    # HOLE, which is what makes a canister appearing in it read as delivery.
    _rect(px, TRAY_L, TRAY_TOP + drop, TRAY_R, TRAY_BOTTOM + drop, GLASSDARK, 0.9, 0.5)
    _rect(px, TRAY_L - 2, TRAY_BOTTOM + drop, TRAY_R + 2, TRAY_BOTTOM + 2 + drop,
          CHROME, 0.6, 0.3)

    # THE STORY, and it costs twenty pixels: a car battery on the ground beside
    # the plinth with a cable running up into the base. Nobody built this here;
    # somebody found it and got it running.
    bat_top = floor - 8
    _rect(px, BODY_R + 1, bat_top, BODY_R + 5, floor - 1, BATTERY, 0.6, 0.25)
    _rect(px, BODY_R + 2, bat_top - 1, BODY_R + 2, bat_top - 1, TRIM, 0.7)
    _rect(px, BODY_R + 4, bat_top - 1, BODY_R + 4, bat_top - 1, RED, 0.7)
    for step, y in enumerate(range(bat_top - 8, bat_top)):
        cx = BODY_R + 1 - (7 - step) // 2
        if 0 <= cx < CAB_W:
            px[cx, y] = pick(CABLE, 0.6, cx, y)

    # Dents. Seeded, so the wreck is the same wreck every build.
    for _ in range(26):
        dx = rng.randint(BODY_L, BODY_R)
        dy = rng.randint(CROWN_BOTTOM + 2, floor - 13)
        if px[dx, dy][3] == 0:
            continue
        px[dx, dy] = pick(SHELL, 0.22 + hash01(dx, dy, 3) * 0.18, dx, dy)

    outline(img, OUTLINE)
    return img


# --- the reel band ----------------------------------------------------------


def _face(px, top: int, rarity: str) -> None:
    """One cell of the band: a filled lozenge in the tier's colour.

    It has to be readable as a COLOUR at ten pixels across and while it is
    moving, so it is a solid mass rather than a symbol — the symbol is on the
    canister, where there is room for one. A rim of glass either side keeps the
    cells from merging into a stripe when the band is running.
    """
    ramp = RARITY[rarity]
    for row in range(REEL_H):
        y = top + row
        for x in range(REEL_W):
            nx = (x + 0.5) / REEL_W - 0.5
            ny = (row + 0.5) / REEL_H - 0.5
            d = abs(nx) * 1.5 + abs(ny) * 1.25
            if d > 0.60:
                px[x, y] = pick(GLASSDARK, 0.2, x, y)
            elif d > 0.32:
                px[x, y] = pick(ramp, 0.9 - d * 0.4, x, y)
            else:
                px[x, y] = pick(ramp, 0.25, x, y)


def make_strip() -> Image.Image:
    """The whole band as one tall image. See `BAND` and the module docstring.

    A DIVIDER BETWEEN CELLS, and it is not decoration: a band of ten lozenges
    with nothing between them slides past as one texture, and the eye cannot
    count what it cannot separate. One dark row per cell is what turns a moving
    strip into a moving strip of THINGS, which is the whole reason slowing down
    means anything.
    """
    img = Image.new("RGBA", (REEL_W, REEL_H * CELLS), TRANSPARENT)
    px = img.load()
    for index, rarity in enumerate(BAND):
        top = index * REEL_H
        _face(px, top, rarity)
        for x in range(REEL_W):
            px[x, top] = pick(GLASSDARK, 0.05, x, top)
    return img


# --- the lever --------------------------------------------------------------


def make_lever(frame: int, frames: int) -> Image.Image:
    """The arm, from resting to fully pulled.

    IT ROTATES AROUND ITS PIVOT AND NOTHING ELSE. An earlier version walked the
    arm out with a per-step drift that looked fine at rest and posted the ball
    off the top of the frame at full travel, which is the failure mode of every
    hand-tuned pixel animation: it is drawn for the pose you were looking at.
    A real angle sweep between two authored stops cannot do that.

    The ball is the only pure red thing on the machine and it stays red at
    every angle — the eye tracks the knob, so the knob is what has to stay
    legible while it moves.
    """
    img = Image.new("RGBA", (LEVER_W, LEVER_H), TRANSPARENT)
    px = img.load()
    t = frame / max(1, frames - 1)
    # Up-and-out at rest, down-and-out when pulled. Not a full sweep to
    # horizontal: an arm that ends level reads as a handle that came off.
    angle = math.radians(-72.0 + t * 118.0)
    pivot_x, pivot_y = LEVER_PIVOT
    reach_x, reach_y = 9.0, 15.0

    steps = 22
    for step in range(steps + 1):
        f = step / steps
        x = pivot_x + math.cos(angle) * reach_x * f
        y = pivot_y + math.sin(angle) * reach_y * f
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < LEVER_W and 0 <= iy < LEVER_H):
            continue
        px[ix, iy] = pick(CHROME, 0.78 - f * 0.18, ix, iy)
        # A second column, so the shaft has thickness and does not disappear
        # into the cabinet behind it at the angles where it is nearly vertical.
        if ix + 1 < LEVER_W:
            px[ix + 1, iy] = pick(CHROME, 0.46 - f * 0.12, ix + 1, iy)

    bx = pivot_x + math.cos(angle) * reach_x
    by = pivot_y + math.sin(angle) * reach_y
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            if dx * dx + dy * dy > 10:
                continue
            ix, iy = int(round(bx + dx)), int(round(by + dy))
            if 0 <= ix < LEVER_W and 0 <= iy < LEVER_H:
                px[ix, iy] = pick(RED, 0.92 - (dx + dy) * 0.07, ix, iy)
    outline(img, OUTLINE)
    return img


# --- the light --------------------------------------------------------------


def make_marquee(frame: int, frames: int) -> Image.Image:
    """The crown's bulbs, chasing. Greyscale, additive, tinted by the client.

    A CHASE RATHER THAN A PULSE. Every other light in this game breathes,
    because everything else that glows out here is fire. Bulbs going round a
    sign in sequence is the one motion nothing organic makes, and it is what
    says ELECTRIC from across the clearing without a single word.
    """
    field = [[0.0] * MARQUEE_W for _ in range(MARQUEE_H)]
    phase = frame / frames
    for i in range(BULBS):
        bx = 4.0 + i * (MARQUEE_W - 8.0) / (BULBS - 1)
        # Each bulb peaks a fraction of a cycle after the one to its left.
        local = (phase - i / BULBS) % 1.0
        heat = max(0.0, 1.0 - abs(local - 0.5) * 3.2)
        ellipse(field, bx, 7.0, 2.6, 2.6, 0.55 + heat * 1.5)
        ellipse(field, bx, 7.0, 5.4, 4.6, 0.12 + heat * 0.3)
    # The wash the whole crown throws down over the glass.
    ellipse(field, MARQUEE_W / 2.0, 14.0, 25.0, 9.0, 0.28)
    img = Image.new("RGBA", (MARQUEE_W, MARQUEE_H), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def make_window(frame: int, frames: int) -> Image.Image:
    """The backlight behind the three reels. Greyscale, additive.

    Steady with a slow sag, because it is a lamp behind glass rather than a
    signal: the reels are what move, and a backlight that flickered would make
    them look like they were stuttering.
    """
    field = [[0.0] * WINDOW_W for _ in range(WINDOW_H)]
    sag = 0.88 + 0.12 * math.sin(frame / frames * math.tau)
    for index in range(3):
        cx = 6.0 + index * (REEL_W + REEL_GAP)
        ellipse(field, cx, WINDOW_H / 2.0, 5.4, 9.0, 0.85 * sag)
        ellipse(field, cx, WINDOW_H / 2.0, 9.0, 11.0, 0.2 * sag)
    img = Image.new("RGBA", (WINDOW_W, WINDOW_H), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def make_burst(frame: int, frames: int) -> Image.Image:
    """The payout flash. Greyscale, additive, tinted with the RARITY.

    One shot, and the whole reason the tier is worth watching for: a common
    pull throws a small dim ring and a legendary throws a wide one, because the
    CLIENT scales this sheet by the tier rather than the sheet carrying five
    versions of itself. Shape here, magnitude there.

    A ring plus a star, not a ball. A filled flash at this size is a white
    blob; a ring says something LEFT the machine, which is what happened.
    """
    field = [[0.0] * BURST for _ in range(BURST)]
    t = frame / max(1, frames - 1)
    cx = cy = BURST / 2.0
    grow = 4.0 + t * 26.0
    fade = (1.0 - t) ** 1.6
    ellipse(field, cx, cy, grow, grow * 0.82, 1.5 * fade, hollow=0.62)
    ellipse(field, cx, cy, 6.5 - t * 4.0, 6.5 - t * 4.0, 2.2 * (1.0 - t) ** 3)
    # Four spikes, on the diagonals so they do not sit on the ring's own axes.
    reach = 8.0 + t * 26.0
    for angle in (0.7854, 2.3562, 3.9270, 5.4978):
        for step in range(int(reach)):
            f = step / max(1.0, reach)
            add(
                field,
                int(cx + math.cos(angle) * step),
                int(cy + math.sin(angle) * step),
                1.3 * fade * (1.0 - f),
            )
    img = Image.new("RGBA", (BURST, BURST), TRANSPARENT)
    resolve(field, img, BEAM)
    return img


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "machine"
    out_dir.mkdir(parents=True, exist_ok=True)

    cabinets = [make_cabinet(random.Random(args.seed), settled) for settled in (False, True)]
    pack(cabinets, CAB_W, CAB_H).save(out_dir / "cabinet.png")

    strip = make_strip()
    strip.save(out_dir / "strip.png")

    lever_frames = 6
    levers = [make_lever(i, lever_frames) for i in range(lever_frames)]
    pack(levers, LEVER_W, LEVER_H).save(out_dir / "lever.png")

    marquee_frames = 10
    marquees = [make_marquee(i, marquee_frames) for i in range(marquee_frames)]
    pack(marquees, MARQUEE_W, MARQUEE_H).save(out_dir / "marquee.png")

    window_frames = 6
    windows = [make_window(i, window_frames) for i in range(window_frames)]
    pack(windows, WINDOW_W, WINDOW_H).save(out_dir / "window.png")

    burst_frames = 12
    bursts = [make_burst(i, burst_frames) for i in range(burst_frames)]
    pack(bursts, BURST, BURST).save(out_dir / "burst.png")

    manifest = {
        "seed": args.seed,
        "cabinet": {
            "file": "cabinet.png",
            "frameWidth": CAB_W,
            "frameHeight": CAB_H,
            "frames": len(cabinets),
            # The contact is the bottom row: this is a bottom-anchored prop
            # like a table or a torch, and the client sorts it by that row.
            "reels": [list(_reel_slot(i)) for i in range(3)],
            "reelWidth": REEL_W,
            "reelHeight": REEL_H,
            "lever": list(LEVER_ANCHOR),
            # Where a canister is launched from, in frame pixels. The client
            # arcs it out of this hole rather than out of the cabinet's centre.
            "trayMouth": [(TRAY_L + TRAY_R) // 2, TRAY_BOTTOM - 1],
            "crown": [CAB_W // 2, (CROWN_TOP + CROWN_BOTTOM) // 2],
            # The row the three cells have to agree on, in frame pixels. The
            # client flashes it when they do — see the brass ticks above.
            "payLine": REEL_Y + REEL_H // 2,
        },
        # THE BAND. One image, `cells` tall, scrolled and wrapped by the client
        # — see `game/machine.ts` `reelScroll`. `frameHeight` is the WINDOW,
        # not the sheet: what the cabinet shows is one cell at a time.
        "reel": {
            "file": "strip.png",
            "frameWidth": REEL_W,
            "frameHeight": REEL_H,
            "cells": CELLS,
            "band": list(BAND),
        },
        "lever": {
            "file": "lever.png",
            "frameWidth": LEVER_W,
            "frameHeight": LEVER_H,
            "frames": lever_frames,
            # Where the pivot is INSIDE this sheet. The client draws the arm at
            # `cabinet.lever - lever.pivot`, so moving either end is one edit.
            "pivot": list(LEVER_PIVOT),
        },
        "effects": {
            "marquee": {
                "file": "marquee.png",
                "frameWidth": MARQUEE_W,
                "frameHeight": MARQUEE_H,
                "frames": marquee_frames,
                "fps": 14,
                "anchorY": MARQUEE_H // 2,
                "loop": True,
                "tinted": True,
            },
            "window": {
                "file": "window.png",
                "frameWidth": WINDOW_W,
                "frameHeight": WINDOW_H,
                "frames": window_frames,
                "fps": 8,
                "anchorY": WINDOW_H // 2,
                "loop": True,
                "tinted": True,
            },
            "burst": {
                "file": "burst.png",
                "frameWidth": BURST,
                "frameHeight": BURST,
                "frames": burst_frames,
                "fps": 18,
                "anchorY": BURST // 2,
                "loop": False,
                "tinted": True,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the upgrade machine.")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    out = build(args)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
