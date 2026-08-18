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
- The KNIFE is the last cell (key 3) and the one weapon that never changes:
  it cannot be picked up, swapped or dropped. **A run starts with it and
  with no gun at all.** It does not shoot — it swings a short arc that
  leaves a WHITE PATH, and the swings chain three deep: a slash, a slash
  the other way, and a cut. The cut is slower, wider and goes through more
  than one body. Its damage is a floor, not a benchmark: quiet is the point
  of it, and the first gun on the ground has to stay worth walking to.
  It is drawn held IN against the body and a little smaller than the guns,
  because a blade at a pistol's extension reads as a sword floating beside
  the sprite.

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
  A gold HUD arrow (`/hud/arrow.png`) points at the VOID corridor carved on a
  random map edge — the same dark gap as the camp exit, and its outer end
  FLARES so the way out is a visible hole in the border treeline rather than a
  crack. The threshold is DRESSED: four torches in two ranks of two, and cut
  paving with light in its seams — the exit opens during the blackout, so those
  torches and the pads' own are the only thing burning on the map and the only
  thing that can say "here" rather than "that way". Crossing
  that corridor ends the night — but it does not go home yet. It opens on the
  **STORE**, and the day increments on the way out of THAT.
  Extraction pads are on the
  MINIMAP: dormant ones once their ground has been explored, awake ones
  always, gold once their quota is paid, and RED and breathing on the siren's
  own beat once the pickup has been called. The world is already laid out for the
  walk — `server/app/scenery.py` returns the ROUTE its scenes are strung
  along (outward from the mouth ending at the landmark), `SceneLight`/
  `BEACON` is the channel a beacon arrives on, and the boot prints
  players leave behind are navigation for the trip back.
- **The STORE is the fourth beat of the loop and the only place money exists.**
  A trader's camp in a long forest GLADE, read left to right
  (`server/app/store.py`): the party walks in from the west, the way back seals
  behind them exactly as the forest's did, the merchant is pitched in the
  middle — his tent, his campfire, his torches — and his three or four rustic
  tables are in front of him with one gun on each. The east end stands open the
  whole time; walking out of it is the next day — straight into the next
  night's forest, arriving through an edge corridor that seals behind them,
  exactly as leaving the campfire does.
  - **It is OUTDOORS, and that is load-bearing.** It was an interior first, a
    plank corridor with walls and hanging lamps, and the problem outweighed
    everything it got right: it was the only room in the game, so it read as a
    menu the game had cut to rather than as somewhere the party walked. A
    clearing with a tent in it reads as a person who is also out here. The
    glade is an ordinary forest map — the same soil, trees and darkness as
    everywhere else — which is also why almost none of it needs special code:
    his tent is a scenery prop, his campfire is a `FIRE` tile, and his torches
    are `SceneLight`s like any cabin lamp.
  - The lane is a corridor made of WOODS rather than of walls, and the shape is
    the point: one decision repeated three or four times, so the treeline
    squeezes the walkable ground into a lane and every table sits between the
    way in and the way out. A round clearing lets a party cut a diagonal and
    leave without seeing half the stock. The tables are placed on an even
    rhythm and then pushed off it — four identical stalls at four identical
    intervals is the loudest tell that nobody set this up by hand.
  - **CURRENCY.** Everything the party loaded onto the night's platforms
    becomes the GROUP's balance on the way in here — nothing else, anywhere, adds to
    it. Loot still in the bag is not money, it is loot they failed to extract.
    The balance is the party's and survives the day; `Player.gold` is a
    separate, personal number (coins somebody walked over) and stays that way.
  - Each table shows a coin and a price above it. Walking close LIFTS the
    weapon off the boards, lights a pool under it, and opens the buy tooltip;
    E takes it. A stall sells once and the table stays there empty, because
    the gap is what says you already bought it. Prices are the loot catalog's
    value times a markup, never a second list. A price the party cannot cover
    is shown anyway, in red — the AWP priced out of reach is doing more work
    than a tutorial line about saving up would. The colour is the whole
    message; the tooltip does not also spell out that you are short.
  - It runs the darkness like every other forest map, because it IS one. The
    pitch being a pool of firelight in a dark glade is the whole picture, and
    the torches lining the lane are NAVIGATION — the lantern is off here, so
    without them a party emerging from the west corridor would have no way of
    knowing which direction the trader is. The merchant
    (`server/tools/make_merchant.py`) is not an entity — he stands still and
    plays an idle loop with three flourishes interrupting it, entirely
    client-side, because nothing about which frame he is on has ever been
    worth a message.
- The room's ZONE (`server/app/zones.py`) says where the run is and how that
  place behaves: its title card, whether enemies spawn and guns fire
  (`hostile`), and whether the lantern may be switched on (`lantern`). The
  client is told all three and infers none of them from the map.
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
  and the footsteps read heavier.   TAB expands the bag on the left HUD. A collected item is held over the
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
- **AMMUNITION IS UPKEEP, NOT CARGO** (`server/app/ammo.py`). Every gun eats a
  round per shot out of a per-player reserve for its calibre — pistol, rifle,
  or precision — and the knife eats nothing, which is most of why the knife is
  still in the game. A box is worth ZERO, takes no bag slot and cannot be
  loaded onto a platform: a round competing with a gold ring for a pocket cell
  would make shooting a choice against extracting, which is a tax on playing
  rather than a trade-off. THE FOREST STOCKS ITSELF AGAINST THE BELT — the map
  is built knowing what the party carries, so a room of knives finds no
  ammunition at all — and a box is collected only by somebody whose OWN belt
  holds that calibre and has room for it, so the rifle rounds go to whoever
  brought the rifle and a full reserve leaves the box there for the walk back.
  The rounds ride on the hotbar cell of the gun they feed; the knife's cell
  has no number on it, and that absence is the point.
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
  rolls empty (wind VFX), coins, or one item, which JUMPS out of the opening
  and lands. Coins only once the exit is open, for the same reason the ground
  gets swept then. Camp maps have none. Interact is loot, then object, then
  ready.
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
- **A corpse pays a ROLL, and then it STAYS.** A creature's `gold` is the
  ceiling, not the payout — each point is flipped on its own (`COIN_DROP_CHANCE`),
  so the usual zombie drops 0 to 3 coins with both ends rare, and none of it is
  credited: the coins land on the ground and somebody has to walk over them.
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