# World, zones & scenery — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`assets/AGENTS.md`](../../assets/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the tile grid and its alphabet, hand-authored and procedural maps, story SCENES, interactive objects, zones, weather, the camp |
| **Inputs** | a seed, the day number, `ammo.party_calibres` (what the belt carries), the zone being built |
| **Outputs** | `MapPayload` (`tiles`, `seed`, `props`, `lights`, `crates`, `entrance`, `rifts`), `Population` (`scenes`, `route` — kept server-side), `welcome.zone` |
| **Depends on** | `world.py` (tiles), `maps.py` (builders), `config.py` (`TILE_SIZE`, map size) |
| **Consumers** | `loot.py` and `ammo.py` (two passes over the same scene list), `rift.py` (where pads plot), `crates.py` (`attach`), the client's terrain/scenery layers |
| **Authoritative** | every tile, every scene position, every object and its footprint, the zone's rules |
| **Presentation** | terrain scatter, prop bending, wind, boot prints, darkness |

## The two halves of a world, and this is the rule that decides where code goes

| | placed by | on the wire | why |
| --- | --- | --- | --- |
| **TEXTURE** — soil, grass, ferns, litter, prop variants | the CLIENT, hashed from `map.seed` | four bytes | one rock is as good as another |
| **SCENES** — a wreck and the prints leading away from it | `server/app/scenery.py` | the `props` list | the meaning is the relationship between the pieces, and a hash cannot agree on that |

**Anything decidable from `(tx, ty, seed)` belongs to the client.** Anything that
means something is a scene.

## Invariants

- **A scene is the unit of placement, never a prop.** Adding "one more object type" that places itself individually is the mistake this module exists to prevent.
- **Scenes run after `_connect`**, may CLEAR only rock and tree, and `_stamp` REVERTS on a failed reachability re-check. Never drill.
- **The connectivity check is a SET from a point that matters**, not a count from the first floor tile in scan order.
- **A standing thing is solid on one tile of height, at its feet.** Growing the box up the sprite turns a signboard into a wall.
- **PROP** (solid + sight-blocking) is for vehicles and statues; **LOW** (solid, transparent to light) is for waist-high cover. Making cover PROP puts a shadow wedge behind every barrel.
- **No forest scene is lit.** `SceneLight` exists and only the STORE and the extraction `BEACON` use it. World lights LIGHT and never EXPLORE.
- **There are no buildings.** A procedurally dropped house teaches "house = loot" in two expeditions.
- **Zone rules are enforced server-side**, not just described to the client. `zone.hostile` gates the GUN, not the swing.
- **`zones.ambient` is zero in every zone a player can be killed in.** The shop is the only exception.
- **`populate`'s `scenes` and `route` are not on the wire and are not unused** — extraction wants exactly them.
- **Map data is always `list[list[int]]`**, and builders must assert the floor is connected.

## Danger zones

- `mapgen._connect` / `scenery._stamp` — a bad edit generates unplayable maps intermittently, on some seeds only.
- `FOOTPRINTS` depth and `_claim` — silently invisible walls.
- `crates.attach` + `Navigator.invalidate()` — freeing a tile without invalidating leaves pathing walking into thin air.

## Weather with teeth

Weather used to be **paint**. It was rolled, shipped and drawn — a rainy night
was the same night with a wash over it — which made it the cheapest thing in
the game to notice and the least worth noticing.

`zones.WeatherRule` gives each coat two scalars, and they are an **inverted
pair**:

| coat | sight | noise | the night it makes |
| --- | --- | --- | --- |
| clear | 1.0 | 1.0 | The baseline. The only night where what you learned about ranges is true. |
| rain | 0.88 | 0.55 | **The sneaking night.** You can see; you cannot hear. Best night to work a clearing, worst night to be surprised on. |
| fog | 0.58 | 1.15 | **The blind night.** You cannot see; sound carries further than usual. A gunshot here is a much worse idea than anywhere else. |

