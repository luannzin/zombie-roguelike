# client/src/game/ — game core

## Purpose

Everything between the socket and the renderer: the loop, the predicted local
player, interpolated remotes, world state, transient effects, and the single
seam React is allowed to read.

## Ownership

| file | owns |
| --- | --- |
| `game.ts` | orchestrator: connection, two clocks, render loop, `start()`/`dispose()` |
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
- `dispose()` releases every socket, timer, listener, observer and rAF handle
  created in this folder.
- Tuning comes from `welcome.config`; the lantern's own constants are the
  exception, because the battery is client-local and the server does not know
  the lamp exists.
- `lantern.output` is the single value the lighting system reads — fov beam gain
  and reach, hearth warmth, and the HUD cells.

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
