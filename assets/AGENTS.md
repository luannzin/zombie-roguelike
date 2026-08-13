# assets/ — art

## Purpose

Two stages of art: source material that is never shipped, and the production
output the game actually loads.

## Ownership

- `raw/` — source art (`player.png`, `zombie.png`, `coin.png`) and font sources
  (`fonts/DepartureMono-Regular.otf`). **Never served.**
- `processed/` — production art: `player/`, `zombie/`, `coin/` (`sheet.png` +
  `manifest.json`), `terrain/`, `hud/`. Vite's `publicDir` points here, so these
  files are fetched as `/player/sheet.png`, `/terrain/ground.png`, ….

## Local Contracts

- Files here are **generated output, not hand-edited source.** Everything in
  `processed/` is reproducible by rerunning a script in `server/tools/`; edit
  the generator, not the PNG.
- Raw character art is a 3x3 grid of frames on solid magenta (`#FF00FF`), rows
  down/side/up, col 1 idle. Terrain and HUD icons have no raw stage.
- Processed character sheets are rows down/left/right/up × 3 frames, at
  `TILE_SIZE` from `server/app/config.py`.
- A folder name here is the asset key the server ships in
  `welcome.config` (`enemyTypes[*].sprite`, `coinSprite`) — renaming a folder is
  a protocol-visible change.
- The client reads `processed/` only. Nothing may import from `raw/`; the font
  is bundled from `client/src/assets/fonts/` instead.

## Work Guidance

- Adding art means adding a generator run in `server/tools/`, then committing
  both the script change and its output.

## Verification

- Rerun the relevant generator and confirm `git status` shows only the intended
  files changed — output is deterministic.
