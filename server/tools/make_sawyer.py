#!/usr/bin/env python3
"""Asset pipeline: THE SAWYER — the first boss. What is left of the logging crew.

Output (assets/processed/sawyer/):
    idle-<facing>.png      8f  @8   LOOP      breathing, the engine idling under him
    walk-<facing>.png      8f  @10  LOOP      the stomp. He does not walk, he arrives
    chop-<facing>.png     16f  @14  one-shot  overhead, into the floor, then WRENCHED free
    rip-<facing>.png      14f  @14  one-shot  the throw. A crescent of chain leaves the bar
    rev-<facing>.png      14f  @14  one-shot  the cord, the catch, the roar
    death-<facing>.png    21f  @10  one-shot  knees, then forward. Last frame is the rest
    sweep.png             36f  @16  one-shot  the ataque giratorio. NO FACING — see below
    arrive-down.png       30f  @14  one-shot  THE CINEMATIC. He lands on you
    slash.png       8 headings x 5f @14  LOOP  the thrown crescent
    slash-burst.png        6f  @18  one-shot  what it does when it lands
    manifest.json

    <facing> is down / left / right / up. 128x120 per frame, anchored on his
    GROUND CONTACT rather than on the bottom edge.

WHY HE IS A LOGGER.
The forest this game is set in is full of felled trunks, stumps and a
`deadtree` sheet with six blighted species on it. Somebody was cutting it
down. The three creatures are what happened to the people who lived here; the
Sawyer is what happened to the man who ran the crew, and his hard hat is the
same hard hat `make_zombie.py`'s `zhat-hardhat` puts on a walker — filthier,
split, and grown into the skull under it. A boss invented from nothing is a
boss from another game; this one is an existing prop, an existing hat and an
existing rot, at four times the size.

HE IS A RIG, AND THAT IS THE ONE REAL DEPARTURE FROM THE OTHER BODIES.
Every other character in this pipeline is authored as ASCII rows — the player,
the three creatures, the merchant — and that is right at 16x16 and survives at
22x28. It does not survive here. This sheet is 390 frames on a 128x120 grid,
and 390 hand-authored frames at that size do not agree with each other about
where a shoulder is: the arm drifts, the mass changes width mid-swing, and the
volume the whole v2 direction is about stops being one solid. So the Sawyer is
a SKELETON with poses on it:

    joints            hips, shoulders, an elbow solved by IK, the saw's pivot
    masses            capsules and ellipses stacked in draw order (S2)
    the shader        one law applied to every mass, below
    the face          the one thing still PLACED BY HAND, shape by shape,
                      because a face is a decision and no shader makes one
                      (`make_merchant.py` says the same about his)

A pose is hand targets and foot targets. Everything between them is solved, so
the same shoulder is in the same place in frame 3 of the walk and frame 11 of
the chop, and every clip is built out of the same body.

THE SHADER: A DISTANCE FIELD IS A NORMAL, AND A NORMAL IS A PLANE.
S7 wants hard cel bands whose terminator follows the form's curvature, and S8
wants one key at 135deg/60deg for the whole world. On a mass whose outline is
generated rather than drawn, both fall out of the mass's own distance field:

    d, e      = distance to this mass's own edge, and the direction in from it
    theta     = how far the surface has turned to face the camera (rises with d)
    N         = the outward 2D normal, tipped up by theta into the WORLD
    step      = quantise(N . L)

The reason the 2D normal is lifted into world space rather than lit flat: at
this camera an up-screen edge is the TOP of the form and a left-screen edge is
its west FLANK, and those are two different angles to a light 60deg up. Lit
flat, the top of a shoulder and the side of a shoulder come out the same value
and the whole body reads as a sticker. `make_loot.paint_form`'s edge test is
the same idea one size down — this is that test with the camera put back in.

Step 4 is not a band. It is `d <= 2 and i >= SPEC`: a crest, never a face, or
a 40px torso comes out with a specular the size of a hand (S7: step 4 is the
smallest area on the sprite).

THE SAW IS THE OTHER HALF OF THE CHARACTER AND IT IS DRAWN EVERY FRAME.
It is not a sprite stamped at an angle — nothing in this game is rotated at
draw time (S1) and a rotated 30px bar is mush. It is plotted from its pose:
a pivot, an angle, and a length, with the bar swept along the axis, the chain
laid round its rim by ARCLENGTH and the teeth spaced 1 : 0.7 : 0.5 (S17) so
the row of them is not a comb. The chain's phase is a pose field, which is
the single thing that makes the weapon read as RUNNING rather than as held.

WHAT MAKES IT HORRIFYING is not the blade. Three things, and none of them is:

    THE GRAFT     it is not held. The bar is bolted through the wrist, and the
                  arm ends where the housing begins. There is no hand.
    THE TEETH     some of the cutters are TEETH — molars and canines, in the
                  same BONE the husk is made of, wired into the chain. The
                  chain is a mouth he had to build.
    THE MEAT      the chain carries what it last went through. `BLOOD` is the
                  world's one blood (`make_textures`), the same stain the floor
                  wears, so it is not a boss-red invented for a boss.

ONE ACCENT, AND THE ENGINE SHARES IT WITH HIS EYES (S12). The exhaust ember,
the spark off the chain and the two lights under the hat brim are all `EYE`,
because the player has been trained for a whole night to track that hue in the
dark. A second accent on the biggest thing in the game is the sheet arguing
with itself about where to look.

FACINGS. `down`, `side` and `up` are authored; `left` is `right` mirrored, and
mirroring puts the graft on the other arm. That is deliberate and it is the
same trade `process_sprites.py` makes for every creature: a 30px bar hidden
behind a 40px torso is a boss whose weapon disappears every time he turns, and
which arm a dead man's chainsaw is welded to is not information anybody is
tracking. The player's HOLD pose is the exception that proves it — that one is
mirrored per block precisely because a living right-handed man is readable.

EVENT FRAMES ARE ON THE MANIFEST. `hit`, `impact` and `release` are indices
into a clip, and they are the art telling the mechanics when the blow lands
rather than the mechanics guessing. Same contract as a VFX sheet's
`frames / fps` being the effect's duration.

Usage:
    python tools/make_sawyer.py
    python tools/make_sawyer.py --preview ../.preview/sawyer.png
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image

from make_textures import (
    BLOOD,
    PROCESSED_DIR,
    RGBA,
    TRANSPARENT,
    Ramp,
    clamp01,
    hash01,
    material_ramp,
    pack,
)
from make_zombie import BONE, EYE, FUNGUS, GORE, HIDE, ROT

# --- the frame ----------------------------------------------------------------
# THE FRAME IS SIZED BY THE SWING ENVELOPE, NOT BY THE BODY.
#
# 120x112 on a 16px tile: seven and a half tiles across, seven down. He is
# nowhere near that — he stands 55 rows, three and a half tiles, against a
# 24x40 tree and a 16px walker, on a 26px footprint. The rest of it is the arc
# the weapon sweeps, and the number that sets it is not his height:
#
#     shoulder off centre               16
#     shoulder to wrist                 23
#     wrist to the nose of the bar      41   (10 of housing, 31 of bar)
#     ---------------------------------------
#     worst case from the centre        80
#
# 128x120 is seven-eighths of that, and the missing eighth is on purpose: the
# only poses that need all eighty are the ones with the arm at full stretch
# AND the bar pointing the same way, which is a pose nobody swings a running
# chainsaw in. `_fit` tucks the arm on those (see below) rather than the sheet
# carrying thirty-two empty columns on three hundred frames.
#
# The first two cuts were 96x88 and 112x104, both sized by eye against a
# standing pose, and both silently clipped the frames that mattered — the top
# eighteen rows off every raised-bar windup in `chop`, and the last four pixels
# off the resting bar in every idle frame on the sheet. A bar with its nose
# missing still reads as a bar on a contact sheet and reads as a broken sprite
# in a game, which is why `_off_frame` is a check that FAILS the build rather
# than a note in this comment.
#
# The anchor is the GROUND CONTACT, not the frame's bottom edge. Twelve rows
# are left under his feet for the dust to spread into and for a buried bar to
# go below them, and `arrive` throws him clean out of the top of the frame
# with the anchor never moving — which is what lets the client keep him on one
# world position through a jump it does not simulate.
W, H = 128, 120
CX = 64
GROUND = 104

#: S8, in world axes, with Z up and Y running back into the screen. Not a
#: screen-space vector: the whole point of the shader is that an up-screen
#: surface and a left-screen surface are two different angles to this.
LIGHT = (-0.62, 0.28, 0.73)
#: The camera. S1 says 55-60 degrees above the horizon; the shader needs the
#: number because "facing the camera" is a normal like any other.
PITCH = math.radians(57.0)

#: Where the quantiser cuts. Chosen so the CORE of a mass lands on step 2 —
#: S7 gives step 2 the most pixels, and a core that lands on 3 puts the base
#: tone on a rim and the whole body a step too bright.
BANDS = (-0.55, 0.00, 0.58)
#: Step 4 is a crest, not a band: this far in from the edge and no further.
SPEC_DEPTH = 2.2
SPEC_LIGHT = 0.70
#: How deep a mass's shell goes before its surface has finished turning to
#: face the camera. Without the clamp a 24px-wide belly bands across twelve
#: pixels and reads as an airbrush; with it, every mass on the body carries a
#: rim of the same thickness and the flat middles are what differ.
SHELL = 5.5


# --- palette ------------------------------------------------------------------
# HE IS MADE OF THE OTHER CREATURES. `HIDE` is the brute's, and it is his mass
# for the reason the brute has it: mass reads dark. `ROT` is the walker's and
# it is what shows where the hide has split. `BONE` is the husk's. `FUNGUS` is
# the growth off the brute's shoulders, and it is on him because whatever is
# doing that to them has had longer with him. Four creatures' worth of
# material and not one new flesh ramp — a boss painted in colours nothing else
# in the game is painted in is a boss standing in front of the game.

#: HIS OWN MEAT: the brute's hue at a boss's VALUE. S13 gives the focal mass
#: the full ramp and S17 says mass reads dark, and `HIDE` — tuned for a 16px
#: creature that has to survive being one of six things in a dark clearing —
#: comes out a bright green when it is forty pixels across and the only thing
#: on screen. Same hue, a step colder and the ceiling dropped: the TRUNK is
#: this, the limbs stay `HIDE`, and the two-step gap between them is what
#: stops an arm in front of a chest from merging into it (S7).
MEAT = material_ramp(94, 0.24, 0.09, 0.40)
#: Bare steel: the bar, the chain, the bolts through the wrist. High-contrast
#: top step (S14, bare metal) — it is the only thing on him that is supposed
#: to catch the light.
STEEL = material_ramp(212, 0.08, 0.20, 0.82)
#: The housing, and everything that has been outdoors for a year. Rust is the
#: only large warm mass on him and it is deliberately kept under the hat's
#: value so the hat stays the read.
RUST = material_ramp(20, 0.44, 0.14, 0.50)
#: The hard hat: `zhat-hardhat`'s yellow, filthy. Same hue, saturation pulled
#: down and the ceiling dropped — a clean hi-vis yellow on a boss reads as a
#: safety cone, and this one has been under a canopy since the crew died. It
#: is also held BELOW the growths' value on purpose: the hat and the fungus
#: are eleven degrees apart in hue and if they are the same brightness as
#: well, the top of his silhouette becomes one yellow shape.
HAT = material_ramp(45, 0.30, 0.12, 0.50)
#: Logging leathers: the harness, the boots, the belt.
LEATHER = material_ramp(26, 0.30, 0.10, 0.38)
#: What is left of the trousers. `RAG`'s cousin, kept cool and DARK so his
#: legs read as the base of a mass rather than as a second pale shape under
#: the body (S13: background sub-masses lose the top and bottom steps).
CANVAS = material_ramp(206, 0.14, 0.08, 0.33)
#: The chain's own dark. Not black (S7) — a violet-blue near-dark, so the
#: gore in it and the steel round it both separate from it.
VOID = material_ramp(232, 0.18, 0.05, 0.19)
#: Exhaust. Emissive (S14): it ignores the key and it is the accent's hue.
EMBER = EYE

RAMPS: dict[str, Ramp] = {
    "meat": MEAT, "hide": HIDE, "rot": ROT, "bone": BONE, "gore": GORE, "blood": BLOOD,
    "fungus": FUNGUS, "steel": STEEL, "rust": RUST, "hat": HAT,
    "leather": LEATHER, "canvas": CANVAS, "void": VOID, "eye": EYE,
    "ember": EMBER,
}


# --- geometry -----------------------------------------------------------------
# Every mass on the body is one of four shapes. They return PIXEL SETS rather
# than drawing, because a mass has to be shaded as a whole — including the part
# of it another mass is standing in front of — or a limb that goes behind the
# torso gets its rim relit against the torso's edge and detaches.

Pixels = set[tuple[int, int]]


def disc(cx: float, cy: float, rx: float, ry: float) -> Pixels:
    """A filled ellipse. The workhorse: every lump on him is one of these."""
    out: Pixels = set()
    if rx <= 0 or ry <= 0:
        return out
    for y in range(int(cy - ry - 1), int(cy + ry + 2)):
        for x in range(int(cx - rx - 1), int(cx + rx + 2)):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            if dx * dx + dy * dy <= 1.0:
                out.add((x, y))
    return out


def capsule(x0: float, y0: float, x1: float, y1: float,
            r0: float, r1: float | None = None) -> Pixels:
    """A tapered limb: the swept disc of a segment, thick end to thin end.

    Tapered rather than uniform because S17's `1 : 0.7 : 0.5` rhythm applies
    down a limb as much as across a sheet — a forearm the same width as the
    upper arm is a pipe, and four pipes is a mannequin.
    """
    if r1 is None:
        r1 = r0
    out: Pixels = set()
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    rmax = max(r0, r1)
    lo_x, hi_x = int(min(x0, x1) - rmax - 1), int(max(x0, x1) + rmax + 2)
    lo_y, hi_y = int(min(y0, y1) - rmax - 1), int(max(y0, y1) + rmax + 2)
    for y in range(lo_y, hi_y):
        for x in range(lo_x, hi_x):
            if length < 1e-6:
                t = 0.0
            else:
                t = ((x - x0) * dx + (y - y0) * dy) / (length * length)
                t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
            px, py = x0 + dx * t, y0 + dy * t
            if math.hypot(x - px, y - py) <= r0 + (r1 - r0) * t:
                out.add((x, y))
    return out


def poly(points: list[tuple[float, float]]) -> Pixels:
    """Even-odd scanline fill. Plates, the hat brim, the bar's own quad."""
    out: Pixels = set()
    if len(points) < 3:
        return out
    ys = [p[1] for p in points]
    for y in range(int(min(ys)) - 1, int(max(ys)) + 2):
        sy = y + 0.5
        crossings: list[float] = []
        for i in range(len(points)):
            (ax, ay), (bx, by) = points[i], points[(i + 1) % len(points)]
            if (ay <= sy < by) or (by <= sy < ay):
                crossings.append(ax + (sy - ay) / (by - ay) * (bx - ax))
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            for x in range(int(math.ceil(crossings[i] - 0.5)),
                           int(math.floor(crossings[i + 1] - 0.5)) + 1):
                out.add((x, y))
    return out


