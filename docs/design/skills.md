# Skills & the upgrade machine — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).

| | |
| --- | --- |
| **Owns** | what a LEVEL buys: the skill catalog (36 rows), the rarity roll, `Loadout` (stacks + spins owed), and `Mods` — the flattened numbers every other module multiplies by |
| **Inputs** | xp reaching a level (`Room._sync_spins`), `{type:"spin"}` at the cabinet, and the party's `balance` once no level is owed |
| **Outputs** | `spin` events, `snapshot.spinPrice`, `PlayerMeta.skills` / `mods` on the roster, `welcome.config.skills` + `config.machine` |
| **Depends on** | `machine.py` (the timeline), `store.py` (the cabinet's spot), `config.py` (the base numbers `Mods` diverges from) |
| **Consumers** | `simulation.apply_input` (speed, carry ceiling), `Player.max_hp`, `Room.fire` / `Room.swing` (damage), `Room.damage_player` (armour), `damage_enemy` (xp, coin odds), `Room._tip_item` (what a platform credits), the client's battery |
| **Authoritative** | the roll, the stacks, the spins owed, every number in `Mods` |
| **Presentation** | reels, the lever, the pay-line flash, the tin's flight to the tray, the tray row |

## Invariants

- **A level is a token and the machine is the only thing that spends it.** Nothing else in the game consumes a spin.
- **KILLING IS THE ONLY SOURCE OF XP.** Not an omission — see *What a level
  costs* below. A pass that paid xp per point extracted was built and taken
  back out.
- **A level is FREE and gold is the overdraft.** `Room.spin` spends a banked level whenever one is owed and only reaches for `Room.balance` when none is. The price doubles per purchase and resets on the walk into each night's shop.
- **`Loadout.mods` is the ONLY place a player's numbers diverge from `config.py`.** A site still reading the raw constant is a site where a skill silently does nothing.
- **The roll happens on the press; the show happens after.** One `spin` event carries the whole four seconds. A result arriving mid-animation is a reel that changes its mind.
- **One lever.** `Room._machine_busy` is a countdown (this room has no wall clock); a second press is refused.
- **`server/app/machine.py` and `client/src/game/machine.ts` are one clock.** Change together.
- **Rarity is the same five-grade ladder as loot**, painted in the same five colours.
- **The catalog and the icon sheet are ONE LIST IN TWO FILES**, in the same
  order, and both are append-only. `skills.FRAME` is a row's catalog index, so
  a row inserted anywhere but the end re-points every tile after it at somebody
  else's picture and nothing errors. `make_skills._check_order` fails the build
  on any disagreement — it is the only guard there is.

## Change surface

| intent | touch |
| --- | --- |
| the xp curve | `XP_BASE` / `XP_GROWTH` in `server/app/config.py`. What PAYS it is `Room.damage_enemy` and nothing else |
| the price of a bought pull | `STORE_SPIN_PRICE` in `server/app/config.py` (the ladder itself is `Room.spin_price`) |
| add/retune a skill | `server/app/skills.py` + every consumer site above + an icon in `server/tools/make_skills.py` |
| machine timing | `server/app/machine.py` AND `client/src/game/machine.ts` |
| the ceremony drawn | `client/src/render/layers/store.ts`, `client/src/render/machine.ts` |
| the payout tin | `server/tools/make_skills.py` (the art), `client/src/components/hud/SkillCanIcon.tsx` (the sprite), `Game.spawnSkillFly` / `landSkillFly` |
| the HUD tray | `client/src/components/hud/SkillTray.tsx`, `Game.skillList()` |
| the level-up beat | `Game.onLevelUp`, `client/src/components/hud/Announce.tsx`, `drawLevelUps` in `render/layers/effects.ts` |

**Do not touch from here:** the store's stock/prices, extraction quotas, or the
economy settlement.

**Adding a skill checklist:** catalog row in `skills.py` (append, never insert)
-> the number it moves must be read through `Mods` at its consumer site -> icon
in `server/tools/make_skills.py` in the SAME position -> regenerate
(`python tools/make_skills.py` from `server/`, which fails if the two lists
disagree) -> `SKILL_FRAMES` in `client/src/components/hud/Hud.tsx`.


## What a level costs

- **THE OPENING WAS FREE AND IT PAID FOR THE WRONG THING.** At `XP_BASE` 40
  against a zombie's 12 xp, level 2 cost 3.3 zombies and level 5 cost 24 of
  them cumulatively — one night-one forest, with its 32-body cap and its 2.5s
  respawns, handed out four or five levels before the party had met anything.
  Four spins on night one is the machine's entire ceremony spent on somebody
  who has not yet learned what a skill is for, and it is why the run's back
  half felt flat: the interesting part of the curve was over before the game
  had started.
- **THE FIX BELONGS IN THE PRICE OF A LEVEL, NOT IN A SECOND SOURCE.**
  Extraction paying xp per point delivered was tried and reverted. It looked
  right — the pad is what a night is about, and it paid no progression — but it
  made the level bar a SECOND QUOTA METER: one act was already paying money and
  a quest row and the night's whole objective, and adding xp to it meant the
  number over a dying body stopped being the only reason to fight anything. A
  currency that everything pays is not a currency.
- **SO KILLING IS THE ONLY SOURCE, AND THE CURVE IS PRICED FOR THAT.** 110 is
  roughly nine zombies against the old 3.3 — a night's fighting for the first
  level rather than the first minute's. The growth came DOWN (1.4 -> 1.28) at
  the same time because the base now carries the weight: 1.4 off a bigger base
  puts level ten out of reach of a ten-night run, which is the opposite mistake
  and just as bad.
- **WHICH MEANS A LEVEL IS PAID FOR IN RISK, AND THAT IS THE POINT.** Xp only
  comes from things that were trying to kill you, so the spin waiting at the
  cabinet is a receipt for danger taken rather than for errands run. Now that a
  crowd is genuinely lethal, "kill more" and "stay alive" are in real tension —
  which is the tension the machine is supposed to sit at the end of.

---

## Design law

- **A LEVEL IS A TOKEN AND THE MACHINE IS THE ONLY THING THAT TAKES IT.**
  xp used to be a bar that filled and changed nothing. A level now pays one
  SPIN (`server/app/skills.py`), spins bank across nights, and the only place
  one can be spent is a slot cabinet standing on the WEST arc of the merchant's
  clearing — two tiles wide, red, with a gold hood of bulbs, three windows, a
  lever and a tray. It used to be a three-tile dented grey wreck with a car
  battery cabled to its base, which was a good story and a bad object: at that
  size it was a wall in a small shop, and a dark dented box at night is
  indistinguishable from the market stalls beside it. It stands ACROSS the room
  from everything that is about money, so it is somewhere a party WALKS to
  after they have spent — which is the whole difference between a machine and a
  menu item.
  - **AND WHEN THE LEVELS RUN OUT IT TAKES MONEY.** A cabinet that went dead
    the moment a party had spent their levels was a machine with an opening
    hour: everybody pulled in the first ten seconds of the shop and then walked
    away from it for the rest of the visit, which is exactly the beat the thing
    was built to own. It now sells a pull for gold once nothing is owed —
    `STORE_SPIN_PRICE`, doubling with every one the party buys — so there is
    always an offer standing at the far end of the clearing and the decision is
    theirs rather than the machine's.
    - **THE LADDER IS EXPONENTIAL BECAUSE THE THING BEING SOLD HAS NO
      CEILING.** At a flat price a rich night ends with somebody standing at
      the lever until the balance runs out, and thirty pulls in a row is not a
      ceremony, it is a vending machine — the third reel's hold stops being
      anticipation and becomes latency. Doubling means the party always gets to
      buy one more and never gets to buy five: 50 is an easy yes, 100 is a real
      trade against the cheapest gun on a table, and 400 is a number nobody
      talks themselves into. The machine keeps saying yes and the PARTY is the
      one who has to stop, which is the only version of this that is a
      decision.
    - **IT RESETS PER NIGHT, NOT PER RUN.** The doubling exists to end a
      VISIT's buying, so carrying it across nights would make the price on
      night six a number nobody can reach and the whole mechanic would quietly
      stop existing halfway through a run. `Room.enter_store` puts it back at
      the bottom.
    - **AND IT IS THE PARTY'S, NOT A PLAYER'S**, because the purse it comes
      out of is. Four players cannot each buy a 50-gold pull; the second one
      costs 100 whoever is standing at the lever, the same way there is one
      balance and one conversation about who spends it.
    - **A LEVEL IS ALWAYS SPENT FIRST.** Nobody would ever choose to pay while
      holding a free spin, so making them say so would be a menu — the prompt
      names one currency at a time and the server picks the same one.
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
  - **WHAT COMES OUT IS A PICKUP, AND THE PLAYER IS THE ONE HOLDING IT.** The
    tray fires a TIN and it goes straight over the winner's head, hangs there
    the way every looted item in this game does, then flies into the tray ABOVE
    the bag on the HUD, where it becomes one ROW: icon, name in its rarity
    colour, and `x{n}`. It used to be thrown onto the machine's own tray to lie
    in the world for a second and a half before it left — which spent the beat
    after the reels on an object sitting on furniture while the person who won
    it stood beside it doing nothing. It is the same event a collect is, so it
    reuses the same flight (`loot-flies.ts`) rather than owning a second one;
    the only differences are the sprite and that it lands on the shelf rather
    than in a cell, because on a first copy the row it is landing in does not
    exist yet.
  - **THE TRAY MUST NOT KNOW BEFORE THE PLAYER DOES.** The server banks the
    skill on the frame the lever moves and marks the roster dirty, so the
    authoritative stacks arrive a fifth of a second later — three seconds
    before the ceremony that is supposed to be delivering it. `Game.pendingSkill`
    subtracts that copy back out of `skillList()` until the tin lands, the same
    trick a bag cell plays with `incomingHas` while a collect is still crossing
    the screen. Without it the flight is decorative: the row is already there
    when the tin arrives.
  - **THE TIN IS A TIN.** It was a 16x24 aerosol tube with two thin rarity
    bands on a steel body, which meant five tiers read as five grey tubes and
    the object stood taller than the icon it was carrying. It is a 16x18 canned
    good now — steel lid with a pull ring, base rim, and the rarity as the
    LABEL, which is most of the object — so the colour is legible at the size
    it actually appears at and the silhouette is one everybody already knows.
    **AND IT FLIES AT TWO THIRDS OF ITS OWN SIZE** (`LootFly.SKILL_TIN_SCALE`).
    Matching a loot drop's 2x zoom made the two sprites equal in PIXELS, which
    is not equal on screen: a tin is a solid cylinder where a loot icon is a
    small object with air around it, so at the same zoom it was still the
    largest thing that has ever appeared over a player's head — parked there
    for the length of the hold, covering the body it was being given to. The
    scale is on a wrapper rather than on the zoom because the zoom also sizes
    the label window off the manifest, and a fractional zoom would land the
    tin's picture on half a pixel. A skill is a stack, so a duplicate is a smaller
    pull rather than a dead one. The tray is a list of labelled rows and not a
    grid of tiles, because a wall of 16px icons asks the player to hover
    eighteen things to find out what they own — which is a spreadsheet with the
    words hidden. With nothing pulled yet it says so in one muted word rather
    than disappearing: a HUD region that shows up for the first time at the
    first shop is a region the player has to learn mid-run. There is no
    "giros guardados" badge any more — it repeated one fact for a whole night,
    and the marquee below already says it from across the room.
  - **THIRTY-SIX ROWS, AND THE SECOND EIGHTEEN EXIST BECAUSE A RUN IS TEN
    NIGHTS.** The first cut was five commons, four uncommons, four rares, three
    epics and two legendaries — and a party pulls roughly a dozen times in a
    whole run, almost all of it in the bottom two tiers. By the fourth pull
    they had seen most of the tier they were actually rolling in, and every
    pull after that was a duplicate: a smaller version of a number they already
    had. A duplicate is meant to be the CONSOLATION, not the median outcome.
    Nine / eight / eight / six / five is where a ten-day run stops repeating
    itself, and it costs nothing structural — `roll` picks the tier first and
    then a row inside it, so widening a tier does not move anybody else's odds.
    - **AND THE LEGENDARY WEIGHT DOUBLED, 2 -> 4.** Same arithmetic from the
      other end: at one in fifty, twelve pulls means most runs never once saw
      the colour the machine spends four seconds building up to — the reels,
      the pitch ladder and the anticipation on the third reel were all
      dramatising an outcome the player would not live to see. One in
      twenty-five is still eleven times rarer than a common. It is the thing
      that happens ONCE in a good run, rather than the thing that never
      happens.
    - **THE NEW AXIS IS ARMOUR**, and it is the only stat the second pass
      added. Every row in the first eighteen scales something you DO — move,
      hit, carry, earn, see — and there was nothing to pull that made being hit
      cost less, which is a strange hole in a game about walking into the dark.
      `Mods.armor` is a multiplier on damage TAKEN, applied in exactly one
      place (`Room.damage_player`, the door every claw, pellet and chainsaw
      comes through), and it is the one field with a FLOOR under it: unclamped,
      a lucky run stacks past zero and zombies start healing you. A third of
      every hit lands however the machine has gone, and `max(1, ...)` means a
      blow that connects always costs something.
    - It stacks multiplicatively against health rather than duplicating it:
      more HP is a longer bar, armour is a bar that drains slower. That is also
      why the two appear together on a legendary (Pele de Pedra) and separately
      everywhere else.
  - **AN ICON IS THE OBJECT, NOT THE STAT.** Five rows that all mean "you get
    hit less" would be five grey plates in a tray that already had one, so each
    of them is a different THING that happens to protect: a vest, a studded
    pad, a bolted plate with a scratch across it, a helmet, a skin of cracked
    stone. Two rows were redrawn during the second pass for exactly this — an
    open hand became a cut purse (it was the same pink lump as the fist two
    tiles away) and a steel fist became a barrel with a muzzle flash. The
    second one took the skill's NAME with it (Pulso de Aço -> Cano Longo),
    which is allowed: at sixteen pixels the picture is the thing the player
    reads, and a name that fights it is the wrong name.
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
  - **THE LEVEL ITSELF IS ANNOUNCED, IN THE WOODS, TWICE.** It was silent: the
    only evidence a level had happened was a marquee in a zone the player was
    not standing in, hours later. Now a SUMMON COLUMN fires on the body that
    earned it and a card says "Subiu de Nível / +1 ponto de habilidade" at the
    upper third (`Announce`). Two halves, and each covers the other's gap — in
    a party of four a banner alone never says WHOSE level it was, and a column
    alone never says what a level pays out. The card names the payout rather
    than the level number because the number is on the bar already and the
    spin is the thing the player cannot see.
    There is no wire event for it: the server derives the level from lifetime
    xp and puts it on the roster row, so the client watches for the edge and
    seeds itself from `welcome` — a reconnect at level 9 must not celebrate.

---

## Server contracts

- **A LEVEL IS A TOKEN, AND THE ONLY THING THAT SPENDS IT IS A MACHINE IN THE
  SHOP** (`skills.py`, `machine.py`). xp used to be a bar that filled and
  changed nothing; a level now pays one SPIN into `Player.skills`
  (`Loadout.sync_level`, called from `Room._sync_spins` wherever xp moves), and
  spins are banked until somebody stands at the cabinet at the far end of the
  merchant's glade and presses E. Nothing else in the game consumes one.
  - `Loadout.mods` is the flattened result and it is the ONLY place a player's
    numbers diverge from `config.py`. Every site that used to read a constant
    now reads it: `simulation.apply_input` (speed, carry ceiling), `Player.max_hp`
    (every heal and respawn), `Room.fire` / `Room.swing` (damage — folded in
    ONCE, above both the event and the resolution, so the number drawn over a
    body is the number it lost), `damage_enemy` (xp and `coins.roll_drop`'s
    odds), `Room._tip_item` (what a platform credits for a loaded item), and
    the client's own battery. A site still reading `MAX_HP` is a site where a
    skill silently does nothing.
  - The ROLL happens on the press and the SHOW happens after. One
    `spin` event carries the whole four seconds — which skill, which rarity,
    how many copies, how many pulls are left — and every client flies the
    reels, the eject and the settle off it plus `machine.client_payload()`. A
    result that arrived mid-animation is a reel that visibly changes its mind.
  - ONE LEVER. `Room._machine_busy` is a countdown, not a deadline, because
    this room has no wall clock; a second press while it runs is refused.
  - THE PRICE IS STATE, NOT A CONSTANT, so it rides the wire the way the
    balance does: `snapshot.spinPrice`, sent on the two events that move it
    (a pull bought, the walk into the next shop) and always on `welcome`, so a
    body that walks up to the cabinet reads a price rather than waiting for
    somebody else to buy one first. `STORE_SPIN_PRICE` is only the bottom rung.
    A bought pull's `spin` event carries `cost`; a level's does not.
