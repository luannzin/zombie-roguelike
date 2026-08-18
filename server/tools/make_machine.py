#!/usr/bin/env python3
"""Asset pipeline: THE UPGRADE MACHINE — a slot cabinet somebody dragged into
the woods and wired to a car battery.

Output (assets/processed/machine/):
    cabinet.png    2 frames, 36x50   PROP   — idle, and settled after a pull
    reel.png       9 frames, 8x12    PART   — 0..3 spin blur, 4..8 rarity faces
    lever.png      5 frames, 10x22   PART   — the arm, up to fully pulled
    marquee.png    8 frames, 40x18   VFX    — loop, the crown lights
    window.png     6 frames, 30x14   VFX    — loop, the backlight behind the reels
    burst.png     10 frames, 48x48   VFX    — one-shot, the payout flash
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
subtle — a player has to read it from the far end of the glade, before the
prompt, before the tooltip, and think *that thing is for me*.

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
    quantize_alpha,
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
ORDER = ("common", "uncommon", "rare", "epic", "legendary")

# --- geometry ---------------------------------------------------------------
# The cabinet is TWO TILES wide and a little over three tall, which is the size
# a body has to stand next to and look up at. Everything below is measured
# inside this frame, bottom-anchored on the contact row.

CAB_W, CAB_H = 36, 50
BODY_L, BODY_R = 4, 29
CROWN_TOP, CROWN_BOTTOM = 1, 8
#: The three reel windows: left edge of the first, cell size, and the gap.
REEL_X, REEL_Y = 6, 14
REEL_W, REEL_H = 8, 12
REEL_GAP = 1
#: The tray the canister comes out of. `TRAY_MOUTH` is the pixel the client
#: launches a can from, and it rides the manifest so the arc starts at the hole
#: rather than at a guess about where the hole is.
TRAY_L, TRAY_R = 10, 24
TRAY_TOP, TRAY_BOTTOM = 33, 40
#: Where the lever's pivot sits in the cabinet frame. The arm sheet is drawn
#: separately and pinned here, because it is the one part that moves.
#: The pivot is in the LEVER frame's own left margin, and `LEVER_ANCHOR` is
#: where that pivot lands in the cabinet frame — so the client blits the arm at
#: `anchor - pivot` and the two never have to agree about anything else.
LEVER_ANCHOR = (29, 19)
LEVER_PIVOT = (2, 13)
LEVER_W, LEVER_H = 12, 26

MARQUEE_W, MARQUEE_H = 40, 18
WINDOW_W, WINDOW_H = 30, 14
BURST = 48


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

    # Plinth: wider than the body, so the machine stands on something rather
    # than being a box balanced on the soil.
    _rect(px, BODY_L - 2, 41 + drop, BODY_R + 2, 47, SHELL, 0.30, 0.18)
    _rect(px, BODY_L - 2, 47, BODY_R + 2, 48, SHELL, 0.12)

    # Body.
    _rect(px, BODY_L, CROWN_BOTTOM + drop, BODY_R, 41 + drop, SHELL, 0.62, 0.34)
    # Worn stripe down the left edge — the side that got dragged.
    _rect(px, BODY_L, CROWN_BOTTOM + drop, BODY_L + 2, 41 + drop, SHELL_WORN, 0.55, 0.3)

    # Crown. Wider than the body and a step brighter: it is the part that is
    # lit, and the silhouette has to say so before any light is drawn on it.
    _rect(px, BODY_L - 2, CROWN_TOP + drop, BODY_R + 2, CROWN_BOTTOM + drop, TRIM, 0.62, 0.3)
    # ...with the top-right corner smashed off. One asymmetry is what stops a
    # symmetrical object reading as a decal.
    for y in range(CROWN_TOP + drop, CROWN_TOP + 3 + drop):
        for x in range(BODY_R - 1, BODY_R + 3):
            if x - BODY_R + 2 > (y - CROWN_TOP - drop):
                px[x, y] = TRANSPARENT

    # The bulb sockets along the crown. Dark here; the marquee sheet is what
    # lights them, so an unpowered machine still reads as a thing with bulbs.
    for i in range(9):
        bx = BODY_L - 1 + i * 3
        by = CROWN_TOP + 2 + drop
        if 0 <= bx < CAB_W and 0 <= by < CAB_H:
            px[bx, by] = pick(BULB, 0.42, bx, by)

    # The glass band the reels sit behind: one recessed panel, so the three
    # windows read as one instrument and not as three portholes.
    _rect(px, BODY_L + 1, REEL_Y - 2 + drop, BODY_R - 1, REEL_Y + REEL_H + 1 + drop,
          GLASSDARK, 0.75, 0.35)
    for index in range(3):
        rx, ry = _reel_slot(index)
        _rect(px, rx, ry + drop, rx + REEL_W - 1, ry + REEL_H - 1 + drop,
              GLASSDARK, 0.18)

    # The front panel under the glass: a brass strip and two dead buttons. They
    # do nothing — there is one control on this machine and it is the lever —
    # but a fascia with no detail at all reads as an unfinished box.
    _rect(px, BODY_L + 1, 28 + drop, BODY_R - 1, 30 + drop, TRIM, 0.5, 0.2)
    for bx in (BODY_L + 4, BODY_L + 9):
        _rect(px, bx, 31 + drop, bx + 3, 32 + drop, RED, 0.5)

    # The tray: a recess with a lip. Drawn dark and hollow so the eye reads a
    # HOLE, which is what makes a canister appearing in it read as delivery.
    _rect(px, TRAY_L, TRAY_TOP + drop, TRAY_R, TRAY_BOTTOM + drop, GLASSDARK, 0.9, 0.5)
    _rect(px, TRAY_L - 1, TRAY_BOTTOM + drop, TRAY_R + 1, TRAY_BOTTOM + 1 + drop,
          SHELL, 0.55)

    # THE STORY, and it costs eleven pixels: a car battery on the ground beside
    # the plinth with a cable running up into the base. Nobody built this here;
    # somebody found it and got it running.
    _rect(px, BODY_R + 1, 43, BODY_R + 5, 47, BATTERY, 0.6, 0.25)
    px[BODY_R + 2, 42] = pick(TRIM, 0.7, BODY_R + 2, 42)
    px[BODY_R + 4, 42] = pick(RED, 0.7, BODY_R + 4, 42)
    for step, y in enumerate(range(38, 43)):
        cx = BODY_R + 1 - (4 - step) // 2
        if 0 <= cx < CAB_W:
            px[cx, y] = pick(CABLE, 0.6, cx, y)

    # Dents. Seeded, so the wreck is the same wreck every build.
    for _ in range(14):
        dx = rng.randint(BODY_L, BODY_R)
        dy = rng.randint(CROWN_BOTTOM + 2, 40)
        if px[dx, dy][3] == 0:
            continue
        px[dx, dy] = pick(SHELL, 0.22 + hash01(dx, dy, 3) * 0.18, dx, dy)

    outline(img, OUTLINE)
    return img


# --- the reels --------------------------------------------------------------


def make_reel(index: int) -> Image.Image:
    """One reel cell. 0..3 are spin blur; 4..8 are the five rarity faces.

    THE BLUR IS HORIZONTAL BANDS, not a smear, because a pixel reel that spins
    is a strip of symbols going past too fast to resolve — which at this size
    is exactly a stack of bright rows sliding. Four frames cycled fast is
    enough to read as motion and cheap enough to run three of them out of phase
    so the reels are never in lockstep.
    """
    img = Image.new("RGBA", (REEL_W, REEL_H), TRANSPARENT)
    px = img.load()
    if index < 4:
        for y in range(REEL_H):
            band = ((y + index * 3) % 4) / 3.0
            ramp = BEAM if band > 0.6 else GLASSDARK
            for x in range(REEL_W):
                shade = 0.25 + band * 0.55 - abs(x - REEL_W / 2) / REEL_W * 0.3
                px[x, y] = pick(ramp, clamp01(shade), x, y)
        return img

    ramp = RARITY[ORDER[index - 4]]
    # A face is a filled lozenge in the tier's colour with a dark core: it has
    # to be readable as a COLOUR at eight pixels across, so it is a solid mass
    # rather than a symbol. The symbol is on the canister, where there is room.
    for y in range(REEL_H):
        for x in range(REEL_W):
            nx = (x + 0.5) / REEL_W - 0.5
            ny = (y + 0.5) / REEL_H - 0.5
            d = abs(nx) * 1.5 + abs(ny) * 1.15
            if d > 0.62:
                px[x, y] = pick(GLASSDARK, 0.2, x, y)
            elif d > 0.34:
                px[x, y] = pick(ramp, 0.9 - d * 0.4, x, y)
            else:
                px[x, y] = pick(ramp, 0.25, x, y)
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
    reach_x, reach_y = 6.0, 11.0

    steps = 16
    for step in range(steps + 1):
        f = step / steps
        x = pivot_x + math.cos(angle) * reach_x * f
        y = pivot_y + math.sin(angle) * reach_y * f
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < LEVER_W and 0 <= iy < LEVER_H):
            continue
        px[ix, iy] = pick(SHELL, 0.74 - f * 0.18, ix, iy)
        # A second column, so the shaft has thickness and does not disappear
        # into the cabinet behind it at the angles where it is nearly vertical.
        if ix + 1 < LEVER_W:
            px[ix + 1, iy] = pick(SHELL, 0.44 - f * 0.12, ix + 1, iy)

    bx = pivot_x + math.cos(angle) * reach_x
    by = pivot_y + math.sin(angle) * reach_y
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy > 5:
                continue
            ix, iy = int(round(bx + dx)), int(round(by + dy))
            if 0 <= ix < LEVER_W and 0 <= iy < LEVER_H:
                px[ix, iy] = pick(RED, 0.9 - (dx + dy) * 0.09, ix, iy)
    outline(img, OUTLINE)
    return img


# --- the light --------------------------------------------------------------


def make_marquee(frame: int, frames: int) -> Image.Image:
    """The crown's bulbs, chasing. Greyscale, additive, tinted by the client.

    A CHASE RATHER THAN A PULSE. Every other light in this game breathes,
    because everything else that glows out here is fire. Bulbs going round a
    sign in sequence is the one motion nothing organic makes, and it is what
    says ELECTRIC from the far end of the glade without a single word.
    """
    field = [[0.0] * MARQUEE_W for _ in range(MARQUEE_H)]
    phase = frame / frames
    for i in range(9):
        bx = 3.0 + i * 4.3
        # Each bulb peaks a fraction of a cycle after the one to its left.
        local = (phase - i / 9.0) % 1.0
        heat = max(0.0, 1.0 - abs(local - 0.5) * 3.2)
        ellipse(field, bx, 5.0, 2.4, 2.4, 0.55 + heat * 1.5)
        ellipse(field, bx, 5.0, 5.0, 4.2, 0.12 + heat * 0.3)
    # The wash the whole crown throws down over the glass.
    ellipse(field, MARQUEE_W / 2.0, 10.0, 19.0, 7.0, 0.28)
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
        cx = 4.5 + index * 10.5
        ellipse(field, cx, WINDOW_H / 2.0, 4.4, 6.0, 0.85 * sag)
        ellipse(field, cx, WINDOW_H / 2.0, 7.5, 8.0, 0.2 * sag)
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
    grow = 3.0 + t * 19.0
    fade = (1.0 - t) ** 1.6
    ellipse(field, cx, cy, grow, grow * 0.82, 1.5 * fade, hollow=0.62)
    ellipse(field, cx, cy, 5.0 - t * 3.0, 5.0 - t * 3.0, 2.2 * (1.0 - t) ** 3)
    # Four spikes, on the diagonals so they do not sit on the ring's own axes.
    reach = 6.0 + t * 20.0
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
    rng = random.Random(args.seed)

    cabinets = [make_cabinet(random.Random(args.seed), settled) for settled in (False, True)]
    pack(cabinets, CAB_W, CAB_H).save(out_dir / "cabinet.png")

    reels = [make_reel(i) for i in range(9)]
    pack(reels, REEL_W, REEL_H).save(out_dir / "reel.png")

    lever_frames = 5
    levers = [make_lever(i, lever_frames) for i in range(lever_frames)]
    pack(levers, LEVER_W, LEVER_H).save(out_dir / "lever.png")

    marquee_frames = 8
    marquees = [make_marquee(i, marquee_frames) for i in range(marquee_frames)]
    pack(marquees, MARQUEE_W, MARQUEE_H).save(out_dir / "marquee.png")

    window_frames = 6
    windows = [make_window(i, window_frames) for i in range(window_frames)]
    pack(windows, WINDOW_W, WINDOW_H).save(out_dir / "window.png")

    burst_frames = 10
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
        },
        "reel": {
            "file": "reel.png",
            "frameWidth": REEL_W,
            "frameHeight": REEL_H,
            "frames": len(reels),
            "spinFrames": 4,
            "rarities": list(ORDER),
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