def band(pixels: Pixels, ox: float, oy: float, ax: float, ay: float,
         lo: float, hi: float) -> Pixels:
    """The sub-set of a mass lying between two offsets along an axis.

    This is how a flat plane gets onto a round mass: the specular streak down
    a bar, the wet band across a belly, the lit crown of a shoulder. S14 says
    grain runs along its own plane's axis, and this is the axis.
    """
    out: Pixels = set()
    for (x, y) in pixels:
        t = (x - ox) * ax + (y - oy) * ay
        if lo <= t <= hi:
            out.add((x, y))
    return out


def edt(pixels: Pixels) -> dict[tuple[int, int], tuple[float, float, float]]:
    """Per-pixel (distance to this mass's edge, and the unit vector in from it).

    Two-pass 8SSEDT over the mass's own bounding box. The vector matters more
    than the distance: it IS the surface normal in screen space, and getting it
    from a chebyshev flood instead would quantise every rim on the body to
    eight directions and put visible facets on a round shoulder.
    """
    if not pixels:
        return {}
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    x0, x1 = min(xs) - 1, max(xs) + 1
    y0, y1 = min(ys) - 1, max(ys) + 1
    wide, tall = x1 - x0 + 1, y1 - y0 + 1
    big = 1e9
    grid = [[(big, 0.0, 0.0) for _ in range(wide)] for _ in range(tall)]
    for (x, y) in pixels:
        grid[y - y0][x - x0] = (big, 0.0, 0.0)
    for gy in range(tall):
        for gx in range(wide):
            if (gx + x0, gy + y0) not in pixels:
                grid[gy][gx] = (0.0, 0.0, 0.0)

    def relax(gx: int, gy: int, dx: int, dy: int) -> None:
        nx, ny = gx + dx, gy + dy
        if not (0 <= nx < wide and 0 <= ny < tall):
            return
        d, vx, vy = grid[ny][nx]
        if d >= big:
            return
        cx, cy = vx - dx, vy - dy
        cand = math.hypot(cx, cy)
        if cand < grid[gy][gx][0]:
            grid[gy][gx] = (cand, cx, cy)

    for gy in range(tall):
        for gx in range(wide):
            for dx, dy in ((-1, 0), (0, -1), (-1, -1), (1, -1)):
                relax(gx, gy, dx, dy)
        for gx in range(wide - 1, -1, -1):
            relax(gx, gy, 1, 0)
    for gy in range(tall - 1, -1, -1):
        for gx in range(wide - 1, -1, -1):
            for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
                relax(gx, gy, dx, dy)
        for gx in range(wide):
            relax(gx, gy, -1, 0)

    out: dict[tuple[int, int], tuple[float, float, float]] = {}
    for (x, y) in pixels:
        d, vx, vy = grid[y - y0][x - x0]
        length = math.hypot(vx, vy)
        if length < 1e-6:
            out[(x, y)] = (d, 0.0, -1.0)
        else:
            out[(x, y)] = (d, vx / length, vy / length)
    return out


# --- the shader ---------------------------------------------------------------


def _world_normal(ex: float, ey: float, theta: float) -> tuple[float, float, float]:
    """A screen-space rim direction, tipped up into the world by the camera.

    `(ex, ey)` points IN from the nearest edge, so the outward normal is its
    negation. At `theta = 0` the surface is edge-on: an up-screen edge is the
    top of the form (world +Z) and a left-screen edge is its west flank
    (world -X). At `theta = pi/2` the surface faces the camera, which at S1's
    pitch is south and up.
    """
    ox, oy = -ex, -ey
    flank = math.cos(theta)
    face = math.sin(theta)
    nx = ox * flank
    nz = (-oy) * flank * math.sin(PITCH) + face * math.sin(PITCH)
    ny = (-oy) * flank * -math.cos(PITCH) + face * -math.cos(PITCH)
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


def _step_of(d: float, ex: float, ey: float, shell: float) -> int:
    theta = (math.pi / 2.0) * clamp01(d / shell) ** 0.75
    nx, ny, nz = _world_normal(ex, ey, theta)
    i = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
    if d <= SPEC_DEPTH and i >= SPEC_LIGHT:
        return 4
    if i >= BANDS[2]:
        return 3
    if i >= BANDS[1]:
        return 2
    if i >= BANDS[0]:
        return 1
    return 0


@dataclass
class Mass:
    """One convex lump with its own ramp. S2: form is a stack of these."""
    pixels: Pixels
    ramp: Ramp
    tone: int = 0
    shell: float = SHELL
    #: Per-mass shading override — the flat authored patches (a face, a decal
    #: on a housing) that must not be re-lit.
    forced: dict[tuple[int, int], int] = field(default_factory=dict)
    #: Emissive (S14): ignores the key entirely, one flat step.
    glow: bool = False


class Body:
    """A frame under construction: masses in DRAW ORDER, which is depth."""

    def __init__(self) -> None:
        self.masses: list[Mass] = []

    def add(self, pixels: Pixels, ramp: Ramp, tone: int = 0,
            shell: float = SHELL, glow: bool = False) -> Mass:
        mass = Mass(pixels=pixels, ramp=ramp, tone=tone, shell=shell, glow=glow)
        self.masses.append(mass)
        return mass

    def mark(self, mass: Mass, pixels: Pixels, step: int) -> None:
        """Force a step on part of a mass: a seam, a wet band, a lit crown.

        The shader is a good painter and a bad author. Anything that means
        something — the split down his chest, the streak along the bar, the
        gap in the ribs — is marked, not hoped for.
        """
        for p in pixels:
            if p in mass.pixels:
                mass.forced[p] = step

    def paint(self, pixels: Pixels, ramp: Ramp, step: int) -> Mass:
        """A flat authored patch: no shading, no volume, exactly this step."""
        mass = Mass(pixels=set(pixels), ramp=ramp)
        mass.forced = {p: step for p in mass.pixels}
        self.masses.append(mass)
        return mass


def _shift(colour: RGBA, light: float, hue: float, sat: float) -> RGBA:
    """S6/S11's move: cooler, darker, a touch more saturated. Shared law with
    `make_loot._shift` — every keyline in this pipeline is this function."""
    red, green, blue, alpha = colour
    h, l, s = colorsys.rgb_to_hls(red / 255.0, green / 255.0, blue / 255.0)
    h = ((h * 360.0 + hue) % 360.0) / 360.0
    l = max(0.0, min(1.0, l * (1.0 + light)))
    s = max(0.0, min(1.0, s * (1.0 + sat)))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255), alpha)


def resolve(body: Body) -> Image.Image:
    """Masses -> pixels. Shade, occlude, seam, contact, key.

    Order matters and each pass depends on the one before it:

      1. OWNERSHIP. Later masses win. This is the only depth model on the
         sheet and it is enough, because a body is convex lumps in front of
         convex lumps.
      2. SHADING, per mass, over its WHOLE pixel set — including the occluded
         part. Shading only what survives would relight every limb against the
         silhouette of whatever is standing in front of it.
      3. THE SEAM (S18.1). A pixel with a nearer mass beside it drops a step.
         One pixel, never two: this is the AO that says which lump is in
         front, and a fat seam is a line drawn round a limb.
      4. CONTACT (S19). The bottom two rows of the standing silhouette go to
         step 0. It is the cheapest thing that plants fifty pixels of boss on
         a floor.
      5. THE KEYLINE (S6), tinted off the material it keys and dropped on the
         lit crest.
    """
    owner: dict[tuple[int, int], int] = {}
    for index, mass in enumerate(body.masses):
        for p in mass.pixels:
            if 0 <= p[0] < W and 0 <= p[1] < H:
                owner[p] = index

    plan: dict[tuple[int, int], tuple[Ramp, int]] = {}
    for index, mass in enumerate(body.masses):
        visible = {p for p in mass.pixels if owner.get(p) == index}
        if not visible:
            continue
        if mass.glow:
            for p in visible:
                plan[p] = (mass.ramp, mass.forced.get(p, 4))
            continue
        field_ = edt(mass.pixels)
        top = len(mass.ramp) - 1
        for p in visible:
            forced = mass.forced.get(p)
            if forced is not None:
                step = forced
            else:
                d, ex, ey = field_.get(p, (0.0, 0.0, -1.0))
                step = _step_of(d, ex, ey, mass.shell)
            step = max(0, min(top, step + mass.tone))
            plan[p] = (mass.ramp, step)

    # 3. the seam
    seams: dict[tuple[int, int], int] = {}
    for p, index in owner.items():
        if p not in plan:
            continue
        x, y = p
        for nb in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            other = owner.get(nb)
            if other is not None and other > index:
                seams[p] = 1
                break
    for p, drop in seams.items():
        ramp, step = plan[p]
        plan[p] = (ramp, max(0, step - drop))

    # 4. contact — and it is a BAND at the ground line, not a floor under it.
    # Darkening everything below `GROUND` swallowed the one frame the whole
    # chop exists for: a bar buried in the floor is three quarters below the
    # line, and at step 0 the impact frame came out as a boss holding nothing.
    # Two rows above the line and one below is the contact (S19); anything
    # deeper is a thing that has gone INTO the ground and still has to read.
    for p in list(plan):
        if GROUND - 2 <= p[1] <= GROUND + 1:
            ramp, step = plan[p]
            plan[p] = (ramp, max(0, step - 2))

    img = Image.new("RGBA", (W, H), TRANSPARENT)
    px = img.load()
    for (x, y), (ramp, step) in plan.items():
        px[x, y] = ramp[max(0, min(len(ramp) - 1, step))]
    _key(img, plan)
    return img


def _key(img: Image.Image, plan: dict) -> None:
    """The 1px outline. S6, and the same law `make_loot._key` runs.

    Broken on the lit crest, darker along the bottom, and coloured off the
    material it is keying rather than off one shared near-black. On a body
    this big an unbroken border is not 30% of the sprite the way it is on a
    16px icon — but it is still the difference between a mass with light on it
    and a mass someone has traced.
    """
    px = img.load()
    edges: dict[tuple[int, int], RGBA] = {}
    for y in range(img.height):
        for x in range(img.width):
            if px[x, y][3] != 0:
                continue
            below = plan.get((x, y + 1))
            above = plan.get((x, y - 1))
            if below is not None and below[1] >= 3 and above is None:
                continue
            best: tuple[Ramp, int] | None = None
            bottom = False
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                found = plan.get((x + dx, y + dy))
                if found is None:
                    continue
                if best is None or found[1] > best[1]:
                    best = found
                if dy == -1:
                    bottom = True
            if best is None:
                continue
            ramp = best[0]
            edges[(x, y)] = (_shift(ramp[0], -0.48, -18.0, 0.14) if bottom
                             else _shift(ramp[0], -0.25, -15.0, 0.10))
    for (x, y), colour in edges.items():
        px[x, y] = colour


# --- the skeleton -------------------------------------------------------------
# Rest measurements, in frame pixels. Everything below is an offset from these,
# which is the whole reason the rig exists: the shoulder in frame 3 of the walk
# and the shoulder in frame 11 of the chop are the same number plus a delta,
# and nothing drifts.
#
# HE STANDS 55 ROWS. A walker is 16 and a tree is 40. That is the boss read and
# it is the only number on this sheet chosen by eye rather than derived — S17's
# height:footprint band puts a 26px stance somewhere between 29 and 42 rows
# tall, and he is deliberately over it. A boss inside the prop proportions is a
# large enemy; the silhouette has to break the rule the rest of the world keeps.

HIP_Y = 81.0
SHOULDER_Y = 64.0
HEAD_Y = 57.0
#: Half the stance. The feet are 22 apart, so his footprint is not quite two
#: tiles — narrower than his shoulders (S19: the footprint undercuts the mass).
STANCE = 11.0

