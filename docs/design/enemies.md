# Enemies & AI — design law

Nearest contract: [`server/app/AGENTS.md`](../../server/app/AGENTS.md).

| | |
| --- | --- |
| **Owns** | enemy stat blocks, senses, patrol/hunt/return, steering + attack, the spawn director, the extraction chase, corpses |
| **Inputs** | player positions and lantern switches, `ai.Noise` (gunshots, objects), `ai.alarm` (damage), `hunt_all` / `alarm_point` from extraction, nests from `mapgen` |
| **Outputs** | enemy tick rows (`aw` awareness, `v`/`hat`/`cloth` identity), `ai.Attack`, kill events, corpse rows |
| **Depends on** | `pathing.py` (one BFS flow field per player), `world.py` (occlusion), `config.py` (every reach/rate), `enemies.py` (`EnemyType`) |
| **Consumers** | `Room.step_enemies` / `resolve_attack`, `coins.py` (the drop roll), `corpses.py`, the client's hunt diamond |
| **Authoritative** | mode, awareness, facing, position, damage, death |
| **Presentation** | the diamond, the bang, snarl queueing, the collapse timeline, wounds, blood pools |

## Invariants

- **An enemy chases nothing it has not noticed.** Awareness fills only inside the sight cone; `aggro_range` is the GIVE-UP distance, not the notice distance.
- **Sight is symmetric with the lantern.** `ENEMY_VIEW_DARK_SCALE` and `ENEMY_VIEW_LIT_SCALE` are the reaches BOTH sides use — they ship as `enemyViewDarkScale` / `enemyViewLitScale` and `client/src/render/fov.ts` reads them. One source, so there is nothing to keep in step. Never give a creature an absolute view distance.
- **Undergrowth is cover, and it is cover because the picture already said so.**
  `layers/terrain` draws bushes AFTER the characters — stand in a thicket and
  the art closes over you — while `look` tested a clean ray at full reach.
  A picture that lies about the rules is worse than no picture: the player takes
  cover, is seen anyway, and concludes the senses are broken. Standing on a bush
  tile now cuts a creature's reach against you by `BUSH_CONCEAL_SCALE`.

  **IT SCALES THE REACH RATHER THAN BLOCKING THE RAY,** and that was the
  decision. An occluder is all-or-nothing: one bush anywhere on the line would
  hide a player standing in the open ten tiles past it, and a thicket would
  become a wall nothing could see over from any range. Concealment belongs to
  the tile you are STANDING in — crouch in it and they have to come close,
  break the line and you are a shape in a clearing again. The lantern still
  overrules it, because a lit bush is a lit bush.

  **THERE IS NO BUSH TILE.** Undergrowth is DERIVED from the map seed by a hash
  both sides run (`world.tile_hash` / `render/terrain.ts`'s `tileHash`), which
  is why a map payload is four bytes of seed and not a decoration layer. The
  server re-derives the client's bushes rather than anybody shipping a mask, so
  the hash is now a contract: `tests/test_bush_cover.py` pins it against values
  taken out of the browser. Density (`BUSH_CHANCE`) ships in `welcome.config`
  because it decides how much cover a forest HAS; what it cuts the reach to
  stays server-side, because the client never asks.
- **Nothing snaps its head.** Every facing change outside a hunt goes through `ai.turn_towards` at a bounded rate.
- **`ai.glare` never commits.** The beam turns heads and caps awareness below the commit line; being spotted stays the cone's job.
- **Every non-eye awareness source goes through `ai.commit`** — a neighbour's shout (one hop), an `ai.Noise`, `ai.alarm` on damage. Do not add a damage path that skips `alarm`.
- **`ai.Noise` is the only shape sound has**, and the list is cleared every tick.
- **Melee damage is rate-limited per victim** (`MELEE_IMMUNITY`), not per attacker.
- **Stagger is not on the wire** — the slowed velocity is enough.
- **Per-creature stats never enter a snapshot**; the wire carries a type key resolved against `welcome.config.enemyTypes`.
- **Keep the tick O(entities).** Anything that scales with map size belongs in a cached structure (`pathing.py`).

## The hunt (extraction chase)

`hunt_all` commits every creature on one frame; `ai.startle` is what stops that
reading as a switch — face the pad, hold for a beat scaled by distance, then
walk. Awareness is pinned, so the diamond is already lit. See
[`extraction.md`](extraction.md).

## Change surface

| intent | touch |
| --- | --- |
| senses, hunt, steering, the director | `server/app/ai.py` |
| stat blocks, variants, accessories | `server/app/enemies.py` + a processed sprite folder of the same name |
| tuning (reach, rates, group sizes, `BUSH_CONCEAL_SCALE`) | `server/app/config.py` |
| where undergrowth is, on both sides | `world.tile_hash` / `TileMap.bush_at` + `client/src/render/layers/terrain.ts` |
| where creatures start standing | `server/app/mapgen.py` (`NEST_SCENES` / `HAUNT_SCENES`), `Room._seed_nests` |
| the diamond, snarls, wounds | `client/src/render/layers/vision.ts`, `client/src/game/entity-visuals.ts`, `Game.updateGrowls` |

**Adding a creature** = one `EnemyType`, a `SPAWN_TABLE` weight, and a processed
sprite folder. It must require **no client change**.

**Do not touch from here:** extraction pad state, the economy, loot tables, or
the wire protocol pair.

---

## Design law

- **SOME SCENES KEPT THEIR DEAD.** Every wreck on the map is a story about
  people who did not make it, and for a long time none of them had anybody in
  it — the scene said "something happened here" and the forest answered "and
  nothing is here now". The scenes that are specifically about somebody DYING
  (`mapgen.HAUNT_SCENES`: the ambulance, the last stand, the checkpoint, the
  crash, the bus stop) now stand one or two creatures in the wreck at map build
  time, idle until they notice you. It is not a difficulty change — it is the
  answer to "why is this dangerous", and it is what turns opening the third car
  of the night into a decision. The QUIET scenes are deliberately left empty: a
  deadfall is a tree that came down, and putting a creature in it would say the
  map is a list of encounters. The stretches with nothing in them are what make
  the ones with something in them land.

---

## Server contracts

- Damage from melee is rate-limited per victim (`MELEE_IMMUNITY`), not per
  attacker. Do not add a damage path that bypasses it.
- **An enemy chases nothing it has not noticed.** `Enemy.mode` is `idle`
  (patrol a leash around `home`), `hunt`, or `return`, and `Enemy.awareness` is
  the 0..1 meter between the first two. It fills while a living player stands
  inside the creature's SIGHT CONE (`EnemyType.view_tiles` / `view_degrees`,
  occluded by the tile grid, tested in `ai.look`), faster the closer they are,
  and is PINNED at 1 for the whole hunt — a meter that sagged behind cover
  would flicker the hunt diamond back to empty while the thing was still coming.
  `aggro_range` is now the give-up distance, not the notice distance.
