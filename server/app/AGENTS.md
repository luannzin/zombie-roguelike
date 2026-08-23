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
| `boss.py` | THE SAWYER: his stat block, his state machine, the four moves, the thrown crescent. NOT an `EnemyType` and not `ai.py` — see its header. Every TIMING he has is read out of `assets/processed/sawyer/manifest.json` at import, so the telegraph on screen and the telegraph in the simulation are one number |
| `arena.py` | the boss yard: a disc of floor, a corridor in, a ring of `FIRE` tiles for light, and the crew's leavings. No way out until he is down |
| `pathing.py` | BFS flow field, one per player |
| `coins.py` | DARK GOLD, the player's purple coin: drop roll, burst, magnet, collection |
| `loot.py` | world collectables: catalog, scene-context scatter, E-to-collect |
| `weapons.py` | weapon catalog DERIVED twice over — 11 guns off CS2's stat block against the zombie's health, and every lâmina off the KNIFE'S own chain — plus the hotbar (two gun cells and the blade cell), per-shot stats, the melee combo, the shield's belt row, and the ammunition SIZING `ammo.py` imports |
| `crates.py` | INTERACTIVE OBJECTS: the type table (barrels, boxes, chests, stashes, vehicles, altars), their verbs, drop tables, ambush odds and hit boxes; extract from scenery, use, roll |
| `armor.py` | worn plates, their four materials, where a blow lands, and the shield's numbers. THE FOURTH CONTAINER — see [`docs/design/gear.md`](../../docs/design/gear.md) |
| `ammo.py` | the reserve MECHANICS: per-player rounds, boxes gated on what the party carries, scatter, collection, and the calibre set the shop stocks its crates off (`party_calibres`). How big a reserve is belongs to `weapons.py` — it is a question about the guns that eat it |
| `corpses.py` | dead enemies left on the floor: persist until the map swaps |
| `rift.py` | extraction pads: day-scaled count, plot, the cargo platform and its corner lamps, inbound pickup, per-pad quota, the pour's timing, overfeed, hand-called launch, siren / `hunt_all` |
| `entrance.py` | forest edge VOID corridor, emerge formation, staggered seal (`seal_to`), `bounds` for a map with two corridors, extraction `open_exit` (flared at the border) |
| `quests.py` | run objectives: progress, done, optional risk; the HUD mirrors this list |
| `inventory.py` | the pocket: slots, stacking, weight, `tip_one` (one unit out of the bag per pour beat), per-slot value/weight overrides. Its stacking rule is re-derived client-side in `client/src/game/interaction.ts` — see the contract below |
| `world.py` | tile grid, tile alphabet, collision queries — **mirrored by `client/src/game/world.ts`**, which prediction runs on |
| `maps.py` | hand-authored maps (`from_ascii`, `from_rects`) |
| `mapgen.py` | procedural forest, seeded and connectivity-checked; `NEST_SCENES` / `HAUNT_SCENES` decide which scenes have creatures standing in them before anyone arrives |
| `scenery.py` | story SCENES: the layouts, the thread linking them, their lights, the wire rows |
| `camp.py` | the camp clearing, its bonfire, the seat ring, the VOID exit, and the walk-out formation |
| `store.py` | the merchant's CLEARING: corridor / small round room / corridor, the two end gates, the man in the middle with his wagon, counter, fire, gear (`KIT_SPOTS`) and torches, the six-stall grid in front of him and the stock rolled onto it, `price_of` + `_haggle`, the AMMUNITION CRATES on the south wall (`AMMO_SPOTS`, `ammo_price_of` — a crate for every calibre the party is carrying, priced off the cheapest gun that eats it), the cabinet's spot, and the apron the night's platforms land on (`PAYOUT_SPOTS`) |
| `zones.py` | where a run is: title card, `hostile`, `lantern`, `ambient` (zero everywhere but the shop) |
| `skills.py` | what a LEVEL buys: the catalog, the rarity roll, `Loadout` (stacks + spins owed) and `Mods`, the flattened numbers every other module multiplies by |
| `machine.py` | the upgrade machine's TIMELINE — one clock shared with `client/src/game/machine.ts`, including the third reel's per-rarity hold |
| `protocol.py` | wire message shapes — source of truth |
| `config.py` | tuning constants + `client_config()`, whose keys are held equal to the client's `GameConfig` by `tests/test_config_parity.py` |

