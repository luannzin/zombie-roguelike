# Gear: lâminas, worn armour, the shield — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the blade catalog and the cell it lives in, the twelve worn pieces and their four materials, the shield, and everything that stands between a blow and a player's health |
| **Inputs** | `InputPacket.block` (right mouse), `{type:"collect"}`, `{type:"buy"}` |
| **Outputs** | roster `armor` / `shield`, player tick `blk`, `snapshot.armorHits`, `welcome.config.armor` / `armorSlots` / `armorCoverage` / `gunSlots` / `bladeSlot` / `startingBlade` |
| **Depends on** | `enemies.ZOMBIE` (the unit, twice over), `weapons.py` (the belt), `loot.py` (catalog rows), `store.py` (one of two sources), `skills.Mods.armor` (toughness, which is not this) |
| **Consumers** | `Room.damage_player`, `simulation.py` (the walk), `client/src/render/layers/entities.ts` (`gear`), `client/src/components/hud/Armor.tsx` |
| **Authoritative** | every durability, where a blow lands, whether the shield caught it, what a pickup displaces |
| **Presentation** | the overlay on the body, the raised-shield pose, the three bars, the break |

## Invariants

- **The blade cell is never empty**, and that is the guarantee — not that it holds a knife. `Hotbar.__post_init__` puts a blade back; `BLADE_SLOT` never takes a gun; `add` routes on `is_blade`, not on a name.
- **The knife is not an object.** Replacing it drops nothing. Every other lâmina lands at the feet.
- **A blade is a catalog row and no code.** `Room.handle_attack` dispatches on the weapon's `melee` block; a shield dispatches on its `shield` block. Neither dispatches on `kind`.
- **Every blade is the knife's own chain through seven multipliers** (`BladeProfile`). The knife's profile is all ones, and `test_gear.py` checks that the generator reproduces the weapon it was derived from exactly.
- **Damage arrives at one door.** Shield, then plate, then `Mods.armor`, in `Room.damage_player`. Nothing else mitigates anything.
- **Material sets the numbers, slot sets where the hits land.** Soak, durability, weight and price are functions of the tier alone; coverage is the only thing a slot decides.
- **Armour never reaches zero damage taken.** `SOAK_CEILING` is 0.75. The thing that stops a blow outright is the shield, and you have to be holding it, facing the right way, in place of a gun.
- **Worn armour is on the WALK, never in the bag.** `Player.carry_weight` sums it; `inv.w` never does.
- **A shield is UP on the tick row (`blk`) and its LIFE is on the roster.** A pose at 5 Hz would let a player watch a blow land on a shield that had not come up yet.
- **Never hardcode any of this client-side.** Twelve pieces, three slots, the coverage table and the belt's own split all arrive in `welcome.config`.

## Danger zones

- `Room.damage_player` — the one door. A `return` added above the plate is armour that silently stops working.
- `armor.Loadout.absorb` — the roll and the wear. Split from `absorb_at` so the second half is testable; keep it that way.
- `Room.sync_block` / `Game.syncBlock` — a mirror pair, and it must run BEFORE the walk on both sides.
- `weapons.WEAPONS` ordering — blades and shields are APPENDED after the guns, and the held atlas keys off it.
- `GUN_KEYS` — derived as "no melee AND no shield". A shield that leaked back into it would be sold as a firearm and would ask the forest to stock ammunition for it.

## Change surface

| intent | touch |
| --- | --- |
| add a lâmina | one `BladeProfile` in `server/app/weapons.py` + tags in `loot._BLADE_TAGS` + an art map in `server/tools/make_guns.py` (appended) |
| retune every blade at once | `weapons._CHAIN` — the knife's own beats, which every blade is a multiple of |
| a blade's price | nothing: `blade_power` is throughput times ground covered, and `BLADE_VALUE_CURVE` is the only knob |
| add an armour material | one row in `armor.MATERIALS` + a ramp letter in `make_loot._ARMOR_LETTERS` + one in `make_armor.MATERIALS`, then rerun both generators |
| add an armour SLOT | `armor.SLOTS` + `COVERAGE` + `SLOT_NAMES` + `_NAMES` + a template in `make_armor.SHAPES` and `make_loot._ARMOR_FORMS` |
| how much a plate stops or survives | `armor.SOAK_CEILING`, `HITS_BASE` — never a per-piece number |
| where a blow lands | `armor.COVERAGE`, and it is the player sprite's own row bands. Changing it is changing a fact about the art |
| the shield's numbers | `armor.SHIELD_*` + `shield_hp` / `shield_value` / `shield_weight` |
| what blocking costs the walk | `armor.SHIELD_SPEED` — and it lands on `Player.block_speed` / `MovableState.blockSpeed`, which is a MIRROR |
| the block pose | `client/src/game/entity-visuals.ts` (`GUARD_*`, `guard()`), which is the brace's opposite on every axis |
| the three bars and the shield row | `client/src/components/hud/Armor.tsx`, `Game.armorHud()` |
| the overlay on the body | `server/tools/make_armor.py` + `Game.wornSheets` + `GearLayer` in `client/src/render/types.ts` |
| what a table may sell | `server/app/store.py` (`SELLABLE`, `_category`) |

