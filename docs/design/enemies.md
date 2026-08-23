# Enemies & AI — design law

Nearest contract: [`server/app/AGENTS.md`](../../server/app/AGENTS.md).

| | |
| --- | --- |
| **Owns** | enemy stat blocks, senses, patrol/hunt/return/sleep, steering + attack, the spawn director, the pack call, the extraction chase, corpses |
| **Inputs** | player positions and lantern switches, `ai.Noise` (gunshots, objects), `ai.alarm` (damage), `hunt_all` / `alarm_point` from extraction, nests from `mapgen` |
| **Outputs** | enemy tick rows (`aw` awareness, `v`/`hat`/`cloth` identity, `sl` asleep), `ai.Attack`, kill events, corpse rows |
| **Depends on** | `pathing.py` (one BFS flow field per player), `world.py` (occlusion), `config.py` (every reach/rate), `enemies.py` (`EnemyType`) |
| **Consumers** | `Room.step_enemies` / `resolve_attack`, `coins.py` (the drop roll), `corpses.py`, the client's hunt diamond |
| **Authoritative** | mode, awareness, facing, position, damage, death |
| **Presentation** | the diamond, the bang, the miniboss crown, snarl/howl queueing, the collapse timeline, wounds, blood pools |

## Invariants

- **A PACK IS N TIMES ONE ZOMBIE, and nothing shared may gate that.** Each
  creature's `EnemyType.attack_cooldown` is the ONLY rate limit on its melee.
  `Room.resolve_attack` must never set `Player.hurt_immunity` — that field is
  the boss's suppression window and the respawn grace, and a swing blocked by
  it is a swing whose cooldown was already spent, so any shared window makes a
  synchronised pack pay for one hit between them. See *The crowd* below.
- **A body's attack phase is scattered at birth** (`Room.spawn_enemy`). A group
  arrives together and would otherwise swing in lockstep forever.
- **The director scales with the DAY, and only on population.** Never on health
  or damage — see *The night gets bigger* below.
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
- **Every non-eye awareness source goes through `ai.commit`** — a neighbour's shout (one hop), an `ai.Noise`, `ai.alarm` on damage. Do not add a damage path that skips `alarm`. A SLEEPER goes through `ai.wake`, which is `commit` with the getting-up beat on the front; nothing may commit one directly.
- **A SLEEPING CREATURE IS SWITCHED OFF, and the list of things that reach it is closed.** A body inside `EnemyType.wake_range`, a noise, and damage. Not the sight cone (its eyes are shut), not the lantern, and — the one worth writing down — **not `hunt_all`**. The extraction siren commits every other creature on the map; a den it also woke would be the encounter happening TO a party that never found it. See *The miniboss* below.
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

## The thing that reaches

Position was never a decision. A zombie is slower than you and a wolf has to
touch you, so **backing away is the correct answer to the entire bestiary** —
which quietly meant cover was scenery, worn armour was a number that rarely
mattered, and the shield was a boss-fight item. One creature that hurts you
from where it is standing makes all three mean something everywhere, and it
costs no new systems to do it.

### The band is the mechanic

The bloater cannot fire inside `ranged_min`. **Closing is the answer to it** —
the exact inversion of every other threat in the game, where retreating works.
A player who backs away from one is doing the single thing that keeps them in
its band, and learning that is the whole encounter.

A ranged attacker with no minimum would be strictly better the closer it gets,
which leaves the player nothing to do but retreat: the posture this creature
was added to break.

### Slow and fragile, and both are load-bearing

A durable ranged attacker becomes the only thing on screen the player is
allowed to think about — every other creature turns into an obstacle between
them and it. Two pistol rounds and a walking pace means it is always
answerable; what it costs you is the seconds and the ground you spend
answering it.

### It telegraphs, and the windup is what it PAYS

It plants its feet and swells for most of a second before anything leaves it.
On a permanent run an attack that arrives out of the dark with nothing to react
to is a deleted run rather than a threat.

The windup is not a courtesy: the creature stops closing, stops dodging, and is
the easiest thing on the map to shoot while it runs. And it aims where the
target **is**, never where it will be — so a player who changed direction
during the telegraph has already won the exchange. That trade is what makes the
attack a skill check instead of a dice roll.

### The disc is slow enough to outwalk

`projectiles.py`'s whole argument. A projectile you cannot outrun is a number
the game subtracts, not an attack you answer; the asymmetry between a player
who keeps moving (essentially never hit) and one who stands still (always hit)
is the only mechanic in the game that punishes standing still.

It passes **through** a party and bills each body once. Stopping on the first
body would make the person at the back safe behind their friends, which is the
opposite of what a ranged attack should do to a formation.

### The silhouette

