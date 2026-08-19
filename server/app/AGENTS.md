# server/app/ — authoritative simulation

## Purpose

The running game: socket handling, the fixed-tick room loop, entity state,
combat, enemy behaviour, map generation, and the constants that define the
game's scale.

## Ownership

| file | owns |
| --- | --- |
| `main.py` | FastAPI app, room REST, `/ws/{code}` endpoint, shutdown |
| `rooms.py` | the room registry: code generation, lookup, disposal |
| `room.py` | authoritative state, lobby phase, tick loop, broadcasts |
| `simulation.py` | movement + tile collision — mirrored by the client |
| `combat.py` | hitscan raycast and melee arc sweep, both entity-agnostic |
| `entities.py` | `Player`, `Pour` (a body emptying its pocket into a platform), `InputCmd` (includes the lantern switch, relayed not simulated) |
| `enemies.py` | `EnemyType` stat blocks (incl. the sight cone, visual variants and accessory pools), live `Enemy`, `dress` |
| `ai.py` | enemy senses, patrol/hunt/return, steering/attack, the director; `hunt_all` is the extraction chase and `startle` is the beat where it visibly spreads outward from the pad |
| `pathing.py` | BFS flow field, one per player |
| `coins.py` | DARK GOLD, the player's purple coin: drop roll, burst, magnet, collection |
| `loot.py` | world collectables: catalog, scene-context scatter, E-to-collect |
| `weapons.py` | weapon catalog (11 guns + the knife) DERIVED from CS2's stat block against the zombie's health, hotbar, per-shot stats, the melee combo, and the ammunition SIZING `ammo.py` imports |
| `crates.py` | INTERACTIVE OBJECTS: the type table (barrels, boxes, chests, stashes, vehicles, altars), their verbs, drop tables, ambush odds and hit boxes; extract from scenery, use, roll |
| `ammo.py` | the reserve MECHANICS: per-player rounds, boxes gated on what the party carries, scatter, collection. How big a reserve is belongs to `weapons.py` — it is a question about the guns that eat it |
| `corpses.py` | dead enemies left on the floor: persist until the map swaps |
| `rift.py` | extraction pads: day-scaled count, plot, the cargo platform and its corner lamps, inbound pickup, per-pad quota, the pour's timing, overfeed, hand-called launch, siren / `hunt_all` |
| `entrance.py` | forest edge VOID corridor, emerge formation, staggered seal (`seal_to`), `bounds` for a map with two corridors, extraction `open_exit` (flared at the border) |
| `quests.py` | run objectives: progress, done, optional risk; the HUD mirrors this list |
| `inventory.py` | the pocket: slots, stacking, weight, `tip_one` (one unit out of the bag per pour beat), per-slot value/weight overrides |
| `world.py` | tile grid, tile alphabet, collision queries |
| `maps.py` | hand-authored maps (`from_ascii`, `from_rects`) |
| `mapgen.py` | procedural forest, seeded and connectivity-checked; `NEST_SCENES` / `HAUNT_SCENES` decide which scenes have creatures standing in them before anyone arrives |
| `scenery.py` | story SCENES: the layouts, the thread linking them, their lights, the wire rows |
| `camp.py` | the camp clearing, its bonfire, the seat ring, the VOID exit, and the walk-out formation |
| `store.py` | the merchant's CLEARING: corridor / small round room / corridor, the two end gates, the man in the middle with his wagon, counter, fire, gear (`KIT_SPOTS`) and torches, the six-stall grid in front of him and the stock rolled onto it, `price_of` + `_haggle`, the cabinet's spot, and the apron the night's platforms land on (`PAYOUT_SPOTS`) |
| `zones.py` | where a run is: title card, `hostile`, `lantern`, `ambient` (zero everywhere but the shop) |
| `skills.py` | what a LEVEL buys: the catalog, the rarity roll, `Loadout` (stacks + spins owed) and `Mods`, the flattened numbers every other module multiplies by |
| `machine.py` | the upgrade machine's TIMELINE — one clock shared with `client/src/game/machine.ts`, including the third reel's per-rarity hold |
| `protocol.py` | wire message shapes — source of truth |
| `config.py` | tuning constants + `client_config()` |

## Local Contracts — cross-cutting

These bind everything in this directory. Subsystem-specific contracts moved
to the design docs indexed below.

