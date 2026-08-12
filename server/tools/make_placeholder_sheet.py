#!/usr/bin/env python3
"""Generate a placeholder RAW sprite sheet in the project's source format.

The real project will use AI-generated pixel art, but the raw format is fixed:
a 3x3 grid of frames on a solid magenta (#FF00FF) background.

  rows: 0 = facing down, 1 = facing side (right), 2 = facing up
  cols: 0 = step A, 1 = idle/stand, 2 = step B

One entity per run. `--entity` picks the art set (defaults to `--name`, so
`--name zombie` draws the zombie); every set is 12x14 characters of ASCII art
over a per-entity palette, so adding a creature is data, not code.

Output: assets/raw/<name>.png  (consumed by tools/process_sprites.py)

Usage:
    python tools/make_placeholder_sheet.py --name player
    python tools/make_placeholder_sheet.py --name zombie
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


def render_cell(entity: Entity, rows: Art, cell: int, scale: int) -> Image.Image:
    img = Image.new("RGBA", (cell, cell), MAGENTA)
    px = img.load()
    art_w = len(rows[0]) * scale
    art_h = len(rows) * scale
    ox = (cell - art_w) // 2
    oy = cell - art_h - scale  # feet near the bottom of the cell
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            color = entity.palette[ch]
            for sy in range(scale):
                for sx in range(scale):
                    px[ox + x * scale + sx, oy + y * scale + sy] = color
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    ap.add_argument("--entity", choices=tuple(ENTITIES), default=None,
                    help="art set to draw (defaults to --name)")
    ap.add_argument("--cell", type=int, default=32, help="raw cell size in px")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[2] / "assets" / "raw"),
    )
    args = ap.parse_args()

    key = args.entity or args.name
    if key not in ENTITIES:
        raise SystemExit(
            f"no art set for '{key}'; pass --entity {'|'.join(ENTITIES)}"
        )
    entity = ENTITIES[key]

    cell = args.cell
    sheet = Image.new("RGBA", (cell * 3, cell * 3), MAGENTA)
    for row, view in enumerate(VIEWS):
        for col in range(3):
            sheet.paste(render_cell(entity, entity.frame(view, col), cell, args.scale),
                        (col * cell, row * cell))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.name}.png"
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