A pear: widest at the belly, with a head half the size of anything else on the
sheet. Every other build in `make_zombie.py` is widest at the shoulders, so the
inverted contour is what makes it identifiable as a black shape at the edge of
a lantern — which is the only distance that matters for something you are meant
to react to before it fires.

The first cut kept the brute's proportions and only pulled the shoulders in,
and `test_creature_sheets.py` correctly called it a recolour: both were simply
*wide*. What separates them now is **height** as well as width.

---

## Change surface

| intent | touch |
| --- | --- |
| senses, hunt, steering, the director | `server/app/ai.py` |
| stat blocks, variants, accessories | `server/app/enemies.py` + a processed sprite folder of the same name |
| what the BOSS looks like, or a new clip of his | `server/tools/make_sawyer.py` — one rig, one shader, poses as angles. Read its header before adding a clip |
| how the boss FIGHTS — a move, a range band, a timing | `server/app/boss.py` + `server/app/config.py` (`BOSS_*`). Timings come off the art; never type one |
| which night the fight happens on | `server/app/config.py` (`BOSS_DAY`), and nothing else |
| the yard: its size, its fires, what is lying in it | `server/app/arena.py` |
| how the fight FEELS — shake, blood, sound, the grade | `client/src/game/boss.ts` (`punchFor` is the whole table), `client/src/render/post/looks.ts` (`arenaLook` / `enrageLook`) |
| his health bar and his name | `client/src/components/hud/BossBar.tsx` |
| what a creature LOOKS like | `server/tools/make_zombie.py` — FOUR anatomies (`Build.kind`), one derived ramp each, then `process_sprites.py --exact` for the sheet AND its `-death` |
| a creature that attacks at RANGE | `EnemyType.ranged_*` + `shot_*` — **fields, never a key comparison**. The flight is `server/app/projectiles.py` and is shared with the boss's crescent; `ai.py` must stay ignorant of every creature's name |
| what a WOLF looks like, or how many heads it has | `server/tools/make_wolf.py` — one animal, `Build.heads` is a tuple of offsets. It writes the raw art AND processes it |
| what a creature SOUNDS like | `EnemyType.voice` + three recipes in `server/tools/make_audio.py` (`<voice>-idle` / `-alert` / `-death`) |
| the pack: speed, bite, give-up, the howl's reach | `server/app/config.py` (`WOLF_*`) |
| the miniboss: health, bite, the wake radius, the beat | `server/app/config.py` (`MINIBOSS_HP`, `ALPHA_*`) |
| where the den is and what is in it | `server/app/scenery.py` (`_den`, `LANDMARKS`) + `server/app/mapgen.py` (`DEN_SCENES`) |
| the crown and the always-on health bar | `client/src/render/layers/vision.ts` (`drawRankMarks`), `client/src/render/layers/entities.ts` |
| tuning (reach, rates, group sizes, `BUSH_CONCEAL_SCALE`) | `server/app/config.py` |
| where undergrowth is, on both sides | `world.tile_hash` / `TileMap.bush_at` + `client/src/render/layers/terrain.ts` |
| where creatures start standing | `server/app/mapgen.py` (`NEST_SCENES` / `HAUNT_SCENES`), `Room._seed_nests` |
| the diamond, snarls, wounds | `client/src/render/layers/vision.ts`, `client/src/game/entity-visuals.ts`, `Game.updateGrowls` |

**Adding a creature** = one `EnemyType`, a `SPAWN_TABLE` weight, and a processed
sprite folder. It must require **no client change**. A creature with its own
VOICE adds `voice` plus three recipes in `make_audio.py`; a MINIBOSS adds
`rank`, `sleep_sprite`, `persists`, a scene in `scenery.py` and a row in
`mapgen.DEN_SCENES` — and stays OFF `SPAWN_TABLE`, because a miniboss the
director could also roll is a random event rather than a place.

**Do not touch from here:** extraction pad state, the economy, loot tables, or
the wire protocol pair.

---

## The crowd