- `simulation.py` and `client/src/game/simulation.ts` are mirrors. Changing one
  without the other makes the local player rubber-band.
- `protocol.py` is the single source of truth for message shapes;
  `client/src/net/protocol.ts` mirrors it.
- Per-creature stats never enter a snapshot. The wire carries a type key and
  the client resolves it against `welcome.config.enemyTypes`.
- **A snapshot is one payload for the whole room, serialised once.** Nothing on
  it may differ per recipient: a player's input ack rides on their own row as
  `seq`, not at the top level. Adding a per-socket field puts a `dumps()` per
  player back into every tick.
- **Only what moves goes out at 30 Hz.** Names, colours and the score board
  ride `snapshot.roster`, attached every `ROSTER_EVERY_N_TICKS` and on any
  membership change (`_roster_dirty`); `Player.snapshot_payload()` is the tick
  row and `to_payload()` is the whole player. A new field belongs on the roster
  unless it changes between ticks.
- Every message becomes text through `protocol.dumps` — compact separators, and
  one place to change if the encoding ever does.
- Map data is always `list[list[int]]` — the same value hand-drawn by `maps.py`,
  generated by `mapgen.py`, and sent on the wire. Builders must assert the floor
  is connected.
- The map payload carries TWO kinds of world, and they are not interchangeable.
  `seed` is what the client hashes per tile to scatter the forest, so soil,
  grass, ferns and litter cost four bytes and never repeat. `props` is the list
  `scenery.py` placed, and it has to be transmitted precisely because a scene's
  meaning is in how its pieces sit relative to each other — a hash cannot agree
  on that without mirroring this module client-side. If a new decoration can be
  decided from `(tx, ty, seed)` alone, it belongs to the client and not here.
- `rooms.py` owns every live `Room`. Nothing else may hold one past the request
  that fetched it — a reference kept elsewhere outlives `rooms.drop()` and keeps
  a tick task alive after the last player left.
- A room has two phases. In `lobby` **nothing ticks**: state is pushed on
  membership change only. `Room.begin()` is the single transition into
  `playing`, and it is the only place that starts the loop. Do not add a code
  path that simulates a lobby.
- A room's ZONE is separate from its phase and does not change when the phase
  does. A room opens in the camp: the lobby is the camp seen from a chair,
  `preparation` is the same map with the loop running. `begin()` therefore
  moves nobody. The zone DOES change on `embark()`: that is the walk-out, and
  it is the only legal map swap. Forest spawn is the mouth of a VOID corridor
  `entrance.py` carved on a random edge — never a random tile in the middle.
  `snapshot.arriving` puppets the party out of it the same way `departing`
  puppets them in; when every living body is past the mouth the corridor
  seals rank by rank (VOID → TREE, some ROCK) and `tilePatches` ride that
  tick. The director stays off until `gate.state == gone`. Respawn rings
  around the mouth, not the map centre.
- `Room.seating` is join order, and it is the only thing that decides who
  stands where. Seats are re-spaced by `reseat()` while the room is in `lobby`
  and never afterwards: once the simulation is running, position belongs to it.
  The walk-out is the exception: `step_depart` puppets every body, ignoring
  collision, until `embark()`.
- `{type:"ready"}` toggles `Player.ready` only when the feet are inside
  `CAMP_READY_RANGE_TILES` of the fire, the zone is camp, and the room is not
  already departing. When every living player is ready, `begin_depart()` runs.
- The map is sent in `hello`, once per socket, because the lobby draws the real
  one. Never put it in `lobby`, which is re-broadcast on every membership
  change.
- Player-supplied values (the `name` query parameter) are sanitised in
  `entities.clean_name` before they enter room state, because they are echoed
  to every other player.
## Where the rest went

The per-subsystem contracts that used to live here now sit with their design
law, so a task touching one subsystem no longer loads the other six. Read the
one that owns your change:

