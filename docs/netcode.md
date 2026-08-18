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
  "lantern": true,
  "held": 0
}
```

`{"type":"ping","t":<client ms>}` → `{"type":"pong","t":<echo>}` for RTT.

`{"type":"start"}` — host only; ignored otherwise.

`{"type":"ready"}` — toggle ready at the campfire. The server ignores it unless
the room is in the camp, the walk-out has not started, and the player's feet
are inside `readyRangeTiles` of the fire. When every living player is ready the
snapshots flip `departing` and the server puppets the party through the VOID
exit; a second `welcome` is the forest, standing inside a VOID corridor on a
random edge. Snapshots then flip `arriving` while they walk out of it; once
everyone is on floor the woods seal the path (`tilePatches`) and the first
quest appears.

`{"type":"collect","id":"l3"}` — pick up a world drop. The server ignores it
unless the room is in a hostile zone, the player is alive, their feet are
inside `lootCollectTiles` of that drop, and the destination has room: the
pocket for valuables (empty slot or a stack of the same key), the 3-slot
hotbar for guns (no stacking). Overweight is allowed. The remaining
list rides `welcome.loot` and a dirty snapshot `loot`; `lootPickups` is the
juice for that tick and carries `slot` so the client can fly the sprite
onto that HUD cell (`dest` is `"hotbar"` for a gun, omitted for the bag).
The pocket itself rides the roster as `inv`; the belt as `guns`.

`{"type":"break","id":"k1"}` — smash a crate. The server ignores it unless
the player is alive, the walk-out / forest emerge has not started, and their feet are
inside `crateBreakTiles` of that crate. Camp maps have none; a bullet that
hits the crate's sprite box (`crateHitWTiles` × `crateHitHTiles`) does
the same work. The remaining list rides
`map.crates` and a dirty snapshot `crates`; `crateBreaks` is the juice
for that tick (`drop` is `empty` / `coin` / `item`, plus `k` when an
item fell out). The smash opens the LOW tile to floor.

`{"type":"activate","id":"r0"}` — press an extraction console: wake the
platform, load it, or launch it. `id` is the pad; omitted means nearest
in range. The server ignores it unless the player is alive, the walk-out
/ arrival has not started, and their feet are inside `riftActivateTiles`
of that console. Dormant → charging (once, and only while no other pad
is awake). Open → spend bag catalog value toward that pad's quota (guns
stay on the belt); every tier past it wakes another lift drone. Pressing
a paid console launches the platform: it strains, breaks ground — the
deck's tiles arrive as `tilePatches` on that tick — and flies off. When
the last pad has been launched the server carves `egress`, sets
`blackout`, sweeps the map's drops and offers the exit quest.

`{"type":"drop","slot":0}` — toss a bag slot onto the ground near the
player's feet. The server ignores it in camp, during the walk-out, or if
that cell is empty. A stack becomes one world drop per unit; the server
picks walkable tiles. The ground list and the roster both dirty.

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
            "subtitle": "Dia 1", "hostile": false, "lantern": false, "weather": "clear" }
}
```

