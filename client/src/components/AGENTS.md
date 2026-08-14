# client/src/components/ — React components

## Purpose

The DOM half of the client: canvas hosts and the HUD overlay. React lives here
and nowhere near the frame loop.

## Ownership

- `game/` — `GameCanvas`, `MinimapCanvas`. Mount a canvas and hand the ref to
  `Game`; React never touches those pixels again.
- `hud/` — ours: `Hud`, `HudScreen`, `Panel`, `Vitals`, `BatteryGauge`,
  `ProgressBar`, `StatusLine`, `NetStats`, `ControlsHint`, `ZoneTitle`.
- `lobby/` — `CampfireCanvas` (mounts `LobbyScene`), `RoomCode`, `PlayerRoster`.
- `menu/` — `MenuButton`, `HudInput`, `JoinRoomDialog`: the title screen's
  controls, in HUD chrome.
- `ui/` — coss primitives (Base UI + shadcn-style copy-in). **Generated. Do not
  hand-edit.**

## Local Contracts

- HUD state is read from `hud-store` through `useHud`, republished at 5 Hz.
  Never subscribe a component to per-frame game state.
- Every HUD layer is `pointer-events: none` (the `hud-layer` utility) so the
  canvas keeps receiving aim and fire input underneath.
- All four corners live inside `HudScreen`, which curves and tears the overlay.
  A panel placed outside that wrapper visibly floats off the glass.
- `ZoneTitle` is the one thing allowed to own the whole screen, and only for a
  moment. It plays into a deliberately EMPTY frame: `Hud` drops its four
  corners to zero opacity while `snapshot.introducing` is set, and the game is
  holding the player still at the same time. The durations in the component,
  the `zone-*` keyframes and INTRO_TIME in `game/game.ts` are one timeline —
  the card has to clear before the corners come back.
- A control a zone forbids is shown DISABLED, never hidden. `BatteryGauge` in
  the camp still answers "how much light am I carrying into the night"; only
  its readout changes, and a refused keypress kicks the panel instead of doing
  nothing. `ControlsHint` lists what works here for the same reason — offering
  a key that will not answer is worse than not mentioning it.
- Colours and type come from the tokens in `src/styles/index.css`, consumed as
  Tailwind utilities. No literal colours in components.
- coss semantic tokens are re-pointed at the game palette in the coss skin block
  at the bottom of `index.css`; do not add per-component overrides.
- `menu/` reimplements the button and the text field rather than restyling the
  coss ones: every visual decision in those primitives (radius, shadow, ring,
  sans face) is the opposite of the HUD's, and overriding them all at the call
  site costs more than the component. Structural primitives with real behaviour
  — `Dialog`'s portal, focus trap and escape handling — are still reused.

## Work Guidance

- Add a coss primitive with `bunx --bun shadcn@latest add @coss/<name>`; if one
  needs project behaviour, wrap it in `hud/` instead of editing `ui/`.
- New HUD readouts go inside `HudScreen` and take their data from a field on the
  HUD snapshot.

## Verification

- `bun run typecheck` from `client/`.
- Confirm in the browser that aiming and firing still work with the cursor over
  the new element.
