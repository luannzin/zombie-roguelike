# Forest terrain, procedural maps, and shared-vision lighting

Date: 2026-08-12

Replaces the hand-drawn flat-colour arena with a textured, procedurally
generated forest, and adds a lantern-lit field of view that the whole team
shares.

Four independent pieces, built in order. Each one works on its own.

---

## 1. Texture generator — `server/tools/make_textures.py`

A sibling of `make_placeholder_sheet.py`, but there is no "raw" stage: these
textures are *generated*, not AI art, so the script writes final-resolution
pixels straight into `assets/processed/terrain/` (already Vite's `publicDir`,
so the client fetches them from `/terrain/...`).

Four outputs plus a manifest:

| file | shape | role |
| --- | --- | --- |
| `ground.png` | 64x64 (4x4 grid of 16px tiles) | the floor. Square by definition. |
| `rock.png` | 5 frames, 16x20 | solid blocker, **not** square, sits on the ground |
| `tree.png` | 4 frames, 24x40 | solid blocker, **not** square, overhangs its tile |
| `grass.png` | 6 frames, 10x10 | pure decoration, non-solid, sits on the ground |

**Seamlessness.** `ground.png` is one 64x64 image generated from *periodic*
value noise (the lattice wraps at 64px), then read back as a 4x4 grid. The
client picks the sub-tile at `(tx % 4, ty % 4)`. This gives 16 distinct-looking
tiles that are guaranteed to line up with each other, because they are literally
neighbouring windows into one seamless texture. Picking a random variant per
tile would produce edge seams; this cannot.

**Anchoring.** Rock, tree and grass frames are bottom-anchored and horizontally
centred on their tile, matching how `process_sprites.py` normalizes characters.
A tree is 40px tall on a 16px tile, so 24px of canopy overhangs upward.

**Palette.** Damp forest: earth browns for ground, moss greens for grass,
cold grey-blue for rock, dark green canopy over a brown trunk. Hard-edged pixel
art, no anti-aliasing, ordered dithering between ramp steps.

Deterministic: a fixed `--seed` reproduces byte-identical output.

## 2. Procedural generation — `server/app/mapgen.py`

`generate_forest(width, height, seed) -> list[list[int]]`

The tile alphabet grows from two values to three:

```
FLOOR = 0   ROCK = 1   TREE = 2
```

`world.py` becomes `is_solid_tile: value != FLOOR` instead of `== WALL`, so a
fourth tile kind later is data, not code. `WALL` stays as an alias for `ROCK` so
the ASCII arena in `maps.py` still builds.

Steps:

1. fill floor, ring the border with `TREE`
2. two-octave periodic value noise -> dense bands become `TREE`, the fringe
   becomes `ROCK` (rock reads as the edge of a thicket)
3. Poisson-ish scatter of small 1-3 tile rock blobs across the open ground
4. carve 5-8 random glades (radius 3-5 circles of floor) so the map has rooms
   without being a room-and-corridor dungeon
5. carve the **centre clearing** (radius 6) — always floor, this is where
   players spawn
6. connectivity repair: flood-fill from centre, fill pockets under 12 tiles
   solid, drill a straight corridor from every larger pocket to the main region
7. assert `count_reachable == floor_count` (reuses `maps.py:count_reachable`)

The room gets a random seed at construction; the seed ships in the map payload
so the client can hash decoration placement deterministically instead of the
server sending a decoration layer.

## 3. Centre spawn

`Room.pick_spawn` currently picks a random free tile biased *away* from other
players — the opposite of what a co-op run wants. It becomes: candidate tiles
sorted once by `|distance_from_map_centre - SPAWN_RING|`, then a linear scan for
the first candidate at least `SPAWN_SEPARATION` from every living player.

`SPAWN_RING_TILES = 2.5`, `SPAWN_SEPARATION_TILES = 1.2`. Players land on a
tight ring around the centre — together, but not stacked. Respawn uses the same
path.

## 4. FOV, lantern, fog — client only

Visual, not authoritative: the server keeps broadcasting everything and the
client dims what nobody can see. Zero netcode change, and shared vision is a
`max()`.

**`render/fov.ts`** owns three tile-indexed arrays:

- `light: Float32Array` — 0..1, how brightly lit this tile is right now
- `explored: Uint8Array` — has anyone ever seen it (fog of war memory)

Per viewer (every living player, local and remote), recursive shadowcasting over
8 octants out to the lantern radius. Blockers occlude, so a rock throws a real
shadow. Each visible tile's light is `max(ambient, cone)`:

- **ambient** — an omnidirectional glow of `visionAmbientTiles` (3.5), so you
  always see your own feet
- **cone** — `visionConeDegrees` (75) wide along the player's aim vector, out to
  `visionLanternTiles` (11), with a soft angular and radial falloff

Team light is the per-tile `max` across all viewers: you see what your teammates
see, from where they are.

Constants live in `config.py` and ship in `welcome.config`, per the repo rule
that the client never hardcodes a tuning number.

**`render/layers/darkness.ts`** turns the field into pixels. Two small canvases
sized one pixel per tile:

- a **night mask** — `rgba(nightTint, alpha)` where alpha is `0` for fully lit,
  `fogAlpha` for explored-but-unseen, `unseenAlpha` for never-seen
- a **warm pass** — `rgba(lanternWarm, light * k)` composited with `lighter`

Both are blitted once, scaled up over the world with `imageSmoothingEnabled =
true`. Bilinear upscaling of a per-tile field is what produces the soft
falloff — no blur filter, no per-pixel shader, two draw calls.

Unseen is **dim, not black**: you can still read the shape of the map, it is
just drained and cold.

**Terrain layer.** `layers/tiles.ts` becomes `layers/terrain.ts`. The map bakes
once into an offscreen canvas: ground pass, then hashed grass tufts on floor
tiles, then blockers in row order with a contact shadow. Tree canopies are
*not* baked — they draw per frame, after entities, so walking north of a tree
puts you under its foliage. Until the atlas finishes loading the layer paints
the old flat colours, so the game never shows an empty map.

**Minimap** takes the same `light`/`explored` arrays. Never-explored tiles are
covered, explored-but-unseen tiles are dimmed, and enemy dots are drawn only
where the team currently has light. Player dots always show — they are your
team, you know where they are.

---

## Non-goals

- server-side visibility culling (co-op PvE; a modified client seeing through
  the dark costs nobody anything)
- animated foliage / wind
- biome variation beyond the one forest
