# client/ — browser client

## Purpose

Vite + TypeScript app. Canvas 2D draws the game (no engine); React + Tailwind
own the HUD and routing only. Talks to the server over one WebSocket.

## Ownership

- `src/game/` — game loop, prediction, world state (child doc)
- `src/render/` — canvas renderer and its layers (child doc)
- `src/components/` — React components, ours and generated (child doc)
- Owned directly here:
  - `src/net/` — `connection.ts` (socket, reconnect, RTT) and `protocol.ts`
    (wire types, mirror of `server/app/protocol.py`)
  - `src/hooks/` — `useGameSession` owns one `Game` per mounted screen;
    `useHud` reads the store
  - `src/screens/`, `src/app/` — `ArenaScreen` and the route table
  - `src/theme/` — `palette.ts` / `fonts.ts`, which read the CSS tokens so the
    canvas can consume them
  - `src/lib/` — framework-free helpers: math, canvas, store, image, lens, utils
  - `src/styles/index.css` — Tailwind entry and **all** design tokens
  - `src/assets/fonts/` — Departure Mono, bundled and hashed by Vite
  - `vite.config.ts`, `tsconfig.json`, `package.json`, `components.json`

## Local Contracts

- **Layering:** rendering knows nothing about the network; networking knows
  nothing about rendering.
- **React never renders per frame.** `Game` publishes to `hud-store` at 5 Hz and
  components read it via `useSyncExternalStore`. Per-frame state must not become
  component state.
- **All colours live in `src/styles/index.css`.** The DOM consumes them as
  Tailwind utilities; the canvas reads the same custom properties through
  `theme/palette.ts`. Never hardcode a colour anywhere else. Type works the same
  way through `--font-hud` and `theme/fonts.ts`.
- **Never hardcode a gameplay constant.** They arrive in `welcome.config`.
- `src/net/protocol.ts` mirrors `server/app/protocol.py`; change both together.
- Anything created — sockets, timers, listeners, observers, rAF — must be
  released in `Game.dispose()`. StrictMode and HMR both remount, and a leaked
  loop is silent until the frame rate collapses.
- `publicDir` is `../assets/processed`, so art is fetched from `/player/...`,
  `/terrain/...`. `assets/raw` is never served.
- The app is permanently `<html class="dark">`.
- Imports may use the `@` alias for `src/`.

## Work Guidance

```bash
cd client && bun install && bun run dev
```

- `VITE_SERVER_URL=ws://host:8000/ws bun run dev` points at another host.
- Add coss components with `bunx --bun shadcn@latest add @coss/<name>`.

## Verification

- `bun run typecheck` (`tsc --noEmit`) — required after any change here.
- `bun run build` before shipping; it typechecks then builds.
- Open two tabs on `http://localhost:5173` and confirm both players move, shoot
  and light the world without rubber-banding.

## Child DOX Index

- `src/game/AGENTS.md` — loop, prediction/reconciliation, interpolation, world,
  effects, lantern, HUD seam
- `src/render/AGENTS.md` — camera, projection, sprites, fov, minimap, layers
- `src/components/AGENTS.md` — HUD components (ours) vs `ui/` (generated)
