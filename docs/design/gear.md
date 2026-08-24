# Gear: lâminas, worn armour, the shield — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the blade catalog and the cell it lives in, the twenty worn pieces over five slots and four materials, what a SET is called and what wearing it means, the shield, and everything that stands between a blow and a player's health |
| **Inputs** | `InputPacket.block` (right mouse), `{type:"collect"}`, `{type:"buy"}` |
| **Outputs** | roster `armor` / `shield`, player tick `blk`, `snapshot.armorHits`, `welcome.config.armor` / `armorSlots` / `armorSlotNames` / `armorBodyLayout` / `armorCoverage` / `gunSlots` / `bladeSlot` / `startingBlade` |
| **Depends on** | `enemies.ZOMBIE` (the unit, twice over), `weapons.py` (the belt), `loot.py` (catalog rows), `store.py` (one of two sources), `skills.Mods.armor` (toughness, which is not this) |
| **Feeds** | [`ultimates.md`](ultimates.md) — a material's `tags` and `Loadout.tag_pieces` are half of every synergy requirement. This module does not know what an ultimate is |
| **Consumers** | `Room.damage_player`, `simulation.py` (the walk), `client/src/render/layers/entities.ts` (`gear`), `client/src/components/hud/Armor.tsx` |
| **Authoritative** | every durability, where a blow lands, whether the shield caught it, what a pickup displaces |
| **Presentation** | the overlay on the body, the raised-shield pose, the mannequin, the break |

## Invariants

- **The blade cell is never empty**, and that is the guarantee — not that it holds a knife. `Hotbar.__post_init__` puts a blade back; `BLADE_SLOT` never takes a gun; `add` routes on `is_blade`, not on a name.
- **The knife is not an object.** Replacing it drops nothing. Every other lâmina lands at the feet.
- **A blade is a catalog row and no code.** `Room.handle_attack` dispatches on the weapon's `melee` block; a shield dispatches on its `shield` block. Neither dispatches on `kind`.
- **Every blade is the knife's own chain through seven multipliers** (`BladeProfile`). The knife's profile is all ones, and `test_gear.py` checks that the generator reproduces the weapon it was derived from exactly.
- **Damage arrives at one door.** Shield, then plate, then `Mods.armor`, in `Room.damage_player`. Nothing else mitigates anything.
- **Material sets the numbers, slot sets where the hits land.** Armour, durability and weight are functions of the tier alone. Coverage is what a slot decides, it must sum to a whole body (`_check_coverage`), and since there were five slots it also decides PRICE — see `value_of`.
- **A material is a rung AND an identity.** One tier, one set name, one tag set, all on the same row — see [`ultimates.md`](ultimates.md) for why the two axes are deliberately not separable.
- **Armour is FLAT, in damage points.** A plate takes a fixed number off every blow that lands on its part — never a percentage, because a proportional mitigation cannot be printed as a number without naming the blow it is a proportion of.
- **Armour never reaches zero damage taken.** `CEILING_SHARE` caps the top rung under one full claw, and `damage_player`'s `max(1, ...)` is the floor under everything. The thing that stops a blow outright is the shield, and you have to be holding it, facing the right way, in place of a gun.
- **Worn armour is on the WALK, never in the bag.** `Player.carry_weight` sums it; `inv.w` never does.
- **A shield is UP on the tick row (`blk`) and its LIFE is on the roster.** A pose at 5 Hz would let a player watch a blow land on a shield that had not come up yet.
- **Never hardcode any of this client-side.** Twenty pieces, five slots, their names, the coverage table, the FIGURE they are drawn as (`BODY_LAYOUT`) and the belt's own split all arrive in `welcome.config`.

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
| add an armour material | one row in `armor.MATERIALS` (tier, set name, tags) + a ramp letter in `make_loot._ARMOR_LETTERS` + one in `make_armor.MATERIALS`, then rerun both generators |
| add an armour SLOT | `armor.SLOTS` + `_AREA` + `SLOT_NAMES` + `BODY_LAYOUT` + `_NAMES` + a template in `make_armor.SHAPES` and `make_loot._ARMOR_FORMS`. The HUD does not change |
| how much a plate stops or survives | `armor.CEILING_SHARE`, `HITS_BASE` — never a per-piece number |
| where a blow lands | `armor._AREA`, and it is the pixels the player sprite actually spends. Changing it is changing a fact about the art |
| the shield's numbers | `armor.SHIELD_*` + `shield_hp` / `shield_value` / `shield_weight` |
| what blocking costs the walk | `armor.SHIELD_SPEED` — and it lands on `Player.block_speed` / `MovableState.blockSpeed`, which is a MIRROR |
| the block pose | `client/src/game/entity-visuals.ts` (`GUARD_*`, `guard()`), which is the brace's opposite on every axis |
| the mannequin and the shield row | `client/src/components/hud/Armor.tsx`, `Game.armorHud()` |
| where a slot sits on the FIGURE | `armor.BODY_LAYOUT` — shipped, so a sixth slot is not a client change |
| WHAT a card says about a piece | `client/src/game/gear-card.ts` — one function, used by the belt, the armour panel and the shop |
| how a card LOOKS | `client/src/components/hud/GearCard.tsx` (rows) + `HoverCard.tsx` (the portal and the fit) |
| why a pickup was refused | `client/src/game/interaction.ts` (`ammoRefusal`, `HudLootPrompt.reason`) + `LootPrompt.tsx` |
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
- **FIVE PIECES, BECAUSE ARMOUR IS SOMETHING YOU ARE WEARING.** It was three
  — head, body, legs — and three is what you write when armour is a STAT: a
  rating, a durability, a bar. It is not what a player is doing when they put a
  helmet on, and the HUD that grew out of it said so plainly. Three labelled
  rows with thin meters beside them is a spreadsheet of a costume, and a player
  could pick up a pair of steel greaves, wear them all night and never once see
  greaves.
  There are five now — a helmet, bracers, a breastplate, trousers and boots —
  and the panel draws them as a BODY rather than as a list: one box, then
  three, then two, then two, which is a person seen from the front. The rule
  underneath did not change and did not need to. What changed is that the slots
  are finally enough of a person that the picture can be one, and that a hole
  in the picture is a part of you the next blow can land on with nothing in the
  way — which is a far louder sentence than an empty row was.
  The cost was paid once and is bounded: twenty catalog rows instead of twelve,
  five icon shapes, five overlays. Nothing downstream counts them, and
  `BODY_LAYOUT` ships so a sixth is not a client change.
