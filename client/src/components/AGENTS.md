# client/src/components/ — React components

## Purpose

The DOM half of the client: canvas hosts and the HUD overlay. React lives here
and nowhere near the frame loop.

## Ownership

- `game/` — `GameCanvas`, `MinimapCanvas`. Mount a canvas and hand the ref to
  `Game`; React never touches those pixels again.
- `hud/` — ours: `Hud`, `HudScreen`, `Panel`, `Vitals`, `BatteryGauge`,
  `ProgressBar`, `StatusLine`, `NetStats`, `ControlsHint`, `ZoneTitle`,
  `ReadyCount`, `InteractPrompt`, `LootPrompt`, `Inventory`, `InventorySlot`,
  `WeightBar`, `LootIcon`, `LootFly`, `Tooltip`, `TooltipKey`.
- `lobby/` — `CampfireCanvas` (mounts `LobbyScene`; owns the rest-shot fire
  position via `campFireAnchor`, not via per-screen props), `RoomCode`,
  `PlayerRoster`.
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
  A HUD panel placed outside that wrapper visibly floats off the glass. World
  `Tooltip`s are the exception — they belong to the scene, not the glass.
- `ZoneTitle` is the one thing allowed to own the whole screen, and only for a
  moment. It plays into a deliberately EMPTY frame: `Hud` drops its four
  corners to zero opacity while `snapshot.introducing` is set, and the game is
  holding the player still at the same time. `ZONE_INTRO_MS`, the `zone-*`
  keyframes (including the slash that crosses the title after it focuses) and
  INTRO_TIME in `game/game.ts` are one timeline — the card has to clear before
  the corners come back. The slash is a CSS keyframe on mount, not per-frame
  state; reduced motion drops it.
- **Anything that must exist on the arena's FIRST painted frame is driven by
  `introducing`, not by `arrival`.** The store's initial snapshot has
  `introducing: true`, so those elements are up before the game has said
  anything; `arrival` only lands once `onWelcome` has run, which is several
  frames later. That gap is a flash of undimmed scene at the exact seam the
  transition exists to hide. It is why the HUD corners and the `zone-bars`
  letterbox both key off the flag, and why the letterbox lives in `Hud` rather
  than in `ZoneTitle`.
- The `zone-bars` letterbox is ONE element across two screens: `LobbyScreen`
  fades it in under the camera push, the arena opens holding it at full. One
  utility, one gradient — two that were merely similar would show themselves.
  In the arena it is a sibling of `HudScreen`, not a child: the glass filter
  would bend the soft edge and the bars would jump taller on the handover.
  The walk-out reuses it (`cinematic`) so leaving the camp is the same frame
  closing that arriving was.
- `Tooltip` is the reusable world prompt (copy + optional `TooltipKey`). It
  sits OUTSIDE `HudScreen`: the glass would pull it off the thing it is
  pinned to. Show/hide comes from `hud-store` at 5 Hz; the screen position
  is an `anchor` id the game loop writes every frame (`tooltip-anchors`).
  Do not `setState` from that rAF — it is a transform, same idea as the
  glass burst. `InteractPrompt` is ready at the fire; `LootPrompt` is a
  nearby drop. New items get a new caller, not a fork of the chrome.
- `Inventory` is the left-side pocket. Collapsed it is the backpack sprite
  and a TAB hint; TAB expands the slots in place, not a dialog. Slot
  centres are written to `inventory-anchors` from layout. `LootFly` sits
  outside the glass and flies a sprite from the head onto a cell — pose
  is rAF, membership is `loot-flies`.
- A control a zone forbids is shown DISABLED, never hidden. `BatteryGauge` in
  the camp still answers "how much light am I carrying into the night"; only
  its readout changes, and a refused keypress kicks the panel instead of doing
  nothing. `ControlsHint` lists what works here for the same reason — offering
  a key that will not answer is worse than not mentioning it.
- `ReadyCount` is camp-only HUD, fed from `hud-store` (`ready`). It rides the
  same chrome fade as the corners, so the walk-out (`cinematic`) takes it off
  with everything else. The ready prompt is a `Tooltip`, not a corner.
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
  HUD snapshot. World `Tooltip`s are the exception: they sit outside the glass
  and take an `anchor` the game loop writes.

## Verification

- `bun run typecheck` from `client/`.
- Confirm in the browser that aiming and firing still work with the cursor over
  the new element.
