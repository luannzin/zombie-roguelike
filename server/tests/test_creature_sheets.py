"""The dead, as the client will actually receive them.

Run:  python tests/test_creature_sheets.py   (from server/)

THREE CONTRACTS, AND NONE OF THEM HAS A RUNTIME SYMPTOM.

  1. **Every creature has a corpse, and every accessory has one too.** A
     missing `-death` folder is not an error in the client — `loadCharacterSheet`
     warns and returns null, the body simply stops being drawn on the frame it
     dies, and what the player sees is a zombie that vanishes. The same hole in
     a `zhat-*` is a cap that stays hanging in the air where the head used to
     be, which is the loudest possible bug in a corpse.
  2. **The sheets are the shape the renderer assumes.** Four rows (down, left,
     right, up) by three walk columns; a death sheet is a one-shot timeline of
     at least three. Nothing at runtime checks this: a sheet processed at the
     wrong grid draws a slice of the neighbouring frame and reads as glitch art.
  3. **THE VARIANTS ARE DIFFERENT SHAPES, not different palettes.** This is the
     one worth having. S15's test is to draw them in solid black and see if you
     can still tell them apart, and for a long time you could not: one head box,
     one body box, one stride, three colour schemes. That is invisible to every
     other check in this repository — the sheets load, the grids match, the game
     runs, and the forest is full of one creature wearing three coats. Here it
     is arithmetic: take each creature's alpha mask and count the pixels that
     differ. Recolour one of these creatures into another and this fails.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

PROCESSED = Path(__file__).resolve().parents[2] / "assets/processed"

CREATURES = ("zombie", "zombie-husk", "zombie-brute")
ACCESSORIES = (
    "zhat-cap",
    "zhat-beanie",
    "zhat-hardhat",
    "zcloth-vest",
    "zcloth-jacket",
    "zcloth-tie",
)
TILE = 16
ROWS = 4
WALK_COLUMNS = 3
#: How many pixels of one frame's mask two creatures must disagree about
#: before they count as two creatures. The three that pass today are 34, 35
#: and 59 apart out of roughly a hundred lit pixels each, so this floor leaves
#: about a quarter of the smallest margin — enough that a legitimate tweak to
#: a stride or an arm does not trip it, and nowhere near enough for a recolour.
SILHOUETTE_MIN = 26
#: Columns of the UPPER PROFILE that have to differ, and this is the sharper
#: half of the test: S15 says the top contour is what carries an asset's
#: identity, so two creatures telling the same story about where their head
#: and shoulders are is the failure even if the rest of the mask disagrees.
#: Today's three differ over 10, 12 and 12 columns of sixteen.
CONTOUR_MIN = 7


def sheet(name: str) -> Image.Image:
    path = PROCESSED / name / "sheet.png"
    assert path.exists(), f"{name}: no processed sheet — run process_sprites.py"
    return Image.open(path).convert("RGBA")


def mask(name: str, column: int = 1) -> set[tuple[int, int]]:
    """The silhouette of one frame: every pixel that is not transparent."""
    image = sheet(name)
    frame = image.crop((column * TILE, 0, (column + 1) * TILE, TILE))
    pixels = frame.load()
    return {
        (x, y)
        for y in range(TILE)
        for x in range(TILE)
        if pixels[x, y][3] > 0
    }


def contour(name: str) -> dict[int, int | None]:
    """The upper profile: the first lit row in each column, or None."""
    silhouette = mask(name)
    profile: dict[int, int | None] = {}
    for x in range(TILE):
        column = [y for (px, y) in silhouette if px == x]
        profile[x] = min(column) if column else None
    return profile


def main() -> None:
    for name in CREATURES + ACCESSORIES:
        walk = sheet(name)
        assert walk.height == TILE * ROWS, (
            f"{name}: {walk.height}px tall, expected {TILE * ROWS} "
            f"(down / left / right / up)"
        )
        assert walk.width == TILE * WALK_COLUMNS, (
            f"{name}: {walk.width}px wide, expected {TILE * WALK_COLUMNS} walk frames"
        )
        dead = sheet(f"{name}-death")
        assert dead.height == TILE * ROWS, f"{name}-death: wrong row count"
        columns = dead.width // TILE
        assert columns >= 3, (
            f"{name}-death: {columns} frames — a collapse is a timeline, not a swap"
        )

    # S15, as arithmetic. Down-facing idle, which is the pose a player meets.
    masks = {name: mask(name) for name in CREATURES}
    for first in range(len(CREATURES)):
        for second in range(first + 1, len(CREATURES)):
            one, other = CREATURES[first], CREATURES[second]
            apart = len(masks[one] ^ masks[other])
            assert apart >= SILHOUETTE_MIN, (
                f"{one} and {other} are the same shape ({apart} pixels apart). "
                f"A variant is an anatomy, not a palette — see make_zombie.py"
            )
            profiles = contour(one), contour(other)
            columns = sum(1 for x in range(TILE) if profiles[0][x] != profiles[1][x])
            assert columns >= CONTOUR_MIN, (
                f"{one} and {other} have the same top contour ({columns} columns "
                f"differ). S15: the upper profile is the identity — distinguish "
                f"them by head and shoulder, not by colour"
            )

    # And each of them has to BE a creature: something in the top half (a head)
    # and something in the bottom (legs it stands on). A sheet that processed
    # to an empty or clipped frame passes every check above.
    for name, silhouette in masks.items():
        assert any(y < TILE // 2 for _, y in silhouette), f"{name}: no head"
        assert any(y >= TILE - 3 for _, y in silhouette), f"{name}: nothing to stand on"

    print(f"ok ({len(CREATURES)} creatures, {len(ACCESSORIES)} accessories)")


if __name__ == "__main__":
    main()
