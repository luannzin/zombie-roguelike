# Player: movement, belt, weapons, pocket — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md).

| | |
| --- | --- |
| **Owns** | movement + stamina, the 3-cell belt, the weapon catalog and both resolvers, ammunition, the pocket, and the two carried weights |
| **Inputs** | `InputPacket` (move, aim, attack, `held`, `sprint`, lantern), `{type:"collect"}`, `{type:"drop","slot"}`, `{type:"buy"}` |
| **Outputs** | player tick rows (`st` stamina, `wind`, `held`, `ads`), roster `inv` / `guns` / `mods`, `shots` / `swings` events, `welcome.config.weapons` |
| **Depends on** | `skills.Mods` (every ceiling), `config.py` (the base numbers), `loot.py` (catalog rows), `store.py` (the only gun source) |
| **Consumers** | `combat.py`, `ai.py` (noise), `rift.py` (what a pour tips), `client/src/game/simulation.ts` + `prediction.ts` |
| **Authoritative** | position, stamina, health, belt contents, pocket contents, ammunition, every damage number |
| **Presentation** | the held sprite, recoil, the blade's arc, muzzle fire, hit juice, the bag panel |

## Invariants

- **`server/app/simulation.py` and `client/src/game/simulation.ts` are line-for-line mirrors.** Changing one alone makes the local player rubber-band.
- **Two weights, and conflating them is a bug this split exists to fix.** Roster `inv.w` is the POCKET alone (what the bag bar measures); `Player.carry_weight` is the bag **plus only the weapon in hand**, and the client rebuilds it (`Game.moveWeight`) because `heldSlot` is client-authored.
- **The whole gun catalog is derived from CS2's stat block**, scaled by `DAMAGE_SCALE = ZOMBIE_HP / 100`. Do not add a hand-written number to `weapons.py` — add a row with its source columns.
- **A trigger resolves in one of three ways and the catalog says which**: one ray, `pellets > 1` (shotgun, one shell, six rays, a fixed cone), or `fire_on_release` (the AWP).
- **A gun FIRES and the knife SWINGS, and they are two resolvers.** `Room.handle_attack` dispatches on the weapon's `melee` block, never on a `kind` string — so a second blade is a catalog row and no code.
- **The belt has a floor and the floor is the KNIFE.** Not collectable, not droppable, not swappable; it costs a gun slot rather than adding a fourth cell. **A run opens with no gun.**
- **Guns are BOUGHT and never found.** Every weapon row is `droppable=False`; `store.py` is the only source.
- **Ammunition is upkeep, not cargo.** Boxes are worth 0, take no pocket slot, and are collectable only by a player whose own belt holds that calibre. Reserves are sized in KILLS (`KILLS_PER_RESERVE`), not seconds of trigger.
- **A dry trigger burns the cooldown**, on both sides.
- **A full belt TRADES rather than refusing**, and a refused trade must not charge.
- **Stamina is stateless apart from the `winded` latch** — that is what lets prediction replay it. Every tick that skips `apply_input` must still tick the breath.
- **Never hardcode a gameplay constant client-side.** They arrive in `welcome.config`.

## Danger zones

- `simulation.py` / `simulation.ts` — the mirror.
- `prediction.ts` reconciliation and `last_processed_seq` (never reset on embark).
- `weapons.WEAPONS` ordering — **append, never insert**, or every generated frame index moves.
- Any site reading a raw `config.py` constant instead of `Mods` — a skill that silently does nothing.

## Change surface

