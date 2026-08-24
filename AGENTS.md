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
| a **pack, a howl, or the thing asleep in the den** | **enemies** | `docs/design/enemies.md` § The pack / The miniboss |
| **maps, scenes, props, objects, weather, zones** | **world** | `docs/design/world.md` |
| the **boss fight** — his moves, the arena, the bar, which night | **enemies** | `docs/design/enemies.md` § THE SAWYER |
| **moving, carrying, shooting, the bag or the belt** | **player** | `docs/design/player.md` |
| **what a body WEARS, what stops a blow, a lâmina or the shield** | **gear** | `docs/design/gear.md` |
| **healing, a medkit, the cells on 4 and 5** | **player** | `server/app/medical.py` + `docs/design/player.md` |
| **R, an ultimate, a synergy, a set that unlocks something** | **ultimates** | `docs/design/ultimates.md` |
| **a thing that HAPPENS on a night — a wave, the lights, a crate** | **events** | `docs/design/events.md` |
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
| [`docs/design/gear.md`](docs/design/gear.md) | lâminas, the five worn slots and their materials, the shield |
| [`docs/design/ultimates.md`](docs/design/ultimates.md) | one ultimate per weapon, the tags that gate it, the bar that fills it |
| [`docs/design/enemies.md`](docs/design/enemies.md) | senses, hunt, the director, corpses |
| [`docs/design/world.md`](docs/design/world.md) | map generation, scenery, objects, zones, weather, the camp |
| [`docs/design/presentation.md`](docs/design/presentation.md) | audio, VFX, gore, the light budget |
| [`docs/design/events.md`](docs/design/events.md) | the night's script: what happens on a night, when, and the gate over it |

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
  - `Room.collect_loot` + `Inventory.add` + `ammo.Reserve` + `armor.Loadout` + `Hotbar` + `medical.Medical` <-> `client/src/game/interaction.ts` (`canStow`, `swapTargetFor`, `replacedBy`) — whether a pickup is legal, and what it displaces. The client answers locally because the prompt cannot wait for a round trip. FIVE containers now: the pocket refuses when full, a gun cell trades, the BLADE cell always swaps (it has no empty state), a WORN slot refuses only the piece you already have in the same or better condition, and a MEDICAL cell refuses when both are full — it never swaps, because two kits are a quantity rather than alternatives and trading one away would bin the resource the player bent down for
  - `Room.sync_block` <-> `client/src/game/game.ts`'s `Game.blocking` / `syncBlock` — whether the shield is UP. Both resolve it BEFORE the walk reads it, because the walk is the first thing that asks (`block_speed` / `MovableState.blockSpeed`, one resolved multiplier rather than a catalog lookup inside movement code). A block decided after the step is a tick late on exactly the frame it was raised for
  - `ai.look` <-> `client/src/render/fov.ts` — sight symmetry. No longer a copied constant: both read `enemyViewDarkScale` / `enemyViewLitScale` off `welcome.config`
  - `world.tile_hash` <-> `client/src/render/terrain.ts`'s `tileHash` — where the undergrowth IS. The client draws bushes from it and `ai.look` now shortens a creature's reach over the same tiles, so the two must agree bit for bit (`Math.imul` is a 32-bit multiply; plain Python `*` drifts after a few thousand tiles). `tests/test_bush_cover.py` pins it against browser values
  - `make_player.py`'s `HOLD_ARM_X` <-> `client/src/render/guns.ts`'s `GUN_GRIP_SIDE` and `arms.ts`'s `WRIST_OUT` / `SHOULDER_OUT` — WHICH HAND the weapon is in. The sheet draws a holding pose with the weapon arm raised on one side; the client places the grip, and starts the drawn forearm, off the same side. Move one alone and the weapon floats beside a body whose arm is out the other way
  - `make_platform.py`'s deck <-> `client/src/game/pad-cargo.ts` — where a poured item comes to rest. Fractions of the sprite, re-derived rather than shipped; a skid re-proportioned without them stacks loot on the grass
  - `make_sawyer.py`'s `CHOP_ARC` / `RIP_ARC` <-> `client/src/render/layers/boss-vfx.ts`'s `SWING` — WHERE THE BAR IS. The trail is drawn on the nose of a weapon whose pose only the SPRITE knows, so the client re-derives it: the swing's clock is shipped (`welcome.config.bossMoves`) and its arc is mirrored. They agree because both run off the same playhead. Re-author a clip's arc in the generator and `SWING` is the other half that has to move, or the ribbon comes off nothing
  - `boss.Move.clip` / `.after` <-> `client/src/render/boss.ts`'s `clipFor` — WHICH SHEET A MOVE PLAYS. `row.m` used to be both the move's name and its clip's, because every move was one animation. The CHARGE is three (`rev` to telegraph, `walk` to run, `idle` to pull up), so `m` now names a MOVE and the sheet is resolved through `welcome.config.bossMoves`. Assume the two are the same string and he crosses the yard standing still, shaking a chainsaw, on the frame the player has to pick a direction. `bun tests/boss-clock.ts` pins all three
  - `server/app/config.py`'s `bossHit` <-> `client/src/game/game.ts`'s `predictShot` — WHETHER A ROUND STOPS ON HIM. The client draws the local player's own shot before the server answers, off a target list it builds itself; the boss was missing from it for the whole of his first release, so every bullet flew visibly THROUGH the biggest body in the game while landing perfectly. The damage was never the bug — a shot with no stop, no number and no marker simply reads as a miss
  - `assets/processed/sawyer/manifest.json` <-> `server/app/boss.py` <-> `client/src/render/boss.ts` — WHEN THE BAR LANDS. The manifest's event frames are the boss's windups and recoveries: the server reads them at import and derives its hitbox timings, and the client draws frame `t * fps` off the playhead the server sends. Nobody holds a copy of anybody's number. Type a duration into `boss.py` and the fight becomes unfair in a way no screenshot shows — the blow lands before the animation says it does. `bun tests/boss-clock.ts` pins it
