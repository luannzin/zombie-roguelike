# client/ — browser client

## Purpose

Vite + TypeScript app. Canvas 2D draws the game (no engine); React + Tailwind
own the HUD and routing only. Talks to the server over one WebSocket.

## Ownership

- `src/game/` — game loop, prediction, world state, the lobby scene (child doc)
- `src/render/` — canvas renderer and its layers (child doc)
- `src/components/` — React components, ours and generated (child doc)
- Owned directly here:
  - `src/audio/` — `engine.ts` (context, the three buses, gesture unlock, mute),
    `library.ts` (the generated catalog and its decoded buffers), `sfx.ts`
    (one-shots: variant, detune, world position), `beds.ts` (looping ambience
    and the crossfades between places)
  - `src/net/` — `connection.ts` (socket, reconnect, RTT, multicast delivery),
    `protocol.ts` (wire types, mirror of `server/app/protocol.py`),
    `endpoints.ts` (where the server is) and `rooms.ts` (the room REST pair)
  - `src/hooks/` — `useRoomSession` owns one socket per mounted room and holds
    the camp from `hello`, `useGameSession` owns one `Game` per playerId (a
    second welcome is a zone change inside that Game, not a remount),
    `useHud` reads the store
  - `src/screens/`, `src/app/` — `HomeScreen`, `RoomScreen`, `LobbyScreen`,
    `ArenaScreen` and the route table
  - `src/lib/identity.ts` — the player's name, generated and remembered locally
  - `src/theme/` — `palette.ts` / `fonts.ts`, which read the CSS tokens so the
    canvas can consume them
  - `src/lib/` — framework-free helpers: math, canvas, store, image, lens, utils
  - `src/styles/index.css` — Tailwind entry and **all** design tokens
  - `src/assets/fonts/` — Departure Mono, bundled and hashed by Vite
  - `vite.config.ts`, `tsconfig.json`, `package.json`, `components.json`

## Local Contracts

- **Layering:** rendering knows nothing about the network; networking knows
  nothing about rendering. **Audio knows about a listener at a point and sounds
  at other points, and nothing about players, zombies or zones** — sound names,
  per-sound gain and bus routing all come off the generated manifest, so adding
  a sound is a recipe in `server/tools/make_audio.py` plus a call site.
- **A page may not make noise until it has been touched.** `src/audio/engine.ts`
  installs its own gesture listeners and builds the `AudioContext` on the first
  one; `main.tsx` calls `installAudioUnlock` once, outside React, and preloads
  the opening set on that same beat, since decoding cannot start earlier. Before
  that, `playSfx` is a no-op rather than an error, and there is deliberately no
  "click to enable audio" gate. M toggles mute anywhere; the setting is in
  `localStorage` under `zr:audio`.
- **Ambience is declarative.** Callers state what the world sounds like
  (`setBeds({ wind: 1, night: 0.85 })`), never start/stop beds. It is
  idempotent, safe to call before the buffers have decoded (it retries when they
  land), and it is what makes the camp → forest hand-off one call in one place.
- **React never renders per frame.** `Game` publishes to `hud-store` at 5 Hz and
  components read it via `useSyncExternalStore`. Per-frame state must not become
  component state.
- **All colours live in `src/styles/index.css`.** The DOM consumes them as
  Tailwind utilities; the canvas reads the same custom properties through
  `theme/palette.ts`. Never hardcode a colour anywhere else. Type works the same
  way through `--font-hud` and `theme/fonts.ts`.
- **Never hardcode a gameplay constant.** They arrive in `welcome.config`.
- `src/net/protocol.ts` mirrors `server/app/protocol.py`; change both together.
- **One socket per room, owned by `useRoomSession`.** It carries the lobby and
  then the arena; `Game` subscribes to it and never closes it. Anything that
  needs the socket takes it as a prop rather than opening a second one.
- Routes are `/` and `/r/:code`. The room URL is the invite link, so it must
  work whether the room is at the campfire or already in a level.
- **The lobby and the arena are two renders of one place.** `LobbyScreen` draws
  the map from `hello` with the server's own player coordinates; `ArenaScreen`
  draws the same map with the simulation running. Nothing may move at the
  transition.
- **The title screen and the lobby share one rest shot.** The fire sits on
  `campFireAnchor` in `src/render/framing.ts` on both; the title's fallback
  clearing is the same size as the real camp. Entering a room must not jump
  the fire.
- **The lobby owns the transition.** Its canvas is full screen with the chrome
  floating over it — same box as the arena's — and starting a run slides the
  chrome off while the scene's own camera drifts onto the local player and
  pushes in to game scale. `RoomScreen` swaps screens when that move LANDS, not
  when the `welcome` arrives, which is much earlier and would cut it in half.
  Then the arena holds the player still, facing the camera, with no HUD, while
  the day names itself.
- The player's name is client-side state (`lib/identity.ts`, `localStorage`) and
  travels to the server in the socket query string. There is no account, and no
  server-side persistence for it.
- Anything created — sockets, timers, listeners, observers, rAF — must be
  released in `Game.dispose()`. StrictMode and HMR both remount, and a leaked
  loop is silent until the frame rate collapses.
- `publicDir` is `../assets/processed`, so art is fetched from `/player/...`,
  `/backpack/...`, `/terrain/...`, `/scenery/...`. `assets/raw` is never served.
- The app is permanently `<html class="dark">`.
- Imports may use the `@` alias for `src/`.

## Work Guidance

```bash
cd client && bun install && bun run dev
```

- Dev talks to the page origin. Vite proxies `/rooms`, `/health` and `/ws` to
  `http://127.0.0.1:8000` (`ws: true` on `/ws`), so a phone on the LAN only
  needs the Network URL Vite prints.
- `VITE_SERVER_URL=http://host:8000 bun run dev` skips the proxy and hits that
  origin directly. It is an HTTP **origin**, not a socket URL — `endpoints.ts`
  derives both the REST calls and `ws://…/ws/{code}` from it.
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