Neither is simply *harder*. Each takes away a different one of the two senses
this game is about, so the correct way to play a rainy night and a foggy one
are **different from each other** rather than differently difficult. If one
coat ever became worse than another on both axes, weather would go back to
being a difficulty roll in a costume — `test_weather.py` fails if it does.

**Clear having no modifier is not an absence of a rule.** It is the reference
the other two are read against, and a game where every night modified something
would have nothing to modify it *from*.

### Sight is a mirror and has to ship

`ai.look` and the client's `render/fov.ts` multiply by the same number off
`welcome.config.weather`. Sight symmetry is a hard contract here — a creature
sees a shape exactly as far as the shape sees it — and the failure when the two
drift has **no symptom at all**: the player simply gets spotted from further
away than the wash they were shown said they could be. Nobody reports that;
they report the game feeling unfair.

The scalar multiplies the tile count both reaches are fractions of, rather than
the two fractions separately — the same arithmetic written twice is how one of
them ends up missing it.

### Noise has one door

`ai.hear`, and only there. Every sound in the game — a gunshot, the extraction
siren, a horde's howl, a vault being forced — passes through it, and a coat
applied at the call sites instead would be missing from the next one somebody
adds.

---

## Change surface

| intent | touch |
| --- | --- |
| forest shape, size, connectivity | `server/app/mapgen.py`, `server/app/config.py` |
| a new scene / scene layout | `server/app/scenery.py` (+ art in `server/tools/make_scenery.py`) — containers are thinned by `_thin_containers`, so a scene may author more than survive |
| a new LANDMARK (one per map, placed first) | `server/app/scenery.py` `LANDMARKS` — a tuple, in order; the first one that lands is what the thread routes to |
| which scenes come with creatures standing in them | `server/app/mapgen.py` (`NEST_SCENES` / `HAUNT_SCENES` / `DEN_SCENES`) |
| a new interactive object | `server/app/crates.py` (`TYPES`) + `server/tools/make_objects.py` — **and a scene in `scenery.py` that actually places one.** A catalog row nothing places is dead content nothing at runtime notices; `chest` and `strongbox` sat unplaced for months with full footprint and container-set entries. `tests/test_containers.py` fails if the top tier stops spawning |
| an object that takes TIME to open | `crates.ObjectType.open_time` + `Room._begin_force` / `_finish_force`. The noise fires at the START — that is the mechanic, not a detail: a slow open whose noise came at the end would be a gamble whose stake is paid after the payoff is known |
| a new zone | `server/app/zones.py` + whatever builds its map — **no client change** |
| camp layout | `server/app/camp.py` |
| terrain scatter, prop drawing | `client/src/render/layers/terrain.ts`, `layers/scenery.ts`, `client/src/render/terrain.ts` |
| a scenery ASSET | `server/tools/make_scenery.py` / `make_objects.py`, then rerun and commit both — see [`assets/AGENTS.md`](../../assets/AGENTS.md) |

**Do not touch from here:** extraction pad state, the economy, the skills
catalog, or the wire protocol pair.

---

## Design law

- The room's ZONE (`server/app/zones.py`) says where the run is and how that
  place behaves: its title card, whether enemies spawn and guns fire
  (`hostile`), whether the lantern may be switched on (`lantern`), and how much
  light the place has of its own (`ambient` — zero everywhere but the shop).
  The client is told all of it and infers none of it from the map.
- **The camp is one place, not two.** The lobby draws the map the server sent
  in `hello`, with every player on the coordinates the simulation is holding
  for them; starting the run changes what answers your input, not where anybody
  is standing. Nothing may teleport at that transition. Leaving the camp is
  different: the walk-out is a puppeted march into the VOID corridor, and the
  forest `welcome` that follows is a new map. The title screen frames
  the same fire on the same rest shot (`campFireAnchor`); entering a room must
  not jump it.
- Entering a zone is an EVENT, and it is one continuous move: the lobby's chrome
  slides away while its own camera drifts off the fire onto your character and
  pushes in to game scale; the arena takes over on the frame that lands. Camp
  holds you still and facing the camera with no HUD while the title names the
  day. Forest skips that posed hold — the party is already walking out of the
  edge corridor, letterboxed, and the title names the night over the march.
  Then the controls and the chrome return together. Every zone gets a title.

