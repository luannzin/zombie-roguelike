#!/usr/bin/env python3
"""Asset pipeline: procedural VFX sprite sheets.

Third generator in the family, after make_textures.py (terrain) and
make_hud_icons.py. Same rules: no raw stage, final-resolution pixels written
straight into assets/processed/, fully deterministic, shared drawing helpers
imported from make_textures rather than copied.

Output (assets/processed/vfx/):
    summon.png    14 frames, 32x96 — a player materialising at the campfire
    kindle.png    16 frames, 48x96 — the bonfire roaring when the match starts
    manifest.json

EFFECT SHEETS ARE GREYSCALE. An effect that belongs to somebody — a summon, a
revive, a marker — is tinted at draw time with that player's colour (see
client/src/render/vfx.ts). An effect that belongs to the fire — the kindle
roar — is tinted with `fire.core` the same way. Baking a hue in here would
mean one sheet per colour, and the arriving player's column would not match
their row in the roster.

WHY A SPRITE AND NOT A GRADIENT
A beam of light is the one effect a canvas gradient does worst. The gradient
version of this was smooth, and smooth is the opposite of everything else on
screen: the ground is dithered, the fire is six flat colours, the characters
are 16px. Rendering it here means the column gets the same treatment as the
campfire — a hard ramp, ordered dither, quantized alpha — and it reads as part
of the game instead of as a filter laid over it.

UNLIKE THE CAMPFIRE, THIS DOES NOT LOOP. The campfire's frames are a cycle;
these are a TIMELINE, played once per arrival: charge, strike, impact,
collapse. Frame 0 and frame 13 are both empty-ish on purpose, so the effect can
be drawn from t=0 to t=duration with no pop at either end.

ANCHORING
The frame's contact line — where the beam meets the ground and where the
summoned player's feet land — is `anchorY` pixels down from the top, NOT the
bottom edge: the ground flash and the shockwave need rows below it to spread
into. The client draws the frame at `seatY - anchorY`.

Usage:
    python tools/make_vfx.py
    python tools/make_vfx.py --seed 7 --tile 16
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
    RGBA,
    Ramp,
    TRANSPARENT,
    clamp01,
    hash01,
    pack,
    pick,
    rgb,
)

# NEUTRAL ON PURPOSE — the hue is the client's to decide.
#
# The sheet is greyscale so it can be multiplied by whoever is arriving: their
# roster colour lands on the beam and the column becomes theirs, which is a
# thing a baked-in blue can never be. Ramp the steps here and every tint gets
# the same shape for free.
#
# The top step is pure white: the core of the column has to be the brightest
# pixel on screen at the moment of impact, or the strike has no punch — and
# under a multiply it is the step that comes out as the colour itself.
BEAM: Ramp = [
    rgb(c) for c in ("#232329", "#4a4a55", "#7d7d8c", "#b4b4c0", "#e2e2e8", "#ffffff")
]

SUMMON_FRAMES = 14
SUMMON_FPS = 14

# Timeline, in normalized frame time. The gaps matter more than the numbers:
# the pause between CHARGE and STRIKE is what makes the strike land.
CHARGE_START = 0.02
STRIKE_START = 0.20
IMPACT_AT = 0.52
COLLAPSE_START = 0.68

# The fire answering a start, not a beam arriving. Wider than a summon — a
# roar is a mass, not a thread — and it RISES from the pit. Charge, rise,
# impact, collapse. KINDLE_IMPACT is what the client aligns the ember burst to.
KINDLE_FRAMES = 16
KINDLE_FPS = 16
KINDLE_CHARGE = 0.02
KINDLE_RISE = 0.16
KINDLE_IMPACT = 0.48
KINDLE_COLLAPSE = 0.64


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _ease_in(t: float) -> float:
    return t * t


def _quantize_alpha(value: float) -> int:
    """Snap coverage to five steps.

    Smooth alpha on a pixel-art sprite reads as a soft PNG overlay laid on the
    scene; five hard steps read as light with an edge, which is what everything
    else in this game is made of.
    """
    steps = (0, 56, 118, 186, 255)
    return steps[int(clamp01(value) * (len(steps) - 1) + 0.5)]


def _add(field: list[list[float]], x: int, y: int, amount: float) -> None:
    if 0 <= y < len(field) and 0 <= x < len(field[0]):
        field[y][x] += amount


def _ellipse(
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
                _add(field, x, y, strength * edge)
            else:
                _add(field, x, y, strength * (1.0 - dist) ** 1.4)


def _column(
    field: list[list[float]],
    width: int,
    cx: float,
    top: float,
    bottom: float,
    half: float,
    strength: float,
    frame: int,
) -> None:
    """The shaft itself: a vertical band with a hot core and banded texture."""
    for y in range(max(0, int(top)), min(len(field), int(bottom) + 1)):
        # Flare where it meets the ground; the column is not a rectangle. The
        # taper is steep and the exponent holds it narrow for most of the drop:
        # a shaft that widens evenly from top to bottom reads as a wedge sitting
        # in the frame, while one that enters as a thread and only opens up near
        # the contact line reads as light arriving FROM somewhere above it.
        depth = clamp01((y - top) / max(bottom - top, 1.0))
        row_half = half * (0.20 + depth**1.35 * 1.15)
        # A narrow row spreads the same strength over fewer pixels, so without
        # a gain the thinned top fades out under the alpha quantization and the
        # beam comes out as a flare with nothing feeding it.
        row_gain = 1.0 + (1.0 - depth) * 0.45
        # Bands travelling DOWN the shaft. Tied to the frame index rather than
        # to y alone, so the texture moves instead of sitting still. Kept
        # shallow: at full contrast the shaft breaks into a dotted line and
        # stops reading as one continuous thing.
        band = 0.86 + 0.14 * math.sin(y * 0.34 - frame * 1.9)
        for x in range(int(cx - row_half) - 1, int(cx + row_half) + 2):
            if not 0 <= x < width:
                continue
            offset = abs(x - cx) / max(row_half, 0.5)
            if offset > 1.0:
                continue
            # A hot core inside a wide soft sheath. The exponent is the whole
            # look of the beam: too high and it is a thread with a halo.
            core = (1.0 - offset) ** 1.5
            grain = 0.9 + hash01(x, y, frame * 31 + 7) * 0.2
            _add(field, x, y, strength * core * band * grain * row_gain)


def make_summon_frame(
    width: int, height: int, contact_y: int, index: int, frames: int
) -> Image.Image:
    """One frame of the arrival: charge, strike, impact, collapse."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    t = index / (frames - 1)
    cx = (width - 1) / 2.0
    field = [[0.0] * width for _ in range(height)]

    # --- CHARGE: something is about to happen here ---------------------------
    if CHARGE_START <= t < IMPACT_AT:
        grow = clamp01((t - CHARGE_START) / (IMPACT_AT - CHARGE_START))
        # A pool of light gathering on the ground, plus a rim on it, so the
        # charge is legible from the first frame rather than a faint smudge
        # nobody notices until the beam is already falling.
        _ellipse(
            field,
            cx,
            contact_y,
            width * 0.20 + grow * width * 0.26,
            height * 0.024 + grow * height * 0.032,
            0.55 + grow * 0.75,
        )
        _ellipse(
            field,
            cx,
            contact_y,
            width * 0.22 + grow * width * 0.28,
            height * 0.026 + grow * height * 0.034,
            0.5 + grow * 0.5,
            hollow=0.34,
        )
        # Motes lifting OFF the ground, against the fall — the ground answering.
        for i in range(8):
            phase = (index * 0.75 + i * 1.7) % 4.0
            mx = int(round(cx + math.sin(i * 2.3 + index * 0.4) * width * 0.28))
            my = int(round(contact_y - phase * height * 0.045))
            _add(field, mx, my, (0.5 + grow * 0.6) * (1.0 - phase / 4.0))

    # --- STRIKE: the front descends ------------------------------------------
    if STRIKE_START <= t:
        if t < IMPACT_AT:
            drop = _ease_in((t - STRIKE_START) / (IMPACT_AT - STRIKE_START))
            front = drop * contact_y
            strength = 0.7 + drop * 0.55
            half = width * (0.17 + drop * 0.09)
        elif t < COLLAPSE_START:
            front = contact_y
            strength = 1.45
            half = width * 0.30
        else:
            fade = _ease_out((t - COLLAPSE_START) / (1.0 - COLLAPSE_START))
            front = contact_y
            strength = 1.3 * (1.0 - fade)
            # Narrows as it dies: the column is drawn back up, not switched off.
            half = width * (0.30 - fade * 0.25)
        _column(field, width, cx, 0, front, half, strength, index)

    # --- IMPACT: the flash and the wave it throws ----------------------------
    if IMPACT_AT <= t:
        since = (t - IMPACT_AT) / (1.0 - IMPACT_AT)
        flash = max(0.0, 1.0 - since * 2.2)
        if flash > 0.0:
            _ellipse(
                field,
                cx,
                contact_y,
                width * (0.30 + flash * 0.34),
                height * (0.034 + flash * 0.040),
                2.0 * flash,
            )
        # Two waves, the second late and slower, so the ground rings twice.
        for delay, span, weight in ((0.0, 0.62, 1.0), (0.16, 0.86, 0.65)):
            wave = (since - delay) / span
            if not 0.0 < wave < 1.0:
                continue
            radius = _ease_out(wave)
            _ellipse(
                field,
                cx,
                contact_y,
                width * 0.18 + radius * width * 0.36,
                height * 0.020 + radius * height * 0.040,
                (1.0 - wave) * 1.5 * weight,
                # Thick enough to survive the alpha quantization; a thin rim
                # comes out as a dotted ellipse rather than a wave.
                hollow=0.5,
            )
        # Sparks kicked out along the ground.
        for i in range(9):
            if hash01(i, index, 404) < 0.35:
                continue
            angle = hash01(i, 3, 77) * math.tau
            travel = since * width * (0.30 + hash01(i, 9, 5) * 0.34)
            sx = int(round(cx + math.cos(angle) * travel))
            sy = int(round(contact_y + math.sin(angle) * travel * 0.34 - since * height * 0.05))
            _add(field, sx, sy, max(0.0, 0.95 - since * 1.4))

    # --- resolve -------------------------------------------------------------
    px = img.load()
    for y in range(height):
        for x in range(width):
            value = field[y][x]
            if value <= 0.07:
                continue
            colour: RGBA = pick(BEAM, clamp01(value * 0.92), x, y)
            px[x, y] = (colour[0], colour[1], colour[2], _quantize_alpha(value * 1.1))
    return img


