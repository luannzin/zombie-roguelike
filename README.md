# Zombie Roguelike — Vertical Slice

Browser-based multiplayer 2D pixel-art expedition roguelike. No auth, no setup,
no install: open the link, take a name, and you are at a campfire with your
friends. One of you presses start and the night begins.

The whole flow is three screens. `/` is the title: pick a name, then **create a
room** (the server generates a 7-character code and its own camp) or **join
one** with a code somebody read out to you. Both land you on `/r/CODE` — the
invite link — where the party gathers around a fire while the host waits for
stragglers. Rooms live in memory and are dropped when the last player leaves;
nothing is stored anywhere, and the only thing your browser remembers is the
name you chose.

The lobby is not a picture of the camp. It **is** the camp: the map comes down
in `hello` and everybody stands on the coordinates the server is already
holding for them, so pressing start changes what answers your input and nothing
else. The roster slides off the glass while the camera drifts off the fire onto
your own character and closes in; the game picks the shot up mid-move, holds
you still and facing the camera with the HUD off, and the day names itself —
`Preparação`, `Dia 1` — before you get the controls. Then you walk around, and
your lantern stays off, because the bonfire is the light and the battery is
what you carry out into the dark.

> **Where the loop stops today.** A run is meant to go camp → level → extract →
> spend → repeat. Preparation and the walk-out exist: ready at the fire, file
> through the black exit, land in the forest. Extract and return are not built.

* **Client** — Vite + TypeScript + Canvas 2D (no game engine). React + Tailwind
  own the HUD and routing only; they are never part of the render loop.
* **Server** — Python + FastAPI + asyncio, authoritative, fixed 30 Hz tick
* **Transport** — one WebSocket, JSON messages

## Run

Server (terminal 1):

```bash
cd server && uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Windows:

```bash
cd server && uv venv .venv && uv pip install --python .venv\Scripts\python.exe -r requirements.txt && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Client (terminal 2):

```bash
cd client && bun install && bun run dev
```

Open http://localhost:5173, create a room, then paste `/r/CODE` into a second
tab. Each tab is its own player, with its own name, colour, id and seat at the
fire. On another device, use the Network URL Vite prints (`http://192.168.x.x:5173`);
the client talks to that same origin and Vite proxies `/ws` to the server.

Controls: **WASD** move · **mouse** aim · **left click / hold** shoot · **F**
lantern on/off · **E** ready (at the campfire) / collect (a nearby drop) ·
**TAB** backpack.

Point the client at another host with `VITE_SERVER_URL=http://192.168.0.10:8000 bun run dev`
— an HTTP origin, not a socket URL; the client derives both from it. That host
must bind uvicorn with `--host 0.0.0.0`.

## Scale

`TILE_SIZE` in [server/app/config.py](server/app/config.py) is the single
number that defines the game's scale. Every size, speed and distance is
authored in **tiles** and multiplied by it, so changing it rescales everything
consistently.

| | tiles | px at `TILE_SIZE = 16` |
| --- | --- | --- |
| tile | 1 x 1 | 16 x 16 |
| sprite frame | 1 x 1 | 16 x 16 |
| collision box | 0.6 x 0.45 | 9.6 x 7.2 |
| hit capsule | r 0.3 × sprite H | r 4.8, full body |
| move speed | 4.4 / s | 70.4 px/s |
| shot range | 16 | 256 px |

Movement is **continuous**, not tile-by-tile: position is a float in world
pixels and the grid only answers collision (and later, pathfinding) queries.
That costs the server almost nothing — one move is a few float ops plus an
overlap test against at most 4 tiles, so a tick is O(entities), never O(map).

The collision box is deliberately much smaller than the sprite: a full 1-tile
box cannot fit through a 1-tile gap. Position is the **centre of the collision
box**, and a sprite is drawn with its bottom edge at `y + playerHalfHeight`, so
frames of any height (bosses, tall zombies) anchor correctly with no extra code.

## Enemies

An **`EnemyType`** ([server/app/enemies.py](server/app/enemies.py)) is a frozen
stat block — health, damage, speed, aggro range, attack range and cooldown, and
the xp and gold it pays out. An **`Enemy`** is one live instance of a type. The
instance exposes the same hit-capsule shape as `Player`, so `combat.raycast`
shoots both from a single target list, and per-type constants never enter a
snapshot: the wire carries a type key, and the client looks it up in
`welcome.config.enemyTypes`.

Adding a creature is a stat block, a spawn weight, and a sprite sheet of the
same name. No client change, no new draw path, no protocol change.

| | zombie |
| --- | --- |
| health | 30 (4 shots) |
| damage | 9 per hit, every 1.1 s |
| speed | 2.6 tiles/s vs the player's 4.4 — always outrunnable |
| pays | 12 xp, 3 gold |