- **Sight is symmetric, and the lamp is a two-way switch.** A cone's reach is
  a fraction of the LANTERN's, chosen per target by that player's own switch:
  `ENEMY_VIEW_DARK_SCALE` and `ENEMY_VIEW_LIT_SCALE`. Hunt uses the same
  pair: a player who kills the lamp is a shorter shape, and that is how they
  slip a hunter. Never give a creature an absolute view distance.

  **THE CLIENT READS THE SAME TWO NUMBERS**, shipped as `enemyViewDarkScale` /
  `enemyViewLitScale`, and draws its naked-eye and lit washes at exactly those
  reaches (`render/fov.ts`). They used to be copied there as `EYE_REACH` /
  `SIGHT_REACH` under a comment asking whoever moved one to move the other.
  That was the wrong shape for this rule: symmetry breaking produces no error,
  no desync and no visible artefact — only a player seeing a radius the
  creatures do not respect, which is unfalsifiable from inside the game. A
  contract with no symptom has to be one value, not two that agree.
- **Nothing snaps its head.** Every facing change outside an active hunt goes
  through `ai.turn_towards` at a bounded rate — `ENEMY_IDLE_TURN_DEGREES` while
  patrolling, `ENEMY_TURN_DEGREES` under a glare — and a patrolling body walks
  along the facing it currently has, so a new waypoint is a curve rather than a
  change of direction. Assigning `aim_x`/`aim_y` directly makes a turret out of
  a shambling thing, and the sight test is measured off that facing: a
  clearing of enemies re-aiming per tick reads as searchlights.
  `ENEMY_ARRIVE_TILES` must
  stay comfortably above the resulting turn radius or a patrol orbits a
  waypoint it can never reach.