**Do not touch from here:** the pocket's own rules, ammunition, the skills
catalog, or `Mods.armor` — that is TOUGHNESS and it is a different thing (see
below).

---

## Design law

- **LÂMINAS: THE BLADE CELL IS A CELL WITH NO EMPTY STATE, AND EVERY RULE
  ABOUT IT FOLLOWS FROM THAT.** The belt used to be two gun cells and a knife
  that could not be picked up, dropped or swapped — and the promise the player
  learns on their first screen was read out of that as "you always have a
  knife". It never was. The promise is **the hand is never empty**, and the
  fixed knife was one implementation of it. Once the cell can hold an axe or a
  katana, the same promise holds for free: a lâmina lands on the cell and
  whatever was there leaves on the same frame, so there is no instant in which
  the belt has nothing on it.
  What that costs is one honest exception. **The knife is not an object.**
  Replace it and nothing hits the floor — it is `droppable=False`, no pool can
  produce one, and leaving one in the grass every time somebody found an axe
  would litter the map with pickups nobody would ever want. Replace an AXE and
  the axe hits the floor, because that one is a thing the party owns and a
  trade you can change your mind about one step later is a trade. The knife is
  the floor under the cell, not its contents.
- **THE KNIFE IS THE UNIT, EXACTLY AS THE ZOMBIE IS THE UNIT FOR GUNS.** There
  is no published stat block for a hatchet, so the ladder is anchored on the
  one melee weapon this game has always had and every lâmina is the knife's
  own three beats scaled by seven columns: how much of a zombie a whole chain
  takes, how far it reaches, how wide it sweeps, how fast it comes round, how
  much body goes into it, how far it carries as sound, and how many bodies the
  finisher opens. The knife's own profile is all ones — which is not a
  convenience, it is the CHECK: a generator that could not reproduce the
  weapon it was derived from would be a second opinion about a swing that is
  already tuned, and `test_gear.py` fails the build if it drifts by a
  hundredth.
  The one column that is the ladder is `share`. **Under 1.0 the blade cannot
  finish what it started; over it, the chain kills.** That is the single
  largest thing that happens to a run which has been living on the knife, and
  it is one number rather than a table.
- **THE AXE AND THE KATANA NEVER OBSOLETE EACH OTHER**, and that is why there
  are two of them rather than one better one. The axe is slow, short, very
  wide and opens a fourth body on the finisher: it answers a crowd, and its
  silhouette says so before it has been swung once — it is the only thing on
  the held sheet whose weight is at the FAR end. The katana is fast, long and
  narrow: it answers the one thing that got close before you heard it. They
  are priced by what they DO (`blade_power` — share per second of chain, times
  reach, times the crowd the finisher opens) rather than by what they hit for,
  which is why the katana is the expensive one despite the axe hitting harder.
- **LÂMINAS ARE FOUND, AND THAT IS THE ONE PLACE THIS CATEGORY PARTS COMPANY
  WITH THE GUNS.** A firearm is `droppable=False` because the merchant being
  the only source is what makes calibre and ownership the same question — the
  forest stocks ammunition against what the party PAID for. None of that
  argument survives contact with a blade: steel eats nothing, so there is no
  economy to protect, and a run that opens on the knife with no money needs a
  route to better steel that does not go through a shop it cannot afford. A
  hatchet in a logging camp is also simply what is there.
- **ARMOUR: THE ZOMBIE'S CLAW IS THE UNIT.** `weapons.py` anchors every
  firearm on what a zombie can survive; this anchors every plate on what a
  zombie can do. Everything is a function of that one number plus the
  MATERIALS, the SLOTS and one exponent, and there is not a hand-picked
  durability figure anywhere.