- **The forest is sized to the night it has to hold, and 132 x 92 is the
  three-pad size.** The map and its scene count are one decision, not two: a
  map that grows without growing its stories is not a bigger world, it is a
  longer walk between the same things. 132 x 92 was picked so that a night with
  THREE extraction pads can put them far enough apart to be three separate
  expeditions rather than three stops on one lap — which is an argument about
  three pads, and it does not hold for one. A single-pad night on that same map
  is one errand with a long empty walk either side of it.

  So GROUND PER PAD IS THE CONSTANT and the map is the variable
  (`mapgen.size_for_pads`, scaling AREA off `rift.count_for_day`): one pad is
  76 x 53, two is 108 x 75, three is the full 132 x 92, and the scene count
  takes the same fraction. The progression a player feels over the first week
  is the world opening up, not the same world with more errands added to it.
  Aspect never changes — a forest is not a corridor at any size — and the pad
  clearances relax on a cramped map rather than failing, so a small forest
  still gets its extraction point somewhere imperfect.

  The pocket grew with the full size too (five slots), because at three pads a
  party filled the bag at the second scene and spent the rest of the night
  walking past things, which is the game refusing its own content.

- The world arrives in two halves and they are placed by two different systems.
  TEXTURE — soil, grass, ferns, litter, prop variants — is scattered by the
  client from the map seed, because one rock is as good as another. SCENES —
  a cabin and its fence, a camp somebody left in a hurry, boot prints and the
  blood at the end of them — are placed by `server/app/scenery.py` and shipped
  on the map payload, because their meaning is the relationship between the
  pieces and a hash cannot agree on that. Anything decidable from
  `(tx, ty, seed)` belongs to the client; anything that means something belongs
  to a scene.

- **THE FOREST IS A VOCABULARY OF THINGS YOU CAN OPEN, AND THAT REPLACED THE
  CRATE.** A crate is a noun with one verb; once a player has smashed four of
  them the fifth is furniture, and a map made of them generates SPACE rather
  than stories. What is out there now (`server/app/crates.py`, art in
  `server/tools/make_objects.py`) is a set of promises the player learns by
  walking: BARRELS you break (wood, steel, fuel); BOXES, ammo cases and totes
  whose lids hinge open; CHESTS with a domed lid, the only silhouette in the
  woods that curves, which ALWAYS pay; small stashes — a mailbox, a suitcase,
  a chest freezer, a wheelie bin, a toolbox; and six kinds of abandoned
  VEHICLE — car, van, ambulance, police cruiser, lorry, bus — four tiles long,
  solid, sight-blocking, with a bonnet or a bay that lifts. Each type owns its
  own drop table, its own loot TAGS (an ambulance leans medical, a mailbox
  leans dropped), its own rarity curve and its own prompt.
- **A SCENE MAY KEEP FIVE OPENABLES AND NO TWO ON ONE TILE** (`scenery.MAX_CONTAINERS`,
  `_thin_containers`). Scenes roll their containers in independent loops — the
  roadblock rolls barrels AND crates, the haulage spill rolls up to seven — and
  the rolls SUM, so the densest scenes were putting a dozen boxes in a nine-tile
  clearing with nothing checking what was already standing there. Two faults,
  one pass, and both were invisible in a screenshot: a pile that size is not a
  find but furniture (the player stops reading silhouettes and walks the row
  pressing E, and the eight crate builds the pool exists to teach stop meaning
  anything), and two openables on one tile is a sprite inside a sprite over
  ground `_cells` can only claim once — the second one cannot be opened.
  Thinned centrally rather than in each builder because fifteen scenes roll
  containers and every one of them had the same bug; the order is shuffled
  first so the cap is not always paid by whichever loop ran last.