## Local Contracts — cross-cutting

### The boss

- **HE IS NOT AN ENEMY AND `ai.py` MUST NOT LEARN ABOUT HIM.** That module is
  built for a CROWD: a hundred bodies that notice, walk, swing, and are rate
  limited against each other. A boss is one body that is always aware and
  whose entire design is the ORDER of what it does and how long each part
  lasts. Folding him in would mean an `Enemy` with a mode field nothing else
  uses and a special case in every function there.
- **HE SHARES THE CAPSULE AND THAT IS THE WHOLE INTEGRATION.** `Boss` exposes
  `radius` / `capsule_y0` / `capsule_y1` / `x` / `y` / `id` exactly the way
  `Player` and `Enemy` do, so `combat.raycast` and `combat.sweep` hit him
  without knowing he exists. Every gun and the knife worked on him on the day
  he shipped and no weapon will ever need a boss branch. If you add a damage
  source, add him to its target list — do not add a boss path to `combat.py`.
- **THE ART OWNS THE CLOCK.** Windups, recoveries and the length of the
  arrival are derived from the sheet's own frame counts and event frames
  (`boss._clip`). Never type a duration here: the telegraph is what a player
  learns the fight from, so a hard-coded windup that disagrees with the
  animation makes the fight unfair in a way nobody can see. Re-time a clip in
  `make_sawyer.py` and the fight re-times itself.
- **`t` ON THE WIRE IS THE CLIP'S PLAYHEAD, NOT THE STATE'S CLOCK**
  (`Boss.clip_t`). A move is three states and one animation, so the playhead
  runs across all three and the client draws frame `t * fps` with no
  arithmetic of its own. The version that reconstructed it client-side
  restarted the animation on the exact frame the bar landed — see
  `client/tests/boss-clock.ts`, which is the check that found it.
- **`BOSS_DAY` IS READ IN EXACTLY ONE PLACE** (`Room.is_boss_night`). It is a
  day number, not a flag, because the fight is a milestone in a run and a run
  is measured in nights. `None` turns it off.
- **THE MONEY IS STILL MADE IN `enter_store`.** A boss night puts a map
  between the forest and the shop, so the night's takings ride across it as
  `Room._night_takes` — a receipt, not a payment. Do not bank anything in
  `enter_arena`; the global rule (one place, once) has not moved.
- **NO DIRECTOR IN THE ARENA.** The zone is `hostile` — weapons fire, players
  die — but `step_enemies` returns before the top-up. Adding pressure there
  would remove tension (every telegraph would happen in a crowd) and would
  quietly break the arithmetic, because his health is scaled to the guns
  pointed at him.

These bind everything in this directory. Subsystem-specific contracts moved
to the design docs indexed below.

- `simulation.py` and `client/src/game/simulation.ts` are mirrors. Changing one
  without the other makes the local player rubber-band.
- **`world.py` and `client/src/game/world.ts` are mirrors too**, and this one is
  easy to miss: the tile alphabet (`FLOOR`..`LOW`) and `move_axis`,
  `blocks_sight`, `box_blocked` and `raycast_tiles` all exist on both sides
  because prediction runs on them. A tile kind added here alone is a client
  walking through a wall the server is enforcing.
- **`Room.collect_loot` has a client half**, `canStow` in
  `client/src/game/interaction.ts`, which re-derives
  the same three rules (the calibre must be on your own belt, the reserve must
  have room, a slot carrying its own numbers never stacks). It is duplicated on
  purpose — the prompt colours a tooltip at frame rate and cannot wait for a
  round trip — so a change to what a collect refuses is a change in two files.
- `protocol.py` is the single source of truth for message shapes;
  `client/src/net/protocol.ts` mirrors it.
- Per-creature stats never enter a snapshot. The wire carries a type key and
  the client resolves it against `welcome.config.enemyTypes`.