- **COVERAGE IS MEASURED IN PIXELS NOW, NOT IN ROWS, AND THAT IS FORCED BY THE
  SPLIT.** With three slots the sprite's row bands were enough — head 1-8,
  torso 9-12, legs 13-15 — and the shares fell straight out of the row counts.
  Five slots do not fit in one dimension: the arms are not a BAND of the
  figure, they are the outer columns of the band the chest is in the middle of,
  and boots are one row of a band the shins share. So `_AREA` is the area each
  part actually occupies on the player sheet, read the same way
  `make_armor.py` reads it, and `COVERAGE` is that normalised.
  The helmet is still most of the body (58%), which is still not a balance
  decision anybody made — it is what S17's proportion says. What the split adds
  is the OTHER end: boots answer about one blow in twenty-three.
- **WHICH IS WHY PRICE STARTED READING COVERAGE, AND IT IS THE ONLY NUMBER
  ALLOWED TO.** With three parts of roughly comparable size, pricing every
  plate off its material alone was close enough to honest. It is not close
  enough at five — charging the same for a helmet and a pair of boots would put
  a piece on the merchant's shelf that no informed party would ever buy, which
  is dead content with a price tag on it.
  So a piece is priced by what it will actually absorb BEFORE THE SET IS
  FINISHED. A set fails when its busiest part does — the helmet, always — and
  every other piece spends only its own share of that same span. The helmet
  therefore keeps exactly the number the old three-way ladder gave it and the
  rest come out at what they are worth beside it. Read the result once, because
  it is the clearest statement this system makes about itself: at the top of
  the ladder the helmet is two thirds of the price of the whole suit. That IS
  the game — a party's first armour purchase should be a helmet, and the shelf
  now says so without a tutorial line.
  It is still `value_from_hp`, the one curve everything that stops a blow is
  priced off. A second curve for "small pieces" would be a second opinion about
  one question.
- **AND WEIGHT IS AUTHORED PER SET, NOT PER PIECE.** `SET_KG_AT_TOP` is the
  number that was tuned and `KG_BASE` is derived from it. Splitting three
  pieces into five at a fixed per-piece weight would have quietly made a full
  suit two thirds heavier than the figure this system was balanced against, and
  nothing would have failed — the player would simply have been slower for a
  night and nobody would have known why.
- **THE PANEL IS COLLAPSED BY DEFAULT AND C EXPANDS IT, AND COLLAPSED IS NOT
  EMPTY.** The bag and the body are two different questions — what am I
  carrying out, and what is keeping me alive — so they are two keys; folding
  them into one toggle would make a player checking their helmet look at their
  loot as well, in the corner of the screen they are fighting toward.
  What survives the collapse is the header: the SET, and what a blow costs. The
  old panel's one genuine virtue was that "am I still covered" was answerable
  without a keypress, and losing it would have been a bad trade. What expanding
  buys is WHICH piece and WHAT it is, which is a question you ask between
  fights. The header also does not move a pixel when the drawer opens — the
  panel grows upward, because the column is bottom-anchored and the vitals
  under it must stay where the player's eye already is.