- **TWO VERBS, ONE KEY, AND ONLY THE BARRELS ANSWER A BULLET.** E is "use the
  thing in front of me" and the tooltip already said which — a barrel says
  destruir, a chest abrir, a car boot vasculhar. A bullet can break a barrel
  (its own per-type sprite box, not the foot tile); it cannot open anything,
  because a boot does not come open because somebody shot near it and one
  stray round popping every container on the map would delete the walk.
  Using an object frees EVERY tile it stood on — a vehicle claims four — and
  rolls empty, coins, or one item, which JUMPS out of the opening and lands.
  **AN EMPTY ONE SAYS SO OUT LOUD, ON EVERY VERB** — a dry hollow knock and a
  puff of air out of the opening. It used to be a gust on a break and silence
  on an open, which meant an opened chest that paid nothing was
  indistinguishable from a press the server dropped, and those are opposite
  feelings. The sound is well down the mix on purpose: it reports that nothing
  happened, and a disappointment as loud as a find teaches people to stop
  opening things. **The coin slice is the thinnest one on every object in the game**,
  because what an explorable is FOR is the item: that is what gets carried to a
  platform and becomes the group's balance, which is the number a night is
  scored on. Coins only once the exit is open, for the same reason the ground
  gets swept then — which makes the run for the exit the one stretch where dark
  gold really accumulates. Camp maps have none. Interact is loot, then object,
  then ready.
- **AND SOMETIMES SOMEBODY IS STILL IN THE CAR.** A vehicle has an ambush
  chance, rolled independently of its loot, and what comes out arrives already
  hunting whoever opened it. It is the cheapest story the map has and it is
  what makes opening the third car of the night a decision instead of a chore.
- **THERE ARE NO BUILDINGS AND NO LIGHTS IN THE WOODS.** The abandoned cabin,
  the tents and the campsites are gone, and so is every lamp and ember a scene
  used to leave burning. A procedurally dropped house teaches "house = loot"
  inside two expeditions, after which the forest is a list of houses; and a
  fixed light on a dark map does the player's reading for them from across the
  level, before they have spent a step finding out what is under it. Only the
  party's own lamp, the merchant's torches and the extraction pad's beacon
  burn now — and world lights LIGHT WITHOUT EXPLORING, so nothing but a player
  can leave a permanent mark on the map or the minimap. A silhouette in the
  dark that could be a tree, a car or a body is worth more than any of the
  three would be lit.
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
- **TWO LANDMARKS, AND THEY ARE THE TWO KINDS OF PLACE THIS FOREST HAS.**
  Both are one per map, both are placed first and alone (see *Server
  contracts*), and between them they say the only two things about this wood
  that are not "somebody died here": somebody BUILT something, and something
  LIVES here.
- **ONE LANDMARK, AND IT IS THE ONE THING SOMEBODY BUILT.** The `sanctuary`:
  carved stone in a ring — totems, idols, a robed figure, a skull post, a
  monolith — with bones on the floor inside it and an ALTAR in the middle
  whose slab grinds aside. It is the only scene made of vertical shapes in a
  forest of low horizontal wrecks, the only one arranged in a circle, and the
  only one that states its bargain before the player commits: guaranteed loot
  off the best rarity table in the game, and a pack of creatures already
  standing on it. A landmark that was worth more AND safer would be an errand,
  not a decision.
- **AND ONE THAT NOBODY MADE.** The `den`: trunks dragged into a lee, a floor
  of bones denser toward the middle, clothes and blood running OUT along a
  drag mark, and the miniboss asleep in the hollow (`mapgen.DEN_SCENES` →
  `Room._seed_nests`). It is the first scene on this map that is not about
  people at all, and everything in it is aimed at that being readable before
  the shape in the middle resolves: nobody made it, nobody left it, the trail
  points at where the thing hunts rather than at where somebody was going.
  - **IT IS THE ONE PLACE THAT POINTEDLY GETS NO LIGHT.** A `SceneLight` makes
    a place a destination you choose from across the dark, which is exactly
    right for the shrine and exactly wrong here. The whole encounter is that
    **your lantern reaches further than the animal's ears do** — so the lamp
    is what finds the den, and finding it is what carrying the lamp lit was
    for. A den with an ember on it would have done the player's reading for
    them and handed them the decision already made.
  - It pays the second-best scatter in the game and always pays, because the
    bargain has to be worth the animal — but not the best, because the shrine
    is where a run is ROUTED and the den is a thing it walks past. See
    [`enemies.md`](enemies.md) § The miniboss for what is asleep in it.