The map is here rather than in `lobby` because the lobby is not a picture of
the camp — it draws the real one, and `lobby` is re-broadcast on every
membership change. `zone` says where the room is and how that place behaves:
`hostile` gates enemy spawns and weapons, `lantern` gates the lamp, and both
are enforced server-side as well as described here. `weather` is the night's
coat (`clear` / `rain` / `fog`), rolled with the forest clock so a second
expedition can feel like somewhere else; camp is always `clear`.

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
  "ack": 183,
  "loot": [{"id":"l1","k":"compass","x":412.5,"y":288.5}],
  "corpses": [],
  "quests": []
}
```

`snapshot` (every tick):

```json
{
  "type": "snapshot",
  "tick": 4021,
  "ack": 183,
  "departing": false,
  "arriving": false,
  "zoneKey": "camp-1",
  "players": [{ "id": "...", "x": 0, "y": 0, "vx": 0, "vy": 0, "ax": 1, "ay": 0, "lantern": true,
                "hp": 100, "alive": true, "held": 0, "ads": false,
                "xp": 24, "gold": 6, "level": 1, "xpInLevel": 24, "xpToLevel": 40,
                "ready": false, "seq": 183 }],
  "enemies": [{ "id": "e12", "t": "zombie", "x": 0, "y": 0, "vx": 0, "vy": 0, "ax": 1, "ay": 0, "hp": 22, "v": 1, "hat": 0 }],
  "shots": [{ "id": 7, "by": "a1b2c3d4", "k": "glock18", "x": 0, "y": 0, "dx": 1, "dy": 0, "dist": 132.5, "hit": "b5c6", "dmg": 7 }],
  "attacks": [{ "by": "e12", "target": "a1b2c3d4", "x": 0, "y": 0, "dx": 1, "dy": 0, "dmg": 9, "blocked": false }],
  "kills": [{ "kind": "enemy", "killer": "a1b2c3d4", "victim": "e12", "x": 0, "y": 0, "xp": 12, "gold": 3, "t": "zombie", "v": 1, "dx": 1, "dy": 0 }],
  "loot": [{"id":"l1","k":"compass","x":412.5,"y":288.5}],
  "crates": [{"id":"k1","x":320,"y":240,"v":0,"flip":0}],
  "crateBreaks": [{"id":"k2","x":352,"y":256,"v":2,"flip":1,"drop":"empty"}],
  "corpses": [{"id":"e12","x":400,"y":288,"t":"zombie","v":1,"ax":1,"ay":0,"dx":1,"dy":0}]
}
```

`ack` is per-recipient: the last input sequence the server processed for *that*
client. `departing` is the camp walk-out: the server is moving everybody and
the local player must not predict. `arriving` is the forest emerge, the same
lock walking out of the edge corridor. `ready` is camp-only. `zoneKey` is the
zone this snapshot belongs to — drop it if it does not match the last welcome.
`map.entrance` on welcome is the corridor's geometry; a snapshot `entrance`
row is only the live state (`open` / `sealing` / `gone`). `map.rifts` is
the pads (day-scaled count) with their geometry — deck, console, torch,
the four parked drones and the heading the platform leaves along; a
snapshot `rifts` list is the live half when one changes, including
`woke` (when each drone started spooling). `map.egress` / snapshot `egress` is the extraction
exit, carved when the feed quota is paid — same VOID corridor as
`entrance`, walkable once that row exists. Crossing it (standing on VOID
past the mouth, toward the map edge) returns the party to camp.
`blackout` is on welcome and on the snapshot that kills the lamps.
`tilePatches` are
`[tx, ty, kind]` for the ranks of trees that just grew, or the exit
opening. `quests` is the run
objective list (`id`, `label`, `have`, `need`, optional `done` / `risk` / `gold`) —
attached on welcome and again only when it changes.

A second `welcome` (same socket) is a new zone. The client rebuilds the map
from it the same way it did the first time — that is how the party leaves the
camp for the forest. Forest spawn is inside that corridor, not a random
clearing. `ack` is the same counter snapshots use: the client must
keep issuing input sequences above it. Resetting to 0 after the camp walk-out
makes every later packet look like a replay, and the player cannot walk off
the spawn tile.

Enemies carry no per-type constants: `t` keys into `welcome.config.enemyTypes`,
which is the stat block table from `server/app/enemies.py`. Only live enemies
are listed — an id that stops appearing is dead or despawned. `v` indexes
`enemyTypes[t].variants` (the body sheet). `hat` and `cloth` are optional
indices into those overlay pools; omitted means the zombie wears none. The
look is rolled once at spawn and never changes.

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

Hitscan. On an accepted fire (the equipped weapon's `fireCooldown` elapsed,
and its `aimDelay` spent if any — the AWP waits while the trigger is held)
the server raycasts from the shooter along the aim direction, DDA against
solid tiles and analytic ray-vs-circle against every other entity, and takes
the nearest hit. An empty hand (`held` = -1) does not fire. The result is
broadcast as a `shots` entry (`k` the weapon key, `dmg` the damage); damage
is applied server-side only. Per-gun numbers ride `welcome.config.weapons`.

The client draws its *own* tracer immediately using the same math
(`client/src/game/combat.ts`) and ignores server shot events where
`by === localId`, so shooting feels instant without ever being authoritative.