Behaviour is in [ai.py](server/app/ai.py): chase the nearest living player,
swing on contact. Steering walks straight at the target while the enemy's full
body width has a clear line to it, and otherwise follows a BFS **flow field**
from [pathing.py](server/app/pathing.py) — one field per player, rebuilt when
they change tile and shared by every enemy hunting them, so the cost does not
grow with the size of the horde. Greedy chase alone cannot round a corner: it
presses into the wall and the collision slide cancels the only axis that was
helping. A stuck detector backs it up, dropping an enemy that stops making
headway onto the field route.

Melee damage is rate-limited **per victim** (`MELEE_IMMUNITY`), so a pack that
surrounds you cannot resolve eight swings on one tick and delete you — eight
zombies deal what one does, and the swings they waste are drawn as absorbed
rather than dropped. The director scales the population with the number of
living players, spawns in a ring around a random one, and recycles enemies
everyone has run away from.

## Light

Vision is a **client** system ([render/fov.ts](client/src/render/fov.ts)): the
server broadcasts the whole world and the client decides what you are allowed to
make out. Four lights per player, brightest wins per tile, all of them traced
with recursive shadowcasting so cover throws real shadows:

| | reach | what it is for |
| --- | --- | --- |
| sight | full lantern range | a near-zero wash over everything in line of sight — enemies in it are drawn at ~20% alpha, so the dark holds silhouettes instead of nothing |
| ambient | `visionAmbientTiles` | you can always see your own feet |
| beam | `visionLanternTiles` | the cone along your aim |
| spill | 50% of the beam | a weak halo, so the cone is not a stencil |

Two fields come out of that pass. `light` is visibility and saturates at 1;
`heat` is warmth and keeps climbing as you approach the lamp, which is what the
darkness layer turns into additive amber. That split is why the ground under
your feet reads as *bright* while the far end of the same beam is a pale wash.

The lamp runs on a **battery of four cells**
([game/lantern.ts](client/src/game/lantern.ts)), drawn on the HUD as four pixel
batteries that drain top-down from the right. The cells are a readout: the lamp
burns continuously for four minutes and only cuts out once the battery is flat,
at which point **F** does nothing until it has trickled back. On the last cell
it starts dropping out at random, and the
HUD tears in sympathy. Switching on stutters before it catches; dying puts it
out. It trickles back while off, at less than half the rate it drains, so
darkness is the resource you spend to get light back.

The battery is client-local — the server does not know the lamp exists, so
remote players always light at full output.

## Assets

Source art is a 3×3 sprite sheet on solid magenta (`assets/raw/`). The pipeline
keys out the magenta, crops, normalizes, mirrors the side frames and packs a
production sheet into `assets/processed/`. Art already composed at an integer
multiple of the target frame passes `--exact`, which skips the crop/normalize
step so the artist's placement survives verbatim. The game only ever reads
`assets/processed/` (Vite serves it as its `publicDir`).

```bash
cd server
./.venv/bin/python tools/make_placeholder_sheet.py --name player   # regenerate placeholder raw art
./.venv/bin/python tools/process_sprites.py --name player --tile 16 --side-facing left --exact

./.venv/bin/python tools/make_placeholder_sheet.py --name zombie
./.venv/bin/python tools/process_sprites.py --name zombie --tile 16
```

Terrain, effects and HUD icons have no raw stage — they are generated straight
into `assets/processed/`, deterministically:

```bash
./.venv/bin/python tools/make_textures.py     # floor, rocks, trees, ferns, campfire
./.venv/bin/python tools/make_vfx.py          # summon beam
./.venv/bin/python tools/make_hud_icons.py    # battery.png for the lantern gauge
```

Two kinds of animated sheet, and the difference matters. The campfire's eight
frames are a **loop**: every wobble is a sine of the frame phase, so the last
frame hands back to the first with no snap. The summon beam's fourteen are a
**timeline** played once per arrival — charge, strike, impact, collapse — and
its `frames / fps` is what the lobby times the whole materialisation against.

`--tile` must match `TILE_SIZE`. The same command processes future characters,
zombies and NPCs — only `--name` changes (plus `--height` for taller entities). Player colours are a runtime multiply tint over the single base sheet;
no per-colour art exists.

Placeholder art sets live in `ENTITIES` in `make_placeholder_sheet.py` (`player`,
`zombie`) as 12-column ASCII art over a per-entity palette; `--entity` picks one
and defaults to `--name`. Detail finer than 2 raw pixels does not survive the
downscale to a 16x16 frame, so read features (eyes, wounds) need luminance
contrast, not just hue.

## Layout

