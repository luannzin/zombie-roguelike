# ARCHITECTURE

Compressed whole-system model. **You do not need this for every task** — see
the routing table in [`AGENTS.md`](AGENTS.md). Come here when you cannot tell
which subsystem owns a task, or when a change crosses the client/server line
and you need the authority table. Then follow the *Major subsystems* row to
that subsystem's design law in [`docs/design/`](docs/design/) and stop.

**The source is the truth; if this file disagrees with the code, the file is
wrong.**

## Product

Browser-based multiplayer 2D pixel-art zombie roguelike. Open a link, pick a
name, create or join a room by its 7-character code, wait at the campfire,
start. A run is a repeating night: walk into a dark forest, find the extraction
platform, load it with what you found, call the pickup, run for the exit that
opens, spend the takings at a merchant, walk into the next night.

## Runtime

```
Python 3 / FastAPI                        Vite / TypeScript / Canvas 2D + React
uvicorn app.main:app  :8000  <--- one WebSocket per room --->  :5173
  in-memory rooms                            no game engine
  fixed 30 Hz tick                           two clocks: 30 Hz tick + rAF
  JSON snapshots                             React owns HUD + routing only
```

- Nothing is persisted. A room's whole content is its live players; it dies with the last socket. The only durable client datum is the player's name in `localStorage`.
- `server/tools/` is an **offline** asset pipeline (Pillow + stdlib) that generates every pixel and sound into `assets/processed/`. It never runs at request time and `server/app/` may not import from it.
- Vite's `publicDir` is `assets/processed`, so art is fetched as `/player/sheet.png`, `/audio/shot-0.wav`, ….

## High-level architecture

```
input (keys/mouse)
  -> client prediction (simulation.ts)            [instant, local, replayable]
  -> InputPacket over WebSocket
       -> Room.queue_input -> fixed 30 Hz tick    [AUTHORITY LIVES HERE]
            simulation -> combat -> ai -> rift/quests -> events
       -> one snapshot JSON, serialised ONCE for the whole room
  -> client reconciles local player (prediction.ts), interpolates remotes
  -> render passes + audio + hud-store (5 Hz)     [presentation only]
```

Three layering rules, enforced by convention and worth defending:

- rendering knows nothing about the network
- networking knows nothing about rendering
- `server/app/` knows nothing about either

## Gameplay state machine

Verified against `Room.advance_zone` / `zones.py`. **The loop never returns to
the camp.**

```
lobby (nothing ticks; camp map already drawn)
  |  Room.begin()          host presses start -> phase becomes "playing"
  v
preparation  (zone=camp, hostile=False, lantern=False)
  |  every living player ready at the fire -> begin_depart -> embark()
  v
forest  (zone=forest, hostile=True, ambient=0)   <-------------+
  |  arrive out of an edge corridor -> it seals behind you     |
  |  find pad(s): 1 on day 1-2, 2 on day 3-4, 3 on day 5+      |
  |  pour cargo -> quota met -> call pickup -> siren + hunt_all|
  |  LAST pad launches: loot swept, lanterns die, exit carved  |
  |  cross the VOID corridor                                   |
  v                                                            |
store  (zone=store, hostile=False, ambient=0.45)               |
  |  balance credited on the crossing (enter_store)            |
  |  buy from six stalls; spend levels at the machine          |
  |  walk out of the north corridor -> depart_store, day += 1 -+
```

`preparation` runs once per room. `embark`, `enter_store` and `depart_store`
are the only three legal map swaps and they share `Room._swap_map`: each sends
a second `welcome` on the same socket, keeps guns / bag / xp / balance, and
never resets `last_processed_seq`.

## Client / server authority

The intended model and the real one agree. Verified.

| | SERVER (`server/app/`) | CLIENT (`client/src/`) |
| --- | --- | --- |
| position | authoritative; clients send inputs, never positions | predicts locally, replays on ack |
| combat | every ray, arc, damage number and kill | tracers, blood, wounds, hit juice |
| enemies | mode, awareness, facing, damage | the hunt diamond, snarls, collapse |
| loot / objects | placement, roll, collection, drop | flies, tooltips, pops |
| inventory / belt | slots, stacking, weight, trades | the bag panel, drag-to-drop intent |
| ammunition | the reserve, every spend | the number on the cell |
| extraction | pad state, quota, the pour's clock, the sweep | drones, ropes, lamps, the deck pile |
| economy | `Room.balance`, prices, purchases | the coin spray and the counting number |
| skills | the roll, `Mods` | reels, canister, tray |
| zones | title, `hostile`, `lantern`, `ambient` | obeys; infers nothing from the map |
| world | tiles, scenes, lights, corridors | terrain scatter hashed from `map.seed` |
| camera, audio, HUD, particles | — | wholly owned |

