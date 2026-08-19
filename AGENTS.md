# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- The hotbar is 3 cells above the battery (keys 1/2/3, same key holsters):
  two gun slots and then the knife. Guns collect onto the belt, not the
  pocket. The held sprite follows the mouse and flips when aiming left. No
  laser sight. The AWP zooms the camera out while holding to shoot. Tracers
  start at the barrel. Hit juice (blood, a small knockback, tilt) scales
  with the gun's damage. Repeated hits slow then stop the enemy's walk. Each
  gun has its own weight (slows the walk) and feel. EVERY SHOT SPENDS A
  ROUND out of a per-calibre reserve, and a dry trigger clicks and eats the
  cooldown. Guns are BOUGHT and never found.
- **THE WHOLE GUN CATALOG IS DERIVED FROM CS2'S STAT BLOCK, ANCHORED ON THE
  ZOMBIE** (`server/app/weapons.py`). Eleven guns, and not one hand-picked
  damage number among them: damage, cadence, reach, noise, weight and price
  are all functions of the published source table, scaled by
  `DAMAGE_SCALE = ZOMBIE_HP / 100` so **a zombie takes exactly what an
  unarmoured CS2 player takes** — four Glock rounds, three AK rounds, two
  Deagle rounds, one AWP round. The weakest creature in the game is the only
  thing a player ever measures a new gun against, so it is the unit, and a
  rebalance is one constant rather than twelve rows. CS2 balances its cheap
  fast guns with recoil and spread and a top-down hitscan has no wrist, so
  three axes carry that weight here instead: ROUNDS PER KILL (the reserve is
  sized in kills, so an upgrade buys a longer night rather than a bigger
  number), NOISE (the two suppressed weapons, USP-S and M4A1-S, wake barely
  half the forest — the `S` is the whole product), and WEIGHT (ported from
  CS2's own running-speed column). Do not add a hand-written number to that
  file; add a row with its source columns and let the functions do it.
- **A TRIGGER RESOLVES IN ONE OF THREE WAYS, and the catalog says which.**
  One ray is the default. `pellets > 1` is the SHOTGUN: one pull spends one
  SHELL and casts six rays across a fixed twenty-degree cone, so the pattern
  thins itself with distance — a shell kills a zombie outright inside two
  tiles, is a coin flip at three and never kills at four. That falloff is
  geometry, not a curve, which is why it reads without a tooltip and why
  walking one step closer is a plan. `fire_on_release` is the AWP: holding
  the trigger scopes and NEVER fires, and letting go is the shot — the only
  input in the game that is a sentence rather than a word, and what stops
  the sniper being a Deagle that reaches.
- The KNIFE is the last cell (key 3) and the one weapon that never changes:
  it cannot be picked up, swapped or dropped. **A run starts with it and
  with no gun at all.** It does not shoot — it swings a short arc that
  leaves a WHITE PATH, and the swings chain three deep: a slash, a slash
  the other way, and a cut. The cut is slower, wider and goes through more
  than one body. Its damage is a floor, not a benchmark: a whole chain is
  `KNIFE_CHAIN_SHARE` of ONE zombie and never all of it, so the blade always
  leaves you standing in front of something still alive with your cooldown
  spent. Quiet is the point of it, and the first gun in the shop has to stay
  worth saving for.
  It is drawn held IN against the body and a little smaller than the guns,
  because a blade at a pistol's extension reads as a sword floating beside
  the sprite.
- **THE BLADE FOLLOWS ITS OWN SLASH.** The held sprite runs the same easing,
  off the same `arcDegrees`, that the white path does — it is the leading
  edge of the arc, not a separate animation happening nearby. It starts
  cocked past the near lip (a wind-up that costs no latency: the swing still
  begins on the frame of the click), crosses the arc, thrusts the grip out
  along the blade at the middle of the sweep, carries past the far lip and
  is DRAWN BACK to rest. The two slashes cross because the second one sweeps
  the other way, and that handedness is never mirrored for a left-facing
  body. What this replaced was a recoil spring wearing a knife: the sprite
  tilted up by a fixed angle and fell back, so the steel bobbed upward while
  its own slash swept sideways past it.

## Project

Browser-based multiplayer 2D pixel-art zombie roguelike. Python + FastAPI
authoritative server at a fixed 30 Hz, Vite + TypeScript + Canvas 2D client, one
WebSocket carrying JSON. `README.md` is the tour; the rules below bind every
subtree.

- Open a link, pick a name, create or join a room by its 7-character code, wait
  at the campfire, start. One socket (`/ws/{code}`) carries the lobby and the
  run; rooms live in memory and die with their last player.
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
  **THE WAY OUT IS FOUND, NOT FOLLOWED, AND THAT IS FOUR CHANNELS.** The exit
  is a VOID corridor carved on a random map edge — the same dark gap as the
  camp exit, and its outer end FLARES so it is a visible hole in the border
  treeline rather than a crack. The threshold is DRESSED: four torches in two
  ranks of two, and cut paving with light in its seams. Over all of it stands a
  COLUMN of light thrown straight up over the trees, hard for its first few
  seconds and then a steady pulse — drawn in WORLD space, so it is only on
  screen when the camera is pointed somewhere it can be seen, which is what
  makes finding it a matter of looking. A slow spatial PING sounds from the
  mouth every few seconds, and that is the channel that still works while the
  player is facing the other way. The gold HUD chevron (`/hud/chevron.png`) is
  the fourth and it BLINKS: a long solid burst on the frame the exit is carved,
  then dark, then a couple of seconds every few, for as long as the way out is
  uncrossed. It was permanent once, which meant the world never had to say
  anything — a marker that answers "which way out" forever turns a column of
  fire over a black forest into decoration. Then it faded out after ten
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
- **The STORE is the fourth beat of the loop and the only place money exists.**
  A trader's pitch in a round forest CLEARING, walked SOUTH TO NORTH
  (`server/app/store.py`): corridor, room, corridor. The party comes up out of
  the arrival throat and the night's PLATFORMS are being lowered onto the apron
  in front of them and to their left; the trader is parked on the WEST rim with
  his wagon, his counter, his fire and his own gear; his six stalls stand in a
  2x3 GRID on the EAST rim; and the upgrade MACHINE stands alone on the
  NORTH-WEST arc, on the side of the room the way out is on. Get paid, see what
  it buys, spend a level, leave. The way back seals behind them exactly as the
  forest's did; the north end stands open the whole time, and walking out of it
  is the next day — straight into the next night's forest, arriving through an
  edge corridor that seals behind them, exactly as leaving the campfire does.
  - **IT IS A ROOM AND IT USED TO BE A LANE.** The glade was long and
    east-west, with the tables strung along it, and the shape was doing exactly
    one thing: guaranteeing nobody walked past the stock. That is a corridor's
    argument and it is a weak one — the party has to walk the same straight
    line every night whether or not they can afford anything, and a shop that
    is a queue is a shop nobody stands still in. A round room is somewhere you
    STAND: everything in it is visible from the middle at once, two players can
    be at the trader and at the cabinet at the same time without one of them
    walking back through the other, and a party who came home broke can cross
    it in a straight line instead of being marched past six prices. The
    corridors on the ends are the half of the lane that was worth keeping —
    they keep the arrival and the departure as separate events.
  - **THE WAGON IS WHO HE IS.** He had a tent when he was a man camped in a
    glade; he has a CART now, because he did not walk here with six tables on
    his back — he drives, he was somewhere else last week, and that is the
    reason he is worth finding. It is also the only sprite in the game carrying
    the world's history on it: guns racked along the flank, masks strung on a
    line, salvage lashed to the boards, and two covered bodies laid out at the
    wheels. That last one is drawn as quietly as it can be and is never said
    out loud anywhere; the party works out where the stock comes from on their
    own, from across the clearing.
  - **IT IS THE ONE LIT PLACE, AND THAT IS THE ZONE'S JOB.** Everywhere else a
    party goes is a black wood with a torch in it somewhere; here they can see
    the treeline, the far arc of the room, the way out and each other.
    `Zone.ambient` is how — a floor under the darkness pass, zero in every zone
    somebody can be killed in and `zones.STORE_AMBIENT` here. On top of that
    floor a RING of torches burns around the rim, a chain runs down each throat
    and paired ranks dress both mouths. The ring is what a party sees before
    they see anything standing in it, and it is the difference between walking
    into a room and walking into more woods. It is still well under 1: the
    clearing is visible, not daylit, and his fire and the machine's marquee are
    the brightest things in it. The contrast is the reward — a night is only
    frightening if there is somewhere that is not.
  - **THE NIGHT'S PLATFORMS COME HOME WITH THE PARTY, AND GETTING PAID IS AN
    EVENT.** The same four aircraft that took the skids set them down on the
    apron, the lines let go, the drones climb out, and the cargo on the decks
    becomes GOLD: a spray of coins off each platform arcing to the balance on
    the HUD, counting it up, with a large `+N` over the middle that shrinks
    into that number rather than simply vanishing. It is the ONE place group
    gold is ever an object — the moment it is created — because a currency that
    only appears as a HUD digit is a score, and one that visibly comes off a
    machine that visibly came back is money. The balance itself is credited
    server-side on the crossing (`Room.enter_store`); everything above is
    presentation, so a reconnect mid-animation cannot pay anybody twice.
  - **HIS GEAR IS ON HIS SIDE AND NONE OF IT OPENS.** Crates, a barrel of rods,
    a rack of spare barrels, a shelf of tins, a padlocked strongbox — all on
    the WEST arc around the wagon and the fire, because everything a party may
    touch is on the EAST one. That split teaches which half of the room answers
    E in one visit. The art carries the other half of it: every frame is drawn
    roped, strapped and padlocked, because the player spent the previous night
    learning that a box in this game is a thing you open.
  - **It is OUTDOORS, and that is load-bearing.** It was an interior first, a
    plank corridor with walls and hanging lamps, and the problem outweighed
    everything it got right: it was the only building in the game, so it read
    as a menu the game had cut to rather than as somewhere the party walked. A
    clearing with a cart parked in it reads as a person who is also out here.
    It is an ordinary forest map — the same soil, trees and darkness as
    everywhere else — which is also why almost none of it needs special code:
    his campfire is a `FIRE` tile and every torch is a `SceneLight` like any
    cabin lamp.
  - **THE STOCK IS THE ONE THING IN THE ROOM THAT WAS ARRANGED.** Six round
    tables in two columns of three, on the grid, priced cheapest-first and read
    south to north — because that is the direction the party walks in, so the
    first table they reach is the one they can afford and the last is the one
    they are saving for. Everything AROUND the grid is irregular: the wagon,
    the fire, the gear, the torch ring. The old lane jittered its tables off an
    even rhythm on the argument that four identical stalls at four identical
    intervals is the tell that nobody set this up by hand — which is right
    about a corridor and wrong about a market. A trader who lays goods out in
    rows wants them compared; six prices scattered round a clearing is six
    things to hunt rather than one decision to make.
    The tables are ROUND because they are now walked around: a board has a
    front and a back and reads wrong from three of the four sides a room lets
    you approach it from.
  - **THERE ARE TWO CURRENCIES AND THEY ARE TWO METALS.** GOLD is the GROUP's:
    everything the party loaded onto the night's platforms becomes the balance
    on the way in here, and nothing else, anywhere, adds to it. Loot still in
    the bag is not money, it is loot they failed to extract. The balance is the
    party's, it survives the day, and it is the number a night is scored on —
    it is also never an object, which is why nothing in the world is drawn in
    gold except the sparks off a platform tearing out of the ground.
    DARK GOLD is the PLAYER's, and it is the opposite in every way: a PURPLE
    coin (`server/tools/make_coin.py`) that falls off corpses and out of
    explorables, that somebody has to walk over, that pools in `Player.gold`
    and rides on the `GOLD` row of their own panel behind a purple badge. It
    buys nothing yet — it is being saved for things that belong to one player
    rather than to the party — so its taps are set deliberately low: about half
    what they were, split across `config.COIN_DROP_CHANCE` for corpses and
    `crates.DROP_COIN` for objects. Move those two together. Do not merge the
    two currencies, and do not let dark gold pay for anything the group earned.
    The purple is separated from `--rarity-epic` by VALUE on purpose: epic loot
    already glows lavender in the dark, and a coin that glowed the same would
    teach the party that a purple light across a clearing means a good item
    right up until the night it meant three coins.
  - Each table shows the item's NAME in its rarity colour with a coin and a
    price under it. Walking close FLOATS the weapon off the boards — a slow
    breath, not a fixed offset, because a sprite that rose and stopped is a bug
    and one still moving is an offer — lights a pool under it, and opens the
    buy tooltip; E takes it. A stall sells once and the table stays there
    empty, because the gap is what says you already bought it.
    Prices are the loot catalog's value times a markup, never a second list,
    plus one stall's own HAGGLE either side of it. The catalog's value is
    itself derived — CS2 dollars through a curve anchored so the cheapest
    sidearm lands on day one's whole quota and the AWP lands near four
    hundred (`weapons.catalog_value`) — so a weapon's price, its weight and
    its damage all move together or not at all. The SHELF is sorted by price
    and gated by day in bands (`store.STOCK_ORDER`, `_unlock_day`): four
    sidearms on night one, the last thing on the ladder on night five,
    however long the ladder grows. That spread is what makes
    six stalls six decisions: the stock is rolled WITH REPLACEMENT, so he can
    be holding three of the same pistol, and three tables carrying the same
    number is a shelf rather than a shop. It is small enough never to reorder
    the catalog — a haggled AK never undercuts a full-price FAMAS — because the
    price ladder is teaching what the guns are worth.
    A price the party cannot cover is shown anyway, muted — the AWP priced out
    of reach is doing more work than a tutorial line about saving up would. The
    colour is the whole message; the tooltip does not also spell out that you
    are short.
  - It runs the darkness like every other forest map, because it IS one — the
    ambient floor above is a value on the zone, not a branch in the renderer.
    The pitch being the brightest pool in a lit-but-dim clearing is the whole
    picture, and the torches are still NAVIGATION: the lantern is off here, and
    the chain down the south throat is what points a party at the room before
    they can see into it. The merchant
    (`server/tools/make_merchant.py`) is not an entity — he stands still and
    plays an idle loop with three flourishes interrupting it, entirely
    client-side, because nothing about which frame he is on has ever been
    worth a message.
- **A LEVEL IS A TOKEN AND THE MACHINE IS THE ONLY THING THAT TAKES IT.**
  xp used to be a bar that filled and changed nothing. A level now pays one
  SPIN (`server/app/skills.py`), spins bank across nights, and the only place
  one can be spent is a scavenged slot cabinet standing alone on the north-west
  arc of the merchant's clearing — three tiles wide and four and a half tall,
  dented, chrome gone, one corner of its marquee smashed off, wired to a car
  battery on the ground beside it. That battery is the whole answer to "why is
  there a slot machine in a forest". It stands ACROSS the room from everything
  that is about money, on the side the exit is on, so it is somewhere a party
  WALKS to after they have spent — which is the whole difference between a
  machine and a menu item.
  - **IT IS A ROLL, NOT A MENU.** A list of upgrades with prices is a
    spreadsheet the player solves once and then executes every run afterwards;
    a roll is a moment. The ladder is the SAME five rarities loot already uses,
    so a purple canister means here what a purple aura means in the woods and
    nobody learns a second colour language.
  - **THE THIRD REEL IS THE DESIGN.** Two reels stop on a fixed rhythm the
    player learns in two visits; the third holds for longer the better the pull
    was (`machine.REEL_HOLD`). The roll is already resolved server-side when
    the lever moves, so that wait is honest — the machine is taking its time
    telling them, not deciding late. By the third shop a long third reel is
    good news before the colour lands, and that is the whole feeling.
  - **A REEL IS A BAND THAT GOES PAST, NOT A PICTURE THAT CHANGES.** Each
    window is a scrolling view onto one tall strip of ten cells
    (`/machine/strip.png`), and it DECELERATES into its stop over half a
    second. That ramp is where the whole ceremony actually lives: the reel
    crawls past six or seven faces one at a time with the answer already
    decided, and because the strip's fixed order puts a legendary next to a
    common, a near miss is a real thing that happened rather than an effect
    somebody wrote. Commons sit on the band four times, so the strip looks like
    the odds it pays. It used to be four frames of blur and a hard cut to a
    colour, which read as a colour appearing in a box.
  - The PAY LINE — the row all three windows have to agree on, marked in brass
    between them — flashes on the frame the last reel lands, before the tray
    fires. The machine reacting to its own result has to come before the
    consequence of it.
  - **RARITY IS A MULTIPLIER, NOT A SECOND CEREMONY.** One curve (`pullGain`)
    scales the burst, the marquee tint, the canister's glow and the camera
    shove; the sounds ladder the same way, and the `jackpot` flourish is EPIC
    AND UP only, because a celebration that fires on every pull stops being one.
  - What comes out is a physical CANISTER — the machine's tray fires it, it
    arcs, it lands, it sits there being looked at, then it flies into the tray
    ABOVE the bag on the HUD, where it becomes one ROW: icon, name in its
    rarity colour, and `x{n}`. A skill is a stack, so a duplicate is a smaller
    pull rather than a dead one. The tray is a list of labelled rows and not a
    grid of tiles, because a wall of 16px icons asks the player to hover
    eighteen things to find out what they own — which is a spreadsheet with the
    words hidden. With nothing pulled yet it says so in one muted word rather
    than disappearing: a HUD region that shows up for the first time at the
    first shop is a region the player has to learn mid-run. There is no
    "giros guardados" badge any more — it repeated one fact for a whole night,
    and the marquee below already says it from across the room.
  - **A SKILL HAS TO ACTUALLY DO SOMETHING**, and `skills.Mods` is the one
    place a player's numbers diverge from `config.py`. Speed, carry ceiling,
    health ceiling, gun and blade damage, xp, dark-gold odds, lantern life and
    what a platform credits for a loaded item all read it. A site still reading
    the raw constant is a site where a skill silently does nothing — see
    `server/app/AGENTS.md`.
  - The cabinet's MARQUEE burns harder for a player holding an unspent level.
    That is the only teaching in the zone that happens at a distance, it costs
    one float, and it is the thing a HUD line could never do from the far side
    of a clearing.
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
- Nothing is persisted server-side. The only durable client datum is the
  player's name, in `localStorage`.
- The server is authoritative. Clients send inputs, never positions.
- Every gameplay constant lives in `server/app/config.py` and reaches the client
  in `welcome.config`. Never hardcode one client-side.
- These pairs are mirrors and change together:
  - `server/app/simulation.py` ↔ `client/src/game/simulation.ts`
  - `server/app/protocol.py` ↔ `client/src/net/protocol.ts`
- Sizes, speeds and distances are authored in tiles/seconds and multiplied by
  `TILE_SIZE`. No raw pixel numbers.
- **The forest is 132 x 92 tiles and its scene count went up with it.** Those
  are one decision, not two: a map that grows without growing its stories is
  not a bigger world, it is a longer walk between the same things. What the
  extra ground buys is that a night with three extraction pads can put them
  far enough apart to be three separate expeditions rather than three stops on
  one lap. The pocket grew with it too (five slots), because at three a party
  filled the bag at the second scene and spent the rest of the night walking
  past things, which is the game refusing its own content.
- All colours and type live in `client/src/styles/index.css`, read by the canvas
  through `client/src/theme/`.
- **A SOUND IS PER EVENT, NEVER PER CATEGORY.** The object vocabulary was
  undone once already by three different containers all playing the inventory
  panel's UI tick, and the same trap caught the upgrade machine (built out of
  `object-heavy` and `object-open` first, and reading as a car boot). A lever,
  a reel detent, a canister landing in a steel tray and a container that turned
  out to be empty are four events and they have four recipes. Reaching for an
  existing sound because it is roughly the right shape is how the loudest
  channel in the game ends up saying every object is the same object.
