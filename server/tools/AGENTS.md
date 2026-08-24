# server/tools/ — asset pipeline

## Purpose

Offline scripts that produce every pixel the game ships. They are never
imported by `app/` and never run at request time.

## Ownership

| script | stage | output |
| --- | --- | --- |
| `make_placeholder_sheet.py` | generates raw art | `assets/raw/<name>.png` (player, zombie variants, backpack, zhat-*, zcloth-*) plus `<name>-death.png` for exact creatures and their overlays |
| `process_sprites.py` | raw → production | `assets/processed/<name>/` |
| `make_coin.py` | generates final pixels | `assets/processed/coin/` (8-frame turn of the ANOMALY SHARD — dark gold, the player's currency and the only one with a world sprite. Also paints `hud/darkcoin.png` for `make_hud_icons`) |
| `make_textures.py` | generates final pixels | `assets/processed/terrain/` (4 grounds, blend, patch, rock, tree, deadtree, stump, grass, bush, branch, leaves, fern, campfire) |
| `make_scenery.py` | generates final pixels | `assets/processed/scenery/` (tent, fence, sign, logs, firepit, blood, tracks, clothes, debris) — and PACKS what `make_objects.py` drew into the same folder and the one manifest |
| `make_objects.py` | draws only; `make_scenery.build()` packs it | the INTERACTIVE objects and the tribal ground: barrel, crate, box, chest, stash, vehicle, altar, statue, bones, oil |
| `make_vfx.py` | generates final pixels | `assets/processed/vfx/` (summon, kindle, aura, wind, death) — GREYSCALE, tinted at draw time |
| `make_weapon_vfx.py` | generates final pixels | `assets/processed/weapon-vfx/` (muzzle, blast, impact) — oriented, ramp BAKED IN: fire is not anybody's colour |
| `make_rift.py` | generates final pixels | `assets/processed/rift/` (the CONSOLE and the threshold kit: torch, torchfire, egress paving, the paid console's aura — plus the retired anomaly sheets, still generated and no longer drawn: scar, pillar, charge, crown, emerge, rift ×4 tiers, collapse ×4 tiers, residue, corrupt) |
| `make_platform.py` | generates final pixels | `assets/processed/platform/` (the extraction platform: the cargo skid ×3 states cold/standby/alarm, a lift drone ×2 postures hover/cruise, rotor and strobe loops, standby and siren lamp glare, the imprint it leaves, rotor downwash, the ground-break burst) |
| `make_gore.py` | generates final pixels | `assets/processed/gore/` (6 wound decals worn by a hit body) |
| `make_loot.py` | generates final pixels | `assets/processed/loot/` (one 16x16 frame per item, including gun icons) — banded volume out of `paint_form`, keyed and planted on an offset ground shadow |
| `make_armor.py` | generates raw art AND processes it | `assets/raw/armor-*.png` + `assets/processed/armor-<slot>-<material>/` (twenty worn overlays on the player's own 16x16 grid: five shapes x four materials, one pose block, ramps IMPORTED from `make_loot.py` so the plate on the floor and the plate on the body are the same colour by construction). The one script here that runs `process_sprites` itself — twenty pairs of commands in this file is a list nobody keeps in step |
| `make_wolf.py` | generates raw art AND processes it | `assets/raw/wolf*.png` + `assets/processed/wolf/`, `wolf-twin/`, `wolf-alpha/`, each with a `-death`, plus `wolf-alpha-sleep/` (THE PACK — one quadruped, `Build.heads` is a tuple of offsets, so one head is a wolf and three is the miniboss and there is only one drawing. Painted in three passes: mass, then a keyline traced off the whole mask, then the details that are allowed to break it. The sleep sheet LOOPS and has no corpse — a state, not an event) |
| `make_guns.py` | generates final pixels | `assets/processed/guns/` (held high-3/4, one 20x9 frame per weapon, plus its carry pose) |
| `make_sawyer.py` | generates final pixels | `assets/processed/sawyer/` (THE FIRST BOSS — one 128x120 rig, eight clips in four facings: `idle`, `walk`, `chop`, `rip`, `rev`, `death`, plus a facing-less `sweep` and the `arrive` cinematic, and the thrown crescent `slash` / `slash-burst` in eight baked headings) |
| `make_merchant.py` | generates final pixels | `assets/processed/merchant/` (the shopkeeper — green coat, brimmed HAT, a face with two eyes in it: `idle` loop plus three one-shot flourishes — `coat`, `beckon`, `coin` — and the manifest's `randomClips` / `randomGap` that drive them) |
| `make_store.py` | generates final pixels | `assets/processed/store/` (the merchant's own kit, all in the shop's own warm `WOOD`/`LINEN` and flat-filled: his WAGON ×1 and counter ×1, small round table ×4 with `topY`, `kit` ×5 — crates, a barrel of rods, a rack, a shelf, a padlocked strongbox, all drawn SHUT because nothing in this zone opens — torch ×2 with `flameY`, rug, torchfire, buy glow) |
| `make_machine.py` | generates final pixels | `assets/processed/machine/` (the upgrade cabinet, two tiles wide and cartoon-flat: body ×2 idle/settled with the reel windows, pay line, lever pivot and tray mouth in its manifest; `strip.png` — the reel BAND, one tall image of ten cells the client scrolls; lever ×6 sweeping on a real angle; marquee, reel backlight and payout burst, all greyscale so the client can tint them by rarity) |
| `make_ultimates.py` | generates final pixels | `assets/processed/ultimates/` (one 20x20 mark per ultimate). THE ONE ICON SHEET DRAWN WITH MATHS rather than with character maps, and the reason is in its header: every other icon sheet holds OBJECTS, and all four of these are ENERGY — an arc, a round with a lance, a fan of tracers, a pulse — whose shapes are circles and rays. It checks itself against `app.ultimates` when the server is importable |
| `make_skills.py` | generates final pixels | `assets/processed/skills/` (one 16x16 icon per skill in catalog order, plus the payout TIN in five rarity colourways at 16x18 — a dark pass and an emissive pass, with the label window's rectangle on the manifest) |
| `make_hud_icons.py` | generates final pixels | `assets/processed/hud/` (battery, backpack, coin, darkcoin, arrow, chevron) |
| `make_audio.py` | generates final samples | `assets/processed/audio/` (48 sounds, 88 wavs + manifest + loudness.json). Creature voices are resolved by PREFIX — `EnemyType.voice` names one and the client asks for `<voice>-idle` / `-alert` / `-death` — so a creature's whole vocabulary is three recipes here and one field there |

## Route

A generator draws a thing the **game** already defines. If the task changes what
the thing IS — its footprint, verb, drop table, where it is placed — that is
[`docs/design/world.md`](../../docs/design/world.md) and `server/app/`, and the
art follows. If it only changes how it LOOKS or SOUNDS, this directory plus
[`docs/design/presentation.md`](../../docs/design/presentation.md) is the whole
surface. Output rules live in [`assets/AGENTS.md`](../../assets/AGENTS.md).

## Local Contracts

- Raw sprite input is a grid of frames on solid magenta (`#FF00FF`); rows
  are down/side/up, col 1 is idle. Walk sheets are 3 columns.
  `process_sprites.py` keys, crops, normalizes, mirrors the side row and
  writes `sheet.png` + `manifest.json` with rows down/left/right/up.
  **A sheet may carry that block TWICE**: three more source rows, the same
  facings drawn HOLDING something, which come out as `hold-down` /
  `hold-left` / `hold-right` / `hold-up` APPENDED after the four walk rows
  (`POSE_PREFIXES`). The player has them; nothing else does, and a sheet
  without the block is byte-for-byte what it always was. Each block is
  mirrored on its own — mirroring the walk row into the hold row would put
  the weapon in the wrong hand. Gear
  overlays (backpack, zhat-*, zcloth-*) and exact creatures (zombie variants)
  skip the crop: they are authored on the processed 16x16 player grid and
  processed with `--exact`. A creature (and each zhat-* / zcloth-*) also
  writes `<name>-death.png`: an N-column collapse timeline, last column the
  prone rest. Process that with the same `--exact --side-facing right`
  command. Never rotate a 16px walk frame to fake a corpse.
- **THE TWO CURRENCIES ARE NO LONGER TWO METALS.** `paint_coin` now strikes
  one thing — `COIN_RAMP`, the group's gold, and `hud/coin.png` is its only
  output. Dark gold is an ANOMALY SHARD: a sphere painted with `make_rift`'s
  `Prism` and its six-ramp `PRISM`, so the player's currency is made of the
  same material as the thing the whole night is spent feeding. `make_coin.py`
  owns it and paints both sizes — `coin/sheet.png` at 16px and
  `hud/darkcoin.png` at 8px, which is frame 0 with `light` turned up because
  the badge sits on a panel the night never dims. `DARK_COIN_RAMP` is deleted;
  do not reintroduce a purple ramp, the prism is the palette. `groove` on
  `paint_coin` survives for the gold disc alone.
- Terrain, HUD icons and both currencies have **no raw stage** — they are
  generated straight into `assets/processed/`. The gold disc is `paint_coin`
  in `make_textures.py`; the shard is `make_coin.make_spin_frame`, and the
  HUD badge is its frame 0 rather than a second drawing of the same object.
  Guns are the same: `make_guns.py` writes the
  held frame; `make_loot.py` writes the 16x16 ground/HUD icons under the
  same keys. Do not fold the two SHEETS — a 16px isometric pistol rotated
  around a grip is mush, and the frames differ in length and in where they
  sit in their cell. **They do share the PAINTER**: `make_loot.WEAPONS` is
  drawn by `make_guns.paint_rows` out of `make_guns`' own ramps, passing its
  own origin so the icon plants on the tile instead of centring. That import
  is the contract. "The icon matches the thing in your hands" is not a
  promise prose can keep — the two sheets ran on different shaders for as
  long as the shading was private to `make_guns`, and the floor copies were
  still lit by `_blit`'s diagonal falloff long after the held sheet had
  stopped being. Do not reintroduce a second set of gun ramps here.
  Pistol grips are a solid block — no heel hole, no selector.
  At this size a 1px loop is eaten by the outline and reads as a circle.
  **The knife is on both sheets and is drawn STRAIGHT on both** — handle,
  crossguard and blade on one line, with the guard the only thing leaving
  it. Every gun in these lists hangs a grip below its barrel, so a blade
  with any drop at the back is a sixth pistol at 16px whatever the blade
  is doing. It is also the shortest silhouette in both files: length is
  how these sheets say range.
- **ONE CAMERA FOR THE WHOLE SCENERY FOLDER, AND IT LIVES IN `make_objects.py`.**
  `SLOPE` (the 2:1 dimetric the crates are built on), the plane table
  `PLANE_TOP` / `PLANE_FRONT` / `PLANE_SIDE`, and the flat-step painter `tone`
  are public there, and `make_scenery.py` imports all four rather than keeping
  its own. Its three volume primitives — `_box`, `_billet`, `_stone` — are
  built on them, so a fence post, a felled trunk, a firepit stone and a crate
  are lit by one rule and stand on one ground plane. The reason it is a shared
  import and not a shared convention: the two modules pack into the SAME
  manifest and get placed in the same clearing by `server/app/scenery.py`, so
  any drift between them is visible in one screenshot.
- **THE OBJECT SHEETS ARE SOLIDS NOW, NOT ELEVATIONS.** `make_objects.py`
  owns four primitives — `box` (a dimetric box, three planes), `cap` (just its
  lid, at any height and any foreshortening — this is what an opening lid is),
  `dome` (caps stacked on a circular profile, for the chest) and `billet` (a
  cylinder lying down) — plus `stone` and `shadow`. Everything in the folder is
  built from them, so a fence rail, a felled trunk, a barrel hoop and a crate
  slat are the same solid in the same light. What they replaced: the barrel
  was a bulged rectangle with a token ellipse on top, the box and chest were
  courses of board seen dead-on, the five stashes were five coloured
  rectangles, the altar was a stone staircase, and the six VEHICLES were side
  elevations under a dither — no top surface anywhere, on the objects the
  camera looks down at hardest.
- **A FOOTPRINT WITH `lw == rw` IS A DIAMOND, AND A DIAMOND IS A GEM.** The
  crate sheet says it and it applies to every `box` call: unequal left and
  right runs are what make a top face read as a rectangle in perspective
  rather than as a lozenge sitting on a wall.
- **THE VEHICLE ROOF IS SWEPT, CAPPED AND RASTERISED AS A REGION**, and all
  three words are load-bearing. `VEHICLE_PROFILE` describes the line where the
  roof meets the flank, so sweeping it back along `SLOPE` generates roof,
  bonnet and boot lid in one pass with the six profiles unchanged. Sweeping
  the WHOLE silhouette shears the body into a parallelogram; plotting the
  sweep point by point leaves a checkerboard wherever two offsets round to the
  same row; and filling between the extremes without a cap paints the entire
  rear quarter of a car as roof. Sweep the top only, fill each column between
  its extremes, and clamp the band to the sweep depth.
- **A PLANE IS A BAND, AND `pick` IS NOT HOW YOU MAKE ONE.** Every prop in
  `make_scenery.py` used to be shaded `pick(ramp, <continuous value>)`, which
  dithers between the two nearest steps — so a "subtle" grain of 0.10 does not
  roughen a face, it scatters single pixels of the neighbouring step across
  it, which is the per-pixel noise S5 rules out and the reason a tent read as
  a hill and a fence as a row of pencil strokes. Use `objects.tone`, which
  lands on the step exactly. Texture is a clustered BAND (the bark strip on a
  log), never a jitter. `pick` still belongs to the DECALS, which are flat by
  contract and genuinely want a continuous value.
- **`make_guns.py`'s camera is a ROW GRID, and that is the only shading rule
  on the sheet.** The twelve weapons are drawn from above at the world's high
  3/4, seven authored rows deep, and a pixel's ramp step is a function of its
  ROW alone (`ROW_STEP`): crown, bore, near side, under-shelf, then the grip
  and magazine hanging off rows 4-6. The reason it cannot be a light azimuth
  is that the client SPINS this frame around the grip — a sprite lit from
  135deg is lit from 315deg as soon as the player turns around, so the sheet
  keys off PITCH, which survives the rotation, and every top plane is bright
  at every heading. Row 3 is deliberately darker than row 4: it is the seam
  (S10) that stops a magazine welding itself to a receiver. The alphabet is
  one letter per PART — stock, receiver, handguard, barrel, grip, magazine,
  can, optic, lens, mechanical, muzzle — and the palette beside each map says
  what material that part is made of. Two modifiers: UPPERCASE lifts one step
  (the specular streak, S14), `x` is a recess in the shared `VOID` ramp. Do
  not reintroduce a gradient or a dither here; the flat side elevations these
  replaced were twelve stickers on a world built out of stacked volumes.
- **The row grid gives a mass its plane; ROW COUNT gives it its thickness, and
  the sheet needs both.** The first cut of the 3/4 rebuild had the grid and
  not the taper — barrel, receiver and butt all ran three rows deep for the
  whole length of every rifle — and five of the twelve came out as the same
  dark slab with a bright line on it. A weapon tapers, and on this camera the
  taper is vertical: butt four rows, receiver three, handguard three
  narrowing, barrel TWO, muzzle one. Draw the taper before drawing the parts.
- **`make_guns.py`'s ramps are derived, not picked.** `_ramp(hue, sat, lo, hi)`
  builds all five steps from S11's table, so a material is authored as where
  its ends sit and the hue-shift-and-desaturate law is written once. The `lo`
  end is the number that matters: these ramps used to bottom out a hair off
  the outline, which meant every plane the grid puts on step 0 or 1 — the
  whole underside, and the entire grip and magazine — sank into it. S7 says
  step 2 is the ambient reference and is "not black". Keep the ceilings under
  the world's own (`ROCK_RAMP` tops out at #5d5860); the lantern multiplies
  over all of it. `GRIP` is the one warm neutral on the sheet on purpose:
  grip and magazine hang on the same rows at the same two planes, so hue is
  the only thing left to tell them apart with.
- `make_guns.py`'s manifest carries POSE as well as pixels: `hold` (world px
  along aim from the body centre to the grip — how far in front of the
  character the thing is carried) and `scale`. Both are written as exception
  maps rather than as columns on every row, because eleven of the twelve
  entries are guns held the one way guns are held. The knife is the exception
  on both: held in against the body, drawn at 0.8. A single carry distance for
  everything is what made the blade read as a sword floating beside the
  sprite.
- **THE LOOT SHEET IS VOLUME, NOT STENCIL, AND THE SHADER IS AN EDGE TEST.**
  `make_loot.paint_form` breaks a character map into SUB-BLOBS — a connected run
  of one material — and a pixel's step comes from which of that blob's own edges
  it sits on: upper-left rim step 3 (lifting to 4 on a corner that points into
  the key), lower-right rim step 1, underside step 0, everything else step 2.
  It is an edge test and not a coordinate test because S7 says the terminator
  follows form curvature and never cuts straight; the first cut banded off the
  bounding box and produced forty-six identical lumps — bright cap, mid-grey
  left half, dark right half — on a bottle, a wrench and a skull alike. What
  BOTH replaced was `pick(ramp, <diagonal falloff>)`, which is a gradient (S7)
  through a ditherer (S5) lit from a direction no object on the sheet has.
- **ONE ALPHABET FOR THE WHOLE LOOT SHEET (`make_loot.ALPHABET`), and the maps
  do not carry their own palettes.** `m` is metal in all forty-six of them. The
  per-item palette dict that used to sit beside each map was forty-six chances
  for a letter to be missing from its own key, and a missing letter does not
  raise — `ramps.get` returns `None` and every pixel wearing it is dropped, so
  the gap only ever shows up on a dark tile in a live game. Two modifiers, the
  same two `make_guns.py` uses: UPPERCASE lifts one step, `x` is a recess in the
  shared `VOID`.
- **A LOOT MAP IS AUTHORED IN FIVE DECISIONS AND IN THIS ORDER**: the TOP
  CONTOUR (S15 — it carries the identity, and two items in a tier that share a
  crown are two items nobody can tell apart); the LEAN (S21 — long axis 15-20deg
  down-right, because a bilaterally symmetric icon reads as a UI glyph); HEIGHT
  OVER FOOTPRINT (S17, 1.1:1 to 1.6:1 — the old maps ran four rows tall and
  eight wide, which is why a first-aid kit, a license plate and a ledger were
  three rectangles); NOTCHES (S15, 2-4px bitten out at irregular intervals); and
  the ACCENT (S12, one hue, under 8% of pixels, and most items do not get one).
- **THE KEYLINE IS TINTED OFF THE MATERIAL IT IS KEYING AND IT BREAKS ON THE LIT
  CREST** (`make_loot._key`, and `make_skills._key_tin` / `make_platform._key`
  run the same law). One flat near-black border round every object on a sheet
  stops being part of any material and becomes a BORDER, which is what makes a
  set of objects read as stickers; and on a 16px sprite an unbroken border is
  30-40% of every opaque pixel, competing with the two brightest steps in the
  ramp. Bottom edges go darker still — that is the contact (S19).
- **EVERY LOOT ICON PLANTS ON AN OFFSET GROUND SHADOW** (S9: flat, echoing the
  FOOTPRINT rather than the silhouette, down-right, two alpha bands, no detail).
  The HUD draws this same sheet and gets one too — the alternative is two
  drawings of one object, which is the failure `make_guns.py` documents at
  length. The weapons get the same treatment for the same reason: a pistol sits
  next to a medkit on the belt.
- **`make_skills.py`'s TIN is a cylinder, and a cylinder is five VERTICAL
  BANDS** (`CYLINDER`), with the key band NOT at the silhouette's edge — the
  edge is the part turning away. It replaced a horizontal falloff through
  `pick`, which at fourteen pixels across is a smear of two neighbouring steps
  with no edge in it, on the one object the game hands the player as a reward.
  Its `RARITY` ramps are `material_ramp` off each tier's CSS hue, so the
  identity is the hue at the base step and the rest is the law. The ICONS are
  not part of this: they are flat HUD marks, centred, no contact, by contract.
- **`make_platform.py`'s skid is a HEIGHT FIELD on `make_objects`' camera slope
  but SQUARE TO THE SCREEN**, and the drone is `objects.box` pods on
  `objects.billet` arms. The footprint axes are `v` across (1px per unit) and
  `u` into the frame (`SLOPE` px per unit), so every cell of a column shares one
  screen column and the solid is a heightmap render; cells are drawn in
  descending `u` so occlusion falls out of the draw order. ARCHITECTURE IS
  AXIS-ALIGNED IN THIS GAME AND PROPS ARE CORNER-ON — the pad occupies a
  rectangle of tiles and is entered, so it is built like the shop's masonry, and
  a crate beside it is still yawed 45deg. Corner-on it projected to a lozenge
  with no square face to carry its height and no front to walk into.
  What the projection costs: a face pointing along `v` is EDGE-ON and has no
  pixels, so the right-hand boundary column of each mass steps down to
  `PLANE_SIDE` — one column, never two, or it reads as a stripe painted on the
  front. Three traps, all of which bit: every row must round on WHOLE pixels
  (`_row` rounds half UP — Python's `round` breaks .5 to even and half of a 2:1
  grid lands on .5, which combs the prop into vertical stripes); one depth cell
  is one pixel of PHYSICAL depth, the same size as one unit of `v`, so a wall
  5px thick laterally is 5 cells deep and not `5 / SLOPE`; and rivets go only
  within a few pixels of a fold, because square to the screen the deck is one
  large top face and a lattice across the whole of it reads as polka dots on a
  table rather than as fixings.
  The four lift eyes sit on the four corner posts, which corner-on was the one
  arrangement that could not have them — at 45deg two of a box's corners project
  to the same screen column and the client stationed two drones on top of each
  other. Their order is the rope contract shared with `server/app/rift.py`:
  front-left, back-right, front-right, back-left.
- **LIGHT THAT OVERLAPS IS TUNED AGAINST THE WORST CASE, NOT THE SINGLE ONE.**
  Eleven torches ring the shop and four glare sheets ring the pad, and both sets
  ADD. A flame or a lamp tuned to look right alone in a black wood sums into a
  flat sheet when there are eleven of it, which erases the object it belongs to
  — the shop read as a daylit room with fires painted on it. The numbers that
  hold this are `TORCH_FIRE_ALPHA` and the scene-light gradient stops in the
  client, the bloom ellipse and `gain` in `make_store.make_torchfire`, and the
  ceilings on `GREEN_GLARE` / `RED_GLARE` here.
- **`make_sawyer.py` IS A RIG, AND IT IS THE ONLY ONE.** Every other body in
  this pipeline is authored as ASCII rows — the player, the three creatures,
  the merchant — and that stays true; the boss is 390 frames on a 128x120
  grid, and 390 hand-authored frames of a swinging 41px weapon do not agree
  with each other about where a shoulder is. So a pose is ANGLES AND REACHES
  (`Pose`), the joints are solved (`_ik`, and every joint on him breaks
  OUTWARD — a first cut that took the bend direction off which side of the
  body a limb was on came out knock-kneed with its forearms folded across its
  own gut), and one shader bands every mass off its own distance field. Do not
  hand-place a pixel of the body here; place the mass and let the law paint
  it. The face is the exception and it is deliberate — it is the only part of
  him that is a drawing, for the reason `make_merchant.py` gives about his.
- **THE FRAME IS LAW AND THE POSE IS INTENT (`_fit`).** 128x120 is eight
  pixels short of the worst case a fully extended arm plus a fully extended
  bar can reach, so where the two disagree the arm tucks along its own angle
  and, failing that, the bar foreshortens. It is deterministic, it runs last,
  and it does NOT paper over a badly authored pose: `_off_frame` still fails
  the build if anything reaches the border afterwards, and `_fit` itself
  raises rather than silently drawing a pose no tuck can save. Two frame sizes
  were shipped and rebuilt before this existed (96x88, then 112x104), both
  chosen by eye against a standing pose, and both silently clipped the frames
  that carried the fight.
- **A ONE-SHOT ON THE BOSS SHEET STARTS AND ENDS ON `rest(facing)`**, checked
  in `build` — `make_merchant.py`'s seam rule, with one difference: the check
  compares POSES rather than pixels, because the chain phase advances across
  every clip and is supposed to keep going across the cut. Compare pixels and
  either every clip fails or the check has to be told to ignore the weapon.
- Generation is deterministic: the same command must produce byte-identical
  PNGs. Do not introduce unseeded randomness.
- `--tile` must match `TILE_SIZE` in `app/config.py`.
- Non-square props (rock, tree, deadtree, stump, grass, bush, fern, campfire and
  everything in `scenery/props`) are bottom-anchored silhouettes with alpha,
  centred on their tile or contact point; only the `ground_*.png` atlases tile
  seamlessly.
- **Every solid prop is a set of NAMED RECIPES, not rolls of one recipe** —
  `ROCK_RECIPES` (8), `TREE_RECIPES` (6 species), `DEADTREE_RECIPES` (6),
  `STUMP_RECIPES` (4 states), `BUSH_RECIPES` (5), `FERN_RECIPES` (5), and the
  sheet's frame order is the dict's order. What has to differ between two of
  them is the SILHOUETTE, and rerolling one recipe varies the noise inside a
  shape it never varies. Adding one means adding a recipe; the client picks
  its variant off `frames` in the manifest, so nothing there has to know.
- **They share one construction, and it is documented in `make_textures.py`'s
  own section comments**: masses with hard plane breaks between them, one key
  at 135deg/60deg, a step-0 seam wherever a near mass lands against a far one
  (`_tree_clump` + `_clump_stack`), root claws at the contact line
  (`_root_spurs`), a contact band inside the silhouette (`_contact`), and a
  flat offset ellipse under the FOOTPRINT (`_cast_shadow`). A tree's footprint
  is its root spread and not its canopy, which is why `_cast_shadow` takes the
  extent as numbers while `_rock_shadow` reads it off the silhouette.
- **Organic props do not carry a closed outline.** `outline()` draws one, then
  `_break_crest` removes it where the key lands (§6 of
  [`PIXEL-ART-DIRECTION-V2.md`](../../PIXEL-ART-DIRECTION-V2.md)). This is not
  cosmetic: on a bare `deadtree` armature the border was 41% of every opaque
  pixel and six silhouettes resolved as six scribbles.
- **The three low greens are ordered by DRAW DEPTH, not by taste.** `bush` is
  drawn behind bodies, `fern` in front of them, `grass` underfoot, so
  `SHRUB` > `FROND` in value and the fern gets NO cast shadow — its ellipse
  would land on the player's chest. Keep that order when touching the ramps.
- `deadtree` shares `tree`'s frame size and anchor so a blighted tile swaps
  sheets and nothing else moves. It does NOT have to share the frame COUNT.
- `campfire` is the exception to the light rule and stays one: its flame is
  EMISSIVE (§14) and ignores the key. Its stones and logs do not — they are
  built like every other prop. It is also a LOOP, so nothing in it may use
  `rng`; per-pixel variation there comes from `hash01`, which is stable across
  frames.
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
- **THERE ARE TWO POINTERS AND THEY ARE DIFFERENT SHAPES ON PURPOSE.**
  `make_arrow` is a thin dart: a triangular head on a shaft with a nock flare,
  and the head and the shaft are DIFFERENT WIDTHS, which is what keeps it
  legible at 26 screen pixels while it rotates. `make_chevron` is a solid
  TRIANGLE with a notched back, and it is what the way-out marker uses, because
  that one BLINKS — it is on screen half a second at a time and what the eye
  catches in a flash is AREA, not line. Both are authored pointing RIGHT;
  `ExitGuide` applies the `atan2`.
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
- Shared helpers (`pick`, `hash01`, `clamp01`, `pack`, `rgb`, `material_ramp`,
  the ramps) live in `make_textures.py` and are imported by the other
  generators, so every sheet keeps one shading vocabulary. Do not copy them.
- **A MATERIAL IS FOUR NUMBERS, NOT FIFTEEN HEX TRIPLES.** `material_ramp(hue,
  sat, lo, hi, steps=5)` builds a ramp out of S11's law — value on a fixed
  non-linear curve, saturation peaking in the mid-to-shadow range and dropping
  at the highlight, hue swinging cool into shadow and warm into light. It began
  as `make_guns._ramp` and moved when `make_loot.py` needed the same law for
  the same objects; it is the only place any of that is written down. A
  hand-typed ramp is five chances to break one clause silently, and the failure
  is invisible per colour and obvious per set — one material in a sheet that
  does not shift hue reads as plastic beside eleven that do. `steps=6` exists
  for the dimetric props: `make_objects` puts its top plane on step 5, so a
  five-step ramp collapses the top plane into the specular.
- **The `lo` end is the number that matters, and the CEILING is a per-sheet
  decision.** Scenery ramps sit under S11's own base-step band because a trunk
  recedes; `make_guns`' sit under those again because the lantern multiplies
  over a weapon held in a dark forest; `make_loot`'s sit ABOVE both, because a
  drop is a thing on a dark floor the player has to see from far enough away to
  decide whether the walk is worth it. Tuning a loot ramp like a tree ramp
  produces forty-six correctly-banded illegible lumps, which is exactly what
  the first cut of that rewrite produced.
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
  the clearing is `make_textures.py`'s soil and trees. A store-specific floor
  would put a rectangle of somewhere else in the middle of a forest.
- **THE WAGON SAYS HE TRAVELS AND LIVES OUT OF IT, AND NOTHING WORSE.** Guns
  racked on the flank, a line of lanterns under the eave, crates roped at the
  wheels, a lamp on the front bow. It used to hang BONE MASKS on that line and
  lay two covered bodies with their boots out at the front wheel — the argument
  being that the party should work out where the stock comes from on their own.
  The argument was fine and the result was not: the shop is the one beat of the
  loop that exists as relief from the night, and the biggest sprite in it was a
  cart with corpses under a tarp. THE RULE FOR THIS WHOLE FOLDER'S SHOP ART: it
  may be poor, worn and improvised; it may not be grim.
- **THE SHOP HAS ITS OWN TIMBER AND ITS OWN SHADING.** `WOOD` and `LINEN` in
  `make_store.py` are a step warmer and a step brighter than `make_scenery`'s
  `PLANK` and `CANVAS`, and everything on the pitch is filled FLAT (`flat()`,
  exact ramp steps) instead of dithered with `pick`. Two reasons, and both are
  about size: these props are half the size they were, and at that size a Bayer
  checker between two browns reads as dirt rather than as grain. Scenery is
  something you FIND and can be filthy; a shop is something somebody keeps.
- **THE STALLS ARE ROUND BECAUSE THEY ARE WALKED AROUND, AND SMALL BECAUSE
  THEY ARE FURNITURE.** Round: every table is approached from any side, and a
  rectangular board has a front and a back that read wrong from three of them.
  Four pedestals under four discs — the disc is the constant the eye reads and
  the leg is where the variation goes. SMALL: they were 2.25 x 2 tiles, taller
  than the gun lying on them and nearly as wide as the merchant, which put six
  objects in the middle of the shop that outweighed everything they were
  selling. 1.5 x 1.25 makes a pedestal a stand for a weapon rather than a piece
  of scenery with a weapon on it. Keep the leg THICK relative to the top: a
  wide disc on a thin stalk is a mushroom, which is exactly what the first pass
  of these looked like standing in a forest.
- **HIS GEAR IS DRAWN SHUT, and that is a gameplay contract in the art.** The
  player spent the previous night learning that a box in this game is a thing
  you open, so every frame of `kit.png` is roped, strapped, lidded or padlocked
  — a silhouette that reads "closed" is what keeps a safe zone from reading as
  unclaimed loot, and it is cheaper than any amount of prompt suppression.
- **THE MACHINE IS A TOY AND IT USED TO BE A WRECK.** `make_machine.py` drew a
  three-tile dented grey cabinet with its chrome gone, a smashed marquee corner
  and a car battery cabled to the base — the argument being that a clean
  machine would be the one object in the game that came from a different one.
  It failed twice over: at that size it was a wall in a small shop, and a dark
  dented box at night is indistinguishable from the market stalls beside it. It
  is 32x46 now — two tiles wide — and drawn FLAT in three colours: a gold hood
  with bulb sockets, a red shell, a cream fascia. The vocabulary is what may
  never be subtle: three windows in a row, a hood of bulbs, a lever on the
  right, a tray at the bottom, because a player has to read it from the door,
  before any prompt, and think *that thing is for me*. Grime is not part of
  that vocabulary and at this size it is noise on top of it.
- **THE REEL IS A BAND, NOT A FRAME NUMBER.** `strip.png` is one tall image of
  ten cells in a FIXED, deliberately unsorted order, and the client scrolls a
  one-cell window over it. It used to be nine sprites — four frames of blur
  then a hard cut to a rarity face — which read as a colour appearing in a box.
  A band buys three things no sheet of frames can: the TEASE (it decelerates
  through six or seven faces with the answer already decided), the NEAR MISS
  (the order puts a legendary next to a common, so a reel that stopped one cell
  short really did), and WEIGHT (blur is the strip drawn again at an offset
  scaled by its own speed). Commons appear four times in the band because they
  are the likeliest roll, so the strip looks like the odds it pays. Do not sort
  the band: ascending order would teach the player that blue means purple is
  next, and turn the last half second into arithmetic.
- **RARITY IS THE LABEL AND THE LIGHT, NEVER THE SHAPE.** A legendary tin is
  the same tin as a common one and a legendary reel face is the same lozenge;
  only the ramp changes. The tin used to wear its rarity on two thin bands of a
  steel tube, which at the size it actually appears at meant five tiers were
  five grey tubes — the colour is the LABEL now, the largest area on the
  object. `make_skills.py` and `make_machine.py` both
  duplicate the five `--rarity-*` colours from `client/src/styles/index.css`
  rather than importing them (these are offline scripts), and the two lists
  must stay identical — a tin that is not the colour the bag paints the same
  grade would be a second colour language for one idea.
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
- **HE HAS A FACE, AND THAT IS NOT A DETAIL.** He was a cold grey-blue hooded
  figure whose face was six pixels of void with one eye glint in it. That is
  the same silhouette this game uses for everything that wants to kill you, and
  it was survivable only while he stood on a dark rim; he is the thing in the
  MIDDLE of the shop now. So: a brimmed hat instead of a hood, skin with two
  eyes under it, a red scarf, and a GREEN coat — green because he is otherwise
  always seen against warm timber (his cart, his counter, his mat) and a brown
  coat put a brown man in front of a brown wagon.

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
python tools/make_weapon_vfx.py
python tools/make_rift.py
python tools/make_platform.py
python tools/make_merchant.py
python tools/make_store.py
python tools/make_machine.py
python tools/make_skills.py
python tools/make_gore.py
python tools/make_loot.py
python tools/make_guns.py
python tools/make_armor.py
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
- **Worn armour is `make_armor.py` and it is BAKED, not greyscale.** The
  backpack is greyscale so the client can multiply the wearer's identity
  colour through it; a plate's colour IS its material, which is the whole
  armour ladder, so it is painted in its own ramp and the drawable says so per
  layer (`GearLayer.tint`). The two live in the same `gear` list and are drawn
  by the same `blitGear`.
- **Armour overlays carry ONE pose block where the player carries two.** The
  hold pose moves ARMS; a helmet, a breastplate over the coat's centre and a
  pair of greaves sit on the three parts of this figure that are identical
  between the blocks, so a second block would be twelve sheets that are
  pixel-for-pixel the first twelve.
- **Twelve pieces are three SHAPES in four colours, and that is the opposite
  of the creature rule on purpose.** `make_zombie.py`'s variants must be three
  silhouettes because the question there is "what is that". Four helmets are
  four rungs of one ladder: the player already knows it is a helmet, and a
  ladder whose rungs are four different shapes cannot be ordered at a glance.
  See `make_armor.py`'s header and `make_loot._ARMOR_FORMS`.

## Verification

- `python tests/test_creature_sheets.py` from `server/` after touching
  `make_zombie.py`: every creature and accessory still has a `-death` timeline,
  the grids are what the renderer assumes, and the three variants are still
  three SHAPES — S15's silhouette test as arithmetic, which is the one thing
  about this sheet nothing at runtime can notice.
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
