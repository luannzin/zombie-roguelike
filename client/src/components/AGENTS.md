# client/src/components/ — React components

## Purpose

The DOM half of the client: canvas hosts and the HUD overlay. React lives here
and nowhere near the frame loop.

## Ownership

- `game/` — `GameCanvas`, `MinimapCanvas`. Mount a canvas and hand the ref to
  `Game`; React never touches those pixels again.
- `hud/` — ours: `Hud`, `HudScreen`, `Panel`, `Vitals`, `BatteryGauge`,
  `ProgressBar`, `StatusLine`, `NetStats`, `ControlsHint`, `ZoneTitle`, `Announce`,
  `ReadyCount`, `Balance`, `QuestLog`, `QuestRow`, `QuestAnnounce`, `QuestCount`, `InteractPrompt`, `LootPrompt`, `CratePrompt`, `RiftPrompt`, `BuyPrompt`, `MachinePrompt`, `ExitGuide`, `SkillTray`, `SkillIcon`, `SkillCanIcon`, `Inventory`, `InventorySlot`,
  `InventoryGold`, `WeightBar`, `LootIcon`, `CoinIcon`, `DarkCoinIcon`, `SlotValue`, `LootFly`, `LootCard`,
  `LootCardRow`, `TooltipCard`, `InventoryGhost`, `Tooltip`, `TooltipKey`,
  `Hotbar`, `HotbarSlot`.
- `lobby/` — `CampfireCanvas` (mounts `LobbyScene`; owns the rest-shot fire
  position via `campFireAnchor`, not via per-screen props), `RoomCode`,
  `PlayerRoster`.
- `menu/` — `MenuButton`, `HudInput`, `HudSlider`, `JoinRoomDialog`,
  `AudioOptions`: the title screen's controls, in HUD chrome.
- `ui/` — coss primitives (Base UI + shadcn-style copy-in). **Generated. Do not
  hand-edit.**

## Route