def _kindle_flames(
    field: list[list[float]],
    width: int,
    cx: float,
    base_y: float,
    reach: float,
    strength: float,
    frame: int,
) -> None:
    """The fire's own tongues, scaled up into a roar.

    Same idea as `_flame_field` in make_textures.py: three overlapping tongues
    summed, not drawn as separate shapes, so the crossing is the hot core.
    Authored here rather than imported because the prop's sway is in pixels
    sized for a 24px pit; a 48px column needs a lean that actually travels.
    """
    if reach < 1.0:
        return
    phase = frame * 0.62
    tongues = (
        # (half width, height ratio, sway px, sway harmonic, phase offset)
        # Wider than a summon's shaft: a roar is a mass sitting on the pit.
        (width * 0.38, 0.86, 4.2, 1, 0.0),
        (width * 0.24, 1.00, 6.4, 2, 2.1),
        (width * 0.16, 0.74, 7.2, 3, 4.3),
        (width * 0.12, 0.54, 5.2, 2, 1.1),
    )
    for half_w, tall, sway, harmonic, offset in tongues:
        span = reach * tall
        steps = int(span * 2.4)
        for step in range(steps + 1):
            t = step / max(steps, 1)
            lean = math.sin(phase * harmonic + offset + t * 2.8) * sway * t
            fx = cx + lean
            fy = base_y - t * span
            # Soft taper: a high exponent pinches the column into a thread
            # two-thirds of the way up and the roar reads as a second summon.
            half = max(0.8, half_w * (1.0 - t) ** 0.38)
            # Bands travelling UP the shaft — fire rises; the summon's travel
            # the other way. Tied to the frame so the texture moves.
            band = 0.86 + 0.14 * math.sin((base_y - fy) * 0.30 + frame * 1.7)
            y = int(round(fy))
            for x in range(int(fx - half) - 1, int(fx + half) + 2):
                if not 0 <= x < width:
                    continue
                radial = abs(x - fx) / half
                if radial > 1.0:
                    continue
                core = (1.0 - radial) ** 1.35
                grain = 0.88 + hash01(x, y, frame * 17 + 3) * 0.24
                # Hottest at the root, cooler at the tip — same rule as the
                # campfire sprite, or the column reads as a white slab.
                cool = 1.0 - t * 0.30
                _add(field, x, y, strength * core * band * grain * cool)


