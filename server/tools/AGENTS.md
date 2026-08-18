# server/tools/ — asset pipeline

## Purpose

Offline scripts that produce every pixel the game ships. They are never
imported by `app/` and never run at request time.

## Ownership

| script | stage | output |
| --- | --- | --- |
| `make_placeholder_sheet.py` | generates raw art | `assets/raw/<name>.png` (player, zombie variants, backpack, zhat-*, zcloth-*) plus `<name>-death.png` for exact creatures and their overlays |
| `process_sprites.py` | raw → production | `assets/processed/<name>/` |
| `make_coin.py` | generates final pixels | `assets/processed/coin/` (8-frame Y-spin of the PURPLE dark gold disc — the player's currency, and the only one with a world sprite) |
| `make_textures.py` | generates final pixels | `assets/processed/terrain/` (4 grounds, blend, patch, rock, tree, deadtree, stump, grass, bush, branch, leaves, fern, campfire) |
| `make_scenery.py` | generates final pixels | `assets/processed/scenery/` (tent, fence, sign, logs, firepit, blood, tracks, clothes, debris) — and PACKS what `make_objects.py` drew into the same folder and the one manifest |
| `make_objects.py` | draws only; `make_scenery.build()` packs it | the INTERACTIVE objects and the tribal ground: barrel, box, chest, stash, vehicle, altar, statue, bones, oil |
| `make_vfx.py` | generates final pixels | `assets/processed/vfx/` (summon, kindle, aura, wind, death) |
| `make_rift.py` | generates final pixels | `assets/processed/rift/` (the CONSOLE and the threshold kit: torch, torchfire, egress paving, the paid console's aura — plus the retired anomaly sheets, still generated and no longer drawn: scar, pillar, charge, crown, emerge, rift ×4 tiers, collapse ×4 tiers, residue, corrupt) |
| `make_platform.py` | generates final pixels | `assets/processed/platform/` (the extraction platform: the cargo skid ×3 states cold/standby/alarm, a lift drone ×2 postures hover/cruise, rotor and strobe loops, standby and siren lamp glare, the imprint it leaves, rotor downwash, the ground-break burst) |
| `make_gore.py` | generates final pixels | `assets/processed/gore/` (6 wound decals worn by a hit body) |
| `make_loot.py` | generates final pixels | `assets/processed/loot/` (one 16x16 frame per item, including gun icons) |
| `make_guns.py` | generates final pixels | `assets/processed/guns/` (held side-view, one 18x8 frame per weapon, plus its carry pose) |
| `make_merchant.py` | generates final pixels | `assets/processed/merchant/` (the shopkeeper: `idle` loop plus three one-shot flourishes — `coat`, `beckon`, `coin` — and the manifest's `randomClips` / `randomGap` that drive them) |
| `make_store.py` | generates final pixels | `assets/processed/store/` (the merchant's own kit: table ×4 with `topY`, torch ×2 with `flameY`, rug, torchfire, buy glow) |
| `make_hud_icons.py` | generates final pixels | `assets/processed/hud/` (battery, backpack, coin, darkcoin, arrow) |
| `make_audio.py` | generates final samples | `assets/processed/audio/` (35 sounds, 66 wavs + manifest + loudness.json) |

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
- `paint_coin` strikes BOTH currencies and `ramp` is the only thing that
  differs: `COIN_RAMP` is the group's gold (`hud/coin.png` alone), and
  `DARK_COIN_RAMP` is the player's dark gold (`coin/` plus `hud/darkcoin.png`).
  The purple ramp has five steps to gold's four because purple has less
  luminance to spend, and it is held below `--rarity-epic`'s brightness so a
  coin on the ground cannot be mistaken for an epic drop's aura. `groove`
  sinks a struck ring in NORMALISED radius, so it squashes with the spin
  instead of sliding off the face.
- Terrain, HUD icons and the world coin have **no raw stage** — they are
  generated straight into `assets/processed/`. The coin disc is `paint_coin`
  in `make_textures.py`; the HUD badge is that disc face-on, the pickup
  sheet is the same disc spun. Guns are the same: `make_guns.py` writes the
  held side-view; `make_loot.py` writes the 16x16 ground/HUD icons under the
  same keys. Do not fold them — a 16px isometric pistol rotated around a
  grip is mush. Pistol grips are a solid block — no heel hole, no selector.
  At this size a 1px loop is eaten by the outline and reads as a circle.
  **The knife is on both sheets and is drawn STRAIGHT on both** — handle,
  crossguard and blade on one line, with the guard the only thing leaving
  it. Every gun in these lists hangs a grip below its barrel, so a blade
  with any drop at the back is a sixth pistol at 16px whatever the blade
  is doing. It is also the shortest silhouette in both files: length is
  how these sheets say range.
- `make_guns.py`'s manifest carries POSE as well as pixels: `hold` (world px
  along aim from the body centre to the grip — how far in front of the
  character the thing is carried) and `scale`. Both are written as exception
  maps rather than as columns on every row, because five of six entries are
  guns held the one way guns are held. The knife is the exception on both:
  held in against the body, drawn at 0.8. A single carry distance for
  everything is what made the blade read as a sword floating beside the
  sprite.
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
- Prop frames are VARIANTS, except the campfire's (a LOOP) and the animated
  object sheets' (a ONE-SHOT). An animated sheet is `kinds` × `animFrames`,
  packed kind-major, frame 0 of each kind being its idle pose. Whether that
  one-shot is a barrel bursting or a lid hinging up is the SERVER's business
  (`crates.ObjectType.verb`) and never the sheet's — the art contract is
  identical either way, which is why one set of fields covers both. The old
  `breakFrames` name is gone with the single crate sheet it described. The
  crate
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
  `client/src/game/lobby-scene.ts`; object one-shot / wind life / death in
  `client/src/game/game.ts`). `wind` is the empty-object gust — greyscale,
  drawn without a player tint. `death` is the same family: dirt and air
  kicked when a body hits the floor. `sfx_zombie_death` puts its thud on
  `DEATH_IMPACT`.
- **The HUD arrow is an ARROW.** `make_hud_icons.make_arrow` draws a
  triangular head on a shaft with a small nock flare, procedurally, so the head
  and the shaft are DIFFERENT WIDTHS — that is the only thing that keeps it
  legible at 26 screen pixels while it rotates. The sprite it replaced was a
  caret (a wedge crossed by a bar), and a rotating caret reads as a cross or a
  plus rather than as something with a front and a back. Authored pointing
  RIGHT; `ExitGuide` applies the `atan2`.
- **`make_rift.py` used to draw the whole extraction point and now draws its
  DRESSING.** The extraction point is a cargo platform (`make_platform.py`);
  what survived here are the four sheets that were never about the anomaly,
  because they are about a THRESHOLD somebody set up:
  - `console` — the one thing on the map you press, in four STATES, and the
    index is authoritative: idle, armed, READY, spent. Nothing here may be
    rolled the way an object kind is. The verbs behind those states did not
    change when the structure did — wake it, load it, launch it, and a dead
    button afterwards — so neither did the sprite. READY is the same lectern,
    the same plunger and the same pips with the light in them moved to the warm
    end of the prism, so it reads as this console having changed its mind
    rather than as a different object.
  - `torch` (an unlit PROP) and `torchfire` (a looping VFX in the anomaly's
    prism, anchored on the post's BASE — the frame is taller than the torch,
    and `anchorY` is not its height, because the fire needs rows above the post
    to burn into). The exit corridor wears four of these and every extraction
    pad wears one. **That sharing is the point rather than a saving**: one
    flame in this game means "a threshold somebody dressed", and the pad is the
    other end of the errand the exit is.
  - `aura` — the band a PAID console throws until somebody sends the platform.
    It belongs to the CONSOLE and is anchored on the console's contact. Its hue
    is a function of POSITION around the band rather than of what threw it, the
    only effect in the game that works that way, which is what makes it look
    like nothing else on the map.
  - `egress` — cut paving for the exit's threshold. Its grout is DASHED and
    only its interior split runs solid: these decals sit on adjacent tiles, so
    a continuous seam at every boundary is a bright grid however faint you make
    it. Its slab bodies go into BOTH halves — the dark grain alone vanished
    into a night forest and the field read as a net with nothing between the
    strands.
  - **The anomaly's own sheets are still generated and nothing draws them**:
    `scar`, `pillar`, `charge`, `crown`, `emerge`, `rift` ×4 tiers, `collapse`
    ×4 tiers, `residue`, `corrupt`. They are kept because the art is worth
    keeping, and everything the file documents about them still holds — the
    structural seams (`build` measures `charge`→`crown`, `emerge`→`rift` and
    `rift`→`collapse` and refuses to write if any is non-zero), the tier files,
    the empty `collapse` tail, and the anomaly drawn as ABSENCE with its cells
    spread by the golden angle. Do not delete them, and do not wire them back
    into the pad: the extraction point is a machine now.
  - Its hue is `--scene-beacon` (118 255 196) in `client/src/styles/index.css`.
    The `BEACON` ramp bakes it into the prop sheets, because a prop's colour is
    its material. Move the CSS variable and this ramp moves with it.
- **`make_platform.py` is the EXTRACTION POINT, and like `make_rift.py` before
  it, it writes into all three shapes at once** — because the thing it draws is
  made of three kinds of object. `platform` is a bottom-anchored PROP in the
  depth sort; `drone` is a PROP drawn in the AIR pass (the aircraft never
  touch the floor); `imprint` is a flat DECAL split into a `multiply` half and
  a `lighter` half; `rotor`, `strobe`, `standby`, `siren`, `downwash` and
  `burst` are VFX resolved out of an intensity field and drawn additively over
  the darkness. That split is the design, not an accident of filing.
  - **THE DRONES DO NOT LIVE ON THE SKID.** They used to be parked at its
    corners, which made the pad look like a complete machine waiting to be
    switched on. It is a LOADING DOCK: the aircraft come when it calls them.
    This file draws a drone in the two postures a flight has — pitched forward
    crossing the clearing, level once it is holding station over its corner —
    and nothing that implies one was ever standing on the ground here.
  - **`IRON` is imported from `make_rift.py`, not re-typed.** The console you
    press is bolted beside the deck it operates, and one game has one steel in
    it. The rest of the palette is local because it is local: `RUST` runs
    DOWNWARD from seams because water does, `HAZARD` is the one saturated
    colour on the prop and earns it (black-and-yellow chevrons are how a 16px
    world says "machinery, stand clear"), and `STATUS` is green because every
    other light in this game is fire or the beacon's mint and a machine
    reporting that it is running must be neither. `RED_GLARE` is the alarm: the
    same red the client washes the clearing with, so the baked lamp and the
    siren glow are one light.
  - The prop frames are STATES: `platform` is cold / green standby / red
    alarm (only the corner lamps differ), `drone` is hover / cruise. A drone
    whose props are painted on never spins — the blades are `rotor`'s job.
  - **A rotor is a SMEAR, not a shape.** Drawing blades and stepping them round
    strobes horribly at any frame rate a sheet can afford, so what is drawn is
    the disc the blades sweep with one bright arc running round it. Diagonal
    pairs counter-rotate like a real quad, so the four are never in lockstep.
  - **`standby` and `siren` are the corner lamps' glare**, not the bulbs. The
    bulbs are baked into the platform sheet; these sheets are additive light
    on top. Standby breathes green. Siren is a rotating bar of red with a
    hard leading edge, 12 frames at 16 fps — `sfx_siren` is one turn of that
    loop.
  - `imprint` is the one sheet here the player WATCHES ARRIVE: it is uncovered
    on the frame the skid breaks ground, so it has to land as an answer to
    "what was under there" at that moment. A soft RECTANGLE, never an ellipse —
    the thing that stood here had corners, and rounding them off loses the clue
    that says a machine was sitting here rather than that something burned.
  - `burst` is a one-shot and `build` enforces the rule every one-shot follows:
    the first and last frames must be empty. A tail with alpha in it leaves
    dust hanging over a bare imprint forever.
  - **`layout` ships the arrangement with the art**, in TILE offsets in the
    same coordinate language as `scenery.Piece` — `server/app/rift.py`'s
    `_PLATFORM` / `_DECK` / `_CONSOLE` / `_TORCH` mirror it exactly and if one
    moves the other has to. There is no parked-drone list. Three entries are
    in PIXELS and are the exception on purpose: `eyes` (where on the sprite
    each rope ends), `lamps` (where the corner glare sits), and `rope.length`
    (how much line a drone pays out). The client flies the rigging from those
    numbers, because a rope between a fixed eye and an aircraft that arrives,
    ties on, strains and then leaves cannot be a sprite — and `rope.length`
    alone is what sets the hover height, since an arriving drone stations
    itself one rope above its eye.
- Shared helpers (`pick`, `hash01`, `clamp01`, `pack`, `rgb`, the ramps) live in
  `make_textures.py` and are imported by the other generators, so every sheet
  keeps one shading vocabulary. Do not copy them.
- **There is a second vocabulary in `make_textures.py` and it is for LIGHT**:
  `BEAM`, `ellipse`, `add`, `ease_in`, `ease_out`, `quantize_alpha`, `resolve`.
  An effect is not painted shape by shape, it is SUMMED into a float field and
  resolved once — so overlapping shapes add up and the crossing of two tongues
  is the hot core, which is impossible to fake by drawing in order.
  `make_vfx.py`, `make_rift.py` and `make_platform.py` all build their sheets
  out of these, which is what keeps a rotor disc, a siren sweep and the
  summon column lit in the same steps instead of becoming three kinds of glow.
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
  `sfx_crate_break` fits inside the barrel break strip. `sfx_zombie_death`
  lands on `DEATH_IMPACT`. `sfx_siren` is one turn of `siren.png` (12 frames
  at 16 fps = 0.75s) and plays once per sweep for the whole pickup. Changing
  a sheet's `frames / fps` means changing its sound.
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
    steps, loot, objects, the lamp, the transitions). Keep `sfx` narrow: somebody
    turning combat down must not lose their own footsteps with it. A sound in
    the wrong bus is a slider that does not do what its label says.
- **The knife's place on the ladder IS the weapon.** `knife-swing` and
  `knife-hit` ride `sfx` with the guns and sit eleven-plus dB under them,
  because quiet is the reason to carry a blade at all and a mix that made it
  as loud as a Glock would take that away in the one channel the player
  cannot turn off. Its three swing variants are NOT interchangeable the way
  a footstep's are: the caller forces one per combo step (0 and 1 are the
  slashes, 2 is the slower, lower cut), the same trick `sfx_rarity` uses.
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
- **The store's sheets are toned like scenery, because the camp is OUTDOORS.**
  It was an interior once and its art was authored lit; it is a clearing now,
  so everything here stands in the same forest at night and is multiplied by
  the same darkness pass the trees are. Only the FIRE breaks that, and only
  because it is drawn additively after that pass.
