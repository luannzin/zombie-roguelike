# client/src/render/ — canvas renderer

## Purpose

Turns a plain `RenderState` snapshot into pixels. No network, no gameplay
mutation, no React.

## Ownership

| file | owns |
| --- | --- |
| `renderer.ts` | pass sequencing and the world/screen transform |
| `types.ts` | `RenderState`, `DrawableEntity` — the renderer's input contract |
| `camera.ts` | follow, clamp to map bounds |
| `projection.ts` | zoom + offset between world and screen space |
| `sprites.ts` | sheet loading, `SpriteBook`, per-colour multiply tints |
| `terrain.ts` | terrain atlas loading |
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
  across viewers.
- Sprites are keyed by asset name; which enemy sheets to load comes from
  `welcome.config.enemyTypes[*].sprite`, never a hardcoded list.
- Colours come from `theme/palette.ts` only. Never write a literal colour here.
- Frames are bottom-anchored, so any frame height works with no extra code.
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
