# client/src/render/ — canvas renderer

## Purpose

Turns a plain `RenderState` snapshot into pixels. No network, no gameplay
mutation, no React.

## Ownership

| file | owns |
| --- | --- |
| `renderer.ts` | pass sequencing and the world/screen transform |
| `types.ts` | `RenderState`, `DrawableEntity` — the renderer's input contract (`gear` is the equipped overlay) |
| `camera.ts` | follow, clamp to map bounds, the arrival push-in |
| `framing.ts` | the wide shot of the camp — zoom and rest-shot fire position |
| `projection.ts` | zoom + offset between world and screen space |
| `sprites.ts` | sheet loading, `SpriteBook`, per-colour multiply tints |
| `terrain.ts` | terrain atlas loading (4 grounds, blend stencils, props, flat decals, the animated campfire) |
| `scenery.ts` | scenery atlas loading: standing props and flat decals of what people left |
| `vfx.ts` | effect atlas loading: one-shot sheets (summon, kindle, wind) and the looping loot `aura` |
| `loot.ts` | loot atlas: one 16x16 frame per collectable item |
| `fov.ts` | shared field of view — `light` and `heat` fields |
| `wind.ts` | the shared gust field every bending thing reads |
| `disturbance.ts` | what bodies do to the plants they walk through |
| `layers/vision.ts` | the ENEMY's hunt diamond — fill meter and bang over the head |
| `layers/scenery.ts` | placed scenes: flat decals into the ground bake, standing props into the depth sort |
| `minimap.ts` | the minimap canvas |
| `layers/` | the actual drawing: terrain, entities, loot, vision, effects, atmosphere, darkness, vignette |

## Local Contracts

- The renderer consumes state and never mutates it. Players and enemies arrive
  in one `entities` list and are drawn by one path.
- `renderer.ts` only sequences passes and switches spaces; drawing lives in
  `layers/`. **The pass order is the atmosphere** — ground (soil, litter, flat
  scenery) → dust → coins and loot sprites → entities, bonfires and standing
  scenery (one depth sort by `y`, including live crates and smash sheets) →
  overgrowth → motes → darkness → combat effects → loot auras / motes /
  epic-legendary beams / empty-crate wind → hunt diamond →
  labels → vignette. Effects and loot light go over the darkness because
  they are light, not things being lit. An unlit drop HIDES ITS SPRITE.
  Glow, motes and the epic/legendary column leak a whisper through the
  night (`lit(visibility, floor)`) so the player can feel a find before
  the lantern reaches it — never a full beam, never the item itself.
  Loot sprites use `Projection` in the screen-space pass with the coins;
  glow, motes and beams sit in the world-space pass after darkness and
  take raw world pixels — `view.x` there would project them a second time,
  off the map. Every rarity throws specks; epic and legendary keep the
  looping column as well.
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
  is safe to call every frame and throttles itself.
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
  it. Treating it as a wall tile puts a rock under every crate.
- `Camera` follows the player and nothing else. The move INTO a zone belongs to
  `game/lobby-scene.ts`, which is already showing the same place when it starts;
  by the time this camera exists the push-in is over and it opens on the frame
  it was handed. Do not add an arrival here — it would replay a shot the player
  has just watched.
- `framing.ts` holds both ends of that move: `ARENA_ZOOM` is the scale the game
  is played at, and `campZoom` is the wide shot, clamped to at least one step
  below it so there is always a push to see. The wide shot's fire position
  (`CAMP_FIRE_ANCHOR` / `campFireAnchor`) lives here too, because the title
  screen and the lobby share it — two call sites with two numbers is a fire
  that jumps when you enter a room. They are read by the lobby and by
  `Camera`'s resting zoom; if they diverge, starting a run cuts to a different
  picture of the same clearing instead of continuing the shot.
- Sprites are keyed by asset name; which enemy sheets to load comes from
  `welcome.config.enemyTypes[*].sprite`, never a hardcoded list. The backpack
  overlay is `welcome.config.backpackSprite`.