- **THE CARDS PRINT FIVE KINDS OF ROW AND NO OTHERS.** `DANO`, `TIROS/S`,
  `ARMADURA`, `DURABILIDADE`, `MUNIÇÃO`. The first cut of these cards printed
  everything that was true — a rifle came with damage, cadence, damage per
  second, range, noise, calibre and weight — and every one of those numbers was
  real and the card was still wrong: a hover card is read in the half second
  before something reaches you, and a seven-row table is not read at all. It is
  dismissed, then the player stops hovering, then the whole system may as well
  not exist.
  Everything cut was cut on one test — would a player ever choose differently
  because of it, in the moment they are looking at this card. Range and noise
  are real and are learned by SHOOTING. Weight is real and is already a bar on
  the bag. A material is already in the object's own name. "Acertos aqui" was
  an interesting fact about anatomy and never once a decision.
  Two rows that are not numbers survive, and both earn it: a shield's ÂNGULO,
  because its durability is a lie by omission without the rule that it only
  answers what it is facing; and a weapon's ULTIMATE, because that is the
  single largest thing a player is choosing between at a shop table and it is
  invisible everywhere else until they already own the weapon.
- **ARMOUR IS FLAT, AND THAT IS A DECISION ABOUT WHAT THE PLAYER READS.** It
  began as a fraction — steel took 56% of a blow — which is a clean rule and
  an unreadable stat. A percentage cannot go on a card without naming the blow
  it is a percentage OF, and the moment the card names one the entire stat
  block is anchored on one creature and starts lying the day there is a second
  one worth comparing against. There is no honest way to print a proportional
  mitigation as a number.
  A flat rating has no such problem: `ARMADURA 5` means five, against anything
  this game ever grows. And the shape it gives the category is the better one:
  armour is STRONG against a crowd of small hits and WEAK against one big one,
  so plate is what you wear for the forest and is not what saves you from the
  Sawyer's bar — the shield is, and that is what stops the shield being a
  plate you have to hold. A proportional mitigation is equally good against
  everything, which is another way of saying it never makes a decision
  interesting.
  The ladder is 2 / 3 / 5 / 7 armour over 8 / 24 / 60 / 112 durability, which
  divides evenly into 4 / 8 / 12 / 16 blows — the flat take is what makes that
  arithmetic exact, and exact is what lets the HUD promise a count.
- **THE CLAW IS STILL THE SIZING ANCHOR, ONCE, AT BUILD TIME.** `weapons.py` anchors every
  firearm on what a zombie can survive; this anchors every plate on what a
  zombie can do. Everything is a function of that one number plus the
  MATERIALS, the SLOTS and one exponent, and there is not a hand-picked
  durability figure anywhere.
- **MATERIAL SETS THE NUMBERS, SLOT SETS WHERE THE HITS LAND.** Twenty rows
  stay readable because a player who has learnt what leather does has learnt
  it for all five slots, and the only question left about a piece is whether
  they are already wearing something better THERE. Soak is a quarter of the
  ceiling per rung, so "one better" means the same thing everywhere on the
  ladder; durability is `HITS_BASE * tier` blows landing on that part; weight
  and price come off the tier too.
  It is also why the ICONS are five shapes in four colours — which is the
  exact opposite of the creature rule, where three variants must be three
  silhouettes. There the question is "what is that"; here the player already
  knows it is a helmet and the question is "is it better than mine". A ladder
  whose rungs are four different shapes cannot be ordered at a glance.
- **WHERE A BLOW LANDS IS THE SPRITE'S OWN ANATOMY.** `COVERAGE` is derived
  from `_AREA` — the pixels `make_player.py` actually spends on each part of a
  fifteen-row figure, which is S17's proportion. So the HELMET is the piece that matters
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
- **A PIECE OF ARMOUR IS NOW ALSO A CLAIM ABOUT WHAT YOU ARE.** Every
  material carries a SET NAME and a set of TAGS, and an ultimate's
  requirements are written against them — see [`ultimates.md`](ultimates.md).
  Nothing in this module knows what an ultimate is: armour answers "what am I
  wearing", the ultimate catalog answers "what does that unlock", and the only
  thing travelling between them is a string. That separation is what lets the
  synergy system grow without this file changing, and it is why the tags are
  on `Material` rather than in a table somewhere that knows about both.
  The consequence for THIS system is real and deliberate: the best plate in
  the game carries exactly one identity, so wearing it locks three ultimates
  as surely as it unlocks the fourth. "Buy the most expensive thing you can
  afford" stopped being the whole of the armour decision on the day that
  became true.
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
  lands**, and there are five answers because a player has five containers.
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