A HUD element is the **face** of a subsystem, never its owner. What it shows is
decided in `client/src/game/` and, above that, on the server. If the task is
about what the panel *means* rather than how it looks, follow the element to
its subsystem's design law in [`docs/design/`](../../../docs/design/) —
`RiftPrompt`/`ExitGuide` -> `extraction.md`, `BuyPrompt`/`Balance` ->
`store.md`, `SkillTray`/`MachinePrompt` -> `skills.md`,
`Inventory`/`Hotbar`/`WeightBar` -> `player.md`. The seam between them is
`client/src/game/hud-store.ts` (see
[`../game/AGENTS.md`](../game/AGENTS.md)).

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
- `Announce` is `ZoneTitle` one size down, for news that arrives MID-RUN.
  Same language — rules out from the centre, type into focus, a second line a
  beat later, reusing the `zone-*` keyframes at a shorter
  `animation-duration`, which is what those percentage keyframes are written
  for. Everything that differs is about the frame it lands in: an arrival owns
  an empty screen, this one lands over live gameplay. 24px not 44px, one rule
  not two, upper third not the middle (the middle is the player's own body and
  where they are aiming), `ANNOUNCE_MS` not three seconds, and no slash — that
  bar is the arrival card's one beat and firing it at every event would spend
  it. It does NOT dim the corners: `introducing` is the arrival's flag and
  nothing here holds the player still.
  It is a one-shot keyed on `announce.key`, so the key is the EVENT
  (`level-7`) and never the kind of event — the store keeps the last one
  forever and a repeated key announces once. First caller is the level-up
  ("Subiu de Nível" / "+1 ponto de habilidade"); the world half of that beat
  is a summon column on the body, in `render/layers/effects.ts`, because a
  banner alone leaves the other three players wondering whose level it was.
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
  glass burst. The card is `whitespace-nowrap`: it is `position: fixed` with
  no width, so its containing block is the viewport and a tooltip pinned near
  the screen edge was wrapping mid-sentence into a two-line card that jumped
  as the player walked. These are one-line prompts — overflowing the edge is
  the better failure, and a caller whose copy does not fit should shorten it
  or move a part into `start` / `end`, which are `shrink-0`. `InteractPrompt` is ready at the fire; `LootPrompt` is a
  nearby drop; `CratePrompt` names the object's OWN verb, which arrives on the
  HUD snapshot as a string ("destruir" / "abrir" / "vasculhar") — there is no
  verb constant in the component, because adding an object is a row in
  `server/app/crates.py`; `RiftPrompt` is
  a pad, and it has FOUR things to say because the one key has four different
  jobs: "ligar a plataforma" while dormant, "outra plataforma está ligada"
  while another pad is awake, "carregar a plataforma" with anything in the
  pocket, and "chamar a extração · o barulho atrai tudo" once the pocket is
  empty. IT USED TO HAVE FIVE — a separate "sobrecarregar a plataforma" past
  the quota — and that line died with the rule under it: a pour takes the whole
  bag on either side of the bill, so there is no second verb to name. Two
  prompts for one action is two things for the player to learn about a
  distinction the machine no longer makes. THAT LAST ONE IS THE DANGER TONE: it
  is the most expensive press in the game and the line has to say so before it
  happens. All but the first two carry the coin badge and the pad's own
  `have/need` — which is allowed to read past `need`, because the overshoot is
  the size of the core coming out the far end.
  Empty-bag refusal at a hungry pad is in the danger tone.
  A full bag keeps the pin and says "Inventário Cheio" in
  the danger tone — hiding it would look like the drop vanished. New
  items get a new caller, not a fork of the chrome.
  `ExitGuide` is the gold TRIANGLE for the way out (`/hud/chevron.png`, not
  `arrow.png`): outside the glass, halfway between the player and the screen
  edge in the corridor's direction, positioned by `stepExitGuide` in its own
  rAF. The transform is sub-pixel `translate3d` on purpose — rounding it undoes
  the smoothing that module exists for.
  `LootPrompt` has THREE states, and the middle one is why `full` is not
  enough on its own: a full BELT with a gun in hand is a trade, so the copy
  becomes "trocar {held} por {new}" with the gun being given up in the muted
  tone and the one being gained in its rarity colour — the direction of the
  trade reads before either name does. What you would pick up is on the
  ground in front of you; what you would put down is in your hands where you
  cannot see it, which is the whole reason it has to be named.
  `BuyPrompt` is a shop table. The PRICE rides in the tooltip's `end` slot
  rather than in the sentence, which is what keeps the card to one line
  whatever the weapon is called. Three states in the copy: an ordinary
  purchase, a trade when the belt is full with a gun in hand — which matters
  more here than on a drop, because the gun being given up is being exchanged
  for one that COSTS MONEY and a player who misses that line pays twice — and
  a refusal when no trade is legal. AFFORDABILITY IS ONLY A COLOUR: an
  unaffordable price turns red and says nothing else, because the number and
  the empty purse are already the message and spelling it out made the card
  long enough to wrap. The stall is still offered rather than hidden — a shop
  that only shows what you can already afford has no aspirational shelf, and
  the AWP priced out of reach is doing more work than a tutorial line about
  saving up.
- **TWO CURRENCIES, TWO BADGES, AND THE BADGE IS HOW THE PLAYER TELLS THEM
  APART.** `CoinIcon` (`/hud/coin.png`, gold) is the GROUP's, and it goes
  everywhere the group's money is quoted: `Balance`, `SlotValue`,
  `InventoryGold`, the gold `QuestCount` rows, the store's prices.
  `DarkCoinIcon` (`/hud/darkcoin.png`) is the PLAYER's dark gold and appears in
  exactly one place — the `GOLD` row of `Vitals`. It is an ANOMALY SHARD: a
  sphere in the rift's own prism, and frame 0 of the same painter that turns
  the pickup in the world, so the badge cannot drift from the thing on the
  floor. The two icons used to share a disc silhouette on the argument that at
  8px the metal is the whole message; that ended when one of them stopped
  being metal. A ball against a struck disc is now the fastest way to read
  which currency a number is. Do not put the gold coin on a personal number or
  the shard on a party number.
- `Balance` is the party's purse and it is drawn ONLY in the store, sharing
  the top-centre slot with `ReadyCount` (same kind of statement about the
  party; the two zones never overlap). It exists from the moment the party
  leaves the forest, but nothing in a run can spend it — a permanent gold
  counter would sit in the corner of every expedition talking about money the
  player cannot use, competing with the bag, which is the number that actually
  changes while they play. `Vitals.gold` is the other one and stays up the
  whole run, because it is the currency the player is actually collecting out
  there: purple coins they walked over, one at a time.