- **MATERIAL SETS THE NUMBERS, SLOT SETS WHERE THE HITS LAND.** Twelve rows
  stay readable because a player who has learnt what leather does has learnt
  it for all three slots, and the only question left about a piece is whether
  they are already wearing something better THERE. Soak is a quarter of the
  ceiling per rung, so "one better" means the same thing everywhere on the
  ladder; durability is `HITS_BASE * tier` blows landing on that part; weight
  and price come off the tier too.
  It is also why the ICONS are three shapes in four colours — which is the
  exact opposite of the creature rule, where three variants must be three
  silhouettes. There the question is "what is that"; here the player already
  knows it is a helmet and the question is "is it better than mine". A ladder
  whose rungs are four different shapes cannot be ordered at a glance.
- **WHERE A BLOW LANDS IS THE SPRITE'S OWN ANATOMY.** `COVERAGE` is head 7,
  torso 4, legs 3 — the rows `make_player.py` actually spends on a fifteen-row
  figure, which is S17's proportion. So the HELMET is the piece that matters
  most on this character, and that is not a balance decision anybody made: it
  is what the silhouette says. A player aiming at this sprite is aiming mostly
  at a head, and a rule the game never shows you is a rule nobody learns.
- **ONE BLOW LANDS ON ONE PART, ROLLED — NOT SPREAD ACROSS THE SET.** Every
  worn piece could soak its coverage-weighted share of everything, which is
  smoother and worse: the pieces would then wear at exactly the rate that
  makes a whole set fail at the same moment, and a set that fails all at once
  is a stat that went away rather than an event. Rolled, the chest goes first
  because the chest is hit most, it goes in the middle of a fight, and the
  player finds out by looking at three numbers they had been ignoring all
  night. It is also what makes a PARTIAL set feel partial: the roll happens
  whether or not there is anything there, so a helmet is not quietly worn on
  the legs, and the times it does not answer are the ones you remember.
- **A PLATE THAT BREAKS STILL SOAKS THE BLOW THAT BROKE IT.** The last thing a
  chestplate does is its job.
- **ARMOUR IS GEAR AND `Mods.armor` IS TOUGHNESS, AND THEY MULTIPLY IN THAT
  ORDER.** A skill's armour is a multiplier the run bought and nothing can
  take away; a plate is an object with a number on it that ends at zero. Steel
  stops part of the blow, and what gets through is what the body has to be
  tough about — which is also why the plate is applied first. Putting them in
  one field would make "you found a chestplate" and "you rolled an armour
  skill" the same event, and they are not.
- **ARMOUR IS FOUND AND BOUGHT BOTH, AND IT IS THE FIRST THING IN THE GAME
  THAT IS.** A firearm can only be bought, because the merchant being the only
  source is what makes ammunition mean anything. A lâmina can be found,
  because steel eats nothing. Armour is on both ladders, and that is what it
  is FOR: a shelf of nothing but guns asks one question every night — which
  gun — and the answer is always the most expensive affordable one. A shelf
  with plate on it asks a better one. This night's take is a rifle, or it is a
  helmet and rounds, and a party that has been dying at doorways knows which.
- **THE SHIELD IS NOT ARMOUR THAT IS BETTER. IT IS A WALL, AND EVERYTHING
  ABOUT HOW IT IS CARRIED IS THE PRICE OF THAT.** Every plate is attrition —
  it takes a share and lets the rest through. The shield takes the blow to
  ZERO, and in exchange: it eats a GUN CELL (a party member behind one is a
  party member who is not shooting), it only answers what is in front of it
  (`SHIELD_ARC_DEGREES` — a shield with no back is what makes a second player
  worth having), it only works while the button is held, it slows the walk
  while it is up, and it comes apart in fourteen claws. That is a shorter life
  than the best armour in the game, deliberately: a shield is a resource to
  spend at a doorway, not a wall to live behind.
- **A SHIELD HAS NO TRIGGER.** Not "the attack is suppressed while blocking" —
  there is nothing to suppress. The left button does nothing at all with one
  in hand, which is the whole cost of the cell it stands in and the reason a
  party carrying two of them is a party that cannot kill anything.
