#!/usr/bin/env python3
"""Asset pipeline: what a gun going off actually looks like.

Sibling of make_vfx.py and it exists for one reason: the shot was the only
important event in the game still drawn entirely out of canvas primitives —
a filled circle at the barrel, two straight lines down the ray, and a spray
of squares at the far end. Everything AROUND it (the summon column, the
kindle roar, the death puff) had been pixel art for a while, so the loudest
thing in the game was also the only thing that did not look like it was made
of the same stuff as the forest.

The vocabulary here is taken from `assets/inspiration/pixel-art-new-style/
weapon-vfx.png`, and what that sheet actually teaches is four things:

  1. A MUZZLE FLASH IS NOT A CIRCLE. It is a hot core with PETALS coming off
     it and a lance thrown forward down the barrel — an asymmetric star,
     brightest at the middle and reaching furthest along the shot.
  2. THE RING IS WHAT SELLS IT. Every blast on that sheet throws a torus out
     of the muzzle a frame or two after the flash, and the ring is what makes
     the flash read as pressure leaving a barrel rather than as a light being
     switched on.
  3. WHITE IS THE MIDDLE, NOT THE WHOLE. The core is white, the body is gold,
     the shoulders are orange and the outer edge is a deep red that is nearly
     the colour of the night. A flash drawn in one bright colour is a lamp.
  4. IT ENDS IN SMOKE. The last third of every animation on that sheet is
     dark clumps drifting off the muzzle. A flash that simply faded would be
     an effect stopping; smoke is an effect finishing.

Output (assets/processed/weapon-vfx/):
    muzzle.png     7 frames, 30x20 — the bloom at the barrel of any gun
    blast.png     10 frames, 56x36 — the shotgun's cone, ring and smoke
    impact.png     7 frames, 18x18 — a round arriving somewhere
    manifest.json

EVERY SHEET POINTS RIGHT, like the held-gun atlas, and the client rotates it
onto the aim. That is also why these carry an `anchorX` as well as an
`anchorY`: a muzzle flash is anchored at the BARREL TIP, on its left edge,
not at its middle — the effect grows forward out of the gun, and a
centre-anchored frame would put half the fire behind the player's hands.

UNLIKE THE EFFECTS IN make_vfx.py, THESE ARE NOT GREYSCALE. Those sheets are
tinted at draw time because they belong to a PLAYER — an arrival column is
the colour of whoever is arriving. Fire is not anybody's colour. A muzzle
flash tinted teal because a teal player pulled the trigger would be the one
effect in the game that lied about what it was, so the ramp is baked and the
client draws these additively with no tint at all.

Usage:
    python tools/make_weapon_vfx.py
    python tools/make_weapon_vfx.py --tile 16
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    Ramp,
    TRANSPARENT,
    add,
    clamp01,
    ease_out,
    ellipse,
    hash01,
    pack,
    resolve,
    rgb,
)

#: The fire ramp. Deep red at the edge through orange and gold to a white
#: core — the "Original Palette" strip on the reference sheet, quantised to
#: the seven steps this game's `pick` dithers between. The bottom step is
#: nearly the colour of the night on purpose: it is what lets the outside of
#: a flash sit ON the dark forest instead of cutting a hole in it.
FIRE: Ramp = [
    rgb(c)
    for c in ("#2a0a04", "#6d1c06", "#b8410c", "#e8791a", "#ffc247", "#fff3c8", "#ffffff")
]

#: What is left in the air afterwards. Warm grey rather than neutral, because
#: the smoke off a shot is lit by the shot for the first few frames of it.
SMOKE: Ramp = [rgb(c) for c in ("#16130f", "#241f19", "#332c24", "#443b31", "#584d40")]

# --- muzzle -------------------------------------------------------------------
# Seven frames at 45 fps: about 0.15 s, which is a little longer than the old
# procedural flash and considerably shorter than it felt, because the old one
# was a hard circle that vanished and this one has somewhere to go.
MUZZLE_FRAMES = 7
MUZZLE_FPS = 45
MUZZLE_W = 30
MUZZLE_H = 20
#: The barrel tip, in frame pixels. Two in from the left so the flash has a
#: row of pixels to bleed BACKWARDS over the muzzle brake, which is what
#: stops it looking pasted onto the end of the gun.
MUZZLE_ANCHOR_X = 3
MUZZLE_ANCHOR_Y = MUZZLE_H // 2
#: When the bloom peaks and when the smoke takes over, in normalised time.
MUZZLE_PEAK = 0.22
MUZZLE_SMOKE = 0.45

# --- blast --------------------------------------------------------------------
# The shotgun, and it is a different SHAPE rather than a bigger muzzle flash:
# a cone that reaches, holds and then breaks up. Ten frames at 34 fps is just
# under 0.3 s, which is most of the weapon's 0.35 s cooldown — the smoke is
# still clearing when the next shell is legal, and that is the whole feel of
# a pump gun.
BLAST_FRAMES = 10
BLAST_FPS = 34
BLAST_W = 56
BLAST_H = 36
BLAST_ANCHOR_X = 4
BLAST_ANCHOR_Y = BLAST_H // 2
BLAST_PEAK = 0.20
BLAST_BREAK = 0.38

# --- impact -------------------------------------------------------------------
# A round arriving. Centre-anchored, since an impact has no direction the way
# a muzzle does — the debris does, and the debris is particles.
IMPACT_FRAMES = 7
IMPACT_FPS = 50
IMPACT_W = 18
IMPACT_H = 18


def _petals(
    field: list[list[float]],
    cx: float,
    cy: float,
    reach: float,
    count: int,
    strength: float,
    seed: int,
    *,
    forward: float = 1.0,
    spread: float = math.pi,
) -> None:
    """Spikes radiating out of a point — the thing a circle is not.

    Each petal is a short line of falling intensity, and the two decisions
    that matter are both about ASYMMETRY. `forward` stretches the petals
    pointing down the barrel and squashes the ones pointing back at the
    shooter, because gas leaves a muzzle in one direction; `spread` narrows
    the fan for a cone and opens it to a full circle for an impact. A
    symmetric star reads as a sparkle, which is the wrong noun.
    """
    for i in range(count):
        # Deterministic, so a rebuild is byte-identical and a diff is a
        # decision rather than a reroll.
        angle = (hash01(i, seed, 11) - 0.5) * 2.0 * spread
        lean = math.cos(angle)
        length = reach * (0.45 + hash01(i, seed, 29) * 0.55)
        length *= 1.0 + max(0.0, lean) * (forward - 1.0)
        steps = max(2, int(length * 1.6))
        for step in range(steps + 1):
            t = step / steps
            px = cx + math.cos(angle) * length * t
            py = cy + math.sin(angle) * length * t
            # Bright at the root, gone at the tip. A petal of even weight is
            # a spoke on a wheel.
            add(field, int(round(px)), int(round(py)), strength * (1.0 - t) ** 1.6)


def _cone(
    field: list[list[float]],
    x0: float,
    cy: float,
    length: float,
    half_at_end: float,
    strength: float,
    seed: int,
) -> None:
    """A wedge of fire opening forward from `x0` — the shotgun's whole read.

    Filled rather than outlined, hot along the axis and falling off toward
    the lips, and the front face is RAGGED: a cone with a clean leading edge
    reads as a torch beam, and what this is meant to read as is a column of
    gas and lead that has already started to come apart.
    """
    if length < 1.0:
        return
    for step in range(int(length) + 1):
        t = step / max(length, 1.0)
        x = x0 + step
        half = 0.6 + half_at_end * t**0.85
        # The tip frays: the last quarter loses pixels to the hash rather
        # than to a gradient, so the edge is chewed instead of soft.
        fray = 1.0 if t < 0.72 else max(0.0, 1.0 - (t - 0.72) / 0.28)
        for y in range(int(cy - half) - 1, int(cy + half) + 2):
            offset = abs(y - cy) / max(half, 0.5)
            if offset > 1.0:
                continue
            if hash01(x, y, seed) > fray:
                continue
            # Hot on the axis, and hotter at the throat than at the mouth.
            core = (1.0 - offset) ** 1.3
            throat = 1.0 - t * 0.55
            add(field, x, y, strength * core * throat)


def _clumps(
    field: list[list[float]],
    cx: float,
    cy: float,
    drift: float,
    spread: float,
    count: int,
    strength: float,
    seed: int,
) -> None:
    """Smoke: overlapping blobs that walk forward and swell as they thin.

    Blobs and not a cloud texture, because the reference sheet's smoke is
    visibly made of lumps and because a soft cloud at 16 px is a smudge.
    """
    for i in range(count):
        angle = (hash01(i, seed, 5) - 0.5) * spread
        distance = drift * (0.35 + hash01(i, seed, 13) * 0.85)
        bx = cx + math.cos(angle) * distance
        by = cy + math.sin(angle) * distance * 0.8
        radius = 1.4 + hash01(i, seed, 21) * 2.2 + drift * 0.18
        ellipse(field, bx, by, radius, radius * 0.85, strength * (0.6 + hash01(i, seed, 33) * 0.6))


def make_muzzle_frame(index: int) -> Image.Image:
    """One frame of a gun going off: core, petals, lance, ring, smoke."""
    img = Image.new("RGBA", (MUZZLE_W, MUZZLE_H), TRANSPARENT)
    t = index / (MUZZLE_FRAMES - 1)
    cx = float(MUZZLE_ANCHOR_X)
    cy = float(MUZZLE_ANCHOR_Y)
    fire = [[0.0] * MUZZLE_W for _ in range(MUZZLE_H)]
    smoke = [[0.0] * MUZZLE_W for _ in range(MUZZLE_H)]

    # A rise so fast it is nearly a step, then a long fall. Ignition takes one
    # frame in the real world and the reference sheet honours that: frame 0 is
    # already most of the way up.
    if t <= MUZZLE_PEAK:
        heat = 0.55 + (t / MUZZLE_PEAK) * 0.45
    else:
        heat = max(0.0, 1.0 - (t - MUZZLE_PEAK) / (1.0 - MUZZLE_PEAK)) ** 1.35

    if heat > 0.02:
        grow = 0.55 + ease_out(min(1.0, t / MUZZLE_PEAK)) * 0.45
        # THE CORE. Wider than tall and pushed a pixel forward, so it sits on
        # the barrel rather than around it.
        ellipse(fire, cx + 1.5 * grow, cy, 3.4 * grow, 2.6 * grow, 2.2 * heat)
        # THE LANCE: gas thrown straight down the bore, and the one part of
        # the flash that says which way the round went.
        _cone(fire, cx, cy, 6.0 + 9.0 * grow * heat, 2.3 * grow, 1.5 * heat, seed=index * 7 + 3)
        # THE PETALS.
        _petals(
            fire,
            cx + 1.0,
            cy,
            5.0 + 4.0 * grow,
            9,
            1.35 * heat,
            seed=index * 13 + 1,
            forward=1.9,
        )

    # THE RING, one beat behind the flash and travelling out through it.
    ring = (t - 0.08) / 0.46
    if 0.0 < ring < 1.0:
        radius = 2.0 + ease_out(ring) * 9.0
        ellipse(
            fire,
            cx + radius * 0.35,
            cy,
            radius,
            radius * 0.72,
            1.5 * (1.0 - ring),
            # Thick enough to survive the five-step alpha quantiser; a thinner
            # rim comes out as a dotted ellipse instead of a wave.
            hollow=0.45,
        )

    # THE SMOKE, taking over as the fire goes out.
    if t >= MUZZLE_SMOKE:
        age = (t - MUZZLE_SMOKE) / (1.0 - MUZZLE_SMOKE)
        _clumps(
            smoke,
            cx + 3.0 + age * 5.0,
            cy,
            2.0 + age * 5.0,
            1.5,
            6,
            0.85 * (1.0 - age * 0.55),
            seed=index * 17 + 5,
        )

    # Smoke first so the fire burns through it, which is the order the two
    # things actually happen in.
    resolve(smoke, img, SMOKE, floor=0.16, tone=0.9, gain=0.62)
    resolve(fire, img, FIRE, floor=0.10, tone=0.86, gain=1.15)
    return img


def make_blast_frame(index: int) -> Image.Image:
    """One frame of a shell: a cone that reaches, holds, breaks and drifts."""
    img = Image.new("RGBA", (BLAST_W, BLAST_H), TRANSPARENT)
    t = index / (BLAST_FRAMES - 1)
    cx = float(BLAST_ANCHOR_X)
    cy = float(BLAST_ANCHOR_Y)
    fire = [[0.0] * BLAST_W for _ in range(BLAST_H)]
    smoke = [[0.0] * BLAST_W for _ in range(BLAST_H)]

    if t <= BLAST_PEAK:
        reach = ease_out(t / BLAST_PEAK)
        heat = 0.7 + reach * 0.3
    else:
        decay = (t - BLAST_PEAK) / (1.0 - BLAST_PEAK)
        reach = 1.0
        heat = max(0.0, 1.0 - decay) ** 1.5

    if heat > 0.02:
        length = 10.0 + reach * (BLAST_W - BLAST_ANCHOR_X - 12.0)
        # Past the break the cone stops being a wedge and starts being lumps,
        # so the fire is pulled back toward the muzzle while the smoke ahead
        # of it takes the shape over.
        if t > BLAST_BREAK:
            broken = (t - BLAST_BREAK) / (1.0 - BLAST_BREAK)
            length *= 1.0 - broken * 0.55
        _cone(fire, cx, cy, length, 7.5 * reach, 1.7 * heat, seed=index * 11 + 2)
        ellipse(fire, cx + 2.0, cy, 4.2, 3.4, 2.4 * heat)
        _petals(
            fire, cx + 1.0, cy, 7.0, 11, 1.3 * heat, seed=index * 19 + 7, forward=1.6
        )

    # The ring off a shell is bigger and slower than a pistol's, and it is the
    # part of this animation people will actually remember.
    ring = (t - 0.06) / 0.5
    if 0.0 < ring < 1.0:
        radius = 3.0 + ease_out(ring) * 13.0
        ellipse(
            fire, cx + radius * 0.3, cy, radius, radius * 0.78, 1.7 * (1.0 - ring), hollow=0.5
        )

    if t >= BLAST_PEAK:
        age = clamp01((t - BLAST_PEAK) / (1.0 - BLAST_PEAK))
        _clumps(
            smoke,
            cx + 6.0 + age * 16.0,
            cy,
            4.0 + age * 12.0,
            1.35,
            14,
            0.95 * (1.0 - age * 0.5),
            seed=index * 23 + 9,
        )

    resolve(smoke, img, SMOKE, floor=0.16, tone=0.92, gain=0.7)
    resolve(fire, img, FIRE, floor=0.10, tone=0.86, gain=1.15)
    return img


def make_impact_frame(index: int) -> Image.Image:
    """One frame of a round arriving: a hot point, a star, a ring, nothing.

    Centre-anchored and symmetric — the opposite decision to the muzzle, and
    for the opposite reason. A muzzle flash has a direction because the gas
    is leaving down a tube; an impact throws in every direction at once, and
    what carries the direction of the shot is the debris the effects layer
    kicks BACK along the ray.
    """
    img = Image.new("RGBA", (IMPACT_W, IMPACT_H), TRANSPARENT)
    t = index / (IMPACT_FRAMES - 1)
    cx = (IMPACT_W - 1) / 2.0
    cy = (IMPACT_H - 1) / 2.0
    fire = [[0.0] * IMPACT_W for _ in range(IMPACT_H)]

    heat = max(0.0, 1.0 - t) ** 1.4
    if heat > 0.02:
        ellipse(fire, cx, cy, 1.8 + t * 1.6, 1.8 + t * 1.6, 2.3 * heat)
        _petals(fire, cx, cy, 3.0 + t * 4.5, 8, 1.25 * heat, seed=index * 31 + 4)

    ring = t / 0.8
    if 0.0 < ring < 1.0:
        radius = 1.5 + ease_out(ring) * 6.0
        ellipse(fire, cx, cy, radius, radius, 1.3 * (1.0 - ring), hollow=0.5)

    resolve(fire, img, FIRE, floor=0.10, tone=0.86, gain=1.1)
    return img


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "weapon-vfx"
    out_dir.mkdir(parents=True, exist_ok=True)

    sheets = {
        "muzzle": (
            [make_muzzle_frame(i) for i in range(MUZZLE_FRAMES)],
            MUZZLE_W,
            MUZZLE_H,
            MUZZLE_FPS,
            MUZZLE_ANCHOR_X,
            MUZZLE_ANCHOR_Y,
        ),
        "blast": (
            [make_blast_frame(i) for i in range(BLAST_FRAMES)],
            BLAST_W,
            BLAST_H,
            BLAST_FPS,
            BLAST_ANCHOR_X,
            BLAST_ANCHOR_Y,
        ),
        "impact": (
            [make_impact_frame(i) for i in range(IMPACT_FRAMES)],
            IMPACT_W,
            IMPACT_H,
            IMPACT_FPS,
            (IMPACT_W - 1) // 2,
            (IMPACT_H - 1) // 2,
        ),
    }

    effects: dict[str, dict] = {}
    for name, (frames, width, height, fps, ax, ay) in sheets.items():
        pack(frames, width, height).save(out_dir / f"{name}.png")
        effects[name] = {
            "file": f"{name}.png",
            "frameWidth": width,
            "frameHeight": height,
            "frames": len(frames),
            "fps": fps,
            "anchorX": ax,
            "anchorY": ay,
        }
        print(f"  {name}: {len(frames)} frames @ {width}x{height}")

    manifest = {"tile": args.tile, "effects": effects}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tile",
        type=int,
        default=DEFAULT_TILE,
        help="must match TILE_SIZE in server/app/config.py",
    )
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