- **A HORDE THAT CANNOT KILL YOU FASTER THAN ONE ZOMBIE IS NOT A HORDE, IT IS
  A PICTURE OF ONE.** For most of this game's life, melee damage was
  rate-limited PER PLAYER: one hit opened a 0.6s window every other creature
  whiffed into, so the ceiling was `max(damage) / MELEE_IMMUNITY` dps
  **regardless of how many were on you**. Thirty-two zombies did exactly as
  much damage as one, and a body could stand still inside the entire population
  of a map for 6.7 seconds. That single constant is why the game had no horror
  in it. Every other lever — spawning, lighting, sound, the sight cone, the
  director — was decorating a threat that arithmetically could not escalate.
  - **THE FIX WAS A DELETION, NOT A NUMBER.** The first attempt shrank the
    window to a floor (0.14s) on the theory that the creature's own cooldown
    was the real limiter and the shared one was a second limiter stacked on
    top. Half right, and the half that was wrong is the interesting half: a
    blocked swing still spends the swinger's cooldown up in `ai.step`, so ANY
    shared window makes a pack that swings TOGETHER land one blow between them
    and then reset in lockstep. A pack that walked to you together is
    synchronised by construction. The window had to stop gating melee entirely,
    not get smaller.
  - **AND THE PHASE HAD TO BE SCATTERED**, or the fix produced a different bad
    game. With every swing landing, a synchronised six delivers 54 damage in one
    frame and nothing for the rest of the second — a coin flip rather than a
    fight: you survive the volley untouched or you are deleted by it, and
    nothing you do in between changes it. One random offset at spawn turns the
    volley into a STREAM. Same damage per second, spread across the second, so
    being surrounded is a cost you feel accumulating and can pull out of — and
    the bites, flinches and hurt sounds become a rhythm instead of one stacked
    frame of noise.
  - **THE SHAPE THAT CAME OUT IS THE RIGHT ONE, INCLUDING THE PART THAT GOT
    EASIER.** A lone zombie now takes ~13s to kill a full-health player, up from
    6.7 — because it was never the threat, and the old cap was holding the
    SINGLE creature's damage up to the same ceiling as the crowd's. Two is
    ~6.6s, three ~4.4s, five ~2.8s, eight ~1.7s. The unit of danger moved from
    the creature to the SITUATION, which is what the encounter design already
    assumed and never got to be true.
  - **THE PLAYER HAS TO BE TOLD BEFORE IT KILLS THEM.** A crowd that can delete
    you in under two seconds needs a tell, or a death reads as the game cheating
    rather than as a mistake. The client counts bodies inside `PRESSURE_TILES`
    of the local player and drives the danger vignette and the heartbeat off it
    (`Game.stepPressure`), so the screen closes in and the pulse comes up while
    the pack is still CLOSING. Same two channels low health already used, which
    is deliberate: one message, two deliveries, and a player with the sound off
    still gets it.

## The pack

- **A SECOND CREATURE THAT IS A ZOMBIE WITH DIFFERENT NUMBERS IS A ZOMBIE.**
  That is the whole brief the wolf was written against, and it is why every
  number on it is set as a DIFFERENCE from `ZOMBIE` rather than picked:
  `enemies.ZOMBIE` is the unit this game is balanced in — `weapons.py` derives
  eleven guns off its health — so a creature not expressed against it is a
  creature nobody can reason about.

  The difference in one line: **a zombie is a wall that never stops, a wolf is
  a knife that leaves.** It is faster than you walk (3.6 tiles against your
  4.4, so strolling away does not work and sprinting always does), it bites
  every 0.55s for 5 instead of every 1.1s for 9, it dies in three pistol
  rounds instead of four, and it gives up at ten tiles instead of
  twenty-four. So the answer to a zombie — back off and shoot — is the wrong
  answer to a pack, and the answer to a pack — break the line and commit to
  leaving — does not work on a horde that never stops coming.
- **BEING BITTEN CONSTANTLY FOR A LITTLE IS NOT THE SAME EVENT AS BEING HIT
  OCCASIONALLY FOR A LOT**, even at the same dps, and the arithmetic hides
  that. 5 every 0.55s is 9.1 dps against the zombie's 8.2 — a rounding error
  per animal. What changes is that you can watch a zombie's swing coming and
  you cannot watch a pack's: the damage arrives as a texture rather than as
  events, so the decision it asks for is "am I still going to be here in three
  seconds" instead of "can I take this one".
- **THE HOWL IS WHAT MAKES IT A PACK RATHER THAN FOUR ANIMALS IN A FIELD.**
  An ordinary commit nudges whatever is within `ENEMY_ALERT_SHARE_DIST` — one
  hop, anything, eight tiles. A creature with `pack_call_tiles` instead calls
  **its own kind, at four times that reach**. One wolf finding you is the
  whole clearing finding you, and the sound arrives before they do.
  - **IT IS RESTRICTED TO ITS PACK, and that is the half worth arguing
    about.** A howl that also woke the dead would be strictly better than a
    shout at every range, and the wolf's entire design is that it is not a
    better zombie. It would also mean the next social creature inherited a
    general-purpose alarm by accident. `tests/test_pack.py` pins both
    directions, because nothing at runtime can tell.
  - **THE GROUP IS `EnemyType.pack`, NOT THE TYPE KEY**, and the difference is
    the whole reason the alpha has a call at all. Keyed on the type, the
    loudest call in the game belonged to the one creature there is only ever
    one of — his howl reached nobody. A leader brings the animals that are
    already out there. It is also not `voice`, which is nearly right and is
    the footgun version: a creature given a wolf's growl for flavour would
    silently join the pack.
  - **AND IT DOES NOT REACH INTO A DEN.** A sleeper never answers a call, and
    that cost a good scene: a wolf howling beside the den waking its alpha is
    exactly the picture you want. It is also thirty tiles — well past the
    lantern — so a player shooting at a pack across a clearing would wake a
    miniboss they cannot see and had no reason to expect. What reaches a
    sleeper stays the three things that are about IT, because those are the
    three a player can choose not to do.
  - **AND THE SOUND IS THE ONLY CLEAN VOICE IN THE GAME.** Everything else in
    the mix is torn — the growls, the snarl, the engine, the siren — because
    everything else is either a body that has stopped working or a machine. A
    howl is a healthy sound made on purpose, and against a night built out of
    rasp it is unmistakable through any amount of other noise. It has to be:
    it is not a reaction, it is a MESSAGE, and the player has to know they have
    been reported at the same moment the map does.
