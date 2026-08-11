#!/usr/bin/env python3
"""Generate a placeholder RAW sprite sheet in the project's source format.

The real project will use AI-generated pixel art, but the raw format is fixed:
a 3x3 grid of frames on a solid magenta (#FF00FF) background.

  rows: 0 = facing down, 1 = facing side (right), 2 = facing up
  cols: 0 = step A, 1 = idle/stand, 2 = step B

Output: assets/raw/<name>.png  (consumed by tools/process_sprites.py)

Usage:
    python tools/make_placeholder_sheet.py --name player
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

MAGENTA = (255, 0, 255, 255)

PALETTE = {
    "o": (28, 26, 38, 255),     # outline
    "d": (96, 100, 118, 255),   # dark shade
    "b": (232, 232, 240, 255),  # body (this is what gets tinted in-game)
    "s": (238, 202, 172, 255),  # skin
    "e": (36, 34, 46, 255),     # eye
}

# 12 wide, 16 tall. '.' = background.
HEAD = {
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

TORSO = [
    "...obbbbo...",
    "..obbbbbbo..",
    "..obbbbbbo..",
    "..obbbbbbo..",
    "...obbbbo...",
]

# Leg frames: index 1 is the neutral stance.
LEGS = [
    ["..obb..bbo..", "..od....do..", "..oo....oo.."],
    ["...ob..bo...", "...od..do...", "...oo..oo..."],
    ["..obb..bbo..", "...od..do...", "..oo....oo.."],
]


def build_frame(view: str, frame: int) -> list[str]:
    return HEAD[view] + TORSO + LEGS[frame]


def render_cell(rows: list[str], cell: int, scale: int) -> Image.Image:
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
            color = PALETTE[ch]
            for sy in range(scale):
                for sx in range(scale):
                    px[ox + x * scale + sx, oy + y * scale + sy] = color
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    ap.add_argument("--cell", type=int, default=32, help="raw cell size in px")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[2] / "assets" / "raw"),
    )
    args = ap.parse_args()

    cell = args.cell
    sheet = Image.new("RGBA", (cell * 3, cell * 3), MAGENTA)
    for row, view in enumerate(("down", "side", "up")):
        for col in range(3):
            sheet.paste(render_cell(build_frame(view, col), cell, args.scale),
                        (col * cell, row * cell))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.name}.png"
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
