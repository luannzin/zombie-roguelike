# Ultimates: the synergy between a weapon and what you are wearing — design law

Nearest contracts: [`server/app/AGENTS.md`](../../server/app/AGENTS.md),
[`client/src/game/AGENTS.md`](../../client/src/game/AGENTS.md),
[`client/src/components/AGENTS.md`](../../client/src/components/AGENTS.md).

| | |
| --- | --- |
| **Owns** | the ultimate catalog, the tag vocabulary both halves of a build speak, what fills a bar, what a press does to the world, and the panel above the belt |
| **Inputs** | `{type:"ult"}` (R) |
| **Outputs** | `snapshot.ults` / `volleys` / `ultBursts`, player tick `ult` (the open window), roster `ult` (the bars), `welcome.config.ultimates` / `ultimateTags` / `ultimateSetPieces` |
| **Depends on** | `weapons.WeaponDef.tags`, `armor.Material.tags` + `Loadout.tag_pieces`, `projectiles.py` (a volley's flight), `Room.damage_enemy` / `heal_player` (the one doors) |
| **Consumers** | `Room.use_ultimate` / `_charge_ult` / `_empower` / `step_ult_shots`, `Game.ultimateHud` / `playUltimate`, `client/src/components/hud/Ultimate.tsx`, `render/layers/effects.drawVolleys` |
| **Authoritative** | whether the press is legal, what the effect does, what the bar is worth, how long a window lasts |
| **Presentation** | the mark, the panel's five states, the burst, the crescent, the shake |

## Invariants

- **Nothing anywhere names a combination.** There is no `if weapon == "minigun" and armor == "steel"`. A weapon carries tags, a material carries tags, and an ultimate lists the tags it needs.
- **One ultimate per weapon, enforced at import.** `ultimates.BY_WEAPON` raises on a second — the HUD panel is the weapon in hand and there is nowhere to draw a choice.
- **The panel follows the hand.** There is no selection, no binding and no second belt: 1/2/3 decides what R does.
- **The bar is per ULTIMATE and per SOURCE.** A katana's charge does not move while its owner shoots, and a medic's cannot be filled by shooting.
- **A locked bar does not fill at all.** Locked and empty are the same state on the wire, so the panel can never show a full bar under a padlock.
- **There is no cooldown.** Firing spends the bar; the bar refills by playing.
- **A window belongs to the weapon that opened it.** `Room._empower` checks the weapon, not just the window; the seconds keep burning while it is holstered.
- **Nothing is predicted.** R is the only key in the game with no local half — the burst, the shake and the sound all wait for the server's own event.
- **Every effect goes through the existing one door.** A volley's hits land in `damage_enemy`; an aura's healing lands in `heal_player`. An ultimate must never be the one thing that skips a plate or forgets to pay xp.

## Danger zones

- `Room.use_ultimate` — the bar is spent BEFORE the effect. An ultimate that found no target is still an ultimate that was fired, and a `return` above the spend is a free one.
- `Room._charge_ult` — three guards (the weapon owns it, the source matches, it is unlocked). Dropping any one silently changes what the game rewards.
- `projectiles.Impact.hits` carries an OWNER as its fifth column. Dropping it makes an ultimate the one way to clear a pack for no xp.
- `ultimates.SET_PIECES` is counted in PIECES. Switching it to coverage makes one leather cap a full ninja set, because the head is over half this sprite.
- `TAGS` — a tag required of armour that no material carries is an ultimate that can never unlock, and it looks exactly like one the player has not found the armour for. `_check_armor_tags` fails the import.

## Change surface

| intent | touch |
| --- | --- |
| add an ultimate | one `UltimateDef` in `server/app/ultimates.py` + a mark in `server/tools/make_ultimates.py` |
| give an existing ultimate to a second weapon | a tag on that weapon's row in `weapons.WEAPONS` — nothing else |
| retune how often one comes round | `UltimateDef.charge_full`, one number |
| what an ultimate DOES | its effect block (`Volley` / `Empower` / `Aura`) |
| a new KIND of effect | a fourth block + one branch in `Room.use_ultimate` |
| which set unlocks what | `armor.MATERIALS`' tags and `UltimateDef.requires` |
| what a requirement is CALLED | `ultimates.TAGS` |
| how much of a set counts | `ultimates.SET_PIECES` (or `UltimateDef.pieces` for one row) |
| the panel's five states | `client/src/components/hud/Ultimate.tsx` |
| the mark's locked / ready treatment | `client/src/components/hud/UltimateIcon.tsx` |
| what an activation LOOKS like | `Effects.spawnUltimate` + `Game.playUltimate` |
| what a thrown one looks like | `render/layers/effects.drawVolleys` + `--ult-arc` |

**Do not touch from here:** the skills catalog (that is what a RUN bought and it
is permanent), `Mods`, the ammunition economy, or `damage_player`.

---

## Design law

- **THE PROBLEM THIS SOLVES IS THAT NOTHING YOU WORE EVER CHANGED WHAT YOU
  COULD DO.** A weapon was a rate of damage and armour was a rate of damage
  taken. Both were dials, both were bought with the same gold out of the same
  shop, and the whole of a party's build decision was therefore "buy the
  biggest number you can afford", twice, independently. Four players who had
  played equally well were four identical survivors with different-coloured
  plate on.
  An ultimate is the JOIN. Every weapon owns exactly one, and it is locked
  until the body holding that weapon is also wearing the right set — so the
  minigun's answer to a crowd exists only for somebody dressed in riot steel,
  and the katana's exists only for somebody who gave up steel to move. Two
  players holding identical weapons are now different characters because of
  what they put on.
- **THE LADDER AND THE IDENTITY ARE THE SAME COLUMN, AND THAT IS THE WHOLE
  BALANCE ARGUMENT.** Armour could have grown a second axis — a tier for the
  numbers and a "kind" for the flavour, cross-multiplied. That is a catalog
  four times the size and, far worse, a catalog with a strictly correct answer
  in it: whatever the top tier of your preferred kind happens to be. Folding
  the two together means the best plate in the game carries exactly ONE tag, so
  wearing it locks three ultimates as surely as it unlocks the fourth, and the
  player who wants a different one has to give up armour to get it.
  `test_ultimates.py` asserts it as arithmetic: no material may gate two.
  The consequence is a ladder where every rung is somebody's endgame. Cloth is
  the medic's, leather is the assassin's, steel is the gunner's, kevlar is the
  marksman's — and the cheapest thing in the shop unlocks the support build,
  deliberately, because a party's healer should not have to be the richest
  person in it.
- **THE SYSTEM IS DATA OR IT IS NOTHING.** The first version of this feature
  that anybody writes has `if weapon == "minigun" and armor == "riot"` in it,
  and that version is finished the moment it ships: every new ultimate is a
  new branch, every new weapon that should satisfy an old one is another, and
  within four additions nobody can answer "what unlocks this" without reading
  code. So a weapon carries TAGS, a material carries TAGS, and an ultimate
  lists the tags it needs — and `Room` never learns a weapon's name.
  The claim is asserted rather than documented. `test_ultimates.test_data_row`
  builds a fifth ultimate inside the test, out of the same dataclasses, for a
  weapon that has never had one, and drives it through the unmodified room. If
  any part of the pipeline had learned a name it fails, and it fails for the
  right reason.
- **A TAG IS SOMETHING A PLAYER WOULD SAY OUT LOUD.** `automatic`, `precision`,
  `blade`, `Conjunto Sombra`. That is the test for whether a tag is worth
  having, because the HUD PRINTS them: a requirement row the player cannot read
  is a lock with no key drawn on it. It is also why `TagDef` carries a `source`
  — an armour tag is met by wearing enough of a set and draws as progress
  ("2/3"), and a weapon tag is met by holding one thing and draws as a tick.
  A row that could only say "no" would hide the fact that somebody is one
  helmet away from an ultimate.
- **A SET IS THREE OF FIVE PIECES, COUNTED IN PIECES.** Coverage is the more
  elegant sum and it is the wrong one here: the head is over half of this
  sprite (`armor.COVERAGE`), so a coverage rule would make ONE LEATHER CAP into
  a full ninja set. Pieces are what the player watches themselves collect, what
  the mannequin draws, and what a HUD row can print.
- **THE BAR IS PER ULTIMATE, AND THAT IS WHAT MAKES THE BELT A SET OF SEPARATE
  PROMISES.** One shared meter is a third of the code and a completely
  different game: the correct play becomes "charge with whatever is convenient
  and fire with whatever is strongest", which is the exact opposite of what
  this system exists to make people do. Your katana's charge sits on the katana
  while you spend a night shooting a Deagle, and it is still there when you
  draw it again.
- **AND IT IS EARNED BY DOING THAT WEAPON'S JOB.** A gunner charges on damage,
  a medic charges on healing, and neither can charge by doing the other's — so
  "carry the support gun and play normally" is not a build. The medic's is the
  one row in the catalog that is a statement about having other people with
  you: solo it is nearly unreachable, and in a party it is the natural
  consequence of doing the job.
- **THERE IS NO COOLDOWN, AND THE ABSENCE IS THE FEATURE.** Firing spends the
  whole bar; the bar refills by playing. A timer on top would be a second clock
  saying the same thing as the first and, worse, a promise that the game will
  hand it back for free — which is exactly the arbitrary ability button this is
  meant not to be. What you get back is what you go and earn, which is also why
  the panel has five states and not six.
- **A LOCKED BAR DOES NOT FILL.** The player is shown LOCKED → CHARGING →
  READY, so that has to be the machine the server runs. A bar that filled
  behind a padlock would make the panel say two things at once, and the moment
  the armour was finally bought the ultimate would fire immediately — which
  reads as the lock having been decorative.
- **FOUR ULTIMATES, FOUR VERBS.** That is the acceptance test for the catalog:
  if two of them would both be described afterwards as "press R for more
  damage", one should not exist. A crescent that cuts a lane through a pack,
  one round that deletes whatever it touches, six seconds of not having to
  think about ammunition, and a pulse that puts the party back on its feet are
  four things a player would tell you about differently.
  Each one is also shaped by its weapon's actual PROBLEM rather than by its
  strength. A katana answers the one thing that got close and has no answer to
  the six behind it, so its ultimate opens a lane. A minigun's real enemy is
  its own reserve — thirteen seconds of held trigger empties a full rifle pouch
  — so its ultimate is six seconds of not counting rather than six seconds of
  bigger numbers. That is why `Empower` has a `free_ammo` flag at all.
- **AN ULTIMATE IS STILL MISSABLE.** A volley runs on `projectiles.py`, which
  means it inherits that module's two rules: it can be walked out of, and it
  passes through a crowd billing each body once. A crescent that homed would be
  a button that deletes what you point it at, which is a cutscene rather than a
  weapon; one that stopped on the first zombie would be a very expensive way to
  kill one zombie.
- **NOTHING ABOUT IT IS PREDICTED, AND IT IS THE ONLY KEY IN THE GAME LIKE
  THAT.** A shot is predicted, a swing is predicted, the shield goes up on the
  frame the button is pressed — all three are cheap to be wrong about. An
  ultimate is a night's charge, and flashing the screen and then not having
  fired would be the worst frame in this game. So the burst, the shake and the
  sound all wait for the server's own `ults` row, which is also what makes a
  teammate's ultimate and your own the same event drawn by the same code.
  The one thing that answers locally is a refusal, and only when the panel
  already says so — a key that does nothing with no explanation reads as a
  dropped input.
- **ONE BURST FOR FOUR ABILITIES.** What the activation beat has to
  communicate is not *which* ultimate fired, it is *that one did*: a party of
  four needs to read "somebody just spent theirs" across a dark clearing in a
  fifth of a second, and four different bursts would be four things to learn
  instead of one. Which ultimate it was is on the panel, on the sound, and
  about to be extremely obvious anyway. Same argument for `--ult-flash` being
  neutral gold rather than each ultimate's own hue.
  The SHAKE is only the presser's. A teammate's ultimate across the clearing is
  a thing you see; shaking the camera for it would lurch the screen for an
  event the player had no part in.
- **THE PANEL SAYS LOCKED ALWAYS AND WHY ONLY WHEN ASKED.** A permanent
  requirement list is three more lines of text in the corner the player is
  fighting toward, answering a question that is asked once per build and then
  never again. But the list is shown on hover even when every row is MET —
  a list that vanished on success would teach this system to exactly one
  player, the one who happened to look at it while it was still locked.

---

## Server contracts

- **`{type:"ult"}` CARRIES NO PAYLOAD.** Which ultimate fires is decided
  entirely by what the server thinks is on the belt on the frame the message
  lands. A client that named one could fire the katana's while holding the
  minigun, one dropped hotbar packet later.
- **THE WINDOW IS A POSE AND THE BAR IS A METER**, and that is why they ride
  different rows. `ult` on the TICK row is the open window: every client draws
  the charge burning off a body, and at roster rate a six-second window would
  visibly start and end late on everybody else's screen. `ult` on the ROSTER is
  the bars, which only their owner reads and which fill over a night.
- **THREE EVENT LISTS AND THEY ARE THREE KINDS OF THING.** `ults` is a
  one-shot (somebody pressed R); `volleys` is STATE, whole every tick, because
  a client that missed a packet still has to draw the crescent halfway across
  the clearing; `ultBursts` is a one-shot again.
- **A VOLLEY IS NOT A SPIT.** They are one mechanic server-side and two
  completely different pictures, which is why `Projectile` carries a `look`
  string the room copies onto the wire and never interprets — and why the
  client has `DrawableVolley` beside `DrawableSpit` rather than a branch inside
  one draw call.
- **THE OWNER IS THE FIFTH COLUMN OF A PROJECTILE HIT.** Without it an ultimate
  would be the one way in the game to clear a pack for no xp and no level — a
  button that makes the run worse.

## Known gaps

- **No dedicated sound.** An activation borrows the level-up's summon column
  and its sample, pitched down. That is a defensible pairing — both are "a
  thing happened to this body that the party should look at" — but four
  ultimates sharing one voice is the loudest remaining hole. Four recipes in
  `make_audio.py` and one call site each.
- **Only one `Volley` look exists** (`slash`), so `drawVolleys` has one branch
  it never takes. The second one is what will prove the string is doing its
  job.
- **Unplayed.** Everything here is pinned by `test_ultimates.py` and was
  verified in a browser as far as the pane allows — the panel renders in its
  locked state, in the right place, off the real config — but nobody has
  charged a bar by fighting, pressed R at a pack, or watched a crescent cross a
  clearing. What wants eyes on it: whether `charge_full` comes round too often
  or never; whether six seconds of Tempestade de Balas reads as an event or as
  a stat; and whether a locked panel over the belt is a goal or is nagging.
