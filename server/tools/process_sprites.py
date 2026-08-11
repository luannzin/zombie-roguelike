#!/usr/bin/env python3
"""Asset pipeline: raw AI-generated sprite sheet -> production sprite sheet.

Input contract (assets/raw/<name>.png):
    3x3 grid of frames on a solid magenta (#FF00FF) background
    rows: down, side (facing right), up
    cols: 3 animation frames, col 1 = idle/neutral

Steps:
    1. load the source PNG
    2. split into a 3x3 grid
    3. key out the magenta background -> alpha
    4. crop each frame to its content bounds
    5. normalize onto a canonical NxN canvas, bottom-centred, nearest-neighbour
    6. mirror the "side" frames to produce the "left" facing row
    7. export a packed sheet + manifest.json

Output (assets/processed/<name>/):
    sheet.png     rows = down, left, right, up   cols = 3 frames
    manifest.json

The pipeline is entity-agnostic: zombies, NPCs and other characters use the
same command with a different --name.

Usage:
    python tools/process_sprites.py --name player --size 16
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "assets" / "raw"
PROCESSED_DIR = ROOT / "assets" / "processed"

KEY_COLOR = (255, 0, 255)
GRID_COLS = 3
GRID_ROWS = 3
SOURCE_ROWS = ("down", "side", "up")
OUTPUT_ROWS = ("down", "left", "right", "up")


def split_grid(sheet: Image.Image) -> list[list[Image.Image]]:
    cw = sheet.width // GRID_COLS
    ch = sheet.height // GRID_ROWS
    return [
        [sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)) for c in range(GRID_COLS)]
        for r in range(GRID_ROWS)
    ]


def key_out(img: Image.Image, tolerance: int = 40) -> Image.Image:
    img = img.convert("RGBA")
    px = img.load()
    kr, kg, kb = KEY_COLOR
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if abs(r - kr) <= tolerance and abs(g - kg) <= tolerance and abs(b - kb) <= tolerance:
                px[x, y] = (0, 0, 0, 0)
            elif a < 255:
                px[x, y] = (r, g, b, 255)
    return img


def crop_to_content(img: Image.Image) -> Image.Image:
    box = img.getbbox()
    return img.crop(box) if box else img


def normalize(img: Image.Image, size: int, anchor_bottom_pad: int = 0) -> Image.Image:
    """Fit into a size x size canvas, bottom-centred, preserving aspect ratio."""
    target_h = max(1, size - anchor_bottom_pad)
    scale = min(size / img.width, target_h / img.height)
    if scale < 1.0 or scale > 1.0:
        new_w = max(1, round(img.width * scale))
        new_h = max(1, round(img.height * scale))
        img = img.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - img.width) // 2
    y = size - anchor_bottom_pad - img.height
    canvas.paste(img, (x, max(0, y)))
    return canvas


def process(name: str, size: int, tolerance: int, bottom_pad: int) -> Path:
    src = RAW_DIR / f"{name}.png"
    if not src.exists():
        raise SystemExit(f"raw asset not found: {src}")

    grid = split_grid(Image.open(src))
    frames: dict[str, list[Image.Image]] = {}
    for row_index, view in enumerate(SOURCE_ROWS):
        cells = []
        for cell in grid[row_index]:
            cell = key_out(cell, tolerance)
            cell = crop_to_content(cell)
            cell = normalize(cell, size, bottom_pad)
            cells.append(cell)
        frames[view] = cells

    frames["right"] = frames["side"]
    frames["left"] = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames["side"]]

    out_dir = PROCESSED_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = Image.new("RGBA", (size * GRID_COLS, size * len(OUTPUT_ROWS)), (0, 0, 0, 0))
    for row_index, view in enumerate(OUTPUT_ROWS):
        for col, frame in enumerate(frames[view]):
            sheet.paste(frame, (col * size, row_index * size))
    sheet_path = out_dir / "sheet.png"
    sheet.save(sheet_path)

    manifest = {
        "name": name,
        "sheet": "sheet.png",
        "frameWidth": size,
        "frameHeight": size,
        "frames": GRID_COLS,
        "rows": {view: i for i, view in enumerate(OUTPUT_ROWS)},
        "idleFrame": 1,
        "walkFrameOrder": [0, 1, 2, 1],
        "fps": 8,
        "anchor": {"x": 0.5, "y": 1.0},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {sheet_path} and manifest.json")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    ap.add_argument("--size", type=int, default=16, help="canonical sprite size")
    ap.add_argument("--tolerance", type=int, default=40, help="magenta key tolerance")
    ap.add_argument("--bottom-pad", type=int, default=0)
    args = ap.parse_args()
    process(args.name, args.size, args.tolerance, args.bottom_pad)


if __name__ == "__main__":
    main()