| doc | what moved there |
| --- | --- |
| [`docs/design/extraction.md`](../../docs/design/extraction.md) | quests, pads, the pour, the pickup, the deck free, the sweep, the core, both corridors, VOID/egress, `hunt_all`/`startle` |
| [`docs/design/store.md`](../../docs/design/store.md) | where money is created, `balance` vs `Player.gold`, the store map's shape, the wagon, the light budget, the spine, stalls and prices |
| [`docs/design/skills.md`](../../docs/design/skills.md) | levels as spins, `Mods` and every site that must read it, the machine's one lever |
| [`docs/design/player.md`](../../docs/design/player.md) | loot vs coins, stamina, the two weights, the belt trade, the gun catalog, the knife, both resolvers, the combo, ammunition |
| [`docs/design/enemies.md`](../../docs/design/enemies.md) | awareness and the sight cone, glare, noise, groups, the corpse roll, nests |
| [`docs/design/world.md`](../../docs/design/world.md) | zone enforcement, scenes and placement, connectivity, footprints, the landmark, the object vocabulary, the thread, unlit forests, the camp pool |

`ARCHITECTURE.md` at the repo root carries the whole-system map, the authority
table and the gameplay state machine.

## Work Guidance

- Adding a creature = one `EnemyType`, a `SPAWN_TABLE` weight, and a processed
  sprite folder of the same name. It must require no client change — its sight
  cone is two more fields on the same stat block, and the hunt diamond
  fills from `aw` regardless. Visual variants and accessories are lists on
  that type (`variants`, `hats`, `clothes`); `dress` rolls them at spawn
  and the snapshot carries `v` / `hat` / `cloth`. Same stats, different
  sheets. A new overlay is a `GEAR` entry processed `--exact`, then a name
  on the pool.
- Adding a gun = one `WeaponDef` in `weapons.py`, the same key on `loot.py`
  with `pocket="hotbar"`, a held frame in `make_guns.py` and a 16x16 icon
  in `make_loot.py`. Combat, weight and the hotbar HUD all read the
  catalog — the client needs no branch. Ammo is named and unused.
  Adding a MELEE weapon is the same list plus a `MeleeDef` of `ComboStep`s
  and nothing else: the swing resolver, the arc the client draws and the
  HUD cell are all driven off that block. Append to `WEAPONS` and to both
  generators' lists — never insert, or every existing frame index moves.
- Adding a WEAPON to the shop is a row on `store.STOCK_ORDER` plus its unlock
  day. The price, the table it lands on and the tooltip all derive; the client
  needs no change. Keep at least three weapons unlocked on day one — the roll
  is with replacement, so a shorter pool is a grid of six of the same pistol.
- Adding a zone = one `zones.Zone` and whatever builds its map. Its title card,
  its safety and its lighting rules are all data; the client needs no change to
  announce or obey a new one. A forest's subtitle is `night_clock()` — a time
  between 20:00 and 03:00, "da noite" before midnight and "da manhã" after.
  Weather (`clear` / `rain` / `fog`) is rolled with that clock so a second
  night can feel like somewhere else without a new map. Camp is always
  `clear`. Do not hardcode a clock or a coat.
- The expedition hand-off IS the walk-out. In the camp, `{type:"ready"}` at
  the fire; when everyone is ready the room puppets two staggered files into
  the VOID corridor and `embark()` swaps the map for `mapgen.build_forest`,
  sends a second `welcome`, and the zone becomes `forest`. Players stand
  inside the edge corridor; `begin_arrive()` marches them onto the mouth,
  then `begin_seal()` eats the path. Do not invent a third phase for this
  — `playing` stays `playing`. Do not reset
  `last_processed_seq` on embark: the client has been numbering packets since
  the camp, and `queue_input` drops anything at or below that ack. The
  welcome carries `ack` so a rebuilt `LocalPlayer` can resume above it.
  The other two hand-offs are the same shape and share `_swap_map` with it:
  `enter_store()` swaps the forest for the merchant's glade (and banks the
  night), and `depart_store()` swaps that for the NEXT night's forest,
  incrementing `day`. All three keep guns, the leftover bag, xp and the party
  balance, and all three obey the same sequence rule.
- Keep the tick O(entities). Anything that scales with map size belongs in a
  cached structure (see `pathing.py`, one field per player shared by the horde).
- New tuning goes in `config.py` in tiles/seconds, plus a `client_config()` key
  if prediction or rendering needs it. Asset folder names the client loads
  (`coinSprite`, `backpackSprite`, `enemyTypes[*].sprite` / `variants` /
  `hats` / `clothes`) live here too.

## Verification

- `python tests/test_snapshot_shape.py` and `python tests/test_pour.py` from
  `server/`. Both are plain scripts and print `ok`; there is no runner.
- Beyond that, run the server and confirm at least two clients move, shoot and
  take damage without desync.