- **A forest night has a coat.** `night_clock()` rolls the hour; weather
  (`clear` / `rain` / `fog`) rolls with it so day 2 can feel like somewhere
  else without a new map. Rain is a looping bed plus streaks in the lantern.
  Camp is always clear.

---

## Server contracts

- Zone rules are enforced HERE, not just described to the client. A
  non-hostile zone runs no spawn director and drops the GUN half of
  `handle_attack`. A client that ignores `zone.lantern` gets light it cannot
  act on, which is the acceptable half of the trade; one that ignores
  `zone.hostile` gets nothing.
- **`zone.hostile` gates the gun, not the swing.** The rule it encodes is
  "weapons fire here", and a knife does not fire — no range, almost no
  noise, nothing that can go off across a clearing by accident. So the blade
  works at the campfire and that is deliberate: it makes the camp a place
  rather than a menu. Anyone killed there is respawned onto their own seat
  by the normal `respawn` path, and `embark` revives whoever was still down
  when the party left, because the walk-out puppets bodies instead of
  ticking respawn timers.

- **A scene is the unit of placement, never a prop.** `scenery.py` places
  GROUPS with fixed internal relationships — a tent, a cold firepit and the
  boot prints leading away from both — because the relationship is the whole
  content. A prop scattered on its own is texture, and texture is the client's
  job off the map seed. Adding "one more object type" that places itself
  individually here is the mistake this module exists to prevent; add a scene.