- **`make_store.py` draws only what the trader BROUGHT.** No ground, no walls:
  the clearing is `make_textures.py`'s soil and trees, and the shelter is
  `make_scenery.py`'s tent. A second tent sheet would only be a slightly
  different one, and a store-specific floor would put a rectangle of somewhere
  else in the middle of a forest.
- **The camp's torch is NOT the threshold torch.** `make_rift.py` also draws a
  torch and its fire, but that one burns the prism — cyan and violet, because
  it marks a way through: the exit corridor and every extraction pad. This one
  is warm (`FLAME`), because it is a man's campfire on a stick. Sharing the
  sheet would say the merchant's pitch and an extraction point are the same
  kind of place, which is the one thing the scene must not say. Both are
  `tinted: false` for the same reason: a flame is a ramp from a dull red root
  to a white core, and a draw-time multiply is a single hue.
- **`table.topY` is gameplay geometry living in the art, and that is correct.**
  It is the pixel row a weapon rests on, per table frame, and the four tables
  are deliberately three different heights (a trestle, a board over boxes, a
  board over a barrel). One hardcoded offset client-side would float one gun
  and sink another. `lamp.flameY` is the same contract for where a lamp burns.
- **The merchant is CLIPS, not a walk cycle.** He never moves, so he ships an
  `idle` loop plus one-shot flourishes and a manifest that says which ones may
  interrupt (`randomClips`) and how long the gaps are (`randomGap`). Adding a
  fourth flourish is a recipe here plus a name on that list — the client reads
  both and needs no change. Nothing about him is on the wire.

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
python tools/make_rift.py
python tools/make_platform.py
python tools/make_merchant.py
python tools/make_store.py
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
  must leave `assets/processed/` byte-identical. That is also how a refactor of
  the shared helpers is proved safe — move a ramp or a field primitive, re-run
  every generator, and nothing under `assets/processed/` may move.
- `make_platform.py` checks the one rule its own sheets can break: `burst` is a
  one-shot, so `build` measures its first and last frames' alpha and refuses to
  write if either carries any. A tail with alpha in it leaves dust hanging over
  a bare imprint for the rest of the night.
- `make_rift.py` checks its own seams: it prints the worst channel difference
  at every handoff — `charge`→`crown`, `emerge`→`rift`, and `rift`→`collapse`
  for each tier — and exits non-zero if any is anything but 0. It also refuses
  a `collapse` whose last frame is not fully transparent. A handoff that pops
  is the one artifact that gives away that the rift is a sprite.
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
