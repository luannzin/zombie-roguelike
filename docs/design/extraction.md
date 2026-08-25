# Extraction — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).
Whole-system map: [`ARCHITECTURE.md`](../../ARCHITECTURE.md).

| | |
| --- | --- |
| **Owns** | extraction pads, the pour, the pickup call, the siren, the carved exit, the run's quest chain, and both edge corridors |
| **Inputs** | `{type:"activate","id"}`, movement (walks out of a pour), damage (ends a pour), day number |
| **Outputs** | `rifts` geometry rows + `riftStates`, `pours` events, `quests`, `tilePatches`, `map.entrance`, `hunt_all` on every enemy, `Room.enter_store` |
| **Depends on** | `inventory.py` (what a pour tips), `loot.py` (catalog value), `mapgen`/`scenery` (where pads plot), `ai.py` (`hunt_all`, `startle`), `entrance.py` (corridors) |
| **Consumers** | `quests.py`, `store.py` (the night's takings), `coins.py` (blackout fold), the whole client extraction stack |
| **Authoritative** | pad state, `Rift.fed` / `cargo` / quota, pour progress, egress open, exit crossing, day advance |
| **Presentation** | drones, ropes, lamps, rotor wash, the ground-break burst, the chevron, the pile on the deck |

## Invariants

- **A NIGHT ENDS ONE WAY: THE PARTY SPENDS THE LAST PAD.** There is no clock
  and no deadline — see *No clock* below before adding one.
- **One awake pad at a time.** `Room._awake_rift` refuses a second console.
- **A pour is server-clocked.** One item leaves the pocket per `rift.POUR_BEAT`; the client draws what the server already spent. Never empty a pocket in one call.
- **A pour is a commitment.** Nothing but damage ends it: movement keys are acked and ignored, and there is no ceiling — the press tips the WHOLE bag in, on either side of the quota.
- **The overpay core only exists while a next console exists** (`Room._pads_left`); both halves of that rule move together.
- **Nothing client-side settles anything.** The client animates; `Room` owns pad state, the sweep, and the balance.
- **`rifts` on the wire is history, not a second mechanic.** The module is `rift.py`; the thing is a cargo platform.

## Danger zones

- `Room._step_pour` / `_tip_item` — the pour's clock. A change here desyncs bag against deck.
- `Room._free_deck` vs SPENT — two separate beats, seconds apart, on purpose.
- `entrance.carve` / `open_exit` — `flare` selects the depth AND the connectivity question (`_walkable_connected`, not `maps.count_reachable`).
- `_close_extraction` ordering: sweep, egress carve, blackout, `hunt_all` are one beat.


## No clock

- **A NIGHT HAS NO DEADLINE, AND THAT IS A DECISION THAT HAS BEEN MADE TWICE.**
  The blackout fires when the party spends the LAST pad and at no other time.
  A countdown was built and then taken back out: rolled per night, announced,
  drawn top-centre, closing extraction through this same door at zero.
- **WHY IT CAME OUT.** On paper it fixed a real hole — without it, waiting
  costs nothing, so clearing the whole forest slowly is strictly the best line.
  In the hand it changed what the game is ABOUT. A visible countdown makes
  every decision a scheduling decision: the player stops reading the forest and
  starts reading the clock, and the pressure that arrives is administrative
  rather than frightening. This game's dread is supposed to come from what is
  in the dark with you, not from a number in the corner telling you to hurry.
- **THE HOLE IT WAS AIMED AT IS REAL AND IS NOW THE CROWD'S JOB.** Thoroughness
  should cost something — but the honest cost of staying out is that the forest
  keeps filling up (`ENEMY_DAY_RATE`, `ENEMY_DAY_POPULATION`) and a crowd can
  now kill, so the longer a party works a map the more of it is standing behind
  them. That is a deadline the player reads by LOOKING AROUND, which is the
  version this game wants. If lateness needs a sharper cost later, put it on
  the population curve before reaching for a timer again.

## Change surface

| intent | touch |
| --- | --- |
| pad timing, quota, overfeed | `server/app/rift.py`, `server/app/config.py` |
| pour mechanics | `server/app/room.py` (`_begin_pour`/`_step_pour`/`_tip_item`), `server/app/inventory.py` |
| quest rows | `server/app/quests.py`, `server/app/room.py` (`offer_*`/`step_quests`) |
| corridors, the exit | `server/app/entrance.py` |
| pad/drone visuals, deck load | `client/src/render/layers/rift.ts`, `client/src/render/platform.ts`, `client/src/game/pad-cargo.ts` |
| the skid's art | `server/tools/make_platform.py` — never the PNG; `pad-cargo.ts`'s floor fractions mirror its deck |
| exit UX | `client/src/game/exit-guide.ts` (screen pose), `client/src/game/exit-path.ts` (the route it points down), `client/src/components/hud/ExitGuide.tsx`, `client/src/render/rift.ts` (paving/torches) |
| the prompt | `client/src/components/hud/RiftPrompt.tsx`, `client/src/game/interaction.ts` (`riftPrompt`, `nearRift`) |

**Do not touch from here:** economy settlement (`Room.enter_store`), inventory
authority (`server/app/inventory.py` slot rules), the wire protocol pair, or
`store.py`'s pricing.

---

## The loop this sits inside

- A run is an **expedition loop**, and after the first lap it is a CYCLE OF
  TWO: forest, shop, forest, shop. `Preparação` is where a run BEGINS and
  nothing more — the party readies at the fire once, files through the black
  exit once, and a second `welcome` drops them in a VOID corridor on a random
  edge of the forest (the camp exit, continued). They walk out of it; the woods
  swallow the way back. Then the first objective appears: find the extraction
  point. From then on the SHOP is the place between nights: walking out of it
  goes straight to the next day's forest, through the same hand-off leaving the
  fire uses. **The run never goes back to the camp** — the shop already resets
  the party (spend, re-arm, a fire to stand at), and sending them home
  afterwards made them ready up a second time for a decision they had just
  made.

## The pads, the pour, the pickup, the way out

- **EXTRACTION is the core loop, and a night's pads are a QUEUE.** The
  extraction point is an abandoned CARGO PLATFORM: a rusted iron skid open at
  the front, still half loaded with crates nobody came back for, with four
  corner lamps. A console stands in front of it and a torch — the same torch
  the exit corridor wears — burns beside that console from the moment the map
  is built, because a landmark you can only see once you have found it is not
  a landmark. The platform's own tiles are SOLID: it is cargo space, and the
  party may not get on it. **THE DRONES ARE NOT PART OF THIS STRUCTURE.**
  Nothing is parked at the corners; the pad is a loading dock, and four
  aircraft come in from one treeline when somebody calls for a pickup.

  **THE SKID IS SQUARE TO THE SCREEN, AND IT IS THE ONLY THING IN THE FOREST
  THAT IS.** Every prop out there — crate, barrel, fence post — is yawed 45
  degrees onto the diagonal `objects.box` camera, and the pad was too. Three
  things followed from that and they compound: the object OCCUPIES an
  axis-aligned rectangle of tiles, so the art was a diamond standing on a
  rectangle and everything derived from the footprint (the solid tiles, the
  imprint, the dent pattern) disagreed with the silhouette; corner-on there is
  no square face anywhere, so the tallest thing on the prop was twenty-six
  pixels of slanted edges with nothing to carry its height; and a cargo skid is
  ENTERED, but corner-on the opening faced the lower-left of the screen and the
  player walked into a corner of it.

  So it is built like the shop's masonry — a face and a cap, square to the tile
  grid — on the same camera slope, the same 135-degree key and the same
  painter. ARCHITECTURE IS AXIS-ALIGNED IN THIS GAME AND PROPS ARE CORNER-ON.
  What that buys is the read: a full-width front face that says "raised deck",
  a deck you can see the load standing on, three walls at three heights that
  make it a well rather than a table, and an open front with a hazard-striped
  ramp down the middle of it — facing the console the player is already
  standing at. The way in is the front, and now it looks like one.
  - **THE QUEUE IS ORDERED BY DISTANCE FROM THE DOOR, AND THE FIRST PAD IS
    NEAR IT.** It used to sit at `route[-1]`, the far end of the story thread,
    which read well on paper — out along the trail, back with your pockets
    full — and cost the night its opening. The party arrives with an EMPTY BAG:
    a first console two minutes' walk away is an objective nobody can act on
    yet, so the walk out was spent finding a machine with nothing to give it,
    and the first thing the run ever asks for landed after the first thing it
    makes you do. The first platform stands a clearing out from the arrival
    mouth now (`rift.NEAR_SPAWN_CLEARANCE`, far enough to clear the corridor
    and its avoid radius): found almost at once, loaded with whatever the walk
    turned up, and the night works OUTWARD from it. The trail is not lost, it
    moves down the queue — the SECOND pad takes `route[-1]`, and on a five-pad
    night the rest go as far from spawn as the clearances allow.
  - The module is still called `rift.py` and the wire still says `rifts`. That
    is history, not a second mechanic: the extraction point used to be a tear
    in the world with stones around it, and renaming twenty client files buys
    nothing this line cannot say. `assets/processed/rift/` still holds that
    art — the pad borrows its CONSOLE and its TORCH and nothing else.
  - After the entrance seals, the HUD quest `Encontre o ponto de extração`
    ticks `0/N` when a console is pressed (`quests.py`). Day 1–2 spawn one pad;
    day 3–4 two; day 5+ three (`rift.count_for_day`). That count also SIZES
    THE MAP (`mapgen.size_for_pads`, see [`world.md`](world.md)): ground per pad
    is constant, so a one-pad night is a third of the forest rather than the
    full one with two thirds of nothing in it. **Only one platform may
    be awake at a time** — a second console refuses while another is running,
    so three pads is three walks rather than an errand list a party splits up.
    Each pad carries its OWN quota (`rift.pad_need`, the night's bill divided
    between them) and its own `Carregue a plataforma` row (catalog gold from
    the pocket — guns stay on the belt — the HUD draws the coin badge).
  - **LOADING IS A CEREMONY AND IT IS THE SHOT THE WHOLE NIGHT IS FOR.** E on
    an open pad does not spend anything: the character WALKS to a mark in front
    of the skid, turns to face it, takes the backpack off their shoulders,
    turns it upside down, and tips it out. The items come out one at a time,
    arc over the front lip and land on the deck, where they STAY — a pile that
    grows all night, that nobody can pick back up, and that goes up with the
    platform when the drones take it. Then the pack goes back on. Every item
    leaves the pocket on the frame it leaves the bag, because the server owns
    that clock (`Room._step_pour`); a bag that emptied instantly under an
    animation would be visibly still full and already spent. THE PRESS IS THE
    COMMITMENT: it goes on until the bag is empty, whether that settles the
    quota or overshoots it, and a movement key does not take it back. It used
    to — and what that bought was the most expensive verb in the game being
    undone by the key players hold down most, plus a load that stopped on the
    bill and left somebody standing at a machine they had already committed to
    still carrying half the night. Being hit still ends it: something eating
    you while your pack is open is the one interruption that is not the
    player's own fumble.
  - **THE NIGHT'S BILL IS A SHARE OF WHAT IS ACTUALLY OUT THERE.** A forest
    holds a MEDIAN of about 910 points of findable value — roughly a third of
    it scattered on the ground, the rest inside the forty-odd objects standing
    on it — and `rift.night_need` is set against the LOW quarter of that
    spread rather than the median, so a bad roll makes a night hard and never
    impossible. Day 1 asks 40 (under five per cent, and that whole take is the
    budget that buys the first gun); day 5 asks 248 across three pads; day 10
    asks 448, which is the night the walk stops being optional and the shrine
    stops being a question. Moving a number in `loot.SCENE_COUNTS`,
    `crates.TYPES` or `mapgen` moves how many nights a party survives — the
    two ends are one decision.
  - **THE LAMPS ARE THE STATE.** Pressing the console powers the deck and the
    four corner lamps come up GREEN: found, running, safe to load, and nothing
    out there has heard anything. The quota is a FLOOR, not a ceiling — E on a
    paid pad keeps loading while the pocket has anything. The console goes
    GOLD the moment the quota lands and throws a rainbow band (`aura.png`)
    until somebody calls the pickup. Green means loading. Red means the
    aircraft are coming. There are no overfeed tiers and the drones are not a
    meter.

    **THE CORNERS THROW LIGHT, AND FOUR SHEETS ARE ONE BUDGET.** `make_platform`
    bakes the three states into the skid, so the housings change colour on
    their own — and a lamp that changes colour and throws nothing is a PAINTED
    lamp. Across a dark clearing four coloured pixels are not what says the
    platform is live, so each corner also blits its own additive glare sheet
    (`standby.png` green, `siren.png` red) riding the deck, which means they go
    up with the platform rather than staying behind in its hole.
    They overlap, `lighter` does not clamp and bloom sits on top, so they are
    judged as a SUM over the deck and never one lamp at a time: this layer was
    deleted once because at full strength the four of them made a white
    rectangle the size of the skid. `layers/rift` holds each at `LAMP_GLARE`
    0.55 (`LAMP_ALARM_GLARE` 0.68), so four at once land near one lamp's worth
    and the deck's own banding survives underneath. There is NO air halo — a
    gradient with no shape in it cannot say where light comes from, and all it
    ever did was flatten the hazard paint.
  - **E on a paid pad with an empty pocket CALLS THE PICKUP**, and that is the
    most expensive press in the game. The lamps go RED and start sweeping as
    sirens. `Room._siren` throws a map-wide noise every `SIREN_PULSE`, and
    `hunt_all` puts every creature on the map on hunt for the whole thirteen
    seconds that follow — the party cannot leave and cannot take it back.
    Sirens alone first (`LIFT_ALARM`); then four drones come in as a GROUP
    from `rift.approach`, stagger off the treeline, split onto the four
    diagonals, and each pays a line down to its eye. The lift waits until the
    LAST rope is tied. Then three beats (`LIFT_STRAIN` / `LIFT_BREAK` /
    `LIFT_CLIMB`): rotors to maximum with the skid rattling in its own hole
    and not moving, because the beat that says HEAVY is the one where nothing
    happens; the ground lets go (dirt burst, camera shove, deck tiles patched
    back to floor, `imprint.png` uncovered); then up and away along a heading
    the map rolled at placement, accelerating, shrinking and fading. Everything
    paid past the quota comes back as ONE condensed core (`rift_shard`),
    dropped in the middle of that imprint, with value, weight and drawn SIZE
    proportional to the overpayment. That is what overfeeding buys: four slots
    of loot become one you carry to the next console, at a weight that costs
    real walk speed. On the LAST pad of the night there is no next console, so
    no core is paid and the game stops offering to keep loading at all.
  - Calling the LAST pad carves a new exit on a random edge, kills every
    lantern, puts the whole pack on hunt (`Encontre a saída`, risk), and
    SWEEPS EVERY REMAINING DROP OFF THE MAP. Extraction is what loot was for;
    with no console left to load, a bottle in the grass on the way out is only
    a reason to stop moving while the pack hunts. Coins still fall and still
    count — they are gold, not cargo.
  - **THE PACK REACTS OUTWARD FROM THE PAD, AND THE PAUSE IS THE MESSAGE.**
    `hunt_all` commits every creature on the map on one frame, and a hundred
    bodies that all start walking together reads as a switch being thrown. So
    a creature the alarm reaches TURNS TO FACE THE PLATFORM and stands
    (`ai.startle`) for a beat scaled by how far the sound had to travel — near
    ones snap round first, distant ones a moment later. It is hunting the whole
    time, so the diamond is already lit: what the player watches from the
    console they just pressed is every mark in the clearing come up, hold, and
    then start moving toward them in the order the noise reached them. The
    snarls are queued client-side and drained nearest-first for the same
    reason — eight of them stacked on one tick is a wall of noise that says
    nothing about how many there are or where they are.
  **THE WAY OUT IS FOUND, NOT FOLLOWED, AND THAT IS THREE CHANNELS.** The exit
  is a VOID corridor carved on a random map edge — the same dark gap as the
  camp exit, and its outer end FLARES so it is a visible hole in the border
  treeline rather than a crack. The threshold is DRESSED: four torches in two
  ranks of two, and cut paving with light in its seams. A slow spatial PING
  sounds from the mouth every few seconds, and that is the channel that still
  works while the player is facing the other way.
  **THERE USED TO BE A FOURTH: a COLUMN of light thrown straight up over the
  trees**, drawn in world space so finding it was a matter of looking. It was
  the best of the four and it is gone, because it was drawn off `world.egress`
  and the STORE has an egress too — its north corridor. A party walking into
  the merchant's clearing shortly after calling the pickup got a flaring pillar
  of light standing in the exit of the one zone with nothing to navigate. It
  was deleted rather than special-cased: a world marker that has to ask which
  map it is on belongs to the map, and the exit already had three channels.
  The gold HUD chevron (`/hud/chevron.png`) is the third and it BLINKS: a long
  solid burst on the frame the exit is carved, then dark, then a couple of
  seconds every few, for as long as the way out is uncrossed. It was permanent
  once, which meant the world never had to say anything — a marker that answers
  "which way out" forever turns fire burning over a black forest into
  decoration. Then it faded out after ten
  seconds, which left a party that turned the wrong way at second twelve with
  nothing to ask. Pulsing is both: the map does the work most of the time and
  the glass is there when somebody has lost their bearings. It is a solid
  TRIANGLE rather than the thin dart on `arrow.png`, because what the eye
  catches in a half-second flash is area, not line.

  **AND IT POINTS DOWN THE ROUTE, NOT AT THE EXIT.** It used to be a compass —
  a bearing straight from the player to the corridor's back point — which is
  the right answer on open ground and the wrong one in a forest of trunks,
  boulders and scenery. Players followed it into a thicket, decided it was
  broken, and stopped reading it during the one sequence in the game where
  nobody has time for the minimap. `game/exit-path.ts` floods the map outward
  from the mouth once, giving every reachable tile its distance to the exit,
  and the chevron walks a few tiles downhill from wherever the player is and
  aims at where that walk ends up. A FIELD, NOT A PATH: a path is per-player
  and dies the moment somebody steps off it, a field answers everyone with two
  array lookups and degrades correctly — a tile the flood never reached gets no
  answer and the old straight bearing takes over, which is the one case where
  "that way" beats nothing.

  The quest row is an ORDER now and not a task — "A saída abriu — corra". The
  platform left, every lantern on the map died, every drop was swept and the
  whole pack is hunting; "find the exit" is the same grammar as "find the
  extraction point" and this moment is nothing like that one.
  Crossing that corridor ends the night — but it does not go home yet. It opens
  on the **STORE**, and the day increments on the way out of THAT.
  Extraction pads are on the
  MINIMAP: dormant ones once their ground has been explored, awake ones
  always, gold once their quota is paid, and RED and breathing on the siren's
  own beat once the pickup has been called. The world is already laid out for the
  walk — `server/app/scenery.py` returns the ROUTE its scenes are strung
  along (outward from the mouth ending at the landmark), `SceneLight`/
  `BEACON` is the channel a beacon arrives on, and the boot prints
  players leave behind are navigation for the trip back.

---

## Server contracts

- **Quests are authoritative and room-wide.** `quests.py` owns the list;
  the HUD mirrors it (`have`/`need`/`done`/`risk`/`gold`) and never invents a row.
  Dropping a quest from the list is how it leaves the screen. Forest chain:
  find every pad (`extract`, `0/N`, offered the tick the entrance goes
  `gone`, ticked when a console is pressed), load the running platform
  (`feed`, catalog gold from the pocket — the row carries `gold` so the
  HUD draws the coin), then run for the carved exit (`exit`, `risk`).
  There is only ever ONE load row, because there is only ever one awake pad:
  it carries THAT pad's quota, is dropped when the pad launches, and a fresh
  one goes up at the next console. Its `have` is allowed PAST `need` while
  staying done — the overshoot is the size of the core coming out the far
  end, and clamping it hides the only number that says so.
  The exit is a VOID corridor on a random map edge (`entrance.open_exit`),
  the same shape as the camp walk-out. VOID is walkable only while
  `world.egress` is set; camp and the forest arrival stay solid. The
  quest ticks when a living player stands on VOID past the FLOOR mouth
  (`EXIT_CROSS_TILES`), not on proximity to the threshold. Launching the LAST
  pad opens egress, blackout, and panic-hunt.
  Crossing the corridor takes the party to the SHOP (`Room.enter_store`), not
  home. Do not auto-remove a row on complete — ticking `need/need` is the
  check. Camp has none.

- **The extraction point is a CARGO PLATFORM, and `rift.py` is its historical
  name.** An abandoned iron skid with four corner lamps, a console in front of
  it, and a torch beside that console burning all night. THE DRONES ARE NOT
  PART OF THIS STRUCTURE and the server ships no position for them: they
  arrive from off-map along `approach` when the pad calls, take a corner each
  in the DIAGONAL order the art uses, and are gone with the platform. Waking
  the pad powers the deck and the lamps go GREEN. Calling the pickup turns
  them RED, starts a siren, and `Room._siren` plus `hunt_all` put every
  creature on the map walking toward the clearing for the whole thirteen
  seconds of the sequence (`LIFT_ALARM` / inbound / drop / strain / break /
  climb). `_stamp` makes the deck's tiles `LOW`: the party may not get on the
  platform, but a five-by-two block of sight-blocker in the one clearing they
  fight in would be worse than the thing it prevents.
- **LOADING IS A POUR, AND IT TAKES TIME.** `activate_rift` no longer spends
  anything: it starts a `Pour` on the player (`Room._begin_pour`) and the body
  becomes a puppet for the length of it. `Room._step_pour` runs four beats —
  WALK to a mark `rift.POUR_STAND` tiles in front of the deck, LIFT the pack
  off the back, DUMP one item every `rift.POUR_BEAT`, STOW it again — and
  `_tip_item` is the whole transaction, one unit at a time: `Inventory.tip_one`
  out of the pocket, `Rift.feed` into the pad, one `pours` event out to every
  client. THE PACING IS THE POINT. The client draws the sprites leaving the
  backpack, and a server that emptied the pocket in one call would leave a bag
  that is visibly still full and already spent. THERE IS NO CEILING — the pour
  runs until `Inventory.tip_one` comes back empty, so the quota is a number the
  load passes through rather than a number it stops on.
  `Rift.cargo` is the pad's running pile index and it rides the geometry
  payload, because two players watching one pour have to watch one pile.
  **A pour CAN be walked out of, and that reversed a decision.**
  `Room._puppet_inputs` acks every packet and obeys none of them except a
  MOVEMENT key, which ends the pour where it stands. It used to obey nothing at
  all, and the argument for that was real: a load undone by somebody leaning on
  W while watching the deck is the most expensive verb in the game lost to the
  key that is held down more than any other. What it missed is the forest. The
  press already threw a noise, the lamps are green, the clearing is lit, and
  the body is planted for several seconds — which is precisely when something
  arrives. A player who could see it coming and could not step off the mark was
  not making a decision, they were watching one be made for them, and "stand
  here and take it" is not a cost, it is an absence of play.
  **What keeps it a commitment is that the pour SPENDS AS IT GOES.** `_tip_item`
  moves one unit at a time, so walking away banks everything already on the pad
  and keeps everything still in the bag — there is nothing to refund and
  nothing to lose, only a load left unfinished and a console to come back to.
  That is the same fairness rule `_step_use` states from the other side: a heal
  is spent on the LAST frame precisely because what interrupts a heal is the
  thing you were healing because of. `damage_player` still ends a pour too.
  The client mirrors the cancel rather than waiting for it — `Game.tick` clears
  `localPour` on the frame a movement key goes down, because `liveInput` masks
  movement out of a pour packet and the server cannot cancel off a bit that was
  never sent.
- **One pad at a time, and the PLAYER calls the pickup.** `Room._awake_rift`
  is the gate: a dormant console refuses while another platform is charging or
  open. `activate_rift` is a four-way switch on the pad's state plus what is
  in the pocket — wake it, start a pour (one verb, on either side of the
  quota), or call the pickup with an empty bag. The bag is what disambiguates the last
  two on purpose: overfeeding is only a real choice if it is repeatable, and a
  press that called the aircraft the instant the quota landed would make
  keeping the bag going unreachable. `Rift.begin_collapse` banks the
  overpayment and `Room._drop_excess` pays it out on the tick the pad reaches
  SPENT, IN THE MIDDLE OF THE IMPRINT — on the ground the skid was sitting on,
  because the core is the thing that did not fit aboard, not a bag somebody
  put down near the console.
- **The deck's tiles are handed back on the tick the skid breaks ground.**
  `Room._free_deck` fires off `Rift.lifted` (`close_at + BREAK_AT`), patches
  those tiles to `FLOOR` on the wire and rebuilds the navigator. It is a
  separate beat from SPENT and seconds earlier on purpose: the map physically
  changes shape when the platform comes off it, and a party that watches one
  fly away and then walks into the hole it left is the only version of this
  that is not a lie. `Rift.freed` rides the geometry payload so a rehydrate
  does not re-free ground that is already free.
- **`_close_extraction` sweeps the ground.** `Room._clear_loot` empties
  `drops` on the tick the last pad is launched, alongside the egress carve and
  the blackout — one beat, one change of what the map is for. Loot existed to
  load a platform and there is no platform left, so the run home is a RUN and not a
  shopping trip with a horde behind it. Coins are NOT swept: they fall from
  kills on the way out and they are gold rather than cargo. The empty list
  rides the next snapshot (`payload["loot"] = []` when `loot is not None`, so
  "nothing left" is a message and not an omission) and the client's
  `replaceLoot` clears on it.
- **A core only exists while there is a next console to carry it to.**
  `Room._pads_left` (any pad still DORMANT) gates both halves of that rule:
  `_drop_excess` pays nothing on the last pad of the night, and
  `activate_rift` stops offering to keep loading there — paid means launched,
  whatever you are carrying. Without the second half the first is a trap: E on
  a paid pad loads while the pocket has anything, so a party would empty a full
  bag onto a platform that cannot pay it back on the way out.
- **`Drop` and `Slot` carry per-item overrides, and exactly one thing sets
  them.** Everything the world scatters is worth what its catalog row says,
  which is why the catalog ships once in `welcome.config` and the wire carries
  a key. A condensed core out of an overfed pad is worth whatever was
  overpaid, so `value` / `weight` / `scale` travel WITH the object — through
  the ground, the bag, a toss back onto the ground, and the tooltip. A slot
  carrying them never stacks: two cores worth 40 and 300 are not two of a
  thing, and merging them would have to invent a number for the pair.

- **`_tick_exit_quest` is one mechanic with two destinations.** A living body
  crossing the VOID at the end of the map sets `_pending_return`; what is on
  the far side belongs to the zone being LEFT, and `advance_zone` dispatches
  it — forest to store, store to the NEXT FOREST. The day increments in
  `depart_store` only: the shop is the end of the night just survived, not the
  start of the next one, which is why its card reads "Fim do dia N".
- **THE LOOP NEVER RETURNS TO THE CAMP.** `preparation` is where a run BEGINS
  and nothing more — the party gathers at the fire once, readies once, walks
  out once (`begin_depart` → `embark`). From then on the SHOP is the place
  between nights: it already resets the party (spend, re-arm, a fire to stand
  at), and routing them through an empty camp afterwards made them ready up a
  second time for a decision they had just made. `depart_store` is therefore
  the same hand-off `embark` is — both go through `_swap_map`, so leaving the
  merchant arrives in an edge corridor and seals behind them exactly as
  leaving the fire does. There is no `return_home`; do not add one back
  without a reason the camp has to exist mid-run.

- VOID (`world.VOID`) is a winding path of forest floor between trees.
  Camp and the forest arrival keep it solid — players bounce, and only the
  walk-out may puppet a body onto it. Once the last pad has flown, `egress` opens
  and VOID on that map becomes the walkable extraction corridor: find the
  dark gap on the edge and cross it. The carve wanders and frays; the
  client paints ground and crushes a darkness falloff around it.
- **The exit is MARKED, and the marks are why it can be found.** `open_exit`
  places four torches (`entrance._torches`, `TORCH_RANKS`): two ranks of two
  straddling the centreline, one rank out in the clearing and one inside the
  corridor, so the party walks between them. Two ranks rather than a pair,
  because a line of lights reads as a way through and two loose fires do not.
  They are drawn, never solid — the exit of a night like that one is the worst
  possible place for a collision surprise — and a torch whose tile is woods is
  pulled toward the centreline and then SKIPPED rather than forced, since a
  light with no visible source is worse than three torches. About one map in
  ten gets three. The client turns them into scene lights and lays paving
  around the mouth; only the contact points are on the wire.
- **The two corridors are read from opposite ends, so they taper differently
  AND they are different lengths.** An arrival is walked outward-in and then
  sealed, so its border ranks pinch to a crack (`EDGE_PINCH`), the treeline
  stays unbroken from inside, and its DEPTH (`ENTRANCE_DEPTH_TILES`, 12) is the
  length of the dark walk out of it — the point of it. An exit has the opposite
  job: the only thing on screen that can say "you found it" is a gap in the
  BORDER treeline, so `open_exit` carves with `flare`, which widens those ranks
  (`EDGE_FLARE`) and cuts them with almost no fray. It is also SHORT
  (`EXIT_DEPTH_TILES`, 5), because what the party sees appear is not its far
  end — that is off in the blackout — but its MOUTH, the floor threshold
  carrying the torches and the paving. At the arrival's depth that threshold
  landed twelve tiles inland and the way out read as having opened in the
  middle of the woods. `flare` is what selects between the two depths in
  `carve`, since only `open_exit` ever sets it.
- **An exit carve asks whether the map is connected WITH the corridor counted
  as walkable** (`entrance._walkable_connected`), not `maps.count_reachable`.
  The strict FLOOR-only flood is the right question while VOID is solid; it is
  the wrong one here, because an egress corridor only ever exists alongside an
  open `egress` and bodies may walk it. Asking it rejected any side whose path
  happened to cut a floor region in two — even though the path itself is the
  seam between the halves — and about one night in twenty came out with no way
  off the map at all. The arrival's side is also a preference now rather than a
  rule: it goes to the END of the try list instead of being struck off it.

- **THE PACK REACTS OUTWARD FROM THE PAD.** `hunt_all` commits every creature
  on the map at once; `ai.startle` is what stops that reading as a switch. A
  creature the alarm reaches turns to face `Room.alarm_point`, holds still for
  a beat scaled by its distance from it, and only then walks. It is hunting the
  whole time — the awareness is pinned and the client's diamond is already lit
  — so what the player watches is every mark in the clearing come up, hold, and
  start moving toward them in order of how far the sound had to travel.