- **Sound is generated art, like every pixel.** `server/tools/make_audio.py`
  synthesises the whole catalog into `assets/processed/audio/` — deterministic,
  stdlib only, one DSP vocabulary at the top that every recipe is written in —
  and the manifest carries each sound's gain and bus, so the mix is generated
  output rather than numbers scattered through the client. The client half is
  `client/src/audio/`: it knows about a listener at a point and sounds at other
  points, and nothing about players, zombies or zones. Sounds are SPATIAL,
  which is what makes the lantern pay off — a creature you cannot see but can
  place is the difference between tension and ambush. Ambience is stated, never
  started: a zone declares what it sounds like and the beds crossfade to it.
- Rendering knows nothing about the network; networking knows nothing about
  rendering; the server simulation knows nothing about either.
- `assets/processed/` is generated output. Edit the generator in
  `server/tools/`, never the PNG.
- The world arrives in two halves and they are placed by two different systems.
  TEXTURE — soil, grass, ferns, litter, prop variants — is scattered by the
  client from the map seed, because one rock is as good as another. SCENES —
  a cabin and its fence, a camp somebody left in a hurry, boot prints and the
  blood at the end of them — are placed by `server/app/scenery.py` and shipped
  on the map payload, because their meaning is the relationship between the
  pieces and a hash cannot agree on that. Anything decidable from
  `(tx, ty, seed)` belongs to the client; anything that means something belongs
  to a scene.
