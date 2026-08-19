# server/ — authoritative game server + asset pipeline

## Purpose

Python 3 process that owns the game. FastAPI serves a small room REST pair
(`POST /rooms`, `GET /rooms/{code}`) and one WebSocket endpoint per room
(`/ws/{code}`); a started room runs a fixed 30 Hz tick, simulates every entity,
and broadcasts JSON snapshots. The same tree also holds the offline asset
pipeline that produces everything the client renders.

## Ownership

- `app/` — runtime simulation, protocol, tuning (child doc)
- `tools/` — asset generation and processing scripts (child doc)
- Root-owned here: `requirements.txt` (fastapi, uvicorn, pillow)

## Design law

Why the simulation is shaped this way: [`docs/design/`](../docs/design/) — one file per subsystem, indexed from the root `AGENTS.md`. Whole-system map: [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Local Contracts

- The server is authoritative. Clients send inputs, never positions.
- Every gameplay constant lives in `app/config.py` and reaches the client in
  `welcome.config`. A constant the client needs but the payload does not carry
  is a bug in `client_config()`, not a reason to hardcode it client-side.
- Nothing in `app/` may import from `tools/`, and nothing in either may know
  about rendering.
- Dependencies are installed into `server/.venv`; every command below is run
  from `server/`.

## Work Guidance

- Author sizes, speeds and distances in **tiles/seconds**, then multiply by
  `TILE_SIZE`. Never write a raw pixel number.
- Changing a wire shape means editing `app/protocol.py` and
  `client/src/net/protocol.ts` in the same change.
- `python -m uvicorn app.main:app --reload --port 8000` is the run command
  (`.venv/bin/python` on POSIX, `.venv\Scripts\python.exe` on Windows).

## Verification

- `python tests/test_snapshot_shape.py`, `python tests/test_pour.py` and
  `python tests/test_store_walk.py` from `server/`. Plain scripts, no runner,
  each prints `ok`. The last one flood-fills the shop and fails if the exit,
  the merchant, a stall or the cabinet cannot be walked to — run it after any
  edit to `store.py`'s layout offsets.
- Then run the server and join from two browser tabs; check the server stays at
  a steady tick and no client rubber-bands.

## Child DOX Index

- `app/AGENTS.md` — the tick loop, entities, combat, AI, map generation, wire
  protocol, tuning constants
- `tools/AGENTS.md` — sprite, terrain and HUD-icon generation into `assets/`