The one deliberate client authorship: `heldSlot` (which belt cell is in hand),
which is why `Player.carry_weight` is rebuilt client-side as `Game.moveWeight`
rather than read off the wire.

## Major subsystems

| subsystem | server | client | design law |
| --- | --- | --- | --- |
| room lifecycle / wire | `main.py`, `rooms.py`, `room.py`, `protocol.py` | `net/`, `hooks/useRoomSession` | `server/app/AGENTS.md` |
| movement / prediction | `simulation.py`, `config.py` | `game/simulation.ts`, `prediction.ts`, `interpolation.ts` | [`player.md`](docs/design/player.md) |
| weapons / combat / ammo | `weapons.py`, `combat.py`, `ammo.py` | `game/combat.ts`, `render/guns.ts`, `weapon-vfx.ts` | [`player.md`](docs/design/player.md) |
| enemies / AI | `enemies.py`, `ai.py`, `pathing.py`, `corpses.py` | `render/layers/vision.ts`, `entity-visuals.ts` | [`enemies.md`](docs/design/enemies.md) |
| world gen / scenery / objects | `mapgen.py`, `maps.py`, `world.py`, `scenery.py`, `crates.py`, `camp.py`, `zones.py` | `game/world.ts`, `objects.ts`, `render/layers/terrain.ts`, `scenery.ts` | [`world.md`](docs/design/world.md) |
| extraction | `rift.py`, `entrance.py`, `quests.py` | `render/layers/rift.ts`, `game/pad-cargo.ts`, `exit-guide.ts` | [`extraction.md`](docs/design/extraction.md) |
| loot / inventory / currency | `loot.py`, `inventory.py`, `coins.py` | `components/hud/Inventory.tsx`, `game/loot-flies.ts` | [`player.md`](docs/design/player.md) |
| store / economy | `store.py` | `render/layers/store.ts`, `layers/payout.ts`, `game/payout.ts` | [`store.md`](docs/design/store.md) |
| gear / armour | `armor.py`, `weapons.py` (the belt) | `components/hud/Armor.tsx`, `game/gear-card.ts` | [`gear.md`](docs/design/gear.md) |
| ultimates / synergy | `ultimates.py`, `projectiles.py` | `components/hud/Ultimate.tsx`, `render/ultimates.ts` | [`ultimates.md`](docs/design/ultimates.md) |
| skills / machine | `skills.py`, `machine.py` | `game/machine.ts`, `render/machine.ts`, `skills.ts` | [`skills.md`](docs/design/skills.md) |
| rendering | — | `render/` (+ `render/layers/`) | `client/src/render/AGENTS.md` |
| audio | `tools/make_audio.py` (generation) | `audio/` | [`presentation.md`](docs/design/presentation.md) |
| HUD | — | `components/hud/`, `game/hud-store.ts` | `client/src/components/AGENTS.md` |
| asset pipeline | `tools/make_*.py`, `process_sprites.py` | consumes `assets/processed/` | `server/tools/AGENTS.md`, `assets/AGENTS.md` |

## Important data flows

**Every tick (30 Hz)**
`queue_input` -> `step_players` (apply input, stamina, attacks) -> `step_enemies`
(senses, steering, attacks) -> `step_rift` / `step_quests` -> one `snapshot`
dict -> `protocol.dumps` -> broadcast.

**A shot**
client predicts tracer + hit feel -> `attack` on the input packet -> `Room.fire`
-> `ammo` spend, `combat.raycast`, `damage_enemy` (folds `Mods` once, above both
the event and the resolution) -> `ai.alarm` + `ai.Noise` -> `shots` / `kills`
events -> client draws muzzle, impact, wound, floating damage.