- Collectable loot is placed by the server next to those scenes
  (`server/app/loot.py`), not hashed from the seed, and there is a SECOND pass
  over the same scene list for ammunition (`server/app/ammo.py`) so the boxes
  land where the party is already going. Five rarities (common white, uncommon
  green, rare blue, epic purple, legendary gold). E collects
  when close; the name in the tooltip takes the rarity colour. Epic and
  legendary get a small looping beam; every rarity also throws a few
  rarity-coloured motes. The sprite hides in the dark; the motes and
  aura leak a whisper so a drop can be felt before the lantern reaches
  it. Camp maps have none. The pocket is
  `server/app/inventory.py`: a few slots (upgradeable), stacking by key,
  and a weight in kg that may go past max. The open bag shows
  `current / maxkg` and the bag's item-value total; that budget is the
  POCKET's alone — weapons never eat into it, because it answers "how much
  loot can I still carry out" and guns are not what extraction is for.
  Past 20% of max carry the walk slows
  and the footsteps read heavier. The bag's ceiling and the walk's are both
  a PLAYER's now rather than the config's — a skill moves them, and so it
  moves max health, damage, xp, dark-gold odds and lantern life. Anything
  still reading the raw constant is a skill silently doing nothing.
    TAB expands the bag on the left HUD. A collected item is held over the
  head, the bag opens so the slot is visible, then the sprite flies into
  that cell — the slot stays empty (border, value, weight) until the
  fly lands, so the roster cannot pop a second copy. Hovering a filled
  cell is a pointer and opens a card tooltip (name, rarity, weight,
  value) that flips or shifts to stay on screen; name and rarity both
  take the rarity colour. Slot value is a small HUD coin plus the
  number. Dragging a cell
  off the panel sends `{type:"drop","slot"}`; the server places the
  stack on walkable floor near the player's feet. A full bag (no slot
  and no stack) keeps the drop tooltip and reads "Inventário Cheio".
  Guns land on the HOTBAR (`server/app/weapons.py`), not in the pocket — they
  do not stack. **They are never found: the merchant is the only source.** A
  firearm is something the party spent a night's extraction on rather than
  something the forest handed them, and it is also what makes ammunition mean
  anything — a calibre nobody paid for is a calibre nobody finds boxes of.
  Nobody starts with one: the belt opens as two empty cells and the knife. 1 / 2 selects a gun slot, 3 is
  the knife; the same key holsters. An
  empty hand does not fire. The held sprite follows the mouse and flips
  when the cursor is left
  of the body. There is no laser sight. The AWP eases the camera out
  (`scopeZoom`) while the trigger is held, for more forest in frame. Tracers
  start at the barrel (`gunMuzzle`). What SLOWS you is the bag plus only the
  weapon in your HAND — a full rack is not a tax on having found things, and
  switching to the knife is a real way to move faster. A belt with no free
  gun cell does not refuse a better gun: the drop's tooltip becomes
  "trocar {held} por {new}" and E trades, leaving the old one at your feet.
  That is refused while holding the knife, which is not yours to trade away.