- **Gear sits on the body.** `DrawableEntity.gear` is an overlay sheet drawn
  in the same facing and walk frame, multiply-tinted with the wearer's
  colour. It is registered to the processed player grid, so it is blitted at
  the same dest rect. Always the backpack for players right now; null for
  enemies. Facing down shows straps (the pack is behind); facing up and
  side show the pack on the back.
- Colours come from `theme/palette.ts` only. Never write a literal colour here.
- Frames are bottom-anchored, so any frame height works with no extra code.
- A prop sheet's frames are VARIANTS unless its manifest entry carries `fps`
  (only the campfire does), in which case they are an animation loop. Playing a
  variant sheet makes the boulders twitch.
- The world coin is `make_coin.py`: the HUD disc, eight Y-axis frames, one
  row. `drawCoins` plays `walkFrameOrder` at the sheet's `fps`. Do not
  hardcode a 3-frame ping-pong — the sheet owns the spin.
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
  Live crates and their smash sheets join that same sort from `world.crates`
  / `effects.crateSmashes` — they are no longer scenery props.
- The bake order inside the ground canvas is a stack of things resting on each
  other: soil, stains that soaked in, litter that fell on top, then what people
  left last. A blood stain under a drift of leaves is older than the leaves,
  which is not the story any of those scenes is telling.
- Almost nothing in `layers/scenery.ts` moves, and that is deliberate: these are
  the things in the forest that have STOPPED. A sign swings, canvas breathes, a
  dead fire smokes — all three off the sheet's own `sway`/`smokes` fields, so
  the art decides what the wind can push, not a table in the layer. A crate
  smash is a one-shot on the crate sheet (`kinds` × `breakFrames`), not sway.
  The first `HIT_FLASH_LIFE` of a smash is the same additive white blink a
  body gets when a shot lands — without it the wood just starts playing.
- Scenery props are drawn through `Projection`, so the lobby can reuse the same
  routine with `WORLD_SPACE` after applying its own transform. The camp is
  dressed too (`server/app/camp.py`); a crate the lobby drew flat behind the
  party would jump into the depth sort the instant the run started.
- **`wind.ts` is the only shared clock, and sharing it is the point.** Every
  plant keeps its own phase — a synchronised field reads as the screen
  wobbling — but the GUST is one travelling front sampled at each thing's own
  position, so a wave of foliage leans together and lets go. Grass, bushes,
  ferns AND the scenery that sways (a sign on its post, tent canvas) all read
  `wind.lean`. A sign bending on its own clock while the weeds at its base bend
  on another is the clearest tell that a scene was assembled out of parts.
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
  different kinds of object. Tones come from `--scene-*`; `beacon` is unused
  and reserved so the extraction point is a data change, not a render change.
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
  bake a hue into a sheet in `make_vfx.py`. `wind` is the exception that
  stays greyscale at draw time — a gust of air, not a player-coloured beam.
- `terrain.ts` and `layers/terrain.ts` are also used by `game/lobby-scene.ts`
  over a locally generated map. Nothing in them may assume a server sent the
  `TileMap`.
- `TerrainLayer.setDecorationMask` vetoes grass, bushes and ferns per tile. It exists so
  an area can be kept clear of undergrowth **without** its tiles becoming solid
  — `isSolidTile` treats anything that is not `FLOOR` as a wall, so "bare floor"
  can never be a tile kind. Rocks and trees are not affected; those are the
  map's decision. VOID is forest floor: the ground bake paints it, grass and
  ferns stay off it, and the darkness pass crushes a falloff around it. The
  tiles themselves wander and fray — a rectangle of VOID would read as a
  corridor punched through the woods.
- Cached bitmaps and tints are released in `Renderer.dispose()`.
- `imageSmoothingEnabled` stays `false` — this is pixel art.

## Work Guidance

- A new visual pass is a new module in `layers/` plus one call in
  `Renderer.draw()`, placed deliberately relative to the darkness pass.
- Anything read every frame belongs in `RenderState`, not fetched inside a
  layer.

## Verification

- `bun run typecheck` from `client/`.
- Check in the browser at two zoom-relevant window sizes that props still
  overlap characters correctly and the lantern cone has a soft spill.
