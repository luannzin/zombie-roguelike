# client/src/game/ — game core

## Purpose

Everything between the socket and the renderer: the loop, the predicted local
player, interpolated remotes, world state, transient effects, and the single
seam React is allowed to read.

## Ownership

| file | owns |
| --- | --- |
| `game.ts` | orchestrator: two clocks, render loop, `start()`/`dispose()` |
| `lobby-scene.ts` | the camp, drawn before the simulation is allowed to run |
| `simulation.ts` | movement — mirror of `server/app/simulation.py` |
| `prediction.ts` | apply-locally, replay-on-ack reconciliation |
| `interpolation.ts` | remote entity smoothing |
| `input.ts` | keyboard/mouse sampling into an `InputPacket` |
| `world.ts` | client tile map, collision + sight queries, fires, hearth mask |
| `combat.ts` | client-side shot feel and tracer bookkeeping |
| `effects.ts` | tracers, dust, floating text, event lights |
| `entity-visuals.ts` | per-player colour/name visual state |
| `lantern.ts` | four-cell battery, produces `output` 0..1 |
| `hud-store.ts` | the only seam to React; `HUD_INTERVAL` = 0.2 s |

## Local Contracts

- Two clocks: a fixed 30 Hz tick samples input, predicts and sends; `rAF`
  interpolates, smooths and renders. Do not move prediction into `rAF`.
- `simulation.ts` is the **only** place the local player may be moved, and it
  must stay a line-for-line mirror of the Python version.
- `hud-store.ts` is the only channel to the UI. Nothing here may touch the DOM
  beyond the two canvases `game.ts` owns.
- **`Game` does not own its socket.** The connection is created by
  `hooks/useRoomSession` and has been carrying the lobby since before the game
  existed; `Game` subscribes in `start()` and unsubscribes in `dispose()`, and
  must never close it. The `welcome` it was built from is replayed in `start()`
  because it arrived first.
- `lobby-scene.ts` is decoration only: no input, no prediction, no socket. It
  draws through the arena's own `TerrainLayer`, so the lobby and the game
  cannot drift apart.
- **The lobby draws the real camp.** `setCamp` takes the map from `hello` and
  `setMembers` takes the server's own coordinates; the scene never decides
  where anybody stands. It used to force the local player into the front seat,
  which meant every client saw a different party and everyone's characters
  jumped the instant the run started. The local player is marked by the ring
  under their feet instead. The one caller with no server — the title screen —
  falls back to a locally generated clearing, which only has to LOOK like the
  place because nobody is standing in it. Its map is the same size as the real
  camp (`CAMP_WIDTH_TILES` × `CAMP_HEIGHT_TILES`): a smaller one makes the
  camera clamp and pulls the fire off the rest anchor, so entering a room jumps
  it. The rest anchor itself is `campFireAnchor` in `render/framing.ts`, shared
  with the title screen.
- Positions arrive as the CENTRE of a collision box, the way a snapshot carries
  them; the scene converts to a contact point with `config.playerHalfHeight`.
  Getting that wrong is a party floating above their own shadows.
- **The lobby performs the transition, not the arena.** `beginLaunch` drifts the
  camera from the fire onto the local player, takes the anchor back to centre
  and pushes from `campZoom` to `ARENA_ZOOM`, all on one smootherstep — so the
  last frame this scene draws is pixel-for-pixel the first frame the arena
  draws, and `Camera` has no arrival code at all. The screen swap waits for the
  move to land (see `screens/RoomScreen`), never for the `welcome`.
- The lobby's canvas is FULL SCREEN with the chrome floating over it, for the
  same reason: the arena's canvas is the whole window, so a lobby canvas in a
  column beside a sidebar would shift the world sideways at the handover no
  matter how well the camera matched.
- The lobby runs the arena's `FovField` and `DarknessLayer` over the same
  bonfire light, in the arena's pass order. Nothing here may draw its own
  version of the night — the camp has to be lit identically before and after
  the run starts, and it is, by being lit by the same code.