- Scenes run AFTER `_connect`, never before: they need boxes of open ground and
  connectivity is what decides which ground is open. A scene may CLEAR up to
  `scenery.CLEARABLE` of its plot (rock and tree only — never FIRE, VOID or
  another scene's building), which only adds floor and so cannot disconnect
  anything. Standing pieces claim tiles from `FOOTPRINTS` — derived from the
  piece's contact point, never listed per-scene — and those can cut a path, so
  `_stamp` re-checks reachability from the player origin and REVERTS on
  failure. Never drill: a corridor cut through a parked lorry to keep the map
  connected is a map with a hole in a lorry. `_seal` puts back scrub whose
  clearing left an orphan tile of floor; both generators leave sealed pockets
  in their own treelines and those are not ours to tidy.
- The connectivity check is a SET from a point that matters (spawn clearing,
  camp fire), not a count from the first floor tile in scan order. A camp
  treeline pocket is two tiles and is the first floor the scan finds; a count
  that starts there answers no before an object has landed. Containment, not
  totals: clearing one pocket while a fence orphans another cancels in a
  count. The reachable set is carried across attempts — a flood of the whole
  map per try is most of what generation costs.
- Scene placement never touches the `BORDER` treeline, which is what keeps the
  camera from framing the end of the world.
- VEHICLES and STATUES claim `world.PROP` (solid, sight-blocking), and that is
  a gameplay decision rather than a physical one: you lose a creature behind a
  bus, and a ring of totems is a ring of blind corners, which is most of what
  makes the shrine expensive. Waist-high cover — fences, signs, barrels,
  boxes, logs — claims `world.LOW`: solid to bodies and bullets, transparent
  to light. Making those PROP puts a shadow wedge behind every barrel and
  turns a fence into a wall of black. Firepits stay walkable. Objects are then
  pulled off the scenery list (`crates.attach`) so using one can `set_tile`
  every cell it held back to FLOOR. `Navigator` must `invalidate()` when a
  tile opens.
- **A standing thing is solid on one tile of height, at its feet.** Trees,
  signs, tents, buses, totems — the canopy, the board, the roofline are drawn,
  not walked into. `FOOTPRINTS` depth is 1 and `_cells` sits on the contact
  point; growing the box up the sprite is how a signboard becomes a wall.
  TREE is the same contract: the trunk tile only.
- The LANDMARKS (`scenery.LANDMARKS` — the tribal `sanctuary`, then the wolf
  `den`) are placed first, in order, alone, with a much larger attempt budget,
  and there is at most one of each per map. Rolled in with the weighted pool
  they lose every anchor race to a 4x3 woodpile; a second one of either turns
  the first from a place into a prop. **The FIRST one that lands is what the
  thread routes to** (`landmark_at`), which is why the shrine is listed first:
  a run has one place it is walking toward, and the den must not be able to
  take over the shape of a night. It is the one thing out here
  somebody BUILT rather than abandoned, the only scene made of vertical carved
  shapes in a forest of low horizontal wrecks, and the only one that states
  its bargain in props before the player commits: guaranteed loot on an altar
  rolling off the best rarity table in the game, with a pack already standing
  on it (`mapgen.NEST_SCENES` → `Room._seed_nests`). Nests are the only
  creatures placed rather than spawned by the director, because a place has to
  be dangerous whether or not anybody has walked to it yet.
- **A NEST ROW NAMES A COUNT, AND MAY NAME A TYPE.** Three kinds:
  `NEST_SCENES` (0 = "the landmark's guard", sized by `room.NEST_PACK`),
  `HAUNT_SCENES` (one or two of whatever the director spawns, standing in the
  wreck that killed them), and `DEN_SCENES`, which is the only one that says
  WHAT. The first two are about people and people are interchangeable; a den
  exists BECAUSE of the animal in it, so it names a type key and
  `_seed_nests` spawns a creature the spawn table has never heard of. It also
  places it dead centre rather than scattering — the bones are laid denser
  toward the spot it is lying on, and a miniboss rolled two tiles into the
  treeline is a hollow with nothing in it.
- **`populate` returns a `Population`, and half of it is not on the wire.**
  `props` and `lights` ship; `scenes` (now `PlacedScene` with a kind) and
  `route` are where things ended up in tiles and the order the thread walks
  them. They are kept because EXTRACTION wants exactly that: a set of places
  worth standing in, and a direction leading away from spawn. Loot is a
  second pass over `scenes` (`loot.scatter`) — a drop belongs to the place
  it sits in, not to a hash. Do not delete them for being unused.

- **THE OBJECTS ARE A VOCABULARY, AND `crates.py` IS THE DICTIONARY.** The
  module and the wire still say `crates` — history, like `rifts` — but the
  list holds barrels, eight wooden crates, supply boxes, ammo cases, chests,
  mailboxes, suitcases, freezers, bins, toolboxes, six kinds of abandoned
  vehicle, and the shrine's altar. Everything that separates one from another is a row in
  `crates.TYPES`: its sheet and sheet row, its VERB, its prompt, its footprint
  and hit box, its drop table, the catalog TAGS its item roll leans on, its
  rarity curve, and its AMBUSH chance. The whole table ships in
  `welcome.config.objects`; the client has no list of its own.
- **THE CRATE SHEET IS THE ONE PLACE THE ART CARRIES THE TABLE.** Everything
  else in the vocabulary says what it IS and nothing about what is in it — a
  barrel is deliberately anonymous, and all three roll off much the same odds.
  The eight crates say what has HAPPENED to them, in silhouette, from as far
  as the lantern reaches: reinforced and ironbound stand tall with battens and
  straps and hold the best wooden tables in the forest; broken, rotted and
  collapsed are notched, low and mossy and hold almost nothing. That is a
  table the player can read before committing to the walk, which is the only
  reason to draw eight of a thing instead of one. `scenery.CRATE_POOL` keeps
  the three clean builds to a third of the pool on purpose — the wrecks are
  what teach the shapes, because they are the ones you keep seeing, and a
  forest where the good silhouette was common would make the reading pointless.
- **TWO VERBS, ONE KEY, AND ONLY ONE OF THEM ANSWERS A BULLET.**
  `{type:"break","id"}` is "use the thing in front of me" — from the input's
  point of view that is one intent, and the prompt already said which it
  would be. A BREAK object (the barrels) can also be shot: `crates.along_ray`
  tests each type's own sprite box, so a car is four tiles of target and a
  toolbox is one. OPEN objects skip that ray entirely — a boot does not come
  open because somebody shot near it, and one stray round popping every
  container on the map would delete the walk. Reach is measured feet to the
  nearest point of the FOOTPRINT (`crates.nearest`), because a bus is four
  tiles long and a centre-to-centre reach refuses the prompt at exactly the
  doors the art is pointing at.
- Using one frees EVERY tile it stood on (`Crate.cells`) — a vehicle claims
  four, and freeing only the contact tile leaves three invisible walls.
  `Navigator` must `invalidate()`. Walk-out refuses; camp maps have none.
  Outcomes come off the type's own table: empty (the client plays wind on a
  break), coins, or one catalog item rolled with that object's tags and rarity
  curve. A chest and an altar have no empty weight at all — they are the only
  objects guaranteed to pay, which is what the domed lid and the ring of
  statues are advertising from across a clearing. During the BLACKOUT
  `roll_drop(items=False)` folds the item weight into COIN, so nothing puts a
  fresh item back on a map `_clear_loot` just swept; folded into coin rather
  than into empty on purpose, because what changes is what falls out, not
  whether anything does. That fold makes the run for the exit the one stretch
  of a night where dark gold really accumulates, which is the place for it:
  every coin table on the way in is deliberately thin. Noise is per type (`ObjectType.noise_tiles`) — a
  mailbox and a lorry bonnet are not the same event.
