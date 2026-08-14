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
  "shoot": true,
  "lantern": true
}
```

`{"type":"ping","t":<client ms>}` → `{"type":"pong","t":<echo>}` for RTT.

`{"type":"start"}` — host only; ignored otherwise.

`{"type":"ready"}` — toggle ready at the campfire. The server ignores it unless
the room is in the camp, the walk-out has not started, and the player's feet
are inside `readyRangeTiles` of the fire. When every living player is ready the
snapshots flip `departing` and the server puppets the party through the VOID
exit; a second `welcome` is the forest.

### server → client

`hello` (once, first message — the lobby is built from this):

```json
{
  "type": "hello",
  "playerId": "a1b2c3d4",
  "code": "ABC1234",
  "config": { "tickRate": 30, "dt": 0.0333, "tileSize": 16, "...": "..." },
  "map": { "width": 60, "height": 40, "tileSize": 16, "seed": 8412, "tiles": [[2, 2, 0, "..."]] },
  "zone": { "key": "camp-1", "kind": "camp", "day": 1, "title": "Preparação",
            "subtitle": "Dia 1", "hostile": false, "lantern": false }
}
```

The map is here rather than in `lobby` because the lobby is not a picture of
the camp — it draws the real one, and `lobby` is re-broadcast on every
membership change. `zone` says where the room is and how that place behaves:
`hostile` gates enemy spawns and weapons, `lantern` gates the lamp, and both
are enforced server-side as well as described here.

`lobby` (on every membership or phase change):

```json
{
  "type": "lobby", "code": "ABC1234", "hostId": "a1b2c3d4", "phase": "lobby",
  "zone": { "...": "..." },
  "players": [{ "id": "a1b2c3d4", "name": "Player483", "color": "#4d9de0", "x": 488, "y": 364.4 }]
}
```

Roster rows carry real world positions: the seat a player is standing on at the
fire is the tile they start `preparation` on, so nothing moves when the host
presses start.

`welcome` (when the run starts, or on joining one already running):

```json
{
  "type": "welcome",
  "playerId": "a1b2c3d4",
  "player": { "id": "...", "name": "Player483", "color": "#4d9de0", "x": 200, "y": 168, "...": "..." },
  "config": { "tickRate": 30, "dt": 0.0333, "tileSize": 16, "moveSpeed": 70.4,
              "playerHalfWidth": 4.8, "playerHalfHeight": 3.6, "...": "..." },
  "map": { "width": 64, "height": 40, "tileSize": 16, "tiles": [[1, 1, 0, "..."]] },
  "zone": { "...": "..." },
  "ack": 183
}
```

`snapshot` (every tick):

```json
{
  "type": "snapshot",
  "tick": 4021,
  "ack": 183,
  "departing": false,
  "zoneKey": "camp-1",
  "players": [{ "id": "...", "x": 0, "y": 0, "vx": 0, "vy": 0, "ax": 1, "ay": 0, "lantern": true,
                "hp": 100, "alive": true, "xp": 24, "gold": 6, "level": 1, "xpInLevel": 24, "xpToLevel": 40,
                "ready": false }],
  "enemies": [{ "id": "e12", "t": "zombie", "x": 0, "y": 0, "vx": 0, "vy": 0, "ax": 1, "ay": 0, "hp": 22 }],
  "shots": [{ "id": 7, "by": "a1b2c3d4", "x": 0, "y": 0, "dx": 1, "dy": 0, "dist": 132.5, "hit": "b5c6" }],
  "attacks": [{ "by": "e12", "target": "a1b2c3d4", "x": 0, "y": 0, "dx": 1, "dy": 0, "dmg": 9, "blocked": false }],
  "kills": [{ "kind": "enemy", "killer": "a1b2c3d4", "victim": "e12", "x": 0, "y": 0, "xp": 12, "gold": 3 }]
}
```

`ack` is per-recipient: the last input sequence the server processed for *that*
client. `departing` is the camp walk-out: the server is moving everybody and
the local player must not predict. `ready` is camp-only. `zoneKey` is the
zone this snapshot belongs to — drop it if it does not match the last welcome.

A second `welcome` (same socket) is a new zone. The client rebuilds the map
from it the same way it did the first time — that is how the party leaves the
camp for the forest. `ack` is the same counter snapshots use: the client must
keep issuing input sequences above it. Resetting to 0 after the camp walk-out
makes every later packet look like a replay, and the player cannot walk off
the spawn tile.

Enemies carry no per-type constants: `t` keys into `welcome.config.enemyTypes`,
which is the stat block table from `server/app/enemies.py`. Only live enemies
are listed — an id that stops appearing is dead or despawned.

`attacks` is enemy melee. `dmg` is 0 and `blocked` true when the victim's
i-frames absorbed the swing (see below); the event is still broadcast so the
client can show the hit being absorbed rather than silently dropping it.

## Melee damage is rate-limited per victim

`MELEE_IMMUNITY` (0.6 s) is a property of the **victim**, not the attacker. A
landed hit opens a window in which further melee whiffs, so the damage ceiling
is one enemy's damage per window no matter how many are in contact — eight
zombies on one player deal exactly what one does. Without it, a pack that
surrounds you resolves every swing on the same tick and kills instantly, which
is a matter of spawn luck rather than play. Respawns get a longer window
(`RESPAWN_IMMUNITY`) so waking up inside the horde is survivable.

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

## Frame rate vs tick rate

Rendering runs on `requestAnimationFrame` (60 fps+); the simulation runs at
`TICK_RATE`. They are decoupled:

* **local player** — `LocalPlayer.subTickPosition` advances a scratch copy of
  the state by the leftover accumulator time through the same collision-aware
  `applyInput`, so the sprite moves on every frame and lands exactly where the
  next tick commits it. The scratch uses **live** movement/aim (not the last
  sent packet) so a mid-tick keypress starts motion this frame; nothing is
  stored, so reconciliation is unaffected.
* **remote players** — interpolation is already continuous in time, so they are
  smooth at any refresh rate.
* **aim** — recomputed per frame, not per tick, so the crosshair never feels
  capped at 30 Hz. The value sent to the server is still sampled per tick.
* **entities are drawn in screen space** with integer rounding, so motion is
  quantized to 1 screen pixel instead of `zoom` screen pixels.

Raising the simulation to 60 Hz is a one-line change (`TICK_RATE` in
`server/app/config.py`): the client reads `dt` from the `welcome` config, so it
follows automatically — at the cost of double the input packets and snapshots.

## Remote entities: interpolation

Enemies are pure server state — the client never predicts them, it interpolates
them exactly like remote players, through the same `SnapshotBuffer`. The local
player is the only entity that is ever predicted.

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