- **`group_min` IS ON THE STAT BLOCK, NOT IN THE WEIGHTS TABLE.** The
  director rolls the type first and clamps the size to it. A pack of one is a
  stray dog, and putting the floor in `ENEMY_GROUP_WEIGHTS` would have meant
  one table describing two creatures.

## The miniboss

**A new class, and the argument for it is that the boss could not be one.**
`boss.py` is a body with a state machine, a cinematic, an arena, a health bar
across the screen and a module of its own; it is the milestone a run is built
around and it costs what it costs. THE ALPHA IS AN `Enemy`. `ai.py` steers it,
the same cone notices you, the same flow field routes it around a rock, the
same `Room.damage_player` resolves its bite. Four things separate it from a
zombie and **all four are data**:

    it is ASLEEP    `sleep_sprite` — until somebody comes close enough
    it PERSISTS     `persists` — the map placed it; the recycler must not
    it is RANKED    `rank` — how the HUD is told to crown it
    it has a PLACE  `scenery._den`, the way the Sawyer has an arena

So the SECOND miniboss is a stat block, a scene and a sprite folder. Nothing
in this module or in the client learns its name.

- **THE ENCOUNTER IS THE DECISION, AND THE DECISION NEEDS THE PLAYER TO SEE IT
  FIRST.** Every other creature in this game is already looking for you when
  you find it. This one is curled up in its own den with its eyes shut, and
  `ALPHA_WAKE_TILES` is deliberately **shorter than the lantern's reach** —
  which is the whole mechanism. Your own light finds the den before the thing
  in it can hear you, and what you do next is yours. That gap IS the feature;
  anything that closes it (a longer wake radius, a lit scene, a siren that
  reaches it) deletes the encounter and leaves a big fast zombie.
- **IT IS DRAWN ASLEEP RATHER THAN PAUSED.** A creature frozen on its idle
  column reads as lag or as a corpse. `wolf-alpha-sleep` is a real pose — a
  curl, heads tucked, three frames of breath, and **a dark socket where every
  other creature in the game carries a lit one**. That absence is the
  telegraph: the accent hue is this game's word for "it has noticed you", so
  the one creature that has not is the only art in the game wearing an empty
  socket. It lights on the frame its eyes open.
- **AND IT STANDS UP BEFORE IT COMES.** `ALPHA_WAKE_DELAY` is a free beat
  — it gets to its feet, it howls, and only then does it walk. Nothing else in
  this game gets one and nothing else needs one: it is the difference between
  waking something and being ambushed by it, and it is the last beat of a
  decision the player has already been given time to make.
- **YOU CAN LEAVE, AND LEAVING PUTS IT BACK.** Run past `ALPHA_AGGRO_TILES` or
  past the leash and it gives up, walks home, and **goes back to sleep**. That
  last clause is the one that matters: the den is still there, still occupied,
  still a decision. A miniboss that idled in the treeline afterwards would
  have turned a PLACE into a wandering monster the first time anybody escaped
  one — and escaping is supposed to be an outcome, not a delay.
  - It is also why a sleeper never RESETTLES. An ordinary creature that gets
    wedged on the way home accepts where it is standing as its new home, which
    is right when one patch of forest is as good as another and wrong for
    something whose whole encounter is a place.
- **THREE HEADS BITE LIKE THREE HEADS.** He is not a big wolf with a big
  number on his swing — he is the wolf's own rhythm, faster: 13 every 0.45s,
  29 dps, the highest melee in the game by a wide margin. That is deliberate
  and it is what makes leaving as correct an answer as fighting. You cannot
  trade with him; you kite him or you go.
- **HIS HEALTH IS A THIRD OF THE BOSS'S AND IT IS WRITTEN AS THAT FRACTION**
  (`MINIBOSS_HP = BOSS_HP_BASE // 3`). Typed, he would be a creature somebody
  balanced once. As a fraction he is a stated portion of the fight the run is
  already built around, and retuning that fight retunes him in the same
  motion. Unlike the boss it does NOT scale with the party — the client
  resolves health bars against `welcome.config.enemyTypes`, and a per-room
  number would mean a per-room catalog.
