#!/usr/bin/env python3
"""Asset pipeline: the MERCHANT — the one person out here who is not trying to eat you.

Output (assets/processed/merchant/):
    idle.png     8 frames,  22x28   LOOP     — standing, breathing, blinking
    coat.png     18 frames, 22x28   one-shot — the coat opens on the wares
    beckon.png   14 frames, 22x28   one-shot — a hand out, twice
    coin.png     16 frames, 22x28   one-shot — a coin flipped and pocketed
    manifest.json

HE IS A CHARACTER WITH NO WALK, AND THAT IS WHY HE IS NOT ON THE RAW PATH.
Every other body in the game goes `make_placeholder_sheet.py` → `process_sprites.py`,
which produces one shape: four facings by three walk frames. The merchant never
takes a step and never turns around — he stands behind his tables facing the
corridor for the whole of a store visit. What he has instead of facings is
CLIPS: one loop that always runs, and three one-shots the client fires at
random while the party shops. That does not fit a walk sheet's rows, so he is
generated straight into `assets/processed/` like the rift, and each clip is its
own file because they have different lengths and different rules.

ONE FACING, AND THE ANIMATION IS THE CHARACTER.
A shopkeeper who stands still is furniture. Everything readable about him is in
the three one-shots, so each one has to say something a still frame cannot:
`coat` is the sales pitch (the coat comes open on a lining hung with stock),
`beckon` is him noticing you, and `coin` is what he thinks about while you make
up your mind. They are deliberately different LENGTHS and different KINDS of
motion — one symmetric, one repeated, one travelling — because three idles of
the same shape read as one animation glitching rather than as a person.

EVERY ONE-SHOT STARTS AND ENDS ON IDLE FRAME 0.
Same discipline as `make_rift.py`'s handoffs, for the same reason: the client
cuts from the loop into a one-shot and back with no blend, so a first or last
frame that is not the resting pose is a visible jump at both ends. Here it is
cheap to guarantee — the one-shots are built from the same parts as the idle —
and `build` verifies it by comparing bytes, refusing to write if either seam
moved.

THE ART IS AUTHORED, NOT NOISED.
The body is ASCII layers over a palette, the same vocabulary as
`make_placeholder_sheet.py`, because a face and a silhouette are decisions and
noise cannot make them. What IS procedural: the weave grain on the coat (a
`hash01` value jitter, keyed to BODY coordinates so it does not crawl when he
breathes) and the flipped coin's arc.

READ ORDER. He is bigger than a player (22x28 against 16x16) and stands alone
in a lit corridor, so he can carry more detail than a zombie — but the reads
that matter at this size are three: the BUNDLE breaking his silhouette above
the shoulders, the black hood with one eye-glint in it, and the purple bandana,
which is the only violet in the game and is what makes him identifiable from
the far end of the store.

Usage:
    python tools/make_merchant.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from make_textures import (
    COIN_OUTLINE,
    COIN_RAMP,
    PROCESSED_DIR,
    RGBA,
    TRANSPARENT,
    clamp01,
    hash01,
    pack,
    rgb,
)

#: The frame he is authored on. Wider and taller than a 16x16 body: he is a
#: hunched man under a load, and cropping that to a player's box would take the
#: bundle off his back — which is most of what makes the silhouette his.
W, H = 22, 28

#: The three blocks stack at fixed rows. The load is drawn from row 0 and the
#: head starts three rows down, which is the whole point of the arrangement:
#: the sack clears the hood, so the silhouette is broken above the shoulders
#: rather than being one smooth dome like every other body in the game.
BUNDLE_TOP = 0
HEAD_TOP = 3
TORSO_TOP = 12
#: Arm overlays are authored against the shoulder line, not the frame top.
ARM_TOP = 8

Palette = dict[str, RGBA]
Art = list[str]


# --- palette ----------------------------------------------------------------
# A wanderer's kit against the forest palette. The load is warm burlap so the
# back of him separates from the front of him, and the scarf is the one
# saturated colour on the body.
#
# HE USED TO BE COLD GREY-BLUE WITH A HOLE FOR A FACE, and that was a mistake
# the shop could carry while he stood on a rim in the dark and cannot carry now
# that he is the thing in the middle of the room. A hooded figure whose face is
# six pixels of void reads as a threat — it is the same silhouette the game
# uses for everything that wants to kill you — and this is the one person in
# the run who does not. So the coat is warm brown, the hood is a HAT, and there
# is a face under it with two eyes in it. Nothing else about him changed.

PALETTE: Palette = {
    "o": rgb("#1a1410"),  # outline
    "k": rgb("#20302b"),  # coat, deep shade / the lining seen from inside
    "c": rgb("#31473e"),  # coat, mid — the mass of him
    "C": rgb("#456055"),  # coat, lit from the upper left
    "H": rgb("#5d7a69"),  # coat, rim highlight (sparingly)
    "h": rgb("#4a3324"),  # the hat's crown
    "N": rgb("#6b4b32"),  # the hat's brim, catching the light
    "f": rgb("#c9a07a"),  # his face
    "F": rgb("#a97f5c"),  # his face, in shade
    "e": rgb("#241c18"),  # eyes — two pixels, and they are the whole face
    "p": rgb("#8c3a3a"),  # scarf
    "P": rgb("#b45050"),  # scarf, lit
    "b": rgb("#6f6247"),  # burlap bundle
    "B": rgb("#8a7b59"),  # burlap, lit
    "r": rgb("#4c3f28"),  # rope
    "l": rgb("#4a3524"),  # leather strap / pouch
    "L": rgb("#8a6a34"),  # brass buckle
    "s": rgb("#c2926a"),  # bare hand
    "S": rgb("#6a5236"),  # fingerless glove
    "m": rgb("#6a6d78"),  # gunmetal
    "M": rgb("#8d919c"),  # gunmetal, lit
    "v": rgb("#33343d"),  # the vest under the coat
    "V": rgb("#43444f"),  # vest, lit
    "g": rgb("#4a6b53"),  # a bottle of something
    "w": rgb("#9aa3ab"),  # glass / cork highlight
    "t": rgb("#3a3e31"),  # trousers, under the open coat
    "x": rgb("#463c30"),  # boot
}

#: Coat pixels get a weave: a small deterministic value jitter so the mass of
#: him is not one flat swatch. Keyed to body coordinates, not frame
#: coordinates — grain that re-rolls when he breathes crawls like static.
#: Kept to one step either side: two steps at this size stops being cloth and
#: becomes dirt on the lens.
WEAVE = {"c": ("k", "C"), "v": ("k", "V"), "t": ("k", "t")}
WEAVE_RATE = 0.10


def _rows(*lines: str) -> Art:
    for line in lines:
        if len(line) != W:
            raise ValueError(f"row width {len(line)} != {W}: {line!r}")
    return list(lines)


# --- the load ---------------------------------------------------------------
# Drawn FIRST, behind everything: a stuffed sack over a rolled bedroll, roped
# down and riding high on his right shoulder. It is deliberately off-centre and
# it clears the hood. A load balanced on both shoulders reads as a backpack;
# one slung to a side, breaking the top of the silhouette, reads as everything
# he owns.

BUNDLE = _rows(
    "..obbbbbo.............",
    ".obBBBBBbo............",
    ".obBBBBBBbo...........",
    ".obBrrBBBbo...........",
    "obbBBBBBBBbo..........",
    "orrBBBBBBBBro.........",
    "obBBBBBBBBBbo.........",
    "obbBBBBBBBbbo.........",
    ".orrbbbbbbboo.........",
    "..obbbbbbbbo..........",
    "..obbbbbbbo...........",
    "...oooooooo...........",
)


# --- head -------------------------------------------------------------------
# A BRIMMED HAT AND A FACE UNDER IT. The brim is wider than the crown and wider
# than the head, which is what makes a hat read as a hat at eight pixels
# across, and the face below it is skin with two dark eyes and a scarf at the
# jaw. See the palette note: he is the one person in the run who is not trying
# to kill anybody, and the sprite has to say so before he has done anything.

HEAD_REST = _rows(
    ".......oooooooo.......",
    "......ohhhhhhhho......",
    "......ohhhhhhhho......",
    "....oNNNNNNNNNNNNo....",
    "......oFffffffFo......",
    "......oFfeffeffo......",
    "......oFfffffffo......",
    "......opppPPpppo......",
    ".......occcccco.......",
)

#: The eyes are shut: a blink, or his attention somewhere else. Two pixels of
#: difference, and it is the difference between a person and a mannequin.
HEAD_BLIND = _rows(
    ".......oooooooo.......",
    "......ohhhhhhhho......",
    "......ohhhhhhhho......",
    "....oNNNNNNNNNNNNo....",
    "......oFffffffFo......",
    "......oFfffffffo......",
    "......oFfffffffo......",
    "......opppPPpppo......",
    ".......occcccco.......",
)


# --- body -------------------------------------------------------------------
# Shoulders, the two leather lines where the load's straps come over them,
# pouches at the ribs, a belt, and an ankle-length coat down to the boots. The
# straps are the join between the front of him and the thing on his back.

TORSO_REST = _rows(
    "....oCCcccccccccco....",
    "...oCCclcccccclccko...",
    "...oCcclccccccLccko...",
    "...oCcclcccccclccko...",
    "...occllccccccllcko...",
    "...ocLllccccccllLko...",
    "...occccccccccccclo...",
    "...ollllllLllLllllo...",
    "....oCcccckkccccco....",
    "....oCcccckkccccco....",
    "....occccckkccccco....",
    "....occccckkccccco....",
    "....occccckkccccco....",
    "...occcccckkccccclo...",
    "...okk.kkkookkk.kko...",
    "......oxxo..oxxo......",
    "......oooo..oooo......",
)


# --- the coat, coming open --------------------------------------------------
# What is behind the coat is the pitch: a vest hung with stock — a pistol, two
# bottles, pouches — over trousers and boots. It is authored ONCE, at its
# widest, and the narrower stages are the CENTRE of it. That is not a shortcut:
# it means the stock does not shuffle as the coat opens, you simply see more of
# the same shelf, which is what opening a coat does.

#: Rows 13..25 of the body, at the width the wide pose shows.
OPEN_MID: tuple[str, ...] = (
    "vvvVvvvvVvvv",
    "vmMvvggvvllv",
    "vmMvvggvvlLv",
    "vvmvvggvvllv",
    "vvvvvVVvvvvv",
    "vvvvvvvvvvvv",
    "lllllLLlllll",
    "tttttttttttt",
    "tttttttttttt",
    "tttttoottttt",
    "tttttoottttt",
    "tttttoottttt",
    "tttto..otttt",
)

#: A panel seen from inside: the frame's outline, the lit outer edge, the coat,
#: then the lining in shadow against the vest. The hem row goes dark — it is
#: the bottom of a heavy coat, not a lit edge.
PANEL = ("Ccko", "okcC")
PANEL_HEM = ("kkko", "okkk")


def open_torso(mid_width: int, hands: bool = False) -> Art:
    """One stage of the coat opening, as a whole body.

    The stages are separate bodies rather than overlays because the SILHOUETTE
    is what changes: a panel painted over the closed coat would leave the
    closed coat's own edge showing through the gap it just opened.
    """
    crop = (len(OPEN_MID[0]) - mid_width) // 2
    pad = (W - (mid_width + 10)) // 2
    rows = [TORSO_REST[0]]  # the shoulders do not move
    for index, mid in enumerate(OPEN_MID):
        left, right = PANEL_HEM if index == len(OPEN_MID) - 1 else PANEL
        if hands and index == 0:
            left, right = "s" + left[1:], right[:3] + "s"
        rows.append(
            "." * pad + "o" + left + mid[crop:len(mid) - crop] + right + "o" + "." * pad
        )
    rows.extend(TORSO_REST[-2:])  # the boots are the boots
    return _rows(*rows)


TORSO_CRACK = open_torso(6)
TORSO_HALF = open_torso(8, hands=True)
TORSO_WIDE = open_torso(12, hands=True)


# --- arms -------------------------------------------------------------------
# Only the poses that leave the resting silhouette need art, and they are
# OVERLAYS: a raised arm changes nothing below the shoulder. Authored from
# `ARM_TOP` so the rows read against the shoulder line.
#
# It is his left arm (screen right) that does the work — the load is on the
# other side, and a man waving through his own bedroll reads as a mistake.

ARM_OUT = _rows(  # held out at chest height: "come here, then"
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "................occo..",
    "...............occSso.",
    "................ossso.",
    ".................ooo..",
    "......................",
)

ARM_UP = _rows(  # the wave itself, at head height
    "......................",
    "..................oso.",
    ".................osSso",
    ".................osSso",
    "................occSo.",
    "...............occco..",
    "................ooo...",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
)

ARM_REACH = _rows(  # a hand at the belt, taking the coin out
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "..............occo....",
    "..............ossco...",
    "..............osso....",
    "...............oo.....",
)

ARM_FLICK = _rows(  # the thumb goes; the hand stays open under the flight
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "......................",
    "...............occo...",
    "..............ossso...",
    "..............osso....",
    "...............oo.....",
    "......................",
)


# --- painting ---------------------------------------------------------------


def _weave(ch: str, bx: int, by: int) -> str:
    """Break a flat swatch into cloth, deterministically and in BODY space."""
    swatch = WEAVE.get(ch)
    if swatch is None:
        return ch
    roll = hash01(bx, by, 9173)
    if roll < WEAVE_RATE:
        return swatch[0]
    if roll > 1.0 - WEAVE_RATE:
        return swatch[1]
    return ch


def draw(img: Image.Image, art: Art, ox: int = 0, oy: int = 0, weave: bool = True) -> None:
    """Stamp one ASCII layer. '.' is transparent — layers are stacked, not merged."""
    px = img.load()
    for y, line in enumerate(art):
        for x, ch in enumerate(line):
            if ch == ".":
                continue
            if weave:
                ch = _weave(ch, x, y)
            tx, ty = x + ox, y + oy
            if 0 <= tx < W and 0 <= ty < H:
                px[tx, ty] = PALETTE[ch]


def draw_coin(img: Image.Image, cx: float, cy: float, spin: float) -> None:
    """The flipped coin: the game's own gold, narrowed by where it is in its turn.

    Two pixels by two, or one by two edge-on. It is not a coin sprite — it is
    the same ramp the HUD badge and the world pickup are made of, so the thing
    he pockets is the thing the player earns. No outline: a keyline round a
    2px disc leaves no disc, only the keyline.
    """
    px = img.load()
    x0, y0 = int(round(cx)), int(round(cy))
    columns = (0, 1) if spin > 0.45 else (0,)
    for row, colour in ((0, COIN_RAMP[3]), (1, COIN_RAMP[1])):
        for dx in columns:
            x, y = x0 + dx, y0 + row
            if 0 <= x < W and 0 <= y < H:
                px[x, y] = colour


def frame(
    *,
    torso: Art,
    head: Art = HEAD_REST,
    bob: int = 0,
    arm: Art | None = None,
    coin: tuple[float, float, float] | None = None,
) -> Image.Image:
    """One frame: load, body, head, arm — in that order, because it is depth.

    `bob` sinks the head and its load by a pixel. It sinks rather than lifts on
    purpose: lifting opens a one-pixel slit of nothing between the hood and the
    shoulders, and the hood is drawn last so sinking simply overlaps.
    """
    img = Image.new("RGBA", (W, H), TRANSPARENT)
    draw(img, BUNDLE, 0, BUNDLE_TOP + bob)
    draw(img, torso, 0, TORSO_TOP)
    draw(img, head, 0, HEAD_TOP + bob)
    if arm is not None:
        draw(img, arm, 0, ARM_TOP, weave=False)
    if coin is not None:
        draw_coin(img, *coin)
    return img


# --- clips ------------------------------------------------------------------
# A clip is a list of frames plus how fast it runs and whether it loops. The
# one-shots are written as STAGES with holds rather than as one frame per
# drawing: the hold on the open coat is what makes it a pose instead of a
# flicker, and the fast steps on either side are what make it a movement.

IDLE_FPS = 6
CLIP_FPS = 12


def clip_idle() -> list[Image.Image]:
    """Eight frames of standing there. Breath on a slow cycle, one blink.

    Frame 0 is the resting pose every one-shot has to start and end on, so it
    carries no bob and no blink.
    """
    breath = (0, 0, 1, 1, 1, 0, 0, 0)
    blink = (False, False, False, False, False, False, True, False)
    return [
        frame(torso=TORSO_REST, head=HEAD_BLIND if shut else HEAD_REST, bob=bob)
        for bob, shut in zip(breath, blink)
    ]


def clip_coat() -> list[Image.Image]:
    """The pitch. Open, hold on the stock, close.

    Asymmetric on purpose: it opens in three fast steps and closes in two, the
    way somebody who has done this a thousand times does it.
    """
    stages: list[tuple[Art, int, int]] = [
        (TORSO_REST, 0, 2),
        (TORSO_CRACK, 0, 2),
        (TORSO_HALF, 0, 2),
        (TORSO_WIDE, 0, 3),
        (TORSO_WIDE, 1, 3),
        (TORSO_WIDE, 0, 2),
        (TORSO_HALF, 0, 2),
        (TORSO_CRACK, 0, 1),
        (TORSO_REST, 0, 1),
    ]
    frames: list[Image.Image] = []
    for torso, bob, hold in stages:
        frames.extend(frame(torso=torso, bob=bob) for _ in range(hold))
    return frames


def clip_beckon() -> list[Image.Image]:
    """Noticing you: the arm comes up, waves twice, drops.

    The second wave is shorter than the first. Two identical waves read as a
    loop of one wave, which is the thing every idle animation must not do.
    """
    stages: list[tuple[Art | None, int]] = [
        (None, 1),
        (ARM_OUT, 2),
        (ARM_UP, 2),
        (ARM_OUT, 2),
        (ARM_UP, 2),
        (ARM_OUT, 1),
        (ARM_UP, 1),
        (ARM_OUT, 2),
        (None, 1),
    ]
    frames: list[Image.Image] = []
    for arm, hold in stages:
        frames.extend(
            frame(torso=TORSO_REST, head=HEAD_REST, arm=arm) for _ in range(hold)
        )
    return frames


#: Where the coin leaves the hand and how high it goes. Authored in frame
#: pixels because that is what the arc has to clear — the top of the hood.
COIN_FROM = (16.0, 15.0)
COIN_RISE = 7.0
COIN_FLIGHT = 8


def clip_coin() -> list[Image.Image]:
    """What he does while you make up your mind: flips a coin and pockets it.

    The flight is a parabola rather than a list of positions, and the spin is a
    cosine of the same parameter, so the coin is edge-on at the top of the arc
    where a real one is turning fastest.
    """
    frames: list[Image.Image] = [
        frame(torso=TORSO_REST),
        frame(torso=TORSO_REST, head=HEAD_BLIND, bob=1, arm=ARM_REACH),
        frame(torso=TORSO_REST, head=HEAD_BLIND, bob=1, arm=ARM_REACH),
    ]
    for step in range(COIN_FLIGHT):
        t = (step + 1) / (COIN_FLIGHT + 1)
        x = COIN_FROM[0] - 3.0 * t
        y = COIN_FROM[1] - COIN_RISE * 4.0 * t * (1.0 - t)
        spin = 1.0 - 2.0 * abs(0.5 - t) * 2.0
        frames.append(
            frame(
                torso=TORSO_REST,
                head=HEAD_BLIND,
                bob=1,
                arm=ARM_FLICK,
                coin=(x, y, clamp01(spin)),
            )
        )
    frames.append(frame(torso=TORSO_REST, head=HEAD_BLIND, bob=1, arm=ARM_REACH))
    frames.append(frame(torso=TORSO_REST, head=HEAD_BLIND, bob=1, arm=ARM_REACH))
    frames.append(frame(torso=TORSO_REST, head=HEAD_BLIND, bob=1))
    frames.append(frame(torso=TORSO_REST, bob=1))
    frames.append(frame(torso=TORSO_REST))
    return frames


# --- build ------------------------------------------------------------------


def _same(a: Image.Image, b: Image.Image) -> int:
    """Worst channel difference between two frames. Seams must be 0."""
    pa, pb = a.load(), b.load()
    worst = 0
    for y in range(H):
        for x in range(W):
            for ca, cb in zip(pa[x, y], pb[x, y]):
                worst = max(worst, abs(ca - cb))
    return worst


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "merchant"
    out_dir.mkdir(parents=True, exist_ok=True)

    idle = clip_idle()
    oneshots = {"coat": clip_coat(), "beckon": clip_beckon(), "coin": clip_coin()}

    # THE SEAM CHECK. The client cuts from the loop into a one-shot and back
    # with no blend, so both ends of every one-shot have to BE idle frame 0.
    rest = idle[0]
    for name, frames in oneshots.items():
        for edge, index in (("first", 0), ("last", -1)):
            diff = _same(rest, frames[index])
            print(f"  seam {name}.{edge} -> idle[0]: {diff}")
            if diff != 0:
                raise SystemExit(
                    f"{name} {edge} frame is not the resting pose (diff {diff})"
                )

    clips: dict[str, dict] = {}
    for name, frames, fps, loop in (
        ("idle", idle, IDLE_FPS, True),
        ("coat", oneshots["coat"], CLIP_FPS, False),
        ("beckon", oneshots["beckon"], CLIP_FPS, False),
        ("coin", oneshots["coin"], CLIP_FPS, False),
    ):
        pack(frames, W, H).save(out_dir / f"{name}.png")
        clips[name] = {
            "file": f"{name}.png",
            "frames": len(frames),
            "fps": fps,
            "loop": loop,
        }

    manifest = {
        "name": "merchant",
        "frameWidth": W,
        "frameHeight": H,
        # He is bottom-anchored like every other standing thing, and depth-sorts
        # with the party: a player may walk behind him.
        "anchor": {"x": 0.5, "y": 1.0},
        "clips": clips,
        # The three the client rolls between while the loop runs. Order is not
        # a priority — the client picks one at random when the gap elapses.
        "randomClips": ["coat", "beckon", "coin"],
        # Seconds between one-shots. A shopkeeper who performs every two
        # seconds is a cutscene; one who never moves is a statue.
        "randomGap": [4.0, 11.0],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"wrote {out_dir}: frame {W}x{H}, "
        + ", ".join(f"{name} {spec['frames']}f" for name, spec in clips.items())
    )
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="",
                    help="write a scaled contact sheet HERE (outside the tree) "
                         "for eyeballing the art; never into assets/")
    ap.add_argument("--preview-scale", type=int, default=8)
    args = ap.parse_args()
    out_dir = build(args)
    if args.preview:
        _preview(out_dir, Path(args.preview), args.preview_scale)


def _preview(out_dir: Path, path: Path, scale: int) -> None:
    """A scaled contact sheet of every clip. Not shipped — a look at the art."""
    manifest = json.loads((out_dir / "manifest.json").read_text())
    strips = [Image.open(out_dir / spec["file"]) for spec in manifest["clips"].values()]
    width = max(strip.width for strip in strips)
    sheet = Image.new("RGBA", (width, sum(s.height for s in strips)), (40, 30, 46, 255))
    y = 0
    for strip in strips:
        sheet.paste(strip, (0, y), strip)
        y += strip.height
    sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
