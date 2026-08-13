# client/src/components/ — React components

## Purpose

The DOM half of the client: canvas hosts and the HUD overlay. React lives here
and nowhere near the frame loop.

## Ownership

- `game/` — `GameCanvas`, `MinimapCanvas`. Mount a canvas and hand the ref to
  `Game`; React never touches those pixels again.
- `hud/` — ours: `Hud`, `HudScreen`, `Panel`, `Vitals`, `BatteryGauge`,
  `ProgressBar`, `StatusLine`, `NetStats`, `ControlsHint`.
- `ui/` — coss primitives (Base UI + shadcn-style copy-in). **Generated. Do not
  hand-edit.**

## Local Contracts

- HUD state is read from `hud-store` through `useHud`, republished at 5 Hz.
  Never subscribe a component to per-frame game state.
- Every HUD layer is `pointer-events: none` (the `hud-layer` utility) so the
  canvas keeps receiving aim and fire input underneath.
- All four corners live inside `HudScreen`, which curves and tears the overlay.
  A panel placed outside that wrapper visibly floats off the glass.
- Colours and type come from the tokens in `src/styles/index.css`, consumed as
  Tailwind utilities. No literal colours in components.
- coss semantic tokens are re-pointed at the game palette in the coss skin block
  at the bottom of `index.css`; do not add per-component overrides.

## Work Guidance

- Add a coss primitive with `bunx --bun shadcn@latest add @coss/<name>`; if one
  needs project behaviour, wrap it in `hud/` instead of editing `ui/`.
- New HUD readouts go inside `HudScreen` and take their data from a field on the
  HUD snapshot.

## Verification

- `bun run typecheck` from `client/`.
- Confirm in the browser that aiming and firing still work with the cursor over
  the new element.
