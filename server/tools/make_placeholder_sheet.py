#!/usr/bin/env python3
"""Generate a placeholder RAW sprite sheet in the project's source format.

The real project will use AI-generated pixel art, but the raw format is fixed:
a 3x3 grid of frames on a solid magenta (#FF00FF) background.

Characters:
  rows: 0 = facing down, 1 = facing side (right), 2 = facing up
  cols: 0 = step A, 1 = idle/stand, 2 = step B

Items (coin, …):
  rows: same art repeated (no facing)
  cols: spin / idle frames

Gear (backpack, …):
  rows: down / side / up, same as a character
  cols: walk frames (col 1 idle)
  Art is authored on the processed 16x16 player grid so an overlay composites
  without a second transform. Neutral greys — the client multiply-tints them
  with the wearer's colour.

One art set per run. `--entity` picks it (defaults to `--name`). Creatures,
items and gear are all data tables, so adding any of them is not a code change.

Output: assets/raw/<name>.png  (consumed by tools/process_sprites.py)

Usage:
    python tools/make_placeholder_sheet.py --name player
    python tools/make_placeholder_sheet.py --name zombie
    python tools/make_placeholder_sheet.py --name coin
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAGENTA = (255, 0, 255, 255)
VIEWS = ("down", "side", "up")

Palette = dict[str, tuple[int, int, int, int]]
Art = list[str]


@dataclass(frozen=True)
class Entity:
    """One creature: a colour key plus stacked head / torso / legs art.

    All art is 12 columns wide, '.' = background. `torso` is per-view so a
    creature can hold its arms differently depending on where it faces; the
    three `legs` frames are the animation, index 1 being the neutral stance.
    """

    palette: Palette
    head: dict[str, Art]
    torso: dict[str, Art]
    legs: list[Art]

    def frame(self, view: str, index: int) -> Art:
        return self.head[view] + self.torso[view] + self.legs[index]


PLAYER_PALETTE: Palette = {
    "o": (28, 26, 38, 255),     # outline
    "d": (96, 100, 118, 255),   # dark shade
    "b": (232, 232, 240, 255),  # body (this is what gets tinted in-game)
    "s": (238, 202, 172, 255),  # skin
    "e": (36, 34, 46, 255),     # eye
}

PLAYER_HEAD = {
    "down": [
        "....oooo....",
        "...odddddo..",
        "...ossssso..",
        "...oesesseo.",
        "...ossssso..",
        "....ooooo...",
    ],
    "side": [
        "....oooo....",
        "...oddddddo.",
        "...osssssso.",
        "...osssesso.",
        "...osssssso.",
        "....ooooo...",
    ],
    "up": [
        "....oooo....",
        "...odddddo..",
        "...oddddddo.",
        "...oddddddo.",
        "...oddddddo.",
        "....ooooo...",
    ],
}

PLAYER_TORSO = [
    "...obbbbo...",
    "..obbbbbbo..",
    "..obbbbbbo..",
    "..obbbbbbo..",
    "...obbbbo...",
]

PLAYER = Entity(
    palette=PLAYER_PALETTE,
    head=PLAYER_HEAD,
    torso={view: PLAYER_TORSO for view in VIEWS},
    legs=[
        ["..obb..bbo..", "..od....do..", "..oo....oo.."],
        ["...ob..bo...", "...od..do...", "...oo..oo..."],
        ["..obb..bbo..", "...od..do...", "..oo....oo.."],
    ],
)

ZOMBIE_PALETTE: Palette = {
    "o": (22, 30, 26, 255),     # outline
    "d": (54, 72, 50, 255),     # matted hair / dark shade
    "b": (118, 122, 96, 255),   # body (torn shirt)
    "s": (138, 176, 106, 255),  # rotten skin
    "e": (30, 38, 26, 255),     # sunken eye socket
    "r": (150, 44, 52, 255),    # wound / open jaw
}

ZOMBIE_HEAD = {
    # Lolling head: bug eyes and a hanging jaw.
    "down": [
        "....oooo....",
        "...odddddo..",
        "...osssssso.",
        "...oeesseeo.",  # 2px eyes: 1px washes out in the downscale to 16x16
        "...osrrrsso.",
        "....ooooo...",
    ],
    "side": [
        "....oooo....",
        "...oddddddo.",
        "...osssssso.",
        "...osssseeo.",
        "...ossrrrro.",
        "....ooooo...",
    ],
    "up": [
        "....oooo....",
        "...odddddo..",
        "...oddddddo.",
        "...oddrdddo.",  # exposed wound on the back of the skull
        "...oddddddo.",
        "....ooooo...",
    ],
}

ZOMBIE = Entity(
    palette=ZOMBIE_PALETTE,
    head=ZOMBIE_HEAD,
    torso={
        # Arms reach out towards whatever the zombie is facing.
        "down": [
            "...obbbbo...",
            "..obbbbbbo..",
            ".osbbbbbbso.",
            ".osobbbboso.",
            "...obbbbo...",
        ],
        "side": [
            "...obbbbo...",
            "..obbbbbbo..",
            "..obbbbbosso",
            "..obbbbbbo..",
            "...obbbbo...",
        ],
        "up": [
            "...obbbbo...",
            "..obbbbbbo..",
            ".oobbbbbboo.",
            "..obbbbbbo..",
            "...obbbbo...",
        ],
    },
    # Shamble: one leg steps, the other drags (wider foot) behind it.
    legs=[
        ["..obb.bbo...", "..od...do...", "..ooo..oo..."],
        ["...ob..bbo..", "...od..ddo..", "...oo..ooo.."],
        ["..obb..bo...", "..od...do...", "..oo..ooo..."],
    ],
)

ENTITIES = {"player": PLAYER, "zombie": ZOMBIE}

# ---------------------------------------------------------------------------
# Items — pickups use the same 3x3 raw format so process_sprites.py eats them
# unchanged. Columns are spin frames; every row is the same art (no facing).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One pickup: palette + 3 spin frames (cols 0..2 of the raw sheet)."""

    palette: Palette
    frames: list[Art]


