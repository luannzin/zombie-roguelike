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

#: The held-weapon generator, imported for its PAINTER and its material ramps.
#: The twelve gun icons on this sheet are the same twelve objects that sheet
#: draws, so they are shaded by its code and coloured out of its ramps rather
#: than out of a matching set kept here — see the comment over `WEAPONS`.
import make_guns as guns  # noqa: E402

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
RED: Ramp = [rgb(c) for c in ("#3a0d0c", "#5e1512", "#8a1f19", "#b52c22", "#d94a34")]
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
# The manifest is keyed by ITEM KEY, not by position, so this list only has
# to CONTAIN every key `server/app/loot.py` can produce — it does not have to
# match its order. Guns and ammunition boxes are generated there off the
# weapons catalog, so a new weapon needs one entry down at the bottom of this
# list and nothing else; a weapon with no entry draws nothing and is still
# collectable, which is the right way round for an art gap to fail.
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
        "rusty_can",
        {"r": RUST, "m": METAL},
        [
            ".rrrr.",
            "rmmmmr",
            "rmmmmr",
            "rmmmmr",
            "rmmmmr",
            ".rrrr.",
        ],
    ),
    (
        "torn_map",
        {"c": CLOTH, "w": WOOD},
        [
            ".cccccc.",
            "cccccccc",
            "ccwcc.cc",
            "cccwccwc",
            "cc.ccwcc",
            ".cccc.c.",
        ],
    ),
    (
        "spark_plug",
        {"m": METAL, "c": CLOTH},
        [
            "..mm..",
            "..mm..",
            ".mmmm.",
            ".cccc.",
            ".cccc.",
            "..mm..",
            "..m...",
        ],
    ),
    (
        "license_plate",
        {"m": METAL, "c": CLOTH},
        [
            "mmmmmmmmm",
            "mcc.cc.cm",
            "mc.c.c.cm",
            "mmmmmmmmm",
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
        "car_battery",
        {"k": OBSIDIAN, "s": RUST, "m": METAL},
        [
            "..m..m..",
            ".ss..ss.",
            "kkkkkkkk",
            "kkkkkkkk",
            "kkkkkkkk",
            "kkkkkkkk",
        ],
    ),
    (
        "first_aid",
        {"w": CLOTH, "r": RED},
        [
            "wwwwwwww",
            "wwwrrwww",
            "wwwrrwww",
            "wrrrrrrw",
            "wrrrrrrw",
            "wwwrrwww",
            "wwwrrwww",
        ],
    ),
    (
        "road_flare",
        {"g": GOLD, "r": RED},
        [
            "..gg..",
            ".gggg.",
            "..rr..",
            "..rr..",
            "..rr..",
            "..rr..",
        ],
    ),
    (
        "wrench_set",
        {"m": METAL},
        [
            "mm..mm..",
            "mm..mm..",
            ".mmmm...",
            "..mm....",
            "..mm....",
            "..mm....",
            "..mm....",
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
        "morphine",
        {"m": METAL, "c": CRYSTAL},
        [
            "..mm..",
            "..cc..",
            "..cc..",
            "..cc..",
            "..mm..",
            "...m..",
            "...m..",
        ],
    ),
    (
        "police_radio",
        {"k": OBSIDIAN, "c": CRYSTAL, "m": METAL},
        [
            "...m...",
            "...m...",
            ".kkkkk.",
            ".kccck.",
            ".kkkkk.",
            ".kkkkk.",
            ".kkkkk.",
        ],
    ),
    (
        "night_vision",
        {"o": OLIVE, "c": CRYSTAL},
        [
            "oooooooo",
            "occoocco",
            "occoocco",
            "oooooooo",
            "..o..o..",
        ],
    ),
    (
        "bone_charm",
        {"b": BONE, "r": LEATHER},
        [
            "..r..r..",
            "...rr...",
            "..bbbb..",
            ".b.bb.b.",
            "..bbbb..",
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
        "ritual_dagger",
        {"m": METAL, "b": BONE, "w": WOOD},
        [
            "...m...",
            "...m...",
            "...m...",
            "...m...",
            "..bbb..",
            "...w...",
            "...w...",
        ],
    ),
    (
        "bank_ledger",
        {"l": LEATHER, "g": GOLD, "c": CLOTH},
        [
            "llllllll",
            "lggggggl",
            "lgccccgl",
            "lgccccgl",
            "lggggggl",
            "llllllll",
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
        "obsidian_totem",
        {"k": OBSIDIAN, "g": GOLD},
        [
            ".kkkk.",
            "kkkkkk",
            "kgkkgk",
            "kkkkkk",
            "kgkkgk",
            "kkkkkk",
            ".kkkk.",
        ],
    ),
    (
        "ancestor_skull",
        {"b": BONE, "g": GOLD, "k": OBSIDIAN},
        [
            ".bbbb.",
            "bbbbbb",
            "gggggg",
            "bkbbkb",
            "bbbbbb",
            ".b..b.",
        ],
    ),
    # AMMUNITION, and the three of them are drawn to be told apart at a glance
    # in a HUD cell the size of a fingernail. Not by colour — by COUNT and
    # HEIGHT of the rounds standing in the case: three short ones is pistol,
    # four tall ones is rifle, and one big one on a black case is the AWP.
    # A player reading a box across a dark clearing is deciding whether the
    # walk is for them, and "which calibre" is the only question they have.
    (
        "ammo_pistol",
        {"g": GOLD, "o": OLIVE},
        [
            "..g.g.g..",
            "..ggggg..",
            ".ooooooo.",
            ".o.....o.",
            ".ooooooo.",
        ],
    ),
    (
        "ammo_rifle",
        {"g": GOLD, "o": OLIVE},
        [
            ".g.g.g.g.",
            ".g.g.g.g.",
            ".ggggggg.",
            "ooooooooo",
            "o.......o",
            "ooooooooo",
        ],
    ),
    (
        "ammo_awp",
        {"g": GOLD, "k": OBSIDIAN},
        [
            "...g...",
            "..ggg..",
            "..ggg..",
            "..ggg..",
            ".kkkkk.",
            ".kkkkk.",
        ],
    ),
    # Two more calibres, and they are told apart from the three above by the
    # same rule: COUNT and HEIGHT of what is standing in the case, never by
    # colour alone. Six stubby rounds packed tight is the SMG — more of them
    # than the pistol has and shorter than the rifle's — and the shotgun is
    # the one case in the set whose contents are not brass at all.
    (
        "ammo_smg",
        {"g": GOLD, "o": OLIVE},
        [
            "gg.gg.gg.",
            "ggggggggg",
            ".ooooooo.",
            ".o.....o.",
            ".ooooooo.",
        ],
    ),
    # RED SHELLS ON A BRASS BASE, and this is the only ammunition icon in the
    # game with a colour of its own. It has earned it: a shotgun shell is the
    # one round a player has ever actually held, everybody already knows it is
    # a red plastic tube, and the shell reserve is the smallest and most
    # precious in the game — it should read from further away than the others.
    (
        "ammo_shell",
        {"r": RED, "g": GOLD, "o": OLIVE},
        [
            ".rr.rr.rr",
            ".rr.rr.rr",
            ".gg.gg.gg",
            "ooooooooo",
            "o.......o",
            "ooooooooo",
        ],
    ),
    # The condensed core. Never scattered and never in a crate: the only thing
    # that makes one is overfeeding a rift and shutting it, and what it is
    # WORTH comes off that rift rather than off the catalog — so this frame is
    # the only fixed thing about it. The drop and the bag slot carry the value,
    # the weight, and the SCALE this sprite is drawn at, which is why the art
    # is a cut shard with no baseline detail: it has to survive being drawn at
    # twice the size without reading as a boulder.
    (
        "rift_shard",
        {"c": CRYSTAL, "v": PEARL, "s": STONE},
        [
            "...cc...",
            "..cccc..",
            ".cvvvcc.",
            "cvvccvvc",
            ".cvvvcc.",
            "..svvs..",
            "...ss...",
        ],
    ),
]


# ---------------------------------------------------------------------------
# THE WEAPONS, AND THEY ARE NOT PAINTED BY `_blit`.
#
# Everything above is lit by the diagonal falloff in `_blit`: brighter at the
# top-left, darker at the bottom-right, one key light on a small standing
# prop. That is right for a bottle and it is what the guns used to get too —
# and it is exactly the shading `make_guns.py` threw out, because a weapon in
# this game is drawn from ABOVE on a row grid where a pixel's plane is a
# function of its ROW. The two sheets are the same twelve objects, so a player
# who picks up the thing on the floor has to get the thing they were looking
# at, and for as long as the floor copy was lit from the upper left and the
# held copy was lit from the sky, they did not.
#
# So these rows are painted by `make_guns.paint_rows` — the generator's own
# painter, imported, not reimplemented — with `make_guns`' own material ramps.
# Not a matching palette: THE SAME ONE. A copied constant is a constant that
# drifts, and the whole reason this comment exists is that it already had.
#
# What changes between the two sheets is exactly two things, and both are
# forced by the cell rather than chosen:
#
#   * LENGTH. A held frame is 24px wide and a loot cell is 16, so every map
#     here is the held map with its barrel and stock SHORTENED — S16's rule
#     that a smaller variant deletes rather than shrinks. Class order still
#     holds (knife shortest, AWP longest), it is just compressed;
#   * ORIGIN. A held weapon is centred in its frame because it turns around
#     its grip. One on the ground is planted on the bottom of the cell like
#     every other icon here, so it sits on the tile instead of hovering.
#
# The muzzle marker `m` is gone: it exists on the held sheet so the tracer
# knows where the barrel ends, and nothing on the floor fires. Everything else
# is the same alphabet — t stock, r receiver, h handguard, b barrel, g grip,
# n magazine, c can, e optic, l lens, k mechanical, x recess.
# ---------------------------------------------------------------------------

WEAPONS: list[tuple[str, Palette, Art]] = [
    (
        "glock18",
        {"r": guns.STEEL, "b": guns.STEEL, "f": guns.POLY,
         "g": guns.GRIP, "n": guns.MAG},
        [
            "..........",
            "..rrRRrbbb",
            "..rxrrrbb.",
            ".ffffxf...",
            ".ggg......",
            "ggg.......",
            "gnn.......",
        ],
    ),
    (
        "usp_s",
        {"r": guns.STEEL, "f": guns.POLY, "g": guns.GRIP,
         "n": guns.MAG, "c": guns.CAN},
        [
            ".......ccccc.",
            "..rrrrrCCCCc.",
            "..rxrrrccccc.",
            ".ffffxf......",
            ".ggg.........",
            "ggg..........",
            "gnn..........",
        ],
    ),
    (
        "dual_berettas",
        {"r": guns.CHROME, "b": guns.CHROME, "f": guns.POLY, "g": guns.GRIP},
        [
            "............",
            "..rrRRrrbbb.",
            "..rxrrrrbb..",
            ".ffffxf.....",
            "gggrrrrrrbb.",
            ".ggrxrrrrbb.",
            "..fffxf.....",
        ],
    ),
    (
        "deagle",
        {"r": guns.CHROME, "b": guns.CHROME, "k": guns.CHROME,
         "f": guns.CHROME, "g": guns.GRIP, "n": guns.MAG},
        [
            "....kkkkk....",
            "..rrRRrrbbbbb",
            "..rxrrrrbbbb.",
            ".fffffxf.....",
            ".ggg.........",
            "ggg..........",
            "gnn..........",
        ],
    ),
    (
        "mp7",
        {"t": guns.POLY, "r": guns.POLY, "h": guns.POLY, "b": guns.STEEL,
         "f": guns.POLY, "g": guns.GRIP, "n": guns.MAG, "k": guns.STEEL},
        [
            "......kk......",
            "tttxrrRRrrhbbb",
            "ttxrrrrrrrhbb.",
            "..ffffxff.....",
            "....gg........",
            "....gg........",
            "....nn........",
        ],
    ),
    (
        "p90",
        {"r": guns.POLY, "h": guns.POLY, "b": guns.STEEL, "f": guns.POLY,
         "g": guns.GRIP, "n": guns.TAN},
        [
            "..nnnnnnn.....",
            "rrrrRRrrrhbbb.",
            "rrxrrrrrrhbb..",
            ".fffffxff.....",
            "....gg........",
            "....gg........",
            "...ff.........",
        ],
    ),
    (
        "xm1014",
        {"t": guns.POLY, "r": guns.STEEL, "h": guns.POLY, "b": guns.STEEL,
         "f": guns.POLY, "g": guns.GRIP, "n": guns.MAG},
        [
            "..............",
            "tttxrrRRhhbbbb",
            "ttxrrrrrhhbbb.",
            "..fffxfnnnnn..",
            "....gg........",
            "...gg.........",
            "..gg..........",
        ],
    ),
    (
        "famas",
        {"r": guns.POLY, "h": guns.POLY, "b": guns.STEEL, "f": guns.POLY,
         "g": guns.GRIP, "n": guns.POLY, "k": guns.STEEL},
        [
            "...kkkkk......",
            "rrrrrRRrhhbbb.",
            "rrxrrrrrhhbb..",
            ".ffffxff......",
            "..nn.gg.......",
            "..nn.gg.......",
            "..nn..........",
        ],
    ),
    (
        "ak47",
        {"w": guns.WOOD, "r": guns.STEEL, "b": guns.STEEL, "f": guns.STEEL,
         "g": guns.GRIP, "n": guns.TAN, "k": guns.STEEL},
        [
            "........k.....",
            "wwwxrrRRkwwbbb",
            "wwwxrrrrkwbbb.",
            ".fffxff.......",
            "...gg...nn....",
            "..gg....nnn...",
            "..g......nn...",
        ],
    ),
    (
        "m4a1s",
        {"t": guns.POLY, "r": guns.POLY, "h": guns.POLY, "c": guns.CAN,
         "f": guns.POLY, "g": guns.GRIP, "n": guns.MAG, "k": guns.STEEL},
        [
            "...kkkk...ccc.",
            "ttxrrRRrhhcccc",
            "ttxrrrrrhhccc.",
            ".ffxfff.......",
            "...gg..nn.....",
            "..gg...nn.....",
            "..g....nn.....",
        ],
    ),
    (
        "awp",
        {"o": guns.OLIVE, "r": guns.STEEL, "b": guns.STEEL, "e": guns.OPTIC,
         "l": guns.LENS, "f": guns.STEEL, "g": guns.GRIP, "n": guns.MAG},
        [
            "...eeell......",
            "ooxrrRRrbbbbbb",
            "ooxrrrrxbbbbb.",
            ".ooxffff......",
            "....gg..nn....",
            "...gg...nn....",
            "...g....nn....",
        ],
    ),
    # The knife. Never on the ground and never in a crate — this frame exists
    # so the fixed hotbar cell has something to draw and the tooltip has
    # something to name. Drawn STRAIGHT, like its held frame: every gun above
    # hangs a grip below its barrel, so a blade that did the same would be a
    # sixth pistol in a row of cells.
    #
    # FOUR ROWS, NOT SEVEN, and that is not a shortcut. `paint_rows` takes a
    # pixel's plane from its row INDEX, so a map that stops at row 3 is a map
    # of an object with nothing hanging under it — which is what a knife is.
    # Padding it out to seven with blank rows would draw the same pixels and
    # then plant them three rows too high in the cell.
    (
        "knife",
        {"b": guns.CHROME, "k": guns.STEEL, "g": guns.GRIP},
        [
            "...k......",
            "ggkkbBBbbb",
            "ggkkbbbbb.",
            "...k......",
        ],
    ),
]


def _weapon_blit(art: Art, ramps: Palette, cell: int) -> Image.Image:
    """One weapon icon, on `make_guns`' row grid and planted on the tile.

    The origin is the only thing this adds: a held frame centres, and a thing
    lying on the floor sits on the bottom of its cell the way every other icon
    on this sheet does. Outlined in the LOOT sheet's own colour rather than the
    gun sheet's — the two differ by four values out of 255, and one sheet with
    one outline beats a hairline seam nobody can see but a diff can.
    """
    width, height = guns.art_size(art)
    img = guns.paint_rows(art, ramps, (cell, cell),
                          ((cell - width) // 2, cell - height - 1))
    outline(img, OUTLINE)
    return img


def build(args) -> Path:
    tile = args.tile
    out_dir = PROCESSED_DIR / "loot"
    out_dir.mkdir(parents=True, exist_ok=True)

    painted = (
        [(key, _blit(art, pal, tile)) for key, pal, art in ITEMS]
        + [(key, _weapon_blit(art, pal, tile)) for key, pal, art in WEAPONS]
    )
    pack([frame for _, frame in painted], tile, tile).save(out_dir / "sheet.png")

    manifest = {
        "tile": tile,
        "frameWidth": tile,
        "frameHeight": tile,
        "frames": len(painted),
        "items": {key: {"frame": index} for index, (key, _) in enumerate(painted)},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out_dir}: {len(ITEMS)} items + {len(WEAPONS)} weapons @ {tile}x{tile}")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE,
                    help="must match TILE_SIZE in server/app/config.py")
    args = ap.parse_args()
    build(args)


if __name__ == "__main__":
    main()