- **HE WEARS A CROWN, AND THE CROWN IS THE CONFIRMATION RATHER THAN THE
  WARNING.** The warning is the art: every creature in this game carries one
  lit socket per eye, and a wolf carries one per HEAD, so **three embers
  moving together in the dark** is a thing the player has never seen and the
  only thing in the forest that looks like it. The HUD mark sits above the
  hunt diamond, does not fill, and is drawn UNLIT while the thing is still
  asleep — the same sentence the sprite is telling with its shut eyes, said
  again in the one channel that survives the distance.

## The night gets bigger

- **THE FOREST USED TO GET EMPTIER AS THE RUN WENT ON**, and nothing in this
  module or `enemies.py` had ever heard of the day. The map triples between
  night one and night five (4 028 tiles -> 12 144) and the quota sextuples, so
  density fell from 1.49 enemies per 1000 tiles to 0.49. Night five was three
  times quieter than night one while asking six times the work — which a player
  reads as padding, because that is what it is.
  - **THREE NUMBERS WALK WITH THE DAY AND THEY ARE ALL ABOUT PRESSURE**: how
    many the forest holds (`ENEMY_DAY_POPULATION`), how fast it refills
    (`ENEMY_DAY_RATE`), and how big a wave is (`ENEMY_DAY_GROUP_TILT`).
  - **NOT HEALTH AND NOT DAMAGE**, which is the tempting fourth and the wrong
    one. A zombie with 90 HP on night five is the same encounter taking three
    times as long, and the player reads that as their gun getting worse — the
    bullet-sponge trade, where the answer to "make it harder" is "make it
    slower". Now that a crowd can kill, POPULATION is the difficulty knob: the
    same zombie is frightening in sixes and was never frightening alone.
    Scaling stats would also force a per-day `enemyTypes` payload, because the
    client draws health bars off the catalog — a whole contract bought in
    exchange for a worse game.
  - **THE REFILL RATE IS THE ONE THAT CHANGES BEHAVIOUR.** The cap decides how
    crowded a forest is; the interval decides whether clearing a pocket buys
    any peace. By night five a wave lands every 1.7s rather than every 2.5, so
    standing and fighting stops being a way to make ground safe and starts
    being a way to be surrounded.
  - **THE SECOND SILHOUETTE IS THE PACK, AND IT IS WHY POPULATION WAS NEVER
    ENOUGH.** For most of this game's life `ENEMY_TYPES` held exactly one row
    and the three "variants" were sprites over identical stats, so a run's
    whole bestiary was learned in the first sixty seconds and nothing new
    walked out of the dark until the Sawyer. Population scaling buys pressure;
    it cannot buy surprise, because surprise is a thing you have not seen
    before and there was only ever one thing. See *The pack* below.

## Design law

- **THE THREE CREATURES ARE THREE ANATOMIES, NOT THREE PALETTES.** They were
  three palettes for a long time: one head box, one body box, one stride, and
  the walker, the husk and the brute differed by which four hex values filled
  them. Cover the colour and there was one creature on the sheet. Now the
  walker is a person with its head sunk into its shoulders, the husk is a
  SKELETON — skull, a gap of neck, ribs with the night showing between them —
  and the brute is a mass with fungus growing out of its shoulders, wider than
  its own head is tall. The test is S15's and it is the one to run before any
  future variant ships: draw all of them in solid black at 1x, and if you
  cannot say which is which, what has been drawn is a recolour.
- **A FACE IS A LIGHT, NOT A HOLE.** Every creature carries an EYE: one
  saturated pixel inside a dark socket, and it is the single accent the sprite
  is allowed (S12). Sockets used to be ink on rot, which at eight pixels is
  one dark value pretending to be two, and the result was a creature with no
  face at exactly the distance where a face is all you have. The eye is what
  the player tracks at the edge of the lantern, it is the last thing to go as
  the thing walks out of the light, and it stays lit in the corpse's head
  through the whole collapse. ONE eye burns on the walker and the husk and
  BOTH burn on the brute — asymmetry is a head turned slightly away, and the
  brute is the one that has already seen you.
- **THE COLLAPSE IS ONE TIMELINE AND EVERYTHING RIDES IT.** `HEAD_POSE` and
  `BODY_POSE` in `make_zombie.py` are the fall in offsets, and the creature,
  its hat and its shirt all read the same two tables. That is what keeps a cap
  ON a head through a fall the cap was authored separately from — and it is
  why a new accessory is a draw function and no timing at all.
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

## THE SAWYER — the first boss

**Shipped.** `server/app/boss.py` (the fight), `server/app/arena.py` (the
yard), `client/src/game/boss.ts` (how it feels), `client/src/render/boss.ts`
(how it is drawn) and `client/src/components/hud/BossBar.tsx` (his name and
his health). Which night it happens on is `config.BOSS_DAY`, read in exactly
one place. What follows is why it is shaped the way it is.

