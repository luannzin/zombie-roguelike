# client/src/components/ — React components

## Purpose

The DOM half of the client: canvas hosts and the HUD overlay. React lives here
and nowhere near the frame loop.

## Ownership

- `game/` — `GameCanvas`, `MinimapCanvas`. Mount a canvas and hand the ref to
  `Game`; React never touches those pixels again.
- `hud/` — ours: `Hud`, `HudScreen`, `Panel`, `Vitals`, `BatteryGauge`,
  `ProgressBar`, `StatusLine`, `NetStats`, `ControlsHint`, `ZoneTitle`,
  `ReadyCount`, `QuestLog`, `QuestRow`, `QuestAnnounce`, `InteractPrompt`, `LootPrompt`, `CratePrompt`, `Inventory`, `InventorySlot`,
  `InventoryGold`, `WeightBar`, `LootIcon`, `CoinIcon`, `SlotValue`, `LootFly`, `LootCard`,
  `LootCardRow`, `TooltipCard`, `InventoryGhost`, `Tooltip`, `TooltipKey`,
  `Hotbar`, `HotbarSlot`.
- `lobby/` — `CampfireCanvas` (mounts `LobbyScene`; owns the rest-shot fire
  position via `campFireAnchor`, not via per-screen props), `RoomCode`,
  `PlayerRoster`.
- `menu/` — `MenuButton`, `HudInput`, `HudSlider`, `JoinRoomDialog`,
  `AudioOptions`: the title screen's controls, in HUD chrome.
- `ui/` — coss primitives (Base UI + shadcn-style copy-in). **Generated. Do not
  hand-edit.**

## Local Contracts

- HUD state is read from `hud-store` through `useHud`, republished at 5 Hz.
  Never subscribe a component to per-frame game state.
- Every HUD layer is `pointer-events: none` (the `hud-layer` utility) so the
  canvas keeps receiving aim and fire input underneath. The bag is the
  exception: `Inventory` sets `pointer-events: auto` on itself so hover
  and drag work, and nothing else on that corner may.
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
  nearby drop; `CratePrompt` is smash ("E para destruir"). A full bag keeps the pin and says "Inventário Cheio" in
  the danger tone — hiding it would look like the drop vanished. New
  items get a new caller, not a fork of the chrome.
  `LootPrompt` has THREE states, and the middle one is why `full` is not
  enough on its own: a full BELT with a gun in hand is a trade, so the copy
  becomes "trocar {held} por {new}" with the gun being given up in the muted
  tone and the one being gained in its rarity colour — the direction of the
  trade reads before either name does. What you would pick up is on the
  ground in front of you; what you would put down is in your hands where you
  cannot see it, which is the whole reason it has to be named.
- `Inventory` is the left-side pocket. Collapsed it is the backpack sprite
  and a TAB hint; TAB expands the slots in place, not a dialog. A collect
  opens it so the slot is on screen before the fly leaves the head. Slot
  centres are written to `inventory-anchors` from layout. `LootFly` sits
  outside the glass — hold, then travel — pose is rAF, membership is
  `loot-flies`. A fly targeting a cell keeps that cell empty (no rarity
  border, no value, no weight on the bar) until it lands. Slot anchors
  are written every frame while the drawer is open, and travel waits
  until the cell is on screen so the sprite cannot aim at a collapsed
  row. Hovering a filled cell is a pointer and opens `LootCard`
  (`TooltipCard` chrome: same fill, bar, staircase arrow). The card
  measures and flips or shifts so a left-edge slot cannot push it off
  the screen; the arrow slides with it. Name and rarity both take the
  rarity colour. Slot value is the small HUD coin (`/hud/coin.png`)
  plus the number. Dragging a cell off the panel tosses it;
  `InventoryGhost` follows the cursor.
  The open bag shows the sum of item values (`InventoryGold`) and
  weight as `0.2 / 10kg`. The hover card's PESO is the same unit.
  A fly in the air is not in that gold total yet, same as the bar.
  Both the card and the ghost portal to `document.body` so the glass
  does not warp them off the pointer. The card's `fixed` layer is a
  wrapper — `.world-tooltip` is `position: relative` and cannot be the
  positioned node. Drop goes through
  `inventory-actions`, never a socket from React.
- `Hotbar` is two gun cells and then the knife, above the battery. Always
  visible, pointer-events none — 1/2/3 is sampled in `game/input.ts`, not
  by the DOM. Same chrome fade as the corners. A gun fly uses dest `hotbar`
  and writes `hotbar-N` anchors the way bag slots write `slot-N`. The
  selected cell rings and replays `animate-hotbar-pick`. Weapons do not show
  a coin value. The knife's cell is separated by a hairline and gets no
  label: it is always full and always last, which explains itself the second
  time somebody presses 3 — a caption on a permanent cell is chrome that is
  read once. The hairline earns its keep on the first screen of a run, where
  the two gun cells are empty and it is the difference between "you have
  nothing" and "you have this".
- A control a zone forbids is shown DISABLED, never hidden. `BatteryGauge` in
  the camp still answers "how much light am I carrying into the night"; only
  its readout changes, and a refused keypress kicks the panel instead of doing
  nothing. `ControlsHint` lists what works here for the same reason — offering
  a key that will not answer is worse than not mentioning it.
- `ReadyCount` is camp-only HUD, fed from `hud-store` (`ready`). It rides the
  same chrome fade as the corners, so the walk-out (`cinematic`) takes it off
  with everything else. The ready prompt is a `Tooltip`, not a corner.
- `QuestLog` is a Panel under the minimap, same chrome as the belt and the
  bag. New tasks do not just appear in the list: `QuestAnnounce` puts the
  label big at centre (22px, the HUD's 2×), holds so it can be read, then
  FLIPs into the card. Completed rows rise, then leave — the HUD dismisses
  them after that beat even if the server still carries `done`. `risk` still
  paints the count in the danger tone. Reduced motion fades only; no dock.
- Colours and type come from the tokens in `src/styles/index.css`, consumed as
  Tailwind utilities. No literal colours in components.
- coss semantic tokens are re-pointed at the game palette in the coss skin block
  at the bottom of `index.css`; do not add per-component overrides.
- **The menu and the lobby chrome are SILENT.** No hover tick, no click. Both
  were built and cut: hover chattered at buttons the pointer was only crossing,
  and the click marked a decision the screen was already announcing — over a
  title screen whose backdrop is a crackling bonfire, it read as a synthetic
  noise laid on top of the one thing selling the place. Audio still unlocks on
  the first press, because that listener is `audio/engine.ts`'s and has nothing
  to do with any button. The UI sounds that remain belong to the GAME, not to
  the chrome: a refusal (`ui-error`, from `Game`) and the bag opening.
  `ControlsHint` always lists `M som`, unlike the rest of that line, because
  mute is the one control that works everywhere and there is no settings screen
  yet.
- **Opções is a stage of `HomeScreen`, not a route.** Same reason `play` is:
  there is nothing to link to and nothing to come back to. `AudioOptions` reads
  the audio engine through `useSyncExternalStore` — the same shape as `useHud`,
  since the mix lives in a Web Audio graph React does not own — and every change
  applies live and ramped, so there is no apply button. `HudSlider` is a native
  `<input type="range">` skinned by `.hud-range`: the platform supplies drag,
  keyboard stepping, touch and ARIA, and we supply every pixel. The coss
  `Slider` is not used, for the reason below.
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
