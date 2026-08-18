#!/usr/bin/env python3
"""Asset pipeline: SKILL ICONS and the CANISTERS the machine spits them out in.

Output (assets/processed/skills/):
    sheet.png      one 16x16 icon per skill, left to right in catalog order
    can.png        5 frames, 16x24 — one canister per rarity
    cap.png        5 frames, 16x24 — the same canister, lit, for the additive
                   pass, so a legendary can actually glows in a dark glade
    manifest.json  frame index per skill key, plus the canister geometry

TWO SHAPES AND THEY ARE DRAWN IN TWO PLACES.
The ICON is a flat HUD mark: centred in its cell, no contact shadow, no bottom
weighting, because it is stamped on a tile above the bag and again on the front
of a canister. Loot icons are bottom-anchored props that stand on soil; these
never touch the ground, and copying that anchoring would leave every tile in
the tray sitting one pixel low.

The CANISTER is the physical object — the thing that comes out of the tray, and
the only reason the skill is not a menu entry. It is one silhouette in five
colourways: a steel tube with a domed cap, a band, and a WINDOW in the middle
that is deliberately left as a flat plate, because the client composites the
icon into it. One can plus eighteen icons is eighteen readable objects out of
twenty-three drawings, and every one of them is guaranteed to read as the same
KIND of thing — which is the whole point of a machine that dispenses them.

RARITY IS THE METAL AND THE GLOW, NOT THE SHAPE.
A legendary canister is the same tube as a common one. Changing the silhouette
per tier would mean the player reads the tier off the outline before the colour
has said anything, and the colour is the language loot already taught them.

Usage:
    python tools/make_skills.py
    python tools/make_skills.py --tile 16
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
    quantize_alpha,
    rgb,
)

# --- palette ----------------------------------------------------------------
# ICONS ARE DRAWN AGAINST A DARK PANEL, not against soil. The loot ramps are
# tuned to survive a forest floor at night and come out muddy on an inset HUD
# tile, so these sit a step or two brighter and lean on value separation rather
# than on hue: a tray of eighteen tiles has to be scannable at a glance, and
# eighteen saturated colours is a sticker album.

STEEL: Ramp = [rgb(c) for c in ("#1b1e23", "#2b3038", "#3d434e", "#535a67", "#6d7583", "#8f97a6")]
DARK: Ramp = [rgb(c) for c in ("#101215", "#191c21", "#23272e", "#2e333b")]
HIDE: Ramp = [rgb(c) for c in ("#2a1d14", "#3b291c", "#4f3826", "#674a33", "#846044")]
CLOTH: Ramp = [rgb(c) for c in ("#2c2a24", "#3b3830", "#4d493e", "#615c4e", "#787260")]
FLESH: Ramp = [rgb(c) for c in ("#4a2622", "#68352c", "#8a4739", "#ac5c49", "#c9765d")]
BLOOD: Ramp = [rgb(c) for c in ("#3a0d0c", "#5e1512", "#8a1f19", "#b52c22", "#d94a34")]
GOLD: Ramp = [rgb(c) for c in ("#3a2410", "#6a4018", "#a06820", "#d4a040", "#f2c14b", "#ffe08a")]
GLASS: Ramp = [rgb(c) for c in ("#16222b", "#22343f", "#33505f", "#4a7488", "#6ba3b8", "#9fd4e2")]
SPARK: Ramp = [rgb(c) for c in ("#3d4b2a", "#5d7239", "#86a34c", "#b4d067", "#e2f2a0")]
FROST: Ramp = [rgb(c) for c in ("#1c2a38", "#2a4258", "#3d6480", "#5b93b0", "#95d0e0")]
NEON: Ramp = [rgb(c) for c in ("#3d1029", "#66184a", "#992a70", "#cc4a9c", "#ff6cba", "#ffb8dd")]
OUTLINE: RGBA = rgb("#07080a")

#: The five rarity colours, straight off `client/src/styles/index.css`. They
#: are duplicated here rather than imported because the CSS is the client's and
#: this is an offline script — but they are the same five and must stay so: a
#: canister that is not the colour the bag paints the same rarity is a second
#: colour language for one idea.
RARITY: dict[str, Ramp] = {
    "common": [rgb(c) for c in ("#3a3a42", "#565660", "#7c7c88", "#a8a8b4", "#e8e8f0")],
    "uncommon": [rgb(c) for c in ("#123020", "#1d4d32", "#2c7a4d", "#42a86a", "#5dce7a")],
    "rare": [rgb(c) for c in ("#131f3d", "#1d3160", "#2c4b96", "#3e6ac6", "#5b8def")],
    "epic": [rgb(c) for c in ("#2a1440", "#3f1d63", "#5f2d94", "#8a48c4", "#b46ee8")],
    "legendary": [rgb(c) for c in ("#3a2a0c", "#5e4413", "#96701f", "#c99a34", "#f2c14b")],
}
ORDER = ("common", "uncommon", "rare", "epic", "legendary")

Art = list[str]
Palette = dict[str, Ramp]

ICON_CELL = 16
CAN_W = 16
CAN_H = 24
#: Where the icon is stamped on the canister, top-left in frame pixels. The
#: window is 10x10 and the icon is 16x16, so the client scales it — the number
#: the client needs is this corner and that size, which is why both ride the
#: manifest instead of being guessed from the sheet.
WINDOW = (3, 8, 10, 10)


def _blit(art: Art, ramps: Palette, cell: int = ICON_CELL) -> Image.Image:
    """One char per pixel, CENTRED in the cell.

    Deliberately not `make_loot._blit`, which plants its art on the bottom edge
    because a loot icon is a prop standing on a tile. Nothing here stands on
    anything: an icon is a mark on a panel and a canister label, and both want
    the same optical centre.
    """
    img = Image.new("RGBA", (cell, cell), TRANSPARENT)
    px = img.load()
    art_w = max(len(row) for row in art)
    art_h = len(art)
    ox = (cell - art_w) // 2
    oy = (cell - art_h) // 2
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            ramp = ramps.get(ch)
            if ramp is None:
                continue
            # Light from the top-left, the same direction every other sheet in
            # this game is lit from. A tray of icons lit from a second angle
            # reads as art borrowed from somewhere else.
            shade = 0.74 - (y / max(art_h - 1, 1)) * 0.30 + (x / max(art_w - 1, 1)) * 0.14
            px[ox + x, oy + y] = pick(ramp, shade, ox + x, oy + y)
    outline(img, OUTLINE)
    return img


# ---------------------------------------------------------------------------
# THE CATALOG. Order is the frame order and mirrors `server/app/skills.py`.
#
# ONE IDEA PER ICON, AND IT IS THE EFFECT. At sixteen pixels an icon cannot say
# "Coração de Ferro"; it can say HEART and it can say IRON, and a plated heart
# is both. Anything that needed a third element was redrawn until it did not.
# ---------------------------------------------------------------------------

ICONS: list[tuple[str, Palette, Art]] = [
    (
        # Passo Leve — a boot, with the ground streaking past under it.
        "passo_leve",
        {"h": HIDE, "d": DARK, "s": SPARK},
        [
            "..hh....",
            "..hhh...",
            "..hhh...",
            "..hhhh..",
            ".hhhhhh.",
            ".dddddd.",
            "ss..ss..",
            ".ss..ss.",
        ],
    ),
    (
        # Forro Reforçado — a canvas patch, read by the HOLE in it. A filled
        # square of cloth at this size is a grey block; a stitched border round
        # empty middle is unmistakably something sewn on.
        "forro_reforcado",
        {"c": CLOTH, "s": STEEL},
        [
            "scscscsc",
            "c......c",
            "s......s",
            "c......c",
            "s......s",
            "c......c",
            "scscscsc",
        ],
    ),
    (
        # Mão Firme — a round. It was a fist first and a fist at sixteen pixels
        # is a lump; a cartridge is a silhouette nobody has to be told about,
        # and it pairs with `mira_apurada`'s reticle as "the gun rows".
        "mao_firme",
        {"g": GOLD, "s": STEEL, "d": DARK},
        [
            "..ss..",
            ".ssss.",
            "ssssss",
            "sdddds",
            "gggggg",
            "gg..gg",
            "gggggg",
            "gddddg",
        ],
    ),
    (
        # Couro Grosso — a hide chest piece with a strap across it.
        "couro_grosso",
        {"h": HIDE, "d": DARK},
        [
            ".hhhhhh.",
            "hhhhhhhh",
            "hdhhhhdh",
            "hhdhhdhh",
            "hhhddhhh",
            ".hhhhhh.",
            "..hhhh..",
        ],
    ),
    (
        # Dedos Rápidos — a coin, already leaving.
        "dedos_rapidos",
        {"g": GOLD, "d": DARK, "s": STEEL},
        [
            "...gggg.",
            "..gggggg",
            "s.gggddg",
            ".sggdggg",
            "s.gggggg",
            "..gggggg",
            "...gggg.",
        ],
    ),
    (
        # Lâmina Afiada — a blade with the edge catching.
        "lamina_afiada",
        {"s": STEEL, "h": HIDE, "w": SPARK},
        [
            "......ws",
            ".....sss",
            "....sss.",
            "...sss..",
            "..sss...",
            ".hss....",
            "hh......",
        ],
    ),
    (
        # Bateria Fria — a cell with frost on it.
        "bateria_fria",
        {"s": STEEL, "f": FROST, "d": DARK},
        [
            "..ss..",
            "ssssss",
            "sffffs",
            "sfdfds",
            "sffffs",
            "sfdffs",
            "ssssss",
        ],
    ),
    (
        # Pulmão Fundo — a ribcage taking a breath.
        "pulmao_fundo",
        {"b": DARK, "f": FLESH, "s": STEEL},
        [
            "....ss....",
            "ff..ss..ff",
            "ffff..ffff",
            "ffffbbffff",
            "ffffbbffff",
            ".fffbbfff.",
            "..ff..ff..",
        ],
    ),
    (
        # Costura Grossa — a spool of heavy thread. A needle was a diagonal
        # hairline and vanished; a spool is two flanges and a wound middle,
        # which survives being 10 pixels across.
        "costura_grossa",
        {"s": STEEL, "c": CLOTH},
        [
            "ssssssss",
            "s......s",
            ".cccccc.",
            ".c.cc.c.",
            ".cccccc.",
            "s......s",
            "ssssssss",
        ],
    ),
    (
        # Veterano — three chevrons.
        "veterano",
        {"g": GOLD, "d": DARK},
        [
            "...gg...",
            "..gggg..",
            ".gg..gg.",
            "...gg...",
            "..gggg..",
            ".gg..gg.",
            "gg....gg",
        ],
    ),
    (
        # Mira Apurada — a reticle.
        "mira_apurada",
        {"s": STEEL, "r": BLOOD},
        [
            "...ss...",
            ".ssssss.",
            ".s.rr.s.",
            "ssr..rss",
            ".s.rr.s.",
            ".ssssss.",
            "...ss...",
        ],
    ),
    (
        # Pele Dura — a riveted plate.
        "pele_dura",
        {"s": STEEL, "d": DARK},
        [
            "ssssssss",
            "sdssssds",
            "ssssssss",
            "ssssssss",
            ".ssssss.",
            "..ssss..",
            "...ss...",
        ],
    ),
    (
        # Olho de Sucateiro — an eye, appraising.
        "olho_de_sucateiro",
        {"s": STEEL, "g": GLASS, "d": DARK, "o": GOLD},
        [
            "..sssss..",
            ".sgggggs.",
            "sggoooggs",
            "sggodoggs",
            "sggoooggs",
            ".sgggggs.",
            "..sssss..",
        ],
    ),
    (
        # Açougueiro — a cleaver.
        "acougueiro",
        {"s": STEEL, "h": HIDE, "r": BLOOD},
        [
            "sssssss..",
            "sssssss..",
            "ssssssshh",
            "srssssshh",
            "sssssss..",
            ".ssssss..",
            "..rsss...",
        ],
    ),
    (
        # Bolsos Fundos — a pack with a second pouch bolted on.
        "bolsos_fundos",
        {"c": CLOTH, "h": HIDE, "d": DARK},
        [
            ".hh..hh.",
            ".hh..hh.",
            "cccccccc",
            "cddddddc",
            "cccccccc",
            "cc.cc.cc",
            "cccccccc",
            ".cccccc.",
        ],
    ),
    (
        # Faro de Ouro — a coin, and the trail that led to it.
        "faro_de_ouro",
        {"g": GOLD, "d": DARK, "n": NEON},
        [
            "n..gggg.",
            ".ngggggg",
            "n.ggddgg",
            ".nggdggg",
            "n.gggggg",
            "..gggggg",
            "...gggg.",
        ],
    ),
    (
        # Coração de Ferro — a heart under plate.
        "coracao_de_ferro",
        {"r": BLOOD, "s": STEEL, "d": DARK},
        [
            ".rr..rr.",
            "rrrrrrrr",
            "rsrrrrsr",
            "rrssssrr",
            ".rsddsr.",
            "..rssr..",
            "...rr...",
        ],
    ),
    (
        # Rei do Ferro-Velho — a crown beaten out of scrap.
        "rei_do_ferro_velho",
        {"g": GOLD, "s": STEEL, "d": DARK},
        [
            "s..gg..s",
            "ss.gg.ss",
            "sgsggsgs",
            "sggggggs",
            "sgdggdgs",
            "ssgggggs",
            ".ssssss.",
        ],
    ),
]


# --- the canister -----------------------------------------------------------


#: Half-width of the tube at each row, out of a 16-wide cell. THE SHAPE OF THE
#: OBJECT IS THIS LIST and nothing else: a domed cap so the thing reads as
#: pressurised rather than as a box, a straight barrel, and a foot that pulls
#: in one pixel so it looks like it is standing on the tray instead of sunk
#: into it. It was a plain rectangle first and a rectangle is a crate.
CAN_PROFILE = (
    2, 4, 5, 5,      # dome
    5, 5, 5, 5,      # shoulder band
    5, 5, 5, 5, 5,   # barrel — the window lives in here
    5, 5, 5, 5, 5,
    5, 5, 5, 5,      # base band
    4, 3,            # foot
)
#: Which rows are the rarity METAL rather than steel: the shoulder and the
#: base. Everything between them is the same tube on every tier, which is what
#: makes the colour read as a grade rather than as a different object.
CAP_ROWS = range(0, 8)
BASE_ROWS = range(18, 24)


def make_can(ramp: Ramp, lit: bool) -> Image.Image:
    """One rarity's canister. `lit` is the additive copy.

    The dark pass is a real object in the world and takes the darkness multiply
    like anything else. The LIT pass is drawn after it, additively, and carries
    only the parts that are actually emitting — the seam between cap and
    barrel, and the rim around the window. That split is why a legendary can
    lying on the tray of a machine in a dark glade is visible from the other
    end of the lane while a common one is just an object somebody has to walk
    over to.
    """
    img = Image.new("RGBA", (CAN_W, CAN_H), TRANSPARENT)
    px = img.load()
    wx, wy, ww, wh = WINDOW
    centre = CAN_W / 2.0

    for y in range(CAN_H):
        half = CAN_PROFILE[y] if y < len(CAN_PROFILE) else 0
        if half <= 0:
            continue
        left = int(centre - half)
        right = int(centre + half) - 1
        band = y in CAP_ROWS or y in BASE_ROWS
        source = ramp if band else STEEL
        seam = y in (7, 8, 17, 18)
        for x in range(left, right + 1):
            # A cylinder is a horizontal ramp and nothing else at this size:
            # brightest a third of the way in from the left, falling off both
            # ways. Same light direction as every icon above it.
            t = (x - left) / max(1, right - left)
            shade = 1.0 - abs(t - 0.32) * 1.5
            if y <= 1 or y >= CAN_H - 2:
                shade -= 0.2
            in_window = wx <= x < wx + ww and wy <= y < wy + wh
            rim = (
                (wx - 1 <= x <= wx + ww and y in (wy - 1, wy + wh))
                or (wy - 1 <= y <= wy + wh and x in (wx - 1, wx + ww))
            )
            if lit:
                if not (rim or seam):
                    continue
                colour = pick(ramp, min(1.0, max(0.35, shade) + 0.4), x, y)
                px[x, y] = (colour[0], colour[1], colour[2], quantize_alpha(0.8))
                continue
            if in_window:
                # Flat, dark, and slightly cooler than the tube: the icon is
                # what is being read here and a shaded plate behind it would
                # fight its own shading.
                px[x, y] = pick(DARK, 0.3 + (y - wy) / (wh * 3.0), x, y)
                continue
            if rim:
                px[x, y] = pick(ramp, 0.85, x, y)
                continue
            px[x, y] = pick(source, max(0.06, shade), x, y)

    if not lit:
        outline(img, OUTLINE)
    return img


def build(args) -> Path:
    out_dir = PROCESSED_DIR / "skills"
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = args.tile

    icons = [_blit(art, ramps, cell) for _, ramps, art in ICONS]
    pack(icons, cell, cell).save(out_dir / "sheet.png")

    cans = [make_can(RARITY[name], lit=False) for name in ORDER]
    caps = [make_can(RARITY[name], lit=True) for name in ORDER]
    pack(cans, CAN_W, CAN_H).save(out_dir / "can.png")
    pack(caps, CAN_W, CAN_H).save(out_dir / "cap.png")

    manifest = {
        "tile": cell,
        "icons": {
            "file": "sheet.png",
            "frameWidth": cell,
            "frameHeight": cell,
            "frames": len(icons),
        },
        "frames": {key: index for index, (key, _, _) in enumerate(ICONS)},
        "can": {
            "file": "can.png",
            "litFile": "cap.png",
            "frameWidth": CAN_W,
            "frameHeight": CAN_H,
            "frames": len(cans),
            "rarities": list(ORDER),
            # Where the icon goes, in frame pixels. Shipped rather than derived
            # so moving the window is one edit here and no edit on the client.
            "window": list(WINDOW),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate skill icons and canisters.")
    parser.add_argument("--tile", type=int, default=DEFAULT_TILE)
    args = parser.parse_args()
    out = build(args)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
