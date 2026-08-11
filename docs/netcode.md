# Netcode

## Loop

Server: fixed tick, `TICK_RATE = 30` (`server/app/config.py`). Each tick it
consumes queued input, simulates, and broadcasts a snapshot.

Client: a fixed 30 Hz tick inside `requestAnimationFrame` samples input,
predicts locally, and sends the packet. Rendering runs at display rate.

## Messages

### client → server

```json
{
  "type": "input",
  "sequence": 183,
  "movement": { "up": true, "down": false, "left": false, "right": true },
  "aim": { "x": 0.72, "y": -0.69 },
  "shoot": true
}
```

`{"type":"ping","t":<client ms>}` → `{"type":"pong","t":<echo>}` for RTT.

### server → client

`welcome` (once, on join):

```json
{
  "type": "welcome",
  "playerId": "a1b2c3d4",
  "player": { "id": "...", "name": "Player483", "color": "#4d9de0", "x": 200, "y": 168, "...": "..." },
  "config": { "tickRate": 30, "dt": 0.0333, "moveSpeed": 70, "playerRadius": 5, "...": "..." },
  "map": { "width": 64, "height": 40, "tileSize": 16, "tiles": [[1, 1, 0, "..."]] }
}
```

`snapshot` (every tick):

```json
{
  "type": "snapshot",
  "tick": 4021,
  "ack": 183,
  "players": [{ "id": "...", "x": 0, "y": 0, "vx": 0, "vy": 0, "ax": 1, "ay": 0, "hp": 100, "alive": true }],
  "shots": [{ "id": 7, "by": "a1b2c3d4", "x": 0, "y": 0, "dx": 1, "dy": 0, "dist": 132.5, "hit": "b5c6" }],
  "kills": [{ "killer": "a1b2c3d4", "victim": "b5c6", "x": 0, "y": 0 }]
}
```

`ack` is per-recipient: the last input sequence the server processed for *that*
client.

## Local player: prediction + reconciliation

1. Each client tick builds an `InputPacket` with a monotonic `sequence`.
2. `LocalPlayer.predict` applies it immediately and pushes it onto `pending`.
3. On each snapshot, `LocalPlayer.reconcile`:
   * overwrites local state with the authoritative state,
   * drops every pending input with `sequence <= ack`,
   * replays the remaining inputs through the same `applyInput` the server runs.
4. The positional difference between the pre- and post-reconciliation position
   is accumulated into a decaying visual error (`ERROR_DECAY`), so corrections
   are smoothed instead of snapping. A correction larger than
   `SNAP_THRESHOLD` (respawn, teleport) snaps instead.

This is why `simulation.py` and `simulation.ts` must stay identical, down to the
wall-snapping arithmetic in `world.py` / `world.ts`.

## Remote players: interpolation

`SnapshotBuffer` keeps ~1.5 s of snapshots stamped with local receive time and
renders everything at `now - INTERP_DELAY_MS` (100 ms), interpolating position
and aim between the two surrounding snapshots. No extrapolation: a late packet
holds the last known state rather than overshooting.

## Input queue policy

The server consumes **one** input per player per tick, allowing up to
`MAX_INPUTS_PER_TICK` when a player's queue is backed up (jitter catch-up), and
caps the queue at `MAX_INPUT_QUEUE`. Inputs with a sequence at or below what was
already processed are dropped, so replays cannot buy extra movement.

If no input is available, the server briefly extrapolates the last input (up to
3 ticks) so remote viewers do not see a stutter during jitter.

## Shooting

Hitscan. On an accepted fire (`FIRE_COOLDOWN` elapsed) the server raycasts from
the shooter along the aim direction, DDA against solid tiles and analytic
ray-vs-circle against every other entity, and takes the nearest hit. The result
is broadcast as a `shots` entry; damage is applied server-side only.

The client draws its *own* tracer immediately using the same math
(`client/src/game/combat.ts`) and ignores server shot events where
`by === localId`, so shooting feels instant without ever being authoritative.