- **RUNNING IS A DECISION, AND STAMINA IS WHAT MAKES IT ONE.** SHIFT runs at
  1.55x the walk and spends a bar to do it (`STAMINA_*` in
  `server/app/config.py`). It is the party's answer to ground it has already
  read — the walk back to a console, the last stretch to a pad with the pack
  coming — and it is bounded well under a hunting creature's charge on purpose:
  it outruns a shamble and never outruns a hunt. The bar costs more than
  standing still pays back, so a night cannot be sprinted end to end, and
  catching your breath is FASTER STANDING STILL than walking, which is the one
  place the system asks the player to stop and look at the dark. Spend it to
  zero and the key stops answering until a third of it is back — the HUD says
  "winded…", because a control that goes quiet with no explanation reads as a
  dropped input. The multiplier sits ON TOP of the walk, so a skill's speed
  bonus and the bag's weight both still apply: a body hauling a full pack runs
  at a full pack's pace. Nobody runs through a cutscene or a POUR; both puppet
  the body, and the breath comes back over them.
- **AMMUNITION IS UPKEEP, NOT CARGO** (`server/app/ammo.py`). Every gun eats a
  round per TRIGGER PULL out of a per-player reserve for its calibre — pistol,
  SMG, shell, rifle or precision, five of them, derived from the catalog
  rather than listed — and the knife eats nothing, which is most of why the
  knife is still in the game. A shell buys six pellets and costs one round,
  because a shotgun spends a SHELL and not a pattern. A box is worth ZERO,
  takes no bag slot and cannot be loaded onto a platform: a round competing
  with a gold ring for a pocket cell would make shooting a choice against
  extracting, which is a tax on playing rather than a trade-off. THE FOREST
  STOCKS ITSELF AGAINST THE BELT — the map is built knowing what the party
  carries, so a room of knives finds no ammunition at all — and a box is
  collected only by somebody whose OWN belt holds that calibre and has room
  for it, so the rifle rounds go to whoever brought the rifle and a full
  reserve leaves the box there for the walk back. The rounds ride on the
  hotbar cell of the gun they feed; the knife's cell has no number on it, and
  that absence is the point.
  **A RESERVE IS COUNTED IN KILLS, NOT IN SECONDS OF TRIGGER.** The caps used
  to be sized so every calibre gave about thirty seconds of continuous fire,
  which sounds fair and is not: thirty seconds of P90 is twenty-one zombies
  and thirty seconds of Deagle is sixty-six, so the cheap fast gun quietly had
  a third of the ammunition economy of the expensive slow one. They are sized
  on `KILLS_PER_RESERVE` against the hungriest weapon that eats the calibre
  (`weapons.py`), so a full reserve is a night's worth of answers whatever you
  are holding, and the per-weapon difference stays where it belongs — in
  rounds per kill, where an upgrade buys a LONGER NIGHT rather than a bigger
  number. The shell reserve is the smallest in the game and deliberately so:
  sixty answers to "something is already touching me" and no answer at all to
  anything further off.