COIN_PALETTE: Palette = {
    "o": (72, 42, 18, 255),      # outline
    "d": (160, 90, 28, 255),     # dark gold / rim
    "g": (242, 165, 65, 255),    # body — matches --ink-accent
    "h": (255, 214, 120, 255),   # highlight
    "s": (255, 245, 200, 255),   # shine
}

# Y-axis spin: face → three-quarter → edge. Process with `--uniform` so every
# frame shares one crop box and stays the same on-screen size while rotating.
COIN = Item(
    palette=COIN_PALETTE,
    frames=[
        # Face-on — full disc, bright face.
        [
            "..oooooo..",
            ".odggggdo.",
            "odghsshgdo",
            "oggssssggo",
            "odghsshgdo",
            ".odggggdo.",
            "..oooooo..",
        ],
        # Three-quarter — body foreshortens, shine slides to the rim.
        [
            "...oooo...",
            "..odggdo..",
            ".odghhgdo.",
            ".oggssggo.",
            ".odghhgdo.",
            "..odggdo..",
            "...oooo...",
        ],
        # Edge-on — thin slab, rim gleam. Same height as the face disc.
        [
            "....oo....",
            "...oddo...",
            "...oggo...",
            "...ohso...",
            "...oggo...",
            "...oddo...",
            "....oo....",
        ],
    ],
)

ITEMS = {"coin": COIN}


# ---------------------------------------------------------------------------
# Gear — equipment overlays. Same 3x3 raw grid as a character (down / side /
# up), but the art is a 16x16 frame registered to the processed player sheet
# so it composites on the body with no extra offset. Side faces RIGHT; the
# processor mirrors it to produce left.
#
# GREYSCALE ON PURPOSE. The client multiply-tints the sheet with the wearer's
# colour, the same way it tints the player's own body. A hue baked in here
# would be one pack per roster swatch, and would not match.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gear:
    """One overlay: palette + three view poses on the processed player grid."""

    palette: Palette
    views: dict[str, Art]


# Cool neutrals, a step darker than the player's shirt (`b` = e8e8f0) so the
# pack still reads after the same multiply. Outline matches the player so the
# two silhouettes share a keyline.
BACKPACK_PALETTE: Palette = {
    "o": (28, 26, 38, 255),      # outline
    "d": (84, 86, 98, 255),      # shade
    "b": (176, 178, 190, 255),   # body — the tint target
    "h": (214, 216, 226, 255),   # flap / highlight
    "k": (130, 132, 144, 255),   # buckle
}

