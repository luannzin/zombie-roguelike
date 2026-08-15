#!/usr/bin/env python3
"""Generate a placeholder RAW sprite sheet in the project's source format.

The real project will use AI-generated pixel art, but the raw format is fixed:
a 3x3 grid of frames on a solid magenta (#FF00FF) background.

Characters:
  rows: 0 = facing down, 1 = facing side (right), 2 = facing up
  cols: 0 = step A, 1 = idle/stand, 2 = step B

Gear (backpack, zhat-*, zcloth-*, …):
  rows: down / side / up, same as a character
  cols: walk frames (col 1 idle)
  Art is authored on the processed 16x16 player grid so an overlay composites
  without a second transform. The backpack is greyscale — the client
  multiply-tints it with the wearer's colour. Zombie hats and clothes bake
  their colour; enemies are drawn untinted.

Exact creatures (zombie, zombie-husk, zombie-brute) use that same 16x16
grid so accessories register. Process them with `--exact`.

One art set per run. `--entity` picks it (defaults to `--name`). Creatures
and gear are data tables, so adding either is not a code change. The world
coin is `make_coin.py` — generated, no raw stage.

Output: assets/raw/<name>.png  (consumed by tools/process_sprites.py)

Usage:
    python tools/make_placeholder_sheet.py --name player
    python tools/make_placeholder_sheet.py --name zombie
    python tools/make_placeholder_sheet.py --name zombie-husk
    python tools/make_placeholder_sheet.py --name zhat-cap
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

ENTITIES = {"player": PLAYER}

# ---------------------------------------------------------------------------
# Exact creatures — authored on the processed 16x16 player grid so overlays
# (hats, clothes) composite the way the backpack does: no crop, no rescale.
# One pad row, 6 head, 5 torso, 3 legs, one pad row. Hats own rows 0–4;
# clothes own rows 7–11. Variants share the silhouette and differ in paint
# and pose, so one accessory sheet fits all three.
# ---------------------------------------------------------------------------

EXACT_W = 16
PAD = ["." * EXACT_W]


@dataclass(frozen=True)
class ExactCreature:
    """One 16x16-authored creature: palette + head / torso / walk legs."""

    palette: Palette
    head: dict[str, Art]
    torso: dict[str, Art]
    legs: list[Art]

    def frame(self, view: str, index: int) -> Art:
        return PAD + self.head[view] + self.torso[view] + self.legs[index] + PAD


def _rows(*lines: str) -> Art:
    for line in lines:
        if len(line) != EXACT_W:
            raise ValueError(f"row width {len(line)} != {EXACT_W}: {line!r}")
    return list(lines)


# Walker — classic rot. Green skin, torn shirt, hanging jaw, a slight reach.
WALKER_PALETTE: Palette = {
    "o": (22, 30, 26, 255),
    "d": (46, 60, 42, 255),
    "b": (108, 112, 90, 255),
    "k": (84, 88, 70, 255),
    "s": (134, 170, 104, 255),
    "h": (158, 186, 122, 255),
    "e": (28, 36, 24, 255),
    "r": (148, 42, 50, 255),
}

WALKER_HEAD = {
    "down": _rows(
        "......oooo......",
        "....oddddddo....",
        "....osssssso....",
        "....oeesseeo....",
        "....osrrrrso....",
        ".....oooooo.....",
    ),
    "side": _rows(
        ".......oooo.....",
        ".....odddddo....",
        ".....ossssso....",
        ".....osseseo....",
        ".....ossrrro....",
        "......ooooo.....",
    ),
    "up": _rows(
        "......oooo......",
        "....oddddddo....",
        "....oddddddo....",
        "....oddrdddo....",
        "....oddddddo....",
        ".....oooooo.....",
    ),
}

WALKER_TORSO = {
    "down": _rows(
        ".....obbbbo.....",
        "....obkbbbbo....",
        "...osbbbbbbso...",
        "...osobbbboso...",
        ".....obbbbo.....",
    ),
    "side": _rows(
        ".....obbbbo.....",
        "....obbbbbbo....",
        "....obbbbosso...",
        "....obkbbbbo....",
        ".....obbbbo.....",
    ),
    "up": _rows(
        ".....obbbbo.....",
        "....obbbbbbo....",
        "....obkbbbbo....",
        "....obbbbbbo....",
        ".....obbbbo.....",
    ),
}

# Shared shamble: one foot steps, the other drags a wider print.
SHAMBLE_LEGS = [
    _rows("....obb..bo.....", "....od...do.....", "....ooo..oo....."),
    _rows(".....ob..bo.....", ".....od..do.....", ".....oo..oo....."),
    _rows(".....ob..bbo....", ".....od...do....", ".....oo..ooo...."),
]

WALKER = ExactCreature(
    palette=WALKER_PALETTE,
    head=WALKER_HEAD,
    torso=WALKER_TORSO,
    legs=SHAMBLE_LEGS,
)

# Husk — spent. Ashen skin, almost no shirt, skull showing, arms hang.
HUSK_PALETTE: Palette = {
    "o": (28, 28, 30, 255),
    "d": (58, 56, 54, 255),
    "b": (98, 96, 88, 255),
    "k": (76, 74, 68, 255),
    "s": (154, 156, 132, 255),
    "h": (176, 178, 154, 255),
    "e": (36, 34, 32, 255),
    "r": (120, 48, 52, 255),
}

HUSK_HEAD = {
    "down": _rows(
        "......oooo......",
        "....oddddddo....",
        "....osssssso....",
        "....oessoeso....",
        "....os.rr.so....",
        ".....oooooo.....",
    ),
    "side": _rows(
        ".......oooo.....",
        ".....odddddo....",
        ".....ossssso....",
        ".....os.sseo....",
        ".....os.rrro....",
        "......ooooo.....",
    ),
    "up": _rows(
        "......oooo......",
        "....oddddddo....",
        "....oddddddo....",
        "....odd.dddo....",
        "....oddddddo....",
        ".....oooooo.....",
    ),
}

HUSK_TORSO = {
    "down": _rows(
        ".....osssso.....",
        "....osbbbso.....",
        "....osssssso....",
        "....oskkkso.....",
        ".....osssso.....",
    ),
    "side": _rows(
        ".....osssso.....",
        "....osbbbso.....",
        "....osssssso....",
        "....oskkkso.....",
        ".....osssso.....",
    ),
    "up": _rows(
        ".....osssso.....",
        "....osbbbso.....",
        "....oskkkso.....",
        "....osbbbso.....",
        ".....osssso.....",
    ),
}

HUSK = ExactCreature(
    palette=HUSK_PALETTE,
    head=HUSK_HEAD,
    torso=HUSK_TORSO,
    legs=SHAMBLE_LEGS,
)

# Brute — heavier. Jaundiced skin, stained shirt, thick brow, arms out.
BRUTE_PALETTE: Palette = {
    "o": (32, 28, 22, 255),
    "d": (62, 52, 36, 255),
    "b": (88, 78, 58, 255),
    "k": (68, 60, 44, 255),
    "s": (168, 164, 88, 255),
    "h": (188, 180, 110, 255),
    "e": (36, 30, 22, 255),
    "r": (140, 40, 44, 255),
}

BRUTE_HEAD = {
    "down": _rows(
        "......oooo......",
        "....oddddddo....",
        "....odssssdo....",
        "....oesesseo....",
        "....osrrrrso....",
        ".....oooooo.....",
    ),
    "side": _rows(
        ".......oooo.....",
        ".....odddddo....",
        ".....odsssdo....",
        ".....osseseo....",
        ".....osrrrro....",
        "......ooooo.....",
    ),
    "up": _rows(
        "......oooo......",
        "....oddddddo....",
        "....oddddddo....",
        "....oddddddo....",
        "....oddddddo....",
        ".....oooooo.....",
    ),
}

BRUTE_TORSO = {
    "down": _rows(
        ".....obbbbo.....",
        "....obkbbbbo....",
        "...osbbbbbbso...",
        "...osbbbbbbso...",
        ".....obbbbo.....",
    ),
    "side": _rows(
        ".....obbbbo.....",
        "....obbbbbbo....",
        "....obbbbosso...",
        "....obkbbbbo....",
        ".....obbbbo.....",
    ),
    "up": _rows(
        ".....obbbbo.....",
        "....obbbbbbo....",
        "....obkbbbbo....",
        "....obbbbbbo....",
        ".....obbbbo.....",
    ),
}

BRUTE = ExactCreature(
    palette=BRUTE_PALETTE,
    head=BRUTE_HEAD,
    torso=BRUTE_TORSO,
    legs=SHAMBLE_LEGS,
)

EXACT = {
    "zombie": WALKER,
    "zombie-husk": HUSK,
    "zombie-brute": BRUTE,
}

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

# Zombie accessories — same 16x16 registration as the backpack. Baked colour:
# enemies are drawn untinted, so a hue here is the only identity a hat has.
# Hats sit on the head band (rows 0–4); clothes sit on the torso (rows 7–11).

HAT_CAP_PALETTE: Palette = {
    "o": (28, 26, 22, 255),
    "d": (72, 64, 44, 255),
    "b": (118, 102, 64, 255),
    "h": (148, 128, 78, 255),
}

HAT_CAP = Gear(
    palette=HAT_CAP_PALETTE,
    views={
        "down": _rows(
            ".....oooooo.....",
            "....obbbbbbo....",
            "....ohbbbbbo....",
            "...oooooooooo...",
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
        ),
        "side": _rows(
            ".......oooo.....",
            ".....obbbbbo....",
            ".....ohbbbbo....",
            ".....oooooooo...",
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
        ),
        "up": _rows(
            ".....oooooo.....",
            "....obbbbbbo....",
            "....obbbbbbo....",
            ".....oooooo.....",
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
        ),
    },
)

HAT_BEANIE_PALETTE: Palette = {
    "o": (32, 22, 24, 255),
    "d": (88, 40, 46, 255),
    "b": (132, 58, 64, 255),
    "h": (160, 84, 88, 255),
}

HAT_BEANIE = Gear(
    palette=HAT_BEANIE_PALETTE,
    views={
        "down": _rows(
            "......oo........",
            ".....obbbo......",
            "....obbbbbbo....",
            ".....oooooo.....",
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
        ),
        "side": _rows(
            "........oo......",
            "......obbbo.....",
            ".....obbbbbo....",
            "......ooooo.....",
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
        ),
        "up": _rows(
            "......oo........",
            ".....obbbo......",
            "....obbbbbbo....",
            ".....oooooo.....",
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
        ),
    },
)

HAT_HARDHAT_PALETTE: Palette = {
    "o": (36, 32, 18, 255),
    "d": (120, 96, 32, 255),
    "b": (176, 148, 48, 255),
    "h": (204, 180, 72, 255),
    "k": (80, 72, 36, 255),
}

HAT_HARDHAT = Gear(
    palette=HAT_HARDHAT_PALETTE,
    views={
        "down": _rows(
            ".....oooooo.....",
            "....obhhhhbo....",
            "....obbbbbbo....",
            "...ookooooooo...",
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
        ),
        "side": _rows(
            ".......oooo.....",
            ".....obhhhbo....",
            ".....obbbbbo....",
            ".....okooooooo..",
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
        ),
        "up": _rows(
            ".....oooooo.....",
            "....obhhhhbo....",
            "....obbbbbbo....",
            ".....oooooo.....",
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
        ),
    },
)

CLOTH_VEST_PALETTE: Palette = {
    "o": (24, 26, 22, 255),
    "d": (48, 52, 40, 255),
    "b": (72, 78, 56, 255),
    "h": (96, 100, 74, 255),
}

CLOTH_VEST = Gear(
    palette=CLOTH_VEST_PALETTE,
    views={
        "down": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            ".....o....o.....",
            "....ob....bo....",
            "....ob....bo....",
            "....obbbbbbo....",
            ".....obbbo......",
            "................",
            "................",
            "................",
            "................",
        ),
        "side": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            ".....o..........",
            "....obbo........",
            "....obbo...o....",
            "....obbbo..bo...",
            ".....obbo.......",
            "................",
            "................",
            "................",
            "................",
        ),
        "up": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            ".....oooooo.....",
            "....obbbbbbo....",
            "....obbbbbbo....",
            "....obhbbbbo....",
            ".....obbbo......",
            "................",
            "................",
            "................",
            "................",
        ),
    },
)

CLOTH_JACKET_PALETTE: Palette = {
    "o": (30, 24, 20, 255),
    "d": (64, 48, 38, 255),
    "b": (102, 78, 58, 255),
    "h": (128, 100, 74, 255),
}

CLOTH_JACKET = Gear(
    palette=CLOTH_JACKET_PALETTE,
    views={
        "down": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "....o......o....",
            "...ob......bo...",
            "...ob......bo...",
            "...obb....bbo...",
            "....ob....bo....",
            "................",
            "................",
            "................",
            "................",
        ),
        "side": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "...o............",
            "..obbo..........",
            "..obbbo.........",
            "..odbbbo........",
            "...obbbo........",
            "................",
            "................",
            "................",
            "................",
        ),
        "up": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "....oooooooo....",
            "...obbbbbbbbo...",
            "...obhhhhhhbo...",
            "...obbbbbbbbo...",
            "....odbbbbdo....",
            "................",
            "................",
            "................",
            "................",
        ),
    },
)

CLOTH_TIE_PALETTE: Palette = {
    "o": (28, 22, 24, 255),
    "d": (72, 32, 40, 255),
    "b": (112, 44, 52, 255),
}

CLOTH_TIE = Gear(
    palette=CLOTH_TIE_PALETTE,
    views={
        "down": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "......oo........",
            "......obbo......",
            "......obbo......",
            ".......oo.......",
            "................",
            "................",
            "................",
            "................",
            "................",
        ),
        "side": _rows(
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "................",
            "........o.......",
            "........bo......",
            "........bo......",
            "........o.......",
            "................",
            "................",
            "................",
            "................",
            "................",
        ),
        "up": _rows(
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
            "................",
            "................",
            "................",
            "................",
        ),
    },
)

GEAR = {
    "backpack": BACKPACK,
    "zhat-cap": HAT_CAP,
    "zhat-beanie": HAT_BEANIE,
    "zhat-hardhat": HAT_HARDHAT,
    "zcloth-vest": CLOTH_VEST,
    "zcloth-jacket": CLOTH_JACKET,
    "zcloth-tie": CLOTH_TIE,
}


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


def paint_exact(palette: Palette, rows: Art) -> Image.Image:
    """One 16x16 cell, one source char per pixel, top-left origin."""
    img = Image.new("RGBA", (EXACT_W, EXACT_W), MAGENTA)
    px = img.load()
    for y, line in enumerate(rows):
        for x, ch in enumerate(line):
            if ch == ".":
                continue
            px[x, y] = palette[ch]
    return img


def write_exact_sheet(columns: list[dict[str, Art]], palette: Palette, path: Path) -> None:
    """3x3 raw sheet on the processed grid. `columns` is the three walk cells."""
    sheet = Image.new("RGBA", (EXACT_W * 3, EXACT_W * 3), MAGENTA)
    for row, view in enumerate(VIEWS):
        for col, frames in enumerate(columns):
            sheet.paste(paint_exact(palette, frames[view]), (col * EXACT_W, row * EXACT_W))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height})")


def write_gear(gear: Gear, path: Path) -> None:
    """3x3 raw sheet; walk columns share one pose (overlays do not animate)."""
    write_exact_sheet([gear.views, gear.views, gear.views], gear.palette, path)


def write_exact_creature(creature: ExactCreature, path: Path) -> None:
    columns = [
        {view: creature.frame(view, col) for view in VIEWS}
        for col in range(3)
    ]
    write_exact_sheet(columns, creature.palette, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    keys = (*ENTITIES, *EXACT, *GEAR)
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

    if key in GEAR:
        # Gear is authored on the processed 16x16 grid. Forcing the cell here
        # means `--exact` in process_sprites.py keeps that registration.
        write_gear(GEAR[key], out)
        return

    if key in EXACT:
        write_exact_creature(EXACT[key], out)
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