- **HE IS ONE OF THE DEAD, DRAWN BIGGER.** Every material on him is a ramp
  another creature is already made of — the brute's `HIDE` at a boss's value,
  the walker's `ROT`, the husk's `BONE`, the brute's `FUNGUS` — and his hard
  hat is `zhat-hardhat`, the accessory a walker can be wearing when you meet
  it. That is not thrift. The three creatures answer "what happened to the
  people who lived here"; the boss has to answer the same question with the
  same evidence, or he is a monster from another game standing in this one.
  The forest is already full of felled trunks, stumps and blighted trees:
  somebody was cutting it down, and he is what is left of the man who ran the
  crew.
- **A BOSS IS NOT A BIG ENEMY, IT IS A THING WITH A TELL.** Every attack on
  the sheet spends more frames winding up than swinging — `chop` holds the bar
  over his shoulder for four frames and buries it for four more before he can
  wrench it out, `sweep` plants and coils for six, `rip` cocks for five. The
  punish window is DRAWN, not configured. A boss whose blow cannot be read
  before it lands is one players learn by dying rather than by watching, and
  at 14fps the windup is the only place that information can live. When the
  numbers are written, they go around those frames: `manifest.clips.*.events`
  carries `hit` / `release` / `roar` / `impact` as frame indices, and it is the
  art telling the simulation when the blow lands rather than the simulation
  guessing.
- **FIVE ATTACKS THAT ARE FIVE SHAPES, NOT FIVE DAMAGE NUMBERS.** `chop` is
  vertical and lands on a point; `sweep` is a circle and lands on everything;
  `rip` is horizontal and lands at range, as a crescent that outlives the
  animation; `charge` is not a swing at all and lands as a BODY; `rev` lands
  on nothing. Two attacks that swing in the same
  plane are one attack the player cannot tell apart until it has hit them,
  which is why the chop and the throw are authored on perpendicular arcs and
  why the throw's arc is written down per facing rather than derived — a
  horizontal swing does not project the same way face-on as it does in
  profile.