- **The belt's last cell is the KNIFE and it is not loot.** Nobody collects
  it, drops it or rolls a second one — it is placed by `Hotbar` itself, and
  that guarantee is the feature: a run OPENS with no gun, and the hand is
  still not empty. It costs a gun slot rather than adding a fourth cell, so
  carrying it is not free. It also does not shoot, which makes it the one
  weapon in the game
  that resolves as an ARC (`combat.sweep`) instead of a ray, and the only
  one with a COMBO: slash, slash, cut. The chain is held open by a clock
  rather than by the button, so breaking contact after two slashes starts
  fresh instead of banking a finisher. The cut is slower, wider, opens up
  to three bodies and ends the chain. Every step draws a white path swept
  out of the hand — the only uncoloured effect in the game — and the whole
  chain makes less noise than a single gunshot, which is the entire reason
  to use it. Picking up a gun while holding the blade puts it in your hand;
  a second gun does not. It is also the one weapon that works in the CAMP:
  `zone.hostile` gates the gun, not the swing, so the fire is somewhere you
  can mess about with a blade. Anyone killed there walks back to their seat
  a couple of seconds later.
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
- **ONE LANDMARK, AND IT IS THE ONE THING SOMEBODY BUILT.** The `sanctuary`:
  carved stone in a ring — totems, idols, a robed figure, a skull post, a
  monolith — with bones on the floor inside it and an ALTAR in the middle
  whose slab grinds aside. It is the only scene made of vertical shapes in a
  forest of low horizontal wrecks, the only one arranged in a circle, and the
  only one that states its bargain before the player commits: guaranteed loot
  off the best rarity table in the game, and a pack of creatures already
  standing on it. A landmark that was worth more AND safer would be an errand,
  not a decision.
