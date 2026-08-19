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

- **One awake pad at a time.** `Room._awake_rift` refuses a second console.
- **A pour is server-clocked.** One item leaves the pocket per `rift.POUR_BEAT`; the client draws what the server already spent. Never empty a pocket in one call.
- **A pour is always escapable** — a movement key or damage ends it and keeps what was already tipped.
- **The overpay core only exists while a next console exists** (`Room._pads_left`); both halves of that rule move together.
- **Nothing client-side settles anything.** The client animates; `Room` owns pad state, the sweep, and the balance.
- **`rifts` on the wire is history, not a second mechanic.** The module is `rift.py`; the thing is a cargo platform.

## Danger zones

- `Room._step_pour` / `_tip_item` — the pour's clock. A change here desyncs bag against deck.
- `Room._free_deck` vs SPENT — two separate beats, seconds apart, on purpose.
- `entrance.carve` / `open_exit` — `flare` selects the depth AND the connectivity question (`_walkable_connected`, not `maps.count_reachable`).
- `_close_extraction` ordering: sweep, egress carve, blackout, `hunt_all` are one beat.

## Change surface

| intent | touch |
| --- | --- |
| pad timing, quota, overfeed | `server/app/rift.py`, `server/app/config.py` |
| pour mechanics | `server/app/room.py` (`_begin_pour`/`_step_pour`/`_tip_item`), `server/app/inventory.py` |
| quest rows | `server/app/quests.py`, `server/app/room.py` (`offer_*`/`step_quests`) |
| corridors, the exit | `server/app/entrance.py` |
| pad/drone visuals, deck load | `client/src/render/layers/rift.ts`, `client/src/render/platform.ts`, `client/src/game/pad-cargo.ts` |
| exit UX | `client/src/game/exit-guide.ts`, `client/src/components/hud/ExitGuide.tsx`, `client/src/render/rift.ts` (paving/torches) |
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
  - The module is still called `rift.py` and the wire still says `rifts`. That
    is history, not a second mechanic: the extraction point used to be a tear
    in the world with stones around it, and renaming twenty client files buys
    nothing this line cannot say. `assets/processed/rift/` still holds that
    art — the pad borrows its CONSOLE and its TORCH and nothing else.
  - After the entrance seals, the HUD quest `Encontre o ponto de extração`
    ticks `0/N` when a console is pressed (`quests.py`). Day 1–2 spawn one pad;
    day 3–4 two; day 5+ three (`rift.count_for_day`). **Only one platform may
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
    animation would be visibly still full and already spent. Any movement key
    walks out of it and keeps what has already gone in, and being hit ends it —
    standing still for three seconds in a dark forest is a choice, not a
    cutscene.
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
  that is visibly still full and already spent. The CEILING is set once, at the
  start: under the quota a pour stops on the bill, at or past it there is no
  number to stop at and it takes the whole bag.
  `Rift.cargo` is the pad's running pile index and it rides the geometry
  payload, because two players watching one pour have to watch one pile.
  **A pour can always be walked out of.** `Room._pour_inputs` acks every
  packet and obeys none of them except a movement key, which ends the pour
  where it stands and leaves everything already tipped in the pad; taking
  damage ends it too (`damage_player`). Standing still for three seconds in a
  dark forest has to be a choice that can be un-made.
- **One pad at a time, and the PLAYER calls the pickup.** `Room._awake_rift`
  is the gate: a dormant console refuses while another platform is charging or
  open. `activate_rift` is a four-way switch on the pad's state plus what is
  in the pocket — wake it, start a pour toward the quota, start one past it,
  or call the pickup with an empty bag. The bag is what disambiguates the last
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