- **Sizes, speeds and distances are authored in tiles/seconds** and multiplied by `TILE_SIZE`. No raw pixel numbers.
- **All colours and type live in `client/src/styles/index.css`**, read by the canvas through `client/src/theme/`.
- **The WORLD is pixel art; the LIGHT, the AIR and the LENS are not.** Every `render/layers/` pass draws into an offscreen 2D surface at one pixel per pixel, and `render/post/` finishes that surface on the GPU with nothing nearest-filtered. Do not pixelate an effect to "match", and do not draw on the visible canvas from anywhere but the post chain.
- **Rendering knows nothing about the network; networking knows nothing about rendering; `server/app/` knows nothing about either.**
- **`assets/processed/` is generated output.** Edit the generator in `server/tools/`, never the PNG.
- **Generated-asset lists are append-only.** Inserting a row moves every existing frame index.
- **Money is created in exactly one place, once:** `Room.enter_store`. The client never settles.
- **Damage arrives at exactly one place, once:** `Room.damage_player`. The shield, worn armour and `Mods.armor` are applied there and nowhere else, in that order — a mitigation written at three call sites is one that will be missing from the fourth. Anything that can hurt a player comes through this door, including the boss.
- **A player has FIVE containers and `loot.ItemDef.pocket` is what decides between them:** the pocket (`bag`, slots and weight), the belt (`hotbar` — a gun into a gun cell, a lâmina into the blade cell), the reserve (`ammo`), the body (`worn` — FIVE slots: head, arms, body, legs, feet) and the medical cells (`med` — two of them, on keys 4 and 5). None of `ammo`, `worn` or `med` costs a pocket cell, because the bag's budget answers "how much loot can I still carry out" and none of rounds, a helmet or a bandage is cargo. Worn armour and medicine still cost SPEED.
- **Health comes back through exactly one door:** `Room.heal_player`. It used to be one PLACE because there was one caller; there are two sources now — a medical channel completing (`_step_use`) and the field gun's dart — so the rule is a method instead of a coincidence. What did not change is the important half: there is still no regeneration, no heal on extraction, and nothing that happens to a body on its own. Every point of health in this game is something a person spent something to give it, and a DOWNED body is never healed by anything.
- **Medicine is not cargo.** Both kits have `value=0`, so they cannot be sold, poured, or counted toward a quota. The merchant sells them, and that trip is one-way.
- **Every weapon owns at most one ULTIMATE, and nothing anywhere names a combination.** A weapon carries tags, a material carries tags, and an ultimate lists the tags it needs (`server/app/ultimates.py`). Adding one is a data row; a second weapon that satisfies an existing one is a tag on that weapon's row. `Room` never learns a weapon's name and neither does the HUD.