| intent | touch |
| --- | --- |
| add a gun | `server/app/weapons.py` + `loot.py` row (`pocket="hotbar"`) + `server/tools/make_guns.py` + `make_loot.py` (append) |
| add a melee weapon | the same list plus a `MeleeDef` of `ComboStep`s — nothing else |
| movement / stamina | `server/app/simulation.py` **and** `client/src/game/simulation.ts`, `config.py` |
| ammunition | `server/app/ammo.py` (mechanics) / `weapons.py` (sizing) |
| pocket rules | `server/app/inventory.py`, `Room.collect_loot` / `drop_loot` — and the client's mirror of what a collect refuses, `client/src/game/interaction.ts` (`canStow`, `swapTargetFor`) |
| shot feel | `client/src/game/combat.ts`, `effects.ts`, `entity-visuals.ts` |
| bag / belt HUD | `client/src/components/hud/Inventory.tsx`, `Hotbar.tsx`, `Game.inventoryHud()` / `hotbarHud()` |
| what E offers, and whether it is refused | `client/src/game/interaction.ts` — every reach test and prompt, pure over an `InteractionState` |

**Do not touch from here:** extraction pad state, store pricing, the skills
catalog, or map generation.

---

## Design law


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

---

## Server contracts

- **Loot is not a coin.** Coins magnetize off a corpse. A drop sits next to
  a scene, shows a tooltip, and is collected with `{type:"collect","id"}`.
  The catalog and rarity weights live in `loot.py`; the client never invents
  a name or a colour. Camp maps have none. Valuables land in the pocket
  (`player.inv`); guns land on the hotbar (`player.guns`, `weapons.py`) —
  they do not stack. `ItemDef.pocket` is which. A full bag refuses; a full
  BELT trades instead — see `swap_weapon`. `{type:"drop","slot"}`
  pulls a bag cell back onto the ground near the feet (`inventory.take`,
  `loot.place_near`); camp and the walk-out refuse it. A stack is one
  world drop per unit. Guns are not tossed from the belt yet, except by
  being traded out from under the hand.
- **SHIFT is a REQUEST, and the breath is what answers it.** `sprint` rides
  every input packet, but nothing reads it as a state: `simulation.running`
  decides per tick whether the body is actually running (moving, key down, bar
  not empty, not `winded`) and `simulation.step_stamina` spends or refills it.
  `SPRINT_SPEED` MULTIPLIES the walk, so a skill's speed bonus and the carry
  penalty both still apply underneath. The system is deliberately stateless
  apart from the `winded` LATCH — no rest timer, no cooldown — because that is
  what lets the client replay it: `st` (and `wind` only while it is set) go out
  on the player's tick row, prediction snaps them and replays the inputs the
  server has not seen yet. A tick that does not call `apply_input` has to tick
  the breath itself, and every one of them does: the pour, both cutscene
  marches, and a socket that has gone quiet past the extrapolation window.
  Respawn refills it — the bar is not a punishment that outlives the death.
- **Two weights, and conflating them is the bug this split exists to fix.**
  Roster `inv.w` is the POCKET alone — it is what the bag's `current / maxkg`
  bar measures, so a rifle must never eat into it: that budget answers "how
  much loot can I still carry out" and guns are not what extraction is for.
  `Player.carry_weight` is the other number, what the WALK carries
  (`carry_scale`): the bag plus **only the weapon in hand**
  (`Hotbar.held_weight`), so a full rack is not a silent tax on having found
  things and switching to the knife genuinely moves you faster. It is not on
  the wire — the client rebuilds it from `inv.w` + `guns` against the same
  catalog (`Game.moveWeight`), because the hotbar selection is
  client-authored and a number computed here would be stale for exactly the
  frames the player is watching their own speed change.
- **A full belt is a TRADE, not a wall.** `Room.swap_weapon` puts the new gun
  in the held slot and drops the old one at the player's feet, through the
  same `{type:"collect"}` the client already sends. It refuses unless a GUN
  is in hand: the knife's cell cannot be consumed by a pickup, or the one
  weapon that cannot be lost would be one misplaced E away from being lost.
  Holstered refuses too — an empty hand is not a choice about which gun to
  keep. The gun you gave up lands on the floor rather than vanishing, so a
  trade is reversible one step later.