- **THE ONE BLOW THAT BREAKS IT STILL GOES THROUGH, MINUS WHAT IT ATE.** The
  Sawyer's bar arriving through the wreckage of a riot shield is the moment
  the player learns what "126" meant, and a shield that ate an arbitrarily
  large blow because it happened to have one point left would be a wall with a
  loophole in it. The wreck is not dropped: a shield at zero is not a shield,
  and leaving one on the floor would invite somebody to pick up a thing that
  cannot do anything.
- **RIGHT MOUSE IS A REQUEST, EXACTLY AS SHIFT IS.** Nothing reads `block` as
  a state: `Room.sync_block` decides per tick whether the shield is actually
  up, against what is in the hand and whether it is still in one piece, and
  the client runs the same rule off its own button so raising it is not a
  round trip. What that costs is one resolved number on the body
  (`block_speed`) rather than a catalog lookup inside movement code, because
  `simulation.py` and `simulation.ts` are a line-for-line mirror and neither
  is allowed to know what a `ShieldDef` is.
- **ARMOUR IS VISIBLE, THROUGH THE SYSTEM THAT WAS ALREADY THERE.** The game
  already had a way to put something on a body — `DrawableEntity.gear`, which
  is how a backpack rides a player and a cap rides a zombie — and armour is
  exactly that: a sheet on the same 16x16 grid, in the same facing and the
  same walk column, one draw call after the body. A second mechanism for
  putting things on people would be a second thing to keep in step with the
  walk cycle.
  What that cost was one honest change: **a gear layer now says whether it
  wears the body's colour.** The backpack is greyscale and takes the wearer's
  tint, because it is issued kit and wearing your own colour is the point of
  it. A steel plate is baked, because its colour IS its material and that is
  the entire ladder — multiplying a player's identity swatch through it would
  turn steel and leather into two shades of that player.
  The overlays carry ONE pose block where the player carries two. That is
  correct rather than lazy: the hold pose moves ARMS, and a helmet, a
  breastplate over the coat's centre and a pair of greaves sit on the three
  parts of this figure that are identical between the blocks.

---

## Server contracts

- **`loot.ItemDef.pocket` is the only thing that decides where something
  lands**, and there are four answers because a player has four containers.
  `Room.take_gear` is the one door both a pickup and a purchase go through, so
  a table selling a helmet and a cabin dropping one cannot disagree about what
  happens when you already have one.
- **A worn piece keeps its damage through a swap.** `Drop.hp` carries it
  through the ground, so "is this actually an upgrade" stays a real question
  with a cracked steel plate on your chest and a fresh cloth one in front of
  you. The ONE refusal a worn slot has is the piece you are already wearing in
  the same or better condition; a piece that is WORSE than what is there still
  goes on, because "worse" is not something the server gets to decide.
- **A shield's durability lives on the BODY, not on the belt.** A belt cell
  holds a key and this is state — and it is not in the `Loadout` either,
  because you hold a shield rather than wear it. At most one per belt, which
  is a design rule before it is a technical one.
- **`snapshot.armorHits` is the EVENT and the roster is the STATE**, the same
  split `kills` keeps from `enemies`. The bar is resynced off `PlayerMeta`; a
  client that missed a packet must never replay a piece breaking. Only the
  BREAK is juice: a plate taking its share already has a picture — the hit
  flash, the blood, the knockback all fired off the same blow.
- **The shop walks every ladder at once.** `STOCK_UNLOCK` is banded inside
  each CATEGORY rather than over one merged sort, because three cloth rags
  cost less than the cheapest pistol and a merged sort would have pushed the
  first firearm off night one. That is not a rebalance anybody asked for, it
  is an accident of concatenation. The gun ladder comes out of this
  byte-for-byte what it was before there was anything else on the shelf.

## Known gaps

- **No dedicated sound.** A plate soaking is silent (the blow it came with is
  not) and a piece breaking borrows `crate-break` pitched up. A steel tick, a
  leather scuff and a polycarbonate crack are three recipes in
  `make_audio.py` and one call site each; nobody has written them.
- **The overlays have not been looked at in a browser at speed.** They are
  registered on measured bands and `make_armor._check` fails the build if one
  leaves the grid, but nobody has watched a body in a full steel set walk
  across a clearing to see whether the plate reads as worn or as painted on.
- **The shield has no impact art.** A blow stopping dead on it currently looks
  the same as a blow missing. The spark belongs in `weapon-vfx` and wants the
  hit point, which `armorHits` already carries.
