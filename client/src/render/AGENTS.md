# client/src/render/ — canvas renderer

## Purpose

Turns a plain `RenderState` snapshot into pixels. No network, no gameplay
mutation, no React.

## Ownership

| file | owns |
| --- | --- |
| `renderer.ts` | pass sequencing and the world/screen transform |
| `types.ts` | `RenderState`, `DrawableEntity` — the renderer's input contract (`gear` overlays, `weapon` the held gun with its whole pose in `gunKick`/`gunSwing`/`gunPump`/`gunLift` plus `gunOpen`/`gunHeat`/`gunHands`, `hitSpin` the hit tilt, `pour` the backpack coming off the back) |
| `camera.ts` | follow, clamp to map bounds, the arrival push-in |
| `framing.ts` | the wide shot of the camp — zoom and rest-shot fire position |
| `projection.ts` | zoom + offset between world and screen space |
| `sprites.ts` | sheet loading, `SpriteBook`, per-colour multiply tints |
| `terrain.ts` | terrain atlas loading (4 grounds, blend stencils, props, flat decals, the animated campfire) |
| `scenery.ts` | scenery atlas loading: standing props and flat decals of what people left |
| `vfx.ts` | effect atlas loading: one-shot sheets (summon — a lobby arrival AND a level-up — kindle, wind, death) and the looping loot `aura`. GREYSCALE, tinted per player |
| `weapon-vfx.ts` | the fire at a barrel: muzzle, the shotgun's cone, impacts. ORIENTED (rotated onto the aim about `anchorX`) and un-tinted — fire is not anybody's colour |
| `boss.ts` | the Sawyer's atlas — facing clips, the facing-less spin, the crescent's eight baked headings — and the frame picker. THE THIRD KIND OF ANIMATED THING here: clips like the merchant, authoritative like a body. `t` off the wire is the CLIP's playhead and this file does no arithmetic on it (see `client/tests/boss-clock.ts`) |
| `layers/boss-vfx.ts` | what his attacks look like WHILE THEY HAPPEN: the bar's white-hot TRAIL, the WIND circling a spin, and the crescent a landed blow leaves. `tipAt` re-derives the bar's nose from the row's playhead — it is not on the wire and must not be. There are deliberately NO ground telegraphs; the windup frames are the tell (read the header before adding one back) |
| `layers/boss.ts` | him, painted: the frame, his contact pool sized off his FOOTPRINT (never the frame), the silhouette flash on every landed hit, and the crescents |
| `rift.ts` | threshold atlas: the console prop with its four STATES, the torch prop and its fire, the paid console's band, the exit's paving |
| `platform.ts` | extraction atlas: the cargo skid (cold / green standby / red alarm) and lift drone (hover / cruise) props, rotor / strobe / standby / siren / downwash / burst effect sheets, the imprint decal, and the `layout` block the ropes and lamps are drawn from |
| `layers/rift.ts` | extraction pads: the whole rig's timing (`riftPhase`) plus its four passes — floor, depth sort, the air, additive light — and the deck's LOAD, both the pile at rest and what is still falling into it |
| `store.ts` | the merchant's own kit: his WAGON and his counter, the six small round tables (with `topY`), his gear (`kit`), torches (with `flameY`), the mat, the torch fire and the buy pool — plus the HUD coin the price tag draws |
| `machine.ts` | the upgrade cabinet's atlas: body, the reel BAND (`strip.png` — one tall image, scrolled and wrapped), lever, pay line, and the three greyscale lights (marquee, reel backlight, payout burst) the layer tints |
| `skills.ts` | the skill atlas as GEOMETRY ONLY: frame sizes, rarity order, the label window. Nothing here draws — both places a skill appears (the tray row, the payout tin) are DOM, and this is where they read the manifest from so the fetch happens once |
| `merchant.ts` | the shopkeeper's clips and the player that picks between them (`MerchantPose`, `stepMerchant`, `merchantFrame`) |
| `layers/store.ts` | his pitch drawn: mat, depth-sorted wagon / counter / tables / gear / torches / merchant / MACHINE, stock FLOATING over the table you are at, the fires, the cabinet's tinted light, the scrolling bands, the pay-line flash and the price tags |
| `layers/payout.ts` | the night's platforms being lowered into the shop's apron, the drones leaving, and the gold flying to the HUD balance |
| `loot.ts` | loot atlas: one 16x16 frame per collectable item |
| `guns.ts` | held-gun atlas and the ONE pose every reader of a held weapon shares: `gunPose`, and the grip / muzzle / port / support-hand points taken off it. The grip is measured from the body's FEET and offset off its centreline — see `GUN_GRIP_ABOVE_FEET` / `GUN_GRIP_SIDE` |
| `arms.ts` | the limbs holding it: a run of world pixels from the shoulder socket to the grip, in the player's own dyed cloth, plus the hand pixels drawn OVER the weapon. Nothing here is authored art — the sheet has four facings and the weapon points anywhere |
| `gore.ts` | gore atlas: small wound decals stamped on a body that has been hit |
| `fov.ts` | shared field of view — `light` and `heat` fields. Its two sight reaches are NOT constants here: they arrive on `VisionConfig` as `eyeScale` / `sightScale`, off `config.enemyViewDarkScale` / `enemyViewLitScale`, which is what makes an enemy see a shape exactly as far as the shape sees it |
| `wind.ts` | the shared gust field every bending thing reads |
| `shadows.ts` | the shared LIGHT field and the one routine that grounds a standing thing: an ambient contact pool plus a cast thrown away from whatever is lighting it |
| `disturbance.ts` | what bodies do to the plants they walk through |
| `layers/vision.ts` | the ENEMY's hunt diamond — fill meter and bang over the head |
| `layers/scenery.ts` | placed scenes: flat decals into the ground bake, standing props into the depth sort; live boot prints (including a blood tint) |
| `layers/corpses.ts` | blood pools under dead enemies — scenery `blood.png`, growing, world space |
| `minimap.ts` | the minimap canvas |
| `layers/` | the actual drawing: terrain, entities, loot, vision, effects, atmosphere, darkness, vignette |
| `post/grade.ts` | the `Grade` — the whole screen-effect state as one object — and the `GradeStack` that composes a base LOOK with named event layers on their own envelopes. Pure arithmetic, no DOM, no GL |
| `post/looks.ts` | every look this game wears: the three PLACES (`forestLook` / `campLook` / `shopLook`, full grades) and the EVENTS (danger, hit, extraction, payout, surge, scope, death — partials). Functions, not constants, because every colour in them comes off `index.css` |
| `post/chain.ts` | the WebGL2 finish: bright pass, three-level bloom, radial light shafts, defocus, and one composite that does aberration, fog, the grade, the wash, the vignette and the grain. Returns null on a machine without WebGL2 |