- **A hit shows on the body, and it keeps showing.** A landed shot throws
  debris BACK along the ray and blood FORWARD out the far side, so the two
  read as a round passing through something rather than stopping on it, and
  it leaves a WOUND — one frame of `assets/processed/gore/` pinned to the
  sprite and masked to its silhouette, so the mark is ON the creature and
  carried through the walk cycle until it dries. Damage the player
  can only read off a health bar is a number; damage they can see on the
  creature is damage. Volume of spray and debris follows the gun's damage.
  A landed round knocks the body a little BACK along the shot with a tilt
  around the feet. Stacked hits slow then stop the walk on the server
  (`Enemy.stagger`); the sprite freeze is the visual of that plant. Only
  flesh bleeds: wood takes splinters and a swing the i-frames ate takes
  nothing.
- **THE FIRE AT THE BARREL IS PIXEL ART, NOT A CIRCLE**
  (`server/tools/make_weapon_vfx.py`, `client/src/render/weapon-vfx.ts`). The
  shot was the last important event in the game still drawn entirely out of
  canvas primitives, which made the loudest thing on screen the only thing
  that did not look like it was made of the same stuff as the forest. What is
  drawn now comes off
  `assets/inspiration/pixel-art-new-style/weapon-vfx.png` and follows what
  that sheet actually teaches: a muzzle flash is a hot core with PETALS and a
  LANCE thrown down the barrel, never a disc; the RING a beat later is what
  makes it read as pressure leaving a gun rather than a lamp switching on;
  white is the middle and deep red is the edge; and it ends in SMOKE, because
  a flash that simply faded is an effect stopping rather than finishing. The
  shotgun gets a different SHAPE and not a bigger flash — a cone that reaches,
  holds, breaks up and drifts — which is most of what makes the two weapons
  feel like different objects. Three sheets, all pointing right and rotated
  onto the aim, all drawn ADDITIVELY after the darkness pass, and all with the
  ramp BAKED IN: unlike `make_vfx.py`'s greyscale sheets, fire is not
  anybody's colour and a muzzle flash tinted to the shooter would be the one
  effect in the game that lied about what it was. One flash per TRIGGER PULL
  however many pellets came out of it, one damage number per BODY however many
  pellets reached it, and the atlas is null-safe — a client that could not
  load it falls back to the primitives it replaced.
