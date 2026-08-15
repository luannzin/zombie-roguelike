#!/usr/bin/env python3
"""Asset pipeline: collectable loot icons.

Fifth generator in the family. Same rules as scenery: no raw stage, final
pixels into assets/processed/, deterministic, shading helpers imported from
make_textures rather than copied.

Output (assets/processed/loot/):
    sheet.png      one 16x16 frame per item, left to right in catalog order
    manifest.json  frame index per item key

These sit ON the ground as small standing props: outline, face toward the
camera, bottom-weighted in the cell so they plant on a tile. They are not
coins — they do not spin — and they are not scenery: the server places them
next to scenes and the player picks them up.

READ ORDER AT 16px. Value and silhouette, never fine detail. A bottle is a
tall neck, a crown is three points, a key is a bit and a bow.

Usage:
    python tools/make_loot.py
    python tools/make_loot.py --tile 16
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from make_textures import (
    DEFAULT_TILE,
    PROCESSED_DIR,
    RGBA,
    Ramp,
    TRANSPARENT,
    outline,
    pack,
    pick,
    rgb,
)

# Worked materials against the forest. Gold and gem steps go brighter than
# the scenery ramps — these have to read as *things* on a dark floor, not as
# more litter.
WOOD: Ramp = [rgb(c) for c in ("#1b1710", "#272118", "#342c20", "#413628", "#4f4232")]
METAL: Ramp = [rgb(c) for c in ("#16181b", "#212429", "#2e3238", "#3d4249", "#4d535b", "#6a717a")]
RUST: Ramp = [rgb(c) for c in ("#2a1712", "#3b2019", "#4d2a20", "#6a3a28", "#8a4a30")]
GLASS: Ramp = [rgb(c) for c in ("#1c242b", "#2a3742", "#3d4f5d", "#56707f", "#7794a4", "#a8c4d0")]
GOLD: Ramp = [rgb(c) for c in ("#3a2410", "#6a4018", "#a06820", "#d4a040", "#f2c14b", "#ffe08a")]
STONE: Ramp = [rgb(c) for c in ("#1e1d21", "#2a292e", "#37353b", "#454249", "#545059")]
BONE: Ramp = [rgb(c) for c in ("#38362e", "#49463c", "#5c584b", "#726d5c", "#8a8471")]
LEATHER: Ramp = [rgb(c) for c in ("#1a1310", "#251b16", "#31241c", "#3f2f24", "#534033")]
CLOTH: Ramp = [rgb(c) for c in ("#2e2c26", "#3d3a32", "#4d493e", "#5f5a4c", "#746e5c")]
CRYSTAL: Ramp = [rgb(c) for c in ("#1a2438", "#2a4060", "#3d6a9a", "#5a9ad0", "#8ad0f0", "#d0f0ff")]
OBSIDIAN: Ramp = [rgb(c) for c in ("#0a0a10", "#14141c", "#1e1e2a", "#2c2c3a", "#4a4a5a", "#8a8a9a")]
PEARL: Ramp = [rgb(c) for c in ("#1a1420", "#2a2030", "#3d3048", "#5a4868", "#2a2a32", "#c8c0d0")]
OLIVE: Ramp = [rgb(c) for c in ("#1d2016", "#272b1d", "#333825", "#40462e", "#545c3c")]
OUTLINE = rgb("#0a0b0d")

Art = list[str]
Palette = dict[str, Ramp]


def _blit(art: Art, ramps: Palette, cell: int) -> Image.Image:
    """One char per pixel, centred and planted near the bottom of the cell."""
    img = Image.new("RGBA", (cell, cell), TRANSPARENT)
    px = img.load()
    art_w = len(art[0])
    art_h = len(art)
    ox = (cell - art_w) // 2
    oy = cell - art_h - 1
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            ramp = ramps.get(ch)
            if ramp is None:
                continue
            # Top-left of the silhouette is the lit face.
            shade = 0.72 - (y / max(art_h - 1, 1)) * 0.28 + (x / max(art_w - 1, 1)) * 0.12
            px[ox + x, oy + y] = pick(ramp, shade, ox + x, oy + y)
    outline(img, OUTLINE)
    return img


# ---------------------------------------------------------------------------
# Catalog order is the frame order. server/app/loot.py lists the same keys.
# ---------------------------------------------------------------------------

ITEMS: list[tuple[str, Palette, Art]] = [
    (
        "old_tools",
        {"w": WOOD, "m": METAL, "r": RUST},
        [
            "....m.......",
            "...mmm......",
            "....m.ww....",
            "....m.ww....",
            "..rr..ww....",
            ".rrrr.ww....",
            "..rr........",
        ],
    ),
    (
        "empty_bottle",
        {"g": GLASS, "c": CLOTH},
        [
            "...gg...",
            "...gg...",
            "..gggg..",
            ".ggccgg.",
            ".gggggg.",
            ".gggggg.",
            "..gggg..",
        ],
    ),
    (
        "broken_toy",
        {"c": CLOTH, "l": LEATHER, "b": BONE},
        [
            "..ccc...",
            ".cbbbc..",
            ".cbcbc..",
            "..ccc...",
            ".lcccl..",
            ".l...l..",
            ".l...l..",
        ],
    ),
    (
        "broken_clock",
        {"w": WOOD, "m": METAL, "g": GLASS},
        [
            "..wwwwww..",
            ".wggggggw.",
            ".wgmmgggw.",
            ".wggmgggw.",
            ".wggggmgw.",
            "..wwwwww..",
            "....mm....",
        ],
    ),
    (
        "scrap",
        {"m": METAL, "r": RUST},
        [
            "..rr.m....",
            ".rrmmmr...",
            "..mmrrm...",
            ".mrr.mm...",
            "..m.rr....",
        ],
    ),
    (
        "camera",
        {"l": LEATHER, "m": METAL, "g": GLASS},
        [
            "...mm.....",
            ".lllllll..",
            ".lmmgmml..",
            ".lmgggml..",
            ".lmmmmml..",
            ".lllllll..",
        ],
    ),
    (
        "old_headphone",
        {"l": LEATHER, "m": METAL},
        [
            "...mmmm...",
            "..m....m..",
            ".m......m.",
            "ll......ll",
            "ll......ll",
        ],
    ),
    (
        "portable_radio",
        {"m": METAL, "l": LEATHER, "g": GLASS},
        [
            "....m.....",
            "....m.....",
            ".mmmmmmm..",
            ".mgggllm..",
            ".mlllllm..",
            ".mmmmmmm..",
        ],
    ),
    (
        "compass",
        {"g": GOLD, "m": METAL, "c": CRYSTAL},
        [
            "..ggggg..",
            ".gcmmmcg.",
            ".gmcmcmg.",
            ".gcmmmcg.",
            "..ggggg..",
        ],
    ),
    (
        "military_camera",
        {"o": OLIVE, "m": METAL, "g": GLASS},
        [
            "...mm.....",
            ".ooooooo..",
            ".ommgmmo..",
            ".omgggmo..",
            ".ommmmmo..",
            ".ooooooo..",
        ],
    ),
    (
        "gold_ring",
        {"g": GOLD},
        [
            "..gggg..",
            ".g....g.",
            ".g....g.",
            "..gggg..",
        ],
    ),
    (
        "binoculars",
        {"m": METAL, "g": GLASS, "l": LEATHER},
        [
            ".gg..gg.",
            ".mmllmm.",
            ".mmllmm.",
            ".mm..mm.",
        ],
    ),
    (
        "precious_gem",
        {"c": CRYSTAL},
        [
            "...cc...",
            "..cccc..",
            ".cccccc.",
            "..cccc..",
            "...cc...",
        ],
    ),
    (
        "stone_idol",
        {"s": STONE, "b": BONE},
        [
            "...ss...",
            "..sbbss.",
            "..sssss.",
            "...sss..",
            "..sssss.",
            ".sssssss",
        ],
    ),
    (
        "tribal_mask",
        {"w": WOOD, "c": CLOTH, "b": BONE},
        [
            ".wwwwwww.",
            ".wbbwbbw.",
            ".wwcwcww.",
            ".wwwwwcw.",
            "..wwwww..",
        ],
    ),
    (
        "ancient_amulet",
        {"g": GOLD, "c": CRYSTAL, "l": LEATHER},
        [
            "...ll....",
            "..l..l...",
            ".l....l..",
            "..gggg...",
            "..gcg....",
            "...g.....",
        ],
    ),
    (
        "gold_figurine",
        {"g": GOLD},
        [
            "...gg...",
            "..gggg..",
            "...gg...",
            "..gggg..",
            ".gggggg.",
            "..gggg..",
        ],
    ),
    (
        "raw_diamond",
        {"c": CRYSTAL, "s": STONE},
        [
            "...cc...",
            "..cccc..",
            ".ccsccc.",
            "..cccc..",
            "...ss...",
        ],
    ),
    (
        "black_pearl",
        {"p": PEARL, "o": OBSIDIAN},
        [
            "..oooo..",
            ".oopooo.",
            ".oooooo.",
            "..oooo..",
        ],
    ),
    (
        "black_diamond",
        {"o": OBSIDIAN, "c": CRYSTAL},
        [
            "...oo...",
            "..oooo..",
            ".oocooo.",
            "..oooo..",
            "...oo...",
        ],
    ),
    (
        "lost_crown",
        {"g": GOLD, "c": CRYSTAL},
        [
            "g.c.g.c.g",
            "ggggggggg",
            "gcccccccg",
            "ggggggggg",
        ],
    ),
    (
        "sanctuary_relic",
        {"s": STONE, "g": GOLD, "c": CRYSTAL},
        [
            "...g....",
            "..gcg...",
            "...g....",
            ".ssssss.",
            ".sggggs.",
            ".ssssss.",
        ],
    ),
    (
        "vault_key",
        {"g": GOLD, "m": METAL},
        [
            "..gggg..",
            ".g....g.",
            "..gggg..",
            "....g...",
            "....g.mm",
            "....g.m.",
        ],
    ),
    (
        "royal_ring",
        {"g": GOLD, "c": CRYSTAL},
        [
            "...cc...",
            "..gggg..",
            ".g....g.",
            ".g....g.",
            "..gggg..",
        ],
    ),
    (
        "glock18",
        {"t": LEATHER, "m": METAL},
        [
            "....mmmmmm.",
            "...tmmmmmm.",
            "...t.......",
            "...t.......",
            "...tt......",
        ],
    ),
    (
        "deagle",
        {"s": GOLD, "g": CLOTH},
        [
            ".....sssssss",
            "....ssssssss",
            "...gg.......",
            "...gg.......",
            "...ggg......",
        ],
    ),
    (
        "famas",
        {"m": METAL, "g": CLOTH},
        [
            "...mmmmmm...",
            "...m....m.mm",
            "ggggggggggmm",
            "g....g......",
            "gggggg......",
        ],
    ),
    (
        "ak47",
        {"w": WOOD, "m": METAL},
        [
            ".........m..",
            "wwwwwmmmmmmm",
            "w...w.mmmmmm",
            "wwwww.mm....",
            "......mm....",
        ],
    ),
    (
        "awp",
        {"o": OLIVE, "m": METAL, "s": STONE},
        [
            ".......ss.....",
            "ooooooommmmmmm",
            "o....o.mmmmmmm",
            "oooooo.m......",
        ],
    ),
]


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "loot"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = [_blit(art, pal, tile) for _, pal, art in ITEMS]
    pack(frames, tile, tile).save(out_dir / "sheet.png")

    manifest = {
        "tile": tile,
        "frameWidth": tile,
        "frameHeight": tile,
        "frames": len(ITEMS),
        "items": {key: {"frame": index} for index, (key, _, _) in enumerate(ITEMS)},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(ITEMS)} items @ {tile}x{tile}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
