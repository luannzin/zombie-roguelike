# Zombie Roguelike — Vertical Slice

Browser-based multiplayer 2D pixel-art arena. No lobby, no auth, no setup:
open the page, you are in the game.

* **Client** — Vite + TypeScript + Canvas 2D (no engine, no React)
* **Server** — Python + FastAPI + asyncio, authoritative, fixed 30 Hz tick
* **Transport** — one WebSocket, JSON messages

## Run

Server (terminal 1):

```bash
cd server && uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Client (terminal 2):

```bash
cd client && bun install && bun run dev
```

Open http://localhost:5173 in two or more tabs. Each tab joins the same room
with its own random name, colour, id and spawn point.

Controls: **WASD** move · **mouse** aim · **left click / hold** shoot.

Point the client at another host with `VITE_SERVER_URL=ws://192.168.0.10:8000/ws bun run dev`.

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
| hit circle | r 0.375 | r 6 |
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

## Assets

Source art is a 3×3 sprite sheet on solid magenta (`assets/raw/`). The pipeline
keys out the magenta, crops, normalizes, mirrors the side frames and packs a
production sheet into `assets/processed/`. The game only ever reads
`assets/processed/` (Vite serves it as its `publicDir`).

```bash
cd server
./.venv/bin/python tools/make_placeholder_sheet.py --name player   # regenerate placeholder raw art
./.venv/bin/python tools/process_sprites.py --name player --tile 16
```

`--tile` must match `TILE_SIZE`. The same command processes future characters,
zombies and NPCs — only `--name` changes (plus `--height` for taller entities). Player colours are a runtime multiply tint over the single base sheet;
no per-colour art exists.

## Layout

```
server/
  app/
    main.py         FastAPI app + /ws endpoint
    room.py         authoritative room: tick loop, spawning, broadcast
    simulation.py   movement (mirrored by the client for prediction)
    combat.py       hitscan raycast (entity-agnostic — zombies plug in here)
    world.py        tile grid + collision
    maps.py         map data and builders
    entities.py     Player / InputCmd
    protocol.py     wire message shapes
    config.py       tuning constants, shipped to the client on join
  tools/            asset pipeline
client/
  src/
    net/            connection + protocol types
    game/           world, simulation, prediction, interpolation, input, effects, combat, game loop
    render/         camera, sprites/tinting, renderer
assets/
  raw/              source art (never served)
  processed/        production art (served by Vite)
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

## Extension points

| Later feature | Where it goes |
| --- | --- |
| zombies / AI / spawning | new dataclass beside `Player`, stepped in `Room.step`; already targetable by `combat.raycast` |
| projectiles | new entity list in `Room`, new event array in the snapshot |
| weapons, upgrades, XP, levels | fields on `Player` + constants in `config.py` |
| procedural maps | another builder in `maps.py` returning `list[list[int]]` |
| multiple rooms | `Room` is not a singleton — key a dict by room id and put the id in the WS path |
| new characters | run the asset pipeline with a different `--name` |