#: Per facing: how wide the body is, where the shoulders sit, and which way the
#: face is pointed. `side` is authored facing RIGHT; `left` is this mirrored.
#: The side view is NARROW and DEEP — half the front's width — because a boss
#: that is 42px across from every angle is a slab, not a body.
@dataclass(frozen=True)
class View:
    chest_rx: float
    belly_rx: float
    hip_rx: float
    head_rx: float
    #: (free arm, graft arm) shoulder offsets from centre.
    shoulder: tuple[tuple[float, float], tuple[float, float]]
    #: (near foot, far foot) offsets from centre.
    foot: tuple[float, float]


VIEWS: dict[str, View] = {
    "down": View(17.0, 15.0, 11.5, 8.5, ((-15.0, 2.0), (16.0, 0.0)), (-10.0, 10.0)),
    "up": View(17.0, 14.0, 11.5, 8.5, ((15.0, 2.0), (-16.0, 0.0)), (10.0, -10.0)),
    "side": View(13.0, 13.0, 9.5, 7.6, ((-3.0, 3.0), (4.0, 0.0)), (-5.0, 5.0)),
}


@dataclass
class Pose:
    """One frame, as intent. Angles are SCREEN degrees, clockwise, 0 = right.

    Arms and the saw are polar because that is how a swing is authored — an
    arc is one number moving, and a swing written as wrist coordinates is
    forty numbers that have to stay on a circle by hand.
    """
    facing: str = "down"
    #: Whole-body offsets. `rise` is height off the ground; the anchor does not
    #: move with it, which is what makes the landing land.
    shift: tuple[float, float] = (0.0, 0.0)
    rise: float = 0.0
    crouch: float = 0.0
    #: The torso pitched toward the camera and rotated on its own axis. `lean`
    #: is what the whole fight is animated on: he never moves without falling
    #: into it first.
    lean: float = 0.0
    twist: float = 0.0
    head: tuple[float, float] = (0.0, 0.0)
    #: 0 shut, 1 unhinged. The jaw is the face's only moving part and it is
    #: what a roar IS at this size.
    jaw: float = 0.0
    #: (degrees, reach 0..1) for the free arm and the graft arm.
    arm_a: tuple[float, float] = (103.0, 0.92)
    arm_b: tuple[float, float] = (72.0, 0.90)
    #: Absolute screen angle of the bar, and how long it is drawn.
    saw_ang: float = 44.0
    saw_len: float = 31.0
    #: Where the chain is in its loop, and how hard the engine is working.
    #: `rev` drives the exhaust, the spark and the shake — nothing else.
    chain: float = 0.0
    rev: float = 0.30
    #: (near, far) foot offsets from their rest positions.
    feet: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.0), (0.0, 0.0))
    #: The collapse. Every mass sags toward the floor and the hat comes off.
    fall: float = 0.0
    #: Drawn, then flipped. Only `sweep` uses it — see `clip_sweep`.
    mirror: bool = False
    #: Extra art the clip asks for, resolved in `draw`.
    #: WHERE the blow lands, as an offset from his own contact point. It exists
    #: for one facing: swung northward the impact is a third of the way up his
    #: own body on screen, and dust drawn at his feet says he hit the floor
    #: behind himself.
    hit_at: tuple[float, float] = (0.0, 0.0)
    dust: float = 0.0
    crack: float = 0.0
    shadow: float = 0.0


