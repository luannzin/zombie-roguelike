# client/src/render/ — canvas renderer

## Purpose

Turns a plain `RenderState` snapshot into pixels. No network, no gameplay
mutation, no React.

## Ownership

| file | owns |
| --- | --- |
| `renderer.ts` | pass sequencing and the world/screen transform |
| `types.ts` | `RenderState`, `DrawableEntity` — the renderer's input contract |
| `camera.ts` | follow, clamp to map bounds, the arrival push-in |
| `framing.ts` | the wide shot of the camp — zoom and rest-shot fire position |
| `projection.ts` | zoom + offset between world and screen space |
| `sprites.ts` | sheet loading, `SpriteBook`, per-colour multiply tints |
| `terrain.ts` | terrain atlas loading (ground, props, the animated campfire) |
| `vfx.ts` | effect atlas loading: one-shot animation sheets |
| `fov.ts` | shared field of view — `light` and `heat` fields |
| `minimap.ts` | the minimap canvas |
| `layers/` | the actual drawing: terrain, entities, effects, atmosphere, darkness, vignette |

## Local Contracts

- The renderer consumes state and never mutates it. Players and enemies arrive
  in one `entities` list and are drawn by one path.
- `renderer.ts` only sequences passes and switches spaces; drawing lives in
  `layers/`. **The pass order is the atmosphere** — ground → dust → entities
  (depth-sorted by `y`) → overgrowth → motes → darkness → combat effects →
  labels → vignette. Effects go over the darkness because a muzzle flash is a
  light source, not a thing being lit.
- Vision is a client-side visual system: the server broadcasts the whole world.
  `fov.ts` produces two fields — `light` saturates at 1 (visibility), `heat`
  keeps climbing (warmth, drawn as additive amber). Shared vision is a `max()`
  across viewers whose snapshot `lantern` is on (plus the local lamp's output).
- A `LightSource` is a light the WORLD owns — a bonfire — and it is not a
  `Viewer` with the aim zeroed: it has no cone, no battery and no lag, and it
  is warmer than any lamp. It gets its own pass (`FovField.burn`) over the same
  shadowcast, merged with the same `max()`.
- Occlusion is `world.blocksSight`, not `isSolidTile`. A campfire stops a body
  and a bullet but not light.
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
  `welcome.config.enemyTypes[*].sprite`, never a hardcoded list.
- Colours come from `theme/palette.ts` only. Never write a literal colour here.
- Frames are bottom-anchored, so any frame height works with no extra code.
- A prop sheet's frames are VARIANTS unless its manifest entry carries `fps`
  (only the campfire does), in which case they are an animation loop. Playing a
  variant sheet makes the boulders twitch.
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
  color)`, so an effect that belongs to a player carries their colour. That
  tint is not `sprites.TintCache`: a straight multiply is right for a material
  and turns a white-hot core into flat paint, so `EffectTintCache` adds the
  neutral art back over it. Never bake a hue into a sheet in `make_vfx.py`.
- `terrain.ts` and `layers/terrain.ts` are also used by `game/lobby-scene.ts`
  over a locally generated map. Nothing in them may assume a server sent the
  `TileMap`.
- `TerrainLayer.setDecorationMask` vetoes grass and ferns per tile. It exists so
  an area can be kept clear of undergrowth **without** its tiles becoming solid
  — `isSolidTile` treats anything that is not `FLOOR` as a wall, so "bare floor"
  can never be a tile kind. Rocks and trees are not affected; those are the
  map's decision.
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