- **AND SOMETIMES SOMEBODY IS STILL IN THE CAR.** `ObjectType.ambush` is
  rolled in `Room.smash_crate` AFTER the loot and independent of it, so a boot
  can hold a medical kit AND a passenger; `Room._ambush` places the creature
  already committed to whoever opened it. It is the cheapest story the map has
  and the reason opening the third car of the night is a decision rather than
  a chore. The remaining list rides `welcome`/`map.crates` and a dirty
  snapshot `crates`; `crateBreaks` carries the type key `t` (the object is
  already gone from the live list, so the client has nothing left to ask), the
  outcome, and `amb`.

- **The thread is what makes it one story instead of seven.** `_route` orders
  the placed scenes by distance from spawn so the narrative reads OUTWARD and
  ends at the landmark; `_thread` lays prints between them with blood
  escalating leg by leg and a drag on the last one. Prints that land on
  anything but floor are DROPPED, not moved: a trail that breaks at a thicket
  and resumes on the far side is what a real one does, and one that bends
  around every trunk to stay visible reads as a drawn line. The camp gets no
  thread — it is firewood around a fire, and a blood trail through it is the
  wrong promise.
- **NO FOREST SCENE IS LIT.** `SceneLight` still exists and the STORE still
  uses it — the merchant's torches are navigation in the one zone with no
  lantern — but nothing in the woods emits one any more. A fixed light on a
  dark map does the player's reading for them from across the level, through
  the treeline, before they have spent a step finding out what is under it,
  and the darkness is the only real inventory of tension the game has. The
  client backs it up: world lights LIGHT and never EXPLORE (`render/fov.ts`
  `burn`), so nothing but the party can leave a permanent mark on the map or
  the minimap. `BEACON` is the extraction pad — its torch from the moment the
  map is built, its deck once the console is pressed — and it is the
  deliberate exception, because the pad IS the objective.
- The camp draws from `CAMP_POOL`, not `SCENES`: firewood and a sign, nothing
  that bled, and no containers. It is the one non-hostile zone, and a last
  stand outside the tent the party is about to leave from is a promise the
  zone does not keep. Camp scenes also keep clear of the hearth and the exit
  mouth — the same two places the decoration mask and the walk-out already own.