def _polar(ox: float, oy: float, deg: float, dist: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return ox + math.cos(rad) * dist, oy + math.sin(rad) * dist


def _ik(sx: float, sy: float, tx: float, ty: float,
        l1: float, l2: float, sign: float) -> tuple[float, float]:
    """Two-bone solve: where the elbow goes so the hand reaches the target.

    `sign` is which way the joint breaks, and EVERY JOINT ON HIM BREAKS
    OUTWARD — knees bow away from the centre line, elbows away from the ribs.
    It is not a free parameter and it is not symmetry: a knee is a hinge that
    only goes one way, and the way it goes is a fact about the leg rather than
    about where the foot is standing this frame.

    The first cut derived it from which side of the hips the foot was on,
    which produced the mirror of it — both knees pinched toward the middle and
    both forearms folded across the gut. On a body forty pixels wide that is
    not a subtle error: it is the posture of somebody trying to take up less
    room, worn by the largest thing in the game.
    """
    dx, dy = tx - sx, ty - sy
    dist = max(1e-3, min(math.hypot(dx, dy), l1 + l2 - 0.01))
    ux, uy = dx / dist, dy / dist
    a = (dist * dist + l1 * l1 - l2 * l2) / (2.0 * dist)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    return sx + ux * a - uy * h * sign, sy + uy * a + ux * h * sign


@dataclass
class Rig:
    """The solved frame: where every joint actually is."""
    view: View
    hip: tuple[float, float]
    chest: tuple[float, float]
    belly: tuple[float, float]
    head: tuple[float, float]
    shoulder_a: tuple[float, float]
    shoulder_b: tuple[float, float]
    elbow_a: tuple[float, float]
    elbow_b: tuple[float, float]
    hand_a: tuple[float, float]
    wrist_b: tuple[float, float]
    feet: tuple[tuple[float, float], tuple[float, float]]


#: Limb lengths. The graft arm is SHORTER — the hand is gone and the housing
#: starts at the wrist, so the arm that carries the weapon has less arm.
UPPER, FORE = 14.0, 13.0
GRAFT_UPPER, GRAFT_FORE = 14.0, 9.5
THIGH, SHIN = 10.5, 9.5


def solve(pose: Pose) -> Rig:
    view = VIEWS[pose.facing]
    sx, sy = pose.shift
    lift = pose.rise
    hip = (CX + sx, HIP_Y + sy + pose.crouch - lift)
    chest = (hip[0] + pose.twist * 0.35 + pose.lean * 0.20,
             hip[1] - 17.0 + pose.crouch * 0.35 + pose.lean * 0.55)
    belly = ((hip[0] + chest[0]) / 2.0 + 1.0, (hip[1] + chest[1]) / 2.0 + 1.5)
    head = (chest[0] + pose.twist * 0.5 + pose.head[0],
            chest[1] - 7.0 + pose.head[1] + pose.lean * 0.30)

    (ax, ay), (bx, by) = view.shoulder
    shoulder_a = (chest[0] + ax + pose.twist * 0.6, chest[1] + ay - 1.0)
    shoulder_b = (chest[0] + bx + pose.twist * 0.6, chest[1] + by - 1.0)

    deg, reach = pose.arm_a
    hand_a = _polar(*shoulder_a, deg, (UPPER + FORE) * reach)
    deg, reach = pose.arm_b
    wrist_b = _polar(*shoulder_b, deg, (GRAFT_UPPER + GRAFT_FORE) * reach)

    # Mirrored for `up` because that facing is his back: the arm on the left
    # of the screen is the one that was on the right.
    bend = -1.0 if pose.facing == "up" else 1.0
    elbow_a = _ik(*shoulder_a, *hand_a, UPPER, FORE, bend)
    elbow_b = _ik(*shoulder_b, *wrist_b, GRAFT_UPPER, GRAFT_FORE, -bend)

    near, far = view.foot
    (nx, ny), (fx, fy) = pose.feet
    feet = ((CX + sx + near + nx, GROUND + ny - lift),
            (CX + sx + far + fx, GROUND - 1.0 + fy - lift))
    return Rig(view, hip, chest, belly, head, shoulder_a, shoulder_b,
               elbow_a, elbow_b, hand_a, wrist_b, feet)


# --- the saw ------------------------------------------------------------------
# Plotted, never stamped. Everything here is authored in the bar's own (s, v)
# frame — `s` along the bar from the wrist, `v` across it — and converted to
# screen at the end, so the same code draws it pointing anywhere and the teeth
# stay square to the steel instead of to the frame.


def _uv(px: float, py: float, ang: float, s: float, v: float) -> tuple[float, float]:
    rad = math.radians(ang)
    ux, uy = math.cos(rad), math.sin(rad)
    return px + ux * s - uy * v, py + uy * s + ux * v


#: The cutters, spaced on S17's `1 : 0.7 : 0.5`. A comb of evenly spaced teeth
#: reads as a zip, and it is the one thing that made the first cut of this bar
#: look like a toy: the eye counts a regular interval and stops seeing edge.
TOOTH_GAPS = (6.2, 4.4, 3.2)
#: Every third cutter is a HUMAN tooth in the husk's own bone — a molar, wide
#: and blunt, wired between two steel ones. That is the horror beat on this
#: weapon and it is worth three pixels each.
BONE_EVERY = 4


def bar_pixels(pivot: tuple[float, float], ang: float, length: float
               ) -> tuple[Pixels, float, float]:
    """The steel itself: a tapered quad off the housing, with a rounded nose."""
    base, tip = 10.0, 10.0 + length
    hw0, hw1 = 5.4, 3.4
    quad = poly([
        _uv(*pivot, ang, base, -hw0), _uv(*pivot, ang, tip, -hw1),
        _uv(*pivot, ang, tip, hw1), _uv(*pivot, ang, base, hw0),
    ])
    nose = disc(*_uv(*pivot, ang, tip, 0.0), hw1 + 0.4, hw1 + 0.4)
    return quad | nose, base, tip


def draw_saw(body: Body, pivot: tuple[float, float], ang: float,
             length: float, chain: float, rev: float, gore: float = 1.0) -> None:
    """The whole weapon, back to front: tank, housing, bar, chain, teeth, meat."""
    px, py = pivot

    # THE HOUSING. It is not a chainsaw's housing any more — it is a housing
    # bolted to a wrist, so it has no rear handle and no trigger. What it keeps
    # is the shape a two-stroke has from above: a fat block, the tank slung
    # under it, and a stack out of the top corner.
    tank = disc(*_uv(px, py, ang, 1.0, 5.0), 6.0, 5.2)
    body.add(tank, RUST, tone=-1)
    shell = poly([
        _uv(px, py, ang, -4.0, -5.0), _uv(px, py, ang, 2.0, -7.5),
        _uv(px, py, ang, 11.0, -5.4), _uv(px, py, ang, 11.5, 4.6),
        _uv(px, py, ang, -3.0, 5.2),
    ])
    housing = body.add(shell, RUST)
    # A cooling fin band, and the one place on the housing allowed a plane
    # break: S14 says grain runs along its own plane's axis, and the axis of
    # this plane is the bar.
    body.mark(housing, band(shell, px, py, math.cos(math.radians(ang)),
                            math.sin(math.radians(ang)), 3.0, 5.0), 1)

    # THE STACK, and the ember in it. Emissive (S14) and the sprite's accent
    # (S12) — the same hue as the two lights under his hat, because the player
    # has spent a whole night learning that that colour is a thing that has
    # noticed them.
    stack = capsule(*_uv(px, py, ang, 0.0, -6.0), *_uv(px, py, ang, -1.5, -11.5), 2.6, 2.0)
    body.add(stack, STEEL, tone=-1)
    heat = 0.35 + 0.65 * clamp01(rev)
    if heat > 0.45:
        body.add(disc(*_uv(px, py, ang, -1.5, -11.0), 1.6 * heat, 1.4 * heat),
                 EMBER, glow=True)

    # THE BAR. One long mass, and the streak down it is the only specular the
    # weapon gets — S14's painted-metal rule, a 1-2px line along the form's
    # length rather than a hit on a corner.
    steel, base, tip = bar_pixels(pivot, ang, length)
    bar = body.add(steel, STEEL, shell=3.0)
    rad = math.radians(ang)
    ux, uy = math.cos(rad), math.sin(rad)
    crest = band(steel, px, py, -uy, ux, -2.8, -1.6)
    body.mark(bar, crest, 4)
    body.mark(bar, band(steel, px, py, -uy, ux, 0.4, 2.0), 2)
    body.mark(bar, band(steel, px, py, -uy, ux, 2.0, 5.6), 1)

    # THE CHAIN. The rim of the bar, two pixels deep, in the near-dark — and
    # the LINKS are an arclength function of the pose's phase, which is the
    # single thing that makes this read as running rather than as held. A
    # still chain is a saw somebody is carrying; a moving one is a saw that is
    # about to be used.
    rim = {p for p, (d, _, _) in edt(steel).items() if d <= 1.7}
    link = body.add(rim, VOID)
    lit: Pixels = set()
    for (x, y) in rim:
        s = (x - px) * ux + (y - py) * uy
        if (int((s * 0.5 + chain * 3.0) % 3.0)) == 0:
            lit.add((x, y))
    body.mark(link, lit, 3)

    # THE CUTTERS. Both rims, offset by half a gap so the two rows interleave
    # the way a real chain's do, marching with the same phase as the links.
    s = base + 2.0 + (chain % 1.0) * 3.7
    index = 0
    while s < tip - 1.0:
        for side in (-1.0, 1.0):
            offset = s + (0.0 if side < 0 else 1.9)
            if offset > tip - 1.0:
                continue
            hw = 5.4 + (3.4 - 5.4) * ((offset - base) / max(1.0, tip - base))
            root = hw * side
            if (index + (0 if side < 0 else 1)) % BONE_EVERY == 0:
                # A molar: blunt, wide, and a whole step lighter than the
                # steel it is wired between.
                tooth = disc(*_uv(px, py, ang, offset + 0.5, root + side * 1.7), 2.1, 2.1)
                body.add(tooth, BONE, tone=1, shell=2.2)
                body.add(disc(*_uv(px, py, ang, offset + 0.5, root + side * 3.2), 0.9, 0.9),
                         BONE, tone=-1, shell=1.2)
            else:
                # A CUTTER, not a saw-blade triangle: hooked back against the
                # direction of travel, which is what a chain tooth is and what
                # keeps the row from reading as a comb even where the spacing
                # gets tight.
                tooth = poly([
                    _uv(px, py, ang, offset - 1.8, root),
                    _uv(px, py, ang, offset + 1.8, root),
                    _uv(px, py, ang, offset + 2.4, root + side * 2.0),
                    _uv(px, py, ang, offset - 0.4, root + side * 3.4),
                ])
                body.add(tooth, STEEL, tone=1, shell=1.8)
            index += 1
        s += TOOTH_GAPS[index % len(TOOTH_GAPS)]

    # WHAT IT WENT THROUGH. `BLOOD` is the world's one blood — the same stain
    # `make_scenery` leaves on a floor and the same wound `make_gore` opens on
    # a body — so the meat on this chain is the game's meat and not a red
    # somebody picked for a boss.
    if gore > 0.05:
        for step, (along, side) in enumerate(((0.10, -1.0), (0.22, 1.0), (0.46, 1.0))):
            wet = base + along * (tip - base)
            hw = 5.4 + (3.4 - 5.4) * along
            body.add(disc(*_uv(px, py, ang, wet, hw * side), 2.4 * gore, 2.1 * gore),
                     BLOOD, tone=1, shell=1.8)
        drip = _uv(px, py, ang, tip - 3.0, 4.0)
        body.add(capsule(drip[0], drip[1], drip[0] + 0.4, drip[1] + 4.5 * gore, 1.4, 0.7),
                 BLOOD, tone=1, shell=1.4)


# --- the body -----------------------------------------------------------------
# Masses in DRAW ORDER, and the order is the depth model (S18.1). Read the
# function top to bottom and you are reading back to front.


def _boot(body: Body, x: float, y: float, facing: str, flip: float) -> None:
    """A logging boot: a heel block, a toe cap, and the shin sunk into it."""
    body.add(disc(x, y - 3.4, 4.4, 4.0), LEATHER)
    body.add(disc(x + flip * 1.6, y - 1.6, 5.0, 2.8), LEATHER, tone=-1, shell=2.6)


def _leg(body: Body, hip: tuple[float, float], foot: tuple[float, float],
         facing: str, bow: float, toe: float, back: bool) -> None:
    """One leg. `bow` is which way the knee breaks; `toe` is which way the boot
    points. They were one number and they are two things — the knee always
    goes outward and the toe always follows the foot, and tying them together
    is what made the far leg's boot point into the near leg's shin."""
    knee = _ik(hip[0], hip[1], foot[0], foot[1] - 4.0, THIGH, SHIN, bow)
    tone = -1 if back else 0
    body.add(capsule(hip[0], hip[1], knee[0], knee[1], 6.6, 5.4), CANVAS, tone=tone)
    body.add(capsule(knee[0], knee[1], foot[0], foot[1] - 4.0, 5.4, 4.4),
             CANVAS, tone=tone + 1)
    _boot(body, foot[0], foot[1], facing, toe)


def _growths(body: Body, x: float, y: float, spread: float, scale: float) -> None:
    """The fungus off the shoulder. `make_zombie` puts it on the brute; the
    Sawyer has had longer, so his are a ridge rather than three lumps — and
    they break the top of the silhouette, which is where S15 says the identity
    of a shape lives.

    THEY GREW A LIMB AND HAD TO BE CUT BACK. The first cut ran nine pixels out
    from the joint on descending radii, which is the construction of an ARM —
    and on the frames where the graft sweeps across the body, the shoulder it
    was left standing on read as a second arm raised the other way with a pale
    hand on the end of it. A crest is SHORT and it CLUSTERS: nothing here goes
    more than six pixels off the joint, the lobes are within a pixel of each
    other in size rather than tapering, and the whole thing sits a step darker
    than the hat so the top of the silhouette has one bright shape on it and
    not two.
    """
    for i, (dx, dy, r) in enumerate(((0.0, -0.5, 3.2), (3.4, -2.6, 2.9),
                                     (6.0, -4.4, 2.3), (1.8, -4.2, 2.1))):
        body.add(disc(x + dx * spread, y + dy, r * scale, r * scale * 0.94),
                 FUNGUS, tone=0 if i % 2 else -1, shell=2.6)


def _face(body: Body, head: tuple[float, float], view: View, pose: Pose) -> None:
    """Two lights in two holes, and a jaw that does not close.

    Placed by hand, shape by shape. The shader is a good painter and it has
    never once decided anything: every other mass on this body is where the
    solver put it, and the face is the only part of him that is a drawing.
    """
    hx, hy = head
    if pose.facing == "up":
        return
    profile = pose.facing == "side"
    # THE BROW. One dark band across the whole upper face, under the brim. It
    # is not detail — it is what makes the sockets holes instead of two spots
    # painted on a forehead, and without it the accent has nothing to burn in.
    brow = disc(hx, hy - 2.2, view.head_rx * 0.95, 2.8)
    body.paint(brow, VOID, 1)
    sockets = ((2.4, 0.4), (-3.4, 0.6)) if profile else ((-3.8, 0.2), (3.6, -0.2))
    for i, (dx, dy) in enumerate(sockets):
        if profile and i == 1:
            continue
        body.paint(disc(hx + dx, hy + dy, 2.9, 2.5), VOID, 0)
        # THE EYE (S12). One accent, four pixels, and the last thing that
        # disappears when he walks out of the lantern — the same promise
        # `make_zombie` makes about every creature on the sheet, kept at the
        # size the rest of him is drawn at (S21b).
        body.paint(disc(hx + dx + 0.3, hy + dy + 0.2, 1.7, 1.5), EYE, 4)
        body.paint(disc(hx + dx + 0.1, hy + dy, 0.9, 0.8), EYE, 3)

    drop = 3.4 + pose.jaw * 5.5
    mx = hx + (3.4 if profile else 0.0)
    body.paint(disc(mx, hy + drop * 0.66, 3.8 if not profile else 3.2,
                    1.5 + pose.jaw * 3.0), VOID, 0)
    # Teeth: a broken row, and broken is the point — a full set reads as a
    # grin, and a grin is a cartoon.
    for i, dx in enumerate((-3.2, -1.4, 0.6, 2.6)):
        if i == 2 and pose.jaw < 0.35:
            continue
        body.paint(disc(mx + dx, hy + drop * (0.30 if pose.jaw > 0.2 else 0.52),
                        0.9, 1.1 + (0.0 if pose.jaw > 0.2 else 0.5)), BONE, 3)
    if pose.jaw > 0.3:
        for dx in (-2.4, 0.2, 2.2):
            body.paint(disc(mx + dx, hy + drop * 0.9, 0.9, 1.0), BONE, 2)


def _hat(body: Body, head: tuple[float, float], view: View, pose: Pose) -> None:
    """The crew's hard hat, split and grown into. `zhat-hardhat`'s dome, brim
    and ridge at four times the size — the same object, so a player who has
    shot a hard-hatted walker knows what they are looking at."""
    hx, hy = head
    lift = pose.fall * 6.0
    hx += pose.fall * 5.0
    hy -= lift
    crown = disc(hx, hy - 6.0, view.head_rx + 1.8, view.head_rx * 0.92)
    crown = {p for p in crown if p[1] <= hy - 4.6}
    # THE SPLIT. A wedge bitten out of the crown, off centre (S15 — nothing on
    # this body is symmetrical) and deep enough to break the TOP CONTOUR,
    # which is the line the whole silhouette is identified from.
    split = poly([(hx + 0.5, hy - 16.0), (hx + 4.5, hy - 16.0), (hx + 1.5, hy - 6.5)])
    dome = body.add(crown - split, HAT)
    body.mark(dome, band(crown, hx, hy, 1.0, 0.0, -3.0, 0.0), 4)
    # THE BRIM, and it is the reason the eyes work. It sits a clear three rows
    # above the sockets and throws its own shade band across them: the face
    # under a hard hat is a face in a hole, and two lit pixels in a hole is
    # the read this entire body is built around.
    brim = disc(hx + pose.fall * 1.0, hy - 4.4, view.head_rx + 3.6, 2.6)
    brim = {p for p in brim if p[1] >= hy - 6.0}
    body.add(brim, HAT, tone=-1, shell=2.4)


def _torso(body: Body, rig: Rig, pose: Pose) -> None:
    view = rig.view
    sag = pose.fall * 3.0
    hips = disc(rig.hip[0], rig.hip[1] - 2.0, view.hip_rx, 7.5)
    body.add(hips, CANVAS)
    # THE GUT HANGS, and it hangs to ONE SIDE. A belly centred under a chest
    # is a snowman; the whole trunk is offset a pixel and a half off the hip
    # line so the body has a side it is falling toward (S15).
    belly = disc(rig.belly[0] + 1.5, rig.belly[1] + sag, view.belly_rx, 10.5)
    gut = body.add(belly, MEAT)
    chest = disc(rig.chest[0], rig.chest[1], view.chest_rx, 11.0)
    # NOTCHES (S15): 2-4px bitten out of the edge at irregular intervals, so
    # the outline of the biggest mass in the game is not a smooth arc. They
    # are taken out of the chest rather than added to it because a bite reads
    # as damage and a bump reads as anatomy.
    for (nx, ny, nr) in ((-0.92, -0.30, 3.4), (0.86, 0.44, 2.6), (-0.35, 0.95, 2.2)):
        chest = chest - disc(rig.chest[0] + nx * view.chest_rx,
                             rig.chest[1] + ny * 11.0, nr, nr * 0.9)
    trunk = body.add(chest, MEAT)

    # THE SHOULDERS ARE THEIR OWN MASSES. S2: form is a stack of convex lumps
    # and the boundaries read by VALUE STEP. Rolled into the chest disc they
    # were one 40px oval with arms coming out of it, and at this size that is
    # a barrel, not a torso.
    for (jx, jy), lift in ((rig.shoulder_a, 0), (rig.shoulder_b, 1)):
        body.add(disc(jx, jy + 1.0, 7.4 + lift * 1.4, 6.6 + lift * 1.2),
                 MEAT, tone=1, shell=4.0)

    if pose.facing != "up":
        # THE SPLIT CHEST. He is open down the sternum and the ribs on one
        # side are outside the hide. Not centred: S15 bans the mirror, and a
        # wound down the middle of a body is the most symmetrical thing you
        # can do to it.
        seam = band(chest, rig.chest[0] - 3.0, rig.chest[1], 1.0, 0.0, -2.4, 2.4)
        seam = {p for p in seam if p[1] > rig.chest[1] - 7.0}
        body.paint(seam, GORE, 1)
        for i in range(4):
            y = rig.chest[1] - 5.0 + i * 3.6
            rib = disc(rig.chest[0] + view.chest_rx * 0.40, y, view.chest_rx * 0.46, 1.4)
            body.paint(rib & chest, BONE, 3 - (i % 2))
            body.paint((disc(rig.chest[0] + view.chest_rx * 0.40, y + 1.6,
                             view.chest_rx * 0.46, 1.0) & chest) - rib, VOID, 0)
        body.mark(gut, band(belly, rig.belly[0], rig.belly[1], 0.0, 1.0, 3.0, 7.0), 1)
    else:
        # HIS BACK. The spine is out — a ridge of bone knuckles down the
        # middle of the biggest flat mass on the sheet, because a back with
        # nothing on it is the one angle where he stops being a creature.
        for i in range(6):
            body.paint(disc(rig.chest[0] + 1.0, rig.chest[1] - 8.0 + i * 3.6,
                            2.0 - i * 0.12, 1.5), BONE, 3 if i % 2 else 2)

    # THE HARNESS. Logging leathers, still buckled. One strap over the graft
    # shoulder and one round the gut: it is what says a PERSON put this on,
    # which is the difference between a monster and a man something happened to.
    ax, ay = rig.shoulder_a
    bx, by = rig.shoulder_b
    strap = capsule(bx, by + 1.0, rig.hip[0] + (ax - bx) * 0.22, rig.hip[1] - 5.0, 2.6, 2.2)
    body.add(strap & (chest | belly), LEATHER, shell=2.0)
    belt = band(hips, rig.hip[0], rig.hip[1], 0.0, 1.0, -4.0, -1.0)
    body.add(belt, LEATHER, shell=2.0)


def _dust(body: Body, amount: float, at: tuple[float, float] = (0.0, 0.0)) -> None:
    """What a five-tonne landing throws. Flat, unlit, no keyline: it is air.

    Rings rather than a cloud — a puff drawn as one blob at this size is a
    grey lump on the floor, and what says IMPACT is the ring travelling out
    from under him faster than he stands up.
    """
    reach = 7.0 + 30.0 * amount
    fade = clamp01(1.35 - amount)
    for i in range(14):
        a = 0.35 + i * 0.47
        swell = 0.62 + 0.38 * hash01(i, 3, 91)
        x = CX + 3.0 + at[0] + math.cos(a) * reach * 1.45 * swell
        y = GROUND - 4.0 + at[1] + math.sin(a) * reach * 0.36 * swell - amount * 5.0
        r = (5.2 - amount * 2.4) * (0.55 + 0.45 * hash01(i, 7, 13))
        if r < 1.1:
            continue
        body.paint(_clip_decal(disc(x, y, r, r * 0.72)), CANVAS,
                   1 if fade > 0.4 else 0)


#: How close to the edge the weapon may come before the arm has to tuck.
MARGIN = 3.0


def _weapon_box(rig: Rig, pose: Pose) -> tuple[float, float, float, float]:
    """The rectangle the saw occupies, from its pose alone.

    TWO boxes, not one, and the split is what makes it usable. The weapon is
    an L: a deep housing with an exhaust stack over it (wide across the bar,
    short along it) and a long thin bar with cutters (narrow across, long
    along). One box round both claims the stack's height for the whole length
    of the bar — a corner nothing occupies — and `_fit` spent it, tucking the
    arm on poses that were already inside the frame and failing outright on
    poses that were nearly so.
    """
    px, py = rig.wrist_b
    xs: list[float] = []
    ys: list[float] = []
    spans = (
        (-7.0, 12.0, -14.5, 10.5),                              # housing + stack
        (10.0, 10.0 + pose.saw_len + 3.5, -9.0, 9.0),           # bar + cutters
    )
    for s0, s1, v0, v1 in spans:
        for s in (s0, s1):
            for v in (v0, v1):
                x, y = _uv(px, py, pose.saw_ang, s, v)
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _fit(pose: Pose) -> Pose:
    """Tuck the arm until the weapon is inside the frame. THE POSE IS INTENT.

    Every clip on this sheet is authored as angles and reaches — what he is
    DOING — and a frame is a fixed rectangle. Where the two disagree the frame
    wins, because a bar with its nose cut off is a bug the contact sheet
    cannot show. So the arm comes in along its own angle first (an arm pulls in
    through a swing anyway; a chainsaw held at full stretch through a spin is
    the pose nobody adopts), and only if that runs out does the BAR shorten —
    which reads as foreshortening, the same thing the `up` facing does on
    purpose.

    It is deterministic and it is the last thing that touches a pose, so two
    builds of the same clip are the same pixels. What it is NOT is a silent
    fix for a badly authored pose: `_off_frame` still fails the build if
    anything reaches the border after this has run, which is what happens when
    the body itself is in the wrong place rather than the weapon.
    """
    # A pose that is deliberately off screen is not a pose to tuck. `arrive`
    # holds him a hundred and twenty rows above his own frame for four frames
    # while only his shadow is visible, and there is no arm position that puts
    # a weapon back inside a canvas the body is not in.
    if pose.rise > 1.0:
        return pose
    for reach in (1.00, 0.94, 0.88, 0.82, 0.76, 0.70, 0.64, 0.58, 0.52, 0.46):
        for span in (1.00, 0.92, 0.84, 0.76, 0.68, 0.60, 0.52):
            trial = replace(pose,
                            arm_b=(pose.arm_b[0], pose.arm_b[1] * reach),
                            saw_len=pose.saw_len * span)
            x0, y0, x1, y1 = _weapon_box(solve(trial), trial)
            if (x0 >= MARGIN and y0 >= MARGIN
                    and x1 <= W - 1 - MARGIN and y1 <= H - 1 - MARGIN):
                return trial
    raise SystemExit(
        f"no arm tuck fits this pose in the frame: facing={pose.facing} "
        f"saw_ang={pose.saw_ang:.0f} arm_b={pose.arm_b} crouch={pose.crouch}. "
        f"A bar pointed straight down from a crouched wrist cannot fit any "
        f"frame — swing it across him instead.")


def _clip_decal(pixels: Pixels) -> Pixels:
    """Ground marks are cropped to the frame; limbs are not.

    Dust and a ground crack are noise around a contact point — the half of a
    ring that falls outside the frame carries nothing, and cropping it is
    invisible. The same crop on an arm is a missing hand.
    """
    return {(x, y) for (x, y) in pixels
            if MARGIN <= x <= W - 1 - MARGIN and MARGIN <= y <= H - 1 - MARGIN}


def draw(pose: Pose) -> Image.Image:
    """One frame of the Sawyer. Depth is the order of the calls below."""
    pose = _fit(pose)
    rig = solve(pose)
    view = rig.view
    body = Body()
    facing = pose.facing
    flip = -1.0 if facing == "up" else 1.0

    if pose.shadow > 0.01:
        # THE ONLY BAKED SHADOW ON THE SHEET, and it is only on `arrive`.
        # `render/shadows.ts` gives every body a contact pool at runtime, so a
        # second one baked in would double every frame — but the runtime field
        # cannot draw the shadow of a thing that is fifty rows in the air and
        # about to land on you, and that shadow IS the cinematic's first beat.
        r = 9.0 + 15.0 * pose.shadow
        body.paint(_clip_decal(disc(CX + 4.0, GROUND - 2.0, r, r * 0.32)), VOID, 1)
        body.paint(_clip_decal(disc(CX + 4.0, GROUND - 2.0, r * 0.6, r * 0.2)), VOID, 0)

    if pose.crack > 0.01:
        # The floor he landed on, opening. Drawn under him, spreading with the
        # clip: a flat decal, no keyline, the same class of mark as
        # `make_scenery`'s `tracks`.
        ox, oy = pose.hit_at
        for i in range(7):
            a = i * 0.9 + 0.4
            reach = (6.0 + i * 2.4) * pose.crack
            x = CX + ox + math.cos(a) * reach * 1.5
            y = GROUND - 2.0 + oy + math.sin(a) * reach * 0.45
            body.paint(_clip_decal(
                capsule(CX + 3.0 + ox, GROUND - 2.0 + oy, x, y, 2.2, 0.6)), VOID, 0)

    # 1. what is behind him: the far leg, the growths off his back.
    far_first = facing != "up"
    legs = ((rig.feet[1], True), (rig.feet[0], False))
    if not far_first:
        legs = ((rig.feet[0], False), (rig.feet[1], True))
    hip_off = view.hip_rx * 0.5
    for (foot, back) in legs:
        side = -1.0 if foot[0] < rig.hip[0] else 1.0
        _leg(body, (rig.hip[0] + side * hip_off, rig.hip[1]), foot, facing,
             -side, side * flip, back)

    gx, gy = rig.shoulder_b
    if facing == "up":
        _growths(body, gx - 2.0, gy - 5.0, -1.0, 1.15)
        _growths(body, rig.shoulder_a[0] + 2.0, rig.shoulder_a[1] - 3.0, 1.0, 0.7)
    else:
        _growths(body, gx + 1.0, gy - 6.0, 1.0, 1.0)

    if facing == "side":
        # The far arm, BEHIND the torso. It is the one place the draw order
        # says something the poses cannot: in profile his free arm is on the
        # other side of him and it has to be occluded, or the body flattens.
        body.add(capsule(*rig.shoulder_a, *rig.elbow_a, 5.4, 4.6), HIDE, tone=-2)
        body.add(capsule(*rig.elbow_a, *rig.hand_a, 4.6, 3.8), HIDE, tone=-1)
        body.add(disc(*rig.hand_a, 4.0, 3.6), HIDE, tone=-1)

    # 2. the trunk.
    _torso(body, rig, pose)

    # 3. the free arm, in front of the body on every facing that has it there.
    if facing != "side":
        # THE FOREARM IS A STEP LIGHTER THAN THE UPPER ARM, and that is the
        # only thing that makes an arm read as two bones. Two capsules of the
        # same material meeting at an angle are one tube with a kink in it:
        # the shader bands each of them across its own width, so the seam
        # between them lands mid-band and vanishes. It is lighter rather than
        # darker because the forearm hangs FORWARD of the upper arm — nearer
        # the camera, which at this pitch means nearer the key (S18.4).
        body.add(capsule(*rig.shoulder_a, *rig.elbow_a, 6.2, 5.2), HIDE)
        body.add(capsule(*rig.elbow_a, *rig.hand_a, 5.2, 4.2), HIDE, tone=1)
        body.add(disc(*rig.hand_a, 4.4, 4.0), HIDE, tone=1)
        for i, (dx, dy) in enumerate(((-2.6, 2.6), (0.0, 3.4), (2.6, 2.4))):
            body.add(disc(rig.hand_a[0] + dx * flip, rig.hand_a[1] + dy, 1.5, 1.9),
                     HIDE, tone=0 if i == 2 else 1, shell=2.0)

    # 4. the head, sunk between the shoulders. NO NECK — the head mass
    # overlaps the chest by six rows, which is the walker's own lean taken as
    # far as it goes (`make_zombie`: the head sits forward of the shoulders and
    # a row lower than a living one).
    skull = disc(rig.head[0], rig.head[1], view.head_rx, view.head_rx * 0.9)
    head = body.add(skull, ROT)
    if facing == "side":
        # The jaw juts. In profile that overhang is the whole read: it is what
        # separates his top contour from a boulder's.
        body.add(disc(rig.head[0] + 4.0, rig.head[1] + 3.6 + pose.jaw * 2.0, 4.6, 3.4),
                 ROT, shell=3.0)
    elif facing == "down":
        body.add(disc(rig.head[0] + 0.5, rig.head[1] + 3.8 + pose.jaw * 3.0,
                      view.head_rx * 0.72, 3.0), ROT, tone=-1, shell=3.0)
    if facing == "up":
        body.add(disc(rig.head[0], rig.head[1] - 0.5, view.head_rx * 0.86,
                      view.head_rx * 0.78), ROT, tone=-2, shell=4.0)
        for i in range(4):
            body.paint(disc(rig.head[0] - 3.0 + i * 2.2, rig.head[1] + 1.4 + (i % 2) * 1.2,
                            1.1, 0.9), VOID, 0)
    else:
        body.mark(head, band(skull, rig.head[0], rig.head[1], 0.0, 1.0, -7.0, -4.0), 3)
    _face(body, rig.head, view, pose)
    _hat(body, rig.head, view, pose)

    # 5. the graft, and then the weapon. Last, and in front of everything,
    # because the fight is about where the bar is.
    body.add(capsule(*rig.shoulder_b, *rig.elbow_b, 7.0, 5.8), HIDE)
    body.add(capsule(*rig.elbow_b, *rig.wrist_b, 5.8, 4.6), HIDE, tone=1)
    # WHERE THE HAND WAS. A ring of bone at the wrist and two bolts through
    # it. Nothing about the saw says "grafted" until you can see the join.
    body.add(disc(*rig.wrist_b, 4.4, 4.0), BONE, tone=-1, shell=2.2)
    for dx, dy in ((-2.2, -1.6), (2.0, 1.8)):
        body.add(disc(rig.wrist_b[0] + dx, rig.wrist_b[1] + dy, 1.3, 1.3), STEEL, shell=1.4)
    draw_saw(body, rig.wrist_b, pose.saw_ang, pose.saw_len, pose.chain, pose.rev)

    if pose.dust > 0.01:
        _dust(body, pose.dust, pose.hit_at)
    img = resolve(body)
    return img.transpose(Image.FLIP_LEFT_RIGHT) if pose.mirror else img


# --- the clips ----------------------------------------------------------------
# A clip is a list of poses. They are authored as BEATS with holds rather than
# one pose per frame, for the reason `make_merchant.py` gives: the hold on a
# windup is what makes it a threat instead of a flicker, and the fast steps on
# either side of it are what make the rest a movement.
#
# EVERY CLIP STARTS AND ENDS ON `rest(facing)`. The client cuts from the idle
# loop into a one-shot and back with no blend, so a first or last frame that is
# not the resting pose is a visible jump at both ends. `build` checks it.
#
# THE TELEGRAPH IS THE MECHANIC. Every attack here spends more frames winding
# up than swinging: a boss whose blow cannot be read before it lands is a boss
# players learn by dying rather than by watching, and at 14fps the windup is
# the only place the information can live.

IDLE_FPS = 8
WALK_FPS = 10
ACT_FPS = 14

#: Per facing: where forward is on screen, the bar's resting angle, and how
#: much of the bar the camera sees when he points it AWAY from you.
#:
#: `span` is foreshortening and it is not a cheat. At S1's pitch a bar pointing
#: north is running away from the camera, and a 31px bar drawn at 31px while
#: pointing away is a bar that got longer when he turned round. The `up`
#: clips shorten it and the whole facing stops looking like the `down` one
#: with the head repainted.
FACE = {
    "down": {"aim": 90.0, "rest": 32.0, "span": 1.00, "fwd": (0.0, 1.0)},
    "side": {"aim": 0.0, "rest": 18.0, "span": 1.00, "fwd": (1.0, 0.0)},
    "up": {"aim": 270.0, "rest": 148.0, "span": 0.74, "fwd": (0.0, -1.0)},
}


def rest(facing: str) -> Pose:
    """The pose everything returns to. Frame 0 of the idle loop."""
    spec = FACE[facing]
    return Pose(
        facing=facing,
        saw_ang=spec["rest"],
        saw_len=31.0 * spec["span"],
        arm_b=(96.0 if facing != "up" else 84.0, 0.80),
        arm_a=(103.0 if facing != "up" else 77.0, 0.92),
        rev=0.30,
    )


def _beats(stages: list[tuple[Pose, int]]) -> list[Pose]:
    frames: list[Pose] = []
    for pose, hold in stages:
        frames.extend(pose for _ in range(hold))
    return frames


def _chain(frames: list[Pose], rate: float = 0.62) -> list[Pose]:
    """Advance the chain across a clip. It never stops, in any clip, ever —
    including the ones where he is not swinging. A saw that only runs while it
    is being used is a prop; one that runs all night is a threat standing in
    the room with you."""
    return [replace(pose, chain=pose.chain + index * rate)
            for index, pose in enumerate(frames)]


def _step(facing: str, along: float, lift: float = 0.0) -> tuple[float, float]:
    fx, fy = FACE[facing]["fwd"]
    return (fx * along, fy * along * 0.55 - lift)


# --- idle ---------------------------------------------------------------------


def clip_idle(facing: str) -> list[Pose]:
    """Eight frames of standing there with a running engine.

    Two cycles at different rates, which is the whole trick: the BREATH is a
    slow four-frame swell and the SHAKE is the engine, one frame on one frame
    off. A body that only breathes reads as asleep; a body that only shakes
    reads as a machine; the two at different periods read as a man holding
    something that is fighting him.
    """
    base = rest(facing)
    breath = (0.0, -0.5, -1.0, -1.2, -1.0, -0.5, 0.0, 0.2)
    frames: list[Pose] = []
    for i in range(8):
        # The engine runs on a FOUR-frame cycle inside an eight-frame breath,
        # and both are sines of the frame index so both are zero at frame 0.
        # That is not tidiness: frame 0 of this loop is the pose every one-shot
        # on the sheet starts and ends on, and a shake that is 2.6 degrees off
        # at frame 0 is a bar that jumps every single time he attacks.
        shake = 2.6 * math.sin(i * math.tau / 4.0)
        frames.append(replace(
            base,
            crouch=-breath[i] * 0.6,
            lean=breath[i] * 0.5,
            head=(0.0, breath[i] * 0.4),
            saw_ang=base.saw_ang + shake,
            arm_b=(base.arm_b[0] + shake * 0.25, base.arm_b[1]),
            rev=base.rev + 0.09 * math.sin(i * math.tau / 4.0),
        ))
    return _chain(frames)


# --- walk ---------------------------------------------------------------------


def clip_walk(facing: str) -> list[Pose]:
    """The stomp. Eight frames, and it is NOT a walk cycle with a big sprite on it.

    `make_zombie` says a walker does not walk, it falls forward repeatedly and
    catches itself. He is that with four times the mass, so the cycle is built
    round the CATCH: the body drops on the plant (`crouch` spikes on the frame
    the foot lands, not between), the lean runs a beat ahead of the feet, and
    the two halves of the cycle are DIFFERENT — he drags the far leg, so its
    half is flatter and a frame longer in feel. A symmetric stride on a body
    this asymmetric is the one thing that would make him read as a costume.
    """
    base = rest(facing)
    frames: list[Pose] = []
    #: A stride is worth more here than it looks. At six pixels over eight
    #: frames the cycle was legible frame by frame and invisible in motion —
    #: eight frames of a body that is 40 wide moving 6, which reads as a
    #: sprite sliding. Nine, with the DROP on the plant doubled, is a stomp.
    stride = 9.0
    for i in range(8):
        t = i / 8.0
        phase = math.sin(t * math.tau)
        drag = math.sin(t * math.tau + math.pi)
        plant = max(0.0, -math.cos(t * math.tau))
        near = _step(facing, phase * stride, lift=max(0.0, phase) * 4.6)
        far = _step(facing, drag * stride * 0.7, lift=max(0.0, drag) * 1.6)
        frames.append(replace(
            base,
            feet=(near, far),
            crouch=3.0 * plant - 1.0,
            lean=1.8 + phase * 1.8,
            twist=phase * 3.2,
            head=(phase * 1.2, 0.6 + plant * 1.6),
            shift=(phase * 1.0, 0.0),
            saw_ang=base.saw_ang - phase * 7.0,
            arm_a=(base.arm_a[0] - phase * 9.0, base.arm_a[1]),
            arm_b=(base.arm_b[0] + phase * 6.0, 0.92),
            rev=0.30 + 0.08 * plant,
        ))
    return _chain(frames)


# --- chop ---------------------------------------------------------------------
# THE COMMITTED ONE. He raises it over the graft shoulder, holds for three
# frames where anybody watching can see it coming, and buries it in the floor.
# Then he has to get it OUT, and those four frames are the whole reason this
# attack is fair: the punish window is drawn, not configured.

#: (windup angle, contact angle) per facing. Authored per facing rather than
#: derived from the aim because the `up` swing is FORESHORTENED — swung away
#: from the camera the same arc covers a third of the screen distance, and the
#: derived version came out as a bar twitching behind his head.
#: (raised angle, contact angle, contact arm angle, contact reach, bar scale
#: at contact, where the blow lands relative to his feet).
CHOP_ARC = {
    "down": (-122.0, 133.0, 45.0, 0.70, 1.00, (-6.0, 1.0)),
    "side": (-128.0, 62.0, 30.0, 0.80, 1.00, (16.0, 1.0)),
    # Swung north the bar is pointing AWAY from the camera, so it is drawn at
    # a third of its length and most of it is behind his own shoulder. What
    # carries this frame is the lunge and the dust, and the dust is up the
    # screen where the ground he hit actually is.
    "up": (232.0, 286.0, 128.0, 0.62, 0.38, (-4.0, -17.0)),
}


def clip_chop(facing: str) -> tuple[list[Pose], dict]:
    base = rest(facing)
    high, low, low_arm, low_reach, low_span, at = CHOP_ARC[facing]
    spec = FACE[facing]
    up_arm = 292.0 if facing != "up" else 248.0

    coil = replace(base, crouch=1.4, lean=-2.4, twist=-2.6, jaw=0.25,
                   arm_b=(base.arm_b[0] - 14.0 * (1 if facing != "up" else -1), 0.80),
                   saw_ang=base.saw_ang - 26.0, rev=0.55)
    raised = replace(base, crouch=-1.0, lean=-4.0, twist=-4.0, jaw=0.55,
                     head=(0.0, -1.0), arm_b=(up_arm, 0.86), saw_ang=high,
                     saw_len=31.0 * spec["span"], rev=0.95)
    # ONE frame between the raise and the impact, and it is drawn on the far
    # side of the arc from both. A swing that passes through the poses either
    # side of it reads as slow; a swing whose single in-between frame is
    # somewhere neither of them is reads as a blur, which is what a bar moving
    # 240 degrees in a fourteenth of a second actually looks like.
    swing = replace(base, crouch=-2.0, lean=-1.0, twist=-1.0, jaw=0.8,
                    arm_b=(up_arm - 40.0 * (1 if facing != "up" else -1), 0.92),
                    saw_ang=high + (low - high) * 0.42,
                    saw_len=31.0 * (spec["span"] + low_span) * 0.5, rev=1.0)
    hit = replace(base, crouch=5.0, lean=7.0, twist=3.0, jaw=1.0,
                  head=(0.0, 1.6), arm_b=(low_arm, low_reach), saw_ang=low,
                  saw_len=31.0 * low_span, hit_at=at,
                  feet=(_step(facing, 3.0), _step(facing, -2.0)),
                  rev=1.0, dust=0.30, crack=0.55)
    stuck = replace(hit, jaw=0.5, dust=0.55, crack=0.75, rev=0.7, crouch=5.6)
    wrench = replace(stuck, lean=4.0, twist=-2.0,
                     arm_b=(low_arm - 12.0, low_reach + 0.12),
                     saw_ang=low - 16.0, dust=0.75, crack=0.85, rev=0.9, jaw=0.7)
    freed = replace(base, crouch=2.0, lean=-1.0, saw_ang=base.saw_ang - 14.0,
                    arm_b=(base.arm_b[0], 0.86), crack=0.9, hit_at=at,
                    rev=0.6, jaw=0.3)

    frames = _beats([
        (base, 1), (coil, 2), (raised, 2), (raised, 2),
        (swing, 1), (hit, 1), (stuck, 2), (wrench, 2), (freed, 2), (base, 1),
    ])
    return _chain(frames, 0.8), {"hit": 9, "recover": 12}


# --- sweep --------------------------------------------------------------------


#: How many frames one full turn takes. Twelve puts three frames in each
#: quadrant, which is the fewest that still reads as a turn rather than as a
#: sprite being swapped.
TURN = 12
TURNS = 2
#: The facing at each twelfth of a turn, and whether it is drawn mirrored.
#: `sweep` is the one clip with NO facing of its own — it passes through all
#: of them — so it ships as a single file and the client starts it at whatever
#: phase the boss was facing.
SPIN: tuple[tuple[str, bool], ...] = (
    ("down", False), ("down", False), ("side", False), ("side", False),
    ("side", False), ("up", False), ("up", False), ("up", False),
    ("side", True), ("side", True), ("side", True), ("down", False),
)


def clip_sweep() -> tuple[list[Pose], dict]:
    """The ataque giratorio. He plants, and then he is a lawnmower.

    THIS CLIP HAS NO FACING AND THAT IS THE POINT. Every other clip is
    authored three times; a spin authored three times is the same rotation
    written down three times with a phase offset, and the three copies drift.
    So the rig turns instead: the pose's own facing steps through
    down -> right -> up -> left twice, the bar sweeps a full circle in step
    with it, and the client enters the clip at whatever phase the boss was
    already facing.

    The mirrored quadrant lights him from the upper RIGHT for three frames,
    which S8 forbids — and it is the same trade `process_sprites.py` makes for
    every creature's left-facing row. At two turns in a second and a half
    nobody has ever seen it; a body drawn from a fourth authored angle to
    avoid it is a fourth angle that has to agree with the other three.
    """
    frames: list[Pose] = []
    for turn in range(TURNS):
        for step in range(TURN):
            facing, mirror = SPIN[step]
            base = rest(facing)
            t = step / TURN
            # The bar leads the body. A saw exactly on the shoulder line reads
            # as glued to him; a few degrees ahead reads as being SWUNG.
            lead = 26.0
            ang = FACE[facing]["aim"] + lead
            frames.append(replace(
                base, mirror=mirror,
                saw_ang=ang,
                saw_len=33.0 * (1.0 if facing == "side" else 0.62),
                arm_b=(FACE[facing]["aim"] + (10.0 if not mirror else -10.0), 1.0),
                arm_a=(FACE[facing]["aim"] - 30.0, 1.0),
                crouch=1.0 + 0.8 * math.sin(t * math.tau),
                lean=2.0, twist=3.0 * math.cos(t * math.tau),
                jaw=0.8, rev=1.0,
                shift=(math.sin((turn * TURN + step) * 0.9) * 1.2, 0.0),
                # NO DUST UNDER THE SPIN. `_dust` is a ring of blobs sized for
                # an impact, and at the low amounts a continuous effect wants
                # it stops being air and becomes a heap of gravel he is
                # standing in — on every frame of the longest clip on the
                # sheet. The spin's dust is the two frames either side of it,
                # where a plant and a skid actually happen.
            ))
    base = rest("down")
    wind = replace(base, crouch=2.6, lean=-3.0, twist=-5.0, jaw=0.4, rev=0.7,
                   arm_b=(base.arm_b[0] - 40.0, 0.72), saw_ang=base.saw_ang - 62.0)
    load = replace(wind, crouch=3.4, twist=-7.0, rev=1.0, jaw=0.7,
                   saw_ang=base.saw_ang - 84.0)
    reel = replace(base, crouch=3.0, lean=4.0, twist=6.0, jaw=0.6, rev=0.6,
                   arm_b=(base.arm_b[0] + 22.0, 0.94), saw_ang=base.saw_ang + 34.0,
                   dust=0.35)
    settle = replace(base, crouch=1.6, lean=1.4, twist=2.0, jaw=0.2, rev=0.45,
                     saw_ang=base.saw_ang + 12.0, dust=0.15)
    out = _beats([(base, 1), (wind, 2), (load, 3)]) + frames + \
        _beats([(reel, 3), (settle, 2), (base, 1)])
    return _chain(out, 0.9), {"spin": 6, "spinEnd": 6 + TURN * TURNS,
                              "turns": TURNS, "framesPerTurn": TURN}


# --- rip ----------------------------------------------------------------------


#: (cocked bar, released bar, cocked arm, released arm). The throw is a
#: HORIZONTAL arc — the chop is the vertical one, and two attacks that swing
#: in the same plane are one attack the player cannot tell apart until it has
#: hit them.
#:
#: A horizontal swing does not project the same way from every facing, and
#: these four numbers are that projection. Face-on it crosses the SCREEN, so
#: it runs right to left through the front of him. In profile it crosses the
#: BODY, so it runs from behind his shoulder to out in front. Derived from a
#: single arc they came out as the same sweep drawn three times, and one of
#: the three ended with the bar thirty pixels past the right-hand edge —
#: sixteen for the shoulder, twenty-three for the arm and forty-one for the
#: weapon, all pointing the same way.
RIP_ARC = {
    "down": (8.0, 172.0, 44.0, 140.0),
    "side": (140.0, 22.0, 136.0, 52.0),
    "up": (172.0, 8.0, 136.0, 40.0),
}


def clip_rip(facing: str) -> tuple[list[Pose], dict]:
    """The throw. He drags the bar across himself and something leaves it.

    The crescent is not drawn here. It is its own sheet with its own eight
    headings (`slash.png`), because the moment it leaves the bar it stops
    being part of him — it travels, it is what the player dodges, and a thing
    that outlives its animation cannot live inside it.
    """
    base = rest(facing)
    back, through, cock_arm, tear_arm = RIP_ARC[facing]
    spec = FACE[facing]
    #: Which way the whole body turns through the throw, taken from the arc
    #: rather than from the facing — the shoulders lead the arm and the arm
    #: leads the bar, and all three have to agree about which way is round.
    sign = 1.0 if tear_arm > cock_arm else -1.0
    swept = through + (through - back) * 0.12

    cock = replace(base, crouch=1.6, lean=-2.0, twist=-6.0 * sign, jaw=0.35,
                   arm_b=(cock_arm, 0.82), saw_ang=back, rev=0.65)
    load = replace(cock, crouch=2.4, twist=-8.0 * sign, jaw=0.6, rev=1.0,
                   arm_b=(cock_arm - 8.0 * sign, 0.76),
                   saw_ang=back - 14.0 * sign)
    tear = replace(base, crouch=0.6, lean=3.0, twist=6.0 * sign, jaw=1.0,
                   arm_b=(tear_arm, 1.0), saw_ang=through,
                   saw_len=34.0 * spec["span"], rev=1.0,
                   feet=(_step(facing, 2.0), _step(facing, -1.0)))
    after = replace(tear, twist=8.0 * sign, lean=2.0, jaw=0.6,
                    arm_b=(tear_arm + 14.0 * sign, 0.94),
                    saw_ang=swept, rev=0.8)
    ease = replace(base, crouch=1.0, twist=3.0 * sign, jaw=0.2, rev=0.5,
                   saw_ang=base.saw_ang + 18.0 * sign, arm_b=(base.arm_b[0], 0.88))

    frames = _beats([
        (base, 1), (cock, 2), (load, 3), (tear, 1), (tear, 1),
        (after, 2), (ease, 3), (base, 1),
    ])
    return _chain(frames, 0.85), {"release": 6}


# --- rev ----------------------------------------------------------------------


def clip_rev(facing: str) -> tuple[list[Pose], dict]:
    """The cord, the catch, the roar. A telegraph and a phase change in one.

    It is the only clip in which nothing about him moves toward the player,
    and that is what it is for: it is the beat that says the fight has
    changed. The engine climbs across four frames — `rev` drives the ember,
    the shake and the exhaust, and nothing else on the sheet touches them —
    and the roar lands two frames AFTER the engine peaks, so the sound the
    player is hearing in their head is the saw and not him.
    """
    base = rest(facing)
    lift = replace(base, crouch=1.2, lean=-1.6, jaw=0.2, rev=0.45,
                   arm_b=(base.arm_b[0] - 26.0, 0.72),
                   saw_ang=FACE[facing]["aim"] - 52.0)
    pull = replace(lift, crouch=2.0, twist=-3.0, jaw=0.4, rev=0.75,
                   arm_a=(base.arm_a[0] - 44.0, 0.70),
                   saw_ang=FACE[facing]["aim"] - 44.0)
    catch = replace(lift, crouch=0.4, twist=2.0, jaw=0.6, rev=1.0,
                    arm_a=(base.arm_a[0] - 8.0, 0.92),
                    saw_ang=FACE[facing]["aim"] - 58.0)
    roar = replace(base, crouch=-1.6, lean=-4.0, jaw=1.0, rev=1.0,
                   head=(0.0, -1.6), arm_a=(base.arm_a[0] - 58.0, 0.98),
                   arm_b=(base.arm_b[0] - 46.0, 0.96),
                   saw_ang=FACE[facing]["aim"] - 74.0)
    ease = replace(base, crouch=0.8, jaw=0.35, rev=0.6,
                   saw_ang=base.saw_ang - 10.0)

    frames = _beats([
        (base, 1), (lift, 2), (pull, 1), (catch, 2),
        (roar, 3), (roar, 1), (ease, 3), (base, 1),
    ])
    return _chain(frames, 1.1), {"roar": 6}


# --- arrive -------------------------------------------------------------------


def clip_arrive() -> tuple[list[Pose], dict]:
    """THE CINEMATIC. He comes down on the place the players just finished in.

    It is authored `down` only. Every other clip has three facings because the
    boss is being fought from anywhere; this one runs once, before there is a
    fight, and the camera beat it belongs to puts him in front of the party.

    FOUR FRAMES OF NOTHING BUT A SHADOW, and they are the best four frames on
    the sheet. Nothing on screen has ever cast a growing shadow — the runtime
    field cannot, because it draws what is standing on the floor — so the mark
    spreading under the party is unambiguous and it is the only warning they
    get. Then he enters from the top of the frame already falling, which is
    two frames the client does not have to script.
    """
    base = rest("down")
    frames: list[Pose] = []
    for i in range(4):
        frames.append(replace(base, rise=120.0, shadow=0.18 + i * 0.24,
                              rev=0.0, jaw=0.2))
    # HE COMES DOWN TUCKED. A body drawn standing upright and simply moved up
    # the frame is a body on a lift, not a body falling — what says falling is
    # that the knees are up and the arms are IN, because that is the shape
    # something makes when it is about to hit. The tuck opens across the three
    # frames so the last one before impact is already reaching for the floor.
    for i, (high, tuck) in enumerate(((44.0, 1.0), (22.0, 0.7), (8.0, 0.25))):
        frames.append(replace(
            base, rise=high, shadow=0.9 + i * 0.03,
            crouch=9.0 * tuck - 1.0, lean=-5.0 * tuck,
            head=(0.0, -1.5 * tuck),
            jaw=0.5 + i * 0.15,
            feet=((-1.0, -7.0 * tuck), (1.0, -5.0 * tuck)),
            arm_a=(base.arm_a[0] - 34.0 * tuck, 0.70 - 0.12 * tuck),
            arm_b=(base.arm_b[0] - 26.0 * tuck, 0.66),
            saw_ang=base.saw_ang - 40.0 - 26.0 * tuck,
            rev=0.3 + i * 0.2,
        ))
    # THE LANDING POSE, and the bar is the reason it looks like this. A boss
    # coming down out of the sky wants to land in a crouch with the weapon
    # driven into the floor under him — and a 41px bar pointing down from a
    # wrist that is already at knee height ends twenty rows below the canvas,
    # in any canvas. So it goes ACROSS: arm out wide, bar swept over the
    # ground on his left, which is also the pose that makes the dust ring read,
    # because nothing is standing on top of it.
    land = replace(base, crouch=8.0, lean=6.0, jaw=1.0, head=(0.0, 2.0),
                   arm_a=(132.0, 0.98), arm_b=(8.0, 0.85), saw_ang=146.0,
                   feet=((-4.0, 0.0), (4.0, 0.0)), dust=0.22, crack=0.5, rev=1.0)
    frames.append(land)
    for i in range(4):
        frames.append(replace(land, crouch=8.0 - i * 1.2, jaw=1.0 - i * 0.12,
                              dust=0.34 + i * 0.20, crack=0.62 + i * 0.09,
                              rev=1.0))
    for i in range(5):
        t = i / 4.0
        frames.append(replace(
            base, crouch=3.4 * (1.0 - t), lean=3.0 * (1.0 - t) - 1.0,
            jaw=0.5 - t * 0.2, head=(0.0, 1.0 - t),
            arm_a=(base.arm_a[0] + 16.0 * (1.0 - t), 0.94),
            arm_b=(base.arm_b[0] + 10.0 * (1.0 - t), 0.94),
            saw_ang=base.saw_ang + 24.0 * (1.0 - t),
            dust=max(0.0, 0.95 - t * 0.9), crack=0.95, rev=0.9,
        ))
    roar, _ = clip_rev("down")
    frames.extend(replace(pose, crack=0.9, chain=0.0) for pose in roar[1:-1])
    frames.append(base)
    return _chain(frames, 0.75), {"impact": 7, "rise": 12, "roar": 18}


# --- death --------------------------------------------------------------------


def clip_death(facing: str) -> tuple[list[Pose], dict]:
    """Knees first, then forward. The last frame is the rest he holds all night.

    Same contract as every creature's `-death` sheet in `make_zombie.py`: a
    timeline, not a loop, whose final column is the corpse. What is different
    is the SAW — it dies too. `rev` runs to zero across the clip, which takes
    the ember out, stops the shake and stops the chain, and the last thing
    that happens on this sheet is the accent going out. He is the only thing
    in the game that has two lights to lose.
    """
    base = rest(facing)
    # Which way his arms splay. `crouch` is capped at 13 through the whole
    # collapse and that cap is load-bearing: it lowers the HIPS while the feet
    # stay on the floor, so past about fourteen the legs fold through the
    # ground and the hands end up below the bottom of the canvas. A body this
    # size does not need more than that to read as down — what says down is
    # the LEAN and the head, not the height.
    mir = 1.0 if facing != "up" else -1.0
    flat = 168.0 if facing != "up" else 12.0
    frames: list[Pose] = []
    stages = [
        # 1. hit. The engine misses a beat and he straightens into it.
        (replace(base, crouch=-1.0, lean=-3.0, jaw=0.6, rev=0.5,
                 head=(0.0, -1.0), saw_ang=base.saw_ang - 18.0), 2),
        # 2. the knees go.
        (replace(base, crouch=2.0, lean=2.0, twist=-3.0, jaw=0.8, rev=0.35,
                 arm_a=(base.arm_a[0] + 14.0, 0.80),
                 saw_ang=flat - 78.0 * mir), 2),
        (replace(base, crouch=6.0, lean=5.0, twist=2.0, jaw=0.7, rev=0.2,
                 head=(0.5 * mir, 2.0), arm_a=(90.0 + 34.0 * mir, 0.94),
                 arm_b=(90.0 - 22.0 * mir, 0.92),
                 saw_ang=flat - 46.0 * mir,
                 feet=((-2.0, 0.0), (2.0, 0.0)), dust=0.20), 2),
        # 3. forward. The saw hits the floor before he does.
        (replace(base, crouch=11.0, lean=9.0, jaw=0.5, rev=0.10, fall=0.35,
                 head=(1.0 * mir, 4.0), arm_a=(90.0 + 50.0 * mir, 0.98),
                 arm_b=(90.0 - 48.0 * mir, 0.94), saw_ang=flat - 20.0 * mir,
                 feet=((-5.0, 0.0), (5.0, 0.0)), dust=0.45), 2),
        (replace(base, crouch=12.5, lean=12.0, jaw=0.35, rev=0.04, fall=0.7,
                 head=(1.6 * mir, 6.4), arm_a=(90.0 + 60.0 * mir, 0.98),
                 arm_b=(90.0 - 62.0 * mir, 0.95), saw_ang=flat - 8.0 * mir,
                 feet=((-7.0, 1.0), (7.0, 1.0)), dust=0.65), 3),
        # 4. the rest he holds for the remainder of the night.
        (replace(base, crouch=13.0, lean=13.0, jaw=0.2, rev=0.0, fall=1.0,
                 head=(2.0 * mir, 7.4), arm_a=(90.0 + 64.0 * mir, 0.98),
                 arm_b=(90.0 - 66.0 * mir, 0.95), saw_ang=flat,
                 feet=((-8.0, 1.0), (8.0, 1.0)), dust=0.45), 3),
        (replace(base, crouch=13.0, lean=13.0, jaw=0.15, rev=0.0, fall=1.0,
                 head=(2.0 * mir, 7.6), arm_a=(90.0 + 64.0 * mir, 0.98),
                 arm_b=(90.0 - 66.0 * mir, 0.95), saw_ang=flat,
                 feet=((-8.0, 1.0), (8.0, 1.0)), dust=0.0), 6),
    ]
    frames = _beats([(base, 1)] + stages)
    # The chain slows and stops with the engine rather than running at a fixed
    # rate: a corpse whose saw is still turning is a corpse that is not done.
    out: list[Pose] = []
    phase = 0.0
    for pose in frames:
        out.append(replace(pose, chain=phase))
        phase += 0.9 * pose.rev
    return out, {"knees": 7, "down": 13, "rest": len(out) - 1}


# --- what leaves the bar ------------------------------------------------------
# The thrown crescent is its own sheet because it OUTLIVES the animation that
# threw it. `rip` releases on frame 6 and the thing then travels for most of a
# second, so it cannot live inside the clip — and it is not a VFX either:
# `make_vfx.py`'s sheets are greyscale and tinted per player, and this belongs
# to a creature, in its own baked colour, like `make_weapon_vfx.py`'s fire.

#: Eight compass headings, BAKED, one per 45 degrees — the same decision
#: `tracks.png` documents in `make_textures.py`. A crescent rotated at draw
#: time is a grey smear, and which way the teeth face is the whole read.
SLASH_HEADINGS = 8
SLASH_W = SLASH_H = 40
SLASH_FRAMES = 5
BURST_W = BURST_H = 32
BURST_FRAMES = 6


def slash_frame(heading: float, step: int) -> Image.Image:
    """One frame of the crescent: an arc of chain with the teeth on the outside.

    It is a piece of the weapon, not a magic slash — the same steel, the same
    cutters, the same near-dark chain, so a player who has watched the bar
    knows what has just been thrown at them. What makes it read as MOVING is
    the leading edge: an ember rim on the outer arc only (S14, emissive), one
    pixel deep, in the accent the engine and his eyes already share.
    """
    body = Body.__new__(Body)
    body.masses = []
    cx, cy = SLASH_W / 2.0, SLASH_H / 2.0
    t = step / (SLASH_FRAMES - 1)
    #: It STRETCHES as it goes: the arc opens and thins, which is the only
    #: cue at this size that says it is travelling rather than spinning.
    radius = 11.0 + 5.0 * t
    thick = 4.6 - 2.2 * t
    span = math.radians(64.0 - 16.0 * t)
    aim = math.radians(heading)

    arc: Pixels = set()
    outer: list[tuple[float, float]] = []
    for y in range(SLASH_H):
        for x in range(SLASH_W):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            r = math.hypot(dx, dy)
            if r < 1e-6:
                continue
            delta = math.atan2(dy, dx) - aim
            delta = (delta + math.pi) % math.tau - math.pi
            if abs(delta) > span:
                continue
            # The ends taper. An arc of even thickness is a rainbow.
            taper = 1.0 - (abs(delta) / span) ** 2.2
            half = thick * (0.35 + 0.65 * taper) * 0.5
            if abs(r - radius) <= half:
                arc.add((x, y))
    if not arc:
        return Image.new("RGBA", (SLASH_W, SLASH_H), TRANSPARENT)
    steel = body.add(arc, STEEL, shell=2.2)

    for (x, y) in arc:
        dx, dy = x + 0.5 - cx, y + 0.5 - cy
        r = math.hypot(dx, dy)
        if r >= radius + thick * 0.18:
            outer.append((x, y))
    body.mark(steel, {p for p in outer}, 1)

    # THE CUTTERS, on the outer arc, marching with the same phase the bar's do.
    count = 7
    for i in range(count):
        u = (i + 0.5) / count
        delta = (u * 2.0 - 1.0) * span * 0.92
        ang = aim + delta
        rr = radius + thick * 0.4
        px = cx + math.cos(ang) * rr
        py = cy + math.sin(ang) * rr
        if i % 3 == 0:
            body.add(disc(px, py, 1.9, 1.9), BONE, tone=1, shell=1.8)
        else:
            tip_r = rr + 2.6 * (1.0 - abs(delta) / span * 0.6)
            body.add(poly([
                (cx + math.cos(ang - 0.10) * (rr - 1.0),
                 cy + math.sin(ang - 0.10) * (rr - 1.0)),
                (cx + math.cos(ang + 0.10) * (rr - 1.0),
                 cy + math.sin(ang + 0.10) * (rr - 1.0)),
                (cx + math.cos(ang + 0.13) * tip_r,
                 cy + math.sin(ang + 0.13) * tip_r),
            ]), STEEL, tone=1, shell=1.4)

    # THE LEADING EDGE. One pixel of the accent on the outside of the arc, and
    # it is the only emissive thing on the sheet — the crescent has to be
    # findable against a forest floor at night, and S22 says what says "lit" is
    # the lit object rather than a wash around it.
    lead: Pixels = set()
    for i in range(64):
        delta = (i / 63.0 * 2.0 - 1.0) * span
        rr = radius + thick * 0.5
        lead.add((int(round(cx + math.cos(aim + delta) * rr)),
                  int(round(cy + math.sin(aim + delta) * rr))))
    body.add(lead, EMBER, glow=True)

    # And the meat it took with it.
    for i in range(3):
        delta = (hash01(i, step, 5) - 0.5) * 1.5 * span
        rr = radius - thick * (0.2 + 0.5 * hash01(i, step, 9))
        body.add(disc(cx + math.cos(aim + delta) * rr,
                      cy + math.sin(aim + delta) * rr, 1.6, 1.5),
                 BLOOD, tone=1, shell=1.4)

    img = Image.new("RGBA", (SLASH_W, SLASH_H), TRANSPARENT)
    _compose(body, img)
    return img


def burst_frame(step: int) -> Image.Image:
    """What the crescent does when it stops: it comes apart.

    A timeline, not a loop (S: VFX sheets are timelines) — frame 0 is the
    crescent's own thickness collapsed to a point and the last frame is nearly
    empty, so there is no pop at either end.
    """
    body = Body.__new__(Body)
    body.masses = []
    cx, cy = BURST_W / 2.0, BURST_H / 2.0
    t = step / (BURST_FRAMES - 1)
    # THE FLASH IS A STAR, NOT A DISC, and it is over in two frames.
    # An emissive circle that GROWS is a filled peach lozenge sitting on the
    # floor — it has no direction in it, which S22 rules out in as many words:
    # a glow with no shape carries no information. Four spokes on the crescent
    # kept the direction the thing was travelling in, and they contract instead
    # of expanding, so the impact reads as the arc collapsing into the point it
    # hit rather than as a bubble inflating out of it.
    flash = (1.0 - t) ** 2.0
    if flash > 0.20:
        core = 1.6 + 3.4 * flash
        body.add(disc(cx, cy, core, core * 0.82), EMBER, glow=True)
        for spoke in range(4):
            a = math.pi / 4.0 + spoke * math.pi / 2.0
            reach = core + 5.0 * flash
            body.add(capsule(cx, cy, cx + math.cos(a) * reach,
                             cy + math.sin(a) * reach * 0.8, 1.4 * flash, 0.5),
                     EMBER, glow=True)

    # THE SHARDS ARE THE CHAIN COMING APART, so they are cutter-sized and they
    # carry the meat with them. Eleven two-pixel specks read as sparks off a
    # grinder; these are pieces.
    if t > 0.001:
        for i in range(14):
            a = hash01(i, 0, 17) * math.tau
            speed = 4.0 + 11.0 * hash01(i, 1, 23)
            r = speed * t * 1.5
            size = (3.2 - 1.9 * t) * (0.55 + 0.55 * hash01(i, 2, 31))
            if size < 0.9:
                continue
            x, y = cx + math.cos(a) * r, cy + math.sin(a) * r * 0.8
            ramp = BLOOD if i % 3 else STEEL
            body.add(disc(x, y, size, size * 0.85), ramp,
                     tone=1 if ramp is BLOOD else 0, shell=1.6)
    img = Image.new("RGBA", (BURST_W, BURST_H), TRANSPARENT)
    _compose(body, img)
    return img


def _compose(body: Body, img: Image.Image) -> None:
    """`resolve` for a sheet that is not the boss's own frame size."""
    global W, H
    keep_w, keep_h = W, H
    W, H = img.width, img.height
    try:
        out = resolve(body)
    finally:
        W, H = keep_w, keep_h
    img.alpha_composite(out)


# --- build --------------------------------------------------------------------

#: `left` is `right` flipped. Every creature in the game ships this way
#: (`process_sprites.py` mirrors the side row) and the cost is the same one:
#: the key light comes from the upper right for one facing out of four.
FACINGS = ("down", "left", "right", "up")


def _render(poses: list[Pose], mirror: bool = False) -> list[Image.Image]:
    out: list[Image.Image] = []
    for pose in poses:
        img = draw(pose)
        out.append(img.transpose(Image.FLIP_LEFT_RIGHT) if mirror else img)
    return out


def _off_frame(frames: list[Image.Image], poses: list[Pose]) -> list[int]:
    """Frames whose art touches the border. Everything here is CLIPPED ART.

    It is a real check and not a tidiness one: the 96x88 first cut looked
    correct in every still except the four that mattered, because a bar with
    its last eight pixels missing still reads as a bar in a contact sheet and
    reads as a broken sprite in a game. The only frames allowed to fail it are
    the ones where he is deliberately off screen — `arrive`'s entry, where
    `rise` puts him above the frame on purpose.
    """
    bad: list[int] = []
    for index, (img, pose) in enumerate(zip(frames, poses)):
        if pose.rise > 1.0:
            continue
        px = img.load()
        hit = False
        for x in range(img.width):
            if px[x, 0][3] or px[x, img.height - 1][3]:
                hit = True
                break
        if not hit:
            for y in range(img.height):
                if px[0, y][3] or px[img.width - 1, y][3]:
                    hit = True
                    break
        if hit:
            bad.append(index)
    return bad


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "sawyer"
    out_dir.mkdir(parents=True, exist_ok=True)

    #: name -> (per-facing pose builder, fps, loops, events)
    plan: list[tuple[str, object, int, bool]] = [
        ("idle", clip_idle, IDLE_FPS, True),
        ("walk", clip_walk, WALK_FPS, True),
        ("chop", clip_chop, ACT_FPS, False),
        ("rip", clip_rip, ACT_FPS, False),
        ("rev", clip_rev, ACT_FPS, False),
        ("death", clip_death, 10, False),
    ]

    clips: dict[str, dict] = {}
    clipped: list[str] = []
    seams: list[str] = []

    def seam(name: str, facing: str, poses: list[Pose]) -> None:
        """THE SEAM CHECK, and it is `make_merchant.py`'s for the same reason:
        the client cuts from the idle loop into a one-shot and back with no
        blend, so both ends of a one-shot have to BE the resting pose.

        It compares POSES, not pixels, and the difference matters. Every clip
        advances the chain, so the last frame of a one-shot is never
        pixel-identical to the first — the links have moved, which is the one
        thing on this sheet that is SUPPOSED to keep going across the cut. A
        pixel check would either fail on every clip or have to be told to
        ignore the weapon.
        """
        target = rest(facing)
        for edge, pose in (("first", poses[0]), ("last", poses[-1])):
            if name == "arrive" and edge == "first":
                continue  # he is not there yet: that is the point of the clip
            if replace(pose, chain=0.0) != target:
                seams.append(f"{name}-{facing} {edge}")

    for facing in ("down", "side", "up"):
        if replace(clip_idle(facing)[0], chain=0.0) != rest(facing):
            raise SystemExit(f"idle-{facing} frame 0 is not the resting pose")

    for name, builder, fps, loop in plan:
        facings: dict[str, str] = {}
        events: dict = {}
        count = 0
        for facing in FACINGS:
            source = "side" if facing in ("left", "right") else facing
            made = builder(source)
            poses, events = made if isinstance(made, tuple) else (made, {})
            frames = _render(poses, mirror=(facing == "left"))
            count = len(frames)
            bad = _off_frame(frames, poses)
            if bad:
                clipped.append(f"{name}-{facing} frames {bad}")
            if name not in ("idle", "walk", "death"):
                seam(name, source, poses)
            pack(frames, W, H).save(out_dir / f"{name}-{facing}.png")
            facings[facing] = f"{name}-{facing}.png"
        clips[name] = {"frames": count, "fps": fps, "loop": loop,
                       "facings": facings}
        if events:
            clips[name]["events"] = events

    # THE SPIN, which has no facing. See `clip_sweep`.
    poses, events = clip_sweep()
    seam("sweep", "down", poses)
    frames = _render(poses)
    bad = _off_frame(frames, poses)
    if bad:
        clipped.append(f"sweep frames {bad}")
    pack(frames, W, H).save(out_dir / "sweep.png")
    clips["sweep"] = {"frames": len(frames), "fps": 16, "loop": False,
                      "file": "sweep.png", "facings": None, "events": events}

    # THE CINEMATIC, which has one.
    poses, events = clip_arrive()
    seam("arrive", "down", poses)
    frames = _render(poses)
    bad = _off_frame(frames, poses)
    if bad:
        clipped.append(f"arrive frames {bad}")
    pack(frames, W, H).save(out_dir / "arrive-down.png")
    clips["arrive"] = {"frames": len(frames), "fps": ACT_FPS, "loop": False,
                       "facings": {"down": "arrive-down.png"}, "events": events}


    slashes = [slash_frame(h * 360.0 / SLASH_HEADINGS, step)
               for h in range(SLASH_HEADINGS) for step in range(SLASH_FRAMES)]
    pack(slashes, SLASH_W, SLASH_H).save(out_dir / "slash.png")
    bursts = [burst_frame(step) for step in range(BURST_FRAMES)]
    pack(bursts, BURST_W, BURST_H).save(out_dir / "slash-burst.png")

    manifest = {
        "name": "sawyer",
        "frameWidth": W,
        "frameHeight": H,
        # The GROUND CONTACT, not the frame's bottom edge — he keeps rows under
        # his feet for dust and for a buried bar. Everything else in the game
        # anchors at 1.0; this one does not, and a client that assumes it will
        # bury him a foot deep.
        "anchor": {"x": 0.5, "y": round(GROUND / H, 4)},
        # What he actually occupies on the floor, in tiles. The frame is sized
        # by his SWING and is nowhere near his footprint — a hitbox taken off
        # `frameWidth` would be seven tiles wide.
        "footprint": {"w": round(26.0 / 16.0, 3), "h": round(12.0 / 16.0, 3)},
        "height": round(55.0 / 16.0, 3),
        "clips": clips,
        "projectile": {
            "file": "slash.png",
            "frameWidth": SLASH_W, "frameHeight": SLASH_H,
            "headings": SLASH_HEADINGS, "frames": SLASH_FRAMES,
            "fps": 14, "loop": True,
            "anchor": {"x": 0.5, "y": 0.5},
            "burst": {"file": "slash-burst.png", "frameWidth": BURST_W,
                      "frameHeight": BURST_H, "frames": BURST_FRAMES,
                      "fps": 18, "loop": False,
                      "anchor": {"x": 0.5, "y": 0.5}},
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for line in seams:
        print(f"  SEAM: {line} is not the resting pose")
    if seams:
        raise SystemExit("a one-shot does not start and end on idle frame 0")
    for line in clipped:
        print(f"  CLIPPED: {line}")
    if clipped and not args.allow_clipped:
        raise SystemExit("art is touching the frame border — see above")

    print(f"wrote {out_dir}: frame {W}x{H}, "
          + ", ".join(f"{name} {spec['frames']}f" for name, spec in clips.items())
          + f", slash {SLASH_HEADINGS}x{SLASH_FRAMES}")
    return out_dir


def _preview(out_dir: Path, path: Path, scale: int) -> None:
    """A contact sheet of every clip, on the forest's own dark. Not shipped."""
    manifest = json.loads((out_dir / "manifest.json").read_text())
    rows: list[Image.Image] = []
    for spec in manifest["clips"].values():
        name = spec.get("file") or spec["facings"].get("down") or \
            next(iter(spec["facings"].values()))
        rows.append(Image.open(out_dir / name))
    rows.append(Image.open(out_dir / "slash.png"))
    rows.append(Image.open(out_dir / "slash-burst.png"))
    width = max(row.width for row in rows)
    sheet = Image.new("RGBA", (width, sum(r.height for r in rows)), (34, 30, 30, 255))
    y = 0
    for row in rows:
        sheet.paste(row, (0, y), row)
        y += row.height
    sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="",
                    help="write a scaled contact sheet HERE (outside the tree) "
                         "for eyeballing the art; never into assets/")
    ap.add_argument("--preview-scale", type=int, default=3)
    ap.add_argument("--allow-clipped", action="store_true",
                    help="report art touching the frame border instead of "
                         "failing on it. For looking at a work in progress.")
    args = ap.parse_args()
    out_dir = build(args)
    if args.preview:
        _preview(out_dir, Path(args.preview), args.preview_scale)


if __name__ == "__main__":
    main()
