# server/tools/ — asset pipeline

## Purpose

Offline scripts that produce every pixel the game ships. They are never
imported by `app/` and never run at request time.

## Ownership

| script | stage | output |
| --- | --- | --- |
| `make_placeholder_sheet.py` | generates raw art | `assets/raw/<name>.png` (player, zombie variants, backpack, zhat-*, zcloth-*) plus `<name>-death.png` for exact creatures and their overlays |
| `process_sprites.py` | raw → production | `assets/processed/<name>/` |
| `make_coin.py` | generates final pixels | `assets/processed/coin/` (8-frame Y-spin, same disc as the HUD badge) |
| `make_textures.py` | generates final pixels | `assets/processed/terrain/` (4 grounds, blend, patch, rock, tree, deadtree, stump, grass, bush, branch, leaves, fern, campfire) |
| `make_scenery.py` | generates final pixels | `assets/processed/scenery/` (cabin, tent, fence, sign, logs, crate, firepit, blood, tracks, clothes, debris) |
| `make_vfx.py` | generates final pixels | `assets/processed/vfx/` (summon, kindle, aura, wind, death) |
| `make_gore.py` | generates final pixels | `assets/processed/gore/` (6 wound decals worn by a hit body) |
| `make_loot.py` | generates final pixels | `assets/processed/loot/` (one 16x16 frame per item, including gun icons) |
| `make_guns.py` | generates final pixels | `assets/processed/guns/` (held side-view, one 18x8 frame per weapon) |
| `make_hud_icons.py` | generates final pixels | `assets/processed/hud/` (battery, backpack, coin) |
| `make_audio.py` | generates final samples | `assets/processed/audio/` (32 sounds, 59 wavs + manifest + loudness.json) |

## Local Contracts

- Raw sprite input is a grid of frames on solid magenta (`#FF00FF`); rows
  are down/side/up, col 1 is idle. Walk sheets are 3 columns.
  `process_sprites.py` keys, crops, normalizes, mirrors the side row and
  writes `sheet.png` + `manifest.json` with rows down/left/right/up. Gear
  overlays (backpack, zhat-*, zcloth-*) and exact creatures (zombie variants)
  skip the crop: they are authored on the processed 16x16 player grid and
  processed with `--exact`. A creature (and each zhat-* / zcloth-*) also
  writes `<name>-death.png`: an N-column collapse timeline, last column the
  prone rest. Process that with the same `--exact --side-facing right`
  command. Never rotate a 16px walk frame to fake a corpse.
- Terrain, HUD icons and the world coin have **no raw stage** — they are
  generated straight into `assets/processed/`. The coin disc is `paint_coin`
  in `make_textures.py`; the HUD badge is that disc face-on, the pickup
  sheet is the same disc spun. Guns are the same: `make_guns.py` writes the
  held side-view; `make_loot.py` writes the 16x16 ground/HUD icons under the
  same keys. Do not fold them — a 16px isometric pistol rotated around a
  grip is mush. Pistol grips are a solid block — no heel hole, no selector.
  At this size a 1px loop is eaten by the outline and reads as a circle.
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
- **`gore/` is the third destination and it is a fourth shape: a mark on a
  BODY.** Not a standing prop, not a flat decal baked into the ground, not a
  vfx timeline. Its frames are wound VARIANTS in their own baked colour, drawn
  with the sprite in the entity pass and lit by the same night the sprite is —
  so they are not greyscale, not tinted at draw time and never additive. The
  client rolls one per landed hit and the creature carries it (see
  `client/src/render/gore.ts`). At 8px a wound reads by WEIGHT and DIRECTION,
  not outline, and nothing here is outlined: a keyline lifts the mark off the
  body and it becomes a sticker. Keep each frame to a handful of pixels — four
  of them share one 16px creature, and a heavy sheet paints a red silhouette
  over the thing the lantern just found.
- **There is one blood.** `BLOOD` lives in `make_textures.py` beside
  `COIN_RAMP`, for the same reason: the stain a scene left on the floor
  (`make_scenery.py`) and the wound a bullet just opened (`make_gore.py`) have
  to be the same material, or the forest has two kinds of blood in it.
- `tracks.png` bakes one frame per compass point rather than being rotated at
  draw time. A 16px print through a canvas rotate is grey mush, and heel-vs-toe
  is the whole value of a footprint. `TRACK_DIRECTIONS` here and in
  `app/scenery.py` are one number.
