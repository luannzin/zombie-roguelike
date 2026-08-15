# assets/ — art

## Purpose

Two stages of art: source material that is never shipped, and the production
output the game actually loads.

## Ownership

- `raw/` — source art (`player.png`, `zombie.png`, `zombie-husk.png`,
  `zombie-brute.png`, `backpack.png`, `zhat-*.png`, `zcloth-*.png`)
  and font sources (`fonts/DepartureMono-Regular.otf`). **Never served.**
- `inspiration/` — reference recordings a generator was tuned AGAINST, never
  shipped and never decoded at runtime (`gun/*.mp3`). They are the measuring
  stick for a synthesized sound, not a fallback for one: nothing in `client/`
  or `server/app/` may read this folder.
- `processed/` — production art: `player/`, `zombie/`, `zombie-husk/`,
  `zombie-brute/`, `zhat-*/`, `zcloth-*/`, `coin/`, `backpack/`
  (`sheet.png` + `manifest.json`), `terrain/`, `scenery/`, `vfx/`, `gore/`,
  `loot/`, `guns/` (held side-view), `hud/`, and `audio/` (16-bit mono wavs +
  `manifest.json`) — the folder is art too,
  generated the same way, and `/audio/shot-0.wav` is served like any sprite.
  Vite's `publicDir` points here, so these files are fetched as
  `/player/sheet.png`, `/backpack/sheet.png`, `/zombie-husk/sheet.png`,
  `/zhat-cap/sheet.png`, `/terrain/ground_loam.png`,
  `/scenery/cabin.png`, `/loot/sheet.png`, `/guns/sheet.png`, `/hud/backpack.png`,
  `/hud/coin.png`, ….
- `terrain/` is the PLACE — soil, stone, wood that grew there — and the client
  scatters it off the map seed. `scenery/` was carried in by somebody, and it
  arrives placed in groups from `server/app/scenery.py`. Two folders because
  they are positioned by two different systems, not because they look different.

## Local Contracts

- Files here are **generated output, not hand-edited source.** Everything in
  `processed/` is reproducible by rerunning a script in `server/tools/`; edit
  the generator, not the PNG.
- Raw character art is a 3x3 grid of frames on solid magenta (`#FF00FF`), rows
  down/side/up, col 1 idle. Terrain, HUD icons and the world coin have
  no raw stage. The pickup is `make_coin.py` — the HUD disc, spinning.
- Processed character sheets are rows down/left/right/up × 3 frames, at
  `TILE_SIZE` from `server/app/config.py`.
- Four shapes of art, and the shape decides how it is drawn: a seamless GROUND
  atlas, a bottom-anchored PROP silhouette with an outline, a flat DECAL with
  neither, a BODY MARK (`gore/`) stamped inside a creature's sprite frame,
  and a HELD gun (`guns/`) rotated around its grip. See `server/tools/AGENTS.md`.
- Sound has two shapes and the manifest says which: a ONE-SHOT, rendered in
  several seeded variants so repeats do not surface, and a looping BED whose
  ends were crossfaded to meet. `audio/manifest.json` also carries each sound's
  `gain` and `bus` — the mix is generated output, not client code.
- A folder name here is the asset key the server ships in
  `welcome.config` (`enemyTypes[*].sprite`, `enemyTypes[*].variants`,
  `hats`, `clothes`, `coinSprite`, `backpackSprite`) — renaming a folder
  is a protocol-visible change.
- `backpack/` is a gear overlay: same 4×3 character grid as `player/`,
  greyscale, registered to the processed player frame so it composites on
  the back. The client multiply-tints it with the wearer's colour.
- Zombie bodies (`zombie/`, `zombie-husk/`, `zombie-brute/`) are authored
  on that same 16×16 grid and processed `--exact`, so hats (`zhat-*`) and
  clothes (`zcloth-*`) lock to the head and torso the way the backpack
  locks to the player. Accessory sheets bake their own colour — enemies
  are drawn untinted.
- `guns/` is the held side-view: one 26×12 frame per weapon, pointing right,
  grip and muzzle in the manifest. The same keys have 16×16 icons on `loot/`
  for the ground and the hotbar. Do not rotate a loot icon in the hand.
- The client reads `processed/` only. Nothing may import from `raw/`; the font
  is bundled from `client/src/assets/fonts/` instead.

## Work Guidance

- Adding art means adding a generator run in `server/tools/`, then committing
  both the script change and its output.

## Verification

- Rerun the relevant generator and confirm `git status` shows only the intended
  files changed — output is deterministic.