- The **hearth** is the fire plus the seat ring, and nothing decorative stands
  in it: the map generator refuses trees and rocks there, and a `TerrainLayer`
  decoration mask (`world.hearthMask`) refuses grass and ferns. Both measure on
  the same ellipse the seats use. A plant in front of a player hides the
  character the roster is pointing at. The arena sets the same mask, because
  `preparation` is that same ground.
- A **bonfire is a tile** (`FIRE`), and everything reads it off the map:
  collision, the animated sprite, and the light. It blocks bodies but not sight
  (`blocksSight`) — left as an occluder it would shadow the half of the party
  sitting behind it, which is the one place in the camp that must be lit.
- VOID is a gap in the treeline, not a missing floor: solid, painted as ground,
  crushed by darkness. `blocksSight` lets light fall into it so the trees do
  not close into a wall; the darkness pass then kills the warmth so leaked
  firelight never turns the mouth into a hallway.
- **The summon sheet is the clock.** `SUMMON_TIME` is the sheet's
  `frames / fps` and `SUMMON_IMPACT` mirrors `IMPACT_AT` in
  `server/tools/make_vfx.py`; the body must finish resolving on the frame the
  sprite flashes, or the arrival lands twice. The sheet owns the flash and the
  shockwaves — the code only adds what it cannot know, which is whose arrival
  it is: the sheet is greyscale and tinted with the arriving player's colour,
  plus one ring and a spray of sparks in the same colour.
- Lobby names are drawn in SCREEN space, on a card ABOVE the head. Above,
  because the seat ring is elliptical and a label under a player's feet lands
  on whoever is sitting closer to the camera. The card is the roster row in
  pixels — inset fill, hairline border, 2px colour bar — and every measurement
  is a whole multiple of one design pixel so it stays on the font's grid.
- `dispose()` releases every timer, listener, observer and rAF handle created in
  this folder.
- Tuning comes from `welcome.config`; the lantern's drain/recharge constants
  are the exception, because the battery is client-local. The switch is not:
  `on` is on the input packet and every player snapshot so remotes go dark.
- `lantern.output` is the local lamp the lighting system reads — fov beam gain
  and reach, hearth warmth, and the HUD cells. Remotes contribute 0 or 1
  from their snapshot `lantern` flag.
- `lantern.allowed` comes from `welcome.zone.lantern` and is a property of the
  LAMP, not a check at the call site, so every route to switching on goes
  through one refusal. A refused press is COUNTED, not ignored: the HUD reads
  at 5 Hz and has to be able to answer each keypress, because a control that
  silently does nothing reads as a broken keybind rather than as a rule.
- The zone also masks `shoot` on the outgoing packet. The server drops it too,
  and the mask has to be on the packet or prediction draws a tracer that was
  never fired.
- Entering a zone HOLDS the player for `INTRO_TIME`: movement and aim are
  masked on the outgoing packet (not at the input layer, or prediction would
  move them locally and yank them back), the character faces the camera, and
  the HUD keeps its corners off the glass. What is on screen for that beat is
  the place, one character standing in it, and the day's name — then the
  controls and the chrome return together.
- The camp walk-out (`snapshot.departing`) is the same mask plus no local
  prediction: the server puppets every body, and the local player is
  interpolated with the remotes so they cannot fight the march. Camera follows
  the party, looking ahead at the VOID mouth. E at the fire sends
  `{type:"ready"}`; the server is what decides whether it counted.
- Entering a zone is announced ONCE, through `hud-store.arrival`, keyed by the
  zone key; `introducing` says whether the hold is still running. INTRO_TIME,
  `CARD_MS` in `hud/ZoneTitle` and the `zone-*` keyframes are one timeline. The
  card must clear BEFORE the hold ends, or the HUD rises under the title.

## Work Guidance

- New per-frame state stays here or in `render/`; it must not reach React.
- New HUD data means a field on the `hud-store` snapshot, published at 5 Hz —
  not a subscription from a component to the game. Camp ready uses `ready` and
  `prompt`; the walk-out uses `cinematic`.
- Anything long-lived created here gets a matching release in `Game.dispose()`
  in the same change.

## Verification

- `bun run typecheck` from `client/`.
- Rubber-banding on the local player means `simulation.ts` has drifted from the
  server; compare the two files directly.
