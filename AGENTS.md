# Root work contract

Browser-based multiplayer 2D pixel-art zombie roguelike. Python + FastAPI
authoritative server at a fixed 30 Hz, Vite + TypeScript + Canvas 2D client,
one WebSocket carrying JSON.

**This file is the router. It loads into every session and stays short on
purpose — it does not contain the architecture, it tells you how to find the
part of it your task needs.**

The repository documents itself in four layers. You do not read them all; you
walk one branch.

| layer | file(s) | answers |
| --- | --- | --- |
| router | this file | "where do I look?" |
| system model | [`ARCHITECTURE.md`](ARCHITECTURE.md) | "what owns this, and which side is authoritative?" |
| work contract | the nearest `AGENTS.md` | "what must I not break here?" |
| design law | [`docs/design/`](docs/design/) | "why is it this way, and what is the smallest change surface?" |
| ambient | [`STATE.md`](STATE.md) | "what is currently moving, broken, or off-limits?" |

---

## When a task arrives

Do this before touching source. It is six cheap steps that replace an
expensive repository search.

1. **Classify** the task — what does it actually change? (table below)
2. **Route** to the owning subsystem. If the classification is obvious to you, go straight to step 3; if it is not, read [`ARCHITECTURE.md`](ARCHITECTURE.md) § *Major subsystems* once and stop there.
3. **Load that branch only**: the owning directory's `AGENTS.md`, plus that subsystem's design doc. Two files, typically.
4. **Take the change surface** from the design doc's *Change surface* table — it names the files. Note its *Do not touch* line.
5. **Inspect source** only now, and only those files. Large files: jump to the section (see *Large files*), never read whole.
6. **Implement**, then verify (see *Verification*).

```
task
 |  classify: what does it change?
 v
subsystem  ------ unsure? ARCHITECTURE.md § Major subsystems, once
 |
 v
nearest AGENTS.md  +  docs/design/<subsystem>.md
 |  its "Change surface" table
 v
3-6 source files
 |
 v
implement -> verify
```

### Classify

Conceptual routing, not keyword matching. Ask what the change actually
touches, then take that row. A task that spans two rows takes both branches —
never all of them.

| the task is about… | subsystem | route |
| --- | --- | --- |
| a rule of play — damage, cost, quota, spawn, progression | the owning **server** module | `server/app/AGENTS.md` + its design doc |
| how something **looks or sounds** happening | **presentation** | `client/src/render/` or `client/src/audio/` + `docs/design/presentation.md` |
| a **panel, prompt, meter or tooltip** | **HUD** | `client/src/components/AGENTS.md` |
| a **message shape, desync, prediction or reconnect** | **networking** | `server/app/AGENTS.md` (wire contracts) + `docs/netcode.md` |
| **finding, loading or leaving** an extraction point | **extraction** | `docs/design/extraction.md` |
| the **merchant, prices, buying, the payout** | **store** | `docs/design/store.md` |
| **levels, upgrades, the cabinet** | **skills** | `docs/design/skills.md` |
| the **look of the picture** — grade, bloom, fog, the lens, camera feel | **presentation** | `client/src/render/post/` + `docs/design/presentation.md` |
| how **creatures notice, chase or react** | **enemies** | `docs/design/enemies.md` |
| **maps, scenes, props, objects, weather, zones** | **world** | `docs/design/world.md` |
| **moving, carrying, shooting, the bag or the belt** | **player** | `docs/design/player.md` |
| a **pixel or a sound that must be regenerated** | **asset pipeline** | `assets/AGENTS.md` -> `server/tools/AGENTS.md` |