## Verification

| scope | command |
| --- | --- |
| server | `python tests/test_snapshot_shape.py`, `test_pour.py`, `test_store_walk.py`, `test_config_parity.py`, `test_loot_frames.py`, `test_bush_cover.py`, `test_scenery_containers.py`, `test_creature_sheets.py`, `test_map_scale.py`, `test_boss_fight.py`, `test_gear.py`, `test_pack.py`, `test_medical.py`, `test_events.py`, `test_night_pressure.py`, `test_quota.py`, `test_containers.py`, `test_skills.py`, `test_ranged.py`, `test_reroll.py`, `test_weather.py`, `test_ultimates.py` from `server/` — plain scripts, each prints `ok` |
| client | `bun run typecheck` from `client/` — required after any change there |
| client | `bun tests/grade.ts` from `client/` after touching `render/post/grade.ts` — plain script, prints `ok` |
| client | `bun tests/exit-path.ts` from `client/` after touching `game/exit-path.ts` — plain script, prints `ok` |
| client | `bun tests/weapon-pose.ts` from `client/` after touching `render/guns.ts`, `game/weapon-feel.ts` or `make_guns.py` — plain script, prints `ok`. It reads the REAL atlas manifest, so it fails if the generator stops appending action frames |
| client | `bun tests/events.ts` from `client/` after touching `server/app/events.py`'s catalog or `client/src/game/events.ts` — plain script, prints `ok`. It reads the REAL catalog out of the Python, so it fails if the two sides of the night's script drift |
| client | `bun tests/boss-clock.ts` from `client/` after touching `render/boss.ts`, `app/boss.py` or `make_sawyer.py` — plain script, prints `ok`. It reads the REAL sawyer manifest and pins the one thing nothing at runtime notices: that the frame on screen when a blow lands is the frame the art says it lands on |
| assets | `python tools/make_armor.py` from `server/` after touching a worn overlay — it writes the raw art AND processes it, and it fails the build if any piece leaves the 16x16 player grid, which is the one way an overlay goes wrong invisibly |
| assets | `python tools/make_ultimates.py` from `server/` after adding an ultimate or editing a mark — it fails the build if the catalog and the sheet hold different keys, which is a HUD panel with a hole in it and the one failure a screenshot of the shop will not show |
| assets | `python tools/make_wolf.py` from `server/` after touching the pack rig — it writes the raw art AND processes all seven sheets, and it fails the build if any pixel reaches a frame unshaded (which is what a part painted outside the mask pass looks like). Follow it with `test_creature_sheets.py`, which counts the heads |
| assets | `python tools/make_sawyer.py` from `server/` after touching the boss rig — it is its own test: it fails the build if a one-shot does not start and end on the resting pose, or if any frame's art reaches the frame border |
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

Run `test_creature_sheets.py` after touching `make_zombie.py`, `make_wolf.py`
or reprocessing a creature: it checks that every creature and every accessory
still has a `-death` timeline, that the grids are what the renderer assumes
(READ off each manifest — a quadruped is not 16x16), and — the two worth
having — that the variants in a family are still different SHAPES, and that
each wolf still has the right number of HEADS. S15's silhouette test as
arithmetic: mask them, count the pixels and the top-contour columns that
differ, and fail if a variant has become a recolour of another. The head count
is the same trick one level up: every creature carries one lit accent pixel
per socket, so counting embers on the face-on frame counts heads, and a fan
that silently clipped one off the frame is invisible to everything else here.

Run `test_pack.py` after touching the wolves, `ai.shout` / `ai.wake` /
`MODE_SLEEP`, `EnemyType.group_min` / `persists`, `Room._seed_nests` or
`mapgen.DEN_SCENES`. It drives the whole miniboss encounter with nobody
watching: the den landing on the map, the thing asleep in the middle of it,
the extraction siren and the abandonment timer both failing to reach it, the
wake radius, the free beat it spends standing up, and the escape that walks it
home and puts it back to sleep. It also pins the one thing about the HOWL that
has no symptom — that it reaches its own kind at four times a shout's range
and does not wake the dead, which would otherwise make it a strictly better
shout that every future creature inherited by accident.

