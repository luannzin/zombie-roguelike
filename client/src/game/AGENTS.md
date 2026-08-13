# client/src/game/ — game core

## Purpose

Everything between the socket and the renderer: the loop, the predicted local
player, interpolated remotes, world state, transient effects, and the single
seam React is allowed to read.

## Ownership

| file | owns |
| --- | --- |
| `game.ts` | orchestrator: two clocks, render loop, `start()`/`dispose()` |
| `lobby-scene.ts` | the campfire clearing drawn before the run starts |
| `simulation.ts` | movement — mirror of `server/app/simulation.py` |
| `prediction.ts` | apply-locally, replay-on-ack reconciliation |
| `interpolation.ts` | remote entity smoothing |
| `input.ts` | keyboard/mouse sampling into an `InputPacket` |
| `world.ts` | client tile map + collision queries |
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
  draws through the arena's own `TerrainLayer` over a locally generated
  `TileMap`, so the lobby and the forest cannot drift apart. Art scale comes
  from the terrain manifest, never a hardcoded tile size.
- The **hearth** (`HEARTH_TILES`) is the fire plus the seat ring, and nothing
  decorative stands in it: the map generator refuses trees and rocks there, and
  a `TerrainLayer` decoration mask refuses grass and ferns. Both measure on the
  same ellipse the seats use. A plant in front of a seated player hides the
  character the roster is pointing at.
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

## Work Guidance

- New per-frame state stays here or in `render/`; it must not reach React.
- New HUD data means a field on the `hud-store` snapshot, published at 5 Hz —
  not a subscription from a component to the game.
- Anything long-lived created here gets a matching release in `Game.dispose()`
  in the same change.

## Verification

- `bun run typecheck` from `client/`.
- Rubber-banding on the local player means `simulation.ts` has drifted from the
  server; compare the two files directly.
