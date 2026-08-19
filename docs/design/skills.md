# Skills & the upgrade machine — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).

| | |
| --- | --- |
| **Owns** | what a LEVEL buys: the skill catalog, the rarity roll, `Loadout` (stacks + spins owed), and `Mods` — the flattened numbers every other module multiplies by |
| **Inputs** | xp reaching a level (`Room._sync_spins`), `{type:"spin"}` at the cabinet |
| **Outputs** | `spin` events, `PlayerMeta.skills` / `mods` on the roster, `welcome.config.skills` + `config.machine` |
| **Depends on** | `machine.py` (the timeline), `store.py` (the cabinet's spot), `config.py` (the base numbers `Mods` diverges from) |
| **Consumers** | `simulation.apply_input` (speed, carry ceiling), `Player.max_hp`, `Room.fire` / `Room.swing` (damage), `damage_enemy` (xp, coin odds), `Room._tip_item` (what a platform credits), the client's battery |
| **Authoritative** | the roll, the stacks, the spins owed, every number in `Mods` |
| **Presentation** | reels, the lever, the pay-line flash, the canister's arc, the tray row |

## Invariants

- **A level is a token and the machine is the only thing that spends it.** Nothing else in the game consumes a spin.
- **`Loadout.mods` is the ONLY place a player's numbers diverge from `config.py`.** A site still reading the raw constant is a site where a skill silently does nothing.
- **The roll happens on the press; the show happens after.** One `spin` event carries the whole four seconds. A result arriving mid-animation is a reel that changes its mind.
- **One lever.** `Room._machine_busy` is a countdown (this room has no wall clock); a second press is refused.
- **`server/app/machine.py` and `client/src/game/machine.ts` are one clock.** Change together.
- **Rarity is the same five-grade ladder as loot**, painted in the same five colours.

## Change surface

| intent | touch |
| --- | --- |
| add/retune a skill | `server/app/skills.py` + every consumer site above + an icon in `server/tools/make_skills.py` |
| machine timing | `server/app/machine.py` AND `client/src/game/machine.ts` |
| the ceremony drawn | `client/src/render/layers/store.ts`, `client/src/render/machine.ts`, `render/skills.ts` |
| the HUD tray | `client/src/components/hud/SkillTray.tsx`, `Game.skillList()` |

**Do not touch from here:** the store's stock/prices, extraction quotas, or the
economy settlement.

**Adding a skill checklist:** catalog row in `skills.py` -> the number it moves
must be read through `Mods` at its consumer site -> icon in
`server/tools/make_skills.py` (append, never insert) -> regenerate.

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