- **`charge` IS THE ANSWER TO A GUN, AND WITHOUT IT THERE WASN'T ONE.** Every
  other move on the sheet is authored around a player who came close. The
  crescent nominally covers range, and it is DELIBERATELY slow enough to walk
  out of — which is right, because it is the move that teaches "keep moving",
  and which is also why it is no answer at all to somebody who was already
  moving. A body that walks at 2.9 tiles a second cannot reach a body that
  runs at 4.4, so a player with a rifle and any patience won the fight by
  walking backwards, and the entire move list was decoration.

  A fifth swing would not have fixed it. **The counter to reaching across a
  gap has to be closing it**, so the charge is the one attack whose hitbox
  MOVES: he roars, locks a heading, and crosses the yard at 10.5 tiles a
  second — faster than a sprint, so it cannot be outrun, only sidestepped.
  That is the same lesson the chop teaches, asked again at a range where the
  player believed the answer was "stand here".

  **AND HE LEADS THE TARGET, WHICH IS THE PART WORTH ARGUING ABOUT.** The
  first cut locked the heading onto the player's CURRENT tile, on the
  principle that total commitment is what makes a fast move fair. It landed
  nought out of sixteen against a player orbiting him at walking pace, because
  a charge that takes a second to cross eight tiles cannot touch anybody
  moving at all, in any direction, ever. A move that punishes nothing is not a
  counter to kiting; it is a cutscene the player strolls around. Leading turns
  it into the question it was supposed to ask: he has committed to where you
  were HEADED, so the answer is to stop doing what you were doing. Autopilot
  loses, reacting wins, and the commitment is still absolute — nothing steers
  him once he is running, and a charge dodged into the treeline buries the bar
  in a trunk for the longest free window in the fight (`slam`).

  **IT COSTS NO ART, AND THAT IS WHY IT IS THREE CLIPS.** `rev` is the cord
  and the roar (already the fight's "something is coming" beat), `walk` is the
  run, `idle` is him pulling up. It is the only move that is not one
  animation, which is why `Move` grew `clip` / `after` and why `row.m` now
  names a MOVE rather than a sheet — the client resolves the animation through
  `welcome.config.bossMoves` instead of assuming the two strings are the same.
- **THE PICKER WAS A LOOKUP TABLE WITH A COIN FLIP ON TOP.** Bands abutted
  rather than overlapping — chop to 4.4 tiles, rip from 4.0 and alone for the
  rest of the arena — and the rule was "never the last move again", uniform
  over whatever was legal. Under four tiles that is chop, sweep, chop, sweep
  forever; past four and a half it is one attack on a metronome. Both halves
  are learned in about fifteen seconds and the rest of the fight is executing
  a known loop. Three changes, each removing a different kind of
  predictability:
  - **THE BANDS OVERLAP.** Four tiles is now chop, throw and charge. A player
    cannot read the next move off their own distance.
  - **EACH BAND TAPERS** (`BOSS_BAND_EDGE`), so the overlap is a blend rather
    than a cliff: a move is likeliest in the middle of what it is FOR and
    merely possible at the fringe. The fight still teaches a shape — close is
    heavy, far is thrown — without being a rule.
  - **A REPEAT IS EXPENSIVE, NOT ILLEGAL** (`BOSS_REPEAT_PENALTY`). Two chops
    running is a thing that happens to you now; three never is, and even that
    ban yields when the range leaves him nothing else to do — out past the
    throw's reach the charge is the only legal move, and refusing to repeat
    there does not vary the fight, it removes it. **A boss forbidden to repeat
    is exactly as readable as one that always does**, in the other direction,
    and the strict alternation was the single biggest reason he read as a
    script.
- **THE ENRAGE CHANGES THE MOVES, NOT JUST THE CLOCK.** It used to be three
  multipliers — faster walk, shorter wait, one extra crescent roll — which is
  the same fight on a shorter timer, fought with knowledge the player already
  has. Each swing now has a variant, and every one of them costs zero frames
  of art because it changes **what leaves the weapon rather than how the
  weapon is posed**:
  - **`rip` throws a FAN** (`BOSS_FAN_CRESCENTS`). One crescent is beaten by a
    step sideways, which is the right answer in the first half — it is the
    move that teaches "keep moving", and it is also why a player who learned
    that lesson could not lose the second half. Three make the sidestep a
    DIRECTION: there is still somewhere to be, and now you have to pick it.
  - **`sweep` WALKS** (`BOSS_SWEEP_DRIFT`). Rooted, the answer is to back off
    one tile and wait a second and a half out. Drifting, backing off has to be
    a retreat. At a fraction of his walk, never his full speed — the one move
    with no blind side must not also be unloseable.
  - **`chop` COMES BACK** (`BOSS_DOUBLE_CHOP_CHANCE`). This is the variant
    that changes the most while adding the least: no new clip, no new hitbox,
    no new number. What it takes away is a CERTAINTY. The chop's recovery is
    the longest window in the fight and every safe thing a player does —
    reload, heal, walk in and swing — is scheduled off it. Half the time it is
    now a window you have to look at first.

  Same clips, same telegraphs, same lengths. **The player's knowledge is not
  invalidated, it is made insufficient**, which is what a phase change is for.
- **`rev` EXISTS BECAUSE A FIGHT NEEDS A BEAT THAT IS NOT AN ATTACK.** It is
  the only clip in which nothing moves toward the player: he pulls the cord,
  the engine catches, and he roars two frames after it peaks — so the sound in
  the player's head is the saw rather than him. It is the phase change and the
  free window in one, and it is the last third of the arrival cinematic for
  the same reason.
- **THE CINEMATIC IS A SHADOW BEFORE IT IS A BOSS.** `arrive` opens on four
  frames of nothing but a growing ellipse under the party. Nothing else in
  this game casts a growing shadow — `render/shadows.ts` draws what is
  standing on the floor — so the mark is unambiguous, and it is the only
  warning anybody gets. He enters the frame already falling and already
  tucked, lands in a crouch that opens the floor, and the clip ends on idle
  frame 0 so the fight starts from the pose the loop is in.
- **THE SPIN HAS NO FACING.** `sweep.png` ships once, and the rig's own facing
  steps through down / right / up / left twice inside it. Authored per facing
  it would be the same rotation written down four times with a phase offset,
  and four copies of one rotation drift. The client enters the clip at
  whatever phase the boss was already facing.
- **HIS DEATH IS THE ACCENT GOING OUT.** Every creature in this game carries
  one lit pixel in a dark socket, and the Sawyer carries three: two eyes and
  the ember in the exhaust, all the same hue, because the player has spent a
  whole night learning that that colour is a thing that has noticed them.
  `rev` runs to zero across the collapse, which takes the ember out, stops the
  shake and stops the chain. He is the only thing in the game with lights to
  lose, and losing them is the last event on the sheet.
- **HE IS AT THE END OF THE WAY OUT, AND THAT IS THE WHOLE STAGING.** The
  party does a normal night — find the pads, feed them, call the pickup, walk
  to the exit — and the exit corridor opens onto a yard instead of onto the
  shop. Nothing announces it. They are not sent to fight him; they are leaving,
  and he is what is between them and leaving. Every other framing considered
  (a quest row, a door, a choice at the console) makes the fight a thing the
  party opted into, and the one this game can afford to say is "you were
  already going this way".
- **THE YARD IS A CIRCLE BECAUSE EXPLORING IS OVER.** `mapgen` builds forests
  out of noise, which is right for a place whose game is not being able to see
  across it. A boss fight wants the opposite: one legible space, no dead ends
  to be cornered in, no rock to lose a 41-pixel chainsaw behind, and a rim you
  can put your back to without being safe. So `arena.py` is authored — a disc,
  a corridor in, a ring of fires — and the dressing stays on the outer band so
  nothing is ever between the camera and the fight.
- **THE YARD IS LIT, AND IT IS THE ONLY HOSTILE PLACE THAT IS.** Three layers:
  a rim of nine `world.FIRE` tiles (they light, cast, animate and block, for
  free), four burning heaps inside it as scene lights with a mark on the
  ground under each, and — the exception — a real `ambient` floor.

  That floor breaks a stated rule and it is worth being honest about why. The
  rule is that ambient is zero anywhere a player can die, because darkness
  hiding information is what makes exploring mean anything. **Nobody explores
  this map.** There is nothing in it to find and exactly one thing to look at,
  and that thing kills you if you cannot see which arm is going up. A dark
  middle does not buy tension here; it buys a fight lost to the lighting.

  The floor does not replace the fires. `layers/darkness` takes the MAX of the
  zone floor and the fov's own light rather than summing them, so the drums
  and the heaps are still the brightest things in the room and the room still
  has shape. The heaps are LIGHTS AND DECALS, never tiles: a solid tile in the
  middle of a boss arena is somewhere a two-tile body can wedge itself.
- **THE EXIT IS SHUT BY NOT EXISTING, AND IT OPENS AT THE FAR END.**
  `build_arena` carves the way IN and nothing else; `Room._boss_down` calls
  `arena.open_far_exit` on the frame he falls, which cuts the treeline
  straight across from the corridor the party walked in through. A door that
  is drawn and locked invites a party to stand in it. And one door at each end
  of a room is a room you CROSS — a way out beside the way in would send them
  back the way they came, which is not what surviving that fight earned.

  The yard is a disc inside a nine-tile margin, so the corridor lands in the
  treeline with rock between it and the floor; `open_far_exit` carves the same
  kind of lane the arrival got. Without it every side fails the connectivity
  check and the party is sealed in with a corpse — which is why
  `test_boss_fight.py` asserts both the side and the reachability.
- **HIS HEALTH SCALES WITH THE GUNS POINTED AT HIM** (`boss.hp_for`), and the
  first player is worth more than the rest — a party also brings more ways to
  be revived and more bodies for him to have to choose between. The fight is
  authored around its LENGTH: long enough to learn the telegraphs, short
  enough that learning them pays off.
- **NOTHING ELSE IS INVITED.** The director does not run in the arena. It
  would remove tension rather than add it — every telegraph would happen in a
  crowd — and it would break the health arithmetic, because guns pointed at a
  zombie are guns he does not have to survive.
- **HITTING HIM HAS TO FEEL LIKE HITTING HIM, AND FOR A WHILE IT DID NOT.**
  `Room.fire` and `Room.melee` have had him in their target lists since the
  day he shipped, so every round always did its damage. But the client draws
  the local player's own shot the frame the trigger goes down, off a target
  list `predictShot` builds itself — and **he was not in it**. The tracer flew
  visibly through the biggest body in the game: nothing stopped, no number
  floated, no marker, no hit sound, no camera bump. The only feedback that
  arrived was the server's `hit` event a round trip later, spent on a flash
  and some blood, on the darkest sprite in the game, while a chainsaw was
  coming at you.

  **A SHOT THAT LOOKS LIKE A MISS IS A MISS**, as far as the player is
  concerned, and a player who believes their gun does nothing to a boss stops
  shooting him. The fix is the same split every other body already uses: the
  prediction owns the INSTANT (the tracer stopping, the number, the spark, the
  bump, the sound), the server's event owns the CONFIRMATION (the blood, and
  the health bar, which is state). His capsule ships as `welcome.config.bossHit`
  rather than being mirrored, because a hitbox the client guesses at is a
  hitbox that disagrees with the one deciding damage.

  Two related things were wrong for the same reason and are fixed with it.
  `feelVictim` routed his id into `entity-visuals`, which knows nothing about
  him — it minted a visual state for a body nothing draws off, so the reaction
  went nowhere. And his flash is `lighter` compositing the sprite over itself,
  which brightens a body **in proportion to how bright it already was**: a
  zombie visibly blinks at 0.85 alpha and he barely moved. It takes two passes
  on a hard hit.
- **WHAT IS STILL OPEN.** Whether he should drop something other than coins
  and xp (a weapon? the art has an obvious one); and whether a party that
  WIPES in the yard should lose the night's takings — at the moment they
  respawn and the receipt survives, which is the forgiving reading.

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
