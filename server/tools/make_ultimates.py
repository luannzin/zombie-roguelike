#!/usr/bin/env python3
"""Asset pipeline: ULTIMATE ICONS — one mark per ultimate, for the HUD panel.

Output (assets/processed/ultimates/):
    sheet.png      one 20x20 icon per ultimate, left to right in catalog order
    manifest.json  frame index per ultimate key, plus the cell size

WHY THESE ARE DRAWN WITH MATHS AND NOT WITH CHARACTER MAPS
==========================================================
Every other icon sheet in this game is a hand-authored grid, and that is right
for what those sheets contain: a helmet, a hammer, a boot, a heart. Those are
OBJECTS, and an object is a silhouette you author pixel by pixel because no
formula knows where a claw hammer's cheek goes.

An ultimate is not an object. All four of these are ENERGY — an arc of steel
leaving a blade, one round with a lance of light in front of it, a fan of
tracers, a pulse going out from a body — and the shapes energy makes are
circles, arcs, rays and stars. Authoring a circle as a character map at twenty
pixels produces a lumpy polygon, and authoring FOUR of them produces four
lumpy polygons that do not match each other. The arcs here are the same arcs
`make_vfx.py` and `make_weapon_vfx.py` draw for the same reason.

WHAT THEY HAVE TO SAY, IN ORDER
===============================
1. WHICH ULTIMATE THIS IS, from the silhouette alone, on a 32px tile the
   player glances at mid-fight. Four marks: an ARC, a ROUND, a FAN, a RING.
   No two of them share a gesture, which is the same rule the creature sheets
   keep and for the same reason.
2. THAT IT IS ENERGY rather than a thing. Every icon here is drawn with a
   bright core and a dimmer body, so it reads as something emitting rather
   than something lit. That is the one place these part company with the skill
   tray, whose icons are deliberately lit objects.
3. NOTHING ABOUT ITS STATE. Locked, charging and ready are the PANEL's job —
   they are three different treatments of the same mark, done in CSS on one
   image, because an ultimate that changed picture as it charged would make
   the player learn four icons instead of one.

ONE ACCENT HUE EACH, AND THEY ARE THE FOUR IDENTITIES
The colours are not decoration: they are the same four builds the armour
ladder is, so a player who has learnt that Sombra is violet reads the katana's
mark before its shape resolves. Violet for the assassin, amber for the
marksman, orange for the gunner, green for the medic.

Usage:
    python tools/make_ultimates.py
    python tools/make_ultimates.py --cell 20
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image

from make_textures import (
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    material_ramp,
    outline,
    pack,
    rgb,
)

#: The cell every icon is drawn in. Bigger than a skill tile (16) because this
#: is the only icon in the game that gets a panel to itself — and because
#: three of the four marks are ARCS, which need the extra radius before their
#: curvature reads as curvature rather than as a staircase.
CELL = 20

OUTLINE: RGBA = rgb("#06070b")

# --- the four identities ------------------------------------------------------
#
# Each is a five-step ramp out of S11's law, exactly like every other sheet:
# authored as a hue, how saturated it is, and where its two ends sit. The
# CEILINGS are the highest in the game and that is deliberate — these are
# drawn on an inset HUD panel rather than on soil, they are meant to read as
# LIGHT, and the panel behind them is the darkest surface the game has.

#: The assassin. Violet, and it is the one hue nothing else in the HUD spends.
SHADOW: Ramp = material_ramp(276, 0.42, 0.16, 0.86)
#: The marksman. Amber — the colour of a round, and the one warm mark that is
#: not fire.
BRASS: Ramp = material_ramp(41, 0.62, 0.15, 0.90)
#: The gunner. Hot orange, a step past brass, because a storm of tracers has
#: to out-burn a single round sitting next to it in a shop.
BLAZE: Ramp = material_ramp(22, 0.72, 0.16, 0.92)
#: The medic. The one cool-green in the game, and the same family the heal
#: float already uses.
VITAL: Ramp = material_ramp(146, 0.48, 0.16, 0.88)

#: The dark counterpart every mark is bedded on. Not black: a mark with no
#: body reads as a line drawing, and every other sheet in this game says form
#: with a value STEP rather than with an outline.
GLOOM: Ramp = material_ramp(240, 0.16, 0.06, 0.34)


# --- primitives ---------------------------------------------------------------
#
# Four functions, and between them they draw all four icons. Each one takes a
# STEP rather than a colour: the ramp is chosen per icon and the step is what
# says core-or-body, so an icon is authored as geometry plus brightness and
# never as hex.


def _put(px, size: int, x: int, y: int, ramp: Ramp, step: int) -> None:
    if 0 <= x < size and 0 <= y < size:
        px[x, y] = ramp[max(0, min(step, len(ramp) - 1))]


def _arc(px, size, cx, cy, radius, thick, a0, a1, ramp, step, core=None):
    """A band of an annulus, swept between two angles.

    Sampled by ANGLE rather than by scanning the box, because a scan tests
    every pixel in the cell against two radii and an angle range and still
    leaves gaps on the diagonals at this size. Stepping the angle finely
    enough that consecutive samples overlap is what makes a twenty-pixel arc
    come out solid.
    """
    steps = max(24, int(radius * 14))
    for i in range(steps + 1):
        angle = a0 + (a1 - a0) * i / steps
        for t in range(thick):
            r = radius - t
            x = int(round(cx + math.cos(angle) * r))
            y = int(round(cy + math.sin(angle) * r))
            # The OUTER band is the core, the inner ones are the body. An arc
            # lit on its leading edge reads as travelling; lit evenly it reads
            # as a drawn line.
            _put(px, size, x, y, ramp, step if (t or core is None) else core)


def _ray(px, size, x0, y0, x1, y1, ramp, step, thick=1):
    """A straight run, thickened perpendicular to itself."""
    dx, dy = x1 - x0, y1 - y0
    steps = max(2, int(max(abs(dx), abs(dy)) * 2))
    nx, ny = -dy, dx
    length = math.hypot(nx, ny) or 1.0
    nx, ny = nx / length, ny / length
    for i in range(steps + 1):
        px_, py_ = x0 + dx * i / steps, y0 + dy * i / steps
        for t in range(thick):
            off = t - (thick - 1) / 2.0
            _put(px, size, int(round(px_ + nx * off)), int(round(py_ + ny * off)), ramp, step)


def _disc(px, size, cx, cy, radius, ramp, step, core=None):
    """A filled circle, optionally with a brighter cap toward the key light."""
    r2 = radius * radius
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy > r2:
                continue
            # The key is at 135deg, up and left, exactly as it is on every
            # other sheet in this game — the icon that lit itself from a
            # second angle would be the one that looks borrowed.
            lit = core is not None and (dx + dy) < -radius * 0.35
            _put(px, size, x, y, ramp, core if lit else step)


def _star(px, size, cx, cy, arms, inner, outer, ramp, step, phase=0.0):
    """A burst: `arms` rays out of one point. What an impact looks like."""
    for i in range(arms):
        angle = phase + i * (math.tau / arms)
        _ray(
            px, size,
            cx + math.cos(angle) * inner, cy + math.sin(angle) * inner,
            cx + math.cos(angle) * outer, cy + math.sin(angle) * outer,
            ramp, step,
        )


# --- the four marks -----------------------------------------------------------


def _shadow_slash(px, size):
    """AN ARC WITH A TRAIL BEHIND IT. The gesture is a sword coming round.

    Two arcs on one centre: a bright leading edge and a dim one a couple of
    pixels back on the same sweep, which is what says the steel is TRAVELLING.
    A single arc, however thick, is a crescent moon.

    It is swept from the lower left to the upper right — the direction the
    held-weapon sheet swings — and it is open on the side the blade came from,
    so the mark has a start and an end rather than being a symmetric lens.
    """
    c = size / 2.0
    _arc(px, size, c + 1.5, c + 1.0, size * 0.42, 3, math.radians(-118), math.radians(56),
         SHADOW, 2, core=4)
    # The trail: the same sweep, shorter and dimmer, a step behind.
    _arc(px, size, c + 3.2, c + 2.4, size * 0.42, 2, math.radians(-104), math.radians(20),
         GLOOM, 2)
    # The tip, where the edge is moving fastest and the light concentrates.
    tip_a = math.radians(56)
    _disc(px, size, c + 1.5 + math.cos(tip_a) * size * 0.42,
          c + 1.0 + math.sin(tip_a) * size * 0.42, 1.6, SHADOW, 3, core=5)


def _extreme_shot(px, size):
    """ONE ROUND, AND A LANCE OF LIGHT IN FRONT OF IT.

    The only icon here whose subject is an OBJECT, and the composition is what
    keeps it from reading as a bullet pickup: the round sits back on the left,
    the lance runs off the right edge of the cell, and the two crosshair ticks
    frame the lane rather than the round. What the mark says is "this is going
    somewhere", which is the ultimate — a Deagle shot that crosses the map.
    """
    c = size / 2.0
    # The lane, running clean off the edge.
    _ray(px, size, 5, c, size - 1, c, BRASS, 4, thick=2)
    _ray(px, size, 6, c, size - 4, c, BRASS, 1, thick=4)
    # The round: a body and an ogive, drawn as two discs so the nose is
    # narrower than the case without a second shape to author.
    _disc(px, size, 5.0, c, 3.2, BRASS, 2, core=4)
    _disc(px, size, 7.4, c, 2.1, BRASS, 3, core=5)
    # The ticks. Above and below the lane and NOT touching it — a crosshair
    # that closed would read as a scope reticle, which is a different verb.
    for sign in (-1, 1):
        _ray(px, size, size - 6, c + sign * 4, size - 2, c + sign * 4, BRASS, 3)
        _ray(px, size, size - 2, c + sign * 4, size - 2, c + sign * 2, BRASS, 3)


def _bullet_storm(px, size):
    """A FAN. Three lanes leaving one point, and a burst where they arrive.

    The one mark here built out of straight lines, which is most of why it
    reads against the other three at a glance: an arc, a round, a RAY FAN and
    a ring are four different gestures before any of them is a picture.

    The lanes are unequal in length on purpose. Three parallel bars of the
    same length is a menu glyph; three that fan and overshoot each other is
    something being sprayed.
    """
    c = size / 2.0
    ox, oy = 2.0, c + 3.5
    for index, (angle, reach, step) in enumerate((
        (-38.0, size * 0.92, 2),
        (-24.0, size * 0.80, 4),
        (-10.0, size * 0.70, 3),
    )):
        a = math.radians(angle)
        _ray(px, size, ox, oy, ox + math.cos(a) * reach, oy + math.sin(a) * reach,
             BLAZE, step, thick=2 if index == 1 else 1)
    # The muzzle end: a small mass, so the fan comes OUT of something.
    _disc(px, size, ox + 1.0, oy - 0.5, 2.4, GLOOM, 2)
    # And the far end, where it is landing.
    a = math.radians(-24.0)
    _star(px, size, ox + math.cos(a) * size * 0.80, oy + math.sin(a) * size * 0.80,
          6, 1.2, 4.0, BLAZE, 4, phase=math.radians(15))


def _emergency_protocol(px, size):
    """A RING GOING OUT, WITH A CROSS INSIDE IT.

    The only closed shape on the sheet, which is the whole reason it is a ring:
    the other three marks all have a direction and this one deliberately has
    none, because what it does is not aimed. A player who reads "this one is
    not pointed at anything" from the silhouette alone has read the mechanic.

    TWO rings, the outer one dimmer and broken. A single ring is a circle; two
    at different brightness with a gap in the outer one is a pulse, mid-travel.
    """
    c = size / 2.0
    # The outer pulse: broken at the upper right so the shape is not a perfect
    # annulus, which is the difference between "expanding" and "drawn".
    _arc(px, size, c, c, size * 0.44, 1, math.radians(-52), math.radians(268), GLOOM, 3)
    _arc(px, size, c, c, size * 0.32, 2, math.radians(-140), math.radians(160), VITAL, 3, core=5)
    # The cross. Fat and short — a thin one at this size disappears into the
    # ring around it, and a long one touches it and closes the composition.
    _ray(px, size, c, c - 3.4, c, c + 3.4, VITAL, 4, thick=3)
    _ray(px, size, c - 3.4, c, c + 3.4, c, VITAL, 4, thick=3)


#: Order is FRAME ORDER, and it mirrors `server/app/ultimates.ULTIMATES`. The
#: manifest is keyed by ULTIMATE KEY, so nothing downstream depends on this
#: list's order — but `build` checks the two lists hold the same keys, because
#: an ultimate the server can offer and this cannot draw is a HUD panel with a
#: hole in it, and it is the one failure a screenshot of the shop will not show.
MARKS = (
    ("shadow_slash", _shadow_slash),
    ("extreme_shot", _extreme_shot),
    ("bullet_storm", _bullet_storm),
    ("emergency_protocol", _emergency_protocol),
)


def _icon(draw, cell: int) -> Image.Image:
    img = Image.new("RGBA", (cell, cell), TRANSPARENT)
    draw(img.load(), cell)
    # The keyline last, exactly as every other sheet does it: a mark on a dark
    # panel needs a hard edge or the panel's own inset shadow eats its border.
    outline(img, OUTLINE)
    return img


def _check_against_server() -> None:
    """The catalog and this sheet have to hold the same keys.

    BEST EFFORT AND DELIBERATELY SO. This is an art pipeline and it has to run
    with the game server absent — a designer regenerating icons should not need
    the app importable — so a failed import is a skipped check rather than a
    failed build. What it catches when it can run is the only thing worth
    catching here: an ultimate with no mark, which draws an empty panel that
    still fires.
    """
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app import ultimates  # noqa: PLC0415
    except Exception:
        print("  (server catalog not importable — skipping the key check)")
        return
    mine = {key for key, _ in MARKS}
    theirs = set(ultimates.BY_KEY)
    if mine != theirs:
        raise ValueError(
            f"ultimates without a mark: {sorted(theirs - mine)}; "
            f"marks without an ultimate: {sorted(mine - theirs)}"
        )


def build(args) -> Path:
    cell = args.cell
    out_dir = PROCESSED_DIR / "ultimates"
    out_dir.mkdir(parents=True, exist_ok=True)
    _check_against_server()

    frames = [_icon(draw, cell) for _, draw in MARKS]
    pack(frames, cell, cell).save(out_dir / "sheet.png")
    manifest = {
        "cell": cell,
        "frames": len(frames),
        "items": {key: {"frame": index} for index, (key, _) in enumerate(MARKS)},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(frames)} marks @ {cell}x{cell}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=int, default=CELL)
    build(ap.parse_args())


if __name__ == "__main__":
    main()