- **MELEE IS RATE-LIMITED BY THE ATTACKER, NEVER BY THE VICTIM.**
  `Room.resolve_attack` reads `Player.hurt_immunity` and must not set it: a
  swing blocked by a shared window has already spent the swinger's cooldown up
  in `ai.step`, so any shared window makes a synchronised pack land one blow
  between them. `hurt_immunity` belongs to the boss's chop and the respawn
  grace. See [`docs/design/enemies.md`](../../docs/design/enemies.md) § The crowd.
- **`Player.stagger` is part of the movement mirror.** It is ticked inside
  `apply_input` / `applyInput`, not on a room clock — reconciliation replays
  unacked inputs through that function, and a decay stepped anywhere else
  replays the body at speeds the server never used.
- **A night can end two ways and there is one implementation of ending one.**
  `Room.step_night` reaching zero calls `_close_extraction`, the same door the
  last spent pad uses. Do not add a second closing path.
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
- **A CATALOG ON `client_config()` IS A LOOKUP TABLE, KEYED BY KEY.** `loot`,
  `weapons`, `objects` and `skills` are all indexed client-side by a key that
  arrived on the roster or on an event, so every one of them ships as a dict.
  `skills.catalog_payload` shipped a LIST of `{"k": ...}` rows while
  `protocol.ts` declared `Record<string, SkillConfig>`: `config.skills[key]`
  was `undefined` for every skill in the game, the HUD tray stayed empty for a
  whole run and the payout tin always wore frame 0. Nothing errored on either
  side — an array is an object in JS, and `test_config_parity.py` compared only
  the top-level key sets. It checks the shape of all four now.
- **A LOOT FRAME COMES FROM THE ATLAS MANIFEST, NEVER FROM CATALOG POSITION.**
  `loot.catalog_payload` reads `assets/processed/loot/manifest.json`, which
  `tools/make_loot.py` keys by item KEY and writes in its OWN order. The two
  lists cover the same items and do not have to agree on sequence; they used
  to be assumed to, and appending the knife and the condensed core to `ITEMS`
  silently handed them frames 40 and 41 — two boxes of ammunition — and shifted
  every gun under them onto somebody else's weapon. Nothing failed; the client
  just drew the wrong picture. `tests/test_loot_frames.py` is the check: run it
  after adding any item on either side.
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
- **The director reads the DAY** (`EnemyDirector(spawn_points, day)`), and it
  scales population, refill rate and wave size only. Creature stats never
  scale: the client resolves health bars against `welcome.config.enemyTypes`,
  so a per-day stat means a per-day catalog payload — bought in exchange for a
  bullet sponge, which is the wrong answer to "make it harder" regardless.
- Keep the tick O(entities). Anything that scales with map size belongs in a
  cached structure (see `pathing.py`, one field per player shared by the horde).
- New tuning goes in `config.py` in tiles/seconds, plus a `client_config()` key
  if prediction or rendering needs it — and the matching REQUIRED field on
  `GameConfig` in the same change, or `test_config_parity.py` fails. Asset folder names the client loads
  (`coinSprite`, `backpackSprite`, `enemyTypes[*].sprite` / `variants` /
  `hats` / `clothes`) live here too.

## Verification

- `python tests/test_config_parity.py` after ANY edit to `client_config()`:
  it is the only check that the constants actually reach the client.
- `python tests/test_snapshot_shape.py` and `python tests/test_pour.py` from
  `server/`. Both are plain scripts and print `ok`; there is no runner.
- `python tests/test_bush_cover.py` after touching `world.tile_hash`,
  `TileMap.bush_at`, `BUSH_CHANCE` or the client's `tileHash`. It pins the hash
  against values taken out of a browser, because nothing at runtime notices when
  the two sides place undergrowth in different tiles — the symptom is a player
  taking cover that is not there.
- `python tests/test_scenery_containers.py` after adding a container kind or a
  scene that places one: two openables on a tile is a sprite inside a sprite on
  ground that can only be claimed once.
- Beyond that, run the server and confirm at least two clients move, shoot and
  take damage without desync.
