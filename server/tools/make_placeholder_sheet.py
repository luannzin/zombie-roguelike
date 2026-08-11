#!/usr/bin/env python3
"""Generate a placeholder RAW sprite sheet in the project's source format.

The real project will use AI-generated pixel art, but the raw format is fixed:
a 3x3 grid of frames on a solid magenta (#FF00FF) background.

  rows: 0 = facing down, 1 = facing side (right), 2 = facing up
  cols: 0 = step A, 1 = idle/stand, 2 = step B

The art is drawn at the canonical 16x24 (1 x 1.5 tiles at TILE_SIZE 16) so the
processing pipeline never has to resample it.

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
    "d": (96, 100, 118, 255),   # dark shade (hair, trousers)
    "b": (232, 232, 240, 255),  # body — this is what gets tinted in-game
    "s": (238, 202, 172, 255),  # skin
    "e": (36, 34, 46, 255),     # eye
}

ART_W, ART_H = 16, 24

# rows 0..8: head + shoulders, per facing
HEADS = {
    "down": [
        "....oooooo......",
        "...odddddddo....",
        "...ossssssso....",
        "...ossssssso....",
        "...osesssseo....",
        "...ossssssso....",
        "....ooooooo.....",
        "....obbbbbo.....",
        "...obbbbbbbo....",
    ],
    "side": [
        "....oooooo......",
        "...odddddddo....",
        "...odddsssso....",
        "...ossssssso....",
        "...ossssseso....",
        "...ossssssso....",
        "....ooooooo.....",
        "....obbbbbo.....",
        "...obbbbbbbo....",
    ],
    "up": [
        "....oooooo......",
        "...odddddddo....",
        "...oddddddddo...",
        "...oddddddddo...",
        "...oddddddddo...",
        "...oddddddddo...",
        "....ooooooo.....",
        "....obbbbbo.....",
        "...obbbbbbbo....",
    ],
}

# rows 9..16: torso, shared by every facing
TORSO = [
    "..obbbbbbbbbo...",
    "..obbbbbbbbbo...",
    "..obbbbbbbbbo...",
    "..obbbbbbbbbo...",
    "...obbbbbbbo....",
    "...obbbbbbbo....",
    "...odddddddo....",
    "...odd...ddo....",
]

# rows 17..23: legs. Index 1 is the neutral stance.
LEGS = [
    [
        "..odd.....ddo...",
        "..odd.....ddo...",
        "..odd.....ddo...",
        "..ooo.....ooo...",
        ".oooo.....oooo..",
        ".oooo.....oooo..",
        ".oooo.....oooo..",
    ],
    [
        "...odd...ddo....",
        "...odd...ddo....",
        "...odd...ddo....",
        "...ooo...ooo....",
        "...ooo...ooo....",
        "..oooo...oooo...",
        "..oooo...oooo...",
    ],
    [
        "....odddddo.....",
        "....odddddo.....",
        "....odddddo.....",
        "....ooooooo.....",
        "...ooooooooo....",
        "...ooooooooo....",
        "...ooooooooo....",
    ],
]


def build_frame(view: str, frame: int) -> list[str]:
    rows = HEADS[view] + TORSO + LEGS[frame]
    bad = [(i, r) for i, r in enumerate(rows) if len(r) != ART_W]
    if bad:
        raise SystemExit(f"art rows must be {ART_W} chars: {bad[:3]}")
    if len(rows) != ART_H:
        raise SystemExit(f"art must be {ART_H} rows, got {len(rows)}")
    return rows


def render_cell(rows: list[str], cell_w: int, cell_h: int) -> Image.Image:
    img = Image.new("RGBA", (cell_w, cell_h), MAGENTA)
    px = img.load()
    ox = (cell_w - ART_W) // 2
    oy = (cell_h - ART_H) // 2
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px[ox + x, oy + y] = PALETTE[ch]
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    ap.add_argument("--cell-width", type=int, default=24)
    ap.add_argument("--cell-height", type=int, default=36)
    ap.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[2] / "assets" / "raw"),
    )
    args = ap.parse_args()

    cw, ch = args.cell_width, args.cell_height
    sheet = Image.new("RGBA", (cw * 3, ch * 3), MAGENTA)
    for row, view in enumerate(("down", "side", "up")):
        for col in range(3):
            sheet.paste(render_cell(build_frame(view, col), cw, ch), (col * cw, row * ch))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.name}.png"
    sheet.convert("RGB").save(path)
    print(f"wrote {path} ({sheet.width}x{sheet.height}, cell {cw}x{ch})")


if __name__ == "__main__":
    main()
