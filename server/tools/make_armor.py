#!/usr/bin/env python3
"""Asset pipeline: WHAT A BODY IS WEARING — twelve overlays on the player grid.

    assets/raw/armor-<slot>-<material>.png       3x3, magenta-keyed
    assets/processed/armor-<slot>-<material>/    sheet.png + manifest.json

Twelve sheets, three shapes, four materials, and one command: this script
writes the raw art AND runs it through `process_sprites` itself, because
twelve pairs of commands in `AGENTS.md` is a list nobody keeps in step.

WHY THIS IS AN OVERLAY AND NOT A SECOND PLAYER SHEET
====================================================
The game already had a way to put something on a body: `DrawableEntity.gear`,
which is how a backpack rides a player and how a cap rides a zombie. It is a
sheet registered to the same 16x16 grid, drawn in the same facing and the same
walk column, one draw call after the body. Armour is exactly that and nothing
more, so it uses exactly that — a second mechanism for putting things on
people would be a second thing to keep in step with the walk cycle, and the
walk cycle is the one thing on this sprite that must never disagree with
itself.

WHERE THE PIXELS GO IS MEASURED, NOT GUESSED
The bands below are the PLAYER SHEET'S OWN, read off the art rather than
copied out of `make_player.py`'s anatomy constants: head rows 1-8, torso 9-12,
legs 13-15, and the columns each of those actually occupies on each facing.
That is the difference between a helmet and a helmet floating a pixel above a
head, and it is not a thing a screenshot at 16px will tell you — it is a thing
you notice three zones later when somebody says the sprite "looks wrong".

ONE POSE BLOCK, DELIBERATELY. The player sheet carries two (walk, and a
holding pose with the weapon arm raised); these carry one, like the backpack,
and are drawn off the walk block in both. That is correct rather than lazy:
the hold pose moves ARMS, and nothing here is on an arm. A helmet, a
breastplate over the coat's centre and a pair of greaves sit on the three
parts of this figure that are identical between the two blocks, so a second
block would be twelve more sheets that are pixel-for-pixel the first twelve.

SLOT SETS THE SHAPE, MATERIAL SETS THE COLOUR
The same split `server/app/armor.py` makes about the numbers and
`make_loot.py` makes about the icons. Four helmets are four RUNGS OF ONE
LADDER, not four objects: the player already knows it is a helmet, and the
only question is whether it is better than theirs. A ladder whose rungs are
one shape in four colours can be ordered at a glance; one whose rungs are four
shapes cannot. (This is the exact opposite of the creature rule in
`make_zombie.py`, where three variants must be three SILHOUETTES — because
there the question is "what is that", and here it is not.)

ARMOUR IS NOT TINTED. Every ramp here is baked. The backpack is greyscale so
the client can multiply the wearer's identity colour through it — a pack is
issued kit and wearing your own colour is the point of it — and a steel plate
is the opposite: its colour IS its material, which is the whole ladder. The
client knows the difference because the drawable says so per layer
(`GearLayer.tint`), not because of anything about this file's names.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_loot as loot  # noqa: E402
import process_sprites  # noqa: E402
from make_textures import Ramp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "assets" / "raw"

MAGENTA = (255, 0, 255, 255)
TILE = 16
#: down / side / up, in the order `process_sprites.SOURCE_ROWS` expects. The
#: side row is authored facing RIGHT and mirrored for left, like every other
#: sheet in this pipeline.
VIEWS = ("down", "side", "up")

# --- the materials -----------------------------------------------------------
#
# IMPORTED, NOT RE-DERIVED. These are the same four ramps `make_loot.py` paints
# the twelve armour ICONS with, so the plate on the ground and the plate on the
# body are the same colour by construction rather than by two people typing the
# same hue. A copied ramp is a ramp that drifts, and this pipeline has already
# been bitten by exactly that once (see `make_loot`'s note on `paint_rows`).
MATERIALS: dict[str, Ramp] = {
    "cloth": loot.CLOTH,
    "leather": loot.LEATHER,
    "steel": loot.METAL,
    "kevlar": loot.OLIVE,
}

#: Which ramp step each letter paints. Three steps and no more: at four pixels
#: of helmet there is no room for a gradient, and S6's rule that interior form
#: is a value STEP rather than a line is only affordable if there are few
#: enough steps for each to mean something.
#:
#:     @  the crest: the top plane, one step above the fill
#:     #  the fill: the material's own step
#:     -  the shade: the underside and the rim it sits on
STEPS: dict[str, int] = {"@": 4, "#": 3, "-": 1}

Art = list[str]

# --- the shapes --------------------------------------------------------------
#
# Sixteen rows of sixteen, registered on the player's own bands. `.` is
# transparent; everything else is a step in `STEPS`.
#
# THE BANDS, read off `assets/processed/player/sheet.png`:
#
#     rows 1-8    head        cols 3-12 (row 1 is 4-11, the rounded crown)
#     rows 9-12   torso       cols 3-12 facing the camera, 4-12 in profile
#     rows 13-15  legs        cols 5-10 facing the camera, 6-9 in profile
#
# Each piece takes the TOP of its band and leaves the bottom showing. A helmet
# that reached the chin would delete the face, a breastplate that reached the
# waist would delete the coat, and greaves that reached the floor would delete
# the boots — and the face, the coat and the boots are the character. Armour
# is worn OVER somebody, and the somebody has to survive it.

#: The helmet: THREE ROWS OFF THE TOP OF THE HEAD, and not one more.
#:
#: The first cut of this took five rows and a rim, which on a figure whose
#: head is seven rows of fifteen is not a helmet — it is a head replaced by a
#: box. The face went, and with it the character: what was left was a slab
#: walking around. THE SOMEBODY HAS TO SURVIVE THE ARMOUR.
#:
#: So: the crown (following the head's own contour, cols 4-11 on row 1 and
#: 3-12 below it), one row of fill, and a dark brim above the eyes. Three
#: rows, and the face underneath is untouched. The brim is the piece that
#: does the work — a cap of two rows is a haircut, and the dark line under it
#: is what says "strapped on".
HEAD: dict[str, Art] = {
    "down": [
        "................",
        "....@@@@@@@@....",
        "...##########...",
        "...----------...",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    # In profile the brim runs on past the temple and a cheek piece drops one
    # row at the back. That single pixel is the only depth this shape can
    # afford, and without it a helmet seen from the side is a bowl.
    "side": [
        "................",
        "....@@@@@@@@....",
        "...##########...",
        "...----------...",
        "...--...........",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "up": [
        "................",
        "....@@@@@@@@....",
        "...##########...",
        "...##########...",
        "...----------...",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
}

#: The cuirass: SHOULDERS, then a narrower plate, then a dark hem.
#:
#: THE TOP ROW IS WIDER THAN THE TWO UNDER IT, and that one pixel at each end
#: is the whole shape. Three rows of equal width across a torso is a STRIPE —
#: it reads as the character's shirt having a band on it — and a stripe is
#: what the first cut of this was. Flaring the top row out to the torso's full
#: span turns it into a T: pauldrons over a breastplate, which is a
#: silhouette, and silhouette is what carries identity at this size (S15).
#:
#: Under the shoulders it is inset one column each side, so the coat's own
#: edge and the arms survive; row 12, the coat's bottom, is left bare
#: entirely. A plate ENDS, and where it ends you can see what is under it.
#:
#: The seam is off centre for the reason nothing on the loot sheet is
#: bilaterally symmetric — a symmetric mark at this size reads as a UI glyph
#: — and because that is also how a cuirass is laced.
BODY: dict[str, Art] = {
    "down": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "...@@@@@@@@@@...",
        "....###-####....",
        "....--------....",
        "................",
        "................",
        "................",
        "................",
    ],
    "side": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "....@@@@@@@@@...",
        ".....####-##....",
        ".....-------....",
        "................",
        "................",
        "................",
        "................",
    ],
    "up": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "...@@@@@@@@@@...",
        "....########....",
        "....--------....",
        "................",
        "................",
        "................",
        "................",
    ],
}

#: The greaves: two rows down the shin, and THE BOOT IS LEFT ALONE.
#:
#: Row 15 is what the contact shadow is drawn under and what the walk lands
#: on. A plate over it is armour standing on the floor rather than a person
#: wearing armour — and the boots are one of the three things on this sprite
#: that make it a character. Crest, then a dark cuff.
LEGS: dict[str, Art] = {
    "down": [
        *["................" for _ in range(13)],
        ".....@@@@@@.....",
        ".....------.....",
        "................",
    ],
    "side": [
        *["................" for _ in range(13)],
        "......@@@@......",
        "......----......",
        "................",
    ],
    "up": [
        *["................" for _ in range(13)],
        ".....@@@@@@.....",
        ".....------.....",
        "................",
    ],
}

SHAPES: dict[str, dict[str, Art]] = {"head": HEAD, "body": BODY, "legs": LEGS}


def _check(key: str, art: dict[str, Art]) -> None:
    """The grid the whole overlay contract rests on.

    A sheet that is not exactly 16x16 per view composites at an offset, and at
    this size an offset of one pixel is a helmet hovering over a head. It is
    also invisible in a screenshot — the piece still looks like a helmet, it
    is just not on anybody — which is precisely the class of mistake a build
    check is for.
    """
    for view, rows in art.items():
        if len(rows) != TILE:
            raise ValueError(f"{key}/{view}: {len(rows)} rows, the grid is {TILE}")
        for y, row in enumerate(rows):
            if len(row) != TILE:
                raise ValueError(f"{key}/{view}: row {y} is {len(row)} wide, the grid is {TILE}")
            for ch in row:
                if ch != "." and ch not in STEPS:
                    raise ValueError(f"{key}/{view}: row {y} has '{ch}', not in the alphabet")


def _cell(art: Art, ramp: Ramp) -> Image.Image:
    """One 16x16 frame on magenta, ready for `process_sprites --exact`."""
    img = Image.new("RGBA", (TILE, TILE), MAGENTA)
    px = img.load()
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px[x, y] = ramp[min(STEPS[ch], len(ramp) - 1)]
    return img


def _raw_sheet(art: dict[str, Art], ramp: Ramp) -> Image.Image:
    """The 3x3 raw sheet: three views down the rows, one pose across the columns.

    THE THREE COLUMNS ARE IDENTICAL, exactly as the backpack's are. An overlay
    does not animate — the body under it does, and the walk column the client
    picks is what puts the plate on the right frame of the stride. Three copies
    of one drawing is what lets `blitGear` use the body's own column index
    without a special case for gear that has fewer frames than the body.
    """
    sheet = Image.new("RGBA", (TILE * 3, TILE * len(VIEWS)), MAGENTA)
    for row, view in enumerate(VIEWS):
        cell = _cell(art[view], ramp)
        for col in range(3):
            sheet.paste(cell, (col * TILE, row * TILE))
    return sheet


def build(args) -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for slot, art in SHAPES.items():
        _check(slot, art)
        for material, ramp in MATERIALS.items():
            name = f"armor-{slot}-{material}"
            raw = RAW_DIR / f"{name}.png"
            _raw_sheet(art, ramp).save(raw)
            # Straight through the same door the backpack and every zombie
            # accessory go through: authored at the target grid, so no crop,
            # no rescale, no re-centre — the artist's placement IS the
            # registration.
            process_sprites.process(
                SimpleNamespace(
                    name=name,
                    tile=args.tile,
                    width=0,
                    height=0,
                    tolerance=40,
                    no_hue_key=False,
                    side_facing="right",
                    filter="auto",
                    alpha_threshold=128,
                    bottom_pad=0,
                    exact=True,
                    uniform=False,
                )
            )
            written.append(raw)
    print(f"wrote {len(written)} armour overlays ({len(SHAPES)} shapes x {len(MATERIALS)} materials)")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=TILE)
    build(ap.parse_args())


if __name__ == "__main__":
    main()