Run `test_boss_fight.py` after touching `boss.py`, `arena.py`, or the transit
in `room.py`: it drives a whole boss night with nobody watching — waking him,
the cinematic's length, blows landing, the crescent expiring, the enrage, the
exit his death carves, the crossing, and the night's takings surviving the
detour to reach the shop. Every one of those is a join where the fight can
silently stop, and none of them has a symptom you would see in a screenshot.

It also pins the three things about HIS MOVE SET that no screenshot shows:
that the picker still has more than one answer at every range and never plays
three of anything running; that the charge is still a RUN rather than a pose,
and still tells the client all three of the sheets it plays; and that the
enrage still changes the MOVES — a fan of crescents, a chop that comes
straight back — rather than only the clock.

Run `test_gear.py` after touching `armor.py`, the blade cell in `weapons.Hotbar`,
`Room.damage_player` / `wear_armor` / `swap_blade` / `sync_block`, or the shop's
stock ladders. It pins the three things about gear that have no symptom you
would see while playing: that the blade cell is never empty and that the KNIFE
is not an object (replacing it drops nothing, replacing anything else does);
that a set takes its material's flat rating off any blow and that a plate
survives exactly `HITS_BASE * tier` of them — and that `COVERAGE` sums to a
whole body, which nothing at runtime notices; and
that the shield blocks only what it is FACING, spends itself on the blow that
breaks it, and leaves the belt when it does. A shield that blocked from behind
would be a strictly-better plate and nobody would ever notice — they would
just stop dying.