**A night's value**
`loot.scatter` (a second pass over `scenery`'s scene list) -> pocket ->
`Room._tip_item` one unit per `POUR_BEAT` -> `Rift.fed` -> `Room.enter_store`
credits `sum(rift.fed)` into `Room.balance`, **once** -> `store.price_of` spends
it. Loot still in the bag is not money.

**A new world**
`mapgen.build_forest(seed, day, calibres=ammo.party_calibres(...))` -> `_connect` -> `scenery.populate`
(scenes + route) -> `loot.scatter` + `ammo.scatter` over those scenes ->
`crates.attach` -> `rift.plot` -> `MapPayload` on `welcome`.

## Critical contracts

| contract | rule |
| --- | --- |
| **authority** | clients send inputs, never positions |
| **mirrors** | SIX pairs, changed in one edit. Line-for-line: `simulation.py` <-> `game/simulation.ts`; `protocol.py` <-> `net/protocol.ts`; `machine.py` <-> `game/machine.ts`. Re-derived, and no less breakable: `world.py` <-> `game/world.ts` (tile alphabet + collision); `Room.collect_loot`+`Inventory.add`+`ammo.Reserve` <-> `game/interaction.ts` (is this pickup legal — answered locally because a prompt cannot wait for a round trip); `ai.look` <-> `render/fov.ts` (sight symmetry) |
| **config** | every gameplay constant lives in `server/app/config.py` and reaches the client in `welcome.config`. A constant the client needs but the payload lacks is a bug in `client_config()`, not a licence to hardcode. Always-sent fields are REQUIRED on `GameConfig`, so hedging one (`config.x ?? 100`) is a type error; `tests/test_config_parity.py` holds the two key sets equal both ways |
| **units** | author sizes/speeds/distances in tiles and seconds, then multiply by `TILE_SIZE`. No raw pixel numbers |
| **snapshot** | one payload for the whole room, serialised once. Nothing may differ per recipient (an input ack rides the player's own row as `seq`). Only what MOVES goes at 30 Hz; identity rides `roster` every `ROSTER_EVERY_N_TICKS` |
| **economy** | the server credits extracted value exactly once, in `Room.enter_store`. The client's payout animation is presentation. **The client must never perform settlement** |
| **skill mods** | `skills.Loadout.mods` is the only place a player's numbers diverge from `config.py`. A site reading the raw constant is a skill silently doing nothing |
| **determinism** | `assets/processed/` is reproducible output — rerunning a generator must change only intended files. Terrain scatter is a pure function of `(tx, ty, map.seed)` |
| **asset keys** | a folder name under `assets/processed/` is a protocol-visible string (`enemyTypes[*].sprite`, `hats`, `clothes`, `coinSprite`, `backpackSprite`). Renaming a folder is a wire change |
| **frame order** | generator lists (`weapons.WEAPONS`, skills, loot icons) are **append-only** — inserting moves every existing frame index |
| **sight symmetry** | an enemy sees a shape exactly as far as the shape sees it. Both halves now read ONE source: `ENEMY_VIEW_DARK_SCALE` / `ENEMY_VIEW_LIT_SCALE` ship as `enemyViewDarkScale` / `enemyViewLitScale`, `ai.look` tests the cone against them and `render/fov.ts` draws the wash at them. They used to be hand-copied into `fov.ts` as `EYE_REACH` / `SIGHT_REACH` — a rule whose breakage has no symptom except a player seeing a radius the creatures do not respect |
| **room ownership** | `rooms.py` owns every live `Room`; a reference held elsewhere outlives `rooms.drop()` and keeps a tick task alive |
| **lifetime** | anything created in the client (sockets, timers, listeners, rAF) must be released in `Game.dispose()` |

## Repository map

```
ARCHITECTURE.md      this file
STATE.md             current phase, priorities, do-not-touch
AGENTS.md            root work contract + AI context rules
docs/
  design/            per-subsystem design law (the "why"), 7 files
  netcode.md         protocol tour
  superpowers/specs/ dated design specs (historical intent)
server/
  app/               authoritative simulation — 30 files, flat, ~15.5k LOC
  tools/             offline asset generators — ~18k LOC, never imported by app/
  tests/             three plain scripts, no runner, each prints `ok`
client/
  src/game/          loop, prediction, world, effects, the HUD seam
  src/render/        canvas renderer + layers/
  src/net/           socket, wire types
  src/components/    hud/ (ours) and ui/ (generated coss/shadcn — do not hand-edit)
  src/audio/         buses, one-shots, beds
  src/screens/ app/ hooks/ lib/ theme/ styles/
assets/
  raw/               source art, never served
  inspiration/       reference material, never shipped, never read at runtime
  processed/         generated production art + audio (Vite publicDir)
```

## Architectural invariants

1. The server is authoritative for gameplay; the client is presentation.
2. Money is created in exactly one function, once.
3. The three mirror pairs move together or the game desyncs.
4. Gameplay constants live in `config.py` and travel in `welcome.config`.
5. `assets/processed/` is output — edit the generator, never the PNG.
6. Anything decidable from `(tx, ty, seed)` belongs to the client; anything whose meaning is a relationship is a server-placed scene.
7. A scene, not a prop, is the unit of world placement.
8. `zone.ambient` is zero in every zone a player can be killed in.
9. A skill's effect exists only where `Mods` is read.
10. Generated-asset lists are append-only.
