# assets/ — art

## Purpose

Two stages of art: source material that is never shipped, and the production
output the game actually loads.

## Ownership

- `raw/` — source art (`player.png`, `zombie.png`, `coin.png`, `backpack.png`)
  and font sources (`fonts/DepartureMono-Regular.otf`). **Never served.**
- `processed/` — production art: `player/`, `zombie/`, `coin/`, `backpack/`
  (`sheet.png` + `manifest.json`), `terrain/`, `scenery/`, `vfx/`, `hud/`.
  Vite's `publicDir` points here, so these files are fetched as
  `/player/sheet.png`, `/backpack/sheet.png`, `/terrain/ground_loam.png`,
  `/scenery/cabin.png`, `/loot/sheet.png`, ….
- `terrain/` is the PLACE — soil, stone, wood that grew there — and the client
  scatters it off the map seed. `scenery/` was carried in by somebody, and it
  arrives placed in groups from `server/app/scenery.py`. Two folders because
  they are positioned by two different systems, not because they look different.

## Local Contracts

- Files here are **generated output, not hand-edited source.** Everything in
  `processed/` is reproducible by rerunning a script in `server/tools/`; edit
  the generator, not the PNG.
- Raw character art is a 3x3 grid of frames on solid magenta (`#FF00FF`), rows
  down/side/up, col 1 idle. Terrain and HUD icons have no raw stage.
- Processed character sheets are rows down/left/right/up × 3 frames, at
  `TILE_SIZE` from `server/app/config.py`.
- Three shapes of art, and the shape decides how it is drawn: a seamless GROUND
  atlas, a bottom-anchored PROP silhouette with an outline, and a flat DECAL
  with neither. See `server/tools/AGENTS.md`.
- A folder name here is the asset key the server ships in
  `welcome.config` (`enemyTypes[*].sprite`, `coinSprite`, `backpackSprite`) —
  renaming a folder is a protocol-visible change.
- `backpack/` is a gear overlay: same 4×3 character grid as `player/`,
  greyscale, registered to the processed player frame so it composites on
  the back. The client multiply-tints it with the wearer's colour.
- The client reads `processed/` only. Nothing may import from `raw/`; the font
  is bundled from `client/src/assets/fonts/` instead.

## Work Guidance

- Adding art means adding a generator run in `server/tools/`, then committing
  both the script change and its output.

## Verification

- Rerun the relevant generator and confirm `git status` shows only the intended
  files changed — output is deterministic.