## Design law

[`docs/design/presentation.md`](../../../docs/design/presentation.md) — the light budget, effect sheets, gore, and the rule that this layer owns no state.

## Local Contracts

- The renderer consumes state and never mutates it. Players and enemies arrive
  in one `entities` list and are drawn by one path.
- `renderer.ts` only sequences passes and switches spaces; drawing lives in
  `layers/`. **The pass order is the atmosphere** — ground (soil, litter, flat
  scenery, then any extraction imprint) → dust → coins and loot sprites → entities, bonfires and standing
  scenery (one depth sort by `y`, including live objects and their one-shots, the
  console, the torch and a grounded skid) → `drawRiftAir` (ropes, inbound
  drones, an airborne skid — after the sort, before the darkness) →
  overgrowth → motes / rain / fog → darkness → combat effects → loot auras / motes /
  epic-legendary beams / empty-object wind / death burst / torch fire / corner lamps / rig glow → hunt diamond →
  labels → THE FINISH. Effects and loot light go over the darkness because
  they are light, not things being lit. An unlit drop HIDES ITS SPRITE.
  Corpses hide the same way. Blood pools sit on the floor with the boot
  prints; the fallen sprite sits with the loot, under living bodies.
  Glow, motes and the epic/legendary column leak a whisper through the
  night (`lit(visibility, floor)`) so the player can feel a find before
  the lantern reaches it — never a full beam, never the item itself.
  Loot sprites use `Projection` in the screen-space pass with the coins;
  glow, motes and beams sit in the world-space pass after darkness and
  take raw world pixels — `view.x` there would project them a second time,
  off the map. Every rarity throws specks; epic and legendary keep the
  looping column as well.
  A drop's `scale` is 1 for everything the world scatters; only a condensed
  core out of an overfed pad sets it, proportional to the overpayment, so
  "how much did we bank" is legible from the size of the thing lying in the
  grass before anyone is close enough to read a tooltip. Scaling happens about
  the CONTACT, not the centre — a bigger drop grows upward off the ground it is
  lying on, the way a bigger prop would.
  The hunt diamond goes AFTER the darkness on purpose, see below.
- **`fov.ts` is what the PLAYERS can see; `layers/vision.ts` is the ENEMY hunt
  tell.** Unrelated systems: the first is a client-side tile field that decides
  what is drawn at all, the second fills a diamond from the `aw` meter on the
  creature's snapshot row. The server still tests a sight cone (`ai.look`);
  that wedge is not drawn. Do not re-derive a floor cone here.
- **The hunt diamond sits ON the night only if this client has already seen
  the body while it was alerting** (`alertKnown`, latched in `Game`). Killing
  the lamp then does not hide that it has you. A hunter that committed in
  the dark, never seen, wears nothing — that would be a free tracker. The
  body itself still vanishes. Idle creatures (`aw` below `NOTICE_AT`) show
  nothing. The mark is drawn as world-pixel rectangles, not as type: it
  lives in the forest, not on the HUD.
- **A diamond is a REACTION, not furniture.** Below `NOTICE_AT` nothing is
  drawn at all; from there an empty lozenge appears and fills — yellow, amber,
  red — and at 1 it is hunting and stays full. Drawing one over every idle
  creature turns the dark into a diagram; hiding one on a hunter undoes the
  tell. Both failures are worse than the diamond being briefly conservative.