# 16 columns, one char per processed pixel. Empty rows pad to the frame so
# `--exact` keeps this placement against the player's torso (rows 6–11).
BACKPACK_DOWN: Art = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "......o..o......",
    ".....od..do.....",
    "......o..o......",
    "......o..o......",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
]

# Facing right: the pack sits on the LEFT (their back) and sticks out 2px.
BACKPACK_SIDE: Art = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "....o...........",
    "...ooo..........",
    "..obbbo.........",
    "..ohhbo.........",
    "..obkbo.........",
    "..oddbo.........",
    "...ooo..........",
    "................",
    "................",
    "................",
    "................",
]

# Facing away: the pack is the thing you see. Centred on the torso.
BACKPACK_UP: Art = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    ".....oooooo.....",
    "....obbbbbbo....",
    "....ohhhhhho....",
    "....obbkkbbo....",
    "....odbbbbdo....",
    ".....oooooo.....",
    "................",
    "................",
    "................",
    "................",
]

BACKPACK = Gear(
    palette=BACKPACK_PALETTE,
    views={"down": BACKPACK_DOWN, "side": BACKPACK_SIDE, "up": BACKPACK_UP},
)

GEAR = {"backpack": BACKPACK}


def render_cell(
    palette: Palette, rows: Art, cell: int, scale: int, *, center: bool = False
) -> Image.Image:
    img = Image.new("RGBA", (cell, cell), MAGENTA)
    px = img.load()
    art_w = len(rows[0]) * scale
    art_h = len(rows) * scale
    ox = (cell - art_w) // 2
    # Characters plant feet near the bottom; pickups sit centred in the cell.
    oy = (cell - art_h) // 2 if center else cell - art_h - scale
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            color = palette[ch]
            for sy in range(scale):
                for sx in range(scale):
                    px[ox + x * scale + sx, oy + y * scale + sy] = color
    return img


def write_gear(gear: Gear, path: Path) -> None:
    """3x3 raw sheet, one processed-pixel per char, top-left of a 16x16 cell."""
    cell = 16
    sheet = Image.new("RGBA", (cell * 3, cell * 3), MAGENTA)
    for row, view in enumerate(VIEWS):
        cell_img = Image.new("RGBA", (cell, cell), MAGENTA)
        px = cell_img.load()
        for y, line in enumerate(gear.views[view]):
            for x, ch in enumerate(line):
                if ch == ".":
                    continue
                px[x, y] = gear.palette[ch]
        for col in range(3):
            sheet.paste(cell_img, (col * cell, row * cell))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height})")


def write_sheet(frames: list[Art], palette: Palette, cell: int, scale: int, path: Path) -> None:
    sheet = Image.new("RGBA", (cell * 3, cell * 3), MAGENTA)
    for row in range(3):
        for col, art in enumerate(frames):
            sheet.paste(
                render_cell(palette, art, cell, scale, center=True),
                (col * cell, row * cell),
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    keys = (*ENTITIES, *ITEMS, *GEAR)
    ap.add_argument("--entity", choices=keys, default=None,
                    help="art set to draw (defaults to --name)")
    ap.add_argument("--cell", type=int, default=32, help="raw cell size in px")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[2] / "assets" / "raw"),
    )
    args = ap.parse_args()

    key = args.entity or args.name
    out = Path(args.out_dir) / f"{args.name}.png"

    if key in ITEMS:
        item = ITEMS[key]
        write_sheet(item.frames, item.palette, args.cell, args.scale, out)
        return

    if key in GEAR:
        # Gear is authored on the processed 16x16 grid. Forcing the cell here
        # means `--exact` in process_sprites.py keeps that registration.
        write_gear(GEAR[key], out)
        return

    if key not in ENTITIES:
        raise SystemExit(
            f"no art set for '{key}'; pass --entity {'|'.join(keys)}"
        )
    entity = ENTITIES[key]
    sheet = Image.new("RGBA", (args.cell * 3, args.cell * 3), MAGENTA)
    for row, view in enumerate(VIEWS):
        for col in range(3):
            sheet.paste(
                render_cell(entity.palette, entity.frame(view, col), args.cell, args.scale),
                (col * args.cell, row * args.cell),
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out)
    print(f"wrote {out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
