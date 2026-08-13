# server/tools/ — asset pipeline

## Purpose

Offline scripts that produce every pixel the game ships. They are never
imported by `app/` and never run at request time.

## Ownership

| script | stage | output |
| --- | --- | --- |
| `make_placeholder_sheet.py` | generates raw art | `assets/raw/<name>.png` |
| `process_sprites.py` | raw → production | `assets/processed/<name>/` |
| `make_textures.py` | generates final pixels | `assets/processed/terrain/` (ground, rock, tree, grass, fern, campfire) |
| `make_hud_icons.py` | generates final pixels | `assets/processed/hud/` |

## Local Contracts

- Raw sprite input is a 3x3 grid of frames on solid magenta (`#FF00FF`); rows
  are down/side/up, col 1 is idle. `process_sprites.py` keys, crops, normalizes,
  mirrors the side row and writes `sheet.png` + `manifest.json` with rows
  down/left/right/up.
- Terrain and HUD icons have **no raw stage** — they are generated straight into
  `assets/processed/`.
- Generation is deterministic: the same command must produce byte-identical
  PNGs. Do not introduce unseeded randomness.
- `--tile` must match `TILE_SIZE` in `app/config.py`.
- Non-square props (rock, tree, grass, fern, campfire) are bottom-anchored
  silhouettes with alpha, centred on their tile; only `ground.png` tiles
  seamlessly.
- Prop frames are VARIANTS, except the campfire's, which are an ANIMATION —
  flagged with `animated` + `fps` in the manifest. An animated sheet's frames
  must LOOP: every wobble is a sine of the frame phase (or an integer multiple),
  so the last frame hands back to the first with no snap. Do not use `rng` per
  frame; it stutters at the wrap even when each frame looks right alone.
- Shared drawing helpers live in `make_textures.py` and are imported, not
  copied, so all generated art keeps one shading vocabulary.

## Work Guidance

Run from `server/` with the venv python:

```bash
python tools/make_placeholder_sheet.py --name player
python tools/process_sprites.py --name player --tile 16
python tools/make_textures.py
python tools/make_hud_icons.py
```

- A new character or item is `--name` (plus `--height` for taller entities); art
  sets live in `ENTITIES` in `make_placeholder_sheet.py`.
- Detail finer than 2 raw pixels does not survive the downscale to a 16x16
  frame — read features need luminance contrast, not hue.

## Verification

- Re-run the generator and check `git status`: a script that has not changed
  must leave `assets/processed/` byte-identical.