- **A PIECE OF GEAR DESCRIBES ITSELF THE SAME WAY EVERYWHERE, AND IT SAYS
  WHAT IT DOES.** A player meets the same object four times — on a shop table,
  on the ground, on the belt, on the body — and it used to introduce itself
  differently each time and never say anything useful: a name and a price at
  the stall, a name in a prompt, a name and an ammo count on the belt, and the
  raw key `steel` on the armour panel. You could pick up a pair of steel
  greaves and not notice. So there is ONE function (`gear-card.ts`) that turns
  a catalog key into rows, and one component that draws them.
- **EVERY ROW IS A REAL NUMBER IN A REAL UNIT.** The first cut of the cards
  led with `abate em 3 tiros`, `absorve 56%` and `aguenta 61/61` — three
  INTERPRETATIONS of numbers the player never got to see. A stat block exists
  to compare two objects and you cannot compare two interpretations: 56% of
  what, measured against which blow? So the headline is `DANO 9`,
  `ARMADURA 5`, `DURABILIDADE 61`, in the game's own units — damage points,
  tiles, kilos, rounds a minute. Counts that a player would work out anyway
  and get wrong stay as clearly labelled counts below the number they are
  counting — `DANO/S` is the only one left, because damage and cadence are
  both real and both meaningless alone.
  **AND NOTHING ON A CARD IS ANCHORED ON A CREATURE.** `TIROS P/ ABATE` and
  `GOLPE DE ZUMBI 9 → 4` were true and were still wrong: they described one
  enemy, and this game is going to have more. If a stat needs an example to
  make sense, the stat is wrong, not the example — which is what sent armour
  back to `armor.py` to come out flat.
  A ZERO IS NEVER PRINTED. `RUÍDO 0.0t` on a shield is not a stat, it is a
  field that did not apply, and a card that lists what an object does not have
  has stopped being a description.
  The panel's own header is the same number for the whole set, which is why
  it sits in damage points directly above a health bar counted in the same
  ones: `-5` beside `100` is a sentence, `56%` beside `100` is two unrelated
  numbers.
  The ONE percentage left anywhere is the shield's walk multiplier, because a
  multiplier has no other honest unit: the walk it scales is already the
  product of a skill, a carry weight and a sprint.
- **THE SHOP SHOWS ITS CARD WITHOUT BEING ASKED.** Everywhere else a card is a
  hover, because everywhere else the object is already yours or is lying in the
  grass costing nothing. A shop table is the one place a party spends a whole
  night's extraction, and choosing between a rifle and a breastplate off two
  names and two numbers is choosing blind. It stacks ABOVE the action line so
  the line — key, verb, price — stays exactly where the player already knows to
  look, and the pair points at the stall once, from the half that is pinned to
  it.
- **A REFUSAL SAYS WHY.** "Inventário Cheio" was printed over a box of rifle
  rounds by a player with an empty bag: not true, explains nothing, and teaches
  the player that the prompt lies. There are three refusals and only one is
  about space — no cell (`Mochila cheia`), a calibre nobody in your hands can
  fire (which is not a refusal about YOU at all: the rounds belong to whoever
  brought the gun), and a reserve already full (muted, not red — nothing is
  wrong, and the box will still be there on the walk back).

## Known gaps

- **Cards are unplayed.** The four surfaces typecheck and the rows are derived
  from the live catalog, but nobody has hovered one mid-fight. Worth watching:
  whether the shop's unprompted block is welcome or is in the way when you
  already know what you want, and whether the belt's hover fires by accident
  when a player parks the cursor in that corner.
- **No dedicated sound.** A plate soaking is silent (the blow it came with is
  not) and a piece breaking borrows `crate-break` pitched up. A steel tick, a
  leather scuff and a polycarbonate crack are three recipes in
  `make_audio.py` and one call site each; nobody has written them.
- **The overlays have not been looked at in a browser at speed.** They are
  registered on measured bands and `make_armor._check` fails the build if one
  leaves the grid, but nobody has watched a body in a full steel set walk
  across a clearing to see whether the plate reads as worn or as painted on.
  The BRACERS are the piece to watch: they are two columns either side of the
  chest and they are the one overlay drawn off the walk block that the HOLD
  pose actually moves, so they stay put on the frames the weapon arm is
  raised.
- **The boots are one row.** Row 15 is the whole budget — it is what the
  contact shadow sits under and what the walk lands on — so the overlay is a
  single lit band, two columns wider on each side than the trouser cuff above
  it. That flare is the entire read, and whether it survives a body walking
  away from the camera is unknown.
- **The shield has no impact art.** A blow stopping dead on it currently looks
  the same as a blow missing. The spark belongs in `weapon-vfx` and wants the
  hit point, which `armorHits` already carries.
