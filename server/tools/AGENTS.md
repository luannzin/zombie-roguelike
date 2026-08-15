# server/tools/ — asset pipeline

## Purpose

Offline scripts that produce every pixel the game ships. They are never
imported by `app/` and never run at request time.

## Ownership

| script | stage | output |
| --- | --- | --- |
| `make_placeholder_sheet.py` | generates raw art | `assets/raw/<name>.png` (player, zombie, coin, backpack) |
| `process_sprites.py` | raw → production | `assets/processed/<name>/` |
| `make_textures.py` | generates final pixels | `assets/processed/terrain/` (4 grounds, blend, patch, rock, tree, deadtree, stump, grass, bush, branch, leaves, fern, campfire) |
| `make_scenery.py` | generates final pixels | `assets/processed/scenery/` (cabin, tent, fence, sign, logs, crate, firepit, blood, tracks, clothes, debris) |
| `make_vfx.py` | generates final pixels | `assets/processed/vfx/` (summon, kindle, aura) |
| `make_loot.py` | generates final pixels | `assets/processed/loot/` (one 16x16 frame per item) |
| `make_hud_icons.py` | generates final pixels | `assets/processed/hud/` (battery, backpack) |

## Local Contracts

- Raw sprite input is a 3x3 grid of frames on solid magenta (`#FF00FF`); rows
  are down/side/up, col 1 is idle. `process_sprites.py` keys, crops, normalizes,
  mirrors the side row and writes `sheet.png` + `manifest.json` with rows
  down/left/right/up. Gear overlays (backpack) skip the crop: they are
  authored on the processed 16x16 player grid and processed with `--exact`.
- Terrain and HUD icons have **no raw stage** — they are generated straight into
  `assets/processed/`.
- Generation is deterministic: the same command must produce byte-identical
  PNGs. Do not introduce unseeded randomness.
- `--tile` must match `TILE_SIZE` in `app/config.py`.
- Non-square props (rock, tree, deadtree, stump, grass, bush, fern, campfire and
  everything in `scenery/props`) are bottom-anchored silhouettes with alpha,
  centred on their tile or contact point; only the `ground_*.png` atlases tile
  seamlessly.
- **DECALS are the third shape and they are drawn differently.** `patch`,
  `branch`, `leaves` and everything in `scenery/decals` lie FLAT: no outline, no
  silhouette, no implied face toward the camera. The client bakes them into its
  ground canvas. Giving one a keyline makes it read as a thing standing up at
  ankle height.
- There are FOUR ground atlases and a map mixes them. Every feature inside one
  must stay well under a tile — the atlas repeats every 4 tiles, and one blob a
  tile wide draws a legible checker on the floor. Structure at map scale is the
  client's material field's job. `blend.png` is the set of alpha stencils that
  dissolve one soil into the next; its frames are graded by COVERAGE, thresholded
  by rank so each step differs from the last by exactly 1/frames of the tile.
- `terrain/` is the place and `scenery/` is what people left in it. The split is
  a placement rule: terrain is scattered client-side off the map seed, scenery
  is placed server-side in groups by `app/scenery.py`. A new sheet goes in
  whichever folder matches how it will be positioned.
- `tracks.png` bakes one frame per compass point rather than being rotated at
  draw time. A 16px print through a canvas rotate is grey mush, and heel-vs-toe
  is the whole value of a footprint. `TRACK_DIRECTIONS` here and in
  `app/scenery.py` are one number.
- Prop frames are VARIANTS, except the campfire's, which are an ANIMATION —
  flagged with `animated` + `fps` in the manifest. An animated sheet's frames
  must LOOP: every wobble is a sine of the frame phase (or an integer multiple),
  so the last frame hands back to the first with no snap. Do not use `rng` per
  frame; it stutters at the wrap even when each frame looks right alone.
- VFX sheets (`make_vfx.py`) are TIMELINES, not loops — except `aura`, which
  is a looping column over epic/legendary loot. One-shots play once per event,
  with frame 0 and the last frame near-empty so there is no pop at either end.
  A looping sheet is a sine of the frame phase so the wrap does not snap.
  They are anchored on `anchorY` — the row the effect happens at, with spare
  rows BELOW it for an impact to spread into — not on the bottom edge.
- VFX sheets are GREYSCALE. An effect belonging to a player is tinted with that
  player's colour by the client (`client/src/render/vfx.ts`); the kindle roar
  is tinted with `fire.core` the same way. A hue baked in here would mean one
  sheet per colour and would not match the roster.
- A VFX sheet's `frames / fps` is the effect's duration and the client times
  itself off it. Changing either means changing whatever the client aligns to
  it (`SUMMON_TIME` / `SUMMON_IMPACT`, `KINDLE_TIME` / `KINDLE_IMPACT` in
  `client/src/game/lobby-scene.ts`).
- Shared helpers (`pick`, `hash01`, `clamp01`, `pack`, `rgb`, the ramps) live in
  `make_textures.py` and are imported by the other generators, so every sheet
  keeps one shading vocabulary. Do not copy them.
- Shared drawing helpers live in `make_textures.py` and are imported, not
  copied, so all generated art keeps one shading vocabulary.

## Work Guidance

Run from `server/` with the venv python:

```bash
python tools/make_placeholder_sheet.py --name player
python tools/process_sprites.py --name player --tile 16
python tools/make_placeholder_sheet.py --name backpack
python tools/process_sprites.py --name backpack --tile 16 --exact --side-facing right
python tools/make_textures.py
python tools/make_scenery.py
python tools/make_vfx.py
python tools/make_loot.py
python tools/make_hud_icons.py
```

- A new character or item is `--name` (plus `--height` for taller entities); art
  sets live in `ENTITIES` / `ITEMS` / `GEAR` in `make_placeholder_sheet.py`.
- Gear overlays (backpack) are authored on the processed 16x16 player grid and
  processed with `--exact --side-facing right`, so they composite on the body
  with no extra offset. They are GREYSCALE: the client multiply-tints them
  with the wearer's colour.
- Detail finer than 2 raw pixels does not survive the downscale to a 16x16
  frame — read features need luminance contrast, not hue.

## Verification

- Re-run the generator and check `git status`: a script that has not changed
  must leave `assets/processed/` byte-identical.