def make_kindle_frame(
    width: int, height: int, contact_y: int, index: int, frames: int
) -> Image.Image:
    """One frame of the fire answering: charge, rise, impact, collapse."""
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    t = index / (frames - 1)
    cx = (width - 1) / 2.0
    field = [[0.0] * width for _ in range(height)]

    # --- CHARGE: the pit gathers itself --------------------------------------
    if KINDLE_CHARGE <= t < KINDLE_IMPACT:
        grow = clamp01((t - KINDLE_CHARGE) / (KINDLE_IMPACT - KINDLE_CHARGE))
        # A pool of heat on the coals, plus a rim, so the charge is a thing
        # you see — not a smudge that only makes sense once the column is up.
        _ellipse(
            field,
            cx,
            contact_y,
            width * 0.16 + grow * width * 0.28,
            height * 0.022 + grow * height * 0.036,
            0.65 + grow * 0.85,
        )
        _ellipse(
            field,
            cx,
            contact_y,
            width * 0.18 + grow * width * 0.30,
            height * 0.024 + grow * height * 0.038,
            0.55 + grow * 0.55,
            hollow=0.36,
        )
        # Embers lifting OFF the pit — the fire inhaling.
        for i in range(10):
            phase = (index * 0.85 + i * 1.6) % 5.0
            mx = int(round(cx + math.sin(i * 2.1 + index * 0.45) * width * 0.26))
            my = int(round(contact_y - phase * height * 0.055))
            _add(field, mx, my, (0.55 + grow * 0.7) * (1.0 - phase / 5.0))

    # --- RISE: the column climbs out of the pit ------------------------------
    if KINDLE_RISE <= t:
        if t < KINDLE_IMPACT:
            climb = _ease_out((t - KINDLE_RISE) / (KINDLE_IMPACT - KINDLE_RISE))
            reach = climb * contact_y * 0.96
            strength = 0.95 + climb * 0.85
        elif t < KINDLE_COLLAPSE:
            reach = contact_y * 0.96
            strength = 1.85
        else:
            fade = _ease_out((t - KINDLE_COLLAPSE) / (1.0 - KINDLE_COLLAPSE))
            # Drawn back INTO the pit, not switched off — the fire keeps the
            # heat and lets the column go.
            reach = contact_y * (0.96 - fade * 0.70)
            strength = 1.55 * (1.0 - fade)
        _kindle_flames(field, width, cx, contact_y, reach, strength, index)
        # A wide bloom at the coals for the whole rise, so the column is
        # sitting IN the fire rather than hovering a thread above it.
        if reach > 2.0:
            bloom = min(1.0, strength / 1.85)
            _ellipse(
                field,
                cx,
                contact_y,
                width * (0.22 + bloom * 0.16),
                height * (0.028 + bloom * 0.022),
                0.9 * bloom,
            )

    # --- IMPACT: the flash and the wave the hearth throws --------------------
    if KINDLE_IMPACT <= t:
        since = (t - KINDLE_IMPACT) / (1.0 - KINDLE_IMPACT)
        flash = max(0.0, 1.0 - since * 2.0)
        if flash > 0.0:
            _ellipse(
                field,
                cx,
                contact_y,
                width * (0.28 + flash * 0.38),
                height * (0.032 + flash * 0.048),
                2.2 * flash,
            )
        # Two waves, the second late and slower, so the ground rings twice.
        # Wider than a summon's: this is the whole hearth answering, not a seat.
        for delay, span, weight in ((0.0, 0.58, 1.0), (0.14, 0.82, 0.62)):
            wave = (since - delay) / span
            if not 0.0 < wave < 1.0:
                continue
            radius = _ease_out(wave)
            _ellipse(
                field,
                cx,
                contact_y,
                width * 0.20 + radius * width * 0.42,
                height * 0.022 + radius * height * 0.046,
                (1.0 - wave) * 1.55 * weight,
                hollow=0.5,
            )
        for i in range(12):
            if hash01(i, index, 505) < 0.32:
                continue
            angle = hash01(i, 4, 81) * math.tau
            travel = since * width * (0.28 + hash01(i, 11, 6) * 0.38)
            sx = int(round(cx + math.cos(angle) * travel))
            sy = int(round(contact_y + math.sin(angle) * travel * 0.32 - since * height * 0.08))
            _add(field, sx, sy, max(0.0, 1.0 - since * 1.35))

    px = img.load()
    for y in range(height):
        for x in range(width):
            value = field[y][x]
            if value <= 0.07:
                continue
            colour: RGBA = pick(BEAM, clamp01(value * 0.92), x, y)
            px[x, y] = (colour[0], colour[1], colour[2], _quantize_alpha(value * 1.1))
    return img


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "vfx"
    out_dir.mkdir(parents=True, exist_ok=True)

    width = tile * 2
    height = tile * 6
    # Rows below the contact line are where the flash and the shockwave spread.
    contact_y = height - round(tile * 0.75)
    frames = [
        make_summon_frame(width, height, contact_y, i, SUMMON_FRAMES)
        for i in range(SUMMON_FRAMES)
    ]
    pack(frames, width, height).save(out_dir / "summon.png")

    # Wider than a summon: a roar is a mass sitting on the hearth, not a
    # thread delivering one body. Same height and contact row so the two
    # sheets share an anchor language.
    kindle_w = tile * 3
    kindle_h = tile * 6
    kindle_contact = kindle_h - round(tile * 0.75)
    kindle_frames = [
        make_kindle_frame(kindle_w, kindle_h, kindle_contact, i, KINDLE_FRAMES)
        for i in range(KINDLE_FRAMES)
    ]
    pack(kindle_frames, kindle_w, kindle_h).save(out_dir / "kindle.png")

    manifest = {
        "tile": tile,
        "effects": {
            "summon": {
                "file": "summon.png",
                "frameWidth": width,
                "frameHeight": height,
                "frames": SUMMON_FRAMES,
                "fps": SUMMON_FPS,
                # Distance from the top of the frame to the ground contact line.
                # The client draws at `y - anchorY`, NOT bottom-anchored.
                "anchorY": contact_y,
                # Plays once per event; do not loop it.
                "loop": False,
            },
            "kindle": {
                "file": "kindle.png",
                "frameWidth": kindle_w,
                "frameHeight": kindle_h,
                "frames": KINDLE_FRAMES,
                "fps": KINDLE_FPS,
                "anchorY": kindle_contact,
                "loop": False,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: summon {SUMMON_FRAMES}x{width}x{height} "
        f"@ {SUMMON_FPS}fps, kindle {KINDLE_FRAMES}x{kindle_w}x{kindle_h} "
        f"@ {KINDLE_FPS}fps, contact row {contact_y}/{kindle_contact}"
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