```
server/
  app/
    main.py         FastAPI app: room REST + the /ws/{code} endpoint
    rooms.py        room registry: code generation, lookup, disposal
    room.py         authoritative room: lobby phase, zone, tick loop, broadcast
    simulation.py   movement (mirrored by the client for prediction)
    combat.py       hitscan raycast (entity-agnostic — players and enemies)
    world.py        tile grid + collision
    pathing.py      BFS flow field per player — how enemies get around cover
    maps.py         map data and builders
    camp.py         the camp clearing, its bonfire and the seat ring
    zones.py        where a run is: title card, hostile, lantern
    entities.py     Player / InputCmd
    inventory.py    the pocket: slots, stacking, weight
    enemies.py      EnemyType stat blocks + live Enemy instances
    ai.py           enemy behaviour (chase, attack) + the spawn director
    protocol.py     wire message shapes
    config.py       tuning constants, shipped to the client on join
  tools/            asset pipeline
client/
  src/
    net/            connection, protocol types, server endpoints, room REST
    game/           world, simulation, prediction, interpolation, input, effects,
                    combat, per-player visuals, lantern battery, game loop,
                    lobby-scene (the campfire), hud-store (UI seam)
    render/         camera, projection, framing, sprites/tinting, minimap, fov,
                    renderer, terrain + vfx atlas loading
      layers/       terrain, entities, effects, atmosphere, darkness, vignette
    theme/          palette.ts / fonts.ts — read the CSS tokens for canvas use
    lib/            math, canvas, store, lens (HUD barrel map), utils
                    (framework-free helpers)
    components/
      game/         canvas hosts (GameCanvas, MinimapCanvas)
      hud/          HUD components — ours
      lobby/        CampfireCanvas, RoomCode, PlayerRoster
      menu/         MenuButton, HudInput, JoinRoomDialog
      ui/           coss primitives — GENERATED, do not hand-edit
    hooks/          useRoomSession (owns the socket), useGameSession (owns Game),
                    useHud
    screens/        HomeScreen, RoomScreen, LobbyScreen, ArenaScreen
    app/            route table — / and /r/:code
    assets/fonts/   Departure Mono (bundled + hashed by Vite)
    styles/         index.css — Tailwind entry + ALL design tokens
assets/
  raw/              source art + font sources (never served)
assets/
  raw/              source art (never served)
  processed/        production art (served by Vite): sprites, terrain, vfx, hud
docs/
  netcode.md        protocol + prediction/reconciliation details
```

## Architecture rules

* The server is authoritative. Clients send **inputs**, never positions.
* All gameplay constants live in `server/app/config.py` and reach the client in
  the `welcome` message, so prediction runs the server's numbers.
* `server/app/simulation.py` and `client/src/game/simulation.ts` are mirrors.
  Change one, change the other, or the local player will rubber-band.
* Rendering knows nothing about the network; networking knows nothing about
  rendering; the server simulation knows nothing about either.
* One socket per room, owned by `useRoomSession`, carrying the lobby and then
  the run. `Game` subscribes to it and never closes it — starting a match must
  not mean reconnecting and becoming a different player.
* Rooms are in-memory and code-addressed (`server/app/rooms.py`). A room with no
  sockets left is dropped, tick task and all.
* React never renders per frame. `Game` publishes a snapshot to `hud-store` at
  5 Hz and React reads it via `useSyncExternalStore`; everything that changes
  every frame is drawn to canvas. Do not move per-frame state into component
  state.
* **All colours live in `client/src/styles/index.css`.** The DOM consumes them
  as Tailwind utilities, the canvas reads the same custom properties at runtime
  through `theme/palette.ts`. Never hardcode a colour anywhere else. Type works
  the same way via `--font-hud` and `theme/fonts.ts`.
* The UI kit is [coss](https://coss.com/ui) (Base UI + shadcn-style copy-in).
  Its components live in `components/ui/` and are generated — add more with
  `bunx --bun shadcn@latest add @coss/<name>`, don't hand-edit them. coss's
  semantic tokens (`--background`, `--border`, `--destructive`, …) are
  re-pointed at the game palette in the **coss skin** block at the bottom of
  `index.css`, so its components inherit the arena's look with no per-component
  overrides. The app is permanently `<html class="dark">`.
* Anything the client creates — sockets, timers, listeners, observers, rAF —
  must be released in `Game.dispose()`. React StrictMode and HMR both remount,
  and a leaked loop is silent until the frame rate collapses.

## Extension points

| Later feature | Where it goes |
| --- | --- |
| a new enemy | one `EnemyType` in `enemies.py` + a weight in `SPAWN_TABLE` + a processed sprite folder of the same name. No client change: stats and art name ship in `welcome.config.enemyTypes` |
| a new enemy behaviour | `ai.py` — `update()` decides, `Room` applies. Steering already has flow-field navigation to reuse |
| projectiles | new entity list in `Room`, new event array in the snapshot |
| weapons, upgrades, shops | fields on `Player` + constants in `config.py`; `gold` is already accumulating |
| procedural maps | another builder in `maps.py` returning `list[list[int]]` |
| multiple rooms | `Room` is not a singleton — key a dict by room id and put the id in the WS path |
| new characters | run the asset pipeline with a different `--name` |
| battery pickups | a coin-shaped entity in `Room` + a `pickups` event; give `Lantern` a `refill()` and set `RECHARGE_SECONDS` to `Infinity` so cells stop trickling back on their own |