- **A gun is a catalog row AND a shot.** `weapons.py` owns damage, cadence,
  reach, muzzle, noise, AWP hold-to-aim (`aim_delay`) and the
  hotbar. Nobody spawns with a gun — see the knife bullet below. Input
  `held` is the slot in hand (-1 holstered), like the lantern switch; an
  empty hand does not fire. A collected gun equips itself only when the
  hand held no gun (empty, or the blade), so a first pickup arms you and a
  second does not take the weapon you were using out of your hands. Per-shot numbers ride `welcome.config.weapons`; the
  global `FIRE_COOLDOWN` / `SHOT_DAMAGE` / `SHOT_RANGE` are leftovers for
  a client that has not seen the catalog. Snapshot `held` / `ads` are
  what remotes draw. Ammo types are named and unused.
- **The belt has a floor, and the floor is the KNIFE.** The hotbar is three
  cells: `GUN_SLOTS` (2) gun cells plus one fixed cell at `KNIFE_SLOT` that
  always holds `knife`. `add` and `can_stow` only ever look at the gun
  range, `__post_init__` puts the blade back, and `loot.py` marks the row
  `droppable=False` so no pool can ever roll a second one. **`Hotbar.starting`
  hands out no gun** — a run opens holding the blade, and the first firearm
  is something you find. Do not make it collectable to "unify" it with the
  guns, and do not give it a fourth cell of its own: the guarantee is the
  feature and the slot it costs is the price.
- **A gun FIRES and the knife SWINGS, and they are two resolvers.**
  `Room.handle_attack` dispatches on the weapon's `melee` block, never on
  its `kind` string, so a second blade is a catalog row and no code.
  `combat.raycast` is a line that stops at the first thing it meets;
  `combat.sweep` is an arc that takes everything inside it, near first,
  measured SURFACE to surface so a fat creature is not harder to hit than
  a thin one standing in the same place. A swing that landed on flesh does
  not also take the crate behind it.
- **The combo is three beats and the chain is held open by a CLOCK, not by
  the button.** `ComboStep` carries its own damage, cadence, reach, arc,
  target cap and `window`; `Player.combo_step` / `combo_left` advance
  through them and `step_players` lets the window run out. Slash, slash,
  cut: the finisher is slower, wider, opens up to three bodies and has
  `window=0`, so it ENDS the chain rather than looping it. Holstering,
  respawning and embarking all reset it. The counter is never on the wire —
  a swing carries the step it WAS, which is all a remote needs to draw.
- **The blade's noise radius is its whole argument.** A gunshot wakes
  sixteen tiles; the entire knife chain wakes five, and only when it
  CONNECTS — a whiff is silent and is not broadcast at all. Raising it to
  match a gun would delete the reason the weapon exists.

- **AMMUNITION IS UPKEEP, NOT CARGO** (`ammo.py`). Every gun eats one round
  per shot out of the firing player's reserve; the knife eats nothing, which
  is most of why the knife is still in the game. A dry trigger still burns the
  cooldown, on both sides, or an empty gun clicks thirty times a second. Boxes
  are worth 0 and take no pocket slot — a round competing with a gold ring for
  a bag cell would make shooting a choice against extracting, which is not a
  trade-off, it is a tax on playing. THE FOREST STOCKS ITSELF AGAINST THE
  BELT: `mapgen.build_forest` is handed `ammo.party_calibres`, so a party of
  knives finds none at all, and `Room.collect_loot` refuses a box unless the
  COLLECTING player's own hotbar holds that calibre and has room for it — the
  rifle rounds belong to whoever brought the rifle, and a full reserve leaves
  the box on the ground for the walk back.
- **GUNS ARE BOUGHT AND NEVER FOUND.** Every weapon row is
  `droppable=False`, so no scene, object or roll can produce one and
  `store.py` is the only source. That is what makes calibre and ownership the
  same question: what the party paid the merchant for last night decides what
  the forest bothers to stock tonight. A purchase comes loaded
  (`Reserve.grant_for`), because a gun that could not be fired until the
  following night would make the shop feel broken.
