#!/usr/bin/env python3
"""Asset pipeline: raw AI-generated sprite sheet -> production sprite sheet.

Input contract (assets/raw/<name>.png):
    Nx3 grid of frames on a solid magenta (#FF00FF) background
    rows: down, side, up
    cols: walk sheets are 3 (col 1 = idle); death sheets (`<name>-death`)
    are a one-shot timeline, last column = the prone rest that stays.

Steps:
    1. load the source PNG
    2. split into a 3x3 grid
    3. key out the magenta background -> alpha
    4. crop each frame to its content bounds
    5. normalize onto a canonical NxN canvas, bottom-centred
    6. mirror the "side" frames to produce the opposite facing row
    7. export a packed sheet + manifest.json

Output (assets/processed/<name>/):
    sheet.png     rows = down, left, right, up   cols = 3 frames
    manifest.json

The canonical frame is 1 x 1 tile (16x16 px at the project's TILE_SIZE of 16),
so `--tile` is normally the only size flag you need; it must match TILE_SIZE in
server/app/config.py. Frames do not have to be square — a taller entity passes
`--height` and the renderer anchors it by its bottom edge.

Notes on real (AI-generated) source art:
    * It is usually drawn at high resolution with per-pixel noise, so the big
      downscale uses area-averaging (BOX) rather than NEAREST, which would
      sample noise instead of the intended pixel. `--filter` overrides this.
    * Anti-aliased edges blend into the key colour, so the default key test is
      a magenta *hue* test (high R, high B, low G) rather than a plain distance
      test, which leaves a pink fringe.
    * `--side-facing` tells the pipeline which way the source side row faces;
      the other facing is produced by mirroring.

The pipeline is entity-agnostic: zombies, NPCs and other characters use the
same command with a different --name.

Usage:
    python tools/process_sprites.py --name player --tile 16 --side-facing left
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

# Canonical frame shape, in tiles. Mirrors server/app/config.py:
# TILE_SIZE is the one number that sets the scale; a character frame is
# 1 x 1 tile (16x16 at tile 16, 32x32 at tile 32). Taller entities pass
# --height (or --tiles-h) without changing the tile scale.
DEFAULT_TILE = 16
SPRITE_TILES_W = 1.0
SPRITE_TILES_H = 1.0

FILTERS = {
    "nearest": Image.NEAREST,
    "box": Image.BOX,
    "lanczos": Image.LANCZOS,
    "bilinear": Image.BILINEAR,
}


def split_grid(sheet: Image.Image, cols: int, rows: int) -> list[list[Image.Image]]:
    cw = sheet.width // cols
    ch = sheet.height // rows
    if cw < 1 or ch < 1:
        raise SystemExit(
            f"sheet {sheet.width}x{sheet.height} is too small for a {cols}x{rows} grid"
        )
    return [
        [sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)) for c in range(cols)]
        for r in range(rows)
    ]


def is_key_pixel(r: int, g: int, b: int, tolerance: int, hue_key: bool) -> bool:
    kr, kg, kb = KEY_COLOR
    if abs(r - kr) <= tolerance and abs(g - kg) <= tolerance and abs(b - kb) <= tolerance:
        return True
    if hue_key:
        # magenta-ish: red and blue both strong, green clearly weaker.
        # Catches anti-aliased edges that blend towards the background.
        return r > 120 and b > 120 and g < min(r, b) * 0.72
    return False


def key_out(img: Image.Image, tolerance: int, hue_key: bool) -> Image.Image:
    img = img.convert("RGBA")
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if is_key_pixel(r, g, b, tolerance, hue_key):
                px[x, y] = (0, 0, 0, 0)
            elif a < 255:
                px[x, y] = (r, g, b, 255)
    return img


def crop_to_content(img: Image.Image) -> Image.Image:
    box = img.getbbox()
    return img.crop(box) if box else img


def union_bbox(images: list[Image.Image]) -> tuple[int, int, int, int] | None:
    """Shared crop box across frames — keeps spin / idle sizes locked together."""
    boxes = [img.getbbox() for img in images]
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def pick_filter(name: str, scale: float):
    if name != "auto":
        return FILTERS[name]
    # Big reductions of high-res art must average; small changes stay crisp.
    return Image.BOX if scale < 0.67 else Image.NEAREST


def normalize(
    img: Image.Image,
    width: int,
    height: int,
    bottom_pad: int,
    filter_name: str,
    alpha_threshold: int,
) -> Image.Image:
    """Fit into a width x height canvas, bottom-centred, preserving aspect ratio."""
    target_h = max(1, height - bottom_pad)
    scale = min(width / img.width, target_h / img.height)
    if scale != 1.0:
        new_w = max(1, round(img.width * scale))
        new_h = max(1, round(img.height * scale))
        img = img.resize((new_w, new_h), pick_filter(filter_name, scale))

    if alpha_threshold > 0:
        # Keep a hard pixel-art silhouette instead of a soft resampled edge.
        px = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = px[x, y]
                px[x, y] = (r, g, b, 255 if a >= alpha_threshold else 0)
        img = crop_to_content(img)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = (width - img.width) // 2
    y = height - bottom_pad - img.height
    canvas.paste(img, (x, max(0, y)))
    return canvas


def process(args) -> Path:
    src = RAW_DIR / f"{args.name}.png"
    if not src.exists():
        raise SystemExit(f"raw asset not found: {src}")

    width = args.width or round(args.tile * SPRITE_TILES_W)
    height = args.height or round(args.tile * SPRITE_TILES_H)

    src_img = Image.open(src)
    if args.exact:
        # Exact sheets are authored in target pixels, so the grid is the sheet
        # divided by the frame. Walk is 3x3; death is Nx3 (a timeline).
        cols = src_img.width // width
        rows = src_img.height // height
        if cols < 1 or rows != len(SOURCE_ROWS):
            raise SystemExit(
                f"exact sheet {src_img.width}x{src_img.height} must be "
                f"{width} wide by {height * len(SOURCE_ROWS)} tall "
                f"(got {cols}x{rows} cells)"
            )
    else:
        cols, rows = GRID_COLS, GRID_ROWS

    grid = split_grid(src_img, cols, rows)
    keyed = [
        [key_out(cell, args.tolerance, not args.no_hue_key) for cell in row]
        for row in grid
    ]

    # Shared crop box: foreshortened frames keep the face-on size.
    shared = union_bbox([cell for row in keyed for cell in row]) if args.uniform else None

    frames: dict[str, list[Image.Image]] = {}
    for row_index, view in enumerate(SOURCE_ROWS):
        cells = []
        for cell in keyed[row_index]:
            if args.exact:
                # Source already composed at the target grid — keep the artist's
                # placement instead of re-cropping and re-centring each frame.
                if cell.size != (width, height):
                    cell = cell.resize((width, height), Image.NEAREST)
            else:
                if shared is not None:
                    cell = cell.crop(shared)
                else:
                    cell = crop_to_content(cell)
                cell = normalize(
                    cell, width, height, args.bottom_pad, args.filter, args.alpha_threshold
                )
            cells.append(cell)
        frames[view] = cells

    mirrored = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames["side"]]
    if args.side_facing == "right":
        frames["right"] = frames["side"]
        frames["left"] = mirrored
    else:
        frames["left"] = frames["side"]
        frames["right"] = mirrored

    out_dir = PROCESSED_DIR / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = Image.new("RGBA", (width * cols, height * len(OUTPUT_ROWS)), (0, 0, 0, 0))
    for row_index, view in enumerate(OUTPUT_ROWS):
        for col, frame in enumerate(frames[view]):
            sheet.paste(frame, (col * width, row_index * height))
    sheet_path = out_dir / "sheet.png"
    sheet.save(sheet_path)

    # Walk cycle vs one-shot timeline. Death sheets (`*-death`) are N frames
    # that play once and hold the last — a prone rest, not a ping-pong.
    # `--uniform` used to mean a 3-frame ping-pong; the world coin now lives
    # in make_coin.py and owns its own order.
    timeline = cols != GRID_COLS or args.name.endswith("-death")
    if timeline:
        walk_order = list(range(cols))
        idle = cols - 1
        fps = 12
        loop = False
    else:
        walk_order = [0, 1, 2, 1]
        idle = 0 if args.uniform else 1
        fps = 12 if args.uniform else 8
        loop = True

    manifest = {
        "name": args.name,
        "sheet": "sheet.png",
        "frameWidth": width,
        "frameHeight": height,
        "frames": cols,
        "rows": {view: i for i, view in enumerate(OUTPUT_ROWS)},
        "idleFrame": idle,
        "walkFrameOrder": walk_order,
        "fps": fps,
        "loop": loop,
        "anchor": {"x": 0.5, "y": 1.0},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {sheet_path} ({sheet.width}x{sheet.height}, "
          f"frame {width}x{height}) and manifest.json")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="player")
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="tile size = the game's scale; frame is 1 x 1.5 tiles")
    ap.add_argument("--width", type=int, default=0, help="override frame width in px")
    ap.add_argument("--height", type=int, default=0, help="override frame height in px")
    ap.add_argument("--tolerance", type=int, default=40, help="magenta key distance tolerance")
    ap.add_argument("--no-hue-key", action="store_true", help="disable the magenta hue test")
    ap.add_argument("--side-facing", choices=("left", "right"), default="right",
                    help="direction the source side row faces")
    ap.add_argument("--filter", choices=("auto", *FILTERS), default="auto")
    ap.add_argument("--alpha-threshold", type=int, default=128,
                    help="0 disables; otherwise alpha is forced to 0 or 255")
    ap.add_argument("--bottom-pad", type=int, default=0)
    ap.add_argument(
        "--exact",
        action="store_true",
        help="source cell is already composed at the target grid: straight NEAREST "
             "downscale, no crop / rescale / re-centre (art drawn at an integer multiple)",
    )
    ap.add_argument(
        "--uniform",
        action="store_true",
        help="shared crop box across all cells (spin/item sheets stay one size)",
    )
    args = ap.parse_args()
    process(args)


if __name__ == "__main__":
    main()