- Vision is a client-side visual system: the server broadcasts the whole world.
  `fov.ts` produces two fields — `light` saturates at 1 (visibility), `heat`
  keeps climbing (warmth, drawn as additive amber). Shared vision is a `max()`
  across viewers whose snapshot `lantern` is on (plus the local lamp's output).
- **`FovField.dirty` is the repaint contract.** Light only exists inside a
  light's own radius, so the field publishes the tile box it touched, unioned
  with the previous frame's (a tile that just fell dark changed too). Anything
  caching pixels per tile — `layers/darkness` — rebuilds that box and leaves
  the map alone; it must force a full pass whenever its own surfaces or its
  colours are replaced. `explored` is committed inside `shine`, never in a pass
  over the whole field.
- The minimap repaints on its own cadence, not the render clock: `Minimap.draw`
  is safe to call every frame and throttles itself. `rebuildTiles()` is the
  contract when kinds change (the forest swallowing the arrival corridor).
- **Extraction pads are on the minimap, and they obey a different vision rule
  from an enemy** — the same reason a teammate does: what the party KNOWS is
  not what the party can currently see. A dormant pad appears once its ground
  is explored and then stays; an AWAKE one appears whatever the fog says,
  because it is a beacon burning in a dark forest and there is nobody on the
  map it is a secret from; a spent one keeps a dead mark, because the point of
  a spent pad is that the map remembers. The mark is a DIAMOND and it is the
  only diamond on the widget — players and enemies are round, so a rotated
  square is the shape with the most silhouette left over at four pixels. It is
  mint while dormant or waking and GOLD once the quota is paid, matching the
  console; RED and breathing on the siren's own beat once the pickup has been
  called. Only a live one breathes, so movement alone says which to walk to.
  Pads draw UNDER the bodies: a place does not cover a person standing on it.
- **`Renderer.stampTiles` is the slam.** New TREE/ROCK on tiles that were VOID
  go into the prop bake (`TerrainLayer.stampProps`) without rebuilding soil —
  the corridor was already forest floor. `DarknessLayer.invalidatePath` drops
  the VOID crush so the ribbon recedes with the path. A full terrain reset
  here would hitch the slam.
- A `LightSource` is a light the WORLD owns — a bonfire — and it is not a
  `Viewer` with the aim zeroed: it has no cone, no battery and no lag, and it
  is warmer than any lamp. It gets its own pass (`FovField.burn`) over the same
  shadowcast, merged with the same `max()`.
- Occlusion is `world.blocksSight`, not `isSolidTile`. A campfire stops a body
  and a bullet but not light. VOID is the same for light: it is a gap between
  trees, so the beam falls in; darkness then follows the path as a falloff
  (`VOID_CRUSH_REACH`), not as a stamped rectangle, so it reads as a ribbon
  of deep woods. `LOW` is the third exception — waist-high cover you look
  over. Paint it as ground (with PROP and VOID); the standing sprite covers
  it. Treating it as a wall tile puts a rock under every barrel.
- `Camera` follows the player and nothing else. The move INTO a zone belongs to
  `game/lobby-scene.ts`, which is already showing the same place when it starts;
  by the time this camera exists the push-in is over and it opens on the frame
  it was handed. Do not add an arrival here — it would replay a shot the player
  has just watched. Game may ease `Camera.zoom` toward a weapon's `scopeZoom`
  while the AWP trigger is held (`stepScope`); rest is `ARENA_ZOOM`. That is
  a gun, not a framing rule — keep it out of `Camera`.
- `framing.ts` holds both ends of that move: `ARENA_ZOOM` is the scale the game
  is played at, and `campZoom` is the wide shot, clamped to at least one step
  below it so there is always a push to see. The wide shot's fire position
  (`CAMP_FIRE_ANCHOR` / `campFireAnchor`) lives here too, because the title
  screen and the lobby share it — two call sites with two numbers is a fire
  that jumps when you enter a room. They are read by the lobby and by
  `Camera`'s resting zoom; if they diverge, starting a run cuts to a different
  picture of the same clearing instead of continuing the shot.
- Sprites are keyed by asset name; which enemy sheets to load comes from
  `welcome.config.enemyTypes[*].sprite` plus that type's `variants` / `hats`
  / `clothes`, never a hardcoded list. Each of those also loads `<name>-death`
  (optional: missing death art falls back to the idle walk frame, never a
  rotate). The backpack overlay is `welcome.config.backpackSprite`.
- **Wounds sit on the body too, and they are the OPPOSITE of a vfx sheet.**
  `DrawableEntity.stains` are frames of the gore atlas: baked colour, no tint,
  no additive, drawn in the entity pass and multiplied by the same
  `visibility` as the body — a wound on a creature outside the lantern is as
  invisible as the creature, or blood becomes a free tracker. They go AFTER
  the hit flash, because the blink is the moment and the wound is the record,
  and the record has to outlast it. Offsets are normalised (`u` -1..1 across
  the frame, `v` 0..1 up from the feet), so the same stain lands correctly on
  a creature of any size.
- **A wound is MASKED TO THE SILHOUETTE, and that is what makes it blood
  rather than a sticker.** `drawStains` composites into a shared scratch frame
  in the sheet's own 16x16 space — marks land on the sprite's pixel grid, so
  they never straddle a half pixel and shimmer as the camera moves — then
  `destination-in` against the body frame discards everything that missed the
  creature, and only the survivor is blown up into the dest rect. Doing it in
  the other order leaves blood hanging in the transparent corners of the frame
  beside the body. The mask is the BODY, not the gear: overlays are registered
  to the same grid and live inside that outline. The scratch surface is one
  canvas for the whole game, grown to the largest frame and never shrunk —
  do not allocate one per entity per frame.
  Because the mask is unforgiving, placement (`EntityVisuals.splatter`) aims
  at the trunk and stays well inside it: a mark aimed past the edge is not
  clipped gracefully, it is deleted.
- **A POURED BACKPACK IS NOT GEAR.** While `DrawableEntity.pour` is set the
  game takes the pack OUT of `gear` and hands it here as a pose instead, and
  `drawHeldPack` draws the same sheet, row and frame through one extra
  transform: out along the aim, up, and over onto its mouth. At `grip` 0 that
  transform is the identity, which is what makes the handover from worn to held
  invisible — do not "improve" it by drawing a second sheet or by starting the
  ease anywhere but at the worn position. A character standing beside a
  platform while items appear out of them is a spawner; the same character
  holding their own bag over the deck is somebody paying for the flight home.
- **A DECK CARRIES ITS LOAD, and every position in it is relative to the
  platform's CONTACT POINT.** `game/pad-cargo.ts` owns the pile;
  `layers/rift.ts` draws it twice — with the box in the standing sort while the
  skid is on the ground, and inside `drawRiftAir` through the same
  scale/alpha/tilt once it is flying, which is what carries a night's work out
  of the map with the thing it was loaded onto. Absolute positions would leave
  the pile in the grass. Items still in the air are ALWAYS in the air pass,
  never the standing sort: the body doing the pouring stands in front of the
  deck, so sorted by feet every item would fly behind the person throwing it.
  The pile is drawn in insertion order and that is the depth order — the grid
  fills the far row first and climbs a layer at a time.
- **Gear sits on the body.** `DrawableEntity.gear` is a back-to-front list of
  overlay sheets drawn in the same facing and walk frame. A tinted target
  (the player) multiply-tints every layer — the backpack follows the wearer.
  An untinted target (a zombie) keeps the art's own colours, so hats and
  clothes can be a cap or a vest without a second identity. Overlays are
  registered to the processed 16x16 grid and blitted at the same dest rect.
  Players wear `[backpack]`; enemies wear the clothes-then-hat list the
  server rolled, or nothing.
- **A heavy hit TILTS the body.** `DrawableEntity.hitSpin` is radians around
  the feet, applied in the entity pass, health bar left upright. Knockback
  is `recoilX/Y` along the shot — the same spring a lunge uses, held for
  the stun then released. Do not rotate the shadow.
- **A gun is IN HAND, not gear.** `DrawableEntity.weapon` is a catalog key
  into the guns atlas (`make_guns.py`): side-view, pointing right, rotated
  around the grip and flipped when aim is left. An empty hand draws nothing.
  `gunMuzzle` in `guns.ts` is the barrel tip — tracers start there, not at
  the body. Do not rotate a loot-atlas icon; that sheet is the ground/HUD
  face. There is no laser sight. The knife is one more frame on that same
  sheet and needs no branch: a blade in the hand is a sprite rotated around
  a grip exactly like a barrel is.
- **How far out a weapon is HELD, and how big it is drawn, belong to the
  weapon.** `GunFrame.hold` (world px along aim from the body centre) and
  `GunFrame.scale` ride the guns manifest beside the grip, and `gunHand`
  reads them — so the call site has to pass the weapon, not just a pose.
  One constant for everything put the knife out where a barrel goes, which
  read as a small sword floating beside the sprite rather than as something
  somebody is holding. `GUN_HAND_ALONG` is now only the fallback for an
  atlas without the field.
- **The blade path is a PATH, not an arc.** `drawSwings` in `layers/effects`
  draws where the edge IS at this instant plus the tail behind it — the
  stroke races round the cone in the first two thirds of its life and
  closes over the last third — because a static arc that fades is a decal
  saying a swing happened near here, and the thing the player is doing is
  moving a blade. Three strokes on one wedge (a glow the cut alone gets,
  the tail, then a white core on the leading quarter), and `sweep` flips
  the direction so two consecutive slashes cross into an X. It is the only
  WHITE effect in the palette: every other fast-moving mark is tinted, so
  an uncoloured stroke can only mean one thing.
- **AND THE SPRITE IS ON THAT PATH.** `EntityVisuals.startSwing` runs the
  same easing off the same `arcDegrees`, so the held knife IS the leading
  edge rather than a second animation happening nearby: it starts cocked
  past the near lip, crosses, thrusts the grip out along the blade at the
  middle of the sweep, and is drawn back to rest over a follow-through that
  outlives the path. `SWING_TRAVEL_END` is shared between the two — if it
  moves in one it moves in both. `gunSwing` on the drawable is SCREEN space
  and is never mirrored for a left-facing body (`gunKick` is, because "the
  muzzle rises" changes sign with the facing and "the blade is here" does
  not); mirroring it would uncross the two slashes every time somebody aimed
  left. A gun's pose is a SPRING and a blade's is a CLOCK, and the two never
  run at once — which is the bug this replaced: the knife used to borrow the
  recoil spring, tilt up by a fixed angle and fall back, so the steel bobbed
  upward while its own slash swept sideways past it.
- **One flash per TRIGGER PULL, whatever the ray count.** `spawnShot` takes a
  LIST of rays: a pistol hands it one and a shell hands it six, and the only
  things that differ are how many tracers and impacts come out and which
  sheet burns at the barrel (`Flash.kind` — a shotgun throws a CONE). The
  bang, the brass, the light and the damage number are per pull, so a shell
  is one event rather than six pistols going off in a fan. The damage number
  lands on the deepest ray that CONNECTED, so it sits on the body it came
  off rather than out at the mouth of the cone.
- Colours come from `theme/palette.ts` only. Never write a literal colour here.
- Frames are bottom-anchored, so any frame height works with no extra code.
- A prop sheet's frames are VARIANTS unless its manifest entry carries `fps`
  (only the campfire does), in which case they are an animation loop. Playing a
  variant sheet makes the boulders twitch.
- The world coin is `make_coin.py`: the PURPLE dark gold disc, eight Y-axis
  frames, one row. `drawCoins` plays `walkFrameOrder` at the sheet's `fps`. Do
  not hardcode a 3-frame ping-pong — the sheet owns the spin. It is the only
  currency with a world sprite; the group's gold is a number, and the one place
  it is drawn out here is the spark burst off a launching platform.
- **The floor is FOUR soils, mixed by a client-side material field.** One ground
  texture over a whole map is the loudest tell that a forest was generated —
  the eye finds the 4x4 atlas repeat in seconds. The field is two octaves of
  value noise off the map seed (one octave puts its extrema on the lattice and
  draws square regions), banded into loam / turf / mud / litter, and its
  boundaries are DISSOLVED through the graded stencils in `blend.png` rather
  than butted together on a grid line. Three things fray that boundary and all
  three are needed: the stencil frays it inside a tile, a per-tile jitter on the
  field frays which tiles are on it, and the fringe width has to sit between
  "wider than the narrowest band" (everything becomes mush) and "narrower than a
  tile" (regions get straight rectangular sides).
- **BLIGHT is the same idea applied to trunks.** A coarser field marks stands of
  dead wood, so `deadtree` and `stump` come in GROVES — see-through clearings
  next to thickets you cannot see through — rather than salted evenly, which
  reads as damage to the art. `trunkSheet` is what decides, and BOTH the prop
  bake and the overgrowth pass must call it: a canopy redrawn from a different
  sheet than the one baked under it leaves a living crown over a bare trunk
  wherever a body walked past.
- **Flat decals are baked, standing props are sorted.** Litter, stains, blood,
  boot prints and dropped clothing go into the ground canvas — no silhouette, no
  per-frame cost, and they can never occlude a body. Cabins, tents, fences,
  signs and cold firepits go into the entity depth sort next to the
  bonfires, because a player walking behind a cabin has to disappear behind it.
  That one requirement is the whole reason they are not in the prop bake.
  Live objects and their one-shots join that same sort from `world.crates` /
  `effects.crateSmashes` — they are no longer scenery props. Each carries the
  atlas SHEET it draws from, resolved once from `config.objects` when the row
  was unpacked (`game/objects.ts`), because a one-shot outlives the live row
  and there is nothing left to ask what kind it was.
- The bake order inside the ground canvas is a stack of things resting on each
  other: soil, stains that soaked in, litter that fell on top, then what people
  left last. A blood stain under a drift of leaves is older than the leaves,
  which is not the story any of those scenes is telling.
- Almost nothing in `layers/scenery.ts` moves, and that is deliberate: these are
  the things in the forest that have STOPPED. Canvas breathes and a dead fire
  smokes, both off the sheet's own `sway`/`smokes` fields, so the art decides
  what the wind can push, not a table in the layer.
- **A SIGN DOES NOT SWAY, AND `sway` IS A SHEAR OF THE WHOLE SPRITE.** It used
  to, at the largest lean on the sheet. The client's sway offsets the entire
  frame horizontally — post, contact band and all — so a swinging sign slides
  its own footprint across the floor every frame, which reads as a decal being
  dragged rather than as timber in wind and breaks the one convention the whole
  prop set stands on: nothing floats, everything sits on its shadow. Canvas is
  the exception and earns it — a tent wall is fabric with nothing under it, and
  its lean is small enough that the pegged hem never leaves its contact band.
  Anything with a foot in the ground gets `sway=0`. An object
  being used is a one-shot on its own sheet (`kinds` × `animFrames`, kind-major,
  frame 0 the idle), not sway. `crateAnimFrame` CLAMPS on the last frame, and
  that clamp is what lets one number serve both verbs: a break sheet ends
  near-empty, an open sheet ends on a lid standing up and holds it for the rest
  of `CRATE_BREAK_LIFE` — cutting an opened container the instant its lid
  finished rising reads as the object vanishing rather than as it being emptied.
  The first `HIT_FLASH_LIFE` of a smash is the same additive white blink a
  body gets when a shot lands — without it the wood just starts playing.
- Scenery props are drawn through `Projection`, so the lobby can reuse the same
  routine with `WORLD_SPACE` after applying its own transform. The camp is
  dressed too (`server/app/camp.py`); a woodpile the lobby drew flat behind the
  party would jump into the depth sort the instant the run started.
- **`wind.ts` is the only shared clock, and sharing it is the point.** Every
  plant keeps its own phase — a synchronised field reads as the screen
  wobbling — but the GUST is one travelling front sampled at each thing's own
  position, so a wave of foliage leans together and lets go. Grass, bushes,
  ferns AND the scenery that sways (tent canvas) all read `wind.lean`. Canvas
  bending on its own clock while the weeds at its pegs bend on another is the
  clearest tell that a scene was assembled out of parts.
- **`shadows.ts` is a light field, not a decoration, and it is shared for the
  same reason `wind.ts` is.** Every prop, body, coin and drop used to paint its
  own hard ellipse at a fixed alpha in six different files, which says "not
  floating" and nothing else — a crate two tiles from a bonfire wore the same
  mark as a crate alone in the black wood. Two terms replace it and they answer
  different questions: CONTACT is ambient occlusion, always there, the crease
  where a silhouette stops the sky reaching the floor; CAST is the shadow, and
  it points away from the lights the renderer collected this frame, lengthens
  with distance from them, and disappears where nothing is burning. Fire
  flicker rides the cast, so a body at the hearth has a shadow that breathes.
  It is stamped as a soft blob with smoothing ON, never a hard ellipse: a
  shadow is LIGHT, and light is on the smooth side of the house split.
- **The trees and the rocks are deliberately not in it.** Their contact is
  baked into the static ground canvas (and the rocks' into the sprite, by
  `make_textures.py`), and that cache is rebuilt when the map changes, not when
  a lantern walks past. A trunk that swung its shadow around the player would
  cost a full ground rebake every frame.
- **The LAMP is an object now, not just a reach.** `RenderState.lamp` is where
  the local player's lantern IS — held out ahead of the body down the aim —
  as opposed to `fov`'s `lantern`, which is how far that player can SEE. Two
  passes need the point and neither can get it from the fov field: the shaft
  pass needs somewhere to smear the bright buffer toward, and the shadow field
  needs somewhere for a shadow to point away from. That is now its ONLY
  consumer. **Do not try to give the lantern shafts again.** Three routes have
  been walked: lowering the bloom threshold blooms the lit grass; drawing a hot
  core into the scene comes back through bloom as a circle stuck to the player;
  and a synthetic emitter inside the shaft march hides the circle from bloom
  but smears evenly, because it lands near the source whether or not a trunk is
  in the way. Occlusion in that pass is the trunk really being dark in the
  buffer. Volumetric lantern belongs to the motes in `layers/atmosphere.ts`,
  which the darkness pass dims and which therefore respect the shadowcast.
- **`UNSEEN_ALPHA` is a silhouette level and `applyVisibility` is a gate, and
  they are not the same knob.** The first says how much of the WORLD survives
  in the dark — 0.78 leaves a fifth of the art, which is a readable shape and
  not a readable object. The second says whether a CREATURE is drawn at all,
  off the fov's light. Making the woods legible must never be done by moving
  the second one.
- **`disturbance.ts` is the world noticing the player, and its visibility gate
  is a RULE.** A body contributes two pushes — one at its feet, one at a lagged
  wake that chases it — because without the wake the grass snaps back the
  instant you clear it and reads as a bubble stuck to your shoes. A body the
  fov says you cannot see contributes NOTHING: foliage parting around an
  invisible creature is a free tracker that undoes the lantern, exactly as a
  floor cone drawn over an unlit thing would be. Inside your light it is a fair
  tell and a good one.
- The field is owned by `Renderer` and takes the entity list DIRECTLY —
  `Disturber` is structurally a subset of `DrawableEntity` so there is no
  per-frame projection array.
- **Boot prints are drawn live, not baked, and they are the one long-lived
  effect.** Everything else flat is baked into the ground canvas; prints fade,
  and a map that accumulated them forever would end as a mat carrying no
  information. They are `Effects`-owned (see `game/AGENTS.md`) and culled
  against the camera here, because the list outlives the walk that made it on
  purpose — the trail is navigation for the way back.
- **A light is a light.** `drawSceneLights` is `drawFires` with a different
  tone and beat, and must stay that way: the moment a lamp out in the woods is
  drawn by different code from the camp's bonfire they start reading as
  different kinds of object. Tones come from `--scene-*`; `beacon` is the
  extraction platform, pushed onto the SAME `scenery.lights` list when it
  powers up (`TileMap.setRiftState`) rather than given a list of its own — the lighting
  has no idea it is special, which is what "a light is a light" was for.
- A `FIRE` tile is drawn in the ENTITY sort, not with the terrain: baked it
  could not animate, and drawn as scenery it would be covered by whoever is
  standing behind it — a ring of players around a picture of a fire. Its glow
  is a separate additive pass over the darkness, breathing on the same
  `fireFlicker` the light field uses, so the flame, the ground and the party
  move together.
- `vfx.ts` sheets are one-shot TIMELINES anchored on `anchorY` (the row the
  effect happens at), not bottom-anchored like props. Draw them ADDITIVELY,
  after the darkness pass: a beam of light is a light source, not a thing being
  lit. Their `frames / fps` is the effect's duration — callers time themselves
  off the sheet rather than picking their own.
- VFX art is GREYSCALE and tinted at draw time through `effectImage(sheet,
  color)`, so an effect that belongs to a player carries their colour and the
  kindle roar carries `fire.core`. That tint is not `sprites.TintCache`: a
  straight multiply is right for a material and turns a white-hot core into
  flat paint, so `EffectTintCache` adds the neutral art back over it. Never
  bake a hue into a sheet in `make_vfx.py`. `wind` and `death` stay
  greyscale at draw time — a gust of air, dirt off the ground, not a
  player-coloured beam.
- **The `summon` sheet has two callers now**, and the second is the argument
  for not making a new one. `lobby-scene.ts` delivers an arriving body with
  it; `drawLevelUps` in `layers/effects` fires the same column on a player who
  just levelled, tinted `summon.spark` rather than greyscale. Both mean *this
  body is being remade*, which is the one thing a level does that no pickup
  does — and reusing the art the player already learned in the lobby says it
  without teaching a second vocabulary.
- `terrain.ts` and `layers/terrain.ts` are also used by `game/lobby-scene.ts`
  over a locally generated map. Nothing in them may assume a server sent the
  `TileMap`.
- **BUSHES ARE DRAWN OVER BODIES, WITH THE FERNS.** `undergrowth()` still
  CLAIMS a bush tile — the tile gives up its grass, because a bush and a tuft on
  one tile is a pile — but the shrub itself is painted in `overgrowth()`, after
  the entity pass. Drawn with the grass it was the tallest undergrowth on the
  map and the only foliage a player could never be hidden by: you walked in
  front of a thicket the way you walk in front of a painting of one. Standing in
  one now puts you in cover and looks like it — and the cover is REAL: `ai.look`
  re-derives these same tiles from the map seed and shortens a creature's reach
  over them. `BUSH_CHANCE` is therefore a gameplay number and arrives in
  `welcome.config` (`setBushChance`); the hash that places them is bit-for-bit
  the server's `world.tile_hash`, and moving either one alone puts the cover
  somewhere other than the bush.
- `TerrainLayer.setDecorationMask` vetoes grass, bushes and ferns per tile. It exists so
  an area can be kept clear of undergrowth **without** its tiles becoming solid
  — `isSolidTile` treats anything that is not `FLOOR` as a wall, so "bare floor"
  can never be a tile kind. Rocks and trees are not affected; those are the
  map's decision. VOID is forest floor: the ground bake paints it, grass and
  ferns stay off it, and the darkness pass crushes a falloff around it. The
  tiles themselves wander and fray — a rectangle of VOID would read as a
  corridor punched through the woods.
- **The extraction point spans all three shapes at once and is drawn in FOUR
  different places in the frame**, because it is four kinds of thing happening
  at once. It is an abandoned cargo platform with four corner lamps — the
  aircraft are not on it until they are called:
  - `drawRiftGround` — the imprint the skid leaves, on the FLOOR with the boot
    prints. It does not exist until the platform breaks ground; before that the
    ground under a platform is the platform's.
  - `riftStanding` — the console, the torch, and the skid (with everything
    poured into it) while it is still on the ground, MERGED into the entity
    depth sort so a body walking behind the
    platform disappears behind it. NO DRONES, EVER: they arrive flying and
    leave flying. Prop frames are STATES, never variants —
    `platformPropFrame` takes the state, and hashing one would make the pad
    flicker between "safe to load" and "every zombie on the map is coming".
  - `drawRiftAir` — the ropes, the inbound aircraft, a skid that has come free
    (with its load), and anything still falling out of a backpack toward the
    deck. Screen space, AFTER the depth sort and BEFORE the darkness. Both
    halves matter: nothing standing on the floor can plausibly be in front of a
    machine hanging over it, and drawing before the darkness is what lets an
    inbound drone resolve out of the dark instead of popping in at full
    brightness, and what lets a platform twenty tiles up dissolve into the
    night instead of staying crisp over a blacked-out forest.
  - `drawRiftGlow` — corner lamps (green standby or red siren), rotor discs,
    nav lights, rotor wash, the ground-break burst, the red wash the siren
    throws over the clearing, and the paid console's band. Additive, after the
    darkness pass.

  The exit arrow is HUD chrome (`hud/ExitGuide`), not a world sprite.
- **THE LAMPS ARE THE STATE, and there are only two things they say.** Green:
  this pad is found, powered and taking cargo, and nothing out there has heard
  anything. Red: somebody has called for a pickup, the corners are sweeping a
  siren, and the server has put every creature on the map on hunt
  (`Room.sirening`). Everything else on this pad is detail; those two colours
  are the whole decision the extraction offers.
- **THE DRONES ARE NOT ON THIS MAP UNTIL THEY ARE CALLED.** Nothing is parked
  at the corners. Four aircraft come in over one treeline on `rift.approach`,
  staggered, holding formation, and only peel to a corner each over the last
  third of the crossing. The whole flight is one `closeAt` plus the constants
  in `config.rift`. Four flight plans at 6 Hz to describe something fully
  determined would be the largest message in the game for no information.
- **The ropes are DRAWN, not baked, and they are PAID OUT.** A line between a
  fixed eye on the skid and a drone that arrives, drops a hook, catches, strains
  and then flies off cannot be a sprite. The art ships where each rope ends
  (`layout.eyes`) and how much line there is (`layout.rope`); `drawRope` pays
  it out of the winch under gravity, lets the free end swing, homes it onto the
  eye so the catch does not jump, and only then lets the slack come out of it.
  Sag is the difference between the rope's length and how far apart its two
  ends actually are: a fresh tie still has line in it and pools, and by the
  time the rig is straining there is none left and it is dead straight, which
  is what says the machine is pulling. `layout.rope` is also what sets the
  hover height — an arriving drone stations itself one rope above its eye.
- **The pickup is the set piece of the night and it is deliberately long.**
  Sirens alone first (`liftAlarm`) — the aircraft are not even on screen.
  Then inbound, then each line dropping, then the lift waits for the LAST
  tie. Then three beats: `liftStrain` is rotors at maximum with the skid
  rattling in its own hole and NOT MOVING, because the beat that says a thing
  is heavy is the one where nothing happens — the shudder grows through it and
  is gone the instant the ground lets go. Then `liftBreak`: the burst fires,
  the imprint is uncovered, and the server's `tilePatches` hand the deck's
  tiles back to the floor on that same tick. Then `liftClimb`: up and away
  along the map's heading, EASING IN, because something heavy that has just
  come unstuck is still speeding up when it leaves frame. Scale carries the
  distance and the ground shadow stays on the floor; an object that only dims
  looks like it is being switched off.
- **A spent pad is a condition, not a moment, and there are TWO of them.** A
  pad that FLEW leaves the imprint, a dead console (its fourth frame — driven
  home, every lamp out; reusing `idle` would pop the plunger back up and offer
  the button again) and nothing else. A pad the END OF THE NIGHT killed never
  flew: its platform is still sitting there cold with its ground still under
  it. `closeAt` is what separates them. Either way the map remembering is the
  whole point of the state.
- **The pad's torch burns from the moment the map is built**, in every state
  including spent, and it is on `scenery.lights` from the `TileMap`
  constructor rather than from a state change. Everything else about an
  extraction point is dark until somebody presses the button, and a landmark
  you can only see once you have found it is not a landmark. The deck's own
  light is separate and does wait for the console.
- **The paid console throws a band** (`aura`, out of the rift atlas), drawn on
  the CONSOLE and on wall time rather than the pad's clock, so every armed
  console in a night turns at the same rate instead of at its own age. It is
  the only thing that can say "this button does something different now" from
  outside tooltip range.
- **`render/rift.ts` is now the THRESHOLD atlas, not the extraction one.** What
  it still loads is the console, the torch, that torch's fire, the console's
  band and the exit's paving — the pieces that were never about the anomaly.
  The anomaly's own sheets are still generated into `assets/processed/rift/`
  and nothing loads them; they are kept because the art is worth keeping. The
  platform's art lives in `render/platform.ts`, and `drawRiftProp` takes BOTH
  atlases because one pad is made of two generators' output.
- **The exit is dressed in three passes, one per kind of thing.** The paving
  (`drawEgressGround`) goes on the FLOOR with the boot prints — multiply for
  the slabs, `lighter` for the seams, the same split every ground decal here
  uses — and it is SCATTERED CLIENT-SIDE: which tile got which cut is decidable
  from `(tx, ty, seed)`, so by the rule the world is split on it is the
  client's, and only the mouth is on the wire. It is drawn live rather than
  baked because the corridor does not exist when the ground canvas is built.
  The torches are PROPS in the entity depth sort (`egressTorches`), so a body
  can disappear behind one. Their fire (`drawEgressFire`) is additive after the
  darkness, each one offset around the loop by its index — four fires playing
  the same frame at the same instant read as four copies of one sprite, which
  is what they are and what the eye must not notice. `drawRiftFire` does the
  same for the pads' torches, on the same sheet: one flame in this game means
  "a threshold somebody dressed".
- **The STORE draws almost nothing of its own, and that is the design.** It is
  an ordinary forest map: the clearing's soil, grass and trees come from
  `layers/terrain`, his campfire is a `FIRE` tile drawn by the terrain layer
  like the camp's, and his torch ring feeds the same light field a cabin lamp
  does. Only what is HIS is special-cased — the mat goes flat with the boot
  prints; the wagon, the counter, the tables, his gear, the torches and the man
  go IN the entity sort (each table drawing its own goods immediately after
  itself, so a gun is never sorted away from the pedestal it is floating over);
  the torch flames and the buy pool are additive after the darkness like every
  other light; and the tags go last.
  It had a plank floor, walls, a baseboard and hanging lamps when it was an
  interior. All of that is gone; do not reintroduce a floor override or a wall
  pass for it. If the shop needs a new object, prefer a scenery prop or a tile
  kind that already draws itself over a sixth entry point in `layers/store`.
- **It runs the darkness like every other forest map**, on an ambient FLOOR
  (`zones.STORE_AMBIENT`) rather than on a branch in the renderer. The whole
  room is legible from the middle of it and his fire, the torches around the
  rim and the cabinet's marquee are still the brightest things in it. The
  lantern is off here; the torches are what say "somebody lit this" before
  anything standing in them is read.
- **THE AMBIENT FLOOR AND EVERY ADDITIVE LIGHT ON TOP OF IT ARE ONE BUDGET.**
  `drawSceneLights`, `drawFires`, `drawStoreLight` and `drawPayoutLight` all
  composite with `lighter`, which SUMS — nothing in this renderer clamps a
  total. The shop is the only zone that stacks a high ambient floor, a ring of
  torches, a campfire and three landing platforms in one small room, and it
  went FLAT WHITE on arrival. The loudest contributor was `drawPayoutLight`:
  three skids setting down within five tiles of each other, each with a
  seven-tile `downwash` sheet at 0.85 — two overlapping is already 1.7 of a
  full-bright sheet, before eight rotors at 0.9 and eight strobes at 0.8 go on
  top. The fix is spent on both sides (the skids land far apart and the ambient
  floor and torch ring came down on the server; the alphas here came down with
  them) and it stays a shared budget: adding a light source here means taking
  brightness out of another one, and "it looked fine on my screenshot" is not a
  check — walk in during a three-platform payout.
- **A price tag is the shop talking, not an object in the room.** It is drawn
  in the label pass so nothing can occlude it, and it is on the world rather
  than in the HUD because "what is that and what does it cost" has to be
  answerable from the middle of the clearing. It carries the item's NAME in its
  rarity colour above the price, and that is what the GRID cost: six pedestals
  laid out in front of the man are compared at a glance instead of walked past
  in order, the
  stock is rolled WITH REPLACEMENT so two of them really can be the same gun at
  two prices, and six bare numbers over six identical tables is a puzzle. An
  unaffordable price is MUTED, never hidden: a shop that greys out its own
  stock is telling you what to want.
- **The goods FLOAT, and floating is a breath rather than an offset.** A gun on
  the table you are standing at lifts off the boards and keeps moving
  (`standLift`, `config.storeLiftTiles`); a sprite that rose to a fixed height
  and stopped is a bug, and one that is still breathing is an offer. The pool
  underneath (`glow`) is the other half of the same statement, and both are
  keyed off the SAME `nearId` the buy prompt is.
- **The merchant is not an entity and must not become one.** He has no
  position that changes, no aim, no walk cycle — so he has a CLIP PLAYER
  instead, and it is entirely client-side. Two players watching him see
  different flourishes, which is fine: synchronising that would cost a message
  per animation to buy an agreement nobody can perceive.
- **NOTHING IN THIS DIRECTORY DRAWS ON THE VISIBLE CANVAS.** Every pass draws
  into an offscreen 2D surface `Renderer` owns; the visible element is a WebGL2
  context and only `post/chain.ts` ever touches it. That is the house split
  made structural — the WORLD is pixel art at one pixel per pixel and every
  layer still draws it that way, while LIGHT, AIR and the LENS are smooth and
  live on the far side of the handoff. A client without WebGL2 gets a plain
  blit of the surface plus the old 2D danger vignette: the same game, without
  the finish. The fallback is deliberately NOT a 2D imitation of the chain —
  bloom by repeated `drawImage` is slow and banded, and a half-done look is
  worse than no look.
- **The renderer consumes a `Grade`; it never decides one.** A grade is a
  reaction to the GAME — how hurt you are, which place this is, whether a
  pickup is coming down — and this layer is not allowed to know any of that.
  `Game` owns the `GradeStack`, steps it in `stepGrade`, and puts the resolved
  grade on `RenderState`. The one thing the renderer does derive is
  `gatherShafts`: which lights to smear from, because that is screen geometry
  and it already has the projection.
- **`resolve()` returns a REUSED object.** Read it or upload it in the same
  frame; never keep the reference.
- **An event is a LAYER, never a setting.** Danger, death, the scope, an
  extraction and a payout can all be true at once, and each names only the
  fields it has an opinion about. Writing into one shared grade would mean
  whichever event fired last wins and whichever finished last clears it — so a
  hit taken during an extraction would end by resetting the extraction back to
  the forest. `hold`/`release` for anything with state, `pulse` for a one-shot.
- **The envelope IS the choreography.** A ceremony does not need seven clocks
  for its light, its exposure, its bloom and its shafts — it needs one layer
  with a long `attack`. The extraction's grade takes over a second to arrive,
  and that alone is what turns "the numbers changed" into a machine coming
  down through the trees.
- **Shafts are a radial blur of the BRIGHT buffer toward a point, and that is
  why they need no geometry.** The bright pass has already discarded
  everything that is not a light, so the smear only survives where nothing
  occludes the line back to the source — a trunk between the player and a
  burning rig punches a real gap in the beam because the trunk is dark in that
  buffer. Four sources at most, ranked by brightness AND nearness to the middle
  of the frame: a source at the very edge rakes the screen at a glancing angle,
  which reads as a smudge on the lens rather than light through trees.
- **Every chain pass is skipped when its grade term is zero.** A frame with no
  bloom, no shafts and no defocus is one upload and one draw. Do not add a pass
  that runs unconditionally.
- Cached bitmaps and tints are released in `Renderer.dispose()`, and the post
  chain with them.
- `imageSmoothingEnabled` stays `false` — this is pixel art. **Two deliberate
  exceptions, both air:** `layers/atmosphere.ts` turns it on for the ground-fog
  stamp and back off after, and nothing in `post/` is ever nearest-filtered.

## Work Guidance

- A new visual pass is a new module in `layers/` plus one call in
  `Renderer.draw()`, placed deliberately relative to the darkness pass.
- A new REACTION to an event is a look in `post/looks.ts` plus one
  `hold`/`release` in `Game.stepGrade` or one `pulse` at the event. It is not a
  new pass and it is not a field on `RenderState`.
- A new grade FIELD is one entry in `Grade`, one in `SCALARS` or `TRIPLES`, one
  uniform, and its use in the composite shader. The list is what makes a
  forgotten field a type error instead of a knob that silently will not
  animate.
- Anything read every frame belongs in `RenderState`, not fetched inside a
  layer.

## Verification

- `bun run typecheck` from `client/`.
- `bun tests/shadows.ts` from `client/` after touching `shadows.ts` — plain
  script, prints `ok`. It covers `lightAt`'s arithmetic only (which way the
  mark points, what cancels, what is out of reach); the stamping is judged by
  looking, like the rest of the finish.
- `bun tests/grade.ts` from `client/` after touching `post/grade.ts` — plain
  script, prints `ok`. It is the only check on the envelopes and on the
  property the whole design rests on: a partial layer must leave every field it
  does not name alone.
- Check in the browser at two zoom-relevant window sizes that props still
  overlap characters correctly and the lantern cone has a soft spill.
- Walk a lit crate around the camp's bonfire: its shadow should swing to stay
  opposite the fire, shorten as you close on it, and fade out entirely once you
  are back in the dark with the lamp off.
- The chain has no automated check and cannot have one — look at it. A bonfire
  should bloom and the grass beside it should not; walking to low HP should
  close the frame and drain it; going down the scope should soften the forest
  and leave the target sharp.