If the task names a *feeling* rather than a system ("make the exit more
dramatic", "make the shop feel alive"), classify by **what would have to
change to produce it** — usually presentation plus one gameplay subsystem —
and say which you picked before you start.

### What to load, and what not to

- **The subsystem's design doc: always**, for the subsystem you routed to. That is where the change surface lives.
- **`ARCHITECTURE.md`: only when routing is unclear**, or when the change crosses the client/server line and you need the authority table. Read it once; do not re-read per file.
- **`STATE.md`: when the task depends on the present** — it touches a system that changed recently, you hit something that looks like a regression, you are about to modify a "do not touch" area, or the task asks what to work on next. It is ambient context, not a required step. Skip it for a self-contained change to a stable system.
- **Never**: all seven design docs; every `AGENTS.md` in the tree; the repository end to end; a giant file opened without a target section.

If you catch yourself opening a subsystem the task does not touch, stop and
say why you think you need it.

### Subagent strategy

For any investigation that spans more than ~3 files, dispatch a **read-only
exploration agent** and have it return exactly:

- relevant files (path + line ranges)
- ownership: which subsystem, server or client
- the data flow through them
- the contracts involved
- risks / danger zones
- a recommended change surface

It must not modify code. The main agent then implements from that report. This
keeps the exploration cost out of the implementation context.

---

## DOX: the AGENTS.md chain

`AGENTS.md` files are binding work contracts for their subtrees. Everything in
this repository must stay understandable from the nearest applicable
`AGENTS.md` plus every parent above it.

**Before editing:** walk from the repo root to each target path and read every
`AGENTS.md` **on that route** — the route, not the tree. For a change in
`server/app/` that is this file plus two; there is never a reason to read a
sibling branch. The closer doc controls local detail; no child may weaken a
parent's rule. Re-read in the current session — do not rely on memory.

**After editing:** update the closest owning doc when a change affects purpose,
scope, ownership, durable structure, contracts, workflow, inputs/outputs,
constraints, artifacts, user preferences, or the child index. Update parents
when parent-level structure changes. Delete stale text rather than explaining
history. Small edits that change no behaviour and no contract may leave docs
unchanged — but the check still happens.

**Child doc shape** (create one when a folder becomes a durable boundary):
Purpose, Ownership, Local Contracts, Work Guidance, Verification, Child DOX
Index. Leave a section empty rather than inventing content for it.

**Style:** concise, current, operational. Stable contracts, not diary entries.
Broad rules in parents, concrete details in children. Do not duplicate a rule
across files unless each scope genuinely needs its own version.

### Child DOX Index

| path | covers |
| --- | --- |
| [`server/AGENTS.md`](server/AGENTS.md) | the Python process: runtime + asset pipeline |
| [`server/app/AGENTS.md`](server/app/AGENTS.md) | authoritative simulation, wire protocol, tuning |
| [`server/tools/AGENTS.md`](server/tools/AGENTS.md) | offline asset generation |
| [`client/AGENTS.md`](client/AGENTS.md) | browser client: build, net, audio, hooks, screens |
| [`client/src/game/AGENTS.md`](client/src/game/AGENTS.md) | loop, prediction, world, effects, the HUD seam |
| [`client/src/render/AGENTS.md`](client/src/render/AGENTS.md) | camera, atlases, passes, layers |
| [`client/src/components/AGENTS.md`](client/src/components/AGENTS.md) | HUD components (ours) vs `ui/` (generated) |
| [`assets/AGENTS.md`](assets/AGENTS.md) | raw source art vs served production art |
| [`docs/AGENTS.md`](docs/AGENTS.md) | durable reference docs and design specs |

Root-owned files: `ARCHITECTURE.md`, `STATE.md`, `README.md`, `CLAUDE.md`
(a one-line import of this file, so harnesses that look for `CLAUDE.md` find
the router), `.gitignore`.

### Design law index

Not work contracts — the reasoning behind each subsystem. Read the one that
owns your task; skip the rest.

| doc | subsystem |
| --- | --- |
| [`docs/design/extraction.md`](docs/design/extraction.md) | pads, the pour, the pickup, the exit, quests, corridors |
| [`docs/design/store.md`](docs/design/store.md) | the merchant's clearing, stalls, prices, the payout, the balance |
| [`docs/design/skills.md`](docs/design/skills.md) | levels, the upgrade machine, `Mods` |
| [`docs/design/player.md`](docs/design/player.md) | movement, stamina, the belt, weapons, ammo, the pocket |
| [`docs/design/enemies.md`](docs/design/enemies.md) | senses, hunt, the director, corpses |
| [`docs/design/world.md`](docs/design/world.md) | map generation, scenery, objects, zones, weather, the camp |
| [`docs/design/presentation.md`](docs/design/presentation.md) | audio, VFX, gore, the light budget |

---

## Global rules

These bind every subtree. Subsystem-specific rules live in the docs above.

- **The server is authoritative. Clients send inputs, never positions.**
- **Nothing is persisted server-side.** The only durable client datum is the player's name, in `localStorage`.
- **Every gameplay constant lives in `server/app/config.py`** and reaches the client in `welcome.config`. Never hardcode one client-side — and never hedge one either. Fields `client_config()` always sends are **required** on `GameConfig`, so `config.x ?? 100` does not compile past a type error; `test_config_parity.py` keeps the two key sets equal in both directions. The client used to hedge, and two constants had silently drifted (`INVENTORY_SLOTS` 3 vs 5, `CARRY_MAX_WEIGHT` 10 vs 14) with nothing failing.
- **These pairs are mirrors and change together.** Three are line-for-line; five are rules re-derived on the other side and are just as breakable:
  - `server/app/simulation.py` <-> `client/src/game/simulation.ts` — movement, stamina
  - `server/app/protocol.py` <-> `client/src/net/protocol.ts` — every wire shape
  - `server/app/machine.py` <-> `client/src/game/machine.ts` — the pull's clock
  - `server/app/world.py` <-> `client/src/game/world.ts` — the tile alphabet, the `GROUNDS` / `CLEAR` sets, and `move_axis` / `blocks_sight` / `box_blocked` / `raycast_tiles`. Prediction runs on it; a tile kind added on one side alone desyncs collision. Solidity is no longer `!= FLOOR`: the shop's `TILEFLOOR` is a second walkable ground, so both sides test membership of `GROUNDS` and a member added to one alone rubber-bands the shop's doorway
  - `Room.collect_loot` + `Inventory.add` + `ammo.Reserve` <-> `client/src/game/interaction.ts` (`canStow`, `swapTargetFor`) — whether a pickup is legal. The client answers locally because the prompt cannot wait for a round trip
  - `ai.look` <-> `client/src/render/fov.ts` — sight symmetry. No longer a copied constant: both read `enemyViewDarkScale` / `enemyViewLitScale` off `welcome.config`
  - `world.tile_hash` <-> `client/src/render/terrain.ts`'s `tileHash` — where the undergrowth IS. The client draws bushes from it and `ai.look` now shortens a creature's reach over the same tiles, so the two must agree bit for bit (`Math.imul` is a 32-bit multiply; plain Python `*` drifts after a few thousand tiles). `tests/test_bush_cover.py` pins it against browser values
  - `make_player.py`'s `HOLD_ARM_X` <-> `client/src/render/guns.ts`'s `GUN_GRIP_SIDE` and `arms.ts`'s `WRIST_OUT` / `SHOULDER_OUT` — WHICH HAND the weapon is in. The sheet draws a holding pose with the weapon arm raised on one side; the client places the grip, and starts the drawn forearm, off the same side. Move one alone and the weapon floats beside a body whose arm is out the other way
  - `make_platform.py`'s deck <-> `client/src/game/pad-cargo.ts` — where a poured item comes to rest. Fractions of the sprite, re-derived rather than shipped; a skid re-proportioned without them stacks loot on the grass
- **Sizes, speeds and distances are authored in tiles/seconds** and multiplied by `TILE_SIZE`. No raw pixel numbers.
- **All colours and type live in `client/src/styles/index.css`**, read by the canvas through `client/src/theme/`.
- **The WORLD is pixel art; the LIGHT, the AIR and the LENS are not.** Every `render/layers/` pass draws into an offscreen 2D surface at one pixel per pixel, and `render/post/` finishes that surface on the GPU with nothing nearest-filtered. Do not pixelate an effect to "match", and do not draw on the visible canvas from anywhere but the post chain.
- **Rendering knows nothing about the network; networking knows nothing about rendering; `server/app/` knows nothing about either.**
- **`assets/processed/` is generated output.** Edit the generator in `server/tools/`, never the PNG.
- **Generated-asset lists are append-only.** Inserting a row moves every existing frame index.
- **Money is created in exactly one place, once:** `Room.enter_store`. The client never settles.

## Verification

| scope | command |
| --- | --- |
| server | `python tests/test_snapshot_shape.py`, `test_pour.py`, `test_store_walk.py`, `test_config_parity.py`, `test_loot_frames.py`, `test_bush_cover.py`, `test_scenery_containers.py`, `test_creature_sheets.py` from `server/` — plain scripts, each prints `ok` |
| client | `bun run typecheck` from `client/` — required after any change there |
| client | `bun tests/grade.ts` from `client/` after touching `render/post/grade.ts` — plain script, prints `ok` |
| client | `bun tests/exit-path.ts` from `client/` after touching `game/exit-path.ts` — plain script, prints `ok` |
| client | `bun tests/weapon-pose.ts` from `client/` after touching `render/guns.ts`, `game/weapon-feel.ts` or `make_guns.py` — plain script, prints `ok`. It reads the REAL atlas manifest, so it fails if the generator stops appending action frames |
| both | run the server, open two browser tabs, confirm both players move, shoot and light the world without rubber-banding |

Run `test_store_walk.py` after any edit to `store.py`'s layout offsets: it
flood-fills the shop and fails if the exit, the merchant, a stall or the
cabinet cannot be reached.

Run `test_loot_frames.py` after adding an item to `loot.ITEMS` or a drawing
to `make_loot.py`: it fails if the catalog names a key the atlas has no art
for. A frame is taken from the atlas manifest, not from catalog position —
the two lists deliberately do not share an order.

Run `test_bush_cover.py` after touching `world.tile_hash`, `TileMap.bush_at`,
`BUSH_CHANCE` or the client's `tileHash`: it pins the hash against values taken
out of a browser, which is the only way to catch the two sides placing
undergrowth in different tiles — nothing at runtime notices.

Run `test_scenery_containers.py` after adding a container kind or a scene that
places one: it fails if two openables claim the same tile, or if a scene keeps
more than `MAX_CONTAINERS`.

Run `bun tests/weapon-pose.ts` after touching the held weapon: the pose maths
in `render/guns.ts`, the per-class feel in `game/weapon-feel.ts`, or the atlas
`make_guns.py` writes. It pins the one thing nothing at runtime notices — that
the muzzle, the ejection port and the off hand are the same pose, mirrored
together — and that every firearm still has an action frame, APPENDED after
the closed ones rather than interleaved.

Run `test_creature_sheets.py` after touching `make_zombie.py` or reprocessing
a creature: it checks that every creature and every accessory still has a
`-death` timeline, that the grids are what the renderer assumes, and — the one
worth having — that the three variants are still three SHAPES. S15's silhouette
test as arithmetic: mask them, count the pixels and the top-contour columns
that differ, and fail if a variant has become a recolour of another.

Run `test_config_parity.py` after touching `client_config()` or `GameConfig`:
it fails if either side declares a key the other does not, in either
direction. It is the only check on the constants contract — the client cannot
tell a missing field from a wrong number at runtime.

## Large files

Do not open these whole. Locate the section, then read it.

| file | lines | why it is large | how to navigate |
| --- | --- | --- | --- |
| `client/src/game/game.ts` | ~4400 | the orchestrator every client subsystem hangs off | 21 `// --- <section> ---` banners; the full list is in the file's own header comment. Grep the banner, never the line number |
| `server/app/room.py` | ~2800 | the authoritative room: lifecycle, tick, and every player-intent handler | 16 `# --- <section> ---` banners; the full list is in the module docstring. Grep the banner, then `def ` inside it |
| `server/tools/make_rift.py`, `make_audio.py`, `make_objects.py` | 1.9-2.6k | offline generators: one long recipe per asset, no shared state | grep the asset name |
| `client/src/net/protocol.ts` | ~1400 | the whole wire surface as types | grep the message or payload name |

They are not scheduled for splitting. Documenting their internal boundaries was
the cheaper fix; see `STATE.md` if that changes.

**A banner that lies is worse than no banner**, because this file tells you to
trust it instead of opening the file. Both of the big two used to have five,
one of which spanned >1300 lines across eight unrelated subsystems. If you add
a handler, put it under the banner that describes it or add one.

## User preferences

Durable behaviour the user has asked for. Subsystem-level preferences live with
their design doc — this list is only for things that cross every subtree.

- Design law is written as *why*, not *what*. When recording a decision, record the argument that produced it and the alternative it replaced, not a restatement of the code.
- Prefer deriving a number from an existing source table over hand-picking it (see the CS2 derivation in [`docs/design/player.md`](docs/design/player.md) and price derivation in [`docs/design/store.md`](docs/design/store.md)).