- **`ai.glare` is the lantern's price and it is deliberately indirect.** The
  beam falling on an enemy that is not looking at you TURNS it (bounded rate,
  `ENEMY_TURN_DEGREES`) and raises awareness to at most `ENEMY_GLARE_CAP` —
  never to the commit line. Being spotted stays the sight cone's job. A glare
  that spotted directly would make the lamp a button nobody presses; one that
  swings heads around leaves the player a second to kill the light.
- Awareness also arrives from three more places that are not the creature's
  own eyes, and all of them go through `ai.commit`: a neighbour's shout (one
  hop, `ENEMY_ALERT_SHARE_DIST` — a chain would wake the map), an `ai.Noise`,
  and `ai.alarm` when the room applies damage. Getting shot in the back must
  wake it; do not add a damage path that skips `alarm`. A gun hit that
  leaves the enemy alive also stacks `Enemy.stagger` (`take_stagger`):
  `ai.move` scales vx/vy by it so a burst slows then plants them. Do not
  put stagger on the snapshot — the slowed velocity is enough. A pause in
  fire decays the meter (`tick_stagger`).
- **`ai.Noise` is the sound system's only shape.** The room collects them
  during a tick (`Room.noises`) and `ai.update` consumes them; they are
  cleared every tick, and a noise that survived one would keep waking whatever
  wandered into it. A gunshot is the only source so far — the next one is an
  append with a different radius, never a second mechanism.
- Enemies arrive as a GROUP (`ENEMY_GROUP_SIZES`, weighted): one landing spot,
  members scattered around it, each taking its own tile as `home`. The
  director places an occupied patch of forest, not a wave aimed at the party.
- Only what moves goes on the tick row, and `aw` earns its place: the client
  fills the hunt diamond from it every frame. Cone geometry is per-type and
  rides `welcome.config.enemyTypes`; it is tested, not drawn. A zombie's
  look (`v`, `hat`, `cloth`) is identity and never changes, but enemies
  have no roster, so those indices ride the tick row — omit `hat` / `cloth`
  when the slot is empty.

- **A corpse pays a ROLL, not a receipt.** A creature's `gold` is the most it
  can drop in DARK GOLD; each point is flipped on its own at
  `COIN_DROP_CHANCE` (`coins.roll_drop`), and that chance is now RARE rather
  than merely low — a 3-gold zombie pays nothing four times in five and three
  about twice in ten thousand. It was cut when the coin became an anomaly
  shard: see `docs/design/store.md`, where the art is the argument for the
  rate. Nothing is credited — the shards hit the ground and somebody has to
  walk over them. `COIN_DROP_CHANCE` and `crates.DROP_COIN` are the only two
  taps on this currency and they are set together; turning one alone just
  moves where the same money comes from. xp is the opposite and stays fixed: what the kill was worth does
  not vary, what fell out of it does. `kills[].gold` is what actually fell,
  `enemyTypes[*].goldMax` is the ceiling; the client displays neither as a
  promise. The body STAYS: `corpses.py` keeps one row per kill, shipped like
  crates (on welcome, and on a snapshot only when the list grew). The kill
  event is the juice (fall direction, look, `dx`/`dy`); the client plays
  `<sheet>-death` along that vector. The list is the record you walk back
  through. Camp maps have none; embark clears them.

- **SOME SCENES KEEP THEIR DEAD** (`mapgen.HAUNT_SCENES`). The scenes that are
  about somebody dying stand one or two creatures in the wreck at map build
  time, through the same `nests` channel the sanctuary's pack uses — the row is
  `(x, y, count)` and a count of 0 means "the landmark's guard", which is
  `room.NEST_PACK`. It is not a difficulty change; it is the answer to "why is
  this dangerous", and it is what stops the loot in a wreck being a chore. The
  quiet scenes are deliberately left empty: the stretches with nothing in them
  are what make the ones with something in them land.