- `SkillTray` sits ABOVE the bag, in the same column, and that is the whole
  placement argument: a skill and a pocket are the same kind of statement —
  *this is what I am carrying* — one you can still lose tonight and one you
  keep, and stacking them is what stops the HUD growing a fifth region.
  It is a LIST OF LABELLED ROWS, not a grid of tiles: icon, NAME in the
  rarity colour, and `x{qty}`, one row per skill, stacked with no gap so they
  read as one shelf that grew. A wall of 16px icons asked the player to hover
  eighteen things to find out what they owned, which is a spreadsheet with the
  words hidden; the hover card is now only the sentence about what the skill
  DOES. A row at its cap is muted, because a number that silently stopped
  meaning anything is worse than no number.
  It is NEVER EMPTY — with no skills it says `habilidades: nenhuma` in one
  muted row. A region that appeared for the first time at the first shop is a
  region the player has to learn mid-run, and the empty row is also the only
  place the HUD admits the system exists before it has paid out.
  There is NO spins badge. It said the same thing five times a second for a
  whole night, and the cabinet's own marquee already burns harder for a player
  holding an unspent level — teaching at a distance, in the world, which is
  the one thing a HUD line could never do.
- `MachinePrompt` answers even when the player has NOTHING to spend, which is
  why it has three states rather than one. A machine that only spoke to
  somebody already holding a level would be scenery for the whole first shop —
  and the connection between killing zombies in the woods and the lever in the
  glade would never get made. The empty copy states the CURRENCY ("suba de
  nível para girar") rather than the refusal, because where a spin comes from
  is the one thing a player standing at the cabinet does not know yet.
- **`ExitGuide` BLINKS, and the blink is on the render clock.** `hud-store`
  carries ONE BIT — there is an uncrossed way out — and the component owns the
  envelope: a long solid burst while the news is news, then it goes dark, then
  it comes back for a couple of seconds every few, forever. A permanent marker
  answers "which way out" for the rest of the night, so the column of light
  over the treeline, the torches at the threshold and the ping from the mouth
  become decoration nobody has a reason to read; a marker that simply faded out
  left a party that turned the wrong way at second twelve with nothing to ask.
  The ramps at each end of a pulse are shorter than the store's 200 ms
  republish, which is why the envelope cannot live in the snapshot — pushed
  through it, a fade arrives as two steps and a pop.
  The sprite is a TRIANGLE for the same reason: what the eye catches in a
  half-second flash is AREA, not line, and the old dart is a thin thing that
  reads by its length. It still sits outside `HudScreen`: the glass would bend
  it off the screen edge.
- `Inventory` is the left-side pocket. Collapsed it is the backpack sprite
  and a TAB hint; TAB expands the slots in place, not a dialog. A collect
  opens it so the slot is on screen before the fly leaves the head. Slot
  centres are written to `inventory-anchors` from layout. `LootFly` sits
  outside the glass — hold, then travel — pose is rAF, membership is
  `loot-flies`. A fly targeting a cell keeps that cell empty (no rarity
  border, no value, no weight on the bar) until it lands. Slot anchors
  are written every frame while the drawer is open, and travel waits
  until the cell is on screen so the sprite cannot aim at a collapsed
  row. `SkillTray` publishes its own box on the SAME anchor map
  (`SKILL_TRAY_ANCHOR`), unconditionally, because the machine's payout
  is a fly too: one anchor for the whole shelf rather than one per row,
  since on a first copy the row is what the landing creates. That fly
  draws `SkillCanIcon` instead of `LootIcon` — the tin body picked by
  rarity with the skill's own icon scaled into its label window, all
  three numbers read off the skill manifest so the art can be redrawn
  at another size without a component changing. Hovering a filled cell is a pointer and opens `LootCard`
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
  bag, right-aligned with the map (`items-end`). New tasks do not just
  appear in the list: `QuestAnnounce` puts the label at top-centre
  (11px, same face as the card, `whitespace-nowrap` so a long name stays
  one line), holds so it can be read, then flies into the card
  the same way a collect flies into the bag (rAF pose, `warpHudPoint`,
  outside the glass). Completed rows rise, then leave — the HUD dismisses
  them after that beat even if the server still carries `done`. `risk`
  still paints the count in the danger tone. Reduced motion fades only;
  no dock.
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