- **A corpse pays a ROLL, and then it STAYS.** A creature's `gold` is the
  ceiling, not the payout — each point is flipped on its own (`COIN_DROP_CHANCE`),
  and that flip sits BELOW half, so the usual zombie pays nothing about half the
  time, one dark gold coin most of the rest, and three about once in a hundred.
  None of it is credited: the coins land on the ground and somebody has to walk
  over them.
  xp does not vary, because what a kill is WORTH is a rule and what fell out
  of it is luck. The body is the other half: a death burst, a collapse
  timeline on `<sheet>-death`, then a prone rest with a growing blood pool
  (scenery `blood.png`). Walking back through your dead is how an extraction
  run reads the map you made. Stepping in a pool tints the next boot prints,
  decaying each stride.
- **A forest night has a coat.** `night_clock()` rolls the hour; weather
  (`clear` / `rain` / `fog`) rolls with it so day 2 can feel like somewhere
  else without a new map. Rain is a looping bed plus streaks in the lantern.
  Camp is always clear.

## Child DOX Index

- `server/AGENTS.md` — authoritative Python server and the asset pipeline
- `client/AGENTS.md` — browser client: canvas game, React HUD, tokens, build
- `assets/AGENTS.md` — raw source art vs served production art
- `docs/AGENTS.md` — durable reference docs and design specs
- Root-owned files: `README.md`, `.gitignore`, and root-level project
  documentation.