- Prop frames are VARIANTS, except the campfire's (a LOOP) and the crate
  sheet (kinds × one-shot break, packed kind-major, idle is frame 0 of
  each kind). A looping sheet's frames must LOOP: every wobble is a sine
  of the frame phase (or an integer multiple), so the last frame hands
  back to the first with no snap. A break strip is a TIMELINE: last
  frames near-empty, no wrap. Do not use `rng` per frame; it stutters
  at the wrap even when each frame looks right alone.
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
  `client/src/game/lobby-scene.ts`; crate smash / wind life / death in
  `client/src/game/game.ts`). `wind` is the empty-crate gust — greyscale,
  drawn without a player tint. `death` is a body hitting the floor, tinted
  with blood at draw time; `sfx_zombie_death` puts its thud on `DEATH_IMPACT`.
- Shared helpers (`pick`, `hash01`, `clamp01`, `pack`, `rgb`, the ramps) live in
  `make_textures.py` and are imported by the other generators, so every sheet
  keeps one shading vocabulary. Do not copy them.
- Shared drawing helpers live in `make_textures.py` and are imported, not
  copied, so all generated art keeps one shading vocabulary.
- **`make_audio.py` is the same idea for sound.** The helpers above its RECIPES
  banner are the synthesis vocabulary — sources, envelopes, biquads, space,
  arrangement — and a sound is a short paragraph written in them. It is stdlib
  only (`wave`, `math`, `random`, `array`): no numpy, so regenerating the
  game's assets never needs a compiled dependency.
- Sound obeys the sheet rules restated for samples:
  - **Variants, not one file.** Anything that fires more than about once a
    second (steps, shots, impacts, growls) renders several from different seeds;
    the client picks one and detunes it. One sample replayed is the audible twin
    of `rng` per frame in a looping sheet.
  - **Beds must loop.** They are rendered longer than they ship and `loopify`
    crossfades the tail over the head — same discipline as a looping sheet being
    a sine of the frame phase. `--only` re-renders one sound; the manifest is
    always rewritten whole.
  - **Timelines align to the sheet they play with.** `sfx_kindle` and
  `sfx_summon` put their impact on the frame `make_vfx.py` flashes, and
  `sfx_crate_break` fits inside the crate smash strip. `sfx_zombie_death`
  lands on `DEATH_IMPACT`. Changing a sheet's `frames / fps` means changing
  its sound.
  - **The mix is MEASURED, not guessed.** `CATALOG` authors a `level_db` on one
    ladder; the generator renders the sound, measures its loudness with a
    BS.1770 K-weighted meter (`loudness_lufs`) and computes the manifest `gain`
    that lands it there. So two sounds written at the same level are the same
    loudness, and the client needs no per-bus trim — which is what makes 50 on
    one of the game's volume sliders match 50 on another. Hand-picked gains were
    wrong by up to 22 dB, and every one of those errors was inaudible until it
    was next to the sound it clashed with.
  - Loudness is the loudest **150 ms window**, not the integrated file. The
    window is the ear's own integration time: integrated loudness divides by
    duration, so it calls a 40 ms tick quiet and boosts it into a bang while
    rating a long soft chime as loud.
  - One gain per SOUND, from the mean of its variants — never per file, or the
    levelling irons out the variation the variants exist to provide.
  - `loudness.json` is **committed output**, not a scratch cache: the manifest's
    gains are derived from it, so `--only` on a tree without it cannot produce a
    correct manifest. The generator says so loudly rather than shipping unity
    gains.
  - Every one-shot is DC-blocked and faded on the way out (`build`), so no
    recipe has to remember. Beds are exempt from both: a filter's settling
    transient at the head would re-open the seam `loopify` just crossfaded shut.
  - **`bus` is a player-facing grouping**, because each one is a fader in the
    game's Opções panel: `ui` (the interface answering), `ambient` (the loops),
    `sfx` (**guns and zombies only**) and `misc` (everything else that happens —
    steps, loot, crates, the lamp, the transitions). Keep `sfx` narrow: somebody
    turning combat down must not lose their own footsteps with it. A sound in
    the wrong bus is a slider that does not do what its label says.
- Every zombie sound is one instrument (`_throat`) and the differences are
  contour and envelope, so they come from one creature. **A growl is ROUGH, not
  LOW**: `_wander` (cycle-to-cycle pitch instability) and `_grind` (irregular
  amplitude) are what separate it from a moo, and dropping the fundamental to
  find menace instead produces livestock. The `sub` subharmonic seasons it and
  must stay well under the roughness — pushed too far it becomes the strongest
  periodic component, the ear takes THAT as the pitch, and the sound lands back
  in the same hole an octave down.