Run `test_medical.py` after touching `medical.py`, `Room.use_medical` /
`_step_use` / `damage_player`, the `med` rows in `loot.ITEMS`, or the shop's
medicine ladder. It pins the four things about the medical belt that have no
symptom you would see while playing: that medicine is NOT CARGO (both kits are
`value=0`, and a price creeping back puts them into the quota, the payout and
the pocket's weight bar at once); that the cell is spent on the LAST frame and
only there, so an interrupted heal costs the seconds and keeps the item; that a
full belt REFUSES a third kit rather than swapping one away; and that the two
kits still trade on different axes rather than being one item twice. It also
pins the rule the docstrings already claimed but the code did not have — that
ANY blow cancels a heal, not only a fatal one. Without that, holding 4 while
walking backwards is free, and the "stand still in the open" the whole verb is
built on never happens.

Run `bun tests/events.ts` from `client/` alongside it. `events.py` and
`client/src/game/events.ts` are a mirror pair — the server ships an event KEY
and holds no interface copy — and the failure mode when they drift is the
quietest in the codebase: an event with no client row fires, does everything it
was written to do, and says NOTHING. The horde arrives with no howl and no
card. Both sides are behaving correctly and the game is broken in between them,
with no error anywhere to find.

Run `test_events.py` after touching `events.py`, the effect doors on `Room`
(`send_horde`, `begin_dark`, `drop_supplies`, `stir_at_downed`), or anything
that opens or closes the gate (`sirening`, `blackout`, `arriving`, `departing`,
the zone). It drives all three triggers with nobody watching, because a trigger
that never fires is indistinguishable from one whose odds are low and nobody
plays enough permanent nights to tell. It also pins the two claims that rot
quietest: that an effect which REFUSES spends no cooldown and no per-night
allowance — a rare event silently consumed by a firing nobody saw is invisible
from inside the game — and that adding an event really is a data row, asserted
against a row the test builds itself and drives through the unmodified
director.

Run `test_containers.py` after touching `crates.ObjectType.open_time`, the
vault row, `Room._begin_force` / `_finish_force`, or any scene that places a
chest-family container. It pins the four things about a timed object that
playing cannot see: that the noise goes out at the START (a slow open whose
noise came at the end is a gamble whose stake is paid after the payoff is
known, which is backwards and is one line away at all times); that an
interrupted force costs the seconds and leaves the object shut; that only ONE
pair of hands may work an object, since two completions would pay twice and a
duplication bug that looks like good luck is the kind nobody reports; and that
the tier is ACTUALLY ON THE MAP — `chest` and `strongbox` were catalog rows
with footprints and container-set entries that no scene ever placed, so the
domed lid `make_chest.py` argues about at length had never once appeared in a
game.

Run `test_quota.py` after touching `loot.ITEMS` values, `loot.SCENE_COUNTS`,
`crates.TYPES` or `rift.SUPPLY_BASE` / `SUPPLY_PER_PAD`. It re-measures real
generated forests and fails if the supply fit has drifted more than a tenth,
which is the only way a measurement written down once stays honest. It has
already earned its place: zeroing medicine's value in T-04 took two rows out of
the findable pile and moved the fit by a tenth at every pad count, and nothing
else anywhere would have noticed.

Run `test_skills.py` after touching `skills.py`, a `Mods` consumer site, or
`make_skills.ICONS`. Most of the catalog is `(field, number)` and needs no test;
what this pins is the tier that is NOT. A rule is a boolean read at exactly one
site, and a rule read nowhere looks identical to a skill the player has not
found yet — the canister lands, the tray shows the tile, and nothing happens
for the rest of the run. It drives each rule through the real code path it is
meant to change, checks that `lamp_immune` is honoured by BOTH halves of the
lantern suppression (one alone produces a lamp that lights for a single
packet), and asserts the trade-off rows still cost what their blurbs say — a
downside dropped in a rebalance is a strictly-better row, and nobody reports a
skill that is too good.

Run `test_ranged.py` after touching `projectiles.py`, `EnemyType`'s `ranged_*`
or `shot_*` fields, `ai.py`'s ranged branch, or `Room._throw` / `step_shots`.
It pins the five things about a creature that reaches which playing cannot
show you: that the near edge of its band HOLDS (a minimum that silently stopped
working turns it into a creature that is strictly better the closer it gets,
which just feels unfair); that the windup exists, PLANTS it and reaches the
wire; that the disc is slower than the player walks, which is arithmetic
nothing at runtime checks; that a disc is tested against the MAP before it is
tested against bodies, because the other order is a hit through cover; and that
`ai.py` still does not contain the name of a single creature — checked as text,
because a key comparison would work perfectly while quietly making the second
ranged creature a code change instead of a stat block.

Run `test_reroll.py` after touching `Room.reroll` / `reroll_price` or
`store.reroll_stands`. It pins the exploit that is one line away from this
feature: if a SOLD table came back on the next spin, the correct play would be
to buy the cheapest thing on the shelf and reroll until the shop had paid for
itself. Nobody reports a shop that is too generous — they just get rich, and
the economy quietly stops mattering. It also pins that the ladder doubles AND
resets (flat makes a rich night a queue at the counter; carried across the run
the price by night six is unreachable and the mechanic silently stops
existing), and that an empty shelf is a refusal rather than a purchase.

Run `test_weather.py` after touching `zones.WEATHER_RULES`, `ai.look` or
`ai.hear`. The sight scalar is half of a MIRROR — the other half is the
client's `render/fov.ts`, and the two are in different languages — and the
failure when they drift has no symptom: the player gets spotted from further
away than the wash they were shown said they could be. It also pins that a coat
cuts BOTH reaches (applied to the naked eye alone, the lantern silently becomes
a stealth item on foggy nights), and that the coats stay an INVERTED pair
rather than a difficulty ladder.

Run `test_ultimates.py` after touching `ultimates.py`, `Room.use_ultimate` /
`_charge_ult` / `_empower` / `step_ult_shots`, a weapon's `tags`, or a
material's. It pins the five things about synergy that have no symptom you
would ever see while playing, and each of them would read as bad DESIGN rather
than as a bug: a requirement that silently passes (every ultimate unlocks the
moment its weapon is picked up, and the whole feature quietly does not exist);
one that silently fails (identical, from inside the game, to an ultimate whose
armour you have not found — the player buys the set, presses R, gets nothing,
and concludes the key is broken); a bar that fills off the wrong weapon or the
wrong action, which makes "charge with whatever is convenient and fire with
whatever is strongest" the correct play; a window that follows its owner onto
another weapon, whose only symptom is somebody having a very good night; and
the architecture claim itself — it builds a fifth ultimate inside the test, for
a weapon that has never had one, and drives it through the unmodified room.

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
