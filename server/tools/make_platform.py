#!/usr/bin/env python3
"""Asset pipeline: the extraction PLATFORM — the thing that carries loot out.

Everything else in `scenery/` is something people left behind. This is the one
object on the map that answers back, and what it is is a CARGO SKID somebody
abandoned in the woods: a welded iron box open at the front, still half full of
crates nobody came back for, with four dead lift drones parked at its corners
on the ropes they were rigged to.

Output (assets/processed/platform/):
    platform.png  2 frames,  80x64  PROP  — the skid, cold then powered
    drone.png     2 frames,  24x16  PROP  — a lift drone, dead then live
    rotor.png     8 frames,  28x12  VFX   — loop: four discs turning
    strobe.png    8 frames,  24x16  VFX   — loop: a live drone's nav lights
    imprint.png   1 frame,   80x48  DECAL — the hole in the ground it left
    downwash.png  12 frames, 112x56 VFX   — loop: rotor wash under a straining
                                            platform
    burst.png     12 frames, 128x64 VFX   — one-shot: the ground letting go
    manifest.json

THE THREE SHAPES, THE SAME SPLIT `make_rift.py` DOCUMENTS
`platform` and `drone` are PROPS: baked colour, bottom-anchored, in the depth
sort, multiplied by the night like every trunk on the map. `imprint` is a
DECAL — flat, no outline, drawn `multiply` + `lighter` in two halves so the
soil's own grain reads through the dent. `rotor` / `strobe` / `downwash` /
`burst` are VFX: summed into an intensity field and resolved once, drawn
additively AFTER the darkness pass, because a rotor disc catching the light is
light and not a thing being lit.

WHY THE EYES ARE IN THE MANIFEST
The ropes are drawn LIVE by the client — a rope between a fixed eye and a drone
that climbs, strains and then flies off cannot be a sprite. So the four lift
eyes ship as pixel offsets from the platform's contact point (`layout.eyes`),
in the same order the server places the drones, and both sides read that one
list. Baking a rope into the platform sheet would freeze the one part of this
structure whose whole job is to move.

WHY IT IS IRON AND NOT STONE
This replaced a ring of quarried stones around a tear in the world. The tear
was the odd one out on purpose and the stones were its plumbing; a skid with
crates still in it is the opposite claim — somebody's equipment, left here,
that works again if you feed it. `IRON` therefore comes from `make_rift.py`
rather than being re-typed: the console you press is the same metal as the deck
it is bolted beside, and one game has one steel in it.

Usage:
    python tools/make_platform.py
    python tools/make_platform.py --seed 7 --tile 16
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
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TIMBER,
    TIMBER_OUTLINE,
    TRANSPARENT,
    add,
    clamp01,
    ease_in,
    ease_out,
    ellipse,
    hash01,
    pack,
    pick,
    resolve,
    rgb,
)
from make_rift import IRON, SOCKET

# --- materials ---------------------------------------------------------------

#: The outline every piece of this structure is keyed with. Darker than `IRON`'s
#: own bottom step, because a silhouette sharing a value with the body it
#: surrounds stops being a silhouette the moment the night multiply lands.
EDGE = rgb("#0a0b0d")

#: Corrosion. Warm, and the only warm thing in the metal — which is what makes
#: it read as AGE rather than as paint: the skid has stood in a wet forest for
#: years and the water ran down from every seam and rivet.
RUST: Ramp = [rgb(c) for c in ("#2b1a10", "#40281a", "#573624", "#6f4630", "#8a5c3e")]

#: Hazard paint on the front threshold, half worn off. The one saturated colour
#: on the whole prop and it earns its place: black-and-yellow chevrons are the
#: single most legible way a 16px world can say "machinery, stand clear", and
#: they are what a player picks the pad out by from across a clearing before
#: any of the detail resolves.
HAZARD: Ramp = [rgb(c) for c in ("#4a3a10", "#7d6117", "#b89122", "#e5bb3a")]

#: A powered fitting. GREEN, because every other light in this game is fire or
#: the beacon's mint, and a machine reporting that it is running must be
#: neither — the console goes gold when the quota lands and the deck must not
#: compete with it.
STATUS: Ramp = [rgb(c) for c in ("#0c2415", "#155c30", "#27a557", "#63e894", "#c8ffdd")]

#: A live drone's tail light. Red, and dim: a marker, not a lamp.
STROBE: Ramp = [rgb(c) for c in ("#2a0808", "#6e1414", "#c02424", "#ff6a5a")]

#: Rope. Three usable steps is all a two-pixel line can spend, and the client
#: draws the rigging from these rather than from a sprite — see `layout.rope`.
ROPE: Ramp = [rgb(c) for c in ("#1a1409", "#33280f", "#4d3c19", "#6b5527")]

#: What the skid crushed: soil that has been under a tonne of iron for years —
#: pressed flat, dead, and darker than the ground beside it.
#:
#: NOT BLACK. These are multiplied over live terrain, so the ramp only has to
#: take light OUT of the soil — pushed to the bottom of the scale the mark
#: stops reading as pressed ground and starts reading as a hole in the floor,
#: which is the one thing it must not be now that the platform is gone and the
#: party can walk over it.
PRESSED: Ramp = [rgb(c) for c in ("#1b1d16", "#22251b", "#2b2e22", "#353829", "#404432")]
#: Oil, and the grit that came out from under the skid feet.
OIL = rgb("#08080b")
GRIT: Ramp = [rgb(c) for c in ("#3a3428", "#4a4234", "#5b5142")]


# --- the skid ----------------------------------------------------------------
#
# THE PLOT IS 7x7 AND THE SKID IS 5x4 OF IT. The rest is the approach: the tile
# the console stands on, the tile the torch stands on, and a lane down each
# side wide enough for a body to get round the back. A structure that filled
# its own plot would be a wall with a button on it.

PLATFORM_TILES_W = 5
PLATFORM_TILES_H = 4

#: Cold, powered. STATES, never variants — the frame index says whether the
#: thing is switched on, and rolling one would make the pad flicker.
PLATFORM_STATES = 2
PLATFORM_COLD, PLATFORM_LIVE = range(PLATFORM_STATES)

#: Dead, live. Same rule.
DRONE_STATES = 2
DRONE_DEAD, DRONE_LIVE = range(DRONE_STATES)

#: Four corners, and THE ORDER IS THE CONTRACT — `layout.eyes` here, `_DRONES`
#: in `server/app/rift.py` and the order the client wakes them are one list. It
#: runs on the DIAGONAL (front-left, back-right, front-right, back-left) rather
#: than around the rim, so a platform lifting on two drones is lifting on
#: opposite corners and hangs level instead of hinging.
DRONES = 4

ROTOR_FRAMES = 8
ROTOR_FPS = 24
STROBE_FRAMES = 8
STROBE_FPS = 8
DOWNWASH_FRAMES = 12
DOWNWASH_FPS = 12
BURST_FRAMES = 12
BURST_FPS = 18


def _rows(height: int) -> dict[str, float]:
    """The skid's horizontal landmarks, as fractions of its own height.

    Authored against 64px and expressed as fractions so `--tile` still produces
    a coherent box. Every one of these is a FOLD in the object — the eye reads
    this shape entirely off where one surface stops and the next begins — so
    they are named after the surfaces rather than left as loose numbers.
    """
    h = height
    return {
        "post_top": 0.047 * h,    # the back posts' eyes, above everything
        "back_top": 0.141 * h,    # top rail of the back wall
        "back_face": 0.219 * h,   # where the rail ends and the inside face starts
        "post_front": 0.391 * h,  # the front posts start here
        "deck_far": 0.453 * h,    # far edge of the floor
        "lip_top": 0.734 * h,     # the front threshold
        "deck_near": 0.797 * h,   # near edge of the floor / top of the skid beams
        "base_bot": 0.953 * h,    # the feet
    }


def _half(width: int, height: int, y: float) -> float:
    """Half the silhouette's width at row `y`.

    THE TAPER IS THE PERSPECTIVE. Narrow at the back, wide at the front, and
    that one gradient is the only thing telling the eye it is looking into an
    open box rather than at a flat panel. Drawn with parallel sides it reads as
    a doorway.
    """
    r = _rows(height)
    far = width * 0.375
    near = width * 0.463
    if y <= r["back_top"]:
        return far
    if y >= r["deck_near"]:
        # The box overhangs its own beams, which is what stops the bottom edge
        # reading as the floor line.
        t = (y - r["deck_near"]) / max(height - r["deck_near"], 1.0)
        return near - t * width * 0.030
    t = (y - r["back_top"]) / max(r["deck_near"] - r["back_top"], 1.0)
    return far + (near - far) * t


def _eyes(width: int, height: int) -> tuple[tuple[float, float], ...]:
    """The four lift eyes, in pixels from the sprite's top-left.

    Ordered front-left, back-right, front-right, back-left — the diagonal order
    `DRONES` documents. `_layout` converts these to offsets from the CONTACT
    point, which is the frame the client and the server both work in.
    """
    r = _rows(height)
    cx = (width - 1) / 2.0
    back_x = _half(width, height, r["back_top"]) - width * 0.035
    # Held IN off the near corner by more than the back pair. An eye sitting on
    # the widest row of the silhouette has half its ring outside the frame, and
    # a lift point that is clipped is a lift point the ropes appear to miss.
    front_x = _half(width, height, r["deck_near"]) - width * 0.078
    back_y = r["post_top"] + height * 0.031
    front_y = r["post_front"] + height * 0.031
    return (
        (cx - front_x, front_y),
        (cx + back_x, back_y),
        (cx + front_x, front_y),
        (cx - back_x, back_y),
    )


def make_platform(width: int, height: int, state: int, rng: random.Random) -> Image.Image:
    """One skid. PROP: baked colour, bottom-anchored, lit by the night.

    Built surface by surface rather than shape by shape, because that is what
    the eye is actually reading: a top rail catching the sky, the inside of a
    back wall in its own shadow, a floor with things standing on it, a
    threshold, and the beams underneath. Drawing an outline first and filling
    it produces a box with no inside.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    r = _rows(height)
    cx = (width - 1) / 2.0
    live = state == PLATFORM_LIVE
    wall = max(3.0, width * 0.062)

    # --- the body ------------------------------------------------------------
    body: dict[tuple[int, int], str] = {}
    for y in range(int(r["back_top"]), int(r["base_bot"]) + 1):
        half = _half(width, height, y + 0.5)
        inner = half - wall
        for x in range(width):
            u = x - cx
            if abs(u) > half:
                continue
            if y >= r["deck_near"]:
                body[(x, y)] = "base"
            elif y >= r["lip_top"]:
                body[(x, y)] = "lip"
            elif y < r["back_face"]:
                # The back wall's own top rail spans the full width: it is the
                # far edge of the box, not a frame around a hole.
                body[(x, y)] = "rail"
            elif abs(u) > inner:
                body[(x, y)] = "side"
            elif y < r["deck_far"]:
                body[(x, y)] = "back"
            else:
                body[(x, y)] = "floor"

    for (x, y), part in body.items():
        u = (x - cx) / max(_half(width, height, y + 0.5), 1.0)
        grain = (hash01(x, y, 907) - 0.5) * 0.13
        if part == "rail":
            # The one surface pointed at the sky, and the reason the box has a
            # readable top edge at all. The topmost row of it is the CATCH —
            # a rail shaded evenly is a grey band, and a grey band across the
            # top of a sprite reads as a wall behind the object.
            catch = 1.0 if y <= r["back_top"] + 1 else 0.0
            shade = 0.58 + catch * 0.30 - abs(u) * 0.16 - (y - r["back_top"]) * 0.030
        elif part == "back":
            # Inside a wall, facing the camera and shaded by its own overhang:
            # darkest right under the rail, opening up as it falls to the floor.
            t = (y - r["back_face"]) / max(r["deck_far"] - r["back_face"], 1.0)
            shade = 0.11 + ease_out(t) * 0.17 - abs(u) * 0.07
        elif part == "side":
            # Inner faces of the side walls: shadow on the left, a catch on the
            # right, so the box is lit from the upper left like everything else.
            shade = 0.26 + (u * 0.30) - (y / height) * 0.06
        elif part == "floor":
            # THE DECK HAS TO BE THE LIGHT SURFACE. It is the only thing in
            # here pointed up at the sky, and drawn as dark as the walls the
            # whole interior collapses into one textured rectangle with crates
            # floating in it. It still falls off toward the back, where the
            # walls close over it.
            t = (y - r["deck_far"]) / max(r["lip_top"] - r["deck_far"], 1.0)
            shade = 0.30 + ease_in(t) * 0.30 - abs(u) * 0.06
            # Plate seams: this is a floor made of welded sheet, and two dark
            # lines are the cheapest way to say a surface has a scale.
            if int(abs(x - cx)) % 13 == 6:
                shade -= 0.16
        elif part == "lip":
            shade = 0.62 - abs(u) * 0.12
        else:
            t = (y - r["deck_near"]) / max(r["base_bot"] - r["deck_near"], 1.0)
            shade = 0.34 - t * 0.20 - abs(u) * 0.10
        px[x, y] = pick(IRON, clamp01(shade + grain), x, y)

    # The fold where the back wall meets the deck. One dark row, and it is what
    # makes the floor read as going UNDER the wall rather than butting into it.
    for x in range(width):
        for row in (int(r["deck_far"]) - 1, int(r["deck_far"])):
            if body.get((x, row)) in ("back", "floor"):
                px[x, row] = IRON[0]

    # --- corrosion -----------------------------------------------------------
    # Rust RUNS DOWNWARD from seams, because water does. Streaks starting
    # anywhere else read as brown paint, which is the failure mode of every
    # weathered-metal sprite.
    for _ in range(int(width * 0.9)):
        sx = rng.randrange(width)
        sy = rng.randrange(int(r["back_top"]), int(r["deck_near"]))
        run = rng.randint(2, max(3, height // 9))
        heat = rng.uniform(0.35, 0.95)
        for step in range(run):
            y = sy + step
            if (sx, y) not in body:
                break
            if body[(sx, y)] == "floor" and step > 1:
                break
            fade = heat * (1.0 - step / (run + 1.0))
            if fade < 0.18:
                break
            px[sx, y] = pick(RUST, clamp01(fade), sx, y)

    # --- rivets --------------------------------------------------------------
    # Two pixels each: a light one and the shadow under it. One pixel is a
    # speck; three is a bolt head the size of a fist at this scale.
    seam_rows = (int(r["back_face"]) + 1, int(r["deck_far"]) - 1, int(r["lip_top"]) + 1)
    for row in seam_rows:
        step = max(4, width // 12)
        for x in range(int(cx) % step, width, step):
            if (x, row) not in body:
                continue
            px[x, row] = pick(IRON, 0.92, x, row)
            if (x, row + 1) in body:
                px[x, row + 1] = IRON[0]

    # --- stencils ------------------------------------------------------------
    # A painted block on the back wall, half gone. It carries no information
    # and is not meant to: it is there so the biggest flat area on the prop has
    # something on it, and so the box reads as a numbered unit out of a fleet
    # rather than as a one-off somebody welded in a shed.
    stencil_y = int(r["back_face"] + (r["deck_far"] - r["back_face"]) * 0.34)
    for block in range(4):
        left = int(cx - width * 0.30 + block * width * 0.075)
        for oy in range(max(2, height // 16)):
            for ox in range(max(2, width // 32)):
                x, y = left + ox, stencil_y + oy
                if body.get((x, y)) != "back":
                    continue
                if hash01(x, y, 3301) < 0.34:
                    continue
                px[x, y] = pick(IRON, 0.66, x, y)

    _cargo(px, body, width, height)

    # --- the threshold -------------------------------------------------------
    # Hazard chevrons, worn. The wear is what keeps them from reading as a
    # decal: a clean stripe on a rusted box is a sticker applied yesterday.
    for y in range(int(r["lip_top"]), int(r["deck_near"])):
        for x in range(width):
            if body.get((x, y)) != "lip":
                continue
            band = int(x + (y - r["lip_top"]) * 2) % 10
            if band >= 5:
                continue
            wear = hash01(x, y, 2711)
            if wear < 0.34:
                continue
            px[x, y] = pick(HAZARD, clamp01(0.30 + wear * 0.72), x, y)

    _posts(px, body, width, height, live)

    # --- feet ----------------------------------------------------------------
    # Four blocks under the beams. The imprint is a picture of these, so they
    # have to be visible enough that a player recognises the dents in the
    # ground as belonging to this object.
    foot_y = int(r["base_bot"])
    for side in (-1, 1):
        for lane in (0.86, 0.34):
            fx = int(round(cx + side * _half(width, height, foot_y) * lane))
            for oy in range(0, max(2, height // 24) + 1):
                for ox in range(-1, 2):
                    if 0 <= fx + ox < width and 0 <= foot_y + oy < height:
                        px[fx + ox, foot_y + oy] = pick(
                            IRON, 0.22, fx + ox, foot_y + oy
                        )
                        body[(fx + ox, foot_y + oy)] = "base"

    # --- the light in it -----------------------------------------------------
    # A strip along the inside of the threshold. Dead sockets when it is cold:
    # an unlit fitting has to read as switched OFF rather than as a hole
    # punched in the sprite, which is the whole reason `SOCKET` exists.
    strip_y = int(r["lip_top"]) - 1
    for x in range(width):
        if body.get((x, strip_y)) not in ("floor", "lip"):
            continue
        if (x + strip_y) % 3 == 0:
            px[x, strip_y] = pick(STATUS, 0.86, x, strip_y) if live else SOCKET

    _outline(px, body, width, height)
    return img


def _cargo(px, body: dict, width: int, height: int) -> None:
    """What is still in it. SCENERY, and it never changes.

    The box is not a container the game tracks — nothing fed into the pad goes
    in here and nothing comes out. It is there to say the skid was loaded once
    and abandoned loaded, which is what makes a party believe the thing can
    carry their bag. Drawn back to front so the near crates overlap the far
    ones: that overlap is the only depth cue an interior this small gets.
    """
    r = _rows(height)
    cx = (width - 1) / 2.0
    floor_top = r["deck_far"]
    floor_bot = r["lip_top"]
    span = max(floor_bot - floor_top, 1.0)
    s = width / 80.0

    def depth(base_y: float) -> float:
        """0 at the back of the box, 1 at the threshold. Dims what is far."""
        return clamp01((base_y - floor_top) / span)

    def box(bx: float, base: float, w: float, h: float) -> None:
        lightness = 0.34 + depth(base) * 0.34
        left, right = int(bx - w / 2), int(bx + w / 2)
        top, bottom = int(base - h), int(base)
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if body.get((x, y)) not in ("floor", "back"):
                    continue
                t = (y - top) / max(h, 1.0)
                edge = x in (left, right) or y in (top, bottom)
                shade = lightness - t * 0.16 - (x - bx) / max(w, 1.0) * 0.10
                px[x, y] = TIMBER_OUTLINE if edge else pick(TIMBER, clamp01(shade), x, y)
        # One slat across the face. A blank rectangle is a block; a rectangle
        # with a board on it is a crate.
        mid = int(base - h * 0.55)
        for x in range(left + 1, right):
            if body.get((x, mid)) in ("floor", "back"):
                px[x, mid] = TIMBER_OUTLINE

    def drum(bx: float, base: float, w: float, h: float) -> None:
        """A rusted barrel. CYLINDRICAL, and the shading has to say so.

        The lid ellipse at the top and two hoop bands round the belly are what
        separate a barrel from an orange rectangle — the curve alone is not
        enough at eleven pixels wide, because the whole ramp fits in four steps
        and a smooth gradient across four steps is a flat fill.
        """
        lightness = 0.22 + depth(base) * 0.26
        half = max(w / 2.0, 1.0)
        top = base - h
        lid = h * 0.16
        for y in range(int(top - lid), int(base) + 1):
            for x in range(int(bx - half) - 1, int(bx + half) + 2):
                if body.get((x, y)) not in ("floor", "back"):
                    continue
                u = (x - bx) / half
                if abs(u) > 1.0:
                    continue
                curve = math.sqrt(max(0.0, 1.0 - u * u))
                if y < top:
                    # The lid, seen at the same slant the deck is.
                    if abs((y - top) / max(lid, 1.0)) > curve:
                        continue
                    px[x, y] = pick(RUST, clamp01(lightness + 0.34), x, y)
                    continue
                if curve < 0.20:
                    continue
                v = (y - top) / max(h, 1.0)
                hoop = 0.20 if 0.26 < v < 0.34 or 0.66 < v < 0.74 else 0.0
                rim = curve < 0.42 or y >= base - 0.5
                shade = lightness + curve * 0.42 - abs(u + 0.40) * 0.22 - hoop
                px[x, y] = TIMBER_OUTLINE if rim else pick(RUST, clamp01(shade), x, y)

    def sack(bx: float, base: float, w: float, h: float) -> None:
        for y in range(int(base - h), int(base) + 1):
            for x in range(int(bx - w / 2), int(bx + w / 2) + 1):
                if body.get((x, y)) not in ("floor", "back"):
                    continue
                u = (x - bx) / max(w / 2.0, 1.0)
                v = (y - (base - h)) / max(h, 1.0)
                if u * u + (1.0 - v) * (1.0 - v) * 0.7 > 1.0:
                    continue
                px[x, y] = pick(TIMBER, clamp01(0.18 + v * 0.22 - u * 0.10), x, y)

    # Back row first, then the near row over it. It is deliberately NOT full:
    # the gap in the middle of the deck is where the eye goes, and a box packed
    # wall to wall reads as a texture rather than as somebody's abandoned load.
    box(cx - 22 * s, floor_top + span * 0.36, 14 * s, 10 * s)
    drum(cx + 19 * s, floor_top + span * 0.34, 10 * s, 11 * s)
    sack(cx - 4 * s, floor_top + span * 0.44, 12 * s, 6 * s)
    box(cx - 13 * s, floor_bot - 2 * s, 12 * s, 9 * s)
    drum(cx + 26 * s, floor_bot - 1 * s, 9 * s, 10 * s)
    # A coil of the same rope the drones are rigged with. Spare, never used.
    coil_x, coil_y = cx + 9 * s, floor_bot - 3 * s
    for ring in range(3):
        rr = (4.0 - ring) * s
        for degrees in range(0, 360, 12):
            a = math.radians(degrees)
            x = int(round(coil_x + math.cos(a) * rr))
            y = int(round(coil_y + math.sin(a) * rr * 0.45))
            if body.get((x, y)) == "floor":
                px[x, y] = pick(ROPE, 0.4 + ring * 0.2, x, y)


def _posts(px, body: dict, width: int, height: int, live: bool) -> None:
    """Four corner posts, each with the eye a rope is tied through.

    They stand PROUD of the walls on purpose. The eyes are the only part of the
    prop the ropes touch, so they have to survive in silhouette — a lift point
    flush with the rim leaves four ropes apparently tied to nothing.
    """
    r = _rows(height)
    cx = (width - 1) / 2.0
    thickness = max(1, int(round(width / 46.0)))
    for index, (ex, ey) in enumerate(_eyes(width, height)):
        back = index in (1, 3)
        top = r["post_top"] if back else r["post_front"]
        bottom = r["deck_far"] if back else r["deck_near"]
        col = int(round(ex))
        for y in range(int(top), int(bottom) + 1):
            for ox in range(-thickness, thickness + 1):
                x = col + ox
                if not (0 <= x < width and 0 <= y < height):
                    continue
                lean = (x - cx) / max(width / 2.0, 1.0)
                shade = 0.50 - abs(ox) * 0.14 - lean * 0.10 - (y - top) / max(height, 1) * 0.12
                px[x, y] = pick(IRON, clamp01(shade), x, y)
                body[(x, y)] = "post"
        # The eye: a RING WITH A HOLE PUNCHED THROUGH IT, so it reads as
        # something a rope goes THROUGH. A filled knob is a bolt, and a rope
        # tied to a bolt looks glued on. The hole is keyed with `EDGE` rather
        # than left transparent — a gap in the sprite would let the forest
        # through a piece of solid iron.
        ring = max(2.2, width / 24.0)
        row = int(round(ey))
        for oy in range(int(-ring) - 1, int(ring) + 2):
            for ox in range(int(-ring) - 1, int(ring) + 2):
                x, y = col + ox, row + oy
                if not (0 <= x < width and 0 <= y < height):
                    continue
                d = math.hypot(ox, oy * 1.10)
                if d > ring:
                    continue
                body[(x, y)] = "post"
                if d < ring - 1.7:
                    px[x, y] = EDGE
                else:
                    px[x, y] = pick(IRON, clamp01(1.0 - oy * 0.10 - ox * 0.05), x, y)
        # The post's status lamp, just under the eye.
        lamp_y = row + int(ring) + 1
        if 0 <= lamp_y < height:
            for ox in range(-1, 1):
                x = col + ox
                if 0 <= x < width:
                    px[x, lamp_y] = pick(STATUS, 0.88, x, lamp_y) if live else SOCKET
                    body[(x, lamp_y)] = "post"


def _outline(px, body: dict, width: int, height: int) -> None:
    """Key the silhouette, and nothing inside it.

    Only the outer boundary: outlining every internal surface draws the object
    as a wireframe, and the folds are already carried by the value breaks
    between the surfaces themselves.
    """
    edges = [
        (x, y)
        for (x, y) in body
        if any(
            (x + ox, y + oy) not in body
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
    ]
    for x, y in edges:
        px[x, y] = EDGE


# --- the drones --------------------------------------------------------------


def make_drone(width: int, height: int, state: int) -> Image.Image:
    """One lift drone. PROP, bottom-anchored on its skids.

    A QUADCOPTER READ FROM ABOVE AND IN FRONT, which is the only angle that
    fits four motors and a hull into 24 pixels. Two states, and the difference
    between them is POSTURE rather than detail: dead it has settled and tipped,
    with its blades hanging; live it sits level with its lights on and no
    blades drawn at all — the blades are the `rotor` sheet's job, because a
    drone whose props are painted on is a drone that never actually spins.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    px = img.load()
    live = state == DRONE_LIVE
    cx = (width - 1) / 2.0
    # Dead, it has settled onto the ground and tipped; live, it hangs level.
    # The tip is a pixel and a half, and it is the whole read.
    tilt = 0.0 if live else 0.14
    cy = height * (0.44 if live else 0.56)
    arm = width * 0.375
    reach = height * 0.22
    pods = [
        (cx - arm, cy - reach), (cx + arm, cy - reach),
        (cx - arm, cy + reach), (cx + arm, cy + reach),
    ]
    pods = [(x, y + (x - cx) * tilt) for x, y in pods]

    body: dict[tuple[int, int], str] = {}

    def blob(bx: float, by: float, rx: float, ry: float, part: str) -> None:
        for y in range(int(by - ry) - 1, int(by + ry) + 2):
            for x in range(int(bx - rx) - 1, int(bx + rx) + 2):
                if not (0 <= x < width and 0 <= y < height):
                    continue
                if ((x - bx) / rx) ** 2 + ((y - by) / ry) ** 2 <= 1.0:
                    body[(x, y)] = part

    # Arms first, so the pods and the hull sit on top of them.
    for pod_x, pod_y in pods:
        steps = int(max(abs(pod_x - cx), abs(pod_y - cy)) * 2) + 2
        for i in range(steps + 1):
            t = i / steps
            x = int(round(cx + (pod_x - cx) * t))
            y = int(round(cy + (pod_y - cy) * t))
            for oy in range(0, 2):
                if 0 <= x < width and 0 <= y + oy < height:
                    body[(x, y + oy)] = "arm"
    for pod_x, pod_y in pods:
        blob(pod_x, pod_y, width * 0.10, height * 0.10, "pod")
    blob(cx, cy, width * 0.20, height * 0.19, "hull")
    # Skids: why it can stand on the ground at all, and the pixels that make
    # the dead pose read as parked rather than as crashed.
    skid_y = height - 2 if not live else height - 1
    for side in (-1, 1):
        for ox in range(int(width * 0.16)):
            x = int(round(cx + side * (width * 0.10 + ox)))
            if 0 <= x < width and 0 <= skid_y < height:
                body[(x, skid_y)] = "skid"

    for (x, y), part in body.items():
        u = (x - cx) / max(width / 2.0, 1.0)
        v = (y - cy) / max(height / 2.0, 1.0)
        if part == "hull":
            shade = 0.66 - u * 0.20 - v * 0.26
        elif part == "pod":
            shade = 0.52 - u * 0.14 - v * 0.18
        elif part == "arm":
            shade = 0.36 - u * 0.10
        else:
            shade = 0.20
        px[x, y] = pick(IRON, clamp01(shade + (hash01(x, y, 431) - 0.5) * 0.10), x, y)

    if live:
        # Nav lights: green forward, red aft. Two pixels each, and the only
        # thing on a 24px sprite that says which way it is facing.
        for pod_x, pod_y in pods[:2]:
            x, y = int(round(pod_x)), int(round(pod_y))
            if (x, y) in body:
                px[x, y] = pick(STATUS, 0.92, x, y)
        for pod_x, pod_y in pods[2:]:
            x, y = int(round(pod_x)), int(round(pod_y))
            if (x, y) in body:
                px[x, y] = pick(STROBE, 0.86, x, y)
        # A lit eye on the hull, so a hovering drone still reads as switched on
        # when its rotors are lost against the treeline.
        hx, hy = int(round(cx)), int(round(cy))
        if (hx, hy) in body:
            px[hx, hy] = pick(STATUS, 0.70, hx, hy)
    else:
        # Dead: the blades hang. Drawn only in this state, through the pods, so
        # a parked drone has something to have stopped.
        span = int(width * 0.13)
        for pod_x, pod_y in pods:
            for ox in range(-span, span + 1):
                x = int(round(pod_x + ox))
                y = int(round(pod_y + abs(ox) * 0.35))
                if 0 <= x < width and 0 <= y < height and (x, y) not in body:
                    px[x, y] = IRON[1]
                    body[(x, y)] = "blade"
        for pod_x, pod_y in pods:
            x, y = int(round(pod_x)), int(round(pod_y))
            if (x, y) in body:
                px[x, y] = SOCKET

    _outline(px, body, width, height)
    return img


def make_rotor_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """Four turning discs. VFX: additive, over the drone, after the darkness.

    A ROTOR IS NOT A SHAPE, IT IS A SMEAR. Drawing blades and stepping them
    round strobes horribly at any frame rate a sprite sheet can afford — so
    what is drawn is the disc the blades sweep, faint, with one bright arc
    running round it. The arc carries the speed; the disc carries the fact that
    something is there at all.

    LOOPS: every term is a function of the frame phase, so the last frame hands
    back to the first with nothing to snap.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    phase = index / total
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    arm = width * 0.32
    reach = height * 0.30
    pods = (
        (cx - arm, cy - reach), (cx + arm, cy - reach),
        (cx - arm, cy + reach), (cx + arm, cy + reach),
    )
    rx, ry = width * 0.21, height * 0.22
    for pod, (pod_x, pod_y) in enumerate(pods):
        # The faint disc.
        ellipse(field, pod_x, pod_y, rx, ry, 0.30, hollow=0.55)
        ellipse(field, pod_x, pod_y, rx * 0.55, ry * 0.55, 0.10)
        # The arc. Counter-rotating pairs, like a real quad — diagonal
        # neighbours turn the same way, so the four are never in lockstep.
        spin = 1.0 if pod in (0, 3) else -1.0
        base = (phase * spin + pod * 0.25) * math.tau
        for step in range(9):
            a = base + step * 0.16 * spin
            fade = 1.0 - step / 9.0
            x = int(round(pod_x + math.cos(a) * rx * 0.92))
            y = int(round(pod_y + math.sin(a) * ry * 0.92))
            add(field, x, y, 0.85 * fade)
            add(field, x, y + 1, 0.30 * fade)
    resolve(field, img, BEAM, floor=0.06, tone=0.80, gain=0.72)
    return img


def make_strobe_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """A live drone's nav lights, blinking. VFX, additive, over the drone.

    THE BLINK IS WHY THIS IS A SHEET AND NOT A BAKED PIXEL. Four drones on the
    same rig, each offset around this loop by the client, is what turns a row
    of switched-on props into machinery with power running through it — and a
    blink is the one signal that reads at any zoom and through the dark.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    phase = index / total
    cx = (width - 1) / 2.0
    cy = height * 0.44
    arm = width * 0.375
    reach = height * 0.22
    # A sharp pulse, not a sine: a marker light snaps on and decays.
    pulse = ease_out(clamp01(1.0 - (phase % 0.5) * 3.4))
    lead = 1.0 if phase < 0.5 else 0.35
    corners = (
        (cx - arm, cy - reach), (cx + arm, cy - reach),
        (cx - arm, cy + reach), (cx + arm, cy + reach),
    )
    for i, (sx, sy) in enumerate(corners):
        gain = pulse * (lead if i < 2 else 1.35 - lead)
        if gain <= 0.02:
            continue
        ellipse(field, sx, sy, width * 0.13, height * 0.13, 0.75 * gain)
        add(field, int(round(sx)), int(round(sy)), 0.55 * gain)
    resolve(field, img, BEAM, floor=0.06, tone=0.85, gain=0.62)
    return img


# --- the ground --------------------------------------------------------------


class GroundDecal:
    """A ground mark split into what it DARKENS and what it ADDS.

    Same two-blend contract `make_rift.py` documents, for the same reason:
    drawn `source-over` a decal's dark pixels REPLACE the soil, the terrain's
    grain dies under the mark, and the field reads as a sticker laid on dirt
    instead of as something that happened to the ground.
    """

    def __init__(self, width: int, height: int) -> None:
        self.dark = Image.new("RGBA", (width, height), TRANSPARENT)
        self.lit = Image.new("RGBA", (width, height), TRANSPARENT)
        self._dark = self.dark.load()
        self._lit = self.lit.load()
        self.width = width
        self.height = height

    def put(self, x: int, y: int, colour: RGBA, alpha: float, luminous: bool = False) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        px = self._lit if luminous else self._dark
        prior = px[x, y][3]
        px[x, y] = (colour[0], colour[1], colour[2], max(prior, int(clamp01(alpha) * 255)))


def make_imprint(width: int, height: int, rng: random.Random) -> GroundDecal:
    """What is left when the skid goes. DECAL — flat, no outline, no face.

    THE POINT OF THIS SPRITE IS THAT THE PLAYER WATCHES IT ARRIVE. It is
    uncovered on the frame the platform breaks ground, so it is not scenery the
    map came with — it is the answer to "what was under there", and it has to
    land as an answer at that moment: a pressed rectangle of dead soil, four
    deep dents where the feet stood, oil where the gear sat, and the grit that
    came out from underneath.

    The rectangle is deliberately RAGGED. A crisp edge would say the object was
    lifted off clean ground; a frayed one says it has been settling into this
    spot for years and the forest has been creeping back at it.
    """
    decal = GroundDecal(width, height)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    half_w = width * 0.46
    half_h = height * 0.42

    for y in range(height):
        for x in range(width):
            u = abs(x - cx) / half_w
            v = abs(y - cy) / half_h
            # A soft RECTANGLE rather than an ellipse: the thing that stood
            # here had corners, and rounding them off loses the one clue that
            # says a machine was parked here rather than that something burned.
            edge = max(u, v) + (hash01(x, y, 1091) - 0.5) * 0.16
            if edge > 1.0:
                continue
            depth = clamp01((1.0 - edge) * 1.5)
            grain = hash01(x, y, 5501)
            step = clamp01(0.30 + depth * 0.40 + (grain - 0.5) * 0.34)
            decal.put(x, y, pick(PRESSED, step, x, y), 0.34 + depth * 0.32)

    # Drag scars: it did not land here gently, and it has shifted since.
    for _ in range(int(width * 0.5)):
        sx = int(cx + (rng.random() - 0.5) * half_w * 1.7)
        sy = int(cy + (rng.random() - 0.5) * half_h * 1.7)
        run = rng.randint(3, max(4, width // 8))
        for step in range(run):
            decal.put(sx + step, sy, PRESSED[0], 0.30 + 0.30 * (1.0 - step / run))

    # The four dents. DEEPEST THING IN THE FRAME, with a lip of thrown soil on
    # the low side — a flat dark ellipse is a puddle, and a puddle says nothing
    # about weight.
    # Eight, because the skid rides on a beam front and back rather than on
    # four posts — and they are NUDGED off the grid they would otherwise form.
    # A perfect lattice of identical dents is the one thing that would give
    # away that this was stamped rather than settled into.
    for side in (-1, 1):
        for lane in (0.80, 0.30):
            for row in (-1, 1):
                nudge = hash01(int(side * 7), int(lane * 100), int(row * 13))
                fx = cx + side * half_w * (lane + (nudge - 0.5) * 0.08)
                fy = cy + row * half_h * (0.62 + (nudge - 0.5) * 0.10)
                rx = width * (0.048 + nudge * 0.016)
                ry = height * (0.066 + nudge * 0.020)
                for y in range(int(fy - ry * 2), int(fy + ry * 2) + 1):
                    for x in range(int(fx - rx * 2), int(fx + rx * 2) + 1):
                        d = math.hypot((x - fx) / rx, (y - fy) / ry)
                        if d <= 1.0:
                            decal.put(x, y, OIL, 0.40 + (1.0 - d) * 0.38)
                        elif d <= 1.5 and y > fy:
                            decal.put(x, y, pick(GRIT, 0.7, x, y), 0.30, luminous=True)

    # Oil pooled where the lift gear sat, and bolts that shook loose. The bolts
    # are the LIT half: two bright pixels are what a lantern finds when a
    # player walks back across this later in the night.
    for _ in range(int(width * 0.35)):
        x = int(cx + (rng.random() - 0.5) * half_w * 1.2)
        y = int(cy + (rng.random() - 0.5) * half_h * 1.2)
        decal.put(x, y, OIL, 0.5 + rng.random() * 0.4)
    for _ in range(int(width * 0.22)):
        x = int(cx + (rng.random() - 0.5) * half_w * 1.9)
        y = int(cy + (rng.random() - 0.5) * half_h * 1.9)
        decal.put(x, y, pick(GRIT, rng.random(), x, y), 0.55, luminous=True)
    return decal


def make_downwash_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """Rotor wash under a platform that is straining. VFX, additive, LOOPING.

    Four rotors at full power over dry soil push a ring of dust outward, it
    thins, and the next one is already leaving. Three rings a third of a cycle
    apart is what makes that continuous — one ring reads as a pulse, and a
    pulse under a machine holding station reads as the machine misfiring.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    reach = width * 0.48
    for ring in range(3):
        phase = ((index / total) + ring / 3.0) % 1.0
        radius = ease_out(phase) * reach
        # Brightest in the middle of its travel: dust needs a moment to be
        # lifted and has thinned to nothing by the time it reaches the rim.
        strength = math.sin(math.pi * phase) * 0.62
        if radius < 2.0 or strength <= 0.01:
            continue
        ellipse(field, cx, cy, radius, radius * 0.42, strength, hollow=0.42)
    # The churn directly under the deck never clears.
    ellipse(field, cx, cy, width * 0.20, height * 0.20,
            0.30 + 0.08 * math.sin(index / total * math.tau))
    # Grit whipping round, on its own turn, so the ring is never a clean circle.
    for i in range(14):
        a = (i / 14.0 + index / total * 0.5) * math.tau
        rad = reach * (0.35 + 0.55 * ((i * 7 % 11) / 11.0))
        add(field, int(round(cx + math.cos(a) * rad)),
            int(round(cy + math.sin(a) * rad * 0.42)), 0.45)
    resolve(field, img, BEAM, floor=0.07, tone=0.62, gain=0.50)
    return img


def make_burst_frame(width: int, height: int, index: int, total: int) -> Image.Image:
    """The ground letting go. VFX one-shot, on the frame the skid breaks free.

    A TONNE OF IRON COMING UNSTUCK IS ONE EVENT, not a fade-up: everything
    under it that had been pressed flat for years is thrown out at once, and
    after that there is only settling dust. So the field is nearly all in the
    first third and the tail is empty — frame 0 and the last frame are both
    near nothing, the rule every one-shot in this game follows, so there is no
    pop at either end.
    """
    img = Image.new("RGBA", (width, height), TRANSPARENT)
    field = [[0.0] * width for _ in range(height)]
    t = index / max(total - 1, 1)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    reach = width * 0.50

    front = ease_out(clamp01(t * 1.35))
    strength = (1.0 - ease_in(clamp01(t * 1.05))) * 1.15
    # Frame 0 opens on nothing and grows into the blast within one frame.
    strength *= min(1.0, t * total * 0.9)
    if strength > 0.01:
        ellipse(field, cx, cy, max(2.0, front * reach), max(1.2, front * reach * 0.40),
                strength * 0.72, hollow=0.34)
        ellipse(field, cx, cy, max(2.0, front * reach * 0.62),
                max(1.2, front * reach * 0.26), strength * 0.40)
    # Debris thrown along fixed bearings, so the burst has direction in it
    # rather than being a symmetric puff. It slows as it goes, like thrown dirt.
    for i in range(20):
        a = (i / 20.0) * math.tau + 0.31
        speed = 0.55 + ((i * 13 % 17) / 17.0) * 0.75
        rad = ease_out(clamp01(t * speed * 1.6)) * reach * 1.06
        fade = (1.0 - ease_in(t)) * 0.95 * min(1.0, t * total * 0.9)
        if fade <= 0.02:
            continue
        x = int(round(cx + math.cos(a) * rad))
        y = int(round(cy + math.sin(a) * rad * 0.42 - ease_out(t) * height * 0.14))
        add(field, x, y, fade)
        add(field, x, y + 1, fade * 0.45)
    resolve(field, img, BEAM, floor=0.07, tone=0.70, gain=0.62)
    return img


# --- build -------------------------------------------------------------------


def _layout(plot: int, width: int, height: int) -> dict:
    """Where every piece stands, in TILE offsets from the plot's top-left.

    Same coordinate language as `scenery.Piece` and as `make_rift.py`'s own
    layout: a standing piece's `dy` is the BOTTOM EDGE of the row it stands on
    (its contact point), a decal's `dy` is its centre. `server/app/rift.py`
    mirrors this exactly — if one moves the other has to.

    `eyes` and `rope` are the exceptions and are in PIXELS, because they are
    details of the ART: where on the sprite a rope is tied and how much of it
    was rigged are not tile quantities, and the client is the only side that
    needs them.
    """
    middle = plot / 2.0
    deck = 5.0                 # contact row of the skid
    front = plot - 1.0         # the approach: console and torch
    eyes = _eyes(width, height)
    return {
        # The skid. 5 tiles wide, contact two rows up from the plot's edge so
        # there is standing room in front of it for the console.
        "platform": {"dx": middle, "dy": deck},
        # THE PLAYER MAY NOT GET ON IT — the two rows the box actually sits on
        # are made solid. See `_stamp` in server/app/rift.py.
        "footprint": {"x": 1, "y": 3, "w": PLATFORM_TILES_W, "h": 2},
        # The four drones, parked outside the skid's own columns so a body can
        # still walk down either side of the pad. Diagonal order.
        "drones": [
            {"dx": 0.5, "dy": deck, "corner": 0},
            {"dx": plot - 0.5, "dy": deck - 2.0, "corner": 1},
            {"dx": plot - 0.5, "dy": deck, "corner": 2},
            {"dx": 0.5, "dy": deck - 2.0, "corner": 3},
        ],
        # Lift eyes, in pixels from the platform's contact point. Same order.
        "eyes": [
            {"dx": round(ex - (width - 1) / 2.0, 1), "dy": round(ey - height, 1)}
            for ex, ey in eyes
        ],
        # How much rope each drone was rigged with, in pixels. It is what sets
        # the hover height: a live drone climbs until its line is straight and
        # holds there, so this number alone decides how high over the pad the
        # rig ends up sitting.
        "rope": {"length": round(height * 1.05, 1)},
        # Flat, centred on the skid's own footprint — this is a picture of what
        # stood there, so it is the same rectangle.
        "imprint": {"dx": middle, "dy": deck - 1.0},
        # The approach. The same console `make_rift.py` draws, and one of the
        # same torches the exit corridor is dressed with.
        "console": {"dx": middle, "dy": front},
        "torch": {"dx": 1.0, "dy": front},
        # The light the pad puts on the map. `kind` 2 is BEACON in
        # `server/app/scenery.py` — the value is the contract.
        "light": {"dx": middle, "dy": deck - 1.0, "radiusTiles": 4.0, "kind": 2},
    }


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "platform"
    out_dir.mkdir(parents=True, exist_ok=True)

    plat_w, plat_h = tile * PLATFORM_TILES_W, tile * PLATFORM_TILES_H
    platforms = [
        make_platform(plat_w, plat_h, state, random.Random(args.seed + 17))
        for state in range(PLATFORM_STATES)
    ]
    pack(platforms, plat_w, plat_h).save(out_dir / "platform.png")

    drone_w, drone_h = round(tile * 1.5), tile
    drones = [make_drone(drone_w, drone_h, state) for state in range(DRONE_STATES)]
    pack(drones, drone_w, drone_h).save(out_dir / "drone.png")

    # Wider than the drone: the discs overhang its arms, which is what makes it
    # read as a machine with props on rather than as a lit toy. Anchored on the
    # ROTOR PLANE, not on the skids — `rotorY` in the manifest is how far above
    # a drone's contact point that plane sits.
    rotor_w, rotor_h = round(tile * 1.75), round(tile * 0.75)
    rotors = [make_rotor_frame(rotor_w, rotor_h, i, ROTOR_FRAMES) for i in range(ROTOR_FRAMES)]
    pack(rotors, rotor_w, rotor_h).save(out_dir / "rotor.png")

    strobes = [
        make_strobe_frame(drone_w, drone_h, i, STROBE_FRAMES) for i in range(STROBE_FRAMES)
    ]
    pack(strobes, drone_w, drone_h).save(out_dir / "strobe.png")

    imp_w, imp_h = tile * PLATFORM_TILES_W, tile * 3
    imprint = make_imprint(imp_w, imp_h, random.Random(args.seed + 29))
    pack([imprint.dark], imp_w, imp_h).save(out_dir / "imprint.png")
    pack([imprint.lit], imp_w, imp_h).save(out_dir / "imprint-lit.png")

    wash_w, wash_h = tile * 7, round(tile * 3.5)
    washes = [
        make_downwash_frame(wash_w, wash_h, i, DOWNWASH_FRAMES) for i in range(DOWNWASH_FRAMES)
    ]
    pack(washes, wash_w, wash_h).save(out_dir / "downwash.png")

    burst_w, burst_h = tile * 8, tile * 4
    bursts = [make_burst_frame(burst_w, burst_h, i, BURST_FRAMES) for i in range(BURST_FRAMES)]
    pack(bursts, burst_w, burst_h).save(out_dir / "burst.png")

    head_alpha = bursts[0].getchannel("A").getextrema()[1]
    tail_alpha = bursts[-1].getchannel("A").getextrema()[1]

    manifest = {
        "tile": tile,
        "seed": args.seed,
        "plot": {"widthTiles": 7, "heightTiles": 7},
        "props": {
            "platform": {
                "file": "platform.png",
                "frameWidth": plat_w,
                "frameHeight": plat_h,
                "frames": PLATFORM_STATES,
                "shapes": 1,
                "states": PLATFORM_STATES,
            },
            "drone": {
                "file": "drone.png",
                "frameWidth": drone_w,
                "frameHeight": drone_h,
                "frames": DRONE_STATES,
                "shapes": 1,
                "states": DRONE_STATES,
                # Where the rotor plane sits above a drone's contact point.
                "rotorY": round(drone_h * 0.56, 1),
            },
        },
        "decals": {
            "imprint": {
                "file": "imprint.png",
                "litFile": "imprint-lit.png",
                "frameWidth": imp_w,
                "frameHeight": imp_h,
                "frames": 1,
            },
        },
        "effects": {
            "rotor": {
                "file": "rotor.png",
                "frameWidth": rotor_w,
                "frameHeight": rotor_h,
                "frames": ROTOR_FRAMES,
                "fps": ROTOR_FPS,
                "anchorY": rotor_h / 2.0,
                "loop": True,
                "tinted": False,
            },
            "strobe": {
                "file": "strobe.png",
                "frameWidth": drone_w,
                "frameHeight": drone_h,
                "frames": STROBE_FRAMES,
                "fps": STROBE_FPS,
                "anchorY": drone_h,
                "loop": True,
                "tinted": False,
            },
            "downwash": {
                "file": "downwash.png",
                "frameWidth": wash_w,
                "frameHeight": wash_h,
                "frames": DOWNWASH_FRAMES,
                "fps": DOWNWASH_FPS,
                "anchorY": wash_h / 2.0,
                "loop": True,
                "tinted": False,
            },
            "burst": {
                "file": "burst.png",
                "frameWidth": burst_w,
                "frameHeight": burst_h,
                "frames": BURST_FRAMES,
                "fps": BURST_FPS,
                "anchorY": burst_h / 2.0,
                "loop": False,
                "tinted": False,
            },
        },
        "layout": _layout(7, plat_w, plat_h),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: "
        f"platform {PLATFORM_STATES}x{plat_w}x{plat_h}, "
        f"drone {DRONE_STATES}x{drone_w}x{drone_h}, "
        f"rotor {ROTOR_FRAMES}x{rotor_w}x{rotor_h} @{ROTOR_FPS}fps loop, "
        f"strobe {STROBE_FRAMES}x{drone_w}x{drone_h} @{STROBE_FPS}fps loop, "
        f"imprint 1x{imp_w}x{imp_h}, "
        f"downwash {DOWNWASH_FRAMES}x{wash_w}x{wash_h} @{DOWNWASH_FPS}fps loop, "
        f"burst {BURST_FRAMES}x{burst_w}x{burst_h} @{BURST_FPS}fps, "
        f"burst edges {head_alpha}/{tail_alpha}"
    )
    if head_alpha > 8 or tail_alpha > 8:
        raise SystemExit(
            f"burst does not open and close on nothing (first {head_alpha}, "
            f"last {tail_alpha}): a one-shot whose ends carry alpha pops when "
            f"the client starts it and leaves dust hanging over a bare imprint"
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