- The bonfire at rest and the bonfire that roars on launch are built from the
  same two helpers (`_fire_roar`, `_fire_spit`). A kindle written as a generic
  whoosh-and-boom is an explosion, and reads as cutting to a different fire.
- The menu and lobby chrome have NO sounds — no hover, no click. Both existed
  and were cut; do not re-add them as a convenience. The `ui` bus now carries
  only the refusal and the bag, which belong to the game rather than to the
  chrome.
- One-shots are 22050 Hz, beds 16000 Hz, all 16-bit mono. The beds are the bulk
  of the ~2.3 MB output; if that ever needs to come down, encoding them is the
  lever, not shortening them.

## Work Guidance

Run from `server/` with the venv python:

```bash
python tools/make_placeholder_sheet.py --name player
python tools/process_sprites.py --name player --tile 16
python tools/make_placeholder_sheet.py --name backpack
python tools/process_sprites.py --name backpack --tile 16 --exact --side-facing right
python tools/make_placeholder_sheet.py --name zombie
python tools/process_sprites.py --name zombie --tile 16 --exact --side-facing right
python tools/process_sprites.py --name zombie-death --tile 16 --exact --side-facing right
python tools/make_placeholder_sheet.py --name zombie-husk
python tools/process_sprites.py --name zombie-husk --tile 16 --exact --side-facing right
python tools/process_sprites.py --name zombie-husk-death --tile 16 --exact --side-facing right
python tools/make_placeholder_sheet.py --name zombie-brute
python tools/process_sprites.py --name zombie-brute --tile 16 --exact --side-facing right
python tools/process_sprites.py --name zombie-brute-death --tile 16 --exact --side-facing right
python tools/make_placeholder_sheet.py --name zhat-cap
python tools/process_sprites.py --name zhat-cap --tile 16 --exact --side-facing right
python tools/process_sprites.py --name zhat-cap-death --tile 16 --exact --side-facing right
python tools/make_textures.py
python tools/make_scenery.py
python tools/make_vfx.py
python tools/make_gore.py
python tools/make_loot.py
python tools/make_guns.py
python tools/make_hud_icons.py
python tools/make_coin.py
python tools/make_audio.py
```

- A new character or item is `--name` (plus `--height` for taller entities); art
  sets live in `ENTITIES` / `EXACT` / `GEAR` in `make_placeholder_sheet.py`.
- Gear overlays (backpack) are authored on the processed 16x16 player grid and
  processed with `--exact --side-facing right`, so they composite on the body
  with no extra offset. The backpack is GREYSCALE: the client multiply-tints
  it with the wearer's colour. Zombie hats and clothes bake their colour —
  enemies are drawn untinted.
- Zombie variants are `EXACT` creatures on that same grid, processed
  `--exact`, so a hat or vest registers on every body. Hats are `zhat-*`
  (`cap`, `beanie`, `hardhat`), clothes are `zcloth-*` (`vest`, `jacket`,
  `tie`) — same `--exact --side-facing right` command as `zhat-cap`. Each
  of those also ships a `<name>-death` sheet (collapse timeline, last
  frame the prone rest). Process the death raw the same way.
- Detail finer than 2 raw pixels does not survive the downscale to a 16x16
  frame — read features need luminance contrast, not hue.

## Verification

- Re-run the generator and check `git status`: a script that has not changed
  must leave `assets/processed/` byte-identical.
- Audio has no eyes to check it with, so check it with numbers: a wav must have
  a peak in range, no DC offset, both edges at zero, no samples pinned at the
  rail, and — for a bed — a wrap discontinuity small against its own local RMS.
  A loop that fails that last one clicks once per cycle forever.
- After changing a level or a recipe, confirm the ladder still holds: for each
  sound, `measured LUFS + 20*log10(gain)` must equal `REFERENCE_LUFS +
  level_db`. It lands within hundredths of a dB, so anything larger means a
  sound was re-rendered without its measurement being refreshed. Check no
  `0.97 * gain` exceeds 1.0 while you are there.
- **Tune a sound against references by measuring, not by adjective.** Reference
  recordings live in `assets/inspiration/<sound>/`; the browser decodes mp3
  natively, so an FFT in a page gives band energies, spectral centroid, 85%
  rolloff and decay times for both the references and the generated wav on one
  scale. `shot` was rebuilt this way after two blind passes overshot in
  opposite directions — the number that found it was the 150 Hz - 1 kHz share,
  which the references all put at 24-44% and the synthesized version had at
  3.6%. Aim to land INSIDE the range the references span, not on their average:
  four real gunshots disagree with each other far more than the remaining error
  does, so an average is a sound nothing actually makes.
